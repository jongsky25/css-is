# Connected tools — A20 / 7.99

This increment gives each approved tool a separate credential to read selected Office Connect metadata on behalf of an existing user. The tool does not need that user's password or browser cookie. These are delegated read credentials, not independent service accounts or OAuth grants.

## Authorize and connect

1. Sign in normally, open **My profile → Connected tools**, and give the tool a recognizable name.
2. Select **Document metadata**, **Work and task metadata**, or both. Subjects/titles, owner IDs, dates and task status may be private information; authorize only a tool that should receive those fields. Body text, submissions/evidence, private messages, files/URLs, grants and review notes are excluded.
3. Choose an expiry of **7 days** (default), **30 days** or **90 days**, confirm the stated consent, and enter your current password. Issuance requires a current registered session, matching origin and a session-bound CSRF token. At most 20 unexpired credentials may belong to one owner.
4. Save the displayed secret directly in the tool's private credential store. The complete secret is shown **once** in a private/no-store response. It cannot be recovered from the management screen. Never put it in a URL, repository, shared document, log or AI prompt.
5. Call the documented HTTPS API with `Authorization: Bearer <saved credential>` and **no session cookie**. There is no password login, refresh or credential-issuance API for the tool.

If the create response is lost, check the tool list and revoke any newly created credential you could not save before creating a replacement. Issuance is not an automatically retried client operation. The browser screens are `/account/integrations` (own credentials) and `/admin/integrations` (account administrators' revocation inventory). Lists page 100 entries at a time and never return hashes or recoverable secrets.

The [API contract](INTEGRATION_READ_API.md) and [OpenAPI artifact](api/v1/openapi.json) define the supported resource projections, pagination and errors. Current OpenAPI version: **1.3.0**. Application version: **7.99**.

## Allowed reads

| Credential scope | Allowed endpoints |
|---|---|
| Either valid scope | `GET /api/v1/`, `GET /api/v1/openapi.json` |
| `documents:read` | Document metadata list and detail |
| `work:read` | Work-item list/detail and task list/detail |

The API root reports `authentication: scoped_read_credential` and `read_only: true` for these credentials. OpenAPI marks selected metadata reads with `x-integration-scope`; bearer authentication is absent from task-write, write-context and operation-receipt security declarations.

Every non-GET method is refused, including task acknowledgement/submission, acceptance, return, cancellation and any future mutation route. Write context, human operation receipts, browser screens, uploads, downloads and other application APIs are outside the credential boundary. Unknown API paths are refused too. These credentials do not turn a tool into an approver. Existing human-session task API behavior remains unchanged.

## Current authority and audience

Credentials inherit their owner's **current** domain authority, bounded by the scopes selected at issuance. They do not grant an administrator document readership or widen unit, assignment, canonical-document or restricted-record access. Reads revalidate the credential and owner in the business read snapshot; every linked document must remain readable. Domain grant and assignment changes affect the next read. An owner receiving additional domain access may expose additional metadata within the selected credential scope, so keep scopes and ownership appropriate for that tool.

Credentials are bound to the configured deployment origin and `/api/v1`. Production must set the canonical `CSS_BASE_URL` (or the existing server-provided `SPACE_HOST`); development falls back to the request origin. Untrusted forwarded-host headers do not select an audience. A copied database on a differently configured deployment does not accept the original audience's credentials. This is an opaque credential checked by the application, not a JWT or an OAuth token.

Invalid/expired/revoked credentials return private JSON 401. A present invalid Authorization header, duplicate authorization headers or combined cookie/bearer identities never fall back to a browser session. Missing or inaccessible records remain indistinguishable 404s; a valid credential without the required scope gets 403. No cross-origin browser CORS access is enabled. HTTPS is required for remote clients; the example permits HTTP on loopback only for isolated local testing.

## Expiry, revocation and rotation

- Expiry is enforced at the exact stored expiry second. No refresh token or automatic extension exists.
- Owners can revoke their credentials; account administrators can revoke any listed credential. Revocation rechecks the current registered session and owner/administrative authority while holding the database writer lock.
- Password/hash/salt, username, role, active/reset-required state, directory-account link and bureau-access changes permanently revoke that account's existing credentials through database triggers. Re-enabling an account does not restore those credentials. Domain grants and assignments are checked live rather than frozen into the secret.
- Browser logout closes that browser session; independently authorized tools continue until expiry, explicit revocation or an account change. Revoke a credential separately when disconnecting a tool.
- Rotate by issuing a new credential, updating the tool, checking a permitted read, then revoking the old credential. Replacement does not extend or modify the old grant.
- A request already in progress can finish using its authorized snapshot. Revocation applies to subsequent authentication and read checks; it is not cancellation of an already delivered response.

The secret contains 256 random bits plus a random public credential ID. Only its SHA-256 digest is stored. Hash comparison is constant-time. Scope, owner, audience, name and expiry are immutable after issuance; a revoked credential cannot be restored by an update. The credential table and indexes are installed additively and repeatably without changing existing users, sessions, domain records or operation receipts.

Routine recovery from the newest durable snapshot preserves eligible credentials across restarts. An operator-selected historical database restore revokes all restored credentials and clears browser sessions, preventing a snapshot from reviving previously revoked access. After such a restore, owners must sign in and explicitly authorize fresh credentials. Restoring database files outside the supported restore path requires the same credential revocation step before serving requests.

## Audit and operational limits

Issuance and explicit revocation commit atomically with the existing security audit chain. Credential reads record the owner, public credential ID, resource family (`contract`, `documents`, `work` or `unsupported`), supported method and HTTP status, plus last use. Raw URLs, query strings, bodies, secret values and returned record prose are excluded. Existing HTTP monitoring attributes these requests to `integration:<public ID>` and does not create browser feedback/error events for them.

Business reads remain reads; recording their security access uses a short serialized SQLite write **after the business snapshot closes**. Successful data is not sent if that audit write fails. Busy storage returns private 503 with `Retry-After`; another audit failure returns private 500. This adds one small security write per admitted credential request and is not a throughput claim. Audit history follows the existing retention/backup policy; monitor its size before expanding polling traffic.

The existing in-process limiter admits at most **120 credential requests/minute per owner across credentials** by default (`CSS_RL_INTEGRATION_READ`), including requests denied for scope or method. Limited requests return 429/`Retry-After: 60` and do not generate another audit write. Current-password confirmation/issuance attempts are capped at **5 per 15 minutes per owner** (`CSS_RL_INTEGRATION_ISSUE`); the UI reports when to retry. These counters are local to the existing single-worker process and reset on restart; the database's 20-active-credential limit remains serialized and durable. Multiple workers or independent replicas need coordinated admission control before expanding deployment.

## Independent client

```sh
python examples/read_api.py \
  --base-url https://office.example/api/v1 \
  --credential-file /private/path/tracker-credential.txt \
  --resource work-items
```

The client uses only the Python standard library. Choose exactly one of `--credential-file` and `--session-file`. It never sends both authentication types, follows redirects with a credential, retries writes automatically, or prints credentials/response bodies in errors. Normal command output contains authorized metadata; protect it accordingly. In Python: `ReadClient(base_url, credential=saved_secret)`.

## Rollout and recovery

Proposed release 7.99 follows freshly checked main 7.98. Application/cache/changelog metadata move together; runtime packaging includes both credential modules and the template. There are no new dependencies or external provider requests. Existing verified-backup and deployment gates apply.

For an integration incident, revoke the affected credential or revoke all of an owner's credentials by an account security change, then issue replacements only after review. Prefer a forward repair preserving the credential table, revocations and security history. Code 7.98 does not accept these bearer credentials; if temporarily returning to it, retain the additive schema and revoke affected credentials before re-enabling newer code. Never erase revocation/history to restore access. Historical-restore revocation must also be retained if restoring application code.

## Verification and remaining work

Local verification: **321 tests passed** in the shuffled API/authentication/security/browser-policy/release/deployment regression set (seed 311), with no failures or skips. After final admission-control and restore changes, **116 API/credential/Chromium/backup tests passed** in shuffled order, with no failures or skips. The final **3** concurrent-issuance and desktop/mobile independent-client boundary checks passed, including refusal to forward bearer credentials through redirects. These sets overlap and are not additive totals. Release metadata, dependency-lock inputs, vendored dependency integrity, Python compilation and whitespace checks also passed. Required CI verifies the complete PR head.

Synthetic local checks cover real password/consent forms, scope ceilings, current linked-document/grant authority, account-change triggers, audience, expiry, mixed/duplicate identities, method/endpoint restrictions, private audit attribution, audit rollback, rate limits, concurrency, repeatable installation and paginated management. Desktop/mobile Chromium journeys use actual HTTP forms and an independent bearer client through read and revocation. Production business-workflow observations remain deferred; no real provider account or production record is used.

Independent service principals, delegated OAuth consent flows, machine writes and external adapters remain later increments based on actual client needs. Existing human approvals remain outside this credential boundary.
