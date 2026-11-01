# Private officer-confirmed initial task assignment

Draft PR #572, candidate 9.76. The owner approved adding initial task assignment
before deployment, preview publication, activation and personal/live testing.
Those steps remain deferred. Local checks use synthetic accounts/documents and
blocked outgoing providers.

## Guide and independent consent

| Step | Command |
| --- | --- |
| Start signed-in guide | `/task_assign` |
| Retrieve exact private preview | `/taskassign_preview OPERATION_ID` |
| Confirm before expiry | `/taskassign_confirm TOKEN` |
| Recover recorded outcome | `/taskassign_receipt OPERATION_ID` |

The separate `tasks.assign` consent requires `work.read` and default-off switch
`CSS_TELEGRAM_TASKS_ASSIGN_ENABLED`, available work/document modules and existing
private inbound/link/delivery/account/bot proof. Task proposal, deadline,
acknowledgement, submission and review consents grant no assignment authority.
Group/topic and direct-worker paths cannot assign. Current menu and consent
choices respect the independent pilot.

The no-script phone form takes permitted work/task IDs, an explicitly selected
active owner and a mandatory reason of at most 500 characters (CRLF normalizes
to LF). The directory starts with a blank choice; the proposed owner is never
automatically confirmed. The directory follows the existing active-account work
form choices; linked-document eligibility is checked after selection. Only the
supported fields are accepted, with CSRF and current signed-in origin checks.

Preparing the form changes no assignment. Retrieve the five-minute private
preview, check the work/task, contributing unit ID, suggested account ID, selected
name/account ID, unchanged deadline, Proposed → To do and reason, then send its
exact confirmation in the original private chat. The selected account and reason
appear in Telegram and normal source history. Stored expected-output/submission
contents stay in Office Connect.

## Native officer and contributor rules

The actor must currently have the native `confirm` action for this proposed task:
concerned officer authority covers the **task's contributing unit**. Work-lead,
creator/proposer or suggested-owner status alone is insufficient. An officer for
the work case's unit also needs authority over a different contributing unit.
Existing native hierarchical/director/seat authority remains authoritative.

The selected active person must already have access to **every linked document**.
Missing or revoked access blocks preparation or confirmation. This action grants
no document permissions. Once confirmed, ownership participates in normal work
membership/visibility rules; it does not bypass linked-document intersections.
A proposal is a suggestion: the officer may explicitly confirm a different
eligible person. The original proposed-owner field remains part of source history.

Confirmation calls the existing native task `confirm` mutation. It assigns that
person and moves Proposed → To do with one revision and normal work event/audit/
reminder effects. It preserves the task deadline, title, output, submission,
contributing unit and required status. Native official-date validation is repeated
for the existing deadline. Use the separate deadline workflow to change a date.
It does not acknowledge, submit, accept, complete the work case or approve an
official document. Reassignment has its own [private officer workflow](TELEGRAM_TASK_REASSIGNMENT.md);
reopening/cancellation remain separate source actions.

Completed/closed work, hidden linked documents, a task already assigned or no
longer proposed, inactive/renamed/changed selected accounts, lost task-unit officer
rights and changed source state refuse stale confirmation. Active latest
uninvalidated formal consolidation review on a nonterminal linked document blocks
the bot amendment before or after preview, preserving dependent formal approvals.
Amend those cases in Office Connect.

Full source task/work and linked document metadata plus append-only event history
fence stale/reverted previews; the selected account snapshot includes its displayed
name and identity. Source contents are hashed only, not projected into Telegram.
Current contributor/document permissions, native deadline rules, officer rights,
scopes/pilots, expiry and original account/chat/bot proof are rechecked inside the
confirmation transaction. Restore/disconnect/revocation cannot keep a preview alive.

## Atomic outcome and recovery

Native source/event/audit/reminder effects, consumed preview, receipt and private
reply handoff share one transaction. Audit, receipt or handoff failure rolls back.
Repeated/concurrent confirmation assigns once. Another pending preview selecting
a different owner cannot reassign the now-confirmed task. Recovery checks current
source view/read access and reports recorded outcome, current owner account and
status without replaying assignment, including later source reassignment.
Deleting a task cancels its pending previews and clears receipt targets, fencing
numeric-ID reuse from displaying or assigning a replacement task.

## Verification and deferred acceptance

Use the Python 3.11 isolated commands in [CLOUD_WORKSPACE.md](CLOUD_WORKSPACE.md).
Focused files are `tests/test_telegram_task_assign.py` and
`tests/test_telegram_task_assign_browser.py`. The 390×844 JavaScript-disabled
phone flow checks explicit selection, separate consent, missing-owner access
refusal, strict fields/CSRF, unchanged source permissions, exact confirmation/
retry and expired sessions. A separate source access decision in the synthetic
fixture illustrates that the bot grants no document access.

Current exact verification is recorded in [SETUP_STATUS.md](SETUP_STATUS.md).
All [live acceptance cases](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md) remain Pending.
No scheduler, provider registration, real message, Telegram activation or production
publication was added. The feature remains on the draft review branch.
