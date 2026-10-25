# Telegram action contract (T3.1)

Implementation: [telegram_actions.py](../telegram_actions.py),
[calendar_actions.py](../calendar_actions.py),
[delivery plan](TELEGRAM_TWO_WAY_PLAN.md).

T3.1 introduced this contract with an empty adapter registry. T3.2 now installs
a calendar-create adapter through the [guided meeting flow](TELEGRAM_MEETINGS.md),
and T3.3 adds the separate [linked room-request adapter](TELEGRAM_ROOM_REQUESTS.md).
T3.4 adds an optional [combined flow](TELEGRAM_MEETING_ROOMS.md), using a calendar parent and separately recorded room child with room-only recovery.
It requires explicit current read/create consent and independent default-off
switches. Room submission requires its own request and read consent, plus calendar read consent for linking. No production activation or hosted
verification is recorded.

## Calls and bindings

`issue(conn, context, action, client_key, fields, now)` returns an operation ID,
an opaque 43-character token and a structured preview. Tokens are derived with domain-separated HMAC from a random 256-bit nonce and
operation ID; SQLite stores the nonce and token hash, never a plaintext code. The token fits within a
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
The installed adapter queues private descriptors transactionally; the separate
bounded transport renders and sends them after commit.

Receipts contain operation ID, action, state (`committed`, `partial`, `failed`;
pending/cancelled can be inspected through recovery), safe result code and nullable
calendar/room result IDs. No rendered business message or provider response is
stored. A definite domain failure can consume a token with a failed receipt;
an unexpected failure rolls back and leaves the unexpired preview pending.

## Trusted adapter responsibilities

Trusted adapters implement these methods; calendar creation and one linked room
request are installed behind separate default-off gates:

| Method | Required behavior |
| --- | --- |
| `prepare(conn, user, fields)` | Return normalized field dict, exact structured preview dict and expected-revision dict. Validate current domain authority and all fields. Show participants/audience, office date/start/end/duration and Asia/Manila timezone, with requested room slots separate from actual booking status. |
| `revalidate(conn, user, fields, expected)` | Recheck domain permissions, participants, source revisions, module state and conflicts inside the confirmation writer transaction. Raise on stale state; do not silently update the preview. |
| `apply(conn, user, fields, operation_id)` | Apply a caller-owned transaction mutation and return allowlisted receipt fields. Never commit, open another writer, perform network I/O or replace the invoking operation identity. An explicitly previewed coordinator may record a uniquely keyed child in the same transaction, as documented for T3.4. |
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
The extracted services perform no network I/O. T3.3 adds a caller-owned plain
internal room request/link path, including transaction-safe slot initialization
and approver notice insertion; existing UI default commits/courtesy behavior
remain unchanged.

The optional `queue_preview` and `queue_receipt` adapter hooks run in their
respective writer transactions and may enqueue descriptors only, with no commits
or network I/O. Both adapters use them for private delivery. `confirm_digest`
lets the authenticated update worker confirm using the stored token hash after
private-sender validation, without persisting the raw incoming code.

T3.2 implements deterministic fields, action consent and exact private preview
confirmation for one non-recurring calendar meeting; T3.3 reuses the same contract
for one self-owned pending room request linked to a currently permitted meeting. Group-origin requests bind
the original registration/topic and require membership proof at confirmation;
full participant previews and receipts remain private. Source-share consent is
not inferred. Before-delete triggers detach calendar/room receipt foreign keys,
cancels stale delivery and records a neutral deletion outcome, preserving UI hard
deletes and preventing recreation on recovery. External relay recovery or new
external calendar integration is not provided by this contract.

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
removing result IDs/revision/code details and raw routing context, retaining key/hash/context identity
tombstones. Detailed recovery then denies with a neutral expiry response, and
old keys still cannot execute again. Ordinary restart preserves unexpired
previews and receipts. There is no exactly-once guarantee across rollback to an
older database snapshot; all write switches remain off by default pending hosted recovery evidence.

T3.4 records an explicitly previewed room child under the parent confirmation transaction. A child domain refusal rolls back its savepoint and returns a partial parent plus failed child; unexpected exceptions roll back everything. Child attempts have separate operation IDs, keys, hashes and the same bound context. No extra token is minted for the initial child because its exact hours and failure policy were confirmed in the parent preview. A fresh retry uses the ordinary room action contract and existing meeting ID, with an indexed parent reference. Receipt rendering can show current child status while retaining the historical parent outcome. Room-grant revocation also scrubs combined calendar previews; calendar-only previews are unaffected.

T4.1 adds [transactional source-change events and metadata-only routing](TELEGRAM_CHANGE_EVENTS.md). It does not deliver change notifications or replay business actions; T4.2 owns that transport handoff.

T4.2 adds [current permission-checked calendar and room change notices](TELEGRAM_CHANGE_NOTICES.md), with a separate default-off read/delivery pilot. Business confirmation/recovery semantics are unchanged; a notice never repeats an action.
