# Private guided meetings and room requests through webhook replies

This draft repair is part of PR #572, candidate 9.77. It completes the private
interactive transport without an outgoing Telegram connection. The owner still
defers deployment, activation and actual hosted acceptance. Group/automatic
outgoing delivery and the complete T4.4 live pilot remain separate open work.

## Meeting workflow

1. With existing linking/inbound/delivery/calendar-read/calendar-create switches
   enabled and both calendar grants explicitly consented, send `/meeting` in the
   linked private chat. Open the signed-in preparation link returned immediately.
2. Choose exact title, Manila date/time, audience, unit and participants. With
   separate room-read/request grants and switches, optionally choose one room
   block and the explicit room-request checkbox. It remains unchecked by default.
3. Submit **Prepare exact private preview**. No calendar entry or room request
   exists yet. The resulting page shows `/meeting_preview OPERATION_ID`.
4. Send that command privately. Check the entire exact preview, including room
   choice, participant identities, audience, duration and Manila expiry. The
   five-minute lifetime starts when the form prepares the preview, not when
   Telegram displays it.
5. Send the exact `/meeting_confirm CODE` displayed there. The reply contains the
   recorded meeting/room outcome and source links. `/meeting_receipt OPERATION_ID`
   explicitly recovers current outcome without creating anything again.

A calendar-only meeting requests no room. A combined result can save the meeting
and fail its room child; that is a partial outcome, never a booked room. A
successfully submitted room request remains pending Administrative Section
approval. Normal domain audit, calendar/email outbox and room approver-notice
records retain their existing behavior; interactive Telegram uses no outgoing
provider call.

## Existing meeting / room-only retry

With existing calendar-read/room-read/room-request switches and separate grants,
send `/room_request` privately. Open its signed-in guide and choose an existing
meeting you created or participate in, plus one continuous room block. Submit
**Prepare exact private preview**, then send the displayed
`/room_preview OPERATION_ID`. Verify the exact hours/status/no-booking statement
and send its `/room_confirm CODE` within the same five-minute lifetime.
`/room_receipt OPERATION_ID` returns the current recorded result.

For a failed room child, the meeting receipt names the saved meeting and supplies
a parent-bound room-only retry link. Send `/room_request` first, then use that
retry link and confirm fresh hours. The new child remains linked to the original
meeting operation. Neither retry nor receipt recovery creates another meeting.
Original parent recovery includes the updated child outcome. Do not start a new
meeting merely because room submission failed.

## Authorization, atomicity and delivery

No grant is added automatically and no host switch is enabled by this code.
Existing calendar/room authorization, own-request rules, source visibility,
revision/participant/name checks, conflicts, module controls and explicit consent
remain authoritative. No new action grant, endpoint or schema is introduced.
Forms keep existing sign-in, cookie-bound CSRF, body bounds and rate limits.
Their operation IDs are non-secret routing identifiers, checked against the
signed-in actor/action before being displayed; confirmation codes never enter
URLs. Preview retrieval and recovery additionally bind the current private
sender, account, connection/generation, bot, action and original context.

Private guide, preview, confirmation and receipt replies use authenticated intake's
serialized writer transaction. Mutation, domain audit, consumed preview, durable
operation receipt, update deduplication and uncertain webhook handoff commit
atomically. Late domain/authority/expiry failures roll back to a local savepoint
before a neutral reply. SQLite failures roll back the entire update and return
503, allowing Telegram's retry before expiry. An already-committed operation
cannot be recreated by repeated/concurrent confirmations or explicit recovery.

Telegram supplies no success result/message ID for webhook responses. A crash
after commit but before response can lose the reply; request the explicit receipt
or issue a fresh command. Duplicate update IDs receive only acknowledgment and
never repeat a handoff. Fresh preview/receipt commands intentionally request
another current copy; they do not authorize automatic retries of uncertain sends.
No exactly-once guarantee is made for restoring an older database snapshot.

Private webhook action forms queue no outgoing guide/preview/receipt push. Old
pending private action deliveries become ineligible in webhook mode; their
business operation/receipt remains available for explicit recovery. Existing
uncertain deliveries are never replayed. Queues store command/body-hash and
uncertain response metadata, not rendered meeting contents or raw confirmation
codes. Preview fields are scrubbed on consumption/expiry/revocation/restore by
the existing lifecycle. Source changes after a response appears on later reads;
messages already in flight/received cannot be recalled.

## Existing direct/group paths and rollback

`CSS_TELEGRAM_REPLY_TRANSPORT=direct` preserves the existing worker path for
private guides, previews, confirmations and recovery. The new private pull
commands are webhook-only and ignored in direct mode. Group-origin actions retain
the existing asynchronous worker/membership-verification path, even when private
reply mode is webhook. New pull commands never turn a group operation into a
private-origin action or perform network membership checks under a writer lock.
Group form success retains the old delivery instructions.

Pause using existing inbound/delivery or relevant calendar/room action/read
switches. Grant revocation/disconnect/account changes fence the next pull/commit.
Transport rollback follows the existing reviewed backup/restart procedure; it
never resets update IDs, operation keys or uncertain deliveries. An unconsumed
webhook preview has no queued push to revive after switching to direct mode:
prepare a new preview if its code was never retrieved. Confirmed source records
and receipts remain intact.

## Automated and hosted acceptance

New actual 390×844 JavaScript-disabled browser cases obtain both linking codes
from actual bot messages, open the returned guide, submit the real forms, read
preview operation commands from those pages, and extract confirmation codes only
from bot replies. They cover calendar-only followed by a separate room request,
and the optional combined flow, with both outgoing sends and membership calls
forbidden. Legacy browser tests explicitly select direct mode. Focused cases
cover partial room failure/retry, current authority/expiry, wrong actors/actions,
response/late-domain rollback, concurrent confirmations, old private push
suppression and group worker preservation.

All data/providers are synthetic. Live source SHA, real user receipt, group
behavior, approval notifications and scheduled delivery require a separately
authorized hosted pilot. This repair does not claim those are verified.
