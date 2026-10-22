# Supported integration API — A19 / 7.97

The read contract introduced in 7.92 now supports one explicit task action: acknowledge a confirmed contribution as in progress. Selected document/work metadata, task status and acknowledgement use existing human sessions and current domain permissions. The API contract is **1.1.0**, mounted at **`/api/v1`**; its version is independent of the application's release number.

The [generated OpenAPI artifact](api/v1/openapi.json) is checked against the running contract in tests. The authenticated live contract is `GET /api/v1/openapi.json`. Existing browser form actions and the application's older general OpenAPI output are outside this supported contract.

## Routes

| GET route | Result |
|---|---|
| `/api/v1/` | API version, application version, `read_only: false` capability and contract URL |
| `/api/v1/documents` | Page of permitted document metadata |
| `/api/v1/documents/{document_id}` | Current permitted canonical document metadata |
| `/api/v1/work-items` | Page of permitted shared-work items |
| `/api/v1/work-items/{work_item_id}` | One permitted shared-work item |
| `/api/v1/work-items/{work_item_id}/tasks` | Page of contributions within a permitted work item |
| `/api/v1/work-items/{work_item_id}/tasks/{task_id}` | One contribution and its current status/revision |
| `/api/v1/write-context` | Session-bound CSRF token for an explicit acknowledgement |
| `/api/v1/operations/{operation_id}` | The current user’s recorded acknowledgement result, subject to current target access |

The only supported POST is `/api/v1/work-items/{work_item_id}/tasks/{task_id}/acknowledge`. It returns an operation receipt; all other resources retain GET-only access.

Document fields include number, subject, direction, type, status, verification, deadline, revision, timestamps and API/web links. Work fields include title, concerned-unit ID, confirmed-lead ID, deadline, revision, timestamps and links. Task fields include title, work-item ID, confirmed-owner ID, status, deadline, revision, timestamps and links. The contract deliberately projects these fields; it does not serialize database rows wholesale.

File contents/URLs, email metadata, instructions, submission prose, credentials, grants, review notes, operation diagnostics and signatures are outside these responses. Work items have no new synthetic overall status: document lifecycle and task contribution statuses retain their distinct domain meanings. A confirmed task is not a released document.

## Authentication and current access

Use an existing registered `css_session` cookie obtained through the normal login flow. The API uses the same signature, expiry, account-state and database-session checks as the screens. Password/role changes, session logout/revocation and deactivation apply on subsequent requests. Business reads also reload the current actor and evaluate current role grants, directory authority, assignments and restricted-document access inside a read snapshot.

A technical administrator does not gain document/work access through the API. Proposing a lead/owner does not grant readership. Work visibility requires the existing case audience **and** access to every linked document after canonical merges. Reassignment and restricted-access revocation are checked again on the next request. Missing and inaccessible objects return the same 404 response.

This increment serves authenticated, human-operated clients. Scoped service identities, delegated OAuth and unattended integrations belong to A20. API keys, bearer-token authentication and new token-issuance routes are not introduced here. Clients should use an approved person's current session only for that person's work; session values belong in private local storage and must stay out of repositories, logs and AI prompts.

All API namespace responses use private/no-store caching. API requests skip browser navigation, notification and feedback hydration. GET requests read business records without marking instructions as read, sending provider requests or creating domain audit/history entries. Existing HTTP monitoring remains active. Existing permitted records remain readable when the Documents/Shared work write switches are off, matching the screens.

Browser clients use same-origin requests. No cross-origin CORS access is enabled. Non-browser clients use HTTPS; the example permits loopback HTTP for isolated local tests.

## IDs, time and pagination

- Resource IDs, account/unit references and `next_before` are decimal **strings**. This preserves SQLite identifiers beyond JavaScript's exact-integer range. Treat IDs as identifiers rather than numbers; valid resource paths use positive decimal IDs through SQLite's signed 64-bit maximum.
- `revision` is the current integer revision of that entity. A case's revision is independent of its tasks' revisions. Acknowledgement requires the exact task revision; outdated revisions produce 409 without a new change.
- Timestamps are ISO 8601 with an explicit offset. Existing naive stored timestamps use the configured application offset (`CSS_TZ_OFFSET`, normally `+08:00`); already-aware timestamps retain their offset. `due_date` is an ISO calendar date or null.
- Page queries accept `limit` from 1–100 (default 25) and a `before` cursor (default 0 for newest). Pass the previous page's `next_before` unchanged. Records are ordered newest ID first; document cursors use the existing registry's canonical/alias sort position and may differ from a returned canonical resource ID.
- Document lists also accept `q` (up to 200 characters) and `queue`: `all`, `IN`, `OUT`, `mine`, `review`, `release`, or `archived`. Search reuses the existing permission-filtered registry selection with snippets and full-source bodies omitted.
- A list returns `{"data": [...], "page": {"limit": 25, "has_more": true, "next_before": "123"}}`. End of results is `has_more: false` and `next_before: null`. No global/hidden-record counts are returned. Unknown or duplicate query parameters are rejected.

Selections are permission-filtered before the page limit. Shared-work paging now uses a SQL counterpart of its existing detail predicate, compiled from the same current document authority helper, for both UI and API. Newer hidden records do not create an empty scan page or a cursor containing a hidden case ID. Task reads first require access to their work item and never accept a task from a different parent.

Each business read uses a database read snapshot. Separate page requests are fresh reads: new merges, source edits and access changes can change later pages. This is not an immutable report/export snapshot or a synchronization/change-feed protocol; consumers reconciling a changing dataset should use entity IDs and revisions.

Merged document detail requests return the permitted canonical record's ID and metadata. Obsolete source titles/statuses are not returned. Damaged merge cycles fail closed.

## Response and error contract

Success is JSON: one typed resource for detail routes, or the list envelope above. The self/web links are relative to the deployment origin. Treat subject/title strings as untrusted source data; consuming AI tools should not interpret them as permission to perform actions.

Errors use `{"error": {"code": "not_found", "message": "Resource not found or unavailable to you."}}`.

| Status | Code | Client action |
|---|---|---|
| 400 | `invalid_request` | Correct bounded paths, headers, query or JSON fields |
| 403 | `request_verification_failed` | Fetch the current write context and verify the request origin |
| 401 | `authentication_required` | Sign in through the existing flow |
| 404 | `not_found` | Check the ID/current access; absence and denied access are indistinguishable |
| 405 | `method_not_allowed` | Use the method declared by `Allow` |
| 409 | `revision_conflict` | Read the current task before deciding on a new request/key |
| 409 | `idempotency_conflict` | A key already belongs to different input; check the saved original request |
| 409 | `action_unavailable` | Check feature switches and the current workflow in the screens |
| 413 | `request_too_large` | Keep the UTF-8 JSON body within 8,192 bytes |
| 415 | `unsupported_media_type` | Use `application/json` |
| 503 | `temporarily_unavailable` | Check the result, then retry the identical request/key if needed |
| 500 | `internal_error` | Retry reads later; for writes, check the operation result before retrying the identical request/key |

Anonymous requests return JSON 401 without redirecting to login. PUT/PATCH/DELETE, HEAD and OPTIONS are unsupported, as are POSTs outside the acknowledgement route; authenticated requests receive JSON 405 (HEAD has no response body). Validation returns the documented 400 envelope rather than FastAPI's generic 422 body. Browser routes retain their existing forms, redirects and same-origin write checks.

## Standalone client

[examples/read_api.py](../examples/read_api.py) uses only Python's standard library and has no application imports. It pages documents or work items, preserves string identifiers, bounds response size/time, refuses redirect forwarding of sessions and handles HTTP errors without printing credentials or response bodies.

```sh
python examples/read_api.py \
  --base-url https://office.example/api/v1 \
  --session-file /private/path/current-session.txt \
  --resource documents
```

The session file contains only the cookie value from an authorized signed-in session. Protect and remove it according to the operator's session policy. This example does not automate passwords or provision an integration identity. `ReadClient.get()` accepts API-relative paths such as `/documents/123` and the origin-relative `/api/v1/...` self links.

## Explicit acknowledgement and recovery

1. Read the task and let the authorized operator decide to start it. The existing owner **or scoped officer** may acknowledge a confirmed `todo` task. Being a case creator, proposed owner, lead or technical administrator does not independently grant this action.
2. Save a fresh lowercase UUID v4 operation key and the exact target, task revision and reason in private client storage **before sending**. The key is not a credential. Never generate a replacement automatically after a timeout.
3. `GET /api/v1/write-context` returns `{"csrf_token":"..."}`. Use the current registered session cookie for both requests. Tokens are bound to that session; a new login needs a new write context.
4. Send POST with `Origin` matching the configured deployment origin, `X-CSRF-Token`, `Idempotency-Key` and `Content-Type: application/json`. There are no query parameters. Body: `{"revision":2,"reason":"Starting my assigned contribution"}`. Revision must be an integer from 1 through 9,223,372,036,854,775,806; reason must be a nonblank string of at most 2,000 characters. Unknown JSON fields, duplicate members/headers, boolean/string revisions and oversized bodies are rejected. Bodies are limited to 8,192 UTF-8 bytes, including streamed requests.
5. Success is HTTP 200 with `id`, `action: acknowledge`, `status: succeeded`, string `work_item_id`/`task_id`, `result_revision`, `result_status: in_progress`, offset-aware `completed_at` and relative `links.self`/`task`/`web`. Neither reason nor task prose is copied into the public receipt.
6. After a lost response, use `GET /api/v1/operations/{saved-key}`. If unavailable, first check the session and current target access. A 404 may mean no committed receipt **or** lost access; it does not prove the change failed. Once current access is confirmed, resending the identical request/key safely returns the original receipt or attempts the action once. A received validation/permission/conflict response does not reserve a key.

The request fingerprint includes action, parent/task IDs, revision and exact reason text. An actor reusing a committed key with different input gets 409, subject to current access checks. A different signed-in actor has a separate key namespace. A newly registered session for the **same actor** can recover the receipt. Other users cannot read it, including technical administrators.

The write acquires SQLite's writer transaction before rechecking the registered session, current grants, linked documents, feature switches, case state, task revision and shared UI action rules. Task update, work history/audit, review invalidation and receipt commit together. A process failure before commit leaves none of these changes; a failure after commit leaves a readable receipt. There is no external side effect or queued background job. Only completed operations are stored; the contract does not invent pending/failed states.

A replay only returns the original recorded result and creates no new task/history changes. Existing receipts remain readable and replayable with current access when write switches are disabled. Reassignment or restricted-document/grant changes may remove both target and receipt access. The receipt's revision/status describes the original acknowledgement, **not the task's current state**; follow `links.task` for the latter.

Receipts are immutable and retained without automatic expiration, preserving retry protection across restarts and releases. Do not clear this table as routine log cleanup. Database restore can rewind both task state and receipts to the snapshot: after a restore, reconcile with operators before resending old requests. No exactly-once guarantee is made across restore to an older snapshot or independent databases.

`TaskClient` in [examples/read_api.py](../examples/read_api.py) extends `ReadClient` with `acknowledge(work_item_id, task_id, revision=..., reason=..., operation_id=saved_key)` and `operation(saved_key)`. It requires string IDs and an explicitly saved key, fetches the write context, sends the matching origin and never automatically retries POSTs. The existing CLI remains read-only. Protect the saved request because its reason may contain private work information. No password automation, machine identity, AI tool or document-approval authority is added.

## Verification and remaining A19 work

The original 7.92 read/survey evidence remains below. For 7.97, the API/work/deployment/release regression set passed **271 tests** in shuffled order (seed 311), with no failures or skips. The final read/write API set passed **84 tests** in shuffled order with no failures or skips, including real writer contention, completed-case refusal and recovery with a newly registered session and unresolved migrated-document operations. After incorporating main’s 7.93 ARTA date filters, the combined API/ARTA/release set passed **114 tests** in shuffled order with no failures or skips. After also incorporating main 7.95, **118 API/ARTA/release/deployment tests** passed in shuffled order without failures or skips. After incorporating main 7.96, the API/travel-review/release/deployment checks passed **123 tests** in shuffled order without failures or skips. Required CI verifies the complete final head.

- Broad local API/survey/shared-work/registry/deployment regression: **289 passed**, no failures or skips. Final contract/survey verification in shuffled order: **50 passed**, no failures or skips. Final required CI verifies the complete head.
- Authenticated HTTP tests cover typed schema/artifact agreement, current session/account/grant revocation, technical-admin boundaries, restricted/canonical document access, linked-case intersection, task reassignment/parent scoping, invalid and duplicate parameters, private errors and read-only business-state invariants.
- Pages are reconciled against the existing Python work-detail predicate across staff/officer/technical-admin audiences. A 270-record hidden population does not hide an older visible page. IDs above 2^53 retain their exact string value. Actual generated work statements run on the OS SQLite too.
- The standalone client reads the real application through an isolated local HTTP bridge, follows pages and self links, refuses an actual 302 trap, and receives 401 after session revocation. No production business records or external providers are used.
- The remaining combined-survey confirmation race is exercised in English and Filipino with a deliberate 300ms deferred-script delay. The check waits for matching draft removal and retains actual saved-count/skip assertions; survey runtime behavior is unchanged.

The 7.97 increment covers acknowledgement preconditions and its operation-result contract. Other approved task actions and external-operation contracts remain later A19 increments. A20 supplies scoped integration identities; A21 adds reliable events/adapters. Production workflow observations remain deferred, and no production throughput claim is made.

## Release and rollback

7.97 increments verified main 7.96 with aligned release/cache metadata. The runtime inventory includes `integration_operations.py`. The repeatable shared-work installer adds `work_api_operation` and immutable-receipt triggers; existing tables/rows are not rewritten and no new dependency is required. To disable the new action, deploy a newly versioned forward repair that keeps receipt lookup available. If restoring earlier application behavior, retain the additive table and existing receipts, coordinate clients and preserve acknowledged task/history state. Do not delete successful changes or receipts to roll back code. Existing deployment backup gates and SQLite online backups cover the new table.
