# Personal calendar entry pilot (v8.83)

This M2.5 pilot adds `prepare_personal_calendar_entry` and
`get_personal_calendar_operation`. It is implemented and disabled by default.
Hosted operator acceptance is pending. It follows the saved report views merged
in [PR #494](https://github.com/jongsky25/css-is/pull/494), commit
`7ed5fa5f83bc7ac0b461e45859b3fc2789bdd05c`.

## Behavior and boundaries

Separate optional `calendar:entry:create` consent allows a new tentative personal
meeting. Existing read-only grants and default OAuth scopes are unchanged. The
only participant is the current account; the audience is `people`, with no owning
or additional units. The current account must meet ordinary Calendar staff and
participant eligibility. The source is the ordinary `/calendar/entries/{id}`
screen with its normal current-access checks.

Allowed inputs are title (1–200 characters), first day, optional last day within
366 days, optional paired start/end times, venue (up to 200), and note (up to
2000). Dates are ISO YYYY-MM-DD. Times are HH:MM in Asia/Manila; omit both for an
all-day entry. The end must follow the start when times are present. Unknown
fields, other attendees, audiences, status, type, recurrence, units, meeting URLs
and room parameters are rejected. Text is escaped in browser review.

The tool prepares an expiring preview and returns its confirmation URL. It does
not create an entry. The signed-in owner reviews all proposed details, visibility,
status and type, then presses **Confirm: save my calendar entry**. CSRF, canonical
Origin, current session, connection, scope, payload integrity and current Calendar
eligibility are rechecked. The existing transactional calendar creation service
creates the entry, normal calendar history and seen marker; the personal-save
identity, completed receipt and content-free integration audit commit atomically.
The normal title-bearing calendar revision is part of the source record. The
integration audit and tool receipts contain no title, venue or note.

No invitations, email outbox entries, room bookings, Meet links, activity links,
travel filings, submissions or approvals are created. The domain calendar service
skips notifications to the acting person, who is this entry's sole participant.
There is no MCP edit, sharing, cancellation, restoration or delete tool. Later
manual Calendar changes use existing UI authority and are never overwritten by
MCP recovery or replay. Completed receipts mean the original creation succeeded;
they do not assert its current details or status. The original immutable calendar
UID and owner-operation mapping prevent a receipt from linking a replacement row.

## Retries and retention

Keep one random 16–80 character operation key across retries. An exact same-key
retry recovers the same preview or original entry; another payload or connection
cannot reuse it. Receipt lookup requires the original active connection and
explicit scope. Refresh rotates tokens while preserving that connection identity.
A timeout or unavailable receipt is not evidence that saving failed. Inspect the
original operation/source before preparing a new key.

Previews expire after ten minutes. Completed payload copies are cleared in the
creation transaction; expired copies are lazily cleared in independent batches
of up to 100. Operation tombstones/receipts remain, so keys are not silently
recycled. Limits are 50 live previews and 10,000 total operations per account,
plus the shared process-local action limiter (30/minute). Multi-worker deployments
need a shared limiter before relying on that limit across instances. Saved entry
content follows ordinary Calendar retention and history behavior.

## Operator activation and acceptance

1. Deploy v8.83 or newer with runtime import-closure and release checks passing.
2. Enable `CSS_MCP_ENABLED=1` and `CSS_MCP_PERSONAL_CALENDAR_ENABLED=1` only for the
   intended pilot deployment. Other write switches are independent.
3. Reconnect/reconsent and select the separate personal-calendar permission. Old
   grants are never widened automatically. Refresh the ChatGPT tool catalog.
4. Prepare a synthetic all-day entry, then a timed entry. Compare the entire
   browser preview and normal source page with the exact requested values.
5. Confirm no record exists before confirmation; one private tentative entry
   exists afterward. Verify another account, including a bureau administrator,
   cannot view it. Verify no email/outbox, room, activity or travel side effects.
6. Exercise retry, receipt recovery, token refresh between preview and confirm,
   duplicate confirmation, expired preview, revoked connection and lost Calendar
   eligibility. Replays must create no second entry. A manual Calendar edit must
   survive subsequent receipt recovery.
7. Record deployment SHA, roles, exact input/source IDs, outcomes and timings.
   Local automated checks are not hosted acceptance evidence.

Rollback: set `CSS_MCP_PERSONAL_CALENDAR_ENABLED=0` and restart if needed. Pending
previews and MCP receipts become unavailable; ordinary Calendar entries and the
normal source screen remain available under existing authority. Disconnecting
revokes the connection immediately. Rollback does not erase saved entries or
silently undo a confirmed action.
