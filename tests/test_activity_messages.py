"""
Managed-activity organizer messages — the welcome message (shown post-consent)
and the ending message (auto-shown once a participant finishes ALL the feedback),
plus the tone-preset draft library.

Covers: draft rendering + {name} handling, storage round-trip (blank -> NULL),
messages-route RBAC, welcome shown after consent, and ending shown ONLY after the
attendee has completed every feedback form (on both the link tree and thanks page).
"""
import app as app_mod
import auth
import storage as st
import activity_messages as amsg


def _make_event(conn, created_by):
    """A minimal bureau event with one F2 feedback form. Returns (ev, [fids])."""
    fids = [st.create_form_instance(conn, 2, "F2", "2099-02-02",
                                    venue="Probe Hall", topic="Probe Activity")]
    ev = st.create_event(conn, "Probe Activity", "2099-02-02", venue="Probe Hall",
                         organizer="Test Org", form_instance_ids=fids,
                         created_by=created_by)
    conn.commit()
    return ev, fids


def _cleanup(conn, ev, fids):
    conn.execute("DELETE FROM response WHERE attendee_id IN "
                 "(SELECT id FROM attendee WHERE event_id=?)", (ev["id"],))
    conn.execute("DELETE FROM attendee WHERE event_id=?", (ev["id"],))
    conn.execute("DELETE FROM event_form WHERE event_id=?", (ev["id"],))
    conn.execute("DELETE FROM event WHERE id=?", (ev["id"],))
    conn.executemany("DELETE FROM form_instance WHERE id=?", [(f,) for f in fids])
    conn.commit()


# ---- draft library ----------------------------------------------------------

def test_drafts_weave_details_and_keep_name_token():
    ev = {"title": "Immunization Forum", "event_date": "2026-06-15",
          "venue": "Main Hall", "organizer": "BLHSD"}
    for slot in ("welcome", "ending"):
        drafts = amsg.render_drafts(slot, ev)
        assert set(drafts) == set(amsg.TONES)            # all five tones present
        for tone, text in drafts.items():
            assert "Immunization Forum" in text          # detail woven in
            assert "{name}" in text                       # name left for view-time


def test_personalize_substitutes_first_name_with_fallback():
    assert amsg.personalize("Hi {name}!", "Maria Clara Santos") == "Hi Maria!"
    assert amsg.personalize("Hi {name}!", "") == "Hi there!"
    assert amsg.personalize(None, "X") is None


# ---- storage round-trip -----------------------------------------------------

def test_set_event_messages_roundtrip_and_blank_is_null(db_path):
    conn = st.connect(db_path); st.init_db(conn)
    ev, fids = _make_event(conn, "manager@test.local")
    try:
        st.set_event_messages(conn, ev["id"], "  Welcome aboard  ", "Thanks!")
        got = st.get_event(conn, ev["event_token"])
        assert got["welcome_message"] == "Welcome aboard"   # trimmed
        assert got["ending_message"] == "Thanks!"
        # blank wipes back to NULL (= nothing shown)
        st.set_event_messages(conn, ev["id"], "   ", "")
        got = st.get_event(conn, ev["event_token"])
        assert got["welcome_message"] is None and got["ending_message"] is None
    finally:
        _cleanup(conn, ev, fids); conn.close()


# ---- messages-route RBAC ----------------------------------------------------

def test_messages_route_saves_for_creator(manager, db_path):
    conn = st.connect(db_path); st.init_db(conn)
    ev, fids = _make_event(conn, "manager@test.local")   # creator == manager fixture
    tok = ev["event_token"]
    try:
        r = manager.post(f"/activities/{tok}/messages",
                         data={"welcome_message": "Welcome, {name}!",
                               "ending_message": "Bye, {name}!"},
                         follow_redirects=False)
        assert r.status_code == 303
        got = st.get_event(conn, tok)
        assert got["welcome_message"] == "Welcome, {name}!"
        assert got["ending_message"] == "Bye, {name}!"
    finally:
        _cleanup(conn, ev, fids); conn.close()


def test_messages_route_non_creator_blocked(manager, db_path):
    conn = st.connect(db_path); st.init_db(conn)
    ev, fids = _make_event(conn, "someone.else@test.local")  # NOT the manager
    tok = ev["event_token"]
    try:
        r = manager.post(f"/activities/{tok}/messages",
                         data={"welcome_message": "hax", "ending_message": ""},
                         follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == f"/e/{tok}"
        assert st.get_event(conn, tok)["welcome_message"] is None   # nothing written
    finally:
        _cleanup(conn, ev, fids); conn.close()


# ---- participant-facing display --------------------------------------------

def test_welcome_shows_after_consent_only(manager, db_path):
    conn = st.connect(db_path); st.init_db(conn)
    ev, fids = _make_event(conn, "manager@test.local")
    tok = ev["event_token"]
    try:
        st.set_event_messages(conn, ev["id"], "Welcome, {name}! Glad you came.", "")
        # pre-consent (no att) — message hidden
        assert "Glad you came" not in manager.get(f"/e/{tok}").text
        # post-consent — message shown with the name resolved
        aid = st.add_attendee(conn, ev["id"], name="Jordan Cruz", email="j@x.com",
                              sex="M", affiliation="DOH", consent_text="x")
        conn.commit()
        shown = manager.get(f"/e/{tok}?att={auth.make_attendee_token(aid)}").text
        assert "Welcome, Jordan! Glad you came." in shown
    finally:
        _cleanup(conn, ev, fids); conn.close()


def test_ending_shows_only_after_completion(manager, db_path):
    conn = st.connect(db_path); st.init_db(conn)
    ev, fids = _make_event(conn, "manager@test.local")
    tok = ev["event_token"]
    try:
        st.set_event_messages(conn, ev["id"], "", "See you next time, {name}!")
        aid = st.add_attendee(conn, ev["id"], name="Sam Reyes", email="s@x.com",
                              sex="F", affiliation="DOH", consent_text="x")
        conn.commit()
        # not yet completed — ending hidden on the link tree
        assert "See you next time" not in manager.get(f"/e/{tok}?att={auth.make_attendee_token(aid)}").text
        # complete the single feedback form as this attendee
        st.record_response(conn, fids[0], [], attendee_id=aid)
        conn.commit()
        assert st.attendee_completed_feedback(conn, ev["id"], aid) is True
        shown = manager.get(f"/e/{tok}?att={auth.make_attendee_token(aid)}").text
        assert "See you next time, Sam!" in shown
    finally:
        _cleanup(conn, ev, fids); conn.close()
