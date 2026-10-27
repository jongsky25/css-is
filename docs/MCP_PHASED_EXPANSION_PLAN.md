# Office Connect MCP expansion plan

Status: **Incremental implementation**, updated October 27, 2026. Baseline: the read-only MCP expansion in v8.35 (PR #444). M1 reads and default-off M2.1 through M2.6 and M3.1 acknowledgement, M3.2 task-submission and M3.3 supply-submission pilots are implemented as recorded below. Existing OAuth grants are not widened. Hosted write acceptance remains separate from implementation.

## Goal and boundary

Let a person use ChatGPT to find permitted Office Connect information, prepare routine work and, in later phases, confirm selected actions through Office Connect. Keep the person, not the model, responsible for a consequential decision. Each result should show its source, current status and what was actually changed.

**No MCP phase will offer delete, cancel, withdraw, void, reverse, archive, discard or equivalent actions.** This applies to records, submissions, bookings, stock movements and files, including differently named tools with the same effect. Staff may still use existing Office Connect screens for actions those screens permit. Disconnecting an OAuth grant in Office Connect remains a security control, not a business-record cancellation.

MCP remains an AI-client interface. Existing versioned API and change-feed/webhook contracts remain the preferred path for non-AI systems. A client does not gain more domain access because it uses MCP.

## Current baseline

v8.35 offers read-only tools for permitted work and document metadata, calendar events and room bookings, supply queues, personal travel filings, manager-scoped activity progress and a combined overview. Its OAuth scopes are `work:read`, `documents:read`, `calendar:read`, `supplies:read`, `travel:read` and `activities:read`. The overview includes only granted areas and labels others `not_granted`. Account status, grant status, scope and current record authority are checked again at read time. No file bodies, private task submissions, individual survey answers, claim amounts, meeting URLs or write actions are exposed by this baseline.

Before expanding this baseline, complete a real ChatGPT connection with a low-privilege account, compare returned records with the Office Connect screens, test grant revocation, and record deployment SHA/version and observed limitations. An empty tool result must be checked against source data and scope before calling it a successful business answer.

## Coverage map

| Area | Additional reads to consider | Eligible writes, in later phases | Authority and content boundary |
| --- | --- | --- | --- |
| Shared work and tasks | Blockers, decisions, discussion summaries, milestones and permitted history | Create a draft task or comment; acknowledge an assigned task; submit completed work for review; update permitted task details | Reuse case, task, assignment, linked-document and revision checks. Private submissions require a separate, explicit scope. |
| Documents | Authorized status history, review queue, version metadata and selected text excerpts | Create an outgoing draft or note; submit a draft for review | Keep files and body text behind separate content scopes. Signing, official dispatch and external sends stay on the Office Connect confirmation screens. |
| Calendar and rooms | Availability, event detail, permitted participants and room request status | Create or edit a personal event; request a room; add a permitted agenda note | Preserve audience, attendee, room-admin and conflict rules. Meeting links require a separate scope; no booking cancellation. |
| Supplies | Catalog and availability, own request lines, authorized approvals, delivery/issue status and aggregated stock dashboards | Save and submit one's own request; acknowledge received supplies; authorized approver decision; controlled receipt or issue posting | Reuse current unit grants, stock ledger, reservation and idempotency rules. Ledger posting is a late, separately enabled phase. No stock reversal. |
| Travel | Own checklist, reviewer feedback status and filing milestones | Save a personal filing draft; request review; submit a completed filing; authorized reviewer decision | Keep claim amounts, receipts, scanned content and documents separate from ordinary status reads. No withdrawal. |
| Activities, registration and reports | Team-scoped activity detail, registration totals, de-identified survey aggregates and report links | Save an activity draft; update a permitted schedule; publish an invitation after confirmation; save a report draft | Reuse Monitor/team visibility. No individual survey answers, roster export or publication from a general read scope. |
| Notifications, meals and work arrangements | Own notices, meal request status and work-arrangement status | Mark one's own notice read; create or update an own request where the UI already allows it | These are personal scopes. A shared summary must not turn another person's requests into a team-wide feed. |
| Wellness and other sensitive records | Personal status only, if a specific need and privacy review establish it | Personal draft or submission only after a separate pilot | Never include health or sensitive details in default consent or general overviews. |
| Administration and integrations | Read-only readiness, connector health and aggregate audit/usage metrics for authorized administrators | No role grants, credentials, policy changes or integration-secret updates through MCP in this plan | Preserve the existing administrator screens and approval boundary. |

The map is a candidate inventory, not permission to expose every field. Each increment must list exact fields and source services. If a safe projection cannot be made, provide a source link to the Office Connect screen instead of returning sensitive content.

## Phased delivery

### M0 — Establish live baseline and action contract

Verify v8.35 in a real ChatGPT connection with representative viewer, manager and custodian accounts. Document the exact OAuth callback/client behavior, scope display, revocation latency, mobile/desktop differences, empty-result handling and source-link behavior. Measure read latency, query count, response size and audit volume without copying private content into artifacts. Inventory each proposed write against its existing service and current UI permission checks.

Define the common write contract before publishing any write tool: a separate action-specific OAuth scope, strict input schema, current account and record authority, feature switch, expected record revision, user-visible preview, single-use confirmation, persisted idempotency key and operation receipt. A write must recheck all conditions inside the committing transaction. Recovery from a lost response must return the original receipt or prove that no commit occurred; it must not silently create a new key and repeat the action. Do not ask the model to carry passwords, session cookies or OAuth tokens in chat text.

**Gate:** real-client read and revocation evidence; permission matrix and field projections reviewed; one written transaction/receipt design with failure and retry cases accepted.

### M1 — Complete low-sensitivity reads

Add small, paginated tools for own notifications and requests, calendar availability, supply catalog/authorized stock status, work blockers and permitted report totals. Keep personal and team scopes separate. Include `as_of`, pagination, source links and explicit `not_granted`/`not_available` states in cross-module summaries. Add search only through existing permission-checked query services; do not create a raw SQL or arbitrary export tool. Consider approved document excerpts and work discussion only as separately consented content reads with clear length and retention limits.

**Gate:** each tool matches the corresponding Office Connect screen for low- and high-privilege synthetic accounts; revoked access disappears on the next call; hidden records and private text never appear in search snippets or errors; bounded queries meet the capacity target set in M0.

### M2 — Personal preparation and low-impact state

Start writes with drafts and personal state: mark an own notification read, save an own report view, prepare a task comment draft, save a personal calendar entry or travel/supply request draft where the domain service supports drafts. Show the exact proposed fields and destination before confirmation. The model may propose text, but the user must review it. Do not send invitations, submit work, allocate stock or make an approval in this phase.

Use granular scopes such as `notifications:mark_read`, `calendar:event:draft` and `travel:filing:draft`; a broad `*:write` scope is not acceptable. Tools cannot use an old read-only grant for writes. Keep write capabilities off by default until the module's tests and an operator pilot pass.

**Gate:** explicit consent and confirmation, stale-revision rejection, duplicate-call idempotency, cross-user denial, audit/receipt visibility, lost-response recovery and ordinary screen parity.

### M3 — Submit routine work for someone else's review

Extend the same preview/confirm/receipt pattern to task acknowledgement and submission, supply request submission, travel review requests and filing submission, room requests, meal/work-arrangement requests, and activity draft submission or invitation publication where the current user has the underlying authority. Reuse existing services instead of updating tables directly. A submission result must report the actual new state, responsible next party and a source link. These operations create or advance work; none may cancel or withdraw it.

For task acknowledgement/submission, align with the existing `/api/v1` operation-key, revision and receipt contract, including its rule that a timeout is not proof of failure. For external mail, calendars or document relays, use an outbox/operation state so a retry cannot send twice. Keep signed documents and financial/stock posting out of this phase.

**Gate:** two independent clients racing on the same revision commit at most once; disabled modules and revoked role grants block writes; a lost response is recoverable; notification/outbox failure cannot produce an unexplained partial business action; staff complete the same workflow in the UI and through MCP with the same authority.

### M4 — Controlled decisions and operational posting

Pilot one high-impact action at a time for a named role: review acceptance, supply request approval, room request approval, travel reviewer decision, or stock receipt/issue posting. Require a fresh source read, current role and assignment, exact revision, structured preview of downstream effects, explicit per-action human confirmation and a durable receipt. Enforce separation of duties: a requester cannot approve their own request, and technical administration alone does not grant business authority. Model text cannot become a policy, signature or decision without the authorized person's confirmation.

Do not expose document signing, official dispatch, payment, credential/role changes or bulk record edits as direct MCP writes under this plan. MCP may prepare a draft and deep-link to the existing signed-in screen for those actions. A later proposal would need its own threat model and acceptance decision.

**Gate:** representative approver/custodian pilot, concurrency and stock-equation checks, downstream notification reconciliation, rollback/recovery drill, audit review and a recorded go/no-go decision for each individual action. A passed read phase does not automatically activate writes.

### M5 — Interoperability, scale and operating review

Document MCP tool schemas, error codes and versions alongside the existing API/OpenAPI and change-feed contracts. Publish examples for ChatGPT and one independent test client. Add contract tests for scope negotiation, client upgrade, pagination, permission withdrawal, restore and replay. Monitor aggregate tool latency, error rate, rate-limit hits, token refresh, audit growth and queued side effects. Revisit SQLite/hosting capacity using measured workload before increasing throughput or replica count; a multi-worker deployment needs coordinated rate limits and transactional guarantees.

**Gate:** a supported rollback path, owner/operator runbook, measured performance and privacy review, and evidence that AI and non-AI clients see consistent current state. Keep a versioned tool contract so existing clients do not silently receive broader data or new write authority.

## Standard acceptance for every increment

1. Define the exact user question or action, fields, role, OAuth scope, source link, maximum page/body size and expected empty/disabled result.
2. Compare permitted and hidden results with the current UI service using multiple users, unit boundaries, reassignment, account deactivation, grant revocation and restricted records.
3. For a write, show an exact preview and require an explicit human confirmation tied to actor, target, payload digest, revision and a short expiry; revalidate inside the transaction.
4. Test two-client races, repeated requests, timeouts after commit, restart/restore handling, audit attribution and downstream notification failure. No model-generated retry may silently create a second action.
5. Run required repository checks, deploy behind a per-module switch, test a real connector with synthetic or agreed test records, and record the observed version, result and rollback route before enabling broader use.

## First eligible increment

After M0 acceptance, build **M1.1: own notifications and calendar availability reads**. They answer common questions without exposing file content or committing business changes. Define a separate scope for personal notifications, reuse their existing owner checks, and return at most 25 entries with links and clear unread state. Compare against the signed-in screens and confirm immediate denial after disconnect. Then choose the next M1 read from actual usage evidence; do not open M2 write access before the common action contract is accepted.


### M1.1 implementation record — v8.42

The first delivery adds own unread **shared-work notice metadata** and **conference-room request-slot availability**. Other notification domains and personal free/busy remain outside this delivery. See [pilot setup and acceptance](MCP_READ_ADAPTER.md#m11-pilot-switches-and-acceptance). Both tools are independently disabled by default. New notifications require `notifications:read`; room availability uses `calendar:read`. No existing grant is expanded and no business state is written. Automated permission, pagination, source-parity and privacy checks are included; hosted acceptance and capacity evidence are pending. Broader M1 reads and M2 writes remain separate increments.


### M1.2 first implementation — v8.44

Begin satisfaction survey coverage with `get_csm_summary(year, month)`, a bureau-wide Type 1 monthly aggregate under separate `surveys:csm:read` consent. Shared date/SQD helpers keep existing reports and the new projection aligned. No individual responses, comments, identities or demographic filters. Score suppression and capacity limits are explicit; the independent pilot flag defaults off. See [CSM pilot contract](MCP_READ_ADAPTER.md#m12-first-delivery-monthly-type-1-csm). Service-level breakdowns, comparisons, Type 2 activity surveys and Type 3 resource-person ratings remain subsequent increments, each with its own authority/privacy review. Hosted acceptance is pending.


### M1.2 second implementation — v8.45

Add a separate-consent, default-off bureau-wide quarterly Type 2 activity-satisfaction summary. Share existing SERVQUAL report calculations; preserve activity-start dates, item scales and sparse-answer denominators. Exclude personal responses and speaker ratings, withhold all small-sample scores and refuse partial capacity results. Individual activity/unit breakdowns and Type 3 resource-person summaries remain subsequent increments. See [Type 2 pilot](MCP_READ_ADAPTER.md#m12-second-delivery-quarterly-type-2-activity-satisfaction); hosted acceptance remains pending.


### M1.2 third implementation — v8.46

Add a separately consented annual Type 3 summary for one currently visible resource person. Reuse the person dashboard's quality index and Type 3 dimensions, share current hidden/Director checks with the profile routes, exclude respondents/comments/rankings, and withhold small-sample scores. The independent pilot flag defaults off. See [Type 3 pilot contract](MCP_READ_ADAPTER.md#m12-third-delivery-annual-type-3-resource-person-summaries). Per-activity/unit comparisons, broader breakdowns and writes remain later work; hosted acceptance is pending.


### Individual activity discovery/detail implementation — v8.48

Add metadata-only quarter/title discovery and a full Type 2 scorecard for one selected merged activity. Shared grouping preserves representative/member links and current group changes. New detail-read consent and an independent default-off pilot flag prevent broadening old quarterly/progress grants. Exclude respondents and speaker scores; preserve suppression/capacity gates and distinguish unavailable source scorecards. See [discovery/detail pilot](MCP_READ_ADAPTER.md#individual-activity-discovery-and-satisfaction-details). Earlier live pilot acceptance remains pending; this implementation does not mark it complete. Unit trends, comparisons and writes remain separate work.

### Unit Type 2 summary implementation — v8.49

Add current reporting-unit discovery and quarterly summaries for one lead unit and its descendants. Match existing report-view authority and exact slash-delimited unit selection; reuse consolidated Type 2 arithmetic, suppression and capacity refusals. New `surveys:units:read` consent and independent default-off `CSS_MCP_UNIT_SURVEYS_ENABLED` preserve older grants. No comments, individuals, speaker ratings or rankings. See [unit pilot contract](MCP_READ_ADAPTER.md#unit-discovery-and-quarterly-type-2-summaries--v849). Live acceptance remains pending, including earlier survey pilots. Period comparisons and writes remain subsequent increments.

### Consecutive-quarter unit comparison implementation — v8.50

Add one selected unit's Type 2 quarter versus its immediately preceding quarter. Use the existing unit attribution and source scorecards within one authorization snapshot; publish original-scale-point changes only when both periods pass all scoring/suppression/capacity rules. New `surveys:unit_trends:read` and independent default-off `CSS_MCP_UNIT_TRENDS_ENABLED` preserve older grants. No arbitrary periods, peers, rankings or causal claims. See the [comparison pilot contract](MCP_READ_ADAPTER.md#consecutive-quarter-unit-comparisons--v850). Local implementation does not establish hosted acceptance. Broader trends and writes remain later increments.

### Consecutive-month Type 1 CSM comparisons — v8.52

Add a fixed bureau-wide submission month versus its immediately preceding month. Reuse official ARTA CSM predicates, pooled SQD1–SQD8 overall and per-item denominators; return percentage-point changes from the published one-decimal report values only when both periods pass small-sample/capacity checks. New `surveys:csm_trends:read` consent and independent default-off `CSS_MCP_CSM_TRENDS_ENABLED` preserve older grants. No service/demographic filters, comments, identities or causal claims. See the [monthly comparison pilot](MCP_READ_ADAPTER.md#consecutive-month-csm-comparisons--v852). Hosted acceptance, including previous pilots, remains pending; broader breakdowns and writes remain subsequent increments.

### Resource-person discovery and consecutive-year comparisons — v8.53

Add permitted name/ID lookup and one selected person's Type 3 annual results versus the previous year. Share the dashboard's current hidden/Director predicate and quality-index/dimension arithmetic, label historical people, filter visibility before discovery paging and use minimal person metadata. New `surveys:resource_person_trends:read` consent and independent default-off `CSS_MCP_RESOURCE_PERSON_TRENDS_ENABLED` preserve older named-summary grants. No peer rankings, contacts, respondents or causal claims; both periods must pass all existing sample/capacity rules before any scores or changes are published. See the [person comparison pilot](MCP_READ_ADAPTER.md#resource-person-discovery-and-consecutive-year-comparisons--v853). All hosted acceptance remains pending. Broader breakdowns and writes remain later work.

### Implemented operator status view — v8.62

`/account/integrations/mcp`, linked from the existing Connected tools screen,
provides phone-accessible running build/catalog inspection, pilot-switch status,
own-connection scope checks and source-based survey verification prompts. It
adds no MCP tools or write capability and cannot refresh ChatGPT's saved catalog.
Live survey acceptance remains pending; use the page to distinguish host setup,
connection consent and ChatGPT registration before the deferred desktop check.

### Activity discovery archive-size fix — v8.65

Remove the global 2,000-form discovery gate that refused narrow searches on the
hosted archive. Discovery groups only the requested quarter in SQLite, filters
the authoritative group title and pages bounded metadata results. Detail resolves
one current group directly. Keep existing tool contracts/consent, source scoring,
response/sample guards and bounded query work; large unrelated inventories no
longer refuse these reads. Synthetic large-inventory and source-parity tests pass;
repeat the Regional BHW Summit Forum Q3 2026 hosted check after deployment before
recording live survey acceptance.

### Linked Type 3 resource-person selectors — v8.71

Outside activity progress now supplies the correct Type 3 source report link.
Under the existing explicit annual resource-person permission/pilot and current
visibility, it also supplies bounded linked person IDs for the existing annual
summary tool. This closes the activity-to-person selection gap using existing
tool registrations; it does not introduce one-activity Type 3 analytics or
reinterpret annual results as an activity scorecard. Hosted acceptance remains
pending, including the Regional BHW Summit Forum resource-person handoff.

### Activity-specific Type 3 named-person scorecards — v8.74

Implemented a separately consented/default-off one-person, one-current-activity
read using the per-person activity page's quality index, OSQ and five dimensions.
Current hidden/Director visibility, source engagement cutoff, full merged-group
resolution and established small-sample/capacity guards apply. Existing outside
activity metadata now carries an explicit activity/member ID for the new tool.
Annual and activity-specific contracts remain distinct; no existing grant is
widened. Live activation and per-person Summit/source-page acceptance remain
pending consent, host switch and a supported ChatGPT catalog refresh.

### Operator-reported read acceptance — October 27, 2026

The operator reports all requested live read checks passed. The Summit's two
named-person activity scorecards were retrieved through the refreshed ChatGPT
catalog and explicitly confirmed against their exact source pages. This closes
the reported desktop setup and Summit score-parity blocker. No deployment SHA,
per-role evidence, revocation timing or capacity measurements were supplied;
those M0 operating evidence fields remain unrecorded. See the
[acceptance handoff and write contract](MCP_WRITE_PILOT.md).

### M2.1 implementation — v8.78

Add `mark_my_notification_read` to prepare one own shared-work notice action and
`get_mcp_operation` to recover its durable receipt. Separate optional
`notifications:mark_read` consent and default-off
`CSS_MCP_NOTIFICATION_WRITES_ENABLED` govern the pilot. Execution requires an
actor/grant/revision-bound, expiring preview and explicit signed-in browser
confirmation. Share the UI domain service and atomically commit the marker,
receipt and audit; reject stale, revoked and cross-user requests and serialize
duplicate confirmations. Tests include recovery, rollback and mobile no-script
confirmation. See [operator activation and acceptance](MCP_WRITE_PILOT.md).
Hosted write acceptance remains pending; other M2/M3/M4 actions remain future work.

M2.1 merged in [PR #489](https://github.com/jongsky25/css-is/pull/489), commit
`a44873cee6912e34563d0bb2f7be1087e0b08856`. Merge does not record hosted acceptance
or enable the pilot.

### M2.2 implementation — v8.79

Prepare a new own supply-request draft with exact purpose/date and bounded
active catalog item/quantity lines. New `supplies:request:draft` consent and
independent default-off `CSS_MCP_SUPPLY_DRAFTS_ENABLED` do not widen existing
read/notification grants. Recheck current staff/unit linkage and catalog
revisions on an expiring signed-in browser preview. Atomically call the shared
UI save-draft service with durable receipt/audit; retries cannot overwrite later
UI edits or create duplicates. No submissions, control numbers, stock
allocations, approval notices or edits to existing drafts. See the
[supply-draft pilot contract and acceptance runbook](MCP_SUPPLY_DRAFT_PILOT.md).
Hosted acceptance remains pending; additional M2 drafts and M3/M4 actions remain
future work.

M2.2 merged in [PR #490](https://github.com/jongsky25/css-is/pull/490), commit
`436fc7d07619d9b8b31fc134c122130c1d0fc178`. Hosted acceptance/activation remain
separate from merge.

The earlier action modules were added to the hosting allowlist in v8.80,
[PR #491](https://github.com/jongsky25/css-is/pull/491), merge
`de60adeb68a405da7ef597c79a6422d832d3eb8f`. Runtime import-closure tests pass;
this packaging fix does not activate or accept a hosted pilot.

### M2.3 implementation — v8.81

Prepare and explicitly confirm saving an owner-private text draft for one
currently permitted contribution. Separate `work:comment:draft` consent and
default-off `CSS_MCP_COMMENT_DRAFTS_ENABLED` preserve existing grants. Recheck
current case/task authority/revisions on a short-lived browser preview; save the
private draft, receipt and body-free audit atomically with same-key recovery.
Owner-only source/listing and exact-task compose prefill let the person review
the draft in the existing UI. No MCP posting, notices, mentions, task submission
or workflow changes. See [pilot contract and acceptance](MCP_COMMENT_DRAFT_PILOT.md).
Hosted acceptance remains pending; other M2 preparation and all M3/M4 MCP writes
remain separate work.

M2.3 merged in [PR #492](https://github.com/jongsky25/css-is/pull/492), commit
`1ee20da23cd7fc84aaa278d9268f41be7440268e`. This does not activate or record
hosted acceptance for the private-comment pilot.

### M2.4 implementation — v8.82

Save a new owner-private named survey report selection after explicit browser
confirmation. New `reports:view:save` consent and default-off
`CSS_MCP_REPORT_VIEWS_ENABLED` preserve existing read/draft grants. Restrict this
first delivery to one Type 1 CSM month or Type 2 activity quarter; generate exact
source links without loading survey results. Bind actor/grant/payload/expiry,
recheck current role/name/capacity, and atomically save preference/receipt/audit.
Owner-only Reports collection/source pages reopen current report data through
ordinary report permissions. No report mutation, content, export, sharing,
overwrite or delete. See [pilot contract and acceptance](MCP_REPORT_VIEW_PILOT.md).
Hosted acceptance and other M2/M3/M4 actions remain separate work.

M2.4 merged in [PR #494](https://github.com/jongsky25/css-is/pull/494), commit
`7ed5fa5f83bc7ac0b461e45859b3fc2789bdd05c`.

### M2.5 implementation — v8.83

The default-off personal-calendar pilot adds a separately consented
`calendar:entry:create` action. ChatGPT prepares bounded title/date/time/venue/note
fields; the signed-in user confirms the exact preview before the existing domain
service saves one tentative meeting visible only to that user. No invitations,
rooms, recurrence, Meet links, activity links or travel filings are created.
Current Calendar eligibility, session/grant/scope and payload integrity are
rechecked. Original UID/operation identity, receipt and integration audit commit
atomically with the entry; retries never overwrite later normal Calendar edits.

See [setup, boundaries and acceptance](MCP_PERSONAL_CALENDAR_PILOT.md).
Automated OAuth/MCP/browser and domain checks cover local behavior. Hosted write
acceptance remains pending; further M2 and all M3/M4 actions remain separate work.

M2.5 merged in [PR #495](https://github.com/jongsky25/css-is/pull/495), commit
`9db1f2c1c877cdee1aea9c0cac90375e699be9e7`.

### M2.6 implementation — v8.84

The default-off travel reimbursement pilot adds separate `travel:filing:draft`
consent, excluded from default OAuth scopes. ChatGPT prepares an own standalone
reimbursement filing; signed-in browser confirmation opens its normal incomplete
In progress checklist. Exact activity/DPO/role fields, every proposed Yes/No
answer, initial checklist, working-day deadline, Admin Unit visibility and ordinary
reminder behavior are shown before confirmation. Current policy, session,
connection, scope and payload are rechecked under the writer lock.

The normal travel domain service creates the filing/checklist atomically with
original identity, content-free integration audit and receipt. Exact retries do
not overwrite later normal travel actions. Completed/expired preview and derived
checklist copies are cleared. No linked calendar/activity, cash advance,
liquidation, amounts, generation, review request, submission, approval or payment
is performed. See [pilot setup and acceptance](MCP_TRAVEL_DRAFT_PILOT.md).
Hosted acceptance remains pending; further M2 and all M3/M4 writes are separate.

M2.6 merged in [PR #496](https://github.com/jongsky25/css-is/pull/496), commit
`6bd192a863b6574caf040e52b90ae30f781a822d`.

### M3.1 implementation — v8.85

A separately consented, default-off `work:task:acknowledge` pilot prepares an
acknowledgement for the current owner's To do task. Signed-in browser review
shows exact task/work-item identity and revision, progress note, In progress
transition and ordinary shared-work history/review/notice effects. Confirmation
rechecks current authority, workflow and snapshot under the writer lock.

The canonical API operation service now supplies a caller-owned transactional
acknowledgement entry point, preserving fingerprint and immutable-receipt
contracts. One persisted UUID v4 key supports canonical API reads/replays; task,
history/audit effects and API/MCP receipts commit atomically. Recovery reports
original status/revision, next actor and source links without repeating later
work. No submission, approval, owner/deadline change or external relay is added.

See [M3.1 setup, acceptance and rollback](MCP_TASK_ACKNOWLEDGEMENT_PILOT.md).
Hosted M2/M3 acceptance remains pending and no write flag is activated. Other
M3 actions and all M4 decisions remain separate increments.

M3.1 merged in [PR #497](https://github.com/jongsky25/css-is/pull/497), commit
`a54aea0cf584462f3a17be6bc45696fdbdd52f48`.

### M3.2 implementation — v8.86

Separate default-off `work:task:submit` consent prepares submission of an assigned
In progress task. The owner reviews the complete exact output/note, current
revision, saved-output replacement/history visibility and lead/unit review
routing in the signed-in browser before moving it to For review. Current
blockers, prerequisites, changed-decision reviews, ownership, linked access,
workflow availability and snapshots are rechecked inside the writer transaction.

A shared caller-owned API submission entry point preserves canonical fingerprint,
session checks and immutable receipts. Task/output/history/audit/review/notice
effects and API/MCP receipts commit atomically with historical next-review-party
metadata. Stable UUID v4 keys support exact API replay; recovery does not repeat
submission or overwrite later review decisions. No acceptance, approval,
completion, owner/deadline changes, uploads or external relay are added.

See [M3.2 setup and acceptance](MCP_TASK_SUBMISSION_PILOT.md). Hosted write
acceptance remains pending and all flags remain unchanged. Other M3 actions and
all M4 decisions are separate increments.

M3.2 merged in [PR #498](https://github.com/jongsky25/css-is/pull/498), commit
`5c09167e51882e6e4d7f4b1b50d2904ce41caafa`.

### M3.3 implementation — v8.87

Separate default-off `supplies:request:submit` consent prepares an existing own
draft or returned request. Browser review shows exact lines/quantities,
purpose/date, current requester/unit, catalog revisions and approval routing.
The existing zero-eligible-approver behavior remains explicit: submission may
proceed with a routing warning and awaits a configured eligible approver.

The shared domain submission service now offers a caller-owned transactional
entry point. Immutable submitted header/lines, control numbering, normal
operation/event/audit and MCP completion/routing metadata commit together. All
bound identity/catalog/routing/revision conditions are rechecked; independent
previews against one revision commit once. Exact recovery preserves later
returns/edits and old submitted versions. No approval, reservation, issuance,
purchase, payment, withdrawal or external relay is added.

See [M3.3 setup and acceptance](MCP_SUPPLY_SUBMISSION_PILOT.md). Hosted write
acceptance remains pending and no flag is activated. Other M3 actions and all M4
decisions remain separate increments.
