"""
Office Connect dashboard insights
=========================

The plain-language layer. The engine (css_is_engine) turns atoms into numbers;
this turns those numbers into something everyone can read — a phrase, a story, a
"worth looking at" callout — for the public dashboard at /dashboard.

Nothing here invents scoring. Every score still comes from eng.* run on a slice
of the atoms. This module only:
  * gives the survey items short, human labels (no SQD/B codes for the public),
  * groups free-text comments into themes and an appreciate / improve story,
  * reads a trend or a person's spread and says what it means in words,
  * slices the atoms per person and per event so the views can be built.

The reports page (/reports) keeps the technical numbers; the dashboard speaks.
"""

from __future__ import annotations
import re
import math
import statistics
import numpy as np
import pandas as pd

import css_is_engine as eng

# =====================================================================
# PLAIN LABELS — codes stay in the reports; the public sees these words.
# ARTA SQD wording confirmed against ARTA MC 2022-05 (the official CSM form).
# =====================================================================

SQD_LABELS = {
    "SQD1": "Service was prompt",
    "SQD2": "Steps were clear and followed",
    "SQD3": "Process was simple",
    "SQD4": "Information was easy to find",
    "SQD5": "Fees were reasonable",
    "SQD6": "No irregularities",
    "SQD7": "Staff were respectful",
    "SQD8": "Got what I needed",
}

# How to name the same item when it is the WEAK spot (read as a concern).
SQD_CONCERN = {
    "SQD1": "how long service takes",
    "SQD2": "how clear the steps are",
    "SQD3": "how simple the process is",
    "SQD4": "how easy it is to find information",
    "SQD5": "whether fees feel reasonable",
    "SQD6": "fairness during the transaction",
    "SQD7": "how respectful staff are",
    "SQD8": "getting what they came for",
}

# Plain names for the SERVQUAL dimensions — the public never sees "B6"/"Tangible".
# The SAME five dimensions read DIFFERENTLY on each form: Form 2 asks about the
# CONDUCT OF THE ACTIVITY (the event and the people organizing it); Form 3 asks
# about the RESOURCE PERSON (the individual speaker), so each form gets its own
# labels rather than a shared generic set.
#
# EVERY LABEL BELOW MUST DESCRIBE THE ITEMS ITS DIMENSION ACTUALLY CONTAINS —
# i.e. app.B_TEXT_ACTIVITY (Form 2) / app.B_TEXT (Form 3) grouped by
# eng.DIM_MAP_FORM2 / DIM_MAP_FORM3. These two are the only source of truth; if
# you change a question's wording or a dimension's items, re-read the label here.
# (They were originally written from the column headers in CSS Spreadsheets.xlsx,
# which describes a DIFFERENT set of B-items than the questions this app asks —
# hence "Courteous organizers" over an item about competence, and "well dressed
# and appears neat" over an item about materials and the venue. Corrected in
# v2.56 to match the questions people are actually answering.)
DIM_LABELS_F2 = {        # Form 2 — how the activity itself was run
    "Reliability":    "Delivered as promised",     # B1–B4: as announced, accurate, on schedule, reliable
    "Responsiveness": "Organizers ready to help",  # B5: organizers responsive to questions and needs
    "Assurance":      "Knowledgeable organizers",  # B6: handled by knowledgeable, competent people
    "Empathy":        "Clear & reassuring",        # B7: communicated clearly, gave confidence
    # NOTE: this bucket really does average two different things — B8 is about
    # caring attention to participants, B9 about materials and the venue. The
    # label names both rather than pretending it is only the venue; the grouping
    # itself is eng.DIM_MAP_FORM2's (LOCKED — changing it moves published scores).
    "Tangible":       "Attention & set-up",        # B8–B9: attention to participants, materials/venue
}
DIM_CONCERN_F2 = {
    "Reliability":    "delivering the activity as promised",
    "Responsiveness": "organizers being ready to help",
    "Assurance":      "the organizers' knowledge and competence",
    "Empathy":        "how clearly things were communicated",
    "Tangible":       "attention to participants and the set-up",
}
DIM_LABELS_F3 = {        # Form 3 — how the resource person came across
    "Reliability":    "Delivered as promised",      # B1–B4: as announced, accurate, on schedule, reliable
    "Responsiveness": "Open to questions",          # B5: responsive to questions and needs
    "Assurance":      "Knowledgeable & clear",      # B6–B7: knowledgeable/competent, clear, inspired confidence
    "Empathy":        "Attentive to the audience",  # B8: gave caring attention to participants
    "Tangible":       "Materials & venue",          # B9: materials, venue and presentation
}
DIM_CONCERN_F3 = {
    "Reliability":    "delivering the session as promised",
    "Responsiveness": "openness to questions",
    "Assurance":      "knowledge and clarity",
    "Empathy":        "attentiveness to the audience",
    "Tangible":       "the materials and venue",
}
# Generic aliases default to the resource-person set: the person-centric views
# (People grid, person detail, bureau benchmarks) are all Form 3.
DIM_LABELS = DIM_LABELS_F3
DIM_CONCERN = DIM_CONCERN_F3


def dim_labels(survey_type):
    """Form-appropriate dimension labels — activity-conduct for Form 2, resource
    person for Form 3 (and the F3 set as the default for everything else)."""
    return DIM_LABELS_F2 if survey_type == 2 else DIM_LABELS_F3


def dim_concern(survey_type):
    return DIM_CONCERN_F2 if survey_type == 2 else DIM_CONCERN_F3


def survey_title(survey_type):
    return {1: "Walk-in service", 2: "Activities & events",
            3: "Resource persons"}.get(survey_type, "Feedback")


# Band thresholds for a SERVQUAL perception mean (1–7). The engine's OSQ_BANDS are
# for the 1–4 overall-quality item, not this scale, so we keep a separate table.
SEVEN_BANDS = [(1, 4.0, "Poor"), (4.0, 5.5, "Fair"), (5.5, 6.25, "Good"), (6.25, 7.001, "Excellent")]


def band7(value):
    return eng.band(value, SEVEN_BANDS) if value is not None else None


def band_index(value):
    """Band label for the 0-100 Quality Index (the headline quality metric)."""
    return eng.band(value, eng.QUALITY_INDEX_BANDS) if value is not None else None


def _qi_metric(df):
    """The Quality Index as a Metric, so it can serve as a _trend / year_over_year
    scorer (headline + trends are on the index, a 0-100 'pct'-scale metric)."""
    idx, n = eng.quality_index(df)
    return eng.Metric(idx, n, "quality index")


# =====================================================================
# PERIODS — month / quarter / year, derived straight from event_date so the
# dashboard can offer a finer grain than the engine's stored columns.
# =====================================================================

_MONTHS = ["", "Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


_PERIOD_COL = {"monthly": "month", "quarterly": "quarter", "yearly": "year"}


def period_col_for(grain):
    return _PERIOD_COL.get(grain, "quarter")


def _keys(df, grain):
    """The period-key Series for a frame at `grain`, reading the column that
    assign_periods precomputed (no date re-parsing on hot paths)."""
    return df[period_col_for(grain)]


def period_keys(dates, grain):
    """A Series of period keys for a Series of event_dates, at the chosen grain.
    Fallback for callers that only have raw dates; hot paths use _keys(df)."""
    d = pd.to_datetime(dates)
    if grain == "monthly":
        return d.dt.strftime("%Y-%m")
    if grain == "yearly":
        return d.dt.year.astype(str)
    return d.dt.year.astype(str) + "-Q" + d.dt.quarter.astype(str)   # quarterly


def span_label(dates):
    """A human date span for captions, e.g. 'Feb 2026 – May 2026' (or a single
    month if all the data falls in one)."""
    if dates is None or len(dates) == 0:
        return ""
    d = pd.to_datetime(dates)
    lo, hi = d.min(), d.max()
    a = f"{_MONTHS[lo.month]} {lo.year}"
    b = f"{_MONTHS[hi.month]} {hi.year}"
    return a if a == b else f"{a} – {b}"


def period_label(key, grain):
    if grain == "monthly":
        y, m = key.split("-")
        return f"{_MONTHS[int(m)]} {y}"
    if grain == "yearly":
        return key
    y, q = key.split("-Q")
    return f"Q{q} {y}"


# =====================================================================
# VERBATIM STORY — predefined theme buckets (chosen over raw word-frequency:
# repeatable, readable, no dependencies) + a light appreciate / improve split.
# =====================================================================

# Each bucket: keywords to match, a noun for "N people talked about ___",
# and how to phrase it as praise vs. as something to improve.
THEME_BUCKETS = [
    {"key": "speed", "name": "Speed & waiting",
     "words": ["time", "times", "wait", "waited", "waiting", "fast", "quick", "quickly",
               "slow", "slowly", "delay", "delayed", "long", "hour", "hours", "minutes",
               "prompt", "late", "schedule", "overran", "ran over", "on time"],
     "noun": "timing", "praise": "fast, low-wait service", "improve": "speed and waiting times"},
    {"key": "process", "name": "Clarity & process",
     "words": ["step", "steps", "unclear", "confusing", "confused", "instruction",
               "instructions", "requirement", "requirements", "process", "form", "forms",
               "complicated", "simple", "easy", "documents", "paperwork"],
     "noun": "the process", "praise": "a clear, simple process", "improve": "clearer steps and instructions"},
    {"key": "staff", "name": "Staff & attitude",
     "words": ["staff", "officer", "personnel", "rude", "helpful", "polite", "courteous",
               "friendly", "accommodating", "attitude", "respectful", "kind", "patient"],
     "noun": "the staff", "praise": "courteous, helpful staff", "improve": "how staff interact with people"},
    {"key": "knowledge", "name": "Knowledge & content",
     "words": ["knowledge", "knowledgeable", "accurate", "accuracy", "correct", "expert",
               "expertise", "answer", "answers", "topic", "speaker", "content", "informative",
               "competent", "clear", "engaging", "prepared", "practical"],
     "noun": "knowledge", "praise": "knowledge and expertise", "improve": "depth or accuracy of the content"},
    {"key": "facilities", "name": "Facilities & access",
     "words": ["venue", "room", "hall", "website", "site", "online", "portal", "parking",
               "location", "accessible", "navigate", "find", "found", "warm", "cramped",
               "seats", "seating", "materials", "handout", "handouts", "audio", "sound",
               "sounds", "mic", "microphone", "volume", "screen",
               "internet", "connection", "connectivity", "platform", "wifi", "signal"],
     "noun": "facilities", "praise": "the venue and materials", "improve": "facilities, venue, or finding information"},
    {"key": "outcome", "name": "Outcome & value",
     "words": ["resolved", "completed", "useful", "worth", "worthwhile", "satisfied",
               "achieved", "fee", "fees", "cost", "payment", "value", "needed", "helped",
               "inspiring", "great", "excellent", "improvement"],
     "noun": "outcomes", "praise": "useful, worthwhile outcomes", "improve": "the outcome or value delivered"},
]

# Sentiment cues for the appreciate / improve split. Matched by WHOLE WORD against the
# ordered token list (so a negative like "unclear" is never read as the positive
# "clear", and "breakfast" never as "fast"), with negation handled BOTH ways via the
# preceding token: a negated negative is neutral ("no problem", "without difficulty"),
# a negated positive is a complaint ("not clear", "wasn't helpful"). The rule is
# deliberately complaint-forward: any un-negated concrete issue sends the quote to
# "improve" — a polite "thank you" never buries an actionable problem. Only a quote
# with NO live negative signal lands in "appreciate" (most feedback is praise).
_POS_WORDS = {
    "thank", "thanks", "great", "excellent", "helpful", "clear", "clearly",
    "knowledgeable", "smooth", "easy", "quick", "polite", "courteous", "inspiring",
    "fantastic", "accommodating", "solid", "good", "better", "best", "practical",
    "engaging", "informative", "wonderful", "appreciate", "appreciated", "nice",
    "satisfied", "organized", "commendable", "effective", "efficient", "professional",
    "insightful", "approachable", "patient", "kind", "enjoyed", "loved", "perfect",
    "amazing", "awesome", "thankful", "grateful", "audible", "working", "accessible",
    "stable", "prepared", "enough", "complete", "sufficient",
    # Mostly meaningful when NEGATED ("did not understand", "couldn't hear/connect").
    "understand", "understood", "hear", "heard", "follow", "followed", "catch",
    "connect", "connected", "load", "loaded",
}
_NEG_WORDS = {
    "unclear", "confusing", "confused", "difficult", "difficulty", "difficulties",
    "slow", "late", "problem", "problems", "issue", "issues", "complicated", "poor",
    "bad", "noise", "noisy", "inconsistent", "struggle", "struggled", "struggling",
    "cramped", "lacking", "lacked", "disorganized", "boring", "weak", "unprepared",
    "inaudible", "unstable", "laggy", "lag", "lagging", "delay", "delays", "delayed",
    "rushed", "insufficient", "crowded", "wish", "sana", "hope", "hoped", "hoping",
    "enhancement", "enhancements", "lengthy", "disappointing", "disappointed",
    "interrupted", "hassle", "tedious", "overwhelming", "incomplete", "missing",
    "error", "errors", "glitch", "glitches", "choppy", "blurry", "echo", "freezing",
    "froze", "distracting", "limited", "cutting", "buffering", "unreliable", "fix",
    "unanswered", "contradiction", "contradictions", "muffled", "garbled", "distorted",
    "static", "unintelligible", "incomprehensible", "robotic",
    # Filipino / Taglish negatives (the data is bilingual).
    "problema", "mabagal", "bagal", "mahina", "hina", "mahirap", "nahirapan",
    "nahihirapan", "hirap", "kulang", "malabo", "ingay", "maingay", "putol",
    "putolputol", "sira", "ayusin", "dapat", "sayang", "gulo", "magulo",
}
# High-precision multi-word negatives (rarely negated, so matched as substrings).
_NEG_PHRASES = ("too long", "too short", "too fast", "too slow", "too many",
                "too much", "too little", "hard to", "difficult to", "unable to",
                "not enough", "ran over", "over time", "long wait", "more time",
                "needs improvement", "room for improvement", "for improvement",
                "could improve", "to improve", "improve the", "be improved",
                "would be better", "could be better", "lack of", "needs more",
                "need more", "need to improve", "hard time", "longer time")
# Tokens that flip the sentiment of a nearby word (English + Filipino "hindi/wala").
_NEGATORS = {"not", "no", "never", "without", "hardly", "barely", "dont", "don't",
             "doesnt", "doesn't", "didnt", "didn't", "cant", "can't", "couldnt",
             "couldn't", "wont", "won't", "isnt", "isn't", "wasnt", "wasn't",
             "arent", "aren't", "werent", "weren't", "cannot", "nothing",
             "hindi", "wala", "walang", "wlang", "huwag"}


def _tokens(text):
    return re.findall(r"[a-z']+", (text or "").lower())


# Words whose UN-negated form isn't genuine praise — they only carry sentiment when
# negated ("did not understand", "couldn't hear"). Kept out of praise detection so a
# plain factual comment doesn't read as positive.
_NEGATED_ONLY_POS = {"understand", "understood", "hear", "heard", "follow",
                     "followed", "catch", "connect", "connected", "load", "loaded"}
_PRAISE_WORDS = _POS_WORDS - _NEGATED_ONLY_POS


def _signals(text):
    """(has_praise, has_complaint) for a quote, using a two-token negation window.
    A live complaint = a negative phrase, an un-negated concrete negative, or a
    negated positive ("not clear"). Live praise = an un-negated praise word, or a
    negated negative ("no problem", "walang problema"). A quote can carry both."""
    low = (text or "").lower()
    has_complaint = any(p in low for p in _NEG_PHRASES)
    has_praise = False
    toks = _tokens(text)
    for i, t in enumerate(toks):
        # Look back up to two tokens, so "wala pong problema" / "not very clear" read
        # as negated (politeness particles or adverbs can sit between the two).
        negated = any(w in _NEGATORS for w in toks[max(0, i - 2):i])
        if t in _NEG_WORDS:
            if negated:
                has_praise = True             # "no problem" / "walang problema"
            else:
                has_complaint = True          # a live complaint
        elif t in _POS_WORDS:
            if negated:
                has_complaint = True          # "not clear" / "wasn't helpful"
            elif t in _PRAISE_WORDS:
                has_praise = True
    return has_praise, has_complaint


def classify_quote(text):
    """'appreciate', 'improve', or 'mixed'. A quote that carries BOTH a live complaint
    and live praise is 'mixed' (good-but-bad / bad-but-good) — it belongs on both
    sides rather than being filed under one, so neither the praise nor the problem is
    hidden. A quote with only a live complaint is 'improve'; anything else is
    'appreciate' (most feedback is praise)."""
    praise, complaint = _signals(text)
    if praise and complaint:
        return "mixed"
    if complaint:
        return "improve"
    return "appreciate"


# "clear(ly)" is a Knowledge cue ("the speaker explained clearly") but ALSO
# describes AV quality ("clear audio", "platform not clear"). It is the one word
# the Knowledge bucket shares with the room/AV world, so it needs disambiguation.
_AMBIGUOUS_CLARITY = {"clear", "clearly"}


def match_buckets(text):
    """Which theme buckets a quote touches (a quote can touch several).

    Disambiguate "clear": when a quote also lands in Facilities (a real venue/AV
    word like "audio" or "venue" is present) and Knowledge matched ONLY on a
    clarity word, the clarity is about the room/AV, not the content — so drop the
    spurious Knowledge tag and leave the comment under Facilities. A quote that
    names the content too (e.g. "speaker", "topic") keeps its Knowledge tag."""
    toks = set(_tokens(text))
    low = (text or "").lower()
    matched = {}
    for b in THEME_BUCKETS:
        hitwords = [w for w in b["words"] if (w in toks) or (" " in w and w in low)]
        if hitwords:
            matched[b["key"]] = hitwords
    hits = list(matched)
    if ("knowledge" in matched and "facilities" in matched
            and all(w in _AMBIGUOUS_CLARITY for w in matched["knowledge"])):
        hits.remove("knowledge")
    return hits


def _flatten_quotes(verbatims):
    """verbatims (from storage.verbatims_for_responses) -> flat quote dicts.
    Each overall remark and each item note becomes its own quote, carrying its
    identity (rid + item, '' for the overall remark) so a manual re-tag can target it."""
    quotes = []
    for v in verbatims:
        rid = v.get("response_id")
        meta = {"when": v.get("when"), "form_id": v.get("form_id"),
                "activity": v.get("activity"), "topic": v.get("topic"), "rid": rid}
        if v.get("remarks"):
            quotes.append({"text": v["remarks"], "item": "", **meta})
        for item, text in (v.get("notes") or {}).items():
            if text:
                quotes.append({"text": text, "item": item, **meta})
    return quotes


# Public alias — docs/AI_INTEGRATION_PLAN.md Phase 4's AI re-analyze/summary
# callers need the same flat (rid, item, text) quotes story_panel builds from,
# without reaching into a name marked private.
flatten_quotes = _flatten_quotes


def _phrase_for_side(buckets_sorted, side):
    """A one-line headline for the appreciate / improve column."""
    if not buckets_sorted:
        return None
    top = buckets_sorted[0]
    bdef = next(b for b in THEME_BUCKETS if b["key"] == top["key"])
    n = top["count"]
    who = "person" if n == 1 else "people"
    if side == "appreciate":
        return f"{n} {who} praised {bdef['praise']}"
    return f"{n} {who} pointed to {bdef['improve']}"


def story_panel(verbatims, overrides=None, split_mixed=False):
    """Turn a scope's comments into a two-sided story grouped by theme. `overrides`
    is {(response_id, item): 'appreciate'|'improve'|'mixed'} from manual re-tags — a
    user's correction wins over the automatic classification.

    A 'mixed' quote (good-but-bad / bad-but-good) carries q['sentiment'] == 'mixed'
    so the template can badge it. By default it is credited to BOTH sides (nothing
    hidden, nothing misplaced). With `split_mixed=True` it goes ONLY to its own
    `mixed` group instead — for the Verbatims page's three-column layout
    (Appreciate / Improve / Mixed), where Mixed gets a column of its own rather
    than being duplicated across the two (feedback #54).

    Returns {total, appreciate:{phrase, buckets:[{key,name,noun,count,quotes}]},
             improve:{...}, mixed:{...}} — pull-quote style, ready for the template.
    The `mixed` group is empty unless `split_mixed` is set."""
    overrides = overrides or {}
    quotes = _flatten_quotes(verbatims)
    sides = {"appreciate": {}, "improve": {}, "mixed": {}}
    for q in quotes:
        forced = overrides.get((q.get("rid"), q.get("item", "")))
        q["overridden"] = forced is not None      # so the template can flag a manual tag
        sentiment = (forced if forced in ("appreciate", "improve", "mixed")
                     else classify_quote(q["text"]))
        q["sentiment"] = sentiment                # 'appreciate' | 'improve' | 'mixed'
        keys = match_buckets(q["text"]) or ["__other__"]
        if sentiment == "mixed":
            targets = ("mixed",) if split_mixed else ("appreciate", "improve")
        else:
            targets = (sentiment,)
        for side in targets:
            for k in keys:
                sides[side].setdefault(k, []).append(q)

    def pack(side_map):
        buckets = []
        for k, qs in side_map.items():
            if k == "__other__":
                name, noun = "Other", "other things"
            else:
                bdef = next(b for b in THEME_BUCKETS if b["key"] == k)
                name, noun = bdef["name"], bdef["noun"]
            buckets.append({"key": k, "name": name, "noun": noun,
                            "count": len(qs), "quotes": qs})
        # most-talked-about first; "Other" always sinks to the bottom
        buckets.sort(key=lambda b: (b["key"] == "__other__", -b["count"]))
        named = [b for b in buckets if b["key"] != "__other__"]
        return {"buckets": buckets, "phrase": _phrase_for_side(named, side_name)}

    side_name = "appreciate"
    appreciate = pack(sides["appreciate"])
    side_name = "improve"
    improve = pack(sides["improve"])
    side_name = "mixed"
    mixed = pack(sides["mixed"])
    return {"total": len(quotes), "appreciate": appreciate, "improve": improve,
            "mixed": mixed}


# =====================================================================
# READING THE NUMBERS — consistency, stability, signal phrases.
# Scales differ: ARTA headline is a 0–100 top-box %, SERVQUAL is a 1–7 mean.
# =====================================================================

# How big a swing counts as "a lot" for each scale.
_VOLATILE = {"pct": 8.0, "mean7": 0.8}


def consistency(values, scale="mean7"):
    """Plain-language read on how much a person's scores swing between sessions.
    Informational only — it surfaces the pattern, it is not a flag on the person."""
    vals = [n for v in values if (n := eng.finite_number(v)) is not None]
    if len(vals) < 2:
        return {"known": False, "stable": None, "sd": None,
                "phrase": "Not enough sessions yet to tell whether scores are steady."}
    sd = statistics.stdev(vals)
    stable = sd < _VOLATILE.get(scale, 0.8)
    if stable:
        phrase = "Scores are consistent across sessions — they don't swing much."
    else:
        phrase = ("Scores vary a lot between sessions — worth looking at what's "
                  "different on the higher- and lower-rated ones.")
    return {"known": True, "stable": stable, "sd": sd, "phrase": phrase}


def stability_phrase(series, scale="mean7"):
    """Read a trend (list of {value}) and say what it's doing, in words.
    Returns {phrase, tone} where tone is good / bad / neutral."""
    vals = [n for p in series if (n := eng.finite_number(p.get("value"))) is not None]
    n = len(vals)
    if n < 2:
        return {"phrase": "Not enough periods yet to see a trend.", "tone": "neutral"}
    sd = statistics.stdev(vals)
    span = max(vals) - min(vals)
    swing = _VOLATILE.get(scale, 0.8)
    move = vals[-1] - vals[0]
    # A genuinely bouncy line (big spread, no clear direction) reads as inconsistent.
    if sd >= swing and abs(move) < span * 0.6:
        return {"phrase": "Scores are inconsistent — worth investigating what changed.",
                "tone": "bad"}
    rise = swing * 0.5
    if move >= rise:
        return {"phrase": f"Steadily improving over the last {n} periods.", "tone": "good"}
    if move <= -rise:
        return {"phrase": f"Trending downward over the last {n} periods — worth a look.",
                "tone": "bad"}
    return {"phrase": "Holding steady.", "tone": "neutral"}


def arta_signal(df):
    """The headline plain-language read for walk-in service: name the weakest
    part (most actionable), or praise the strongest if nothing is weak."""
    scored = []
    for it in eng.ARTA_HEADLINE_ITEMS:
        det = eng.arta_item_detail(df, it)
        if det.get("score") is not None and det["n"] >= 1:
            scored.append((it, det["score"]))
    if not scored:
        return None
    scored.sort(key=lambda x: x[1])
    low_it, low_v = scored[0]
    high_it, high_v = scored[-1]
    if low_v < 80:
        return (f"Clients are least satisfied with {SQD_CONCERN[low_it]} — "
                f"it's the lowest-scoring part of the walk-in experience "
                f"({low_v:.0f}% positive).")
    return (f"“{SQD_LABELS[high_it]}” is the strongest part of the walk-in "
            f"experience ({high_v:.0f}% positive).")


def frame_item_means(df):
    """All item means for a frame in ONE groupby (item_id -> mean of non-NA
    values), so the whole-frame overall/dimension/signal computations don't each
    re-scan the frame per item. Returns a dict."""
    if not _has(df):
        return {}
    valid = eng.valid_answers(df)
    if valid.empty:
        return {}
    return valid.groupby("item_id", observed=True)["value"].mean().to_dict()


def frame_dim_means(dim_map, item_means):
    """Dimension means from precomputed item means (mean of present item means).
    Matches eng.dimension_mean's definition; returns {dim: value}."""
    out = {}
    for dim, items in dim_map.items():
        present = [item_means[it] for it in items
                   if it in item_means and item_means[it] == item_means[it]]
        if present:
            out[dim] = sum(present) / len(present)
    return out


def frame_overall(dim_map, item_means):
    """Overall perception = mean of dimension means, from precomputed item means.
    Matches eng.overall_perception exactly."""
    dvals = list(frame_dim_means(dim_map, item_means).values())
    return (sum(dvals) / len(dvals)) if dvals else None


def servqual_signal(df, dim_map, item_means=None, labels=DIM_LABELS, concern=DIM_CONCERN):
    """Headline read for an activity / resource-person slice: weakest dimension,
    or strongest if all are solid, plus the expectation gap when it bites.
    `labels`/`concern` are the form-appropriate plain names (Form 2 vs Form 3).
    `item_means` may be passed in (frame_item_means) to avoid re-scanning."""
    im = item_means if item_means is not None else frame_item_means(df)
    dims = sorted(frame_dim_means(dim_map, im).items(), key=lambda x: x[1])
    if not dims:
        return None
    low_dim, low_v = dims[0]
    high_dim, high_v = dims[-1]
    overall_v = frame_overall(dim_map, im)
    expc_v = im.get("A")
    gap_note = ""
    if overall_v is not None and expc_v is not None:
        if overall_v - expc_v < -0.25:
            gap_note = " Overall, the experience landed below what people expected."
    if low_v < 5.5:
        return (f"The weakest area is {concern[low_dim]} "
                f"(scoring {low_v:.1f} of 7).{gap_note}")
    return (f"“{labels[high_dim]}” is the strongest point "
            f"({high_v:.1f} of 7).{gap_note}")


# =====================================================================
# SLICING — per person, per event, per period. "Slice, then run the calculator."
# =====================================================================

def _has(df):
    return df is not None and not df.empty


def arta_slice(atoms, rp_id):
    return atoms[(atoms["survey_type"] == 1) & (atoms["served_by_rp_id"] == rp_id)]


def rp_slice(atoms, rp_id):
    return atoms[(atoms["survey_type"] == 3) & (atoms["rp_id"] == rp_id)]


def _band_view(value, bands):
    return eng.band(value, bands) if value is not None else None


_FORM3_ITEMS = [it for items in eng.DIM_MAP_FORM3.values() for it in items]


def _spread_read(per_resp, scale7):
    """How much respondents agree about a person, from the spread of their
    per-respondent overall scores. A consensus read — not a judgement."""
    n = len(per_resp)
    if n < 3:
        return {"label": "too few to tell", "sd": None, "tone": "unknown"}
    sd = float(per_resp.std(ddof=1))
    lo, hi = (0.8, 1.5) if scale7 else (0.6, 1.1)
    if sd < lo:
        return {"label": "strong agreement", "sd": round(sd, 2), "tone": "good"}
    if sd < hi:
        return {"label": "some spread", "sd": round(sd, 2), "tone": "mid"}
    return {"label": "mixed views", "sd": round(sd, 2), "tone": "bad"}


def _person_extras(a, r, has_rp, has_arta):
    """A name-positive 'standout strength', a robust top-box %, a consensus (spread)
    read, and the WEAKEST dimension value (for the well-rounded badge) — from their
    own slice only, no ranking."""
    strongest = topbox = spread = weakest = None
    dim_values = None
    if has_rp:
        dims = _ranked_dimensions(r, eng.DIM_MAP_FORM3)
        if dims:
            strongest = dims[0]["name"]               # raw highest (fallback)
            weakest = dims[-1]["value"]               # lowest dimension — is anything dragging?
            dim_values = {d["name"]: d["value"] for d in dims}   # for the distinctive read
        valid = r[(~r["is_na"]) & (r["item_id"].isin(_FORM3_ITEMS))]
        if len(valid):
            topbox = round(float((valid["value"] >= 6).mean()) * 100)
            spread = _spread_read(valid.groupby("response_id")["value"].mean(), scale7=True)
    elif has_arta:
        items = _arta_items(a)
        strongest = items[0]["name"] if items else None
        valid = a[(~a["is_na"]) & (a["item_id"].isin(eng.ARTA_HEADLINE_ITEMS))]
        if len(valid):
            topbox = round(float((valid["value"] >= 4).mean()) * 100)
            spread = _spread_read(valid.groupby("response_id")["value"].mean(), scale7=False)
    return {"strongest": strongest, "topbox": topbox, "spread": spread,
            "weakest": weakest, "dim_values": dim_values}


def _confidence(n):
    """Reliability of a person's score given how many ratings back it. Five levels,
    log-spaced — reliability grows with √n, so the thresholds step geometrically
    (10/30/100/300/1000) and a 3,000-rating veteran clearly outranks a 120-rating one."""
    if n >= 1000:
        return {"level": "vhigh", "label": "Very high confidence", "dots": 5}
    if n >= 300:
        return {"level": "high", "label": "High confidence", "dots": 4}
    if n >= 100:
        return {"level": "good", "label": "Good confidence", "dots": 3}
    if n >= 30:
        return {"level": "fair", "label": "Fair confidence", "dots": 2}
    if n >= eng.N_MIN:
        return {"level": "build", "label": "Building confidence", "dots": 1}
    return {"level": "early", "label": "Early read — too few ratings to be sure", "dots": 0}


def person_overall_score(r):
    """Headline for a resource person: each respondent's overall (the average of the
    nine SERVQUAL attributes they answered), averaged across respondents. Every one
    of the nine attributes counts equally (unlike the dimension-weighted mean the
    technical /reports page uses), and at these sample sizes a stray harsh rating
    barely moves it. A median was tried but collapses to 7.0 for most people on this
    ceiling-bound data, so the average is what actually tells people apart.
    Returns (value, n_respondents)."""
    valid = r[(~r["is_na"]) & (r["item_id"].isin(_FORM3_ITEMS))]
    if valid.empty:
        return None, 0
    per_resp = valid.groupby("response_id")["value"].mean()
    return float(per_resp.mean()), int(per_resp.size)


def person_card(atoms, person, *, pre=None, rp_event_overalls=None):
    """One person's summary for the People grid: their walk-in (server) score
    and their resource-person (speaker) score, side by side, with a consistency
    read. Returns None if the person has no ratings at all.

    The speaker score is the average of per-respondent overalls across all nine
    attributes equally — not the dimension-weighted mean-of-means the technical
    /reports page uses.

    `pre` is an optional (arta_df, rp_df) pair from a caller that pre-split the
    atoms once for many people (people_grid) — same math, far fewer full scans."""
    if pre is not None:
        a, r = pre
    else:
        a = arta_slice(atoms, person["id"])
        r = rp_slice(atoms, person["id"])
    a = a if a is not None else atoms.iloc[0:0]
    r = r if r is not None else atoms.iloc[0:0]
    arta_m = eng.arta_topbox(a) if _has(a) else None
    rp_value, rp_n = person_overall_score(r) if _has(r) else (None, 0)
    has_arta = arta_m is not None and arta_m.value is not None
    has_rp = rp_value is not None
    if not (has_arta or has_rp):
        return None

    # Consistency: prefer per-event spread as a resource person; else per-month
    # spread as a server. This is what "between sessions" means for each role.
    if has_rp:
        if rp_event_overalls is not None:        # precomputed by people_grid (fast path)
            per_event = rp_event_overalls
        else:
            per_event = [eng.overall_perception(g, eng.DIM_MAP_FORM3).value
                         for _fid, g in r.groupby("form_instance_id")]
            per_event = [v for v in per_event if v is not None]
        cons = consistency(per_event, scale="mean7")
    elif has_arta:
        months = []
        for _k, g in a.groupby(_keys(a, "monthly")):
            m = eng.arta_topbox(g)
            if m.value is not None:
                months.append(m.value)
        cons = consistency(months, scale="pct")
    else:
        cons = consistency([])

    extras = _person_extras(a, r, has_rp, has_arta)
    # "Ratings" = people who rated this person (respondents), NOT item-answers —
    # arta_topbox.n counts item-answers, so derive respondents directly.
    n_ratings = int(rp_n) if has_rp else int(a["response_id"].nunique())
    # Breadth of experience (powers Veteran / Rising star): how many distinct
    # events/sessions this person has been rated across.
    _pslice = r if has_rp else a
    events = int(_pslice["form_instance_id"].nunique()) if _has(_pslice) else 0
    # Recent direction (powers the "on the rise" badge): improving over recent months?
    # The headline metric is the Quality Index for speakers (0-100), the top-box %
    # for walk-in servers — both 0-100, so the trend reads on the "pct" scale.
    _slice = r if has_rp else a
    _scorer = _qi_metric if has_rp else eng.arta_topbox
    _tr = _trend(_last_periods(_slice, "monthly", 6), "monthly", _scorer)
    rising = stability_phrase(_tr, scale="pct")["tone"] == "good"
    _rvals = [p["value"] for p in _tr if p.get("value") is not None]
    rise_mag = (_rvals[-1] - _rvals[0]) if len(_rvals) >= 2 else 0.0   # how big the recent climb is
    # Combined Quality Index (0-100) over all ten satisfaction questions (nine
    # SERVQUAL B-items + the OSQ) — the headline quality metric for speakers. servqual
    # is the familiar /7 mean, osq the /4 overall-quality question — both kept as the
    # index's components for display. ARTA-only servers have no B/C battery.
    if has_rp:
        qi_val, qi_n = eng.quality_index(r)
        _osq = eng.osq_C(r)
        quality = {"index": qi_val, "servqual": rp_value,
                   "osq": (_osq.value if _osq.value is not None else None), "n": qi_n,
                   "shown": (f"{qi_val:.0f}" if qi_val is not None else None),
                   "band": band_index(qi_val)}
    else:
        quality = None
    return {
        "id": person["id"], "name": person["name"],
        "is_internal": person["is_internal"], "org_path": person.get("org_path"),
        "has_photo": person.get("has_photo"), "hidden_public": person.get("hidden_public"),
        "arta": ({"value": arta_m.value, "shown": f"{arta_m.value:.0f}%", "n": arta_m.n,
                  "band": _band_view(arta_m.value, eng.ARTA_BANDS)} if has_arta else None),
        "rp": ({"value": rp_value, "shown": f"{rp_value:.1f}", "n": rp_n,
                "band": band7(rp_value)} if has_rp else None),
        "ratings": n_ratings, "low_n": n_ratings < eng.N_MIN,
        "strongest": extras["strongest"], "topbox": extras["topbox"], "spread": extras["spread"],
        "weakest": extras["weakest"], "confidence": _confidence(n_ratings),
        "dim_values": extras["dim_values"],
        "events": events, "primary": "rp" if has_rp else "arta",
        "rising": rising, "rise": rise_mag,
        "consistency": cons, "quality": quality,
    }


# Positive, earned recognitions shown on a people card. Every badge has THREE levels;
# the level is shown by repeating its single icon 1–3 times (more icons = higher
# award), so we never rely on a colour or a fancy emoji that won't render. Generous
# on purpose — many people deserve a nod. Nothing here is ever negative.
BADGE_DEFS = {
    "most_rated":  {"label": "Most rated", "emoji": "🏅", "cls": "bg-gold",
                    "tip": "Among the most-rated people — lots of feedback to go on."},
    "top_rated":   {"label": "Top rated", "emoji": "⭐", "cls": "bg-blue",
                    "tip": "Among the highest-rated people, with enough ratings to be sure."},
    "proven":      {"label": "Proven", "emoji": "💪", "cls": "bg-violet",
                    "tip": "A high score backed by a large number of ratings — very reliable."},
    "flawless":    {"label": "Flawless", "emoji": "💯", "cls": "bg-amber",
                    "tip": "Everyone — 100% of raters — gave them top marks (6–7)."},
    "favorite":    {"label": "Crowd favorite", "emoji": "❤️", "cls": "bg-rose",
                    "tip": "A large majority of raters gave them top marks (6–7)."},
    "unanimous":   {"label": "Unanimous", "emoji": "🤝", "cls": "bg-teal",
                    "tip": "Raters strongly agree with each other — very little spread."},
    "wellrounded": {"label": "Well-rounded", "emoji": "💎", "cls": "bg-indigo",
                    "tip": "Strong on every dimension — no weak spot."},
    "veteran":     {"label": "Veteran", "emoji": "🎖️", "cls": "bg-stone",
                    "tip": "Rated across many different events — a seasoned presence."},
    "rising_star": {"label": "Rising star", "emoji": "🌟", "cls": "bg-fuchsia",
                    "tip": "New, but already rated highly — one to watch."},
    "rising":      {"label": "On the rise", "emoji": "📈", "cls": "bg-green",
                    "tip": "Scores have been climbing over recent months."},
}
# Display priority when a card earns more than the cap. Reliability/quality first.
_BADGE_ORDER = ["proven", "top_rated", "flawless", "rising_star", "most_rated",
                "veteran", "favorite", "unanimous", "wellrounded", "rising"]
_BADGE_CAP = 3


def _badge(key, level):
    """One badge at a level (1–3). The icon is repeated `level` times."""
    d = BADGE_DEFS[key]
    level = max(1, min(3, int(level)))
    return {"key": key, "label": d["label"], "emoji": d["emoji"], "level": level,
            "icons": d["emoji"] * level, "cls": d["cls"],
            "tip": f"{d['tip']} (level {level} of 3)"}


def _pct_below(value, arr):
    return (sum(1 for x in arr if x < value) / len(arr)) if arr else 0.0


def _tier(value, t1, t2, t3):
    """Map a value to level 1/2/3 by ascending cutoffs, or 0 if below t1."""
    return 3 if value >= t3 else (2 if value >= t2 else (1 if value >= t1 else 0))


def _assign_badges(cards):
    """Attach earned badges across the grid. Each badge has three levels (shown by
    icon count); thresholds are generous so recognition is broad, not just the top
    one or two people."""
    if not cards:
        return
    credible = [c for c in cards if c["ratings"] >= eng.N_MIN]
    ratings_all = sorted(c["ratings"] for c in cards)
    adj_cred = sorted(c["adj"] for c in credible)
    adj_med = adj_cred[len(adj_cred) // 2] if adj_cred else 0   # median fair-score
    order = {k: i for i, k in enumerate(_BADGE_ORDER)}
    for c in cards:
        earned = []
        cred = c["ratings"] >= eng.N_MIN
        tb = c["topbox"] or 0
        # Most rated — by feedback-volume percentile (top 30% / 15% / 5%).
        lvl = _tier(_pct_below(c["ratings"], ratings_all), 0.70, 0.85, 0.95)
        if c["ratings"] > 0 and lvl:
            earned.append(("most_rated", lvl))
        # Top rated — by adjusted-score percentile among the credible (top 33/15/5%).
        if credible and cred:
            lvl = _tier(_pct_below(c["adj"], adj_cred), 0.67, 0.85, 0.95)
            if lvl:
                earned.append(("top_rated", lvl))
        # Proven — an above-median score backed by lots of ratings (reliability). Tier by volume.
        if cred and c["adj"] >= adj_med:
            lvl = _tier(c["ratings"], 50, 200, 800)
            if lvl:
                earned.append(("proven", lvl))
        # Flawless (100% top marks) supersedes Crowd favorite; tier by how many ratings hold it up.
        if cred and tb >= 100:
            earned.append(("flawless", _tier(c["ratings"], eng.N_MIN, 30, 100) or 1))
        elif cred:                                    # Crowd favorite — top-box ≥90 / ≥95 / ≥98.
            lvl = _tier(tb, 90, 95, 98)
            if lvl:
                earned.append(("favorite", lvl))
        # Unanimous — raters agree (low spread). Tier by how tight (SD on the 7-scale).
        sd = (c.get("spread") or {}).get("sd")
        if cred and sd is not None and c["primary"] == "rp" and sd < 0.8:
            lvl = 3 if sd < 0.45 else (2 if sd < 0.6 else 1)
            earned.append(("unanimous", lvl))
        # Well-rounded — no weak dimension. Tier by how high the WEAKEST dimension is.
        wk = c.get("weakest")
        if cred and wk is not None:
            lvl = _tier(wk, 6.0, 6.3, 6.5)
            if lvl:
                earned.append(("wellrounded", lvl))
        # Veteran — breadth of experience. Tier by number of distinct events rated across.
        ev = c.get("events", 0)
        if cred:
            lvl = _tier(ev, 8, 20, 40)
            if lvl:
                earned.append(("veteran", lvl))
        # Rising star — a newcomer (few events) who's already rated highly. Tier by score.
        if cred and ev <= 5 and credible and c["adj"] >= adj_med:
            lvl = _tier(_pct_below(c["adj"], adj_cred), 0.50, 0.75, 0.90)
            earned.append(("rising_star", max(1, lvl)))
        # On the rise — by the size of the recent climb (scale differs by role).
        if c.get("rising") and c["ratings"] >= 5:
            mag = c.get("rise", 0) or 0
            lvl = _tier(mag, 0.1, 0.3, 0.5) if c["primary"] == "rp" else _tier(mag, 2, 5, 10)
            earned.append(("rising", max(1, lvl)))
        earned.sort(key=lambda e: order[e[0]])
        c["badge_keys"] = {k for k, _ in earned}                      # all earned (for filtering)
        c["all_badges"] = [_badge(k, lvl) for k, lvl in earned]       # full, priority order
        c["badges"] = c["all_badges"][:_BADGE_CAP]                    # top few (default display)


def _rp_event_overalls(t3):
    """Every resource person's per-event overall scores in one pass:
    {rp_id: [overall, ...]}, one value per form instance they spoke at. Same
    definition person_card uses for its own fallback (overall_perception over
    DIM_MAP_FORM3), precomputed here so the People grid doesn't recompute it
    once per person.

    Fully vectorized: three grouped means (item → dimension → overall) over the
    whole Form-3 frame at once, instead of an overall_perception() groupby per
    (person, event) — the dominant cost of the People grid at production volume.
    Mathematically identical to overall_perception (overall = mean of present
    dimension-means; a dimension = mean of its present item-means)."""
    out = {}
    if not _has(t3):
        return out
    item2dim = {it: d for d, items in eng.DIM_MAP_FORM3.items() for it in items}
    v = t3[(~t3["is_na"]) & (t3["item_id"].isin(item2dim))]
    if not len(v):
        return out
    item_mean = v.groupby(["rp_id", "form_instance_id", "item_id"], sort=False)["value"].mean()
    im = item_mean.reset_index()
    im["dim"] = im["item_id"].map(item2dim)
    dim_mean = im.groupby(["rp_id", "form_instance_id", "dim"], sort=False)["value"].mean()
    # overall per (rp, event) = mean of that event's dimension-means; sort_index keeps
    # the per-person lists in ascending form_instance_id order (matching the old loop).
    overall = dim_mean.groupby(level=["rp_id", "form_instance_id"], sort=False).mean().sort_index()
    for rp_id, g in overall.groupby(level="rp_id", sort=True):
        if rp_id != rp_id:                            # skip NaN rp_id
            continue
        out[int(rp_id)] = [float(x) for x in g.values]
    return out


def _is_director(person):
    """Mirrors storage.is_bureau_director (kept local — this module works on
    plain dicts already fetched by the caller, never touches storage/DB
    directly). The Director rotates too fast to track individually, so this
    is checked live off position/designation rather than a stored flag that
    would need re-applying on every handover."""
    desig = (person.get("designation") or "").strip().lower()
    posn = (person.get("position") or "").strip().lower()
    return "director" in posn or "director" in desig


def people_grid(atoms, staff, include_hidden=False):
    """Cards for everyone with at least one rating. Hidden people are dropped
    from the public grid unless include_hidden (admin) is set. Each card gets a
    relative 'vs average' read (never a rank)."""
    t1 = atoms[atoms["survey_type"] == 1]
    t3 = atoms[atoms["survey_type"] == 3]
    arta_avg = eng.arta_topbox(t1).value
    # Global priors for the shrinkage: the bureau-wide average of per-respondent
    # overalls for speakers (same basis as each person's score), the top-box % for
    # walk-in. A person's score is pulled toward this when they have few ratings.
    _t3v = t3[(~t3["is_na"]) & (t3["item_id"].isin(_FORM3_ITEMS))] if _has(t3) else t3
    rp_prior = float(_t3v.groupby("response_id")["value"].mean().mean()) if len(_t3v) else None
    # Split once per person instead of masking the full frame per staff member,
    # and precompute every person's per-event overalls in one vectorized pass.
    by_served = {k: g for k, g in t1.groupby("served_by_rp_id")} if _has(t1) else {}
    by_rp = {k: g for k, g in t3.groupby("rp_id")} if _has(t3) else {}
    ev_by_rp = _rp_event_overalls(t3) if _has(t3) else {}
    cards = []
    for p in staff:
        if (p.get("hidden_public") or _is_director(p)) and not include_hidden:
            continue
        card = person_card(atoms, p, pre=(by_served.get(p["id"]), by_rp.get(p["id"])),
                           rp_event_overalls=ev_by_rp.get(p["id"], []))
        if not card:
            continue
        # Shrinkage-adjusted score for fair ranking: pull a person's mean toward the
        # bureau average with weight C (≈ how many ratings it takes to "earn" the raw
        # score), so a 7.0-from-1-rating can't outrank a 6.8-from-200. Same idea as
        # IMDb's weighted rating / an empirical-Bayes posterior mean. Scaled to 0–100
        # so walk-in (%) and speaker (/7) people rank on one axis.
        C = eng.N_MIN
        n = card["ratings"]
        if card["rp"]:
            prior = rp_prior if rp_prior is not None else card["rp"]["value"]
            card["adj"] = (n * card["rp"]["value"] + C * prior) / (n + C) / 7 * 100
        elif card["arta"]:
            prior = arta_avg if arta_avg is not None else card["arta"]["value"]
            card["adj"] = (n * card["arta"]["value"] + C * prior) / (n + C)
        else:
            card["adj"] = 0
        cards.append(card)
    # Distinctive strength: the dimension where each person most beats the bureau
    # average for that dimension — so "Known for" is personal, not the dimension
    # (Assurance) that happens to be highest for almost everyone.
    sums, ns = {}, {}
    for c in cards:
        for name, val in (c.get("dim_values") or {}).items():
            sums[name] = sums.get(name, 0.0) + val
            ns[name] = ns.get(name, 0) + 1
    dim_avg = {k: sums[k] / ns[k] for k in sums}
    for c in cards:
        dv = c.get("dim_values")
        if dv:
            c["strongest"] = max(dv, key=lambda k: dv[k] - dim_avg.get(k, dv[k]))

    _assign_badges(cards)
    # Base order: fair-adjusted score, strongest first. The route re-sorts per the
    # user's chosen sort; this is the stable default/tiebreak.
    cards.sort(key=lambda c: -c.get("adj", 0))
    return cards


def scope_profile(cards, scope_label):
    """A warm, visual collective profile for the people in scope (a division, section,
    or the whole bureau): a personal headline + story, the numbers that matter, a
    score gauge, and a clickable badge showcase. Follows whatever scope is selected."""
    if not cards:
        return None
    n_people = len(cards)
    total_ratings = sum(c["ratings"] for c in cards)
    rp_people = [c for c in cards if c.get("rp")]
    denom = sum(c["ratings"] for c in rp_people)
    # Rating-weighted average score — the scope's typical rated experience.
    avg = (sum(c["rp"]["value"] * c["ratings"] for c in rp_people) / denom) if denom else None
    tbs = [c["topbox"] for c in cards if c["topbox"] is not None]
    avg_tb = round(sum(tbs) / len(tbs)) if tbs else None
    total_badges = sum(len(c.get("badge_keys", ())) for c in cards)
    band = band7(avg) if avg is not None else None

    # Badge showcase: count per badge, in the canonical badge order, biggest first.
    tally = {}
    for c in cards:
        for k in c.get("badge_keys", ()):
            tally[k] = tally.get(k, 0) + 1
    showcase = sorted(
        ({"key": k, "count": v, "emoji": BADGE_DEFS[k]["emoji"],
          "label": BADGE_DEFS[k]["label"], "cls": BADGE_DEFS[k]["cls"]} for k, v in tally.items()),
        key=lambda b: -b["count"])

    # Warm, personal voice — speaks about "our people", excellence + engagement.
    unit = "the bureau" if scope_label.lower().startswith("whole") else scope_label
    who = "person" if n_people == 1 else "people"
    headline = f"Meet the {n_people} {who} behind {unit}."
    story = f"Together they've earned the trust of <b>{total_ratings:,} voices</b>"
    if total_badges:
        story += f" and <b>{total_badges} badges</b>"
    story += "."
    if band:
        story += (f" People rate them <b>{band}</b> — "
                  f"these are the folks who show up and deliver.")

    return {
        "scope": scope_label, "people": n_people, "ratings": total_ratings,
        "avg": (round(avg, 1) if avg is not None else None), "band": band,
        "avg_pct": (round(avg / 7 * 100) if avg is not None else None),
        "avg_topbox": avg_tb, "badges": total_badges,
        "headline": headline, "story": story, "showcase": showcase,
    }


def person_trend(atoms, person, grain):
    """Trend points for the person's primary role (resource person if they have
    speaker ratings, else walk-in server)."""
    r = rp_slice(atoms, person["id"])
    if _has(r):
        return _trend(r, grain, _qi_metric), "rp"          # headline metric = Quality Index (0-100)
    a = arta_slice(atoms, person["id"])
    if _has(a):
        return _trend(a, grain, eng.arta_topbox), "arta"
    return [], None


def person_dimensions(atoms, person):
    """Ranked dimension bars for a resource person (plain names)."""
    r = rp_slice(atoms, person["id"])
    if not _has(r):
        return []
    return _ranked_dimensions(r, eng.DIM_MAP_FORM3)


def person_arta_items(atoms, person):
    """Per-item walk-in breakdown when the person is rated as a server."""
    a = arta_slice(atoms, person["id"])
    if not _has(a):
        return []
    return _arta_items(a)


# Concrete, do-this-next coaching for a resource person's TECHNICAL-ASSISTANCE
# delivery — one diagnosis + a few specific actions per SERVQUAL dimension, in the
# language of running a TA session for LGUs / health units.
DIM_TA = {
    "Reliability": {
        "diagnosis": "Participants felt sessions didn't always deliver what was announced — the scope, "
                     "schedule, or accuracy of the guidance slipped.",
        "actions": [
            "Open with a one-slide agenda and hold to the announced scope and timing.",
            "Verify every figure, citation, and issuance is current before each delivery.",
            "Close by recapping what was promised and confirming it was covered."]},
    "Responsiveness": {
        "diagnosis": "Attendees wanted quicker, fuller answers — questions and on-the-spot needs weren't "
                     "always met during the session.",
        "actions": [
            "Invite questions after each major section, not only at the end.",
            "Note anything you can't answer fully and send a written follow-up within a few days.",
            "For large rooms, bring a co-facilitator to field questions while you present."]},
    "Assurance": {
        "diagnosis": "Confidence in the depth of expertise or the clarity of the guidance could be stronger.",
        "actions": [
            "Lead with your credentials and cite the standards or issuances behind your advice.",
            "Anchor each point in a concrete LGU or field example so it feels proven, not theoretical.",
            "Rehearse the opening — a crisp, confident start earns trust fast."]},
    "Empathy": {
        "diagnosis": "The session could feel more attuned to each participant's setting, constraints, and pace.",
        "actions": [
            "Start by asking about participants' contexts and tailor examples to them.",
            "Check the pace mid-way (“too fast? too slow?”) and adjust.",
            "Acknowledge participants by name or unit when you respond."]},
    "Tangible": {
        "diagnosis": "The slides, handouts, or how the material was presented held the experience back.",
        "actions": [
            "Hand out a clean, shareable reference pack participants can keep.",
            "Simplify slides — fewer words, clearer visuals, readable from the back row.",
            "Test your slides and the AV (projector, sound) before you start."]},
}


def bureau_dims(atoms):
    """Bureau-wide dimension means for resource persons — the yardstick a person's
    own dimensions are measured against in the TA advice."""
    d = atoms[atoms["survey_type"] == 3]
    return {r["raw"]: r["value"] for r in _ranked_dimensions(d, eng.DIM_MAP_FORM3)} if _has(d) else {}


def ta_advice(dims, peer_dims=None, peer_label="the bureau"):
    """Deeper, actionable coaching for a resource person's technical-assistance
    delivery: the dimension with the most room to grow, why it matters, concrete
    steps, an optional second area, and the strength to keep leaning on. `dims` is
    person_dimensions() output (ranked); `peer_dims` is bureau_dims() for context;
    `peer_label` names the benchmark (e.g. a parent division) for unit-level reuse."""
    if not dims or len(dims) < 2:
        return None
    person_avg = sum(d["value"] for d in dims) / len(dims)
    strongest = dims[0]
    # The opportunity must NOT show the same rounded score as the strength — pick the
    # lowest dimension whose displayed score is actually below the top one. If every
    # dimension rounds to the same number the person is evenly strong (handled below).
    lower = [d for d in dims if d["shown"] != strongest["shown"]]
    even = not lower
    weakest = lower[-1] if lower else dims[-1]
    second = lower[-2] if len(lower) >= 2 else None

    def block(d):
        raw = d.get("raw")
        meta = DIM_TA.get(raw, {})
        val, peer = d["value"], (peer_dims or {}).get(raw)
        # A genuine soft spot earns the honest diagnosis; an already-strong "lowest
        # area" gets an encouraging frame — never scold a high performer.
        genuine = val < 5.8 or (peer is not None and val < peer - 0.3)
        diagnosis = meta.get("diagnosis", "") if genuine else (
            "This is your lowest area — still strong, just the dimension with the most "
            "headroom to turn into a signature strength.")
        context = ""
        if peer is not None:
            diff = val - peer
            if diff <= -0.15:
                context = (f"At {d['shown']} of 7 it's about {abs(diff):.1f} below {peer_label}'s "
                           f"{peer:.1f} here — the clearest place to gain ground.")
            elif diff >= 0.15:
                context = (f"At {d['shown']} of 7 you're already above {peer_label}'s {peer:.1f} "
                           f"here — a small push makes it a standout.")
            else:
                context = f"At {d['shown']} of 7 it's right around the {peer_label} norm — steady, with room to lift."
        return {"area": d["name"], "score": d["shown"], "raw": raw,
                "diagnosis": diagnosis, "actions": meta.get("actions", []), "context": context}

    focus = block(weakest)
    focus["even"] = even
    if even:
        # No real weak spot — don't show a score that matches the strength.
        focus["diagnosis"] = ("Your dimensions are remarkably even — there's no single weak spot. "
                              "The area with a touch more headroom to push higher:")
        focus["context"] = ""
    secondary = (block(second) if (not even and second is not None
                 and second is not strongest and second["value"] < person_avg - 0.05) else None)
    keep = (f"Keep leading with “{strongest['name']}” ({strongest['shown']} of 7) — "
            f"it's your anchor, and it's what people already trust you for.")
    return {"focus": focus, "secondary": secondary, "keep": keep, "even": even}


def year_over_year(atoms, person, role):
    """Is this person improving year on year? Returns each year's score plus a plain
    insight comparing the latest full reading with the year before. Uses all-time
    data (it inherently needs more than one year)."""
    slc = rp_slice(atoms, person["id"]) if role == "rp" else arta_slice(atoms, person["id"])
    if not _has(slc):
        return None
    # Headline metric per role: the Quality Index (0-100) for speakers, the top-box %
    # for walk-in servers — both 0-100, so the year-on-year read is on that scale.
    scorer = _qi_metric if role == "rp" else eng.arta_topbox
    pts = [p for p in _trend(slc, "yearly", scorer) if p["value"] is not None]
    pts.sort(key=lambda p: p["key"])
    fmt = (lambda v: f"{v:.0f}%") if role == "arta" else (lambda v: f"{v:.0f}")
    bars = [{"label": p["label"], "value": p["value"], "shown": fmt(p["value"]), "n": p.get("n")} for p in pts]
    if len(pts) < 2:
        return {"bars": bars, "insight": "Not enough years yet to compare — this is the baseline.",
                "tone": "neutral", "delta": None}
    last, prev = pts[-1], pts[-2]
    delta = last["value"] - prev["value"]
    thr = 1.5
    if delta >= thr:
        tone = "good"
        insight = (f"You're improving — up from {fmt(prev['value'])} in {prev['label']} "
                   f"to {fmt(last['value'])} in {last['label']}.")
    elif delta <= -thr:
        tone = "bad"
        insight = (f"A dip this year — {fmt(prev['value'])} in {prev['label']} down to "
                   f"{fmt(last['value'])} in {last['label']}. A small reset usually turns it around.")
    else:
        tone = "neutral"
        insight = (f"Holding steady — {fmt(last['value'])} in {last['label']}, "
                   f"about the same as {prev['label']}.")
    return {"bars": bars, "insight": insight, "tone": tone, "delta": round(delta, 2)}


# Overall-performance composite: blend a resource person's within-group QUALITY
# standing (fair-adjusted score) with their ENGAGEMENT standing (how many events
# they've been rated across). Engagement carries the heavier weight — the bureau
# places a premium on showing up to deliver technical assistance. Both axes are
# percentile ranks within the group, so the blend is scale-free (no need to
# normalise a /7 score against a raw event count).
PERF_W_QUALITY = 0.45
PERF_W_ENGAGEMENT = 0.55

# Engagement blends how many activities/sessions were run (effort / commitment to
# deliver) with how many people rated them (reach / impact). Equal weight — a
# unit or person that both delivers often AND reaches many ranks highest. Volume
# no longer sits inside quality; it lives here.
ENG_W_ACTIVITIES = 0.5
ENG_W_RESPONDENTS = 0.5


def _pctile(values, v):
    """Percentile standing of v within values: share of the group at or below v,
    as 0–100. Ties count as 'at or below' so the top value reads as 100."""
    n = len(values)
    return (sum(1 for x in values if x <= v) / n * 100.0) if n else 0.0


def _quality_index_of(c):
    """The card's combined Quality Index (0-100), or 0 when absent."""
    v = (c.get("quality") or {}).get("index")
    return v if v is not None else 0.0


def _quality_rank_key(c):
    """Sort key for the QUALITY axis — the combined Quality Index (0-100 over all ten
    satisfaction questions: nine SERVQUAL + the OSQ), with a low-sample guard: anyone
    with fewer than N_MIN ratings sorts BELOW every sufficiently-rated peer (so a
    perfect-from-2-ratings can't top a strong-from-500), and within each tier the
    higher index ranks higher. Volume is NOT folded into quality — it lives only on
    the engagement axis, so the quality rank matches the index shown (display == basis)."""
    enough = 1 if c.get("ratings", 0) >= eng.N_MIN else 0
    return (enough, _quality_index_of(c))


def _standing(me, peers):
    """Rank `me` within a peer set on three axes — QUALITY (the combined Quality Index,
    with a low-sample guard), ENGAGEMENT (a 50/50 blend of activities run and people
    reached) and an OVERALL composite that puts a premium on engagement — and attach
    the gap-vs-average stats that make each standing concrete. Assumes me ∈ peers and
    every peer has an `rp` score. Quality ranks on the index shown, so the rank always
    matches the score; volume influences only engagement/overall."""
    n = len(peers)
    # Quality: rank on the combined Quality Index (low-n guarded), described against
    # this group's average and spread. The rank basis IS the displayed index.
    my_key = _quality_rank_key(me)
    q_rank = sum(1 for c in peers if _quality_rank_key(c) > my_key) + 1

    def _qpct(c):
        """Percentile on the quality sort key — coherent with q_rank and reused by
        the overall blend, so 'overall' combines the SAME quality the user sees."""
        k = _quality_rank_key(c)
        return (sum(1 for x in peers if _quality_rank_key(x) <= k) / n * 100.0) if n else 0.0

    q_pct = round(_qpct(me))
    idx_vals = [_quality_index_of(c) for c in peers]
    grp_avg = statistics.mean(idx_vals)
    my_idx = _quality_index_of(me)
    diff = my_idx - grp_avg
    sd = statistics.pstdev(idx_vals) if n >= 2 else 0.0
    z = (diff / sd) if sd > 1e-9 else None
    myq = me.get("quality") or {}
    # Engagement: 50/50 percentile blend of activities run and respondents reached.
    act_vals = [c.get("events", 0) for c in peers]
    resp_vals = [c.get("ratings", 0) for c in peers]

    def _eng_score(c):
        return (ENG_W_ACTIVITIES * _pctile(act_vals, c.get("events", 0))
                + ENG_W_RESPONDENTS * _pctile(resp_vals, c.get("ratings", 0)))

    my_eng = _eng_score(me)
    e_rank = sum(1 for c in peers if _eng_score(c) > my_eng) + 1
    e_pct = round(my_eng)
    # Overall: weighted blend of the two percentile standings (premium on engagement).
    def perf(c):
        return (PERF_W_QUALITY * _qpct(c) + PERF_W_ENGAGEMENT * _eng_score(c))
    perfs = {id(c): perf(c) for c in peers}
    my_perf = perfs[id(me)]
    o_rank = sum(1 for c in peers if perfs[id(c)] > my_perf) + 1
    o_pct = round(sum(1 for c in peers if perfs[id(c)] <= my_perf) / n * 100) if n else 0
    return {
        "n": n,
        # Quality is the combined index (0-100, 1 dp); servqual (/7) and osq (/4) are
        # its components; my_n/low_n expose the sample behind it.
        "quality": {"rank": q_rank, "pct": q_pct, "avg": round(grp_avg, 1),
                    "my": round(my_idx, 1), "diff": round(diff, 1),
                    "servqual": (round(myq["servqual"], 2) if myq.get("servqual") is not None else None),
                    "osq": (round(myq["osq"], 2) if myq.get("osq") is not None else None),
                    "my_n": me.get("ratings", 0), "low_n": me.get("ratings", 0) < eng.N_MIN,
                    "z": (round(z, 1) if z is not None else None)},
        # Engagement carries both counts (activities + respondents) and their peer means;
        # the rank/pct are on the 50/50 blend.
        "engagement": {"rank": e_rank, "pct": e_pct,
                       "acts": me.get("events", 0), "resp": me.get("ratings", 0),
                       "avg_acts": round(statistics.mean(act_vals), 1) if act_vals else 0,
                       "avg_resp": round(statistics.mean(resp_vals), 1) if resp_vals else 0},
        "overall": {"rank": o_rank, "pct": o_pct},
    }


def peer_standing(grid, person_id):
    """How a resource person ranks — on rating quality, on engagement (events
    delivered), and on an overall-performance composite that prizes engagement —
    WITHIN their section and WITHIN the whole bureau, plus the footprint of their
    contribution. Built from the People grid (same fair-adjusted scores), framed to
    encourage, never to shame."""
    me = next((c for c in grid if c["id"] == person_id), None)
    if not me or not me.get("rp"):
        return None
    peers = [c for c in grid if c.get("rp")]
    if not peers:
        return None
    bureau = _standing(me, peers)

    # Section = resource persons sharing this person's org_path. Only a real ranking
    # when there are at least two of them; otherwise the person is the sole rated RP
    # in their unit (or external, with no section at all).
    sect = me.get("org_path")
    sect_peers = [c for c in peers if c.get("org_path") == sect] if sect else []
    sect_name = _short(sect) if sect else None
    section = _standing(me, sect_peers) if (sect and len(sect_peers) >= 2) else None

    # Headline standing reads off the OVERALL (composite) percentile in the bureau,
    # so it reflects both quality and engagement together.
    op = bureau["overall"]["pct"]
    top = max(1, 100 - op)
    if op >= 80:
        standing = (f"Overall, you're among the bureau's strongest — in the top {top}%, "
                    "counting both how you're rated and how often you deliver technical assistance.")
    elif op >= 60:
        standing = (f"Overall, you're in the bureau's upper tier — top {top}% across rating "
                    "quality and engagement combined.")
    elif op >= 40:
        standing = ("Overall, you're right around the middle of the bureau — a solid, steady "
                    "contributor with clear room to climb.")
    else:
        standing = ("Overall, you're early in your climb — every session you deliver lifts both "
                    "your engagement and your standing.")

    # Contribution footprint within the section and the bureau (kept from before):
    # lead with the absolute footprint, only mention a share when it's ≥1%.
    sect_cards = sect_peers if sect_peers else [me]
    sect_ratings = sum(c["ratings"] for c in sect_cards) or me["ratings"]
    bureau_ratings = sum(c["ratings"] for c in peers) or me["ratings"]
    sect_pct = me["ratings"] / sect_ratings * 100 if sect_ratings else 0
    b_pct = me["ratings"] / bureau_ratings * 100 if bureau_ratings else 0
    shares = []
    if sect_pct >= 1 and sect_name:
        shares.append(f"about <b>{round(sect_pct)}%</b> of {sect_name}'s feedback")
    if b_pct >= 1:
        shares.append(f"<b>{round(b_pct)}%</b> of the bureau's")
    _rt, _ev = me["ratings"], me.get("events", 0)
    contribution = (f"You've gathered <b>{_rt:,}</b> rating{'' if _rt == 1 else 's'} "
                    f"across <b>{_ev}</b> event{'' if _ev == 1 else 's'}")
    contribution += (" — " + " and ".join(shares) + ".") if shares else "."

    return {
        "external": not bool(sect), "section_name": sect_name,
        "section_people": len(sect_cards), "section": section, "bureau": bureau,
        "standing": standing, "contribution": contribution,
    }


# ---- shared scorers / shapers -------------------------------------------------

def _last_periods(df, grain, n):
    """Filter to rows in the most recent `n` periods at `grain` — so a micro-trend
    computes 4 months instead of every month in six years of history."""
    if not _has(df):
        return df
    keys = _keys(df, grain)
    # Distinct period-keys first (vectorized), then filter/sort the handful — instead of
    # iterating every row of (potentially years of) history to build the set.
    last = sorted(k for k in keys.unique().tolist() if k is not None and k == k)[-n:]
    return df[keys.isin(last).values]


def _trend(df, grain, scorer):
    out = []
    if not _has(df):
        return out
    # One pass: groupby splits the frame per period (sorted), instead of
    # re-masking the whole frame once per period — same math, far less scanning.
    keys = _keys(df, grain)
    for k, sub in df.groupby(keys.values):
        if k is None or k != k:          # skip NaT periods (bad/blank dates)
            continue
        m = scorer(sub)
        out.append({"key": k, "label": period_label(k, grain),
                    "value": m.value, "n": int(m.n)})
    return out


def _ranked_dimensions(df, dim_map, labels=DIM_LABELS):
    # One groupby over all items, then assemble each dimension from its present items
    # (value = mean of present item-means; n = total valid item-answers) — identical to
    # calling eng.dimension_mean per dimension, but a single scan instead of one boolean
    # filter + groupby per dimension. Hot path for pulse insights/summary + person extras.
    rows = []
    valid = eng.valid_answers(df) if _has(df) else df
    agg = (valid.groupby("item_id", observed=True)["value"].agg(["mean", "count"])
           if _has(valid) and len(valid) else None)
    if agg is None or agg.empty:
        return rows
    means_by_item = agg["mean"]
    count_by_item = agg["count"]
    for dim, items in dim_map.items():
        present = [it for it in items if it in agg.index]
        if not present:
            continue
        value = float(np.mean([float(means_by_item[it]) for it in present]))
        total_n = int(sum(int(count_by_item[it]) for it in present))
        rows.append({"name": labels.get(dim, dim), "raw": dim,
                     "value": value, "shown": f"{value:.1f}",
                     "pct": value / 7 * 100, "n": total_n})
    rows.sort(key=lambda x: -x["value"])
    return rows


def _arta_items(df):
    rows = []
    for it in eng.ARTA_HEADLINE_ITEMS:
        det = eng.arta_item_detail(df, it)
        if det.get("score") is None:
            continue
        rows.append({"item": it, "name": SQD_LABELS.get(it, it),
                     "value": det["score"], "shown": f"{det['score']:.0f}%",
                     "n": det["n"]})
    rows.sort(key=lambda x: -x["value"])
    return rows


# ---- events (Activities view) -------------------------------------------------

def event_overall_map(df, dim_map):
    """Vectorized per-form-instance overall perception — the SAME definition the
    engine uses (overall = mean of dimension-means; dimension = mean of its item
    means), computed in one groupby pass instead of one engine call per event.

    Returns {form_instance_id: overall_value}. This is the hot-path replacement
    for looping eng.overall_perception() over thousands of events."""
    if not _has(df):
        return {}
    valid = eng.valid_answers(df)
    item2dim = {it: d for d, items in dim_map.items() for it in items}
    sub = valid[valid["item_id"].isin(item2dim)]
    if sub.empty:
        return {}
    dim = sub["item_id"].map(item2dim)
    # mean per (event, item) -> mean per (event, dim) -> mean per event
    item_means = sub.groupby([sub["form_instance_id"], sub["item_id"], dim.values], observed=True)["value"].mean()
    item_means.index.names = ["fid", "item", "dim"]
    dim_means = item_means.groupby(["fid", "dim"]).mean()
    overall = dim_means.groupby("fid").mean()
    return overall.to_dict()


def event_value_map(df, item_id):
    """Vectorized per-form-instance mean of one item (e.g. 'A' = expectation)."""
    if not _has(df):
        return {}
    sub = eng.valid_answers(df[df["item_id"] == item_id])
    if sub.empty:
        return {}
    return sub.groupby("form_instance_id")["value"].mean().to_dict()


def _event_group_key(inst):
    """Group an F2 with its F3s: same date + venue + organizer. Bureau events key
    on the lead unit; outside events on the external organizer."""
    venue = (inst["venue"] or "").strip().lower()
    if inst["organizer_external_id"]:
        return ("ext", inst["event_date"], venue, inst["organizer_external_id"])
    return ("bur", inst["event_date"], venue, inst["lead_org_id"])


def build_events(atoms, instances):
    """Group form instances into events and score each from the atoms. Returns a
    list (newest first) of event summaries with an F2 block + per-speaker F3s.

    Performance: the atoms are aggregated ONCE (per form_instance + item sums/counts,
    and per form_instance response sets). Every event's scores are then derived in
    pure Python from those small tables, so there is no per-event pandas work. This
    keeps the Activities view fast even with thousands of instances. The numbers are
    identical to scoring each slice through the engine (verified by equivalence test).
    """
    groups = {}
    for inst in instances:
        groups.setdefault(_event_group_key(inst), []).append(inst)

    # ---- one-time aggregation over all atoms ----
    if len(atoms):
        nona = eng.valid_answers(atoms)
        agg = nona.groupby(["form_instance_id", "item_id"], observed=True)["value"].agg(["sum", "count"])
        fi_item = {}
        for (fi, item), row in zip(agg.index, agg.itertuples(index=False)):
            fi_item.setdefault(fi, {})[item] = (float(row.sum), int(row.count))
        fi_resp = {fi: set(v) for fi, v in
                   atoms.groupby("form_instance_id")["response_id"].agg(set).items()}
    else:
        fi_item, fi_resp = {}, {}

    def _means_counts(ids):
        """Combine per-item (sum,count) across instance ids -> (mean dict, count dict)."""
        acc = {}
        for i in ids:
            for item, (sm, ct) in fi_item.get(i, {}).items():
                a = acc.get(item)
                acc[item] = (sm + a[0], ct + a[1]) if a else (sm, ct)
        means = {it: sm / ct for it, (sm, ct) in acc.items() if ct}
        counts = {it: ct for it, (sm, ct) in acc.items()}
        return means, counts

    def _resp_ids(ids):
        out = set()
        for i in ids:
            out |= fi_resp.get(i, set())
        return out

    def _dim_means(means, counts, dim_map):
        """[(dim, value, n)] for dims that have any answered item — matches
        eng.dimension_mean (dim = mean of present item-means; n = sum of counts)."""
        out = []
        for dim, items in dim_map.items():
            present = [it for it in items if it in means]
            if present:
                val = sum(means[it] for it in present) / len(present)
                n = sum(counts[it] for it in present)
                out.append((dim, val, n))
        return out

    def _overall(means, counts, dim_map):
        dims = _dim_means(means, counts, dim_map)
        if not dims:
            return None
        return sum(d[1] for d in dims) / len(dims)

    def _ranked(means, counts, dim_map, labels=DIM_LABELS):
        rows = [{"name": labels.get(dim, dim), "raw": dim, "value": v,
                 "shown": f"{v:.1f}", "pct": v / 7 * 100, "n": int(n)}
                for dim, v, n in _dim_means(means, counts, dim_map)]
        rows.sort(key=lambda x: -x["value"])
        return rows

    def _signal(means, counts, dim_map, labels=DIM_LABELS, concern=DIM_CONCERN):
        dims = [(d, v) for d, v, _ in _dim_means(means, counts, dim_map)]
        if not dims:
            return None
        dims.sort(key=lambda x: x[1])
        low_dim, low_v = dims[0]
        high_dim, high_v = dims[-1]
        overall = _overall(means, counts, dim_map)
        expc = means.get("A")
        gap_note = ""
        if overall is not None and expc is not None and (overall - expc) < -0.25:
            gap_note = " Overall, the experience landed below what people expected."
        if low_v < 5.5:
            return (f"The weakest area is {concern[low_dim]} "
                    f"(scoring {low_v:.1f} of 7).{gap_note}")
        return (f"\u201c{labels[high_dim]}\u201d is the strongest point "
                f"({high_v:.1f} of 7).{gap_note}")

    events = []
    for key, insts in groups.items():
        f2s = [i for i in insts if i["survey_type"] == 2]
        f3s = [i for i in insts if i["survey_type"] == 3]
        date = insts[0]["event_date"]
        venue = insts[0]["venue"]
        modality = insts[0].get("modality") or "f2f"
        is_ext = key[0] == "ext"
        organizer = (insts[0]["organizer_name"] if is_ext
                     else (insts[0]["lead_name"] or "Bureau"))
        if f2s and f2s[0]["topic"]:
            name = f2s[0]["topic"]
        elif is_ext:
            name = f3s[0]["topic"] if f3s else "Outside engagement"
        else:
            name = "Event on " + date

        all_ids = [i["id"] for i in insts]

        # F2 block (event review)
        f2_block = None
        ranked = []
        gap_sentence = None
        if f2s:
            f2_ids = [i["id"] for i in f2s]
            m2, c2 = _means_counts(f2_ids)
            # Event score uses the event-about dimensions only — Assurance (B6,
            # "handled by knowledgeable and competent people") and Empathy (B7,
            # how clearly things were communicated) read as judgments of the
            # people running it, so they are scored and shown separately
            # (matches the Pulse rule). Caveat worth knowing when reading this:
            # B8 ("caring attention to participants") is also a people-shaped
            # item, but eng.DIM_MAP_FORM2 files it under Tangible, so it counts
            # toward the event score rather than the people split.
            overall_v = _overall(m2, c2, EVENT_DIMS_FORM2)
            ranked = _ranked(m2, c2, EVENT_DIMS_FORM2, EVENT_DIM_LABELS)
            if overall_v is not None:
                osq_v = m2.get("C")
                exp_v = m2.get("A")
                people_map = {k: eng.DIM_MAP_FORM2[k] for k in ("Assurance", "Empathy")}
                people_dims = _ranked(m2, c2, people_map, DIM_LABELS_F2)
                f2_block = {
                    "overall": overall_v, "overall_shown": f"{overall_v:.1f}",
                    "respondents": len(_resp_ids(f2_ids)),
                    "band": band7(overall_v),
                    # The form's own overall-satisfaction question (item C, 1–4).
                    "osq": osq_v, "osq_shown": (f"{osq_v:.1f}" if osq_v is not None else None),
                    "osq_band": _band_view(osq_v, eng.OSQ_BANDS),
                    # Expectation before the event (item A, 1–7).
                    "expectation": exp_v,
                    "expectation_shown": (f"{exp_v:.1f}" if exp_v is not None else None),
                    "signal": _signal(m2, c2, EVENT_DIMS_FORM2, EVENT_DIM_LABELS, EVENT_DIM_CONCERN),
                    "people_dims": people_dims,
                    "people_read": _people_read(people_dims),
                    "read": _event_read(_band_view(osq_v, eng.OSQ_BANDS), osq_v,
                                        overall_v, exp_v, ranked),
                    "journey": _event_journey(exp_v, overall_v, _band_view(osq_v, eng.OSQ_BANDS)),
                }
                gap_sentence = _gap_sentence(m2.get("A"), overall_v)

        # Per-speaker F3s. A resource person can carry more than one F3 form in
        # the SAME event group (e.g. several batches/sessions run on the same
        # date + venue) — the date+venue+organizer grouping key above has no
        # finer-grained way to tell those sessions apart. Group by rp_id FIRST
        # and combine that person's forms with the ordinary combining rule
        # (_means_counts over all their instance ids), so a person appears
        # ONCE per event with one score, not once per session.
        by_rp = {}
        for f3 in f3s:
            by_rp.setdefault(f3["rp_id"], []).append(f3)
        speakers = []
        for rp_id, forms in by_rp.items():
            ids = [f["id"] for f in forms]
            m3, c3 = _means_counts(ids)
            v = _overall(m3, c3, eng.DIM_MAP_FORM3)
            if v is None:
                continue
            exp_v = m3.get("A")
            osq_v = m3.get("C")
            gap = (v - exp_v) if exp_v is not None else None
            topics = [f["topic"] for f in forms if f.get("topic")]
            uniq_topics = list(dict.fromkeys(topics))   # de-dup, keep order
            # Whether this speaker is the bureau Director — the position
            # turns over, so this is read live off position/designation
            # (storage.is_bureau_director's own check) rather than a stored
            # per-person flag. Callers that shouldn't rank/list the Director
            # (e.g. the roster export) filter on this; build_events() itself
            # stays unfiltered so other consumers are unaffected.
            posn = (forms[0].get("rp_position") or "").strip().lower()
            desig = (forms[0].get("rp_designation") or "").strip().lower()
            speakers.append({
                "name": forms[0]["rp_name"] or "Speaker", "topic": "; ".join(uniq_topics),
                "rp_id": rp_id, "hidden": forms[0].get("rp_hidden"),
                "is_director": "director" in posn or "director" in desig,
                "instance_ids": ids,
                "value": v, "shown": f"{v:.1f}", "band": band7(v),
                "respondents": len(_resp_ids(ids)),
                # Per-speaker Overall Service Quality (item C, 1-4) and SERVQUAL
                # gap (dimension average minus expectation A) — same fields and
                # formatting activity_servqual() uses for the whole-activity
                # summary, just scoped to this one resource person's own forms.
                "osq": osq_v, "osq_shown": (f"{osq_v:.2f}" if osq_v is not None else "—"),
                "osq_band": _band_view(osq_v, eng.OSQ_BANDS),
                "gap": gap, "gap_shown": (f"{gap:+.2f}" if gap is not None else "—"),
                "verdict": _servqual_verdict(gap),
            })
        speakers.sort(key=lambda s: -s["value"])

        if not ranked and f3s:
            mf, cf = _means_counts([i["id"] for i in f3s])
            ranked = _ranked(mf, cf, eng.DIM_MAP_FORM3)

        # The card's respondent count/response_ids should match what's actually
        # SCORED and shown for this event. When there's a real Form-2 score
        # (f2_block) — the activity's own review — respondents must be F2-only:
        # folding in incidental Type-3 speaker reviews that happen to share the
        # same date+venue+org purely by grouping-key coincidence silently inflated
        # "N response(s)" next to a score computed from the F2 alone (speakers are
        # rated separately on the People page since the 2026-06-12 decoupling).
        # When there's NO usable F2 score (no F2 forms, or an F2 with zero actual
        # answers), the card falls back to showing a speaker's score instead (see
        # the template's `elif e.speakers` branch) — so respondents falls back to
        # the whole group too, matching whatever's actually displayed.
        resp_scope_ids = [i["id"] for i in f2s] if f2_block else all_ids
        resp_set = _resp_ids(resp_scope_ids)
        respondents = len(resp_set)
        if respondents == 0:
            continue
        # Entry window: the event's forms are managed as one, so read it off the
        # first instance that has any bound set (all-NULL = always open).
        win = next((i for i in insts if i.get("open_at") or i.get("close_at")), None)
        attendance = next((i.get("attendance") for i in insts if i.get("attendance")), None)
        # Multi-day end date (latest across the group's forms; None = single day),
        # and the CLOSED flag = every non-archived form locked to encoding — the same
        # rule as storage.event_is_closed. Both drive the "recently concluded" strip
        # so closing an activity concludes it immediately, regardless of its date.
        end_date = max((i["end_date"] for i in insts if i.get("end_date")), default=None)
        closed = all(i.get("encoding_locked") for i in insts)
        events.append({
            "id": min(all_ids), "name": name, "date": date, "venue": venue,
            "modality": modality,
            "organizer": organizer, "is_external": is_ext, "respondents": respondents,
            "f2": f2_block, "ranked": ranked, "gap_sentence": gap_sentence,
            "speakers": speakers, "response_ids": list(resp_set),
            "instance_ids": all_ids,
            "attendance": attendance,
            "attendance_suspect": any(i.get("attendance_suspect") for i in insts),
            "open_at": win["open_at"] if win else None,
            "close_at": win["close_at"] if win else None,
            "end_date": end_date, "closed": closed,
        })
    events.sort(key=lambda e: e["date"], reverse=True)
    return events


# Per-activity resource-person reporting starts here. Data before this date is too
# messy to break down cleanly per activity, so the per-person engagement list (and
# its drill-down detail page) only surfaces activities on/after it — for BOTH the
# non-bureau "invited / outside" engagements and bureau-led activities.
RP_ENGAGEMENT_SINCE = "2026-06-15"


def rp_activity_engagements(events, rp_id, since=RP_ENGAGEMENT_SINCE):
    """A resource person's per-activity engagements on or after `since`, newest
    first — BOTH invited/outside and bureau-led activities. One row per activity the
    person spoke at, carrying the person's OWN score for that session (not the
    activity aggregate) so each can be opened into its own detail + downloadables.
    Each row is tagged `kind` ('outside' | 'bureau'). Built from build_events()."""
    out = []
    for e in events:
        if (e["date"] or "") < since:
            continue
        sp = next((s for s in e["speakers"] if s["rp_id"] == rp_id), None)
        if not sp:
            continue
        out.append({
            "event_id": e["id"], "name": e["name"], "date": e["date"],
            "venue": e["venue"], "organizer": e["organizer"], "topic": sp["topic"],
            "value": sp["value"], "shown": sp["shown"], "band": sp["band"],
            "respondents": sp["respondents"],
            "is_external": e["is_external"],
            "kind": "outside" if e["is_external"] else "bureau",
        })
    return out


def pooled_summary(atoms):
    """One rolled-up line for the records flagged `pooled` — responses that still
    count in every aggregate (via _LOAD_SQL) but are NOT shown as named events.
    Returns None when there are no pooled responses in the current scope."""
    if not len(atoms) or "pooled" not in atoms.columns:
        return None
    pa = atoms[atoms["pooled"] == 1]
    if not len(pa):
        return None
    f2 = pa[pa["survey_type"] == 2]
    nona = eng.valid_answers(f2)
    overall = None
    if len(nona):
        item_means = nona.groupby("item_id", observed=True)["value"].mean().to_dict()
        dims = []
        for _dim, items in EVENT_DIMS_FORM2.items():   # event-about dims, as on each event row
            present = [it for it in items if it in item_means]
            if present:
                dims.append(sum(item_means[it] for it in present) / len(present))
        if dims:
            overall = sum(dims) / len(dims)
    return {
        "respondents": int(pa["response_id"].nunique()),
        "records": int(pa["form_instance_id"].nunique()),
        "overall": overall,
        "overall_shown": (f"{overall:.1f}" if overall is not None else None),
        "band": (band7(overall) if overall is not None else None),
    }


# =====================================================================
# Per-activity SERVQUAL report — the full scorecard for ONE activity.
# Mirrors the bureau's reference computation exactly (see CSS Reports_reference):
#   • per dimension (all five): perception mean (1–7), gap vs expectation, verdict
#   • TOTAL  = sum of the present dimension means
#   • AVERAGE = mean of the present dimension means
#   • EXPECTATION = item A mean (1–7)
#   • SERVQUAL = AVERAGE − EXPECTATION (the overall gap)
#   • OVERALL SERVICE QUALITY = item C mean (1–4) -> Excellent/Good/Fair/Poor
# Unlike the Activities-list row (which splits Assurance/Empathy out as "the people
# running it"), the report uses the FULL SERVQUAL grouping so the five dimensions
# line up one-for-one with the reference report the bureau already produces.
# =====================================================================

def _servqual_verdict(gap):
    """Standard SERVQUAL read of a perception-minus-expectation gap."""
    gap = eng.finite_number(gap)
    if gap is None:
        return None
    if gap >= 0.10:
        return "Exceeds Expectation"
    if gap <= -0.10:
        return "Below Expectation"
    return "Meets Expectation"


def activity_servqual(atoms, instance_ids):
    """Full SERVQUAL scorecard for one activity's Form-2 review. `instance_ids` is
    the activity's form_instance ids; only the Type-2 (event review) answers are
    scored. Returns None when the slice carries no Form-2 answers."""
    if not len(atoms):
        return None
    df = atoms[(atoms["form_instance_id"].isin(instance_ids)) &
               (atoms["survey_type"] == 2) & (~atoms["is_na"])]
    df = eng.valid_answers(df)
    if not len(df):
        return None
    exp = eng.expectation_A(df).value
    osq = eng.osq_C(df).value
    dims, total, present = [], 0.0, 0
    for dim, items in eng.DIM_MAP_FORM2.items():
        m = eng.dimension_mean(df, items)
        if m.value is None:
            continue
        gap = (m.value - exp) if exp is not None else None
        dims.append({
            "key": dim, "label": dim, "sub": DIM_LABELS_F2.get(dim, ""),
            "value": m.value, "shown": f"{m.value:.2f}", "n": int(m.n),
            "pct": m.value / 7 * 100,
            "gap": gap, "gap_shown": (f"{gap:+.2f}" if gap is not None else "—"),
            "verdict": _servqual_verdict(gap),
        })
        total += m.value
        present += 1
    if not dims:
        return None
    avg = total / present
    servqual = (avg - exp) if exp is not None else None
    return {
        "dims": dims,
        "total_shown": f"{total:.2f}",
        "average": avg, "average_shown": f"{avg:.2f}", "average_band": band7(avg),
        "expectation": exp, "expectation_shown": (f"{exp:.2f}" if exp is not None else "—"),
        "servqual": servqual, "servqual_shown": (f"{servqual:+.2f}" if servqual is not None else "—"),
        "servqual_verdict": _servqual_verdict(servqual),
        "osq": osq, "osq_shown": (f"{osq:.2f}" if osq is not None else "—"),
        "osq_grade": _band_view(osq, eng.OSQ_BANDS),
        "respondents": int(df["response_id"].nunique()),
    }


def activity_benchmark(atoms, instance_ids, scope_label):
    """How one activity compares to the OTHER Form-2 activities run by the same org
    unit (its section — or the bureau when the activity is untagged) in the SAME
    calendar year. Cohort figures only; the per-dimension and overall deltas against
    this activity are computed where both sides are known (the route). Returns None
    when there are no peer activities in that section+year (e.g. the first/only one).

    The cohort key is read from the activity's own Form-2 slice: the `org_path` that
    section-tagging stamped on every form of the event, plus the activity's year. The
    cohort means are rating-weighted (every peer respondent counts once), matching how
    `activity_servqual` scores this activity, so the two are directly comparable."""
    if not len(atoms):
        return None
    mine = atoms[(atoms["form_instance_id"].isin(instance_ids)) &
                 (atoms["survey_type"] == 2) & (~atoms["is_na"])]
    if not len(mine):
        return None
    paths = mine["org_path"].mode()
    dates = mine["event_date"].dropna()
    if not len(paths) or not len(dates):
        return None
    org_path, year = paths.iloc[0], str(dates.iloc[0])[:4]
    pool = atoms[(atoms["survey_type"] == 2) & (~atoms["is_na"]) &
                 (atoms["org_path"].astype("string").str.startswith(org_path, na=False)) &
                 (atoms["event_date"].str.slice(0, 4) == year) &
                 (~atoms["form_instance_id"].isin(instance_ids))]
    if not len(pool):
        return None
    dims, total, present = {}, 0.0, 0
    for dim, items in eng.DIM_MAP_FORM2.items():
        m = eng.dimension_mean(pool, items)
        if m.value is None:
            continue
        dims[dim] = {"mean": m.value, "shown": f"{m.value:.2f}", "pct": m.value / 7 * 100}
        total += m.value
        present += 1
    if not present:
        return None
    avg = total / present
    osq = eng.osq_C(pool).value
    # Short label for tight spots (column header, bar captions): section names read
    # "Section 1 - Local Health System Integration" — keep just the part before " - ".
    short = scope_label.split(" - ")[0].strip() or scope_label
    return {
        "label": scope_label, "short": short, "year": year,
        "peers": int(pool["event_date"].nunique()),       # distinct event dates ≈ activity count
        "respondents": int(pool["response_id"].nunique()),
        "overall": {"mean": avg, "shown": f"{avg:.2f}", "band": band7(avg), "pct": avg / 7 * 100},
        "osq": {"value": osq, "shown": (f"{osq:.2f}" if osq is not None else "—"),
                "band": _band_view(osq, eng.OSQ_BANDS)},
        "dims": dims,
    }


def activity_demographics(captured, manual):
    """Combine demographic counts captured from respondents (sex / affiliation) with
    an optional manual override (for older activities that predate capture). Manual
    counts, when present for a field, take precedence over the captured tallies.
    `captured` and `manual` are each {male,female,doh,nondoh} dicts (any may be None).
    Returns None when there is nothing to show."""
    captured = captured or {}
    manual = manual or {}

    def pick(k):
        mv = manual.get(k)
        return int(mv) if mv not in (None, "") else int(captured.get(k) or 0)

    male, female = pick("male"), pick("female")
    doh, nondoh = pick("doh"), pick("nondoh")
    used_manual = any(manual.get(k) not in (None, "") for k in ("male", "female", "doh", "nondoh"))
    if not (male or female or doh or nondoh):
        return None
    sex_total = male + female
    aff_total = doh + nondoh
    return {
        "male": male, "female": female,
        "female_pct": (female / sex_total * 100 if sex_total else 0),
        "male_pct": (male / sex_total * 100 if sex_total else 0),
        "mf_ratio": (f"{male}:{female}" if sex_total else None),
        "doh": doh, "nondoh": nondoh,
        "doh_pct": (doh / aff_total * 100 if aff_total else 0),
        "nondoh_pct": (nondoh / aff_total * 100 if aff_total else 0),
        "affil_ratio": (f"{doh}:{nondoh}" if aff_total else None),
        "manual": used_manual,
    }


def _gap_sentence(expectation, experience):
    if expectation is None or experience is None:
        return None
    g = experience - expectation
    exp_s, got_s = f"{expectation:.1f}", f"{experience:.1f}"
    if g >= 0.25:
        return (f"People came in expecting about {exp_s} of 7 and came away rating "
                f"the experience {got_s} — it exceeded expectations.")
    if g <= -0.25:
        return (f"People came in expecting about {exp_s} of 7 but came away rating "
                f"the experience {got_s} — it fell short of expectations.")
    return (f"People expected about {exp_s} of 7 and experienced {got_s} — "
            f"right about where they hoped.")


# Event-context dimension wording: the Activities page reads a Form 2 *event*
# review, so it uses the Form 2 labels. Plain aliases — the F2 set is already
# written against the activity's own questions, so there is nothing to override
# here. Kept as named aliases for the build_events call sites.
EVENT_DIM_LABELS = DIM_LABELS_F2
EVENT_DIM_CONCERN = DIM_CONCERN_F2


def _event_read(osq_band, osq_value, perception, expectation, ranked_event):
    """A warm, plain-language read of one event from its Form 2 answers: the
    overall-satisfaction question (item C), the expectation gap, and the standout /
    grow area among the event-about dimensions. Encouraging, never shaming."""
    parts = []
    tone = _tone_for_band(osq_band) if osq_band else _tone_for_band(band7(perception))
    if osq_band:
        warmth = {
            "Excellent": "People walked away genuinely happy with this one",
            "Good": "People came away satisfied",
            "Fair": "People left with a fair, middle-of-the-road impression",
            "Poor": "People left less than satisfied",
        }.get(osq_band, "Here is how people felt about it")
        tail = f" ({osq_value:.1f} of 4)" if osq_value is not None else ""
        parts.append(f"{warmth} — they rated it “{osq_band}” overall{tail}.")
    elif perception is not None:
        parts.append(f"People rated the experience {perception:.1f} of 7 overall.")
    if expectation is not None and perception is not None:
        g = perception - expectation
        if g >= 0.25:
            parts.append("That came in above what they expected walking in — a nice surprise.")
        elif g <= -0.25:
            parts.append("That sat a little below what they had hoped for coming in.")
        else:
            parts.append("That is right about where they expected to land.")
    if ranked_event:
        top = ranked_event[0]
        parts.append(f"Its strongest area was “{top['name']}” at {top['shown']} of 7.")
        low = ranked_event[-1]
        if len(ranked_event) > 1 and low["value"] < 5.8 and low["raw"] != top["raw"]:
            parts.append(f"The area with the most room to grow was “{low['name']}.”")
    return {"tone": tone, "text": " ".join(parts)}


def _event_journey(expectation, perception, osq_band):
    """The signature event visual: a 3-step arc — what people Expected (item A),
    what they Experienced (perception /7), and how Satisfied they were (OSQ band) —
    plus a one-word verdict on the expectation gap. This framing is unique to events
    (Form 2's A→B→C arc) and deliberately unlike the resource-person view."""
    verdict, gap = None, None
    if expectation is not None and perception is not None:
        gap = perception - expectation
        verdict = "beat" if gap >= 0.25 else ("below" if gap <= -0.25 else "met")
    tone = _tone_for_band(osq_band) if osq_band else _tone_for_band(band7(perception))
    return {
        "expected": (round(expectation, 1) if expectation is not None else None),
        "expected_pct": (round(expectation / 7 * 100) if expectation is not None else None),
        "experienced": (round(perception, 1) if perception is not None else None),
        "experienced_pct": (round(perception / 7 * 100) if perception is not None else None),
        "osq_band": osq_band,
        "verdict": verdict,           # beat | met | below | None
        "gap": (round(gap, 1) if gap is not None else None),
        "tone": tone,
        "verdict_label": {"beat": "Beat expectations", "met": "Met expectations",
                          "below": "Below expectations"}.get(verdict),
    }


def _weighted_event_overall(f2_events):
    """Rating-weighted mean event-about perception (/7) across events that carry an
    f2 block — the collective 'how the activities landed' score. None if no respondents.
    Shared by activities_profile + unit_card so the two can't drift."""
    denom = sum(e["respondents"] for e in f2_events)
    if not denom:
        return None
    return sum(e["f2"]["overall"] * e["respondents"] for e in f2_events) / denom


def _event_area_means(f2_events):
    """Average of each event-about dimension across the events (by raw key), strongest
    first: [{name, raw, value, shown}]. Shared by activities_profile + unit_card."""
    acc = {}
    for e in f2_events:
        for r in e.get("ranked", []):
            a = acc.setdefault(r["raw"], {"name": r["name"], "sum": 0.0, "k": 0})
            a["sum"] += r["value"]; a["k"] += 1
    rows = [{"name": a["name"], "raw": raw, "value": a["sum"] / a["k"], "shown": f"{a['sum']/a['k']:.1f}"}
            for raw, a in acc.items() if a["k"]]
    rows.sort(key=lambda x: -x["value"])
    return rows


def _people_area_means(f2_events):
    """Mean of the organizer-conduct dims (Assurance B6 'Courteous organizers' / Empathy
    B7 'Attentive to participants') across a unit's activities, keyed by raw dim — the
    basis for the Gracious-hosts / People-first unit badges."""
    acc = {}
    for e in f2_events:
        for r in (e.get("f2") or {}).get("people_dims", []):
            a = acc.setdefault(r["raw"], {"sum": 0.0, "k": 0})
            a["sum"] += r["value"]; a["k"] += 1
    return {raw: a["sum"] / a["k"] for raw, a in acc.items() if a["k"]}


def activities_profile(events, pooled, scope_label):
    """A warm, event-flavoured collective read for the activities in scope (bureau,
    division, or section). Distinct from the People scope_profile: it speaks about
    what was *run* and how it *landed* — volume, satisfaction, whether it met what
    people expected, and the strongest / weakest event areas across the scope."""
    f2 = [e for e in events if e.get("f2")]
    if not f2:
        return None
    n = len(f2)
    respondents = sum(e["respondents"] for e in f2)
    if pooled and pooled.get("records"):
        respondents += pooled.get("respondents", 0)

    # Rating-weighted average perception across activities + its band.
    avg = _weighted_event_overall(f2) or 0.0
    band = band7(avg)

    # Satisfaction (OSQ) band distribution across activities.
    osq_tally = {}
    for e in f2:
        b = e["f2"].get("osq_band")
        if b:
            osq_tally[b] = osq_tally.get(b, 0) + 1

    # Met-or-beat-expectations rate (only activities that have both figures).
    judged = [e for e in f2 if e["f2"].get("journey") and e["f2"]["journey"]["verdict"]]
    met = sum(1 for e in judged if e["f2"]["journey"]["verdict"] in ("met", "beat"))
    met_pct = round(met / len(judged) * 100) if judged else None

    # Strongest / weakest event-about areas, aggregated across the scope's activities.
    areas = _event_area_means(f2)
    strongest = areas[0] if areas else None
    weakest = areas[-1] if len(areas) > 1 else None

    unit = "The bureau" if scope_label.lower().startswith(("whole", "the whole")) else scope_label
    activities_word = "activity" if n == 1 else "activities"
    headline = f"{unit} ran {n} {activities_word} for {respondents:,} people."
    story = ""
    if band:
        story = f"People rate the experience <b>{band}</b> on average."
    if met_pct is not None:
        story += (f" <b>{met_pct}%</b> met or beat what people expected walking in."
                  if not story else
                  f" And <b>{met_pct}%</b> met or beat what people expected walking in.")

    return {
        "scope": scope_label, "activities": n, "respondents": respondents,
        "avg": round(avg, 1), "band": band, "avg_pct": round(avg / 7 * 100),
        "osq_tally": osq_tally, "met_pct": met_pct,
        "strongest": strongest, "weakest": weakest,
        "headline": headline, "story": story, "tone": _tone_for_band(band),
    }


# =====================================================================
# ORG-UNIT COACHING — the activity analog of the per-person coach page. A section /
# division / bureau is read as ONE entity through the Form-2 activities it owns
# (org_path prefix), then run through the same coach / TA / standing / badge stack.
# Encouraging by construction; a unit is never publicly rank-shamed.
# =====================================================================

# Concrete next-step tips per EVENT dimension (the unit-coach growth focus).
EVENT_DIM_TIP = {
    "Reliability": "tightening the agenda and holding activities to their stated objectives lifts this",
    "Responsiveness": "having organizers visibly on hand to help during sessions is what moves this",
    "Tangible": "a better-prepared venue and cleaner materials are the quickest wins here",
}


# The nine SERVQUAL B-items a Form-2 response is scored on (same codes as Form 3).
_FORM2_ITEMS = [it for items in eng.DIM_MAP_FORM2.values() for it in items]


def unit_overall_score(f2_atoms):
    """A unit's headline activity score by the SAME rule People uses
    (person_overall_score): each respondent's mean across the nine SERVQUAL B-items,
    then averaged across respondents — all nine count equally. Returns (value, n)."""
    valid = f2_atoms[(~f2_atoms["is_na"]) & (f2_atoms["item_id"].isin(_FORM2_ITEMS))]
    if valid.empty:
        return None, 0
    per_resp = valid.groupby("response_id")["value"].mean()
    return float(per_resp.mean()), int(per_resp.size)


def _form2_prior(atoms):
    """Bureau-wide mean of per-respondent nine-item Form-2 overalls — the shrinkage
    prior a unit's score is pulled toward (the volume premium, mirroring people_grid)."""
    f2 = atoms[atoms["survey_type"] == 2]
    v = f2[(~f2["is_na"]) & (f2["item_id"].isin(_FORM2_ITEMS))] if _has(f2) else f2
    return float(v.groupby("response_id")["value"].mean().mean()) if len(v) else None


def unit_card(atoms, unit, instances=None, *, pre_events=None, prior=None):
    """Collective ACTIVITY summary for one org unit (the Form-2 events it owns) — the
    activity analog of person_card. Returns None if the unit has run no rated activity.
    Keys deliberately mirror person_card (rp/ratings/adj/events/topbox/dim_values/…) so
    the badge + standing stack reuses them unchanged. The headline score uses People's
    rule (nine equal-weight B-items) and a shrinkage-adjusted `adj` (the volume premium),
    so a few-activity unit can't outrank a high-volume one on a hair-higher raw mean.
    `pre_events` is the unit's already-built F2 events (route fast path)."""
    u_atoms = eng.scope(atoms, org_prefix=unit["path"] or None)
    if pre_events is not None:
        f2 = pre_events
    else:
        f2 = [e for e in build_events(u_atoms, instances or []) if e.get("f2")]
    f2_atoms = u_atoms[u_atoms["survey_type"] == 2]
    overall, respondents = unit_overall_score(f2_atoms)    # People's nine-item rule
    if not f2 or overall is None:
        return None
    # Shrinkage-adjusted score for fair ranking (empirical-Bayes; same C and basis as
    # people_grid) — pulls a thin unit toward the bureau mean so volume is rewarded.
    C = eng.N_MIN
    pr = prior if prior is not None else _form2_prior(atoms)
    adj = ((respondents * overall + C * pr) / (respondents + C) / 7 * 100
           if pr is not None else overall / 7 * 100)
    areas = _event_area_means(f2)                  # ranked event dims (breakdown + coach)
    dim_values = {r["raw"]: r["value"] for r in areas}
    # OSQ "top band" share — activities people rated Good/Excellent overall (badges).
    osq_known = [e for e in f2 if e["f2"].get("osq_band")]
    topbox = (round(sum(1 for e in osq_known if e["f2"]["osq_band"] in ("Excellent", "Good"))
                    / len(osq_known) * 100) if osq_known else None)
    # Met-or-beat expectations across activities that have both figures.
    judged = [e for e in f2 if e["f2"].get("journey") and e["f2"]["journey"]["verdict"]]
    met_pct = (round(sum(1 for e in judged if e["f2"]["journey"]["verdict"] in ("met", "beat"))
                     / len(judged) * 100) if judged else None)
    osq_vals = [e["f2"]["osq"] for e in f2 if e["f2"].get("osq") is not None]
    osq = (sum(osq_vals) / len(osq_vals)) if osq_vals else None
    # Combined Quality Index (0-100) over all ten satisfaction questions (nine
    # SERVQUAL B-items + the OSQ), per-respondent — the quality axis basis. servqual
    # (/7) and osq (/4, per-respondent mean) are kept as its display components.
    qi_val, qi_n = eng.quality_index(f2_atoms)
    _osq_c = eng.osq_C(f2_atoms)
    quality = {"index": qi_val, "servqual": overall,
               "osq": (_osq_c.value if _osq_c.value is not None else None), "n": qi_n,
               "shown": (f"{qi_val:.0f}" if qi_val is not None else None),
               "band": band_index(qi_val)}
    # Cross-ACTIVITY consistency (spread of per-event overalls — not per respondent).
    per_event = [e["f2"]["overall"] for e in f2 if e["f2"].get("overall") is not None]
    cons = consistency(per_event, scale="mean7")
    sd = (statistics.pstdev(per_event) if len(per_event) >= 2 else None)
    # Recent momentum: monthly trend of the unit's Quality Index (the headline metric).
    _tr = _trend(_last_periods(f2_atoms, "monthly", 6), "monthly", _qi_metric)
    rising = stability_phrase(_tr, scale="pct")["tone"] == "good"
    _rv = [p["value"] for p in _tr if p.get("value") is not None]
    rise_mag = (_rv[-1] - _rv[0]) if len(_rv) >= 2 else 0.0
    return {
        "path": unit["path"], "name": unit["name"], "level": unit["level"],
        "short": _short(unit["path"]) or unit["name"],
        "events": len(f2), "respondents": respondents,
        "rp": {"value": overall, "shown": f"{overall:.1f}", "n": respondents, "band": band7(overall)},
        "overall": overall, "band": band7(overall), "avg_pct": round(overall / 7 * 100),
        "topbox": topbox, "met_pct": met_pct,
        "osq": osq, "osq_band": _band_view(osq, eng.OSQ_BANDS),
        "dim_values": dim_values, "areas": areas,
        "people_dim_values": _people_area_means(f2),   # Assurance/Empathy (organizer conduct)
        "strongest": (areas[0]["name"] if areas else None),
        "weakest": (areas[-1]["value"] if areas else None),
        "spread": {"sd": (round(sd, 2) if sd is not None else None)},
        "consistency": cons, "rising": rising, "rise": rise_mag,
        "ratings": respondents, "low_n": respondents < eng.N_MIN,
        "primary": "rp", "adj": adj, "quality": quality,
    }


def unit_coach(card, trend, breakdown):
    """Collective coach read for an org unit's activities — the activity analog of
    coach_notes, in a 'this unit's activities' voice. Same return shape so the coach
    panel markup is reused verbatim. Encouraging, never shaming."""
    short = card["short"]
    sp = stability_phrase(trend, "pct")          # trend is the 0-100 Quality Index
    cons = card.get("consistency") or {}
    strongest = breakdown[0] if breakdown else None
    weakest = breakdown[-1] if breakdown and len(breakdown) > 1 else None
    met = card.get("met_pct")
    praise, focus = [], []

    if strongest:
        praise.append(f"“{strongest['name']}” is this unit's strongest area ({strongest['shown']} of 7).")
    if sp["tone"] == "good":
        praise.append("Activity ratings have been climbing lately — real momentum.")
    if met is not None and met >= 80:
        praise.append(f"{met}% of its activities met or beat what people expected walking in.")
    if cons.get("stable"):
        praise.append("The experience is consistent from one activity to the next — people know what to expect.")
    if not praise:
        praise.append("The unit is running rated activities — that's the foundation to build on.")

    if weakest and weakest is not strongest:
        tip = EVENT_DIM_TIP.get(weakest.get("raw"), "")
        line = f"“{weakest['name']}” has the most room to grow ({weakest['shown']} of 7)"
        focus.append(line + (f" — {tip}." if tip else "."))
    if cons.get("known") and not cons.get("stable"):
        focus.append("Ratings swing between activities — comparing the best- and lowest-rated ones often "
                     "shows what made the difference.")
    if sp["tone"] == "bad" and "inconsistent" not in sp["phrase"].lower():
        focus.append("Activity scores have dipped a little lately — a small reset on the basics usually turns it around.")

    if sp["tone"] == "good":
        tone, headline = "celebrate", f"{short}'s activities are on a strong roll."
        motivation = "Keep doing what's working — it's clearly landing with people."
    elif met is not None and met >= 80 and cons.get("stable"):
        tone, headline = "celebrate", f"{short} sets a standard worth modelling."
        motivation = "A dependable, high-quality run of activities — thank you for the bar you set."
    elif sp["tone"] == "bad":
        tone, headline = "support", f"{short}, let's steady the run of activities."
        motivation = "Every unit hits tougher stretches; the scores have been strong before and are within reach again."
    elif cons.get("known") and not cons.get("stable"):
        tone, headline = "steady", f"{short}'s best activities are excellent — let's make it every time."
        motivation = "The high notes are already there; the goal now is hitting them consistently."
    else:
        tone, headline = "encourage", f"{short} is doing well, with clear room to grow."
        motivation = "Solid work — one focused nudge lifts the whole experience."

    return {"first": short, "headline": headline, "praise": praise, "focus": focus,
            "motivation": motivation, "tone": tone, "trend_read": sp["phrase"], "comparison": None}


def unit_event_dims(atoms, org_prefix):
    """EVENT_DIMS_FORM2 means for a scope — the benchmark a unit's TA advice is read
    against (analog of bureau_dims, but event-about dims, scoped to a parent unit)."""
    d = eng.scope(atoms, org_prefix=org_prefix or None, survey_type=2)
    return ({r["raw"]: r["value"] for r in _ranked_dimensions(d, EVENT_DIMS_FORM2, EVENT_DIM_LABELS)}
            if _has(d) else {})


def unit_ta_advice(card, parent_dims, peer_label="the bureau"):
    """Activity TA advice for a unit — reuses ta_advice with the event dims and the
    parent unit's dims (division for a section, bureau for a division) as benchmark."""
    dv = card.get("dim_values") or {}
    if len(dv) < 2:
        return None
    dims = [{"name": EVENT_DIM_LABELS.get(raw, raw), "raw": raw, "value": v, "shown": f"{v:.1f}"}
            for raw, v in sorted(dv.items(), key=lambda kv: -kv[1])]
    return ta_advice(dims, parent_dims or None, peer_label=peer_label)


def unit_standing(card, siblings, sibling_kind):
    """Rank a unit against its siblings (sections-vs-sections, divisions-vs-divisions)
    on activity quality + engagement (activities run). None when <2 peers. Reuses
    _standing; the prose never rank-shames a unit."""
    peers = [c for c in siblings if c and c.get("rp")]
    if len(peers) < 2 or not any(c["path"] == card["path"] for c in peers):
        return None
    me = next(c for c in peers if c["path"] == card["path"])
    grp = _standing(me, peers)
    # Unit cohorts are small (a few sections / two divisions), so a percentile reads
    # oddly ("top 1%" of 3). Speak in rank-of-N instead — clearer and still encouraging.
    rank, n = grp["overall"]["rank"], grp["n"]
    if rank == 1:
        standing = (f"Among {sibling_kind}, this unit's activities rank highest — #1 of {n}, blending "
                    "how they're rated with how many it runs.")
    elif rank <= max(1, round(n / 3)):
        standing = (f"Among {sibling_kind}, this unit is one of the strongest — #{rank} of {n} on "
                    "rating quality and activity volume combined.")
    elif rank <= round(n * 2 / 3):
        standing = (f"Among {sibling_kind}, this unit sits around the middle — #{rank} of {n}, a steady "
                    "contributor with clear room to climb.")
    else:
        standing = (f"Among {sibling_kind}, this unit is early in its climb — every activity it runs "
                    f"lifts its standing among the {n}.")
    return {"group": grp, "sibling_kind": sibling_kind, "standing": standing}


def unit_year_over_year(atoms, org_prefix):
    """Year-on-year of a unit's activity Quality Index (0-100, the headline metric).
    Same {bars,insight,tone,delta} shape as year_over_year, so the panel is reused."""
    slc = eng.scope(atoms, org_prefix=org_prefix or None, survey_type=2)
    if not _has(slc):
        return None
    pts = [p for p in _trend(slc, "yearly", _qi_metric) if p["value"] is not None]
    pts.sort(key=lambda p: p["key"])
    fmt = lambda v: f"{v:.0f}"
    bars = [{"label": p["label"], "value": p["value"], "shown": fmt(p["value"]), "n": p.get("n")} for p in pts]
    if len(pts) < 2:
        return {"bars": bars, "insight": "Not enough years yet to compare — this is the baseline.",
                "tone": "neutral", "delta": None}
    last, prev = pts[-1], pts[-2]
    delta = last["value"] - prev["value"]
    if delta >= 1.5:
        tone = "good"
        insight = (f"The unit's activities are improving — up from {fmt(prev['value'])} in {prev['label']} "
                   f"to {fmt(last['value'])} in {last['label']}.")
    elif delta <= -1.5:
        tone = "bad"
        insight = (f"A dip this year — {fmt(prev['value'])} in {prev['label']} down to {fmt(last['value'])} "
                   f"in {last['label']}. A small reset usually turns it around.")
    else:
        tone = "neutral"
        insight = (f"Holding steady — {fmt(last['value'])} in {last['label']}, about the same as {prev['label']}.")
    return {"bars": bars, "insight": insight, "tone": tone, "delta": round(delta, 2)}


# UNIT badges — a DISTINCT set from the People badges, grounded in the Form-2
# questions an activity is scored on (OSQ satisfaction, the expectation gap, and the
# event- + organizer-conduct dimensions) plus how much a unit runs. Positive-only.
# Three-level icon-count tiers (more icons = higher), except the singular Pacesetter.
UNIT_BADGE_DEFS = {
    "pacesetter":    {"label": "Pacesetter", "emoji": "🏆", "cls": "bg-gold",
                      "tip": "Top overall standing among its sibling units — quality and how much it runs, combined."},
    "crowd_pleaser": {"label": "Crowd-pleaser", "emoji": "😊", "cls": "bg-rose",
                      "tip": "Its activities are rated highly satisfying overall."},
    "over_delivers": {"label": "Over-delivers", "emoji": "🎯", "cls": "bg-violet",
                      "tip": "Most of its activities beat or met what people expected walking in."},
    "well_run":      {"label": "Well-run all-round", "emoji": "✅", "cls": "bg-indigo",
                      "tip": "Strong on every event area — no weak spot."},
    "gracious":      {"label": "Gracious hosts", "emoji": "🙏", "cls": "bg-amber",
                      "tip": "Its organizers are rated courteous and professional."},
    "people_first":  {"label": "People-first", "emoji": "💗", "cls": "bg-fuchsia",
                      "tip": "Attentive to participants' needs."},
    "prolific":      {"label": "Prolific", "emoji": "📅", "cls": "bg-stone",
                      "tip": "Runs a high volume of activities."},
    "wide_reach":    {"label": "Wide reach", "emoji": "📣", "cls": "bg-blue",
                      "tip": "Reaches a large audience across its activities."},
    "steady_hand":   {"label": "Steady hand", "emoji": "⚓", "cls": "bg-teal",
                      "tip": "A consistent experience from one activity to the next."},
    "momentum":      {"label": "Gaining momentum", "emoji": "🚀", "cls": "bg-green",
                      "tip": "Activity ratings have been climbing recently."},
}
_UNIT_BADGE_ORDER = ["pacesetter", "crowd_pleaser", "over_delivers", "well_run", "gracious",
                     "people_first", "prolific", "wide_reach", "steady_hand", "momentum"]
_UNIT_SINGLE = {"pacesetter"}            # singular distinctions (no 1–3 level)
_UNIT_BADGE_CAP = 4


def _unit_badge(key, level):
    """One unit badge. Most tier 1–3 by icon count; singular badges show one icon."""
    d = UNIT_BADGE_DEFS[key]
    single = key in _UNIT_SINGLE
    level = 1 if single else max(1, min(3, int(level)))
    return {"key": key, "label": d["label"], "emoji": d["emoji"], "level": level,
            "icons": d["emoji"] * level, "cls": d["cls"],
            "tip": d["tip"] if single else f"{d['tip']} (level {level} of 3)"}


def assign_unit_badges(cards):
    """Attach the UNIT badge set (UNIT_BADGE_DEFS) — activity-flavoured and grounded in
    Form 2, deliberately distinct from the People badges. `pacesetter` ranks WITHIN the
    passed sibling cohort (sections-vs-sections, divisions-vs-divisions); the rest are
    absolute Form-2 thresholds. Gated on credibility; positive-only, never shaming."""
    cards = [c for c in cards if c]
    if not cards:
        return
    order = {k: i for i, k in enumerate(_UNIT_BADGE_ORDER)}
    # Overall composite (quality + activity volume, percentile-blended) -> Pacesetter.
    adj_vals = [c["adj"] for c in cards]
    ev_vals = [c.get("events", 0) for c in cards]

    def _perf(c):
        return (PERF_W_QUALITY * _pctile(adj_vals, c["adj"])
                + PERF_W_ENGAGEMENT * _pctile(ev_vals, c.get("events", 0)))
    perfs = {id(c): _perf(c) for c in cards}
    top_perf = max(perfs.values()) if perfs else 0.0
    credible_cohort = sum(1 for c in cards if c["ratings"] >= eng.N_MIN)

    for c in cards:
        earned = []
        if c["ratings"] < eng.N_MIN:                    # too thin to badge
            c["badge_keys"], c["all_badges"], c["badges"] = set(), [], []
            continue
        # Pacesetter — cohort leader on the overall composite (needs ≥2 credible peers).
        if credible_cohort >= 2 and perfs[id(c)] >= top_perf - 1e-9:
            earned.append(("pacesetter", 1))
        # Crowd-pleaser — OSQ (item C) top-box share across activities.
        lvl = _tier(c.get("topbox") or 0, 85, 93, 98)
        if lvl:
            earned.append(("crowd_pleaser", lvl))
        # Over-delivers — share of activities that met/beat expectations (item A -> experience).
        if c.get("met_pct") is not None:
            lvl = _tier(c["met_pct"], 80, 90, 97)
            if lvl:
                earned.append(("over_delivers", lvl))
        # Well-run all-round — the weakest event dimension is still high.
        wk = c.get("weakest")
        if wk is not None:
            lvl = _tier(wk, 6.0, 6.3, 6.5)
            if lvl:
                earned.append(("well_run", lvl))
        # Gracious hosts / People-first — the organizer-conduct dims (B6 / B7).
        pdv = c.get("people_dim_values") or {}
        if pdv.get("Assurance") is not None:
            lvl = _tier(pdv["Assurance"], 6.2, 6.5, 6.7)
            if lvl:
                earned.append(("gracious", lvl))
        if pdv.get("Empathy") is not None:
            lvl = _tier(pdv["Empathy"], 6.2, 6.5, 6.7)
            if lvl:
                earned.append(("people_first", lvl))
        # Prolific — volume of activities run.
        lvl = _tier(c.get("events", 0), 8, 20, 40)
        if lvl:
            earned.append(("prolific", lvl))
        # Wide reach — participants reached.
        lvl = _tier(c.get("respondents", 0), 500, 2000, 6000)
        if lvl:
            earned.append(("wide_reach", lvl))
        # Steady hand — low spread across activities (lower SD = higher level).
        sd = (c.get("spread") or {}).get("sd")
        if sd is not None:
            lvl = 3 if sd < 0.30 else (2 if sd < 0.45 else (1 if sd < 0.60 else 0))
            if lvl:
                earned.append(("steady_hand", lvl))
        # Gaining momentum — a real recent climb.
        if c.get("rising"):
            earned.append(("momentum", _tier(c.get("rise", 0) or 0, 0.1, 0.3, 0.5) or 1))
        earned.sort(key=lambda e: order[e[0]])
        c["badge_keys"] = {k for k, _ in earned}
        c["all_badges"] = [_unit_badge(k, lvl) for k, lvl in earned]
        c["badges"] = c["all_badges"][:_UNIT_BADGE_CAP]


def unit_badge_legend():
    """Ordered [{key,label,emoji,cls,tip}] for the Teams badge legend (all unit badges,
    in display-priority order)."""
    return [dict(key=k, **UNIT_BADGE_DEFS[k]) for k in _UNIT_BADGE_ORDER]


def _people_read(people_dims):
    """A warm one-liner about how the people running the event came across —
    built from the two person-about dimensions (Assurance + Empathy) that the
    event score deliberately leaves out. Returns None when neither was answered."""
    if not people_dims:
        return None
    avg = sum(d["value"] for d in people_dims) / len(people_dims)
    band = band7(avg)
    lead = {
        "Excellent": "came across as warm, sure-footed, and easy to trust",
        "Good": "came across as knowledgeable and caring",
        "Fair": "made a mixed personal impression",
        "Poor": "have room to connect more warmly with the room",
    }.get(band, None)
    return {"avg": avg, "shown": f"{avg:.1f}", "band": band, "tone": _tone_for_band(band),
            "text": (f"The people who ran it {lead} ({avg:.1f} of 7)." if lead else None)}


# ---- pulse + trends -----------------------------------------------------------

def pulse_tile(atoms, survey_type):
    """A vital-sign tile for one survey type: headline, band, micro-trend (last 4
    periods, monthly), and a plain-language signal phrase."""
    df = atoms[atoms["survey_type"] == survey_type]
    if not _has(df):
        return {"survey_type": survey_type, "title": survey_title(survey_type),
                "has_data": False}

    recent = _last_periods(df, "monthly", 4)         # micro-trend only needs 4 months
    respondents = int(df["response_id"].nunique())
    flags = ["low n"] if respondents < eng.N_MIN else []
    if survey_type == 1:
        m = eng.arta_topbox(df)
        value = m.value
        headline = f"{m.value:.0f}%" if m.value is not None else "—"
        band = _band_view(m.value, eng.ARTA_BANDS)
        micro = _trend(recent, "monthly", eng.arta_topbox)
        signal = arta_signal(df)
        scale = "pct"; unit = "% positive"
        flags = list(m.flags)
    else:
        dim_map = _pulse_dim_map(survey_type)        # event-only dims for activities
        im = frame_item_means(df)                    # one groupby for headline + signal
        value = frame_overall(dim_map, im)
        headline = f"{value:.1f}" if value is not None else "—"
        band = band7(value)
        micro = _trend(recent, "monthly", lambda d: eng.overall_perception(d, dim_map))
        signal = servqual_signal(df, dim_map, item_means=im,
                                 labels=dim_labels(survey_type), concern=dim_concern(survey_type))
        scale = "mean7"; unit = "of 7"

    micro = micro[-4:]
    tone = _tone_for_band(band)
    spark = _spark_points(micro, scale)
    delta = _spark_delta(micro, scale)
    return {
        "survey_type": survey_type, "title": survey_title(survey_type),
        "has_data": value is not None, "headline": headline, "unit": unit,
        "band": band, "tone": tone, "respondents": respondents,
        "micro": micro, "micro_spark": spark["poly"], "micro_pts": spark["pts"],
        "micro_delta_text": delta["text"], "micro_delta_tone": delta["tone"],
        "signal": signal, "flags": flags,
    }


def _spark_delta(points, scale):
    """A plain-language one-liner about how the micro-trend moved from its first to
    its last month — the 'insight' under a Pulse sparkline. Higher is better for both
    metrics, so a rise reads good and a fall reads bad; tiny wiggles read as steady."""
    pts_in = [p for p in points if p["value"] is not None]
    if len(pts_in) < 2:
        return {"text": None, "tone": "neutral"}
    first, last = pts_in[0], pts_in[-1]
    diff = last["value"] - first["value"]
    since = first["label"]
    if scale == "pct":                       # whole-number percentage points
        thresh, mag = 1.0, f"{abs(diff):.0f} point{'s' if abs(diff) >= 1.5 else ''}"
    else:                                    # mean out of 7 — one decimal
        thresh, mag = 0.1, f"{abs(diff):.1f}"
    if diff >= thresh:
        return {"text": f"▲ Up {mag} since {since}", "tone": "good"}
    if diff <= -thresh:
        return {"text": f"▼ Down {mag} since {since}", "tone": "bad"}
    return {"text": f"Holding steady since {since}", "tone": "neutral"}


def _tone_for_band(band):
    return {"Outstanding": "good", "Satisfactory": "good", "Excellent": "good",
            "Good": "good", "Fair": "mid", "Poor": "bad",
            "Needs Improvement": "bad"}.get(band, "neutral")


def _spark_points(points, scale):
    """Tiny normalized sparkline (0–100 viewBox): a polyline string plus the
    per-point coords + labels so the template can attach hover tooltips."""
    pts_in = [p for p in points if p["value"] is not None]
    if len(pts_in) < 2:
        return {"poly": None, "pts": []}
    vals = [p["value"] for p in pts_in]
    lo, hi = min(vals), max(vals)
    rng = (hi - lo) or 1.0
    coords, pts, n = [], [], len(pts_in)
    for i, p in enumerate(pts_in):
        v = p["value"]
        x = i / (n - 1) * 100
        y = 100 - (v - lo) / rng * 100
        coords.append(f"{x:.1f},{y:.1f}")
        shown = f"{v:.0f}%" if scale == "pct" else f"{v:.1f}"
        short = (p["label"].split(" ")[0][:3] if p.get("label") else "")
        pts.append({"x": round(x, 1), "y": round(y, 1), "label": p["label"],
                    "short": short, "shown": shown, "n": p.get("n")})
    return {"poly": " ".join(coords), "pts": pts}


# =====================================================================
# Office Connect landing-page geometry. Same contract as _svg_geom/_count_geom:
# every number the template needs is computed HERE, so the markup only draws the
# strings it is handed. Neither emits a colour — callers pass semantic tone
# tokens ("green"/"accent"/"amber"/"red"/"soft") that the template maps to CSS
# custom properties once, which is what keeps 3 themes x 6 accents working.
# =====================================================================

def ring_geom(pct, r=18, sw=4):
    """stroke-dasharray geometry for a progress ring (a person's hours used, a
    team's filed share). `dash`/`gap` are the two halves of the dasharray; the
    circle is drawn rotated -90deg by CSS so it starts at twelve o'clock."""
    pct = 0.0 if pct is None else float(pct)
    frac = min(100.0, max(0.0, pct)) / 100.0
    circ = 2 * math.pi * r
    return {"size": 2 * (r + sw), "cx": r + sw, "cy": r + sw, "r": r, "sw": sw,
            "circ": round(circ, 2), "dash": round(circ * frac, 2),
            "gap": round(circ * (1 - frac), 2), "pct": round(pct)}


def bars_geom(totals, headcount, *, thin_at=1):
    """Stacked Mon-Fri columns for work-arrangement coverage.

    `totals` is work_arrangement_period_summary's list of
    {idx, name, onsite, offsite, empty_sections}. Stacked rather than grouped so
    every bar is the same height (= headcount) and the eye reads the ON-SITE
    FRACTION directly instead of comparing two free-floating bars.

    A column at or below `thin_at` on-site turns amber, and zero turns red — the
    Friday problem, visible without reading a number. Returns the coordinates
    plus the aria label and the `chart_table` rows, so a caller never has to
    re-derive the numbers for the screen-reader fallback."""
    W, H, padl, padr, padt, padb = 460, 190, 34, 12, 10, 34
    plotw, ploth = W - padl - padr, H - padt - padb
    axis_y = padt + ploth
    ymax = max(1, headcount or 0)
    n = len(totals) or 1
    slot = plotw / n
    bw = min(28.0, slot * 0.55)
    bars, rows = [], []
    for i, t in enumerate(totals):
        onsite, offsite = t.get("onsite", 0), t.get("offsite", 0)
        x = padl + slot * i + (slot - bw) / 2
        h_on = ploth * (onsite / ymax)
        h_off = ploth * (offsite / ymax)
        tone = "green" if onsite > thin_at else ("amber" if onsite else "red")
        empty = t.get("empty_sections") or []
        bars.append({
            "idx": t.get("idx", i), "name": t["name"], "short": t["name"][:3],
            "x": round(x, 1), "w": round(bw, 1), "label_x": round(x + bw / 2, 1),
            "onsite": {"n": onsite, "y": round(axis_y - h_on, 1),
                       "h": round(h_on, 1), "tone": tone},
            "offsite": {"n": offsite, "y": round(axis_y - h_on - h_off, 1),
                        "h": round(h_off, 1), "tone": "soft"},
            "thin": onsite <= thin_at, "empty_sections": empty,
        })
        rows.append([t["name"], str(onsite), str(offsite), ", ".join(empty) or "—"])
    grid = [{"y": round(axis_y - ploth * f, 1), "label": str(round(ymax * f))}
            for f in (0, 0.5, 1)]
    thinnest = min(bars, key=lambda b: b["onsite"]["n"]) if bars else None
    label = "; ".join(f"{b['name']} {b['onsite']['n']} of {ymax}" for b in bars)
    return {
        "W": W, "H": H, "padl": padl, "axis_y": round(axis_y, 1), "ymax": ymax,
        "bars": bars, "grid": grid,
        "thinnest": ({"name": thinnest["name"], "onsite": thinnest["onsite"]["n"],
                      "tone": thinnest["onsite"]["tone"]} if thinnest else None),
        "xtitle_x": round(padl + plotw / 2, 1), "xtitle_y": H - 4,
        "ytitle_x": 11, "ytitle_y": round(padt + ploth / 2, 1),
        "aria_label": f"People on-site each weekday, out of {ymax}: {label}."
                      if bars else "No coverage data for this period.",
        "table": {"caption": "On-site coverage by weekday",
                  "headers": ["Weekday", "On-site", "Off-site",
                              "Sections with nobody on-site"],
                  "rows": rows},
    }


def count_bars_geom(items, *, caption, unit_label="", value_header="Count",
                    key_header="Item"):
    """One-series columns for a plain tally — breaks per weekday, day-offs per
    weekday, people taking part per week.

    `items` is [{"name", "short"?, "n"}]. The tallest column is toned "accent"
    and the rest "soft": with a single series there is nothing to tell apart by
    colour, so the only honest job colour has left is pointing at the answer the
    reader came for. Same contract as bars_geom — coordinates, tone TOKENS, an
    aria label and the chart_table rows, never a colour and never HTML."""
    W, H, padl, padr, padt, padb = 460, 170, 34, 12, 10, 34
    plotw, ploth = W - padl - padr, H - padt - padb
    axis_y = padt + ploth
    vals = [max(0, int(i.get("n") or 0)) for i in items]
    ymax = max(1, max(vals) if vals else 1)
    n = len(items) or 1
    slot = plotw / n
    bw = min(30.0, slot * 0.6)
    top = max(vals) if vals else 0
    bars, rows = [], []
    for i, item in enumerate(items):
        v = vals[i]
        x = padl + slot * i + (slot - bw) / 2
        h = ploth * (v / ymax)
        bars.append({
            "name": item["name"], "short": item.get("short") or item["name"][:3],
            "n": v, "x": round(x, 1), "w": round(bw, 1),
            "y": round(axis_y - h, 1), "h": round(h, 1),
            "label_x": round(x + bw / 2, 1),
            "value_y": round(axis_y - h - 4, 1),
            "tone": "accent" if (v and v == top) else "soft",
            "peak": bool(v and v == top),
        })
        rows.append([item["name"], str(v)])
    grid = [{"y": round(axis_y - ploth * f, 1), "label": str(round(ymax * f))}
            for f in (0, 0.5, 1)]
    said = "; ".join(f"{b['name']} {b['n']}" for b in bars)
    return {
        "W": W, "H": H, "padl": padl, "axis_y": round(axis_y, 1), "ymax": ymax,
        "bars": bars, "grid": grid,
        "total": sum(vals), "empty": not any(vals),
        "aria_label": (f"{caption}{(' in ' + unit_label) if unit_label else ''}: "
                       f"{said}." if any(vals) else f"{caption}: nothing yet."),
        "table": {"caption": caption, "headers": [key_header, value_header],
                  "rows": rows},
    }


# How many shades a heat grid uses. Four steps plus "none": beyond that the eye
# stops ranking the cells and starts guessing at them.
HEAT_STEPS = 4


def _heat_step(value, top):
    """0 for nothing, else 1..HEAT_STEPS with the busiest cell at the top."""
    if not value:
        return 0
    if top <= 1:
        return HEAT_STEPS
    return 1 + int((value - 1) * (HEAT_STEPS - 1) / (top - 1))


def heat_geom(grid, row_labels, col_labels, *, caption, cell_noun="breaks"):
    """A day x time-of-day heat grid.

    `grid[r][c]` is a count. Cells carry an intensity STEP (0..HEAT_STEPS), never
    a colour — the template maps a step to one custom property, so the grid is
    right in all 36 theme x accent combinations. Rows that are entirely empty are
    dropped (a wellness break has never been taken on a Sunday; a permanently
    blank Sunday row just makes the used days smaller).

    Returns the peak cell too, because that is the sentence the card actually
    wants: "most breaks land Wednesday, before 10"."""
    keep = [r for r, row in enumerate(grid) if any(row)]
    if not keep:                       # nothing filed yet — draw the empty week
        keep = list(range(len(grid)))
    cw, ch, gap = 62, 30, 4
    labw = 74
    rows_out, cells, table_rows = [], [], []
    top = max((v for row in grid for v in row), default=0)
    for i, r in enumerate(keep):
        y = i * (ch + gap)
        rows_out.append({"label": row_labels[r], "y": y + ch / 2 + 4})
        table_rows.append([row_labels[r]] + [str(v) for v in grid[r]])
        for c, v in enumerate(grid[r]):
            cells.append({
                "row": row_labels[r], "col": col_labels[c], "n": v,
                "x": labw + c * (cw + gap), "y": y, "w": cw, "h": ch,
                # Spread 1..HEAT_STEPS across the range actually present: the
                # quietest used cell is never invisible and the busiest is always
                # full strength, whether the peak is 3 breaks or 300.
                "step": _heat_step(v, top),
                "aria": f"{row_labels[r]}, {col_labels[c]}: {v}",
            })
    W = labw + len(col_labels) * (cw + gap)
    H = len(keep) * (ch + gap) + 18
    peak = max(cells, key=lambda c: c["n"]) if cells else None
    if peak and not peak["n"]:
        peak = None
    return {
        "W": W, "H": H, "labw": labw, "cw": cw, "ch": ch, "gap": gap,
        "cells": cells, "rows": rows_out,
        "cols": [{"label": lab, "x": labw + c * (cw + gap) + cw / 2}
                 for c, lab in enumerate(col_labels)],
        "col_y": len(keep) * (ch + gap) + 11,
        "max": top, "total": sum(c["n"] for c in cells),
        "peak": ({"row": peak["row"], "col": peak["col"], "n": peak["n"]}
                 if peak else None),
        "aria_label": (f"{caption}: busiest is {peak['row']}, {peak['col']}, "
                       f"with {peak['n']} {cell_noun}."
                       if peak else f"{caption}: nothing yet."),
        "table": {"caption": caption,
                  "headers": ["Day"] + list(col_labels),
                  "rows": table_rows},
    }


# =====================================================================
# PULSE — name-free "things to know". Every statement below is an AGGREGATE read
# of a survey type; it never names a person or a specific activity. The vital
# cards expand to these, and the three summary cards are built from the same kind
# of material, so the whole Pulse page stays anonymous by construction.
# =====================================================================

# The Activities & Events card reports on the EVENT itself, not the people running
# it. The activity form shares the SERVQUAL items with the speaker form, and two of
# its dimensions read as judgments of a person — Assurance ("Knowledgeable &
# trustworthy", item B6) and Empathy ("Caring attention", B7). We drop those here so
# the card only reflects event-about ratings (delivered as promised, kept to schedule,
# addressed questions, materials & venue). Speaker quality lives on its own card.
EVENT_DIMS_FORM2 = {k: v for k, v in eng.DIM_MAP_FORM2.items()
                    if k not in ("Assurance", "Empathy")}


def _pulse_dim_map(survey_type):
    """Dimension map a pulse view should score with: event-only for activities,
    the full speaker map for resource persons."""
    return EVENT_DIMS_FORM2 if survey_type == 2 else eng.DIM_MAP_FORM3


def _confidence_note(n):
    """How much weight to put on a number, given how many responses back it."""
    if n >= eng.N_MIN * 10:
        return ("good", f"Backed by {n:,} responses — a solid, reliable read.")
    if n >= eng.N_MIN:
        return ("neutral", f"Backed by {n:,} responses — enough to be meaningful.")
    return ("mid", f"Only {n:,} response(s) so far — treat this as an early hint, not an interpretation.")


def pulse_card_insights(atoms, survey_type):
    """At least five aggregate, plain-language 'things to know' for one vital card.
    Strictly name-free: no person, no specific activity is ever cited."""
    df = atoms[atoms["survey_type"] == survey_type]
    if not _has(df):
        return []
    out = []
    respondents = int(df["response_id"].nunique())
    recent = _last_periods(df, "monthly", 6)

    if survey_type == 1:
        m = eng.arta_topbox(df)
        if m.value is not None:
            band = _band_view(m.value, eng.ARTA_BANDS)
            out.append({"tone": _tone_for_band(band), "label": "Overall",
                        "text": f"{m.value:.0f}% of walk-in clients rated their experience "
                                f"positively — that sits in the “{band}” band."})
        items = _arta_items(df)                       # ranked best → worst
        if items:
            top = items[0]
            out.append({"tone": "good", "label": "Strongest",
                        "text": f"Clients are happiest with “{top['name']}” "
                                f"({top['shown']} positive)."})
            low = items[-1]
            out.append({"tone": "mid" if low["value"] < 80 else "good", "label": "Room to grow",
                        "text": f"The lowest-scoring part of the visit is {SQD_CONCERN[low['item']]} "
                                f"({low['shown']} positive)."})
        tr = stability_phrase(_trend(recent, "monthly", eng.arta_topbox), scale="pct")
        out.append({"tone": tr["tone"], "label": "Recent months", "text": tr["phrase"]})
        tone, note = _confidence_note(respondents)
        out.append({"tone": tone, "label": "How sure we are", "text": note})
    else:
        dim_map = _pulse_dim_map(survey_type)        # event-only dims for activities
        who = "survey respondents" if survey_type == 2 else "participants"
        im = frame_item_means(df)
        value = frame_overall(dim_map, im)
        if value is not None:
            band = band7(value)
            out.append({"tone": _tone_for_band(band), "label": "Overall",
                        "text": f"The average rating is {value:.1f} out of 7 — "
                                f"that sits in the “{band}” band."})
        dims = _ranked_dimensions(df, dim_map, dim_labels(survey_type))   # ranked best → worst
        if dims:
            top = dims[0]
            out.append({"tone": "good", "label": "Strongest",
                        "text": f"The strongest quality is “{top['name']}” ({top['shown']} of 7)."})
            low = dims[-1]
            out.append({"tone": "mid" if low["value"] < 5.5 else "good", "label": "Room to grow",
                        "text": f"The area with the most room to grow is "
                                f"{dim_concern(survey_type).get(low['raw'], low['name'].lower())} "
                                f"({low['shown']} of 7)."})
        expc = im.get("A")
        if value is not None and expc is not None:
            if value - expc < -0.25:
                out.append({"tone": "mid", "label": "Expectations",
                            "text": f"On average the experience landed a little below what "
                                    f"{who} expected beforehand."})
            else:
                out.append({"tone": "good", "label": "Expectations",
                            "text": f"On average the experience met or beat what "
                                    f"{who} expected beforehand."})
        tr = stability_phrase(_trend(recent, "monthly",
                                     lambda d: eng.overall_perception(d, dim_map)), scale="mean7")
        out.append({"tone": tr["tone"], "label": "Recent months", "text": tr["phrase"]})
        tone, note = _confidence_note(respondents)
        out.append({"tone": tone, "label": "How sure we are", "text": note})
    return out


# Per-survey-type phrasings so the summary bullets never read as the same
# sentence with a noun swapped — each kind of feedback gets its own voice.
def _good_line(stype, name, shown):
    if stype == 1:
        return f"Walk-in clients rate “{name}” highest of all ({shown} positive)."
    if stype == 2:
        return f"At our activities, “{name}” is the standout strength ({shown} of 7)."
    return f"Audiences single out “{name}” as what our resource persons do best ({shown} of 7)."


def _watch_line(stype, phrase, shown, tier):
    """A uniquely-worded watch bullet. `tier` is low/mid/strong; `phrase` is the
    plain concern; `shown` already carries its unit (e.g. '99% positive', '6.4 of 7')."""
    table = {
        1: {"low":    f"The walk-in step most in need of attention is {phrase} ({shown}) — worth a closer look.",
            "mid":    f"There's clear room to improve {phrase} at the walk-in desk ({shown}).",
            "strong": f"Walk-in scores are strong all round; {phrase} is the one spot that lags slightly ({shown})."},
        2: {"low":    f"For activities, {phrase} is the weakest area and deserves a closer look ({shown}).",
            "mid":    f"Activities have the most headroom on {phrase} ({shown}).",
            "strong": f"Activity ratings are high across the board — {phrase} just trails the rest a touch ({shown})."},
        3: {"low":    f"Among resource persons, {phrase} is where scores dip most ({shown}) — worth a closer look.",
            "mid":    f"Resource persons have the most room to grow on {phrase} ({shown}).",
            "strong": f"Speaker scores are uniformly strong; {phrase} sits only marginally behind ({shown})."},
    }
    return table[stype][tier]


def pulse_summary(atoms):
    """The three summary cards — What has been good / Worth looking at / Overall
    pulse — built only from aggregate reads. Never names a person or activity.
    Each bullet is uniquely worded per survey type (no repeated template)."""
    good, watch = [], []
    concern = False              # is anything a GENUINE worry, vs. just fine-tuning?

    a = atoms[atoms["survey_type"] == 1]
    if _has(a):
        items = _arta_items(a)
        if items:
            good.append(_good_line(1, items[0]["name"], items[0]["shown"]))
            # The weakest part ALWAYS shows — even when everything is strong we
            # nitpick the relative low spot, so this card is never empty.
            low = items[-1]
            shown = f"{low['shown']} positive"
            tier = "low" if low["value"] < 80 else ("mid" if low["value"] < 90 else "strong")
            if tier == "low":
                concern = True
            watch.append(_watch_line(1, SQD_CONCERN[low["item"]], shown, tier))

    for stype, dim_map in ((2, EVENT_DIMS_FORM2), (3, eng.DIM_MAP_FORM3)):
        d = atoms[atoms["survey_type"] == stype]
        if not _has(d):
            continue
        dims = _ranked_dimensions(d, dim_map, dim_labels(stype))
        if dims:
            good.append(_good_line(stype, dims[0]["name"], dims[0]["shown"]))
            low = dims[-1]
            area = dim_concern(stype).get(low["raw"], low["name"].lower())
            shown = f"{low['shown']} of 7"
            tier = "low" if low["value"] < 5.5 else ("mid" if low["value"] < 6.3 else "strong")
            if tier == "low":
                concern = True
            watch.append(_watch_line(stype, area, shown, tier))
        im = frame_item_means(d)
        ov, expc = frame_overall(dim_map, im), im.get("A")
        if stype == 2 and ov is not None and expc is not None and ov - expc < -0.2:
            concern = True
            watch.append("On average, activities are landing a little below what survey respondents "
                         "expected beforehand — expectations are slightly outpacing the experience.")

    total = int(atoms["response_id"].nunique()) if _has(atoms) else 0
    overall = _overall_pulse_sentence(atoms, total, concern)
    if not good:
        good.append("Not enough feedback yet to highlight clear strengths.")
    if not watch:
        watch.append("Not enough feedback yet to point to a specific area to watch.")
    return {"good": good, "watch": watch, "overall": overall}


def _overall_pulse_sentence(atoms, total, has_concern):
    if total == 0:
        return "No feedback has come in for this view yet."
    parts = []
    a = atoms[atoms["survey_type"] == 1]
    if _has(a):
        m = eng.arta_topbox(a)
        if m.value is not None:
            parts.append(f"walk-in service at {m.value:.0f}% positive")
    for stype, dim_map, lab in ((2, EVENT_DIMS_FORM2, "activities"),
                                (3, eng.DIM_MAP_FORM3, "resource persons")):
        d = atoms[atoms["survey_type"] == stype]
        if _has(d):
            ov = frame_overall(dim_map, frame_item_means(d))
            if ov is not None:
                parts.append(f"{lab} at {ov:.1f} of 7")
    if not parts:
        return f"Across {total:,} responses in this view, there isn't enough scored feedback yet to summarise."
    body = "; ".join(parts)
    close = ("Overall the picture is positive, with a few areas flagged under “Worth looking at”."
             if has_concern else
             "Overall the picture is healthy — scores are steady, and “Worth looking at” is just "
             "fine-tuning rather than anything urgent.")
    return f"Across {total:,} responses in this view, the bureau is sitting at {body}. {close}"


# 7-pt SERVQUAL top-box: "rated it top" = 6 or 7 (parallel to eng.arta_topbox,
# which is the 4-5 top-box of the 5-pt ARTA scale).
SERVQUAL_TOPBOX_MIN = 6


def servqual_topbox(df, dim_map):
    """% top-box for a SERVQUAL frame: share of valid perception item-answers
    rated 6-7. The 'rated it top' headline that moves where the 6.5-ish mean
    doesn't — same item-answer denominator style as eng.arta_topbox."""
    items = [it for items in dim_map.values() for it in items]
    return _topbox_metric(df, items, SERVQUAL_TOPBOX_MIN)


def _topbox_metric(df, items, thresh):
    sub = df[df["item_id"].isin(items)]
    valid = eng.valid_answers(sub)
    n = len(valid)
    if n == 0:
        return _ItemMetric(None, 0)
    score = float((valid["value"] >= thresh).sum()) / n * 100.0
    return _ItemMetric(score, int(valid["response_id"].nunique()))


# "Unhappy" = the bottom of the scale (ARTA 5-pt: Disagree/Strongly-Disagree <=2;
# SERVQUAL 7-pt: the disagree side <=3). The share who rated LOW moves far more than
# a near-ceiling mean and catches detractor creep the headline hides.
ARTA_BOTTOMBOX_MAX = 2
SERVQUAL_BOTTOMBOX_MAX = 3


def _bottombox_metric(df, items, thresh):
    sub = df[df["item_id"].isin(items)]
    valid = eng.valid_answers(sub)
    n = len(valid)
    if n == 0:
        return _ItemMetric(None, 0)
    score = float((valid["value"] <= thresh).sum()) / n * 100.0
    return _ItemMetric(score, int(valid["response_id"].nunique()))


def _unhappy_phrase(unhappy):
    """Plain read of the 'who rated low' trend."""
    uv = [p["value"] for p in unhappy if p["value"] is not None]
    if not uv:
        return None
    cur, mx = uv[-1], max(uv)
    if mx < 2:
        return {"tone": "good", "text": "Almost no one rates this low — under 2% in every period."}
    if mx < 8:
        return {"tone": "good",
                "text": f"Few rate this low — at most {mx:.0f}% in any period, {cur:.0f}% most recently."}
    return {"tone": "neutral",
            "text": f"Worth watching the unhappy share — it has reached {mx:.0f}% "
                    f"({cur:.0f}% most recently)."}


def _latest_driver(series, dim_series, pct):
    """Augmented-analytics 'what drove it': of the areas, which one moved most in the
    SAME direction as the headline's latest period-over-period change. Index-aligned
    so the headline and each area are compared across the exact same two periods."""
    idx = [i for i, p in enumerate(series) if p["value"] is not None]
    if len(idx) < 2:
        return None
    i_now, i_prev = idx[-1], idx[-2]
    head_delta = series[i_now]["value"] - series[i_prev]["value"]
    thr = 1.0 if pct else 0.05
    if abs(head_delta) < thr:
        return None
    fmt = (lambda v: f"{v:.0f}%") if pct else (lambda v: f"{v:.1f}")
    best = None
    for d in dim_series:
        a, b = d["points"][i_prev]["value"], d["points"][i_now]["value"]
        if a is None or b is None:
            continue
        dd = b - a
        if (dd >= 0) == (head_delta >= 0) and (best is None or abs(dd) > abs(best[0])):
            best = (dd, d["name"], fmt(a), fmt(b))
    if not best or abs(best[0]) < thr:
        return None
    return {"name": best[1], "dir": "up" if head_delta >= 0 else "down",
            "from_s": best[2], "to_s": best[3]}


def _arta_topbox_resp(df):
    """Walk-in top-box %, but with the RESPONDENT count as n (not item-answers) so
    the per-period confidence band uses a fair sample size."""
    m = eng.arta_topbox(df)
    sub = df[df["item_id"].isin(eng.ARTA_HEADLINE_ITEMS)]
    resp = int(eng.valid_answers(sub)["response_id"].nunique()) if len(sub) else 0
    return _ItemMetric(m.value, resp)


# ----- signal vs noise: an SPC individuals-chart read of the headline series -----

def _control_stats(series, pct):
    """Individuals-chart (SPC) center line + 3-sigma control limits for the headline
    series, with sigma from the moving-range estimate (mR-bar / 1.128 — the standard
    individuals-chart constant). This is what separates a genuine signal from normal
    noise: a stable near-ceiling line is reported confidently as 'in control', and
    only a point outside the limits (or a long one-sided run) is flagged.
    Returns None when there are too few periods (<4) for a meaningful baseline.

    A PRACTICAL FLOOR guards against SPC's near-ceiling trap: when variation is
    almost nil the limits become razor-thin and a trivial 1-2pp blip would 'break'
    them. We only call a point a signal if it ALSO deviates from the centre by a
    practically meaningful amount (>=3pp / 0.2 of 7)."""
    vals = [(i, p["value"]) for i, p in enumerate(series) if p["value"] is not None]
    if len(vals) < 4:
        return None
    xs = [v for _, v in vals]
    cl = sum(xs) / len(xs)
    mrs = [abs(xs[k] - xs[k - 1]) for k in range(1, len(xs))]
    mrbar = (sum(mrs) / len(mrs)) if mrs else 0.0
    sigma = mrbar / 1.128
    ucl, lcl = cl + 3 * sigma, cl - 3 * sigma
    eps = 1e-9
    floor = 3.0 if pct else 0.2
    signals = [i for i, v in vals
               if sigma > eps and (v > ucl + eps or v < lcl - eps) and abs(v - cl) >= floor]
    # longest run strictly on one side of the center line (a drift the limits miss).
    # Gated on a meaningful overall spread so near-ceiling data (which sits a hair
    # above a CL pinned just under the ceiling) isn't mislabelled a 'trend'.
    best_side, best_len, cur_side, cur_len = 0, 0, 0, 0
    for _, v in vals:
        side = 1 if v > cl + eps else (-1 if v < cl - eps else 0)
        cur_len = cur_len + 1 if (side != 0 and side == cur_side) else (1 if side else 0)
        cur_side = side
        if cur_len > best_len:
            best_len, best_side = cur_len, cur_side
    spread = max(xs) - min(xs)
    drift = ("above" if best_side > 0 else "below") if (best_len >= 8 and spread >= floor) else None
    return {"cl": cl, "ucl": ucl, "lcl": lcl, "sigma": sigma,
            "signals": signals, "drift": drift}


def _conf_halfwidths(series, pct):
    """95% margin-of-error half-width per period for a top-box proportion, sized by
    that period's respondent count (binomial SE). Few responses => a wide band =>
    'don't trust this wobble'. Only meaningful for the % top-box headline; the raw
    /7 mean view returns None (we don't store per-period spread)."""
    if not pct:
        return None
    out = []
    for p in series:
        v, nn = p["value"], p.get("n", 0)
        if v is None or nn < 1:
            out.append(None)
            continue
        pr = min(1.0, max(0.0, v / 100.0))
        out.append(1.96 * math.sqrt(pr * (1 - pr) / nn) * 100.0)
    return out


def _control_read(stats, series, pct, view_from=0):
    """Plain-language SPC read for the consolidated headline panel. `view_from` is
    the index of the first period shown on the chart (the recent window) so the read
    stays CONSISTENT with what's plotted: a signal inside the window is called out
    directly (its dot is visible); a signal only in older history is mentioned as
    'earlier — switch on Full history to see it' rather than naming a period with no
    dot on screen."""
    if not stats:
        return None
    fmt = (lambda v: f"{v:.0f}%") if pct else (lambda v: f"{v:.1f}")
    cl, sig, drift = stats["cl"], stats["signals"], stats["drift"]
    high = cl >= (85 if pct else 5.5)
    in_view = [i for i in sig if i >= view_from]
    earlier = [i for i in sig if i < view_from]
    labs = lambda idxs: ", ".join(series[i]["label"] for i in idxs[:4])
    stable_word = "Consistently high and stable" if high else "Holding stable"

    if in_view:                                    # a signal the user can see on the chart
        above = any(series[i]["value"] > stats["ucl"] for i in in_view)
        below = any(series[i]["value"] < stats["lcl"] for i in in_view)
        dirw, tone = (("above", "good") if above and not below
                      else ("below", "bad") if below and not above
                      else ("outside", "neutral"))
        plural = len(in_view) != 1
        return {"tone": tone, "label": "Signal",
                "headline": (f"{len(in_view)} period{'s' if plural else ''} "
                             f"stand{'' if plural else 's'} out {dirw} the usual range."),
                "detail": "Worth a closer look at what was different in " + labs(in_view) + "."}
    if drift:                                      # a sustained one-sided run (no single outlier)
        good_dir = drift == "above"
        return {"tone": "good" if good_dir else "bad", "label": "Trend",
                "headline": (f"A steady run of periods {drift} the usual level — feedback may be "
                             f"{'improving' if good_dir else 'slipping'}."),
                "detail": ("Not one odd period but a consistent lean — "
                           + ("worth building on." if good_dir else "worth understanding."))}
    if earlier:                                    # only older blips, off the recent window
        return {"tone": "good" if high else "neutral", "label": "In control",
                "headline": stable_word + f" — recent periods are all within the usual range (around {fmt(cl)}).",
                "detail": "Earlier, " + labs(earlier) + " stood out — switch on Full history to see it."}
    return {"tone": "good" if high else "neutral", "label": "In control",
            "headline": stable_word + f" — every period sits within its usual range (around {fmt(cl)}).",
            "detail": "The small ups and downs are normal variation, not something to react to."}


def trend_view(atoms, survey_type, grain, metric="topbox", window=8, show_full=False):
    """Full trend for the Trends view: a headline series + per-area series + a
    stability read. The headline is '% rated it top' (top-box) by default — it has
    real range where a near-ceiling mean is flat; Activities/Resource persons can
    switch to the raw /7 mean (metric='mean'). The chart auto-zooms to the data and
    defaults to a recent window; the narrative reads the full history."""
    df = atoms[atoms["survey_type"] == survey_type]
    if not _has(df):
        return {"has_data": False, "title": survey_title(survey_type)}

    if survey_type == 1:
        # ARTA headline is always top-box %; the mean of an agree-scale isn't meaningful.
        metric = "topbox"
        series = _trend(df, grain, _arta_topbox_resp)
        pct, unit, ymax = True, "% rated it top", 100
        # ARTA "areas" = the eight items, in plain language (each as its own top-box %).
        dim_series = []
        for it in eng.ARTA_HEADLINE_ITEMS:
            pts = _trend(df, grain, lambda d, _i=it: _arta_item_metric(d, _i))
            if any(p["value"] is not None for p in pts):
                dim_series.append({"name": SQD_LABELS[it], "points": pts})
        unhappy = _trend(df, grain, lambda d: _bottombox_metric(d, eng.ARTA_HEADLINE_ITEMS,
                                                                 ARTA_BOTTOMBOX_MAX))
    else:
        dim_map = eng.DIM_MAP_FORM2 if survey_type == 2 else eng.DIM_MAP_FORM3
        tl = dim_labels(survey_type)            # activity-conduct vs resource-person names
        if metric == "mean":
            series = _trend(df, grain, lambda d, _m=dim_map: eng.overall_perception(d, _m))
            pct, unit, ymax = False, "of 7", 7
            dimscore = lambda d, _it: eng.dimension_mean(d, _it)
        else:
            metric = "topbox"
            series = _trend(df, grain, lambda d, _m=dim_map: servqual_topbox(d, _m))
            pct, unit, ymax = True, "% rated it top", 100
            dimscore = lambda d, _it: _topbox_metric(d, _it, SERVQUAL_TOPBOX_MIN)
        dim_series = []
        for dim, items in dim_map.items():
            pts = _trend(df, grain, lambda d, _it=items: dimscore(d, _it))
            if any(p["value"] is not None for p in pts):
                dim_series.append({"name": tl.get(dim, dim), "points": pts})
        _bb_items = [it for items in dim_map.values() for it in items]
        unhappy = _trend(df, grain, lambda d, _it=_bb_items: _bottombox_metric(
            d, _it, SERVQUAL_BOTTOMBOX_MAX))

    scale = "pct" if pct else "mean7"
    n_valid = len([p for p in series if p["value"] is not None])
    full_n = len(series)
    view_from = 0 if (show_full or full_n <= window) else full_n - window
    control = _control_stats(series, pct)       # SPC read over the FULL history
    conf = _conf_halfwidths(series, pct)        # per-period margin of error (top-box)
    # Movers are read over the DISPLAYED window so the by-area highlight + "what's
    # moving" text match what's actually plotted (a 21-quarter net of ~0 would hide
    # a clear recent climb).
    wdims = [{"name": d["name"], "points": d["points"][view_from:]} for d in dim_series]
    movers = _trend_movers(wdims, pct)
    # which areas to emphasise (bold) vs dim (grey) on the by-area chart
    roles = {}
    if movers:
        if movers.get("improved"):
            roles[movers["improved"]["name"]] = "up"
        if movers.get("watch"):
            roles[movers["watch"]["name"]] = "down"
    return {
        "has_data": True, "title": survey_title(survey_type), "unit": unit, "ymax": ymax,
        "pct": pct, "metric": metric, "window": window, "show_full": show_full,
        "n_periods": n_valid,
        "series": series, "stability": stability_phrase(series, scale),
        "control_read": _control_read(control, series, pct, view_from),
        "driver": _latest_driver(series, dim_series, pct),
        "dimensions": dim_series,
        "geom": _svg_geom(series, dim_series, ymax, pct, window, show_full,
                          control=control, conf=conf, mover_roles=roles),
        "unhappy_geom": _svg_geom(unhappy, [], 100, True, window, show_full),
        "unhappy_read": _unhappy_phrase(unhappy),
        "movers": movers,
        # Raw layers (not SVG geometry) so non-HTML renderers — e.g. the matplotlib
        # download — can redraw the control band, confidence ribbon, unhappy-share
        # line and mover highlight themselves.
        "control": control, "conf": conf, "unhappy": unhappy, "roles": roles,
    }


def _trend_movers(dim_series, pct):
    """Read the per-area lines and pick the one that climbed the most and the one
    that slipped the most (first vs last period it has data for) — so the busy
    multi-line chart gets a plain-language 'what's actually moving' takeaway."""
    fmt = (lambda v: f"{v:.0f}%") if pct else (lambda v: f"{v:.1f}")
    thr = 3.0 if pct else 0.2          # ignore noise below ~3pp / 0.2 of 7
    rows = []
    for d in dim_series:
        vals = [(p["label"], p["value"]) for p in d["points"] if p["value"] is not None]
        if len(vals) < 2:
            continue
        first, last = vals[0], vals[-1]
        rows.append({"name": d["name"], "delta": last[1] - first[1],
                     "from_s": fmt(first[1]), "to_s": fmt(last[1]),
                     "from_lab": first[0]})
    if not rows:
        return None
    up, down = max(rows, key=lambda r: r["delta"]), min(rows, key=lambda r: r["delta"])
    out = {}
    if up["delta"] >= thr:
        out["improved"] = up
    if down["delta"] <= -thr and down["name"] != up["name"]:
        out["watch"] = down
    return out or None


# Distinct line colors for the dimension trend lines.
_LINE_COLORS = ["#2b6cb0", "#2f855a", "#b7791f", "#805ad5", "#0987a0", "#c53030",
                "#d53f8c", "#718096"]


def _gridvals(lo, hi, pct):
    """3-4 'nice' horizontal-gridline values spanning [lo, hi]."""
    rng = hi - lo
    if rng <= 0:
        return [lo]
    raw = rng / 3.0
    steps = (1, 2, 5, 10, 20, 25, 50) if pct else (0.1, 0.2, 0.5, 1.0)
    step = next((s for s in steps if s >= raw), steps[-1])
    vals, v = [], math.ceil(lo / step) * step
    while v <= hi + 1e-9:
        vals.append(round(v, 2))
        v += step
    return vals or [lo, hi]


def _nice_bounds(vmin, vmax, ymax_full, pct):
    """Pick a TIGHT, honest y-range around the data so small-but-real movement is
    visible, plus nice gridlines. Returns (lo, hi, gridvals, flat).
    `flat` is True when the data barely moves (near-ceiling) — the caller frames
    that as 'consistently high', and we still show a small band so it isn't a
    divide-by-zero or a line glued to an edge."""
    flat = (vmax - vmin) < (0.5 if pct else 0.05)
    if flat:
        pad = 2.0 if pct else 0.2
        center = (vmin + vmax) / 2.0
        lo, hi = center - pad, center + pad
    else:
        pad = (vmax - vmin) * 0.35
        lo, hi = vmin - pad, vmax + pad
    if pct:
        lo, hi = math.floor(lo / 2) * 2, math.ceil(hi / 2) * 2
    else:
        lo, hi = math.floor(lo * 10) / 10, math.ceil(hi * 10) / 10
    lo = max(0, lo)
    hi = min(ymax_full, hi)
    if hi <= lo:                                   # pinned at the ceiling
        lo = max(0, ymax_full - (2 if pct else 0.2))
        hi = ymax_full
    return lo, hi, _gridvals(lo, hi, pct), flat


def _svg_geom(series, dim_series, ymax_full, pct, window=8, show_full=False,
              control=None, conf=None, mover_roles=None):
    """Precompute SVG coordinates for the Trends chart. Upgrades over a plain
    0-to-max line: (1) the y-axis AUTO-ZOOMS to the data in view (with gridlines),
    so a 6.4->6.7 climb reads as real instead of flat near the top; (2) a RECENT
    WINDOW by default (last `window` periods) with thinned x-labels; (3) an SPC
    CONTROL BAND (center line + 3-sigma limits) with out-of-limit periods flagged;
    (4) a per-period CONFIDENCE RIBBON sized by sample N; (5) per-area `role`
    (up/down mover vs flat) + end-label coords so the by-area chart can bold the
    movers and dim the rest. The template only draws the strings we hand it."""
    mover_roles = mover_roles or {}
    full_n = len(series)
    lo_i = 0 if (show_full or full_n <= window) else full_n - window
    vseries = series[lo_i:]
    vdims = [{"name": d["name"], "points": d["points"][lo_i:]} for d in dim_series]
    n = len(vseries)

    # --- auto-zoom: fit y to everything in view (headline, areas, band, ribbon) ---
    vals = [p["value"] for p in vseries if p["value"] is not None]
    for d in vdims:
        vals += [p["value"] for p in d["points"] if p["value"] is not None]
    if control:
        vals += [min(ymax_full, max(0, control[k])) for k in ("ucl", "lcl", "cl")]
    if conf:
        for i, p in enumerate(vseries):
            hw = conf[lo_i + i]
            if p["value"] is not None and hw:
                vals += [min(ymax_full, p["value"] + hw), max(0, p["value"] - hw)]
    if not vals:
        vals = [0, ymax_full]
    ylo, yhi, gridvals, flat = _nice_bounds(min(vals), max(vals), ymax_full, pct)

    # padl/padbot leave room for a rotated Y-axis title + a centred X-axis title
    # (the figure-axis standard: every chart carries labelled axes).
    W, H, padl, padr, padtop, padbot = 680, 252, 62, 16, 18, 50
    plotw, ploth = W - padl - padr, H - padtop - padbot

    def xy(i, v):
        x = padl + (i * plotw / (n - 1) if n > 1 else plotw / 2)
        y = padtop + (1 - (v - ylo) / (yhi - ylo)) * ploth
        return x, y

    def cy(v):                                     # y for a constant level (clamped)
        return round(xy(0, min(ymax_full, max(0, v)))[1], 1)

    def line(points):
        pts, dots = [], []
        for i, p in enumerate(points):
            if p["value"] is None:
                continue
            x, y = xy(i, p["value"])
            pts.append(f"{x:.1f},{y:.1f}")
            dots.append({"x": round(x, 1), "y": round(y, 1), "label": p["label"],
                         "value": p["value"], "n": p.get("n", 0), "signal": False})
        return " ".join(pts), dots

    fmt = (lambda v: f"{v:.0f}%") if pct else (lambda v: f"{v:.1f}")
    main_poly, main_dots = line(vseries)

    # --- confidence ribbon: upper edge forward, lower edge back (closed polygon) ---
    conf_poly = ""
    if conf:
        ups, downs = [], []
        for i, p in enumerate(vseries):
            if p["value"] is None:
                continue
            hw = conf[lo_i + i] or 0
            x = xy(i, p["value"])[0]
            ups.append(f"{x:.1f},{xy(i, min(ymax_full, p['value'] + hw))[1]:.1f}")
            downs.append(f"{x:.1f},{xy(i, max(0, p['value'] - hw))[1]:.1f}")
        if ups:
            conf_poly = " ".join(ups + downs[::-1])

    # --- control band: 3 constant horizontal levels + flag the signal dots ---
    control_geom = None
    if control:
        sigset = {idx - lo_i for idx in control["signals"] if idx >= lo_i}
        j = 0
        for i, p in enumerate(vseries):
            if p["value"] is None:
                continue
            main_dots[j]["signal"] = i in sigset
            j += 1
        control_geom = {
            "cl_y": cy(control["cl"]), "ucl_y": cy(control["ucl"]), "lcl_y": cy(control["lcl"]),
            "cl_label": fmt(control["cl"]),
            "ucl_label": fmt(min(ymax_full, control["ucl"])),
            "lcl_label": fmt(max(0, control["lcl"])),
            "x1": padl, "x2": W - padr, "lab_x": W - padr - 2,
            "has_signal": bool(control["signals"]),
        }
    dims = []
    for idx, d in enumerate(vdims):
        poly, ddots = line(d["points"])
        vv = [p["value"] for p in d["points"] if p["value"] is not None]
        # Current value + which way the line is leaning (first vs last point in view),
        # so the legend reads as "Quick to help 6.4 ↑" instead of a bare swatch.
        cur = fmt(vv[-1]) if vv else None
        if len(vv) >= 2:
            move = vv[-1] - vv[0]
            thr = 3.0 if pct else 0.2
            arrow = "↑" if move >= thr else ("↓" if move <= -thr else "→")
        else:
            arrow = "→"
        role = mover_roles.get(d["name"])          # 'up' / 'down' / None(=steady)
        end = ddots[-1] if ddots else None
        dims.append({"name": d["name"], "poly": poly,
                     "color": _LINE_COLORS[idx % len(_LINE_COLORS)],
                     "cur": cur, "arrow": arrow, "role": role,
                     "endx": (end["x"] if end else None),
                     "endy": (end["y"] if end else None)})

    # Thin x-labels to ~8 visible when a long history is shown; always keep the last.
    step = math.ceil(n / 8) if n > 9 else 1
    xlabels = [{"x": round(xy(i, ylo)[0], 1), "text": p["label"],
                "show": (i % step == 0) or (i == n - 1)}
               for i, p in enumerate(vseries)]
    grid = [{"y": round(xy(0, gv)[1], 1), "label": fmt(gv)} for gv in gridvals]

    # Screen-reader data tables (WCAG 1.1.1) — the same in-view numbers the chart plots,
    # built from the index-aligned vseries / vdims so the table matches the drawn window.
    # main_table: one value column. dims_table: one column per area/segment (None if no dims).
    cell = lambda v: (fmt(v) if v is not None else "—")
    main_table = [[p["label"], cell(p["value"])] for p in vseries]
    dims_table = None
    if vdims:
        dims_table = {
            "headers": ["Period"] + [d["name"] for d in vdims],
            "rows": [[vseries[i]["label"]]
                     + [cell(d["points"][i]["value"] if i < len(d["points"]) else None)
                        for d in vdims]
                     for i in range(len(vseries))],
        }

    return {"W": W, "H": H, "padl": padl,
            "main_poly": main_poly, "main_dots": main_dots, "dims": dims,
            "main_table": main_table, "dims_table": dims_table,
            "xlabels": xlabels, "axis_y": round(H - padbot, 1), "grid": grid,
            "ylo": ylo, "yhi": yhi, "flat": flat, "full_n": full_n,
            "shown_n": n, "windowed": not (show_full or full_n <= window),
            "conf_poly": conf_poly, "control": control_geom,
            # anchor points for the X/Y axis titles (figure-axis standard)
            "ytitle_x": 15, "ytitle_y": round((padtop + (H - padbot)) / 2, 1),
            "xtitle_x": round((padl + W - padr) / 2, 1), "xtitle_y": H - 7}


# =====================================================================
# TRENDS — PHASE D: segment-split + verbatim-sentiment over time.
# Both reuse the headline machinery above: _trend() for the period series,
# _svg_geom() for the coordinates. The discipline that matters here is the
# SAME one the SPC page enforces — don't let a thin slice read as a signal.
# =====================================================================

def _headline_spec(survey_type, metric):
    """The scorer + scale the Trends headline uses, factored so the segment-split
    can run the EXACT same metric on each slice (else the lines wouldn't be
    comparable to the overall line drawn behind them). Mirrors trend_view."""
    if survey_type == 1:
        return _arta_topbox_resp, True, 100, "% rated it top"      # ARTA is always top-box
    dim_map = eng.DIM_MAP_FORM2 if survey_type == 2 else eng.DIM_MAP_FORM3
    if metric == "mean":
        return (lambda d, _m=dim_map: eng.overall_perception(d, _m)), False, 7, "of 7"
    return (lambda d, _m=dim_map: servqual_topbox(d, _m)), True, 100, "% rated it top"


def _segment_read(seg_series, pct):
    """One plain-language line on whether the split is pulling segments apart —
    read off the latest period each segment has data for."""
    fmt = (lambda v: f"{v:.0f}%") if pct else (lambda v: f"{v:.1f}")
    latest = []
    for s in seg_series:
        vv = [p["value"] for p in s["points"] if p["value"] is not None]
        if vv:
            latest.append((s["name"], vv[-1]))
    if len(latest) < 2:
        return None
    latest.sort(key=lambda t: -t[1])
    hi, lo = latest[0], latest[-1]
    gap = hi[1] - lo[1]
    thr = 5.0 if pct else 0.3
    if gap < thr:
        return {"tone": "neutral",
                "text": f"{hi[0]} and {lo[0]} are tracking together "
                        f"({fmt(hi[1])} vs {fmt(lo[1])}) — the split isn't pulling them apart."}
    return {"tone": "watch",
            "text": f"{hi[0]} ({fmt(hi[1])}) is running ahead of {lo[0]} ({fmt(lo[1])}) "
                    f"— a gap of {fmt(gap)} the headline average hides."}


def segment_trend(atoms, survey_type, grain, segment_col, labels=None,
                  metric="topbox", window=8, show_full=False, min_n=None):
    """Split the headline trend by a categorical segment (e.g. modality online vs
    face-to-face): each segment becomes its own line over the SAME headline metric,
    with the overall line drawn behind for reference. A segment too thin to read
    (fewer than `min_n` responses in the shown window) is dropped with a note, so a
    2-response slice can't masquerade as a trend. Needs >=2 readable segments to be
    worth showing at all."""
    df = atoms[atoms["survey_type"] == survey_type] if _has(atoms) else atoms
    if not _has(df) or segment_col not in df.columns:
        return {"has_data": False}
    min_n = eng.N_MIN if min_n is None else min_n
    labels = labels or {}
    scorer, pct, ymax, unit = _headline_spec(survey_type, metric)
    headline = _trend(df, grain, scorer)
    seg_series, dropped = [], []
    # stable order: by total responses desc, so colours/legend don't jump around
    vals = [v for v in df[segment_col].dropna().unique()]
    vals.sort(key=lambda v: -int((df[segment_col] == v).sum()))
    for v in vals:
        pts = _trend(df[df[segment_col] == v], grain, scorer)
        lo_i = 0 if (show_full or len(pts) <= window) else len(pts) - window
        n_in_view = sum(p["n"] for p in pts[lo_i:])
        name = labels.get(v, str(v))
        if not any(p["value"] is not None for p in pts) or n_in_view < min_n:
            if name not in dropped:
                dropped.append(name)
            continue
        seg_series.append({"name": name, "points": pts})
    if len(seg_series) < 2:
        return {"has_data": False, "dropped": dropped,
                "only": seg_series[0]["name"] if seg_series else None}
    return {"has_data": True, "pct": pct, "unit": unit, "ymax": ymax,
            "geom": _svg_geom(headline, seg_series, ymax, pct, window, show_full),
            "segments": [s["name"] for s in seg_series], "dropped": dropped,
            # raw per-segment series so non-HTML renderers (matplotlib) can redraw
            "series_raw": seg_series, "read": _segment_read(seg_series, pct)}


def _sentiment_read(series):
    """First-vs-last read on the tone of comments over time."""
    vv = [(p["label"], p["value"]) for p in series if p["value"] is not None]
    if len(vv) < 2:
        return {"tone": "neutral",
                "text": "Not enough comments yet to read a trend in tone."}
    move = vv[-1][1] - vv[0][1]
    cur = vv[-1][1]
    if move >= 5:
        return {"tone": "good",
                "text": f"The tone of comments is warming — {vv[-1][0]} sits at "
                        f"{cur:.0f}% positive, up from {vv[0][1]:.0f}%."}
    if move <= -5:
        return {"tone": "bad",
                "text": f"The tone of comments is cooling — {vv[-1][0]} is {cur:.0f}% "
                        f"positive, down from {vv[0][1]:.0f}%. Worth reading what changed."}
    return {"tone": "neutral",
            "text": f"Comment tone is steady — about {cur:.0f}% of recent comments "
                    f"read as positive."}


def _sentiment_breakdown_read(appr, impr, mixed):
    """3-way read for the breakdown chart: is the share of comments pointing to
    something to improve rising or easing over time? Mentions the mixed (good-but-
    bad) share when it's big enough to matter."""
    iv = [(p["label"], p["value"]) for p in impr if p["value"] is not None]
    if len(iv) < 2:
        return {"tone": "neutral",
                "text": "Not enough comments yet to read how the mix of tone is shifting."}
    move = iv[-1][1] - iv[0][1]
    cur = iv[-1][1]
    mv = [p["value"] for p in mixed if p["value"] is not None]
    mixed_now = mv[-1] if mv else 0
    mixed_note = (f" Mixed (good-but-bad) comments sit at {mixed_now:.0f}%."
                  if mixed_now >= 10 else "")
    if move >= 5:
        return {"tone": "bad",
                "text": f"Comments are tilting toward areas to improve — {iv[-1][0]} sits "
                        f"at {cur:.0f}% improvement-focused, up from {iv[0][1]:.0f}%. "
                        f"Worth reading what changed.{mixed_note}"}
    if move <= -5:
        return {"tone": "good",
                "text": f"Fewer comments are flagging problems — improvement-focused "
                        f"comments eased to {cur:.0f}% by {iv[-1][0]}, down from "
                        f"{iv[0][1]:.0f}%.{mixed_note}"}
    return {"tone": "neutral",
            "text": f"The mix of tone is steady — about {cur:.0f}% of recent comments "
                    f"point to something to improve.{mixed_note}"}


def sentiment_trend(atoms, verbatims, survey_type, grain, overrides=None,
                    window=8, show_full=False):
    """% of free-text comments that read as appreciation, per period — the tone of
    what people WRITE, beside the tone of how they RATE. Catches the case where the
    score holds but the words sour (or vice-versa). Uses the same classifier and the
    same manual re-tags (`overrides`) the story panels use. `verbatims` is the
    storage payload for the scope's responses; we map each comment back to its
    period via the atoms frame (no second date parse)."""
    df = atoms[atoms["survey_type"] == survey_type] if _has(atoms) else atoms
    if not _has(df) or not verbatims:
        return {"has_data": False}
    keycol = period_col_for(grain)
    if keycol not in df.columns:
        return {"has_data": False}
    rid_period = (df.dropna(subset=[keycol]).drop_duplicates("response_id")
                    .set_index("response_id")[keycol].to_dict())
    overrides = overrides or {}
    # period key -> {pos, appr, impr, mixed, tot}. `pos` drives the long-standing
    # binary "% positive" line (unchanged); appr/impr/mixed drive the 3-way
    # breakdown. They differ only for comments manually re-tagged "mixed": those
    # stay text-classified for the binary line but land in the mixed bucket below.
    tally = {}
    for q in _flatten_quotes(verbatims):
        per = rid_period.get(q.get("rid"))
        if per is None or per != per:              # comment outside the dated scope
            continue
        forced = overrides.get((q.get("rid"), q.get("item", "")))
        auto = classify_quote(q["text"])
        side = forced if forced in ("appreciate", "improve") else auto
        klass = forced if forced in ("appreciate", "improve", "mixed") else auto
        t = tally.setdefault(per, {"pos": 0, "appr": 0, "impr": 0, "mixed": 0, "tot": 0})
        t["tot"] += 1
        if side == "appreciate":
            t["pos"] += 1
        t[{"appreciate": "appr", "improve": "impr", "mixed": "mixed"}[klass]] += 1
    if not tally:
        return {"has_data": False}
    items = sorted(tally.items())

    def _share(bucket):
        return [{"key": k, "label": period_label(k, grain),
                 "value": (100.0 * c[bucket] / c["tot"]) if c["tot"] else None,
                 "n": c["tot"]} for k, c in items]

    series = _share("pos")                         # binary line — back-compat
    appr, impr, mixed = _share("appr"), _share("impr"), _share("mixed")
    # 3-way breakdown: appreciation as the headline line, areas-to-improve and
    # mixed (good-but-bad) drawn over it. Mutually exclusive, so the three shares
    # sum to 100% in every period. Reuses the segment-split chart machinery.
    breakdown = {
        "has_data": True,
        "geom": _svg_geom(appr, [{"name": "Areas to improve", "points": impr},
                                 {"name": "Mixed (good-but-bad)", "points": mixed}],
                          100, True, window, show_full),
        "series_raw": [{"name": "Appreciation", "points": appr},
                       {"name": "Areas to improve", "points": impr},
                       {"name": "Mixed (good-but-bad)", "points": mixed}],
        "read": _sentiment_breakdown_read(appr, impr, mixed),
    }
    return {"has_data": True, "series": series,
            "geom": _svg_geom(series, [], 100, True, window, show_full),
            "read": _sentiment_read(series), "breakdown": breakdown}


class _ItemMetric:
    def __init__(self, value, n):
        self.value, self.n, self.flags = value, n, []


def _arta_item_metric(df, item):
    det = eng.arta_item_detail(df, item)
    return _ItemMetric(det.get("score"), det.get("n", 0))


# =====================================================================
# PARTICIPATION — how MANY responses we're getting (volume), who's active,
# and where the blind spots are. Counts, not scores.
# =====================================================================

def _short(path):
    """Drop the bureau root segment for display: 'BLHSD/Div1/SecA' -> 'Div1/SecA'."""
    if not path:
        return path
    return path.split("/", 1)[1] if "/" in path else path


def _count(df):
    return int(df["response_id"].nunique()) if _has(df) else 0


def volume_series(atoms, survey_type, grain):
    """Response COUNT per period for one survey type (the 'are we going up or down
    in responses' chart)."""
    df = atoms[atoms["survey_type"] == survey_type]
    out = []
    if not _has(df):
        return out
    keys = _keys(df, grain)
    counts = df.groupby(keys.values)["response_id"].nunique()    # one pass
    for k, n in counts.items():
        if k is None or k != k:
            continue
        out.append({"key": k, "label": period_label(k, grain), "count": int(n)})
    return out


def volume_headline(atoms, survey_type, grain="monthly"):
    """Latest period's response count vs the previous period — the up/down read."""
    series = volume_series(atoms, survey_type, grain)
    total = _count(atoms[atoms["survey_type"] == survey_type])
    h = {"title": survey_title(survey_type), "total": total, "series": series,
         "latest": None, "prev": None, "delta": None, "pct": None, "dir": "flat",
         "latest_label": None}
    if series:
        h["latest"] = series[-1]["count"]; h["latest_label"] = series[-1]["label"]
        if len(series) >= 2:
            h["prev"] = series[-2]["count"]
            h["delta"] = h["latest"] - h["prev"]
            h["pct"] = (h["delta"] / h["prev"] * 100) if h["prev"] else None
            h["dir"] = "up" if h["delta"] > 0 else ("down" if h["delta"] < 0 else "flat")
    return h


def volume_by_unit(atoms, org_struct):
    """Distinct responses attributed to each division and section — who is (and
    isn't) generating feedback. Bureau-wide by nature (it IS the breakdown)."""
    def for_prefix(prefix):
        return _count(atoms[atoms["org_path"].astype(str).str.startswith(prefix)])
    rows = []
    for d in org_struct["divisions"]:
        rows.append({"level": "division", "label": _short(d["path"]) or d["name"],
                     "path": d["path"], "count": for_prefix(d["path"])})
        for s in d["sections"]:
            rows.append({"level": "section", "label": _short(s["path"]),
                         "path": s["path"], "count": for_prefix(s["path"])})
    for s in org_struct["admin_sections"]:
        rows.append({"level": "section", "label": _short(s["path"]) + " · admin",
                     "path": s["path"], "count": for_prefix(s["path"])})
    ext = _count(atoms[atoms["org_path"].astype(str) == "External"])
    if ext:
        rows.append({"level": "external", "label": "External speakers", "path": "External", "count": ext})
    mx = max([r["count"] for r in rows], default=0)
    for r in rows:
        r["pct"] = (r["count"] / mx * 100) if mx else 0
    return rows


def coverage(atoms, instances, staff):
    """How much of the program is actually being measured: events that drew any
    feedback, and staff who have any rating."""
    groups = {}
    for inst in instances:
        groups.setdefault(_event_group_key(inst), []).append(inst)
    inst_with_data = set(atoms["form_instance_id"].dropna().astype(int).tolist())
    ev_total = len(groups)
    ev_with = sum(1 for g in groups.values() if any(i["id"] in inst_with_data for i in g))

    internal = [p for p in staff if p["is_internal"]]
    rated = set(atoms[atoms["survey_type"] == 1]["served_by_rp_id"].dropna().astype(int).tolist())
    rated |= set(atoms[atoms["survey_type"] == 3]["rp_id"].dropna().astype(int).tolist())
    st_total = len(internal)
    st_rated = sum(1 for p in internal if p["id"] in rated)

    def pct(a, b):
        return (a / b * 100) if b else 0
    return {"events_total": ev_total, "events_with": ev_with, "events_pct": pct(ev_with, ev_total),
            "staff_total": st_total, "staff_rated": st_rated, "staff_pct": pct(st_rated, st_total)}


def blind_spots(atoms, instances, staff, org_struct, low_event=5):
    """Plain-language 'who/what is silent' list — the gaps in coverage."""
    out = []
    # Sections with zero responses.
    for d in org_struct["divisions"]:
        for s in d["sections"]:
            if _count(atoms[atoms["org_path"].astype(str).str.startswith(s["path"])]) == 0:
                out.append({"tone": "bad",
                            "text": f"{_short(s['path'])} has no feedback on record yet."})
    # Internal staff with no rating at all.
    rated = set(atoms[atoms["survey_type"] == 1]["served_by_rp_id"].dropna().astype(int).tolist())
    rated |= set(atoms[atoms["survey_type"] == 3]["rp_id"].dropna().astype(int).tolist())
    # Count only — never name individuals who have no feedback (it reads as shaming).
    n_unrated = sum(1 for p in staff if p["is_internal"] and p["id"] not in rated)
    if n_unrated:
        out.append({"tone": "mid",
                    "text": (f"{n_unrated} staff member{'s' if n_unrated != 1 else ''} "
                             f"{'have' if n_unrated != 1 else 'has'} no feedback on record yet.")})
    # Events that drew only a handful of responses. One pass: distinct responses
    # per form instance, then summed per event group (a response belongs to
    # exactly one instance, so the sum is exact).
    groups = {}
    for inst in instances:
        groups.setdefault(_event_group_key(inst), []).append(inst)
    per_inst = (atoms.groupby("form_instance_id")["response_id"].nunique().to_dict()
                if _has(atoms) else {})
    thin = 0
    for g in groups.values():
        n = sum(per_inst.get(i["id"], 0) for i in g)
        if 0 < n < low_event:
            thin += 1
    if thin:
        out.append({"tone": "mid",
                    "text": f"{thin} event(s) drew fewer than {low_event} responses — results there are thin."})
    return out


# =====================================================================
# PARTICIPATION v2 — the Trends-grade redesign for VOLUME. Same learnings as the
# Trends page applied to "how MUCH feedback we get": a consolidated plain-language
# read, honest auto-zoomed charts with labelled axes, an SPC control band so a real
# surge/drop is told apart from normal noise, a confidence ribbon on coverage (a
# genuine proportion), normalized engagement (responses per event), and by-unit
# movers (who rose/fell most) with a driver line. Reuses the Trends engine
# (_control_stats / _conf_halfwidths / _control_read / _svg_geom) wherever the scale
# is a percent; adds count-aware geometry for the raw volume / ratio series.
# =====================================================================

# Nice gridline steps spanning whole counts AND small ratios (responses per event).
_COUNT_STEPS = [0.1, 0.2, 0.5, 1, 2, 5, 10, 20, 25, 50, 100, 200, 250, 500,
                1000, 2000, 2500, 5000, 10000, 20000]


def _nice_step(rng, target=3.0):
    """A 'nice' step (~rng/target) from the count ladder — for integer counts and
    small float ratios alike."""
    raw = (rng / target) if rng > 0 else 1.0
    return next((s for s in _COUNT_STEPS if s >= raw), _COUNT_STEPS[-1])


def _count_gridvals(lo, hi):
    step = _nice_step(hi - lo)
    vals, v = [], math.ceil(lo / step) * step
    while v <= hi + 1e-9:
        vals.append(round(v, 2))
        v += step
    return vals or [lo, hi]


def _count_bounds(vmin, vmax, ymax_full=None):
    """Tight, honest auto-zoom for a count/ratio series (like _nice_bounds, but on a
    count scale). Returns (lo, hi, gridvals, flat)."""
    span = vmax - vmin
    flat = span < 1e-9
    if flat:
        pad = max(1.0, abs(vmax) * 0.1) if vmax else 1.0
        lo, hi = vmin - pad, vmax + pad
    else:
        pad = span * 0.35
        lo, hi = vmin - pad, vmax + pad
    step = _nice_step(hi - lo)
    lo = math.floor(lo / step) * step
    hi = math.ceil(hi / step) * step
    lo = max(0, lo)
    if ymax_full:
        hi = min(ymax_full, hi)
    if hi <= lo:
        hi = lo + step
    return lo, hi, _count_gridvals(lo, hi), flat


def _count_geom(series, control=None, window=8, show_full=False, decimals=0):
    """SVG geometry for a single count/ratio line. Mirrors _svg_geom's output keys
    (so the template's chart markup is shared) but on a count scale: auto-zoom,
    integer/ratio gridlines, an SPC control band with flagged signal dots, and a
    recent window. No percent confidence ribbon (a raw count has no sampling MoE)."""
    full_n = len(series)
    lo_i = 0 if (show_full or full_n <= window) else full_n - window
    vseries = series[lo_i:]
    n = len(vseries)
    fmt = (lambda v: f"{v:,.0f}") if decimals == 0 else (lambda v: f"{v:,.{decimals}f}")

    vals = [p["value"] for p in vseries if p["value"] is not None]
    if control:
        vals += [max(0, control[k]) for k in ("ucl", "lcl", "cl")]
    if not vals:
        vals = [0, 1]
    ylo, yhi, gridvals, flat = _count_bounds(min(vals), max(vals))

    W, H, padl, padr, padtop, padbot = 680, 252, 62, 16, 18, 50
    plotw, ploth = W - padl - padr, H - padtop - padbot

    def xy(i, v):
        x = padl + (i * plotw / (n - 1) if n > 1 else plotw / 2)
        y = padtop + (1 - (v - ylo) / (yhi - ylo)) * ploth if yhi > ylo else padtop + ploth / 2
        return x, y

    def cy(v):
        return round(xy(0, max(ylo, min(yhi, v)))[1], 1)

    pts, dots = [], []
    for i, p in enumerate(vseries):
        if p["value"] is None:
            continue
        x, y = xy(i, p["value"])
        pts.append(f"{x:.1f},{y:.1f}")
        dots.append({"x": round(x, 1), "y": round(y, 1), "label": p["label"],
                     "value": p["value"], "shown": fmt(p["value"]),
                     "n": p.get("n", 0), "signal": False})
    main_poly = " ".join(pts)

    control_geom = None
    if control:
        sigset = {idx - lo_i for idx in control["signals"] if idx >= lo_i}
        j = 0
        for i, p in enumerate(vseries):
            if p["value"] is None:
                continue
            dots[j]["signal"] = i in sigset
            j += 1
        control_geom = {
            "cl_y": cy(control["cl"]), "ucl_y": cy(control["ucl"]), "lcl_y": cy(control["lcl"]),
            "cl_label": fmt(control["cl"]), "ucl_label": fmt(control["ucl"]),
            "lcl_label": fmt(max(0, control["lcl"])),
            "x1": padl, "x2": W - padr, "lab_x": W - padr - 2,
            "has_signal": bool(control["signals"])}

    step = math.ceil(n / 8) if n > 9 else 1
    xlabels = [{"x": round(xy(i, ylo)[0], 1), "text": p["label"],
                "show": (i % step == 0) or (i == n - 1)} for i, p in enumerate(vseries)]
    grid = [{"y": round(xy(0, gv)[1], 1), "label": fmt(gv)} for gv in gridvals]
    # Screen-reader data table (WCAG 1.1.1) — same in-view counts the line plots.
    cell = lambda v: (fmt(v) if v is not None else "—")
    main_table = [[p["label"], cell(p["value"])] for p in vseries]
    return {"W": W, "H": H, "padl": padl, "main_poly": main_poly, "main_dots": dots,
            "main_table": main_table,
            "xlabels": xlabels, "axis_y": round(H - padbot, 1), "grid": grid,
            "ylo": ylo, "yhi": yhi, "flat": flat, "full_n": full_n, "shown_n": n,
            "windowed": not (show_full or full_n <= window), "control": control_geom,
            "ytitle_x": 15, "ytitle_y": round((padtop + (H - padbot)) / 2, 1),
            "xtitle_x": round((padl + W - padr) / 2, 1), "xtitle_y": H - 7}


def _volume_read(stats, series, view_from=0):
    """Plain-language SPC read for a response-VOLUME series — the count analogue of
    _control_read (whose wording is tuned for satisfaction scores)."""
    fmt = lambda v: f"{v:,.0f}"
    if not stats:
        return {"tone": "neutral", "label": "Early days",
                "headline": "Not enough history yet to tell a real swing from normal noise.",
                "detail": "A few more periods and we can flag genuine surges or drop-offs."}
    cl, sig, drift = stats["cl"], stats["signals"], stats["drift"]
    in_view = [i for i in sig if i >= view_from]
    earlier = [i for i in sig if i < view_from]
    labs = lambda idxs: ", ".join(series[i]["label"] for i in idxs[:4])
    if in_view:
        above = any(series[i]["value"] > stats["ucl"] for i in in_view)
        below = any(series[i]["value"] < stats["lcl"] for i in in_view)
        dirw, tone = (("a surge in", "good") if above and not below
                      else ("a drop in", "bad") if below and not above
                      else ("an unusual swing in", "neutral"))
        plural = len(in_view) != 1
        return {"tone": tone, "label": "Signal",
                "headline": (f"{len(in_view)} period{'s' if plural else ''} show {dirw} responses "
                             "beyond the usual range."),
                "detail": "Worth a look at what changed around " + labs(in_view) + "."}
    if drift:
        up = drift == "above"
        return {"tone": "good" if up else "bad", "label": "Trend",
                "headline": ("A steady run of busier-than-usual periods — participation may be picking up."
                             if up else
                             "A steady run of quieter-than-usual periods — participation may be tailing off."),
                "detail": ("Not one odd period but a consistent lean — "
                           + ("worth building on." if up else "worth understanding."))}
    if earlier:
        return {"tone": "neutral", "label": "In control",
                "headline": f"Recent periods are all within the usual range (around {fmt(cl)} responses).",
                "detail": "Earlier, " + labs(earlier) + " stood out — switch on Full history to see it."}
    return {"tone": "neutral", "label": "In control",
            "headline": f"Steady — every period sits within its usual range (around {fmt(cl)} responses).",
            "detail": "The small ups and downs are normal variation, not something to react to."}


def volume_view(atoms, survey_type, grain, window=8, show_full=False):
    """One survey type's response VOLUME over time, with an SPC control band so a
    genuine surge/drop is told apart from normal month-to-month wobble. The count
    analogue of trend_view."""
    raw = volume_series(atoms, survey_type, grain)            # [{key,label,count}]
    series = [{"key": p["key"], "label": p["label"], "value": p["count"], "n": p["count"]}
              for p in raw]
    title = survey_title(survey_type)
    total = _count(atoms[atoms["survey_type"] == survey_type])
    head = volume_headline(atoms, survey_type, grain)
    if not series:
        return {"has_data": False, "title": title, "total": 0, "headline": head}
    full_n = len(series)
    view_from = 0 if (show_full or full_n <= window) else full_n - window
    control = _control_stats(series, False)
    geom = _count_geom(series, control=control, window=window, show_full=show_full)
    return {"has_data": True, "title": title, "total": total, "series": series,
            "geom": geom, "headline": head, "n_periods": full_n,
            "control_read": _volume_read(control, series, view_from)}


def _event_periods(instances, grain):
    """Map each event GROUP (an F2 with its F3s) to the period of its date.
    Returns {group_key: (period_key, [instances])}."""
    groups = {}
    for inst in instances:
        groups.setdefault(_event_group_key(inst), []).append(inst)
    out = {}
    for gk, members in groups.items():
        date = members[0]["event_date"]
        if not date:
            continue
        key = period_keys(pd.Series([date]), grain).iloc[0]
        if key is None or key != key:
            continue
        out[gk] = (key, members)
    return out


def coverage_trend(atoms, instances, grain, window=8, show_full=False):
    """Event-coverage % over time: of the events that ran each period, the share that
    drew any feedback. A genuine proportion, so it carries a 95% confidence ribbon
    (few events => wide band => don't over-read a wobble) plus an SPC control band."""
    inst_with = (set(atoms["form_instance_id"].dropna().astype(int).tolist())
                 if _has(atoms) else set())
    per = {}                                           # period -> [with, total]
    for key, members in _event_periods(instances, grain).values():
        slot = per.setdefault(key, [0, 0])
        slot[1] += 1
        if any(i["id"] in inst_with for i in members):
            slot[0] += 1
    series = []
    for key in sorted(per):
        w, t = per[key]
        series.append({"key": key, "label": period_label(key, grain),
                       "value": (w / t * 100) if t else 0, "n": t, "with": w, "total": t})
    if not series:
        return {"has_data": False}
    full_n = len(series)
    view_from = 0 if (show_full or full_n <= window) else full_n - window
    control = _control_stats(series, True)
    conf = _conf_halfwidths(series, True)
    geom = _svg_geom(series, [], 100, True, window, show_full, control=control, conf=conf)
    return {"has_data": True, "series": series, "geom": geom, "latest": series[-1],
            "control_read": _control_read(control, series, True, view_from)}


def engagement_trend(atoms, instances, grain, window=8, show_full=False):
    """Responses-per-event over time — are events drawing DEEPER feedback, not just
    are there more events? Responses in a period / events that ran that period."""
    ev_per = {}
    for key, _members in _event_periods(instances, grain).values():
        ev_per[key] = ev_per.get(key, 0) + 1
    rows = {}
    if _has(atoms):
        keys = _keys(atoms, grain)
        resp = atoms.groupby(keys.values)["response_id"].nunique()
        for key, r in resp.items():
            if key is None or key != key:
                continue
            ev = ev_per.get(key, 0)
            if ev:
                rows[key] = r / ev
    series = [{"key": k, "label": period_label(k, grain), "value": rows[k], "n": ev_per.get(k, 0)}
              for k in sorted(rows)]
    if not series:
        return {"has_data": False}
    control = _control_stats(series, False)
    geom = _count_geom(series, control=control, window=window, show_full=show_full, decimals=1)
    return {"has_data": True, "series": series, "geom": geom, "latest": series[-1]}


def volume_by_unit2(atoms, org_struct, grain):
    """volume_by_unit + normalization (responses per event) + a latest-period
    movement read so the biggest RISERS/FALLERS can be highlighted (movers) and the
    rest dimmed — the by-area learning applied to org units."""
    base = volume_by_unit(atoms, org_struct)
    for r in base:
        r.update({"events": None, "per_event": None, "per_event_s": "—",
                  "delta": 0, "role": None})
    if not _has(atoms):
        return base
    kcol = _keys(atoms, grain)
    period_of = {idx: k for idx, k in kcol.items()}
    keys_all = sorted({k for k in period_of.values() if k is not None and k == k})
    cur_k = keys_all[-1] if keys_all else None
    prev_k = keys_all[-2] if len(keys_all) >= 2 else None
    paths = atoms["org_path"].astype(str)

    def sub_for(prefix):
        return atoms[paths.str.startswith(prefix)]

    deltas = []
    for r in base:
        p = r["path"]
        if not p or p == "External":
            continue
        sub = sub_for(p)
        ev = int(sub["form_instance_id"].dropna().nunique()) if _has(sub) else 0
        r["events"] = ev
        r["per_event"] = (r["count"] / ev) if ev else None
        r["per_event_s"] = f"{r['per_event']:.1f}" if r["per_event"] is not None else "—"
        if cur_k:
            sk = kcol.loc[sub.index]
            cur = int(sub[sk == cur_k]["response_id"].nunique()) if _has(sub) else 0
            prev = int(sub[sk == prev_k]["response_id"].nunique()) if (prev_k and _has(sub)) else 0
            r["cur"], r["prev"], r["delta"] = cur, prev, cur - prev
            deltas.append(r)
    if deltas:
        up = max(deltas, key=lambda r: r["delta"])
        down = min(deltas, key=lambda r: r["delta"])
        if up["delta"] >= 3:
            up["role"] = "up"
        if down["delta"] <= -3 and down is not up:
            down["role"] = "down"
    return base


def participation_read(volumes, by_unit, cover, grain):
    """ONE consolidated plain-language 'is participation healthy?' read for the top
    of the page — latest movement across all survey types, the coverage standing,
    and which unit is driving the change."""
    have = [v for v in volumes if v.get("has_data")]
    lat = sum((v["headline"].get("latest") or 0) for v in have)
    prv = sum((v["headline"].get("prev") or 0) for v in have
              if v["headline"].get("prev") is not None)
    total = sum(v.get("total", 0) for v in volumes)
    lab = next((v["headline"].get("latest_label") for v in have
                if v["headline"].get("latest_label")), None)
    delta = (lat - prv) if prv else None
    period_word = {"monthly": "month", "quarterly": "quarter", "yearly": "year"}.get(grain, "period")
    if not lab or delta is None or delta == 0:
        tone = "neutral"
        lead = f"Participation is holding steady — {total:,} responses on record so far."
    elif delta > 0:
        tone = "good"
        lead = (f"Participation is rising — {lat:,} responses this {period_word} ({lab}), "
                f"up {delta:,} on the {period_word} before.")
    else:
        tone = "watch"
        lead = (f"Participation eased off — {lat:,} responses this {period_word} ({lab}), "
                f"down {abs(delta):,} on the {period_word} before.")
    cov = (f"{cover['events_pct']:.0f}% of events and {cover['staff_pct']:.0f}% of staff "
           "have feedback on record.")
    movers = [r for r in by_unit if r.get("role")]
    driver = None
    if movers:
        up = next((r for r in movers if r["role"] == "up"), None)
        dn = next((r for r in movers if r["role"] == "down"), None)
        parts = []
        if up:
            parts.append(f"{up['label']} grew most (+{up['delta']:,})")
        if dn:
            parts.append(f"{dn['label']} fell most ({dn['delta']:,})")
        if parts:
            driver = "Where it moved this " + period_word + ": " + "; ".join(parts) + "."
    return {"tone": tone, "lead": lead, "coverage": cov, "driver": driver}


# =====================================================================
# PHASE 2 — relative comparison, confidence in plain words, like-for-like
# movement, and the PERSONAL COACH (praise · motivation · growth focus).
# =====================================================================

# Concrete, encouraging coaching tips per area — what to actually try.
DIM_TIP = {
    "Reliability": "confirming what you'll cover at the start and closing the loop at the end keeps this strong",
    "Responsiveness": "inviting questions early and following up on them is what lifts this",
    "Assurance": "a confident, well-prepared opening builds trust in your expertise fast",
    "Empathy": "checking in on participants by name and watching your pace makes this land",
    "Tangible": "clearer slides or handouts and a comfortable room set-up move this most",
}
SQD_TIP = {
    "SQD1": "even a quick status update while clients wait makes the time feel shorter",
    "SQD2": "walking clients through the steps up front sets clear expectations",
    "SQD3": "trimming or explaining each step makes the whole process feel simpler",
    "SQD4": "a one-page 'what to bring' guide is the fastest fix for findability",
    "SQD5": "explaining what each fee is for makes it feel fair",
    "SQD6": "a visible, uniform process reassures clients everyone is treated equally",
    "SQD7": "a warm greeting and a patient tone are what people remember",
    "SQD8": "confirming the client got exactly what they came for closes strong",
}

_CMP_THRESH = {"pct": 3.0, "mean7": 0.2, "index": 3.0}

# Honorifics to skip when addressing someone by first name in the coach panel.
_HONORIFICS = {"dr", "dra", "prof", "engr", "atty", "mr", "ms", "mrs", "hon", "rev", "sir", "maam", "ma'am"}


def _first_name(name):
    """First given name, skipping leading honorifics: 'Dr. Vince Reyes' -> 'Vince'."""
    for tok in (name or "").split():
        clean = tok.strip(".,").lower()
        if clean and clean not in _HONORIFICS:
            return tok.strip(".,")
    return (name or "there").split()[0] if name else "there"


def benchmark_value(atoms, role):
    """The peer average for a role across the given (already-scoped) atoms. For
    resource people the headline is the Quality Index (0-100), so the benchmark is
    the bureau-wide index; for walk-in servers it's the ARTA top-box %."""
    if role == "rp":
        idx, _ = eng.quality_index(atoms[atoms["survey_type"] == 3])
        return idx
    return eng.arta_topbox(atoms[atoms["survey_type"] == 1]).value


def overall_perception_default(atoms, survey_type):
    dim_map = eng.DIM_MAP_FORM2 if survey_type == 2 else eng.DIM_MAP_FORM3
    return eng.overall_perception(atoms[atoms["survey_type"] == survey_type], dim_map)


def compare_to_average(value, avg, scale):
    """Relative standing only (never a rank): above / around / below the average."""
    if value is None or avg is None:
        return None
    diff = value - avg
    thr = _CMP_THRESH.get(scale, 0.2)
    avg_s = f"{avg:.0f}%" if scale == "pct" else (f"{avg:.0f}" if scale == "index" else f"{avg:.1f}")
    if diff > thr:
        label, word = "above", "above"
    elif diff < -thr:
        label, word = "below", "below"
    else:
        label, word = "around", "right around"
    return {"label": label, "diff": diff, "avg": avg,
            "phrase": f"{word} the average of {avg_s}"}


def confidence_phrase(n):
    """Plain-language read on how much to trust a score, given how many responses
    back it. None when the base is comfortable."""
    if n is None:
        return None
    if n < 5:
        return f"Based on only {n} response(s) — treat this as an early hint, not an interpretation."
    if n < eng.N_MIN:
        return f"Based on {n} responses — a small sample, so read it with some caution."
    return None


def movement_phrase(res, grain="quarterly"):
    """Turn eng.pop_with_like_for_like into a warm, plain-language read on the most
    recent period: which way it moved, how much it matters, and — kept from the
    technical version — whether the change is genuine or just a different mix of
    activities/teams reporting. Returns {headline, takeaway, tone} (no jargon)."""
    raw, lfl = res["raw"], res["like_for_like"]
    if raw["delta"] is None or lfl["delta"] is None:
        return None
    rd, ld = raw["delta"], lfl["delta"]
    pct = (raw["unit"] == "pp")
    fmt = (lambda v: f"{abs(v):.0f} points") if pct else (lambda v: f"{abs(v):.1f}")
    period = {"quarterly": "quarter", "yearly": "year"}.get(grain, "period")
    # How big is the move, in feel? (bands are unit-aware)
    mag = abs(rd)
    flat = mag < (1.0 if pct else 0.1)
    big = mag >= (6.0 if pct else 0.6)

    if flat:
        return {"tone": "neutral",
                "headline": f"The latest {period} is holding the same level as the one before.",
                "takeaway": "Feedback is steady — no real change up or down."}

    size = "noticeably " if big else ""
    if rd > 0:
        headline = f"Feedback {size}ticked up in the latest {period} (about {fmt(rd)} higher)."
        tone = "good"
    else:
        headline = f"Feedback {size}eased back in the latest {period} (about {fmt(rd)} lower)."
        tone = "bad" if big else "neutral"

    # Composition guard, in human terms: did the same change survive when we compare
    # only the activities/teams that reported in BOTH periods?
    same_dir = (rd >= 0) == (ld >= 0)
    if not same_dir or abs(ld) < abs(rd) * 0.5:
        return {"tone": "neutral", "headline": headline,
                "takeaway": ("But that's mostly because a different mix of activities "
                             "responded this time — comparing only the ones in both "
                             f"{period}s, it's about the same. Don't read too much into it.")}
    verb = "real and worth building on" if rd > 0 else "real — worth a closer look at what changed"
    return {"tone": tone, "headline": headline,
            "takeaway": f"This holds up even comparing like-for-like, so the shift is {verb}."}


def coach_notes(person, card, trend, role, breakdown, cmp):
    """The personal-coach panel: read this person's pattern and speak to THEM —
    celebrate strengths, give honest encouragement, and name one growth focus.
    Praise-forward and never punitive; the goal is motivation, not a verdict."""
    name = person.get("name") or "This person"
    first = _first_name(name)
    scale = "pct"          # both the Quality Index (rp) and ARTA top-box are 0-100
    sp = stability_phrase(trend, scale)
    cons = card.get("consistency") or {}
    strongest = breakdown[0] if breakdown else None
    weakest = breakdown[-1] if breakdown and len(breakdown) > 1 else None

    praise, focus = [], []

    # ---- what's going well ----
    if strongest:
        praise.append(f"“{strongest['name']}” is your standout strength ({strongest['shown']}).")
    if sp["tone"] == "good":
        praise.append("Your scores have been climbing — that's real momentum.")
    if cmp and cmp["label"] == "above":
        praise.append(f"You're scoring {cmp['phrase']} — clearly appreciated by the people you serve.")
    if cons.get("stable"):
        praise.append("You deliver consistently from session to session — people know what to expect from you.")
    if not praise:
        praise.append("You're showing up and being rated — that's the foundation to build on.")

    # ---- where to focus next (framed as opportunity) ----
    if weakest and weakest is not strongest:
        key = weakest.get("raw") or weakest.get("item")
        tip = (DIM_TIP if role == "rp" else SQD_TIP).get(key, "")
        line = f"“{weakest['name']}” is your lowest area right now ({weakest['shown']})"
        focus.append(line + (f" — {tip}." if tip else "."))
    if cons.get("known") and not cons.get("stable"):
        focus.append("Your ratings swing between sessions — look back at your highest- and "
                     "lowest-rated ones and notice what was different. Repeating the good days is the win.")
    if sp["tone"] == "bad" and "inconsistent" not in sp["phrase"].lower():
        focus.append("Scores have dipped a little lately — a small reset on the basics usually turns it around.")

    # ---- tone, motivation, headline ----
    above_steady = bool(cmp and cmp["label"] == "above" and cons.get("stable"))
    if sp["tone"] == "good":
        tone = "celebrate"
        motivation = f"Keep doing exactly what you're doing, {first} — it's working."
        headline = f"{first}, you're on a strong upward roll."
    elif above_steady:
        tone = "celebrate"
        motivation = f"You're a dependable, top-tier performer, {first}. Thank you for the standard you set."
        headline = f"{first}, you're one to model."
    elif sp["tone"] == "bad":
        tone = "support"
        motivation = f"Everyone hits tougher stretches, {first}. You've scored well before — it's within reach again."
        headline = f"{first}, let's steady the ship together."
    elif cons.get("known") and not cons.get("stable"):
        tone = "steady"
        motivation = f"You've already shown you can score high, {first} — the goal now is making it every time."
        headline = f"{first}, your best is excellent — let's make it your normal."
    else:
        tone = "encourage"
        motivation = f"Solid work, {first}. One focused nudge lifts the whole experience."
        headline = f"{first}, you're doing well with clear room to grow."

    return {"first": first, "headline": headline, "praise": praise,
            "focus": focus, "motivation": motivation, "tone": tone,
            "trend_read": sp["phrase"], "comparison": cmp}


# ---- worth looking at (auto callouts on Pulse) --------------------------------

def worth_looking_at(atoms, staff):
    """Auto-surfaced, plain-language things to pay attention to. High
    interpretation, never an item code. Ordered most-actionable first."""
    out = []

    # 1) A walk-in item that's been weak across the most recent months.
    a = atoms[atoms["survey_type"] == 1]
    if _has(a):
        months = sorted(set(period_keys(a["event_date"], "monthly").tolist()))
        recent = months[-3:]
        for it in eng.ARTA_HEADLINE_ITEMS:
            weak_streak = 0
            for k in recent:
                sub = a[period_keys(a["event_date"], "monthly").values == k]
                det = eng.arta_item_detail(sub, it)
                if det.get("score") is not None and det["score"] < 75:
                    weak_streak += 1
            if weak_streak >= 2:
                out.append({
                    "tone": "bad",
                    "text": (f"Walk-in clients have flagged {SQD_CONCERN[it]} as a "
                             f"recurring problem across {weak_streak} of the last "
                             f"{len(recent)} months — this is worth fixing."),
                })
                break  # one ARTA callout is enough for the headline

    # 2) The activity/event with the biggest shortfall vs. expectations.
    insts = None
    for st_type, dim_map in ((2, eng.DIM_MAP_FORM2),):
        df = atoms[atoms["survey_type"] == st_type]
        worst = None
        for _fid, g in df.groupby("form_instance_id"):
            overall = eng.overall_perception(g, dim_map)
            expc = eng.expectation_A(g)
            if overall.value is not None and expc.value is not None:
                gap = overall.value - expc.value
                topic = g["topic"].iloc[0] if "topic" in g else "an event"
                if worst is None or gap < worst[0]:
                    worst = (gap, topic)
        if worst and worst[0] <= -0.4:
            out.append({
                "tone": "mid",
                "text": (f"“{worst[1]}” landed noticeably below what attendees "
                         f"expected — a good candidate for a debrief."),
            })

    # 3) A resource person whose scores swing a lot between sessions.
    for p in staff:
        if p.get("hidden_public") or _is_director(p):
            continue
        r = rp_slice(atoms, p["id"])
        if not _has(r):
            continue
        per_event = []
        for _fid, g in r.groupby("form_instance_id"):
            m = eng.overall_perception(g, eng.DIM_MAP_FORM3)
            if m.value is not None:
                per_event.append(m.value)
        c = consistency(per_event, scale="mean7")
        if c["known"] and not c["stable"]:
            out.append({
                "tone": "mid",
                "text": (f"{p['name']}'s session ratings swing a lot from event to "
                         f"event — the high and low sessions are worth comparing."),
            })
            break

    return out
