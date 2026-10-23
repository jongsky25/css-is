"""
ai_core.py — Office Connect free-tier AI integration (Google Gemini, with an
optional Groq fallback).
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
    CSS_GEMINI_MODEL     (default gemini-3.5-flash)
    CSS_AI_TIMEOUT       (default 8.0 seconds, total request timeout)
    CSS_RL_AI            (ratelimit.py burst bucket override, "max/window")

docs/AI_FALLBACK_PLAN.md adds a second, free-tier provider (Groq) that
`ask()` tries automatically when Gemini's daily budget is exhausted or it
429s into its cooldown, never on a timeout or a malformed response. If
Gemini isn't configured at all, Groq can also serve as the sole provider
(see `ai_available()`) instead of every feature going straight to its
deterministic fallback. Either way it is admin opt-in (`ai_fallback_enabled`
setting, default off) and never applies to `harmonize` (which already sends
resource-person names to Google under its own opt-in flag — doubling that
exposure to a second vendor would undermine that feature's own privacy
design). Configure with:
    CSS_GROQ_API_KEY     (optional; enables Groq as fallback or sole provider)
    CSS_GROQ_MODEL       (default llama-3.3-70b-versatile)
"""
from __future__ import annotations

import asyncio
import base64
import json
import os
import re
import time

import httpx

import qa_rules
import ratelimit as rl
import storage as st
import tzutil as tz

GEMINI_MODEL_DEFAULT = "gemini-3.5-flash"
GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta"
# Gemini 2.5+/3.x "thinking" tokens are spent from the SAME maxOutputTokens
# budget as the visible answer. Our structured calls set small token limits
# sized for a compact JSON reply, so on the Gemini-3 path (where thinking can
# only be lowered, not switched off) we add this much headroom on top of the
# caller's limit to leave room for the now-minimal reasoning.
THINKING_HEADROOM_TOKENS = 1024

GROQ_MODEL_DEFAULT = "llama-3.3-70b-versatile"
GROQ_API_BASE = "https://api.groq.com/openai/v1"

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
    "nl_answer_grounded": 40,   # "maximize" engine: select server-owned facts.
                                # Costs a second model call on top of nl_router,
                                # so it gets its own (lower) cap.
    "nl_help": 40,
    "ux_analysis": 5,
    "verbatim": 30,
    "report_draft": 20,
    "feedback_triage": 20,
    "messages": 20,
    "harmonize": 20,
    "assistant_action": 15,
    "i18n_review": 20,   # tools/i18n_review.py — one-off DRAFT-translation review
    "travel_scan": 30,   # travel prepare page: read the fare off an uploaded ticket / receipt
                         # (the only feature that sends an image; Gemini only, no Groq fallback)
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

def _env(name, default=""):
    """os.environ.get, stripped. A secret pasted into a hosting platform's
    settings UI easily picks up a trailing newline/space; left unstripped,
    that lands in the request URL or headers and httpx refuses to send it
    (e.g. AttributeError-free but a hard `InvalidURL`/`LocalProtocolError`)
    — exactly the kind of failure ask()'s AIError contract is supposed to
    keep away from callers."""
    return (os.environ.get(name) or "").strip() or default


def ai_configured():
    return bool(_env("CSS_GEMINI_API_KEY"))


def ai_model():
    return _env("CSS_GEMINI_MODEL", GEMINI_MODEL_DEFAULT)


def groq_configured():
    return bool(_env("CSS_GROQ_API_KEY"))


def ai_groq_model():
    return _env("CSS_GROQ_MODEL", GROQ_MODEL_DEFAULT)


def fallback_enabled(conn):
    return st.get_setting(conn, "ai_fallback_enabled", "0") != "0"


def ai_available(conn, feature=None):
    """True if ask() could actually reach a provider for `feature`, ignoring
    the mode/feature-flag/rate/budget gates checked separately. Gemini being
    configured is always sufficient. Absent that, Groq can stand in on its
    own — same admin opt-in (`ai_fallback_enabled`) and `harmonize` exclusion
    as the Gemini-quota-exhausted fallback path, since those constraints are
    about Groq itself, not about why Gemini wasn't reached."""
    if ai_configured():
        return True
    if feature == "harmonize":
        return False
    return groq_configured() and fallback_enabled(conn)


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


# Separate cooldown state for Groq — kept apart from Gemini's above so a Groq
# 429 doesn't get confused with Gemini's, and doesn't hammer Groq on repeat
# quota hits.
_GROQ_COOLDOWN_UNTIL = [0.0]


def _groq_in_cooldown(now=None):
    now = time.time() if now is None else now
    return now < _GROQ_COOLDOWN_UNTIL[0]


def _set_groq_cooldown(now=None):
    now = time.time() if now is None else now
    _GROQ_COOLDOWN_UNTIL[0] = now + _COOLDOWN_SECONDS


def groq_cooldown_remaining():
    """Seconds left in an active Groq 429 cooldown, 0 if none — for the
    /admin/ai status card."""
    return max(0, int(_GROQ_COOLDOWN_UNTIL[0] - time.time()))


def reset_groq_cooldown():
    """Test hook."""
    _GROQ_COOLDOWN_UNTIL[0] = 0.0


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

def _thinking_config(model):
    """Gemini 2.5+ and 3.x turn "thinking" ON by default, and those thinking
    tokens are spent from the SAME maxOutputTokens budget as the visible
    answer — so a small token limit sized for a compact JSON reply gets starved
    by default ("high") thinking, and the schema-constrained call comes back
    truncated ("model output did not match the response schema") or empty.
    (Groq's Llama has no thinking, which is why the same calls worked there.)
    Pin thinking to its floor for these short structured calls. The knob and
    its floor differ by model family, and the two are mutually exclusive —
    sending both in one request is a 400.

    Returns a `thinkingConfig` dict, or None for a model with no thinking knob.
    """
    m = (model or "").lower()
    if m.startswith("gemini-3"):
        # Gemini 3 can't fully disable thinking; "minimal" is the floor and is
        # supported on Flash/Flash-Lite, "low" is the safe floor elsewhere.
        return {"thinkingLevel": "minimal" if "flash" in m else "low"}
    if m.startswith(("gemini-2.5", "gemini-2.0")):
        return {"thinkingBudget": 0}   # 0 fully disables thinking on 2.x
    return None


def _http_generate(prompt, *, system=None, response_schema=None, temperature=0.2,
                    max_output_tokens=1024, timeout=8.0, images=None):
    """One Gemini `generateContent` call. Connect timeout is fixed at 3s; total
    timeout is `timeout` (default 8s). Retries once on a 5xx or a timeout,
    never on 429 (a 429 instead sets a 60s cooldown and raises immediately).

    `images` is an optional list of (mime_type, bytes) sent inline before the prompt text
    (a photo or a PDF); only Gemini takes them.

    Returns {"text", "parsed", "tokens_in", "tokens_out", "latency_ms", "model"}.
    `parsed` is the JSON-decoded text when `response_schema` was supplied,
    else None. Raises AIUnavailable (cooldown active) / AITimeout / AIBadResponse.
    """
    if _in_cooldown():
        raise AIUnavailable("cooling down after a recent Gemini 429")

    model = ai_model()
    url = f"{GEMINI_API_BASE}/models/{model}:generateContent"
    generation_config = {"temperature": temperature, "maxOutputTokens": max_output_tokens}
    thinking = _thinking_config(model)
    if thinking is not None:
        generation_config["thinkingConfig"] = thinking
        if "thinkingLevel" in thinking:
            # Gemini 3 shares the token budget between thinking and the answer;
            # give the answer its full requested size plus room for the (now
            # minimal) reasoning, so structured JSON isn't cut off mid-object.
            generation_config["maxOutputTokens"] = max_output_tokens + THINKING_HEADROOM_TOKENS
    if response_schema is not None:
        generation_config["responseMimeType"] = "application/json"
        generation_config["responseSchema"] = response_schema
    parts = [{"inline_data": {"mime_type": mime, "data": base64.b64encode(raw).decode("ascii")}}
             for mime, raw in (images or [])]
    parts.append({"text": prompt})
    body = {"contents": [{"role": "user", "parts": parts}],
            "generationConfig": generation_config}
    if system:
        body["systemInstruction"] = {"parts": [{"text": system}]}
    headers = {"x-goog-api-key": _env("CSS_GEMINI_API_KEY"),
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
        except httpx.InvalidURL as e:
            # A malformed model name (e.g. CSS_GEMINI_MODEL carrying a stray
            # control character) fails at request-build time, before any
            # network call — retrying won't help, so fail this call the same
            # way a bad response would, instead of leaking past ask()'s
            # AIError contract as a raw 500.
            raise AIBadResponse(f"Gemini request could not be built: {e}") from e
        if resp.status_code == 429:
            # Include Google's reason in the log detail: a 429 can mean a real
            # burst limit, but also "this model has zero free-tier quota"
            # (deprecated model / unprovisioned key) — indistinguishable
            # without the body, and the admin's fix differs for each.
            _set_cooldown()
            raise AIUnavailable(
                f"Gemini rate limit (429) — cooling down: {resp.text[:300]}")
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
# Groq — the fallback provider (docs/AI_FALLBACK_PLAN.md). Only ever reached
# from ask() when Gemini's quota/rate-limit is exhausted; mirrors
# _http_generate's contract exactly (same raised errors, same return shape).
# ---------------------------------------------------------------------

def _http_generate_groq(prompt, *, system=None, response_schema=None, temperature=0.2,
                         max_output_tokens=1024, timeout=8.0):
    """One Groq chat-completion call (OpenAI-compatible endpoint). Same retry/
    cooldown contract as _http_generate, against Groq's own, separate
    cooldown state. Raises AIUnavailable (cooldown active) / AITimeout /
    AIBadResponse. Returns {"text", "parsed", "tokens_in", "tokens_out",
    "latency_ms", "model"}.
    """
    if _groq_in_cooldown():
        raise AIUnavailable("cooling down after a recent Groq 429")

    model = ai_groq_model()
    sys_text = system or ""
    if response_schema is not None:
        sys_text = (sys_text + "\n\nRespond with ONLY a JSON object matching "
                    f"this shape: {json.dumps(response_schema)}").strip()
    messages = ([{"role": "system", "content": sys_text}] if sys_text else []) + \
               [{"role": "user", "content": prompt}]
    body = {"model": model, "messages": messages, "temperature": temperature,
            "max_tokens": max_output_tokens}
    if response_schema is not None:
        body["response_format"] = {"type": "json_object"}
    headers = {"Authorization": f"Bearer {_env('CSS_GROQ_API_KEY')}",
               "Content-Type": "application/json"}
    http_timeout = httpx.Timeout(timeout, connect=3.0)
    url = f"{GROQ_API_BASE}/chat/completions"

    start = time.monotonic()
    resp = None
    for attempt in (1, 2):
        try:
            resp = httpx.post(url, json=body, headers=headers, timeout=http_timeout)
        except httpx.InvalidURL as e:
            raise AIBadResponse(f"Groq request could not be built: {e}") from e
        except (httpx.TimeoutException, httpx.TransportError) as e:
            if attempt == 2:
                raise AITimeout("Groq request timed out") from e
            continue
        if resp.status_code == 429:
            _set_groq_cooldown()
            raise AIUnavailable(
                f"Groq rate limit (429) — cooling down: {resp.text[:300]}")
        if resp.status_code >= 500 and attempt == 1:
            continue
        break
    latency_ms = int((time.monotonic() - start) * 1000)

    if resp is None:
        raise AITimeout("Groq request timed out")
    if resp.status_code >= 500:
        raise AIBadResponse(f"Groq returned {resp.status_code} after retry")
    if resp.status_code != 200:
        raise AIBadResponse(f"Groq returned {resp.status_code}: {resp.text[:300]}")
    try:
        data = resp.json()
    except ValueError as e:
        raise AIBadResponse("Groq response was not valid JSON") from e

    choices = data.get("choices") or []
    text = (choices[0].get("message") or {}).get("content", "") if choices else ""
    parsed = None
    if response_schema is not None:
        if not text:
            raise AIBadResponse("model returned no text for a schema-constrained call")
        try:
            parsed = json.loads(text)
        except ValueError as e:
            raise AIBadResponse("model output did not match the response schema") from e
    usage = data.get("usage") or {}
    return {"text": text, "parsed": parsed,
            "tokens_in": usage.get("prompt_tokens"),
            "tokens_out": usage.get("completion_tokens"),
            "latency_ms": latency_ms, "model": model}


def _try_groq_fallback(conn, *, feature, ip, prompt, system, response_schema,
                        temperature, max_output_tokens, timeout, images=None):
    """Attempt the Groq fallback for one Gemini quota/rate-limit failure.
    Returns a result dict on success. Returns None *silently* if Groq isn't
    applicable (excluded feature, disabled, not configured, rate-limited).
    If Groq *was* applicable but itself raised AIError, that error
    propagates — ask() decides how to fold it into the log line."""
    if feature == "harmonize" or not fallback_enabled(conn) or not groq_configured():
        return None
    if images:
        return None
    if not rl.allow("ai_groq", ip or "unknown"):
        return None
    return _http_generate_groq(prompt, system=system, response_schema=response_schema,
                                temperature=temperature, max_output_tokens=max_output_tokens,
                                timeout=timeout)


def _fold_groq_error(base_msg, groq_exc):
    return base_msg + (f"; groq fallback failed: {groq_exc}" if groq_exc else "")


# ---------------------------------------------------------------------
# Interaction logging + the two public entry points.
# ---------------------------------------------------------------------

def _log_interaction(conn, *, user, feature, mode, outcome, result=None, error=None,
                      destination=None, confidence=None, prompt=None, log_prompts=True,
                      provider="gemini", question=None):
    user_id = user.get("id") if user else None
    role = user.get("role") if user else None
    if feature == "report_draft":
        # Drafts retain outcome/token/timing metadata only, even when content
        # logging is enabled for other features. Rejecting provider prose must
        # not copy it (or provider error bodies) into the interaction log.
        log_prompts = False
        error = "report_draft_provider_failure" if error else None
    # The clean, normalized user question (for the learned-rules FAQ miner in
    # storage.top_questions). Only stored when prompt logging is on, since it's
    # the same user-typed content the prompt-logging toggle governs.
    question_norm = (qa_rules.normalize(question) or None) if (log_prompts and question) else None
    return st.create_ai_interaction(
        conn, user_id=user_id, role=role, feature=feature, mode=mode,
        model=(result or {}).get("model") or ai_model(),
        prompt_masked=mask_for_log(prompt) if (log_prompts and prompt) else None,
        response_masked=mask_for_log((result or {}).get("text")) if (log_prompts and result) else None,
        outcome=outcome, destination=destination, confidence=confidence,
        latency_ms=(result or {}).get("latency_ms"),
        tokens_in=(result or {}).get("tokens_in"),
        tokens_out=(result or {}).get("tokens_out"),
        error=error, provider=provider, question_norm=question_norm)


def ask(conn, user, feature, prompt, *, ip=None, system=None, response_schema=None,
        temperature=0.2, max_output_tokens=1024, timeout=8.0, question=None, images=None):
    """The single entry point every AI feature calls.

    Gates in order: configured + mode != off + feature flag -> burst rate
    limit -> DB-backed daily budget -> the HTTP call. Every outcome (success
    or any failure) is logged to ai_interaction — budget is never consumed
    for a `no_config` or budget-exceeded refusal, since the call never
    reached (or wasn't allowed to reach) a provider.

    Gemini is preferred whenever it's configured. If it isn't, but Groq is
    (and an admin has opted into `ai_fallback_enabled`, and `feature` isn't
    `harmonize`), Groq serves as the sole provider for this call instead of
    raising `no_config` — see `ai_available()`.

    Returns (result, interaction_id) on success. Raises AIError on any
    failure — callers catch AIError and fall back to their existing
    behavior; this function itself never raises anything else.

    `images` ([(mime, bytes)]) makes it a Gemini-only call: Groq's text model cannot read
    them, so neither the Groq-alone nor the quota fallback is used (the caller falls back
    to typing the amount by hand). The bytes are never logged.
    """
    mode = ai_mode(conn)
    log_prompts = st.get_setting(conn, "ai_log_prompts", "masked") != "off"

    gemini_ready = ai_configured()
    groq_only = not gemini_ready and not images and ai_available(conn, feature)

    if not (gemini_ready or groq_only) or mode == "off" or not feature_enabled(conn, feature):
        _log_interaction(conn, user=user, feature=feature, mode=mode, outcome="no_config",
                          error="AI is not configured, mode is off, or this feature is disabled",
                          prompt=prompt, log_prompts=log_prompts)
        raise AIUnavailable("AI is not configured, mode is off, or this feature is disabled")

    if not rl.allow("ai", ip or "unknown"):
        _log_interaction(conn, user=user, feature=feature, mode=mode, outcome="fallback_error",
                          error="AI burst rate limit exceeded", prompt=prompt, log_prompts=log_prompts)
        raise AIUnavailable("AI request rate limit exceeded")

    if groq_only:
        try:
            budget_check_and_consume(conn, feature)
        except AIBudgetExceeded as e:
            _log_interaction(conn, user=user, feature=feature, mode=mode, outcome="fallback_budget",
                              error=str(e), prompt=prompt, log_prompts=log_prompts)
            raise
        try:
            fb = _try_groq_fallback(conn, feature=feature, ip=ip, prompt=prompt, system=system,
                                     response_schema=response_schema, temperature=temperature,
                                     max_output_tokens=max_output_tokens, timeout=timeout)
        except AIError as e:
            _log_interaction(conn, user=user, feature=feature, mode=mode, outcome="fallback_error",
                              error=str(e), prompt=prompt, log_prompts=log_prompts)
            raise
        if fb is None:
            # ai_available() already confirmed Groq is configured/opted-in/not
            # harmonize, so the only way _try_groq_fallback still declines is
            # its own ai_groq burst-ratelimit bucket.
            err = "Groq request rate limit exceeded"
            _log_interaction(conn, user=user, feature=feature, mode=mode, outcome="fallback_error",
                              error=err, prompt=prompt, log_prompts=log_prompts)
            raise AIUnavailable(err)
        interaction_id = _log_interaction(conn, user=user, feature=feature, mode=mode,
                                           outcome="ok", result=fb, prompt=prompt,
                                           log_prompts=log_prompts, provider="groq",
                                           question=question)
        return fb, interaction_id

    try:
        budget_check_and_consume(conn, feature)
    except AIBudgetExceeded as e:
        fb, groq_exc = None, None
        try:
            fb = _try_groq_fallback(conn, feature=feature, ip=ip, prompt=prompt, system=system,
                                     response_schema=response_schema, temperature=temperature,
                                     max_output_tokens=max_output_tokens, timeout=timeout,
                                     images=images)
        except AIError as ge:
            groq_exc = ge
        if fb is not None:
            interaction_id = _log_interaction(conn, user=user, feature=feature, mode=mode,
                                               outcome="ok", result=fb, prompt=prompt,
                                               log_prompts=log_prompts, provider="groq",
                                               question=question)
            return fb, interaction_id
        _log_interaction(conn, user=user, feature=feature, mode=mode, outcome="fallback_budget",
                          error=_fold_groq_error(str(e), groq_exc), prompt=prompt,
                          log_prompts=log_prompts)
        raise

    try:
        # `images` is passed only when there are some, so a text-only call keeps the exact
        # signature every existing caller and test double of _http_generate expects.
        result = _http_generate(prompt, system=system, response_schema=response_schema,
                                 temperature=temperature, max_output_tokens=max_output_tokens,
                                 timeout=timeout, **({"images": images} if images else {}))
    except AITimeout as e:
        _log_interaction(conn, user=user, feature=feature, mode=mode, outcome="fallback_timeout",
                          error=str(e), prompt=prompt, log_prompts=log_prompts)
        raise
    except AIUnavailable as e:
        fb, groq_exc = None, None
        try:
            fb = _try_groq_fallback(conn, feature=feature, ip=ip, prompt=prompt, system=system,
                                     response_schema=response_schema, temperature=temperature,
                                     max_output_tokens=max_output_tokens, timeout=timeout,
                                     images=images)
        except AIError as ge:
            groq_exc = ge
        if fb is not None:
            interaction_id = _log_interaction(conn, user=user, feature=feature, mode=mode,
                                               outcome="ok", result=fb, prompt=prompt,
                                               log_prompts=log_prompts, provider="groq",
                                               question=question)
            return fb, interaction_id
        _log_interaction(conn, user=user, feature=feature, mode=mode, outcome="fallback_error",
                          error=_fold_groq_error(str(e), groq_exc), prompt=prompt,
                          log_prompts=log_prompts)
        raise
    except AIError as e:
        _log_interaction(conn, user=user, feature=feature, mode=mode, outcome="fallback_error",
                          error=str(e), prompt=prompt, log_prompts=log_prompts)
        raise

    interaction_id = _log_interaction(conn, user=user, feature=feature, mode=mode, outcome="ok",
                                      result=result, prompt=prompt, log_prompts=log_prompts,
                                      question=question)
    return result, interaction_id


# ---------------------------------------------------------------------
# Non-blocking wrappers for the async request handlers.
#
# ask()/test_connection() make a SYNCHRONOUS httpx call that can take up to the
# full timeout plus one retry (~16s worst case). FastAPI's `async def` handlers
# run on the single uvicorn worker's event loop — and that same loop is what
# accepts new TCP connections. So a synchronous AI call made directly from an
# async handler freezes the whole worker for the call's duration: uvicorn stops
# accepting connections and the fronting proxy/load-balancer answers every other
# in-flight request with an edge 5xx (503/500) that never reaches — and is never
# logged by — this app. That is the mechanism behind the recurring "500" the AI
# features triggered (most often via the landing-bar router, the hottest AI
# path), and no amount of AIError handling inside the app can catch it, because
# the error is emitted OUTSIDE the app.
#
# These wrappers run the blocking call in a worker thread (asyncio.to_thread) so
# the event loop stays free to accept connections. sqlite connections are bound
# to the thread that created them, so the wrapper opens its OWN short-lived
# connection inside the thread (from the caller connection's own DB path) rather
# than reusing the caller's. The returned interaction_id is a plain int the
# caller can keep using on its own connection (the row is already committed by
# the thread's connection before this returns).
# ---------------------------------------------------------------------

def _conn_db_path(conn):
    """Filesystem path of `conn`'s main database, or None for an in-memory DB
    (which can't be reopened by path in another thread)."""
    try:
        for _seq, name, file in conn.execute("PRAGMA database_list"):
            if name == "main":
                return file or None
    except Exception:        # noqa: BLE001
        pass
    return None


async def _run_off_loop(conn, fn, *args, **kwargs):
    """Run blocking `fn(conn_like, *args, **kwargs)` off the event loop, giving
    it a fresh thread-local connection. Falls back to a direct (in-thread) call
    for an in-memory DB, which has no reopenable path — that path only happens
    in tests, which already run off the request loop."""
    path = _conn_db_path(conn)
    if not path:
        return fn(conn, *args, **kwargs)

    def _run():
        c = st.connect(path)
        try:
            return fn(c, *args, **kwargs)
        finally:
            c.close()

    return await asyncio.to_thread(_run)


async def ask_async(conn, user, feature, prompt, **kwargs):
    """Non-blocking `ask()` for `async def` handlers — same contract (returns
    (result, interaction_id) or raises AIError), but the blocking HTTP call
    never freezes the event loop. See the module comment above."""
    return await _run_off_loop(conn, ask, user, feature, prompt, **kwargs)


async def test_connection_async(conn, user=None):
    """Non-blocking `test_connection()` for the /admin/ai test button."""
    return await _run_off_loop(conn, test_connection, user=user)


async def test_groq_connection_async(conn, user=None):
    """Non-blocking `test_groq_connection()` for the /admin/ai test button."""
    return await _run_off_loop(conn, test_groq_connection, user=user)


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


def test_groq_connection(conn, user=None):
    """The /admin/ai "Test Groq connection" egress smoke test: one tiny real
    Groq call. Bypasses `ai_fallback_enabled` exactly like test_connection
    bypasses the mode/feature gates — it must prove egress/config before
    anything depends on it. Still budget- and rate-limited, and logged."""
    mode = ai_mode(conn)
    if not groq_configured():
        _log_interaction(conn, user=user, feature="test", mode=mode, outcome="no_config",
                          error="CSS_GROQ_API_KEY is not set", provider="groq")
        raise AIUnavailable("CSS_GROQ_API_KEY is not set")

    if not rl.allow("ai_groq", "admin-test"):
        _log_interaction(conn, user=user, feature="test", mode=mode, outcome="fallback_error",
                          error="AI burst rate limit exceeded", provider="groq")
        raise AIUnavailable("AI request rate limit exceeded")

    try:
        budget_check_and_consume(conn, "test")
    except AIBudgetExceeded as e:
        _log_interaction(conn, user=user, feature="test", mode=mode, outcome="fallback_budget",
                          error=str(e), provider="groq")
        raise

    try:
        result = _http_generate_groq("Reply with the single word: OK.",
                                     max_output_tokens=16, timeout=8.0)
    except AITimeout as e:
        _log_interaction(conn, user=user, feature="test", mode=mode, outcome="fallback_timeout",
                          error=str(e), provider="groq")
        raise
    except AIError as e:
        _log_interaction(conn, user=user, feature="test", mode=mode, outcome="fallback_error",
                          error=str(e), provider="groq")
        raise

    _log_interaction(conn, user=user, feature="test", mode=mode, outcome="ok", result=result,
                      provider="groq")
    return result
