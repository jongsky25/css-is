"""Type-3 resource-person PowerPoint roster export.

/reports/rp-roster-export builds one slide per activity (Form 3.0 style),
listing every resource person scored on it with their Overall Service Quality
(item C band) and SERVQUAL Score (dimension average minus expectation). These
lock:
  * the deck honors the same quarter (period) filter as the on-screen report;
  * a multi-speaker activity gets one table row per resource person;
  * the Activity filter narrows the deck to just that one activity's slide.
"""
import io
import storage as st
from pptx import Presentation

# A full Form-3 SERVQUAL answer set (one item per dimension) so each speaker
# scores cleanly. Distinct B-item values per person so their SERVQUAL/OSQ differ.
_F3_ANSWERS_A = [("A", 6), ("B1", 6), ("B2", 6), ("B3", 6), ("B4", 6),
                  ("B5", 6), ("B6", 6), ("B7", 6), ("B8", 6), ("B9", 6), ("C", 4)]
_F3_ANSWERS_B = [("A", 6), ("B1", 7), ("B2", 7), ("B3", 7), ("B4", 7),
                  ("B5", 7), ("B6", 7), ("B7", 7), ("B8", 7), ("B9", 7), ("C", 4)]


def _two_internal_rps(db_path):
    conn = st.connect(db_path)
    rows = conn.execute(
        "SELECT id FROM resource_person WHERE is_internal=1 ORDER BY id LIMIT 2").fetchall()
    conn.close()
    return [r[0] for r in rows]


def _make_bureau_multi(manager, db_path, name, date, venue, rp_ids, topics):
    r = manager.post("/create", data={
        "event_type": "bureau", "activity_name": name,
        "event_date": date, "venue": venue, "qr_mode": "combined",
        "rp_id": [str(x) for x in rp_ids], "topic": topics,
    }, follow_redirects=True)
    assert r.status_code == 200, r.text[:400]
    conn = st.connect(db_path)
    ev = conn.execute("SELECT id FROM event WHERE title=? ORDER BY id DESC LIMIT 1",
                      (name,)).fetchone()[0]
    f3s = [row[0] for row in conn.execute(
        "SELECT fi.id FROM event_form ef JOIN form_instance fi ON fi.id = ef.form_instance_id "
        "WHERE ef.event_id=? AND fi.survey_type=3 ORDER BY fi.id", (ev,)).fetchall()]
    conn.close()
    return ev, f3s


def _add_responses(db_path, fid, answers, n=3):
    conn = st.connect(db_path)
    for _ in range(n):
        st.record_response(conn, fid, answers)
    conn.close()


def _pptx_slides(data):
    """[{'texts': [...], 'rows': [[cell,...],...]}] — one entry per slide that
    carries a table, with every text-box string on that slide (so a test can
    find the slide for a given activity by its headline) plus the table rows."""
    prs = Presentation(io.BytesIO(data))
    out = []
    for slide in prs.slides:
        texts, rows = [], None
        for shape in slide.shapes:
            if shape.has_table:
                t = shape.table
                rows = [[t.cell(r, c).text for c in range(len(t.columns))]
                        for r in range(len(t.rows))]
            elif shape.has_text_frame and shape.text_frame.text:
                texts.append(shape.text_frame.text)
        if rows is not None:
            out.append({"texts": texts, "rows": rows})
    return out


def _slide_for(slides, name):
    return next(s for s in slides if any(name in t for t in s["texts"]))


def test_rp_roster_export_lists_every_speaker_per_activity(manager, app_mod):
    db_path = app_mod.DB
    rp1, rp2 = _two_internal_rps(db_path)
    # A venue string unique to this test — build_events groups activities by
    # (date, venue, lead org), and other suites reuse plain dates like this one,
    # so a generic venue would silently merge this activity into an unrelated
    # test's event group.
    _ev, (f3a, f3b) = _make_bureau_multi(
        manager, db_path, "RP Roster Alpha", "2026-05-14", "RP Roster Test Venue Alpha",
        [rp1, rp2], ["Session One", "Session Two"])
    _add_responses(db_path, f3a, _F3_ANSWERS_A, 3)
    _add_responses(db_path, f3b, _F3_ANSWERS_B, 3)
    app_mod.invalidate_atoms()

    r = manager.get("/reports/rp-roster-export", params={"period": "quarter:2026-Q2"})
    assert r.status_code == 200
    assert r.headers["content-type"] == (
        "application/vnd.openxmlformats-officedocument.presentationml.presentation")
    assert "attachment" in r.headers["content-disposition"]

    slides = _pptx_slides(r.content)
    slide = _slide_for(slides, "RP Roster Alpha")
    header, *rows = slide["rows"]
    assert header == ["#", "Staff Name", "Overall Service Quality", "SERVQUAL Score"]
    assert len(rows) == 2                       # both resource persons listed, one table
    names = {row[1] for row in rows}
    assert len(names) == 2                       # two distinct staff names, one per row
    for row in rows:
        assert "Excellent" in row[2] or "Good" in row[2] or "Fair" in row[2] or "Poor" in row[2]
        assert row[3] not in ("", "—")


def test_rp_roster_export_merges_one_persons_multiple_sessions(manager, app_mod):
    """A resource person who ran more than one session within the same activity
    (same date + venue — e.g. several batches of the same training) must appear
    ONCE on that activity's slide, not once per session. Regression for a real
    prod roster that listed the same name 2-3x with different scores because the
    date+venue grouping can't otherwise tell sessions of the same person apart."""
    db_path = app_mod.DB
    rp1 = _two_internal_rps(db_path)[0]
    _ev, (f3a, f3b) = _make_bureau_multi(
        manager, db_path, "RP Roster Merge", "2026-05-18", "RP Roster Test Venue Merge",
        [rp1, rp1], ["Batch 1", "Batch 2"])
    _add_responses(db_path, f3a, _F3_ANSWERS_A, 3)
    _add_responses(db_path, f3b, _F3_ANSWERS_B, 3)
    app_mod.invalidate_atoms()

    r = manager.get("/reports/rp-roster-export", params={"period": "quarter:2026-Q2"})
    assert r.status_code == 200
    slides = _pptx_slides(r.content)
    slide = _slide_for(slides, "RP Roster Merge")
    header, *rows = slide["rows"]
    assert len(rows) == 1                        # one person, one row — not two
    assert rows[0][3] not in ("", "—")


def test_rp_roster_export_omits_the_director(manager, app_mod):
    """The Director rotates too fast to be a meaningful named roster entry —
    always left off the per-activity roster, identified live by position
    ('Director...') rather than a per-person flag, so it applies to whoever
    holds the role without needing to be re-applied on turnover."""
    db_path = app_mod.DB
    rp1 = _two_internal_rps(db_path)[0]
    conn = st.connect(db_path)
    sec = conn.execute("SELECT id FROM org_unit WHERE level='section' LIMIT 1").fetchone()[0]
    director_id = st.add_rp(conn, "Test Director Person", is_internal=True,
                            org_unit_id=sec, position="Director IV")
    conn.close()

    _ev, (f3_speaker, f3_director) = _make_bureau_multi(
        manager, db_path, "RP Roster Director Test", "2026-05-19",
        "RP Roster Test Venue Director", [rp1, director_id], ["Session One", "Director remarks"])
    _add_responses(db_path, f3_speaker, _F3_ANSWERS_A, 3)
    _add_responses(db_path, f3_director, _F3_ANSWERS_B, 3)
    app_mod.invalidate_atoms()

    r = manager.get("/reports/rp-roster-export", params={"period": "quarter:2026-Q2"})
    assert r.status_code == 200
    slides = _pptx_slides(r.content)
    slide = _slide_for(slides, "RP Roster Director Test")
    header, *rows = slide["rows"]
    assert len(rows) == 1                         # only the non-director speaker
    assert "Test Director Person" not in [row[1] for row in rows]


def test_rp_roster_export_honors_quarter_filter(manager, app_mod):
    """An activity outside the requested quarter contributes no slide."""
    db_path = app_mod.DB
    rp1 = _two_internal_rps(db_path)[0]
    _ev, (f3,) = _make_bureau_multi(
        manager, db_path, "RP Roster OffQuarter", "2026-01-15", "RP Roster Test Venue Z",
        [rp1], ["Q1 Session"])
    _add_responses(db_path, f3, _F3_ANSWERS_A, 3)
    app_mod.invalidate_atoms()

    r = manager.get("/reports/rp-roster-export", params={"period": "quarter:2026-Q2"})
    assert r.status_code == 200
    slides = _pptx_slides(r.content)
    assert not any(any("RP Roster OffQuarter" in t for t in s["texts"]) for s in slides)


def test_rp_roster_export_activity_filter_narrows_to_one_slide(manager, app_mod):
    db_path = app_mod.DB
    rp1, rp2 = _two_internal_rps(db_path)
    _make_bureau_multi(manager, db_path, "RP Roster Narrow One", "2026-05-16",
                       "RP Roster Test Venue Narrow-1", [rp1], ["Talk"])
    _ev2, (f3b,) = _make_bureau_multi(manager, db_path, "RP Roster Narrow Two", "2026-05-17",
                                      "RP Roster Test Venue Narrow-2", [rp2], ["Talk 2"])
    _add_responses(db_path, f3b, _F3_ANSWERS_B, 3)
    app_mod.invalidate_atoms()

    from app import _rp_activity_options, get_atoms
    conn = st.connect(db_path)
    atoms = get_atoms(conn)
    opts = _rp_activity_options(conn, atoms)
    conn.close()
    picked = next(o for o in opts if o["text"] == "RP Roster Narrow Two")

    r = manager.get("/reports/rp-roster-export", params={"activity": picked["value"]})
    assert r.status_code == 200
    slides = _pptx_slides(r.content)
    assert len(slides) == 1                      # scoped to exactly the one picked activity
    assert any("RP Roster Narrow Two" in t for t in slides[0]["texts"])
    assert not any(
        any("RP Roster Narrow One" in t for t in s["texts"]) for s in slides)
