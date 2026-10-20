# Findings register

Reviewed revision: `3a45851` (Office Connect 7.22), 19 October 2026. Read [evidence and limitations](EVIDENCE.md) alongside this register. Priorities are delivery priorities, not CVSS scores: **P0** requires an immediate repair release; **P1** belongs in the next foundation releases; **P2** follows in measured workflow improvements; **P3** is a controlled capability expansion. Confirm deployed exposure before assigning incident impact.

## F01 — Self-edited designation changes approval authority

**P0 · High security impact · Locally reproduced.**

`POST /me` writes a linked user's designation into the staff directory. Organization rank is then inferred from designation/position text, including the word “Director”. Document and approval permissions consume that inferred rank. A self-service display field therefore becomes an authorization input.

- **Evidence:** [profile write](../../../app.py#L5725), [rank inference](../../../storage.py#L6798), [ranked account lookup](../../../storage.py#L6961), [document permissions](../../../documents_permissions.py#L37), [probe](evidence/authority-ai-probes.json).
- **Result:** a linked viewer changed designation to Director, gained director/chief status, and opened another user's previously inaccessible preverification document. The application role stayed `viewer`. A document explicitly marked restricted remained inaccessible; this was not a bypass of every document permission.
- **Consequence:** unauthorized approval authority and wider access wherever inferred leadership rank is trusted. Wellness/work-arrangement self-approval paths also use leadership inference and require regression coverage.
- **Repair:** first remove self-service writes to authority-bearing directory fields. Then introduce administrator-controlled organizational assignments with scope, effective dates, delegation and audit history. Keep ordinary display titles independently editable if desired. Review existing assignments with the business owner; do not automatically trust a migration of current free text.
- **Acceptance:** changing any profile field never changes permissions; viewer, chief, delegate, director and technical-admin tests cover own/other unit, preverification/restricted records, self-approval, expiry and removal of assignments. Previously authorized workflows still work.

## F02 — Snapshot loop compares incompatible SQLite change counters

**P0 · High durability impact when optional persistence is enabled · Locally reproduced primitive and source-traced loop.**

`_db_data_version()` opens a new connection for each `PRAGMA data_version` read. SQLite documents that values are meaningful for comparison only on the same connection over time. The persistence loop compares values from different connections to decide whether another backup is needed. Its health view uses the same signal.

- **Evidence:** [counter and loop](../../../app.py#L4903), [health view](../../../app.py#L3850), [real SQLite probe](evidence/persistence-probe.json), [SQLite documentation](https://www.sqlite.org/pragma.html#pragma_data_version).
- **Result:** three committed changes advanced a long-lived reader's counter from 2 to 5; the application's fresh-connection reads stayed at 2. The loop can skip changes after its first save, while its health calculation fails to report them as unsaved. Existing tests mock an increasing counter and miss this behavior.
- **Limit:** this concerns the optional persistence loop; it does not establish production data loss or failure of every backup path. Separate scheduled/shutdown/manual backup mechanisms exist. The live storage configuration was not accessible.
- **Repair:** use a correctly maintained connection with suitable synchronization, or a durable mutation generation. Initially, taking bounded periodic snapshots without the faulty skip optimization is a simpler containment option. Only mark a generation saved after a successful snapshot. Verify which storage survives host restart and which failure domains each copy covers.
- **Acceptance:** real commits after the first snapshot appear in the next snapshot; a failed copy leaves health degraded; restart/crash and restore drills preserve the expected records. Prove the agreed recovery point and recovery time from restored data, not a successful upload message. Update the contradictory persistence runbooks.

## F03 — Signed sessions retain stale authority and lack revocation

**P0 · High security impact · Locally reproduced.**

Tokens contain role and issue time, and the common request layer reconstructs the user from these claims. It does not consistently resolve current account status and authority. Logout removes the browser cookie but cannot revoke a retained copy.

- **Evidence:** [token creation/validation](../../../auth.py#L150), [request user](../../../app.py#L2095), [authentication middleware](../../../app.py#L2219), [probe](evidence/security-probes.json).
- **Result:** an old admin cookie opened `/admin/users` after demotion and after password replacement; a replayed cookie worked after logout. A deactivated user's cookie caused HTTP 500 on admin and documents pages when notification code encountered a denied actor. Deactivation was not demonstrated to grant access.
- **Repair:** resolve active status and role centrally from current account state, using bounded invalidation if caching is necessary. Add server-side session records or a revocation/version mechanism with explicit logout semantics. Revoke affected sessions on password replacement, deactivation and authority changes. Retain domain-level permission checks.
- **Acceptance:** revoked, malformed, expired and stale-role cookies fail safely with an appropriate authentication response; no notification/rendering error turns account revocation into a 500. Prove per-session logout and administrative sign-out behavior explicitly.

## F04 — CSRF defenses vary by module

**P1 · High potential security impact · Missing boundary control locally reproduced.**

Newer Documents and Work handlers validate CSRF tokens; older shared form parsing does not. A cookie-bearing POST with a foreign Origin changed the administrative feedback setting.

- **Evidence:** [shared form handling](../../../app.py#L6783), [Documents checks](../../../documents_routes.py#L30), [Work checks](../../../work_routes.py#L29), [probe](evidence/security-probes.json).
- **Limit:** the HTTP client supplied the cookie; it does not simulate browser SameSite rules. Current `SameSite=Lax` reduces ordinary cross-site form attacks. The result demonstrates an inconsistent server boundary, not successful exploitation in every browser scenario.
- **Repair:** define a common CSRF policy for cookie-authenticated state changes, including login/account operations, form and JSON requests. Check allowed origins and handle missing-origin clients deliberately. Exempt public survey submissions and signed machine callbacks through explicit policies with their own controls.
- **Acceptance:** enumerate write routes and test allowed/forbidden origins, valid/missing/invalid tokens, sibling-host scenarios and legitimate callbacks. Add browser-level tests for the actual hosting domain arrangement.

## F05 — Login accepts external protocol-relative return URLs

**P1 · Medium security impact · Locally reproduced.**

- **Evidence:** [login redirect validation](../../../app.py#L2571), [probe](evidence/security-probes.json). `next=//example.invalid` returned a 303 with that external Location.
- **Repair:** one shared validator for local return destinations; reject network-path URLs, schemes, backslashes/control characters and ambiguous encodings. Review onboarding, language-switch and other return-URL consumers.
- **Acceptance:** legitimate internal deep links survive login/onboarding; all external or ambiguous destinations resolve to a safe local fallback.

## F06 — Authentication abuse controls and production defaults need hardening

**P1 · High potential security impact · Local behavior and source evidence; deployed configuration unknown.**

- Thirty wrong-password requests from one client returned 401 with no throttling. Login and reset handlers have no corresponding application rate limit. Edge controls, if any, were not inspected.
- Password policy accepts a commonly compromised eight-character numeric password. PBKDF2-SHA256 uses 200,000 iterations; [OWASP currently recommends 600,000 or more](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html) for this algorithm. Benchmark the selected replacement parameters on deployment hardware.
- An empty account table exposes first-admin creation through the public login flow. This becomes significant after an incorrect empty-database startup or restore.
- `CSS_SECURE_COOKIES` defaults off. Local application responses lacked CSP, nosniff, frame protection, HSTS, Referrer-Policy and explicit cache policy on the sampled response. These are local defaults; a reverse proxy may supply some headers.
- **Evidence:** [auth policy](../../../auth.py#L74), [login/bootstrap](../../../app.py#L2555), [cookie configuration](../../../app.py#L150), [probe](evidence/security-probes.json).
- **Repair:** controlled first-run setup; account and source-aware throttling that tolerates shared office NAT; reset limits; blocked compromised passwords; versioned hash migration on successful login; secure production startup assertions. Prefer organizational OIDC and stronger administrator authentication if the identity provider is available. Introduce CSP in report-only mode before enforcement, tailored to current scripts and embeds.
- **Acceptance:** an uninitialized public deployment cannot be claimed without the setup credential; throttling is observable and recoverable; old hashes migrate without locking out users; cookies and headers are verified at the public HTTPS endpoint; private responses have intentional cache rules. An identity-provider outage has a documented, controlled recovery route.

## F07 — Bearer URLs and sensitive AI text can enter operational records

**P1 · Medium privacy/security impact · Locally reproduced masking behavior.**

- **Evidence:** [path bucketing](../../../monitoring.py#L64), [AI interaction logging](../../../ai_core.py#L553), [deterministic answer logging](../../../app.py#L6043), [security probe](evidence/security-probes.json), [AI probe](evidence/authority-ai-probes.json).
- Calendar feed, room-request and room-display bearer URL paths survived log bucketing unchanged. Survey paths have existing masking; its coverage is incomplete.
- AI text masking removes emails and long digit runs but retains names and sensitive prose. Normalized questions can also be stored without that masking when prompt logging is enabled. Retention settings already exist; retention alone does not remove unnecessary sensitive fields.
- **Repair:** inventory sensitive routes/fields, log stable route templates instead of secrets, classify provider/log data, disable unnecessary prompt storage, enforce purpose-specific retention and access. Check edge/provider logs as well as application logs. Rotate any production bearer links found exposed after assessing their use.
- **Acceptance:** synthetic secret sentinels never appear in application/access/error/trace logs or analytics payloads; names/medical prose are handled according to the approved data policy; retention and deletion are tested end to end. No raw prompts or cookies in routine diagnostics.

## F08 — Dependency reproducibility and PDF resource isolation are insufficient

**P1 · High availability risk for affected parser paths · Local dependency scan; live versions unverified.**

- **Evidence:** [requirements](../../../requirements.txt), [PDF reader](../../../documents_reader.py#L294), [dependency summary](evidence/dependency-summary.json).
- The resolved local app/test set contained `pypdf 6.10.0`. The scanner returned 49 entries representing 31 distinct advisory IDs before alias deduplication, including CPU/memory exhaustion advisories. This is not 49 distinct confirmed exploits. The deployed package inventory must be checked separately.
- Examples include CVE-2026-41168 / GHSA-jj6c-8h6c-hppx (fix listed at 6.10.1) and CVE-2026-41312 (6.10.2). Other listed advisories require later versions; choose a release that resolves the entire applicable set.
- Existing size/page/text limits and public-IP checks for remote reads are useful. Parsing/decompression can consume substantial resources before page/text limits take effect. A thread timeout alone cannot reliably stop CPU-bound parsing.
- **Repair:** lock direct and transitive dependencies against the deployed Python version; generate an SBOM and scan the built artifact. Run untrusted PDF/OCR work in bounded processes with CPU, memory and wall-clock limits, explicit cancellation, and concurrency caps. Preserve SSRF protections and test redirects/DNS changes.
- **Acceptance:** deterministic builds; no unaccepted reachable high-impact advisories; hostile/oversized/corrupt documents terminate within limits without stalling ordinary requests. Successful multi-page intake and existing supported exports still work.

## F09 — Missing/NaN values can crash analytics and corrupt report narrative

**P1 · High reporting integrity/reliability impact · Locally reproduced.**

- **Evidence:** [organization filtering](../../../css_is_engine.py#L282), [trend statistics](../../../dashboard_insights.py#L496), [minimal probes](evidence/authority-ai-probes.json), [test summary](evidence/test-summary.json).
- Filtering a frame with a null organization path raised `ValueError`. A trend containing NaN raised `AttributeError` inside statistics. Seventeen full-suite failures clustered around these analytics/report paths. Five MRR narrative/export failures persisted in a focused rerun, including non-finite narrative content and mismatched activity/modality expectations.
- **Repair:** define missing, invalid, unrated, zero-denominator and insufficient-sample behavior once in the calculation layer. Filter finite numeric values explicitly; use null-safe scope masks. Trace MRR mapping/narrative defects separately rather than assuming one NaN fix solves all five.
- **Acceptance:** a maintained synthetic fixture independently establishes counts, means, scope, missingness and confidence/sample rules. HTML and all supported exports agree. No `nan`/`inf` prose or crashes for sparse/mixed data; invalid source records remain diagnosable rather than silently changing denominators.

## F10 — Deployment is not gated by a reproducible green test suite

**P1 · High release reliability impact · Repository and execution evidence.**

- **Evidence:** [deployment workflow](../../../.github/workflows/deploy-hf.yml), [preflight](../../../qa_preflight.py), [smoke harness](../../../qa_smoke.py#L201), [test summary](evidence/test-summary.json).
- Pushes to main trigger deployment with version and backup checks but no test/preflight job. The full suite finished with 3,968 passed, 48 failed and 16 skipped. Some failures reflect absent snapshot data and date-sensitive fixtures; others are independently reproduced defects. They cannot all be dismissed as environment noise.
- Native preflight was green with one missing-backup warning. When configured with a synthetic database, informational import output was treated as a template error. Its template scan also excludes nested template directories. The smoke harness ran 142 checks with one calendar rendering failure: it rendered a template without required request context. Browser calendar requests returned 200, so this smoke result alone does not demonstrate a broken live calendar.
- Docker targets Python 3.11; this audit ran 3.12. Pinning the actual runtime is part of making the baseline reproducible.
- **Repair:** deterministic synthetic fixtures, injected clock, recursive template validation and structured preflight output. Make tests, dependency review and integration smoke checks required before artifact promotion. Reconcile runbooks with actual persistence/deploy code. Extract modules only as they are changed, keeping public behavior stable.
- **Acceptance:** a fresh checkout of the release artifact passes documented gates on the deployment runtime without production data or secrets. Tests for F01–F11 fail before repairs and pass after them. A failed required gate prevents deployment. Rehearse upgrade and rollback with compatible database snapshots.

## F11 — Service worker can replay writes after an ambiguous proxy failure

**P1 · High integrity/reliability impact · Failure-injection reproduction.**

- **Evidence:** [retry logic](../../../static/js/sw.js#L14), [write interception](../../../static/js/sw.js#L123), [simulation](evidence/retry-probe.json).
- The service worker retries non-GET requests when a 5xx lacks `X-CSS-App`. Absence of this response header does not prove the origin never committed: a proxy can replace the response after execution. A simulation of commit followed by a proxy 503 produced two side effects and an eventual 200.
- This was a simulated failure, not an observed duplicate in production. Survey submissions already have deduplication IDs, and some document operations have strong receipts. These guarantees are not uniform across all writes.
- **Repair:** automatic retries only for reads or operations with durable idempotency semantics. Add operation keys and server receipts to prioritized writes; distinguish failed, pending, completed and unknown outcomes. For ambiguous outcomes query status before repeating.
- **Acceptance:** commit-then-drop-response, repeated clicks, reconnect and retry tests produce one business effect and a recoverable user status. Deploy a service-worker update with a new cache version and verify old clients adopt it; removing the code server-side alone does not replace cached client logic.

## F12 — Blocking work and fragmented job execution threaten responsiveness

**P2 · High availability impact under slow dependencies · Locally reproduced plus source inspection.**

- **Evidence:** [middleware](../../../app.py#L2219), [password reset mail](../../../app.py#L2792), [document external operation](../../../documents_routes.py#L618), [local measurements](evidence/performance.json).
- Synchronous database/notification work runs inside async middleware. Reset-mail delivery and some external document/backup operations also run synchronously inside async routes. A mocked 300 ms mail call produced about 309 ms of event-loop delay.
- Some AI/password operations already offload blocking work correctly. Newer document operations persist intent and receipts; reuse that design. The older scheduler has catch-and-continue paths and day-claim ordering that need observable recovery semantics.
- **Repair:** remove blocking I/O from the event loop, bound concurrency, then migrate long operations to durable jobs with leases, deadlines, retries, reconciliation and operator-visible failure. Do not hold database transactions while waiting for remote services. Use processes for work that needs enforceable CPU/memory termination.
- **Acceptance:** injected provider stalls do not stall unrelated requests; restart during a job recovers to a known/unknown reconciled state without duplicate delivery; queue depth, oldest job age and failures are visible. Cancellation and retries preserve business permissions and exact-version approvals.

## F13 — Request preparation and document lookup perform excessive queries

**P2 · Performance/scalability opportunity · Locally measured.**

- **Evidence:** [document list](../../../documents.py#L54), [middleware](../../../app.py#L2219), [measurements](evidence/performance.json).
- Home performed 219 statements; an authenticated CSS request performed 56, compared with zero for anonymous CSS. A visible-document list performed 22/202/2,002 statements at 10/100/1,000 documents. Per-record permission lookups explain this growth. FTS exists; it does not eliminate the registry scan by itself.
- Warm in-process pages on the small dataset were fast, about 10–15 ms. These query counts demonstrate avoidable work and growth, not a production latency claim.
- **Repair:** skip account/notification hydration for public static assets; reuse a request-scoped actor/permission context; move allowed-scope filtering into bounded SQL and add keyset pagination. Cache only with explicit invalidation and account/scope separation. Profile analytics refresh separately before replacing its existing incremental cache.
- **Acceptance:** zero application SQL for ordinary static assets, bounded first-page registry queries at 1,000 and 10,000 records, and materially lower Home query counts. Every old and new visibility rule passes equivalence tests, including restricted records and revocation. Measure p95 under representative concurrency before setting capacity commitments.

## F14 — Integration endpoints lack a usable external contract

**P2/P3 · Interoperability and maintainability opportunity · Generated-contract inspection.**

- **Evidence:** [OpenAPI inventory](evidence/api-contract.json), existing calendar/relay/document modules. The schema contains 362 paths and 411 operations, including 224 write operations, with no request-body schemas or declared security schemes. Authentication exists in middleware/handlers; this is not evidence that all routes are anonymous.
- Forms, ICS, exports and signed Workspace relays are useful integrations. Their conventions do not yet form a stable general API for external applications or agents.
- **Repair:** begin with a small `/api/v1` surface for selected document/work records and status. Publish typed inputs/outputs, permission scopes, pagination, errors, revision preconditions, idempotency and version/deprecation policy. Add service identities/delegated OAuth as needed and signed events with replay/delivery tracking. Keep UI, API and future MCP adapters on the same domain services.
- **Acceptance:** a separate sample client completes the chosen workflow using only published contracts; revoked/narrow credentials cannot cross scope; repeated events and writes are safe; errors and changes are contract-tested. No connector gets authority merely because it possesses the application's shared administrative credential.

## F15 — Model self-reported grounding is accepted as factual verification

**P1 containment; P3 expansion · High decision/data risk in optional AI mode · Provider-stub reproduction.**

- **Evidence:** [optional grounded-answer branch](../../../app.py#L6172), [probe](evidence/authority-ai-probes.json).
- Given a source fact of 2 responses, a stub model answered 999999 with `grounded=true` and confidence 0.99. The endpoint returned that answer as `served_by=grounded`. This proves the acceptance contract does not validate the numeric claim; it does not measure real-model hallucination frequency. Deterministic answers are an existing safer path, and AI is opt-in.
- **Repair:** retain deterministic rendering for official totals and calculations. Bind other answers to authorized source IDs, versions and timestamps; validate structured facts independently of model confidence. Define abstention and escalation. Treat retrieved documents, user prose and tool output as untrusted instructions. Apply F07 data minimization and F01/F03 permissions before expanding access.
- **Acceptance:** a versioned evaluation set covers numeric correctness, citations, stale facts, access revocation, no-answer cases, prompt injection and misleading tool output. Block official numeric answers that disagree with source facts. Pilot read-only use with budgets and observable fallbacks. Any later write requires explicit user intent, preview/confirmation, current authority, revision checks and idempotency.

## F16 — Confirmed accessibility defects and workflow hypotheses need focused UX work

**P2 · User experience/accessibility impact · Automated browser findings plus visual review.**

- **Evidence:** [browser results](evidence/browser-normal-results.json), [coverage summary](EVIDENCE.md#browser-and-accessibility-review).
- Confirmed examples: Home carousel ARIA-child errors and tiny targets; Home/dashboard/survey low contrast; a mobile Home scroll region not keyboard-accessible; nested interactive avatar controls on Wellness. Some measured contrast ratios were around 2.5:1, and survey N/A targets were approximately 13 px.
- All sampled pages returned 200 without recorded JS exceptions or page-wide overflow. Tests used Chromium, desktop/mobile widths and light theme; this is not a complete assistive-technology or usability audit.
- Home already has a personal to-do area. Further prioritizing actionable work, reducing acronyms, clarifying “what happens next”, and progressively revealing advanced document controls are hypotheses to validate with staff, not demonstrated usability failures or measured productivity gains.
- **Repair:** correct shared color/control/semantic patterns first, then pilot Documents-to-Work with staff, approvers and records personnel. Expand the proven patterns to rooms/calendar, travel and surveys. Preserve deep links, keyboard navigation and useful existing shortcuts.
- **Acceptance:** no critical/serious automated violations on agreed primary journeys; manual keyboard, focus, screen-reader, zoom and error-recovery checks pass. Aim for WCAG 2.2 AA, including 24 CSS px minimum targets where applicable and 44 px preferred touch targets. Capture task completion, time, assistance and wrong-action rates before and after; agree improvement targets from the baseline.

## Risk dependencies

Authority and revocation repairs (F01/F03) precede new API or AI access. Backup correctness and restore evidence (F02) precede schema/hosting changes. Release gates, dependency control and safe retries (F08/F10/F11) support every later phase. UX and performance changes must preserve the domain permission and approval rules already implemented.
