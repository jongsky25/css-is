# Reply shortcuts from private discussion views

Draft PR #572, candidate 9.85. In review; deployment, preview publication,
activation and personal/live testing remain deferred.

## From reading to the existing reply workflow

Current `/discussion_thread` views show a **Reply form** link for the selected
comment and each displayed direct reply. Current `/discussion_message` parts also
show a link for that selected message. A work-level view uses the existing work
reply form; a task view uses the task reply form. Stale/unavailable message-part
responses do not offer a shortcut. Direct-reply pages retain continuation when
additional links reduce the number of displayed replies.

The link contains only `case_id`, optional `task_id`, and `parent_id`. It carries
no existing message text, entered reply, colleague selections, revision promise,
private origin, operation ID or confirmation token. Opening it does not create an
origin, preview, operation, reply, notice, read marker or preference change.

The normal path is:

1. Read the currently permitted comment/reply in the private view.
2. First send `/work_reply` or `/task_reply` as shown in that view, then open or
   reopen its Reply form link. A current matching private request is required;
   without one, the page explains that a request is needed.
3. Sign in as the linked Office Connect account. Work/task/parent numbers are
   prefilled; reply text and mention selections start empty. URL query fields
   cannot preload a body, mention list or approval/confirmation action.
4. Enter the reply, prepare the exact private preview and inspect the current
   work/task, parent number/revision and your entered text. Confirm privately
   before expiry. Retry/recovery reports the same native post without reposting.

Source numbers remain editable suggestions, not authority. Existing strict fields,
CSRF, body length/plain-text and current actor/source checks still apply. No reply
is posted by the link, page opening or Prepare preview button alone.

## Existing permissions and source rules

No new scope, command, pilot, database schema or write service is introduced. The
view already needs `work.discussion.read` plus `work.read`. Shortcuts additionally
require current **`work.reply`/`CSS_TELEGRAM_WORK_REPLY_ENABLED`** for work-level
comments or **`tasks.reply`/`CSS_TELEGRAM_TASKS_REPLY_ENABLED`** for task comments.
An opposite-type reply grant is insufficient. Grant revocation/pause removes the
shortcut on the next view; read-only users can continue permitted reading without
it. Existing private sender/bot/generation/module/webhook requirements apply.

The signed-in form still requires a matching original private request bound to
the linked account. A cached or forwarded URL cannot bypass source visibility,
every-linked-document access, exact thread/parent checks or current reply consent.
No parent text is copied into the reply preview or URL; the old writer reads the
current parent for validation/hash and displays its current number/revision.

A parent edit **before preparation** is reflected in the fresh preview. The link
does not pin old content. A parent/work/task/document change **after preparation**
invalidates the pending confirmation, requiring a fresh preview. The user should
review the current parent in Office Connect or its separately permitted private
view before confirming. Existing immutable history, parent/follower notices,
mention consent/eligibility and atomic native reply/receipt behavior are unchanged.
Reading a parent is not silently acknowledged by posting its reply; only native
author read rules for the newly saved message apply.

## Bounded presentation and isolated checks

Thread reply blocks count shortcut URLs within the UTF-16 budget and keep seek
continuation. The thread content budget is 3300 units with space reserved for
navigation, the short private-request instruction and the existing read-only footer;
the external 4096-unit assertion is unchanged. Long Unicode parent/reply previews,
200-character origins, current message parts with previous/next links and extra
parent navigation are covered together. All links are generated only after current
source/message validation, using the existing configured origin and numeric IDs.

Use [isolated Python 3.11 commands](CLOUD_WORKSPACE.md). Focused files are
`tests/test_telegram_reply_shortcuts.py` and
`tests/test_telegram_reply_shortcuts_browser.py`. Service checks cover source-only
links on selected/direct/current-part views, opposite/revoked/paused grant hiding,
no read/source/action/origin writes from lookup, fresh/stale parent handling, lost
document access, long Unicode/maximum-origin seek/part budgets and stale-part hiding.
Four 390×844 JavaScript-disabled phone cases cover work/task and selected/direct
parents: explicit existing reply request, no implicit origin/operation, source-only
prefill, empty text/mentions, strict form/CSRF, no source post before confirmation,
exact preview, one native reply/notice, retry idempotence and unchanged task/work
state. All data/providers are synthetic/blocked. See [evidence](SETUP_STATUS.md),
[existing reply behavior](TELEGRAM_REPLY_MANAGEMENT.md) and
[pending live acceptance](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md).
