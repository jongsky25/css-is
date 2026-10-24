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
from datetime import timedelta
import json

import ai_core as ai
import storage as st
import tzutil as tz


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


def test_admin_ai_loads_with_gemini_unconfigured_and_groq_available(admin, db_path, monkeypatch):
    """Regression: ai_available(conn) must be computed before the route's DB
    connection is closed. Gemini unconfigured + Groq configured is exactly
    the combination that made ai_available() fall through to a DB read
    (fallback_enabled(conn)) instead of short-circuiting on ai_configured()
    or groq_configured() alone — with no CSS_GROQ_API_KEY, the same call
    short-circuits before ever touching the (by-then-closed) connection,
    which is why that gap survived until a live Space with Groq configured
    hit it as a 500 on every /admin/ai load."""
    monkeypatch.delenv("CSS_GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("CSS_GROQ_API_KEY", "groq-key")
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    assert admin.get("/admin/ai").status_code == 200


def test_admin_ai_harmonize_checkbox_defaults_unchecked(admin, db_path):
    """docs/AI_INTEGRATION_PLAN.md Phase 8: harmonize is the one feature that
    must render unchecked with no setting saved yet, unlike every other
    feature's checkbox (which defaults checked)."""
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    body = admin.get("/admin/ai").text
    harmonize_row = body[body.index('name="ai_feature_harmonize"'):]
    assert "checked" not in harmonize_row.split(">", 1)[0]
    verbatim_row = body[body.index('name="ai_feature_verbatim"'):]
    assert "checked" in verbatim_row.split(">", 1)[0]


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


def test_admin_ai_operations_summary_uses_full_window_and_metadata_only(admin, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    now = tz.now_local()
    stamp = now.isoformat(timespec="seconds")
    try:
        conn.executemany(
            "INSERT INTO ai_interaction(created_at,feature,mode,outcome,provider,latency_ms,"
            "tokens_in,tokens_out,rating,prompt_masked) VALUES (?,?,?,?,?,?,?,?,?,?)",
            [(stamp, "nl_router", "assistant", "ok", "gemini", 100, 10, 5,
              1 if i == 0 else None, "PRIVATE-SUMMARY-CONTENT") for i in range(201)])
        conn.execute(
            "INSERT INTO ai_interaction(created_at,feature,mode,outcome,provider,latency_ms,"
            "tokens_in,tokens_out,rating) VALUES (?,?,?,?,?,?,?,?,?)",
            (stamp, "nl_help", "assistant", "rejected_validation", "groq", 200, 2, 1, -1))
        conn.execute(
            "INSERT INTO ai_interaction(created_at,feature,mode,outcome,provider) VALUES (?,?,?,?,?)",
            (stamp, "nl_help", "assistant", "fallback_budget", "groq"))
        conn.execute(
            "INSERT INTO ai_interaction(created_at,feature,mode,outcome,provider,latency_ms) VALUES (?,?,?,?,?,?)",
            (stamp, "nl_router", "assistant", "ok", "rules", 0))
        for when in (now - timedelta(days=8), now + timedelta(hours=1)):
            conn.execute(
                "INSERT INTO ai_interaction(created_at,feature,mode,outcome,provider) VALUES (?,?,?,?,?)",
                (when.isoformat(timespec="seconds"), "nl_router", "assistant", "ok", "gemini"))
        conn.commit()
        rows = st.ai_operations_summary(
            conn, (now - timedelta(days=7)).isoformat(timespec="seconds"), stamp)
        assert [(r['provider'], r['interactions']) for r in rows] == [
            ('gemini', 201), ('groq', 2), ('rules', 1)]
        assert rows[0]['served'] == 201 and rows[0]['positive'] == 1
        assert rows[0]['mean_latency_ms'] == 100 and rows[0]['latency_samples'] == 201
        assert (rows[0]['tokens_in'], rows[0]['tokens_out'], rows[0]['token_samples']) == (2010, 1005, 201)
        assert rows[1]['rejected'] == 1 and rows[1]['fallback'] == 1 and rows[1]['negative'] == 1
        assert rows[1]['latency_samples'] == 1 and rows[1]['token_samples'] == 1
        assert 'PRIVATE-SUMMARY-CONTENT' not in json.dumps(rows)
    finally:
        conn.close()
    body = admin.get('/admin/ai').text
    card = body.split('<h2>Last 7 days</h2>', 1)[1].split('<h2>Settings</h2>', 1)[0]
    assert '201</b> interactions' in card
    assert '100 ms' in card and '201 measured' in card
    assert '2010 in / 1005 out' in card
    assert 'PRIVATE-SUMMARY-CONTENT' not in card
