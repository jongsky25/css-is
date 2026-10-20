# Browser write protection — candidate 7.28

20 October 2026. Implements the remaining local A05/F04 request-boundary work after safe return URLs shipped in 7.27. Branch: `fix/phase1-request-origin`. Live verification remains deferred. This candidate has not been merged or deployed.

**Release decision:** the owner subsequently authorized merging and deploying this slice as **7.28**. Source hashes, application version, worker generation, and deployment packaging were checked before publishing. The earlier local results and deferred production checks below remain the evidence baseline; deployment outcome is recorded by the GitHub Actions run associated with the merge.

## Policy

All authenticated writes and public account operations require an exact request origin: scheme, hostname and effective port must match. A normal browser sends `Origin` with POSTs. When Origin is absent, a same-origin `Referer` is accepted. When either is present it must be valid; conflicting headers, duplicates, `Origin: null`, sibling hosts, wrong schemes/ports, and cross-site Fetch Metadata are rejected. Requests with neither Origin nor Referer are rejected. Missing browser metadata alone does not grant an exception.

The middleware runs before handlers read request bodies, so JSON, forms, multipart and binary uploads share the boundary without buffering uploads. Unauthenticated protected writes retain their existing 401 response. Authorization still resolves the current session and permissions. Documents and Work keep their existing session-bound CSRF tokens; a valid module token does not override a foreign Origin, and a valid Origin does not replace those tokens.

This is an **origin-verification CSRF policy**, not a new universal form-token scheme. Native clients can set Origin, but still need valid credentials and authorization. The browser prevents another website from forging its own Origin while using the victim's cookies.

Logout now revokes sessions only through POST. Desktop/mobile navigation uses a form button. GET `/logout` shows confirmation without revoking the session, so cross-site navigation and link prefetching cannot silently sign a user out.

## Trusted deployment origin

The expected origin is selected in this order:

1. Server-configured `CSS_BASE_URL`, such as `https://equityinhealth-office-connect.hf.space` (origin only).
2. `https://` plus the server-provided Hugging Face `SPACE_HOST` hostname.
3. The ASGI request's base origin, suitable for local development or a correctly configured trusted reverse proxy.

Caller-supplied `X-Forwarded-Host` and `X-Forwarded-Proto` are not independently trusted by these checks. Canonical configuration takes precedence over request headers. If TLS terminates at a proxy, configure the public HTTPS origin or ensure trusted proxy handling produces the correct ASGI scheme. Do not loosen matching to sibling domains or disable the boundary to fix a misconfigured proxy.

An incorrect canonical setting intentionally causes 403 responses. Confirm the deployment's actual origin/configuration before promotion; that environment evidence remains deferred. Reopening an old page with a different origin requires navigating to the configured origin and signing in there.

## Explicit exceptions

The inventory covers **225 write operations: 211 origin-protected operations and 14 explicit POST exceptions**. Exceptions match complete routes, not public prefixes, and do not apply to PUT/PATCH/DELETE or newly added child paths. The authoritative list and rationale live in `request_security.CSRF_EXCEPTIONS`; [write-routes.json](phase1/csrf/write-routes.json) enumerates every current operation.

| Contract | Independent controls retained |
|---|---|
| `/r/{qr_token}`, `/seq` | Public survey tokens, response windows, submission-ID deduplication |
| `/e/{event_token}`, `/e/{event_token}/email-link` | Public event token, registration validation, rate-limited recovery |
| `/room` | Anonymous external request validation, rate limit and honeypot |
| `/room/t/{token}/withdraw`, `/take`, `/meals`, `/meals/start` | Signed tracking token, external reservation constraints |
| `/rooms/decide/{rid}`, `/wellness/decide/{claim_id}` | Signed decision token and handler's current-approver checks |
| `/whereabouts/week` | Signed user/week token |
| `/offsite-backup/ping` | Shared `X-Backup-Token` secret |
| `/integrations/gmail/documents` | Timestamped body HMAC, replay/deduplication controls |

These handlers do not derive mutation authority from a login cookie. Their existing validation still runs even when no origin is supplied. This work does not convert public endpoints into authenticated ones or claim their separate abuse controls are complete.

## Maintenance client compatibility

Cookie-based scripts must send the application's canonical origin with writes, for example `Origin: https://equityinhealth-office-connect.hf.space`. `pull_backup.py` now supplies it for login and fresh-snapshot requests; `close_feedback.py` inherits that helper, and `refile_lost_feedback.py` supplies it for feedback writes. Update scripts before using the new server. The deployment backup gate continues to use the updated helper, with no bypass.

Browser forms and fetch calls need no new JavaScript token injector. Keep current module tokens where required. Clients that suppress both Origin and Referer deliberately receive 403; use a normal same-origin browser flow or an authorized native client with an explicit Origin.

## Local evidence

- The final focused suite covers origin parsing, all protected write routes, account operations, logout, valid/invalid module tokens, survey replay, signed callbacks, maintenance client headers, auth, Work, Travel, Documents, room/whereabouts flows and deployment packaging. Exact results: [verification.json](phase1/csrf/verification.json).
- A real local Chromium browser logged into a synthetic database, then submitted a form from a different origin on the same host. Its valid session cookie was sent, the response was 403, and the setting remained unchanged. A same-origin write succeeded. GET logout retained the session and POST logout cleared it. [Browser results](phase1/csrf/browser.json).
- The broad run collected 4,196 tests: **4,145 passed, 35 failed, 16 skipped**. Of those failures, 33 match the prior Phase 0 failure inventory. Two were test assumptions affected by this change: a read-only-page assertion incorrectly included the shared logout button, and a client used `http://testserver` while its canonical setting was `https://office.example.org`. Both were corrected and rerun in the final focused suite. The full suite was not repeated after those corrections and the final additional cases.
- TestClient fixtures now explicitly model browser Origin headers; hostile/missing-header tests remove or override that default. The production boundary is exercised, not bypassed. The local Chromium check separately confirms real browser behavior.
- Runtime: local Python 3.12, with Node for the service-worker regressions. Exact deployed Python 3.11 and production proxy behavior remain unverified. No production credentials or data were used.

## Promotion and next slice

Application version and worker generation are prepared as 7.28; shared CSS asset URLs are refreshed for the logout buttons. No database migration is required. Inspect canonical origin configuration before rollout and retain the existing deployment backup gate. If an origin configuration is wrong, correct that configuration rather than removing the protection. Main currently auto-deploys, so this candidate remains on its review branch.

The next local package is A09: sparse/null/NaN analytics and report narratives, using independent reference totals and browser/export comparisons. A10 will address deterministic release tests and runtime parity. The broader audit findings remain tracked separately.
