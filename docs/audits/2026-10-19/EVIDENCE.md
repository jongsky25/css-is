# Evidence, methods and limitations

## Scope and environment

- **Date/revision:** 19 October 2026; commit `3a45851`, Office Connect 7.22.
- **Method:** repository/architecture inventory, targeted source tracing across the main components, existing automated tests, isolated synthetic security/correctness probes, local browser inspection, dependency/static analysis and current official peer documentation.
- **Inventory:** 131 top-level Python files, 81,777 Python lines, 182 HTML templates. This is an inventory, not a claim that every line was manually reviewed. Runtime OpenAPI: 362 paths, 411 operations, 224 writes. AST route counts differ because generated/router registration is represented differently; the report uses runtime counts.
- **Local runtime:** Python 3.12.14, SQLite 3.53.1, FastAPI 0.141.1, Starlette 1.6.0, pandas 2.2.3, NumPy 2.3.5, pytest 9.1.1, httpx 0.28.1. Docker targets Python 3.11; runtime parity remains a release task. The [resolved audit requirements](evidence/resolved-audit-requirements.txt) are evidence of this local run, not a recommended production lockfile.
- **Synthetic UI fixture:** two accounts, seven directory people, 171 survey responses, 1,617 answers, one document and one work item. The separate document-growth probe created up to 1,000 synthetic documents. No production database was available.
- **Providers:** no real mail, AI, Workspace mutation or other provider transaction was performed. Relevant delay/model behavior was stubbed. The local UI ran on loopback with scheduling disabled.
- **Production:** the repository points to `https://equityinhealth-office-connect.hf.space`. The available web access could not reach the site, and the workspace network policy did not include the host. The supplied login was not used. Deployed version, storage, headers, dependency set, provider settings and traffic remain unverified.

Application source and production data/settings were unchanged. Only this audit package was added to the repository. Local test tools/dependencies and disposable synthetic files were created to gather evidence. Nothing was committed or deployed.

## Evidence index

The JSON files contain synthetic/minimized results. [SHA256.json](evidence/SHA256.json) records their hashes and the included screenshots; hashes establish artifact consistency, not independent certification. Full logs and probe scripts remain in the local scratch workspace at `/workspace/scratch/office-connect-audit`; the repository package intentionally excludes databases, raw request logs and full test tracebacks.

| Evidence | Supports |
|---|---|
| [Source inventory summary](evidence/source-summary.json) | Component sizes and inventory scope |
| [Test summary and failure names](evidence/test-summary.json) | Full suite, focused rerun, preflight and smoke results |
| [Authentication/boundary probes](evidence/security-probes.json) | F03–F07 |
| [Authority, AI and analytics probes](evidence/authority-ai-probes.json) | F01, F07, F09, F15 |
| [SQLite counter probe](evidence/persistence-probe.json) | F02 |
| [Service-worker replay simulation](evidence/retry-probe.json) | F11 |
| [Performance measurements](evidence/performance.json) | F12–F13 |
| [API schema inventory](evidence/api-contract.json) | F14 |
| [Dependency/static-analysis summary](evidence/dependency-summary.json) | F08 and scan limitations |
| [Initial browser sample](evidence/browser-results.json) and [targeted follow-up](evidence/browser-normal-results.json) | F16 |
| [Mobile Home screenshot](evidence/home-mobile.png) and [desktop dashboard screenshot](evidence/dashboard-desktop.png) | Visual context for the synthetic browser review |

## Test results and interpretation

| Check | Result | Interpretation |
|---|---|---|
| Full pytest suite | **4,032 total: 3,968 passed, 48 failed, 16 skipped**, approximately 210 seconds; 3,923 warnings | Broad regression coverage exists, but it is not a green release gate |
| Focused rerun of MRR/routes/profile paths | **79 total: 63 passed, 16 failed**, approximately 19 seconds | Confirms persistent report/route/profile problems; fixture state differs, so it is not a before/after repair comparison |
| Native `qa_preflight.py` | 0 failures, 1 warning (no backup directory for size comparison) | Import/syntax checks pass in this mode; does not establish functional correctness |
| Preflight pointed at synthetic DB | 1 failure, 1 warning | Informational database initialization stdout was incorrectly treated as a template failure |
| `qa_smoke.py`, synthetic data, `QA_SAMPLE=1` | 142 checks, 1 failure, 2 coverage warnings | Calendar template direct-render lacked `request`; no rated section/admin-section covered in this run |

The full suite failures were triaged into the following clusters. These explain the observed failures, not blanket exemptions from repair:

| Cluster | Count | Evidence/next step |
|---|---:|---|
| Absent snapshot/fixture content assumptions | 14 | Nine integrity tests opened an empty schema; three AI-report tests lacked expected report data; Home/search each expected seeded activities. Build self-contained fixtures and rerun. |
| Clock/calendar-dependent scenarios | 13 | One room test used a past date; seven recurring-room scenarios encountered calendar/holiday assumptions; five reminder setups violated the current lead-time rule. Inject a clock and explicit business calendar. |
| Analytics and report output | 17 | Six NaN statistics errors, six null organization-mask errors and five MRR narrative/export failures. Minimal independent probes confirm the first two defects; MRR failures also persist in the focused rerun. |
| Business-role expectation mismatch | 2 | Wellness and work-arrangement tests expected technical admin to have approval authority. Reconcile intended business policy with fixtures; do not grant blanket authority merely to make tests pass. |
| Deleted/inactive actor path in profile scenario | 1 | Shared notification handling raised an uncaught permission exception; consistent with the separate deactivation probe. |
| Profile UI expectation | 1 | Test expects the companion ladder on the profile. Confirm intended UI behavior before changing code or test. |

A passing test suite is not a security proof. For example, persistence tests mocked an increasing counter and missed real SQLite semantics, and the authority-escalation path was uncovered through a dedicated boundary probe. Add those regression cases to the implementation work.

For repeatability, use a **disposable checkout/container without live data or provider credentials**, install the chosen audit/deployment dependency set, disable the scheduler and run:

```bash
CSS_NO_SCHEDULER=1 python qa_preflight.py
CSS_NO_SCHEDULER=1 python -m pytest -q --junitxml=/tmp/office-connect-pytest.xml
CSS_NO_SCHEDULER=1 python -m pytest -q tests/test_mrr_export_nuance.py tests/test_routes.py tests/test_profile_edit.py
```

Use the repository's synthetic seeder in a separate database for browser/smoke checks; direct database paths explicitly. Some legacy tests still look for `css_is.db` independently of configuration. Do not provide a production database just to satisfy them. Date, Python/dependency versions and test ordering can change failure counts until A10 is completed.

## Security and correctness reproduction notes

### Authority and session boundaries

The authority probe created a viewer linked to a directory person, another user's ordinary preverification document, and an explicitly restricted document. It checked permissions, submitted an ordinary profile edit with a leadership designation, then checked permissions and an HTTP document read again. Result: new director/chief authority and access to the ordinary document; no access to the restricted one. Explicit restriction was set through the document mutation service, because registration alone does not apply that access setting.

The session probe created synthetic accounts, issued a normal signed cookie and changed account state in the isolated database. It reused the old cookie after demotion, password replacement, logout and deactivation. The first three remained accepted on user administration; deactivation produced a 500 in notification permission handling. This does not claim inactive accounts retained authorized access.

The CSRF probe sent a foreign Origin with a supplied cookie to an administrative form. It changed state, demonstrating missing uniform server enforcement. Browser SameSite behavior was not simulated. The redirect probe checked the actual 303 Location. Thirty invalid login requests establish the observed lack of a local throttle over that sample; edge controls and broader abuse capacity were not tested.

### Persistence

The real SQLite probe opened a WAL database, held one reader connection, and made three committed changes from a writer. At each step it recorded both the long-lived reader's `PRAGMA data_version` and a new connection's value. Results:

| Step | Fresh connection | Same reader connection |
|---|---:|---:|
| Initial | 2 | 2 |
| Commit 1 | 2 | 3 |
| Commit 2 | 2 | 4 |
| Commit 3 | 2 | 5 |

This reproduces the incorrect primitive used by `_db_data_version()`. Source tracing connects it to the periodic save/health comparisons. It is not an end-to-end live bucket test, and backup loss was not observed. Real bucket/restart/restore verification remains an immediate roadmap gate.

### Write retries, AI and analytics

- **Replay:** a Node VM executed the service-worker retry function against a fake fetch that recorded a side effect, returned a proxy 503 without the application marker, then accepted the retry. The final status was 200 with two recorded effects. No real business request was duplicated.
- **AI:** an injected provider result asserted grounding/confidence while disagreeing with the supplied fact (2 versus 999999). The optional maximized-answer endpoint accepted it. This is a contract failure test, not a benchmark of a particular model's hallucination rate.
- **Privacy:** synthetic name/medical prose survived the current masking helper; bearer-path sentinels survived path bucketing. Production log contents were not inspected.
- **Analytics:** direct minimal calls with a null organization path and a NaN trend independently produced the exceptions seen in the suite. They do not depend on a production snapshot.

## Performance measurements

In-process HTTP requests used a copied synthetic database and a normal staff session. Each route had one first measurement followed by seven repeated warm samples. SQL trace callbacks counted statements. Results exclude TLS, hosting proxies, WAN latency and meaningful multi-user contention; seven samples do not establish a production p95.

| Route | First measurement (ms) | Warm median (ms) | SQL statements |
|---|---:|---:|---:|
| Home | 332.6 | 15.2 | 219 |
| Calendar | 62.1 | 10.9 | 79 |
| Documents | 40.2 | 11.6 | 80 |
| Work | 28.6 | 10.7 | 66 |
| Rooms | 53.0 | 13.4 | 104 |
| Travel | 17.7 | 9.5 | 70 |
| Dashboard | 111.4 | 14.9 | 64 |
| Authenticated health request | 8.2 | 8.2 | 57 |
| Authenticated CSS request | 8.9 | 6.6 | 56 |

The anonymous CSS request made zero application SQL statements. The gap points to common authenticated request preparation, rather than the static file handler itself.

| Visible document count | Registry lookup statements | Elapsed (ms) |
|---:|---:|---:|
| 10 | 22 | 0.4 |
| 100 | 202 | 2.9 |
| 1,000 | 2,002 | 50.2 |

These were owner-visible records, not a complete mix of permission scenarios. Any optimization must additionally prove visibility correctness for all relevant roles/scopes. A mocked 300 ms mail provider delay during password reset caused about **309.3 ms event-loop lag**, measured by a concurrent 10 ms ticker. This directly supports removing blocking work from async request execution.

No production load/stress test, sustained soak, capacity limit, database migration benchmark or vendor performance comparison was performed. Older repository performance notes are historical context; current incremental cache behavior was considered rather than assuming old full-rebuild timings still apply.

## Browser and accessibility review

Chromium at **1440×1000** and **390×844**, light theme, synthetic staff session; service workers disabled to keep page inspection independent of cached content. Initial run: 20 page/viewport combinations. Follow-up: 8 checks, dismissing introductory tours before capture. Their union covers **23 distinct combinations: 13 desktop and 10 mobile**.

- Desktop: Home, Calendar, Rooms overview, room booking, Travel, Wellness, Work Arrangement, Documents list/detail, Work list/detail, Dashboard, survey.
- Mobile: Home, Calendar, Rooms overview, room booking, Travel, Documents list, Work list, Wellness, Dashboard, survey.
- All sampled navigations returned HTTP 200 with no recorded page JavaScript exceptions and no page-wide horizontal overflow.
- axe-core 4.10.3 checked WCAG 2 A/AA, 2.1 A/AA and 2.2 AA tags. Automated checks cannot establish complete conformance.

| Surface | Confirmed automated findings in targeted follow-up |
|---|---|
| Home desktop | ARIA required children: 1; contrast: 7 nodes; target size: 5 nodes |
| Home mobile | ARIA required children: 1; contrast: 3; keyboard-inaccessible scroll region: 1; target size: 5 |
| Wellness desktop/mobile | Nested interactive control: 1 each |
| Dashboard desktop/mobile | Contrast: 17 nodes each |
| Survey desktop/mobile | Contrast: 1; target size: 9 each |

The JSON contains affected selectors and failure explanations. Counts describe this sample, not the number of distinct site-wide defects. Shared components can cause repeated instances. A mobile screenshot shows that a personal to-do area already exists; the proposed task-queue work should build on it.

No staff observation, task-time benchmark, screen-reader session, full keyboard walkthrough, dark-theme review, offline end-to-end exercise or exhaustive form/dialog/error-state review was performed. The browser checks primarily tested rendering and automated accessibility, not completion of every business workflow. Those gaps are explicit Phase 2–3 tasks.

## Dependency and static-analysis interpretation

`pip-audit` scanned 48 pinned packages from the local resolved app/test dependency set. It reported 49 entries for `pypdf 6.10.0`, comprising 31 distinct advisory IDs before alias deduplication. IDs and fixed versions are preserved in the summary. Package mirrors and installed sets can differ from deployment; scan the actual built artifact before declaring production exposure or selecting a fixed version.

Bandit produced 249 candidates, including 142 dynamic-SQL warnings and 33 swallowed-exception warnings. They are review leads, not 249 confirmed vulnerabilities. The three high-severity weak-hash candidates inspected were a photo ETag, calendar import identity and travel-rule fingerprint; their presence did not demonstrate password/signature compromise. No SQL-injection exploit was established by this audit, and not every dynamic query was exhaustively analyzed. Control-flow probes, parser exposure and runtime evidence drove the reported findings.

## Remaining production and business validation

1. Confirm running revision, modules, dependency/SBOM, runtime and host/proxy configuration.
2. Confirm data/attachment persistence, successful recent backups and an independently verified restore; agree recovery objectives.
3. Review authority assignments, session exposure, log destinations and bearer-link handling with the system owner.
4. Measure representative traffic, record sizes, slow requests, errors, resource use and provider latency/cost without logging sensitive payloads.
5. Validate intended business permissions, reporting/travel rules, retention and external system ownership with the responsible staff.
6. Conduct staff usability/accessibility sessions and selected peer product trials; use their results to refine later phases.

Until those checks are completed, this package is a **source and local-system audit with a production-validation plan**, not a completed production penetration test, compliance assessment or operational certification.
