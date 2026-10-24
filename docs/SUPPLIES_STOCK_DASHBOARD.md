# Supplies stock dashboard

Open **Supplies → Stock dashboard**, or **Stock dashboard for this catalog search** above Supply catalog. Choose search, unit and catalog status, then **Refresh dashboard**. The two ECharts panels count matching catalog items across every page; quantities in different units are never added together. Interactive inventory draft/saved filters do not change this dashboard scope.

**Physical stock** uses the existing ledger classifier: unrecorded, out of stock, critical, normal, or inactive. **Availability after reservations** uses the same ledger/reservation totals as the interactive inventory: unrecorded, out of stock, fully reserved, low available, available, or inactive. Unrecorded stock is not a confirmed zero, and equality with the critical level is not low. Inactive items retain their separate state.

Select a chart bar or linked count label to open the exact matching interactive inventory and current-view CSV. Search, unit and active/inactive scope are preserved. The linked catalog also renders the filtered table, CSV and 30-item pagination on the server when scripts or vendor assets fail. Retry retains filters; restored assets keep the requested page. Reset returns to the initial catalog search and active/inactive scope, removing chart filters from the URL. Existing private inventory views can save the applied settings.

## Below-critical list

The dashboard lists **recorded active items whose on-hand quantity is strictly below their critical level**, with code/description, unit, on hand, reserved, available, critical and target quantities. Unknown and inactive stock are excluded. A confirmed zero with a zero critical level is out of stock but not below threshold. Availability shortages remain separate: stock can be physically normal but fully reserved or low available.

The list is server-paginated in 30-item pages, with a full matching count and stable code/ID ordering. Item links open the existing detail screen. Existing target settings are displayed without inventing a purchase quantity or replenishment recommendation. Unset targets remain **Not set**. Quantities remain exact decimal strings; no browser number conversion is used for those values.

## Access and implementation

All active staff retain their existing active-catalog access. Including inactive items or viewing inactive-only scope requires a current custodian/auditor grant; technical administrators do not receive that access implicitly. Each dashboard, linked inventory page and export rebuilds current authority. Reads remain available when Supplies changes are disabled. Scope is shown with a snapshot timestamp; counts can change before a subsequent link/request.

`supplies_stock_dashboard.report` reuses `supplies_grid.selected_query` in one read snapshot for both chart aggregates and the bounded below-critical list/count. It uses the existing classifier and reservation semantics without stock writes, notice projection, preferences created by the dashboard, schema changes. The optional presentation export adds only the locally vendored browser libraries described below. Only aggregate states/counts/links are embedded in chart JSON. Item details are limited to the current server list page. No stock quantities are summed across unlike units.

The dashboard reuses locally vendored ECharts 6.1.0 and its existing hash/provenance/advisory gates. It renders SVG without HTML tooltips or animation. Always-visible linked HTML count tables provide keyboard/print access and survive rendering/asset failure. Labels are text, layouts resize, cached history navigation refreshes the dashboard, and dashboard/linked responses use `no-store`. Existing inventory reports, stock ledger, catalog forms, reservations and replenishment flows keep their established behavior.

## Verification

```sh
CSS_TEST_NOW=2026-10-20T06:00:00 python -m pytest tests/test_supplies_stock_dashboard.py tests/test_supplies_stock_dashboard_browser.py tests/test_supplies_grid.py tests/test_supplies_grid_browser.py tests/test_deploy_hf.py
node --check static/js/supplies-stock-dashboard.js
node --check static/js/supplies-grid.js
python scripts/check_vendor_dependencies.py
```

Coverage includes classifier boundaries, unknown/zero stock, strict thresholds, real reservations, search/unit/catalog scopes, every nonzero chart link against grid/CSV counts, below-critical pagination, revoked grants/accounts, no data writes, actual SVG clicks, mobile layout, safe text, failed charts/table refreshes, script-disabled filtered tables and pagination recovery when assets return.

## PowerPoint report

Select **Export PowerPoint report** to download `office-connect-supplies-stock-report.pptx`. The presentation contains a scope/date summary, two editable native PowerPoint charts and editable tables of **all** matching below-critical items, including subsequent dashboard pages. Table headings repeat on continuation slides. Quantities remain exact strings and unset targets appear as **Not set**. No quantities are summed across different units and targets do not become purchase recommendations.

The export uses the **applied** dashboard search, unit and catalog status. Edit filters and select **Refresh dashboard** to apply them before exporting. Every export reads a fresh authorized snapshot, so quantities can differ from an older displayed page. Permission revocation or account deactivation takes effect on the new request. Snapshot responses and errors use `no-store`.

Exports allow at most **1,000 below-critical items**. Larger lists return an explicit instruction to narrow filters; they are never silently truncated. Empty results still produce a report explaining the empty scope. JavaScript and export libraries are required; failed requests/assets show a retry message while dashboard tables remain usable. All generation occurs locally in the browser without uploading records to an external converter.

`/supplies/stock-dashboard/presentation-data` reuses the same `report`/`selected_query` authority and snapshot as the dashboard, with a bounded complete below-critical list instead of page-size rows. PptxGenJS 4.0.1 and JSZip 3.10.1 browser distributions are locally vendored and pinned with SHA-512 archive provenance, SHA-256 file checks, license texts and npm advisory checks for every embedded browser dependency. No schema, stock mutations, new Python dependencies or notification processing are introduced.

Browser verification downloads real PPTX archives, parses every OOXML relationship/XML part, checks both editable chart caches and embedded XLSX workbooks, confirms all-page native tables, fresh stock changes and applied-filter behavior, and exercises empty results, mobile layout, failed assets/requests and revoked grants.
