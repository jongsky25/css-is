# Office Connect integration research and continuation guide

Last updated: 2026-10-24
Repository: [jongsky25/css-is](https://github.com/jongsky25/css-is)
Deployment: [equityinhealth/office-connect](https://huggingface.co/spaces/equityinhealth/office-connect)

This is the durable record of research into public Hugging Face Spaces and widely used GitHub projects that could improve Office Connect. Customer Satisfaction Survey (CSS) is one module of this platform.

The user wants a broad set of worthwhile candidates, explained and evaluated one at a time. The Tabulator registry pilot was merged in [PR #424](https://github.com/jongsky25/css-is/pull/424) as release 8.16. The saved-view and deadline-label follow-up went live as 8.18 in PR #427. Deadline quick filters from PR #430 are included in verified live v8.21. The CI time-budget fix and current-view CSV export from PR #432 are now verified live in v8.22. Lead and deadline-period filters from PR #436 are verified live in v8.25. Grouped workflow/lead views from PR #438 are verified live in v8.28. The read-only Supplies inventory from PR #440 is verified live in v8.30. The Apache ECharts document workload dashboard from PR #442 is verified live in v8.32. The ECharts Supplies stock dashboard from PR #445 is verified live in v8.34. Other candidates remain research items.

## Resume here

**Current topic: the user authorized PptxGenJS Supplies stock PowerPoint exports with “do it”. Implementation is in PR #447; full CI, merge and live deployment verification are in progress. Do not start another enhancement.**

**In progress — Supplies stock PowerPoint report:** [PR #447](https://github.com/jongsky25/css-is/pull/447), branch `feat/supplies-powerpoint-export`, head 1752657227f859f5c9f12ca59188c5c4a0307fba, currently v8.37, preserving MCP expansion v8.35 and the intervening MCP phased expansion plan v8.36 (PR #446). Exports include an applied-scope/date summary, two editable native charts and all matching below-critical items in editable paginated tables. Every click reads a fresh authorized snapshot; exact quantities and unset targets are retained. Exports refuse more than 1,000 below-critical items instead of truncating. PptxGenJS 4.0.1 and JSZip 3.10.1 plus embedded browser dependencies are locally vendored with provenance, licenses, hashes and advisory gates. Focused/browser checks and LibreOffice opening/rendering passed. The earlier v8.36 CI run 40077336981 is superseded by fresh v8.37 CI [40078317550](https://github.com/jongsky25/css-is/actions/runs/40078317550) after reconciling the intervening main release. This is not yet a deployed feature. Preserve intervening main releases and reconcile the version if another release merges first.

**Latest delivery — ECharts Supplies stock dashboard:** [PR #445](https://github.com/jongsky25/css-is/pull/445) merged as 9ccf64b32fe742ea2db3099f31e9d15de48b92db (v8.34), preserving MCP consent recovery v8.33 from PR #443. The user authorized the stock dashboard with “do it”.

Choose **Supplies → Stock dashboard**, or **Stock dashboard for this catalog search** above Supply catalog. Filter search, unit and active/inactive scope, then Refresh dashboard. Physical-stock and availability-after-reservations charts count every matching permitted catalog item across all pages. They reuse supplies_grid.selected_query and the established ledger/reservation classifier in one snapshot. Counts describe items; quantities in unlike units are never added together. Unrecorded stock stays distinct from zero, threshold equality is not low, and inactive items remain separate.

The bounded, server-paginated below-critical list shows recorded active items whose on-hand stock is strictly below their critical level, with code/description, unit, on hand, reserved, available, critical and target quantities. Unknown/inactive items are excluded, and a confirmed zero with a zero critical level is not below threshold. Availability shortages stay separate from physical stock. Existing targets are displayed without inventing purchase quantities. The full matching count and stable 30-item pages are retained; quantities remain decimal strings.

Select a real chart bar or accessible count label to open the exact inventory/CSV filter while retaining search/unit/catalog scope. Linked inventory pages also render the filtered table/export/pagination on the server when scripts or vendors fail. Retry retains filters, recovered assets retain the requested page, and Reset removes chart filters while restoring the initial catalog search/include-inactive setting. Existing private inventory views can save the applied settings. Inactive access requires a fresh custodian/auditor grant, not merely technical administrator status. Active staff retain existing active-catalog access, including read-only operation while Supplies changes are disabled. Headers/errors use no-store. The dashboard introduces no stock write, notice projection, schema change or dependency; it reuses the locally vendored ECharts build/gates. Read [the stock dashboard guide on main](https://github.com/jongsky25/css-is/blob/main/docs/SUPPLIES_STOCK_DASHBOARD.md).

**Verification:** PR workflow [40072633048](https://github.com/jongsky25/css-is/actions/runs/40072633048) passed both full 6,403-test orders with no failures/skips and all 447 offline AI cases on 510f8c83e282574b751540aac34a806f7de83022. Post-merge workflow [40074060356](https://github.com/jongsky25/css-is/actions/runs/40074060356) also passed both 6,403-test orders, every required gate and dependency/production-image/vendor audits. Deploy job 120817609229 uploaded Space commit 68f1981fa78516f4ae7928771baa0fd560e735fc, reached RUNNING and logged `Live /login version check: OK (expected v8.34)` at 2026-10-24 07:46:53 UTC. Coverage includes classifier/zero/unknown/threshold boundaries, actual reservations, every nonzero chart link against grid/CSV counts, below-critical pagination, revoked grants/accounts and no writes. Real ECharts/Tabulator browser checks cover bar clicks, mobile/text safety, CSV, retry/reset, failed charts/assets, script-disabled filtered tables and recovered page-two state. No manual action is required.

**Earlier delivery — Apache ECharts document workload dashboard:** [PR #442](https://github.com/jongsky25/css-is/pull/442) merged as b3f320957d6e9afdb49cf4f78546980eacbd8164 (v8.32), preserving the intervening MCP v8.31 release in PR #441. The user authorized the document dashboard with “do it”.

Choose **Documents → Workload dashboard**, or the register's **Workload dashboard for this queue and search** link. Workflow stages, deadline groups and assigned-lead counts cover every permitted record in the selected queue/search, independent of draft/saved interactive-grid filters. All three aggregates share the registry's Selection/current authority and one read snapshot. The charts receive grouped labels/counts, never document subjects, bodies, snippets or complete records. Lead labels come only from authorized matching records. The chart shows the largest 20 lead groups; its table lists every matching lead. Counts describe documents, not contributions, throughput or staff performance.

The five deadline groups are disjoint: overdue, due soon including today through the next three working days, later, unknown and closed/cancelled. Working-day/holiday rules and invalid-date handling reuse the grid's classifier. Select a real chart bar or accessible count-table link to open the matching table/CSV, preserving queue/search and adding the exact state/lead filter. New Later deadlines and Closed or cancelled register options support those links and remain compatible with schema-1 saved views. The linked table is also filtered/paginated on the server when scripts/assets fail. Retry retains linked filters, recovered assets retain the requested page, and Reset removes linked filter/page URL settings. Browser history refreshes a cached dashboard. HTML responses/errors use no-store. No document write or dashboard schema migration is introduced.

ECharts 6.1.0 is vendored locally as an unmodified full SVG-capable browser build, with upstream/third-party licenses retained. Published archive SHA-512 and vendored file SHA-256 hashes are recorded with provenance. The release gate verifies the full file set and audits ECharts plus bundled zrender 6.1.0 and tslib 2.3.0, retaining a separate ECharts receipt/manifest. No CDN, external service key or new Python requirement is needed for the dashboard. Linked HTML count tables remain usable without charts and provide keyboard/print access. Labels render as text; HTML tooltips and animation are disabled. Read [the dashboard guide on main](https://github.com/jongsky25/css-is/blob/main/docs/DOCUMENT_WORKLOAD_DASHBOARD.md).

**Verification:** PR workflow [40063839458](https://github.com/jongsky25/css-is/actions/runs/40063839458) passed both full 6,390-test orders with no failures/skips and all 447 offline AI cases on 2e53c8ea4faf51e9f9c2271679acc343f1853498. Post-merge workflow [40065126878](https://github.com/jongsky25/css-is/actions/runs/40065126878) also passed both 6,390-test orders, every required gate and Python/production-image/npm dependency audits. Deploy job 120790850373 uploaded Space commit e651d644339e1ab62849890de1fb352736d99c1a, reached RUNNING and logged `Live /login version check: OK (expected v8.32)` at 2026-10-24 05:31:31 UTC. Tests compare every queue/user against the independent registry reference and each nonzero drill-down against grid/CSV counts, including working-day/invalid-date boundaries, inactive/private leads, more than 20 groups and access revocation. Actual ECharts/Tabulator browser checks cover bar clicks, CSV, retry/reset, history, mobile/text safety, failed assets, recovered pagination and all-scripts-disabled filtered pages. Vendor checks reject incomplete graph provenance and transitive advisories. No manual action is required.

**Earlier delivery — read-only Supplies inventory:** [PR #440](https://github.com/jongsky25/css-is/pull/440) merged as 32a32eb5a9ed27586b3747a51910b9b83e486c73 (v8.30), preserving the intervening v8.29 capacity assessment. The user accepted the recommendation to reuse Tabulator in Supplies with “okay”.

Choose **Supplies → Supply catalog → Interactive inventory**. Search codes/descriptions and combine unit, physical-stock, availability and active/inactive filters, then Apply filters. Filtering, counting and numeric sorting cover the full authorized catalog before 30-item pagination. Code stays visible and links to the existing item screen; other columns can be resized/hidden. The standard catalog is the initial view and fallback. Failed/expired refreshes clear stale rows. The table reuses the existing stock classifier: unrecorded stock is unknown, a recorded zero is Out of stock, threshold equality is not low, and reservations distinguish Fully reserved/Low available from physical Critical stock. SQLite sorts integer quantities; JSON decimal strings and CSV preserve exact 64-bit totals.

All active staff retain their existing active-catalog access. Inactive items require a current custodian/auditor grant; a technical administrator role alone does not suffice. Reopening an inactive saved view after revocation fails rather than exposing items or broadening scope. Private account-owned inventory views retain applied filters, sorting, visibility and widths, with ten-view quotas, CSRF, owner/revision checks and non-reused IDs. The additive supply_inventory_view table contains preferences only. Its transactions do not run stock-notice processing. Current-view CSV shares the fresh authorized selection/order across all pages, includes only visible columns, neutralizes formulas, and rejects over 10,000 matches without truncation. Reads/preferences remain available when Supplies changes are disabled. No stock, reservation, report or catalog workflow is changed, and no dependency is added.

**Scope clarification:** the current catalog has no category field. The pilot filters existing units and stock states; category support is a separate, unselected enhancement. Existing critical/target levels retain their current meaning; no new reorder calculation is introduced. Read [the Supplies guide on main](https://github.com/jongsky25/css-is/blob/main/docs/SUPPLIES_INTERACTIVE_INVENTORY.md).

**Verification:** PR workflow [40057752339](https://github.com/jongsky25/css-is/actions/runs/40057752339) passed both full 6,364-test orders with no failures/skips and all 447 offline AI cases on 0b01e47004166481f3f18927d131bfbcecafe0f5. Post-merge workflow [40059331874](https://github.com/jongsky25/css-is/actions/runs/40059331874) also passed both 6,364-test orders, every required gate and the production dependency audit. Deploy job 120773111714 uploaded Space commit f07bb07a6cccae99420836a1062601166c69cf3b, reached RUNNING and logged `Live /login version check: OK (expected v8.30)` at 2026-10-24 04:01:28 UTC. Domain/HTTP coverage includes classification/reservation boundaries, filtering before pagination, numeric precision, live authority, private preferences, quota/revisions, CSRF/body bounds, read-only data and unchanged pending notices. Chromium uses the actual vendor/routes for all-page CSV, columns, draft controls, saved-view reload, mobile layout, stock zero/unknown, revoked inactive access, failed export/refresh and missing-vendor fallback. No manual action is required.

**Earlier delivery — grouped workflow/assigned-lead views:** [PR #438](https://github.com/jongsky25/css-is/pull/438) merged as 35204adcd9c9775e87e349fe7c6c7d4c52b2f90f (v8.28), preserving the intervening v8.26/v8.27 AI releases. The user authorized this enhancement with “do it” after the recommendation to add grouping.

Choose **Documents → Interactive table → Group by → Workflow** or **Assigned lead**, then **Apply filters**. The server groups all authorized queue/search matches after the applied workflow, verification, deadline and lead/date filters, before 30-record pagination. Groups sort alphabetically, with the selected sort inside each group. A summary lists totals across every matching page; table group headers explicitly distinguish full-result totals from the records on the current page. Groups can continue across pages and stay expanded. Lead groups use string account IDs, retain inactive historical assignees and collect missing/dangling assignments under Unresolved. Labels remain text.

Private saved views retain grouping. Old schema-1 views default to no grouping without a migration or rewriting stored preferences. Reset table clears grouping. Current-view CSV preserves group/order across all pages and adds a formula-safe Group: Workflow or Group: Assigned lead column even if that display column is hidden. Unapplied choices do not affect the current view/export. The existing 10,000-record export bound, fresh access checks and no-store responses remain in force. The separate full-register export retains its queue/search scope. Read [the guide on main](https://github.com/jongsky25/css-is/blob/main/docs/TABULATOR_PILOT.md).

**Verification:** PR workflow [40054273519](https://github.com/jongsky25/css-is/actions/runs/40054273519) passed both complete 6,337-test orders with no failures/skips and all 447 offline AI cases on c101cf45be7156e575edc6d01dae3016e095a822. Post-merge workflow [40055588296](https://github.com/jongsky25/css-is/actions/runs/40055588296) also passed both 6,337-test orders, every required gate and the production dependency audit. Deploy job 120760723117 uploaded Space commit a91efbbf922d474bba24bb0f61ef68357fe74e4f, reached RUNNING and logged `Live /login version check: OK (expected v8.28)` at 2026-10-24 03:01:49 UTC. Browser checks cover global/page-fragment counts, pagination, workflow/lead grouping, hidden-column CSV, saved-view reload, unapplied choices and reset. Domain checks cover authorization changes, combined filters, all-page ordering, private preferences, inactive/unresolved leads, CSV formula safety and invalid group options. No manual action is required.

**Earlier delivery — lead and deadline-period filters:** [PR #436](https://github.com/jongsky25/css-is/pull/436) merged as 470a969e9d7dbd5f4beac82243f31b56a87b88a9 (v8.25), preserving the intervening v8.23/v8.24 AI releases. The user authorized this enhancement with “do the next”.

Choose **Documents → Interactive table → Assigned lead**, optionally set **Due from** and **Due through**, then **Apply filters**. Lead can be a named assignee or Unresolved. Date endpoints are inclusive; either bound works alone. Missing/malformed deadlines do not match a date bound. Range filtering retains queue/workflow semantics for closed/cancelled documents; urgency filters keep their prior exclusions. Lead/date filters combine with queue/search, workflow, verification and urgency before counts/pagination, and current-view CSV shares the same validated selection/order.

Lead choices come only from records in the current authorized queue/search, including inactive historical leads. Saved views retain the lead ID and fixed date bounds. Old schema-1 preferences gain unrestricted defaults without a database migration or preference rewrite on read. A saved lead absent from the current choices remains selected as Saved lead (no matching records); fresh requests still apply the ID and current access instead of broadening to all leads. Restoring/resetting synchronizes the shared locale-independent date display. Reset clears these filters without deleting saved views. Standard-table counts, full-register measures and the original CSV retain their queue/search scope. Read [the guide on main](https://github.com/jongsky25/css-is/blob/main/docs/TABULATOR_PILOT.md).

**Verification:** PR workflow [40047954140](https://github.com/jongsky25/css-is/actions/runs/40047954140) passed both 6,325-test orders with no failures/skips and all 447 offline AI cases on 7807930ab5905efc465ed6bb39d02838ac097845. Post-merge workflow [40049676749](https://github.com/jongsky25/css-is/actions/runs/40049676749) also passed both full 6,325-test orders, all required gates and the production dependency audit. Deploy job 120743839508 uploaded Space commit 9f6aab94a289819fd86a5f2ce7f4f6d70a422a68, reached RUNNING and logged `Live /login version check: OK (expected v8.25)` at 2026-10-24 01:44 UTC. No manual action is required. Browser checks cover date labels/displays, inclusive boundaries, save/reopen, all-page CSV, reset, reversed-range feedback, stale leads and mobile controls; domain/HTTP checks cover access revocation, private choices, inactive leads, old preferences and invalid options.

**Earlier delivery — CI time first, then current-view export (v8.22):** [PR #432](https://github.com/jongsky25/css-is/pull/432) merged as 1a3b81701bbb5b37a62eb6a9d0db5afb9729e6fb (v8.22). Commit d7cf42f raised test jobs from 30 to 45 minutes before the export implementation, preserving normal/shuffled suites, dependency audits, zero-skip report checks and AI evidence gates. The extra budget accommodates slow OCR/browser setup without cancelling the final checks.

Choose **Documents → Interactive table → Export current view (CSV)**. The server generates all matching pages using applied queue/search, workflow, verification and deadline filters, sorting and visible columns, including settings restored from saved views. A shared validated query keeps selection/order aligned with the grid; current access is rechecked. UTF-8 CSV neutralizes spreadsheet formulas. More than 10,000 authorized matches produces a narrowing error rather than a partial file. Downloads/errors use no-store; failure leaves the grid usable. The separate full-register CSV retains its queue/search scope. Read [the guide on main](https://github.com/jongsky25/css-is/blob/main/docs/TABULATOR_PILOT.md).

The first audit caught CVE-2026-115572, CVE-2026-115585 and CVE-2026-115580 in the existing pypdf 6.21.1 pin. The release updates it to the advised patched 6.21.2, regenerating runtime/test hashes with locked uv 0.13.4 and retaining all other package versions. All four local requirement-set audits and the actual production Docker audit passed; no advisory is suppressed. An additional 139 PDF reader/intake/OCR/export checks passed against the patch.

**Verification:** PR workflow [40040207436](https://github.com/jongsky25/css-is/actions/runs/40040207436) passed both complete orders of 6,244 tests with no failures/skips and all 389 offline AI cases on 07ff6fc9cbdf260b0a617c1de8ac65f9c2af5000. Post-merge workflow [40042094743](https://github.com/jongsky25/css-is/actions/runs/40042094743) also passed both 6,244-test orders, all required gates and the dependency audit. Deploy job 120722743090 uploaded Space commit 3061a0e0274a27b711ae46f060a3cd4ad36d23b1, reached RUNNING and logged `Live /login version check: OK (expected v8.22)` at 2026-10-24 00:21 UTC. No manual action is required.

The initial Tabulator release 8.16 was verified before this follow-up began. [Workflow 39953481637](https://github.com/jongsky25/css-is/actions/runs/39953481637) reached RUNNING and logged `Live /login version check: OK (expected v8.16)` at 2026-10-23 12:48 UTC (Space commit be3fa42ff10b4d4e53ebd78fec6d0d17bf17b4b5).

The user then authorized: “once verified deployment. add the saved views and deadline highlighting”. [PR #427](https://github.com/jongsky25/css-is/pull/427) implemented both and merged as 72316d375e51199e661321d8bc2e20f10940106e. An intervening main release was preserved, so this follow-up became 8.18. Read [the user and technical guide on main](https://github.com/jongsky25/css-is/blob/main/docs/TABULATOR_PILOT.md).

Delivered behavior:
- Up to ten private, account-owned named views with queue/search, applied workflow/verification filters, sorting, column visibility and widths; create, update/rename, open and delete controls.
- Preferences contain display settings only. Opening starts at page one and rechecks current record access. CSRF, ownership, strict option validation, non-reusable IDs and revision checks protect writes.
- Both standard and interactive tables label overdue, due today, due soon and unknown deadlines using the existing three-working-day window and configured holidays; closed and cancelled records have no deadline alert.
- Full-register measures/CSV keep their explicit queue/search scope. Saved views do not add matching-filter exports, inline editing or new document mutations.

Both complete PR CI orders passed 6,158 tests each on db17bd7d391052d3500391a2b22aee914da316cc; all required checks passed. Post-merge normal and shuffled verification also passed all 6,158 tests each. The first post-merge normal job was canceled at its 30-minute budget after approximately 15 minutes of setup; a targeted retry completed successfully.

**Deployment verified:** [workflow 39962997557, attempt 2](https://github.com/jongsky25/css-is/actions/runs/39962997557/attempts/2) succeeded, uploaded Space commit bd9a6382b57484a7927cec1d759b958c92ae8c20, reached RUNNING and logged `Live /login version check: OK (expected v8.18)` at 2026-10-23 14:38 UTC.

A 45-minute CI budget proposal was prepared in [PR #429](https://github.com/jongsky25/css-is/pull/429) after the runner delay; 29 release-gate checks passed. The deployment retry succeeded, so that proposal was closed without merging. Its branch `fix/release-verification-time-budget` is retained for future pipeline work. **No v8.19 release or timeout change was deployed as part of that earlier v8.18 task. The 45-minute budget was later implemented and deployed in PR #432 (v8.22).**

**Deadline filters delivered:** [PR #430](https://github.com/jongsky25/css-is/pull/430) merged as b86bb7f30f70215b75ca7397b40d7b7d248037e7 (v8.20), after both CI orders passed 6,190 tests with no failures/skips and all 366 offline AI cases in workflow 39982506921. Overdue, Due today, Due soon (including today), and Unknown deadline combine with queue/search and workflow/verification before counting and pagination. Saved views retain the deadline choice; older views default to all deadlines. A shared classifier and request-wide date/holiday window keep filtering and labels consistent; closed/cancelled records never match urgency filters.

**Deployment verified in newer v8.21:** intervening [PR #431](https://github.com/jongsky25/css-is/pull/431) merged on top of PR #430 as dcec77c3261a6d53f961aa9c28a33a6f9c7395d7 and preserved its deadline-filter files. [Workflow 39990837900](https://github.com/jongsky25/css-is/actions/runs/39990837900) passed both 6,213-test orders, no failures/skips, and all 389 offline AI cases. Deploy job 120564200778 uploaded Space commit f3fedea881e482b7ddd920068e6f0c1a28fc096d, reached RUNNING and logged `Live /login version check: OK (expected v8.21)` at 2026-10-23 17:43 UTC.

**Obsolete deploy safely cancelled:** v8.20 workflow 39986164250 attempts 1 and 2 hit the 30-minute normal-job limit after slow setup; attempt 1 printed all 6,190 tests passed before cancellation interrupted report gates, and attempt 2 reached 94% without a reported failure. Attempt 3 was queued behind newer v8.21. The GitHub connector lacked a cancel tool and local gh API access was blocked by the environment network policy. An isolated operational branch `ops/clear-obsolete-deploy-20261023`, commit 0f1c179, added a no-permission, no-deploy queue job using the existing `hf-deploy` concurrency group with `cancel-in-progress: false`. [Queue workflow 39996976941](https://github.com/jongsky25/css-is/actions/runs/39996976941) replaced the obsolete pending v8.20 retry through native queue behavior, while preserving the active v8.21 release. Run 39986164250 is confirmed cancelled. **No manual cancellation is required. Do not merge this operational workflow into main.**

**Next action:** finish PR #447 full normal/shuffled CI, merge the verified current head, then verify the post-merge gates and exact live login version before marking the PowerPoint export delivered. Update this guide and PR #423 with final evidence. Document workload PowerPoint exports, Gotenberg, Supplies categories, CI setup improvements and obsolete deployment protection remain unselected. The CI test-job budget is 45 minutes.

The next session should:
1. Read this file and the three linked catalogs.
2. Check recent application changes before assuming a feature is missing.
3. Continue the current candidate discussion. Explain the concrete user benefit, existing overlap, implementation scope, costs and license conditions.
4. When a candidate is selected for implementation, propose a small pilot with measurable acceptance criteria, then follow the user's authorized scope.
5. Update this file's current topic, decisions and next action as work progresses.

Suggested continuation prompt:

> Read docs/INTEGRATION_RESEARCH.md in jongsky25/css-is on branch research/integration-candidates, together with its linked catalogs. Continue the Office Connect integration work from the recorded current topic. Re-check the latest application code before implementing anything.

If this documentation is merged later, use main instead. The research branch was used because every push to main triggers the Hugging Face deployment workflow.

## Research files

| File | Contents |
| --- | --- |
| [GitHub candidate catalog](integration-research/github-candidates.csv) | 51 repositories: exact observed stars, license notes, last push dates, selected release checks, proposed use, effort and caveats. |
| [Hugging Face candidate catalog](integration-research/hugging-face-candidates.csv) | 26 public Spaces, including competing implementations and candidates on hold. |
| [Hugging Face feature backlog](integration-research/hugging-face-backlog.csv) | 23 separately reviewable feature increments, mapped to Space candidate IDs, dependencies and acceptance criteria. |

These are research snapshots, not a promise of current availability. Stars, licenses, model versions and service status must be rechecked when a candidate is selected. GitHub review included 48 repositories above 5,000 stars and three relevant exceptions: SurveyJS Form Library, RapidFuzz and Apache Tika.

No model inference, uploads of Office Connect records, production integrations or accuracy benchmarks were performed during the research. Public demo status is not proof of a usable external API. GitHub stars are a discovery signal, not a quality or security certification.

## Existing application baseline

The reviewed application uses FastAPI, Jinja and SQLite, deployed as a Docker Space. It includes CSS scoring and reports; document intake, registry, search and signing workflows; work items and approvals; activities and minutes templates; calendars and rooms; travel receipt suggestions; supplies; and notifications.

Important existing capabilities:
- [documents_grid.py](https://github.com/jongsky25/css-is/blob/main/documents_grid.py): bounded Tabulator reads, private saved views, deadline labels/urgency/lead/date filters and current-view CSV, live in v8.25; see [TABULATOR_PILOT.md on main](https://github.com/jongsky25/css-is/blob/main/docs/TABULATOR_PILOT.md).
- [documents_intake.py](../documents_intake.py): reviewed OCR-assisted document metadata.
- [documents_search.py](../documents_search.py): SQLite FTS5, indexed-file provenance and access checks.
- [search_sources.py](../search_sources.py): role-aware cross-module search sources.
- [static/js/pdf-page-intake.mjs](../static/js/pdf-page-intake.mjs) and [static/js/document_ink.mjs](../static/js/document_ink.mjs): PDF.js already provides local PDF previews and pen-mark rendering. PDF.js is an existing dependency, not a new integration.
- [travel_scan.py](../travel_scan.py): Gemini already suggests fields from tickets and receipts. Another scanner is a challenger or fallback.
- [activity_docs.py](../activity_docs.py): minutes templates already exist; recording transcription would add a new input workflow.
- [supplies_import.py](../supplies_import.py): reviewed spreadsheet-import preview.
- [supplies_replenishment.py](../supplies_replenishment.py): deterministic replenishment suggestions.
- [documents_notify.py](../documents_notify.py): existing email delivery and notification-bell integration.
- [backups.py](../backups.py): consistent SQLite backup-API snapshots and scheduling.
- [ai_core.py](../ai_core.py) and [office_answers.py](../office_answers.py): provider controls, validated outputs, authorized keys and app-rendered facts.

Preserve official scoring, authoritative amounts, permissions, approval transitions and source records. An integration may suggest or present information without becoming the authority for those rules.

## GitHub recommendations

The proposed first sequence was **Tabulator → ECharts → PptxGenJS → Gotenberg → Apprise → one search pilot**. This is a recommendation, not an approved implementation schedule.

| Candidate | Proposed value | Integration approach |
| --- | --- | --- |
| [Tabulator](https://github.com/tabulator-tables/tabulator) | Filterable, sortable, grouped tables for registry, supplies and travel. | Vanilla JavaScript component in selected Jinja pages; backend retains validation and authorization. |
| [Apache ECharts](https://github.com/apache/echarts) | Interactive CSS and operational charts. | Browser charts backed by authorized aggregates and existing official calculations. |
| [PptxGenJS](https://github.com/gitbrent/PptxGenJS) | Editable PowerPoint briefings from approved results. | Branded slide templates populated with actual application data. |
| [Gotenberg](https://github.com/gotenberg/gotenberg) | Consistent PDF exports and Office-document conversion. | Separate Docker HTTP service with fonts, limits and controlled file handling. |
| [Apprise](https://github.com/caronc/apprise) | Extra notification delivery channels. | Python library behind the current notices/delivery flow. |
| [FullCalendar](https://github.com/fullcalendar/fullcalendar) | Improved calendar interactions. | Selective enhancement of existing calendar views; resource views require Premium licensing. |
| [Tiptap](https://github.com/ueberdosis/tiptap) | Rich-text minutes, notes and correspondence drafts. | Browser editor plus sanitization and a defined saved-content format. |
| [Frappe Gantt](https://github.com/frappe/gantt), [SortableJS](https://github.com/SortableJS/Sortable), [Mermaid](https://github.com/mermaid-js/mermaid) | Timelines, reorderable lists and workflow diagrams. | Separate, focused UI increments over existing records and state transitions. |
| [RapidFuzz](https://github.com/rapidfuzz/RapidFuzz) | Suggested matching names, organizations and references. | Small Python component; no automatic merges or identity assumptions. |
| [OCRmyPDF](https://github.com/ocrmypdf/OCRmyPDF), [Pandoc](https://github.com/jgm/pandoc) | Searchable PDF derivatives and editable document exports. | Bounded conversion workers; preserve originals and provenance. |
| [sqlite-vec](https://github.com/asg017/sqlite-vec), [Meilisearch](https://github.com/meilisearch/meilisearch) | Local semantic retrieval or a dedicated filtered/hybrid search service. | Compare alternatives against the current FTS baseline; do not deploy every search engine. |
| [DuckDB](https://github.com/duckdb/duckdb) | Cross-period analytics. | Query authorized snapshots or derived datasets; retain transactional SQLite. |
| [Activepieces](https://github.com/activepieces/activepieces), [n8n](https://github.com/n8n-io/n8n) | Cross-service automation. | Separate services consuming approved events; feature and licensing review before embedding. |
| [Celery](https://github.com/celery/celery) | Queued OCR, conversion and transcription jobs. | Python workers plus a broker, retries, idempotency and job-state tracking. |

Larger platforms remain conditional: ONLYOFFICE for embedded Office editing; DocuSeal/Documenso for signing capabilities missing from current workflows; Metabase/Superset for self-service BI; Keycloak for shared identity; Paperless-ngx for a genuinely separate archive; Novu for a broader notification platform.

Operations candidates: Uptime Kuma for external monitoring, Restic for encrypted off-site retention of existing consistent snapshots, and Playwright for browser regression checks.

### Tabulator discussion and possible pilot

Tabulator would make selected Office Connect lists behave more like useful spreadsheet views. For example, a document officer could narrow the registry to pending items, sort by deadline, and choose the columns needed for a review. A supplies officer could group items by category and sort a computed low-stock indicator.

The benefit is less scrolling, less repeated searching and less copying into spreadsheets merely to organize a list. Some of these actions may already exist on individual pages; measure the incremental benefit before replacing the current table.

This is a UI component, not a new database, an AI system or an approval engine. It does not automatically understand stock thresholds, grant access, save preferences, or provide business rules. Office Connect must supply those behaviors and validate any updates.

Suggested pilot, if authorized:
- Choose one frequently used registry or inventory table after inspecting its current implementation.
- Start with display, sorting and filtering; add column selection if useful.
- Keep existing row actions and keyboard/mobile usability.
- Use server pagination/filtering when data volume requires it; do not load all records into the browser just for a grid.
- Treat exports, saved views and inline editing as separately scoped additions.
- Verify that hidden/unauthorized rows never reach the browser or exports, calculated values remain correct, and normal actions continue to work.
- Compare time to complete a few real lookup tasks against the existing page.

The read-only pilot is implemented in [PR #424](https://github.com/jongsky25/css-is/pull/424), on branch feat/document-registry-tabulator. It adds server-side workflow and verification filters, sorting over all authorized matches, column resizing/visibility and a fallback. The pilot's 8.16 deployment is verified. Personal saved views and deadline highlighting are merged and verified live as 8.18 in PR #427.


### Tabulator next improvements under consideration

Private saved views, column preferences, deadline highlighting/quick filters, current-view CSV, lead/deadline date-range filters and grouped workflow/lead views are live in v8.28 (PRs #427, #430, #432, #436 and #438). The CI test-job budget is 45 minutes. The read-only Supplies inventory is also live in v8.30 (PR #440), with module-specific stock semantics, private views and current-view CSV. The Apache ECharts document workload dashboard is live in v8.32 (PR #442), with exact chart/table/CSV drill-downs and accessible count tables. The Supplies stock dashboard is also live in v8.34 (PR #445), with exact inventory links and a paginated below-critical list. Subsequent researched integrations, including PptxGenJS, remain recommendations until selected.

The initial full CI runs for PR #424 each passed 6,045 tests but failed the runtime import-closure check. The new documents_grid.py module was omitted from deploy_hf.RUNTIME_PY. Commit 310efad corrects the allowlist and the four local deployment tests pass. The subsequent full normal/shuffled checks passed on d81151a. After preserving main's intervening AI action release, the metadata was reconciled to 8.16 and PR #424 was merged. The initial 8.16 and follow-up 8.18 deployments are verified; their linked workflow logs record the live-version checks.

## Hugging Face recommendations

The first proposed sequence was redaction preview → OCR benchmark and one chosen integration → structured intake fields → scanned-table preview → semantic search → CSS topics → meeting transcription. Alternatives serving the same purpose should compete in evaluation rather than become separate user-facing tools.

| Capability | Candidate families |
| --- | --- |
| PII redaction | Presidio; browser Privacy Filter alternative. |
| OCR/layout parsing | PaddleOCR-VL, SmolDocling, MinerU, LightOnOCR; PP-StructureV3 for tables. GitHub Docling/PaddleOCR belong to this same decision. |
| Intake fields/classification | GLiNER2; browser zero-shot classification as an alternative. |
| Semantic/visual search | BGE-M3 embeddings; KaLM or BGE reranking; ColPali only for demonstrated visual-page retrieval gaps. |
| CSS topic discovery | BERTopic with embeddings appropriate for Filipino/English comments. |
| Translation | MADLAD-400, evaluated with bilingual office examples. |
| Meeting audio | Whisper/faster-whisper; speaker labels/WhisperX; optional GTCRN denoising. |
| Forecasting | Chronos-2, conditional on sufficient historical data and backtests against simple baselines. |
| Accessibility/assets | Kokoro read-aloud, Florence captions, BiRefNet background removal. |
| Handwriting | TrOCR only as a conditional experiment; not a complete paper-survey or checkbox reader. |

The CSV contains exact Space URLs and statuses. Some demos were paused, sleeping or broken, even where the underlying library remained useful. Do not rely on public demo uptime for production.

## Deployment and interoperability constraints

- [OCR_WORKER_LIMITS.md](OCR_WORKER_LIMITS.md) documents a 512 MiB, 45-second OCR process with one active process per app process. Large neural models need separately provisioned workers/services.
- [INTEGRATION_ACCESS.md](INTEGRATION_ACCESS.md) defines delegated metadata-only, read-only access. It is not an authorized document-body transport or write API.
- [INTEGRATION_WEBHOOKS.md](INTEGRATION_WEBHOOKS.md) describes a signed change-feed adapter; it is not already a deployed file-processing worker.
- Use narrow versioned adapters, bounded inputs, timeouts, cancellation, provenance, explicit job state and existing fallback patterns.
- Filter authorized candidates before exposing content to inference/search services and recheck authorization when rendering results. Embeddings do not provide access control.
- Keep existing file-retention behavior when adding upload or OCR features.
- Review app code, model weights and dependent components separately for license compatibility.
- Evaluate local office documents, Filipino/English switching, names and acronyms. Existing synthetic/provider-mocked AI checks do not establish real model accuracy.
- Prefer controlled services or adapted browser code for production; a public demo is an evaluation reference.
- [deploy-hf.yml](../.github/workflows/deploy-hf.yml) triggers deployment on every push to main. Documentation publication must not inadvertently become an application release.

## License and maintenance findings

These are findings from the research date; verify selected versions before adoption.

- Tabulator moved to tabulator-tables/tabulator and had a recent release during review.
- Presidio moved to data-privacy-stack/presidio.
- Casbin's popular core repo is now apache/casbin; its stars do not measure the Python binding's adoption.
- FullCalendar's MIT standard components and Premium resource views have different terms.
- SurveyJS Form Library is MIT; Survey Creator, Dashboard and PDF Generator require commercial licensing.
- n8n uses Sustainable Use and Enterprise licenses.
- Activepieces and Novu have MIT community/core code with commercial enterprise areas.
- Meilisearch has MIT Community and commercial Enterprise editions.
- Windmill source-built and distributed Community binaries have different terms.
- Stirling-PDF's MIT root license explicitly excludes several separately licensed directories.
- DocuSeal is AGPLv3 with additional terms; embedded signing/form builder are listed as Pro.
- Metabase includes AGPL and commercial editions; check embedding entitlements.
- Jina reranker v3.5 model is CC-BY-NC-4.0.
- sqlite-vec is pre-v1 and warns of breaking changes.
- pdf-lib's latest release found was v1.17.1 from 2021; defer unless a specific need justifies it.
- html5-qrcode announces maintenance mode and seeks new owners; defer for new work.

## Decision log

| Date | Decision or status |
| --- | --- |
| 2026-10-23 | Confirmed target is Office Connect / CSS-IS hosted on Hugging Face, not ChatGPT workspace. |
| 2026-10-23 | Completed initial review of 26 HF Spaces and 23 possible feature increments. |
| 2026-10-23 | Expanded review to 51 GitHub repositories with stars, deployment fit, license and maintenance notes. |
| 2026-10-23 | User requested durable GitHub documentation so this work can resume in future sessions. |
| 2026-10-23 | User authorized the Tabulator pilot with “execute” and then requested merging first. [PR #424](https://github.com/jongsky25/css-is/pull/424) merged as ed54b9b (version 8.16); [deployment run](https://github.com/jongsky25/css-is/actions/runs/39953481637) pending at the merge check. |
| 2026-10-23 | User authorized deadline quick filters with “do it”; implemented in [PR #430](https://github.com/jongsky25/css-is/pull/430), release v8.20, merged after both 6,190-test CI orders passed; verified live in v8.21 through workflow 39990837900. The obsolete v8.20 retry was safely cancelled through native concurrency queue housekeeping. |
| 2026-10-23 | User authorized saved views and deadline highlighting after deployment verification; PR #427 merged, both CI orders and post-merge gates passed, and live v8.18 was verified in workflow 39962997557. |
| 2026-10-23 | User authorized CI time first, then current-view export; implemented in [PR #432](https://github.com/jongsky25/css-is/pull/432), merged and verified live as v8.22 on October 24. |
| 2026-10-24 | Verified v8.22 in workflow 40042094743 after both 6,244-test orders and all release gates passed. CI allows 45 minutes, current-view CSV is live, and the audit-blocking pypdf advisories are patched in 6.21.2. No further implementation is selected. |
| 2026-10-24 | User authorized lead and deadline date-range filters with “do the next”; [PR #436](https://github.com/jongsky25/css-is/pull/436) is merged and verified live as v8.25. |
| 2026-10-24 | Workflow 40049676749 verified live v8.25 at 01:44 UTC after both 6,325-test orders and all gates passed. Lead/date filters, saved-view restoration and matching CSV exports are delivered; no further implementation is selected. |

| 2026-10-24 | User authorized grouped workflow/assigned-lead views with “do it”; PR #438 merged, both PR and post-merge 6,337-test orders and all gates passed, and workflow 40055588296 verified live v8.28 at 03:01:49 UTC. Group totals cover all pages; private saved views and current-view CSV retain grouping. No further implementation is selected. |

| 2026-10-24 | User accepted Supplies reuse with “okay”; PR #440 merged as v8.30 after preserving v8.29. Both PR and post-merge 6,364-test orders and all gates passed; workflow 40059331874 verified live v8.30 at 04:01:28 UTC. Category support is deferred because the catalog has no category field. No further implementation is selected. |

| 2026-10-24 | User authorized the Apache ECharts document workload dashboard with “do it”; PR #442 merged as v8.32 after preserving MCP v8.31. Both PR and post-merge 6,390-test orders and all gates passed; workflow 40065126878 verified live v8.32 at 05:31:31 UTC. The dashboard and exact, accessible drill-downs are delivered. No further implementation is selected. |

| 2026-10-24 | User authorized the ECharts Supplies stock dashboard with “do it”; PR #445 merged as v8.34 after preserving MCP consent recovery v8.33. Both PR and post-merge 6,403-test orders and all gates passed; workflow 40074060356 verified live v8.34 at 07:46:53 UTC. Stock charts, exact inventory links and the below-critical list are delivered. No further implementation is selected. |

When work resumes, record accepted/rejected candidates, rationale, implementation/PR links, verification results and the next topic here. Preserve the distinction between a researched recommendation, an approved implementation and a deployed feature.
