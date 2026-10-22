# A17 — calendar guidance and recovery (7.87)

## This increment

Calendar item pages now explain the saved schedule state, the organiser/owning unit, the next step and the scope of changes. The calendar remains a shared schedule: anyone who can see an item may edit it under the existing rules. A **Confirmed** schedule is not room approval, travel approval or proof of email delivery. Tentative and postponed items tell the reader to check with the organiser. Cancelled items explain their absence from ordinary views and the existing restore period.

- **Series:** ordinary edits and cancellation affect the whole series. A selected occurrence retains its `?date=` link and the existing Change just this one / Skip this date controls. A series download is identified as covering the whole series.
- **Linked CSS activities:** the activity still owns its title, dates and venue; date changes retain the existing management check and registrant notification choice. Cancelling the calendar overlay does not cancel the CSS activity. Room and travel records retain their independent status and controls.
- **Restore:** the display uses the same 30-day boundary as `cal_restore`, including legacy cancellations without timestamps. Expired items have an explanation instead of an unusable Restore button. An unparseable timestamp receives a review message. The original service still checks the boundary on POST.
- **Cancellation:** Cancel item opens a native review page before the existing POST. It explains series scope, restore limits, separate room/travel records and notification/refresh delays. Reading the review page changes no calendar business state. The original POST remains available and independently checks current visibility. This also works without JavaScript.

## Editing and read recovery

Validation, conflict and linked-activity date-confirmation responses focus a visible message before further editing. Draft fields remain on the server-rendered form. A conflict offers the current item in a new tab, explains that no save occurred, and labels the existing next save **Replace with my changes**. Another intervening edit is still checked by the original revision guard.

If cancellation happens while an edit form is open, the POST returns a 409 draft page instead of redirecting away and losing the entered details. It shows the cancellation, offers review in a new tab and withholds the ordinary Save button. It does not restore the item or write the draft. Visibility loss still returns the existing 404 rather than exposing an inaccessible record.

The item preview opens with an announced loading state. Failed reads keep the calendar page open with an explicit GET retry and a full-page link. Both delayed successes and failures are ignored after dismissal or a newer selection. Dialog cleanup happens synchronously, so an old queued close event cannot erase a preview reopened by Back/Forward navigation. The read generation guard is independent of transport cancellation. Native dialogs use the shared A16 focus helper for containment, Escape and focus return; quick-add More options still carries entered fields to the ordinary form.

## Downloads and subscriptions

A one-item `.ics` download is described as a one-time copy; importing it is not an ongoing subscription. Existing download/feed endpoints, UID/sequence rules, recurrence, visibility and cancellation output are unchanged.

The calendar's More menu and item detail link to `/me#calendar-feed`. That profile section now shows whether a subscription link exists, its saved scope and birthday choice, and explains that page filters do not change those settings. App-specific instructions cover subscribing from a URL, read-only behavior, refresh delays and checking the office calendar for current facts. No app registration or refresh receipt is inferred from creating a link.

The private link remains a bearer credential, displayed only to its account owner. Reset/revocation stops future reads through that link and cannot erase cached/imported copies. No new provider request, external script, clipboard permission or secret-bearing telemetry was introduced. The profile page also uses the existing theme text color for filled buttons and a larger Subscribe target.

## Evidence and remaining work

- `tests/test_calendar_guidance.py`: lifecycle meaning, exact restore boundary/service agreement, current visibility, read-only cancellation review, cancelled-edit draft retention, repeated conflicts, linked-activity consequences, occurrence links and independent subscription settings/revocation.
- `tests/test_calendar_guidance_browser.py`: actual application responses served over local HTTP, real form POSTs/303s/SQLite results, synthetic signed-in staff, blocked external hosts. Covers mobile/light and desktop/dark, modal focus, cancellation/restore, failed/stale reads, conflicts, validation, subscriptions, no-script cancellation, bookmarked previews/history and occurrence deep links.
- After integrating the concurrent Supplies 7.86 release, 57 focused calendar guidance/browser, Supplies acceptance, release and email-coverage tests passed. The accessibility evidence was refreshed on the integrated code.
- Existing calendar, room, home-feed and shared accessibility suites passed **1,228 cases** during the broader local regression run. The final browser run passed all **12 journeys**, including additional history/occurrence cases and a deterministic queued-close/reopen regression added after CI exposed that race; required full CI runs also include them.
- Pinned axe-core **4.14.0** / Chromium **154.0.8037.57** sampled **52 states** at 1440px and 390px in light/dark: agenda, preview, quick add, confirmed/tentative/postponed/cancelled/expired details, cancellation review, conflict/validation recovery and subscription off/on with help expanded. [Evidence](audits/2026-10-19/A17_CALENDAR_AUTOMATED_EVIDENCE.json) records zero automated violations/overflows and retains **128 incomplete checks** for review. Evidence contains diagnostics/selectors, with private feed URLs redacted. Mobile detail/conflict screenshots were visually reviewed locally.

Reproduce the explicit scan outside ordinary test collection with an independently installed pinned engine:

```sh
npm install --prefix /tmp/a17-audit --ignore-scripts --no-audit --no-fund axe-core@4.14.0
A17_AXE_PATH=/tmp/a17-audit/node_modules/axe-core/axe.min.js \
A17_REPORT=/tmp/a17-calendar-report.json CSS_TEST_NOW=2026-10-20T06:00:00 \
python -m pytest -q tests/browser/a17_calendar_probe.py
```

No live production workflow, real calendar provider refresh or manual screen-reader session was performed. Staff observations, incomplete-check review, other browsers, real zoom/mobile/forced-color checks and the A16 manual exit evidence remain open. Travel filing/approval refinements are the next A17 increment. This is not whole-product accessibility certification.

## Release and rollback

Version 7.87 increments main 7.86 (the Supplies release) with aligned changelogs, service-worker version and calendar asset references. `calendar_guidance.py` is in the deployment inventory. No schema migration or new dependency is required. Roll back by reverting this increment and publishing a new application/cache version through the existing release workflow.
