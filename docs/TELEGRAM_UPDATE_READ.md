# Explicit discussion read acknowledgement

Draft PR #572, candidate 9.80. In review; deployment, preview publication,
activation and personal/live testing remain deferred.

Start `/update_read` in your linked private Telegram chat. Its signed-in,
JavaScript-free form accepts one own notice ID and its exact notice revision,
as shown by `/update_status NOTICE_ID`. Read the discussion in Office Connect
before confirming. Prepare the form, retrieve `/updateread_preview OPERATION`,
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
