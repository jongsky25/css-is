# Office Connect Telegram — mobile handoff

Updated: November 3, 2026. This document is a handoff, not release approval.

## Current priority: close the batch

The owner now requests completion of the three stages, with optional features
frozen. Use [TELEGRAM_FINISHING_HANDOFF.md](TELEGRAM_FINISHING_HANDOFF.md) as the
current startup prompt, exact source/check snapshot, pilot planning and release
authority guide. Earlier feature recommendations below are historical. The
handoff request did not itself authorize deployment, publication, activation,
real messages or main merge.

## Start the next chat

Attach or select repository **`jongsky25/css-is`** and branch
**`feat/telegram-private-work-lookup`**, then send:

> office connect. Continue the Telegram integration in draft PR #572. Read
> AGENTS.md, docs/CLOUD_COLLABORATION.md, docs/SETUP_STATUS.md,
> docs/TELEGRAM_MOBILE_HANDOFF.md and docs/TELEGRAM_TWO_WAY_PLAN.md. Verify the
> current branch, main, access and PR checks. Tell me the next useful feature and
> carry out the feature I approve. Keep the handoff current and save changes to
> the review branch. I will do personal/live testing later; do not deploy,
> publish a preview, activate features, send real messages or merge to main.

The shorthand **office connect** is defined by the repository's AGENTS.md, not
as a global command. If a new chat cannot see this repository and branch, attach
or select them first. GitHub authentication and cloud workspace access must be
verified again in that session.

## Current work and owner preferences

- Draft [PR #572](https://github.com/jongsky25/css-is/pull/572); branch
  `feat/telegram-private-work-lookup`; candidate **9.91**. The prior application
  baseline was `585a9cb` (own supplies drafts), with actual main `625c60f`
  (9.62) merged into review. Own supplies submission is now implemented; see the latest progress entry below and check the PR head.
- The owner has linked Telegram and reported pulling calendar information. That
  report does not establish that the new draft features have been deployed or
  tested live. The owner wants more capabilities added first, then will do
  personal/live testing later. Local isolated automated tests are appropriate.
- The usual pattern is: owner asks “what is next?”, assistant recommends one
  concrete useful feature, and implements it when the owner says “do it”.
  Preserve existing decisions and use judgment; avoid asking for routine choices.
- Production deployment, main merge/push, preview publication/replacement,
  activation, live/personal tests and real provider messages remain deferred.
  No such action is authorized merely by continuing the feature work.

## What is in the draft

The draft expands private Telegram work beyond calendar lookup. Features use
independent default-off pilots and delegated consent; existing native visibility,
linked-document permissions and business authority still apply.

- Permitted task/work and document metadata lookup, personal request statuses,
  unified metadata search, private menu/status and staged daily brief preferences.
- Guided task proposals, acknowledgement/submission, deadlines, review,
  assignment/reassignment, reopening/cancellation, blockers and prerequisites.
- Guided plain meeting creation/rescheduling/cancellation and room requests,
  withdrawal/date moves, with native approval and recovery rules preserved.
- Work/task comments, replies, eligible mentions, own-comment editing and reply
  shortcuts. Writes use signed-in forms, exact private previews, current-source
  rechecks, explicit confirmation and non-replaying receipts.
- An own-recipient discussion inbox and explicit, separately confirmed read
  acknowledgement; follow/unfollow plus a saved-follow list. Work-wide follows
  also cover task discussions; task-specific follows remain independent.
- Separately consented exact-thread discussion search with short current-revision
  excerpts, and selected comment/direct-reply views with nested navigation and
  revision-bound message parts. Text copied to Telegram remains in that chat.
  Search/reading alone do not mark messages read.

Use the [Telegram plan and progress ledger](TELEGRAM_TWO_WAY_PLAN.md),
[current status](SETUP_STATUS.md), [reply shortcuts](TELEGRAM_REPLY_SHORTCUTS.md),
[discussion reading](TELEGRAM_DISCUSSION_READING.md),
[discussion search](TELEGRAM_DISCUSSION_SEARCH.md), and the
[pending live acceptance checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md) for
specific permissions, commands, limits, evidence and earlier increments. The
PR description also summarizes the broader feature set. The source and current
PR status take precedence over historical notes.

## Verification and current CI issue

For application commit `222f13b`, isolated Python 3.11 checks passed: **873
regressions**, **832 shuffled** (seed 311), **77 focused**, and **8 phone-flow**
checks; each cited report had no failures or skips. Groups overlap. Phone checks
used synthetic data and JavaScript-disabled browser automation, not the owner's
personal/live acceptance. Release metadata, lock inputs, vendor integrity,
installed compatibility, AI contract, compilation, main release history, local
Markdown links and whitespace were checked as recorded in SETUP_STATUS.md.

On November 3, the `functional` CI job for **`222f13b` failed during dependency
installation, before its tests**: Debian no longer supplied the pinned Chromium
and chromium-common version `156.0.8078.73-1~deb13u1` (apt exit 100). The job is
[here](https://github.com/jongsky25/css-is/actions/runs/41568914035/job/125696996825).
Metadata passed and other release checks were still running when inspected.
This is not evidence that the Telegram feature failed; it is an unresolved CI
blocker. A later documentation push starts checks for a new head, so inspect the
actual head and fresh logs before reporting current CI. Do not bypass or weaken
the required gates. Investigate the pinned browser availability and the repository's
avatar/release workflow; make any appropriate fix on the review branch and verify it.

Actual main was `25fe812` (code version **9.61**) when inspected; fetch again.
Main contains companion refinements merged into the review branch, with released
changelog entries preserved. Main is production-connected: a main push/merge
triggers deployment. All full CI and release/backup gates remain required before
any separately authorized promotion.

## Safe development and saving progress

1. Read AGENTS.md and the [cloud/mobile workflow](MOBILE_CLOUD_WORKFLOW.md). Check
   branch, working tree, current main and current PR head/checks; preserve work.
2. Use Python 3.11 and [isolated cloud commands](CLOUD_WORKSPACE.md). Run tests
   through `.venv/bin/python scripts/cloud_workspace.py test ...`; use synthetic
   data, disabled schedulers and blocked providers. Never use production data.
3. For long or concurrent suites use separate fresh `--basetemp` directories under
   `/workspace/office-test-tmp/`; keep JUnit reports outside those directories.
   Remove only completed synthetic scratch. Local `/tmp` reports are not durable.
4. For a user-visible change, synchronize `version.py`, `CHANGELOG.md` and
   `static/js/sw.js`; preserve actual main release history. Update the Telegram
   plan, status, relevant behavior guide and pending live checklist. Verify the
   applicable normal/shuffled checks, metadata and links; report exact results.
5. Commit and push only the review branch, update draft PR metadata and verify the
   local/remote/PR heads and draft status. New CI belongs to the new head: do not
   transfer a previous head's passing results. The current draft is not live.

Do not put secrets, personal records or raw production logs into the chat or
repository. Historical seasonal/monitoring notes are preserved in the status file;
they do not override the owner's current Telegram scope or deferred live work.

## Fresh-session inspection — November 3, 2026

At `3cea8f5`, full normal/shuffled, dependency/container, metadata and aggregate
CI passed in run 41569265716. Separate avatar functional run 41569265827 again
failed before tests because the same Chromium pin was unavailable. Main remains
`25fe812`. See the latest SETUP_STATUS.md entry for links.

Next feature recommendation awaits owner approval: bounded private top-level
discussion browsing for one work/task, with older pages and existing thread,
message and reply navigation. Reuse independent read consent and preserve all
read/notice/follow state. No feature implementation has started. Publication,
activation, deployment, main merge and personal/live testing remain deferred.
These results describe the inspected head; inspect fresh checks after this save.

## Approved browsing implementation — November 3, 2026

Discussion browsing is now implemented in draft candidate 9.86, with
`/discussion_browse WORK_ID work|TASK_ID [before:COMMENT_ID]` and existing
thread/message/source/reply navigation. [Behavior](TELEGRAM_DISCUSSION_BROWSING.md).
291 regressions (6 phone flows) and 285 shuffled checks passed without skips;
groups overlap. See SETUP_STATUS.md for scope, reports and metadata checks.
Avatar CI setup uses the hashed Playwright lock's fixed browser revision instead
of the unavailable Debian Chromium pin; local alias launch passed, fresh actual
CI remains required. Inspect the new PR head and all checks. No deployment,
preview, activation, main merge, real send or personal/live testing occurred.

## Latest navigation increment — November 3, 2026

Candidate 9.87 adds independently reading-consented inbox → current thread and
followed scope → browse commands. See [behavior](TELEGRAM_DISCUSSION_NAVIGATION.md)
and the latest status/plan entries. 302 regressions (including 10 phone flows)
and 292 shuffled checks passed without failures/skips; groups overlap.

Previous head `df55759` passed full CI and locked-browser installation. Avatar
acceptance passed 131 tests before the native visibility test's browser crashed
at the profile animation query; root cause remains unproven. No avatar gate was
changed in this increment. Inspect fresh-head CI and investigate any continuing
crash before promotion. Deployment, previews, activation, real sends, main merge
and personal/live testing remain deferred.

## Latest acknowledgement shortcut — November 3, 2026

Candidate 9.88 adds an independently permitted notice ID/revision form shortcut
from unread update details. Listing/opening it creates no private origin, preview,
operation or read marker. Fresh `/update_read`, signed-in strict form, exact
private preview and confirmation remain required. See [behavior](TELEGRAM_UPDATE_READ.md).
400 regressions (six no-script phone flows), 394 shuffled checks and five
supplementary Unicode/budget checks passed without failures/skips; groups overlap.
See latest status/plan evidence for reports and limits.

Previous head `3dc7600` passed full CI; avatar acceptance again crashed in native
visibility after installation and 131 passing tests. Inspect fresh-head CI and
resolve the browser crash before any separately authorized promotion. Deployment,
previews, activation, real messages, main merge and personal/live tests remain
deferred. No avatar workflow change in this increment.

## Latest own-message edit shortcuts — November 3, 2026

Candidate 9.89 adds author-only edit form URLs to current reading views under
matching independent edit permission. Source IDs/revision prefill; replacement
text stays empty; no origin/operation/edit is created by opening. Existing exact
private preparation/confirmation and current ownership/source/revision checks
remain required. [Behavior](TELEGRAM_COMMENT_EDITING.md).

539 regressions (ten phone flows), 529 shuffled checks and 30 combined shortcut/
phone checks passed without failures/skips; groups overlap. See latest status/
plan evidence. Combined controls retain nested seek paging and fixed message
parts at maximum supported IDs/revisions/origin; thread previews are shorter
when edit controls are enabled.

Prior head `c14c205` full CI was still running at last inspection; avatar
acceptance again crashed in native visibility after 131 passing tests. Inspect
fresh exact-head checks; root cause remains unproven. No avatar gate changed.
Deployment, previews, activation, real messages, main merge and personal/live
testing remain deferred.

## Latest guided supplies draft increment — November 3, 2026

Candidate 9.90 adds `/supply_draft` with independent default-off creation consent
and supplies read prerequisite. A signed-in no-script catalog form supports five
lines and 1000-character purpose; exact private preview and confirmation create
one own native draft. Submission, control numbers, approval, inventory holds/issues
and approver mail remain separate. [Behavior](TELEGRAM_SUPPLY_DRAFTS.md).

374 regressions (two phone flows), 372 shuffled checks and 41 release/bundle/
diagnostic checks passed without failures/skips; groups overlap. See latest status
and plan for reports, constraints and fixture corrections. No full local suite.

Four incoming avatar CI-investigation commits through `e7bea14` are preserved.
Avatar acceptance passed on that head after diagnostics/shared-memory changes;
full CI was still running at last inspection. Inspect the new feature head's own
CI/acceptance. Deployment, previews, activation, real messages, personal/live
testing and main merge remain deferred.

## Latest own submission increment — November 3, 2026

Candidate 9.91 adds independent `/supply_submit` for one own draft/returned request.
Supplies read is required; draft consent is neither sufficient nor required.
Source-only request/revision form → exact full private preview → confirmation
uses native numbering, immutable submitted version and approval mail queue, with
original/current receipt recovery. Approval and inventory effects stay separate.
[Behavior](TELEGRAM_SUPPLY_SUBMISSION.md). Real messages remain deferred.

483 regressions (five no-script phone flows), 478 shuffled checks and 77 action/
release/bundle checks passed without failures/skips; groups overlap. Menu/status
wording now fits maximum origin length while retaining every command/label and
permission; this fixes the prior full-CI failure. See latest status/plan evidence.

Actual main `625c60f` (released 9.62 avatar repair #580) was merged into review
with all 661 released changelog entries preserved. Previous feature head passed
avatar acceptance but failed full CI on menu size. Inspect new exact-head checks
before promotion. Deployment, previews, activation, personal/live testing and
main merge remain deferred; no production action occurred in this work.
