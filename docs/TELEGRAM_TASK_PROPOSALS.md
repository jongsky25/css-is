# Private guided task proposals

Draft PR #572, candidate 9.71. The owner requested the next feature while keeping
deployment, preview publication, activation and personal/live testing deferred.
Automated verification uses isolated synthetic work/documents/accounts and blocked
outgoing Telegram providers.

## Commands and consent

| Step | Command |
| --- | --- |
| Start the signed-in guide | `/new_task` |
| Retrieve the exact prepared preview | `/newtask_preview OPERATION_ID` |
| Confirm that preview before expiry | `/newtask_confirm TOKEN` |
| Recover the recorded outcome | `/newtask_receipt OPERATION_ID` |

The new `tasks.create` consent is independent of task acknowledgement/submission
and requires current `work.read`. Host switch `CSS_TELEGRAM_TASKS_CREATE_ENABLED`
defaults off; work/document modules and the existing read/inbound/link/delivery
pilots must also be available. Private webhook transport and the original active
account/chat/bot proof are required. Group/topic and direct requests cannot create
tasks. A paused source module hides and refuses guides as well as confirmations.

Start privately and open the signed-in form. Choose an existing permitted work
number, title (160 characters), expected output (1,000 characters), contributing
unit, optional proposed owner and optional exact Manila deadline. Blank unit uses
the work's unit. The directory/unit choices match the native work form. Multiline
output normalizes CRLF to LF; other control characters are refused. Oversized
UTF-16 previews require a shorter description or the normal Office Connect form.
The form explicitly says these actor-entered fields will appear in Telegram.

The form only prepares a five-minute private preview. It changes no task. Retrieve
the displayed operation, review the work/title/output/unit/proposed-account/date
and send the exact confirmation before expiry. IDs and selected labels identify
the choices; unknown/inaccessible work receives the same denial without its title.

## Native proposal and assignment rules

Confirmation uses `work_tasks.create_in_transaction` to create one **required**
contribution in **proposed** state, with `owner_id=NULL`. Choosing a proposed
owner is a suggestion, not assignment or document access. The concerned officer
must confirm assignment through the existing source workflow or the separately
consented [private officer assignment flow](TELEGRAM_TASK_ASSIGNMENT.md). Neither this
scope nor the confirmation token grants officer authority, acknowledgement,
submission, acceptance or official document approval.

Current work visibility is the intersection with linked document permissions.
Completed work and closed/cancelled legacy mappings remain blocked. A contribution
deadline cannot follow a linked official deadline. Native officer assignment still
checks that an eventual owner can read every linked document; proposing someone
does not grant access. A new required contribution can require the work review to
be done again and participates in normal source completion rules. Active latest,
not-yet-invalidated consolidation review packets on nonterminal documents block
bot proposals: native creation could invalidate their dependent approvals, so
those larger amendments stay in Office Connect. The block is checked again at
confirmation, including review started after preview. The supported proposal path
does not change an official deadline or advance/reset a formal approval.

The receipt reports the created task/work IDs and current source status, then
links to `/work_status` and the signed-in work page. It avoids an own-task detail
command that would deny an unassigned proposal. After actual officer assignment,
recovery can report the new status without creating or assigning anything again.

## Current authority, transactions and recovery

Expected state binds the current work row, linked document identities/revisions/
deadlines, latest append-only work event, chosen unit and proposed account labels/
state. Source access, writable/open state and native deadlines are checked again
inside the confirmation transaction. Changes, account deactivation/rename,
revocation, pilot pause, expiry and restore/disconnect stop stale proposals.

The native task row, work event/audit/review invalidation, consumed preview and
operation receipt share one writer transaction and private reply savepoint. Audit,
late receipt, handoff or expiry failures must roll back the task and review effects.
Duplicate/concurrent confirmations recover one operation. The retained receipt
routes to the original work/task; a task-delete trigger clears its numeric target
before ID reuse, so recovery reports deletion and cannot display a replacement or
recreate the old task. Existing acknowledgement/submission preview endpoints
explicitly reject proposal previews rather than interpreting their different shape.

The shared no-script form retains current-session/actor/CSRF, single-valued
allowlisted fields, rate limits and a bounded 20 KB body (large enough for encoded
Unicode output). Raw confirmation tokens appear only in the original private
reply. Pending preview fields are scrubbed on consumption/cancellation/expiry;
delivery/update descriptors retain no task body. Native source history keeps its
normal records. No new table, external provider, dependency or scheduler is added.

Synthetic cases cover proposal-only state, native officer confirmation, no access
grant, official deadlines, hidden work/document intersections, invalid/Unicode/
multiline input, current source/pilot/account/restore fences, concurrency, atomic
failures, deletion/ID reuse and cross-protocol denial. A real 390×844 JavaScript-
disabled flow consents separately, submits the form, retrieves the visible exact
preview, confirms twice and verifies one unassigned proposal plus CSRF/session
denials. Later hosted/user acceptance stays **Pending** in the
[live checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md).
