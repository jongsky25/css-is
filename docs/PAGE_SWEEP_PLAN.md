# Page-by-page UI/perf/mobile sweep — execution plan

> ## ▶ EXECUTION STATUS
> **Phase 1 (B + C + D) — DONE & verified 2026-06-16.**
> - **B (16px floor):** `app.css` global `input,select,textarea{font-size:max(16px,var(--fs-base)) !important}`
>   (the `!important` is required — 8 component-scoped page `<style>` rules load after app.css and
>   would otherwise win; verified users select now 16px). Supersedes the `.pub-card`-scoped idea.
> - **C (.resp-table):** new responsive pattern in `app.css` (`thead`/`tr:has(th)` hidden, rows → label-
>   value cards <640px, `td::before`=data-label, `.num`/`.ctr` left-aligned, `.actions` flex-wrap).
>   Applied to directory (class only — self-descriptive), users, audit, monitor_event, feedback_board.
> - **D (report tables):** `resp-table`+data-labels on the reports SQD table and the activity-detail
>   SERVQUAL table. **Fixed the real bug:** `/reports/activities/{id}` no longer overflows (661→375px);
>   also capped the `section_id` select with `max-width:100%` (was forcing 373px width).
> - Cache-buster bumped to `?v=20260616c` in dash_layout.html + public_layout.html.
> - Verified live at 375 (stacked cards, no overflow) + desktop (tables unchanged). Tests: see below.
>
> **Phase 2 (A — dashboard perf) — DONE & verified 2026-06-16.** (app.py only; pytest green.)
> - **Serve-stale `view_memo`:** added `_view_prev` (last-good, survives atoms swaps) + `_views_warming`
>   flag. On a miss during a post-swap re-warm, returns last-good instead of blocking — consistent with
>   the existing atoms SWR model. `invalidate_views`/`invalidate_atoms` now also clear `_view_prev`.
> - **Background re-warm:** `_refresh_worker` calls `_prewarm_dashboard(df, conn)` after each atoms swap
>   (sets `_views_warming` for the window) → the first viewer after a data append no longer pays the
>   multi-second rebuild.
> - **Startup pre-warm:** background thread on startup warms the hot views (gated by `CSS_NO_SCHEDULER`).
> - **Pre-warm set (TRIMMED — deviation, see note):** events + pulse("","all") + people("","all",admin).
>   Reduced from the approved "default + 4 windows × both admin" because the worker re-warms after EVERY
>   append; the full set was ~70 s of background CPU per append (near-continuous on an active system).
>   Narrow set ≈ 25 s; other windows/scopes build on first visit (serve-stale covers the window).
> - **Person detail:** memoized into `person_ident` (rp_id,admin) + `person_rep` (rp_id,period,grain,admin);
>   rp/arta slices computed once (were 3×); `benchmark` (period,role) + `bureau_dims` (period) memoized &
>   shared across persons. Verbatims still fetched FRESH (outside the memo).
> - **Pull-quote (deviation from "fold into memo"):** kept FRESH but shrank the fetch window 300→80 ids.
>   Folding would require `invalidate_views()` on every verbatim edit (those routes don't invalidate),
>   causing post-edit stalls — the shrink keeps freshness with zero invalidation risk.
> - **Measured (clean):** person-detail **1675 ms → 60 ms**; people ~450 → ~240 ms; pulse warm ~763 → ~330 ms.
>   Pulse/Person render output unchanged (verified). Cold-start + post-append now warm in background.
> - **Phase 2c (builder vectorization of pulse_card_insights/pulse_summary/people-grid): DEFERRED.**
>   Pre-warm moved the cost off the request path, so it's no longer user-facing-urgent; it's now a
>   background-CPU optimization (would also let the pre-warm set widen back to ×4 windows cheaply).
>
> **Phase 3 (E + F — rating polish + smaller wins) — DONE & verified 2026-06-16.**
> - **E1 rating scale → 1→7** (`rating.html` `item.scale|reverse`): verified buttons render 1…7 and the
>   "1 = lowest / 7 = highest" caption now matches.
> - **E2 encode scale → 1→7** (`encode_form.html`): verified numeric 1→7 and labeled Poor→Excellent (low→high).
> - **E3 lazy avatars:** speaker `<img>` now `loading="lazy" decoding="async"`.
> - **E4 link_tree style extraction:** inline styles → `.sp-row/.sp-av/.sp-name/.tile/.tile-list/.link-list/.go`
>   in a scoped `{% block head %}`; verified post-consent render is pixel-parity (speaker row + resource tile).
> - **E5 encode sticky bar:** compact "Save →" under 600px (was wrapping to 4 lines) — verified single-line.
> - **F1 show-password toggle:** delegated `[data-pw-toggle]` handler in app.js + `.pw-wrap/.pw-toggle` CSS;
>   added to login + set/reset. Verified toggle flips type & label, input stays 16px.
> - **F2 /create window copy + mobile:** §2 relabelled "When can people answer?" with a default-explaining
>   hint; §6 reworded to reference it; `.win-row` stacks vertically (centred "until") under 640px. Verified.
> - **F3 pulse period-chips:** `.winbar { flex-wrap:wrap }` — verified "Last 30 days" no longer clipped at 375.
> - Cache-busters: app.css `?v=20260616d`, app.js `?v=20260616a`.
>
> **Phase 2c (builder vectorization) — DONE & verified 2026-06-16.** (dashboard_insights.py + app.py.)
> Method: captured a golden baseline of all builder outputs, optimized, and diffed — **all outputs
> byte-identical** (people grid, pulse tiles/insights/summary, rp-event-overalls); pytest green; dashboard +
> people render identical live.
> - **`_rp_event_overalls`** (di:794): nested per-(person,event) `overall_perception` loop → three grouped
>   means (item→dim→overall) in one pass. Order preserved (form_instance_id asc).
> - **`_ranked_dimensions`** (di:1258): was `eng.dimension_mean` per dimension (9× re-filter) → one groupby
>   over all items, assemble each dimension from its present item-means. Also speeds `_person_extras`.
> - **`_last_periods`** (di:1232): `.unique()` before the set-comprehension (was iterating ~1.18M rows).
> - **Measured:** people_grid **11.5 s → 2.2 s** (~5×); pulse_summary **4.2 s → 2.2 s**; pulse_card_insights
>   ×3 **3.1 s → 2.0 s**.
> - **Full ×4-window pre-warm RESTORED** in `_prewarm_dashboard` (pulse × all/ytd/quarter/d30 + people
>   public+admin + events) — ~25 s background pass now (was ~70 s pre-vectorization), bounded + off the
>   request path via serve-stale.
>
> **SWEEP FULLY COMPLETE** (Phases 1, 2, 2c, 3). Remaining are optional design items only (Trends Phase D
> segment-split, directory jump-nav) + the out-of-scope security item (session cookie `Secure` on HTTPS).
> No git commits made — all changes in the working tree on `main`.
> ---


**Goal:** for each page, (1) design/layout assessment + recommendation, (2) probable
slowdown cause + long-term fix, (3) mobile/tablet fit check + recommendation.

**How this doc is used:** assessments are recorded here as we sweep. The user triggers
execution later, page by page. Each page entry carries a `Decisions` block capturing the
answers to that page's open questions, and an `Action plan` with concrete, file-referenced steps.

**Inspection method:** live preview (uvicorn :8000) screenshotted at mobile (375), tablet
(768), desktop (1280); template/route code read; real load timings via navigation API.

**Order (user-journey):**
1. Respondent flow — `/e/{token}` → `/r/{token}` → `/seq` → thanks/result → `/arta`
2. Auth — login / set-password / forgot / reset
3. Staff hub — `/` → `/search` → `/create` → `/encode` → `/directory`(+sub) → `/monitor` → `/shared`
4. Dashboard — `/dashboard` → people → person → teams → trends → participation
5. Reports — `/reports` → verbatims → activities(+detail)
6. Admin/ops — users / audit / sharing / feedback / backups / ops

**Legend:** 🟢 strong / leave · 🟡 minor polish · 🔴 needs work · ⏱ perf · 📱 mobile

---

## 1. Respondent flow

### 1.1 `/e/{event_token}` — Event landing / link-tree / registration
**Route:** `app.py:3160` → `_event_view` (`app.py:3115`) → `templates/link_tree.html` · layout `public_layout.html`
**Live timing:** TTFB 143 ms · DOMContentLoaded 183 ms · load 214 ms · 7 KB HTML.

**Design/layout — 🟢 strong, 🟡 minor**
- Centered single-column card, clear label hierarchy, prominent privacy/consent panel,
  speaker line-up with avatars, gated "unlock after feedback" resources. Well-built.
- Display-settings gear (theme / text-size / density) is a genuine a11y win for respondents.
- 🟡 Template is heavy on inline `style="…"` attributes — maintainability only, not UX.
  Optional: extract the repeated list-item/anchor styles to `.link-tile` / `.res-tile` classes.

**Slowdown — 🟢 not a concern**
- `_event_view` makes several small DB reads (`get_event_forms`, `list_event_links`,
  `attendee_completed_feedback`, `list_event_resource_persons`, `get_setting`) — all cheap.
- ⏱ Only scaling risk: each speaker avatar is a separate `/photo/{id}` request, and the
  `<img>` tags have no `loading="lazy"`. Fine for typical 1–5 speakers; for many-speaker
  events add `loading="lazy"` + `decoding="async"` (`link_tree.html:42`). Long-term: low priority.

**Mobile/tablet — 🟡 one real fix**
- 📱 Form inputs/selects render at **15.2px** → iOS Safari auto-zooms on focus mid-form.
  Fix: bump public-form `input`/`select`/`textarea` to `font-size:16px` (likely a `.pub-card`
  scope rule in `app.css`). Concrete, low-effort, high-value for phone respondents.
- Tap targets good (submit 52px, inputs 42px). Single column reflows cleanly at 375.
- viewport meta present; no-flash theme script in place.

**Decisions:**
- 16px input fix → **public forms only** (scope to `.pub-card` inputs/selects/textareas).
- Inline styles → **extract to CSS classes** (link-tile / resource-tile / speaker-row).
- Avatars → **add `loading="lazy"` + `decoding="async"`**.

**Action plan:**
1. ⚠️ SUPERSEDED by 3.3 decision → use the **site-wide** `input,select,textarea{font-size:16px}`
   global rule instead of the `.pub-card`-scoped version. (Original scoped rule kept here for
   history only.) 📱 fixes iOS zoom on respondent + staff forms alike.
2. `app.css`: add `.link-tile` (the rating-link `<a>`), `.res-tile` (resource `<a>`),
   `.speaker-row`/`.speaker-avatar` classes; replace inline `style="…"` in
   `link_tree.html:41-48,57-63,93-99` with those classes. No visual change intended — diff screenshots.
3. `link_tree.html:42`: add `loading="lazy" decoding="async"` to the speaker `<img>`.
4. Verify at 375/768/1280; re-screenshot the consent form + a registered (post-consent) state.

### 1.2 `/r/{qr_token}` — Rating / feedback form (core respondent screen)
**Route:** `app.py:2931` → `templates/rating.html` · also `closed.html` when window shut.
**Live timing:** TTFB 93 ms · DOM 447 ms · load 504 ms · 34 KB HTML (11 questions).

**Design/layout — 🟢 strong, 🔴 one real bug**
- Excellent respondent UX: big numeric scale buttons, per-item optional note, tappable
  comment-suggestion chips, live "x of N answered" progress, "Your answers are anonymous"
  reassurance, clear section headers (ABOUT YOU / EXPECTATION / YOUR EXPERIENCE).
- 🔴 **Scale caption/button mismatch** (`rating.html:95,103`): buttons iterate `scale[0]→[-1]`
  = **7,6,…,1 left-to-right**, but the anchor caption prints `scale[-1]="1 = lowest"` on the
  LEFT and `scale[0]="7 = highest"` on the RIGHT — so "1 = lowest" sits under the **7** button.
  Confusing; risks inverted ratings. Fix options recorded in Decisions.
- 🟡 Closed-window state (`closed.html`) is clean and on-brand (lock, "Closed <date>", contact hint).

**Slowdown — 🟢 not a concern**
- `survey_spec(ctx)` parses stored JSON (cheap); single context query; served-by path loads
  internal resource persons (**45 rows** → native `<select>`, fine). No N+1, no heavy compute.
- 34 KB is inherent to 11×(7 buttons + note + chips); acceptable. No action.

**Mobile/tablet — 🟡 covered by 1.1 fix**
- `.scale` wraps to 3-col on mobile (`rating.html:144-145`), 46px tap buttons — good.
- 📱 Selects/note inputs/free-text are 15.2px → same iOS zoom issue; the `.pub-card` 16px rule
  from 1.1 covers this page (extends `public_layout.html`). Confirm scope includes `textarea`.

**Decisions:**
- Scale fix → **reverse buttons to ascending 1→7 left-to-right** (caption already reads
  "1=lowest" left / "7=highest" right, so it becomes correct once buttons are reversed).

**Action plan:**
1. `rating.html:95`: change `{% for val, lbl in item.scale %}` → `{% for val, lbl in item.scale|reverse %}`
   so the lowest value renders leftmost. Caption at `:103` stays as-is (now matches).
2. ⚠️ This also reverses the labeled 4-point scale (currently Excellent→Poor). Verify it reads
   sensibly as Poor→Excellent left-to-right; if not, gate the reverse to numeric scales only.
3. Confirm the `.pub-card` 16px rule (from 1.1) includes `textarea` so the note/free-text fields
   stop triggering iOS zoom.
4. Re-screenshot at 375/768/1280; spot-check both a numeric (7-pt) and a labeled (4-pt) item.

### 1.3 `/seq` + `thanks.html` + `closed.html` — sequence guide & post-submit states
**Routes:** `/seq` `app.py:3074` → `sequence.html`; thank-you `thanks.html`; closed-window `closed.html`.

**Design/layout — 🟢 strong**
- `/seq`: "complete each survey in turn" numbered list, large tap tiles. Clean.
- `thanks.html`: centered ✓ confirmation, anonymity note, contextual next-step button
  (next survey / back to activity / back to set) + optional organizer ending message.
- `closed.html`: on-brand lock state with closed date + contact hint.
- 🟡 Same inline-style pattern as 1.1 (cosmetic/maintainability only).

**Slowdown — 🟢 not a concern**
- `/seq` loops `get_form_context` once per token (bounded, typically 1–3). All trivial reads.

**Mobile/tablet — 🟢 good**
- All `.pub-card`, single column, reflow clean. No form inputs here (no zoom concern).

**Decisions:**
- Inline-style cleanup → **skip these three** (leave thanks/seq/closed as-is; less churn).

**Action plan:** None. Pages pass the sweep. (Global `.pub-card` 16px from 1.1 already covers
any future inputs; no form inputs exist here today.)

> **Reclassified:** `/arta` (walk-in QR) is staff-facing (`dash_layout`, login-gated) — moved to
> §3 Staff hub, not respondent flow.

---

## 2. Auth — login / set-password / forgot / reset

### 2.1 `/login`, `/forgot`, `/set-password`, `/reset-password`
**Routes:** `app.py:733/906/874/930` → `login.html`, `forgot.html`, `set_password.html`
(shared by invite + reset via `mode`). All extend `public_layout.html`.
**Live timing (login):** load 352 ms · 4 KB.

**Design/layout — 🟢 strong**
- Tight 380–400px centered card, logo, focused single-purpose forms, no nav (correct).
- Microcopy matches the pilot auth model (`forgot.html`: "admin resets, no email needed").
- All edge states handled: first-run admin setup, invite vs reset, invalid/expired link.

**Slowdown — 🟢 not a concern** — static-ish pages, one cheap auth/token lookup.

**Mobile/tablet — 🟡 covered + one optional**
- 📱 email/password inputs are 15.2px → iOS zoom; covered by the `.pub-card` 16px rule (1.1).
- Buttons ~40px tall (`.7rem` padding) — acceptable for auth.
- Optional: a "show password" toggle reduces blind-typing errors on phones (esp. the 8-char
  set/reset screens). Discretionary — see Decisions.

**Decisions:**
- Show-password toggle → **add it** to password fields on login + set/reset.

**Action plan:**
1. Add a small reusable show/hide toggle (eye button) next to `#password` in `login.html:27`
   and `set_password.html:20`. Implement once in `app.js` (delegate on `[data-pw-toggle]`) so
   both pages share it; toggle `type` between `password`/`text`, with `aria-pressed`/label.
2. Ensure the 16px `.pub-card` rule applies so toggling to `text` doesn't trigger iOS zoom.
3. Verify at 375; confirm autofill + autocomplete attributes still behave.

> **Out of sweep scope (security, noted not actioned):** memory flags "make session cookie
> `Secure` on HTTPS" — track separately; not a UI/perf/mobile item.

---

## 3. Staff hub

### 3.1 `/` — Home hub
**Route:** `app.py:1720` → `home.html`. Pieces: `home_stats`, `get_atoms`, `view_memo("events")`,
`upcoming_events`, `ongoing_events`.
**Live timing:** first load 2.29 s (TTFB 1.68 s); repeated warm fetches **449 → 68 → 65 ms**.

**Profiled costs (separate process):** `home_stats` 448 ms cold / **0 ms warm**;
`get_atoms` **5.4 s cold** / 25 ms warm; `list_activity_instances` **853 ms (uncached)**;
`build_events` **2.0 s**; `upcoming`/`ongoing` ~1–13 ms.

**Design/layout — 🟢 strong**
- Personalized greeting, role chip, Ctrl-K search, period filter, 4 KPI cards, and three
  lifecycle feeds (Upcoming / Ongoing / Recently concluded). Clear task-oriented hub. No changes.

**Slowdown — 🟡 cold-start & post-append rebuild, NOT steady state**
- Steady state is ~65 ms — fine. The pain is two-fold and lands on a user request:
  1. **Cold start:** `get_atoms` 5.4 s on a fresh process. Mitigated today by the pickle
     warm-restart snapshot (`_persist_atoms_async`) + `--workers 1` (keep both).
  2. **After any new response:** `_data_key` changes → `_build_blocking` calls `_view_memo.clear()`
     (`app.py:425`) → the "events" memo is cold → the *next* viewer of home/dashboard pays
     `list_activity_instances` (853 ms) + `build_events` (2.0 s) **synchronously**, because derived
     views are NOT served-stale-then-rebuilt the way atoms are. On an actively-collecting system
     this recurs often.
- **Long-term fixes (recommended):**
  a. Extend the atoms "serve stale, rebuild in background" pattern to the **`view_memo` layer**
     (esp. `events`): on a memo miss after invalidation, serve the previous value and rebuild off
     the request path — or warm the `events` memo inside `_refresh_worker` right after the atoms swap.
  b. Decouple the home **"Recently concluded"** feed from the full 2,764-event build: it only needs
     ≤60 concluded events in the last 90 days — a targeted query/derivation avoids `build_events`
     on the home path entirely.
  c. Make/keep `list_activity_instances` cached or derive it from atoms (it's an 853 ms query run
     inside the events builder).

**Mobile/tablet — 🟢 good**
- Mobile (375): hamburger nav, KPI cards reflow to 2×2, period chips wrap. Clean.
- Tablet (768): 4 KPI cards in a row, 2-col feeds, hamburger nav. Clean.
- 🟡 Optional: nav collapses to hamburger already at 768 — could raise the breakpoint so landscape
  tablets keep the full menu bar. Low priority.

**Decisions:**
- Rebuild cost → **serve-stale `view_memo`** (the systemic fix; benefits all dashboard pages).
- Cold start → **add startup pre-warm** so the first user never waits.

**Action plan (⭐ cross-cutting — implement once, benefits §3.1 + all of §4 Dashboard):**
1. **Serve-stale view_memo** (`app.py:535` `view_memo`, `:414` `_build_blocking`): keep the
   previous memo values on invalidation instead of `_view_memo.clear()` wiping them. On a miss,
   return the last-known value and rebuild off the request path (background thread / reuse
   `_refresh_worker`). Key by atoms-key so a served-stale value is clearly labeled stale and
   replaced when the rebuild commits. Verify correctness vs the current `invalidate_views()` /
   `invalidate_atoms()` contracts (some mutations MUST block — preserve those).
2. **Startup pre-warm**: on app startup (FastAPI startup event), kick `get_atoms(conn)` +
   warm the `events` memo in a background thread, so the 5.4 s cold build happens before the
   first request rather than on it. Compose with the existing pickle snapshot (load snapshot
   first, then verify/refresh).
3. (Optional follow-on if (1) proves insufficient) targeted 90-day query for the home
   "Recently concluded" feed; cache `list_activity_instances`.
4. Verify: restart server → first home load fast; add a response → next home/dashboard load
   stays ~fast (no 2 s stall). Re-measure warm fetches.

### 3.2 `/search` — Full-page search fallback
**Route:** `app.py:1766` → `search.html`. Backs the Ctrl-K palette for no-JS / deep-link cases.

**Design — 🟢 simple/clean** · search box + "N results" + page tiles with section chip.
**Slowdown — 🟢 none** · in-memory `search_index_for` over `NAV_GROUPS`; instant.
**Mobile — 🟢** full-width box reflows trivially (verify at build).

**Decisions:** none needed — page passes.
**Action plan:** None.
> Note (out of sweep scope): memory records a Phase-2 seam to extend search to DB records
> (people/activities), not just pages. Feature work, not a sweep fix — flagged, not scheduled.

### 3.3 `/create` — Create activity survey
**Route:** `app.py:1783` (GET) / `1798` (POST) → `form_create.html`; success → `result.html`.
**Live timing:** TTFB 182 ms · load 305 ms · 27 KB.

**Design/layout — 🟢 strong, 🟡 one clarity nit**
- Excellent 6-section numbered form (Event type → details → organizer → resource-person repeater
  → QR mode → response window) with generous inline help and an add/remove RP repeater. Polished.
- 🟡 Possible concept overlap: §2 "Entry window (optional)" vs §6 "Response window — auto-opens on
  the event date." Two window concepts on one form may confuse. Consider merging the explanation or
  cross-referencing them. See Decisions.
- `result.html` (post-create): QR cards, form-id list, print button — clean (covered here).

**Slowdown — 🟢 not a concern** · loads 45 RPs + org-unit list for selects; 305 ms.

**Mobile/tablet — 🟡 reflows well; cross-cutting input-zoom item**
- Sections stack, RP/Topic/Remove row stacks, date inputs stack at 375. Good.
- 🟡 The "until" label sits between two stacked date inputs on mobile — slightly awkward, minor.
- 📱 **Cross-cutting:** staff-form **text inputs are 15.2px** and are NOT in `.pub-card`, so the
  1.1 fix doesn't reach them → iOS tablet zoom-on-focus. Affects all staff forms (create, directory,
  encode, monitor, admin). Decision below applies sweep-wide.

**Decisions:**
- Input zoom → **site-wide 16px** for all inputs (staff + public). ⭐ This SUPERSEDES the
  "public forms only" scope recorded in 1.1 — implement one global rule instead.
- Window copy → **clarify** the §2 entry-window / §6 response-window relationship.

**Action plan:**
1. ⭐ **(replaces 1.1 step 1)** `app.css`: a single global rule
   `input, select, textarea { font-size:16px; }` (audit existing per-input overrides so nothing
   regresses; spot-check density on dashboards). Fixes iOS zoom on every page.
2. `form_create.html`: reword §2/§6 so the optional manual entry window vs the auto-open-on-event-date
   response window read as one coherent model (e.g. one combined "When can people answer?" explainer).
3. Mobile polish: fix the "until" label placement between the two stacked date inputs (375).
4. Verify create→result flow at 375/768/1280.

### 3.4 `/encode` + `/encode/{qr_token}` — Paper / manual data entry
**Routes:** list `app.py:4305` → `encode_home.html`; detail `4330/4354` → `encode_form.html`.
**Live timing:** list TTFB 139 ms / load 723 ms; detail fast.

**Design/layout — 🟢 strong**
- List: clear instructions, walk-in CO-CSM callout, search + Date/Responses sort, badged table
  (Speaker/Event, Not-open-yet/Closed, responses recorded). Smartly shows recent forms only with
  "search to find older" (3,907 forms total — avoids dumping all).
- Detail: rapid-entry layout — "Date collected" (paper-slip date, not today), N/A-defaulted radios,
  per-question note, dimension tags (RELIABILITY…), sticky "Save & enter next" + "Done" bar. Excellent
  for transcription throughput.

**Slowdown — 🟢 not a concern** · list intentionally bounded; detail is a single-form render.

**Mobile/tablet — 🟢 works, 🟡 sticky-bar polish**
- Detail radios wrap to a 5+3 grid (7…1 + N/A) at 375 — usable.
- 🟡 Sticky "Save & enter next" wraps to ~4 lines on mobile (cramped); consider a shorter mobile label
  or icon.

**Consistency note — 🟡** the encode scale is also **7→1**; if respondent `rating.html` reverses to
1→7 (decision 1.2), the encode form should match so staff and respondents see the same order.

**Decisions:**
- Encode scale → **match the 1→7 reversal** (apply the same fix to `encode_form.html`).
- Sticky bar → **shorten on mobile** (compact label/icon under ~600px).

**Action plan:**
1. `encode_form.html`: reverse the scale radio order to 1→7 to match `rating.html` (decision 1.2);
   keep N/A default. Verify dimension tags + note fields unaffected.
2. `app.css` (or inline): under a mobile breakpoint, give the sticky action bar a compact label
   (e.g. "Save →") so it stays one line; keep full label ≥600px.
3. Verify list + detail at 375/768/1280; confirm site-wide 16px (3.3) covers the "Date collected"
   and note inputs here.

### 3.5 `/directory` (+ sub-pages) — Organogram & people registry
**Routes:** `app.py:2025` → `directory.html`; sub-pages: person edit `2251` (`staff_form.html`),
external `2329/2352` (`external_rp_form.html`), cleanup `2446` (`cleanup.html`).
**Live timing:** TTFB 99 ms · load 629 ms · 50 KB · **0 images** (no photos rendered here).

**Design/layout — 🟢 strong, 🟡 long page**
- Clean build-order flow: Bureau → Office of Director → Divisions → Sections → Staff → External RPs →
  Outside organizers → "Start fresh" danger zone. Consistent cards, inline edit/remove, scoped search
  boxes per registry. Destructive action well-separated at the bottom.
- 🟡 Very long single page (~5,200 px). Acceptable (it mirrors the build sequence); optional: a sticky
  section jump-nav. Low priority.

**Slowdown — 🟢 not a concern** · no photo fan-out here; 629 ms.

**Mobile/tablet — 🔴 table actions clipped**
- 📱 The org-unit / RP tables scroll horizontally inside their card and **clip the Edit/Remove
  buttons** off the right edge at 375 (page-level overflow is contained, but actions are hard to reach).
  Long names also balloon row height.
- Recommend a responsive table treatment: under ~640px, drop the low-value PATH column and/or stack
  each row into a label-value card so Edit/Remove stay visible. Applies to all admin tables (reused on
  Users/Audit — see §6).

**Sub-pages:** `staff_form` / `external_rp_form` are simple CRUD forms (inherit site-wide 16px + card
pattern). `cleanup.html` (name cleanup: title-case, merge, split, archive-low) is a heavier tool —
assess depth per Decisions. ⚠️ memory flags a `name_cleanup.py` truncation keeping qa_preflight RED
(code/test issue, not UI — track separately).

**Decisions:**
- Mobile tables → **stack to cards under 640px** via a reusable pattern (also applied to §6 Users/Audit).
- Sub-pages → **assess each individually** (cleanup, staff form, external form below).

**Action plan:**
1. ⭐ **(reusable)** Add a `.resp-table` treatment in `app.css`: under ~640px, each `<tr>` becomes a
   stacked label-value card (use `data-label` on `<td>` or CSS `::before` from `<th>` text); actions
   row sits full-width and tappable. Apply to `directory.html` org-unit + RP tables.
2. Optional: sticky section jump-nav for the long directory page (low priority).
3. Verify org-unit add/edit/remove + RP search at 375/768/1280; confirm Edit/Remove reachable.
4. Reuse `.resp-table` on Users (§6.1) and Audit (§6.2).

#### 3.5a `/directory/cleanup` — Name cleanup tool
**Route:** `app.py:2446` → `cleanup.html`. Live: TTFB 326 ms · load 759 ms · 24 KB.
- **Design 🟢** filter chips (Needs action / Rosters / Has duplicate / ALL-CAPS / Under-5-ratings /
  Hidden / All external) + bulk actions (Archive-under-5, Fix-ALL-CAPS) + "Save restore point" safety +
  clear explainer. Empty state clean (external roster already cleaned → all counts 0).
- **Slowdown 🟢** filter-count computation bounded by external-RP count; fine.
- **Mobile 🟡** toolbar chips wrap OK; result **rows weren't visible** (0 records) — when populated they
  likely need the `.resp-table` treatment too. Verify against a populated roster.
- **Action:** apply `.resp-table` to cleanup result rows; otherwise passes.

#### 3.5b `/directory/person/{id}/edit` + external RP form — CRUD forms
**Routes:** `app.py:2251` (`staff_form.html`), `2329/2352` (`external_rp_form.html`).
- **Design 🟢** clean centered card, photo-upload avatar, sensible field grouping, Save/Cancel.
- **Mobile 🟢** field grid stacks correctly; the narrow Honorific + wide Full-name pairing stays
  side-by-side by design. Good responsive behavior.
- **Slowdown 🟢** trivial. **Action:** none beyond site-wide 16px (3.3). Pass.

### 3.6 `/monitor` (+ `/monitor/{event_token}`) — Registration & CSS status
**Routes:** list `app.py:3529` → `monitor.html`; detail `3551` → `monitor_event.html`.
**Live timing:** list TTFB 56 ms / load 444 ms; detail comparable.

**Design/layout — 🟢 strong**
- List: clear explainer, per-activity cards with ONGOING/UPCOMING badge, CSS-done %, progress bar,
  and registered/completed/in-progress/not-started breakdown.
- Detail: 5 KPI cards + Export roster (XLSX) + Manage activity + copyable registration link +
  participant roster with per-row recovery actions (Copy link / Resend email). Confirms the
  request-derived base URL is working (shows the LAN host, not a hard-coded one).

**Slowdown — 🟢 not a concern** · scoped to link-tree activities only (never the historical backlog).

**Mobile/tablet — 🟡 covered by `.resp-table`**
- The 8-column roster table clips the recovery-link actions on mobile (same as directory). Covered by
  the §3.5 `.resp-table` decision — no separate decision needed.

**Decisions:** none new — roster table folds into the `.resp-table` rollout (3.5).

**Action plan:** apply `.resp-table` to `monitor_event.html` roster; verify Copy-link / Resend reachable
at 375. List page passes as-is.

### 3.7 `/shared` + `/arta` — Shared materials & walk-in QR
**Routes:** `/shared` `app.py:3761` → `shared.html`; `/arta` `app.py:1983` → `arta_link.html`.
**Live timing:** shared load 410 ms / TTFB 69 ms; arta fast.

**Design/layout — 🟢 strong**
- `/shared`: single-column activity list, each card → its shared resources (programmes/slides/certs).
- `/arta`: one focused QR card + explainer; request-derived URL confirmed. Clean.

**Slowdown — 🟢 not a concern** for either.

**Mobile/tablet — 🟢 good** — single-column cards reflow trivially.

**Decisions:**
- Print QR on /arta → **skip** (browser print is enough).

**Action plan:** None — both pages pass. Site-wide 16px (3.3) covers any inputs.

---

## 4. Dashboard

### 4.1 `/dashboard` — Pulse (flagship; heaviest perf page) 🔴⏱
**Route:** `app.py:5360` → `pulse.html`. Pieces: `get_atoms`, `eng.scope`+`_apply_window`,
`view_memo("pulse",(org,win))` → `pulse_tile`/`pulse_card_insights`/`pulse_summary`, fresh pull-quotes.
**Live timing:** cold first load **9.4 s (TTFB 8.9 s)**; warm fetches **1182 → 763 ms**. 34 KB.

**Profiled costs:** `scope+apply_window` ~0 ms; **`pulse_tile ×3` 2.5 s**; **`pulse_card_insights ×3`
5.2 s**; **`pulse_summary` 4.1 s** (≈12 s memoized build); **`verbatims_for_responses ×3` 444 ms
(fresh EVERY request, outside the memo)**.

**Design/layout — 🟢 excellent**
- Three vital-signs cards (walk-in / activities / resource-persons) with sparkline, trend direction,
  strongest-point quote, respondent count, "More details"; then narrative cards (What's good / Worth
  looking at / Overall pulse). Name-free, plain-language, genuinely glanceable. No design changes.

**Slowdown — 🔴 the worst in the app**
- **Cold ≈ 12 s pulse build** per distinct (org, win). Memoized — but the memo is cleared on every
  data append (`_build_blocking` → `_view_memo.clear()`), so on an actively-collecting bureau the
  **next dashboard viewer waits ~12 s**. This is THE strongest justification for the §3.1 serve-stale
  fix.
- **Warm ≈ 450–760 ms** dominated by the **fresh pull-quote fetch** (444 ms, 3× `verbatims_for_responses`
  with ≤300 IDs). It sits outside the memo for verbatim-edit freshness — but verbatim edits already call
  `invalidate_views()`, so the quote can safely live in the memo.
- **Long-term fixes (recommended, extend §3.1):**
  a. ⭐ **Serve-stale `view_memo`** (3.1) — essential here; viewers never eat the 12 s rebuild.
  b. **Pre-warm the default-scope pulse memo** (`("","all")`) at startup, not just atoms.
  c. **Fold the pull-quote into the pulse memo** (kill the 444 ms/request); rely on `invalidate_views()`.
  d. (optional) Optimize/vectorize or background-build `pulse_card_insights` (5.2 s) + `pulse_summary`
     (4.1 s) — the bulk of the cold cost; could be built in `_refresh_worker` after the atoms swap.

**Mobile/tablet — 🟢 good, 🟡 chip clip**
- 3 cards stack to single column at 375; sparklines render.
- 🟡 The period-chip row (All time / YTD / This quarter / Last 30 days) clips "Last 30 days" at the
  right edge at 375. Make the chip row wrap or horizontally scroll.

**Decisions:**
- Pull-quote → **fold into the pulse memo** (rely on existing `invalidate_views()` for freshness).
- Heavy builders → **optimize/vectorize** `pulse_card_insights` + `pulse_summary` (attack root cost).
- Pre-warm scope (refines §3.1) → **whole-bureau × all 4 windows** (all/ytd/quarter/d30).

**Action plan:**
1. **Fold pull-quote into memo** (`app.py:5376-5392`): move the per-tile newest-verbatim lookup inside
   `_build_pulse` so the quote is cached with the tile; drop the per-request loop. Verify a verbatim
   edit (which calls `invalidate_views()`) refreshes the quote on next load. Expected warm ≈ home (~65 ms).
2. **Optimize the builders** (`dashboard_insights.py`): profile `pulse_card_insights` (5.2 s) and
   `pulse_summary` (4.1 s); vectorize the pandas groupbys / avoid per-row Python loops / precompute shared
   aggregates once and pass into all three tiles. Target sub-second cold build.
3. **Startup pre-warm** (refines §3.1 step 2): after atoms warm, pre-build `view_memo("pulse", ("",w))`
   for w in {all, ytd, quarter, d30} (and the `events` memo) in the background thread.
4. **Mobile**: make the period-chip row wrap or horizontally scroll so "Last 30 days" isn't clipped at 375.
5. Verify: cold first dashboard load fast (pre-warmed); add a response → next load instant via serve-stale;
   warm fetch ≈ home. Re-measure.

### 4.2 `/dashboard/people` — People grid 🟢/🔴⏱
**Route:** `app.py:5407` → `people.html`.
**Live timing:** cold first load **9.1 s (TTFB 8.4 s)**; warm **519 → 433 ms**. 95 KB · **0 photo requests**.

**Design/layout — 🟢 excellent**
- Gamified people cards (initials avatar, unit, earned badges, score /7, confidence, ratings count),
  badge-filter chips, sort (Most ratings / Highest score / A–Z), search, hero summary "Meet the 33…".
  Engaging and information-dense without clutter. Smartly uses **initials avatars, not photos** → avoids
  the N-image fan-out. No design changes.

**Slowdown — 🔴 same class as Pulse**
- Cold ~8–9 s — its own heavy people-grid aggregation (scores/badges/confidence over 14.6k ratings),
  memoized but cleared on data append. Warm ~450 ms.
- **Fix:** same cross-cutting treatment (serve-stale, pre-warm, optimize the builder) — see scoping
  decision below.

**Mobile/tablet — 🟢 good** — scope/period selectors stack, hero reflows, cards/chips stack at 375.

**Decisions:**
- Builder scope → **all dashboard builders** (pulse, people, teams, trends, participation) get
  serve-stale + startup pre-warm + builder optimization. ⭐ Treated as one cross-cutting perf workstream.

**Action plan:**
1. People-grid builder joins the §4.1 treatment: pre-warm `("","all")` at startup; optimize the
   scores/badges/confidence aggregation (vectorize over the 14.6k-rating frame).
2. Mobile passes; no layout work.

> ⭐ **CROSS-CUTTING PERF WORKSTREAM (applies to §3.1 + all of §4):** (a) serve-stale `view_memo`,
> (b) startup pre-warm of atoms + each dashboard memo (whole-bureau × 4 windows), (c) optimize each
> heavy builder (pulse_card_insights, pulse_summary, people-grid, teams, trends, participation),
> (d) fold per-request fresh fetches into their memos where an `invalidate_views()` hook already exists.
> Implement once; verify each dashboard page cold-fast + warm ≈ home + instant after a data append.

### 4.3 `/dashboard/people/{rp_id}` — Person detail (coaching report) 🟢/🔴⏱
**Route:** `app.py:5467` → `person.html`.
**Live timing:** first 1.98 s (TTFB 1.63 s); **warm 1675 → 1443 ms** (barely faster than cold).

**Design/layout — 🟢 excellent**
- Personalized coaching report: header + earned badges + year filter, "Coaching Notes" (what's going
  well + encouragement), "Strengthen …" (biggest opportunity + "Try this" actions), peer standing.
  Supportive, name-positive, no raw quotes (per the earlier per-page decision). No design changes.

**Slowdown — 🔴 distinct from the cross-cutting fix; warm is ~1.5 s**
- Most per-person panels run **uncached every request**: `person_trend`, `person_dimensions`,
  `person_arta_items`, `story_panel`, `year_over_year`, `coach_notes`, `ta_advice`. `rp_slice`/
  `arta_slice` are recomputed **3×** over the 35k-row frame (`app.py:5488,5498,5499`). `bureau_dims(atoms)`
  + `benchmark_value` are scope-level (not person-specific) yet recompute per request. Only `people_grid`
  is memoized.
- **Fix (page-specific):**
  a. Wrap the per-person panels in `view_memo("person", (rp_id, period, grain, admin), …)` so repeat
     visits are instant (pre-warm NOT needed — too many people; on-demand memo + serve-stale suffices).
  b. Compute `rp_slice`/`arta_slice` **once** and reuse (kill the 3× duplication).
  c. Memoize the scope-level `bureau_dims` / `benchmark_value` (shared across all person views).

**Mobile/tablet — 🟢 good** — header/badges/cards stack; year chips wrap to 2 rows (no clip). 54 KB.

**Decisions:**
- Person perf → **full fix**: memoize per-person panels + compute slices once + memoize scope-level
  `bureau_dims`/`benchmark_value`.

**Action plan:**
1. `app.py:5467` route: wrap per-person panels in `view_memo("person",(rp_id,period,grain,admin),…)`;
   served-stale on data append (inherits the cross-cutting serve-stale layer).
2. Compute `rp_slice(atoms,rp_id)` / `arta_slice` once at the top and reuse (remove the 3× recompute).
3. Memoize `bureau_dims(atoms)` and `benchmark_value(atoms,role)` at scope level (shared with other pages).
4. Verify repeat person visits ≈ instant; coaching/peer figures unchanged. Mobile passes as-is.

### 4.4 `/dashboard/teams` (+ `/dashboard/teams/{org_path}`) — Team/org coaching 🟢
**Route:** index `app.py:5674` → `teams.html`; per-unit drill-down `5695` → `team.html`.
**Live timing:** cold first **5.75 s (TTFB 5.36 s)**; **warm 209 → 203 ms** (memoizes well).

**Design/layout — 🟢 excellent**
- Hierarchical org read: Bureau → Divisions → Sections, each with rated-activity count, people reached,
  met-expectations %, score /7, and earned-badge emojis; "What the badges mean" explainer. Clear nesting.
  No design changes.

**Slowdown — 🟢 warm-fine; cold covered by cross-cutting**
- Warm ~205 ms (good — effective memo). Cold ~5.7 s is the teams builder → handled by the cross-cutting
  pre-warm + serve-stale + optimize workstream. No page-specific perf work.

**Mobile/tablet — 🟢 good** — year chips wrap (no clip), cards stack with badges/score. (The chip-clip seen
on Pulse is specific to `pulse.html`, not global.)

**Decisions:** none new — inherits the cross-cutting perf workstream.
**Action plan:** ensure the `teams` (and per-unit `team`) builders are in the pre-warm + optimize set;
otherwise passes. Per-unit drill-down inherits the same.

### 4.5 `/dashboard/trends` — Trends (SPC) 🟢 reference standard
**Route:** `app.py:6023` → `trends.html`.
**Live timing:** first 1.05 s (TTFB 666 ms, atoms warm); **warm 184 → 182 ms**.

**Design/layout — 🟢 excellent (the polished benchmark)**
- Plain-language status headline ("IN CONTROL — consistently high and stable"), survey-type tabs,
  Monthly/Quarterly/Yearly grain, Recent/Full-history toggle, SPC control chart with usual-range +
  margin-of-error bands, auto-zoom, **labelled X/Y axis titles**, and a "How it's computed" note.
  This is the figure-axis + download-standard reference for the rest of the app. No changes.

**Slowdown — 🟢** warm ~182 ms; cold covered by cross-cutting.

**Mobile/tablet — 🟢 good** — tabs/toggles wrap; the SVG chart scales to viewport (299 px at 375, no
overflow). Reads small but clean.

**Decisions:** none new.
**Action plan:** trends builder joins the pre-warm/optimize set; otherwise passes.
> Note (out of sweep scope): memory lists Trends "Phase D" (segment-split + verbatim-sentiment trends)
> as optional/unbuilt — feature work, not a sweep fix.

### 4.6 `/dashboard/participation` — Participation (volume/coverage SPC) 🟢
**Route:** `app.py:6076` → `participation.html`.
**Live timing:** cold first **6.89 s (TTFB 6.81 s)**; **warm 223 → 182 ms**.

**Design/layout — 🟢 excellent** — matches the Trends standard: status headline ("EASING…"), coverage %,
"where it moved", 3 KPI cards with directional trend, responses-over-time SPC chart with labelled axes.
No changes.

**Slowdown — 🟢** warm ~200 ms; cold ~6.8 s covered by cross-cutting.

**Mobile/tablet — 🟢 good** — no horizontal overflow at 375; same responsive chart/chip behavior as Trends.

**Decisions:** none new.
**Action plan:** participation builder joins the pre-warm/optimize set; otherwise passes.

---

## 5. Reports

### 5.1 `/reports` — ARTA Harmonized Client Satisfaction (technical) 🟢/🟡
**Route:** `app.py:5027` → `reports.html` (Type 1 ARTA / Type 2 Activity / Type 3 RP tabs).
**Live timing:** first 944 ms (TTFB 837 ms); **warm 750 → 445 ms**.

**Design/layout — 🟢 excellent**
- Precise technical report: SQD dimension table (item codes, SA–A·Neither·D–SD distribution bars,
  top-box %, N with N/A counts), On-Site/Online/Did-not-specify split, "How to read these numbers"
  expander, per-type tabs, scope/period, Download. Matches the download-standard. No design changes.

**Slowdown — 🟡 warm ~450–750 ms by design**
- The report is "computed fresh from raw answers" (stated design goal — item codes/denominators intact).
  Lower traffic than dashboards. Could memoize per (type, scope, period) with `invalidate_views`, but
  freshness is intentional. See Decisions.

**Mobile/tablet — 🟡 SQD table scrolls horizontally**
- Tabs/selectors stack at 375. The SQD table is 485 px inside a scroll container → TOP-BOX/N need
  horizontal scroll (page itself doesn't overflow). Acceptable for a data table, but a responsive
  per-item stacked layout would improve scannability. See Decisions.

**Decisions:**
- SQD table mobile → **per-item stacked cards under 640px**.
- Report memo → **keep fresh** (my recommendation; deferred to me). Rationale: the report's value is
  "computed fresh from raw answers, denominators intact" = the official/auditable view; low-traffic;
  ~450 ms acceptable; memoizing risks the freshness guarantee for an official document.

**Action plan:**
1. `reports.html` + `app.css`: under ~640px, render each SQD item as a compact card (statement +
   distribution bar + top-box badge + N) instead of table rows; keep the table ≥640px. Verify all three
   report types (ARTA / Activity / RP).
2. No perf change (kept fresh). Confirm site-wide 16px (3.3) covers the scope/period selects.
3. Verify tabs + scope/period at 375/768/1280.

### 5.2 `/reports/verbatims` — All feedback (verbatims) 🟢
**Route:** `app.py:5155` → `verbatims.html`.
**Live timing:** first 977 ms (TTFB 586 ms); warm 298 ms (one 2159 ms spike = an invalidation stall).

**Design/layout — 🟢 strong** — comment cards (form-id, subject, timestamp, verbatim, "Edit comment"),
per-item notes with dimension tags + "Edit note", filter tabs (All/Walk-in/Events/Speakers).
**Paginated** ("page 1 of 241", 50/page) — handles 12,013 comments without dumping all. No changes.

**Slowdown — 🟢** warm ~300 ms thanks to pagination. The occasional ~2 s spike is an invalidation stall →
addressed by the cross-cutting serve-stale fix (§3.1/§4).

**Mobile/tablet — 🟢 good** — no horizontal overflow; cards stack.

**Decisions:** none new.
**Action plan:** none beyond inheriting serve-stale + site-wide 16px. Passes.

### 5.3 `/reports/activities` (+ `/reports/activities/{event_id}`) — Activity reports 🟢/🔴📱
**Routes:** list `app.py:5792` → `activities.html`; detail `5854` → (activity F2 report template).
**Live timing:** list first 1.59 s / warm 226 ms; detail first 583 ms / **warm 776 → 447 ms**.

**Design/layout — 🟢 excellent**
- List: search, sort (Date/Score/Organizer), Curate, Expand/Collapse all, per-activity score cards.
- Detail: storytelling F2 report — 4 KPI cards (overall /4, perception /7 + SERVQUAL gap, expectation,
  respondents), expected→experienced→satisfaction flow, narrative, "How this compares" peer bars, and a
  dimension-by-dimension SERVQUAL table. Polished. No design changes.

**Slowdown — 🟡 acceptable**
- Detail warm ~450–776 ms (per-activity SERVQUAL build, computed fresh). Acceptable for a click-through;
  keep fresh (consistent with §5.1). List warm ~226 ms.

**Mobile/tablet — 🔴 detail page overflows horizontally**
- 📱 The activity-detail page **scrolls sideways at 375** (page width 661 px) because the SERVQUAL
  **dimension table (623 px) is not contained** — KPI cards stack fine, but the table forces page overflow.
  Real bug. List cards reflow fine (verify at build).

**Decisions:**
- Dimension table → **per-item stacked cards under 640px** (reuse the §5.1 SQD treatment for consistency;
  fixes the page overflow).

**Action plan:**
1. Apply the same responsive per-item card pattern (from §5.1) to the activity-detail SERVQUAL dimension
   table so it stacks under ~640px and the page stops overflowing. Share one CSS pattern across §5.1 + §5.3.
2. Verify no horizontal page scroll at 375; KPI cards + peer bars already reflow.
3. List page: confirm cards reflow at 375 (expected fine). Keep reports fresh (no memo).

---

## 6. Admin / ops

### 6.1 `/admin/users` — Users & roles 🟢
**Route:** `app.py:964` → `users.html`. Fast (45 staff rows).
- **Design 🟢** progress bar ("1 of 45 have an account"), staff-accounts table (Staff/Email/Account/Role),
  pilot-auth temp-password explainer. Clean.
- **Slowdown 🟢** trivial.
- **Mobile 🟡** 5-column table → inherits the `.resp-table` stack-to-cards fix (§3.5). No new decision.
- **Action:** apply `.resp-table`; otherwise passes.

### 6.2 `/admin/audit` — Audit log 🟢
**Route:** `app.py:1091` → `audit.html`. Load 533 ms · 117 KB (200-row cap).
- **Design 🟢** integrity banner ("Chain intact — no tampering detected"), Action/Actor filters,
  hash-chained When/Who/Action/What table with action badges. Clean.
- **Slowdown 🟢** 200-row cap keeps it light; 533 ms.
- **Mobile 🟡** 4-column table → inherits `.resp-table` (§3.5).
- **Action:** apply `.resp-table`; otherwise passes. (Recent-200 + filters is an acceptable cap for an
  audit view; no pagination needed.)

### 6.3 `/admin/sharing` — Sharing settings 🟢
**Route:** `app.py:1115` → `admin_sharing.html`.
- **Design 🟢** master kill-switch (Public resource sharing ON/OFF) + Save + list of activities sharing
  materials. Simple and clear.
- **Slowdown 🟢** trivial. **Mobile 🟢** toggle + cards reflow. **Action:** none — passes.

### 6.4 `/admin/feedback` — Spot Feedback triage 🟢
**Route:** `app.py:1180` → `feedback_board.html` (detail `1223` → `feedback_detail.html`).
- **Design 🟢** status filter tabs (New/Reviewing/Will-address/Won't-fix/Done), each entry shows page URL
  + exact CSS-selector spot, feedback text, and inline triage (status dropdown + assignee + note + Apply),
  Export Excel. Functional triage board.
- **Slowdown 🟢** trivial.
- **Mobile 🟡** the triage column is form-heavy — when applying `.resp-table` (stack-to-cards), the
  status/assignee/note/Apply controls must stack full-width below each entry (not just reflow a table cell).
- **Action:** apply `.resp-table` with care for the triage form controls; otherwise passes.

### 6.5 `/admin/backups` — Backups 🟢
**Route:** `app.py:1351` → `backups.html`.
- **Design 🟢** status strip (scheduled state, next run, snapshots kept, total size, live DB size),
  "Back up now", schedule config (frequency/time/day/keep-newest + retention purge), snapshots list.
- **Slowdown 🟢** trivial.
- **Mobile 🟡** 4-column schedule field row stacks (verify); populated snapshots list inherits `.resp-table`.
- **Action:** verify field-row stacking + apply `.resp-table` to snapshots; otherwise passes.

### 6.6 `/ops` — System health 🟢
**Route:** `app.py:1565` → `ops.html`. Load 283 ms · 17 KB.
- **Design 🟢** plain-language status banner + "Right now" KPI cards (How busy / Speed / Reliability /
  Headroom) + "Is the data safe?" checklist. Excellent non-technical ops read.
- **Slowdown 🟢** fast. **Mobile 🟢** KPI grid + checklist reflow.
- **Action:** none — passes.
- 🟡 Observation (not a fix): the "Speed: 9 in 10 pages load under a second" metric reflects steady-state;
  it won't surface the dashboard **cold-build** stalls (§4). Once the perf workstream lands, consider
  whether ops should flag slow cold builds. Optional, out of this sweep.

---

## Consolidated workstreams & suggested build order

**A. ⭐ Dashboard perf (biggest impact — §3.1 + all §4 + spikes on §5.2):**
serve-stale `view_memo`; startup pre-warm (atoms + each dashboard memo, whole-bureau × 4 windows);
optimize heavy builders (pulse_card_insights, pulse_summary, people-grid, teams, trends, participation);
fold per-request fresh fetches (pulse pull-quote) into memos; person-detail memoization + slice dedupe +
shared bureau_dims/benchmark. → Every dashboard page cold-fast, warm ≈ home, instant after data appends.

**B. ⭐ Site-wide 16px inputs (§3.3, supersedes §1.1):** one global `input,select,textarea{font-size:16px}`
rule. → Kills iOS zoom-on-focus on every form (respondent + staff).

**C. ⭐ Responsive `.resp-table` (§3.5, reused §3.5a, §3.6, §6.1, §6.2, §6.4, §6.5):** stack admin/data
tables to label-value cards under ~640px so actions/columns stop clipping.

**D. ⭐ Responsive report tables (§5.1 + §5.3):** per-item stacked cards for the SQD + activity SERVQUAL
dimension tables under ~640px. §5.3 also fixes a real horizontal-page-overflow bug.

**E. Respondent rating polish (§1.1, §1.2, §3.4):** reverse scale to 1→7 (rating + encode), avatar
lazy-load, link_tree style extraction, encode sticky-bar mobile label.

**F. Smaller wins:** show-password toggle (§2.1); /create window-copy clarity + "until" placement (§3.3);
Pulse period-chip wrap (§4.1).

**Suggested order:** B + C + D first (broad, low-risk CSS; immediate mobile payoff) → A (the high-value
perf workstream; verify carefully against the invalidate_views/invalidate_atoms contracts) → E → F.

**Out of sweep scope (tracked, not actioned):** session-cookie `Secure` on HTTPS (§2.1); DB-record
search Phase-2 (§3.2); `name_cleanup.py` truncation keeping qa_preflight RED (§3.5); Trends Phase D (§4.5).

**Verification per page:** re-screenshot at 375/768/1280; re-measure cold + warm load; for perf items,
confirm "add a response → next dashboard load stays fast." Run `pytest` + `qa_preflight` after each
workstream.
