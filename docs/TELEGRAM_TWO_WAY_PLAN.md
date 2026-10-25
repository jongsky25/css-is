# Office Connect ↔ Telegram delivery plan

Status: T0 and T1.1 merged; T1.2 in review; two-way capabilities remain inactive.
Last updated: 2026-10-25.
Repository: jongsky25/css-is.
Planning baseline inspected: abf3141 (merge of PR #458).
Owner: Office Connect maintainers. Delivery agent: Sol or another assigned coding agent.

## Start here in any chat

Read this entire file, applicable repository instructions, and the current source before working. This file is the durable scope, progress ledger, and handoff for the Telegram integration.

Suggested prompt:

> Continue the Office Connect Telegram plan in docs/TELEGRAM_TWO_WAY_PLAN.md. Reconcile its progress with merged code, select the first ready incomplete increment, implement only that increment, run its acceptance checks, and update this Markdown in the same PR. Report the PR, checks, remaining limitations, and next increment. Do not treat merged code as proof of live deployment.

**Mandatory maintenance rule:** update this file when an increment starts, its scope changes, it becomes blocked, an implementation PR opens, it merges, or its live pilot is verified. Every implementation PR must include the corresponding plan update. At the start of a later chat, reconcile stale statuses with GitHub before choosing work.

Use statuses: planned → in progress → in review → merged → pilot verified. Use blocked with a concrete reason and unblock action. Keep implementation status separate from deployment/activation status. Never mark work complete solely because code exists or mocked tests pass.

For every started increment, record: owner, date, branch/PR, changed behavior, checks and results, known gaps, deployment/feature-switch state, and next action. Record merge SHA and live evidence when available. If merge metadata was unavailable in the PR itself, reconcile it in the next documentation update.

## Goal and first release

Telegram is a conversational interface to Office Connect. Office Connect owns records, permissions, business rules, and audit history.

First complete workflow:

Team calls bot → exact meeting preview → confirmation → Office Connect calendar entry → linked conference-room request → actual approval status and subsequent changes returned to the right Telegram conversation.

The first release includes private account linking, registered team groups, permitted calendar lookup, room-slot lookup, meeting creation, room requests, status updates, and reminders. Use the existing Office Connect calendar and conference-room model. Do not assume a catalog of multiple rooms or personal Google/Outlook free/busy exists.

Start with commands, buttons, and guided fields. Natural-language extraction follows a working deterministic flow. A language model can propose fields; business services decide whether an action is allowed.

## Verified repository baseline

- Telegram currently provides optional private unread-discussion reminders through Apprise. Its documented pilot excludes groups, business content, and inbound commands.
- Calendar and room services already exist, including approval rules and linked calendar/room records.
- The versioned API supports permission-checked work/document reads and task acknowledgement/submission with durable receipts. Existing task writes require registered user sessions; read credentials do not grant bot writes.
- The change feed covers documents and shared work/tasks. It is not a universal calendar/room event feed or a complete permission synchronization protocol.
- MCP provides permission-checked reads and has its own phased expansion plan. Telegram must not silently widen MCP grants or bypass its boundaries.
- This baseline is source inspection, not verification of production configuration or delivery.

References:
[Telegram pilot](APPRISE_TELEGRAM_DIGESTS.md),
[API access](INTEGRATION_ACCESS.md),
[change feed](INTEGRATION_CHANGES.md),
[webhook adapter](INTEGRATION_WEBHOOKS.md),
[MCP plan](MCP_PHASED_EXPANSION_PLAN.md),
[calendar source](../office_calendar.py),
[calendar routes](../calendar_routes.py),
[room routes](../rooms_routes.py),
[task operations](../integration_operations.py).

## Product and implementation decisions

1. Link a Telegram numeric user ID to an authenticated Office Connect account using an expiring single-use flow. Never identify staff by display name or username alone. Never collect Office Connect passwords or browser cookies in Telegram.
2. Register each group explicitly, with an Office Connect owner, permitted purpose, and defined shared audience. Telegram group membership never grants Office Connect access. Staff must start a private bot conversation before private delivery can work.
3. Sensitive/personal results go to the linked person's private chat or signed-in page. Group messages contain only explicitly approved shared fields. A requester's access alone does not authorize disclosure to the whole group. Resolve the audience model before enabling group reads.
4. Reuse domain services and current actor authority. Add action-specific delegated authorization; do not impersonate a global administrator or reuse browser sessions as bot credentials.
5. Each write has a structured preview, actor-bound expiring confirmation, expected record revision where applicable, durable operation ID, and receipt. Recheck account, grant, permissions, conflicts, and module state when committing. Duplicate updates and button clicks return the original outcome.
6. Store Telegram update IDs and action receipts durably. Verify inbound webhook authenticity, limit request sizes/rates, and acknowledge only after durable receipt. Specify restart and retry handling before enabling actions.
7. Record outbound work durably with the business change where possible. Recheck destination eligibility before sending. Distinguish queued, accepted by Telegram, failed, and uncertain delivery. Telegram acceptance is not proof of reading. Do not promise exactly-once message delivery or blindly resend uncertain attempts.
8. Calendar creation and room approval are distinct. Requested slots do not constitute a confirmed booking. Report partial outcomes and reuse the original operation when recovering.
9. Use Asia/Manila as the office default and show date, time, duration, and timezone before confirming. Resolve ambiguous dates and participant names. Never infer consent from general group conversation.
10. Start with explicit bot commands/replies and only context Telegram actually provides. Account for privacy mode, bot removal, group migration, changed membership, and revoked access. No assumption of arbitrary past-chat retrieval.
11. Enable capabilities independently and default new actions off. Preserve existing private digest behavior. Document disconnect, pause, restore, and recovery behavior.
12. Keep dependencies consistent with the existing Python application. A new platform, database, queue, or AI framework requires a demonstrated need; it is not a prerequisite for this plan.

## Phases and bounded increments

Implement one increment per PR. If an increment needs multiple independent migrations or workflow changes, split it into numbered children and update this file first. Dependencies are gates, not permission to bundle all subsequent work.

| ID | Deliverable and boundary | Depends on | Required acceptance evidence |
| --- | --- | --- | --- |
| T0 | Inventory exact domain services, permission predicates, hosting constraints, schemas, and delivery architecture. Specify webhook vs polling, action grants, group audience, receipts, retention, and switch names. Documentation/design only. | None | Concrete field/role matrix and failure-state contract; identify any service extraction needed. |
| T1.1 | Add durable Telegram connection, update, operation, and delivery storage with migrations and independent switches. No business actions. | T0 | Upgrade/restart/restore fixtures; existing digest regression checks; switches default off. |
| T1.2 | Receive authenticated updates; deduplicate; handle private /start and /help; provide bounded delivery handling. | T1.1 | Invalid webhook rejected; duplicate update processed once; restart recovery; malformed/oversized input rejected. |
| T1.3 | Account link, connection status, disconnect, and revocation. | T1.2 | Expiry/replay/cross-account tests; deactivated users denied; disconnect blocks next read/write/send; credentials absent from logs. |
| T1.4 | Register groups and topics, establish permitted shared fields and routing, handle removal/migration. | T1.3 | Unregistered groups denied; unauthorized staff cannot bind a group; restricted data never sent to a group; changed membership handled by defined audience policy. |
| T2.1 | Private calendar lookup with bounded dates, paging, and source links. | T1.3 | Low/high privilege parity with calendar screens; empty, disabled, revoked, and timezone cases. |
| T2.2 | Room-slot availability and own request status. Read only. | T2.1 | Free/requested/booked/closed match source rules; holidays, booking horizon, and conflicts represented accurately. |
| T2.3 | Group-safe schedule/room lookup using registered audience rules. | T1.4, T2.2 | Requester-only information stays private; approved group projection and source links tested. |
| T3.1 | Reusable action preview/confirmation/receipt contract and calendar create service extraction if needed. Keep bot creation disabled. | T2.3 | Cross-user/expired/replayed confirmations; stale state; timeout after commit; two clients racing; UI behavior preserved. |
| T3.2 | Create one non-recurring calendar meeting through guided input, in private or registered group contexts. | T3.1 | Correct participants/audience/time; same permission rules as UI; one record on repeated clicks; receipt and source link. |
| T3.3 | Submit one conference-room request and link it to an existing permitted meeting. Preserve normal approval. | T3.2 | Conflict recheck; pending vs approved; unauthorized linking denied; duplicate submission recovery; no automatic approval. |
| T3.4 | Combine meeting creation and room request into the guided meeting flow. | T3.3 | Calendar-success/room-failure shown clearly; retry does not recreate meeting; source links and next responsible party shown. |
| T4.1 | Add durable calendar/room change events and delivery routing for committed changes from any supported interface. | T3.4 | UI-originated changes captured; rolled-back writes emit nothing; routing and revocation checked; replay does not repeat business actions. |
| T4.2 | Send meeting changes and room decision results to eligible private/group destinations. | T4.1 | Approval/decline/time-change cases; bot blocked/removed; provider failure and uncertain responses; no disclosure after disconnect. |
| T4.3 | Add configurable reminders and quiet hours; prevent redundant email/Telegram noise through channel preferences. | T4.2 | Timezone boundaries, rescheduled meetings, scheduler restart, cancelled items, and repeated runs handled. |
| T4.4 | Pilot the complete first release with linked test staff and one approved group; record runbook and rollback. | T4.3 | Real group request → calendar → room approval → Telegram update; UI changes return correctly; revoked account denied; deployed SHA recorded. |
| T5.1 | Parse explicitly supplied natural-language meeting details into the existing preview. | T4.4 | Ambiguous dates/names prompt clarification; quoted content cannot bypass permissions; no write without confirmation; guided fallback works. |
| T5.2 | Permit meeting edits using the existing revision/confirmation contract; recurring events require a separately scoped child increment. | T4.4 | Concurrent edits rejected; room/time implications explicit; notifications reflect final state; existing UI rules preserved. |
| T6.1 | Private shared-work/task lookup and assignment/status notifications. | T4.4 | Reuse read/feed permission rules; hidden linked documents respected; deduplication and disconnect verified. |
| T6.2 | Task acknowledgement using a new delegated action grant and existing receipt semantics. | T6.1 | Current assignee authority; duplicate and stale-state recovery; read-only grants cannot write. |
| T6.3 | Task submission for review; scope comments/attachments as separate children if needed. | T6.2 | Existing readiness/review rules; private submission content protected; durable receipt and reviewer notification. |
| T7 | Expand additional modules through separately specified read → draft → submit increments. No blanket write enablement. | T4.4 and relevant services | Each child has exact fields, authority, acceptance tests, and independent switch before implementation. |

## Later-module backlog

These are candidates, not ready-to-build increments. Promote one at a time into the table with concrete acceptance criteria.

| Module | Telegram into Office Connect | Office Connect back to Telegram | Default context |
| --- | --- | --- | --- |
| Documents | Permitted lookup, routing/review status; later reviewed drafts | Routing/review notices and signed-in links | Private; group metadata only if explicitly allowed |
| Supplies | Catalog, own draft/request submission, receipt acknowledgement | Approval, collection, issue status | Private |
| Travel | Own checklist/status; later draft and review submission | Missing items, deadlines, reviewer feedback | Private |
| Meals/work arrangements | Own eligible request/update | Submission and decision status | Private |
| Activities/reports | Permitted schedules and aggregate summaries; later activity drafts | Schedule/report notices | Audience checked |
| Approvals | Initially open signed-in approval screen; later separately scoped decisions | Notify assigned approver and requester | Private, role checked |

Cancellation, deletion, withdrawal, official signing/dispatch, financial posting, stock adjustments, sensitive wellness details, and role/credential administration remain in existing Office Connect screens for this plan. Telegram may link to those screens. This boundary does not remove existing UI capabilities.

Google/Outlook two-way calendar synchronization, external free/busy, automatic video-meeting creation, multiple-room inventory, automatic monitoring of all group conversation, voice/file ingestion, and bulk operations require separate scopes. ICS feeds alone do not implement two-way synchronization.

## Definition of done for each increment

- User-visible behavior and exact scope match the increment.
- Current authorization and domain rules are reused, including disabled-module behavior.
- Meaningful tests cover success, denial, stale state, and applicable duplicate/restart/failure cases.
- Run repository-required checks and focused regressions; record actual commands/results.
- No real staff data, bot tokens, chat IDs, or private content appear in test artifacts.
- Migration and recovery effects are documented; feature switches and operator steps are explicit.
- This plan is updated in the same PR, with evidence and next action.
- Mark merged only after merge is confirmed; mark pilot verified only after real hosted evidence. A code-complete increment may remain disabled pending its pilot.

## Progress ledger

T0 merged in PR #465 at `4cd01a0bfd17ccf57dba12b05a24c72bfd098f29`. T1.1 merged in PR #466 at `bef000127846aebb9fc1176c190664797d262eb4`. T1.2 is in review; T1.3–T7 remain planned. All two-way capabilities remain inactive.

| Increment | Status | Owner / date | PR / commit | Evidence | Activation / next action |
| --- | --- | --- | --- | --- | --- |
| Planning document | Published | Codex / 2026-10-25 | See GitHub file history | Source inspection at abf3141; documentation-only change | Plan available for cross-chat handoff |
| T0 | Merged | Codex / 2026-10-25 | [PR #465](https://github.com/jongsky25/css-is/pull/465), `docs/telegram-t0-contract` | [Source-backed design contract](TELEGRAM_T0_CONTRACT.md); main reconciled at f9e868e; checks below | Merged at `4cd01a0bfd17ccf57dba12b05a24c72bfd098f29`; live deployment unverified |
| T1.1 | Merged | Codex / 2026-10-25 | [PR #466](https://github.com/jongsky25/css-is/pull/466), `feat/telegram-t1-1-storage` | Four inert tables, independent default-off switches, migration/restart/restore and digest checks passed | Merged at `bef000127846aebb9fc1176c190664797d262eb4`; live deployment unverified |
| T1.2 | In review | Codex / 2026-10-25 | `feat/telegram-t1-2-webhook` (PR link added after opening) | Authenticated intake, durable deduplication, private help, bounded delivery; checks below | Release 8.56 candidate; switches off, no linking/business actions or live verification |
| T1.3–T7 | Planned | Unassigned | — | Not implemented | Follow dependencies |

### T0 handoff — 2026-10-25

- Owner: Codex. Draft [PR #465](https://github.com/jongsky25/css-is/pull/465), initial design commit `9148395`; opened and merged 2026-10-25 at `4cd01a0bfd17ccf57dba12b05a24c72bfd098f29` (release 8.54). Started and completed design on `docs/telegram-t0-contract` from main `f9e868e`; no merged T0 implementation was present at reconciliation.
- Delivered: [T0 contract](TELEGRAM_T0_CONTRACT.md), including exact service/field/role matrix, webhook choice, proposed schemas, grants, group disclosure policy, retention, switch names, restore/retry state contract and required service extractions. Documentation only.
- Checks: `git diff --check`, `python scripts/lock_dependencies.py --check`, `python scripts/check_vendor_dependencies.py`, `python scripts/ai_evaluation.py contract --base origin/main` passed. Relative Markdown links and six required contract sections verified with a local Python check.
- Initial release limitation: `python scripts/check_release.py release --base origin/main` fails because application version remains 8.53. CI applies this gate unconditionally, including documentation PRs. The initial documentation-only revision left release metadata unchanged; resolved on user instruction to merge by adding release 8.54 metadata and matching service-worker cache version. The release metadata gate now passes. No runtime tests were run for the original design-only change; release metadata was subsequently added to satisfy CI.
- Deployment/switch state: no deployment, credentials, webhook registration or feature activation performed. All two-way capabilities remain unimplemented/inactive. Existing digest behavior unchanged by this documentation change.
- Known gaps: production storage paths, snapshot durability, webhook ingress and Bot API egress remain unverified. Snapshot rollback may lose local commits; business writes must stay off until reconciliation/recovery is demonstrated. Design review is not live evidence.
- Next increment, now started after T0 merge: T1.1, four inert durable tables, independent default-off switches and migration/restart/restore fixtures plus existing digest regressions. Do not include inbound handling or business actions.

### T1.1 operator and implementation handoff — 2026-10-25

- Owner/branch: Codex, `feat/telegram-t1-1-storage`, based on T0 merge `4cd01a0`. [PR #466](https://github.com/jongsky25/css-is/pull/466) opened 2026-10-25; implementation commit `0b32c19`; merged at `bef000127846aebb9fc1176c190664797d262eb4`.
- Scope: additive `telegram_storage.install` via `storage.init_db`; four empty tables and independent exact-`1` environment switches from the T0 contract. No receiver, transport, scheduler, account linking, grants or business actions. The host upload closure includes the new module.
- Migration: normal application initialization installs tables/indexes idempotently. Existing business rows and Apprise digest preferences are preserved. No database topology change. A normal process restart preserves rows, claims and generations; this increment does not execute or recover queued work.
- Restore: all current `app.py` snapshot/seed hydration paths call `backups.clear_restored_sessions`; deliberate `backups.restore_backup` does too. That hook now pauses two-way connections even for routine snapshot recovery, rotates random generations, clears received payloads and stale claims, cancels pending operations/updates/deliveries and marks interrupted sends uncertain. Committed/partial/failed receipts and provider acceptance metadata remain. Legacy snapshots without these tables are supported. Future grant/group/preview increments must extend the hook when their tables exist.
- Operator steps: keep every `CSS_TELEGRAM_*_ENABLED` capability unset or `0`; do not register a webhook. Existing `CSS_APPRISE_TELEGRAM_ENABLED` remains separate. Turning a new switch on cannot activate a capability in this storage-only release. No bot secrets are needed for T1.1.
- Pause/rollback: unset the new switches; leave additive tables in place rather than deleting receipts. A code rollback must retain the restore hook before any future reactivation. After restoring a snapshot, do not manually mark rows active or resend uncertain work; receipt reconciliation and relinking belong to later increments. Existing digests retain their current separate restore semantics.
- Limitations: no cleanup worker or retry engine is implemented here; T1.2 and subsequent increments own runtime handling. Real production storage durability and transport remain unverified. No live sends or deployment verification claimed.
- Checks (using isolated `/tmp/telegram-test-venv`, installed from hash-locked `requirements-test.txt`, with `CSS_TEST_NOW=2026-10-20T06:00:00`):
  - `python -m pytest tests/test_telegram_storage.py tests/test_work_channels.py tests/test_deploy_hf.py tests/test_backups.py tests/test_phase0_persistence.py tests/test_persist_health.py tests/test_release_checks.py --tb=short --junitxml=/tmp/telegram-t1-1.xml`: 125 passed, no failures/skips. JUnit gate passed.
  - After adding actual `make_backup`/`restore_backup` coverage and invalid-state checks: `python -m pytest tests/test_telegram_storage.py --tb=short`: all 18 passed.
  - `python -m pytest tests/test_work.py -k 'digest or notification_preferences or routine_bell or quiet_preferences' --tb=short -q`: passed (exit 0).
  - `git diff --check`, release metadata (`--base origin/main`), dependency lock, vendor integrity, AI evaluation contract, compile checks and `pip check`: passed. Existing Starlette/httpx deprecation warning only. Full repository/browser suites were not run; no UI changed.
- Release metadata: 8.55 in version/changelog/service-worker cache, satisfying the unconditional release gate. T1.1 merged as PR #466; no deployed SHA or live evidence available.
- Next: T1.2 authenticated update ingestion, durable deduplication, private `/start` and `/help`, bounded handling. Do not bundle linking or calendar actions.

### T1.2 implementation and operator handoff — 2026-10-25

- Owner/branch: Codex, `feat/telegram-t1-2-webhook`, based on T1.1 merge `bef0001`. Release 8.56 candidate; in review, not merged or pilot verified.
- Delivered: `telegram_bot.py` authenticated webhook, durable receipt and rate limits, neutral private `/start` and `/help`, database-backed help queue and bounded processing/delivery; `telegram_transport.py` one fixed-provider Bot API attempt with bounded response, TLS, no redirects/retries or provider-body logging. Added scheduler call, exact public/Origin exception and runtime upload closure. Storage adds five indexes for rate checks, destination/connection history and retention only; no new tables or business workflows.
- Scope clarification: `/start` does **not** create a link challenge yet; T1.3 owns account linking. Group messages, callbacks, edited messages and unsupported commands are durably ignored. No arbitrary text, names, usernames, link arguments or provider response bodies are saved. Only neutral private help can be rendered/sent. Existing digest behavior stays separate.
- Processing/recovery: commit receipt before HTTP 200. Duplicate provider update IDs return the existing acknowledgement, even at the rate limit. Up to 20 updates/tick; help enqueue and processed marker share one transaction. Up to 20 delivery candidates/tick, one per destination per second after acceptance, with committed sending markers and conditional finalizers. Expired internal processing/claimed leases can recover; interrupted sending becomes uncertain and never auto-resends. Restore cancels pending work and fences in-flight finalizers. Current account/connection generation, configuration fingerprint, switch and private destination are rechecked before sending.
- Failure handling: only definite Telegram 429 rejection enters retry_wait (honor retry_after up to the 24-hour expiry, max five attempts). Permanent 4xx rejection fails that attempt and suppresses older queued replies for the destination; a **new authenticated private command**, after the rejection, is required to attempt another neutral reply. This refines the T0 destination-pause rule for an unlinked help-only bot without adding a destination management workflow. Network timeout, ambiguous 5xx, malformed/mismatched response and interrupted sends stay uncertain. Accepted means provider acceptance, not reading.
- Retention: input content is never persisted; minimal help descriptors are cleared on processing. Each tick scrubs routing/payload fields from at most 20 update receipts older than seven days while keeping ID/hash tombstones for deduplication, and deletes at most 20 terminal delivery rows older than 180 days. Pending help expires 24 hours after receipt. No task/calendar operation cleanup exists yet because this increment creates no business operations.
- Activation: leave all switches unset/0 for this PR. A later help-only operator pilot requires validated `CSS_TELEGRAM_BOT_TOKEN`, a random 32–256 character `[A-Za-z0-9_-]` `CSS_TELEGRAM_WEBHOOK_SECRET`, `CSS_TELEGRAM_INBOUND_ENABLED=1` and `CSS_TELEGRAM_DELIVERY_ENABLED=1`. All link/group/read/write/reminder switches remain 0. Register exactly `POST /integrations/telegram/webhook` on the canonical verified HTTPS origin through Telegram setWebhook with the matching secret_token; no polling/getUpdates or automatic registration is performed by the app. Do not put tokens into shell history, URLs in logs or the Markdown.
- Before enabling: verify actual deployed SHA, durable local DB/snapshot paths and restore behavior, public HTTPS routing, bot ownership, provider egress, and one webhook owner. Use a synthetic private account to check `/start`, `/help`, duplicate update handling and restart before introducing real staff. No such hosted pilot was performed in this increment.
- Pause/rollback: disable inbound (503/no new receipts) and delivery independently. Queued help may wait until expiry; processing requires inbound on. Uncertain attempts never resume automatically. Disable both before rollback or webhook removal. Preserve receipts/tombstones; never reset IDs or bulk replay pending updates. A fresh user command may request another help response; it does not authorize replay of an uncertain send or any business action. Existing Apprise digests are controlled independently.
- Tests: with hash-locked `/tmp/telegram-test-venv` and `CSS_TEST_NOW=2026-10-20T06:00:00`, `python -m pytest tests/test_telegram_bot.py tests/test_telegram_transport.py tests/test_telegram_storage.py tests/test_work_channels.py tests/test_deploy_hf.py tests/test_release_checks.py --tb=short --junitxml=/tmp/telegram-t1-2.xml` passed **126 tests**. `python -m pytest tests/test_request_origin.py tests/test_backups.py tests/test_phase0_persistence.py tests/test_persist_health.py tests/test_work.py -k 'not browser' --tb=short --junitxml=/tmp/telegram-t1-2-regressions.xml` passed **252 tests**. Coverage includes real application middleware, two concurrent receipt writers and send workers, enqueue rollback, restart, restore during send, credential-safe logs, bounds, rate limits, expiry, retries, retention and fixed-provider payload. No real network sends, credentials or staff data used. Full repository/browser suites were not run; no UI changed.
- Additional gates passed: diff whitespace, Python compilation, dependency lock, vendor integrity, AI evaluation contract, pip compatibility, release metadata 8.56 and both JUnit reports (no failures/skips). Existing Starlette/httpx deprecation warning only.
- Remaining gaps: no account linking/status/disconnect UI, group registration, calendar/room reads or writes. Production configuration and live behavior remain unverified; all two-way switches stay off by default. No external provider registration or activation performed.
- Next ready after T1.2 review/merge: T1.3 account link/status/disconnect and revocation, with expiring single-use challenge, cross-account and replay checks, action-specific consent and restore invalidation for its new tables.

### Per-increment handoff template

- ID / title:
- Status / owner / last updated:
- Branch / PR / merge SHA:
- Delivered behavior and files:
- Tests run and actual results:
- Open gaps or blocker / unblock action:
- Deployment version / switches / live evidence:
- Next ready increment and exact next action:

## Decision log

- 2026-10-25: User requested a durable GitHub Markdown plan, phased for Sol delivery, with mandatory updates when development starts or finishes.
- 2026-10-25: First release targets internal calendar plus existing conference-room requests and return notifications.
- 2026-10-25: Guided commands precede natural-language extraction; one bounded increment per implementation PR.
- 2026-10-25: Every future implementation PR must maintain this plan; production activation and verification are tracked separately.

- 2026-10-25: T0 selected as first ready increment; documented the implementation contract against f9e868e. No runtime behavior or production activation changed.

- 2026-10-25: User authorized T0 merge and next increment. T0 merged as PR #465; T1.1 started separately with inert storage and restore fencing.

- 2026-10-25: User authorized T1.1 merge and next increment. PR #466 merged at bef0001; T1.2 implemented separately. Neutral help uses fresh private commands to recover from permanent rejection; business actions remain out of scope.
