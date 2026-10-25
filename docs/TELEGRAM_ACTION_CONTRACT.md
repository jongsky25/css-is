# Telegram action contract (T3.1)

Implementation: [telegram_actions.py](../telegram_actions.py),
[calendar_actions.py](../calendar_actions.py),
[delivery plan](TELEGRAM_TWO_WAY_PLAN.md).

This is a dormant service contract. The production adapter registry is empty.
There is no action command, callback, action preview screen or write-grant issuance.
Enabling environment switches cannot create a calendar entry or room request
through Telegram in T3.1. Tests install a synthetic adapter explicitly.

## Calls and bindings

`issue(conn, context, action, client_key, fields, now)` returns an operation ID,
an opaque 43-character token and a structured preview. Tokens contain 256 bits
of randomness; only their SHA-256 hashes are stored. The token fits within a
64-byte callback when prefixed with a short action marker in a later increment.
It expires after five minutes. There is no token regeneration for an existing key.

Context is exactly connection ID/generation, numeric sender ID, exact chat/topic,
and registration ID/generation (both absent for private chat). Private chat must
match the linked sender. Current account, bot provenance, link configuration,
inbound/action/read switches and separate read **and write** grants are checked.
Group confirmation additionally verifies fresh bot/owner administrator and
requester membership outside the writer transaction, then rechecks local routing
and generations under the writer lock. Provider membership can change after
verification; no local transaction can lock Telegram membership.

Input fields, exact preview and expected revisions are canonically serialized,
bounded to 16 KiB each and hashed together with the action. The operation also
binds a hash of the destination context. An existing actor/key with different
content, connection or context is rejected. Identical pending issuance returns
its operation ID without another token; identical terminal issuance returns the
original receipt after current-access checks. Expired/cancelled keys require a
new preview with a new key; a key is never reused to execute another action.

`confirm(conn, context, token, now)` checks bindings and expiry under
`BEGIN IMMEDIATE`, revalidates domain authority and expected state, and applies
the action, records its receipt and consumes the preview in the same transaction.
It immediately clears normalized fields, preview text and expected revisions.
An exception rolls everything back. A consumed token returns the original receipt
while retained and currently authorized; it never repeats the action. Expiry does
not invalidate a previously committed outcome.

`recover(conn, context, action, operation_id)` checks current delegation,
destination context and domain access before returning the receipt. This is the
recovery path when a response is lost after commit, including after the token is
purged. A receipt does not preserve authorization after access is revoked.
Neither confirmation nor recovery sends a Telegram message in this increment.

Receipts contain operation ID, action, state (`committed`, `partial`, `failed`;
pending/cancelled can be inspected through recovery), safe result code and nullable
calendar/room result IDs. No rendered business message or provider response is
stored. A definite domain failure can consume a token with a failed receipt;
an unexpected failure rolls back and leaves the unexpired preview pending.

## Trusted adapter responsibilities

Future adapters must implement these methods; none is installed here:

| Method | Required behavior |
| --- | --- |
| `prepare(conn, user, fields)` | Return normalized field dict, exact structured preview dict and expected-revision dict. Validate current domain authority and all fields. Show participants/audience, office date/start/end/duration and Asia/Manila timezone, with requested room slots separate from actual booking status. |
| `revalidate(conn, user, fields, expected)` | Recheck domain permissions, participants, source revisions, module state and conflicts inside the confirmation writer transaction. Raise on stale state; do not silently update the preview. |
| `apply(conn, user, fields, operation_id)` | Apply a caller-owned transaction mutation and return allowlisted receipt fields. Never commit, open another writer, perform network I/O or generate a new operation identity. |
| `check_receipt(conn, user, operation)` | Recheck current domain access to all result/target records before receipt disclosure, including replay/recovery. Must also handle pending/cancelled receipts with no result IDs. |

These are trusted application services, not arbitrary plugin callbacks or user
code. The engine checks that an adapter has not ended the transaction, but cannot
undo a commit from a defective adapter. Every installed adapter needs transaction
rollback and concurrency tests before it becomes reachable.

The shared calendar service extracts the existing UI parser and creates through
`storage.cal_create(commit=False)` with current actor and participant checks.
Creation, revisions, audit and existing email outbox rows share the caller's
transaction. It retains source `app`; it accepts no arbitrary storage source,
import key or overlay field. The UI uses a transaction-owning wrapper and retains
its existing recurrence/detach, room-request and post-commit Meet orchestration.
The extracted service performs no network I/O. T3.3 owns transaction extraction
for room requests; this increment does not change room writes.

Before T3.2, implement the real non-recurring meeting adapter, deterministic
input and action consent, safe preview delivery and explicit confirmation wiring.
Full participant/audience previews must not be sent into a group merely because
the requester may see them. Originating in a group does not grant source-share
consent. Preserve current signed-in hard-delete behavior when deciding how real
receipt result foreign keys and receipt recovery interact with deleted records.
External relay recovery or new external calendar integration is not provided by
this contract.

## Revocation, restore and retention

Connection/account changes, required read/write grant revocation and group
state/generation changes cancel pending previews, clear their content and cancel
pending operations atomically. Restore does the same, and preserves committed
receipts while pausing/revoking the existing Telegram connection/grant state.
Reactivation or relinking never revives an old preview.

Cleanup cancels at most 20 expired previews per tick, immediately scrubbing their
content; it purges at most 20 non-pending token rows after expiry plus 24 hours.
Pending token rows are never purged before their operations are cancelled.
After 180 days it compacts at most 20 terminal operation receipts per tick,
removing result IDs/revision/code details and retaining key/hash/context identity
tombstones. Detailed recovery then denies with a neutral expiry response, and
old keys still cannot execute again. Ordinary restart preserves unexpired
previews and receipts. There is no exactly-once guarantee across rollback to an
older database snapshot; production bot writes remain unavailable pending later
implementation and hosted recovery evidence.
