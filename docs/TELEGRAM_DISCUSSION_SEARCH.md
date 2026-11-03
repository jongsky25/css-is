# Private discussion text search

Draft PR #572, candidate 9.83. In review; deployment, preview publication,
activation and personal/live testing remain deferred.

## Scope and explicit consent to text excerpts

Use `/discussion_search WORK_ID work WORDS` for one work-level discussion or
`/discussion_search WORK_ID TASK_ID WORDS` for one task thread in that work.
The work-level option searches only work-level posts and replies; it does **not**
search every task as a work-wide follow would. Select task threads explicitly.

Independent `work.discussion.search` consent and default-off
`CSS_TELEGRAM_WORK_DISCUSSION_SEARCH_ENABLED` require separate `work.read`
consent/pilot, current work/source modules and native access to every linked
document. Inbox, followed-list, follow-write, read-acknowledgement, comment and
metadata-search permissions do not grant discussion text search automatically.
The account page explains that limited excerpts will be copied into private
Telegram. Existing `/find` remains a metadata search and does not search discussion
bodies even when this new capability is consented.

Native work and exact-task visibility are checked **before any discussion-body
query**. Hidden/missing work and cross-work/missing task targets return the same
neutral denial. Task submission/output and formal-document content are excluded.
Terminal discussions remain searchable when native current visibility allows them.
This scope grants no source membership, document access or write permission.

## Matching, current revisions and bounded excerpts

WORDS is a literal contiguous phrase of 2–80 Unicode characters, after trimming
the ends. Internal spaces are literal; control characters are rejected. Matching
uses Unicode casefold, including expansions such as STRASSE matching Straße.
It does not treat `%`, `_`, quotes or SQL operators as patterns or instructions;
all values are bound parameters. It does not apply accent folding, word stemming
or a language-model interpretation.

Comments and replies in the exact selected thread are matched using only their
**current revision**. Earlier immutable body revisions are not searched or copied.
The SQL result contains comment ID, reply indicator, current revision and one
bounded excerpt, without returning a full-body field. No separate author labels,
accounts, parent text, mention recipients, notices or read/follow state are fetched.
Names or other details already present in permitted discussion text can appear in
its excerpt; this feature does not redact the text's meaning.

Each excerpt contains at most 240 original-text characters plus optional ellipses,
with a window around the literal match. Unicode-casefold offsets are mapped back
to the original text so expansions do not shift or lose the matched phrase.
Control characters in displayed source text become spaces. Replies use plain
Telegram text with no HTML/Markdown interpretation. Results include work/task IDs
and bounded titles, comment/reply ID and revision, and an exact source discussion
link with focus/fragment and task context. The source page retains its normal
current text/history and read-management behavior.

## Seek continuation and read-only behavior

Results use descending **comment ID**, rather than edit-time order. Up to three
results are shown with one-result lookahead and a UTF-16 reply budget. Long Unicode
or source URLs can reduce a page while keeping continuation. Follow the displayed
command, for example `/discussion_search 42 work before:123 handoff notes`.
The optional first `before:COMMENT_ID` token after the thread is reserved for seek
paging and must be a canonical positive SQLite integer. The continuation preserves
the source thread and literal phrase. No hidden matches or global totals are shown.
Every page resolves current permissions and current revisions again.

Search itself marks nothing read, changes no follow/notice/read marker or source
record, creates no origin/draft/operation, and enables no delivery preference,
provider or scheduler. Native source discussion reads remain separate actions.
Replies/excerpts are not queued for a later worker or public/group channel.

## Private context, retention and later activation

Current account, link/grant/pilot, source modules, bot identity/fingerprint,
connection generation, private sender/chat/topic proof, origin and webhook mode
are required. Disconnect, restore, inactive account, revocation, pause or source
loss prevent later searches. Groups, topics, foreign senders and callbacks cannot
retrieve excerpts. Duplicate webhook IDs produce no second reply. Rendering
requires the existing intake transaction and source/body checks share its snapshot.

The query and generated excerpts remain ephemeral in **Office Connect's Telegram
processing**. Retained update/delivery descriptors hold no plaintext query, excerpt
or private projection; ordinary routing IDs and ingress payload hashes are unchanged.
Queries sent by the user and excerpts already delivered to Telegram remain in that
chat under Telegram's own retention. Revocation blocks future reads; it cannot
retract previously delivered text. No source/Telegram schema migration or new
dependency was introduced.

Use [isolated Python 3.11 commands](CLOUD_WORKSPACE.md). Focused files are
`tests/test_telegram_discussion_search.py` and
`tests/test_telegram_discussion_search_browser.py`. Service checks cover exact work/
task/reply scope, current revision refresh, literal SQL metacharacters, Unicode
offsets/length, strict input/seek/UTF-16 budgets, metadata-grant independence,
permission denial before body SQL, actual-renderer field minimization, no source/
read/operation writes, ephemeral descriptors, current context and deduplication.
Two 390×844 JavaScript-disabled phone cases cover separate text consent, metadata
search exclusion, work/task current parent/reply excerpts, excluded old revisions,
bounded text, exact source navigation, unchanged notices/read/follows and disconnect.
All data/providers are synthetic or blocked. See [verification](SETUP_STATUS.md)
and [pending live acceptance](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md).
