# Interactive Supplies inventory

Open **Supplies → Supply catalog → Interactive inventory**. The standard catalog remains the initial view. This pilot uses the existing vendored Tabulator 6.7.1 build and makes no stock or catalog edits.

Search item codes/descriptions and combine **Unit filter**, **Physical stock filter**, **Availability filter**, and **Catalog status filter**, then choose **Apply filters**. Sorting, counting and filtering cover the complete matching catalog before 30-item pagination. The keyboard-accessible **Inventory sort** control and column headers both sort remotely. Code links open the existing item screen; Code remains visible. Other columns can be hidden or resized. The table has a bounded scroll area and mobile controls.

## Stock meaning and access

Physical stock is the immutable ledger total. Available stock subtracts existing reservations. This table calls the same classifier used by catalog warnings: a confirmed zero is **Out of stock**, positive physical stock below the critical level is **Critical**, zero availability with positive physical stock is **Fully reserved**, and positive availability below the critical level is **Low available**. Equality with the critical level is not low. Unposted items remain **Stock not recorded**, with unknown on-hand/reserved/available cells rather than confirmed zeros. Missing quantities and unset targets sort last in both directions. Quantities are sorted as SQLite integers and transmitted as decimal strings to preserve exact totals beyond JavaScript's safe-integer limit.

All active staff can read active catalog items, as in the existing catalog/item screens. **Include inactive items** and **Inactive items only** require a current custodian or auditor grant. A technical administrator role alone does not grant inactive stock access. Each page, export and saved-view write rechecks current identity and scope. A previously saved inactive scope fails after grant revocation; it does not silently broaden or reveal inactive records. Reads and preferences remain available when Supplies changes are disabled.

There is no category field in the current catalog, so the pilot filters existing units and stock states. Adding categories is a separate enhancement. Critical and target levels keep their current business meaning; no new reorder calculation is introduced. Existing operational inventory reports, workbook downloads, notices, receipts, requests, reservations, stock ledger and replenishment flows retain their established behavior.

## Private saved views

Expand **My inventory views**, enter a name, then choose **Save new view**. An account can keep ten personal views. They retain the applied search/filters, sort, visible columns and widths. Unapplied control changes are excluded. **Update selected view** updates settings/name; **Delete selected view** removes the preference. The view ID is placed in the URL for reload and **Open view** restores it at page one, checking current access. Sharing a URL does not share a view or stock access. A saved unit that no longer appears remains selected without broadening the filter.

Preferences live in the additive `supply_inventory_view` table, separate from document views and stock operations. They contain settings, never stock snapshots. Writes require the session's Supplies CSRF token, owner identity and current revision. Stale updates return 409; other users cannot update/delete a view. IDs are not reused after deletion. Preference transactions do not invoke stock-notice processing. **Reset table** restores the initial catalog page's search and active/inactive scope, default columns/sort and unrestricted unit/state filters without deleting views.

## Current-view export and fallback

**Export current inventory (CSV)** exports every matching page, in the applied sort order, with only visible columns. CSV includes friendly status labels, exact quantities, explicit unknown/unset values and a UTF-8 BOM. Spreadsheet formula text is neutralized. The server reads a fresh authorized snapshot using the same selection and ordering as the table. More than 10,000 matches returns a narrowing error instead of a partial export. An export error leaves the table available to retry. Inventory APIs and errors use `no-store`.

If JavaScript/vendor assets are unavailable, the standard catalog remains usable. A failed or expired data request removes stale interactive rows and restores the standard table; reload to refresh that snapshot. Stock/catalog editing continues through the existing forms and detail screens.

## Verification

```sh
CSS_TEST_NOW=2026-10-20T06:00:00 python -m pytest tests/test_supplies_grid.py tests/test_supplies_grid_browser.py tests/test_supplies.py tests/test_supplies_stock.py tests/test_supplies_notify.py tests/test_supplies_reports.py tests/test_deploy_hf.py
node --check static/js/supplies-grid.js
python scripts/check_vendor_dependencies.py
```

Domain/HTTP checks cover filters before pagination, exact numeric ordering/transport, classifier boundaries, reservations, active accounts and live grants, CSV scope/columns/formulas/limits, private preferences, quotas, stale revisions, repeated schema installation, CSRF/body bounds, no-store responses and unchanged stock records. Chromium checks use the actual vendored build and authenticated routes for saved-view reload, all-page CSV, draft controls, columns, mobile layout, unknown/zero stock, inactive access revocation, failure recovery and missing-vendor fallback.
