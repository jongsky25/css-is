# P2.1 — Discussion and replies

October 16, 2026. **Accepted**, version **6.60**, branch `codex/work-discussions`. Phase 1 was explicitly accepted by the user before development began. This increment was subsequently merged at `9622870` on the user’s instruction. Live deployment success has not been independently verified.

Phase 2 acceptance was recorded when the user authorized P3.1 after the [technical acceptance review](WORK_MANAGEMENT_PHASE_2_ACCEPTANCE.md). Historical verification notes below remain unchanged.

## Delivered

- Work items and individual contributions each have a discussion screen, reached from their detail cards. A contribution discussion is visible to the permitted work-item audience, not solely the task owner; this is explained on screen.
- Plain-text messages (1–4,000 characters), replies with linked context, author labels and timestamps. Thread navigation shows 30 messages at a time; focus links can reach older reply targets.
- Authors can edit their own messages. Every original and edit is retained in append-only revision rows, with readable history and pagination. An independent message revision rejects stale edits, preserving the unsaved text for comparison.
- Current active account, work membership and visibility of every linked source document are rechecked for reads and writes. Technical administrators gain no bypass. Revoked source access prevents reading history or posting/editing. Replies cannot cross work items or contribution threads.
- Posting and editing do not update case, task, document or approval revisions, task state, deadlines or formal approval evidence. Discussion may continue on completed contributions; it is not a workflow transition.
- Existing Documents/Work enablement switches gate writes; permitted history remains readable when disabled. No automatic notifications, mentions, followers, task creation or formal decisions are introduced; those remain later increments.

## Storage and deployment

Additive `work_comment` and `work_comment_revision` tables, indexes, foreign keys and immutable-history triggers are installed through the existing idempotent schema installer. Inserts and edits are transactional. A failed revision insert rolls back the message itself. No legacy assignment or document data is migrated.

`work_discussion.py` is included in the deployment module allowlist, with an existing automated packaging guard. Version and plain-language changelog are bumped to 6.60.

## Verification

Focused suite: **115 passed** across shared work, Documents, setup, HTTP routes and Workspace operations; only the existing Starlette/httpx deprecation warning. Evidence includes independent task/document revisions, author-only edits, stale and simultaneous edit rejection, thread boundaries, revoked and inactive access, disabled writes with readable history, escaped HTML, CSRF, transactional rollback, immutable history, repeat installation and message/edit pagination.

A Chromium journey used two confirmed contributors to discuss a contribution, reply, edit their own text and inspect retained history. The case-wide discussion stayed separate. Desktop (1440px) and mobile (390px), keyboard history interaction, no horizontal overflow or browser errors. Local browser script and screenshots: `/workspace/scratch/work-p21`. Test report: `/tmp/work-p21-tests.xml`.

## Next increment

P2.2 adds permission-aware mentions, following, unread state and durable targeted notices. Review and merge P2.1 first. Phase 1 acceptance is recorded in the plan; it does not claim live integration verification or replace P4 operational acceptance.
