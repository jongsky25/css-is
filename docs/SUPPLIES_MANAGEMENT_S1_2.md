# S1.2 — Stock ledger, opening entry, and manual receipt

Date: October 21, 2026 (Asia/Manila). Status: **Verified locally**. Prerequisite: [S1.1](SUPPLIES_MANAGEMENT_S1_1.md). Parent: [implementation plan](SUPPLIES_MANAGEMENT_PLAN.md).

## Implemented behavior

- Custodians can record a reviewed opening count from an active item's detail page. Count date, count basis, quantity, actor, item snapshot and posting timestamp are retained. Zero is a valid confirmed opening. A ledger with any prior posting rejects an opening, including after a receipt-only start; an opening also locks the unit against subsequent catalog edits.
- Custodians can record accepted deliveries through **Record receipt**. Delivery details include supplier, effective receipt date, DR/APR references, procurement mode and optional note. The UI supports five item lines; the service accepts at most 20 lines. Each line stores accepted quantity, optional exact decimal unit cost, optional expiry, and the item's code/description/unit at posting.
- A posted receipt has an internal reference such as `RCV-000001`, a detail page, and a paginated receipt list. This uses the immutable receipt's internal ID, not the later formal SUP/REP/ISS numbering sequences.
- Stock cards show immutable posted movements and ledger-derived running balances. Posting ID order is authoritative even for a later-entered transaction with an earlier effective date. Running balances continue correctly across pages. The item and catalog show recorded stock on hand; an untouched item says **Not recorded**, rather than claiming a physical zero count.
- Staff can read quantities for active items. Only current custodians and auditors can read stock cards, receipts, supplier costs and delivery references. Auditors remain read only. Permission/enable checks occur before an idempotent result is returned, so retries do not bypass revocation or disabled writes.
- Identical operation-key retries return the original posting; mismatched payloads conflict. Independent SQLite connections serialize competing openings and duplicate receipt retries. Receipt header, lines, movements, operation result, module event and application audit commit together. Validation, audit failure or aggregate overflow rolls back the entire posting.

No uploaded balance or physical count was adopted. Development and verification used synthetic databases only. Supplies remains default-off; no production deployment or business-role assignment was performed.

## Files and schema

Added `supplies_stock.py` and `tests/test_supplies_stock.py`. Extended the existing schema/permissions/catalog/routes, stock detail/catalog/base views, styles and prior tests. Added receipt form/detail/list templates. `version.py` records **7.67** and its stock-opening/receipt release note. No dependencies, external services, public endpoints or CSRF exemptions were added.

Three additive tables:

| Table | Purpose/integrity |
|---|---|
| `supply_receipt` | Immutable delivery header, effective/posting dates, receiving actor snapshot and unique operation link. |
| `supply_receipt_line` | Immutable accepted quantities, exact decimal cost text, optional expiry and item snapshots. |
| `supply_stock_movement` | Immutable signed integer movements with item/actor snapshots, source references and operation link; item/posting index; one opening per item. |

Database triggers reject movement/header/line edits and deletions, openings on populated ledgers, and receipt movements that do not match their accepted source line. Foreign keys link receipt lines, movements, actors and operations. Operation foreign keys are deferred until commit so the existing result-recording primitive can finalize the whole posting atomically. Repeat schema installation preserves all posted rows.

The ledger schema names future movement kinds for continuity, but only opening and accepted receipt posting are exposed in this increment. Reversal, issue, return, adjustment and replenishment actions remain deferred to their planned increments.

## Validation and display decisions

- Opening quantities are whole numbers from 0 through 2,147,483,647; receipt quantities are positive whole numbers in the same range. Aggregate on-hand arithmetic supports signed SQLite 64-bit integers and rejects overflow before committing.
- Receipt/count dates are required valid ISO dates and cannot be future dates. Earlier effective dates are allowed and do not reorder prior postings. Posting dates/times come from `tzutil`.
- Optional costs are canonical nonnegative decimal strings with four decimal places, up to `999999999.9999`. Unknown cost remains SQL null and displays **Not recorded**; a known zero displays `0.0000`. No float valuation or inventory-value total is introduced.
- Supplier is required for a delivery; references/procurement mode/note are optional. Expiry is optional valid date metadata; this increment does not enforce batch/expiry-controlled issuance.
- Each receipt line includes the catalog revision shown when selecting its unit. A stale catalog revision or inactive selected item aborts the whole receipt. Same-item lines with different costs/expiry metadata are supported and accumulate correctly.
- Multi-query stock/receipt reads share a read snapshot. They do not commit an enclosing caller transaction. Stock movements remain the authoritative balance source; no user-editable stored balance or competing stock cache is added.

## Verification

Environment: isolated CPython 3.11.17 with the existing hash-verified test lock.

```bash
/workspace/scratch/supplies-venv/bin/python -m pytest tests/test_supplies.py tests/test_supplies_stock.py tests/test_work.py tests/test_browser_security.py tests/test_dependency_gates.py tests/test_backups.py tests/test_auth_rbac.py tests/test_phase0_security.py
```

**397 passed, 1 warning in 36.08s.** This includes 55 Supplies cases and 342 existing regression cases. The warning is the previously observed Starlette/httpx TestClient deprecation.

Covered cases include opening 10 + receipt 5 = 15; exact retry/mismatch behavior; rejection of another opening; zero opening and real unit-lock integration; receipt before opening; repeated installation; multi-line accumulation; retained snapshots after catalog rename; backdated effective dates; quantities above 32-bit aggregate totals; exact known-zero versus unknown costs; invalid quantities/costs/dates; stale catalog/invalid second-line whole-receipt rollback; audit failure; aggregate overflow; current/revoked permissions; default/disabled access; immutability/FKs; independent-connection contention; running totals over multiple pages; and HTTP CSRF, origin, validation and cost-privacy boundaries.

After explicit date-label corrections and route import cleanup, reran the two affected HTTP flows:

```bash
/workspace/scratch/supplies-venv/bin/python -m pytest tests/test_supplies.py::test_http_catalog_configuration_and_permission_boundaries tests/test_supplies_stock.py::test_opening_receipt_http_and_cost_privacy
```

**2 passed, 1 existing warning in 4.18s.** Additional checks: `scripts/lock_dependencies.py --check` reports current lock inputs; `compileall` on the Supplies modules succeeds; `git diff --check` is clean. The full repository runner remains scheduled for S6.2.

### Real browser flow

Used installed Chromium through Playwright against a temporary localhost Uvicorn process with lifespan jobs disabled, a disposable database and registered synthetic sessions. The browser performed the actual form submissions and redirects:

1. Custodian entered a reviewed opening of 10 reams; the item showed 10 and removed the opening form.
2. Custodian posted a five-ream accepted delivery with supplier, DR/APR, procurement mode, unit cost `123.4567` and expiry metadata.
3. Receipt detail retained those fields and linked to the stock card; the card showed balances 10 then 15.
4. At 390px viewport width, the stock card and receipt form fit the document; the ledger uses a focusable horizontal scroll region.
5. A separate ordinary-staff session saw 15 reams without supplier/cost details; direct receipt access returned 403.
6. Database checks found exactly two stock movements, one receipt, one accepted line, balances `[10, 15]`, and no foreign-key violations. No browser page errors occurred.

Explicit date labels keep the shared date-picker enhancement from changing their accessible label text. Table headings retain complete words on desktop, while narrow views scroll within the table region.

Screenshots (synthetic records only):

- [Desktop stock card](evidence/supplies-s1-2/stock-card-desktop.png)
- [Phone stock card](evidence/supplies-s1-2/stock-card-mobile.png)
- [Receipt detail](evidence/supplies-s1-2/receipt-desktop.png)

The temporary walkthrough helper is `/workspace/scratch/verify_supplies_stock_browser.py`; HTTP/service tests and the screenshots retain reviewable evidence independently of that temporary helper.

## Limits, recovery, and next increment

No Excel import, request/approval/reservation, issuance, return/correction, warning, replenishment or reporting workflow was introduced. This is not production acceptance. Quantity labels say **On hand**; reserved/available quantities are introduced with the request allocator later. The live reconciliation, role assignment and cutover requirements remain open under S6.3.

**Next eligible increment: S1.3 — Spreadsheet preview and reconciliation.** It must remain read-only with respect to inventory: previewing a workbook may create staged preview/reconciliation evidence but must not post openings or receipts. At S1.4, reuse the opening validation/ledger rules through a transaction-neutral helper under one outer import-batch transaction; do not nest the public transaction-owning `post_opening` service or maintain a separate opening-balance field. Preserve source hashes, mappings and exclusions, and never run workbook formulas/macros/links.

At S2.3, receipt posting must invoke the common allocator inside its current transaction, before finalizing the operation/event; do not call a transaction-owning public service from another transaction. At S3.3, corrections must use linked reversing movements and preserve original receipt evidence; the posted-row triggers intentionally forbid overwriting prior accepted quantities. At S5.3, introduce replenishment receipt links/accepted-rejected quantities explicitly and reconcile incoming stock through the same atomic receipt path.

Recovery: disable Supplies writes while retaining authorized reads and immutable postings. Roll back code if necessary while retaining the additive tables. Do not delete movements to undo stock or restore an old shared database after unrelated office work; use the planned correction/recovery process. No real inventory recovery is required for this synthetic execution.

No unresolved technical failure blocks S1.3.
