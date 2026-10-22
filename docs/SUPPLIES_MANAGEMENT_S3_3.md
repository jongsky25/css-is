# S3.3 — Returns, stocktake differences and reversals

Status: **Verified locally**, October 21, 2026. Depends on verified S3.2. Local application version: **7.79**.

## Implemented behavior

- Custodians record returns against a specific original release line. Usable returns add stock and allocate oldest outstanding demand. Damaged/unusable returns retain quantity, condition, actor, date and reason without increasing usable stock. Neither reduces effective issuance or creates replacement demand.
- Partial mistaken-issue reversals link the original movement, reduce effective issuance, and require an explicit `reopen_demand=yes/no` choice. Reopening adds only the corrected quantity to outstanding demand. Choosing no adds that quantity to cancelled remainder. Existing valid cancellations and Approved decisions remain intact.
- The cumulative quantity of all returns (including unusable returns) and issue reversals cannot exceed the original line's issued quantity. Receipt reversals are likewise limited to the original accepted quantity less prior reversals.
- A physical count records a signed difference from current stock. Loss previews identify affected requests and quantities; posting releases reservations from newest to oldest until they fit, retaining the oldest demand and leaving losses awaiting stock. Positive adjustments allocate oldest demand normally. An unchanged count needs no adjustment; an unrecorded item must first use reviewed opening stock.
- Receipt reversals require enough current free stock. They never silently release reservations; blocked forms explain that issued stock or reservations must be reconciled first. Original receipt lines retain accepted quantities beside reversed and net-accepted totals.
- Every mutation requires a preview and explicit confirmation. The preview fingerprint includes the normalized action, current item/source evidence, latest stock posting and reservation/request versions. Changed stock, allocation, source eligibility or catalog context rejects a stale preview. An identical authorized retry with its original operation key returns the committed result; a different payload conflicts.
- Stock movement, correction evidence, request projections, reservation reconciliation, operation result and audit commit in one `BEGIN IMMEDIATE` transaction. Failures roll everything back. Current account, custodian grant and enabled flag are rechecked before any replay result is returned.
- Original releases, movements, recipient/paper acknowledgment evidence and original print fields remain immutable. Detail/print views show reversal and return summaries separately. Request history uses plain-language correction events. Paginated history and stable correction links inherit current source access; unrelated affected requests are removed from recipient-visible evidence.

## Files and contracts

The main implementation is `supplies_corrections.py`, the additive installer in `supplies_storage.py`, and the review/history endpoints in `supplies_routes.py`. Narrow hooks extend `supplies_stock.py`, `supplies_issues.py`, `supplies_requests.py` and `supplies_print.py` for linked movements, net totals and history. Templates provide review forms, confirmation, correction history, stock-card references and correction summaries. The deployment manifest includes the new runtime module. Version, changelog and service-worker cache agree at 7.79.

Public service entry points: `preview`, `post_return`, `post_stocktake`, `reverse_issue`, `reverse_receipt`, `history`, `get_correction`. Mutations take the original parent ID, normalized form fields, reviewed fingerprint, confirmation and operation key. One source line is corrected per posting; repeat the review for additional lines.

GET forms and POST actions follow the S0.1 contract:

- `/supplies/issues/{id}/returns`
- `/supplies/items/{id}/stocktake`
- `/supplies/issues/{id}/reverse`
- `/supplies/receipts/{id}/reverse`

Each has a session-CSRF-protected POST `/preview` action that performs reads only. Final POST commits the reviewed correction. GET `/supplies/{items|issues|receipts}/{id}/corrections` paginates history; GET `/supplies/corrections/{id}` provides a stable evidence reference. All paths retain the existing authenticated middleware and origin checks; no public/CSRF exception was added.

Schema impact: new append-only `supply_correction` with original issue/receipt/movement links, optional correction movement, signed quantity, count/condition/demand choice, posting/effective dates, actor snapshot, reason, before/after stock and immutable impact evidence. Source indexes support cumulative limits/history. Database triggers enforce source eligibility, movement matching, immutability and links to original issues/receipts rather than reversals. Existing movement and issue rows are not rewritten. Repeated installation preserves records and foreign-key integrity.

## Verification

Before S3.3 changes, the integrated S3.2 baseline passed **4,959 tests in normal order and 4,959 in shuffled order**. These are baseline results, not a full-suite claim for the subsequent S3.3 changes.

S3.3 verification passed **685 distinct relevant tests**, with no skips:

```bash
PATH=/workspace/scratch/supplies-venv/bin:$PATH python -m pytest -o addopts= -q tests/test_supplies*.py tests/test_search.py tests/test_deploy_hf.py tests/test_release_checks.py --junitxml=/workspace/scratch/supplies-s33-gate.xml
# 343 passed, including 37 new correction tests.

PATH=/workspace/scratch/supplies-venv/bin:$PATH python -m pytest -o addopts= -q tests/test_work.py tests/test_browser_security.py tests/test_dependency_gates.py tests/test_backups.py tests/test_auth_rbac.py tests/test_phase0_security.py --junitxml=/workspace/scratch/supplies-s33-shared.xml
# 342 passed.

PATH=/workspace/scratch/supplies-venv/bin:$PATH python -m pytest -o addopts= -q tests/test_supplies_corrections.py tests/test_supplies_requests.py tests/test_supplies_acknowledgments.py --junitxml=/workspace/scratch/supplies-s33-final-touched.xml
# 95 passed after the final request-history wording/evidence hooks.
```

Coverage includes exact quantity arithmetic; true returns versus mistaken reversal; existing cancellation preservation; unavailable or excess source quantities; invalid/future/backdated-before-source evidence; explicit demand choices; zero physical count; newest-first loss release; oldest-first refill; consumed/reserved receipt rejection; stale reviews; unchanged/changed replay payloads; disabled/revoked authority; concurrent same-key and competing-key returns; concurrent stocktake versus issuance; audit/allocator rollback; immutable original/acknowledgment evidence; retained item snapshots; repeated installation; scoped and paginated history; stable older evidence links; CSRF/origin checks; escaped input; and read-only preview behavior.

Release metadata, dependency lock inputs, 188 vendored PDF.js files, runtime import closure, compilation and `git diff --check` pass. JUnit gates confirm no failures/skips. The existing Starlette/httpx TestClient deprecation warning remains. No dependency versions changed. Installed test and audit-tool inventories were also audited during the preceding integration checks: 68 and 32 packages respectively, complete coverage and no known advisories. The production Docker audit was blocked by this environment's certificate trust; hosted Actions stopped before any job steps. Those are not reported as passed deployment gates. No merge or deployment was attempted after the user stopped merging.

### Real browser and A4 evidence

`/workspace/scratch/verify_supplies_corrections_browser.py` uses real Chromium, a temporary localhost Uvicorn server and disposable synthetic data. It verifies loss preview/deallocation, usable and damaged returns, an explicitly cancelled-demand issue reversal, receipt reversal, blocked reserved-stock reversal, exact POST retries, source-scoped history, corrected release printing, 390px layouts and no browser page errors. `pdfinfo` verifies A4 dimensions and `pdftotext` verifies original and corrected quantities. The mobile review and PDF were visually inspected.

Numerical walkthrough: opening 10, release 4 and 2, count remaining stock down from 4 to 2, accept 2 usable and document 1 unusable return, reverse 1 erroneous issue without reopening demand, receive 3, reverse 2 from that receipt, then block its final 1 after reservations consume available stock. Final on hand and reservations are **6 / 6**; original request effective issued/cancelled is **5 / 1**. The first release still prints original quantity **4**, beside reversed **1**, effective issued **3**, usable returned **2** and unusable returned **1**.

Synthetic evidence:

- [Stocktake impact review](evidence/supplies-s3-3/stocktake-impact-desktop.png)
- [Usable return on phone](evidence/supplies-s3-3/usable-return-preview-mobile.png)
- [Explicit issue-reversal choice on phone](evidence/supplies-s3-3/issue-reversal-preview-mobile.png)
- [Blocked receipt reversal on phone](evidence/supplies-s3-3/blocked-receipt-reversal-mobile.png)
- [Recipient correction history](evidence/supplies-s3-3/recipient-correction-history-mobile.png)
- [Corrected release A4 PDF](evidence/supplies-s3-3/corrected-release-A4.pdf)

## Handoff and recovery

**Next eligible increment: S4.1 — Stock warning rules and persistent notices.** Read the existing available/outstanding quantities after corrections; do not infer low-stock state from physical on-hand alone. Warning notifications and replenishment remain later work.

Scope limits: corrections operate on one original line at a time; no reversal of a reversal, no automatic replacement request and no replenishment-linked receipt yet. Opening/import errors use a justified physical-count adjustment rather than rewriting the original opening. S5's future replenishment receipt service must also reconcile incoming and received/cancelled quantities atomically when reversal is introduced there.

Recovery: disable Supplies business changes while retaining authorized history/print access. Retry the same confirmed form and operation key after a lost response. Original movements and correction evidence must never be edited/deleted; address another error with a newly justified stocktake, receipt or issue through the appropriate service. Keep the additive tables when rolling back application code. Do not restore the whole shared database solely to undo a Supplies correction.

The user stopped merging and requested S3.3 work. PR #386 remains unmerged; these S3.3 changes are local. No live roles, opening balances, feature flag or deployment were changed.
