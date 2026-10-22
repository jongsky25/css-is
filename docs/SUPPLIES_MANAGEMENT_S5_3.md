# S5.3 — Partial delivery, acceptance and stock receipt

Status: **Verified locally**, October 21, 2026. Depends on verified S5.2. Local application version: **7.84**.

## Behavior

A current custodian records a delivery against an approved, ordered or partially received replenishment. Each selected line captures delivered, accepted and rejected units; accepted plus rejected must equal delivered. Rejected units require a reason and post no stock. Supplier, DR, receipt date, optional APR/procurement details, cost, expiry and notes remain in immutable delivery evidence. The delivery cannot exceed the unreceived approved remainder, and an all-rejected delivery leaves the commitment open for a replacement delivery.

Accepted units create a linked receipt and receipt lines, add ledger stock, reduce approved incoming and allocate stock to the oldest outstanding approved requests in one SQLite write transaction. Replenishment status and revision update with the same posting. The operation key, parent revision, item revision and write lock prevent replay, stale forms and competing deliveries from double-counting. A general receipt for an item with open approved replenishment incoming is blocked so staff use the linked delivery action.

A correction of an accepted linked receipt requires an explicit choice: return the corrected units to approved incoming, or cancel that remainder. The correction reduces stock and net received, updates the commitment and replenishment status, and saves immutable correction-link and audit evidence in one transaction. Existing reservation protection still prevents reversing stock that has been reserved or issued. Delivery history appears on the replenishment detail page, and the linked receipt points back to its replenishment. Current authorization and disabled-mode rules apply to these views and actions.

## Files and validation

`supplies_deliveries.py` owns delivery validation and transactional posting. `supplies_storage.py` adds delivery and correction-link evidence and receipt references. `supplies_corrections.py` reconciles linked reversals, while `supplies_stock.py` blocks bypass receipts. Routes and templates expose delivery entry, detail and correction choices. The deployment import closure includes the delivery module; version, changelog and service-worker cache are 7.84.

The relevant regression gate passed **755 tests**, no failures or skips, with one existing Starlette/httpx deprecation warning:

```bash
PATH=/workspace/scratch/supplies-venv/bin:$PATH python -m pytest -o addopts= -q tests/test_supplies*.py tests/test_search.py tests/test_deploy_hf.py tests/test_release_checks.py tests/test_work.py tests/test_browser_security.py tests/test_dependency_gates.py tests/test_backups.py tests/test_auth_rbac.py tests/test_phase0_security.py --junitxml=/workspace/scratch/supplies-s53-gate.xml
python scripts/check_release.py junit /workspace/scratch/supplies-s53-gate.xml
```

The six focused S5.3 cases cover two partial receipts with reservation allocation and warning recovery; rejected-only evidence; invalid and over-delivered quantities; generic-receipt bypass; replay; both correction choices; competing delivery postings; and scoped HTTP forms. A real Chromium walkthrough at 390px recorded six delivered with four accepted and two rejected, then accepted the remaining six. Incoming changed `10 → 6 → 0` and on-hand `10 → 14 → 20`. An unrelated requester received 404 for delivery detail. No page errors or page-level horizontal overflow occurred. Screenshots: [delivery form](evidence/supplies-s5-3/delivery-form-mobile.png), [partial delivery](evidence/supplies-s5-3/partial-delivery-mobile.png), [completed delivery](evidence/supplies-s5-3/completed-delivery-mobile.png). Release metadata, dependency lock, vendored PDF.js, Python compilation and `git diff --check` pass.

## Handoff

**Next eligible increment: S6.1 — stock cards, inventory and consumption reports.** Reporting should reconcile ledger stock, accepted delivery receipts, corrections and issued quantities without treating incoming or rejected units as physical stock.

No supplier order was sent, live delivery accepted, feature enabled, balance imported, production role assigned, merge, push or deployment performed. The user's stop-merging instruction remains in effect.
