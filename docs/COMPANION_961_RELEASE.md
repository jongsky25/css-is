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
before the existing fresh-backup/version/upload/live-verification gates. All release gates and deployment succeeded. No check, backup or version guard
was bypassed.

This release record is saved on `docs/companion-961-release-handoff` rather than
pushing documentation directly to production-connected main. Appearance defaults,
outfits, personal preferences and schedules are not changed by this operation.
No real business form or Telegram action is used as a smoke test.

Telegram's branch remains untouched. Its later update from main must preserve the
9.60/9.61 release history, reconcile version/cache/status files, and run its own
checks. It is not merged or deployed as part of this release.

## Verified production evidence

- Merge-commit normal suite: 8,448 passed, 2 warnings, 2078.92 seconds.
  Shuffled suite: 8,448 passed, 2 warnings, 1611.52 seconds.
  Both JUnit gates report zero failures/skips. Metadata, dependency audit and
  aggregate Required checks succeeded.
- Deployment succeeded with fresh verified snapshot
  `css_is_20261102_135300_manual.db` (OK, 49.3 MB); no backup bypass.
- Hugging Face Space commit: `3d980139c515a444337969ca22e087856497e720`.
- Independent read-only check: runtime RUNNING; revision-pinned build manifest
  version 9.61 and source `25fe8125bb2329b52a84cd34604a047d0b37e0e7`;
  public `/login` returned 200 and displayed 9.61.
- SHA-256 comparison matched all 13 checked files: six public CSS/JS/SVG assets
  and seven revision-pinned templates/Python modules against the merged source.
- Final read-only Telegram diagnostics job succeeded; the overall production
  workflow completed successfully.

Production: https://equityinhealth-office-connect.hf.space

To use a new Christmas outfit, select it in Appearance and choose Publish now.
Saved Halloween settings are intentionally retained until changed. A personal
companion preference may also need Follow seasonal appearance. No live appearance
setting, schedule, business form or Telegram provider action was changed in this
release verification.

Next Telegram integration remains separate: update its branch from main when
requested, retain 9.60/9.61 history, reconcile CHANGELOG.md, version.py,
static/js/sw.js and docs/SETUP_STATUS.md, then run its required checks. A clean
runtime merge observed earlier is not a guarantee against later branch changes.
