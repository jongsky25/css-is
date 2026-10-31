# Cloud/mobile setup status

Updated: 2026-10-31. Repository: `jongsky25/css-is` (Office Connect BLHSD).
Setup branch: `setup/cloud-mobile-continuity`.

## Current step: 5 — backup bucket private; admin/recovery verification pending

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
- [ ] 5. Hosting/log/storage access and recovery verified.
- [ ] 6. Monitoring gaps assessed and reusable workflow documented.

## Next action

See [operations findings](OPERATIONS_ACCESS.md). The owner-authorized bucket
privacy change is complete: anonymous metadata/listing is denied, production
health passes, and a new periodic snapshot appeared after the change. Next:
owner admin review of Operations/Backups, exact mount identity confirmation and
an approved isolated recovery exercise. Assess the earlier public exposure.
Steps 1–4 are complete; step 5 remains open for those checks. No restart or
production code deployment was performed.

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
