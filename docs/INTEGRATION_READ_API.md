# Supported read API — A19 / 7.92

This is the first supported integration contract, following the survey/report improvements in 7.90–7.91. It exposes selected document/work metadata and task status through existing human sessions and current domain permissions. The API contract is **1.0.0**, mounted at **`/api/v1`**; its version is independent of the application's release number.

The [generated OpenAPI artifact](api/v1/openapi.json) is checked against the running contract in tests. The authenticated live contract is `GET /api/v1/openapi.json`. Existing browser form actions and the application's older general OpenAPI output are outside this supported contract.

## Routes

| GET route | Result |
|---|---|
| `/api/v1/` | API version, application version, read-only capability and contract URL |
| `/api/v1/documents` | Page of permitted document metadata |
| `/api/v1/documents/{document_id}` | Current permitted canonical document metadata |
| `/api/v1/work-items` | Page of permitted shared-work items |
| `/api/v1/work-items/{work_item_id}` | One permitted shared-work item |
| `/api/v1/work-items/{work_item_id}/tasks` | Page of contributions within a permitted work item |
| `/api/v1/work-items/{work_item_id}/tasks/{task_id}` | One contribution and its current status/revision |

Document fields include number, subject, direction, type, status, verification, deadline, revision, timestamps and API/web links. Work fields include title, concerned-unit ID, confirmed-lead ID, deadline, revision, timestamps and links. Task fields include title, work-item ID, confirmed-owner ID, status, deadline, revision, timestamps and links. The contract deliberately projects these fields; it does not serialize database rows wholesale.

File contents/URLs, email metadata, instructions, submission prose, credentials, grants, review notes, operation diagnostics and signatures are outside these responses. Work items have no new synthetic overall status: document lifecycle and task contribution statuses retain their distinct domain meanings. A confirmed task is not a released document.

## Authentication and current access

Use an existing registered `css_session` cookie obtained through the normal login flow. The API uses the same signature, expiry, account-state and database-session checks as the screens. Password/role changes, session logout/revocation and deactivation apply on subsequent requests. Business reads also reload the current actor and evaluate current role grants, directory authority, assignments and restricted-document access inside a read snapshot.

A technical administrator does not gain document/work access through the API. Proposing a lead/owner does not grant readership. Work visibility requires the existing case audience **and** access to every linked document after canonical merges. Reassignment and restricted-access revocation are checked again on the next request. Missing and inaccessible objects return the same 404 response.

This increment serves authenticated, human-operated clients. Scoped service identities, delegated OAuth and unattended integrations belong to A20. API keys, bearer-token authentication, new token-issuance routes and API write actions are not introduced here. Clients should use an approved person's current session only for that person's work; session values belong in private local storage and must stay out of repositories, logs and AI prompts.

All API namespace responses use private/no-store caching. API requests skip browser navigation, notification and feedback hydration. Business records are read without marking instructions as read, sending provider requests or creating domain audit/history entries. Existing HTTP monitoring remains active. Existing permitted records remain readable when the Documents/Shared work write switches are off, matching the screens.

Browser clients use same-origin requests. No cross-origin CORS access is enabled. Non-browser clients use HTTPS; the example permits loopback HTTP for isolated local tests.

## IDs, time and pagination

- Resource IDs, account/unit references and `next_before` are decimal **strings**. This preserves SQLite identifiers beyond JavaScript's exact-integer range. Treat IDs as identifiers rather than numbers; valid resource paths use positive decimal IDs through SQLite's signed 64-bit maximum.
- `revision` is the current integer revision of that entity. A case's revision is independent of its tasks' revisions. Future API writes need a separate revision/precondition contract; this release accepts GET reads only.
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
| 400 | `invalid_request` | Correct the bounded path/query parameters |
| 401 | `authentication_required` | Sign in through the existing flow |
| 404 | `not_found` | Check the ID/current access; absence and denied access are indistinguishable |
| 405 | `method_not_allowed` | Use GET; the response declares `Allow: GET` |
| 500 | `internal_error` | Retry a read later; internal exceptions and submitted values are not returned |

Anonymous reads return JSON 401 without redirecting to login. POST/PUT/PATCH/DELETE, HEAD and OPTIONS are outside this read contract; authenticated requests receive JSON 405 (HEAD has no response body). Validation returns the documented 400 envelope rather than FastAPI's generic 422 body. Browser routes retain their existing forms, redirects and same-origin write checks.

## Standalone client

[examples/read_api.py](../examples/read_api.py) uses only Python's standard library and has no application imports. It pages documents or work items, preserves string identifiers, bounds response size/time, refuses redirect forwarding of sessions and handles HTTP errors without printing credentials or response bodies.

```sh
python examples/read_api.py \
  --base-url https://office.example/api/v1 \
  --session-file /private/path/current-session.txt \
  --resource documents
```

The session file contains only the cookie value from an authorized signed-in session. Protect and remove it according to the operator's session policy. This example does not automate passwords or provision an integration identity. `ReadClient.get()` accepts API-relative paths such as `/documents/123` and the origin-relative `/api/v1/...` self links.

## Verification and remaining A19 work

- Broad local API/survey/shared-work/registry/deployment regression: **289 passed**, no failures or skips. Final contract/survey verification in shuffled order: **50 passed**, no failures or skips. Final required CI verifies the complete head.
- Authenticated HTTP tests cover typed schema/artifact agreement, current session/account/grant revocation, technical-admin boundaries, restricted/canonical document access, linked-case intersection, task reassignment/parent scoping, invalid and duplicate parameters, private errors and read-only business-state invariants.
- Pages are reconciled against the existing Python work-detail predicate across staff/officer/technical-admin audiences. A 270-record hidden population does not hide an older visible page. IDs above 2^53 retain their exact string value. Actual generated work statements run on the OS SQLite too.
- The standalone client reads the real application through an isolated local HTTP bridge, follows pages and self links, refuses an actual 302 trap, and receives 401 after session revocation. No production business records or external providers are used.
- The remaining combined-survey confirmation race is exercised in English and Filipino with a deliberate 300ms deferred-script delay. The check waits for matching draft removal and retains actual saved-count/skip assertions; survey runtime behavior is unchanged.

Later A19 increments cover approved write contracts, revision preconditions and operation-status contracts. A20 supplies scoped integration identities; A21 adds reliable events/adapters. Production workflow observations remain deferred, and no production throughput claim is made.

## Release and rollback

7.92 increments verified main 7.91 with aligned release/cache metadata. The deployment inventory includes the two new runtime modules; no schema migration or new dependency is required. Revert the API mount/module references through a newly versioned release if needed, coordinate with any adopted clients, and preserve permission-filtered shared-work paging during a forward repair. There are no API writes or data backfills to undo.
