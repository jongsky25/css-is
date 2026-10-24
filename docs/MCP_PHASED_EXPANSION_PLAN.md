# Office Connect MCP expansion plan

Status: **Proposed**, October 24, 2026. Baseline: the read-only MCP expansion in v8.35 (PR #444). This document plans later increments; it does not enable any write tool or widen an existing OAuth grant. Production acceptance of v8.35 remains a separate deployment and real-client check.

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
