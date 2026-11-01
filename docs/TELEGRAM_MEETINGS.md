# Guided Telegram meetings (T3.2)

Draft 9.75 adds a [private webhook guide/preview/confirmation/recovery flow](TELEGRAM_PRIVATE_MEETING_WEBHOOK.md). Direct/group worker behavior below remains available; deployment and live acceptance are separate.

T3.4 update: the optional [combined room flow](TELEGRAM_MEETING_ROOMS.md) extends calendar-only creation below. Its separate room consent, explicit checkbox, partial outcomes and recovery rules apply only when selected.

This optional pilot creates one non-recurring Office Connect calendar meeting.
Calendar-only creation requests no room. The optional combined flow attempts a separately consented room request; it never books or approves one automatically, generates a video link, or discloses meeting content to a Telegram group. See the [plan and progress ledger](TELEGRAM_TWO_WAY_PLAN.md)
and [action contract](TELEGRAM_ACTION_CONTRACT.md). Deployment/activation is
separate from code completion; no hosted pilot is recorded.

## Staff workflow

1. With the pilot enabled, explicitly choose **Read permitted calendar entries**
   and **Create one meeting after an exact private preview and confirmation**
   during the existing browser + original-private-chat link flow. Both are
   unchecked by default. Existing links require disconnect/relink to add consent.
2. Send bare `/meeting` in the private bot chat or an active registered group/topic.
   Full meeting fields and confirmation commands are accepted only through the
   signed-in form and the original private bot chat respectively.
3. Open the private reply's signed-in preparation link within ten minutes.
   Choose the exact starting conversation, title, office date, start/end, venue,
   calendar audience, owning unit and up to twelve active participants.
4. Submit **Send exact preview to my private chat**. This saves no calendar entry.
   Check the private preview's participants (including account numbers to resolve
   duplicate names), audience, unit, Asia/Manila date/times, duration, the explicit room/no-room choice and exact confirmation deadline.
5. Send the displayed `/meeting_confirm CODE` in that same private bot chat before
   the deadline. The five-minute lifetime starts when the preview is prepared,
   not when Telegram delivers it. The exact original group/topic remains bound
   even though the preview and confirmation are private.
6. The private creation receipt contains the operation ID and signed-in source
   link. `/meeting_receipt OPERATION_ID` explicitly requests current recovery
   status without creating another meeting. Repeated confirmations and retries
   recover the same operation; a new preview/key is a separate user intent.

The browser form preserves fields after validation errors. Start/end must be
exact HH:MM values on one YYYY-MM-DD date, with end after start. Overnight,
recurring, all-day and other calendar kinds remain in Office Connect for this
increment. Titles/venues are at most 120 characters; participant and unit choices
come from the same current signed-in catalog and permission rules. Participant
names/unit labels changed after preview require a new preview. A meeting's calendar
audience is not approval to share its content with Telegram: group sharing still
requires the separate per-entry, per-destination exact-version consent.

## Authorization and delivery

Require the existing valid bot/webhook/canonical HTTPS configuration,
`CSS_TELEGRAM_INBOUND_ENABLED=1`, `CSS_TELEGRAM_DELIVERY_ENABLED=1`,
`CSS_TELEGRAM_LINK_ENABLED=1`, `CSS_TELEGRAM_CALENDAR_READ_ENABLED=1` and
`CSS_TELEGRAM_CALENDAR_CREATE_ENABLED=1`, plus both current read/create grants.
Group origins additionally require the existing group switch, active exact-topic
registration, current owner/bot provenance, and fresh provider owner/bot
administrator and requester membership proof at confirmation. Joining a group
never grants a calendar role. No write scope is added by migration or by merely
enabling a switch. Room submission is a separately consented [linked request flow](TELEGRAM_ROOM_REQUESTS.md); the optional [combined flow](TELEGRAM_MEETING_ROOMS.md) can now request one room block after saving the meeting, with both room permissions and explicit preview consent.

The ordinary Origin guard and cookie-bound CSRF protect the signed-in preparation
POST. It accepts at most 8 KiB and allowlisted fields; browser sessions never go
to Telegram. Origin references in links are account-bound routing identifiers,
not credentials. No confirmation token appears in a URL. The authenticated,
bounded webhook accepts `/meeting_confirm` only from private messages and stores
its hash rather than the code. Unsupported group field/confirmation messages are
ignored without collecting conversation text.

The action engine installs one real calendar adapter. It validates and applies
through the shared UI calendar service using the current delegated actor, source
`app`, normal audit/revision/email outbox, and no global administrator identity.
Preparation and its private preview descriptor commit together. Confirmation
commits calendar mutation, receipt, consumed preview and private receipt descriptor
together. Neither transaction calls Telegram, Meet or another provider. The
existing UI Meet behavior remains unchanged. With the optional room checkbox unchecked, no room record is written. T3.4 adds a separately recorded room child attempt only when explicitly previewed; see the [combined flow](TELEGRAM_MEETING_ROOMS.md) for partial outcomes and room-only recovery.

Preview tokens are domain-separated HMAC values over a random 256-bit nonce and
operation ID using the existing application signing key. SQLite stores the nonce
and token hash, never plaintext codes; rendering derives a code transiently.
This allows restart-safe private delivery without a second token. A signing-key
change can prevent delivery of an old pending preview; start a fresh preview.
Existing already-delivered codes remain bounded by their original expiry and
current authority checks. Current bot configuration and connection generations
still fence all action/delivery stages.

Workers claim action updates before leaving the writer transaction for group
membership verification. At most twenty updates and two group action proofs run
per processing tick. The existing outbound drain remains capped at twenty
candidates and two group-send verifications. Confirmation deadlines account for
elapsed processing/provider time and are rechecked before commit. Duplicate
workers/updates cannot create a second record for the same operation.

Private preview/receipt delivery uses the existing pacing, bounded transport,
revocation and final-send fences. An expired or changed preview is suppressed;
receipts recheck current source visibility. Uncertain sends are never blindly
resent. The explicit receipt command can request another copy and may therefore
produce a duplicate message, while returning the same business outcome. Telegram
acceptance does not prove reading and cannot be recalled.

## Storage, deletion and recovery

Initialization adds the minimal ten-minute `telegram_meeting_origin` routing
table, nullable preview nonce and operation context JSON columns, and a receipt
source-deletion trigger. Repeated initialization preserves data; no topology or
new service is introduced. Earlier dormant previews without nonce/context metadata
are not delivered by the new meeting path; begin a fresh meeting request. Migration
grants no action consent.

Pending preview content clears on consumption, grant/connection/account revocation,
group-generation changes, expiry and restore using the existing action hooks.
Restore also deletes all meeting-origin references and pauses/revokes the existing
Telegram state. Origin routing rows are purged in batches of twenty after expiry
plus 24 hours. Operation routing context is retained with receipt metadata for
180 days, then scrubbed with result details while key/hash tombstones remain.
Token rows retain the existing expiry-plus-24-hour purge. No rendered business
message is stored in delivery descriptors or processed updates.

Hard deletion in Office Connect clears a receipt's result foreign key and records
`calendar_deleted`, allowing existing delete tooling to work. It cancels queued
source receipts and marks an in-flight receipt uncertain while clearing its claim.
Recovery reports deletion without a stale source link and never recreates the
entry. Soft cancellation and other later source changes remain visible in Office
Connect; automatic change notices belong to T4.

For a lost response or worker restart, use the original operation ID. For snapshot
rollback, keep all bot writes off pending receipt/provider/durable-storage
reconciliation; an older restored snapshot may have lost committed operations.
No exactly-once promise is made across snapshot rollback.

## Operator pilot and rollback

Keep the default-off state for this PR. Before any activation, verify the deployed
SHA, durable DB/snapshot behavior and recovery, canonical HTTPS webhook ownership,
Bot API reachability and ownership of a synthetic private account/group. Then
verify fresh read/create consent, private and exact-topic starts, preview/deadline,
manual confirmation, one record after duplicate updates, private source receipt,
read-only/foreign account denial, membership loss, disconnect and restore. No
such hosted test is claimed by mocked tests or merge status.

Pause meeting writes by disabling `CSS_TELEGRAM_CALENDAR_CREATE_ENABLED`; pending
confirmations then deny. Disable delivery/inbound independently as needed, or
revoke the account link/group registration. Existing meetings remain in Office
Connect. Preserve operation receipts/tombstones and restore fencing on rollback;
never replay uncertain deliveries or historical confirmations in bulk. Keep separately scoped room writes off unless verified under their own runbook,
and keep change notices/reminders off. [T3.4](TELEGRAM_MEETING_ROOMS.md) adds the optional combined flow with separate child receipts and room-only recovery; T4.1 next adds durable change events.
