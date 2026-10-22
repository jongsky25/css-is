# S5.2 — Replenishment approval and procurement tracking

Status: **Verified locally**, October 21, 2026. Depends on verified S5.1. Local application version: **7.83**.

## Behavior

A current custodian submits an owned draft or returned replenishment through the detail page. Submission allocates a `REP-YYYY-NNNNN` number on first submission and appends an immutable numbered revision with item, unit, cost, purpose, procurement reference, expected need date, requested quantity and recalculated stock/demand/incoming inputs. Resubmission retains the control number and earlier revisions/decisions. If another open replenishment exists or requested quantity exceeds the current calculation, submission requires an explanation. Catalog changes that affect submitted item identity require the custodian to edit and save the draft again.

Only a current **replenishment approver** can approve, reduce, return or reject a submitted revision. The preparer cannot decide their own replenishment, even with a second grant. An approved decision addresses every submitted line, cannot exceed requested quantity, and requires line reasons for reductions. Return/reject require a decision reason. Approval recalculates each line against current on-hand, outstanding approved demand and other incoming commitments; approval above the current need or alongside another open replenishment requires a decision explanation. All revision, line, decision, actor and calculation evidence is append-only.

Approval creates one commitment per line. Incoming equals `approved − net received − cancelled` across active approved/ordered/partially received replenishments. Approval never posts physical stock. Custodians can record one order with reference, expected delivery date, responsible current custodian and per-line ordered quantities up to the active approved quantity. Ordering changes the stage but does not create incoming a second time. A smaller ordered quantity does not silently cancel the unplaced approved balance; the approved balance remains incoming until a reasoned cancellation or later accepted delivery.

Custodians can cancel selected unreceived approved quantities with a reason, without changing prior decisions, order evidence or stock movements. Partial cancellation reduces incoming by exactly the cancelled amount; full cancellation closes an entirely unreceived record. The service checks current grants, enabled state, record revision and idempotency key inside a SQLite write transaction. Competing decisions cannot create duplicate incoming.

The replenishment detail page shows current calculation inputs, overlaps, submission/decision history, approved and incoming quantities, order information and cancellation history. Approvers see submitted and decided records under their current grant. During a returned draft edit, they see the last submitted snapshot; private draft changes do not appear until resubmission. Other staff cannot see the replenishment list, costs or detail. Disabled mode preserves authorized reads and blocks mutations.

## Files and validation

`supplies_replenishment_flow.py` owns S5.2 transitions. `supplies_storage.py` adds immutable submission, decision, order and cancellation evidence tables. `supplies_replenishment.py` enriches scoped detail reads and protects returned edits. `supplies_routes.py` and the replenishment views expose the review and action forms. Deployment import closure includes the new module; version, changelog and service-worker cache are 7.83.

The relevant regression gate passed **747 tests**, no failures or skips, with one existing Starlette/httpx deprecation warning:

```bash
PATH=/workspace/scratch/supplies-venv/bin:$PATH python -m pytest -o addopts= -q tests/test_supplies*.py tests/test_search.py tests/test_deploy_hf.py tests/test_release_checks.py tests/test_work.py tests/test_browser_security.py tests/test_dependency_gates.py tests/test_backups.py tests/test_auth_rbac.py tests/test_phase0_security.py --junitxml=/workspace/scratch/supplies-s52-gate.xml
python scripts/check_release.py junit /workspace/scratch/supplies-s52-gate.xml
```

After the final expected-delivery validation and added coverage, **8 focused S5.2 cases passed**. They cover duplicate form replay, returned/edit/resubmitted history, overlap explanations, independent grants and self-approval, reduced approval and rejection, stale or simultaneous decisions, scoped reads and disabled mode, order accounting, partial/full cancellation and HTTP submission/approval. Release metadata, dependency lock, vendored PDF.js checks, compilation and `git diff --check` also pass.

A real Chromium walkthrough on a disposable synthetic database at 390px submitted a draft, had a separate approver approve it, recorded a procurement order, cancelled four of ten unreceived units, and confirmed incoming changed `0 → 10 → 10 → 6` while physical stock stayed unchanged. The unrelated requester received 404 for detail. There were no browser page errors or page-level horizontal overflow. Screenshots: [submitted](evidence/supplies-s5-2/submitted-mobile.png), [approved](evidence/supplies-s5-2/approved-mobile.png), [ordered](evidence/supplies-s5-2/ordered-mobile.png), [partial cancellation](evidence/supplies-s5-2/partial-cancellation-mobile.png).

## Handoff

**Next eligible increment: S5.3 — partial delivery, acceptance and stock receipt.** Accepted quantities must reduce commitment incoming and add ledger stock in the same transaction, with receipt-line links. Rejected quantities add no stock. Reversing a linked receipt must reconcile both stock and incoming/cancelled remainder according to the explicit correction choice. Generic receipts must not bypass a replenishment delivery link.

No supplier order was sent, delivery accepted, live feature enabled, balance imported, role assigned outside synthetic tests, merge, push or deployment performed. The user's stop-merging instruction remains in effect.
