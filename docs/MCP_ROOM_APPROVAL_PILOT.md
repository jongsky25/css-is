# Plain room-request approval pilot (v8.99)

M4.3 adds `get_room_approval_context`, `prepare_room_request_approval` and
`get_room_approval_operation`, disabled by default. It follows merged
[PR #510](https://github.com/jongsky25/css-is/pull/510), commit
`dd0e4e83e8839a8cade0356fb298692f997e6284`. Hosted acceptance is deferred until
after the planned room/travel decision implementations; it has not passed here.

## Exact booking and current authority

One plain internal Requested room reservation becomes Approved and holds exactly
its existing requested hours. Current active/internal Administrative Section
membership is required, using `rooms.is_room_admin`; technical administrator role
alone and acting OIC status do not grant it. The requester cannot approve their
own reservation. The current filing actor is also refused. Existing ordinary
Rooms authority and broader actions are unchanged.

Separate optional `rooms:request:approve` consent, global `CSS_MCP_ENABLED=1` and
independent `CSS_MCP_ROOM_APPROVALS_ENABLED=1` are required. Request/create/read,
calendar and other decision grants do not widen into approval. The requester must
remain an active staff account. Guests, on-behalf-of records, meals or an existing
meal form, series, moves, standby, activity links and previously decided records
use ordinary Rooms. This pilot never declines rivals or overrides held/blocked
hours, moves a booking, changes a series, orders meals or cancels anything.

Supported requests have a nonempty title up to 250 characters, purpose up to 2,000
characters, known format, retained creation identity and 1–12 continuous active
configured hour slots. The normal weekday/holiday/closure and 90-day request
horizon apply. Today is eligible only before the first requested hour begins.
A linked calendar meeting must still be a permitted single-day meeting for its
requester, with the same title/day and requested hours inside its timed block.
Private calendar notes, URLs and people are hashed for consistency, not displayed
or returned to the model. Approval does not confirm or otherwise edit the meeting.

Up to 25 overlapping pending rivals are supported. Their count is reviewed, but
no other request's title, purpose or requester is copied into the MCP preview.
Rivals remain Requested and their fields do not change; the newly approved hours
are unavailable for another approval while held. Larger competitions use the UI.

## Fresh context and exact browser review

Use an ID from the existing Rooms/Approvals source with
`get_room_approval_context`. It returns request ID, exact lowercase 64-hex
`expected_revision`, day, slot count, competing count and source link. It returns
no title, purpose, identities, contact details, calendar content or rival metadata.

The revision binds the complete reservation/slot records, active configured hours,
linked meeting, competing request identities/update stamps, current approver/
directory/unit scope, requester identity/address, mail feature/pause and requester
email/quiet-hour preferences, plus the normal room ICS option. A change requires
fresh context and review rather than a silent newer-source retry.

`prepare_room_request_approval` accepts only positive integer `room_request_id`,
exact `expected_revision`, nonempty `reason` up to 2,000 characters, and one random
16–80 character `operation_id`. No slot/date/status override, decline-rivals,
standby, series, meal, move, calendar update, guest or send-checkbox input is
accepted. Preparation creates a private preview and audit, not a booking/notice.

The signed-in approver sees the exact reference/title, requester and email
recipient, current Administrative Section approver, date/hours/timezone, purpose,
attendees/format, linked meeting ID, decision reason, pending-rival count and exact
email/preference/quiet-hour/ICS policy. Text is escaped and multiline text retained.
**Confirm: approve and book requested hours** explicitly authorizes holding them.
The existing bounded three-field CSRF/same-origin form works at 320px without
JavaScript. It expires after ten minutes and is revalidated under the writer lock.

## Shared core and atomic decision/notice

Ordinary `rooms.approve` delegates booking/audits to
`rooms.approve_in_transaction`, preserving normal public arguments and post-commit
rival, move, meal and requester hooks. The caller-owned core acquires no hidden
commit: it rechecks pending state/date/closures, marks the requested slots approved,
updates the decision, and records the domain audit. SQLite's unique approved-slot
index still enforces one held booking for each hour. Ordinary series/override/
move workflows retain their broader normal behavior.

The MCP helper checks current actor/source policy again and calls that core with
`decline_rivals=False`. The normal requester `approved` bell/notice is inserted
transactionally through `rooms_notify.on_decided(..., commit=False)`, restricted
to no-meal notices. A durable original identity, requester email marker, minimal
receipt and integration audit commit with the booking and domain audit. A final
notice/audit failure rolls all of them back. Two clients/keys racing the same
request commit at most once; two requests competing for one hour cannot both win.

Completed receipts verify the same original room ID/reference/creation stamp,
requester and retained operation/approver/decision mapping under current active
Administrative Section authority and same OAuth grant/resource/scope. Deleted or
reused source identities cannot bind an old receipt. Later ordinary withdrawal,
cancellation, scheduling edits or calendar changes remain separate. Recovery
never rebooks, restores old state or creates another notice. Retained approval
identities and existing approved-notice evidence block reapproval of an original
room through another key if its state is manually reset.

## Single-attempt requester email and existing channels

The normal requester bell entry is available immediately. There is one initial
email recipient: the requester's reviewed account/address. No decision is sent to
rivals and no new email to other room approvers is added. The usual requester
approval composer includes normal room details, reference and My reservations
link. The existing `room_ics` option adds the normal calendar file when reviewed
as enabled; it does not create an external calendar event or invitation response.

Disabled feature/global pause or requester room-email preference at confirmation
produces terminal `skipped_off`, native notice status and a normal skip log. Later
enabling cannot send that skipped email. Enabled notices commit as Queued;
queued means neither sent nor delivered. Normal feature/pause/preference/quiet-
hour/transport policy is checked again before a unique durable transport claim.

`room_approval_delivery.run` handles five queued notices per scheduler tick (max
20), rechecking original active grant/current Administrative Section approver,
original approved room/slots/configuration, linked meeting, active requester/name/
address and reviewed ICS setting. Source or identity drift cancels instead of
retargeting or composing changed content. Current quiet hours hold the queue
without consuming an attempt. Current feature/preference disable skips; missing
transport is terminal Not configured. An expired/past or started slot does not
produce a stale queued approval email.

A unique Attempting marker and native attempt count commit before provider I/O.
The worker uses normal mail policy and logs each handled result. Sent means
transport acceptance, not reading or guaranteed delivery. False/exception, process
death or failure recording transport success never automatically retry. Stale
Attempting becomes Uncertain after ten minutes. No resend endpoint is added.
Queued notices cancel after 24 hours; bounded cleanup runs even with flags off.
The native retrying Rooms mail loop explicitly excludes both existing MCP request
notices and these MCP approval notices, including while either pilot is disabled.

Existing ordinary future reminder/digest jobs and Telegram room notification/
availability projections retain their normal preferences and authority checks.
They are separate from this initial requester email; this action does not change
notification subscriptions, bot routes or group access. No direct send occurs in
the confirmation transaction.

## Receipts, retention and rollback

The receipt returns original approval/booked-at-decision status, reference/day,
slot count, requester next role, current email-state counts and Rooms source link.
It omits title/purpose/reason/names/addresses, private meeting data and rival text.
It reports the original booking decision, not a claim that a later-cancelled room
is still held. Current notice counts are not proof of delivery or reading.

Completed preview/snapshot copies clear in the commit; expired copies clear in
independently committed lazy batches of 100 before prepare/recover/browser access,
even when later checks fail. Minimal hash/key/result and original booking identity
remain for recovery. Normal room/bell/decision records follow their existing
retention; clearing a preview does not erase the shared decision or bell text.
Deleting a notice cannot make a key eligible for another booking or send.

Limits: 50 live previews and 10,000 total keys per actor, one request/continuous
block per action, 12 slots, 25 pending rivals and the shared process-local
30/minute action limiter. Multiple hosting workers need coordinated rate limiting;
database writer transactions and the unique slot constraint protect booking races.

Rollback disables `CSS_MCP_ROOM_APPROVALS_ENABLED`. New context/prepare/confirm/
recovery and new initial email attempts stop; bounded cleanup continues. Existing
bookings, native notices and retained receipts stay. Ordinary Rooms, future
reminders and Telegram jobs retain normal behavior. Rollback never cancels a
booking, changes a rival, frees a key or replays an uncertain email.

## Deferred hosted acceptance and named go/no-go

Automated implementation checks run for each increment. Per the current work
sequence, hosted ChatGPT acceptance will happen after room approval and travel
reviewer decisions are implemented. No hosting flag is enabled by this PR.

1. Deploy v8.99 or newer with local core/race/notice/email/preference/ICS/calendar/
   Telegram/browser/OAuth/release/packaging checks. Record deployed SHA/operator.
2. Before a named pilot, identify Administrative Section approver, independent
   requester, agreed synthetic room/meeting/day/slot IDs, and rollback owner.
   Reconnect with only the required new consent. Verify requester, filing actor,
   technical admin, archived/external/non-Administrative staff and read/request-only
   grants cannot approve.
3. Compare exact source/preview with ordinary Rooms: reference/title/purpose,
   requester, hours, current authority, linked meeting, pending rivals and exact
   email/preference/quiet-hour/ICS policy. Preparation must leave hours unheld.
4. Confirm once and reconcile unique held slots, decision/domain/integration audit,
   retained identity/receipt, one requester bell/delivery marker and unchanged
   calendar/rival/meal/series/move records. Verify normal requester email/ICS with
   synthetic transport and current states; queued is not delivered.
5. Race same request and overlapping requests/keys/clients; replay after lost
   response; inject final-audit/notice failure. Change role/directory, requester,
   meeting, closure, hours, competitor, policy, scope/session/grant or expiry.
   Failure must leave no partial booking, notice or unexplained missing receipt.
6. Test preference/feature skip-at-confirmation then enable, quiet-hour waiting,
   disabled pilot, source/recipient drift, concurrent mail workers, false/error/
   crash/result-write failure and native mail-loop exclusion. Prove no second
   automatic attempt. Verify normal reminder/Telegram preferences remain normal.
7. Withdraw/cancel/edit in ordinary Rooms and recover the old key; later state
   must survive. Check source identity mismatch, preview/notice cleanup/limits,
   320px/no-JavaScript and flag rollback. Record outcomes and a specific hosted
   go/no-go before enabling staff decisions. Travel decisions remain separate.
