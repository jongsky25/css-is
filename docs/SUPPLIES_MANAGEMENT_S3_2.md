# S3.2 — Receipt acknowledgment and printable request/release

Date: October 21, 2026 (Asia/Manila). Status: **Verified locally**. Prerequisite: [S3.1](SUPPLIES_MANAGEMENT_S3_1.md). Parent: [implementation plan](SUPPLIES_MANAGEMENT_PLAN.md).

## Delivered

Each posted release starts with **Pending** acknowledgment. Its recorded recipient can acknowledge receipt or report a dispute with a reason. A dispute can be resolved by an explained recipient acknowledgment or documented paper evidence, with every prior response retained. A recipient may also dispute an earlier acknowledgment, including a paper acknowledgment. Repeating the current status under a new operation is rejected rather than silently replacing evidence.

Current custodians can separately **Record a paper acknowledgment**, supplying a paper receipt reference, acknowledgment date and evidence note. The date must be valid, nonfuture and on/after handover. Paper evidence is visibly labeled **Paper acknowledgment recorded by custodian**, with the recording actor, timestamp and reference; it is never presented as an online response by the recipient. A requester who is not the release's recipient cannot self-acknowledge it.

Acknowledgments are append-only and scoped to an individual release, independent of other partial handovers. A revision token prevents concurrent responses from overwriting each other. Current account/grants and the feature flag are checked before successful-operation replay. Acknowledgment/dispute changes no stock movements, reservations, issue records, issued totals or request quantities.

Authenticated **Print submitted request** and **Print release form** views preserve the attached form's original fields: control number, requested/issued dates, quantity, unit, item description, purpose/details, Requested by and Issued by. Printed names are labeled as recorded names, with actual signature lines left blank. No generated signature or acknowledgment is represented as a staff signature.

A labeled supplement provides approval and quantity reconciliation, actual release numbers/dates/quantities, recipients and acknowledgment evidence. Multiple handovers show **Multiple handovers — see release supplement** rather than inventing a single issue date or issuer. Full-request printing uses the immutable submitted revision, even while private returned corrections exist; a specific earlier revision may be selected. Never-submitted drafts cannot be printed as submitted forms.

Release printing remains confined to that release and its necessary submitted context. An alternate recipient can print their assigned release but cannot use that relationship to print the complete request or other releases. Current business-role and relationship-based read permissions remain enforced when writes are disabled.

## Implementation

- Added `supplies_acknowledgments.py`: recipient responses, paper recording, current-state/history reads, revision/idempotency validation and atomic audit. Pending/revision zero is derived when no evidence exists.
- Added immutable `supply_issue_acknowledgment`: issue/revision, status/method, actor snapshot/time, note, paper reference/date and operation key. A unique issue/revision and serialized write transaction admit one decision per observed version. Updates/deletes are blocked.
- Existing `supply_issue` and `supply_issue_line` remain immutable. Acknowledgment does not call stock posting, numbering or allocation helpers; audit failure rolls back the response/evidence/operation together.
- Added `supplies_print.py` for authorized, consistent-snapshot request/release print data. Request prints use immutable submitted headers/lines plus current approved/issued/cancelled/reserved/awaiting quantities. Release prints include only assigned release items and context.
- Added POST `/supplies/issues/{id}/acknowledge` and `/paper-acknowledgment`, GET `/supplies/requests/{id}/print?revision=...` and `/supplies/issues/{id}/print`. Mutations retain session-bound CSRF/Origin checks; invalid/stale forms preserve entered notes and original revision tokens.
- Release detail/list and request release links show acknowledgment status/history and allowed controls. Recipient and paper methods have separate labels/forms. Current-status transitions that would add duplicate evidence are omitted from normal controls.
- Added standalone print HTML/CSS and a self-hosted print-button script. A4 portrait uses 14mm margins, repeated table headers, wrapping long values, blank signature areas and release blocks kept together when they fit a page. Browser Print / save PDF handles printing without adding a server rendering dependency.
- Version is **7.74**. No dependencies, external services, recipient signature generation, stock corrections or acknowledgment attachments were added.

## Verification

The final relevant regression run passed **593 cases**, including **26 S3.2 cases** and the previous 567 relevant cases:

```bash
/workspace/scratch/supplies-venv/bin/python -m pytest tests/test_supplies_acknowledgments.py tests/test_supplies_issues.py tests/test_supplies_backorders.py tests/test_supplies_approvals.py tests/test_supplies_requests.py tests/test_supplies_import_review.py tests/test_supplies_import.py tests/test_supplies.py tests/test_supplies_stock.py tests/test_work.py tests/test_browser_security.py tests/test_dependency_gates.py tests/test_backups.py tests/test_auth_rbac.py tests/test_phase0_security.py -o addopts= -q
```

Coverage includes:

- Independent pending/acknowledged states per partial release, exact successful replay and unchanged stock, projection, issue and request rows.
- Dispute reasons, explained resolution and retained prior evidence; paper acknowledgment followed by a recipient dispute and documented paper resolution.
- Recipient-only self-response, including a request owner who is not the alternate recipient; assigned-release-only print access with complete-request/other-release denial.
- Attributed paper method/actor/reference, current custodian authority, required evidence and valid acknowledgment/handover chronology.
- Stale versions and changed operation intent; simultaneous recipient/paper submissions on separate SQLite connections with exactly one commit.
- Revoked/inactive/disabled mutation checks, read-only print/history access where authorized and audit rollback.
- Immutable acknowledgment evidence, repeat installation and foreign-key integrity.
- Immutable submitted print snapshots during returned corrections, printing earlier revisions after resubmission, quantity reconciliation and separate partial releases/methods.
- HTTP response/paper forms, CSRF/Origin rejection, escaped notes, safe stale-form preservation and print authorization without mutation tokens in output.

Dependency-lock input checks, compilation and `git diff --check` passed. The existing Starlette/httpx TestClient deprecation remains the only warning. The full repository runner remains scheduled for S6.2.

### Browser → response → evidence → A4 output

Installed Chromium through Playwright exercised a temporary localhost Uvicorn application, disposable SQLite database and registered synthetic sessions:

1. A recipient disputed the first 4-Ream release, then resolved it with an explanation. Both events remained visible, and exact POST replay added no duplicate response.
2. A custodian recorded signed-paper evidence for a second 2-Ream release to an alternate, with a distinct method/actor/reference/date. The requester could not act as that alternate recipient.
3. The alternate could print the assigned release but received 404 for the first release print and full-request print.
4. The request print retained original form fields, requested/approved/issued totals of **6 / 6 / 6**, the two actual release dates and the recipient-versus-paper histories.
5. The print button called browser printing. Chromium rendered actual PDFs using print CSS; `pdfinfo` verified A4 page dimensions and `pdftotext` verified fields, release separation, blank signature labels and absence of toolbar text. A stress request with 20 long descriptions and a long purpose retained its final item and repeated table headers across pages.
6. The representative release fits **1 A4 page**, the two-release request uses **2 pages**, and the long request uses **4 pages**. The PDF release, request continuation and long-table continuation were visually inspected. Phone response/history views fit 390px.
7. Stock movements, reservations, request headers and issue headers/lines remained identical before and after acknowledgment/printing. Exactly three response events were saved, foreign-key checks passed and no browser page errors occurred.

Synthetic artifacts:

- [Request A4 PDF](evidence/supplies-s3-2/request-A4.pdf)
- [Release A4 PDF](evidence/supplies-s3-2/release-A4.pdf)
- [Long request A4 PDF](evidence/supplies-s3-2/long-request-A4.pdf)
- [Recipient history on phone](evidence/supplies-s3-2/recipient-history-mobile.png)
- [Paper evidence on phone](evidence/supplies-s3-2/paper-history-mobile.png)
- [Request print view](evidence/supplies-s3-2/request-print-desktop.png)

Temporary helper: `/workspace/scratch/verify_supplies_acknowledgments_browser.py`. The attached PDF was read as form-layout reference; no source business balances, production requests, operational grants or deployment were changed.

## Handoff and recovery

**Next increment: S3.3 — Returns, stocktake differences and reversals.** Preserve immutable issue/release and acknowledgment evidence while introducing separately linked correction records. Acknowledgment/dispute alone must never reverse or adjust stock or issuance.

Genuine usable returns add physical stock without reducing effective-issued quantities or reopening original demand. Erroneous issue reversal must explicitly reconcile reopened versus cancelled remainder; cumulative returns/reversals cannot exceed original issue lines. Receipt reversal and stocktake differences must preserve stock/reservation invariants and share the existing allocator. Preserve source IDs and canonical unit snapshots.

Extend print reconciliation alongside S3.3 so correction/reversal evidence is visible beside original posted releases and effective-issued totals. Never silently rewrite the historical release quantities, recipient acknowledgment journal or original form dates to represent a correction. Record any needed new correction supplement separately.

Recovery: disable Supplies changes while retaining authorized history/print access. Retry the original response operation key after a lost response. Do not delete prior responses or mutate posted issue rows to change acknowledgment; append a valid dispute/resolution with attribution. This increment changes no physical stock, so its response recovery requires no stock reversal.
