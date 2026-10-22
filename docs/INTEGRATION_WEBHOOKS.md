# Signed HTTPS adapter — A21 / 7.101

This independent Python 3.11+ adapter turns the [resumable change feed](INTEGRATION_CHANGES.md) into signed HTTPS deliveries. It uses the published API and an existing [delegated read credential](INTEGRATION_ACCESS.md). Run it on the integration owner's approved runner or scheduler. This release does not install an outbound worker on the Office Connect host or automatically connect a provider account.

The generic HTTPS interface can feed a custom receiver or an automation platform such as n8n **when that receiver implements signature verification and durable deduplication**. The provider and live destination have not yet been selected/validated. Local tests use synthetic records and local HTTP servers. A21's live adapter/operational exit gate remains open.

## Ownership and setup

Name the integration owner and receiver owner. Agree which metadata family the receiver may retain and how it deletes identifiers after access loss. The source credential belongs to a real consenting user and never grants more than that user's current domain access. Keep human approvals separate.

1. Use a supported, maintained Python 3.11+ runner with outbound access approved for the source and receiver. No additional Python package is needed. The adapter preserves the runner's normal proxy, CA trust and network restrictions.
2. Create a private directory and owner-only files (`0600` on Unix). Save the source credential in a file. Save receiver settings in another private JSON file:

   ```json
   {"url":"https://receiver.example/office-connect","key_id":"office-2026-01","secret":"REPLACE_WITH_64_LOWERCASE_HEX_CHARACTERS"}
   ```

   Generate a random 32-byte secret with a trusted secret manager or Python's `secrets.token_hex(32)` and provision it privately to both runner and receiver. Never use the literal placeholder. Do not place secrets in command arguments, logs, source control or screenshots. Receiver URLs cannot contain user information, query parameters or fragments; this adapter uses its signing headers for authentication. A platform needing another authentication method needs its own reviewed adapter.
3. Install receiver verification/deduplication before scheduling deliveries. Protect the receiver's durable database and backups too. The supplied helper does not launch a public HTTP server or configure a provider for you.
4. Collect one page (the first run starts **now** and queues no historical backfill):

   ```sh
   python examples/webhook_adapter.py collect \
     --base-url https://office.example/api/v1 \
     --credential-file /private/tracker-credential.txt \
     --receiver-file /private/receiver.json \
     --state /private/work-delivery.sqlite --resource work-items
   ```

5. Run the same command with `deliver` instead of `collect`. Schedule both commands on the runner. Each invocation polls one page or attempts at most 25 due jobs (`--limit 1..100`). Continue collection when `has_more` is true; wait between empty polls. Do not busy-loop retries or exceed the source's shared per-owner admission budget (120 reads/minute by default). Each attempt also reads the current resource, so include those requests in the polling budget.

Use `documents` for document notices or `work-items` for work/task notices. Each needs its matching read scope. For an initial full dataset, follow the feed's checkpoint-before-enumeration ordering and periodically reconcile current access/deletions. The adapter is an event forwarder, not a complete record mirror.

The `--allow-loopback-http` option permits an HTTP receiver only at `127.0.0.1`, `localhost` or `::1` for local synthetic tests. Remote destinations require HTTPS. Redirects are terminal and never receive a forwarded signature. Only the integration owner controls this local configuration; no application user can configure arbitrary outbound calls on the Office Connect host.

## Signature and receiver contract

The exact UTF-8 body is canonical JSON (sorted keys, no insignificant whitespace, non-ASCII preserved, no NaN). It contains only:

```json
{"delivery_id":"64-character lowercase hexadecimal ID","event":{"id":"stable source notice ID","schema_version":"1","type":"work_item.changed","resource_id":"123","work_item_id":"123","revision":2,"recorded_at":"2026-10-22T00:00:00+00:00","resource_url":"/api/v1/work-items/123"},"schema_version":"1"}
```

Private titles, subjects, output/evidence, source credentials and signing secrets are excluded. Notice fields/IDs/timestamps and exact relative resource paths are validated before enqueueing. A notice describes a committed revision; a current read can already be newer. Retries and concurrent runners can arrive out of order; reconcile IDs/revisions with current data instead of treating arrival order as authoritative history. A notice is not a command to acknowledge, submit or approve anything.

Headers:

| Header | Value |
|---|---|
| `X-OfficeConnect-Key-Id` | Configured key identifier |
| `X-OfficeConnect-Timestamp` | Integer Unix seconds, refreshed on every attempt |
| `X-OfficeConnect-Signature` | `v1=` plus lowercase HMAC-SHA256 hex |

The signed bytes are `b"v1." + key_id + b"." + timestamp + b"." + exact_body`, with key ID and timestamp encoded as ASCII and the secret decoded from hex. Do not parse/reformat JSON before authentication. Require one of each signing header, compare signatures in constant time and reject timestamps more than five minutes in either direction. Synchronize runner/receiver clocks. Do not relax freshness to repair a clock problem.

[examples/webhook_receiver.py](../examples/webhook_receiver.py) supplies `verify()` and `accept()`. The HTTP layer must limit the request body to 16 KiB, reject duplicate signing headers, suppress secrets/bodies in logs, and return 2xx **after** durable acceptance. Example receiver transaction:

```python
from examples.webhook_receiver import accept

def apply(conn, event):
    conn.execute("INSERT INTO local_change(event_id) VALUES(?)", (event["id"],))

is_new = accept(private_sqlite_connection, exact_body, request_headers,
                key_id=receiver_key_id, secret=receiver_secret, apply=apply)
# Return 204 after this succeeds, including when is_new is False.
```

Create the receiver's own `local_change` table first. The helper commits the callback's **local SQLite effect and receipt together**. The callback must use that connection without committing or starting another transaction. On callback failure, both roll back and the HTTP layer should return an error. Concurrent duplicates serialize and do not rerun the effect. A repeated delivery ID with different body content is refused.

Keep receipts for as long as any sender state can be replayed. Fresh signatures alone do not prevent replay inside the freshness window. Remote calls made by a receiver need that downstream service's own idempotency/operation-result contract; this local transaction cannot guarantee exactly-once external effects. A bare n8n webhook trigger is not sufficient verification/deduplication by itself.

## Durability and status

The sender commits queued notices and its feed checkpoint in one SQLite transaction. Duplicate notice IDs keep one immutable body; changed content under an existing ID is refused. Collection uses checkpoint comparison to prevent concurrent pollers from rewinding progress. At 1,000 pending/in-flight deliveries, collection pauses; accepted/terminal history is retained. There is no automatic pruning, so monitor disk usage and protect backups on both runners.

Each claim records an attempt and holds a 120-second lease. Source and receiver requests run outside writer transactions, with bounded socket timeouts (source at most 30 seconds, receiver 15 seconds). A stale claim cannot finalize a replacement attempt. An expired claim becomes `unknown_after_lease` and can be retried with the same ID/body. A process pause or response loss can still cause concurrent/repeated remote deliveries; the receiver's durable receipt is required.

Delivery IDs are deterministic for the source API URL, destination URL and source notice ID. They survive restart, retry, explicit replay and credential/signing-key rotation for the same source/destination. Receiver receipts compare the stable body, while signing timestamps can change. Changing a destination URL creates a different destination identity; reconcile before moving endpoints.

Commands use the same configuration arguments as `collect`:

| Command | Result |
|---|---|
| `status` | Counts and up to 100 outstanding deliveries (IDs, state, attempt count, minimized outcome, HTTP code, next due time) |
| `history --delivery-id ID` | One saved delivery's attempt outcomes/timestamps and explicit replay timestamps |
| `replay --delivery-id ID` | Requeue one failed/blocked delivery, preserving body, ID and all previous history |

States are `pending`, `in_flight`, `accepted`, `failed` and `blocked`. `accepted` means an HTTP 2xx was received; it does **not** prove downstream business completion. Reconcile the receiver's receipt/business status separately. Successful deliveries cannot be replayed by this command; duplicate source polling does not requeue them. Pending/in-flight rows cannot be reset by replay.

Network/ambiguous transport failures, HTTP 408/425/429 and 5xx are retried with exponential delay from five seconds, capped at one hour. Numeric/date `Retry-After` can extend the delay up to that cap. Other HTTP errors, including redirects, are terminal. A cycle permits at most eight attempts and three days; failed cycles require explicit review/replay. Replay starts a new bounded cycle and records the request. Sender history excludes receiver response bodies, arbitrary response headers and raw exceptions.

## Access and failure recovery

Before **every** outbound send, the adapter fetches the linked current resource using the current credential. It blocks missing/denied resources, obsolete canonical aliases, mismatched task parents/IDs and revisions older than the queued notice. Authentication/scope failures stop the invocation. A revoked or expired credential is never replaced by a cached payload. An already-started outbound request can finish after a permission change; previously accepted data needs the agreed retention/reconciliation policy.

- **Temporary source or receiver failure:** keep the state file; let due jobs retry. Inspect `status`/`history`. Do not delete progress to retry.
- **Receiver 4xx/redirect:** fix the receiver configuration/authorization at its owner-controlled endpoint, then explicitly replay the selected failed delivery. Do not blindly replay business effects; check the receiver receipt first.
- **Source 401/403 or resource access loss:** restore legitimate access through normal consent/permission workflows, then review blocked jobs. Explicit replay rechecks access again. Do not broaden permissions solely to empty a queue.
- **Source 410/checkpoint loss or historical restore:** retain the old state for review, stop scheduling it, obtain a fresh checkpoint in a new state file and reconcile a current baseline. Do not silently discard the error or reuse another credential's checkpoint. Supported historical restores also revoke old credentials.
- **Credential/signing key rotation or target change:** the state file is bound to the exact source, credential ID, family, receiver URL, key ID and key fingerprint. The adapter refuses mismatches. Pause the old runner; review outstanding/ambiguous jobs and receiver receipts, provision new private settings, create a separate state file, capture a fresh checkpoint and reconcile. Coordinate receiver key retirement; do not run competing old/new configurations accidentally. Same-source/destination notice IDs retain their delivery IDs if reimported through a reviewed recovery procedure.
- **Disk/storage failure:** stop scheduling, preserve both databases and repair storage before resuming. A lost sender result may already have reached the receiver. Restore consistent backups/receipts; do not assume resending without receiver receipts is harmless.

Keep signing keys separate from source credentials and database backups; neither raw secret is stored in sender state. New state files use owner-only permissions; shared/nonregular/symlink files are refused on supported Unix runners. The database and private directory remain operator-owned security boundaries. Retained IDs may still identify records after access loss; define retention instead of treating this journal as a permanent authorized record mirror.

## Rollout and rollback

Release **7.101** follows freshly checked main **7.100**. The API contract remains **1.4.0** and the application database schema is unchanged. The adapter and receiver helper use the standard library. No provider credentials are provisioned or live webhooks sent by this release.

Validate the selected receiver in its sandbox using the local signature/receipt contract before connecting real notices. Check success, response loss, duplicates, bad signatures, access revocation, expiry, recovery and receiver retention with its owner. Production business workflow observations remain deferred.

To stop this increment, pause the external scheduler and retain the private sender/receiver databases and keys for reconciliation. App-host rollback alone does not stop an independently scheduled adapter. Prefer a versioned forward repair; preserve the existing change feed's restore/high-water safeguards. Do not delete receipts or force-replay deliveries to test rollback.

## Verification

A shuffled local regression run passed **231 tests** (seed 313), covering the adapter, supported read/change/write contracts, delegated access and release gates. Final adapter checks passed **36 tests** (seed 314); these sets overlap. Both JUnit reports have no failures or skips. Release metadata, dependency-lock inputs, vendored PDF.js integrity, Python compilation, CLI startup/error hygiene and whitespace checks passed. Full CI remains the release gate for the final PR head.

Tests include real local HTTP source-to-receiver delivery, source credential revocation and document restriction before retries, receiver commit followed by a lost/replaced response, durable restart, constant-time signature validation/freshness, duplicate/tampered deliveries, receiver transaction rollback, concurrent receipt/claim/poll races, expired leases/stale finalization, terminal redirects/4xx, Retry-After, retry budgets, private file/binding guards, key rotation and queue backpressure. No production business records or live receiver account are used.
