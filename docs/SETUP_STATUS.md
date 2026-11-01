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
