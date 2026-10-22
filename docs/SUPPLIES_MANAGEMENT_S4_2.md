# S4.2 — Supplies dashboard and role-specific action queues

Status: **Verified locally**, October 21, 2026. Depends on verified S4.1. Local application version: **7.81**.

## Implemented behavior

`/supplies` now opens the Supplies overview. Current role and record relationships determine its cards, with operational work grouped before personal requests/releases. Each count links to the corresponding queue with the exact status/recipient filter used to calculate it.

| Reader | Dashboard work |
|---|---|
| Requester/recipient | Own drafts and returned requests, submitted requests awaiting approval, approved outstanding requests, assigned releases awaiting acknowledgment or disputed, and visible awaiting-stock lines. |
| Scoped request approver | The personal work above plus pending approvals in current scope, excluding own requests. Shortages remain limited to owned/scoped records. |
| Custodian | Ready-to-issue requests, all operational shortages, pending/disputed releases, own unread active stock notices, current warning items and latest stock activity; personal requests remain separate. |
| Auditor | Read-only stock warnings, operational shortages and stock activity, plus independent personal work. No custodian action right is implied. |
| Technical administrator | Independent own-request/recipient rights and the existing configuration link; no automatic operational records, costs or queues. |

Recent personal requests show the next person/action. Submitted requests name current eligible approvers, or identify administrator assignment as the next step when none are configured. Approved outstanding requests identify the custodian's stock/handover responsibility. Release queues identify the recorded recipient for acknowledgment/dispute resolution. Shortage counts are explicitly **lines**, while request/release/warning/activity counts count their corresponding rows.

The request, approval, issuance, shortage, release, warning and new stock-activity queues use shared count/list queries in `supplies_dashboard.py`. Literal search is bounded to 200 characters. Applicable status/type filters and recipient-only release filtering are validated; unsupported values fail cleanly. Pages contain at most 25 results, ordered deterministically, with search/status/recipient parameters retained in previous/next links. The dashboard shows five recent personal requests and, for stock readers, five recent movements with links to full lists.

A shared current-grant request predicate checks the latest immutable submitted unit, including descendants by hierarchy boundary. It excludes other people's never-submitted drafts and does not follow private returned-draft edits into a different unit before resubmission. Request/release detail checks and operational queue visibility use the same scope/recipient helpers. Assigned recipients retain access to their release without gaining full-request or unrelated-release access. Count and list queries execute in the same SQLite read snapshot. Revocation immediately removes affected cards, queues and detail access on subsequent requests.

Stock activity is restricted to current custodians/auditors and selects only movement identity, item snapshots, signed quantity, dates and actor. It does not select supplier costs or receipt metadata. Current warning counts reuse the S4.1 live-stock predicate, not a potentially delayed notice projection. Pending notice processing remains explicit for stock readers. Personal unread notice counts use the existing recipient-scoped unread-active view.

Disabled mode keeps authorized counts/lists/details readable, explains paused business actions, hides request/receipt/handover action links and routes issuance links to read-only request detail. Underlying business mutation services continue to enforce the flag even for an old submitted form. Eligible internal staff can start a request when enabled; accounts without directory linkage receive the existing setup guidance rather than an unusable request link.

## Files and contracts

- New `supplies_dashboard.py`: shared queue construction, validated filters, count/list pagination, next-action labels and role-aware dashboard composition.
- `supplies_permissions.py`: reusable submitted-unit scope and request/release read SQL predicates.
- Existing list helpers in `supplies_requests.py`, `supplies_approvals.py`, `supplies_issues.py`, `supplies_backorders.py` and `supplies_notify.py` delegate to the shared queue service. Existing request/release detail helpers apply shared current permission clauses. Business posting/decision/acknowledgment contracts are preserved.
- `supplies_routes.py`: overview, queue filter inputs and GET `/supplies/activity`.
- New dashboard/activity templates, shared queue filter/pagination partials, and narrow queue/navigation/style edits provide keyboard-accessible links, labeled filters, status text and mobile request/approval summaries.
- `app.py` updates the existing Supplies search hint for the overview. `deploy_hf.py` includes the runtime module. Version, changelog and service-worker cache agree at 7.81.

No schema migration or new mutation endpoint is introduced by S4.2. Previous additive S3.3/S4.1 work remains present. GET dashboard, queue and activity views do not process notice backlogs, mark notices read, reserve/issue stock or write operation records.

Existing list APIs keep their record keys and default behavior, adding totals, filter metadata and pagination URLs. Query parameters: `q`, `status`, `page`; `/supplies/issues` also accepts `mine=1` for releases assigned to the current user. `/supplies/activity` uses `status` as the movement-type filter. Existing item and notice routes retain their prior contracts.

## Verification

**735 relevant tests passed**, no skips, including **26 new S4.2 cases**:

```bash
PATH=/workspace/scratch/supplies-venv/bin:$PATH python -m pytest -o addopts= -q tests/test_supplies*.py tests/test_search.py tests/test_deploy_hf.py tests/test_release_checks.py tests/test_work.py tests/test_browser_security.py tests/test_dependency_gates.py tests/test_backups.py tests/test_auth_rbac.py tests/test_phase0_security.py --junitxml=/workspace/scratch/supplies-s42-gate.xml
# 735 passed, 1 existing Starlette/httpx deprecation warning, 83.37 seconds.
python scripts/check_release.py junit /workspace/scratch/supplies-s42-gate.xml
# 735 tests, no failures or skips.

PATH=/workspace/scratch/supplies-venv/bin:$PATH python -m pytest -o addopts= -q tests/test_supplies_dashboard.py --junitxml=/workspace/scratch/supplies-s42-final.xml
# 26 passed after the final operational/personal grouping change.
```

Coverage includes card-to-filter count parity across roles, counts beyond the first page, own versus scoped requests, self-approval exclusion, cross-unit/private-draft protection, immutable submitted-unit scope through returned edits and resubmission, assigned-recipient-only access, acknowledgment/dispute count transitions, immediate revocation/inactivation denial, literal search and injection-like inputs, invalid filters/pages/limits, stable pagination with retained filters, current approver/assignment guidance, stock-reader-only activity without costs, unchanged business/notification tables after reads, disabled read access/business-write rejection, route authorization and escaped query text.

Release metadata, dependency-lock input checks, 188 vendored PDF.js file checks, deployment import closure, compilation and `git diff --check` pass. No dependency changes were needed. This is the relevant increment regression gate; the complete repository suite and merge/deployment gates were not rerun or claimed for S4.2.

### Real browser evidence

Temporary helper: `/workspace/scratch/verify_supplies_dashboard_browser.py`. Real Chromium exercised a temporary localhost Uvicorn server and disposable synthetic database:

1. Requester, scoped approver and custodian dashboards show counts matching their linked filtered queue responses. The requester opens the draft-action card using Tab/Shift-Tab/Enter, searches a draft and submits it using the keyboard.
2. The approver opens the scoped approval card, searches the request and approves its submitted quantities. The custodian receives five units through the receipt form, finds the approved request through a filtered issuance queue and posts a two-unit handover.
3. The recorded recipient opens the personal pending-acknowledgment card, keeps `mine=1` while filtering to the new release, acknowledges it, and sees the personal pending count fall from two to one. Counts are checked against the service after transitions.
4. Twenty-six additional synthetic drafts prove real previous/next navigation: search `Paged` and status `action` remain in the second-page URL and controls, with total 26 and one second-page record. Keyboard Enter follows the next link successfully.
5. The stock-activity view filters to the three issue movements. Requester pages and activity summaries omit the synthetic supplier/cost detail. There are five stock movements after the walkthrough: opening, two original releases, receipt and the new release.
6. Disabled mode retains counts/read links and hides receipt/handover actions. Replaying a previously successful handover payload with current session CSRF returns 409 and adds no movement. Revoking the approver grant removes the approval card, returns 403 for the inbox and 404 for the formerly scoped request.
7. Representative desktop and 390px views fit without page overflow. Dashboard cards, labeled filters, pagination and action forms are keyboard-operable; mobile summaries expose next actions without requiring table scrolling. No browser page errors or foreign-key violations occurred. Operational groups and mobile filters were visually inspected.

Synthetic screenshots:

- [Requester overview on desktop](evidence/supplies-s4-2/requester-overview-desktop.png)
- [Approver overview on desktop](evidence/supplies-s4-2/approver-overview-desktop.png)
- [Custodian work first on desktop](evidence/supplies-s4-2/custodian-overview-desktop.png)
- [Requester overview on phone](evidence/supplies-s4-2/requester-overview-mobile.png)
- [Personal acknowledgment queue](evidence/supplies-s4-2/personal-acknowledgment-queue-mobile.png)
- [Filtered second page on phone](evidence/supplies-s4-2/filtered-pagination-mobile.png)
- [Filtered stock activity](evidence/supplies-s4-2/stock-activity-mobile.png)
- [Disabled overview on phone](evidence/supplies-s4-2/disabled-overview-mobile.png)

## Handoff and recovery

**Next eligible increment: S5.1 — Replenishment suggestions and draft creation.** Reuse current on-hand, active reservation and outstanding-demand calculations. Do not count reserved demand twice. Preserve independent replenishment permissions and distinguish draft/proposed amounts from committed incoming stock. The approved plan defines the target/incoming formula and required missing-target handling.

This increment provides action queues and recent operational activity, with no replenishment drafts, purchasing, external messages or new analytics. Search is literal matching over defined queue fields; broad reporting/export remains later work. Counts are current at their read snapshot and can legitimately change before a linked page is opened if another user posts a decision or handover.

Recovery: these dashboard/list changes have no business data to undo. Existing record/detail links and business transaction/replay guards remain authoritative. Retain all earlier ledger, correction, warning and notice evidence when reverting view code. Continue to use the S4.1 explicit reconciliation action for pending warning delivery, never a repeated stock posting.

No live feature enablement, stock import, role configuration, merge, push of these local increments, or deployment was performed. The user's earlier stop-merging instruction remains in effect.
