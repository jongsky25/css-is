# Office Calendar (with Birthdays) — integration plan v2

**Status:** planned, not started.
**Source material:** `CY-2026-BLHSD-CALENDAR-OF-ACTIVITIES.docx` — 12 monthly Word grids; the
cell colour marks the owning unit (Bureau, Sections 1–5).
**Owner decisions so far:**
- everyone can add and edit;
- weekly whereabouts ↔ calendar are two-way;
- CSS activities ↔ calendar are two-way;
- views for me / section / division / bureau;
- a Calendar option on the home page;
- emails, reminders and the bell all know about it;
- **staff birthdays are captured and remembered.**

v2 revises v1 after a review against the code and against calendar standards (sources in §16).
§0 lists what changed. §13 breaks the work into **increments small enough for one Sonnet session
each**.

---

## 0. What changed from v1 (review findings)

| v1 said | Problem | v2 does |
|---|---|---|
| Activities copied into `calendar_entry` on create *and* unioned at read time | Two mechanisms; copies drift; needs a sync function | **Read-time only.** Activities come from a provider. A `calendar_entry` linked to an event is an *overlay* holding only calendar-only fields (people, tags, kind). Title/date/venue are always read from `event`. Nothing to sync. |
| Calendar *writes* `whereabouts` rows (`source='calendar'`) and rewrites them when trips move | Write fan-out, a new column, many edge cases | **Computed at read time.** `whereabouts_defaults()` consults the calendar between the person's own report and the filing. Only the person's submit writes rows, so a moved trip is reflected automatically. |
| Change emails "batched within 15 min" | No queue existed to batch with | The app already runs an **in-process 60-second scheduler** (`app._scheduler_loop`). Add a `calendar_outbox` table flushed by that loop. |
| Ad-hoc fields | Can't export cleanly, no recurrence, no versioning | Fields line up with **iCalendar (RFC 5545)**: opaque random `uid`, `sequence`, `status`, `rrule`/`exdate`. Exports, feeds and future sync then come almost free. |
| Views, ICS, emails and the bell each query their own way | Logic duplicated four times | One **layer registry** (`office_calendar.py`): every source emits the same item shape, and every consumer reads it. Birthdays, holidays, leave and deadlines are just more layers. |
| No status | The Word file has "(Tentative)", "(POSTPONED)", "Pending" | `status`: tentative / confirmed / postponed / cancelled. |
| No recurrence | The Word file repeats HSDD Monthly, Section 1 Mtg, LES, quarterly MR | Recurrence (weekly / monthly / nth-weekday, plus exceptions), in a later increment (H1). The schema reserves the columns from day one. |
| No program tags | Most of the file is themed (PK, BHW, LHS ML, ZBB, Sulu Transition, SHF, LIPH) | `tags` with a filter, e.g. "show me everything PK". |
| ICS feed for staying current | Google refreshes subscribed feeds only every ~12–24h; Outlook web every few hours | The feed is for awareness only. Urgent changes always go by bell + email. Say so in the UI. |
| One big phase per feature | Too large for one session | 24 small increments with files, done-when and tests (§13). |

---

## 1. Principles

1. **One thing, one home.** CSS activity → `event`. Meeting or trip → `calendar_entry`. Holiday →
   `holiday`. Birthday → directory person. The calendar *renders* all of them and copies none.
2. **The calendar proposes, the person disposes.** A calendar assignment can prefill someone's
   whereabouts. It never overrides what that person reported.
3. **Open to everyone, accountable to everyone.** Anyone edits. Every change is audited, visible,
   reversible, and announced to the people it affects.
4. **Standards-shaped data.** Store what iCalendar can express, so export, subscribe and later sync
   are thin layers, not rewrites.
5. **Reuse the machinery.**
   - Scope: `storage.team_scope_for_user`.
   - Scheduler: `app._scheduler_loop`.
   - Reminder jobs and admin toggles: `send_reminders.py` + `admin_email`.
   - Bell: `_notification_items`.
   - To-do strip: `office_connect.home_tasks`.
   - Signed links: the `auth.make_whereabouts_token` pattern.
   - Mail: `mailer.py` + `email_log`.
   - Audit: `audit_log`.
6. **Keep `app.py` thin.** It is ~15.9k lines. Calendar logic lives in new modules:
   `office_calendar.py`, `calendar_import.py`, `birthdays.py`. Routes go in a
   `calendar_routes.py` FastAPI `APIRouter` that `app.py` includes (one line). The existing
   auth middleware gates by path, so it covers router routes unchanged.

---

## 2. Architecture: the layer registry

`office_calendar.py` owns one function every consumer calls:

```python
items_between(conn, user, start, end, *, scope="mine", layers=None, filters=None) -> list[CalItem]
```

`CalItem` is a plain dict, the single shape used by views, home, ICS, emails, bell and the future API:

```
{ "key": "entry:42" | "event:17" | "holiday:2026-12-25" | "bday:88:2026" | "leave:5:2026-10-12" | "deadline:awa:2026-10-15",
  "layer": "entries" | "activities" | "holidays" | "leave" | "birthdays" | "deadlines",
  "title", "start" (date), "end" (date, inclusive), "start_time", "end_time", "all_day",
  "kind", "status", "owner_org_id", "owner_label", "tone" (unit colour token),
  "people": [{user_id, name, initials, photo_url, role}], "tags": [...],
  "venue", "modality", "url" (detail page), "meeting_url",
  "css": {lifecycle, registered, score} | None,     # activities only
  "flags": ["conflict", "mismatch", "tentative"], "editable": bool, "private": bool }
```

Each **provider** is a function `(conn, user, start, end, scope) -> [CalItem]` registered in
`LAYERS`:

| Layer | Source | Notes |
|---|---|---|
| `entries` | `calendar_entry` | meetings, trips, trainings, deadlines, banners |
| `activities` | `event` (+ overlay entry) | every CSS activity, no backfill needed |
| `holidays` | `holiday` | regular / special / suspension |
| `leave` | `whereabouts` status = leave | shows **"On leave"** only, never a note |
| `birthdays` | directory person (§6) | only for people who opted in, within their sharing scope |
| `deadlines` | computed | AWA filing deadline, whereabouts week due, OPCR dues from entries |
| *future* | rooms, vehicles, travel orders, WFP targets, DOH-wide inbound ICS | a new provider plus one registry line |

Scope resolution happens **once**, in `items_between`, through `team_scope_for_user`. A provider
receives an already-resolved scope and can't widen it. An unlinked account (kind `"none"`) gets
bureau-audience items and its own items only — the same safety rule `office_connect` follows.

---

## 3. Data model (auto-migrated, additive)

```sql
calendar_entry (
  id INTEGER PRIMARY KEY,
  uid TEXT NOT NULL UNIQUE,          -- random UUID hex (RFC 7986: opaque, no host/user data)
  sequence INTEGER NOT NULL DEFAULT 0,  -- +1 on any date/time/status/recurrence change
  title TEXT NOT NULL,
  kind TEXT NOT NULL,                -- meeting|training|travel|deadline|audit_mr|banner|activity
  status TEXT NOT NULL DEFAULT 'confirmed', -- tentative|confirmed|postponed|cancelled
  start_date TEXT NOT NULL, end_date TEXT,  -- inclusive range; NULL = single day
  start_time TEXT, end_time TEXT,    -- 'HH:MM' Asia/Manila; NULL = all day
  time_note TEXT,                    -- free text kept from import ("1:30-3pm", "AM")
  venue TEXT, modality TEXT,         -- 'f2f'|'online'|'hybrid'
  meeting_url TEXT, note TEXT,
  owner_org_id INTEGER REFERENCES org_unit(id),
  audience TEXT NOT NULL DEFAULT 'unit',    -- bureau|unit|people
  event_id INTEGER UNIQUE REFERENCES event(id), -- set => overlay on a CSS activity
  rrule TEXT, exdates TEXT,          -- reserved; used from increment H1 (RFC 5545 subset)
  source TEXT NOT NULL DEFAULT 'app',       -- app|import|whereabouts
  import_key TEXT UNIQUE,            -- idempotent re-import
  created_by, created_at, updated_by, updated_at, cancelled_at, cancelled_by
);
CREATE INDEX idx_cal_entry_dates ON calendar_entry(start_date, end_date);

calendar_entry_person (entry_id, user_id, role TEXT,  -- lead|attending|travel
                       seen_seq INTEGER,              -- last sequence this person has seen (bell)
                       added_by, added_at, PRIMARY KEY(entry_id, user_id));
CREATE INDEX idx_cal_person_user ON calendar_entry_person(user_id);

calendar_entry_tag (entry_id, tag, PRIMARY KEY(entry_id, tag));

calendar_entry_revision (id, entry_id, sequence, changed_by, changed_at, diff_json);
                         -- powers "History" + Restore; audit_log still gets a one-line summary

calendar_outbox (id, user_id, entry_id, change TEXT, created_at, sent_at);
                         -- added|changed|cancelled|reminder; flushed by the scheduler (§9)

-- birthdays (§6): on resource_person (the directory person, internal staff only)
resource_person + birth_month INTEGER, birth_day INTEGER,   -- NO year
                + birthday_share TEXT NOT NULL DEFAULT 'none',  -- none|section|division|bureau
                + birthday_consent_at TEXT, birthday_consent_text TEXT
```

- `sequence` increments on date, time, status or recurrence changes, so ICS clients treat the
  update as newer.
- All times are Asia/Manila (`tzutil`).

---

## 4. Whereabouts ↔ calendar

Effective status per person per weekday. The first match wins, and it's computed at read time:

| # | Layer | Source |
|---|---|---|
| 1 | Holiday / suspension | `holiday` — nobody expected, no prompts |
| 2 | **Own report** | `whereabouts` row (written only when the person submits) |
| 3 | Calendar default | a `travel` entry listing the person → **Field**, note = venue |
| 4 | Filed arrangement | ANNEX C via `_wa_default_status` (today's behaviour) |

**Calendar → whereabouts.** `whereabouts_defaults()` adds layer 3. The Monday email and the form
open already showing "Field — Palawan". Confirming writes the person's own row. If the trip moves
*before* they confirm, the default simply moves with it.

**Whereabouts → calendar.** When someone reports **Field** with a note that no entry covers, the
form shows "Add this trip to the calendar". One tap creates a `travel` entry (source
`whereabouts`, audience = their unit). It's never automatic: the note stays private until they
publish it.

**Mismatches** come from one function, `office_calendar.mismatches(conn, user_ids, week)`. They're
soft and never block anything:

| Case | Told | Where |
|---|---|---|
| On a trip, but reported Office/Leave | the person | bell + home task "Confirm where you'll be" |
| Listed on an entry while on leave | the person + the entry's lead | bell; chip on the entry |
| Double-booked at the same hour | the person | chip only |
| Trip changed after they confirmed | the person | bell, links to that week's form |
| Section summary | chiefs | extra lines in the existing Tuesday roll-up |

AWA stays at layer 4. Wellness breaks never appear on the calendar.

---

## 5. CSS activity ↔ calendar

- **Activity → calendar: automatic.** The `activities` provider lists every non-archived event in
  range, so existing activities appear on day one. If an overlay entry exists (`event_id` set), its
  people, tags and kind are merged in. Title, dates, venue and modality always come from the event.
- **Calendar → activity: "Collect feedback (CSS)".** This button sits on `training`/`meeting`
  entries. It opens `/create` prefilled (title, dates, venue, modality, organizer =
  owner unit, speakers = attendees). Saving sets `calendar_entry.event_id`, so the entry becomes
  the overlay.
- **Duplicate guard, both directions.** The create form looks for a same-date entry with a
  similar title and offers "Link to the calendar entry". Promotion looks for a same-date event
  and offers "Link to the existing activity". Reuse the existing create-duplicate heuristics.
- **Editing a linked item from the calendar** writes the event's own fields through the existing
  activity edit path. If the activity has registrants, show the existing "notify N registrants"
  step (`activity_messages`).
- **CSS chips on the card** follow the lifecycle: *N registered* → *feedback open* → *score 4.6*.
  They link to Monitor and Results.
- **Nudge, once.** The day after a past `training` entry with no event, the creator is asked
  "Collect feedback?". These kinds are never nudged: `audit_mr`, `banner`, `deadline`,
  and internal meetings.

---

## 6. Birthdays

**Why it belongs here:** birthdays are a calendar layer, and remembering them is a reminder
problem. Celebrating monthly celebrants is a common office tradition, so the plan supports that
explicitly.

### Capture (privacy first)
- Store **month and day only, never the year.** Age isn't needed, and leaving it out means less
  personal data to hold. A birthday is personal data under RA 10173 (NPC Advisory Opinion 2017-63).
- **The person enters it themselves** on *My profile* and in the *Welcome* onboarding step. Admins
  can't see or edit it on the staff form, which keeps it from becoming an HR record.
- **Sharing is opt-in.** `birthday_share`: *Don't share* (default) / *My section* /
  *My division* / *Whole bureau*.
- **Consent is recorded.** Turning sharing on records `birthday_consent_at` and a snapshot of the
  notice shown. This copies the attendee-consent pattern already in the app.
- **Withdrawing is one click.** It clears the date, the sharing choice and the consent record.
- Archived (resigned or transferred) staff drop out automatically.
- Notice text, shown next to the field: *"Optional. Only the month and day are kept, never your
  year. We use it to greet you and remind your teammates. Choose who sees it; you can remove it
  any time."*

### Show
- The `birthdays` layer puts 🎂 *Name* on the day, inside the person's sharing scope intersected
  with the viewer's scope. Each birthday is a yearly item; in ICS it's `RRULE:FREQ=YEARLY`.
- **Feb 29** is shown on Feb 28 in non-leap years.
- **Weekend birthdays** also get a "this weekend" note on Friday.
- The home "This week" card has a line *"Celebrating this week: Riza (Wed), Tek (Sat)"*.
- **On the day:**
  - The celebrant's home greeting changes: "Happy birthday, <nickname>! 🎉".
  - Their avatar gets a party hat or cake badge on Team-view faces (the avatar system already
    has moods).
- **Monthly celebrants** page at `/calendar/birthdays?month=10`: a printable list, grouped by
  section, for the welfare or celebrations committee.

### Remind
| What | When | To | Channel |
|---|---|---|---|
| "Today is Mae's birthday" | the morning of | teammates inside Mae's sharing scope who haven't turned it off | bell (and home card) |
| "Birthdays this week" | Monday | everyone, scoped | one line in the existing Monday email; no extra email |
| "Tomorrow: Mae's birthday" | day before | *celebration coordinators* (accounts listed in an admin setting) | email |
| "October celebrants" | 1st working day of the month | coordinators | email with the list + printable link |
| The celebrant | never | — | no one gets a reminder about themselves |

All of these are toggles in `/me` and in Admin → Email, and they respect `birthday_share`.

*Later, optional:* a "Send a greeting" button that leaves a short message on the celebrant's home
card. It would reuse the comment storage patterns. It isn't scheduled; it's listed in §12.

---

## 7. Views

- **Page:** `/calendar`. The URL carries all state, e.g.
  `?scope=section&view=week&date=2026-10-12&layers=entries,activities,birthdays&tag=PK`.
- **Scope:**
  - `Me` · `My section` · `My division` · `Bureau`;
  - a person picker;
  - section chips (the colour legend, clickable);
  - kind, tag and status filters.
- **Default blend:** "mine + bureau-wide".
- **Layer toggles:** Activities · Meetings & trips · Holidays · Leave · Birthdays · Deadlines.

| Layout | For | Notes |
|---|---|---|
| **Agenda** | phones, "what's next" | grouped by day; today pinned; holidays inline |
| **Month** | the familiar Word view | up to 3 chips per day, then "+N more"; spanning bars for trips |
| **Week — people × days** | chiefs: "who is where" | avatar rows; trips as bars; leave hatched; whereabouts dot |
| **Timeline** | travel planning | 4–8 weeks of multi-day bars per person (later increment) |

- **Rendering:** server-side Jinja plus a little vanilla JS, matching the rest of the app. No
  calendar library at first.
- **Possible later library:** if drag-to-move or resize is wanted, evaluate *EventCalendar*
  (vkurko/calendar). It's MIT-licensed, has no dependencies, and includes resource/timeline views.
  FullCalendar's resource timeline is a paid premium plugin. TOAST UI Calendar is reported as no
  longer maintained.

---

## 8. Home page

Recommended toggle: **Team | Me | Calendar** (`/?view=calendar`).

- **Team** and **Me** each get a slim **"This week"** card with:
  - up to 5 items for that scope;
  - a "who's away" strip;
  - the birthdays line.
- **Calendar** tab: the agenda or week component with scope pills and quick-add. Its scope follows
  the tab you came from (Team → my section, Me → me).
- **To-do strip:** `_task_calendar` adds:
  - "2 things today";
  - "Confirm where you'll be for the Palawan trip";
  - "Collect feedback for Tuesday's orientation".

  Like the other sources, a failure is swallowed so it never breaks the strip.
- **Nav:** a **Calendar** entry. Global search learns the calendar keywords and can find entries
  by title or tag.

---

## 9. Notifications

### Delivery machinery
- `calendar_outbox` rows are written in the same transaction as the change. They're written for
  each affected attendee, never for the editor.
- `_scheduler_loop` already ticks every 60s. Each tick calls
  `office_calendar.flush_outbox(conn)`. It sends **one email per person** for rows at least
  **10 minutes old**, so a burst of edits becomes one message. It then marks them sent and logs to
  `email_log`.
- **Same-day urgency:** a change to an entry happening today or tomorrow skips the 10-minute wait.

### Email
| Job | When | To |
|---|---|---|
| Added / changed / cancelled | outbox flush | attendees |
| **Monday week-ahead** | extends the existing whereabouts Monday email (no second email) | everyone |
| Day-before reminder | daily sweep | attendees of tomorrow's entries (linked activities stay on the existing `--events` job, so no doubles) |
| Chief roll-up lines | existing Tuesday roll-up | chiefs |
| CSS follow-up nudge | daily sweep, once per entry | entry creator |
| Birthday jobs | §6 | coordinators / everyone |

Every invite and reminder email carries an `.ics` attachment with the same `uid` and current
`sequence`, so a calendar app updates the event instead of duplicating it.

### Bell (`_notification_items`)
- **"N new / changed calendar items for you".** Counts `calendar_entry_person` rows where the
  entry's `sequence > seen_seq`. Opening `/calendar?scope=me` marks them seen.
- **"Confirm where you'll be for <trip>"** — the mismatches from §4.
- **"🎂 Today: Mae's birthday"** — at most one row that lists the names, and it clears at midnight.
- **Not in the bell:** "you have a meeting today". That's information, so it lives on the home card.

### Personal feed
- A signed webcal URL per user, at `/calendar/feed/<token>.ics`: "mine" or "my section",
  optionally including birthdays.
- It contains `VTIMEZONE` Asia/Manila, stable `UID`s, `SEQUENCE` and `STATUS`.
- The page states plainly that Google updates subscribed calendars only about every 12–24 hours.
- Tokens can be revoked: a "reset link" button on `/me`.

### Preferences (`/me`)
- invites & changes;
- day-before;
- Monday summary;
- teammates' birthdays.

All default on. Admins have global switches in Admin → Email.

---

## 10. Visual design

- **Colour = owning unit; icon = kind; text is always present.**
  - Reuse the Word legend colours, mapped onto the existing `_unit_badges.html` tokens so dark
    mode and contrast keep working.
  - Never use colour as the only signal; the existing a11y tests apply.
- **Chip:** left colour bar · kind icon · one-line title · time · 2–3 stacked avatars.
  - Tentative chips are dashed; postponed or cancelled chips are struck through and dimmed.
  - Tapping a chip opens a side sheet, not a new page.
- **Multi-day items** are spanning bars. **Banners** ("MORATORIUM MR SIA") are a thin ribbon across
  the week. **Holidays** tint the day and show their name. **Today** is highlighted.
- **Birthdays** are a small 🎂 row at the top of the day, separate from work items so they never
  crowd the schedule.
- **Quick add:** click a day (drag across days later) → title, dates, people ("whole section"
  shortcut), kind, tags, "also collect CSS feedback". Everything else is optional.
- **Mobile:** Agenda only. Month collapses to a density strip. No horizontal page scroll.
- **Repo rules:** bump `app.css?v=` in `dash_layout.html` / `public_layout.html` whenever
  `app.css` changes. Put calendar styles in `static/css/calendar.css` so the bumps stay small.

---

## 11. Guardrails for "everyone can edit"

- **Audit:** every create, edit, cancel and restore writes a `calendar_entry_revision` diff plus an
  `audit_log` line. Each card shows "edited by Mae · 2h ago".
- **History:** the entry's History view lists revisions; **Restore** reverts to one.
- **Cancel:**
  - Cancel is a soft delete (status `cancelled`), restorable for 30 days.
  - Hard delete is admin-only.
- **Optimistic save:** the form posts the `sequence` it loaded. If the stored one is higher, show
  what changed instead of overwriting.
- **Accountability, not a gate:** edits to bureau-audience, `audit_mr` and `banner` entries also
  notify the owning unit's chief.
- **Privacy:**
  - Leave shows no reason.
  - Wellness never appears.
  - Birthdays appear only within the person's chosen sharing scope.
  - An entry marked `private` (later) shows as "Busy" to others.

---

## 12. Hooks for future iterations (designed in now, built later)

| Future feature | What already supports it |
|---|---|
| Recurring meetings (HSDD monthly, LES, quarterly MR) | `rrule`/`exdates` columns; `python-dateutil` is already installed via pandas; scheduled as H1 |
| Room / vehicle booking | a new `resources` provider plus a `calendar_entry_resource` table; same views |
| Travel orders / authority to travel, memos, minutes | add `calendar_entry_link(entry_id, kind, url)` (attachments by URL first) |
| WFP / OPCR targets and deliverables | `deadline` kind plus tags; a provider can read targets once they exist in the app |
| Post-activity outputs | linked CSS activity → `report_docs` reports already exist; link from the card |
| RSVP (going / maybe / not going) | add a `response` column to `calendar_entry_person`; maps to iCal `PARTSTAT` |
| Read API / integrations | `/api/calendar?from&to&scope` returns `CalItem` JSON (increment H3) |
| AI assistant ("What is Section 3 doing next week?") | `ai_core` grounded on `items_between`; same scope rules |
| Inbound calendars (DOH-wide, partner ICS) | a provider that reads a cached subscribed `.ics` |
| Two-way Google/Outlook sync | stable `uid` + `sequence` make CalDAV / Graph sync possible later; not planned now |
| Birthday greetings wall, work anniversaries | the same `birthdays` provider pattern (an anniversary is just another yearly item) |

---

## 13. Increments (each sized for one Sonnet session → one PR)

**Rules for every increment:**
- Touch about 5 files or fewer and stay under ~500 changed lines, tests included.
- Ship something usable, or a tested internal piece, with **no half-finished UI**.
- Bump `version.py` (`APP_VERSION` + the plain-language entry) and add a `CHANGELOG.md` entry.
- Run `./run_tests.sh`. Bump `app.css?v=` if CSS changed.
- Don't change behaviour outside the increment's scope.

**Prompt to paste into a Sonnet session:** *"Implement increment `<ID>` from
docs/OFFICE_CALENDAR_PLAN.md. Read §§1–3 and the increment. Follow its file list, done-when and
tests exactly; anything listed as out of scope stays out. Open a draft PR."*

### Milestone A — Foundation
| ID | Goal | Files | Done when | Tests |
|---|---|---|---|---|
| **A1** | Schema + storage CRUD | `storage.py` (tables in `init_db`, functions: `cal_create`, `cal_update` (bumps sequence on date/time/status), `cal_cancel`, `cal_restore`, `cal_get`, `cal_list_between`, people + tags setters, revision write), `tests/test_calendar_storage.py` | Functions work on a fresh DB and on an existing one (migration). No UI. | create/update/cancel/restore; sequence rules; revision rows; range overlap query (multi-day entries crossing the window) |
| **A2** | Layer registry + scope | new `office_calendar.py` (`CalItem`, `LAYERS`, `items_between`, providers `entries` + `holidays`), `tests/test_calendar_scope.py` | Returns merged, sorted items for a range | unlinked → bureau + own only; section member → section + bureau; division chief → division; Director → bureau; audience=people only visible to listed people |
| **A3** | Read-only `/calendar` Agenda view + nav entry | new `calendar_routes.py` (APIRouter, included from `app.py`), `templates/calendar.html`, `static/css/calendar.css`, nav/search entry in `app.py` | Signed-in users see the agenda for 2 weeks, with scope pills | route auth; scope pills change the result; holiday shown |
| **A4** | Add / edit / cancel / restore form | `calendar_routes.py`, `templates/calendar_entry_form.html`, `templates/calendar_entry.html` (detail + history) | Anyone can add/edit; stale-sequence save shows a conflict; History + Restore work; "edited by" shown | permission (any signed-in user); conflict path; restore; audit rows |
| **A5** | Month grid + filters | `calendar_routes.py`, `templates/calendar.html` (month partial), `calendar.css` | Month view with spanning bars, unit colours, legend chips, kind/tag/status filters in the URL | multi-day rendering across weeks; filter combos; "+N more" |

### Milestone B — Import the Word calendar
| ID | Goal | Files | Done when | Tests |
|---|---|---|---|---|
| **B1** | Pure .docx parser | new `calendar_import.py` (uses `python-docx`, already a dependency): month tables → day cells → lines with fill colour; merge consecutive identical lines into ranges; group typo variants; guess `kind`, `status` (Tentative/POSTPONED/Pending), times; extract parenthesised name tokens; drop inline holiday lines | `parse(path) -> [Draft]` deterministic | build a tiny .docx fixture inside the test; range merge; kind/status guesses; holiday drop |
| **B2** | Admin import screen (no people yet) | `calendar_routes.py`, `templates/calendar_import.html` | Upload → colour→unit mapping → preview table (approve/edit/skip) → import; idempotent via `import_key` | re-import creates no duplicates; mapping applied; skip respected |
| **B3** | People resolver | `calendar_import.py`, `templates/calendar_import.html` | Name tokens matched by nickname / first name / directory name; unmatched go to a "who is this?" list; resolved people written to `calendar_entry_person` | ambiguous names never auto-assigned; nickname match |

### Milestone C — Home page
| ID | Goal | Files | Done when | Tests |
|---|---|---|---|---|
| **C1** | "This week" card on Team & Me | `office_connect.py` (`calendar_week_block`), `templates/office_connect.html` | Card shows ≤5 items + who's-away for the tab's scope | scope parity with `team_view_data`; empty state |
| **C2** | Calendar tab + `_task_calendar` | `office_connect.py`, `templates/office_connect.html`, `app.py` (`view=calendar`) | `/?view=calendar` renders agenda/week; to-do shows today's count | tab switch; task tone order; failure isolation |
| **C3** | Week people × days view | `calendar_routes.py`, `templates/calendar.html` (week partial), `calendar.css` | Rows = people in scope; trips as bars; leave hatched; whereabouts dot | scope; leave privacy (no note) |

### Milestone D — Activities two-way
| ID | Goal | Files | Done when | Tests |
|---|---|---|---|---|
| **D1** | `activities` provider + overlay + CSS chips | `office_calendar.py`, chip partial | All non-archived events appear; overlay people/tags merged; chips by lifecycle | archived hidden; overlay merge; outside events included |
| **D2** | "Collect feedback" + duplicate guard | `calendar_routes.py`, `app.py` (`/create` prefill + link on save), `templates/form_create.html` | Promote prefills and links; create form offers to link a same-day similar entry | link both ways; no double item on the calendar after linking |
| **D3** | Editing linked items + CSS nudge | `calendar_routes.py`, `send_reminders.py` (job `calendar_css_nudge`) | Calendar edit of a linked item goes through the activity edit path (registrant notice); nudge once per past training | nudge once; excluded kinds; registrant guard |

### Milestone E — Whereabouts interplay
| ID | Goal | Files | Done when | Tests |
|---|---|---|---|---|
| **E1** | Travel default + `leave` layer | `storage.py` (`whereabouts_defaults` layer 3), `office_calendar.py` (leave provider) | Form and Monday email prefill Field + venue for listed travellers; leave shows as "On leave" | precedence table (§4) row by row; moved trip moves the default; confirmed rows untouched |
| **E2** | Suggest-to-calendar + mismatches | `office_calendar.py` (`mismatches`), `templates/whereabouts_week.html`, `office_connect.py` (task) | "Add this trip" offer; mismatch home task; chips | each mismatch case; note stays private until published |

### Milestone F — Birthdays
| ID | Goal | Files | Done when | Tests |
|---|---|---|---|---|
| **F1** | Capture with consent | `storage.py` (columns + `set_birthday`, `clear_birthday`), `app.py` (`/me` + welcome save), `templates/me.html`, `templates/welcome.html` | Month/day + sharing choice + notice; consent snapshot; withdraw clears all; not shown on staff form | no year stored; withdraw; validation (Feb 29 ok, Apr 31 rejected) |
| **F2** | `birthdays` layer + home line + greeting + celebrants page | new `birthdays.py` (pure helpers: occurrences in range, Feb-29 rule, scope filter), `office_calendar.py` (provider), `office_connect.py`, `templates/office_connect.html`, `templates/calendar_birthdays.html` | 🎂 on calendar; "Celebrating this week"; celebrant greeting; printable monthly list | share-scope × viewer-scope matrix; archived excluded; Feb 29; weekend note |
| **F3** | Birthday reminders | `send_reminders.py` (jobs `birthday_coordinators`, `birthday_month`), `app.py` (bell row + admin setting for coordinators), `templates/me.html` (pref) | Bell "Today: …"; Monday line; day-before + monthly emails to coordinators; prefs respected; never to the celebrant | dedupe via `email_log`; pref off; celebrant excluded |

### Milestone G — Notifications
| ID | Goal | Files | Done when | Tests |
|---|---|---|---|---|
| **G1** | Outbox + batched change emails | `storage.py` (`calendar_outbox`), `office_calendar.py` (`enqueue`, `flush_outbox`), `app.py` (one call in `_scheduler_loop`), `mailer.py` (message builder) | One email per person per burst; editor excluded; today/tomorrow skip the wait | debounce; editor excluded; prefs; no send when mail off |
| **G2** | Bell rows + seen tracking | `app.py` (`_notification_items`), `calendar_routes.py` (mark seen) | Counts match `/calendar?scope=me`; clear on view | count parity; sequence bump re-surfaces |
| **G3** | Monday + day-before + roll-up | `send_reminders.py`, `mailer.py` | Week-ahead inside the existing Monday email; day-before for entries (not linked activities); roll-up mismatch lines | no duplicate with `--events`; weekday gating |
| **G4** | ICS: per-entry download/attachment + personal feed | new `calendar_ics.py` (writer: line folding at 75 octets, escaping, VTIMEZONE Asia/Manila, UID/SEQUENCE/STATUS, yearly RRULE for birthdays), `calendar_routes.py`, `auth.py` (feed token), `templates/me.html` | `.ics` validates; feed URL works without login and is revocable | golden-file ICS; folding/escaping; token revoke; scope of feed |

### Milestone H — Recurrence and extras
| ID | Goal | Files | Done when | Tests |
|---|---|---|---|---|
| **H1** | Recurrence | `office_calendar.py` (expand with `dateutil.rrule`), form fields, `calendar_ics.py` (emit RRULE/EXDATE) | Weekly / monthly / nth-weekday; skip one date; edit "this one" vs "all" (this-one = EXDATE + detached entry) | expansion within window; exdate; holiday overlap shown |
| **H2** | Timeline view + quick-add sheet | `templates/calendar.html`, `static/js/calendar.js`, `calendar.css` | Multi-week bars per person; inline quick add | rendering smoke; quick-add posts to A4 route |
| **H3** | Read API + AI grounding | `calendar_routes.py` (`/api/calendar`), `ai_core.py` hook | JSON `CalItem`s, scope-enforced; assistant can answer "what's on next week" | scope; no leakage of private/leave notes |

**Suggested order:** A1 → A2 → A3 → A4 → A5 → B1 → B2 → B3 → C1 → **F1 → F2** → C2 → D1 → D2 →
E1 → G1 → G2 → F3 → C3 → E2 → G3 → D3 → G4 → H1 → H2 → H3.
- F1 can also ship first on its own if birthdays are wanted early: it depends only on the
  directory.
- Each milestone ends with something staff can use.

---

## 14. Test checklist (cross-cutting)

- **Scope:**
  - unlinked sees no section;
  - a section, division or bureau user sees exactly their scope;
  - a provider can't widen scope.
- **Precedence (§4):** holiday > own report > calendar default > filing.
- **Activities:** no double rendering once linked; edits through the event path only.
- **Birthdays:**
  - no year stored;
  - share scope respected in views, bell, email and feed;
  - withdraw purges;
  - the celebrant is never reminded.
- **Notifications:**
  - bell counts equal the destination page counts;
  - batching works;
  - no duplicate with existing jobs;
  - opt-outs are honoured.
- **ICS:** stable UID, increasing SEQUENCE, correct folding and escaping, Asia/Manila times.

## 15. Risks / open items

- **Colour → unit mapping** of the Word legend needs one human confirmation during import (B2).
- **Nickname ambiguity** (two "Mae"s): the resolver never auto-assigns an ambiguous name (B3).
- **Bell cost:** `_notification_items` runs on every request. Keep it to indexed single counts
  (`idx_cal_person_user`).
- **Email volume** is the real cost of open editing. The outbox debounce plus the merged Monday
  email is the mitigation; watch `email_log` after G1.
- **Celebration coordinators:** who they are is an office decision (an admin setting; empty
  until set).
- **Birthday sharing default** is *Don't share* (opt-in). Changing it to opt-out would need a legal
  basis and a notice review.
- **New convention:** `calendar_routes.py` introduces the first `APIRouter`. If that's unwelcome,
  routes can live in `app.py` instead, with the logic still in the modules.

## 16. Sources consulted

- RFC 5545 recommended practices — https://icalendar.org/iCalendar-RFC-5545/5-recommended-practices.html
- RFC 5545 UID property — https://icalendar.org/iCalendar-RFC-5545/3-8-4-7-unique-identifier.html
- RFC 7986 UID guidance (opaque random UUIDs) — https://icalendar.org/New-Properties-for-iCalendar-RFC-7986/5-3-uid-property.html
- RRULE / RDATE / EXDATE practice — https://itime.day/articles/rrule-rdate-exdate-guide
- Recurring-event overrides (EXDATE + override pattern) — https://v2-5-0.developer.nylas.com/docs/v2/calendar/recurring-events/
- dateutil rrule — https://dateutil.readthedocs.io/en/2.4.2/_modules/dateutil/rrule.html
- Subscribed-calendar refresh delays — https://usecarly.com/blog/google-calendar-ics-refresh-rate/ ,
  https://learn.microsoft.com/en-us/answers/questions/2152833/adjust-synchronized-time-for-added-calendar-on-owa ,
  https://nocal.app/help/ics-and-subscriptions/why-subscribed-calendars-dont-update-instantly
- "Subscribe in Google Calendar" link pattern — https://til.simonwillison.net/ics/google-calendar-ics-subscribe-link
- Team calendar / absence visibility practice — https://dockyard.com/blog/2019/07/19/team-ux-calendar-management ,
  https://help.reclaim.ai/en/articles/14462727-set-up-team-ooo-calendars ,
  https://ithub.mclennan.edu/books/draftworking-in-iss-standards-procedures-and-resources/page/calendars-and-availability
- Calendar UI libraries & licensing — https://www.pistack.xyz/posts/2026-08-25-calendar-ui-libraries-fullcalendar-react-big-calendar-toast-ui-comparison/ ,
  https://v7.fullcalendar.io/premium , https://cdn.jsdelivr.net/npm/@event-calendar/build@5.7.1/README.md
- Birthdays as personal data (NPC Advisory Opinion 2017-63) — https://digitalpolicyalert.org/event/22441-adopted-npc-advisory-opinion-no-2017-63-on-personal-and-sensitive-information
- Consent and lawful bases under RA 10173 — https://fpf.org/?p=167709 , https://accralaw.com/?p=16522
