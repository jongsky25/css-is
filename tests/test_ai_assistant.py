"""
POST /api/ai/route `kind="action"` — docs/AI_INTEGRATION_PLAN.md Phase 9 (full
assistant mode).

Covers: the action kind and conversation history only ever activate at
ai_mode="assistant" with the "assistant_action" feature flag on; a role that
lacks an action's capability never even has it in its catalog, so a mocked
model "proposing" it is caught by the same allow-list check as any other bad
answer (the prompt-injection defense, same shape as Phase 1's destination
test); archive_activity's `fid` is validated against the caller's own
candidate list (never an arbitrary id); create_activity_draft and
export_report validate their args against the real endpoints' own rules;
confirmed actions log outcome=ok under the "assistant_action" feature (not
"nl_router") so /admin/ai can tell them apart.

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
    conn.execute("DELETE FROM learned_rule")  # seeded FAQ rules would preempt the model path
    conn.execute("DELETE FROM app_setting WHERE key LIKE 'ai_%'")
    conn.commit()


def _configure_assistant(conn, monkeypatch):
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    st.set_setting(conn, "ai_mode", "assistant")


def _mock_action_answer(monkeypatch, action_key, args, confidence=0.9):
    payload = {"kind": "action", "action_key": action_key, "args": args,
              "confidence": confidence, "reason": "because"}
    monkeypatch.setattr(ai, "_http_generate", lambda *a, **kw: {
        "text": json.dumps(payload), "parsed": payload,
        "tokens_in": 5, "tokens_out": 5, "latency_ms": 40, "model": "gemini-test"})


def _last_interaction(conn):
    return conn.execute(
        "SELECT outcome, feature, confidence FROM ai_interaction "
        "ORDER BY id DESC LIMIT 1").fetchone()


def _make_activity(db_path, created_by, topic, event_date="2026-06-01"):
    conn = st.connect(db_path)
    fid = st.create_form_instance(conn, survey_type=2, form="F2", event_date=event_date,
                                  topic=topic, created_by=created_by)
    conn.close()
    return fid


# ---- gating: mode + feature flag ----------------------------------------------

def test_action_kind_ignored_below_assistant_mode(manager, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
        st.set_setting(conn, "ai_mode", "answers")   # one rung below assistant
        conn.commit(); conn.close()
        _mock_action_answer(monkeypatch, "export_report",
                            {"report_type": "2", "report_fmt": "pdf"})
        r = manager.post("/api/ai/route", data={"q": "export the activities report"})
        assert r.json() == {"kind": "fallback"}
        conn = st.connect(db_path)
        assert _last_interaction(conn)[0] == "rejected_validation"
    finally:
        _reset(conn); conn.close()


def test_action_kind_ignored_when_feature_disabled(manager, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_assistant(conn, monkeypatch)
        st.set_setting(conn, "ai_feature_assistant_action", "0")
        conn.commit(); conn.close()
        _mock_action_answer(monkeypatch, "export_report",
                            {"report_type": "2", "report_fmt": "pdf"})
        r = manager.post("/api/ai/route", data={"q": "export the activities report"})
        assert r.json() == {"kind": "fallback"}
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()


# ---- create_activity_draft -----------------------------------------------------

def test_create_activity_draft_happy_path(manager, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_assistant(conn, monkeypatch)
        conn.commit(); conn.close()
        _mock_action_answer(monkeypatch, "create_activity_draft",
                            {"activity_name": "Team Sync", "event_date": "2026-08-01"})
        r = manager.post("/api/ai/route", data={"q": "start a draft for team sync on aug 1"})
        assert r.status_code == 200
        body = r.json()
        assert body["kind"] == "action"
        assert body["action"] == "create_activity_draft"
        assert body["method"] == "POST"
        assert body["url"] == "/create"
        assert body["fields"] == {
            "activity_name": "Team Sync", "event_date": "2026-08-01", "event_type": "bureau"}
        conn = st.connect(db_path)
        outcome, feature, confidence = _last_interaction(conn)
        assert outcome == "ok" and feature == "assistant_action" and confidence == 0.9
    finally:
        _reset(conn); conn.close()


def test_create_activity_draft_bad_date_falls_back(manager, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_assistant(conn, monkeypatch)
        conn.commit(); conn.close()
        _mock_action_answer(monkeypatch, "create_activity_draft",
                            {"activity_name": "Team Sync", "event_date": "not-a-date"})
        r = manager.post("/api/ai/route", data={"q": "start a draft"})
        assert r.json() == {"kind": "fallback"}
        conn = st.connect(db_path)
        assert _last_interaction(conn)[0] == "rejected_validation"
    finally:
        _reset(conn); conn.close()


def test_create_activity_draft_blank_name_falls_back(manager, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_assistant(conn, monkeypatch)
        conn.commit(); conn.close()
        _mock_action_answer(monkeypatch, "create_activity_draft",
                            {"activity_name": "   ", "event_date": "2026-08-01"})
        r = manager.post("/api/ai/route", data={"q": "start a draft"})
        assert r.json() == {"kind": "fallback"}
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()


def test_create_activity_draft_refused_for_viewer(viewer, db_path, monkeypatch):
    """A viewer's action catalog never contains create_activity_draft at all
    (no create_activity cap) — a mocked model "proposing" it anyway is caught
    the same way an out-of-catalog destination is."""
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_assistant(conn, monkeypatch)
        conn.commit(); conn.close()
        _mock_action_answer(monkeypatch, "create_activity_draft",
                            {"activity_name": "Team Sync", "event_date": "2026-08-01"})
        r = viewer.post("/api/ai/route", data={"q": "start a draft"})
        assert r.json() == {"kind": "fallback"}
        conn = st.connect(db_path)
        assert _last_interaction(conn)[0] == "rejected_validation"
    finally:
        _reset(conn); conn.close()


# ---- archive_activity ------------------------------------------------------------

def test_archive_activity_happy_path(manager, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_assistant(conn, monkeypatch)
        conn.commit(); conn.close()
        fid = _make_activity(db_path, "manager@test.local", "Q3 Training")
        _mock_action_answer(monkeypatch, "archive_activity", {"fid": str(fid)})
        r = manager.post("/api/ai/route", data={"q": "archive the q3 training"})
        assert r.status_code == 200
        body = r.json()
        assert body["kind"] == "action"
        assert body["method"] == "POST"
        assert body["url"] == f"/activities/instance/{fid}/archive"
        assert "Q3 Training" in body["description"]
        conn = st.connect(db_path)
        outcome, feature, _ = _last_interaction(conn)
        assert outcome == "ok" and feature == "assistant_action"
    finally:
        _reset(conn); conn.close()


def test_archive_activity_out_of_candidates_falls_back(manager, db_path, monkeypatch):
    """A mocked model naming an id that was never offered in the Archivable
    activities list (e.g. another manager's activity it hallucinated or was
    injected into guessing) is rejected server-side — never trusted."""
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_assistant(conn, monkeypatch)
        conn.commit(); conn.close()
        other_fid = _make_activity(db_path, "admin@test.local", "Admin-only activity")
        _mock_action_answer(monkeypatch, "archive_activity", {"fid": str(other_fid)})
        r = manager.post("/api/ai/route", data={"q": "archive that other activity"})
        assert r.json() == {"kind": "fallback"}
        conn = st.connect(db_path)
        assert _last_interaction(conn)[0] == "rejected_validation"
    finally:
        _reset(conn); conn.close()


def test_archive_activity_refused_for_viewer(viewer, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_assistant(conn, monkeypatch)
        conn.commit(); conn.close()
        _mock_action_answer(monkeypatch, "archive_activity", {"fid": "1"})
        r = viewer.post("/api/ai/route", data={"q": "archive something"})
        assert r.json() == {"kind": "fallback"}
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()


# ---- export_report ---------------------------------------------------------------

def test_export_report_happy_path(viewer, db_path, monkeypatch):
    """export_report's cap is "view" — every role, including viewer, may
    propose and confirm it."""
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_assistant(conn, monkeypatch)
        conn.commit(); conn.close()
        _mock_action_answer(monkeypatch, "export_report",
                            {"report_type": "2", "report_fmt": "pdf"})
        r = viewer.post("/api/ai/route", data={"q": "export the activities report as pdf"})
        assert r.status_code == 200
        body = r.json()
        assert body["kind"] == "action"
        assert body["method"] == "GET"
        assert body["url"] == "/reports/export?type=2&fmt=pdf"
        assert body["fields"] == {}
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()


def test_export_report_bad_format_falls_back(viewer, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_assistant(conn, monkeypatch)
        conn.commit(); conn.close()
        _mock_action_answer(monkeypatch, "export_report",
                            {"report_type": "2", "report_fmt": "csv"})
        r = viewer.post("/api/ai/route", data={"q": "export as csv"})
        assert r.json() == {"kind": "fallback"}
        conn = st.connect(db_path)
        assert _last_interaction(conn)[0] == "rejected_validation"
    finally:
        _reset(conn); conn.close()


# ---- confidence floor + budget --------------------------------------------------

def test_action_low_confidence_falls_back(manager, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_assistant(conn, monkeypatch)
        conn.commit(); conn.close()
        _mock_action_answer(monkeypatch, "export_report",
                            {"report_type": "1", "report_fmt": "docx"}, confidence=0.2)
        r = manager.post("/api/ai/route", data={"q": "export something"})
        assert r.json() == {"kind": "fallback"}
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()


def test_action_budget_exceeded_falls_back(manager, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_assistant(conn, monkeypatch)
        st.set_setting(conn, "ai_cap_nl_router", "0")
        conn.commit(); conn.close()
        r = manager.post("/api/ai/route", data={"q": "export something"})
        assert r.json() == {"kind": "fallback"}
        conn = st.connect(db_path)
        assert _last_interaction(conn)[0] == "fallback_budget"
    finally:
        _reset(conn); conn.close()


# ---- conversation history --------------------------------------------------------

def test_history_is_forwarded_to_the_prompt_in_assistant_mode(manager, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_assistant(conn, monkeypatch)
        conn.commit(); conn.close()
        seen_prompts = []

        def _capture(prompt, **kw):
            seen_prompts.append(prompt)
            payload = {"kind": "navigate", "destination": "pulse", "confidence": 0.9}
            return {"text": json.dumps(payload), "parsed": payload,
                    "tokens_in": 5, "tokens_out": 5, "latency_ms": 40, "model": "gemini-test"}
        monkeypatch.setattr(ai, "_http_generate", _capture)

        history = [{"role": "user", "text": "how is satisfaction trending"},
                   {"role": "assistant", "text": "Suggested opening Trends."}]
        r = manager.post("/api/ai/route",
                         data={"q": "yeah open it", "history": json.dumps(history)})
        assert r.status_code == 200
        assert seen_prompts
        assert "how is satisfaction trending" in seen_prompts[0]
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()


def test_malformed_history_does_not_break_the_request(manager, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure_assistant(conn, monkeypatch)
        conn.commit(); conn.close()
        _mock_action_answer(monkeypatch, "export_report",
                            {"report_type": "1", "report_fmt": "docx"})
        r = manager.post("/api/ai/route",
                         data={"q": "export it", "history": "{not json"})
        assert r.status_code == 200
        assert r.json()["kind"] == "action"
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()
