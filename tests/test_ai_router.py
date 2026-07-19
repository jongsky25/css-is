"""
POST /api/ai/route, POST /api/ai/feedback, GET /start, and the login-redirect
opt-in — docs/AI_INTEGRATION_PLAN.md Phase 1.

Covers: role-filtered destination routing (a viewer's catalog never even
contains an admin-only destination, so a mocked model "steering" one there
is caught by the same allow-list check as any other bad answer — the
prompt-injection defense); out-of-catalog destinations and sub-floor
confidence rejected server-side (outcome flips to rejected_validation via
storage.update_ai_interaction_outcome); AIError and budget-exceeded both
falling back; feedback ownership/RBAC; /start rendering for all four roles;
and the login redirect honoring both ai_mode/ai_landing_default settings
without hijacking an explicit `next`.

Autouse fixture below guarantees this file never reaches the real network —
it always monkeypatches ai_core._http_generate.
"""
import json

import httpx
import pytest

import ai_core as ai
import storage as st


@pytest.fixture(autouse=True)
def _no_real_network(monkeypatch):
    def _boom(*a, **kw):
        raise AssertionError("a real httpx.post reached the network in an AI test — mock it")
    monkeypatch.setattr(httpx, "post", _boom)
    ai.reset_cooldown()
    yield
    ai.reset_cooldown()


def _reset(conn):
    conn.execute("DELETE FROM ai_interaction")
    conn.execute("DELETE FROM ai_budget")
    conn.execute("DELETE FROM app_setting WHERE key LIKE 'ai_%'")
    conn.commit()


def _configure_router(conn, monkeypatch, *, landing_default=None):
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    st.set_setting(conn, "ai_mode", "router")
    if landing_default is not None:
        st.set_setting(conn, "ai_landing_default", landing_default)


def _mock_route_answer(monkeypatch, destination, confidence, reason="because"):
    payload = {"destination": destination, "confidence": confidence, "reason": reason}
    monkeypatch.setattr(ai, "_http_generate", lambda *a, **kw: {
        "text": json.dumps(payload), "parsed": payload,
        "tokens_in": 5, "tokens_out": 5, "latency_ms": 40, "model": "gemini-test"})


def _last_interaction(conn):
    return conn.execute(
        "SELECT outcome, destination, confidence FROM ai_interaction "
        "WHERE feature='nl_router' ORDER BY id DESC LIMIT 1").fetchone()


# ---- /start renders regardless of AI mode ------------------------------------

def test_start_renders_for_all_roles(viewer, encoder, manager, admin, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    for client in (viewer, encoder, manager, admin):
        r = client.get("/start")
        assert r.status_code == 200
        assert "What do you want to do" in r.text


def test_start_renders_with_ai_off(viewer, db_path, monkeypatch):
    monkeypatch.delenv("CSS_GEMINI_API_KEY", raising=False)
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    assert viewer.get("/start").status_code == 200


# ---- /api/ai/route: valid routing, role filtering ----------------------------

def test_route_valid_destination(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_router(conn, monkeypatch)
        conn.commit(); conn.close()
        _mock_route_answer(monkeypatch, "pulse", 0.9)
        r = admin.post("/api/ai/route", data={"q": "how are we doing"})
        assert r.status_code == 200
        body = r.json()
        assert body["kind"] == "navigate"
        assert body["destination"] == "pulse"
        assert body["url"] == "/dashboard"
        assert "interaction_id" in body
        conn = st.connect(db_path)
        outcome, destination, confidence = _last_interaction(conn)
        assert outcome == "ok" and destination == "pulse" and confidence == 0.9
    finally:
        _reset(conn); conn.close()


def test_route_empty_query_is_fallback_with_no_ai_call(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_router(conn, monkeypatch)
        conn.commit(); conn.close()
        r = admin.post("/api/ai/route", data={"q": ""})
        assert r.status_code == 200
        assert r.json() == {"kind": "fallback"}
        conn = st.connect(db_path)
        assert conn.execute("SELECT COUNT(*) FROM ai_interaction").fetchone()[0] == 0
    finally:
        _reset(conn); conn.close()


def test_route_injection_admin_only_destination_rejected_for_viewer(viewer, db_path, monkeypatch):
    """A mocked model "steering" a viewer to /admin/users: the viewer's own
    catalog (role-filtered, same as search_index_for) never contains the
    'users' key at all, so this is caught by the ordinary allow-list check —
    no special-cased injection defense needed."""
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_router(conn, monkeypatch)
        conn.commit(); conn.close()
        _mock_route_answer(monkeypatch, "users", 0.95)
        r = viewer.post("/api/ai/route", data={"q": "show me the user accounts"})
        assert r.status_code == 200
        assert r.json() == {"kind": "fallback"}
        conn = st.connect(db_path)
        outcome, destination, confidence = _last_interaction(conn)
        assert outcome == "rejected_validation"
    finally:
        _reset(conn); conn.close()


def test_route_out_of_catalog_destination_falls_back(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_router(conn, monkeypatch)
        conn.commit(); conn.close()
        _mock_route_answer(monkeypatch, "nonexistent_page", 0.99)
        r = admin.post("/api/ai/route", data={"q": "take me somewhere"})
        assert r.json() == {"kind": "fallback"}
        conn = st.connect(db_path)
        assert _last_interaction(conn)[0] == "rejected_validation"
    finally:
        _reset(conn); conn.close()


def test_route_low_confidence_falls_back(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_router(conn, monkeypatch)
        conn.commit(); conn.close()
        _mock_route_answer(monkeypatch, "pulse", 0.2)
        r = admin.post("/api/ai/route", data={"q": "hmm"})
        assert r.json() == {"kind": "fallback"}
        conn = st.connect(db_path)
        assert _last_interaction(conn)[0] == "rejected_validation"
    finally:
        _reset(conn); conn.close()


def test_route_malformed_json_falls_back(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_router(conn, monkeypatch)
        conn.commit(); conn.close()
        monkeypatch.setattr(ai, "_http_generate", lambda *a, **kw: (_ for _ in ()).throw(
            ai.AIBadResponse("model output did not match the response schema")))
        r = admin.post("/api/ai/route", data={"q": "anything"})
        assert r.json() == {"kind": "fallback"}
        conn = st.connect(db_path)
        assert _last_interaction(conn)[0] == "fallback_error"
    finally:
        _reset(conn); conn.close()


def test_route_unconfigured_falls_back(admin, db_path, monkeypatch):
    monkeypatch.delenv("CSS_GEMINI_API_KEY", raising=False)
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    r = admin.post("/api/ai/route", data={"q": "anything"})
    assert r.json() == {"kind": "fallback"}


def test_route_budget_exceeded_falls_back(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_router(conn, monkeypatch)
        st.set_setting(conn, "ai_cap_nl_router", "0")
        conn.commit(); conn.close()
        r = admin.post("/api/ai/route", data={"q": "anything"})
        assert r.json() == {"kind": "fallback"}
        conn = st.connect(db_path)
        assert _last_interaction(conn)[0] == "fallback_budget"
    finally:
        _reset(conn); conn.close()


# ---- /api/ai/feedback: ownership + RBAC --------------------------------------

def test_feedback_owner_can_rate(viewer, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        viewer_id = conn.execute(
            "SELECT id FROM admin_user WHERE username='viewer@test.local'").fetchone()[0]
        iid = st.create_ai_interaction(conn, user_id=viewer_id, feature="nl_router",
                                       mode="router", outcome="ok")
        conn.commit()
        r = viewer.post("/api/ai/feedback", data={"interaction_id": iid, "rating": "up"})
        assert r.status_code == 204
        conn2 = st.connect(db_path)
        assert conn2.execute(
            "SELECT rating FROM ai_interaction WHERE id=?", (iid,)).fetchone()[0] == 1
        conn2.close()
    finally:
        _reset(conn); conn.close()


def test_feedback_non_owner_rejected(viewer, manager, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        viewer_id = conn.execute(
            "SELECT id FROM admin_user WHERE username='viewer@test.local'").fetchone()[0]
        iid = st.create_ai_interaction(conn, user_id=viewer_id, feature="nl_router",
                                       mode="router", outcome="ok")
        conn.commit(); conn.close()
        r = manager.post("/api/ai/feedback", data={"interaction_id": iid, "rating": "down"})
        assert r.status_code == 404
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()


def test_feedback_admin_can_rate_anyones(viewer, admin, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        viewer_id = conn.execute(
            "SELECT id FROM admin_user WHERE username='viewer@test.local'").fetchone()[0]
        iid = st.create_ai_interaction(conn, user_id=viewer_id, feature="nl_router",
                                       mode="router", outcome="ok")
        conn.commit(); conn.close()
        r = admin.post("/api/ai/feedback", data={"interaction_id": iid, "rating": "up"})
        assert r.status_code == 204
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()


def test_feedback_invalid_rating_rejected(viewer, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        iid = st.create_ai_interaction(conn, feature="nl_router", mode="router", outcome="ok")
        conn.commit()
        r = viewer.post("/api/ai/feedback", data={"interaction_id": iid, "rating": "sideways"})
        assert r.status_code == 400
    finally:
        _reset(conn); conn.close()


# ---- login redirect opt-in ----------------------------------------------------

def _login(client, username, password="Test1234!", next_path=None):
    data = {"username": username, "password": password}
    if next_path is not None:
        data["next"] = next_path
    return client.post("/login", data=data, follow_redirects=False)


def test_login_redirects_to_start_when_opted_in(client, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_router(conn, monkeypatch, landing_default="start")
        conn.commit(); conn.close()
        r = _login(client, "viewer@test.local")
        assert r.status_code == 303
        assert r.headers["location"] == "/start"
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()


def test_login_stays_on_hub_when_landing_default_is_hub(client, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_router(conn, monkeypatch, landing_default="hub")
        conn.commit(); conn.close()
        r = _login(client, "viewer@test.local")
        assert r.headers["location"] == "/"
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()


def test_login_stays_on_hub_when_ai_off(client, db_path, monkeypatch):
    monkeypatch.delenv("CSS_GEMINI_API_KEY", raising=False)
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        st.set_setting(conn, "ai_mode", "off")
        st.set_setting(conn, "ai_landing_default", "start")
        conn.commit(); conn.close()
        r = _login(client, "viewer@test.local")
        assert r.headers["location"] == "/"
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()


def test_login_honors_explicit_next(client, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_router(conn, monkeypatch, landing_default="start")
        conn.commit(); conn.close()
        r = _login(client, "viewer@test.local", next_path="/dashboard")
        assert r.headers["location"] == "/dashboard"
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()
