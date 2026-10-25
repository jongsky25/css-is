# Linked Telegram room requests (T3.3)

The optional pilot submits one internal conference-room request for an existing
calendar meeting. It creates no meeting, edits no meeting, and never approves or
holds a booking. See the [delivery plan](TELEGRAM_TWO_WAY_PLAN.md),
[action contract](TELEGRAM_ACTION_CONTRACT.md), and independent
[meeting-creation flow](TELEGRAM_MEETINGS.md). All switches remain off by default;
no hosted activation is recorded.

## Staff workflow

1. With the pilot enabled, link using the separate **calendar read**, **room read**
   and **room request** checkboxes. They are unchecked by default and the original
   private bot chat must confirm the account and permissions. Existing links need
   explicit disconnect/relink; enabling a switch adds no consent.
2. Send bare `/room_request` privately or in an active registered group/topic.
   The guide goes to your private chat. Open its signed-in link within ten minutes.
3. Enter the number from the end of the meeting's signed-in calendar address.
   Choose exact room start/end hours. The source date is the meeting's date.
4. Submit **Send room preview to my private chat**. No request exists yet.
   Check meeting title/number/date/time/status, requested room block and configured
   hour labels, duration, Asia/Manila timezone, your requester account and the
   pending-approval/no-booking statement.
5. Send `/room_confirm CODE` from the same private bot chat before the displayed
   five-minute deadline. For a group origin, the original registration/topic and
   current owner, bot and requester membership remain required.
6. Read the private receipt's reference, current status and signed-in My requests
   and calendar links. `/room_receipt OPERATION_ID` asks for current recovery
   status without repeating submission. A confirmed request initially says
   **requested (pending approval; no booking held)**. Approval remains a separate
   Administrative Section action; later recovery can say **approved (booked)**.

A pending *action* means its preview has not committed a room request; this is
separate from an already submitted room reservation awaiting approval. Repeated
updates, workers, confirmation commands and the same prepared form do not submit
another request. A new preview/key is a separate intent, and is rejected while
the meeting already has a requested/approved room link.

The meeting must be visible to your current account, and you must be its creator
or a listed participant. Bureau visibility or an administrator role alone is not
enough. This pilot supports one-day non-recurring calendar meetings without a
linked CSS activity and excludes cancelled entries. An all-day/missing-time
meeting is labelled truthfully; requested room hours remain explicit. The room
block may include setup time, and its exact hours are separately shown from the
meeting's time. Select one continuous block of current configured hours.

No guest, on-behalf-of, standby, series, meals, encoding, approval, withdrawal or
cancellation is exposed here. Use existing Office Connect screens for those
supported workflows. No group source-share consent is inferred from starting a
request in a group; every guide, preview and receipt stays private.

## Authority and business rules

Require existing valid bot/webhook/canonical HTTPS setup; current delegated link;
inbound/delivery/link switches; `CSS_TELEGRAM_CALENDAR_READ_ENABLED=1`,
`CSS_TELEGRAM_ROOMS_READ_ENABLED=1`, `CSS_TELEGRAM_ROOMS_REQUEST_ENABLED=1`; and all
three corresponding grants. Calendar-create consent/switch is unnecessary when
requesting for an existing meeting. Group origins additionally require the group
pilot, exact current registration and fresh membership proof at confirmation.
Meeting and room tokens/origins cannot be exchanged between action commands.

The signed-in form retains ordinary Origin checks and cookie-bound CSRF, bounds
input to 8 KiB and accepts only origin/key, meeting number and hour fields. No
password, cookie, guest data or untrusted requester identity is sent to Telegram.
The requester always resolves from the current linked actor.

`room_actions.py` checks current actor, calendar visibility and creator/participant
authority. The preview binds the complete source revision (excluding read-seen
metadata) and configured slot snapshot; even a title change that does not advance
the calendar sequence invalidates it. Current authority, source revision, active
slots, ordinary working-day/holiday/closure/lead-time/90-day-horizon rules, existing
live links and approved/blocked conflicts are rechecked in the confirmation
writer transaction. Pending competitors remain permitted by the source rules;
none holds the hours. No slot receives an approved flag from this action.

Plain internal `rooms.request(commit=False)` and `rooms.link_entry(commit=False)`
require a caller-owned transaction. The request, slots, link, normal audit,
approver notice rows, operation receipt, consumed preview and private Telegram
receipt descriptor commit together. No provider/network call occurs under the
writer lock. Room notice email delivery remains in the existing scheduler.
Notification/receipt-insert failure rolls back the entire bot request. Existing
signed-in requests retain default commits and best-effort courtesy hooks,
including guests/meals/standby/series paths; these are not delegated to the bot.
Lazy slot initialization now preserves a caller's transaction too.

The usual action token/hash/nonce handling, private send-time authorization,
uncertain-send policy and bounded worker/transport limits apply. Explicit receipt
recovery may return another copy; it repeats no business action. Approval/change
push notifications are not implemented by T3.3; current source status is available
through explicit recovery, existing private room reads and signed-in pages.

## Migration, recovery and operator checks

Initialization adds an action discriminator to the existing minimal origin table,
defaulting older rows to `calendar.create`. It adds no new grant and preserves old
meeting origins. A calendar-read revocation also immediately scrubs/cancels pending
room previews because linking depends on that permission. Existing connection,
group, account, room-read/request grant and restore fences remain. Raw origin rows
and receipt/context metadata retain the existing bounded cleanup schedule.

A room-result before-delete trigger detaches receipt references, cancels queued
source sends and fences in-flight finalizers, mirroring the calendar deletion
behavior. Recovery reports deleted records without recreating them or returning
stale source links. Changing a room's requester or its calendar link denies the
original delegated receipt. A calendar/room deletion is not automatic withdrawal
of some other surviving business record; review My room requests in Office Connect.
Snapshot rollback still needs receipt/provider/durable-storage reconciliation;
there is no exactly-once guarantee across restoration of an older snapshot.

Keep this pilot off for the PR. Before activation, verify deployed SHA, durable
storage/snapshot recovery, canonical HTTPS/webhook/bot ownership and egress, then
use synthetic linked staff and one exact registered topic. Check fresh separate
consent, creator/participant denial cases, exact source/slot preview, normal
pending approval, concurrent booking refusal, duplicate/restart recovery, approved
status recovery, private delivery and disconnect/group/restore/source-change
fences. Mocked tests and a merge do not establish live verification.

Pause `CSS_TELEGRAM_ROOMS_REQUEST_ENABLED` to block new preparation/confirmation.
Disable delivery/inbound independently or disconnect/revoke the group as needed.
Preserve receipts, tombstones and restore fencing on rollback; never bulk replay
old confirmations or uncertain sends. Existing requests and approvals remain in
Office Connect. T3.4 now combines meeting creation with this separate room child
operation and must report calendar-success/room-failure without recreating meetings.

T3.4 adds [combined meeting/room intent and room-only recovery](TELEGRAM_MEETING_ROOMS.md). A failed parent receipt can prefill its existing meeting in this form after a fresh `/room_request`; the new preview and operation reference the parent. Source authority and revision checks still apply, and this room-only path never creates a meeting.
