# Search + assistant on the home page — phased build plan (handover)

**Status:** planned, not started. This document is the build spec. Hand it to the
implementing agent as-is.
**Owner:** avincentpatrick

**Decisions already made (do not re-open them):**
- Build **all four parts**: move search to the home page, widen search, widen the
  assistant, and test and roll out.
- Colleagues' **basic status is visible to everyone** who is signed in. "Basic"
  means only in the office / from home / field / on leave / off. It never
  includes a note, a place, or a reason.
- **`/css` keeps its own search,** limited to CSS.

**Build discipline (same as `docs/AI_INTEGRATION_PLAN.md`):**
- One phase = one PR = one `APP_VERSION` bump (6.3, 6.4, …) with a plain-language
  CHANGELOG entry (see `version.py` lines 8-16).
- `bash run_tests.sh` must be green, and the phase's acceptance checks must pass,
  before the next phase starts.
- Do not build ahead of the current phase.
- Each phase lists the files it may touch. If a phase seems to need a file that is
  not listed, stop and say so in the PR rather than widening it.

---

## 0. What exists today (checked against the code, 2026-10-09)

| Thing | Where | Fact |
|---|---|---|
| New home | `GET /` → `choose()` `app.py:4945`; `templates/office_connect.html`; data in `office_connect.py` | "Hi, Jong 👋", companion, Team/Me/Calendar tabs, "Your to-do" (`home_tasks`, `office_connect.py:1178`). **No search box, no assistant link.** |
| CSS hub | `GET /css` → `home()` `app.py:5072`; `templates/home.html` | Holds "What would you like to do, Jong?" (`:149`), "✨ Try the assistant" → `/start` (`:153`), and the inline search box `form.gsearch[data-search]` (`:158-166`). |
| Search engine | `static/js/search.js` | One engine with two mounts: the Ctrl/⌘-K palette (`initPalette`) and any `form[data-search]` (`initInline`). The page index is `window.SEARCH_INDEX` from `search_index_for()` `app.py:803`, which only contains pages the user's role allows. |
| Palette on phones | `search.js:319` | Looks for `#navSearchBtn`, but **no template renders it**. On a phone the palette cannot be opened at all. `home.html` also shows a "Ctrl K" hint on touch screens. |
| Record search | `GET /api/search` `app.py:5598` | Only **Activities** (top 5) and **People** (resource persons, top 5). No rate limit. The `search.js` header says it searches "comments", but it does not. |
| Assistant | `/start` (`app.py:5215`, `start.html`, `start.js`); `POST /api/ai/route` `app.py:5882` | FAQ rules first, then the model picks from server allow-lists. Answers come from `AI_ANSWER_SLOTS` (`app.py:866`): 12 CSS-stat slots plus 8 calendar slots (`calendar_answers.py`). The model never sees the data; the server renders it. |
| Assistant blind spots | — | To-dos, approvals, wellness hours, AWA filing, who is in the office, the conference room, colleagues. |
| Who-is-where data | `storage.work_arrangement_day` `:9555`, `whereabouts_roster_week` `:10062` | **Deliberately team-scoped** through `team_scope_for_user(area="awa")` `:7170`. An unlinked account gets `"none"`. Note: `calendar_answers._away` already shows "who is away" bureau-wide. |
| Rooms | `rooms.py` | One conference room with time slots: `slot_states(conn, day)` `:160`, `list_for_user` `:216`. |

---

## Phase 1 — Search and assistant move to the home page (v6.3)

**Goal:** the home page gets the search box and the assistant entry point. Phones
can open search. The CSS hub stops greeting people as if it were the home page.
**Touch:** `templates/_search_box.html` (new), `templates/office_connect.html`,
`templates/home.html`, `templates/dash_layout.html`, `static/css/app.css`,
`tours.py`, `tests/test_search.py`, `tests/test_landing_fork.py`,
`tests/test_office_connect.py`.

1. **Shared macro.** Create `templates/_search_box.html` with a
   `search_box(placeholder, scope="all", tour=None)` macro.
   - Move the exact `form.gsearch` markup there from `home.html:158-166`.
   - Add `data-scope="{{ scope }}"` to the form.
2. **Home page.** In `office_connect.html`, render the macro right after the hero
   (after the birthday blocks, before "Your to-do").
   - Do not render it in the Calendar tab, which stays bare.
   - Placeholder: "Search people, pages, your calendar — or ask a question…".
   - Next to the box, add `<a class="try-assistant" href="/start">✨ Ask the assistant</a>`.
   - Move the `.try-assistant` styles into `app.css` if they live in `home.html`.
3. **Header button on every page.** In `dash_layout.html` `.right`, for signed-in
   users, add `<button id="navSearchBtn" type="button" aria-label="Search (Ctrl K)">`
   with the magnifier SVG, before the ⚙ menu.
   - `search.js` already wires it up.
   - It must show at phone width.
4. **Hide the "Ctrl K" hint on touch screens.** In `app.css`:
   `@media (hover:none), (max-width:640px) { .gs-kbd { display:none } }`.
5. **CSS hub.**
   - In `home.html`, change the `<h1>` to "CSS hub" and keep the `.hsub` line.
   - Remove the "✨ Try the assistant" link.
   - Keep the box (it is limited to CSS in Phase 2) but render it through the macro
     with `scope="css"` and the placeholder "Search CSS — activities, resource
     persons, reports…".
6. **Tours.** Find the step that targets `[data-tour="search"]` with
   `grep -n 'data-tour\|search' tours.py`. Point it at the home page box and give
   the home box `tour="search"`. Make sure no tour step targets an element that no
   longer exists.
7. **Tests.**
   - `test_landing_wires_the_search_box` now asserts on `/` (box, `SEARCH_INDEX`,
     `search.js`).
   - Add a test that `/` with `view=calendar` has no inline box.
   - Add a test that `/css` has `data-scope="css"` and no "What would you like to do".
   - Add a test that `#navSearchBtn` renders for a signed-in user and not on the
     login page.

**Acceptance:**
- At 390px wide, the home page shows the box under the greeting, the header 🔍 opens
  the palette, and no "Ctrl K" hint shows.
- Typing "trends" on the home page lists the Trends page.
- `/css` reads "CSS hub".
- Full test suite green. Bump `search.js?v=`.

---

## Phase 2 — CSS-only search on `/css` (v6.4)

**Goal:** the box on `/css` searches only CSS. It offers one way out to search
everything.
**Touch:** `static/js/search.js`, `app.py` (only `api_search` and
`search_index_for`), `tests/test_search.py`.

1. **Index entries know their module.** In `search_index_for`, add a `mod` key to
   each entry: the group's `name` lower-cased (`"css"`, `"wellness"`, `"awa"`,
   `"administrator"`). The three fixed entries get `mod: "core"`.
2. **Scoped matching in `search.js`.**
   - `attach(opts)` takes `opts.scope`, and `initInline` reads it from
     `form.dataset.scope`.
   - When the scope is not `"all"`, rank only entries whose `mod` matches.
   - `_fetchDB` appends `&scope=<scope>` to the request.
3. **Server side.** `api_search` takes `scope: str = "all"`. Any scope other than
   `"all"`/`"css"` is treated as `"all"`. Today both sources are CSS, so the
   behaviour is unchanged. The parameter matters from Phase 3.
4. **The way out.** When the box is scoped, the last row is
   `Search everything for “<q>” →`. Picking it opens the global palette with the
   query filled in.
   - Expose `open(q)` from `initPalette` on `window.CSSSearch.openPalette`.
5. **Fix the header comment** in `search.js` so it no longer claims comments are
   searched.
6. **Tests.** On `/css`, `SEARCH_INDEX` entries carry `mod`. Use a small pure-Python
   check of the scoped filter, or assert on the rendered `data-scope`.
   `/api/search?scope=css` returns only Activities and People sections.

**Acceptance:**
- On `/css`, "wellness" finds nothing except the "Search everything" row.
- On the home page, "wellness" finds the Wellness pages.

---

## Phase 3 — `/api/search` becomes a list of sources (no visible change) (v6.5)

**Goal:** make adding sources safe and cheap before adding any.
**Touch:** `search_sources.py` (new), `app.py` (`api_search`), `ratelimit.py`,
`deploy_hf.py` (`RUNTIME_PY` list), `tests/test_search.py`.

1. **New module `search_sources.py`.** Each source is a dict
   `{key, section, scopes: {"all","css",…}, run(conn, user, terms, ctx) -> list[row]}`.
   - A row has the existing shape `{title, hint, url, section, kw}`.
   - `ctx` carries `get_atoms`, `view_memo`, `is_chief`, and `today`. Pass callables
     in from `app.py` so the module does not import `app`. This is the same pattern
     as `office_connect.team_view_data`.
2. **Move the two existing sources into it unchanged.** Activities and People keep
   identical queries and limits.
3. **`api_search` loop.**
   - Loop over the sources for the requested scope.
   - Wrap each `run` in `try/except Exception` with a log line. One broken source
     never breaks search; this is the same rule as `home_tasks`.
   - Cap each section at 5 rows and the response at 30.
4. **Rate limit.** Add a `ratelimit` bucket `"search": (120, 60)`, keyed by account
   id (`str(user["id"])`), the way the `card` bucket is keyed. Over the limit, return `[]`.
5. **Deploy list.** Add `search_sources.py` to `deploy_hf.RUNTIME_PY`. The existing
   `test_deploy_hf.py` guards this.
6. **Tests.**
   - All existing `/api/search` tests still pass, untouched.
   - New: monkeypatch a source to raise, and the others still return.
   - New: the 121st call in a minute returns `[]`.

**Acceptance:** no visible change for users, and response shape and order are
identical. This is a pure refactor.

---

## Phase 4 — Search the rest of the office (own data and shared pages) (v6.6)

**Goal:** the home box finds things across every module. Each new source uses the
same function, with the same visibility rules, as the page it links to, so search
can never show something the page would not.
**Touch:** `search_sources.py`, `tests/test_search_sources.py` (new). Read-only
calls into `office_calendar`, `office_connect`, `rooms`, `storage`, `tours`.
**Do not add new SQL** when an existing function already answers.

| Section | Source function (reuse) | Matches on | Link | Scopes |
|---|---|---|---|---|
| Calendar | `office_calendar.items_between(conn, user, today-30d, today+90d, scope="blend", layers=["entries","activities"])`, without banners, cancelled or postponed items | title | `/calendar/entries/{id}` for entries; the activity's own link otherwise (check the item dict) | all |
| My to-do | `office_connect.home_tasks(conn, user, today)` | title + detail | the task's `url` | all |
| My requests | `st.list_my_wellness_claims` (own), `st.my_work_arrangement_for` / `my_pending_work_arrangement` (current open period) | "wellness", date, arrangement label, status | `/wellness`, `/work-arrangement` | all |
| Conference room | `rooms.list_for_user(conn, uid, upcoming_only=True)` plus a fixed "Book the conference room" row when the query mentions room, conference or book | title, date | the reservation page that `rooms_routes` already links to (grep `list_for_user` callers for the URL) | all |
| Help | `help_catalog_for(user, is_chief)` (pass it in through `ctx`) | label + step text | the section's `url` with `?tour=1` | all |

- Only search a source when the query is at least 2 characters.
- Calendar results: at most 5, nearest date first.
- Never put a calendar entry's notes or meeting link in the `hint`. Use date,
  time, and "tentative" only, the same as `calendar_answers._line`.
- **Tests:** one test per source, plus:
  - another user's private calendar entry is not found;
  - an approver does not see other people's wellness claims through "My requests";
  - `scope=css` returns none of these sections.

**Acceptance (seed DB):**
- "audit" on the home page finds the 13:00 HEMB Auditor meeting.
- "wellness" finds the to-do and the Wellness pages.
- "room" finds the booking row.

---

## Phase 5 — Colleagues and their basic status, visible to everyone (v6.7)

**Goal:** search for a colleague and see their unit and today's basic status. This
is the "show basic status to everyone" decision. It is a deliberate widening of
who can see whom, so it is built as narrowly as possible and can be switched off.
**Touch:** `storage.py` (one new function), `search_sources.py`, `app.py` (one new
route, one admin setting), `templates/colleague.html` (new), the admin settings
template that holds AWA settings (grep `bureau_access` or `work_arrangement` in
`templates/admin_*.html`), and `tests/test_colleague_status.py` (new).

1. **New `storage.basic_status_for_day(conn, day) -> {user_id: state}`.**
   - Covers every active account linked to a non-archived directory person,
     bureau-wide.
   - `state` is exactly one of `"onsite","wfh","field","leave","off","unknown"`.
   - Use the same precedence as `work_arrangement_day`: what the person reported
     (`whereabouts_for_day`) beats a calendar trip (`cal_travel_defaults`), which
     beats the fortnight filing. A holiday or weekend gives `"off"` for everyone.
   - **Refactor, don't copy.** Pull the per-person state resolution in
     `work_arrangement_day` into a private helper that both call. That way the
     team page and this function cannot disagree.
   - The roster must come from an **unscoped** query of linked staff. Never call
     `work_arrangement_roster(conn, ps, user)` with the viewer: it is
     scope-filtered on purpose.
   - **Never returned:** note, remarks, field location, leave type or reason,
     arrangement label, `undeclared`, `plotted`. Add a test that the returned dict
     values are bare strings.
   - Memoize per `(db, day)` for 60 s with the existing `view_memo` pattern; search
     calls it on every keystroke.
2. **Admin switch.**
   - Setting `colleague_status_scope`: `"bureau"` (default, per the decision) or
     `"team"`. In `"team"`, filter the result to `team_scope_for_user(conn,
     viewer, area="awa")`, so `"none"` shows no status.
   - Put it on the admin page that already holds AWA and bureau-access settings,
     with one line of help text: "Who can see whether a colleague is in the office
     today."
3. **Colleagues search source.**
   - Match against the directory: name, nickname (`calendar_people` aliases if
     cheap), position, and unit name.
   - Hint: `Position · Unit · In the office today` (labels: In the office / Working
     from home / In the field / On leave / Off today / no status).
   - Link: `/people/{user_id}`.
   - Scope `all` only.
   - Cap at 5. Exact first-name and nickname matches rank first.
4. **New page `GET /people/{user_id}`** (signed-in only; 404 for an unknown or
   unlinked id). A small read-only card showing:
   - photo or initials, name, position, unit;
   - today's basic status (respecting the switch);
   - "Away in the next 7 days" from `office_calendar.items_between(conn, viewer,
     …, scope="bureau", layers=["entries","leave"])`, filtered to this person, with
     the same fields `calendar_answers._away` uses. That makes the calendar's own
     visibility rules the gate.
   - shared birthday (only if `birthdays.shared_with` allows);
   - "Send a birthday card" when `card_celebrants` includes them.
   - **No** email, phone, notes, filing history, wellness data, or reasons.
5. **Unchanged:** `/work-arrangement/day`, the roster, and the home "5 in the office
   today" card stay team-scoped exactly as now.
6. **Tests.**
   - An unlinked viewer sees status when the switch is `"bureau"` and does not when
     it is `"team"`.
   - A leave note and a field location never appear in `/api/search`, `/people/{id}`,
     or the page HTML.
   - A weekend and a holiday read "Off today".
   - A reported status beats the filing.
   - `/people/{id}` returns 404 for an unknown id, and redirects to login when
     signed out.

**Acceptance:** "jong" on the home page shows "Jong … · In the office today", and
the card opens. Switching the setting to "team" hides status for someone outside
your section.

---

## Phase 6 — The assistant answers about the whole office (v6.8)

**Goal:** add answer slots for the new modules in the same style as
`calendar_answers.py`. The model only picks a slot key. The server writes the
sentence from the asker's own data, so names and records never reach the model.
**Touch:** `office_answers.py` (new), `app.py` (merge the slots, add a seed-rules
function, one line in the router system prompt), `deploy_hf.py`,
`tests/test_office_answers.py` (new).

1. **`office_answers.py`.** Copy the shape of `calendar_answers.py`:
   - a `SLOTS` dict of `{label, kw, user_render(conn, user, today) -> str}`;
   - a `SEED_RULES` list;
   - `MAX_LINES = 6`.

| Slot key | Answers | Built from |
|---|---|---|
| `todo_summary` | "What's on my to-do?" | `office_connect.home_tasks`, titles only, in its order |
| `approvals_waiting` | "Do I have approvals?" | `st.pending_approval_counts` |
| `wellness_left` | "How many wellness hours do I have left?" | `st.wellness_hours_used` + `WELLNESS_WEEKLY_HOURS`, plus the next approved break |
| `awa_status` | "Did I file my AWA?" / "When is the AWA deadline?" | the same calls as `office_connect._task_awa` |
| `office_today` | "Who is in the office today?" | counts plus first names per state from `basic_status_for_day` (respects `colleague_status_scope`), at most 6 names per state, then "…and N more" |
| `wfh_today` | "Who is working from home today?" | same, `wfh` only |
| `room_today` / `room_tomorrow` | "Is the conference room free today/tomorrow?" | `rooms.slot_states` → free time windows (use `rooms.hour_label`); "closed" for a non-working day (`rooms.is_working_day`) |
| `my_room_bookings` | "My room bookings" | `rooms.list_for_user(upcoming_only=True)` |

2. **Seed rules.** Add `_seed_office_rules(conn)` next to `_seed_calendar_rules`
   (`app.py:1512`), with its own marker setting `office_rules_seeded`. These answers
   then work with no model call and **while AI is switched off**. Include Tagalog or
   Taglish variants ("sino ang nasa opisina", "ilan oras wellness ko").
3. **Merge.** `AI_ANSWER_SLOTS.update(office_answers.SLOTS)` right after the
   calendar merge (`app.py:949`). `_render_answer` already handles `user_render`.
4. **Router prompt.** Add one sentence to `_ai_router_system_prompt`: the assistant
   can answer about the asker's own to-dos, wellness, AWA, room, and who is in the
   office.
   - Do **not** put any data in the prompt.
   - Check that the Answers catalog stays under the prompt-size budget in
     `ai_core.FEATURE_DEFAULTS`.
5. **Tests.**
   - Each slot renders for a user with no data ("You have nothing on your to-do").
   - Each seed rule routes to its slot with AI mode `"off"`.
   - `office_today` honours the `"team"` switch.
   - No slot output contains a whereabouts note.

**Acceptance:** on `/start`, "who's in the office today", "free ba ang conference
room bukas", and "how many wellness hours left" all answer correctly, with AI on
and with AI off (through the rules).

---

## Phase 7 — One box: search and ask together on the home page (v6.9)

**Goal:** people don't have to choose between "search" and "assistant". The home
box does both.
**Touch:** `static/js/assistant.js` (new; extracted from `start.js`),
`static/js/start.js`, `static/js/search.js`, `templates/_search_box.html`,
`templates/start.html`, `app.py` (one optional slot with an argument),
`static/css/app.css`, `tests/test_ai_router.py`, `tests/test_search.py`.

1. **Extract `assistant.js`.** Move the `/api/ai/route` call, answer-card render,
   Confirm-card flow, and 👍/👎 posting out of `start.js` into
   `window.CSSAssistant.ask(q, mountEl)`.
   - `start.js` becomes a thin caller.
   - **`/start` must behave exactly as before.** Its existing tests must pass
     untouched.
2. **"Ask" row in the box.** In `search.js`, when the box's scope is `"all"` and the
   query looks like a question, insert a first row: `✨ Ask: “<q>”`.
   - A query looks like a question when it ends in `?`, or starts with who, what,
     when, where, how, is, am, do, does, can, sino, ano, kailan, saan, ilan, or
     may, or is 4 words or more.
   - Choosing that row calls `CSSAssistant.ask` and renders the answer card inside
     the dropdown, above the normal results. The normal results stay underneath.
   - Navigate results still navigate.
   - With AI off, the rules layer still answers. On a `fallback` reply, drop the
     row and keep the normal results.
3. **Optional: a `person_status` slot with one argument.** Use this for "Where is
   Mimi today?".
   - The model returns `{slot:"person_status", args:{name}}`.
   - The server resolves `name` with `calendar_people.match` against the directory.
     With no match or more than one, it answers "I couldn't tell who you mean",
     with links to the matches.
   - The server renders only the basic state, and respects the switch.
   - Validate it like `_ai_validate_action_args`, so the model's text never becomes
     output.
   - **Skip this item if it pushes the phase past one reviewable PR.** It can be its
     own v6.10.
4. **`/start` stays.** It is still a full-page assistant, linked from the home box.
   Leave the `ai_landing_default` setting alone, but change its help text on
   `/admin/ai`: the home page now carries the assistant too.
5. **Tests.**
   - The question heuristic, as a JS-free Python mirror if one exists; otherwise
     assert the markup hooks.
   - `/start` HTML still loads `start.js` and now `assistant.js`.
   - The `person_status` validation rejects names that are not in the directory.

**Acceptance:**
- On the home page, typing "who is in the office today?" shows the answer in place.
- Typing "trends" shows only page results, with no Ask row.
- `/start` is unchanged.

---

## Phase 8 — QA sweep and handoff (v6.10, or v6.11 if Phase 7 was split)

**Touch:** tests and docs only, plus any small fixes the checks find.

- **Phone check.** Use Playwright with the pre-installed Chromium at 390×844 on `/`,
  `/css`, `/start`, and `/people/{id}`. Check:
  - no horizontal scroll;
  - the box is not covered by the "Send feedback" button (see the screenshot: it
    floats bottom-right);
  - the 🔍 button opens the palette;
  - the keyboard does not hide the results.
  Attach the screenshots to the PR.
- **Accessibility.**
  - The box is a combobox: `role="combobox"`, `aria-expanded`, and `aria-controls`
    on the input, `role="listbox"` on the list (already there).
  - Ask rows and answer cards are announced through `aria-live="polite"`.
- **Speed.** With the seed DB, time 50 `/api/search` calls for common terms. Write
  the p95 into `docs/PERFORMANCE.md`. Target: under 150 ms.
- **Telemetry.** Add the section counts to the `csi:search` event detail, and add a
  `csi:ask` event (fired, answered, fallback), so `/admin/ux-insights` shows whether
  people use the new box.
- **Help.** Update `/help` (`tours.py`) text for the home page search and the
  colleague card.
- **CHANGELOG.** Write a user-facing summary of the whole feature.

---

## Risks and how this plan handles them

| Risk | Handling |
|---|---|
| Colleague status widens visibility past the team rule that `work_arrangement_day` was built to enforce | A separate function returns states only; an admin switch can set it back to `"team"`; team pages are untouched; tests check that notes and reasons never leak |
| Search gets slow on every keystroke | Source registry with per-source try/except, per-section caps, 60 s memo on status, rate limit, and a p95 check in Phase 8 |
| The model sees personal data | It never does. Every new answer is a server-rendered slot. The only model argument (`person_status.name`) is checked against the directory before use |
| `/start` breaks during the Phase 7 extraction | Its existing tests must pass untouched; `assistant.js` is a move, not a rewrite |
| Too big for one session | Each phase stands alone, ships alone, and lists its files. Phases 1-2 are UI-only; 3 is a refactor; 4-6 add data; 7 is the only cross-cutting JS change |
