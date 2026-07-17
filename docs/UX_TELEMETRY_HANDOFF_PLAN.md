# Passive UX-behavior telemetry — implementation handoff

**Status:** planned, not started.
**Owner:** avincentpatrick
**Source pattern:** `jongsky25/ofis-platform` — commit `7a7e369` ("Add passive UX-behavior
telemetry with a ranked improvement digest"). That build is live and working; this doc adapts
the same design to CSS-IS's stack (Flask + server-rendered Jinja + SQLite, not Next.js +
Supabase). Read the OFIS files before building here — they are the reference implementation,
not just prose:
`lib/telemetry.ts`, `app/components/Telemetry.tsx`, `app/api/telemetry/route.ts`,
`app/api/telemetry/digest/route.ts`, `app/(dashboard)/analytics/ux/`, migration
`061_ui_telemetry.sql`, tests in `__tests__/telemetry.ts`.

**Why:** CSS-IS already has one half of a friction-detection system — **Spot Feedback**
(`storage.py` `spot_feedback` table, `page_url` + `element_selector` per report, admin triage
board) — but that only captures what users *bother to type up*. It has no passive signal for
where staff silently struggle: rage-clicking a dead element, searching and getting nothing,
abandoning a form, hitting a client-side JS error. OFIS closes that gap with a small,
privacy-conscious event stream plus a **ranked digest** that says "fix this, it's at this
route, this element" — correlated with existing spot-feedback so a hotspot someone *also*
complained about jumps the queue. Same win applies here: this app has 60+ templates and a long
tail of admin/reporting screens; a ranked "what to fix first" list beats guessing from spot
feedback alone.

This is **not** a rebuild of Spot Feedback and **not** third-party analytics (no GA/Mixpanel/
session-replay). It is one new table, one small client-side capture script, one ingest route,
and one admin-only digest view — all first-party, all sanitized before it leaves the browser.

---

## 1. What OFIS built (the pattern to port)

Three layers, framework-agnostic in intent even though the reference is TypeScript:

1. **Controlled vocabulary of event types**, written passively, no explicit user action:
   - `pageview` — a screen was viewed (`meta.from` carries the previous route, powers nav-flow
     analysis)
   - `dead_click` — click on a non-interactive element (user expected something to happen)
   - `rage_click` — ≥3 rapid clicks within a small time/pixel window (frustration signal,
     weighted higher than dead_click)
   - `search_empty` — a search/filter returned zero results (`meta.term`, sanitized)
   - `client_error` — `window.onerror` / `unhandledrejection`
   - `form_abandon` — a form was edited, then the user navigated away without submitting

2. **Sanitize in the browser before anything leaves the tab, then re-sanitize server-side**
   (defense in depth, same shape as validating twice). Two masking rules do almost all the
   work:
   - **Route masking**: a concrete path (`/person/482/edit`, `/reports/activities/91`) is
     turned into a **pattern** (`/person/:id/edit`) by replacing UUID/numeric/date-shaped path
     segments. This de-PIIs the path (no attendee/person ids travel), stops the same screen's
     friction from fragmenting across every record, and — critically — **maps 1:1 back to a
     Flask route** so an opportunity in the digest is directly Grep-able to `app.py`.
   - **Text masking**: any run of 3+ digits (ids, phone numbers, dates baked into label text)
     becomes `###`, capped to a short length. No PII-bearing element text or search terms are
     ever stored raw.

3. **Pure aggregation + a ranked digest** — no ML, no LLM in the loop, deterministic and
   testable:
   - Group dead/rage clicks by (masked route, source anchor).
   - Score: `rageClicks × 3 + deadClicks`, damped by distinct-user count (one frustrated person
     spamming clicks can't dominate the board) — `users >= 3 → ×1`, `users == 2 → ×0.8`,
     `users <= 1 → ×0.6`.
   - **Correlate with existing feedback**: if a friction hotspot's masked route (+ selector,
     falling back to route-only) matches an open Spot Feedback item, boost its score (OFIS uses
     ×1.5) and attach the feedback text — "someone already complained about this exact spot."
   - Emit a ranked list of opportunities, each with a one-line deterministic **hint** ("Users
     rage-click this element — it looks interactive but does nothing...").
   - Side panels: top screens by views, nav flows, dead-end exit routes, failed search terms,
     client errors by route.

---

## 2. CSS-IS adaptation

### 2.1 Schema — new table, mirrors `spot_feedback` / `audit_log` conventions

```sql
CREATE TABLE IF NOT EXISTS ui_event (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    created_at      TEXT NOT NULL,              -- tz.now_local() ISO string, same as audit_log.ts
    user_id         INTEGER,                    -- nullable: public/link-tree pages have no admin_user
    role            TEXT,                       -- staffer role at capture time, if signed in
    session_id      TEXT NOT NULL,               -- client-generated per page load, groups one visit
    event_type      TEXT NOT NULL,               -- pageview | dead_click | rage_click | search_empty
                                                   -- | client_error | form_abandon
    route           TEXT NOT NULL,                -- masked route PATTERN, e.g. /person/:id/edit
    component       TEXT,                          -- nearest data-testid/data-tour anchor
    element_selector TEXT,                          -- short CSS path
    element_text     TEXT,                           -- sanitized text (digits masked, capped)
    meta_json        TEXT,                            -- JSON: {from}, {term}, {name,message}, etc.
    FOREIGN KEY (user_id) REFERENCES admin_user(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS ui_event_type_created_idx  ON ui_event(event_type, created_at);
CREATE INDEX IF NOT EXISTS ui_event_route_created_idx ON ui_event(route, created_at);
```

Add via the existing `init_db()` migration block in `storage.py` (same pattern as the
`spot_feedback` / `raffle_draw` / `event_link` additive blocks — `CREATE TABLE IF NOT EXISTS`
+ a `PRAGMA table_info` column-add guard if a field is ever added later). No `.oxlintrc`/Alembic
here; this repo's migrations are the additive-SQL-in-`init_db()` convention already used
throughout `storage.py`.

**Retention:** wire `ui_event` into `retention.py` alongside whatever purge window already
applies to `requests.log`/monitoring data — this is behavioral, not audit-of-record data, so it
does not need indefinite retention. Suggest a rolling 90-day purge, admin-configurable via
`app_setting` (`ui_telemetry_retention_days`), consistent with "no hardcoded policy numbers"
practice elsewhere in this codebase.

### 2.2 Capture script — a small vanilla-JS module, not a framework component

OFIS's `Telemetry.tsx` is a React client island; CSS-IS is server-rendered Jinja, so the port
is a plain `static/js/telemetry.js` loaded once from `dash_layout.html` (the shared
authenticated-shell template every dashboard page extends — confirm the exact include point,
likely near where `realtime.py`'s client script or the existing feedback-widget script is
already loaded).

Keep the same behavioral contract as the reference implementation:
- Batches events client-side (target ~10s flush interval or 25-event queue, whichever first —
  same constants OFIS uses, tune if needed).
- Ships via `navigator.sendBeacon('/telemetry', blob)` with a `fetch(..., {keepalive:true})`
  fallback — never blocks navigation, never surfaces an error to the user (best-effort, wrapped
  in try/catch).
- Flushes on `visibilitychange` (hidden) and `pagehide`, not just the interval — otherwise a
  user who navigates away inside the flush window loses the batch.
- Dead-click detection: click target has no ancestor matching an "interactive" selector list
  (`a, button, input, select, textarea, label, [role=button], [data-tour], [contenteditable]`,
  etc. — adapt to whatever roles/attrs this codebase's interactive elements actually use; check
  `templates/_components.html` for the shared button/link partials first).
- Rage-click detection: ≥3 clicks within ~800ms and ~24px of each other, with a cooldown so one
  frustration burst doesn't spam multiple rows.
- **Must ignore CSS-IS's own overlay UI** — the Spot Feedback widget's element-picker overlay
  and any print-only chrome — the same way OFIS excludes `[data-feedback-ignore],.no-print`.
  Find and tag the equivalent selector(s) here (the Spot Feedback picker in this codebase; grep
  `feedback.py`/`templates/feedback_board.html` and the front-end widget for its overlay markup)
  before wiring the click listener, or every feedback submission will register as a rage-click
  on itself.
- **Route masking must run client-side before the event is queued**, using the same id/date
  pattern rules as `sanitizeText`/`maskRoute` in the OFIS reference (port the two functions
  near-verbatim — they're pure, framework-free, and directly portable to JS). CSS-IS route
  shapes to verify against: `/r/<token>`, `/directory/person/<id>/edit`, `/reports/activities/
  <id>`, `/monitor/<event_id>`, `/activities/<token>/manage` — `monitoring.py`'s existing path
  bucketing regex is a second precedent for this exact masking; reuse or align with it rather
  than inventing a third convention.

### 2.3 Ingest route

`POST /telemetry` (or `/api/telemetry` if this app reserves an `/api` prefix elsewhere — check
`app.py`'s route table first) — accepts a JSON batch, re-sanitizes server-side (never trust the
client mask alone), writes each event with `st.create_ui_event(...)`. No response body needed
beyond 204/200; keep it cheap, this fires constantly.

- **No CSRF token required** if this app's CSRF middleware already exempts `sendBeacon`-style
  fire-and-forget endpoints elsewhere (check how the existing feedback/monitoring beacons, if
  any, are exempted) — otherwise the beacon will silently fail CSRF and every event is lost.
  Confirm this explicitly; it is the single most likely reason a naive port ships broken.
- **Rate-limit it** — reuse `ratelimit.py`'s existing decorator/pattern the way other write
  endpoints do, capped generously (this is high-volume but low-value-per-request; a slow-loris
  on `/telemetry` shouldn't be able to fill the DB — cap batch size server-side too, e.g. reject
  batches over ~50 events).
- User attribution: if signed in, attach `user_id`/`role` from the session the same way other
  authenticated routes do; if the endpoint is reachable from public/link-tree pages, allow
  `user_id NULL` (do not require auth to record telemetry on public registration pages, but
  scope the digest's "top screens" view to note which routes are public vs. staff-only so the
  two audiences aren't confused in the ranking).

### 2.4 Digest + admin surface

Port `lib/telemetry.ts`'s pure aggregation functions (`topRoutes`, `navFlows`,
`emptySearchTerms`, `errorsByRoute`, `exitRoutes`, `frictionByTarget`, `frictionScore`,
`correlateFeedback`, `buildDigest`) into a new `ui_telemetry.py` module — they're pure
functions over plain rows/dicts in the reference, which translates directly to Python with no
framework dependency. Unit-test them the same way OFIS does in `__tests__/telemetry.ts`: no DB,
just list-of-dict fixtures in, `Digest` dict out. Add `tests/test_ui_telemetry.py` following
this repo's existing pure-function test style (see `tests/test_comment_bucketing.py` or
`tests/test_verbatim_sentiment.py` for the local convention of testing aggregation logic
without a DB).

`correlateFeedback` is the one place this needs real CSS-IS wiring, not just a port: match on
`ui_event.route` (masked) against `maskRoute(spot_feedback.page_url)`, and `element_selector`
where present, falling back to route-only — reuse `st.list_spot_feedback()` for the feedback
side of the join.

**Admin surface:** new `templates/ux_insights.html` + a `dashboard_insights.py` function (this
module already builds the other admin analytics views — `dashboard_insights.py` is the natural
home rather than a new top-level module) rendering the digest: ranked opportunities table
(route, component/selector, score, signal breakdown, matched feedback, hint), plus the side
panels (top screens, dead-end exits, failed searches, errors). Gate it exactly like the
existing admin-only surfaces (`/admin/feedback.json`, `/backups`, `/ops`) — reuse whatever
decorator restricts those (likely `admin`-role check in `auth.py`). Add a nav entry in
`NAV_GROUPS` (`app.py`) so it's discoverable and Ctrl-K-searchable, same as the Outside Events
plan did.

---

## 3. Guardrails specific to this codebase

- **Privacy first, same standing rule as Spot Feedback screenshots and the existing masking in
  `feedback.py`**: no attendee/person names, TINs-equivalent identifiers, emails, or free-text
  survey answers may ever reach `ui_event`. The sanitizers are not optional polish — they are
  the reason this feature is safe to ship at all. Route + element **structure**, not content.
- **No third-party analytics, no session replay** — same as OFIS. This must stay first-party,
  in the existing SQLite DB, covered by the existing backup (`backups.py`/`pull_backup.py`) and
  retention (`retention.py`) machinery. Do not introduce a new vendor dependency for this.
- **Respect the "large file" / sandbox-corruption lessons in `docs/QA_PLAYBOOK.md`** if this is
  built inside the Cowork sandbox — `storage.py` and `app.py` are both already large files that
  have hit truncation bugs; edit via the documented native/host path, not the sandbox mount, and
  re-run `qa_preflight.py` before declaring done.
- **`RUNTIME_PY` in `deploy_hf.py`** — if `ui_telemetry.py` (or wherever the aggregation module
  lands) is a new top-level `.py` module, it **must** be added to the `RUNTIME_PY` list in
  `deploy_hf.py` or it will silently not deploy to the live HF Space. This has bitten this repo
  before; don't repeat it.
- **Version bump + CHANGELOG** — `deploy_hf.py` enforces an `APP_VERSION` bump and a
  plain-language `CHANGELOG.md` entry on deploy, per this repo's existing release discipline.

---

## 4. Build order

1. **Schema** — `ui_event` table in `storage.py` `init_db()` + `st.create_ui_event` /
   `st.list_ui_events` helpers. Unit test the round-trip (mirror `test_spot_feedback.py`'s
   storage-roundtrip test).
2. **Capture script** — `static/js/telemetry.js`, wired into `dash_layout.html`. Verify by hand
   locally: click a dead element, rage-click something, trigger a JS error, confirm rows land in
   `ui_event` via the ingest route.
3. **Ingest route** — `POST /telemetry` in `app.py`, CSRF-exempted (verified, not assumed),
   rate-limited, server-side re-sanitization.
4. **Aggregation module** — `ui_telemetry.py` port of the pure functions + `tests/
   test_ui_telemetry.py`.
5. **Admin digest view** — `dashboard_insights.py` function + `templates/ux_insights.html` +
   nav entry, admin-gated.
6. **Retention wiring** — `retention.py` purge job + `app_setting` for the window.

Each step is independently deployable/testable; ship 1–3 first if you want the minimal useful
slice (raw events land, even before the ranked digest exists), then 4–6.

## 5. Testing

- Unit: sanitizer functions (route masking, text masking) — exact-value tests including the
  edge cases OFIS's suite covers (trailing slash, UUID vs. numeric vs. date segment, empty
  input).
- Unit: aggregation functions on fixture rows — no DB.
- Storage roundtrip test — mirror `test_spot_feedback.py` style.
- Route test: `/telemetry` accepts a batch, rejects an oversized one, writes sanitized rows even
  if the client sends unsanitized text (defense-in-depth check — deliberately POST a raw digit
  run and assert it comes back masked).
- Manual: full click-through per §4 step 2, then confirm the digest ranks it and that an
  existing/seeded Spot Feedback entry on the same route boosts the score and shows up attached.
- Gate before done: full `pytest` + `qa_smoke.py`, per this repo's standing rule.

## 6. Out of scope (explicitly)

- Session replay / screen recording of any kind.
- Any cross-request user profiling beyond the existing `session_id`/`user_id` grouping already
  described above.
- Sending any of this data to a third-party service (analytics vendor, error-tracking SaaS).
- Reworking Spot Feedback itself — this plan only *reads* it for correlation.
