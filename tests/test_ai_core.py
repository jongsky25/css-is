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
import ratelimit as rl
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
    ai.reset_groq_cooldown()

    def _boom(*a, **kw):
        raise AssertionError("a real httpx.post reached the network in an AI test — mock it")
    monkeypatch.setattr(httpx, "post", _boom)
    yield
    ai.reset_cooldown()
    ai.reset_groq_cooldown()


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


# ---- thinking-budget guard: Gemini 2.5+/3.x spend "thinking" tokens from the
# same maxOutputTokens budget as the answer, so our small structured calls were
# starved and came back as truncated/empty JSON (worked on Groq, which has no
# thinking). _http_generate must pin thinking to its floor and, on Gemini 3,
# widen the token budget so the JSON answer isn't cut off. ------------------

def test_thinking_config_by_model_family():
    assert ai._thinking_config("gemini-3.5-flash") == {"thinkingLevel": "minimal"}
    assert ai._thinking_config("gemini-3-pro") == {"thinkingLevel": "low"}
    assert ai._thinking_config("gemini-2.5-flash") == {"thinkingBudget": 0}
    assert ai._thinking_config("gemini-2.0-flash") == {"thinkingBudget": 0}
    assert ai._thinking_config("some-other-model") is None


def test_gemini3_call_pins_thinking_and_widens_token_budget(monkeypatch):
    monkeypatch.setenv("CSS_GEMINI_MODEL", "gemini-3.5-flash")
    seen = {}

    def fake_post(url, *, json, headers, timeout):
        seen["gc"] = json["generationConfig"]
        return _FakeResp(200, payload={"candidates": [{"content": {"parts": [{"text": '{"a": 1}'}]}}]})
    monkeypatch.setattr(httpx, "post", fake_post)

    ai._http_generate("hi", response_schema={"type": "object"}, max_output_tokens=256)
    gc = seen["gc"]
    assert gc["thinkingConfig"] == {"thinkingLevel": "minimal"}
    # answer size (256) preserved, plus headroom for the minimal reasoning.
    assert gc["maxOutputTokens"] == 256 + ai.THINKING_HEADROOM_TOKENS


def test_gemini25_call_disables_thinking_without_widening_budget(monkeypatch):
    monkeypatch.setenv("CSS_GEMINI_MODEL", "gemini-2.5-flash")
    seen = {}

    def fake_post(url, *, json, headers, timeout):
        seen["gc"] = json["generationConfig"]
        return _FakeResp(200, payload={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})
    monkeypatch.setattr(httpx, "post", fake_post)

    ai._http_generate("hi", max_output_tokens=256)
    gc = seen["gc"]
    assert gc["thinkingConfig"] == {"thinkingBudget": 0}
    # thinking is off on 2.x, so no headroom needed — budget stays as asked.
    assert gc["maxOutputTokens"] == 256


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


# ---- env var hygiene: a pasted secret carrying a stray newline must never
# reach httpx as a raw, unhandled crash (real incident: CSS_GEMINI_MODEL set
# via a hosting platform's secrets UI with a trailing "\n" made the request
# URL itself invalid, and httpx.InvalidURL isn't a TimeoutException/
# TransportError, so it escaped ask()'s AIError contract as a bare 500). ----

def test_model_env_var_trailing_newline_is_stripped(monkeypatch):
    monkeypatch.setenv("CSS_GEMINI_MODEL", "gemini-2.5-flash\n")
    assert ai.ai_model() == "gemini-2.5-flash"


def test_api_key_env_var_whitespace_is_stripped(monkeypatch):
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "  a-real-key  \n")
    assert ai.ai_configured() is True

    def fake_post(url, *, json, headers, timeout):
        assert headers["x-goog-api-key"] == "a-real-key"
        return _FakeResp(200, payload={"candidates": [{"content": {"parts": [{"text": "ok"}]}}]})
    monkeypatch.setattr(httpx, "post", fake_post)
    result = ai._http_generate("hi")
    assert result["text"] == "ok"


def test_whitespace_only_model_env_var_falls_back_to_default(monkeypatch):
    monkeypatch.setenv("CSS_GEMINI_MODEL", "   ")
    assert ai.ai_model() == ai.GEMINI_MODEL_DEFAULT


def test_invalid_url_from_bad_model_raises_ai_bad_response_not_a_crash(monkeypatch):
    """Belt-and-suspenders: even if a malformed CSS_GEMINI_MODEL somehow still
    reaches httpx (stripping is the primary fix), the InvalidURL it raises
    must come back as an AIError like every other failure, never bubble up
    raw."""
    def fake_post(*a, **kw):
        raise httpx.InvalidURL("Invalid non-printable ASCII character in URL")
    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(ai.AIBadResponse):
        ai._http_generate("hi")


def test_groq_invalid_url_raises_ai_bad_response_not_a_crash(monkeypatch):
    def fake_post(*a, **kw):
        raise httpx.InvalidURL("Invalid non-printable ASCII character in URL")
    monkeypatch.setattr(httpx, "post", fake_post)

    with pytest.raises(ai.AIBadResponse):
        ai._http_generate_groq("hi")


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
        st.set_setting(conn, "ai_cap_messages", "10")
        st.set_setting(conn, "ai_daily_cap", "10")

        def fake_http_generate(prompt, **kw):
            return {"text": "call 09171234567 back", "parsed": None,
                    "tokens_in": 1, "tokens_out": 1, "latency_ms": 5, "model": "gemini-test"}
        monkeypatch.setattr(ai, "_http_generate", fake_http_generate)

        result, interaction_id = ai.ask(conn, {"id": 1, "role": "admin"}, "messages",
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


# ---- Groq fallback (docs/AI_FALLBACK_PLAN.md) ----------------------------------

def test_ask_budget_exceeded_falls_back_to_groq_success(db_path, monkeypatch):
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("CSS_GROQ_API_KEY", "groq-key")
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        st.set_setting(conn, "ai_mode", "router")
        st.set_setting(conn, "ai_cap_verbatim", "0")   # already exhausted
        st.set_setting(conn, "ai_fallback_enabled", "1")

        def fake_groq(prompt, **kw):
            return {"text": "groq says hi", "parsed": None, "tokens_in": 1, "tokens_out": 1,
                    "latency_ms": 5, "model": "groq-test"}
        monkeypatch.setattr(ai, "_http_generate_groq", fake_groq)

        result, interaction_id = ai.ask(conn, {"id": 1, "role": "admin"}, "verbatim", "hi")
        assert result["text"] == "groq says hi"
        row = conn.execute("SELECT outcome, provider FROM ai_interaction WHERE id=?",
                           (interaction_id,)).fetchone()
        assert row[0] == "ok"
        assert row[1] == "groq"
    finally:
        _reset_ai(conn); conn.close()


def test_ask_budget_exceeded_no_groq_key_is_unchanged(db_path, monkeypatch):
    """Backward-compat regression: with no CSS_GROQ_API_KEY, behavior is
    byte-for-byte today's — Groq is never even attempted."""
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("CSS_GROQ_API_KEY", raising=False)
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        st.set_setting(conn, "ai_mode", "router")
        st.set_setting(conn, "ai_cap_verbatim", "0")
        st.set_setting(conn, "ai_fallback_enabled", "1")
        called = []
        monkeypatch.setattr(ai, "_http_generate_groq", lambda *a, **kw: called.append(1))

        with pytest.raises(ai.AIBudgetExceeded):
            ai.ask(conn, {"id": 1, "role": "admin"}, "verbatim", "hi")
        assert not called
        row = conn.execute("SELECT outcome, provider FROM ai_interaction ORDER BY id DESC LIMIT 1").fetchone()
        assert row[0] == "fallback_budget"
        assert row[1] == "gemini"
    finally:
        _reset_ai(conn); conn.close()


def test_ask_budget_exceeded_fallback_disabled_is_unchanged(db_path, monkeypatch):
    """Backward-compat regression: ai_fallback_enabled=0 (the shipped default)
    means Groq is never attempted even with a key configured."""
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("CSS_GROQ_API_KEY", "groq-key")
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        st.set_setting(conn, "ai_mode", "router")
        st.set_setting(conn, "ai_cap_verbatim", "0")
        st.set_setting(conn, "ai_fallback_enabled", "0")
        called = []
        monkeypatch.setattr(ai, "_http_generate_groq", lambda *a, **kw: called.append(1))

        with pytest.raises(ai.AIBudgetExceeded):
            ai.ask(conn, {"id": 1, "role": "admin"}, "verbatim", "hi")
        assert not called
    finally:
        _reset_ai(conn); conn.close()


def test_ask_gemini_429_falls_back_to_groq_keeps_gemini_cooldown(db_path, monkeypatch):
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("CSS_GROQ_API_KEY", "groq-key")
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        st.set_setting(conn, "ai_mode", "router")
        st.set_setting(conn, "ai_fallback_enabled", "1")

        def gemini_boom(*a, **kw):
            ai._set_cooldown()
            raise ai.AIUnavailable("Gemini rate limit (429) — cooling down")
        monkeypatch.setattr(ai, "_http_generate", gemini_boom)

        def fake_groq(prompt, **kw):
            return {"text": "groq ok", "parsed": None, "tokens_in": 1, "tokens_out": 1,
                    "latency_ms": 5, "model": "groq-test"}
        monkeypatch.setattr(ai, "_http_generate_groq", fake_groq)

        result, interaction_id = ai.ask(conn, {"id": 1, "role": "admin"}, "verbatim", "hi")
        assert result["text"] == "groq ok"
        # A successful Groq call doesn't erase the fact Gemini is cooling down.
        assert ai.cooldown_remaining() > 0
        row = conn.execute("SELECT outcome, provider FROM ai_interaction WHERE id=?",
                           (interaction_id,)).fetchone()
        assert row[0] == "ok" and row[1] == "groq"
    finally:
        _reset_ai(conn); conn.close()


def test_ask_gemini_429_groq_also_429s_folds_error(db_path, monkeypatch):
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("CSS_GROQ_API_KEY", "groq-key")
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        st.set_setting(conn, "ai_mode", "router")
        st.set_setting(conn, "ai_fallback_enabled", "1")

        def gemini_boom(*a, **kw):
            ai._set_cooldown()
            raise ai.AIUnavailable("Gemini rate limit (429) — cooling down")
        monkeypatch.setattr(ai, "_http_generate", gemini_boom)
        # Groq's own real _http_generate_groq runs here, hitting the mocked
        # httpx.post — proves Groq's 429 path sets its own cooldown too.
        monkeypatch.setattr(httpx, "post", lambda *a, **kw: _FakeResp(429, text="groq rate limited"))

        with pytest.raises(ai.AIUnavailable):
            ai.ask(conn, {"id": 1, "role": "admin"}, "messages", "hi")

        assert ai.cooldown_remaining() > 0
        assert ai.groq_cooldown_remaining() > 0
        row = conn.execute(
            "SELECT outcome, error, provider FROM ai_interaction ORDER BY id DESC LIMIT 1").fetchone()
        assert row[0] == "fallback_error"
        assert "groq fallback failed" in row[1]
        assert row[2] == "gemini"
    finally:
        _reset_ai(conn); conn.close()


def test_ask_gemini_timeout_never_attempts_groq(db_path, monkeypatch):
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("CSS_GROQ_API_KEY", "groq-key")
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        st.set_setting(conn, "ai_mode", "router")
        st.set_setting(conn, "ai_fallback_enabled", "1")

        def boom(*a, **kw):
            raise ai.AITimeout("simulated timeout")
        monkeypatch.setattr(ai, "_http_generate", boom)
        called = []
        monkeypatch.setattr(ai, "_http_generate_groq", lambda *a, **kw: called.append(1))

        with pytest.raises(ai.AITimeout):
            ai.ask(conn, {"id": 1, "role": "admin"}, "verbatim", "hi")
        assert not called
    finally:
        _reset_ai(conn); conn.close()


def test_ask_gemini_bad_response_never_attempts_groq(db_path, monkeypatch):
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("CSS_GROQ_API_KEY", "groq-key")
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        st.set_setting(conn, "ai_mode", "router")
        st.set_setting(conn, "ai_fallback_enabled", "1")

        def boom(*a, **kw):
            raise ai.AIBadResponse("model output did not match the response schema")
        monkeypatch.setattr(ai, "_http_generate", boom)
        called = []
        monkeypatch.setattr(ai, "_http_generate_groq", lambda *a, **kw: called.append(1))

        with pytest.raises(ai.AIBadResponse):
            ai.ask(conn, {"id": 1, "role": "admin"}, "verbatim", "hi")
        assert not called
    finally:
        _reset_ai(conn); conn.close()


def test_ask_harmonize_never_uses_groq_fallback(db_path, monkeypatch):
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("CSS_GROQ_API_KEY", "groq-key")
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        st.set_setting(conn, "ai_mode", "router")
        st.set_setting(conn, "ai_feature_harmonize", "1")
        st.set_setting(conn, "ai_cap_harmonize", "0")   # already exhausted
        st.set_setting(conn, "ai_fallback_enabled", "1")
        called = []
        monkeypatch.setattr(ai, "_http_generate_groq", lambda *a, **kw: called.append(1))

        with pytest.raises(ai.AIBudgetExceeded):
            ai.ask(conn, {"id": 1, "role": "admin"}, "harmonize", "hi")
        assert not called
    finally:
        _reset_ai(conn); conn.close()


def test_ask_groq_ratelimit_exhausted_skips_fallback(db_path, monkeypatch):
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("CSS_GROQ_API_KEY", "groq-key")
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        st.set_setting(conn, "ai_mode", "router")
        st.set_setting(conn, "ai_cap_verbatim", "0")   # already exhausted
        st.set_setting(conn, "ai_fallback_enabled", "1")
        # Deny only the ai_groq bucket; the earlier "ai" burst check must still pass.
        monkeypatch.setattr(rl, "allow", lambda bucket, key: bucket != "ai_groq")
        called = []
        monkeypatch.setattr(ai, "_http_generate_groq", lambda *a, **kw: called.append(1))

        with pytest.raises(ai.AIBudgetExceeded):
            ai.ask(conn, {"id": 1, "role": "admin"}, "verbatim", "hi")
        assert not called
    finally:
        _reset_ai(conn); conn.close()


# ---- Groq as sole provider when Gemini isn't configured (post-v2.19 addendum,
# docs/AI_FALLBACK_PLAN.md) --------------------------------------------------

def test_ai_available_true_when_gemini_configured_regardless_of_groq(db_path, monkeypatch):
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("CSS_GROQ_API_KEY", raising=False)
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        assert ai.ai_available(conn) is True
    finally:
        _reset_ai(conn); conn.close()


def test_ai_available_groq_standalone_requires_key_and_opt_in(db_path, monkeypatch):
    monkeypatch.delenv("CSS_GEMINI_API_KEY", raising=False)
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        assert ai.ai_available(conn) is False   # neither key nor opt-in

        monkeypatch.setenv("CSS_GROQ_API_KEY", "groq-key")
        assert ai.ai_available(conn) is False   # key but no admin opt-in

        st.set_setting(conn, "ai_fallback_enabled", "1")
        assert ai.ai_available(conn) is True    # key + opt-in, no Gemini needed
    finally:
        _reset_ai(conn); conn.close()


def test_ai_available_harmonize_excluded_even_with_groq_ready(db_path, monkeypatch):
    monkeypatch.delenv("CSS_GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("CSS_GROQ_API_KEY", "groq-key")
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        st.set_setting(conn, "ai_fallback_enabled", "1")
        assert ai.ai_available(conn) is True
        assert ai.ai_available(conn, "harmonize") is False
        assert ai.ai_available(conn, "verbatim") is True
    finally:
        _reset_ai(conn); conn.close()


def test_ask_groq_standalone_success_when_gemini_unconfigured(db_path, monkeypatch):
    monkeypatch.delenv("CSS_GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("CSS_GROQ_API_KEY", "groq-key")
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        st.set_setting(conn, "ai_mode", "router")
        st.set_setting(conn, "ai_fallback_enabled", "1")
        st.set_setting(conn, "ai_cap_verbatim", "10")

        gemini_called = []
        monkeypatch.setattr(ai, "_http_generate", lambda *a, **kw: gemini_called.append(1))
        monkeypatch.setattr(ai, "_http_generate_groq", lambda *a, **kw: {
            "text": "groq answer", "parsed": None, "tokens_in": 1, "tokens_out": 1,
            "latency_ms": 5, "model": "groq-test"})

        result, interaction_id = ai.ask(conn, {"id": 1, "role": "admin"}, "verbatim", "hi")
        assert result["text"] == "groq answer"
        assert not gemini_called   # Gemini was never even attempted

        day = tz.today_local().isoformat()
        assert conn.execute("SELECT calls FROM ai_budget WHERE day=? AND feature=?",
                            (day, "verbatim")).fetchone()[0] == 1
        row = conn.execute("SELECT outcome, provider FROM ai_interaction WHERE id=?",
                           (interaction_id,)).fetchone()
        assert row[0] == "ok" and row[1] == "groq"
    finally:
        _reset_ai(conn); conn.close()


def test_ask_groq_standalone_not_offered_without_fallback_enabled(db_path, monkeypatch):
    monkeypatch.delenv("CSS_GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("CSS_GROQ_API_KEY", "groq-key")
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        st.set_setting(conn, "ai_mode", "router")   # ai_fallback_enabled left at its default (off)
        groq_called = []
        monkeypatch.setattr(ai, "_http_generate_groq", lambda *a, **kw: groq_called.append(1))

        with pytest.raises(ai.AIUnavailable):
            ai.ask(conn, {"id": 1, "role": "admin"}, "verbatim", "hi")
        assert not groq_called
        day = tz.today_local().isoformat()
        assert conn.execute("SELECT calls FROM ai_budget WHERE day=? AND feature=?",
                            (day, "verbatim")).fetchone() is None
        outcome = conn.execute(
            "SELECT outcome FROM ai_interaction ORDER BY id DESC LIMIT 1").fetchone()[0]
        assert outcome == "no_config"
    finally:
        _reset_ai(conn); conn.close()


def test_ask_groq_standalone_harmonize_still_excluded(db_path, monkeypatch):
    monkeypatch.delenv("CSS_GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("CSS_GROQ_API_KEY", "groq-key")
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        st.set_setting(conn, "ai_mode", "assistant")
        st.set_setting(conn, "ai_fallback_enabled", "1")
        st.set_setting(conn, "ai_feature_harmonize", "1")   # even if the per-feature flag is on
        groq_called = []
        monkeypatch.setattr(ai, "_http_generate_groq", lambda *a, **kw: groq_called.append(1))

        with pytest.raises(ai.AIUnavailable):
            ai.ask(conn, {"id": 1, "role": "admin"}, "harmonize", "hi")
        assert not groq_called
        outcome = conn.execute(
            "SELECT outcome FROM ai_interaction ORDER BY id DESC LIMIT 1").fetchone()[0]
        assert outcome == "no_config"
    finally:
        _reset_ai(conn); conn.close()


def test_ask_groq_standalone_mode_off_still_blocks_everything(db_path, monkeypatch):
    """mode=off remains a hard stop for every provider — it's an admin
    decision that AI shouldn't run at all, not something specific to
    Gemini being unreachable."""
    monkeypatch.delenv("CSS_GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("CSS_GROQ_API_KEY", "groq-key")
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        st.set_setting(conn, "ai_mode", "off")
        st.set_setting(conn, "ai_fallback_enabled", "1")
        with pytest.raises(ai.AIUnavailable):
            ai.ask(conn, {"id": 1, "role": "admin"}, "verbatim", "hi")
        outcome = conn.execute(
            "SELECT outcome FROM ai_interaction ORDER BY id DESC LIMIT 1").fetchone()[0]
        assert outcome == "no_config"
    finally:
        _reset_ai(conn); conn.close()


def test_ask_groq_standalone_budget_exceeded_raises_and_logs(db_path, monkeypatch):
    monkeypatch.delenv("CSS_GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("CSS_GROQ_API_KEY", "groq-key")
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        st.set_setting(conn, "ai_mode", "router")
        st.set_setting(conn, "ai_fallback_enabled", "1")
        st.set_setting(conn, "ai_cap_verbatim", "0")   # already exhausted
        groq_called = []
        monkeypatch.setattr(ai, "_http_generate_groq", lambda *a, **kw: groq_called.append(1))

        with pytest.raises(ai.AIBudgetExceeded):
            ai.ask(conn, {"id": 1, "role": "admin"}, "verbatim", "hi")
        assert not groq_called
        outcome = conn.execute(
            "SELECT outcome FROM ai_interaction ORDER BY id DESC LIMIT 1").fetchone()[0]
        assert outcome == "fallback_budget"
    finally:
        _reset_ai(conn); conn.close()


def test_ask_groq_standalone_ratelimit_exhausted_raises_unavailable(db_path, monkeypatch):
    monkeypatch.delenv("CSS_GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("CSS_GROQ_API_KEY", "groq-key")
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        st.set_setting(conn, "ai_mode", "router")
        st.set_setting(conn, "ai_fallback_enabled", "1")
        st.set_setting(conn, "ai_cap_messages", "10")
        monkeypatch.setattr(rl, "allow", lambda bucket, key: bucket != "ai_groq")
        groq_called = []
        monkeypatch.setattr(ai, "_http_generate_groq", lambda *a, **kw: groq_called.append(1))

        with pytest.raises(ai.AIUnavailable):
            ai.ask(conn, {"id": 1, "role": "admin"}, "messages", "hi")
        assert not groq_called
        row = conn.execute(
            "SELECT outcome, error FROM ai_interaction ORDER BY id DESC LIMIT 1").fetchone()
        assert row[0] == "fallback_error"
        assert "rate limit" in row[1]
    finally:
        _reset_ai(conn); conn.close()


def test_ask_groq_standalone_error_propagates_and_logs(db_path, monkeypatch):
    monkeypatch.delenv("CSS_GEMINI_API_KEY", raising=False)
    monkeypatch.setenv("CSS_GROQ_API_KEY", "groq-key")
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        st.set_setting(conn, "ai_mode", "router")
        st.set_setting(conn, "ai_fallback_enabled", "1")
        st.set_setting(conn, "ai_cap_messages", "10")

        def boom(*a, **kw):
            raise ai.AIBadResponse("Groq returned 503 after retry")
        monkeypatch.setattr(ai, "_http_generate_groq", boom)

        with pytest.raises(ai.AIBadResponse):
            ai.ask(conn, {"id": 1, "role": "admin"}, "messages", "hi")
        row = conn.execute(
            "SELECT outcome, error FROM ai_interaction ORDER BY id DESC LIMIT 1").fetchone()
        assert row[0] == "fallback_error"
        assert "503" in row[1]
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


# ---- ask_async / test_connection_async: non-blocking wrappers ---------------
# These run the blocking HTTP call in a worker thread so an `async def` handler
# never freezes the event loop (a frozen loop stops uvicorn accepting new
# connections, so the fronting proxy answers every other request with an edge
# 5xx — the recurring "500" the AI features triggered).

def test_ask_async_offloads_to_worker_thread_and_logs_ok(db_path, monkeypatch):
    import asyncio
    import threading
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        st.set_setting(conn, "ai_mode", "router")
        st.set_setting(conn, "ai_cap_verbatim", "10")
        st.set_setting(conn, "ai_daily_cap", "10")

        seen = {}

        def fake_http_generate(prompt, **kw):
            seen["thread"] = threading.current_thread().name
            return {"text": "answer", "parsed": None, "tokens_in": 1,
                    "tokens_out": 1, "latency_ms": 5, "model": "gemini-test"}
        monkeypatch.setattr(ai, "_http_generate", fake_http_generate)

        result, interaction_id = asyncio.run(
            ai.ask_async(conn, {"id": 1, "role": "admin"}, "verbatim", "hi"))

        assert result["text"] == "answer"
        # the blocking call ran OFF the main (event-loop) thread
        assert seen["thread"] != threading.main_thread().name
        # the row the worker thread's own connection committed is visible here
        row = conn.execute("SELECT outcome FROM ai_interaction WHERE id=?",
                           (interaction_id,)).fetchone()
        assert row[0] == "ok"
    finally:
        _reset_ai(conn); conn.close()


def test_ask_async_propagates_aierror(db_path, monkeypatch):
    import asyncio
    monkeypatch.setenv("CSS_GEMINI_API_KEY", "test-key")
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        st.set_setting(conn, "ai_mode", "router")

        def boom(prompt, **kw):
            raise ai.AITimeout("nope")
        monkeypatch.setattr(ai, "_http_generate", boom)

        with pytest.raises(ai.AIError):
            asyncio.run(ai.ask_async(conn, {"id": 1, "role": "admin"}, "verbatim", "hi"))
    finally:
        _reset_ai(conn); conn.close()


def test_ask_async_unconfigured_raises_no_config(db_path, monkeypatch):
    import asyncio
    monkeypatch.delenv("CSS_GEMINI_API_KEY", raising=False)
    conn = st.connect(db_path); st.init_db(conn); _reset_ai(conn)
    try:
        st.set_setting(conn, "ai_mode", "router")
        with pytest.raises(ai.AIUnavailable):
            asyncio.run(ai.ask_async(conn, {"id": 1, "role": "admin"}, "verbatim", "hi"))
    finally:
        _reset_ai(conn); conn.close()
