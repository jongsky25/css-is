"""
POST /activities/{event_token}/messages/ai-draft — docs/AI_INTEGRATION_PLAN.md
Phase 7 (v2.10). Rewrites one welcome/ending draft from the activity's own
metadata only (title/date/venue/modality/organizer) in the requested tone.

Covers: creator/admin-only RBAC (same _can_manage_event gate as the rest of
the manage page), a successful call returning the draft text + interaction_id,
AIError falling back to a plain notice, budget-exceeded falling back, a
response missing the literal {name} token being rejected (logged
rejected_validation) and falling back, an invalid slot/tone being rejected,
the audit row, that nothing is written to the event's stored messages (the
existing autosave route owns that), and that the prompt handed to the model
never carries attendee data — only activity metadata.

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


def _configure(conn, monkeypatch):
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    st.set_setting(conn, "ai_mode", "router")


def _make_event(conn, created_by, **kw):
    fids = [st.create_form_instance(conn, 2, "F2", "2099-03-03",
                                    venue="Probe Hall", topic="Probe Activity")]
    ev = st.create_event(conn, "Immunization Forum", "2099-03-03", venue="Probe Hall",
                         organizer="BLHSD", form_instance_ids=fids,
                         created_by=created_by, **kw)
    conn.commit()
    return ev, fids


def _cleanup(conn, ev, fids):
    conn.execute("DELETE FROM response WHERE attendee_id IN "
                 "(SELECT id FROM attendee WHERE event_id=?)", (ev["id"],))
    conn.execute("DELETE FROM attendee WHERE event_id=?", (ev["id"],))
    conn.execute("DELETE FROM event_form WHERE event_id=?", (ev["id"],))
    conn.execute("DELETE FROM event WHERE id=?", (ev["id"],))
    conn.executemany("DELETE FROM form_instance WHERE id=?", [(f,) for f in fids])
    conn.commit()


def _mock_draft(monkeypatch, text="Hi {name}! So glad you could join Immunization Forum."):
    monkeypatch.setattr(ai, "_http_generate", lambda *a, **kw: {
        "text": "{}", "parsed": {"text": text},
        "tokens_in": 80, "tokens_out": 30, "latency_ms": 400, "model": "gemini-test"})


def _last_interaction(conn):
    return conn.execute(
        "SELECT outcome, feature FROM ai_interaction "
        "WHERE feature='messages' ORDER BY id DESC LIMIT 1").fetchone()


def test_ai_draft_requires_creator_or_admin(admin, viewer, manager, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    _configure(conn, monkeypatch)
    ev, fids = _make_event(conn, "manager@test.local")   # creator == manager fixture
    tok = ev["event_token"]
    conn.commit(); conn.close()
    try:
        _mock_draft(monkeypatch)
        r = viewer.post(f"/activities/{tok}/messages/ai-draft",
                        data={"slot": "welcome", "tone": "personal"})
        assert r.status_code == 403
        r = admin.post(f"/activities/{tok}/messages/ai-draft",
                       data={"slot": "welcome", "tone": "personal"})
        assert r.status_code == 200
        r = manager.post(f"/activities/{tok}/messages/ai-draft",
                         data={"slot": "welcome", "tone": "personal"})
        assert r.status_code == 200
    finally:
        conn = st.connect(db_path); _cleanup(conn, ev, fids); _reset(conn); conn.close()


def test_ai_draft_success_returns_text_and_interaction_id(manager, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    _configure(conn, monkeypatch)
    ev, fids = _make_event(conn, "manager@test.local")
    tok = ev["event_token"]
    conn.commit(); conn.close()
    try:
        _mock_draft(monkeypatch, text="Hi {name}! Immunization Forum awaits — glad you're here.")
        r = manager.post(f"/activities/{tok}/messages/ai-draft",
                         data={"slot": "welcome", "tone": "warm"})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is True
        assert "{name}" in body["text"]
        assert "Immunization Forum" in body["text"]
        assert "interaction_id" in body
        conn = st.connect(db_path)
        outcome, feature = _last_interaction(conn)
        assert outcome == "ok" and feature == "messages"
    finally:
        conn = st.connect(db_path); _cleanup(conn, ev, fids); _reset(conn); conn.close()


def test_ai_draft_invalid_slot_or_tone_rejected(manager, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    _configure(conn, monkeypatch)
    ev, fids = _make_event(conn, "manager@test.local")
    tok = ev["event_token"]
    conn.commit(); conn.close()
    try:
        _mock_draft(monkeypatch)
        assert manager.post(f"/activities/{tok}/messages/ai-draft",
                            data={"slot": "middle", "tone": "personal"}).status_code == 400
        assert manager.post(f"/activities/{tok}/messages/ai-draft",
                            data={"slot": "welcome", "tone": "sarcastic"}).status_code == 400
    finally:
        conn = st.connect(db_path); _cleanup(conn, ev, fids); _reset(conn); conn.close()


def test_ai_draft_missing_name_token_rejected_and_logged(manager, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    _configure(conn, monkeypatch)
    ev, fids = _make_event(conn, "manager@test.local")
    tok = ev["event_token"]
    conn.commit(); conn.close()
    try:
        _mock_draft(monkeypatch, text="Welcome to Immunization Forum, we're glad you're here!")
        r = manager.post(f"/activities/{tok}/messages/ai-draft",
                         data={"slot": "welcome", "tone": "personal"})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False
        assert "notice" in body
        conn = st.connect(db_path)
        assert _last_interaction(conn)[0] == "rejected_validation"
    finally:
        conn = st.connect(db_path); _cleanup(conn, ev, fids); _reset(conn); conn.close()


def test_ai_draft_ai_error_falls_back_to_notice(manager, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    _configure(conn, monkeypatch)
    ev, fids = _make_event(conn, "manager@test.local")
    tok = ev["event_token"]
    conn.commit(); conn.close()
    try:
        monkeypatch.setattr(ai, "_http_generate", lambda *a, **kw: (_ for _ in ()).throw(
            ai.AIBadResponse("boom")))
        r = manager.post(f"/activities/{tok}/messages/ai-draft",
                         data={"slot": "ending", "tone": "concise"})
        assert r.status_code == 200
        body = r.json()
        assert body["ok"] is False
        assert "notice" in body
        conn = st.connect(db_path)
        assert _last_interaction(conn)[0] == "fallback_error"
    finally:
        conn = st.connect(db_path); _cleanup(conn, ev, fids); _reset(conn); conn.close()


def test_ai_draft_budget_exceeded_falls_back(manager, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    _configure(conn, monkeypatch)
    st.set_setting(conn, "ai_cap_messages", "0")
    ev, fids = _make_event(conn, "manager@test.local")
    tok = ev["event_token"]
    conn.commit(); conn.close()
    try:
        r = manager.post(f"/activities/{tok}/messages/ai-draft",
                         data={"slot": "welcome", "tone": "personal"})
        assert r.status_code == 200
        assert r.json()["ok"] is False
        conn = st.connect(db_path)
        assert _last_interaction(conn)[0] == "fallback_budget"
    finally:
        conn = st.connect(db_path); _cleanup(conn, ev, fids); _reset(conn); conn.close()


def test_ai_draft_writes_audit_row(manager, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    _configure(conn, monkeypatch)
    ev, fids = _make_event(conn, "manager@test.local")
    tok = ev["event_token"]
    conn.commit(); conn.close()
    try:
        _mock_draft(monkeypatch)
        manager.post(f"/activities/{tok}/messages/ai-draft",
                     data={"slot": "welcome", "tone": "personal"})
        conn = st.connect(db_path)
        row = conn.execute(
            "SELECT action, target_type, target_id FROM audit_log "
            "ORDER BY id DESC LIMIT 1").fetchone()
        assert row[0] == "ai_message_draft"
        assert row[1] == "event"
        assert str(row[2]) == str(ev["id"])
    finally:
        conn = st.connect(db_path); _cleanup(conn, ev, fids); _reset(conn); conn.close()


def test_ai_draft_never_writes_stored_messages(manager, db_path, monkeypatch):
    """Read-only: only the existing autosave POST .../messages persists text."""
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    _configure(conn, monkeypatch)
    ev, fids = _make_event(conn, "manager@test.local")
    tok = ev["event_token"]
    conn.commit(); conn.close()
    try:
        _mock_draft(monkeypatch, text="Hi {name}! Welcome aboard.")
        manager.post(f"/activities/{tok}/messages/ai-draft",
                     data={"slot": "welcome", "tone": "personal"})
        conn = st.connect(db_path)
        assert st.get_event(conn, tok)["welcome_message"] is None
    finally:
        conn = st.connect(db_path); _cleanup(conn, ev, fids); _reset(conn); conn.close()


def test_ai_draft_prompt_carries_only_activity_metadata(manager, db_path, monkeypatch):
    """No attendee data ever reaches the prompt — only title/date/venue/
    modality/organizer, none of which is respondent PII."""
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    _configure(conn, monkeypatch)
    ev, fids = _make_event(conn, "manager@test.local")
    tok = ev["event_token"]
    conn.commit(); conn.close()

    seen_prompts = []

    def _capture(prompt, **kw):
        seen_prompts.append(prompt)
        return {"text": "{}", "parsed": {"text": "Hi {name}! Welcome to Immunization Forum."},
                "tokens_in": 1, "tokens_out": 1, "latency_ms": 1, "model": "gemini-test"}
    monkeypatch.setattr(ai, "_http_generate", _capture)

    try:
        r = manager.post(f"/activities/{tok}/messages/ai-draft",
                         data={"slot": "welcome", "tone": "professional"})
        assert r.status_code == 200
        assert r.json()["ok"] is True
        assert seen_prompts, "the AI call was never made"
        prompt = seen_prompts[0]
        assert "Immunization Forum" in prompt
        assert "Probe Hall" in prompt
        assert "BLHSD" in prompt
        assert "face-to-face" in prompt
    finally:
        conn = st.connect(db_path); _cleanup(conn, ev, fids); _reset(conn); conn.close()
