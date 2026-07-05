"""
Spot Feedback — in-page comments from signed-in users + the admin triage board.

Covers: storage round-trip + status filter, submit gating by the
`spot_feedback_enabled` switch, board/export RBAC (admin-only `triage_feedback`),
triage updates + audit, and a real XLSX export.
"""
import storage as st


def _reset(conn):
    conn.execute("DELETE FROM spot_feedback")
    conn.execute("DELETE FROM feedback_update")
    st.set_setting(conn, "spot_feedback_enabled", "1")
    conn.commit()


# ---- storage round-trip -----------------------------------------------------

def test_storage_roundtrip_and_status_filter(db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        a = st.create_spot_feedback(conn, user_id=1, submitter="u@x", page_url="/dashboard",
                                    element_selector=".card", region_json='{"r":1}', message="hi")
        b = st.create_spot_feedback(conn, user_id=2, submitter="v@x", page_url="/reports",
                                    element_selector=None, region_json=None, message="yo")
        rows = st.list_spot_feedback(conn)
        assert [r["id"] for r in rows] == [b, a]                 # newest first
        assert st.get_spot_feedback(conn, a)["status"] == "New"  # default
        st.update_spot_feedback(conn, a, status="Done", admin_note="fixed")
        got = st.get_spot_feedback(conn, a)
        assert got["status"] == "Done" and got["admin_note"] == "fixed" and got["updated_at"]
        assert [r["id"] for r in st.list_spot_feedback(conn, status="Done")] == [a]
        assert st.spot_feedback_status_counts(conn) == {"New": 1, "Done": 1}
    finally:
        _reset(conn); conn.close()


# ---- submit gating ----------------------------------------------------------

def test_submit_open_to_logged_in_when_enabled(viewer, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        r = viewer.post("/feedback", data={"message": "looks off", "page_url": "/dashboard",
                        "element_selector": ".x", "region_json": "{}"},
                        headers={"X-Requested-With": "fetch"})
        assert r.status_code == 204
        rows = st.list_spot_feedback(conn)
        assert len(rows) == 1 and rows[0]["message"] == "looks off"
    finally:
        _reset(conn); conn.close()


def test_submit_blocked_when_disabled(viewer, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    st.set_setting(conn, "spot_feedback_enabled", "0"); conn.commit()
    try:
        r = viewer.post("/feedback", data={"message": "nope", "page_url": "/x"},
                        headers={"X-Requested-With": "fetch"})
        assert r.status_code == 403
        assert st.list_spot_feedback(conn) == []
    finally:
        _reset(conn); conn.close()


def test_submit_rejects_empty_message(viewer, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        r = viewer.post("/feedback", data={"message": "   ", "page_url": "/x"},
                        headers={"X-Requested-With": "fetch"})
        assert r.status_code == 400 and st.list_spot_feedback(conn) == []
    finally:
        _reset(conn); conn.close()


# ---- board / triage / export RBAC ------------------------------------------

def test_board_admin_only(admin, viewer, manager, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    assert admin.get("/admin/feedback").status_code == 200
    assert viewer.get("/admin/feedback").status_code == 403
    assert manager.get("/admin/feedback").status_code == 403


def test_triage_updates_and_audits(admin, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        fid = st.create_spot_feedback(conn, user_id=1, submitter="u@x", page_url="/dashboard",
                                      element_selector=".c", region_json=None, message="m")
        r = admin.post(f"/admin/feedback/{fid}",
                       data={"status": "Reviewing", "reply": "thanks, on it", "admin_note": "ok",
                             "from_status": ""}, follow_redirects=False)
        assert r.status_code == 303
        assert st.get_spot_feedback(conn, fid)["status"] == "Reviewing"
        row = conn.execute("SELECT action FROM audit_log WHERE action='spot_feedback_triage' "
                           "ORDER BY id DESC LIMIT 1").fetchone()
        assert row is not None
    finally:
        _reset(conn); conn.close()


def test_triage_rejects_unknown_status(admin, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        fid = st.create_spot_feedback(conn, user_id=1, submitter="u@x", page_url="/d",
                                      element_selector=None, region_json=None, message="m")
        admin.post(f"/admin/feedback/{fid}", data={"status": "Bogus"}, follow_redirects=False)
        assert st.get_spot_feedback(conn, fid)["status"] == "New"   # unchanged
    finally:
        _reset(conn); conn.close()


def test_detail_page_renders_and_is_admin_only(admin, viewer, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    fid = st.create_spot_feedback(
        conn, user_id=1, submitter="ray@x", page_url="/directory",
        element_selector="div:nth-of-type(1)",
        region_json='{"rect":{"x":463,"y":-1390,"w":980,"h":4906},'
                    '"viewport":{"w":1920,"h":919,"scrollX":0,"scrollY":1440}}',
        message="this should stay where I left it")
    conn.commit(); conn.close()
    assert viewer.get(f"/admin/feedback/view/{fid}").status_code == 403
    r = admin.get(f"/admin/feedback/view/{fid}")
    assert r.status_code == 200
    body = r.text
    assert "this should stay where I left it" in body      # full message
    assert "div:nth-of-type(1)" in body                     # exact element
    assert "980×4906" in body                               # parsed region rect
    conn = st.connect(db_path); _reset(conn); conn.close()


def test_detail_missing_redirects_to_board(admin, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    r = admin.get("/admin/feedback/view/999999", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/admin/feedback")


def test_detail_triage_returns_to_detail_with_history(admin, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    fid = st.create_spot_feedback(conn, user_id=1, submitter="u@x", page_url="/d",
                                  element_selector=None, region_json=None, message="m")
    conn.commit(); conn.close()
    r = admin.post(f"/admin/feedback/{fid}",
                   data={"status": "Done", "reply": "all fixed!", "admin_note": "fixed",
                         "back": "detail"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == f"/admin/feedback/view/{fid}?msg=Saved."
    conn = st.connect(db_path)
    hist = st.spot_feedback_history(conn, fid)
    assert any(h["action"] == "spot_feedback_triage" and h["after"] == "Done" for h in hist)
    _reset(conn); conn.close()


def test_export_route_not_shadowed_by_detail(admin, db_path):
    """GET /admin/feedback/export must still hit the XLSX export, not the int-only
    detail route."""
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    assert admin.get("/admin/feedback/export").status_code == 200


def test_export_xlsx_admin_only(admin, viewer, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    st.create_spot_feedback(conn, user_id=1, submitter="u@x", page_url="/d",
                            element_selector=".c", region_json=None, message="m")
    conn.commit(); conn.close()
    assert viewer.get("/admin/feedback/export").status_code == 403
    r = admin.get("/admin/feedback/export")
    assert r.status_code == 200
    assert "spreadsheetml" in r.headers["content-type"]
    assert r.content[:2] == b"PK" and len(r.content) > 0
    conn = st.connect(db_path); _reset(conn); conn.close()


# ---- submitter notifications (phased "we heard you") ------------------------

def test_ack_event_seeded_on_create(db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        fid = st.create_spot_feedback(conn, user_id=7, submitter="u@x", page_url="/d",
                                      element_selector=None, region_json=None, message="m")
        ups = st.list_feedback_updates(conn, fid)
        assert len(ups) == 1 and ups[0]["kind"] == "ack" and ups[0]["reply"]
        assert st.count_unread_feedback(conn, 7) == 1   # their own ack is unread
    finally:
        _reset(conn); conn.close()


def test_triage_adds_phase_event_with_reply(admin, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        fid = st.create_spot_feedback(conn, user_id=7, submitter="u@x", page_url="/d",
                                      element_selector=None, region_json=None, message="m")
        admin.post(f"/admin/feedback/{fid}",
                   data={"status": "Reviewing", "reply": "looking into it",
                         "admin_note": "secret"}, follow_redirects=False)
        ups = st.list_feedback_updates(conn, fid)
        assert [u["kind"] for u in ups] == ["ack", "status"]
        assert ups[-1]["status"] == "Reviewing" and ups[-1]["reply"] == "looking into it"
        # the internal note is NOT part of the submitter-facing trail
        assert all((u["reply"] or "") != "secret" for u in ups)
    finally:
        _reset(conn); conn.close()


def test_my_feedback_is_owner_scoped_and_hides_internal_note(viewer, admin, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    # viewer leaves feedback through the real endpoint (so user_id == viewer)
    viewer.post("/feedback", data={"message": "viewer note here", "page_url": "/dashboard"},
                headers={"X-Requested-With": "fetch"})
    conn = st.connect(db_path)
    row = st.list_spot_feedback(conn)[0]; fid = row["id"]; uid = row["user_id"]
    conn.close()
    # admin replies + writes a private note
    admin.post(f"/admin/feedback/{fid}",
               data={"status": "Will address", "reply": "great catch — fixing",
                     "admin_note": "PRIVATE-INTERNAL"}, follow_redirects=False)
    r = viewer.get("/my/feedback")
    assert r.status_code == 200
    assert "viewer note here" in r.text
    assert "great catch — fixing" in r.text          # the reply is shown
    assert "PRIVATE-INTERNAL" not in r.text           # the internal note is not
    # visiting clears the unread badge
    conn = st.connect(db_path)
    assert st.count_unread_feedback(conn, uid) == 0
    _reset(conn); conn.close()


def test_my_feedback_only_shows_your_own(viewer, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    # someone else's submission
    st.create_spot_feedback(conn, user_id=99999, submitter="other@x", page_url="/d",
                            element_selector=None, region_json=None, message="not yours")
    conn.commit(); conn.close()
    r = viewer.get("/my/feedback")
    assert r.status_code == 200 and "not yours" not in r.text
    conn = st.connect(db_path); _reset(conn); conn.close()


# ---- archiving once resolved ------------------------------------------------

def test_archive_storage_owner_scoped_and_resolved_only(db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        fid = st.create_spot_feedback(conn, user_id=5, submitter="u@x", page_url="/d",
                                      element_selector=None, region_json=None, message="m")
        # active (New) thread cannot be archived…
        st.archive_feedback(conn, fid, 5)
        assert st.get_spot_feedback(conn, fid)["archived_at"] is None
        st.update_spot_feedback(conn, fid, status="Done", admin_note=None)
        # …and a non-owner cannot archive it either
        st.archive_feedback(conn, fid, 999)
        assert st.get_spot_feedback(conn, fid)["archived_at"] is None
        # owner archives the resolved thread
        st.archive_feedback(conn, fid, 5)
        assert st.get_spot_feedback(conn, fid)["archived_at"]
        rows = st.list_user_feedback(conn, 5)
        assert rows[0]["archived"] is True and rows[0]["resolved"] is True
        # unarchive restores
        st.unarchive_feedback(conn, fid, 5)
        assert st.get_spot_feedback(conn, fid)["archived_at"] is None
        assert st.list_user_feedback(conn, 5)[0]["archived"] is False
    finally:
        _reset(conn); conn.close()


def test_my_feedback_archive_flow(viewer, admin, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    viewer.post("/feedback", data={"message": "archive me", "page_url": "/dashboard"},
                headers={"X-Requested-With": "fetch"})
    conn = st.connect(db_path)
    fid = st.list_spot_feedback(conn)[0]["id"]; conn.close()
    # admin resolves it so the Archive control becomes available
    admin.post(f"/admin/feedback/{fid}", data={"status": "Done"}, follow_redirects=False)
    # before archiving the card is active and offers Archive
    body = viewer.get("/my/feedback").text
    assert "archive me" in body and f"/my/feedback/{fid}/archive" in body
    # archive it
    r = viewer.post(f"/my/feedback/{fid}/archive", follow_redirects=False)
    assert r.status_code == 303
    body = viewer.get("/my/feedback").text
    assert "Archived (1)" in body and f"/my/feedback/{fid}/unarchive" in body
    # unarchive restores it to the active list
    viewer.post(f"/my/feedback/{fid}/unarchive", follow_redirects=False)
    body = viewer.get("/my/feedback").text
    assert "Archived (1)" not in body and f"/my/feedback/{fid}/archive" in body
    conn = st.connect(db_path); _reset(conn); conn.close()
