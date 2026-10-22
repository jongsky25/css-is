# S6.2 — Integrated acceptance, concurrency and recovery

Status: **Verified locally**, October 21, 2026. Depends on verified S6.1. Local application version: **7.85**. This increment adds synthetic integration checks and evidence; it changes no production code or schema.

## Integrated acceptance

The exact section 9 paper-ream scenario passed in a real Chromium session through browser forms, HTTP routes, services, the SQLite ledger and read-only reports. The reproducible script is `scripts/verify_supplies_s62_browser.py`; it initializes a fresh temporary database before importing the app, so no project database is copied or changed. Separate requesters A and B submitted requests for 8 and 7 reams. A separate approver reduced A to 6 and approved B for 7. A custodian partially issued 4 to A; A cancelled the remaining 2; a separate replenishment approver approved the calculated need for 21; two deliveries accepted 10 and 11; B received and acknowledged 7; and B returned 1 usable ream. The final on-hand, reserved, available, outstanding demand and approved incoming figures were `(21, 0, 21, 0, 0)`.

The focused test asserts every intermediate checkpoint in section 9, including the idempotent issue retry, oldest-first allocation after cancellation and delivery, stock-card running balances `[10, 6, 16, 9, 20, 21]`, net issue consumption `11`, one usable return, no outstanding replenishment, and no foreign-key violations. The Chromium walk covers the same main sequence using the real forms and confirms the final reports. Screenshots: [partial issue](evidence/supplies-s6-2/partial-issue-mobile.png), [partial delivery](evidence/supplies-s6-2/partial-delivery-mobile.png), [final stock card](evidence/supplies-s6-2/final-stock-card-mobile.png), and [final inventory](evidence/supplies-s6-2/final-inventory-mobile.png). No page-level horizontal overflow or browser page errors occurred at 390px.

## Contention, authority and recovery

Two independent SQLite connections competed to receive the same eight approved units. Exactly one committed; the other saw a conflict, leaving one receipt and a two-unit incoming remainder. An injected allocator failure after delivery posting rolled back the delivery, receipt, stock movement, commitment change and operation key together. Invalid CSRF created no decision; a revoked request approver could not act; a stale approval revision failed; and disabling Supplies blocked a new receipt while inventory and fulfillment remained readable.

The backup rehearsal used the application's `make_backup` and `restore_backup` on a disposable database containing both Supplies records and unrelated application accounts, organization units and a setting. A post-snapshot item and setting change were rolled back by the restore. Counts, stock balances, event sequence, operation keys, the unrelated setting, SQLite integrity and foreign keys matched the saved snapshot. The restore also created its pre-restore safety snapshot. This demonstrates the mechanism with synthetic data; a real shared-database restore still requires coordinated recovery across other office activity.

Existing Supplies regression cases cover the additional section 9 boundaries: zero-threshold stockout, exact threshold, unset target, mixed-item fulfillment, missing or self approver, revocation, competing issues, partial cancellation, true return versus erroneous reversal, stocktake loss, receipt reversal after consumption, rejected delivery, duplicate import, rollback, print/export totals, and disabled-mode reads. The new tests are in `tests/test_supplies_acceptance.py`.

## Verification

The relevant regression gate passed **762 tests**, with no failures or skips and one existing Starlette/httpx deprecation warning:

```bash
PATH=/workspace/scratch/supplies-venv/bin:$PATH python -m pytest -o addopts= -q tests/test_supplies*.py tests/test_search.py tests/test_deploy_hf.py tests/test_release_checks.py tests/test_work.py tests/test_browser_security.py tests/test_dependency_gates.py tests/test_backups.py tests/test_auth_rbac.py tests/test_phase0_security.py --junitxml=/workspace/scratch/supplies-s62-gate-final.xml
python scripts/check_release.py junit /workspace/scratch/supplies-s62-gate-final.xml
```

An initial run found a flaky existing import test: it compared the staged XLSX SHA-256 with a separately regenerated workbook whose ZIP timestamps can differ. `tests/test_supplies_import_review.py` now checks the exact uploaded bytes against the staged source hash; the isolated rerun and final gate pass. The release metadata check still passes at 7.85. Dependency lock inputs, `pip check`, vendored PDF.js file verification (188 files), Python compilation and `git diff --check` pass. A fresh vulnerability scan of the built container was not run locally; the repository's CI dependency-audit job remains the authoritative gate for that evidence.

The full repository runner passed with `CSS_DB` set to a disposable synthetic database:

```bash
CSS_DB=/path/to/disposable/synthetic.db PATH=/workspace/scratch/supplies-venv/bin:$PATH bash run_tests.sh
```

It reported **5,073 tests passed**, no failures or skips, with two pre-existing dependency deprecation warnings. Its `qa_smoke.py` phase reported **4 checks passed**. The disposable database had no unrelated people, events or accounts, so the smoke check warned that those other-module data paths were not exercised. The full pytest suite and focused Supplies browser/report/restore checks provide the relevant technical coverage; this run does not stand in for a populated-data smoke or staff pilot. The project database was not opened by that runner.

No live balances, staff grants or feature flags were changed. No merge, push or deployment was performed. The user's stop-merging instruction remains in effect.

**Next eligible increment after verification: S6.3 — reconciled cutover and staff pilot.** That phase requires real physical counts, named staff roles, a coordinated cutoff and staff acceptance; passing synthetic checks alone does not authorize or complete it.
