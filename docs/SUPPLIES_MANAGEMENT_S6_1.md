# S6.1 — Stock cards, inventory and consumption reports

Status: **Verified locally**, October 21, 2026. Depends on verified S5.3. Local application version: **7.85**.

## Behavior

Current custodians and Supplies auditors can open read-only reports for inventory, request fulfillment, issue consumption, outstanding replenishment, and an item's full stock card. Inventory separates on-hand, reserved, available and approved incoming quantities. Fulfillment shows requested, approved, net issued, cancelled, reserved and awaiting quantities. The replenishment report shows the approved, net accepted, cancelled and still incoming portions of open commitments. Reports continue to work while Supplies writes are disabled; staff without a current stock-reader grant cannot open their pages, print views or Excel downloads.

Stock cards show every immutable movement in posting-ID order, with running balance, effective date, receipt or release reference, DR and supplier where applicable, recorded source cost, actor and reason. Corrections appear as separate movements. Issue consumption shows release-level detail and totals grouped by item, recorded unit and issue posting date; later issue reversals change net issued quantities and usable/unusable returns remain visible separately. A posting-date filter is available on stock cards and consumption. It includes only movements, issues and corrections posted by that date, even if their effective dates differ. Inventory, fulfillment and replenishment are explicitly current snapshots because their mutable reservations and commitments do not provide a historical as-of projection.

All five reports have an A4 landscape print/PDF view and an `openpyxl` workbook download. Consumption workbooks add a grouped summary sheet. Text beginning with spreadsheet formula characters is escaped in every exported data cell. Cost columns are labelled as recorded receipt values or draft estimates and are not presented as official accounting valuation. The existing A4 request/release forms remain available.

## Files and validation

`supplies_reports.py` owns scoped, snapshot-consistent report queries and workbook generation. `supplies_routes.py` exposes the read, print and XLSX endpoints. `templates/supplies/report.html` and `report_print.html` show the figures and print view; Supplies navigation and item details link to them. The deployment import closure includes the new module. Version, changelog and service-worker cache are 7.85.

The relevant regression gate passed **759 tests**, no failures or skips, with one existing Starlette/httpx deprecation warning:

```bash
PATH=/workspace/scratch/supplies-venv/bin:$PATH python -m pytest -o addopts= -q tests/test_supplies*.py tests/test_search.py tests/test_deploy_hf.py tests/test_release_checks.py tests/test_work.py tests/test_browser_security.py tests/test_dependency_gates.py tests/test_backups.py tests/test_auth_rbac.py tests/test_phase0_security.py --junitxml=/workspace/scratch/supplies-s61-gate.xml
python scripts/check_release.py junit /workspace/scratch/supplies-s61-gate.xml
```

The four S6.1 cases cover linked delivery and receipt-correction reconciliation, posting-date cutoffs, issue-reversal net consumption, request fulfillment, formula-safe XLSX values, invalid filters, current-grant authorization, and HTML/print/XLSX HTTP routes. All four passed again after the final consumption-summary change. A real Chromium mobile walkthrough on a disposable synthetic database checked inventory, closed replenishment, full stock card, XLSX download, and scoped denial without page errors or horizontal overflow. Its [stock-card screenshot](evidence/supplies-s6-1/stock-card-mobile.png), [inventory screenshot](evidence/supplies-s6-1/inventory-mobile.png), and [A4 PDF](evidence/supplies-s6-1/stock-card-a4.pdf) show the output. The PDF is one readable landscape A4 page with opening and two linked receipts. Release metadata, dependency lock, vendored PDF.js, Python compilation and `git diff --check` pass.

## Handoff

**Next eligible increment: S6.2 — integrated acceptance, concurrency and recovery.** Run the complete request-to-report scenario through browser, routes, services and a disposable database, then rehearse backup/restore and relevant security checks before any staff pilot.

No live feature enabled, balances imported, production role assigned, merge, push or deployment performed. The user's stop-merging instruction remains in effect.
