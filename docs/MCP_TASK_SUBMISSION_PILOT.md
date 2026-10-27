# Own task submission pilot (v8.86)

This default-off M3.2 increment adds `prepare_task_submission` and
`get_task_submission_operation`. Hosted write acceptance remains pending; merging
code or passing read checks does not activate it. It follows task acknowledgement
merged in [PR #497](https://github.com/jongsky25/css-is/pull/497), commit
`a54aea0cf584462f3a17be6bc45696fdbdd52f48`.

## Action, fields and visibility

Separate optional `work:task:submit` consent permits preparing submission for an
**In progress** task currently assigned to the user. Acknowledgement, read and
draft scopes do not authorize submission. Existing grants and default OAuth
scopes are unchanged. The pilot restricts preparation/confirmation to the
assigned owner, even where an officer has broader ordinary UI/API authority.
Technical administration alone gives no submission authority.

Inputs are positive 64-bit work-item/task IDs, current strict integer revision
1–9223372036854775806, a required review note of 1–2000 characters, required
output/evidence of 1–8000 characters and one random 16–80 character operation
key. Text is trimmed, UTF-8 valid and rejects control characters other than
newline/tab. Unknown fields, reviewer decisions and owner/deadline changes are
rejected. Evidence links are saved as text, never fetched or uploaded by the
pilot. Read a current task revision; never guess or silently retry a newer one.

Preparation changes no task. The signed-in owner reviews the complete exact
output and note, IDs/titles, revision, due date, **In progress → For review** and
next review party before pressing **Confirm: submit my task for review**. The
output replaces that task's current saved submission; earlier versions remain in
normal shared-work history. The saved output and note are visible to permitted
work-item readers under normal record access rules. This is not a private draft
or a public publication. The preview escapes text and works without JavaScript.

Normal domain effects include task revision/history/audit updates, work-item
review invalidation and cancellation of pending legacy document deadline or
milestone notices. Ownership and due date stay unchanged. This action does not
accept, approve or complete the task, sign or dispatch a document, upload files,
fetch evidence links or send invitations. The work-item lead or authorized
concerned officer must review the exact submitted revision before accepting or
returning it in the normal workflow.

## Confirmation, routing and canonical receipts

A ten-minute preview binds actor, original connection, normalized payload,
case/task snapshot and reviewer routing (current case lead and unit). Browser
confirmation rechecks canonical Origin, CSRF, registered session, active grant
and scope, exact digest, expiry and current record authority under the writer
lock. Task/work-item/routing changes, reassignment, completed work, disabled
shared work and revoked linked-document access invalidate pending actions.
Recorded blockers, unfinished prerequisites and unresolved changed-decision
reviews prevent submission through the same current task-action predicate and
domain service as the UI/API.

`integration_operations.submit_in_transaction` reuses the existing API
fingerprint, current session/authority checks, task mutation and immutable
`work_api_operation` receipt. The regular API keeps its existing transaction and
schema. MCP owns a surrounding writer transaction so task/output/history/audit/
review/notice effects, canonical API receipt, MCP completion and review-routing
metadata commit atomically; a failure rolls them all back. No relay calls occur
in the transaction.

One random canonical UUID v4 key is persisted during preparation and reused for
API receipt lookup and exact API replay. It is separate from the user-facing MCP
operation key and is returned only after completion. API receipts still require
a registered signed-in session; an MCP bearer is not an API write credential.
The completed MCP result contains original `for_review` status/revision,
completion time, review party role, original lead/unit IDs and source/API links.
It returns no output, note or title text. Routing/status are historical; open the
normal source to see current state and responsibility.

Exact retries, duplicate confirmation, lost-response recovery and token refresh
preserve the original result without submitting twice or overwriting later
acceptance, return or edits. Current source access is rechecked by the canonical
receipt reader. Different payloads/connections cannot reuse a key. Independent
previews against one revision commit at most once. A timeout/unavailable result
is not proof of failure: inspect the original MCP/API operation before a new key.
Never infer acceptance or approval from a successful submission receipt.

Completed/expired preview output/note/snapshot copies clear; expiry cleanup uses
independent batches of up to 100. Hashes, original keys, routing metadata and
durable receipt markers remain, with ordinary shared-work history retaining its
normal versions. Limits are 50 live previews and 10,000 total keys per account,
plus the shared process-local action limiter (30/minute). Multiple workers need
coordinated limits before relying on that cap across instances.

## Operator acceptance and rollback

1. Deploy v8.86 or newer after release, runtime import-closure and API/MCP checks.
2. Finish the hosted write acceptance gates before activation. For the named
   assigned-owner pilot, enable `CSS_MCP_ENABLED=1`,
   `CSS_MCP_TASK_SUBMISSIONS_ENABLED=1` and normal shared work. Other write flags
   are independent. Reconnect/reconsent to submission and refresh ChatGPT tools.
3. Prepare a synthetic In progress task with its current revision and complete
   output/note. Compare the entire escaped browser preview with the ordinary
   task, revision, due date, current lead/unit and intended shared visibility.
   Verify no task/output changes before confirmation.
4. Confirm once: one task increment/event and canonical receipt, status For
   review, exact output/note, unchanged owner/deadline and correct next review
   party. Compare the MCP result with its API receipt and source. Review/accept
   the exact version through the existing UI; stale review must fail.
5. Exercise duplicate confirmation, API replay, lost response and token refresh
   between preview and save. Later UI/API acceptance or edits must survive
   recovery, which must still describe the original submission.
6. Race independent clients/keys on one revision. Verify at most one commit and
   exact rollback of task/output/history/receipts when completion fails. Test
   new blockers, unfinished prerequisites, changed-decision review, changed
   routing/revisions, reassignment, access/grant/session revocation, disabled
   modules and expiry. Officer/admin accounts cannot submit another owner's
   task through this pilot.
7. Record deployment SHA, named roles, exact synthetic inputs/source revisions,
   MCP/API keys, timings, outcomes and domain review/notice reconciliation. Local
   automated checks are not hosted acceptance evidence.

Rollback: disable `CSS_MCP_TASK_SUBMISSIONS_ENABLED` and restart if needed.
MCP previews/receipts become unavailable; ordinary shared work and API receipts
retain their usual authority and behavior. Disconnect immediately revokes the
connection. Rollback never silently reverses a submitted task or deletes its
output/history/receipts. No hosted activation or acceptance is claimed here.
