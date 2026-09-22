"""Trends Phase D: segment-split (modality) + verbatim-sentiment trend.
Pure functions exercised against small synthetic atoms — no DB."""
import pandas as pd
import css_is_engine as eng
import dashboard_insights as di


def _row(rid, item, val, date, modality, st=2):
    return {"response_id": rid, "survey_type": st, "item_id": item,
            "value": float(val), "is_na": False, "event_date": date,
            "modality": modality}


def _resp(rid, date, modality, scores, st=2):
    """One respondent's answers across the SERVQUAL items (B1..B9)."""
    items = ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9"]
    return [_row(rid, it, scores, date, modality, st) for it in items]


def _atoms(rows):
    return eng.assign_periods(pd.DataFrame(rows))


# ---- segment_trend -----------------------------------------------------------

def test_segment_trend_splits_by_modality():
    # Two quarters, two modalities. Online rated low (5s), f2f rated top (7s),
    # with enough respondents in each slice to clear the min-N guard.
    rows = []
    rid = 1
    for q_date in ("2026-01-15", "2026-04-15"):
        for _ in range(6):
            rows += _resp(rid, q_date, "online", 5); rid += 1
            rows += _resp(rid, q_date, "f2f", 7); rid += 1
    seg = di.segment_trend(_atoms(rows), 2, "quarterly", "modality",
                           labels={"online": "Online", "f2f": "Face-to-face"},
                           metric="topbox", min_n=3)
    assert seg["has_data"] is True
    assert set(seg["segments"]) == {"Online", "Face-to-face"}
    # raw series carried for non-HTML renderers
    names = {s["name"] for s in seg["series_raw"]}
    assert names == {"Online", "Face-to-face"}
    # f2f (all 7s -> 100% top-box) runs ahead of online (all 5s -> 0%)
    latest = {s["name"]: [p["value"] for p in s["points"] if p["value"] is not None][-1]
              for s in seg["series_raw"]}
    assert latest["Face-to-face"] > latest["Online"]
    assert seg["read"]["tone"] == "watch"


def test_segment_trend_surfaces_a_third_hybrid_segment():
    # Same grouping logic as the two-way split above, but with a third modality
    # value present. segment_trend() is generic — it should surface a "Hybrid"
    # line the moment the labels dict names it, with no code change needed.
    rows = []
    rid = 1
    for q_date in ("2026-01-15", "2026-04-15"):
        for _ in range(6):
            rows += _resp(rid, q_date, "online", 5); rid += 1
            rows += _resp(rid, q_date, "f2f", 7); rid += 1
            rows += _resp(rid, q_date, "hybrid", 6); rid += 1
    seg = di.segment_trend(_atoms(rows), 2, "quarterly", "modality",
                           labels={"online": "Online", "f2f": "Face-to-face", "hybrid": "Hybrid"},
                           metric="topbox", min_n=3)
    assert seg["has_data"] is True
    assert set(seg["segments"]) == {"Online", "Face-to-face", "Hybrid"}
    names = {s["name"] for s in seg["series_raw"]}
    assert names == {"Online", "Face-to-face", "Hybrid"}


def test_segment_trend_drops_thin_slice_and_bails():
    # 6 face-to-face respondents but only 1 online -> online is dropped, and with
    # fewer than two readable segments the split isn't shown.
    rows = []
    rid = 1
    for _ in range(6):
        rows += _resp(rid, "2026-01-15", "f2f", 6); rid += 1
    rows += _resp(rid, "2026-01-15", "online", 6)
    seg = di.segment_trend(_atoms(rows), 2, "quarterly", "modality",
                           labels={"online": "Online", "f2f": "Face-to-face"}, min_n=3)
    assert seg["has_data"] is False
    assert "Online" in (seg.get("dropped") or [])
    assert seg.get("only") == "Face-to-face"


def test_segment_trend_missing_column():
    rows = _resp(1, "2026-01-15", "f2f", 6)
    df = _atoms(rows).drop(columns=["modality"])
    assert di.segment_trend(df, 2, "quarterly", "modality")["has_data"] is False


# ---- sentiment_trend ---------------------------------------------------------

def _verb(rid, text):
    return {"response_id": rid, "remarks": text, "notes": {}, "when": "", "form_id": "",
            "topic": ""}


def test_sentiment_trend_tracks_tone_over_periods():
    # Q1 comments mostly positive, Q2 mostly complaints -> a cooling trend.
    rows = []
    verbs = []
    rid = 1
    for _ in range(4):                       # Q1: praise
        rows += _resp(rid, "2026-01-15", "f2f", 6)
        verbs.append(_verb(rid, "very helpful and clear, thank you")); rid += 1
    for _ in range(4):                       # Q2: complaints
        rows += _resp(rid, "2026-04-15", "f2f", 6)
        verbs.append(_verb(rid, "the venue was a problem and it was confusing")); rid += 1
    sent = di.sentiment_trend(_atoms(rows), verbs, 2, "quarterly")
    assert sent["has_data"] is True
    vals = [p["value"] for p in sent["series"]]
    assert vals[0] > vals[-1]                # tone cooled
    assert sent["read"]["tone"] == "bad"


def test_sentiment_trend_no_comments():
    rows = _resp(1, "2026-01-15", "f2f", 6)
    assert di.sentiment_trend(_atoms(rows), [], 2, "quarterly")["has_data"] is False


def test_sentiment_trend_honors_overrides():
    rows = _resp(1, "2026-01-15", "f2f", 6)
    verbs = [_verb(1, "the venue was a problem")]    # auto -> improve
    base = di.sentiment_trend(_atoms(rows), verbs, 2, "quarterly")
    assert base["series"][0]["value"] == 0.0
    forced = di.sentiment_trend(_atoms(rows), verbs, 2, "quarterly",
                                overrides={(1, ""): "appreciate"})
    assert forced["series"][0]["value"] == 100.0
