# Private work and task comments

Draft PR #572, candidate 9.75. Work/task discussion posts are implemented for later
activation. Deployment, preview publication, activation and personal/live testing
remain deferred. Automated verification uses synthetic data and blocked providers.

## Commands and separate consent

| Step | Work-level comment | Task comment |
| --- | --- | --- |
| Open signed-in form | `/work_comment` | `/task_comment` |
| Retrieve exact preview | `/workcomment_preview OPERATION_ID` | `/taskcomment_preview OPERATION_ID` |
| Confirm before expiry | `/workcomment_confirm TOKEN` | `/taskcomment_confirm TOKEN` |
| Recover recorded post/current revision | `/workcomment_receipt OPERATION_ID` | `/taskcomment_receipt OPERATION_ID` |

Independent `work.comment` and `tasks.comment` grants require `work.read` and their
respective default-off switches `CSS_TELEGRAM_WORK_COMMENT_ENABLED` and
`CSS_TELEGRAM_TASKS_COMMENT_ENABLED`. Current private inbound/link/delivery/account/
bot/chat proof must remain valid. Other task/comment/read grants enable neither
action automatically. Groups, topics and direct-worker posting are refused.

The signed-in JavaScript-free form takes an exact work number, task number for a
task comment only, and plain comment text (1,000 characters maximum). CRLF/CR line
endings normalize to LF; control characters and unsupported fields are refused.
No reply target, mentions, edits, status or approval fields are accepted. A string
such as `@name` remains literal text; it creates no mention or extra recipient.

Preparation writes no comment. Retrieve the five-minute private preview, inspect
the exact target, current work/task states and full entered text, then confirm
in the original private chat. Oversized Unicode previews are refused before any
source mutation. **Your entered comment appears in Telegram and the saved source
discussion/history, visible to people with current work/document access.** Stored
thread contents, expected outputs, submissions and blocker reasons are not copied
into Telegram. The form offers source links for reviewing discussion there.

## Native discussion visibility and effects

Native discussion authority is current work visibility, including every linked
document. A user does not need task ownership, a work-lead designation or officer
status simply to comment. Consent/technical account role grants no source access;
both work and task must still be available in the selected work. No membership,
document permission or follow preference is created by choosing a target.

Discussion is informal and independent of task/document revisions. Native posting
can remain available on completed work, Done/Cancelled tasks and work under active
formal consolidation review. The adapter preserves that behavior rather than
applying the separate task-amendment restrictions. Work/task status, ownership,
submission/output, revisions, blockers, dependencies, deadlines, document review
packets and approvals stay unchanged. A comment cannot submit, accept, reopen or
approve a task/document, or resolve a changed-decision review.

One native `work_comment` plus its first immutable `work_comment_revision` is
created with the linked author and normal source timestamp. Normal permitted
follower notices and the author's observed-revision marker apply. Mention rows,
reply targets and notification preferences are not added. Existing independently
configured digest policies may later include normal source notices; this feature
does not configure, enable or execute any digest/scheduler/provider delivery.
Replies, mentions, edits and reading stored discussion remain in Office Connect.

## Transaction, stale previews and recovery

`work_discussion.post` retains its existing public transaction wrapper and native
posting behavior. Extracted `post_in_transaction` requires the caller's active
transaction; its body is unchanged apart from SQL indentation. Scope/access,
source-write availability, plain text, native reply/mention rules, immutable
history, follower notices and author-read recording remain native. The Telegram
adapter calls the helper with no parent/mentions inside the generic confirmation
transaction. Comment/revision/notices/read marker, consumed preview, stored comment
identifier, receipt and private reply handoff commit together. Notice, receipt or
handoff failure rolls back all. Duplicate/concurrent confirmation posts once.

Before preview retrieval and confirmation, current work/task/document source
fingerprints, history and permissions are rechecked. Changed records require a
fresh preview even when informal posting itself remains permitted. Unrelated
comments do not invalidate another new comment, because discussion has its own
independent history and does not revise work/tasks. Module/consent/pilot pauses,
revocation, expiry, disconnect, restore, account changes and original context
checks prevent stale posting or unauthorized recovery.

An additive nullable `telegram_operation.comment_id` retains the saved identifier
without persisting a second copy of comment text. Old operations migrate unchanged
before triggers are installed. Pending task deletion cancels/scrubs a task preview;
work deletion cancels/scrubs comment previews and clears routing/identifier fields,
fencing numeric-ID reuse. Native append-only discussion history and foreign keys
protect committed comments and their references. Receipt validation checks the
current source thread and original author. Recovery reports recorded outcome,
source link and current comment revision without exposing the stored text or
posting again. A later native author edit changes the displayed revision only.
Retained-key cleanup removes the comment and source routing identifiers.

The shared status menu shortens repeated work-read descriptions while preserving
full missing action consent and the separate Work lookup consent. Menu/status stay
within Telegram's limit for the maximum supported site origin.

## Verification and deferred acceptance

Use [isolated Python 3.11 commands](CLOUD_WORKSPACE.md). Focused files:
`tests/test_telegram_comment_manage.py` and
`tests/test_telegram_comment_manage_browser.py`. Coverage includes ordinary-reader
posting/source visibility, work/task thread boundaries, strict plain input and
literal mentions, unchanged source/approvals, follower/author-read effects,
terminal/formal-review discussion, independent concurrent comments, changed
source/context/permissions, atomic notice/receipt/handoff failures, retries,
concurrent confirmations, deletion/ID reuse, retention and edited-revision recovery.
Two 390×844 JavaScript-disabled phone flows verify separate consent/menu/forms,
CSRF/strict fields, exact plain-text preview, confirmation/retry, no source task
changes, no outgoing delivery, and expired sessions. Existing native discussion,
channel and submission/API checks also exercise the public wrapper.

Exact evidence is in [SETUP_STATUS.md](SETUP_STATUS.md). All later
[live acceptance cases](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md) remain Pending.
