# Private room withdrawal and date moves

Draft PR #572, candidate 9.64. Deployment, preview publication, activation and
live testing remain deferred. Automated checks use synthetic data and blocked
outgoing providers.

## Commands and permissions

| Action | Start | Retrieve prepared preview | Confirm | Recover |
| --- | --- | --- | --- | --- |
| Withdraw | `/room_withdraw` | `/withdraw_preview OPERATION_ID` | `/withdraw_confirm TOKEN` | `/withdraw_receipt OPERATION_ID` |
| Move date | `/room_move` | `/move_preview OPERATION_ID` | `/move_confirm TOKEN` | `/move_receipt OPERATION_ID` |

Both need current `rooms.read` plus their independent explicit consent:
`rooms.withdraw` or `rooms.move`. Host switches
`CSS_TELEGRAM_ROOMS_WITHDRAW_ENABLED` and `CSS_TELEGRAM_ROOMS_MOVE_ENABLED` default
off. Existing room-request/read consent grants neither action. Group/topic and
direct-transport actions are unavailable; private inbound/link/delivery controls
and the original linked account/bot proof must remain current.

Start privately, open the signed-in guide and enter your room reference from
`/my_rooms` or `/room_status` (the numeric ID also works). Moving additionally asks
for an exact new Manila date. The script-free form prepares a five-minute preview
without changing a booking. Retrieve the preview using its displayed operation
command, review every effect and send the exact private confirmation before expiry.

## Source behavior

- Withdrawing your own pending request marks it withdrawn. Withdrawing your own
  approved booking releases its held hours. Native source status is `withdrawn`.
- Withdrawing an original booking also withdraws its own pending move children;
  their references appear in the preview. Withdrawing only a pending move keeps
  the original approved booking held. Changed child/parent relationships require
  a fresh preview. Existing pending moves must be withdrawn before another move
  is prepared.
- Moving a pending request changes its date in place, retaining its original
  reference, hours and pending approval state. It holds no hours.
- Moving an approved booking files a new pending `move` request for the same
  hours. The old approved booking remains held until the normal Administrative
  Section approval. Approving the move through the existing source workflow
  releases the old booking (source status `withdrawn`) and books the new hours;
  bot confirmation cannot grant approval. Rejecting/withdrawing the move does
  not release the old booking.
- A calendar-linked move additionally needs current `calendar.read` and the
  canonical permitted-meeting policy. Its proposed date must match the meeting's
  current date. Update the meeting in Office Connect first. Neither action edits
  the calendar. New conflict/closure/inactive-hour checks still run at confirmation.

Only the actual signed-in requester can act; administrator visibility grants no
on-behalf-of authority. Guests, meal-linked forms (even if a stale meals flag is
off), series, standby, direct activity links and on-behalf-of requests stay in
Office Connect. Internal/encoded/approved-move records may be eligible when they
are otherwise plain, owned and currently pending/approved. There is no time-block
change, meal operation, approval, calendar edit or provider call in these actions.

## Atomicity, current state and recovery

The native `rooms.withdraw` and `rooms.request_move` support caller-owned
`commit=False`, preserving their normal default behavior. Transactional move-child
creation accepts only the same owner's plain approved booking, unchanged source
fields/slots/link and no existing pending move. The existing slot availability,
date horizon and approval rules remain authoritative.

Source rows/held slots, move child, audit, normal notice outbox, consumed preview
and operation receipt share one writer transaction. Transactional callbacks do
not swallow errors or commit independently; meals callbacks are excluded by the
plain-source guard. An audit, notice, late receipt, expiry or webhook handoff
failure must roll everything back, including retaining the original held booking.

Expected state hashes include current room data, slot definitions, pending move
children/parent and durable source incarnation/revision heads. Same-second
edit/revert and numeric-ID reuse cannot revive a preview. Linked moves also bind
the meeting revision. Read/write revocation, account changes, restore/disconnect,
expiry, new approval or newly occupied target hours prevent stale confirmation.
Revoking calendar read also cancels pending linked move previews.

Duplicate/concurrent confirmations return the recorded outcome, without a second
withdrawal or move. Receipts describe that outcome plus current request/original
booking state, so subsequent approval is distinguishable from initial submission.
The existing deletion/retention fences prevent recreation through recovery.
No automatic private push or uncertain-response retry is added. Normal room
notices follow existing preferences; this work activates no delivery switches.

The room forms reuse the same actor-bound CSRF, bounded allowlisted field,
rate-limit and current-session form implementation as meeting management, with
separate paths/templates/action bindings. Confirmation tokens stay private;
signed-in forms show operation IDs. Sensitive purpose/people/decision notes are
not projected in previews or receipts.

Synthetic checks cover pending/approved paths, normal approval after move,
withdrawal/child semantics, owner-only access including administrators, special
source blockers, changed/reverted records, scope/host/restore/expiry, target
conflicts, audit/notice/receipt/handoff rollback and concurrent confirmation.
Three actual 390×844 no-script browser flows test explicit scope consent, CSRF,
exact preview/confirmation, duplicate recovery and expired sessions. All later
hosted cases remain **Pending** in the [live checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md).
