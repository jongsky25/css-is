# S2.1 — Draft, submit and track supply requests

Date: October 21, 2026 (Asia/Manila). Status: **Verified locally**. Prerequisite: [S1.4](SUPPLIES_MANAGEMENT_S1_4.md). Parent: [implementation plan](SUPPLIES_MANAGEMENT_PLAN.md).

## Delivered

**My requests** lets staff create and edit multi-item drafts, review a saved draft, submit for approval, track status and timeline, and withdraw before approval with a reason. Drafts require a purpose and 1–20 positive whole-quantity item lines; date needed is optional. Duplicate selections of the same item combine into one validated quantity, with overflow rejected. Five item fields are initially visible; an expandable section provides the remaining fifteen.

The account's current directory linkage supplies the requester and organizational unit. Form fields cannot override either. Creating/saving a draft and first submission require an active account linked to current, unarchived internal staff with an existing unit. Submission reloads this linkage, so directory changes since drafting are captured in the submitted snapshot. Other active owners can continue reading their existing history after linkage changes; inactive accounts cannot access it.

Only the owner can read or mutate a request in this increment. Technical administrator, custodian and other business-role grants do not confer request content access. My requests paginates at 25 and lists only the signed-in owner's records. S2.2 will introduce scoped approver access and its inbox.

Submission assigns `SUP-YYYY-NNNNN` using the local calendar year, persists immutable header/line snapshots, advances both the optimistic record revision and submitted revision, and appends audit/timeline events in the same transaction. Drafts consume no control number. Numbers never wrap after 99,999. An identical authorized retry returns the original result, and a different operation against an already submitted request cannot create another submission/number.

A missing eligible approver shows a clear routing warning while the request remains submitted. Routing checks current active accounts, unrevoked request-approver grants and unit ancestry, excluding the owner; sibling paths such as `TEST/D10` do not match `TEST/D1`. Configuration changes update this warning on the next read.

Withdrawing a draft or submitted request sets `approval_status='cancelled'`, retains any allocated number and submitted snapshots, and records the reason. Cancelled requests cannot be reopened or resubmitted. Approved requests cannot use preapproval withdrawal. Request actions do not reserve, issue or change stock.

## Implementation

- Added `supplies_requests.py` for directory eligibility, owner access, normalized drafts, numbering, immutable submission, routing status, withdrawal and reads.
- Added `supply_request`, `supply_request_draft_line`, `supply_request_revision` and `supply_request_revision_line` through the additive installer. Submitted headers/lines have update/delete protection. `revision` is the record concurrency token; `current_revision` counts immutable submissions and remains zero in drafts.
- Draft lines retain stable IDs for retained items and store catalog identity/unit snapshots. If code, description or unit changes after the draft was saved, submission requires the owner to edit/save it again to review the current item. Inactive items fail at both save and submit.
- Catalog deactivation now rejects items referenced by current submitted/returned/approved request revisions. Withdrawn requests release this guard; drafts do not block deactivation and must pass active-item validation at submission.
- Added GET list/new/detail/edit routes under `/supplies/requests`, POST create/save/submit/withdraw routes, owner-only templates, navigation and version **7.70**. All writes retain Supplies feature-flag, current-account, session-bound CSRF and existing Origin checks.
- Invalid/stale draft saves re-render submitted values safely. Stale forms retain the submitted concurrency token, preventing a silent overwrite of the newer saved request. Purpose and withdrawal reason are escaped in reports. Dates/timeline timestamps use existing human-readable date filters.
- Request writes, submission sequence, snapshots and audit share one `BEGIN IMMEDIATE` transaction. No request operation calls stock posting helpers or creates reservations.

## Verification

A relevant regression run passed **469 cases**: the first 27 S2.1 cases plus all 442 existing Supplies and selected repository regression cases:

```bash
/workspace/scratch/supplies-venv/bin/python -m pytest tests/test_supplies_requests.py tests/test_supplies_import_review.py tests/test_supplies_import.py tests/test_supplies.py tests/test_supplies_stock.py tests/test_work.py tests/test_browser_security.py tests/test_dependency_gates.py tests/test_backups.py tests/test_auth_rbac.py tests/test_phase0_security.py -q
```

The final focused request suite passed all **32 S2.1 cases**, including five additional tests for the complete multipart form, safe validation/stale-form preservation, pagination/reinstallation, conflicting keys/withdrawal rollback and approved-state withdrawal protection. **474 distinct relevant cases passed across these runs.** The existing Starlette/httpx TestClient deprecation remains the only warning; dependency locks were not changed. The full repository runner remains scheduled for S6.2.

Tests verify:

- Combined duplicate quantities and stable retained draft-line IDs; create/edit/submit/retry and unchanged ledger over a posted opening of 10.
- Owner-only reads/listing/edits/submission/withdrawal, including administrator/custodian and unrelated linked staff accounts.
- Reloaded directory linkage, external/archived/unlinked/unitless staff rejection, inactive accounts and forged account attributes.
- Current directory snapshots on submission and immutable requester/unit/item evidence after later directory/catalog changes.
- Missing purpose, invalid date, empty/excessive lines, zero/fractional/boolean quantities and combined overflow.
- Inactive catalog items and changed units requiring explicit draft review.
- Open obligation deactivation protection; cancelled/draft behavior; stale tokens; submission/withdrawal replay and conflicting operation keys.
- Current approver hierarchy, owner exclusion, revocation, disabled writes and readable history.
- Number uniqueness, competing connections, annual exhaustion and rollback of numbering/snapshots on audit failure.
- Real HTTP owner isolation, CSRF/Origin rejection, ignored forged requester/unit fields, safe HTML escaping, preserved invalid/stale form values, full 20-line multipart forms, list pagination and repeated installation/foreign-key integrity.

Dependency-lock input checks, module compilation and `git diff --check` passed.

### Browser → draft → submission → database → response

Installed Chromium through Playwright used a temporary localhost Uvicorn server, disposable SQLite database and registered synthetic sessions:

1. A linked staff account opened My requests and created a draft with two paper entries (3 + 2 Ream) and a second item (8 Piece).
2. The saved draft combined paper into 5 Ream. The owner edited/saved its purpose, then reviewed and submitted it.
3. Exactly one `SUP-2026-00001` and one immutable revision with two lines were persisted. Replaying the original submission POST consumed no additional number or revision.
4. The detail page showed the missing-approver warning and human-readable timeline. Another staff account received 404 for the detail and could not see its purpose in My requests.
5. The owner withdrew with a reason; the request became cancelled and retained its submitted evidence and timeline.
6. The ledger rows remained identical to the initial 10-Ream opening. Foreign keys were valid, no browser page errors occurred, and form/detail pages fit a 390px viewport with tables scrolling inside labeled regions. The mobile detail screenshot was visually inspected.

Synthetic screenshots:

- [Mobile draft form](evidence/supplies-s2-1/draft-form-mobile.png)
- [Mobile submitted request](evidence/supplies-s2-1/submitted-mobile.png)
- [Desktop submitted request](evidence/supplies-s2-1/submitted-desktop.png)
- [Withdrawn request](evidence/supplies-s2-1/withdrawn-desktop.png)

Temporary walkthrough helper: `/workspace/scratch/verify_supplies_requests_browser.py`. No production request, operational grant, stock import or deployment was performed.

## Handoff and recovery

**Next increment: S2.2 — Approval decisions and initial reservation.** Add current scoped approver visibility/inbox, self-approval prevention, immutable decisions for the exact submitted revision, reduced quantities with reasons, return/reject, returned editing/resubmission and the shared oldest-first allocator. Approval must leave physical on-hand unchanged.

Use `revision` for concurrent edits/actions and `current_revision` to locate the submitted snapshot. Resolve approvers against the snapshotted submitted `unit_id`, never the owner's later directory unit. Recheck active item identity/unit before approving demand against current catalog units.

Before enabling returned-request editing, extend `_write_lines` to retain IDs referenced by old immutable revisions when an item is removed; it currently deletes removed lines only in never-submitted drafts. Allow returned editing/resubmission without overwriting old revision headers/lines, keep the existing control number and append the next submitted revision. Add returned withdrawal support alongside that workflow. Returned, rejected and approved states exist as schema foundations but have no transition endpoint in S2.1.

S2.3/S3.1 must refine the approved-item deactivation guard to check remaining unfulfilled obligations once cancellation/issuance exists. S5.1 must also include open replenishment obligations. Do not weaken submitted/returned obligations or infer their completion from stock totals.

Recovery: disable Supplies writes while preserving owner history reads. Additive request/revision tables may remain after a code rollback; do not delete submitted evidence or reset/reuse allocated control numbers. This increment changes no physical stock and requires no stock reversal to recover.
