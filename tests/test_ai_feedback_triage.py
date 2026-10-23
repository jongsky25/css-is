"""
POST /admin/feedback/{fid}/ai-suggest — docs/AI_INTEGRATION_PLAN.md Phase 6.

Covers: admin-only RBAC (`triage_feedback`, same gate as the rest of the
Spot Feedback board), a successful call returning a status/severity/
duplicate_of/reason suggestion + interaction_id, AIError and
budget-exceeded both falling back to a plain notice instead of an error,
the audit row, the server-side allow-list rejecting a suggested
duplicate_of id that wasn't in the candidate list this endpoint itself
built, and that the raw feedback message is masked before it reaches the
prompt handed to the model. The endpoint never writes to spot_feedback
itself — only the pre-existing POST /admin/feedback/{fid} form does that.

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
    conn.execute("DELETE FROM spot_feedback")
    conn.execute("DELETE FROM feedback_update")
    conn.execute("DELETE FROM ai_interaction")
    conn.execute("DELETE FROM ai_budget")
    conn.execute("DELETE FROM app_setting WHERE key LIKE 'ai_%'")
    st.set_setting(conn, "spot_feedback_enabled", "1")
    conn.commit()


def _configure(conn, monkeypatch):
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    st.set_setting(conn, "ai_mode", "router")


def _mock_suggestion(monkeypatch, *, status="Reviewing", severity="Medium",
                     duplicate_of=0, reason="Looks like a UI glitch on the edit screen."):
    monkeypatch.setattr(ai, "_http_generate", lambda *a, **kw: {
        "text": "{}", "parsed": {"status": status, "severity": severity,
                                 "duplicate_of": duplicate_of, "reason": reason},
        "tokens_in": 120, "tokens_out": 40, "latency_ms": 500, "model": "gemini-test"})


def _last_interaction(conn):
    return conn.execute(
        "SELECT outcome, feature FROM ai_interaction "
        "WHERE feature='feedback_triage' ORDER BY id DESC LIMIT 1").fetchone()


def _make_item(conn, message="the save button does nothing"):
    return st.create_spot_feedback(conn, user_id=1, submitter="u@x", page_url="/dashboard",
                                   element_selector=".save", region_json=None, message=message)


def test_suggest_requires_admin(admin, viewer, manager, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch)
        fid = _make_item(conn)
        conn.commit(); conn.close()
        _mock_suggestion(monkeypatch)
        assert viewer.post(f"/admin/feedback/{fid}/ai-suggest").status_code == 403
        assert manager.post(f"/admin/feedback/{fid}/ai-suggest").status_code == 403
        assert admin.post(f"/admin/feedback/{fid}/ai-suggest").status_code == 200
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()


def test_suggest_success_returns_fields_and_interaction_id(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch)
        fid = _make_item(conn)
        conn.commit(); conn.close()
        _mock_suggestion(monkeypatch, status="Will address", severity="High",
                         reason="Blocks saving edits.")
        r = admin.post(f"/admin/feedback/{fid}/ai-suggest")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert body["status"] == "Will address"
        assert body["severity"] == "High"
        assert body["duplicate_of"] is None      # model said 0 == "no match"
        assert "Blocks saving" in body["reason"]
        assert "interaction_id" in body
        conn = st.connect(db_path)
        outcome, feature = _last_interaction(conn)
        assert outcome == "ok" and feature == "feedback_triage"
    finally:
        _reset(conn); conn.close()


def test_suggest_missing_item_404s(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    _configure(conn, monkeypatch)
    conn.commit(); conn.close()
    r = admin.post("/admin/feedback/999999/ai-suggest")
    assert r.status_code == 404
    conn = st.connect(db_path); _reset(conn); conn.close()


def test_suggest_ai_error_falls_back_to_notice(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch)
        fid = _make_item(conn)
        conn.commit(); conn.close()
        monkeypatch.setattr(ai, "_http_generate", lambda *a, **kw: (_ for _ in ()).throw(
            ai.AIBadResponse("boom")))
        r = admin.post(f"/admin/feedback/{fid}/ai-suggest")
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False
        assert "notice" in body
        conn = st.connect(db_path)
        assert _last_interaction(conn)[0] == "fallback_error"
    finally:
        _reset(conn); conn.close()


def test_suggest_unconfigured_falls_back_to_notice(admin, db_path, monkeypatch):
    monkeypatch.delenv("CSS_GEMINI_API_KEY", raising=False)
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    fid = _make_item(conn)
    conn.commit(); conn.close()
    r = admin.post(f"/admin/feedback/{fid}/ai-suggest")
    assert r.status_code == 200
    assert r.json()["ok"] is False
    conn = st.connect(db_path); _reset(conn); conn.close()


def test_suggest_budget_exceeded_falls_back(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch)
        st.set_setting(conn, "ai_cap_feedback_triage", "0")
        fid = _make_item(conn)
        conn.commit(); conn.close()
        r = admin.post(f"/admin/feedback/{fid}/ai-suggest")
        assert r.status_code == 200
        assert r.json()["ok"] is False
        conn = st.connect(db_path)
        assert _last_interaction(conn)[0] == "fallback_budget"
    finally:
        _reset(conn); conn.close()


def test_suggest_writes_audit_row(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch)
        fid = _make_item(conn)
        conn.commit(); conn.close()
        _mock_suggestion(monkeypatch)
        admin.post(f"/admin/feedback/{fid}/ai-suggest")
        conn = st.connect(db_path)
        row = conn.execute(
            "SELECT action, target_type, target_id FROM audit_log "
            "ORDER BY id DESC LIMIT 1").fetchone()
        assert row[0] == "ai_feedback_suggest"
        assert row[1] == "spot_feedback"
        assert str(row[2]) == str(fid)
    finally:
        _reset(conn); conn.close()


def test_suggest_never_writes_to_spot_feedback(admin, db_path, monkeypatch):
    """The suggest endpoint is read-only — only the existing triage form
    (POST /admin/feedback/{fid}) may change status/severity/duplicate_of."""
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch)
        fid = _make_item(conn)
        conn.commit(); conn.close()
        _mock_suggestion(monkeypatch, status="Done", severity="Critical")
        admin.post(f"/admin/feedback/{fid}/ai-suggest")
        conn = st.connect(db_path)
        entry = st.get_spot_feedback(conn, fid)
        assert entry["status"] == "New" and entry["severity"] is None
    finally:
        _reset(conn); conn.close()


def test_suggest_rejects_duplicate_of_outside_candidate_allowlist(admin, db_path, monkeypatch):
    """A resolved item is never offered as a candidate — if the model still
    names an id outside the allow-list this endpoint built, it's dropped."""
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    _configure(conn, monkeypatch)
    fid = _make_item(conn)
    resolved = _make_item(conn, message="an old, already-closed item")
    st.update_spot_feedback(conn, resolved, status="Done", admin_note=None)
    conn.commit(); conn.close()
    # The model hallucinates a duplicate id that was never in the candidate list
    # this endpoint built (either a resolved item, or one that doesn't exist).
    _mock_suggestion(monkeypatch, duplicate_of=resolved)
    r = admin.post(f"/admin/feedback/{fid}/ai-suggest")
    assert r.status_code == 200
    assert r.json()["ok"] is False
    conn = st.connect(db_path); _reset(conn); conn.close()


def test_suggest_accepts_duplicate_of_within_candidate_allowlist(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    _configure(conn, monkeypatch)
    fid = _make_item(conn)
    other = _make_item(conn, message="save button broken here too")
    conn.commit(); conn.close()
    _mock_suggestion(monkeypatch, duplicate_of=other)
    r = admin.post(f"/admin/feedback/{fid}/ai-suggest")
    assert r.status_code == 200
    assert r.json()["duplicate_of"] == other
    conn = st.connect(db_path); _reset(conn); conn.close()


def test_suggest_never_leaks_raw_message_into_prompt(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch)
        fid = _make_item(conn, message="Call 09171234567 about this, it's broken")
        conn.commit(); conn.close()
    finally:
        pass

    seen_prompts = []

    def _capture(prompt, **kw):
        seen_prompts.append(prompt)
        return {"text": "{}", "parsed": {"status": "New", "severity": "Low",
                                         "duplicate_of": 0, "reason": "ok"},
                "tokens_in": 1, "tokens_out": 1, "latency_ms": 1, "model": "gemini-test"}
    monkeypatch.setattr(ai, "_http_generate", _capture)

    r = admin.post(f"/admin/feedback/{fid}/ai-suggest")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    assert seen_prompts, "the AI call was never made"
    assert "09171234567" not in seen_prompts[0]
    conn = st.connect(db_path); _reset(conn); conn.close()
