"""Spot Feedback #28 — filter the Resource-person (Type 3) report by Activity.

The consolidated RP report at /reports?type=3 gains an Activity dropdown so a
reviewer can narrow the SERVQUAL numbers to a single activity. These lock:
  * the dropdown lists activities that carry resource-person responses;
  * selecting one narrows the report to exactly that activity's responses;
  * the filter is Type-3 only (a stray param on Type 1/2 is ignored, no crash).
"""
import re
import storage as st

# A full Form-3 SERVQUAL answer set (one item per dimension) so the report has data.
_F3_ANSWERS = [("A", 6), ("B1", 6), ("B2", 6), ("B3", 6), ("B4", 6),
               ("B5", 6), ("B6", 6), ("B7", 6), ("B8", 6), ("B9", 6), ("C", 4)]


def _one_internal_rp(db_path):
    conn = st.connect(db_path)
    row = conn.execute(
        "SELECT id FROM resource_person WHERE is_internal=1 ORDER BY id LIMIT 1").fetchone()
    conn.close()
    return row[0]


def _make_bureau(manager, db_path, name, date, venue):
    """Create a bureau activity (F2 + one F3 speaker) named `name`. Returns the
    event id and its first Form-3 instance id (the response target). Distinct
    date+venue per call so build_events keeps them as separate event groups."""
    rp = _one_internal_rp(db_path)
    r = manager.post("/create", data={
        "event_type": "bureau", "activity_name": name,
        "event_date": date, "venue": venue, "qr_mode": "combined",
        "rp_id": [str(rp)], "topic": ["Session topic"],
    }, follow_redirects=True)
    assert r.status_code == 200, r.text[:400]
    conn = st.connect(db_path)
    ev = conn.execute("SELECT id FROM event WHERE title=? ORDER BY id DESC LIMIT 1",
                      (name,)).fetchone()[0]
    f3 = conn.execute(
        "SELECT fi.id FROM event_form ef JOIN form_instance fi ON fi.id = ef.form_instance_id "
        "WHERE ef.event_id=? AND fi.survey_type=3 ORDER BY fi.id LIMIT 1", (ev,)).fetchone()[0]
    conn.close()
    return ev, f3


def _add_responses(db_path, fid, n):
    conn = st.connect(db_path)
    for _ in range(n):
        st.record_response(conn, fid, _F3_ANSWERS)
    conn.close()


def _option_value(body, name):
    """The <option> value the Activity dropdown rendered for activity `name`."""
    m = re.search(rf'<option value="(\d+)"[^>]*>{re.escape(name)} —', body)
    return m.group(1) if m else None


def test_rp_report_activity_filter(manager, app_mod):
    db_path = app_mod.DB
    _a_ev, a_f3 = _make_bureau(manager, db_path, "RP Filter Alpha", "2026-06-10", "Hall A")
    _b_ev, b_f3 = _make_bureau(manager, db_path, "RP Filter Bravo", "2026-06-11", "Hall B")
    _add_responses(db_path, a_f3, 3)             # Alpha: 3 responses
    _add_responses(db_path, b_f3, 2)             # Bravo: 2
    app_mod.invalidate_atoms()                   # full blocking rebuild on next request

    # The dropdown offers both activities on the Type-3 report.
    body = manager.get("/reports", params={"type": 3}).text
    assert 'name="activity"' in body             # the new filter control exists
    assert 'href="/dashboard/people">View other resource persons' in body
    a_val = _option_value(body, "RP Filter Alpha")
    b_val = _option_value(body, "RP Filter Bravo")
    assert a_val and b_val, "both activities should appear as filter options"

    # Narrow to Alpha → exactly its 3 responses; its name shows + the option is selected.
    ra = manager.get("/reports", params={"type": 3, "activity": a_val})
    assert ra.status_code == 200
    assert "3 rated respondent(s)" in ra.text
    assert "3 total submission(s)" in ra.text
    assert "RP Filter Alpha" in ra.text
    assert f'value="{a_val}" selected' in ra.text

    # Narrow to Bravo → its 2 responses (proves the filter actually restricts).
    rb = manager.get("/reports", params={"type": 3, "activity": b_val})
    assert "2 rated respondent(s)" in rb.text
    assert "2 total submission(s)" in rb.text


def test_activity_filter_is_type3_only(manager):
    """A stray activity param on Type 1/2 is ignored — no narrowing, no crash."""
    assert manager.get("/reports", params={"type": 1, "activity": "999999"}).status_code == 200
    assert manager.get("/reports", params={"type": 2, "activity": "999999"}).status_code == 200


def test_linked_staff_sees_own_results_by_activity(viewer, manager, app_mod):
    db_path = app_mod.DB
    own_rp = _one_internal_rp(db_path)
    conn = st.connect(db_path)
    conn.execute("UPDATE admin_user SET rp_id=? WHERE username=?",
                 (own_rp, "viewer@test.local"))
    conn.commit()
    conn.close()

    _a_ev, a_f3 = _make_bureau(manager, db_path, "My RP Alpha", "2026-07-10", "Hall A")
    _b_ev, b_f3 = _make_bureau(manager, db_path, "My RP Bravo", "2026-07-11", "Hall B")
    _add_responses(db_path, a_f3, 3)
    _add_responses(db_path, b_f3, 2)
    app_mod.invalidate_atoms()

    body = viewer.get("/reports", params={"type": 3}).text
    assert "Your RP results by activity" in body
    assert "My RP Alpha" in body and "My RP Bravo" in body
    a_val = _option_value(body, "My RP Alpha")
    assert a_val
    narrowed = viewer.get("/reports", params={"type": 3, "activity": a_val}).text
    section = narrowed.split('id="my-rp-heading"', 1)[1].split("</section>", 1)[0]
    assert "My RP Alpha" in section
    assert "My RP Bravo" not in section
    assert f'/dashboard/people/{own_rp}/activity/{a_val}' in section
    assert viewer.get(f"/dashboard/people/{own_rp}/activity/{a_val}").status_code == 200
    assert "Your RP results by activity" not in manager.get("/reports", params={"type": 3}).text
