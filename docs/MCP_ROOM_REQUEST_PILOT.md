# Linked room request pilot (v8.90)

M3.6 adds `get_my_room_request_context`, `prepare_room_request` and
`get_room_request_operation`, disabled by default. Hosted acceptance is pending.
It follows paper handover records merged in
[PR #501](https://github.com/jongsky25/css-is/pull/501), commit
`e56a1e5f1f9d8460cc5cae0f5313927195933f0e`.

## Bounded action and consent

Separate optional `rooms:request` consent prepares one internal, self-owned room
request linked to an existing plain one-day calendar meeting the user created or
participates in. Broad calendar visibility and technical admin authority alone
are insufficient. Recurring, cancelled, multiday and CSS-linked entries are
outside this pilot. Existing grants and default read scopes are unchanged. The
personal-calendar write flag and calendar read scope are not required.

This pilot records **Requested**, pending Administrative Section approval.
Requested holds no booking, so unrelated requests can compete for the same
hours. It creates no new calendar meeting, edits no meeting schedule, approves
nothing and adds no meals, standby, repeating series, external requester,
stock/financial operation or payment. A separate normal approval is needed to
hold the room. Ordinary room-request visibility and follow-up rules apply.

## Fresh context and exact preview

Read `get_my_room_request_context(entry_id)` first. It returns an exact revision
digest, meeting day/time/status, safe public room-hour availability, current
initial-notice recipient count and whether a live linked request already exists.
It exposes no meeting notes, video URL, attendee names, rival titles or recipient
emails. The existing calendar read can identify an entry; use the context digest
rather than guessing a revision.

Preparation accepts a positive 64-bit calendar entry ID, the exact 64-character
hex `expected_revision`, configured `from_time`/`to_time` in HH:MM Asia/Manila,
and one random 16–80 character operation key. Choose one continuous block of
configured hours with the end after the start. Unknown title, date, participant,
requester, approval, standby, meals and repetition inputs are rejected.

The signed-in browser displays the existing meeting/title/day, calendar status
and meeting times alongside the exact requested room block, slot labels, current
requester identity and other active Administrative Section notification
recipients/email addresses. Requested room hours do not edit meeting times. The
preview explains the recipient count, normal request-email feature setting and
pending/no-booking semantics. If there are no other section recipients, it shows
that warning without inventing an approver or silently rejecting a request the
normal domain permits. The owner reviews it and presses **Confirm: request the
room**. The preview expires after ten minutes.

## Current checks and atomic effects

The preview binds the full meeting revision (including private fields only as a
hash), configured slots, requester identity, current recipient routing and email
setting. Current meeting authority, calendar revision, no live room link,
working-day/horizon/holiday/closure policy and approved/blocked hours are checked
under the writer lock. A new pending rival is not an approved booking; normal
room competition rules remain intact.

`room_actions.request_in_transaction` reuses the existing room domain service to
create Requested and link the existing entry. The reservation, unapproved slot
rows, link/audit, initial normal room notices, their durable delivery markers,
original-record identity mapping and MCP receipt commit together. A failure
rolls everything back. No provider I/O runs in the transaction. Different
previews for one meeting commit at most one live linked request. Retry and
recovery do not create another room request, edit the meeting or repeat notices.

The completed receipt reports original Requested state/reference, the fact that
this operation held no booking, the Administrative Section next-party role and
initial-notice recipient count, source/calendar links and current notice-state
counts. It returns no title, private meeting data or recipient emails. Later
approval/decline/withdrawal is separate: `booking_held=false` describes original
request creation, not current status. Inspect `/rooms/mine` and the calendar
source for current state. Recovery rechecks the active connection, current
meeting authority, room ownership/link, immutable source identity and retained
mapping. Cascading mappings prevent a deleted/reused room or notice ID from
recreating or rebinding the old operation.

## Initial notices and normal room mail

Initial MCP `new_request` room notices retain their normal in-app records and
composer, but their IDs are mapped to a separate durable worker in the same
creation transaction. The legacy `rooms_notify.flush` excludes mapped notices
regardless of pilot flag or email status, so its ordinary failed-message retry
loop cannot replay them. Existing non-MCP notices keep their normal behavior.
Normal room summaries, escalations, reminders and later decisions remain
separate existing events with their ordinary controls; the single-attempt rule
here applies to these initial MCP request notices.

The room scheduler runs the bounded worker (five notices/tick, maximum 20).
Before an external call it rechecks connection/source authority, current request
state/details, current section membership and the recipient address approved at
confirmation. Feature switches/global pause and transport configuration apply.
Obsolete/revoked notices cancel; disabled mail becomes `skipped_off`; missing
transport becomes `not_configured`. A committed unique `attempting` marker
precedes network I/O, so concurrent workers cannot send the same initial notice.
True sent means transport acceptance, not reading or booking approval. False,
ambiguous, crashed or unrecorded outcomes never automatically requeue. Stale
attempts become `uncertain` after ten minutes. A failure recording a successful
send leaves its committed marker in place and prevents another attempt.

Current receipt counts distinguish queued, attempting, sent, uncertain,
skipped_off, not_configured and cancelled. Queued is not sent. A timeout or
unavailable receipt is not proof of no request: recover the original operation
and inspect its source/notice state before another key or separate notification.
No resend, approval, cancellation or withdrawal tool is added.

Expired/completed preview copies clear. Worker cleanup also runs while sending
is disabled; queued notices older than 24 hours cancel. Markers/hashes retain
idempotency, while normal room notices/history retain ordinary retention and can
be purged through their existing lifecycle. Limits are 50 live previews and
10,000 total keys per actor, plus the shared process-local 30/minute action
limiter. Multiple workers need coordinated rate limits; database writer locks
protect the request and delivery claims themselves.

## Operator acceptance and rollback

1. Deploy v8.90 or newer after release, import-closure and room/MCP/mail tests.
2. Finish hosted write acceptance before the named requester pilot. Enable
   `CSS_MCP_ENABLED=1` and `CSS_MCP_ROOM_REQUESTS_ENABLED=1`; reconnect with the new
   permission and refresh the catalog. Other write flags remain independent.
3. Read current context for a synthetic permitted one-day meeting. Compare exact
   revision/day/meeting time, configured requested hours, requester and recipient
   routing with the normal calendar/room screens. Verify no request before
   browser confirmation and no unrelated rival details in context.
4. Confirm once: Requested, self-owned, linked to the existing meeting, one set
   of unapproved slots and initial notices/markers, unchanged calendar and no
   booking hold. Compare source/reference and next-party role/count with receipt.
   Test zero other recipients and later separate authorized approval; original
   recovery must not recreate or overwrite either record.
5. Exercise lost responses, refresh, duplicate and competing confirmations,
   rollback at final audit, changed meeting/private data/slots/requester/routing,
   closures, taken hours, expired previews, lost access/session/grant and the
   supported one-day/continuous-block restrictions.
6. Verify mapped initial notices are never sent by the legacy retry loop, even
   with the pilot disabled. With synthetic transports test concurrent workers,
   feature/pause/configuration gates, revoked recipients, uncertainty, crash and
   failure recording transport success. No second automatic attempt is allowed.
7. Record deployment SHA, roles, exact entries/room IDs/hours/revisions/keys,
   notice states, timings and results. Local checks are not hosted acceptance.

Rollback: disable `CSS_MCP_ROOM_REQUESTS_ENABLED` and restart if needed. New MCP
requests and initial-notice delivery stop; bounded cleanup continues and the
legacy sender still excludes mapped notices. Normal room sources, pending
requests and separately authorized decisions retain their usual behavior. A
connection disconnect prevents its queued initial notices from being claimed.
Rollback never silently cancels a room request, reverses a booking decision or
replays an attempted notice. No live flag activation is claimed here.
