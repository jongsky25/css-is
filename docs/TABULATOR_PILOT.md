# Tabulator document register pilot

The document register offers an optional interactive table. Open `/documents`, then choose **Interactive table**. Sorting and workflow/verification/deadline filters apply to all permitted records matching the current queue and search. Each request retrieves at most 30 rows. Column resizing and visibility affect the current view. The table body scrolls within a bounded height so headings and pagination remain available.

The standard table is the initial view and remains available through **Standard table**. Missing JavaScript or vendor files leave that view usable. A failed table request clears the interactive view and restores the standard table with a retry message. Reload to refresh the standard table's snapshot.

## Saved views and deadlines

In the interactive table, expand **My saved views**, enter a name and choose **Save new view**. Each account can keep ten named views. A view retains the queue, search, applied workflow/verification/deadline filters, sorting, visible columns and widths. **Update selected view** replaces its settings or changes its name; **Delete selected view** removes the preference without changing the current table or any documents. **Reset table** restores default filters and columns for the current queue/search without deleting saved views.

Saving puts the view ID in the page URL, so reloading restores it. Choose a saved view and **Open view** to reopen it on another device. Opening starts at page one and checks current document access; sharing the URL does not share the view or its records. Preferences live in the account-owned `document_registry_view` table, with no record snapshots or browser storage. Writes require the session's CSRF token, and stale revisions return 409 instead of overwriting another tab's changes. The GET/POST `/documents/grid-views` responses use `no-store`.

Both table modes label active documents **Overdue** before today, **Due today**, **Due soon** through three working days after today, or **Unknown deadline**. Working days exclude weekends and configured holidays. Closed and cancelled records have no deadline alert. Labels accompany color; existing date rules, measures, escalation cutoffs and exports retain their behavior. Labels refresh when records are fetched, including on a reload, sort or page change.

The **Deadline** filter offers **Overdue**, **Due today**, **Due soon (including today)** and **Unknown deadline**. Choose a deadline and **Apply filters**; it combines with the queue, search, workflow and verification before counting and pagination. Due soon includes today through the next three working days, matching the register measure. Urgency filters exclude closed/cancelled records, and missing or malformed dates count as unknown. Saved views retain this choice; older views without a deadline option open with **All deadlines**. No schema migration is needed. The current date and holiday window are fixed once per grid request, so filtering and badges agree.

## Lead and deadline date ranges

Use **Assigned lead** to choose a person or **Unresolved**, then optionally set **Due from** and **Due through** and choose **Apply filters**. Both endpoints are inclusive; either bound can be used alone. These are deadline dates, not registration dates. Missing or invalid deadlines do not match a date bound. Closed/cancelled records can match the date range when the selected queue/workflow permits them; deadline urgency filters retain their existing exclusions.

Lead choices come only from records in the authorized queue/search, including inactive people with historical assignments. Reload to refresh the choices. A saved lead that no longer appears stays selected as **Saved lead (no matching records)**; the server still applies its ID and current access rather than broadening to all leads. Options and date validation grant no document access. Saved views retain the lead and fixed date bounds; older views default to all leads and no date bounds, with no database migration.

The shared server query applies these filters before counts, pagination, sorting and current-view CSV export. The standard table, full-register measures and original CSV above it retain their queue/search scope. Reversed or invalid ranges are rejected, and Reset table clears the lead/date choices without deleting saved views.

## Group by workflow or assigned lead

Choose **Group by → Workflow** or **Assigned lead**, then **Apply filters**. The server groups the full authorized queue/search after all applied filters, before slicing it into 30-record pages. Groups appear alphabetically, with the selected sort inside each group. The summary lists counts across all matching pages; each table group header distinguishes that total from the records on the current page. A group can continue on the next page. Group headers stay expanded; paging remains the way to browse large groups.

Lead groups use account IDs, including inactive historical assignees, and collect missing or dangling assignments under Unresolved. Labels are displayed as text. Counts, page records and export selection recheck current access; no record snapshot is stored in a preference. Saved views retain grouping, while older views default to no grouping without rewriting their stored JSON. Reset table clears grouping. Unapplied choices do not affect the displayed groups or export.

Grouped current-view CSV downloads place a **Group: Workflow** or **Group: Assigned lead** column first and keep group order across all pages, even if the corresponding display column is hidden. The normal 10,000-record bound and formula escaping apply. The separate full-register export retains its existing behavior.

## Export the current view

Choose **Export current view (CSV)** in the interactive table. The download uses the applied queue/search, workflow, verification and deadline filters, current sorting and visible columns across **all matching pages**. Unapplied form choices do not change it. A saved view restores these settings before export; the export itself creates no preferences or document changes.

The server rechecks current authorization in a fresh snapshot and shares the grid's validated query and stable ordering. CSV includes primary field values, friendly workflow/verification labels, ISO due dates (or Unknown), and UTF-8 text with a BOM for spreadsheet compatibility. Badges, links, snippets and other secondary annotations are not additional CSV columns. Spreadsheet formulas are neutralized. At most 10,000 authorized matches can be exported; larger requests fail with a narrowing message instead of producing a truncated file. Downloads and errors use `no-store`. An export failure leaves the table available. The separate export above the interactive table retains its full queue/search scope.

## Behavior and boundaries

- Number and subject links open the existing document screen. The Number column stays visible so every row remains actionable.
- Queue and search parameters are carried into every request. Workflow, verification and deadline choices narrow the interactive table and its current-view CSV; the existing full-register measures and CSV export are explicitly labelled as covering the queue and search.
- Deadline sorts put unknown deadlines last in either direction. Every sort has a stable record-ID tie-breaker.
- The grid uses numbered pages with SQL LIMIT/OFFSET after permission, search and state filtering. Concurrent additions or changes can move rows between numbered pages; refresh to see the latest register. Requests clamp a page removed by deletion or permission changes to the current last page.
- Existing keyset pagination remains unchanged for the standard view.
- No editing, bulk mutations or persistent browser storage are enabled. Current-view CSV export is generated server-side. Browser controls do not grant authority; each data request rebuilds the current registry scope.
- The read-only `/documents/grid-data` route returns a display-field projection with `Cache-Control: no-store`. Existing registry logic supplies authorized FTS snippets, including indexed-file access checks.
- Plain-text/DOM formatters keep subjects, names and excerpts from becoming executable markup.

## Files and dependency

- `documents_grid.py`: validated options and bounded reads over `documents_registry.Selection`.
- `static/js/document-registry.js` and `static/css/document-registry.css`: optional view, remote ordering/filtering, columns and failure recovery.
- `templates/documents/index.html`: entry point and standard-table fallback.
- `static/vendor/tabulator/`: unmodified npm 6.7.1 distribution and MIT license.
- `docs/dependencies/tabulator-manifest.json`: npm archive integrity and hashes of shipped assets.
- `scripts/check_vendor_dependencies.py`: verifies both PDF.js and Tabulator and audits both when `--audit-output` is supplied. The extra audit receipt uses the `-tabulator.json` suffix.

## Verification

Run the focused registry, route and browser checks:

```sh
python -m pytest tests/test_document_registry_groups.py tests/test_document_registry_lead_dates.py tests/test_document_registry_export.py tests/test_document_registry_views.py tests/test_document_registry_grid.py tests/test_document_registry_grid_browser.py tests/test_document_registry_pagination.py tests/test_document_registry_sqlite_compat.py tests/test_documents_routes.py tests/test_vendor_dependency_gate.py
python scripts/check_vendor_dependencies.py
node --check static/js/document-registry.js
```

The broader research and catalogs are preserved in [research PR #423](https://github.com/jongsky25/css-is/pull/423). This pilot is the first implementation selected by the user. Its review/deployment status should be checked in its implementation PR before continuing to another module.
