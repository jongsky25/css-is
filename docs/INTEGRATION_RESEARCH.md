# Office Connect integration research and continuation guide

Last updated: 2026-10-23
Repository: [jongsky25/css-is](https://github.com/jongsky25/css-is)
Deployment: [equityinhealth/office-connect](https://huggingface.co/spaces/equityinhealth/office-connect)

This is the durable record of research into public Hugging Face Spaces and widely used GitHub projects that could improve Office Connect. Customer Satisfaction Survey (CSS) is one module of this platform.

The user wants a broad set of worthwhile candidates, explained and evaluated one at a time. The Tabulator registry pilot was merged in [PR #424](https://github.com/jongsky25/css-is/pull/424) as release 8.16. The saved-view and deadline-label follow-up is live as 8.18 in PR #427. Other candidates remain research items.

## Resume here

**Current topic: saved views and deadline highlighting are complete and live in Office Connect v8.18. Select the next enhancement or candidate when requested.**

The initial Tabulator release 8.16 was verified before this follow-up began. [Workflow 39953481637](https://github.com/jongsky25/css-is/actions/runs/39953481637) reached RUNNING and logged `Live /login version check: OK (expected v8.16)` at 2026-10-23 12:48 UTC (Space commit be3fa42ff10b4d4e53ebd78fec6d0d17bf17b4b5).

The user then authorized: “once verified deployment. add the saved views and deadline highlighting”. [PR #427](https://github.com/jongsky25/css-is/pull/427) implemented both and merged as 72316d375e51199e661321d8bc2e20f10940106e. An intervening main release was preserved, so this follow-up became 8.18. Read [the user and technical guide on main](https://github.com/jongsky25/css-is/blob/main/docs/TABULATOR_PILOT.md).

Delivered behavior:
- Up to ten private, account-owned named views with queue/search, applied workflow/verification filters, sorting, column visibility and widths; create, update/rename, open and delete controls.
- Preferences contain display settings only. Opening starts at page one and rechecks current record access. CSRF, ownership, strict option validation, non-reusable IDs and revision checks protect writes.
- Both standard and interactive tables label overdue, due today, due soon and unknown deadlines using the existing three-working-day window and configured holidays; closed and cancelled records have no deadline alert.
- Full-register measures/CSV keep their explicit queue/search scope. Saved views do not add matching-filter exports, inline editing or new document mutations.

Both complete PR CI orders passed 6,158 tests each on db17bd7d391052d3500391a2b22aee914da316cc; all required checks passed. Post-merge normal and shuffled verification also passed all 6,158 tests each. The first post-merge normal job was canceled at its 30-minute budget after approximately 15 minutes of setup; a targeted retry completed successfully.

**Deployment verified:** [workflow 39962997557, attempt 2](https://github.com/jongsky25/css-is/actions/runs/39962997557/attempts/2) succeeded, uploaded Space commit bd9a6382b57484a7927cec1d759b958c92ae8c20, reached RUNNING and logged `Live /login version check: OK (expected v8.18)` at 2026-10-23 14:38 UTC.

A 45-minute CI budget proposal was prepared in [PR #429](https://github.com/jongsky25/css-is/pull/429) after the runner delay; 29 release-gate checks passed. The deployment retry succeeded, so that proposal was closed without merging. Its branch `fix/release-verification-time-budget` is retained for future pipeline work. **No v8.19 release or timeout change was deployed by this task.**

**Next action:** choose the next feature when the user requests it. Remaining ideas include deadline quick filters; lead/date filters; an authorized export matching interactive filters; grouped workflow/lead views; reuse in Supplies; or the next researched candidate. These remain recommendations, not implementation authorization.

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
- [documents_grid.py](../documents_grid.py): bounded Tabulator registry reads, account-owned saved views and deadline labels, live as 8.18; see [TABULATOR_PILOT.md](../TABULATOR_PILOT.md).
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

Saved per-user views, column preferences and overdue/due-soon highlighting are live in 8.18 (PR #427). Remaining candidates include deadline quick filters; filters for lead, direction and date range; and a server-generated export that matches the interactive filters and permitted columns. Grouped workflow/lead views and reuse in Supplies can follow. The remaining items are recommendations and have not been selected for implementation.

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

| 2026-10-23 | User authorized saved views and deadline highlighting after deployment verification; PR #427 merged, both CI orders and post-merge gates passed, and live v8.18 was verified in workflow 39962997557. |

When work resumes, record accepted/rejected candidates, rationale, implementation/PR links, verification results and the next topic here. Preserve the distinction between a researched recommendation, an approved implementation and a deployed feature.
