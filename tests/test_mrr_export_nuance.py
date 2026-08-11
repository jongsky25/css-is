"""The MRR activity workbook must read differently row by row.

Two problems this locks down:

1. Every row used to carry the SAME Action / Next-Steps / Resources text. Next
   Steps was a hardcoded sentence; Action and Resources were keyed on a weakest
   dimension drawn from only three event-about dimensions, so the whole bureau's
   activities shared a handful of strings.
2. The COMMENTS block filled up with the quick-pick options respondents merely
   TAPPED on the rating form (chips are written straight into the free-text box),
   which buried the words people actually typed and repeated the same canned
   phrases down every row.

The rule now: typed words take every comment slot they can fill, quick-picks only
backfill what's left, and the backfill rotates across the sheet's rows.
"""
import io
from datetime import timedelta

from openpyxl import load_workbook

import storage as st

_ITEMS = ["B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9"]


def _activity(app_mod, topic, *, days_ago, scores, osq, exp=6.0, remarks=(),
              notes=(), modality=None, attendance=None):
    """One standalone Form-2 activity with a real SERVQUAL scorecard.

    `scores` maps an item id to its value, defaulting the rest to 6; `remarks` is
    one comment string per response; `notes` is {item: text} per response.
    """
    conn = st.connect(app_mod.DB)
    date = (app_mod._today_local() - timedelta(days=days_ago)).isoformat()
    fid = st.create_form_instance(conn, 2, "F2", date, topic=topic, venue=f"Venue {topic}",
                                  modality=modality, created_by="me@x")
    if attendance:
        conn.execute("UPDATE form_instance SET attendance=? WHERE id=?", (attendance, fid))
    rows = max(len(remarks), len(notes), 1)
    for i in range(rows):
        answers = [("A", exp), ("C", osq)] + [(it, scores.get(it, 6)) for it in _ITEMS]
        st.record_response(conn, fid, answers,
                           remarks=(remarks[i] if i < len(remarks) else None),
                           item_remarks=(notes[i] if i < len(notes) else None))
    conn.commit(); conn.close()
    app_mod.invalidate_atoms()
    return fid


def _sheet1(client):
    r = client.get("/reports/activities-export")
    assert r.status_code == 200
    return load_workbook(io.BytesIO(r.content))["AGENDA 4_Sheet1"]


def _rows(ws):
    """{activity title fragment -> (findings, analysis, action, next_steps, resources)}."""
    out = []
    for row in range(7, ws.max_row + 1):
        cells = [ws.cell(row=row, column=c).value for c in range(2, 7)]
        if any(cells):
            out.append(tuple(cells))
    return out


def _row_for(ws, topic):
    return next(r for r in _rows(ws) if topic in (r[0] or ""))


# ---- 1. typed words come first ------------------------------------------------

def test_typed_comments_outrank_quick_picks(manager, app_mod):
    """A chip-only remark must not push a typed comment out of the cell."""
    topic = "MRR Nuance Typed AAA"
    typed = "The handouts arrived late and the room was freezing"
    _activity(app_mod, topic, days_ago=9, scores={"B5": 4}, osq=3,
              remarks=["Knowledgeable, Well-prepared", "Engaging, Helpful",
                       "Knowledgeable, Engaging", typed])
    findings = _row_for(_sheet1(manager), topic)[0]
    body = findings.split("COMMENTS:", 1)[1]
    lines = [ln for ln in body.splitlines() if ln.strip()]
    assert typed in lines[0], "the words someone typed must lead the comment list"
    assert "quick-pick option" in body, "chips still backfill the slots typing left empty"
    assert lines[0].count("quick-pick") == 0


def test_item_notes_count_as_typed_words(manager, app_mod):
    """Per-question notes are always typed — they belong in the report."""
    topic = "MRR Nuance Notes BBB"
    _activity(app_mod, topic, days_ago=8, scores={"B9": 4}, osq=3,
              remarks=["Well-prepared"], notes=[{"B9": "Projector kept cutting out"}])
    findings = _row_for(_sheet1(manager), topic)[0]
    assert "Projector kept cutting out" in findings


def test_quick_picks_are_labelled_never_passed_off_as_verbatims(manager, app_mod):
    topic = "MRR Nuance Label CCC"
    _activity(app_mod, topic, days_ago=7, scores={"B5": 4}, osq=3,
              remarks=["Wanted more Q&A", "Wanted more Q&A"])
    findings = _row_for(_sheet1(manager), topic)[0]
    assert "“Wanted more Q&A” (quick-pick option · chosen by 2" in findings


def test_no_comments_says_so_instead_of_a_dangling_header(manager, app_mod):
    topic = "MRR Nuance Silent DDD"
    _activity(app_mod, topic, days_ago=6, scores={}, osq=4)
    findings = _row_for(_sheet1(manager), topic)[0]
    assert "No written comments were submitted" in findings


# ---- 2. quick-picks spread across rows ----------------------------------------

def test_chip_backfill_rotates_across_rows(app_mod):
    """Three activities whose respondents all tapped the same top option must not
    all show that option — the sheet rotates to each row's next-best pick."""
    picks = [{"text": "Knowledgeable", "count": 9},
             {"text": "Engaging", "count": 5},
             {"text": "Helpful", "count": 3}]
    events = [{"respondents": 9, "comments": [], "chip_picks": list(picks)} for _ in range(3)]
    spread = {}
    firsts = [app_mod._activity_comment_lines(e, spread)[0] for e in events]
    assert len({f for f in firsts}) == 3, (
        "each row should lead with a different quick-pick option, got: " + repr(firsts))
    # Row 1 leads with the option most of its respondents picked; row 2 opens with
    # the one no row has shown yet; row 3 with the least-shown of what's left.
    assert "Knowledgeable" in firsts[0] and "Helpful" in firsts[1] and "Engaging" in firsts[2]


def test_chip_backfill_repeats_only_when_a_row_has_nothing_else(app_mod):
    spread = {"Knowledgeable": 4}
    only = [{"text": "Knowledgeable", "count": 6}]
    lines = app_mod._activity_comment_lines(
        {"respondents": 6, "comments": [], "chip_picks": only}, spread)
    assert "Knowledgeable" in lines[0], "an activity with one option still reports it"


def test_a_full_cell_of_typed_words_consumes_no_chip_budget(app_mod):
    """A row that never needed the backfill must not make the next row skip an
    option it has not shown yet."""
    spread = {}
    typed = [{"text": f"Real comment {i}", "count": 1} for i in range(5)]
    app_mod._activity_comment_lines(
        {"respondents": 5, "comments": typed,
         "chip_picks": [{"text": "Knowledgeable", "count": 5}]}, spread)
    assert spread == {}


# ---- 3. the four analysis columns differ row to row ---------------------------

def test_analysis_columns_differ_between_activities(manager, app_mod):
    """Different weakest dimensions, bands and dates => four distinct columns."""
    a = "MRR Nuance Col EEE"      # Responsiveness (B5) weakest, virtual
    b = "MRR Nuance Col FFF"      # Tangible (B8/B9) weakest, face-to-face
    c = "MRR Nuance Col GGG"      # nothing genuinely weak
    _activity(app_mod, a, days_ago=20, scores={"B5": 3.0}, osq=2, modality="online",
              attendance=40)
    _activity(app_mod, b, days_ago=12, scores={"B8": 4.0, "B9": 4.0}, osq=3, modality="f2f",
              attendance=25)
    _activity(app_mod, c, days_ago=4, scores={}, osq=4, modality="f2f", attendance=18)
    ws = _sheet1(manager)
    rows = [_row_for(ws, t) for t in (a, b, c)]
    for col, label in ((1, "Analysis"), (2, "Action"), (3, "Next Steps"), (4, "Resources")):
        texts = [r[col] for r in rows]
        assert len(set(texts)) == 3, f"{label} repeated across activities: {texts}"


def test_next_steps_are_pinned_to_each_activity_date(manager, app_mod):
    topic = "MRR Nuance Date HHH"
    fid = _activity(app_mod, topic, days_ago=30, scores={"B5": 4}, osq=3)
    assert fid
    day = (app_mod._today_local() - timedelta(days=30))
    next_steps = _row_for(_sheet1(manager), topic)[3]
    assert day.strftime("%B") in next_steps and str(day.year) in next_steps
    assert topic in next_steps, "the timeline should name the activity it belongs to"


def test_action_names_the_weakest_dimension_and_scales_its_advice(manager, app_mod):
    weak = "MRR Nuance Weak III"
    fine = "MRR Nuance Fine JJJ"
    _activity(app_mod, weak, days_ago=15, scores={"B5": 2.5}, osq=2)
    _activity(app_mod, fine, days_ago=14, scores={}, osq=4)
    ws = _sheet1(manager)
    weak_action = _row_for(ws, weak)[2]
    fine_action = _row_for(ws, fine)[2]
    assert "Responsiveness" in weak_action and weak_action.startswith("Target")
    assert "No area needs correcting" in fine_action, (
        "an evenly strong activity must not be told to fix its lowest dimension")
    assert "None identified from the feedback" in _row_for(ws, fine)[4]


def test_action_picks_up_what_respondents_asked_for(manager, app_mod):
    """An improvable option enough people tapped becomes part of the plan."""
    topic = "MRR Nuance Ask KKK"
    _activity(app_mod, topic, days_ago=11, scores={"B5": 4}, osq=3,
              remarks=["Wanted more Q&A"] * 4)
    action = _row_for(_sheet1(manager), topic)[2]
    assert "Wanted more Q&A" in action and "open forum" in action


def test_resources_split_on_modality(manager, app_mod):
    online = "MRR Nuance Online LLL"
    f2f = "MRR Nuance F2F MMM"
    _activity(app_mod, online, days_ago=19, scores={"B8": 4.0, "B9": 4.0}, osq=3,
              modality="online")
    _activity(app_mod, f2f, days_ago=18, scores={"B8": 4.0, "B9": 4.0}, osq=3, modality="f2f")
    ws = _sheet1(manager)
    assert "online-meeting platform" in _row_for(ws, online)[4]
    assert "venue" in _row_for(ws, f2f)[4].lower()


def test_page_preview_matches_the_downloaded_draft(manager, app_mod):
    """The editable MRR form on the activity page and the Excel cell are the same
    text — the page must draft from the same five-dimension scorecard."""
    topic = "MRR Nuance Preview NNN"
    fid = _activity(app_mod, topic, days_ago=13, scores={"B6": 4.0}, osq=3)
    html = manager.get(f"/reports/activities/{fid}").text
    action = _row_for(_sheet1(manager), topic)[2]
    # The textarea carries the same drafted sentence (HTML-escaped quotes aside).
    assert action.split(".")[0].split("“")[0].strip()[:40] in html
    assert "Assurance" in action, "the five-dimension scorecard must reach the page draft"
