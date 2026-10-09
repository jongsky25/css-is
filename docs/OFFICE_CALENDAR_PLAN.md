# Office Calendar — integration plan

**Status:** planned, not started.
**Source material:** `CY-2026-BLHSD-CALENDAR-OF-ACTIVITIES.docx` (12 monthly grids, colour = owning
unit: Bureau, Sections 1–5).
**Decisions already made by the owner:** everyone can add/edit; the calendar and weekly
whereabouts are two-way; CSS activities and calendar entries are two-way; many views (me /
section / division / bureau); a Calendar option on the home page; emails, reminders and the
bell must all know about it.

---

## 1. Principles

1. **One thing, one home.** An item that is a CSS activity is stored in `event`. An item that
   is only a meeting/trip is stored in `calendar_entry`. The calendar *shows both*; it never
   keeps two copies that can drift.
2. **The calendar proposes, the person disposes.** A calendar assignment can *prefill* a
   person's whereabouts; it can never overwrite what that person said themselves.
3. **Open to everyone, accountable to everyone.** Anyone edits anything, but every change is
   audited, visible ("edited by Mae · 2h ago"), reversible, and notifies the people it affects.
4. **Reuse the machinery.** Scope = `storage.team_scope_for_user`; holidays = `holiday`;
   reminders = `send_reminders.py` jobs + `admin_email` toggles; bell = `_notification_items`;
   home to-do = `office_connect.home_tasks`; tokens = `auth.make_whereabouts_token`. No new
   scheduler, no new mail path.

---

## 2. Data model (all auto-migrated, additive)

```
calendar_entry
  id, title, kind, start_date, end_date (NULL = single day),
  start_time, end_time (nullable; all-day when NULL), time_note (free text kept from the
  Word file, e.g. "1:30-3pm"), venue, modality ('f2f'|'online'|NULL), note,
  owner_org_id -> org_unit  (Bureau / a section — the Word legend colour),
  audience ('bureau'|'unit'|'people'),   -- who it is *for*; people = only the attendee list
  event_id -> event (NULL unless promoted to / created from a CSS activity),
  source ('app'|'import'|'activity'|'whereabouts'),
  created_by, created_at, updated_by, updated_at, cancelled_at, cancelled_by

calendar_entry_person
  entry_id, user_id, role ('lead'|'attending'|'travel'), seen_at, added_by, added_at
  -- seen_at drives the bell: NULL = "you were added / it changed, look".

whereabouts  (existing)   + source ('self'|'calendar')  + entry_id (nullable)
event        (existing)   no new columns needed; calendar_entry.event_id points at it
```

`kind` (icon + filter, not colour): `meeting`, `training` (orientation/workshop/consultation),
`travel` (technical assistance, monitoring, field visit — multi-day, away from the office),
`deadline` (DUE: …), `audit_mr` (IQA, EQA, MR, Mancom, Strat Planning), `banner`
(multi-day bureau notice like "MORATORIUM MR SIA"), `activity` (linked to `event`).

Multi-day items are **one row with a range**, not one row per day (the Word file repeats them
in every cell). Holidays stay in `holiday` and are overlaid, never copied.

---

## 3. Whereabouts ↔ calendar: who wins

Per person per day, the effective status is resolved in this order (first hit wins):

| # | Layer | Source | Notes |
|---|-------|--------|-------|
| 1 | Holiday / suspension | `holiday` | nobody expected; no prompts |
| 2 | **Person's own report** | `whereabouts.source='self'` | always outranks everything below |
| 3 | Calendar default | `whereabouts.source='calendar'` | only `travel` entries set **Field** (+ place as the note); meetings and trainings set nothing |
| 4 | Filed arrangement | ANNEX C via `_wa_default_status` | today's default |

### Calendar → whereabouts (prefill)
- When an entry of kind `travel` has attendees, `whereabouts_defaults()` returns **Field** for
  those people on those weekdays, note = venue ("Palawan"). The Monday email and the weekly
  form open already filled in; the person just confirms.
- Rows written this way are `source='calendar'`, carry `entry_id`, and are **only ever
  rewritten by the calendar**. A row the person has touched or submitted becomes
  `source='self'` and the calendar never edits it again.
- Entry moved / shortened / cancelled → unconfirmed `calendar` rows follow it automatically.
  A *confirmed* `self` row is left alone and instead raises a **mismatch** (below).

### Whereabouts → calendar (suggest)
- If a person reports **Field** with a note and no calendar entry covers them that day, the
  form offers one tap: "Add this to the calendar" (creates a `travel` entry, `source=
  'whereabouts'`, audience = their unit). Never automatic — a whereabouts note is private to
  the person until they choose to publish it.
- **Leave** shows on the calendar as "On leave" only (no reason, no note) in the availability
  row. It is never an entry.

### Mismatches (soft, never blocking)
| Situation | Who is told | Where |
|-----------|-------------|-------|
| Assigned to a trip, but reported Office/Leave | the person | bell + home task "Confirm where you'll be" |
| Assigned to an entry while on leave | the person + the entry's lead | bell; chip on the entry |
| Same person double-booked at the same hour | the person | chip only (no email) |
| Trip changed after the person confirmed | the person | bell, links to that week's form |
| Chief roll-up | section chiefs | extra lines in the existing `whereabouts_rollup` email |

AWA (work-from-home / day off) is untouched: it stays layer 4. Wellness breaks never appear on
the calendar (privacy).

---

## 4. CSS activity ↔ calendar: two-way

### Activity → calendar (automatic)
- **Every activity appears on the calendar with no extra step.** The calendar view unions
  `calendar_entry` rows with `event` rows that have no entry yet, so existing activities show
  immediately and nothing needs backfilling.
- Creating an activity (`/create`) also writes a linked `calendar_entry` in the same
  transaction: owner = `lead_org_id`, attendees = creator + resource persons who have accounts,
  kind `activity`.

### Calendar → activity (one tap)
- Any `training`/`meeting` entry gets **"Collect feedback (CSS)"**: opens the create form
  pre-filled (title, dates, venue, modality, organizer, speakers from attendees) and links the
  new `event` back via `calendar_entry.event_id`.
- After an entry with kind `training` has passed with no link, the creator gets a single
  next-day nudge ("Did this one have participants? Collect feedback"). Internal meetings
  (Mancom, IQA, Strat Planning, MR, banners) are marked non-eligible and never nudged.
- Duplicate guard: creating an activity, or promoting an entry, first looks for a same-day,
  similar-title counterpart and offers **Link instead of create** (reuses the existing
  duplicate-warning logic).

### Single source of truth once linked
- Title, dates, venue, modality, speakers live on the **event**. The entry is a mirror.
  Editing either screen writes the event; a small `sync_entry_from_event()` refreshes the entry.
- If the activity already has registrants, a date/venue edit from the calendar shows the
  existing "this will notify N registrants" step (`activity_messages`) instead of silently
  changing it.
- Calendar cards for linked items show live CSS chips: *N registered · feedback open · score
  4.6* and link to the Monitor / results pages. Cancelling a linked entry asks whether to
  archive the activity too.

---

## 5. Views

One page, `/calendar`, plus the home-page tab (§6). Two independent controls:

**Scope** (reuses `team_scope_for_user`, so nobody sees outside their rights):
`Me` · `My section` · `My division` · `Bureau` — plus a person picker and a section filter
(the colour legend, clickable). "Mine + bureau-wide" is the default blend: your own items and
anything with audience = bureau.

**Layout:**
| Layout | For | Notes |
|--------|-----|-------|
| **Agenda** | default on phones; "what's next" | grouped by day, today pinned, holidays inline |
| **Week — people × days** | chiefs: "who is where" | rows = people (avatars from `_faces`), cells show trips as spanning bars, leave as hatched, whereabouts status as a dot |
| **Month grid** | the familiar Word layout | colour = owner unit, up to 3 chips/day then "+N more" |
| **Timeline** | travel-heavy planning | multi-day bars per person across 4–8 weeks |

URL state: `/calendar?scope=section&view=week&date=2026-10-12`; shareable, restores on reload.

---

## 6. Home page

Today's toggle is **Team | Me** (`?view=me`). Recommendation: make it **Team | Me | Calendar**
(`?view=calendar`), because the first two are about *people and wellbeing* and the third is a
different mental mode — but don't bury the calendar behind it:

- **Team and Me both get a slim "This week" card** (next 5 items for that scope + a "who's away"
  strip). It is the glanceable version; one click opens the Calendar tab.
- **Calendar tab** = the full component: scope pills, Week/Month/Agenda switch, quick-add.
  Default scope follows where you came from (from Team → my section; from Me → me).
- **To-do strip** (`home_tasks`) gains `_task_calendar`: "2 things today", "Confirm your
  whereabouts for the Palawan trip" (tone *todo*), "Collect feedback for Tuesday's orientation"
  (tone *todo*). Failures are swallowed like the other sources.
- Nav gets a **Calendar** entry in the main menu (the menu already scrolls on short screens).

---

## 7. Visual design (so it is pleasant, not a spreadsheet)

- **Colour = owner unit, shape/icon = kind, text always present.** Reuse the section colours
  from the Word legend, mapped onto the existing `_unit_badges.html` tokens so dark mode and
  contrast already work. Colour is never the only signal (existing a11y chart tests apply).
- Entry chip: left colour bar, kind icon, 1-line title, time if known, 2–3 stacked avatars for
  attendees; hover/tap opens a side sheet, not a new page.
- Multi-day trips are **spanning bars**, not 5 repeated chips.
- Today column highlighted; holiday days tinted with the holiday name; "MORATORIUM" style
  banners render as a thin ribbon across the week, not as an entry on every day.
- **Quick add**: tap a day or drag across days → bottom sheet: title, dates, people ("whole
  section" shortcut), kind, "also collect CSS feedback" toggle. Everything else optional.
- Linked CSS items get a small "feedback" pill that changes with lifecycle (upcoming → open →
  concluded, score once available).
- Empty states say what to do ("Nothing on for your section this week — add something").
- Phone: Agenda only, month collapses to a density heat-strip; no horizontal page scroll.
- Respect the repo rule: bump `app.css?v=` in `dash_layout.html` / `public_layout.html` whenever
  `app.css` changes.

---

## 8. Emails, reminders, bell

### Email (all through `mailer.py` / `send_reminders.py`, each with an on/off in `admin_email`)
| Job | When | To | Notes |
|-----|------|----|-------|
| **Monday week-ahead** | existing whereabouts Monday email | each person | **Extend, don't add a second email**: adds "On your calendar this week" and the prefilled whereabouts |
| **Added / changed / cancelled** | immediately, batched per person within ~15 min | attendees | one email per burst; skipped for the editor; `email_log` dedupes |
| **Day-before reminder** | daily sweep | attendees of tomorrow's entries | linked activities keep using the existing `--events` job so no one gets two |
| **Chief roll-up** | existing Tuesday roll-up | section chiefs | + mismatches (§3) |
| **CSS follow-up nudge** | day after a `training` entry | creator, once | §4 |

Every invite/reminder carries an `.ics` attachment. Plus a **personal calendar feed**: a
signed webcal URL per user (same signing approach as the whereabouts token), choice of "mine"
or "my section", so it shows in Outlook/Google/phone calendars.

### Bell (`_notification_items`)
New rows, each count taken from the same query the destination page uses:
- "N new calendar entries for you" / "N changes to your calendar" → `/calendar?scope=me`
  (from `calendar_entry_person.seen_at IS NULL`; opening the page marks them seen).
- "Confirm your whereabouts for <trip>" → that week's whereabouts form (mismatches, §3).
- Chiefs: "N people on <section> have a conflict this week" (optional, can start off).
Not in the bell: "you have a meeting today" (that is informational and lives on the home
to-do/This-week card). The bell stays for things that need an action or a look.

### Preferences
`/me` gets three switches (invitations & changes · day-before reminder · Monday summary);
defaults on. Admins can turn each job off globally in Admin → Email.

---

## 9. Getting the Word calendar in (one-time importer)

1. Admin uploads the .docx → parser reads each month table, day cells, and each entry's cell
   **shading colour** (→ owner unit, via a one-time colour→unit mapping screen).
2. Consecutive identical lines are merged into ranges; typo variants ("Strat Planningv",
   "Strat Plannin") are grouped and offered as one; inline holiday lines are dropped (already in
   `holiday`); `kind` is guessed from keywords (TA/monitoring/field visit → `travel`,
   Orientation/Workshop/Consultation → `training`, DUE → `deadline`, IQA/EQA/MR/Mancom → `audit_mr`).
3. Names in parentheses (Riza, Mae, Tek, Doc Malou, Sir Jong…) are matched to accounts via the
   directory + new nickname field; anything unmatched goes to a "who is this?" queue.
4. Admin reviews a preview table (approve / edit / skip per row), then imports. Idempotent on
   (title, start, owner) so re-running never duplicates.
5. After import the Word file is retired; the app is the calendar.

---

## 10. Guardrails for "everyone can edit"

- Every create/edit/cancel writes to `audit_log` and sets `updated_by/updated_at`.
- Cancel is a soft delete (`cancelled_at`) with **Restore** for 30 days; hard delete is
  admin-only.
- Optimistic check on save: if `updated_at` changed since the form opened, show what changed
  instead of overwriting.
- Edits to bureau-audience entries, and to `audit_mr` / `banner` kinds, also notify the owning
  unit's chief (no approval needed — accountability, not a gate).
- Unlinked-account rule applies: an account with no directory link sees only bureau-audience
  entries and its own, never a section's.

---

## 11. Phasing (each phase is shippable on its own)

| Phase | Scope | Version bump |
|-------|-------|--------------|
| **P1** | `calendar_entry` + persons; importer + review screen; `/calendar` Agenda + Month; holiday overlay; audit/restore | minor |
| **P2** | Home **Calendar** tab + "This week" card + `_task_calendar`; scope/section filters; Week (people × days) | minor |
| **P3** | Activity ↔ calendar two-way (auto-entry on create, "Collect feedback", link/dedupe, CSS chips) | minor |
| **P4** | Whereabouts interplay (prefill, suggest, mismatches) + bell items | minor |
| **P5** | Emails (week-ahead, change/cancel, day-before, roll-up lines, CSS nudge) + `.ics` + personal feed + `/me` prefs | minor |
| **P6** | Timeline layout, quick-add polish, optional natural-language add via `ai_core` | minor |

Every phase: bump `version.py`, add a `CHANGELOG.md` entry, add tests, bump `app.css?v=` if CSS changed.

## 12. Tests to write

- Scope: unlinked account sees no section; division chief sees division; Director sees bureau.
- Precedence: holiday > self report > calendar default > filing; calendar never overwrites a
  `self` row; moving a trip updates only unconfirmed `calendar` rows.
- Activity sync both ways: create → entry; edit entry → event; edit event → entry; cancel;
  duplicate-link path; registrant-notify guard.
- Importer: range merging, colour→unit, nickname match/unmatched, idempotent re-run.
- Notifications: bell counts match destination page; seen_at clears; email batching; no
  duplicate with the `--events` job; opt-outs honoured.
- Privacy: leave shows no reason; wellness never appears.

## 13. Risks / notes

- **Colour → unit mapping** needs one human confirmation (the Word legend is only colours).
- **Nickname ambiguity** (two "Mae"s) is real; the "who is this?" queue is mandatory, not optional.
- **Bell cost**: `_notification_items` runs on every request — index `(user_id, seen_at)` and keep
  the queries to single indexed counts.
- **Email volume** is the main risk of open editing; the burst batching and the "merge into the
  Monday email" rule are what keep it tolerable.
- Calendar reads are date-range queries on indexed `start_date/end_date`; they do not need the
  atoms cache (`view_memo`), which is for survey analytics.
