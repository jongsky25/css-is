# Private meeting rescheduling and cancellation

Draft PR #572, candidate 9.70. The owner is adding features before personal/live
testing. Deployment, preview publication, host activation and real messages remain
deferred. Local automated verification uses synthetic records and blocked providers.

## Commands and consent

| Action | Start | Retrieve prepared preview | Confirm exact preview | Recover outcome |
| --- | --- | --- | --- | --- |
| Reschedule | `/meeting_reschedule` | `/reschedule_preview OPERATION_ID` | `/reschedule_confirm TOKEN` | `/reschedule_receipt OPERATION_ID` |
| Cancel | `/meeting_cancel` | `/cancel_preview OPERATION_ID` | `/cancel_confirm TOKEN` | `/cancel_receipt OPERATION_ID` |

Each action needs existing `calendar.read` plus its own explicit checkbox:
`calendar.reschedule` or `calendar.cancel`. Separate host switches
`CSS_TELEGRAM_CALENDAR_RESCHEDULE_ENABLED` and `CSS_TELEGRAM_CALENDAR_CANCEL_ENABLED`
default off. Existing meeting-create consent grants neither new action. Private
webhook replies and inbound/link/delivery controls are required; direct transport
and group/topic requests cannot use these actions. Current menus/status reflect
the new independent consent and pilot conditions.

1. Start the action in the original linked private chat.
2. Open its signed-in guide. Enter the meeting entry number from its calendar URL.
   Rescheduling additionally asks for an exact Manila date and same-day start/end
   times; cancellation identifies the exact record without deleting it.
3. The script-free phone form prepares a five-minute preview. No meeting changes
   yet. Send the displayed preview-retrieval command in the original private chat.
4. Review the existing date/time/status and exact proposed change, then send the
   confirmation shown before expiry. Recovery reports the recorded outcome and
   current source state; it cannot repeat the write or recreate a deleted meeting.

## Supported source records and limits

These actions are creator-only, even if a participant or administrator can view
someone else's meeting. The source must be a live, one-day, non-recurring native
meeting. Imported, activity-linked, recurring/skipped-date, multi-day and already
cancelled meetings stay in Office Connect. Meetings with managed Google Meet
links or online/hybrid entries requiring relay creation also stay in the source
workflow. No provider call occurs inside the bot action transaction.

An active linked room request or approved booking blocks either action, including
when that link was added after preview. Manage the booking in Office Connect
first. This increment does not move/withdraw a room request, release approved hours,
cancel meals or change another requester's booking. Independent room management
can be scoped later; existing `/room_request` creation/approval semantics remain.

Rescheduling changes only date/start/end times, preserving status, title, audience,
participants, notes and other source fields. The editor's normal seen-sequence
marker can advance. Cancellation uses the source soft-cancel operation and retains
the record and cancellation revision. Normal source calendar change notices are
queued under existing channel/quiet-hour controls; previewing sends no notice and
this work does not activate any delivery switch or add a scheduler.

## Transaction and lifecycle guarantees

The existing actor-bound action engine rechecks account, original sender/chat,
bot proof, link generation, current read/write consent and host controls. Preview
source identity includes the full entry hash and latest source revision ID,
preventing same-second edits/reverts from reviving an old preview. Source edits,
room links, role changes, revoke/disconnect/restore and expiry block confirmation.
The generic read-grant revocation trigger cancels these pending previews too.

Calendar update/cancel storage functions accept caller-owned `commit=False` while
retaining existing default commit behavior. `BEGIN IMMEDIATE` covers fresh source
checks, source revision/outbox/audit, consumed preview and operation receipt. A
savepoint also covers final private reply rendering. Failed audit, late receipt,
expiry or webhook handoff must roll back the source change; uncertain accepted
responses are never replayed automatically. Duplicate/concurrent confirmations
return one recorded operation without a second edit.

The signed-in form checks current session, CSRF, an allowlisted bounded body,
single-valued fields, original action context and rate limits. Browser query
parameters cannot substitute another actor or action. Raw confirmation tokens
appear only in the original private reply; signed-in forms display operation IDs.

Synthetic checks cover both native source transitions and script-free 390×844
browser consent/form/preview/confirmation flows, visibility/creator and unsupported
source blockers, current grant/host fences, stale/reverted revisions, concurrency,
audit/late receipt/handoff rollback, restore/deletion and no outbound calls.
The [later live checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md) remains Pending.
