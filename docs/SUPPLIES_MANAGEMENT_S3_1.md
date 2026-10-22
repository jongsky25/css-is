# S3.1 — Partial and full issuance

Date: October 21, 2026 (Asia/Manila). Status: **Verified locally**. Prerequisite: [S2.3](SUPPLIES_MANAGEMENT_S2_3.md). Parent: [implementation plan](SUPPLIES_MANAGEMENT_PLAN.md).

## Delivered

Current custodians can open **Ready to issue**, choose an approved request with reserved stock, and record the actual quantities handed to an active internal staff recipient. Quantities start blank; unused item lines remain blank. The form shows current reserved, outstanding, issued and awaiting-stock quantities, requires a handover date and explicit confirmation, and defaults to the requester when that account remains an eligible recipient.

Each handover receives its own `ISS-YYYY-NNNNN`, effective handover date, posting timestamp, issuer/recipient snapshots and immutable item lines. A custodian may issue some reserved quantities now and the rest in another release. Posting reduces physical on-hand and current reservations together, increases effective-issued totals, retains approval/cancellation evidence and reruns the existing allocator inside the same transaction. Request fulfillment updates to Partially issued, Fully issued or the other quantity-derived states as appropriate.

An alternate recipient requires a recorded reason. Eligible recipients are active accounts linked to current unarchived internal directory staff with an organizational unit; this is rechecked before posting. Recipient selection cannot assign external or inactive accounts. The release retains historical recipient/issuer/item names and units even after later directory/catalog changes.

**Releases** lists records accessible through requester ownership, assigned recipient, current scoped approval or custodian/auditor grants. An alternate recipient can read their assigned release and its necessary submitted request context, without gaining access to unrelated releases or the complete request. Technical administrator status alone confers no business access. Request detail links each release separately, preserving partial release dates and quantities.

All issuance checks current account/grants, feature flag, request revision and reservation versions inside a serialized write transaction. Issued quantities must be positive whole numbers no greater than both current reservation and uncancelled outstanding demand. The item must remain active with the approved canonical unit. Unapproved, unreserved, cancelled, stale or over-quantity issuance fails without a release, number or stock deduction. Identical authorized retries return the committed release reference.

## Implementation

- Added `supplies_issues.py`: custodian queue/form data, current recipient validation, release numbering, atomic handover posting and role/relationship-scoped release reads/lists.
- Added immutable `supply_issue` and `supply_issue_line` tables. Headers retain submitted revision, recipient account/directory snapshots, alternate reason, issuer/date/note and operation key. Lines retain stable request line, submitted revision line, reservation, item, quantity, canonical snapshots and a unique stock movement link.
- A database trigger verifies that each issue line matches its negative issue movement's item, quantity and source header/line identifiers. Release/line updates and deletes are blocked. Issue line IDs are allocated under the same serialized write transaction before linking movement and line.
- Posting owns one `BEGIN IMMEDIATE`: validate all selected lines; allocate number; insert release/movements/lines; reduce reservations and increase issued projections; advance request revision; record audited issue/request events; run the shared allocator; commit. Audit, movement or allocator failure rolls everything back.
- Added GET `/supplies/issuance`, `/supplies/issues`, `/supplies/issues/{id}`, `/supplies/requests/{id}/issues/new`, and POST `/supplies/requests/{id}/issues`. All writes retain current-custodian, feature-flag, session-bound CSRF and Origin checks.
- Added queue, handover, release list/detail templates, mobile quantity summaries, navigation and release links/timeline labels on request detail. Invalid/stale forms retain entered quantities and original concurrency tokens so newer stock cannot be silently accepted.
- Version is **7.73**. No dependencies, external services, acknowledgment/signature controls or print exports were added.

## Verification

The relevant regression run passed **567 cases**, including **33 S3.1 cases** and the previous 534 relevant cases:

```bash
/workspace/scratch/supplies-venv/bin/python -m pytest tests/test_supplies_issues.py tests/test_supplies_backorders.py tests/test_supplies_approvals.py tests/test_supplies_requests.py tests/test_supplies_import_review.py tests/test_supplies_import.py tests/test_supplies.py tests/test_supplies_stock.py tests/test_work.py tests/test_browser_security.py tests/test_dependency_gates.py tests/test_backups.py tests/test_auth_rbac.py tests/test_phase0_security.py -o addopts= -q
```

Coverage includes:

- Two partial releases completing approved demand; unique numbers, exact stock/issued/reserved totals, unchanged approval evidence and safe replay.
- Zero/negative/fractional/boolean quantities, over-reservation, foreign/duplicate lines, stale request/reservation revisions, future dates and missing confirmation, leaving no release or consumed number.
- Owner/approver/administrator issuance denial; current custodian authority and revoked/disabled successful-operation retries.
- Unapproved, unreserved and cancelled demand rejection; receipt-induced version staleness; real partial issue followed by remainder cancellation and another request's fulfillment.
- Alternate-recipient reasons; assigned-release-only reads/listing without request access or access to a different release.
- Recipient inactivity, external/archive/unitless/unlinked directory records rechecked at posting; immutable snapshots after later directory/catalog changes.
- Immutable posted headers/lines, scoped reader revocation, movement-match constraints and valid foreign keys.
- Annual release-number exhaustion; second-line movement failure; audit/allocator failure, all with no partial release/movement/projection/numbering effect.
- Two simultaneous independent SQLite connections competing to issue the final reserved units: one succeeds and one conflicts, with zero on-hand/reserved and exactly one release.
- Multi-item handovers, queue/release pagination, repeated additive installation, HTTP CSRF/Origin checks, request-owner write denial and safe stale-form quantity/version preservation.

Dependency-lock input checks, compilation and `git diff --check` passed. The existing Starlette/httpx TestClient deprecation remains the only warning. The complete repository runner remains scheduled for S6.2.

### Browser → handover → release → stock/request → response

Installed Chromium through Playwright used a temporary localhost Uvicorn server, disposable SQLite database and registered synthetic sessions:

1. The custodian selected an approved request for 6 Ream from Ready to issue against physical stock of 10. The requester was the default recipient; issue quantity started blank.
2. An actual form submission posted 4 Ream as `ISS-2026-00001`. Replaying the original POST deducted once, and the request displayed Partially issued with 2 remaining reserved.
3. A second form posted the remaining 2 Ream as `ISS-2026-00002` on a separate handover date, with an alternate recipient and explicit reason.
4. The requester saw Fully issued and links to both releases. The alternate's Releases list contained only the assigned second release; the first release and full request returned 404 for that account.
5. The issuance queue cleared. The database held two issue headers, two issue lines and three physical movements (opening, issue 4, issue 2), with **4 on hand, 0 reserved, 4 available** and effective-issued 6.
6. Foreign-key checks passed, no browser page errors occurred, and forms/release views fit a 390px viewport. The mobile handover form was visually inspected.

Synthetic screenshots:

- [Mobile handover form](evidence/supplies-s3-1/handover-form-mobile.png)
- [Mobile alternate-recipient release](evidence/supplies-s3-1/alternate-release-mobile.png)
- [Desktop release](evidence/supplies-s3-1/alternate-release-desktop.png)
- [Fully issued request with both release links](evidence/supplies-s3-1/fully-issued-request.png)

Temporary helper: `/workspace/scratch/verify_supplies_issues_browser.py`. No production stock, requests, staff roles or deployment were changed.

## Handoff and recovery

**Next increment: S3.2 — Receipt acknowledgment and printable request/release.** Add separate append-only acknowledgment/dispute evidence keyed to each release, with current recipient-only self-acknowledgment and explicitly attributed custodian paper recording. Acknowledgment must not change stock, issued projections or immutable release headers/lines.

Print the attached request form's original fields with labeled approval/partial-release supplements. Keep each actual release number/date/quantity visible; do not merge releases into one issue date or invent a signature. Alternate recipients have release-specific access; preserve that boundary in print/acknowledgment routes rather than granting unrestricted request access.

S3.3 corrections must reference immutable `supply_issue_line` and its movement. Effective-issued projections currently increase only with posted issue quantities; later genuine returns must not decrease them, while erroneous reversal must explicitly reconcile reopened/cancelled demand. Continue using reservation versions and request revision to prevent stale handovers/cancellations, and run the existing allocator with all quantity mutations in the same transaction.

Recovery: disable Supplies writes to stop further handovers while retaining authorized release/history reads. Retry the original operation key after an interrupted response; do not create a new handover just to recover its response. Never delete/edit a posted release, reset the ISS sequence or manually restore stock. Erroneous committed handovers require the planned S3.3 correction workflow. This increment records handover only; recipient acknowledgment and printing remain S3.2.
