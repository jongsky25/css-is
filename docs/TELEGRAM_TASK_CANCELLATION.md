# Private officer cancellation of unfinished tasks

Draft PR #572, candidate 9.78. The owner explicitly requested task cancellation.
Deployment, preview publication, activation and personal/live testing remain
deferred. Local checks use synthetic records and blocked outgoing providers.

## Commands and independent consent

| Step | Command |
| --- | --- |
| Start signed-in guide | `/task_cancel` |
| Retrieve exact private preview | `/taskcancel_preview OPERATION_ID` |
| Confirm before expiry | `/taskcancel_confirm TOKEN` |
| Recover outcome/current state | `/taskcancel_receipt OPERATION_ID` |

Independent `tasks.cancel` consent requires `work.read`, default-off switch
`CSS_TELEGRAM_TASKS_CANCEL_ENABLED`, source work/document modules and current
private inbound/link/delivery/account/chat/bot proof. Other task consents grant
no cancellation authority. Group/topic and direct-worker paths cannot cancel.
Menus and consent choices respect the separate pilot.

The signed-in no-script phone form takes permitted work/task IDs and a mandatory
reason of at most 500 characters (CRLF normalizes to LF). CSRF, strict allowlisted
fields, bounded body and original signed-in private-origin checks remain enforced.
Owner, date and submission fields cannot be supplied.

Preparing the form changes no task. Retrieve the five-minute preview, review the
identified work/task/unit, required/optional flag, retained owner account, current
state → Cancelled, reason and contribution/dependency effects, then confirm
exactly in the original private chat. The reason appears in Telegram and normal
source history. Stored submission/output contents stay in Office Connect; review
them and task dependencies there before cancelling.

## Source authority and consequences

Only the native concerned officer over the **task's contributing unit** may
cancel a Proposed/To do/In progress/For review task. Work-lead, task-owner or
technical-admin role alone grants no cancellation authority. Native hierarchical/
director/seat rules remain authoritative. Done and already-Cancelled tasks cannot
be cancelled. Completed/closed work must follow its separate source workflow.

**Cancelled tasks are excluded from outstanding-contribution checks, including
required contributions.** Cancellation does not accept output. Dependent tasks
requiring this task's acceptance remain blocked; existing dependency edges are
not removed. Work completion, official release and document cancellation remain
separate source decisions. This action does not delete the task or complete/cancel
the work case. Cancelled tasks cannot use the Done-task reopening command.

The existing native `cancel` mutation records Cancelled state, revision and normal
event/audit/reminder effects. Owner fields, deadline, title/output/submission,
unit, required status, original proposal and prior history remain preserved.
Recorded blockers/follow-up and changed-decision history are retained. Cancellation
can close an unassigned proposal or a task whose owner is inactive/lacks document
access: native cancellation intentionally does not require owner eligibility.
The actor still needs current source/document view and officer authority. No
access is granted. Normal membership applies, so a former owner without another
source right may lose work access when their contribution is cancelled.

Active latest uninvalidated formal consolidation review on a nonterminal linked
document blocks bot amendments, including review begun after preview, preserving
dependent approvals. Amend such work in Office Connect. Hidden documents, changed
source/submission/work/history, lost officer rights, source pauses and expired/
revoked/restored contexts refuse stale confirmation. Task/work and linked-document
contents are hashed only; append-only event history also fences reverted changes.
Current scopes/pilots and original actor/account/chat/bot proof are rechecked.

## Atomic recovery and verification

Native source/event/audit/reminder effects, consumed preview, receipt and private
handoff share one transaction. Audit/receipt/handoff failure rolls everything
back. Duplicate/concurrent confirmation records one cancellation. Task deletion
cancels pending previews and clears receipt targets, fencing numeric-ID reuse.
Recovery checks current source view/read and reports the recorded outcome plus
current state without repeating the action.

Cancellation shares bounded reason fields, source snapshots and receipt routing
with task review, using its own native action/result/scope/protocol. Existing
review and reopening behavior remain covered. No native task/work service was
changed.

Use the Python 3.11 isolated commands in [CLOUD_WORKSPACE.md](CLOUD_WORKSPACE.md).
Focused files are `tests/test_telegram_task_cancel.py` and
`tests/test_telegram_task_cancel_browser.py`. The 390×844 JavaScript-disabled phone
cases cancel an unassigned proposal and a submitted task with separate consent,
visible contribution/dependency warnings, CSRF/strict fields, exact private
confirmation/retry, retained owner/submission/deadline and expired sessions.
Exact results are in [SETUP_STATUS.md](SETUP_STATUS.md). All
[live acceptance cases](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md) remain Pending.
No scheduler, provider registration, real message or activation was added.
