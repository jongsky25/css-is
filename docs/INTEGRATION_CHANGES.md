# Resumable change feed — A21 / 7.100

`GET /api/v1/changes` lets an approved tool read small notices about permitted document, work-item and task revisions. This is a polling feed over the supported API. Signed webhook delivery, remote delivery receipts and provider adapters remain future A21 increments.

## Contract and scope

API contract **1.4.0** adds these query parameters:

| Parameter | Meaning |
|---|---|
| `resource` | Required: `documents` or `work-items` (including tasks) |
| `cursor` | Opaque 64-character checkpoint returned by an earlier call; omit to start now |
| `limit` | 1–100, default 25 |

Existing registered human sessions can read their permitted notices. Delegated credentials need `documents:read` or `work:read` matching the family. Current credential/account state and domain authority apply; no write or approval authority is added. Unknown/duplicate parameters and malformed cursors return private JSON 400. Missing/expired credentials return 401, insufficient scope returns 403, and unavailable checkpoints return **410 / `checkpoint_unavailable`**.

Responses contain `data`, `next_cursor`, `has_more` and `initialized`. A notice contains only:

- Stable random `id`, `schema_version: "1"`, and `type`: `document.changed`, `work_item.changed` or `task.changed`.
- Decimal string `resource_id`, optional string `work_item_id`, and committed entity `revision`.
- Offset-aware UTC `recorded_at` and a relative supported-API `resource_url`.

Global sequence positions, identity bindings, stream generation, historical prose, evidence and operation details are excluded. Fetch the linked current resource separately; its revision may already be newer. A notice is a reconciliation hint, not a historical snapshot or a command to repeat a business action.

## Start, resume and replay

1. Call without a cursor. The empty page has `initialized: true` and a checkpoint at the current stream position. This starts **now**; existing records are not backfilled as fictitious changes.
2. Save the checkpoint. For an initial dataset, enumerate the normal resource/task APIs **after obtaining it**, then consume changes from it. This ordering catches revisions committed during enumeration. Baseline pages remain fresh reads, not one immutable export snapshot.
3. Resume with the saved cursor. Notices are ordered by committed internal sequence and filtered by **current** permission before the page limit. `has_more` describes additional permitted notices, not hidden counts.
4. Process/deduplicate by notice ID and save `next_cursor` in the **same durable transaction** as local processing. Continue while `has_more` is true; otherwise wait before polling again.
5. After a timeout/lost response, retry the original saved cursor. Replayed notices retain their IDs. A replay may include newer changes or omit records whose access was revoked; authorization is never frozen into a saved page.

Saving a local notice does not acknowledge/submit an Office Connect task. There is no upstream feed acknowledgement mutation. External business actions need their own transactional receipts/idempotency rules before advancing a checkpoint.

## Permissions and reconciliation

Each page uses the metadata APIs' domain predicates in a read snapshot. Work/task notices require case readership and access to every linked canonical document. Document notices require current terminal-record access; obsolete alias IDs are suppressed. Technical administration does not imply record readership.

This is **not a complete synchronization protocol** for grants, revocations, hard deletions or alias removal. Newly readable older records can fall behind a checkpoint; inaccessible records are omitted without identifying tombstones. Periodically reconcile through the current APIs, recheck access before using retained data and remove data the integration may no longer retain. Silence does not prove the entire dataset or its permissions are unchanged.

The selected scope captures entity creation and revision changes, including task status transitions. It does not promise notices for every private discussion, file, calendar/grant change or maintenance edit without an entity revision. One task action can revise its parent too. Deduplicate by the full notice ID, not an entity ID.

## Checkpoint lifecycle and recovery

Random server-held checkpoints bind owner, exact credential (or human actor), family, deployment/API audience and stream generation. Other tools/users/families cannot reuse them. Empty polls keep their checkpoint unchanged when only hidden changes occur. Initialization returns a fresh reference; cursor text exposes no resource IDs or global counters.

A returned checkpoint expires seven days after its successful save/renewal. Polling an up-to-date checkpoint renews it. Older replay checkpoints can expire while a tool advances using newer ones. Expired rows are removed in bounded batches; notices are retained without automatic pruning. Missing, expired, mismatched and invalidated checkpoints share the private 410 response.

On 410, retain the old inbox for review, obtain a new starting checkpoint and rebuild/reconcile the current baseline. Do not fabricate cursors or reset silently after access errors. Credential rotation requires a new identity's checkpoint/baseline. A fresh session for the same human actor does not itself change the binding.

Routine newest-snapshot boot recovery preserves eligible checkpoints. Supported historical database restore resets stream generation and clears checkpoints, while retaining restored notices. It also revokes restored tool credentials/browser sessions. File restores outside that path require the same invalidation before serving requests.

## Independent example

`ReadClient.changes(resource, cursor=saved_cursor, limit=25)` in [examples/read_api.py](../examples/read_api.py) reads one validated batch without advancing a caller's durable state.

[examples/change_inbox.py](../examples/change_inbox.py) collects **one page per invocation** into a private local SQLite inbox:

```sh
python examples/change_inbox.py \
  --base-url https://office.example/api/v1 \
  --credential-file /private/path/tracker-credential.txt \
  --inbox /private/path/work-notices.sqlite \
  --resource work-items
```

The first run initializes progress. Later runs insert unique notices and commit the new checkpoint together. The inbox binds its site, credential ID and family, creates new files with owner-only permissions and never stores the credential secret. Protect existing inbox permissions yourself. Output contains only initialization/count/more status. This is receipt storage, not a record mirror or external-action executor. Failure retains saved progress; duplicate notices cannot duplicate local receipts. The integration owner remains responsible for retention of local identifiers after access changes.

## Storage, performance and rollout

An additive `integration_change` table has a monotonic internal sequence, random public IDs and immutable rows. SQLite triggers insert notices in the entity's original writer transaction. Rollback leaves no notice; failed notice storage refuses the business write. Repeated installation preserves history and performs no backfill.

SQL permission filtering precedes pagination. The feed closes its business snapshot before a short writer stores/renews a checkpoint and deletes at most 200 expired references. Credential requests retain minimized security audits, excluding cursor/query values. Human feed reads share the per-owner integration admission budget. Empty polls may rescan intervening hidden notices; measure representative populations before expanding polling traffic. This adds storage and short checkpoint writes; no production throughput claim is made.

The change sequence participates in the existing snapshot high-water guard. Release **7.100** follows freshly checked main **7.99**, with aligned release/cache metadata and the new runtime module packaged. There is no new dependency, provider request or live business-record test.

Prefer a forward repair that stops serving the feed while retaining notices, checkpoints, restore invalidation and high-water handling. Older 7.99 code does not understand the new counter or checkpoint restore rules. Do not bypass guards or erase notices to force rollback. Capturing changes while the feed is unavailable requires the current schema and restore safeguards to remain installed.

## Verification and remaining work

The shuffled API/work/credential/Chromium/backup/release/deployment regression set passed **400 tests** (seed 311), with no failures or skips. Final feed/client/inbox/schema/deployment checks passed **22 tests** in shuffled order, with no failures or skips. These sets overlap. Release metadata, dependency-lock inputs, vendor integrity, Python compilation, CLI startup and whitespace checks passed.

Local checks cover domain rollback, failed notice/checkpoint storage, replay, hidden populations, restricted/canonical/linked-record authority, administrator boundaries, scope/identity/audience, expiry, limits, concurrency, repeatable installation and actual snapshot restore. A separate HTTP client recovers a replaced/lost response with its saved checkpoint. The inbox verifies atomic receipt/progress commits and duplicate refusal. Full CI verifies the final head.

Signed push delivery, remote delivery receipts, external replay operations and one owner-selected provider adapter remain later A21 work. Production workflow observations remain deferred.
