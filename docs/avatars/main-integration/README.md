# Companion upgrade on current main — v9.04

This integration is based on current main d01f417 (v9.03), not the earlier
v8.57 verification branch. It ports the complete sixteen-species illustrated
catalog, optional wardrobe and shared motion from reviewed source 48133d4.
It preserves newer main application, search, scheduler, dependency and release
checks. The unrelated thread-owned reader and archived diagnostic tree are not
imported. Appearance preferences use main's existing connection lifecycle.

The two preference columns are additive and default existing users to seasonal
appearance. Identity, care, growth, cooldowns, account roles and opt-in audio remain.
The deployment allowlist includes companion_wardrobe.py. APP_VERSION, changelog,
changed avatar asset URLs and service-worker cache identify this release as 9.04.

## Validation status

127 local core/wardrobe/appearance/onboarding/packaging cases pass; qa_preflight
is GREEN (only the existing missing-backup-directory warning). The initial local
attempt lacked current main's locked rapidfuzz dependency; after installing the
current requirements-test.txt, the rerun passes. That initial attempt is not
acceptance evidence. Browser interactions, all eight animal care flows, native
visibility/touch/keyboard, pointer arbitration, seasonal refresh and four bounded
30-second CPU4 mobile frame checks run on this integration. Dedicated hosted
acceptance also checks all 432 animal rigs and actual themed contact sheets.
[Hosted avatar acceptance 40635843512](https://github.com/jongsky25/css-is/actions/runs/40635843512)
passes 131 tests with zero failures/skips, all 432 rig cases, and six actual themed
sheets (1,170 cards). All four 30-second CPU4 mobile frame samples meet 33 ms;
reported p95 values are 16.7–16.8 ms. The archive digest, 27 source-file hashes,
case counts and sample protocol were independently verified in
[hosted-avatar-audit.json](hosted-avatar-audit.json). The original ZIP is retained.
This is bounded current-application frame acceptance, not a new full memory matrix.
[Full application CI 40635843471](https://github.com/jongsky25/css-is/actions/runs/40635843471)
passes both normal and shuffled orders: **8,028 tests per order, zero failures,
errors or skips**, plus all 447 offline AI cases per report. Metadata, dependency
and aggregate Required checks pass. [application/audit.json](application/audit.json)
records independent archive hashes, all JUnit cases and strict AI checks against
GitHub's exact temporary checkout 0eae87ed (same tree as branch bb91698).
Later report-only changes do not change the accepted production or test sources.
All pre-merge automated acceptance is complete. Current deployment status is
tracked by the existing [main deployment workflow](https://github.com/jongsky25/css-is/actions/workflows/deploy-hf.yml).

Historical full matrix evidence remains available in
[PR #526](https://github.com/jongsky25/css-is/pull/526) and its source-specific
[report](https://github.com/jongsky25/css-is/blob/48133d47d4eaec576a320ae103bf8c809e4d40c5/docs/avatars/completion/REPORT.md).
Those timing/memory comparisons concern frozen fecd276 versus accepted 2B;
they are not re-labelled as measurements of this current-main integration.
The original 2B exception and unresolved results remain recorded there. No GC,
root-retention, native-hook, observer calibration or disposal probe was resumed.
No physical-phone testing is claimed. No new runtime dependency or remote asset.

## Release and rollback

Merge to main uses the existing gated deployment workflow, including full tests,
strict offline AI evidence, dependency audits, version check, fresh backup and
live-version verification. None of those safeguards are bypassed. Use a normal
revert commit and a fresh version/cache bump for rollback. Leave the additive
columns unused rather than dropping or clearing saved preferences or care data.

## Navigation contract correction

The first hosted avatar job stopped after 123 passes on an imported page-hide
assertion that expected cached pages to keep running animations. That conflicts
with the shared visibility policy. The current test instead proves that persisted
page-hide pauses and retains the same animation objects, persisted page-show
resumes those objects, and real navigation stops only avatar motion while leaving
an unrelated animation alone. The corrected local case passes. Production JS is
unchanged by this test correction; the original failure is retained under
development/. Hosted acceptance was rerun and passes all 131 cases, including this corrected check.

## Supplemental local full-suite attempt

The local shuffled application attempt reached 84% before SQLite could not
create another fixture DB because the separate 8.8 GiB /tmp volume filled with
retained synthetic pytest fixtures. Its original error log is retained under
development/. Completed fixture directories were moved intact to the larger
workspace volume, freeing /tmp; no user data or historical archive was deleted.
The affected MCP meal-request case passes on replay after freeing space. This partial
local run is not accepted as a full-suite pass; isolated hosted normal/shuffled
results remain authoritative.

## Rechecking retained evidence

The original avatar and application ZIPs are retained beside their audit JSONs.
Verify their recorded SHA-256 values before extracting. JUnit acceptance uses
scripts/check_release.py junit; strict AI reports must be checked from exact
checkout 0eae87edb718ba76a067bbe0e2f2ef488ca72bb3 because their provenance binds
the Git commit as well as source hashes. The GitHub checkout is temporary and
does not represent an earlier main merge. No report or acceptance gate was
modified to accept another source.
