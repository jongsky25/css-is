"""
POST /admin/ux-insights/analyze — docs/AI_INTEGRATION_PLAN.md Phase 3.

Covers: admin-only RBAC (same /admin-prefix gating as the rest of UX
Insights, no new gating code), a successful call returning the analysis text
+ interaction_id, AIError and budget-exceeded both falling back to the
existing-download notice instead of an error, the audit row, and that the
raw digits from an unmasked telemetry POST never reach the prompt handed to
the model (same end-to-end leak test as the handoff export, extended to the
AI call site).

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
    conn.execute("DELETE FROM ui_event")
    conn.execute("DELETE FROM spot_feedback")
    conn.execute("DELETE FROM feedback_update")
    conn.execute("DELETE FROM ai_interaction")
    conn.execute("DELETE FROM ai_budget")
    conn.execute("DELETE FROM app_setting WHERE key LIKE 'ai_%'")
    # Other test modules may leave this row with a NULL value (see
    # test_ux_insights.py's _reset for why that differs from no row at all —
    # get_setting only falls back to its default when the row is absent).
    conn.execute("DELETE FROM app_setting WHERE key='ui_telemetry_retention_days'")
    conn.commit()


def _configure(conn, monkeypatch):
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    st.set_setting(conn, "ai_mode", "router")


def _mock_analysis(monkeypatch, text="Top issue: the save button on the edit "
                                     "screen is triggering rage clicks."):
    monkeypatch.setattr(ai, "_http_generate", lambda *a, **kw: {
        "text": text, "parsed": None,
        "tokens_in": 400, "tokens_out": 60, "latency_ms": 900, "model": "gemini-test"})


def _last_interaction(conn):
    return conn.execute(
        "SELECT outcome, feature FROM ai_interaction "
        "WHERE feature='ux_analysis' ORDER BY id DESC LIMIT 1").fetchone()


def test_analyze_requires_admin(admin, viewer, manager, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch)
        conn.commit(); conn.close()
        _mock_analysis(monkeypatch)
        assert viewer.post("/admin/ux-insights/analyze").status_code == 403
        assert manager.post("/admin/ux-insights/analyze").status_code == 403
        assert admin.post("/admin/ux-insights/analyze").status_code == 200
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()


def test_analyze_success_returns_text_and_interaction_id(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch)
        conn.commit(); conn.close()
        _mock_analysis(monkeypatch, text="Fix the save button on the edit screen.")
        r = admin.post("/admin/ux-insights/analyze?days=30")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert "Fix the save button" in body["text"]
        assert "interaction_id" in body
        conn = st.connect(db_path)
        outcome, feature = _last_interaction(conn)
        assert outcome == "ok" and feature == "ux_analysis"
    finally:
        _reset(conn); conn.close()


def test_analyze_ai_error_falls_back_to_notice(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch)
        conn.commit(); conn.close()
        monkeypatch.setattr(ai, "_http_generate", lambda *a, **kw: (_ for _ in ()).throw(
            ai.AIBadResponse("boom")))
        r = admin.post("/admin/ux-insights/analyze")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False
        assert "notice" in body
        conn = st.connect(db_path)
        assert _last_interaction(conn)[0] == "fallback_error"
    finally:
        _reset(conn); conn.close()


def test_analyze_unconfigured_falls_back_to_notice(admin, db_path, monkeypatch):
    monkeypatch.delenv("CSS_GEMINI_API_KEY", raising=False)
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    r = admin.post("/admin/ux-insights/analyze")
    assert r.status_code == 200
    assert r.json()["ok"] is False


def test_analyze_budget_exceeded_falls_back(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch)
        st.set_setting(conn, "ai_cap_ux_analysis", "0")
        conn.commit(); conn.close()
        r = admin.post("/admin/ux-insights/analyze")
        assert r.status_code == 200
        assert r.json()["ok"] is False
        conn = st.connect(db_path)
        assert _last_interaction(conn)[0] == "fallback_budget"
    finally:
        _reset(conn); conn.close()


def test_analyze_writes_audit_row(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch)
        conn.commit(); conn.close()
        _mock_analysis(monkeypatch)
        admin.post("/admin/ux-insights/analyze?days=30")
        conn = st.connect(db_path)
        row = conn.execute(
            "SELECT action, target_type, summary FROM audit_log "
            "ORDER BY id DESC LIMIT 1").fetchone()
        assert row[0] == "export"
        assert row[1] == "ui_event"
        assert "AI analysis" in row[2]
    finally:
        _reset(conn); conn.close()


def test_analyze_never_leaks_raw_input_into_prompt(admin, viewer, db_path, monkeypatch):
    """Same end-to-end leak defense as the handoff export, extended to the
    prompt handed to the model: an unmasked digit posted through /telemetry
    must never reach ai_core.ask()'s prompt argument."""
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch)
        conn.commit(); conn.close()
    finally:
        pass
    r = viewer.post("/telemetry", json={"events": [
        {"event_type": "dead_click", "route": "/directory/person/482/edit",
         "session_id": "sess-raw-C",
         "element_text": "Call 09171234567 about client 90210"},
    ]})
    assert r.status_code == 204

    seen_prompts = []

    def _capture(prompt, **kw):
        seen_prompts.append(prompt)
        return {"text": "analysis", "parsed": None, "tokens_in": 1, "tokens_out": 1,
                "latency_ms": 1, "model": "gemini-test"}
    monkeypatch.setattr(ai, "_http_generate", _capture)

    r = admin.post("/admin/ux-insights/analyze?days=7")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert seen_prompts, "the AI call was never made"
    prompt = seen_prompts[0]
    assert "09171234567" not in prompt
    assert "90210" not in prompt
    assert "/directory/person/482/edit" not in prompt
    conn = st.connect(db_path); _reset(conn); conn.close()
