# Dashboard PDF reports

Open **Supplies → Stock dashboard** or **Documents → Workload dashboard**, apply the desired dashboard filters with **Refresh dashboard**, then select **Export PDF report**. Downloads work with JavaScript disabled. Draft filter edits do not change the link's applied scope. Every download reads a fresh authorized snapshot, so current counts may differ from an older displayed page.

The standalone landscape A4 PDFs contain selectable text, embedded DejaVu fonts, vector bar charts, complete count tables, the applied filters and a snapshot timestamp. Tables wrap long labels and repeat headings on continuation pages. Every page has a snapshot/footer and page number. Long chart labels may be shortened; complete tables preserve full labels.

## Report scopes

**Supplies:** physical-stock and availability charts/counts cover all matching catalog pages. The below-critical table includes every matching recorded active item strictly below critical, with code/description, unit, on hand, reserved, available, critical and target quantities. Values remain exact strings; unset targets remain **Not set**. Unknown stock differs from zero, threshold equality is not low, inactive items remain separate, and quantities across unlike units are not summed. Targets are existing settings, not purchase recommendations. More than **1,000 below-critical items** requires narrowing filters rather than truncating. Including inactive items requires a current custodian/auditor grant.

**Documents:** workflow and deadline charts/counts cover every permitted match in the applied queue/search. The lead chart explicitly shows the largest 20 groups and full group count; complete tables retain every group, including Unresolved and inactive historical leads. Counts describe documents, not individual contributions/performance. Date boundaries reuse existing working-day/holiday, invalid-date and closed/cancelled semantics. No document subjects, bodies, snippets, attachments or record lists enter the report. Director-only instruction scope is rechecked and ignores search as in the dashboard. More than **1,000 lead groups** requires narrowing the scope rather than truncating.

Both use the same bounded complete snapshot mode as their PowerPoint reports. Empty scopes still produce PDFs. Success/error responses use `no-store`; a refused export returns an accessible error page with links to return or reset filters, without a partial attachment. Reads remain available when module changes are disabled. No schema change, business write, preference write or external conversion request is introduced.

## ReportLab versus Gotenberg

| Option | Fit for these reports | Decision |
| --- | --- | --- |
| Existing ReportLab 5.0.1 and installed DejaVu fonts | Already deployed; supports vector charts, selectable text, wrapping/repeated tables and direct authenticated downloads from structured snapshots. | Use for both dashboard PDFs. No new dependency or service. |
| Gotenberg | Useful for browser-faithful HTML/CSS rendering and Office-file conversion; requires an additional container/service, resource limits and protected network access. | Defer until those conversion/fidelity capabilities are needed. |

`dashboard_pdf.py` renders only already-authorized report data. Paragraph text is escaped, chart labels are plain text, and no HTML, images, URLs or attachments are fetched for conversion. The existing report helpers supply all classifications and access decisions; PDF routes share their export bounds. The module is included in `deploy_hf.RUNTIME_PY`.

## CI correction delivered first

The outside-activity QR test previously searched all HTML for `/e/`. Random PNG base64 could contain that sequence and falsely fail a deployment. It now parses actual anchor destinations, verifies the `/seq` token link and rejects real `/e/` paths. A deterministic embedded-image payload containing `/e/` exercises the previous failure on every run. The separate public link-tree 404 check remains intact. This test-only correction was committed before PDF implementation.

## Verification

```sh
CSS_TEST_CHROMIUM=/usr/bin/chromium CSS_TEST_NOW=2026-10-20T06:00:00 python -m pytest tests/test_dashboard_pdf.py tests/test_dashboard_pdf_browser.py tests/test_outside_activity.py::test_outside_combined_qr_is_sequence_not_link_tree tests/test_outside_activity.py::test_link_tree_404s_for_outside_event tests/test_documents_presentation_browser.py tests/test_supplies_stock_presentation_browser.py tests/test_deploy_hf.py
```

Coverage inspects actual PDF text/pages and Unicode/markup labels, complete multi-page lists and lead tables beyond chart limits, snapshots from authorized source data, no writes, fresh stock/access changes, applied versus draft scope, script-disabled downloads, disabled-module reads, current/revoked grants, bounded refusal/errors, and existing PowerPoint exports.
