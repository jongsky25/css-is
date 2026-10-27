# Own task acknowledgement pilot (v8.85)

This first M3 increment implements `prepare_task_acknowledgement` and
`get_task_acknowledgement_operation`. It is disabled by default. Hosted M2/M3
write acceptance remains pending; passing read checks or merging code does not
enable this action. It follows reimbursement drafts merged in
[PR #496](https://github.com/jongsky25/css-is/pull/496), commit
`6bd192a863b6574caf040e52b90ae30f781a822d`.

## Scope and behavior

Separate optional `work:task:acknowledge` consent authorizes preparation for a
**To do** task currently assigned to the user. The normal task service also lets
certain officers acknowledge others' tasks; this pilot deliberately restricts
preparation/confirmation to the assigned owner. Technical administration alone
provides no authority. Default OAuth scopes remain reads and existing grants are
never widened. No other write pilot flag or read scope is required.

Inputs are work-item ID, task ID, its current revision, a progress note and one
random 16–80 character operation key. IDs are positive 64-bit integers; revision
is a strict integer 1–9223372036854775806. The note is required, at most 2000
characters, trimmed and UTF-8 valid; control characters other than newline/tab
are rejected. Unknown fields, outputs, owner changes and deadlines are rejected.
The model must read a current revision rather than guess or automatically retry
against a newer one.

Preparation creates an expiring preview only. In the signed-in browser, the
owner reviews exact case/task IDs and titles, revision, due date, progress note,
**To do → In progress** and the responsible next person (the assigned owner).
The note enters ordinary shared-work history visible to permitted readers.
Normal domain effects include work-item review invalidation and cancellation of
pending legacy document deadline/milestone notices. No output is submitted,
accepted or approved; no ownership or deadline is changed and no invitations or
external relay calls occur. Later submit/return/cancel actions remain ordinary
UI/API operations outside this MCP pilot.

## Confirmation, API parity and recovery

Confirmation checks the canonical Origin, CSRF, current registered session,
original active connection/scope, exact preview digest and ten-minute expiry.
Current case/task access, ownership, workflow availability, linked-document
constraints, task revision and the work-item snapshot are rechecked under the
writer lock. Disabled shared work, a completed case, reassignment, lost linked
record access or a changed revision blocks acknowledgement.

The shared `integration_operations.acknowledge_in_transaction` uses the same
fingerprint, actor/session check, task mutation and immutable `work_api_operation`
receipt as API v1. The regular API still owns its transaction; the MCP browser
confirmation owns a surrounding writer transaction. The task update, normal work
history/audit/review/notice effects, canonical API receipt, MCP completion marker
and integration audit commit together. Any failure rolls them all back.

A random canonical UUID **v4** key is generated once during preparation and
persisted, so both the API receipt URL and an exact API replay use the existing
API key contract. The MCP operation key remains a separate stable user-facing
recovery key. Canonical API receipt reads still require a registered signed-in
session; an MCP bearer does not become an API write credential.

The completed tool result returns the original `in_progress` status, result
revision, completion time, assigned-owner next actor, ordinary task source and
canonical API receipt link/key. It does not return titles, progress-note or output
text. Current source access is rechecked through the existing API receipt reader.
A completed receipt describes that acknowledgement, not later task state or
ownership. Refresh rotates bearer/refresh tokens while preserving connection
identity. Exact-key retries and duplicate confirmation return the original result,
never repeat the action or overwrite later UI/API work. Different payloads or
connections cannot reuse a key. Two independent confirmations against one task
revision commit at most once.

A timeout/unavailable result is not proof of failure. Recover the original MCP
operation or inspect the canonical API receipt and source before preparing a new
key. Never silently acknowledge a newly read revision. Canonical receipts are
immutable and their foreign keys retain the original case/task identity.

Preview note/snapshot copies clear on completion and lazily on expiry in separate
batches of up to 100. Hashes, original keys and durable receipt markers remain;
ordinary shared-work history keeps its normal retention. Limits are 50 live
previews and 10,000 total keys per account, with the shared process-local action
limiter of 30/minute. Multiple workers require coordinated limits before relying
on that cap across instances.

## Operator acceptance and rollback

1. Deploy v8.85 or newer after release, runtime import-closure and API/MCP tests.
2. Keep the pilot off while finishing hosted write acceptance. For a named owner
   in the intended pilot, enable `CSS_MCP_ENABLED=1`,
   `CSS_MCP_TASK_ACKNOWLEDGEMENTS_ENABLED=1` and normal shared work. Reconnect and
   explicitly select the new permission; refresh ChatGPT's tools.
3. Prepare a synthetic owned To do task using its current revision. Verify no
   task state changes before confirmation. Compare the full browser preview with
   the normal task screen, including note visibility and domain effects.
4. Confirm once: one revision increment, one acknowledgement event and one
   canonical receipt; status In progress, unchanged owner/due date/output, and
   assigned owner next. Check the API receipt against the MCP result.
5. Test exact API replay, duplicate confirmation, lost-response recovery and
   token refresh between preview and confirmation. Later normal UI/API edits
   must survive recovery. Never infer current state from the historical result.
6. Race two independent clients/keys on one revision. Check that only one task
   transition commits. Reassignment, linked-record access loss, task/case change,
   module disabled, revoked grant/session and expiry must block pending writes.
   Officer/admin accounts must not prepare another owner's task in this pilot.
7. Record deployment SHA, roles, source/task revisions, canonical/MCP keys,
   outcomes, timings and domain notice/review reconciliation. Local automated
   checks do not supply hosted acceptance evidence.

Rollback: disable `CSS_MCP_TASK_ACKNOWLEDGEMENTS_ENABLED` and restart if needed.
MCP previews/receipts become unavailable; ordinary work and canonical API receipts
retain normal authority and behavior. Disconnect revokes the connection
immediately. Rollback never silently reverses an acknowledged task or deletes its
history/receipts. No hosted activation or acceptance is claimed by this delivery.
