"""
/admin/ai — the AI console (docs/AI_INTEGRATION_PLAN.md Phase 0): status +
settings form + interaction log browser over ai_core.py.

Covers: admin-only RBAC (via the existing /admin-prefix cap, no new gating
code — same pattern as test_ux_insights.py), settings save + clamp + an
invalid mode falling back to "off", the audit row on both settings changes
and test-connection attempts, and the log browser's empty/populated states.

Autouse fixture below guarantees /admin/ai/test never reaches the real
network — it always monkeypatches ai_core._http_generate.
"""
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


# ---- RBAC -----------------------------------------------------------------

def test_admin_ai_requires_admin(admin, viewer, manager, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    assert admin.get("/admin/ai").status_code == 200
    assert viewer.get("/admin/ai").status_code == 403
    assert manager.get("/admin/ai").status_code == 403


def test_admin_ai_settings_requires_admin(viewer, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    assert viewer.post("/admin/ai/settings", data={"ai_mode": "router"}).status_code == 403


def test_admin_ai_test_requires_admin(viewer, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    assert viewer.post("/admin/ai/test").status_code == 403


# ---- status card ------------------------------------------------------------

def test_admin_ai_shows_not_configured_when_no_key(admin, db_path, monkeypatch):
    monkeypatch.delenv("CSS_GEMINI_API_KEY", raising=False)
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    body = admin.get("/admin/ai").text
    assert "not configured" in body


# ---- settings: save, clamp, invalid mode, audit ------------------------------

def test_admin_ai_settings_save_and_clamp(admin, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    try:
        data = {
            "ai_mode": "router",
            "ai_daily_cap": "50000",          # over max -> clamp to 1000
            "ai_log_retention_days": "1",     # under min -> clamp to 7
            "ai_log_prompts": "off",
            "ai_landing_default": "start",
            "ai_feature_verbatim": "on",
            "ai_cap_verbatim": "999999",      # over max -> clamp to 1000
        }
        r = admin.post("/admin/ai/settings", data=data, follow_redirects=False)
        assert r.status_code == 303
        conn = st.connect(db_path)
        assert st.get_setting(conn, "ai_mode") == "router"
        assert st.get_setting(conn, "ai_daily_cap") == "1000"
        assert st.get_setting(conn, "ai_log_retention_days") == "7"
        assert st.get_setting(conn, "ai_log_prompts") == "off"
        assert st.get_setting(conn, "ai_landing_default") == "start"
        assert st.get_setting(conn, "ai_feature_verbatim") == "1"
        assert st.get_setting(conn, "ai_cap_verbatim") == "1000"
        # a feature checkbox the browser omitted (unchecked) is saved disabled
        assert st.get_setting(conn, "ai_feature_report_draft") == "0"
    finally:
        _reset(conn); conn.close()


def test_admin_ai_settings_invalid_mode_falls_back_to_off(admin, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    try:
        admin.post("/admin/ai/settings", data={"ai_mode": "nonsense"}, follow_redirects=False)
        conn = st.connect(db_path)
        assert st.get_setting(conn, "ai_mode") == "off"
    finally:
        _reset(conn); conn.close()


def test_admin_ai_settings_writes_audit_row(admin, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    try:
        admin.post("/admin/ai/settings", data={"ai_mode": "router", "ai_daily_cap": "50"},
                   follow_redirects=False)
        conn = st.connect(db_path)
        row = conn.execute("SELECT action, target_type FROM audit_log "
                           "ORDER BY id DESC LIMIT 1").fetchone()
        assert row[0] == "ai_settings_changed"
        assert row[1] == "setting"
    finally:
        _reset(conn); conn.close()


# ---- test connection ---------------------------------------------------------

def test_admin_ai_test_connection_success(admin, db_path, monkeypatch):
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    try:
        monkeypatch.setattr(ai, "_http_generate", lambda *a, **kw: {
            "text": "OK", "parsed": None, "tokens_in": 1, "tokens_out": 1,
            "latency_ms": 42, "model": "gemini-test"})
        r = admin.post("/admin/ai/test", follow_redirects=False)
        assert r.status_code == 303
        assert "msg=" in r.headers["location"]
        conn = st.connect(db_path)
        outcome = conn.execute("SELECT outcome FROM ai_interaction WHERE feature='test' "
                               "ORDER BY id DESC LIMIT 1").fetchone()[0]
        assert outcome == "ok"
        audit_row = conn.execute("SELECT action FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
        assert audit_row[0] == "ai_test_connection"
    finally:
        _reset(conn); conn.close()


def test_admin_ai_test_connection_unconfigured_shows_error(admin, db_path, monkeypatch):
    monkeypatch.delenv("CSS_GEMINI_API_KEY", raising=False)
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    try:
        r = admin.post("/admin/ai/test", follow_redirects=False)
        assert r.status_code == 303
        assert "err=" in r.headers["location"]
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()


# ---- interaction log browser --------------------------------------------------

def test_admin_ai_log_browser_empty_state(admin, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    body = admin.get("/admin/ai?feature=harmonize").text
    assert "No AI interactions logged yet" in body


def test_admin_ai_log_browser_shows_rows(admin, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        st.create_ai_interaction(conn, feature="verbatim", mode="off", outcome="ok",
                                 latency_ms=123)
    finally:
        conn.close()
    try:
        body = admin.get("/admin/ai").text
        assert "verbatim" in body
        assert "123 ms" in body
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()
