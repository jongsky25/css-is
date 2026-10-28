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
Full normal/shuffled application CI is required before merge. Results are pending.

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
