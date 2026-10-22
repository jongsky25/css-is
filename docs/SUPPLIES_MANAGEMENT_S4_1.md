# S4.1 — Stock warning rules and persistent notices

Status: **Verified locally**, October 21, 2026. Depends on verified S3.3. Local application version: **7.80**.

## Implemented behavior

Physical stock and availability are displayed separately in the catalog, item detail and warning list:

| Condition | Physical stock | Availability |
|---|---|---|
| No posted stock yet | Stock not recorded | Stock not recorded |
| On hand = 0, including critical level 0 | Out of stock | Out of stock |
| Positive on hand below critical level | Critical | Low available, or Fully reserved when available = 0 |
| On hand at or above critical level | Normal | Available, Low available, or Fully reserved according to available stock |
| Inactive item | Inactive | Inactive |

Exactly-at-threshold quantities are normal/available; zero critical level suppresses only the positive low-stock band. A positive physical balance with zero availability is Fully reserved. Unrecorded items are excluded from the actionable warning queue until their opening stock is reviewed; inactive items resolve their active warning episodes.

Each stock/reservation change queues an immutable snapshot after allocation, inside the same business transaction. Catalog creation, threshold/context edits and deactivation queue their resulting state too. The central allocator covers approvals, openings/imports, receipts, handovers, reservation cancellation/refresh and S3.3 corrections. Snapshot deduplication suppresses unchanged events; transaction rollback also removes the uncommitted queue entry.

After a successful commit, the transaction wrapper processes up to 100 queued events in posting order. Each event's episode update, recipient notices and processed marker commit atomically in a separate transaction. Delivery failure rolls back only that projection, increments a bounded failure record and leaves the event pending. The already committed stock operation still succeeds. Original operation retries return their existing result and may retry pending projection without another stock movement. GET routes never process notices or mark them read.

An active warning episode starts when availability enters low/fully-reserved/out-of-stock state. Notification version 1 goes to current active custodians. Meaningful worsening means a new peak severity (Low available → Fully reserved → Out of stock), or a further halving of positive availability relative to the last notification baseline. Partial recovery within an episode does not reset that baseline; small fluctuations and ordinary refreshes do not spam. Full recovery resolves the episode and all its notices. A subsequent decline starts a new episode.

Recipient/version uniqueness prevents duplicate notices. Newly granted custodians receive the active episode's current state once; granting auditor/approver rights alone does not subscribe someone. Delivery reloads current active custodian recipients. Every list/detail/read/replay request reloads the account and current custodian grant, and requires the notice's own recipient ID. Revocation or account deactivation removes old-link access immediately. Auditors can view the warning list, but cannot read another custodian's notices.

Warnings use current ledger/reservation quantities even if notice processing is delayed. The warning page shows pending work and offers an explicit reconciliation POST. Reconciliation queues missing/changed snapshots and retries existing events without re-enqueuing unchanged items, so bounded backlog processing makes progress. Notice detail distinguishes its immutable historical snapshot from current stock. Reading a notice and retrying warning processing remain permitted when business stock changes are disabled.

## Files and schema

- `supplies_notify.py`: classification, transaction-neutral snapshot enqueueing, bounded dispatcher, episode projection, current-recipient delivery, authorized warnings/notices, explicit reconciliation and idempotent read marking.
- `supplies_storage.py`: additive queue/episode/projection/notice tables, evidence guards and post-commit dispatch; narrow `record` hooks for catalog changes and custodian grants.
- `supplies_allocations.py`: final-state enqueue after allocation and invariant checks.
- `supplies.py`: catalog reservation aggregates and warning labels.
- `supplies_routes.py`, `templates/supplies/{warnings,notices,notice}.html`, and narrow catalog/item/navigation edits: scoped paginated screens, status text and CSRF-protected actions.
- `deploy_hf.py`: new runtime module included in deployment import closure. Version, changelog and cache use 7.80.

New tables:

- `supply_alert_event`: immutable source snapshot, item/operation link, created/processed timestamps and retry status; unique item/operation key.
- `supply_alert_episode`: one active episode per item, notification version, peak severity, notified availability baseline, source event and lifecycle timestamps.
- `supply_item_alert`: latest processed per-item projection.
- `supply_notice`: recipient-specific immutable warning evidence with read/resolved times; unique episode/version/recipient.

Indexes cover pending event order, item history, active episodes and recipient pagination. Triggers prevent editing/deleting source warning and notice evidence while allowing processing/read/resolution markers. Repeated installation retains data and passes foreign-key checks. No stock movements or reservations are rewritten by notice processing.

Service entry points: `classify`, `status`, `enqueue`, `process_pending`, `reconcile_alerts`, `list_warnings`, `list_notices`, `get_notice`, `mark_read`.

Routes:

- GET `/supplies/warnings`; POST `/supplies/warnings/reconcile`.
- GET `/supplies/notices`, with optional unread-active filter and pagination.
- GET `/supplies/notices/{id}`; POST `/supplies/notices/{id}/read`.

No public-route, origin, CSRF or feature-flag exception for stock business mutations was added. Reconciliation/read marking are explicitly separate notice actions. No external messaging, background service or cron was introduced.

## Verification

**709 tests passed**, no failures/skips, including **24 new S4.1 cases**:

```bash
PATH=/workspace/scratch/supplies-venv/bin:$PATH python -m pytest -o addopts= -q tests/test_supplies*.py tests/test_search.py tests/test_deploy_hf.py tests/test_release_checks.py tests/test_work.py tests/test_browser_security.py tests/test_dependency_gates.py tests/test_backups.py tests/test_auth_rbac.py tests/test_phase0_security.py --junitxml=/workspace/scratch/supplies-s41-gate.xml
# 709 passed, 1 existing Starlette/httpx deprecation warning, 82.89 seconds.
python scripts/check_release.py junit /workspace/scratch/supplies-s41-gate.xml
# 709 tests, no failures or skips.
```

Coverage includes zero threshold/zero stock, equality, unrecorded balances, fully reserved stock, low positive availability, threshold recalculation, severity versions, halving and fluctuation deduplication, full recovery and recurrence, deactivation, current recipients/new custodians, auditor separation, owner-only notice reads, immediate revocation/inactivation denial, disabled-mode read/reconciliation, immutable evidence, migration repeatability, scoped pagination and unread counts, concurrent dispatchers, failed delivery and original stock replay, committed low/recovery/recurrence while delivery is unavailable, queue failure rollback, bounded backlog progress, read-only GETs, session CSRF/origin rejection and idempotent read marking.

Also passed: release metadata, dependency-lock inputs, 188 vendored PDF.js file checks, deployment import closure, compilation and `git diff --check`. No dependency changes were needed. This is the increment's relevant regression gate, not a claim that the complete repository suite was rerun for S4.1. Merge/deployment gates were not invoked.

### Real browser evidence

Temporary helper: `/workspace/scratch/verify_supplies_notify_browser.py`. Real Chromium used a disposable synthetic SQLite database and localhost Uvicorn server with lifespan jobs disabled.

1. Opening 10, two releases totaling 6, and another approved demand of 5 produce **on hand 4 / reserved 4 / available 0**. The screen shows physical Normal and availability Fully reserved; exactly one custodian notice exists.
2. The custodian marks the notice read and retries the exact POST without another change.
3. After setting critical level to zero, an injected notice-delivery failure accompanies a physical count of zero. The stock correction succeeds; the warning list shows Out of stock and one pending warning update. Refresh does not process the pending event.
4. Explicit reconciliation delivers the missing stockout notice without adding stock movements.
5. A receipt of 6 allocates 5, leaving 1 available; at threshold zero this resolves the episode and unread-active count becomes zero. A subsequent count of 1 leaves stock fully reserved and starts a second episode.
6. Granting a second custodian creates one current-episode notice for that person. The revoked original custodian's old notice/warning URLs and ordinary requester's notice URL return 403.
7. Four notices exist in total: two resolved notices from the first episode, one recurrence notice for the original custodian and one current notice for the new custodian. Foreign-key checks pass, 390px layouts fit and no browser page errors occur. Representative desktop and mobile screenshots were visually inspected.

Synthetic screenshots:

- [Fully reserved stock on desktop](evidence/supplies-s4-1/fully-reserved-desktop.png)
- [Committed zero-stock correction with notices pending](evidence/supplies-s4-1/pending-stockout-mobile.png)
- [Stockout notices on phone](evidence/supplies-s4-1/stockout-notices-mobile.png)
- [Recovered unread-active view](evidence/supplies-s4-1/recovered-notices-mobile.png)
- [New custodian's active notice](evidence/supplies-s4-1/new-custodian-current-notice-mobile.png)
- [Historical versus current notice quantities](evidence/supplies-s4-1/current-notice-mobile.png)

## Handoff and recovery

**Next eligible increment: S4.2 — Supplies dashboard and role-specific action queues.** Reuse the current permission predicates and warning classification for counts/lists. Notice projections may lag during a delivery failure; use current stock for operational quantities and expose pending processing explicitly. Preserve independent physical/available states and current custodian ownership checks on any new links or badges.

Recovery: keep the durable queue, snapshots and notices. Use Reconcile warning notices to retry pending processing, repeating for backlogs beyond the 100-event batch. Later Supplies commits also attempt pending work. Do not repeat a receipt, handover or correction to retry a notice. Never discard failed events merely to advance the queue; chronological processing preserves recovery/recurrence evidence. A business change whose queue cannot be saved has not committed and rolls back normally. A business change whose delivery subsequently fails is already committed and retains its original operation result.

Limits: in-app delivery only; no automated purchasing, external alerts, scheduled worker or dashboard aggregation yet. Existing stock created before this increment is classified live on reads and can be backfilled explicitly through reconciliation. This task did not enable live Supplies, import stock, alter live roles, merge, push these increments, or deploy. S3.3 local work is preserved alongside S4.1.
