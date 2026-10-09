# Conference Room Reservation — plan v2

**Status:** planned, not started.
**Scope:** the bureau's one conference room.

**Owner decisions so far:**
- Anyone signed in can request a slot. Anyone in the **Administrative Section** can approve it.
- An admin can **encode** a reservation they received some other way. An encoded reservation is
  approved immediately.
- An admin can **cancel** a reservation in favour of a more important one. The system suggests
  other slots to the person who was bumped.
- A requester can **withdraw** their own reservation.
- Approved reservations feed the Office Calendar.
- Reservations and CSS activities link both ways. A new activity, especially an online one, can
  be asked whether it wants the room.
- The request asks **"Will meals be requested?"** A yes produces a pre-filled meal form. The owner
  will supply the form layout later.
- A **permanent QR code and link** let external people request the room without an account. Their
  requests go through the same admin approval.
- There is **one room**, and **timeslots are fixed**.
- Notifications go out by bell and email.

v2 reviews v1 (the chat outline) for intuitiveness, layout on different screens, and friction.
§0 lists what changed. §12 splits the work into increments, each sized for one PR.

---

## 0. What changed from v1 (review findings)

| v1 said | Friction / problem | v2 does |
|---|---|---|
| A form: pick a date, pick a slot, submit | The requester finds a clash only after submitting. It takes three steps before they see anything useful. | **Availability board first** (§3.1). The week is laid out as a grid of fixed slots, and the requester clicks a free cell. The form opens pre-filled beside the grid. Clashes are visible before typing. |
| A unique index on (date, slot) for "active" statuses | If pending counts as active, the second requester is hard-blocked. Admins then never see competing requests, and "more important" can't be weighed. | **Many pending requests, one approved.** The uniqueness rule applies only to *approved* slots. Requesters see "1 other request pending for this slot". Approving one asks what to do with the others (§4.3). |
| Admin cancels, then encodes the more important booking | Two separate steps, with a window where someone else can grab the slot. The bumped person may also hear about it before a reason exists. | **"Book anyway"**, one atomic action that starts from the new booking (§4.4). The admin picks a taken slot and sees who will be bumped. They enter a reason, and the system saves both changes in one transaction. Bump notices go out with alternatives. |
| Suggested slots with an "accept" link | The suggested slot can be taken before the person clicks. | The accept link **re-checks availability**. If the slot is still free, it books it **already approved**, because the admin caused the bump. If not, it shows fresh suggestions. Nothing is held, so nothing goes stale. |
| "All admin-section users approve" | Several approvers means each assumes someone else will act, plus N emails per request and two people approving at once. | **First to act wins.** The decision is idempotent, and later clickers see "Approved by Ana at 9:14". The Administrative Section gets one email per request (or a digest). A request still pending after a set time escalates to the Admin Head (§6). |
| A modal on `/create` after the activity is saved | The prompt comes after the form is done, and it's easy to dismiss. Online activities rarely think "room". | An **inline availability chip inside the activity form**, next to Date/Modality (§7.1): "Conference room: AM free · PM booked [☐ Also reserve]". It is pre-ticked for online and hybrid activities. |
| Rescheduling an activity re-requests the room | The approved slot is dropped before the new one is approved, so the activity can end up with no room. | **Move request** (§7.3). The old booking stays until the move is approved. A free target slot gets a one-click admin approval. |
| External form: name, organization, contact | Spam risk. The external requester also has no way to see status or withdraw. | The public form gives a **reference code plus a signed "track your request" link** by email (§5). An email address that hasn't been confirmed shows as a badge to admins, but doesn't block. The page carries a Data Privacy Act consent line and a retention rule. |
| Meal form generated from the request | The form layout is unknown, and it can't be generated before approval. Changes after generation are also not handled. | The meal *details* are captured now: headcount, which meals by slot, and dietary notes. The **form is generated on approval** and **regenerated with a version number** when the details change. A cutoff warns about late meal requests (§8). |
| One layout | The plan never said how it looks on a phone (where the QR lands), a laptop, or a wide monitor. | A per-breakpoint layout using the app's existing breakpoints (§10), plus a **door/TV display mode** and a **printable A4 QR poster**. |
| Not mentioned | Weekends, holidays, maintenance, room capacity, recurring meetings, lead time, and requests whose date has passed | Guardrails (§9). |

---

## 1. Principles

1. **See before you ask.** Every entry point shows availability before collecting details.
2. **One form, many doors.** The room page, the calendar, the activity form, and the public QR page
   all reuse the same request component and the same `rooms.request()` service function. The
   rules live in one place.
3. **Plain status words.** Use Requested, Approved, Declined, Moved, Withdrawn, Cancelled, and
   Expired. Pair every status with an icon and text, never colour alone. The app also has a
   contrast theme.
4. **First to act wins, everyone sees who acted.** Every decision shows who made it and when, in
   the UI and in the audit log.
5. **Never leave someone roomless without an alternative.** Every bump, decline, or failed move
   comes with suggested slots.
6. **Keep `app.py` thin.** New code goes in `rooms.py` (services), `rooms_routes.py` (an
   `APIRouter` included with one line, like `calendar_routes.py`), `room_meal_form.py` (the PDF),
   and templates under `templates/rooms/`.
7. **Reuse the machinery.**
   - The `/approvals` inbox and `_approvals.html`
   - `_notification_items` (the bell)
   - The `mailer.py` builders and `email_log`
   - Signed links on the `auth.make_wellness_decide_token` pattern
   - `ratelimit.allow`
   - `_qr_data_uri`
   - The `office_calendar.LAYERS` registry
   - `app._scheduler_loop`
   - The `wellness_register` PDF pattern
   - `retention.py`
   - `audit_log`

---

## 2. Data model (auto-migrated in `storage.init_db`, additive)

```sql
room_slot            -- the fixed timeslots; editable in settings
  id, code ('AM','PM',…), label, start_time, end_time, sort, active

room_reservation     -- one request
  id, ref_code (e.g. 'CR-2610-0042', shown to people),
  requester_user_id NULL,                   -- internal requester
  ext_name, ext_org, ext_email, ext_phone,  -- external requester (NULL for internal)
  ext_email_verified_at NULL,
  on_behalf_of TEXT NULL,                   -- when an admin encodes for someone
  title, purpose, attendees INT, modality ('f2f','online','hybrid'),
  status ('requested','approved','declined','withdrawn','cancelled','expired'),
  source ('internal','external','encoded','move','bump_accept'),
  decided_by, decided_at, decide_note,
  bumped_by_reservation_id NULL,            -- set on a booking cancelled in favour of another
  moves_reservation_id NULL,                -- set on a move request; the old booking stays until approved
  event_id NULL, calendar_entry_id NULL,    -- links to a CSS activity / calendar entry
  meals_requested INT DEFAULT 0,
  created_at, updated_at, created_by

room_reservation_slot  -- the slots a request covers (a request can take several consecutive slots)
  reservation_id, date, slot_id, is_approved INT  -- copied from the parent; written only by rooms.py

CREATE UNIQUE INDEX ux_room_slot_taken ON room_reservation_slot(date, slot_id) WHERE is_approved = 1;

room_meal            -- meal details (§8)
  reservation_id, headcount, am_snack, lunch, pm_snack, dietary_notes, form_version, form_generated_at

room_block           -- maintenance, a holiday override, or an admin hold
  date, slot_id NULL (whole day), reason, created_by
```

- The partial unique index makes the "one room" rule a database guarantee. Two admins approving
  different requests for the same slot at the same moment cannot both succeed. The second one gets
  a friendly "Already approved for Ana's request" message.
- `is_approved` is copied onto the slot rows in the same transaction as each status change. It
  lives in `rooms.py` only, so no trigger is needed.
- `ref_code` is the thing people say on the phone ("CR-2610-0042"). Internal ids never appear in
  the UI.
- **Room hours are 07:00–19:00 (decided).** Timeslots are fixed one-hour blocks inside those hours
  (12 blocks a day; **open item O1** asks whether the owner prefers larger blocks). A request
  covers one or more *consecutive* blocks on one day, picked by clicking or dragging a range. Quick
  picks "Morning", "Afternoon", and "Whole day" select common ranges. Multi-day use is entered as
  one request per day, through a "repeat" helper (§9). Because slots are rows in `room_slot`,
  changing the block size later needs no code change.
- On the board (§3.1) the grid therefore becomes a **time grid** (hours down the side, days across)
  on wide screens, and a day agenda of hour blocks on phones.

---

## 3. Requester experience (internal)

### 3.1 Availability board — `/rooms`

The single landing page, reached from the nav item **"Conference Room"** in the group that already
holds Calendar.

```
 Conference Room                         [◀ This week ▶]  [Today]    [+ Request]
 ┌────────────┬───────────────┬───────────────┐
 │            │ AM 8–12       │ PM 1–5        │
 ├────────────┼───────────────┼───────────────┤
 │ Mon 12 Oct │ ✓ Free        │ ● Approved    │   ← approved shows the title to staff
 │ Tue 13 Oct │ ◐ 1 requested │ ✓ Free        │   ← a pending request is still requestable
 │ Wed 14 Oct │ ★ Yours       │ ★ Yours       │
 │ Thu 15 Oct │ ⛔ Holiday     │ ⛔ Holiday     │
 │ Fri 16 Oct │ ✓ Free        │ ✕ Maintenance │
 └────────────┴───────────────┴───────────────┘
 My reservations (2 upcoming) ▸
```

**Interactions**
- Clicking a free or "requested" cell opens the request panel with the date and slot filled in.
- Shift-click, or click-and-drag across a row, selects consecutive slots. A "Whole day" link sits
  on each row.
- Clicking an approved cell shows details: the title, the requesting unit, and the linked activity.
  External requesters' contact details are visible to admins only.

**Request panel fields**
- Title.
- Purpose.
- Attendees, with a capacity warning above `room.capacity`.
- Modality.
- "Will meals be requested?" A yes reveals the §8 fields inline.
- An optional "Link to an existing CSS activity" picker.
- Name, unit, and contact are taken from the directory, not typed.

**Buttons and status**
- One primary button: **Request room**.
- After submitting, the cell turns ★ "Yours · Requested", with a toast giving the ref code.

**Clash notices**
- If the slot already has requests, a soft notice appears: "1 other request is pending for this
  slot. The Administrative Section will decide." This is not an error.

### 3.2 My reservations

A list on `/rooms/mine`, also a tab on the board.

- Each row shows a status chip and a short timeline: "Requested Oct 9 → Approved Oct 9 by Ana".
- Available actions:
  - **Withdraw**, with a confirmation and an optional reason.
  - **Change**, which only creates a *move request* (§7.3).
  - **Create CSS activity** (§7.2).
  - **Download meal form** (§8).
- Withdrawing an approved booking less than 24 h before it starts also alerts the Administrative
  Section, because meals and setup may already be arranged.

### 3.3 Other doors (all open the same panel)

- **Office Calendar.** Clicking a slot in the "Rooms" layer, or the "Reserve room" quick action.
- **The activity form.** The inline chip (§7.1).
- **The home page.** A "Book the conference room" tile. A home to-do appears through
  `office_connect.home_tasks` when the user has a decision or a bump to act on.

---

## 4. Administrative Section experience

### 4.1 Who counts as an approver

- `rooms.is_room_admin(user)` is true for:
  - accounts whose directory `org_path` ends in `/ADMIN` (the Administrative Section);
  - the section's OIC (`section_oic`);
  - `admin`-role accounts as a fallback.
- An optional app setting lists extra approver accounts, for people outside the section.

### 4.2 Requests queue

- A third queue, **Conference Room**, on `/approvals`, next to the wellness and AWA queues. A
  "Requests" tab on `/rooms` shows the same queue.
- Each card shows:
  - the date, slots, title, requester and unit (or an "External" badge with the organization);
  - attendees and whether meals are requested;
  - the competing requests for the same slots, side by side, so the admin compares them in one
    place.
- Actions:
  - **Approve**;
  - **Decline**, with a reason required;
  - **Approve another slot**, which opens the suggestions.
- Approving is disabled, with the reason shown, when the slot is already approved for something
  else. "Book anyway" (§4.4) is offered instead.
- An email one-click link opens a confirmation page, never a bare GET that changes state. That page
  re-checks for clashes.

### 4.3 Approving when others are competing

When an approved request covers slots that other requests are also waiting on, a dialog asks:

> "2 other requests want Tue 13 AM. **Decline them and suggest alternatives** (recommended) /
> keep them pending."

The default declines them, with an auto-written reason and suggested slots.

### 4.4 Encode and "Book anyway"

- **Encode** is the same panel as a normal request, with an **"On behalf of"** field. The field
  takes a directory person, or free text for an external requester. Saving sets the status to
  approved and the source to `encoded`.
- Selecting a slot that is already approved shows a **Book anyway** variant:
  - It names the booking that will be bumped, for example "Section 3 Planning (Juan, approved
    Oct 2)".
  - It requires a reason.
  - It previews the alternatives the bumped person will be offered.
- One transaction saves the new booking as approved, cancels the old one with
  `bumped_by_reservation_id` set, and queues the bump notice. Nothing can slip in between.
- Admins can also **block** slots for maintenance or holidays. A block shows as ✕ on the board.
  Blocking a booked slot runs the same bump flow.

### 4.5 Suggestions

`rooms.suggest(date, slots, n=3)` searches in this order:

1. the same slots on the next working days;
2. the same day in other slots;
3. the previous working days, if they are still in the future.

Holidays, weekends, and blocks are skipped. Suggestions appear as one-click buttons in the email,
the bell, and the "My reservations" row.

---

## 5. External requests (permanent QR / link)

- **Permanent URL:** `/room`. It is short, easy to type off a poster, and added to
  `_PUBLIC_EXACT`. The QR encodes `CSS_BASE_URL + "/room"`, so it survives redeploys. It **must
  never change**.
- **Poster:** `/rooms/poster` is admin-only. It produces a printable A4 page with the QR, the short
  URL, the room name, and "Scan to request the conference room".
- **Page layout:** the page uses `public_layout.html` and `.pub-card`, and is designed for a phone
  first, because the QR lands on a phone.
- **Steps:**
  1. **Pick a slot.** A read-only free/busy day list for the next 30 days. It shows titles of
     nothing, to protect privacy.
  2. **Details.**
     - Name, organization, email, phone.
     - Title, purpose, attendees, and meals.
     - A Data Privacy Act consent checkbox.
     - A hidden honeypot field.
  3. **Done.** The page shows the reference code and says "We emailed you a link to track or
     withdraw this request."
- **Tracking link:** a signed token link (`auth.make_room_track_token`, the same HMAC pattern as
  whereabouts) to `/room/t/<token>`. It shows the status and offers Withdraw. On a bump or decline,
  it offers suggested slots to accept.
- **Email verification is soft.** The first time the tracking link is opened, the email counts as
  verified. Admins see an "email not yet confirmed" badge, but approval is not blocked. Blocking
  would turn away legitimate guests who only gave a phone number.
- **Abuse limits:**
  - a new `ratelimit` bucket `room` (5 submissions per hour per IP);
  - at most 3 open requests per email address;
  - the honeypot, which silently drops bot submissions.
- **Retention:** external contact fields are blanked 12 months after the reservation date by a new
  `retention.purge_room_external()` step. The reservation itself is kept for the record.

---

## 6. Notifications

| Event | Who | Bell | Email |
|---|---|---|---|
| New request | Administrative Section | ✓ (count) | one email to the section, or digest mode in `admin_email` |
| Pending 24 h with no decision, or the slot is under 48 h away | Admin Head | ✓ | ✓ escalation |
| Approved / declined | Requester (internal or external) | ✓ | ✓ with the ref code and a calendar `.ics` |
| Bumped | Requester | ✓ | ✓ with the reason and the suggestions as buttons |
| Withdrawn under 24 h before start | Administrative Section | ✓ | ✓ |
| Move requested / approved | Admin / requester | ✓ | ✓ |
| Tomorrow's room schedule | Administrative Section | — | daily at 16:00, through `send_reminders` (setup and meals checklist) |
| Day-before reminder | Requester | — | ✓ |
| Meal form generated / updated | Administrative Section | ✓ | ✓ with the PDF attached |

- The bell rows come from `_notification_items`. A `room_seen_at` column on `admin_user` clears
  them.
- Each email is idempotent per (reservation, event, version) through `email_log`. A retry never
  sends the same notice twice.

---

## 7. CSS activity ↔ reservation

### 7.1 From the activity form (`form_create.html`)

- Once a **date** is set, an inline chip under Venue shows availability for that date, fetched from
  `/rooms/api/day?date=…`:
  `Conference room: AM ✓ free · PM ● booked   [☐ Also reserve the conference room]`
- **When the checkbox is pre-ticked:**
  - when modality is **online** or **hybrid** (the room hosts the online session);
  - when the venue text contains "conference room".
- **When ticked:**
  - Slot selection appears inline.
  - A meals question appears.
  - Saving the activity also submits a room request linked by `event_id`. It uses the
    `calendar_routes.link_after_create` pattern, which never fails the activity save.
- **Online activities:** with the room reserved, the venue label becomes "Conference Room (host) +
  platform link". The attendee page then tells people where the host is.

### 7.2 From a reservation

- An approved reservation shows **Create CSS activity**. It opens `/create?from_room=<id>`, with
  the title, date, modality, and venue "Conference Room" filled in. This mirrors the
  `?from_entry=` precedent.
- On save, `event_id` is written back to the reservation.

### 7.3 When things change

- **The activity's date changes and it has an approved room.**
  - A banner on the activity says "Your room booking is still for Oct 13 AM.
    **Request move to Oct 20 AM**".
  - The move is a new request (`moves_reservation_id` set).
  - The old booking stays until the move is approved. Approving the move releases the old slot in
    the same transaction.
  - If the target slot is free, the admin sees a one-click "Approve move".
- **The activity is cancelled or archived.** The requester is prompted to withdraw the room. The
  booking is not withdrawn silently.
- **The room is cancelled or bumped.** The activity shows a "No room — pick an alternative" banner
  with the suggestions. The activity itself is not touched.

---

## 8. Meals

- **Meals are derived from the meeting schedule (decided).** When "Will meals be requested?" is yes,
  the system works out which meals apply from the reserved hours, with no ticking needed:

  | Meal | Included when the booking covers |
  |---|---|
  | AM snack | 10:00 (the 10:00–11:00 block) |
  | Lunch | 12:00 (the 12:00–13:00 block) |
  | PM snack | 15:00 (the 15:00–16:00 block) |

  These trigger hours are settings, so they can be changed without code. The requester sees the
  derived list ("AM snack · Lunch · PM snack") with a one-click way to untick any item.
- **Also captured:** headcount, defaulting to attendees, and dietary notes.
- **Generated:** on approval, `room_meal_form.render_pdf(data)` creates the form, following the
  `wellness_register` module pattern. It is stored as `form_version = 1` and emailed to the
  Administrative Section with the PDF attached. The requester can download it from "My
  reservations".
- **Changes:** editing meal details on an approved booking regenerates the form as version N+1,
  marked "Revised". The section is notified.
- **Cutoff:** the 2-working-day lead time (§9) already covers meals, so no separate meal cutoff is
  needed. Meals added or changed on an approved booking less than 2 working days before the date
  show an amber warning to both sides.
- **Layout:** placeholder until the owner sends the official form (**open item O3**). The data
  fields above are designed so the official layout only changes the renderer.

---

## 9. Guardrails and edge cases

| Case | Rule |
|---|---|
| Weekends and holidays | Shown as ⛔. Requesters can't select them. Admins can override with a reason (from the `holiday` table). |
| Lead time | **A request must be made at least 2 working days before the date (decided), for internal and external requesters alike.** Earlier dates show as unavailable on the board. Admins can encode inside the window with a reason, for urgent cases. Booking horizon: up to 90 days ahead (internal) and 60 days ahead (external), unless the owner says otherwise. |
| Pending past its date | Becomes `expired` (scheduler, nightly). The requester gets a short notice. |
| Capacity | `room.capacity` is a setting. Going over it is a warning, not a block. |
| Recurring meetings | "Repeat weekly until …" in the panel creates N linked requests. The admin can **Approve all** or approve one at a time. Clashing dates are listed before submitting. |
| Two admins act at once | The partial unique index plus an idempotent decide. The loser sees who won. |
| Editing an approved booking | Only through a move request (slots) or a meals edit. Title and purpose edits don't need re-approval. |
| Audit | Every create, decide, bump, withdraw, move, and block is written to `audit_log` with the old and new status. |
| Time zone | All times are office-local through `tzutil`. |

---

## 10. Layout across screens

The plan follows the app's existing breakpoints (`static/css/app.css`):
- 480 / 640 px: phones;
- 780 px: the nav collapses to the hamburger menu;
- 1180 / 1200 px: laptops vs desktops;
- `body[data-width]`;
- the `--dsf` density scale;
- the light, dark, and contrast themes.

| Width | Board (`/rooms`) | Request panel | Queue (`/approvals`) |
|---|---|---|---|
| **≥ 1200 px** (desktop, 1080p and wider) | A full week grid (Mon–Fri, with an optional Sat/Sun toggle). Above 1600 px, a two-week grid. Uses `data-width="full"`. | A **side panel** on the right (about 380 px). The grid stays visible, so you can pick another slot without closing anything. | Cards in two columns. Competing requests side by side. |
| **781–1199 px** (laptops, 1366×768, small external monitors) | A week grid. Slot labels shorten to "AM" and "PM". | A **drawer** that overlays the right side, at most 420 px wide. Its action bar is sticky. The existing `max-height:700px` rule keeps actions reachable on short screens. | One column. `resp-table-wide` stacks the action buttons. |
| **≤ 780 px** (tablets, phones) | Switches to a **day agenda**. A swipeable date strip at the top shows 7 day chips with free-slot dots. Each slot is a full-width card at least 48 px tall. | A **full-screen sheet** with a sticky bottom action bar. Inputs are at least 16 px to stop iOS from zooming. | Stacked cards (`resp-table`). Approve and Decline are full-width buttons. |
| **≤ 480 px** | Same as above. The date strip scrolls horizontally *inside itself only*, so the page never scrolls sideways. | Fields are one per row. Meal checkboxes become toggle chips. | Same as above. |

**Other display needs**
- **Door / TV display:** `/rooms/display` is signed-in or token-gated, read-only, and refreshes
  every 60 s. It shows "Now", "Next", and the rest of today's schedule in large type, with the
  request QR in the corner. It suits a TV outside the room or a tablet by the door, and is laid out
  for 1920×1080 and for portrait tablets.
- **Print:**
  - The board prints as a one-page weekly schedule. The existing `@media print` rules already hide
    the nav.
  - The A4 QR poster.
  - The meal form PDF.

**Accessibility**
- Each grid cell is a button with an `aria-label` such as "Tuesday 13 October, AM, available".
- Arrow keys move between cells, and Enter opens the panel.
- Status is never shown by colour alone: icon plus word in all three themes.

---

## 11. Friction review of the remaining design

| Friction | Severity | Mitigation in this plan |
|---|---|---|
| Approval sits with "everyone", so nobody acts | High | First-to-act, a count on the bell, escalation to the Admin Head (§6) |
| A requester doesn't know if a pending clash means "no" | Medium | A soft notice plus a live status and timeline. Losing requests are declined with suggestions, not left hanging (§4.3) |
| A bumped person feels ambushed | High | A required reason, alternatives in the same message, and one-click accept that auto-approves (§4.4) |
| External guests don't get their tracking email (spam folder) | Medium | The ref code is shown on screen and can be printed. Guests can phone the section with the ref, and the admin finds it by ref in the queue search |
| The activity form gets longer | Medium | The room chip stays one line until ticked. It is hidden when no date is set |
| Approvers get too many emails | Medium | Digest mode in `admin_email`. The bell is the primary channel |
| The meal form layout is unknown | Low | Fields are captured now. Only the renderer changes later |
| Timeslots aren't confirmed | Low | Slots are data (`room_slot`), not code. Changing them needs no deploy |

---

## 12. Increments (each one PR)

| # | Increment | Files | Done when / tests |
|---|---|---|---|
| R1 | Schema + slots + service core | `storage.py` (init_db), `rooms.py` | Tables created idempotently. `request`, `approve`, `decline`, `withdraw` work. Two approvals of one slot → exactly one wins. `tests/test_rooms_core.py` |
| R2 | Availability board + request panel + My reservations | `rooms_routes.py`, `templates/rooms/*`, `static/css/rooms.css`, `static/js/rooms.js` | Works at 375 / 1024 / 1440 / 1920 px (Playwright screenshots). Keyboard navigation through the grid. `test_rooms_pages.py` |
| R3 | Approver resolution + queue in `/approvals` + decide links | `rooms.py`, `_approvals.html`, `auth.py` | A member of the Administrative Section sees the queue and others don't. A decide link re-checks clashes. `test_rooms_approval.py` |
| R4 | Encode, Book anyway, blocks, suggestions, competing-request dialog | `rooms.py`, templates | The bump is atomic. Suggestions skip holidays and blocks. `test_rooms_bump.py` |
| R5 | Notifications: bell, mailer builders, escalation, reminders, schedule digest | `mailer.py`, `app.py` (bell row), `send_reminders.py` | Each notice is sent once (`email_log`). `mailer.preview` covers each one. `test_rooms_notify.py` |
| R6 | Public `/room`, tracking link, poster, rate limit, retention | `rooms_routes.py`, `app.py` (`_PUBLIC_EXACT` + prefix), `ratelimit.py`, `retention.py` | The honeypot drops bots. The 6th submission in an hour gets a 429. Track and withdraw work without login. `test_rooms_public.py` |
| R7 | Calendar layer "rooms" + ICS | `office_calendar.py`, `calendar_ics.py`, calendar templates | Approved bookings appear. Pending ones appear only to the requester and admins (**O2**). `test_calendar_rooms.py` |
| R8 | Activity ↔ room (inline chip, from_room prefill, move requests, banners) | `form_create.html`, `app.py` create handler, `rooms.py` | Saving an activity never fails because of a room problem. A move keeps the old slot until it is approved. `test_rooms_activity.py` |
| R9 | Meals: derived from hours, PDF, versioning (**notify the owner first; the official form layout is needed**) | `room_meal_form.py`, routes | The PDF renders. Editing meals → v2 plus a notice. `test_rooms_meals.py` |
| R10 | Door/TV display + recurring requests + polish | templates, `rooms.py` | The display refreshes. Repeat-weekly creates N linked requests. `version.py` and `CHANGELOG.md` entries |

R1 → R2 → R3 is the minimum useful release, internal-only. R6 (external) can ship as soon as R3
is done.

---

## 13. Open items for the owner

**Decided**
- Room hours are 07:00–19:00.
- Pending requests show on the Office Calendar only to the requester and admins.
- The lead time is 2 working days.
- Meals are derived automatically from the meeting hours (AM snack, lunch, PM snack).
- Only Administrative Section members approve. No extra approvers from outside the section.

**Still open**
- **O1.** Are one-hour blocks (07:00–19:00) right, or would you prefer larger fixed blocks (for
  example 07–12, 12–15, 15–19)? What is the room capacity?
- **O3.** The official meal request form layout. The owner will send it when we reach increment R9,
  and the session will notify them then.
- **O5.** Door/TV display (R10): a read-only screen for a TV or tablet by the room door showing what
  is on now, what is next, and today's schedule, with the request QR in the corner. It is optional
  and built last. Keep or drop?
