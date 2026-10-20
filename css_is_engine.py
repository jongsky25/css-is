"""
Office Connect calculator
=================

What this does, in one sentence:
    It keeps only the raw answers people gave ("atoms"), and calculates every
    score fresh from those answers using the SAME functions -- whether the score
    is for one staff member or the whole bureau, one event or the whole year.

Why that matters:
    There is no second set of "combining math" that can drift away from the
    per-survey math. Combining = "pick the answers you care about, then run the
    ordinary calculator on them." That is the whole design.

Three survey types:
    Type 1  ARTA walk-in CSM        1-5 agree scale, headline is a top-box %
    Type 2  Activity CSS (SERVQUAL) 1-7 scale, headline is a mean
    Type 3  Resource-person CSS     1-7 scale, mean (different dimension map)
"""

from __future__ import annotations
from dataclasses import dataclass, field
import numpy as np
import pandas as pd

# =====================================================================
# CONFIG -- every survey definition lives here as data, not code.
# Editing a dimension map or a band is a change here, never in the logic.
# =====================================================================

N_MIN = 10              # fewer responses than this -> the cell is flagged "low n"
CEILING_TOPBOX = 95.0   # top-box % at/above this (with enough n) -> "non-discriminating"

# Type 1 (ARTA), 1-5: 5=Strongly Agree, 4=Agree, 3=Neither, 2=Disagree, 1=Strongly Disagree
ARTA_HEADLINE_ITEMS = ["SQD1", "SQD2", "SQD3", "SQD4", "SQD5", "SQD6", "SQD7", "SQD8"]
ARTA_BANDS = [(0, 60, "Poor"), (60, 80, "Fair"), (80, 95, "Satisfactory"), (95, 100.001, "Outstanding")]

# SERVQUAL dimension maps (LOCKED). On B items, 0 means N/A.
DIM_MAP_FORM2 = {
    "Reliability":    ["B1", "B2", "B3", "B4"],
    "Responsiveness": ["B5"],
    "Assurance":      ["B6"],
    "Empathy":        ["B7"],
    "Tangible":       ["B8", "B9"],
}
DIM_MAP_FORM3 = {
    "Reliability":    ["B1", "B2", "B3", "B4"],
    "Responsiveness": ["B5"],
    "Assurance":      ["B6", "B7"],
    "Empathy":        ["B8"],
    "Tangible":       ["B9"],
}
OSQ_BANDS = [(1, 1.75, "Poor"), (1.75, 2.5, "Fair"), (2.5, 3.25, "Good"), (3.25, 4.001, "Excellent")]

# The full satisfaction battery on Forms 2 & 3, for the combined Quality Index:
# the nine SERVQUAL perception questions (1-7) PLUS the single OSQ "overall
# quality" question (C, 1-4). The expectation question (A) is deliberately NOT
# here — it is a baseline, not a satisfaction rating. Every question is scored
# equally after each is rescaled to 0-100 (see quality_index).
SERVQUAL_ITEMS = ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9"]  # 1-7
OSQ_ITEM = "C"                                                           # 1-4
QUALITY_SCALE_MAX = {**{it: 7 for it in SERVQUAL_ITEMS}, OSQ_ITEM: 4}    # per-item scale top
# Bands for the 0-100 Quality Index — the SEVEN_BANDS /7 thresholds mapped onto the
# 0-100 scale via (b-1)/6*100 (4.0->50, 5.5->75, 6.25->87.5), so the index's
# Poor/Fair/Good/Excellent line up with how the /7 mean was always banded.
QUALITY_INDEX_BANDS = [(0, 50, "Poor"), (50, 75, "Fair"), (75, 87.5, "Good"), (87.5, 100.001, "Excellent")]


def finite_number(value):
    """Normalize a numeric scalar; missing, malformed and infinite values are absent."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return number if np.isfinite(number) else None


def answer_quality(df):
    """Disjoint source-row counts, without mutating or dropping the source records."""
    values = pd.to_numeric(df["value"], errors="coerce")
    na = df["is_na"].eq(True).fillna(False)
    known = df["is_na"].eq(False).fillna(False)
    tops = df["item_id"].astype(object).map(
        {**{it: 5 for it in ["SQD0", *ARTA_HEADLINE_ITEMS]},
         **QUALITY_SCALE_MAX, "A": 7})
    valid = known & np.isfinite(values) & values.ge(1) & values.le(tops)
    return values, valid, {"valid": int(valid.sum()), "na": int(na.sum()),
                           "invalid": int((~na & ~valid).sum())}


def valid_answers(df):
    """Only finite, in-scale, explicitly rated answers enter score denominators."""
    values, valid, _ = answer_quality(df)
    result = df.loc[valid].copy()
    result["value"] = values.loc[valid].astype(float)
    return result


def band(value, table):
    """Return the band label for a value, or None if there is no value."""
    if finite_number(value) is None:
        return None
    for lo, hi, label in table:
        if lo <= value < hi:
            return label
    return None


def gap_label(g):
    g = round(g, 2)
    return "Exceeds" if g > 0 else ("Meets" if g == 0 else "Needs Improvement")


# =====================================================================
# THE TRIPLE -- no score is ever a bare number. It always travels with
# how many responses it stands on and what it is "out of".
# =====================================================================

@dataclass
class Metric:
    value: float | None          # full precision; rounding happens only when printed
    n: int                       # responses behind it
    denom: str                   # plain words: what it is "out of"
    flags: list = field(default_factory=list)

    def show(self, kind="mean"):
        if finite_number(self.value) is None:
            return f"(no data, n={self.n})"
        v = f"{self.value:.1f}%" if kind == "pct" else f"{self.value:.2f}"
        tail = f"  [{' ; '.join(self.flags)}]" if self.flags else ""
        return f"{v}  (n={self.n}, {self.denom}){tail}"


# =====================================================================
# TYPE 1 -- ARTA top-box %
# =====================================================================

def arta_topbox(df, items=ARTA_HEADLINE_ITEMS):
    """Headline ARTA score: share of Agree+Strongly-Agree among valid answers."""
    sub = df[df["item_id"].isin(items)]
    valid = valid_answers(sub)
    n = len(valid)                                   # valid ITEM-responses = the headline denominator
    if n == 0:
        return Metric(None, 0, "valid SQD answers", ["no data"])
    topbox = int((valid["value"] >= 4).sum())
    score = topbox / n * 100
    flags = []
    respondents = valid["response_id"].nunique()
    if respondents < N_MIN:
        flags.append("low n")
    if score >= CEILING_TOPBOX and respondents >= N_MIN:
        flags.append("non-discriminating - see verbatims")
    return Metric(score, n, "valid SQD answers (Agree+Strongly Agree)", flags)


def arta_item_detail(df, item):
    """Full distribution + score for one SQD item."""
    sub = df[df["item_id"] == item]
    valid = valid_answers(sub)
    n = len(valid)
    _, _, quality = answer_quality(sub)
    na = quality["na"]
    if n == 0:
        return {"item": item, "n": 0, "na": na, "invalid": quality["invalid"], "score": None}
    score = (valid["value"] >= 4).sum() / n * 100      # top-box %
    bottombox = (valid["value"] <= 2).sum() / n * 100
    dist = valid["value"].value_counts().reindex([5, 4, 3, 2, 1], fill_value=0)
    return {"item": item, "n": n, "na": na, "invalid": quality["invalid"], "score": score, "bottom_box": bottombox,
            "dist": {"SA": int(dist[5]), "A": int(dist[4]), "Neither": int(dist[3]),
                     "D": int(dist[2]), "SD": int(dist[1])}}


# =====================================================================
# TYPE 2 / 3 -- SERVQUAL (mean of means)
# =====================================================================

def item_stats(df, item):
    sub = valid_answers(df[df["item_id"] == item])
    vals = sub["value"].astype(float)
    n = len(vals)
    if n == 0:
        return None
    return {"item": item, "mean": float(vals.mean()),
            "sd": float(vals.std(ddof=1)) if n >= 2 else None, "n": n}


def dimension_mean(df, items):
    """Dimension = mean of its item means (only items that actually have answers).

    Vectorized: per-item means/counts come from a single groupby over the slice
    instead of one boolean-mask filter per item (the old item_stats loop). Same
    result (mean of the present items' means; n = total valid item-answers); much
    faster when called repeatedly at production volume.
    """
    flags = ["1-item, volatile"] if len(items) == 1 else []
    valid = valid_answers(df)
    if len(valid):
        sub = valid[valid["item_id"].isin(items)]
        agg = sub.groupby("item_id", observed=True)["value"].agg(["mean", "count"]) if len(sub) else None
    else:
        agg = None
    if agg is None or agg.empty:
        return Metric(None, 0, "item means", flags + ["no data"])
    means = agg["mean"].tolist()
    total_n = int(agg["count"].sum())
    present = len(means)
    return Metric(float(np.mean(means)), total_n, f"mean of {present} item-mean(s)", flags)


def overall_perception(df, dim_map):
    """Overall = mean of the dimension means (dimension-weighted, NOT item-weighted).

    Vectorized: the per-item means are computed with a single groupby instead of
    re-filtering df once per item (dimension_mean -> item_stats). Mathematically
    identical to the per-item version (a dimension is still the mean of its present
    item-means, and the overall is still the mean of the present dimension-means);
    just far faster when called thousands of times at production volume.
    """
    valid = valid_answers(df)
    valid = valid[valid["item_id"].isin({it for items in dim_map.values() for it in items})]
    respondents = valid["response_id"].nunique()
    item_mean = valid.groupby("item_id", observed=True)["value"].mean() if len(valid) else None
    dvals = []
    if item_mean is not None:
        idx = item_mean.index
        for items in dim_map.values():
            means = [float(item_mean[it]) for it in items if it in idx]
            if means:
                dvals.append(float(np.mean(means)))
    if not dvals:
        return Metric(None, 0, "dimension means", ["no data"])
    flags = ["low n"] if respondents < N_MIN else []
    return Metric(float(np.mean(dvals)), respondents, f"mean of {len(dvals)} dimension-means", flags)


def expectation_A(df):
    sub = valid_answers(df[df["item_id"] == "A"])
    n = len(sub)
    if n == 0:
        return Metric(None, 0, "expectation answers", ["no data"])
    return Metric(float(sub["value"].mean()), n, "expectation (A) answers")


def osq_C(df):
    sub = valid_answers(df[df["item_id"] == "C"])
    n = len(sub)
    if n == 0:
        return Metric(None, 0, "OSQ answers", ["no data"])
    return Metric(float(sub["value"].mean()), n, "overall-service-quality answers")


def quality_index(df):
    """The combined Quality Index (0-100) for a slice of Form-2/3 answers.

    Every satisfaction question counts equally as one question: the nine SERVQUAL
    perception items (B1-B9, 1-7) and the single OSQ overall-quality item (C, 1-4).
    Each answer is min-max rescaled to 0-100 — (v-1)/(max-1)*100, so the lowest
    possible answer = 0 and the highest = 100 on BOTH scales, letting the 1-7 and
    1-4 questions combine fairly. We take each respondent's mean across the
    questions they answered (equal weight per question; a respondent who skipped
    the OSQ simply scores on their B answers), then average across respondents.
    The expectation question (A) is excluded. Returns (index_0_100, n_respondents);
    (None, 0) when the slice has no scorable answer.
    """
    items = SERVQUAL_ITEMS + [OSQ_ITEM]
    sub = valid_answers(df[df["item_id"].isin(items)])
    if sub.empty:
        return None, 0
    tops = sub["item_id"].astype(object).map(QUALITY_SCALE_MAX)          # 7 for B*, 4 for C
    norm = (sub["value"] - 1) / (tops - 1) * 100.0        # min-max to 0-100
    per_resp = norm.groupby(sub["response_id"]).mean()    # equal weight per answered question
    if per_resp.empty:
        return None, 0
    return float(per_resp.mean()), int(per_resp.size)


# =====================================================================
# SCOPING -- pick a slice of answers (an org node, a period, a subgroup).
# Combining is just: slice, then run the calculator above.
# =====================================================================

def assign_periods(atoms):
    a = atoms.copy()
    ed = a["event_date"]
    # Period columns are a pure function of event_date, and event_date repeats
    # heavily — on the production data ~800 distinct dates back ~400K rows. So we
    # parse + format the DISTINCT dates once and map back, instead of running
    # pd.to_datetime + string-building over every row (~3x faster, verified
    # bit-identical to the old per-row version). The map approach also works
    # unchanged on the small incremental delta (its own, even smaller, date set).
    uniq = pd.Index(ed.unique())
    # errors="coerce": a single malformed event_date must not crash the WHOLE
    # reporting layer. Bad/blank dates become NaT -> their period columns stay
    # null, so the row is simply excluded from period-scoped views (and from the
    # period dropdown, which builds from non-null values) instead of taking down
    # every dashboard, report, and export. Explicit format skips pandas' per-value
    # inference — event_date is always 'YYYY-MM-DD' (a 10-char slice from the DB).
    d = pd.to_datetime(uniq, format="%Y-%m-%d", errors="coerce")
    ys = d.year.astype("string")            # <NA> for the NaT (malformed) dates
    q = d.quarter
    # 'month' (YYYY-MM) is a cheap slice of the already-'YYYY-MM-DD' string — far
    # cheaper than strftime — so the dashboard's monthly trends never re-parse.
    lut = pd.DataFrame({
        "year": ys,
        "quarter": ys + "-Q" + q.astype("string"),       # NA propagates from ys
        "semester": ys + "-H" + ((q + 1) // 2).astype("string"),
        "month": pd.Series(uniq, dtype="string").where(d.notna()).str.slice(0, 7).values,
    }, index=uniq)
    for c in ("year", "quarter", "semester", "month"):
        a[c] = ed.map(lut[c])
    return a


def scope(atoms, org_prefix=None, period_col=None, period=None,
          rp_internal=None, organizer_type=None, survey_type=None, form=None):
    df = atoms
    if survey_type is not None:
        df = df[df["survey_type"] == survey_type]      # never pool across survey types
    if form is not None:
        df = df[df["form"] == form]
    if org_prefix is not None:
        df = df[df["org_path"].astype("string").str.startswith(org_prefix, na=False)]
    if period is not None and period_col is not None:
        df = df[df[period_col] == period]
    if rp_internal is not None:
        df = df[df["rp_internal"] == rp_internal]
    if organizer_type is not None:
        df = df[df["organizer_type"] == organizer_type]
    return df


# =====================================================================
# PERIOD-OVER-PERIOD comparison + the guards
# =====================================================================

def pop_delta(metric_now, metric_prior, unit="points"):
    """current minus prior, full precision. Units stated, n shown on both sides."""
    flags = []
    if metric_now.value is None or metric_prior.value is None:
        return {"now": metric_now, "prior": metric_prior, "delta": None,
                "unit": unit, "flags": ["no data one side"]}
    delta = metric_now.value - metric_prior.value
    if metric_now.n < N_MIN or metric_prior.n < N_MIN:
        flags.append("low n: delta unreliable")
    return {"now": metric_now, "prior": metric_prior, "delta": delta, "unit": unit, "flags": flags}


def pop_with_like_for_like(atoms, scorer, org_prefix, period_col, p_now, p_prior, unit="points"):
    """
    Two deltas, side by side:
      raw          -> every unit that showed up in each period
      like-for-like-> only the units present in BOTH periods (so a change in the
                      MIX of units can't masquerade as a real change)
    """
    now = scope(atoms, org_prefix, period_col, p_now)
    prior = scope(atoms, org_prefix, period_col, p_prior)
    raw = pop_delta(scorer(now), scorer(prior), unit)

    units_now = set(now["rateable_unit"])
    units_prior = set(prior["rateable_unit"])
    both = units_now & units_prior
    nl = now[now["rateable_unit"].isin(both)]
    pl = prior[prior["rateable_unit"].isin(both)]
    lfl = pop_delta(scorer(nl), scorer(pl), unit)
    lfl["flags"] = lfl["flags"] + [f"like-for-like: {len(both)} shared unit(s)"]
    if units_now != units_prior:
        raw["flags"] = raw["flags"] + ["composition changed - compare to like-for-like"]
    return {"raw": raw, "like_for_like": lfl}


def fmt_delta(d):
    if d["delta"] is None:
        return f"n/a ({'; '.join(d['flags'])})"
    sign = "+" if d["delta"] >= 0 else ""
    u = "pp" if d["unit"] == "pp" else "pts"
    nowv = f"{d['now'].value:.1f}" if d["unit"] == "pp" else f"{d['now'].value:.2f}"
    prv = f"{d['prior'].value:.1f}" if d["unit"] == "pp" else f"{d['prior'].value:.2f}"
    tail = f"  [{'; '.join(d['flags'])}]" if d["flags"] else ""
    return f"{prv} -> {nowv}  ({sign}{d['delta']:.2f} {u}; n {d['prior'].n}->{d['now'].n}){tail}"
