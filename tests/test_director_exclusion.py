"""The Director is excluded from per-person CSS rankings/reports as a standing
rule (not a per-person toggle), since the role turns over faster than anyone
remembers to re-flag a new occupant. Detected live off position/designation
(storage.is_bureau_director) rather than stored state, so it applies to
whoever holds the role without any action needed on handover. These lock:
  * People rankings drop the Director by default;
  * an admin explicitly viewing hidden people still sees them (same bypass
    hidden_public already gets);
  * a non-director keeps showing up normally.
"""
import storage as st

_F3_ANSWERS = [("A", 6), ("B1", 6), ("B2", 6), ("B3", 6), ("B4", 6),
               ("B5", 6), ("B6", 6), ("B7", 6), ("B8", 6), ("B9", 6), ("C", 4)]


def test_is_bureau_director_matches_on_position_or_designation():
    assert st.is_bureau_director({"position": "Director IV", "designation": ""})
    assert st.is_bureau_director({"position": "", "designation": "Director"})
    assert st.is_bureau_director({"position": "director iv", "designation": ""})
    assert not st.is_bureau_director({"position": "Division Chief", "designation": "Division Chief"})
    assert not st.is_bureau_director({"position": None, "designation": None})


def _make_bureau(manager, db_path, name, date, venue, rp_id, topic):
    r = manager.post("/create", data={
        "event_type": "bureau", "activity_name": name,
        "event_date": date, "venue": venue, "qr_mode": "combined",
        "rp_id": [str(rp_id)], "topic": [topic],
    }, follow_redirects=True)
    assert r.status_code == 200, r.text[:400]
    conn = st.connect(db_path)
    ev = conn.execute("SELECT id FROM event WHERE title=? ORDER BY id DESC LIMIT 1",
                      (name,)).fetchone()[0]
    f3 = conn.execute(
        "SELECT fi.id FROM event_form ef JOIN form_instance fi ON fi.id = ef.form_instance_id "
        "WHERE ef.event_id=? AND fi.survey_type=3 ORDER BY fi.id LIMIT 1", (ev,)).fetchone()[0]
    conn.close()
    return f3


def test_director_omitted_from_people_rankings_admin_sees_with_toggle(manager, admin, app_mod):
    db_path = app_mod.DB
    conn = st.connect(db_path)
    sec = conn.execute("SELECT id FROM org_unit WHERE level='section' LIMIT 1").fetchone()[0]
    director_id = st.add_rp(conn, "Test Ranking Director", is_internal=True,
                            org_unit_id=sec, position="Director IV")
    speaker_id = st.add_rp(conn, "Test Ranking Speaker", is_internal=True,
                           org_unit_id=sec)
    conn.close()

    fd = _make_bureau(manager, db_path, "People Ranking Director Activity",
                      "2026-05-20", "People Ranking Test Venue Director",
                      director_id, "Director session")
    fs = _make_bureau(manager, db_path, "People Ranking Speaker Activity",
                      "2026-05-21", "People Ranking Test Venue Speaker",
                      speaker_id, "Speaker session")
    conn = st.connect(db_path)
    for _ in range(3):
        st.record_response(conn, fd, _F3_ANSWERS)
        st.record_response(conn, fs, _F3_ANSWERS)
    conn.close()
    app_mod.invalidate_atoms()

    # Non-admin (section_manager): the Director never appears.
    body = manager.get("/dashboard/people", params={"period": "all"}).text
    assert "Test Ranking Speaker" in body
    assert "Test Ranking Director" not in body

    # Admin, explicitly toggled to see hidden people (include_hidden=True
    # follows from the "hide" capability, same as hidden_public): the
    # Director shows up, same bypass hidden_public already gets.
    admin_body = admin.get("/dashboard/people", params={"period": "all"}).text
    assert "Test Ranking Speaker" in admin_body
    assert "Test Ranking Director" in admin_body
