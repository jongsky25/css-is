# Tabulator document register pilot

The document register offers an optional interactive table. Open `/documents`, then choose **Interactive table**. Sorting and workflow/verification filters apply to all permitted records matching the current queue and search. Each request retrieves at most 30 rows. Column resizing and visibility affect the current view.

The standard table is the initial view and remains available through **Standard table**. Missing JavaScript or vendor files leave that view usable. A failed table request clears the interactive view and restores the standard table with a retry message. Reload to refresh the standard table's snapshot.

## Behavior and boundaries

- Number and subject links open the existing document screen. The Number column stays visible so every row remains actionable.
- Queue and search parameters are carried into every request. Workflow and verification choices narrow the interactive table only; the existing full-register measures and CSV export are explicitly labelled as covering the queue and search.
- Deadline sorts put unknown deadlines last in either direction. Every sort has a stable record-ID tie-breaker.
- The grid uses numbered pages with SQL LIMIT/OFFSET after permission, search and state filtering. Concurrent additions or changes can move rows between numbered pages; refresh to see the latest register. Requests clamp a page removed by deletion or permission changes to the current last page.
- Existing keyset pagination remains unchanged for the standard view.
- No editing, bulk mutations, client-side exports or persistent browser storage are enabled. Browser controls do not grant authority; each data request rebuilds the current registry scope.
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
python -m pytest tests/test_document_registry_grid.py tests/test_document_registry_grid_browser.py tests/test_document_registry_pagination.py tests/test_document_registry_sqlite_compat.py tests/test_documents_routes.py tests/test_vendor_dependency_gate.py
python scripts/check_vendor_dependencies.py
node --check static/js/document-registry.js
```

The broader research and catalogs are preserved in [research PR #423](https://github.com/jongsky25/css-is/pull/423). This pilot is the first implementation selected by the user. Its review/deployment status should be checked in its implementation PR before continuing to another module.
