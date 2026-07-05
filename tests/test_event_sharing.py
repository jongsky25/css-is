"""
Phase 6 (revised) — two-bucket resource sharing on the link tree.

Resources live in one of two buckets: "shared immediately" (visible_after_done=0,
shown as soon as a participant registers/consents) and "shared after feedback"
(visible_after_done=1, unlocked for a participant only once they have completed
all of the activity's feedback forms). There is NO all-or-none publish gate; the
only global control is the public_sharing_enabled master switch.

Covers: per-attendee completion detection, bucket filtering, the move action, the
master switch, list_shared_events, and the /shared + /admin/sharing pages.
"""
import storage as st


# ---- helpers ----------------------------------------------------------------

def _event(conn, created_by, date, *, n_forms=1):
    fids = [st.create_form_instance(conn, 2, "F2", date, venue="Hall", topic="Probe")]
    for i in range(n_forms - 1):
        fids.append(st.create_form_instance(conn, 2, "F2b", date, venue="Hall",
                                            topic="Probe%d" % i))
    ev = st.create_event(conn, "Probe", date, venue="Hall", organizer="Org",
                         form_instance_ids=fids, created_by=created_by)
    conn.commit()
    return ev, fids


def _cleanup(conn, ev, fids):
    conn.execute("DELETE FROM answer WHERE response_id IN "
                 "(SELECT id FROM response WHERE form_instance_id IN (%s))"
                 % ",".join("?" * len(fids)), fids)
    conn.execute("DELETE FROM response WHERE form_instance_id IN (%s)"
                 % ",".join("?" * len(fids)), fids)
    conn.execute("DELETE FROM event_link WHERE event_id=?", (ev["id"],))
    conn.execute("DELETE FROM attendee WHERE event_id=?", (ev["id"],))
    conn.execute("DELETE FROM event_form WHERE event_id=?", (ev["id"],))
    conn.execute("DELETE FROM event WHERE id=?", (ev["id"],))
    conn.executemany("DELETE FROM form_instance WHERE id=?", [(f,) for f in fids])
    conn.commit()


# ---- attendee_completed_feedback --------------------------------------------

def test_attendee_completed_feedback(db_path):
    conn = st.connect(db_path); st.init_db(conn)
    ev, fids = _event(conn, "m@x", "2000-01-01", n_forms=2)   # two forms to finish
    aid = st.add_attendee(conn, ev["id"], name="P", email="p@x.com",
                          sex="F", affiliation="DOH", consent_text="x")
    conn.commit()
    try:
        assert st.attendee_completed_feedback(conn, ev["id"], aid) is False
        st.record_response(conn, fids[0], [], attendee_id=aid)      # one of two
        assert st.attendee_completed_feedback(conn, ev["id"], aid) is False
        st.record_response(conn, fids[1], [], attendee_id=aid)      # finished both
        assert st.attendee_completed_feedback(conn, ev["id"], aid) is True
        assert st.attendee_completed_feedback(conn, ev["id"], None) is False
    finally:
        _cleanup(conn, ev, fids); conn.close()


# ---- bucket filtering -------------------------------------------------------

def test_list_public_event_links_by_completion(db_path):
    conn = st.connect(db_path); st.init_db(conn)
    ev, fids = _event(conn, "m@x", "2000-01-01")
    try:
        st.add_event_link(conn, ev["id"], "slides", "Deck", "https://x/d")
        st.add_event_link(conn, ev["id"], "certificate", "Cert", "https://x/c",
                          visible_after_done=True)
        # not completed -> only the immediate link
        assert {l["label"] for l in st.list_public_event_links(conn, ev["id"], False)} == {"Deck"}
        # completed -> both
        assert {l["label"] for l in st.list_public_event_links(conn, ev["id"], True)} == {"Deck", "Cert"}
    finally:
        _cleanup(conn, ev, fids); conn.close()


def test_update_event_link_toggles_after_done(db_path):
    conn = st.connect(db_path); st.init_db(conn)
    ev, fids = _event(conn, "m@x", "2000-01-01")
    try:
        lid = st.add_event_link(conn, ev["id"], "slides", "Deck", "https://x/d")
        assert st.get_event_link(conn, lid)["visible_after_done"] is False
        st.update_event_link(conn, lid, kind="slides", label="Deck", url="https://x/d",
                             visible_after_done=True)
        assert st.get_event_link(conn, lid)["visible_after_done"] is True
    finally:
        _cleanup(conn, ev, fids); conn.close()


# ---- list_shared_events -----------------------------------------------------

def test_list_shared_events(db_path):
    conn = st.connect(db_path); st.init_db(conn)
    # concluded + has an immediate link -> included
    good, g = _event(conn, "m@x", "2000-01-01")
    st.add_event_link(conn, good["id"], "slides", "Deck", "https://x/d")
    # concluded but only an after-feedback link -> excluded
    afteronly, a = _event(conn, "m@x", "2000-01-02")
    st.add_event_link(conn, afteronly["id"], "certificate", "Cert", "https://x/c",
                      visible_after_done=True)
    # NOT concluded (future) -> excluded
    future, f = _event(conn, "m@x", "2099-12-31")
    st.add_event_link(conn, future["id"], "slides", "Deck", "https://x/d")
    try:
        ids = {row["id"] for row in st.list_shared_events(conn)}
        assert good["id"] in ids
        assert afteronly["id"] not in ids
        assert future["id"] not in ids
    finally:
        for ev, fids in ((good, g), (afteronly, a), (future, f)):
            _cleanup(conn, ev, fids)
        conn.close()


# ---- route: immediate vs after-feedback on the public page ------------------

def test_public_page_two_buckets(manager, db_path):
    conn = st.connect(db_path); st.init_db(conn)
    ev, fids = _event(conn, "manager@test.local", "2000-01-01")
    tok = ev["event_token"]
    st.add_event_link(conn, ev["id"], "slides", "Immediate Deck", "https://x/d")
    st.add_event_link(conn, ev["id"], "certificate", "Reward Cert", "https://x/c",
                      visible_after_done=True)
    aid = st.add_attendee(conn, ev["id"], name="P", email="p@x.com",
                          sex="F", affiliation="DOH", consent_text="x")
    conn.commit()
    try:
        # before finishing feedback: immediate shows, cert locked (teaser, no link)
        body = manager.get(f"/e/{tok}?att={aid}").text
        assert "Immediate Deck" in body
        assert "Reward Cert" not in body
        assert "unlock" in body.lower()
        # finish the feedback -> cert unlocks
        st.record_response(conn, fids[0], [], attendee_id=aid); conn.commit()
        body2 = manager.get(f"/e/{tok}?att={aid}").text
        assert "Reward Cert" in body2 and "Immediate Deck" in body2
    finally:
        _cleanup(conn, ev, fids); conn.close()


def test_public_page_honors_master_switch(manager, db_path):
    conn = st.connect(db_path); st.init_db(conn)
    ev, fids = _event(conn, "manager@test.local", "2000-01-01")
    tok = ev["event_token"]
    st.add_event_link(conn, ev["id"], "slides", "Master Deck", "https://x/d")
    aid = st.add_attendee(conn, ev["id"], name="P", email="p@x.com",
                          sex="F", affiliation="DOH", consent_text="x")
    conn.commit()
    try:
        st.set_setting(conn, "public_sharing_enabled", "1")
        assert "Master Deck" in manager.get(f"/e/{tok}?att={aid}").text
        st.set_setting(conn, "public_sharing_enabled", "0")
        assert "Master Deck" not in manager.get(f"/e/{tok}?att={aid}").text
    finally:
        st.set_setting(conn, "public_sharing_enabled", "1")
        _cleanup(conn, ev, fids); conn.close()


# ---- route: link add (bucket) + move ----------------------------------------

def test_add_link_to_bucket_and_move(manager, db_path):
    conn = st.connect(db_path); st.init_db(conn)
    ev, fids = _event(conn, "manager@test.local", "2000-01-01")
    tok = ev["event_token"]
    try:
        # add an after-feedback link via the route's hidden field
        manager.post(f"/activities/{tok}/links",
                     data={"kind": "certificate", "label": "Cert",
                           "url": "files.example.com/cert", "visible_after_done": "1"})
        links = st.list_event_links(conn, ev["id"])
        assert len(links) == 1 and links[0]["visible_after_done"] is True
        # move it to the immediate bucket
        manager.post(f"/activities/{tok}/links/{links[0]['id']}", data={"_action": "move"})
        assert st.get_event_link(conn, links[0]["id"])["visible_after_done"] is False
    finally:
        _cleanup(conn, ev, fids); conn.close()


def test_publish_route_gone(manager, db_path):
    # the old all-or-none publish endpoint must no longer exist
    conn = st.connect(db_path); st.init_db(conn)
    ev, fids = _event(conn, "manager@test.local", "2000-01-01")
    try:
        r = manager.post(f"/activities/{ev['event_token']}/publish",
                         data={"public_share": "1"}, follow_redirects=False)
        assert r.status_code == 404
    finally:
        _cleanup(conn, ev, fids); conn.close()


# ---- /shared + /admin/sharing pages -----------------------------------------

def test_shared_index_lists_concluded(viewer, db_path):
    conn = st.connect(db_path); st.init_db(conn)
    ev, fids = _event(conn, "m@x", "2000-01-01")
    st.add_event_link(conn, ev["id"], "slides", "Shared Deck XYZ", "https://x/d")
    conn.commit()
    try:
        body = viewer.get("/shared").text
        assert f"/e/{ev['event_token']}" in body      # the activity is deep-linked
    finally:
        _cleanup(conn, ev, fids); conn.close()


def test_admin_sharing_get_and_toggle(admin, db_path):
    conn = st.connect(db_path); st.init_db(conn)
    try:
        assert admin.get("/admin/sharing").status_code == 200
        admin.post("/admin/sharing", data={})  # unchecked -> off
        assert st.get_setting(conn, "public_sharing_enabled") == "0"
        admin.post("/admin/sharing", data={"public_sharing_enabled": "on"})
        assert st.get_setting(conn, "public_sharing_enabled") == "1"
    finally:
        st.set_setting(conn, "public_sharing_enabled", "1")
        conn.close()


def test_admin_sharing_requires_manage_users(viewer):
    assert viewer.get("/admin/sharing").status_code == 403
