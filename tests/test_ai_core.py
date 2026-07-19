"""
ai_core.py — the Gemini client, budget guard and error taxonomy behind
docs/AI_INTEGRATION_PLAN.md Phase 0.

Covers: the DB-backed daily budget (per-feature cap, global cap, survives a
reconnect, atomic — a blocked call never increments the counter); the
_http_generate retry contract (one retry on 5xx/timeout, never on 429, a 429
sets a 60s cooldown); ask()'s gating order and outcome logging (unconfigured
never touches budget; every outcome — success or fallback — is logged);
mask_for_log's digit/email masking; and the ai_interaction/ai_budget
retention purge.

AI tests never touch the real network: the autouse fixture below replaces
httpx.post with something that fails loudly if a test forgets to mock it.
Tests of _http_generate's own retry logic mock httpx.post directly (that's
the function under test); tests of ask()/test_connection() instead mock
ai_core._http_generate, one layer up.
"""
from datetime import timedelta

import httpx
import pytest

import ai_core as ai
import retention as ret
import storage as st
import tzutil as tz


class _FakeResp:
    def __init__(self, status_code, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload
        self.text = text

    def json(self):
        if self._payload is None:
            raise ValueError("no json body")
        return self._payload


@pytest.fixture(autouse=True)
def _ai_test_isolation(monkeypatch):
    ai.reset_cooldown()

    def _boom(*a, **kw):
        raise AssertionError("a real httpx.post reached the network in an AI test — mock it")
    monkeypatch.setattr(httpx, "post", _boom)
    yield
    ai.reset_cooldown()


def _reset_ai(conn):
    conn.execute("DELETE FROM ai_interaction")
    conn.execute("DELETE FROM ai_budget")
    conn.execute("DELETE FROM app_setting WHERE key LIKE 'ai_%'")
    conn.commit()


# ---- mask_for_log -----------------------------------------------------------

def test_mask_for_log_masks_digits_and_emails():
    masked = ai.mask_for_log("Call 09171234567 or email jane@example.com re: client 90210")
    assert "09171234567" not in masked
    assert "jane@example.com" not in masked
    assert "90210" not in masked
    assert "[email]" in masked and "###" in masked


def test_mask_for_log_empty_is_none():
    assert ai.mask_for_log("") is None
    assert ai.mask_for_log(None) is None


def test_mask_for_log_caps_length():
    masked = ai.mask_for_log("a" * 5000)
    assert len(masked) == ai.MASK_CAP + 1
    assert masked.endswith("…")


# ---- _http_generate: retry / 429 / timeout contract -------------------------

def test_success_parses_text_schema_and_usage(monkeypatch):
    payload = {"candidates": [{"content": {"parts": [{"text": '{"a": 1}'}]}}],
               "usageMetadata": {"promptTokenCount": 5, "candidatesTokenCount": 3}}
    monkeypatch.setattr(httpx, "post", lambda *a, **kw: _FakeResp(200, payload=payload))
    result = ai._http_generate("hi", response_schema={"type": "object"})
    assert result["parsed"] == {"a": 1}
    assert result["tokens_in"] == 5 and result["tokens_out"] == 3
    assert result["model"] == ai.ai_model()


def test_429_sets_cooldown_never_retries(monkeypatch):
    calls = []

    def fake_post(*a, **kw):
        calls.append(1)
        return _FakeResp(429, text="rate limited")
    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(ai.AIUnavailable):
        ai._http_generate("hi")
    assert len(calls) == 1
    assert ai.cooldown_remaining() > 0

    # A second call short-circuits on the cooldown without touching httpx at all.
    with pytest.raises(ai.AIUnavailable):
        ai._http_generate("hi")
    assert len(calls) == 1


def test_timeout_retries_once_then_raises(monkeypatch):
    calls = []

    def fake_post(*a, **kw):
        calls.append(1)
        raise httpx.TimeoutException("boom")
    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(ai.AITimeout):
        ai._http_generate("hi")
    assert len(calls) == 2


def test_5xx_retries_once_then_bad_response(monkeypatch):
    calls = []

    def fake_post(*a, **kw):
        calls.append(1)
        return _FakeResp(503, text="server error")
    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(ai.AIBadResponse):
        ai._http_generate("hi")
    assert len(calls) == 2


def test_success_after_one_5xx_retry(monkeypatch):
    calls = []
    payload = {"candidates": [{"content": {"parts": [{"text": "ok"}]}}]}

    def fake_post(*a, **kw):
        calls.append(1)
        if len(calls) == 1:
            return _FakeResp(503, text="transient")
        return _FakeResp(200, payload=payload)
    monkeypatch.setattr(httpx, "post", fake_post)

    result = ai._http_generate("hi")
    assert result["text"] == "ok"
    assert len(calls) == 2


# ---- feature gates -------------------------------------------------------------

def test_feature_enabled_defaults_on_except_harmonize(db_path):
    """Every feature defaults enabled once mode/config allow it — except
    "harmonize" (docs/AI_INTEGRATION_PLAN.md Phase 8), which sends directory
    names to Google and so ships opt-in even with no setting written yet."""
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        assert ai.feature_enabled(conn, "harmonize") is False
        for f in ai.FEATURES:
            if f != "harmonize":
                assert ai.feature_enabled(conn, f) is True
        st.set_setting(conn, "ai_feature_harmonize", "1")
        assert ai.feature_enabled(conn, "harmonize") is True
        st.set_setting(conn, "ai_feature_harmonize", "0")
        assert ai.feature_enabled(conn, "harmonize") is False
    finally:
        _reset_ai(conn); conn.close()


# ---- budget -------------------------------------------------------------------

def test_budget_cap_one_blocks_second_call_counter_intact(db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        st.set_setting(conn, "ai_cap_verbatim", "1")
        st.set_setting(conn, "ai_daily_cap", "100")
        ai.budget_check_and_consume(conn, "verbatim")
        with pytest.raises(ai.AIBudgetExceeded):
            ai.budget_check_and_consume(conn, "verbatim")
        day = tz.today_local().isoformat()
        calls = conn.execute("SELECT calls FROM ai_budget WHERE day=? AND feature=?",
                             (day, "verbatim")).fetchone()[0]
        assert calls == 1
    finally:
        _reset_ai(conn); conn.close()


def test_budget_survives_reconnect(db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    st.set_setting(conn, "ai_cap_verbatim", "5")
    st.set_setting(conn, "ai_daily_cap", "100")
    ai.budget_check_and_consume(conn, "verbatim")
    conn.close()

    conn2 = st.connect(db_path)
    try:
        day = tz.today_local().isoformat()
        calls = conn2.execute("SELECT calls FROM ai_budget WHERE day=? AND feature=?",
                              (day, "verbatim")).fetchone()[0]
        assert calls == 1
        ai.budget_check_and_consume(conn2, "verbatim")
        calls2 = conn2.execute("SELECT calls FROM ai_budget WHERE day=? AND feature=?",
                               (day, "verbatim")).fetchone()[0]
        assert calls2 == 2
    finally:
        _reset_ai(conn2); conn2.close()


def test_budget_global_cap_blocks_independent_of_feature_cap(db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        st.set_setting(conn, "ai_cap_verbatim", "50")
        st.set_setting(conn, "ai_cap_report_draft", "50")
        st.set_setting(conn, "ai_daily_cap", "1")
        ai.budget_check_and_consume(conn, "verbatim")   # spends the whole global cap
        with pytest.raises(ai.AIBudgetExceeded):
            ai.budget_check_and_consume(conn, "report_draft")   # blocked on GLOBAL, not its own cap
    finally:
        _reset_ai(conn); conn.close()


# ---- ask(): gating order + outcome logging -------------------------------------

def test_ask_unconfigured_raises_and_consumes_no_budget(db_path, monkeypatch):
    monkeypatch.delenv("CSS_GEMINI_API_KEY", raising=False)
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        st.set_setting(conn, "ai_mode", "router")   # mode is NOT the reason this fails
        st.set_setting(conn, "ai_cap_verbatim", "10")
        with pytest.raises(ai.AIUnavailable):
            ai.ask(conn, {"id": 1, "role": "admin"}, "verbatim", "hello")
        day = tz.today_local().isoformat()
        assert conn.execute("SELECT calls FROM ai_budget WHERE day=? AND feature=?",
                            (day, "verbatim")).fetchone() is None
        outcome = conn.execute(
            "SELECT outcome FROM ai_interaction ORDER BY id DESC LIMIT 1").fetchone()[0]
        assert outcome == "no_config"
    finally:
        _reset_ai(conn); conn.close()


def test_ask_mode_off_raises_no_config(db_path, monkeypatch):
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        st.set_setting(conn, "ai_mode", "off")
        with pytest.raises(ai.AIUnavailable):
            ai.ask(conn, {"id": 1, "role": "admin"}, "verbatim", "hello")
        outcome = conn.execute(
            "SELECT outcome FROM ai_interaction ORDER BY id DESC LIMIT 1").fetchone()[0]
        assert outcome == "no_config"
    finally:
        _reset_ai(conn); conn.close()


def test_ask_budget_exceeded_never_reaches_http(db_path, monkeypatch):
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        st.set_setting(conn, "ai_mode", "router")
        st.set_setting(conn, "ai_cap_verbatim", "0")   # already exhausted
        called = []
        monkeypatch.setattr(ai, "_http_generate", lambda *a, **kw: called.append(1))
        with pytest.raises(ai.AIBudgetExceeded):
            ai.ask(conn, {"id": 1, "role": "admin"}, "verbatim", "hi")
        assert not called
        outcome = conn.execute(
            "SELECT outcome FROM ai_interaction ORDER BY id DESC LIMIT 1").fetchone()[0]
        assert outcome == "fallback_budget"
    finally:
        _reset_ai(conn); conn.close()


def test_ask_logs_fallback_timeout(db_path, monkeypatch):
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        st.set_setting(conn, "ai_mode", "router")

        def boom(*a, **kw):
            raise ai.AITimeout("simulated timeout")
        monkeypatch.setattr(ai, "_http_generate", boom)

        with pytest.raises(ai.AITimeout):
            ai.ask(conn, {"id": 1, "role": "admin"}, "verbatim", "hi")
        outcome = conn.execute(
            "SELECT outcome FROM ai_interaction ORDER BY id DESC LIMIT 1").fetchone()[0]
        assert outcome == "fallback_timeout"
    finally:
        _reset_ai(conn); conn.close()


def test_ask_success_logs_ok_with_masked_prompt_and_response(db_path, monkeypatch):
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        st.set_setting(conn, "ai_mode", "router")
        st.set_setting(conn, "ai_cap_verbatim", "10")
        st.set_setting(conn, "ai_daily_cap", "10")

        def fake_http_generate(prompt, **kw):
            return {"text": "call 09171234567 back", "parsed": None,
                    "tokens_in": 1, "tokens_out": 1, "latency_ms": 5, "model": "gemini-test"}
        monkeypatch.setattr(ai, "_http_generate", fake_http_generate)

        result, interaction_id = ai.ask(conn, {"id": 1, "role": "admin"}, "verbatim",
                                        "call 09171234567 about it")
        assert result["text"] == "call 09171234567 back"
        row = conn.execute(
            "SELECT outcome, prompt_masked, response_masked FROM ai_interaction WHERE id=?",
            (interaction_id,)).fetchone()
        assert row[0] == "ok"
        assert "09171234567" not in row[1]
        assert "09171234567" not in row[2]
    finally:
        _reset_ai(conn); conn.close()


def test_ask_respects_ai_log_prompts_off(db_path, monkeypatch):
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        st.set_setting(conn, "ai_mode", "router")
        st.set_setting(conn, "ai_log_prompts", "off")
        monkeypatch.setattr(ai, "_http_generate", lambda prompt, **kw: {
            "text": "hello", "parsed": None, "tokens_in": 1, "tokens_out": 1,
            "latency_ms": 5, "model": "gemini-test"})
        _, interaction_id = ai.ask(conn, {"id": 1, "role": "admin"}, "verbatim", "a secret prompt")
        row = conn.execute(
            "SELECT prompt_masked, response_masked FROM ai_interaction WHERE id=?",
            (interaction_id,)).fetchone()
        assert row[0] is None and row[1] is None
    finally:
        _reset_ai(conn); conn.close()


# ---- storage helpers: feedback ownership ---------------------------------------

def test_set_ai_feedback_ownership(db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        iid = st.create_ai_interaction(conn, user_id=1, role="viewer", feature="verbatim",
                                       mode="off", outcome="ok")
        assert st.set_ai_feedback(conn, iid, user_id=2, rating=1) is False
        assert st.set_ai_feedback(conn, iid, user_id=1, rating=1) is True
        assert conn.execute("SELECT rating FROM ai_interaction WHERE id=?",
                            (iid,)).fetchone()[0] == 1
        assert st.set_ai_feedback(conn, iid, user_id=2, rating=-1, is_admin=True) is True
    finally:
        _reset_ai(conn); conn.close()


# ---- retention purge -------------------------------------------------------------

def test_purge_stale_ai_log(db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        old_ts = (tz.now_local() - timedelta(days=200)).isoformat(timespec="seconds")
        recent_ts = tz.now_iso()
        conn.execute("INSERT INTO ai_interaction(created_at, feature, mode, outcome) "
                    "VALUES (?,?,?,?)", (old_ts, "verbatim", "off", "ok"))
        conn.execute("INSERT INTO ai_interaction(created_at, feature, mode, outcome) "
                    "VALUES (?,?,?,?)", (recent_ts, "verbatim", "off", "ok"))
        old_day = (tz.now_local() - timedelta(days=200)).date().isoformat()
        today = tz.today_local().isoformat()
        conn.execute("INSERT INTO ai_budget(day, feature, calls) VALUES (?,?,1)",
                    (old_day, "verbatim"))
        conn.execute("INSERT INTO ai_budget(day, feature, calls) VALUES (?,?,1)",
                    (today, "verbatim"))
        conn.commit()
    finally:
        conn.close()

    n = ret.purge_stale_ai_log(db_path=db_path, days=90)
    assert n == 1

    conn = st.connect(db_path)
    try:
        assert conn.execute("SELECT COUNT(*) FROM ai_interaction").fetchone()[0] == 1
        assert conn.execute("SELECT COUNT(*) FROM ai_budget").fetchone()[0] == 1
    finally:
        _reset_ai(conn); conn.close()
