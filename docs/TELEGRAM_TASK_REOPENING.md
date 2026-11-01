# Private reopening of accepted tasks

Draft PR #572, candidate 9.75. The owner requested the next feature after task
reassignment. Deployment, preview publication, activation and personal/live testing
remain deferred. Local checks use synthetic records and blocked providers.

## Commands and separate consent

| Step | Command |
| --- | --- |
| Start signed-in guide | `/task_reopen` |
| Retrieve exact private preview | `/taskreopen_preview OPERATION_ID` |
| Confirm before expiry | `/taskreopen_confirm TOKEN` |
| Recover outcome/current state | `/taskreopen_receipt OPERATION_ID` |

Independent `tasks.reopen` consent requires `work.read`, default-off switch
`CSS_TELEGRAM_TASKS_REOPEN_ENABLED`, work/document modules and current private
inbound/link/delivery/account/chat/bot proof. Other task consents grant no reopening
right. Group/topic and direct-worker paths cannot reopen tasks. Current menu and
consent choices respect the independent pilot.

The signed-in phone form works without JavaScript and takes permitted work/task
IDs plus a mandatory reason of at most 500 characters (CRLF normalizes to LF).
CSRF, strict field allowlists, bounded body and original signed-in private-origin
checks remain mandatory. Owner/date/submission fields cannot be supplied.

Preparing a form changes no task. Retrieve the five-minute private preview, check
the identified work/task, existing owner account, Done → In progress and reason,
then send the exact confirmation in the original private chat. The actor-entered
reason appears in Telegram and native history. Stored submission/expected-output
contents stay in Office Connect; review them there before reopening.

## Existing source authority and effects

The native concerned **case officer** or confirmed work lead must currently have
`reopen` authority for this Done task. Ownership or another Telegram permission
alone is insufficient. Proposed/To do/In progress/For review/Cancelled tasks cannot
be reopened by this action. The current owner must remain active and able to read
every linked document, both before preview and at confirmation. No owner/access
change is made.

Confirmation calls the existing native task reopening mutation. It returns Done
→ In progress for the same owner, records the normal revision/event/audit/reminder
effects and preserves title, expected output, submission, deadline, unit, required
status and original proposal. Existing pending changed-decision reviews and
unfinished prerequisites remain unresolved. Reopening can permit rework while
those remain; it never resolves them or bypasses subsequent native submission/
acceptance blockers. Normal resubmission and review are separate actions.

**This does not reopen a completed work case or an official document.** Reopen
completed work through its separate Office Connect workflow first. Closed legacy
work, hidden linked documents and active latest uninvalidated formal consolidation
review on a nonterminal linked document block the bot action. Review beginning
after preview also blocks it so dependent formal approvals remain unchanged.
Formal-review amendments stay in Office Connect.

Task/work/linked-document snapshots and append-only event history fence changed
or reverted source, including a task reopened and accepted again. Source contents
are hashed only. Current permissions, owner eligibility, source modules, pilots,
scopes, expiry and original account/chat/bot proof are checked again inside the
transaction. Lost lead/officer/access rights and restore/disconnect/revocation
cannot keep a preview valid.

## Atomic outcome and verification

Native source/event/audit/reminder effects, consumed preview, receipt and private
handoff share one transaction. Audit/receipt/handoff failure rolls everything back.
Repeated/concurrent confirmation reopens once. Recovery checks current source
view/read access and reports recorded outcome plus current state (including later
resubmission) without repeating the action. Task deletion cancels pending previews
and clears recorded targets, fencing numeric-ID reuse.

Reopening shares bounded fields, source snapshots and receipt routing with the
existing review adapter, with a distinct native action/result, scope and protocol.
Existing acceptance and return behavior remains covered by regression checks.
Expanded `/status` keeps every missing consent label while stating relinking
instructions once in its footer, preserving the Telegram message-size limit.

Use the Python 3.11 isolated commands in [CLOUD_WORKSPACE.md](CLOUD_WORKSPACE.md).
Focused files are `tests/test_telegram_task_reopen.py` and
`tests/test_telegram_task_reopen_browser.py`. Phone cases exercise both officer and
lead at 390×844 with JavaScript disabled, separate consent, exact preview/retry,
CSRF/strict fields, unchanged owner/submission/deadline and expired sessions.
Exact results are recorded in [SETUP_STATUS.md](SETUP_STATUS.md). All
[live acceptance cases](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md) remain Pending.
No provider registration, real message, scheduler or activation was added.
