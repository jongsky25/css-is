# S2.2 — Approval decisions and initial reservation

Date: October 21, 2026 (Asia/Manila). Status: **Verified locally**. Prerequisite: [S2.1](SUPPLIES_MANAGEMENT_S2_1.md). Parent: [implementation plan](SUPPLIES_MANAGEMENT_PLAN.md).

## Delivered

The **Approval inbox** lists pending requests within the signed-in approver's current unit scope, excluding their own requests. Approvers can approve explicit line quantities, return a request for correction or reject it. Each reduction, including approval of zero, requires a line reason; returning/rejecting requires a decision reason. Approved quantities cannot exceed requested quantities, and every submitted line must appear exactly once. All-zero approved selections are retained as decisions with no stock demand and display **No approved quantity**.

Every decision checks the active account, current grant scope, request concurrency token and exact submitted revision inside one transaction. Self-approval, out-of-scope or revoked grants, private drafts, stale submissions and already-decided versions are rejected. Each submitted revision permits one immutable decision. Multiple eligible approvers see the same pending version, and only one can commit a decision.

Approval creates reservations against physical on-hand without posting any stock movement. The shared allocator processes outstanding approved lines by immutable approval timestamp, request ID and stable line ID. It fills older demand before newer demand and records changed reservations in append-only request events. A request for 6 followed by one for 7 against stock of 10 reserves **6 and 4**, leaving **3 awaiting stock** and **0 available**. Request details show requested, approved, reserved and awaiting-stock quantities separately. Item detail shows physical on-hand, reserved and available stock. Phone views include a readable per-item quantity summary alongside the scrollable comparison table.

Returned requests can be edited, resubmitted or withdrawn by their owner. Resubmission keeps the original control number and creates another immutable submitted revision. Removed items are retired from the editable projection rather than deleted, preserving stable line IDs and historical references. Until resubmission, non-owner readers see the previous submitted purpose, unit and items, not private corrections. Old submissions, reduction reasons and decisions remain available in the history panel.

Submitted/decided records are readable by current scoped approvers, custodians and auditors according to the contract; private never-submitted drafts remain owner-only. These reading grants do not confer editing, withdrawal or decision authority. Revoking a grant removes its reads and inbox access immediately, including permission to replay a previously successful decision. Independent ownership or another business grant still applies.

## Implementation

- Added `supplies_approvals.py`: scoped inbox, decision authorization, line validation, immutable decision posting and atomic initial reservation.
- Added `supplies_allocations.py`: transaction-neutral `allocate_outstanding` plus availability calculation. It reuses immutable physical movements, calculates demand using approved less issued/cancelled quantities, serializes through the caller's write transaction and appends allocation events under the same operation. Unchanged reruns do not rewrite reservations or append events.
- Added `supply_request_decision`, `supply_request_decision_line` and `supply_reservation`, with unique decision-per-revision constraints and immutable decision triggers. Reservations contain request/line/item identifiers, approval time, reserved quantity, effective-issued/cancelled projection fields and version.
- Added a backward-compatible `active` column to `supply_request_draft_line`. Existing S2.1 rows default active; retired lines remain referenced by submitted history and can be reactivated by later corrections.
- Extended the request service for returned edits/resubmission, snapshot-based scope, role-sensitive reads and immutable revision/decision history. Non-owner history omits draft-save events that could expose private correction values.
- Added GET `/supplies/approvals` and POST `/supplies/requests/{id}/decide`; retained the existing owner-only save/submit/withdraw endpoints. Forms check CSRF/Origin and preserve invalid/stale submitted values and concurrency tokens safely. Technical administrator role alone grants no business visibility or decision rights.
- Extended request/detail/item templates and navigation; added a narrow-screen quantity summary. Catalog units are additionally fixed while approved demand remains outstanding, including demand for items with no stock history.
- Version is **7.71**. No dependencies, external services, notification channels, issuance or stock correction endpoints were added.

## Verification

The final relevant regression run passed **504 cases**, including **30 S2.2 cases** and the previous 474 relevant cases:

```bash
/workspace/scratch/supplies-venv/bin/python -m pytest tests/test_supplies_approvals.py tests/test_supplies_requests.py tests/test_supplies_import_review.py tests/test_supplies_import.py tests/test_supplies.py tests/test_supplies_stock.py tests/test_work.py tests/test_browser_security.py tests/test_dependency_gates.py tests/test_backups.py tests/test_auth_rbac.py tests/test_phase0_security.py -o addopts= -q
```

Coverage includes:

- Reduced approvals and exact requested/approved/reserved/awaiting-stock totals; identical decision replay and unchanged physical ledger.
- Self-approval, technical administrator/custodian role bypass, scoped/private-draft reads, out-of-scope ancestry, revoked grants and successful-operation replay after revocation.
- Missing/duplicate/foreign lines, overapproval, missing reduction reasons, negative/fractional/boolean quantities and atomic validation failures.
- Return/reject reasons, no reservation on return/reject, returned withdrawal and rejected terminal behavior.
- Returned corrections, removed-line history integrity, stable line IDs, original control numbers and immutable prior revisions/decisions.
- Private returned purpose/unit corrections remaining invisible to prior scoped readers until resubmission; changing submission unit removes the prior scope's reads/inbox entry.
- Stale record/submission revisions, changed item units and a valid return path for correction.
- Audit and allocator failures rolling back decision, request state, operation and reservations together.
- Two genuinely simultaneous approvers using separate SQLite connections: exactly one commits. Two simultaneous competing requests never reserve more than physical stock.
- Zero approvals, no-stock demand, safe allocator reruns and older awaiting demand receiving priority when a subsequent approval runs allocation after a receipt.
- Disabled writes/readable history, custodian/auditor read-only access, full HTTP decision forms, owner control separation, CSRF and safe validation rendering.
- Unit changes blocked for approved outstanding demand without stock history; additive upgrade from preexisting S2.1 lines, repeated installation and foreign-key integrity.

Dependency-lock input checks, compilation and `git diff --check` passed. The existing Starlette/httpx TestClient deprecation remains the only warning. The complete repository runner remains scheduled for S6.2.

### Browser → decision → reservation → database → response

Installed Chromium through Playwright exercised a disposable localhost Uvicorn application/database and registered synthetic sessions:

1. The scoped approver opened the inbox, returned request A and supplied a correction reason.
2. The owner corrected its purpose, saved and resubmitted it as revision 2 while retaining `SUP-2026-00001`.
3. The approver reduced requested 8 to approved 6 with a line reason. Replaying the original decision POST created no duplicate decision or reservation.
4. Approval of request B for 7 reserved the remaining 4 and left 3 awaiting stock. Physical stock remained 10; reservations totaled 10 and availability was zero.
5. The owner saw reduction/history evidence without decision controls. The custodian's item page showed physical/reserved/available measures. Revocation removed the approver's request access (404) and inbox access (403).
6. Submitted revisions and decisions remained visible in history; no stock movement changed. Foreign-key checks passed and no browser page errors occurred. Decision and shortage views fit 390px, with quantity tables scrolling inside labeled regions and an additional phone summary. The mobile shortage screenshot was visually inspected.

Synthetic screenshots:

- [Mobile decision](evidence/supplies-s2-2/decision-mobile.png)
- [Mobile shortage](evidence/supplies-s2-2/shortage-mobile.png)
- [Desktop shortage](evidence/supplies-s2-2/shortage-desktop.png)
- [Submitted revision history](evidence/supplies-s2-2/revision-history-desktop.png)

Temporary walkthrough helper: `/workspace/scratch/verify_supplies_approvals_browser.py`. No live business roles, requests, approvals, inventory adoption or deployment were performed.

## Handoff and recovery

**Next increment: S2.3 — Backorders and cancellation of remaining demand.** Wire the same allocator into receipts and reservation releases, add awaiting-stock queues and reasoned cancellation of the full remaining quantity per selected line. Preserve approval decisions and physical on-hand during cancellation. Recompute fulfillment quantities/precedence as cancellation becomes available.

S2.2 invokes allocation during approval. Receipts/openings currently update physical stock without automatically refilling existing awaiting demand; automatic refill on receipt/release belongs to S2.3. A later approval already reruns this same allocator across older demand, and its priority is tested. Do not implement a second allocation calculation.

Reservation rows have `effective_issued_quantity` and `cancelled_quantity` initialized to zero for the later issuance/cancellation services. Update these only with their corresponding immutable evidence and allocator in one outer transaction. Use the reservation `version` and current transactional quantities for future issue/cancel validation; allocation can change without changing the request header revision. Do not mutate immutable approved quantities or rewrite prior submitted snapshots.

Continue resolving scope against immutable submitted units, not unsent directory corrections. Preserve `supply_request_draft_line` IDs referenced by any submitted revision. Catalog deactivation remains conservative for approved requests until S2.3/S3.1 can prove no remaining obligation; S5.1 must add open replenishment guards.

Recovery: disable Supplies writes while preserving authorized record/history reads. Do not delete decisions, reset control numbers or manually edit reservation projections. These approvals have changed no physical stock; application recovery should retain decision evidence and reconcile reservations through the shared allocator. Operational acceptance and rollout remain separate from local verification.
