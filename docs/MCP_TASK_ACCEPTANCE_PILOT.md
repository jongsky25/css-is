# Confirmed-lead task acceptance pilot (v8.97)

M4.1 adds `get_task_acceptance_context`, `prepare_task_acceptance` and
`get_task_acceptance_operation`, disabled by default. It follows
[PR #508](https://github.com/jongsky25/css-is/pull/508), merge
`061dc6f4bd2f722e9a598e0e08d7af357872ab71`. Hosted decision acceptance remains
pending; implementation does not authorize activating this pilot for staff.

## Exact decision and separation of duties

This pilot lets the **currently confirmed work-item lead** accept another
person's exact canonical For review contribution as Done. It does not complete
the work item, approve/close an official document, return/reassign/cancel work,
sign/dispatch a document, or post stock/financial transactions. No evidence URL
is fetched or automatically verified. The human lead reviews the saved output
and any underlying evidence through normal trusted channels before confirming.

Separate optional `work:task:accept` consent, `CSS_MCP_ENABLED=1`, independent
`CSS_MCP_TASK_ACCEPTANCES_ENABLED=1`, current active session/account, ordinary
work/document readership and the current confirmed lead assignment are required.
The documents and shared-work modules must be enabled and the work item open.
Existing read/acknowledge/submit grants never widen into decision authority.

The assigned owner and actual submitting actor cannot accept their own
contribution. An officer can submit on an owner's behalf in the normal UI, but
cannot then accept that submission through this pilot. Technical administration,
officer rank and proposed lead status alone are insufficient. This is deliberately
narrower than the existing ordinary officer/lead action menu; that UI/API policy
is unchanged. An administrator who is separately confirmed as lead still must
meet the same separation, visibility, state and exact-review conditions.

The task must have retained native `task_proposed` and `task_submit` history.
Latest submitted revision/status/owner/output must exactly match the current task.
The assigned owner and submitting actor must remain active; the owner must retain
access to all linked documents. Imported tasks without that native origin or
unverifiable history use ordinary Work. Current blockers, unfinished prerequisites,
pending changed-decision reviews, completed/closed work or legacy-source locks
block acceptance through the existing service.

A later normal milestone/blocker change can increment the task revision without
creating a new submission. This pilot then requires a renewed canonical
submission through ordinary Work; a new MCP preview cannot silently accept output
from an older submission revision. No force/override input is provided.

## Fresh source and exact browser review

Call `get_task_acceptance_context` with positive integer work-item/task IDs from
the normal source link. It returns IDs, current numeric task revision, a lowercase
64-hex `expected_revision`, the proposed Done status and source link. It does not
return titles, saved output, notes, requester/submitter identities or evidence URLs.

The exact revision binds case/task metadata, immutable native origin and submission
history, current reviewer/owner/submitter identities, linked/canonical record state,
active dependent task metadata, and pending legacy notice count/latest ID. At most
25 linked records and 25 active dependent contributions are supported; larger
cases use ordinary Work. Registration-like roster or unrelated task bodies are
not loaded by this pilot. Existing Work visibility checks remain authoritative.

`prepare_task_acceptance` accepts only `work_item_id`, `task_id`, numeric `revision`,
exact `expected_revision`, nonempty decision `reason` (at most 2,000 characters)
and a random 16–80 character `operation_id`. Reason text uses the existing task
submission text validator. No output replacement, owner/status/action override,
file upload, email checkbox, official approval or posting input is accepted.
Preparation records a private preview/audit and makes no business decision.

Signed-in browser review shows the exact work item/task, current confirmed lead,
assigned owner, actual submitter, revision, full expected output, full saved
submission, original submission note and proposed acceptance reason. It lists
active dependent contributions, linked-record count and pending legacy notices
to cancel. All plain text is escaped, with multiline text preserved.

**Confirm: accept reviewed contribution** explicitly affirms human review of the
saved output. The existing bounded same-origin/CSRF three-field form works at
320px without JavaScript. Previews expire after ten minutes. Any source,
submission, lead, identity, access, dependency, notice or linked-state change
requires fresh context and review rather than a silent newer-revision retry.

## Shared service, atomic effects and recovery

`task_acceptance.accept_in_transaction` rechecks the narrow pilot policy and calls
`work_tasks.mutate_in_transaction(..., 'accept', ...)`. It never updates task status
directly or bypasses normal blocker, document-access, open-state or revision gates.
The normal service owns Done status/revision, preserved submission/owner/due date,
append-only shared history/audit, dependent formal-review invalidation and legacy
deadline/milestone notice cancellation. A dependent contribution may become
unblocked; its status is not automatically advanced.

Task change, native history/domain audit, minimal MCP result and integration audit
commit together under one writer transaction. Final audit, review invalidation or
other failure rolls everything back. Two clients/keys racing the same revision
commit at most once; same-key confirmation/recovery returns the original decision.
This action creates no direct email/invitation or new external outbox. Existing
normal notification preferences, future jobs and shared-history visibility still
apply. There is no transport delivery claim in the receipt.

The acceptance receipt is stored in the MCP action table and verified against the
immutable native `task_accept` event. It does not add a new `/api/v1` decision route
or alter the existing acknowledge/submit API receipt contract. It returns original
Done status/revision/time, work/task IDs, coordinating lead as next actor and source,
without output, expected output, submission note, decision text or display names.

Recovery requires the same active grant/resource/scope, current confirmed lead and
current visibility of the original task and linked records. Case/task creation
stamps, retained task-origin event and immutable acceptance actor/task/revision
are verified. Reused source identities cannot bind an old result. Current lead
loss or source-access withdrawal makes the receipt unavailable; it never keeps
old authority alive.

Later ordinary reopening, corrections or resubmission remain separate. Recovering
the original key preserves them and never accepts again. A truly new canonical
submission cycle may be accepted with fresh context, a new key and a separate
human confirmation. This pilot does not impose a lifetime one-decision limit on
a task or resurrect an obsolete submission.

## Retention, capacity and rollback

Completed preview/snapshot copies clear with the decision commit. Expired copies
clear in independently committed lazy batches of 100 before prepare/recover/browser
access, even when later flag/authority checks fail. Minimal identities, hashes,
result and operation tombstones remain for recovery. Native shared history retains
the original submission and decision under its existing retention rules; clearing
a private preview is not deletion of the shared decision record.

Limits are 50 live previews and 10,000 total keys per actor, one task/revision per
action, 2,000 reason characters, 25 linked records, 25 active dependents and the
shared process-local 30/minute action limiter. Coordinated rate limiting is needed
for multiple hosting workers; database writer serialization protects decisions.

Rollback disables `CSS_MCP_TASK_ACCEPTANCES_ENABLED` and restarts if required.
New context/prepare/confirmation/recovery stop; lazy preview cleanup still works.
Committed Done decisions, immutable history and retained receipts remain. Ordinary
Work review/reopen flows retain their existing behavior. Rollback never reverses
a decision, frees a key or changes an official record automatically.

## Named pilot acceptance and go/no-go

1. Deploy v8.97 or newer after local MCP/OAuth/browser, existing Work, blocker/
   review, task API, integration-access, release and packaging checks. Record SHA.
2. Before enabling for any staff decision, record the named confirmed lead,
   independent contributor/submitter, synthetic or agreed case/task IDs, and the
   operator responsible for rollback. Reconnect with only the required consent;
   verify read/submit-only, owner, submitting officer, proposed lead, other officer
   and technical-admin accounts cannot accept.
3. Compare ordinary Work and the exact browser preview: saved/expected output,
   submission note, actor/owner/submitter, task revision, acceptance reason,
   downstream contributions, linked state, notice counts and explicit effects.
   Verify preparation leaves the task For review and all business records unchanged.
4. Confirm once; compare native Done revision/history, retained output/owner/due
   date, minimal receipt, dependent unblocking and normal notice/review effects.
   Verify no work-item completion, official approval/closure/signature/dispatch,
   external send or stock/financial posting. Reconcile normal downstream notices.
5. Race two keys/clients, replay after a lost response, inject final-audit/review
   failure, and withdraw role/session/grant/linked access. Change output/source/
   lead/owner/submitter, block prerequisites, and test expiry/CSRF/Origin/tampering.
   Failures must not leave a partial decision or an unexplained missing receipt.
6. Reopen/resubmit normally and recover the old receipt; later work must survive.
   Test a fresh separate acceptance cycle, source identity mismatch, preview text
   cleanup/capacity, 320px/no-JavaScript and flag rollback. Record observed outcomes.
7. Record a specific go/no-go decision before enabling a named staff pilot or
   expanding it. Local tests and previous read/M3 acceptance do not activate M4.
   Other decisions, signing/dispatch and operational posting remain separate work.
