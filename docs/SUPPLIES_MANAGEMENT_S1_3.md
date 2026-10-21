# S1.3 — Spreadsheet preview and reconciliation evidence

Date: October 21, 2026 (Asia/Manila). Status: **Verified locally**. Prerequisite: [S1.2](SUPPLIES_MANAGEMENT_S1_2.md). Parent: [implementation plan](SUPPLIES_MANAGEMENT_PLAN.md).

## Delivered

**Workbook previews** is available to current custodians and auditors. A custodian can upload an XLSX stock workbook while Supplies changes are enabled; auditors can inspect saved previews without uploading. Ordinary staff and technical administrators without a stock-reading grant cannot read previews. Disabling changes preserves authorized reads.

The preview compares four distinct pieces of evidence for every summary item:

1. Saved summary balance.
2. Saved balance in the directly referenced card cell.
3. Saved balance on the last meaningful card row, ignoring prefilled formulas on blank transaction rows.
4. Independently calculated literal opening + receipts − issues, when the source is unambiguous.

Differences in item names/units, missing or invalid cached values, conditional/period-filtered totals, broken balance chains, unsupported formulas, invalid movement dates/quantities, duplicate names and unmapped sheets become explicit review findings. Source cell addresses, formulas as inert text, saved values and transaction evidence remain available in an expandable evidence view. No formulas, macros, hyperlinks or external references are executed/followed.

Saved previews retain source SHA-256, normalized basename, summary sheet/row coordinates, diagnostics and extracted original values. They do not retain the uploaded binary, recipient names or unrelated supplier/recipient card fields. Source evidence is immutable; future reconciliation choices must be stored separately.

**No inventory is changed by preview.** There is no apply/reconcile-posting action in S1.3. Actual mapping, physical-count acceptance, exclusions and atomic opening import belong to S1.4. All uploaded values remain evidence requiring review; matching numerical caches do not establish current physical stock.

## Implementation

- Added `supplies_import.py`: bounded archive/XML checks, supported-template parsing, independent arithmetic and staged-preview/read services.
- Added `supply_import_batch` and `supply_import_row` through the existing additive installer. Source fields cannot be updated or deleted. The batch has a revision/status foundation for later review; all batches created here stay `preview`.
- Added GET `/supplies/import`, GET `/supplies/import/{id}`, and POST `/supplies/import/preview`, with independent role checks, session-bound CSRF, the existing origin protection and audited idempotency keys. A repeated identical upload/key returns its original preview, not another batch.
- Upload size is bounded while reading the request stream, including requests with no reliable Content-Length. Uploaded file handles close after reading. Parsing runs in a worker thread that owns its SQLite connection, outside the short write transaction. Account/grants and the feature flag are checked before parsing and again before persisting, so revocation/disable during parsing cannot publish a preview.
- Added upload/history and preview templates, scoped responsive styling, navigation, and tests. `version.py` records **7.68** and a plain-language preview release note. No dependencies, public endpoints, new CSRF exemptions or external services were added.

### Supported profile and limits

The initial profile follows the supplied workbook: one summary header with ARTICLE, UNIT OF MEASURE and BALANCE in columns A/F/I; critical values in P; stock-card DATE/RECEIVED/ISSUED/BALANCE in A/B/D/F, with UNIT and NAME OF ITEM labels. Direct local F-cell references support quoted sheet names, escaped apostrophes and case-insensitive sheet lookup. Unknown summary layouts fail clearly; unsupported card/formula layouts remain review findings rather than guessed imports.

Limits: 8 MiB upload/evidence, 32 MiB expanded archive, 4 MiB per archive part, 1,024 archive members, 150 sheets, 2,000 rows/32 columns per sheet, 300,000 populated/rectangular-area cells, 500 summary item rows, and 4,000 characters per cell/formula. Reject encrypted/macro-enabled files, duplicate/traversing archive members, malformed XML and document-type/entity declarations. XML must be UTF-8-compatible; UTF-16/null-containing XML is rejected before loading. External relationships are reported but never followed. No files are extracted from the archive.

Only literal nonnegative whole quantities are used in independent arithmetic. Formula strings are recognized for comparison only; no expression evaluator is used. An unknown opening, formula-valued movement, invalid date or invalid/negative/out-of-range arithmetic suppresses the independent result and requires reconciliation. A spreadsheet error such as `#VALUE!` is preserved as evidence, never converted into a stock number.

Preview item/history lists paginate at 25. No names or units are automatically merged/converted. An unnamed row with quantity/unit evidence remains visible for review. An otherwise blank card row with a prefilled balance formula is ignored even if its saved value is nonempty.

## Verification

```bash
/workspace/scratch/supplies-venv/bin/python -m pytest tests/test_supplies_import.py tests/test_supplies.py tests/test_supplies_stock.py tests/test_work.py tests/test_browser_security.py tests/test_dependency_gates.py tests/test_backups.py tests/test_auth_rbac.py tests/test_phase0_security.py
```

**426 passed, 1 warning in 38.10s:** 29 new preview cases, 55 existing Supplies cases and 342 existing regression cases. The warning is the previously recorded Starlette/httpx TestClient deprecation. A focused run of `tests/test_supplies_import.py` also passed all 29 cases.

Coverage includes monthly totals versus latest/arithmetic values; stale/missing/error caches; trailing formulas with a misleading saved value; unit differences; gaps; unsupported/formula-valued openings; quoted/case-insensitive sheet references; external hyperlinks; invalid ZIP/XML/entities/macros; size/worksheet/cell/text limits; unknown layouts; blank item identities; preview pagination and HTML escaping; immutable source evidence; repeated installation; exact retry/conflicting key behavior; audit rollback; current/revoked/disabled authority, including changes during parsing; bounded chunked uploads; HTTP CSRF/origin checks; an absent apply route; and unchanged catalog/receipt/ledger rows after staging a preview over an existing stock balance.

Additional checks: dependency-lock inputs remain current; Supplies modules compile; `git diff --check` passes. No lockfile changed. The complete repository runner remains scheduled for S6.2.

### Supplied workbook verification

Read the actual uploaded `Updated-Stock-Card.xlsx`, then staged it using the same service in a disposable database with a synthetic reviewer. The source hash matched `62e174bdba692ec37d1c9e8d18ff074d3e7de67899b6d17dec773168df378c9d`.

- **100 sheets, 99 summary items, 99 associated cards**, with no unmapped sheets.
- **12 summary/card unit differences** and **41 description differences** requiring identity/unit review. These are findings, not decisions to merge or convert items.
- All **99 summary references** point to separate conditional/period-filtered total rows, rather than the last meaningful dated balance row.
- **16 summary/latest-cache differences** and **17 summary/independent-arithmetic differences**. A difference can reflect an intentional selected period; it is not automatically labeled an incorrect historical record.
- One balance-chain gap with a missing/invalid saved card value, and three zero critical levels.
- **Zero item, stock movement, receipt or receipt-line records** were created in that disposable database; foreign-key checks passed. Only preview evidence and its configuration/audit records were staged.

The disposable database was removed after verification. The real workbook, its per-item balances and transaction names are not committed as fixtures or screenshots. These aggregate findings do not validate a physical count or authorize adoption as current stock.

### Browser → upload → parser → database → response

Used installed Chromium through Playwright against a temporary localhost Uvicorn server, lifespan jobs disabled, a synthetic workbook and registered synthetic sessions:

1. Custodian uploaded a workbook through the real multipart form and followed the redirect to saved evidence.
2. The preview displayed balances 10 / 10 / 15 / 15 and the deliberate Ream-versus-Pack difference.
3. Source details expanded to show the subtotal formulas and transaction evidence as inert text.
4. At 390px viewport width, the page fit the document and comparisons scrolled within their table region.
5. Auditor could read the preview but had no upload control; ordinary staff received 403.
6. The previously posted synthetic stock balance remained **10**, with a byte-for-byte equivalent ledger-row result and no receipt created. One batch/row of preview evidence was saved, foreign keys were valid, and no browser page errors occurred.

Screenshots contain synthetic data only:

- [Desktop preview](evidence/supplies-s1-3/preview-desktop.png)
- [Phone preview](evidence/supplies-s1-3/preview-mobile.png)

Temporary walkthrough helper: `/workspace/scratch/verify_supplies_import_browser.py`. Service/HTTP tests and screenshots preserve reviewable evidence independently of that temporary script.

## Handoff and recovery

**Next eligible increment: S1.4 — Reviewed opening import.** Add explicit item/unit mapping, accepted physical quantities and count/cutoff date, threshold review, reconciliation reasons and exclusions. Preserve `raw_json`/metadata as immutable source evidence. Do not clear warnings or overwrite source values to represent a reviewer decision.

Apply the finalized selection in **one outer transaction**. Factor transaction-neutral opening-validation/ledger helpers from the current stock service; do not nest public transaction-owning `post_opening` calls. Recheck current authority, batch revision, source selection and populated item ledgers before any posting. Guard source/batch replay and existing opening/movement records, and retain an excluded-row report. No future import may simply adopt a saved formula cache as an accepted physical quantity.

Current staging fields are `supply_import_batch(source_sha256, filename, sheet_count, metadata_json, status, revision, created_by, created_at, operation_key)` and `supply_import_row(batch_id, source_sheet, source_row, raw_json)`. Add separate reviewer/mapping/acceptance fields as needed; existing triggers deliberately permit new review-field updates while blocking source-field changes.

Recovery: disable Supplies writes to stop new uploads while retaining authorized preview reads. A code rollback can leave the additive staging tables and audit evidence intact. Preview created no stock change to reverse. No deployment, real business-role configuration or live opening import was performed. No unresolved technical failure blocks S1.4.
