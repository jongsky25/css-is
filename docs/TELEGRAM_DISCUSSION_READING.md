# Selected discussion threads and current message parts

Draft PR #572, candidate 9.84. In review; deployment, preview publication,
activation and personal/live testing remain deferred.

## Commands and independent text-reading consent

`/discussion_thread WORK_ID work COMMENT_ID` opens a selected work-level comment.
Replace `work` with a task ID for a selected comment in that exact task thread.
The view shows a bounded current preview and a page of **direct replies**, newest
reply ID first. It does not flatten an entire descendant tree. Each reply has a
command to open its own replies; a valid same-thread parent command returns up a
level. This allows nested discussion reading without an unbounded recursive fetch.
Each displayed node includes an exact native source link with focus/task context.

Independent `work.discussion.read` consent and default-off
`CSS_TELEGRAM_WORK_DISCUSSION_READ_ENABLED` require separate `work.read`
consent/pilot, current modules and native work/every-linked-document access.
Search, metadata, inbox, follow and posting permissions do not grant reading
automatically. Reading permission does not grant search, posting, editing, follows,
read acknowledgement or source membership. The account page explicitly explains
that current text is copied into the private Telegram chat.

The work/task scope and selected comment metadata are validated **before body
SQL**. Hidden/missing work, cross-work tasks, a comment in another task or a
missing message return the same neutral denial. Parent and child references cannot
expand into other work/task threads, including inconsistent legacy references.
Only current message revisions are projected. Author labels/IDs, task submission/
output, notice/mention/follow/read state and parent bodies are not fetched. Names
already written into permitted text remain part of that text; it is not redacted.

## Bounded thread pages and full current messages

The selected preview is at most 300 characters plus a truncation ellipsis; each
direct-reply preview is at most 180. Up to three direct replies plus lookahead are
queried, with a UTF-16 reply budget that can reduce a page while preserving seek
continuation. Follow the displayed `/discussion_thread ... before:REPLY_ID`
command for older direct replies. Source IDs are positive canonical SQLite integers.
No global or hidden reply totals are shown. Every page refreshes current source,
revisions and permissions; pages are not a frozen conversation snapshot.

Use `/discussion_message WORK_ID work|TASK_ID COMMENT_ID` to read a full current
message in numbered parts. Each part contains at most **900 original Unicode
characters**, so native messages of at most 4000 characters need at most five parts.
The response includes current revision, part number/total, source URL, previous/
next commands and a thread command. Newlines are retained in message parts;
other control characters become spaces. Previews flatten control characters.
Codepoint slicing/length functions account for embedded NUL in older native text,
so content after NUL remains addressable without returning a full-body SQL field.
No source text is modified and no HTML/Markdown parsing is enabled.

Continuation uses `/discussion_message ... part:REVISION:NUMBER`. A request for
an older revision is refused **before any body query** and offers the current
first-part command. It cannot retrieve history or silently mix an old first part
with a new second part. A part beyond the selected message's actual length offers
a reopen command. Reopen without a part token after an edit. Text already delivered
to Telegram remains there; a later refusal does not retract a previously read part.

## Search integration, state and private delivery

When both independent search and reading grants/pilots are current, search results
include a View thread command. Search remains usable without reading consent and
hides that command after reading revocation/pause. Reading a known comment ID does
not require searching first or retaining a search query. Thread/read commands hold
only source IDs, seek/revision/part metadata and remain ephemeral in app processing.

Current linked account, role, bot identity/fingerprint, connection generation,
private sender/chat/topic proof, grants/pilots, source modules, origin and webhook
mode are checked on every request. Revocation, source loss, pause, account change,
disconnect and restore prevent stale reads. Unsupported groups/topics/foreign
contexts/callbacks reveal no text. Duplicate webhook updates reply once. Rendering
requires the existing intake transaction; source validation and bounded current
body reads share its snapshot.

Reading here **marks nothing read** and changes no source record, notices, follows
or delivery preferences. It creates no origin, draft or operation and enables no
provider/scheduler. Full source discussion pages retain their normal native read
management. No body/query/part projection is retained in Office Connect's Telegram
update/delivery descriptors; ordinary routing IDs and ingress hashes are unchanged.
Text already copied into Telegram follows that chat's own retention. No database
migration, new dependency or change to native permission/history rules is needed.

## Isolated verification and later activation

Use [isolated Python 3.11 commands](CLOUD_WORKSPACE.md). Focused files are
`tests/test_telegram_discussion_read.py` and
`tests/test_telegram_discussion_read_browser.py`. Service checks cover exact
selected/direct/nested/parent scope, legacy cross-thread references, current-only
refresh, complete five-part Unicode/control-text reading, stale revision refusal
before body SQL, direct-reply seek/part/search-link max-origin budgets, independent
grants, real-renderer field minimization, no source/read/preferences/action writes,
ephemeral descriptors, current context and duplicate/no-push behavior. Two 390×844
JavaScript-disabled phone flows cover work/task independent consent, direct/nested
views, complete message parts, an intervening native edit, refused old continuation,
current reopen/source navigation and unchanged native read state. All data/providers
are synthetic/blocked. See [verification](SETUP_STATUS.md) and
[pending live acceptance](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md).
