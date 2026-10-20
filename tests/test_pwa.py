"""
PWA tests.

Phase 1 — the dynamic manifest, the root-scope service worker, and the head wiring
on public survey pages (all anonymous/public routes).

Phase 2 — the offline submission queue's server side: the submission_log dedup that
makes a replayed offline POST idempotent.
"""
from tests.conftest import session_token
import json
import sqlite3

import pytest


def test_manifest_defaults_to_root(client):
    r = client.get("/manifest.webmanifest")
    assert r.status_code == 200
    assert "application/manifest+json" in r.headers.get("content-type", "")
    m = json.loads(r.text)
    assert m["start_url"] == "/"
    assert m["scope"] == "/"
    assert m["display"] == "standalone"
    assert any(i["sizes"] == "512x512" for i in m["icons"])
    assert any(i.get("purpose") == "maskable" for i in m["icons"])


def test_manifest_start_url_echoes_form_path(client):
    r = client.get("/manifest.webmanifest", params={"start": "/seq?tokens=abc"})
    assert r.status_code == 200
    assert json.loads(r.text)["start_url"] == "/seq?tokens=abc"


def test_manifest_rejects_offsite_start(client):
    # A scheme or protocol-relative target must not become the launch URL.
    for bad in ("https://evil.example/", "//evil.example/", "javascript:alert(1)"):
        m = json.loads(client.get("/manifest.webmanifest", params={"start": bad}).text)
        assert m["start_url"] == "/", bad


def test_service_worker_served_at_root_scope(client):
    r = client.get("/sw.js")
    assert r.status_code == 200
    assert "javascript" in r.headers.get("content-type", "")
    assert r.headers.get("service-worker-allowed") == "/"
    assert "CACHE_VERSION" in r.text


def test_service_worker_is_public_assets_only(client):
    r = client.get("/sw.js")
    assert r.status_code == 200 and "cacheableStatic" in r.text
    # Dynamic-cache behavior is executed under Node in test_service_worker_retry.
    assert "PHOTO_MAX" not in r.text and "PUBLIC_NAV" not in r.text


def test_public_form_wires_pwa(client, sample_ids):
    # A rendered public survey page advertises the manifest and registers the SW.
    r = client.get(f"/r/{sample_ids['qr_token']}")
    if r.status_code != 200:        # stale token -> closed/404; nothing to assert
        return
    assert 'rel="manifest"' in r.text
    assert "/manifest.webmanifest?start=" in r.text
    assert "serviceWorker" in r.text and "/sw.js" in r.text


# ── Phase 2: offline-queue dedup (submission_log) ─────────────────────────────

@pytest.fixture
def offline_form(app_mod, tmp_path, monkeypatch, client):
    """An open synthetic survey; replay checks need no production snapshot."""
    import storage as st
    import tzutil
    from datetime import timedelta
    path = str(tmp_path / 'offline.db')
    monkeypatch.setattr(app_mod, 'DB', path)
    conn = app_mod.get_conn()
    try:
        rp = st.add_rp(conn, 'Synthetic speaker', True)
        now = tzutil.now_local()
        fid = st.create_form_instance(conn, 3, 'F3', now.date().isoformat(),
                                      rp_id=rp, topic='Offline replay test')
        st.set_response_window(conn, fid, (now - timedelta(days=1)).isoformat(),
                               (now + timedelta(days=1)).isoformat())
        token = conn.execute('SELECT qr_token FROM form_instance WHERE id=?', (fid,)).fetchone()[0]
    finally:
        conn.close()
    assert client.get(f'/r/{token}').status_code == 200
    return path, token


def _response_count(db_path, qr_token):
    conn = sqlite3.connect(db_path)
    n = conn.execute(
        "SELECT COUNT(*) FROM response r JOIN form_instance f ON r.form_instance_id=f.id "
        "WHERE f.qr_token=?", (qr_token,)).fetchone()[0]
    conn.close()
    return n


def test_submission_log_helpers(db_path):
    import storage as st
    conn = st.connect(db_path); st.init_db(conn)
    sid = "UNIT-SID-PWA-1"
    assert st.submission_seen(conn, sid) is False
    st.mark_submission(conn, sid)
    assert st.submission_seen(conn, sid) is True
    st.mark_submission(conn, sid)                 # idempotent — must not raise
    assert st.submission_seen(conn, "") is False  # empty id is never "seen"
    conn.close()


def test_offline_replay_records_once(client, offline_form):
    db_path, tk = offline_form
    body = {"submission_id": "REPLAY-PWA-1", "A": "5", "remarks": "from the field"}
    before = _response_count(db_path, tk)

    r1 = client.post(f"/r/{tk}", data=body)
    assert r1.status_code == 200
    assert _response_count(db_path, tk) == before + 1   # first send records

    r2 = client.post(f"/r/{tk}", data=body)             # identical replay
    assert r2.status_code == 200
    assert r2.json().get("deduped") is True
    assert _response_count(db_path, tk) == before + 1   # no duplicate


def test_no_submission_id_is_not_deduped(client, offline_form):
    # Regression: an ordinary (online) submit carries no submission_id and is
    # recorded every time — behaviour must be unchanged by Phase 2.
    db_path, tk = offline_form
    before = _response_count(db_path, tk)
    client.post(f"/r/{tk}", data={"A": "4"})
    client.post(f"/r/{tk}", data={"A": "4"})
    assert _response_count(db_path, tk) == before + 2


def test_seq_replay_deduped(client, offline_form):
    db_path, tk = offline_form
    body = {"tokens": tk, "submission_id": "SEQ-REPLAY-PWA-1"}
    r1 = client.post("/seq", data=body)
    assert r1.status_code == 200
    # the submission id is now logged, so a replay short-circuits as deduped
    r2 = client.post("/seq", data=body)
    assert r2.status_code == 200
    assert r2.json().get("deduped") is True


# App response identification: GET retries avoid app-originated failures.
# Absence of a marker does not establish that a write was never committed.

def test_every_response_carries_app_marker_header(client):
    # success, redirect, and 4xx all stamp X-CSS-App
    assert client.get("/login").headers.get("x-css-app") == "1"
    assert client.get("/", follow_redirects=False).headers.get("x-css-app") == "1"
    assert client.get("/no-such-page-zzz").headers.get("x-css-app") == "1"


def test_unhandled_crash_500_still_carries_app_marker(app_mod):
    # An app crash should be identifiable so GETs do not retry it.
    # (Signed-in client: the auth gate would otherwise redirect the test route
    # to /login before it can crash.)
    from starlette.testclient import TestClient
    import auth, storage as st
    from tests.conftest import ROLE_USERS

    @app_mod.app.get("/_test_boom_route")
    def _boom():
        raise RuntimeError("intentional test crash")

    conn = st.connect(app_mod.DB)
    u = st.get_admin_user(conn, ROLE_USERS["admin"]); conn.close()
    c = TestClient(app_mod.app, raise_server_exceptions=False)
    c.cookies.set(auth.COOKIE_NAME, session_token(
        {"id": u["id"], "username": u["username"], "role": u["role"]}))
    r = c.get("/_test_boom_route")
    assert r.status_code == 500
    assert r.headers.get("x-css-app") == "1"


def test_service_worker_has_edge_retry_shield(client):
    sw = client.get("/sw.js").text
    assert "x-css-app" in sw
    assert "fetchRetrying" in sw
    assert "isEdgeError" in sw
    # Non-GETs bypass the shield; executable regression coverage is in
    # test_service_worker_retry.py.
    assert 'req.method !== "GET"' in sw
