# S5.1 — Replenishment suggestions and draft creation

Status: **Verified locally**, October 21, 2026. Depends on verified S4.2. Local application version: **7.82**.

## Behavior

Current custodians and auditors can review active catalog items at `/supplies/replenishments`. Each row shows on-hand, reserved, available, total approved outstanding demand, approved incoming, catalog target, calculated suggestion, and existing open replenishments. The calculation is `max(0, target + outstanding - on_hand - incoming)`. Outstanding includes reserved and awaiting-stock quantities once. Incoming is approved quantity less received and cancelled units across approved/ordered/partially received commitments. Drafts never contribute to incoming. A missing target displays **Set target or enter quantity**; zero suggestions explain when incoming already covers the need. The page presents all active items, with attention conditions determined by critical availability, zero physical stock or demand awaiting stock.

Current custodians can prepare and edit a multi-item draft of up to 20 distinct items. The form captures purpose, expected need date, optional procurement reference, requested quantity, intended stock target, optional exact-decimal estimated unit cost and a reason for any target or quantity override. The target must meet the item's critical level. A manual intended target is required when the catalog target is unset; it does not change the catalog. Draft lines save a contemporaneous copy of the suggestion inputs, item/unit identity and explanation. The operation log records the full saved input and returns the original result on an identical retry. Conflicting operation keys or stale revisions fail in one transaction.

Only the preparer can edit a draft. Current custodians can see their own list; auditors have read-only access to all; a replenishment approver can see submitted/decided records when those stages exist in S5.2. Other staff cannot see the list, costs or detail. Disabled mode preserves authorized reads and blocks draft writes. Catalog deactivation now rejects items with open draft, submitted, returned, approved, ordered or partially received replenishment obligations.

This increment adds `supply_replenishment`, draft-line and future commitment tables; only draft rows are written by S5.1 services. No control number is allocated until S5.2 submission. No procurement approval, order, delivery receipt, stock movement or live incoming commitment is posted by a draft.

## Verification

The relevant regression gate passed **741 tests**, with no failures or skips and one existing Starlette/httpx deprecation warning:

```bash
PATH=/workspace/scratch/supplies-venv/bin:$PATH python -m pytest -o addopts= -q tests/test_supplies*.py tests/test_search.py tests/test_deploy_hf.py tests/test_release_checks.py tests/test_work.py tests/test_browser_security.py tests/test_dependency_gates.py tests/test_backups.py tests/test_auth_rbac.py tests/test_phase0_security.py --junitxml=/workspace/scratch/supplies-s51-gate.xml
python scripts/check_release.py junit /workspace/scratch/supplies-s51-gate.xml
```

The S5.1 cases cover the plan's `on hand 6, reserved 6, outstanding 7, target 20 → suggestion 21` checkpoint, exclusion of drafts from incoming, net approved incoming, missing targets, justified overrides, combined items, stale edits, idempotency, deactivation, current grants and disabled mode. An HTTP form test submits all 20 item slots, checks the saved detail and verifies private draft access. Release metadata 7.82, dependency lock, vendored PDF.js and Python compilation pass.

A real Chromium walkthrough used a disposable synthetic database at localhost: it displayed stock suggestions on a 390px viewport, prefilled the chosen item's target and quantity, saved a two-item draft, confirmed unchanged incoming and suggestion, and verified 403/404 for an unrelated requester. There were no page errors or page-level horizontal overflow. Screenshots: [mobile suggestions](evidence/supplies-s5-1/suggestions-mobile.png) and [mobile draft](evidence/supplies-s5-1/draft-mobile.png).

## Handoff

**Next eligible increment: S5.2 — replenishment approval and procurement tracking.** Add numbered immutable submissions, distinct replenishment-approver decisions, current-overlap recalculation, approved incoming commitments, order/reference tracking and reasoned cancellation. Reuse the S5.1 commitment shape, and keep receipt acceptance for S5.3. The saved suggestion is historical context; approval must recalculate against current stock and other incoming commitments.

No live feature enablement, balance import, role assignment, merge, push or deployment was performed. The user's stop-merging instruction remains in effect.
