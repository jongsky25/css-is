# Private task dependency management

Draft PR #572, candidate 9.74. Adding and removing prerequisites are implemented
for later activation. Deployment, preview publication, activation and personal/live
testing remain deferred. Automated checks use synthetic data and blocked providers.

## Commands and consent

| Step | Add a prerequisite | Remove a prerequisite |
| --- | --- | --- |
| Open signed-in form | `/task_dependency_add` | `/task_dependency_remove` |
| Retrieve exact preview | `/taskdepadd_preview OPERATION_ID` | `/taskdepremove_preview OPERATION_ID` |
| Confirm before expiry | `/taskdepadd_confirm TOKEN` | `/taskdepremove_confirm TOKEN` |
| Recover recorded outcome/current state | `/taskdepadd_receipt OPERATION_ID` | `/taskdepremove_receipt OPERATION_ID` |

Independent `tasks.dependency_add` and `tasks.dependency_remove` consents require
`work.read` and their respective default-off switches
`CSS_TELEGRAM_TASKS_DEPENDENCY_ADD_ENABLED` and
`CSS_TELEGRAM_TASKS_DEPENDENCY_REMOVE_ENABLED`. Current private inbound, link,
delivery, account, bot and original chat proof must still match. Group/topic and
direct-worker confirmation paths are refused. Read lookup and blocker-management
permissions grant neither dependency action; one action does not grant the other.

The signed-in JavaScript-free form requires exact work/dependent/prerequisite task
numbers and a bounded nonempty change reason (500 characters maximum, CRLF
normalized). Preparation changes no source record. Retrieve the five-minute exact
preview in the original private chat and check the direction, both task numbers,
titles, current statuses and consequences before confirming. The dependent task
requires the prerequisite task to be Done before submission or acceptance.
**Your entered reason appears in Telegram and normal source history.** Stored
submissions, expected outputs, blocker reasons and discussion contents are hashed
for source fencing where relevant; they are not projected into the private reply.

## Native rules and preserved state

Current native authority requires the confirmed work lead or a concerned case/task
officer, on an active dependent task in open work. Task ownership, follow-up
responsibility, a technical account role, visibility or Telegram consent alone
grants no coordinator authority. Both tasks must currently be readable in the
same work item. Selecting another work item or task grants no access.

Adding refuses self-dependencies, duplicate links, cancelled prerequisites and
cycles of any length. A Done prerequisite may be added; its already satisfied
state is explicit in the preview. Removing requires that the exact link currently
exists; an existing cancelled prerequisite can be removed. Each operation changes
one edge plus the dependent task revision and native work/audit history. The
prerequisite itself remains unchanged. Task ownership, progress, submission,
recorded blocker/follow-up fields, task deadlines and official document deadlines
stay unchanged. Other dependencies and changed-decision reviews remain effective.
No task is automatically completed, submitted or accepted. Removing the final
prerequisite can allow a later explicit submission only when all native guards
permit it.

Done/Cancelled dependent tasks and closed/completed work refuse amendments. Active
latest uninvalidated formal consolidation review on a nonterminal linked document
blocks bot amendments before or after preview; amend such work in Office Connect.
No approval, document access, membership or reminder is granted by this operation.

## Atomicity, stale previews and recovery

The adapter calls the existing `work_blockers.mutate_in_transaction` in the generic
confirmation transaction. Native access/authority/revision/cycle checks run again
at the write. The task, edge, event/audit, preview consumption, receipt and private
reply handoff commit together. Audit, receipt or handoff failure rolls back all.
Duplicate/concurrent confirmation records the change once.

Before confirming, the adapter revalidates the full dependent-task/work/linked-
document source digest, the complete prerequisite record and the same-work edge
graph. A changed graph without a task revision/event change is still refused.
Source history fences reverted native changes. Current source permissions, source
modules, scopes/pilots, expiry, connection generations and original context are
rechecked. Revocation, pause, disconnect and restore cannot revive stale actions.

An additive nullable `telegram_operation.dependency_task_id` tracks the selected
prerequisite for deletion/recovery; old operations remain unchanged. The migration
is idempotent and runs before triggers are installed. Deleting either task cancels
and scrubs pending previews. Target deletion clears both task pointers; prerequisite
deletion clears its pointer and marks the receipt, preventing numeric-ID reuse
from acting on or describing a replacement. Retained-key cleanup clears both
identifiers. Recovery requires current source view, reports the original outcome
and current edge/status or deletion, and never repeats the change. Later native
edge changes are reflected as current state without changing the recorded outcome.

## Verification and deferred acceptance

Use [isolated Python 3.11 commands](CLOUD_WORKSPACE.md). Focused coverage is in
`tests/test_telegram_dependency_manage.py` and
`tests/test_telegram_dependency_manage_browser.py`. It covers coordinator-only
permissions, source visibility, same-work direction/cycles, duplicate/missing links,
terminal/formal-review guards, strict input/current context, graph snapshots,
unchanged source fields, effective submission guards, atomic failures, retries,
concurrent confirmation, both task deletion/reuse paths, retention and recovery.
Two 390×844 JavaScript-disabled phone flows cover independent consent/menu/form
routing, CSRF/strict fields, invalid self-selection, exact preview/confirmation,
retry, retained task fields, expired sessions and no outgoing notifications.

The shared menu status now shortens repeated work-read prerequisite descriptions
while retaining each feature's availability and full missing action consent.
The existing schema-upgrade test removes the new trigger/column as well and
checks that old pending operations survive migration without acquiring a target.

Exact evidence is recorded in [SETUP_STATUS.md](SETUP_STATUS.md). All
[live acceptance rows](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md) remain Pending.
