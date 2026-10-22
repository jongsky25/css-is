# Supplies S6.3 cutover and staff-pilot record

Status: **Paused at user request — operational evidence pending**. The people below were nominated in this conversation, but their accounts, scopes and grants have not been verified or changed. Keep count sheets and current stock balances in an appropriately controlled location, not as test fixtures. A blank field is an unmet gate, not an assumed approval.

## 1. People, scope, and authority

| Required fact | Actual value / evidence reference |
|---|---|
| Pilot office(s) and organizational-unit IDs | **Whole office** (user-confirmed); organizational-unit IDs pending |
| Pilot coordinator and support owner/contact | Support contact: **gbcanoy@doh.gov.ph** (user-nominated); coordinator pending |
| Requester(s), active account IDs and office | Whole-office staff; active account IDs and office mapping pending |
| Request approver and scoped unit; eligible alternate for own requests | **gbcanoy@doh.gov.ph**; alternate for their own requests: **armedel@doh.gov.ph** (user-nominated); scoped unit/grants pending |
| Custodian(s), including one for count/import/issue | **gbcanoy@doh.gov.ph** (user-nominated); account/grant pending |
| Replenishment approver, separate from its preparer | **armedel@doh.gov.ph** (user-nominated); account/grant pending |
| Read-only auditor/reconciliation reviewer | **Pending** |
| Person authorized to pause/reopen Supplies; recovery coordinator | **Pending** |

An administrator records grants at `/supplies/settings` and confirms each person signs in with their own active account. A request approver's grant must cover the requesting unit. The requester cannot approve their own request, and a replenishment preparer cannot approve their own replenishment. A general administrator grant alone gives neither business approval nor stock-posting authority. Record grant IDs, scopes, and a second person's review of the assignments in the controlled pilot record.

## 2. Inventory and cutoff evidence

| Required fact | Actual value / evidence reference |
|---|---|
| Count date/time, timezone, count team, signed count-sheet location | **Pending** |
| Agreed final spreadsheet posting cutoff, timezone, and owner who enforces freeze | **Pending** |
| Exact source workbook filename and SHA-256 | **Pending** |
| Included item list: source row, canonical item/code, physical count and unit, critical/target levels | **Pending** |
| Excluded rows and reason, especially non-consumables and expiry-controlled items | **Pending** |
| Unit/name conflicts resolved by count in canonical unit; reviewer | **Pending** |
| Pre-cutoff outstanding *unissued* request register and owner | **Pending** |
| Verified backup name/location, timestamp, integrity result, recovery owner | **Pending** |
| Import batch ID, accepted-selection hash, review/applied IDs | **Pending** |
| Inventory/ledger reconciliation report and independent sign-off | **Pending** |

The uploaded `Updated-Stock-Card.xlsx` is source reference data, not a dated physical count. It has known unit/name discrepancies and cached formula balances. Do not convert Pack/Piece/Ream or accept a displayed balance by inference. Each included row needs an explicit physical count in its canonical unit; each excluded row needs a reason. Keep expiry-controlled items outside the pilot unless a separate batch/expiry operating process is approved and implemented. Record stock already issued before cutoff only in history outside this new ledger; do not enter it again as a new issue. Record only genuinely unissued pre-cutoff demand in the separate register, then decide its new-system treatment without doubling demand.

## 3. Ordered cutover gates

Mark each step with time, actor, evidence reference, and independent reviewer in the controlled record. Stop on any unresolved difference.

1. Confirm the deployed build matches the locally verified S6.2 release and that the pilot office, people, role separation and item scope above are complete. Demonstrate authorized read access and denied access outside scope while Supplies writes are paused.
2. Reconcile the final spreadsheet movements to the signed physical count. Resolve each item name/unit mismatch and every physical-versus-sheet variance. Agree on the source of truth at cutoff and publish the exact freeze time to stock posters.
3. Take a consistent shared-database backup through the existing Backups module, retain its name/location outside ephemeral storage, verify integrity and a recoverable copy, and record other-module activity that recovery would affect. The disposable S6.2 restore rehearsal does not verify this live backup.
4. Freeze spreadsheet stock posting at the agreed cutoff. Capture a final source snapshot and hash. Keep paper or spreadsheet corrections after cutoff in a separately numbered exception log until posted or rejected; do not run two independent stock ledgers.
5. In a controlled window, grant the custodian access and temporarily enable Supplies for the reviewed import only. Preview the exact workbook at `/supplies/import`; reconcile **every** row; finalize with the dated count/cutover basis; have the reviewer inspect the final selection and its exclusions before applying once. Keep pilot staff from posting requests, receipts, issues or corrections during this window. If this separation cannot be enforced, do not import yet.
6. Pause Supplies writes again. Compare the applied import report, opening ledger entries and `/supplies/reports/inventory` to the accepted physical count for every included item, including zero counts. Check units, thresholds, excluded rows, total opening movements, and absence of duplicate openings. Resolve differences through audited correction review, never direct balance edits or a repeated import.
7. Review the pre-cutoff outstanding register with the approver and custodian. Enter only approved, still-unissued obligations through the normal request flow when the pilot opens; record links to legacy control numbers. No historical issue is deducted a second time.
8. After independent stock/ledger sign-off, enable the pilot for the named users. Record the exact time the application becomes the sole stock-posting source. Keep the prior spreadsheet read-only as historical evidence.

## 4. Representative staff acceptance

Use a real pilot item and small authorized quantities, with separately identified actors. Record request/replenishment/issue/receipt IDs, timestamps, expected and actual on-hand/reserved/available/incoming values, and evidence links for each step. Do not enter test stock into live balances merely to produce a screenshot.

| Step and responsible role | Evidence and acceptance check | Result |
|---|---|---|
| Requester submits from pilot office | Request number, purpose, unit and requested quantity are correct; requester sees own status | **Pending** |
| Scoped approver decides, possibly reducing quantity | Decision actor/scope, remarks and approved amount are visible; self-approval is denied | **Pending** |
| Custodian partially issues | Release number/recipient, reserved and physical stock change once; remainder is visible | **Pending** |
| Recipient acknowledges release | Recipient and time/method appear on release history; no second deduction | **Pending** |
| Custodian reviews warning and drafts replenishment | Available stock, threshold, demand and suggested amount make sense | **Pending** |
| Separate replenishment approver decides | Decision and order reference are recorded; preparer cannot self-approve | **Pending** |
| Custodian receives partial delivery | Accepted/rejected amounts and DR/supplier reference; accepted stock and incoming reconcile | **Pending** |
| Auditor/reviewer checks reports | Stock card, inventory, fulfillment, consumption and outstanding replenishment match the ledger/count | **Pending** |
| Support owner runs recovery walk-through | Write pause, preserved reads, incident contacts and reconciliation route understood | **Pending** |

Log each defect with ID, severity, owner, affected transaction IDs, expected/actual quantities, resolution and retest evidence. A material stock, access or audit difference keeps the pilot blocked. The pilot coordinator and independent reviewer sign off only after all rows above pass and current inventory agrees with counted stock plus documented post-cutoff movements.

## 5. Incident and recovery rule

The authorized administrator can disable Supplies changes at `/supplies/settings`; existing authorized reads and posted evidence remain available. Preserve request, movement, issue, delivery and audit IDs. Record an incident timestamp and a current shared-database backup before any repair. Reconcile transactions through the application's reviewed correction flow and the paper exception log. Do not blindly restore an earlier shared database after other modules or offices have written new data. Any full restore requires a coordinated recovery decision covering all modules and subsequent activity.
