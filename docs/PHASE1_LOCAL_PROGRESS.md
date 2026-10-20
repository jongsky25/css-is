# Phase 1 local progress — candidate 7.24

**Current slice, 20 October 2026:** Browser defaults are merged/deployed as **7.48**; main **7.49** preserves same-origin referrers so login and saves can use the existing CSRF fallback. The current A08 dependency increment, candidate **7.50**, pins runtime/test/release dependencies and adds complete advisory scans and Python SBOM evidence; see [dependency maintenance](DEPENDENCIES.md). PDF/OCR process isolation is a separate increment. A07 log privacy and first-admin setup, login/reset throttling and password/hash changes are excluded from the current enhancement at the owner's direction. A10 release checks are implemented; requiring checks before merge still needs administrator configuration. Historical verification below is unchanged.

**Release integration, 20 October 2026:** the user authorized merging before further work. Main had advanced to 7.26, so the combined repairs are now version **7.27**, including the main-branch changes through `7b8f910`. Integration validation passed 486 tests with no failures/skips. See [release integration record](releases/7.27.md). The candidate 7.24 results below are retained as historical evidence.

Prepared 20 October 2026. Live verification is deferred at the user's direction; local implementation and synthetic testing continue. No production login, live data change, commit, push, merge or deployment was performed. This candidate includes the earlier [Phase 0 repairs](PHASE0_REPAIRS.md).

## Completed in this slice

### F05 / A05: safe return destinations

`request_security.safe_local_return` validates login, session response, onboarding, language switch (including its Referer fallback), directory return, room return, and PWA launch destinations. It rejects external schemes, network-path URLs, backslashes, controls, and nested encodings that expose dangerous separators. Validation is bounded by length and decode depth. Legitimate internal paths, query strings and fragments are returned unchanged. Room flows retain their narrower permitted destinations.

The helper's fallback is trusted application code, not user input. Conservatively rejected links land at the route's safe fallback. The common CSRF/origin boundary portion of A05 remains pending; this change does not claim to fix F04.

### F11 / A11: contain ambiguous automatic write replay

The service worker passes all non-GET requests directly to the browser. Its retry helper also refuses to retry a non-GET. A missing `X-CSS-App` header is no longer treated as evidence that the origin did not commit a write. GET retry behavior remains, and application-originated GET errors are not retried.

The worker cache generation is now `v7.24-a`. Existing install/activate behavior requests immediate activation, purges the previous app cache and claims clients; `/sw.js` remains served with `Cache-Control: no-cache`. Local execution verifies these lifecycle hooks. Adoption by already-installed production clients remains unverified.

The separate survey queue retains its existing submission-ID deduplication. Survey replay tests now create isolated synthetic forms instead of skipping without an open form in a database snapshot. This verifies sequential replay and normal submissions; it does not establish concurrency safety for every workflow.

A11 remains partial: durable operation IDs, result lookup, reconciliation, and user-facing unknown-result handling for priority mutations still need implementation. A manual resubmit or another client can still duplicate an operation that has no server idempotency contract. This repair removes the demonstrated service-worker replay path.

## Verification

- Before repair: the new tests reported 30 failures across unsafe return destinations and simulated write replay.
- After repair: **247 passed, zero failures, zero skips**, approximately 13 seconds.
- Included: safe return tests, the actual worker executed under Node with simulated network responses, PWA/survey deduplication, onboarding, authentication/cookies, Phase 0 authority/session/persistence regressions, and room navigation compatibility.
- The worker simulation covers POST/PUT/PATCH/DELETE after commit followed by proxy 500/502/503/504 or response loss; exactly one simulated business effect occurs. It also checks GET recovery, app-error handling, upload pass-through and cache lifecycle.
- Python tests use temporary local databases. No live service or production credentials are needed.
- Python 3.12.14 and local Node were used. Python 3.11 deployment parity remains unverified.
- The broader suite was not rerun for this slice. The previously documented 36 baseline-related failures remain unresolved; these focused results are not a claim that the entire suite is green.

Command:

```bash
CSS_NO_SCHEDULER=1 python -m pytest -q \
  tests/test_safe_returns.py tests/test_service_worker_retry.py tests/test_pwa.py \
  tests/test_onboarding_flow.py tests/test_auth_rbac.py tests/test_auth_async.py \
  tests/test_secure_cookies.py tests/test_phase0_security.py \
  tests/test_phase0_persistence.py tests/test_rooms_pages.py \
  tests/test_rooms_activity_pages.py tests/test_rooms_bump_pages.py --tb=short
```

Node is required for executable worker coverage; without it that test reports a skip, which is not acceptable as evidence for this slice. Machine-readable results and source hashes: [phase1/verification.json](phase1/verification.json).

## Next local sequence

1. **A05 / F04:** inventory browser writes, explicit public forms and machine callbacks; implement a consistent CSRF/origin policy, including login/account operations and deliberate handling of absent Origin. Preserve existing Documents/Work token checks and legitimate callbacks. Test actual boundary behavior before broad rollout.
2. **A09:** correct sparse/null/NaN analytics and report narratives against an independent synthetic reference dataset; reconcile browser/export totals.
3. **A10:** make remaining fixture/date failures deterministic and establish required release checks on the exact deployment runtime. Retain diagnosed failures with owners rather than blanket skips.
4. **A11 remainder:** add durable idempotency/status to the chosen priority workflow before expanding external jobs or write integrations.

Managed organizational authority (A04) still needs reviewed assignment data; identity/provider/retention decisions remain dependent on owner input. Defer those data-dependent changes while working on the local sequence.

## Deferred evidence and promotion

Live environment discovery, actual backup recovery, current leadership assignment review, installed-client update adoption, and deployment/runtime behavior remain open evidence gaps. Deferring them permits local work, not a claim of production readiness. Retain the review branch; `main` currently auto-deploys. Prefer forward fixes that retain the Phase 0 security boundaries.

The earlier transfer archive represents the prior 7.23 snapshot; current 7.24 work is in this workspace and must be included in any future transfer.
