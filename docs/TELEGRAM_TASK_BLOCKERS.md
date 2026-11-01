# Private task blockers and prerequisites lookup

Draft PR #572, candidate 9.76. The owner approved blocker/prerequisite lookup.
Deployment, preview publication, activation and personal/live testing remain
deferred. Local verification uses synthetic records and blocked outgoing providers.

## Command and independent metadata consent

`/task_blockers WORK_ID TASK_ID [BEFORE_ID]`

Separate `tasks.blockers.read` consent requires `work.read`, default-off switch
`CSS_TELEGRAM_TASKS_BLOCKERS_READ_ENABLED`, source work/document modules and current
private inbound/link/delivery/account/chat/bot proof. The checkbox covers blocker
flags, prerequisite metadata and follow-up owner/date. Review-queue or task-write
consent alone does not grant it. Group/topic and direct-worker paths ignore it.
Current menu and consent choices respect the separate pilot. Own-task and review
details offer the command only when its independent grant/pilot is available.

Any actor who can currently read the source work/task may inspect this metadata;
reviewer/officer authority is not required just to read. Existing own-task lookup,
unified search and daily brief projections are unchanged. A work participant can
inspect same-case prerequisite metadata through this explicit scope without
gaining any task/blocker mutation authority.

## What is shown and what stays in the source

The reply identifies work/task, bounded titles and current task state, then shows:

- Native blocker check: waiting or clear. Other source state/permissions/review
  rules still apply, so clear does not promise submission/acceptance is available.
- Whether an explicit blocker is recorded and whether unresolved changed-direction
  review exists. Canonical native decision/blocker checks supply these flags.
- Follow-up display name/account and date for a recorded blocker, only when the
  account is active and can still read the case. Otherwise a neutral unavailable
  account label replaces the name/ID; the permitted task's follow-up date remains.
- Unfinished same-case prerequisite task IDs, bounded titles, statuses and deadlines,
  with exact `/work/CASE#task-TASK` source anchors.

Free-text blocker/dependency reasons, decision/resolution/discussion notes, expected
outputs and submissions are never projected to Telegram. Follow the source task
link to inspect those contents and resolve issues under normal Office Connect
permissions. An owner who lost source access is not disclosed through a stale
follow-up assignment. Missing/hidden/wrong-case targets share a neutral denial.
A foreign or missing prerequisite edge is refused rather than projected through
an otherwise permitted target; native dependency writes already require one case.

## Native meaning and paging

Only **Done** satisfies a prerequisite. Cancelled is still waiting until explicitly
addressed in Office Connect; the command does not remove dependency edges or accept
cancelled work. Accepted prerequisites disappear from unfinished pages. Source
unblocking, acceptance and direction-review resolution are reflected on the next
read, with no cached authority or state.

Completed work and Done/Cancelled tasks can be read as permitted historical
metadata, with a lifecycle warning. This enables no action. Unlike a write guide,
read-only blocker history does not amend work or invalidate formal reviews.

Each reply lists up to five unfinished prerequisites with a 3,000 UTF-16-unit row
budget plus bounded footer. The query filters same-case and non-Done status before
seek/limit. A sixth row/message-budget cut produces a continuation using the last
shown ID, without skipping eligible rows. IDs must be positive signed-64-bit
integers. An empty cursor page means no unfinished prerequisites **on that page**;
the native waiting/clear check still describes current overall blocker state.

## No resolution or outgoing delivery

Reads run inside the incoming webhook transaction and recheck current account/
chat/bot/scopes/modules before private reply handoff. No task, blocker, decision,
dependency, deadline, operation, preview or origin is written. No message bodies,
follow-up names or query descriptors are retained in delivery/update projections;
no outgoing worker job is created. Duplicate updates are not replayed. Source
visibility changes, lost grants, host/source pauses, restore/disconnect and changed
bot proof prevent later reads. No native work/task/blocker/decision service changed.

## Verification and deferred acceptance

Use the Python 3.11 isolated commands in [CLOUD_WORKSPACE.md](CLOUD_WORKSPACE.md).
Focused files are `tests/test_telegram_task_blockers.py` and
`tests/test_telegram_task_blockers_browser.py`. Service checks cover body exclusion,
source/owner visibility, changed resolutions, accepted/cancelled prerequisites,
Unicode paging, ordinary read actors, historical state, inconsistent edges,
independent hints/consent and private/direct/group/topic/duplicate boundaries.
The 390×844 JavaScript-disabled phone cases use ordinary owner and lead, follow
the exact source link (where the detailed reason is visible), verify no lookup
mutation, and observe a separate native resolution on the next Telegram read.

Exact results are in [SETUP_STATUS.md](SETUP_STATUS.md). All
[live acceptance cases](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md) remain Pending.
No provider registration, real message, scheduler or activation was added.

Recording or clearing has a separate [private confirmation workflow](TELEGRAM_BLOCKER_MANAGEMENT.md).
This metadata lookup remains read only; it does not expose stored reasons or
grant either write consent. Source resolution is still available in Office Connect.

Same-work prerequisite addition/removal are separate confirmed writes; see
[dependency management](TELEGRAM_DEPENDENCY_MANAGEMENT.md). Metadata lookup remains read-only.
