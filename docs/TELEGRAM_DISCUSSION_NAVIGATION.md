# Inbox and followed-discussion navigation

Draft PR #572, candidate 9.87. Deployment, previews, activation and personal/live
testing remain deferred.

`/my_updates` lists your unread notice metadata. Both its rows and
`/update_status NOTICE_ID` now offer `View current thread` when current independent
`work.discussion.read` consent and its default-off pilot are enabled, in addition
to the inbox/work read requirements. The command opens the exact comment in its
work/task scope. Notice revision and current revision remain distinct: opening a
thread reads its **current** revision, not historical text from the notice.

`/my_follows` now offers `Browse comments` for each saved scope under the same
separate reading consent/pilot. A work-wide saved row opens work-level comments
only. Its native follow coverage still includes task discussions, but the shortcut
does not expand into task rows or select an arbitrary task. A saved task row opens
only that task discussion. Follow/unfollow controls retain independent permission
and confirmation requirements.

Both metadata views continue to query no discussion body, author label or task
submission. Shortcuts contain source IDs only and create no action origin, draft,
preview or operation. They do not change notices, read markers, follows or delivery
preferences. Existing bounded seek pages reserve UTF-16 space for the new commands;
source URLs, details and continuation remain available at the maximum origin size.

The destination command rechecks current private context, grants, pilots, modules
and native source/every-linked-document/task access. Cached commands preserve no
access after revocation, pause, disconnect, source loss or restore. Reading text
copies it into the private Telegram chat; it does not mark the notice read.
Explicit read acknowledgement remains a separate confirmed action.

Verification extends the inbox/follow service suites and no-script 390×844 phone
flows. Cases cover separate consent, grant/pilot removal, current text after a
notice revision changes, exact work/task navigation, source loss, body-SQL denial
in metadata views, unchanged state, no operations and Unicode seek completeness.
See [status](SETUP_STATUS.md), [inbox](TELEGRAM_DISCUSSION_INBOX.md),
[followed list](TELEGRAM_FOLLOWED_DISCUSSIONS.md),
[browsing](TELEGRAM_DISCUSSION_BROWSING.md) and
[reading](TELEGRAM_DISCUSSION_READING.md). Hosted acceptance remains Pending.
