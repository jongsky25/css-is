# Private blocker recording and clearing

Draft PR #572, candidate 9.74. The owner explicitly approved recording and clearing
task blockers. Deployment, preview publication, activation and personal/live testing
remain deferred. Local checks use synthetic records and blocked outgoing providers.

## Commands and independent consent

| Step | Record a new blocker | Clear a recorded blocker |
| --- | --- | --- |
| Start signed-in form | `/task_block` | `/task_unblock` |
| Retrieve exact private preview | `/taskblock_preview OPERATION_ID` | `/taskunblock_preview OPERATION_ID` |
| Confirm before expiry | `/taskblock_confirm TOKEN` | `/taskunblock_confirm TOKEN` |
| Recover outcome/current state | `/taskblock_receipt OPERATION_ID` | `/taskunblock_receipt OPERATION_ID` |

Independent `tasks.block` and `tasks.unblock` consent each require `work.read`,
available work/document modules, current private inbound/link/delivery/account/
chat/bot proof and their default-off switches `CSS_TELEGRAM_TASKS_BLOCK_ENABLED`
and `CSS_TELEGRAM_TASKS_UNBLOCK_ENABLED`. Metadata lookup or another task consent
grants neither write; one write scope does not grant the other. Group/topic and
direct-worker paths cannot apply these actions.

No-script phone forms take permitted work/task IDs and a mandatory reason of at
most 500 characters (CRLF normalizes to LF). Recording also requires an explicitly
selected active follow-up person and exact date. Date is a follow-up target,
not a change to the task or official deadline. The directory starts blank; source
eligibility/selection rules are checked after selection and at confirmation.
Clearing queries no person directory and accepts no follow-up/date fields.

Preparation changes no blocker. Retrieve the five-minute private preview, check
the work/task/current state, exact entered reason and (when recording) selected
name/account/date, then confirm in the original private chat. **Your entered
blocker/resolution reason appears in Telegram and normal work history.** A clearing
preview does not copy the stored old blocker reason into Telegram; review its
current details in Office Connect first. The complete source snapshot still fences
changed/reverted blockers, submissions, work and linked documents.

## Native authority and supported changes

Current native blocker authority must permit the action on an active task in
open work. Task owners and current follow-up owners can participate; case leads
and concerned case/task officers can coordinate. A noncoordinator participant may
select only themselves in this new-recording flow. Coordinators may choose another
eligible person. Technical account role, visibility or Telegram consent alone
grants no source mutation authority.

The selected person must already be active, read the work case and every linked
document. Follow-up assignment grants no membership or document access. Current
account/display-name/source rights are rechecked. Clearing preserves the native
ability to resolve a blocker even if its former follow-up/task owner is inactive;
the acting user's own authority and source view must remain valid.

Recording is supported **only when no blocker is currently recorded**; it never
silently overwrites one. Amend an existing blocker in Office Connect or separately
clear it before recording a replacement. Clearing requires a current recorded
blocker and removes its reason/follow-up owner/date, with the entered resolution
retained in normal history. Old source history remains unchanged.

Task owner, state, submission/output, task deadline, unit/required/proposal fields,
dependency edges and changed-decision history stay unchanged. Clearing this one
blocker does not satisfy prerequisites, resolve changed direction or automatically
permit submission/acceptance. Native downstream checks still apply. Completed/
closed work and Done/Cancelled tasks refuse changes. Active latest uninvalidated
formal consolidation review on a nonterminal linked document blocks bot amendments,
including review begun after preview, so dependent approvals remain unchanged.
Amend such work in Office Connect.

## Atomic native mutation and recovery

`work_blockers.mutate` retains its existing public transaction wrapper and source
behavior. Its extracted `mutate_in_transaction` requires an active caller-owned
transaction and performs the same native authority/access/revision/event/audit
logic. The Telegram adapter calls that entry point inside the generic confirmation
transaction. Native source effects, consumed preview, receipt and private reply
handoff therefore commit together; audit/receipt/handoff failure rolls back all.
No native business rule was relaxed.

Duplicate/concurrent confirmation changes one blocker once. Current scopes/pilots,
source modules, role/view/follow-up permissions, expiry and original context are
rechecked. Revocation/disconnect/restore and changed task/blocker/account/source
state refuse stale confirmation. Deletion cancels pending previews and clears
receipt targets, fencing numeric-ID reuse. Recovery checks current source view
and reports recorded outcome/current blocker flag without replaying the change or
revealing stored blocker text, including later source blocker changes.

## Verification and deferred acceptance

Use the Python 3.11 isolated commands in [CLOUD_WORKSPACE.md](CLOUD_WORKSPACE.md).
Focused files are `tests/test_telegram_blocker_manage.py` and
`tests/test_telegram_blocker_manage_browser.py`. Source checks cover participant/
coordinator restrictions, existing membership/document eligibility, no overwrite/
no-op, state/formal-review/current-context guards, unchanged dependencies and
pending direction with blocked resubmission, rollback/concurrent/deletion/receipt
behavior and the strict native caller-owned contract. Two 390×844 JavaScript-
disabled phone cases exercise separate recording/clearing consent, owner-only
follow-up selection, CSRF/strict fields, exact preview/retry, retained task state/
deadline/submission, no outgoing delivery and expired sessions.

Exact results are in [SETUP_STATUS.md](SETUP_STATUS.md). All
[live acceptance cases](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md) remain Pending.
No provider registration, real message, scheduler or activation was added.
