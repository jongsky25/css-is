# Document workload dashboard

Open **Documents → Workload dashboard**, or use **Workload dashboard for this queue and search** above the register. Choose a queue/search and **Refresh dashboard**. The dashboard aggregates every matching record the current account can access, with a visible snapshot time. It counts documents, not contributions, throughput or staff performance. Draft or saved interactive-table filters do not alter this queue/search scope.

## Charts and linked counts

- **Workflow stages** uses the document's current workflow status. Zero-count stages remain visible without active drill-down links.
- **Deadlines** has five non-overlapping groups: Overdue, Due soon (including today), Later deadlines, Unknown deadline, and Closed or cancelled. Overdue is before the local calendar date. Due soon includes today through the next three working days, excluding weekends/configured holidays. Later is beyond that boundary. Missing/invalid dates are unknown; closed/cancelled records have no urgency alert. The actual date boundaries appear above the chart. The same classifier and calendar rules are used by the interactive register.
- **Workload by assigned lead** groups by current lead account ID, retaining inactive historical assignees and collecting missing/dangling assignments under Unresolved. The chart shows the 20 largest groups; the table contains every matching lead and total. Names come only from permitted matching records, not the staff directory.

Select a bar or a linked row label to open the matching document table. Queue/search are preserved and the selected workflow, deadline or lead filter is added. New **Later deadlines** and **Closed or cancelled** register options make those drill-downs exact. Links use `interactive=1` to open Tabulator automatically, but the server also renders the same filtered table and pagination for missing JavaScript/vendor assets. The server fallback offers **Export linked view (CSV)**; the interactive export shares those filters. Each new page/export rechecks current access, so counts can change after the snapshot.

A failed interactive refresh clears stale rows and restores the filtered server snapshot. Retry retains the linked filter. **Reset table** clears chart filters/URL settings and restores the current queue/search defaults. Saved views can retain the new deadline choices without a migration. Reload to refresh the server snapshot. Returning to a cached dashboard through browser history refreshes its counts.

## Accessibility, privacy and implementation

Every chart has an always-visible HTML count table with captions, row/column headings and keyboard-operable links. Charts are optional enhancements; missing vendor assets or rendering errors leave those tables usable. The charts use SVG, avoid animated transitions and HTML tooltips, display untrusted labels as text, and resize for the viewport. Lead chart labels may be shortened visually; full names remain in the table. Print uses the count tables.

`documents_dashboard.report` reuses `documents_grid.selected_query` and `documents_registry.Selection`: canonical/migrated records, aliases, queue membership, search visibility and fresh permissions retain registry semantics. All three aggregates share a SQLite read snapshot and fixed local date/working-day boundary. Only grouped counts and labels are projected; no record subjects, bodies, snippets or complete record list reaches the charts. An unexpected legacy workflow remains visible as a plain count instead of inventing a supported filter. Director-only instruction scope is checked on each request. The dashboard remains readable when Documents changes are disabled. HTML responses/errors use `no-store`; no browser storage, document write, external service call or database migration is introduced.

Apache ECharts **6.1.0** is served from `static/vendor/echarts`, not a CDN. Its unmodified npm full build includes zrender **6.1.0** and tslib **2.3.0**. Source archive SHA-512 integrity, vendored file SHA-256 hashes, dependency provenance and license files are recorded in `docs/dependencies/echarts-manifest.json`. The metadata gate verifies the complete file set; the release audit checks all three npm packages and stores a separate ECharts receipt. Upstream Apache-2.0, BSD-3-Clause, 0BSD and bundled D3 license notices are retained. Updating the distribution requires reviewing its complete dependency graph and repeating archive/file verification and all vendor audits.

## Verification

```sh
CSS_TEST_NOW=2026-10-20T06:00:00 python -m pytest tests/test_documents_dashboard.py tests/test_documents_dashboard_browser.py tests/test_document_registry_grid.py tests/test_document_registry_views.py tests/test_document_registry_grid_browser.py tests/test_vendor_dependency_gate.py tests/test_documents_routes.py tests/test_deploy_hf.py
python scripts/check_vendor_dependencies.py --audit-output /tmp/vendor-audit.json
node --check static/js/document-dashboard.js
node --check static/js/document-registry.js
```

Authority tests compare every queue/user against the independent registry reference and check each nonzero drill-down against grid/CSV counts. Coverage includes working-day boundaries, malformed/unknown dates, inactive records/leads, private leads, more than 20 lead groups, access revocation, no writes, vendor graph/hash checks and transitive advisories. Browser checks use the actual ECharts SVG/Tabulator builds and authenticated routes for bar clicks, linked tables/CSV, failed-refresh retry/reset, history navigation, mobile layout, text-only labels, failed assets, no-script pagination, response cache policy and fresh access after a change.

## PowerPoint report

Select **Export PowerPoint report** to download `office-connect-document-workload-report.pptx`. The presentation includes editable native workflow, deadline and assigned-lead charts, embedded XLSX chart data, and complete editable aggregate count tables with repeated headers and continuation slides. It includes the applied queue/search, fresh snapshot date, and the actual local date/working-day boundaries. Counts describe documents, not individual contributions or performance. No document subjects, bodies, snippets, attachments or record lists are included.

Every click reads one fresh authorized snapshot through `/documents/dashboard/presentation-data`, reusing `documents_dashboard.report` and the registry's current access selection. The **applied** dashboard scope is captured when the page loads; draft queue/search edits require **Refresh dashboard** before export. Director-only instruction scope ignores search as in the dashboard and is rechecked on each request. Success and error responses use `no-store`. The export remains a read when Documents changes are disabled.

The lead chart shows the **largest 20 groups**, explicitly labeled with the number shown and the full group count. Complete tables retain every matching group and full labels, including inactive historical leads and Unresolved. Long chart labels may be shortened; full labels remain in tables. More than **1,000 lead groups** returns an explicit instruction to narrow the queue/search instead of silently truncating. Empty scopes still generate an explanatory presentation. Zero-count workflow/deadline states remain visible in count tables. Deadline groups retain existing working-day, invalid-date and closed/cancelled semantics.

The export reuses the already vendored PptxGenJS 4.0.1 / JSZip 3.10.1 browser distributions and their hash, license, provenance and advisory gates. No new dependency, schema change, document mutation or external conversion service is introduced. Failed export assets/requests show a retry message and retain the dashboard tables. All presentation generation runs in the browser.

```sh
CSS_TEST_CHROMIUM=/usr/bin/chromium CSS_TEST_NOW=2026-10-20T06:00:00 python -m pytest tests/test_documents_presentation.py tests/test_documents_presentation_browser.py tests/test_documents_dashboard.py tests/test_documents_dashboard_browser.py
node --check static/js/document-workload-presentation.js
```

Coverage includes all queue/user authority combinations, exact aggregate totals, working-day and invalid-date boundaries, complete/refused lead-group limits, revoked record/account access, no writes, real PPTX OOXML/chart/workbook inspection, applied versus draft filters, more than 20 lead groups with complete tables, empty scopes, mobile layout, safe labels, failed assets/requests and forbidden/invalid export scopes.

## PDF report

Select **Export PDF report** for a printable snapshot with charts, complete tables, applied filters and a fresh date. Downloads also work without JavaScript. The existing PowerPoint export remains available for editable slides. See [Dashboard PDF reports](DASHBOARD_PDF_REPORTS.md) for scope, limits, access rules and the ReportLab/Gotenberg comparison.
