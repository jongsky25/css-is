# AI assistance evaluation — A22 / 8.22

Evaluation suite **1.11.0** contains **423 named scenarios**: 38 answer-route cases from 8.01, 60 MRR/CO-CSM report-draft cases from 8.04, 48 feedback-triage cases from 8.07, 49 verbatim comment cases from 8.10, 32 participant-message cases from 8.12, 30 UX Insights analysis cases from 8.13, 32 directory duplicate-suggestion cases from 8.14, 31 landing-assistant action cases from 8.15, 19 direct travel scan cases from 8.17, 27 travel checklist upload cases from 8.19, 23 calendar invitation upload cases from 8.21, and 34 landing-assistant help/navigation cases from 8.22. It turns selected safeguards into a reproducible, versioned release gate and produces a small report by category and case. The retained suite ID `existing-ai-answers` is a historical identifier; all twelve surfaces must pass.

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

The previous routes trusted model-written prose and saved it directly into exportable report fields. A JSON string schema alone could not establish that a claim was supported. In **8.04**, [ai_report_drafts.py](../ai_report_drafts.py) therefore accepts only exactly:

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

## Feedback triage: contract v1 and independent evidence

The 48 `feedback_triage` scenarios call the real admin route against synthetic feedback and provider HTTP fakes. They cover valid status/severity values, a bounded open candidate list, unknown or wrong-type duplicate IDs, malformed provider selections, hostile feedback, access/settings revocation, source/candidate changes during the request, budgets, retries, timeouts and audit failure. The provider returns a strict four-field selection: `status`, `severity`, integer `duplicate_of` (0 means none), and a reason of 1–500 characters. Extra fields, invalid enums, noninteger or unlisted duplicate IDs and malformed reasons reject the whole suggestion. The response states `contract_version: 1` and `review_required: true`.

The prompt contains only a bounded, partially masked message and up to 30 newest open candidate IDs/snippets. Submitter identity, admin note, page URL, selector, region and history are omitted. Masking recognizes common email and phone forms but does **not** guarantee anonymity of arbitrary text. The free-form reason remains untrusted text, masked and escaped when shown. Metadata-only interaction logs omit prompts, replies and raw provider error bodies even when general content logging is set to `masked`.

The admin's current session, role/capability and AI switches, plus the feedback and candidate snapshot, are checked again after provider I/O before a suggestion returns. Only the existing admin `triage_feedback` capability can request this board-wide suggestion; the board has no per-record unit boundary. The route writes no feedback, update or submitter notification. A real Chromium test verifies that suggestions only fill fields for human review, an in-flight human edit prevents prefill, a no-match clears the previous duplicate field, and escaped model text cannot create an HTML element. The existing Save action remains the human decision. These tests do not measure whether a real model assigns the right severity/status or recognizes actual duplicates, and do not certify edits made after the suggestion appears.

The route uses at most 512 output tokens and an eight-second read timeout (three-second connect timeout). Existing provider retry means elapsed time may exceed one timeout. All evaluation cases use fakes with no real spend or production records.

## Verbatim comment analysis: complete batches and human precedence

The 49 `verbatim` scenarios exercise both activity-comment routes through registered users, current storage reads and the real provider adapter, with synthetic comments and fake HTTP replies. Thirty-three cases cover classification; sixteen cover the on-screen AI summary. A network guard prevents actual provider calls. The test set covers human corrections before and during AI work, changed/new/archived comments, revoked sessions or roles, disabled AI, two batches, malformed or injected selections, later-batch failure, provider retry/budget refusal and audit rollback.

A classification response must have exactly one valid `{i, sentiment}` for every comment in its batch, with an integer index and `appreciate`, `improve` or `mixed`. Missing, repeated, wrong-type, out-of-range or extra selections reject the whole run. The route collects all batches before writing; under a final write transaction it rechecks the current session, capability, AI settings and fresh activity/comment/human-tag snapshot. AI tags, a minimal audit entry and success outcomes commit together. A failed later batch or a human correction made during the call leaves all previous tags intact. Existing human tags are excluded from provider batches; a later human tag still takes precedence through the existing manual workflow.

The summary route sends bounded, partially masked quote excerpts and fixed theme/count information, omitting the activity name. It accepts one to three nonempty bullets of at most 240 characters, rejects extra fields and rechecks the same authority/source boundary before returning. Summary text is still untrusted free-form prose. The browser escapes it, and the response is for human review; it does not save or certify an official report. Prompt/reply/error-body content is omitted from verbatim interaction logs even when general content logging is enabled. Masking common email/phone strings is partial, not universal anonymization.

Both routes use an eight-second provider read timeout and three-second connect timeout; retries can extend total elapsed time. These cases establish deterministic application safeguards, not a real model's sentiment accuracy, theme relevance, refusal behavior or summary factuality. No live provider spend or production comments enter the test set.

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

## Activity message drafting: reviewable plain text

Thirty-two `messages` scenarios exercise the real activity draft route with synthetic activity details and fake provider HTTP. They cover welcome and ending drafts, changed role/session/settings/activity details, malformed output, unsupported numbers, HTML, links, private email content, timeout/retry, budget refusal and audit rollback. Every case is required in both CI orders. No attendee record is sent to the provider.

The response contract is a single `text` field: bounded plain text with exactly one literal `{name}` placeholder. Extra fields, tags, links, control characters, and numeric details absent from current activity metadata are rejected. This is a narrow safeguard, not a semantic proof that every venue, organizer, or claim is accurate. Organizers see the complete suggestion and must explicitly apply it. Edits made during the AI request are preserved. The existing message autosave acts only after application.

The route rechecks the registered account, permission, AI switches and current activity after provider I/O. Success outcome and audit commit together; failures leave stored messages alone. Participant-message interaction logs retain outcome/token/timing metadata without prompts, replies or provider error bodies, including when general content logging is on. The request allows up to 300 output tokens and an eight-second read timeout, with the existing retry and budget limits. Synthetic tests do not measure real-model writing quality or production latency.

## UX Insights analysis: current data and review scope

Thirty `ux_analysis` scenarios call the admin route with synthetic telemetry, feedback and fake provider HTTP. They cover current admin access, changed events or feedback, retention and AI setting changes, unsupported numeric claims, unsafe text, timeouts, budget refusal and audit rollback. The browser check verifies that model text is escaped and the event count, window and partial-sample status are visible. Every case is required in both CI orders.

The provider receives the existing self-describing UX handoff after contact email and mobile-number masking. Handoff sanitization is partial and does not prove all free text anonymous. A returned analysis must be bounded plain text without links, markup, control characters or numeric tokens absent from the source handoff. Those checks cannot prove causal interpretation or that every proposed fix is useful, so the page labels the result for review against the handoff.

The route rechecks the registered admin, AI switches and current telemetry/feedback snapshot after provider I/O. Audit and successful outcome commit together. Logs retain outcome/token/timing metadata without prompt, response or raw provider error bodies, including when general content logging is on. The request allows at most 1,024 output tokens and an eight-second read timeout, with the existing retry and budget limits. This is not a production latency or real-model quality score.

## Directory duplicate suggestions: current records and staff decision

Thirty-two `harmonize` scenarios exercise the existing admin route with synthetic directory names and fake provider HTTP. They cover current admin access, deactivation/demotion/logout, AI switches, renamed/deleted/changed records, invalid relations and reasons, hostile source names, budgets, timeout/503, and audit rollback. A Chromium check confirms hints are escaped and shown beside the separate human merge action. Every case is required in both CI orders.

Names remain professional personal data sent to Gemini only when an administrator explicitly enables the existing `harmonize` flag. The prompt includes only the two current candidate names, rating counts and staff markers, with common email and digit runs masked. No additional provider is used. The route accepts exactly `same`, `different` or `unsure` plus a bounded, plain-text reason. It rechecks the registered admin, opt-in, and both current candidate records after provider I/O. Only a validated hint is returned; it cannot merge records. Logs retain outcome/token/timing metadata without prompts, replies or raw provider errors, including when general content logging is enabled. Audit records identify the pair by IDs and omit names.

The request allows at most 256 output tokens and an eight-second provider read timeout, with the existing retry and budget limits. These synthetic checks establish application safeguards, not real-model duplicate-identification accuracy. Staff must inspect both records before using the existing merge action.

## Landing assistant actions: current authority and confirmation

Thirty-one `assistant_action` cases exercise the signed-in `/api/ai/route` path with synthetic activities and fake Gemini HTTP. They cover create, archive and export suggestions, denied roles, deactivation/demotion/logout, changed AI switches, renamed/archived/new activity candidates, malformed or injected selections, low confidence, typed and exact action arguments, budget, timeouts and 503 replies. A Chromium check confirms that the description is escaped and only an explicit Confirm click submits the existing action form. Every case is required in both CI orders.

The model selects a key from a role-filtered server catalog; it never supplies the destination URL. The route now rechecks the registered account, role, AI mode and switches after provider I/O. For archive suggestions it also rechecks the full current candidate list; a changed list or record yields the normal fallback. Action arguments must have exactly the supported fields and expected string types, and oversized names or unsupported IDs are rejected. Successful suggestions are logged only after the current check. The actual create/archive/export endpoints still enforce their own authorization and audit when staff confirms; this route does not execute a write.

These deterministic cases verify the application boundary, not whether a real model correctly understands a staff request. The user must review the confirmation card. Production workflow observations remain deferred.

## Travel receipt scanning: current filing and bounded suggestions

Nineteen `travel_scan` scenarios exercise the signed-in `/travel/f/{ref}/scan` route with a synthetic image and fake Gemini HTTP response. They cover owner access, revoked sessions/accounts, changes to the filing and feature switch during provider I/O, malformed amount/date/currency/text fields, budget refusal, timeout and HTTP errors. The route rechecks the registered actor and entire filing before returning a reading. Invalid readings fall back to manual entry; a scan never saves an amount to the filing.

The provider sees the uploaded image or PDF, so it may contain personal and financial information. The image is not retained by the direct scan route, and travel-scan interaction logs now omit prompts, replies and provider error bodies. The existing 25-second read timeout can be attempted twice. The suite tests application safeguards with fake provider choices; it cannot establish OCR accuracy or prove that a suggested amount appears on the document. Checklist upload readings and calendar invitation readings share the provider feature but are not part of these nineteen direct-route cases.

## Checklist upload readings: current owner and explicit DPO choice

Twenty-seven `checklist_upload` scenarios exercise the real travel upload route with a fake Drive relay and simulated Gemini HTTP. DPO and appearance replies require complete typed fields, valid dates and bounded plain text before a reading or filing check is offered. Malformed AI replies leave the confirmed file upload intact and offer manual entry. A matching DPO number no longer saves an AI supplied date automatically: the person must choose the existing button, review the filled form and save it. A Chromium check confirms the date field stays unchanged until that button is clicked.

After relay and provider work, the route takes a short write lock and rechecks the registered account, travel setting, unchanged filing, editability and applicable checklist row before saving the upload. If that check fails, it asks the relay to remove the uploaded file and returns no reading. A failed relay cleanup leaves an unlinked file requiring records staff review; the route logs the filing reference and row for investigation without logging file contents. AI feature disablement during the request suppresses the reading while allowing an otherwise valid upload.

These synthetic checks establish the application's boundary, not document reading accuracy. The existing provider and relay receive uploaded files under their current data contracts; no live documents are used in this suite.

## Calendar invitation reading: current activity and staff review

Twenty-three `invitation_upload` scenarios call the signed-in calendar upload route with a synthetic PDF, fake Drive relay and fake Gemini HTTP. They cover changed or revoked access, changed or cancelled activities, changed outside-office details, malformed or unsafe readings, budget and feature switches, timeout/503 replies, failed relay uploads and cleanup. The route checks the current registered session, visibility, activity and outside-office details under a short write lock before saving the uploaded link. If those checks fail, it asks the relay to remove the file; a failed cleanup is reported for records staff review.

Provider readings require complete typed fields and bounded plain text. Missing or extra fields, markup, links, contact details and oversized text are rejected. A bad AI reading does not prevent a valid upload. If AI is disabled while a file is processing, the file can still be kept but no reading is offered. Suggestions fill the form only after the person clicks “Use these”; saving remains a separate action. The provider sees the uploaded image or PDF, which may contain personal information. Interaction logs retain outcome/timing metadata without prompt, response or provider error bodies. These offline checks do not establish real-model reading accuracy or production latency.

## Landing assistant help and navigation: current links and access

Thirty-four `help_navigation` scenarios call the signed-in assistant route using fake Gemini HTTP. They cover registered-session loss, role and access changes, disabled switches, changed page/guide catalogs, malformed or unavailable keys, low confidence, timeout/503 replies and budget refusal. The model chooses only a server catalog key; labels, guide text and URLs come from the application. Before a valid suggestion returns, the route checks the current account, role, access flags, AI switches and the same offered catalog under a short write lock. A stale or invalid result falls back to normal search.

These cases verify application routing and current permission checks with simulated model selections. They do not establish that a real model picks the most useful page or guide. The provider receives the typed request and offered catalog, which may contain the user's own text; no live provider is called by the suite.

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

The scenarios check the existing bounded provider request settings (at most eight seconds per read timeout, three-second connect timeout and bounded output tokens), one retry where supported, and daily-budget refusal. They introduce no real spend. A timeout can involve two attempts; these are not an eight-second end-to-end service promise. Groq quality/fallback routing, OCR and other AI surfaces need their own future evaluation sets. Report draft, feedback-triage, verbatim, activity-message, UX-analysis and directory-suggestion and assistant-action safeguards are now included; real-model style-choice quality is not measured.

Before broader AI capability or live-model comparisons, the owner must define representative question quality targets, approved provider/data retention terms, expected scope/refusals, spend/token budgets and representative latency measurements. Evaluate live-model quality separately from this deterministic safeguard score; do not infer one from the other. Production workflow observations remain deferred.

## Rollout and repair

Release **8.22** follows the merged 8.21 main branch. No schema migration, new feature flag or production provider configuration is required. The pinned `pypdf` version advances to 6.21.2 to resolve three reported malformed-PDF runtime advisories. The application and service-worker cache versions use exactly two digits after the decimal.

Existing AI/human comment tags are not rewritten. UX analysis remains a review aid and displays its evidence window and sample status. Production workflow observations and real-model quality remain deferred. Both normal and shuffled full CI must pass for the final PR head, including all 366 scenarios and the minimized report gate.

For a failing gate, inspect the case ID and repair the application, fixture or expectation with a reviewed explanation. Increase the suite version for case/reference edits and rerun current evidence; do not reuse an old report or omit failed cases.
