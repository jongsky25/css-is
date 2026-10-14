# Travel Filing — plan v1

Build handoff: the owner's Draft 7 specification (verification page https://claude.ai/artifact/8D5ehqQrYQCBvUWvQstw2H). This file mirrors the headings of `docs/ROOM_RESERVATION_PLAN.md` and records what was built and what was decided on the way.

## 0. What changed from the first plan
Audit findings that shaped the build: no CSRF protection (so every travel POST checks Origin/Referer), `/travel*` has no middleware gate (every handler checks ownership), a filing snapshots its activity, no working-day counter existed beyond `rooms.add_working_days`, no rates were supplied (amounts are typed in), the relay gets HMAC and an allow-list, and new email jobs must be registered in four places.

## 1. Principles
Contents of generated forms are never saved. Only checklist drivers, links, flags, dates and status are. Rules are pure and live in `travel_rules.py`; routes only call them. The Google relay sits behind an interface that tests fake. Accounting has no role in the platform; the Admin Unit verifies flags.

## 2. Data model
Six additive tables (`travel_filing`, `travel_item`, `travel_flag`, `travel_route_type`, `travel_ceiling`, `travel_justification`) and `admin_user.employee_no`. Seeds are written once, keyed `travel.seeded` in `app_setting`, so administrator edits are never put back. Settings keys are under `travel.*`.

## 3. Requester experience (internal)
Built in T2: `/travel`, `/travel/new`, `/travel/f/{ref}`, ready page.

## 4. Admin Unit experience
Built in T6/T7: verify queue, ceilings and routes, justification library.

## 5. External requests
None. Travel filing is staff only.

## 6. Notifications
Built in T3: reminder job `travel_filing_due`, bell rows.

## 7. CSS activity ↔ filing
Built in T2: calendar chips, buttons on activity pages. A filing stores `entry_id` or `event_id` plus a snapshot.

## 8. Documents
Built in T4/T5: relay and payload builders.

## 9. Guardrails and edge cases
One live cash advance per user and activity (partial unique index). Withdrawn filings free the slot. Reimbursement is hidden when a live cash advance exists.

## 10. Layout across screens
Readable at 400px; English text hard-coded.

## 11. Friction review of the remaining design
Open: every unlisted route flags until the Admin Unit adds approved routes.

## 12. Increments (each one PR)
T1 Foundations, T2 Filing shell, T3 Reminders and bell, T4 Relay, T5 Prepare and generate, T6 Flags, T7 Library and admin screens.

## 13. Open items
- **Assumption 5** (owner to confirm at T2 review): a cash advance on a current or future activity has no deadline; liquidation and reimbursement are due 5 calendar days after the last day, rolled to a working day; an activity already over when the filing is opened gives every kind 5 working days from the day opened.
- **Approved routes**: a route type counts as approved only when it has an active `travel_route_type` row and an `rer` ceiling (`travel.ceilings` drops inactive ones). Adding a route in T7 must create its RER ceiling.
- **Ride documents** (`cenrr`, `rer`) are not known when the filing opens. The checklist adds them from the derived answers `rides_cenrr` / `rides_rer`, set when the itinerary is prepared (T5/T6).
- **Open flags are part of `completeness()`** so the missing list shows them; "ready" is refused while any remains.
- **A fare of exactly 1,000.01 unreceipted** raises both `over_ceiling` (when above the route cap) and `no_receipt_over_1000`.
- **`peso_words(1)`** returns "One Peso" (singular); the spec gave no vector.
- **Starter MC 114 wording** is generic text with the tokens `{{traveler_name}}`, `{{activity_title}}`, `{{dates}}`, `{{venue}}`. The owner's sample justification is a real person's document and was not copied; template administrators replace the starter rows in the library (T7).
- **Back-to-office report**: when `cert_of_appearance_available` is false the checklist asks for `bto_report` instead of `cert_appearance`.
- **Per diem and transport allowance rules**: manual entry until supplied.
- **Wording** of the Job Order certification and the meals/lodging and extra-expense certifications needs the owner's approval against the official issuance.
- **2027 holidays** must be loaded before 2027 deadlines are trustworthy.
- **Local test setup**: the HTTP tests need a `css_is.db` (gitignored). `python setup_db.py` creates one; four tests (`test_ai_report_draft`, `test_routes[/work-arrangement/approvals]`, `test_search::test_api_search_activities`, `test_wellness::test_chief_pages_are_gated`) fail on that sample database and also fail on `main`.
