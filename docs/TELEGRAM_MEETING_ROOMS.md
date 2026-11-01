# Guided meeting with a room request (T3.4)

Draft 9.61 adds a [private webhook guide/preview/confirmation/recovery flow](TELEGRAM_PRIVATE_MEETING_WEBHOOK.md). Direct/group worker behavior below remains available; deployment and live acceptance are separate.

Implementation: [meeting adapter](../telegram_meetings.py),
[room child coordinator](../telegram_meeting_rooms.py),
[room adapter](../telegram_room_requests.py),
[progress ledger](TELEGRAM_TWO_WAY_PLAN.md).
All pilots remain off by default. Merge and mocked tests are not hosted verification.

## Staff flow

1. Link with explicit `calendar.read`, `calendar.create`, `rooms.read` and
   `rooms.request` consent. Existing connections receive no new permissions;
   disconnect/relink if those choices were not included.
2. Send `/meeting` privately or in an approved exact group/topic. Open the
   signed-in guide. The optional room checkbox starts unchecked and appears
   only with the room permissions and pilots. Leaving it unchecked preserves
   calendar-only creation.
3. Choose the meeting's exact fields and, optionally, one continuous configured
   room block on the same date. Meeting and room clocks are separate choices.
   Room hours do not silently change the venue or meeting time.
4. Read the private preview: meeting participants/audience/date/time/duration,
   requested room hours/duration in Asia/Manila, pending approval/no hold, and
   the explicit instruction to keep the meeting if the room request fails.
   Send its `/meeting_confirm CODE` before the five-minute deadline.
5. The private receipt links the saved calendar entry and shows the room child
   operation and current request status. Requested means pending Administrative
   Section approval; approved means booked. The requester chooses new hours
   after a failure. No approval or change notification is sent automatically.

If a room business rule refuses the request after preview (for example a newly
approved competitor or closure), the meeting remains saved. Its parent receipt is
`partial / meeting_room_failed`; a separate room child is `failed /
room_unavailable`. No reason, title or identity from another reservation is copied
into the receipt. The source link and responsible next person are explicit.

For recovery use `/meeting_receipt OPERATION_ID`, even after token-row cleanup.
Replaying the original confirmation or resubmitting its form returns the original
outcome. It never retries the room or creates another meeting.

For a **fresh room-only attempt**, send `/room_request`, then open the signed-in
retry URL from the partial receipt. The original meeting number is prefilled and
cannot be changed for that parent intent. Select new hours, check the new private
room preview and use `/room_confirm CODE`. The new room operation references the
same parent and existing calendar entry; no calendar creation service runs. A live
requested/approved room link prevents a second request. The original parent
outcome remains historical; later receipt rendering also shows a successful
child's current room status. `/room_receipt CHILD_ID` can recover a child directly.

Deleted sources are reported neutrally and are never recreated. A cancelled,
changed or inaccessible source must pass the ordinary room eligibility and exact
revision checks before a fresh retry. The signed-in retry URL contains an opaque
operation identifier, not a credential; ownership and current source authority
are always checked. A new room origin and fresh confirmation are required.

## Authorization and transaction boundaries

Reuse all [meeting](TELEGRAM_MEETINGS.md) and [room](TELEGRAM_ROOM_REQUESTS.md)
configuration and current delegation checks. Both room read/request grants and
switches are additionally required for combined preparation, confirmation and
receipt disclosure. Group starts retain exact routing/generations and fresh
owner/bot/requester membership verification. Every field, preview and receipt is
private. This never grants group source sharing.

New preview issuance checks room dates, working days, holidays, horizon and known
conflicts before saving any business record. The signed preview binds configured
slot identities/labels/clocks as well as meeting fields. Changed slots or lost
consent invalidate confirmation before commit. Room availability can change after
preview: confirmation rechecks domain rules inside the writer transaction and
records a definite room refusal as a partial result, as explicitly previewed.

The existing parent writer creates the calendar entry/revision/audit/email outbox.
It adds a separate `rooms.request` child operation and attempts the existing
actor-aware request/link service under a SQLite savepoint. Success includes room
records, slots, link, audit and approver-notice outbox. A `rooms.RoomError` rolls
back only child business writes and preserves a safe failure receipt. Unexpected
exceptions, notice failures, revoked authority, elapsed expiry or receipt enqueue
failure roll back the entire confirmation. The engine consumes the parent preview
and queues one private parent receipt atomically with both durable outcomes.
No provider calls or commits run inside either mutation path.

The child has its own operation/key/hash/context and source/result IDs. Its
initial attempt is authorized by the parent's exact combined confirmation, so no
second token or preview is minted for that attempt. A fresh retry uses the
ordinary room preview/confirmation engine and a new child operation. Concurrent
parent confirmations serialize and recover the existing receipt without creating
another child. Ordinary restart preserves these identities. Snapshot rollback
still cannot guarantee exactly-once outcomes.

## Migration, retention, activation and rollback

Normal initialization adds nullable, indexed `parent_operation_id` referencing
`telegram_operation`; existing operations keep NULL. No new service, queue, grant
or switch is introduced. A new grant trigger scrubs pending combined previews
when room read/request consent is revoked; calendar-only previews retain their
independent permissions. Account/link/group/restore fences remain in force.

The existing five-minute preview, bounded cleanup, expiry-plus-24-hour token purge
and 180-day receipt-detail compaction also cover this flow. Parent/child identity
links remain with key/hash tombstones, without preview content. Restores retain
terminal parent/child receipts while pausing/revoking connections and cancelling
pending previews/deliveries. Receipt rendering rechecks current source and room
ownership/access, including child requests. No historical receipt restores access.

Keep switches off until deployed SHA, durable storage/snapshot recovery, canonical
HTTPS webhook ownership, Bot API egress and a synthetic private/group pilot are
verified. Test fresh combined consent, private exact preview, duplicate workers,
late room conflict, one saved meeting plus failed child, new room-only preview,
normal approval, source/grant revocation, restart and restore. Record actual live
evidence in the progress ledger; none is claimed here.

Disable calendar-create to pause new combined commits. Disable room-request/read
to pause room actions and suppress combined previews/receipts; this does not turn
a confirmed combined intent into calendar-only creation. Delivery/inbound remain
independently pausable. Keep additive metadata and restore fences during rollback;
never bulk replay historical confirmations or uncertain sends. Existing saved
meetings and ordinary room approvals remain managed in Office Connect.

T4.1 next adds durable calendar/room change events and routing. Automatic change
notices, reminders, natural-language parsing, recurrence, guests, meals, standby,
on-behalf-of requests and approval/cancel/withdraw actions are outside T3.4.

T4.1 adds [transactional source-change events and metadata-only routing](TELEGRAM_CHANGE_EVENTS.md). It does not deliver change notifications or replay business actions; T4.2 owns that transport handoff.

T4.2 adds [current permission-checked calendar and room change notices](TELEGRAM_CHANGE_NOTICES.md), with a separate default-off read/delivery pilot. Business confirmation/recovery semantics are unchanged; a notice never repeats an action.
