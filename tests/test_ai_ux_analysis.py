"""
POST /admin/ux-insights/analyze — docs/AI_INTEGRATION_PLAN.md Phase 3.

Covers: admin-only (same gate as /admin/ux-insights itself); a successful
mocked call renders {"ok": true, "text", "interaction_id"} and writes an
audit row; any AIError (unconfigured, mode off, feature flag off, budget
exceeded) falls back to {"ok": false} with no user-facing error; the
interaction is logged under feature "ux_analysis" so /admin/ai can tell it
apart from the router/answers features.

Autouse fixture below guarantees this file never reaches the real network —
it always monkeypatches ai_core._http_generate.
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


def _configure(conn, monkeypatch, mode):
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    st.set_setting(conn, "ai_mode", mode)


def _mock_generate(monkeypatch, text="Here is the analysis."):
    monkeypatch.setattr(ai, "_http_generate", lambda *a, **kw: {
        "text": text, "parsed": None,
        "tokens_in": 50, "tokens_out": 40, "latency_ms": 120, "model": "gemini-test"})


def _last_interaction(conn):
    return conn.execute(
        "SELECT feature, outcome FROM ai_interaction ORDER BY id DESC LIMIT 1").fetchone()


def test_analyze_requires_admin(admin, viewer, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    assert viewer.post("/admin/ux-insights/analyze", data={"days": 30}).status_code == 403
    assert admin.post("/admin/ux-insights/analyze", data={"days": 30}).status_code in (200, 500)


def test_analyze_success_renders_mocked_text_and_audits(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch, "assistant")
        conn.commit(); conn.close()
        _mock_generate(monkeypatch, text="Fix the dead clicks on /monitor first.")
        r = admin.post("/admin/ux-insights/analyze", data={"days": 30})
        body = r.json()
        assert body["ok"] is True
        assert body["text"] == "Fix the dead clicks on /monitor first."
        assert body["interaction_id"]
        conn = st.connect(db_path)
        feature, outcome = _last_interaction(conn)
        assert feature == "ux_analysis" and outcome == "ok"
        row = conn.execute(
            "SELECT action FROM audit_log ORDER BY id DESC LIMIT 1").fetchone()
        assert row[0] == "ai_ux_analysis"
    finally:
        _reset(conn); conn.close()


def test_analyze_falls_back_when_ai_off(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch, "off")
        conn.commit(); conn.close()
        _mock_generate(monkeypatch)
        r = admin.post("/admin/ux-insights/analyze", data={"days": 30})
        assert r.json() == {"ok": False}
        conn = st.connect(db_path)
        assert _last_interaction(conn) == ("ux_analysis", "no_config")
    finally:
        _reset(conn); conn.close()


def test_analyze_falls_back_when_feature_disabled(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch, "assistant")
        st.set_setting(conn, "ai_feature_ux_analysis", "0")
        conn.commit(); conn.close()
        _mock_generate(monkeypatch)
        r = admin.post("/admin/ux-insights/analyze", data={"days": 30})
        assert r.json() == {"ok": False}
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()


def test_analyze_falls_back_once_daily_cap_reached(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch, "assistant")
        st.set_setting(conn, "ai_cap_ux_analysis", "1")
        conn.commit(); conn.close()
        _mock_generate(monkeypatch)
        first = admin.post("/admin/ux-insights/analyze", data={"days": 30})
        assert first.json()["ok"] is True
        second = admin.post("/admin/ux-insights/analyze", data={"days": 30})
        assert second.json() == {"ok": False}
        conn = st.connect(db_path)
        assert _last_interaction(conn) == ("ux_analysis", "fallback_budget")
    finally:
        _reset(conn); conn.close()
