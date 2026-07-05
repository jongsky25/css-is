"""
Managed activity link-tree — the curated `event_link` resources, the creator/admin
manage page, and the public single-source-of-truth enrichment.

Covers: URL safety, storage CRUD + created_by, resource-person listing, manage-page
RBAC (creator / admin / other / logged-out), and the add → public-page round-trip
(resources hidden before consent, shown after).
"""
import re
import app as app_mod
import storage as st


# ---- helpers ----------------------------------------------------------------

def _make_event(conn, created_by, *, with_speaker=False):
    """Create a minimal bureau event (F2 + optional F3 speaker) and return
    (event_dict, [form_instance_ids]). Caller must _cleanup."""
    fids = [st.create_form_instance(conn, 2, "F2", "2099-02-02",
                                    venue="Probe Hall", topic="Probe Activity")]
    if with_speaker:
        rp = conn.execute("SELECT id FROM resource_person LIMIT 1").fetchone()[0]
        fids.append(st.create_form_instance(conn, 3, "F3", "2099-02-02",
                                            venue="Probe Hall", topic="Probe Talk", rp_id=rp))
    ev = st.create_event(conn, "Probe Activity", "2099-02-02", venue="Probe Hall",
                         organizer="Test Org", form_instance_ids=fids,
                         created_by=created_by)
    conn.commit()
    return ev, fids


def _cleanup(conn, ev, fids):
    conn.execute("DELETE FROM event_link WHERE event_id=?", (ev["id"],))
    conn.execute("DELETE FROM attendee WHERE event_id=?", (ev["id"],))
    conn.execute("DELETE FROM event_form WHERE event_id=?", (ev["id"],))
    conn.execute("DELETE FROM event WHERE id=?", (ev["id"],))
    conn.executemany("DELETE FROM form_instance WHERE id=?", [(f,) for f in fids])
    conn.commit()


# ---- URL safety -------------------------------------------------------------

def test_safe_url_accepts_http_and_bare_domain():
    assert app_mod._safe_url("https://x.com/a") == "https://x.com/a"
    assert app_mod._safe_url("http://x.com") == "http://x.com"
    assert app_mod._safe_url("files.example.com/deck.pdf") == "https://files.example.com/deck.pdf"


def test_safe_url_rejects_dangerous_and_empty():
    for bad in ("javascript:alert(1)", "data:text/html,x", "  ", "", "/local/path",
                "vbscript:msgbox(1)"):
        assert app_mod._safe_url(bad) is None, bad


# ---- storage CRUD -----------------------------------------------------------

def test_event_link_crud_and_created_by(db_path):
    conn = st.connect(db_path); st.init_db(conn)
    ev, fids = _make_event(conn, "manager@test.local")
    try:
        assert st.get_event(conn, ev["event_token"])["created_by"] == "manager@test.local"
        a = st.add_event_link(conn, ev["id"], "slides", "Deck", "https://x/d", "note")
        b = st.add_event_link(conn, ev["id"], "program", "Agenda", "https://x/a")
        links = st.list_event_links(conn, ev["id"])
        assert [l["label"] for l in links] == ["Deck", "Agenda"]          # ordinal order
        assert links[0]["kind"] == "slides" and links[0]["note"] == "note"
        st.update_event_link(conn, a, kind="recording", label="Deck v2", url="https://x/d2")
        got = st.get_event_link(conn, a)
        assert got["label"] == "Deck v2" and got["kind"] == "recording" and got["note"] is None
        st.delete_event_link(conn, a)
        assert [l["id"] for l in st.list_event_links(conn, ev["id"])] == [b]
    finally:
        _cleanup(conn, ev, fids); conn.close()


def test_unknown_kind_falls_back_to_other(db_path):
    conn = st.connect(db_path); st.init_db(conn)
    ev, fids = _make_event(conn, "manager@test.local")
    try:
        lid = st.add_event_link(conn, ev["id"], "bogus", "X", "https://x")
        assert st.get_event_link(conn, lid)["kind"] == "other"
    finally:
        _cleanup(conn, ev, fids); conn.close()


def test_list_event_resource_persons(db_path):
    conn = st.connect(db_path); st.init_db(conn)
    ev, fids = _make_event(conn, "manager@test.local", with_speaker=True)
    try:
        sp = st.list_event_resource_persons(conn, ev["id"])
        assert len(sp) == 1 and sp[0]["name"]
    finally:
        _cleanup(conn, ev, fids); conn.close()


# ---- manage-page RBAC -------------------------------------------------------

def test_manage_rbac(admin, manager, app_mod, db_path):
    from starlette.testclient import TestClient
    conn = st.connect(db_path); st.init_db(conn)
    ev, fids = _make_event(conn, "manager@test.local")  # creator == the manager fixture
    tok = ev["event_token"]
    try:
        # creator (section_manager) and admin can manage
        assert manager.get(f"/activities/{tok}/manage").status_code == 200
        assert admin.get(f"/activities/{tok}/manage").status_code == 200
        # logged-out is bounced to login by the auth middleware. Use a FRESH client
        # (the shared `client` fixture is session-scoped and accumulates cookies).
        anon = TestClient(app_mod.app)
        r = anon.get(f"/activities/{tok}/manage", follow_redirects=False)
        assert r.status_code in (302, 303, 307) and "/login" in r.headers.get("location", "")
    finally:
        _cleanup(conn, ev, fids); conn.close()


def test_manage_non_creator_redirected_to_public(manager, db_path):
    conn = st.connect(db_path); st.init_db(conn)
    ev, fids = _make_event(conn, "someone.else@test.local")  # NOT the manager fixture
    tok = ev["event_token"]
    try:
        r = manager.get(f"/activities/{tok}/manage", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == f"/e/{tok}"
    finally:
        _cleanup(conn, ev, fids); conn.close()


# ---- add link -> public page round-trip ------------------------------------

def test_add_link_shows_on_manage_and_public_after_consent(manager, db_path):
    conn = st.connect(db_path); st.init_db(conn)
    ev, fids = _make_event(conn, "manager@test.local")
    tok = ev["event_token"]
    try:
        # add a good link via the route
        manager.post(f"/activities/{tok}/links",
                     data={"kind": "slides", "label": "Day 1 deck",
                           "url": "files.example.com/deck", "note": "v1"})
        assert "Day 1 deck" in manager.get(f"/activities/{tok}/manage").text
        assert len(st.list_event_links(conn, ev["id"])) == 1

        # a dangerous URL is refused — no row written
        manager.post(f"/activities/{tok}/links",
                     data={"kind": "info", "label": "evil", "url": "javascript:alert(1)"})
        assert len(st.list_event_links(conn, ev["id"])) == 1

        # public page: hidden before consent, shown immediately after consent
        # (a default "shared immediately" resource — no publish step).
        assert "Day 1 deck" not in manager.get(f"/e/{tok}").text
        aid = st.add_attendee(conn, ev["id"], name="P", email="p@x.com",
                              sex="F", affiliation="DOH", consent_text="x")
        conn.commit()
        shown = manager.get(f"/e/{tok}?att={aid}").text
        assert "Day 1 deck" in shown and "Programme" in shown
    finally:
        _cleanup(conn, ev, fids); conn.close()
