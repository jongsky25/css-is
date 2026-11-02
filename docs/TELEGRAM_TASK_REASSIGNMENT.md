# Private officer task reassignment

Draft PR #572, candidate 9.79. The owner requested the next feature after initial
assignment. Deployment, preview publication, activation and personal/live testing
remain deferred. Local verification uses synthetic records and blocked providers.

## Commands and separate consent

| Step | Command |
| --- | --- |
| Start signed-in guide | `/task_reassign` |
| Retrieve exact private preview | `/taskreassign_preview OPERATION_ID` |
| Confirm before expiry | `/taskreassign_confirm TOKEN` |
| Recover outcome/current state | `/taskreassign_receipt OPERATION_ID` |

Independent `tasks.reassign` consent requires `work.read`, default-off switch
`CSS_TELEGRAM_TASKS_REASSIGN_ENABLED`, source work/document modules and existing
private inbound/link/delivery/account/chat/bot proof. Initial `tasks.assign`
consent does not permit transfer. Group/topic and direct-worker paths cannot
transfer tasks. Current consent choices and menus respect the separate pilot.

The no-script signed-in phone form takes permitted work/task IDs, an explicitly
selected different active owner and a mandatory reason of at most 500 characters
(CRLF normalizes to LF). The active-account directory starts blank; the task's
current or proposed owner is not silently selected. Eligibility for every linked
document is checked after selection and again at confirmation. CSRF, exact field
allowlists, bounded body and current signed-in origin checks remain mandatory.

Preparation changes no task. Retrieve the five-minute private preview, check
work/task/unit, old owner account, new selected name/account, current status,
unchanged deadline and reason, then send the exact confirmation in the original
private chat. The selected account and reason appear in Telegram/source history.
Submission and expected-output contents stay in Office Connect.

## Native transfer behavior and limits

**Reassignment returns the task to To do for the new owner**, including tasks
previously In progress or For review. This is explicit in the form and preview.
The existing submission is preserved for source history and further work; review
it in Office Connect before transferring. Reassignment does not acknowledge,
submit or accept the task, resolve blockers, complete the work or approve a document.

Only the native concerned officer over the **task's contributing unit** may
transfer a To do, In progress or For review task. Work-lead, task-owner or technical
admin role alone grants no officer authority. Native hierarchical/director/seat
rules remain authoritative. Proposed tasks use initial assignment; Done/Cancelled
tasks cannot be transferred through this feature. Same-owner selection is refused.

The selected active person must already read **every linked document**. No
document permissions are granted. Ownership follows native work membership rules:
the new owner gains normal task membership while the old owner retains only
whatever independent source rights they still have. Source document intersections
remain enforced.

The existing native `reassign` mutation changes owner/status/revision and records
normal event/audit/reminder effects. It preserves title, expected output, existing
submission, deadline, contributing unit, original proposal, required status and
recorded blocker/follow-up/dependency/changed-decision information. A blocker can
remain while work is transferred; acceptance/submission still require their own
native checks. Original deadlines are validated against linked official dates;
use the independent deadline workflow to change one.

Completed/closed work, hidden documents, lost officer or new-owner access,
inactive/renamed/changed selected accounts, changed task/submission/source and
stale/reverted history block confirmation. Active latest uninvalidated formal
consolidation review on a nonterminal linked document blocks amendments before or
after preview so dependent formal approvals remain unchanged. Use Office Connect
for those larger amendments.

Initial assignment and transfer share current identity/access/source-snapshot/
receipt routing, with separate native actions, results, protocols and pilots.
Source task/work contents and linked document metadata are hashed only; event
history also fences reverted changes. Current source permissions, native owner/
deadline rules, scopes/pilots, expiry and original account/chat/bot proof are
checked again inside the confirmation transaction.

## Atomic recovery and verification

Native effects, consumed preview, receipt and final private reply handoff share
one transaction. Audit/receipt/handoff failure rolls back. Duplicate/concurrent
confirmation transfers once; a competing pending choice cannot transfer the
updated task again. Deletion cancels previews and clears targets, fencing reused
numeric IDs. Recovery checks current read/source view and reports recorded outcome
plus current owner/status, including later source changes, without replaying.

Run `scripts/cloud_workspace.py test` using the Python 3.11 isolated environment
from [CLOUD_WORKSPACE.md](CLOUD_WORKSPACE.md). Focused files are
`tests/test_telegram_task_reassign.py` and
`tests/test_telegram_task_reassign_browser.py`. Phone checks exercise In progress
and For review at 390×844 with JavaScript disabled, explicit blank owner selection,
visible reset warning, CSRF/strict fields, exact confirmation/retry, preserved
submission/document permissions and expired sessions. Initial assignment behavior
is checked alongside the shared-adapter changes.

Exact results are recorded in [SETUP_STATUS.md](SETUP_STATUS.md). All
[live acceptance cases](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md) remain Pending.
No scheduler, provider registration, real message or activation was added.
Reopening/cancellation and amendments under active formal review remain separate.
