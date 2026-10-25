# Telegram T0: implementation contract

Design baseline: `f9e868e` on main, inspected 2026-10-25. This is a proposed
implementation contract for the [delivery plan](TELEGRAM_TWO_WAY_PLAN.md), not
an implemented API, migration, configuration change, or production verification.
No applicable AGENTS.md was found in the checkout or its workspace ancestors.

## Source inventory and authority

| Surface | Existing source and behavior | Telegram contract |
| --- | --- | --- |
| Identity | `auth.py`, `storage.session_actor`; active `admin_user`, directory and scoped appointments | Resolve current numeric account ID on every read, commit and send. A Telegram connection is a new delegated credential, never a browser session. |
| Calendar read | `office_calendar.viewer_context`, `entry_visible`, `items_between`, `viewable_entry`; `calendar_routes` `/api/calendar` whitelist | Reuse current viewer context and scope; initial private layers are entries, holidays and rooms. Do not expose leave, birthdays or activity details through a blanket calendar dump. Maximum 31 days per query, 10 items/page with actor-bound cursor. |
| Calendar audience | `entry_visible`: listed participants and creator see own items; bureau audience visible to staff; people audience excludes others; unit audience uses current directory paths/team scope | Viewer/encoder/section_manager/admin role names alone do not establish visibility. Test each role with people/unit/bureau audiences and with/without scoped appointments. |
| Calendar create | `/calendar/new`, nested `_parse`; `storage.cal_validate`, `cal_create(commit=False)`, `people_choices` | Existing creation route is available to signed-in staff, without a separate create-activity capability. Extract its validation, including active participants, audience and owner rules; add explicit delegated `calendar.create` consent. Never call raw storage as an authorization service. |
| Calendar revisions | `calendar_entry.sequence`, `updated_at`, `calendar_entry_revision`; `cal_update` supports expected sequence/time | Preview records target sequence and update timestamp for edits/linking; stale state requires a fresh preview. New records bind normalized input hash. |
| Room availability | `rooms.day_view`, `slot_states`, `day_closed_reason`, `earliest_bookable`, `precheck`, `suggest`, `slot_range` | Use existing working-day, holiday, lead-time, horizon, closure and slot rules. Requested means pending; approved means booked. Never describe requested/standby as held. |
| Room request | `rooms_routes` `/rooms/request`; `rooms.request`, `rooms.link_entry`, `reservations_for_entry` | Staff may request for themselves. Bot requires `rooms.request` consent; no guest, on-behalf-of, meals, standby, series or encode path initially. Require viewable target plus creator/participant authority to attach a request; reject another existing link. |
| Room decision | `rooms.is_room_admin`: administrator or active internal Administrative Section appointment; `approve`, `decline` | Send status to eligible requester; approval stays in Office Connect. No approval grant or global administrator impersonation. |
| Existing outbound | `work_channels.py`, `apprise_transport.py`, `docs/APPRISE_TELEGRAM_DIGESTS.md`; calendar email outbox and room notices | Keep existing private digest preferences, switches, transport and queue separate. Linking the bot does not migrate or enable digests. |
| Task operations | `integration_operations.py`, `work_api_operation`; current session required, transactional mutation + receipt, access checked on recovery | Reuse the receipt pattern later, not session payloads or existing read-token grants. T6 must add separate task action grants. |

Private read projection: title, kind/status, local date/time, timezone, venue,
owner label and signed-in source link, only when the underlying item permits it.
Omit notes, meeting URLs, people lists, contact details, attachments and document
metadata. Own room status may add reference, requested slots and decision status;
notes/reasons stay on the signed-in page. Unlinked/inactive accounts get only
neutral help and linking instructions. Domain-disabled behavior must match UI;
no independent calendar module switch was found to invent as an existing gate.
Existing Documents/Collaborative-work gates still govern digests and later tasks.

## Hosting and transport

Use an HTTPS webhook at proposed `POST /integrations/telegram/webhook` in the
existing FastAPI application. Do not start a competing long poller. Docker runs
one uvicorn process on port 7860; the existing app scheduler can drain bounded
SQLite-backed work. No new queue, database, framework or hosted service is needed.
Use database claims, not process-local locks, so overlapping ticks cannot double
execute. Network calls happen outside the SQLite write transaction.

`DEPLOY.md`, `app.py` persistence setup and `backups.py` describe a local live
SQLite DB (`CSS_DB`) with possible `CSS_PERSIST_DIR` snapshots restored at boot.
Effective production mounts, snapshot lag, webhook reachability and Telegram
egress have not been verified. Before T1.2 activation, verify HTTPS/base URL,
durable storage and restart behavior, Bot API access, and single webhook ownership.
Before any business writes, prove recovery cannot silently replay actions lost
between a committed local write and its durable snapshot. Snapshot restore must
pause bot work pending reconciliation. Merge triggers deployment; this PR does
not merge or activate anything.

Register webhook externally only after the receiver is deployed and validated.
Validate `X-Telegram-Bot-Api-Secret-Token` with constant-time comparison before
parsing. Proposed secrets: `CSS_TELEGRAM_BOT_TOKEN`,
`CSS_TELEGRAM_WEBHOOK_SECRET`; never store these in SQLite, URLs in logs, or test
artifacts. Narrowly exempt only this route from browser session/Origin/CSRF
requirements; require provider secret instead. All account-link browser actions
retain normal session, Origin and CSRF protection.

Bound input to 64 KiB while streaming, JSON object only; validate numeric update,
user and chat IDs, supported update shape, text <=4096 characters, callback data
<=64 bytes. Drop unsupported authenticated update kinds durably as ignored.
Apply 120 requests/minute globally and 20/minute per sender with bounded storage;
429 means retry later, no acknowledgement of new work. Invalid secret returns
403; oversized input 413; malformed input 400; DB failure 503. Return 200 only
after update receipt is committed, including duplicates. Request logs omit body,
secret header, numeric destinations and callback/link tokens.

## Connection, consent and group audience

Account link: private `/start` creates an opaque random 256-bit challenge, stores
only its hash and numeric sender/private-chat IDs, expires after 10 minutes.
The signed-in page shows the account and requested capabilities; a protected POST
consumes the challenge once and requires a matching private-bot confirmation
before activation. This prevents a forwarded link silently binding another
person's Telegram identity. Enforce one active account per Telegram user and one
active Telegram identity per account. Replacement requires explicit disconnect.
Recheck active account and current authority under the writer lock. Read consent
and each action grant are separately revocable; issue no business grants merely
from `/start`. Status and disconnect remain available while delivery is paused.

Proposed grants: `calendar.read`, `rooms.read`, `calendar.create`, `rooms.request`;
later `tasks.read`, `tasks.acknowledge`, `tasks.submit` require their own increments.
Disconnect increments a connection generation, revokes all grants, expires
challenges/previews and cancels queued sends. Every worker compares generation
before commit/send/finalization. Deactivation has the same deny effect even if a
stored connection still says active. Already accepted messages cannot be recalled.

Group registration in T1.4 requires an active Office Connect administrator and
an explicitly consenting linked staff owner, verified Telegram administrator
status for the binder, exact numeric group/topic IDs and audited purpose.
Use a **bureau-shared projection**, independent of observed Telegram membership:
only explicitly designated bureau-audience calendar entries with an audited
`telegram_group_share` opt-in may expose title, date/time/timezone, venue and
status to that registration. This is an additional disclosure consent, not an
inference from bureau visibility. No participants, notes, meeting URLs, unit/people
entries, leave, birthdays or personal request status. Room availability in groups
contains only date, slots and free/requested/booked/closed, without requester,
title, reference or decision reasons. Source links always require Office Connect
sign-in. The owner accepts that new Telegram members can see shared content;
membership grants no Office Connect authority. Disable groups until this policy
and explicit share opt-in exist and pass T2.3 checks.

Commands still require a linked, currently permitted actor. Recheck registration,
owner activity, source share consent and generation before sending. Topic closure,
owner revocation, bot removal or uncertain registration state pauses routing.
Do not silently follow group migrations: pause old destination, cancel queued
old sends, reverify administrator/owner and audience consent for the new group,
then increment registration generation. Do not fetch arbitrary group history;
privacy mode stays on and commands/replies drive the flow.

## Proposed storage and migrations (T1.1 and later)

All names below are new designs. Use idempotent `storage.init_db` migrations and
SQLite transactions; enforce foreign keys and unique constraints, not prechecks
alone. Numeric Telegram IDs use signed 64-bit integers (groups can be negative).
Dates for transport/expiry are UTC; meeting input/output uses Asia/Manila.

| Table | Required fields / constraints | Introduce |
| --- | --- | --- |
| `telegram_connection` | id, account_id FK, telegram_user_id, private_chat_id, state, generation, created/updated/revoked timestamps; unique active account and sender | T1.1 |
| `telegram_update` | bot identity + update_id unique, sender/chat/topic, minimal normalized payload, payload hash, received time, state, attempts, claim token/lease, error code, generation | T1.1 |
| `telegram_operation` | operation UUID unique, actor FK, connection/generation, action, input hash, target IDs/revision, state, result IDs/code, timestamps; unique actor + operation key | T1.1 |
| `telegram_delivery` | id, dedupe key unique, operation/event link, destination/registration generations, projection descriptor, state, attempt/lease token, retry_at, provider message_id, sanitized error, timestamps | T1.1 |
| `telegram_link_challenge`, `telegram_grant` | hashed one-time challenge/expiry/consumed state; account/connection/action/generation, consent time/revoked time | T1.3 |
| `telegram_group`, share consent | chat/topic unique, owner FK, purpose, projection version, state/generation; entry+registration explicit share consent and audit | T1.4/T2.3 |
| `telegram_preview` | random token hash, actor/action/connection/group generations, normalized fields hash, expected revision, expires/consumed time, operation FK | T3.1 |
| calendar/room change event outbox | stable event key, source ID/revision, event type, committed timestamp; unique revision/type | T4.1 |

T1.1 creates inert storage only. Empty/legacy DB migrations, repeated init,
restart and restored fixtures must preserve business data and existing digest
settings. Add restore invalidation to every supported restore path, including
`backups.clear_restored_sessions` callers; schema initialization alone is not
proof of restore detection. Restore places connections/registrations in paused
state, expires grants/challenges/previews, cancels pending actions, marks sending
attempts uncertain and fences old workers. Operator reconciles receipts/provider
history and relinks before resuming; never replay all historical updates.

Retention: remove normalized input content after processing or 7 days, whichever
comes first; keep minimal update-ID/hash tombstones for the life of the bot
identity to prevent late replay (no payload). Purge expired challenges/previews
within 24 hours; erase pending content immediately on disconnect. Keep operation
receipts and delivery metadata 180 days, with no rendered business body; after
that retain only operation-key/hash tombstones until bot retirement. Existing
business audit retention stays unchanged. Remove unused numeric routing data
30 days after disconnect unless referenced by retained receipts. Backup copies
follow existing backup retention and must remain access-controlled; restore
reapplies revocation/pause before sending. Cleanup is bounded per scheduler tick.

## Confirmation, transaction and failure contract

Previews show exact normalized fields, participants, audience, office date,
start/end/duration/timezone, and requested room slots separately from booking
status. Confirmation expires after 5 minutes, is actor/action/input-bound and
one use; callbacks carry opaque tokens, never trusted fields. Acquire the writer
lock, re-resolve identity/grant/generations, recheck source authority, expected
revision and conflicts, then write business record + receipt atomically. Same
key + same hash returns original receipt after current-access checks; same key +
different hash returns conflict. Receipt recovery cannot disclose revoked data.

| Failure / race | Required durable outcome and recovery |
| --- | --- |
| Duplicate update, button or two workers | Unique keys and conditional claim/consume; one action, original receipt returned. |
| Crash before action transaction commits | Rollback all changes; leased update becomes eligible after expiry. |
| Timeout after business commit | Recover receipt using original operation ID; never create a second record. |
| Expired/foreign/stale preview | Deny with neutral reason; create a new preview, no partial mutation. |
| Meeting succeeds, room fails | Persist meeting receipt and room failure separately; report partial result with source link. Retry room child operation after a new preview, reusing meeting ID. |
| Account/grant/module/group revoked after enqueue | Suppress at next commit/send; fence stale finalizers. A network send already in flight cannot be unsent; record that limitation. |
| Provider 429 or definite rejection before acceptance | Record safe error, honor retry_after for 429; bounded exponential retries (max 5 attempts, 24 hours). Permanent 400/403 fails and pauses invalid destination. |
| Timeout, connection loss after request, crash while sending, ambiguous 5xx | Mark uncertain, no automatic resend. Operator may inspect provider evidence or explicitly enqueue a replacement with duplicate warning. |
| Process restart | Reclaim expired internal-processing leases; expired sending leases become uncertain. Never retry a business action without its operation identity. |
| Backup restore / stale snapshot | Pause all two-way execution and sends; reconcile possible lost receipts and Telegram pending updates before reactivation. No exactly-once guarantee across snapshot rollback. |

Delivery states: queued → claimed → sending → accepted/failed/uncertain;
retry_wait only for definite retryable rejection; cancelled for revoked/expired
work. Commit sending marker before HTTP. Accepted stores provider message ID and
means accepted by Telegram, not read. Claim tokens/generations fence finalizers.
Drain at most 20 updates and 20 deliveries per tick; use per-destination pacing,
finite HTTP timeout and no implicit HTTP-library retries or redirects.

## Switches, extraction and acceptance handoff

Proposed environment switches, all default `0` and fail closed on unknown values:
`CSS_TELEGRAM_INBOUND_ENABLED`, `CSS_TELEGRAM_DELIVERY_ENABLED`,
`CSS_TELEGRAM_LINK_ENABLED`, `CSS_TELEGRAM_GROUPS_ENABLED`,
`CSS_TELEGRAM_CALENDAR_READ_ENABLED`, `CSS_TELEGRAM_ROOMS_READ_ENABLED`,
`CSS_TELEGRAM_CALENDAR_CREATE_ENABLED`, `CSS_TELEGRAM_ROOMS_REQUEST_ENABLED`,
`CSS_TELEGRAM_CHANGE_NOTICES_ENABLED`, `CSS_TELEGRAM_REMINDERS_ENABLED`.
Require underlying read/link/group switches as applicable; action switches never
grant consent. T5/T6 add separately named switches in their own designs.
Existing `CSS_APPRISE_TELEGRAM_ENABLED` and digest preferences remain independent.
Pause inbound stops new receipts with 503; pause delivery leaves eligible queued
work pending only until its 24-hour expiry. Pausing writes blocks confirmation;
resume rechecks everything and expires stale previews. Disconnect never depends
on an enabled sending switch. No new switches exist at T0.

Required extraction before T3.2: move `_parse` and create orchestration out of
`calendar_routes.make_router` into a shared actor-aware service, preserve UI
validation, `cal_create(commit=False)` audit/email behavior and meeting relay
semantics, add atomic receipt in the caller transaction. Do not invent a new
calendar source value without updating storage's allowed values.

Before T3.3, make `rooms.request` and linking usable in a caller-owned transaction
without internal commits; preserve conflict checks, slot locks, approval and
notification hooks. `rooms.link_entry` checks reservation ownership but does not
itself check calendar visibility: shared orchestration must check both records.
T3.1 can prepare calendar extraction; room extraction belongs to T3.3, keeping
one bounded increment per PR. T4.1 must capture committed changes from UI and
other supported writers rather than copying existing email queues. Its event
insert must share the business transaction; audit a full writer inventory there.

T0 acceptance is source-backed review of the matrix, schema boundaries, authority,
transport, failure table, retention, switch names and extraction list above.
No runtime tests can prove this design implemented. T1.1 next: create only the
four inert tables, independent switches, restore fencing and fixtures; run
migration/restart/restore checks plus `tests/test_work_channels.py` and the digest
subset of `tests/test_work.py`. T1.2 subsequently adds the actual receiver and
bounded scheduler/transport. Live activation remains gated on hosting evidence.
