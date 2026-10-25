# Office Connect ↔ Telegram delivery plan

Status: planned; implementation has not started.
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

All T1–T7 increments are planned and inactive. No Telegram two-way feature has been implemented by this planning change.

| Increment | Status | Owner / date | PR / commit | Evidence | Activation / next action |
| --- | --- | --- | --- | --- | --- |
| Planning document | Published | Codex / 2026-10-25 | See GitHub file history | Source inspection at abf3141; documentation-only change | Plan available for cross-chat handoff |
| T0 | Planned | Unassigned | — | Existing sources and integration documents identified above | First implementation session: reconcile current main, then complete contracts |
| T1.1–T7 | Planned | Unassigned | — | Not implemented | Follow dependencies; expand each started row separately |

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
