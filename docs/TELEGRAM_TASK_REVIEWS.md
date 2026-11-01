# Private submitted-task acceptance and return

Draft PR #572, candidate 9.77. The owner approved adding review features before
deployment, preview publication, activation and personal/live testing. Those steps
remain deferred. Local verification uses synthetic accounts/records and blocked
outgoing providers.

## Commands and independent consent

| Step | Accept submitted task | Return for changes |
| --- | --- | --- |
| Start signed-in guide | `/task_accept` | `/task_return` |
| Retrieve exact preview | `/taskaccept_preview OPERATION_ID` | `/taskreturn_preview OPERATION_ID` |
| Confirm before expiry | `/taskaccept_confirm TOKEN` | `/taskreturn_confirm TOKEN` |
| Recover recorded outcome | `/taskaccept_receipt OPERATION_ID` | `/taskreturn_receipt OPERATION_ID` |

`tasks.accept` and `tasks.return` are independent consent scopes with separate
default-off switches `CSS_TELEGRAM_TASKS_ACCEPT_ENABLED` and
`CSS_TELEGRAM_TASKS_RETURN_ENABLED`. Each requires current `work.read`, available
work/document modules and the existing private inbound/link/delivery/account/bot
proof. Neither scope grants the other. Group/topic and direct-worker paths cannot
perform reviews. Current menus and consent choices respect the separate pilots.

Review the current submitted evidence in the signed-in Office Connect work page.
The no-script phone form takes work/task IDs and a mandatory reason (500 characters
maximum, normalized CRLF to LF). It only prepares a five-minute private preview.
Check the identified work/task, current and resulting status and reason, then
confirm that exact preview in its original private chat. The actor-entered reason
appears in Telegram and source history. Stored submission and expected-output
contents are never projected or replaced through this flow.

## Native review authority and effects

The concerned case officer or confirmed work lead must currently have the native
`accept` or `return` action. Ownership, task proposal, acknowledgement/submission
or Telegram consent alone grants no review authority. Only tasks currently For
review qualify. Acceptance moves the task to Done; return-for-changes moves it to
In progress for its existing owner. Native source rules are checked at preparation
and confirmation, including current account/contributor access during mutation.

Acceptance is refused while a recorded blocker, unfinished prerequisite or
unresolved changed-decision review exists. Return follows its native rule and can
request changes while those blockers remain; it does not clear or resolve them.
Any blocker/source change after preview requires fresh preparation. Completed/
closed work, hidden linked documents, lost officer/lead rights and changed source
state refuse confirmation. Active latest uninvalidated formal consolidation
review on a nonterminal document also blocks both actions, including review that
starts after preparation, preserving dependent formal approvals.

The existing native review mutation records status/revision and normal work
event/audit/reminder effects. It preserves owner, submission, expected output,
required status and deadlines. It does not complete the work case or approve,
release, close or change dates on an official document. Assignment, reassignment and
[accepted-task reopening](TELEGRAM_TASK_REOPENING.md) have independent workflows;
[task cancellation](TELEGRAM_TASK_CANCELLATION.md) has its own officer workflow.

Full task/work state, linked document metadata and append-only work-event history
fence stale/reverted previews. Submission contents are hashed only. Current native
blockers and permissions are rechecked as well. Strict allowlisted form fields,
CSRF, expiry, original actor/account/chat/bot proof and current pilots/scopes remain
mandatory. Cross-action commands cannot consume another review's token.

Native effects, preview consumption, receipt and final private reply handoff share
one transaction. Audit, receipt or handoff failure rolls everything back. Repeated
and concurrent confirmation changes one task once; a pending opposite review
cannot reverse a confirmed outcome. Recovery checks current read/source view,
reports recorded outcome and current status and never replays the action. Task
deletion cancels pending review previews and clears receipt targets so numeric-ID
reuse cannot expose or mutate a replacement task.

## Verification and deferred acceptance

Use `scripts/cloud_workspace.py test` under the Python 3.11 isolated environment
from [CLOUD_WORKSPACE.md](CLOUD_WORKSPACE.md). New focused files are
`tests/test_telegram_task_review.py` and
`tests/test_telegram_task_review_browser.py`; the latter exercises both reviews at
390×844 with JavaScript disabled, separate consent, CSRF/strict fields, exact
private confirmation/retry and expired sessions. Provider calls are blocked.

Exact current verification is in [SETUP_STATUS.md](SETUP_STATUS.md). All
[live acceptance cases](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md) remain Pending.
No scheduler, provider registration, real message or automatic delivery activation
was added. Main is production-connected; this feature remains on the draft branch.

Use the separately consented [private review queue](TELEGRAM_REVIEW_QUEUE.md) to
find currently eligible submitted tasks and their work/task IDs. Reading the queue
creates no preview or review decision and grants no accept/return authority.
