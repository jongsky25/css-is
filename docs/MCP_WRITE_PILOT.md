# MCP notification write pilot — M2.1

Implemented for v8.78; default off. Hosted write acceptance has not been run.

## Read acceptance handoff — October 27, 2026

The operator reported that all requested read checks passed in ChatGPT. They
specifically confirmed both Regional BHW Summit Forum person/activity scorecards
for activity 11591 (people 17 and 69) matched their exact signed-in source pages.
The desktop catalog refresh, separate consent and host activation resolved the
previous missing-tool issue. This is operator-reported live evidence, not a
fresh production inspection by the coding agent. Deployment SHA/version,
per-role observations, revocation timings and capacity measurements were not
provided in this chat and must not be invented or treated as measured evidence.

## Common action contract

This first action establishes the pattern for later M2 writes. Its storage
supports only the notification action. The shared browser confirmation boundary
also serves the independent [v8.79 supply-draft pilot](MCP_SUPPLY_DRAFT_PILOT.md),
which has its own scope, switch, storage and domain checks. The same boundary
also serves [v8.81 private task comment drafts](MCP_COMMENT_DRAFT_PILOT.md).
The independent [v8.82 saved report views](MCP_REPORT_VIEW_PILOT.md) pilot uses
the same confirmation boundary for personal selection metadata only.
Future domains need
their own authority, revision and preview review before reusing this pattern.

1. A new granular OAuth permission, `notifications:mark_read`, is eligible at
   registration but excluded from server default authorization scopes. Consent
   shows a separate optional action checkbox. Explicitly requested action scopes
   are also listed for review. Old grants and refreshes never gain permission.
2. `mark_my_notification_read(notification_id, operation_id)` prepares a durable
   preview. The caller generates a random 16–80 character key, keeps it, and
   reuses it after every timeout. The tool does **not** mark the notice read.
3. The preview binds actor, exact OAuth grant, deployment resource, action,
   request fingerprint, notice/comment/case/task IDs, current notice/message/read
   revisions and a ten-minute expiry. A key cannot switch target or connection.
4. The tool returns an account-protected confirmation URL. Opening it does not
   change read state. The page shows shared-work title, notice ID, category,
   creation date, observed message revision and a specific confirmation button.
   It exposes no message text to ChatGPT. A model-supplied yes/boolean cannot
   confirm an operation.
5. Browser POST requires a current registered session for that same actor,
   same-origin checks, session CSRF, the exact preview digest and explicit button
   confirmation. Under `BEGIN IMMEDIATE`, it rechecks account, grant, resource,
   permission, pilot/module switches, current source access, revisions and expiry.
6. The existing UI mark-read service, receipt completion and audit append commit
   together. Audit failure rolls everything back. Concurrent confirmations write
   once; later message edits stay unread. No provider, outbox or other external
   effect is involved in this action.
7. `get_mcp_operation(operation_id)` recovers pending/completed state through the
   same current OAuth grant. Repeating preparation or confirmation returns the
   original completed receipt. A completed receipt does not mark a later edit
   read. Expired/stale uncommitted previews require a new reviewed operation.
8. Lost authority, disconnect, account security changes and historical restore
   block further execution and receipt disclosure. Browser confirmation uses the
   active grant's refresh lifetime. OAuth refresh now preserves the connection's
   grant ID while atomically replacing both token hashes, so old tokens stop
   working while pending previews, receipts and owner revocation links keep
   their binding. An error is not proof of no commit:
   inspect the original receipt/source before creating a replacement key.

Receipts store identifiers, revisions, hashes and timestamps, not credentials,
message bodies or usernames. They retain keys rather than silently recycling
them. The pilot allows 50 unexpired pending previews and 10,000 total operations
per actor, then refuses further preparation. There is no automatic receipt
deletion: an operator must design a tombstone-preserving retention policy before
wider rollout or increasing this limit. Prepare/confirm/recovery share a per-actor
30/minute process-local limiter. This pilot retains the existing single-process
rate-limit limitation; do not treat it as a distributed quota.

## Operator activation and live verification

1. Deploy v8.78 or later; verify the running version/commit on ChatGPT readiness.
2. Enable `CSS_MCP_ENABLED=1`, `CSS_MCP_NOTIFICATIONS_ENABLED=1` and the new
   `CSS_MCP_NOTIFICATION_WRITES_ENABLED=1`; restart. Shared work and documents
   must be enabled through their ordinary settings. Use an agreed test account
   with an unread shared-work notice, not sensitive production messages.
3. Refresh the ChatGPT app catalog to load `mark_my_notification_read` and
   `get_mcp_operation`. Reauthorize and explicitly approve the new action
   permission, plus `notifications:read` to discover notices. Readiness shows
   the write pilot and permission independently; old grants remain read-only.
4. Ask ChatGPT to list your notices and prepare marking **one** selected notice
   read using a new random operation key. Save the key and confirmation link.
5. Check Office Connect first: the notice must still be unread. Review the
   preview, then confirm it yourself. Check that precisely the selected notice
   is read and ChatGPT recovers the same completed receipt with the original key.
6. Repeat the same key and submit the same form again: there must be one
   completion audit and no additional mutation. Edit a separate test message
   between preview and confirmation: the stale preview must fail and leave it
   unread. Check a different account, a read-only grant and a disconnected grant
   cannot perform the action. Test receipt recovery after a dropped response.
7. Record deployed version/SHA, account role, source parity, denial/retry results
   and observed latency. Only then record hosted acceptance for this write pilot.

Disable `CSS_MCP_NOTIFICATION_WRITES_ENABLED` and restart to stop preparation,
confirmation and recovery. Pending previews cannot execute while disabled; they
expire after ten minutes and may resume if re-enabled before expiry. Revoke the
test OAuth grant to invalidate its previews permanently. Rollback does not undo
already confirmed read markers; the pilot exposes no reverse/delete action.

## Local verification

`tests/test_mcp_actions.py` covers browser confirmation, MCP dispatch, read-only
grant denial, default-off behavior, cross-account/source/connection boundaries,
CSRF/origin/digest checks, stale edits/read state, expiry, revoked scopes/grants,
restore/session revocation, atomic audit failure, two-client races, lost-response
recovery, later unread edits and mobile confirmation with JavaScript disabled.
The remote OAuth probe verifies optional action consent, a real bearer MCP
preparation, browser confirmation and receipt recovery after token rotation,
alongside unchanged read-only consent and unsupported-scope denial.

This local evidence does not prove a deployed ChatGPT workspace has loaded the
new tools or that the hosted write pilot passed. No later M2/M3/M4 writes are
enabled by this implementation.

Personal calendar entry preparation is a separate default-off pilot: see
[M2.5 setup and acceptance](MCP_PERSONAL_CALENDAR_PILOT.md).

Unsubmitted reimbursement checklists are a separate default-off pilot: see
[M2.6 setup and acceptance](MCP_TRAVEL_DRAFT_PILOT.md).

Own task acknowledgement is a separate default-off M3 pilot using canonical API
receipts: see [setup and acceptance](MCP_TASK_ACKNOWLEDGEMENT_PILOT.md).

Own task submission for review is a separate default-off M3 pilot using canonical
API receipts: see [setup and acceptance](MCP_TASK_SUBMISSION_PILOT.md).

Own supply request submission is a separate default-off M3 pilot: see
[setup and acceptance](MCP_SUPPLY_SUBMISSION_PILOT.md).
