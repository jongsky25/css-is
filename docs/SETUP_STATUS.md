# Cloud/mobile setup status

Updated: 2026-11-01. Repository: `jongsky25/css-is` (Office Connect BLHSD).
Integration branch: `setup/cloud-mobile-continuity`; default startup branch after
merge: `main`.

## Collaboration workflow ready — operational follow-ups tracked separately

Completed: root `AGENTS.md`, the new-chat handoff in
`docs/CLOUD_COLLABORATION.md`, this checklist, and a README entry point.
Saved on GitHub branch `setup/cloud-mobile-continuity`; initial implementation
commit `d9d13e5`. All local Markdown links across the four changed files resolve;
`git diff --check` passed. Application tests were not run for documentation changes.
No application behavior, secrets, deployment settings, or live data changed.

The user shorthand **office connect** is now defined in root `AGENTS.md`.
It resumes the next unfinished setup step when these repository instructions
are available. It is not a globally registered chat command; repository/branch
access remains necessary in a fresh chat.

## Step 2 evidence — 2026-10-31

- Added `scripts/cloud_setup.sh`, `scripts/cloud_workspace.py`, and
  [cloud commands and isolation details](CLOUD_WORKSPACE.md).
- Installed CPython 3.11.17 with uv into this workspace and created ignored `.venv`.
  Installed `requirements-test.txt` using pip's hash verification and wheel-only
  policy. `pip check` passed. Default system Python remains 3.12; use `.venv`.
- Verified Node v24.19.0 and Tesseract 5.5.0 with English data.
- System-package installation through Playwright failed because su privileges
  are unavailable. Existing image libraries were sufficient: Playwright's pinned
  Chromium/headless shell downloaded successfully, and doctor launched a real
  headless page. Setup now makes system-package installation an explicit opt-in.
- `bash scripts/cloud_setup.sh` completed successfully on rerun with cached
  dependencies; doctor also passed independently. A separate fresh cloud image
  was not provisioned in this step; missing base-image prerequisites fail visibly.
- Isolation check confirmed inherited fake credentials/persistence paths were
  excluded, scheduler disabled, database precreated to prevent seed copying,
  and temporary database removed after completion.
- Temporary uvicorn server started on loopback port 8765; `/login` returned HTTP
  200 with a form; server was stopped after verification.
- 83 authentication/RBAC/document OCR tests passed in 13.16s. Three appearance
  browser tests passed in 13.13s using the image's `/usr/bin/chromium` (the tests
  prefer it). Both JUnit reports passed the no-failures/no-skips gate. The doctor
  separately verified Playwright's downloaded browser.
- Shell syntax, Python compilation and `git diff --check` passed. Full normal/
  shuffled suites, release metadata and dependency audits were not run; existing
  release gates still apply before merging. No public preview or release created.
- Logs/reports are local `/tmp/office-*` evidence, not durable artifacts; this
  summary and reproducible commands are saved in GitHub with the setup work.

## Evidence inspected

- GitHub connector successfully listed this repository with read/write access.
- Workspace origin is `https://github.com/jongsky25/css-is.git`; initial working tree
  was clean on branch `work`.
- Managed environment reports running/connected and an enforced unrestricted HTTP
  policy. It reports no configured secret bindings or outbound cloud identities.
  This does not prove every service credential is absent or every API is authorized.
- Repository is FastAPI/Jinja; Docker and CI specify Python 3.11.
- PR CI already calls shared release checks, including Chromium and OCR prerequisites.
- `.github/workflows/deploy-hf.yml` deploys main to Hugging Face after verification.
- Live branch/rule inspection confirms the branch-protection enforcement gap;
  see step 3 below.
- `DEPLOY.md` records conflicting historical persistence descriptions. Effective
  production storage and recovery have not been verified in this setup.

## Checklist

- [x] 1. Continuity files verified and saved remotely.
- [x] 2. Reproducible cloud development/test workspace verified (limits above).
- [x] 3. Main protection and CI enforcement verified against live rules.
- [x] 4. Separate private preview usable from a phone (iOS limitations below).
- [x] 5. Core hosting/log/storage access and isolated recovery verified; operational limits tracked.
- [x] 6. Monitoring gaps assessed and reusable workflow/templates documented; no external alerts configured.

## Next action

**Current Telegram feature work — November 1, 2026:** continue draft
[PR #572](https://github.com/jongsky25/css-is/pull/572), branch
`feat/telegram-private-work-lookup`, candidate **9.78**. The latest addition is
[colleague mentions in comments/replies](TELEGRAM_COLLEAGUE_MENTIONS.md), following author-owned comment editing and replies and comment posting, dependency management, blocker recording/clearing and lookup, review queue, cancellation and task reopening/reassignment,
initial assignment, submitted-task review, deadline changes and guided proposals. Inspect exact-head CI and continue the next requested feature.
Deployment, preview publication, activation and personal/live testing remain
explicitly deferred. Monitoring follow-ups below remain separately tracked and
are not the active Telegram task. See the latest evidence at the end of this file.


## Preserved seasonal preparation notes

Main now includes merged PR #578 at `adb83b4` (code version 9.60). The notes
below retain its earlier preparation history; Telegram publication remains deferred.

**Seasonal release PR opened — November 1, 2026.**
[Draft PR #578](https://github.com/jongsky25/css-is/pull/578) prepares 9.60.
Owner accepted the richer preview design and requested checks/release preparation;
production approval remains pending. Local release/appearance/preview group:
67 passed in 44.60s, no failures/skips. Metadata, lock-input and AI contract checks
passed. Required CI is running on the PR; exact final-head status must be read
from GitHub before claiming release readiness. Do not enable auto-merge.
Post-metadata merge-tree simulation against Telegram `cb192da` confirms conflicts
only in CHANGELOG.md, version.py, static/js/sw.js and docs/SETUP_STATUS.md.
These are release history/cache/status reconciliation, with no seasonal/Telegram
runtime source conflict observed. Proposed order remains seasonal first; if main
advances, update/reconcile and rerun all required checks. Keep the accepted preview
at `f4438aa` while CI runs; no republish or production change is needed.
Next: inspect full exact-head normal/shuffled/dependency/metadata/aggregate results,
resolve failures if any, and ask for explicit merge/deployment approval only once
the candidate passes. Final CI evidence belongs in PR #578 to avoid restarting
the verified source commit solely to record check results.

**Seasonal release preparation authorized — November 1, 2026.** Owner accepted
the richer design and requested release preparation/PR/checks, with merge and
production deployment explicitly left for final approval. Candidate 9.60 on
`feat/seasonal-theme-design`, based on current main `a7b9b38` (9.59).
Proposed order: seasonal first while Telegram continues independently at candidate
9.77/head `cb192da`. This is not a lock on the other thread: if main advances,
refresh/reconcile versions and repeat required checks before release. Initial
merge-tree simulation against Telegram found only the shared status-document
conflict. Metadata/cache/changelog now synchronized for seasonal 9.60; final
metadata adds the expected shared release-file reconciliation work.
Phone design acceptance applies to preview source `f4438aa`; release metadata is
the only subsequent application-facing preparation change. No feature activation,
schedule installation, preview replacement, merge or production deployment.
Next: open the release PR and observe complete normal/shuffled, dependency/container,
metadata and aggregate CI on its exact candidate head; fix failures without bypass.

**Richer seasonal design revision — November 1, 2026.** Owner requested stronger
festivities after the first preview. Added fuller Christmas tree/parol/gift artwork,
garlands, New Year fireworks/skyline/year display and bunting, decorated companion
settings, gold Home card details and festive footers. Phone hero artwork now stays
visible. Sound remains deferred; accessibility controls retained. Initial focused
group 19 passed; final seasonal group after refinements 13 passed, no failures/skips,
JUnit gate passed. [Screenshots and implementation notes](SEASONAL_THEME_IMPLEMENTATION.md).
Published source `f4438aaf361e527bb73747f87fb3ed9b1084dae9` to the existing
private preview; Space commit `62e72b31bec9cfa0c1d26c9a7e683278dab6b35f`
is RUNNING. Authorized health/login and new festive assets return 200; login has
PREVIEW banner. This replaces our original seasonal preview. Password unchanged;
phone review pending. Next: owner reloads/signs in, enables artwork and reviews
both richer themes. No production release, merge or Telegram publication.

**Seasonal private preview published — November 1, 2026.**
Owner requested publication. Source `5f6a18c2f5171dc17e6ee7462db2a8e77fe9ac64`
is RUNNING on the existing private CPU Basic preview; Space commit
`d5ed25c6bc88f4b7e194ca5c8ed8b463135b3071`. Remote manifest matches; authorized
health/login and seasonal assets return 200, login has PREVIEW banner/header;
anonymous health/login return 404. Isolated preview-bundle tests: 3 passed,
JUnit gate passed with zero failures/skips. Existing password secret unchanged;
no hosted app sign-in is claimed because the password is unavailable here.
The replaced preview was old collaboration source `f03125c2`; Telegram's latest
handoff explicitly defers preview publication. No Telegram build was overwritten.
[Phone review instructions and evidence](SEASONAL_THEME_IMPLEMENTATION.md).
Next: owner reviews Christmas/New Year on phone, then resolve feedback and reconcile
release order with Telegram. Shared preview now holds the seasonal candidate;
serialize future publishes. No production merge/deployment or version change.

**Seasonal application integration candidate — November 1, 2026.**
`feat/seasonal-theme-design` now implements Christmas/New Year palettes and parol
scenes, Home countdown to a validated target year in Asia/Manila, static midnight
greeting, optional bounded effects and generalized Appearance controls. No sound.
[Implementation, real-page screenshots and coordination handoff](SEASONAL_THEME_IMPLEMENTATION.md).
Existing appearance checks: 22 passed; combined checks: 34 passed; expanded seasonal
checks: 13 passed (overlapping groups), zero failures/skips, JUnit gates pass.
Final focused browser/new-season run after the admin-copy change: 16 passed,
zero failures/skips; JUnit gate passed.
No event published, Telegram message, preview overwrite, PR, merge or deployment.
Version metadata is intentionally deferred until release order with Telegram is
known; full required CI/release checks and hosted phone acceptance remain pending.
Latest compared Telegram branch head: `6a83c07`; only this status file overlaps by
changed path. Next: coordinate the shared preview slot and review on phone, then
refresh both feature branches and validate the eventual combined release.

**Seasonal build started in isolation — November 1, 2026.**
Branch `feat/seasonal-theme-design` starts from main `a7b9b38` in a separate
worktree. [Interactive mockups, screenshots and merge-coordination notes](design/seasonal/README.md)
cover Christmas/New Year Home, light/dark, a working form and simulated midnight.
32 browser layout combinations, draft retention and countdown transition/reset
passed. No application/runtime tests, integration, preview, release metadata,
Telegram messages, merge or deployment. Open Telegram draft PR #572 remains
independent; the current shared changed path is this status document only.
Next: refresh both branches, then integrate dedicated seasonal assets/tokens and
the configured server-synchronized countdown from
[the build handoff](SEASONAL_THEME_BUILD_HANDOFF.md). Sound remains deferred.

**Monitoring release deployed; automatic trigger and phone receipt pending — November 1, 2026.**

[PR #575](https://github.com/jongsky25/css-is/pull/575) merged as
`c81b235da0745dddf0e388c05b8496ea61532fb9`, release **9.58**.
All PR checks and the production normal/shuffled suites, dependency audit,
metadata and aggregate gate passed. The existing backup/version gates and
deployment also passed in [run 41273309243](https://github.com/jongsky25/css-is/actions/runs/41273309243).

Authenticated post-deploy observations confirm version 9.58/commit c81b235 and
the unchanged acknowledged historical audit incident: operational audit ok,
acknowledged=true, checkpoint_changed=false, raw_ok=false, through_id=9452.
Live probes in [run 41273427503](https://github.com/jongsky25/css-is/actions/runs/41273427503)
attempt 2 returned **uptime=true, backup=true, audit=true, monitor=true** in both
observations. No extra notification was created on this retry.

The initial marked delivery test succeeded: bot-created
[issue #576](https://github.com/jongsky25/css-is/issues/576) is assigned to
`jongsky25`. GitHub accepted the issue/assignment; phone receipt has not been
confirmed. An asynchronous receipt question is pending.

**Automatic coverage is not yet verified.** No event=schedule execution has
been observed. The cron is saved on main, but source/manual runs alone do not
prove continuous monitoring. A conditional owner check of the workflow's
Enable workflow button is now resolved: the owner's screenshot shows Disable
workflow, and the API confirms state=active. Command access has recovered.
On November 1 at 06:15:58 UTC the agent refreshed scheduling registration by
disabling and immediately re-enabling workflow 403282831; its final state is
active. No application code, deployment or data was changed by that refresh.

A normal manual [run 41280398437](https://github.com/jongsky25/css-is/actions/runs/41280398437)
then passed with uptime, backup, audit and monitor all true in both observations,
and no alert transitions. This is a workflow_dispatch run, not evidence of an
automatic scheduled execution. The owner has no further Enable button to find.

Investigation at 06:49–06:55 UTC confirmed the workflow is active, the repository
is public/non-fork/non-archived with default branch main, and the exact cron source
is on main. No schedule-triggered runs exist. GitHub Status reports no current
incident. Reading repository-wide Actions policy is denied (403), although manual
Actions execute successfully. The root cause remains unconfirmed; do not call the
original valid range/step expression a syntax error.

A review candidate on `fix/monitor-schedule-registration` (9.59) replaces the
range/step expression with equivalent explicit minutes to prompt source-based
schedule registration. This is a repair attempt, not proof of a GitHub defect or
an established fix. Full release checks and production promotion are required
before it can affect scheduling on main. Existing alert logic and credential
scope are unchanged.

Candidate saved as [PR #577](https://github.com/jongsky25/css-is/pull/577).
All 37 isolated monitor tests passed without skips/failures; the release metadata,
JUnit, documentation-link and diff checks passed. Full required CI is running.
Production promotion requires owner approval because merging restarts the live
app through the existing gated deployment; this investigation did not itself
authorize a new production release. No workflow gates are bypassed.

Next: obtain release approval, complete the candidate checks and promotion,
then observe a real scheduled execution
with healthy/valid signals, and obtain phone receipt confirmation. Do not claim
either step passed until evidence exists. No production outage, failed backup
or audit corruption was induced. Only generic statuses were published; no private
record contents or credential values were disclosed.

This handoff is saved separately on
`docs/monitoring-handoff-41273309243`; application code is merged/deployed.
Automated sign-ins use the existing deployment account and consequently appear
in its audit/usage views. Broader backup exposure/retention/recovery work remains
outside this monitoring request.

### Historical implementation notes

**Automatic monitoring requested — November 1, 2026.**
Candidate 9.58 is on `feat/operational-monitoring`. The owner requested outage,
backup and new-audit alerts plus a phone delivery test. GitHub owner-assignment
notifications are the initial channel while the asynchronous channel choice is
pending; no phone receipt is claimed. Independent five-minute GitHub checks use
two observations twenty seconds apart, durable incident deduplication and automatic
recovery closure. A private read-only status endpoint uses existing admin/session
checks; the historical audit acknowledgment is preserved.

See [monitoring procedure and limits](MONITORING_WORKFLOW.md). The repository is
public, so incident metadata is generic and no private records/provider errors
leave the app. No new paid service or secret is required. Existing deployment
secret names are reused by trusted main only. The integration cannot access the
GitHub secrets public-key endpoint; it did not retrieve any secret values.

Local isolated Python 3.11 checks: **183 passed**, no failures/skips (13.98 seconds),
including actual synthetic sign-in/status/sign-out, backup/auth and deployment
regressions. The initial 67-check subset also passed. Hash-verified cloud setup
and doctor completed. The monitor waits for the public protocol marker before
sending credentials and uses an existing-account-only sign-in guard, preventing
first-admin creation against an empty database. These regression checks passed;
full CI restarts on the corrected source. One existing Starlette/httpx deprecation warning remains.
Release/full CI, activation and delivery test are pending; source alone does not
establish automatic monitoring or phone delivery. The current request authorizes
the gated release/configuration needed to activate this monitoring.

Next: save/open the candidate, pass full release checks, merge/deploy, run a normal
check, send one marked owner notification test, verify the schedule and obtain
phone receipt confirmation. No app outage or data corruption will be induced to
test alerts. Backup exposure review and other operational follow-ups stay separate.

### Completed audit work

**Audit warning resolved operationally — November 1, 2026.**
The owner-requested writer fix [PR #573](https://github.com/jongsky25/css-is/pull/573)
merged as `5f3d775` and deployed as 9.56. The historical incident acknowledgment
[PR #574](https://github.com/jongsky25/css-is/pull/574) merged as `5a6338d` and
deployed as **9.57**. Both PRs passed both full-suite orders, dependency audit,
metadata, avatar acceptance and the required aggregate gate. Both production
workflows passed their own verification, backup/version gates and deployment.

Final [deployment run 41263751821](https://github.com/jongsky25/css-is/actions/runs/41263751821)
completed successfully. Authenticated post-deploy Operations observations confirm
version 9.57, commit `5a6338d`, `ok=true`, `acknowledged=true`, `bad_id=null`,
`checkpoint_changed=false`, and `through_id=9452`. `raw_ok=false` is expected:
original audit records/hashes remain unchanged and the historical chain failure
is still documented. This clears the active audit warning without rewriting
history. Changes to the reviewed prefix and new chain failures remain actionable.
Only typed, sanitized status was read from the workflow archive; no private audit
records or credential values were published. Temporary audit snapshot directories
were checked absent after the read-only inspections.

No further audit data repair is needed for this reviewed incident. Continue with
the owner's next requested work. Automatic monitoring alerts remain a separate
follow-up; the owner reports backups fixed. This final handoff is saved on
`docs/audit-warning-resolved`; application changes are merged and deployed, while
this documentation-only completion update is saved separately from main.

### Historical action notes

November 1 follow-up: owner authorized merging PR #573 and then clearing the
reviewed historical warning. PR #573 is ready for review, with metadata,
dependency audit and avatar acceptance passing; both full suites are still
running at this handoff. Auto-merge is disabled on the repository, so merge must
be performed after observing the required aggregate gate pass.

The acknowledgment candidate is on `fix/audit-incident-acknowledgment` (9.57).
It pins the exact reviewed historical prefix, preserves the strict verifier and
all original database records, and keeps future failures actionable. See the
[incident acknowledgment design](operations/audit-2026-11-01.md).
Local verification: 59 targeted audit/health/deploy-diagnostics checks passed,
zero skips/failures (7.03 seconds); JUnit, release metadata and diff checks pass.
Two independent read-only snapshots (`084815` and `085017` auto snapshots on
November 1) matched the 9,411-row fingerprint through #9452. Candidate operational
checks on the latter report acknowledged history with no active failure, while
the raw full-chain failure remains. No app ran on the snapshot; temporary data
was removed. Existing post-deploy diagnostics now expose only typed audit status
alongside existing sanitized Operations observations for live verification.

Next: finish the gated #573 merge, then merge/deploy the acknowledgment candidate
after its checks, and confirm the live audit status. This owner request includes
the releases necessary to clear the warning; no backup settings or automatic
monitoring alerts are in scope. This is work in progress, not a claim of deployment.

User resumed the audit warning on November 1 and reports backups fixed.
Investigation and prospective write fixes are on `fix/audit-chain-investigation`;
see [audit investigation](operations/audit-2026-11-01.md). The #8949 numeric-zero
hash mismatch is reproduced; two later forks match the concurrent-writer defect.
Historical records and warnings are preserved. Validation and save results are
recorded below. No production release is authorized by this request.
Automatic monitoring remains separate. Earlier deferral statements below are
historical and no longer defer this requested investigation.


Use the [mobile/cloud workflow](MOBILE_CLOUD_WORKFLOW.md) for the user's next
requested feature or fix. The collaboration setup is ready on this branch;
release 9.55 is being integrated with explicit user approval to merge once
ready. Main triggers production deployment; all release/backup gates still apply.

The user explicitly deferred the audit investigation to finish collaboration
setup. Do not automatically resume #8949 investigation or exposure remediation.
Keep [operational follow-ups](OPERATIONS_ACCESS.md) visible; return to them when
requested. Monitoring is currently manual; automatic outage alerts and phone
notification delivery have not been configured or verified.

## Step 3 evidence — 2026-10-31, 14:15 UTC

- Main is `aaef9d3da0ac5289ca79b1e458c249a404292ddf`; branch endpoint reports
  `protected: false`, required status checks off, and no contexts.
- Ruleset listing and active main branch rules both returned empty lists.
- Detailed classic protection returned HTTP 403 through connector and gh; this
  integration lacks administration access. The connector has no rule write tool.
- Latest five workflow runs succeeded. Latest PR CI `41201937781` and main deploy
  `41206532759` each succeeded on attempt 2; their job lists confirm metadata,
  dependency audit, both test orders and aggregate gate passed. No reruns triggered.
- Required check name confirmed from the actual check run:
  `verification / Required checks`, GitHub Actions integration ID `15368`.
- Prepared a policy requiring PRs, the current aggregate check, up-to-date branches,
  resolved review threads, no bypasses, and blocking deletion/force pushes.
  It requires zero approvals to support a solo maintainer. Not yet applied.
- Changes are documentation/configuration proposals only. No live settings, main
  commits, workflows, deployments, or application behavior were changed.

## Release status

No PR merge or production deployment authorized by this setup request. These
documentation changes do not bump application versions; existing release metadata
checks may require reconciliation before any later merge. Do not bypass them.

## Step 3 follow-up — 2026-10-31, 14:35 UTC

The user created ruleset `26274179`, **Office Connect main release gate**.
Live branch, applicable-rules and ruleset-detail reads confirm:

- Main is now `protected: true`; the ruleset is active and targets only main.
- Bypass list is empty; current integration reports bypass `never`.
- PRs required, zero approvals, review conversations must be resolved.
- Required check is `verification / Required checks` from GitHub Actions `15368`.
- Deletion and force pushes blocked.
- **Remaining gap:** `strict_required_status_checks_policy` is false. The user
  must enable the up-to-date branch requirement; no administration write access
  is available through this integration.

The branch endpoint's legacy `protection.enabled: false` describes classic
protection, not the active ruleset. Applicable rules and ruleset details establish
that the new protection is enforced. No merge, deployment or failing push was used
to test enforcement. Previous unprotected observations above are historical.

## Step 3 final verification — 2026-10-31, 14:37 UTC

After the user's second save, both the ruleset-detail endpoint and applicable
main-branch rules confirm `strict_required_status_checks_policy: true`.
Ruleset `26274179` remains active, targets only `refs/heads/main`, has no bypass
actors, requires PRs and resolved review threads with zero required approvals,
requires `verification / Required checks` from GitHub Actions app `15368`, and
blocks deletion and force pushes. The integration cannot bypass the rules.
All intended settings are now verified. Step 3 is complete. Verification used
read-only APIs; no test push to main, merge, workflow rerun or deployment occurred.

## Step 4 evidence — 2026-10-31

- User explicitly chose Hugging Face for preview instead of Render. No Render
  resources were created or changed.
- Target is fixed to `equityinhealth/office-connect-preview`; production target and
  deployment script remain untouched. No preview has been created or uploaded.
- No HF cached token or configured `HF_TOKEN` was available. Cloud environment
  reports no secret bindings. GitHub Actions production secrets were not accessed.
- Added `scripts/deploy_preview_hf.py`: dry-run defaults, code-only bundle, private
  target check, committed-source provenance, and explicit publish flag. A staged
  940-file bundle passed exclusion checks. Production databases, env files and
  deploy scripts are not included. Generated metadata/Docker/README replace live
  equivalents for the preview only.
- Added `scripts/preview_app.py`: new temporary SQLite DB and synthetic admin on
  each start, isolated signing key, scheduler disabled, inherited provider settings
  removed, and Python/asyncio outbound socket guard. No real data is used.
- Added visible PREVIEW banners to staged template copies, environment response
  headers, noindex headers and a readiness endpoint. Source templates unchanged.
- `tests/test_preview_setup.py`: two tests passed without skips, including staged
  bundle startup, HTTP auth rejection/success, Chromium login at 390×844, banner,
  untouched sentinel DB/persistence path, and external socket rejection. JUnit gate
  passed. This does not prove deployed private access or an OS-level egress sandbox.
- Isolated deployment SDK installed from hash-verified `requirements-deploy.txt`;
  required HfApi method signatures verified. Dry-run made no network requests.
- Current official Hugging Face docs confirm CPU Basic has no hourly charge but
  new compute Spaces require eligible account plans. Eligibility remains unknown;
  no plan/hardware/storage purchase was made.
- Remaining: private Space, preview password secret, scoped credential, upload,
  successful remote build, unauthorized-access rejection and authorized phone test.
  No remote URL is claimed live. Full release suites/audits were not run.

## Step 4 manual progress — 2026-10-31

- User created `equityinhealth/office-connect-preview`. Initial public metadata
  showed Gradio; user corrected it and changed visibility to private.
- User screenshot of committed README `06597e0` confirms `sdk: docker`,
  `app_port: 7860`, no python_version line, and a private badge.
- Anonymous metadata/README reads now return HTTP 401. Authenticated metadata
  has not been verified; `HF_TOKEN` is not configured in this workspace.
- User reports saving `OFFICE_PREVIEW_PASSWORD` in the preview Space's secrets.
  Its value was neither requested nor inspected. Presence remains to be verified
  by authenticated secret-name lookup or successful preview startup.
- Next action: create a fine-grained HF token with write access only to the
  preview Space and bind it as cloud secret `HF_TOKEN`. First locate the client's
  supported cloud secret settings if necessary. Never paste credentials in chat.
  After binding, verify SDK/private state and secret-name presence, publish the
  prepared bundle, then monitor and test remotely. Preview is not yet deployed.

## Step 4 publication — 2026-10-31

- Fresh managed environment reports `HF_TOKEN` ready; authenticated HF API calls
  succeeded. Token contents were not printed. The preview password secret name
  was verified remotely; its value was not retrieved or replaced.
- Installed the hashed deploy lock in isolated Python 3.11 environment;
  `pip check` passed. Published the existing 940-file code-only bundle using
  `scripts/deploy_preview_hf.py --publish` from a clean tree.
- Source: `2cff502345d4c477985c80031c8c7663a0c4cc1a`; Space commit:
  `0d6467f4b82527f9546fe5fe20f3336918da39c8`. Downloaded
  `preview-build.json` confirms the source commit.
- API confirms private Docker Space, stage `RUNNING`, hardware `cpu-basic`.
  No plan/hardware/storage upgrade or production operation was performed.
- Anonymous `/preview-health` and `/login`: HTTP 404. Authorized health: HTTP
  200 and expected readiness text. Authorized login: HTTP 200, PREVIEW banner,
  `x-office-connect-environment: preview`.
- URL: https://huggingface.co/spaces/equityinhealth/office-connect-preview
- Remaining: successful signed-in phone login and synthetic page action, using
  the owner's saved preview password. No production data or credentials copied.
  Full release suites/audits were not rerun for this publication/status update.

## Step 4 iOS embedding repair — 2026-10-31

- Owner's phone confirmed Hub access but the app frame was blank. Authorized
  remote `/login` had `frame-ancestors 'self'` and `X-Frame-Options: SAMEORIGIN`,
  blocking the Hub embed. Direct `.hf.space` access returned private-access 404;
  a Hub session does not automatically authorize that top-level URL on iOS.
- Preview wrapper now permits only self and `https://huggingface.co` ancestors,
  removes its incompatible frame-options header, and uses SameSite=None on
  hosted preview cookies while retaining Secure/HttpOnly and origin checks.
  Production security middleware and cookie configuration are unchanged.
- Fresh hashed Python 3.11 test environment setup/doctor passed. The first browser
  attempt ran before Chromium finished installing and failed to launch; after
  installation, all 3 preview checks passed, including synthetic HTTP/mobile
  login, isolation and header/cookie regression checks. All 23 existing browser
  security tests passed. Both JUnit gates passed without skips; diff check passed.
- Publish and remote header verification follow this committed change. Phone
  acceptance remains pending. No production release or visibility change authorized.

- Repair publication verified: Space commit
  `5ac1982785c0298e0e9203c084a465f6d1ead53d`, source
  `f03125c2d56e9f6f4f029e77ef821d91be46d076` confirmed from remote build metadata.
  Runtime is RUNNING on CPU Basic. Authorized health/login both return 200.
  Login now advertises `frame-ancestors 'self' https://huggingface.co` with no
  X-Frame-Options header. Anonymous login remains hidden with HTTP 404.
  Owner should retry the signed-in Hub page; iOS cookie restrictions may still
  require the provider's temporary cross-site tracking workaround. Successful
  remote phone login remains unverified; local mobile login passed.

## Step 4 phone login confirmed — 2026-10-31

Owner supplied an iPhone Safari screenshot showing the private Space Running,
the PREVIEW synthetic-data banner, and the authenticated synthetic administrator
home page (Hi, Preview). This confirms remote phone login and home rendering after
the embedding repair. The screenshot does not establish a subsequent page action
or whether Safari tracking protection was restored. Next: open Calendar or Your
profile and confirm the page loads while remaining signed in. Step 4 remains open
for that final interaction check. No hosting/code/production change in this update.

## Step 4 accepted on phone — 2026-10-31

Owner's second iPhone Safari screenshot confirms Calendar navigation after login:
dated agenda cards, empty schedule, holiday entries and calendar legend rendered
inside the private Running Space. Together with the preceding authenticated home
screenshot, this completes the requested phone login/page-action acceptance.
Step 4 is complete. This verifies navigation/rendering, not calendar data writes
or all application features. iOS private-Space cookie limitations remain; whether
tracking protection was restored has not been verified. Preview remains synthetic,
disposable and private; production is unchanged. Next is setup step 5.

## Step 5 read-only inspection — 2026-10-31

See [Operations access and recovery](OPERATIONS_ACCESS.md) for evidence and limits.
Production/preview hosting, deployed production version 9.54/main aaef9d3,
health, settings-name access and bounded hosting-log access are verified.
Startup logs establish local css_is.db, /data/_backups/scheduled, a boot restore
and a 60-second saver with 24 retained snapshots. They do not establish current
backup age or a tested recovery objective.

Important finding: equityinhealth/office-connect-data is public. Explicitly
anonymous bucket metadata/listing succeeds and exposes 25 database snapshot
entries. No database was downloaded. Confirm the exact mount mapping before
making the bucket private and validating continued durability; visibility was
not changed in this session. The configured HF token also has broader production
read access than the intended preview-only scope.

App admin credentials are absent, and /ops and /admin/backups redirect to login.
GitHub deployment job metadata is readable, but secret-name listing is denied
and useful deployment log text could not be retrieved. Actual recovery, independent
backup retention and current durability remain unverified. Step 5 stays open.
No test suite was rerun for this read-only/documentation task; Markdown links
and git diff checks are the applicable validation.

## Step 5 bucket privacy correction — 2026-10-31, 15:59 UTC

Owner authorized the live bucket visibility change. The SDK update succeeded;
authenticated bucket metadata now reports private=true. Anonymous metadata and
snapshot listing both return HTTP 401; authenticated snapshot listing succeeds.
Production health remained HTTP 200/status ok. New periodic snapshot
css_is_20261031_235908_auto.db appeared after the change, confirming continued
backup writes. No backup contents were downloaded or restored, no forced snapshot
was requested, and no mount/restart/deployment/token change was made.

The exact mount identity remains unavailable through the current API/browser
access; settings HTML requires the owner's browser login. A cold-start remount
was not tested. Current write evidence does not replace integrity/recovery
verification or assessment of the earlier public exposure. Step 5 stays open for
admin/mount/recovery evidence. Documentation diff and local-link checks passed;
application tests were not rerun for a bucket settings change.

## Step 5 recovery/exposure follow-up — 2026-10-31, 16:06 UTC

Owner authorized the follow-up. Downloaded one existing private-bucket snapshot
into restricted temporary storage, verified size/integrity, and exercised actual
backups.restore_backup against a separate temporary destination under an isolated
credential-free environment and outbound socket guard. Both integrity checks,
synthetic pre-restore safety-copy check and restored session/integration reset
postconditions passed. Source was unchanged. No app was run on the recovered data.
Temporary database/cache copies were removed; production health remained 200/ok.
Anonymous snapshot HEAD remains 401. Observed download/drill: 16.2 seconds;
local restore/check: 0.83 seconds. These are not agreed recovery objectives.

Sanitized evidence and limitations are saved in
[recovery-2026-10-31.json](operations/recovery-2026-10-31.json). Snapshot contains
account, document and integration credential records; source stores read keys as
hashes. Prior third-party downloads/public exposure duration remain unknown.
Current tools provide no historical bucket access audit. No production account/key
reset or external notification was performed. Owner admin/mount evidence,
independent retention, recovery objectives and exposure decisions remain pending.
Documentation links/diff checks passed. No application suite rerun: this was an
isolated exercise of the existing deployed recovery routine and documentation.

## Step 5 owner Operations verification — 2026-10-31

Owner production screenshot confirms live permanent-storage saves (displayed
2026-11-01 00:09:16 local), daily backups on, 25 saved/about 1.1 GB, last daily
backup OK and next daily backup 2026-11-01 02:00. Owner admin durability status
is now verified. Do not confuse the daily maintenance schedule with the 60-second
periodic durability saver.

The screenshot also reports audit gap #8949. Read-only inspection of existing
snapshot css_is_20261101_001016_auto.db confirms one content-hash mismatch at
#8949 (previous link itself matches #8948) and two later link-only mismatches.
Sanitized [audit evidence](operations/audit-2026-10-31.json) is saved; no audit
field contents were published. The cause remains unknown; recovery/integrity
success does not establish audit authenticity. No rehash, deletion, live repair,
restart or deployment was performed. Temporary audit snapshot/caches were removed.
Audit investigation and exposure/remaining operational limits stay open.

## Step 6 — monitoring assessment and reusable workflow, 2026-10-31

User chose collaboration setup before the deferred audit investigation. Inspected
monitoring.py, request/exception middleware, health/Operations endpoints, durability
and audit checks, CI and production deployment workflow, release gates and preview
publisher. Existing in-process metrics/logs/health/Operations already cover manual
diagnostics. No configured external uptime checker/error exporter or verified
phone alert delivery was found. No new SDK, paid service, scheduled automation,
alert recipient or production monitoring change was introduced.

Added the phone request → branch → isolated build/tests → committed private preview
→ phone acceptance → PR/release procedure, monitoring coverage/gap assessment,
request/PR templates and a session handoff template. Documented shared-preview
publish serialization, exact candidate provenance, iOS limitations, fresh-session
access checks and production-connected main. AGENTS.md now follows current status
and preserves deferred findings rather than automatically resuming them.

Core step 5 access/storage/recovery evidence is complete within its recorded scope;
remaining operational hardening/exposure/audit tasks are separate tracked work.
Step 6's monitoring assessment and reusable procedures are complete. This does not
claim external automatic alerting or full production security/recovery acceptance.
Work is saved on setup/cloud-mobile-continuity; no merge, production deployment or
preview republish occurred. GitHub issue/PR templates become default only after
integration into the relevant default-branch workflow; they are usable as files now.
No release CI or app suite was run for these docs/templates. Diff, links and issue
frontmatter validation are the applicable checks. Instructions are still held on
the setup branch; a fresh chat must select that branch until approved integration.

## Main integration candidate — release 9.55

User explicitly requested preparation, required checks and merge once ready,
including the production deployment triggered by main. Reviewed the accumulated
setup changes; production runtime logic remains unchanged except release metadata
and service-worker cache version. Preview behavior is isolated in its own tooling.
Updated startup instructions so “office connect” uses current main or the saved
active review branch, rather than always selecting the historical setup branch.
Synchronized version.py, Markdown changelog and service-worker version to 9.55.

This entry records the candidate, not a claim that CI, merge or deployment has
completed. The PR and GitHub checks provide the actual integration outcome.
Deferred audit/exposure findings stay deferred. No release gates may be bypassed.

## Telegram review handoff — 2026-10-31

Requested broader Telegram review is saved on `docs/telegram-broader-review`.
See the [reconciled integration ledger](TELEGRAM_TWO_WAY_PLAN.md#broader-integration-review--2026-10-31).
Private reply/link repairs #569/#570 are merged; latest main deployment run
41227419174 passed. The complete T4.4 hosted pilot remains unverified, and its
runbook PR #488 remains open. Next: verify hosted linking, then fresh outgoing
connectivity before group/action/scheduled delivery and the full pilot.
T5–T7 remain gated on T4.4. This was a source/GitHub/documentation review; no
application tests, live sends, feature-switch changes, merge or deployment.
Deferred audit/exposure work remains deferred.

Owner subsequently confirms live Telegram linking and calendar retrieval. The
next feature request is progressive Telegram expansion; recommended first scope
is usable private guided meeting creation, then room requests. First-expansion
preference is pending; see the Telegram ledger's owner acceptance entry.

## Telegram task/work expansion — 2026-11-01

Owner selected private task and work-status lookup. Implementation is saved on
`feat/telegram-private-work-lookup`, candidate 9.56: `/my_tasks`, `/task_status`,
`/my_work`, `/work_status`, bounded pages and source links; no writes or pushes.
New `work.read` consent and default-off `CSS_TELEGRAM_WORK_READ_ENABLED` are
required. Existing calendar permission does not grant this access. See the
[runbook](TELEGRAM_WORK_LOOKUP.md) and
[implementation evidence](TELEGRAM_TWO_WAY_PLAN.md#t61a-implementation-evidence--2026-11-01).

Fresh setup/doctor passed. Local verification: 26 focused tests (including mobile
no-script two-channel consent/lookup), 419 broader regressions and 46 targeted
shuffled tests passed without skips/failures; counts overlap. Metadata, locks,
vendor, AI contract, compatibility, compile, relative links and diff checks pass.
Full repository suites/container audit remain CI gates. Next: review exact-head
CI and the PR, then separately authorized release/activation and actual hosted
acceptance. No live switch, real Telegram send, preview publish, merge or deploy.
Deferred operations findings remain deferred.

Saved remotely in [draft PR #572](https://github.com/jongsky25/css-is/pull/572),
implementation commit `b31a6f2`; exact-head CI pending. No merge/deployment.

## Private Telegram task batch staged — 2026-11-01

Owner approved building more before deployment/live testing. Same draft PR #572
and branch `feat/telegram-private-work-lookup`, still candidate 9.56, now include
overdue/upcoming/review task filters, completed/total work progress, acknowledgement
and output submission for review through exact private previews/confirmation.
Separate default-off action switches and `tasks.acknowledge`/`tasks.submit` consent
are required along with work-read access. Canonical ownership, workflow, blockers,
revision checks, audit and atomic durable receipts apply. No group task actions
or automatic notifications. See the [updated runbook](TELEGRAM_WORK_LOOKUP.md).

Final local checks: 292 broader regressions, 88 shuffled cases and 43 final
consent/link/browser cases passed with zero failures/skips (overlapping groups).
Two actual mobile no-script workflows cover reading and task submission with
outbound Telegram forbidden. Metadata/locks/vendor/compatibility/AI contract,
compile, local links and diff checks passed. Full repository suites and dependency
audit remain PR CI gates. Next: keep reviewing/adding on the draft; release,
activation and live testing are deferred by the owner's explicit instruction.
No production/preview setting, real message, merge or deployment changed.

## Document lookup and summary staged — 2026-11-01

Owner approved the next additions on the same branch/draft PR #572 (candidate
9.56): `/documents [BEFORE_ID]`, `/find_documents WORDS`, `/document_status ID`,
and `/my_summary`. Document metadata/status requires separate unchecked
`documents.read` consent and default-off `CSS_TELEGRAM_DOCUMENTS_READ_ENABLED`;
it uses webhook-only replies independently of Collaborative work. Search covers
number/subject only and retains no search text in Telegram queue payloads.
Summary uses work-read access and current Manila-date authorized-set counts.
See the [document/summary runbook](TELEGRAM_DOCUMENT_LOOKUP.md).

Validation: 277 broader regressions and 55 shuffled cases passed without
failures/skips (overlapping groups), including two actual phone-width no-script
read-consent flows with outgoing sends forbidden. Metadata/locks/vendor/AI
contract/compatibility, compilation, relative links and whitespace passed.
Full repository suites/container audit remain PR CI gates. Next: review or
continue building on the draft as directed; deployment, activation and live
testing remain deferred. No real messages, production/preview changes or merge.

## Next increment: own supplies-request lookup staged — 2026-11-01

User instructed continuation once ready. Verified all checks passed at draft head
`8ec39b4`: functional, metadata, dependency audit, full Python 3.11 normal/shuffled
suites and Required checks (CI run 41259502581). Continued to bounded T7.2a on the
same draft PR #572/branch/candidate 9.56, preserving deferred deployment/live tests.

Added `/my_supplies [all|active|needs_action|completed] [PAGE]` and
`/supply_status REQUEST_ID`: only the owner's reference, approval/collection stage,
needed date and source link. Separate default-off Supplies-read switch/consent;
Supplies must be enabled, Documents/work need not be. No stock/item/people/notes
projection, actions, receipt acknowledgement or notifications. Source requester
stage defines pickup/handover/receipt semantics. [Runbook](TELEGRAM_SUPPLIES_LOOKUP.md).

257 broader cases, 41 shuffled cases and 18 final focused cases passed with zero
failures/skips (overlapping groups), including source-service approval→handover→
receipt transitions, admin/business-role isolation and a third no-script mobile
consent/read/disconnect case. Metadata/locks/vendor/compatibility/AI contract,
compile, links and diff checks passed. Fresh exact-head PR CI is required for
this new child; prior head's green CI is historical evidence. Next: inspect
that CI/review before further expansion. Draft remains unmerged and no hosting,
preview, feature switch, real Telegram send or live acceptance was performed.

## Travel, meals and arrangement lookup staged — 2026-11-01

Owner approved this next read-only batch in draft PR #572, same branch/candidate
9.56. Added travel list/detail with deadlines, filing/paper-review states and
source completeness count; standalone and room-linked meal list/detail with
order/delivery states; and work-arrangement list/detail with requested period/type
and filing status. Eight commands are documented in the
[personal lookup runbook](TELEGRAM_PERSONAL_LOOKUP.md). Each of the three source
areas requires separate unchecked consent and its own default-off Telegram switch.
Travel also honors its source module switch and excludes purged filings. All
reads are private/webhook-only and owner-bound even for admins/managers.

No amounts, file URLs, dietary/special requests, venues, people, arrangement
reasons, review/decision notes or colleague data are projected. No filing,
review/submission/approval, meal ordering or arrangement changes occur.

426 broader regressions and 76 shuffled cases passed without failures/skips
(overlapping groups). Six actual phone-width no-script read-consent flows now
cover every private-read scope, with outgoing Telegram forbidden. Metadata,
locks/vendor/compatibility/AI contract, compile, local links and diff checks pass.
Full repository suites/container audit remain exact-head PR CI gates. Next:
review those checks or continue bounded additions as directed. No merge,
production/preview settings, real send, deployment or live acceptance; those
remain explicitly deferred.

## Private meeting/room webhook flow staged — 2026-11-01

Owner approved the next core-workflow repair on the same draft PR #572/branch,
candidate 9.56. Private `/meeting` and `/room_request` now return guides through
webhook replies; real forms show `/meeting_preview OPERATION_ID` or
`/room_preview OPERATION_ID`; private confirmation/receipt commands commit and
recover the existing authorized action without an outgoing provider connection.
Combined room failure preserves the meeting and supports a fresh parent-linked
room-only retry. Room requests remain pending approval, never auto-booked.
[Runbook](TELEGRAM_PRIVATE_MEETING_WEBHOOK.md).

No new grants/switches: current explicit calendar read/create and room read/request
consent still apply. Source business mutations, audit, consumed preview, receipt,
update deduplication and uncertain response handoff commit atomically. Private
webhook pushes are not queued; old pending private pushes are suppressed in that
mode. Group-origin confirmations still use the existing async membership path;
direct-mode behavior remains available. Uncertain sends are never replayed.

322 broader regressions and 19 shuffled flow/browser cases passed without
failures/skips (overlapping groups). Two real phone no-script browser flows use
only actual message/form-visible codes and forbid outbound sends/membership
calls. Tests cover duplicate/concurrent commits, source/current authority,
partial retry, old queue suppression and complete rollback on handoff failure.
Metadata/locks/vendor/compatibility/AI contract, compile, links/diff checks pass.
Full repository suites/container audit remain fresh exact-head CI gates. Next:
review CI or separately scoped additions as directed. No merge/deployment,
production/preview setting, real provider call or hosted acceptance. Live testing
and full T4.4/group/scheduled-delivery verification remain deferred/open.

## Audit warning candidate — November 1, 2026

Branch `fix/audit-chain-investigation`, based on main `e0dde74` (merged 9.55).
Saved as [draft PR #573](https://github.com/jongsky25/css-is/pull/573), initial
implementation commit `360517c`. Release CI is not yet verified.
Version 9.56 synchronizes release metadata for review; it is not deployed.
Read-only snapshot investigation and production limits are in
[the audit report](operations/audit-2026-11-01.md).

Python 3.11 hashed test-lock installation and pip check passed. Isolated targeted
audit, integration access/changes, travel transaction, appearance and monitoring
checks: **125 passed**, zero skips/failures (27.47 seconds). JUnit gate, release
metadata check, changed documentation links and git diff check passed. One
existing Starlette/httpx deprecation warning was emitted. Full normal/shuffled
suites and dependency/container audits remain release CI requirements; these
targeted results do not replace them. No preview is needed for this storage-only
change. No production data mutation, merge, restart or deployment occurred.

Next: review the saved candidate and its CI before any explicitly requested
release. The historical #8949 warning is intentionally preserved; incident
acknowledgment/checkpoint design remains separate from the prospective writer fix.

## Telegram candidate reconciled with current main — 2026-11-01

Main advanced to `5a6338d` with separately merged audit-write/incident work
(PRs #573/#574), source version 9.57. Preserved those changes by merging current
main into the Telegram review branch. This does not resume audit operations or
authorize a production change. Previous audit candidate/status entries are
historical. The current Telegram candidate is now **9.58**, with main's 9.56/9.57
release history retained and Telegram's unpublished notes moved to 9.58.

Meeting/room implementation commit `f9ab222` holds the transport repair. Before
reconciliation, 322 broader cases, 19 shuffled flow cases and two final actual
mobile webhook cases passed without failures/skips; the final browser run also
verifies nullable legacy routing contexts do not crash the signed-in page.
Fresh merged-candidate checks follow; prior-head results are not transferred.
Draft PR #572 remains unmerged; deployment, activation and live testing deferred.

## Reconciled Telegram 9.58 checks complete locally — 2026-11-01

After merging actual main `5a6338d`, source head `4ad1955` passed **766** all-
Telegram plus audit/deployment/release tests and **45** shuffled private-webhook/
legacy-worker browser/audit tests, with zero failures/skips (groups overlap).
Reports: `/tmp/telegram-958-merged-regressions.xml` and
`/tmp/telegram-958-merged-shuffled.xml`. Metadata/increase against main 9.57,
locks/vendor/installed compatibility/AI contract, compile, relative links and
PR whitespace checks pass. Final edits only save this evidence/handoff; no
application changes followed the passing merged-source runs.

Draft PR #572 remains the durable review location on
`feat/telegram-private-work-lookup`, candidate **9.58**. Inspect fresh exact-head
repository-wide normal/shuffled/dependency/aggregate CI before any readiness or
release claim; prior-head results are historical. Next: review those checks or
continue separately scoped work when directed. Production/preview release,
feature activation, real messages and live acceptance remain explicitly deferred.
The complete T4.4 group/calendar/room/reminder/revocation/rollback hosted pilot
and outgoing scheduled/group delivery are still unverified.

## Personalized menu and acceptance plan implemented — 2026-11-01

Owner approved `/menu`/`/help` grouped discovery, availability explanations and
record-specific next steps, plus a concrete later live-testing checklist.
Implementation is staged on the existing Telegram branch/draft PR #572.
Pre-main-reconciliation checks: 310 broader tests, 84 shuffled cases and 10 final
menu cases passed without failures/skips (groups overlap), including six actual
phone no-script consent/read/menu/status/disconnect flows with outgoing Telegram
forbidden. All live acceptance checklist cases are explicitly Pending.
Current main advanced to monitoring release 9.58; Telegram's unpublished candidate
will be reconciled above it before fresh checks. No live action is authorized.

## Telegram candidate reconciled above monitoring release — 2026-11-01

Preserved main `c81b235` / separately merged PR #575 monitoring changes. Telegram
menu implementation is saved at `97953e6`; the current unpublished candidate is
now **9.59**, with actual main release 9.58 preserved. Current runbooks and the
Pending live-test checklist reflect 9.59. Fresh merged-source verification follows.
No operational-monitor run/notification test, production data change, Telegram
activation, merge to main or deployment was initiated by this task.

## Personalized menu and checklist verified — current candidate 9.59

Source/test head `cee7614`, with main `c81b235` preserved, passed **813** all-
Telegram plus operational-monitor/audit/deployment/release cases and **69**
shuffled menu/phone/guided/monitor cases, zero failures/skips. Final menu/worker
run: **23 passed**. Groups overlap. Reports are
`/tmp/telegram-959-merged-regressions-final.xml`,
`/tmp/telegram-959-merged-shuffled.xml`, `/tmp/telegram-menu-worker-final.xml`.
The earlier stale help-heading assertion is fixed and now explicitly verifies
neutral unlinked help with no business commands. Six actual no-script phone
consent/read/menu/status/disconnect cases pass with outgoing Telegram forbidden.

`/menu` and `/help` show only currently available/consented commands, grouped with
examples; `/status` explains exact missing consent or paused controls without
listing unavailable commands. Task-specific next actions honor current owner,
write consent, source state/open-work/blocker rules. List/detail/back/recovery
guidance is added without granting permission or creating records.

See the [menu guide](TELEGRAM_MENU.md) and the
[concrete later live checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md), whose
live cases are all Pending. Metadata/locks/vendor/compatibility/AI contract,
compile, links and PR whitespace checks pass. Final edits only record results;
no app source changes follow those runs. Draft PR #572 remains unmerged on
`feat/telegram-private-work-lookup`, candidate **9.59**. Next: inspect fresh
exact-head full normal/shuffled/dependency/aggregate CI and review the draft;
release, host activation, real messages and live acceptance remain deferred.
No monitor run, notification test, production/preview deployment or live data
mutation was initiated by this task. Group/scheduled/outgoing T4.4 work stays open.


## Daily work brief and saved reminder choices — 2026-11-01

Owner approved building an on-demand daily brief and reminder preferences before
activation/live testing. Draft PR #572 continues on
`feat/telegram-private-work-lookup`, unpublished candidate **9.60**. Main c81b235
(9.58) is preserved; this task does not resume monitoring or operations work.

`/brief` composes permitted personal calendar entries for today through six days
ahead, the existing task/work summary and own room/supplies/personal-request
statuses. Each source requires its existing consent/module/pilot. Sections have
bounded current-source results and full lookup commands; no business record is
changed and no business text is cached for replay. Calendar covers the full dated
range, including earlier entries today. Recent personal filings include all
statuses and are labeled accordingly.

The signed-in, phone-width, JavaScript-free notification page saves separate
section choices, an off-by-default future reminder preference and preferred
Manila time. CSRF, current session/account, input bounds, stale revisions and
atomic audit checks apply. There is no daily-brief scheduler, enqueue path or
sending hook. Saved choices neither grant permissions nor change existing
calendar/room reminders, email channels, quiet hours or host switches.

See [daily brief details](TELEGRAM_DAILY_BRIEF.md) and the expanded
[pending live checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md).

Current isolated Python 3.11 verification: **775 all-Telegram plus deployment/
release regressions passed**, **37 shuffled brief/menu/phone-form cases passed**,
zero failures/errors/skips (overlapping groups). Reports:
`/tmp/telegram-brief-regressions.xml` and `/tmp/telegram-brief-shuffled.xml`;
both JUnit gates pass. The earlier initial subset passed 33 cases and the three
phone-form cases passed separately; these overlap the final groups. Metadata/
version increase (9.60 over main 9.58), dependency locks/vendor integrity, installed
compatibility, AI contract, compilation, documentation file links and whitespace
checks passed. The existing Starlette/httpx deprecation warning remains. No
application source changes followed the passing runs. Full repository-wide
normal/shuffled suites and dependency/container audit are fresh exact-head CI
gates, not claimed passed locally.

Next: inspect exact-head full normal/shuffled/dependency/aggregate CI and review
the draft. Deployment, preview publication, activation, real messages and live
testing remain deferred. A future scheduled-brief delivery implementation needs
separate consent/delivery/quiet-hour/deduplication/expiry/revocation design and
verification; storing a preferred time does not authorize or activate it.


## Unified private metadata search — 2026-11-01

Owner approved `/find WORDS` across permitted tasks/work titles, document
numbers/subjects and meeting titles. Draft PR #572 continues on
`feat/telegram-private-work-lookup`, unpublished candidate **9.61**; main c81b235
(9.58) is preserved. Private webhook replies use each existing source grant,
module and pilot without any umbrella permission. Source visibility/ownership
and literal casefold matching precede bounded result limits. Hidden linked
documents suppress related work/tasks. Meetings use canonical calendar blend
visibility, the meeting kind and explicit next-31-day Manila window, retaining
source recurrence links.

Grouped results show source status where available, deadlines and actual detail
commands; work has no invented overall status. Only metadata fields are searched
and projected. No outputs, file/OCR contents, sender/people/note/venue/meeting-URL
fields are queried for matching. Source titles remain user-authored. Search text
stays ephemeral inside the existing intake transaction and is never queued or
cached. Existing deduplication, rate limits, private identity and restore/revoke
fences apply. No schema, grant, dependency, scheduler or external service is added.

See [search behavior](TELEGRAM_PRIVATE_SEARCH.md) and the expanded
[pending live checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md). Six real phone
consent/read flows now exercise permitted search sources and deny search after
disconnect with outgoing Telegram forbidden.

Current isolated Python 3.11 verification: **796 all-Telegram/deployment/release
regressions passed**, plus **61 shuffled search/menu/phone/brief cases**, zero
failures/errors/skips (groups overlap). Reports:
`/tmp/telegram-search-regressions.xml` and `/tmp/telegram-search-shuffled.xml`;
both JUnit gates pass. The earlier focused run passed 37 cases, including the six
real no-script phone flows; it overlaps the final groups. The initial schema-
fixture error was corrected before the final runs. Candidate 9.61 metadata/
increase over actual main 9.58, locks/vendor integrity, installed compatibility,
AI contract, compilation, documentation file targets and whitespace checks pass.
The existing Starlette/httpx deprecation warning remains. No application source
edits followed the passing runs. Exact-head repository-wide normal/shuffled/
dependency/container/aggregate CI remains required and is not claimed passed.


Next: inspect fresh exact-head full normal/shuffled/dependency/aggregate CI and
review the draft. Production/preview publication, feature activation, real
messages and live testing remain deferred. Existing daily-brief reminder choices
are still saved preferences only; search does not activate any delivery. No
monitoring/operations action or live data access occurred for this task.


## Private meeting management implemented — 2026-11-01

Owner approved continuing feature development while personal/live testing stays
deferred. Draft PR #572 continues on `feat/telegram-private-work-lookup`,
unpublished candidate **9.62**, preserving main c81b235 (9.58).

Added separately consented, default-off `calendar.reschedule` and
`calendar.cancel` actions. `/meeting_reschedule` and `/meeting_cancel` return
signed-in, script-free forms; prepared operation IDs retrieve exact private
previews with five-minute deadlines and action-specific confirmation/recovery
commands. Existing create/read consent cannot grant either new write action.

Only an actor's own plain native one-day meeting is eligible. Recurring, imported,
activity-linked, already-cancelled and managed video cases stay in Office Connect.
Active linked room requests/bookings block preparation and confirmation, including
new links after preview; this increment does not move/cancel rooms or meals.
Rescheduling changes date/start/end only, preserving remaining source fields.
Cancellation uses native soft cancellation. Source notices follow current
notification settings; no feature/notice/reminder delivery is activated now.

Native calendar update/cancel now supports caller-owned transactions with existing
default behavior preserved. Source revision/outbox/audit, consumed preview and
operation receipt commit together. A full source hash plus latest revision ID
blocks stale or edited/reverted previews. Atomic rollback, duplicate/concurrent
confirmation, creator/current-authority/private transport fences and deletion
recovery are covered by synthetic checks.

See [meeting-management behavior](TELEGRAM_MEETING_MANAGEMENT.md) and the expanded
[pending live checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md).

Current isolated Python 3.11 verification: **1789 regression cases** across
Telegram, native calendar, audit-chain writers, deployment and release checks
passed, plus **98 shuffled action/menu/phone cases**, **11 native Meet relay
cases** and **4 final normal late-receipt/consent cases**, zero failures/errors/
skips. Groups overlap; the four final cases were added after broad-run collection
and also passed in the shuffled group. The earlier new-management/phone run
passed 48 cases, overlapping these groups. Initial synthetic table/API/seen-marker
assertions were corrected to the actual source schema/semantics before final
runs; no permission or atomicity assertion was weakened. JUnit reports:
`/tmp/telegram-manage-regressions.xml`, `/tmp/telegram-manage-shuffled.xml`,
`/tmp/telegram-manage-relay.xml`, `/tmp/telegram-manage-extra.xml`. All gates pass.

Candidate 9.62 metadata/increase over main 9.58, dependency locks/vendor integrity,
installed compatibility, AI contract, compilation, documentation file targets
and whitespace checks pass. Existing Starlette/httpx deprecation warning remains.
No application source edits followed the passing runs. Fresh exact-head full
repository normal/shuffled/dependency/container/aggregate CI remains required;
no live acceptance or deployment is claimed.

Next: inspect fresh exact-head repository-wide normal/shuffled/dependency/aggregate
CI and review the draft. Production/preview publication, host activation, real
messages and user/live testing remain deferred. Independent room management and
managed provider/series editing remain future work; no operational monitor action
or live data access occurred in this task.


## Private room withdrawal and date moves — 2026-11-01

Owner approved room-request management while publication/activation and live
testing remain deferred. Draft PR #572 continues on
`feat/telegram-private-work-lookup`, unpublished candidate **9.63**, preserving
main c81b235 (9.58). Separate default-off `rooms.withdraw` / `rooms.move` pilots
and explicit consent also require current room read; existing read/request
consent cannot grant either new action.

`/room_withdraw` and `/room_move` return script-free signed-in forms accepting
an own room reference or ID. Exact five-minute private previews precede
confirmation and action-specific recovery. Pending date moves change the request
in place. Approved moves submit a new pending child while the old booking stays
held until normal approval; no bot action grants approval. Withdrawing releases
held hours and identifies pending move children also withdrawn. Withdrawing only
a move leaves the original unchanged and reports its actual current status.

Only the actual requester can act, including when an administrator can view other
requests. Meals/meal forms, series, standby, guests, direct activity links and
on-behalf-of cases stay in Office Connect. A calendar-linked move additionally
requires calendar read and a new date matching the current permitted meeting.
The calendar is never silently edited.

Native room writes/notices now support strict caller-owned transactions while
existing default behavior remains. Source rows/held slots, move child, notice
outbox/audit, consumed preview and receipt share one transaction. Durable source
heads and full room/slot/family hashes stop stale/edited-reverted previews; linked
meeting revisions and current target conflicts are also checked. Shared signed-in
form handling retains actor/session/CSRF, strict fields, body bounds and rate
limits for both meeting and room paths.

See [room-management behavior](TELEGRAM_ROOM_MANAGEMENT.md) and the expanded
[pending live checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md).

Local Python 3.11 verification: **1,454 broad regressions passed** across
Telegram, native room/approval/meal/series/guest/UI workflows, calendar links,
existing MCP room tools, audit-chain writers, deployment and release checks.
**142 final shuffled action/menu/phone checks** and **2 final normal parent-status/
approval-race checks** passed, zero failures/errors/skips. Groups overlap. The
broad run began before a final preview-only correction to show an original
booking's actual status when cancelling a pending move; business writes were
unchanged. The final shuffled/normal groups cover that correction and the
additional race assertion. Initial expected old-booking status was corrected
to native `withdrawn` after normal move approval, preserving the actual source
semantics and held-slot assertions. Earlier focused run: 92 passed; initial
native/shared-form subset: 90 passed.

Reports: `/tmp/telegram-room-manage-regressions.xml`,
`/tmp/telegram-room-manage-shuffled-final.xml`,
`/tmp/telegram-room-manage-final-state.xml`; all JUnit gates pass. Candidate 9.63
metadata/increase over main 9.58, locks/vendor integrity, installed compatibility,
AI contract, compilation, local documentation file targets and whitespace checks
pass. Existing Starlette/httpx deprecation warning remains. No app source edits
followed the final passing groups. Fresh exact-head repository-wide normal/
shuffled/dependency/container/aggregate CI still needs inspection; no hosted or
user acceptance is claimed.

Next: inspect fresh exact-head full normal/shuffled/dependency/container/aggregate
CI and review the draft. Deployment, preview publication, host activation, real
messages and user/live testing remain deferred. Meal/series/guest/on-behalf-of
management, different-hour moves and combined calendar/room rescheduling remain
separate future scope. No operational monitor action or live data access occurred.


## Private guided task proposals — 2026-11-01

Owner requested the next Telegram feature while deployment, preview publication,
activation and personal/live testing remain deferred. Added `/new_task` guided
proposals in draft PR #572 on `feat/telegram-private-work-lookup`, candidate
**9.64**. Independent main monitoring registration repair `a7b9b38` (9.59,
PR #577) was preserved by review-branch merge `6b064fc`; its released changelog
entry remains below the unpublished Telegram batch. No monitor execution or
configuration action was initiated by this task.

Separate default-off `CSS_TELEGRAM_TASKS_CREATE_ENABLED` / `tasks.create` consent
requires work read, available document/work modules and the original private
webhook/account/bot context. The script-free signed-in form captures permitted
work ID, task title, expected output, contributing unit, optional proposed owner
and exact optional deadline. A five-minute private preview precedes confirmation;
source deadline, visibility/intersection and open-work rules are checked again.

Confirmation creates one native required contribution in proposed state, with no
confirmed owner. Officer assignment remains a separate source decision and still
requires linked-document access for the eventual owner; no access is granted by
proposal. Native task/event/audit/review effects, consumed preview, receipt and
final private reply share one transaction. Duplicate/concurrent confirmations
produce one proposal. New receipt deletion fencing prevents numeric-ID reuse
from displaying a replacement task. Legacy ack/submit preview endpoints reject
proposal-shaped operations.

Active latest, not-yet-invalidated consolidation review packets on nonterminal
documents block bot creation. Native additions there can reset dependent formal
approvals; those amendments stay in Office Connect, including when review starts
after preview. Native services remain unchanged. Source module pause also blocks
guides and directory forms.

See [task proposal behavior](TELEGRAM_TASK_PROPOSALS.md) and the expanded
[pending live checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md).

Isolated Python 3.11 verification: **1,408 broad regressions passed** across
Telegram, native work/assignment/review/completion/legacy/UI behavior, audit-chain
writers, deployment and release checks. **125 final shuffled checks** cover new
proposals, current module/formal-review guards, task ack/submit separation, menus,
action engine and existing meeting/room phone forms. **3 final normal guard
cases** passed; zero failures/errors/skips in all groups. Groups overlap.

The broad run started before final proposal-only refinements: source pause now
blocks guides, preview wording identifies required contributions, and active
formal-review amendments stay in Office Connect. The final shuffled and normal
guard groups cover those refinements. Earlier dedicated proposal/phone run: 35
passed; existing task/menu/shared-form subset: 73 passed. Initial synthetic
officer-confirmation reason and long-source-label fixtures were corrected to
actual native requirements before passing final groups. No permission assertion
was weakened.

Reports: `/tmp/telegram-task-create-regressions.xml`,
`/tmp/telegram-task-create-shuffled-verified.xml`,
`/tmp/telegram-task-create-final-guards.xml`; JUnit gates pass. Candidate 9.64
metadata/increase over actual main 9.59, locks/vendor integrity, installed
compatibility, AI contract, compile, local file links and whitespace checks pass.
Existing Starlette/httpx deprecation warning remains. No app source edits followed
the final passing groups. Fresh exact-head full repository normal/shuffled/
dependency/container/aggregate CI still requires inspection; no hosted or user
acceptance is claimed.

Next: inspect fresh exact-head repository-wide normal/shuffled/dependency/
container/aggregate CI and review the draft. Release, host activation, real
messages and user/live acceptance remain deferred. Automatic assignment, task
acceptance/cancellation/deadline changes and amendments to active formal reviews
remain separate scope. No production data or external staff messaging was used.


## Private internal task deadlines — 2026-11-01

The owner requested the next feature while keeping deployment, preview publication,
activation and personal/live testing deferred. Added `/task_deadline` with a
signed-in no-script form, `/deadline_preview`, `/deadline_confirm` and
`/deadline_receipt` to draft PR #572, review branch
`feat/telegram-private-work-lookup`, candidate **9.65**. Actual main remains
`a7b9b38` (released 9.59); its changes and released changelog remain preserved.
No main merge, provider calls, monitor execution or production data access occurred.

Separate default-off `CSS_TELEGRAM_TASKS_DEADLINE_ENABLED` / `tasks.deadline`
consent requires work read, source modules and original private webhook/account/
chat/bot proof. The native concerned-officer or confirmed-work-lead `milestone`
authority is checked at preparation and confirmation. Task ownership alone is
insufficient. The form requires set/change with an exact date or explicit clear
with a blank date, plus a bounded reason. The preview identifies work/task, status,
old/new deadline and reason before exact five-minute confirmation.

Confirmation uses the native task milestone transaction. Owner, progress,
required status, expected output, submission and official deadlines stay unchanged.
Internal targets cannot follow linked official deadlines. Completed/closed work,
done/cancelled tasks, lost document visibility and active formal consolidation
review block the operation. Formal review beginning after preview also blocks it;
dependent approval amendments remain in Office Connect. Shared proposal/deadline
helpers retain these rules and hash source state without projecting submissions.

Native source/event/audit/reminder effects, preview consumption, receipt and
private handoff commit atomically. Duplicate/concurrent confirmation changes one
milestone; audit/receipt/handoff failures roll back. Task deletion cancels pending
previews and clears recorded targets to fence numeric-ID reuse. Read revocation,
source/host pauses, stale/reverted source, restored connection, expired proof and
changed officer/lead authority refuse confirmation. Recovery rechecks current
source view and reports current state without repeating a change.

See [feature details](TELEGRAM_TASK_DEADLINES.md) and the extended
[pending live checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md). All live cases
remain Pending. No scheduler, automatic assignment, acceptance, cancellation or
external staff message was added.

Isolated Python 3.11 verification: **1459 broad regressions passed** across
`tests/test_telegram*.py`, `tests/test_work*.py`, audit-chain writers, deployment
and release checks. **167 current shuffled checks** (seed 311) passed across
deadline/proposal services and phone forms, menu, generic action engine, existing
task actions and private meeting webhook handling. Zero failures/errors/skips in
both groups; groups overlap. The broad run includes the final authority-revocation
and four native nonterminal-state cases. No application source edits followed
these runs.

Earlier dedicated proposal/deadline/menu/phone sample: 90 passed; earlier generic
engine/deadline sample: 76 passed. Initial synthetic linked-document fixtures
needed access for the assigned contributor; the legacy-schema simulation needed
to remove the newer deletion trigger before dropping its referenced table. Those
fixtures were corrected without weakening authority or migration assertions.
Final passing groups cover both corrections.

Reports: `/tmp/telegram-task-deadline-regressions.xml` and
`/tmp/telegram-task-deadline-shuffled.xml`; both pass the JUnit no-skips gate.
Candidate 9.65 release metadata/increase over actual main 9.59, locks/vendor
integrity, installed compatibility, AI contract, Python compilation, local Markdown
links and whitespace pass. Existing Starlette/httpx deprecation warning remains.
Full exact-head repository normal/shuffled/dependency/container/aggregate CI still
requires inspection after push. No hosted or user acceptance is claimed.

Next: inspect fresh exact-head repository-wide normal/shuffled/dependency/
container/aggregate CI and continue the requested feature work. No hosted/user
acceptance is claimed. Main merge, preview publication, release, feature activation,
real messages and live testing remain deferred until the owner's later instruction.


## Private submitted-task review — 2026-11-01

Owner explicitly requested task acceptance and return-for-changes after the latest
internal deadline feature. Added `/task_accept` and `/task_return`, separate
signed-in no-script guides, private previews, exact confirmation and receipts to
review branch `feat/telegram-private-work-lookup`, draft PR #572, candidate
**9.66**. Actual main remains `a7b9b38` (released 9.59). Deployment, preview
publication, activation and personal/live testing remain explicitly deferred.

Separate default-off `CSS_TELEGRAM_TASKS_ACCEPT_ENABLED` / `tasks.accept` and
`CSS_TELEGRAM_TASKS_RETURN_ENABLED` / `tasks.return` require work read and current
private inbound/link/delivery/source/account/bot proof. The concerned case officer
or confirmed work lead must have the native action. Task ownership or another
Telegram permission alone grants neither review action. The form captures only
permitted work/task IDs and a bounded mandatory reason. Review the current
submission in Office Connect first; bot previews identify work/task, For review →
Done or In progress, and the actor-entered reason without disclosing stored output.

The existing native `accept`/`return` task transaction remains authoritative.
Acceptance preserves recorded-blocker, unfinished-prerequisite and unresolved
changed-decision rules. Return may request changes with those blockers still
present; it does not resolve them. Changed source/submission/event history, lost
visibility/authority, closed/completed work and task states, revocation/pause/
restore/expiry and original-context checks prevent stale writes. Active formal
consolidation review before or after preview blocks bot amendments, preserving
dependent official approvals. No native work service was changed.

Review preserves owner, submission, output, required status and deadlines. It does
not complete the work case or approve/release/close an official document. Native
source/event/audit/reminder effects, consumed preview, receipt and private handoff
share one transaction. Audit/receipt/handoff failure rolls back. Duplicate and
concurrent confirmation changes one task once; a pending opposite action cannot
reverse a confirmed result. Deletion cancels pending previews and clears receipt
targets, fencing numeric-ID reuse. Recovery reports the recorded outcome and
current permitted state without repeating the action.

Isolated Python 3.11 verification: **1559 broad regressions passed** across
`tests/test_telegram*.py`, `tests/test_work*.py`, audit-chain writers, deployment
and release checks. **265 current shuffled checks** (seed 311) passed across
new review services/phone forms, deadline/proposal services/phone forms, menu,
action engine, existing task actions and private meeting webhook handling. Zero
failures/errors/skips in both groups; groups overlap. Both include final opposite-
preview and native owner-account cases. Earlier focused service/phone group:
94 passed; initial menu/action wiring group: 46 passed. No application source
changes followed these runs.

The first focused pass caught four changed-decision test fixtures treating the
native discussion's returned message ID as a record. The fixture now uses that ID
and its actual initial revision. A copied browser-selector syntax error was fixed
before the final passing service/phone run. Current passing groups cover both
corrections without weakening source or browser assertions.

Reports: `/tmp/telegram-task-review-regressions.xml` and
`/tmp/telegram-task-review-shuffled.xml`; both pass the no-skips JUnit gate.
Candidate 9.66 metadata/increase over actual main 9.59, dependency locks/vendor
integrity, installed compatibility, AI contract, Python compilation, local file
links and whitespace pass. Existing Starlette/httpx deprecation warning remains.
Full exact-head repository normal/shuffled/dependency/container/aggregate CI still
requires inspection after push. Earlier-head results are not current acceptance.

See [task review behavior](TELEGRAM_TASK_REVIEWS.md) and the expanded
[pending live checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md); all live cases
remain Pending. No real provider message, production data access, scheduler,
monitor execution or Telegram activation occurred. Assignment/reassignment,
reopening, cancellation and formal-review amendments remain separate scope.

Next: inspect fresh exact-head full repository normal/shuffled/dependency/
container/aggregate CI, then continue the next explicitly requested feature.
Main merge, release, preview publication, pilot activation and personal/live
acceptance remain deferred until the owner's later instruction.


## Private initial task assignment — 2026-11-01

Owner explicitly requested officer-confirmed initial task assignment after task
review. Added `/task_assign`, a signed-in no-script owner selector, private
`/taskassign_preview`, exact `/taskassign_confirm` and `/taskassign_receipt` to
review branch `feat/telegram-private-work-lookup`, draft PR #572, candidate
**9.67**. Actual main remains `a7b9b38` (released 9.59), preserved on this branch.
Deployment, preview publication, activation and personal/live testing remain
explicitly deferred. Initial access inspection found prior-head functional,
metadata and dependency CI passing; full normal/shuffled were still running.
Those results are not transferred to this candidate.

Separate default-off `CSS_TELEGRAM_TASKS_ASSIGN_ENABLED` / `tasks.assign` consent
requires work read, source modules and current private inbound/link/delivery/
account/bot proof. The actor needs the native `confirm` action over the task's
contributing unit; work-lead/proposer/suggested-owner status alone is insufficient.
The form requires explicit owner selection and a bounded reason. No suggested
owner is automatically selected. Preview identifies task/work/unit, suggestion,
selected name/account, unchanged deadline and Proposed → To do before confirmation.

The selected active person needs existing access to every linked document.
Assignment grants no document permissions; confirmed ownership participates in
normal work membership rules and keeps linked-document visibility intersections.
Native source owner/document/date checks are repeated at preview and confirmation.
Account/name/source changes, lost task-unit officer or contributor rights,
completed/closed work, already-assigned/cancelled tasks and stale/revoked/expired/
restored contexts block confirmation. Active formal consolidation review beginning
before or after preview blocks amendments to preserve dependent approvals.

Confirmation calls the existing native `confirm` transaction, setting the selected
owner and To do state while preserving deadline, title/output/submission, required
status, unit and original proposal. It does not acknowledge, submit, review,
complete the case or approve an official document. Native source/event/audit/
reminder effects, consumed preview, receipt and private handoff share one atomic
transaction. Audit/receipt/handoff failure rolls back; duplicate/concurrent
confirmation assigns once. A competing pending owner choice cannot reassign the
confirmed task. Deletion fences numeric-ID reuse. Recovery reports current owner/
status and recorded outcome without replaying the original assignment.

Proposal wording now says officer assignment is separately confirmed, allowing
this independent private officer flow without granting proposal scope any new
authority. Native work/task services and source permissions remain unchanged.

Isolated Python 3.11 verification: **1618 broad regressions passed** across
`tests/test_telegram*.py`, `tests/test_work*.py`, audit-chain writers, deployment
and release checks. **323 current shuffled checks** (seed 311) passed across
assignment/review/deadline/proposal services and phone forms, menu/action engine,
existing task actions and private meeting webhook handling. Zero failures/errors/
skips in both groups; groups overlap. Both include the final positive contributing-
unit officer case. Earlier focused assignment and phone/proposal-phone group:
58 passed; existing menu/action/proposal wiring group: 83 passed. No application
source changes followed these runs.

The initial assignment sample caught one fixture assumption: changing an account's
technical role also revokes its Telegram connection, so it cannot retrieve a guide.
The corrected case tests native technical-admin authority directly and still
requires source denial. Current groups cover connection revocation and source
permissions without weakening either rule. A hidden-document case independently
retains officer authority while removing explicit restricted-document visibility.

Reports: `/tmp/telegram-task-assign-regressions.xml` and
`/tmp/telegram-task-assign-shuffled.xml`; both pass the JUnit no-skips gate.
Candidate 9.67 metadata/increase over actual main 9.59, locks/vendor integrity,
installed compatibility, AI contract, Python compilation, local Markdown links
and whitespace pass. Existing Starlette/httpx deprecation warning remains.
Full exact-head repository normal/shuffled/dependency/container/aggregate CI still
requires inspection after push. Earlier-head checks are not candidate acceptance.

See [assignment behavior](TELEGRAM_TASK_ASSIGNMENT.md),
[proposal boundary](TELEGRAM_TASK_PROPOSALS.md) and the extended
[pending live checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md). All live cases
remain Pending. No provider call, production data access, scheduler, monitor
execution or pilot activation occurred. Reassignment/reopening/cancellation and
formal-review amendments remain separate source actions.

Next: inspect fresh exact-head full repository normal/shuffled/dependency/
container/aggregate CI, then continue the next explicitly requested feature.
Main merge, release, preview publication, activation and personal/live testing
remain deferred until the owner's later instruction.


## Private officer task reassignment — 2026-11-01

Owner requested the next feature after initial assignment. Added `/task_reassign`,
a signed-in no-script different-owner selector, `/taskreassign_preview`, exact
`/taskreassign_confirm` and `/taskreassign_receipt` to review branch
`feat/telegram-private-work-lookup`, draft PR #572, candidate **9.68**. Actual main
remains `a7b9b38` (released 9.59), preserved on this branch. Deployment, preview
publication, activation and personal/live testing remain explicitly deferred.
Initial access inspection found prior-head functional/metadata/dependency checks
passing and full normal/shuffled still running; those are not current acceptance.

Separate default-off `CSS_TELEGRAM_TASKS_REASSIGN_ENABLED` / `tasks.reassign`
consent requires work read, source modules and current private inbound/link/
delivery/account/chat/bot proof. Initial assignment consent grants no transfer
right. Native officer authority must cover the task's contributing unit; task
ownership or work-lead status alone is insufficient. Only To do/In progress/For
review tasks qualify, and the new active owner must differ from the current one
and already read every linked document. The bot grants no document access.

The form and exact private preview explicitly show the reset to To do, including
In progress and For review tasks. Preview identifies old/new owner, current/new
state, work/task/unit, unchanged deadline and bounded reason. Existing submission,
output, original proposal, required status, deadline and blocker/follow-up/
prerequisite/changed-decision information remain preserved. Source membership
rules determine the old/new owners' access; stored submissions stay in Office
Connect. Transfer does not resolve blockers, accept work or approve a document.

Native reassignment remains authoritative. Initial assignment and reassignment
share identity/access/snapshot/receipt routing, with separate native actions,
result codes, scopes/pilots and command protocols. Source/account/submission/
event changes, lost officer/new-owner rights, hidden documents, closed/completed
work and revoked/expired/restored contexts prevent stale transfer. Active formal
consolidation review starting before or after preview blocks bot amendments,
preserving dependent approvals. No native work/task service was changed.

Native source/event/audit/reminder effects, consumed preview, receipt and final
private handoff share one transaction. Audit/receipt/handoff failure rolls back;
duplicate/concurrent confirmations transfer once. Competing owner choices cannot
transfer the updated source again. Deletion cancels previews/clears targets to
fence ID reuse. Recovery checks current source view and reports recorded outcome
plus current owner/status without replay, including later source transfer/progress.

Isolated Python 3.11 verification: **1680 broad regressions passed** across
`tests/test_telegram*.py`, `tests/test_work*.py`, audit-chain writers, deployment
and release checks. **384 current shuffled checks** (seed 311) passed across
reassignment/initial-assignment/review/deadline/proposal services and phone forms,
menu/action engine, existing task actions and private meeting webhook handling.
**4 final normal phone checks** passed for reassignment and initial assignment.
Zero failures/errors/skips in all groups; groups overlap. Earlier focused transfer
service sample: 56 passed; combined transfer/initial-assignment/phone sample:
116 passed; initial wiring group: 104 passed.

Broad/shuffled collection preceded one wording-only refinement to the initial
assignment form: it now points to the separately consented reassignment flow
rather than saying all reassignment stays in Office Connect. Final four normal
phone cases cover both current forms after that refinement. All functional source
and the final three service cases (changed submission, missing access before
preview and contributing-unit officer positive) were present before broad/shuffled
collection. No functional code edits followed these groups.

Reports: `/tmp/telegram-task-reassign-regressions.xml`,
`/tmp/telegram-task-reassign-shuffled.xml` and
`/tmp/telegram-task-reassign-phone-final.xml`; all pass the JUnit no-skips gate.
Candidate 9.68 metadata/increase over actual main 9.59, locks/vendor integrity,
installed compatibility, AI contract, Python compilation, local Markdown links
and whitespace pass. Existing Starlette/httpx deprecation warning remains.
Full exact-head repository normal/shuffled/dependency/container/aggregate CI still
requires inspection after push. Earlier-head results are not current acceptance.

See [transfer behavior](TELEGRAM_TASK_REASSIGNMENT.md) and the expanded
[pending live checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md). All live cases
remain Pending. No provider call, production data, scheduler, monitor execution,
publication or activation occurred. Reopening/cancellation and formal-review
amendments remain separate source actions.

Next: inspect fresh exact-head full repository normal/shuffled/dependency/
container/aggregate CI, then continue the next explicitly requested feature.
Main merge, release, preview publication, activation and personal/live testing
remain deferred until the owner's later instruction.


## Private accepted-task reopening — 2026-11-01

Owner requested the next feature after reassignment. Added `/task_reopen`, a
signed-in no-script reason form, `/taskreopen_preview`, exact private
`/taskreopen_confirm` and `/taskreopen_receipt` to review branch
`feat/telegram-private-work-lookup`, draft PR #572, candidate **9.69**. Actual main
remains `a7b9b38` (released 9.59), preserved on this branch. Deployment, preview
publication, activation and personal/live testing remain explicitly deferred.
Initial exact prior-head inspection found all functional/release metadata/
dependency/full normal/full shuffled/aggregate CI checks passing at `3bea6d1`.
Those checks establish the earlier candidate only, not this new head's acceptance.

Separate default-off `CSS_TELEGRAM_TASKS_REOPEN_ENABLED` / `tasks.reopen` consent
requires work read, work/document modules and original private inbound/link/
delivery/account/chat/bot proof. Native concerned case-officer or confirmed
work-lead authority is checked on every preparation/confirmation; task ownership
alone is insufficient. Only Done tasks qualify. Existing owner must still be
active and able to read every linked document. The bounded mandatory reason and
identified task/current owner/Done → In progress are shown before confirmation.

Confirmation uses the existing native `reopen` mutation. It preserves owner,
submission/output, deadline, required status, unit, original proposal and history.
Pending changed-decision reviews or unfinished prerequisites remain unresolved;
normal resubmission/acceptance blockers still apply. Source changes/reversion,
lost rights, missing/ineligible owner, hidden documents and revoked/expired/
restored contexts prevent stale writes. Active formal consolidation review begun
before or after preview blocks amendments to preserve dependent approvals.
Completed work must be reopened separately in Office Connect first; this task
action does not reopen the case or an official document.

The shared review adapter supplies source snapshots and receipt routing, with a
separate reopening action/result/scope/protocol. Native task/work services remain
unchanged. Source/event/audit/reminder effects, consumed preview, receipt and
private handoff commit atomically. Audit/receipt/handoff failure rolls back;
duplicate/concurrent confirmation reopens once. Deletion fences numeric-ID reuse.
Recovery checks current read/source view and reports later status without replay.

Expanded status initially exceeded Telegram's limit by 13 UTF-16 units. Removed
repeated per-feature relinking instructions while preserving every missing-consent
label and the shared account/relink footer. Current menu assertions require the
full reopening/work-read consent labels and the 4096-unit budget.

Isolated Python 3.11 verification: **1734 broad regressions passed** across
`tests/test_telegram*.py`, `tests/test_work*.py`, audit-chain writers, deployment
and release checks. **437 current shuffled checks** (seed 311) passed across
reopening/reassignment/initial-assignment/review/deadline/proposal services and
phone forms, menu/action engine, existing task actions and private meeting webhook
handling. Zero failures/errors/skips in both groups; groups overlap. Both include
the final native pending-direction/unfinished-prerequisite cases and the current
status budget fix. Earlier focused service sample: 49 passed; combined reopening/
review/menu/phone sample: 159 passed. No application source edits followed these
passing groups.

The initial shared review/menu/action run had one failure: expanded status was
4109 UTF-16 units, above Telegram's 4096 limit. The fix preserves each human consent
label and states relinking instructions once in the footer. Current budget and
visibility assertions remain; full reopening/work-read consent labels are also
asserted. The final groups cover this correction and both officer/lead phone flows.
No permission, workflow or no-skips assertion was weakened.

Reports: `/tmp/telegram-task-reopen-regressions.xml` and
`/tmp/telegram-task-reopen-shuffled.xml`; both pass the JUnit no-skips gate.
Candidate 9.69 metadata/increase over actual main 9.59, dependency locks/vendor
integrity, installed compatibility, AI contract, Python compilation, local Markdown
links and whitespace pass. Existing Starlette/httpx deprecation warning remains.
Full exact-head repository normal/shuffled/dependency/container/aggregate CI still
requires inspection after push. Earlier-head results are not current acceptance.

See [reopening behavior](TELEGRAM_TASK_REOPENING.md) and the expanded
[pending live checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md). All live cases
remain Pending. No provider call, production data, scheduler, monitor execution,
publication or activation occurred. Task cancellation, completed-work reopening
and amendments under active formal review remain separate source actions.

Next: inspect fresh exact-head full repository normal/shuffled/dependency/
container/aggregate CI, then continue the next explicitly requested feature.
Main merge, release, preview publication, activation and personal/live testing
remain deferred until the owner's later instruction.


## Private officer task cancellation — 2026-11-01

Owner explicitly approved task cancellation. Added `/task_cancel`, a signed-in
no-script reason form, `/taskcancel_preview`, exact `/taskcancel_confirm` and
`/taskcancel_receipt` to review branch `feat/telegram-private-work-lookup`, draft
PR #572, candidate **9.70**. Actual main remains `a7b9b38` (released 9.59), preserved
on this branch. Deployment, preview publication, activation and personal/live
testing remain explicitly deferred. Initial prior-head inspection at `535ef54`
found metadata passing and the remaining checks still running; those are not
this candidate's acceptance.

Separate default-off `CSS_TELEGRAM_TASKS_CANCEL_ENABLED` / `tasks.cancel` consent
requires work read, source modules and current private inbound/link/delivery/
account/chat/bot proof. Native officer authority must cover the task's contributing
unit; work-lead/task-owner status alone is insufficient. Proposed/To do/In progress/
For review tasks qualify; Done/already-Cancelled tasks and completed/closed work
refuse the action. Preview identifies work/task/unit, required/optional flag,
retained owner, current → Cancelled, reason and completion/dependency effects.

Cancelled tasks are excluded from outstanding-contribution checks, including
required tasks. Cancellation does not accept output or satisfy dependencies
requiring its acceptance. Work completion and official document decisions remain
separate. Owner fields, previous submission/output, deadline, required status,
original proposal, blocker/follow-up/decision history and dependency edges are
preserved. Native cancellation can close unassigned tasks or tasks with ineligible
owners without granting access; actor view/officer checks still apply. Normal
membership can remove a former owner's work access without another source right.
Cancelled tasks cannot use the Done-task reopening command. No task is deleted.

The existing native `cancel` mutation remains authoritative; no native task/work
service changed. Shared review snapshots/receipt routing use separate cancellation
action/result/scope/protocol. Source/submission/work/history changes, lost officer
rights, hidden documents, source pauses and revoked/expired/restored context block
stale confirmation. Active formal consolidation review before or after preview
blocks amendments, preserving dependent approvals. Source/event/audit/reminder
effects, consumed preview, receipt and private handoff commit atomically. Audit/
receipt/handoff failure rolls back. Duplicate/concurrent confirmation cancels
once; deletion fences ID reuse. Recovery checks current source view and reports
recorded outcome/current state without replay.

Isolated Python 3.11 verification: **1788 broad regressions passed** across
`tests/test_telegram*.py`, `tests/test_work*.py`, audit-chain writers, deployment
and release checks. **490 current shuffled checks** (seed 311) passed across
cancellation/reopening/reassignment/initial-assignment/review/deadline/proposal
services and phone forms, menu/action engine, existing task actions and private
meeting webhook handling. Zero failures/errors/skips in both groups; groups
overlap. Earlier focused cancellation services: 46 passed; verified cancellation/
phone/menu group: 63 passed; shared review/reopening/menu/action wiring: 193 passed.
All functional source and final completion/dependency/blocker/optional/submission
cases preceded broad/shuffled collection. No application source edits followed
the passing groups.

The first combined phone run had two fixture failures: a copied selector still
pointed at the reopening form. Corrected it to the cancellation form without
weakening any assertions. The verified 63-case group and current broad/shuffled
runs use the corrected selector, exercise proposed and For review phone flows,
and preserve all CSRF/allowlist/source/no-provider/no-skips assertions.

Reports: `/tmp/telegram-task-cancel-regressions.xml`,
`/tmp/telegram-task-cancel-shuffled.xml` and
`/tmp/telegram-task-cancel-verified.xml`; all pass the JUnit no-skips gate.
Candidate 9.70 metadata/increase over actual main 9.59, locks/vendor integrity,
installed compatibility, AI contract, Python compilation, local Markdown links
and whitespace pass. Existing Starlette/httpx deprecation warning remains.
Full exact-head repository normal/shuffled/dependency/container/aggregate CI still
requires inspection after push. Earlier-head results are not current acceptance.

See [cancellation behavior](TELEGRAM_TASK_CANCELLATION.md) and the expanded
[pending live checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md). All live cases
remain Pending. No provider call, production data, scheduler, monitor execution,
publication or activation occurred. Completed-work/document lifecycle and
amendments under active formal review remain separate source workflows.

Next: inspect fresh exact-head full repository normal/shuffled/dependency/
container/aggregate CI, then continue the next explicitly requested feature.
Main merge, release, preview publication, activation and personal/live testing
remain deferred until the owner's later instruction.


## Private current task review queue — 2026-11-01

Owner explicitly approved a review queue after task actions. Added `/review_queue
[BEFORE_ID]` and `/review_task WORK_ID TASK_ID` to review branch
`feat/telegram-private-work-lookup`, draft PR #572, candidate **9.71**. Actual main
remains `a7b9b38` (released 9.59), preserved on this branch. Deployment, preview
publication, activation and personal/live testing remain explicitly deferred.
Initial prior-head inspection at `74fe448` found functional/metadata/dependency
passing and normal/shuffled still running; those are not new-head acceptance.

Separate default-off `CSS_TELEGRAM_TASKS_REVIEW_READ_ENABLED` / `tasks.review.read`
metadata consent requires work read, source modules and current private inbound/
link/delivery/account/chat/bot proof. The consent explicitly covers task/work/
owner/deadline metadata; it grants no accept/return authority. Existing own-task,
search and brief projections are unchanged. Only submitted tasks with current
native case-officer or confirmed-work-lead review authority, source visibility,
open work, no active formal review and an eligible current owner are shown.
Owner/task-unit officer status alone is insufficient; hidden/unknown/ineligible
details share a neutral denial.

Rows show bounded task/work titles, IDs, owner display name/account and deadline.
Submission/output/blocker reasons stay in Office Connect. A source-blocked
acceptance can still permit return; each command hint also requires its separate
write scope/pilot. Queue-only consent gives source review guidance without write
commands. Offered existing start commands lead to the signed-in ID/reason form,
expiring private preview and exact confirmation; no read creates an operation,
preview, origin or source mutation. Fresh reads remove tasks after acceptance or
return and recheck source/host/scope/context changes.

SQL applies visibility and case coordinator authority before native bounded scan.
At most 200 permitted candidates are inspected in batches of 50; rows then pass
canonical work/open/formal-review/owner/native-action checks. Five-row/message
budgets and seek cursors avoid skips. An empty page can offer Continue when more
permitted source candidates remain after many fail eligibility; it never claims
global emptiness. A one-row lookahead verifies continuation. Hidden-source IDs
are excluded before scan limits. Queries/names/bodies are never retained in
projections, reads create no worker push, and duplicate updates are not replayed.
Current context is checked again before private reply handoff.

Isolated Python 3.11 verification: **1832 broad regressions passed** across
`tests/test_telegram*.py`, `tests/test_work*.py`, audit-chain writers, deployment
and release checks. **533 current shuffled checks** (seed 311) passed across
review queue/services/phone cases and all current task actions, menu/action engine,
existing task actions and private meeting webhook handling. Zero failures/errors/
skips in both groups; groups overlap. Both include final write-pilot guidance and
formal-review-after-earlier-list checks. Earlier focused queue services: 38 passed;
combined queue/menu/three phone flows: 51 passed; bot/link/menu wiring: 56 passed.
No application source edits followed the passing groups.

Phone cases cover read-only metadata consent and separately consented queue →
accept/return with the existing signed-in form, exact private preview, confirmation/
retry, current queue removal and disconnection denial. Native source/permission/
owner/blocker/formal-review guards, no source/prepared writes, private/direct/group/
topic boundaries, duplicate intake, ephemeral query/metadata, Unicode paging,
pre-limit visibility/authority filtering and bounded scan continuation pass.

Reports: `/tmp/telegram-review-queue-regressions.xml`,
`/tmp/telegram-review-queue-shuffled.xml` and
`/tmp/telegram-review-queue-verified.xml`; all pass the JUnit no-skips gate.
Candidate 9.71 metadata/increase over actual main 9.59, locks/vendor integrity,
installed compatibility, AI contract, Python compilation, local Markdown links
and whitespace pass. Existing Starlette/httpx deprecation warning remains.
Full exact-head repository normal/shuffled/dependency/container/aggregate CI still
requires inspection after push. Earlier-head results are not current acceptance.

See [review queue behavior](TELEGRAM_REVIEW_QUEUE.md) and the expanded
[pending live checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md). All live cases
remain Pending. No provider call, production data, scheduler, monitor execution,
publication or activation occurred. Native review/task/work services are unchanged.

Next: inspect fresh exact-head full repository normal/shuffled/dependency/
container/aggregate CI, then continue the next explicitly requested feature.
Main merge, release, preview publication, activation and personal/live testing
remain deferred until the owner's later instruction.


## Private blocker and prerequisite lookup — 2026-11-01

Owner explicitly approved blocker/prerequisite lookup. Added `/task_blockers
WORK_ID TASK_ID [BEFORE_ID]` to review branch `feat/telegram-private-work-lookup`,
draft PR #572, candidate **9.72**. Actual main remains `a7b9b38` (released 9.59),
preserved on this branch. Deployment, preview publication, activation and personal/
live testing remain explicitly deferred. Initial prior-head `5941882` inspection
found metadata/dependency checks passing and functional/normal/shuffled still
running; those checks are not new-head acceptance.

Separate default-off `CSS_TELEGRAM_TASKS_BLOCKERS_READ_ENABLED` /
`tasks.blockers.read` metadata consent requires work read, source modules and
current private inbound/link/delivery/account/chat/bot proof. Existing own-task
and review details offer the hint only with this independent grant/pilot. Source
work/task visibility permits metadata reading; reviewer/officer authority is not
required merely to read. Existing own-task/search/brief projections are unchanged.

Reply shows native waiting/clear check, recorded-blocker and unresolved-direction
flags, permitted follow-up display name/account/date, and unfinished same-case
prerequisite IDs/titles/states/deadlines. Native decision/blocker checks supply
flags. Blocker/dependency reasons, decision/resolution/discussion notes, outputs
and submissions remain in Office Connect. Inactive or no-longer-permitted follow-up
accounts are neutral, while the permitted task's date remains visible. Hidden/
unknown/wrong-case targets and inconsistent foreign dependency edges share denial.

Only Done satisfies a prerequisite; Cancelled remains waiting. Source unblocking,
acceptance and changed-direction resolution update the next read. Completed work
and terminal tasks can be read as history with a lifecycle warning; lookup enables
no action, resolves nothing and changes no edge/deadline/task. Native source links
point to exact task anchors. Five-row/UTF-16-budget pages filter same-case and
non-Done state before seek/limit and avoid skips/duplicates. Empty cursor pages
never imply global completion; other task state/permissions/review rules still apply.

Reads remain in the incoming webhook transaction with context/grant/module recheck
before handoff, retain no query/name/body projection, and never enqueue or replay
worker pushes. No source mutation, operation, preview or origin is created. Native
task/work/blocker/decision services remain unchanged. Group/topic/direct contexts,
duplicate updates, revoked/restored links and changed bot proof remain fenced.

Isolated Python 3.11 verification: **1869 broad regressions passed** across
`tests/test_telegram*.py`, `tests/test_work*.py`, audit-chain writers, deployment
and release checks. **569 current shuffled checks** (seed 311) passed across
blocker/queue services and phone flows, all current task actions, menu/action
engine, existing task actions and private meeting webhook handling. Zero failures/
errors/skips in both groups; groups overlap. Earlier focused blocker services:
32 passed; combined blockers/phone/queue/menu group: 86 passed; bot/link/menu/queue
wiring: 96 passed. All final resolution freshness and independent hint cases were
present before broad/shuffled collection. No application source edits followed
these passing groups.

Phone cases use ordinary owner and lead with read-only consent, open the exact
source task anchor (detailed reason visible only there), verify no lookup mutation
of task/edges or prepared actions, and observe a separate native resolution on
fresh Telegram read before disconnect denial. Source/owner visibility, current
modules/scopes/context, historical state, foreign-edge denial, body exclusion,
accepted/cancelled prerequisites, direction resolution, Unicode seek paging and
private/direct/group/topic/duplicate boundaries pass. No permission/no-skips
assertion was weakened.

Reports: `/tmp/telegram-task-blockers-regressions.xml`,
`/tmp/telegram-task-blockers-shuffled.xml` and
`/tmp/telegram-task-blockers-verified.xml`; all pass the JUnit no-skips gate.
Candidate 9.72 metadata/increase over actual main 9.59, locks/vendor integrity,
installed compatibility, AI contract, Python compilation, local Markdown links
and whitespace pass. Existing Starlette/httpx deprecation warning remains.
Full exact-head repository normal/shuffled/dependency/container/aggregate CI still
requires inspection after push. Earlier-head results are not current acceptance.

See [blocker lookup behavior](TELEGRAM_TASK_BLOCKERS.md) and the expanded
[pending live checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md). All live cases
remain Pending. No provider call, production data, scheduler, monitor execution,
publication or activation occurred.

Next: inspect fresh exact-head full repository normal/shuffled/dependency/
container/aggregate CI, then continue the next explicitly requested feature.
Main merge, release, preview publication, activation and personal/live testing
remain deferred until the owner's later instruction.


## Private blocker recording and clearing — 2026-11-01

Owner explicitly approved recording and clearing blockers. Added `/task_block` and
`/task_unblock`, separate signed-in no-script forms, exact private previews/
confirmation and receipts to review branch `feat/telegram-private-work-lookup`,
draft PR #572, candidate **9.73**. Actual main remains `a7b9b38` (released 9.59),
preserved on this branch. Deployment, preview publication, activation and personal/
live testing remain explicitly deferred. Initial prior-head `a2be3ff` inspection
found metadata passing and other checks running; those are not new-head acceptance.

Independent default-off `CSS_TELEGRAM_TASKS_BLOCK_ENABLED` / `tasks.block` and
`CSS_TELEGRAM_TASKS_UNBLOCK_ENABLED` / `tasks.unblock` require work read, source
modules and original private inbound/link/delivery/account/chat/bot proof. Metadata
lookup and other task grants grant neither write. Native task-owner/current-
follow-up/lead/concerned-officer authority is rechecked; noncoordinator recording
participants select only themselves. A coordinator may choose another active
person who already reads the case and every linked document; no access is granted.

Recording requires no existing blocker, an explicit follow-up person/exact date
and bounded reason. It refuses silent overwrite; existing-blocker amendments stay
in Office Connect or require a separate clearing first. Clearing requires a
recorded blocker and resolution reason, removes its follow-up fields, and keeps
native ability to clear despite an inactive former follow-up/task owner. Acting
user/source rights remain required. The exact preview shows actor-entered reason
and selected follow-up fields; old stored blocker details are hashed only and not
copied into Telegram. Native history retains the old and resolution details.

Task owner/state/submission/output, task deadline, dependency edges and pending
changed-direction history stay unchanged. Clearing one blocker does not resolve
prerequisites/decisions or bypass resubmission/acceptance checks. Done/Cancelled
tasks, completed/closed work and active formal consolidation review before/after
preview block amendments. Source/account/blocker changes, lost permissions,
revocation/pause/expiry/restore and cross-protocol contexts refuse stale actions.

Extracted `work_blockers.mutate_in_transaction` with strict caller-owned transaction
requirement; public `mutate` keeps its existing transaction wrapper and identical
native business rules. Telegram calls that helper so source/revision/event/audit,
preview consumption, receipt and private handoff are atomic. Audit/receipt/handoff
failure rolls back. Duplicate/concurrent confirmation changes once. Deletion
fences numeric-ID reuse; recovery reports recorded outcome/current flag without
replay or disclosure of stored blocker text, including later source changes.

Isolated Python 3.11 verification: **1961 broad regressions passed** across
`tests/test_telegram*.py`, `tests/test_work*.py`, audit-chain writers, deployment
and release checks. **659 current shuffled checks** (seed 311) passed across
blocker management/lookup, queue and all current task services/phone forms,
menu/action engine, existing task actions and private meeting webhook handling.
Zero failures/errors/skips in both groups; groups overlap. Earlier focused blocker
management services: 77 passed; combined service/phone/menu group: 97 passed;
native-work/menu/action wiring: 209 passed. All final changed-blocker and inactive-
former-owner clearing cases preceded broad/shuffled collection. No application
source edits followed these passing groups.

Native participant/coordinator/self-selection/member/document rules, no overwrite/
no-op, exact dates/strict fields, current source/context/terminal/formal-review
fences, unchanged prerequisites/changed direction with blocked resubmission,
strict caller-owned contract, audit/receipt/handoff rollback, concurrent retries,
ID reuse and later-current-state receipts pass. Two JavaScript-disabled phone
flows check separate scopes, prohibited other-person choice, CSRF/allowlists,
exact private preview/confirmation/retry, retained state/deadline/submission,
expired sessions and no outgoing provider calls. No native business rule or
permission/no-skips assertion was weakened.

Reports: `/tmp/telegram-blocker-manage-regressions.xml`,
`/tmp/telegram-blocker-manage-shuffled.xml` and
`/tmp/telegram-blocker-manage-verified.xml`; all pass the JUnit no-skips gate.
Candidate 9.73 metadata/increase over actual main 9.59, locks/vendor integrity,
installed compatibility, AI contract, Python compilation, local Markdown links
and whitespace pass. Existing Starlette/httpx deprecation warning remains.
Full exact-head repository normal/shuffled/dependency/container/aggregate CI still
requires inspection after push. Earlier-head results are not current acceptance.

See [blocker management behavior](TELEGRAM_BLOCKER_MANAGEMENT.md) and the expanded
[pending live checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md). All live cases
remain Pending. No provider call, production data, scheduler, monitor execution,
publication or activation occurred. Dependency amendments remain separate source
workflows; this feature changes only recorded blocker/follow-up fields.

Next: inspect fresh exact-head full repository normal/shuffled/dependency/
container/aggregate CI, then continue the next explicitly requested feature.
Main merge, release, preview publication, activation and personal/live testing
remain deferred until the owner's later instruction.


## Private task dependency management — 2026-11-01

Owner explicitly approved adding/removing task prerequisites. Implemented
`/task_dependency_add` and `/task_dependency_remove`, signed-in no-script forms,
exact private previews/confirmation and outcome recovery on review branch
`feat/telegram-private-work-lookup`, draft PR #572, candidate **9.74**. Actual main
remains `a7b9b38` (released 9.59), preserved on the review branch. Deployment,
preview publication, activation and personal/live testing remain deferred.

Independent default-off `CSS_TELEGRAM_TASKS_DEPENDENCY_ADD_ENABLED` /
`tasks.dependency_add` and `CSS_TELEGRAM_TASKS_DEPENDENCY_REMOVE_ENABLED` /
`tasks.dependency_remove` require work-read consent and current private inbound/
link/delivery/account/bot/chat proof. Other task/blocker/metadata scopes grant
neither action. Native current work-lead/concerned case/task-officer authority
must permit the active dependent task; ownership or follow-up responsibility
alone is insufficient. Both tasks must currently be readable in the same work.

Exact preview shows dependent/prerequisite IDs, titles, states, dependency
direction, consequences and mandatory actor-entered reason. It never projects
stored submissions, output criteria, blocker reasons or discussion. Adding
refuses self/duplicate/cross-work/cancelled-prerequisite links and cycles of any
length. Done prerequisites are allowed and labelled already satisfied. Removing
requires the exact existing link and can remove a cancelled prerequisite. Only
one edge/dependent revision/native history changes; other task fields, upstream
task, deadlines, blockers and changed-decision history stay unchanged. Removal
does not auto-submit or bypass remaining native submission/acceptance guards.
Done/Cancelled dependents, closed/completed work and active formal consolidation
review before/after preview refuse bot amendments.

Current task/work/document digest, full prerequisite record, source history and
same-work edge graph fence stale previews, including graph changes without task
revision/event changes. The adapter calls the existing native caller-owned
mutation inside the generic transaction. Source/task/edge/event/audit, consumed
preview, receipt and webhook reply handoff are atomic; failures roll back and
concurrent retry changes once. No native mutation or permission rule changed.

Additive nullable `telegram_operation.dependency_task_id` migrates idempotently
before trigger creation, preserving older operations. Pending previews are
cancelled/scrubbed if either task is deleted; target deletion clears both pointers,
prerequisite deletion clears its pointer and marks recovery, fencing numeric-ID
reuse. Retained-key cleanup clears both. Recovery reports original outcome and
current link/status or deletion with current source view, without replay.

Expanded menu status shortens repeated work-read prerequisite wording while
retaining each feature and full missing action consent. The upgrade test now
simulates the new trigger/column's absence and checks unchanged old operations.

Isolated Python 3.11 verification: **2072 broad regressions passed**
across Telegram, native work, audit-chain writers, deployment and release checks.
**766 shuffled current task/action/menu/phone checks** (seed 311)
passed. **318 combined dependency/phone/shared/native-work checks**
also passed, with a separate **1 maximum-origin menu/status budget check**.
All groups have zero failures/errors/skips; groups overlap. The final menu boundary
case was added after broad/shuffled collection and passed separately. No application
source edits followed the passing final combined/broad/shuffled groups.

Both 390×844 JavaScript-disabled phone flows, independent consent/pilots, current
coordinator-only/source rules, exact direction, self/cross-work/duplicate/cancelled/
acyclic guards, Done prerequisites/cancelled-link removal, stale tasks/work/docs/
graph/formal review/context, native remaining submission gates, audit/receipt/
handoff rollback, concurrent retries, both task deletion/ID reuse, retention and
later-current-state recovery pass. Initial checks caught the expanded missing-
consent status budget and a schema-upgrade fixture missing the new trigger; the
status was shortened and the upgrade fixture extended, then passing groups reran.
No native rule, permission assertion or no-skips gate was weakened.

Reports: `/tmp/telegram-dependency-regressions.xml`,
`/tmp/telegram-dependency-shuffled.xml`,
`/tmp/telegram-dependency-verified-final.xml` and
`/tmp/telegram-dependency-menu-limit.xml`; all pass the JUnit no-skips gate.
Candidate 9.74 metadata over actual main 9.59, dependency locks/vendor integrity,
installed compatibility, AI contract 1.12.0, Python compilation, local Markdown
links and whitespace pass. Existing Starlette/httpx deprecation warning remains.
Full exact-head repository normal/shuffled/dependency/container/aggregate CI still
requires inspection after push; prior-head evidence is not current acceptance.

See [dependency behavior](TELEGRAM_DEPENDENCY_MANAGEMENT.md) and
[pending live acceptance](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md). All live rows
remain Pending. No real Telegram message/provider registration, production data,
scheduler/monitor execution, deployment, publication or activation occurred.
Initial prior-head `936b7ab` inspection found metadata/dependency audit passing
and normal/shuffled/avatar checks running; those are not new-head acceptance.

Next: inspect fresh exact-head full repository normal/shuffled/dependency/
container/aggregate CI and continue only the next explicitly requested feature.
Main merge/release, preview publication, activation and live testing remain
deferred until the owner's later instruction.


## Private work and task comments — 2026-11-01

Owner explicitly approved work/task discussion posting. Implemented `/work_comment`
and `/task_comment`, signed-in JavaScript-free preparation, exact private previews/
confirmation and receipt recovery on branch `feat/telegram-private-work-lookup`,
draft PR #572, candidate **9.75**. Actual main remains `a7b9b38` (released 9.59),
preserved on the review branch. Deployment, preview publication, activation and
personal/live testing remain explicitly deferred.

Independent default-off `CSS_TELEGRAM_WORK_COMMENT_ENABLED` / `work.comment` and
`CSS_TELEGRAM_TASKS_COMMENT_ENABLED` / `tasks.comment` require separate work-read
consent and current private inbound/link/delivery/account/bot/chat proof. Neither
another task scope nor one comment scope grants the other. Private webhook-only
handling rejects group/topic/direct-worker paths. Consent grants no source access.

Native current work visibility, including every linked document, permits informal
discussion; task ownership/lead/officer status is not required simply to post.
Work-level comments accept no task; task comments require an exact task in that
work. Each form takes only target IDs and plain text, up to 1,000 characters with
normalized line endings. Unsupported reply/mention/edit/status/approval fields and
controls are refused. Literal @name creates no mention. The exact preview shows
target titles/IDs/current states and complete actor-entered text with visibility
notice; stored discussion, submissions, output and blocker reasons are not copied.

A comment creates native immutable message/revision history, normal permitted
follower notices and the author's observed-revision marker. Task/work/document
state, revisions, deadlines, ownership, submission, blockers, dependencies, events
and formal approvals remain unchanged. Native discussion stays available on
completed work, Done/Cancelled tasks and under active formal review. Changed
source after preview still requires a fresh preview; unrelated new comments do
not invalidate each other. No reply, mentions, edits, follow preference, digest
setting or access grant is added. Independently configured existing digests may
later include normal source notices; no scheduler/digest/provider is executed here.

Extracted strict caller-owned `work_discussion.post_in_transaction`; the public
`post` wrapper keeps its transaction and native body. AST comparison after SQL
indentation normalization confirms identical posting logic. The adapter uses that
helper inside generic confirmation, so comment/revision/follower notices/author
read marker, operation comment ID, preview consumption, receipt and reply handoff
commit atomically. Notice/receipt/handoff failure rolls back; retries/concurrent
confirmation post once. Native author-only edits and reply/mention rules remain
available unchanged to existing source callers.

Additive nullable `telegram_operation.comment_id` migrates before triggers and
preserves old operations. Pending task deletion cancels/scrubs task previews;
work deletion cancels/scrubs comment previews and clears routing/identifier fields,
fencing numeric-ID reuse. Native immutable history/FKs protect committed source
references. Retention clears comment/source routing IDs. Recovery checks current
source/thread/original author and reports recorded outcome, link/current revision
without stored text or replay. A later source edit changes only the reported
revision. Pending deleted-source recovery stays cancelled without describing a
replacement. Schema upgrade now simulates absence of the new column/trigger and
checks older operations acquire no new comment identifier.

Isolated Python 3.11 verification: **2229 broad regressions passed**
across Telegram/native work, integration submission API/MCP submissions, audit-chain
writers, deployment and release checks. **857 current shuffled
comment/dependency/blocker/task/action/menu/phone checks** (seed 311) passed.
**300 combined comment/phone/shared/native-work checks**
and an earlier **49 phone/menu/action/budget group** passed.
All groups have zero failures/errors/skips and overlap. All final comment/source-
access/line-ending/deletion assertions preceded broad/shuffled collection; no
application source edits followed these passing final groups.

Ordinary-reader and every-linked-document/source access, separate scopes/pilots,
strict thread/input boundaries, literal mentions, normalized text, native follower/
author-read effects, unchanged business state/reviews, terminal/formal discussion,
independent comments, current source/context/restore fences, native caller-owned
contract, atomic notice/receipt/handoff rollback, retries/concurrency, deletion/ID
reuse, retention and later edited-revision recovery pass. Both 390×844 JavaScript-
disabled phone flows pass CSRF/allowlists, exact text/target previews, confirmation/
retry, unchanged tasks/work and expired sessions with no outgoing calls. Expanded
menu/status fit the maximum supported origin. Initial checks required extending
the schema-upgrade fixture for the new column/trigger and respecting native lead
linked-document eligibility and append-only events in synthetic fixtures. Pending
work deletion now explicitly asserts the existing cancelled receipt and cleared
routing, without describing a reused ID. No native constraint, permission or
no-skips assertion was relaxed.

Reports: `/tmp/telegram-comment-regressions.xml`,
`/tmp/telegram-comment-shuffled.xml`, `/tmp/telegram-comment-verified-final.xml`
and `/tmp/telegram-comment-phone-wiring.xml`; all pass the JUnit no-skips gate.
Candidate 9.75 metadata over actual main 9.59, dependency locks/vendor integrity,
installed compatibility, AI contract 1.12.0, Python compilation, local Markdown
links and whitespace pass. Existing Starlette/httpx deprecation warning remains.
Full exact-head repository normal/shuffled/dependency/container/aggregate CI still
requires inspection after push; prior-head evidence is not current acceptance.

See [comment behavior](TELEGRAM_COMMENT_MANAGEMENT.md) and
[pending live acceptance](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md). All live rows
remain Pending. No real Telegram message/provider registration, production data,
scheduler/monitor execution, deployment, preview publication or activation occurred.
Initial prior-head `1e1063e` inspection found metadata/dependency audit/avatar
functional checks passing and normal/shuffled checks running. Those are not
new-head acceptance.

Next: inspect fresh exact-head full repository normal/shuffled/dependency/
container/aggregate CI and continue only the next explicitly requested feature.
Main merge/release, preview publication, activation and personal/live testing
remain deferred until the owner's later instruction.


## Private work and task replies — 2026-11-01

Owner explicitly approved replying to existing work/task comments. Implemented
`/work_reply` and `/task_reply`, signed-in no-script forms, exact private previews/
confirmation and recovery on branch `feat/telegram-private-work-lookup`, draft
PR #572, candidate **9.76**. Actual main remains `a7b9b38` (released 9.59), preserved
on the review branch. Deployment, preview publication, activation and personal/live
testing remain explicitly deferred.

Independent default-off `CSS_TELEGRAM_WORK_REPLY_ENABLED` / `work.reply` and
`CSS_TELEGRAM_TASKS_REPLY_ENABLED` / `tasks.reply` each require work-read consent
and current private inbound/link/delivery/account/bot/chat proof. Other comment/
task/read scopes enable neither reply, and one reply scope grants neither the
other nor ordinary comment posting. Groups/topics/direct-worker paths are refused.

Native current work visibility, including every linked document, permits informal
replies; ordinary source readers need no task-owner/lead/officer role. Selecting
work/task/parent grants no access. Exact parent ID must exist in the same selected
work-level or same-task discussion; cross-work/work-vs-task/other-task/missing
parents are refused. Same-thread replies to replies remain allowed. The form
accepts exact target IDs, parent ID and plain text up to 1,000 characters, normalizes
line endings and rejects controls/unsupported fields. Literal @name adds no mention.

Preview shows work/task IDs/titles/current states, exact parent number/current
revision/source link and complete actor-entered reply with visibility/notice
effects. Parent text/author names and other stored discussion/submission/output/
blocker contents stay in Office Connect. The full parent record is hashed only;
parent edits before preview pull or confirmation refuse stale input. Fresh preview
shows the new revision. Unrelated discussion remains independent. Current work/
task/document digest/history, source rights, modules, scopes/pilots, expiry and
original context are rechecked; revocation/account change/disconnect/restore/pause
cannot revive stale replies.

Uses the existing unchanged native `work_discussion.post_in_transaction` with
exact parent and no mentions. One immutable reply/revision, normal permitted
follower/eligible parent-author notices and author-read marker are created. Native
notice deduplication applies; inactive/no-longer-permitted parent authors and
self-replies create no parent-author notice. No follow/access/notification setting
is added, and no digest/scheduler/provider is enabled/executed. Work/task/document
state, revisions, ownership, submissions, blockers, dependencies, deadlines, events
and formal review/approvals stay unchanged. Native informal discussion remains
available on terminal work/tasks and under active formal review; changed source
still requires a fresh preview. Mentions, edits and stored discussion reads remain
source workflows.

Reply/history/notices/read marker, saved comment identifier, preview consumption,
receipt and private reply handoff are atomic; failures roll back and retries/
concurrent confirmation post once. Existing comment receipt/retention metadata is
reused; no source mutation logic, new table or identifier column was introduced.
Deletion and work-read-revocation fences include both reply scopes. Native
append-only parent history and FKs protect parent/thread deletion/ID reuse, with
constraints intact. Recovery checks source/thread/original author/nonempty parent,
reports original reply outcome/parent/link/current reply revision, and never
projects saved parent/reply text or posts again. A later native author edit changes
only the reported reply revision. Ordinary post forms now point to separate reply
commands while retaining their strict no-parent contract.

The native discussion page now displays comment numbers and current revisions
so the reply target can be selected from visible source metadata without inspecting
a URL. Both final phone flows verify that source label before preparing the reply.

Isolated Python 3.11 verification: **2337 broad regressions passed**
across Telegram/native work, integration submission API/MCP submissions, audit-chain
writers, deployment and release checks. **963 current shuffled
reply/comment/dependency/blocker/task/action/menu/phone checks** (seed 311) passed.
Focused reply services: **104 passed**; earlier phone/shared/menu/
maximum-origin group: **49 passed**, with **47
earlier shared wiring checks**. All groups have zero failures/errors/skips and
overlap. Core reply behavior and service cases were fixed before broad/shuffled
collection. Visible source comment numbers/revisions and their phone assertions
were added afterward and verified separately by **2 final
390×844 JavaScript-disabled phone flows**. No source edits followed those final
phone checks or the completed broad/shuffled groups.

Exact thread/work/task/parent boundaries, ordinary-reader/current document access,
independent scopes/pilots, strict plain fields/literal mentions/normalized text,
hash-only parent storage, stale edited-parent pulls/confirmations and fresh revision
previews, replies to replies, eligible/no-access/inactive/self parent notices,
unchanged business/formal/terminal source state, independent comments, current
context/revoke/restore fences, atomic notice/receipt/handoff rollback, retries/
concurrency, immutable parent/FK protection, retention and edited-reply revision
recovery pass. Both final phone cases verify native source ID/revision discovery,
separate grants/menu/forms, CSRF/strict parent/thread fields, exact full text/parent
preview, confirmation/retry, unchanged work/tasks, no mentions/outgoing calls and
expired sessions. No native rule, source constraint, permission or no-skips gate
was changed or weakened.

Reports: `/tmp/telegram-reply-regressions.xml`,
`/tmp/telegram-reply-shuffled.xml`, `/tmp/telegram-reply-focused.xml`,
`/tmp/telegram-reply-phone-wiring.xml`, `/tmp/telegram-reply-phone-final.xml` and
`/tmp/telegram-reply-wiring.xml`; all pass the JUnit no-skips gate.
Candidate 9.76 metadata over actual main 9.59, dependency locks/vendor integrity,
installed compatibility, AI contract 1.12.0, Python compilation, local Markdown
links and whitespace pass. Existing Starlette/httpx deprecation warning remains.
Full exact-head repository normal/shuffled/dependency/container/aggregate CI still
requires inspection after push; prior-head evidence is not current acceptance.

See [reply behavior](TELEGRAM_REPLY_MANAGEMENT.md) and
[pending live acceptance](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md). All live rows
remain Pending. No real Telegram message/provider registration, production data,
scheduler/monitor execution, deployment, preview publication or activation occurred.
Initial prior-head `7c0e8a5` inspection found metadata/dependency audit/avatar
functional checks passing and full normal/shuffled checks running; those are not
new-head acceptance.

Next: inspect fresh exact-head full repository normal/shuffled/dependency/
container/aggregate CI and continue only the next explicitly requested feature.
Main merge/release, preview publication, activation and personal/live testing
remain deferred until the owner's later instruction.


## Private author-owned comment editing — 2026-11-01

Owner explicitly approved editing their own work/task comments. Implemented
`/work_comment_edit` and `/task_comment_edit`, signed-in no-script forms, exact
private previews/confirmation and recovery on branch
`feat/telegram-private-work-lookup`, draft PR #572, candidate **9.77**. Actual main
remains `a7b9b38` (released 9.59), preserved on the review branch. Deployment,
preview publication, activation and personal/live testing remain deferred.

Independent default-off `CSS_TELEGRAM_WORK_COMMENT_EDIT_ENABLED` /
`work.comment_edit` and `CSS_TELEGRAM_TASKS_COMMENT_EDIT_ENABLED` /
`tasks.comment_edit` require work-read consent and current private inbound/link/
delivery/account/bot/original chat proof. Other comment/reply/task/read grants
provide neither edit; one edit scope grants neither the other nor post/reply
creation. Group/topic/direct-worker paths are refused. Consent grants no access.

Only the original author with current work/every-linked-document access may edit,
including their own replies. Reader/lead/officer/technical administrator status
cannot override authorship. Exact comment must be in the selected work-level or
same-task thread. Form takes exact source IDs/current comment revision and complete
plain replacement text (up to 1,000 characters), normalizes line endings and refuses
controls, unsupported parent/mention/progress fields, invalid/stale revisions and
unchanged text. Visible source comment number/revision supports selection.

Preview shows exact target, current → next revision, unchanged reply parent if any,
source link and full replacement text with visibility notice. Old text/history
and mentioned identities stay in Office Connect. The current comment/mention
metadata is hashed only; older revision contents are not fetched. Existing
structured mentions are preserved via native mentions=None and currently validated
before preview/confirmation; inactive/no-access mentions block editing, including
eligibility lost after preview without a source revision change. Their count alone
is shown. Literal @name adds no mention. Amend mention selection in source if needed.

One immutable revision is added; original comment, author, timestamp, parent and
all old revisions remain intact. Native edit notice/author-read behavior applies,
without new follower/reply notices or notification preferences. Work/task/document
status, revisions, ownership, submissions, blockers, dependencies, deadlines, events
and formal review/approvals remain unchanged. Native informal editing can remain
available on completed work, terminal tasks and under active formal review. Unrelated
comments remain independent. Newer edits before preview retrieval/confirmation
require review of the latest revision and a fresh preview; no later text is overwritten.
Current source/module/scope/pilot/context/expiry/revoke/account/disconnect/restore
fences remain enforced.

Extracted strict caller-owned `work_discussion.edit_in_transaction`; public `edit`
retains its wrapper and identical native edit body (AST parity verified). Revision,
retained mentions/native notice/read effects, recorded edit revision, consumed
preview, receipt and private reply handoff commit atomically. Failures roll back;
duplicate/concurrent confirmation adds one revision once. Native source constraints
and authorship/history/mention behavior remain unchanged for existing callers.

Additive nullable `telegram_operation.comment_revision` migrates before triggers
and leaves older operations unchanged/null. Existing comment_id stores the selected
comment; the recorded saved revision is retained separately from current source
revision. Deletion/revocation fences include both edit scopes. Work deletion and
retained-key cleanup clear identifier/revision/routing fields; native immutable
history/FKs protect source references. Recovery checks current source/thread/author
and reports original edit revision/current revision plus a link, without stored
text/replay/overwrite. A later native edit to revision 3 leaves an earlier operation
reported as recorded 2/current 3. Existing comment/reply forms now link to separate
edit commands and keep their original field contracts.

Shared status lists the repeated work-read prerequisite once when both action and
read consent are missing, while retaining every feature/full missing action consent
and the separate Work lookup consent. This fixes the maximum-origin message budget
without hiding availability details. Schema-upgrade coverage simulates absence of
the new column and checks that old pending operations receive no saved edit revision.

Isolated Python 3.11 verification: **2466 broad regressions passed**
across Telegram/native work, integration submission API/MCP submissions, audit-chain
writers, deployment and release checks. **1090 current shuffled
edit/reply/comment/task/action/menu/phone checks** (seed 311) passed.
**337 combined edit/phone/shared/native-work checks** passed,
including both final inactive-mention-after-preview cases. Earlier focused edits:
**123 passed**; earlier phone/shared/menu/budget group:
**49 passed**. All groups have zero failures/errors/skips and
overlap. All final service/phone cases preceded broad/shuffled collection; no
application source edits followed the passing final groups.

Original-author authority against reader/lead/officer/technical-admin overrides,
exact source/thread/revision selection, plain/no-op refusal, stale preview retrieval/
confirmation and fresh revision, old immutable history/reply parent, retained
mentions/current eligibility before/after preview, native notice/read effects,
unchanged terminal/formal/business state, current source/context/revocation/restore
fences, strict caller-owned contract, notice/receipt/handoff rollback, retries/
concurrency, retention and recorded-versus-current revision recovery pass.
Both 390×844 JavaScript-disabled phone flows verify source comment ID/revision,
independent grants/menu/forms, CSRF/strict fields, other-author/stale revision
refusal, full exact replacement preview, confirmation/retry, old history, unchanged
work/tasks, no mentions/outgoing calls and expired sessions. Native discussion and
submission API/MCP callers pass with the identical public edit body. Initial shared
wiring exposed the expanded maximum-origin status budget; the repeated work-read
prerequisite is now listed once without hiding any feature or missing action
consent. Final combined/broad/shuffled groups include that passing budget case.
No native constraint, author/permission assertion or no-skips gate was weakened.

The initial broad attempt was interrupted after the 8.8 GiB temporary volume filled
with retained synthetic test databases (browser crashes and SQLite disk-full setup
errors; 1982 reported cases, 2 failures/229 errors). Its report is retained separately
as `/tmp/telegram-comment-edit-regressions-disk-full-interrupted.xml` and is not
acceptance evidence. Removed only completed/interrupted synthetic pytest directories,
preserving XML reports, and reran the entire unchanged broad command with
`--basetemp=/workspace/office-test-tmp/comment-edit-regressions` on the larger
workspace volume. The passing broad count above is from that clean rerun.
`docs/CLOUD_WORKSPACE.md` now records capacity checks, separate larger-volume
pytest scratch paths for concurrent runs, report preservation and clean reruns.

Reports: `/tmp/telegram-comment-edit-regressions.xml`,
`/tmp/telegram-comment-edit-shuffled.xml`, `/tmp/telegram-comment-edit-verified.xml`,
`/tmp/telegram-comment-edit-focused.xml` and
`/tmp/telegram-comment-edit-phone-wiring.xml`; all pass the JUnit no-skips gate.
Candidate 9.77 metadata over actual main 9.59, dependency locks/vendor integrity,
installed compatibility, AI contract 1.12.0, Python compilation, local Markdown
links and whitespace pass. Existing Starlette/httpx deprecation warning remains.
Full exact-head repository normal/shuffled/dependency/container/aggregate CI still
requires inspection after push; prior-head evidence is not current acceptance.

See [editing behavior](TELEGRAM_COMMENT_EDITING.md) and
[pending live acceptance](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md). All live rows
remain Pending. No real Telegram message/provider registration, production data,
scheduler/monitor execution, deployment, preview publication or activation occurred.
Initial prior-head `6a83c07` inspection found metadata/dependency audit/avatar
functional checks passing and full normal/shuffled checks running; those are not
new-head acceptance.

Next: inspect fresh exact-head full repository normal/shuffled/dependency/
container/aggregate CI and continue only the next explicitly requested feature.
Main merge/release, preview publication, activation and personal/live testing
remain deferred until the owner's later instruction.


## Colleague mentions in comments and replies — 2026-11-01

Owner explicitly approved colleague mentions in work/task comments and replies.
Added optional explicit selection to the existing `/work_comment`, `/task_comment`,
`/work_reply` and `/task_reply` forms/preview/confirmation protocols on branch
`feat/telegram-private-work-lookup`, draft PR #572, candidate **9.78**. Actual main
remains `a7b9b38` (released 9.59), preserved on this branch. Deployment, preview
publication, activation and personal/live testing remain explicitly deferred.

Independent default-off `CSS_TELEGRAM_WORK_MENTIONS_ENABLED` / `work.mentions`
requires work-read consent plus the applicable existing post/reply permission and
pilot. Auxiliary consent alone cannot post/reply/edit or grant source access; one
posting grant alone cannot select colleagues. Unmentioned posts remain available
without auxiliary consent. Existing text edits retain their original strict fields
and preserve existing mention metadata using native current eligibility checks.

New source-only GET loader within the signed-in forms accepts original private
request/source IDs, never draft text, CSRF/action keys or selected people in the
URL. It prepares/posts nothing. Current work/task/optional-parent scope is verified
before native `work_updates.candidates` returns only active current readers of
that work and every linked document. No directory before selection, on unavailable
source, or without mention consent/pilot. No person is preselected. Main POST fields,
CSRF/key/origin checks remain separate. Optional repeated mentions are declared
only for these comment/reply routes; other keys stay single-valued/allowlisted and
unrelated shared forms retain their contracts. Body/field limits bound selection.

Up to 20 distinct strict account IDs normalize in sorted order; malformed,
duplicate, over-limit, inactive and nonreader selections are refused. Full selected
account/role/active/resource/display-name snapshots bind the exact private preview.
Message plus each selected name/account are displayed, with native notice/no-access
effects. Any name/current source eligibility change before pull/confirmation
requires a fresh preview, including document-access loss without revision change.
Stored parent/discussion/submission contents remain in Office Connect. Oversized
Unicode previews refuse rather than silently dropping people or message text.

Existing unchanged native `work_discussion.post_in_transaction` receives validated
IDs. Message/revision/structured mentions, normal permitted notices/author-read
marker, consumed preview, receipt and private handoff commit atomically. Notice/
receipt/handoff failure rolls back all; duplicate/concurrent confirmation posts
once. Native parent/follower/mention priority deduplicates one person/message;
self mention records metadata without a self-notice. No follow/notification setting,
source membership/access, external destination or scheduler/digest/provider execution
is added. Existing independent digest policies remain separate. Task/work/document
state, revisions, ownership, submissions, blockers, dependencies, deadlines, events
and formal review/approvals stay unchanged; native informal terminal/formal discussion
behavior is preserved.

Current auxiliary/base/read scopes and pilots, source rights/modules, recipient
names/eligibility, expiry and original account/bot/chat/context are rechecked.
Revoking auxiliary consent cancels/scrubs pending previews in all four posting flows
conservatively, including unmentioned pending previews; fresh unmentioned posting
remains available under its own grants. Existing edit previews/committed messages
keep their own permissions. Pause, disconnect, restore and context loss cannot
produce stale selected-mention creation. Core receipts remain source/thread/author
bound, report original post/current revision without stored recipient names, and
never replay notices. Existing deletion/retention rules remain intact. No new
business action, source mutation rule/table or receipt identifier was introduced.

Isolated Python 3.11 verification: **2604 broad regressions passed**
across Telegram/native work, integration submission API/MCP submissions, audit-chain
writers, deployment and release checks. **1227 current shuffled
mention/edit/reply/comment/task/action/menu/phone checks** (seed 311) passed.
**148 final mention/phone/menu/budget checks** passed,
alongside **4 dedicated phone flows** and **239
earlier shared action/menu/unmentioned comment/reply/budget checks**. All groups
have zero failures/errors/skips and overlap. All final service/phone assertions
preceded broad/shuffled collection; no application source edits followed these
passing final groups.

All four posting modes, independent auxiliary/base/read consent/pilots, empty/
loaded/source-scoped/paused choices, strict/duplicate/20-person selection, current
name/active/work/every-document eligibility (including permission loss without
source revision), revoke/pause/expiry/disconnect/restore, native mention/follower/
parent notice priority/deduplication and self behavior, unchanged source/access/
preferences, atomic notice/receipt/handoff rollback and concurrent/repeated
confirmation pass. Four 390×844 JavaScript-disabled phone cases verify exact consent,
source-ID-only loader URLs with no prepared/posting effects, blank default choices,
CSRF/allowlists, invalid recipients, full message/name/account preview, confirmation/
retry, unchanged work/tasks, native mention/notice rows, no outgoing calls and
expired sessions. Existing unmentioned posts/replies, mention-preserving text edits
and unrelated shared-form defaults remain protected by regressions.

Initial new-test assertions expected a text reply after disconnect/restore and
used an ambiguous selector for the new GET+POST forms. They now explicitly assert
no inline response/no source mutation after context loss, and select the POST form
for its CSRF/origin/key; native no-response and strict field behavior were preserved.
No native constraint, permission/eligibility assertion or no-skips gate was weakened.

Reports: `/tmp/telegram-mentions-regressions.xml`,
`/tmp/telegram-mentions-shuffled.xml`, `/tmp/telegram-mentions-verified-complete.xml`,
`/tmp/telegram-mentions-phone-final.xml` and `/tmp/telegram-mentions-wiring.xml`;
all pass the JUnit no-skips gate. Long concurrent suites use separate workspace
`--basetemp` paths per CLOUD_WORKSPACE.md; completed synthetic databases are removed
after keeping reports. No temporary-volume exhaustion occurred in these runs.
Candidate 9.78 metadata over actual main 9.59, dependency locks/vendor integrity,
installed compatibility, AI contract 1.12.0, Python compilation, local Markdown
links and whitespace pass. Existing Starlette/httpx deprecation warning remains.
Full exact-head repository normal/shuffled/dependency/container/aggregate CI still
requires inspection after push; prior-head evidence is not current acceptance.

See [mention behavior](TELEGRAM_COLLEAGUE_MENTIONS.md) and
[pending live acceptance](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md). All live rows
remain Pending. No real Telegram message/provider registration, production data,
scheduler/monitor execution, deployment, preview publication or activation occurred.
Initial prior-head `cb192da` inspection found metadata/dependency audit/avatar
functional checks passing and full normal/shuffled checks running; those are not
new-head acceptance.

Next: inspect fresh exact-head full repository normal/shuffled/dependency/
container/aggregate CI and continue only the next explicitly requested feature.
Main merge/release, preview publication, activation and personal/live testing
remain deferred until the owner's later instruction.
