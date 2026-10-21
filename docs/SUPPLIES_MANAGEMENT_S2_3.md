# S2.3 — Backorders and cancellation of remaining demand

Date: October 21, 2026 (Asia/Manila). Status: **Verified locally**. Prerequisite: [S2.2](SUPPLIES_MANAGEMENT_S2_2.md). Parent: [implementation plan](SUPPLIES_MANAGEMENT_PLAN.md).

## Delivered

Receiving stock now refills existing approved demand immediately in the same transaction, using the shared allocator introduced in S2.2. Normal receipts, standalone opening counts and reviewed imported openings all allocate by immutable approval time, request ID and line ID. No second reservation calculation was introduced. Replaying a successful receipt/opening/import cannot add stock or allocate it twice.

**Awaiting stock** lists approved line shortages in allocation order. Owners see their requests; current scoped approvers see requests in their units; custodians and auditors see operational shortages across the stockroom. Technical administrator role alone supplies no business visibility. Private drafts and submitted-but-unapproved demand do not appear. Lists paginate at 25 lines, and revoked grants immediately stop contributing visibility.

Requesters and current custodians can cancel the **full unissued remainder of each selected approved line**, with a required reason. Cancellation does not change the Approved decision, requested/approved snapshots, physical stock movements or issued quantities. It appends immutable cancellation evidence, updates cancelled demand, releases reservations and fills the next eligible requests in one transaction. Manual partial cancellation amounts are not accepted.

Cancellation checks both the request record revision and each selected reservation version. A receipt may update reservations without changing the header revision, so a stale cancellation form must reload before acting on changed allocation. The server computes remaining quantities; it does not trust browser balances. Selected lines must belong to the current approved request, have remaining demand and appear exactly once. An invalid selection aborts the entire action. Exact authorized retries return the committed result without another cancellation.

Approved request details display requested, approved, issued, cancelled, outstanding, reserved and awaiting-stock quantities separately. Fulfillment follows the contract's precedence: terminal fulfilled/closed states, then partial issuance, then any reservation, otherwise awaiting stock. Approval state stays Approved even when fulfillment becomes **Cancelled before issue** or **Closed with remainder cancelled**. Phone views include readable item summaries, and cancellation history retains actor, time, reason and quantities.

Custodians can **Refresh reservations** to safely rerun allocation against current stock and demand. Unchanged reruns do not rewrite projection versions or append duplicate allocation-change events. Catalog deactivation now checks actual remaining approved obligations; completed/cancelled demand no longer blocks it, while other submitted/returned/outstanding requests still do.

## Implementation

- Added `supplies_backorders.py`: scoped shortage queries, full-remainder cancellation and authorized allocation refresh.
- Added immutable `supply_request_cancellation` and `supply_request_cancellation_line` tables. Evidence links the submitted revision and reservation, with cancelled quantity, previous reservation, issued-quantity snapshot, actor/time/reason and operation key.
- Integrated the existing transaction-neutral `allocate_outstanding` into receipt, standalone opening and batch-import posting after recording their operation, before commit. Allocation failure rolls back the stock write, audit and projections together.
- Extended request reads with outstanding quantities, reservation version, cancellation permission/history and quantity-derived fulfillment. Cancellation increments the request concurrency token and affected projection versions; reallocation may also advance other requests' reservation versions.
- Added GET `/supplies/awaiting-stock`, POST `/supplies/requests/{id}/cancel-remainder` and POST `/supplies/allocations/refresh`, retaining feature-flag, current-account/grant, session-bound CSRF and Origin checks. Owners and custodians see cancellation controls; approver/auditor read access does not confer cancellation authority.
- Invalid/stale cancellation submissions retain entered reasons, selected lines and original concurrency tokens. Reload is required to accept newer quantities. Added queue/navigation, expanded detail columns, mobile summaries and cancellation-history/timeline labels.
- Refined item deactivation to retain submitted/returned guards and check outstanding approved quantities, preserving the later replenishment-guard handoff. Version is **7.72**. No dependency or external-service changes.

## Verification

The final relevant regression run passed **534 cases**, including **30 S2.3 cases** and the previous 504 relevant cases:

```bash
/workspace/scratch/supplies-venv/bin/python -m pytest tests/test_supplies_backorders.py tests/test_supplies_approvals.py tests/test_supplies_requests.py tests/test_supplies_import_review.py tests/test_supplies_import.py tests/test_supplies.py tests/test_supplies_stock.py tests/test_work.py tests/test_browser_security.py tests/test_dependency_gates.py tests/test_backups.py tests/test_auth_rbac.py tests/test_phase0_security.py -o addopts= -q
```

Coverage includes:

- Receipt allocation to older demand, exact shortage/availability equations and successful receipt replay.
- Cancellation releasing stock to the next request, preserving immutable approval decisions and identical physical ledger rows, with exact cancellation replay.
- Mixed-item requests, selected-line cancellation, fully unreserved demand and terminal fulfillment.
- Standalone/imported opening stock filling previously approved no-stock demand.
- Empty, duplicate, foreign, stale, partial-amount and reasonless cancellations, with no partial effects.
- Owner/custodian authority; approver/administrator denial; current grant scopes and revocation; disabled mutations with retained reads.
- Unchanged allocation reruns preserving reservation rows/change-event counts and requiring current custodian authority, including retries.
- A synthetic future issued-history scenario: cancelling only the unissued remainder preserves issued totals and all stock movement rows. This test does not add or exercise an issuance endpoint.
- Receipt-allocation, cancellation-allocation and audit failures rolling back stock/evidence/projections/operation records together.
- Remaining-obligation deactivation guards, immutable cancellation evidence, repeated additive installation and foreign keys.
- Two simultaneous cancellations using separate SQLite connections committing once; simultaneous receipt/cancellation preserving all item/line equations or rejecting a stale version.
- Receipt-driven reservation version changes invalidating stale cancellation forms even when the request header did not change.
- Scoped queue pagination and exclusion of draft/unapproved demand; revoked/disabled successful-operation replay.
- HTTP CSRF/Origin checks, safe validation rendering, cancellation controls/history and unauthorized refresh attempts.
- Fulfillment precedence across mixed issued, cancelled and reserved quantities.

One older S2.1 test was updated to create a real approval through S2.2 instead of manually changing the header to Approved without its decision/reservation records.

Dependency-lock input checks, module compilation and `git diff --check` passed. The existing Starlette/httpx TestClient deprecation remains the only warning. The full repository runner remains scheduled for S6.2.

### Browser → receipt → refill → cancellation → database → response

Installed Chromium through Playwright used a temporary localhost Uvicorn application, disposable SQLite database and registered synthetic sessions:

1. Against physical stock of 10, requests A for 8 and B for 7 reserved 8 and 2. The custodian's queue showed B's shortage.
2. A real browser receipt for 2 increased on-hand to 12 and refilled B to reserved 4, awaiting 3. Replaying the receipt POST created no duplicate receipt/movement.
3. The owner selected A's full remaining 8 and entered a reason. Cancellation retained A's Approved status and history, closed its demand, and increased B's reservation to 7.
4. Replaying the cancellation POST created no second cancellation. The shortage queue cleared; final stock was **12 on hand, 7 reserved, 5 available**.
5. Approvers had no cancellation controls, unrelated staff received 404 for the request and saw no private shortage entries, and the custodian safely refreshed allocations.
6. The database contained one receipt, one cancellation, two original approval decisions and two physical movements (opening plus receipt). Foreign-key checks passed, no page errors occurred, and mobile detail/form views fit 390px. The mobile cancellation form was visually inspected.

Synthetic screenshots:

- [Shortage queue](evidence/supplies-s2-3/queue-desktop.png)
- [Mobile receipt refill](evidence/supplies-s2-3/receipt-refill-mobile.png)
- [Mobile cancellation form](evidence/supplies-s2-3/cancel-form-mobile.png)
- [Mobile cancelled remainder](evidence/supplies-s2-3/cancelled-mobile.png)
- [Stock after cancellation](evidence/supplies-s2-3/stock-after-cancellation.png)

Temporary helper: `/workspace/scratch/verify_supplies_backorders_browser.py`. No production stock, requests, roles or deployment were changed.

## Handoff and recovery

**Next increment: S3.1 — Partial and full issuance.** Add the custodian issuance queue/form, authorized recipient, release numbering and immutable issue lines/stock movements. Reduce physical stock and current reservations, increase effective-issued quantities and rerun the same allocator in one outer transaction. Preserve approved/cancelled demand and reject issuance beyond reserved/outstanding quantities.

Use current request and reservation versions for issue/cancellation concurrency. Cancellation changes the request revision; receipt/refill can change a reservation version without changing the request header. Derive outstanding as approved minus effective-issued minus cancelled; awaiting stock is outstanding minus reserved. Never infer issued totals from cancelled or reserved quantities.

Cancellation evidence snapshots issued quantities but does not establish issue evidence itself. S3.1 must link effective-issued projection changes to actual immutable issue records. S3.3 corrections/returns and S5.3 accepted deliveries must reuse the allocator inside their own transaction. Deactivation now releases completed approved obligations correctly; S5.1 must additionally guard open replenishment obligations.

Recovery: disable Supplies writes while retaining authorized history/queue reads. Receipt and cancellation actions are atomic; retry their original operation key after an interrupted response. Use Refresh reservations to safely reconcile projections from current stock/demand when appropriate. Do not delete cancellations, rewrite approval decisions or manually zero reservations. Posted physical receipts remain immutable and require the planned correction workflow if erroneous; cancellation itself never reverses stock or issued history.
