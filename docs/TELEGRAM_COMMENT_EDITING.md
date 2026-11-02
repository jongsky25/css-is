# Private editing of your own work and task comments

Draft PR #572, candidate 9.79. Author-owned comment editing is implemented for
later activation. Deployment, preview publication, activation and personal/live
testing remain deferred. Local checks use synthetic records and blocked providers.

## Commands and independent consent

| Step | Edit a work-level comment | Edit a task comment |
| --- | --- | --- |
| Open signed-in form | `/work_comment_edit` | `/task_comment_edit` |
| Retrieve exact preview | `/workedit_preview OPERATION_ID` | `/taskedit_preview OPERATION_ID` |
| Confirm before expiry | `/workedit_confirm TOKEN` | `/taskedit_confirm TOKEN` |
| Recover original edit/current revision | `/workedit_receipt OPERATION_ID` | `/taskedit_receipt OPERATION_ID` |

Independent `work.comment_edit` and `tasks.comment_edit` grants each require
`work.read` and the default-off switches `CSS_TELEGRAM_WORK_COMMENT_EDIT_ENABLED`
and `CSS_TELEGRAM_TASKS_COMMENT_EDIT_ENABLED`. Other read/comment/reply/task grants
provide neither edit automatically; one edit scope enables neither the other nor
ordinary post/reply creation. Current private inbound/link/delivery/account/bot/
original chat proof must remain valid. Group/topic/direct-worker edits are refused.

Review the original comment and history in Office Connect. The discussion page
shows the comment number and current revision. The signed-in JavaScript-free form
takes exact work/comment/revision numbers, a task number for task comments only,
and the complete replacement text (1,000 characters maximum). CRLF/CR normalize
to LF. Control characters, unsupported parent/mention/progress/approval fields,
stale or invalid revisions, wrong-thread targets and identical text are refused.
Your own replies can also be edited without changing their existing parent.

Preparation changes no comment. Retrieve the five-minute private preview and check
the exact work/task/comment, current → next revision, existing reply parent if any,
source link and complete replacement before confirming in the original private
chat. **Your entered replacement text appears in Telegram and normal source
history for people with current work/document access.** Previous text/history and
mentioned identities remain in Office Connect. The current stored comment and mention metadata
are hashed for source fencing; older revision contents are not fetched by this flow. Oversized
Unicode previews are refused before mutation; there is no silent text truncation.

## Native author, thread and mention rules

Only the original author with current source work/every-linked-document access
may edit. Task ownership, lead/officer status or a technical administrator role
gives no permission to edit another author's text. Consent grants no source access.
The exact comment must belong to the selected work-level or same-task discussion;
cross-work, work-versus-task and other-task selections are refused.

This is a text-only edit. Existing structured mentions are preserved using the
native `mentions=None` behavior, validated against current work/document eligibility
before preview and before saving. Their count is shown without their identities.
An inactive or no-longer-permitted mention blocks the edit, including eligibility
lost after preview. Amend mentions in Office Connect first if needed. Literal
`@name` in replacement text creates no new mention. Native edit notice and author-
read rules remain unchanged; a text edit does not create new follower/reply notices.
No follow/access/notification preference, mention selection or parent change is added.
Existing independently configured digests remain separate; this feature enables
or executes no scheduler, digest or provider delivery.

One new immutable comment revision is added; the original author, comment/thread/
parent identifiers, original timestamp and every older revision remain intact.
The author-read marker advances by the native rules. Work/task status, ownership,
revisions, submissions/output, blockers, prerequisites, deadlines, events and formal
review/approval records stay unchanged. Native informal discussion editing can
remain available on completed work, Done/Cancelled tasks and under active formal
review. Editing a discussion comment does not revise an official decision or
approval, submit/accept/reopen work, or resolve a changed-decision review.

## Concurrency, atomicity and recovery

The form and preview bind the exact current comment revision. The full current
comment and existing mention metadata are hashed; work/task/linked-document source
digest and source history also apply. Any newer edit before preview retrieval or
confirmation refuses the old preview, including a later edit back to earlier text.
Review the latest source revision and prepare a fresh operation. Unrelated new
comments remain independent. Current source rights, modules, scopes/pilots, expiry,
account and original connection/context are rechecked; revoke/pause/disconnect/
restore cannot revive a stale edit.

`work_discussion.edit` retains its public transaction wrapper and original native
edit body. Extracted `edit_in_transaction` strictly requires the caller's transaction
and keeps author/revision/access/history/mention/notice logic unchanged (AST parity
verified). The Telegram adapter uses it in the generic confirmation transaction.
Revision/retained mentions/native notice/read effects, recorded edit revision,
preview consumption, receipt and private reply handoff commit atomically. Notice,
receipt or handoff failure rolls back all. Duplicate/concurrent confirmation adds
one revision once; it cannot overwrite a later source edit.

Additive nullable `telegram_operation.comment_revision` records the revision saved
by this edit separately from current source state. Existing operations migrate with
a null value before triggers are installed. Existing `comment_id` stores the chosen
comment, and work/task routing remains independent. Deletion/revocation fences
include both edit scopes; native append-only comment history and foreign keys
protect source references. Work-deletion and retained-key cleanup clear revision/
identifier/routing metadata. No native source schema or history constraint changed.

Recovery verifies the current source thread and original author. It reports the
recorded edit revision, current comment revision and source link without stored
text, replay or overwrite. For example, a saved revision 2 followed by a native
edit to revision 3 remains reported as recorded 2/current 3. It never creates a new
comment, repeats the edit or erases later history. Comment/reply forms now point
to the separate edit commands while retaining their original field contracts.

The shared status message lists the work-read prerequisite once when it would
otherwise repeat beside each missing action consent. All individual feature/
missing-consent details remain available, including the separate Work lookup
consent, within Telegram's limit at the maximum supported site origin.

## Verification and deferred acceptance

Use [isolated Python 3.11 commands](CLOUD_WORKSPACE.md). Focused files are
`tests/test_telegram_comment_edit.py` and
`tests/test_telegram_comment_edit_browser.py`. Coverage includes original-author
checks against reader/lead/officer/technical-admin overrides, exact thread/revision
selection, strict text and no-op refusal, stale edits/fresh revisions, unchanged
source/terminal/formal review state, immutable old history and reply parent,
retained current mentions/eligibility loss, native notice/read rules, current
source/context/permission fences, atomic failures, retries/concurrency, retention
and recorded-versus-current revision recovery. Two 390×844 JavaScript-disabled
phone flows cover independent grants/menu/forms, visible source ID/revision,
CSRF/strict fields, other-author/stale revision refusal, exact replacement preview,
confirmation/retry, old revision retention, unchanged work/tasks, no mentions/
outgoing calls and expired sessions. Existing native discussion/API callers
exercise the retained public wrapper.

Exact evidence is in [SETUP_STATUS.md](SETUP_STATUS.md). All later
[live acceptance cases](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md) remain Pending.
