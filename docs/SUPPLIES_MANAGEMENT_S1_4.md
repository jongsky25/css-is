# S1.4 — Reviewed opening import

Date: October 21, 2026 (Asia/Manila). Status: **Verified locally**. Prerequisite: [S1.3](SUPPLIES_MANAGEMENT_S1_3.md). Parent: [implementation plan](SUPPLIES_MANAGEMENT_PLAN.md).

## Delivered

Custodians can reconcile each staged source row by explicitly including a verified physical count or excluding the row with a reason. Inclusion requires a canonical item mapping, quantity and reviewed thresholds. New items require a code, description and canonical unit; mapping to an existing item preserves its identity and unit. Unit differences are resolved through a documented count in the canonical unit, never through automatic conversion or acceptance of formula caches.

Every source row must have a decision, and at least one must be included. Finalization requires a nonfuture physical-count/cutover date, a basis and explicit confirmation of the counts and units. The final report shows all included mappings, quantities, units, thresholds and exclusion reasons beside their source sheet/row locations. It retains the workbook SHA-256 and a hash of the finalized selection. Physical quantities start blank; no workbook value is automatically accepted.

Applying a finalized selection creates new item masters, updates reviewed thresholds for existing mapped items, and posts opening balances in one transaction. It imports no historical transactions. Any stale batch/item revision, inactive mapping, duplicate item/code, populated ledger, previously applied source hash or posting/audit failure rejects the entire batch. Zero physical counts are valid openings and still populate the ledger.

Changing any row after finalization returns the batch to preview and requires another final review. Applied batches, decisions, final selections and source evidence remain immutable. Retrying the identical successful operation returns its saved result; a fresh apply against an applied batch fails without creating stock. Current account/grants and the Supplies flag are checked even for retries.

## Implementation

- Added `supplies_import_review.py` for row decisions, finalization, reports and atomic application.
- Added the append-only `supply_import_review` table with reviewer, timestamp, revision and operation key. Each save/finalize/apply retains its own JSON evidence; source metadata and raw rows remain untouched. A partial unique index prevents two applied batches with the same source hash.
- Factored a transaction-neutral opening helper from `supplies_stock.py`. Both standalone openings and imports retain the empty-ledger guard. Batch application owns one `BEGIN IMMEDIATE` transaction; it never nests public posting transactions.
- Opening movements retain the batch and staging-row identifiers. The apply report maps source rows to created item/movement IDs. Item timeline events reference the same audited operation and source/selection hashes.
- Added POST `/supplies/import/{id}/rows/{row_id}`, `/finalize` and `/apply`, with current custodian authorization, feature-flag checks, session-bound CSRF and existing origin protection. Review pages use a consistent read snapshot. Individual row forms preserve pagination and avoid large multipart field counts.
- Extended the preview UI with reconciliation forms, dated final review, exclusion report, atomic apply and applied status. Auditors retain read-only access. Version is **7.69**. No dependencies or external services were added.

## Verification

The existing relevant suite plus the first 12 S1.4 cases passed **438 cases**:

```bash
/workspace/scratch/supplies-venv/bin/python -m pytest tests/test_supplies_import_review.py tests/test_supplies_import.py tests/test_supplies.py tests/test_supplies_stock.py tests/test_work.py tests/test_browser_security.py tests/test_dependency_gates.py tests/test_backups.py tests/test_auth_rbac.py tests/test_phase0_security.py -q
```

A final focused run passed all **16 S1.4 cases**, including four additional checks for mapped-item thresholds/revoked retry authority, audit-failure rollback, competing connections and repeated additive installation. In total, **442 distinct relevant cases passed** across these runs. The previously recorded Starlette/httpx TestClient deprecation remains the only warning. The complete repository runner remains scheduled for S6.2.

Coverage includes unresolved and excluded-only selections; explicit confirmation and future-date rejection; missing/noninteger quantities and thresholds; source ownership; duplicate targets; exact selection counts and item quantities; canonical units and thresholds; excluded-row reasons; preserved raw evidence and lineage; zero openings; stale review revisions; editing a finalized review; source/batch replay; changed item revisions, inactive mappings, code collisions and populated ledgers; mid-batch and audit failures with no partial item/threshold/movement changes; current business authority/disabled writes; selection-hash mismatch; HTTP CSRF/read permissions and applied controls; immutable review/applied records; and installation/foreign-key integrity.

Dependency-lock input checks, module compilation and `git diff --check` passed. No lockfile changed.

### Browser → review → database → response

Installed Chromium through Playwright exercised a temporary localhost Uvicorn server, disposable SQLite database, registered synthetic sessions and a synthetic workbook:

1. A custodian explicitly mapped a Ream-versus-Pack discrepancy to a new item using Ream, entered a verified count of 13, critical level 3 and target 20, and documented the reconciliation.
2. The custodian finalized all decisions with a physical-count/cutover date and confirmation, then reviewed the accepted selection before applying it.
3. Applying persisted exactly one opening of **13 Ream** and an applied batch. Replaying the original apply POST created no additional movement.
4. An auditor could read the applied report with no mutation controls. Foreign-key checks passed and no browser page errors occurred.
5. Reconciliation forms and the final report fit a 390px viewport; tables scroll within their labeled regions. The final mobile screenshot was visually inspected.

Synthetic screenshots:

- [Mobile reconciliation form](evidence/supplies-s1-4/reconcile-mobile.png)
- [Mobile final review](evidence/supplies-s1-4/final-review-mobile.png)
- [Desktop final review](evidence/supplies-s1-4/final-review-desktop.png)
- [Applied result](evidence/supplies-s1-4/applied-desktop.png)

Temporary browser helper: `/workspace/scratch/verify_supplies_review_browser.py`. No real uploaded workbook balances were applied, and no live deployment or business-role configuration was performed.

## Handoff and recovery

**Next increment: S2.1 — Draft, submit and track supply requests.** Implement request drafts, requester/unit authorization, submission/control numbering and tracking without changing stock. Add catalog deactivation checks for open request obligations before enabling that workflow, as required by the plan.

P1 inventory implementation is verified locally. Operational adoption still requires the custodian's actual dated physical count, canonical-unit reconciliation, threshold decisions and cutover basis. Those are business inputs, not inferred from spreadsheet caches.

Disable Supplies changes to stop new reviews/applications while preserving authorized reads. A code rollback may leave additive review tables and evidence intact. Applied openings must not be deleted or reapplied: retain their lineage and use the planned audited correction/reversal workflow when available. S1.4 introduces no correction UI and makes no claim that a physical count or cutover was accepted for the supplied workbook.
