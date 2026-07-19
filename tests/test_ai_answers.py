"""
POST /api/ai/route kind=answer|help — docs/AI_INTEGRATION_PLAN.md Phase 2.

Covers: mode="router" never exposes the answer/help options (a mocked model
returning one anyway is still caught server-side, same defense-in-depth as
Phase 1's out-of-catalog destination check); the answer-slot and help-key
allow-lists enforced exactly like Phase 1's destination allow-list, including
role filtering (a viewer's help catalog never contains a manager-only page);
answer text is a server template rendered against mocked aggregates, never
model-authored; help text/link come from tours.py content; low confidence
and the per-capability feature flags all fall back; the interaction log's
feature column is corrected to nl_answer/nl_help so /admin/ai can tell them
apart from a plain navigation.

Autouse fixture below guarantees this file never reaches the real network —
it always monkeypatches ai_core._http_generate.
"""
import json

import httpx
import pytest

import ai_core as ai
import app as app_mod
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


def _mock_answer(monkeypatch, kind, **fields):
    payload = {"kind": kind, "confidence": 0.9, "reason": "because"}
    payload.update(fields)
    monkeypatch.setattr(ai, "_http_generate", lambda *a, **kw: {
        "text": json.dumps(payload), "parsed": payload,
        "tokens_in": 5, "tokens_out": 5, "latency_ms": 40, "model": "gemini-test"})


def _last_interaction(conn):
    return conn.execute(
        "SELECT feature, outcome, confidence FROM ai_interaction "
        "ORDER BY id DESC LIMIT 1").fetchone()


FAKE_STATS = {"responses": {"d30": 42, "ytd": 100, "quarter": 60, "all": 500},
              "people_rated": {"d30": 7, "ytd": 20, "quarter": 12, "all": 90},
              "satisfaction": {"d30": 88, "ytd": 91, "quarter": 90, "all": 92},
              "activities": {"d30": 3, "ytd": 15, "quarter": 8, "all": 60}}


# ---- mode="router" never offers answer/help (defense in depth) ---------------

def test_mode_router_ignores_answer_kind(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch, "router")
        conn.commit(); conn.close()
        _mock_answer(monkeypatch, "answer", answer_slot="responses_30d", confidence=0.95)
        r = admin.post("/api/ai/route", data={"q": "how many responses this month"})
        assert r.json() == {"kind": "fallback"}
        conn = st.connect(db_path)
        feature, outcome, _ = _last_interaction(conn)
        assert feature == "nl_router" and outcome == "rejected_validation"
    finally:
        _reset(conn); conn.close()


def test_mode_router_ignores_help_kind(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch, "router")
        conn.commit(); conn.close()
        _mock_answer(monkeypatch, "help", help_key="monitor", confidence=0.95)
        r = admin.post("/api/ai/route", data={"q": "how do I track a training"})
        assert r.json() == {"kind": "fallback"}
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()


# ---- answers mode: slot allow-list + server-templated rendering --------------

def test_answer_valid_slot_renders_from_mocked_aggregates(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch, "answers")
        conn.commit(); conn.close()
        _mock_answer(monkeypatch, "answer", answer_slot="responses_30d", confidence=0.9)
        monkeypatch.setattr(app_mod, "home_stats", lambda conn: FAKE_STATS)
        r = admin.post("/api/ai/route", data={"q": "how many responses in the last 30 days"})
        body = r.json()
        assert body["kind"] == "answer"
        assert "42" in body["text"]
        conn = st.connect(db_path)
        feature, outcome, confidence = _last_interaction(conn)
        assert feature == "nl_answer" and outcome == "ok" and confidence == 0.9
    finally:
        _reset(conn); conn.close()


def test_answer_no_data_slot_renders_fallback_sentence(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch, "answers")
        conn.commit(); conn.close()
        _mock_answer(monkeypatch, "answer", answer_slot="satisfaction_30d", confidence=0.9)
        empty_stats = {**FAKE_STATS, "satisfaction": {"d30": None, "ytd": None,
                                                       "quarter": None, "all": None}}
        monkeypatch.setattr(app_mod, "home_stats", lambda conn: empty_stats)
        r = admin.post("/api/ai/route", data={"q": "what's our satisfaction"})
        assert r.json()["text"] == "There isn't enough data yet to show satisfaction for the last 30 days."
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()


def test_answer_unknown_slot_falls_back(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch, "answers")
        conn.commit(); conn.close()
        _mock_answer(monkeypatch, "answer", answer_slot="nonexistent_slot", confidence=0.9)
        r = admin.post("/api/ai/route", data={"q": "anything"})
        assert r.json() == {"kind": "fallback"}
        conn = st.connect(db_path)
        assert _last_interaction(conn)[1] == "rejected_validation"
    finally:
        _reset(conn); conn.close()


def test_answer_low_confidence_falls_back(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch, "answers")
        conn.commit(); conn.close()
        _mock_answer(monkeypatch, "answer", answer_slot="responses_30d", confidence=0.2)
        r = admin.post("/api/ai/route", data={"q": "anything"})
        assert r.json() == {"kind": "fallback"}
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()


def test_answer_feature_flag_off_falls_back(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch, "answers")
        st.set_setting(conn, "ai_feature_nl_answer", "0")
        conn.commit(); conn.close()
        _mock_answer(monkeypatch, "answer", answer_slot="responses_30d", confidence=0.9)
        r = admin.post("/api/ai/route", data={"q": "anything"})
        assert r.json() == {"kind": "fallback"}
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()


# ---- answers mode: help-key allow-list + role filtering -----------------------

def test_help_valid_key_renders_tour_content(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch, "answers")
        conn.commit(); conn.close()
        _mock_answer(monkeypatch, "help", help_key="monitor", confidence=0.9)
        r = admin.post("/api/ai/route", data={"q": "how do I track who answered"})
        body = r.json()
        assert body["kind"] == "help"
        assert body["url"].startswith("/monitor")
        assert body["text"]
        conn = st.connect(db_path)
        assert _last_interaction(conn)[0] == "nl_help"
    finally:
        _reset(conn); conn.close()


def test_help_key_outside_viewer_role_falls_back(viewer, db_path, monkeypatch):
    """A viewer's help catalog never contains 'monitor' (cap=manage_event) — a
    mocked model steering them there is caught the same way an out-of-role
    destination is in Phase 1's injection test."""
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch, "answers")
        conn.commit(); conn.close()
        _mock_answer(monkeypatch, "help", help_key="monitor", confidence=0.9)
        r = viewer.post("/api/ai/route", data={"q": "how do I track who answered"})
        assert r.json() == {"kind": "fallback"}
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()


def test_help_unknown_key_falls_back(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch, "answers")
        conn.commit(); conn.close()
        _mock_answer(monkeypatch, "help", help_key="nonexistent", confidence=0.9)
        r = admin.post("/api/ai/route", data={"q": "anything"})
        assert r.json() == {"kind": "fallback"}
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()


def test_help_feature_flag_off_falls_back(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch, "answers")
        st.set_setting(conn, "ai_feature_nl_help", "0")
        conn.commit(); conn.close()
        _mock_answer(monkeypatch, "help", help_key="monitor", confidence=0.9)
        r = admin.post("/api/ai/route", data={"q": "anything"})
        assert r.json() == {"kind": "fallback"}
    finally:
        conn = st.connect(db_path); _reset(conn); conn.close()


# ---- Phase 1 navigation still works unchanged in answers mode -----------------

def test_navigate_kind_still_works_in_answers_mode(admin, db_path, monkeypatch):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _configure(conn, monkeypatch, "answers")
        conn.commit(); conn.close()
        _mock_answer(monkeypatch, "navigate", destination="pulse", confidence=0.9)
        r = admin.post("/api/ai/route", data={"q": "how are we doing"})
        body = r.json()
        assert body["kind"] == "navigate" and body["destination"] == "pulse"
        conn = st.connect(db_path)
        assert _last_interaction(conn)[0] == "nl_router"
    finally:
        _reset(conn); conn.close()
