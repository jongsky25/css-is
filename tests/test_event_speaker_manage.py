"""Resource persons on a bureau activity.

Rule: a resource person can never be saved without a topic (and vice versa) —
neither when the activity is created nor when added/edited later on the manage
page. The manage page can add, edit (topic always; person only while the review
has no responses) and remove resource persons on a bureau activity.
"""
import re
import storage as st


def _two_rps(db_path):
    conn = st.connect(db_path)
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM resource_person ORDER BY id LIMIT 2")]
    conn.close()
    return ids


def _create(manager, **extra):
    data = {"event_type": "bureau", "activity_name": "Speaker Manage Forum",
            "event_date": "2026-06-11", "venue": "Hall A", "qr_mode": "combined"}
    data.update(extra)
    return manager.post("/create", data=data, follow_redirects=True)


def _event_id(db_path):
    conn = st.connect(db_path)
    row = conn.execute("SELECT id, event_token FROM event WHERE title=? "
                       "ORDER BY id DESC LIMIT 1", ("Speaker Manage Forum",)).fetchone()
    conn.close()
    return row


def _f3s(db_path, ev_id):
    conn = st.connect(db_path)
    rows = conn.execute(
        "SELECT fi.id, fi.rp_id, fi.topic, fi.lead_org_id FROM event_form ef "
        "JOIN form_instance fi ON fi.id=ef.form_instance_id "
        "WHERE ef.event_id=? AND fi.survey_type=3 ORDER BY fi.id", (ev_id,)).fetchall()
    conn.close()
    return rows


def test_create_rejects_resource_person_without_topic(manager, db_path):
    rp = _two_rps(db_path)[0]
    r = _create(manager, rp_id=str(rp), topic="")
    assert r.status_code == 400
    assert "needs a topic" in r.text
    assert _event_id(db_path) is None


def test_create_rejects_topic_without_resource_person(manager, db_path):
    r = _create(manager, rp_id="", topic="Orphan topic")
    assert r.status_code == 400
    assert "Pick a resource person" in r.text


def test_create_without_any_resource_person_is_still_fine(manager, db_path):
    r = _create(manager)
    assert r.status_code == 200
    assert _event_id(db_path) is not None


def test_manage_add_edit_remove_resource_person(manager, db_path):
    rp1, rp2 = _two_rps(db_path)
    _create(manager)
    ev_id, tok = _event_id(db_path)
    assert "No resource persons are attached" in manager.get(f"/activities/{tok}/manage").text

    # add — needs both a person and a topic
    r = manager.post(f"/activities/{tok}/speakers", data={"rp_id": str(rp1), "topic": ""},
                     follow_redirects=False)
    assert "err=addspeaker" in r.headers["location"]
    assert _f3s(db_path, ev_id) == []
    manager.post(f"/activities/{tok}/speakers", data={"rp_id": str(rp1), "topic": "Opening"})
    (fid, got_rp, topic, lead), = _f3s(db_path, ev_id)
    assert (got_rp, topic) == (rp1, "Opening")
    assert lead is not None          # inherits the activity's organizing section
    page = manager.get(f"/activities/{tok}/manage").text
    assert "Opening" in page and "No resource persons are attached" not in page

    # edit topic + person
    manager.post(f"/activities/{tok}/speakers/{fid}/rename",
                 data={"rp_id": str(rp2), "topic": "Closing"})
    (_, got_rp, topic, _), = _f3s(db_path, ev_id)
    assert (got_rp, topic) == (rp2, "Closing")
    # a blank topic is refused
    r = manager.post(f"/activities/{tok}/speakers/{fid}/rename",
                     data={"rp_id": str(rp2), "topic": " "}, follow_redirects=False)
    assert "err=renametopic" in r.headers["location"]

    # remove
    manager.post(f"/activities/{tok}/speakers/{fid}/remove")
    assert _f3s(db_path, ev_id) == []


def test_person_locked_once_responses_exist_but_topic_still_editable(manager, db_path):
    rp1, rp2 = _two_rps(db_path)
    _create(manager, rp_id=str(rp1), topic="Keynote")
    ev_id, tok = _event_id(db_path)
    (fid, *_), = _f3s(db_path, ev_id)
    conn = st.connect(db_path)
    st.record_response(conn, fid, [("A", 6), ("C", 4)])
    conn.close()

    r = manager.post(f"/activities/{tok}/speakers/{fid}/rename",
                     data={"rp_id": str(rp2), "topic": "Renamed"}, follow_redirects=False)
    assert "err=rpchange" in r.headers["location"]
    (_, got_rp, topic, _), = _f3s(db_path, ev_id)
    assert got_rp == rp1 and topic == "Keynote"        # nothing half-applied

    manager.post(f"/activities/{tok}/speakers/{fid}/rename",
                 data={"rp_id": str(rp1), "topic": "Renamed"})
    assert _f3s(db_path, ev_id)[0][2] == "Renamed"
    # and it can't be removed while it has responses
    r = manager.post(f"/activities/{tok}/speakers/{fid}/remove", follow_redirects=False)
    assert "err=hasresponses" in r.headers["location"]
