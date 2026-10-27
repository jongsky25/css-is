# MCP private task comment drafts — M2.3

Implemented for v8.81; independently disabled by default. Hosted acceptance is
pending. Follows supply drafts merged in
[PR #490](https://github.com/jongsky25/css-is/pull/490) and the
[common action contract](MCP_WRITE_PILOT.md).

The hosting allowlist for the earlier notification and supply action modules
was repaired separately in v8.80, [PR #491](https://github.com/jongsky25/css-is/pull/491).
This release includes its own private-comment modules and verifies the complete
deployment import closure. Merge alone does not establish hosted acceptance.

## Capability and boundary

`prepare_task_comment_draft(work_item_id, task_id, body, operation_id)` prepares
one new owner-private text draft for a currently permitted contribution task.
Use exact work/task IDs from the signed-in UI or existing authorized metadata
reads. Supply the user's proposed text; the tool does not read discussion
messages, other drafts or private task submissions to generate it.

Positive integer IDs and 1–4,000 characters of plain text are required. Normalize
line endings and trim outer whitespace. Reject hidden C0/DEL controls except
newlines/tabs. No mentions, reply parent, attachments, posting, task submission,
workflow decisions or edits/deletes of existing drafts are exposed.

The initial call stores a ten-minute preview, not a saved draft or shared
message. It returns status, key and an account-protected confirmation URL; no
draft body or private discussion content is returned. The browser shows the
exact normalized body, current work item/task names and IDs. Only an explicit
**Confirm: save my private draft** POST saves the new private record.

Saved drafts are visible only to their owner while they retain current access
to the target case/task. Case officers, collaborators and technical admins gain
no access to another person's draft through these screens. The source page
offers **Load into the discussion form for review**. That GET preloads the
owner's text into the exact matching task's existing compose form; it never
posts. Draft IDs for a different owner, case or contribution are refused, and
drafts cannot be loaded as replies or message edits. The task discussion lists
only the owner's latest ten saved drafts, with source links and timestamps.

Posting remains a separate explicit action on the existing Office Connect form,
with its existing authority, CSRF and notification rules. No MCP tool can post
the draft. Drafts are independent saved text, not tracked publication records:
later manual posting does not mark a draft consumed or prevent another manual
post. Screens describe the save/load action rather than claiming the text has
never subsequently been shared.

## Permission, persistence and recovery

- New `work:comment:draft` consent is separate from `work:read`, notifications and
  supply draft permissions, and excluded from default OAuth scopes. Old grants
  and refreshes never gain it. Readiness displays its consent/switch separately.
- Enable global MCP, `CSS_MCP_COMMENT_DRAFTS_ENABLED=1` and ordinary Shared work
  and Documents modules to prepare/confirm/recover through MCP. Other write
  switches are independent. Saved private source pages remain ordinary owner
  records even after the MCP pilot is disabled or its grant is disconnected.
- Bind the preview to actor, exact OAuth grant/resource, normalized request hash,
  current case/task ID/title/revision snapshot, internal operation key and expiry.
  Recheck current account/scope/source access and revisions under the writer lock
  at confirmation, alongside registered-session, Origin, CSRF and preview-digest
  checks. Source/compose reads recheck owner and current task access.
- The domain service saves only `work_comment_draft` plus a body-free audit.
  MCP receipt completion and audit commit atomically with that save. No shared
  comment, comment revision, read marker, mention, follower notice, task/case
  mutation or workflow invalidation occurs. Audit failure rolls everything back.
- `get_task_comment_draft_operation(operation_id)` recovers status and source link
  through the same current grant without returning the saved body. Repeated keys,
  simultaneous confirmations and dropped responses recover one original record.
  A changed payload or different connection cannot reuse a key. Token rotation
  retains its binding; disconnect, account/security changes and historical restore
  block further execution/receipt access. Saved source access follows ordinary
  current owner/case permissions, rather than keeping a revoked grant alive.
- Later target revisions do not mutate/re-save a completed draft. Source and
  compose show a changed-context warning for review. A saved receipt never
  represents a posted message or current task/workflow status.

Keep one random 16–80 character key across timeouts. Never invent a replacement
key because a response was lost; inspect the original receipt/source first.
The pilot allows 50 unexpired pending previews and 10,000 total operation keys
per actor. Completion clears duplicate preview text/snapshots. Each entry point
commits bounded cleanup of up to 100 expired preview copies before processing;
key/hash/ID/time tombstones remain. This is lazy cleanup, not timed deletion on
an idle host. Wider rollout needs scheduled preview retention maintenance.
The confirmed private draft body is the intended durable domain record. No
credentials or body text are copied to MCP/domain audit summaries.

## Operator pilot

1. Deploy v8.81 or later, record running version/commit, and enable the global
   MCP switch, `CSS_MCP_COMMENT_DRAFTS_ENABLED=1` and normal Shared work/Documents.
2. Refresh the ChatGPT app tool catalog for `prepare_task_comment_draft` and
   `get_task_comment_draft_operation`; reauthorize and explicitly approve the new
   private-comment-draft permission. Verify readiness.
3. With an agreed test account and visible task, prepare a short test draft. Check
   the work/task target and text on the confirmation page. No saved draft or
   public discussion message should exist before confirmation.
4. Confirm the save yourself. Compare the owner-private source text, then load
   it into the task's discussion form. Check all three steps leave public
   messages, notices and task state unchanged. Do not click Post message unless
   separately intending an ordinary UI publication.
5. Repeat/recover the original key and resubmit the form: one private draft must
   remain. Check changed case/task revisions, lost case access, other users,
   read-only grants, session/grant revocation and expired previews are refused.
   Check no private body appears in MCP responses or audit summaries.
6. Record version/SHA, role, source parity, failure/recovery observations and
   latency before recording hosted acceptance. Local tests cover a real OAuth/
   MCP/browser journey across token rotation and mobile no-script save/load plus
   a separate explicit post using the existing UI.

Disable `CSS_MCP_COMMENT_DRAFTS_ENABLED` and restart to stop preparation,
confirmation and receipt disclosure through MCP. Revoke a connection to
invalidate its previews permanently. Pending previews can resume if re-enabled
before expiry. Existing owner-private saved records remain; the pilot offers no
delete/cancel/archive or reverse action.
