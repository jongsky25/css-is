# Calendar — real data, calendar-only view, every screen (plan v2)

**Status:** planned, not started. Owner answered the open questions with "go with the defaults".
**Builds on:** `docs/OFFICE_CALENDAR_PLAN.md` (A–H increments, all shipped up to 4.0).
**Source data:** `CY-2026-BLHSD-CALENDAR-OF-ACTIVITIES.docx` (kept out of the repo; it names staff).

Owner goals, in their words:
1. Clicking **Calendar** shows only the calendar.
2. It fits every screen, not just phones.
3. A more beautiful calendar.
4. Everything fits together, buttons included, with nothing wasted.
5. Intuitive, user-friendly, frictionless.
6. Phased, incremental improvement.
7. Import the CY 2026 Word calendar.

---

## 0. Review of plan v1 (what this version changes)

| v1 said | Problem found on review | v2 does |
|---|---|---|
| Import after the UI work | The redesign would be tuned on an empty calendar. September alone has 51 items. | **Import first (Phase 0)**, so every later phase is checked against real density. |
| Fill "AM"/"PM" with default clock times (08:00–12:00 / 13:00–17:00) | That invents data: a "PM" meeting would show as 1 pm and go into `.ics` feeds and reminders as fact. | Keep `time_note`, add **no** clock time. AM sorts before PM before untimed, and shows as an "AM"/"PM" chip. |
| Add a regression test that parses this .docx | It would commit a file of staff names and schedules into the repo. | The test builds a **synthetic fixture** with the same shapes (as `tests/test_calendar_import.py` already does). Real-file numbers live only in the import report. |
| "Undo this import" by deleting the batch | No schema link from an entry to its batch was assumed | Already possible: `calendar_import_batch.result.created` lists every `entry_id`. Undo reads it, so no migration is needed. It only deletes entries **not edited since import**; edited ones are listed for a person to decide. |
| Turn repeats into one recurring entry | The repeats are irregular: LHSI ×7 and HSDD ×5 don't all land on a rule. A wrong rule invents meetings. | Suggest a series **only when `recurrence.build()` reproduces every date exactly**. Otherwise the items stay separate and are tagged so they can be filtered together. |
| "Staging first, then production" | This session cannot reach the Hugging Face deployment and shouldn't. | Claude runs the full import on a **local copy** and produces the report. An admin runs the same upload in production through `/calendar/import`, where the review screen shows the same numbers. |
| Every agenda day shows its own empty card | 14 cards that say "Nothing scheduled" are noise, and the screenshot shows a page-level empty state plus today's empty card. | Collapse empty days ("Sat 10 – Mon 12 · nothing scheduled"). Today always shows. One empty state, never two. |
| "Fix the flash banner" (cause unknown) | — | Cause found: `office_connect.html` imports the `flash` **macro**, which shadows the page's `flash` text inside the included `_calendar_body.html`, so the macro object is printed. Rename the page value to `cal_flash`. |

---

## 1. Principles

1. **Content before controls.** On a phone the first event must be visible without scrolling (today: about 1,000 px down).
2. **One calendar, two doors.** `/calendar` and the home **Calendar** tab render the same `_calendar_body.html`. Nothing is styled twice.
3. **Never invent data.** The importer proposes and a person approves. No made-up times, owners or series.
4. **Colour is never the only signal** (existing rule): the unit name is written on every item, and status has a shape (dashed, struck through).
5. **Progressive enhancement** (existing rule): every view works without JS, and JS only adds sheets, swipe and shortcuts.
6. **Small PRs.** Each increment = one PR with tests, a `CHANGELOG.md` entry, a `version.py` bump and a `calendar.css?v=` cache-buster bump.

---

## 2. Facts the plan is built on

**The Word file** (parsed with the existing `calendar_import.parse`, no DB writes):

| | |
|---|---|
| Month tables / raw lines | 12 / 678 |
| Drafts after merging multi-day runs | **380** (105 multi-day) |
| Owner from colour | S1 91 · S4 86 · S3 53 · S2 50 · Bureau 33 · S5 19 |
| No owner colour | **48** |
| Types | meeting 200 · training 97 · travel 48 · MR/audit 33 · deadline 1 · banner 1 |
| Status | 373 confirmed · 6 tentative · 1 postponed |
| Holiday lines (set aside, not drafts) | 18 |
| Lines with a people hint | 92 |
| No clock time | 306 (many only "AM"/"PM") |
| Per month | Jan 29 · Feb 42 · Mar 42 · Apr 38 · May 21 · Jun 33 · Jul 47 · Aug 32 · Sep 51 · Oct 32 · Nov 10 · Dec 3 |
| Source typos | "130pm", "10an", "Strat Plannin/Planningv", "Orientation on/to" |
| Repeats | "Learning Exchange Session on LHSI" ×7 · "HSDD Monthly Mtg" ×5 · "Q# MR" ×3 · "Meeting with WHO" ×3 |
| Longest title | 209 characters |

**The page today** (from the screenshots and `templates/office_connect.html`, `_calendar_body.html`, `static/css/calendar.css`):
- The Calendar tab still renders the hero, companion, Team/Me/Calendar switch and the whole to-do list above the calendar.
- Toolbar: 5 scope pills, 4 layout pills, 4 buttons, nav links, 3 selects with a Filter button, unit chips and a range line, about 900 px on a phone.
- The month grid is hidden below 760 px. Week has `min-width:52rem`. Timeline has 1.55 rem columns.
- The add form's From/To time inputs overflow on a phone, and the "Send feedback" button covers the footer text.
- `--page-max` is 1600 px (1920 px on "full"), and the agenda stretches to fill it.

---

## 3. Phases

Each increment: **files · done when · tests**. Tests run with `./run_tests.sh`. UI increments are also checked at **360, 390, 768, 1024, 1440 and 1920 px**, in light, dark and contrast themes (Playwright, Chromium already installed).

### Phase 0: import the CY 2026 Word calendar

**P0.1 Parser fixes** (`calendar_import.py`, `tests/test_calendar_import.py`)
- **Status: done (v4.1).** The dry run showed the parser already handled "130pm", "10an" and typo grouping, so those needed no work. Reading all 380 drafts found different problems, now fixed:
  - "MR SIA" (measles-rubella) was being read as a management review (3 items).
  - A link in a line ("Meeting Link: https://…") now becomes the meeting link.
  - A start time before 06:00 ("3 AM") is not kept and is flagged.
  - A bare time left in a title ("PK TWG 10-12", 16 items) is flagged, not guessed.
  - A fragment title ("and OOP") and days that differ by a whole word (LDS vs SGA merged into one range) are flagged.
  - "Immaculate Concepcion" is recognised as a holiday line (19 holiday lines, 379 drafts).
- *Tests:* made-up lines with the same shapes, in `tests/test_calendar_import.py`.

**P0.2 Suggestions, never decisions** (`calendar_import.py`, `calendar_import_apply.py`)
- `owner_suggestion` for the 48 unowned drafts, from (in order) a people hint that resolves to one unit, a tag that one unit owns ≥80% of in this file, or a "Section N" in the title. It is shown preselected-but-flagged, never silently applied.
- **Status: done (v4.1)** in `calendar_import_suggest.py`, stored in the batch payload. On this file 5 of 47 unowned items get a suggestion (42 need a person), and **no repeat fits a rule exactly** (LHSI Learning Exchange, HSDD Monthly, Q MR all fall on irregular dates), so no series is suggested. The check is kept for future files.
- `series_suggestion`: same title, owner and kind, three or more single-day items, suggested only when a `recurrence` rule reproduces every date and adds none.
- Holiday comparison already exists on the review page (`have_hol`), so P0.4 only needs the "add the missing ones" checklist.
- *Tests:* a suggestion is never applied without the review form saying so; an irregular repeat gets no series.

**P0.3 Review screen made workable for 380 rows** *(done, v4.2: 307 of 379 look fine, 72 need you on the CY 2026 file; checked at 390, 768 and 1440 px)* (`templates/calendar_import_review.html`, `calendar_routes.py`)
- Top: a **"Needs you" list**: unowned, warnings, tentative/postponed, suggested series. The clean rows sit below, collapsed, as "327 rows look fine".
- Bulk actions: *set owner for selected*, *approve all clean rows*, *skip before a date*.
- A sticky summary bar: "Will import N · skip M · needs you K".
- Phone layout uses the existing `.resp-table` card pattern (from `PAGE_SWEEP_PLAN.md`).
- *Done when* an admin can clear the 48 + warnings without horizontal scrolling at 390 px.

**P0.4 Apply, holidays, undo** *(done, v4.3; series approval left out because no repeat in this file fits a rule)* (`calendar_import_apply.py`, `calendar_routes.py`, `storage.py`)
- Apply (exists): mapping, audience = bureau, idempotent `import_key`, audit.
- Approved series → one entry with `rrule`. Their source drafts are recorded in the batch result so re-import doesn't recreate them.
- Holidays: "missing" ones are offered as a checklist and added with `storage.set_holiday`.
- **Undo import** on the batch page: deletes created entries untouched since import (`sequence` still 0 and `updated_at` = `created_at`). It lists edited entries instead of deleting them, and is audited.
- *Tests:* re-import → 0 new; undo removes only untouched; series not duplicated on re-import.

**P0.5 People** *(done, v4.4: the resolver already handled the guide's names, so the work was capturing 19 more items' names and a usable phone layout; items with names went from 92 to 111)* (existing B3 screen, `calendar_people.py`)
- Run the 92 hints through the resolver. Ambiguous names are never auto-assigned (existing rule), and nicknames learned here are remembered for next year.

**P0.6 Dry run and hand-off** *(done, v4.5: report written, not committed because it names staff; it found the double-apply hazard and two noisy flags, now fixed)*
- Claude imports into a local copy of the DB and writes `scratchpad/import-report.md`: counts by month and owner vs §2, the 48 owner calls with suggestions, the series proposals, the holiday diff and 20 spot-checks against the Word file.
- The owner reviews the report. An admin then runs the same upload in production. Past months (Jan–Sep) are imported as history.

### Phase 1: calendar-only view and a compact toolbar *(done, v4.6; empty days were already omitted from the agenda, so P1.3 only fixed the duplicate empty message)*

**P1.1 Calendar-only Calendar tab** (`templates/office_connect.html`, `app.py` home route)
- When `view == "calendar"`: no hero, companion, to-do or "Coming up". The top is a slim row: the Team / Me / **Calendar** segmented switch (so leaving is one tap) and the page title.
- Also skip building data for blocks that aren't drawn (tasks, insights) on this view, which makes the page faster.
- Fix the `<Macro 'flash'>` banner (rename to `cal_flash`).
- *Tests:* `test_calendar_home_tab.py`: the calendar view contains no `oc-todo`/`oc-hero`, and the flash text renders.

**P1.2 Two-row toolbar** (`_calendar_body.html`, `calendar.css`)
- Row 1: `[Agenda | Week | Timeline | Month]` segmented, then **+ Add** (primary) and **⋯** (Quick add, Birthdays, Import from Word for admins, Subscribe .ics).
- Row 2: `‹  Today  ›` + range label ("Oct 9 – 22") + **Scope ▾** (one `<select>`, replacing 5 pills) + **Filters (n)**.
- Filters (type, status, tag, units) move into a `<details>` panel that auto-submits on change (no-JS: a Filter button inside it). Active filters show as removable chips.
- All controls ≥ 44 px tall, and the phone toolbar is ≤ 2 rows.
- *Done when* at 390 px the first day card is visible without scrolling.

**P1.3 Empty states and the feedback button**
- Collapsed empty days, one empty state, and an "Add something" action in it.
- Bottom padding equal to the feedback button height on calendar pages, so nothing is covered.

### Phase 2: fits every screen *(done, v4.7, with two deliberate cuts: a multi-column agenda instead of a mini-month pane, and no day-by-day Week list under 480px)*

**P2.1 Layout by width** (`calendar.css`)

| Width | Agenda | Week | Timeline | Month |
|---|---|---|---|---|
| ≤ 480 | single column | day-by-day list, swipe/arrow between days | sticky names, horizontal scroll with fade hint | compact grid: dots per day; tap a day → that day's agenda |
| 481–1023 | single column, wider cards | 5 columns, no forced min-width | as phone | full grid, 2 items per day + "+n" |
| ≥ 1024 | **two panes**: mini month + unit legend left, agenda right | full | full | full, 3 items per day + "+n" |
| ≥ 1600 | content capped at ~1400 px and centred | — | uses the width | — |

- Use `clamp()` for type and spacing, and `minmax(0,1fr)` so long titles (209 chars) wrap or clamp instead of widening the page.
- *Tests:* a Playwright script asserts `scrollWidth <= innerWidth` on every view at all six widths.

**P2.2 Forms** (`calendar_entry_form.html`)
- Native `type=date|time`, so From/To stack under 480 px, and the italic "Pick a date" placeholder style is dropped.
- Keep the long form; Quick add stays the fast path.

### Phase 3: a more beautiful calendar *(done, v4.8; no "now" line, because the grids are by day, not by hour)*

- **Day header:** a date badge (big number with the weekday above it), a "Today" accent, and a weekend tint.
- **Event card:** a time column (or an AM/PM chip, or "All day"), a title clamped to 2 lines, a unit colour bar plus the unit name, a kind icon (meeting, training, travel, MR) and a quieter meta line (venue, faces, tags).
- **Week/Timeline:** a "now" line, a holiday ribbon, and multi-day bars with rounded ends only where they truly start and end.
- **Month:** today ring, holiday label, a density dot on the phone.
- Same tokens and themes as now (`--cal-*` pairs already have light, dark and contrast). No new colours without a contrast check.

### Phase 4: frictionless *(done, v4.9; **S** searches instead of `/` because the app already uses `/`; no refresh-free view changes, and no add button inside Week cells)*

- **Details sheet:** tapping an item opens a bottom sheet (phone) or side panel (desktop) fetched from the entry page. Back/Escape closes it, and the URL updates so it can be shared. Without JS it's the ordinary link.
- **Add from where you are:** tap an empty day or slot → Quick add with that date (already on Timeline; extend to Agenda, Week and Month).
- **Remember** the last layout and scope per person (a cookie read server-side, so there's no flash of the wrong view).
- **Keyboard:** ← / → move, `T` today, `A` add, `/` search. **Swipe** left/right on touch.
- **Search** by title across the year (380 items need it). It reuses the filter form.

### Phase 5: hardening

- Accessibility: focus order through the toolbar and sheet, `aria-current` on day/view, reduced motion, and screen-reader day headings.
- Playwright screenshot set (six widths × four views × light/dark), kept in the scratchpad and not committed.
- `qa_smoke.py` gets the calendar views. `docs/OFFICE_CALENDAR_PLAN.md` gets a pointer to this file.

---

## 4. Order, size and risk

| Order | Increment | Size | Main risk | Guard |
|---|---|---|---|---|
| 1 | P0.1–P0.2 | S | a parser change shifts existing drafts | the existing parser tests + new cases |
| 2 | P0.3–P0.4 | M | bulk actions apply the wrong rows | review shows counts, apply is idempotent, undo exists |
| 3 | P0.5–P0.6 | S | wrong person on an item | ambiguous names are never auto-assigned |
| 4 | P1.1–P1.3 | M | home route regressions | home-tab tests; other views unchanged |
| 5 | P2.1–P2.2 | M | horizontal overflow somewhere | the six-width overflow check |
| 6 | P3 | M | theme contrast | contrast theme check per change |
| 7 | P4 | L | JS-only paths | each feature has a no-JS fallback |
| 8 | P5 | S | — | — |

## 5. How we'll know it worked

- Phone: first event visible without scrolling, and the toolbar is ≤ 2 rows.
- No horizontal page scroll at any of the six widths in any view.
- Import: 380 drafts accounted for (imported + skipped + merged into series = 380), 0 duplicates on re-import, and 18 holidays reconciled.
- Adding an item takes ≤ 3 taps from the calendar with Quick add.
- `ui_telemetry` page views on `/calendar` and `/?view=calendar` are compared before and after (the telemetry already exists).
