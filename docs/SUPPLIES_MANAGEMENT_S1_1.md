# S1.1 — Module shell, grants, and item catalog

Date: October 21, 2026 (Asia/Manila). Status: **Verified locally**. No production deployment, real role assignments, or inventory import was performed.

Prerequisite: [S0.1](SUPPLIES_MANAGEMENT_S0_1.md), verified. Parent plan: [Supplies management](SUPPLIES_MANAGEMENT_PLAN.md).

## Implemented behavior

- **Office → Supplies** opens the searchable catalog. Active staff accounts can browse active item descriptions, units, critical levels and optional target levels. Catalog pagination uses 50 items per page. No physical or available balance is fabricated before the ledger exists.
- `/supplies/settings` is restricted to current database administrators. They can enable/disable business changes and assign/revoke the independent custodian, scoped request-approver, replenishment-approver and auditor grants. Configuration remains available while business changes are disabled. Setup does not grant catalog-maintenance authority by itself.
- A current custodian can add, edit and deactivate catalog items while enabled. Codes are unique without regard to ASCII case. Whole-number thresholds and target-at-least-critical are validated. Deactivation requires a reason and retains the record/history.
- Custodians and auditors can include inactive items and read recent item history. Other staff cannot reveal inactive items by changing a query string or guessing an item URL. Auditors cannot change catalog records.
- Every mutation reloads the account and relevant authority inside a serialized transaction. Form tokens are bound to the session and the existing origin middleware still applies. Revision checks reject stale edits. Operation UUIDs and payload fingerprints make identical retries harmless and reject reused keys with different changes.
- Configuration/catalog changes, operation results, append-only module events and the existing application audit entry commit together. Audit failures roll back the business change. Busy writes return a retryable conflict. No helper commits a caller's open transaction.
- `supplies.enabled` defaults off and is independent of Work/Documents. Disabling writes leaves permitted catalog reads available. No new public endpoint or CSRF exemption was added.

## Files and schema

New production modules: `supplies_storage.py`, `supplies_permissions.py`, `supplies.py`, `supplies_routes.py`.

New views/styles: `templates/supplies/{base,_fields,catalog,item,settings,error}.html`, `static/css/supplies.css`.

Narrow integration edits: `storage.init_db` registers the installer; `app.py` imports/registers the router and adds the shared Office navigation/search entry; `templates/dash_layout.html` recognizes the menu highlight. `version.py` records version **7.66** and its plain-language catalog/setup release note.

Additive foundation schema only:

| Table | Purpose |
|---|---|
| `supply_role_grant` | Revocable module roles with real-unit scope for request approvers; partial uniqueness also prevents duplicate active global grants. |
| `supply_item` | Validated item masters, active state, revision and thresholds. |
| `supply_operation` | Immutable operation keys, actor/payload identity and committed results. |
| `supply_event` | Append-only per-entity event history, linked to its operation and actor. |
| `supply_sequence` | Numbering foundation for later SUP/REP/ISS workflows; not consumed yet. |

No stock, request, replenishment, delivery or notification tables are installed in this increment. Repeat schema installation preserves existing records, operations, grants, events and enable state. The installer does not seed live business roles or items.

## Verification evidence

Python: isolated CPython 3.11.17 environment prepared under S0.1 from the existing hash-verified test lock. All fixture data and browser accounts are synthetic.

```bash
/workspace/scratch/supplies-venv/bin/python -m pytest tests/test_supplies.py tests/test_work.py tests/test_browser_security.py tests/test_dependency_gates.py tests/test_backups.py tests/test_auth_rbac.py tests/test_phase0_security.py
```

**Result: 368 passed, 1 warning in 32.10s.** This includes 26 Supplies cases and 342 existing regression cases. The warning is the existing Starlette/httpx TestClient deprecation, also present in the S0.1 baseline.

The focused Supplies cases cover migration repeatability, default-off/independent flags, current/stale/inactive actors, technical-admin separation, scoped descendants versus similarly named sibling units, duplicate null-scope grants, revocation, operation-key replay and mismatches, stale settings/item/grant revisions, invalid thresholds/units/text, inactive visibility, pagination, transactional audit failure, immutable history, transaction ownership/busy contention, the upcoming stock-unit-lock integration boundary, CSRF/origin checks, output escaping and real HTTP form flows. Disabled HTTP writes are checked with a valid current session-bound token and return 409, independently of the CSRF tests.

Additional commands:

```bash
/workspace/scratch/supplies-venv/bin/python scripts/lock_dependencies.py --check
/workspace/scratch/supplies-venv/bin/python -m compileall -q supplies.py supplies_storage.py supplies_permissions.py supplies_routes.py
git diff --check
```

Results: lock inputs current; compilation successful; no whitespace errors. No dependency lock was changed.

### Browser → route → database → response

Used local Chromium (`/usr/bin/chromium`) through Playwright, a temporary database, and registered synthetic sessions. The full walkthrough used a temporary localhost Uvicorn process with application lifespan jobs disabled:

1. Administrator opened settings, assigned a custodian and enabled changes.
2. Custodian added an item through the form, edited it, and saw the saved detail/catalog.
3. Ordinary staff saw the item but had no maintenance form.
4. Custodian deactivated it; ordinary staff's refreshed catalog excluded it.
5. Administrator disabled changes; custodian could still read inactive history but had no create control.
6. Database inspection matched the final item at revision 3 and exactly six operation/event records for those six business/configuration changes. No browser page errors occurred.

A targeted subsequent layout check loaded the real rendered routes/assets through TestClient and Chromium: desktop catalog/settings rendered; the role select had an explicit accessible label; at 390px viewport width the table remained at least 680px wide inside a focusable horizontal scroll region, and the document did not overflow. This corrected the initial narrow-column phone rendering. The form remains a single column on phones.

Recorded screenshots (synthetic accounts/items only):

- [Desktop catalog](evidence/supplies-s1-1/catalog-desktop.png)
- [Phone catalog](evidence/supplies-s1-1/catalog-mobile.png)
- [Administrator settings](evidence/supplies-s1-1/settings-desktop.png)

Local walkthrough helpers were `/workspace/scratch/verify_supplies_browser.py` and `/workspace/scratch/check_supplies_layout.py`. The committed HTTP tests and screenshots retain the behavior/evidence if those temporary helpers disappear. No production browser session or real inventory was used. The complete repository regression runner remains scheduled for S6.2; this increment ran the focused and relevant shared suites above.

## Limits and next integration points

S1.1 does not implement stock balances, opening entries, receipts, supply requests, approvals, issuance, replenishment, alerts or reports. Role grants for later workflows are configuration foundations, not working approval queues. Deactivation has no outstanding obligations to reconcile because those models do not yet exist.

**Next eligible increment: S1.2 — Stock ledger, opening entry, and manual receipt.** Reuse the existing transaction, operation and audit primitives instead of introducing competing commit/idempotency paths. Add stock tables only in that increment. `update_item` already checks for posted `supply_stock_movement` rows before allowing a unit change; preserve/test that guard against the real schema.

When S2.1 introduces requests, and S5.1 introduces replenishment, extend `deactivate_item` with open-obligation checks before those workflows become writable. Keep the custodian/auditor versus ordinary-staff inactive visibility predicate consistent. Item reactivation is not exposed in this increment; preserve retired codes/history rather than reusing codes for a new unit.

## Recovery

Keep Supplies disabled if any issue appears. Authorized reads remain available. A code rollback should leave these additive tables and evidence intact; no destructive down migration is needed. Re-enable/role configuration is only performed by a current administrator. Do not restore an old copy of the entire shared application database just to undo a catalog change after other office activity has occurred.

There are no open technical failures blocking S1.2. Live role assignments, physical-count date, reconciled opening balances and staff acceptance remain the operational inputs already listed under S0.1/S6.3.
