# Office Connect integration research and continuation guide

Last updated: 2026-10-25 (research and decision log); status section re-based on current `main` on 2026-11-11
Repository: [jongsky25/css-is](https://github.com/jongsky25/css-is)
Deployment: [equityinhealth/office-connect](https://huggingface.co/spaces/equityinhealth/office-connect)

This is the durable record of research into public Hugging Face Spaces and widely used GitHub projects that could improve Office Connect. Customer Satisfaction Survey (CSS) is one module of this platform.

The owner wanted a broad set of worthwhile candidates, explained and evaluated one at a time. Nothing below is an approved implementation schedule: a researched recommendation is not a decision, and a decision is not a release.

## Status

This section replaces a long October 25 handoff narrative (per-release validation notes and CI run IDs). That narrative is preserved in the history of the review branch `research/integration-candidates` (PR #423, kept) and is not needed to resume the work. Everything here is taken from the decision log below, and has **not** been re-verified against the current application; check `version.py`, `CHANGELOG.md` and `docs/SETUP_STATUS.md` for what is live now.

**Delivered from this research, as recorded in the decision log (release in parentheses):** Tabulator registry pilot (8.16), saved views and deadline highlighting (8.18), deadline quick filters (8.20), current-view CSV export and the CI time budget (8.22), lead and deadline-period filters (8.25), grouped workflow and assigned-lead views (8.28), read-only Supplies inventory (8.30), Apache ECharts document workload and Supplies stock dashboards (8.32, 8.34), PptxGenJS Supplies and Documents PowerPoint reports (8.39, 8.41), dashboard PDF reports using the already installed ReportLab (8.43), typo-tolerant search (8.60), Schedule (8.66), Travel claims table (8.68) and Travel claims CSV export (8.70). Private Telegram discussion digests through Apprise (8.47) and Telegram setup controls with precise diagnostics (8.51) were also delivered.

**Later delivery on the current line:** private saved filter and sort views for the Travel claims table, researched as release 8.71 (PR #481), were re-applied onto the current application as release 10.28 (PR #621).

**Telegram caveat:** outgoing Telegram delivery was never verified. Real activation needs hosting secrets and personal opt-in. Do not copy tokens or chat IDs into repository documentation or logs.

**Not selected:** no further candidate was chosen after the Travel work. The remaining candidates, the Hugging Face backlog and the license findings are below. The existing-application baseline below describes the application as reviewed on October 25, 2026, and its version references are from that date. Stars, licenses, model versions and service status are likewise snapshots from October 2026 and must be rechecked before a candidate is selected.

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

**PDF decision (v8.43):** the structured dashboard PDF requirement is delivered with already installed ReportLab. Gotenberg remains a candidate for browser-faithful HTML or Office-file conversion, rather than a required new service for these reports.

| Candidate | Proposed value | Integration approach |
| --- | --- | --- |
| [Tabulator](https://github.com/tabulator-tables/tabulator) | Filterable, sortable, grouped tables for registry, supplies and travel. | Vanilla JavaScript component in selected Jinja pages; backend retains validation and authorization. |
| [Apache ECharts](https://github.com/apache/echarts) | Interactive CSS and operational charts. | Browser charts backed by authorized aggregates and existing official calculations. |
| [PptxGenJS](https://github.com/gitbrent/PptxGenJS) | Editable PowerPoint briefings from approved results. | Branded slide templates populated with actual application data. |
| [Gotenberg](https://github.com/gotenberg/gotenberg) | Consistent PDF exports and Office-document conversion. | Separate Docker HTTP service with fonts, limits and controlled file handling. |
| [Apprise](https://github.com/caronc/apprise) | Extra notification delivery channels. | Private Telegram discussion-digest pilot delivered in PR #456/v8.47; real activation requires hosting secrets and personal opt-in. Other providers remain research candidates. |
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

Private saved views, column preferences, deadline highlighting/quick filters, current-view CSV, lead/deadline date-range filters and grouped workflow/lead views are live in v8.28 (PRs #427, #430, #432, #436 and #438). The CI test-job budget is 45 minutes. The read-only Supplies inventory is also live in v8.30 (PR #440), with module-specific stock semantics, private views and current-view CSV. The Apache ECharts document workload dashboard is live in v8.32 (PR #442), with exact chart/table/CSV drill-downs and accessible count tables. The Supplies stock dashboard is also live in v8.34 (PR #445), with exact inventory links and a paginated below-critical list. PptxGenJS Supplies stock PowerPoint exports are delivered in v8.39 (PR #447), with editable charts/tables, applied scope, fresh snapshots and complete bounded below-critical lists. Document workload PowerPoint exports are also delivered in v8.41 (PR #450), with three editable charts, complete count tables, applied queue/search and fresh snapshot/date boundaries. Both dashboard PDF exports and the QR CI correction are delivered in v8.43 (PR #452), using existing ReportLab. Gotenberg is deferred for these structured reports. The owner-only Travel claims table is merged in PR #477 and verified live as v8.68. Its native CSV follow-up is merged in PR #479 and verified live as v8.70. Private saved filter/sort views are implemented separately in PR #481, candidate v8.71, unmerged/not live; only an isolated preference table is added. Other researched integrations remain recommendations until selected.

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
| 2026-10-24 | User authorized PptxGenJS Supplies stock PowerPoint reports with “do it”; PR #447 merged as v8.39 after preserving intervening MCP releases through v8.38. Both final PR and post-merge 6,410-test orders, all 447 offline AI cases and every release gate passed. Workflow 40081048041 verified live v8.39 at 09:34:13 UTC. Editable charts/tables, fresh applied scope and all-page bounded below-critical exports are delivered. No further implementation is selected. |
| 2026-10-24 | User authorized Documents workload PowerPoint briefings with “do it”; PR #450 merged as v8.41 after preserving MCP registration fix v8.40. Both final PR and post-merge 6,415-test orders, all 447 offline AI cases and every gate passed. Workflow 40085119668 verified live v8.41 at 10:30:52 UTC. Editable charts/workbooks, complete count tables, applied scope and fresh permission-aware snapshots are delivered. No further implementation is selected. |
| 2026-10-24 | User authorized the flaky QR-link CI fix first, followed by PDFs. Test-only correction 26421e8 preceded PDF implementation; PR #452 merged as v8.43 after preserving M1.1 MCP reads v8.42. Both final PR/post-merge 6,422-test orders, all 447 offline AI cases and every gate passed. Workflow 40090118979 verified live v8.43 at 11:52:27 UTC. ReportLab met the PDF requirements; Gotenberg is deferred. No further implementation is selected. |
| 2026-10-25 | User authorized conditional CSV merge and the next increment. PR #479 was open and merged as v8.70/b4b1b92 after preserving Telegram room requests and passing 86 combined checks. Deployment 40176549103 passed both 6,961-test orders/447 AI cases/all gates and verified live v8.70 at 09:12:00 UTC. Private saved Travel selections are implemented separately in PR #481, candidate v8.71/head ddd2ce4; 15 domain, 11 browser, 67 table/page/deployment and 76 security/backup checks passed. First normal CI found the missing audit guard. Fix 1577519 retained that guard and passed 46 targeted checks; replacement full CI 40178850258 passed both 6,988-test orders, all 447 AI cases and all gates. Saved views remain unmerged/not live. |
| 2026-10-25 | User authorized Travel table merge and the next increment. PR #477 merged as v8.68/8bd2e5f after preserving Telegram meetings and passing 74 combined checks; deployment 40173934917 passed both 6,896-test orders/447 AI cases/all gates and verified live v8.68 at 08:07:27 UTC. CSV export is implemented separately in PR #479, candidate v8.69/head 82408ed; 28 domain/HTTP and 63 browser/travel-page/deployment checks passed, full CI 40174143027 passed both 6,918-test orders, all 447 AI cases and every required gate on 82408ed. CSV remains unmerged/not live. |
| 2026-10-25 | User authorized Schedule merge and the next increment. PR #473 merged as v8.66 after preserving main v8.65 and passing 111 combined checks. Deployment 40169508849 passed both 6,826-test orders/447 AI cases/all gates and verified live v8.66 at 06:53:41 UTC. Implemented the owner-only Travel claims table separately in PR #477, candidate v8.67; 92 focused and 190 travel regression checks passed; full CI 40169879494 passed both 6,856-test orders, all 447 AI cases and every required gate on 4d74a2f. Travel remains unmerged/not live. |
| 2026-10-25 | User authorized search merge and the next researched integration. Search PR #463 merged as v8.60 after full prior-head and final combined checks, then was verified live through v8.61. FullCalendar Schedule is implemented separately in PR #473 (candidate v8.63), with both full 6,744-test orders, all 447 AI cases and every gate passed; it remains unmerged. |

**CI follow-up resolved:** PR #452 fixes the PNG-base64 false positive observed in old v8.40 workflow 40083543723/job 120841776542. Actual destinations are now checked with a deterministic regression payload. Both full PR and post-merge orders passed, and live v8.43 is verified. No further QR CI fix is pending.

When work resumes, record accepted/rejected candidates, rationale, implementation/PR links, verification results and the next topic here. Preserve the distinction between a researched recommendation, an approved implementation and a deployed feature.
