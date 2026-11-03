# Private discussion browsing

Draft PR #572, candidate 9.86; publication, deployment, activation and live testing
remain deferred.

Use `/discussion_browse WORK_ID work` for work-level top-level comments or
`/discussion_browse WORK_ID TASK_ID` for exactly one task discussion. You do not
need a search phrase or comment ID. Current revisions appear newest comment ID
first, with up to three 180-character previews plus bounded lookahead. Follow
`Older comments` for seek paging; intervening edits refresh on the next request.
Pages are not a frozen snapshot. Empty pages reveal no hidden counts. Replies,
including legacy orphaned replies, are excluded from top-level lists. Open a
selected thread to navigate direct/nested replies or read full current message
parts using the existing revision checks. Source links focus the exact comment.

The existing independent `work.discussion.read` and `work.read` grants and their
default-off pilots are required. Search, inbox and follow consent do not grant
browsing. Work/module/every-linked-document and exact task checks precede body
SQL. Current private connection, bot, generation, restore, destination and grant
checks use the existing reading adapter. No new flag, scope, migration or provider
is introduced. Text is copied into the private Telegram chat and remains subject
to that chat's retention. Descriptors retain no body/preview projection.

Browsing marks nothing read and changes no notices, follows, source records,
delivery preferences or operations. Author labels, submissions, history and
notice/read/follow state are not queried. Reply links appear only with the
matching current reply consent/pilot; they prefill source IDs only. Fresh private
origin, entered text, exact preview and confirmation remain required.

Unicode/maximum-origin replies reserve room for navigation and the 4096 UTF-16
unit Telegram limit. Service regressions cover seek completeness, scope and
current revision isolation, empty pages, state/projection minimization, existing
consent/revocation/context guards and body SQL authorization. Two synthetic
390×844 JavaScript-disabled phone flows enter through browsing and continue into
thread/message/source navigation. See [reading](TELEGRAM_DISCUSSION_READING.md),
[reply shortcuts](TELEGRAM_REPLY_SHORTCUTS.md) and [status](SETUP_STATUS.md) for
related behavior and actual verification. Hosted acceptance remains Pending.
