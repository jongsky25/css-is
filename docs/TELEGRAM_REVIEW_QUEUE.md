# Private task review queue

Draft PR #572, candidate 9.75. The owner requested a review queue after task action
features. Deployment, preview publication, activation and personal/live testing
remain deferred. Local verification uses synthetic records and blocked providers.

## Commands and independent metadata consent

| Purpose | Command |
| --- | --- |
| List current eligible reviews, newest task ID first | `/review_queue [BEFORE_ID]` |
| Inspect one currently eligible review | `/review_task WORK_ID TASK_ID` |

Separate `tasks.review.read` consent requires `work.read` and default-off host
switch `CSS_TELEGRAM_TASKS_REVIEW_READ_ENABLED`, available work/document modules
and current private inbound/link/delivery/account/chat/bot proof. The checkbox
explicitly covers task, work, owner and deadline metadata. Other task write/read
consents do not grant this queue. Group/topic and direct-worker paths ignore it.
Current menus and consent choices respect the separate pilot.

Results show task/work IDs and bounded titles, current owner's display name and
account ID, For review state and task deadline. The detail has a source work link
for reviewing the submission. Submission/expected-output/body/blocker-note and
review-reason contents are never projected. This explicit metadata scope does not
broaden existing own-task lookup, unified search or brief projections.

## Current source eligibility and separate actions

Only submitted tasks with current native case-officer or confirmed-work-lead
`accept` or `return` authority qualify. Ownership or an officer role for a different
contributing unit alone is insufficient. Source visibility (including every linked
document), open work, active formal-consolidation-review guard and current owner's
native account/document eligibility are checked on every list/detail request.
Completed/closed work, non-For-review tasks, hidden documents, ineligible owners,
lost reviewer rights and active formal reviews are omitted. Unknown/hidden/
ineligible detail IDs share one neutral denial; no hidden counts are returned.

Native blockers can prevent acceptance while return-for-changes remains allowed.
Such tasks can remain in the queue, with acceptance labelled blocked in detail
without disclosing blocker reasons. Accept/return command hints require each
independent write consent/pilot **and** current native action. Queue-only consent
offers source review guidance without advertising unconsented write commands.

Start the offered `/task_accept` or `/task_return`, open its signed-in guide and
enter the shown work/task IDs and reason, then retrieve and confirm its exact
private preview. Reading a queue/detail creates no operation, preview, origin or
source mutation. A listed result never grants future authority: every preparation
and confirmation still performs its own current source checks. After acceptance
or return changes state, fresh queue reads omit that task.

## Bounded paging and delivery

List responses show up to five rows within a UTF-16 message budget. SQL applies
current source visibility and case coordinator filtering before the native scan.
The scan inspects at most 200 permitted candidates in batches of 50 and runs the
canonical source/owner checks rather than duplicating those policies in SQL.
Message-budget or sixth-row lookahead produces a next-page command using the last
shown task ID; remaining eligible rows are never skipped.

If many otherwise visible submitted tasks fail native eligibility, a page may
show no eligible rows and a **Continue** command for older permitted candidates.
This is a bounded scan, not a claim that the entire queue is empty. A one-candidate
lookahead verifies that more SQL-permitted source candidates exist. Such cursors
refer only to visible/coordinator candidates; hidden-source rows are excluded
before limits and are never exposed by pagination. IDs are strictly positive
signed-64-bit integers; arbitrary input gives usage help, with no persisted query.

Reads run within the incoming webhook transaction and recheck current context/
permissions before reply handoff. They retain no names, source bodies or query
projection in deliveries and create no outgoing worker job. Duplicate updates
are not replayed; source/host/scope changes, restore/disconnect and changed bot
proof stop later reads. No cache of record authority is created.

## Verification and deferred acceptance

Use the Python 3.11 isolated commands in [CLOUD_WORKSPACE.md](CLOUD_WORKSPACE.md).
Focused files are `tests/test_telegram_review_queue.py` and
`tests/test_telegram_review_queue_browser.py`. Service checks cover current
review authority, native acceptance blockers, separate action hints, source and
owner visibility, paging/Unicode/scan continuation, formal-review changes, read
revocation/pauses, group/direct denial, duplicate updates and no source or prepared
write effects. Phone cases at 390×844 with JavaScript disabled exercise queue-only
consent and queue → accept/return through the existing signed-in form and exact
confirmation, followed by removal from the queue and disconnection denial.

Exact results are recorded in [SETUP_STATUS.md](SETUP_STATUS.md). All
[live acceptance cases](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md) remain Pending.
No provider registration, real message, scheduler or activation was added.

With independent [blocker metadata consent](TELEGRAM_TASK_BLOCKERS.md), the review
detail also offers `/task_blockers WORK_ID TASK_ID`. Queue consent alone does not
reveal blocker reasons, notes or follow-up identity.
