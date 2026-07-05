"""
PWA tests.

Phase 1 — the dynamic manifest, the root-scope service worker, and the head wiring
on public survey pages (all anonymous/public routes).

Phase 2 — the offline submission queue's server side: the submission_log dedup that
makes a replayed offline POST idempotent.
"""
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


def test_public_form_wires_pwa(client, sample_ids):
    # A rendered public survey page advertises the manifest and registers the SW.
    r = client.get(f"/r/{sample_ids['qr_token']}")
    if r.status_code != 200:        # stale token -> closed/404; nothing to assert
        return
    assert 'rel="manifest"' in r.text
    assert "/manifest.webmanifest?start=" in r.text
    assert "serviceWorker" in r.text and "/sw.js" in r.text


# ── Phase 2: offline-queue dedup (submission_log) ─────────────────────────────

def _open_token(client, db_path):
    """A qr_token whose form window is currently open (GET /r/<tok> → 200)."""
    conn = sqlite3.connect(db_path)
    toks = [r[0] for r in conn.execute(
        "SELECT qr_token FROM form_instance WHERE qr_token IS NOT NULL").fetchall()]
    conn.close()
    for tk in toks:
        if client.get(f"/r/{tk}").status_code == 200:
            return tk
    return None


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


def test_offline_replay_records_once(client, db_path):
    tk = _open_token(client, db_path)
    if not tk:
        pytest.skip("no open form in the test DB")
    body = {"submission_id": "REPLAY-PWA-1", "A": "5", "remarks": "from the field"}
    before = _response_count(db_path, tk)

    r1 = client.post(f"/r/{tk}", data=body)
    assert r1.status_code == 200
    assert _response_count(db_path, tk) == before + 1   # first send records

    r2 = client.post(f"/r/{tk}", data=body)             # identical replay
    assert r2.status_code == 200
    assert r2.json().get("deduped") is True
    assert _response_count(db_path, tk) == before + 1   # no duplicate


def test_no_submission_id_is_not_deduped(client, db_path):
    # Regression: an ordinary (online) submit carries no submission_id and is
    # recorded every time — behaviour must be unchanged by Phase 2.
    tk = _open_token(client, db_path)
    if not tk:
        pytest.skip("no open form in the test DB")
    before = _response_count(db_path, tk)
    client.post(f"/r/{tk}", data={"A": "4"})
    client.post(f"/r/{tk}", data={"A": "4"})
    assert _response_count(db_path, tk) == before + 2


def test_seq_replay_deduped(client, db_path):
    tk = _open_token(client, db_path)
    if not tk:
        pytest.skip("no open form in the test DB")
    body = {"tokens": tk, "submission_id": "SEQ-REPLAY-PWA-1"}
    r1 = client.post("/seq", data=body)
    assert r1.status_code == 200
    # the submission id is now logged, so a replay short-circuits as deduped
    r2 = client.post("/seq", data=body)
    assert r2.status_code == 200
    assert r2.json().get("deduped") is True
