"""Per-activity report downloads carry the de-duplicated respondent comments.

The activity page (/reports/activities/<id>) shows a comments panel on screen, but
its Download button goes through a different path (/dashboard/export?visual=event)
than the /reports/export SERVQUAL/ARTA reports. This locks in that the per-activity
PDF / PPTX / XLSX now render those comments too — one flat ×N list, matching the
other downloadable reports — so the download and the screen can never disagree.
"""
import io
import zipfile

import pandas as pd
from reportlab.platypus import Paragraph

import app
import report_docs as rd
import dashboard_insights as di
import dashboard_docs as dd
import dashboard_export as dx

_ITEMS = ["A", "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9", "C"]


def _answers(fi_id, rid, value, *, osq=4.0, exp=6.0):
    rows = []
    for it in _ITEMS:
        v = exp if it == "A" else (osq if it == "C" else value)
        rows.append({"form_instance_id": fi_id, "response_id": rid, "survey_type": 2,
                     "is_na": False, "org_path": "BLHSD/HSDD/S1", "event_date": "2026-03-01",
                     "item_id": it, "value": float(v)})
    return rows


def _payload(comments):
    """A per-activity event payload — a real SERVQUAL scorecard plus the comments
    block the export path attaches (mirrors app._visual_payload's `event` branch)."""
    atoms = pd.DataFrame(_answers(100, 1, 6.6) + _answers(100, 2, 6.2))
    report = di.activity_servqual(atoms, [100])
    return {"ranked": [], "ymax": 7, "report": report, "bench": None,
            "demo": {"mf_ratio": "1:1"}, "journey_read": None, "name": "T",
            "date": "2026-03-01", "venue": "HQ", "organizer": None,
            "respondents": report["respondents"], "comments": comments}


def _comments(pairs, cap=None):
    grouped, shown, uniq = app._dedup_remarks(pairs, cap=cap or app._COMMENT_CAP)
    return {"items": grouped, "total": shown, "unique": uniq}


_VMETA = dx.VisualMeta(title="Activity — Report", place="HQ", period="2026-03-01",
                       unit="SERVQUAL perception, mean 1–7", notes=["n"],
                       generated_at="2026-07-09 00:00", n=2)


def _pdf_paragraphs(payload):
    """The flowable story event_pdf builds — captured before it's rendered to the
    embedded-font PDF (whose glyph-coded text isn't byte-searchable)."""
    captured = {}
    orig = rd._pdf_doc
    rd._pdf_doc = lambda meta, f: (captured.__setitem__("f", list(f)) or orig(meta, f))
    try:
        dd.event_pdf(payload, _VMETA)
    finally:
        rd._pdf_doc = orig
    return [p.text for p in captured["f"] if isinstance(p, Paragraph)]


def test_dedup_source_matches_the_on_screen_verbatims():
    # Same shape storage.verbatims_for_responses yields; flatten + dedup as the route does.
    verbatims = [
        {"response_id": 1, "remarks": "Very helpful facilitators", "notes": {}},
        {"response_id": 2, "remarks": "very  helpful facilitators", "notes": {}},   # folds -> ×2
        {"response_id": 3, "remarks": "Venue was too cold", "notes": {"B4": "More handouts"}},
        {"response_id": 4, "remarks": "none", "notes": {}},                          # throw-away
    ]
    quotes = di._flatten_quotes(verbatims)
    grouped, shown, uniq = app._dedup_remarks(((q["text"], "") for q in quotes),
                                              cap=app._COMMENT_CAP)
    texts = {g["text"]: g["count"] for g in grouped}
    assert texts == {"Very helpful facilitators": 2, "Venue was too cold": 1,
                     "More handouts": 1}          # dup collapsed, item note kept, "none" dropped
    assert shown == 4 and uniq == 3


def test_pdf_lists_deduplicated_comments_with_counts():
    P = _pdf_paragraphs(_payload(_comments(
        [("Great session", ""), ("great  session", ""), ("Too cold", "")])))
    assert any("Respondent comments (3)" in x for x in P)          # 3 meaningful remarks
    quotes = [x for x in P if x.startswith("“")]
    assert any("Great session" in x and "×2" in x for x in quotes)   # ×2 on the collapsed pair
    assert any("Too cold" in x for x in quotes)
    assert len(quotes) == 2                                        # 2 unique


def test_pdf_omits_section_when_no_comments():
    P = _pdf_paragraphs(_payload({"items": [], "total": 0, "unique": 0}))
    assert not any("Respondent comments" in x for x in P)


def test_pdf_notes_capped_overflow():
    cap = app._COMMENT_CAP
    items = [{"text": f"c{i}", "count": 1} for i in range(cap)]
    P = _pdf_paragraphs(_payload({"items": items, "total": cap + 5, "unique": cap + 5}))
    assert any("…and 5 more unique comments" in x for x in P)


def test_pptx_adds_in_their_words_slide():
    pptx = dd.event_pptx(_payload(_comments(
        [("Great session", ""), ("great  session", ""), ("Too cold", "")])), _VMETA)
    z = zipfile.ZipFile(io.BytesIO(pptx))
    blob = " ".join(z.read(n).decode("utf-8", "ignore")
                    for n in z.namelist() if n.endswith(".xml"))
    assert "In their words" in blob and "Great session" in blob and "×2" in blob


def test_xlsx_adds_comments_sheet():
    tables = dict(dx._tables("event", _payload(_comments(
        [("Great session", ""), ("great  session", ""), ("Too cold", "")]))))
    assert "Respondent comments" in tables
    df = tables["Respondent comments"]
    assert list(df.columns) == ["Comment", "Count"]
    assert int(df[df["Comment"] == "Great session"]["Count"].iloc[0]) == 2


def test_xlsx_omits_comments_sheet_when_empty():
    tables = dict(dx._tables("event", _payload({"items": [], "total": 0, "unique": 0})))
    assert "Respondent comments" not in tables


# ---------------------------------------------------------------------------
# The individual person report download carries comments too — its on-screen
# page shows a comments panel, so the PDF / PPTX / XLSX must match it.
# ---------------------------------------------------------------------------

def _person_payload(comments):
    return {"trend": [], "role": "rp", "ymax": 7, "breakdown": [], "breakdown_ymax": 7,
            "breakdown_title": "Breakdown",
            "card": {"rp": {"shown": "6.20", "band": "Good", "value": 6.2, "n": 10},
                     "ratings": 10, "consistency": {"phrase": "Scores are steady."}},
            "cmp": None, "coach": {}, "ta": {}, "yoy": {}, "peers": None, "badges": [],
            "scale": "mean7", "single": False, "position": None, "comments": comments}


_PVMETA = dx.VisualMeta(title="Jane — Performance", person="Jane", place="Section 1",
                        period="2026", unit="Mean rating, 1–7", notes=["n"],
                        generated_at="2026-07-09 00:00", n=10)


def _person_pdf_paragraphs(payload):
    captured = {}
    orig = rd._pdf_doc
    rd._pdf_doc = lambda meta, f: (captured.__setitem__("f", list(f)) or orig(meta, f))
    try:
        dd.person_pdf(payload, _PVMETA)
    finally:
        rd._pdf_doc = orig
    return [p.text for p in captured["f"] if isinstance(p, Paragraph)]


def test_person_pdf_lists_deduplicated_comments():
    P = _person_pdf_paragraphs(_person_payload(_comments(
        [("Clear speaker", ""), ("clear  speaker", ""), ("Ran over time", "")])))
    assert any("Respondent comments (3)" in x for x in P)
    quotes = [x for x in P if x.startswith("“")]
    assert any("Clear speaker" in x and "×2" in x for x in quotes)
    assert len(quotes) == 2


def test_person_pdf_omits_section_when_no_comments():
    P = _person_pdf_paragraphs(_person_payload({"items": [], "total": 0, "unique": 0}))
    assert not any("Respondent comments" in x for x in P)


def test_person_pptx_adds_in_their_words_slide():
    pptx = dd.person_pptx(_person_payload(_comments(
        [("Clear speaker", ""), ("clear  speaker", "")])), _PVMETA)
    z = zipfile.ZipFile(io.BytesIO(pptx))
    blob = " ".join(z.read(n).decode("utf-8", "ignore")
                    for n in z.namelist() if n.endswith(".xml"))
    assert "In their words" in blob and "Clear speaker" in blob and "×2" in blob


def test_person_xlsx_adds_comments_sheet():
    tables = dict(dx._tables("person", _person_payload(_comments(
        [("Clear speaker", ""), ("clear  speaker", ""), ("Ran over time", "")]))))
    assert "Respondent comments" in tables
    df = tables["Respondent comments"]
    assert list(df.columns) == ["Comment", "Count"]
    assert int(df[df["Comment"] == "Clear speaker"]["Count"].iloc[0]) == 2


def test_person_xlsx_omits_comments_sheet_when_empty():
    tables = dict(dx._tables("person", _person_payload({"items": [], "total": 0, "unique": 0})))
    assert "Respondent comments" not in tables
