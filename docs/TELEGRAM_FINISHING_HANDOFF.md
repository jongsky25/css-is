# Finish the current Telegram feature batch — three-stage handoff

**November 4 owner update:** reuse the existing bot; a new bot is not required.
The [operator reuse preflight](TELEGRAM_PILOT_OPERATOR.md#existing-bot-reuse--november-4-2026-asiamanila)
supersedes earlier dedicated-bot requirements. Production release remains deferred.

Updated November 3, 2026. Repository: `jongsky25/css-is`.
Review branch: `feat/telegram-private-work-lookup`.
Draft [PR #572](https://github.com/jongsky25/css-is/pull/572).
Candidate application version: **9.91**.

## Current finishing-session result

**New owner instruction: “do stage 2”.** The isolated test scope is authorized;
follow the [operator runbook](TELEGRAM_PILOT_OPERATOR.md). Do not request this
authorization again. Dedicated bot/participant/password setup and actual receipt
are still prerequisites. Stage 3/production remains deferred. Earlier blanket
stage-2 deferrals below describe historical instructions and are superseded.

See [status](SETUP_STATUS.md#next-action) for inspected-head CI/rules evidence and
[the concrete stage-2 pilot plan](TELEGRAM_STAGE2_PILOT_PLAN.md) for the proposed
HF target, test bot, visibility decision, fixtures, switch batches and blockers.
Final checks for the documentation save belong to its actual SHA and are recorded
in PR #572. Do not transfer `edcc437` results to that new head. Publication,
activation, real messages and stage-3 production release remain deferred.

## Latest owner direction and authorization

The owner asked how much remained, accepted the three-stage completion framing,
and requested this full handoff for a new session. **Stop proposing/adding optional
features.** Finish this batch through checks, agreed acceptance and an explicitly
authorized release. CI/pilot findings may be fixed on the review branch.

This handoff request authorizes documentation/continuity work; it does **not**
revoke the owner's earlier deferral of deployment, preview publication/replacement,
activation, real messages, personal/live tests or main merge. In the next session:

- Complete stage 1 and concrete read-only/local preparation autonomously.
- Prepare a specific test target, source/version, feature/account allowlist and
  test plan before requesting the owner's test-publication/activation/live-message
  approval. Ask only for decisions or missing access that actually block that plan.
- Preview/personal acceptance alone is not production release authorization.
  Prepare the exact release candidate and obtain an explicit production instruction
  before main merge/deploy or production feature changes.
- If the owner subsequently explicitly authorizes an action, honor that scope and
  proceed; do not ask repeatedly for the same authorization.

All components remain on Hugging Face unless the owner changes that requirement.
Do not introduce another hosting provider, outbound proxy or paid resource as a
routine fix. No production database is a development fixture. Keep secret values,
private identities, tokens, cookies and message bodies out of chat/GitHub evidence.

## Start the new session

Select this repository and review branch, not main. Read, in order:

1. [AGENTS.md](../AGENTS.md), [cloud collaboration](CLOUD_COLLABORATION.md),
   [current status](SETUP_STATUS.md), and this handoff.
2. [Telegram plan/progress ledger](TELEGRAM_TWO_WAY_PLAN.md),
   [mobile history](TELEGRAM_MOBILE_HANDOFF.md), and
   [live acceptance checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md).
3. [Mobile workflow](MOBILE_CLOUD_WORKFLOW.md),
   [cloud workspace](CLOUD_WORKSPACE.md), [dependencies](DEPENDENCIES.md),
   [release gates](RELEASE_GATES.md), and current workflow files.
4. Before hosted work, [preview setup](HF_PREVIEW_SETUP.md),
   [operations evidence](OPERATIONS_ACCESS.md), [DEPLOY.md](../DEPLOY.md),
   [webhook replies](TELEGRAM_WEBHOOK_REPLIES.md), and
   [private guided replies](TELEGRAM_PRIVATE_MEETING_WEBHOOK.md).

Verify fresh GitHub/cloud access, current branch, clean/dirty tree and latest
local/remote/PR heads. Preserve any existing work. Fetch actual main and the review
branch; never force-push or discard another session's commits. Parallel work has
already occurred here. Current actual main was `625c60f2fc91ddf98519a9084a5c4217fd1f2e56`
(released 9.62, avatar CI repair #580). Recheck it; metadata/historical notes are
not proof of today's hosting or rule settings.

Useful read-only checks:

```bash
git status --short --branch
git log -5 --oneline
git ls-remote origin refs/heads/feat/telegram-private-work-lookup refs/heads/main
```

The last application commit before this handoff is
`1f25bbdbd5720873f2adea778e91ba13acd45395`. This handoff is saved in a **later
documentation commit**: inspect the actual PR head and its own checks. A new
push can cancel/restart previous-head workflows; neither previous green jobs nor
cancelled runs establish the current head's acceptance.

## What is already implemented

The draft is a broad private Telegram interface with independent default-off
pilots/consent and native authority, not a blanket permission grant:

- Calendar/room reads; private guided plain meeting creation/reschedule/cancel,
  room request/withdraw/date move and combined meeting/room recovery.
- Work/task/document metadata, own supplies/travel/meals/arrangement status,
  metadata search, review/blocker lookup, menu/status and requested daily brief.
- Exact confirmed task workflows: proposal, acknowledgement/submission, officer
  assignment/reassignment/deadlines/reopening/cancellation/review, blockers and
  prerequisites. Formal source review/official approvals remain authoritative.
- Discussions: posts/replies/eligible mentions, author-only edits, own inbox,
  confirmed own-notice read acknowledgement, follow/unfollow/saved follows,
  independently consented search, bounded root/direct/nested reading and fixed
  revision-bound message parts, plus permission-checked reply/edit/navigation/
  acknowledgement shortcuts. Reading alone changes no read/follow state.
- [Own supply drafts](TELEGRAM_SUPPLY_DRAFTS.md): active catalog search/25-row pages,
  five lines, 1000-character purpose, native requester/availability checks and
  exact private confirmation; no submission/number/approval/hold/mail.
- [Own supply submission](TELEGRAM_SUPPLY_SUBMISSION.md): independent submission
  consent, existing own draft/returned request and exact revision; complete
  request/requester/items/quantities/routing preview; native number/immutable
  version/approval-mail queue/outcome/handoff atomicity. Zero approvers warns;
  returned requests keep their number. Historical receipts never resubmit or
  overwrite later decisions/edits. Approval/reservation/issue remain separate.

Behavior guides and the plan are the detailed contracts. Source-only form links
create no origin/operation/write on GET. Original private requests, signed-in
strict CSRF forms, current source/grants/revisions, exact previews and explicit
confirmation are still required. Do not weaken these for testing convenience.

The owner reported successful hosted linking/calendar retrieval on an older
release. That does not establish live acceptance of this unpublished batch.
New private features, group/scheduled delivery and the complete T4.4 pilot are
not established live. Natural-language commands, automatic task notifications
and later-module expansion are outside this batch's completion scope.

## Stage 1 — finish verification and fix actual failures

Observed on application head `1f25bbd` while preparing this handoff:

| Check | Observed result |
| --- | --- |
| [CI 41634542460](https://github.com/jongsky25/css-is/actions/runs/41634542460) | In progress: complete normal and shuffled suites still running |
| CI release metadata | Passed |
| CI dependency/container audit | Passed |
| [Avatar acceptance 41634542442](https://github.com/jongsky25/css-is/actions/runs/41634542442) | Passed |
| Local relevant regressions | 483 passed, including five no-script phone flows |
| Local shuffled group (seed 311) | 478 passed |
| Local action/release/bundle/diagnostic group | 77 passed |

Local groups overlap; reports had no failures/errors/skips. Full local repository
suites were not run. Reports under `/workspace/supply-submit-*.xml` are disposable
workspace artifacts, not guaranteed available in the new session. Durable results
and earlier fixture corrections are in status/plan. Starlette/httpx deprecation
warnings remain; no dependency changes were introduced.

Known failures and repairs to preserve:

- Old avatar setup pinned a Debian Chromium package no longer available. It now
  uses the fixed browser revision selected by the hashed Playwright lock.
- Native visibility subsequently crashed after 131 passing tests. Diagnostic
  capture and 1 GiB container shared memory were preserved, then released in main
  9.62 (#580). Avatar acceptance passed on the current application head. See
  [investigation](AVATAR_CRASH_INVESTIGATION.md); do not revert the repair or
  weaken assertions/timeouts to obtain a green run.
- Previous head `585a9cb` full normal/shuffled CI each had 10,483 passes and one
  failure: max-origin fully enabled menu **4121 > 4096 UTF-16 units**. Current
  code shortens descriptions and status prerequisites/paused reasons, preserving
  every command, feature label and permission. The original regression and seven
  status-state budgets pass locally. Keep both menu and status within the limit.
- Actual main 9.62 was merged into review at `78a160c`; all **661** actual-main
  release entries were verified unchanged. Candidate version/cache is 9.91.

Stage-1 actions:

1. Inspect the **actual current head's** normal/shuffled, JUnit/no-skips/AI evidence,
   dependency/container, metadata, aggregate Required checks and avatar results.
   Read failed logs/steps. Distinguish pending/cancelled/setup/test failures.
2. Fix real failures on the review branch, with focused checks and appropriate
   regressions. No ignored failures, weakened assertions, removed gates, skipped
   tests or backup/version bypasses. Rerun flaky failures only with evidence and
   record any unresolved flakiness honestly.
3. Use Python 3.11 and hashed locks. Fresh setup:
   `bash scripts/cloud_setup.sh`; then
   `.venv/bin/python scripts/cloud_workspace.py doctor`.
   Run application tests through the wrapper with fresh synthetic basetemps under
   `/workspace/office-test-tmp/`, reports outside those directories, and blocked
   providers/disabled schedulers. Never start against inherited production data.
4. Useful current focused group: `tests/test_telegram_supply_submit.py`,
   `tests/test_telegram_supply_submit_browser.py`, draft/read/action/storage/menu/
   dependency-manage/MCP-supply suites and deployment/release tests. The existing
   max-origin regression is in `tests/test_telegram_dependency_manage.py`.
5. Reconcile newer main without losing releases or parallel changes. Runtime
   changes need synchronized `version.py`, `CHANGELOG.md`, `static/js/sw.js` and
   updated plan/status/runbooks. Documentation-only updates need link/diff checks.
6. Push only the review branch; keep PR draft during preparation. Verify local,
   remote and PR heads match and inspect newly triggered checks. Do not transfer
   evidence from another head. Freeze the eventual tested candidate before pilot.

Stage 1 is done when every required gate and avatar acceptance is green on the
frozen current candidate, main freshness/reviews are reconciled, and no known
acceptance-blocking defect is left. This alone authorizes no publication/release.

## Stage 2 — approved test target, acceptance and pilot fixes

First prepare a concrete plan identifying source/version, target, accounts/roles,
selected flags/consents, synthetic fixtures, real provider actions and rollback.
Then request the specific outstanding test-publication/activation/message approval.
Do not ask the owner to approve an abstract deployment before doing the preparation.

### Important existing-preview limitation

The existing private preview is
`equityinhealth/office-connect-preview`; production is
`equityinhealth/office-connect`. Preview setup documentation contains historical
source/version values—verify actual current hosting before replacing it.

`python scripts/deploy_preview_hf.py` is a dry run; `--publish` writes the shared
preview and needs approval, a clean committed tree, scoped `HF_TOKEN` and remote
`OFFICE_PREVIEW_PASSWORD`. Verify private visibility, source SHA, RUNNING,
`/preview-health`, PREVIEW banner and environment header after an approved publish.
Synthetic login is `preview@example.invalid`; the password stays in its secret
location/password manager, never chat. Data/sessions reset on restart. Serialize
publishes so another session's preview is not silently replaced.

**The current preview is not a real Telegram pilot environment.**
`scripts/preview_app.py` clears integration credentials/flags, blocks non-loopback
outbound sockets, disables scheduling and creates a disposable database. A private
Hub-authenticated Space may also be unreachable by Telegram's webhook delivery.
Publishing it unchanged does not activate/test real bot linking, confirms,
notifications, reminders or outgoing provider delivery.

Do not silently weaken its isolation, insert production credentials, attach
production storage or redirect the production bot to make the test appear to work.
Separate UI review from end-to-end provider acceptance. For real Telegram tests,
prepare an agreed isolated Hugging Face test target/profile with synthetic data,
a **dedicated test bot**, reachable authenticated webhook, limited flags/accounts
and known restart behavior. Resolve Space/webhook reachability and source-visibility
requirements before publication. One bot has one webhook; replacing the existing
production bot's registration disrupts it. New target/configuration, webhook
registration, real messages and scheduler enablement need explicit scoped approval.
If a safe pilot target/access is unavailable, record that blocker and the concrete
unblock plan; do not move writes to production or claim mocked evidence is live.

### Acceptance batches

Use the [full pending checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md) and behavior
guides. It contains many cases, not three individual tests. Agree the capabilities
to be released; track each applicable case with exact source/deployment, synthetic
role/context, expected/observed result and pass/fail/pending evidence. Suggested
phone-sized batches:

1. **Link/discovery:** `/start` → browser explicit scopes → private `/status` →
   `/confirm`; menu/help/status and max enabled feature set. Do not send another
   `/start` while a claimed challenge awaits confirmation; it replaces that code.
2. **Calendar/rooms:** reads, guided meeting, pending room request, normal approval,
   status and recovery; recurrence/managed/foreign/conflict denials as applicable.
3. **Work/tasks:** permitted metadata, owner and officer roles, proposal/assignment,
   acknowledgement/submission/review, deadlines/blockers/dependencies. Preserve
   formal-review/source permissions and independently consent each action.
4. **Discussions:** separate reading/search/mentions/write grants, own/foreign edit
   controls, bounded nested pages/parts, stale revisions, follow coverage, own inbox
   and explicit notice-revision acknowledgement. Reading marks nothing read.
5. **Supplies:** catalog draft → one own draft/no number → separate submit consent
   → exact full/routing preview → one normal number/version/mail queue. Returned
   resubmission keeps the number. Zero approvers warns; no approval/stock hold.
   Real email delivery is a separate agreed action; do not notify real staff.
6. **Other private reads:** permitted documents and own travel/meals/arrangements;
   compare metadata/source status without exposing excluded bodies/files/notes.
7. **Lifecycle/recovery:** revocation, pause, disconnect, lost source, stale cached
   forms, duplicate confirmation and receipt recovery. Use synthetic isolated data
   for fault/rollback tests; do not corrupt live data to provoke errors.

Create the native fixtures/roles these flows actually require. The standard UI
preview seeds only a synthetic admin and organization structure, not the internal
staff linkage, colleague/officer roles, source documents/work, supply catalog,
stock or approvals necessary for these tests. Native rules must not be bypassed
by treating technical administration as universal authority.

Private webhook `sendMessage` responses are recorded as uncertain one-time
handoffs. HTTP 200/database handoff proves neither user receipt nor reading;
record the owner's actual receipt. Never replay old uncertain sends. Historical
Requests/HTTPX outgoing timeouts were observed on HF; current connectivity must
be checked with safe Operations diagnostics, not assumed permanently broken/fixed.
Scheduled/group delivery, membership checks and reminders use the outgoing path
and are not proven by interactive private replies. Verify them separately only
if included in the approved pilot. Keep full T4.4 incomplete otherwise.

For every defect, fix the review branch, retest, record evidence and obtain fresh
head checks. If code changed, the prior hosted source/acceptance is stale; reconcile
what needs retesting and republish only within the owner's authorization. Do not
mark the entire checklist passed from a screenshot, mocks or one successful command.

Stage 2 is done when the agreed release matrix passes, the owner explicitly accepts
the actual tested candidate, defects are resolved, and remaining exclusions are
recorded. UI-only success is not provider acceptance. Keep unreleased group/
scheduled features disabled and T4.4 pending if not in scope.

## Stage 3 — explicitly approved production release and selected activation

Prepare the exact candidate SHA/version, green gates/reviews/main freshness,
acceptance evidence, feature/account allowlist, persistence/backup verification,
monitoring and rollback before requesting the final production instruction.
A clear instruction can name PR #572, the reviewed SHA/version, authorization to
merge/deploy via canonical gates, and separately which pilots/accounts/provider
operations may be enabled. Do not infer all-feature activation from a code release.

After the owner explicitly authorizes that concrete scope:

1. Recheck actual main, PR head/base, rules/reviews, green exact-head gates, merge/
   deployment activity and accepted source. Any new merge conflict/runtime change
   requires reviewable reconciliation and fresh verification. Do not merge on
   cancelled/old-head checks or bypass protection.
2. Read `.github/workflows/deploy-hf.yml`, current `deploy_hf.py`, release/backup
   guidance and effective hosted persistence/configuration. `DEPLOY.md` includes
   obsolete DB-carrier instructions. Current storage was previously observed with
   `CSS_PERSIST_DIR=/data`; reverify effective mounts/variables rather than assuming.
   Do not run ad-hoc deployment against the workspace's synthetic DB or upload it
   as a live seed. If persistence cannot be verified, stop and resolve that access.
3. Merge only the approved PR/source. A main push/merge triggers the canonical
   serialized main-only workflow: complete verification → fresh verified predeploy
   backup → strict-version/code deployment → hosted version/source checks → safe
   Telegram Operations diagnostics. Preserve every gate; no `--skip-backup`,
   `CSS_DEPLOY_SKIP_BACKUP`, manual seed replacement or alternative uploader.
4. Verify the workflow on the **actual merged main SHA**, deployment/Space source,
   expected application version, RUNNING/health/login and persistence/backup
   outcomes. Successful upload is not the final result. Keep staff data/credentials
   out of reports; inspect only necessary safe diagnostics/aggregate evidence.
5. Enable only the separately approved pilots/configuration and named account
   consents. Fresh opt-in does not replace native roles/source permissions. New
   features remain default-off after deployment; old grants do not widen. Verify
   approved live outcomes/receipt using agreed synthetic accounts/records only.
6. Monitor approved paths and record exact version/source/flags/outcomes. On failure,
   pause affected delivery/pilots and preserve uncertain/committed work. A rollback
   never recalls delivered messages, reverses records or silently retries uncertain
   sends. Do not restore production data or change storage topology as an incidental
   code rollback; use separately approved recovery procedures. Old snapshots can
   lose newer tombstones; no exactly-once restore guarantee is established.
7. Update PR/plan/status/checklist with confirmed merge SHA, deployed source/version,
   selected activation and actual live evidence, open issues and operator rollback.
   Mark implemented/merged/deployed/pilot-verified separately. Do not claim full T4.4
   if group/scheduled/outgoing/revocation/rollback evidence is still missing.

Stage 3 is done when the authorized release is actually deployed/verified,
selected activation passes its agreed live checks, rollback/operations handoff is
recorded, and the owner knows exactly what is enabled and what remains deferred.
Optional backlog items are not prerequisites for closing the current private batch.

## Saving progress and credentials

Use connected GitHub tools when sufficient; shell Git and connector credentials
are separate access paths. Current-session access is not proof in a new session.
Secret names/locations only: cloud/preview `HF_TOKEN`, preview
`OFFICE_PREVIEW_PASSWORD`; canonical GitHub deployment `HF_TOKEN`, `CSS_ADMIN_USER`,
`CSS_ADMIN_PASS`; approved bot host `CSS_TELEGRAM_BOT_TOKEN`,
`CSS_TELEGRAM_WEBHOOK_SECRET`. Verify scope/readiness without printing values.
Do not copy credentials from production to tests or ask for them in chat.

Maintain [status](SETUP_STATUS.md), the plan and checklist after material changes.
Push relevant source/docs only to the review branch, update draft PR metadata,
and verify local/remote/PR heads. Never commit environments, DBs, backups, provider
logs, cookies or local test scratch. Report any unsaved work explicitly. The next
session should end each stage with a short outcome, actual evidence, limitations
and precise next action, rather than another open-ended feature recommendation.

## Copy/paste prompt for the new session

> office connect. Finish the current Telegram feature batch in draft PR #572,
> repository jongsky25/css-is, branch feat/telegram-private-work-lookup. Read
> AGENTS.md, docs/SETUP_STATUS.md, docs/TELEGRAM_FINISHING_HANDOFF.md,
> docs/TELEGRAM_TWO_WAY_PLAN.md and the live acceptance checklist. Freeze optional
> features. Verify actual heads/main/access and current CI, fix stage-1 failures,
> then prepare the concrete stage-2 pilot and acceptance plan. The existing private
> preview blocks integrations and is not proof of real Telegram delivery. Keep
> publication, deployment, activation, real messages and main merge deferred until
> I explicitly approve each required scope; preview acceptance alone is not
> production release approval. After accepted testing and my explicit release
> instruction, complete stage 3 through canonical verification/backup gates and
> verify actual deployment/selected activation. Save progress and evidence to the
> review branch and keep stage status accurate. Do not add optional features or
> treat old-head/local/mock evidence as current live acceptance.
