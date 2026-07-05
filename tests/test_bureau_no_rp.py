"""Resource persons are OPTIONAL for a bureau-organized activity.

A bureau activity produces a Form 2 event review on its own, so it's valid with
zero resource persons (a consultation, a service day, an internal activity with
no invited speaker). An outside event has only speaker reviews to offer, so it
still needs at least one. These tests lock that asymmetry.
"""
import storage as st


def _bureau(manager, name="No-Speaker Consultation", date="2026-06-15", **extra):
    data = {"event_type": "bureau", "activity_name": name,
            "event_date": date, "qr_mode": "combined"}
    data.update(extra)
    return manager.post("/create", data=data, follow_redirects=True)


def _event(db_path, title):
    conn = st.connect(db_path)
    row = conn.execute("SELECT id, event_token FROM event WHERE title=? "
                       "ORDER BY id DESC LIMIT 1", (title,)).fetchone()
    conn.close()
    return row


def test_bureau_activity_created_with_no_resource_person(manager, db_path):
    r = _bureau(manager, name="RP-less Bureau Activity")
    assert r.status_code == 200, r.text[:600]
    ev = _event(db_path, "RP-less Bureau Activity")
    assert ev is not None, "the activity should still be persisted as an event"
    event_id, _ = ev
    conn = st.connect(db_path)
    types = sorted(t[0] for t in conn.execute(
        "SELECT fi.survey_type FROM event_form ef "
        "JOIN form_instance fi ON fi.id = ef.form_instance_id WHERE ef.event_id=?",
        (event_id,)).fetchall())
    conn.close()
    assert types == [2], f"expected a lone Form 2 event review, got {types}"


def test_outside_activity_still_requires_a_resource_person(manager, db_path):
    r = manager.post("/create", data={
        "event_type": "outside", "activity_name": "Invited, no speaker",
        "event_date": "2026-06-15", "external_org": "DOH Regional Office",
        "qr_mode": "combined",
    }, follow_redirects=True)
    assert r.status_code == 400
    assert "at least one resource person" in r.text.lower()
