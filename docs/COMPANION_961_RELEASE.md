# Companion 9.61 production release — November 2, 2026

Owner explicitly approved merging and deploying 9.61. Before merge, main remained
`adb83b4` (9.60); PR head `8280506` was unchanged, merge state was clean, and all
required checks passed. [PR #579](https://github.com/jongsky25/css-is/pull/579)
merged as `25fe8125bb2329b52a84cd34604a047d0b37e0e7`.

PR evidence: [full CI 41382361015](https://github.com/jongsky25/css-is/actions/runs/41382361015)
passed 8,448 tests in each normal/shuffled order with zero failures/skips, plus
AI, dependency/container, metadata and aggregate gates.
[Avatar acceptance 41382360975](https://github.com/jongsky25/css-is/actions/runs/41382360975)
passed 137 interaction tests and 432 rendered rig/stage/mood/theme cases.

Production [run 41393018082](https://github.com/jongsky25/css-is/actions/runs/41393018082)
reruns complete checks on merge commit `25fe8125bb2329b52a84cd34604a047d0b37e0e7`
before the existing fresh-backup/version/upload/live-verification gates. Initial
state: in progress. No check, backup or version guard is bypassed. Deployment
completion must be observed and independently verified before claiming success.

This release record is saved on `docs/companion-961-release-handoff` rather than
pushing documentation directly to production-connected main. Appearance defaults,
outfits, personal preferences and schedules are not changed by this operation.
No real business form or Telegram action is used as a smoke test.

Telegram's branch remains untouched. Its later update from main must preserve the
9.60/9.61 release history, reconcile version/cache/status files, and run its own
checks. It is not merged or deployed as part of this release.

Next: observe the production run, preserve any failed gate, then verify live 9.61,
the deployed source commit and new companion assets. Record the final evidence below.
