# S0.1 — Supplies contracts and baseline

Date: October 21, 2026 (Asia/Manila). Status: **Verified** for technical contract/baseline; operational policy and staff pilot acceptance remain pending.

Scope: contract definition, synthetic acceptance data, and pre-implementation baseline. No application routes, database tables, stock transactions, grants, or live imports are introduced in this increment.

Plan: [Supplies management implementation plan](SUPPLIES_MANAGEMENT_PLAN.md). Repository inspected: `20746ba1f8c6fdde1c9a6dcbeb9340c2651bce64`. Initial working tree contained only the untracked plan. No applicable `AGENTS.md` was found in the workspace/repository or affected documentation/fixture directories.

## 1. Role and access contract

Role identifiers: `custodian`, `request_approver`, `replenishment_approver`, `auditor`. These are supplies grants, distinct from `auth.ROLE_CAPS`. Requester and recipient are relationships to a record, not privileged grant names. Module configuration uses the current database account's `admin` role; cookie-supplied roles are not authoritative.

An operational requester must be an active account linked through `admin_user.rp_id` to an internal `resource_person` with an organizational unit. Reload the account and directory linkage at submission. Snapshot that unit; do not accept an arbitrary requester/unit pair from form fields. Receipt recipients must be active staff accounts; default to the requester, with an explicitly recorded alternate recipient when needed. No external recipients or on-behalf request creation in v1.

| Action/data | Requester/recipient | Request approver | Custodian | Replenishment approver | Auditor | Technical administrator alone |
|---|---|---|---|---|---|---|
| Browse active catalog/available quantity | Active staff | Yes | Yes | Yes | Yes | Yes, if active staff |
| Create/edit/submit/withdraw own request | Own draft/returned record; withdraw before approval | Same ordinary staff rights | Same ordinary staff rights | Same ordinary staff rights | Same ordinary staff rights | Same ordinary staff rights |
| Read staff requests | Own; recipient sees assigned release and necessary request context | Submitted/decided records in current grant scope | Operational records; other people's private drafts excluded | No additional request access | Submitted/operational records | Setup routing metadata only; no general content/cost bypass |
| Approve/return/reject staff request | No self-approval | Current scope; never own request | Only with separate approver grant | Only with separate request-approver grant | No | No |
| Maintain catalog/thresholds; receive stock; issue; correct | No | No | Yes | No | No | No |
| Cancel unissued approved remainder | Own request | No additional right | Yes with reason | No | No | No |
| Acknowledge/dispute release | Recorded recipient only | Only if recorded recipient | May record paper receipt with method/reason | Only if recorded recipient | Only if recorded recipient | Only if recorded recipient |
| Prepare/submit/track replenishment | No | No | Yes | Read submitted/decided; decide with grant | Read-only operational | No business action |
| Approve/return/reject replenishment | No | No automatic right | Separate grant required; never own prepared request | Yes; never own prepared request | No | No |
| View ledger, supplier costs, operational reports | No | Request context only, no general supplier-cost access | Yes | Replenishment context/costs only | Yes, read-only | No automatic right |
| Configure enable flag and grant/revoke roles | No | No | No | No | No | Yes, audited |

`request_approver` grants require a real organizational unit, matching that unit and descendants by directory hierarchy. A bureau-root grant covers the bureau; do not use arbitrary null scope as an accidental global approval bypass. The other three grant types are stockroom-wide in v1 and have null unit scope. Grants are never physically deleted; set `revoked_at`. Multiple roles may coexist, but self-approval prohibitions still apply.

Approvers are resolved from current scope grants at decision time, not frozen as a person at submission. All eligible approvers see the same pending revision; only the first valid decision commits. Zero eligible approvers is a routing warning, not auto-approval. Setup may reveal request number/unit/count requiring an approver, without exposing its purpose/items to an otherwise unauthorized administrator. Revocation removes role-based visibility, queue counts and notice access immediately; a person's independent requester/recipient rights remain.

The feature flag defaults off. It blocks catalog and all stock/workflow business mutations, even for custodians; grants and flag configuration remain available to administrators. Reads require the same current authorization whether the flag is on or off. Configuration changes remain auditable while disabled. No new public-route or CSRF exception is allowed.

## 2. Domain names, validation, and persistence

Use integer primary keys and foreign keys to existing `admin_user`, `org_unit`, and `resource_person` records where appropriate. Snapshot names/units on posted evidence so later directory edits do not rewrite history. Immutable snapshots do not preserve access after a grant is revoked.

### 2.1 Shared fields

| Contract | Exact fields/rules |
|---|---|
| Mutable record | `id`, `revision` starting at 1, `created_by`, `created_at`, `updated_at`; expected revision required for updates/decisions. |
| Actor | Derived from current session account ID; never trust posted `actor_id`, role, stock balance or computed state. |
| Quantity | Whole-number decimal input, 1–2,147,483,647 for positive transaction/line quantities; zero allowed for opening, thresholds and approved line quantities. Reject fractions, booleans, negatives and overflow. Guard aggregate arithmetic against SQLite integer overflow. |
| Unit cost | Optional nonnegative decimal string, at most four decimal places, up to `999999999.9999`; store canonical decimal text. Empty means unknown, not zero. V1 assumes PHP; no floating-point valuation. |
| Text limits | Item code 40; description 240; unit 40; purpose 2,000; reason/note 2,000; supplier 240; reference numbers 120. Trim boundary whitespace; reject empty required fields. Escape on output. |
| Dates/time | `date_needed`, `effective_date`, `expiry_date`, `expected_delivery_date`: ISO `YYYY-MM-DD` when supplied. Posting timestamps from `tzutil.now_iso`; numbering year from `tzutil.today_local`. Do not use host UTC date. |
| Operation | `operation_key` (UUID), canonical server-built payload fingerprint, actor ID, operation name, target ID, committed result reference and time. Same authorized retry returns original result; mismatching payload conflicts. Reload access before returning a prior result. |
| Event | `id`, `entity_type`, `entity_id`, `action`, `actor_id`, `detail_json`, `created_at`, `operation_key`. Append-only; add an application audit record in the same transaction with no hidden commit. |
| Errors | `Denied`: not found/unavailable without existence leak; `Conflict`: stale revision/key reuse/incompatible state; `Invalid`: field or invariant validation; `Disabled`: writes unavailable. HTTP: unavailable read 404, denied action/CSRF 403, conflict 409, invalid 422, disabled business writes 409 with a clear message. |

Domain errors belong to Supplies, without importing Documents' business permission classes. Routes may use the repository's ordinary redirect-after-success pattern; validation re-renders submitted values with a safe error message. A successful domain call returns the resulting record/reference. Services accept an account-ID-bearing actor and reload it inside the write transaction.

### 2.2 Minimum schema/field contract by introduction increment

These are field contracts, not a request to create future tables in S1.1. Additional foreign keys/indexes may be introduced when needed without renaming these business fields.

| Increment/model | Required fields beyond applicable shared fields |
|---|---|
| S1.1 `supply_role_grant` | `user_id`, `role`, `unit_id`, `granted_by`, `created_at`, `revoked_by`, `revoked_at`; unique active user/role/scope, including global null scopes. |
| S1.1 `supply_item` | `code` (case-insensitive unique), `description`, `unit`, `critical_level` (default 0), `target_level` (nullable, at least critical when set), `active`. No stored user-editable stock balance. |
| S1.1 shared infrastructure | `supply_event`, `supply_operation`, `supply_sequence(kind, year, last_value)`; introduce/consume the transactional stock behavior in S1.2. |
| S1.2 movement | `item_id`, `kind`, signed `quantity_delta`, `effective_date`, immutable `posted_at`, `source_type`, `source_id`, `source_line_id`, optional `reverses_movement_id`, `reason`, `operation_key`. Kind: `opening`, `receipt`, `issue`, `return`, `adjustment`, `reversal`. Opening may be zero; other deltas must be nonzero with the correct sign. |
| S1.2 receipt/line | Header: `receipt_number`/internal ID, `supplier`, `dr_number`, `apr_number`, `procurement_mode`, `effective_date`, `received_by`, `posted_at`. Line: `item_id`, `accepted_quantity`, `unit_cost`, optional `expiry_date`; source unit snapshot. Nullable replenishment links added in S5.3. |
| S1.4 import | Batch: `source_sha256`, file name, `cutoff_date`, `reviewed_by`, `reviewed_at`, `status`, apply operation. Rows: `source_sheet`, `source_row`, raw names/units/balances, canonical mapping, `accepted_quantity`, reconciliation reason, excluded flag. Finalized selection is immutable. |
| S2.1 request | `control_number` (null in draft), `requester_id`, `unit_id`, `purpose`, `date_needed`, `approval_status`, `current_revision`, `submitted_at`, optional `legacy_control_number`. Immutable revision header/line snapshots on each submission. Lines: stable `line_id`, `item_id`, `description_snapshot`, `unit_snapshot`, `requested_quantity`. |
| S2.2 decision | `request_id`, `submitted_revision`, `decision` (`approved`, `returned`, `rejected`), `decided_by`, `decided_at`, reason; approved line quantity/reason keyed to that revision's line. A decision references the exact submitted revision. |
| S2.2 reservation | `request_id`, `line_id`, `item_id`, `reserved_quantity`, `approved_at`, version; current reservation projection is mutable only through the allocator. Changes append events. Outstanding/cancelled totals must remain traceable. |
| S3.1 issue/line | `release_number`, `request_id`, `recipient_id`, recipient snapshot, `issued_by`, `effective_date`, `posted_at`, operation. Lines: request `line_id`, `item_id`, `issued_quantity`, stock movement link. |
| S3.2 acknowledgment | `issue_id`, `status` (`pending`, `acknowledged`, `disputed`), `method` (`recipient`, `paper_recorded`), actor/time/note. Preserve prior events; a dispute can later resolve with evidence, never silently disappear. |
| S5.1 replenishment | `control_number`, `prepared_by`, `purpose`, `status`, `current_revision`, `submitted_at`; lines include `item_id`, `requested_quantity`, optional estimated `unit_cost`, suggestion inputs and override reason. |
| S5.2 approval/order | Immutable revision decision with approved quantities; header `order_reference`, `ordered_at`, `expected_delivery_date`; line `cancelled_quantity`. Incoming derives from approved minus net accepted receipts minus cancellations, counted once. |
| S5.3 delivery | Receipt header/line links to replenishment and its approved lines; `delivered_quantity`, `accepted_quantity`, `rejected_quantity`, rejection reason. Delivered = accepted + rejected; accepted > 0 required to post stock for a line. An all-rejected delivery may be documented with no stock movement. |
| S4.1 notices | Item/record, alert episode/version, recipient, created/read/resolved times; unique recipient/event key. Durable pending event processing so notification retry never replays a stock mutation. |

Do not duplicate original stock in an opening-balance item field and a ledger movement. Physical quantities come from signed movements; reserved quantities come from current reservations; derived balances are not editable. A materialized cache, if needed later, must be reconciled to those sources.

## 3. State and action contract

### 3.1 Supply requests

| Current approval state | Allowed action → result | Guard |
|---|---|---|
| `draft` | Edit/save; submit → `submitted`; withdraw → `cancelled` | Owner; valid active catalog items; submission unit/purpose/lines validated. |
| `submitted` | Approve → `approved`; return → `returned`; reject → `rejected`; owner withdraw → `cancelled` | Latest submitted revision; eligible non-owner approver for decisions; return/reject require reason. |
| `returned` | Owner edit while retaining `returned`; resubmit → `submitted`; withdraw → `cancelled` | New submitted revision; prior versions/decisions retained. |
| `approved` | Reserve, issue, acknowledge, cancel unissued remainder, or correct evidence | Approval state remains `approved`; changes to approved item/quantity require a new request. |
| `rejected`, `cancelled` | Read only; create a separate new draft if needed | Never reopen or reuse the prior control number as a new request. |

Allocate `SUP-YYYY-NNNNN` only on first submission; resubmission retains it. `REP-YYYY-NNNNN` follows the same rule. `ISS-YYYY-NNNNN` is assigned when an issue posts. Sequence update and record creation share a transaction; numbers need not be gapless, must never be reused, and fail explicitly after 99,999 in a year rather than wrapping.

For approved lines, exact quantity names are `requested_quantity`, `approved_quantity`, `effective_issued_quantity`, `cancelled_quantity`, `reserved_quantity`, `awaiting_stock_quantity`. The equations in the parent plan govern all screens/reports.

Derived fulfillment precedence, using the sum of approved quantities:

1. No outstanding and issued equals approved: `fully_issued`.
2. No outstanding, issued is zero, cancelled is positive: `cancelled_before_issue`.
3. No outstanding, both issued and cancelled are positive: `closed_remainder_cancelled`.
4. Outstanding remains and any quantity has been issued: `partially_issued`.
5. No issues yet and any reservation exists: `ready_to_issue`.
6. Otherwise: `awaiting_stock`.

Line shortages remain visible even when the header says Ready to issue or Partially issued. Acknowledgment is per release and cannot change these quantity-derived states.

### 3.2 Allocation and cancellation

Allocation orders eligible outstanding lines by immutable `approved_at`, request ID, then line ID. It fills the oldest line before the next. Recompute inside the serialized write transaction, never based on browser balances. Cancellation only removes outstanding quantities and releases associated reservations; it does not change posted issues. Cancel the full remaining quantity per selected line in v1; partial manual cancellation amounts are deferred.

Stocktake loss deallocates in reverse priority order until total reservations fit on-hand, records every affected line, and leaves those quantities awaiting stock. Receipt, positive correction, accepted return and released reservations refill by normal oldest-first priority. A blocked receipt reversal does not silently deallocate; the operator must explicitly reconcile it through the appropriate correction action first.

### 3.3 Returns and correction decisions

Use actual accepted usable returns as positive movements linked to issue lines; rejected/unusable returns do not add usable stock. A true return never reduces `effective_issued_quantity` or reopens demand. Limit the sum of true returns and erroneous-issue reversals to the original issued quantity.

For erroneous issue reversal, require `reopen_demand` and a reason. True reduces effective issuance and restores the corrected quantity to outstanding allocation; false reduces issuance and adds that quantity to cancelled remainder so the request stays closed for that quantity. Preserve all existing valid cancellations. The choice is explicit in the correction preview; default to requiring a selection. This prevents hidden demand reopening after a closed request is corrected.

For erroneous replenishment-linked receipt reversal, require `reopen_incoming` and a reason. True subtracts from net received and restores the corrected quantity to approved incoming; false moves that quantity to cancelled remainder instead. Never exceed the original accepted quantity or reverse stock that is no longer on hand/free under the parent's constraints. The correction changes stock, receipt net totals, replenishment status and events atomically.

No automatic replacement demand is created for lost or damaged supplied items. A staff requester creates a new request if a replacement is needed. A correction may not reverse a reversal; if a new error needs correction, record a new justified adjustment/receipt/issue through the appropriate service with links to the correction evidence.

### 3.4 Replenishment

Persist approval state (`draft`, `submitted`, `returned`, `approved`, `rejected`, `cancelled`) separately from procurement fulfillment. Preserve an Approved decision after unreceived remainder cancellation, just as for staff requests. Derive operational display: Approved awaiting order, Ordered, Partially received, Received, Cancelled before receipt, or Closed with remainder cancelled. A rejected delivery does not count as received. Actual receipt can occur against Approved without a separate order entry.

Order tracking cannot change approved line quantities. Multiple delivery lines may satisfy an approved line, but net accepted + cancelled cannot exceed its approved quantity. Incoming includes approved but not yet ordered quantities, so changing Ordered stage does not add it again.

## 4. Service and route boundaries

Common mutation signature: `service(conn, user, ..., expected_revision, operation_key)` where mutable state exists. A fresh database transaction owns actor/grant reload, revision/idempotency checks, writes, numbering/allocation, events and audit. Helpers do not commit. No new module calls Documents or Work to determine whether Supplies is enabled or who can approve.

| Increment | Service entry points to introduce | Route contract |
|---|---|---|
| S1.1 | `enabled`, `require_actor`, `can_view_*`, `require_*`, `create_item`, `update_item`, `deactivate_item`, `grant_role`, `revoke_role` | GET `/supplies`, `/supplies/items`, `/supplies/settings`; POST `/supplies/items`, `/supplies/items/{id}/update`, `/supplies/items/{id}/deactivate`, `/supplies/settings/enabled`, `/supplies/settings/grants`, `/supplies/settings/grants/{id}/revoke`. |
| S1.2 | `post_opening`, `post_receipt`, `stock_card`, `stock_totals` | GET `/supplies/items/{id}`, `/supplies/receipts/new`; POST `/supplies/items/{id}/opening`, `/supplies/receipts`. |
| S1.3–S1.4 | `preview_import`, `reconcile_import`, `apply_import` | GET `/supplies/import`; POST `/supplies/import/preview`, `/supplies/import/{id}/reconcile`, `/supplies/import/{id}/apply`. |
| S2.1 | `save_draft`, `submit_request`, `withdraw_request`, `get_request`, `list_requests` | GET `/supplies/requests`, `/supplies/requests/new`, `/supplies/requests/{id}`; POST `/supplies/requests`, `/supplies/requests/{id}/save`, `/submit`, `/withdraw` under that record path. |
| S2.2–S2.3 | `decide_request`, `allocate_outstanding`, `cancel_remainder` | GET `/supplies/approvals`, `/supplies/awaiting-stock`; POST `/supplies/requests/{id}/decide`, `/supplies/requests/{id}/cancel-remainder`. |
| S3.1–S3.2 | `post_issue`, `acknowledge_issue`, `record_paper_acknowledgment`, `request_print` | GET `/supplies/issuance`, `/supplies/issues/{id}`, `/supplies/requests/{id}/print`; POST `/supplies/requests/{id}/issues`, `/supplies/issues/{id}/acknowledge`, `/supplies/issues/{id}/paper-acknowledgment`. |
| S3.3 | `post_return`, `post_stocktake`, `reverse_issue`, `reverse_receipt` | POST `/supplies/issues/{id}/returns`, `/supplies/items/{id}/stocktake`, `/supplies/issues/{id}/reverse`, `/supplies/receipts/{id}/reverse`; GET forms show impact previews. |
| S4.1–S4.2 | `reconcile_alerts`, `list_notices`, `dashboard` | GET `/supplies/warnings`, `/supplies/notices`; POST `/supplies/notices/{id}/read`. |
| S5.1–S5.3 | `suggest_replenishment`, `save_replenishment`, `submit_replenishment`, `decide_replenishment`, `record_order`, `cancel_replenishment_remainder`, `receive_delivery` | GET `/supplies/replenishments`, `/new`, `/{id}` under that path; POST create and `/{id}/save`, `/submit`, `/decide`, `/order`, `/cancel-remainder`, `/deliveries` under each record. |
| S6.1 | `inventory_report`, `consumption_report`, `fulfillment_report`, `incoming_report` | GET `/supplies/reports/{report}` and `/supplies/reports/{report}.xlsx`; only allowlisted report names/filters. |

GET routes never create a stock transaction or business decision. POST forms use a session-bound `supplies:` CSRF token plus the existing origin middleware. All navigation targets are fixed local URLs or validated with `safe_local_return`. Pagination applies to queues and histories. A consistent predicate controls detail/list/count/export/notice visibility.

## 5. Repository integration confirmed

- `storage.connect` enables foreign keys, WAL and busy timeout. `storage.init_db` installs `documents_storage` and `work_storage`; add the new independent supplies installer here in S1.1. Do not make business transactions call schema installation.
- `documents_storage.transaction` rejects an already-open transaction, uses `BEGIN IMMEDIATE`, commits on success and rolls back on failure. Follow this ownership pattern in Supplies without coupling to Documents. Do not silently commit caller work.
- `app.get_conn` and router factories are the existing connection/router injection pattern. `app.py` registers routers near its end. `work_routes` provides an existing session-bound form-token pattern; inspect the then-current version before adapting it.
- `app._auth_gate` reloads the session user and checks same-origin writes via `request_security`. `/supplies` remains authenticated and is not added to public routes/CSRF exemptions. Add module grant checks inside services too.
- `templates/dash_layout.html` is the dashboard/navigation base. Use existing components and escaped Jinja output; no new frontend build dependency.
- `tzutil.now_iso` and `today_local` supply the configured Philippine local wall clock. Tests freeze the clock in `tests/conftest.py`; do not assume the host date.
- Existing HTTP fixtures use registered-session `session_token`, private database copies and browser Origin headers. Build supplies synthetic accounts/grants using the same pattern, without changing global role capabilities.
- `backups.py` uses SQLite's backup API. Existing shared-database backups must retain the added tables. Recovery testing belongs in S6.2, before live use.
- `docs/DEPENDENCIES.md` specifies Python 3.11 and the hash-verified `requirements-test.txt`. `run_tests.sh` runs pytest followed by `qa_smoke.py`. Application version/release notes are in `version.py`; S0.1 has no user-visible application change and needs no bump.

## 6. Synthetic acceptance evidence

Fixture: [contract_scenario.json](../tests/fixtures/supplies/contract_scenario.json). It has only invented actor names and one invented item. Each of 12 steps records expected `[on_hand, reserved, available, outstanding, incoming]` quantities. It is acceptance data for later tests, not proof that a Supplies service exists.

The key expectations are: opening 10; approve A for 6 and B for 7; issue A four exactly once; cancel A's remaining two and transfer reservations to B; suggest replenishment 21; approve it without physical stock change; accept deliveries of 10 and 11; issue B seven; accept a real return of one without reopening B's demand. Final on-hand is 21, reserved/outstanding/incoming are zero. Ledger arithmetic: `10 - 4 + 10 - 7 + 11 + 1 = 21`.

The fixture was independently walked through with a small in-memory reference calculation: maintain approved/issued/cancelled quantities by request, allocate in approval order after each step, deduplicate issue operation keys, and compare all five totals to each expected checkpoint. This calculation does not import or exercise a future supplies implementation.

**Result:** 12/12 checkpoints passed; two unique issues despite three issue attempts; six signed ledger entries; oldest-first reservation redistribution; suggestion 21 before replenishment approval and zero afterward; genuine return leaves B's demand closed. Every checkpoint satisfies `available = on_hand - reserved`, nonnegative stock/reservations, and outstanding demand at least reserved stock.

### Baseline environment and commands

The initial command below stopped before collection with `No module named pytest` in the workspace's default Python 3.12.14. This was an environment setup issue, not an application test failure:

```bash
python -m pytest tests/test_work.py tests/test_browser_security.py tests/test_dependency_gates.py tests/test_backups.py
```

Created an isolated environment outside the checkout and installed the existing hash-verified test lock without editing dependency files:

```bash
uv venv --python 3.11 /workspace/scratch/supplies-venv
uv pip install --python /workspace/scratch/supplies-venv/bin/python --require-hashes --only-binary=:all: -r requirements-test.txt
/workspace/scratch/supplies-venv/bin/python -m pip check
/workspace/scratch/supplies-venv/bin/python -m pytest tests/test_work.py tests/test_browser_security.py tests/test_dependency_gates.py tests/test_backups.py
```

Observed interpreter: CPython 3.11.17. Lock installation succeeded with 68 packages. `pip check`: **No broken requirements found**. Focused baseline: **230 passed, 1 warning in 27.11s**. The existing warning is `StarletteDeprecationWarning` about httpx use by Starlette TestClient; no dependency changes were made to address it in this documentation increment.

This baseline covers existing Work domain/HTTP conventions, browser security response/origin behavior, dependency gates and shared backup behavior. It is not the full regression suite, a browser UAT session, a production check, or a test of a Supplies module. No failing application test was observed in this selected baseline. The full runner and live recovery checks remain scheduled under S6.2/S6.3.

Document/fixture validation also passed: 19 unique execution IDs; all local Markdown links resolve; balanced code fences; no trailing whitespace; valid JSON; and `git diff --check`. The only checkout additions/edits for this increment are the plan, this contract/evidence document and the synthetic fixture. No version bump or runtime file change is needed.

## 7. Operational inputs and later boundaries

Before S6.3 live cutover, record real custodians, scoped request approvers and alternates, a replenishment approver distinct from the preparer, an auditor/support owner, pilot offices, physical-count/cutoff date, reconciled item units and balances, and which non-consumable/expiry-controlled items remain excluded. None is fabricated in this contract. All can remain pending during synthetic development.

No new staff outreach, external notifications, purchases, production grants, deployment, or uploaded opening balances have been executed. The user's current instruction is being applied to the first increment of the agreed one-increment-per-run plan.

## 8. Handoff

Evidence status: **Verified**. The role/action matrix, field names, service/route boundaries, correction choices, numerical expectations and focused baseline are recorded. No unresolved reservation, partial-issue, return or numbering decision blocks synthetic implementation. Operational inputs in section 7 remain pending for live cutover.

Next eligible increment: **S1.1 — Module shell, grants, and item catalog**. Its implementation must start by rereading this matrix, common fields, and the current integration points; future stock/request tables remain deferred to their listed increments. Reuse the isolated test environment if still available; otherwise recreate it from the same lock.

Recovery: these changes add documentation and a synthetic fixture only; remove/revert those additions and the plan status edit to undo S0.1. No operational database recovery is required.
