# Supplies integration release 7.78

This release integrates S0.1 through S3.2 with main at `715753fd29d8ec5d16f630737b99f03c5d5a5d8d` (7.77), retaining its unrelated changes and release history. Earlier increment handoffs describe their local implementation checkpoints; 7.78 is the combined integration release.

Supplies defaults disabled and grants no operational privileges merely because an account is an administrator. Enabling it and adopting actual opening stock require real business-role assignments and reconciled physical counts; this merge imports no uploaded workbook balances and assigns no live roles. S3.3 corrections and subsequent warning/replenishment increments remain planned.

The Hugging Face deployment manifest now includes every Supplies runtime module, and the in-app version, CHANGELOG.md and service-worker cache all use 7.78. Existing CI and the deployment workflow retain their normal verification/backup gates.

Validation for this merge includes the complete repository regression suite, browser checks, release/dependency metadata checks and the export/data smoke check. Individual increment browser/PDF evidence remains in the linked implementation plan and handoffs. The merge result and final gate results are recorded with the pull request.
