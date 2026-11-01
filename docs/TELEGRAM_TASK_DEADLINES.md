# Private internal task deadline changes

Draft PR #572, candidate 9.71. Deployment, preview publication, activation and
personal/live acceptance remain deferred. Synthetic local checks send no real
Telegram messages and use no production records.

## Guide and confirmation

| Step | Command |
| --- | --- |
| Open signed-in guide | `/task_deadline` |
| Retrieve prepared private preview | `/deadline_preview OPERATION_ID` |
| Confirm the exact preview | `/deadline_confirm TOKEN` |
| Recover recorded outcome | `/deadline_receipt OPERATION_ID` |

Separate `tasks.deadline` consent requires `work.read` and default-off host
switch `CSS_TELEGRAM_TASKS_DEADLINE_ENABLED`. Existing private inbound, link,
delivery, bot/account context and work/document modules must be available.
Group/topic and direct-worker paths cannot perform this action. Fresh menus
show it only when these prerequisites are available.

The phone form works without JavaScript. Enter permitted work/task IDs, choose
set/change with an exact date or explicitly clear with a blank date, and supply
a reason of at most 500 characters. A blank date alone is insufficient to clear.
Invalid dates, unchanged targets, unsupported fields and oversized previews are
refused. Reasons normalize CRLF to LF; they appear in Telegram and work history.

The signed-in form prepares only a five-minute preview. Retrieve it privately,
review the identified work/task, old and new deadline, status and reason, then
send its exact confirmation before expiry. The form itself changes no deadline.

## Existing source authority and effects

The concerned case officer or confirmed work lead must currently have the native
`milestone` action. Owning a task, proposing it or consenting to Telegram is
insufficient. Confirmation checks authority and source visibility again. Hidden
linked documents, completed/closed work and done/cancelled tasks are blocked.
The internal date cannot follow a linked official deadline. Official document
deadlines are never changed or cleared by this feature.

Confirmation calls the existing native task milestone service. It preserves
owner, progress, required status, expected output and submission while recording
the normal revision, work event, audit and native reminder effects. Active latest
uninvalidated formal consolidation review on a nonterminal document blocks the
bot amendment, including review started after preview. Amend those work items
in Office Connect so dependent approvals can be reviewed there.

Full work/task contents and linked document metadata are hashed for stale-source
checks; source submission/output contents are never projected into Telegram.
Work event history also fences changes that were later reverted. New or changed
source state requires a fresh preview. A revoked scope, source pause, restored
context, expired link or changed actor/chat/bot proof also prevents stale writes.

Native source effects, consumed preview, receipt and private reply handoff share
one transaction. Audit, receipt or handoff failure rolls everything back. Duplicate
and concurrent confirmation produces one milestone. Recovery rechecks current
source view/read access and reports the recorded outcome plus current state;
it never replays the write. Deleting the task cancels pending previews and clears
recorded targets so a reused numeric ID cannot expose or change a replacement.

This adds no assignment, acceptance, cancellation, official-date amendment,
scheduler or delivery activation. See the [pending live checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md).

## Reproduce isolated checks

Use Python 3.11 and `scripts/cloud_workspace.py test` as described in
[CLOUD_WORKSPACE.md](CLOUD_WORKSPACE.md). Focused files are
`tests/test_telegram_task_deadline.py` and
`tests/test_telegram_task_deadline_browser.py`. They cover native authority,
explicit clearing, stale/closed/hidden sources, formal-review preservation,
rollback, concurrent retries, deletion/ID reuse, scope controls and a 390-pixel
JavaScript-disabled form through private confirmation. Exact current results
are recorded in [SETUP_STATUS.md](SETUP_STATUS.md).
