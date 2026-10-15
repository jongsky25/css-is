# Travel Filing — plan v1

Build handoff: the owner's Draft 7 specification (verification page https://claude.ai/artifact/8D5ehqQrYQCBvUWvQstw2H). This file mirrors the headings of `docs/ROOM_RESERVATION_PLAN.md` and records what was built and what was decided on the way.

## 0. What changed from the first plan
Audit findings that shaped the build: no CSRF protection (so every travel POST checks Origin/Referer), `/travel*` has no middleware gate (every handler checks ownership), a filing snapshots its activity, no working-day counter existed beyond `rooms.add_working_days`, no rates were supplied (amounts are typed in), the relay gets HMAC and an allow-list, and new email jobs must be registered in four places.

## 1. Principles
Contents of generated forms are never saved. Only checklist drivers, links, flags, dates and status are. Rules are pure and live in `travel_rules.py`; routes only call them. The Google relay sits behind an interface that tests fake. Accounting has no role in the platform; the Admin Unit verifies flags.

## 2. Data model
Six additive tables (`travel_filing`, `travel_item`, `travel_flag`, `travel_route_type`, `travel_ceiling`, `travel_justification`) and `admin_user.employee_no`. Seeds are written once, keyed `travel.seeded` in `app_setting`, so administrator edits are never put back. Settings keys are under `travel.*`.

## 3. Requester experience (internal)
Built in T2: `/travel` (my filings, activities that may need a claim, unliquidated warnings), `/travel/new` (activity, kind, role, trip questions, papers), `/travel/f/{ref}` (checklist with Drive links, N/A, FMIS references, changing answers), `/travel/f/{ref}/ready` (print list, Mark ready, Mark submitted). Withdrawn and submitted filings are read-only.

## 4. Admin Unit experience
Built in T6: the verify queue at `/travel/verify` (Administrative Section members only; the app admin role is no bypass). It lists open flags with the person and filing, and records Verified or Reject with a note; a participant-only flag also needs the supervisor's confirmation. Built in T7: `/travel/admin` (ceilings and approved routes; a new route is created together with its RER ceiling) for Administrative Section members, and `/travel/library` (the MC 114 texts) which template administrators edit and other members read. Both show a notice when next year's holidays are not loaded.

## 5. External requests
None. Travel filing is staff only.

## 6. Notifications
Built in T3. Reminder job `travel_filing_due` (`send_reminders.send_travel_filing_due`, registered in `_ALL_JOBS`, `JOB_FEATURE`, `mailer.FEATURES` and `mailer._PREVIEWS`; timing knob `travel_filing_lead_days`, default 2): one email a day per person listing open or ready filings due within the lead days or overdue, plus submitted cash advances whose activity is over with no liquidation. Withdrawn and submitted filings are never mentioned. It goes to the directory email, else the login, and does nothing while `travel.enabled` is off. Bell rows come from `travel_notify.bell_rows`: overdue, due soon, cash advance needing a liquidation, and for Admin Unit members "N travel flags to verify" once open flags exist.

## 7. CSS activity ↔ filing
Built in T2: calendar chips, buttons on activity pages. A filing stores `entry_id` or `event_id` plus a snapshot.

## 8. Documents
Built in T4: the relay. `gdocs_relay.py` signs every request (HMAC-SHA256 over `ts.payload`) and returns a `RelayResult`; routes get it through `gdocs_relay.get_relay()`, which tests replace. `apps_script/travel_docs.gs` is the source of the Apps Script; `docs/TRAVEL_DOCS_RELAY_SETUP.md` lists what a person must do. `POST /travel/f/{ref}/link-check` checks a pasted Drive link and stores the file id; `/admin/travel` shows relay status, a test button, signatories and template administrators. Built in T5: `travel_docs.build_payloads` makes the relay payloads for Appendix A and B, the travel report, the Job Order certification, MC 114, the CENRR and one RER per ride, from values the prepare page posts (`/travel/f/{ref}/prepare`, `static/js/travel_prepare.js`). `POST /travel/f/{ref}/generate` rechecks the rides on the server, opens flags, and makes the documents after the response, one relay call at a time. `GET /travel/f/{ref}/status` reports progress. Nothing typed on the prepare page is stored.

## 9. Guardrails and edge cases
One live cash advance per user and activity (partial unique index). Withdrawn filings free the slot. Reimbursement is hidden when a live cash advance exists.

## 10. Layout across screens
Readable at 400px; English text hard-coded.

## 11. Friction review of the remaining design
Open: every unlisted route flags until the Admin Unit adds approved routes.

## 12. Increments (each one PR)
T1 Foundations, T2 Filing shell, T3 Reminders and bell, T4 Relay, T5 Prepare and generate, T6 Flags, T7 Library and admin screens, T8 Templates, T9 Policy rates. All are built; what is left is the owner's list under Open items.

## 13. Open items
- **T2 nav**: only "My travel claims" and the hidden "Travel filing settings" are in the Travel menu. Verify, ceilings and library entries arrive with T6/T7 so the menu never links to a missing page.
- **Drive links**: only `https://drive.google.com/` and `https://docs.google.com/` links are accepted. A generated form can be replaced by the person's own Drive link (shown as "your own copy") until the relay exists.
- **"Not filed" chip**: shown only for calendar entries of kind travel or training that the viewer is on, and for in-person CSS activities the viewer is part of, from 60 days back onward. This keeps ordinary meetings quiet.
- **Overlay entries** (calendar entries linked to a CSS activity) are filed against the activity, never against the overlay entry.
- **Repeating items**: a filing is for one occurrence (the `date` in the link), but the one-live-cash-advance rule is per entry, so a series allows one live cash advance at a time.
- **Unliquidated warning** counts only submitted cash advances whose activity has ended.
- **Editing a ready filing** sends it back to "in progress".
- **Cash advance lead time (owner, 2026-10-14):** a cash advance can only be filed when the activity starts more than 7 days away (8 or more days ahead; `travel_rules.ca_lead_error`). Closer or past activities use a reimbursement. So a cash advance never has a deadline (assumption 5 confirmed); liquidation and reimbursement are due 5 calendar days after the last day, rolled to a working day, or 5 working days from opening when the activity had already ended.
- **Approved routes**: a route type counts as approved only when it has an active `travel_route_type` row and an `rer` ceiling (`travel.ceilings` drops inactive ones). Adding a route in T7 must create its RER ceiling.
- **Ride documents** (`cenrr`, `rer`) are not known when the filing opens. The checklist adds them from the derived answers `rides_cenrr` / `rides_rer`, set when the itinerary is prepared (T5/T6).
- **Open flags are part of `completeness()`** so the missing list shows them; "ready" is refused while any remains.
- **A fare of exactly 1,000.01 unreceipted** raises both `over_ceiling` (when above the route cap) and `no_receipt_over_1000`.
- **`peso_words(1)`** returns "One Peso" (singular); the spec gave no vector.
- **Starter MC 114 wording** (owner agreed generic placeholder text is fine) is generic text with the tokens `{{traveler_name}}`, `{{activity_title}}`, `{{dates}}`, `{{venue}}`. The owner's sample justification is a real person's document and was not copied; template administrators replace the starter rows in the library (T7).
- **Back-to-office report**: when `cert_of_appearance_available` is false the checklist asks for `bto_report` instead of `cert_appearance`.
- **Per diem and transport allowance rules**: supplied (DO 2019-0225 and 2019-0225-A) and built in T9; see `docs/TRAVEL_RATES_PLAN.md`. The page works the limit out, and a claim above it is flagged.
- **Wording** of the Job Order certification and the meals/lodging and extra-expense certifications needs the owner's approval against the official issuance.
- **2027 holidays** must be loaded before 2027 deadlines are trustworthy.
- **Reminders (T3)**: filings in "ready" are reminded too, since they are not yet handed in. There is no per-person opt-out; an administrator can switch the job off or change the lead days at `/admin/email`. The bell's flag line links to `/admin/travel` until T6 adds the verify queue; point it there then.
- **Relay (T4)**: the relay has never run against real Google; the checks listed in `docs/TRAVEL_DOCS_RELAY_SETUP.md` (escaping, merged-cell rows, `addEditor` emails, run time) are still to be done by a person. The script rejects template keys, folder names and request ids that are not plain slugs, a hardening beyond the draft in the spec.
- **Link check stores the file id only**: `travel_item` has no column for the file name, so the name is returned to the page but not saved (nothing in the spec needs it later). The link-check route has no button yet; T5's script calls it.
- **Generation (T5)**: each click makes a new revision per form (`doc_state` is `pending:N`, `done:N` or `failed:N`, and the revision is part of the relay `request_id`), so a retry after a failure never gets back a stale document and the older copy stays in Drive. A run that has not moved for 10 minutes (server restarted) is closed as failed the next time status is read.
- **Several RERs**: `travel_item` has one `doc_url`, so the first RER is the link and the others are listed in the item's note ("More: ...").
- **Flags are created by generate (T5)**: `sync_flags` keeps a flag's decision while its fingerprint is unchanged and replaces it when the fare, route or role changes. The Admin Unit verify queue is T6.
- **Job Order certification text**: the starter activities text is only the activity and dates; obligations are left blank for the person. The wording still needs the owner's approval.
- **Not yet checked against real Google**: the templates, placeholder names and repeated rows (see `docs/TRAVEL_DOCS_RELAY_SETUP.md`).
- **Flags (T6)**: a rejected flag blocks "ready" as an open one does, and sends a ready filing back to in progress; the person fixes the ride (a changed fare or route makes a new flag) or talks to the Admin Unit. Decided flags can be decided again by posting to the same URL, but the page lists only open ones; the "Recently decided" list is the last 30. The queue leaves out withdrawn and submitted filings. A rejection has no email, only the bell and the note on the filing.
- **Retention (T7)**: filings are purged 12 months after `submitted_at`, and also after `withdrawn_at` (the spec named only submitted ones; withdrawn filings hold the same links, so the safer reading was taken). The window is the `travel.retention_months` setting. The purge runs once a day with the room-guest purge, and by hand with `python retention.py --travel-filings [--dry-run] [--months N]`. Open filings are never purged.
- **Library (T7)**: for each place a text is used, the first switched-on text (lowest id) is the one pre-filled. There is no delete, only switching a text off. Only the four tokens `{{traveler_name}}`, `{{activity_title}}`, `{{dates}}`, `{{venue}}` are accepted.
- **Ceilings (T7)**: amounts must be more than 0 and at most 100,000. Switching a route off keeps its ceiling; the route simply stops counting as approved.
- **To do by people (not code)**: deploy the relay and fill the templates (`docs/TRAVEL_DOCS_RELAY_SETUP.md`); name template administrators; load 2027 holidays; confirm the readings in `docs/TRAVEL_RATES_PLAN.md` section 3 and check the Policy rates tab against the issuance; approve the wording of the Job Order certification and the meals/lodging and extra-expense certifications; confirm the Job Order starter text; run the live relay checks.
- **Templates (T8)**: the office's CENRR and RER are Excel forms, so their templates are Google Sheets and the relay fills Sheets as well as Docs (it checks the template's type). The five Word forms are converted by `apps_script/travel_templates.gs`, which was written from the wording of the sample files and has not run against real Google: its report lists missing placeholders, and the output still needs a person's eye (tables, logos, merged cells). Known simplifications: the CENRR's date row is removed and its details line becomes `{{p_date}}: {{p_text}}`; Appendix A's `itinerary_no` and the Post Travel Report's unit lines are not placeholders; the MC 114 closing sentence ("reimbursement requested") is fixed text.
- **Local test setup**: the HTTP tests need a `css_is.db` (gitignored). `python setup_db.py` creates one; nine tests (`test_ai_report_draft` x3, `test_avatar_care`, `test_home_feeds`, `test_integrity`, `test_routes[/work-arrangement/approvals]`, `test_search::test_api_search_activities`, `test_wellness::test_chief_pages_are_gated`) fail on that sample database and also fail on `main`.
