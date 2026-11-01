# Private replies to work and task comments

Draft PR #572, candidate 9.77. Work/task discussion replies are implemented for
later activation. Deployment, preview publication, activation and personal/live
testing remain deferred. Local verification uses synthetic data and blocked providers.

## Commands and independent consent

| Step | Work-level reply | Task reply |
| --- | --- | --- |
| Open signed-in form | `/work_reply` | `/task_reply` |
| Retrieve exact private preview | `/workreply_preview OPERATION_ID` | `/taskreply_preview OPERATION_ID` |
| Confirm before expiry | `/workreply_confirm TOKEN` | `/taskreply_confirm TOKEN` |
| Recover original post/current revision | `/workreply_receipt OPERATION_ID` | `/taskreply_receipt OPERATION_ID` |

Independent `work.reply` and `tasks.reply` consent each require `work.read` plus
the default-off switches `CSS_TELEGRAM_WORK_REPLY_ENABLED` and
`CSS_TELEGRAM_TASKS_REPLY_ENABLED`, respectively. Existing comment-posting, task
and metadata grants enable neither reply automatically; one reply grant enables
neither the other reply nor ordinary comment creation. Current private inbound,
link, delivery, account, bot and original chat proof must remain valid. Group,
topic and direct-worker posting paths are refused.

The signed-in JavaScript-free form takes exact work/parent-comment numbers, an
exact task number for task replies only, and plain reply text (1,000 characters
maximum). CRLF/CR normalize to LF; control characters and unsupported mention,
edit, progress, approval or extra task fields are refused. Literal `@name` does
not create a mention. Preparation changes no source discussion.

The source discussion displays each comment number and current revision so the
parent can be selected without inspecting a URL. Review the selected parent in
Office Connect before preparing. The five-minute
private preview shows exact work/task numbers and titles, their current states,
parent comment number/current revision, a source link and the complete entered
reply. **Your entered reply appears in Telegram and the saved discussion/history,
visible to people with current source access.** Parent text/author names, other
stored discussion, submissions, outputs and blocker reasons stay in Office Connect.
Oversized Unicode previews are refused before posting. Confirm in the original
private chat only after checking the parent, thread and full reply text.

## Native thread, visibility and notice rules

Current native discussion access, including every linked document, permits a reply.
Task ownership, lead/officer status and technical account role are not prerequisites
for an ordinary permitted reader to participate. Consent grants no source access.
The selected parent must exist in the exact work-level or exact same-task thread.
Cross-work, work-versus-task and other-task parents are refused. A reply may target
another reply in the same thread; native immutable parent links remain authoritative.

The adapter uses the existing `work_discussion.post_in_transaction` with the exact
parent ID and no mentions. Native posting rechecks scope and parent thread at the
write. One immutable comment plus its first revision is created with the linked
author and normal timestamp. Normal permitted follower and eligible parent-author
notices apply, deduplicated by native rules; authors receive no notice about their
own reply. Inactive or no-longer-permitted parent authors receive no new notice.
A reply grants no membership, document access, follow setting or notification
preference. Existing independently configured digests may later include normal
source notices; no digest/scheduler/provider is enabled or executed here.

Replies are informal discussion. Work/task status, ownership, revisions, output,
submissions, blockers, dependencies, deadlines, events and formal approval/review
records stay unchanged. Native discussion can remain available on completed work,
Done/Cancelled tasks and work under active formal review. Changed source after
preview still requires a fresh preview; discussion never submits, accepts, reopens,
approves or resolves a changed-decision review. Your own text edits use
[separate edit confirmation](TELEGRAM_COMMENT_EDITING.md); mentions and reading
stored discussion remain in Office Connect.

## Stale parents, atomicity and recovery

The preview binds a hash of the full current parent record/revision, without
storing another copy of parent text or author name. Current work/task/document
source digest and source history also apply. Parent editing before preview retrieval
or confirmation refuses the old preview, including an edit back to earlier text.
Prepare a fresh operation to review the new parent revision. Unrelated discussion
posts do not invalidate a reply. Current source permissions, modules, scopes,
pilots, expiry and original connection/context are rechecked. Revocation, account
changes, pause, disconnect and restore cannot revive a stale reply.

Native reply/revision/follower and parent notices/author-read marker, saved comment
identifier, consumed preview, receipt and private reply handoff commit atomically.
Notice/receipt/handoff failure rolls back all; duplicate/concurrent confirmation
posts once. Existing native posting logic and schema remain unchanged. The adapter
reuses the existing saved-comment receipt metadata and retention rules; no new
source table or identifier column is needed. Task/work deletion and work-read
revocation fences include the new actions. Native append-only parent history and
foreign keys protect parent and thread references from deletion/number reuse.
No native constraint is disabled to enable this flow.

Recovery requires current source/thread/original author and an actual reply parent.
It reports the original reply outcome, parent number, source link and current reply
revision without projecting saved reply/parent text or reposting. Later native
author edits update the reported reply revision only. Retention clears source and
saved-comment identifiers through the existing retained-key policy.

## Verification and deferred acceptance

Use [isolated Python 3.11 commands](CLOUD_WORKSPACE.md). Focused files are
`tests/test_telegram_reply_manage.py` and
`tests/test_telegram_reply_manage_browser.py`. Coverage includes ordinary-reader
access, exact thread/parent boundaries, strict plain fields, parent-edit stale
previews/fresh revisions, hash-only parent storage, replies to replies, eligible/
inactive/no-access/self parent-author notices, unchanged source and terminal/formal
review state, current source/context/permission fences, atomic notice/receipt/
handoff failures, concurrent/repeat confirmation, immutable parent/thread reference
protection, retention and later edited-revision receipts without replay/text.
Two 390×844 JavaScript-disabled phone cases cover independent grants/menu/forms,
CSRF/strict target fields, parent ID/current revision, full exact plain-text preview,
confirmation/retry, unchanged work/tasks, no mentions/outgoing calls and expired
sessions. Menu/status remain within the budget at the maximum supported origin.

Exact evidence is in [SETUP_STATUS.md](SETUP_STATUS.md). All later
[live acceptance cases](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md) remain Pending.
