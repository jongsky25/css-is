# Cloud/mobile setup status

Updated: 2026-10-31. Repository: `jongsky25/css-is` (Office Connect BLHSD).
Setup branch: `setup/cloud-mobile-continuity`.

## Current step: 3 — complete; main protection verified

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
- [ ] 4. Separate preview/staging usable from a phone.
- [ ] 5. Hosting/log/storage access and recovery verified.
- [ ] 6. Monitoring gaps assessed and reusable workflow documented.

## Next action

Begin step 4: assess a separate staging/preview environment for phone review.
Inspect the existing Hugging Face deployment and persistence requirements before
choosing hosting. Use synthetic data, separate credentials and disabled real
notifications. Do not merge or deploy this setup branch to production. Steps 1–3
are complete; the historical observations below retain the earlier setup evidence.

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
