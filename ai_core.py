"""
ai_core.py — CSS-IS free-tier AI integration (Google Gemini).
================================================================
docs/AI_INTEGRATION_PLAN.md Phase 0. The one module that ever talks to
Gemini: config, budget, the HTTP call, the error taxonomy, interaction
logging. Every feature built on top of this is a thin caller obeying one
contract:

    try AI -> on any AIError -> deterministic fallback (the feature's
    current behavior) -> never a user-facing error.

Callers only ever catch `AIError` (its subclasses distinguish *why*, for
logging — never for changing what the user sees). The single entry point is
`ask()`: it gates on config/mode/feature, rate-limits, spends the DB-backed
daily budget, makes the call, and logs the outcome (success or failure)
to `ai_interaction` — every call is diagnosable from `/admin/ai`, including
the ones that never reached Gemini.

Model output is never trusted with side effects: callers validate
destinations/params/slots/action ids against their own server-side
allow-lists. This module's job stops at "here is what the model said."

Configure with:
    CSS_GEMINI_API_KEY   (required to enable any AI feature)
    CSS_GEMINI_MODEL     (default gemini-2.0-flash)
    CSS_AI_TIMEOUT       (default 8.0 seconds, total request timeout)
    CSS_RL_AI            (ratelimit.py burst bucket override, "max/window")
"""
from __future__ import annotations

import json
import os
import re
import time

import httpx

import ratelimit as rl
import storage as st
import tzutil as tz

GEMINI_MODEL_DEFAULT = "gemini-2.0-flash"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"

# off < router < answers < assistant — each mode is a superset of the last,
# so `mode_at_least(conn, "answers")` is true for both answers and assistant.
AI_MODES = ("off", "router", "answers", "assistant")
_MODE_RANK = {m: i for i, m in enumerate(AI_MODES)}

# Every feature ai_core.ask() has ever been asked to gate/log for (the
# ai_interaction.feature vocabulary). Per-feature caps default here so a
# handful of busy landing-bar router calls can't starve the batch features.
FEATURE_DEFAULTS = {
    "nl_router": 80,
    "nl_answer": 80,
    "nl_help": 40,
    "ux_analysis": 5,
    "verbatim": 30,
    "report_draft": 20,
    "feedback_triage": 20,
    "messages": 20,
    "harmonize": 20,
    "test": 5,   # the /admin/ai "Test connection" egress smoke test
}
FEATURES = tuple(FEATURE_DEFAULTS.keys())

# Every feature defaults ENABLED ("1") once mode allows it, except the ones
# listed here. "harmonize" (docs/AI_INTEGRATION_PLAN.md Phase 8) sends
# resource_person names — professional-context personal data — to Google, so
# it ships opt-in: an admin must flip it on at /admin/ai even after raising
# the mode.
FEATURE_ENABLED_DEFAULT = {
    "harmonize": "0",
}

DAILY_CAP_DEFAULT = 150

OUTCOMES = ("ok", "fallback_budget", "fallback_timeout", "fallback_error",
            "rejected_validation", "no_config")

MASK_CAP = 4000


class AIError(Exception):
    """Base for every AI failure a caller catches to trigger its fallback."""


class AIUnavailable(AIError):
    """Not configured, mode/feature gated off, rate-limited, or cooling down
    after a recent 429."""


class AIBudgetExceeded(AIError):
    """The daily global or per-feature call budget has already been spent."""


class AITimeout(AIError):
    """The request timed out, including after the one permitted retry."""


class AIBadResponse(AIError):
    """A non-2xx response (after retry), or a 2xx body that didn't parse as
    the expected text/JSON."""


# ---------------------------------------------------------------------
# Config / mode / feature gates
# ---------------------------------------------------------------------

def ai_configured():
    return bool(os.environ.get("CSS_GEMINI_API_KEY"))


def ai_model():
    return os.environ.get("CSS_GEMINI_MODEL", GEMINI_MODEL_DEFAULT)


def ai_mode(conn):
    mode = st.get_setting(conn, "ai_mode", "off")
    return mode if mode in AI_MODES else "off"


def mode_at_least(conn, floor):
    return _MODE_RANK.get(ai_mode(conn), 0) >= _MODE_RANK[floor]


def feature_enabled(conn, feature):
    default = FEATURE_ENABLED_DEFAULT.get(feature, "1")
    return st.get_setting(conn, f"ai_feature_{feature}", default) != "0"


# ---------------------------------------------------------------------
# 429 cooldown — process-global, in-memory (mirrors ratelimit.py's scope: an
# abuse/backoff guard, not the source of truth for anything durable).
# ---------------------------------------------------------------------

_COOLDOWN_SECONDS = 60
_COOLDOWN_UNTIL = [0.0]


def _in_cooldown(now=None):
    now = time.time() if now is None else now
    return now < _COOLDOWN_UNTIL[0]


def _set_cooldown(now=None):
    now = time.time() if now is None else now
    _COOLDOWN_UNTIL[0] = now + _COOLDOWN_SECONDS


def cooldown_remaining():
    """Seconds left in an active 429 cooldown, 0 if none — for the /admin/ai
    status card."""
    return max(0, int(_COOLDOWN_UNTIL[0] - time.time()))


def reset_cooldown():
    """Test hook."""
    _COOLDOWN_UNTIL[0] = 0.0


# ---------------------------------------------------------------------
# Budget — DB-backed daily call counts, so the cap survives a restart and
# needs no scheduler (it's simply keyed by local calendar date).
# ---------------------------------------------------------------------

def budget_check_and_consume(conn, feature):
    """Atomically check + increment today's call count for `feature`. Raises
    AIBudgetExceeded (without incrementing anything) if either the
    per-feature or the global daily cap would be exceeded."""
    day = tz.today_local().isoformat()
    global_cap = int(st.get_setting(conn, "ai_daily_cap", str(DAILY_CAP_DEFAULT)))
    feature_cap = int(st.get_setting(
        conn, f"ai_cap_{feature}", str(FEATURE_DEFAULTS.get(feature, 20))))
    conn.execute("BEGIN IMMEDIATE")
    try:
        row = conn.execute(
            "SELECT calls FROM ai_budget WHERE day=? AND feature=?", (day, feature)).fetchone()
        feature_calls = row[0] if row else 0
        global_calls = conn.execute(
            "SELECT COALESCE(SUM(calls),0) FROM ai_budget WHERE day=?", (day,)).fetchone()[0]
        if feature_calls >= feature_cap:
            conn.rollback()
            raise AIBudgetExceeded(f"'{feature}' has reached its daily cap ({feature_cap}).")
        if global_calls >= global_cap:
            conn.rollback()
            raise AIBudgetExceeded(f"the global daily AI cap ({global_cap}) has been reached.")
        conn.execute(
            "INSERT INTO ai_budget(day, feature, calls) VALUES (?,?,1) "
            "ON CONFLICT(day, feature) DO UPDATE SET calls = calls + 1",
            (day, feature))
        conn.commit()
    except AIBudgetExceeded:
        raise
    except Exception:
        conn.rollback()
        raise


# ---------------------------------------------------------------------
# Masked logging — the same never-store-raw discipline as ui_telemetry's
# sanitize_text, extended with email masking (prompts/queries are free text,
# unlike telemetry's element labels).
# ---------------------------------------------------------------------

_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_DIGIT_RUN_RE = re.compile(r"\d{3,}")


def mask_for_log(text):
    """Mask emails and digit-runs (ids/phone numbers/amounts) in `text`,
    cap length. Returns None for empty input. Applied to every
    prompt/response before it reaches the ai_interaction table."""
    if not text:
        return None
    clean = _EMAIL_RE.sub("[email]", str(text))
    clean = _DIGIT_RUN_RE.sub("###", clean)
    return clean if len(clean) <= MASK_CAP else clean[:MASK_CAP] + "…"


# ---------------------------------------------------------------------
# The HTTP call — the ONLY function AI tests ever mock (never the network).
# ---------------------------------------------------------------------

def _http_generate(prompt, *, system=None, response_schema=None, temperature=0.2,
                    max_output_tokens=1024, timeout=8.0):
    """One Gemini `generateContent` call. Connect timeout is fixed at 3s; total
    timeout is `timeout` (default 8s). Retries once on a 5xx or a timeout,
    never on 429 (a 429 instead sets a 60s cooldown and raises immediately).

    Returns {"text", "parsed", "tokens_in", "tokens_out", "latency_ms", "model"}.
    `parsed` is the JSON-decoded text when `response_schema` was supplied,
    else None. Raises AIUnavailable (cooldown active) / AITimeout / AIBadResponse.
    """
    if _in_cooldown():
        raise AIUnavailable("cooling down after a recent Gemini 429")

    model = ai_model()
    url = f"{GEMINI_API_BASE}/models/{model}:generateContent"
    generation_config = {"temperature": temperature, "maxOutputTokens": max_output_tokens}
    if response_schema is not None:
        generation_config["responseMimeType"] = "application/json"
        generation_config["responseSchema"] = response_schema
    body = {"contents": [{"role": "user", "parts": [{"text": prompt}]}],
            "generationConfig": generation_config}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    headers = {"x-goog-api-key": os.environ.get("CSS_GEMINI_API_KEY", ""),
               "Content-Type": "application/json"}
    http_timeout = httpx.Timeout(timeout, connect=3.0)

    start = time.monotonic()
    resp = None
    for attempt in (1, 2):
        try:
            resp = httpx.post(url, json=body, headers=headers, timeout=http_timeout)
        except (httpx.TimeoutException, httpx.TransportError) as e:
            if attempt == 2:
                raise AITimeout("Gemini request timed out") from e
            continue
        if resp.status_code == 429:
            _set_cooldown()
            raise AIUnavailable("Gemini rate limit (429) — cooling down")
        if resp.status_code >= 500 and attempt == 1:
            continue
        break
    latency_ms = int((time.monotonic() - start) * 1000)

    if resp is None:
        raise AITimeout("Gemini request timed out")
    if resp.status_code >= 500:
        raise AIBadResponse(f"Gemini returned {resp.status_code} after retry")
    if resp.status_code != 200:
        raise AIBadResponse(f"Gemini returned {resp.status_code}: {resp.text[:300]}")
    try:
        data = resp.json()
    except ValueError as e:
        raise AIBadResponse("Gemini response was not valid JSON") from e

    candidates = data.get("candidates") or []
    text = ""
    if candidates:
        parts = (candidates[0].get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts)
    parsed = None
    if response_schema is not None:
        if not text:
            raise AIBadResponse("model returned no text for a schema-constrained call")
        try:
            parsed = json.loads(text)
        except ValueError as e:
            raise AIBadResponse("model output did not match the response schema") from e
    usage = data.get("usageMetadata") or {}
    return {"text": text, "parsed": parsed,
            "tokens_in": usage.get("promptTokenCount"),
            "tokens_out": usage.get("candidatesTokenCount"),
            "latency_ms": latency_ms, "model": model}


# ---------------------------------------------------------------------
# Interaction logging + the two public entry points.
# ---------------------------------------------------------------------

def _log_interaction(conn, *, user, feature, mode, outcome, result=None, error=None,
                      destination=None, confidence=None, prompt=None, log_prompts=True):
    user_id = user.get("id") if user else None
    role = user.get("role") if user else None
    return st.create_ai_interaction(
        conn, user_id=user_id, role=role, feature=feature, mode=mode,
        model=(result or {}).get("model") or ai_model(),
        prompt_masked=mask_for_log(prompt) if (log_prompts and prompt) else None,
        response_masked=mask_for_log((result or {}).get("text")) if (log_prompts and result) else None,
        outcome=outcome, destination=destination, confidence=confidence,
        latency_ms=(result or {}).get("latency_ms"),
        tokens_in=(result or {}).get("tokens_in"),
        tokens_out=(result or {}).get("tokens_out"),
        error=error)


def ask(conn, user, feature, prompt, *, ip=None, system=None, response_schema=None,
        temperature=0.2, max_output_tokens=1024, timeout=8.0):
    """The single entry point every AI feature calls.

    Gates in order: configured + mode != off + feature flag -> burst rate
    limit -> DB-backed daily budget -> the HTTP call. Every outcome (success
    or any failure) is logged to ai_interaction — budget is never consumed
    for a `no_config` or budget-exceeded refusal, since the call never
    reached (or wasn't allowed to reach) Gemini.

    Returns (result, interaction_id) on success. Raises AIError on any
    failure — callers catch AIError and fall back to their existing
    behavior; this function itself never raises anything else.
    """
    mode = ai_mode(conn)
    log_prompts = st.get_setting(conn, "ai_log_prompts", "masked") != "off"

    if not ai_configured() or mode == "off" or not feature_enabled(conn, feature):
        _log_interaction(conn, user=user, feature=feature, mode=mode, outcome="no_config",
                          error="AI is not configured, mode is off, or this feature is disabled",
                          prompt=prompt, log_prompts=log_prompts)
        raise AIUnavailable("AI is not configured, mode is off, or this feature is disabled")

    if not rl.allow("ai", ip or "unknown"):
        _log_interaction(conn, user=user, feature=feature, mode=mode, outcome="fallback_error",
                          error="AI burst rate limit exceeded", prompt=prompt, log_prompts=log_prompts)
        raise AIUnavailable("AI request rate limit exceeded")

    try:
        budget_check_and_consume(conn, feature)
    except AIBudgetExceeded as e:
        _log_interaction(conn, user=user, feature=feature, mode=mode, outcome="fallback_budget",
                          error=str(e), prompt=prompt, log_prompts=log_prompts)
        raise

    try:
        result = _http_generate(prompt, system=system, response_schema=response_schema,
                                 temperature=temperature, max_output_tokens=max_output_tokens,
                                 timeout=timeout)
    except AITimeout as e:
        _log_interaction(conn, user=user, feature=feature, mode=mode, outcome="fallback_timeout",
                          error=str(e), prompt=prompt, log_prompts=log_prompts)
        raise
    except AIError as e:
        _log_interaction(conn, user=user, feature=feature, mode=mode, outcome="fallback_error",
                          error=str(e), prompt=prompt, log_prompts=log_prompts)
        raise

    interaction_id = _log_interaction(conn, user=user, feature=feature, mode=mode, outcome="ok",
                                      result=result, prompt=prompt, log_prompts=log_prompts)
    return result, interaction_id


def test_connection(conn, user=None):
    """The /admin/ai "Test connection" egress smoke test: one tiny real
    Gemini call. Deliberately bypasses the mode/feature gates — `ai_mode`
    defaults to "off" and no feature ships enabled until later phases, but
    this button must still prove connectivity/config before any of them
    ship. Still budget- and rate-limited, and logged, like every other call.
    """
    mode = ai_mode(conn)
    if not ai_configured():
        _log_interaction(conn, user=user, feature="test", mode=mode, outcome="no_config",
                          error="CSS_GEMINI_API_KEY is not set")
        raise AIUnavailable("CSS_GEMINI_API_KEY is not set")

    if not rl.allow("ai", "admin-test"):
        _log_interaction(conn, user=user, feature="test", mode=mode, outcome="fallback_error",
                          error="AI burst rate limit exceeded")
        raise AIUnavailable("AI request rate limit exceeded")

    try:
        budget_check_and_consume(conn, "test")
    except AIBudgetExceeded as e:
        _log_interaction(conn, user=user, feature="test", mode=mode, outcome="fallback_budget",
                          error=str(e))
        raise

    try:
        result = _http_generate("Reply with the single word: OK.",
                                max_output_tokens=16, timeout=8.0)
    except AITimeout as e:
        _log_interaction(conn, user=user, feature="test", mode=mode, outcome="fallback_timeout",
                          error=str(e))
        raise
    except AIError as e:
        _log_interaction(conn, user=user, feature="test", mode=mode, outcome="fallback_error",
                          error=str(e))
        raise

    _log_interaction(conn, user=user, feature="test", mode=mode, outcome="ok", result=result)
    return result
