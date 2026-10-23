# AI answer and report draft evaluation — A22 / 8.02

Evaluation suite **1.1.0** contains **98 named scenarios**: the 38 answer-route scenarios introduced in 8.01, plus 60 MRR/CO-CSM report-draft scenarios added in 8.02. It turns selected safeguards into a reproducible, versioned release gate and produces a small report by category and case. The retained suite ID `existing-ai-answers` is a historical identifier; both surfaces must pass.

## What it checks

| Category | Coverage |
|---|---|
| Facts | Independently expected response counts, ARTA/activity scales, missing ratings, event versus submission periods, differences/percentage points, source IDs/labels/denominators/as-of dates and fixed templates |
| Authority | Account/role/session changes, professional-name opt-in, unknown/private sources and each asker's own private calendar |
| Freshness | Edited or archived sources, unavailable IDs and a date rollover during the provider call |
| Injection | Hostile source names, invented prose/values/actions, forged confidence, repeated IDs and unsupported operations |
| Resilience | Explicit abstention, low confidence, timeout, 503/retry, 429, malformed provider JSON, daily budget exhaustion and disabled feature |

Each scenario calls the real application route using registered synthetic accounts and a private copy of the test database. The real AI provider adapter builds/parses requests, enforces settings/budgets and handles retries. A fake replaces only provider HTTP responses. Socket/DNS guards reject actual network attempts, even if the route catches the resulting error. Fake credentials are installed only inside the test fixture; the Groq fallback is disabled there.

The suite does **not** measure a real model's understanding of a question, source relevance, multilingual quality, refusal tendency or inference accuracy. The provider's chosen selection is a controlled input. A passing report means the named application safeguards passed those inputs. It is not a claim that every AI feature or permission boundary is fully evaluated. Existing A12 and other AI regressions remain required separately in the full suite.

## Reviewed reference data and expected answers

- [evaluations/ai/reference-v1.json](../evaluations/ai/reference-v1.json) describes five synthetic forms, six responses and explicit valid/invalid/NA ratings. It fixes the reference clock at **October 20, 2026, 06:00 local time**. No production data is copied.
- [evaluations/ai/cases-v1.json](../evaluations/ai/cases-v1.json) records each case's ID/category, question, controlled provider input and expected result. Expected numbers, source labels and outcomes are literal reviewable values; tests do not ask the renderer or provider to generate the answer key.
- [tests/test_ai_evaluation.py](../tests/test_ai_evaluation.py) seeds those records and exercises the actual route. Unknown scenario names fail instead of quietly becoming a passing default.

Reference arithmetic:

| Measure | Expected calculation |
|---|---|
| All-time responses | 2 ARTA + 1 rated activity + 1 unrated activity + 1 archived activity + 1 resource-person response = **6** |
| Last 30 days | Four submissions on October 11, 12 and 19 = **4**; September event dates do not move October submissions out of this window |
| ARTA satisfaction | 2 top-box ratings / 3 valid ratings = **67%**; out-of-scale, missing and NA ratings are excluded |
| Active activity satisfaction | 2 top-box ratings / 3 valid ratings = **67%**; fractional/invalid ratings and archived activity breakdowns are excluded |
| Unrated activity | No valid ratings means **missing**, not zero percent |
| September event month | The September activity and resource-person form contribute **2 responses** |
| Overall Home satisfaction | Current Home semantics include the archived response's valid rating: 6 top-box / 8 valid = **75%**; recent Home satisfaction is 4 / 6 = **67%** |
| Differences | 6 − 4 = **+2 responses**; 67 − 75 = **−8 percentage points** |

Home's retained archive treatment differs from active survey breakdowns. This dataset makes that distinction explicit; this increment does not change those production definitions. Missing/invalid ratings are excluded in both. Professional names are off by default, while existing bureau-wide aggregate counts retain their current scope.

## Report drafts: contract v1 and independent evidence

The real `POST /reports/activities/{id}/ai-mrr-draft` and `POST /reports/csm-draft` routes are exercised with registered manager/viewer accounts, a private synthetic database and simulated provider HTTP. [tests/test_ai_report_evaluation.py](../tests/test_ai_report_evaluation.py) covers both styles, missing/empty data, denied users, revoked accounts/sessions, changed roles/settings, edits/new submissions/archives/period moves, day rollover, concurrent human edits, malformed or injected selections, timeouts, 503 retries, 429, budget/feature refusal and failures midway through field/audit writes.

The previous routes trusted model-written prose and saved it directly into exportable report fields. A JSON string schema alone could not establish that a claim was supported. In **8.02**, [ai_report_drafts.py](../ai_report_drafts.py) therefore accepts only exactly:

```json
{"contract_version": 1, "style": "detailed"}
```

`style` may be `concise` or `detailed`; version must be integer 1. Extra fields, free-form narrative, actions, wrong types and unsupported styles are rejected. The provider chooses presentation only. The server writes fixed evidence and clearly proposed recommendations, without invented owners, commitments, funding decisions or completed actions. **This reduces free-form AI drafting**: analysts can still write and save their own narrative. Human edits are not certified by this renderer.

Only aggregate counts/scores, fixed dimension labels, validated dates/periods and the as-of date enter the provider prompt. Activity/service/person names, venues, raw comments and comment themes are omitted. Report-draft interaction logs keep outcome/token/timing metadata but omit prompts, replies and raw provider error bodies, even when content logging is enabled for other features. A successful provider reply remains `rejected_validation` until the validated draft and its audit commit successfully. Existing retention/provider settings apply; this is not universal anonymization or approval of a provider's terms.

Fresh source reads bypass the dashboard's stale-while-revalidate caches. MRR atom loading is restricted to the current event's member forms. The official five-dimension SERVQUAL gap is used, rather than the activity card's three-dimension summary. Locally hashed form/response/answer content, event membership, existing saved fields and the reference day are compared after the provider call. No raw source hash input is sent to AI or added to the evaluation report. Current registered session/role/capability and AI mode/feature switch are rechecked under a write transaction. All generated fields and the audit commit together; source/access changes, concurrent human edits, failed selections and failed writes preserve the previous draft. No lock is held during provider I/O.

Reviewed report reference arithmetic (the `report_drafts` section of `reference-v1.json`):

| Measure | Expected result |
|---|---|
| MRR | Two identical responses: C=3 gives **3.0/4**; dimension means are Reliability **6**, Responsiveness **2**, Assurance **4**, Empathy **5**, Tangible **3** |
| MRR gap | Five-dimension average (6+2+4+5+3)/5 = **4**; expectation **6**; gap **−2.00** |
| CO-CSM | Two Q4 submissions: SQD1 ratings 5 and 3 give **50%** positive; the other seven official dimensions each give **100%**; overall 15/16 = **93.8%** after rounding |
| Period scope | An additional 2025 submission is excluded, even though its form event date is in 2026; official CSM uses submission date |
| Missing | CSM responses without valid ratings retain **N/A**, not zero; an MRR activity without usable satisfaction evidence makes no provider call |

The requests allow at most **96 output tokens**, an **eight-second read timeout** and a three-second connect timeout. The existing retry may make two attempts; this is not an eight-second end-to-end promise. Existing daily budgets and rate limits remain. All these tests use fakes, with no real spend.

## Run and read a report

Use the repository's locked test environment (Python 3.11 in release CI):

```sh
python scripts/ai_evaluation.py run --output test-results/ai-evaluation.json
python scripts/ai_evaluation.py run --output test-results/ai-evaluation-shuffled.json --shuffle-seed 319
python scripts/ai_evaluation.py check test-results/ai-evaluation.json
```

The runner sets the reference clock for its test subprocess. It does not set a production clock or access live data. A missing test dependency is an execution failure; install the existing locked test requirements rather than skipping a scenario. No new evaluation framework/provider dependency is needed.

The JSON report is authoritative. Its companion `.md` gives per-category counts and per-case outcomes. Reports include only case IDs/categories/status, test durations, contract/runtime/version metadata, selected source hashes and the checked-out Git commit. They exclude questions, prompts/replies, source content, account names, credentials and raw error details. Times include synthetic fixture/setup/teardown work and are **not** production inference latency measurements.

Use the failing case ID to find its reviewed question and expectation in the manifest, then inspect the local test failure. Do not upload production records/prompts as debugging artifacts. The two CI orders have their own reports; each must independently pass every case.

## Gates and evidence lifecycle

[scripts/ai_evaluation.py](../scripts/ai_evaluation.py) is a pytest plugin and command-line gate. Default pytest configuration loads it; recording is enabled only when `--ai-evaluation-report=PATH` is supplied. Release CI supplies that option to the existing full normal/shuffled test jobs, then validates the resulting report before the final required-check gate. Reports are uploaded in the existing test artifact bundles with **14-day retention**.

The gate requires:

1. Every current manifest case, exactly once, with all setup/call/teardown phases passing. Missing/duplicate cases, skips, xfail/xpass, fixture errors and failed/interrupted sessions are refused. A partial `-k` run cannot produce valid complete evidence or reuse a previous passing artifact.
2. All five categories and current suite/contract/reference-clock metadata.
3. Matching manifest/reference hashes, a fingerprint of the declared application/evaluation source files and application version, plus the exact checked-out Git commit. A code or dataset change requires a fresh run. The declared fingerprint covers the files listed in `PROVENANCE`; the Git commit additionally identifies the committed tree. It is not a signature or an attestation against malicious report authors.
4. Valid finite timings, minimized known fields and successful independent report validation. Reports are replaced atomically. A previous report is removed before a recorded rerun; unsuccessful runs retain explicit failed evidence when session completion is possible.

Case/reference edits also require an increased `suite_version` in the manifest. The metadata CI job compares those files with its trusted base commit; changing expected answers without increasing the suite version is refused. Review changes to questions, expected values, fixture data and coverage with the same care as application changes. Retain difficult failed cases. A source-code-only fix can keep the existing question-set version but must rerun current evidence.

## Provider and operational boundaries

The existing provider/data contract remains [verified facts v1](VERIFIED_AI_ANSWERS.md). A broader survey selection receives the user question and bounded fact IDs/descriptions/groups, without numeric values. Names and user questions are untrusted text and can still contain personal material; these checks do not establish universal anonymization. Current consent, settings, logging/retention and provider governance remain in force.

The scenarios check the existing bounded provider request settings (at most eight seconds per read timeout, three-second connect timeout and bounded output tokens), one retry where supported, and daily-budget refusal. They introduce no real spend. A timeout can involve two attempts; these are not an eight-second end-to-end service promise. Groq quality/fallback routing, OCR, feedback triage and other AI surfaces need their own future evaluation sets. Report draft safeguards are now included; real-model style-choice quality is not measured.

Before broader AI capability or live-model comparisons, the owner must define representative question quality targets, approved provider/data retention terms, expected scope/refusals, spend/token budgets and representative latency measurements. Evaluate live-model quality separately from this deterministic safeguard score; do not infer one from the other. Production workflow observations remain deferred.

## Rollout and repair

Release **8.02** follows freshly checked **8.01**. No schema migration, new feature flag, dependency or production provider configuration is required. The runtime module is included in deployment packaging. The two-digit application-version policy remains enforced.

Previously saved AI/human drafts are not rewritten or certified. Saved drafts are not automatically invalidated by source changes after generation: review or regenerate before official use. Exports continue reading saved fields without another AI call and retain their existing defaults when no draft exists. Clicking the drafting button explicitly replaces the current prefill, as before; an edit made during that request is protected. Current report creation permissions remain the existing bureau-wide capability boundary.

Both normal and shuffled full CI must pass for the final PR head, including all 98 scenarios and the minimized report gate. Local verification evidence is recorded in the PR. This increment does not publish a report, connect a new provider, evaluate live-model quality or resume manual production testing.

For a failing gate, repair the application, fixture or expectation with a reviewed explanation and a new suite version when reference inputs change; then rerun. Preserve failed evidence until the issue is understood. Do not relax the gate, omit cases, reuse an old report or restore model-authored official figures to obtain a green release. If a future broader lookup is unsuitable, the existing `catalog` engine remains the operational fallback.
