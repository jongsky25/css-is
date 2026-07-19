# Groq fallback provider — build plan (handover)

**Status:** planned, not started. This document is the build spec — hand it to the
implementing agent/developer as-is.
**Owner:** avincentpatrick
**Depends on:** `docs/AI_INTEGRATION_PLAN.md` (Phases 0-10, all merged as of
`APP_VERSION` 2.13). Read that doc first — this one only adds a fallback path
on top of the choke point it built (`ai_core.ask()`); it does not change or
re-litigate anything already decided there. Gemini stays the primary,
free-tier provider; Groq only fills in when Gemini's quota is exhausted.

**Decisions already made (do not re-litigate):**
Groq (not OpenAI/Anthropic/OpenRouter) as the fallback provider ·
fallback triggers **only** on Gemini quota/rate-limit exhaustion
(`AIBudgetExceeded`, or the 429-cooldown `AIUnavailable`) — never on
timeouts or malformed responses · fallback is **admin opt-in**
(`ai_fallback_enabled`, default off), not silently enabled by the presence
of an API key · the `harmonize` feature is hard-excluded from fallback
regardless of the global toggle (it already sends personal names to Google
under its own opt-in default-off flag — see rationale below) · everything
stays inside `ai_core.py`; no caller in `app.py` changes, since every caller
only ever catches `ai.AIError` and never observes which provider answered.

**Build discipline:** same as the parent plan — one PR, one `APP_VERSION`
bump, a layman `CHANGELOG` entry, full test suite green, and the acceptance
checks below passed before merge.

**Addendum (post-v2.19):** §2 originally said the pre-existing `no_config`
gate (Gemini unconfigured/mode-off/feature-off) "must never reach Groq."
That line described "Gemini not configured" and "AI is off" as the same
kind of gate; they aren't. `ai_mode=off` and per-feature flags remain a hard
stop for every provider — an admin decision that AI shouldn't run at all.
"Gemini isn't configured" is not that: after this addendum, `ai_available()`
lets Groq stand in as the *sole* provider when `CSS_GEMINI_API_KEY` is unset
but `CSS_GROQ_API_KEY` + `ai_fallback_enabled` are, subject to the same
`harmonize` exclusion as the quota-exhaustion fallback. The 500/503
incidents in v2.16/v2.18/v2.19 were audited before this change shipped: both
of the two that were app-code bugs (the event-loop-blocking synchronous
`httpx` call, and the whitespace-tainted-env-var `InvalidURL` crash) were
already fixed generically (`asyncio.to_thread` via `ask_async()`, and the
`_env()` stripping helper) in code paths Groq already shared with Gemini, so
this addendum doesn't reintroduce either. The v2.18 edge/ELB 503s were
unrelated to provider choice.

---

## 0. Why

`ai_core.ask()` (`ai_core.py:322-372`) is the one place every AI feature in
CSS-IS calls through. When Gemini's daily budget cap is hit or it 429s into
its 60s cooldown, every caller already falls back to its own deterministic,
non-AI behavior — the app never breaks, but users simply stop getting AI
help until the cap resets or the cooldown clears. This plan adds a second,
free-tier provider (Groq) that `ask()` tries automatically in exactly those
two situations, so AI features keep answering through a quota bump instead
of going quiet, while still preserving the "never a user-facing AI error"
contract the parent plan established.

## 1. Alternatives considered (why Groq, why this scope)

- **OpenAI or Anthropic instead of Groq.** Both are more capable and
  plausibly more reliable, but both are metered/paid — using either as the
  "quota ran out, spend money instead" fallback quietly turns a $0-cost
  project into a billed one the moment Gemini's free tier gets busy,
  contradicting the parent plan's explicit "free tier" decision
  (`docs/AI_INTEGRATION_PLAN.md:6`). Rejected for v1. The new provider call
  is isolated behind one function (`_http_generate_groq`) invoked from one
  helper (`_try_groq_fallback`), so swapping in OpenAI/Anthropic later, or
  chaining Groq → a paid provider as a second-level fallback, is a small,
  additive change, not a rewrite.
- **OpenRouter instead of Groq.** Would also work (it aggregates many
  providers behind one API), but its free-tier models carry their own —
  often stricter, e.g. ~20 req/day — limits on top of per-provider ones,
  plus an extra proxy hop. Groq's direct free tier is more generous and
  lower-latency, which matters more here since it backs synchronous request
  handlers with 3-8s timeout budgets. Rejected for v1; same swappability
  note applies.
- **Fall back on every `AIError`, not just quota.** Simpler to implement
  (one `except AIError` instead of splitting `AIBudgetExceeded`/cooldown-
  `AIUnavailable` from `AITimeout`/`AIBadResponse`) and more resilient.
  Rejected: a timeout or malformed response is Gemini having a bad moment,
  not "quota reached" — retrying those against a second provider is a
  different behavior change (e.g. a malformed-JSON failure could just as
  easily malform against Groq) that needs its own scoping and testing, not
  bundled into a quota fallback. Widening the `except` in `ask()` later is a
  one-line change if this scope proves too narrow in practice.
- **Enable fallback automatically whenever `CSS_GROQ_API_KEY` is set**
  (mirroring `ai_configured()`). Simpler — no new setting, no admin UI
  change — but it means setting an env var silently starts sending the same
  prompts to a *second* third-party vendor with no in-app record that this
  was a deliberate choice. Rejected in favor of an explicit
  `ai_fallback_enabled` admin toggle (default off), consistent with how
  every other AI behavior change in this app is admin-gated (`ai_mode`,
  per-feature flags, `harmonize`'s own opt-in). If this extra ceremony
  proves unwanted, dropping the setting check in `_try_groq_fallback` is a
  one-line simplification.
- **Let `harmonize` participate in fallback like every other feature.**
  Simpler, but `harmonize` ships opt-in/default-off specifically because it
  sends resource-person names (PII) to Google (`ai_core.py:70-76`); silently
  doubling that exposure to a second vendor the moment an admin flips the
  *general* fallback toggle would undermine that feature's own privacy
  design. Kept as a hard-coded exclusion in `_try_groq_fallback` — cheap,
  and consistent with how the codebase already special-cases this feature.
- **Skip JSON mode for Groq, return plain text only.** Simpler
  `_http_generate_groq`, but most of the 9 `ai.ask()` call sites pass
  `response_schema` and depend on `result["parsed"]` being populated — text-
  only would make the fallback silently useless for most features. Rejected;
  Groq's `response_format: {"type":"json_object"}` plus a schema-shape
  instruction folded into the system prompt reconstructs the same contract
  `_http_generate` already provides via Gemini's native `responseSchema`.

## 2. Architecture — where the fallback hooks in

No new choke point: `ask()` stays the single entry point, and the fallback
only fires from the two branches that mean "Gemini's quota is exhausted":

- The `except AIBudgetExceeded` block around `budget_check_and_consume`
  (currently `ai_core.py:352-355`).
- The case inside the `_http_generate` try block (`357-368`) where Gemini
  raises `AIUnavailable` specifically — not `AITimeout`, not the generic
  `AIBadResponse` case, which continue straight to the deterministic
  fallback exactly as today.

The pre-existing `no_config`/mode-off and burst-rate-limit `AIUnavailable`
raises (`339-348`) happen *before* Gemini is even attempted and are
deliberately left untouched — those mean AI is off or the server is
throttling abuse, not "Gemini's quota is exhausted," so they must never
reach Groq.

**Contract preserved:** on Groq success, `ask()` returns normally — the
caller never sees an error, exactly like a normal Gemini success, just with
`provider="groq"` in the logged interaction. On Groq failure (not
configured, disabled for this feature/globally, itself rate-limited, or
itself erroring), `ask()` logs the *original* Gemini outcome as today (with
the Groq failure folded into `error` for diagnosability) and re-raises the
original `AIError`, so the caller's deterministic fallback still runs.
**With no `CSS_GROQ_API_KEY` set, or `ai_fallback_enabled=0` (the shipped
default), behavior is byte-for-byte identical to today.** That equivalence
is the acceptance check for this phase, same spirit as Phase 0's "with
`ai_mode=off`, the app is byte-for-byte today's behavior" check in the
parent plan.

## 3. Build spec

### `ai_core.py`

New config, mirroring the existing Gemini config exactly (`ai_core.py:24-27,
112-117`):
- `CSS_GROQ_API_KEY` (optional), `CSS_GROQ_MODEL` (default
  `llama-3.3-70b-versatile` — **confirm the current model name/availability
  in the Groq console before shipping**, model offerings change over time).
- `groq_configured()`, `ai_groq_model()`.
- `fallback_enabled(conn)` → `app_setting` `ai_fallback_enabled` (default
  `"0"`), same `get_setting`/`set_setting` pattern as every other tunable
  (`storage.py:686-705`).

New cooldown state, mirroring `_COOLDOWN_UNTIL`/`_in_cooldown`/
`_set_cooldown`/`cooldown_remaining`/`reset_cooldown` (`ai_core.py:139-161`)
but **separate** from Gemini's, so a Groq 429 doesn't get confused with
Gemini's and doesn't hammer Groq on repeat quota hits:
`_GROQ_COOLDOWN_UNTIL`, `_groq_in_cooldown`, `_set_groq_cooldown`,
`groq_cooldown_remaining()`, `reset_groq_cooldown()` (test hook).

`_http_generate_groq(prompt, *, system=None, response_schema=None,
temperature=0.2, max_output_tokens=1024, timeout=8.0)` — new function,
mirrors `_http_generate`'s contract exactly (same raised errors, same
`{text, parsed, tokens_in, tokens_out, latency_ms, model}` return shape).
Calls Groq's OpenAI-compatible `POST
https://api.groq.com/openai/v1/chat/completions` via `httpx.post` (no SDK,
same house convention as Gemini — see `docs/AI_INTEGRATION_PLAN.md:49`).
Auth via `Authorization: Bearer <CSS_GROQ_API_KEY>`. Retries once on
5xx/timeout, never on 429 (429 → `_set_groq_cooldown()` + `AIUnavailable`),
identical policy to `_http_generate` (`ai_core.py:256-268`). When
`response_schema` is given: set `response_format: {"type": "json_object"}`
and append `"Respond with ONLY a JSON object matching this shape: {schema}"`
to the system prompt; parse failures raise `AIBadResponse`, same as
Gemini's existing schema-mismatch handling.

```python
def _http_generate_groq(prompt, *, system=None, response_schema=None,
                         temperature=0.2, max_output_tokens=1024, timeout=8.0):
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
    headers = {"Authorization": f"Bearer {os.environ.get('CSS_GROQ_API_KEY', '')}",
               "Content-Type": "application/json"}
    # Same two-attempt retry loop / timeout / status-code handling as
    # _http_generate (ai_core.py:252-276), against
    # f"{GROQ_API_BASE}/chat/completions" (GROQ_API_BASE =
    # "https://api.groq.com/openai/v1"), but call _set_groq_cooldown() on 429
    # instead of _set_cooldown(). Response parsing:
    #   text = data["choices"][0]["message"]["content"]
    #   parsed = json.loads(text) if response_schema is not None else None  (AIBadResponse on failure)
    #   usage = data.get("usage") or {}
    #   tokens_in, tokens_out = usage.get("prompt_tokens"), usage.get("completion_tokens")
    return {"text": text, "parsed": parsed, "tokens_in": tokens_in,
            "tokens_out": tokens_out, "latency_ms": latency_ms, "model": model}
```

`_try_groq_fallback(conn, *, feature, ip, prompt, system, response_schema,
temperature, max_output_tokens, timeout)` — new helper. Returns a result
dict if Groq is applicable *and* succeeds. Returns `None` *silently* if
Groq isn't applicable (excluded feature, disabled, not configured, rate-
limited). If Groq *was* applicable but itself raised `AIError`, that error
propagates instead of being swallowed — `ask()` decides how to fold it into
the log line, so an admin reading `/admin/ai` sees both "Gemini: budget
exceeded" and "Groq: also 429'd" on one row instead of losing the second
failure:

```python
def _try_groq_fallback(conn, *, feature, ip, prompt, system, response_schema,
                        temperature, max_output_tokens, timeout):
    if feature == "harmonize" or not fallback_enabled(conn) or not groq_configured():
        return None
    if not rl.allow("ai_groq", ip or "unknown"):
        return None
    return _http_generate_groq(prompt, system=system, response_schema=response_schema,
                                temperature=temperature, max_output_tokens=max_output_tokens,
                                timeout=timeout)   # AIError, if raised, propagates to ask()
```

`_log_interaction()` (`306-319`): add a `provider="gemini"` default kwarg,
threaded through to `st.create_ai_interaction(..., provider=provider)`.

`ask()` (`322-372`) changes — only the two `except` blocks described in §2
gain a fallback attempt; gates, rate limiting, and budget consumption are
untouched:

```python
def _fold_groq_error(base_msg, groq_exc):
    return base_msg + (f"; groq fallback failed: {groq_exc}" if groq_exc else "")

# ... inside ask(), replacing the `except AIBudgetExceeded` block:
except AIBudgetExceeded as e:
    fb, groq_exc = None, None
    try:
        fb = _try_groq_fallback(conn, feature=feature, ip=ip, prompt=prompt, system=system,
                                 response_schema=response_schema, temperature=temperature,
                                 max_output_tokens=max_output_tokens, timeout=timeout)
    except AIError as ge:
        groq_exc = ge
    if fb is not None:
        interaction_id = _log_interaction(conn, user=user, feature=feature, mode=mode,
                                           outcome="ok", result=fb, prompt=prompt,
                                           log_prompts=log_prompts, provider="groq")
        return fb, interaction_id
    _log_interaction(conn, user=user, feature=feature, mode=mode, outcome="fallback_budget",
                      error=_fold_groq_error(str(e), groq_exc), prompt=prompt,
                      log_prompts=log_prompts)
    raise

# ... and replacing the generic `except AIError` around _http_generate with:
except AIUnavailable as e:               # split out — AITimeout/AIBadResponse below are unchanged
    fb, groq_exc = None, None
    try:
        fb = _try_groq_fallback(conn, feature=feature, ip=ip, prompt=prompt, system=system,
                                 response_schema=response_schema, temperature=temperature,
                                 max_output_tokens=max_output_tokens, timeout=timeout)
    except AIError as ge:
        groq_exc = ge
    if fb is not None:
        interaction_id = _log_interaction(conn, user=user, feature=feature, mode=mode,
                                           outcome="ok", result=fb, prompt=prompt,
                                           log_prompts=log_prompts, provider="groq")
        return fb, interaction_id
    _log_interaction(conn, user=user, feature=feature, mode=mode, outcome="fallback_error",
                      error=_fold_groq_error(str(e), groq_exc), prompt=prompt,
                      log_prompts=log_prompts)
    raise
except AIError as e:                     # AIBadResponse etc. — unchanged, no Groq attempt
    _log_interaction(conn, user=user, feature=feature, mode=mode, outcome="fallback_error",
                      error=str(e), prompt=prompt, log_prompts=log_prompts)
    raise
```

Note: `AITimeout`'s existing `except` block (`361-364`) is untouched — no
Groq attempt, per the scope decision in §1.

`test_connection()` (`375-413`): add an analogous
`test_groq_connection(conn, user=None)` for the admin "Test connection"
smoke test — bypasses the `ai_fallback_enabled` gate exactly like the
Gemini one bypasses the mode/feature gates, since it must prove
egress/config before anything depends on it.

### `storage.py`

- New `ALTER TABLE ai_interaction ADD COLUMN provider TEXT` block in
  `_add_missing_columns`, following the `PRAGMA table_info` guard pattern
  used for other post-hoc columns (e.g. the `response` table check around
  line 293) — NULL for historical rows, treated as `"gemini"` when
  displayed.
- `create_ai_interaction` (`2114-2127`): add `provider=None` kwarg, extend
  the `INSERT` column list and placeholders.
- `list_ai_interactions` (`2177-2197`) + `_ai_interaction_row`
  (`2168-2174`): add `provider` to the `SELECT` column list and the
  positional row-to-dict mapping.

### `ratelimit.py`

Add `"ai_groq": (10, 60)` to the `defaults` dict (~line 26-32), mirroring
the existing `"ai": (20, 60)` bucket — an abuse throttle on Groq calls
specifically, checked via `rl.allow("ai_groq", ip)` inside
`_try_groq_fallback`, independent of Gemini's budget/rate limiting.

### `app.py`

- `admin_ai` GET (`2900-2925`): pass Groq status into the template context
  — `ai.groq_configured()`, `ai.groq_cooldown_remaining()`, the
  `ai_fallback_enabled` setting — same shape as the existing Gemini status
  values already passed here.
- `admin_ai_settings` POST (`2928-2963`): read/validate the new
  `ai_fallback_enabled` checkbox, `st.set_setting` + `_audit`, following the
  exact pattern already used for `ai_mode`/`ai_daily_cap` in this handler.
- New `POST /admin/ai/test-groq` route, mirroring `admin_ai_test`
  (`2966-2982`) but calling `ai.test_groq_connection`; same
  admin-gating/audit/redirect-with-`?err=`/`?msg=` shape.

### `templates/admin_ai.html`

- A "Groq (fallback)" status-row pill alongside the existing Key/Model/Mode
  pills (`76-82`): configured/not, model, cooldown remaining.
- An `ai_fallback_enabled` checkbox in the settings form's `settings-grid`
  (`121-146`), with an inline note that `harmonize` never uses the fallback
  regardless of this toggle.
- A small provider badge on each interaction-log row, and a "Test Groq
  connection" button next to the existing "Test connection" button
  (`101-103`).

### Docs / version

- Append a pointer in `docs/AI_INTEGRATION_PLAN.md`'s "Critical files"
  section (or a one-line note near the top) referencing this document, so
  future readers of the parent plan know a fallback exists — do not edit
  the parent plan's "do not re-litigate" list itself, since none of those
  decisions changed.
- `version.py`: bump `APP_VERSION` by one minor step, prepend a layman
  `CHANGELOG` entry (spelled-out date, plain language, one sentence per
  bullet — follow the exact style of the current top entry).
- `CHANGELOG.md`: prepend a technical entry (file-by-file bullets),
  matching the current top entry's format.
- No `requirements.txt` change (Groq reuses `httpx`, already a dependency)
  and no `deploy_hf.py` `RUNTIME_PY` change (no new module — everything
  lives inside the already-registered `ai_core.py`).
- **Deploy note (manual, not code):** `CSS_GROQ_API_KEY` needs to be added
  as an HF Space secret before the fallback can do anything in production —
  flag this in the PR description as a follow-up for whoever holds that
  secret.

## 4. Tests (`tests/test_ai_core.py`)

Use the existing `_ai_test_isolation` autouse fixture (blocks any real
`httpx.post` — a Groq test that forgets to monkeypatch `_http_generate_groq`
fails loudly, same as an un-mocked Gemini call does today) and `_reset_ai`
helper:

1. Gemini budget exceeded + `CSS_GROQ_API_KEY` set + `ai_fallback_enabled=1`
   + `ai._http_generate_groq` monkeypatched to succeed → `ask()` returns
   normally, logged `outcome="ok"`, `provider="groq"`.
2. Same, but no `CSS_GROQ_API_KEY` (or `ai_fallback_enabled=0`) → unchanged
   today's behavior: `AIBudgetExceeded` raised, `provider` logged as
   `"gemini"`/NULL — the backward-compatibility regression test.
3. Gemini 429/cooldown + Groq configured & succeeds → same ok/`provider=groq`
   path; assert Gemini's own cooldown is still set (a successful Groq call
   doesn't erase the fact Gemini is cooling down).
4. Gemini 429 + Groq configured but Groq itself 429s → original
   `AIUnavailable` re-raised, Groq's own cooldown now also set (via
   `_http_generate_groq`'s own 429 path, same mechanism as Gemini's), and
   the logged `error` mentions both failures (`_fold_groq_error`).
5. Gemini `AITimeout` / `AIBadResponse` → Groq **not** attempted even when
   configured/enabled (assert `_http_generate_groq` is never called) — locks
   in the "quota/rate-limit only" scope decision from §1.
6. `feature="harmonize"` + budget exceeded + Groq configured/enabled → Groq
   still not attempted.
7. `ai_groq` ratelimit bucket exhausted → fallback skipped, original
   Gemini error still raised and logged.

## 5. Verification recipe

1. `./run_tests.sh` — full suite green, including the new tests above.
2. Local run with both keys:
   `CSS_GEMINI_API_KEY=… CSS_GROQ_API_KEY=… uvicorn app:app --port 8000`;
   set `ai_daily_cap=0` on `/admin/ai` with `ai_fallback_enabled` on, drive
   an AI feature (e.g. the NL bar), confirm it still answers and the
   `/admin/ai` interaction log shows `provider=groq`.
3. With `ai_fallback_enabled=0` (the shipped default) and `ai_daily_cap=0`:
   confirm the feature falls back to its deterministic behavior exactly as
   it does today — zero errors shown, `provider=gemini`/NULL logged.
4. `/admin/ai` "Test Groq connection" button succeeds and logs a row.
5. `version.py` bump + CHANGELOG entry present (strict CI aborts the deploy
   otherwise, per the parent plan's convention).

## 6. Critical files

- `ai_core.py` — all new config/cooldown/`_http_generate_groq`/
  `_try_groq_fallback` code; `ask()` :322-372; `test_connection()` :375-413
- `storage.py` — `_add_missing_columns` (~:240-300 for the pattern);
  `create_ai_interaction` :2114-2127; `list_ai_interactions` +
  `_ai_interaction_row` :2168-2197
- `ratelimit.py` — `defaults` dict :26-32
- `app.py` — `admin_ai` :2900-2925; `admin_ai_settings` :2928-2963;
  `admin_ai_test` :2966-2982 (pattern for the new `/admin/ai/test-groq`)
- `templates/admin_ai.html` — status pills :76-82; settings grid :121-146;
  test-connection button :101-103
- `tests/test_ai_core.py` — `_ai_test_isolation` fixture :42-50; `_reset_ai`
  :53-57; existing 429/cooldown test :93-109 and budget-exceeded test
  :260-275 as direct templates for the new Groq tests
- `version.py` · `CHANGELOG.md` · `docs/AI_INTEGRATION_PLAN.md` (pointer only)
