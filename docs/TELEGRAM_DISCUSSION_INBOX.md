# Private mentions and unread discussion inbox

Draft PR #572, candidate 9.79. Telegram can list your own unread discussion notice
metadata and open the correct work/task discussion. Deployment, preview publication,
activation and personal/live testing remain deferred. Local verification uses
synthetic data and blocked providers.

## Commands and consent

- `/my_updates` or `/my_updates all` lists your unread notices, newest notice first.
- `/my_updates mentions`, `/my_updates replies` and `/my_updates following` filter
  by the native notice reason. Normal notice priority applies: a reply also carrying
  a structured mention can be classified as a mention.
- `/my_updates FILTER BEFORE_ID` or `/my_updates BEFORE_ID` continues a seek page.
- `/update_status NOTICE_ID` shows current permitted metadata and the exact source
  discussion link for one of your own notices, including an already-read notice.

Independent `work.updates.read` consent and default-off
`CSS_TELEGRAM_WORK_UPDATES_READ_ENABLED` require `work.read`, current source
work/document availability, private inbound/link/delivery/account/bot/chat proof
and webhook replies. Existing work reads, mention selection, comment/reply/edit
permissions grant no inbox consent automatically. Inbox consent grants no write,
mention selection, membership or document access. Group/topic/direct-worker paths
cannot retrieve the inbox or replay a private reply.

## Own notices and current metadata only

Every list/detail query is bound to the current linked account as notice recipient.
Even a case lead or technical administrator cannot use this flow to inspect another
recipient's notice. Another recipient's ID, a missing ID and an inaccessible own
notice return the same neutral detail denial. Current native work visibility,
including every linked document, is checked on each request. Task notices must
still resolve within that same work; work-level notices retain work-level routing.
Terminal work/tasks remain readable when native discussion visibility allows it.

Replies show notice ID/reason, current work/task titles and IDs, comment ID, notice
revision, current comment revision, native notice timestamp/read status and exact
source link. They do not show comment/parent text, authors or selected recipient
names, old history, task submissions or expected outputs. The SQL path never reads
comment body or task submission/output columns; a SQLite authorizer test enforces
that property on the actual renderer connection. No other recipients or total
hidden/unread counts are disclosed.

The unread predicate matches the native discussion inbox:
`observed revision < notice revision`. A later comment edit can therefore show
notice revision 1/current revision 2. After revision 1 is marked read in Office
Connect, that notice leaves the unread list even if the current comment is at 2.
Details label it already read and still report the current revision. This preserves
native notice semantics rather than inventing a new read/unread model.

**Telegram lookup marks nothing read.** Open the source discussion to read its
content and manage read state in Office Connect. No acknowledgement, follow change,
new comment, mention, edit, task action, approval or notification preference is
created by inbox lookup.

## Bounded paging, private delivery and stale source checks

Own recipient, unread reason and source-visibility SQL filtering precede a bounded
native recheck scan (200 candidates, batches of 50). Up to five metadata entries
are shown, with a six-entry lookahead and UTF-16 reply budget. Titles are bounded;
long Unicode/source links can reduce a page size without dropping continuation.
Seek cursors use the last shown notice ID and preserve the chosen filter. If the
scan reaches its bound, a continuation is offered instead of claiming global empty
results. Hidden candidates do not expose names or counts. Each page is rebuilt
from current source state rather than a cached projection.

Source rights, modules, independent scopes/pilots, account/connection generation,
private sender/topic context, current bot and reply mode are rechecked. Disconnect,
restore, revocation, pause and bot changes prevent stale reads. Repeated webhook
update IDs produce no second reply, and no queued outgoing push is created. The
query remains ephemeral; retained update/delivery metadata contains no discussion
query, source title, comment contents or source author/selected-colleague names;
ordinary private routing identifiers remain as in the existing webhook path. Rendering
requires the existing intake transaction. No source or Telegram schema change was
needed; the native notice/history/read model remains unchanged.

## Main reconciliation and verification

Current main `adb83b4` (code version 9.60, merged seasonal PR #578) was merged into
the review branch before this addition. Both runtime feature sets and every actual
main changelog entry are retained. Shared release/status/cache conflicts were
resolved locally and checked for markers; the seasonal source/appearance checks
run with this candidate. No preview was replaced or feature activated as part of
that reconciliation. Earlier main/preparation notes remain historical in the handoff.

Use [isolated Python 3.11 commands](CLOUD_WORKSPACE.md) and separate larger-volume
scratch paths for concurrent long suites. Focused files are
`tests/test_telegram_discussion_updates.py` and
`tests/test_telegram_discussion_updates_browser.py`. They cover own-recipient and
current work/document boundaries, unread categories/read revisions, strict input,
bounded/Unicode paging, ephemeral descriptors, no source/read writes, no body-column
reads, terminal visibility, current scopes/modules/context, groups/topics/direct
mode, deduplication, no outgoing pushes and linking consent. Three 390×844
JavaScript-disabled phone cases cover native mention/reply/follow notices, separate
inbox/read grants, menu/list/detail/source navigation, no Telegram read marking,
source-managed read status, unchanged tasks and disconnect behavior.

Exact results are in [SETUP_STATUS.md](SETUP_STATUS.md). New-head full release CI
and later [live acceptance](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md) remain separate.
