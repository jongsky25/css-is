# Calendar and room change notices (T4.2)

Implementation: [notice handoff/rendering](../telegram_notices.py),
[change capture/routing](TELEGRAM_CHANGE_EVENTS.md),
[durable sender](../telegram_bot.py),
[progress ledger](TELEGRAM_TWO_WAY_PLAN.md).
All pilots remain off by default. No deployed SHA or real provider/staff pilot is
verified by this implementation or its mocked tests.

## Behavior and audience

With the independently enabled change-notice pilot and current read consent,
committed UI, import, scheduler or trusted-action changes can reach the eligible
conversation. A notice reads the current source at send time. It never recreates,
edits, approves or retries a business action.

| Destination | Notice contents and authority |
| --- | --- |
| Private calendar creator/participant | Current title, office date/time, Asia/Manila, venue/status and signed-in calendar link; current source visibility and calendar read consent required. Bureau visibility alone is not a subscription. |
| Current internal room requester | Own reference/date/requested hours and current status, plus My room requests link. Requested means pending approval with no booking held; approved means booked. Declined/withdrawn/cancelled/expired remain distinct. No meeting details are inferred from room permission. |
| Explicitly shared calendar group/topic | Only the existing approved shared fields and signed-in source link, with exact current source-version consent, registration generations, current owner/read authority and fresh membership proof. Edits revoke sharing until reviewed again; cancelled sources remain excluded by the existing sharing policy. |
| Original room operation's exact group/topic | Anonymous day-slot free/requested/booked/closed snapshot. No request reference, title, requester, participants, decision reason or private calendar link. Sibling topics and unrelated registrations receive nothing. |

Guest contacts, unrelated administrators and approvers are not new recipients.
Deleted or inaccessible sources suppress a notice; no deleted content or stale
source link is disclosed. Configuration-only availability events do not invent
new subscriptions. Source-incarnation/revision checks suppress stale events and
row-ID reuse. Multiple changes can coalesce to the latest current source; this
is not a promise to deliver every intermediate edit.

## Handoff and transport

The scheduler prepares the existing bounded routes, then hands off at most twenty
unhandled routes per tick in one writer transaction. The outbox descriptor stores
only notice kind, route/event identifiers and bot provenance. Destination fields
retain connection/registration generations and exact topic. No rendered message,
raw token or provider body is persisted.

`telegram_change_route.delivery_key` is a durable handoff marker. A stable
`event + destination + topic` dedupe key is inserted into `telegram_delivery`
atomically with that marker. Restart, competing workers and repeated ticks cannot
enqueue a second attempt for that route. Failed/accepted/uncertain outbox outcomes
do not reset the marker. A notice is independent of the source operation receipt.

The existing sender retains twenty-candidate and two-group-proof limits, private
and group destination pacing, committed sending markers and conditional claim
finalizers. Group notice proofs use the route's current owner/bot/requester checks
outside the writer lock; elapsed proof time counts against source expiry.
Authorization runs again before render and immediately before the provider call.
The renderer re-reads current permitted data under the writer transaction. It
uses bounded plain text and the canonical signed-in source URL; no Markdown or
HTML interpretation is requested from Telegram.

A route cancellation now fences its matching outbox row in the same transaction:
queued/claimed/retry work cancels; sending becomes uncertain and loses its claim.
Source edit/deletion, consent revocation, account/link changes, group pause or
migration, and restore inherit this fence. An already accepted or in-flight
message cannot be recalled. A late provider success cannot overwrite an uncertain
row whose claim was revoked.

Existing failure semantics apply:

- Definite 429 responses honor the existing bounded retry delay and five-attempt,
  24-hour limit. Each retry rechecks the route, source and group proof.
- Timeout, ambiguous response or interrupted sending remains uncertain, with no
  automatic resend. Repeated handoff does not create a replacement.
- Definite provider rejection fails that delivery and pauses automatic notices
  for the exact bot/destination/topic. New changes do not bypass the pause.
  A group pause covers every eligible sender in that same registration.

To recover from blocking/removal, restore the bot's ability to receive messages,
then send a fresh recognized command in the original conversation (for example
private `/status` or exact-topic `/group_status`). A newly processed authenticated
command received after the rejection clears the pause. Wrong-topic, ignored,
failed, replayed or old updates do not. A new verified link/registration generation
also starts a new binding. Existing failed/uncertain notices remain terminal;
use normal private reads or source pages for the current state. Future eligible
changes can produce new notices after recovery. No historical replay command is
introduced.

## Migration, restore and retention

Normal initialization adds the nullable handoff column/index, an indexed
`telegram_notice_pause` metadata table and route/recovery triggers. Existing
prepared routes keep NULL until a permitted handoff. No new service, queue,
action grant or switch is introduced; current read scopes and independent
`CSS_TELEGRAM_CHANGE_NOTICES_ENABLED=1` remain required alongside valid canonical
bot/link configuration and the existing inbound/delivery/link/read gates.

Restore rotates the change epoch, cancels routes and fences queued/in-flight
notices through the existing hooks. It pauses/revokes connection and registration
state; old generations cannot revive after relinking. Normal restart preserves
handoff markers and paused destinations. Exactly-once behavior across rollback to
an older snapshot remains unproven.

Existing event/route cleanup remains bounded: routing expires after 24 hours,
cancelled route metadata removes after 30 days and terminal event/outbox metadata
after 180 days under their existing limits. The outbox may retain a terminal
identifier descriptor after its route is removed; missing or reused route IDs
cannot authorize that descriptor because event/destination/handoff bindings must
also match. Source identity tombstones remain. Active rejection pauses retain
only the metadata needed to suppress the invalid destination; obsolete bindings
are removed in batches of twenty after 30 days. Fresh recognized recovery clears
the pause immediately, before short-lived update metadata is purged.

## Pilot, pause and remaining work

Keep every pilot off for this PR. Before a later synthetic pilot, verify deployed
SHA, durable DB/snapshot recovery, canonical webhook/bot ownership and API egress.
Check UI time edits, pending/approved/declined room decisions, private/shared
projections, exact topic, source-sharing renewal, duplicates/restart, revocation,
bot blocking/removal, definite rejection recovery, 429, uncertain sends and
restore. Record actual evidence in the progress ledger. None is claimed here.

Pause notices with the change-notice, delivery, inbound or relevant read gate;
normal Office Connect records and approval processes remain authoritative.
Preserve metadata/restore fences on rollback. Never bulk replay confirmations or
uncertain sends. Current notices and creation receipts/email can coexist; user
channel preferences, quiet hours, reminders and cross-channel noise controls are
T4.3. The live complete-workflow pilot remains T4.4.

[T4.3.1 preferences and quiet hours](TELEGRAM_NOTIFICATION_PREFERENCES.md) now extends this delivery path. Current-user and owned-group choices gate automatic notices; a separate not-before field defers quiet work without changing provider backoff. The default-off pilots and source/permission/uncertainty fences above still apply. Durable reminders remain T4.3.2.
