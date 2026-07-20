# CHANGELOG — Cowork revisions (surgical)

## 2026-07-20 (v2.24 — duplicate-activity heads-up now matches across creators, not just same-login/6h)

Spot-feedback report: a real duplicate ("DOH UHC Fund for Zero Balance Billing
in LGU Hospital: POLICY ORIENTATION MEETING") was created and the /create
screen's "you already made this" warning (spot-feedback #67) never fired.

Root cause: `storage.find_recent_duplicate_event` only matched a duplicate
made by the **same** `created_by` login, created within the last **6 hours**.
That's the pattern the original spot-feedback #67 report described (one
manager accidentally double-submitting), but it misses the more common
real-world case — two different staff members independently logging the same
activity, or the same activity re-entered a day or more later. Since the check
is purely advisory (`POST /create` never calls it, and there's no DB unique
constraint), any duplicate outside that narrow window was silently allowed
through with no warning at all.

Fix: `find_recent_duplicate_event(conn, title, event_date)` now matches on
title (case/space-insensitive) + event date alone — no `created_by` filter,
no time cutoff. `GET /create/check-duplicate` updated to match (drops the
now-unused `request` param); `templates/form_create.html` copy updated from
"You already created…" to "…already exists on this date" since the earlier
activity may not be the current user's own. Still purely advisory — `/create`
itself is unchanged, so a genuine second activity that happens to share a name
still saves normally.

Verified: `tests/test_create_duplicate_warning.py` updated — added a
same-title/different-creator case (created by `admin`, found with no creator
argument at all) and a same-title/backdated-creation case (created_at forced
to year 2000, still found) in place of the old "ignores a different creator" /
"ignores outside the lookback window" tests; added an HTTP-level test where
one role creates the activity and a different role's `/create/check-duplicate`
call still reports it. `tests/test_create_duplicate_warning.py` 10/10 pass.

## 2026-07-19 (v2.23 — deploy manifest was missing `qa_rules.py` → app crashed on startup)

`ai_core.py` imports `qa_rules` at module load (the FAQ/learned-rules layer
added in v2.22), but `qa_rules.py` was never added to `deploy_hf.py`'s
`RUNTIME_PY` upload list. So the file exists in the repo and passes every local
test, yet the deployed HF Space never received it — and on start-up
`import ai_core as ai` (app.py) → `import qa_rules` (ai_core.py) raises
`ModuleNotFoundError: No module named 'qa_rules'`, which aborts the whole
uvicorn boot and takes the site down with a server error for everyone.

Fix: add `"qa_rules.py"` to `RUNTIME_PY` in `deploy_hf.py` so it ships with
every deploy. `qa_rules` only depends on the stdlib (`re`), so no further
modules were missing.

## 2026-07-19 (v2.19 — AI calls no longer block the event loop → stop the recurring edge 500)

Root-causes the recurring "error 500" that v2.18 shielded but never explained.
v2.18 correctly observed the signature — `awselb/2.0` `503` and HF proxy `500`
pages with **no** `X-CSS-App`/proxy headers, while the app replica looked
healthy — and shipped a client-side service-worker retry. But the trigger is
**in the app**, not (only) HF's edge: the AI-calling handlers are `async def`,
yet `ai.ask()` → `_http_generate()` makes a **synchronous** `httpx.post`
(connect 3s + total 8s + one retry ≈ up to ~16s). A blocking call on the event
loop of the single uvicorn worker freezes uvicorn's own connection-accept loop,
so for that window the replica accepts **no** new TCP connections and the
fronting ELB/HF proxy answers every other in-flight request with an edge 5xx —
exactly the observed 500/503. The hottest trigger is the landing-bar router
(`POST /api/ai/route`, feature `nl_router`), confirmed firing on the live Space,
so ordinary AI use intermittently 500s everyone else. This is why the v2.18
retry reduced but never removed it, and why every prior in-app `AIError` fix
couldn't: the 500 is emitted **outside** the app.

Fix: move the blocking AI network call **off** the event loop.

- **`ai_core.py`** — new `ask_async()` / `test_connection_async()` /
  `test_groq_connection_async()` run the existing (synchronous) `ask()` /
  `test_connection()` / `test_groq_connection()` in a worker thread via
  `asyncio.to_thread`, so a slow or stuck AI reply can no longer freeze the
  worker. sqlite connections are thread-bound, so the wrapper opens its **own**
  short-lived connection inside the thread (from the caller connection's DB
  path via `PRAGMA database_list`); the returned `interaction_id` is a plain int
  the caller keeps using on its own connection (the row is already committed).
  Same contract as before — returns `(result, interaction_id)` or raises
  `AIError` — so callers' `except ai.AIError` fallbacks are unchanged. An
  in-memory DB (tests only) has no reopenable path and falls back to a direct
  in-thread call.
- **`app.py`** — the 9 `ai.ask(...)` call sites (all in `async def` handlers:
  `/api/ai/route`, `/admin/feedback/{fid}/ai-suggest`,
  `/admin/ux-insights/analyze`, `/directory/cleanup/ai-suggest`,
  `/activities/{token}/messages/ai-draft`, `/reports/csm-draft`,
  `/reports/activities/{id}/ai-reanalyze`, `/ai-summary`, `/ai-mrr-draft`) now
  `await ai.ask_async(...)`; the two `/admin/ai` test buttons `await` the async
  test wrappers. No behavioural change beyond not blocking the loop.
- **`tests/test_ai_core.py`** — `ask_async` offloads to a non-main thread, logs
  `ok` on a row visible to the caller connection, propagates `AIError`, and
  raises `AIUnavailable` when unconfigured.

Same event-loop-stall class, second source: PBKDF2 sign-in hashing.

- **`auth.py`** — `hash_password_async` / `verify_password_async` run the
  deliberately-CPU-heavy PBKDF2 (`_ITERATIONS=200_000`, ~100-150ms/call) off the
  event loop via `asyncio.to_thread`. In-line, it froze the single worker for the
  whole hash — and bots hammer `/login` constantly, so each attempt was a stall
  that could flap the load-balancer health check.
- **`app.py`** — the four `async def` auth handlers (`login_submit`,
  `set_password_submit`, `reset_password_submit`, `admin_users_reset_default`)
  now `await` the off-loop hash. (`_provision_account`, reached only from the
  rare admin-invite path, is left synchronous.)
- **`tests/test_auth_async.py`** — parity of the async wrappers with the sync
  hash/verify, and that the hash runs on a worker thread, not the event loop.

Note on the underlying failure surface (from live diagnosis of the Space): the
recurring "500" is emitted by the HF edge / AWS ELB, not the app — the single
`cpu-basic` worker intermittently fails the load-balancer health check when its
event loop stalls, and the LB then answers everyone with an edge 5xx until the
target re-registers. The app is healthy and serves 200 whenever a request
reaches it. These changes remove the two biggest in-app stall sources (AI HTTP
calls and sign-in hashing); giving the single worker more headroom (a larger CPU
tier) remains the complementary infrastructure-side lever.

Operational note (separate from this code change): the live Space had
`CSS_GEMINI_API_KEY` + `CSS_GEMINI_MODEL` + `CSS_GROQ_API_KEY` set. Removing the
Gemini secret disables all AI at the config gate (`ai_configured()` is false, so
`ask()` short-circuits before any HTTP call and every feature falls back to its
deterministic behaviour) — the fastest way to stop the blocking calls
immediately, independent of a redeploy.

## 2026-07-19 (v2.18 — edge-retry shield against HF routing failures)

Since ~12:35 UTC today (immediately after a Space visibility toggle), ~40-60%
of requests to the Space's direct URL are answered by HF's infrastructure
itself — first `503` from `server: awselb/2.0`, later HF's proxy 500 page,
both with **no** Spaces-proxy headers — while the app replica stays healthy
(control probes of other Spaces through the same edge are 100% consistent, so
the poisoned route is specific to this subdomain). It survives container
restart, redeploy, and pause/resume, and it aborted two auto-deploys at the
`pull_backup` pre-deploy gate. HF-side fix is theirs to make; this ships the
app-side shield.

Key mechanism: the server now stamps `X-CSS-App: 1` on **every** response it
produces (success, 4xx, even unhandled 500s via a new `Exception` handler). A
5xx *without* that header is therefore proof the request never reached the
app — which makes an automatic retry safe for any method, POSTs included.

- **`app.py`** — `_metrics_gate` stamps `X-CSS-App: 1` on every response; new
  `@app.exception_handler(Exception)` `_unhandled_error` returns the plain 500
  WITH the marker (Starlette still re-raises, so tracebacks keep reaching the
  log) — without this, an in-app crash on a POST would look retry-safe to the
  service worker and could double-execute.
- **`static/js/sw.js`** — new `fetchRetrying(req, retryNetworkErrors)`: up to
  3 extra attempts with linear backoff on any 5xx lacking `x-css-app`.
  Wired into all four request classes: static assets (inside the
  stale-while-revalidate refresh), navigations (before the cache/offline
  fallback), all other same-origin GETs (previously not intercepted), and —
  new — non-GET writes, which are retried **only** on the provable edge-error
  case, never on network errors (the Phase-2 offline queue + submission_id
  dedup already covers those). `CACHE_VERSION` → v2.18-a.
- **`pull_backup.py`** — `_with_retry` (6 attempts, linear backoff) around
  `_get`/`_post`: edge 5xx (5xx without `X-CSS-App`) always retried; plain
  network errors retried for GETs only. The 3xx-returned-as-value contract of
  `_post(follow=False)` is preserved inside the retry wrapper.
- **`deploy_hf.py`** — `_fetch_live_login` (version pre-check + post-deploy
  verify) retries 5 times on any HTTP/URL error.
- **`tests/test_pwa.py`** — 4 new tests: marker present on 200/3xx/404; marker
  present on an unhandled-crash 500 (via a temp route + non-raising client);
  sw.js contains the retry shield and intercepts writes.

## 2026-07-19 (v2.17 — fix: default Gemini model closed to new API keys)

Follow-up to v2.14's model bump. The live site's newly created
`CSS_GEMINI_API_KEY` gets a 404 from Gemini for every call:
`"This model models/gemini-2.5-flash is no longer available to new users."`
— Google has closed `gemini-2.5-flash` to keys that didn't already use it.
Per https://ai.google.dev/gemini-api/docs/models the current stable fast
model is `gemini-3.5-flash`.

- **`ai_core.py`** — `GEMINI_MODEL_DEFAULT` is now `gemini-3.5-flash` (was
  `gemini-2.5-flash`); module docstring updated. `CSS_GEMINI_MODEL` still
  overrides.

## 2026-07-19 (v2.16 — fix: unhandled 500 from a whitespace-tainted AI env var)

Production incident: right after `CSS_GEMINI_API_KEY`/`CSS_GROQ_API_KEY` were
added as HF Space secrets, `POST /api/ai/route` (the Start-page NL search bar)
500'd. Traceback: `httpx.InvalidURL: Invalid non-printable ASCII character in
URL, '\n' at position 75`, raised from `_http_generate`'s `httpx.post(url, …)`
at `ai_core.py:311`, inside `ask()`. Root cause: `ai_model()` read
`CSS_GEMINI_MODEL` via a bare `os.environ.get(...)` and interpolated it
straight into the Gemini request URL; a trailing newline picked up when the
model name was pasted into the secret produced a malformed URL.
`httpx.InvalidURL` is a bare `Exception`, not a `TimeoutException`/
`TransportError`, so `_http_generate`'s retry loop didn't catch it — it
escaped `ask()`'s documented "every AI feature must fall back, never a
user-facing error" contract entirely.

- **`ai_core.py`** — new `_env(name, default="")` helper: strips the raw env
  value, falls back to `default` if the result is empty. `ai_configured()`,
  `ai_model()`, `groq_configured()`, `ai_groq_model()`, and the
  `x-goog-api-key`/`Authorization` header reads in `_http_generate`/
  `_http_generate_groq` all go through it now instead of a raw
  `os.environ.get`. Belt-and-suspenders: both `_http_generate` and
  `_http_generate_groq` now also catch `httpx.InvalidURL` around the
  `httpx.post` call and re-raise as `AIBadResponse` (no retry — a malformed
  URL is a config problem, not a transient one), so any future request-build
  failure degrades the same way a bad HTTP response already does instead of
  bubbling up raw.
- **`tests/test_ai_core.py`** — 6 new tests: `CSS_GEMINI_MODEL`/
  `CSS_GEMINI_API_KEY` whitespace is stripped (and actually reaches the
  request that way); a whitespace-only model value falls back to
  `GEMINI_MODEL_DEFAULT`; `httpx.InvalidURL` from either `_http_generate` or
  `_http_generate_groq` surfaces as `AIBadResponse`, not an unhandled
  exception.

## 2026-07-19 (v2.15 — Groq fallback AI provider)

`docs/AI_FALLBACK_PLAN.md` (build spec, merged in #43) implemented as-is. Adds a
second, free-tier provider (Groq) that `ai_core.ask()` tries automatically —
only on the two "Gemini's quota is exhausted" branches (`AIBudgetExceeded`, or
the 429-cooldown `AIUnavailable`), never on `AITimeout`/`AIBadResponse`.
Admin opt-in, off by default; `harmonize` is hard-excluded regardless of the
toggle. With no `CSS_GROQ_API_KEY` set, or `ai_fallback_enabled=0` (the
shipped default), behavior is byte-for-byte identical to today.

- **`ai_core.py`** — `CSS_GROQ_API_KEY`/`CSS_GROQ_MODEL` config
  (`groq_configured()`, `ai_groq_model()`), `fallback_enabled(conn)` (the
  `ai_fallback_enabled` setting), a separate Groq 429 cooldown
  (`_GROQ_COOLDOWN_UNTIL`/`_groq_in_cooldown`/`_set_groq_cooldown`/
  `groq_cooldown_remaining`/`reset_groq_cooldown`), `_http_generate_groq`
  (mirrors `_http_generate`'s retry/timeout/schema contract against Groq's
  OpenAI-compatible `chat/completions` endpoint), `_try_groq_fallback`
  (feature/setting/config/rate-limit gate), and `_fold_groq_error`. `ask()`'s
  `AIBudgetExceeded` and (newly split-out) `AIUnavailable` branches now
  attempt the fallback before re-raising; `AITimeout`/`AIBadResponse` are
  untouched. `_log_interaction`/`create_ai_interaction` gain a `provider`
  kwarg (default `"gemini"`). New `test_groq_connection()` for the admin
  smoke test.
- **`storage.py`** — `ai_interaction.provider TEXT` column (guarded ALTER in
  `_add_missing_columns`); `create_ai_interaction`, `_ai_interaction_row`,
  `list_ai_interactions` thread it through (`_ai_interaction_row` reads NULL
  as `"gemini"`).
- **`ratelimit.py`** — `"ai_groq": (10, 60)` bucket, independent of the
  existing `"ai"` bucket.
- **`app.py`** — `admin_ai` passes Groq status (`groq_configured`,
  `groq_model`, `groq_cooldown_remaining`, `fallback_enabled`) into the
  template; `admin_ai_settings` reads/saves `ai_fallback_enabled`; new
  `POST /admin/ai/test-groq` route mirroring `admin_ai_test`.
- **`templates/admin_ai.html`** — a Groq status row, an `ai_fallback_enabled`
  checkbox (with a note that `harmonize` is always excluded), a "Test Groq
  connection" button, and a provider column on the interaction log.
- **`tests/test_ai_core.py`** — 10 new tests: Groq success on budget-exceeded
  and on Gemini 429 (the latter asserting Gemini's own cooldown survives);
  two backward-compat regressions (no key / toggle off); Groq itself 429ing
  (both cooldowns end up set, both failures folded into one logged error);
  `AITimeout`/`AIBadResponse` never attempting Groq; `harmonize` never
  attempting Groq; the `ai_groq` ratelimit bucket blocking the attempt.
- **Deploy note:** `CSS_GROQ_API_KEY` still needs to be added as an HF Space
  secret before this can do anything in production.

## 2026-07-19 (v2.14 — Fix AI: default Gemini model was deprecated; log 429 bodies)

Live diagnosis (`/admin/ai` interaction log): the key was configured and mode
was `assistant`, yet the very first real call — and every call after — failed
with `Gemini rate limit (429)`. A first-call 429 is quota `limit: 0`, not a
burst limit: Google deprecated `gemini-2.0-flash` (June 1, 2026) and free-tier
quota now only covers Gemini 2.5 models, so a free-tier key calling the old
default is refused outright.

- **`ai_core.py`** — `GEMINI_MODEL_DEFAULT` is now `gemini-2.5-flash` (was
  `gemini-2.0-flash`; `CSS_GEMINI_MODEL` still overrides). The 429 branch of
  `_http_generate` now appends the first 300 chars of Google's response body to
  the `AIUnavailable` message, so the `ai_interaction` log distinguishes a real
  burst limit from "this model has zero quota" — the ambiguity that made this
  outage look like ordinary rate-limiting.
- **`docs/AI_INTEGRATION_PLAN.md`** — default-model note updated to match.

## 2026-07-19 (v2.13 — Phase 10 of the AI integration plan: Filipino translation review)

`docs/AI_INTEGRATION_PLAN.md` Phase 10, the lowest-priority, one-off phase — an
offline dev tool rather than a web feature, so there is no route/RBAC surface.

- **`tools/i18n_review.py`** (new) — CLI script (`python tools/i18n_review.py`)
  that walks every DRAFT Filipino string in `i18n.py` (`B_TEXT_FIL`, `A_TEXT_FIL`,
  `C_TEXT_FIL`, `CONSENT_TMPL_FIL`, `LIKERT5_FIL`, `OSQ4_FIL`, `REMARK_CHIPS_FIL`,
  and the `UI` chrome dict — everything except the already-official
  `ARTA_TEXT_FIL`), paired with its English source in `app.py`, and batches them
  (20/call) through `ai.ask(feature="i18n_review", response_schema=...)` asking
  for a natural, formal-register revision of each. Suggestions are validated
  against a per-batch key allow-list (a key the model wasn't asked about is
  dropped) and a placeholder-preservation check (a suggestion that drops or
  rewrites a `{subject}`/`{months}` token is rejected with a "needs manual fix"
  reason instead of being shown as usable) — same "model output is never
  trusted" discipline as every other phase. The script only prints a
  side-by-side report (optionally to `--out file.md`); it never writes back to
  `i18n.py` — the office still copies in whatever wording it wants by hand.
  Gates on the same `ai_configured()`/`ai_mode`/`feature_enabled()` checks as
  every route-based feature, with a plain-language early-exit message for each.
  Not added to `deploy_hf.py`'s `RUNTIME_PY`/`ALLOW` — it's a dev-machine-only
  tool, never shipped to the Space, same as the existing `tools/contrast_check.py`.
- **`ai_core.py`** — `"i18n_review": 20` added to `FEATURE_DEFAULTS`, which
  automatically wires it into `/admin/ai`'s per-feature cap/flag settings (that
  page iterates `ai.FEATURES`, no template change needed).
- **`version.py`** — `APP_VERSION` 2.12 → 2.13, CHANGELOG entry prepended.
- **`tests/test_i18n_review.py`** (new) — `build_review_items()` covers every
  DRAFT group with unique keys and skips `ARTA_TEXT_FIL`; `review_batch()`
  accepts a valid mocked suggestion, rejects one missing a required
  placeholder, and ignores a key it never asked about (prompt-injection
  guard); `main()`'s three early-exit gates (unconfigured, mode off, feature
  disabled); an end-to-end run with `--limit`/`--out`; and that an `AIError`
  mid-run is skipped and reported rather than crashing the script.

## 2026-07-19 (v2.06 — Phase 3 of the AI integration plan: UX Insights "Analyze now")

`docs/AI_INTEGRATION_PLAN.md` Phase 3, the lowest-risk real feature (admin-only,
zero PII — the handoff payload is already pseudonymized). Ships with
`ux_analysis` already present in `ai_core.FEATURE_DEFAULTS` (cap 5/day) since
Phase 0, so no new setting/table/`admin_ai.html` changes were needed.

- **`app.py`** — `POST /admin/ux-insights/analyze` (new, next to the existing
  `GET /admin/ux-insights/handoff`): builds the identical `uxh.build_handoff(...)`
  payload as the download route, renders it with `uxh.render_handoff_markdown`,
  and hands that Markdown to `ai.ask(feature="ux_analysis", max_output_tokens=2048,
  timeout=30.0)` with a short system prompt steering toward a concise,
  numbered improvement write-up. Any `AIError` returns `{"ok": false, "notice":
  ...}` pointing back at the existing download link — the feature never surfaces
  an error, and export never depends on AI. A successful call is audited the
  same way as the handoff download (`action="export"`). No new gating code:
  inherits `manage_users` via the existing `/admin` prefix rule.
- **`templates/ux_insights.html`** — "✨ Analyze now" button beside the
  existing download links; inline `<script>` posts to the new route and
  renders the result as an in-page card with 👍/👎 feedback chips, reusing the
  same `sendBeacon`-first pattern as `static/js/start.js`'s feedback wiring
  (posts to the existing generic `/api/ai/feedback`, no new feedback route).
- **`version.py`** — `APP_VERSION` 2.05 → 2.06, CHANGELOG entry prepended.
- **`tests/test_ux_analysis.py`** (new) — RBAC, success shape, `AIError` and
  budget-exceeded fallback (both return `ok: false` with a notice, never an
  error status), audit row, and an end-to-end leak test proving an unmasked
  digit posted through `/telemetry` never reaches the prompt handed to
  `ai_core.ask()`.

## 2026-07-19 (v2.04 — Phase 1 of the AI integration plan: NL landing page + router mode)

`docs/AI_INTEGRATION_PLAN.md` Phase 1, built on Phase 0's `ai_core.py`. Ships
with `ai_mode` still defaulting to `off` — the new page always renders and
always answers something, but the router itself is inert until an admin
opts in from `/admin/ai`.

- **`app.py`** — `ai_route_catalog(user)` (new): the NL router's
  destination allow-list, same role/cap filtering as `search_index_for` but
  keyed by `key` (what the router validates against) instead of flattened
  by section. `GET /start` (any signed-in user, no new gating — renders
  regardless of AI mode). `POST /api/ai/route`: builds the prompt from the
  catalog, calls `ai.ask(feature="nl_router", response_schema=...)`,
  then validates the model's `destination` against the catalog and its
  `confidence` against a 0.5 floor server-side before ever building a URL —
  the URL always comes from the catalog entry, never from model text; an
  unknown destination or sub-floor confidence is logged as
  `rejected_validation` (via the new `storage.update_ai_interaction_outcome`)
  and falls back. `POST /api/ai/feedback`: 👍/👎 posted via
  `sendBeacon`, rate-limited on the existing `"telemetry"` bucket (costs no
  AI budget), ownership-checked in `storage.set_ai_feedback`.
  `login_submit`: a fresh sign-in with `next=/` redirects to `/start` instead
  of the hub when AI is configured, mode ≥ router, and the admin-set
  `ai_landing_default` setting (added in Phase 0) is `start` — rollback is
  flipping either setting back.
- **`storage.py`** — `update_ai_interaction_outcome` (new): lets a feature
  backfill the router-only `destination`/`confidence` columns and/or
  override the outcome `ai_core.ask()` already logged, for the case where
  the call reached Gemini fine but the feature's own server-side validation
  doesn't trust the answer.
- **`templates/start.html`** + **`static/js/start.js`** (new): a centered
  "What do you want to do?" box in the `dash_layout` shell, greeting via the
  existing `_account_first_name`, 4–6 suggestion chips from
  `nav_groups_for(user)`. `start.js` copies `search.js`'s debounce/abort
  pattern client-side (9s timeout vs. the server's 8s), shows a result card
  with Go/Cancel + feedback chips and a ~1.5s auto-navigate, and falls back
  to `window.CSSSearch` (the existing keyword palette engine) on any
  non-`navigate` response, timeout, or network error.
- **`templates/home.html`** — a "✨ Try the assistant" link to `/start`
  beside the role chip.
- **`tests/test_ai_router.py`** (new) — per-role destination routing;
  prompt-injection (a mocked model steering a viewer to an admin-only
  destination still falls back); malformed/out-of-catalog destinations and
  sub-floor confidence rejected server-side; budget-exceeded falls back;
  feedback ownership/RBAC; `/start` renders for all four roles; the login
  redirect honors both settings and leaves a plain `next=/` alone otherwise.

## 2026-07-19 (v2.03 — Phase 0 of the AI integration plan: `ai_core.py` foundation)

`docs/AI_INTEGRATION_PLAN.md` Phase 0: the module every future AI feature is
a thin caller of. Ships with `ai_mode=off` — behavior is byte-for-byte
unchanged; this is purely plumbing + the admin console to operate it.

- **`ai_core.py`** (new) — the only module that ever calls Gemini. Config
  gates (`ai_configured`/`ai_model`/`ai_mode`/`feature_enabled`); error
  taxonomy (`AIError` ← `AIUnavailable`/`AIBudgetExceeded`/`AITimeout`/
  `AIBadResponse`); `budget_check_and_consume` (atomic `BEGIN IMMEDIATE`
  upsert+check+increment on `ai_budget`, keyed by local calendar date —
  survives a restart, no scheduler needed); `_http_generate` (the sole
  network call site — Gemini REST v1beta `generateContent` via `httpx.post`,
  connect timeout 3s/total 8s default, retries once on 5xx/timeout, a 429
  sets a 60s in-memory cooldown and never retries); `mask_for_log` (email +
  digit-run masking, mirrors `ui_telemetry.sanitize_text`); `ask()` (the
  single entry point — config/mode/feature gate → `ratelimit.allow("ai", ip)`
  → budget consume → HTTP → `ai_interaction` log on every outcome, success or
  fallback); `test_connection()` (the `/admin/ai` egress smoke test, bypasses
  mode/feature gates since `ai_mode=off` is the shipped default).
- **`storage.py`** — new `ai_interaction` (full call log incl. masked
  prompt/response, outcome, latency/tokens, and a 👍/👎 `rating` column) and
  `ai_budget` (day+feature keyed daily spend counter) tables in
  `_add_missing_columns`; `create_ai_interaction`, `set_ai_feedback`
  (row-ownership check), `list_ai_interactions` (feature/outcome/rating/since
  filters), `purge_stale_ai_interactions`, `purge_stale_ai_budget`. Both
  tables registered in `pull_backup.py`'s `_CHECK_TABLES`.
- **`retention.py`** — `purge_stale_ai_log` (`--ai-log` CLI flag, mirrors
  `--ui-events`): purges `ai_interaction` past `ai_log_retention_days`
  (default 90) plus the matching stale `ai_budget` day-rows.
- **`ratelimit.py`** — new `"ai"` burst bucket, `(20, 60)` default,
  env-overridable via `CSS_RL_AI`.
- **`app.py`** — `GET /admin/ai` (status card + settings form + interaction
  log browser, filterable by feature/outcome/👍👎), `POST /admin/ai/settings`
  (mode, global + per-feature daily caps, per-feature enable flags, prompt
  logging on/off, log retention, post-login landing default — all
  validated/clamped + `_audit`ed), `POST /admin/ai/test` (calls
  `ai_core.test_connection`, audited either way). Admin-gated for free via
  the existing `/admin` prefix in `_required_cap` — no new gating code.
  `NAV_GROUPS` gains an Admin → AI entry.
- **`templates/admin_ai.html`** (new) — modeled on `ux_insights.html` +
  `feedback_board.html`: status card with per-feature usage bars vs caps and
  a cooldown indicator, the settings form, and the log browser with
  expandable masked prompt/response/error per row.
- **Housekeeping** — `httpx` promoted from the QA section of
  `requirements.txt` to a runtime dependency (this is the app's first
  outbound HTTP call from a request handler); `ai_core.py` registered in
  `deploy_hf.py`'s `RUNTIME_PY`; `version.py` → 2.03 with a plain-language
  entry; `tests/test_ai_core.py` + `tests/test_ai_admin.py` (new) cover the
  budget/cooldown/retry/masking contract and the admin console's RBAC +
  settings clamp + audit trail.

## 2026-07-18 (v2.02 — Downloadable UX handoff + the two dormant telemetry signals)

Three additions to the UX telemetry system shipped in v2.01: a downloadable
AI-analysis handoff, live `search_empty` dispatch, and a `form_abandon`
detector.

- **`ux_handoff.py`** (new, pure — no DB/FastAPI, same testability contract as
  `ui_telemetry.py`) — builds the handoff payload over `build_digest()`:
  `events_per_day`/`event_type_counts`, `pseudonymize_events` (drops
  id/user_id, session ids → per-export `s1`/`s2`… pseudonyms, ≤200 most
  recent), `map_routes_to_handlers` (masked route → app.py handler name, by
  segment-shape match against route objects' `.path`/`.name`),
  `feature_usage` (every NAV_GROUPS destination ranked by pageviews, with
  rarely-used/NEVER-used buckets — the "redesign around what staff actually
  use" section), `build_handoff` (adds `nav_flows`, which `build_digest`
  deliberately omits) and `render_handoff_markdown` (deterministic, pipe-
  escaped, self-describing: app context, vocabulary, sanitization semantics
  and the analysis brief travel inside the file).
- **`app.py`** — new `GET /admin/ux-insights/handoff?days=&fmt=md|json`
  (admin-gated for free via the `/admin` prefix): same window clamp + fetch
  block as `ux_insights`, audited like the Spot Feedback export, ships
  `UX_Handoff_{days}d_{ts}.md`/`.json` as `Content-Disposition: attachment`.
  `_clean_telemetry_meta` now also passes `meta.fields` (a small int — the
  form_abandon touched-field count, clamped 1–500). UX Insights nav keywords
  extended with "handoff export download ai".
- **`static/js/telemetry.js`** — `form_abandon` detector: Map of form →
  touched-field Set built from capture-phase `input`/`change`, cleared on
  `submit`, emitted on `pagehide` only (a tab switch is not abandonment) with
  `meta={fields: n}` — never field names or values. Search/filter forms opt
  out via `[data-search]`/`[role="search"]`/`[data-telemetry-ignore]`; the
  Spot Feedback overlay stays excluded.
- **`static/js/search.js`** — dispatches `csi:search-empty` (the event
  telemetry.js has listened for since v2.01) when a palette/inline query has
  zero page hits AND the debounced `/api/search` fetch settles empty; once
  per term per page load.
- **`templates/_telemetry.html`** (new) — `search_empty_signal(term,
  is_empty)` macro for server-rendered zero-result pages (waits for
  DOMContentLoaded so the deferred telemetry.js listener exists first); used
  by `search.html`, `encode_home.html`, `people.html`. `help.html`'s inline
  topic filter dispatches the same event, debounced. `ux_insights.html`
  gains the download control; `dash_layout.html` cache-busters bumped.
- **Housekeeping** — `ux_handoff.py` registered in `deploy_hf.py`'s
  `RUNTIME_PY`; `version.py` → 2.02 with a plain-language entry.
- **Tests** — new `tests/test_ux_handoff.py` (pure fixtures); handoff-
  endpoint coverage in `tests/test_ux_insights.py` incl. an end-to-end leak
  test (raw digits POSTed through `/telemetry` never surface in the export);
  `meta.fields` ingest coverage in `tests/test_telemetry_ingest.py`.

## 2026-07-17 (v2.01 — Build telemetry + passive UX-behavior telemetry pipeline)

Two additions, both admin-facing: which build is actually running (`/ops`), and a
ranked "what to fix first" digest of passive interface-friction signals (`/admin/
ux-insights`) — dead/rage clicks, failed searches, client errors — ported from
`jongsky25/ofis-platform`'s `lib/telemetry.ts` + `Telemetry.tsx` + ingest/digest
routes (commit `7a7e369`) per `docs/UX_TELEMETRY_HANDOFF_PLAN.md`, adapted to this
app's Flask/Jinja/SQLite stack (that reference is Next.js + Supabase).

- **`deploy_hf.py`** — new `write_build_info(version, deployed_by)` stamps
  `build_info.json` (version, git commit SHA + short SHA, deploy timestamp,
  deployer) right before `upload_folder`, added to `ALLOW` so it ships in the
  same bundle it describes. `ui_telemetry.py` added to `RUNTIME_PY`.
- **`app.py`** — new `_load_build_info()` reads `build_info.json` (falls back to
  just `version.APP_VERSION` on a local/dev run with no deploy metadata). New
  `POST /telemetry` ingest route: login-gated via the existing auth middleware,
  rate-limited (`ratelimit.py`), caps batch size, re-sanitizes every field
  server-side rather than trusting the client's own masking alone. New
  `GET /admin/ux-insights` (admin-gated for free via the existing `/admin`-prefix
  → `manage_users` cap) with a 7/30/90-day window switcher, plus
  `POST /admin/ux-insights/retention` to save the admin-configurable retention
  window. New `NAV_GROUPS` entries for both.
- **`storage.py`** — new `ui_event` table (additive, mirrors the
  `spot_feedback`/`audit_log` conventions) + `create_ui_events`/`list_ui_events`
  (with a `since` window filter) + `purge_stale_ui_events`.
- **`ui_telemetry.py`** (new) — the controlled event-type vocabulary, text/
  selector sanitizers, `mask_route` (a generic segment-shape sibling to
  `monitoring.bucket_path`'s hand-curated table; idempotent, so re-running it
  server-side over an already-masked client value is safe), and the aggregation
  half ported from `lib/telemetry.ts`: `top_routes`/`nav_flows`/`exit_routes`,
  `empty_search_terms`/`errors_by_route`, `friction_by_target`/`friction_score`
  (rage-weighted, user-damped), `correlate_feedback` (matches Spot Feedback by
  route+selector), and `build_digest` (the ranked, feedback-boosted opportunity
  list). All pure — plain dict rows in, no DB — so they're cheap to unit test.
- **`static/js/telemetry.js`** (new) — vanilla-JS capture script (no client
  router here, unlike the React reference): pageview, dead-click, rage-click,
  client-error detection; `sessionStorage`-backed session id (a JS var would
  fragment every full page load into its own "session"); ships via `sendBeacon`
  with a `fetch`/`keepalive` fallback. Wired into `dash_layout.html`, signed-in
  shell only.
- **`templates/ops.html`** — new "Build" panel. **`templates/ux_insights.html`**
  (new) — ranked opportunities table + top-screens/exit-routes/failed-searches/
  errors side panels + the retention-window settings form.
- **`retention.py`** — new `purge_stale_ui_events` (CLI: `--ui-events [--days N]`),
  reading the `ui_telemetry_retention_days` app_setting (default 90 days) when
  `--days` isn't given. Kept independent of the existing attendee-PII job
  (different legal basis, months-based, audited) rather than merged — manual/
  cron-invoked only, matching how that job already runs today (no in-process
  scheduler exists for either yet).
- **Fix found via manual verification** (not code review): running the app
  locally and driving it with Playwright caught `INTERACTIVE`'s `[data-tour]` and
  bare `[tabindex]` clauses — ported as-is from the OFIS reference — both
  matching ancestors present on nearly every click in this app specifically
  (`data-tour` tags whole page regions here, not individual controls; the shared
  `<main tabindex="-1">` skip-link target wraps every page's content), which was
  silently disabling single dead-click detection app-wide. Fixed by dropping
  `[data-tour]` and scoping `[tabindex]` to `:not([tabindex="-1"])`.
- **Tests** — 42+ new tests: pure sanitizer/`mask_route`/aggregation unit tests
  (including OFIS's own ranking-acceptance case — a feedback-correlated hotspot
  outranking a higher-raw-count one), storage round-trips, ingest-route RBAC/
  validation/re-sanitization tests, retention purge tests, and digest-view RBAC/
  rendering tests. Full suite: 634 passed (3 pre-existing failures unrelated to
  this change, dependent on a large seeded production `css_is.db`).
- Out of scope for this pass (matching the handoff doc's own suggested order):
  wiring `retention.py --ui-events` into an automatic schedule — it's manual/
  cron-invoked only right now, same as the existing attendee-PII purge.

PR #26.

## 2026-07-17 (v2.00 — Quick-pick comment chips capped at 3, opposite pairs mutually exclusive)

Respondents could tap every canned "quick-pick" comment chip on a survey form at
once (`REMARK_CHIPS` in `app.py`), producing walls of tags and, worse,
self-contradictory pairs (e.g. "Fast service" + "Long wait" both landing in the
same `remarks` free-text field).

- **`app.py`** — `REMARK_CHIPS` restructured from a flat list of strings per
  survey kind to a list of `(word, group)` pairs; `group` is `None` for
  standalone chips or a shared key (`speed`, `process`, `clarity`, `timing`)
  for chips that are opposites of each other. New `MAX_REMARK_CHIPS = 3`
  constant, passed into the `rating.html` / `combined_form.html` render
  contexts as `max_remark_chips`.
- **`i18n.py`** — `REMARK_CHIPS_FIL` restructured with the same group keys,
  index-aligned with `REMARK_CHIPS`; `chips_hint` copy (en + fil) updated to
  mention the 3-chip limit.
- **`templates/rating.html`, `templates/combined_form.html`** — chip loop
  unpacks `(word, group)` and renders `data-group` / the container's
  `data-max-chips`; `toggleChip()` in both templates now frees a conflicting
  chip's slot (same `data-group`) before re-checking the cap, so tapping a
  chip's opposite swaps it in even while already at the limit, and a `.chips.
  at-max` CSS rule dims the remaining inactive chips once the cap is hit.
- **`static/js/app.js`** — new shared `window.refreshChipCap(container)`
  helper (reads `data-max-chips`, toggles `.at-max`), called from both
  templates' `toggleChip()` and from the draft-resume chip re-lighting logic
  so a resumed draft saved before this change (with more than 3 words) shows
  the correct dimmed state.
- No backend/schema change — `remarks` stays free text; the cap/conflict
  rules are a chip-authoring aid only, so typing past 3 phrases by hand is
  still allowed.
- **Verified** with Playwright against the running app: cap enforcement,
  opposite-pair swap-while-at-cap, and draft-resume re-hydration all behave
  correctly; confirmed both `/r/<token>` and `/seq?tokens=...` render the new
  markup.

PR #18.

## 2026-07-17 (v1.99 — Type-2 activity XLSX "Relevant Findings" reformatted to the official MRR layout)

The Type-2 activity inventory Excel download (`/reports/activities-export` and
`/reports/activities/export-selected`, Sheet 1 `AGENDA 4_Sheet1`) had its
"Relevant Findings" cell reformatted to match the official MRR report's
letterhead layout, per a direct format spec from the bureau.

- **`app.py`** — `_activity_relevant_findings(e)` (replaces `_activity_css_seed`)
  builds the cell as: activity title / full date / modality, blank line,
  `SERVQUAL Score: <gap> (<verdict>)` and `Overall SERVQUAL Rating: <OSQ>
  (<band>)` (reusing `dashboard_insights.activity_servqual`, the same official
  scorecard the per-activity report page already shows — so the export and the
  screen can never disagree), `Response Rate:` / `Total Number of Responses:` /
  `Total Number of Participants (Pax):`, blank line, then `COMMENTS:` with up
  to 5 verbatim remarks typed into the form's free-text comment box (never the
  pre-selected rating items).
- New `_attach_activity_findings(atoms, conn, events)` mutates each event dict
  in place with `report` (the SERVQUAL scorecard) and `comments` (deduplicated,
  capped-at-5 remarks via the existing `_dedup_remarks`/`_meaningful_remark`
  helpers, which already drop throwaway answers like "none"/"n/a"/"wala").
  Called from both export routes before the connection closes, since the
  comment fetch needs an open `conn`. The `export-selected` route's `events`
  come from the memoized `view_memo("events", ...)` view, so `chosen` is built
  as `[dict(e) for e in events if ...]` — copies, so the in-place mutation
  never corrupts the shared cache.
- New `_fmt_activity_date_full` (full month name, e.g. "January 15, 2026") for
  the letterhead line, alongside the existing abbreviated `_fmt_activity_date`
  used in Sheet 2's inventory table.
- **Tests** — full suite green against a fresh empty DB (no regressions); the
  new formatter and the `_dedup_remarks` cap/filter behavior were additionally
  smoke-tested directly against fabricated event/report/comment payloads (no
  new test file — no seeded fixture activity exists to assert the exact cell
  text against end-to-end; the existing `test_bulk_actions.py` export-selected
  test only checks that a workbook downloads, not cell content).

PR #17.

Second half of the spot-feedback #67 fix. Root cause of the duplicate event that
prompted v1.96: `POST /create` had zero duplicate-submission protection — no
client-side disable-on-submit guard, no idempotency token, no server-side check.
The two live duplicate pairs (26 minutes and 3 minutes apart, same creator, same
title/date/venue/organizer) don't look like a reflexive double-click; more likely
the creator didn't realize the first save had already succeeded and re-ran Create
from scratch.

Considered blocking the second submit server-side with an interstitial "are you
sure?" page, but that changes what `POST /create` does on a matching title+date —
and the existing test suite (test_modality.py, test_date_range.py,
test_registration_dedup.py, test_event_e.py, test_certificate.py,
test_date_handling.py) has ~25 cases across 6 files that legitimately recreate an
identically-titled/dated activity under the same manager fixture within one test
session (session-scoped shared DB), which is indistinguishable from the real
duplicate case by title+date+creator alone. Blocking broke all of them. Went with
a **live, non-blocking** check instead: it warns, it never blocks Save, so
`POST /create`'s behavior is completely unchanged and every existing test still
holds — including new tests that pin this down explicitly.

- **`storage.py`** — new `find_recent_duplicate_event(conn, title, event_date, created_by, within_hours=6)`: the most recent event with the same title (case/space-insensitive) and date, made by the SAME creator inside the lookback window. Returns `{id, event_token, created_at, event_kind, responses}` or `None`.
- **`app.py`** — new `GET /create/check-duplicate?activity_name=&event_date=` (JSON, login-required via the existing middleware): calls the storage helper for the signed-in user and returns `{"duplicate": null}` or the match with a human-readable timestamp (`_humandt`). Read-only, no side effects.
- **`templates/form_create.html`** — new `#dupWarn` note box (hidden by default) and `checkDuplicate()`: a 500ms-debounced fetch fired on `activity_name` input / `event_date` change. On a hit it shows when the existing one was made, its response count, and a link straight to it (`/monitor/<token>` for a bureau event, `/activities/<token>/manage` for an outside one). Never touches form submission.
- **`static/css/app.css`** — `.dup-warn`, amber-toned (a heads-up, not the red `.errors` block) since the form is otherwise valid and submitting is still allowed.
- **Tests** — new `tests/test_create_duplicate_warning.py`: the storage matcher (same-creator hit, different-creator miss, different-date miss, outside-lookback-window miss), the JSON endpoint (hit, miss, login-required), and — the key regression guard — `test_create_still_allows_a_genuine_second_activity_with_the_same_name` locking in that `/create` itself is unchanged. Full suite green (589 passed; the same pre-existing `test_backups.py` failure and `test_csm_official.py` collection error as v1.96, both unrelated).

## 2026-07-15 (v1.96 — archive/restore reach bureau & outside events, not just standalone forms)

Prompted by spot-feedback #67: a same-day duplicate bureau event (created by mistake, zero
responses) had no reachable Archive button. The only inline archive on the Ongoing feed
(`/activities/instance/<fid>/archive`, v1.74) requires the activity still be in that feed —
which a bureau event with no `close_at` leaves at the end of its event day — and the "Your
recent activities" strip's inline archive (`/activities/form/<fid>/archive`) explicitly
refuses anything with an event record. Once an event ages out of Ongoing there was **no
one-click Archive control left anywhere** (its own manage page's Archive button is
`event_kind == 'outside'`-only). Separately, an event archived via the Ongoing feed or the
Activities-page bulk action had **no restore path in the UI at all** — `/activities/archived`
and its bulk-restore route both filtered to standalone forms only, even though the bulk
archive action's own confirmation message claims "An admin can restore them."

- **`storage.py` `activities_by_creator`** — new `has_event` field per row (`tok is not None`),
  alongside the existing `archivable` (unchanged: standalone-only, drives the per-form route).
  Lets a template pick the right archive/restore route per row shape.
- **`app.py` `activity_inline_archive`** (`POST /activities/instance/{fid}/archive`) — now
  accepts `restore=1`, mirroring every other archive route. Restore expands to the full
  event bundle exactly like the archive direction does, via `st.set_form_archived`. Kept the
  existing permission model (`create_activity`, no per-creator ownership check) for both
  directions, since that already matched production behavior for archiving a bureau/outside
  event from the Ongoing feed.
- **`app.py` `/activities/archived`** (GET) — now lists rows where `archivable` **or**
  `has_event` is true, so event-bundled archives are finally visible and restorable.
- **`app.py` `/activities/archived/bulk`** — extended to detect `info["has_event"]` per ticked
  id and, when set, expand to the event's full form bundle and restore it under the
  `create_activity` gate; standalone rows keep the exact prior ownership-scoped behavior
  (creator or admin) so `test_bulk_restore_skips_other_owners_form` still holds.
- **`templates/home.html`** — "Your recent activities" now renders an Archive button for
  event-bundled rows too (`a.has_event`, posting to the instance route with the same confirm
  dialog the Ongoing feed uses), not only standalone ones (`a.archivable`, unchanged route).
  Copy on both variants of the feed subtitle updated to drop "standalone".
- **`templates/activities_archived.html`** — per-row Restore posts to
  `/activities/form/<fid>/archive` for standalone rows (unchanged) or
  `/activities/instance/<fid>/archive` for event-bundled ones (new); page copy no longer says
  "Standalone activities."
- **Tests** — `tests/test_home_feeds.py`: restore round-trip for a bureau event via the
  instance route (archive → appears on Archived page → restore → both bundled forms come
  back), and a new "Recent activities" render test confirming a bureau event gets an Archive
  button. `tests/test_bulk_actions.py`: bulk-restore of a bundled event (both forms come back,
  gated on `manage_event`/`create_activity`). Full existing suite green (589 passed; the one
  `test_backups.py` failure and the `test_csm_official.py` collection error are pre-existing
  environment artifacts unrelated to this change — reproduced identically with these changes
  stashed out).

## 2026-07-13 (v1.95 — manager-entered respondent count as the completion-rate denominator)
Builds on v1.94 (which folds the not-pre-registered responses into the rate). A section manager (on activities they created) or an admin (on any) can now **override the completion-rate denominator** with the real number of respondents, instead of being tied to the online-registration count. Even after v1.94 counts walk-ins, the denominator is still `registered + unattributed` — which misses attendees who took part but neither pre-registered nor left an attributable response; an organizer who knows the true headcount can now set it directly.

The whole funnel is read from one function (`storage.event_registration_summary`, which `list_events` calls per event and the SSE stream/realtime push seed from), so the math changed in a single place and propagates to every surface — the `/monitor` index, the per-activity page, and the live stream.
- **`storage.py`** — new `event.respondent_target` column (nullable `INTEGER`, lightweight `ALTER TABLE` guard beside `created_by`), threaded through `_EVENT_COLS` + `_event_row` so it reaches every `get_event` caller. New `set_event_respondent_target(conn, event_id, value)` (stores a positive int, `NULL` clears). New `_completion_rate_target(numerator, target)` — `min(100, round(numerator*100/target))`, `None` when target falsy. `event_registration_summary` now branches: with a target set it returns `(completed + unattributed) / target` and `denominator_source="target"`; **with no target it keeps v1.94's default** `(completed + unattributed) / (registered + unattributed)` and `denominator_source="registered"`. It also returns `respondent_target`. Docstring notes the multi-form approximation (`unattributed` is a response-row count, so a walk-in answering two forms counts twice).
- **`app.py`** — new `POST /activities/{event_token}/respondents` (beside the window/dates editors, same `_can_manage_event` creator-or-admin gate). Blank clears; a non-integer or negative → `?err=badtarget`; a value **below** the current respondent count (`completed + unattributed`) → `?err=targettoolow` (nothing saved), so the rate can't be pushed past 100% at save time. Audits `event_respondent_target_set`. `_manage_ctx` now carries `reg_summary` so the editor can pre-fill and show the floor.
- **`templates/activity_manage.html`** — new `#respondents` manage card: number input pre-filled from `ev.respondent_target`, current-state line ("measured against N" vs "live registered count (N registered)"), and the two error flashes.
- **`templates/monitor_event.html` + `monitor.html`** — the completion-rate card appends "· of N expected" when `denominator_source == 'target'` (with a target-aware tooltip on the detail page that keeps v1.94's everyone-who-took-part copy for the default); the SSE handler updates that label live from the streamed `denominator_source` / `respondent_target` (already in the summary dict, so no payload change).
- **Tests** — `tests/test_monitor.py`: `test_respondent_target_overrides_completion_denominator` (default → 100, override 10 → 50 counting walk-ins, clear → back to default), `test_completion_rate_target_clamps_at_100` (unit incl. later-drift clamp and `None`), plus four route tests (set/clear/reject-badtarget, reject-below-actual, non-creator forbidden → `/e/{tok}`, admin on any). Storage + monitor/RBAC/event-link suites green; the three route-level failures under a fresh checkout are the pre-existing seeded-DB fixture gap (they reproduce identically on the base branch).

## 2026-07-13 (v1.94 — Monitor completion rate now counts everyone who took part, including the not-pre-registered)
Follow-up to v1.93's funnel work. The Monitor's "Completion rate" was computed over the pre-registered roster only — `completed / registered` — while walk-in / QR / paper responses were reported separately in the "Not pre-registered" card and never entered the rate. Per request, the rate now measures the share of **everyone who took part** who finished: the not-pre-registered responses are folded into **both** the numerator and the denominator, each counted as a completed submission (it is already an answer that came in).
- **`storage.py` `event_registration_summary`** — `completion_rate` is now `_completion_rate(completed + unattributed, registered + unattributed)`, i.e. `(completed + unattributed) / (registered + unattributed)`. Because the `unattributed` term appears in both numerator and denominator, the v1.93 invariant is preserved: the rate hits **100% only when every REGISTERED person has finished** (the extra term cancels), a near-complete event still reads 99, and a walk-in helps rather than dilutes. `_completion_rate(done, total)` is generalized from `(completed, registered)` to a `done`-out-of-`total` helper with the same `None`-when-empty / cap-at-99 behavior; it now returns `None` only when nobody took part at all (a pure-walk-in event that answered reads 100).
- **`templates/monitor_event.html`** — the "Completion rate" and "Not pre-registered" card tooltips and the explanatory note are reworded so the copy matches the new meaning (walk-ins count toward completion; 100% still requires all registered done).
- **Tests** — `tests/test_monitor.py`: `test_unattributed_responses_counted_separately` and `test_completed_never_exceeds_registered_with_walk_ins` updated to the new values (1 completed + 4 walk-ins → `(1+4)/(2+4)` = 83), plus a new `test_completion_rate_includes_not_pre_registered` locking in the include-not-pre-registered behavior and the "100% only when all registrants finish" guard. All 34 monitor tests green (the route-level `FileNotFoundError`s remain the pre-existing seeded-DB fixture gap).

## 2026-07-09 (v1.93 — Spot Feedback #63/#64: Monitor "Completed CSS" could read higher than "Registered"; funnel invariant enforced)
Two Spot Feedback items on the same Monitor page (`/monitor/05cf28a05990`, the headline stat cards): the "Completed CSS" figure could read *more than* "Registered" and jump on refresh (e.g. 41→42) (#64), and a registrant who had finished the survey showed as "Not started" (#63). Root cause of #64: the "Completed CSS" card was fed by **two different metrics**. The server render seeds it with `summ.completed` — registrants who answered every non-archived form (bounded by `registered`). But the live SSE stream (`/api/monitor/{token}/stream`), which the page's `EventSource` connects to a fraction of a second after load and on every new response, pushed `event_response_total(event_id)` instead — the **raw response-row count** across the event's forms, including unattributed walk-in / QR / paper responses and counting each row. So a moment after load the card was overwritten with the total-responses number, which can exceed `registered` and ticks on every walk-in. (Confirmed on the live event: 40 registered, 39 completed, **3 unattributed** → the old stream pushed 42, exactly the "41–42 / more completed than registered" reported. #63 is the attribution corollary — that one "Not started" registrant answered without her personalized `att` link, so her response is one of the 3 unattributed and her roster row stayed "Not started".)

The fix makes the whole funnel move as one authoritative unit, and pins the invariant *Completed ≤ Registered, and 100% only when they are equal*:
- **`storage.py` `_completion_rate(completed, registered)`** (new) — `None` with no registrants, exactly `100` only when `completed == registered`, otherwise `min(99, round(...))` so a near-complete event (199/200 = 99.5%) reads **99**, never rounding up to a misleading 100%. `event_registration_summary` now derives `completion_rate` through it. Since `completed` is a subset of the registrant roster, the rate is always in `[0, 100]`.
- **`app.py` + `realtime.py`** — the live channel now carries the **entire funnel dict** (registered / completed / in_progress / not_started / completion_rate / unattributed), not a bare count. `monitor_live_stream` seeds and streams `event_registration_summary(...)`; both `realtime.broadcast` sites (single-form and combined-QR submit paths) push the same summary; `realtime.broadcast(event_id, payload)` documents the payload. So "Completed" tracks registrants who finished — never the raw response total — and updates in lockstep with the "Registered"/"In progress"/"Not started"/rate cards.
- **`templates/monitor_event.html`** — each stat card carries an id; the SSE handler updates *all* of them together (and formats the rate `%` / `—`), so the display can never show Completed above the live Registered, or a rate over 100%, even when a new person registers-and-completes after the page loaded. (The removed `event_completed_count` helper from the first cut is superseded by streaming the full summary.) A new **"Not pre-registered"** card surfaces `summ.unattributed` — the walk-in / QR / paper responses that came in with no registration — as its own dashed-border figure (previously it lived only in the prose note), and it live-updates with the rest of the funnel. The note is reworded to point at the card rather than repeat the count (so it can't go stale on a live tick).
- **`app.py` `_build_monitor_xlsx`** — the roster export's funnel line now also carries "Not pre-registered (walk-in / QR / paper): N", so the downloaded XLSX matches the page.
- **Tests** — `tests/test_monitor.py`: `test_completed_never_exceeds_registered_with_walk_ins` (1 completed + 1 not-started + 4 walk-ins → `completed == 1 ≤ registered == 2` and `rate ≤ 100`, while `event_response_total == 6`, the number the old stream would have shown); `test_completion_rate_hits_100_only_when_all_registrants_complete` (unit cases incl. 199/200 → 99 and 40/40 → 100, plus an end-to-end 199-of-200 summary reading 99, not 100). Storage-layer monitor suite green (the route-level `FileNotFoundError`s are the pre-existing seeded-DB fixture gap and reproduce identically on the base branch).

## 2026-07-09 (v1.92 — individual person report download now carries the respondent comments too)
Follow-up to v1.91: the single-person report page (`/dashboard/people/<id>`) shows a comments panel on screen (`story_panel` over the person's response ids), but its **Download** button — the same `/dashboard/export?visual=person` path — was deliberately built to omit them ("a named-person file shouldn't carry them off-screen"). Since the on-screen page already shows them, the download now matches, using the same de-duplicated `×N` block as the per-activity and aggregate reports.
- **`app.py` `_visual_payload` (`visual == "person"`)** — attaches `payload["comments"] = {items, total, unique}`. The response ids are the union of this person's walk-in (`di.arta_slice`) and speaker (`di.rp_slice`) responses over the already-scoped `atoms` (the `a`/`r` slices computed for the date span) — the SAME rids the on-screen `dashboard_person` route feeds to `story_panel`. Flattened via `di._flatten_quotes` and de-duplicated via the existing `_dedup_remarks(..., cap=_COMMENT_CAP)`. Honors the period/single-activity scope. Stale "everything the page shows EXCEPT the verbatim quotes" comment updated.
- **`dashboard_docs.py` `person_pdf`** — adds a bottom "Respondent comments (N)" section (same shape as `event_pdf`: intro, one quoted `rd._comment_text(q)` line per unique, "…and N more" past the cap). Omitted when empty.
- **`dashboard_docs.py` `person_pptx`** — adds an "In their words" quotes slide after the methods slide (`rd._quotes_slide`, neutral column, `×N` on repeats). Omitted when empty.
- **`dashboard_docs.py` `METHODS_PERSON`** — the note that read "Verbatim comments are intentionally omitted from this file" now describes the included de-duplicated comments.
- **`dashboard_export.py` `_tables` (`visual == "person"`)** — adds a "Respondent comments" sheet (`Comment`, `Count`), most-repeated first. Omitted when empty.
- **Verification** — `tests/test_activity_report_comments.py` extended with 5 person-report tests (PDF heading/count + `×N` + empty-omit, PPTX "In their words" slide, XLSX `Comment`/`Count` sheet + empty-omit). Full suite: 582 passed, 3 failed — the same 3 pre-existing seed-dependent failures as v1.91, identical on the base branch.

## 2026-07-09 (v1.91 — per-activity report download now carries the respondent comments)
The single-activity report page (`/reports/activities/<id>`) shows a comments panel on screen, but its **Download** button goes through a different path than the v1.90 reports: it hits `/dashboard/export?visual=event&event_id=<id>&fmt=…` → `_visual_payload(visual="event")` → `dashboard_export.export` → `dashboard_docs.event_{pdf,pptx}` / `dashboard_export._tables`. That path was built "NO verbatims" and v1.90 never touched it, so every per-activity download (PDF/PPTX/XLSX) omitted the comments the page displayed. This wires the same de-duplicated comment block into that path.
- **`app.py` `_visual_payload` (`visual == "event"`)** — now flattens the activity's verbatims (`di._flatten_quotes(st.verbatims_for_responses(conn, ev["response_ids"]))`, the SAME source the on-screen `story_panel` reads) and runs them through the existing `_dedup_remarks(..., cap=_COMMENT_CAP)`, attaching `payload["comments"] = {items, total, unique}` — one flat `×N` list, since SERVQUAL comments aren't typed positive/negative. Stale "NO verbatims" comment updated.
- **`dashboard_docs.py` `event_pdf`** — adds a bottom "Respondent comments (N)" section before the Methods box: an intro line, one quoted line per unique comment via `rd._comment_text(q)` (appends `(×N)` only when `count > 1`), and an "…and N more unique comments" note when the unique count exceeds the cap. Omitted entirely when there are no comments.
- **`dashboard_docs.py` `event_pptx`** — adds an "In their words" quotes slide (reusing `rd._quotes_slide`) after the methods slide, feeding the top comments in a single neutral column (`rd._SOFTP`) with `×N` on repeats. Omitted when empty.
- **`dashboard_export.py` `_tables` (`visual == "event"`)** — adds a "Respondent comments" sheet (`Comment`, `Count`) after the "Who responded" table, most-repeated first. Feeds the XLSX and the PPTX table fallback. Omitted when empty.
- **Verification** — new `tests/test_activity_report_comments.py` (7 tests): the flatten+dedup source matches the on-screen verbatims (dup collapsed to `×2`, item-note kept, "none" dropped); the PDF story carries the heading/count, `×N` quotes, the overflow note, and omits the section when empty; the PPTX blob has the "In their words" slide; the XLSX has the `Comment`/`Count` sheet with the right count and is omitted when empty. Full suite: 577 passed, 3 failed — the 3 (`test_search::test_api_search_activities`, `test_audit_insights::test_audit_page_shows_friendly_labels`, `test_integrity::test_headline_counts_present`) are pre-existing and reproduce identically on the base branch (they need a richer seeded demo DB than a fresh clone's `setup_db.py` builds).

## 2026-07-09 (v1.90 — downloadable reports: de-duplicated respondent comments at the bottom, with ×N repeat counts)
The downloadable reports repeated identical free-text answers verbatim (and capped each ARTA bucket at 12, so a busy period both duplicated and truncated). They now collapse repeats into one counted entry and list them at the foot of the report.
- **`app.py`** — new `_dedup_remarks(items, cap)`: drops throw-away answers via `_meaningful_remark` (blanks, pure punctuation, "none"/"n/a"/"wala"/"ok"…), folds case + internal whitespace to group identical remarks, keeps the first-seen spelling, and returns `(grouped, shown_total, unique_total)` where each entry is `{text, count, type}` sorted by count desc then first appearance. So the listing carries only real feedback, with genuine repeats collapsed into one `×N` line. `test_comments_split_by_feedback_type` updated to assert throw-away answers are dropped; new `test_comments_deduplicate_with_counts` locks the fold + count.
- **`app.py` `_arta_comments`** — rewritten on top of the helper: still splits positive/negative/other, but each bucket is now de-duplicated and capped at `_COMMENT_CAP` (50) uniques, with per-bucket `_shown` (non-blank raw count) and `_unique` (distinct before cap) added, plus report-level `total`/`unique`. The old `limit=12` per-bucket slice is gone.
- **`app.py` `_servqual_official`** — attaches `block["comments"] = {items, total, unique}` built from each response's free-text `comment` via the same helper (one flat list — SERVQUAL comments aren't typed). Only DOCX/XLSX read it; PDF/PPTX ignore the key.
- **`report_docs.py`** — new `_comment_text(q)` renders `text  (×N)` only when `count > 1`. `arta_docx` now lists the full de-duplicated buckets with an "…and N more unique comments" note when a bucket exceeds the cap; `servqual_docx` gains a bottom "Respondent comments" section (it had none); `servqual_xlsx` gains a "Comments" summary sheet (distinct comment + count) beside the raw per-respondent column; `arta_pdf`/`arta_pptx` keep their curated few-quotes but feed from the de-duplicated list and show `×N`, with the PDF note pointing at the DOCX for the complete list.
- **Verification** — `tests/test_arta_report.py`, `tests/test_servqual_raw_responses.py`, `tests/test_report_activity_verbatims.py`, `tests/test_comment_bucketing.py` all pass; a direct render smoke confirms the ARTA DOCX/PDF/PPTX and SERVQUAL DOCX build and the SERVQUAL XLSX carries a populated "Comments" sheet with correct counts. (The `test_search.py` / `test_audit_insights.py` / `test_integrity.py` failures in the sandbox are pre-existing — they need a seeded demo DB absent from a fresh clone — and reproduce identically on the base branch.)

## 2026-07-09 (v1.89 — terminology: "activity report" → "customer satisfaction survey report"; "verdict" → "interpretation")
Renamed two user-facing terms across the interface and the downloadable reports. Display strings only — no logic, data-key, or stored-data changes: CSS classes (`.verdict`, `.jverdict`), the `_servqual_verdict` helper, dict keys (`servqual_verdict`, `d["verdict"]`), and template variables are untouched, so scores and saved responses are identical. The word "activity" as an *event* (create/manage/close activity, the Activities list, the "Activity / Event Satisfaction" report type) is a distinct concept and was left as-is — only the phrase "activity report" changed.
- **`app.py`** — the per-event report title fed to `dx.VisualMeta` (the header on the PDF/PPTX/PNG/XLSX export) is now `… — Customer Satisfaction Survey Report`.
- **`templates/reports.html`** — the "View individual … reports →" link now reads "customer satisfaction survey reports"; the consolidated SERVQUAL dimension table column header is now "Interpretation".
- **`templates/home.html`** — the home feed hover tooltip now opens "the customer satisfaction survey report".
- **`templates/activity.html`** — the satisfaction-journey card caption "overall verdict" → "overall interpretation" (the per-dimension "Interpretation" header was already in place).
- **`templates/team.html`** + **`dashboard_insights.py`** (`_confidence_note`, `confidence_phrase`) — the low-sample notes now say "an early hint, not an interpretation".
- **`report_docs.py`** — the Word (`.docx`) and Excel (`.xlsx`) SERVQUAL dimension table header "Verdict" → "Interpretation".
- **`dashboard_docs.py`** — the event PDF SERVQUAL dimension table header "Verdict" → "Interpretation".
- **`dashboard_export.py`** — the Excel export's SERVQUAL sheet column key "Verdict" → "Interpretation".
- **Verification** — `py_compile` clean on all edited modules; `tests/test_activity_report.py` passes. Rendered against a seeded demo DB: the activity report page and its `.xlsx`/`.pdf`/`.pptx` downloads show "Interpretation" (no "Verdict") and the "Customer Satisfaction Survey Report" title. (The `test_routes.py` failures in the sandbox are pre-existing — they need a delivered `css_is.db` fixture absent from the repo — and reproduce identically on the base branch.)

## 2026-07-09 (v1.88 — Spot Feedback #59: a closed activity lingered on the home "Ongoing" feed until the next day)
Closing an activity ("reporting is already closed") left it under "Ongoing — CSS collecting" on the home dashboard for hours. Two compounding faults in the home "ongoing" feeds' time test, both because the feeds reached for SQLite's `date/datetime('now','localtime')` instead of the app's canonical clock:
1. **Wrong timezone.** Every stored timestamp (`event_date`, `close_at`, `submitted_at`) is written in Asia/Manila via `tzutil` — precisely because the container runs in UTC (a Hugging Face Space; see `tzutil`'s own note). But `'localtime'` follows the *container* zone (UTC), so the feeds compared a UTC "now" against Manila-stamped `close_at` — an ~8 h skew that kept a just-closed activity "collecting" until UTC caught up.
2. **Separator mismatch.** `close_at` is ISO with a **'T'** (`…T08:57:40`); `datetime('now','localtime')` renders with a **space**. With `close_at` unwrapped, the compare was raw text, and on the same date `' '` (0x20) sorts before `'T'` (0x54), so `now <= close_at` stayed true all day.

(The public `/seq` form was unaffected: `_window_state` compares `_now_local().isoformat()` — Manila, 'T' — against `close_at`, so both zone and separator matched and the link closed on time. The bug was confined to the dashboard classification.)

The fix makes the feeds read the app clock, not the container's:
- **`storage.py`** — new `_local_now()` / `_local_today()` (thin `tzutil` wrappers). `upcoming_events`, `ongoing_events`, `ongoing_standalone`, and `ongoing_invited` now **bind** the Manila now/today as query parameters instead of `date/datetime('now','localtime')`, and compare `datetime(?) <= datetime(fi.close_at)` (the `datetime()` wrap also normalises `close_at`'s 'T' separator). `today_local()` and the two "event day has passed" checks (`event_css_done`, `list_shared_events`) likewise derive today from `tzutil`, so the whole lifecycle splits the day on the same Manila boundary everywhere.
- **`storage.py` `lifecycle_of`** — normalises both operands (`.replace("T"," ")`) before the text compare; its caller now passes a Manila `tz.now_iso()` (was `datetime('now','localtime')`).
- **Tests** — `tests/test_outside_activity.py`: pinning the app clock (`_local_now`/`_local_today`) either side of an 08:57 close flips `ongoing_invited`, proving it honours the bound Manila clock, not the container's `'localtime'` — the failure mode a past-date test (date part alone) never caught; `lifecycle_of` reads a same-day post-close now as concluded. Suite green (547 passed; pre-existing env-only failures unchanged).

## 2026-07-09 (v1.87 — Spot Feedback #60/#61/#62: an activity's freshly-encoded responses could vanish from the reports)
Three reports on one invited activity ("Reorientation to PK Excel Workbook and Live Encoding", event 10, 286 responses): its Manage page counted 286 responses and offered a "View resource-person results" link, but the Type-3 report showed "No responses in this scope", the 286 responses didn't appear, and the activity was missing from the report's Activity picker. The data was intact in the database — the responses had simply fallen out of the in-memory analytics cache (`atoms`), so every view built on that cache misbehaved (the Type-3 scope was empty; `build_events` **skips** an event whose cached responses total 0, which dropped it from the Activity picker and from `event_rp_results_url`'s target), while raw-SQL views like the Manage page's own counts still saw all 286.
Root cause: the atoms cache appends only answers past a stored high-water mark of `answer.id`. Every build path (`_build_blocking`, `_refresh_worker`, and the persisted-snapshot writer) read that mark with a **separate** `SELECT MAX(id)` taken *after* the frame was loaded. Any answer another connection committed in the gap between "load the frame" and "read the mark" landed *past* the frame but *under* the mark, so every later `a.id > mark` incremental append skipped it permanently. The throttled pickle then persisted the short frame under a count/max data-key that looked complete, and `_hydrate_atoms_from_pickle` reloaded it on each Space restart — making the gap sticky. A busy live-encoding session (this activity's answers, id 463078–466223) hit exactly that window; live Type-3 totalled 14,767 responses where a from-scratch load of the same DB totalled 15,053 — the difference was exactly event 10's 286.
- **`storage.py` `load_atoms`** — new `upto_answer_id` bound (loads `a.id <= that`). A build now snapshots the mark first and loads up to it, so the frame and the mark it's stored with cover exactly the same rows. The `upto`/`after` windows tile the answers with no gap and no overlap (old + delta == full).
- **`app.py`** — new `_answer_maxid(conn)` helper; `_build_blocking` and `_refresh_worker` snapshot the mark **before** loading and bound the load to it (full and incremental paths), removing the after-the-load `MAX(id)` read entirely.
- **`app.py` snapshot cache** — the sidecar now records the exact mark the frame was built to (`atoms-v2` format: tag + `repr(key)` + amax), and `_hydrate_atoms_from_pickle` restores the frame *with* that mark instead of re-reading `MAX(id)`. Bumping the tag also makes any older tag-less sidecar (including a short one left by the pre-fix path) fail to match, so a stale pickle is dropped and rebuilt clean on the next boot — self-healing the live gap on deploy.
- **Tests** — `tests/test_atoms_cache.py`: `upto`/`after` tile cleanly (`old ⊎ delta == full`); a commit that races the mark snapshot is deferred (behind the mark, out of the frame) and folded in by the next append, never stranded; the v2 snapshot round-trips the frame with its mark; a legacy sidecar is refused. Suite green (no new failures).

## 2026-07-06 (v1.86 — a still-open invited activity now shows on the home "Ongoing" feed)
An invited / "outside" activity (`event_kind='outside'`) is a set of Form-3 speaker reviews grouped under an event record, gathered through one combined `/seq` QR — it has **no Form 2**. The two home "Ongoing" feeds each excluded it by construction: `ongoing_events` filters `survey_type = 2` (it has none) and `ongoing_standalone` filters `ef.form_instance_id IS NULL` (it *has* an event record). Its only home was the "Your recent activities" strip, which drops anything more than 7 days past its `event_date` (`activities_by_creator(..., since_days=7)`). So an invited activity whose event was >7 days ago but whose `/seq` window was still open (`close_at` NULL or future — `_window_state` keeps the public form live) vanished from every home feed while still collecting responses: live to raters, unmanageable by its creator. Reported as a working combined-QR link that "doesn't reflect" under Upcoming/Ongoing/Recent.
- **`storage.py`** — new `ongoing_invited(conn, limit=20)`: one row per `event_kind='outside'` event that has started (`date(event_date) <= today`) and whose window is still open (`close_at IS NULL OR now <= close_at`, matching the public `/seq` form rather than the event-day-only rule the other feeds use for a NULL close). Collapses an activity's speaker forms to a single row carrying the event title, the total response count across its speakers, its speakers, and a `/activities/<token>/manage` link. Rows are shaped like the feed's standalone branch (`standalone=True`, `event_token=None`); `id` is a representative form id, which the inline-archive route already expands to the whole event.
- **`app.py` `home`** — the Ongoing feed is now `ongoing_events + ongoing_standalone + ongoing_invited` (still sorted newest-first). No template change: the existing standalone branch renders the new rows (response count + manage link), and no dedup is needed — the three feeds are mutually exclusive by shape.
- **Tests** — `tests/test_outside_activity.py`: `ongoing_invited` lists an open past activity as one collapsed manage-linked row; excludes a future (not-yet-held) one; excludes one whose window has elapsed; includes one with a future close; and end-to-end, the home page surfaces an open invited activity with its manage link. Full `test_outside_activity.py` green (22); suite green.

## 2026-07-06 (v1.85 — Spot Feedback #57: open a registrant's own response from the Monitor page)
The Monitor roster showed each registrant's CSS status but gave no way to see the response behind it. Feedback #57 asked for a click-through from a registrant to their actual ratings and comments. Read-only, back-office only, and scoped to registrants who answered via the link tree — anonymous walk-in/QR/paper responses (`attendee_id NULL`) are never attributable and never surface here.
- **`storage.py`** — new read-only `attendee_response_detail(conn, event_id, attendee_id)`: that registrant's responses to the event's non-archived forms (answers, per-item notes, overall verbatim). Only rows carrying the given `attendee_id` are returned. No schema change.
- **`app.py`** — new route `GET /monitor/{event_token}/attendee/{attendee_id}/response`, gated to the activity creator/admin (same gate as Monitor). Reuses `survey_spec` so wording and scale labels match what the rater saw (e.g. 5 → "Strongly agree", 4 → "Excellent"). The view is audited (`attendee_view_response`). A purged (identity-removed) registrant is shown as such with no answers surfaced.
- **`templates/monitor_attendee_response.html`** (new) + **`monitor_event.html`** — the CSS-status cell links to the new page only for answered, non-purged registrants.
- **Tests** — `tests/test_monitor.py`: only-own/attributed rows, N/A preserved, rendered answers + verbatim + item note, roster link present, creator-only redirect, purged identity hidden, audit entry written. Green.

## 2026-07-06 (v1.84 — Spot Feedback #54: third "Mixed" column on the Verbatims page)
The Verbatims drill-down (`/reports/verbatims`) rendered two columns (Appreciate / Improve) and credited a "Mixed" comment to **both** sides. Feedback #54 asked for Mixed to be its own column. Change is scoped to this one page — the seven other `story_panel` callers keep the mixed-on-both-sides behaviour, gated behind a new flag.
- **`dashboard_insights.py` `story_panel`** — new `split_mixed=False` param. When `True`, a mixed-sentiment quote routes to its own `mixed` bucket group instead of being duplicated across `appreciate`/`improve`. Return dict always carries a `mixed` group (empty unless split) — additive, so existing consumers are untouched.
- **`app.py` `reports_verbatims`** — calls `story_panel(..., split_mixed=True)`.
- **`templates/verbatims.html`** — three-column grid (`repeat(3, 1fr)`, stacks ≤1050px); new "Mixed — good and bad" column (accent-tinted); updated the explanatory copy / badge tooltips that said Mixed shows "on both columns".
- **Tests** — `tests/test_verbatims_mixed_column.py`: split routes mixed to its own group (and off the two sides); default keeps it on both with an empty mixed group; the page renders all three column headers. Green.

## 2026-07-06 (v1.83 — Spot Feedback #56: per-submission "Responses" sheet in the SERVQUAL Excel)
The Type 2/3 raw-data Excel (`servqual_xlsx`) carried only consolidated figures (Dimensions, Summary, Respondent profile) — no way to see the numbers behind them. Feedback #56 asked for "raw data or actual responses (disaggregated per submission) for each activity or resource person". Adds a per-submission sheet, honouring the report's existing activity/RP scope narrowing.
- **`app.py`** — new pure helper `_servqual_response_rows(df, dim_map)`: one row per `response_id` with that respondent's own per-dimension means (each answered item counted once per person), their overall (mean of their dimension means), expectation (item A) and overall service quality (item C). `_servqual_official` attaches `block["responses"]` (metadata merged in), ordered oldest→newest. **Additive** — only the XLSX extract reads the key; DOCX/PDF/PPTX and the on-screen report ignore it.
- **`storage.py`** — new `response_context_for_ids(conn, response_ids)`: submitted time + human activity name + response-level comment for **every** response (unlike `verbatims_for_responses`, which is comment-only), so comment-less rows are still labelled.
- **`report_docs.py` `servqual_xlsx`** — renders the new "Responses" sheet (`#`, Submitted, Activity, the five dimensions, Overall, Expectation (A), Overall SQ (C), Comment).
- **Tests** — `tests/test_servqual_raw_responses.py`: the pure per-response maths, the rendered XLSX sheet, and an end-to-end Resource-Persons download narrowed to one activity (one distinct row per submission; every row labelled). Green.

## 2026-07-05 (v1.82 — scheduled backup was ON but never fired: seed the anchor)
The admin Backups schedule was `backup_enabled=1` (daily 02:00) on live yet had **never run** — every `backup_run` audit row was a manual "Back up now", `last_backup_at` was empty, and zero `(scheduler)`/`auto` rows existed. Root cause: `next_due(cfg, "")` treats an empty `last_backup_at` as "measure from now", which always lands on the *next future* slot, so `is_due` is `False` at every hour (verified) — and a manual backup never sets `last_backup_at`, so the anchor that would break the deadlock is never seeded. The in-process `_scheduler_loop` ticked every 60s but `is_due` was perpetually false. (Data was never at risk: the separate persistence loop `_snapshot_to_bucket` still writes `_auto` snapshots continuously, and the v1.80 GitHub off-site layer is independent.)
- **`backups.py`** — new `ensure_schedule_anchor(conn)`: seeds `last_backup_at` to `_now()` when the schedule is enabled but has never recorded a run (idempotent; no-op when off or already anchored). Seeds to *now*, not a past slot, preserving the "no surprise immediate run" intent while letting the first real slot fire. `next_due`/`is_due` math is unchanged.
- **`app.py` `_scheduler_loop`** — calls `bk.ensure_schedule_anchor(conn)` each tick before the due-check, so the **currently stuck live state self-heals** on deploy (no admin re-save needed). Once anchored, "stays due" semantics mean a slot missed while the Space is asleep runs on the next wake (e.g. first morning login) rather than being skipped.
- **`app.py` `admin_backups_settings`** — also anchors right after `write_config`, so newly enabling the schedule from the UI is immediately effective.
- **Tests** — `tests/test_backups.py`: `test_empty_anchor_is_never_due_without_seeding` (documents the deadlock at every hour), `test_ensure_schedule_anchor_seeds_then_it_fires` (seed → set → idempotent → due-after-past-slot incl. sleep catch-up), `test_ensure_schedule_anchor_noop_when_disabled`. Full `test_backups.py` green (33).

## 2026-07-05 (v1.80 — off-site (GitHub) backup history on the Backups page)
The off-site daily backup was moved off the user's Windows PC (a 20:00 Task-Scheduler job that only ran when the machine was awake + plugged in, so most evenings it silently skipped) to a **GitHub Actions workflow** in the private `jongsky25/css-is-db-backups` repo (`.github/workflows/offsite-backup.yml` + standalone `offsite_backup.py`): daily `0 3 * * *` UTC, it logs into live, takes a fresh snapshot, downloads + integrity-checks it, GPG/AES256-encrypts it (same recipe as the old PC mirror, so README's decrypt cmd still works), and commits the ciphertext via an orphan force-push (flat history). This change surfaces that layer **inside the app** so an admin can confirm an off-HF copy exists without leaving to the GitHub Actions tab.
- **`app.py`** — new **`POST /offsite-backup/ping`**: a token-gated machine callback the workflow hits after a successful push. Public path (added to `_PUBLIC_EXACT`; CI has no session) but authenticated by `hmac.compare_digest` of the `X-Backup-Token` header against `CSS_OFFSITE_PING_TOKEN` (503 if the env var is unset on the Space, 401 on mismatch). Writes one `audit_log` row (`action=offsite_backup`, actor `(github-actions)`, `target_id`=filename, summary with human size + short SHA), returns 204. Added `import hmac`.
- **`app.py` `admin_backups`** — now also reads `st.list_audit(conn, action="offsite_backup", limit=10)` and computes `offsite_last` + `offsite_stale` (naive-local `datetime.fromisoformat` vs `_tz.now_local()`, >48h ⇒ stale), passed to the template.
- **`storage.py`** — `_AUDIT_ACTIONS["offsite_backup"] = ("Off-site backup to GitHub", "Data & backups")` so the Audit log reads it in plain English. (History is stored in `audit_log` — reused, so **no schema migration**.)
- **`templates/backups.html`** — new "Off-site backups (GitHub)" panel above Schedule: green "Off-site copy current" / amber "overdue" badge, a plain-language explainer, a >48h stale warning pointing at the Actions tab, and a table of recent pings (when · encrypted file · "GitHub · encrypted").
- **Secrets/infra (outside the app repo):** `CSS_OFFSITE_PING_TOKEN` set as a GitHub repo secret; the workflow's final step `curl`s the ping (best-effort — a failed ping never fails the job). ⚠️ Requires the **same `CSS_OFFSITE_PING_TOKEN` added to the HF Space variables** for pings to be accepted. The old Windows Task "CSS-IS daily prod backup" is disabled.

## 2026-07-02 (v1.78 — report link on a closed activity's Manage page)
Closes Spot Feedback #49 (ray — "when i close the activity, the report should be automatically generated"), a follow-on to the v1.76 close-now button. Interpreted as a *prominent report link* (the report already exists and stays live the moment responses arrive — no stored snapshot needed). Invited/outside activities already showed a "View resource-person results →" link in their closed banner; the gap was the regular (bureau) Manage page, whose closed state (added in v1.76) offered only Reopen.
- **`storage.event_report_url(conn, event_id)`** (new) — the kind-aware report link for an activity, or None if it has no live forms. Chooses by where the responses actually are (a cheap `EXISTS` per form), not merely which forms exist, so it matches what `build_events` renders and never points at an empty per-activity report: Form-2 side answered → `/reports/activities/{repr}`; answered only on the RP side, or Form-3-only → `/reports?type=3&activity={repr}`. `repr` = min(non-archived form_instance id), the id both report routes match (same basis as `event_rp_results_url`).
- **`app.py` `_manage_ctx`** — now carries `report_url` (from the helper) and `responses_total` (`event_response_total`).
- **`activity_manage.html`** — the closed branch of the "Stop accepting responses" card leads with a prominent filled **"View the report →"** button (gated on `report_url and responses_total`), with Reopen demoted to a ghost button beside it. The close redirect already lands on this `#danger` card, so the report is right there after closing.
- **Tests** — `tests/test_monitor.py`: `test_event_report_url_follows_the_responses` (Form-2-answered → activity report; RP-answered-only and Form-3-only → Type-3; no forms → None) and `test_closed_activity_manage_shows_report_link` (link hidden while open, shown on close with the correct URL). outside_manage's closed-banner link is unchanged and already covered. Full suite green.

## 2026-07-02 (v1.77 — RP results from home + Type-3 Excel + remove a stray registrant)
Closes three Spot Feedback items, all orbiting the invited HRH PK Reorientation activity (event id 2, Form-3-only, 328 responses): #48 (ray — "why can't i still see the report for this?"), #44 (vcdulfo — "where's the excel option" on `/reports?type=3`), and #45 (vcdulfo — "is it possible to delete an entry?").
- **#48 — `app.py` home "concluded" feed.** An f2-less (invited / resource-person) activity linked to the generic `/activities/outside` list, so "open the report" never showed its numbers. Now it links to `/reports?type=3&activity={e['id']}` — the Type-3 report narrowed to that activity (`e['id']` is the build_events representative id, exactly the Type-3 Activity filter value; same target as `event_rp_results_url`). The feed filter already guarantees an f2-less row here has responses, so the link always has something to show. `home.html` tip updated ("Open the resource-person results"). Test `test_recently_concluded_links_resolve` rewritten to assert the invited branch links to the Type-3 report and that it's actually exercised by the delivered DB.
- **#44 — Type-3 raw-data Excel.** `report_docs.servqual_xlsx(sq, meta)` (new) renders the consolidated SERVQUAL payload — dimensions (Mean as a real number so the sheet is computable, plus the gap/verdict strings), the SERVQUAL summary, and the respondent profile — one table per sheet. `app.py`: added `xlsx` to `_REPORT_FMT`; `/reports/export` now dispatches `servqual_{fmt}` for `fmt=xlsx` on Type 2/3, and coerces a stray `type=1&fmt=xlsx` to docx (ARTA has no servqual_xlsx). `reports.html`: a "Raw data → Excel (.xlsx)" link in the Type-3 download menu (honors the org/period/activity scope). Tests: `test_reports_type3_xlsx_export`, `test_reports_type1_xlsx_coerced_to_docx`.
- **#45 — remove a registrant entry.** `storage.delete_attendee_entry(conn, event_id, attendee_id)` hard-deletes a roster entry **only when it has no responses** (returns `('ok'|'notfound'|'hasresponses', n)`). Deliberately NOT a response delete: `response`/`answer` are append-only under the durability high-water guard (`backups._HIGHWATER_TABLES`, MAX(rowid)), and a responded entry's ratings belong to the reports — same rule as "can't remove a speaker that has responses". Route `POST /monitor/{token}/attendee/{id}/delete` (creator/admin gate, audit `attendee_delete`, flash redirect); `monitor_event` takes a `flash` param. `monitor_event.html`: per-row "Remove" button (confirm) shown only when `not p.n_answered`, plus a flash banner + `.act-btn.danger`/`.flashmsg` styles. Tests: `test_delete_attendee_entry_rules`, `test_monitor_delete_attendee_route`, `test_non_creator_cannot_delete_attendee`.

## 2026-07-02 (v1.76 — close-now for every activity + "open until" on Monitor)
Closes Spot Feedback #46 (vcdulfo@doh.gov.ph — "how to close the survey without waiting for the end of window period") and #47 ("put details on until when it is open"). The close/reopen machinery already existed (`storage.close_event_now`/`reopen_event_now`/`event_is_closed`, v1.62) but was reachable only by invited ("outside") activities — the two POST routes gated on `_get_outside_event` (which enforces `event_kind == "outside"`), and only `outside_manage.html` rendered the buttons. A link-tree activity could only be stopped by hand-setting the window's "closes" date. The storage layer is already kind-agnostic (it joins `event_form`), so this is a surfacing change, not new mechanism.
- **`app.py`** — new `_get_manage_event` helper (get_event + `_can_manage_event`, no kind check; mirrors `_get_outside_event`'s (ev, None)/(None, redirect) shape). Renamed the two routes `outside_close`/`outside_reopen` → `activity_close`/`activity_reopen` (audit actions `event_close`/`event_reopen`) and pointed them at the new helper, so **any** activity's creator/admin can close/reopen. `_manage_ctx` now carries `is_closed`. The regular `monitor_event` render now passes `entry_window` + `is_closed` (read while the conn is open, before the finally).
- **Templates** — `activity_manage.html`: new "Stop accepting responses" card (id `#danger`, the anchor the routes already redirect to) with a **Close survey now** button (JS confirm) that swaps to **Reopen to make a correction** once closed — mirrors the outside-manage wording. `monitor_event.html`: a status line under the title — "Open until <date>" / "Open — no closing date set" / "Closed".
- **Tests** — `tests/test_monitor.py` (3 new: link-tree close↔reopen cycle + the manage button swap; ownership gate on close; the Monitor "open until"→"Closed" surface). Existing `tests/test_outside_activity.py` close/reopen tests still green against the generalized routes. Full suite green.

## 2026-06-30 (v1.75 — comment raffle now supports online activities)
Closes Spot Feedback #41 (ray@gmail.com — "online activities should also have a raffle draw"). The comment raffle (v1.47) was hard-gated to face-to-face responses, even though its claim-code identity model — built for anonymous walk-ins — already fits online entrants exactly: an online respondent sees a code on their thank-you screen and presents it (e.g. in chat) to claim. The fix removes the modality gate in all three places it appeared; no schema or new identity mechanism needed.
- **`storage.py` `raffle_pool`** — dropped the `COALESCE(fi.modality,'f2f')='f2f'` filter, so an online response with a real comment is now an eligible entry (still excludes archived forms, no-comment responses and demographic-only notes). Docstring + the two raffle section comments updated.
- **`app.py`** — both submit handlers (single-form `submit` and combined `/seq`) previously issued a claim code only when `ctx.modality == 'f2f'`; now they issue it whenever the activity's raffle is on, so online raters get their ticket on the thank-you screen. Section comment broadened.
- **Templates** — copy de-scoped from "face-to-face" on `activity_manage.html` / `outside_manage.html` (the raffle card hint) and `raffle.html` (the empty-pool message, server- and client-side). The raffle card was already shown for online activities — only the wording implied otherwise.
- **Tests** — `tests/test_raffle.py`: flipped `test_pool_excludes_online_responses` → `test_pool_enters_online_responses` (online comments now pooled), added `test_thanks_shows_claim_code_for_online_submission` (online `/seq` thank-you renders a 5-char code), updated the module docstring. Full `test_raffle.py` green (18); full suite green.

## 2026-06-30 (v1.74 — inline Archive on the home "Ongoing" feed)
Closes the discoverability gap behind Spot Feedback #42/#43 (ray@gmail.com — two "archive. test data" notes filed from the home Ongoing strip). Archiving an activity already worked from several places (the Recent-activities strip for standalones, the invited-activity manage page, and the `/reports/activities` Edit/merge bulk action), but NOT from the read-only "Ongoing — CSS collecting" feed where a stray/test activity is most often spotted — so it read as "no way to archive from here". This adds the control where the feedback was filed.
- **`app.py`** — new route `activity_inline_archive` → `POST /activities/instance/{fid}/archive` (`create_activity`-gated). Resolves the feed row's form-instance id to the right scope: a row backed by an `event_form` archives EVERY form the event bundles (the Type-2 review + its speaker Type-3s) so the whole activity leaves the feeds; a standalone form archives just itself. Reuses the harmonize journal (`aa.ensure_backup()` + `aa.new_batch()` + `aa.archive_activities`, same auto-backup + per-change undo as the Edit/merge bulk archive), then `invalidate_atoms()`. Redirects home.
- **`templates/home.html`** — each Ongoing row is now wrapped in the existing `.mine-row` flex shell for admins (`mine_all`), with an inline `.mine-arch` Archive form beside the link (confirm dialog; reuses the same CSS as the Recent-activities strip's Archive button — no new styles). Admin-only; the route itself still enforces `create_activity` as defence in depth.
- **Tests** — `tests/test_home_feeds.py` (3 new: standalone archive from the feed hides the row; bureau-event archive covers every bundled form; a viewer is blocked by the permission gate). Full suite green.

## 2026-06-26 (v1.73 — durability: persist-loop watchdog + honest /ops stall detection)
Closes the two blind spots behind a live durability incident (2026-06-26): the background persist loop had stopped saving for ~5h while `/ops` still showed green. Root cause — a snapshot worker hung on bucket (FUSE) I/O froze the loop, so the recorded state stayed at the last `ok` forever (no skip/fail recorded → card never went red). No data was lost (live held the richest copy + was pulled off-site); fixed live via Back-up-now → Restore (`reset_highwater`) → restart. These changes prevent recurrence. Full incident record in the `hf-staging-data-loss` memory note.
- **`app.py` `_persist_loop`** — each snapshot attempt is now bounded by `CSS_PERSIST_OP_TIMEOUT` (default 30s) via `asyncio.wait_for`, so a stalled bucket write can no longer wedge the loop forever; on timeout it records a `fail` (→ /ops red) and keeps ticking. Added a per-tick monotonic **heartbeat** (`last_tick_mono`) written at the top of every iteration, and unified the "last saved data_version" into `_PERSIST_HEALTH["saved_ver"]` so the health view can tell whether live has unsaved changes.
- **`app.py` `_persist_health_view`** — now flips the /ops durability card **RED independently of the recorded state**: if the loop has stopped ticking, OR unsaved changes have gone unwritten, for longer than `CSS_PERSIST_STALL_TICKS` ticks (default 5). This is what was missing on 2026-06-26 — a frozen `ok` state read green while nothing was being saved.
- **`backups.py`** — new pure `persist_is_stalled(...)` (the testable stall rule: loop-not-ticking OR unsaved-too-long, with a `last_tick is None` → not-stalled guard so a just-booted app isn't flagged). Note: a timed-out worker thread may still be stuck on the syscall, but the loop survives and reports — degrading to "loop alive + card red" instead of a silent freeze.
- **Tests** — `tests/test_backups.py` (4 new: `persist_is_stalled` not-before-first-tick / loop-stopped-ticking / unsaved-unwritten / never-saved-window) + new `tests/test_persist_health.py` (4: card green when healthy, red when the loop stops ticking, red when unsaved changes go unwritten, hidden when persistence off). Full suite green.
- **Follow-up still open:** a true bucket lock for the sub-second split-brain window (what advances the high-water mark above a surviving snapshot in the first place) — unchanged from before.

## 2026-06-26 (durability — high-water guard now protects login accounts)
Root-cause of the "user accounts/passwords reset on update" report. Persistence itself is healthy (the live Space mounts the durable bucket `equityinhealth/office-connect-data` at `/data`; the persist loop self-snapshots and the newest snapshot holds all current accounts — verified). The realized resets traced to a snapshotter **wedge** (a ~2-day gap in bucket snapshots, June 23→25 — the same incident as the June-24 loss): while wedged, the newest *valid* snapshot goes stale, so a deploy/restart during the stall restores stale state and accounts revert. The v1.63 self-heal (orphaned-high-water realign) + pre-deploy backup gate already address the wedge; this closes the account-specific blind spot.
- **`backups.py`** — added `admin_user` to `_HIGHWATER_TABLES`. The boot stale-view guard (`_await_fresh_snapshot`) and the persist-loop guard (`live_db_is_stale`) only tracked survey/audit/feedback tables, so a new account/password (which touches *only* `admin_user`) left the high-water mark unchanged — a stale FUSE view could restore a pre-account snapshot and the guards wouldn't notice. Now an account change advances the mark, so such a restore is caught (crash-loop + self-heal) instead of silently resetting accounts. Safe because production never hard-deletes accounts (deactivation = `UPDATE active=0`, rowid unchanged → monotonic).
- **Tests** — new `tests/test_backups.py::test_highwater_protects_accounts` (real, un-patched `_HIGHWATER_TABLES`): an account-only insert advances the mark and a snapshot predating the account reads as stale. Full `tests/test_backups.py` green (24).
- **`report_docs.py`** — guarded a pre-existing None-gap crash surfaced by the pre-deploy test gate: `_na_sq_summary` + two PPTX builders did `g['label'].lower()` under only an `if g:` check, but a partial Form-2 activity (perception rated, expectation item A blank) yields `gap={'label': None, …}` (truthy) → `AttributeError` that 500'd the event PDF/DOCX/PPTX export. Now guarded `if g and g.get("label")` (same "None gap = neutral" treatment as the v1.69 activity.html fix). Unblocked `test_routes.py::test_dashboard_event_export_all_formats`; full suite green.
- **Shipped together** as part of the v1.72 deploy (the staged RP-activity-filter release). A pre-existing stray `_backups/scheduled/css_is_20260625_100908_auto.db-shm` sits in the bucket — harmless (ignored by the snapshot name regex), noted not deleted.

## 2026-06-25 (v1.69 — Invited-activity → RP-results deep link + activity-report None-gap fix)
Two changes. (a) Non-bureau RP-CSS navigation (spec `docs/OUTSIDE_RP_RESULTS_NAV_PLAN.md`): an outside activity is Form-3-only, so it has no Form-2 SERVQUAL report — its scores live only in the Type-3 report's Activity filter (v1.65), with nothing linking there from the activity. (b) A latent 500 on the per-activity report for partial Form-2 data.
- **`storage.py`** — new `event_rp_results_url(conn, event_id)`: returns `/reports?type=3&activity=<min non-archived form_instance id>` (= the `build_events` representative id the Activity filter matches, NOT `event.id`), or None when the event has no live RP forms.
- **`app.py`** — `outside_events_index` attaches `e["rp_results_url"]` per outside event. `_outside_manage_ctx` `report_url` switched from `/reports/activities/{ev['id']}` (404'd for ALL outside events — f2-less AND event.id ≠ build_events id) to `event_rp_results_url`.
- **`templates/outside_events.html`** — new "View resource-person results" action link (shown when `rp_results_url and responses`). **`templates/outside_manage.html`** — the closed-bar link relabelled "View resource-person results →", guarded on `report_url and responses_total`.
- **`templates/activity.html`** — the dimension-table gap cell guards `d.gap is none` → neutral 'zero' class (was `None > 0.005` → `TypeError`, 500-ing the report when a Form-2 response answered perception items but not the expectation item A; `gap_shown` already rendered "—"). Only the one template line had this unsafe comparison.
- **Known build_events quirk (noted, not fixed):** an F3-only outside event is named after its first F3 topic, not the event title — so the Invited-events page (event title) and the RP report it links to (F3 topic) can label the same activity differently.
- **Tests** — `tests/test_outside_rp_results_link.py` (4: helper min-id/excludes-archived/None; page link responses-gated; linked id narrows the report; manage page links to RP results not the 404 report) + `tests/test_activity_report_none_gap.py` (1: perception-only F2 renders 200 with a "—" gap). Updated `test_outside_activity::test_close_hard_locks...` (asserted the old broken link). Full pytest 515 green.

## 2026-06-25 (v1.68 — Invited/outside-event visibility: dedicated list + home "Recently concluded" + Invited badge)
Addresses Spot Feedback #29/#30 (non-bureau activities missing from the home strip / Monitor) and the root cause behind a "missing" June-17 invited activity (data was always intact; it was a visibility gap). A concluded outside event used to fall off every dashboard surface except `/reports/activities`: the Monitor is lifecycle-filtered to upcoming/ongoing, and the home "Recently concluded" strip was Form-2-only (outside events are often Form-3-only). Spec: `docs/OUTSIDE_EVENTS_VISIBILITY_PLAN.md`. Three layers, all reuse the existing `lifecycle_of` / `build_events` — no storage-layer change.
- **Layer ① — dedicated page.** New `app.py` route `outside_events_index` → `GET /activities/outside` (`manage_event`-gated; admin sees all, section_manager sees own). Lists ALL outside events across every lifecycle via `st.list_events(created_by=owner)` (no lifecycle filter) filtered to `event_kind=='outside'`, each enriched with `st.event_response_total`. New `templates/outside_events.html` (lifecycle badge + "Invited" badge + response total; links to Manage/Monitor by token — NOT the report, since `/reports/activities/{id}` 404s on f2-less events and build_events uses a synthetic id ≠ event.id). New nav item key `outside` ("Invited events") under Manage in `NAV_GROUPS` (also feeds the Ctrl-K search index). `templates/monitor.html` invited section now links concluded ones to the page.
- **Layer ② — home "Recently concluded".** `home()` concluded filter relaxed from `e.get("f2")` to `(f2 OR respondents)`, so invited/F3-only activities with responses appear. Each item now carries `url` (report for f2 events, else `/activities/outside`) + an `invited` flag; `home.html` concluded JS uses `a.url` and renders an amber "Invited" badge. `tests/test_home_feeds.py::test_recently_concluded_links_resolve` updated to follow each item's `url` (the old contract assumed every concluded id → a report).
- **Layer ③ — badge + monitor hand-off.** Amber "Invited" badge on the home "Your recent activities" strip (`home.html`, keyed on `a.event_kind=='outside'`, already carried by `activities_by_creator`). DECISION: KEPT the 7-day "Your recent" window (the deliberate v1.10 narrowing) rather than widening to 30 — ①/② already give invited events their homes.
- **Tests** — new `tests/test_outside_events_page.py` (5: concluded invited event shows here but NOT on the Monitor; upcoming shows; scoped to outside-only; auth gate; home strip badge) + `tests/test_home_concluded_invited.py` (2: invited F3 appears + links to the list; real bureau f2 events keep their report link). Full pytest exit 0.
- **Known latent bug (out of scope, flagged separately):** `templates/activity.html:274` 500s on a None Form-2 dimension gap (partial responses); real data renders fine today.

## 2026-06-25 (v1.67 — Audit log: plain-language actions + a "what's been happening" breakdown)
Addresses Spot Feedback #27 (ray@gmail.com) — "a bit of an insight on the audit log would do good? plan". v1.60 had already added the at-a-glance counts (today / week / all-time / busiest / most-common); this makes the log itself readable to a non-technical admin and adds the recent-activity distribution.
- **`storage.py`** — new `_AUDIT_ACTIONS` map (≈60 codes → `(label, category)`), `audit_label(code)` (plain English; **humanize fallback** for any unmapped/new code so it's never blank), and `audit_category(code)` (→ "Other" when unmapped). New `audit_breakdown(conn, days=7, top=6)`: ranked action types (`by_type`, each with label + category + count + bar `pct`) and busiest actors (`by_actor`) over the PH-local window; returns None for an empty window. `audit_insights` now also carries the friendly `label` on its `common`/`last` entries.
- **`app.py`** — registered Jinja filters `audit_label` / `audit_category`; `admin_audit` route now also passes `breakdown`.
- **`templates/audit.html`** — the entries-table action chip now shows the friendly label (raw code kept as the `title=` tooltip + still the filter value, so filtering/forensics are unchanged), tinted by a coarse category grouping (blue = sign-in/feedback · amber = accounts/data/sharing · green = activities/comments/directory · neutral = other), all token-backed/dark-mode safe. The at-a-glance "most recent"/"most common" lines use labels; the filter dropdown lists friendly names (raw value preserved). New "What's been happening · last 7 days" panel: ranked action kinds with count bars + busiest people. Decorative bars are pure CSS; no new color tokens.
- **Scope:** read-only presentation + aggregation over the existing `audit_log`; no schema change, no change to what gets recorded or to the hash-chain integrity check. `/admin/audit` stays admin-gated.
- **Tests** — new `tests/test_audit_insights.py` (5): `audit_label` known + humanize-fallback + empty; `audit_category` incl. unmapped→"Other"; `audit_breakdown` ranks types/actors with labels and a full top bar over the 7-day window; empty-window → None; the page renders the friendly "Signed in" label. Full pytest exit 0.

## 2026-06-25 (v1.66 — /ops: live "who's using it" + "lately" reads)
Addresses Spot Feedback #26 (ray@gmail.com) — "plan for additional layman data. like current users? etc…" on `/ops`. v1.60 had added static all-time inventory counts; this adds the live "who's on the system" + recent-activity signals those counts don't give. No schema change — derived from the audit log (sign-ins) and existing timestamp columns.
- **`storage.py`** — new `usage_pulse(conn)`: from `audit_log` it returns `active_now` (distinct actors with ANY audit action in the last 15 min — a soft presence proxy, since there is no live session store), `signed_in_today` / `signed_in_week` (distinct `action='login'` actors, PH-local windows), `last_login`, and `recent_logins[]` (last 6). From the cheap timestamp columns it returns the "lately" deltas: `responses_today` / `responses_week` (`response.submitted_at`), `activities_week` (`event.created_at`), `participants_week` (`attendee.created_at`). All naive-local stamps, so `date(ts)` and lexical `>=` stay correct (tzutil strips tzinfo — no UTC-shift). Cheap COUNT/GROUP, computed on demand.
- **`app.py` `ops()`** — calls `st.usage_pulse`; builds two plain-language card rows (`people`, `lately`), a `last_login_line`, and a `recent_logins` list (timestamps via `_humandt`), passed to the template.
- **`templates/ops.html`** — two new `.panel`s after "What's in the system": **"Who's using it · sign-in activity"** (the people cards + "Last sign-in:" line + a recent-sign-ins list) and **"Lately · last 7 days"** (the freshness cards). Reuses the existing `.signals`/`.sig` card styles (dark-mode safe); one small `.signins` list style added; the recent list carries an `aria-label`. "Active now" is labelled "in the last 15 min" so it never overpromises real-time presence.
- **Privacy/scope:** `/ops` is `manage_users`-gated (admins only) and `/audit` already shows actor names, so surfacing sign-ins here adds no new exposure. Deliberately NOT adding a session/heartbeat store — the 15-min audit-activity proxy is the honest signal without new infrastructure.
- **Tests** — new `tests/test_ops_usage.py` (4): `usage_pulse` window arithmetic (active-now vs stale vs today vs week, distinct-actor counting, newest-login ordering), the "lately" 7-day deltas, the empty-system zero case, and that `/ops` renders the new panels for an admin. Full pytest exit 0.

## 2026-06-25 (v1.65 — Resource-person report: filter by a single activity)
Addresses Spot Feedback #28 (gbcanoy@doh.gov.ph) — "filter RP Responses by Activity … to quickly locate and review responses for a specific activity." The Type-3 (Resource Persons) report at `/reports?type=3` previously scoped only by Scope (org) + Period; there was no way to isolate one activity.
- **`app.py`** — new `_rp_activity_options(conn, atoms)`: reuses the memoized `di.build_events(...)` (same source as `/reports/activities/{id}`) to list events that carry resource-person (F3) data, each with its `instance_ids`. So the dropdown labels/ids match the rest of the activities views.
- **`app.py` `reports()`** — new `activity` query param (RP-only; coerced to `""` for types 1/2). When set, the atoms fed to `eng.scope(..., survey_type=3)` are narrowed to that event's form instances *before* scoping, so the overall score, per-dimension grid, respondent count and verbatims all reflect the one activity. `activity_opts` + `sel_activity` are passed to the template; the selected activity's name is appended to `scope_label`.
- **`app.py` `reports_export()`** — same `activity` param threaded through for download parity (Word/PDF/PPTX), narrowing the same way and reflecting the activity in the document's scope line.
- **`templates/reports.html`** — an "Activity" `<select>` (default "All activities") added to the filter bar, shown only for `rtype == 3`; auto-submits like Scope/Period and is carried on the existing filter form so it composes with org/period. `report_downloads(...)` macro gained an `activity` arg and threads `&activity=` into each export link (Type-3 call site passes `sel_activity`).
- **Scope/composition:** the Activity filter stacks with Scope + Period (intersection); switching report type via the tabs drops it (the tab links don't carry `activity`). Backlog activities not in the `event` table follow build_events' existing grouping, same as every other activities view.
- **Tests** — new `tests/test_rp_report_filter.py` (2): two bureau activities with distinct response counts → the dropdown lists both, selecting one narrows the report to exactly its respondents (3 vs 2) and marks the option selected; a stray `activity` param on Type 1/2 is ignored (200, no narrowing). Full pytest exit 0.

## 2026-06-25 (v1.63 — persistence self-heal for the orphaned-high-water deadlock + loud /ops durability health)
**Incident (2026-06-25, diagnosed from live container logs).** A ~2-day SILENT persistence outage lost June 24 data (CSS responses + activities + Spot Feedback #28–37). Live logs showed `[persist] SKIP snapshot (timer): live DB is BELOW the high-water mark …` repeating non-stop: the v1.61 stale-lineage guard was WEDGED. The bucket's monotonic high-water mark (HWM) had been advanced ABOVE every surviving snapshot (a split-brain peer raised it, then its snapshot was lost/reverted), so the live container — booted from the best surviving (lower) snapshot — was permanently "stale" and refused to EVER auto-snapshot. Manual `make_backup` bypasses the guard (how the recovery snapshots succeeded) but `write_highwater` is monotonic, so it couldn't lower the mark; only a deliberate restore (`reset_highwater`) could. A deploy restart then restored the last good (June 23) snapshot and finalised the loss. Distinct from v1.55 (seed-revert) and v1.61 (stale-but-valid SNAPSHOT revert): here NO snapshot was written for ~36h, silently.
- **Immediate (no deploy):** unblocked live by scripting Back-up-now → Restore (calls `reset_highwater`), realigning the mark down to current data; a fresh `_auto` snapshot appeared 2 s later, confirming the loop resumed.
- **`backups.py`** — new pure `persist_action(live_marker, best_snapshot_marker, highwater)` → `ok` / `skip` / `realign`. `skip` only when a snapshot strictly RICHER than live exists (the original protection is intact); `realign` when live is below the mark but NO snapshot beats it = the mark is orphaned.
- **`app.py` `_snapshot_to_bucket`** — uses `persist_action`: on `realign` it `reset_highwater(DB)` + snapshots (self-heals the deadlock within one ~60 s tick) instead of skipping forever; on `skip` it still protects the good backup. New `_PERSIST_HEALTH` + `_persist_note()` track last-ok / state / consecutive-bad.
- **`app.py` `/ops`** — `_persist_health_view()` adds a plain-language "is live data being saved right now?" line to the System-health "is the data safe?" list, and a `down` state escalates the overall verdict to RED — so a silent outage is now impossible to miss.
- **`deploy_hf.py`** — NEW pre-deploy redundant-backup gate (separate, already in place): forces + verifies a fresh live snapshot before the upload/restart, aborts if it can't (`--skip-backup` / `CSS_DEPLOY_SKIP_BACKUP=1` override).
- **Recovery tooling (local-only, NOT shipped):** `refile_lost_feedback.py` re-POSTed Spot Feedback #28–37 to live (annotated `[RECOVERED …]`; live back to 37). June 24 survey responses + activities are unrecoverable (in no snapshot). Lost-feedback text saved at `_backups/LOST_feedback_28-37_captured_2026-06-25.md`.
- **Tests** — `tests/test_backups.py` +3: `persist_action` ok/skip/realign rule table. Full pytest exit 0.

## 2026-06-25 (v1.62 — closing an invited activity is now a real hard-stop: locks entry + details, surfaces report)
Addresses a Spot Feedback cluster (#31 "concluded events should not be editable", #33 "[Close] should deactivate + generate reports", #34 "closed but input fields still open") on invited/outside activities. Before, `Close` only set `close_at` (gating the public link); paper entry via `/encode` was never enforced, and the manage page stayed fully editable.
- **State model (no migration):** "closed" = every non-archived form of the event carries `encoding_locked=1`, set alongside `close_at` by `close_event_now`. Reused existing columns. Decision: gate paper entry on the explicit `encoding_locked` signal, NOT a merely-elapsed window — so legitimate back-keying of never-formally-closed events is preserved (no surprise regression on link-tree events).
- **`storage.py`** — `close_event_now` now also sets `encoding_locked=1` (hard-stops paper entry + drops the form from the encode picker, which already filters `encoding_locked`). New `reopen_event_now` (clears `close_at` + `encoding_locked`) and `event_is_closed` (true iff ≥1 non-archived form and all are locked). `get_form_context` now returns `encoding_locked`.
- **`app.py`** — new `POST /activities/{event_token}/reopen` (outside-event guarded, audited as `outside_reopen`). `_outside_manage_ctx` adds `is_closed` + `report_url` (`/reports/activities/{id}`). `submit_encode` now refuses a locked form (409, re-renders the form in its locked state) — server-side teeth for the data-integrity path. `encode_form` GET passes `locked`.
- **`templates/encode_form.html`** — locked forms show a red "this activity is closed" notice and the entry form is replaced by a back-link (no submit). The old window-closed "paper entry still allowed" note is retained for the elapsed-window-but-not-locked case.
- **`templates/outside_manage.html`** — when closed: a top banner with **View activity report →** + **Reopen to make a correction**; the editable cards (speakers, dates, window, raffle) are wrapped in a `[inert]` `locked-region` (dimmed, non-interactive) with a 🔒 flag; the danger-zone Close button is swapped for an "already closed → use Reopen" note. Close confirm copy updated to say it locks details + paper entry. (Manage-field lock is client-side `inert`; the actor is the authorized creator/admin and Reopen is one click, so no per-route server guard was added — the paper-entry block, which is the integrity-critical surface, IS server-enforced.)
- **Scope:** outside/invited activities only (the `/manage` Close button is outside-only). Link-tree activities are unaffected unless globally locked via the existing admin "Close all to encoding".
- **Tests** — `tests/test_outside_activity.py` +2: close hard-locks paper entry (encode GET shows locked state, POST → 409, records nothing) + flags `event_is_closed` + manage page shows banner/report-link/Reopen/inert lock and drops the Close button; reopen reverses it (entry accepted again). Drive-by: fixed a date-drift time-bomb in `tests/test_my_activities.py::test_home_renders_the_strip_for_its_creator` (hardcoded `2026-06-16` had fallen outside the home strip's 7-day window now that "today" is past it → now dates relative to `_today_local()`). Full pytest exit 0.

## 2026-06-22 (v1.56 — read-only Spot Feedback JSON endpoint + local `feedback.py` reader)
Closes the "download the whole DB just to read feedback" loop. Live data lives on the HF bucket (not reachable via the HF API), so reviewing Spot Feedback meant pulling the 21 MB DB from `/admin/backups` by hand. New thin path lets the current feedback be read from a local tool with no download.
- **`app.py`** — new `GET /admin/feedback.json` (gated by the existing `triage_feedback` permission, read-only, mutates nothing). Returns `{generated_at, statuses, counts, total, filter, items[]}`; each item carries `id/created_at/updated_at/submitter/status/page_url/element_selector/message/admin_note/archived_at` plus its `updates[]` reply trail (reuses `st.list_spot_feedback` + `st.list_feedback_updates`). Optional `?status=` filter. Region blob intentionally omitted (noisy).
- **`feedback.py`** (NEW, local-only — NOT in deploy_hf ALLOW, never ships) — logs in via `pull_backup`'s session machinery, GETs the JSON, prints a readable digest (`--json` for raw, `--status`, `--open` to hide Done/Won't-fix). Creds resolve flags → env → gitignored `.env.local` → prompt.
- **`.env.local`** (NEW, gitignored) — holds `CSS_ADMIN_USER`/`CSS_ADMIN_PASS`/optional `CSS_BASE_URL` so repeat checks need no re-entry. `.gitignore` updated.
- The loop is now: `python feedback.py` (read live) → edit → `python deploy_hf.py` (ship) — all without a manual DB download.

## 2026-06-22 (v1.55 — boot-restore hardening: stop a slow bucket mount from reverting live data)
**Incident root cause.** The live Space restarted (~3:10 PM); on boot `_ensure_live_db()` called `bk.newest_valid_snapshot()`, which returns `None` for BOTH a genuinely empty bucket AND a `/data` FUSE mount that simply isn't readable yet. The old code treated `None` as "first boot", copied the shipped seed (`css_is.db`, where `DB == SEED_DB` since `CSS_DB` is unset) over the live DB, and the snapshotter then wrote that seed back and pruned the good snapshots (`PERSIST_KEEP=24` minute-snapshots → a very shallow window). Net effect: live data silently reverted to an older state and recent feedback/account changes were lost. Mount config was fine (`CSS_PERSIST_DIR=/data` set; Dockerfile runs as root) — the bug was the boot path conflating "not ready" with "empty".
- **`backups.py`** — new boot-safety helpers, all unit-tested:
  - `bucket_writable(d)` — real create+read+delete probe (the only reliable "is the FUSE mount actually here?" test; `isdir()` lies during mount lag).
  - `wait_for_bucket(d, timeout=60, interval=2)` — block until the mount proves writable, riding out FUSE lag at boot.
  - `snapshots_present()` — any snapshot file present (valid or not), to tell "empty bucket" apart from "snapshots exist but none open".
  - `boot_decision(...)` — pure decision function returning `restore` / `seed` / `abort`. Only seeds on a POSITIVELY confirmed first boot (mount ready + truly empty + never initialized) or an explicit `CSS_PERSIST_ALLOW_SEED=1` override; otherwise aborts rather than overwrite live data.
  - `prune_backups(keep, keep_daily=0)` — additive deep-retention: also protects the newest snapshot of each of the last `keep_daily` days, so a burst of writes can't churn the 24 minute-snapshots and rotate every older restore point off the bucket. Default 0 keeps the admin schedule's behaviour unchanged.
- **`app.py`** — rewrote the `PERSIST_DIR` branch of `_ensure_live_db()` to: wait for the mount, then act on `bk.boot_decision(...)`. On `abort` it `raise`s (the container crash-loops visibly and self-heals on the next boot once the mount is back — far safer than a silent revert). New `_persist_sentinel()` / `_persist_mark_initialized()` write a `/data/.css_initialized` marker on every good boot so a later empty bucket is recognised as an anomaly, not a first boot. New env knobs: `CSS_PERSIST_KEEP_DAILY` (14), `CSS_PERSIST_BOOT_WAIT` (60), `CSS_PERSIST_ALLOW_SEED`. The snapshot loop now calls `prune_backups(PERSIST_KEEP, keep_daily=PERSIST_KEEP_DAILY)`.
- **Tests** — `tests/test_backups.py` +4: `boot_decision` rule table (restore/seed/abort/override), `prune_backups` daily-anchor retention, `bucket_writable`/`wait_for_bucket` happy + timeout paths, `snapshots_present`. Existing prune test unchanged (default `keep_daily=0`). Full pytest exit 0.

## 2026-06-22 (v1.54 — locale-proof date display + resource person optional for bureau activities)
Two reported issues. (1) A Spot Feedback report (rsmanaloto@doh.gov.ph) flagged `#event_date` on `/create` showing the wrong order — a US-locale desktop rendered the native `<input type=date>` as mm/dd, a dd/mm machine as dd/mm. The stored value was always correct ISO; the confusion was purely the locale-bound display, which the page can't override. (2) A bureau-organized activity was forced to have ≥1 resource person even though it produces a Form 2 event review on its own.
- **`static/js/app.js`** — new zero-dependency date-field enhancer (final IIFE). Every `<input type=date>` keeps its native control (calendar, min/max, keyboard, mobile picker, ISO value) but is made invisible and overlaid with a FIXED, locale-independent `22 Jun 2026` display; inputs with `data-echo` also get a spelled-out `Monday, 22 June 2026` line below. A `MutationObserver` on the `type` attribute drops the overlay (`.raw`) when the "Add specific time" toggle swaps the field to `datetime-local`.
- **`static/css/app.css`** — `.datefix` / `.datefix-disp` / `.datefix-echo` styles using existing tokens (`--surface`/`--ink`/`--line`/`--accent`/`--ring`); verified in dark mode. app.css `?v=` → `20260622b`.
- **`templates/form_create.html`** — `event_date` + `end_date` carry `data-echo` + `data-placeholder`; resource-person section 4 reworded as "optional for a bureau-organized activity", and the bureau/outside type hints updated. app.js `?v=` → `20260622b`.
- **`app.py` (`create_survey`)** — the "Add at least one resource person" validation now applies only when `event_type == "outside"`; a bureau activity with no speakers creates its lone Form 2 + event link tree as before.
- **`static/js/sw.js`** — `CACHE_VERSION` → `v1.54-a` so installed survey PWAs purge the old app-shell and pick up the new CSS/JS.
- **Tests** — new `tests/test_bureau_no_rp.py` (2): a no-RP bureau activity persists with a lone Form 2; an outside event with no RP is still rejected. Affected suites (outside/date/event) green; full pytest exit 0.

## 2026-06-22 (v1.53 — UX #21 deploy 2: SR data-table fallback for Pulse, Participation & Verbatims charts)
Finishes UX #21 (WCAG 1.1.1). Extends the deploy-1 `chart_table()` macro + `.sr-only` utility to the remaining dashboard data charts. No CSS/asset change (utilities already shipped in v1.52) — templates + one builder only.
- **`dashboard_insights.py` (`_count_geom`)** — additively returns `main_table` (period × count, missing periods as “—”), mirroring the `_svg_geom` change. Covers `volume_view` + `engagement_trend`; `coverage_trend` already routes through `_svg_geom` so it inherited its table in v1.52.
- **`templates/participation.html`** — the shared `linechart(G, …)` macro now emits `chart_table(ytitle, ['Period', ytitle], G.main_table)` after each `</svg>` (guarded on `G.main_table`), so every volume / coverage / engagement line gets its table in one place.
- **`templates/pulse.html`** — each vital tile's sparkline now ships a small SR table built from `t.micro_pts` (period × shown value), captioned with the tile title.
- **`templates/verbatims.html`** — the 3-way tone chart's SR table combines the appreciation `main_table` with the improve/mixed `dims_table` (both already on `sent.breakdown.geom` from the v1.52 `_svg_geom` change) into one Period | Appreciation | Areas to improve | Mixed table — no new Python.
- **Classification (no change needed):** the `role="img"` SVGs on `result.html`, `login.html`, `arta_link.html` are the decorative Equity-in-Health logo, and `outside_manage.html`'s is the 🔒 lock status glyph — all already have correct `aria-label`s; none is a data chart.
- **Tests** — `tests/test_a11y_charts.py` extended (+3): `_count_geom` table shape + “—”, the Verbatims table is genuinely 3-way (4 headers, 3 tone cells/row), and Pulse/Participation/Verbatims each ship an SR table where a chart renders. Full pytest exit 0.

## 2026-06-22 (v1.52 — UX #21 deploy 1: skip-to-content link + SR data-table fallback for Trends charts)
WCAG 2.2 work (DOH/government deployment). Two gaps closed: **2.4.1 Bypass Blocks** (a keyboard skip-link) and **1.1.1 Non-text Content** (a screen-reader data table behind each chart). This is the first of two deploys — Trends charts only; the remaining dashboard charts (pulse / verbatims / participation) follow in deploy 2.
- **`static/css/app.css`** — new `.sr-only` utility (clip-rect; visually hidden but kept in the a11y tree) + `.skip-link` (fixed, off-screen via `translateY(-160%)` until `:focus` brings it on-screen). Reuses `--accent`/`--on-accent`/`--ring` (already AA-audited), so `tools/contrast_check.py` needs no new pairs.
- **`templates/dash_layout.html` + `public_layout.html`** — `<a class="skip-link" href="#maincontent">` as the first body child; content target is now a `<main id="maincontent" tabindex="-1">` landmark (`.wrap` is a bare class selector — div→main is style-safe; verified no `.wrap >`/`.pub-wrap >` child rules). app.css `?v=` → `20260622a`.
- **`templates/_components.html`** — new `chart_table(caption, headers, rows)` macro rendering an `<table class="sr-only chart-data">` with `<caption>` + `scope`'d headers. The chart SVG keeps its `role="img"` short summary; the table is the full navigable fallback.
- **`dashboard_insights.py` (`_svg_geom`)** — additively returns `main_table` (period × value) and `dims_table` (period × one column per area/segment, missing points as “—”), built from the already-windowed, index-aligned `vseries`/`vdims`. One change covers all five Trends charts (main, low-raters, by-area, segment-split, comment-sentiment), which all route through `_svg_geom`.
- **`templates/trends.html`** — each of the five charts now emits its SR table after `</svg>` via the macro (single-series → `*.main_table`; multi-series → `*.dims_table`, guarded for the no-dims case).
- **`static/js/sw.js`** — `CACHE_VERSION` → `v1.52-a` so installed survey PWAs purge the old app-shell and pick up the new CSS.
- **Tests** — new `tests/test_a11y_charts.py` (5): `_svg_geom` table shape + “—” for nulls + no dims_table when single-series; skip-link present in both layouts; Trends charts always ship their SR table. Full pytest exit 0.

## 2026-06-22 (v1.51 — Directory email edits re-point the linked account's login)
Pilot bug: editing a BLHSD staff member's email in the Directory did not change the email they sign in with, so reactivating or resetting their account kept reverting to the old address. **Root cause:** the login email lives in `admin_user.username`, copied **once** from `resource_person.email` at account-creation time (`_provision_account`); `update_rp` only ever wrote `resource_person.email`, so the two diverged silently.
- **`storage.py`** — new `set_admin_username(conn, user_id, username)` helper (one-line `UPDATE admin_user SET username=?`), placed beside the other `admin_user` mutators.
- **`app.py` (`POST /directory/person/{id}/update`)** — after `update_rp`, if the person has a linked account, re-point its `username` to the new directory email. Guarded: only when the new email is **valid, changed, and not already owned by another account**. On a collision the directory edit still saves but the login is left intact and a warning is surfaced via `?err=` on the redirect; clearing/invalidating the email leaves the existing login untouched (never blanks a username). Each successful re-point is audited as `change_login_email` (before/after).
- **Tests** — new `tests/test_account_email_sync.py` (3): email edit re-points the account login (old email no longer resolves), collision leaves both logins unchanged + warns, clearing the directory email keeps the existing login. Related directory/user/account/monitor suite green.

## 2026-06-22 (v1.49 — Multi-day activity date range + PDF-only Certificate of Appearance)
Two pilot-feedback items (Spot Feedback from ray@gmail.com). (1) Activities can now carry an optional **start→end date range** for multi-day events; (2) the Certificate of Appearance is now **PDF-only** (the editable PowerPoint export is removed, so an official certificate can't be altered after issue).
- **Schema (`storage.py`)** — additive nullable `end_date TEXT` on both `form_instance` and `event`, added to the `CREATE TABLE` blocks **and** the idempotent `PRAGMA table_info`→`ALTER TABLE ADD COLUMN` migration guards (safe on the live bucket DB). `NULL` = single-day. `create_form_instance`/`create_event` take an optional `end_date`; `_EVENT_COLS`/`_event_row` and `get_form_context` expose it; `_outside_event_context`+`add_event_speaker` propagate it so a late-added speaker inherits the range.
- **Date range is display + lifecycle only — reporting is unchanged.** Year/quarter/semester/month bucketing (`css_is_engine.assign_periods`) still keys **only** off `event_date` (the start), verified by test. `lifecycle_of()` gains an optional `end_date`: with no explicit feedback deadline a multi-day activity stays **"ongoing" through its last day** (`start ≤ today ≤ end`), single-day behaviour byte-identical. `events_with_lifecycle` selects + threads `e.end_date`.
- **Creation (`app.py` `POST /create` + `form_create.html`)** — new optional "to" date input beside the start (min bound to start via inline JS). Shared validator `_norm_end_date(start, raw)`: blank or ≤ start → single-day (no error), non-date → error, beyond the +2yr cap → error. Threaded `end_date` into all three `create_form_instance` calls + both `create_event` calls; echoed back on validation error; result summary shows the range.
- **Manage editing (NEW capability — dates were previously un-editable post-creation)** — `set_event_dates()` re-dates the event row **and** every non-archived form (via `event_form`) so the link tree and reporting atoms never disagree. New `POST /activities/{token}/dates` (same `_can_manage_event` gate + `_audit`), reusing `_norm_end_date`; **calls `invalidate_atoms()`** because moving the start date re-buckets the reporting period (the entry-window save deliberately does not). New "Activity dates" card on `activity_manage.html` + `outside_manage.html` with success/error flashes (`dateok`/`err=baddates`).
- **Display (`humandaterange` filter)** — new Jinja filter renders `June 16–18, 2026` (collapses shared month/year; widens across months/years), falling back to `humandate` for single-day so existing rendering is unchanged. Swapped in at the activity-centric sites: link_tree, rating (survey header), combined_form, monitor (list), monitor_event, monitor_outside, both manage headers. Certificate body uses an equivalent `_long_date_range()` for the "held on …" clause.
- **Certificate PDF-only (`certificate.py`, `app.py`, templates, `i18n.py`)** — removed `render_pptx` + the `_TEMPLATE` asset ref + the module's two-format docstring; the `/e/{token}/certificate` route now always renders PDF (a stale/forged `?fmt=pptx` falls back to PDF, asserted by test). Dropped the "PowerPoint version" buttons from `thanks.html` + `link_tree.html`, the orphaned `thanks_cert_pptx` i18n key, and reworded the manage-page cert help to "print-ready PDF".
- **Tests** — new `tests/test_date_range.py` (10): `humandaterange` collapse/widen, single-day keeps `end_date` NULL, multi-day round-trips to event+forms, end≤start → single-day, non-date end → 400, manage re-dates event+forms, clearing end returns to single-day, bad start rejected/no-change, reporting keys off start. `test_certificate.py` updated (PDF-only assertions, no `render_pptx`), `test_monitor.py` lifecycle test +3 multi-day cases.

## 2026-06-22 (v1.48 — Comment-tone trend over time: 3-way sentiment on the verbatims page)
Extends the verbatim sentiment work longitudinally (UX-queue item #14). `dashboard_insights.sentiment_trend()` already produced a binary "% positive" line (used on Trends/person/team); it now **additively** returns a 3-way `breakdown` (appreciation / areas-to-improve / mixed — mutually exclusive, shares total 100% per period) reusing the segment-chart geometry, plus a new `_sentiment_breakdown_read()`. The binary line stays **byte-identical** (a mixed-overridden comment is still text-classified for it), so the three existing callers are untouched.
- **`/reports/verbatims`** (`app.py` + `templates/verbatims.html`) — new "Tone of comments over time" chart above the digest, built over the **full history** (org scope, period filter dropped) for a single survey type (`survey_type=0`/All shows no chart). Grain toggle (monthly/quarterly/yearly). Figure-axis-standard compliant: labelled X/Y axis titles, legend (green/amber/accent = appreciate/improve/mixed), "how it's computed" calcnote, and a **period-agnostic** person·place·time·(N) caption (place from `crumbs[-1]`, time from the charted range, so it never contradicts the period-ignoring chart).
- **Downloads parity** — `dashboard_docs._chart_sentiment_breakdown()` renders the 3-line chart into the verbatims **PDF** (`rd._fig_block`) and **PPTX** (`rd._chart_slide`) with a figure-number counter + captions; the `app.py` export branch builds the breakdown over full history (`get_atoms` re-scoped) and the page's Download link now carries `&grain`. PNG stays the single themes chart; XLSX stays raw rows + themes (per the per-format download-output roles).
- **Tests** — `tests/test_verbatim_sentiment.py` +6 (shares sum to 100% per period, binary line unchanged, override-mixed bucketing without polluting the positive line, rising-improve read = "bad" tone, single-period + no-comment fallbacks). Full pytest green; `qa_smoke` 153 checks pass; `contrast_check` green (no token change).

## 2026-06-22 (v1.47 — Comment raffle: engagement draw from face-to-face commenters)
New opt-in, per-activity feature: draw a random raffle winner from everyone who left a comment, for both bureau and outside ("invited") activities. The hard constraint shaped the design — bureau responses carry the registered attendee's name, but outside responses are anonymous by design (no name/email ever captured) — so identity is **name-when-known, else a stable CLAIM CODE** shown to the respondent at submission. Eligibility = any non-empty comment on a **face-to-face** response (online/archived excluded; SEX/AFFIL demographic notes don't count).
- **`storage.py`** — migration adds `event.raffle_enabled` (0/1, default 0) + `event.raffle_prize` (TEXT), and a `raffle_draw` history/audit table (event_id, response_id, prize, drawn_at, drawn_by). `_EVENT_COLS`/`_event_row` extended (so `get_event*` expose the two fields). New: `claim_code()` (sha256→5 chars over an unambiguous alphabet, no 0/O/1/I; deterministic + non-sequential; a display label only — response_id is the source of truth), `raffle_pool()` (one entry per f2f comment, attendee name or None, comment = overall remark else non-demographic item notes), `set_event_raffle`, `raffle_record_draw`, `raffle_drawn_ids`, `raffle_winners`, `raffle_reset`.
- **`app.py`** — four routes, all gated by the existing `_can_manage_event` ownership/admin check: `POST …/raffle/settings` (on/off + prize, audited), `GET …/raffle` (projector draw screen), `POST …/raffle/draw` (fair `secrets.choice` from the pool minus prior winners unless `allow_repeat`; prize falls back to the activity's configured prize; returns JSON + audits each draw), `POST …/raffle/reset`. The single-form (`POST /r/{token}`) and combined (`POST /seq`) submit handlers now capture the new response id and, when the activity's raffle is on and the f2f response carries a real comment, pass the claim code(s) to the thank-you page. Added `import secrets`; `submit_combined` now resolves `lang`.
- **`templates/thanks.html`** — a gold "🎟️ You're entered in the raffle!" ticket showing the claim code(s) + keep-this-to-claim note, bilingual EN/FIL inline (no new i18n keys), guarded with `is defined` so other thank-you renders are unaffected.
- **`templates/activity_manage.html` + `outside_manage.html`** — a "🎟️ Comment raffle" card (On/Off badge, enable toggle, prize field, "Open draw screen ↗" when enabled).
- **`templates/raffle.html`** (new, standalone full-screen) — projector draw stage with **four live-selectable animations** (slot reels / prize wheel / name-shuffle+spotlight / lottery tumbler) and a **selectable synthesized audio** picker (Off / Suspense / Arcade — Web Audio API, no audio files, offline-safe), confetti, winner reveal (name|"Anonymous" + claim code + comment + prize), "Draw again", allow-repeat toggle, spacebar-to-draw, live winners list; animation + sound choices persist in `localStorage`. Server-side pick is the source of truth; a ~3.2s minimum spin holds the suspense regardless of network.
- **Tests** — `tests/test_raffle.py` (17): claim-code stability/cleanliness, pool eligibility (real comments only, f2f only, item-note inclusion, demographic-only + no-comment exclusion, named vs anonymous, outside activities), settings/draw/winners/reset storage round-trips, and HTTP draw (picks/records/excludes-repeats, allow-repeat, empty vs exhausted, reset, manager-gating) + thank-you code surfacing. Full suite green (446 passed).

## 2026-06-21 (v1.44 — Phase 3 UI sweep, batch 7: public survey path + auth — FINAL batch)
Seventh and **final** batch of the Phase 3 rubric sweep (`UI_IMPROVEMENT_PLAN.md`, sweep order items 11–13 — public/auth). **Phase 3 is now complete** → Phase 4 (tutorial system) is unblocked. Mapped the respondent-facing + auth templates (mobile lens = top priority; `public_layout.html` confirms `data-theme` applies to public pages, so dark mode is in scope here too). Most were already compliant; the real defects were two unlabeled inputs and one dark-mode hex. NOTE: an Explore pass over-flagged several "mobile overflow" risks that did NOT reproduce and were verified false in Preview at 360px (see below) — they were left unchanged.
- **`templates/rating.html`** — (1) the per-question optional note `<input class="note">` had only a `placeholder` (not a reliable accessible name) → added `aria-label="{{ t('note_ph', lang) }}"` (matches the visible placeholder, i18n-aware). (2) `.conv-error` (the one-at-a-time "please answer first" warning) `color:#c00`→`var(--red)` — the literal maroon was unreadable on dark; the token reads correctly in light/dark/contrast.
- **`templates/combined_form.html`** — same note-input fix: added `aria-label="{{ t('note_ph', lang) }}"` to the per-item `<input class="note">`.
- **Verify-only (no change):** `thanks.html` (no inline style; pub-card + `var(--green)` tokens), `login.html`, `set_password.html`, `forgot.html` (all `.pub-card` with token colours + labelled inputs + `role="img"`/`aria-label` brand mark + `flash err role=alert` error states), `shared.html` (extends `dash_layout`, already uses `empty_state()` + tokens + `aria-hidden` on the `→` glyph). `reset_password.html` does **not exist** (the `/reset-password` route reuses `set_password.html`) — dropped from the batch list.
- **Explore false-alarms, verified NON-defects at 360px (left as-is):** the `@media (max-width:419px)` scale-wrap in rating/combined_form DOES cover 360px (max-width is "≤", so the scale already wraps there — `flex-wrap:wrap` confirmed computed at 360); the `max-width:380px/400px` on `.pub-card` (login/set_password/forgot) is responsive — `max-width` caps but the card still shrinks (measured 331px wide at a 360px viewport, zero page overflow). No breakpoint or width changes made.
- **Verified (Preview, 360px, real tokens):** `/r/af7466fb8215` (rating, open form) renders 200 with **zero horizontal overflow**, scale `flex-wrap:wrap`, note `aria-label`="Add a note about this (optional)", `.conv-error` computed `rgb(197,48,48)`=`--red`; `/seq?tokens=af7466fb8215` (combined) 200, zero overflow, note `aria-label` set; `/login`, `/forgot`, `/set-password` all 200 with zero overflow (cards 331px). All 7 batch-7 templates compile against the app's real Jinja env. `contrast_check` green (no `app.css`/token change); full pytest. Version bumped to **1.44**. **Phase 3 page sweep DONE (batches 1–7).**

## 2026-06-21 (v1.43 — Phase 3 UI sweep, batch 6: admin/ops pages, table-reflow + a11y + dark-mode pass)
Sixth batch of the Phase 3 rubric sweep (`UI_IMPROVEMENT_PLAN.md`, sweep order item 9 — admin/ops). Mapped all 17 admin/ops/manage templates with an Explore pass. Most were already rubric-compliant (use `page_header()`/`empty_state()`, responsive tables, semantic badges) — the real defects were a cluster of non-responsive tables, decorative glyphs missing `aria-hidden`, and a few dark-mode-breaking hex literals. Two findings were **non-defects per the established v1.37 header-audit decision** and left alone: the "manual `<h1>`" on the detail pages (`monitor_event`, `monitor_outside`, `outside_manage`, `activity_manage`, `cleanup`) are the exempt composite name+badge `.mhead` headers (`page_header` escapes its title, can't hold the badge/span — same exemption as person/team); and `directory.html` list avatars stay `alt=""` (decorative, visible text fallback) per the plan.
- **`templates/backups.html`** — the Snapshots table (raw `<table>`, unwrapped, with a Restore *text input* in a cell that would clip badly on mobile) → wrapped in `.table-wrap` + `class="resp-table"` + `data-label` on every `<td>` (full stacked reflow at 360px). Dark-mode hex: `.badge.off` `background:#f3f4f7`→`var(--surface-2)`.
- **`templates/encode_home.html`** — the forms table (already in `.table-wrap`, scroll-only) upgraded to `class="resp-table"` + `data-label`s for a proper stacked reflow.
- **`templates/activity_manage.html`** — the `bucket_card` macro's `.res-tbl` (3-button form-table) wrapped in `.table-wrap`; the per-row `res-kind` leading glyph wrapped `<span aria-hidden="true">` (paired with its own visible text label). The inline `.empty` notes (335/386/456) and "Currently:…" spans (411/413) LEFT as styled status notes — they sit beside add-forms/controls, not blank content areas (Phase-1 deferral guidance; `.empty` is styled muted-italic globally `app.css:472` + locally).
- **`templates/outside_manage.html`** — the headerless `.sp-tbl` form-table wrapped in `.table-wrap` (graceful internal scroll; stacking it would fight the custom right-aligned form cells). The disabled-remove `🔒` glyph given `role="img" aria-label="Locked — has responses, can't be removed"` so it announces meaning instead of reading as a bare emoji.
- **`templates/directory.html`** — `aria-hidden="true"` on the 3 decorative `🔍` search-box glyphs (the inputs already carry `aria-label`); dark-mode hex `.dcard button.del` `border-color:#f0caca`→`var(--red-ln)`; added a local `.dcard td.empty` rule (muted/centered/italic) so the 4 `<td class="empty">` table-cell empties read as designed empty states (kept as `<td>` — the block-level `empty_state()` macro can't sit in a `<tr>`; 4 cells on one page is below the 3-page threshold to promote a shared `app.css` class).
- **`templates/ops.html`** — `aria-hidden="true"` on the decorative `.verdict .icon` and the `.safety .dot` status glyphs (✔/⚠/●/·); each is paired with descriptive text and a tone class, so colour/glyph is not the sole signal.
- **`templates/audit.html`** — the leading `✔`/`⚠` in the chain-status badges wrapped `<span aria-hidden="true">` (the badge text already states "Chain intact"/"CHAIN BROKEN").
- **Verify-only (no change):** `users.html`, `cleanup.html`, `admin_sharing.html`, `monitor.html`, `monitor_event.html`, `monitor_outside.html`, `my_feedback.html`, `feedback_board.html`, `feedback_detail.html`, `result.html` (its `class="list"` summary is a 2-col key/value table — never overflows at 360px; stacking would be worse). All `.empty` notes on these are styled muted (global `app.css:472` + per-template) and are inline/link-bearing status notes the plan keeps as-is.
- **Verified:** all 9 edited templates compile against the app's real Jinja env (incl. the `activity_manage` macro); `/admin/backups`, `/encode`, `/directory`, `/ops`, `/admin/audit`, and `/activities/<token>/manage` (outside) all render 200 with no traceback; **zero document horizontal overflow at 360px** on backups/encode/directory/outside-manage (backups + encode fully reflow via `resp-table`; the manage `.sp-tbl` scrolls inside its `.table-wrap` without pushing the page); 3 directory search icons confirmed `aria-hidden`; `td.empty` rule present. `contrast_check` green (no `app.css`/token change); full pytest. Version bumped to **1.43**.

## 2026-06-21 (v1.42 — Phase 3 UI sweep, batch 5: reports/verbatims, dark-mode + mobile pass)
Fifth batch of the Phase 3 rubric sweep (`UI_IMPROVEMENT_PLAN.md`, sweep order item 8 — reports). `verbatims.html` was already fully rubric-compliant (`page_header()` + `empty_state()`, all-token colours, `.vb-cols` reflow at 780px, single column with no horizontal scroll at 360px) — **verify-only**. All real defects were on `reports.html`: light-only hardcoded hex that ignored dark mode, plus two raw breakdown tables that weren't wrapped for narrow screens. Per the locked decision, fixed by swapping the literals to existing themed tokens rather than adding parallel `[data-theme]` blocks; edits are template-local `<style>` (no `app.css` change, so no cache-bust needed).
- **`templates/reports.html`** — (1) the answer-distribution bar's neutral middle segment `.bar .m` `#cbd5e1`→`var(--line-strong)` (light value `#cdd5e1` is byte-near-identical; dark now resolves to `#3b4c66` instead of staying light grey); (2) the two `border-bottom:1px solid #f1f3f6` rules (`.cc-card .cc-details td`, `.tblk td`)→`var(--line)` (dark now `#2c3a4f` instead of a near-white line); (3) wrapped the two previously-unwrapped tables in `.table-wrap` — the `tally_block` respondent-profile table and the `cc_card` "Full breakdown" `<details>` table (the plan's cross-cutting backlog item for `reports.html`). The wide tables were already handled: the ARTA SQD table is `.resp-table` with `data-label` cells, the SERVQUAL dims tables are already in `.table-wrap`.
- **Deliberately KEPT:** `--grey` fine-print (`.scale-note`, `.cc-base`) per the Phase-1 AA-exempt decision; the `var(--accent,#hex)` fallbacks (`.rtab.on`, `.sharebar i`) — the hex is only a fallback when the token is absent; the green/red bar segments (already tokens). `verbatims.html`'s "Nothing on this side in this scope." note left as a styled inline note (pure status inside a narrow coloured column — the block-level `empty_state()` would read heavy there).
- **Verified (Preview, forged admin cookie):** `/reports?type=1/2/3` + `/reports/verbatims` all render 200 with no console errors; the swapped tokens resolve correctly in both light (`.bar .m`=`rgb(205,213,225)`) and dark (`.bar .m`=`rgb(59,76,102)`, `.tblk td` border=`rgb(44,58,79)`); both Reports and Verbatims have **zero horizontal overflow at 360px** (`scrollWidth==clientWidth==360`, no offenders); the 5 `tally_block` + 3 `cc_card` tables confirmed inside `.table-wrap`. `contrast_check` not re-run for tokens (no `app.css`/token change); full pytest. Version bumped to **1.42**.

## 2026-06-21 (v1.41 — Phase 3 UI sweep, batch 4: activities/activity/activities_archived, empty-state pass)
Fourth batch of the Phase 3 rubric sweep (`UI_IMPROVEMENT_PLAN.md`, sweep order item 7 — activities). Same finding as the prior batches: the list pages were already rubric-compliant. `activities.html` + `activities_archived.html` already use `page_header()` + `empty_state()` (adopted in the v1.37 pass) and have a reflowing `.resp-table`, sticky sortbar on `--stuck-top`, and aria-hidden on standalone arrow/caret glyphs — verify-only. The one real "States" defect was on the detail page.
- **`templates/activity.html`** — the three genuine empties rendered as bare `<p class="sublab" style="margin:0;">` inside a `.panel` migrated to the `empty_state()` macro (import added): the no-section-comparison branch (only activity in scope that year, `icon="⇄"`), the no-Form-2-scores branch (`icon="◔"`), and the no-demographic-data branch (`icon="◔"`, conditional "— enter it below" manager text preserved via `{% set %}`→macro so the HTML-escaping macro keeps the text). Composite name+pill report header LEFT as the bespoke `.rpt-head` `<h1>` per the v1.37 detail-page header exemption (matches person/team).
- **`templates/activities_archived.html`** — removed the now-dead `.empty` CSS rule (the page moved to `empty_state()` in v1.37; the class had no remaining users).
- **Deliberately KEPT:** the demographics/meter brand-blue gradient fills (`#4299e1→#2b6cb0`) and the categorical demographic colours (male/female/DOH blue·pink·green·grey, each paired with a legend dot) — data-series identity, read fine on dark; and the inline `✎`/`⚙` glyphs that sit *within* link/summary text (read as part of the label, consistent with `activities.html`'s un-hidden `✎ Edit / merge`).
- **Verified (forged admin cookie, Preview):** all 49 listed activity reports render 200 with no traceback at desktop + 360px; demographics empty-state confirmed rendering (`◔` + aria-hidden + conditional manager text); SERVQUAL table reflows via `.resp-table` at 360px with no horizontal scroll. The no-Form-2 / no-section-comparison branches are data-gated (every live activity has a Form-2 report and peers) so unexercised at runtime, but the whole template compiles clean on every render (a syntax error would 500 all of them). `contrast_check` green (no colour/token change); full pytest. Version bumped to **1.41**.

## 2026-06-21 (v1.40 — Chart/data-viz dark-mode token sweep on trends + participation)
Follow-up to the batch-3 deferral: the light-only structural hex in the Trends + Participation chart styles (gridlines, SPC bands, limit lines, legend swatches, progress-bar tracks) glared near-white on dark cards. **Resolved by swapping the literals to the existing themed tokens** — NOT by adding a parallel `[data-theme="dark"]` block. Suitable tokens already existed (`--surface-3`≈#eef1f6, `--line-strong`≈#cdd5e1, `--grey-tone`=#94a3b8, `--soft`, `--ink-soft`), so a direct swap is byte-near-identical in light, auto-correct in dark **and** contrast (one edit covers all three themes), and actually *removes* hex rather than doubling it. The badge palette needed its own dark block only because it had no token backing; these did.
- **`templates/trends.html`** — `.chart .grid`/`.ctl-band` `#eef2f7`→`var(--surface-3)`; `.chart .lim`/`.dimline.flat` + `.bandnote .sw.band` border `#cbd5e1`→`var(--line-strong)`; `.bandnote .sw.band` bg `#eef2f7`→`var(--surface-3)`; `.mover` base `#fbfdff`→`var(--surface-2)`; `.axtitle` `#475569`→`var(--soft)` and `.calcnote b` `#475569`→`var(--ink-soft)` (now matches participation, which already used these). Two inline body swatches: Overall key `#94a3b8`→`var(--grey-tone)` (byte-identical light), and the by-area legend flat swatch literal `#cbd5e1`→`var(--line-strong)` in the `{% set sw %}` expr (the expr already mixed `var(--green)` + hex, so this is consistent).
- **`templates/participation.html`** — same `.chart` grid/ctl-band/lim/sw.band swaps; plus `.cover .track` + `.unit .track` `#eef1f5`→`var(--surface-3)` and `.unit.zero .fill` `#e2e8f0`→`var(--line-strong)`.
- **Deliberately KEPT (read fine on dark; data-series identity):** saturated line/bar/badge fills — `.mainline.cov`/`.dot.cov` `#2f855a`, `.eng` `#805ad5`, `.unit .fill` gradients, `.unit.down .mv` `#c05621`, the green confidence ribbon, white dot markers; and the `#d97706` down-trend (line **and** its legend swatch both use it, so they stay matched) + the mid-grey `#64748b` centre line. These are mid/strong tones with adequate contrast on the dark `--surface`.
- **`templates/team.html` — NO CHANGE:** the `.pbadge` earned-badge palette is **already** dark-covered by the existing block in `app.css:745–764` (higher-specificity `[data-theme="dark"] .pbadge.bg-*`), which `contrast_check.py` already audits green. The task's team.html premise was stale. Contrast theme is light-based (`--bg:#fff`), so the light pastels are correct there too — no contrast override needed.
- **Verified:** _pending_ — jinja render (forged admin cookie) of both pages in default + dark + contrast; `contrast_check` green; full pytest. Version bumped to **1.40** (ships together with the held v1.39 a11y batch in one deploy).

## 2026-06-21 (v1.39 — Phase 3 UI sweep, batch 3: teams/team/trends/participation, a11y pass)
Third batch of the Phase 3 rubric sweep (`UI_IMPROVEMENT_PLAN.md`, sweep order items 4–6). Same finding as batches 1–2: the unit-detail + time-series pages are already structurally compliant (single h1 via `page_header`, full-width lede, charts with `role="img"`/aria-label + axis titles + "how computed" notes, reflowing grids). Only real defects were decorative emoji/arrow glyphs missing `aria-hidden`, one un-migrated empty state, and a divider hex that ignored dark mode.
- **`templates/teams.html`** — `aria-hidden="true"` on the two `.uglyph` unit-type emoji spans inside the `ucard()` macro (covers every bureau/division/section card glyph). Unit name is the adjacent visible label, so the glyph is purely decorative.
- **`templates/team.html`** — `.uglyph` header emoji + the `↑` drill-up arrow wrapped `aria-hidden`. The no-data `<div class="panel">` (with inline `style`) migrated to the `empty_state()` macro (import added) — consistent with the v1.37 adoption pass; the period note moves to the title string (drops only the bold, which the macro can't carry). The `.coach-motiv` divider `rgba(0,0,0,.07)` → `var(--line)` (the one dark-mode-breaking hex with a clean token). Composite name+badge+meta header LEFT as a raw `<h1>` per the v1.37 header-audit exemption for detail pages (matches `person.html`).
- **`templates/trends.html`** — leading trend emoji (📈📉➡️🔍) on the two `.read-sub` reads wrapped `aria-hidden`. The `.larr` legend arrows LEFT readable — they're the only directional cue on an unsigned score (informative, not decorative).
- **`templates/participation.html`** — leading 📋/🔍 read emoji + the link `→` affordance wrapped `aria-hidden`; the `▲/▼` movement triangles on the vcard delta and per-unit rows wrapped `aria-hidden` because the **signed** delta beside them already conveys direction in text (redundant glyph).
- **Deliberately deferred (user-confirmed follow-up):** the light-only badge/chart-series hex palettes (`team.html` `.pbadge` gold/rose/violet/teal/indigo/stone/fuchsia ×9; `participation.html` chart swatches/bars; `trends.html` legend `#d97706`/`#cbd5e1`/`#94a3b8`). No token equivalents exist — converting would mean inventing accent tokens, which the sweep rule forbids. Tracked as a separate "dark-mode palette" item, not expanded into this batch.
- **Verified:** _pending_ — jinja parse of all four + render (forged admin cookie) of the team.html empty-state; `contrast_check` green; full pytest. Version bumped to **1.39**.

## 2026-06-21 (v1.38 — Phase 3 UI sweep, batches 1–2: home/pulse + people, a11y pass)
First two batches of the Phase 3 page-by-page rubric sweep (`UI_IMPROVEMENT_PLAN.md`). Both page-sets were already largely rubric-compliant (single h1, full-width lede, styled empty-states, responsive, no 360px overflow, aria-labelled charts); the only real defects were decorative SVGs and content `<img>`s missing accessibility attributes. Batch 1 was folded into this deploy (it was screen-reader-only on its own).
- **`templates/home.html`** — added `aria-hidden="true"` to the 11 decorative inline icon SVGs (the 4 activity-feed headers + the role-filtered module-card icons). The labelled search-box icon already had it.
- **`templates/dash_layout.html`** — added `aria-hidden="true"` to the shared command-palette (Ctrl-K) search icon SVG; benefits every dashboard page.
- **`templates/people.html`, `person.html`, `person_activity.html`** — content avatar `<img>`s changed from `alt=""` to `alt="{{ name }}"` so screen readers announce who each photo is (the no-photo fallback already shows visible initials). The directory list avatars keep `alt=""` (decorative — they have a visible text fallback beside them).
- **Verified (forged admin cookie, Preview):** home + /dashboard → 0 unhandled decorative SVGs, single h1, no 360px overflow; people / person (with photo) / person-activity → avatar alt = name, single h1, no 360px overflow. Full pytest green. Version bumped to **1.38**.

## 2026-06-21 (v1.37 — Phase 1 UI follow-through: empty-state adoption, header audit, contrast tooling)
Layers onto the v1.35 Phase 1 work (the `page_header`/`empty_state` macros and contrast pass). Adoption + audit, no new plumbing.
- **`empty_state()` adoption** — migrated 17 genuine content-area empty states to the macro across 12 templates (people, activities, verbatims, trends, participation, audit, encode_home, activities_archived, feedback_board, my_feedback, reports ×4, shared ×2). Conditional messages use `{% set %}`→macro so scope/query text survives. DELIBERATELY LEFT for the Phase 3 page sweep: `directory.html` `<td class="empty">` table cells, inline `.empty` muted-note spans (`activity_manage` "Currently:…", `outside_manage` 🔒 lock), and link/markup-bearing notes (`monitor.html`, `my_feedback:99`) — the macro escapes HTML, so those become empty-state CTAs later.
- **`static/css/app.css`** — fixed the one accent×theme pair the v1.35 pass missed: amber **accent** preset `#a65f00`→`#a05c00` (was 4.48:1 on its own `--accent-bg`; now 4.74). The v1.35 fixes covered semantics + teal/emerald accents but not amber-on-tint.
- **`templates/admin_sharing.html`** — plain title+lede → `page_header()` macro (now `<h1 class="page">`). **`templates/cleanup.html`** — its description used `class="lead"`, which is **undefined in app.css** (rendered unstyled); fixed to `.lede`.
- **`tools/contrast_check.py`** (new) **supersedes `tools/contrast_audit.py`** (deleted). The old script transcribed tokens by hand (already drifted — still listed the pre-fix amber accent) and never checked `accent`-on-`accent-bg`. The new one **parses `app.css` live** (no drift) and covers a superset: all 18 accent×theme combos + `accent`/`accent-bg`, `accent`/`blue-bg`, `accent-ink`, and the 7 bespoke dark badge pairs. Exit-coded gate; this is the one to run before every deploy now.
- **Header audit** — confirmed the remaining 21 raw-`<h1>` templates skip the macro for deliberate reasons (8 public-layout centered-card pages, 8 dashboard detail pages with composite name+badge+meta headers, 3 form pages, home hero).
- **Verified:** jinja parse of all edits, live render (forged admin cookie) of a people empty-state + the admin_sharing header, contrast_check green, full pytest green. Version bumped to **1.37**.

## 2026-06-21 (v1.35 — Phase 1 UI: contrast fixes, card/panel dedup, page_header macro)
Completes PHASE1_HANDOFF.md. Four tasks: WCAG 2.2 AA contrast fixes, `.card`/`.panel` CSS dedup, dark-mode badge comment block, and `page_header()` macro rollout to all 24 dashboard templates.
- **`tools/contrast_audit.py`** — new stdlib-only script; checks 78 text/bg pairs (24 theme-only + 54 accent×theme) against 4.5:1 AA; exits 1 with failure table if any fail. Run before every deploy.
- **`static/css/app.css`** — fixed 4 failing pairs: `--green` light (#2f7f5a, was #2f855a, 4.39→4.71), `--amber` light (#9e6217, was #b7791f, 3.50→4.79), teal light accent (#0f7a7a, was #0f8a8a, 4.18→5.13), emerald light accent (#1c7e4f, was #1f8a55, 4.35→5.06). Deduped `.card` and `.panel` blocks into a single shared rule. Added comment block explaining bespoke badge hex overrides.
- **`templates/_components.html`** — added `page_header(title, lede="")` macro.
- **24 dashboard templates** — added `{% from "_components.html" import page_header %}` and replaced all `<h1 class="page">` tags with `{{ page_header(...) }}` calls (4 with plain lede passed to macro; 20 with h1 only or dynamic lede left inline).

## 2026-06-21 (v1.34 — Saved views + deep-linkable / shareable report filters)
Completes UX-queue #9. The URL already carries the full filter state (the scope bar and every filter pill are GET query-params), so a report view *is* its URL. This adds the missing affordances on the shared scope bar: copy a shareable deep-link, and pin/recall named views. **No DB, no Python route changes** — per-device localStorage only (locked decision); cross-person sharing is via the copied link.
- **`templates/dash_layout.html`** — inside the `.scopebar` (so it appears on every `show_scope` page): a `.savedviews` group with **★ Save view**, **Saved views ▾** (popover, hidden until ≥1 saved), and **Copy link** buttons, plus an empty `data-sv-menu` the JS fills. All `type="button"`, `hidden` until JS reveals them (graceful no-JS). Emits `window.SAVED_VIEW_CTX = {key: cur, scopeLabel}` reusing the template's existing per-page `cur` nav key.
- **`static/js/app.js`** — new saved-views IIFE: localStorage `css_views_<key>` (array of `{name,url}`, de-dupe by name, cap 20); render popover, navigate on click, `×` to delete; smart default name from `scopeLabel` + lit `.seg a.on` pills. **Copy link** uses `navigator.clipboard.writeText` with an `execCommand('copy')` textarea fallback. Hoisted a shared `window.cssToast()` (reuses `.offline-toast` styling) for the confirm toast; the offline module keeps its own copy untouched.
- **`static/css/app.css`** — `.savedviews` / `.sv-btn` / `.sv-menu` / `.sv-row` / `.sv-go` / `.sv-del` styles matching the scope-bar + palette-popover look; right-aligned, wraps under on mobile. Cache-bust → `v=20260621c` (app.css + app.js refs in `dash_layout.html` and `public_layout.html`).
- **`tests/test_saved_views.py`** — render assertions: control + `SAVED_VIEW_CTX` present on a scope-bar page, absent on `/login`.
- **Verified:** _pending_ — preview DOM checks (save → localStorage round-trip, recall navigates, copy, delete) + full pytest. Version bumped to **1.34**.

## 2026-06-21 (v1.33 — Offline response capture + sync, PWA Phase 2)
Completes UX-queue #5: a survey submitted with no connection is saved on-device and replayed automatically when connectivity returns. JS + a tiny server dedup; the two forms and the online happy-path are untouched.
- **`storage.py`** — new `submission_log(client_submission_id PK, created_at)` table (added in `_add_missing_columns`) + `submission_seen()` / `mark_submission()` (INSERT, swallow IntegrityError). Idempotency ledger so a replayed offline submission records once.
- **`app.py`** — `submit_rating` & `submit_combined` read `submission_id`; if already in `submission_log` they short-circuit with `200 {ok,deduped}` **before** the window check (so an already-recorded item always dequeues even if its window has since closed); after a successful record they call `mark_submission`. Online submits carry no id → byte-for-byte unchanged.
- **`static/js/app.js`** — new offline IIFE: IndexedDB `css_offline/queue`; capture-phase `submit` interceptor that, **only when `navigator.onLine === false`**, `preventDefault`s, serialises `new URLSearchParams(new FormData(form))` (byte-identical to a native POST) + an attached `submission_id`, queues it, and swaps the form for a “Saved on your device” panel. `flush()` runs on page load + the `online` event (mutex-guarded): 2xx→delete, 4xx→mark **failed** & surface (reject-and-surface), 5xx/network→keep & retry. A bottom pill shows “N waiting to send” and failed items with a Discard action; a green toast confirms sends.
- **`static/js/sw.js`** — `sync` handler (`css-flush`) runs the same IDB-read + POST flush so queued answers can go out with no tab open (Android/Chrome; iOS lacks Background Sync → page-flush is the universal path). `CACHE_VERSION` → `v1.33-a`.
- **`i18n.py` / `public_layout.html`** — offline UI strings (EN + draft FIL) injected as `window.OFFLINE_I18N`. **`app.css`** — saved-panel / pending+failed badge / sent-toast styles; cache-bust → `v=20260621b`.
- **Verified:** offline submit queues to IndexedDB + shows the panel; flush POSTs and records server-side; replaying the same `submission_id` adds **no** duplicate; a closed-window replay is marked failed and surfaced. Version bumped to **1.33**.

## 2026-06-21 (v1.32 — Installable PWA + offline app-shell load, Phase 1)
First cut of UX-queue #5. Makes the app **installable** and lets an already-opened survey **load with no signal**; offline *submission* (IndexedDB queue + background sync + dedup) is the deferred Phase 2.
- **New `static/js/sw.js`** — root-scope service worker. Precaches the public app shell (`app.css`, `app.js`, `search.js`, `offline.html`, icons; per-item `cache.add` so one 404 can't abort install). Fetch strategy: non-GET passes straight through (never touches submit); same-origin `/static/*` GET → stale-while-revalidate; navigations → network-first with a cached-page then `/static/offline.html` fallback, runtime-caching only public survey paths (`/r/`, `/seq`, `/e/`) so admin pages stay live. `CACHE_VERSION` (`v1.32-a`) is bumped per deploy; `activate` deletes stale `css-is-*` caches.
- **`app.py`** — `GET /manifest.webmanifest` returns a dynamic manifest (`application/manifest+json`); `?start=` sets `start_url` so installing from a survey link reopens that survey (validated to a same-origin path, else `/`). `GET /sw.js` serves the worker from the **root** path (whole-origin scope) with `Cache-Control: no-cache` + `Service-Worker-Allowed: /`.
- **`static/offline.html`** — minimal offline fallback styled with `app.css`. **`static/img/icons/`** — generated 192/512/512-maskable + 180 apple-touch icons from `equity-mark.png` (Pillow).
- **`templates/public_layout.html`** — `<head>` gains the per-page `rel="manifest"` link, `theme-color`, Android/iOS install meta, icon links, and a tiny inline `serviceWorker.register('/sw.js')`. Wired on public survey pages only (admin dashboard untouched).
- **Verified:** manifest `start_url` echoes the form path; `/sw.js` serves with the right type/headers; SW registers + controls the page; shell cache present. Version bumped to **1.32**.

## 2026-06-20 (v1.22 — Bilingual survey form: English ↔ Filipino)
First-cut i18n, scoped to the **respondent-facing survey form only** (admin UI stays English). No schema change; stored answers are language-independent (keyed by item id + numeric value, which never change between languages).
- **New `i18n.py`** — single office-editable file holding every Filipino string. `pick(request)` resolves the language (cookie `lang` → `Accept-Language` `tl`/`fil` → `en`); `t(key, lang)` looks up static UI chrome (English value matches the template byte-for-byte, so the English render is unchanged). SQD items use the official ARTA Harmonized CSM Tagalog; the rest are drafts marked `# DRAFT — office to refine`.
- **`app.py`** — `survey_spec(ctx, lang="en")` selects the `*_FIL` text/scale/chip maps when `lang=="fil"` (default keeps all 6 existing callers, incl. admin paper-entry, English). New public `GET /lang/{code}` sets a 1-year `lang` cookie and 303s back same-site; added `/lang/` to `_PUBLIC_PREFIXES` so anonymous respondents can switch. `lang` computed via `i18n.pick` and passed on the public render paths (rating GET/POST, closed, thanks, `/seq`); `t` registered as a Jinja global.
- **Templates** — `rating.html` + `closed.html` chrome moved to `t('slug', lang)` (the pluralised intro line branches on `lang` to keep the English output identical). `public_layout.html` gains a prominent left-aligned `EN | FIL` toggle in the public top bar (plain links, works without JS; shown only on survey-flow pages via `{% if lang is defined %}`) and a dynamic `<html lang>`. `.lang-toggle` pill styles added to `app.css` (cache-bust → `v=20260620a`).
- **Verified:** type-1 (ARTA), type-2 (event) and type-3 (resource-person, `{subject}` interpolated) forms render fully in both languages; the toggle persists across navigation and submit; a Filipino submission records correctly (then cleaned up); English output unchanged. Version bumped to **1.22**.

## 2026-06-19 (v1.20 — Global dark-mode text colour sweep)
Full audit of hardcoded `color:` hex values across all templates and app.css; replaced every dark-only value with the appropriate CSS token so all themes work.

**Group 1 — Semantic token swaps (9 files):**
- `app.css` — `.sf-toast color:#fff` → `color:var(--bg)` (inverts correctly against the `var(--ink)` background)
- `directory.html` — `.warn` amber colours, `.hint` muted text
- `backups.html` — `.kind.pre_restore` amber warning
- `cleanup.html` — 9 rules: `.banner.ok` (green), `.restore button` (amber), `.flag.f-low` (amber), `.nm .rid` (grey), `.b-ext` (soft), `.b-hid` (accent/blue), `.f-caps/.f-hon/.f-ros/.f-dup` (amber/green/red/blue), `.arrow` (grey)
- `participation.html` — `.calcnote b`, `.bandnote b` (ink-soft); `.miniread .mt b` (ink); SVG `.ctl-lab` (grey), `.axtitle` (soft)
- `trends.html` — `.read.neutral` border (grey); `.bandnote b` (ink-soft); `.endcap.down`, `.lowline`, `.lowdot` (amber); `.legend span.li.flat` (grey); `.legend button.li.on` highlight (surface-3/line)
- `staff_form.html` — `.warn` amber
- `outside_manage.html` — `.danger` border (red-ln), `.danger h2` (red), `.btn-warn` (amber), `.btn-danger`/`.btn-del` (red)
- `form_create.html` — `.hint` (soft), `.btn-del` (red)

**Group 2 — Badge palette dark mode (app.css):**
Added `:root[data-theme="dark"] .pbadge.bg-*` and `.ublegend .bg-*` overrides for all 10 badge colours (gold, green, blue, rose, violet, amber, teal, indigo, stone, fuchsia). Higher specificity (0,4,0) beats per-template light-mode definitions (0,2,0) so no template edits needed.

## 2026-06-19 (v1.19 — Verbatims scopebar + activity dark-mode contrast)
- **Verbatims page now shows the standard scope/period selectors.** `reports_verbatims()` was passing `org_opts`/`sel_org`/`sel_period` but not `show_scope=True`, `period_opts`, or `crumbs`, so `dash_layout.html`'s scopebar never rendered. Added `period_opts = _period_options(atoms)`, `crumbs = _crumbs(org, org_opts)`, `show_scope=True`, and `scope_extra={"survey_type": survey_type}` (so tab-switching preserves the selected scope). Removed the now-redundant scope badge chip from `verbatims.html`.
- **Activity page dark-mode contrast fixed.** Four hero-card `background:linear-gradient(…)` rules used hardcoded light hex colours (`#eef4ff`, `#f3fbff`, etc.) that stayed pale in dark mode while `var(--ink)` flipped to near-white — making the big numbers invisible. Replaced with token-based gradients (`var(--blue-bg)`, `var(--green-bg)`, `var(--amber-bg)`, `var(--red-bg)`, `var(--surface)`). Also replaced 9 occurrences of hardcoded chip/verdict text colours (`#234e75` → `var(--accent-ink)`; `#7a5300` → `var(--amber)`) that were illegible on dark surfaces.

## 2026-06-18 (v1.18 — Atoms-frame perf: categorical dtypes + unique-date period map)
- **Performance sweep, two phases, no behaviour change.** The shared in-memory atoms frame (the table every dashboard/report is computed from — ~396K rows on the live data) was costing 353 MB resident and ~5.4 s to build cold. Both addressed; output is byte-identical (full pytest + qa_smoke green after each phase).
- **Phase 1 — categorical dtypes (`storage.py`).** 14 low-cardinality label columns (`organizer_ref`, `topic`, `org_path`, `rateable_unit`, `organizer_type`, `year`/`quarter`/`semester`/`month`, `modality`, `form`, `item_id`, `service`, `served_by_rp_id`) were stored as plain strings — e.g. `year` (6 distinct values) alone ate 21 MB. `load_atoms` now downcasts them to `category` via `_categorize_atoms()` (`_ATOMS_CAT_COLS`). Result: **frame 353 → 53 MB (6.7x)**, cold-start pickle **101 → 34 MB (3x)**, dashboard groupby ~2.8x faster. The F1 incremental-append path needed care: pandas 3.0 `pd.concat` silently widens mismatched categoricals back to `str`, so added `storage.concat_atoms()` (`union_categoricals`, cost ∝ len(add)) and `app._refresh_worker` now calls it instead of `pd.concat`. **`event_date` is deliberately NOT categorical** — it's used in ordered ops (`ed >= since` window filter in `_apply_window`, `.min()/.max()` spans) that an unordered categorical rejects (caught by the export tests); kept it a plain ISO string (sorts chronologically). Contract locked by a new dtype assertion in `tests/test_atoms_cache.py::test_incremental_equals_full`.
- **Phase 2 — unique-date period map (`css_is_engine.assign_periods`).** Was running `pd.to_datetime` + string-building over all 396K rows; but `event_date` has only ~814 distinct values, so it now parses/formats the DISTINCT dates once into a lookup and `.map()`s back. **1100 → 403 ms (2.7x)**, verified bit-identical (`year`/`quarter`/`semester`/`month`) to the old per-row `.loc[valid]` version; works unchanged on the incremental delta.
- **Not pursued (logged):** the cold-build SQL `fetchall` (~2.8 s) is the remaining large cost, but the JOIN itself is optimal (`COUNT(*)` over the full join = 247 ms, all PK lookups) — the time is marshalling 19 cols × 396K rows. A dimensional load+merge could shave ~1.5 s but rewrites the path feeding every dashboard aggregate for a build that's rarely on the request path (pickle hydrate + stale-while-revalidate cover the common cases); deferred as poor risk/reward.
- **Verified:** pytest exit-0 (407 tests) and qa_smoke 153 ALL PASSED after both phases; atoms frame 53 MB and period columns category-typed with correct values on the live DB. Single-process constraint unchanged (`--workers 1`). Version bumped to **1.18**.

## 2026-06-18 (v1.17 — Verbatims in-place re-tag + "Apply all changes" on the curate bar)
- **Acted on two Spot Feedback items (2026-06-18 batch).**
- **Feedback (sdeguzman247, `/reports/verbatims`): "no 'done' marking; the page suddenly refreshes when we finish tagging, causing confusion about what's already tagged."** Root cause: each re-tag was a plain `<form>` POST to `/dashboard/comment-tag` that returned a `303` full-page redirect, so every tag reloaded the page, reset scroll, AND re-sorted the comment into a different column — the curator lost their place after every action. Fixed by progressively enhancing the control to post over `fetch` and update the card in place; no reload.
  - **app.py (`comment_tag`):** content-negotiates — when the request `Accept`s `application/json` it returns `{ok, tag, prev, response_id, item_id}` instead of redirecting. The classic `303` path is unchanged, so it still works with JS off.
  - **templates/_story.html (`retag_control` macro):** added `data-retag`/`data-rid`/`data-item`/`data-back`/`data-sentiment` on the wrapper and `data-tag`/`data-label` on each button so JS can re-render the control; the "✓ re-tagged" marker is now always present (hidden until overridden) rather than conditionally emitted.
  - **static/js/app.js:** new block 8b intercepts `.retag form` submits, posts via `fetch` (Accept JSON), and on success rebuilds the control in place — flips the sentiment, shows "✓ re-tagged as <label>", recolours the Verbatims `.vb-dot`, and pulses `.just-tagged`. Falls back to a normal submit on network error or if `fetch`/the data attrs are absent. The comment stays put (no column re-sort) so the curator keeps their place.
  - **static/css/app.css:** promoted the `.retag`/`.retag-mark`/button styles out of the `.story`-scoped selector (the Verbatims page renders the control outside `.story`) and added the `.just-tagged` pulse (respecting `prefers-reduced-motion`).
- **Feedback (gbcanoy, `/reports/activities` `#curateBar`): "if I change both Rename/Merge and Refile, which button saves both? Add an 'Apply both' button."** Root cause: the curate bar is one form but each button submits a single `action` (`rename` | `section` | `untag` | `archive`); the backend handled exactly one. So filling both fields then clicking one button applied only that one.
  - **app.py (`activity_bulk`):** added an `all` action and refactored rename + re-file into `_do_rename()`/`_do_section()` helpers that run inside the **same** `aa.new_batch()`, so a single undo reverses both. `all` applies whichever fields are filled (name and/or section), with a combined flash ("Updated N: renamed to "X" and re-filed to <section>."). Single-action paths and messages preserved.
  - **templates/activities.html:** new "Apply both" group with an `action=all` button (`data-needs-any`); the section `<select>` got `id="cbSection"`; the enable/disable script now also watches the section and enables "Apply all changes" when a name or section is set.
- **Verified (HTTP, against a copy of the live DB with a scratch admin):** combined `all` renamed + re-filed activity 9184 under one undo batch (`curate_…` carrying both `fi_topic` and `fi_lead_org` rows); single rename/section/untag and the empty-`all` guard all behave; `comment_tag` returns JSON (200, `application/json`) with `Accept: application/json` and `303` without; the rendered Verbatims DOM carries all new data attributes; the bumped `app.js`/`app.css` (`?v=20260618a`) are served. Browser click-through wasn't possible in this environment (preview proxy unreachable). Version bumped to **1.17**.

## 2026-06-18 (v1.16 — Durable persistence: bucket-backed live DB, no more rebuild wipes)
- **Root cause of the June-18 data loss, fixed.** HF Spaces have an ephemeral filesystem; the live SQLite DB shipped in the repo, so every deploy/restart reset it to the shipped snapshot — wiping any runtime writes (e.g. gbcanoy's rename/merge curate work, which was never in any exported DB). HF has also retired the classic `/data` persistent-storage tier in favour of **Storage Buckets**.
- **Architecture chosen (Path B — safe from BOTH wipe and corruption):** the live DB stays on the fast local disk (WAL intact, real POSIX locking); a mounted bucket holds **durable snapshots**. On boot the newest valid snapshot is restored from the bucket; the DB is snapshotted back after every change + on shutdown. SQLite is NOT run directly over the object-storage FUSE mount (locking/fsync there is unsafe — verified via `davanstrien/bucket-sqlite-probe-*`).
- **Run as ROOT (Dockerfile):** removed the `USER user` (UID 1000) switch. HF bucket mounts are id-mapped `user_id=0` — a non-root container gets `unable to open database file` on `/data` (the probe's documented failure mode). Root is the same mode Gradio Spaces use.
- **backups.py:** `_default_sched_dir()` now prefers `CSS_PERSIST_DIR` (the bucket, e.g. `/data`) over the live-DB dir, so snapshots land on persistent storage while the DB stays local. New `newest_valid_snapshot()` skips a torn final file (container killed mid-write) and falls back to the previous good one (`quick_check` + real-CSS-DB guard).
- **app.py:** `_ensure_live_db()` gained the Path-B branch (restore newest bucket snapshot on boot, else first-boot seed from the repo + write the first snapshot). New durability engine: `_persist_loop()` snapshots to the bucket on change (gated by `PRAGMA data_version`, every `CSS_PERSIST_TICK`=60s, keep `CSS_PERSIST_KEEP`=24) and a `shutdown` hook snapshots on SIGTERM — shrinking the planned-restart loss window to ~zero. Both no-op unless `CSS_PERSIST_DIR` is set.
- **HF config (one-time):** created private bucket `equityinhealth/office-connect-data`, mounted R/W at `/data` (`set_space_volumes`), set Space var `CSS_PERSIST_DIR=/data`.
- **deploy_hf.py:** the DB "pull/swap" carrier step is retired once persistence is live — the bucket is the source of truth and the repo `css_is.db` is only a first-boot seed. Version bumped to **1.16**.

## 2026-06-18 (v1.15 — Activities list: jump-to-page + prominent foot search)
- **Acted on Spot Feedback #20 (gbcanoy, `/reports/activities?...&page=2`).** The activities list runs to hundreds of pages (PAGE_SIZE=25 over ~10K F2 events) but the pager only offered ±1 (`← Newer` / `Older →`), so reaching a far page meant clicking one step at a time. Added a direct page-jump and surfaced search at the foot of the list.
- **templates/activities.html (template-only, no route change):** the `.pager` block gained a `form.jump` — `<input type="number" name="page" min="1" max="{{ pages }}">` + Go, carrying the current `sort`/`org`/`period`/`q` as hidden inputs so the jump preserves scope. Out-of-range/junk input is already safe: `dashboard_activities` clamps `page = min(max(1, page), pages)` server-side. Also added a `.foot-search` card (repeat of the top search, prefilled `q`, with Clear) nudging "searching is faster than paging through N pages" — the better path for a 10K-row list. First real CSS for `.pager`/`.page-info` (previously unstyled inline); all new styles use existing theme tokens so they track dark mode + accent. Both only render when `pages > 1`.
- **Verified:** Jinja parse-check passes; standalone render of the block (page 2 of 412, q="workshop") produces correct bounds (`min=1 max=412 value=2`), carried filters in every hidden field, and Newer/Older links preserving `q`. No backend/storage/test changes. Version bumped to **1.15**.

## 2026-06-18 (v1.14 — Activities curate: preserve page/sort/filter on action)
- **Acted on Spot Feedback #18 (gbcanoy, `/reports/activities?...&page=2`).** Renaming/merging/re-filing/archiving from the "Edit & merge activities" list dumped the curator back to page 1: `activity_bulk` (`app.py`) redirected to a bare `/reports/activities?{ok|err}=msg`, discarding the `page`/`sort`/`org`/`period`/`q` scope the GET route reads. On a multi-page list (PAGE_SIZE=25) every curate action lost their place.
- **app.py:** added a `_back(key, msg)` closure in `activity_bulk` that rebuilds the redirect from the submitted scope params (`urlencode`) and routed all four exit points through it (success, "pick an action", "no matching activities", empty-title). Imported `urlencode`.
- **templates/activities.html:** `#curateForm` now carries `sort`, `q`, `page` hidden inputs (it already posted `org`/`period`), so the POST knows which page/sort/search to return to. The client-side "✓ Done editing" toggle never navigated — the page-1 jump was purely the action submit, now fixed.
- **Safe on shrink:** if the last row on a page is archived, the GET route already clamps `page` to the valid range, so the curator lands on the nearest existing page rather than an empty one. Version bumped to **1.14**.

## 2026-06-18 (v1.13 — Home-page perf: index the hot stats joins)
- **Acted on Spot Feedback #17 ("the response is a bit slow", home page, admin Ray).** Root cause: `home_stats()` (`app.py`) computes 4 metrics × 4 time windows (All/YTD/Quarter/30-day) and the top-2-box satisfaction query joined `answer` (396K rows) → `response` (36K) → `form_instance` with **no indexes on any of those three tables**, so every windowed metric did a full `SCAN answer` — `EXPLAIN QUERY PLAN` confirmed `SCAN a`. Memoised, so it only bites on cold start (worker restart, day rollover, any new response) — exactly the "after the app wakes up" sluggishness reported, and the same cold-start class as the atoms-rebuild work that never covered `home_stats`.
- **storage.py:** added three `CREATE INDEX IF NOT EXISTS` to the schema bootstrap (beside `idx_attendee_event_email`): `idx_answer_response ON answer(response_id)`, `idx_response_submitted ON response(submitted_at)`, `idx_response_form_instance ON response(form_instance_id)`. Created idempotently by `init_db()` at startup, so the live DB picks them up on the next boot — no manual DB surgery, and harmless if re-run.
- **Verified:** on a scratch copy of the live DB, the windowed satisfaction queries dropped ~78 ms → ~21 ms each (4-window block 356 → 190 ms; the irreducible all-time full scan stays ~125 ms), halving cold `home_stats`. Post-fix `EXPLAIN QUERY PLAN` now reads `SEARCH … USING COVERING INDEX idx_response_submitted` / `idx_answer_response` instead of `SCAN`. `init_db()` on a DB copy creates all three cleanly (schema script parses). Benefits every dashboard/report page on these joins, not just home. Feedback #17 replied to + marked **Done**. Version bumped to **1.13**.

## 2026-06-18 (v1.12 — Single-activity downloads: scorecard, not a one-point timeline)
- **The per-activity person download (visual=person + `event_id`) no longer renders a degenerate "Scores over time" — a single session has exactly one trend point, so the timeline was a lone dot / one-row table across all four formats.** Replaced with a one-time-engagement scorecard. Threaded a `payload["single"]` flag (set in `app.py` `_visual_payload` when `event_id` resolves) so the normal all-time person report is untouched (guarded).
- **dashboard_export.py:** new `_fig_person_single()` — headline score (+ band, respondents, "scoring {cmp.phrase}") with the dimension breakdown given full width (PNG/JPEG). `_tables()` person branch swaps the "Scores over time" table for a one-row **"This session"** summary (Score · Band · Respondents · Bureau average · Difference) when `single`.
- **dashboard_docs.py:** `person_pdf`/`person_pptx` skip the "Scores over time" figure-block / slide when `single` — the PDF Summary box and the PPTX hero slide already carry the headline scorecard, so nothing is lost.
- **Bug fixed (same change):** the download's "vs average" comparison computed the bureau benchmark from the **single-session slice itself**, so it always read "right around the average of X" (score vs itself). `app.py` now sources the benchmark — and the TA "vs the norm" context (`bureau_dims`) — from the FULL atoms (`bench_src = atoms_all if single else atoms`) for the single case. Verified: Vlanche April Dulfo @ *Reorientation to PK Excel Workbook* now reads **6.8 vs the real bureau average 6.5 ("above")** instead of the bogus 6.8-vs-6.8.
- **Verified:** all 5 formats (pdf/pptx/xlsx/png/csv) for the single engagement render with no "Scores over time" (CSV/table scan confirms) and the corrected comparison; PNG layout eyeballed (headline + full-width breakdown, footnotes clear). Regression: the normal person report still carries "Scores over time" + "Year on year" + "Peer standing". **Full pytest 395 green.** Version bumped to **1.12**.

## 2026-06-18 (v1.11 — Per-activity resource-person engagement reports)
- **A resource person now has a per-activity drill-down — their own scorecard + downloadables for ONE activity, scoped strictly to their speaker review (never the activity aggregate).** Covers BOTH invited/outside and bureau-led activities, gated to `event_date ≥ 2026-06-15` (`di.RP_ENGAGEMENT_SINCE`) — the date before which the data is too messy to break down cleanly per activity. Motivation: the existing person report blends every session together and the activity report has no per-speaker drill, so "how did RP X do at this one activity" had no home or export.
- **dashboard_insights.py:** new `RP_ENGAGEMENT_SINCE = "2026-06-15"` + `rp_activity_engagements(events, rp_id, since)` — filters `build_events()` output to activities on/after the cutoff that the person spoke at, returning one row each with the person's OWN F3 score (`shown`/`band`), respondents, and a `kind` tag (`outside`|`bureau`, plus `is_external`). Newest first.
- **app.py:** `GET /dashboard/people/{rp_id}/activity/{event_id}` — guards on (activity exists, `date ≥ cutoff`, person is a speaker) then scopes via new `_person_event_atoms(atoms, rp_id, instance_ids)` (the person's `survey_type==3` atoms within that event's instances) and reuses `person_card`/`person_dimensions`/`story_panel`/`ta_advice`. The person route (`dashboard_person`) now also passes `engagements` (memoised `build_events`). The `visual == "person"` export branch gained an `event_id` scope: same per-person×activity slice, peer-standing/year-on-year/badges suppressed (meaningless for one session), meta title/place/period reframed to the activity. The export route already carried the `event_id` param.
- **Templates:** `templates/person.html` gained a "Per-activity engagements" panel (list with per-row Invited/Bureau-led chips, linking to the detail page); new `templates/person_activity.html` (focused scorecard reusing the `_story`/`_export` macros, conditional "Invited engagement" vs "Bureau-led activity" badge, Download dropdown pointing at `visual=person&event_id=…`).
- **Verified (TestClient, on the live DB copy, no writes):** outside engagement (Vlanche April Dulfo @ *Reorientation to PK Excel Workbook*, build-events id 11568) renders 200 with her 6.8/7 "Excellent" · 164 ratings, dimension bars, session verbatims, TA coaching; all 4 download formats return valid files (PDF/PPTX/XLSX/PNG). Bureau-led path exercised by lowering the cutoff in-process against bureau event 9141 → 200 with the "Bureau-led activity" badge + "As speaker" 6.8 panel + all 4 exports. Guards confirmed: pre-cutoff and non-speaker requests 303-redirect / 404. Production has 0 bureau-led activities since the cutoff yet (only the 1 outside), so the Bureau-led row appears automatically once a post-cutoff bureau activity collects ratings. Version bumped to **1.11**.

## 2026-06-17 (v1.10 — Recent activities window: 30 days → 7 days)
- **Home "Recent activities" strip now spans the last 7 days instead of 30.** The count next to the heading (was "59" under the 30-day window) is just `len(my_activities)` — the rows `storage.activities_by_creator` returns after collapsing each bureau event to one row and filtering by `event_date` within the window (NULL/future dates always kept). Narrowing the window to a week drops the count to this week's activities only.
- **app.py:** both call sites in the home route pass `since_days=7` (was `30`) — the admin `all_creators=True` branch and the section-manager branch. No storage change: `activities_by_creator(..., since_days=N)` already keys on `event_date`. Verified live (admin) 59 → 7.
- **templates/home.html:** the strip's sub-line copy updated "last 30 days" → "last 7 days" (both the admin and manager wordings).
- **Verified:** `storage.activities_by_creator(since_days=7)` returns 7 rows vs 59 for `30`/`None` (the 30-day list happened to hit the strip's 60-row collapse cap, hence the matching 59); existing `tests/test_my_activities.py` still green (it exercises the `since_days` parameter directly, not the route's chosen window). Version bumped to **1.10**.

## 2026-06-17 (v1.7 — Archive standalone activities)
- **Admin/creator can now archive a STANDALONE activity (a Form-3 speaker review with no event record) and restore it — closing the gap the event-level archive couldn't reach.** Motivation: 4 ongoing speaker reviews with 0 responses needed to come off all lists/counts without a destructive delete; `form_instance.archived=1` already removes a row from every analytic (`storage.py` `_LOAD_SQL` `WHERE COALESCE(fi.archived,0)=0`) and feed, but `set_event_archived` only reaches forms joined through `event_form`, so standalone forms had no UI path.
- **storage.py:** new `set_form_archived(conn, fid, archived)` (sibling of `set_event_archived`) and `form_archive_info(conn, fid)` (creator + archived state + whether it belongs to an event, for the route's auth + refusal check). `activities_by_creator` gained an `archived` flag (0=live strip, 1=Archived page) and now returns `fid` + `archivable` (True only for standalone forms) per row.
- **app.py:** `POST /activities/form/{fid}/archive` (restore=1 to undo) — refuses missing/bureau-event forms, authorizes via the existing `_can_manage_event` rule (creator or admin), then `set_form_archived` → `invalidate_atoms()` → `_audit("form_archive")`; archive redirects home, restore redirects to the Archived page. `GET /activities/archived` (gated on `manage_event`) lists the manager's archived standalone activities (admins see all creators') with a Restore button.
- **Templates:** home "Your recent activities" strip gained an inline **Archive** button per standalone row (sibling to the row link, not nested) + a "View archived activities →" footer link; new `templates/activities_archived.html`.
- **Verified:** new `tests/test_form_archive.py` (archive drops it from the strip + `ongoing_standalone`, creator/admin allowed + other manager refused, restore round-trip, bureau-event form refused) + full suite green; live click-through on the home strip → Archive → Archived page → Restore. Version bumped to **1.7**.

## 2026-06-11 (External directory fields + fresh-start wipe)
- **External resource persons get structured fields: honorific, agency, email.** `agency` column added to `resource_person` (schema + migration + `add_rp`/`update_rp`/`list_resource_persons`); `honorific` + `email` already existed. New **dedicated add/edit form** for external RPs (`templates/external_rp_form.html` + routes `GET/POST /directory/external[/{id}][/new|/edit]`), kept separate from the plantilla-shaped internal `staff_form.html`: honorific dropdown (Mr./Ms./Mrs./Dr./Engr./Atty.), required name, optional agency + email. The directory's External section now shows Name/Agency/Email columns + an Edit link, and a "+ Add external resource person" button. Verified: add/edit roundtrip persists all fields, internal-via-external-edit guard redirects, directory renders the new columns.
- **Wiped the entire external resource-person registry for a fresh start** (user request — "remove them all"). `wipe_external_rps.py`: set-based, child→parent deletes with FK enforcement off for the batch + a `PRAGMA foreign_key_check` that PROVES no dangling refs before commit. Removed **155 external RPs + 954 Type-3 speaker forms + 5,290 responses**; **45 BLHSD staff and all Type-2 event data untouched** (event feedback is keyed by activity/org, not resource_person). Consistent backup `_backups/css_is_20260611_232703_pre_external_wipe.db`; result: 0 orphans, fk_check clean, integrity ok, audit chain ok, `external_wipe` audited. (Lesson: `cp` of the live DB makes a torn snapshot → use the SQLite backup API for copies; row-by-row `delete_speaker` tripped the `event_form`/`response` FKs, so the wipe is set-based.)
- **Note:** done under explicit "allow everything, I'll check afterwards" authorization while a parallel honorific workstream was co-editing `app.py`/`name_cleanup.py`/`staff_form.html`. Verified my edits survived. pytest + qa_smoke green; the dev server was down (nothing on :8000) so the in-place wipe had no lock contention.

## 2026-06-11 (Home hub — task-oriented landing)
- **NEW role-aware home at `/` ("What would you like to do?")** replacing the old landing behaviour (managers were dropped straight onto the create-activity form; everyone else onto Pulse). `templates/home.html` extends the dash layout (top nav stays). A **glanceable stats strip** — responses in the last 30 days, people rated (distinct non-archived speakers/staff), overall satisfaction (top-2-box % positive, computed per each survey type's scale: ARTA 1-5, F2/F3 1-7), and all-time responses collected — over a grid of **task-module cards filtered by capability**: *See how we're doing* (`/dashboard`, all) · *Official reports* (`/reports`, all) · *Enter paper responses* (`/encode`, encode) · *Run a survey* (`/create`+`/arta`, create_activity) · *Directory & people* (`/directory` incl. the name cleanup tool, directory) · *Administration* (users/audit/backups/health, manage_users). Each card has a primary link + sub-link pills. No new permissions — cards gate on the existing capability map.
- **Routing:** the create-activity form moved from `GET /` to **`GET /create`** (it always lived behind the `create_activity` cap via `/create`'s gate; the POST handler was already there). `home_stats()` memoises the heavy atoms calc against the atoms cache + current month; the open-survey count is a tiny live query. Nav updated: brand → `/`, "New survey" → `/create`, new `home` active-state.
- **Verified:** renders 200 for every role with the right card count (viewer 2 → encoder 3 → section_manager 4 → admin 6); stats compute (111 this month, 82% positive, 40,986 all-time); `GET /create` still serves the form; live screenshot of the admin hub. pytest + qa_smoke green; production `css_is.db` untouched.

## 2026-06-11 (Name cleanup tool — external resource-person directory)
- **NEW temporary admin tool `/directory/cleanup`** to fix the resource-person roster fast (user request: "create a temporary UI at the directory to help me fix all of this names faster"). Directory-gated (section_manager+); linked from the top of `/directory`. Lists all 218 resource persons with auto-detected flags — **ALL-CAPS** (11), **honorific prefix** (125), **roster** (one field holding several people, 17), and **duplicate candidates** (92) — plus client-side search + filter chips with live counts.
- **Per-record one-click actions:** proper-case an ALL-CAPS name (`RAY JUSTIN VENTURA`→`Ray Justin Ventura`, preserving initials `T.`/roman numerals/credentials), strip leading honorifics (`Dr.`/`Ms.`/`Ma'am`… — but NOT Filipino `Ma.`=Maria), inline rename, archive/hide a non-person, **merge** a duplicate (one-click "fold in" for each suggested dupe, or pick any record via a shared datalist), and **split** a roster (each parsed name pre-resolved to the best-matching existing person via a dropdown, with skip; ratings are duplicated to every individual). Bulk "Fix all ALL-CAPS" button.
- **Backend `name_cleanup.py`** reuses the proven `apply_speakers` machinery (`merge_speaker`/`copy_instance_to`/`delete_instance`/`split_roster`) so a split duplicates each session's ratings per person exactly as the earlier roster passes did. A higher-recall candidate matcher (token-subset / shared-token / typo-fuzzy) surfaces sub-name duplicates `storage.names_match` misses (`Corachea`⊆`Andrea Corachea`, `Ross Rosales`⊆`Dr. Ross Jacob Rosales`). **Internal-name rule enforced:** a merge involving exactly one internal (plantilla) record always keeps the internal record as the survivor, regardless of merge direction.
- **Safety:** first destructive op of a server run takes one automatic `_backups/css_is_*_precleanup.db` snapshot (plus a manual "Save restore point" button); every op is audited (`name_cleanup`/`name_cleanup_merge`/`name_cleanup_split`/`name_cleanup_backup`) and busts the atoms cache. Nothing is auto-applied — the operator confirms each change.
- **Verified:** all ops exercised on a DB copy (rename/strip/title-case/archive/merge incl. internal-protection swap/split) → 0 orphans, audit chain intact; full HTTP layer driven via TestClient on a copy (all routes 303, audit rows written, chain ok); live UI screenshotted (filters, merge fold-in suggestions for Andrea Corachea, split of `Rosales, Loyola, Gawilan, Garcia, Baldonado` each pre-resolved). **pytest 109 passed**; production `css_is.db` untouched by the build.

## 2026-06-10 (QA pass — Cowork)
- **P0 (app down) FIXED:** `app.py` was truncated mid-statement (SyntaxError) — the build did not start. Truncation also dropped `_token_of`/`_qr_data_uri`/`_build_qrs`, which `/create` and `/arta` call (would NameError). Restored tail from snapshot + reconciled with current code. 2278→2324 lines.
- **P0 (Activities 500) FIXED:** `templates/activities.html` truncated mid-tag (`{% en`) → Jinja TemplateSyntaxError on `/dashboard/activities`. Restored the pager block. 151→157 lines.
- **P1 (process):** `.git` is an empty skeleton (0 objects/commits) — the claimed "git per cycle / revert to roll back" safety net never persisted in this mount. Root cause of both P0s: in-app file tools silently truncate large files. Recommend shell-only edits + a real repo on the host, and `python -c "import app"` as a delivery gate.
- **NEW regression suite:** `tests/` (pytest, 84 tests: routes/auth+RBAC/input-abuse/integrity), `pytest.ini`, `run_tests.sh`. Runs on a throwaway DB copy.
- **qa_smoke.py:** added backward-compatible env knobs (QA_SAMPLE/QA_FORMATS/QA_GRAINS) for a fast subset; defaults unchanged.
- **Verified green:** 84/84 pytest pass; export smoke passes all 6 formats; `integrity_check=ok`, 0 orphans, unique tokens; 40,935 responses / 449,423 atoms; PERF-3 resolved (Activities ~0.22s warm). `css_is.db` not modified. Originals in `_backups/qa_20260610_210455/`. Full report: `QA_FINDINGS_2026-06-10.md`.

## 2026-06-11
- **Performance monitoring + audit hooks — completes the "perf monitoring + backups" task.** New `monitoring.py`: in-memory rolling window (last 2000 requests) behind a thread lock, exposing the **four golden signals** — traffic (req/min, totals), latency (p50/p95/p99/max over 5 min), errors (5xx/4xx counts + rate), saturation (in-flight + peak, slow >1s count, DB size + growth-since-start). Path bucketing collapses ids/tokens (`/r/{token}`, `/directory/person/{id}/edit`) so the per-route table stays low-cardinality. Structured **per-request JSONL log** → `requests.log` (size-rotated at 5 MB → `.1`; best-effort, never breaks a request). A second outermost `@app.middleware` (`_metrics_gate`) times every request, counts by status (records 500 on handler exceptions), and logs it. **`GET /health`** — public liveness/readiness JSON (process up + `SELECT 1`; 200 ok / 503 degraded). **`GET /ops`** — admin dashboard (gated via `_required_cap` → manage_users): golden-signal cards, integrity+backup status (audit-chain check + backup schedule), per-route latency table, recent-request log tail; template `templates/ops.html`; nav link added. DB-growth baseline captured at startup. **Missing audit hooks added:** login (`login`/`login_failed`/`first_run_admin`), `logout`, and directory CRUD (`directory_add`/`directory_edit`/`directory_delete` for divisions/sections/bureau/people/external-orgs/photos, plus `clear_sample_data`). Verified: 9 new pytest in tests/test_monitoring.py (bucketing, percentiles, snapshot signals, health payload, /health public, /ops admin-only, logout/directory/failed-login audited) + full suite **109 passed**; qa_smoke 122 pass; live-checked /health + /ops on a demo copy (golden signals, per-route table, audit entry); production css_is.db untouched. Added `.gitignore` for runtime artifacts (requests.log, _backups/scheduled/, css_is_demo.db). Note: the metrics store + scheduler live in the single uvicorn worker (the documented run mode); /ops shows since-process-start, not historical.
- **Admin Backups module (/admin/backups) — easy self-service scheduled backups.** New `backups.py` engine: consistent snapshots via the SQLite backup API into `_backups/scheduled/` (separate from the hand-made pre-cleanup snapshots, never pruned together); make/list/prune/delete/restore + schedule config (in a new `app_setting` key/value table) + pure `is_due`/`next_due` arithmetic. In-process async scheduler (startup hook, 60s tick, `CSS_NO_SCHEDULER=1` opt-out) fires `run_scheduled_job` = **backup → prune to "keep newest N" → 6-month attendee-PII purge** (folds in the retention rule). Admin UI: status header (ON/OFF, next due, counts/sizes), schedule form (frequency h6/h12/daily/weekly + time + weekday + keep N + purge toggle), "Back up now", and a snapshots table with Download / **Restore** (typed RESTORE confirm + auto pre-restore safety snapshot, then `invalidate_atoms()`) / Delete. Routes under `/admin/backups*` (admin-only via the existing `/admin`→manage_users gate); every action audited (`backup_run`/`backup_settings`/`backup_restore`/`backup_download`/`backup_delete`/`backup_failed`). storage: get/set/get_settings. Verified: 11 new pytest in tests/test_backups.py (schedule math, prune-keeps-pre_restore, restore round-trip, job purges, RBAC, restore-needs-confirm) + full suite **100 passed**; qa_smoke 122 pass; live click-through on a demo copy (back-up-now → schedule ON/Weekly → next-due 2026-06-17 23:30 → snapshot row); production css_is.db untouched. Part of the queued "performance monitoring + backups" task (backups slice; golden signals / /health / /ops / request logs / directory+login audit hooks still to come).
- **E — Event link tree + attendee identity capture (Data Privacy Act).** New persistent `eve
## 2026-06-11 (UX redesign — Cowork, full execution)
- **ROOT CAUSE of recurring truncations found:** the agent-workspace mount truncates/zero-pads file tails when syncing large files. All file writes in this pass were made shell-side and verified (`python -c "import app"`, Jinja parse, null-byte scan) after every step; a real git history now exists for rollback (tags `pre-redesign` → `redesign-v1`).
- **P0 repairs before redesign:** `app.py` tail (dashboard routes + `_crumbs`/`_scope_ctx`/`_scoped`/`_nresp`, `/dashboard/report-pack` tail, `_token_of`/`_qr_data_uri`/`_build_qrs`) restored from `_backups` + bytecode; `storage.py` rebuilt 6 dropped functions (`load_atoms`, `get_form_context`, `search_form_instances`, `set_lead_org`, `lead_org_of`, `set_response_window`) from the cpython-314 bytecode constants — atoms SQL recovered verbatim; `dashboard_export.py` `_pack_pptx` tail; `dashboard_insights.py` `_rp_event_overalls` tail; `tests/conftest.py` `sample_ids` tail; `harmonize.py` `__main__` tail; null bytes stripped from `import_csm_blhsd.py`/`harmonize_report.md`; truncated sandbox copies of `encode_home/encode_form.html` re-mirrored. **`css_is.db` was corrupt (failed integrity_check)** — replaced from the newest clean snapshot `_backups/css_is_20260611_180449_prerosters.db` (41,092 responses, integrity ok); corrupt copy kept as `_backups/css_is_CORRUPT_kept_20260611.db`.
- **UX redesign (REDESIGN_PLAN.md, all phases):**
  - *Design system:* new `static/css/app.css` (tokens, components, focus rings, print/reduced-motion) + `static/js/app.js` (loading states, confirms, survey progress, expand/collapse, nav) + `templates/_components.html` macros + `templates/public_layout.html`; `/static` mounted & public-prefixed.
  - *Navigation:* `dash_layout.html` rebuilt — grouped role-aware dropdown nav (Dashboard / Data entry / Manage / Admin) with `aria-current`, mobile hamburger, breadcrumb block. Verified per role: viewer sees only Dashboard; admin sees all four.
  - *Every authenticated page now shares the layout:* converted `form_create`, `directory`, `staff_form`, `reports`, `verbatims`, `arta_link`, `result` from standalone HTML.
  - *Respondent (public) screens* rebuilt mobile-first on `public_layout`: `rating.html` (progress bar, question count + time estimate, equal-width segmented scales with end anchors, neutral N/A, anonymity note), `link_tree` (field-level required/optional marks, consent required client+server), `thanks` (what-happens-to-my-answers note, sequence celebration), `sequence`, `closed`, `login`, `forgot`, `set_password`.
  - *Manager dashboards:* activities — manager forms collapsed behind “⚙ Manage this event”, Expand/Collapse-all, clearer score labels; pulse — real empty states, sparkline aria-labels; people — affiliation counts now respect the active search, search-term highlighting, “no ratings yet” microcopy; person — breadcrumbs; reports — “How to read these numbers” legend (bands/flags/gap thresholds/item codes), report-pack download on page; verbatims — **pagination (?page=, 50/page replaces the hard 300 cap)** + survey-type filter pills + breadcrumbs.
  - *Encoder:* encode_home — public-window status column (Always open/Open/Not yet/Closed), Date/Responses sort, ＋New survey button; encode_form — sticky save bar with session counter + “Done — back to forms”, per-section counters, numbered items, neutral N/A, collected-on help text, mobile-stacking CSM grids.
  - *Feedback & a11y:* role-change now Apply-button + confirm (was silent auto-submit), deactivate confirms, audit log ip-toggle/was-now diff labels/chain-broken recovery hint, `data-loading` submit states, `:focus-visible` rings, `.table-wrap` overflow guards.
- **Behavior changes (exhaustive):** /static mount; verbatims pagination params; people counts after search; encode_home `sort` param + window state; users role-change needs Apply click. All form field names/values, routes, RBAC and POST semantics unchanged.
- **Verified:** full pytest suite green in chunks (**109/109**: rbac 41, routes 24, event_e 5, input_abuse 9, integrity 10, monitoring 9, backups 11); live TestClient walk-throughs — all 4 roles' nav + page access, full respondent journey (/e consent → /r rating → thanks → sequence-next), server-side consent/email validation, export PNG + report-pack PDF byte-checked. Work done on DB copies; the restored `css_is.db` only changed by the corruption fix above.
ck-office: bypasses the response window, defaults items to N/A, adds a "Date collected" field stored as `submitted_at` (the period a walk-in slip counts in). Every save audited as `manual_entry`; views invalidated.
- templates/encode_home.html, encode_form.html: NEW. dash_layout.html: `✎ Paper entry` nav link gated on `can(role,'encode')`.
- Verified end-to-end over HTTP on a temp DB copy (walk-in ARTA + Type-3 SERVQUAL, RBAC 403/404/redirect). Production css_is.db untouched; qa_smoke 122 checks pass.

## 2026-06-09
- migrate.py, verify_migration.py: NEW — idempotent migration of legacy spreadsheets + verifier.
- app.py: harden public `POST /r/{qr_token}` against malformed/out-of-range/hostile input and invalid served_by (BUG-1).
- app.py: anchor Jinja2 templates dir to module path so the app runs from any working directory (BUG-2).
- css_is_engine.py: assign_periods uses errors="coerce