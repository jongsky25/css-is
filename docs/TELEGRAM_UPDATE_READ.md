# Explicit discussion read acknowledgement

Draft PR #572, candidate 9.88. In review; deployment, preview publication,
activation and personal/live testing remain deferred.

Start `/update_read` in your linked private Telegram chat. Its signed-in,
JavaScript-free form accepts one own notice ID and its exact notice revision,
as shown by `/update_status NOTICE_ID`. Read the discussion in Office Connect
before confirming. A notice-prefilled shortcut is available from unread update details
with the acknowledgement permission. Prepare the form, retrieve `/updateread_preview OPERATION`,
and confirm the exact five-minute private preview with its displayed command.
`/updateread_receipt OPERATION` recovers the recorded outcome without replaying it.

Independent `work.updates.acknowledge` consent and the default-off
`CSS_TELEGRAM_WORK_UPDATES_ACKNOWLEDGE_ENABLED` pilot require both `work.read`
and `work.updates.read`, with their current pilots. Existing read/mention/comment
permissions grant no acknowledgement permission. Link, inbound, delivery,
current account/bot/generation, private sender/context and webhook mode are required
on preparation, preview, confirmation and recovery. Scope revocation clears pending
previews, including revocation of either prerequisite. Reconnecting or restoring
data cannot revive the original operation. Source visibility remains authoritative;
even a work lead may acknowledge only their own recipient notice.

The preview shows notice reason/ID, work/task IDs and titles, exact comment/thread
link, notice revision, current comment revision and existing read status. It fetches
no comment body, author identities, task submission or expected output. The native
read helper internally validates the selected comment; discussion contents are never
copied into the Telegram preview, receipt or retained operation descriptors.

Confirmation rechecks the notice, read marker, comment revision and current work,
task metadata, linked documents and source events under the existing writer
transaction. Changed source or read markers require a fresh preview. A revision
different from the selected notice revision is refused. An already-read notice
needs no new operation. Source text, history, notices, other recipients, tasks,
events, approvals, follows and notification preferences remain unchanged.

The native monotonic per-comment/per-account read marker advances only to the
selected notice revision. For notice revision 1/current comment revision 2, this
records read revision 1; it does not acknowledge revision 2. The native unread
predicate compares the marker with the notice revision, so that notice leaves
the unread list. No new unread model or bulk acknowledgement is introduced.
`/my_updates` and `/update_status` continue to mark nothing read.

The source update, operation outcome and private webhook handoff are atomic.
Receipt/handoff failures roll back the read marker. Concurrent confirmations and
duplicate incoming update IDs cannot apply a second acknowledgement. Receipts
show the recorded acknowledged revision separately from current comment/read
revisions; recovery never updates a newer revision. Current own-recipient/source
checks still apply. Deleted source produces neutral non-recreation recovery;
the existing 180-day retention cleanup clears source routing identifiers.

Local verification uses synthetic databases and blocked outgoing providers through
[the isolated workspace wrapper](CLOUD_WORKSPACE.md), with separate workspace
scratch directories for long suites. Service tests cover own-recipient boundaries,
exact/stale revisions, no-op/monotonic markers, current source/document rights,
private protocol/context, consent/pilots, rollback, concurrency and retention.
Three 390×844 JavaScript-disabled phone cases cover native mention/reply/following
notices, separate linking scopes, strict form/CSRF, unchanged read state before
confirmation, exact preview, duplicate confirmation, receipt and updated inbox.
See [current evidence](SETUP_STATUS.md) and the
[pending live checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md).

Main companion refinements #579 at `25fe812` (9.61) were merged into the review
branch before this feature. Actual-main runtime changes and release history are
preserved; no companion preview was replaced.

## Notice-prefilled shortcut from update details (candidate 9.88)

`/update_status NOTICE_ID` offers **Mark this update read form** only for an
unread, valid own notice with current independent acknowledgement consent/pilot.
The existing inbox/work read requirements remain prerequisites. Discussion-reading
consent does not grant acknowledgement; text reading is not required when you
have read the source in Office Connect. Inbox lists remain metadata-only and link
to details; the new acknowledgement shortcut appears on details only.

The URL contains only `notice_id` and the exact **notice** `revision`. It does not
use the potentially newer current comment revision, contain a private-origin
identifier, or create an origin, preview, operation or read marker when listed or
opened. Start `/update_read` privately, then open the signed-in no-script form.
Its two fields are prefilled and remain editable suggestions, not authorization.
Without a current matching private request, there is no preparation form.

Existing strict POST fields and CSRF, own-recipient/current source checks, exact
notice revision, independent grants/pilots, five-minute preview, stale confirmation
protection and retry-safe receipt remain authoritative. Invalid or foreign IDs,
altered revisions, lost permission/source and already-read notices cannot prepare
a new acknowledgement. A cached URL preserves no permission. Neither opening
the form nor reading a thread marks anything read. A successful explicit
confirmation hides the shortcut on refreshed details. Recovering the receipt
never acknowledges a newer revision. No new command, permission, pilot, schema,
dependency or native write service is added.

Service tests cover current consent/pilot, body-SQL denial, maximum-origin reply
budgets and notice/current revision separation. Six synthetic 390×844 no-script
phone flows cover work/task mention/reply/following notices, source-only prefill,
no-origin GET, unchanged pre-confirmation read state, strict CSRF/fields, exact
confirmation, retry/receipt, already-read cached forms and revoked-pilot cached
GET/POST. Hosted/personal acceptance remains Pending.
