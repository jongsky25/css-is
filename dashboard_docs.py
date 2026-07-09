"""
Rich per-format artifacts for the DASHBOARD visuals (parallel to report_docs.py,
which does the same for the official /reports). The standard (see the
download-output-standard): each format has a distinct job —

  * PDF  — a report-ready NARRATIVE: captioned figures + a warm plain-language
           description of each one, WPSAR-style (Summary -> figures -> a key
           table -> Methods & notes; figure captions below, sequential numbers).
  * PPTX — a visual STORYTELLING deck: one chart per slide with a plain-language
           insight, a hero number, and closing takeaways. No tables.

PNG/JPEG (the single combined figure) and CSV/XLSX (the data + Details sheet) are
still produced by dashboard_export; this module only adds the two narrative
artifacts. To stay visually identical to the official reports we REUSE their
low-level scaffolding (report_docs._pdf_* / _ppt_* / _box / _fig_block / charts
palette) and only add visual-specific charts + narrative here.

TRENDS is the pilot; the same shape extends to the other dashboard visuals.
"""
from __future__ import annotations
import io
import math
import re as _re
from xml.sax.saxutils import escape as _escape

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as _plt

from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.platypus import Paragraph, Spacer

import report_docs as rd
from report_docs import _C, _fig_png, _clean

# Distinct line colours for the by-area lines when there are no clear movers.
_LINE_COLORS = ["#2B6CB0", "#2F855A", "#B7791F", "#805AD5", "#0987A0", "#C53030",
                "#D53F8C", "#718096"]

METHODS_TRENDS = (
    "The headline is the share of respondents who rated the service at the top of the "
    "scale (top-box) each period, or the mean 1–7 rating where that view is shown. The "
    "shaded “usual range” is a statistical process-control band (centre line ± 3σ, with σ "
    "from the moving range); a point outside it — and meaningfully far from the centre — "
    "is flagged as standing out. The lighter ribbon is the 95% margin of error for each "
    "period’s proportion, sized by that period’s respondent count. Areas are the survey’s "
    "items/dimensions, each on the same measure. Where shown, the delivery-format split "
    "runs the same headline measure separately for online and face-to-face activities "
    "(formats below a minimum respondent count in the window are omitted), and the "
    "comment-tone line is the share of free-text comments classified as appreciation "
    "(vs. an area to improve) by the same wording rules used elsewhere, honouring manual "
    "re-tags.")


# ---------------------------------------------------------------------
# small adapters / helpers
# ---------------------------------------------------------------------

def _esc(s):
    return _escape("" if s is None else str(s))


def _meta(vmeta):
    """report_docs scaffolding wants a dict; the dashboard carries a VisualMeta."""
    return {"title": vmeta.title, "scope": vmeta.subtitle(),
            "generated": vmeta.generated_at, "source": vmeta.source,
            "place": vmeta.place, "period": vmeta.period}


def _total_n(payload):
    return sum(int(p.get("n") or 0) for p in (payload.get("series") or []))


def _subject(payload):
    return ("share who rated the service at the top of the scale (%)"
            if payload.get("pct") else "average rating (1–7)")


def _fmt_v(payload):
    return (lambda v: f"{v:.0f}%") if payload.get("pct") else (lambda v: f"{v:.1f}")


def _has_unhappy(payload):
    return bool(payload.get("pct")) and any(
        p.get("value") is not None for p in (payload.get("unhappy") or []))


def _thin(n, k=10):
    step = max(1, math.ceil(n / k))
    return [i for i in range(n) if i % step == 0 or i == n - 1]


# ---------------------------------------------------------------------
# charts — single-purpose, larger fonts than the on-screen combined image
# ---------------------------------------------------------------------

def _chart_headline(payload):
    series = payload.get("series") or []
    labels = [p["label"] for p in series]
    n = len(labels)
    xs = list(range(n))
    yv = [p["value"] for p in series]
    ymax = payload["ymax"]
    ylo = payload.get("ylo", 0)
    yhi = payload.get("yhi") or ymax
    fig, ax = _plt.subplots()
    ctl, conf = payload.get("control"), payload.get("conf")
    if conf and any(c is not None for c in conf):
        lo = [yv[i] - conf[i] if (yv[i] is not None and conf[i] is not None) else float("nan") for i in xs]
        hi = [yv[i] + conf[i] if (yv[i] is not None and conf[i] is not None) else float("nan") for i in xs]
        ax.fill_between(xs, lo, hi, color=_C["bar"], alpha=0.16, linewidth=0, label="Margin of error")
    if ctl:
        ax.axhspan(max(ylo, ctl["lcl"]), min(yhi, ctl["ucl"]), color="#1C2330", alpha=0.05,
                   label="Usual range")
        ax.axhline(ctl["cl"], color=_C["soft"], ls="--", lw=1, alpha=0.7)
    ax.plot(xs, yv, "-o", color="#2B6CB0", lw=2.6, ms=5, label="Overall", zorder=5)
    sig = [(i, yv[i]) for i in sorted(set((ctl or {}).get("signals") or []))
           if i < n and yv[i] is not None]
    if sig:
        ax.plot([i for i, _ in sig], [v for _, v in sig], "o", color=_C["bad"], ms=9,
                zorder=6, label="Stands out")
    fmt = _fmt_v(payload)
    for i in _thin(n):
        if yv[i] is not None:
            ax.annotate(fmt(yv[i]), (i, yv[i]), textcoords="offset points", xytext=(0, 9),
                        ha="center", fontsize=8, fontweight="bold")
    ax.set_ylim(ylo, yhi + (yhi - ylo) * 0.10)
    if payload.get("gridvals"):
        ax.set_yticks(payload["gridvals"])
    sh = _thin(n)
    ax.set_xticks(sh); ax.set_xticklabels([labels[i] for i in sh])
    ax.set_ylabel(payload.get("ylabel", "")); ax.set_xlabel(payload.get("xlabel", "Period"))
    ax.legend(loc="lower left", fontsize=8, frameon=False, ncol=4)
    _clean(ax)
    return _fig_png(fig, 8.6, 4.0)


def _chart_unhappy(payload):
    un = payload.get("unhappy") or []
    labels = [p["label"] for p in un]
    uv = [p.get("value") for p in un]
    fig, ax = _plt.subplots()
    ax.plot(range(len(uv)), [v if v is not None else float("nan") for v in uv],
            "-o", color="#DD6B20", lw=2, ms=4)
    top = max([v for v in uv if v is not None] or [0])
    ax.set_ylim(0, max(2.0, top * 1.35))
    sh = _thin(len(labels), 8)
    ax.set_xticks(sh); ax.set_xticklabels([labels[i] for i in sh])
    ax.set_ylabel("Share rating it low (%)"); ax.set_xlabel(payload.get("xlabel", "Period"))
    _clean(ax)
    return _fig_png(fig, 8.4, 3.4)


def _chart_byarea(payload):
    dims = payload.get("dims") or []
    roles = payload.get("roles") or {}
    labels = [p["label"] for p in (payload.get("series") or [])]
    fig, ax = _plt.subplots()
    role_color = {"up": _C["good"], "down": _C["mid"]}
    if roles:
        for dm in dims:
            if dm["name"] in roles:
                continue
            ax.plot(range(len(dm["points"])), [p["value"] for p in dm["points"]],
                    "-", color="#C2C8D2", lw=1.2, alpha=0.85, zorder=2)
        for dm in dims:
            if dm["name"] not in roles:
                continue
            ax.plot(range(len(dm["points"])), [p["value"] for p in dm["points"]],
                    "-", color=role_color.get(roles[dm["name"]], "#2B6CB0"), lw=2.6,
                    zorder=4, label=dm["name"])
    else:
        for idx, dm in enumerate(dims):
            ax.plot(range(len(dm["points"])), [p["value"] for p in dm["points"]],
                    "-", color=_LINE_COLORS[idx % len(_LINE_COLORS)], lw=1.7, alpha=0.9,
                    label=dm["name"])
    sh = _thin(len(labels), 8)
    if sh:
        ax.set_xticks(sh); ax.set_xticklabels([labels[i] for i in sh])
    ax.set_ylabel(payload.get("ylabel", "")); ax.set_xlabel(payload.get("xlabel", "Period"))
    if roles or (0 < len(dims) <= 8):
        ax.legend(loc="best", fontsize=7.5, frameon=False, ncol=2)
    _clean(ax)
    return _fig_png(fig, 8.6, 4.0)


# ---------------------------------------------------------------------
# narrative (warm plain-language)
# ---------------------------------------------------------------------

def _na_summary(payload):
    series = [p for p in (payload.get("series") or []) if p["value"] is not None]
    fmt = (lambda v: f"{v:.0f}%") if payload.get("pct") else (lambda v: f"{v:.1f} of 7")
    bits = []
    if series:
        bits.append(f"The most recent period sits at {fmt(series[-1]['value'])}.")
    cr = payload.get("control_read")
    if cr:
        bits.append(cr["headline"])
    dr = payload.get("driver")
    if dr:
        bits.append(f"Most of the latest movement traces to {dr['name']} "
                    f"({dr['from_s']}→{dr['to_s']}).")
    ur = payload.get("unhappy_read")
    if ur:
        bits.append(ur["text"])
    return " ".join(bits) or "Not enough data yet to read a trend."


def _na_headline(payload):
    base = ("This is the headline measure over time. The shaded “usual range” is the band "
            "of normal variation and the dashed line is the typical level; the lighter "
            "ribbon around the line is the margin of error for each period (wider where "
            "fewer people responded). A red dot marks a period that stands out beyond the "
            "usual range and is worth a closer look.")
    cr = payload.get("control_read")
    if cr:
        base += " " + cr["headline"] + (" " + cr.get("detail", "") if cr.get("detail") else "")
    return base


def _na_unhappy(payload):
    base = ("The flip side of a high score: the share of respondents who rated the service "
            "at the low end. A strong average can still hide a small group of unhappy "
            "clients, so we track it on its own.")
    ur = payload.get("unhappy_read")
    if ur:
        base += " " + ur["text"]
    return base


def _na_byarea(payload):
    mv = payload.get("movers") or {}
    if mv.get("improved") or mv.get("watch"):
        out = ["Each line is one area. The highlighted lines moved the most over the window "
               "shown; the rest are dimmed so the change stands out."]
        if mv.get("improved"):
            m = mv["improved"]
            out.append(f"Most improved: {m['name']} ({m['from_s']}→{m['to_s']}).")
        if mv.get("watch"):
            m = mv["watch"]
            out.append(f"Eased back the most: {m['name']} ({m['from_s']}→{m['to_s']}).")
        return " ".join(out)
    return ("Each line is one area. Over the window shown they move together with no single "
            "area breaking away — a sign of steady, consistent feedback across the board.")


# --- Phase D: segment split (modality) + verbatim-sentiment trend -------------

def _has_segment(payload):
    seg = payload.get("segment")
    return bool(seg and seg.get("series_raw"))


def _has_sentiment(payload):
    sent = payload.get("sentiment")
    return bool(sent and sent.get("series"))


def _chart_segment(payload):
    seg = payload.get("segment") or {}
    labels = [p["label"] for p in (payload.get("series") or [])]
    overall = [p.get("value") for p in (payload.get("series") or [])]
    fig, ax = _plt.subplots()
    ax.plot(range(len(overall)), [v if v is not None else float("nan") for v in overall],
            "-", color="#94A3B8", lw=2, alpha=0.6, label="Overall", zorder=2)
    for idx, dm in enumerate(seg.get("series_raw") or []):
        ax.plot(range(len(dm["points"])), [p["value"] for p in dm["points"]],
                "-o", color=_LINE_COLORS[idx % len(_LINE_COLORS)], lw=2.4, ms=3,
                label=dm["name"], zorder=4)
    sh = _thin(len(labels), 8)
    if sh:
        ax.set_xticks(sh); ax.set_xticklabels([labels[i] for i in sh])
    ax.set_ylabel(payload.get("ylabel", "")); ax.set_xlabel(payload.get("xlabel", "Period"))
    ax.legend(loc="best", fontsize=7.5, frameon=False)
    _clean(ax)
    return _fig_png(fig, 8.6, 3.6)


def _chart_sentiment(payload):
    sent = payload.get("sentiment") or {}
    s = sent.get("series") or []
    labels = [p["label"] for p in s]
    sv = [p.get("value") for p in s]
    fig, ax = _plt.subplots()
    ax.plot(range(len(sv)), [v if v is not None else float("nan") for v in sv],
            "-o", color=_C["good"], lw=2, ms=4)
    ax.set_ylim(0, 100)
    sh = _thin(len(labels), 8)
    if sh:
        ax.set_xticks(sh); ax.set_xticklabels([labels[i] for i in sh])
    ax.set_ylabel("Comments that read positive (%)"); ax.set_xlabel(payload.get("xlabel", "Period"))
    _clean(ax)
    return _fig_png(fig, 8.4, 3.4)


# Colours mirror the on-screen verbatims chart: appreciation green, areas-to-
# improve amber, mixed (good-but-bad) the accent blue.
_SENT_COLORS = {"Appreciation": _C["good"], "Areas to improve": _C["mid"],
                "Mixed (good-but-bad)": _C["bar"]}


def _chart_sentiment_breakdown(payload):
    """3-way tone over time: the share of comments that read as appreciation, an
    area to improve, or mixed — one line each, shares total 100% per period."""
    bd = payload.get("sentiment_breakdown") or {}
    raw = bd.get("series_raw") or []
    if not raw or not raw[0].get("points"):
        return None
    labels = [p["label"] for p in raw[0]["points"]]
    fig, ax = _plt.subplots()
    for s in raw:
        ax.plot(range(len(s["points"])),
                [p["value"] if p["value"] is not None else float("nan") for p in s["points"]],
                "-o", color=_SENT_COLORS.get(s["name"], _C["soft"]), lw=2.2, ms=3, label=s["name"])
    ax.set_ylim(0, 100)
    sh = _thin(len(labels), 8)
    if sh:
        ax.set_xticks(sh); ax.set_xticklabels([labels[i] for i in sh])
    ax.set_ylabel("Share of comments (%)"); ax.set_xlabel(bd.get("xlabel", "Period"))
    ax.legend(loc="best", fontsize=7.5, frameon=False)
    _clean(ax)
    return _fig_png(fig, 8.6, 3.6)


def _na_segment(payload):
    seg = payload.get("segment") or {}
    base = ("The headline split by how the activity ran. The grey line is the overall "
            "figure; each coloured line is one delivery format. Formats with too few "
            "responses in the window are left off so a thin slice can't read as a trend.")
    if seg.get("read"):
        base += " " + seg["read"]["text"]
    if seg.get("dropped"):
        base += f" Left off for low counts: {', '.join(seg['dropped'])}."
    return base


def _na_sentiment(payload):
    sent = payload.get("sentiment") or {}
    base = ("Beside the tone of how people RATE, this tracks the tone of what they WRITE: "
            "the share of free-text comments that read as appreciation rather than pointing "
            "to something to improve. It can catch a souring (or warming) mood the scores "
            "alone would miss.")
    if sent.get("read"):
        base += " " + sent["read"]["text"]
    return base


def _byarea_sub(payload):
    mv = payload.get("movers") or {}
    parts = []
    if mv.get("improved"):
        m = mv["improved"]; parts.append(f"▲ {m['name']} {m['from_s']}→{m['to_s']}")
    if mv.get("watch"):
        m = mv["watch"]; parts.append(f"▼ {m['name']} {m['from_s']}→{m['to_s']}")
    return "   ·   ".join(parts) or "All areas moving together — steady across the board"


def _headline_title(payload):
    cr = payload.get("control_read")
    if not cr:
        return "How the measure is moving"
    return {"Signal": "Some periods stand out",
            "Trend": "A steady run worth noting",
            "In control": "Holding steady and in control"}.get(cr["label"], cr["label"])


def _byarea_title(payload):
    mv = payload.get("movers") or {}
    if mv.get("improved") and not mv.get("watch"):
        return f"{mv['improved']['name']} is climbing"
    if mv.get("watch") and not mv.get("improved"):
        return f"{mv['watch']['name']} is easing back"
    if mv.get("improved") and mv.get("watch"):
        return "Movers worth watching"
    return "Every area moving together"


def _takeaways(payload):
    series = [p for p in (payload.get("series") or []) if p["value"] is not None]
    fmt = (lambda v: f"{v:.0f}%") if payload.get("pct") else (lambda v: f"{v:.1f}/7")
    pts = []
    if series:
        pts.append(f"Most recent period: {fmt(series[-1]['value'])}.")
    cr = payload.get("control_read")
    if cr:
        pts.append(cr["headline"])
    dr = payload.get("driver")
    if dr:
        pts.append(f"Latest movement driven by {dr['name']} ({dr['from_s']}→{dr['to_s']}).")
    ur = payload.get("unhappy_read")
    if ur and len(pts) < 4:
        pts.append(ur["text"])
    focus = None
    mv = payload.get("movers") or {}
    if mv.get("watch"):
        m = mv["watch"]
        focus = (f"{m['name']} eased back the most ({m['from_s']}→{m['to_s']}) — "
                 "worth understanding what changed.")
    return pts[:4], focus


# ---------------------------------------------------------------------
# a compact key table for the PDF (recent periods only, stays readable)
# ---------------------------------------------------------------------

def _trend_table(payload, st):
    series = payload.get("series") or []
    if not series:
        return None
    pct = payload.get("pct")
    fmt = (lambda v: "—" if v is None else (f"{v:.0f}%" if pct else f"{v:.1f}"))
    un = {p["label"]: p.get("value") for p in (payload.get("unhappy") or [])}
    has_un = _has_unhappy(payload)
    headers = ["Period", "Overall", "Respondents"] + (["Rated low"] if has_un else [])
    widths = ([4.6 * cm, 4.0 * cm, 4.0 * cm] + ([3.4 * cm] if has_un else [])
              if has_un else [5.6 * cm, 5.2 * cm, 5.2 * cm])
    rows = []
    for p in series[-12:]:
        row = [p["label"], fmt(p["value"]), f"{int(p.get('n') or 0):,}"]
        if has_un:
            row.append(fmt(un.get(p["label"])))
        rows.append(row)
    return rd._pdf_grid(headers, rows, widths, st, numeric_from=1)


# ---------------------------------------------------------------------
# the two artifacts
# ---------------------------------------------------------------------

def trends_pdf(payload, vmeta):
    st = rd._pdf_styles()
    meta = _meta(vmeta)
    f = rd._pdf_head(st, meta)
    series = payload.get("series") or []
    if not any(p.get("value") is not None for p in series):
        f.append(Paragraph("No data to show for this scope.", st["body"]))
        return rd._pdf_doc(meta, f)

    N = _total_n(payload)
    fign = [0]

    def fb(heading, png, subject):
        fign[0] += 1
        return rd._fig_block(heading, png, fign[0], subject, st, meta, N=N)

    f.append(rd._box("Summary", [Paragraph(_esc(_na_summary(payload)), st["boxbody"])], st))
    f.append(Spacer(1, 12))

    f.append(fb("How the overall measure is moving", _chart_headline(payload),
                "Overall " + _subject(payload) + " over time, with the usual range and margin of error"))
    f.append(Paragraph(_esc(_na_headline(payload)), st["body"]))

    if _has_unhappy(payload):
        f.append(fb("The flip side — who rated low", _chart_unhappy(payload),
                    "Share of respondents rating the service at the low end, over time"))
        f.append(Paragraph(_esc(_na_unhappy(payload)), st["body"]))

    if payload.get("dims"):
        f.append(fb("Area by area", _chart_byarea(payload),
                    "Each service area’s " + _subject(payload) + " over time"))
        f.append(Paragraph(_esc(_na_byarea(payload)), st["body"]))

    if _has_segment(payload):
        f.append(fb("By delivery format", _chart_segment(payload),
                    "Overall " + _subject(payload) + " split by online vs face-to-face, over time"))
        f.append(Paragraph(_esc(_na_segment(payload)), st["body"]))

    if _has_sentiment(payload):
        f.append(fb("What people wrote — tone over time", _chart_sentiment(payload),
                    "Share of free-text comments that read as appreciation, over time"))
        f.append(Paragraph(_esc(_na_sentiment(payload)), st["body"]))

    grid = _trend_table(payload, st)
    if grid is not None:
        f.append(rd._table_block(1, "Overall " + _subject(payload) + " by period (most recent)",
                                 grid, st, meta, N=N))
        f.append(Spacer(1, 10))

    f.append(rd._box("Methods & notes", [Paragraph(_esc(METHODS_TRENDS), st["note"])],
                     st, bg=colors.white))
    return rd._pdf_doc(meta, f)


def trends_pptx(payload, vmeta):
    prs = rd._ppt_new()
    meta = _meta(vmeta)
    rd._title_slide(prs, meta)
    series = [p for p in (payload.get("series") or []) if p["value"] is not None]
    if not series:
        rd._txt(rd._slide(prs), "No data to show for this scope.", 0.8, 3, 11.7, 1, size=20)
        return rd._ppt_save(prs)

    loc = ", ".join(x for x in (meta.get("place"), meta.get("period")) if x)
    N = _total_n(payload)
    fign = [0]

    def cap(subject):
        fign[0] += 1
        base = f"Figure {fign[0]}. {subject}"
        if loc:
            base += f", {loc}"
        return base + f" (N = {N:,})"

    pg = 1
    pct = payload.get("pct")
    latest = series[-1]["value"]
    big = f"{latest:.0f}%" if pct else f"{latest:.1f}/7"
    cr = payload.get("control_read")
    line = (cr["headline"] if cr else "Most recent period") + f"\n{N:,} responses in view"
    rd._hero(prs, meta, pg, big, line)
    pg += 1

    rd._chart_slide(prs, meta, pg, _headline_title(payload), _chart_headline(payload),
                    sub=(cr["headline"] if cr else "Movement over the periods shown"),
                    cap=cap("Overall " + _subject(payload) + " over time"))
    pg += 1

    if _has_unhappy(payload):
        ur = payload.get("unhappy_read")
        rd._chart_slide(prs, meta, pg, "The flip side — who rated low", _chart_unhappy(payload),
                        sub=(ur["text"] if ur else None),
                        cap=cap("Share rating the service low, over time"))
        pg += 1

    if payload.get("dims"):
        rd._chart_slide(prs, meta, pg, _byarea_title(payload), _chart_byarea(payload),
                        sub=_byarea_sub(payload), cap=cap("Each area over time"))
        pg += 1

    if _has_segment(payload):
        seg = payload.get("segment") or {}
        rd._chart_slide(prs, meta, pg, "By delivery format", _chart_segment(payload),
                        sub=(seg.get("read") or {}).get("text"),
                        cap=cap("Split by online vs face-to-face, over time"))
        pg += 1

    if _has_sentiment(payload):
        sent = payload.get("sentiment") or {}
        rd._chart_slide(prs, meta, pg, "What people wrote — tone over time",
                        _chart_sentiment(payload), sub=(sent.get("read") or {}).get("text"),
                        cap=cap("Share of comments that read positive, over time"))
        pg += 1

    rd._methods_slide(prs, meta, pg, METHODS_TRENDS,
                      f"Based on {N:,} responses" + (f" · {loc}" if loc else ""))
    pg += 1

    pts, focus = _takeaways(payload)
    rd._takeaways_slide(prs, meta, pg, pts, focus)
    return rd._ppt_save(prs)


# =====================================================================
# PULSE — the whole-page vital-signs snapshot (all three signs + their
# "things to know" + the three summary cards). Page-level, window-scoped.
# =====================================================================

METHODS_PULSE = (
    "Each vital sign reads one kind of feedback over the selected window. Walk-in "
    "(CO-CSM) uses the top-box share — the percent who Agree or Strongly Agree. Activities "
    "and resource persons use the mean perception rating on a 1–7 scale (activity scores "
    "exclude the two person-judgment items so the card reflects the event, not the speaker). "
    "The bars show the last four months. “Things to know” and the summary cards are aggregate "
    "reads — they never name a person or a specific activity.")


def _tone_color(tone):
    return {"good": _C["good"], "mid": _C["mid"], "bad": _C["bad"]}.get(tone, _C["bar"])


def _chart_pulse_micro(tile):
    micro = tile.get("micro") or []
    labels = [m["label"] for m in micro]
    vals = [m.get("value") for m in micro]
    ymax = tile["ymax"]
    color = _tone_color(tile.get("tone"))
    fig, ax = _plt.subplots()
    bars = ax.bar(range(len(vals)), [v if v is not None else 0 for v in vals],
                  color=color, width=0.6)
    ax.set_xticks(range(len(labels))); ax.set_xticklabels(labels)
    ax.set_ylim(0, ymax * 1.16)
    ax.set_ylabel("Positive responses (%)" if ymax == 100 else "Mean rating (1–7)")
    ax.set_xlabel("Recent months")
    fmt = (lambda v: f"{v:.0f}%") if ymax == 100 else (lambda v: f"{v:.1f}")
    for b, v in zip(bars, vals):
        if v is not None:
            ax.text(b.get_x() + b.get_width() / 2, v + ymax * 0.02, fmt(v),
                    ha="center", va="bottom", fontsize=9, color=_C["ink"])
    _clean(ax)
    return _fig_png(fig, 7.2, 3.5)


def _pulse_value(tile):
    """Clean 'headline + unit' string — avoids the double '%' when the headline
    already carries one (walk-in is '100%' with unit '% positive')."""
    h, u = tile["headline"], (tile.get("unit") or "").lstrip()
    if h.endswith("%") and u.startswith("%"):
        return (h + u[1:]).strip()
    return f"{h} {u}".strip()


def _pulse_headline_line(tile):
    head = f"Latest: {_pulse_value(tile)}"
    return head + (f" — {tile['band']}." if tile.get("band") else ".")


def pulse_pdf(payload, vmeta):
    st = rd._pdf_styles()
    meta = _meta(vmeta)
    f = rd._pdf_head(st, meta)
    tiles = payload.get("tiles") or []
    if not tiles:
        f.append(Paragraph("No feedback in this view yet.", st["body"]))
        return rd._pdf_doc(meta, f)

    summary = payload.get("summary") or {}
    if summary.get("overall"):
        f.append(rd._box("Summary", [Paragraph(_esc(summary["overall"]), st["boxbody"])], st))
        f.append(Spacer(1, 12))

    fign = [0]
    for t in tiles:
        fign[0] += 1
        unit_lab = "positive responses (%)" if t["ymax"] == 100 else "mean rating (1–7)"
        f.append(rd._fig_block(t["title"], _chart_pulse_micro(t), fign[0],
                               f"{t['title']} — recent months ({unit_lab})",
                               st, meta, N=t.get("respondents")))
        desc = _pulse_headline_line(t) + (" " + t["signal"] if t.get("signal") else "")
        f.append(Paragraph(_esc(desc), st["body"]))
        for ins in (t.get("insights") or []):
            f.append(Paragraph(f"<b>{_esc(ins['label'])}.</b> {_esc(ins['text'])}", st["note"]))
        f.append(Spacer(1, 8))

    for heading, key in (("What has been good", "good"), ("Worth looking at", "watch")):
        bullets = summary.get(key) or []
        if bullets:
            f.append(Paragraph(heading, st["h2"]))
            for s in bullets:
                f.append(Paragraph("•  " + _esc(s), st["body"]))

    f.append(rd._box("Methods & notes", [Paragraph(_esc(METHODS_PULSE), st["note"])],
                     st, bg=colors.white))
    return rd._pdf_doc(meta, f)


def pulse_pptx(payload, vmeta):
    prs = rd._ppt_new()
    meta = _meta(vmeta)
    rd._title_slide(prs, meta)
    tiles = payload.get("tiles") or []
    if not tiles:
        rd._txt(rd._slide(prs), "No feedback in this view yet.", 0.8, 3, 11.7, 1, size=20)
        return rd._ppt_save(prs)

    summary = payload.get("summary") or {}
    loc = ", ".join(x for x in (meta.get("place"), meta.get("period")) if x)
    total = payload.get("total") or 0
    fign = [0]

    def cap(subject, N):
        fign[0] += 1
        base = f"Figure {fign[0]}. {subject}"
        if loc:
            base += f", {loc}"
        return base + (f" (N = {N:,})" if N else "")

    pg = 1
    rd._hero(prs, meta, pg, f"{total:,}",
             f"responses in this view\n{meta.get('period', '')}")
    pg += 1

    for t in tiles:
        title = f"{t['title']}: {_pulse_value(t)}" + (f" · {t['band']}" if t.get("band") else "")
        rd._chart_slide(prs, meta, pg, title, _chart_pulse_micro(t),
                        sub=t.get("signal"),
                        cap=cap(f"{t['title']} — recent months", t.get("respondents")))
        pg += 1

    if summary.get("overall"):
        s = rd._slide(prs)
        rd._header(s, "Overall pulse")
        rd._txt(s, summary["overall"], 0.6, 1.7, 12.1, 4.2, size=18, color="334155")
        rd._footer(s, meta, pg)
        pg += 1

    rd._methods_slide(prs, meta, pg, METHODS_PULSE,
                      f"Based on {total:,} responses" + (f" · {loc}" if loc else ""))
    pg += 1

    rd._takeaways_slide(prs, meta, pg, (summary.get("good") or [])[:4],
                        (summary.get("watch") or [None])[0])
    return rd._ppt_save(prs)


# =====================================================================
# PERSON — one person's full performance report (role-aware: speaker vs
# walk-in server). Verbatim quotes are intentionally omitted (user choice);
# coaching + technical-assistance advice ARE included.
# =====================================================================

METHODS_PERSON = (
    "Scores are computed fresh from this person's ratings in the window shown. A speaker's "
    "score is the mean of per-respondent overall ratings across all nine attributes (1–7); a "
    "walk-in server's score is the top-box share (Agree + Strongly Agree). Peer ranks use the "
    "People-grid fair-adjusted scores within the section and the whole bureau; overall "
    "performance blends rating quality with engagement (the number of events delivered). "
    "Coaching is auto-generated guidance to build on, not a personnel evaluation. Verbatim "
    "comments are intentionally omitted from this file.")


def _strip_html(s):
    return _re.sub(r"<[^>]+>", "", s or "")


def _person_pct(payload):
    return payload.get("role") == "arta"


def _person_score(payload):
    card = payload.get("card") or {}
    if payload.get("role") == "rp" and card.get("rp"):
        return card["rp"]["shown"] + "/7", card["rp"].get("band")
    if card.get("arta"):
        return card["arta"]["shown"], card["arta"].get("band")
    return "—", None


def _ylabel_person(pct):
    return "Top-box positive (%)" if pct else "Mean rating (1–7)"


def _chart_person_trend(payload):
    trend = payload.get("trend") or []
    labels = [p["label"] for p in trend]
    vals = [p.get("value") for p in trend]
    pct = _person_pct(payload)
    ymax = payload.get("ymax", 7)
    fig, ax = _plt.subplots()
    ax.plot(range(len(vals)), [v if v is not None else float("nan") for v in vals],
            "-o", color=_C["bar"], lw=2.4, ms=5)
    ax.set_ylim(0, ymax * 1.12)
    ax.set_ylabel(_ylabel_person(pct)); ax.set_xlabel("Period")
    sh = _thin(len(labels), 10)
    if sh:
        ax.set_xticks(sh); ax.set_xticklabels([labels[i] for i in sh])
    fmt = (lambda v: f"{v:.0f}%") if pct else (lambda v: f"{v:.1f}")
    for i in sh:
        if vals[i] is not None:
            ax.annotate(fmt(vals[i]), (i, vals[i]), textcoords="offset points", xytext=(0, 8),
                        ha="center", fontsize=8, color=_C["ink"])
    _clean(ax)
    return _fig_png(fig, 8.2, 3.6)


def _chart_person_breakdown(payload):
    bd = payload.get("breakdown") or []
    bmax = payload.get("breakdown_ymax", 7)
    pct = bmax == 100
    items = bd[::-1]                       # strongest on top
    names = [d["name"] for d in items]
    vals = [d.get("value") or 0 for d in items]
    fig, ax = _plt.subplots()
    ax.barh(range(len(names)), vals, color=_C["bar"], height=0.62)
    ax.set_yticks(range(len(names))); ax.set_yticklabels(names)
    ax.set_xlim(0, bmax * 1.12)
    ax.set_xlabel(_ylabel_person(pct))
    fmt = (lambda v: f"{v:.0f}%") if pct else (lambda v: f"{v:.1f}")
    for y, v in enumerate(vals):
        ax.text(v + bmax * 0.01, y, fmt(v), va="center", fontsize=8.5, color=_C["soft"])
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(length=0); ax.set_axisbelow(True)
    ax.xaxis.grid(True, color=_C["grid"], linewidth=0.8)
    h = max(2.6, 0.5 * len(names) + 1.0)
    return _fig_png(fig, 8.0, h)


def _chart_person_yoy(payload):
    bars = (payload.get("yoy") or {}).get("bars") or []
    labels = [b["label"] for b in bars]
    vals = [b["value"] for b in bars]
    pct = _person_pct(payload)
    ymax = 100 if pct else 7
    fig, ax = _plt.subplots()
    bb = ax.bar(range(len(vals)), vals, color=_C["good"], width=0.55)
    ax.set_xticks(range(len(labels))); ax.set_xticklabels(labels)
    ax.set_ylim(0, ymax * 1.12)
    ax.set_ylabel(_ylabel_person(pct)); ax.set_xlabel("Year")
    for b, bar in zip(bars, bb):
        ax.text(bar.get_x() + bar.get_width() / 2, b["value"] + ymax * 0.02, b["shown"],
                ha="center", va="bottom", fontsize=9, color=_C["ink"])
    _clean(ax)
    return _fig_png(fig, 7.0, 3.4)


def _na_person_summary(payload):
    bits = []
    peers = payload.get("peers")
    if peers and peers.get("standing"):
        bits.append(peers["standing"])
    cmp = payload.get("cmp")
    if cmp:
        who = "speaker" if payload.get("role") == "rp" else "server"
        bits.append(f"This {who} is scoring {cmp['phrase']}.")
    card = payload.get("card") or {}
    conf = card.get("confidence") or {}
    if conf.get("label"):
        bits.append(f"Confidence: {conf['label'].lower()} — based on {card.get('ratings', 0):,} ratings.")
    cons = card.get("consistency") or {}
    if cons.get("phrase"):
        bits.append(cons["phrase"])
    return " ".join(bits) or "Performance summary."


def _person_peer_grid(peers, st):
    two = peers.get("section") is not None

    def rk(side, axis):
        d = peers.get(side)
        return f"#{d[axis]['rank']} of {d['n']}" if d else "—"

    headers = ["Axis"] + (["Section"] if two else []) + ["Whole bureau"]
    rows = []
    for axis, lab in (("overall", "Overall performance"), ("quality", "Rating quality"),
                      ("engagement", "Engagement (events)")):
        rows.append([lab] + ([rk("section", axis)] if two else []) + [rk("bureau", axis)])
    widths = [6 * cm, 5 * cm, 5 * cm] if two else [8 * cm, 8 * cm]
    return rd._pdf_grid(headers, rows, widths, st, numeric_from=1)


def person_pdf(payload, vmeta):
    st = rd._pdf_styles()
    meta = _meta(vmeta)
    f = rd._pdf_head(st, meta)
    if not (payload.get("trend") or payload.get("breakdown") or payload.get("card")):
        f.append(Paragraph("No ratings in this window.", st["body"]))
        return rd._pdf_doc(meta, f)

    N = vmeta.n
    f.append(rd._box("Summary", [Paragraph(_esc(_na_person_summary(payload)), st["boxbody"])], st))
    f.append(Spacer(1, 12))

    fign = [0]

    def fb(heading, png, subject):
        fign[0] += 1
        return rd._fig_block(heading, png, fign[0], subject, st, meta, N=N)

    yoy = payload.get("yoy") or {}
    if len(yoy.get("bars") or []) > 1:
        f.append(fb("Year on year", _chart_person_yoy(payload), "Score by year"))
        f.append(Paragraph(_esc(yoy.get("insight", "")), st["body"]))

    if payload.get("trend") and not payload.get("single"):
        f.append(fb("Scores over time", _chart_person_trend(payload), "Score over time"))

    if payload.get("breakdown"):
        subj = ("Strongest to weakest dimensions" if payload.get("role") == "rp"
                else "Walk-in experience, part by part")
        f.append(fb(payload.get("breakdown_title", "Breakdown"), _chart_person_breakdown(payload), subj))

    peers = payload.get("peers")
    if peers:
        f.append(Paragraph("How they compare", st["h2"]))
        if peers.get("standing"):
            f.append(Paragraph(_esc(peers["standing"]), st["body"]))
        grid = _person_peer_grid(peers, st)
        if grid is not None:
            f.append(rd._table_block(1, "Peer standing — rank within section and bureau",
                                     grid, st, meta, N=N))
            f.append(Spacer(1, 8))
        if peers.get("contribution"):
            f.append(Paragraph("<b>Contribution.</b> " + _esc(_strip_html(peers["contribution"])),
                               st["body"]))

    coach = payload.get("coach") or {}
    if coach.get("praise") or coach.get("motivation"):
        f.append(Paragraph("Coaching — what's going well", st["h2"]))
        for s in (coach.get("praise") or []):
            f.append(Paragraph("•  " + _esc(s), st["body"]))
        if coach.get("motivation"):
            f.append(Paragraph("<i>" + _esc(coach["motivation"]) + "</i>", st["body"]))

    ta = payload.get("ta") or {}
    if ta.get("focus"):
        fo = ta["focus"]
        f.append(Paragraph("Strengthen technical assistance", st["h2"]))
        head = f"Biggest opportunity: {fo['area']}" + ("" if ta.get("even") else f" ({fo['score']} of 7)")
        f.append(Paragraph("<b>" + _esc(head) + "</b>", st["body"]))
        diag = (fo.get("diagnosis", "") + (" " + fo["context"] if fo.get("context") else "")).strip()
        if diag:
            f.append(Paragraph(_esc(diag), st["body"]))
        for a in (fo.get("actions") or []):
            f.append(Paragraph("→  " + _esc(a), st["note"]))
        if ta.get("secondary"):
            se = ta["secondary"]
            f.append(Paragraph(_esc(f"Also worth a look — {se['area']} ({se['score']} of 7):"), st["body"]))
            for a in (se.get("actions") or [])[:2]:
                f.append(Paragraph("→  " + _esc(a), st["note"]))
        if ta.get("keep"):
            f.append(Paragraph(_esc(ta["keep"]), st["body"]))

    f.append(rd._box("Methods & notes", [Paragraph(_esc(METHODS_PERSON), st["note"])],
                     st, bg=colors.white))
    return rd._pdf_doc(meta, f)


def person_pptx(payload, vmeta):
    prs = rd._ppt_new()
    meta = _meta(vmeta)
    rd._title_slide(prs, meta)
    if not payload.get("card"):
        rd._txt(rd._slide(prs), "No ratings in this window.", 0.8, 3, 11.7, 1, size=20)
        return rd._ppt_save(prs)

    loc = ", ".join(x for x in (meta.get("place"), meta.get("period")) if x)
    N = vmeta.n
    fign = [0]

    def cap(subject):
        fign[0] += 1
        base = f"Figure {fign[0]}. {subject}"
        if loc:
            base += f", {loc}"
        return base + (f" (N = {N:,})" if N else "")

    pg = 1
    score, band = _person_score(payload)
    card = payload.get("card") or {}
    line = (f"{band} · " if band else "") + f"{card.get('ratings', 0):,} ratings"
    rd._hero(prs, meta, pg, score, "Performance score\n" + line)
    pg += 1

    if payload.get("trend") and not payload.get("single"):
        rd._chart_slide(prs, meta, pg, "Scores over time", _chart_person_trend(payload),
                        sub=(payload.get("coach") or {}).get("trend_read"),
                        cap=cap("Score over time"))
        pg += 1

    if payload.get("breakdown"):
        rd._chart_slide(prs, meta, pg, "Strengths to build on", _chart_person_breakdown(payload),
                        cap=cap(payload.get("breakdown_title", "Breakdown")))
        pg += 1

    yoy = payload.get("yoy") or {}
    if len(yoy.get("bars") or []) > 1:
        rd._chart_slide(prs, meta, pg, "Year on year", _chart_person_yoy(payload),
                        sub=yoy.get("insight"), cap=cap("Score by year"))
        pg += 1

    peers = payload.get("peers")
    b = (peers or {}).get("bureau")
    if b:
        rd._stats_slide(prs, meta, pg, "How they rank in the bureau", [
            ("Overall", f"#{b['overall']['rank']} of {b['n']}"),
            ("Quality", f"#{b['quality']['rank']}"),
            ("Engagement", f"#{b['engagement']['rank']}"),
        ])
        pg += 1

    rd._methods_slide(prs, meta, pg, METHODS_PERSON,
                      f"Based on {N:,} ratings" + (f" · {loc}" if loc else ""))
    pg += 1

    focus = None
    ta = payload.get("ta") or {}
    if ta.get("focus"):
        fo = ta["focus"]
        acts = fo.get("actions") or []
        focus = f"Strengthen {fo['area']}" + (f": {acts[0]}" if acts else ".")
    rd._takeaways_slide(prs, meta, pg, ((payload.get("coach") or {}).get("praise") or [])[:4], focus)
    return rd._ppt_save(prs)


# =====================================================================
# PARTICIPATION — the whole-page volume/coverage story (page-level): responses
# over time per type (SPC reads), event coverage with a confidence ribbon,
# responses-per-event, where feedback comes from (movers), and blind spots.
# =====================================================================

METHODS_PARTICIPATION = (
    "Volume is the count of distinct responses per period. Event coverage is the share of "
    "events that ran in a period and drew any feedback — a true proportion, so it carries a "
    "95% confidence ribbon (few events → a wider band) and an SPC control band that tells a "
    "real surge or drop apart from normal wobble. Responses-per-event normalises for how many "
    "events ran. “Where feedback comes from” counts distinct responses per org unit. Blind "
    "spots list units/staff/events with little or no feedback — by count, never by name.")

_VOL_COLORS = ["#2B6CB0", "#2F855A", "#B7791F"]


def _chart_part_volume(payload):
    vols = payload.get("volumes") or []
    fig, ax = _plt.subplots()
    longest = []
    for i, v in enumerate(vols):
        s = v.get("series") or []
        if not s:
            continue
        if len(s) > len(longest):
            longest = s
        ax.plot(range(len(s)), [p["value"] for p in s], "-o", lw=2.2, ms=4,
                color=_VOL_COLORS[i % len(_VOL_COLORS)], label=v["title"])
    ax.set_ylabel("Responses"); ax.set_xlabel(payload.get("xlabel", "Period"))
    sh = _thin(len(longest), 8)
    if sh:
        ax.set_xticks(sh); ax.set_xticklabels([longest[i]["label"] for i in sh])
    ax.legend(fontsize=8, frameon=False, ncol=3, loc="upper left")
    _clean(ax)
    return _fig_png(fig, 8.4, 3.6)


def _chart_part_coverage(payload):
    cs = payload.get("cov_series") or []
    labels = [p["label"] for p in cs]
    yv = [p["value"] for p in cs]
    n = len(cs)
    xs = list(range(n))
    ctl, conf = payload.get("cov_control"), payload.get("cov_conf")
    fig, ax = _plt.subplots()
    if conf and any(c is not None for c in conf):
        lo = [yv[i] - conf[i] if (yv[i] is not None and conf[i] is not None) else float("nan") for i in xs]
        hi = [yv[i] + conf[i] if (yv[i] is not None and conf[i] is not None) else float("nan") for i in xs]
        ax.fill_between(xs, lo, hi, color="#2F855A", alpha=0.15, linewidth=0, label="Margin of error")
    if ctl:
        ax.axhspan(max(0, ctl["lcl"]), min(105, ctl["ucl"]), color="#1C2330", alpha=0.05,
                   label="Usual range")
        ax.axhline(ctl["cl"], color=_C["soft"], ls="--", lw=1, alpha=0.7)
    ax.plot(xs, yv, "-o", color="#2F855A", lw=2.4, ms=5, label="Coverage", zorder=5)
    sig = [(i, yv[i]) for i in sorted(set((ctl or {}).get("signals") or [])) if i < n and yv[i] is not None]
    if sig:
        ax.plot([i for i, _ in sig], [v for _, v in sig], "o", color=_C["bad"], ms=8, zorder=6,
                label="Stands out")
    ax.set_ylim(0, 105)
    ax.set_ylabel("Events with feedback (%)"); ax.set_xlabel(payload.get("xlabel", "Period"))
    sh = _thin(n, 8)
    if sh:
        ax.set_xticks(sh); ax.set_xticklabels([labels[i] for i in sh])
    ax.legend(fontsize=7.5, frameon=False, ncol=4, loc="lower left")
    _clean(ax)
    return _fig_png(fig, 8.4, 3.6)


def _chart_part_engagement(payload):
    es = payload.get("eng_series") or []
    labels = [p["label"] for p in es]
    vals = [p["value"] for p in es]
    fig, ax = _plt.subplots()
    ax.plot(range(len(vals)), vals, "-o", color="#805AD5", lw=2.2, ms=4)
    ax.set_ylabel("Responses per event"); ax.set_xlabel(payload.get("xlabel", "Period"))
    sh = _thin(len(labels), 8)
    if sh:
        ax.set_xticks(sh); ax.set_xticklabels([labels[i] for i in sh])
    _clean(ax)
    return _fig_png(fig, 8.0, 3.2)


def _chart_part_byunit(payload):
    bu = [u for u in (payload.get("by_unit") or []) if u.get("count")]
    bu = sorted(bu, key=lambda u: u["count"])[-12:]        # top units, ascending for barh
    names = [u["label"] for u in bu]
    vals = [u["count"] for u in bu]
    role_color = {"up": _C["good"], "down": _C["mid"]}
    colors = [role_color.get(u.get("role"), _C["bar"]) for u in bu]
    fig, ax = _plt.subplots()
    ax.barh(range(len(names)), vals, color=colors, height=0.66)
    ax.set_yticks(range(len(names))); ax.set_yticklabels(names)
    ax.set_xlabel("Distinct responses")
    top = max(vals + [1])
    for y, u in enumerate(bu):
        tag = {"up": "  ▲", "down": "  ▼"}.get(u.get("role"), "")
        ax.text(u["count"] + top * 0.01, y, f"{u['count']:,}{tag}", va="center", fontsize=8.5,
                color=_C["soft"])
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(length=0); ax.set_axisbelow(True)
    ax.xaxis.grid(True, color=_C["grid"], linewidth=0.8)
    ax.set_xlim(0, top * 1.16)
    h = max(2.6, 0.5 * len(names) + 1.0)
    return _fig_png(fig, 8.2, h)


def _part_total(payload):
    return sum(int(v.get("total") or 0) for v in (payload.get("volumes") or []))


def participation_pdf(payload, vmeta):
    st = rd._pdf_styles()
    meta = _meta(vmeta)
    f = rd._pdf_head(st, meta)
    if not payload.get("volumes"):
        f.append(Paragraph("No responses in this scope.", st["body"]))
        return rd._pdf_doc(meta, f)

    read = payload.get("read") or {}
    N = vmeta.n
    summary = " ".join(x for x in (read.get("lead"), read.get("coverage"), read.get("driver")) if x)
    if summary:
        f.append(rd._box("Summary", [Paragraph(_esc(summary), st["boxbody"])], st))
        f.append(Spacer(1, 12))

    fign = [0]

    def fb(heading, png, subject):
        fign[0] += 1
        return rd._fig_block(heading, png, fign[0], subject, st, meta, N=N)

    f.append(fb("Responses over time", _chart_part_volume(payload),
                "Distinct responses per period, by feedback type"))
    # per-type SPC reads as the description
    reads = [f"{v['title']}: {v['control_read']['headline']}" for v in payload["volumes"]
             if v.get("control_read")]
    if reads:
        f.append(Paragraph(_esc("  ".join(reads)), st["body"]))

    if payload.get("cov_series"):
        f.append(fb("Event coverage over time", _chart_part_coverage(payload),
                    "Share of events that drew any feedback, with the usual range and margin of error"))
        cr = payload.get("cov_read")
        cov = payload.get("coverage") or {}
        desc = (f"{cov.get('events_with', 0)} of {cov.get('events_total', 0)} events and "
                f"{cov.get('staff_rated', 0)} of {cov.get('staff_total', 0)} staff have feedback on record. ")
        if cr:
            desc += cr.get("headline", "")
        f.append(Paragraph(_esc(desc), st["body"]))

    if payload.get("eng_series"):
        f.append(fb("Responses per event", _chart_part_engagement(payload),
                    "Average responses per event that ran"))

    if [u for u in (payload.get("by_unit") or []) if u.get("count")]:
        f.append(fb("Where feedback comes from", _chart_part_byunit(payload),
                    "Distinct responses by org unit (movers highlighted)"))
        if read.get("driver"):
            f.append(Paragraph(_esc(read["driver"]), st["body"]))

    blind = payload.get("blind") or []
    if blind:
        f.append(Paragraph("Blind spots — where feedback is thin or missing", st["h2"]))
        for b in blind:
            f.append(Paragraph("•  " + _esc(b["text"]), st["body"]))

    f.append(rd._box("Methods & notes", [Paragraph(_esc(METHODS_PARTICIPATION), st["note"])],
                     st, bg=colors.white))
    return rd._pdf_doc(meta, f)


def participation_pptx(payload, vmeta):
    prs = rd._ppt_new()
    meta = _meta(vmeta)
    rd._title_slide(prs, meta)
    if not payload.get("volumes"):
        rd._txt(rd._slide(prs), "No responses in this scope.", 0.8, 3, 11.7, 1, size=20)
        return rd._ppt_save(prs)

    read = payload.get("read") or {}
    loc = ", ".join(x for x in (meta.get("place"), meta.get("period")) if x)
    N = vmeta.n
    fign = [0]

    def cap(subject):
        fign[0] += 1
        base = f"Figure {fign[0]}. {subject}"
        if loc:
            base += f", {loc}"
        return base + (f" (N = {N:,})" if N else "")

    pg = 1
    rd._hero(prs, meta, pg, f"{N:,}", "responses on record\n" + (read.get("coverage") or ""))
    pg += 1

    rd._chart_slide(prs, meta, pg, "Responses over time", _chart_part_volume(payload),
                    sub=read.get("lead"), cap=cap("Distinct responses per period, by type"))
    pg += 1

    if payload.get("cov_series"):
        rd._chart_slide(prs, meta, pg, "Event coverage", _chart_part_coverage(payload),
                        sub=(payload.get("cov_read") or {}).get("headline"),
                        cap=cap("Share of events that drew feedback"))
        pg += 1

    if [u for u in (payload.get("by_unit") or []) if u.get("count")]:
        rd._chart_slide(prs, meta, pg, "Where feedback comes from", _chart_part_byunit(payload),
                        sub=read.get("driver"), cap=cap("Distinct responses by org unit"))
        pg += 1

    blind = payload.get("blind") or []
    if blind:
        rd._quotes_slide(prs, meta, pg, "Blind spots",
                         [(b["text"], _C["mid"].lstrip("#"), "Gap") for b in blind[:4]])
        pg += 1

    rd._methods_slide(prs, meta, pg, METHODS_PARTICIPATION,
                      f"Based on {N:,} responses" + (f" · {loc}" if loc else ""))
    pg += 1

    pts = [x for x in (read.get("lead"), read.get("coverage"), read.get("driver")) if x][:4]
    focus = blind[0]["text"] if blind else None
    rd._takeaways_slide(prs, meta, pg, pts, focus)
    return rd._ppt_save(prs)


# =====================================================================
# EVENT — one activity's SERVQUAL scorecard, in the OFFICIAL report style
# (user choice). Reuses the report_docs SERVQUAL charts + scaffolding so it
# matches the /reports Type-2 look, with the activity-specific extras (the
# "what happened" read, per-dimension vs-section deltas, the section benchmark,
# speakers). NO verbatim quotes.
# =====================================================================

def _vshort(v):
    """report_docs._na_sq_dims counts 'Exceeds' — normalise the activity's longer
    verdict ('Exceeds Expectation') so the narrative's exceeded-count is right."""
    return {"Exceeds Expectation": "Exceeds", "Meets Expectation": "Meets",
            "Below Expectation": "Below"}.get(v, v)


def _event_sq(rep):
    """Shape activity_servqual output into the `sq` dict report_docs' SERVQUAL
    charts/narrative consume — so the activity report renders in the official look."""
    return {
        "has_data": True, "respondents": rep["respondents"],
        "dimensions": [{"dim": d["label"], "value": d["value"], "shown": d["shown"],
                        "gap_shown": d.get("gap_shown"), "verdict": _vshort(d.get("verdict"))}
                       for d in rep["dims"]],
        "overall": {"shown": rep["average_shown"], "value": rep["average"]},
        "expectation": {"shown": rep["expectation_shown"], "value": rep["expectation"]},
        # Short verdict for the narrative ("meets what they expected"), matching the
        # official report's phrasing; the long form stays in the tables.
        "gap": {"shown": rep["servqual_shown"], "label": _vshort(rep.get("servqual_verdict"))},
        "osq": {"shown": rep["osq_shown"], "band": rep.get("osq_grade")},
        "summary": {"total": rep["total_shown"], "average": rep["average_shown"],
                    "expectation": rep["expectation_shown"], "servqual": rep["servqual_shown"],
                    "servqual_label": rep.get("servqual_verdict"), "osq": rep["osq_shown"],
                    "osq_band": rep.get("osq_grade")},
    }


def _bench_word(delta):
    return "above" if delta >= 0.10 else "below" if delta <= -0.10 else "about level with"


def event_pdf(payload, vmeta):
    st = rd._pdf_styles()
    meta = _meta(vmeta)
    f = rd._pdf_head(st, meta)
    rep = payload.get("report")
    if not rep:
        f.append(Paragraph("No Form-2 (event review) scores for this activity yet.", st["body"]))
        return rd._pdf_doc(meta, f)

    sq = _event_sq(rep)
    N = rep["respondents"]
    summ = [x for x in (payload.get("journey_read"), rd._na_sq_summary(sq), rd._na_sq_osq(sq)) if x]
    f.append(rd._box("Summary", [Paragraph(_esc(" ".join(summ)), st["boxbody"])], st))
    f.append(Spacer(1, 12))

    fign = [0]
    tabn = [0]

    f.append(rd._fig_block("How each area scored", rd._chart_dims(sq), 1,
                           "Service-quality dimension scores versus expectation", st, meta, N=N))
    fign[0] = 1
    f.append(Paragraph(_esc(rd._na_sq_dims(sq)), st["body"]))

    # dimension table — score, SERVQUAL gap, (vs section), verdict
    has_sec = any("sec_delta_shown" in d for d in rep["dims"])
    headers = ["Dimension", "Score /7", "SERVQUAL gap"] + (["vs section"] if has_sec else []) + ["Interpretation"]
    rows = []
    for d in rep["dims"]:
        row = [d["label"], d["shown"], d.get("gap_shown", "—")]
        if has_sec:
            row.append(d.get("sec_delta_shown", "—"))
        row.append(d.get("verdict") or "—")
        rows.append(row)
    widths = ([4.6 * cm, 2.3 * cm, 2.7 * cm, 2.4 * cm, 4.0 * cm] if has_sec
              else [5.4 * cm, 2.6 * cm, 3.0 * cm, 5.0 * cm])
    tabn[0] += 1
    f.append(rd._table_block(tabn[0], "Service quality, dimension by dimension",
                             rd._pdf_grid(headers, rows, widths, st, numeric_from=1), st, meta, N=N))
    f.append(Spacer(1, 10))

    f.append(rd._fig_block("Expectation versus experience", rd._chart_gap(sq), 2,
                           "Expectation versus experience", st, meta, N=N, width=9.0 * cm))
    fign[0] = 2
    servq = rep["servqual_shown"] + (f" ({rep['servqual_verdict']})" if rep.get("servqual_verdict") else "")
    osq = rep["osq_shown"] + (f" ({rep['osq_grade']})" if rep.get("osq_grade") else "")
    tabn[0] += 1
    f.append(rd._table_block(tabn[0], "SERVQUAL summary", rd._pdf_grid(["Metric", "Value"], [
        ["Total (sum of dimension means)", rep["total_shown"]],
        ["Average (mean of dimension means)", rep["average_shown"]],
        ["Expectation", rep["expectation_shown"]],
        ["SERVQUAL (Average − Expectation)", servq],
        ["Overall Service Quality (item C, 1–4)", osq],
    ], [10.0 * cm, 6.0 * cm], st), st, meta, N=N))
    f.append(Spacer(1, 10))

    bench = payload.get("bench")
    if bench:
        o = bench["overall"]
        f.append(Paragraph("How this compares", st["h2"]))
        txt = (f"Against the {bench['peers']} other activit{'y' if bench['peers'] == 1 else 'ies'} "
               f"{bench['label']} ran in {bench['year']} ({bench['respondents']:,} respondents in all), "
               f"this activity averaged {rep['average_shown']}/7 versus {o['shown']}/7 — "
               f"{o.get('delta_shown', '')}, {_bench_word(o.get('delta', 0))} the section's average. "
               f"Satisfaction here was {rep.get('osq_grade') or '—'} versus "
               f"{bench['osq'].get('band') or '—'} across the rest.")
        f.append(Paragraph(_esc(txt), st["body"]))

    demo = payload.get("demo") or {}
    parts = []
    if demo.get("mf_ratio"):
        parts.append(f"Male:Female {demo['mf_ratio']}")
    if demo.get("affil_ratio"):
        parts.append(f"DOH:Non-DOH {demo['affil_ratio']}")
    if parts:
        f.append(Paragraph("Who responded", st["h2"]))
        f.append(Paragraph(_esc("; ".join(parts) + (" (manually entered)" if demo.get("manual") else "") + "."),
                           st["body"]))

    c = payload.get("comments") or {}
    if c.get("items"):
        f.append(Paragraph(f"Respondent comments ({c.get('total', 0):,})", st["h2"]))
        f.append(Paragraph(_esc(
            "Every written comment is listed below. Identical answers are shown "
            "once with a ×N repeat count."), st["body"]))
        for q in c["items"]:
            f.append(Paragraph("“" + _esc(rd._comment_text(q)) + "”", st["body"]))
        more = c.get("unique", len(c["items"])) - len(c["items"])
        if more > 0:
            f.append(Paragraph(_esc(f"…and {more:,} more unique comments"), st["note"]))

    f.append(rd._box("Methods & notes", [Paragraph(_esc(rd.METHODS_SQ), st["note"])], st, bg=colors.white))
    return rd._pdf_doc(meta, f)


def event_pptx(payload, vmeta):
    prs = rd._ppt_new()
    meta = _meta(vmeta)
    rd._title_slide(prs, meta)
    rep = payload.get("report")
    if not rep:
        rd._txt(rd._slide(prs), "No Form-2 (event review) scores for this activity yet.",
                0.8, 3, 11.7, 1, size=20)
        return rd._ppt_save(prs)

    sq = _event_sq(rep)
    loc = ", ".join(x for x in (meta.get("place"), meta.get("period")) if x)
    N = rep["respondents"]
    fign = [0]

    def cap(subject):
        fign[0] += 1
        base = f"Figure {fign[0]}. {subject}"
        if loc:
            base += f", {loc}"
        return base + f" (N = {N:,})"

    pg = 1
    vtxt = f" · {rep['servqual_verdict']}" if rep.get("servqual_verdict") else ""
    rd._hero(prs, meta, pg, rep["average_shown"] + "/7",
             "Average perception" + vtxt + f"\n{N:,} respondents")
    pg += 1

    rd._chart_slide(prs, meta, pg, "How each area scored", rd._chart_dims(sq),
                    sub=rd._na_sq_dims(sq), cap=cap("Dimension scores versus expectation"))
    pg += 1

    rd._chart_slide(prs, meta, pg, "Expectation versus experience", rd._chart_gap(sq),
                    sub=rd._na_sq_osq(sq), cap=cap("Expectation versus experience"))
    pg += 1

    bench = payload.get("bench")
    if bench:
        o = bench["overall"]
        rd._stats_slide(prs, meta, pg, "How this compares", [
            ("This activity", rep["average_shown"] + "/7"),
            (f"{bench['short']} · {bench['year']}", o["shown"] + "/7"),
            ("Difference", o.get("delta_shown", "—")),
        ])
        pg += 1

    rd._methods_slide(prs, meta, pg, rd.METHODS_SQ,
                      f"Based on {N:,} responses" + (f" · {loc}" if loc else ""))
    pg += 1

    c = payload.get("comments") or {}
    if c.get("items"):
        # SERVQUAL comments aren't typed positive/negative — one neutral column,
        # most-repeated first, with ×N on any collapsed repeat.
        items = [(rd._comment_text(q), rd._SOFTP, "Comment") for q in c["items"][:4]]
        rd._quotes_slide(prs, meta, pg, "In their words", items)
        pg += 1

    dims = [d for d in rep["dims"] if d.get("value") is not None]
    pts = [f"Overall service quality: {rep['osq_shown']}/4" + (f" ({rep['osq_grade']})" if rep.get("osq_grade") else "")]
    if dims:
        hi = max(dims, key=lambda d: d["value"])
        pts.append(f"Strongest area: {hi['label']} ({hi['shown']}/7).")
    pts.append(f"SERVQUAL {rep['servqual_shown']}" + (f" — {rep['servqual_verdict']}." if rep.get("servqual_verdict") else "."))
    focus = None
    if dims:
        lo = min(dims, key=lambda d: d["value"])
        focus = f"{lo['label']} ({lo['shown']}/7) — the area with the most headroom."
    rd._takeaways_slide(prs, meta, pg, pts[:4], focus)
    return rd._ppt_save(prs)


# =====================================================================
# TEAM — one org unit's activity report (the unit analog of the Person report:
# collective coach, TA advice, standing vs siblings, year-on-year, breakdown).
# Reuses the Person chart helpers (same payload keys). NO verbatim quotes.
# Plus TEAMS_INDEX — the unit-comparison roster.
# =====================================================================

METHODS_TEAM = (
    "Scores are the unit's activity (Form-2) ratings — the mean of per-respondent overall ratings "
    "across the nine attributes (1–7); the breakdown uses the event-about dimensions. Standing ranks "
    "the unit against its sibling units (sections vs sections, divisions vs divisions) on rating "
    "quality and engagement (activities run). Coaching is auto-generated guidance to build on, not a "
    "performance evaluation. Verbatim comments are intentionally omitted from this file.")


def _na_team_summary(payload):
    bits = []
    standing = payload.get("standing")
    if standing and standing.get("standing"):
        bits.append(standing["standing"])
    profile = payload.get("profile")
    if profile and profile.get("story"):
        bits.append(_strip_html(profile["story"]))
    cons = (payload.get("card") or {}).get("consistency") or {}
    if cons.get("phrase"):
        bits.append(cons["phrase"])
    return " ".join(bits) or "Activity performance summary."


def _team_standing_grid(standing, st):
    grp = (standing or {}).get("group") or {}
    if not grp:
        return None
    n = grp["n"]
    rows = [["Overall performance", f"#{grp['overall']['rank']} of {n}"],
            ["Rating quality", f"#{grp['quality']['rank']} of {n}"],
            ["Engagement (activities)", f"#{grp['engagement']['rank']} of {n}"]]
    return rd._pdf_grid(["Axis", "Rank"], rows, [9 * cm, 7 * cm], st, numeric_from=1)


def _render_ta_pdf(f, ta, st):
    """The 'Strengthen technical assistance' block — shared by person & team PDFs."""
    fo = ta["focus"]
    f.append(Paragraph("Strengthen technical assistance", st["h2"]))
    head = f"Biggest opportunity: {fo['area']}" + ("" if ta.get("even") else f" ({fo['score']} of 7)")
    f.append(Paragraph("<b>" + _esc(head) + "</b>", st["body"]))
    diag = (fo.get("diagnosis", "") + (" " + fo["context"] if fo.get("context") else "")).strip()
    if diag:
        f.append(Paragraph(_esc(diag), st["body"]))
    for a in (fo.get("actions") or []):
        f.append(Paragraph("→  " + _esc(a), st["note"]))
    if ta.get("secondary"):
        se = ta["secondary"]
        f.append(Paragraph(_esc(f"Also worth a look — {se['area']} ({se['score']} of 7):"), st["body"]))
        for a in (se.get("actions") or [])[:2]:
            f.append(Paragraph("→  " + _esc(a), st["note"]))
    if ta.get("keep"):
        f.append(Paragraph(_esc(ta["keep"]), st["body"]))


def team_pdf(payload, vmeta):
    st = rd._pdf_styles()
    meta = _meta(vmeta)
    f = rd._pdf_head(st, meta)
    if not payload.get("card"):
        f.append(Paragraph("No rated activities for this unit yet.", st["body"]))
        return rd._pdf_doc(meta, f)

    N = vmeta.n
    f.append(rd._box("Summary", [Paragraph(_esc(_na_team_summary(payload)), st["boxbody"])], st))
    f.append(Spacer(1, 12))

    fign = [0]

    def fb(heading, png, subject):
        fign[0] += 1
        return rd._fig_block(heading, png, fign[0], subject, st, meta, N=N)

    yoy = payload.get("yoy") or {}
    if len(yoy.get("bars") or []) > 1:
        f.append(fb("Year on year", _chart_person_yoy(payload), "Activity score by year"))
        f.append(Paragraph(_esc(yoy.get("insight", "")), st["body"]))
    if payload.get("trend"):
        f.append(fb("Activity scores over time", _chart_person_trend(payload), "Event-about score over time"))
    if payload.get("breakdown"):
        f.append(fb("Event areas", _chart_person_breakdown(payload), "Event areas, strongest to weakest"))

    standing = payload.get("standing")
    if standing and standing.get("group"):
        f.append(Paragraph("How this unit compares", st["h2"]))
        if standing.get("standing"):
            f.append(Paragraph(_esc(standing["standing"]), st["body"]))
        grid = _team_standing_grid(standing, st)
        if grid is not None:
            f.append(rd._table_block(1, "Standing among " + standing.get("sibling_kind", "siblings"),
                                     grid, st, meta, N=N))
            f.append(Spacer(1, 8))

    coach = payload.get("coach") or {}
    if coach.get("praise") or coach.get("motivation"):
        f.append(Paragraph("Coaching — what's going well", st["h2"]))
        for s in (coach.get("praise") or []):
            f.append(Paragraph("•  " + _esc(s), st["body"]))
        if coach.get("motivation"):
            f.append(Paragraph("<i>" + _esc(coach["motivation"]) + "</i>", st["body"]))

    ta = payload.get("ta") or {}
    if ta.get("focus"):
        _render_ta_pdf(f, ta, st)

    f.append(rd._box("Methods & notes", [Paragraph(_esc(METHODS_TEAM), st["note"])], st, bg=colors.white))
    return rd._pdf_doc(meta, f)


def team_pptx(payload, vmeta):
    prs = rd._ppt_new()
    meta = _meta(vmeta)
    rd._title_slide(prs, meta)
    card = payload.get("card")
    if not card:
        rd._txt(rd._slide(prs), "No rated activities for this unit yet.", 0.8, 3, 11.7, 1, size=20)
        return rd._ppt_save(prs)

    loc = ", ".join(x for x in (meta.get("place"), meta.get("period")) if x)
    N = vmeta.n
    fign = [0]

    def cap(subject):
        fign[0] += 1
        base = f"Figure {fign[0]}. {subject}"
        if loc:
            base += f", {loc}"
        return base + (f" (N = {N:,})" if N else "")

    pg = 1
    band = card.get("band")
    rd._hero(prs, meta, pg, card["rp"]["shown"] + "/7",
             ("Activity rating" + (f" · {band}" if band else ""))
             + f"\n{card.get('events', 0)} activities · {N:,} respondents")
    pg += 1

    if payload.get("trend"):
        rd._chart_slide(prs, meta, pg, "Activity scores over time", _chart_person_trend(payload),
                        sub=(payload.get("coach") or {}).get("trend_read"), cap=cap("Score over time"))
        pg += 1
    if payload.get("breakdown"):
        rd._chart_slide(prs, meta, pg, "Event areas", _chart_person_breakdown(payload),
                        cap=cap("Event areas, strongest to weakest"))
        pg += 1
    yoy = payload.get("yoy") or {}
    if len(yoy.get("bars") or []) > 1:
        rd._chart_slide(prs, meta, pg, "Year on year", _chart_person_yoy(payload),
                        sub=yoy.get("insight"), cap=cap("Score by year"))
        pg += 1
    grp = (payload.get("standing") or {}).get("group")
    if grp:
        rd._stats_slide(prs, meta, pg, "How this unit ranks", [
            ("Overall", f"#{grp['overall']['rank']} of {grp['n']}"),
            ("Quality", f"#{grp['quality']['rank']}"),
            ("Engagement", f"#{grp['engagement']['rank']}"),
        ])
        pg += 1

    rd._methods_slide(prs, meta, pg, METHODS_TEAM,
                      f"Based on {N:,} respondents" + (f" · {loc}" if loc else ""))
    pg += 1

    focus = None
    ta = payload.get("ta") or {}
    if ta.get("focus"):
        fo = ta["focus"]
        acts = fo.get("actions") or []
        focus = f"Strengthen {fo['area']}" + (f": {acts[0]}" if acts else ".")
    rd._takeaways_slide(prs, meta, pg, ((payload.get("coach") or {}).get("praise") or [])[:4], focus)
    return rd._ppt_save(prs)


def _chart_teams_index(payload):
    rows = [r for r in (payload.get("rows") or []) if r["level"] != "bureau"]
    rows = sorted(rows, key=lambda r: r.get("value") or 0)[-16:]
    names = [r["short"] for r in rows]
    vals = [r.get("value") or 0 for r in rows]
    h = max(3.0, 0.42 * len(rows) + 1.2)
    fig, ax = _plt.subplots(figsize=(8.2, h))
    ax.barh(range(len(names)), vals, color=_C["bar"], height=0.66)
    ax.set_yticks(range(len(names))); ax.set_yticklabels(names)
    ax.set_xlim(0, 7.4); ax.set_xlabel("Mean rating (1–7)")
    for y, r in enumerate(rows):
        ax.text((r.get("value") or 0) + 0.06, y, r["score"], va="center", fontsize=8.5, color=_C["soft"])
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(length=0); ax.set_axisbelow(True)
    ax.xaxis.grid(True, color=_C["grid"], linewidth=0.8)
    return _fig_png(fig, 8.2, h)


def _teams_index_summary(rows):
    secs = [r for r in rows if r["level"] == "section"]
    s = f"{len(secs)} unit(s) have rated activities. "
    if secs:
        top = max(secs, key=lambda r: r.get("value") or 0)
        busiest = max(secs, key=lambda r: r.get("events") or 0)
        s += (f"Highest-rated: {top['short']} at {top['score']}/7. "
              f"Most active: {busiest['short']} with {busiest['events']} activities.")
    return s


def teams_index_pdf(payload, vmeta):
    st = rd._pdf_styles()
    meta = _meta(vmeta)
    f = rd._pdf_head(st, meta)
    rows = payload.get("rows") or []
    if not rows:
        f.append(Paragraph("No rated units yet.", st["body"]))
        return rd._pdf_doc(meta, f)

    f.append(rd._box("Summary", [Paragraph(_esc(_teams_index_summary(rows)), st["boxbody"])], st))
    f.append(Spacer(1, 12))
    f.append(rd._fig_block("Units by activity rating", _chart_teams_index(payload), 1,
                           "Each unit's mean activity rating (1–7)", st, meta, N=vmeta.n))
    headers = ["Unit", "Level", "Score", "Activities", "Respondents", "Badges"]
    trows = [[r["short"], r["level"].capitalize(), f"{r['score']}/7", str(r["events"]),
              f"{r['respondents']:,}", str(r["badges"])] for r in rows]
    f.append(rd._table_block(1, "Unit comparison",
                             rd._pdf_grid(headers, trows,
                                          [4.4 * cm, 2.2 * cm, 2.0 * cm, 2.4 * cm, 2.8 * cm, 1.8 * cm],
                                          st, numeric_from=2), st, meta, N=vmeta.n))
    f.append(rd._box("Methods & notes", [Paragraph(_esc(METHODS_TEAM), st["note"])], st, bg=colors.white))
    return rd._pdf_doc(meta, f)


def teams_index_pptx(payload, vmeta):
    prs = rd._ppt_new()
    meta = _meta(vmeta)
    rd._title_slide(prs, meta)
    rows = payload.get("rows") or []
    if not rows:
        rd._txt(rd._slide(prs), "No rated units yet.", 0.8, 3, 11.7, 1, size=20)
        return rd._ppt_save(prs)
    loc = ", ".join(x for x in (meta.get("place"), meta.get("period")) if x)
    n_units = len([r for r in rows if r["level"] == "section"])
    cap = (f"Figure 1. Each unit's mean activity rating (1–7), {loc} (N = {vmeta.n:,})"
           if vmeta.n else None)
    rd._hero(prs, meta, 1, str(n_units), "units with rated activities\n" + (meta.get("period") or ""))
    rd._chart_slide(prs, meta, 2, "Units by activity rating", _chart_teams_index(payload), cap=cap)
    rd._methods_slide(prs, meta, 3, METHODS_TEAM,
                      f"Based on {vmeta.n:,} respondents" + (f" · {loc}" if loc else ""))
    return rd._ppt_save(prs)


# =====================================================================
# PEOPLE — the roster (data-first): a leaderboard chart + the full table of
# everyone with a rating, honoring the page's filters.
# =====================================================================

METHODS_PEOPLE = (
    "The roster lists everyone with at least one rating in the selected scope. Walk-in is the "
    "top-box share (Agree + Strongly Agree); the speaker score is the mean of per-respondent "
    "overall ratings (1–7). The leaderboard ranks by a fair-adjusted score (0–100) that pulls a "
    "few-rating person toward the bureau average, so walk-in and speaker people compare on one "
    "axis and a high score from a single rating can't top a strong score from many.")


def _chart_people_top(payload):
    rows = sorted(payload.get("rows") or [], key=lambda r: r.get("adj", 0))[-15:]
    names = [r["name"] for r in rows]
    vals = [r.get("adj", 0) for r in rows]
    h = max(3.0, 0.42 * len(rows) + 1.2)
    fig, ax = _plt.subplots(figsize=(8.2, h))
    ax.barh(range(len(names)), vals, color=_C["bar"], height=0.66)
    ax.set_yticks(range(len(names))); ax.set_yticklabels(names)
    ax.set_xlim(0, 108); ax.set_xlabel("Fair-adjusted score (0–100)")
    for y, r in enumerate(rows):
        shown = f"{r['rp']}/7" if r["rp"] else (r["arta"] or "")
        ax.text(r.get("adj", 0) + 1, y, f"{shown} · {r['ratings']:,}", va="center",
                fontsize=8, color=_C["soft"])
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(length=0); ax.set_axisbelow(True)
    ax.xaxis.grid(True, color=_C["grid"], linewidth=0.8)
    return _fig_png(fig, 8.2, h)


def people_pdf(payload, vmeta):
    st = rd._pdf_styles()
    meta = _meta(vmeta)
    f = rd._pdf_head(st, meta)
    rows = payload.get("rows") or []
    if not rows:
        f.append(Paragraph("No rated people in this scope.", st["body"]))
        return rd._pdf_doc(meta, f)

    pr = payload.get("profile") or {}
    summ = _strip_html(pr.get("story", "")) or f"{len(rows)} people with ratings."
    f.append(rd._box("Summary", [Paragraph(_esc(summ), st["boxbody"])], st))
    f.append(Spacer(1, 12))
    f.append(rd._fig_block("Top rated (fair-adjusted)", _chart_people_top(payload), 1,
                           "People by fair-adjusted score", st, meta, N=vmeta.n))
    headers = ["Name", "Affil.", "Walk-in", "Speaker", "Ratings", "Badges"]
    trows = [[r["name"], ("Internal" if r["is_internal"] else "External"), r["arta"] or "—",
              (f"{r['rp']}/7" if r["rp"] else "—"), f"{r['ratings']:,}", str(r["badges"])] for r in rows]
    f.append(rd._table_block(1, "People roster",
                             rd._pdf_grid(headers, trows,
                                          [5.0 * cm, 2.0 * cm, 2.0 * cm, 2.2 * cm, 2.2 * cm, 1.6 * cm],
                                          st, numeric_from=2), st, meta, N=vmeta.n))
    f.append(rd._box("Methods & notes", [Paragraph(_esc(METHODS_PEOPLE), st["note"])], st, bg=colors.white))
    return rd._pdf_doc(meta, f)


def people_pptx(payload, vmeta):
    prs = rd._ppt_new()
    meta = _meta(vmeta)
    rd._title_slide(prs, meta)
    rows = payload.get("rows") or []
    if not rows:
        rd._txt(rd._slide(prs), "No rated people in this scope.", 0.8, 3, 11.7, 1, size=20)
        return rd._ppt_save(prs)
    loc = ", ".join(x for x in (meta.get("place"), meta.get("period")) if x)
    pr = payload.get("profile") or {}
    cap = (f"Figure 1. People by fair-adjusted score, {loc} (N = {vmeta.n:,})" if vmeta.n else None)
    rd._hero(prs, meta, 1, str(len(rows)),
             "people with ratings\n" + (f"{pr.get('ratings', 0):,} voices" if pr else ""))
    rd._chart_slide(prs, meta, 2, "Top rated (fair-adjusted)", _chart_people_top(payload), cap=cap)
    rd._methods_slide(prs, meta, 3, METHODS_PEOPLE,
                      f"{len(rows)} people" + (f" · {loc}" if loc else ""))
    return rd._ppt_save(prs)


# =====================================================================
# VERBATIMS — the comment digest (PDF/PPTX): top themes + a few sample quotes
# per side. The full text export is the XLSX/CSV (handled by dashboard_export).
# =====================================================================

METHODS_VERBATIMS = (
    "Comments are the free text respondents left, for the selected scope and survey type. They are "
    "read, never scored. Each comment is auto-classified as something appreciated or to improve, and "
    "tagged to one or more themes; a manual re-tag overrides the automatic one. The full comment list "
    "is on the data (Excel/CSV) export — this digest shows the most-mentioned themes and a few "
    "representative quotes.")


def _chart_verbatims(payload):
    themes = (payload.get("themes") or [])[:12]
    names = [t["name"] for t in themes][::-1]
    vals = [t["count"] for t in themes][::-1]
    h = max(3.0, 0.42 * len(names) + 1.2)
    fig, ax = _plt.subplots(figsize=(8.2, h))
    ax.barh(range(len(names)), vals, color=_C["bar"], height=0.66)
    ax.set_yticks(range(len(names))); ax.set_yticklabels(names)
    ax.set_xlim(0, max(vals) * 1.15 if vals else 1)   # headroom for the count labels
    ax.set_xlabel("Comments mentioning this theme")
    for i, v in enumerate(vals):
        ax.text(v, i, f" {v:,}", va="center", fontsize=8.5, color=_C["soft"])
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(length=0); ax.set_axisbelow(True)
    ax.xaxis.grid(True, color=_C["grid"], linewidth=0.8)
    return _fig_png(fig, 8.2, h)


def _verbatims_side(f, st, heading, side):
    buckets = side.get("buckets") or []
    if not buckets:
        return
    f.append(Paragraph(heading, st["h2"]))
    if side.get("phrase"):
        f.append(Paragraph(_esc(side["phrase"]), st["body"]))
    for b in buckets:
        f.append(Paragraph(f"<b>{_esc(b['name'])}</b> ({b['count']})", st["note"]))
        for q in (b.get("quotes") or [])[:2]:
            f.append(Paragraph("“" + _esc(q) + "”", st["body"]))


def verbatims_pdf(payload, vmeta):
    st = rd._pdf_styles()
    meta = _meta(vmeta)
    f = rd._pdf_head(st, meta)
    if not payload.get("rows"):
        f.append(Paragraph("No written comments in this scope.", st["body"]))
        return rd._pdf_doc(meta, f)

    total = payload.get("total", len(payload["rows"]))
    phrases = [p for p in ((payload.get("appreciate") or {}).get("phrase", ""),
                           (payload.get("improve") or {}).get("phrase", "")) if p]
    summ = f"{total:,} comment(s) in this scope." + ("  " + ".  ".join(phrases) + "." if phrases else "")
    f.append(rd._box("Summary", [Paragraph(_esc(summ), st["boxbody"])], st))
    f.append(Spacer(1, 12))

    fignum = 0
    if payload.get("themes"):
        fignum += 1
        f.append(rd._fig_block("What people talk about most", _chart_verbatims(payload), fignum,
                               "Comment themes by mention count", st, meta, N=vmeta.n))

    sbd = payload.get("sentiment_breakdown")
    sfig = _chart_sentiment_breakdown(payload) if sbd else None
    if sfig:
        fignum += 1
        cap = ("Share of comments reading as appreciation, an area to improve, or mixed "
               "(mentions both), each period; the three shares total 100%."
               + (" " + sbd["read"]["text"] if sbd.get("read") else ""))
        f.append(rd._fig_block("Tone of comments over time", sfig, fignum, cap, st, meta,
                               N=sbd.get("n")))

    _verbatims_side(f, st, "Appreciated", payload.get("appreciate") or {})
    _verbatims_side(f, st, "To improve", payload.get("improve") or {})

    f.append(rd._box("Methods & notes", [Paragraph(_esc(METHODS_VERBATIMS), st["note"])],
                     st, bg=colors.white))
    return rd._pdf_doc(meta, f)


def verbatims_pptx(payload, vmeta):
    prs = rd._ppt_new()
    meta = _meta(vmeta)
    rd._title_slide(prs, meta)
    if not payload.get("rows"):
        rd._txt(rd._slide(prs), "No written comments in this scope.", 0.8, 3, 11.7, 1, size=20)
        return rd._ppt_save(prs)
    loc = ", ".join(x for x in (meta.get("place"), meta.get("period")) if x)
    total = payload.get("total", len(payload["rows"]))
    pg = 1
    rd._hero(prs, meta, pg, f"{total:,}", "comments in this scope\n" + (meta.get("period") or ""))
    pg += 1
    fignum = 0
    if payload.get("themes"):
        fignum += 1
        cap = (f"Figure {fignum}. Comment themes by mention count, {loc} (N = {vmeta.n:,})" if vmeta.n else None)
        rd._chart_slide(prs, meta, pg, "What people talk about most", _chart_verbatims(payload), cap=cap)
        pg += 1
    sbd = payload.get("sentiment_breakdown")
    sfig = _chart_sentiment_breakdown(payload) if sbd else None
    if sfig:
        fignum += 1
        n = sbd.get("n")
        cap = (f"Figure {fignum}. Tone of comments over time, {loc}"
               + (f" (N = {n:,})" if n else "") + ". Shares total 100% per period.")
        rd._chart_slide(prs, meta, pg, "Tone of comments over time", sfig, cap=cap)
        pg += 1
    items = []
    for q in ((payload.get("appreciate") or {}).get("buckets") or []):
        for t in (q.get("quotes") or [])[:1]:
            items.append((t, _C["good"].lstrip("#"), "Appreciated"))
    for q in ((payload.get("improve") or {}).get("buckets") or []):
        for t in (q.get("quotes") or [])[:1]:
            items.append((t, _C["mid"].lstrip("#"), "To improve"))
    if items:
        rd._quotes_slide(prs, meta, pg, "In their words", items[:4])
        pg += 1
    rd._methods_slide(prs, meta, pg, METHODS_VERBATIMS,
                      f"{total:,} comments" + (f" · {loc}" if loc else ""))
    return rd._ppt_save(prs)
