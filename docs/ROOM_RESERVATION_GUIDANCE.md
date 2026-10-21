# A17 — conference-room guidance (7.85)

## This increment

The room reservation journey now explains the current state and who acts next, from the availability board through requesting, decisions and recovery. Existing room services and POST routes remain the source of authority.

- **Requested / standby:** no hours are reserved. The Administrative Section must approve or confirm the request; the reservation page is the place to check the current decision.
- **Approved:** the listed hours are reserved. The owner can use the existing withdrawal/meal controls when applicable.
- **Move waiting:** the new time is unapproved; the original booking remains reserved only when the related record is actually still approved. Once a replacement exists, the old record points to it instead of suggesting a duplicate request. Owned related links focus the existing row without submitting anything.
- **Declined / cancelled:** the decision reason remains visible. Alternative buttons say **Request** for a fresh approval request or **Book** for the existing immediate-approval recovery after an administrative bump. A choice is revalidated by the original service. Future records with no free alternatives still appear under **Needs a new time**, with a link to check availability.
- **Withdrawn / expired / past:** guidance explains that these records cannot establish a new booking. Withdrawal messages no longer promise the hours are free of other bookings.
- **Approval queue:** current blockers, standby consequences, the responsible section and note/reason inputs are clearer. Past requests have no approval/standby-confirm button, matching the service's existing date check. Decline and series actions retain their existing checks.
- **Guest tracking:** the same display rules apply after the existing signed tracking-link validation. Guidance does not mint a new tracking link or claim that an email was delivered. Existing email behavior is unchanged.

## Availability and form recovery

The request panel reads the existing `/rooms/api/day` endpoint for the selected date, including dates outside the visible week. That response contains states and slot labels, not pending meeting titles, requester names or contacts. A request generation check prevents an older response from replacing a later selection; abort is an optimization, not the correctness guard.

The panel distinguishes free-to-request, pending, booked/unavailable, closed-date and standby states. A failed availability check keeps the draft and offers an explicit **Check availability** retry. It does not automatically retry a submission, reserve slots, or skip the original fresh POST checks. From/Until summaries follow the same inclusive range ordering as the service.

On narrower screens the request panel uses the shared A16 focus helper: background isolation, a named dialog, focus containment, Escape dismissal and return focus. A closed panel is inert and hidden from assistive technology. Resizing preserves the active form field; the desktop panel remains a normal region. Day choices are ordinary links with a current-day indicator, and the server form remains usable without JavaScript.

Server errors are visible and focusable inside the open panel, with the submitted values retained. Grid labels distinguish **Yours · Requested** from an owned approved booking and include the visible wording in their accessible names. An approved booking belonging to someone else is not labeled as the requester's booking merely because they also have a pending request for that time.

## Boundaries and performance

`rooms_guidance.py` produces display facts; it does not approve, withdraw, send mail or change an identity. The My reservations route starts with its existing owner-filtered records and builds one relationship index for the page. Related-record work adds no per-row SQL or all-record rescans. Guest relationship reads are limited to immediate linked records with the same guest contact fields; no new token or mutation authority is issued. Foreign requester relations are not rendered.

Existing ownership checks, Administrative Section membership, first-decision rules, uniqueness constraints, notice/closure rules, signed-link validation and request security remain independent of the UI. Meal, series, activity/calendar links and notification services continue to use their original actions. The underlying My reservations list is still unpaged; this increment does not claim to have solved its existing large-register query costs.

## Evidence and remaining work

- `tests/test_rooms_guidance.py` verifies real lifecycle transitions, move/replacement agreement, bumped versus declined recovery, unavailable/stale alternatives, expiry, escaped reasons, ownership and fresh membership checks, guest boundaries and reads without business effects.
- `tests/test_rooms_guidance_browser.py` serves actual application responses over local HTTP, including real form POSTs and 303 redirects, using one synthetic authenticated requester. It checks pending-versus-approved state in SQLite, mobile/desktop/light/dark behavior, stale responses without abort support, explicit retry, retained server-error drafts, related-row focus, resizing, day navigation and the native no-JavaScript form. External notifications are disabled in that fixture; passive telemetry is distinguished from reservation writes.
- The explicit axe-core 4.14.0 runner samples **24 states**: board, request panel, My reservations, guest tracking, room approvals and conflict recovery, each in light/dark at desktop/mobile sizes. Its report includes engine hash, browser version, incomplete checks and overflow results: [automated evidence](audits/2026-10-19/A17_ROOM_AUTOMATED_EVIDENCE.json). A clean sampled scan is not a whole-product accessibility certification.

Reproduce the local scan with the locked test environment and installed Chromium:

```sh
npm install --prefix /tmp/a17-audit --ignore-scripts --no-audit --no-fund axe-core@4.14.0
A17_AXE_PATH=/tmp/a17-audit/node_modules/axe-core/axe.min.js \
A17_REPORT=/tmp/a17-report.json CSS_TEST_NOW=2026-10-20T06:00:00 \
python -m pytest -q tests/browser/a17_rooms_probe.py
```

The runner is excluded from ordinary test collection; no runtime or test dependency was added. The report retains incomplete checks for manual review. No live production workflow or real screen-reader session was performed. Staff task observations, other browser/zoom/forced-color checks and the A16 manual exit evidence remain open. Calendar changes/feed subscriptions and travel filing/approvals are later A17 increments; their existing links and actions have not been redesigned here.

## Release and rollback

Version 7.85 increments current main 7.84, with matching application/changelog/cache versions and changed room asset references. The deployment inventory includes the new runtime guidance module; static/template folders already ship through their existing paths. There is no schema migration or new provider integration. Revert this frontend/guidance increment and publish a new application/cache version through the existing release workflow if rollback is required.
