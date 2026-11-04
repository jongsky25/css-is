# Own discussion following through Telegram

Draft PR #572, candidate 9.81. In review; deployment, preview publication,
activation and personal/live testing remain deferred.

## Guided change and independent consent

Start `/discussion_follow` in your linked private chat. On its signed-in,
JavaScript-free form, enter the work number, optionally enter a task number and
choose **Follow** or **Unfollow**. Leave Task number empty for a work-wide follow.
Prepare the form, retrieve `/discussionfollow_preview OPERATION` in the original
private chat and confirm the exact preview within five minutes.
`/discussionfollow_receipt OPERATION` recovers the original outcome without replay.
Already matching preferences need no operation.

Independent `work.follow` consent and default-off
`CSS_TELEGRAM_WORK_FOLLOW_ENABLED` manage your own follow/unfollow preference.
Both require separate `work.read` consent/pilot and current native work and
every-linked-document visibility. The selected task must belong to that work.
Existing inbox, acknowledgement, mention or comment permissions grant no follow
permission. Following grants no inbox/read-acknowledgement scope, source membership,
document access or authority over another account. Those independent read scopes
are not prerequisites for changing this native Office Connect preference.

## Exact coverage and preserved notice behavior

- A work-wide follow covers new work-level posts and posts in **all task
  discussions** within that work, subject to current source access.
- A task-specific follow covers only that task. Removing it leaves any work-wide
  follow in place, so that task can still produce follower notices.
- Removing a work-wide follow leaves existing task-specific follows in place.
- Existing notices and read markers remain unchanged. Direct mentions and replies
  can still produce notices after unfollowing. No old notices are backfilled or
  deleted, and no bulk unfollow or quiet/mute rule is introduced.

The preview shows the exact work/task ID and title, source discussion link, selected
follow changing from on to off or off to on, and current work-wide coverage when
choosing a task. Other accounts, follower identities/counts, discussion bodies,
authors, task submissions and expected outputs are not retrieved or projected.
The SQL-authorizer test rejects body/submission/output reads during preparation.
Source work/task metadata and linked records are hashed for stale-source checking;
only the actor's selected/work-wide follow rows are read for preference validation.

Following controls eligibility for future **native** follower notices. It does
not enable a scheduler, Telegram/email transport, digest cadence or delivery
preference. Existing native notice priority, recipient eligibility and separately
configured delivery preferences remain authoritative. This does not change task
progress, ownership, deadlines, dependencies, blockers or formal approvals. Native
follow access remains available on terminal discussions when source visibility and
the module allow it.

## Confirmation, source changes and recovery

Preparation, private preview, confirmation and receipts check current account,
bot, connection generation, original sender/chat, grant/pilots, source module and
webhook delivery mode. Groups, topics, foreign contexts and cross-action tokens
cannot change following. Work/source/document changes or selected/work-wide follow
changes invalidate pending previews; an unrelated account's follows do not.
Lost source access hides preview/receipt metadata. Revoking the follow grant or
work read cancels and scrubs pending previews. Disconnect and restore invalidate
the old action context. Confirmed native follows remain Office Connect preferences;
disconnect/revoke does not silently erase them.

The existing native `follow` wrapper now delegates to caller-owned
`follow_in_transaction`. It retains its current visibility, writable-module,
unique-scope and exact own-account insert/delete rules. Telegram source mutation,
operation outcome and private webhook handoff share one transaction. Native,
receipt or handoff failures roll back the preference. Concurrent/duplicate
confirmations do not apply another change. No schema migration is needed.

Receipts distinguish the **recorded** Follow/Unfollow outcome from the **current**
selected and work-wide state. A later source change does not cause recovery to
restore an old preference. Deleted source is reported neutrally without recreation;
existing retention cleanup clears operation source-routing identifiers.

## Isolated verification and later activation

Use [the isolated Python 3.11 wrapper](CLOUD_WORKSPACE.md). Focused files are
`tests/test_telegram_discussion_follow.py` and
`tests/test_telegram_discussion_follow_browser.py`. Synthetic service checks cover
exact own scope/choice, no-op/stale source/current document rights, coverage overlap,
future native notices, preserved existing notices/read state and direct mentions/
replies, private context/grants/pilots, atomic faults, concurrency and retention.
Four 390×844 JavaScript-disabled phone flows cover work/task Follow/Unfollow,
independent linking, CSRF/strict forms, unchanged state before confirmation,
preview coverage, retry/receipt, native future notices and disconnect persistence.
Outgoing providers are blocked. See [evidence and next action](SETUP_STATUS.md)
and the [pending live checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md).
