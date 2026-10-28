## 9.04 — October 28, 2026

- Apps Script `activity_templates.gs`: `at_dropLeadingBlank_` shrinks the header's blank first line instead of deleting it. Docs accepted the deletion but refused to save the document afterwards, which made `makeActivityTemplates()` fail for any newly built template ("Service Documents failed while accessing document"). Templates already built are unaffected.

## 9.03 — October 28, 2026

- DPO: use the venue named in the invitation (or DPO-cites) when the item has none (spot feedback #184, #187). File-copy page: pre-fill the reviewer's name and title in row 2 of the first box (S4/S5 and S1–S3 reviewers, from the traveller's section; blank if unknown or mixed), centre column 2, size both boxes to their text, and suggest keywords and related issuances read from the invitation (#185, #186). The relay `extras` carry `reviewer`, `keywords` and `issuances`; an older relay ignores them.
- Add the `notice_of_meeting` document (draft in Google Docs, suggested for meetings; run `makeActivityTemplates()` to create its template) (#189, #192).
- Add "Expected participants from other offices" to calendar items and the entry page; required when the item's room request asks for meals (#188, #190).
- Supply request form explains an empty item catalog (#191). Spot feedback #193 is covered by 9.02: that request is still pending in the app because the approver has not decided it there.

## 9.02 — October 28, 2026

- Show a "break time has passed and your approver hasn't decided yet" note on a still-pending wellness break request in My break requests, so an undecided request is not mistaken for an approved one that failed to appear. Display only: approval routing, expiry and notifications are unchanged.

## 9.01 — October 28, 2026

- Disable live lifespan scheduler loops by default in the shared pytest fixtures, so native/MCP delivery tests own their worker calls and queued notices. Startup tests explicitly opt back in; production scheduler behavior is unchanged.
- Anchor Telegram change-route expiry coverage to the immutable SQL-trigger event timestamp plus its TTL, rather than a fixed Python date that drifts from SQLite's real clock.
- Increase full normal/shuffled test-job budgets from 45 to 75 minutes to include OCR/browser setup, both complete suites and mandatory JUnit/evaluation/artifact gates. Preserve dependency, release metadata, full-test and backup requirements before deployment.

## 9.00 — October 27, 2026

- Add default-off `travel:review:decide` context/preview/recovery for the current selected Administrative Section reviewer: approve complete papers with no draft notes, or return exact notes already drafted in Office Connect. Refuse self-review and technical-only authority; do not accept model note text or recipient overrides.
- Bind full filing/checklist/raw document metadata/flags/notes, review round, directory/account recipient identity and mail policy to a ten-minute browser preview. Share caller-owned native decision transactions and commit decision, domain/integration audits, permanent round identity, minimal receipt and single-attempt notice together. Old receipts preserve later Ready, edits and review rounds.
- Add a bounded current-grant/source/reviewer/recipient worker using native travel-result mail and logs. Disabled-at-confirmation notices remain skipped; expired queues cancel, ambiguous/crashed/result-write attempts become uncertain without automatic resend, and no files/attachments, Ready/submission, signing/dispatch or claim approval/payment occur. Include native, OAuth, phone without scripts, race, rollback, delivery, retention, packaging and deferred hosted acceptance coverage.

## 8.99 — October 27, 2026

- Add default-off `rooms:request:approve` context/preview/recovery for current Administrative Section approval of another person's plain internal room request. Exact browser review shows requested hours, requester, reason, pending-rival count and email/preference/quiet-hour/ICS policy; self/filing-actor and technical-only approval are refused.
- Share a caller-owned native booking/audit transaction, preserving ordinary Rooms rival/move/series/meal behavior outside the pilot. Commit held slots, decision/domain audit, requester bell/notice, retained identity, delivery marker and MCP receipt together; reject stale/conflicting/unsupported sources and preserve later ordinary withdrawal or edits on recovery.
- Add gated single-attempt requester email with current source/authority/recipient/preferences, quiet-hour waiting, reviewed ICS settings and native mail-loop exclusion. Disabled-at-confirmation skips remain terminal; ambiguous/crashed/result-write failures never resend. Include native/OAuth/mobile, booking/worker races, rollback, stale policy, cleanup, packaging and deferred hosted acceptance coverage. Travel reviewer decisions remain the next separate increment.

## 8.98 — October 27, 2026

- Add default-off `supplies:request:approve` context/preview/recovery for scoped non-requester approval at exact submitted quantities. Exact browser review shows submitted requester/unit/purpose/date, every full approved quantity, initial reserved/awaiting-stock effects and decision reason; reductions, displacement and earlier reservation cycles use ordinary Supplies.
- Share a caller-owned native decision transaction and oldest-first allocation arithmetic. Recompute actual post-insert allocation against the reviewed plan before applying it; atomically commit decision, initial reservations, domain events/audit, durable warning snapshots and minimal MCP receipt. Refuse changed existing reservations, stale stock/catalog/queues and self/technical-only authority.
- Verify original immutable submission/decision/domain receipts, preserve later ordinary issuance/stock changes on recovery, and retain normal post-commit custodian warning reconciliation. Include OAuth, mobile, separation, stock equations, older-demand fairness, races, rollback, warning failure, cleanup, packaging and named pilot go/no-go coverage. No physical movement, issuance, purchase/payment, signature/dispatch or direct email is exposed.

## 8.97 — October 27, 2026

- Add default-off `work:task:accept` context/preview/recovery for a first M4 decision pilot: the current confirmed work-item lead accepts another person's exact canonical For review contribution as Done. Separate consent and exact signed-in output/reason review are required; owner, actual submitting actor, proposed lead and technical/officer authority alone cannot accept through the pilot.
- Reuse the native transactional Work task service for status/revision, preserved output/owner/due date, immutable history/audit, review invalidation and legacy notice cancellation. Bind current source/submission/identities/linked access/dependents/notices; commit the decision, minimal MCP receipt and integration audit atomically.
- Preserve later ordinary reopen/resubmit flows on recovery, verify original source/history identities, clear preview copies, and cover OAuth, separation of duties, rollback/races, dependent effects, access withdrawal, mobile, packaging and operator go/no-go. No whole-work-item completion, official approval/signature/dispatch, direct email or financial/stock posting is exposed.

## 8.96 — October 27, 2026

- Add default-off `activities:announcement:publish` context/preview/recovery for first pinned-update publication on a current/upcoming bureau activity with active forms. Exact signed-in review shows activity, escaped text, registration count and current/future participant-page visibility; no registrant email, invitation or approval is added.
- Share the ordinary Manage pinned-update save/audit service using caller-owned transactions. Commit text, retained original publication identity, audits and receipt atomically; preserve later ordinary edits/clear on recovery and prevent another key from republishing the same original activity.
- Recheck current management, directory/team scope, event/form metadata and audience-count revision; retain bounded previews and permanent operation identities. Include OAuth, mobile, participant-page, ordinary UI/email, race, rollback, source identity, retention, packaging and operator acceptance coverage.

## 8.95 — October 27, 2026

- Add default-off `activities:draft:create` context/preview/recovery for one live bureau activity plus Form 2 from an own private draft. Exact signed-in review shows public-link effects, current fields/section and creator/section-chief mail recipients; no participant invitations, bookings, approval or signature is added.
- Share an atomic plain-bureau creation helper with supported ordinary Create submissions, allowing the existing event/form services to join caller-owned transactions. Retain one draft-to-activity identity across keys, reject strong duplicates, and commit event/form, mapping, audits, receipt and initial notice states together.
- Deliver enabled internal notices through durable single-attempt claims with current authority/source/routing/mail checks. Disabled-at-confirmation notices skip permanently, ambiguous/crashed attempts never resend, original receipts preserve later edits, and private sources show an existing confirmed creation. Include concurrency, rollback, OAuth, public/ordinary UI, mail, mobile, packaging and operator acceptance coverage.

## 8.94 — October 27, 2026

- Add owner-private single-day bureau activity drafts with a shared strict save service, ordinary new/list/source screens and guarded Create prefill. Saving/loading creates no event, survey, public registration/link, calendar/room/travel record or notification; later manual Create submission stays separate and is not tracked as draft consumption.
- Add default-off `activities:draft:save` section-choice/preparation/recovery tools and exact signed-in confirmation under current Create capability. Bind requester/section/date policy, commit source/tombstone/audits/receipt atomically, retain stable save-key identities and clear completed/expired preview copies.
- Enforce owner-only access even for other managers/admins, current role/section checks on loading, CSRF/Origin/bounded forms, replay/race/rollback protection and bounded source/preview collections. Include OAuth refresh, real UI save/load/creation parity, mobile, runtime packaging and operator acceptance coverage.

## 8.93 — October 27, 2026

- Add default-off `activities:dates:update` context, exact signed-in preview and recoverable original date-change receipts for upcoming unused single-day bureau activities with one Form 2.
- Share ordinary creator/admin/team management authority and date-horizon policy; require a fresh full-metadata revision and reject registrations, responses, entry windows, attendance, extra/shared forms and linked calendar/room/travel records. Atomically update the event/form through the canonical date service with domain/integration audits and receipt.
- Invalidate existing application caches after confirmed HTTP commits, preserve later ordinary edits and original event identity on recovery, and add OAuth, permission, race, rollback, cache-failure, mobile, packaging and operator acceptance coverage. No new activity, invitation, rescheduling mail, response edit, approval or cancellation is exposed.

## 8.92 — October 27, 2026

- Add default-off `work_arrangements:request` preparation context, signed-in exact preview, pending-only new filing and historical receipt/current notice counts with an owner-only operation-bound source page.
- Reuse canonical filing rules inside a caller-owned transaction, preserving period/reopen deadlines, No AWA and live-filing guards, boundary-week effectivity, advisory coverage and chain/OIC routing. Director auto-approved filings remain on the ordinary screen; no change/replacement or decision is exposed.
- Commit filing, audits, source identity, receipt and initial approval-email queue atomically. Deliver normal `awa_approval` messages with durable single-attempt claims, current authority/recipient checks and explicit uncertainty; preserve ordinary digests and later decision emails. Add security, concurrency, mail, OAuth, mobile, packaging and operator acceptance coverage.

## 8.91 — October 27, 2026

- Add default-off `meals:request` consent with preparation context, browser-confirmed standalone meal submission and owner-only original receipt recovery.
- Reuse the normal meal validation/creation service under a caller-owned transaction so request, lines, audit, source identity and receipt commit atomically; bind current requester, queue membership, policy and exact fields.
- Preserve two-calendar-day notice, Administrative Section queue visibility and Awaiting order semantics; no room, calendar, supplier order, email, delivery or payment. Add strict input, security, rollback, concurrency, OAuth and mobile confirmation coverage and an operator runbook.

## 8.90 — October 27, 2026

- Add default-off rooms:request context/preparation/recovery for one self-owned pending room request linked to a permitted plain one-day calendar meeting. Browser review binds exact meeting revision, continuous configured hours, current requester and initial Administrative Section recipients; Requested holds no booking and changes no calendar schedule.
- Reuse the existing transactional room/link/notice services to atomically create request, unapproved slots, initial notices, original identity mapping and receipt. Recheck visibility/participation, duplicate live links, closures/horizon/availability, slot configuration and routing; recover across refresh/replay/races without repeating creation or later approval.
- Protect mapped MCP initial notices from the legacy retry loop and deliver through a bounded single-attempt worker with committed claims, current recipient/authority/feature checks, explicit uncertainty and normal logging. Preserve ordinary non-MCP and separate summary/reminder behavior. Include runtime packaging, OAuth/MCP/room/mail/mobile checks and the operator runbook; no approval, meals, standby, repeats, calendar edits or financial action. Hosted acceptance remains pending.

## 8.89 — October 27, 2026

- Add default-off own travel paper-submission context/preparation/recovery with separate travel:filing:submit consent excluded from default scopes. Browser review requires the owner to attest an already completed physical handover before changing an existing Ready filing to Submitted; it does not establish office receipt, claim approval or payment.
- Bind current stamp and full filing/paper/flag/review snapshot, and recheck Ready state, complete checklist and current required-review approval under the writer lock. Allow the existing mark_submitted service to join the caller's transaction while preserving normal UI behavior; atomically commit status/timestamps, handover/audit and receipt.
- Return original recorded state/time and traveller follow-up responsibility without document URLs or financial fields. Recover safely across refresh/replay/races, clear completed/expired previews, and add runtime packaging, OAuth/MCP/travel/browser/mobile checks plus the operator runbook. No automatic Ready step, signing, sending, uploads, review decisions, email, stock or payment; hosted acceptance remains pending.

## 8.88 — October 27, 2026

- Add scoped own-review preparation context (fresh update stamp, readiness and paginated eligible account IDs/names), plus default-off own travel review request preparation/recovery with separate travel:review:request consent excluded from default scopes. Browser review binds the full filing/paper/note snapshot, current update stamp, eligible reviewer and selected email recipient before setting review Requested and incrementing the round.
- Allow the existing review domain service to join the caller's writer transaction while preserving ordinary UI behavior. Atomically commit filing/note changes, audits, receipt and one notification keyed to the review round; report original reviewer responsibility and current mail status separately.
- Add scheduler-driven durable single-attempt mail delivery with committed claim markers, current recipient/authority/feature checks, payload integrity, bounded cleanup and explicit queued/uncertain/skipped/unconfigured states. Never automatically retry ambiguous/crashed attempts. Include runtime packaging, OAuth/MCP/browser/mobile/travel/delivery checks and the operator runbook. No paper approval, ready/submitted transition, document generation or payment; hosted acceptance remains pending.

## 8.87 — October 27, 2026

- Add default-off own supply request submission preparation/recovery with separate supplies:request:submit consent excluded from default scopes. Signed-in browser review binds an existing draft/returned request, every purpose/date/item/quantity/catalog field, current requester/unit, approver routing and numbering year.
- Extract a caller-owned transactional submission entry point while preserving the normal Supply operation contract, immutable snapshots, numbering, audit and post-commit warning reconciliation. Atomically save one submitted version, number and canonical/MCP receipts; report actual original submitted state and next-party role/count, including the normal zero-approver warning.
- Recheck catalog, identity, unit, routing, revisions, session and grant; clear completed/expired preview copies and recover across refresh/races/replay without overwriting later return/edit decisions. Add runtime packaging, OAuth/MCP/Supplies/browser/mobile checks and the operator runbook. No approval, reservations, stock issuance, purchases, payments, withdrawals or external relay; hosted acceptance remains pending.

## 8.86 — October 27, 2026

- Add default-off assigned-task submission preparation and recovery with separate work:task:submit consent excluded from default scopes. Browser confirmation binds exact output, review note, task/work-item revisions and lead/unit routing before moving In progress to For review; explain replacement of saved output and normal history visibility/effects.
- Reuse the canonical API submission fingerprint, session/authority checks, task service and immutable receipt through a caller-owned transactional entry point. Atomically commit task/output/history/audit/review/notice effects with API/MCP receipts and historical next-review-party metadata; preserve one UUID v4 key across replay and refresh.
- Recheck current blockers, unfinished prerequisites, changed decisions, routing, ownership, linked access and workflow state. Clear completed/expired preview copies, preserve later UI/API review decisions and add runtime packaging, OAuth/MCP/API/browser/mobile checks and the pilot runbook. No acceptance, approval, completion, owner/deadline changes, uploads, evidence fetching or external relay; hosted acceptance remains pending.

## 8.85 — October 27, 2026

- Add default-off own assigned-task acknowledgement preparation and recovery with separate work:task:acknowledge consent excluded from default scopes. Browser review binds exact IDs, current task/work-item revisions, progress note and normal shared-work history/review/notice effects before moving To do to In progress.
- Extract a caller-owned transactional acknowledgement entry point from the existing API operation service while preserving canonical fingerprints, current session/authority checks, immutable receipts and API behavior. Persist a canonical UUID v4 key and atomically commit task/history/audit effects with both API and MCP receipts; report original status/revision, next actor and source links.
- Reject stale, reassigned, unavailable, revoked, changed and cross-account requests; recover safely across rotation, duplicate confirmations, API replay and later UI/API work. Clear completed/expired preview copies and add runtime packaging, operator acceptance/rollback and OAuth/MCP/API/browser/mobile coverage. No output submission, approval, ownership/deadline changes or external relay; hosted write acceptance remains pending.

## 8.84 — October 27, 2026

- Add default-off travel reimbursement draft preparation and receipt tools with separate travel:filing:draft consent excluded from default scopes. Limit the pilot to own standalone unsubmitted reimbursement checklists with bounded exact activity/DPO/role fields and strict boolean answers.
- Require actor/grant/payload/policy-bound browser review of every answer, normal deadline, Admin Unit visibility and ordinary reminder behavior. Recheck working-day policy and checklist before the existing domain service atomically creates the filing, missing-item checklist, original identity, receipt and content-free audit.
- Add safe recovery through token rotation, duplicate confirmations and later UI changes; clear completed/expired preview and derived checklist copies. No linked activity/calendar, cash advance, liquidation, amounts, generation, review request, submission, approval or payment. Include runtime packaging, OAuth/MCP/mobile/browser checks and the operator runbook; hosted acceptance remains pending.

## 8.83 — October 27, 2026

- Add default-off personal calendar preparation and receipt tools with separate calendar:entry:create consent excluded from default scopes. Constrain creation to one tentative meeting, current owner as sole participant, people-only visibility and bounded exact text/date/time inputs.
- Require actor/grant/payload-bound signed-in browser confirmation and current Calendar eligibility. Reuse the existing transactional creation service and atomically store original entry identity, receipt and content-free integration audit; recover safely across rotation/races/replays without overwriting later UI changes.
- Make the existing Telegram retention test advance from the actual database cancellation timestamp, avoiding fixed-date failures as the real clock advances.
- Add explicit review, source links, runtime packaging, OAuth/MCP/mobile/browser checks and the pilot runbook. No invitations, room booking, Meet links, recurrence, travel, sharing or MCP edit/delete actions. Hosted acceptance remains pending.

## 8.82 — October 27, 2026

- Add default-off personal saved-report-view preparation and receipt tools with separate reports:view:save consent excluded from default scopes. Limit selections to a named Type 1 CSM month or Type 2 activity quarter and generate exact local source links without loading survey results.
- Require actor/grant/payload-bound browser confirmation, current report authority, name uniqueness and capacity rechecks. Atomically save one private selection with its receipt and body-free audit; reject revoked, expired, changed and cross-account requests and recover safely across rotation/races/replays.
- Add owner-only Reports collection/source pages, strict period validation, runtime packaging and OAuth/MCP/browser/mobile coverage. No report content, changes, exports, sharing, overwrites or deletes; hosted acceptance remains pending.

## 8.81 — October 27, 2026

- Add default-off private task comment draft preparation and receipt tools with separate work:comment:draft consent excluded from default scopes; preserve old grants and refresh scope parity.
- Require an exact owner/grant/target/revision-bound preview and signed-in browser confirmation. Atomically save the private draft, receipt and body-free audit; reject stale/revoked/cross-account requests and recover one draft across races/replays.
- Add owner-only source pages, bounded task draft links and exact-task compose prefill without posting, notices or workflow changes. Clear completed/expired preview copies, preserve source access checks, and add OAuth/MCP/browser/mobile coverage plus the pilot runbook. Hosted write acceptance remains pending.
- Include the new private-comment modules in the hosting runtime allowlist and verify transitive import closure.

## 8.80 — October 27, 2026

- Add mcp_actions.py and mcp_supply_drafts.py to the hosting runtime allowlist. They are required imports of the merged v8.78/v8.79 pilots; the deployment import-closure guard otherwise rejects the incomplete package.
- Preserve default-off switches, grants, business behavior and pending hosted acceptance. Verify the actual deployment import-closure tests alongside release metadata.

## 8.79 — October 27, 2026

- Add independent default-off new personal supply draft preparation and receipt tools with optional supplies:request:draft consent excluded from server defaults; preserve old grants and refresh scope parity.
- Require exact requester/catalog/payload previews and signed-in browser confirmation. Share the UI draft service, recheck staff/unit/item authority and revisions, and atomically save the draft, receipt and audit. Do not submit, allocate stock, assign control numbers or notify approvers.
- Preserve one draft across replay/races and later UI edits; clear completed/expired preview text while retaining operation tombstones. Add strict line validation, no-script mobile confirmation, OAuth/MCP/browser recovery tests and the activation/rollback runbook. Hosted write acceptance remains pending.

## 8.78 — October 27, 2026

- Add a default-off MCP pilot to prepare marking one own shared-work notice read, with separate optional notifications:mark_read consent excluded from server default scopes; preserve existing grants and refresh scope parity.
- Require an expiring actor/grant/target/revision-bound preview and explicit signed-in browser confirmation. Share the existing UI service and atomically commit the read marker, durable receipt and audit; reject stale, revoked and cross-user requests and serialize replays.
- Preserve the connection ID during atomic OAuth token rotation so pending previews, receipts and owner revocation links remain bound to the same grant; old tokens remain invalid.
- Add same-key recovery, readiness/consent controls, bounded preparation and mobile no-script confirmation. Record operator-reported read acceptance and the write contract/activation runbook; hosted write acceptance remains pending.

## 8.77 — October 25, 2026

- Add separate default-off private Telegram reminder lead times for confirmed timed calendar occurrences and own approved room bookings, using current channel choices, read consent and Manila quiet hours. Preserve existing email reminders, interactive replies, group update controls and independent digests.
- Atomically record occurrence hashes and durable sender handoffs; recheck current source/schedule/account/grant/bot before rendering and provider I/O. Suppress cancelled/rescheduled/skipped/past-start work, preserve provider retry deadlines, fence source and preference races, and retain minimal deduplication hashes after ordinary delivery retention.
- Add no-script mobile controls, bounded restart-safe scheduler scans, migration/restore coverage and the T4.3.2 Markdown runbook/progress handoff. All pilots remain off; the complete hosted workflow pilot is still T4.4.

## 8.76 — October 25, 2026

- Add current-account calendar/room channel preferences and Asia/Manila quiet hours, including automatic owned-group controls, guarded by session/Origin/CSRF and revision checks. Reuse the existing calendar email choice and add own room-status email control.
- Defer quiet automatic notices without provider attempts, using a separate not-before gate that preserves 429 retry deadlines. Recheck choices at rendering/final send, fence opt-outs and retain source/authority/restore/expiry protections; apply quiet/current email choices to existing change/status email senders.
- Keep interactive replies, confirmation receipts, legacy digests and admin/approval mail under existing controls. Split T4.3 into preference/quiet-hour and durable-reminder children in the Markdown plan; only T4.3.1 is delivered here. Pilots remain default-off; reminder generation and live verification remain later increments.

## 8.75 — October 25, 2026

- Hand current permitted calendar/room change routes to the existing durable Telegram sender, atomically and with stable deduplication. Render private source/own-request updates, explicitly shared calendar fields or anonymous exact-topic room availability only.
- Recheck route/source/read consent, ownership, registration and membership at handoff, proof, rendering and final send. Fence queued/in-flight notices after source/revocation/restore changes; preserve bounded 429 retries and uncertain outcomes without business replay.
- Pause notices after definite provider rejection until a fresh recognized command in the exact conversation or new verified binding; retain normal room approval and existing digest behavior. Add workflow/privacy/failure tests and the Markdown runbook. All pilots remain default-off; quiet hours/reminders/preferences remain T4.3.

## 8.74 — October 25, 2026

- Add get_resource_person_activity_survey(activity_id, resource_person_id) with separate surveys:person_activities:read consent and default-off CSS_MCP_PERSON_ACTIVITY_SURVEYS_ENABLED.
- Match the named person's activity page: quality index 0–100, OSQ 1–4 and five Type 3 dimension means 1–7. Restrict active responses to that person within the current complete date/normalized-venue/organizer group; accept current representative/member form IDs, preserve the source engagement cutoff and never fall back to annual/bureau totals.
- Reuse the current hidden/Director visibility, annual Type 3 score/sample logic and bounded group resolver without changing existing annual or Type 2 contracts. Keep per-group metadata, per-person form, response/answer and query-work limits; withhold every score for insufficient or unusable samples.
- Add explicit activity IDs to existing outside-activity metadata, consent/readiness entries and a source-based verification prompt. No individual responses, comments, contacts, peer rankings, new writes or existing-grant widening.

## 8.73 — October 25, 2026

- Capture metadata-only calendar/room changes in the business transaction across UI, import, scheduler and trusted action writers, including participant/slot/decision changes; retain source incarnation/revision and stable event identities without copying email queues or business content.
- Prepare bounded, restart-safe routing descriptors with current creator/participant/requester and exact shared-group authority. Recheck read grants, source versions, ownership, topic generations and group proof; supersede stale routes and fence revocation/restore.
- Add bounded retention and feature-off local maintenance, source-writer inventory, rollback/privacy/replay tests and Markdown handoff. No notification rendering or provider send; change notices and every other optional pilot remain default-off.

## 8.72 — October 25, 2026

- Add optional exact room hours to guided meeting preparation, with separate current room consent and an unchecked room request choice. Private confirmation saves one meeting and records a separate pending room request or safe failed child outcome.
- Preserve a saved meeting on a definite room-rule refusal; report source links and who acts next, then prepare a fresh room-only child preview against that original meeting. Replay/recovery never recreates either mutation.
- Add parent/child operation references and dependent consent scrubbing; retain normal room approval, private group-origin details, transaction rollback, restore and retention fences. Update the plan/runbook; all defaults remain off.

## 8.71 — October 25, 2026

- Extend existing MCP activity progress output for authorized outside activities with Type 3 classification, the source activity-filtered resource-person report link and explicit management-count semantics.
- Return bounded linked resource-person ID/name metadata only after rechecking the same live grant's surveys:resource_persons:read scope, existing annual-survey pilot flag and current hidden/Director visibility. Filter before a 25-person output limit, deduplicate people, label archived directory entries and refuse oversized per-activity inventories without partial data.
- Preserve activity feed authority, tool names/arguments, scopes and annual scoring. Publish no activity-specific scores, respondent details or contacts; annual-summary links and guidance distinguish annual results from one activity. Update the phone readiness example to use existing tools.
- Verify actual OAuth/MCP calls with activities-only, disabled, dual-scope and revoked grants; cover hidden/Director filtering, owner feed isolation, ID-to-annual-summary handoff, truncation and read-only metadata projections.

## 8.70 — October 25, 2026

- Add native current-selection CSV downloads to the personal Travel claims table, retaining applied filters, deterministic all-page order and the six table columns.
- Recheck current registered-session/account, Travel switch and owner scope on every download; quote Unicode/commas/newlines and neutralize spreadsheet formula prefixes.
- Refuse exports above 10,000 matching filings before producing an attachment, with an accessible return link. Preserve recorded snapshots, no-store, existing native/interactive tables and all business workflows.

## 8.69 — October 25, 2026

- Add optional guided room requests linked to an existing permitted meeting, with separate calendar/room read and rooms.request consent, exact private previews, normal pending approval and durable confirmation/recovery.
- Make plain internal room requests, linking, lazy slot initialization and approver notice inserts usable inside the action transaction while preserving existing UI defaults and courtesy behavior. No automatic approval, meeting creation, guests, meals, standby or series.
- Recheck source authority/revision, dates, slots, conflicts and existing live links; keep group-origin details private, fence grant/source deletion and update the Telegram plan/runbook. All defaults remain off.

## 8.68 — October 25, 2026

- Add an owner-only Travel claims table with literal Unicode reference/activity search, claim-type/status and recorded end-date filters, deterministic all-page sorting and 30-row server pagination.
- Reuse local MIT Tabulator for optional resizable columns and remote paging; retain native filtering, standard pages, safe text, explicit failed-request fallback, no-store and current session checks.
- Read recorded snapshots without deadline refresh or business writes; retain existing filing/checklist, review, approval and payment behavior.

## 8.67 — October 25, 2026

- Add optional guided single-meeting creation: /meeting in a private or registered conversation, signed-in deterministic fields, an exact private preview, and /meeting_confirm with actor/context-bound expiry and durable replay recovery.
- Require new explicit calendar.create consent alongside calendar.read through the existing two-step link flow. Store nonce/hash metadata for durable preview delivery, and commit calendar/audit/email-outbox/private-receipt records atomically. No room submission, group disclosure or automatic video link.
- Preserve admin hard-delete behavior by detaching deleted result references, cancelling stale sends and reporting deletion on recovery. Add workflow, concurrency, privacy and mobile browser checks plus the Markdown handoff. All defaults stay off; live activation remains unverified.

## 8.66 — October 25, 2026

- Add a read-only FullCalendar Schedule view over existing authorized calendar layers, with the current scope and filters, native record links, preferred-view cookie and no-JavaScript weekly list.
- Show a full week on wide screens and a selectable day on phones. Keep configured office times consistent across browser timezones; preserve inclusive all-day endpoints, real overnight times and incomplete durations without inventing clock values.
- Withhold the whole hour grid above 500 filtered items or invalid intervals. Bound busy all-day rows with explicit more counts and popovers; retain the complete native list, print fallback and safe labels. Preserve existing calendar views and item sheets.
- Vendor MIT FullCalendar Standard 6.1.22, Luxon 3.7.2 and its adapter with all bundled licenses/provenance, exact source/bundle verification and transitive npm audits. No new Python package, service, schema, API or calendar write is added.
- Isolate import-time cookie security in the test app fixture so HTTPS integration tests cannot break later HTTP calendar-preference checks. Keep production behavior unchanged and cover both schemes.

## 8.65 — October 25, 2026

- Replace MCP activity discovery's global 2,000-form refusal with quarter-scoped SQLite grouping, literal Unicode casefold title filtering, and database pagination that fetches at most 26 result rows.
- Resolve individual activity/member IDs directly and load only the complete current date/normalized-venue/organizer group. Reuse source grouping and preserve first-Type-2 title, representative IDs, archive/pooled exclusions and answer-backed eligibility.
- Bound metadata queries to 20 million SQLite VM steps or five seconds; retain a 2,000-form per-group cap, 500-Type-2 member cap, response/answer ceilings and existing score suppression. Abort without partial results and remove the progress handler after each query.
- Keep existing tool names, scopes, hosting switch and scoring unchanged. Cover large same-quarter/historical inventories, pagination beyond 2,000 groups, Unicode/literal search, source grouping, member scorecards, work limits and read-only behavior.

## 8.64 — October 25, 2026

- Add a dormant actor/action/destination-bound preview and atomic receipt contract with five-minute confirmations, revision rechecks, replay recovery and bounded expiry/tombstone cleanup. No bot action adapter, command, callback or write-consent issuance is installed.
- Extract shared calendar form parsing and actor-aware transactional creation; preserve UI recurrence, room-request and post-save Meet behavior while saving calendar/audit/email-outbox records together.
- Add preview revocation/restore fences, migration and concurrency/rollback tests, and update the Telegram progress ledger. All two-way defaults remain off.

## 8.63 — October 25, 2026

- Add default-off registered group/topic schedule and room-slot commands with separate current actor read grants, exact routing, and fresh bot/owner/requester membership checks.
- Require audited owner consent to the previewed exact version of each ordinary bureau calendar entry for each destination. Source edits, sharing revocation and restores fence pending sends; re-registration requires new consent.
- Render only approved calendar fields and signed-in source links, or anonymous room-slot states. Retain metadata-only queues, bounded output and independent private commands. Update the Telegram progress ledger and operator handoff.

## 8.62 — October 25, 2026

- Add a signed-in, phone-friendly ChatGPT readiness page linked from Connected tools, with the running build, actual registered MCP catalog, allowlisted pilot switches and only the current owner's grant metadata.
- Separate registration, host activation and consent; show disabled/unavailable catalog states without inferring successful calls or ChatGPT's saved catalog. No tokens, environment dumps, business tool calls, grants or settings writes.
- Provide selectable survey verification prompts and matching source-report guidance; hosted survey acceptance remains pending.

## 8.61 — October 25, 2026

- Add default-off private /room_slots, /my_rooms and /room_status commands under separate current rooms.read consent. Reuse signed-in day_view, requester-qualified reference lookup and bounded own-request lists.
- Match existing working-day, holiday, closure, pending/approved and booking-horizon rules; distinguish pending/standby from actual bookings. Omit titles, decision notes, contact details and other users' request identifiers from room replies.
- Store query metadata only, render current source data at send time, preserve revocation/generation fences, and update private-account instructions plus the Telegram progress/runbook Markdown. No booking actions or group business reads.

## 8.60 — October 25, 2026

- Add local RapidFuzz 3.14.6 typo suggestions for permission-filtered page navigation, help guides and the existing active staff directory. Keep exact record search first and unchanged; label at most five close destinations, retain CSS scope, private basic-status rules and literal numbers/identifiers.
- Bound approximate queries/candidates/text and refuse oversized approximate staff catalogs rather than rank a partial list. No stored index, external inference, new service, business writes or credential setup is introduced; document/attachment/private-record fuzzy search remains outside this pilot.
- Keep exact local navigation available during search-service failure, remove stale empty placeholders and reject delayed responses after query clearing/reuse. Preserve native anchors, keyboard navigation, assistant cards, no-JavaScript page-search fallback and sanitized telemetry.
- Prevent delayed automatic tours from taking focus from active search, preserve explicit replay, and version the changed browser assets. Pin/hash/audit the MIT dependency without upgrading existing packages; exercise native mobile, permissions and delayed-network flows.

## 8.59 — October 25, 2026

- Add default-off private Telegram calendar lookup using the same viewer context, visibility predicates, scopes and entries/holidays/room-calendar providers as the signed-in calendar. Require current separate calendar.read consent and capability switch.
- Bound date windows to 31 days, visible results to 2,000, pages to at most ten items and replies to Telegram UTF-16 limits; use ten-minute actor/connection/bot-bound signed paging tokens with visible-state change detection.
- Store query metadata only and render current permitted fields at send time, excluding notes, meeting URLs, attendees and other private layers. Recheck revocation at the final provider-call boundary, preserve signed-in source links and update the plan and private-account instructions. No writes, slot lookup or group business reads.

## 8.58 — October 25, 2026

- Add default-off exact Telegram group/topic registration from an observed command, signed-in administrator ownership/purpose/audience consent and fresh Bot API administrator verification for the binder and bot. No delegated owner assignment or business group reads.
- Route only a fixed neutral group-status reply for currently linked staff, with exact registration/topic/generation checks and fresh provider membership checks. Bound provider work, preserve topic IDs and reject private or business projections.
- Fence queued and in-flight group work on removal, migration, topic changes, disconnect, account changes and restore; require explicit fresh verification before resuming. Record bot provenance on new private connections; older links need fresh consent before group use. Update the Telegram ledger and pilot runbook.

## 8.57 — October 25, 2026

- Add default-off two-step private Telegram account linking, signed-in connection status and disconnect, plus explicit optional calendar/room read consent. Raw codes never enter URLs, receipts or stored delivery bodies; private confirmation rechecks the browser session and original Telegram sender.
- Add durable challenge/grant storage, current account/bot/generation grant checks, account-change revocation, pending-work cancellation and restore invalidation. Disconnect remains available when linking or delivery is paused. No business reads/writes or group capabilities are enabled.
- Verify native, script-disabled mobile linking/confirmation/disconnect and update the Telegram plan and operator handoff.

## 8.56 — October 25, 2026

- Add default-off authenticated Telegram webhook intake with bounded input, durable update deduplication and rolling global/per-sender rate limits. Accept neutral private /start and /help only; acknowledge unsupported updates as ignored without retaining content.
- Add bounded SQLite-backed processing and private Bot API delivery to the existing scheduler, with committed sending markers, claim fencing, five-attempt limits for definite throttling, destination pacing, expiry, conservative uncertainty and bounded retention. No linking, groups or business actions.
- Add exact callback authentication/Origin exceptions and runtime upload closure; retain independent Apprise digest settings. Update the Telegram progress ledger and activation/recovery runbook.

## 8.55 — October 25, 2026

- Add inert two-way Telegram connection, update, operation and delivery tables with uniqueness, foreign keys and bounded states. Add independent default-off capability switches without a receiver, sender or business action.
- Fence every snapshot recovery with fresh connection generations; cancel pending actions/updates/sends, clear input payloads and claims, preserve committed receipts, and mark interrupted sending uncertain. Preserve existing Apprise digest configuration.

## 8.54 — October 25, 2026

- Define the Telegram T0 authority, storage and recovery contract. Two-way integration remains unimplemented and inactive.

## 8.53 — October 25, 2026

- Add permitted resource-person name/ID discovery and one-person consecutive-year Type 3 comparisons under separate surveys:resource_person_trends:read consent and default-off CSS_MCP_RESOURCE_PERSON_TRENDS_ENABLED.
- Reuse current hidden/Director visibility and person-dashboard quality-index, OSQ and dimension calculations. Resolve one person's minimal metadata directly instead of loading the full directory for annual summaries.
- Filter visibility before discovery pagination, bound the inventory and name output, and withhold both scorecards and changes if either year fails existing sample/capacity checks. Exclude contacts, respondent answers, comments, peer rankings and causal claims.

## 8.52 — October 25, 2026

- Add compare_csm_months for a selected bureau-wide Type 1 submission month versus the immediately preceding month, under separate surveys:csm_trends:read consent and default-off CSS_MCP_CSM_TRENDS_ENABLED.
- Preserve the official pooled SQD1–SQD8 overall, individual SQD percentages, source links and existing small-sample rules. Publish changes in percentage points from displayed report percentages, not percent growth.
- Refuse more than 5,000 responses or 100,000 SQD-answer rows per month; withhold both scorecards and all changes if either month is empty, unrated, small or over capacity. No individual responses, comments, service/demographic filters or causal claims.

## 8.51 — October 24, 2026

- Add an explicit administrator control for Collaborative work on Documents setup, requiring Documents first, current all-unit permissions authority for enabling, confirmation/reason, shared settings revision and atomic audit. System administrators retain emergency pause; deployment does not enable modules or change document sending.
- Replace generic Telegram unavailability with credential-free diagnostics for each disabled module, host switch, public URL and account target configuration, including setup-code mismatch and malformed token/chat ID. Link administrators to module setup; retain provider validation and delivery semantics.
- Verify permission/revocation/rollback/stale-form gates and the complete phone-sized, script-disabled Documents → Collaborative work → Telegram-ready journey without external sends. Document prerequisites before hosting setup.
- Pin the independent MCP probe's business date to its synthetic fixtures so real Philippine midnight cannot expire its pending room requests; preserve real OAuth expiry timing and the original assertions.

## 8.50 — October 24, 2026

- Add compare_unit_activity_surveys for a selected unit's quarter versus its immediately preceding quarter, under new surveys:unit_trends:read consent and default-off CSS_MCP_UNIT_TRENDS_ENABLED.
- Reuse current report unit attribution, five-dimension calculations, per-period capacity limits and small-cell suppression. Withhold both scorecards and all changes when either period is unavailable, empty, unrated or too small.
- Return original-scale-point deltas and report links, without rankings or claims of causation/statistical significance. Unit discovery keeps its separate existing scope; no existing grant expands.

## 8.49 — October 24, 2026

- Add bounded unit discovery and quarterly Type 2 unit summaries under separate surveys:units:read consent and default-off CSS_MCP_UNIT_SURVEYS_ENABLED.
- Match report selection by current form lead-unit path, including descendants with exact slash boundaries. Reuse the consolidated five-dimension scoring and existing capacity/small-sample refusals; exclude personal answers, text and speaker scores.
- Existing bureau/activity grants do not gain unit access. Live acceptance and period comparisons remain pending.

## 8.48 — October 24, 2026

- Add bounded title/quarter discovery and individual merged-activity Type 2 scorecards under new surveys:activity_details:read consent and default-off CSS_MCP_ACTIVITY_DETAILS_ENABLED.
- Share the source report's date/venue/organizer grouping; resolve representative or active member IDs without fallback to bureau totals. Exclude archived/pooled forms, speaker scores, comments, rosters and individual responses.
- Preserve the full five-dimension detail scorecard, small-sample suppression and capacity refusals. Discovery returns metadata only, paginated at 25 records, and distinguishes empty/disabled states.

## 8.47 — October 24, 2026

- Add an opt-in Apprise 2.0.1 private Telegram discussion-digest pilot with host-secret credentials, per-account opaque setup codes, independent cadence/history and disconnect controls.
- Keep default delivery off and send only a generic HTTPS sign-in reminder; recheck current account, source access, unread state, preferences and configuration before transport.
- Commit durable per-notice/per-day/week claims before I/O, bound scheduler ticks, avoid uncertain/crash retries, and revoke bindings on deliberate restore or account deletion. Preserve existing email/bell flows.
- Pin/audit the new dependency graph and exercise the actual provider with mocked HTTP plus native browser setup/disconnect flows; live activation requires hosting credentials and user opt-in.

## 8.46 — October 24, 2026

- Add one-person annual Type 3 resource-person survey summaries under separate surveys:resource_persons:read consent and default-off CSS_MCP_RESOURCE_PERSON_SURVEYS_ENABLED.
- Share the current person-profile hidden/Director visibility predicate with the named report routes; check it before returning any identity metadata.
- Reuse the person dashboard's normalized quality index and Type 3 dimension map; exclude respondents, comments, contacts, rankings and other survey types. Preserve small-sample and capacity refusal rules without partial scores.

## 8.45 — October 24, 2026

- Add bureau-wide quarterly Type 2 satisfaction summaries under separate surveys:activities:read consent and a default-off CSS_MCP_ACTIVITY_SURVEYS_ENABLED switch.
- Share the report's SERVQUAL block/metric formatting without loading respondent context; preserve 1–7 A/B scores, 1–4 C scores, sparse dimension arithmetic and activity-start-date selection.
- Distinguish receipt totals, historical answer-backed report submissions and rated respondents. Withhold all scores for small populated item cells and refuse over-cap results without partial scores.

## 8.44 — October 24, 2026

- Start M1.2 with fixed-month, bureau-wide Type 1 CSM aggregates under surveys:csm:read and a default-off CSS_MCP_CSM_ENABLED switch.
- Extract shared date predicates and SQD scoring from the existing report so screen/export and MCP calculations remain aligned; MCP reads no comments, demographic remarks or respondent identities.
- Distinguish empty, unrated, small-sample and capacity-limited results. Withhold all score fields if any populated SQD item has fewer than ten responses; cap monthly retrieval at 5,000 responses without truncating scores.

## 8.43 — October 24, 2026

- Fix the flaky outside-activity QR test by inspecting actual anchor destinations instead of searching encoded image data, with a deterministic embedded-image regression case.
- Add direct PDF exports to the Documents workload and Supplies stock dashboards, using fresh authorized snapshots, vector charts, complete repeated-header tables, applied filters and snapshot dates.
- Reuse existing ReportLab and DejaVu fonts instead of adding a Gotenberg conversion service; retain existing 1,000-group/item export bounds, exact quantities, deadline rules, access checks and no-store headers, without new dependencies, schema changes or business writes.

## 8.42 — October 24, 2026

- Implement M1.1 metadata-only own unread shared-work notifications with a separate notifications:read scope, bounded cursor pagination, source links and as-of timestamp; do not mark messages seen or expose titles, authors, bodies, wellness or approval queues.
- Add single-day, paginated conference-room availability under calendar:read, reusing signed-in picker rules without booking details or block reasons. Pending requests hold nothing; no reservation is made.
- Keep both new tools behind independent default-off environment switches and report not_available separately from successful empty data. Existing grants remain unchanged.

## 8.41 — October 24, 2026

- Export the Documents workload dashboard to PowerPoint with editable workflow, deadline and assigned-lead charts plus complete aggregate count tables, applied queue/search and date boundaries.
- Recheck current record access in one fresh snapshot per export, retaining working-day/invalid-date rules and authorized lead labels; chart the largest 20 lead groups with explicit scope and full tables.
- Refuse more than 1,000 lead groups instead of truncating; retain dashboard tables on asset/request failure and reuse the existing PptxGenJS/JSZip distributions and gates without new dependencies, schema changes or document writes.

## 8.40 — October 24, 2026

- Correct the work-only client registration ceiling that prevented v8.38 from displaying optional scopes for newly recreated ChatGPT apps.
- Advertise the six supported read scopes for new and legacy registrations while preserving explicit authorize requests, unchecked optional consent and existing grant/refresh scope limits.
- Remove the ineffective recreate-app loop; reject unsupported/write scopes and cover legacy calendar opt-in through OAuth.

## 8.39 — October 24, 2026

- Add a Supplies stock dashboard PowerPoint export using locally vendored PptxGenJS 4.0.1 and JSZip 3.10.1 with hashes, licenses and npm advisory checks for embedded browser dependencies.
- Generate editable native charts and below-critical tables from a fresh authorized snapshot, preserving applied search/unit/catalog filters, exact quantities and unset targets across all matching list pages.
- Bound exports to 1,000 below-critical items with an explicit narrow-filters error rather than truncating results; keep dashboard tables available if export assets or requests fail.

## 8.38 — October 24, 2026

- Add unchecked optional read scopes to MCP OAuth consent when a client requests only a subset of its registered permissions.
- Recheck selected scopes against the current registration inside the approval transaction; preserve existing grants and token/refresh scope parity.
- Explain how to recreate a legacy ChatGPT app registration when a needed permission is absent; refreshing tools alone cannot expand a grant.
- Verify narrow consent, calendar opt-in and forged-scope denial through the synthetic OAuth/MCP journey; hosted acceptance remains pending.

## 8.36 — October 24, 2026

- Add a phased plan for further read-only and carefully confirmed write features in the Office Connect ChatGPT connection.
- Exclude delete, cancel, withdraw, void, reverse, archive and equivalent record actions from every MCP phase.
- Keep all proposed tools disabled; this release publishes the plan without granting new access or changing business records.

## 8.35 — October 24, 2026

- Let ChatGPT list visible calendar events, activities and room bookings, with dates, status, venue and links back to Office Connect.
- Require a separate calendar read permission and check current calendar visibility on every request; approved room bookings are visible to all signed-in users, while pending requests remain restricted to the requester and room approvers.
- Limit each calendar request to 31 days and 25 returned items; exclude attendee names, meeting links, leave and birthdays. Existing ChatGPT connections must reconnect to approve the new permission.
- Add separately authorized supply request and stock-warning, personal travel filing, and manager-scoped activity progress reads; exclude purposes, claim amounts, files and individual responses.
- Add a combined overview that reads only granted modules and marks ungranted modules clearly rather than reporting empty results.

## 8.34 — October 24, 2026

- Add an ECharts Supplies stock dashboard with full-scope physical-stock and availability counts, using existing ledger/reservation rules and current catalog permissions.
- List recorded active items strictly below their critical level with exact current/target quantities, stable 30-item pagination and item links. Never sum quantities across unlike units.
- Open exact interactive inventory/CSV filters from bars or accessible count links; preserve server-filtered fallback tables, pagination, retry/reset and recovered page state when scripts/assets fail.
- Reuse the existing vendored ECharts dependency and gates without a new dependency, schema migration, stock write or notice projection. Preserve MCP consent recovery v8.33.

## 8.33 — October 24, 2026

- Show a readable error and retry path when ChatGPT connection approval fails, instead of letting the browser download the response.
- Support approval requests from browsers that send a same-site referrer; keep cross-site requests blocked.
- Advertise both read permissions and request work and document metadata by default for new ChatGPT connections.

## 8.32 — October 24, 2026

- Add a document workload dashboard with locally vendored Apache ECharts 6.1.0 and accessible linked count tables for workflow stages, deadline groups and assigned leads.
- Aggregate the authorized registry queue/search in one snapshot, using its existing working-day deadline classifier. Show every lead in the table and the largest 20 in the chart; counts describe documents, not contributions or performance.
- Open matching Tabulator/CSV views from chart bars or table links. Preserve filtered, paginated server tables when scripts or vendors are unavailable; retries retain linked filters and Reset clears them.
- Add Later deadlines and Closed or cancelled deadline filters for exact drill-downs. Retain schema-1 saved-view compatibility, with no schema migration or record mutation.
- Verify upstream archive integrity and vendor file hashes, retain upstream/third-party licenses, and audit ECharts plus bundled zrender 6.1.0 and tslib 2.3.0 through the release dependency gate.

## 8.31 — October 24, 2026

- Add an optional ChatGPT connection for a user's visible shared work and document status, with direct links back to Office Connect.
- Require personal sign-in, password confirmation and limited read permission; allow the user to disconnect from Connected tools.
- Exclude changes to records, attached files, document bodies and private task submissions. The connection is off until enabled for a hosted release.

## 8.30 — October 24, 2026

- Add an optional, read-only Tabulator inventory to Supply catalog with server-side search, unit/physical-stock/availability/active filters, sorting and 30-item pagination.
- Reuse the established stock classifier and reservation totals; preserve unknown quantities, threshold equality and exact 64-bit totals. Inactive items remain restricted to current custodians/auditors.
- Add private account-owned inventory views with CSRF and revision checks, plus formula-safe current-view CSV exports of all matching pages/visible columns, limited to 10,000 items without truncation.
- Keep the standard catalog and item workflows available, including failure fallback. Add only an inventory-preference table, with no stock mutation, category field or new dependency.

## 8.29 — October 24, 2026

- Add a reproducible synthetic A25 capacity and recovery rehearsal with aggregate evidence and a provisional SQLite decision; no production data or live performance claim.
- Batch Type-1 walk-in export answer/remark lookups so office-sized extracts no longer exceed SQLite's variable limit; cover the boundary above 1,000 responses.
- Document large-report time and memory risk, plus the hosted measurement and recovery gate still required.

## 8.28 — October 24, 2026

- Group the interactive document register by workflow or assigned lead before pagination, with full-result counts and explicit counts for each page fragment.
- Keep grouping in private saved views and current-view CSV downloads; grouped exports add a formula-safe group column even when the corresponding display column is hidden.
- Recheck access and all filters for group counts, rows and exports within the same request snapshot. Older saved views default to no grouping; no schema migration or new dependency.

## 8.27 — October 24, 2026

- Add a seven-day provider summary to the admin AI page using existing interaction metadata across the full window, separate from the 200-row log browser.
- Show served, rejected and other fallback counts, voluntary feedback counts, recorded mean latency and reported input/output tokens with sample counts.
- Exclude prompts, replies and user details from the summary, and label partial latency/token coverage and feedback bias. No schema migration, provider change or new dependency.

## 8.26 — October 24, 2026

- Show a collapsible source list beneath verified survey answers, including stable source IDs, as-of dates and valid-rating counts when relevant.
- Explain that AI selects topics while the system calculates the figures; keep ordinary personal answers free of survey-source details.
- Escape source labels as text in the browser and cover the display with a Chromium regression. No schema migration, provider change or new dependency.

## 8.25 — October 24, 2026

- Filter the interactive document register by assigned lead or Unresolved and inclusive, optional Due from / Due through dates before counting and pagination.
- Share the same filters with current-view CSV exports and private saved views; older schema-1 views default to unrestricted lead/date settings without a migration.
- Offer leads from the authorized queue/search, including historical inactive leads. A saved lead with no current matches remains selected without broadening the filter. Invalid/missing due dates are excluded when date bounds are applied.

## 8.24 — October 24, 2026

- Continue A22 with 24 offline Groq routing and exclusion cases, bringing the evaluation suite to 447 named scenarios.
- Check admin opt-in, Gemini preference, quota fallback, Groq-only mode, current session, provider failures and existing AI switches through the assistant route.
- Keep Groq and Gemini request settings and per-provider logs inside the versioned release gate; no live provider calls, schema migration or new configuration.

## 8.23 — October 23, 2026

- Continue A22 with 34 offline landing-assistant help and navigation cases, bringing the evaluation suite to 423 named scenarios.
- Recheck the registered session, access flags, AI switches and offered page/guide catalogs after provider work, before returning a suggestion.
- Reject malformed or unavailable keys and unsafe reason text; keep the normal search as the fallback when AI cannot supply a current suggestion.
- No schema migration or new provider configuration.

## 8.22 — October 23, 2026

- Increase release test jobs from 30 to 45 minutes so OCR/browser setup, both full suite orders and report gates can finish.
- Add Export current view (CSV) with the applied queue/search, workflow, verification and deadline filters, current sort order and visible columns across all matching pages.
- Recheck current access server-side, neutralize spreadsheet formulas, preserve UTF-8 text, and reject exports above 10,000 matches without truncating them. The existing full-register export remains available separately.
- Update pypdf from 6.21.1 to 6.21.2 to resolve three PDF parsing advisories reported by the release audit; regenerate runtime and test hash locks.

## 8.21 — October 23, 2026

- Continue A22 with 23 offline calendar invitation upload cases, bringing the evaluation suite to 389 named scenarios.
- Recheck the registered account, activity visibility and unchanged outside-office details after provider and relay work, before saving the uploaded link. Request removal of the uploaded file if that check fails.
- Reject malformed or unsafe invitation readings. Keep valid uploads when only AI fails, and keep suggestions behind the person's explicit review and save.
- Keep document-reading AI logs to outcome and timing metadata. No schema migration or new provider configuration.

## 8.20 — October 23, 2026

- Filter the interactive document register by overdue, due today, due soon or unknown deadline before pagination and counting.
- Use the same deadline classification as labels; due soon includes today through three working days, excluding configured holidays, and urgency filters exclude closed/cancelled records.
- Save and restore deadline filters in personal views; older views default to all deadlines without a database migration.

## 8.19 — October 23, 2026

- Continue A22 with 27 offline travel checklist upload cases, bringing the evaluation suite to 366 named scenarios.
- Recheck the registered account and unchanged filing after provider and relay work, before saving the confirmed upload. Request removal of the uploaded file if that check fails.
- Reject malformed DPO and appearance readings, keep the file when only AI fails, and require the person to choose and save a suggested DPO date.
- Continue metadata-only AI logs for document readings. No schema migration or new provider configuration.

## 8.18 — October 23, 2026

- Save up to ten personal document views with queue, search, applied filters, sorting, visible columns and widths; reopen a view on any device.
- Create, rename, update or delete your views without changing document records; opening a view checks current access and starts at page one.
- Both document tables label overdue, due-today, due-soon and unknown deadlines using the register's three-working-day window and configured holidays; closed and cancelled records have no deadline alert.

## 8.17 — October 23, 2026

- Continue A22 with 19 offline direct travel scan cases, bringing the versioned evaluation suite to 339 scenarios.
- Recheck the registered session, AI switch, travel switch, filing owner and unchanged filing after the document provider returns.
- Reject malformed amounts, dates, currencies and unsafe text before returning a suggestion. Keep travel scan logs to outcome and timing metadata.
- Keep the uploaded image out of application storage. This release covers the direct receipt scan; checklist uploads and invitation reading remain separate paths.

## 8.16 — October 23, 2026

- Add an opt-in Tabulator document-register view with server-side sorting, workflow and verification filters, resizable columns, a column chooser and 30-row pagination across the authorized result set.
- Reuse the registry selection and page-only FTS snippets, keep the standard table as a fallback, and retain full-register CSV and measure semantics. The read-only JSON endpoint returns display fields with no-store headers.
- Vendor unmodified Tabulator 6.7.1 assets and MIT license with verified npm archive integrity and SHA-256 hashes; extend CI integrity/advisory checks to cover the added library.
- Add permission/search parity, bounded retrieval and browser checks for filters, pagination, safe text rendering, column choices, mobile controls and loading failures.

## 8.15 — October 23, 2026

- Continue A22 with evaluation suite 1.7.0: add 31 offline landing-assistant action cases to the existing 289, for 320 named cases required in both CI orders.
- Recheck the current registered session, role, AI switches and archive candidate list after provider I/O. Reject stale or changed actions before a confirmation card appears.
- Require action-specific typed fields, reject unexpected fields and oversized names, and retain explicit staff confirmation before any existing action endpoint is called.
- Add a Chromium check that the action description is escaped, Cancel does nothing and Confirm alone submits the real form. No schema migration, new dependency or provider configuration. Offline tests do not measure real-model intent recognition.

## 8.14 — October 23, 2026

- Continue A22 with evaluation suite 1.6.0: add 32 offline directory duplicate-suggestion cases to the existing 257, for 289 named cases required in both CI orders.
- Recheck the current administrator session, AI settings and both directory records after provider I/O. Reject malformed, unsafe and stale suggestions; audit validated hints without storing names, and leave merging to staff.
- Keep directory interaction logs to outcome/token/timing metadata without prompts, replies or raw provider errors. Use the existing opt-in for sending names to Gemini, with an eight-second provider read timeout and bounded output.
- Label hints for review and escape model text in the browser. No schema migration, new dependency or provider configuration. Offline tests do not measure real-model duplicate recognition.

## 8.13 — October 23, 2026

- Continue A22 with evaluation suite 1.5.0: add 30 offline UX Insights analysis cases to the existing 227, for 257 named cases required in both CI orders.
- Recheck the current admin session, AI settings and telemetry/feedback snapshot after provider I/O. Reject empty, oversized, unsafe or unsupported numeric output. Commit the success outcome with its audit only after validation.
- Mask email and mobile contact details in the provider handoff, retain only outcome/token/timing metadata in UX analysis interaction logs, and use an eight-second provider read timeout with bounded output.
- Show the analysis window, event count and partial-sample warning beside suggestions; keep model text escaped in the browser. This is a review aid, not a verified causal finding.
- No schema migration, new dependency or production provider configuration. Offline provider fakes do not measure live-model quality or production latency.

## 8.12 — October 23, 2026

- Continue A22 with a versioned offline evaluation set for AI drafted activity messages, including unsupported numeric claims, private information, malformed replies, access changes and provider failures.
- Validate bounded plain-text drafts, an exact name placeholder and source-supported numbers before returning a suggestion. Recheck current access, AI settings and activity details after provider I/O; keep message logs to outcome/token/timing metadata.
- Show the complete AI draft for explicit review before replacing the organizer's text. Edits made while AI is working remain in place. A draft is not saved or sent until the organizer applies it.
- No schema migration, new provider or dependency. Synthetic checks do not establish real-model writing quality.

## 8.11 — October 23, 2026

- Replace companion voice blips with 27 locally hosted recordings and natural effects: animal calls, cat purring, quiet movement and water effects, and a separate sound identity for every plant.
- Play the companion signature when tapped; use quieter, infrequent idle calls and a shared mixer to prevent overlapping voices.
- Show sound controls beside the interactive avatar on Home and Wellness, with a remembered volume setting; keep sound off by default and cancel playback and pending audio when muted or hidden.
- Include source credits, individual audio licenses, pinned source checksums and a rebuild script. The two rabbit excerpts retain CC BY-SA 4.0; the remaining recordings and foley use CC0.
- Load only requested clips after opting into sound. Existing static asset delivery and service-worker caching cover the pack; update script and service-worker versions.

## 8.10 — October 23, 2026

- Continue A22 with evaluation suite 1.3.0: retain 146 answer, report-draft and feedback-triage scenarios and add 49 versioned offline cases for activity-comment re-analysis and AI summary. Use synthetic comments, provider HTTP fakes, current route/auth/storage paths and minimized CI evidence in both orders.
- Read current activity comments without the dashboard cache. Validate every classification index and sentiment, every batch, current account/session/settings and unchanged comments/human tags before atomically saving AI tags and audit. A failed later batch, changed source or failed audit leaves all tags unchanged; prior human corrections remain authoritative.
- Bound partially masked comment snippets and summary output; omit the activity name from the summary prompt. Keep verbatim interaction logs to outcome/token/timing metadata without prompts, replies or raw provider error bodies, including when general content logging is enabled. This masking is not universal anonymization.
- Validate summary shape and length, recheck access and source after provider I/O, and escape model-authored text in the browser. A summary is shown for human review and is not saved to an official report.
- Use eight-second provider read timeouts with existing retry, rate and budget settings. No database migration, new provider configuration or dependency is required. These deterministic tests do not measure live-model classification or summary quality.

## 8.09 — October 23, 2026

- DPO: start the signature block ("By Authority of the Secretary of Health:" and the signatory's name, title and office) at the 2-inch mark on its first line too (Spot Feedback #182). The paragraphs set only the start indent, so single lines began at the left margin.
- DPO: when the invitation's key lines (or "DPO cites") already name the office holding the activity, skip the generated "In support of this, [office] will conduct…" sentence (it repeated the same fact).
- Google side: re-run `rebuildActivityTemplates()` and redeploy `activity_templates.gs`. No schema migration or new dependency.

## 8.08 — October 23, 2026

- Open wellness check-in only after the scheduled approved break ends in local time, including two-hour breaks.
- Hide early check-in links and home reminders; reject early direct visits and submissions.
- Cover the time boundary in tests. No schema migration or new dependency.

## 8.07 — October 23, 2026

- Extend A22 evaluation suite 1.2.0 to 146 scenarios: retain 38 answer and 60 report-draft cases; add 48 feedback-triage cases using synthetic records and fake provider HTTP. Require every case in both full CI orders and bind reports to the new triage code and form.
- Limit the provider request to the current feedback text and 30 open candidates with bounded, partially masked snippets. Omit submitter identity, admin notes, page metadata and history; keep triage logs to outcome/token/timing metadata even when general content logging is enabled.
- Reject unsupported status/severity values, extra fields, malformed reasons, and duplicate IDs outside the offered candidates. Recheck the admin session, AI settings, feedback and candidates after the provider call before returning a suggestion. Provider failure or stale data leaves the manual form available.
- Keep suggestions as explicit form prefills: preserve human edits made while AI is working, clear a stale duplicate field when no match is suggested, escape the reason in the browser and require Save for any business change. Verify these behaviors in Chromium without external network or real provider use.
- No database migration, new dependency or production AI configuration is required. These tests measure deterministic application safeguards, not a real model's judgment or production latency. Keep the release version at two digits after the decimal.

## 8.06 — October 23, 2026

- Add administrator-only Appearance controls for independent page themes and avatar outfits, private desktop/mobile previews, drafts, publishing, manual overrides, fallback settings and seasonal schedules.
- Add a complete Halloween scene with an illustrated haunted-office banner, moon, bats, ghosts, pumpkins, seasonal navigation and cards, companion props, and witch, vampire and pumpkin costumes across all species and growth stages. Retain Default and Christmas presets.
- Make scenery, ambient animation and the banner message configurable; preserve personal light/dark and contrast settings, reduced motion and print behavior. Refresh styling and costume layers on open pages without discarding forms or companion state.
- Store configuration, revision-checked history and hash-chained audit entries atomically. Reject overlapping published schedules and ambiguous local times, resolve expiry without a cron worker, and keep old settings/history compatible.
- Include all appearance modules in the deployment runtime and advance the application and service-worker cache to 8.06. Add backend and Chromium coverage for access, previews, schedules, restoration, live changes, accessibility and mobile layout.

## 8.05 — October 23, 2026

- Fix calendar birthday items opening a "Not Found" page: they now open that month's celebrants list (Spot Feedback #175); month and week views no longer render a missing link as `None`.
- Show a Region column on an activity's Monitor roster when its registration form has a Region question (#176).
- DPO: cite "BLHSD - Local Health Systems Development Assistance" as the funding source (#179); always name the venue in the subject and body, blank when the item has none (#178); type each named person's designation on the draft form (#178); title flush left with no space before its number (#180); several travellers go in a Name | Designation table sized to its text, Times New Roman 12, single spacing (#181); signature block at the 2-inch mark (#182) with no space between its lines (#183).
- New "Minutes of the meeting" document, suggested for meetings (#177).
- Google side: re-run `rebuildActivityTemplates()` and redeploy `travel_docs.gs` / `activity_templates.gs` for the layout changes and the minutes template. No schema migration or new dependency.
## 8.04 — October 23, 2026

- Continue A22 with evaluation suite 1.1.0: retain the 38 answer-route scenarios and add 60 report-draft scenarios for MRR and official CO-CSM reports, with literal independently reviewed source figures and simulated provider HTTP.
- Close the unchecked-prose path into official drafts: report draft contract v1 accepts only a version and concise/detailed style; the server renders aggregate figures, missing-data statements and clearly proposed follow-up wording. Reject extra prose, invented figures/actions, missing selections, wrong types and forged contract versions. Human editing and existing export fallbacks remain available.
- Send only aggregate evidence, fixed dimension labels and validated period/date values to the provider. Omit activity/service/person names, venues, comments and comment themes; report-draft logs retain outcome/token/timing metadata without prompts, replies or raw provider error bodies, including when general content logging is enabled.
- Read current scoped sources without dashboard caches; recheck account/session/role, AI switches, source content/group membership, reference day and existing saved edits after the provider call. Preserve existing drafts after failures or concurrent human edits. Save all generated fields, the success outcome and their audit in one transaction; rejected or stale replies retain a rejection outcome.
- Bound draft generation to 96 output tokens and eight-second read timeouts; existing budget/rate gates, retry and provider settings remain. No real-provider call, new dependency, schema migration or automatic report publication is introduced. Previously saved drafts are not rewritten or certified; later source changes still require human review or regeneration.
- Require all 98 evaluation scenarios in both existing CI orders. Bind reports to the extended source fingerprint and increased suite version; document arithmetic, provider contract, reduced free-form drafting and rollout limits. Keep the application version at exactly two digits after the decimal.

## 8.03 — October 23, 2026

- Allow same-day requests and staff-encoded bookings for available conference room hours; retain approval, conflict, closure and booking horizon checks.
- Require two calendar days of notice for meals, including meals added to an existing room booking, guest forms, activity/calendar prechecks, moves and repeating requests.
- Add standalone meal requests for any activity and venue, with their own references, pax, dietary needs, delivery times and per-meal ordering/delivery status.
- Add Office → Request meals and My meal requests, an Administrative Section management queue, owner withdrawal and audit records; retain access to existing room-linked forms.
- Create standalone meal tables idempotently without changing existing room records or adding dependencies.
- Validate room/meal rules, complete request-to-delivery flow, owner isolation, administrative permissions, guest forms and storage reinitialization.

## 8.02 — October 23, 2026

- Fix ARTA walk-in reports, official exports and the comments view omitting every response on the standing walk-in form after it was marked archived (24 entries, April 10 to October 22, 2026).
- Keep the standing walk-in form out of every form-level archive path (single, inline and bulk); individual entries can still be archived or restored from Walk-in entries.
- Tests cover report counts with an archived standing form and refusal to archive it.
- No schema migration or new dependency.

## 8.01 — October 22, 2026

- Start A22 with evaluation suite 1.0.0: 38 named questions/scenarios and an independent synthetic reference dataset covering server-owned figures/evidence, missing/stale sources, current account/session/calendar authority, injected instructions and provider failures/budgets.
- Exercise the real HTTP route, registered users, database and provider adapter; intercept only provider HTTP and reject attempted network I/O. Expected values/source labels are reviewed literals, not values generated by the renderer or provider. No real-provider call or new dependency is added.
- Produce minimized JSON and Markdown evidence by category/case, bound to the case/reference hashes, selected source files, application version and checked-out Git commit. Reject missing/duplicate/failed/skipped/xfail cases, fixture errors, unsuccessful sessions, unrecognized evidence fields and stale provenance; partial runs cannot reuse a previous passing artifact.
- Require the evaluation report in both normal and shuffled release CI, alongside the existing full-suite/dependency gates. Case/reference edits require a suite-version increase; evidence remains in the existing 14-day CI artifacts.
- Document reproducible runs, reference arithmetic, coverage boundaries, privacy and remaining A22 work. This measures deterministic application safeguards with simulated providers; it does not measure real-model answer relevance, production latency, provider cost or all AI features. Release format remains two digits after the decimal.

## 8.00 — October 22, 2026

- Restore exactly two digits after the decimal for new application releases: 8.00, 8.01 … 8.99, 9.00. Enforce that format in the release gate while retaining recorded historical versions and allowing comparison against the existing 7.100 release.

- Continue A21 with an independent standard-library change-feed to HTTPS webhook adapter. It runs on the integration owner's runner, uses an existing delegated read credential and adds no application-host worker, upstream writes or new dependencies.
- Commit validated minimal notices and progress together in a private local SQLite store; retain stable delivery IDs, attempt history, bounded retries, lease recovery, delivery status and explicit replay of failed/blocked deliveries. Honor bounded Retry-After and refuse redirects.
- Re-read current source authority and resource identity/revision before each send, including retries and replay. Revoked credentials stop the invocation; unavailable, obsolete or no-longer-readable records are blocked without forwarding cached notices.
- Sign versioned canonical JSON with timestamped HMAC-SHA256. Publish receiver verification with bounded freshness, constant-time comparison and an atomic local effect/receipt example that deduplicates lost-response retries. HTTP acceptance does not prove downstream business completion.
- Require fixed HTTPS destinations (explicit loopback-only HTTP test option), private credential/config/state files and separate state after source/identity/family/receiver/key changes. Preserve runner proxy/CA policy and exclude source credentials, private prose and receiver response bodies from deliveries/history.
- Document ownership, checkpoint recovery, retention, replay and key rotation. Tests use synthetic local sources/receivers; choosing and connecting a live provider remains separate. API contract stays 1.4.0.

## 7.100 — October 22, 2026

- Start A21 with an authenticated, permission-filtered `/api/v1/changes` feed for document/work/task revision notices. SQLite triggers capture stable random notice IDs in the same transaction as the entity revision; rolled-back writes leave no notice.
- Add opaque server-held checkpoints bound to owner, credential, resource family, deployment/API audience and stream generation. Resume and replay retain current domain authorization; SQL applies access before pagination. Notices contain identifiers/revision/time and an API link, excluding historical prose and hidden record IDs.
- Add seven-day checkpoint expiry/renewal with bounded expired-row cleanup, owner admission limits, immutable retained notices and a change-log high-water marker. Historical database restores invalidate saved checkpoints; routine newest-snapshot recovery preserves them.
- Publish API contract 1.4.0 and an independent standard-library client/local SQLite inbox example. The inbox commits unique notices and its checkpoint together; task writes remain unavailable to read credentials.
- Document start-now baseline ordering, periodic access/deletion reconciliation, lost-response replay and rollback. This increment does not add webhooks, external delivery receipts or provider adapters. No new dependencies or provider requests.

## 7.99 — October 22, 2026

- Start A20 with user-delegated, deployment/API-bound read credentials for document metadata and/or work/task metadata. Each named integration retains its owner's current domain permissions and cannot access browser routes, task writes, write context or human operation receipts.
- Add browser consent with current-password confirmation, session-bound CSRF, same-origin protection, bounded forms, one-time secret disclosure, 7/30/90-day expiry, owner revocation and account-administrator revocation. Rotation uses an independently issued replacement followed by revocation of the old credential.
- Persist only SHA-256 hashes of high-entropy opaque secrets. Immutable grants and permanent revocation survive repeatable schema installation; password, role, account-state, directory-link and bureau-access changes revoke existing credentials.
- Preserve unexpired credentials through routine boot recovery, but revoke restored credentials after an operator-selected historical database restore so old snapshots cannot revive access.
- Recheck credential expiry, audience, account state and current domain authority on reads. Reject mixed cookie/bearer or duplicate authorization identities without fallback. Attribute minimized credential-use records through the existing serialized audit chain and fail closed when that audit cannot be stored.
- Publish API contract 1.3.0 with read-only bearer security declarations, owner-wide read and issuance limits, paginated credential history, and an independent standard-library read client. No provider or dependency addition. Service principals, OAuth and machine writes remain later A20 work.

## 7.98 — October 22, 2026

- Extend A19 with typed task submission for review through `/api/v1`, using the same task service, current owner/scoped-officer permissions, linked-document access and workflow blockers as the screens.
- Require exact task revision, reason and bounded output/evidence; reject stale writes and preserve existing review/acceptance authority and revision checks.
- Share atomic task/history/audit/review-invalidation/receipt transactions with acknowledgement. Submission fingerprints include exact output text; actor-owned keys cannot be reused across actions or changed input.
- Add a defaulted receipt action column without rewriting immutable acknowledgement rows or changing their retry fingerprints. Return action-aware historical results while keeping submission prose out of API reads/receipts/errors.
- Publish API contract 1.2.0 and a standalone explicit submission client with no automatic POST retries. Keep acknowledgement's 8 KiB body limit; bound submission requests at 64 KiB and output text at 8,000 characters.
- No dependency addition or external provider request. Retain action-aware receipt lookup in a versioned forward repair; older receipt renderers assume acknowledgement.

## 7.97 — October 22, 2026

- Continue A19 with one typed task action: acknowledge an assigned contribution through `/api/v1`, reusing the UI task service and its current owner/officer authority.
- Require a current registered session, matching origin, session-bound CSRF header, bounded JSON, explicit task revision/reason and a caller-saved UUID v4 idempotency key.
- Commit task changes, existing audit/review effects and an immutable actor-owned recovery receipt in one serialized SQLite transaction; concurrent retries cannot duplicate the effect.
- Publish private operation-result reads with fresh linked-document/task access checks. Receipts describe the original result; current task state remains a separate read.
- Add API contract 1.1.0 and an independent standard-library task client with explicit saved keys and no automatic write retries.
- Add an additive receipt table through the existing repeatable installer; retain receipts across restarts and rollback. No new dependency or provider call.

## 7.96 — October 22, 2026

- Travel: admin review of the papers before paper submission (spot feedback #174). When every required form and attachment is in, the traveller picks a reviewer from the Administrative Section (never themselves) and sends the claim for review. The reviewer sees the generated and uploaded documents, adds notes (missing / incorrect / other, optionally against one document), and either sends them back or approves. Email goes to the reviewer on a request or a second look and to the traveller on notes or approval; both sides also get a bell row, and reviewers get a "Review travel papers" page.
- `mark_ready` waits for the approval; any later change to a claim (answers, links, documents) clears it. `travel.review_required` (default on) switches the requirement off. Claims already ready or submitted are not affected until they are edited.
- New columns on `travel_filing` (`review_state`, `reviewer_id`, `review_round`, `review_requested_at`, `review_decided_at`) and a `travel_review_note` table, added automatically on start-up. New email features `travel_review_request` and `travel_review_result` can be switched off under Email.

## 7.95 — October 22, 2026

- Appendix B's "Evidence of Travel attached hereto" starts with the DPO (number and date, blank when not yet known), Appendix A and B, the Certificate of Appearance (the back-to-office report when that replaces it) and the Post Travel Report; uploaded or generated extras follow, then an optional "Other attachments" box on the prepare page (spot feedback #173).
- No schema migration or dependency changes.

## 7.94 — October 22, 2026

- Travel prepare page: designation and purpose are required (marked *) before the forms are made (spot feedback #172).
- DPO: laid out like the office's sample (title and number indented, "SUBJECT:" with a justified, underlined subject hanging at 1.5 in, justified body with 0.5 in first lines, signatory block at 2.25 in, 12 pt after each paragraph). The first paragraph gives the invitation's rationale (when there is one) and then who conducts the activity, when and where; the subject reads "Authority for Select Bureau of Local Health Systems Development (BLHSD) Personnel to Conduct / Participate in / Serve as Resource Person in the …" (spot feedback #170). Re-make the Apps Script templates for the layout to apply.
- New "DPO cites" box in the Documents block of an activity (`calendar_entry_dpo_cites`, created on start-up): the typed text opens the DPO's first paragraph, ahead of the invitation's key lines.
- No dependency changes.

## 7.93 — October 22, 2026

- ARTA walk-in reports can now be filtered to any date range of up to a year, down to a single day: pick From and To dates, or tap Today, Last 7 days or This month.
- The custom range carries through the on-screen numbers, Word/PDF/ARTA-template reports, the BLHSD Excel file and the comments view.
- The Walk-in entries list also has From/To dates and quick ranges, so you can see exactly what came in on a given day.
- Activity and resource-person reports are unchanged; no schema migration or new dependency.

## 7.92 — October 22, 2026

- Start A19 with a supported `/api/v1` read-only contract for selected document metadata, work items and contribution task statuses.
- Publish an isolated typed OpenAPI contract, string identifiers, offset-aware timestamps, bounded keyset pages and consistent private JSON errors.
- Authenticate through current registered user sessions, reuse live document/work authority and return identical missing/inaccessible responses; bearer tokens, machine identities and API writes remain later increments.
- Apply shared-work visibility before paging in SQL for both browser and API lists; linked restricted documents, canonical merges and current grants continue to control access.
- Keep API projections explicit and exclude file bodies, email metadata, submissions, grants and external-operation details. API requests skip browser navigation hydration.
- Add a standalone standard-library read client with bounded reads and no redirect forwarding of sessions, plus checked-in generated contract and integration guidance.
- Repair the remaining combined-survey browser assertion race with delayed-script English/Filipino coverage and an explicit wait for matching draft cleanup; survey runtime behavior is unchanged.
- No schema migration, dependency addition or provider change.

## 7.91 — October 22, 2026

- Continue A18 with visible report scope, inclusive date range, submission/rated-answer denominators, filter reset and a native Apply filters action.
- Resolve resource-person activity member IDs identically for reports, document exports and roster decks; unavailable activity filters fail closed instead of broadening downloads.
- Apply exact organization/descendant boundaries to report and comment selection; keep unavailable saved filter values visible.
- Use active walk-in submission dates for ARTA period options, counts, extracts and comment drill-down; include the complete final day across stored timestamp formats and omit archived source rows.
- Keep unrated SERVQUAL submissions as blank-score Excel rows and state submission versus rated-response counts in Word, PDF, PowerPoint and Excel.
- Explain no matching submissions separately from submissions with no valid ratings, and distinguish activity inventories and named rosters from response extracts.
- No schema migration, new dependency or provider change.

## 7.90 — October 22, 2026

- Start A18 with accessible survey corrections, retained device drafts and clearer submission progress in English and Filipino; reporting clarity remains the next increment.
- Keep drafts until their matching confirmation, isolate registered-attendee draft scopes and preserve newer edits when an older request finishes.
- Explain storage failures, retain offline requests until a matching server receipt, and keep refused/partial combined submissions available for review and copying.
- Share receipt checks with Background Sync; keep the existing submission identities, window/attendee checks, answer scales and scoring rules.
- Improve touch controls, group labels, note/comment controls and focus in one-question mode; rating changes no longer advance automatically.
- Honour named speaker skip controls on the server and distinguish zero/partial combined results from completed feedback. Closed forms offer a read-only device copy when available.
- No schema migration or dependency changes. Existing multi-process/crash reconciliation limits of the survey ledger remain later operations work.

## 7.89 — October 22, 2026

- Extend A17 to travel guidance: current filing meaning, responsible traveller/Administrative Section, checklist/flag blockers and useful existing actions; distinguish paper handover from receipt, approval, payment and email delivery.
- Share readiness blockers between display and fresh ready/submitted service checks; retain ownership, feature-switch, origin and directory-based review authority checks.
- Keep invalid checklist links, answer edits and verification notes on focused server-rendered error pages; show unsaved details read-only when a filing closes during editing.
- Distinguish an earlier valid form from a pending/failed replacement, preserve existing Drive copies and show the latest failure reason.
- Recover generation progress through explicit GET retry, prevent concurrent make clicks and ignore superseded reads. Unconfirmed form requests check saved progress without replaying the write.
- Stop automatic browser upload retries and stop the remaining batch after an uncertain result; offer a saved-file check before another selection.
- Keep existing submission identities, generated document formats and provider contracts. No schema migration or new dependency is required.

## 7.88 — October 22, 2026

- DPO: signatory unit is always the Bureau; the first paragraph is broad and no longer names the section or cites the host's invitation; larger header logos; heading kept in capitals; narrow first columns on the file-copy page.
- Post travel report: DOH letterhead header, bold only on titles with single spacing, and itinerary days outside the activity dates are included.
- Travel: "I travelled by taxi"; links to every CENRR/RER sheet; Move to top and latest-first sort for itinerary entries.

## 7.87 — October 22, 2026

- Extend A17 to calendar status/next-step guidance, distinguishing schedule confirmation from room approval, email delivery and subscribed-app refresh.
- Show series/linked-activity consequences, a native cancellation review page, and restore availability matching the existing 30-day boundary.
- Preserve drafts after validation, competing edits and cancellation during editing; focus the message and label conflict replacement explicitly.
- Offer read-only retry in item previews, invalidate delayed successes/failures on dismissal, and use shared modal focus handling for previews and quick add.
- Explain one-time .ics downloads versus private read-only subscriptions, independent subscription scope, refresh delays and the limits of reset/revocation for cached copies.
- Preserve visibility/write guards, calendar deep links, iCalendar UIDs/sequences and existing feed routes. No schema, dependency or external integration changes.

## 7.86 — October 22, 2026

- Add the Supplies module from reviewed opening stock and staff requests through approval, partial issue, acknowledgment, warnings, replenishment, deliveries, corrections and reports.
- Keep Supplies changes disabled until an administrator verifies staff roles, a dated physical count, the opening ledger and the pilot cutover.
- Preserve authorized reads and transaction evidence while writes are disabled; no live stock or role grants are imported by this release.

## 7.85 — October 21, 2026

- Start A17 with current conference-room status and next-step guidance for owned reservations and validated guest tracking links, including standby, moves, replacements, declines, cancellation, withdrawal, expiry and unavailable alternatives.
- Distinguish owned pending requests from owned approved slots; retain pending-title privacy, directory-based approval authority and independent mutation checks.
- Check typed dates/hours through the existing minimal read API with stale-response protection, retained drafts, explicit check retry and fresh server validation on submission.
- Make mobile request panels contain/restore focus, preserve focus across resizing, use ordinary day links and provide visible server-error recovery; keep the native form usable without JavaScript.
- Clarify immediate booking versus a new request in alternative buttons, current approval blockers and decision notes; avoid claiming email delivery or universal free hours after withdrawal.
- Verify lifecycle/ownership/fresh-authority/HTTP behavior and actual Chromium form-to-data journeys; record sampled local accessibility evidence. Calendar/travel refinements, manual screen-reader and staff task observations remain open.

## 7.84 — October 21, 2026

- Email console (`/admin/email`): add a global **Pause all email** (account mail — invite, reset, registration-link re-send — is never paused; queued room and calendar mail waits and sends after resume; scheduled jobs skip while paused). Audited as `email_pause`.
- Split conference-room meal alerts into their own `room_meal_alerts` switch (reads the old `room_admin_alerts` value until set, so nothing turns back on). Add attachment options `calendar_ics` and `room_ics`.
- Show features that are ON but blocked by another setting (Documents, document sending, shared work, travel filing), list official document dispatch under "Sent from other modules", and write one `document_dispatch` send-log row per recipient.
- Move the admin-tunable timing knobs to `email_params.py` and add room morning/afternoon hours, escalation hours, calendar hold-back, send retries, shared-work digest weekday and the pinned-update cooldown and daily cap (defaults unchanged). `UPDATE_EMAIL_DAILY_CAP`/`UPDATE_EMAIL_COOLDOWN_MIN` constants are now the `update_email_*` settings.
- Send log: filter by feature/result/address, show more, CSV export (manage_users, audited, formula-safe), last-sent and 7-day failure hints, and a "Needs attention" card.
- Delivery policy (applies to all mail, account mail included): staging redirect address, sender name, reply-to, subject prefix. Reply-to needs the updated `apps_script/mail_relay.gs` (redeploy). Test-send can target another active account picked from a list.
- `tests/test_email_coverage.py` fails when a new direct `mailer.send` call, an uncatalogued feature key or an unused catalog entry appears.
- Not changed: birthday greetings still have no per-person opt-out (a documented decision), birthday and daily-job send times follow the single daily sweep, and message wording is still not editable.

## 7.83 — October 21, 2026

- Deliver the A16 shared accessibility engineering slice: readable muted text, theme-aware Wellness buttons, solid keyboard focus indicators, larger survey N/A and carousel controls, keyboard-scrollable growth stages and separate native avatar actions.
- Share modal focus containment, background isolation, Escape dismissal and focus restoration across the mobile drawer, search, feedback, tours and daily snapshots, including nested overlays and responsive dismissal.
- Add a search close control, valid single-control search options, keyboard whole-page feedback with announced errors/status, larger CSS hub filters and Home reflow with doubled text.
- Verify real Chromium keyboard journeys, accessible names/descriptions and native accessibility trees, mobile/desktop layout and no-JavaScript carousel access; record pinned local axe scans of ordinary and open-dialog states.
- Manual screen-reader/browser sessions, remaining axe incomplete checks, staff task observations and live production testing remain open; this is not whole-product WCAG certification.

## 7.82 — October 21, 2026

- Extend A15 to My actions and division follow-up with current document guidance, responsible people/roles, ready/waiting/attention states and direct links to existing controls.
- Filter current access and scope before seek pagination; batch ordinary page data and responsibility names, bound instruction/contribution cards, retain deadline ordering and label unknown dates.
- Share closure facts and legacy contribution choices, preserve authoritative shared-work checks, and retain independent fresh write guards.
- Protect stale review links after authority changes and restore keyboard focus on cross-page action links without waiting for external previews.
- Verify workflow/card agreement, private inputs, role and scope changes, interrupted/partial delivery, page boundaries, growing registers, OS SQLite compatibility and real browser navigation. Staff observations remain open.

## 7.81 — October 21, 2026

- Start A15 with a document “What happens next?” panel showing current responsibility, the next permitted action and an explanation of blockers.
- Cover verification/correction, routing, contributions, exact-version review and returns, signing, delivery, acknowledgment, closure, reopening and archived/read-only states.
- Reuse structural closure and current reviewer authority checks; retain independent POST authorization, revision and exact-version guards.
- Link only to permitted shared work and existing forms; open nested details and move keyboard focus without submitting actions or replaying uncertain external requests.
- Add lifecycle, permission, failure-recovery, read-only HTTP and real-browser navigation coverage. Staff pilot measurements and live production testing remain deferred.

## 7.80 — October 21, 2026

- Navigation: "Travel filing settings" (`/admin/travel`: travel filing on or off, the head of office and certifying-officer fallback, template administrators and the documents relay) moves from search-only into the Administrator menu under Setup & records, for accounts with `manage_users`. Only the menu entry changed; the page, its permission and its search entry are the same, and the search keywords now include head of office, Director, OIC and certifying officer.

## 7.79 — October 21, 2026

- Complete A14 with one alternating document background scheduler and one shared background admission slot, leaving interactive capacity in the two-worker pool.
- Coordinate Drive discovery and filing across processes through an expiring SQLite lease, fenced cursor/result/error writes and durable manual check requests.
- Bound listing/filing turns and intake registration checks with a shared elapsed service budget; process one due filing per turn with backoff, attempt limits and review stops.
- Retain original filing operation markers, payloads and registered numbers after interruptions; expose last/next attempt and protected manual filing retry controls.
- Verify competing processes, real worker exit after filing, stale workers, scheduler fairness, transport budgets, authority changes, safe diagnostics and responsive HTTP navigation during provider stalls.

## 7.78 — October 21, 2026

- Signatory for activity documents (spot feedback #157): the DPO, memorandum and concept note took the head of office only from `travel.sig.head_name`, so they were unsigned unless an administrator typed a name. They now use the same rule as the travel forms (`activity_docs.head_of_office`): the name and title set under Travel filing settings win, and with no name set the Director from the directory is used. Travel filing settings relabels the certifying officer boxes as a fallback and explains that each form takes the head of the traveller's own division from the directory (`travel.directory_signers`, unchanged), and that a blank head of office means the directory's Director. No change to how travel forms pick their signers.

## 7.77 — October 21, 2026

- Real header and a file-copy page (spot feedback #157, #158): the letterhead (seal, Bagong Pilipinas logo and the three-line name) is built into the document's header by `activity_templates.gs` for all four templates, instead of the first table in the body (this also keeps the relay's title-casing from touching "DEPARTMENT OF HEALTH"). A DPO request now carries `extras: {"file_copy": true}`; the relay (`travel_docs.gs` `addFileCopy_`) appends the order's content again after a new section with its own empty header and footer, then two plain tables: BLHSD / Initials / Date, and Keywords / Related issuances, laws, directives. The section change uses the Google Docs advanced service in the relay's Apps Script project. Without it, or if Google refuses, the order is still made, the relay answers `extras: docs_service_off` or `failed`, and the draft message says the extra page is missing. An older relay ignores `extras`. Setup is in `docs/ACTIVITY_DOCS_SETUP.md`: replace `activity_templates` and `travel_docs`, enable the Docs service, deploy a new web-app version and run `rebuildActivityTemplates()`.

## 7.76 — October 21, 2026

- DPO for one person (spot feedback #157): when a DPO has exactly one person, the subject reads "Authority for {name}, {position} of the Bureau of Local Health Systems Development (BLHSD) to Attend as {Participant | Resource Speaker} in the {title} in {venue} on {dates}", the authority line says the same in a sentence, and the Name | Position table is dropped. Resource Speaker when the calendar item says we were invited as a resource person, otherwise Participant. The position follows the #154 rule: a blank line unless "Fill in positions" is ticked. More than one person is unchanged. The request marks the table with `"remove": true`; the relay (`travel_docs.gs` `applyRows_`) deletes that table. Replace the relay script and deploy a new version of it to apply; a relay without it leaves the table with one blank row.

## 7.75 — October 21, 2026

- Add durable, expiring SQLite ownership with fenced completion/failure writes for document service jobs and cross-process reconciliation exclusion.
- Recover aged unstarted sends/signatures after fresh validation; recover interrupted/uncertain operations through existing receipts without repeating their effects.
- Bound automatic receipt checks with backoff and an attempt limit; require review for missing receipts, changed authority and interrupted transient extraction.
- Show clear operation progress and protected minimal status reads; start and cancel the recovery loop with the application lifecycle.
- Verify real worker exit after remote success, competing processes, stale ownership, authorization changes, receipt safety and transient-data privacy.

## 7.74 — October 21, 2026

- Move document action processing and source-preview I/O off the request event loop with SQLite connections owned by their worker threads.
- Bound covered interactive external work to two workers per process with immediate busy rejection and a 120-second request wait; retain capacity until actual completion after timeout/cancellation.
- Share an elapsed Workspace call budget across the initial POST, reply redirects and streamed chunks, with explicit HTTP phase timeouts and no POST retries.
- Prevent active execution, status checks and manual reconciliation from racing over one operation; preserve durable job/relay receipts and sanitize transport errors.
- Verify same-loop navigation during simulated two-second provider stalls, capacity rejection before job creation, cancellation/timeout receipt settlement, and single-effect dispatch behavior.

## 7.73 — October 21, 2026

- Invitation letter for outside activities (spot feedback #156): on a calendar item marked "Another office", an upload (PDF, JPG, PNG or WebP, under 6 MB) keeps the letter in the office Drive through the existing relay upload (`act-<id>/invitation`, shared with the uploader) and stores only the link and file name (`calendar_entry_outside.invitation_url`, `invitation_name`; added by migration). The same upload is read once by the AI (`activity_invitation.py`, the `travel_scan` feature, so its switch, daily budget and per-account limit apply) and returns the office, whether we were invited as a resource person or a participant, and up to three key lines, as a suggestion for the form: nothing is filled in until the person presses "Use these", and nothing is saved until they press Save. The prompt tells the model not to copy individuals' names, numbers or e-mail addresses. The file is never stored by the app; AI off, over budget or unreadable still keeps the letter. "Remove the link" forgets the link only. Needs the relay with upload support, the same as the travel checklist. Saves and uploads are audited as `activity_invitation_file`.

## 7.72 — October 21, 2026

- Share wellness/AWA approval counts, document-review counts, document feature state and the three-item work preview between navigation and Home within one request.
- Reuse the room-approver display lookup across navigation and travel-flag notifications; omit the unused team-link lookup on Home's non-calendar tabs.
- Keep account/session validation and domain permission, write and scoped-data checks live; bind display reads to one account, copy mutable results and retry failed reads.
- Add HTTP parity, query-count, concurrent-user, revocation, feature-switch, failure-recovery and write-boundary regressions.

## 7.71 — October 21, 2026

- Outside activities (spot feedback #155): a calendar item has a new "Who conducts this activity?" choice, BLHSD or another office. For another office it records the host, whether we were invited as a resource person or a participant, and the key lines of the invitation (pasted, one line, up to 600 characters). The DPO background then reads "{host} invited {unit} personnel to ... {title} ..." followed by the pasted lines, and the authority line says "to serve as resource person in" or "to participate in". BLHSD activities draft as before. New table `calendar_entry_outside` (no row means BLHSD); saving is audited as `activity_outside`. No relay or template change.

## 7.70 — October 21, 2026

- Activity documents (DPO, memorandum, concept note): positions are no longer filled in from saved profiles on their own. The Draft button now has a "Fill in positions from saved profiles" checkbox, off by default; without it the position cells are left blank for the person to complete (spot feedback #154).
- Activity templates (`activity_templates.gs`): every paragraph and table now starts plain, because Docs copies the formatting of the paragraph above and one bold line had made the whole DPO bold. Only titles, headings and signatories are bold. The letterhead logos are sized from the picture's own proportions at 70 pt tall. Run `rebuildActivityTemplates()` once to apply it; existing templates are not changed (spot feedback #154).

## 7.69 — October 21, 2026

- Remove session, authority and notification SQL from GET/HEAD requests to packaged public assets, the service worker, manifest and existing favicon path.
- Retain normal routing, file lookup, browser security, cache validation, range responses and request metrics; unsafe methods keep origin checks.
- Match the router's application-relative path so a mount prefix cannot classify private routes as static assets.
- Verify zero database connections/statements with anonymous, active, revoked and malformed sessions, plus private-route, traversal, outage and revocation regressions.

## 7.68 — October 21, 2026

- Page the document registry in groups of 30 after applying current permissions and queue/search filters; preserve full-register counts, measures and CSV exports.
- Resolve authority once per read snapshot and use SQL filters for restricted records, organizational grants, merged receipts and legacy/migrated work assignments.
- Bound search excerpts to page records, skip unused export/global-search snippets, use count queries for approval summaries, and add supporting indexes.
- Add independent legacy-result comparisons, pagination/revocation/work-boundary checks and a reproducible synthetic query/row-loading benchmark.

## 7.67 — October 21, 2026

- Travel Prepare page: a "Your designation (shown on the forms)" field, prefilled from the profile and kept in the browser draft with the signatories. It is sent as `traveler_title` and used for the designation on every form; blank falls back to the profile (spot feedback #150-152, designation part).
- Travel forms (relay `travel_docs.gs`): after each form is filled it is set to Times New Roman 12, paragraphs of 60 characters or more that are left-aligned are justified (tables too), and titles (short bold lines with no full stop, comma, colon or brackets, either centred, all capitals or headings) are bold and in Title Case, keeping acronyms such as DPO, CENRR and RER. Sheets get the font, size and titles; Google Sheets cannot justify. Replace `travel_docs` in the Apps Script project to apply it. No template rebuild (spot feedback #150-152).

## 7.66 — October 21, 2026

- Show each rated resource person on the activity rating page, with their own score, rating count and a clickable result link.
- Link to the combined Type 3 report for the activity while keeping hidden or director profiles subject to the existing visibility rules.
- Add a link from the Type 3 report to the People page to find other resource persons' results.

## 7.65 — October 21, 2026

- Add a personal results list to the Type 3 report for staff whose accounts are linked to a resource-person profile, with each activity's score and rating count.
- Selecting an activity narrows that personal list and opens the existing per-activity scorecard for detailed ratings, comments and downloads.

## 7.64 — October 21, 2026

- Replace model-authored survey answers with validated fact selections and server-rendered figures; fixed answers skip the extra AI call.
- Calculate simple differences on the server, show source labels and periods, and reject invented, changed or incompatible facts.
- Recheck the current session and AI switches after provider calls; preserve resource-person opt-in and search fallback.
- Exclude missing and invalid ratings from Home satisfaction totals and broader survey facts.

## 7.63 — October 21, 2026

- Travel Prepare page: each form in the list has a Make this form again button (Try this form again when it failed). It sends only that form's code, so changing an entry no longer means remaking every form. The earlier copy stays in Drive and the page says so (follow-up to spot feedback #148). No server change: the generate route already took a list of forms.

## 7.62 — October 21, 2026

- Travel Prepare page: itinerary entries can be reordered by dragging their handle, with Move up / Move down buttons and a Sort by date button (spot feedback #147). Entries keep the order shown when the forms are made.
- Travel forms: each ride that needs a CENRR now gets its own CENRR sheet, like the RER (spot feedback #149). The template is unchanged: it already has one repeating line, which now holds one ride.
- The Prepare page says each generated form is a Google Doc or Sheet that can be opened and edited (spot feedback #148).

## 7.61 — October 21, 2026

- Add atomic registration receipts so retries of the same correspondence submission return the saved document/work result without duplicating numbering, tasks or events.
- Add read-only result checks and clear saving/unconfirmed feedback, retain the submitted values in memory and require an explicit retry with the original submission.
- Recheck current access on recovery, reject changed payloads for completed submissions and keep writer waits off the event loop.

## 7.60 — October 21, 2026

- Travel forms follow the office's current "Claims Templates" (Cash Advance, Liquidation, Reimbursement). A liquidation now always makes **Appendix A** (before, only when the itinerary had changed; spot feedback #142), and a liquidation or reimbursement makes **Appendix A and B as one document**, credited to both checklist rows, as in the office's own Word forms (spot feedback #144). The liquidation's Appendix A has the Cash Advance and Reimbursement lines under the total, filled from the advance entered on the filing and left blank when it is not known. A cash advance keeps Appendix A alone. The Apps Script templates must be replaced and rebuilt (`rebuildClaimTemplates()`, docs/TRAVEL_DOCS_RELAY_SETUP.md); until then the new forms cannot be drafted.

## 7.59 — October 20, 2026

- Move PDFium rendering, image decoding, Tesseract and DTRAK scan passes into a resource-limited OCR worker shared by PDF and selected-page reads.
- Bound worker and Tesseract pipe output, preserve scan limits and field evidence, and return retry guidance when OCR is occupied.
- Stop and clean up the worker process group on cancellation, disconnect, timeout or failure; retain capacity until live work has ended.
- Update isolated release tooling to uv 0.13.4 for its reviewed TLS trust-store fix (PYSEC-2026-4321); regenerate its hashed lock.

## 7.58 — October 20, 2026

- Isolate native PDF text extraction in a fresh Linux subprocess with CPU, address-space, elapsed-time and output bounds.
- Admit one native parser per application process, reject excess work with retry guidance, and terminate/reap cancelled, stuck or failed workers.
- Keep child environments and inherited descriptors private; preserve file/link limits, DTRAK behavior, OCR fallback and transient intake.
- OCR/PDFium process isolation remains a separate increment.

## 7.57 — October 20, 2026

- Monitor: a way to see which region each participant belongs to. The roster has never recorded a region, so there was nothing to show. A new **Region** ready-made registration question (Central Office, NCR, CAR, Regions I to XIII, BARMM, Other; required) can be added from the Monitor page in one click, or from the manage page with the other presets. Answers then appear under each person, in "Registration answers at a glance" and in the exported roster. Only people who register after it is added are asked (spot feedback #141).

## 7.56 — October 20, 2026

- Travel checklist wording: the row "DPO signed by a representative" is now "DPO allowing a representative or OIC to sign", with a note that it is the order that lets a representative or the officer-in-charge sign in the Head of Office's place, and the filing question reads "The Department Personnel Order allows a representative or OIC to sign". The row still appears when that box is ticked (spot feedback #145).

## 7.55 — October 20, 2026

- Documents the app makes (calendar item drafts, travel forms and uploaded files) are now shared with the person through the Drive permissions API with `sendNotificationEmail: false`, so Google no longer emails a "shared with you" notice for each one. The link is on the page; the daily email about travel claims that are due soon or overdue is unchanged (spot feedback #146). After drafting, the calendar item says the draft is shared with you, that no email is sent and that drafting again makes another copy (spot feedback #143). Replace `travel_docs` in the Apps Script project to apply the change to the relay.

## 7.54 — October 20, 2026

- Fix for the new letterhead: the Apps Script templates now give the letterhead row (seal, title, Bagong Pilipinas logo) and the DPO Name / Position table fixed column widths that fit between the margins. With Google's default equal columns the title wrapped and the right-hand logo and the Position column could fall off the page. Replace `activity_templates` in the Apps Script project and run `rebuildActivityTemplates()` again.

## 7.53 — October 20, 2026

- The four activity documents (DPO, memorandum, concept note, program flow) now start with the **DOH letterhead**: the DOH seal, "Republic of the Philippines / DEPARTMENT OF HEALTH / Office of the Secretary" and the Bagong Pilipinas logo, with the DOH address footer on every page. Both logos come from the DOH package and are embedded in a new `apps_script/activity_logos.gs`, so no Drive upload is needed. Add that file to the Apps Script project, replace `activity_templates`, and run the new `rebuildActivityTemplates()` (it rebuilds templates that were already good). No change to the app itself (spot feedback #136).

## 7.52 — October 20, 2026

- A calendar item can now also draft a **concept note** and a **program flow**, the rest of the DOH package. The concept note has the numbered DOH sections, the Operational Details table and a program of activities with one row per day; the app fills the title, dates, venue, people and unit and leaves bracketed prompts for the background, objectives, outputs and methodology. The program flow is a heading and two empty rows for each day. They are suggested for trainings, trips and activities lasting several days. The Apps Script templates need to be updated and re-run (docs/ACTIVITY_DOCS_SETUP.md); the first start rebuilds the small document table to accept the new types and keeps what is there (spot feedback #136).

## 7.51 — October 20, 2026

- The drafted invitation now follows the DOH memorandum format used to write to the regions: MEMORANDUM with FOR, FROM and SUBJECT, a request paragraph, the what, when and where, a table of the assistance asked for, the contact line and an initials block. Who it is FOR and the telephone number are left blank to fill in. The Apps Script template needs to be updated and re-run (docs/ACTIVITY_DOCS_SETUP.md) (spot feedback #136).

## 7.50 — October 20, 2026

- Pin runtime, test, audit-tool and deployment-client dependencies with distribution hashes, including PDF libraries.
- Require complete vulnerability scans, a Python dependency SBOM from the production Docker recipe and matching runtime/test versions before release.
- Keep document intake, OCR, previews and generated reports covered by the normal and shuffled Python 3.11 suites.
- PDF/OCR process isolation and the previously excluded authentication/logging changes remain separate work.

## 7.49 — October 20, 2026

- Fix every sign-in and save failing with "This request could not be verified. Reload the page and try again." after 7.48: the new `Referrer-Policy: no-referrer` made Chrome and Edge send form posts with `Origin: null` and no Referer, which the write origin check rejects. The policy is now `same-origin`, which still sends nothing to other sites. Adds a real-browser regression test.

## 7.48 — October 20, 2026

- Enable Secure cookies automatically for configured HTTPS deployments and trusted HTTPS requests, including preference and deletion cookies.
- Add browser framing, MIME, referrer and transport protections, with a staged report-only script policy.
- Prevent dynamic response and service-worker caching of private pages and photos; retain public static assets and the generic offline shell.
- Exclude first-admin setup, authentication throttling and password/hash changes from this enhancement.

## 7.47 — October 20, 2026

- The drafted DPO now follows the DOH Department Personnel Order layout: DOH letterhead, date and number, a subject, a background paragraph, the authority line, a Name and Position table, the expenses paragraphs, "By Authority of the Secretary of Health" with the signatory in capitals, and the DOH address footer. The DPO number, date and funding source are still left blank for you to fill in. The Apps Script template needs to be updated and re-run (docs/ACTIVITY_DOCS_SETUP.md) (spot feedback #136).

## 7.46 — October 20, 2026

- Protect opening a travel filing with durable account-bound submission IDs and atomic filing, checklist, audit and result receipts.
- Recover an existing checklist after an interrupted response; retries reuse the same submission.
- Add private status lookup, preserved form answers and safe closure of unfinished attempts.

## 7.45 — October 20, 2026

- Add the missing in-app update-history entries for 7.36, 7.37, 7.38, 7.40 and 7.41, so the login screen history has no gaps.

## 7.44 — October 20, 2026

- The travel filing page now walks through the claim in steps: 1 Your claim (the answers that decide what you need), 2 Attach the documents (the ones that already exist outside the app), 3 Make the forms (made for you from a template, using what you attached), 4 Enter these in FMIS. Each step explains itself and counts its progress, each item keeps its done or missing badge, and there is one place to prepare the forms (spot feedback #140).
- Fix the "Saved." and error messages on the travel filing page: after saving a checklist item the message was placed after the #fragment in the address, so the browser never sent it and it never showed.

## 7.43 — October 20, 2026

- A calendar item now has a "Documents for this activity" block that says whether it needs a DPO or an invitation. The app suggests from what the item already says (people travelling, who it is open to, its kind) and gives the reason; the person can overrule each one. A needed document can be drafted in Google Docs from the item's details, with the DPO number, date and funding source left blank. The relay needs a one-time template setup (docs/ACTIVITY_DOCS_SETUP.md); until then a draft says so plainly (spot feedback #136).

## 7.42 — October 20, 2026

- Run normal and shuffled Python 3.11 tests on pull requests and before deployment, including Chromium browser tests.
- Reject missing, failed or skipped checks and inconsistent or non-increasing release versions.
- Keep the deployment backup and live-version checks mandatory in GitHub Actions.
- Preserve the 7.40–7.41 travel report and liquidation improvements.

## 7.41 — October 20, 2026

- Liquidation figures on the prepare page: what was actually spent, by kind (plane, TNVS, taxi, per diem and so on, with how many entries were read from your uploaded tickets and receipts), the total against the cash advance, and the refund or the amount over. The Liquidation Report row now points to it (spot feedback #130).

## 7.40 — October 20, 2026

- Post Travel Report on the prepare page: the overview is written from the activity, dates, venue and DPO, and each day is written from the itinerary (rides with times, and taking part in the activity). A day follows the itinerary until you edit it, and a line you wrote is never overwritten. Key points, contributions, support needed, recommendations and the conclusion keep their own boxes, now with a hint on what goes in each (spot feedback #134, #133).

## 7.39 — October 20, 2026

- Verify normal and shuffled test execution on Python 3.11 and record the resolved dependencies.
- Declare the additional PDF and browser test dependencies for clean installations.
- Preserve the travel filing and form improvements in releases 7.36–7.38.

## 7.38 — October 20, 2026

- Fix Appendix B and the Post Travel Report failing with "The relay rejected the signature": requests to the documents relay are now signed over an ASCII-only payload, so checkbox glyphs, curly quotes and accented names no longer break the signature (spot feedback #132).
- When a form fails, tell the person in plain words what happened and what to do, with the filing reference to give the Admin Unit, instead of relay and secret jargon (spot feedback #139).
- Show how the Total is worked out on the prepare page: each fare, and for each day the per diem rule, the region's rate and its lodging, meals and incidentals parts, with the policy notes (spot feedback #138).

## 7.37 — October 20, 2026

- On the travel prepare page, each warning now marks the field it is about in red, with a message on that field, and clicking the warning jumps to the field (spot feedback #131, #137).

## 7.36 — October 20, 2026

- Travel filings are now due 5 working days after the last day of the activity, even when the filing was opened after the activity ended (spot feedback #135).

## 7.35 — October 20, 2026

- Build synthetic survey reference data without reading a production database.
- Give each HTTP test its own database, clients, report caches and rate-limit state.
- Control application dates and token epoch time; retain real elapsed time for worker timeouts.
- Add reproducible shuffled execution and leap-day verification.
- Remove the global duplicate-activity bypass and seed previously implicit audit/archive test state.
- Preserve 7.33 travel upload and 7.34 calendar date-prefill changes.

## 7.34 — October 20, 2026

- Make Quick add redraw its date fields so the chosen day shows in Starts instead of "Pick a date".

## 7.33 — October 20, 2026

- Retry document uploads once on a dropped connection or server error, and say why an upload, ticket reading or feedback failed.
- Keep the feedback message on screen when it can't be sent.
- Log the expected and received origin when a write is rejected, so a misconfigured server address is easy to find.

## 7.32 — October 20, 2026

- Restore the companion growth ladder and guidance on the profile page.
- Give CSM draft/export, activity-feed and search tests explicit survey examples with cleanup.
- Exercise database integrity against a populated temporary database instead of an absent production snapshot.
- Pass the room test's reference date explicitly to the booking guard.
- Retain the concurrent 7.30 and 7.31 calendar and meal-request changes.

## 7.31 — October 20, 2026

- Add a Request meals / Meal form link to the conference room banner on activities and calendar items.
- Add a Request meals entry under Office in the drawer for every requester (Room meals stays admin-only).
- Show a What needs to be done checklist on the meal request form.

## 7.30 — October 20, 2026

- Hide the travel claim link and button on calendar items that hold a conference room (requested, booked, pending move, day mismatch or cancelled-but-holding), since the venue is the office.
- Keep showing a travel claim that was already filed.

## 7.29 — October 20, 2026

- Exclude unused categorical survey items from dimension averages and recommendations.
- Apply shared finite, in-scale answer filtering to score denominators and raw report rows, retaining source records and diagnostic counts.
- Count only contributing respondents in the overall perception metric; retain total submissions separately in official reports.
- Handle null organization paths and non-finite trend values without crashing.
- Verify sparse reference totals across Word, PDF, PowerPoint and Excel, plus exact activity-preview/Excel recommendation agreement.

## 7.28 — October 20, 2026

- Apply exact-origin verification to staff writes and public account operations, including JSON and uploads.
- Reject missing, opaque, malformed, sibling-host, wrong-scheme and wrong-port origins; permit an exact Referer origin when Origin is absent.
- Keep narrow public/bearer and machine-callback exceptions, plus existing Documents/Work CSRF tokens.
- Make logout a protected POST; old GET links show confirmation without ending the session.
- Update cookie-based backup and feedback maintenance clients to send Origin explicitly.

## 7.27 — October 20, 2026

- Sign in again after this update; signing out and account access changes now revoke affected sign-ins.
- Keep directory designations under administrator control while retaining other profile edits.
- Save snapshots every interval, report stalled saves, avoid overlapping timed-out workers, and require fresh sign-in after restore.
- Validate sign-in, onboarding, language, directory, room and installed-app return destinations through a shared local-path policy.
- Stop service-worker write replay after ambiguous proxy failures; retain GET recovery and the deduplicated survey queue.
- Includes the locally prepared security repairs previously labelled 7.23/7.24; those candidate numbers were superseded by concurrent releases on main.

## 7.26 — October 19, 2026

- Search the people list when adding or editing a calendar item, with a clear message when no one matches.
- Keep the system administrator account out of that list.

## 7.25 — October 19, 2026

- Show only events and trips involving your section or division in the home page's Coming up card.

## 7.24 — October 19, 2026

- Add other sections to a calendar item; every involved section sees it and the item shows all of them.
- Mark a travel checklist document as not applicable (or needed) for everyone on the same DPO in one click.
- The Job Order clearance is now named as the signed Certification for Job Order / COS, since they are the same document.

## 7.23 — October 19, 2026

- Show similar activities, dates and details while creating a survey.
- Ask for confirmation before saving a closely matching activity, while allowing a separate activity when needed.

## 7.22 — October 19, 2026

- Open the calendar with Everything I can see selected when no other preferred view is saved.
- Open the Calendar tab with the same default from Team or Me.

## 7.21 — October 19, 2026

- Keep your saved calendar layout and event scope when returning from an item after cancelling or restoring it.

## 7.20 — October 19, 2026

- Save your preferred calendar layout and whose events to show from the calendar toolbar.
- Reopen the saved view after refreshing or returning to the calendar, even if you browse another view in between.

## 7.19 — October 19, 2026

- Keep online activities out of travel claim options and calendar claim reminders.
- Prevent starting a travel claim from an online activity.

## 7.18 — October 19, 2026

- Download an editable Word memorandum draft from an outgoing document.
- Add page notes or pen marks tied to a selected PDF version; pen marks require a matching local copy.
- Index or remove a file’s searchable text with current access and an exact Drive version check.
- Update the existing travel Docs Apps Script deployment to activate pen matching and file text extraction.

## 7.17 — October 19, 2026

- Include the new instruction, search and action modules in the deployed app.

## 7.16 — October 19, 2026

- Tag people and sections in instructions; recipients can find unread tags and mark them read.
- Search saved document details, references, receipts, instructions and email bodies within current access.
- Open My actions for personal steps or Division follow-up for chief and OIC exceptions.
- Use My shared work for contributions already moved to Shared work.

## 7.12 — October 19, 2026

- Prioritize the Date in the Originating office header block for routing-slip document-date suggestions.
- Stop at the next metadata field or routing table; do not fall back to unrelated dates when the office-header date is missing or unreadable.
- Preserve ambiguity checks for multiple routing slips and support split label/value OCR text.
- Update documents_relay.gs in the existing Docs/travel project and redeploy its existing web app; then reread the scan to refresh cached suggestions.

## 7.11 — October 19, 2026

- Widen the intake review workspace, size the preview against the viewport/navigation, and stack panels below 1000px.
- Provide phone view switches below 600px that retain the same form DOM and unsaved values; both panels remain available without JavaScript.
- Collapse OCR suggestions, group fields responsively, keep primary actions accessible, and move floating feedback below the workspace to prevent overlap.
- Scope layout changes to intake review and version its stylesheet/script URLs. No Apps Script update required.

## 7.10 — October 19, 2026

- Derive intake direction from the reviewed sender: Bureau of Local Health Systems Development / BLHSD is Outgoing; other identified senders are Incoming.
- Apply the rule to existing cached OCR suggestions, review saves, Gmail staging and registration; replace the blanket Incoming-only email restriction.
- App-only change; no additional Apps Script update required.

## 7.09 — October 19, 2026

- Recognize routing-slip metadata labels, inline table cells, wrapped subjects/offices and DTRAK identifiers.
- Support document-date suggestions and validate ISO, unambiguous numeric and written month dates; keep ambiguous and conflicting dates for manual review.
- Stop treating the first OCR heading as a subject and avoid assigning dates from unlabelled routing-history rows as current deadlines.
- Add an explicit OCR reread action to refresh cached suggestions without overwriting reviewer-entered fields.
- Requires replacing documents_relay.gs and deploying a new version of the existing Docs/travel web app.

## 7.08 — October 19, 2026

- Bind intake OCR to the queued content checksum, verify the actual source bytes and recheck the source folder/content after reading, while allowing metadata-only Drive version changes.
- Refresh the cached Drive fingerprint from the verified OCR receipt; reject missing or mismatched source receipts before caching suggestions.
- Keep registered-document extraction, approval, signing and filing version checks strict, and show OCR errors beside the review controls.
- Update documents_relay.gs in the existing Docs/travel project and deploy a new version of its existing web app for content-checked intake OCR.

## 7.07 — October 19, 2026

- Fix Workspace replies being decoded twice when Google uses gzip or deflate compression, which caused Drive checks to report an unreachable reply service.
- Remove stale encoding and wire-length headers when reconstructing an already-decoded response while preserving decoded-size limits, redirect validation and single signed POST behavior.
- Identify genuinely malformed compressed replies as decoding errors rather than network connection failures.

## 7.06 — October 19, 2026

- Distinguish the DNS, proxy, TLS/certificate and connection causes previously grouped as relay_unreachable.
- Identify the affected Google service while keeping request URLs, credentials and raw transport/provider messages private.

## 7.05 — October 19, 2026

- Show specific, safe document-intake connection diagnostics for missing configuration, rejected signatures, older deployments, folder mismatches, network failures and processing stages.
- Distinguish relay rejections made before an operation receipt exists while continuing to reject mismatched receipts and hide arbitrary provider text.
- Keep queued reviews after failed checks and clear the diagnostic on the next successful listing.

## 7.04 — October 19, 2026

- Expand the sign-in page’s What’s new to explain the unified Drive and Gmail review queue, body-only emails, grouped attachments, automatic filing and Director routing.
- Explain the Documents permissions and configuration needed to use Intake, and that Gmail stays paused during setup.
- These notes describe the workspace delivered in v7.03; this release corrects its incomplete on-screen description.

## 7.03 — October 19, 2026

- Include body-only work emails in intake with a preserved, escaped Email body box and No attachment note, visible through Director routing without OCR or a synthetic Drive file.

- Converge eligible Gmail auto-pull with Drive uploads in the unnumbered review queue: preserve email provenance, group attachments, prefill sender/receipt details, and require review before numbering and Director instructions.
- Preserve importer replay/recovery with queued acknowledgements, support Shared Drive attachment operations, and keep paused discovery from reverting email to automatic registration.

- Add an opt-in Shared Drive intake queue with metadata discovery, saved review drafts, expiring claims, cached OCR suggestions and grouped scan registration.
- Allocate numbers only after review; move and rename the same files by registration year and direction through durable, retry-safe filing operations.
- Add a document preview and Director routing slip workspace, with a paginated instruction inbox and server-enforced Director-first routing for new incoming intake records.
- Keep intake and registered history permission checked, preserve original filenames, and provide duplicate-scan warnings and reversible dismissal.
- Bound new queue pages and duplicate lookups; reuse the existing FastAPI, SQLite and Workspace relay without a new paid service.
- Preserve legacy OCR preview routes and show their escaped suggestions; allow HTTP tests to initialize a synthetic database in clean checkouts.
- See `docs/DOCUMENT_WORKSPACE_PHASES.md` for setup and live acceptance. Drive integration is disabled until configured; this change does not enable or deploy it.

## 7.02 — October 17, 2026

- Let Documents workflow administrators archive closed or cancelled records with a reason and restore them later.
- Keep archived records and their history available through direct links and an administrator Archive queue while excluding them from normal queues and CSV exports.

## 7.01 — October 17, 2026

- Choose the receipt channel from a dropdown when registering a document or recording another receipt: Email, Gmail, Hand-delivered, Courier, DTRAK, or Other.

## 7.00 — October 17, 2026

- The certifying officer on the travel forms now shows the division head's position in the directory (for example Medical Officer V) rather than the designation "Division Chief". The head of office is still the Director seat in the directory, which includes an OIC-Director; the filer's division head still comes from the filer's own division.

## 6.99 — October 17, 2026

- Use the official ARTA wording for rating statements SQD6, SQD7 and SQD8 (adds "(if asked for help)" and "(if denied) … explained to me"); the online form, paper-entry form and official report all read from the same text. Filipino updated to carry the same conditions (draft, for the office to review). Stored ratings are unchanged.

## 6.98 — October 17, 2026

- Add a "See the name list" button to the Who responded section of an activity's report, shown only to people who manage the activity; it opens the activity's roster limited to the registered people who responded (Spot Feedback #91).
- The roster page gains a "Show only the people who responded" view; the reminder count does not depend on the view. Walk-in and paper responses are counted but have no name to list.

## 6.97 — October 17, 2026

- Make the public service feedback (Type 1 / CSM) form follow the official ARTA Client Satisfaction Measurement form: the official intro and confidentiality note, the date shown automatically, client type, sex, age, region of residence, service availed (from the bureau's list), the Citizen's Charter definition and CC1 to CC3 with the skip rule, optional email and the official suggestions wording (Spot Feedback #121). Everything except the ratings is optional.
- Store those answers as the paper entry does, so online responses count in the official CSM report; online sex answers are now stored as "Male" / "Female" like the report expects.
- Filipino text added for all of it (draft, for the office to review). The activity and resource-person forms are unchanged.

## 6.96 — October 17, 2026

- Keep the small reading taken from each uploaded ticket, receipt, Certificate of Appearance and refund receipt, and draft Appendix A entries and Appendix B answers from it, each showing where it came from (Spot Feedback #122, #123).
- Fill the head of office (the Director) and the certifying officer (the filer's division head) from the directory (Spot Feedback #125).
- Offer "Review and make the forms" once every required attachment is in.
- Carry the cash advance's Appendix A into a liquidation, and add the DPO date from the uploaded DPO.
- Read departure and arrival times and the refund receipt off uploads.

## 6.95 — October 17, 2026

- Add "Add another ride on this day" to every itinerary entry, and "Add TNVS to / from the airport" to plane entries (Spot Feedback #120, #124).
- Warn when two entries on the same day both claim a per diem.

## 6.94 — October 17, 2026

- Hide the Per diem amount box when a per diem rule is chosen and the policy rates give the amount; "Change amount" brings it back (Spot Feedback #119).

## 6.93 — October 17, 2026

- Require the DPO number on every travel filing, when opening it and when editing its answers (Spot Feedback #116, #118).
- Explain on the travel form that the lodging question is about the room cost, not the kind of filing (Spot Feedback #115).

## 6.92 — October 17, 2026

- Fix the break check-in rating buttons so tapping 5 can no longer select 4 (Spot Feedback #117).
- Keep a conference room you unticked when a calendar form is sent back with an error (Spot Feedback #114).

## 6.91 — October 17, 2026

- Locate DTRAK subject cells using labels and table geometry, correct slight skew and OCR a border-free enlarged crop.
- Preserve successful template-region subjects across later-page differences and publish page 1 before reading page 2.
- Carry structured field readings and display source crops, text and specific failure reasons beside Subject.
- Handle malformed display results and empty text previews explicitly.

## 6.90 — October 17, 2026

- Recognize Title and Subject/Title labels and bounded multiline subjects.
- Reconcile identical subject words across formatting differences and substantial leading excerpts without inventing text.
- Expose genuine conflicting readings beside fields with original page references; preserve manual corrections.

## 6.89 — October 17, 2026

- Automatically read the first local PDF page and the next page for DTRAK documents; public links use the same page scope.
- Fill editable fields directly, synchronize visible date controls and require review approval before work selection.
- Preserve manual edits, replace earlier machine-filled values on source changes and invalidate approval after edits.
- Distinguish routing dates from document dates, normalize document types and use bounded positional OCR for tracking captions and deadlines.
- Correct confirmation-checkbox handling and keep source evidence available inline.

## 6.88 — October 17, 2026

- Recognize DTRAK routing-slip headers, wrapped subjects and standalone tracking numbers.
- Separate office and date fields; exclude form versions and routing-table text from metadata.
- Flag routing deadlines, handwritten notes and routing-slip date semantics for review.

## 6.87 — October 17, 2026

- Bypass service-worker forwarding for temporary PDF and page reading requests.
- Send OCR image bytes instead of Blob request bodies for mobile compatibility.
- Explain connection failures and explicitly report when no fields were pre-filled.

## 6.86 — October 17, 2026

- Add local PDF preview and explicit page selection using locally hosted PDF.js.
- Extract native text on-device; send scanned pages as bounded compressed images for local OCR.
- Process selected pages sequentially with progress, partial results, retry, cancellation and cumulative review.
- Preserve original page numbers, report incomplete coverage, and retain manual control of form entries.
- Keep whole-file/public-link reading available with its existing 20 MiB limit.

## 6.85 — October 17, 2026

- Increase transient PDF uploads and link downloads from 6 MiB to 20 MiB.
- Update browser validation, server limits, error messages and guidance consistently.
- Retain the existing page, OCR, pixel, extracted-text and timeout limits.

## 6.84 — October 17, 2026

- Add disabled-by-default, signed Gmail intake with mailbox/account binding and atomic duplicate protection.
- Add Apps Script discovery, private Drive attachment storage, stable checkpoints, bounded retries and operator recovery controls.
- Show Gmail source details and permission-filtered review queues, with explicit extraction confirmation and stale-edit protection.
- Include synthetic Google-service and cross-language integration tests plus setup/recovery documentation.
- Keep live mailbox acceptance and trigger rollout for Phase 6; operational controls currently run through Apps Script.

## 6.83 — October 17, 2026

- Retain the selected file or link after reading attempts, until explicit removal or navigation.
- Distinguish successful reading from fields actually filled, existing values kept, and no-match outcomes.
- Open no-match text previews and guide users to manual fields; surface reading results on mobile.
- Handle expired sessions, unexpected server responses, connection errors and a 90-second browser timeout.
- Recognize split labels, full-width colons, missing label separators and numbered order headings conservatively.

## 6.82 — October 17, 2026

- Clarify selection, oversized-file rejection, reading progress, and whether OCR ran.
- Show a bounded extracted-text preview even when no form fields are recognized.
- Add a remove/clear button and discard late responses after removal while preserving entered values.

## 6.81 — October 17, 2026

- Read scanned PDF pages with local OCR through memory-only rendering and pipes.
- Keep source files, page images, and extracted contents out of persistent storage.
- Show OCR review warnings with existing page evidence and preserve typed entries.
- Include the OCR engine in deployment and bound page count, image size, and OCR execution time.

## 6.80 — October 17, 2026

- Make PDF upload the first correspondence field, with an optional public PDF link.
- Read text PDFs in memory and pre-fill empty fields with page evidence for review.
- Preserve existing entries and save confirmed details only when registering.
- Keep scanned or password-protected PDFs on the manual-entry path.

## 6.73 — October 16, 2026

- Create short links with an explicit button click to conserve the Short.io allowance.
- Stop automatic creation and old unrequested jobs; preserve completed links.

## October 16, 2026 (v6.72 — Short.io public links)

- Replace is.gd creation requests with authenticated Short.io requests for blhsd.s.gy.
- Migrate unsuccessful legacy jobs while preserving completed mappings and original destinations.
- Show missing configuration, provider failure, quota/auth restrictions and retry timing on sharing pages.
- Cover migration, deduplication payloads, secret handling, retries and HTTPS domain validation with regression tests.

## October 16, 2026 (v6.68 — participant registration page)

- Remove activity management and travel claim links from the public registration page; staff can use the internal activity and calendar pages.

## October 16, 2026 (v6.67 — calendar travel claim links)

- Open the matching travel filing and checklist when a claim reminder is selected on the calendar.
- Keep the activity title linked to the activity page.

## October 16, 2026 (v6.66 — automatic public short links)

- Add an opt-in is.gd outbox in SQLite, with persisted retries, shared pacing, expired-lease recovery and shutdown draining.
- Queue public activity/form links on creation; reuse mappings for sharing and printable/downloadable QR codes, with original-link fallback.
- Update sharing controls when shortening completes; keep signed participant URLs out of the provider.
- Add resumable active-link backfill, configuration/rollout documentation and runtime deployment packaging.
- Tests: `tests/test_short_links.py` and activity/sharing regression tests.

## 6.48 — October 16, 2026

- Filter opening questions by claim type and show external advance details only for an external liquidation.
- Show only applicable preparation sections; retain required official report fields and prefilled signatories.
- Guide claimants to the next missing attachment, form, review item, or print list; collapse completed, optional, and FMIS checklist details.
- Use policy ceilings only to prefill cash advance estimates, never actual fares for reimbursement or liquidation.
- Show browser draft restore/save failures and a direct checklist link; omit inapplicable refund/deviation text from generated forms.
- Preserve the existing browser-only draft design, database schema, official form templates, and manual submission workflow.
- Add browser regression coverage for claim switching, mobile layout, fare calculations, local drafts, conditional sections, and document generation with a fake relay.

## 6.47 — October 16, 2026

- Added an audited Documents enable/disable control to Administrator → Documents setup.
- Enabling requires an explicit bureau-wide permissions-administrator grant and keeps sending disabled; disabling stops both switches.
- Confirmation rechecks current authority and settings revision to reject stale or replayed changes.

## 6.46 — October 16, 2026

- Added Administrator → Documents setup for an explicit, reviewed initial batch of existing active account appointments.
- Setup grants only permissions/workflow administration, records the operator and authorization, and leaves both Documents switches disabled.
- Confirmation rechecks account identity and administrator authority atomically; existing grant-administrator history closes the setup route.


## 6.42 — October 15, 2026

- Added document registration, routing, review, signing/release, closure, scoped search and reporting for acceptance testing.
- Documents reuses the existing travel Docs and mail relays for extraction, saved signatures and durable Gmail dispatch/status.
- Includes profile-signature preview, compatibility tests and existing-deployment upgrade instructions.
- Module and sending switches remain disabled; live acceptance and office policy decisions are required before operational use.

# CHANGELOG — Cowork revisions (surgical)

## 2026-10-15 (v6.45 — the DPO and the Certificate of Appearance are checked as they are uploaded)

- `travel_scan.py`: `DOC_FOR` maps a checklist row to what is read (receipt rows as before, `dpo`, `cert_appearance`). `read_doc` asks only for the fields below, never a name; `clean_dpo` / `clean_appearance` never raise; `check()` sets the reading against the filing.
- DPO: number, issue date, the travel dates it covers, and whether it names a funding source. Warns when no funding source is stated, when the number or date differs from the filing, or when its travel dates do not cover the activity. Offers the number / date for an empty or different field.
- Certificate of Appearance: warns when its dates do not cover the activity dates.
- `travel_routes.py`: the upload response gains `doc`, `checks` and `fill` next to `reading`. A reading never changes the filing; the person copies a DPO number / date into "Change my answers" and saves it. Same `travel_scan` rate limit; a failed or skipped read never stops the file being saved. Nothing from a reading is stored on the server.
- `static/js/travel_upload.js`: shows the warnings under the row (kept across the reload in this browser's session) and a button that puts the DPO number / date into the answers form.
- Tests: `tests/test_travel_relay.py` (cleaning, each check, a DPO and a certificate upload, nothing stored, filing unchanged).
- **Version bump:** `APP_VERSION` 6.44 → 6.45.

## 2026-10-15 (v6.44 — tickets and receipts are read as they are uploaded)

- `travel_scan.py`: `READ_CODES`, the checklist rows whose uploads are tickets or receipts (plane ticket, boarding pass, boat / bus ticket, terminal fee, taxi, ride-hailing, lodging bill, extra-expense invoice).
- `travel_routes.py`: an upload to one of those rows is read by the AI at the same time as it goes to Drive (`asyncio.gather`), under the existing `travel_scan` rate limit. The answer comes back as `reading` (and `ai: false` when AI is off). A failed or skipped read never stops the file being saved; a failed Drive upload returns no reading. Nothing from the reading is stored on the server.
- `static/js/travel_upload.js`: shows what was found under the row and keeps peso readings in this browser's session only (`tv-reads:<ref>`).
- `static/js/travel_prepare.js`: each day's fare box lists those readings with a "Use" button, the same one the scan picker uses (`offer`). Nothing is filled in until it is pressed.
- Tests: `tests/test_travel_relay.py` (read on upload, other rows not read, AI off, failed upload, read limit, nothing stored).
- **Version bump:** `APP_VERSION` 6.43 → 6.44.

## 2026-10-15 (v6.43 — upload a file instead of pasting a link)

- `apps_script/travel_docs.gs` (script version 2): `upload_file` puts a JPG / PNG / WebP / PDF in `ROOT/<filing>/<row>/` (one sub-folder per checklist row, idempotent on `request_id`, folder shared view-only with the claimant); `trash_file` trashes a folder or file only when it sits under the root folder. `ping` answers `version: 2`.
- `gdocs_relay.py`: `Relay.upload_file` / `Relay.trash_file`, `UPLOAD_VERSION = 2`, plain-word errors for the new codes.
- `travel_routes.py`: `POST /travel/f/<ref>/upload?code=` (raw file, owner-only, same-origin, open filings, upload / carry rows only, 30 a minute per account) sends the file to the relay, saves only the folder link and id once the relay confirms, and drops the bytes. `POST .../item/<code>/remove-upload` trashes the folder, then clears the row. Pasting a link over uploaded files trashes them first. The admin "Test the relay" press records `travel.relay_version`; the button shows only at version 2, so an old script deployment changes nothing.
- `travel.py` / `storage.py`: `travel_item.drive_source` (`upload` or `link`) so only office-made folders are ever trashed; `save_upload`, `clear_upload`, `uploaded_folder`. `purge_filings` trashes uploaded folders first and skips a filing whose files cannot be trashed (retried next run).
- `static/js/travel_upload.js`, `templates/travel_filing.html`: "Choose file or take photo" (several files at once, big photos shrunk to about 2000 px in the browser) next to the Drive-link box, which stays as the fallback.
- Tests: `tests/test_travel_relay.py` (upload, failure, refusals, switch, rate limit, remove, replace, purge); `test_travel_admin.py` lists the new column and the audited removal.
- **Version bump:** `APP_VERSION` 6.42 → 6.43. Redeploy the relay script (docs/TRAVEL_DOCS_RELAY_SETUP.md, step 7).

## 2026-10-15 (v6.41 — read the fare off a ticket or receipt)

- `ai_core.py`: `ask()` / `_http_generate()` take `images=[(mime, bytes)]`, sent to Gemini as inline data ahead of the prompt. An image call never uses Groq (the Groq-alone and the quota-fallback paths both skip it) and the bytes are never logged. New feature `travel_scan`, 30 a day.
- `travel_scan.py` (new): `sniff` (type from the first bytes), `clean` (a bad amount, date or kind becomes empty, never raises), `read` (one structured Gemini call).
- `travel_routes.py`: `POST /travel/f/<ref>/scan`, raw file as the body (JPG / PNG / WebP / PDF, under 6 MB), owner-only, same-origin, 12 a minute per account (`ratelimit.py`). Stores and audits nothing.
- `static/js/travel_prepare.js`: a file picker under each day's fare box. It shows what was found with a "Use" button; only that button sets the fare (and the date / from / to when empty, and the taxi / TNVS receipt choice). A non-peso total is not offered.
- Tests: `tests/test_travel_scan.py`; `test_travel_admin.py` lists the new read-only POST.
- **Version bump:** `APP_VERSION` 6.40 → 6.41.

## 2026-10-15 (v6.40 — travel rates fill in by themselves)

- `static/js/travel_prepare.js`: the policy limit and the daily allowance now fill the fare and per diem boxes without a click (`autofill`): a box is filled while empty or still holding the last automatic value, so changing a rate updates it and a typed amount is kept. "Set every day to…" sets the per diem rule for the whole trip at once; the per-day "Use" buttons remain. The "Fill every day" button is gone.
- **Version bump:** `APP_VERSION` 6.39 → 6.40.

## 2026-10-15 (v6.39 — travel policy rates)

- `travel_rates.py` (new, pure): DO 2019-0225 and 2019-0225-A as tables and functions. `day_amount` (DTE by cluster, 100% / 50% days, live-in, subsistence allowance, provided lodging or meals, the within-50 km meal allowances), `row_cap` (taxi 550 / TNVS 700, Annex C by area, seaport and shuttle zones, live-out distance bands with the 300 no-receipt hold, Annex B LTFRB fare), `rates_for_rows`, `find_areas`, `ltfrb_fare`, `live_out_max`.
- `travel_rules.py`: `ride_check(..., cap=None)` holds a ride to its policy limit on any document and counts the route as approved; `flags_for(..., opts, is_working)` also flags a day whose per diem is above its rule. A per-diem flag is stored under `over_ceiling` (the table only allows four kinds); `flag_label` headings it on the verify page.
- `travel_docs.py`: `blank_row`, `normalize_rates`; rows carry `basis`, `place`, `km`, `day_kind`, `lodging_provided`, `meals_provided`; `rides_of` / `ride_answers` take the options.
- `travel_routes.py`: `POST /travel/f/{ref}/rates` (read-only calculator, owner only, same-origin, rate limited by the new `travel_rates` bucket, not audited), `GET /travel/rates` (the rate card), policy tables on the prepare page, options passed through `generate`.
- `static/js/travel_prepare.js`: rates panel (destination, subsistence allowance, senior / PWD), per-row fare rate with an Annex C place search or distance, per-row per diem rule, "Use" buttons, "Fill every day with the policy per diem". `rideCheck` takes the policy limit as an optional sixth argument.
- Templates: `travel_rates.html`; "Policy rates" tab; verify page uses `travel_flag_label`.
- Tests: `tests/test_travel_rates.py` (tables, the LTFRB table against its printed method, day rules, caps, flags, normalize, routes, JS/Python parity); `tests/test_travel_admin.py` lists the calculator as read-only.
- Docs: `docs/TRAVEL_RATES_PLAN.md` (what is automated, how, the readings to confirm, what is not automated); `docs/TRAVEL_FILING_PLAN.md` open item closed.
- **Version bump:** `APP_VERSION` 6.38 → 6.39.

## 2026-10-15 (v6.38 — Sheets templates and the template maker)

- `apps_script/travel_docs.gs`: the relay now fills a Google Sheet template as well as a Google Doc (it checks the template's type): `applyFieldsSheet_` and `applyRowsSheet_` (one marker row copied per item; raw `{{...}}` never left behind). The CENRR and RER forms are Excel forms, so their templates are Sheets.
- `apps_script/travel_templates.gs` (new): one-time `makeTravelTemplates()` converts the office's Word and Excel files (found by name under a source folder) into Google Docs / Sheets in `<root>/_templates`, replaces the sample values with the `{{placeholders}}`, saves the `TPL_*` Script Properties and logs every placeholder that did not land; `checkTravelTemplates()` re-checks. Skips a template whose property is already set.
- `travel_docs.py`: Appendix B gets `dpo_ref`; CENRR gets `dates` and `dpo_ref`; RER gets `activity_title` and `dpo_ref` (golden files updated).
- `docs/TRAVEL_DOCS_RELAY_SETUP.md`: step 2 now uses the template maker; a new deployment version is needed after changing the scripts.
- Tests: `tests/test_travel_scripts.py` and `tests/js/sheet_harness.js` (both scripts parse; the real sheet code runs against a fake Sheets API on grids that copy the CENRR and RER layouts).
- **Version bump:** `APP_VERSION` 6.37 → 6.38.

## 2026-10-15 (v6.37 — travel library, ceilings, retention)

- `travel.py`: `route_types`, `flat_ceilings`, `save_ceilings` (all values checked before any write; amounts 0 < n <= 100,000), `add_route` (always creates the route's RER ceiling), `is_template_admin`, `justifications`, `save_justification` (only the four library tokens allowed), `holiday_notice`, `purge_filings`.
- `travel_routes.py`: `GET /travel/admin`, `POST /travel/admin/ceilings`, `POST /travel/admin/route` (Administrative Section only; audited as `travel_ceiling_save`); `GET /travel/library`, `POST /travel/library` (template administrators edit, other Admin Unit members read; audited as `travel_library_save`). Holiday notice on `/travel/admin` and `/admin/travel`. Nav items "Ceilings and routes" and "Justification library" (cap `room_admin`).
- `retention.py`: `purge_travel_filings(conn, months, dry_run)` and `--travel-filings` (with `--dry-run`, `--months`). `rooms_notify.tick` runs the purge once a day beside the room-guest purge and never lets it stop the room notices. Submitted filings are purged by `submitted_at`, withdrawn ones by `withdrawn_at`; links, file ids, FMIS references and notes on items, flag text and notes, and saved answers are blanked, `purged_at` is set, the row and its dates stay.
- Templates: `travel_admin.html`, `travel_library.html`.
- Tests: `tests/test_travel_admin.py`, including a final sweep (no table gains a content column unnoticed, every travel POST is audited unless it is a draft edit, every travel route needs a login, no public prefix includes `/travel`).
- **Version bump:** `APP_VERSION` 6.36 → 6.37.

## 2026-10-14 (v6.36 — travel flags: verify queue)

- `travel.py`: `flag_queue` (open or recently decided, with the filing and person; withdrawn and submitted filings are left out), `get_flag`, `decide_flag` (rejection needs a note; a participant-only flag is verified only with the supervisor's confirmation; a rejection sends a ready filing back to open; filings no longer open cannot be decided).
- `travel_rules.completeness`: a rejected flag blocks "ready" like an open one, with the note in the message.
- `travel_routes.py`: `GET /travel/verify` and `POST /travel/verify/{flag_id}` for Administrative Section members only (`rooms.is_room_admin`, no admin-role bypass), same-origin checked, audited as `travel_flag_decide`, off when the travel switch is off. `templates/travel_verify.html`; nav item "Verify travel flags" (cap `room_admin`, section Admin Unit) in the Travel group.
- `travel_notify.py`: the Admin Unit line now counts only open flags on open or ready filings and links to `/travel/verify`; a person is told when something on an open claim was rejected.
- Tests: `tests/test_travel_flags.py` (all ride vectors through the generate route, queue access, decisions, ready blocking, regeneration, bell).
- **Version bump:** `APP_VERSION` 6.35 → 6.36.

## 2026-10-14 (v6.35 — prepare and generate travel forms)

- `travel_docs.py`: `defaults`, `normalize`, `build_payloads` and one builder per document (`appendix_a`, `appendix_b`, `mc114_justification`, `jo_cert`, `travel_report`, `cenrr`, one `rer` per ride). Payloads are built in memory from what the prepare page posts and are never stored.
- `travel.py`: `sync_flags` (flag rows follow the rides by `sig`; an unchanged flag keeps its decision), `set_derived_answers` (`rides_cenrr` / `rides_rer` bring the CENRR and RER rows onto the checklist), generation state (`start_generation`, `finish_item`, `finish_generation`, `generation_status`; `doc_state` is `pending|done|failed:<revision>`), and `mark_ready` refuses while documents are being made.
- `travel_routes.py`: `GET /travel/f/{ref}/prepare`, `POST /travel/f/{ref}/generate` (JSON, owner only, same-origin, rate limited; documents are made in a `BackgroundTask`, one relay call at a time, `request_id = ref:item:revision:n`), `GET /travel/f/{ref}/status`.
- `templates/travel_prepare.html`, `static/js/travel_prepare.js` (itinerary rows, live totals and ride flags, optional browser draft), `static/css/travel.css`, a "Prepare the forms" button on the filing page.
- Tests: `tests/test_travel_docs_payloads.py` (with golden files in `tests/golden/travel/`), `tests/test_travel_generate.py`.
- **Version bump:** `APP_VERSION` 6.34 → 6.35.

## 2026-10-14 (v6.34 — travel documents relay)

- `gdocs_relay.py`: signed client for the travel documents Apps Script. Envelope `{ts, payload, sig}` with `sig = HMAC-SHA256(secret, "ts.payload")`, `ts` in ms; env `CSS_DOCS_RELAY_URL` / `CSS_DOCS_RELAY_SECRET`; 90 s timeout (10 s connect), follows redirects, one retry on transport error with the same `request_id`; reuses `mailer._parse_relay_json` and `_relay_not_run_reason`. An unconfirmed 200 is a failure (unlike mail). Never raises: returns `RelayResult`. `get_relay()` is the seam tests fake.
- `apps_script/travel_docs.gs`: relay source (actions `ping`, `check_link`, `generate_doc`), with the signature check, a 5 minute clock window, slug-only template/folder/request names, `@doh.gov.ph`-only sharing, and idempotency on `request_id`.
- `travel_routes.py`: `POST /travel/f/{ref}/link-check` (JSON, owner only, same-origin, rate limited by `ratelimit` bucket `travel_relay`; saves the link and `travel_item.drive_file_id`); `/admin/travel` gains relay status and `POST /admin/travel/ping`, plus `POST /admin/travel/signatories` for signatories and template administrators.
- `docs/TRAVEL_DOCS_RELAY_SETUP.md`; `deploy_hf.RUNTIME_PY` lists `gdocs_relay.py`.
- Tests: `tests/test_travel_relay.py`.
- **Version bump:** `APP_VERSION` 6.33 → 6.34.

## 2026-10-14 (v6.33 — travel filing reminders and bell)

- `send_reminders.py`: new job `travel_filing_due` (`send_travel_filing_due`, CLI `--travel-filing-due`, `run()` branch) and timing knob `travel_filing_lead_days` (default 2, range 1-14). One email a day per person: open or ready filings due within the lead days or overdue, plus submitted cash advances whose activity is over with no live liquidation (`travel.unliquidated_cas`). Skips when `travel.enabled` is off; repeats skipped through `_already_sent` (subject carries the date); goes to the directory email, else the login.
- `mailer.py`: `FEATURES["job_travel_filing_due"]`, `travel_filing_due_message`, `_PREVIEWS["job_travel_filing_due"]`.
- `travel_notify.py`: `bell_rows(conn, user_id, today)` from one aggregate query ("N travel claims are overdue" / "due soon", "A cash advance still needs a liquidation"); Admin Unit members also get "N travel flags to verify" only while open `travel_flag` rows exist. Empty when the switch is off. `app.py`: one wrapped call beside `rooms_notify.bell_rows`; `deploy_hf.RUNTIME_PY` lists the new module.
- Tests: `tests/test_travel_reminders.py`.
- **Version bump:** `APP_VERSION` 6.32 → 6.33.

## 2026-10-14 (v6.32 — travel filing shell: checklists, links, ready and submit)

- `travel.py`: filing lifecycle (`create_filing`, `update_answers`, `save_item`, `mark_ready`, `mark_submitted`, `withdraw`, `refresh_deadline`), `activity_choices`, `resolve_source`, `filing_summaries` (one query per 500 ids), `calendar_chips`, `event_url_for`.
- `travel_routes.py`: `/travel`, `/travel/new`, `/travel/f/{ref}` (+ `/answers`, `/item/{code}`, `/ready`, `/submit`, `/withdraw`), `/admin/travel` (on/off switch). Every handler checks the switch, then ownership; every POST checks Origin/Referer. Admin Unit members can view, not edit.
- Guards: cash advance only when the activity starts more than 7 days away; one live cash advance per user and activity; reimbursement hidden when a live cash advance exists; warning page (with acknowledge) before a new cash advance while an older submitted one has no liquidation; liquidation needs a submitted cash advance or a manual amount.
- Templates: `travel_index`, `travel_new`, `travel_filing`, `travel_ready`, `admin_travel`, `_travel_tabs`; `static/css/travel.css`.
- Small inserts: `app.py` (import, router, "Travel" nav group, `_travel_url` on activity pages), `office_calendar.py` (`filing` key on entry and activity items), `_calendar_body.html` (chip), `calendar_entry.html` + `calendar_routes.py` (Travel claim block and button), `link_tree.html`, `monitor_event.html`, `activity_manage.html` (button), `deploy_hf.RUNTIME_PY`.
- Tests: `tests/test_travel_pages.py`; `tests/test_search.py` nav expectations now include the Travel group.
- **Version bump:** `APP_VERSION` 6.31 → 6.32.

## 2026-10-14 (v6.31 — travel filing foundations, employee number)

- `storage.py`: DDL for `travel_filing`, `travel_item`, `travel_flag`, `travel_route_type`, `travel_ceiling`, `travel_justification` (additive, `IF NOT EXISTS`); `admin_user.employee_no` (guarded ALTER, `_ADMIN_COLS`/`_admin_row`, `get_user_profile`, `set_user_employee_no`); ten `travel_*` audit labels; `init_db` tail calls `travel.ensure_defaults`.
- New modules: `travel.py` (seeds, settings defaults, `ceilings`), `travel_rules.py` (deadlines, `ride_check`, flags, `build_checklist`, `completeness`), `travel_checklist.py` (`CHECKLIST_REV = "FMS-BD-01 r6 2025-06"`), `travel_docs.py` (`date_range`, `peso_words`, `money`). All added to `deploy_hf.RUNTIME_PY`.
- `app.py` `/me`: saves the employee number only when the field is on the posted form; `templates/me.html`: new input.
- Tests: `tests/test_travel_rules.py`, `tests/test_travel_core.py`. Plan: `docs/TRAVEL_FILING_PLAN.md`.
- **Version bump:** `APP_VERSION` 6.30 → 6.31.

## 2026-10-14 (v6.30 — calendar form people list scrolls on mobile, with search)

- `templates/calendar_entry_form.html`: the "Who is on it" list gets a `#people-search` box that filters the checkboxes by name (client-side; ticked people stay ticked when hidden) and a "No one matches." line.
- `static/css/calendar.css`: scrolling moved from the `.cf-checks` grid to a new `.cf-checks-scroll` wrapper (`overscroll-behavior`, `touch-action: pan-y`) so it works inside the fieldset on mobile; calendar.css cache-buster `20261014a`.
- **Version bump:** `APP_VERSION` 6.29 → 6.30.

## 2026-10-13 (v6.29 — room line on the calendar item form, one flow end to end)

- `templates/_room_chip.html` (shared by `/create` and `/calendar/new|edit`); `room_chip.js` finds the date / venue / format / start / end fields through `data-*` attributes and makes the hours follow the item's start and end times.
- `calendar_routes.py`: `_room_precheck` before saving, `_room_after_save` after (never fails the item), edit never files a second request, `_room_link` banner on the item page and edit form, `link_after_create` carries the room to the new activity, `/create?from_entry` shows an existing room as linked.
- `rooms.py`: `request(calendar_entry_id=...)`, `reservations_for_entry`, `link_entry`, `entry_room_status`; `activity_room_status` and the new one share `_room_status` (nouns, release reason, standby wording); `linked_to` for Approvals and My reservations.
- `office_calendar._fold_linked_rooms` folds a room into its activity **or calendar item** (repeating items match on the occurrence holding the day); the `.ics` feed follows the same rule.
- Alignment: standby shown on My reservations, in Approvals and in the new-request notice; `/rooms/{id}/move|withdraw|take` may return to `/calendar/entries/…`.
- Tests: `tests/test_calendar_entry_room.py`.
- **Version bump:** `APP_VERSION` 6.28 → 6.29.

## 2026-10-13 (v6.28 — standby room requests, one calendar item per activity+room)

- `office_calendar.py`: a room reservation linked to a CSS activity (`event_id`) is folded into the activity item (room hours as the time note) instead of drawing twice; the personal `.ics` feed skips the duplicate too.
- `room_reservation.standby` (new column, migrated): a **provisional** request for hours already booked or closed. `rooms.request(..., standby=True)` / `precheck(..., standby=True)`; stored as standby only when something is really in the way.
- `rooms.confirm_standby`: Administrative Section confirms it atomically, releasing the held booking(s) with a required reason (blocked hours still need reopening first). `POST /rooms/{id}/decide` action `confirm_standby`.
- UI: standby tick on the Add activity room chip (shown only when some hours are taken) and on `/rooms`; badge and "Confirm standby" button in Approvals; calendar flag "provisional (standby)".
- A multi-day activity gets a "room Thu 7 Mar 09:00–11:00" flag instead of a time note on every day; the `.ics` feed drops a linked room only when it falls inside its activity's dates.
- Tests: Approvals standby card + `confirm_standby` route, `/rooms` standby tick, Add activity standby save, closed hours refuse confirmation, feed day-mismatch.
- **Version bump:** `APP_VERSION` 6.27 → 6.28.

## 2026-10-10 (v6.26 — email the pinned update to registrants)

- Manage page, "Pinned update" card: an opt-in **Also email registrants** checkbox (off by default, disabled when email is unavailable or nobody has an email). Result messages explain what happened (sent / left out by the cap / cooldown / email off / nobody to email).
- `app.py` `_queue_update_emails` + `POST /activities/{token}/announcement`: emails each non-purged registrant **with an email on file** (everyone else is skipped silently), each with their own `/resume?rt=` link, sent after the response via `_send_update_batch` / `_send_and_log("event_update", …)`.
- Guards, all stamped **before** the background send: per-activity cooldown `UPDATE_EMAIL_COOLDOWN_MIN` = 15 (app_setting `event_update_email.<event_id>`), and a daily cap `UPDATE_EMAIL_DAILY_CAP` = 300 across all activities (app_setting `event_update_email_quota.<date>`), a slice of the relay's ~1500/day (docs/MAIL_RELAY_SETUP.md). Registrants over the cap are left out and the organizer is told how many. Removing an update or posting without the box ticked never emails.
- `mailer.py`: `event_update_message` (update text HTML-escaped, newlines kept), new `event_update` entry in `FEATURES` (Admin → Email on/off) and `_PREVIEWS`.
- Audit: `event_update_emailed` with the recipient count.
- `tests/test_update_email.py` (13 tests).
- **Version bump:** `APP_VERSION` 6.25 → 6.26.

## 2026-10-10 (v6.25 — stop accepting guessable attendee ids)

- **Security:** `?att=<id>`, the per-event recognition cookie, the rating form's hidden `att`, and the certificate link used to carry the raw attendee id. Anyone could open a registrant's page, download their named certificate, or file feedback as them by changing the number (or forging the cookie). All four now carry a signed token instead; raw integers are ignored everywhere.
- `auth.make_attendee_token` / `verify_attendee_token`: a new "att" purpose, separate from the emailed resume token, so neither can stand in for the other. Valid 400 days from issue, independent of the activity's dates, so re-registering with the same email always restores access even after the resume link's last-day + 30 days has passed.
- `app.py`: `_att_token`, `_attendee_from_token` (scoped to the activity), `_cookie_attendee`; used by `event_link_tree`, `_resolve_attendee` (certificate), `rating_form` / `submit_rating` (a forged or legacy value is dropped, so the rating is recorded unattributed), `event_consent`, `event_resume`, `event_email_link`. The certificate-ready email link is signed. `link_tree.html` / `thanks.html` pass the token.
- **Compatibility:** old certificate links with an integer `att` and old cookies holding an integer stop working; the person registers again with the same email and is resumed (no duplicate).
- `tests/test_att_hardening.py` (12 tests); existing tests now read the token instead of an integer id.
- **Version bump:** `APP_VERSION` 6.24 → 6.25.

## 2026-10-10 (v6.24 — organizer QR card and link validity on the roster)

- `activity_manage.html` / `_manage_ctx`: the "participant page" card shows a QR of the public link (custom slug when set, via `_qr_data_uri`) with a Download QR button, and explains how it differs from each participant's personal link.
- `monitor_event.html` / `monitor_event`: the roster header states the date until which personal links work (`_link_valid_until`, shared with the participant page; hidden for undated activities).
- `tests/test_event_hub.py`: three more tests (poster QR, custom-slug filename, roster validity date).
- **Version bump:** `APP_VERSION` 6.23 → 6.24.

## 2026-10-10 (v6.23 — event page as a registration hub)

- `link_tree.html` / `i18n.py`: the public page now reads as registration ("Register for this activity"). A benefits list and email help line were added, and the old sign-in/thanks/dupe/consent strings were reworded (EN + FIL).
- Save-your-link panel in the registered view: signed `/resume?rt=` link + inline QR (`_qr_data_uri`), copy/share/download buttons, collapsed on later visits (`?new=1` after a first registration opens it). It renders **only for a device recognized by its cookie**, never for a bare `?att=`. New `POST /e/{token}/email-link` (cookie-only, `email_link` rate bucket 5/h, 15-min per-address cooldown from `email_log`; reuses the `registration_confirmed` email feature). `mailer.registration_confirmed_message` reworded.
- Feedback is held until the activity's first day: `_feedback_state` / `_rating_gate` gate the page tiles **and** `GET`/`POST /r/{token}` (forms with their own `open_at` keep their window; undated and outside activities are ungated). `st.get_event_forms` now also returns `open_at`/`close_at`.
- Personal-link lifetime = activity last day + 30 days: `auth.verify_recovery_token(..., expires_at=)` (default 90-day path unchanged for other callers); `event_resume` uses it, the recognition cookie lasts at least as long, and an expired link redirects with `?expired=1`.
- Pinned update: `event.announcement` / `announcement_at` columns, `POST /activities/{token}/announcement` (+ manage card), shown above the page content for registered participants (plain text, 1000-char cap).
- `tests/test_event_hub.py` (21 tests); `tests/test_registration_dedup.py` now keys "recognized" on the start-fresh link and the `?expired=1` redirect (its events are a year out, so feedback is intentionally hidden).
- **Version bump:** `APP_VERSION` 6.22 → 6.23.

## 2026-10-10 (v6.22 — faster profile photos)

- `app.py` `/photo/{rp_id}`: adds an `ETag` (304 on `If-None-Match`) and `Cache-Control: private, max-age=300` (was `no-cache` with no validator, so every page view re-downloaded every ~100 KB photo). New `?s=64|128|256` returns a memoised JPEG thumbnail; other values return the original.
- Small avatar `<img>`s (`_faces.html`, `_calendar_body.html`, `office_connect.html`, `directory.html`, `link_tree.html`) now request `?s=128`/`?s=64`; calendar/Office Connect/directory avatars also get `loading="lazy" decoding="async"`.
- `static/js/sw.js`: `/photo/<id>` (any `?s=`) is now stale-while-revalidate (instant from cache, refreshed behind; capped at 300 entries; a 404 evicts the cached copy). `CACHE_VERSION` v2.19-b → v2.20-a. `tests/test_pwa.py` covers it.
- `tests/test_routes.py`: ETag/304, thumbnail size, fallback and 404 coverage.
- **Version bump:** `APP_VERSION` 6.21 → 6.22.

## 2026-10-10 (v6.21 — home companion roams, chases the cursor and can be dragged)

- `templates/office_connect.html`: the companion sits in a new `.oc-pet-stage.av-play` area in the hero and is rendered with `drag=true, chase=true`, so the existing roaming engine runs there.
- `templates/_avatars.html`: `avatar()` macro gains `drag_key` and `chase` params (`data-drag-key`, `data-chase`); new `av-chasing` / `av-pounce` animations.
- `static/js/avatars.js`: per-avatar drag position key; new cursor-chase loop (mouse only, honours reduced motion, sleep, petting and dragging); roaming pauses while chasing.
- **Version bump:** `APP_VERSION` 6.20 → 6.21.

## 2026-10-10 (v6.20 — hide "Manage the room" nav from non-Administrative-Section admins)

- `app.py` `_cap_ok`: the `room_admin` cap no longer admits `admin`-role accounts; it follows `room_approver` (Administrative Section) only, matching `rooms.is_room_admin`. Hides Room requests / meals / closures from the Office menu and the door display / QR poster from search.
- `tests/test_search.py`: asserts an admin-role account outside the section sees only "Reserve".
- **Version bump:** `APP_VERSION` 6.19 → 6.20.

## 2026-10-09 (v6.19 — remove growth panel from My profile)

- `templates/me.html`: removed the "How <companion> grows" panel and its now-unused `growth` import/`growth_defs()` call. The home page panel is unchanged.
- **Version bump:** `APP_VERSION` 6.18 → 6.19.

## 2026-10-09 (v6.18 — "Change companion" deep-links to the companion section)

- `templates/office_connect.html`: "Change companion →" now links to `/me#companion`; "Your profile →" and the photo/greeting card still go to `/me`.
- `templates/me.html`: the "Your companion" panel gets `id="companion"` and `scroll-margin-top:5rem` so the sticky header doesn't cover its heading.
- **Version bump:** `APP_VERSION` 6.17 → 6.18.

## 2026-10-09 (v6.17 — conference room: Administrative Section members only)

- `rooms.is_room_admin` no longer admits a section's temporary OIC or `admin`-role accounts; only members of the Administrative Section (`…/ADMIN`) can decide requests, order and tag meals (Requested, Delivered, Not delivered, Cancelled), and manage closures. `rooms_notify.approver_accounts` drops the same two groups, including the admin-role fallback when the section is empty.
- Tests: new `join_admin_section` helper; the OIC and admin-role cases now assert they are refused.
- **Version bump:** `APP_VERSION` 6.16 → 6.17.

## 2026-10-09 (v6.16 — the Office calendar gets its own Calendar menu)

- **`app.py`** — `NAV_GROUPS`: the `calendar` item moved out of **Office** into a new one-item **Calendar** group between Office and Administrator. Office now holds only the conference room (Reserve / Manage the room). Search palette section and scope for `/calendar` become "Calendar".
- **`tests/test_search.py`** — group order and Office/Calendar membership assertions updated.
- **Version bump:** `APP_VERSION` 6.15 → 6.16.

## 2026-10-09 (v6.14 — "Classic home" on /start goes to the landing page)

- The "Classic home →" link on `/start` pointed at `/css` (the CSS hub); it now points at `/`.
- **Version bump:** `APP_VERSION` 6.13 → 6.14 in `version.py` (#231 merged without one).

## 2026-10-09 (v6.13 — phone menu: Display settings behind a ⚙ in the footer)

- The Display accordion is gone from the scrolling nav list. A ⚙ button sits beside My profile / Page tour / Full guide in the pinned footer; it opens the same Theme / Accent / Text size / Density panel upward over the nav list, so the footer and Log out never move or grow. It closes with the sheet.
- Checked in Chromium at 360, 390 and 430px (light, dark, contrast): panel fits above the footer, theme switching works, Log out stays on screen.
- Cache-bust: `?v=20261009f`.
- **Version bump:** `APP_VERSION` 6.11 → 6.13 in `version.py`. #232 (v6.12) merged without a bump, which makes the deploy workflow abort (`CSS_DEPLOY_STRICT_VERSION`), so the sheet menu was never deployed; this bump ships both.

## 2026-10-09 (v6.12 — phone menu is a right-side sheet, Log out always visible)

- **Bug:** the ☰ menu was a dropdown capped at `100vh`, which on iPhone Safari is taller than the visible area, so the bottom (Log out) sat behind the browser toolbar; it was also one long flat list with the Display controls (~400px) always open.
- **Now (≤900px):** a full-height right-side sheet (`100dvh`, safe-area padding) over a dimmed backdrop. Header with ✕; the nav groups are accordions (only the current page's group opens); Display is a collapsed row; a pinned footer holds username · role, My profile / Page tour / Full guide, and **Log out**, so it never scrolls out of reach. Closes on ✕, backdrop tap or Esc (focus returns to ☰); page scroll is locked while open; touch targets are 44px; the floating feedback button is hidden while the sheet is open.
- Checked in Chromium at 360, 390 and 430px (light, dark, contrast): Log out fully on screen at each. Desktop menus untouched.
- Cache-bust: `app.css` and `app.js` `?v=20261009e`.

## 2026-10-09 (v6.11 — header and home hero on phones and tablets)

Checked in Chromium at 320–1440px against the real `app.css` and `dash_layout.html`.

- **Phone hero bug:** the phone rule that caps the companion (`.oc-pet .avwrap > span { height:151px !important }`) also matched the companion's hidden name label, turning it into an invisible 151px block. That is the large blank gap under the companion, which pushed Team / Me / Calendar down by about 150px, and it left "Change companion →" beside the art instead of under it. The rule now targets only `.av-tiltstage`, and the link is a block.
- **Phone header (≤640px):** one 57px row — logo, search, bell, ☰ (was two rows, 97px). ⚙ display settings, the ? help menu and Log out are hidden in the bar and live in the ☰ menu (a "Take a tour of this page" button, "Open the full guide", a Display section, Log out). The ⚙ controls are one `display_settings()` macro used by both the popover and the menu; `app.js` already binds them by delegation, so both copies stay in step. ≤359px also drops the logo mark.
- **Tablet header:** the hamburger now starts at ≤900px (was ≤780px) with ☰ last, and the "username · role" chip is hidden below 1180px (it repeats the greeting). One row at every width from 320px to 1440px; before, 781–1100px wrapped to 90–128px.
- **Send feedback button (≤640px):** icon-only 44px round button (`.sf-lab` hidden; the aria-label is unchanged), on `dash_layout` and `public_layout`.
- **Home search:** on a phone the placeholder becomes "Search or ask a question…" (the long one was cut off mid-word).
- Cache-bust: `app.css?v=20261009d` on both layouts (`public_layout` was still on `20261008a`).

## 2026-10-09 (v6.10 — sweep: phones, accessibility, telemetry, help)

`docs/HOME_SEARCH_ASSISTANT_PLAN.md` Phase 8, and the whole feature (v6.3 to v6.10):

- **What it is:** the home page has one box that searches people, colleagues, pages, your calendar, to-dos, requests, room bookings and help, and that answers questions in place; the header magnifier opens the same search on every page and on phones; `/css` keeps a CSS-only search with a way out to search everything; `/people/{id}` is a small colleague card with basic status (an admin can limit it to each person's own team on `/admin/work-arrangement`); the assistant answers about to-dos, approvals, wellness hours, AWA, who is in the office and the conference room, with the model switched off too.
- **Phone check** (Chromium, 390x844): no horizontal scroll on `/`, `/css`, `/start` or a colleague card; the header magnifier opens the palette; the results stay inside the viewport when the screen is short (the keyboard up). The floating "Send feedback" button used to cover the bottom of the results, so it is hidden while the home box's list is open (`:has()`; the same trick `rooms.css` uses).
- **Accessibility:** the inline box is a combobox (`role`, `aria-autocomplete`, `aria-expanded` kept in step with the list, `aria-controls`); the palette already was; the assistant's answer box and card are `aria-live="polite"`.
- **Telemetry:** `csi:search` now also carries result counts per section (a fixed vocabulary, counts only, never the term); a new `ask` event (`fired`, `answered`/`kind`, `fallback`; never the question) is sent by `assistant.js` for the box and `/start`. `/admin/ux-insights` shows both. The server drops anything outside the vocabularies and any text on an `ask`.
- **Help:** `tours.py` gets a `home_page` tour (the box, the assistant, the colleague card) and a clearer CSS-hub search step; `/` now has a page key so the tour replays with `?tour=1` — it auto-shows once per device, like every page tour. The guide lists it as "Home page" and the CSS hub as "CSS hub".
- **Speed:** `docs/PERFORMANCE.md` section 8: p95 15 ms on the demo DB and 70 ms on a 150-staff / 1,500-entry synthetic load (target 150 ms).
- Tests: `tests/test_search_telemetry.py`.

## 2026-10-09 (v6.9 — one box: search and ask together)

`docs/HOME_SEARCH_ASSISTANT_PLAN.md` Phase 7. `person_status` (item 3, optional) is not built: it is its own change (a model-supplied argument that has to be validated against the directory) and can be v6.10.

- **`static/js/assistant.js` (new):** `window.CSSAssistant.ask(q, mountEl, opts)` — the `/api/ai/route` call, the answer / navigate / action / Confirm cards and the 👍/👎 posting, moved out of `start.js` unchanged. `opts`: `statusEl`, `timeoutMs`, `autoNavigate`, `onFallback(raw)`, `onSettled(kind)`. State is per mount, so `/start` and the search box don't share a pending query.
- **`static/js/start.js`:** now a thin caller (supplies the keyword-palette fallback and the "maximize" timeout). `/start` behaves as before; its existing tests pass untouched. Loads `assistant.js` first.
- **`static/js/search.js`:** on an unscoped box (the home box and Ctrl-K), a question-like query (ends in `?`, starts with who/what/when/where/how/is/am/do/does/can/sino/ano/kailan/saan/ilan/may, or is four words or more) gets a first row `✨ Ask: “q”`. Choosing it renders the answer card in a box at the top of the dropdown, `aria-live="polite"`, with the normal results underneath; navigate cards there don't auto-navigate. On a fallback reply the row and box are dropped. `window.CSSSearch.looksLikeQuestion` is exposed for tests.
- **`/admin/ai`:** the post-login landing setting now says the home page carries the assistant too. `ai_landing_default` is unchanged.
- **Styles:** the card and 👍/👎 styles moved from `start.html` into `app.css` so the dropdown has them. Cache-busts: `app.css`, `search.js`, `assistant.js`, `start.js`.
- Tests: `tests/test_home_assistant_box.py` (the heuristic is run under node when it is installed).

## 2026-10-09 (v6.8 — the assistant answers about the whole office)

`docs/HOME_SEARCH_ASSISTANT_PLAN.md` Phase 6. Same pattern as `calendar_answers`: the model only picks a slot key; the server writes the sentence from the asker's own data, so names and records never reach the model.

- **`office_answers.py` (new):** nine slots — `todo_summary` (`home_tasks` titles only, in order), `approvals_waiting` (`pending_approval_counts`), `wellness_left` (`wellness_hours_used`, `WELLNESS_WEEKLY_HOURS`, next approved break), `awa_status` (the `_task_awa` calls plus the period's deadline), `office_today` / `wfh_today` (`colleague_status_for`, so the admin's bureau/team switch applies; first names per state, six at most, then "…and N more"; a weekend or holiday reads "not a working day"), `room_today` / `room_tomorrow` (`rooms.slot_states` → free windows; "closed" on a non-working day), `my_room_bookings` (`rooms.list_for_user`). Merged into `AI_ANSWER_SLOTS` right after the calendar slots; `MAX_LINES = 6`.
- **Seed rules (`app._seed_office_rules`, marker `office_rules_seeded`):** one exact-match rule per phrasing, English and Tagalog/Taglish ("sino ang nasa opisina", "free ba ang conference room bukas", "ilan oras wellness ko"), so these answer with no model call and while AI is off.
- **Router prompt:** one sentence naming the new topics; no data in it.
- `office_answers.py` added to `deploy_hf.RUNTIME_PY`. Tests: `tests/test_office_answers.py`.

## 2026-10-09 (v6.7 — colleagues and their basic status)

`docs/HOME_SEARCH_ASSISTANT_PLAN.md` Phase 5. A deliberate widening of who can see whom, built narrowly and switchable.

- **`storage.basic_status_for_day(conn, day) -> {user_id: state}`:** `state` is exactly one of `onsite`, `wfh`, `field`, `leave`, `off`, `unknown`. Reported status beats a calendar trip beats the fortnight's filing, through a new shared helper `_wa_person_day` that `work_arrangement_day` (the team page) now also calls, so the two cannot disagree. A weekend or a holiday is `off` for everyone. Read from an unscoped roster of linked staff; memoized 60 s per (database, day) (`basic_status_clear_cache`). No note, remarks, place, leave type or reason, arrangement label, `undeclared` or `plotted` ever leaves it.
- **Admin switch:** setting `colleague_status_scope` (`bureau`, the default, or `team`), on `/admin/work-arrangement`; `colleague_status_for(conn, viewer, day)` applies it with `team_scope_for_user(area="awa")`, so in `team` an unlinked account sees no status.
- **Search:** a `Colleagues` source (scope `all` only) matching name, nickname, position or unit, five at most, an exact first name or nickname first. Hint: `Position · Unit · In the office today` (or `no status`). Links to `/people/{user_id}`.
- **`GET /people/{user_id}`:** signed-in only; 404 for an unknown or unlinked id. Photo or initials, name, position, unit, today's basic status, who is away in the next seven days (from the calendar as the viewer; a trip's title and a leave's reason are not shown), a shared birthday, and a birthday-card link when one can be sent. No email, phone, notes, filing history or wellness data.
- **Unchanged:** `/work-arrangement/day`, the roster, and the home "in the office today" card stay team-scoped. Tests: `tests/test_colleague_status.py`.

## 2026-10-09 (v6.6 — search the rest of the office)

`docs/HOME_SEARCH_ASSISTANT_PLAN.md` Phase 4. Five new `search_sources` sources, scope `all` only (the `/css` box never shows them); each calls the function behind the page it links to, as the signed-in person.

- **Calendar:** `office_calendar.items_between(scope="blend", layers=["entries","activities"])` from 30 days back to 90 ahead, minus banners, cancelled and postponed; title match; five at most, nearest date first (upcoming before past). Hint is date, time and "tentative" only — never notes, a meeting link or a leave reason. Links to the entry (`/calendar/entries/{id}`) or the activity's own link, else `/calendar`.
- **My to-do:** `office_connect.home_tasks`, title + detail, task `url`.
- **My requests:** the person's own `list_my_wellness_claims`, and the current open period's pending or approved work arrangement. Never another person's, whatever the role.
- **Conference room:** the person's own upcoming `rooms.list_for_user` reservations (link `/rooms/mine`), plus a fixed "Book the conference room" row (`/rooms`) when the query mentions room, conference or book.
- **Help:** `help_catalog_for(user, is_chief)` (passed in through `ctx`), label + step text, linked with `?tour=1`.
- Queries under 2 characters search nothing. Tests: `tests/test_search_sources.py`. `/api/search` p95 15 ms on the seeded DB.

## 2026-10-09 (v6.5 — /api/search is a list of sources)

`docs/HOME_SEARCH_ASSISTANT_PLAN.md` Phase 3. A refactor: responses and order are unchanged.

- **`search_sources.py` (new):** each source is `{key, section, scopes, run(conn, user, terms, ctx)}`; Activities and People moved in with identical queries and limits. `ctx` passes `get_atoms`, `view_memo`, `humandate`, `is_chief`, `today` in from `app.py`, so the module never imports `app`.
- **`api_search`:** loops `run_sources` for the scope; each source runs inside try/except with a log line, each section is capped at 5 rows and the response at 30.
- **Rate limit:** `search` bucket, 120 per 60 s, keyed by account id; over the limit the answer is `[]`.
- `search_sources.py` added to `deploy_hf.RUNTIME_PY`. Tests: `tests/test_search.py`.

## 2026-10-09 (v6.4 — CSS-only search on /css)

`docs/HOME_SEARCH_ASSISTANT_PLAN.md` Phase 2.

- **Index (`app.search_index_for`):** every entry carries `mod` — the nav group's name lower-cased (`css`, `wellness`, `awa`, `administrator`); the three fixed entries are `core`.
- **`search.js`:** `attach({scope})` (read from `form.dataset.scope`); a scoped box ranks only entries with a matching `mod` and sends `&scope=` to `/api/search`. The last row is always "Search everything for “q” →", which opens the global palette with the query via `window.CSSSearch.openPalette(q)`. Header comment no longer claims comments are searched. Cache-bust `?v=20261009b`.
- **`/api/search`:** takes `scope` (`all` or `css`; anything else is `all`). Both sources are CSS today, so results are unchanged.
- Tests: `tests/test_search.py`.

## 2026-10-09 (v6.3 — search and assistant on the home page)

`docs/HOME_SEARCH_ASSISTANT_PLAN.md` Phase 1.

- **Shared macro (`templates/_search_box.html`):** `search_box(placeholder, scope, tour)` renders the `form.gsearch` markup with `data-scope`. Used by `/` (scope `all`) and `/css` (scope `css`).
- **Home (`office_connect.html`):** the box sits after the hero and birthday blocks, before "Your to-do", with a "✨ Ask the assistant" link to `/start`. Not rendered in the Calendar tab.
- **Header:** `#navSearchBtn` (magnifier) in `dash_layout.html` for signed-in users; `search.js` already wired it, so phones can now open the palette. The "Ctrl K" hint is hidden on touch and narrow screens.
- **CSS hub (`home.html`):** heading is "CSS hub"; the assistant link moved to the home page. Both boxes carry `data-tour="search"` (the `home` tour only runs on `/css`).
- `.try-assistant` styles moved to `app.css`. Tests: `tests/test_search.py`, `tests/test_landing_fork.py`.

## 2026-10-09 (v6.2 — birthday cards from teammates)

`docs/BIRTHDAY_GREETINGS_PLAN.md` Phase 3.

- **Module (`birthday_cards.py`, a second `APIRouter` like `calendar_routes.py`):** `/birthday/cards` (who you may send to), `/birthday/card/{id}` (form + send), `/me/cards` (cards you received) with `POST /me/cards/{id}/hide`, and `/admin/birthday-cards` with `POST .../hidden` (gated by the `/admin` prefix and checked again in the handler).
- **Eligibility (`office_calendar.card_celebrants`):** a celebrant inside the greeting window (six days before, and the day) who shares their birthday with the sender (`birthdays.shared_with`); never yourself; "Don't share" gets none.
- **Storage (`birthday_card`, `storage.card_*`):** unique per (celebrant, sender, birthday year); six designs; plain text, 280 characters, blank-line squeeze; cards for years before last are deleted as new ones are sent. Hidden flag for moderation.
- **Held until the day (`birthdays.revealed_card_year`):** the celebrant reads this year's cards only from the morning of the birthday. The landing page links to them on the day ("May N card para sa iyo"); `/me` shows a link while there are any.
- **Bell (`office_calendar.card_bell_row`):** "Send X a birthday card (Sat)" straight to the form, or "N birthday cards to send this week" to the list. Cheap guard query first; same switch as the other teammate-birthday reminders.
- **Safety:** HTML-escaped on output, `ratelimit` bucket `card` (20/min, keyed by account), audit records "sent a birthday card" with no message, no date. `birthday_cards.py` added to `deploy_hf.RUNTIME_PY`. Tests: `tests/test_birthday_cards.py`.

## 2026-10-09 (v6.1 — birthday greeting on the landing page)

`docs/BIRTHDAY_GREETINGS_PLAN.md` Phase 2.

- **Landing page (`app._birthday_greeting`, `office_connect.html`):** replaces the old `is_birthday` flag. The six days before a birthday show "Malapit na ang kaarawan mo" with when it falls; the day shows "Maligayang kaarawan" / "Happy birthday!". Never after. The first view of each phase also shows a bilingual card (same message as the email for the day; confetti off under `prefers-reduced-motion`; × hides it in the browser), then only the heading. A line under the companion says it is celebrating too.
- **State (`admin_user.bday_greeted`, guarded ALTER):** `year*10 + 1` (lead-in) or `+ 2` (the day), set when the card first renders. A failure to record it is logged and never breaks the page.
- **Rules (`birthdays.lead_in_phrases`):** "bukas / tomorrow", "sa Sabado / on Saturday".
- Tests: `tests/test_birthday_greeting_signin.py`.

## 2026-10-09 (v6.0 — birthday greeting email)

`docs/BIRTHDAY_GREETINGS_PLAN.md` Phase 1.

- **Rules (`birthdays.py`):** `next_occurrence`, `days_until`, `greeting_phase` (`today` / `before` / `none`, six days before and never after) and `email_send_date` (the birthday, or the last working day before it).
- **Email (`mailer.birthday_greeting_message`, `GREETING_POOL`):** 12 bilingual (Tagalog and English) messages signed "From all of us at BLHSD", picked by `user_id + year`. No date, no age. Name is HTML-escaped.
- **Job (`send_reminders.send_birthday_greetings`, job `birthday_greeting`, `--birthday-greeting`):** to every active account with a birthday on file, on the send date, once per year (email log, subject carries the year), never after the day. No per-person opt-out; the `/admin/email` switch (`job_birthday_greeting`, with preview) is the kill switch. Tests: `tests/test_birthday_greetings.py`.

## 2026-10-09 (v5.9 — conference room reservation R10: the door display and repeat-weekly requests)

- **Door / TV display.** `/rooms/display/<secret>` (no sign-in; a signed-in person can use `/rooms/display`): "In use now" or "Free until ...", "Next", today's schedule (a multi-hour booking is one line), the time,
  and a QR to `/room`; "Closed" for weekends, holidays and whole-day closures. Dark, large type for 1920x1080, one column on a portrait tablet; reloads itself every 60 s and ticks its own clock; never cached or indexed.
  Only approved bookings are shown. The secret is made on first visit to the **Door display** tab (section members) and **Make a new address** kills the old one at once; "Show meeting titles and who booked" can be
  switched off, leaving only "Reserved" and the hours.
- **Repeat weekly.** In the request panel: Repeat every week / every 2 weeks until a date (at most 12 dates). `rooms.plan_series` checks every date first (notice, weekends, holidays, closures, booked hours);
  if any can't be had the page lists them with the reason and files nothing until "Request the N dates that work". The dates share a `series_id`. The section is told once for the whole series ("+4 more dates"),
  the Approvals card offers **Approve all N / Decline all N** (a date something else holds is skipped and reported, never forced) as well as each date alone, the requester hears once, each date gets its own
  meal form, and My reservations shows "Repeats: N dates" with **Withdraw the whole series** (today onward).
- Tests: `tests/test_rooms_series.py`, `tests/test_rooms_series_pages.py`, `tests/test_rooms_display.py`.

## 2026-10-09 (v5.8 — conference room reservation R9: meals, from the form to delivery)

- **The form (`rooms_meals.py`, tables `room_meal` + `room_meal_item`):** 1. Title of the Activity (from the reservation), 2. Number of Pax, 3. Special Request for Meals, 4. Breakfast / AM snack /
  lunch / PM snack, each Yes or No **with its requested delivery time**. It is prepared when "Will meals be requested?" is ticked (or later, from My reservations -> Request meals): each meal starts as Yes
  when the booked hours include its hour (07, 10, 12, 15 — change with the `room_meal_times` setting) and with its usual time (07:30, 10:00, 12:00, 15:00). The requester corrects it at
  `/rooms/meals/<id>` (guests at `/room/t/<token>/meals`); times must be 06:00–19:00 and pax is needed if any meal is Yes. A printable A4 PDF (`room_meal_form.py`) carries the same fields.
- **The Administrative Section's page (`/rooms/meals`, tab "Meals" with a count of meals still to request):** every filled-up form to order from, by date, with pax, the special request and one line per
  wanted meal. Each meal is tagged **Requested** (needs the room approved), then **Delivered**, **Not delivered** (both only on or after the day) or **Cancelled**, each with an optional note, who and
  when; Undo / Reopen fix a slip; "Mark everything still pending as requested" does a whole form. Filters: dates, "needs ordering or tagging" vs everything, and rooms still awaiting approval.
- **Changes after ordering:** the requester can edit only until ordering starts, then asks the section; the section can edit any time, and a meal whose time or yes/no they change goes back to "Not yet
  requested". A change after approval raises a "meal form was changed" notice (bell + email) to the section; an approval with meals raises "a meal form is ready to order".
- **When the booking goes away** (withdrawn, declined, bumped, closed, expired, or moved): its pending / requested meals become Cancelled, and if any were already Requested the section is told to cancel with
  the supplier. Delivered meals are never rewritten. A moved booking's new form copies the old one.
- Tests: `tests/test_rooms_meals.py`, `tests/test_rooms_meals_pages.py`.

## 2026-10-09 (v5.7 — conference room reservation R8: CSS activities and the room, both ways)

- **From the activity form:** a collapsible "Conference room" line (works without scripts). `room_chip.js` fetches `GET /rooms/api/day` (signed in, staff
  rules: 2 working days, 90 days; hours only, never a title), shows free / others asked / booked / closed, and ticks "also reserve" for online and hybrid activities or a venue
  that says "conference room" (unless the person has already decided). The room is checked **before** the activity is saved (`rooms.precheck`), so a bad choice comes back as a form error;
  after saving, the request is filed tied to the activity (`room_reservation.event_id`, first day only) and never undoes the activity if it fails.
- **From a reservation:** My reservations -> "Create a CSS activity for this" opens `/create?from_room=<id>` filled in (title, date, format, venue "Conference room"); saving links the reservation
  to the new activity instead of filing a second request. Only its owner or a room approver; a reservation with an activity already, or no longer live, prefills nothing.
- **Banner on the activity's manage page** (bureau and outside), from `rooms.activity_room_status`: reserved / requested / **booked for a different day** (offers the move) / move waiting /
  **no room any more** (cancelled or declined: the owner can pick a suggested time, which keeps the activity's link) / **archived but still holds the room** (offers withdraw) / a prompt to reserve one.
  Buttons only appear for the booking's owner or a room approver; the buttons return to the activity page (`next` is restricted to same-site activity and room paths; messages travel as `roomerr` / `roomok`).
- **Moves:** an undecided request just changes day; an **approved** booking is kept and a `move` request is filed for the same hours on the new day. Approving the move releases the old hours in the
  same transaction (the old one is marked withdrawn "Moved to CR-..."); declining it leaves the old one; withdrawing the old one withdraws its pending move. The Approvals card says "Move of CR-...".
- Tests: `tests/test_rooms_activity.py`, `tests/test_rooms_activity_pages.py`.

## 2026-10-09 (v5.6 — conference room reservation R7: the Rooms layer on the Office calendar)

- **A `rooms` layer in `office_calendar.LAYERS`** (`kind: room`, 🏢, venue "Conference room", the booked hours as start/end time). An **approved** booking is
  bureau-wide information: every signed-in viewer sees it in every scope except "mine" (your own requests). A **pending** request is shown, as `tentative` /
  "awaiting approval", only to its requester and to the people who decide room requests. Withdrawn, declined, cancelled and expired never show. Colour = the
  requester's unit (grey for guests, whose label is "Guest · organisation"); a guest's name and contact details are never in an item.
- **Where it shows:** the Agenda and Month layouts (and the home page's Calendar tab), the Kind filter and the icon legend ("Conference room"), and
  `GET /api/calendar?layers=rooms` (opt-in: the default layers are unchanged). It is deliberately **not** in the Week and Timeline layouts (who is where, not
  what is booked), nor in the emails, the home "Coming up" card or the assistant's answers, which still ask for entries and activities only.
- **More menu:** "Reserve the conference room" opens the board on that week.
- **Personal feed and the approval email share one event:** your own bookings go into your subscribed calendar feed (`room-<id>@office-connect`; approved =
  confirmed, pending = tentative; withdrawn / cancelled / declined / expired in the last 30 days = `STATUS:CANCELLED` so the app drops them). The `.ics` attached to
  the approval email now uses the same event, so a calendar app never shows it twice, and its SEQUENCE rises when the booking changes.
- Tests: `tests/test_calendar_rooms.py`, `tests/test_calendar_rooms_pages.py`.

## 2026-10-09 (v5.5 — conference room reservation R6: the public QR page for guests)

- **`/room` (no login), permanent.** Short enough to print and type; `/rooms/poster` (section members) prints an A4 page with the QR, the address and three steps.
  The QR encodes `CSS_BASE_URL` + `/room`, so **set `CSS_BASE_URL` before printing** and never change that path. Pick a day from the next 60 days (each shows how many hours
  are open), see each hour as free / others asked / booked / closed (never a title or a name), then fill in the meeting and who you are.
- **Same rules as staff:** two working days' notice, back-to-back hours, approved by the Administrative Section from the same queue (guests are labelled, with an
  "email not confirmed" flag until they open their link; the flag never blocks an approval). Horizon is 60 days for guests, 90 for staff.
- **Tracking link (`/room/t/<signed token>`, 150 days).** The page they land on after sending is the same page the emails link to: status, history (no staff names),
  withdraw, and, after a cancellation or decline, the nearest free times (a bumped guest's pick is booked already approved). The token only opens guest reservations.
- **Abuse limits:** 5 requests an hour per IP (`CSS_RL_ROOM`), 120 availability look-ups a minute (`CSS_RL_ROOM_VIEW`), three open requests per email address, a hidden
  honeypot field (a bot's post is dropped and looks like success), and a required Data Privacy Act consent (timestamped).
- **Retention:** a guest's name, email and phone are removed 12 months after the meeting date and their email notices deleted; the booking stays. Runs once a day inside
  the scheduler tick, and as `python retention.py --room-guests [--dry-run]`.
- Guests also get a "request received" email (under the "Conference room decision result" switch). Tests: `tests/test_rooms_guest.py`, `tests/test_rooms_guest_pages.py`.

## 2026-10-09 (v5.4 — conference room reservation, R1 to R5)

The conference room, built in five increments (`docs/ROOM_RESERVATION_PLAN.md`). The notes below are the increments, newest first; their old version numbers (4.1 to 4.5) were folded into 5.4 when this was merged after the Calendar phases.

### conference room reservation R5: notifications

- **One table, one flush (`rooms_notify.py`, `room_notice`).** A state change only inserts notice rows (one per person per event, UNIQUE so nothing can double
  up); the bell reads them; the scheduler's once-a-minute `tick` emails the ones that owe an email. A booking never waits on the mail relay, a failed send is
  retried (three tries, five minutes apart), a feature an admin switched off is logged as skipped, and notices older than three days are not sent as news.
  With no mail transport or no `CSS_BASE_URL` the emails wait while the bell still works.
- **Requester:** approved / declined / cancelled (reason + the nearest free times) / booked for you / expired. Bell row until My reservations is opened.
  Approved and booked-for-you carry a `.ics`. Guests with an email get the same emails (no bell). You are never notified about your own action.
- **Section:** an email per new request with one-click Approve / Decline (signed, 14-day, confirm page, no state change on GET — `/rooms/decide/`);
  escalation to the Admin Head when a request has waited 24 h or its date is within 48 h; a morning summary of open requests (08:00); tomorrow's schedule with
  attendees and meals (16:00); a bell row and email for a withdrawal less than 24 h before the booking.
- **Reminders:** the afternoon before, to each person with a booking. Dropped if it was withdrawn in the meantime.
- **Expiry:** a request still undecided after its date becomes `expired`.
- Five new switches in /admin/email: room_new_request, room_decided, room_reminder, room_admin_alerts, room_digest (all on by default).
- Tests: `tests/test_rooms_notify.py`, `tests/test_rooms_notify_pages.py`.


### conference room reservation R4: encode, "Book anyway", closures, suggestions

- **Encode:** a section member books for an account or a named guest; approved at once (source `encoded`). Inside the 2-working-day notice a reason is required.
- **Book anyway:** booked hours show as selectable to section members only. The first submit changes nothing and lists who would be cancelled, with the
  alternatives each would be offered; the second (with a reason) books the new one and cancels the old ones in a single transaction, linked by
  `bumped_by_reservation_id`.
- **Suggestions (`rooms.suggest`):** same hours on the next free working days, then other hours the same day, then earlier days still ahead; holidays, weekends,
  closures and booked hours are skipped. A bumped person picks one and it is booked **already approved**; a declined person's pick is an ordinary new request.
  The server only accepts a time it would itself suggest right now, once per cancellation.
- **Closures** (`/rooms/blocks`): whole day or some hours, with a reason; booked hours in the way need a confirm and are cancelled with the reason.
- **Competing requests:** approving can decline the others for the same hours in the same transaction ("Also decline the N competing requests").
- "Needs a new time" section on My reservations. Not yet: the notices themselves (email and bell for the requester) - R5.
- Tests: `tests/test_rooms_bump.py`, `tests/test_rooms_bump_pages.py`.


### conference room reservation R3: approvers and the Approvals queue

- **Who decides:** `rooms.is_room_admin` — anyone in the Administrative Section (directory unit `…/ADMIN`, or beneath it), its temporary OIC, and the `admin`
  role as the always-there fallback. Chiefs who are not in the section do not get room requests.
- **Approvals inbox:** a third queue, "Conference room", on `/approvals` (also reachable to Administrative Section members who are not chiefs, who previously
  got a 403). Cards show requester (guests are labelled), date and hours, meeting, meals, and the *other* requests for the same hours.
- **Rules:** first to act wins and the second is told who; decline needs a reason; Approve is withheld when an approved booking already holds the hours;
  hours blocked after the request was made cannot be approved. Bell row "N conference room requests waiting on your decision"; a Requests tab on `/rooms`.
- Not yet: the email decide link (R5, with the emails that carry it), "Book anyway" and the competing-request dialog (R4).
- Tests: `tests/test_rooms_approval.py`.


### conference room reservation R2: availability board, request panel, My reservations

- **Pages:** `/rooms` (week grid of the twelve hourly slots, one request panel), `/rooms/mine` (your requests, with Withdraw). A "Conference room" item in the
  nav group beside the Office calendar.
- **Layout:** desktop shows the grid beside a sticky request panel (two weeks side by side from 1600px); laptops get the panel as a right-hand drawer; phones
  get one day at a time with a day strip and a full-screen request sheet. Cells always carry an icon and a word, never colour alone.
- **Picking hours:** click an hour, then another in the same day (or drag, or shift-click); the date / From / Until fields stay the source of truth, so the form
  also works typed by hand or with JavaScript off. Quick picks: Morning, Afternoon, Whole day.
- **Privacy:** an approved booking shows its title to signed-in staff; someone else's pending request shows only as a count.
- Not yet: the approval queue and notifications (R3, R5). Requests wait as "Requested".
- Tests: `tests/test_rooms_pages.py`.


### conference room reservation R1: the rules, no screens yet

First increment of docs/ROOM_RESERVATION_PLAN.md. Nothing visible to users yet.

- **Data:** `room_slot` (twelve one-hour slots, 07:00-19:00), `room_reservation`, `room_reservation_slot` and `room_block`. A partial unique index lets
  many people *request* an hour but only one reservation be *approved* for it, so two admins can never both win.
- **Rules (`rooms.py`):** request, approve, decline, withdraw; two working days' notice (holidays and weekends skipped); hours must be back-to-back;
  first admin to decide wins and a later one is told who; a decline needs a reason; only the requester can withdraw. Every change is audited.
- Tests: `tests/test_rooms_core.py`.
=======

## 2026-10-09 (v5.3 — admin birthdays from the Directory)

- **Directory (`POST /directory/person/{id}/birthday`, `staff_form.html`):** the Edit staff page has a Birthday card for admins with `manage_users`, with the same rules as `/admin/users/birthday` (admin consent notice, date never audited, blank month and day clears). Staff with no linked account see a note instead, since the birthday lives on `admin_user`. `_render_staff_form` now takes `msg` / `err`. The Users-page panel is unchanged. Test: `test_admin_sets_a_birthday_from_the_directory_edit_page`.

## 2026-10-09 (v5.2 — "Mine only" ignores the person who ran an import)

- **Scope (`office_calendar._in_scope`):** the creator clause of "mine" is skipped for entries with `source = 'import'`, because a bulk import stamps the importer as `created_by` on every row. Being listed as a person still counts. `created_by` is unchanged, so edit rights are unaffected, and "Mine + bureau-wide" still shows bureau-wide imports. The activities layer still counts the creator as mine. Test: `test_mine_ignores_the_person_who_only_ran_the_import`.

## 2026-10-09 (v5.1 — calendar legend and admin-entered birthdays)

- **Legend (`_calendar_body.html`, `calendar.css`):** Agenda and Month show "Colour = unit" (a swatch per unit in the window, same tones as the bars and dots) and "Icon = type". The kind-icon map moved to the top of the template so both layouts share it.
- **Admin birthdays (`POST /admin/users/birthday`, `users.html`):** an admin with `manage_users` can set, change or clear an active account's birthday and its sharing scope. The consent note records that an administrator entered it; the person can still edit or remove it. The audit log never holds the date. `storage.set_birthday` gained a keyword-only `notice`.

## 2026-10-10 (v5.0 — calendar Phase 5: accessibility and hardening)

`docs/CALENDAR_UX_PLAN.md` Phase 5. Found with axe-core (WCAG 2.0 to 2.2 AA plus best practice) run over every calendar view and state (agenda, month, week, timeline, empty, search, the add form, filters and More open, the item sheet, quick add) in three themes at 390 and 1440px: 72 runs, 90 problems in 6 rules at the start, none left except an open dropdown covering the button beneath it.

- **Grids (`_calendar_month.html`, `_calendar_week.html`, `_calendar_timeline.html`):** a `role="row"` may hold only cells, but the bars, day numbers and "+n more" were links placed directly in the row. They now share one cell-role wrapper (`.cal-layer`, `display:contents`, so layout is unchanged). The compact month's cell is the `gridcell` and holds the link (a link cannot carry that role). The timeline's day headers are header cells containing the add button (a button cannot carry the header role). The empty corner header of Week and Timeline is named "Person".
- **Contrast and size:** out-of-month days fade by colour, not opacity (the number was under 4.5:1), the "+n" in a faded compact cell stays at full strength; bars and "+n more" are at least 24px tall (WCAG 2.2 target size).
- **Structure:** today's section carries `aria-current="date"`; the empty state's heading is an `h2` (it skipped a level).
- **Large text:** at 150% and 200% text the Whose menu, the open Filters panel and the Earlier / Today / Later links widened the page; they now wrap and shrink. Checked on every calendar page, including the menus open, at 390 and 768px.
- **Keyboard (checked in a browser):** every calendar control shows a focus ring; menus open with Enter or Space and close with Escape back to their button; the item sheet and quick add are modal, keep focus inside and give it back to the item that opened them; the sheet is labelled by the item's title; reduced-motion switches off the card lift and the sheet slide.
- **Tests:** `tests/test_calendar_a11y.py` validates every grid row's children from the HTML (no browser needed) and pins each fix; 7 of its tests fail on the old templates. One more guards a bug the restructure introduced and only a screenshot showed (day numbers on the desktop month hidden under the bars, because the number row collapsed).
- **Smoke test (`qa_smoke.py`):** renders the calendar body for each kind of account across 11 layout / scope / filter / search combinations (22 on a two-account database), and honours `CSS_DB` like the app. With no accounts it warns instead of failing.
- **Screens:** 48 (6 widths x 4 views x light and dark) were checked for sideways overflow, script errors and a missing title or toolbar, none found. Kept outside the repo.
- Not a bug: while the More menu is open on a phone it covers the "Later" button beneath it, as any dropdown does.

## 2026-10-10 (v4.9 — calendar Phase 4: frictionless)

`docs/CALENDAR_UX_PLAN.md` Phase 4.

- **Search (`office_calendar.apply_filters`, `calendar_routes._filters`, `_calendar_body.html`):** a `q` box in the toolbar (max 80 characters) matches title, place, owning unit, tags and the names of the people on an item, case-insensitively. Visibility is unchanged: only items the viewer can already see are searched. In the agenda a search reads through the whole year (only days with a match; "earlier / later" step a year; range label "Search in 2026 · 12 matches"); in Week, Timeline and Month it narrows the grid. A removable "Search: …" chip shows it; "Clear filters" clears it too. Holidays are never removed by the menus; a text search keeps only the ones whose name matches.
- **Remembered view (`calendar_routes.with_pref / remember`, home handler):** a `cal_pref` cookie (`layout:scope`, httponly, SameSite=Lax, one year) fills in a **bare** visit (the Calendar tab, the menu link). Any URL that names a layout, scope, date, filter or search is used as written, so a shared link never changes under whoever opens it. A forged or stale value is ignored; a scope the person is not offered falls back to the default.
- **Item sheet (`calendar.js`, `_calendar_quick.html`):** tapping an item fetches its page, takes the `.cal-detail` article out of the parsed document (after removing `script/iframe/object/embed/link/style`) and shows it in a `<dialog>`: a side panel on a wide screen, a sheet from the bottom on a phone. `?item=ID` is added to the address, so Back closes it and a shared link opens it; "Open full page" is always there; a modified click (new tab) and any failed fetch go to the ordinary page. The script never builds HTML from a string (a test enforces it).
- **Add from where you are:** a `+` on every agenda day and the date numbers in the month grid open Quick add with that date filled in. Both are ordinary links or hidden until script runs, so nothing is lost without it.
- **Keyboard and touch:** ← → move, **T** today, **A** add, **S** search (not `/`: the app already uses `/` and Ctrl+K for its command palette). Keys are ignored while typing or while a dialog is open. On a phone, a mostly-horizontal flick over the agenda or month moves to the next or previous window; Week and Timeline (which scroll sideways) and vertical drags are left alone.
- Checked in Chromium on the real file's 379 items: the sheet opens, closes with Escape, Back and the backdrop, deep-links, and ignores junk or missing items; quick add from a day and from a month number creates an item; the keys, search, remembered view and swipe all behave; no script errors on desktop or phone. Found and fixed: `/` clashed with the app's palette (now **S**), and the phone `+` was 35px (now 44px).
- Left out on purpose: loading the calendar without a page refresh when you change view or filter (it still reloads, quickly), and an add button inside Week cells.

## 2026-10-09 (v4.8 — calendar Phase 3: a clearer look)

`docs/CALENDAR_UX_PLAN.md` Phase 3. Colours come only from the app's tokens, so light, dark, high-contrast, text size, density and every accent choice keep working.

- **Day header (`_calendar_body.html`, `calendar.css`):** a date badge (weekday over a large day number; today's is solid accent, weekends tinted), the day name, a Today tag, holidays as a red ribbon pill, and an item count.
- **Cards:** a time column (start over end, an "All day" label, or an AM/PM chip), a kind icon (meeting 👥, training 🎓, trip 🧳, audit/review 📋, notice 📣, deadline ⏰, activity ★), the title clamped to two lines (full title as a tooltip only when it is long), a quiet details line (unit, venue, people, tags), and Tentative / Postponed as pills. The title link is stretched over the whole card, so a tap anywhere opens the item. The full time range stays in the page as hidden text for screen readers.
- **Phones:** time and title share one line (a row less per item) and the unit name sits under the title.
- **Empty state:** one card with "+ Add something", "Look further ahead" and, when a filter is on, "Clear filters" (replaces the one-line hint).
- **Week and Timeline:** today's column is tinted and its header underlined. Month keeps its today ring and holiday labels.
- **Contrast:** three unit text colours were under 4.5:1 in the light theme (green 4.40, orange 4.49, grey 4.06) and are now 4.6+. `tests/test_calendar_contrast.py` reads the real stylesheets and fails if any calendar text pair drops below AA in the light, dark or contrast theme.
- Checked in Chromium on the real file's 379 items at 390 and 1440px in all three themes: no overflow, no clipped cards, no script errors; a tap on the right edge of a card opens it.
- Left out on purpose: a "now" line. The grids are by day, not by hour, so there is no time of day to draw it at.

## 2026-10-09 (v4.7 — calendar Phase 2: every screen size)

`docs/CALENDAR_UX_PLAN.md` Phase 2 (P2.1–P2.2).

- **Month on a phone (`_calendar_month.html`, `office_calendar.month_grid`):** below 761px a compact grid replaces the "needs a wider screen" note: the day number, up to four colour dots (one per distinct owning unit, from the bars drawn on that day), "+n" for the rest and a ★ on holidays. Every cell is a link to that day in the agenda and names itself for a screen reader ("Sunday, September 27: 0 items"). `month_grid` now returns `n` and `tones` per day; items hidden by the lane limit still count.
- **Agenda columns (`_calendar_body.html`):** the days sit in one `.cal-agenda` grid: one column below 1100px, two from 1100px, three from 1500px, in date order left to right. Long titles and meta wrap (`min-width:0`, `overflow-wrap`).
- **Week and Timeline:** the forced `min-width:52rem` is now `40rem` with a name column of `clamp(7rem, 14vw, 11rem)`; on a narrow screen the box scrolls sideways with edge shadows, the names stay sticky, and a "Swipe sideways" hint appears only when the box really scrolls (`calendar.js`).
- **Add / edit form:** `align-content:start` and `min-width:0` stop boxes stretching and overflowing; rows use `minmax(min(190px,100%), 1fr)`; under 480px From and To stay side by side and the note takes its own line; the date overlay has a fixed height and no italic, so Starts, Ends and Last date match.
- Checked in Chromium on the real file's 379 items at 360, 390, 768, 1024, 1440 and 1920px: no horizontal overflow on Month, Agenda, Week, Timeline or the form at any width; no script errors; 2 agenda columns at 1440, 3 at 1920; tapping a day on a phone opens its agenda; Week/Timeline names stay put while scrolling.
- Left out on purpose: a day-by-day Week list under 480px, and a mini-month pane beside the agenda. Multi-column agenda gives most of the wide-screen benefit for far less code; both can follow if wanted.

## 2026-10-09 (v4.6 — calendar Phase 1: calendar-only tab and a compact toolbar)

`docs/CALENDAR_UX_PLAN.md` Phase 1 (P1.1–P1.3).

- **Calendar-only tab (`templates/office_connect.html`, `app.py`):** `/?view=calendar` renders a slim header (title + the Team / Me / Calendar switch) and the calendar. No hero, companion, to-do list or "Coming up". The handler no longer builds `team_view_data`, `home_tasks`, `calendar_week_block`, wellness stats or the work-arrangement hint for that view (none is drawn); `team_linked` is a one-line scope lookup so the Team tab still shows for people who have a team.
- **Two-row toolbar (`templates/_calendar_body.html`, `static/css/calendar.css`, `static/js/calendar.js`):** row 1 = layout switch, **+ Add**, and a **⋯ More** menu (Quick add, Birthdays, Import from Word for admins); row 2 = one GET form with `‹ Earlier | Today | Later ›`, the range, a **Whose** select (replaces the five scope pills; absent in Week and Timeline, which are always the team) and **Filters (n)** (type, status, tag, unit) with removable chips. Everything applies on change when script is on; without script an Apply button submits the same form. Menus close on outside click and Escape. The filter panel is placed against the whole row so it stays on screen wherever the button wraps.
- **Bug fix:** the green "✓ <Macro 'flash'>" banner: the page's message variable `flash` was shadowed by the home page's `flash` macro. It is now `cal_flash`.
- **Empty states:** when nothing is on for the range, today's card still says so, and one line below offers a way forward (clear filters, look further ahead, add something) instead of a second big empty state.
- Checked in Chromium on the real file's 379 imported items at 360, 390, 768, 1024, 1440 and 1920px on both the home tab and `/calendar`: no horizontal overflow, no script errors, filters panel on screen at every width, and on a phone today's events start at y=400 of 844 (before: about 1,000px down). Found and fixed two layout bugs in the first version: the panel opening off the right edge on desktop, and off the left edge at 768px.
- Tests: the scope pills became a select, and the old assertion that the Calendar tab kept the greeting and to-do list was reversed on purpose.

## 2026-10-09 (v4.5 — calendar import dry run, P0.6)

Found by running the CY 2026 file end to end on a local copy and reading the report.

- **`apply()` refuses an already-imported batch** ("This upload has already been imported."). The web route already redirected, but a second call to the function itself overwrote the batch result and with it the list Undo works from (Undo then removed nothing).
- **Fewer false flags:** a time-looking pair glued to letters ("v2 - 2nd") or after a month name ("April 14-16") is no longer flagged as a time in the title; "These days differ by a whole word" no longer fires for spellings of one word ("Plannin/Planning/Planningv", "LHBAssessment"), so the one real case (LDS vs SGA) stands out. Flags on the file: 24 → 21.
- **Dry run result (local copy):** 379 of 379 imported, counts by month and by owner match the file, a second apply is refused, Undo removes all 379. An independent reader found every parsed line in its Word cell (0 missing), and no activity line in the Word tables was dropped (771 content lines: 26 are the "Activity Legend" boilerplate, the rest are in a draft or set aside as holidays). One item ("SEPTEMBER 1: Locking of LHS ML IS Access/Extract data for mid-year") sits in the August table's spill-over cell; the importer reads it as Sep 1.

## 2026-10-09 (v4.4 — calendar import names, P0.5)

- **More names found (`calendar_import._trailing_known_names`):** a name the bureau's name guide knows, written at the very end of a line with no brackets ("…Davao City- Riza and Mae", "…Bicol_Sir Jong/Riza/Vlanche", "…Baguio-Riza", "…HPB-riza"), is now captured and added to any names the bracket/dash rule found. It walks back from the last word over known names, honorifics and "and" and stops at the first other word, so places and topics are not taken for people. On the CY 2026 file the items with names went from 92 to 111.
- **People step (`templates/calendar_import_people.html`):** says how many names are already filled in and how many need a person, shows a live "N of M will be saved" with a sticky Save, and stacks into cards below 1180px. It uses its own `cal-cards` layout, not `resp-table`: that class hides every row holding a `<th>`, and each row here starts with one, so the table was invisible on phones (found by looking at the screenshot; the overflow check alone passed).
- Checked in Chromium at 390, 768 and 1440px on the real file with a stand-in directory built from the name guide: 61 names, all rows visible, no overflow or script errors, and saving added 160 people to 160 items.
- Not changed: the resolver and the name guide (`calendar_people.py`); they already handled these names. Still not captured: names after an unmatched closing bracket ("…Updating Analyn, Jas, Wardah)") and misspellings ("doc vlance").

## 2026-10-09 (v4.3 — calendar import holidays and undo, P0.4)

- **Holidays (`calendar_import_apply.holiday_choices`, review page):** the holiday lines set aside by the parser that are not in Holidays are a checklist with a type each (regular / special / suspension, guessed from the name). Nothing is pre-ticked; some are local (Manila Day). Ticked ones are added with the import, validated with everything else (a bad choice stops the whole import), and a holiday someone already set is never overwritten. They are recorded in the batch result.
- **Undo (`calendar_import_apply.undo`, `POST /calendar/import/{id}/undo`, admin only):** deletes the items the batch created that are untouched since import (sequence 0, and the only revisions are the create plus people matched by the person who ran the import, `storage.cal_entry_untouched_since_import`), and the holidays it added that still read as it left them. Edited items are kept and listed; when nothing is left the batch is reopened (`storage.cal_import_reopen`) so it can be reviewed and imported again. Audited.
- Not done: approving a repeat series on the review screen. No repeat in the CY 2026 file fits a rule exactly, so there was nothing to approve; `suggest_series` stays stored in the batch for a future file.
- Checked on the real file in Chromium at 390px: import 379 items + 1 ticked holiday, undo back to 0 items and 18 holidays, re-import 379.

## 2026-10-09 (v4.2 — calendar import review screen, P0.3)

- **Review screen (`templates/calendar_import_review.html`, `calendar_import_apply.review_rows`):** rows that need a person (no owner colour, a parser warning, a status other than confirmed) are listed first under "Needs you"; the rest are folded into "N rows look fine — show them". Each row shows why it needs you; a suggested owner is shown with a **Use** button and is never preselected.
- **Bulk tools (progressive JS):** tick only the clean rows, tick/untick all, use all suggested owners, give every row with no owner one owner, untick everything before a date. The form fields and the server-side apply are unchanged, so a no-JS browser still works.
- **Sticky summary bar** ("Will import N · skipping M · K ticked with no owner") with the Import and Discard buttons; the table uses `resp-table resp-table-wide`, so it becomes cards below 1180px.
- Checked in Chromium at 390, 768 and 1440px on the real CY 2026 file: no horizontal overflow, no script errors, 307 rows look fine and 72 need you.

## 2026-10-09 (v4.1 — calendar import, P0.1–P0.2)

First two increments of `docs/CALENDAR_UX_PLAN.md` Phase 0 (import the CY 2026 Word calendar). Checked against the real file (379 drafts, 19 holiday lines).

- **Parser (`calendar_import.py`):** "MR SIA" (measles-rubella) no longer counts as a management review (3 items were wrongly `audit_mr`); a URL in a line becomes `meeting_url` and leaves the title; a start time before 06:00 is not kept and is flagged; a bare time left in a title ("PK TWG 10-12") is flagged, not guessed; a title that begins "and/or/with/at" is flagged as a fragment; days merged into one range that differ by a whole word (LDS vs SGA) are flagged as possibly different activities; "Immaculate Concepcion" is recognised as a holiday line.
- **Suggestions (`calendar_import_suggest.py`, new):** `suggest_owners` (a "Section N" in the line, or a tag one unit owns ≥80% of elsewhere in the file) and `suggest_series` (only when a repeat rule reproduces every date exactly). Stored in the batch payload as `suggestions`; nothing is applied without the review screen. On the CY 2026 file: 5 of 47 unowned items get a suggestion, and no repeat fits a rule exactly, so none is suggested.
- Apply passes `meeting_url` through.

## 2026-10-09 (v4.0 — the Office calendar, complete)

A milestone marker for the whole Office calendar programme (increments A1 to H3, v3.5x to v3.79). No code beyond the version.

- **Calendar:** one shared calendar for meetings, trips, trainings, deadlines, banners, CSS activities, reported leave and birthdays, with Agenda / Week /
  Month / Timeline views, filters, scopes (mine, section, division, bureau), a Word-calendar import with the "Who is who?" step, repeating items, quick-add,
  and a Team | Me | Calendar toggle and "Coming up" card on the home page.
- **Two-way links:** weekly whereabouts (a confirmed trip pre-fills Field; your own report always wins; mismatches are soft heads-ups) and CSS activities
  (every activity is on the calendar; "Collect feedback" from an item; editing a linked item goes through the activity; duplicate guard both ways).
- **Staying informed:** one batched email per burst of changes, a Monday week-ahead, a day-before reminder, bell rows with seen-tracking, birthday reminders
  with optional admin-set coordinators, an `.ics` per item, `.ics` attachments, and a private subscribe link.
- **Privacy by construction:** visibility is decided once, in `office_calendar.items_between`, and everything (page, API, feed, emails, assistant answers)
  reads it; birthdays store no year, are shared only by choice and consent is recorded; leave never carries a reason.
- **Read API and assistant:** `GET /api/calendar` and eight calendar questions the search bar answers without the model seeing any calendar data.
- To switch on after deploying: set `CSS_BASE_URL` (emails and links need it), and optionally update the mail relay script (docs/MAIL_RELAY_SETUP.md) so emails carry the `.ics` file.

## 2026-10-09 (v3.79 — office calendar H3: read API and assistant answers)

- **`GET /api/calendar`** (sign-in required; `no-store`): the calendar as JSON — `start`, `end` (default today + 13 days, at most 92 days), `scope`
  (one of the viewer's own scope choices; an unlinked account is not offered `section`), `layers` (some of entries, activities, leave, holidays, birthdays;
  default entries, activities, holidays) and `kind`. It IS `office_calendar.items_between`, the function behind the /calendar page, so a person gets
  exactly what that page would show them in that scope and never more. Each item is a **whitelist** (id, layer, title, kind, status, dates and times, owner,
  venue, format, whether a meeting link exists, tags, url, repeats, the people on it, an activity's lifecycle and registered count): never a note, never
  the meeting link itself, never a leave reason (none is stored), never a birth year. Bad input is a plain 400 with a sentence.
- **The assistant answers calendar questions** (`calendar_answers.py`, new, in the Space bundle): eight answer slots — today, tomorrow, the rest of this
  week, next week, my next item, who is away this week / next week (trips and leave, by name and dates only), and birthdays this week. **The model never sees
  calendar data**: like the survey-statistics answers it can only choose a key from a fixed list of labels and keywords, and the server renders the text from
  the ASKER's own calendar (same visibility, so two people asking get two different, correct answers). Banners, cancelled and postponed items are left out,
  tentative ones are marked, long lists stop at six with "…and N more".
- **No model call needed**: eight FAQ rules ("what is on next week", "who is away this week", …) answer these through the existing deterministic layer, at zero
  cost and while the assistant is off. They are added once to existing installs (marker `calendar_rules_seeded`) so an admin who removes them never has them
  resurrected, and appear on fresh installs with the other seeds. The admin rules form lists the new answer slots automatically.

## 2026-10-09 (v3.78 — office calendar H2: Timeline view and quick-add)

- **Timeline layout** (`/calendar?view=timeline`, and the home Calendar tab's layout switch): four weeks of calendar days across, one row per
  person in the viewer's team (the same directory-based team and scope as the Week layout and Who's in — an unlinked account gets a clear
  message, not everyone), grouped by section. Bars are trips, trainings, meetings, CSS activities and **reported leave (never a reason)**,
  stacked in up to 3 lanes with "+N" for the rest (never silently dropped) and cut-edge markers when an item runs past either end. Items naming
  nobody in the team sit in a band at the top. Weekends are shaded, holidays tinted and named, today outlined; "← Earlier / Later →" move
  four weeks. Filters (type, status, tag, unit) apply as everywhere else. `office_calendar.timeline` is the model.
- **Quick-add sheet** (a `<dialog>`, `static/js/calendar.js`): "⚡ Quick add", a day header, or an empty day on a person's row opens a small
  form (title, type, who can see it, dates, optional times; a person's row pre-fills them as the person on it) that posts to the ORDINARY
  `/calendar/new` route, so every rule there applies unchanged, and returns to the page it came from with a confirmation. The return address must
  be a calendar page of this site (anything else — another host, `//`, backslashes, other paths — is ignored and you land on the new item), and
  the confirmation text is escaped. A progressive enhancement: without JavaScript, the buttons stay hidden and "+ Add" does everything; the
  script builds no HTML from strings.
- Not in this increment: dragging bars to move or resize them (a possible later refinement).

## 2026-10-09 (v3.77 — office calendar H1: repeating items)

- **One entry, many occurrences.** A series is a single `calendar_entry` carrying an RFC 5545 `RRULE` and an `EXDATE`-style list of skipped
  dates (`recurrence.py`, new, pure, added to the Space bundle; `python-dateutil` is now an explicit requirement). Only the shapes people use
  are accepted — every weekday, weekly, every 2 weeks, monthly on the same date, monthly on the same weekday (a 5th becomes "the last") — and
  **every series must end** (UNTIL, at most 2 years), so nothing can fill the calendar, the feed or the reminders forever. A rule must begin on its
  own start date; anything else is refused with a sentence. A trip or an item linked to a CSS activity can't repeat, and a series can't be turned
  into an activity.
- **Add / edit form**: "Repeats" and "Last date it repeats"; the edit form pre-selects the current series, and stopping it is choosing "Doesn't
  repeat" (which also clears the skipped dates).
- **The calendar expands it** (`storage.cal_occurrences_between`): one item per occurrence in the window (keyed `entry:<id>:<date>`, linking to the
  series with `?date=`), skipped dates removed, a multi-day occurrence that began earlier counted, a "· Repeats" flag, and "· Falls on <holiday>" when
  it lands on one. Everything downstream follows: double-booking and leave-on-an-item heads-ups, the day-before reminder, the Monday week-ahead, the
  bell (a series still running counts as upcoming), and cancelling cancels the whole series (restore brings it back).
- **Change just one date**: open an occurrence and choose *Change just this one* (a pre-filled one-off; saving it also skips that date in the series —
  and is refused, creating nothing, if someone already changed that date) or *Skip this date*; skipped dates list with *put back*. Skipping is a
  schedule change: it bumps the sequence and the people on the item get the usual change email.
- **.ics / feed**: a series is ONE event with its `RRULE` and `EXDATE`s (dates for all-day, `TZID` times for timed), in the per-item download, the
  email attachments and the personal feed, so calendar apps show the whole series; the feed no longer repeats it per occurrence.

## 2026-10-09 (v3.76 — office calendar G4: .ics downloads, attachments and the personal feed)

- **`calendar_ics.py`** (new, pure; added to the Space bundle): RFC 5545 output — CRLF lines folded at 75 OCTETS without ever
  splitting a UTF-8 character, TEXT escaping, a VTIMEZONE for Asia/Manila (no DST, one STANDARD block), timed events with
  `TZID`, all-day events as `VALUE=DATE` with the exclusive `DTEND`, UTC `DTSTAMP`, and the entry's random `UID` +
  current `SEQUENCE` + `STATUS` (postponed shows as tentative with a "[Postponed]" title; cancelled says CANCELLED) so a
  calendar app UPDATES an event rather than duplicating it. Birthdays are yearly all-day events (`RRULE:FREQ=YEARLY`; a Feb 29
  person repeats on the last day of February, matching the app) and no birth year exists anywhere.
- **Per item**: "Add to my calendar (.ics)" on every item page (`/calendar/entries/<id>/event.ics`), with the page's own visibility
  (anything you cannot see is a 404) and sign-in required.
- **Attachments**: the change email (G1) and the day-before reminder (G3) now carry an `.ics` with the same uid and current
  sequence (a cancellation carries STATUS:CANCELLED). `mailer.send(attachments=…)` works over SMTP and the relay; **the relay
  script in docs/MAIL_RELAY_SETUP.md gained a few lines to read them — paste it and redeploy a new version to enable
  attachments; an older script just ignores them and the email still goes out.**
- **Personal feed** (`/me` → Calendar link; `/calendar/feed/<token>.ics`): works without signing in because calendar apps cannot;
  the long random token IS the credential, so it is replaceable ("Make a new link" kills the old one at once) and removable.
  It shows what its owner may see, by the same rules as the calendar page — "My items (plus what is bureau-wide)" or "My
  section" — from two weeks back to a year ahead, adds items cancelled in the last 30 days as STATUS:CANCELLED so subscribed apps
  drop them, and (opt-in) the birthdays shared with them. A wrong, reset, switched-off or deactivated-owner token all answer the
  same 404; responses are `private`, `noindex`. The page says plainly that Google refreshes only every 12–24 hours.
- The Monday email carries no attachment (it lists many items); the activity ("CSS") events appear in the feed with a stable id.

## 2026-10-09 (v3.75 — office calendar G3: week-ahead, day-before, roll-up lines)

- **Monday week-ahead**: the existing whereabouts Monday email gains "On the calendar this week" — what that person may
  see for Monday-Friday under the default scope (their own items plus what is bureau-wide), up to 8 with "…and N more";
  banners, cancelled and postponed items are left out, tentative ones are marked, a trip under way shows its days this week.
  No second email, and it keeps the Monday email's weekday gate. Switch: "Put the week's calendar in my Monday email" on `/me`.
- **Day-before reminder** (`--calendar-day-before`, new scheduled email with an /admin/email toggle and preview): everyone on a
  live entry that STARTS tomorrow gets ONE email listing all of tomorrow's. A CSS activity (an entry linked to one) is skipped
  — the existing `--events` reminder covers it, so nobody is told twice; banners are background. Once per person per day (email
  log), dry runs send nothing, inactive accounts are skipped. Switch: "Remind me the day before…" on `/me`.
- **Chief roll-up lines**: the Tuesday roll-up (still only sent to chiefs with someone undeclared) adds "Calendar and report
  disagree (N)": staff who reported something other than Field on a trip day, or leave on a day an item lists them. **Names and
  days only, never an item's title**, which may not be the chief's to read.
- Not yet: the `.ics` attachment on these emails and the personal feed (G4).

## 2026-10-09 (v3.74 — office calendar F3: birthday reminders)

- **Bell**: one row, "🎂 Today: Mae, Tek", listing the day's celebrants the person may see (each owner's sharing choice;
  yourself never). Computed from today's date, so it is gone at midnight; Feb 29 people appear on Feb 28 in a non-leap year.
  One cheap query when nobody has a birthday today.
- **Monday email**: one line, "🎂 Birthdays this week: Riza (Wed), Tek (Sat)", added to the existing whereabouts email — no
  extra email — personalised by each recipient's sharing scope, and absent when there is none.
- **Optional coordinators** (admin → Users → "Birthday celebration coordinators"): tick accounts that organise celebrations.
  Two new scheduled emails, each with its own /admin/email toggle and preview: `--birthday-coordinators` (the day before, one
  email per coordinator per day) and `--birthday-month` (the first working day of the month — weekends and holidays skipped; a
  sleeping app catches up through the 7th). **With nobody ticked neither is sent**; everything else works without them.
  Coordinators only hear about birthdays people shared with them, and never about their own. Both are idempotent through
  `email_log`, and a dry run sends and logs nothing.
- **Profile**: "Tell me about teammates' birthdays (the bell and the Monday email)", on by default; a form without the field
  never flips it.
- Not in this increment: the avatar party-hat badge, and the Monday "week-ahead" for entries (G3).

## 2026-10-09 (v3.73 — office calendar G2: bell rows and seen-tracking)

- **"N new or changed calendar items for you"** in the nav bell: upcoming items the person is ON whose `seen_seq` is empty
  (new) or behind the entry's `sequence` (the schedule moved; a note/tag edit does not count) or that were cancelled. The
  row links to **`/calendar/updates`**, which lists exactly those and marks them seen, so the bell and the list cannot
  disagree; opening an item's own page marks just that one. (The plan said opening `/calendar?scope=me` clears them; that page only
  shows two weeks, so a dedicated list is what makes the count honest.)
- **Never for your own edits**: the person who creates or changes an item is stamped as having seen it; a bulk import stamps
  everyone; and everything that existed before this release is backfilled as already seen (one-time, flagged in
  `app_setting`), so day one shows no flood.
- **"Confirm where you'll be: <trip>"** (same mismatch as the home to-do) and **"<trip> changed after you confirmed your
  week"** (the trip's schedule moved after the person last submitted that week; links to that week's form). Information like
  "you have a meeting today" is not a bell row.
- Cheap on every request: the unseen query is indexed by person, and the trip checks start with one query and return early when
  the person is on no trip. A failure there can never break a page.
- Not yet: the birthday row (F3).

## 2026-10-09 (v3.72 — office calendar G1: batched change emails)

- **Outbox** (`calendar_outbox`): `cal_create` / `cal_update` / cancel / restore write one notice per affected person in the
  SAME transaction as the change — **never the editor**. Kinds: *added* (new, or newly put on it), *changed* (title, date, time,
  venue, format, link or status moved; a note, tag or audience edit says nothing), *cancelled*, *removed*. A bulk import,
  a cancelled-on-arrival item and anything already over queue nothing.
- **`office_calendar.flush_outbox`**, called every scheduler tick: ONE email per person per burst. It waits until the person's
  newest notice is 10 minutes old (or the oldest has waited 60), except a notice about something **today or tomorrow**, which
  goes on the next tick. Within a burst: added + edits → one "added" with the final details; added then cancelled → nothing;
  several items → one "Calendar update: N items" email. Email text is built from the entry as it is *now*.
- **Respects** the person's own switch (new on `/me`, on by default; a form without the field never flips it) and the
  admin's global switch (new feature "Calendar — added / changed / cancelled" in /admin/email, with a preview). Inactive
  accounts and deleted entries are dropped; a failed send retries up to 3 ticks; with mail not configured the notices wait and
  expire after 2 days. Needs `CSS_BASE_URL` (for the links) like the other reminder emails.
- Not yet: the `.ics` attachment (G4), bells (G2), the Monday/day-before emails (G3).

## 2026-10-09 (v3.71 — office calendar F2: birthdays on the calendar)

- **`birthdays` layer**: 🎂 <nickname or first name> on the day, every year, as an all-day item of type "Birthday"
  (a filter option). Visible only to **the owner's sharing choice ∩ the viewer's scope**: yourself always; "My section" =
  the same unit; "My division" = the same division; "Whole bureau" = everyone; "Don't share" = nobody else. The
  default scope (Mine + bureau-wide) shows yours and bureau-shared ones; the section / division pills show that
  unit's people. Archived and inactive people drop off. **Feb 29** sits on Feb 28 in non-leap years. Pure rules live
  in the new `birthdays.py` (added to the Space bundle).
- **Home "Coming up" card**: "🎂 Celebrating this week: Riza (Wed), Tek (Sat (weekend))" under the same scope as the
  card; birthdays are a line, not agenda cards, and no longer fill the card's slots. (Leave bars, which E1 added to the
  same list by accident, are also kept out of it now.)
- **Celebrant's greeting**: on the day the home page says "Happy birthday, <name>! 🎉" — from their own data, whether or
  not they share it.
- **`/calendar/birthdays?month=10`**: the month's celebrants grouped by section, printable, only what the viewer may
  already see; a Birthdays button on the calendar page.
- The Week view skips the layer. Not yet: the avatar party-hat badge, bells and emails (F3, G2).

## 2026-10-09 (v3.70 — office calendar F1: birthdays, captured with consent)

- **Capture on `/me` and the `/welcome` step**, optional: a month and a day. **No year is accepted or stored**
  (no year parameter exists). Feb 29 is fine; Apr 31 or Feb 30 is refused, with the person's other choices kept.
- **Sharing is opt-in**: Don't share (default) / My section / My division / Whole bureau. Choosing a scope records
  `birthday_consent_at` and a snapshot of the exact notice shown; keeping the same scope keeps the original time, a
  wider one is a new consent, and "Don't share" erases the record.
- **One-click withdrawal** (`POST /me/birthday/remove`, "Remove my birthday") clears the date, the sharing choice and
  the consent record. A form that doesn't carry the birthday fields never wipes a saved one.
- **Personal data stays with the person.** Stored on the account, never on the staff directory row, never on the admin
  staff form or user list; the audit log records that it was set/removed and the sharing level, never the date.
- Nothing shows it to anyone yet — the calendar layer, home line and greeting are F2; reminders are F3.

## 2026-10-09 (v3.69 — office calendar: mismatches and "Add this trip")

- **`office_calendar.mismatches(conn, user_ids, start, end)`** — one function for the soft heads-ups, derived at
  read time, never blocking: `trip_conflict` (on a confirmed trip but reported Office/AWA/Leave), `leave_on_entry`
  (reported Leave on a day a live entry lists them; a trip is a trip_conflict, not both) and `double_booked`
  (two timed entries that overlap; touching ends and untimed items don't count). Cancelled and tentative items never count.
- **Whereabouts form:** a day whose report disagrees with a trip says "The calendar has you on <trip>, but you reported
  Office. Is that right?".
- **Home to-do "Confirm where you'll be"** (this week and next) opens the right week.
- **Calendar item page:** a "Heads-up" box, shown only to the person concerned, the item's leads and whoever added it.
- **"Add this trip to the calendar"** (signed-in whereabouts form only): runs of consecutive days the person reported
  as Field with the same place, that no trip covers, get one button → a `travel` entry (source `whereabouts`, audience =
  their section, they are on it). Never automatic; the run is re-derived server-side so a forged request is refused and a
  second tap can't duplicate it.
- Not in this increment: bells and the "trip changed after you confirmed" notice (G2), and the extra lines in the
  Tuesday chief roll-up.

## 2026-10-09 (v3.68 — office calendar: trips fill in whereabouts, leave on the calendar)

- **Calendar → whereabouts (layer 3).** A person listed on a CONFIRMED `travel` entry gets **Field** plotted
  for each working day of it (note = the venue, else the title), above their filed arrangement and below
  their own report. The weekly form and the Monday email open already showing "Field — Palawan"; the form
  says "Filled in from the calendar: <trip>". Read at call time, so a moved trip moves the default; a
  cancelled, tentative or postponed trip gives nothing; weekends are skipped.
- **The person's own report always wins.** A saved row (including Office on a trip day) is never touched;
  confirming a prefilled day writes their own row.
- **Who's in (day) and the week roster** plot an unreported trip day as Field too (marked as plotted). The
  place is shown only when the trip's audience isn't "only the people I add".
- **Leave on the calendar (`leave` layer).** Reported leave days appear as "<name> — on leave", one bar per run
  of working days (a weekend doesn't break it). Never a reason. Visibility is exactly the Who's-in rule
  (own unit subtree, bureau for the Director or a grant, nobody else's for an unlinked account); the default
  "Mine + bureau-wide" and "Mine only" scopes show only your own, so a section isn't flooded. "On leave" is a
  filterable type. The Week view skips the layer (its rows already show leave).
- Mismatch warnings and "Add this trip to the calendar" are E2.

## 2026-10-09 (v3.67 — office calendar: editing linked items + the "collect feedback?" nudge)

- **Editing a calendar item that is linked to a CSS activity.** The form shows the activity's title,
  type, time and venue read-only (the activity owns them) and keeps who is on it, the audience, tags and
  notes editable. Anything posted for the locked fields is ignored.
- **Moving the dates from the calendar** goes through the activity's own Dates path (the event and
  every form of it, the reporting cache, an `event_dates_set` audit row), and the item's own dates and
  sequence follow so attendees' calendars update. Only people who can manage the activity may; others
  see the dates locked (403 if they post them). A stale form is a conflict and changes nothing.
- **Registrants are asked first.** If anyone registered with an email, saving shows "N people
  registered — email them?" with *Save and email them* / *Save without emailing*. The email
  ("Activity re-dated", new admin toggle) carries each person's own resume link.
- **"Collect feedback?" nudge** (new scheduled email, `--calendar-css-nudge`, toggle in /admin/email):
  the day after a TRAINING that lives only on the calendar, its creator is asked once. Never for
  meetings, trips, audits, banners or deadlines; never for cancelled, imported or back-filled items;
  never when a similar activity already exists; marked per item so it cannot repeat; a failed send is
  retried within the 3-day window; a dry run marks nothing.

## 2026-10-09 (v3.66 — office calendar: Collect feedback (CSS) and the duplicate guard)

- **"Collect feedback (CSS)"** on a calendar item's page (live meetings and trainings only — a trip,
  audit, banner, deadline or cancelled/already-linked item has nobody to ask; only people who can
  create activities see it) → `/create?from_entry=<id>`, with the form pre-filled: name, dates, venue
  (or the meeting link), format, the organising section when the item's owner is a section, and the
  item's LEADS who have a directory record as speakers (topic = the item's title; attendees are not
  speakers). A banner says it will be linked, with "Don't link". An item the person can't see, or
  that can't be turned into an activity, simply gives the normal blank form.
- **Linking** (`storage.cal_link_event`) — when Create succeeds the item becomes the activity's
  OVERLAY (D1): the activity owns title/dates/venue and the item adds people/tags/audience, and the
  calendar shows ONE card (the activity). The result page says "Linked to the calendar item". Bureau
  and outside activities both link. A failed link never undoes or hides the activity just created;
  a validation error keeps the link. One audit line; the sequence never changes.
- **Duplicate guard, both directions** — (1) the create screen's new `/create/check-calendar` heads-up
  offers calendar items the person may see with the same dates and a similar title, with a "Link this
  activity to it" button (nothing links until Create); (2) an item's page lists activities on the same
  dates with a similar title that have no calendar item yet, with "Link to this activity"
  (`POST /calendar/entries/{id}/link-activity`, needs create-activity rights; refuses an item or
  activity that is already linked). Similar = equal, one inside the other (6+ characters) or very
  close; always only a suggestion.
- **Item page** shows "linked to the CSS activity … the activity owns the title, dates and venue".
- **Tests** — `tests/test_calendar_link.py`. `static/css/calendar.css` → `?v=20261009k`.
- **Not here yet** — editing a linked item's dates from the calendar (writes through to the activity,
  with the registrant notice) and the next-day "collect feedback?" nudge are D3.

## 2026-10-09 (v3.65 — office calendar: every CSS activity is on the calendar)

- **`activities` layer** (`office_calendar._activities_layer`) — every non-archived CSS activity (the
  `event` table) that overlaps the window is on the calendar with NO copying and NO backfill: if it
  exists it shows, in the agenda, month and week views, the home "Coming up" card and today's to-do
  count. The activity owns its title, dates, venue and format. Invited ("outside") activities are
  included; an activity with no date is never drawn; one whose every form is archived is hidden and
  returns when restored.
- **Chips by lifecycle** — upcoming: "N registered"; ongoing: "feedback open · N answered"; concluded:
  "concluded · N responses" (from `lifecycle_of` + `event_registration_summary`). Staff who manage
  activities land on `/monitor/<token>`, everyone else on the public `/e/<token>`. (The 1-5 score on
  the card is not here yet — it needs the survey atoms and is left for a later increment.)
- **Overlay** — a calendar entry whose `event_id` is set adds people, tags, kind, owner unit and an
  audience on top of the activity and is NEVER drawn as a second card (the entries layer skips it);
  an overlay narrowed to "only the people I add" hides the activity from everyone else.
  `storage.cal_overlays_for_events`.
- **People** — internal speakers who have an account are the people on the activity (role lead), so
  the Week view puts an activity on its speakers' rows.
- **Scope** — visibility is separate from scope. Everyone sees activities (staff register and rate
  through them) unless an overlay narrows it; a section/division view shows the activities that unit
  ORGANISES, "mine" those you created, speak at or are put on; "bureau" everything visible.
- **Filters/labels** — "CSS activity" is in the type filter; a person still cannot POST the
  "activity" kind from the add form (`FORM_KIND_LABELS` vs `KIND_LABELS`). Unit chips and tag menus
  include activities. `viewer_context` now carries `role` and `rp_id`.
- **Tests** — `tests/test_calendar_activities.py`. `static/css/calendar.css` → `?v=20261009j`.

## 2026-10-09 (v3.64 — office calendar: Week view, people × days)

- **Week layout** (Agenda | **Week** | Month; on `/calendar` and the home Calendar tab) — one row per
  person in the viewer's team, grouped by section, Monday–Friday across; each person's calendar items
  are bars over their row (a trip across Tue–Thu is one bar; cut flat where it runs past Friday or
  began earlier; three lanes then "+N more" to that day's agenda). Items that name nobody in the team
  (the whole unit, the bureau, someone outside) sit in a band at the top, so nothing visible is left off.
- **Where people are** comes from `storage.whereabouts_roster_week` — the "Who's in" week page's own
  function — so its rules carry over: scope is the directory (an unlinked account gets a message, not
  everyone), a person's own report beats the filing, a holiday has no cells, **leave never carries a
  reason** (asserted: the note never reaches the page), a field trip shows where; a pale dot is the
  filed plan not yet confirmed by the person. Dots are never the only signal: each non-office state
  also says it in words.
- **Scope** — the scope pills don't apply to this layout (rows come from the directory); items are
  loaded for the whole team but still only what the viewer may see (an item for "only the people I
  add" is drawn for those people alone, not even for the Director).
- **`office_calendar.people_week`**, `monday_of`, and `_lay_out` (the lane stacking `month_grid` now shares).
- `static/css/calendar.css` → `?v=20261009i`. **Tests** — `tests/test_calendar_week.py`.

## 2026-10-09 (v3.63 — office calendar: the Calendar tab on the home page, and today's count in the to-do)

- **Home page tab: Team | Me | Calendar** — `/?view=calendar` shows the full calendar body (scope
  pills, Agenda/Month, filters, unit chips, + Add) under the greeting and to-do, in place of the team
  panels, the Coming-up card and the doors. Team needs a directory link; Me and Calendar are for
  everyone (an unlinked account sees Me | Calendar). The tab opens on the scope of the tab you came
  from: Team -> your team (or the whole bureau), Me -> yours plus bureau-wide. Every link, filter form
  and month/agenda switch stays on the home page (`view=calendar`, layout in `layout=`).
- **Shared body** — `calendar_routes.build_calendar_page(conn, user, today, q, base=, layout_key=,
  fixed=)` builds the page for both `/calendar` and the tab; `templates/_calendar_body.html` is the
  one body. `/calendar` behaves exactly as before; its template variable `view` is now `layout`.
  If the tab's calendar fails the page still renders, with a link to `/calendar`.
- **To-do** — `office_connect._task_calendar_today`: "N things on the calendar today" (your own items
  plus what is bureau-wide; holidays and bureau-wide banners don't count), with the first two titles
  and times, linking to the Calendar tab. Tone "for information": after to-dos, before done items.
  Like every task source, a failure is swallowed and never hides the others.
- **Tests** — `tests/test_calendar_home_tab.py`.

## 2026-10-09 (v3.62 — "Coming up" on the home page; initials as nicknames)

- **Home page (`/`, Team and Me tabs)** — a "Coming up" card under the to-do strip: the next seven
  days from the office calendar, up to five items (Today / Tomorrow / weekday, time, title linked to
  the item, owning unit's colour and name, dates when it is a trip already under way, venue, status,
  up to three faces) with "+N more", a holiday line, an empty state with an Add link, and an "Away"
  strip of the people on a confirmed trip (one chip per person, capped at six). Built by
  `office_connect.calendar_week_block` on top of `office_calendar.items_between`, so what is shown can
  never exceed what `/calendar` shows. Scope: Team = the viewer's unit (their section, a chief's
  division) or the whole bureau for a bureau-wide viewer; Me, or an account with no directory link =
  their own items plus what is bureau-wide. (An item you are on that another unit owns is on the Me
  tab.) The card is optional: if it fails the page still renders.
- **Nicknames** — the bureau's initials are now prefilled as nicknames (KJF, JAP, MM, ASF); one per
  person (Mary Anne Milliscent Castro: "MM", not "MMC"). People can change theirs on My profile.
- **Tests** — `tests/test_calendar_home.py`; nickname tests updated.
- `static/css/calendar.css` bumped to `?v=20261009h`.

## 2026-10-09 (v3.61 — fill in nicknames from the bureau's list; Cath; the previous Director)

- **`/calendar/nicknames`** (admin only) — gives accounts the nickname the calendar uses, from the
  bureau's own list (`calendar_people.NICKNAME_PREFILL`: Tek, Malou, Olga, Mimi, Feng, Dheng, Cha,
  Riza, RJ, Desten, AC, Jong, Cath, Mae). Each person is found by FULL NAME. Rows: Ready (ticked),
  Already set, Has another nickname (left alone unless an admin ticks it), two accounts with that name
  (never ticked), no account found. Initials (KJF, JAP, MM, MMC, ASF, MWB) are not nicknames, and a
  first name needs none. The nickname written comes from the server's list, never the form. A nickname
  is also what the home page greets the person by, and they can change it on My profile. One audit
  line per save. Linked from the import page and the "Who is who?" page.
- **Guide** — Cath = Cathrina Laurio. **`NO_ACCOUNT`**: people the guide names who have no account at
  all (the previous Director, Mar Wynn Bello) now show "has no account" with the skip option
  pre-selected instead of lingering as unmatched.
- **Tests** — `tests/test_calendar_people.py` (nickname proposals, apply, can't overwrite, can't be
  forged; missing-account skip; Cath).

## 2026-10-09 (v3.60 — name guide: the rest of the names, archived people, "Place - Name")

- **Guide additions** — Jong = Ray Justin Ventura; Mae = Maejorie Orpilla; Desten = Modesto Lazo
  (same person as Modesto); MMC = Mary Anne Milliscent Castro (same person as MM); ASF = Analyn
  Fortaleza (same person as Analyn); "Mar Wynn" = the previous Director. MMC/ASF are no longer
  "probably not people" (`PROBABLY_NOT` is now empty; the mechanism stays).
- **Archived / inactive people** — `load_directory` now returns every account with an `inactive`
  flag. The guide may name someone who has left (Maejorie Orpilla is archived; the previous
  Director may be) and the item still shows who it was for, marked "(archived)"; an active
  namesake beats an archived one. Ordinary matching (nickname, first name, "starts like") only
  ever looks at ACTIVE people, and archived people are not offered in the everyday picker.
- **"Place - Name"** — `expand` splits a person glued to a place at the dash ("MDN - Malou",
  "SGA - Arlene", "℅ MM CHD-Cath"): the sides that match somebody are the names and the place is
  dropped; if neither side matches, the whole token is kept so it can be marked "not a person".
- **Dry run on the real file** against the names supplied: 69 of the 92 items with names match;
  only "Mar"/"MWB" (no active account for the previous Director) and "Cath" are left.
- **Tests** — `tests/test_calendar_people.py`.

## 2026-10-09 (v3.59 — name guide for the imported calendar)

- **`calendar_people.NAME_GUIDE`** — the bureau's own answer to "who is this?" for the names in the
  CY 2026 calendar (Tek = Teresita Guzman, Riza = Maria Teresa Santiago, KJF = Kathrine Joyce Flores,
  JAP = the Director, MM = Mary Anne Milliscent, Mar / MWB = the previous Director Mar Wynn Bello…).
  It is looked up by FULL NAME in the directory (all words, else first + last word), so it needs no
  user ids. It ranks just under a remembered answer and above nickname/first-name matching, so two
  Ronnels or two Junes resolve correctly; a guide person with no active account is shown as
  "Guide says … · no active account" and is never replaced by a first-name guess.
- **Not people** — `NOT_PEOPLE` marks the plain places/teams/phrases from the file (Cebu, CAR,
  Tolosa, BLHSD IQA Team, DOH Rep, ZBB…) so they pre-select "Not a person" ("CAR" no longer offers
  Carole); `PROBABLY_NOT` (MMC, ASF) is shown as "Probably not a person" and never chosen.
- **People step** — new chips (Name guide · …, Guide says … · no active account, Not a person) and
  the "Not a person" option pre-selected for known non-people. Still nothing is written until Save.
- **Tests** — `tests/test_calendar_people.py` (guide, ambiguity, missing account, honorific forms).

## 2026-10-09 (v3.58 — office calendar: match the names in the imported calendar)

- **`/calendar/import/{id}/people`** (admin only; only after the batch is imported) — "Who is who?":
  every name the importer found in the imported items, with the items it appears in, how well it
  matched, and a choice per name: a person, "not a person" (places, teams, initials) or "decide later".
- **`calendar_people.py`** (new) — the matcher. Levels, best first: remembered answer, nickname,
  full name (any order), first name, surname/other name, "starts like" (3+ letters). A name is only
  PRE-SELECTED when exactly one person fits at one of the first five levels; "starts like" is only
  ever offered as "maybe" ("Dir. Mar" must not become Maria); two people called Mae are "ambiguous"
  and nothing is chosen; places and initials are "unmatched". Honorifics (Sir, Doc, Ma'am, Dr., Dir.,
  Usec…) are dropped first; "Riza Desten" is split into two people only when each word is someone.
  Active accounts only; "Last, First" directory names are reordered.
- **Writing** — nothing is saved until Save. People are ADDED to the items (never replacing who is on
  them), as `travel` on trips and `attending` otherwise, stamped as already seen so a bulk import
  cannot flood anyone's bell later; people never bump an item's sequence. Applying twice adds nobody
  twice; names left on "decide later" stay on the list. One audit line per save.
  `storage.cal_add_people`, `cal_import_set_result`.
- **Remembered** — each answer is kept (`calendar_people_aliases`, `calendar_people_ignored`) so next
  year's upload pre-selects it as "Remembered".
- **`calendar_import_apply.py`** — `people_state`, `apply_people`. **`deploy_hf.py`** ships
  `calendar_people.py`.
- **Tests** — `tests/test_calendar_people.py`.

## 2026-10-09 (v3.57 — office calendar: import the Word calendar)

- **`/calendar/import`** (admin only — `manage_users`; everyone else gets 403) — upload the yearly
  .docx → review → import. Upload is capped (8 MB, 80 MB unpacked) and any unreadable file gets one
  friendly message; the parsed drafts are kept in the new `calendar_import_batch` table so a review
  survives a restart and B3 can still see the people hints.
- **Review page** — (1) map each legend colour (Bureau, Sections 1-5) to a unit, guessed from unit
  names and remembered next time; this also sets the unit colours the calendar draws
  (`calendar_unit_tones`); (2) who can see the items (everyone, or only the owning unit — an item
  with no unit is always shown to everyone so it can't become invisible); (3) a table of every item
  with tick / dates / title / type / status / owner editable, plus warnings, times and name hints.
- **`calendar_import_apply.py`** — all-or-nothing: every ticked row is validated before the first is
  written (`storage.cal_validate`), one audit line for the whole batch (`cal_create(audit_it=False)`).
  Idempotent: a draft whose `import_key` is already in the calendar is left alone — re-uploading the
  same file, or importing twice, adds nothing and never overwrites a later edit. An imported batch
  cannot be imported or discarded again.
- **Real file** — the CY 2026 calendar imports as 380 items in 0.1 s; review page 618 KB.
- **`deploy_hf.py`** ships `calendar_import_apply.py`; `app.py` adds a search-only "Import calendar"
  entry (admin).
- **Tests** — `tests/test_calendar_import_page.py`.

## 2026-10-09 (unreleased — office calendar B1: the Word-file parser, no visible change)

- **`calendar_import.py`** (new, pure — no DB, no routes): `parse(path_or_file)` reads the yearly
  Word calendar and returns `Draft` entries plus the holiday lines it set aside, file-level
  warnings, stats and the colours it could not map.
  - Owner = run highlight / shading per the legend (green Bureau, yellow S1, magenta S2, orange
    S3, cyan S4, blue S5); pastel cell tints, white and unknown colours mean "no owner".
  - Guesses (all editable in the review screen): kind, status (tentative/postponed/pending),
    modality, start/end time (`130pm:`, `(1:30-3pm)`, `9-12`, `8-10AM`, `9-12 AM` = noon; AM/PM
    alone stay a note), tags, and a raw `people_hint` for the resolver (B3). Numbers such as
    "LIPH IS 3.0", "AO 2021-0040", "CHD6" are not mistaken for times.
  - Wrapped fragments ("(S4: Carole)") join their activity; holiday lines are set aside.
  - Identical activities on consecutive WORKING days merge into one range (across weekends, a
    holiday, or a month table); typo variants within two characters merge with a warning, while a
    different place ("Tawi Tawi" / "Basilan") never does. Stable `import_key` per draft.
  - Run on the real CY 2026 file: 12 tables, 678 lines → 380 drafts, 18 holidays set aside, no
    file-level warnings; 48 drafts had no owner colour and are flagged.
- **`deploy_hf.py`** — ships `calendar_import.py` in the runtime bundle (B2 will import it).
- **Tests** — `tests/test_calendar_import.py` (builds a small .docx in the test; the real file is
  not in the repo).

## 2026-10-09 (v3.56 — office calendar: month grid and filters)

- **`/calendar?view=month&month=YYYY-MM`** — a Sunday-first month grid like the Word calendar.
  A multi-day trip is ONE bar per week (flat-ended where it continues into the next), stacked in
  lanes; at most three lanes are drawn and the rest are counted per day as "+N more", linking to
  that day's agenda — never silently dropped. Holidays label and tint their day; today is ringed;
  tentative bars are dashed, postponed ones struck through. Phones get a note pointing at the
  agenda instead of the grid.
- **Filters (agenda and month)** — type, status and tag selects plus clickable unit chips (the
  colour legend), all kept in the URL and across Earlier/Later/month navigation. Menu options are
  taken from the unfiltered window so choosing one never hides the others; invalid values are
  ignored; holidays are never filtered out.
- **`office_calendar.py`** — `month_span`, `month_grid`, `apply_filters` (also `items_between(filters=)`).
- **`calendar_routes.py`** — `/calendar` now handles both views (`calendar_page`).
- **`static/css/calendar.css`** bumped to `?v=20261009b` (new rules).
- **Tests** — `tests/test_calendar_month.py`.

## 2026-10-09 (v3.55 — office calendar: add, edit, cancel and restore items)

- **`calendar_routes.py`** — `GET/POST /calendar/new`, `GET /calendar/entries/{id}` (detail +
  history), `GET/POST …/edit`, `POST …/cancel`, `POST …/restore`. Anyone signed in may add and
  edit; an entry the viewer may not see answers 404 for every one of these (same as a missing
  one). The form rejects: an empty title, end before start, a non-http(s) meeting link, a type or
  status outside the offered list (so "activity" and "cancelled" can't be posted), people who
  aren't active accounts, "only the people I add" with nobody added, and "owning unit" audience
  with no unit (nobody outside the attendees would ever see it).
- **Conflicts** — the form carries `updated_at`; a save against a newer version returns 409 with
  who changed what, keeps what the person typed, and does not overwrite until they save again.
- **`storage.py`** — `cal_update(expected_updated_at=)` (moves on every edit, unlike the
  sequence); `meeting_url` must be http(s) (it is rendered as a link).
- **`office_calendar.py`** — `viewable_entry`, `people_choices`, `unit_choices`, `display_names`,
  `describe_change`.
- **Templates/CSS** — `calendar_entry_form.html`, `calendar_entry.html`; the agenda gets "+ Add"
  and links each title to its page.
- **`deploy_hf.py`** — the HF runtime bundle now ships `office_calendar.py` and
  `calendar_routes.py` (missing them would have crashed the Space on start; caught by
  `test_runtime_py_is_import_closed`).
- **Tests** — `tests/test_calendar_entry_pages.py`; storage tests extended.

## 2026-10-09 (v3.54 — office calendar: read-only agenda page)

- **`calendar_routes.py`** (new, the repo's first `APIRouter`) — `GET /calendar`: a two-week agenda
  with scope pills (Mine + bureau-wide / Mine only / My section / My division / Everything I can
  see), Earlier / Today / Later links and a pinned "today". `app.py` includes it with one line
  (`make_router(templates, get_conn, _today_local)`); `_auth_gate` already covers it by path.
- **`office_calendar.py`** — `agenda_days()` (groups items by day, "day 2 of 3" for trips) and
  `scope_choices()` (never offers a pill that could only be empty).
- **`templates/calendar.html`, `static/css/calendar.css`** — colour = owning unit (green/yellow/
  magenta/orange/cyan/blue/grey tokens, light/dark/contrast), tentative dashed, postponed struck
  through; the unit name is always written, never colour alone.
- **`app.py` / `dash_layout.html`** — "Office calendar" entry in the AWA menu and search index;
  `/calendar*` highlights it.
- **Tests** — `tests/test_calendar_page.py`.

## 2026-10-09 (unreleased — office calendar A2: scope rules, no visible change)

- **`office_calendar.py`** (new) — the layer registry: `items_between(conn, user, start, end,
  scope=, layers=)` returns merged, sorted `CalItem` dicts from the `entries` and `holidays`
  providers. Visibility comes from the directory (`team_scope_for_user`), never the role: an
  unlinked account sees only bureau-audience items and its own; `audience='people'` is for the
  named people and creator only; an owner-less unit entry is for its own people only. The
  requested scope (blend/mine/section/division/bureau) can only narrow. Owner colour comes from the
  `calendar_unit_tones` setting (importer, B2); bureau-level units default to green.
- **Tests** — `tests/test_calendar_scope.py`. Nothing calls it yet, so `version.py` is not bumped.

## 2026-10-09 (unreleased — office calendar A1: storage only, no visible change)

- **`storage.py`** — new tables `calendar_entry`, `calendar_entry_person`, `calendar_entry_tag`,
  `calendar_entry_revision` (auto-created by `init_db`), and `cal_create` / `cal_update` /
  `cal_cancel` / `cal_restore` / `cal_delete` / `cal_get` / `cal_list_between` / `cal_revisions`.
  Sequence rises only on date/time/status/recurrence changes; stale-sequence saves raise
  `CalendarConflict`; cancel is a soft delete restorable for 30 days; `import_key` makes
  re-import idempotent. Nothing reads these yet, so `version.py` is not bumped.
- **Tests** — `tests/test_calendar_storage.py`. Plan: `docs/OFFICE_CALENDAR_PLAN.md` (increment A1).

## 2026-10-09 (v3.53 — wellness register PDF: office is BLHSD, footnote removed)

- **`storage.py`** — `wellness_person_month` returns `office = BLHSD_NAME` for everyone
  (was the person's org-unit short name).
- **`wellness_register.py`** — dropped the closing footnote (which also still said
  "CSS Information System").
- **Rename** — remaining "CSS Information System" mentions (README, QA playbook,
  requirements.txt, `ux_handoff.py` app context) now say Office Connect.

## 2026-10-09 (v3.52 — Admin Head's own requests escalate to the Director)

- **`storage.py`** — new `_escalation_rank`: an "Admin Head"/"Administrative Head" keeps rank 1
  (the section-chief seat for their own staff) but their OWN wellness/AWA requests follow the
  division-chief hop to the Director. Used by `get_approvers_for`, `approver_name_for` and
  `approver_title_for`. Test: `test_admin_head_escalates_to_director_but_still_chiefs_their_staff`.

## 2026-10-08 (v3.51 — photo crop editor shared with My profile and Welcome)

- **Photo crop** — the drag/zoom circular crop editor moved out of `staff_form.html` into
  `static/js/photo-crop.js` + `templates/_photo_crop.html` (`PhotoCrop.init`). `/me` and the
  Welcome page now use it too (they previously stored the raw upload with no crop), including
  the "Adjust size & position" button for an existing photo. Staff form behaviour is unchanged.

## 2026-10-08 (v3.50 — nickname on My profile)

- **`storage.py`** — new `admin_user.nickname` column (auto-migrated),
  `set_user_nickname()`, and `nickname` on `get_user_profile()` / `_admin_row()`.
- **`app.py`** — `/me` saves it; `_account_first_name()` returns the nickname
  first, so the home greeting reads "Hi, <nickname>".
- **`templates/me.html`** — Nickname field above Designation.

## 2026-10-08 (v3.49 — resource persons always need a topic; editable on the manage page)

- **Create form** — a resource person can no longer be saved without a topic (nor a
  topic without a person). Enforced in the browser (`required`) and on the server
  (`POST /create` re-renders with an error); previously a half-filled row was dropped
  silently and the activity was created with no resource persons.
- **Manage page (bureau activities)** — the read-only "Resource persons" card is now
  editable: add a person + topic, edit the topic any time, change the person or remove
  them while that speaker review has no responses. New speaker reviews inherit the
  activity's organizing section (`lead_org_id`). The `/activities/{token}/speakers`
  routes now work for any manageable activity, not just outside ones; outside activities
  can also swap the person (`storage.update_speaker_rp`).
- **Tests** — `tests/test_event_speaker_manage.py`.

## 2026-10-08 (v3.48 — bust the app.css cache)

- **`templates/dash_layout.html`, `templates/public_layout.html`** — `app.css?v=`
  bumped `20260924a` → `20261008a`. v3.47's dropdown fix lived only in `app.css`,
  and the unchanged query string let browsers keep serving the cached old file, so
  the menu still ran off the bottom on a laptop. **Bump this string whenever
  `app.css` changes.**

## 2026-10-08 (v3.47 — dropdown menu fits short screens)

- **`static/css/app.css`** — `.navgroup .menu` (desktop dropdown) gets
  `max-height: calc(100dvh - var(--topnav-h) - 16px)` (with a `vh` fallback) and
  `overflow-y:auto`, so the sixteen-entry CSS group scrolls instead of running off
  the bottom. The ≤780px hamburger already did this.
- Compact rules under `@media (min-width:781px) and (max-height:700px)`: hint lines
  hidden, row/heading padding tightened. Placed after the base `a`/`.mhint`/`.msec`
  rules so they win on equal specificity.

Checked in headless Chromium at 1280×800/600/1000, 1024×500 and 800×400: the menu
stays within the viewport and the last item ("Paper entry") scrolls into view.

## 2026-10-08 (v3.46 — custom registration questions)

- **`reg_questions.py`** (new, pure logic) — the question kinds, presets and rules:
  `parse_options`, `clean_question`, `collect_answers` (every answer is whitelisted
  server-side against the question's options; a checkbox group is read from the
  raw `parse_qsl` pairs) and `display_value`.
- **`storage`** — new tables `event_question` and `attendee_answer` (created in
  `_add_missing_columns` next to `event_link`), with `list_event_questions`,
  `get_event_question` (scoped to the event — the IDOR guard), `add_event_question`
  (max 20), `update_event_question` (kind locked once answered),
  `remove_event_question` (deletes, or archives once answered),
  `move_event_question`, `save_attendee_answers`, `get_attendee_answers` and
  `event_answers`. Deleting an attendee or merging duplicates clears or moves
  their answers; the roster, export and purge side are in the same release.
- **`app.py`** — manage-page routes `POST /activities/{token}/questions`,
  `/questions/preset`, `/questions/{qid}`, `/questions/{qid}/remove` and
  `/questions/{qid}/move` (creator/admin only, audited). `event_consent` validates
  and stores the answers (`_multi_from_pairs`, `_consent_text_for`); the consent
  notice gains one sentence only for an activity that has questions.
- **Templates / i18n** — a "Registration questions" card on `activity_manage.html`;
  the questions render on the public form and are re-posted by the "Is this you?"
  step in `link_tree.html`; new strings `lt_more_details`, `yes`, `no`,
  `consent_extra_answers`.

Tests: `tests/test_registration_questions.py`.

- **`reg_questions.py`** — `answer_rows` (one registrant's non-empty answers as
  display strings), `column_label` (adds " (removed)" for an archived question)
  and `tally` (counts per option for the active single/multi/yesno questions,
  with the display line precomputed).
- **`app.py`** — `monitor_event` loads the questions (archived included) and
  `event_answers`, sets `p["extra"]` per registrant and passes `answer_tally`.
  `monitor_event_export` passes them to `_build_monitor_xlsx(..., questions=(),
  answers=None)`, which now computes the column count (no more `end_column=8` /
  `"ABCDEFGH"`; `get_column_letter`) and appends one column per question; purged
  registrants' answer cells stay blank. An activity with no questions renders and
  exports exactly as before.
- **`templates/monitor_event.html`** — "Registration answers" `<details>` under the
  email (no new column) and a "Registration answers at a glance" card above the roster.
- **`storage.purge_expired_attendees`** — deletes the purged attendees' answers
  (same cutoff, before the UPDATE); `retention.py` wording updated. Answers are
  read only by `event_answers` / `get_attendee_answers`, from the creator/admin-gated
  monitor routes — never by reports, AI prompts or public pages.

Tests: `tests/test_registration_questions.py`.

## 2026-10-08 (v3.45 — team activities on the home strip and to-do)

- **`storage.event_feed_scope`** — the Monitor's "directory decides" scope, now
  shared (`app._event_feed_scope` delegates to it).
- **`storage.activities_by_creator(team_scope=...)`** — the home "Your recent
  activities" strip lists what the manager created OR what their team runs
  (events by organising unit / speakers' units, standalone forms by organising
  unit). Admins keep the all-creators view.
- **`office_connect._task_activities`** — the to-do strip uses the same scope, so
  an admin-filed activity for the section shows up for its manager.

Tests: `tests/test_team_scope.py`.

## 2026-10-08 (v3.44 — Monitor "Archive this activity" works again)

- **`templates/monitor_event.html`** — the copy/resend click handler was bound to
  every `.act-btn`, including the Archive and Remove submit buttons. It set
  `btn.disabled = true` inside the click, which cancels the form submission, so
  the button greyed out and nothing was archived/removed. The handler is now bound
  to `.act-btn[data-act]` only.

Tests: `tests/test_monitor.py`.

## 2026-10-08 (v3.43 — section managers manage their section's activities)

- **`app._can_manage_event(user, ev, conn)`** — only an admin or the activity's
  `created_by` could manage it, while `/monitor` already listed it for the
  organising section (team scope). A section manager therefore saw an
  admin-filed activity but was bounced off Manage / roster / export / reminders.
  With a `conn`, a user holding `manage_event` whose directory team is not
  "none" now manages activities passing `st.event_in_team_scope` — the same rule
  as the Monitor feed. Other sections and viewers/encoders stay locked out.
- **`storage.event_scope_paths`** — single-event version of the lead/speaker
  org paths that `list_events` already computes.

Tests: `tests/test_team_scope.py`.

## 2026-10-08 (v3.42 — concluded activities stay reachable in Monitor)

- **`/monitor?view=concluded`** — `/monitor` listed only upcoming/ongoing
  activities, so a finished activity's roster page (`/monitor/<token>`, which
  was never lifecycle-gated) had no link to it. A "Concluded" pill now lists
  concluded bureau activities that had registrations; the default view is unchanged.

Tests: `tests/test_monitor.py`.

## 2026-10-06 (v3.41 — wellness register prints the time range)

- **`wellness_register.time_range`** — the monthly register PDF printed only a
  break's start time. Each day cell now reads `16:00 - 17:00` (start + hours
  availed, wrapping past midnight); an unparseable start falls back to as-is.

Tests: `tests/test_wellness.py`.

## 2026-10-05 (v3.40 — AWA report no longer "not reported")

- **`storage.work_arrangement_day`** — a day reported as "awa" fell through to the
  filing-derived path and was still tagged `undeclared`. `undeclared` is now
  `asked and no report`, and `reported` is true for any report.

Tests: `tests/test_whereabouts.py`.

## 2026-10-05 (v3.39 — fix 500 on /css and dashboards)

- **`storage.concat_atoms`** — a delta whose category dtype disagreed with the
  cached frame raised `TypeError: dtype of categories must be the same`, which
  500'd every atoms-backed page. It now falls back to a plain concat +
  re-categorize (same result as a full rebuild).

Tests: `tests/test_atoms_cache.py`.

## 2026-10-01 (v3.38 — weekly roster: Who's in, Week view)

- **`storage.whereabouts_roster_week(conn, monday, user)`** — people × Mon-Fri.
  Built on the same pieces as `work_arrangement_day` (scope via
  `team_scope_for_user`, reported-over-filing precedence, holidays, "No AWA"), so
  the two views cannot disagree (tested day-by-day). A week straddling two
  half-month periods reads each day's own period. Unreported days are `plotted`
  (shown faded); Leave carries no reason, a Field location does. An unlinked
  account gets no roster.
- **`app.py`** — `/work-arrangement/roster?week=` for every signed-in user.
  "not reported" marks and the "Haven't reported this week" count (asked and
  reported no day) are shown only to chiefs / schedule viewers.
- **Templates** — `whereabouts_roster.html`; a Day | Week switch on Who's in; a
  link from the Report-my-week form.
- Not in this change (as agreed): weekly xlsx/pdf export, coverage flag, and
  reflecting weekly reports in the chief fortnight schedule's counts.

Tests: `tests/test_whereabouts.py`.

## 2026-10-01 (v3.37 — PH holidays and work suspensions)

Builds on v3.36 (weekly whereabouts).

- **`storage.py`** — `holiday` table (date, name, kind regular/special/suspension),
  seeded once with the 2026 PH calendar (`seed_holidays`, keyed in app_setting so
  admin deletions stick; Eid'l Fitr/Adha deliberately omitted — announced late).
  `get_holiday`, `holidays_between`, `list_holidays`, `set_holiday`,
  `delete_holiday`. A holiday day: carries no choice on the weekly form and is
  never saved to; reads "Holiday — name" in the Monday email; makes
  `work_arrangement_day` return no roster (so no one is undeclared that day).
- **`send_reminders.py`** — a week of five holidays sends no Monday email.
- **`app.py`** — `/admin/holidays` (admin, `manage_users`) + nav entry.
- Not changed: the fortnightly ANNEX C schedule, coverage warnings and exports
  still treat holidays as ordinary days.

Tests: `tests/test_whereabouts.py`.

## 2026-10-01 (v3.36 — weekly whereabouts)

Staff report where they will be each working day, once a week, and Who's in
shows it.

- **`storage.py`** — tables `whereabouts` (user, day, status office/field/leave/awa,
  field-only note) and `whereabouts_week` (emailed_at / submitted_at, the
  once-per-week guard). `whereabouts_defaults` plots a week from each person's
  ANNEX C filing (per-day period, so a week straddling the 15th/16th is right);
  `save_whereabouts_week` (this + next week only; `awa` refused where nothing to
  follow; note kept for field only). `work_arrangement_day` lets a reported
  office/field/leave override the filing and a "No AWA" tag; `awa` keeps the
  derived WFH/day-off. New day groups `field` and `leave`.
- **`auth.py`** — `make/verify_whereabouts_token` (uid + Monday, 10-day life).
- **`mailer.py`** — `whereabouts_week_message`, feature `job_whereabouts`
  (switchable in /admin/email, previewable).
- **`send_reminders.py`** — job `whereabouts` (`--whereabouts`): Monday (param
  `whereabouts_weekday`) with one day of catch-up; all active staff linked to a
  directory record, including "No AWA"; recorded per person only when the send
  succeeded, so a relay outage retries and nothing ever sends twice.
- **`app.py`** — `/whereabouts/week` (signed link, public prefix) and
  `/work-arrangement/week` (signed in). **Templates** — `whereabouts_week.html`;
  Who's in gains tiles, groups, a "reported" marker and a "Report my week" link.

- **Undeclared**: `whereabouts_week_tracked/nonresponders`, `undeclared` on
  `work_arrangement_day` (only people actually emailed, only once the week was
  sent); chiefs/schedule viewers see a "not reported" pill + "Haven't reported"
  tile. Jobs `whereabouts_nudge` (day after the email, once per person, never
  the same day it went out) and `whereabouts_rollup` (Tuesday by default,
  param `whereabouts_rollup_weekday`; once per chief per week; each chief's
  approvees via `get_approvers_for`). Field/Leave stay separate from "No AWA".

Tests: `tests/test_whereabouts.py`.

## 2026-09-25 (v3.31 — the area around the companion taps it)

The last dead clicks on the home greeting (v3.21 made the photo + name a
link) landed around the companion — `.oc-pet` itself, "*wiggles nose* Change
companion →" — and on the wellness hub the companion's name / "Stage 2 of 6"
text (`.avatar-box`). Only the `.avwrap` drawing responded.

- **`static/js/avatars.js`** — the tap handler also accepts a click inside a
  `[data-pet-area]` that isn't on a control, and plays the tap on that
  area's `.avwrap[data-interactive]` (same drag / pet / away guards).
- **`static/js/telemetry.js`** — `[data-pet-area]` joins `INTERACTIVE`.
- **`templates/office_connect.html`** (`.oc-pet`) and
  **`templates/wellness_hub.html`** (`.avatar-box`) — `data-pet-area`,
  pointer cursor.
- **Cache tokens** — `avatars.js`, `search.js` and `telemetry.js` bumped to
  `?v=20260925a`. The service worker serves static assets
  stale-while-revalidate keyed on the full URL, so a changed script under an
  unchanged token reached people one load late — including the telemetry
  changes of v3.20 / v3.24 / v3.26 and search.js's `csi:search`.

Tests: `tests/test_avatar_care.py`. Verified in headless Chromium on the
rendered wellness hub: a tap on the stage line bounces the companion and
records no dead click, while a click on a stat label still does.

## 2026-09-25 (v3.30 — one System page for the occasional admin screens)

The 30-day UX handoff: six Administrator menu entries opened a handful of
times a month — Backups 4, Audit 2, Sharing 2, Ops 1, UX Insights 1,
Learned rules 1 — beside the admin screens used daily (Users 106,
Feedback 30, Email 11, AI 7, AWA filing 7). All six are `manage_users`.

**`templates/_page_tabs.html`** — `system_header(active)`: kicker "System",
tabs Backups · Audit log · Sharing · System health · UX Insights · Learned
rules (ordered by use), on the shared `page_tabs`.

**`backups.html`, `audit.html`, `admin_sharing.html`, `ops.html`,
`ux_insights.html`, `admin_rules.html`** — `page_header(title, lede)` →
`system_header(key)` + the same lede; titles read "System · …".

**`app.py`** (`NAV_GROUPS`) — the Backups entry is labelled "System"; the
other five keep their keys (search + AI-navigate) with `in_nav: False`.
`ux_insights` now passes `nav_active: "ux_insights"` (it passed `""`).
**`dash_layout.html`** — `nav_cur` maps the five → the System entry.

Tests: `tests/test_page_tabs.py` (tab bar on all six, one menu entry,
search, still admin-only).

## 2026-09-25 (v3.29 — Invited events under Monitor, Name cleanup under Directory)

The two screens the 30-day UX handoff found never used: Invited events
(`/activities/outside`, its own CSS menu entry, 0 views) and Name cleanup
(`/directory/cleanup`, already off the menu behind one button, 0 views).

**`templates/_page_tabs.html`** (new) — `page_tabs(kicker, tabs, active)`,
the heading + tab bar Insights introduced in v3.28, lifted out so the other
screen families share it; plus `monitor_header` and `directory_header`.
**`_insights.html`** now builds its tabs and calls `page_tabs` (same markup
class, `page-tabs`).

- **Monitor**: `monitor.html` / `outside_events.html` — tabs "Bureau
  activities" · "Invited events".
- **Directory**: `directory.html` / `cleanup.html` — tabs "Org units &
  people" · "Name cleanup"; the old "⚙ Name cleanup tool" button is gone.

**`app.py`** — the Invited events nav item is `in_nav: False` (still in
search and an AI-navigate key); the Monitor hint names both.
**`dash_layout.html`** — `nav_cur` maps `outside` → Monitor and `cleanup` →
Directory for the menu highlight.

Tests: `tests/test_page_tabs.py`; `tests/test_insights_tabs.py` follows the
renamed tab-bar class.

## 2026-09-25 (v3.28 — the CSS dashboards as one tabbed Insights page)

The 30-day UX handoff: five separate CSS menu entries for the dashboards —
Pulse 19 views, People 30, Participation 21, Teams 7, Trends 3 — each a
menu round trip away from the next.

**`templates/_insights.html`** — `insights_header(active)`: an "Insights"
kicker, the tab's title, and a tab bar (Pulse · People · Participation ·
Teams · Trends, ordered by use; `aria-current` on the active one). Tabs carry
`org` everywhere and `period` among the four tabs that share its vocabulary —
Pulse's `win` (all / ytd / quarter / d30) is neither carried in nor out.
Scrolls sideways on a phone rather than wrapping.

**`pulse.html`, `people.html`, `participation.html`, `teams.html`,
`trends.html`** — `page_header("X")` → `insights_header("x")`; titles read
"Insights · X". Each tab is still its own page at its own URL, so links,
exports and drill-downs are unchanged.

**`app.py`** (`NAV_GROUPS`) — the Pulse entry is labelled "Insights"; People,
Teams, Trends and Participation keep their keys (still AI-navigate
destinations) but are `in_nav: False`, so the search palette still lists
them. **`dash_layout.html`** — a separate `nav_cur` lights the Insights entry
on all five; `cur` stays each page's own key, since saved views, the page tour
and `PAGE_KEY` are keyed on it.

Tests: `tests/test_insights_tabs.py`.

## 2026-09-25 (v3.27 — "Your to-do" leads the home screen)

The 30-day UX handoff: `/` is the most-visited screen (523 views, 33 users)
and the biggest exit, and people leave it for the same self-service tasks —
apply for a break (`/wellness/apply`, 25 users), file a work arrangement
(29), clear approvals (home → approvals 70×), open an activity's Monitor
(`/css` → `/monitor/{token}` 131×) — while the page leads with team charts.

**`office_connect.home_tasks(conn, user, today=None)`** — one card per task,
each `{key, icon, tone, title, detail, cta, url}`, sorted to do → waiting →
info → done. Built straight from storage (not `team_view_data`), so it works
for an account with no directory link, and each source is isolated in its own
try so one failing never empties the strip:
- `_task_approvals` — `pending_approval_counts` → `/approvals`.
- `_task_wellness` — an approved break on/before today → its check-in page;
  else hours left this week → `/wellness/apply`; else a pending request
  (waiting) or all hours booked (done).
- `_task_awa` — the earliest open filing period: not filed → `/work-arrangement/file`
  with the deadline; pending → waiting; approved → done; "No AWA" or a shut
  window → nothing.
- `_task_office_today` — `work_arrangement_day` headcount → `/work-arrangement/day`
  (weekdays only).
- `_task_activities` — `manage_event` accounts: up to 3 of their own
  upcoming/ongoing bureau activities, "X of Y finished" → `/monitor/{token}`.

**`app.py`** (`choose`) passes `tasks`. **`templates/office_connect.html`** —
the "Your to-do" strip under the greeting; the amber approval notes are
skipped when the strip already carries approvals.

Tests: `tests/test_wellness.py`, `tests/test_work_arrangement.py`,
`tests/test_monitor.py`.

## 2026-09-25 (v3.26 — the measurement the 30-day handoff was missing)

The handoff's "what instrumentation is missing" list: no task success or
failure signal, no search volume (only empty searches), no page timing, no
device split, no app version per event, no per-role view of screens.

**`static/js/telemetry.js`** — `pageview` gains `meta.vp` (phone < 640 px,
tablet < 1024, else desktop). New events: `page_timing` (navigation timing
`ttfb_ms` / `dom_ms` / `load_ms`, after `load`), `form_submit` (the other half
of `form_abandon`, same opt-outs), `form_error` (the page rendered a
`.flash.err` banner; `meta.from` only, never the text), `search` (from a new
`csi:search` event, `meta.hits`, no term).

**Search dispatchers** — `_telemetry.search_signal(term, hits)` (fires
`csi:search`, plus `csi:search-empty` at zero) replaces
`search_empty_signal` in `search.html`, `encode_home.html`, `people.html`;
`static/js/search.js` (once per settled term, page + DB hits) and
`help.html` (in its existing 600 ms debounce) dispatch it too.

**`app.py`** — `_clean_telemetry_meta` validates `hits`, the three timings
(0–600 000 ms), `vp` (fixed vocabulary), and now keeps a legitimate `0`.
`_stamp_version` adds `meta.v` (APP_VERSION) to every ingested event.
`_metrics_gate` → `_record_http_error`: a 403/404/5xx returned to a signed-in
person becomes an `http_error` row (`meta.status`, `meta.method`), skipping
static assets, the beacon and the monitor stream. `http_error` is
server-only (`ui_telemetry.SERVER_EVENT_TYPES`) — the beacon can't send it.

**`ui_telemetry.py`** — `task_outcomes`, `search_stats`, `page_speed`
(median + p90, ≥ 3 samples), `device_mix`, `screens_by_role`,
`events_by_version`; the first four join `build_digest`.

**`ux_handoff.py`** — vocabulary rows for the new types; sections 10 Task
outcomes, 11 Search, 12 Page speed and devices, 13 Screens by role, 14 Events
by app version (appendix is now 15). **`templates/ux_insights.html`** — "Where
tasks go wrong" and "Search & speed" cards.

Tests: `tests/test_telemetry_ingest.py` (new fields, server http_error,
version stamp), `tests/test_ux_handoff.py` (every new section).

## 2026-09-25 (v3.25 — one approvals inbox)

The 30-day UX handoff showed the same 13-14 approvers opening
`/wellness/approvals` and `/work-arrangement/approvals` one after the other
from the home screen (35 + 35 trips). Both queues already gate on the same
check (`storage.user_is_wellness_chief` *is* `user_is_approving_chief`).

**`app.py`**
- `GET /approvals` (`approvals_inbox`) — both queues, forbidden to
  non-approvers; carries `ok` / `err` / `period` (the AWA "decided period"
  ANNEX C link moved here).
- `GET /wellness/approvals` and `/work-arrangement/approvals` keep their own
  403 gate, then 303 to `/approvals#wellness` / `#awa` via `_inbox_url`, so
  emails already sent and bookmarks still land in the right queue.
- Both decide handlers redirect back to the inbox section.
- Nav (both "Approvals" items), the bell, and the approval-request emails
  point at the inbox.

**Templates** — `approvals.html` (new page: per-queue counts as jump links, a
non-empty queue first) and `_approvals.html` (the two queue tables as macros,
lifted unchanged from the removed `wellness_approvals.html` /
`work_arrangement_approvals.html`; the wellness table is now `resp-table`, so
it stacks on a phone). `dash_layout.html`, `office_connect.html`,
`wellness_hub.html`, `work_arrangement_hub.html`,
`work_arrangement_schedule.html` link to the inbox.

**`office_connect.py`**, **`send_reminders.py`** — home notes and the weekly
digest link to the inbox sections.

Tests: `tests/test_wellness.py` (inbox, redirects, gate, decide → inbox);
URL assertions updated in `tests/test_search.py`, `tests/test_bureau_access.py`,
`tests/test_notifications.py`, `tests/test_send_reminders.py`.

## 2026-09-25 (v3.24 — client errors say where they happened)

All 9 client errors in the 30-day UX handoff read just "Error": the capture
sent name + message, but no location, and neither the digest nor the handoff
showed the message.

**`static/js/telemetry.js`** — `errorMeta()` adds `source` (same-origin →
masked path, query dropped; otherwise `external:<host>` only), `line`, `col`,
and up to 3 `frames` ("fn /path:line:col", parsed from V8 and Firefox/Safari
stacks). The `error` listener is now capture-phase so a failed `<script>` or
stylesheet load is recorded as `ResourceError`. Unhandled rejections carry
their stack frames.

**`ui_telemetry.py`** — `clean_error_source`, `clean_error_frames` (each frame
re-validated against that one shape, else dropped), `clean_line_number`,
`error_location`. `errors_by_route` groups by route + name + message +
location (falling back to the top frame) and carries `message`, `location`,
`frames`.

**`app.py`** (`_clean_telemetry_meta`) and **`ux_handoff.py`**
(`_resanitize`) run those cleaners at ingest and at export. The handoff's
"Client errors" table gains message + location columns and a top-frames list;
**`templates/ux_insights.html`** shows message + location.

Tests: `tests/test_ui_telemetry.py`, `tests/test_telemetry_ingest.py`,
`tests/test_ux_handoff.py`.

## 2026-09-25 (v3.23 — "Remind N not finished" on Monitor)

Spot Feedback (Sept 23): "I want to add a reminder feature for the
participants (PAX)". Monitor only had a per-registrant Resend.

**`app.py`**
- `POST /monitor/{token}/remind-unfinished` — creator/admin only. Refuses a
  closed activity or a lapsed response window (409), no mail transport, the
  `css_reminder` feature switched off, and a repeat within
  `REMIND_UNFINISHED_COOLDOWN_MIN` (60, per event, stamped in app_setting
  `monitor_remind_unfinished.<event_id>` BEFORE sending; 429). Recipients:
  `_unfinished_with_email` — status ≠ completed, not purged, email on file —
  each with their own recovery/resume link. Sends run after the response in
  one `BackgroundTask` (`_send_reminder_batch` → `_send_and_log`, one
  email_log row each); one audit row per round.
- `monitor_event` passes `remind_count`, `remind_last`, `remind_wait`,
  `email_on`.

**`mailer.py`** — `css_reminder_message` (text + HTML), `FEATURES["css_reminder"]`
(transactional, admin-toggleable), preview sample.

**`templates/monitor_event.html`** — the toolbar button (confirm dialog;
disabled during cooldown or with no email transport) and a live status line.

Tests: `tests/test_monitor.py` (recipient filtering, cooldown, closed,
lapsed window, no transport, access).

## 2026-09-25 (v3.22 — tell a relay that never ran apart from a garbled confirmation)

The Sept 22–23 Monitor feedback ("Email send failed: mail relay did not
return JSON") was answered by v3.07 (#147), which treats every 200 non-JSON
reply as "likely sent" so an admin is never nudged into a double-send. That
also swallowed the one case that is certainly NOT sent: web-app access not
set to *Anyone* (common on Workspace accounts that only allow "Anyone within
the domain"). Google then 302s the anonymous POST to accounts.google.com and
its sign-in page answers 200 — the script never ran.

**`mailer.py`**
- `_relay_not_run_reason(resp)` — classifies a 200 non-JSON reply by the URL
  the redirects ended on: `accounts.google.com` / `ServiceLogin` → access not
  *Anyone*; any host other than `script.googleusercontent.com` with Apps
  Script's own error text (`Script function not found: …`, `Authorization is
  required…`) → the script couldn't run. Either is a definite failure (no GET
  retry, `send_status` → `failed`). The echo URL keeps v3.07's behaviour.

**`docs/MAIL_RELAY_SETUP.md`** — two new rows in "If something fails".

Tests: `tests/test_mailer.py`.

## 2026-09-25 (v3.21 — make the most-clicked dead spots actionable)

From the 30-day UX handoff, once v3.20 filtered out telemetry noise: the
places staff repeatedly clicked that did nothing.

- **`storage.avatar_growth_actions`** — each point action carries an `href`
  (`/wellness/apply` or `/wellness`); **`templates/_growth.html`** renders it
  as a link. "Take a wellness break +10" on the home growth card was the top
  real dead-click spot (30 clicks, 7 users).
- **`templates/office_connect.html`** — the hero's photo + greeting are one
  `.oc-me` link to `/me`; the "Who is in the office" headline count is a link
  to `/work-arrangement/day` (the footer link stays).
- **`templates/monitor_event.html`** — Copy button beside the registration
  link (clipboard, `prompt()` fallback); the `<code>` is `user-select:all`.
- **`storage.get_work_arrangement`** — adds `week_override_note_approver`
  (the same sentence with the filer's name in place of "your", via
  `_wa_week_note(owner=)`) and `week_override_period`; new
  `_wa_week_override_other` so the conflict is looked up once.
  **`templates/work_arrangement_approvals.html`** shows the third-person note
  with a link to that period's schedule.

Tests: `tests/test_avatar_care.py`, `tests/test_work_arrangement.py`,
`tests/test_monitor.py`.

## 2026-09-25 (v3.20 — UX telemetry stops ranking its own noise)

The 30-day UX handoff (v3.19 build) put the companion's Feed buttons, the
`/me` signature pad and `html > body` clicks at the top of the friction
board. None of those is a broken control: rage bursts on a real `<button>`
were scored ×3 like a dead affordance, every signature stroke is a "click"
on a non-interactive `<canvas>`, and clicks on empty space / at the end of a
text selection were recorded as dead clicks carrying the whole page's text.
Resolved route-level Spot Feedback from June–July was also boosting every
hotspot on the same route, and the handoff repeated those comments once per
opportunity.

**`static/js/telemetry.js`**
- New `NON_ACTIONABLE` (`canvas, [data-ux-ignore]`), `isBackground()` (target
  is `html`/`body`/`main`/`#maincontent` itself) and `endsTextSelection()`
  guards — such clicks record neither a dead nor a rage click.
- A rage burst on an element matching `INTERACTIVE` is still sent, with
  `meta.interactive: true`.

**`app.py`** — `_clean_telemetry_meta` keeps `interactive` (literal `True` only).

**`ui_telemetry.py`**
- `NON_ACTIONABLE_SELECTORS` filters background/canvas selectors server-side
  too, so rows recorded before this fix (still inside retention) re-rank now.
- `is_interactive_rage()` — `meta.interactive`, or for older rows a selector
  whose last segment is a control tag. Counted as `rapid_taps`, scored ×1.
- `correlate_feedback` — route-only matches attach only OPEN feedback; exact
  element matches attach whatever the status (flagged `exact`). Only open
  feedback earns `FEEDBACK_BOOST`; a resolved exact match gets a "fix may not
  have landed" hint instead.

**`ux_handoff.py`** — "rapid taps" column; matched feedback listed once in a
"Spot Feedback matched to these opportunities" section naming the ranks it
matches; vocabulary and scoring text updated.

**`templates/ux_insights.html`** — rapid-tap signal and scoring note.

Tests: `tests/test_ui_telemetry.py`, `tests/test_ux_handoff.py`,
`tests/test_telemetry_ingest.py`.

## 2026-09-25 (v3.19 — a section's division chief can cover it AS division chief)

Follow-up to v3.18's OIC redirect. `set_section_oic`'s picker only ever
offered someone from the covered section itself. The ask: let a section's
own division chief be assigned too — a natural pick, since they already
decide a section chief's own requests — but once assigned, they should be
recognized as covering it AS the division chief they really are, not as a
generic "acting OIC" stand-in.

That distinction isn't cosmetic: v3.18's OIC redirect (`_oic_override_seat`)
unconditionally routed an OIC's own requests one rung above the seat they
cover. Applied blindly to a division chief covering their own section, that
would have redirected their own claim to "rank 2 in the parent division" —
their OWN seat, excluding themselves — leaving them with no approver at all.

**`storage.py`**
- `_oic_override_seat(oic_unit, own_rank)` — now takes the OIC's own
  substantive rank and returns `None` (no redirect) when `own_rank` already
  meets or exceeds `_ORG_LEVEL_RANK` for the seat they're covering. A
  section-level seat is rank 1, so a division chief (rank 2) covering one no
  longer gets redirected — their own requests keep escalating through their
  real rank (division chief → Director), same as if they held no OIC
  assignment.
- `get_approvers_for`, `approver_name_for`, `approver_title_for` — compute
  the account's substantive rank *before* consulting the override now (they
  needed it anyway for the fallback branches), and pass it through.
- `get_section_oic` / `list_section_oics` — new `by_right` field: is this
  delegate covering the seat because they already outrank it (a division
  chief on one of their own sections) rather than as a stand-in below their
  rank? Joins `org_unit` for the covered seat's level to compare against
  `_ORG_LEVEL_RANK`.

**`app.py`**
- `admin_users` — `section_accounts` now also lists each section's parent
  division chief(s), labeled `"<name> (Division Chief)"`, alongside
  same-section staff.
- `admin_users_section_oic_set` — validation now accepts either a
  same-section staff account (rank 0) or the section's own parent division
  chief (rank 2, confirmed against the parent `org_unit`), not just
  same-section staff. Audit summary and flash message read "Division chief
  for ..." / "...as division chief" for that case, "Temporary OIC" / "acting
  OIC" otherwise.

**`templates/users.html`** — the panel and column now say "Covering" rather
than assuming "Acting OIC"; shows "as division chief" or "acting OIC" next
to the current delegate's name, and the same distinction in the remove
button's confirm text.

**`tests/test_section_oic.py`** — extended the shared `org` fixture with a
Director account (to exercise the escalation past the division chief) and
an `outsider` in a wholly unrelated section (for the "must belong to the
section, or chief it" refusal test, now that the division chief itself is a
legitimate pick and can no longer stand in for "someone from elsewhere").
Added: the division chief may cover one of their own sections; their own
request is unaffected by doing so (still escalates to the Director, not
swallowed by the override); `get_section_oic(...).by_right` is set
correctly; the admin route accepts the division chief, labels the picker
option, and audits/flashes it distinctly. Also added teardown cleanup to
the `org` fixture itself — global rank-3 lookups (`_org_accounts_at_rank`
for the Director) aren't scoped to one org_unit, so the fixture's own
Director account has to be cleaned up after each test, not just before the
next one, or it leaks into other test files' escalation assertions.

**`tests/test_director_and_oic_routing.py`** — the division-level-OIC test
added in v3.18 asserted an exact `get_approvers_for(...) == [director]` /
`approver_name_for(...) == "RD-Director"`; loosened to membership/substring
checks (the same idiom `test_wellness.py`'s escalation tests already use),
since Director lookups are bureau-wide and other test files' fixtures can
leave other Director-ranked accounts around in a full-suite run.

## 2026-09-25 (v3.18 — Director auto-approval + OIC self-routing)

Two edge cases in the shared escalation chain (`storage._org_rank` /
`get_approvers_for`, STAFF_ONBOARDING_AVATAR_PLAN.md §7a.2):

1. The Director has nobody above them in the chain, so their own wellness
   break and work arrangement filings sat `pending` on the admin fallback
   until an administrator happened to pick it up. They're now auto-approved
   the moment they're filed.
2. An acting OIC's (`set_section_oic`) own requests still routed through
   their substantive rank — for an OIC standing in for a section chief on
   leave, that meant their own claim went to that same (absent) chief. Their
   own requests are now redirected a rung above the seat they're covering
   instead: covering a section escalates like a section chief would (to the
   division chief); covering a division escalates like a division chief
   would (to the Director).

**`storage.py`**
- `_is_director` + `_AUTO_APPROVE_NOTE`: rank-3 check and shared note used by
  the auto-approval path.
- `create_wellness_claim` inserts the claim as `approved` (with
  `decided_by`/`decided_at`/`decide_note` set) instead of `pending` when the
  filer is the Director.
- `_wa_apply_decision`: the approve/deny core of `decide_work_arrangement`
  (resolve-week safety check, superseding the row a change replaces, the
  status/decided_by/decided_at/decide_note update) pulled out into its own
  function so it can be called both from a human decision and from
  auto-approval. `decide_work_arrangement` itself is now a thin wrapper.
- `create_work_arrangement` and `request_work_arrangement_change` call
  `_wa_apply_decision` right after filing when the filer is the Director.
- `_oic_org_unit_for`: which org unit (if any) an account currently stands
  in as acting OIC for.
- `_oic_override_seat`: maps that unit to the (rank, org_path) one rung
  above it — a section's covering OIC maps to the division chief rank in the
  parent division; a division's covering OIC maps to the Director.
- `get_approvers_for`, `approver_name_for`, `approver_title_for` all check
  `_oic_override_seat` first and, when set, route/name/label off it instead
  of the account's substantive rank. Self-exclusion (an OIC can never be
  their own approver) still applies via the existing `exclude_uid` plumbing.

**`tests/test_director_and_oic_routing.py`** (new) — Director auto-approval
for a wellness claim, a work arrangement filing, and a work arrangement
change (including that the change still supersedes the row it replaces);
a non-Director's filings are unaffected; a section-level and a
division-level OIC's own requests redirect to the division chief / Director
respectively, in both `get_approvers_for` and the apply-page copy; an OIC
still never approves their own request; clearing the OIC restores the
normal chain.

## 2026-09-25 (v3.17 — ANNEX C downloads point at the period that was approved)

Reported as "Gilbert Canoy was approved but does not appear in the
downloadable PDF". The export was correct; the approver was downloading the
wrong period. Filings are only accepted for upcoming periods (the current one
closes the Friday before it starts), but `/work-arrangement/schedule` — the
only page with the ANNEX C buttons — defaults to
`work_arrangement_schedule_period()`, the period being worked. Approving an
October 1-15 filing and clicking "ANNEX C (PDF)" therefore produced the
September 16-30 sheet, where that person's row is blank.

**`app.py`** — `work_arrangement_schedule` builds an `upcoming` summary for
the next period when the page is on the current schedule period and that
next period already has filings or No AWA tags. `work_arrangement_decide`
now redirects with `&period=<decided period>`, and
`work_arrangement_approvals` validates it into `decided_period` /
`decided_period_label`.

**`templates/work_arrangement_schedule.html`** — amber callout above the
period panel with the upcoming period's approved/waiting counts and its own
View / PDF / Excel links.

**`templates/work_arrangement_approvals.html`** — after a decision, a line
under the flash links to that period's schedule and annex downloads.

**`tests/test_work_arrangement.py`** — covers the redirect, both links, and
that the upcoming period's export carries the approval.

## 2026-09-24 (v3.16 — avatar companions wear rank regalia that grows with wellness stage)

Companions already had six growth stages driven by wellness points, but
leveling up only changed the creature's own species-specific body art —
nothing signaled "you've earned something new" the way the existing monthly
seasonal accessory does for the calendar.

**`templates/_avatars_art.html`** — new `_regalia(s, x, y, k=1)` and
`_pot_regalia(s, x=60, y=112)` macros: a five-tier rank outfit (bronze collar
→ silver bandana → gold medal → royal cape, jeweled at stage 6) derived
purely from the wellness stage already threaded through every species macro
— no new schema, columns, or progression track. Each stage replaces the last
rather than stacking. Anchored at a neck/chest point distinct from the
existing monthly `_accessory`/`_pot_bow` slot so a seasonal hat and an earned
rank item never compete for the same spot. Wired into all 16 catalog
species: the 9 headless potted species get the `_pot_regalia` rim-sash
variant; the 7 bodied species get a per-species tuned neck/chest anchor.
`_cat` (stage ≥5), `_dog` (stage ≥4) and `_turtle` (stage ≥5) previously drew
their own one-off neck flourish at their own stage — replaced with the
unified system so every species now shares one consistent rank ladder
starting at stage 2.

**`static/js/avatars.js`** — new `checkLevelUp()`: compares each interactive
companion's current `data-stage` against the last one seen (localStorage,
keyed per species so a species change is never read as a level-up) and, on
an increase, announces the new gear through the existing `badgeToast()` +
`play("badge")` used for freshly-earned wellness badges. Scoped to
`[data-interactive]` only, so viewing someone else's companion on a person
page never fires their level-up.

**`templates/_avatars.html`** — bumped the `avatars.js` cache-bust query
string so the new behavior isn't served stale from a cached copy.

## 2026-09-24 (v3.14 — pages use the whole screen on laptops and monitors)

Reported off two screenshots on a ~1900px monitor: Admin → Users and the
Office Connect home both sat in a 980px strip with roughly half the screen
bare, and the Users "Staff accounts" table didn't even fit that strip, so the
Role/Sees pickers dropped their Apply under them and the actions column was
clipped ("Send reset lin…").

**Root cause:** one hard cap. `.wrap` (every signed-in page's `<main>`), the
topnav and the scope bar were all `max-width:980px`; on top of that several
pages added their own even narrower wrapper (Directory 780px with seven
tables, home 1000px, Office Connect 1040px, …).

**`static/css/app.css`** — new `--page-max` token (1600px) drives `.wrap`,
`.topnav .inner`, `.scopebar .inner` and `.scopeform`, so nav, scope bar and
content always share one edge. Two opt-in tiers keyed off
`body[data-width]`: `full` raises `--page-max` to 1920px (nav follows);
`narrow` caps only the content column at 800px, centred, so the nav doesn't
jump between pages. Side padding goes to 1.5rem at ≥1200px (nav/scope bar
match). The `resp-table-wide` stacking breakpoint moves 960 → 1180px — the
Users row needs ~1060px, so a 1024px laptop was still scrolling it sideways.

**`templates/dash_layout.html`** — `<body data-width="{% block page_width %}{% endblock %}">`.
`full`: users, directory, audit, reports, work_arrangement_schedule,
wellness_dashboard, feedback_board, backups, cleanup. `narrow`: form_create,
staff_form, wellness_apply, wellness_reflect, work_arrangement_file, me,
welcome, start, help, arta_link, external_rp_form, result, admin_sharing,
admin_email, encode_form, arta_entry_edit, monitor_attendee_response.
Everything else takes the default.

**Per-page caps removed** (they'd now fight the container): directory
`.dwrap`, cleanup `.cwrap`, admin_ai `.aiwrap`, ux_insights `.uxwrap`,
office_connect `.oc`, home `.hwrap`, monitor_event / activity_manage /
outside_manage `.mwrap`, monitor_outside `.twrap`, shared `.swrap`. Form
pages keep their own tuned widths inside the narrow column.

**Grids re-tuned for the wider box:** `office_connect.html` `.oc-panels` is
now explicit — 1 column on phones, 2 with the 3rd card spanning at ≥700px,
3 across at ≥1280px (auto-fit would have fit 3 and then the v2.72
`:last-child` span stranded the 3rd card on its own row). `people.html`
grid gets a 4th column at ≥1280px. `users.html` keeps each picker beside its
Apply and the action buttons on one line at ≥1440px, where the row fits.

**`tests/test_landing_fork.py`** — the colour-token test anchored its slice
of the page's `<style>` on the removed `.oc { max-width` rule; it now
anchors on `.oc-hero {`, the block's first rule.

**`app.css?v=`** → `20260924a`; **`version.py`** → v3.14.

**Verified:** Playwright pass on a seeded DB at 1920/1440/1280/1024/375px
across home, Users, Directory, CSS home, Audit, Reports, Wellness
dashboard/apply, AWA schedule/approvals, Me, Help, Ops, Email, Activities —
topnav and content edges match at every width, and no page scrolls
sideways that didn't already. The Users table fits its panel with no
horizontal scroll at 1024 (stacked), 1181, 1200, 1280, 1366, 1440 and 1920.
Two phone-width overflows (Wellness dashboard +229px, AWA schedule +649px at
375px) are identical on `main` and untouched here. pytest: same result as
`main` — the only failures are six that need a populated `css_is.db`
(ai_report_draft ×3, home_feeds, integrity, search), which fail identically
on `main` against an empty database.

## 2026-09-24 (v3.13 — the Temporary OIC picker excludes the section's own chief)

Follow-on from v3.12: once Alexander Medel resolved correctly as the
Administrative Section's chief, he then showed up as a selectable option in
that same section's "Temporary OIC" picker on Admin → Users — i.e. the
system offered him as a stand-in for his own leave.

**`app.py`** — `admin_users`'s `section_accounts` (the eligible-delegate list
per section) now excludes anyone who already resolves to `_org_rank(...) !=
0` for that section — the chief (or, in principle, any chief-ranked seat)
isn't offered as their own section's stand-in. `admin_users_section_oic_set`
gets the matching server-side check, so a tampered POST naming the chief
anyway is refused with the same error as naming someone from a different
section.

**`tests/test_section_oic.py`** — new
`test_the_chief_is_not_offered_as_their_own_sections_delegate`: the picker's
rendered `<option>` for the chief is absent while the eligible deputy's is
present, and POSTing the chief's own id is refused. The rest of the section
_oic suite (13 tests total now), `tests/test_team_scope.py`,
`tests/test_work_arrangement.py`, `tests/test_wellness.py`,
`tests/test_wellness_escalation.py`, `tests/test_bureau_access.py` and
`tests/test_auth_rbac.py` all still pass.

**`version.py` / `CHANGELOG.md`** — bumped to v3.13.

## 2026-09-24 (v3.12 — "Admin Head" now resolves to a section chief)

Reported: Administrative Officer IV Alexander Medel is the chief of the
Administrative Section, but the system wasn't treating him as its automatic
approver.

Root cause is the same class of miss `_org_rank`'s own comments already
document for the Director (Spot Feedback #76): rank is read from the
directory's `designation` field, matched case-insensitively as a substring
against `"section head"` / `"section chief"`. The Administrative Section's
chief carries the designation `"Admin Head"` instead — a real, in-use
variant that never matched — so he resolved to rank 0 (same as a line
staffer), and the section's wellness break and AWA requests had nobody in
the directory to escalate to.

**`storage.py`** — `_org_rank` now also matches `"admin head"` and
`"administrative head"` as rank 1 (section chief), alongside the existing
`"section head"` / `"section chief"` match. No table/route changes: every
caller built on `_org_rank` (`get_approvers_for`, `user_is_approving_chief`,
`approver_name_for`/`approver_title_for`, the wellness + AWA escalation
chains, `team_scope_for_user`) picks this up automatically.

**`tests/test_team_scope.py`** — `test_admin_head_is_recognized_as_a_section_chief`:
`_org_rank` resolves `"Admin Head"`, lower-cased, and `"Administrative
Head"` to rank 1, while a designation that merely contains the word "head"
(`"Head Nurse"`) still doesn't. `tests/test_work_arrangement.py`,
`tests/test_wellness.py`, `tests/test_wellness_escalation.py`,
`tests/test_bureau_access.py` and `tests/test_section_oic.py` still pass
unchanged.

## 2026-09-24 (v3.11 — a temporary OIC for wellness + AWA approvals, per section)

Request: give admins a way to assign a temporary OIC/approver for wellness
breaks and work arrangement (AWA) requests when a section's chief is on
leave — a toggle per section, one delegate at a time.

**`storage.py`** — new `section_oic` table, keyed by `org_unit_id`
(`PRIMARY KEY`), so "one delegate at a time per section" is enforced by the
schema itself: `set_section_oic` upserts (replacing whoever held it),
`clear_section_oic` deletes the row. `get_section_oic` / `list_section_oics`
resolve the delegate's display name for the admin page; `is_section_oic`
answers whether an account currently stands in for ANY unit.
`get_approvers_for` now ADDS the acting OIC for the covering unit (the
requester's own section, or the parent division for a section chief's own
request) alongside the substantive chief — never instead of them, via the
new `_with_section_oic` helper — so an early return from leave is never
locked out by a forgotten delegate. `user_is_approving_chief` now also opens
the approvals queue for a delegate who holds no chief seat of their own, and
`approver_name_for` names the acting delegate (falling back to the
substantive chief) on the apply/hub copy so staff see who will actually
decide their request today. Two new audit actions, `set_section_oic` /
`clear_section_oic`, under a new "Approvals" category.

**`app.py`** — `/admin/users` now also loads each section's current
delegate and the active accounts eligible to become one (same-section,
active accounts only). Two new routes, `POST
/admin/users/section-oic/{org_unit_id}/set` and `.../clear`, both gated on
`manage_users` like the rest of that page; `set` re-validates server-side
that the picked account actually belongs to the section (defense in depth
against a tampered POST) and audits the change.

**`templates/users.html`** — a new "Temporary OIC — Wellness & AWA
approvals" panel above the staff table: one row per section, showing the
current delegate (if any) with a Remove button, or a picker + Assign button
drawn from that section's active accounts — the toggle the request asked
for.

**`tests/test_section_oic.py`** (new, 12 tests) — no delegate by default;
setting one adds them alongside the chief; only one at a time per section
(assigning a second replaces the first, not both); clearing restores the
plain chain; a delegate never approves their own request; a delegate with no
chief seat of their own still gets an approvals queue and can decide a
pending wellness claim end to end; the apply-page copy names the delegate
while active; the same mechanism covers a division-chief seat, not just a
section's; the admin routes are audited, gated to `manage_users`, and
reject an account that doesn't actually belong to the section.
`tests/test_bureau_access.py`, `tests/test_wellness.py`,
`tests/test_wellness_escalation.py` and `tests/test_work_arrangement.py`
still pass unchanged.

## 2026-09-18 (v3.03 — a section manager can add an external resource person)

Spot Feedback #90: "How can I add Resource Persons who are not from BLHSD?"
The `/create` speaker picker already lists external resource persons
alongside internal staff, but adding a *new* one lived entirely under
`/directory/*`, whose `_required_cap` gate is the coarse `"directory"`
capability — admin-only, covering org units, internal staff, archiving and
name-cleanup all at once. A `section_manager` (who already holds
`create_activity`) had no way to add the outside speaker they needed for
their own event, short of asking an admin.

**`auth.py`** — new `"add_external_rp"` capability, granted to
`section_manager` and `admin` (kept separate from `admin`'s blanket
`"directory"`, so it has to be listed explicitly there too).
**`app.py`**'s `_required_cap` now special-cases `/directory/external/new`
and `/directory/external` (the *add* routes only) to require
`"add_external_rp"` instead of falling through to `"directory"` — editing an
existing external RP (`/directory/external/{id}/edit`) stays under the
general, admin-only check, matching the narrower ask.

Since a section manager can't open `/directory` itself, the add
form's post-save redirect and its crumbs/cancel link now follow a `back`
query/hidden-field param (validated same-site-relative,
`_safe_back`) instead of a hardcoded `/directory` — so submitting the form
doesn't hand them a 403. **`templates/form_create.html`** adds a
"+ Add an external resource person" link next to the speaker picker
(`target="_blank"`, `back=/create`, with a hint to reload afterward — a new
tab so their in-progress survey form isn't lost). **`templates/
external_rp_form.html`** threads `back` through the same way for the edit
form too (unused there today, but keeps the two forms in sync); admin's
existing Directory → Add flow is unaffected (default `back` is still
`/directory`).

**`tests/test_auth_rbac.py`** —
`test_section_manager_can_add_external_rp_but_not_open_directory`: a
section manager can open the add form and successfully create an external
RP (verified in the DB, `is_internal=0`), redirected to the `back` target —
while `/directory`, `/directory/staff/new` and editing an existing external
RP all still 403 them. Full `tests/test_auth_rbac.py` (75 tests, all roles ×
all gated paths) plus `tests/test_directory_archive.py`,
`tests/test_directory_search.py`, `tests/test_create_duplicate_warning.py`,
`tests/test_bureau_no_rp.py` and `tests/test_outside_activity.py` pass.

## 2026-09-18 (v3.02 — the approver is now told when a break is withdrawn)

Spot Feedback #75: "how will I know if the approver was notified of my
cancellation?" Filing a break already emails the approver
(`wellness_approval`) and a decision already emails the claimant back
(`wellness_decided`) — withdrawal was the missing third leg, notifying no
one.

**`mailer.py`** — new `wellness_cancelled_message(approver_name,
claimant_name, break_date, start_time, hours, reason, link)`, folding in
v3.01's `cancel_reason` when given (`_note_box_html`, same as a denial's
`decide_note`). Registered as `"wellness_cancelled"` in `FEATURES`
(admin-toggleable from `/admin/email` like every other transactional email,
no template changes needed — that page already renders from the catalog)
and in `_PREVIEWS` (the admin preview/test-send catalog).

**`app.py`** — `POST /wellness/claims/{claim_id}/cancel` now works out who
to tell: if the claim was already `approved`, specifically whoever approved
it (`claim["decided_by"]` — they're the one now expecting a break that
isn't happening); if still `pending`, whoever it would have routed to
(`get_approvers_for`, the same set the original apply notified).

**`tests/test_notifications.py`** —
`test_wellness_cancel_of_a_pending_claim_notifies_the_approver` and
`test_wellness_cancel_of_an_approved_claim_notifies_the_decider`.
**`tests/test_email_admin.py`**'s catalog-completeness tests (every
`FEATURES` key needs a label/hint/group and a working preview sample) now
cover the new key too — full `tests/test_notifications.py`,
`tests/test_email_admin.py`, `tests/test_mailer.py`,
`tests/test_wellness.py` and `tests/test_wellness_escalation.py` suites
(over 190 tests) pass.

## 2026-09-18 (v3.01 — a documented reason when withdrawing a wellness break)

Spot Feedback #77: "Pop up window to record why withdrawing or cancelling
the wellness break for documentation." `wellness_claim` already carries
`decide_note` for the approver's side of a decision (e.g. a denial reason)
but had nothing analogous for the claimant's own withdrawal.

**`storage.py`** — new `cancel_reason TEXT` column (`CREATE TABLE` +
additive `ALTER TABLE` migration, same pattern as the other nullable
wellness columns). `cancel_wellness_claim(conn, claim_id, user_id,
reason="")` now stores it (trimmed, `None` when blank); `get_wellness_claim`
returns it.

**`app.py`** — `POST /wellness/claims/{claim_id}/cancel` is now `async`,
reads an optional `reason` field via `_posted()`, passes it through, and
folds it into the `wellness_cancel` audit summary when given.

**`templates/wellness_hub.html`** — the Withdraw button's `onsubmit` swaps
`confirm('Withdraw this break request?')` for a `window.prompt(...)` asking
why (the "pop up window" asked for); `null` (Cancel on the prompt) still
backs out of the withdrawal exactly as `confirm()` did, an empty answer
still withdraws with no reason recorded. The reason shows next to the
`cancelled` status pill afterward, mirroring how a denial's `decide_note`
already shows next to `denied`.

**`tests/test_wellness.py`** — `test_cancel_reason_is_recorded_and_optional`
(direct `storage` call, present-and-trimmed vs. absent) and
`test_http_withdraw_records_reason` (through the actual endpoint). Verified
live end-to-end (file a break → withdraw with a reason → the reason shows
on `/wellness` next to "cancelled" → the audit log carries it too) and the
full `tests/test_wellness.py` + `tests/test_wellness_escalation.py` suites
(55 tests) pass unchanged otherwise.

## 2026-09-18 (v3.00 — a light 3D lean for the wellness companion)

Spot Feedback #82: "make the pet 3d." Full 3D rendering is out of scope for a
spot fix, so this is a scoped, cosmetic polish in the same spirit rather
than a 3D engine: a tilt-card lean plus a contact shadow.

`templates/_avatars.html` (`avatar_defs()`) — `.avwrap` gets `perspective:
700px`; its SVG gets a permanent `filter:drop-shadow(...)` for a soft
"lifted off the page" contact shadow. The `avatar()` macro's inner sizing
`<span>` (already wrapping just the SVG) is now `.av-tiltstage`, the element
the lean rotates.

`static/js/avatars.js` — folded into the existing "curiosity" `pointermove`
+ `requestAnimationFrame` loop (the one that already turns the owl/dog/cat/
bird's head toward the cursor) rather than adding a second global listener.
For any `.avwrap[data-interactive]`, while the pointer is within the
companion's own bounding box, `.av-tiltstage` gets `rotateY`/`rotateX` set
from the pointer's offset from center (±10°/±8°), transition-free for
responsive tracking; leaving the box clears the transform with a `.35s`
settle transition. Runs for every species (not just the WATCH list used by
the head-turn), gated by the same `prefers-reduced-motion` check as
everything else in the file. Verified independent of the `.avwrap[data-drag]`
positioning transform used by the wellness hub's drag-to-move (different
element: outer `.avwrap` vs inner `.av-tiltstage`), and confirmed both work
together with Playwright.

## 2026-09-18 (v2.99 — a date field's calendar didn't always open on click)

Reported by the user (Spot Feedback #83): "there are times not clickable" on
`#collected_on` (Date collected) on the paper-entry form. Every
`input[type=date]` on the site is enhanced client-side (`static/js/app.js`'s
"Locale-proof date fields") by overlaying an invisible, full-size native
`<input>` on top of a fixed-format display box, so the ISO value stays
locale-proof. But a *native* date input itself splits clicks into a text
zone (focuses only) and a narrow calendar-icon zone (actually opens the
picker) — a split that no longer lines up with anything visible once the
control is stretched invisibly over the display box, so a click on most of
the box silently did nothing. Encoding many paper forms in a row (this
report's `?n=2` in the URL) means hitting that field over and over, which is
what surfaced it.

**`static/js/app.js`** — where `HTMLInputElement.prototype.showPicker`
exists (current Chrome/Edge/Safari), the real input's `pointer-events` is
now set to `none` and a `click` handler on the wrapper calls
`input.focus()` + `input.showPicker()` directly, so any click anywhere in
the box opens the calendar — the icon/text split no longer matters. Skipped
entirely in "raw" mode (the "Add specific time" datetime-local toggle),
where the real control is visible and already directly clickable, and on
browsers without `showPicker()`, where behavior is unchanged from before.

## 2026-09-18 (v2.98 — a right-edge nav dropdown ran off the screen)

Reported by the user (Spot Feedback #93): "yung dropdown lumalagpas sa
screen di na makita ang ibang choices" — a top-nav dropdown on
`/dashboard/participation` overflowed the screen, hiding its other choices.
`.navgroup .menu` (`static/css/app.css`) always anchors `left:0` against its
trigger `<summary>`, growing rightward with no viewport-edge awareness. For
a nav group sitting close to the right side of the bar — common once enough
groups are visible for a role to not all fit on one row before the
`780px` hamburger breakpoint — the menu's right side ran past the window
edge with nothing to scroll it into view.

**`static/js/app.js`** — a new `toggle` listener on every `details.navgroup`
checks the opened `.menu`'s `getBoundingClientRect().right` against
`window.innerWidth` and adds a `menu-flip` class when it would overflow,
clearing it again on close.
**`static/css/app.css`** — `.navgroup .menu.menu-flip { left:auto; right:0; }`
anchors the menu to its trigger's right edge instead, so a menu that would
have overflowed opens leftward and stays fully on-screen; menus that
already fit are untouched.

*(Spot Feedback #81, "the wellness break date defaults to blank," was fixed
as a one-line change on top of the old `<input type=date>` field in an
earlier draft of this branch — superseded before merging by the date-pill
picker below, whose own `loop.first` default covers the same case. No
separate diff for it here.)*

## 2026-09-18 (v2.97 — wellness breaks: current work week only, down from 4 weeks)

Policy change: plans made weeks ahead were routinely getting cancelled or
rescheduled by the time the week actually arrived, so the scheduling window
shrinks to the current work week only.

- **`storage.py`**: `WELLNESS_WINDOW_WEEKS` goes from `4` to `1`. Every
  window-derived helper (`wellness_window_last_date`, `wellness_window_weeks`,
  `wellness_window_dates`) was already built purely off this constant (see
  v2.95), so no other window logic needed to change. Reworded the
  beyond-window `ValueError` (was "up to N weeks ahead" — bad grammar and a
  false "next few weeks" framing at N=1) to "within the current work week."
- **`app.py` / `templates/wellness_apply.html`, `wellness_hub.html`**: copy
  that interpolated `window_weeks` ("plan up to 1 weeks ahead", "the next 1
  weeks") reworded for a single-week policy; dropped the now-dead
  `window_weeks` template context key from both pages (neither template
  reads it anymore). `wellness_hub`'s `can_request` check already scaled
  correctly (it was written generically over `wellness_window_weeks()`) — with
  the window at 1 week, exhausting the current week's entitlement now
  disables the "Request a break" link immediately, since there's no future
  week left to fall back on.
- **Test infra** (`tests/conftest.py`, new `future_weekday` fixture): the
  wellness/notifications/reminders suites each had their own copy of a
  `_future_weekday()` helper (`today + 3 days, rolled to the next weekday`).
  Under a 4-week window that was always safely in-window; under a 1-week
  window it rolls into *next* week on 5 of 7 real calendar days (Wed through
  Sun), which would make the suite flaky depending on what day it's run.
  Replaced with one shared fixture that freezes the wall clock to the
  current ISO week's Monday morning and returns that week's Wednesday —
  deterministic regardless of the real day, and immune to the separate
  minimum-lead-time rule since it's never "today." Updated every call site
  across `tests/test_wellness.py`, `tests/test_notifications.py`,
  `tests/test_send_reminders.py`, and one similarly-patterned inline date
  computation in `tests/test_team_scope.py`; removed the three now-dead
  local helper copies. Tests that freeze "today" for their own reasons
  (`on_digest_day`) use that pinned date directly instead of layering a
  second, conflicting clock freeze on top.
- **Test coverage**: `test_request_allowed_across_the_month` and
  `test_hub_link_stays_enabled_once_a_future_week_is_open` asserted the old
  "a future week is still bookable" behavior directly, so their premise is
  now false — removed / replaced with
  `test_hub_link_disables_once_the_current_week_is_fully_claimed`, which
  asserts the new behavior (link disables immediately; a next-week claim is
  rejected through the real HTTP flow).

## 2026-09-18 (v2.96 — wellness apply form: exact-time fallback next to the slot grid)

Follow-up to v2.95: the new time-slot grid only offers 30-minute-aligned
starts (07:00, 07:30, …), so a break that genuinely needs an odd minute
(14:11, 09:16) had no way to be entered — a real regression against the old
free-text `<input type="time">`, which took any minute.

- **`templates/wellness_apply.html`**: a "Need a specific minute?" control
  sits next to the slot grid — a `<input type="time">` paired with its own
  `name="start_time"` radio (same field, same radio group as the grid's
  pills, so the POST contract is untouched). Typing a value checks that
  radio with the typed value; picking a grid pill afterward clears the box
  back out (native radio-group exclusivity handles the reverse). This path
  isn't pre-validated against `wellness_day_slots` the way grid pills are —
  computing that for every possible minute isn't worth it for what's an
  escape hatch — it's checked by `create_wellness_claim` on submit, exactly
  as the old free-text field always was.
- A resubmitted `start_time` that doesn't match any rendered pill (an odd
  minute carried over from a validation error) now falls back into the
  exact-time box on page load instead of silently not being reselected.

## 2026-09-18 (v2.95 — wellness apply form: pick a date and time slot, not type them)

The apply form's date/time fields were two disconnected native `<input
type="date">`/`type="time">` widgets: no visibility into which times were
actually bookable, an unconstrained time field the server would reject after
a full round trip, and a field order (date, time, *then* break length) where
length — which determines how long a slot needs to be — was asked last.

- **`storage.py`**: new flexi-time policy constants `WELLNESS_DAY_START_HOUR`
  (7), `WELLNESS_DAY_END_HOUR` (19), `WELLNESS_SLOT_STEP_MINUTES` (30),
  `WELLNESS_LUNCH_START_HOUR`/`WELLNESS_LUNCH_END_HOUR` (12/14) — distinct
  from the existing `WELLNESS_SLOTS` analytics buckets, which stay untouched.
  New `wellness_day_slots(conn, user_id, d, hours)` returns every start time
  the picker can offer for that date/length, each flagged `ok`/`reason` against
  the *same* checks `create_wellness_claim` enforces (weekly cap, min lead
  time, a same-day overlap) via a shared `_wellness_overlapping_claim` helper,
  plus an advisory (non-blocking) `lunch` flag. New `wellness_window_dates()`
  lists the weekdays the date strip offers.
- **Bug fix**: `create_wellness_claim`'s double-booking check matched on an
  *exact* `start_time`, so two claims that actually overlapped (e.g. 09:00-10:00
  and 09:30-10:30) were both accepted as long as their start times differed.
  It now checks real interval overlap via `_wellness_overlapping_claim`.
- **Apply form** (`templates/wellness_apply.html`, `app.py`): the native date/time
  inputs are replaced with a date-pill strip and a start-time slot grid, in the
  existing `.acts`/`.lens` radio-pill idiom (real radio inputs, so the POST
  contract — `break_date`/`start_time` fields — is unchanged). Field order is
  now date → break length → start time, so the slot grid can depend on the
  chosen length. The server precomputes `wellness_day_slots` for every window
  date × both break lengths and ships it as a JSON data attribute (same pattern
  as the existing `week_used` map); client JS renders the relevant slot set
  into pills on date/length change, greys out and disables slots the server
  wouldn't accept (with the reason as a tooltip), and marks lunch-crossing
  slots with a 🍴 badge without disabling them. Today defaults pre-selected so
  the form opens with a usable slot grid already showing.
- Tests (`tests/test_wellness.py`): `test_overlapping_break_is_rejected_even_with_a_different_start_time`,
  `test_wellness_day_slots_agrees_with_create_wellness_claim`.

## 2026-09-18 (v2.94 — admin email control center, Phase 7: timing parameters)

`docs/ADMIN_EMAIL_FEATURES_PLAN.md` §12. The six schedule/delay values that
decide *when* a scheduled reminder fires — day-before-event lead time,
wellness decide-link expiry lead time, the digest's and the wellness-filing
nudge's weekday, the CSM results announcement delay, and the AWA filing
nudge's lead time — were plain module constants in `send_reminders.py` with
no admin UI. `send_reminders.py` adds a `PARAMS` catalog (`key -> (label,
default, lo, hi)`) and a `_param(conn, key)` reader that pulls the current
value from a new `email_param.<key>` app_setting, clamped to `[lo, hi]`,
falling back to `default` on anything missing or unparseable. Every job
function that used to close over a module constant (`remind_tomorrows_events`,
`remind_wellness_expiring`, `send_csm_results_to_rps`/
`send_csm_results_to_activity`, `_baseline_once`, `remind_wellness_to_file`,
`remind_awa_to_file`, `send_approvals_digest`) now calls `_param()` instead.

`/admin/email` gains a "Timing" card — one field per `PARAMS` key (a weekday
dropdown for the two weekday knobs, a clamped number input for the rest)
plus the previously admin-invisible `email_log_retention_days`, posting to a
new `POST /admin/email/params` that follows `/admin/ai/settings`'s
clamped-int pattern and audits the change as `email_params_changed`.

`tests/test_send_reminders.py`'s digest-day fixtures read the new default
off `send_reminders.PARAMS["digest_weekday"]` instead of the removed
`_DIGEST_WEEKDAY` constant. `tests/test_email_admin.py` and
`tests/test_send_reminders.py` (73 tests) pass unchanged.

---

## 2026-09-18 (v2.93 — admin email control center, Phase 6: the send log)

Sixth and final phase (docs/ADMIN_EMAIL_FEATURES_PLAN.md). `storage.py` adds
`email_log` (following the `ai_interaction` precedent: `id`, `created_at`,
`feature`, `recipient`, `subject`, `status`, `detail`, indexed on
`created_at` and `feature`) plus `log_email_send`/`recent_email_sends`/
`purge_stale_email_log`. `status` is `sent`/`failed`/`not_configured`/
`skipped_off`; `mailer.py` gains `send_status(result)` to classify a
`mailer.send()` result into the first three (never `skipped_off` — that's
decided by the caller before a send is even attempted).

Every write site now logs one row per attempt: the three Phase-2 funnels
(`_notify_account`/`_notify_email` write `skipped_off` when the feature is
off, else the real result; `_mail_after_response`'s background send logs
through a new `_send_and_log` helper that opens its own connection, since
the background task runs after the request handler's `finally:
conn.close()`), the four always-on account/recovery sends (invite, both
reset paths, registration-link resend), and a new `send_reminders._send()`
wrapper replacing all ten of that module's bare `mailer.send()` calls — a
disabled scheduled job never reaches its function at all (Phase 3's `run()`
already drops it from the job set), so there is no `skipped_off` case at
that level, only `sent`/`failed`/`not_configured`.

`retention.py` gains `purge_stale_email_log` (`--email-log` CLI flag),
90-day default via the new `email_log_retention_days` app_setting —
`recipient` is personal data, which is the whole reason this table has a
retention window. `/admin/email` renders the newest 50 rows at the bottom of
the console with a colored-dot status (`/ops`'s idiom), each labeled with
its feature's human-readable name.

New tests across `tests/test_email_admin.py` (send_status classification,
`log_email_send`/`recent_email_sends`/`purge_stale_email_log`, the console
rendering recent sends), `tests/test_notifications.py` (a real send writes
a `sent` row; a disabled feature writes `skipped_off`), and
`tests/test_send_reminders.py` (a scheduled send writes a `job_events` row).
Also a `docs/QA_PLAYBOOK.md` pass: turn a feature off, trigger it, confirm
no mail + a `skipped_off` row, turn it back on.

## 2026-09-18 (v2.92 — admin email control center, Phase 5: preview + test-send)

Fifth of six phases (docs/ADMIN_EMAIL_FEATURES_PLAN.md). `mailer.py` gains
`sample_message(key)` — `(subject, plain_text_body, html_or_None)` built by
calling the REAL composer with representative sample data, one lambda per
key in a new `_PREVIEWS` dict covering all 18 `FEATURES` keys plus the 3
`ALWAYS_ON` keys (21 total, matching the composer count exactly). `preview
(key)` wraps it down to `(subject, html)`, wrapping a plain-text-only
composer's body (`recovery_message` has no HTML variant) in a minimal HTML
shell so every key still previews as a renderable page. A preview can never
drift from what actually sends, because it calls the same composer function.

`app.py` adds `GET /admin/email/preview/{key}` (renders the sample HTML
directly, for an `<iframe>` on the console; 404s on an unknown key) and
`POST /admin/email/test` (composes the sample and sends it to the
**requesting admin's own** `username` — never an address from the posted
form, so this route can never be turned into an open relay; says so instead
of pretending when `email_configured()` is False). Both `_forbid` on
`manage_users` like every other handler in this module.

`templates/admin_email.html` gains a `row()` macro shared by all three
groups: each row now has a "Send test to me" button beside its toggle, and a
`<details>` disclosure that lazy-loads the preview iframe on open — no
JavaScript, consistent with the rest of the console.

Two new RBAC rows in `tests/test_auth_rbac.py` (`/admin/email/preview/<key>`
GET, `/admin/email/test` POST). New Phase-5 tests in
`tests/test_email_admin.py`: every `FEATURES`/`ALWAYS_ON` key has a working
sample (the one test that stops a future composer from being cataloged
without a preview), an unknown key 404s/errors cleanly, and test-send proves
it ignores any address posted alongside `key`.

## 2026-09-18 (v2.91 — admin email control center, Phase 4: the /admin/email console)

Fourth of six phases (docs/ADMIN_EMAIL_FEATURES_PLAN.md). Adds the human
interface over the toggles Phases 1-3 already wired in: `GET /admin/email`
renders a transport banner (`mailer.email_configured()`, plus which of
relay/SMTP is live) and three groups of rows — Transactional, Scheduled,
Always-on — each with its label, hint and current on/off state, read in one
`st.get_settings` call rather than 18 round trips. `POST
/admin/email/toggle` takes `key` + `on`, rejects any key not in
`mailer.FEATURES` (never lets a POST write an arbitrary `app_setting`),
calls `st.set_email_feature`, audits the change (`email_feature_toggle`),
and redirects with `?msg=Saved.`.

Both handlers `_forbid(request, "manage_users")` on every request, copying
`/admin/rules`' gating (D8) rather than `/admin/sharing`'s. New
`templates/admin_email.html` extends `dash_layout.html` and reuses
`admin_sharing.html`'s idiom verbatim: `.acard` sections, `.state.on` /
`.state.off` pills, `.flash.ok`, plain `<form>` posts with no JavaScript
dependency. Always-on rows (account invite, password reset, registration
link re-send) render with no toggle, just the "why" string from
`mailer.ALWAYS_ON`.

New nav entry under Administrator, beside Sharing. Two new RBAC rows in
`tests/test_auth_rbac.py`'s `GATED` table (`/admin/email` GET, `/admin/email
/toggle` POST — both `manage_users`), plus Phase-4 tests in
`tests/test_email_admin.py`: every row renders, a toggle flips the setting
and writes an audit row, an unknown key is rejected and changes nothing,
and a non-admin gets 403 on both routes.

## 2026-09-18 (v2.90 — admin email control center, Phase 3: gate the seven scheduled jobs)

Third of six phases (docs/ADMIN_EMAIL_FEATURES_PLAN.md). `send_reminders.py`
gains `JOB_FEATURE`, a 1:1 map from each of `_ALL_JOBS` to its
`job_*` admin toggle key, beside the existing `_ALL_JOBS` set.

`run()` filters the resolved `jobs` set against `st.email_feature_enabled`
right after the connection opens: **CLI flags/callers choose which jobs to
consider, the admin toggle can only subtract from that set.** A disabled job
is left out of the returned report entirely rather than reported as `0`, so
a report (and `app._scheduler_loop`'s log of it) can tell "didn't run
because it's off" apart from "ran and found nothing to send". `--dry-run`
additionally prints `<job>: skipped (turned off in /admin/email)` for each
one dropped, since a dry run's whole purpose is to say what would have
happened.

`app._scheduler_loop` needed no change — it already calls `send_reminders.run(DB)`
with no job list, which now means "every job the admin still wants".

Extended `tests/test_send_reminders.py`: a disabled job is absent from
`run()`'s report and sends nothing, an enabled job is unaffected by the
gate, and `--dry-run` names a disabled job instead of running it.

Still no visible behavior change: every `email_feature.*` setting defaults
to on, and nothing yet exposes a way to turn one off (Phase 4's
`/admin/email` console).

## 2026-09-18 (v2.89 — admin email control center, Phase 2: wire the gate into the three funnels)

Second of six phases (docs/ADMIN_EMAIL_FEATURES_PLAN.md). `app.py`'s three
mail funnels — `_notify_account`, `_notify_email`, `_mail_after_response` —
gain a `feature=` argument and check `st.email_feature_enabled(conn, feature)`
before sending; all 11 transactional call sites (event created, event
section-notify, registration confirmed, certificate ready, raffle winner,
wellness approval/decided, work arrangement approval/decided/reopened,
Spot Feedback update) now pass their key.

`_notify_email` and `_mail_after_response` gain `conn` as their first
argument — both are called while `conn` is open at every site (checked, not
assumed). `_mail_after_response` checks the flag at call time rather than
inside its deferred `BackgroundTask`, since that task runs after the request
handler's `finally: conn.close()` — a check deferred into the task would hit
a closed connection. One call site (`registration_confirmed`, `app.py`
`/e/{event_token}` POST) had its send moved from after `conn.close()` to
before it, since `_mail_after_response` now needs `conn` open to check the
flag.

Row #10 (filing reopened) moves off its stray direct `mailer.send()` onto
`_notify_email`, completing the invariant that every gateable email goes
through one of the three funnels — now stated as a comment above them.
Account/recovery mail (invite, password reset, registration-link re-send)
stays on direct `mailer.send()` calls, untouched and never gated (D3).

Still no visible behavior change: every `email_feature.*` setting defaults to
on, and nothing yet exposes a way to turn one off (that's Phase 4's
`/admin/email` console). Extended `tests/test_notifications.py` to assert a
send happens with a feature on and is skipped with it off, for the wellness,
registration, and feedback paths, plus one asserting the four always-on
sends ignore every feature flag. Also fixed a latent test-isolation bug in
Phase 1's `test_features_are_independent` (`tests/test_email_admin.py`),
which flipped `wellness_approval` off and never reset it — harmless while
nothing read the flag, but now leaks into any later test in the same
session.

## 2026-09-18 (v2.88 — admin email control center, Phase 1: settings + catalog)

First of six phases (docs/ADMIN_EMAIL_FEATURES_PLAN.md) building an
`/admin/email` console to turn each of the app's 18 gateable email features
on or off individually, instead of the only current option — unplugging the
mail transport entirely, which silences invites and password resets too.

No behavior change: this phase only adds the building block. `storage.py`
gains `email_feature_enabled(conn, key)` / `set_email_feature(conn, key,
on)` over a new `email_feature.<key>` app_setting row per feature, defaulting
to on so nothing sends differently until an admin actually flips something.
`mailer.py` gains the `FEATURES` catalog (label/hint/group for all 18 keys —
11 transactional, 7 one-per-scheduled-job) and `ALWAYS_ON` (invite, password
reset, registration-link re-send — permanently non-disableable, since
turning any of those off could lock someone out of their own account
recovery). `mailer.py` stays free of any DB import, per the plan's design
call — the catalog is data, not a settings read.

Nothing calls the new gate yet — Phase 2 wires it into the app's three send
helpers (`_notify_account`, `_notify_email`, `_mail_after_response`).

## 2026-09-18 (v2.87 — baseline the CSM back catalogue, don't announce it)

Caught while verifying the v2.86 deploy, not before it: the two CSM results
jobs ask "has this been emailed yet?" and have no floor on how far back they
look. On a database that predates them the honest answer for the ENTIRE back
catalogue is "no" — so the first sweep would mail every organizer, every
section chief and every speaker-with-a-login about every activity the bureau
has ever run, in one burst, against a relay capped at ~1500 recipients a day
(`docs/MAIL_RELAY_SETUP.md`). Hitting that cap doesn't just spam people; it is
also the day invites and password resets stop going out.

The v2.86 container restarted at 15:47 PH, and `_scheduler_loop`'s first
iteration runs immediately with no initial sleep, so the sweep fired on boot
(`_REMINDER_HOUR` is 7; it was 15). Whether anything actually left the building
depends on `CSS_BASE_URL` being set on the Space — `run()` skips entirely
without it — which is not observable from outside. The Friday-only jobs
(digest is Monday, wellness-file is Thursday) did not fire either way.

**`storage.baseline_csm_results_emailed()`** — stamps every activity and
Type-3 form that has ALREADY concluded as though its results email had gone
out, sending nothing. Reuses the two `list_concluded_*` queries so "what gets
baselined" is exactly "what the first sweep would have mailed"; anything still
running keeps its NULL and is picked up normally when it concludes.

**`send_reminders._baseline_once()`** — runs before any CSM job can send,
guarded by a `csm_results_baselined` app_setting rather than being done at
column-add time, so it is still correct on a database that took the columns in
the v2.86 deploy. `--dry-run` reports the counts and changes nothing.

## 2026-09-18 (v2.86 — the rest of the email automation, and a daily sweep)

User asked what else could be automated in the sending, picked seven of the
gaps off that list, and added four more: the CSM results for both the resource
person and the activity ("only for those involved"), and reminders to file
wellness and AWA. Built one by one, a commit each.

**Fired from an action (`app.py`)** — registration confirmation (with the
attendee's own recovery link, so it doubles as the way back in);
Certificate-of-Appearance delivery the moment an attendee completes an
activity's feedback; the raffle winner's notification; and, when an admin
reopens a closed AWA period, a note to the staff who still owe a filing.

**`send_reminders.py` (new)** — the scheduled half, seven jobs behind
independent flags with `--dry-run`: day-before activity reminders (registrants
+ creator + section chief), the wellness decide-link expiry nudge, a weekly
pending-approvals digest, CSM results to the RP and to the activity's
creator/chief, and the two filing nudges. Each job gates itself on the right
day, so the sweep is safe to run daily with no flags.

**Scheduling** — first cut assumed an external cron, the way `retention.py`
and `daily_backup.py` are run. That is wrong for the Space: it is a container,
not a server anyone can add a crontab to, so a cron-only script would never
have run in production. The sweep now rides the existing in-process scheduler
(`app._scheduler_loop`, which already fires backups "no external cron
needed"), once per local day from `_REMINDER_HOUR`, claiming the day in an
`app_setting` BEFORE running so a crash can't replay it a minute later. The
CLI still works unchanged for a manual or off-Space run. `send_reminders.py`
added to `deploy_hf.py`'s `RUNTIME_PY` — the deploy ships an allow-list, so a
new runtime module that is not on it simply is not there in production.

**Idempotency** — every send that could otherwise repeat carries a marker:
`attendee.certificate_emailed_at`, `form_instance.csm_results_emailed_at`,
`event.csm_results_emailed_at`, `wellness_claim.decide_reminded_at`. The
date-window jobs stay deliberately days wide so a missed run still lands; the
markers, not the window, are what keep a reminder to one.

**Pre-merge self-review turned up five fixes**, all in their own commit. The
registration confirmation was sent on EVERY submission of a public endpoint
rate-limited at 120 POSTs/min/IP — a script could have aimed ~120 messages a
minute at any address and exhausted the relay's ~1500/day quota, taking
invites and password resets down with it; it now sends only when a row is
actually created, which dedup already bounds to one per address per activity.
`staff_without_work_arrangement` was nudging people the app refuses filings
from (tagged "No AWA") and skipping people whose only filing was denied (a
denied row frees the period again) — it now follows `work_arrangement_roster`'s
own rules, archived directory people included. The wellness expiry reminder's
window is three days wide and was re-sending for each of them. The approvals
digest re-listed the same pending rows every run, so it is weekly now. And the
three participant-facing sends ran inline, charging the relay's 30 s timeout
to someone tapping Submit at a venue or to the draw screen waiting on its
JSON — they ride a `BackgroundTask` now; admin-side sends stay inline.

## 2026-09-18 (v2.84 — formal HTML emails, invite/reset then everything else)

User request, right after confirming v2.83's relay actually delivers: design
the invite/reset emails to look formal instead of plain text. Extended, still
within the same unmerged PR, to every other notification email.

**`mailer.py`** — new `_email_html()` builds a branded HTML shell: header
("Office Connect" + "Bureau of Local Health Systems Development"), greeting,
heading, intro, a bulletproof table-based CTA button (`_button_html()`),
expiry note, plain-URL fallback, and a footer. Built to email-HTML rules, not
web-HTML rules — no `<style>` block (many clients strip it), no flexbox/grid,
every rule inline, layout via `<table>` so it degrades safely in Outlook's
Word rendering engine. `invite_message()`/`reset_message()` now return
`(subject, text, html)` instead of `(subject, text)`; the three call sites in
`app.py` updated accordingly. `send()` gained an optional `html=` kwarg —
omitted, behavior is unchanged (plain-text-only, exactly as every other
composer — event/wellness/AWA/feedback notifications — still sends). SMTP
path uses `msg.add_alternative(html, subtype="html")` for a proper
multipart/alternative message; the relay path adds `"html"` to the JSON
payload. `name`/`inviter` are HTML-escaped before interpolation.

**`docs/MAIL_RELAY_SETUP.md`** — Apps Script snippet updated to read
`body.html` and set `htmlBody` on `MailApp.sendEmail` when present (falls
back to plain-text-only when absent, matching the JS `if (body.html)` check
already documented). Added a callout for anyone who already deployed the
v2.83 script: paste the updated code, then **Deploy → Manage deployments →
New version → Deploy** — editing alone doesn't reach the live URL.

Branding correction mid-build: initial draft led the header with the old
"CSS·IS" mark (matching `forgot.html`/`set_password.html`); the user
clarified the product is Office Connect now, not CSS-IS. Header now leads
with "Office Connect" only.

**Extended to the other six composers** (`event_created_message`,
`event_section_notify_message`, `wellness_pending_message`,
`wellness_decided_message`, `awa_pending_message`, `awa_decided_message`,
`feedback_update_message`) — all route through two shared helpers,
`app._notify_account`/`app._notify_email`, which gained an `html=` kwarg
passed straight through to `mailer.send()`; every one of the 8 call sites
(`awa_pending_message` is called from two routes) updated to unpack the new
3-tuple. `_email_html()` gained `extra_html` (a shaded callout box, new
`_note_box_html()`) for the optional admin note on a decided wellness/AWA
request or the reply on a Spot Feedback update — rendered only when present,
matching the plain-text version's existing `if note` / `if reply` behavior.
A generic `_e()` escapes the many dynamic fields (titles, names, dates,
remarks) these composers interpolate into `intro`.

**Caught by the test suite, not by inspection:** `tests/test_notifications.py`'s
`sent` fixture's fake `mailer.send` didn't accept the new `html=` kwarg —
every real call now raised `TypeError` inside `_notify_account`/`_notify_email`'s
blanket `except Exception: pass`, silently dropping the notification with no
visible error. All 7 notification tests failed with "0 emails sent" until the
fixture signature was fixed to match. Worth flagging: that same swallow-all
exception handling means a bug in production here would have failed exactly
as silently — the test failure is the only thing that caught it.

**Verified:** 26 tests in `tests/test_mailer.py` total (dynamic-field escaping
across the new composers; note/reply box appears only when given); all 8
`tests/test_notifications.py` tests green after the fixture fix. Rendered and
headless-Chromium-screenshotted all 8 templates (both account emails plus
all 6 notification types, including a no-note and a with-note variant) to
check the actual visual result rather than trust the markup — this caught
the CSS·IS→Office Connect branding mistake earlier in this same PR, so kept
doing it for every subsequent template rather than assuming success. Full
affected-test run green. Version bumped to **2.84**.

## 2026-09-17 (v2.83 — mail leaves over HTTPS; the Space blocks SMTP outright)

**Root cause, finally established.** Port 465 timed out exactly like 587 did.
Two different ports, both *timing out* rather than being refused, while
outbound HTTPS works fine (`ai_core.py` reaches Gemini from the same
container) — that is a firewall silently dropping outbound SMTP, not anything
provider- or code-specific. **No SMTP provider can ever work on this Space**,
which retroactively explains the original Brevo failure too: that was
configured as Brevo *SMTP* on port 587, the same blocked port. The
DKIM/DNS-authentication theory chased at the time was a misdiagnosis, and the
v2.80–v2.82 SMTP fixes (IPv4-only resolution, the recursion repair, port 465)
were all treating a symptom that could never resolve.

**`mailer.py` — new preferred transport, HTTPS relay.** `send()` now picks a
transport: `CSS_MAIL_RELAY_URL` + `CSS_MAIL_RELAY_SECRET` set → POST the
message to a Google Apps Script web app bound to the sending mailbox, which
sends it through Gmail; otherwise fall through to the existing SMTP path,
retained unchanged for networks that permit it (the LAN pilot). Uses `httpx`,
already a runtime dependency. `email_configured()` now means "any transport
can send" and splits into `relay_configured()` / `smtp_configured()`, so every
existing caller and all the "share this link instead" fallback copy keeps
working untouched. Because the mail genuinely originates from the
`doh.gov.ph` Workspace mailbox, Google signs it — so the third-party-sender
DNS authentication that blocked us earlier is moot.

`follow_redirects=True` is load-bearing: an Apps Script `/exec` URL answers
302 across to `script.googleusercontent.com`, and only that second response
carries the JSON. `httpx` does not follow redirects by default, so omitting it
would make every send read as a failure. Failure replies are translated for
the admin rather than dumped raw — a non-JSON 200 (Google's sign-in page) is
reported as the web app's access level not being set to "Anyone", which is the
setup slip that actually causes it.

**`docs/MAIL_RELAY_SETUP.md`** — NEW: why SMTP can't work here, the ~20-line
Apps Script to paste, deployment settings, the three Space secrets, and a
symptom→cause table. ~5 minutes, no DNS records, no Google Cloud project.
**`HARDENING.md`** item 3 rewritten to point at it and to warn off `CSS_SMTP_*`
on this Space.

**Verified:** 14 tests in `tests/test_mailer.py` (relay preferred over SMTP
when both are set; `follow_redirects` asserted explicitly; payload shape;
unauthorized / non-JSON / transport-failure reporting; `relay_configured()`
needing both vars). Plus — because mocked tests gave false confidence twice
this week — an **end-to-end run against a real local HTTP server** that
reproduces Apps Script's 302-then-JSON behaviour, confirming `mailer.send()`
completes the real round trip and the relay receives the exact payload. Still
unverified: delivery from the Space itself, which needs the relay deployed.
Version bumped to **2.83**.

## 2026-09-17 (v2.82 — support Gmail's port 465 as an alternate)

After v2.81's fix, the reset email now times out on port 587 (`Email send
failed: timed out`) instead of erroring instantly — the connection is being
established (IPv4 resolves fine per v2.80/v2.81) but no response ever comes
back within the 15s timeout, the classic signature of a firewall silently
dropping outbound traffic on that port, likely a spam-prevention policy on
the Hugging Face Space's network. Port 465 (Gmail's other SMTP port) is
worth trying as an alternate path.

**`mailer.py`** — `send()` now auto-detects the connection method by port:
465 uses `smtplib.SMTP_SSL` (implicit TLS from connect, no `starttls()`
call — calling `starttls()` on an already-encrypted connection talks the
wrong protocol to the server), any other port keeps the existing
`smtplib.SMTP` + `starttls()` (gated by `CSS_SMTP_TLS`) path unchanged. No
new env var — just set `CSS_SMTP_PORT=465` to switch.

**Verified:** new `tests/test_mailer.py` cases confirm port 465 always uses
`SMTP_SSL` and never calls `starttls()`, and port 587 keeps using plain
`SMTP` + `starttls()` and never touches `SMTP_SSL`; full affected-test run
green. **Not independently verified live** — this session's own sandbox
also can't reach `smtp.gmail.com` on either 587 or 465 (agent sandboxes
commonly restrict raw outbound TCP to an HTTPS proxy), so whether 465
actually gets through on the Space's network is still an open question for
the next live retest. Version bumped to **2.82**.

## 2026-09-17 (v2.81 — the v2.80 IPv4 fix recursed into itself)

Reported immediately after v2.80 deployed: reset email now failed with
`Email send failed: maximum recursion depth exceeded`. Self-inflicted bug in
the v2.80 patch itself: `_ipv4_only_getaddrinfo` resolved the real resolver
by looking up `socket.getaddrinfo` **by name** at call time — but `send()`
had already reassigned `socket.getaddrinfo` to `_ipv4_only_getaddrinfo`
itself before the SMTP connection runs, so the function called itself
forever the moment anything (smtplib, internally) actually invoked address
resolution.

**`mailer.py`** — added a module-level `_real_getaddrinfo = socket.getaddrinfo`
captured once at import time, before `send()` can ever patch the module
attribute. `_ipv4_only_getaddrinfo` now calls `_real_getaddrinfo` directly
instead of the (patchable) `socket.getaddrinfo` name; `send()`'s `finally`
restores via the same captured reference.

**`tests/test_mailer.py`** — the previous test suite passed despite this bug:
it asserted `socket.getaddrinfo is mailer._ipv4_only_getaddrinfo` (an
identity check) but never actually *called* it during the fake SMTP
connection, so the infinite recursion was never exercised. Rewritten:
`test_ipv4_only_getaddrinfo_does_not_recurse_once_patched_onto_socket`
reproduces the exact failure shape (patches `socket.getaddrinfo` onto the
helper, then calls it) — confirmed this fails with `RecursionError` against
the old code and passes against the fix. The two `send()`-level tests now
actually invoke `socket.getaddrinfo(...)` inside the fake SMTP connection
(resolving `127.0.0.1`, no real network needed) instead of only checking
identity.

**Verified:** `pytest tests/test_mailer.py tests/test_auth_rbac.py
tests/test_notifications.py tests/test_account_email_sync.py
tests/test_ops_usage.py` green; manually confirmed the old buggy pattern
reproduces `RecursionError` and the fixed one resolves `smtp.gmail.com` to
IPv4-only addresses live, with no recursion. Version bumped to **2.81**.

## 2026-09-17 (v2.80 — SMTP over IPv6 was unreachable on the Space)

Found via the v2.79 error surfacing: the live Space's Gmail SMTP attempt was
failing with `[Errno 101] Network is unreachable`. `smtp.gmail.com` resolves
to both IPv4 and IPv6 addresses; Hugging Face's container gets assigned an
IPv6 address with no actual IPv6 route out, so `smtplib.SMTP()` picked the
IPv6 address first and failed instantly, never falling back to the IPv4
address that works.

**`mailer.py`** — new `_ipv4_only_getaddrinfo()` wraps `socket.getaddrinfo`
to request `AF_INET` only. `send()` swaps it in (via `try`/`finally`, so it's
always restored even on failure) for just the duration of the SMTP
connection attempt. The hostname passed to `smtplib.SMTP()` is unchanged, so
TLS certificate validation still checks the real domain — only address
resolution is filtered.

**Verified:** new `tests/test_mailer.py` (the filter keeps only `AF_INET`
results against a fake mixed-family resolver; `socket.getaddrinfo` is
confirmed restored to the original after both a successful and a failed
`send()`, with `smtplib.SMTP` faked out so no real network call happens);
full affected-test run (`test_mailer.py`, `test_auth_rbac.py`,
`test_notifications.py`, `test_account_email_sync.py`) green. Version
bumped to **2.80**.

## 2026-09-17 (v2.79 — a failed send no longer looks like "not configured")

Found while live-debugging the v2.78 SMTP rollout: `mailer.send()` returns
`sent: False` both when SMTP genuinely isn't configured (`CSS_SMTP_HOST`
unset) and when it IS configured but the actual send throws (bad
credentials, connection refused, etc.) — but the two `app.py` call sites
(`admin_users_invite`, `admin_users_reset_default`) showed the identical
"Email isn't configured" message either way, hiding the real error and
sending the admin chasing the wrong fix (re-checking env vars that were
already correct).

**`app.py`** — `_provision_account` now also returns `mailer.send()`'s
`detail` string. Both call sites check `mailer.email_configured()` to tell
the two cases apart: truly unconfigured keeps the existing "share this
link" message, but a configured-and-failed send now shows the real
exception text (e.g. an SMTP auth error) alongside the fallback link.

**Verified:** new `tests/test_auth_rbac.py::test_admin_reset_surfaces_send_failure_detail_not_unconfigured`
(monkeypatches `mailer.email_configured`→True and `mailer.send` to fail
with a detail, asserts the redirect carries the real error text and not
the generic "isn't configured" copy); full affected-test run clean. Version
bumped to **2.79**.

## 2026-09-16 (v2.78 — account creation/reset moves to emailed invite links)

`HARDENING.md` item 3 ("Revert pilot auth → emailed invite links + SMTP") —
the code half of it. `mailer.py`/`_invite_link`/`_reset_link` already existed
but weren't wired up; new accounts were still handed the shared
`auth.DEFAULT_PASSWORD` ("12345678") and `/forgot` just told users to ask an
admin.

**`app.py`** — `_provision_account` now creates the account pending
(`active=False`, no password) and emails an invite link via
`mailer.invite_message`/`mailer.send`, instead of hashing in the default
password. `admin_users_reset_default` now emails a `_reset_link`
(`mailer.reset_message`) rather than resetting the account back onto the
default password — the existing password keeps working until the link is
used, same as self-service `/forgot`. `_account_redirect` now also forwards
`link` on the redirect so the Users page can show the raw link when
`mailer.email_configured()` is false (SMTP not set up yet — nothing is lost,
it just isn't emailed).

**Templates** — `forgot.html` gets a real email-entry form (previously just
static "ask your admin" text with no way to actually request a reset) that
branches on whether SMTP is configured. `users.html`: added a `pending`
("Invited · link not used yet") status pill + "Resend invite" action,
relabeled "Reset password" to "Send reset link" with updated confirm copy,
dropped the now-inaccurate temp-password lede text.

**`auth.py`** — `DEFAULT_PASSWORD` kept only for accounts that still carry it
(so the existing forced-reset-on-login path keeps working); comment updated
to say it's legacy, not the provisioning path anymore.

**Verified:** `tests/test_auth_rbac.py::test_admin_reset_sends_a_reset_link_and_keeps_old_password_until_used`
replaces the old default-password-reset assertion (old password stays valid
until the emailed link is followed); full `pytest tests/` run clean aside
from pre-existing failures that need the real production `css_is.db` (not
present in this checkout) — none touch auth/mailer/users. Version bumped to
**2.78**.

Still open (can't be done from here — needs the Space owner): add
`CSS_SMTP_HOST`/`CSS_SMTP_PORT`/`CSS_SMTP_USER`/`CSS_SMTP_PASS`/`CSS_SMTP_FROM`/`CSS_SMTP_TLS`
secrets to the Hugging Face Space. `mailer.py` is provider-agnostic — Brevo's
SMTP relay (`smtp-relay.brevo.com:587`) or any other SMTP provider works with
no further code change.

## 2026-09-16 (v2.77 — the profile-photo picker never opened on some devices)

Reported by the user: mobile users couldn't choose their own photo. The
self-service photo picker on `/me` and `/welcome` wrapped its hidden
`<input type="file">` in `<span class="lbl">` instead of `<label class="lbl">`
— a plain `<span>` has no native click-proxy behavior for a nested input, so
tapping the "Choose photo" text never opened the picker. There was no
mobile-specific CSS (media query, `pointer-events`, `touch-action`) at fault;
it was plain markup. The admin-facing pickers (`staff_form.html`,
`directory.html`) already used the correct `<label>` pattern, which is why
only the employee self-service pages — the ones people actually use from a
phone — looked broken.

**`templates/me.html`** / **`templates/welcome.html`** — `<span class="lbl">`
→ `<label class="lbl">` around each photo-picker's hidden file input.

## 2026-09-16 (v2.76 — the reopened period was missing from the filing form)

Reported by the author against the live site right after v2.75 shipped: an
admin reopened a closed period from `/admin/work-arrangement`, the hub
correctly showed it as "Reopened by an admin," but clicking through to
`/work-arrangement/file` — the actual filing form — didn't offer it as a
"Which period" choice at all. v2.75 only folded the reopened period into
`work_arrangement_hub`'s `periods` list; `_wa_file_page` (`app.py`), which
builds the form independently, still called only
`st.work_arrangement_open_periods()` and had never heard of the override.

**`app.py`** — `_wa_file_page` now also calls
`st.list_work_arrangement_reopens(conn)` and unions those period keys into
`open_ps` before building `open_periods` (and before the coverage loop, so a
reopened period gets its own coverage warnings too, same as a normally-open
one). Each period dict carries a `reopened` flag.

**`work_arrangement_file.html`** — a reopened choice's subtext reads
"reopened by an admin" instead of "file by \<date long past\>", which would
otherwise print a deadline that already came and went.

Test: `test_reopening_over_http_lets_the_employee_file_it_themselves` (added
in v2.75) exercised the POST directly and would never have caught this — it
now also GETs `/work-arrangement/file` first and asserts the period actually
renders as a selectable radio choice, which is what the hub's "File it now"
link actually depends on.

## 2026-09-16 (v2.75 — an admin can temporarily reopen a closed AWA period)

Requested by the author: filing for a work-arrangement (AWA/ANNEX C) period
closes on the Friday before it begins (`_wa_check_period_open`), by design —
"once a period has BEGUN it is closed" (`work_arrangement_open_periods`). That
left no path back in once the deadline passed, not even for an admin, so a
late or missed filing had nowhere to go.

**`storage.py`** — a new table, `work_arrangement_reopen`, holds at most one
row per period: who reopened it, when, and an optional note.
`get_work_arrangement_reopen` / `set_work_arrangement_reopen` /
`clear_work_arrangement_reopen` / `list_work_arrangement_reopens` are its
accessors. `_wa_check_period_open` now takes `conn` (both call sites —
`create_work_arrangement`, `request_work_arrangement_change` — updated to pass
it) and treats a period with an active override as open, alongside the normal
deadline check.

**`app.py`** — a new admin console, `/admin/work-arrangement` (GET) and
`/admin/work-arrangement/reopen` (POST), gated on `manage_users` like every
other `/admin/*` page, listing the current period plus the few before it and
letting an admin reopen or close each one, with an audit-logged summary either
way. The employee's own `/work-arrangement` hub folds any reopened period into
its normal `periods` list (deduped against `work_arrangement_open_periods`) so
it shows up as an ordinary fileable card — labeled "Reopened by an admin" in
`work_arrangement_hub.html` — rather than something an admin files on their
behalf.

Tests: `test_an_admin_reopen_lets_filing_past_the_deadline` (storage-level),
`test_only_an_admin_reaches_the_reopen_console` and
`test_reopening_over_http_lets_the_employee_file_it_themselves` (HTTP-level).
The `wa_org` fixture now also wipes `work_arrangement_reopen` between tests —
without it, a period left reopened by one test (all tests share the same
real-world "current" period start) silently let a later test's deadline
check pass.

## 2026-09-02 (v2.74 — one alternative work arrangement per calendar week)

Reported by the author against the September calendar: filing is one row per
person per half-month period, and `ux_work_arrangement_approved` /
`ux_work_arrangement_pending` enforce that — but a period boundary falls in the
MIDDLE of a working week. September 1-15 and September 16-30 both own part of
the week of the 14th, so "Monday WFH" for the first half and "Wednesday WFH"
for the second half are two separate, individually legal filings that together
put two alternative work arrangement days into one week. Nothing in the module
looked across the boundary, because nothing in the module was framed in weeks.

**`storage.py`** — `_wa_install_week_guard()` adds two GENERATED (VIRTUAL)
columns to `work_arrangement`, `week_head` and `week_tail`: the Mondays of the
first and last calendar weeks the nominated weekday actually falls in inside its
period. Derived in SQL from `period_start` and `weekday` rather than stored, so
they cannot drift out of step with the filing — the same reasoning `_wa_remarks`
gives for deriving the Remarks cell. Note they are only visible to
`PRAGMA table_xinfo`, not `table_info`.

Because periods never overlap, the later filing's first week is the only one
that can meet the earlier filing's last week, so comparing the two ends of each
range decides the question exactly — no need to enumerate the weeks between.
That is what `trg_wa_one_per_week_ins` / `_upd` do (BEFORE INSERT and BEFORE
UPDATE, guarded on `weekday IS NOT NULL AND status IN ('pending','approved')`),
and `work_arrangement_week_conflict()` reads the same two columns to find the
clashing row for a message a person can act on. `work_arrangement_weeks()` and
`work_arrangement_week_label()` are the Python twins.

Wired in at both ends the author asked for, plus the database: filing
(`create_work_arrangement`), changing (`request_work_arrangement_change`,
judged on the day it ASKS for, since a change can walk into a boundary week the
filed day stayed clear of) and approval (`decide_work_arrangement`) all call
`_wa_check_week_free()` first; the trigger is the backstop for any path that
does not.

Deliberate calls:
- **A pending filing holds its week** (`_WA_LIVE`, as the per-period rule
  already does). Letting a second through would only queue a clash for the
  chief. Denied, withdrawn and superseded rows release it again.
- **REG is exempt at both ends** — it nominates no day, so it neither takes a
  week nor is refused one.
- **Rows filed before this rule are left alone.** The triggers judge writes, not
  what is already on the books; an approval that would newly double up a week is
  refused, which is how such a pair gets cleared rather than compounded.
- **A change request is not its own clash** — the row it supersedes sits in the
  same period, and same-period rows are excluded (the per-period indexes own
  that case), otherwise nothing could ever be changed.

**`templates/work_arrangement_file.html`** — the weekday picker's help line now
states the rule before someone hits the refusal.

**`tests/test_work_arrangement.py`** — a new section covering the September
example end to end, the weekday that stops short of the boundary week (Wednesday
in September 1-15 ends on the 9th and legitimately leaves the week of the 14th
free), CWW-vs-WFH, per-person scope, pending/withdrawn/denied, the change and
approval gates, both triggers, the refusal's wording, the HTTP path, and the
generated columns held to the Python arithmetic across year ends and a leap
February. 154 pass in that file; the 6 failures in the wider suite
(`test_ai_report_draft`, `test_home_feeds`, `test_integrity`, `test_search`)
predate this branch and are the demo `setup_db.py` seed standing in for the
delivered database.

## 2026-08-26 (v2.73 — approvals visibility on the home page and nav bell)

Reported directly by a chief who approves both wellness breaks and Alternative
Work Arrangement (AWA) requests: finding out whether anything needed a
decision meant opening `/wellness/approvals` or `/work-arrangement/approvals`
blind, since neither the home page nor the nav bell hinted at it either way.
Two PRs (#115, #116) closed that gap; this entry — and the version bump —
covers both, since #115 shipped without one.

**#115 — home page banner + door badges (`office_connect.py`,
`templates/office_connect.html`):** `team_view_data()` gained
`_approvals_waiting()`, which counts pending items in both queues for an
approving chief and (when non-zero) adds an amber `notes` panel at the top of
`/` plus a matching badge on the Wellness/AWA door cards, each linking
straight into the relevant queue. Empty queues render nothing extra — no
permanent fixture.

**#116 — the nav bell (`storage.py`, `app.py`, `templates/_components.html`,
`templates/dash_layout.html`, `templates/public_layout.html`,
`static/css/app.css`):** the bell used to be a single link to `/my/feedback`
with an unread-feedback badge only. `storage.pending_approval_counts()` is now
the shared source both the home-page banner and the bell read from a chief's
"waiting on me" totals. Two new `admin_user` columns
(`wellness_seen_at`, `wa_seen_at` — the requester-side twin of
`spot_feedback.submitter_seen_at`) drive `unseen_wellness_decisions()` /
`unseen_work_arrangement_decisions()`, so a requester also hears "your break
was approved/denied" in the bell until they reopen `/wellness` or
`/work-arrangement` (which marks it seen, mirroring `/my/feedback`). The bell
itself became a small `details`/`summary` popover (`notif_bell()` macro,
reusing the existing settings/help-menu dropdown mechanics) listing every
active item, each linking straight to its page.

**Verified:** `pytest tests/test_office_connect.py tests/test_landing_fork.py
tests/test_wellness.py tests/test_wellness_escalation.py
tests/test_work_arrangement.py tests/test_notifications.py` green on both;
manual `TestClient` runs seeding a chief with one pending item in each queue
and a requester with one decided-but-unseen item in each, confirming the
banner/badges/bell text, links, and clearing-on-visit all behave.

## 2026-08-24 (v2.72 — the lone card spans the row)

Follow-up to v2.71. `.oc-panels` (`templates/office_connect.html`) always
renders exactly three `.oc-card` children — Wellness, Alternative Work
Arrangement, then CSS/Activities — in a `repeat(auto-fit, minmax(320px,1fr))`
grid. The container's own cap (`.wrap`, 980px) means that grid can never fit
a third 320px+ column (3×320 + 2×16 gap = 992 > 980), so on any laptop/desktop
width the layout is always exactly 2 columns, and the 3rd card always lands
alone in column 1 of row 2 — at half the row's width, with the other half of
the row sitting empty beside it. Reported directly off a screenshot showing
the "Activities" card boxed in at half width next to open space.

**Fix:** `.oc-panels > .oc-card:last-child { grid-column:1 / -1; }` — spans
the last card from the first grid line to the last, whatever the actual
column count turns out to be. Safe at every width: on mobile (1 column) it's
a no-op: `1 / -1` still just means the whole (only) row. Scoped to
`:last-child` rather than a count-based selector because the card order is
fixed by the template, not data — there are always exactly three.

**Verified:** re-ran the same seeded-data Playwright pass as v2.71 (Team and
Me view, 1440/1280/1024/900/375px) — the Activities card now spans the full
row at every desktop width, mobile is unchanged (single column already), no
horizontal overflow introduced, and `pytest tests/test_office_connect.py`
still green (36 tests).

## 2026-08-24 (v2.71 — the home cards fit a personal computer)

The `office_connect.html` landing page ("Office·Connect", the `/` route) lays
its three cards out in `.oc-panels`, a `repeat(auto-fit, minmax(320px,1fr))`
grid. On a phone the cards stack one per row, so nothing was ever visibly
wrong there. On a laptop/desktop viewport the grid renders two columns, and
the Wellness and Alternative Work Arrangement cards sit side by side in row
one — and their content heights routinely disagree: Wellness's `deck` (see
`_components.html`) and AWA's `deck` each size to their own tallest slide, and
in Team view those tallest slides differ by a coverage chart's worth of
height. `.oc-panels` had `align-items:start`, so CSS Grid left each card at
its own natural height instead of stretching it to the row's — the shorter
card just stopped, and the *row track* (sized to the taller card regardless)
left a blank stripe of plain page background before the next row of cards
began. Checked both Team and Me view at 1440/1280/1024/900px: Team view shows
it clearly (richer decks, more mismatch); Me view is milder but the same
mechanism applies whenever a scope's AWA/CSS content outgrows Wellness's.

**Fix, `templates/office_connect.html`:** drop `align-items:start` (default
`stretch` applies), and make `.oc-card` a column flexbox so the leftover
height has somewhere sane to go — `.oc-card > .foot` (the card's own trailing
"Open X →" link, a **direct** child) gets `margin-top:auto` and is pushed to
the bottom, absorbing the gap instead of leaving it as dead air in the middle
of the card or as a stripe of bare page beneath it. Deliberately scoped to the
direct child: the several other `.foot` footnotes tucked inside individual
`deck-slide`s (e.g. the "Not in: …" / "Attendance isn't recorded here" lines)
are not flex items of `.oc-card` and keep their normal `.75rem` top margin
unchanged — a descendant selector there would have collapsed that spacing to
0 for no visual benefit.

**Verified:** ran the app locally (seeded via `seed_dashboard_demo.py`, an
admin account linked to a directory person with speaking history) and
screenshotted `/` and `/?view=me` with Playwright at 1440/1280/1024/900/375px.
Before the fix, the Team view's Wellness/AWA row left a ~190px blank gap above
the "Activities…" card at 1440px; after, both cards' bottoms align and the
next card starts right after the row, at every desktop width tested, with no
horizontal overflow (`scrollWidth == clientWidth` throughout) and no change at
375px (single column, nothing to stretch against). `pytest tests/
test_office_connect.py` still green (36 tests) — the change is presentational
only, no template logic moved.

## 2026-08-16 (v2.70 — a drawn signature, stamped on the day it approves)

Two gaps, one change. The monthly wellness register signed **per week**: a
left-hand "Approved By" band held the approver's name and the italic stand-in
"Digitally approved and signed", so a week with two breaks decided by two chiefs
collapsed both into one line and a reader could not tell which approval covered
which day. And a signature could only enter the system as an **image file an
administrator uploaded** onto a directory record (`templates/staff_form.html`) —
a chief could not produce one from their own phone.

### Capture: a signing box on `/me`

`templates/me.html` gains a **My signature** panel inside the existing profile
form, so it saves with everything else and needs no new write endpoint. A
`<canvas>` with `touch-action:none` (without it the first finger stroke scrolls
the page instead of drawing), Pointer Events + `setPointerCapture` — the idiom
already used by the photo crop editor and `static/js/avatars.js` — Undo and
Clear, a high-DPI backing store, and midpoint-quadratic smoothing so a finger
stroke is not a polygon.

Strokes are kept as point arrays, not baked into the canvas. That buys Undo
(`strokes.pop()`), survival across resize/orientation, and an exact **geometric**
trim: the export's bounding box comes from the points, not from a pixel scan. On
submit the ink is redrawn at up to 600px wide on a **transparent** background and
written to a hidden `signature_data` field as a PNG data URI — the same
mechanism `photo_data` has always used, so no multipart dependency appears.

**An untouched pad writes nothing.** Saving the profile can never wipe a
signature by accident; only the explicit *Remove my signature* box clears one.

### Storage: one signature per person

- **`admin_user.signature` / `signature_mime`** (`storage._add_missing_columns`),
  beside the existing `photo` columns and for the same reason: accounts with no
  directory row need somewhere to keep one. `_ADMIN_COLS` gains a cheap
  `(signature IS NOT NULL)` boolean **appended** — `_admin_row` is positional.
- **`set_user_signature` / `clear_user_signature` / `get_user_signature`**, and
  **`user_signature(conn, user_id)`** which resolves *what this account signs
  with*: the directory row's signature when linked, the account's otherwise —
  the precedence `get_user_profile` already uses for the photo.
- Linked accounts therefore write to `resource_person.signature`, **the field
  certificates already sign with**. That is deliberate: one signature per person,
  not two that can disagree. Consequence: a chief who draws one will see it on
  Certificates of Appearance they sign, replacing any scan uploaded for them.
- **`GET /me/signature.png`** serves it back to its owner only — no id in the
  URL to enumerate, `Cache-Control: no-store`, matching the deliberately stricter
  treatment of `/directory/person/{id}/signature.png` ("forgery risk").
- **`_decode_signature`** (`app.py`) tightens `_decode_photo` for this one blob:
  PNG by **magic bytes**, not by the mime the browser declares, capped at 800 KB.

### The register signs the day, not the week

- `storage.wellness_person_month` selects `c.decided_by` and resolves each
  **distinct** approver's signature once into the entries as
  `approver_signature` / `approver_signature_mime`. One blob per approver per
  month, not one per break.
- `wellness_register.build_day_cell(entries, max_w, max_h)` returns a flowable
  list per weekday: the break line, the approver's signature image, then their
  name over "Digitally approved and signed". `_signature_image` sizes it from
  `ImageReader.getSize()` to the ~85pt column (78×20pt), passes a **fresh
  `BytesIO` per `Image`** (platypus reads the stream eagerly, so a shared one
  comes up empty on the second cell) with `mask="auto"` so the transparent
  background stays transparent, and returns `None` on any failure — a corrupt
  blob degrades to the text stamp rather than 500-ing the download.
- `_approver_html` shrinks to the paper form's `"Approved By:"` caption. The
  two-row week block and its SPANs are unchanged, so the form's shape survives.
- **No approver with a signature = no change.** Name over the italic stamp, as
  before, which is what every already-approved break in the database renders as.

### Note for the bureau

`/wellness/register.pdf` is self-service by design — no chief gate. It now hands
each employee a print-resolution image of their approving chief's signature. That
is inherent to signing the register; `/me/signature.png` and the directory
preview both stay authenticated.

### Tests

`tests/test_wellness.py` — the signature reaches the entries and is read once per
approver; the account-row fallback for an unlinked approver; `build_day_cell`
puts an `Image` in the day's cell and keeps the stamp without one; the PDF
carries `/Subtype /Image` only when signed; a corrupt blob still renders.
`tests/test_profile_edit.py` — the pad renders (including `touch-action:none`, a
silent phone-breaker otherwise); an unlinked viewer can draw and fetch their own;
a blank submit does not wipe; a non-PNG is rejected; a linked account's drawing
lands on the directory row and the remove box clears it.

## 2026-08-16 (v2.69 — the activities deck reads the window its header claims)

v2.67 gave the Activities card an insights deck and set it to a 365-day window,
on the reasoning that three bars is not a trend. The card's header — `Last 90
days · <scope>` — sits **above** the deck, not inside a slide, so it stays on
screen while the reader swipes. Four slides out of five were therefore labelled
with a window they did not use. The longer window may have been the better
chart; it was not the window the card promised, and the promise is what a reader
acts on.

`INSIGHT_DAYS` is now **bound to** `WINDOW_DAYS` rather than restated, so the
two cannot drift apart again:

```python
INSIGHT_DAYS = WINDOW_DAYS
```

### The month chart, at 90 days

`INSIGHT_MONTHS = 12` is gone. `_month_span(cut, today)` returns the calendar
months the window actually touches — three or four, depending on where in the
month today falls — each flagged `whole` when the window covers it end to end.

That flag exists because of a claim the chart cannot support on its own. A
90-day window starts and ends mid-month, so its first and last buckets count
part of a month against months counted in full. Drawing them is fine — each bar
is a true count of what happened *inside the window*. Ranking them is not:
today's month could "win" on sixteen days against last month's thirty-one. So
the "busiest" sentence now requires the leading month to be **whole**, on top of
the existing single-holder rule from v2.67:

```python
peaks = [b for b in volume["bars"] if b["n"] and b["n"] == volume["ymax"]]
busiest = (peaks[0] if len(peaks) == 1
           and keys[volume["bars"].index(peaks[0])] in whole else None)
```

`since` is now the cut date itself (`"May 18"`) rather than the first bucket's
month, so the sentence under the chart states the window's real start instead of
implying it: *"2 activities since May 18."*

### Smaller things in the same area

* The two "Nothing in the last 90 days" empty states hardcoded the number while
  everything around them read `window_days`. They now read the constant too.
* `tests/test_office_connect.py::_payload` takes an optional `today`. Anything
  asserting on the window passes it: left to the real clock, a test with fixed
  event dates passes today and silently stops exercising anything the day those
  dates age out of the 90-day cut.

## 2026-08-15 (v2.67 — the organising section decides which activities you see)

### Creating an activity is not taking part in it

The landing page's activities card qualified a row three ways: you SPOKE at it
(`form_instance.rp_id`), you CREATED it (`form_instance.created_by`), or your
section ORGANISED it (`form_instance.lead_org_id`). Personal was `spoke OR
created`; team added the organising unit.

`created_by` records who filled in the form. That is a fact about the app, not
about whose work the activity was — and an administrator sets activities up for
sections all over the bureau. Every one of those landed on that administrator's
own card, and on their section's team card, for an activity their section had
nothing to do with. The page has no chief-only route guard by design, so there
was nothing behind which that could hide.

The predicate is now one function, `office_connect._css_roles`, shared by the
list and the deck so the two can never disagree about which activities count:

* **Me** is speaker-only. It is the one view whose claim is about YOU, so it is
  the narrowest of the three. The heading says so now: *"Activities you spoke
  at"*.
* **Team** is the organising unit's subtree, plus anything one of the team
  actually spoke at — a teammate speaking at another section's event is real
  work done by a real teammate, and a section head wants it.
* **Creating never qualifies a row.** "Organised" survives as a chip on a row
  that already qualified: worth saying out loud, never a reason to be in the
  list.

One deliberate consequence: an activity with no `lead_org_id` whose only link
was a teammate's `created_by` now drops out of the team view. Anything a
teammate actually spoke at still shows.

### The same rule on the management feeds

`/monitor` and `/activities/outside` short-circuited on `role == "admin"` for
the whole bureau and fell back to `created_by` for everyone else. Both halves
were wrong at once: a section head who also administers the app monitored every
section instead of their own, and an administrator filing an activity FOR
another section carried it on their list for good while the section actually
running it never saw it.

`app._event_feed_scope` now resolves `st.team_scope_for_user` and hands
`st.list_events` a `team_scope`, filtered by `st.event_in_team_scope` —
the organising unit, or one of the team spoke at it. Applied before the
per-event registration rollups, so the expensive work stays proportional to
what is shown.

The speaker half is not a nicety here, it is the only thing that can answer for
an INVITED activity: `create_survey`'s outside branch passes no `lead_org_id`
at all — not on the `event` row and not on its Form 3s, because the organiser is
an external body. The section whose person was invited is the section that owns
the engagement, which is also the right answer. `list_events` grows
`lead_path` and `rp_paths` (the internal speakers' home units) to answer both.

Two deliberate exits from the rule:

* An account the DIRECTORY does not place falls back to `created_by` — exactly
  what it saw before. `_path_in_scope(path, None)` is True for everything, so
  scoping an unplaced account would hand it the bureau; and blanking a
  management page is a lockout, not a safety measure.
* A seat that genuinely needs every section reaches it through the
  `bureau_access` grant from v2.63 — named, audited, revocable — rather than by
  holding a role. Same principle v2.61 established for the directory.

`_can_manage_event` (creator-or-admin) is untouched, so a direct link to
`/monitor/{token}` or `/activities/{token}/manage` still works for whoever set
an activity up. It is the LIST that is now scoped, not the handle.

`/activities/archived` and the `/css` "Your recent activities" strip stay
creator-scoped: those are about picking your own work back up, not about
surveying a team's.

### The card everyone else already had

Activities was the one panel with nothing to read past the list. It is now a
deck like wellness and AWA, over a **365-day** window — the list stays at 90
days, because three bars is not a trend and the deck is answering a different
question.

* **Month by month** — activities per calendar month (`di.count_bars_geom`).
  "Busiest" is claimed only when ONE month holds the top; on a tie the
  superlative is false, and picking whichever month sorted first is how a chart
  ends up disagreeing with the sentence printed under it.
* **How they were rated** — the band mix. An activity below `eng.N_MIN`
  responses is counted in its own row rather than quietly graded, so the mix
  stays a statement about ratings that hold up. On the personal card the band is
  YOUR speaker rating, read from the new per-event `speakers_by_rp` map: the
  event review rates the event, and handing you its score because you happened
  to speak there is exactly the claim to avoid.
* **Who spoke most** — team members only. An outside resource person topping
  your section's list is true but useless; the slide is asking who among us is
  carrying the speaking.
* **Reach** — responses collected, average per activity, the biggest one.

No new query and no new geometry helper: everything comes off the memoised,
scope-free `_activity_index` already in hand, the same discipline `_awa_insights`
follows. No new CSS and no new JS either — `deck`/`deck_slide`, the local
`count_bars` macro, `ul.mix` and `.stat-row` were all already on the page, and
`deck.js` self-disables on a single-slide deck, so an account with nothing to
show still degrades to the plain list.

## 2026-08-15 (v2.63 — landing-page decks, and bureau-wide sight granted per account)

### The seat that legitimately needs every section

v2.61 made the directory the basis of scope: you see the unit you are recorded
in, and no role widens that. That is right for almost everyone and wrong for one
real job — whoever consolidates the bureau's fortnightly ANNEX C has to see and
print every section's work arrangement, and the previous answer ("be an admin")
is exactly the conflation v2.61 removed.

**`admin_user.bureau_access`** is the explicit alternative. Two levels beyond the
default of nothing:

* `'awa'` — the work arrangement only: the team schedule and both ANNEX C
  downloads cover every section.
* `'all'` — every scoped view, wellness register and landing page included.

Set per account in **Admin → Users** ("Sees", beside the role), audited as
`change_bureau_access` exactly like a role change, and revocable. It is read from
the row on every request, never from the session cookie that minted the user
dict — a revoked grant must stop working on the next page load, not whenever the
cookie happens to expire.

Callers ask for what they are showing — `_org_scope_for_user(conn, user,
area="awa"|"wellness")` — so the narrow grant widens the ANNEX C and nothing
else. `team_scope_for_user` regains its "bureau" kind, reachable now by an `'all'`
grant or by a directory record at the bureau-level unit; a work-arrangement grant
deliberately does not widen the landing page, which spans all three modules.

**Sight is not authority.** `user_can_view_work_arrangement_schedule` (chiefs +
grant holders) is kept apart from `user_is_approving_chief` (chiefs only), so the
schedule, its ANNEX C download and its nav entry open for a grant holder while
the approvals queue stays shut — and the queue link is dropped from the hub and
the schedule page for them rather than left to 403. Wellness stays out of the
narrow grant entirely: those are health records, and printing a schedule is not a
reason to read them.

Granted on first start after each account exists, per username, so an
administrator who revokes a grant does not find it back after the next deploy:
`armedel@doh.gov.ph` → work arrangement bureau-wide; `ray@gmail.com` → everything
bureau-wide, with the administrator role.

### The landing page: bigger companion, named faces, swipeable insight decks

### The last thing the role still stood in for

v2.61 (#100) made the directory decide the team, arrived at independently and
from the other end: it resolves the org chart first, seats the Director as the
one directory role whose team really is the bureau, and keeps `"bureau"` for an
`admin` with no seat on the org chart. This branch reached the same conclusion by
a different route, so the merge keeps that structure — single source of truth in
`team_scope_for_user`, `_org_scope_for_user` folding "none" back onto None, the
`archived_at IS NULL` filter — and changes exactly one thing on top of it.

**That last admin fallback is gone.** An account with no seat on the org chart
now resolves to `"none"` like any other unlinked account, and reaches the bureau
only through the explicit grant above. The reach is identical for the one account
that genuinely needs it; what changes is that it is now named, audited and
revocable rather than implied by a role. `ray@gmail.com` — the system
administrator this fallback existed for — is seeded with the `'all'` grant, so
nothing is lost on deploy.

Callers pass the module they are showing (`area="awa"` / `"wellness"`), which is
what lets a work-arrangement grant widen the ANNEX C without touching the
wellness register.

### One card, one number, four unasked questions

The wellness and AWA cards each led with a count and stopped there. Everything
else the data knows — which day and hour breaks actually land on, what people do
with them, whether the reflection says it helped, which arrangement people chose,
which weekday the office empties — was either one click away or nowhere.

Both team cards are now **decks**: a native `scroll-snap` track that swipes with
no JavaScript at all, with arrows, dots and ←/→ keys added on top by
`static/js/deck.js` (nothing is rendered that would be dead without it). Five
readings each, every chart still shipping its `chart_table` screen-reader
fallback, and every slide carrying a one-sentence reading computed in Python —
"Most breaks land Wednesday, before 10", "Friday is the emptiest day — 2 away".

New and reused pieces: `storage.wellness_pattern` (one query, eight weeks,
approved + completed only — a pending request is a plan, not behaviour),
`dashboard_insights.count_bars_geom` and `heat_geom` (coordinates, tone tokens,
aria label and data table, same contract as `bars_geom`). The AWA slides needed
no new query at all: arrangement mix, day-away distribution and per-section
progress are all derived from the period summary already in hand.

**Two layout traps worth remembering**, both found by measuring the rendered page
rather than reading the CSS:

* A deck inside a grid makes the *page* scroll sideways. A grid item sizes to its
  max-content, and a deck's max-content is every slide side by side —
  `min-width:0` on `.oc-card` is load-bearing.
* `.sr-only` is `position:absolute`, so without `position:relative` on
  `.deck-track` the screen-reader chart tables take the `.deck` outside it as
  their containing block, escape the track's clipping, and drag the document four
  screens wide from slide 5's static position.

### "The selected activities are no longer in this view" — when they were

**Symptom.** An admin creates or imports a pair of duplicate activities, ticks
them on /reports/activities and picks Merge, and the bar refuses: *the selected
activities are no longer in this view*. Trying again a moment later works. Found
as an order-dependent test failure — `test_bulk_merge_route_admin_merges_across_dates`
passed alone and failed after any test that had already loaded a page.

**Cause.** The bulk route validated the ticked ids against the memoised `events`
view. `get_atoms` deliberately serves a stale-but-serviceable frame while it
rebuilds in the background, and `view_memo` keys on the frame a view was built
from — so for one refresh, rows added moments ago are absent from that view. Run
alone the test cold-starts (a blocking build, so fresh); after any earlier
request there is a warm frame to serve instead. The window is small but lands
exactly when a curator is most likely to act: right after creating the thing they
mean to merge.

**Fix.** On a total miss, `invalidate_atoms()` and re-resolve once before
concluding the selection is gone. A hit still costs nothing.
`test_bulk_merge_sees_an_activity_created_after_the_view_was_cached` pins the
stale view by hand rather than racing for it — a test that only fails on the
unlucky ordering is how this got missed.

### Faces you can put a name to, and a companion worth looking at

The team wall was pictures with no names — the only label was a native `title=`
that takes a second to appear and never appears on touch. Marks are now 66px
(was 52) and carry a styled name popup on hover **and on keyboard focus**, with
the person's status under the name. The companion is 108px in the hero (was 72)
and each growth stage is 92px (was 64), which is the point at which the
per-stage artwork reads as different plants rather than the same green blob.

"Team filing" — which named the action rather than the thing — is now
**Alternative Work Arrangement**, and the card leads with the dates it covers,
reusing `work_arrangement_period_label` so the card and the printed ANNEX C sheet
name the same fortnight.
## 2026-08-15 (v2.62 — the August 16-31 ANNEX C schedule, transcribed)

### The period the module arrived too late for

**Symptom.** `/work-arrangement/schedule` for August 16-31, 2026 shows 45 blank
rows, and the workbook and PDF exports print the same. The bureau's real
schedule for the period exists — it was filled in, submitted and signed on the
Excel sheet the office has always circulated — but the ANNEX C module only
shipped at v2.59, part-way through the month, so nobody had filed anything in
the app for a period that was already decided on paper.

**Why it could not simply be re-filed.** Filing closes on the last Friday
*before* a period begins — Friday, August 14 for this one — and
`storage.create_work_arrangement` refuses a closed period by design
(`_wa_check_period_open`). That refusal is correct for staff and wrong for a
transcription of a form already approved, and there is no admin "file on behalf"
path. So the sheet is written in as approved rows directly, each carrying its
provenance in `decide_note`.

**Fix.** New `work_arrangement_backfill.py`: the 45 sheet rows as a constant,
plus an idempotent apply that runs once at boot from `app.get_conn()`, guarded
by an `app_setting` marker.

* **42 arrangements** — 4 REG, 5 CWW, 33 WFH — with the weekday the Remarks cell
  nominates. Remarks are not stored: `storage._wa_remarks` re-derives them, so
  the printed annex reproduces the sheet's wording only if the stored
  arrangement and weekday are right. The tests check exactly that.
* **2 No AWA tags** — Sales ("...for approval from OSEC") and Bagos ("Leave") —
  inserted with `effective_from` set to **the period**, not to whatever period
  today falls in. `set_work_arrangement_noawa` uses today's, which would have
  reached back over August 1-15 and quietly altered an annex already submitted.
* **1 row left blank.** Orpilla is blank on the sheet with no reason given, and
  stays blank. The difference between "no arrangement, and here's why" and
  "nobody chased this" is the only signal the Admin Officer has, and inventing a
  reason would erase it.

**Non-destructive, in either order.** Anyone already holding a live arrangement
or No AWA tag for the period is skipped, so a real filing or an admin's
correction outranks the transcription whichever lands first. People are matched
to accounts on order-free name tokens (the sheet writes "Delmendo, Eric" and
"Medel Alexander R."; the directory holds "Eric Delmendo"). A row whose best
match does not clear the runner-up is reported, never guessed — a wrong schedule
on the annex is worse than a missing one, because only the missing one is
visible. `--dry-run` prints the match report and writes nothing.

31 tests in `tests/test_work_arrangement_backfill.py`; the module is registered
in `deploy_hf.RUNTIME_PY` (`test_runtime_py_is_import_closed` catches the
half-closure that would otherwise crash the Space on boot).

## 2026-08-15 (v2.61 — the directory search that did nothing on a phone; archiving people who left; the team comes from the org chart)

### The staff search box that looked dead

**Symptom.** "The search button in the directory to search internal staff is not
working." Two independent faults, and they fail in different places.

**Cause 1 — it did nothing at all under 640px.** `filterTable()` flags a
non-matching row `.nomatch`, and `tr.nomatch { display:none }` was written in
`directory.html`'s own `<style>`. Under 640px `app.css` turns those tables into
stacked cards with `table.resp-table tr { display:block }` — specificity (0,1,2)
against the page-local rule's (0,1,1). The rows were flagged correctly and stayed
on screen anyway. Measured in a real browser: 16 rows flagged `.nomatch`, 19 of
20 still visible at 600px wide. `users.html` carried the identical bug.

**Cause 2 — searching by section found nobody.** The "Assigned to" cell rendered
only `_short_path` ("HSMED/S4"). Nobody looks for a colleague by typing "S4";
they type "Section 4" or "Equity", and both matched zero rows against a
placeholder that promises "name, position, section…".

**Fix.** The hide rule moves to `app.css` as
`tr.nomatch, table.resp-table tr.nomatch { display:none }` — declared right after
the responsive-table block that outranks it, and outside its media query — and
both page-local copies are deleted. The staff row now carries the unit's full
name under the short path, from a `path -> name` map built in `_render_directory`.
A shared `tr.no-hits` row says "No staff match that search" instead of leaving a
header over blank space.

Guarded by `tests/test_directory_search.py`, including two structural tests that
were mutation-checked: putting the rule back inside the media query, or
reintroducing the page-local copy, each fails them.

### Archiving people who have left

**Ask.** "If there are staff that resigned, I as an admin should be able to put
them on archive."

**Design — an archive is not a delete.** `resource_person` gains `archived_at` +
`archived_reason`. The row stays, so every certificate, rating and report that
names that person keeps resolving; what goes away is their place on the CURRENT
roster.

The load-bearing decision is the DEFAULT: `list_resource_persons(conn)` now
excludes archived people, and callers that resolve HISTORY rather than choose
someone now pass `include_archived=True` (`get_rp`, the People grid, the person
page, participation, the exports). Defaulting the other way would have meant
finding every picker; defaulting this way means a picker gets the safe answer
without anyone thinking about it, and the nine history call sites are named in
the docstring.

Archived people also drop out of the org chain of command
(`_org_accounts_at_rank`, `_org_role_filled`, `_org_seat_name`), the wellness and
AWA rosters, and the directory headcount — so a resigned section head is never
offered as this week's approver.

Archiving deactivates the person's linked sign-in. Restoring deliberately does
NOT re-enable it: re-granting access is a decision about permissions, not about a
directory row, and the copy says where to do it.

### The team comes from the directory, not from the account role

**Ask.** "The basis of the team assignment should be the directory, not the user.
I am an admin so I see everything, but that should not be the case — I should
only see my team as section head, which is Section 4."

**Cause.** `_org_scope_for_user` opened with `if user.get("role") == "admin":
return None` — bureau-wide — before it ever looked at the directory. Where
someone sits on the org chart and what the app lets them administer answer
different questions, and collapsing them meant the team view stopped being a team
view for exactly the people most likely to hold the admin role. Verified in the
running app: the Section 4 head's landing page, wellness register and AWA
schedule showed all 19 staff.

**Fix.** `team_scope_for_user` is now the single resolver and reads the directory
first: the Director seat (org rank 3, which `_org_rank` finds in `position`) gets
"bureau"; anyone else with an org unit gets that unit's subtree whatever their
role; only an account with no directory seat falls back to the role, where admin
still means bureau. `_org_scope_for_user` becomes a thin wrapper that folds "no
team" back onto None for its chief-guarded callers. Same account after the fix:
Section 4 only, on all three pages. An admin with no directory seat still sees
all 19.

The approval queues follow the same rule. `list_wellness_approvals` and
`list_work_arrangement_approvals` shared a `role == "admin" -> see everything`
branch; they now share `_mine_or_orphaned`, which gives everyone the requests the
chain routes to them and gives an admin the ORPHANS on top — the requests that
reach nobody because the claimant is unlinked, sits under an unfilled seat, or is
the Director. Admins stay the fallback ABOVE the chain rather than a bypass
around it, so nothing is stranded and nothing routine leaks sideways.

### Verification

`qa_preflight.py` GREEN, `qa_smoke.py` ALL PASSED, and the full pytest run
matches the pre-change baseline exactly (the same 16 failures, all from this
checkout shipping an empty `css_is.db`). 20 new tests across
`test_directory_archive.py`, `test_directory_search.py` and `test_team_scope.py`.
All three fixes were also driven end-to-end in a real browser against a seeded
five-section bureau.

## 2026-08-15 (v2.60 — CSS-IS becomes Office Connect; the companion answers back)

### The care button that looked broken

**Symptom.** The single largest friction source in the app, by a wide margin.
The 30-day UX telemetry ranks "Feed Nori Miguel" at friction score **351** (78
rage-clicks, 5 users) and "Water FernFern" at **117** (26 rage-clicks, 3 users) —
first and third of fifteen. Eleven Spot Feedback comments matched, among them
"Not watering" and "Di gumagana smh sakin ayaw asar."

**Cause.** `static/js/avatars.js` flashed a thank-you bubble **only when the
POST came back `counted: true`**. `counted` is false inside
`AVATAR_CARE_COOLDOWN_HOURS` (6 h) — which is a *success*, not a failure: the
companion has already been cared for. But the client said nothing at all, so the
tap read as a dead button and people tapped again, and again.

Worse for anyone on `prefers-reduced-motion`: `_avatars.html:202-207` sets
`animation:none !important` on everything matching `[class*="av-"]`, which
suppresses the watering/feeding animation too. Those users got **no feedback of
any kind** — no animation, no bubble. (The bubble itself survives, being
opacity-only, which is what makes it the right place to fix this.)

**Fix.** One call site: always flash a bubble, with the wording carrying the
state — "Ahh, thank you! 💧" when the care counted, "Still nicely watered 💧"
when it was already done. Nothing server-side changed; the cooldown rule and
`record_avatar_care`'s contract are untouched, and all 29 `test_avatar_care.py`
tests still pass. `avatars.js` cache-buster bumped to `?v=20260815a`.

### The companion's growth ladder

The avatar has had six growth stages since it shipped, but only ever showed the
one you were on. Nothing on screen said the others existed, what they looked
like, or how to reach them — and the 30-day telemetry says people could not even
tell whether *caring* for it was working (see the care-button fix below).

All six stages of **your own species** now render side by side: reached ones in
colour, locked ones dimmed with the point threshold that unlocks them, and "You
are here" on the current one. Beneath sits the progress bar to the next stage and
a plain list of what actually earns points — take a break **+10**, write a
reflection **+5**, use your full 2 hours **+5**, each streak week **+2**.

Two deliberate details:

- **Everything is derived.** The stages come from `AVATAR_STAGE_NAMES`, the
  thresholds from `WELLNESS_LEVELS`, and the how-it-grows list is read straight
  off the `WELLNESS_PTS_*` constants via `avatar_growth_actions()`. The
  explanation cannot drift from the arithmetic it describes — there is a test
  asserting each number comes from its constant.
- **Caring for it is named as *not* being a way to level up.** Watering or
  feeding earns the *Devoted caretaker* badge, not points. Listing it alongside
  the four scoring actions without saying so would have implied a fifth route to
  growth that does not exist.

Shown on the new landing page and on `/me` — where you pick the companion in the
first place, which is exactly where not knowing how it grows was most obvious.

### `/` becomes the Team View

The landing page people actually see. `/` was the most-visited screen in the app
(520 views in 30 days, all 18 users) **and** its second-highest exit point: it
routed and did nothing else. People dead-clicked the greeting itself — 19 times,
with 17 matching Spot Feedback comments — expecting it to do something.

**Now:** greeting and companion, a **Team | Me** toggle, three panels, then the
three doors exactly as before.

- **Wellness** — a wall of faces (pictures, not names, by request), each ringed
  by the hours they've used against the 2-hour entitlement, over "9 of 14 have
  filed · 64% of hours used".
- **Work arrangement** — a stacked Approved/Pending/Not-filed bar, the same face
  wall, a Mon–Fri on-site coverage chart with the thinnest day called out, and a
  named chase list. It leads with the period **open for filing**, not the one in
  force, because the in-force period's deadline has already passed and a landing
  page leading with it could only ever say "too late".
- **CSS** — recent activities with their ratings, each row saying *why* it is
  listed (`Organised` / `Spoke` / `Your section ran this`), plus what's coming
  up. Low-n scores are shown muted with an explicit "too few to read" chip rather
  than hidden.

**The toggle is a real link**, not JavaScript — `/` and `/?view=me` — matching
how the rest of the app degrades. It appears only for someone who *has* a team:
an account with no directory link gets the personal view and an explainer, never
a Team tab that could only ever be empty.

**Copy that carries a schema limit.** A permanent footnote reads *"Attendance
isn't recorded here — only who ran an activity and who spoke at it."* There is no
staff→activity attendance relation in this system, so without that line the panel
reads as an attendance log and is simply wrong. A test asserts the page never
says "you attended".

**The page cannot lock anyone out.** If the payload build fails for any reason
the handler logs it and falls back to the greeting plus the three doors — which
is exactly the page this one replaced. The one-time onboarding guard stays
precisely where it was.

`templates/choose.html` is deleted; `office_connect.html` and a `_faces.html`
partial replace it. Every colour resolves from a tone token the Python side
chose, and a test slices out the page's own `<style>` block and fails on any
literal hex — with 3 themes × 6 accents × 2 densities, a hardcoded colour is
wrong in nearly every combination.

11 new tests across `test_landing_fork.py` (doors, toggle, panels, the
attendance disclaimer, token discipline), `test_a11y_charts.py` (the faces wall
is pictures-not-names, so its `chart_table` really is the accessible reading of
it) and `test_routes.py` (`/?view=me` joins the smoke list).

### The Team View data layer (`office_connect.py`)

No user-visible change yet — this is the payload the landing page will render,
built and tested ahead of the page itself so the page can be pure markup.

**One public function**, `team_view_data(conn, user, *, get_atoms, view_memo)`,
returning `{me, scope, panels: {wellness, awa, css}, notes}` with each panel
carrying a `team` and a `personal` view.

**Why a new module.** `dashboard_insights` is deliberately `conn`-free and pure;
`storage` has the connection but knows nothing about the atoms cache; `app.py` is
already ~13.8k lines and this is how it got there. The cache primitives are
**injected rather than imported**, which keeps the dependency one-way (no
circular import) and — usefully — lets the tests hand it a fabricated events list
through the memo seam, so the activity predicates are testable without seeding a
whole atoms DataFrame.

**Scope is the safety-critical part.** `team` is `None`, not an empty dict, when
the viewer has no team — there is no code path where an unlinked account receives
a team payload at all. The team builders are not merely filtered, they are **not
called**, because passing such a user to `wellness_week_rollup` or
`work_arrangement_period_summary` is bureau-wide by contract.

**"Involved in an activity" is defined by what the schema can actually support.**
There is no staff→activity attendance relation — `attendee` rows are external
registrants with no account link — so *personal* means **spoke at OR created**.
Organiser-unit is deliberately excluded there: "my section ran it" is not "I was
involved". The *team* view adds it, because there it means exactly what it says,
and every row records which relation qualified it (`unit` / `spoke` / `ran`).

**The activity index** is memoised bureau-wide and viewer-**independent**; all
filtering happens per request against the viewer's own resolved scope, so there
is no per-team cache entry for a key bug to expose. Two tests drive the same
payload through a *warm* dict-backed memo in both request orders to prove it.

Other details worth noting: `build_events` carries no org path or creator (it
groups atoms, not rows), so both are joined back from `list_activity_instances`;
upcoming activities cannot come from `build_events` at all, since it drops
zero-respondent events and an activity that hasn't happened has none; low-n
scores are shown muted rather than hidden; an f3-only activity links to the
type-3 report because `/reports/activities/{id}` 404s without a Form-2 block; and
the AWA panel leads with the period **open for filing** rather than the one in
force, whose deadline has already passed.

**Geometry** (`ring_geom`, `bars_geom`) went into `dashboard_insights.py` beside
`_svg_geom` / `_count_geom`, keeping the house rule that templates only draw
strings handed to them. Neither emits a colour — callers get semantic tone tokens
(`green`/`accent`/`amber`/`red`/`soft`) that the template maps once, which is
what keeps 3 themes × 6 accents working. Both return their `chart_table` rows
alongside the coordinates.

**One deploy fix caught by the suite:** `office_connect.py` had to be added to
`deploy_hf.RUNTIME_PY`. `test_runtime_py_is_import_closed` asserts the shipped
file set is import-closed, so without it the Hugging Face deploy would have
shipped an `app.py` whose import fails at startup.

19 new tests in `tests/test_office_connect.py`.

### Groundwork for the Team View (storage layer)

No user-visible change; five small `storage.py` changes the landing page needs,
each defensible on its own.

**1. `team_scope_for_user` — the one that matters.** `_org_scope_for_user`
collapses two very different situations onto the same `None`: an admin, who is
*meant* to see the whole bureau, and an account with **no directory link**, which
has no team at all. `_path_in_scope(path, None)` is `True` for everything, so
`None` means "show me everyone". That is safe today only because every caller
sits behind `user_is_approving_chief`, which has already excluded unlinked staff.

The Team View is shown to **every** signed-in user with no such guard by design.
Without this helper, an unlinked account would have seen every wellness and
work-arrangement filing in the bureau. `team_scope_for_user` returns an explicit
`(scope_path, kind)` where `kind` is `bureau` / `unit` / `none`, so "no team" can
never be mistaken for "all teams".

**2. `wellness_week_rollup`, split out of `wellness_dashboard_data`.** The parent
also builds an all-weeks pending queue: it selects *every* pending claim in the
bureau, hydrates each one with its own `get_wellness_claim` call, and only then
filters by scope. Correct for the monitoring page; far too expensive for a page
every user loads at every sign-in. The rollup is the cheap half — one query, no
queue, no bureau-wide reflection rate. `wellness_dashboard_data` now calls it and
adds the queue on top, so the monitoring register and the landing page cannot
quietly disagree about a section's hours (asserted directly in the new tests).

**3. Face columns, joined not queried.** `wellness_week_rollup` and
`work_arrangement_roster` now carry `rp_id`, `has_photo` and `avatar_kind` (plus
`position` / `designation` on the former) as joined columns, so drawing a grid of
people costs no additional query per person.

**4. `fi.created_by` on `list_activity_instances`.** The creator is one of the
few relations tying a *staff member* to an activity — attendees are external
registrants with no account link — and it wasn't being selected.

**5. One redundant query per section removed.** `work_arrangement_period_summary`
loops over org paths calling `work_arrangement_coverage`, and each call re-ran
`_wa_noawa_for_period` with identical arguments. The set is per-*period*, not
per-section, so it is now looked up once and passed in. For a section-scoped
chief that saves one query; for a bureau-wide view it removes one per section.

New `tests/test_team_scope.py` (8 tests): scope resolution for linked staff,
admins and the unlinked case; that `_path_in_scope` does not leak across sibling
sections (`…/S1` must not match `…/S10`); the rollup's scoping and face columns;
that the split kept `wellness_dashboard_data` numerically identical; the roster
columns; and the creator column.

### Seven nav groups become four

**Why.** The menu had **seven** groups (Dashboard, Wellness, Work arrangement,
Reports, Data entry, Manage, Admin) for what are really four products — two of
them holding a single item each. Worse, six pages that exist and work appeared in
**no menu at all**: `/wellness/apply`, `/wellness/dashboard`,
`/wellness/approvals`, `/work-arrangement/file`, `/work-arrangement/schedule`,
`/work-arrangement/approvals`. They were reachable only by typing the URL or
through an in-page link.

**Now: Wellness · CSS · AWA · Administrator.** Order follows measured usage, not
org-chart tidiness — `/wellness` draws 348 views from 17 of 18 users in 30 days,
more than the entire Reports group. Within Administrator the same rule applies:
`/admin/ai` (53 views, 4th busiest screen in the app) leads, Audit (2) and
Sharing (1) trail.

**Sub-sections inside a dropdown.** CSS holds sixteen destinations, which as a
flat list would be worse than what it replaced. Items now carry an optional
`section` label, written **once** on the first item of a run and inherited by the
rest, rendered as headings inside the menu: *See how we're doing · Official
reports · Run a survey · Data entry*. Two details that matter:

- The label is resolved **before** cap-filtering. Filtering first would orphan a
  run whose label happened to sit on an item the viewer can't open — "Run a
  survey" lives on New survey (`create_activity`) while Monitor after it needs
  `manage_event`.
- A section whose every item is capped away disappears rather than leaving a
  stray heading (an encoder sees Paper entry but no empty "Run a survey").

**A capability that isn't a role.** The four team pages gate at runtime on
`storage.user_is_approving_chief` — a directory *rank* lookup, not an account
role — so `NAV_GROUPS`'s `cap` field could not express them. They now carry
`cap="chief"`, resolved once per request in the auth middleware into
`request.state.is_chief` (on the connection it already had open) and passed down
to `nav_groups_for` / `search_index_for` / `ai_route_catalog` / `help_catalog_for`.
All four surfaces stay in lockstep, so a plain staff member is never handed a
link they cannot open — and the ⌘K palette, `/search`, `/help`, `/start`'s
suggestions and the NL router all learned about the six newly-surfaced pages for
free, because `NAV_GROUPS` remains the single source of truth.

Four new tests in `tests/test_search.py`: the group shape and section ordering,
the `chief` cap gating nav *and* the search index together, empty sections
vanishing, and the rendered markup (the data-level assertions alone don't prove
`dash_layout` draws it).

### The "this week" card that was a dead target

**Symptom.** Friction rank 7 in the same telemetry: **33 dead-clicks from 9
users** on the wellness hub's *"This week (…): 0 of 2 hours claimed · Request a
break"* panel, with **10 matching Spot Feedback comments**. Only the trailing
button was clickable. People clicked the status text and the hour pips — the part
that *states the problem* — and nothing happened.

**Fix.** The stretched-link pattern (`wellness_hub.html`): the real anchor grows
via `::after { position:absolute; inset:0 }` to cover the card, so the whole
panel becomes the hit area while there is still exactly **one** tab stop and one
accessible name. No JS, no duplicate link. Scoped to a new `.tappable` class on
purpose — the monthly-register panel below is *also* `.panel.entitle` and holds a
`<select>` that must stay operable under any overlay.

**Secondary bug fixed in the same markup.** The button was an `<a href>` carrying
`aria-disabled="true"` when nothing could be requested. The CSS rule's
`pointer-events:none` stopped a *mouse*, but the anchor stayed focusable and
Enter still navigated — so keyboard and screen-reader users were told the control
was disabled and then taken to the form anyway. It now renders as a `<span>` in
that state, with a title naming the real window (`window_weeks`, passed from
`app.py` so the copy can't drift from the `can_request` computation).

Two regression tests added to `tests/test_wellness.py` — one asserting the card
carries exactly one anchor to `/wellness/apply`, one asserting the disabled state
exposes no `href` at all.

### The rename

**Why.** The name described one of three things the system now does. After the
wellness module (v2.25) and ANNEX C (v2.58), a staff member signs in as often for
a two-hour break or a work arrangement as for a survey report — but the product
still announced itself as the Client Satisfaction Survey Information System. The
name had stopped describing the thing.

**Scope — the shell only.** This is a rename of what people read, not of what the
machine runs on. Deliberately left alone:

- **`css_is.db`** (~100 references across `app.py`, `backups.py`, `pull_backup.py`,
  `daily_backup.py`, `setup_db.py`, `migrate.py`, `deploy_hf.py`, `Dockerfile`,
  `.gitignore`) — renaming the database file orphans every existing deployment
  and every backup path.
- **`css_is_engine.py`** (imported as `eng` by 21 modules) — the SERVQUAL/CSM
  calculator. A pure internal identifier; no user ever sees it.
- **`CSS_*` environment variables** (`CSS_DB`, `CSS_BASE_URL`, `CSS_SMTP_*`,
  `CSS_GEMINI_API_KEY`, `CSS_OFFSITE_DIR`, `CSS_NO_SCHEDULER`) — a deployment
  contract.
- **The `/css` route and the name "CSS"** — that is the Client Satisfaction
  Survey, a real programme with a real name, and it keeps it. Office Connect is
  the building; CSS is one of the rooms.
- **`sw.js`'s `css-is-` cache-name prefix** — changing it silently invalidates
  the app-shell cache of every installed client.
- **`~/CSS-IS-prod-backups`** (`daily_backup.py`) — an on-disk path on the ops
  machine with existing history behind it.

**Changed.** The wordmark and `<title>` in `dash_layout.html` and
`public_layout.html`; the sign-in screen; the eight public-form page titles; the
two account emails in `mailer.py`; the PWA manifest `name`/`short_name`
(`app.py:6353`) and `static/offline.html`; the FastAPI app title; the report and
export source lines (`dashboard_export.py`, `report_docs.py`, `csm_report.py`);
the bilingual `thanks_title` in `i18n.py` (both `en` and `fil`); the UX handoff
brief header in `ux_handoff.py` and its two asserting tests; and the module
docstrings.

**Verification.** `qa_preflight.py` GREEN. `pytest`: 1174 passed, with the same
16 pre-existing failures before and after the change (they need a seeded
`css_is.db`, which is gitignored) — a before/after diff of the failure list is
empty, so the rename introduced no regressions.

## 2026-08-15 (v2.59 — "No AWA": the blank row learns to say why)

**Symptom.** v2.58 left two rows of the source ANNEX C with nowhere to go, and
they are the same shape:

1. **Bagos, Jesel** — Remarks read `Leave`. No arrangement, no way to record why.
2. **Sales, Miriam Cecilia** — *"With requst WFH due to medical condition, for
   approval from OSEC"*. A decision pending **outside** the bureau, arriving
   mid-period, long after the Friday deadline had shut.

Both printed as blank rows, indistinguishable from someone who simply never
filed — reintroducing, for these two cases, exactly the ambiguity the module was
built to remove. (2) was additionally the one case where the deadline had a real
cost: the system could only say no.

**Fix.** One mechanism for both: a standing **`No AWA`** tag carrying free text.
It is a statement of fact rather than a request for a schedule, so it needs no
approver and no filing window — which is what lets it cover a mid-period
situation without inventing an override.

- **`storage.py`** — `work_arrangement_noawa`, stored as an **interval**
  (`effective_from` / `effective_to`) rather than a row per period. Carry-over is
  then structural: an interval spans every period between its ends, so nothing
  runs at a period boundary and there is no rollover job to fail silently. Same
  partial-unique-index trick as the arrangement table
  (`ux_wa_noawa_live … WHERE effective_to IS NULL`), so closed intervals fall
  outside it and the history of past reasons accumulates.
- **`storage.py`** — rewording **closes the current interval and opens a new
  one** from the current period. A period whose annex has already been submitted
  keeps the wording it went out with. Rewording *within* the period it started in
  corrects in place instead, since there is no history to preserve yet.
- **`storage.py`** — `_wa_noawa_may_act`: the person or an admin, symmetric with
  who may remove it. An admin has to be able to record a long leave for someone
  who is not signing in; a peer or even their section chief cannot speak for
  them.
- **`storage.py`** — the tag takes effect from the period you are **in**, not the
  next one open for filing. That is the whole point for case (2).
- **`storage.py`** — three integration points. `work_arrangement_roster` merges
  the tag in and lets it **outrank a stale filing** (the stated reason is the
  truth); `work_arrangement_export_rows` prints `No AWA` + the reason;
  `work_arrangement_coverage` drops tagged people from the denominator
  **entirely** — not on-site, not off-site. Someone on leave was never going to
  be at a desk on Friday, and counting them either way misstates the figure the
  warning exists to report. `work_arrangement_period_summary` drops them from
  "filed n of m" too, and surfaces them as their own list so a shrinking
  headcount is visible rather than mysterious.
- **`storage.py`** — filing while tagged is **refused**, naming the Remove
  action, rather than silently clearing the tag. Deleting someone's stated reason
  as a side effect of an unrelated action is the kind of surprise that costs
  trust in the record.
- **`app.py`** — `POST /work-arrangement/no-awa` and `…/remove`. Authority lives
  in storage, so the self path and the admin path are one code path with one
  rule; both audit with the subject named, because an admin acting for someone
  else has to be attributable.
- **`templates/`** — the hub collapses to a single card while a tag is live (no
  point offering a form that would only refuse), with an unobtrusive
  `<details>` offer when there isn't one. The schedule page gains a `No AWA`
  pill, the excluded-from-the-counts note, and per-row admin set/remove controls.
- **`work_arrangement_annex.py`** — unchanged. It renders whatever the rows
  carry, so both the workbook and the PDF picked this up for free.
- **`tests/test_work_arrangement.py`** — 16 new tests (80 total). The ones worth
  keeping honest: persistence across five periods **with nothing run in
  between** (if it ever fails, the tag has quietly become per-period); rewording
  later leaving the old period's wording intact; `test_noawa_needs_no_approval_and_ignores_the_deadline`,
  which asserts a filing is refused at that same moment and the tag is not — if
  that ever starts raising, case (2) has no path again; and the coverage flag
  thresholds re-derived against the smaller section rather than just re-run.

## 2026-08-14 (v2.58 — the ANNEX C work arrangement schedule becomes a record, not a spreadsheet)

**Symptom.** BLHSD maintained its Internal Work Arrangement Schedule (ANNEX C) as
a hand-kept Excel file, one sheet per half-month, 45 staff. Reviewing the live
file (`August 16_31_2026.xlsx`) surfaced four failure modes, all of them
structural rather than clerical:

1. **23 of 45 rows blank** on the Aug 1–15 sheet. The period was never finished
   and nothing in the file makes an unfilled row distinguishable from a
   deliberate one.
2. **No approval trail.** One row read *"With requst WFH due to medical
   condition, for approval from OSEC"* — a pending decision parked in a
   free-text cell, with no record of who decides it or when.
3. **Identity drift.** "Ventura, Ray Justine" on one sheet, "Ray Justin" on the
   other. Two spellings of one person, in one workbook.
4. **No coverage check.** 18 of 45 staff (40%) off-site every Friday; Tuesday had
   2. Nothing surfaces that at the moment someone picks their day — the only
   moment it is cheap to change.

**Fix.** A new module built on the wellness module's shape (per-employee,
date-keyed, status machine, approver resolved from the org chart, official-form
export), because that pattern already solves this problem in this codebase.

- **`storage.py`** — the shared **"Org chain of command"** section, lifted out of
  the wellness block: `_org_rank`, `_org_parent_path`, `_org_accounts_at_rank`,
  `_org_role_filled`, `_org_seat_name`, `approver_name_for`, `get_approvers_for`,
  `is_approver_for`, `user_is_approving_chief`, `approver_title_for`,
  `_org_scope_for_user`, `_path_in_scope`. Who approves you is a fact about the
  org chart, not about what you are asking for. The old `wellness_*` names are
  bound as module-level aliases — the SAME functions, not copies — so every call
  site and both wellness suites keep working untouched. (An alias is an identity
  binding: `monkeypatch.setattr(st, "get_approvers_for", ...)` would not affect
  `st.get_wellness_approvers`. Nothing patches these today.)
- **`storage.py`** — the `work_arrangement` table. `period_start`
  (`'YYYY-MM-01'`/`'YYYY-MM-16'`) keys the period the way `wellness_claim.week_start`
  keys a week. **Two** partial unique indexes, not one: at most one `approved`
  AND at most one `pending` per person per period — one schedule in force plus
  one change in flight. Denied, withdrawn and superseded rows fall outside both,
  so the trail accumulates and re-filing after a denial still works.
- **`storage.py`** — the deadline is the last Friday **strictly** before a period
  begins (a period starting on a Friday closes the Friday prior). A period that
  has begun is closed. Every refusal names both the missed deadline and the next
  open period.
- **`storage.py`** — the Remarks cell ("Friday Day off", "Wednesday WFH") is
  **derived** from `arrangement` + `weekday`, never stored. The source file's
  hidden `Lists` sheet is exactly that cross product.
- **`storage.py`** — changes are staff-initiated only, and file a successor with
  `supersedes_id` rather than editing in place. Approving one retires its
  predecessor in the same transaction, so the "one approved per period" index is
  never momentarily violated. Fixes (2).
- **`storage.py`** — `work_arrangement_coverage` is the first **advisory** rule in
  the codebase: `create_work_arrangement` never consults it and it never raises.
  CWW and WFH are counted apart (a compressed day off removes a person; a WFH
  person is still working). Scope is the exact section path, not the subtree — a
  division rollup would hide an empty section behind a full one. One function
  behind both the employee's live note and the chief's queue flag, so the two
  cannot contradict each other. Addresses (4).
- **`storage.py`** — `work_arrangement_roster` reads **FROM `admin_user` outward**,
  not from `work_arrangement` inward. The blanks are the information: someone who
  never filed is a named row, not a silent gap. Fixes (1).
- **`work_arrangement_annex.py`** (new) — both annex builders in one module,
  because the masthead, the six columns, the verbatim legend and the signature
  block must be identical across Excel and PDF. Excel gets a sheet per half-month
  (`?month=` renders both halves, the file the bureau circulates); the PDF is A4
  **landscape**, since six columns do not fit portrait. Signatories resolve from
  live directory data — the Director via the shared org chain, the preparer from
  an `app_setting` override or the exporting user. Nothing else in this repo
  hardcodes a person's name. Names coming from `resource_person` fixes (3).
- **`app.py`** — hub, filing form (which doubles as the change form), change and
  withdraw posts, approvals queue, decide, period schedule, and the two annex
  downloads. Chief-only pages gate in-handler on `st.user_is_approving_chief`,
  the wellness precedent, because "section chief" is a directory fact and not one
  of the four roles — so `_required_cap()` needs no entry. New nav group and a
  third door on the landing chooser.
- **`deploy_hf.py`** — `work_arrangement_annex.py` added to `RUNTIME_PY`. A module
  imported by `app.py` but missing there is a production `ModuleNotFoundError`
  (see the v2.40 hotfix).
- **`tests/test_work_arrangement.py`** (new, 64 tests) — period and deadline
  arithmetic across leap years, year boundaries and a period that starts on a
  Friday; validation; the partial index as a race backstop; the full change flow
  including denied-and-cancelled leaving the original standing; escalation
  through the shared chain; an identity guard that the wellness aliases are the
  same objects; coverage warning **and** the filing still succeeding and being
  approvable; RBAC; both exports asserted against the form's actual text.
  `tests/test_search.py` and `tests/test_routes.py` pick up the new nav group
  and routes.

## 2026-08-11 (v2.57 — the MRR activity workbook stops repeating itself, row to row)

**Symptom.** Every row of `AGENDA 4_Sheet1` in the activity Excel download read
the same. Three separate causes:

1. **Next Steps and Timeline** was a *hardcoded constant string* in
   `_activity_mrr_analysis` — byte-identical on 100% of rows, always.
2. **Action** and **Resources Needed** were keyed on the weakest dimension of
   `e["ranked"]`, which for an activity carries only **three** dimensions
   (`EVENT_DIMS_FORM2` drops Assurance and Empathy), so the whole bureau drew
   from at most three strings each. The `Assurance`/`Empathy` entries in
   `_MRR_RESOURCE` were unreachable. `Action` also borrowed `di.DIM_TA`, which is
   second-person coaching written for a *resource person* ("Rehearse the
   opening", "Test your slides") — the wrong register for an improvement plan
   about an activity.
3. **The COMMENTS block** filled with quick-pick chips. `rating.html`'s
   tap-to-add chips (`REMARK_CHIPS` / `i18n.REMARK_CHIPS_FIL`) write their words
   straight into the free-text `remarks` box, so a stored "verbatim" is often
   just the canned options — and dedup only ran *within* one activity, so the
   same phrases repeated down every row while real typed comments were pushed
   past the cap of 5. Per-item notes (`v["notes"]`), which are always typed, were
   never read at all.

**Fix.** Same two routes, same workbook shape, same saved-draft precedence.

- **`app.py`** — `_split_chip_remark` splits a remark into tapped options and
  typed words (a mix counts on both sides, so using the chips never costs someone
  their written comment); `_CHIP_CANON` folds the Filipino chip list onto its
  English twin by position so one activity's tally isn't split by language.
  `_attach_chip_picks` sets `comments` (typed only, now including item notes) and
  `chip_picks` (count-ordered options). `_activity_comment_lines` fills the five
  slots with typed words first and only backfills with options, labelled as such;
  a workbook-level `spread` dict rotates which options backfill, and each row
  leaves at least one of its own options unclaimed so the rotation can't stall.
- **`app.py`** — `_activity_mrr_profile` reads the **five**-dimension scorecard
  (`report`, already attached before the workbook is built) and derives severity,
  a runner-up, response rate, modality and the one improvable option enough
  respondents picked. The four columns are generated from that profile:
  `_MRR_ACTION` (dimension × severity, Tangible × modality, in MRR register),
  a timeline pinned to the activity's own date/quarter/name, and resources sized
  to modality and crowd. An evenly strong activity gets a sustaining line, never
  a correction. Deterministic — a re-export of unchanged data is unchanged.
- **`app.py`** — the activity page grafted `report` and the option tally onto its
  event copy before drafting; without it the on-screen MRR form would have drafted
  from less than the download, breaking the promise in its own comment. The AI
  draft path (`_mrr_draft_prompt`) gets the same evidence — scorecard, rate,
  modality, option tally — but still never sees a typed comment.
- **`storage.py`** — `NON_COMMENT_ITEMS` public alias, so the export can skip
  encoding metadata (`SEX`/`AFFIL`/`RESPONSE_NO`) without reaching into a private
  name.
- **`tests/test_mrr_export_nuance.py`** — 13 tests: typed words outrank options,
  item notes count as typed, options are always labelled, the backfill rotates
  across rows and only repeats when a row has nothing else, a full cell spends no
  chip budget, the four columns differ across three activities, the timeline
  carries each activity's own date, resources split on modality, and the page
  preview matches the download.

## 2026-08-11 (v2.56 — activity forms stop reading as if they rate a person; dashboard labels match the questions)

**Symptom.** Forms 2 (activity) and 3 (resource person) shared one set of
statements in `app.B_TEXT`/`A_TEXT`/`C_TEXT` with a `{subject}` placeholder that
`survey_spec()` filled with the resource person's name on F3 and the *activity's
title* on F2. The statements are written about a human, so an activity form
rendered "15th Learning Exchange Session was responsive and willing to address
questions and needs", "… was knowledgeable and competent in the subject", "…
gave caring attention to participants". Two defects shared that root cause: the
title was also redundant (`rating.html`/`combined_form.html` already show it in
the header, so it repeated on all eleven questions), and an F3 form with no
`rp_name` fell back to the activity title — an event's name inside a question
about a person.

**Fix.** Type 2 gets its own wording; Type 3's is untouched. Item ids, scales,
N/A handling and the dimension maps are unchanged, and each item keeps the
meaning it had, so nothing recalculates and past F2 results stay comparable.

- **`app.py`** — new `B_TEXT_ACTIVITY` / `A_TEXT_ACTIVITY` / `C_TEXT_ACTIVITY`
  beside the existing constants, deliberately with **no** `{subject}` token.
  `survey_spec()` picks them on `survey_type == 2` (same shape as the existing
  `fil` dict swap). The F3 no-name fallback is now a localised
  `i18n.t("subject_rp", lang)` — English text was leaking into the Tagalog
  statements ("Si/Ang the resource person ay maalam…") when it was hardcoded.
  A small `_say()` helper capitalises a rendered statement so the lower-case
  generic subjects ("the resource person", "this activity") read correctly both
  at the start of a sentence and mid-sentence. Every consumer — `rating.html`,
  `combined_form.html`, the monitor's per-attendee view, the encode/staff paths
  — renders `spec`, so all of them inherit this.
- **`i18n.py`** — `B_TEXT_ACTIVITY_FIL` / `A_TEXT_ACTIVITY_FIL` /
  `C_TEXT_ACTIVITY_FIL`, marked DRAFT like the rest of the Filipino strings.
- **`tools/i18n_review.py`** — the new maps join the bureau review batch. The
  existing placeholder check already tolerates strings with no placeholder
  (`if needed and …`), which is what the F2 wording is.
- **Tests** — `tests/test_survey_wording.py`: F2 carries none of the person
  phrasings and never repeats the activity title (English and Filipino); F3
  wording is byte-identical to before; a nameless F3 says "the resource person"
  (and "tagapagsalita" in Filipino, never the English phrase);
  both forms still emit the same ids/scales/N-A/dimensions, and language changes
  only labels, never stored values. `tests/test_i18n_review.py` covers the new
  review keys and that a no-placeholder suggestion is accepted.

### Part 2 — the dashboard's dimension labels

**Symptom.** `dashboard_insights.DIM_LABELS_*` / `DIM_CONCERN_*` described a
different set of B-items than the app asks. Their comments cite the column
headers in `CSS Spreadsheets.xlsx` (not in the repo), which evidently describes
the bureau's original instrument: F2 B6 = organizers polite, B7 = sensitive to
participants' needs, B8 = facility appearance. `eng.DIM_MAP_FORM2` matches
*that* instrument exactly. `app.B_TEXT` never did — its own comment calls it
"sensible default text" — so the labels have been describing questions nobody
was asked, on **both** forms: item B6 ("knowledgeable and competent") was
reported as "Courteous organizers", and F3's B9 ("the materials, venue, and
presentation…") as "Neat & well-presented — well dressed and appears neat".

**Fix (labels only — no number moves).** Every label and concern phrase is now
written from the items its dimension actually contains, i.e.
`app.B_TEXT_ACTIVITY` / `app.B_TEXT` grouped by `eng.DIM_MAP_FORM2` /
`DIM_MAP_FORM3`. A header comment names those two as the only source of truth.

| Dimension | Was | Now |
|---|---|---|
| F2 Reliability | Met its objectives | Delivered as promised |
| F2 Assurance | Courteous organizers | Knowledgeable organizers |
| F2 Empathy | Attentive to participants | Clear & reassuring |
| F2 Tangible | Venue & set-up | Attention & set-up |
| F3 Reliability | Clear & well-prepared | Delivered as promised |
| F3 Assurance | Confident & credible | Knowledgeable & clear |
| F3 Tangible | Neat & well-presented | Materials & venue |

F2/F3 Responsiveness and F3 Empathy already described their items and are
unchanged.

- **`dashboard_insights.py`** — the four label/concern dicts, plus two stale
  comments that asserted the old item meanings (the `build_events` note on why
  the event score excludes Assurance/Empathy, and the `EVENT_DIM_LABELS` alias
  note claiming Tangible is "the materials and the venue/facilities").
- **Tests** — `tests/test_dimension_labels.py`: every dimension has exactly one
  label and one concern; each label shares vocabulary with the items it covers
  (a heuristic — the explicit assertions naming each corrected label are the
  real guard); F2's Tangible label names both of its items; and the scoring maps
  are asserted unchanged, since this was a display-only change.

**Known, deliberately not fixed.** `eng.DIM_MAP_FORM2`'s Tangible bucket
averages B8 ("caring attention to participants") with B9 ("materials, venue, and
presentation") into one number — two different constructs, which is why the
honest label is compound. Grouping F2 like F3 (Assurance = B6+B7, Empathy = B8,
Tangible = B9) would make every bucket coherent, but `overall_perception` is the
mean of *dimension* means and the Activities page scores `EVENT_DIMS_FORM2`
(Assurance/Empathy excluded), so B8 would drop out of the event score and
Tangible would become B9 alone — moving every historical activity's published
score, by roughly ±0.3 of 7 wherever B8 and B9 diverge. The map is marked LOCKED
for that reason; changing it is a bureau decision, not a code cleanup.

## 2026-07-30 (v2.55 — fix inflated activity respondent counts)

**Symptom.** An activity card showed 212 responses next to a score of 6.0/7 — but
the score was computed from a single response. Investigation (comparing a month of
production backups against `harmonize_undo` journal entries and the app's own
`build_events`/`load_atoms` code, run directly against a pre-incident snapshot)
traced it to `dashboard_insights.build_events`: `_event_group_key` groups Type-2
(activity review) and Type-3 (speaker review) forms together whenever they share
`(event_date, venue, lead_org_id)` — including when venue is blank, which most
activities' is. The group's `respondents`/`response_ids` summed responses across
**every** form in the group, so 11 unrelated speaker-review forms for 5 different
resource persons (sharing the same date/section/blank-venue by pure coincidence)
inflated one activity's response count from 1 to 212. The score next to it was
unaffected — `f2_block`/`activity_servqual` already filtered to `survey_type==2`
internally — only the displayed count (and everything downstream of
`response_ids`: verbatims, demographics, comment overrides, weighted averages) was
wrong.

**Fix.** `build_events` now scopes `respondents`/`response_ids` to the Type-2 ids
only when the event has a real F2 score (`f2_block` is truthy) — matching what's
actually shown. When there's no usable F2 score (no F2 forms, or an F2 with zero
answers), it falls back to the whole group, matching the template's own fallback
to a speaker's score in that case (`elif e.speakers`) — this preserves existing
behavior for F2-less/F2-empty activities (confirmed via the RP roster/report test
suite, which exercises exactly that shape).

- **`dashboard_insights.py`** — `build_events`'s respondent-scoping logic, as above.
  Every downstream consumer (`app.py`'s verbatims/demographics/comment-override/
  export code, the aggregate weighted-average functions later in this file) reads
  from the same `e["respondents"]`/`e["response_ids"]`, so fixing the one source
  fixes all of them — no other call site needed touching.
- **Tests** — `tests/test_activity_respondents_excludes_speakers.py`: a Type-2
  activity sharing a date/section/blank-venue with two resource persons' Type-3
  reviews now reports only its own 1 response, not 13; a pure Type-3 "outside
  engagement" (no Type-2 at all) still correctly counts its own speaker responses.

## 2026-07-30 (v2.54 — admin "Just fix the date" for activities)

**Why.** The v2.52 "Merge (any date)" action only ever runs against 2+ activities —
it repoints responses AND re-dates the survivor in one step, so it has no path for
correcting a date on an activity that has nothing to merge into (including its own
survivor right after a merge, if the corrected date typed in at merge time turns
out to be wrong).

- **`activity_admin.set_activity_date`** — new curate op: updates `event_date` on
  one or more Type-2 (F2) instances directly, no merge involved. Same admin gate as
  `merge_activities` (`auth.ROLE_CAPS['merge_activity']`), journaled
  (`fi_event_date`, already supported by `harmonize.undo_batch` since v2.52) and
  audited (`activity_redate`).
- **`app.py`** — `/reports/activities/bulk` gains a `redate` action, admin-only,
  server-side date validation, same as `merge`.
- **`templates/activities.html`** — new "Just fix the date →" button next to
  "Merge into one →" in the "Merge (any date)" group; only needs a date (no title,
  no 2-activity minimum) and confirms before submitting.
- **Tests** — `tests/test_activity_merge_across_dates.py` gains coverage for the
  helper + undo, the admin-only gate, and bad-date rejection.

## 2026-07-30 (v2.52 — admin-only "Merge (any date)" for activities)

**Symptom.** Two Activities-page cards for what was really one event, logged under
two different dates 6 days apart (212 responses vs. 76). The existing "Rename /
merge" action could give them the same title but never combined them into one card,
because `dashboard_insights._event_group_key` groups strictly by the exact
`(event_date, venue, lead_org/organizer)` tuple — a shared label doesn't change the
group key.

**Fix.** `activity_admin.merge_activities` is a new curate op, distinct from
`rename_activities`: it repoints every response from the ticked duplicates onto the
instance with the most responses, deletes the emptied rows (reusing
`harmonize.apply_activity_clusters`), then re-dates the survivor to whatever the
operator typed. Gated behind a new `merge_activity` capability (admin only —
`auth.ROLE_CAPS`); the `/reports/activities/bulk` route rejects the `merge` action
for any other role and validates the corrected date server-side.
`harmonize.undo_batch` gained the `fi_event_date` journal kind so the re-date is
reversible along with the rest of the batch, same as every other curate op here.

- **`templates/activities.html`** — new "Merge (any date)" group on the bulk-edit
  bar, rendered only when `can_merge`. Its submit button runs `confirmMerge()`,
  which reads each ticked checkbox's `data-date` and, if they don't already match,
  shows a `confirm()` naming the specific differing dates before allowing the post.
- **Tests** — `tests/test_activity_merge_across_dates.py`: the helper combines
  responses + re-dates + undoes correctly; the bulk route lets an admin merge across
  dates, rejects a section manager, and rejects a malformed corrected date.
- Superseded an earlier standalone `merge_activities.py` CLI draft of the same idea
  — the logic now lives in `activity_admin.py` and is reachable from the UI instead.

## 2026-07-23 (Fix: a multi-session summit's CSS results 404'd after closing)

**Symptom.** An organizer closed a regional BHW summit (created as several
activities — e.g. a morning plenary and an afternoon workshop — on the SAME day,
at the SAME venue, organized by the SAME unit) and clicked the Manage/Monitor
page's **"View the report"** link, but got a 404 (or, on the resource-person side,
an empty "this activity" report) for every session except one. The CSS results were
never lost — only the link to them was broken.

**Root cause.** `dashboard_insights.build_events` deliberately collapses forms that
share a date + venue + organizer into ONE activity (an event review + its speaker
reviews), keyed on the LOWEST form id in the group (`_event_group_key`). But when
two *distinct* event records share that key — the multi-session case — each
session's report link is still built from THAT session's own min form id
(`storage.event_report_url` / `event_rp_results_url`). For every session but the one
owning the group minimum, that id is a **member** of the merged group, not its
**representative**. The report consumers matched only `e["id"] == event_id`, so the
member-id link found no activity and 404'd. (The per-person engagement report at the
bottom of `_person_report` already matched membership too — the other consumers just
hadn't been brought in line.)

- **`app.py`** — new `_match_event(events, event_id)` helper matches a build_events
  activity by its representative id **or** any of its member form-instance ids, and
  is now used by `dashboard_activity` (the `/reports/activities/{id}` SERVQUAL page)
  and `_event_or_404` (its AI re-analyze / summary / MRR-draft actions). The helper
  keys stay per-event (unchanged, still what `test_event_report_url_follows_the_responses`
  pins) — only the *lookup* is made merge-aware.
- **`app.py`** — `_rp_activity_scope` (the Resource-person report's Activity filter,
  shared with its verbatims drill-down) now resolves a member id to its option before
  falling back to the empty view, so the Type-3 link engages on the merged activity.
- **Tests** — new `tests/test_summit_merged_results.py`: two same-day/venue/organizer
  sessions, close the second, then **follow** its report link end-to-end and assert a
  200 with a rendered scorecard (a URL-string assertion alone never caught the 404),
  plus a unit check of the member-id resolution in `_rp_activity_scope`. Verified the
  HTTP test fails (404) without the fix.

## 2026-07-21 (v2.42 — ship the wellness "By person" section scoping)

Version bump so the deploy's strict-version gate ships #74 (already merged): the
wellness utilization dashboard's **By person** table — plus the section rollup,
week tiles and pending queue — is scoped to the viewing chief's own org-unit
subtree (`_wellness_dashboard_scope` / `_wellness_in_scope` in `storage.py`),
instead of listing every active employee. A section chief sees their section, a
division chief their whole division; admins remain bureau-wide. Code shipped in
#74; this bump adds `APP_VERSION = "2.42"` and the plain-language `version.py`
entry the login "What's new" reads.

## 2026-07-21 (Fix: companion sounds were silent on mobile / Safari)

The opt-in companion sounds (`static/js/avatars.js`) never played for most users —
the wellness hub is a mobile PWA, and on iOS Safari (plus any browser after the tab
is backgrounded or the phone is locked) a `WebAudio` context starts/returns
**suspended**, with a frozen `currentTime`. The old code called `audioCtx.resume()`
without awaiting it and then scheduled every tone against that frozen clock, so the
notes landed in the past and played silently — including the very first sound-toggle
confirmation blip, which is why it read as "sounds don't work."

- **`static/js/avatars.js`**: added `ensureAudioCtx()` — creates the context lazily
  inside the user gesture and unlocks it with a one-sample silent buffer (the source
  node iOS requires to truly start a context). `play()` now emits immediately only
  when the context is already `running`; otherwise it calls `resume()` (in-gesture)
  and schedules the tones on the promise's resolution, when `currentTime` is live
  again. Same blips, same opt-in/off-by-default behavior. Verified against a
  suspended-context simulation of the iOS path.
- **Spontaneous species voices** (`static/js/avatars.js`): companions now vocalize on
  their own from the idle loop — soft, quiet, species-specific motifs (dog woof, cat
  meow, bird tweet, owl hoot, dolphin eee, fish blub, plant rustle, …), throttled to
  roughly one every 15–30 s per companion and paired with a visible idle behavior.
  Gated behind the same opt-in sound toggle and the sleep / reduced-motion / hidden-tab
  rules, and — because autoplay policy forbids a timer from starting audio — only ever
  played through a context a user gesture has already unlocked (so the first
  spontaneous sound follows the first interaction of the session; turning sound on
  counts). Never forces or resumes a context on its own.
- **`templates/_avatars.html`**: bump the `avatars.js` asset token to `v=20260722c`
  so returning devices fetch the updated file.

## 2026-07-21 (v2.40 — Hotfix: ship wellness_register.py; guard the deploy against unshipped boot imports)

**Production hotfix.** The live Space was crashing on boot with
`ModuleNotFoundError: No module named 'wellness_register'`. Root cause: v2.39 (#75)
added `wellness_register.py` and an `import wellness_register` in `app.py`, but the
new module was never added to `deploy_hf.py`'s `RUNTIME_PY` allowlist — the deploy
ships an explicit file list, so the module never reached the Space while the import
that needs it did. Every boot then died before serving, which in turn 503'd the
pre-deploy backup gate and deadlocked further deploys.

- **`deploy_hf.py`**: add `wellness_register.py` to `RUNTIME_PY` (the fix), and add
  `_unshipped_local_imports(allow)` — parses every shipped `.py`'s TOP-LEVEL imports
  and hard-aborts the deploy if any resolve to a repo-local module that isn't itself
  shipped. This turns exactly this failure mode (a boot-time import with no shipped
  module) into a loud pre-upload abort instead of a silent live crash. Verified: it
  flags `wellness_register` against the pre-fix allowlist and is clean against the
  fixed one.
- **`version.py`**: `APP_VERSION` → `2.40` with a user-facing changelog entry (this
  deploy is also the first to actually ship the Annex A Excel register live, since
  both 2.39 deploys aborted at the backup gate).

## 2026-07-21 (Wellness register download → official "Annex A. Weekly Wellness Break Log" (Excel), consumed breaks only)

The utilization dashboard's **"Download the register"** now produces the DM's
official **Annex A. Weekly Wellness Break Log** as an Excel workbook instead of
the ad-hoc CSV, and lists **only breaks actually consumed (completed)** —
pending/approved/denied/cancelled claims are left off, since they were never
availed.

- **`/wellness/export.xlsx`** replaces `/wellness/export.csv` (`app.py`). New
  `_build_wellness_register_xlsx` renders the exact seven-column form — No., Name
  of Personnel, Wellness Break Availed (Date/Time), Activity Type, Duration
  (Minutes), Usefulness Rating (1-5), Remarks/Observations — under the
  "Annex A. Weekly Wellness Break Log" masthead (Office/Unit + auto "Weekly
  Covered" span) and the form's footnote. Duration is `hours × 60`; the takeaway
  reflection fills Remarks. Helpers `_fmt_reg_date` / `_wellness_period_label`.
- **Annex A activity mapping** (`storage.py`): `WELLNESS_ANNEX_ACTIVITY` maps our
  keys to the form's six official categories (Physical Exercise, Relaxation,
  Wellness Consult, Recreation, Arts, Others); `WELLNESS_OFFICE_UNIT` carries the
  bureau's full name. `wellness_export_rows` now also returns `activity_key`,
  `activity_annex`, and the `remarks` takeaway.
- **Dashboard download control** (`templates/wellness_dashboard.html`) points at
  the new route and adds a **From/To date-range filter** (a small GET form) so the
  register can be scoped to any span. It defaults to the currently-viewed week —
  matching the Annex A weekly form and tracking the week nav — and clearing both
  fields exports the full register. The `date_from`/`date_to` query params were
  already honored by `wellness_export_rows`; the endpoint drives the exported
  "Weekly Covered" masthead from whichever bounds are supplied.
- Tests updated (`tests/test_wellness.py`): the register export test loads the
  workbook, asserts the Annex A masthead/columns and the mapped row, and confirms
  a still-pending break never reaches the register.

## 2026-07-21 (v2.39 — Wellness: downloadable monthly break register (PDF) per person)

Each employee can now download their own **monthly wellness-break register** as a
print-ready PDF from their wellness page — the record of the breaks they availed
that month, laid out like the DOH monitoring form (Name / Office header + a
Monday–Friday grid, one two-row "Approved By" block per week). Because approval
already happened inside the system, the signature area is filled with **"Digitally
approved and signed"** (over the deciding approver's name) instead of a blank line.

- **New `wellness_register.py`**: `render_month_pdf(data)` builds the form-faithful
  grid with reportlab (weekday cells SPAN their week's "Approved By" line, exactly
  like the paper form); days outside the month are shaded, completed breaks marked ✓.
  `filename()` / `month_title()` helpers. Issued as PDF only (never editable), matching
  `certificate.py`'s pattern.
- **Storage** (`storage.py`): `wellness_availed_months()` lists the months a person has
  an availed (approved/completed) break, newest first, with counts — drives the picker;
  `wellness_person_month()` returns that month's breaks plus the person's name/office and
  each break's deciding approver. Denied/cancelled/pending are excluded (not breaks taken).
- **Route** (`app.py`): `GET /wellness/register.pdf?month=YYYY-MM` — self-service (every
  employee downloads their OWN register, no chief/admin gate), defaults to the current
  month, redirects back to the hub with a message when nothing was availed, and audits the
  download.
- **Hub** (`templates/wellness_hub.html`): a "Monthly register (PDF)" panel with a month
  dropdown + download button, shown only once the person has availed a break.
- Tests: new coverage in `tests/test_wellness.py` for the two storage helpers, the PDF
  bytes/filename, the HTTP download + empty-month redirect, and self-service access.

## 2026-07-21 (v2.38 — Lifelike companions: watering fix, roaming, page-wide swim, personality)

The companion layer grows from "animated sticker" into something that feels a
little alive. Also fixes the long-standing invisible-watering bug.

- **Fix: watering was invisible.** `_avatars.html` hid the `.av-drops` GROUP
  (`opacity:0`) while the care animation animated only its `path` children — a
  child can never out-opacity an `opacity:0` parent, so no plant ever showed
  falling droplets. The hide now targets `.av-drops path` (the `av-drop`
  keyframes own the visibility window, same pattern as `.av-spark`). Also the
  succulent's `animation:none` kill rule (specificity 3) outranked the watering
  perk (2), so it showed nothing when watered — a specificity-4 exception now
  gives it a species-true `av-plump` response.
- **Ground roaming** (`avatars.js` `WALKERS`/`startWalk`): dog, cat, rabbit,
  bird and turtle wander their `.av-play` panel autonomously — travel on the
  `.avmove` layer only (drag owns the wrap transform), live-recomputed bounds,
  species gaits (`av-do-trot/zoom/bound/plod`, deliberately not in `ALL_DO`),
  dog zoomies, rabbit hop chains. The idle loop yields while a leg is underway
  (`_avBusy`), and a drag resets the roam offset so grab and art agree.
- **Page-wide swim** (wellness hub only): a 🌊 toggle on fish/dolphin lifts the
  REAL svg into a `position:fixed` `pointer-events:none` overlay (z-index 14 —
  under the sticky chrome) inside a class-carrying holder (`avwrap fam-animal`
  + data attrs, since every descendant selector dies when the art leaves its
  wrap); it swims viewport waypoints, the dolphin leaps, tap-or-toggle sends it
  home. Preference in localStorage `css-av-explore`; hard-restored on
  reduced-motion, sleep, or care.
- **Personality**: tap bubble now speaks — time-of-day greeting personalized
  via new `data-person`, care memory ("I missed you…", thanks after care) via
  `data-last-care`, streak lines via `data-care-streak` (all new optional
  `avatar()` macro args; wellness route passes them; `get_user_profile` now
  returns `avatar_care_streak`). Dog/cat/bird join the owl in pointer-watching
  (subtler ±8°), a fast pointer near the dog triggers an excited wag, and
  press-and-hold pets the companion (hearts, `av-nuzzle` wiggle, opt-in purr).
- **Tests**: CSS-contract assertions for the watering fix and new keyframes,
  macro personality attrs, swimmer-only explore button, hub markers, profile
  care-streak field. APP_VERSION → 2.37.

## 2026-07-21 (v2.37 — Dolphin companion + swimmer water-drift fix)

A 16th wellness companion and a fix for a long-standing swimmer glitch.

- **New species: dolphin** (`storage.AVATAR_CATALOG`, `_avatars_art.html`
  `_dolphin`, `avatars.js`). An `animal`-family companion (so it is *fed*) that
  **swims** — it shares the fish's figure-eight roam and adds an `av-do-hop`
  leap to its idle repertoire, blinks, flicks its tail fluke, and blows
  bubbles. Fully data-driven: it flows through the `/me` picker, `valid_avatar_kind`
  validation, and the care endpoint with no per-route changes. New gradients
  `avg-dolphin` / `avg-dolphin2`.
- **Fix: swimmer water no longer drifts.** The fish's "home water" backdrop was
  drawn *inside* the roaming `.avmove` group, so it slid across the SVG as the
  fish swam — contradicting its own "stays put" comment. `avatar_svg` now draws
  the water once, **behind and outside** the moving layer, gated by a new
  `storage.avatar_is_swimmer(kind)` helper (also a Jinja global) so the template
  and `avatars.js` can never disagree on who swims. Applies to the fish and the
  new dolphin.
- **Tests** (`test_avatar_care.py`, `test_onboarding_storage.py`): catalog is
  now 16 species; new checks that the dolphin is a fed swimmer and that the
  water backdrop renders once, static, and behind the moving layer (and never
  for non-swimmers). Existing per-species × stage/month render sweeps cover the
  dolphin automatically.

## 2026-07-21 (Wellness monitoring: the "By person" table shows only the viewer's own section)

The utilization dashboard (`/wellness/dashboard`) listed **every** active employee
in the bureau, so a section chief opening the page saw all sections in the "By
person" card, not just the people they're concerned with. Now the whole
per-viewer view is scoped to the chief's own unit — mirroring who they actually
approve for (`list_wellness_approvals`).

- **`wellness_dashboard_data(conn, week_start, user=None)`** (`storage.py`) gains
  the viewer. New helpers `_wellness_dashboard_scope` (the viewer's
  `org_unit.path`, or `None` for admins / accounts with no directory unit) and
  `_wellness_in_scope` (a path is that unit or a descendant). A directory-linked
  chief sees only their subtree: a **section chief** their section, a **division
  chief** their whole division; **admins** and any unscoped call still see the
  whole bureau. The By-person rows, the "By section" rollup, the week tiles and
  the pending queue are all filtered together, so the page stays coherent.
- The route (`app.py`) passes the request's `user` through; the `user=None`
  default keeps existing callers/tests bureau-wide.
- Tests: `tests/test_wellness_escalation.py` adds section-chief, division-chief
  and admin scoping cases on the existing two-section chain fixture.

## 2026-07-21 (v2.36 — Wellness request UX: named approver, "Others" specify, 4-week window, richer post-activity report)

Four changes to the DOH DM 2025-0135 wellness-break flow (`storage.py`, `app.py`,
`templates/wellness_apply.html`, `templates/wellness_reflect.html`), plus the
version bump that ships the prior undeployed main commit (grounded-answer
confidence tuning, #69) alongside it.

- **Named approver** (`wellness_approver_name` / `_wellness_seat_name`, `storage.py`):
  resolves the actual seat-holder's name up the same rank/org-path chain
  `wellness_approver_title` walks. The apply page shows "Send for approval of
  &lt;name&gt;", falling back to the role title when the seat is unfilled. Wired
  through `_wellness_apply_page` and the submit cheer.
- **"Others" requires a specification**: new nullable `wellness_claim.activity_other`
  column (guarded additive migration in `_add_missing_columns`). `create_wellness_claim`
  requires it when `activity == "other"` and clears it otherwise; `get_wellness_claim`
  and the CSV export fold it into the activity label ("Others — gardening"). The form
  reveals + requires the field only when "Others" is picked.
- **Rolling 4-week request window**: `WELLNESS_WINDOW_WEEKS = 4`,
  `wellness_window_last_date()` / `wellness_window_weeks()`. `create_wellness_claim`
  rejects dates past the window (server-side source of truth); the apply page gets a
  date `max`, a per-week `hours_used` map, and a small script so the "hours left" note
  and the 2-hour option track the selected date's week. The 2h/week cap is unchanged
  and still keyed per week.
- **Richer post-break check-in** (Key fields from the DOH Post-Activity Report):
  new nullable `wellness_reflection` columns `usefulness` (1–5), `felt_refreshed`,
  `managed_stress`, `focus_impact`, `suggestions`. `complete_wellness_claim` takes them
  as optional keyword args (older callers/tests unaffected) with range validation; the
  reflect template adds the fields; the register CSV export gains a Usefulness column.
- Tests: new coverage in `tests/test_wellness.py` for all four; escalation suite unaffected.

## 2026-07-21 (v2.35 — "Maximize AI": grounded free-form answers over your own data)

The assistant's Q&A (`nl_answer`) was classify-only: the model picked one of a
short, fixed list of stat slots and the server rendered a templated sentence —
it never composed prose and never saw the numbers. Two changes lift that
ceiling while keeping every existing guardrail (opt-in, budget-capped, graceful
fallback, no PII, no SQL from the model).

- **Expanded canned catalog** (`AI_ANSWER_SLOTS`, `app.py`): added year-to-date
  and all-time slots for satisfaction / activities / people-rated, all rendered
  from figures `home_stats` already computes. Pure additions — the classify-only
  "catalog" engine is unchanged and remains the default.
- **New "maximize" engine** (`nl_answer_grounded`): when an admin switches the
  answer engine to *Maximize AI*, a router `kind=answer` triggers a second,
  separately-capped model call. The server assembles a compact, PII-free **data
  pack** — org-wide totals (`home_stats`), per-activity response counts +
  satisfaction, and (opt-in only) per-resource-person scores — and the model
  composes an answer **strictly** from it, instructed to say it doesn't have the
  data otherwise. The user's text is data, never instructions; the model writes
  no SQL and sees no row-level data.
- **Graceful fallback preserved**: any failure of the grounded call (`AIError`,
  `grounded=false`, low confidence, client timeout) falls through to the canned
  slot render / keyword palette — the assistant never errors and never invents a
  number. The grounded call logs its own `nl_answer_grounded` row for `/admin/ai`.
- **Admin toggle** (`admin_ai.html`, `/admin/ai/settings`): *Answer engine*
  (Canned catalog / Maximize AI) plus an *Include resource-person ratings*
  opt-in (default off — resource-person names are personal data, same stance as
  `harmonize`). New settings `ai_answer_engine`, `ai_answer_people`.
- **`start.js`/`start.html`**: the NL landing page reports the engine so maximize
  mode allows a longer client timeout (two model calls) before degrading to the
  keyword palette; every other mode keeps the snappy 9s budget.
- **`ai_core.py`**: registered `nl_answer_grounded` (its own daily cap, default 40).
- **Seeded FAQ rules** (`SEED_LEARNED_RULES`, `app.py`): enriched the
  deterministic FAQ layer that answers *ahead* of the model — added rules for
  the new YTD/all-time slots and for common phrasings/synonyms (trainings /
  events / sessions, staff / speakers / resource persons, "how are we doing").
  On a fresh install these deflect the most frequent data questions with **zero
  AI budget** (and keep answering when AI is off). Kept focused per phrasing on
  purpose: `qa_rules.score()` penalises keyword-stuffed rules, so coverage comes
  from more tight rules, not fatter ones.
- **`tests/test_ai_answers_grounded.py`** (new): grounded happy path; every
  fallback mode; the engine is genuinely gated by both the toggle and the
  feature flag; and the data pack withholds resource-person names unless opted
  in and never leaks an email. **`tests/test_ai_learned_rules.py`**: the seeded
  answer rules all point at real slots, and ten common paraphrases resolve to
  the right stat with no model call.

## 2026-07-21 (v2.34 — Edit verbatim comments on the activity report, for encoding)

Addresses live Spot Feedback #70 ("i wanted to edit manually the people's own
words, for encoding only") — filed on `/reports/activities/…#comments`.

The audited edit route (`POST /responses/{id}/edit-remark`, `edit_data` only,
before/after logged) already existed and was exposed on `/reports/verbatims`, but
NOT on the per-activity report — whose `#comments` section renders only the
curated digest (`_story.html`, at most 4 themes × 2 quotes per side, re-tag only).
So a user reading one activity's comments had no way to fix the words there.

- **New `storage.activity_editable_comments(conn, response_ids)`**: a flat,
  newest-first list of every respondent-written comment across a set of responses
  (each overall remark + each free-text item note), shaped one-entry-per-edit-box.
  `item_id` is `''` for the overall comment (the blank-item_id contract the edit
  route already uses to update `response.remarks`). Encoding metadata items
  (`SEX`/`AFFIL`/`RESPONSE_NO`) are excluded — they aren't anyone's words.
- **Activity report** (`app.py`, `templates/activity.html`): the `#comments`
  section gains an "✎ Edit the words (for encoding)" panel, shown only to
  `edit_data` holders (section heads + admins). Unlike the digest above it, this
  lists the COMPLETE set, so any comment is reachable; each box posts to the
  existing edit-remark route with `back` returning to `#comments`.
- Tests (`tests/test_activity_editable_comments.py`): storage-level coverage of
  inclusion/exclusion, the blank-item_id contract, and an edit round-trip; plus
  HTTP tests that the panel shows for a manager and is hidden from a viewer.

## 2026-07-21 (v2.33 — Wellness approver routing names the real chief, not "an administrator")

Addresses live Spot Feedback #76 ("if staff → send to section chief, if section
chief → division chief, if division chief → director"). The escalation chain
already existed, but resolved to nobody against real directory data, so the apply
page read "Send to an administrator" for people who clearly sit under a chief.

Two root causes, both in `storage.py`:

- **The Director was invisible to the chain.** Section heads and division chiefs
  carry a functional `designation` ("Section Head" / "Division Chief"), but the
  Director's leadership lives in `position` ("Director IV") with a blank
  `designation`. Rank was read from `designation` only, via an exact-match lookup,
  so a division chief escalated to nobody. `_wellness_rank` now takes
  `(designation, position)` and matches case-insensitively as a substring — reading
  `position` too, but only for "director" (a section head's position is often
  "Chief Health Program Officer", which must not read as a division chief).
  `_wellness_accounts_by_designation` → `_wellness_accounts_at_rank`, and
  `user_is_wellness_chief` now uses the same rank logic, so the Director both
  approves a division chief's break and sees the queue.
- **The copy hid the chain until everyone was onboarded.** `wellness_approver_title`
  returned "an administrator" whenever the approver had no app account yet — which
  was almost always, since only one chief has signed in. It now names the
  org-correct approver as long as that seat is *filled in the directory* (new
  `_wellness_role_filled`), independent of whether that person has logged in. The
  actual claim still routes to the admin fallback until the chief is onboarded, so
  nothing gets stuck; the copy just tells staff who the request is *for*.

- Tests (`tests/test_wellness.py`): new `wellness_chain` fixture plus
  `test_escalation_walks_each_tier` (Director matched by position),
  `test_director_and_chiefs_see_the_queue`, and
  `test_title_names_the_seat_even_without_an_account`.

## 2026-07-21 (v2.32 — fix: Gemini "thinking" starved structured-output calls)

Symptom: after switching the default model to `gemini-3.5-flash`, every
schema-constrained AI call fell back with `AIBadResponse("model output did not
match the response schema")` (or an empty response), while the same calls had
worked on Groq's Llama. "Test connection" still passed because it sends no
`response_schema` and never checks that any text came back.

Cause: Gemini 2.5+/3.x enable "thinking" by default, and on Gemini 3 those
thinking tokens are drawn from the SAME `maxOutputTokens` budget as the visible
answer. Our structured calls set deliberately small limits sized for a compact
JSON reply (the NL router uses 256), so default ("high") thinking starved the
JSON and it came back truncated → `json.loads` failed. Groq's Llama has no
thinking, which is why it was fine.

- **`ai_core.py`** — new `_thinking_config(model)`: pins thinking to its floor
  per model family (`thinkingLevel: minimal|low` for `gemini-3*`, the two
  mutually exclusive with `thinkingBudget: 0` for `gemini-2.x`). `_http_generate`
  now sends `thinkingConfig`, and on the Gemini-3 path widens `maxOutputTokens`
  by `THINKING_HEADROOM_TOKENS` (1024) so the caller's intended answer size is
  preserved with room for the (now minimal) reasoning. Groq path unchanged.
- **`tests/test_ai_core.py`** — cover the per-family config and that a Gemini-3
  call pins thinking + widens the budget while a Gemini-2.5 call disables
  thinking without widening it.

## 2026-07-21 (v2.31 — Wellness break can be claimed 2 hours in one sitting)

The DM's 2-hour weekly entitlement can now be taken as a single 2-hour break,
not only two separate 1-hour claims.

- **`create_wellness_claim`** (`storage.py`): new `hours` parameter (default 1,
  so existing callers/tests are unaffected). Validated to `1..WELLNESS_WEEKLY_HOURS`;
  the weekly-entitlement guard now checks `used + hours` and returns a precise
  "Only N hour(s) left" message when a 2-hour claim won't fit the remaining
  balance. The INSERT stores the chosen `hours` instead of a hard-coded `1`.
- **Apply form** (`templates/wellness_apply.html`, `app.py`): new "Break length"
  radio (1 hour / 2 hours); the 2-hour option is disabled when fewer than 2 hours
  remain that week. The route forwards `p.get("hours")` to `create_wellness_claim`.
- **Hub** (`templates/wellness_hub.html`): break-requests table gains a "Length"
  column showing each claim's hours; length-specific copy ("1-hour break") made
  length-agnostic.
- Tests (`tests/test_wellness.py`): new `test_two_hour_break_in_one_claim`,
  `test_two_hour_claim_rejected_when_only_one_hour_left`, `test_break_length_bounds`.

## 2026-07-21 (v2.30 — Wellness breaks need a 30-minute lead time)

Addresses live Spot Feedback #73 ("minimum time … to request before said time
of wellness break").

- **Minimum lead time** (`storage.py`): new `WELLNESS_MIN_LEAD_MINUTES = 30`
  constant; `create_wellness_claim` now combines `break_date` + `start_time` into
  a local datetime and rejects anything earlier than `tz.now_local() + 30 min`, so
  the approving chief has a real window to act. This also closes a latent gap —
  the prior guard compared the **date only** (`d < today_local()`), which accepted
  a same-day request for a start time that had already passed.
- **Apply form** (`templates/wellness_apply.html`, `app.py`): the start-time field's
  help text now states the rule, driven by the constant (`min_lead`) so the copy
  stays in sync with what's enforced.
- Tests (`tests/test_wellness.py`): new `test_break_needs_minimum_lead_time` (clock
  pinned via `monkeypatch` for determinism); existing claim tests moved to a future
  weekday (`_future_weekday`) so their fixed clock times don't read as "in the past"
  when the suite runs late in the day.

## 2026-07-21 (v2.29 — Companion sleep cycle, care-streak badge, monthly accessories, opt-in sound)

Follow-up round on the v2.28 companion release:

- **Sleep cycle** (`static/js/avatars.js`, `templates/_avatars.html`): companions doze
  9 pm–6 am on the viewer's device clock — lids close (`.av-asleep .av-lid`), a Zzz group
  floats, the idle/roaming engines pause. A tap or care action wakes them for ~45 s.
  The bat is exempt (nocturnal — night is its active time).
- **"Devoted caretaker" badge** (`storage.py`): new `admin_user.avatar_care_streak`
  column counts consecutive care days (same-day keeps, next-day +1, gap resets);
  7 in a row awards `avatar_care_7` once through the existing `wellness_badge` table
  via a shared `_award_badge` helper (`INSERT OR IGNORE` idempotency, also reused by
  `wellness_award_badges`). `/avatar/care` returns `streak` + fresh `badge` label; the
  client floats a toast, the hub badge row shows it permanently. No points.
- **Monthly accessories** (`templates/_avatars_art.html`): `_accessory(m)` draws 12
  head-worn designs anchored inside each species' `.av-head` (so they ride tilts and
  chews); headless potted plants get a month-tinted `_pot_bow` on the rim. The month
  resolves per render via the new `avatar_month` Jinja global (`avatar_accessory_month`).
- **Opt-in sound** (`static/js/avatars.js`): WebAudio-synthesized blips (tap chirp,
  water plips, feed noms, badge arpeggio) behind a 🔇/🔊 toggle next to the care
  button — off by default, remembered in `localStorage`, context created lazily on a
  user gesture. No audio assets, offline-safe.
- Tests: streak/badge/accessory/zzz/sound coverage in `tests/test_avatar_care.py`;
  SW cache `v2.19-b`.

## 2026-07-21 (v2.28 — Companion glow-up: 15 species, personality engine, care play)

The avatar companion system, rebuilt (PR #61):

- **Art** (`templates/_avatars_art.html`, new): all 15 species as detailed inline SVG —
  shared `avg-*` gradients emitted once by `avatar_defs()`, expressive lidded eyes,
  named part groups (`.av-head`/`.av-tail`/`.av-ear-l/r`/`.av-wing-l/r`/…) — behind a
  public `species_art()` dispatcher. Nine new species: sunflower, fern, mushroom,
  succulent / dog, rabbit, fish, owl, bat (catalog rows in `storage.AVATAR_CATALOG`).
- **Personality engine** (`static/js/avatars.js`, new): per-species random idle
  behaviors (CSS keyframes toggled by `av-do-*` classes); the bat flies and the fish
  swims a figure-eight on a new `.avmove` layer; the owl's facial disc follows the
  pointer. All motion gated on `prefers-reduced-motion` and page visibility.
- **Care = cosmetic mood** (`storage.py`, `app.py`): `admin_user.avatar_last_care_at` +
  `POST /avatar/care` (6 h counting cooldown, `care` ratelimit bucket); mood
  happy/okay/droopy derived on read, drives styling only — growth stays strictly
  wellness-points-derived. Water/feed buttons with droplet/treat animations; the hub
  mascot is draggable inside its hero panel (`.av-play`, localStorage position).
- `avatar_family`/`avatar_care_verb` Jinja globals replace the hardcoded species
  tuple in the `avatar()` macro; pickers show all 15 species with blurbs.

## 2026-07-21 (v2.27 — Wellness activity-card fix + duplicate landing cards removed)

Two small follow-ups to v2.26, bundled into one version bump:

- **Wellness apply form** (`templates/wellness_apply.html`, `templates/_wellness_icons.html`,
  `storage.py`): the activity picker's icon/label `<span>`s defaulted to `display:inline`, so
  the 64px icon sizing was ignored and labels spilled past the card border into the note field
  below. Now laid out as a flex column so the icon and label stay inside the card. Also added an
  "Others" activity option (with its own icon) for requests that don't fit the four presets.
- **`/css` hub** (`templates/home.html`): removed the duplicate "CSS — surveys & reports" /
  "Wellness — my 2-hour break" door cards, which repeated the same two cards already shown on
  the `/` chooser landing page.

## 2026-07-21 (v2.26 — Staff onboarding, avatar companion & two-card landing)

Post-login rework in six self-contained phases (see
`docs/STAFF_ONBOARDING_AVATAR_PLAN.md`). No role/capability changes; every deep
link keeps working.

What it does:

- **One-time onboarding** (`/welcome`): first sign-in after this update (detected
  by a new `admin_user.onboarded_at` column, NULL = not yet) walks the user
  through an optional profile-photo upload (into their existing directory record
  via `set_rp_photo`, so it shows on their people page) and adopting a **named
  companion**. The login flow routes first-timers here *after* any temp-password
  reset and *ahead of* the `/start` AI-landing opt-in, carrying `?next=` through;
  a soft guard on `/` stops it being skipped by URL (deep links stay reachable).
- **Avatar catalog** (`templates/_avatars.html`): inline-SVG art, 6 species
  across a plant and an animal family × 6 growth stages, no external assets
  (PWA/offline-safe). Plants sway, animals breathe, a tap bounces + sparkles,
  hover shows the pet name; all motion honours `prefers-reduced-motion`. Two new
  columns carry the choice: `admin_user.avatar_kind` / `avatar_name`.
- **Two-card landing** (`/`): a calm chooser — greeting, photo, the companion,
  and **Wellness** and **CSS** doors. The classic role-filtered hub moved verbatim
  to `/css`; nav/search/help/router links swept accordingly.
- **Viewer routing**: `_css_entry_for` sends a plain viewer linked to a visible
  directory person to their own `/dashboard/people/<id>` first; a "This is your
  profile" banner there links to their section (`/dashboard/teams/<path>`).
  Fallbacks for hidden/unlinked people and non-viewer roles.
- **Unified mascot + editor**: the wellness hub renders the *adopted* companion
  (species from the profile, growth stage still derived from wellness points,
  default plant when unchosen) instead of a hard-coded plant. A new **`/me`** page
  re-picks or renames anytime.
- **Wellness refinements**: the apply form's activity picker is now illustrated
  inline-SVG cards (`templates/_wellness_icons.html`) behind the same radio
  inputs — POST contract unchanged. Approvals escalate by directory rank
  (`get_wellness_approvers` rewrite): staff → section chief → division chief →
  Director → admin fallback, resolved through `org_unit.path`, with rank-aware
  copy on the apply form.

Schema: three guarded `ALTER TABLE admin_user` columns (`avatar_kind`,
`avatar_name`, `onboarded_at`) added by `init_db` — existing databases migrate on
first boot; every existing account sees the one-time onboarding on next sign-in.

Tests: six new files (storage, onboarding flow, landing fork, viewer routing,
profile edit, escalation) plus updates to existing wellness/tour/hub tests —
full suite 955 passed.

## 2026-07-20 (v2.25 — Wellness module: gamified 2-hour weekly wellness break, DM 2025-0135)

New module alongside the CSS: after login the home page offers two doors —
**CSS (surveys & reports)** and **Wellness (my 2-hour break)** — plus a
"Wellness" nav group visible to every signed-in role.

What it does:

- **Break requests** (`/wellness/apply`): 1-hour slots against the DM's
  2-hour weekly entitlement. `storage.create_wellness_claim` enforces the cap
  (pending+approved+completed hours per Mon–Sun week, keyed on a `week_start`
  column), rejects backdated/weekend/duplicate slots, and only offers the
  DM's allowed activity categories.
- **Section-chief approval** (`/wellness/approvals`): the approver is resolved
  through the directory (`admin_user.rp_id → resource_person.org_unit_id`,
  designation in {Section Head, Section Chief, Division Chief}) — not a role.
  Admins are the fallback for unlinked accounts and for chiefs' own requests;
  nobody decides their own claim. Decisions, filings, cancellations and
  completions are all audited.
- **Post-break check-in** (`/wellness/claims/{id}/complete`): mood before/after
  (1–5), what they did, one takeaway → marks the claim completed and stores a
  `wellness_reflection` row.
- **Gamification**: points/level/streak are DERIVED from claim+reflection rows
  (only badge awards persist in `wellness_badge`), so the fun layer can't
  drift from the record. A six-stage inline-SVG companion plant grows with the
  level on the hub (`/wellness`).
- **Monitoring** (`/wellness/dashboard`, chiefs/admins): weekly utilization by
  section and person, pending-queue aging, reflection completion — plus the
  register export (`/wellness/export.csv`) for the Administrative Service's
  monitoring database.

Schema: three new tables (`wellness_claim`, `wellness_reflection`,
`wellness_badge`) created idempotently in `init_db`. New templates
`wellness_*.html`; new tests `tests/test_wellness.py` (13 tests: entitlement,
approver routing, flow + points, in-handler RBAC, export).

Note for rollout: accounts not linked to a directory person (`rp_id` NULL)
show "—" as their section and their requests route to admins — linking
accounts in Admin → Users makes the chief routing work.

## 2026-07-20 (v2.24 — duplicate-activity heads-up now matches across creators, not just same-login/6h)

Spot-feedback report: a real duplicate ("DOH UHC Fund for Zero Balance Billing
in LGU Hospital: POLICY ORIENTATION MEETING") was created and the /create
screen's "you already made this" warning (spot-feedback #67) never fired.

Root cause: `storage.find_recent_duplicate_event` only matched a duplicate
made by the **same** `created_by` login, created within the last **6 hours**.
That's the pattern the original spot-feedback #67 report described (one
manager accidentally double-submitting), but it misses the more common
real-world case — two different staff members independently logging the same
activity, or the same activity re-entered a day or more later. Since the check
is purely advisory (`POST /create` never calls it, and there's no DB unique
constraint), any duplicate outside that narrow window was silently allowed
through with no warning at all.

Fix: `find_recent_duplicate_event(conn, title, event_date)` now matches on
title (case/space-insensitive) + event date alone — no `created_by` filter,
no time cutoff. `GET /create/check-duplicate` updated to match (drops the
now-unused `request` param); `templates/form_create.html` copy updated from
"You already created…" to "…already exists on this date" since the earlier
activity may not be the current user's own. Still purely advisory — `/create`
itself is unchanged, so a genuine second activity that happens to share a name
still saves normally.

Verified: `tests/test_create_duplicate_warning.py` updated — added a
same-title/different-creator case (created by `admin`, found with no creator
argument at all) and a same-title/backdated-creation case (created_at forced
to year 2000, still found) in place of the old "ignores a different creator" /
"ignores outside the lookback window" tests; added an HTTP-level test where
one role creates the activity and a different role's `/create/check-duplicate`
call still reports it. `tests/test_create_duplicate_warning.py` 10/10 pass.

## 2026-07-19 (v2.23 — deploy manifest was missing `qa_rules.py` → app crashed on startup)

`ai_core.py` imports `qa_rules` at module load (the FAQ/learned-rules layer
added in v2.22), but `qa_rules.py` was never added to `deploy_hf.py`'s
`RUNTIME_PY` upload list. So the file exists in the repo and passes every local
test, yet the deployed HF Space never received it — and on start-up
`import ai_core as ai` (app.py) → `import qa_rules` (ai_core.py) raises
`ModuleNotFoundError: No module named 'qa_rules'`, which aborts the whole
uvicorn boot and takes the site down with a server error for everyone.

Fix: add `"qa_rules.py"` to `RUNTIME_PY` in `deploy_hf.py` so it ships with
every deploy. `qa_rules` only depends on the stdlib (`re`), so no further
modules were missing.

## 2026-07-19 (v2.19 — AI calls no longer block the event loop → stop the recurring edge 500)

Root-causes the recurring "error 500" that v2.18 shielded but never explained.
v2.18 correctly observed the signature — `awselb/2.0` `503` and HF proxy `500`
pages with **no** `X-CSS-App`/proxy headers, while the app replica looked
healthy — and shipped a client-side service-worker retry. But the trigger is
**in the app**, not (only) HF's edge: the AI-calling handlers are `async def`,
yet `ai.ask()` → `_http_generate()` makes a **synchronous** `httpx.post`
(connect 3s + total 8s + one retry ≈ up to ~16s). A blocking call on the event
loop of the single uvicorn worker freezes uvicorn's own connection-accept loop,
so for that window the replica accepts **no** new TCP connections and the
fronting ELB/HF proxy answers every other in-flight request with an edge 5xx —
exactly the observed 500/503. The hottest trigger is the landing-bar router
(`POST /api/ai/route`, feature `nl_router`), confirmed firing on the live Space,
so ordinary AI use intermittently 500s everyone else. This is why the v2.18
retry reduced but never removed it, and why every prior in-app `AIError` fix
couldn't: the 500 is emitted **outside** the app.

Fix: move the blocking AI network call **off** the event loop.

- **`ai_core.py`** — new `ask_async()` / `test_connection_async()` /
  `test_groq_connection_async()` run the existing (synchronous) `ask()` /
  `test_connection()` / `test_groq_connection()` in a worker thread via
  `asyncio.to_thread`, so a slow or stuck AI reply can no longer freeze the
  worker. sqlite connections are thread-bound, so the wrapper opens its **own**
  short-lived connection inside the thread (from the caller connection's DB
  path via `PRAGMA database_list`); the returned `interaction_id` is a plain int
  the caller keeps using on its own connection (the row is already committed).
  Same contract as before — returns `(result, interaction_id)` or raises
  `AIError` — so callers' `except ai.AIError` fallbacks are unchanged. An
  in-memory DB (tests only) has no reopenable path and falls back to a direct
  in-thread call.
- **`app.py`** — the 9 `ai.ask(...)` call sites (all in `async def` handlers:
  `/api/ai/route`, `/admin/feedback/{fid}/ai-suggest`,
  `/admin/ux-insights/analyze`, `/directory/cleanup/ai-suggest`,
  `/activities/{token}/messages/ai-draft`, `/reports/csm-draft`,
  `/reports/activities/{id}/ai-reanalyze`, `/ai-summary`, `/ai-mrr-draft`) now
  `await ai.ask_async(...)`; the two `/admin/ai` test buttons `await` the async
  test wrappers. No behavioural change beyond not blocking the loop.
- **`tests/test_ai_core.py`** — `ask_async` offloads to a non-main thread, logs
  `ok` on a row visible to the caller connection, propagates `AIError`, and
  raises `AIUnavailable` when unconfigured.

Same event-loop-stall class, second source: PBKDF2 sign-in hashing.

- **`auth.py`** — `hash_password_async` / `verify_password_async` run the
  deliberately-CPU-heavy PBKDF2 (`_ITERATIONS=200_000`, ~100-150ms/call) off the
  event loop via `asyncio.to_thread`. In-line, it froze the single worker for the
  whole hash — and bots hammer `/login` constantly, so each attempt was a stall
  that could flap the load-balancer health check.
- **`app.py`** — the four `async def` auth handlers (`login_submit`,
  `set_password_submit`, `reset_password_submit`, `admin_users_reset_default`)
  now `await` the off-loop hash. (`_provision_account`, reached only from the
  rare admin-invite path, is left synchronous.)
- **`tests/test_auth_async.py`** — parity of the async wrappers with the sync
  hash/verify, and that the hash runs on a worker thread, not the event loop.

Note on the underlying failure surface (from live diagnosis of the Space): the
recurring "500" is emitted by the HF edge / AWS ELB, not the app — the single
`cpu-basic` worker intermittently fails the load-balancer health check when its
event loop stalls, and the LB then answers everyone with an edge 5xx until the
target re-registers. The app is healthy and serves 200 whenever a request
reaches it. These changes remove the two biggest in-app stall sources (AI HTTP
calls and sign-in hashing); giving the single worker more headroom (a larger CPU
tier) remains the complementary infrastructure-side lever.

Operational note (separate from this code change): the live Space had
`CSS_GEMINI_API_KEY` + `CSS_GEMINI_MODEL` + `CSS_GROQ_API_KEY` set. Removing the
Gemini secret disables all AI at the config gate (`ai_configured()` is false, so
`ask()` short-circuits before any HTTP call and every feature falls back to its
deterministic behaviour) — the fastest way to stop the blocking calls
immediately, independent of a redeploy.

## 2026-07-19 (v2.18 — edge-retry shield against HF routing failures)

Since ~12:35 UTC today (immediately after a Space visibility toggle), ~40-60%
of requests to the Space's direct URL are answered by HF's infrastructure
itself — first `503` from `server: awselb/2.0`, later HF's proxy 500 page,
both with **no** Spaces-proxy headers — while the app replica stays healthy
(control probes of other Spaces through the same edge are 100% consistent, so
the poisoned route is specific to this subdomain). It survives container
restart, redeploy, and pause/resume, and it aborted two auto-deploys at the
`pull_backup` pre-deploy gate. HF-side fix is theirs to make; this ships the
app-side shield.

Key mechanism: the server now stamps `X-CSS-App: 1` on **every** response it
produces (success, 4xx, even unhandled 500s via a new `Exception` handler). A
5xx *without* that header is therefore proof the request never reached the
app — which makes an automatic retry safe for any method, POSTs included.

- **`app.py`** — `_metrics_gate` stamps `X-CSS-App: 1` on every response; new
  `@app.exception_handler(Exception)` `_unhandled_error` returns the plain 500
  WITH the marker (Starlette still re-raises, so tracebacks keep reaching the
  log) — without this, an in-app crash on a POST would look retry-safe to the
  service worker and could double-execute.
- **`static/js/sw.js`** — new `fetchRetrying(req, retryNetworkErrors)`: up to
  3 extra attempts with linear backoff on any 5xx lacking `x-css-app`.
  Wired into all four request classes: static assets (inside the
  stale-while-revalidate refresh), navigations (before the cache/offline
  fallback), all other same-origin GETs (previously not intercepted), and —
  new — non-GET writes, which are retried **only** on the provable edge-error
  case, never on network errors (the Phase-2 offline queue + submission_id
  dedup already covers those). `CACHE_VERSION` → v2.18-a.
- **`pull_backup.py`** — `_with_retry` (6 attempts, linear backoff) around
  `_get`/`_post`: edge 5xx (5xx without `X-CSS-App`) always retried; plain
  network errors retried for GETs only. The 3xx-returned-as-value contract of
  `_post(follow=False)` is preserved inside the retry wrapper.
- **`deploy_hf.py`** — `_fetch_live_login` (version pre-check + post-deploy
  verify) retries 5 times on any HTTP/URL error.
- **`tests/test_pwa.py`** — 4 new tests: marker present on 200/3xx/404; marker
  present on an unhandled-crash 500 (via a temp route + non-raising client);
  sw.js contains the retry shield and intercepts writes.

## 2026-07-19 (v2.17 — fix: default Gemini model closed to new API keys)

Follow-up to v2.14's model bump. The live site's newly created
`CSS_GEMINI_API_KEY` gets a 404 from Gemini for every call:
`"This model models/gemini-2.5-flash is no longer available to new users."`
— Google has closed `gemini-2.5-flash` to keys that didn't already use it.
Per https://ai.google.dev/gemini-api/docs/models the current stable fast
model is `gemini-3.5-flash`.

- **`ai_core.py`** — `GEMINI_MODEL_DEFAULT` is now `gemini-3.5-flash` (was
  `gemini-2.5-flash`); module docstring updated. `CSS_GEMINI_MODEL` still
  overrides.

## 2026-07-19 (v2.16 — fix: unhandled 500 from a whitespace-tainted AI env var)

Production incident: right after `CSS_GEMINI_API_KEY`/`CSS_GROQ_API_KEY` were
added as HF Space secrets, `POST /api/ai/route` (the Start-page NL search bar)
500'd. Traceback: `httpx.InvalidURL: Invalid non-printable ASCII character in
URL, '\n' at position 75`, raised from `_http_generate`'s `httpx.post(url, …)`
at `ai_core.py:311`, inside `ask()`. Root cause: `ai_model()` read
`CSS_GEMINI_MODEL` via a bare `os.environ.get(...)` and interpolated it
straight into the Gemini request URL; a trailing newline picked up when the
model name was pasted into the secret produced a malformed URL.
`httpx.InvalidURL` is a bare `Exception`, not a `TimeoutException`/
`TransportError`, so `_http_generate`'s retry loop didn't catch it — it
escaped `ask()`'s documented "every AI feature must fall back, never a
user-facing error" contract entirely.

- **`ai_core.py`** — new `_env(name, default="")` helper: strips the raw env
  value, falls back to `default` if the result is empty. `ai_configured()`,
  `ai_model()`, `groq_configured()`, `ai_groq_model()`, and the
  `x-goog-api-key`/`Authorization` header reads in `_http_generate`/
  `_http_generate_groq` all go through it now instead of a raw
  `os.environ.get`. Belt-and-suspenders: both `_http_generate` and
  `_http_generate_groq` now also catch `httpx.InvalidURL` around the
  `httpx.post` call and re-raise as `AIBadResponse` (no retry — a malformed
  URL is a config problem, not a transient one), so any future request-build
  failure degrades the same way a bad HTTP response already does instead of
  bubbling up raw.
- **`tests/test_ai_core.py`** — 6 new tests: `CSS_GEMINI_MODEL`/
  `CSS_GEMINI_API_KEY` whitespace is stripped (and actually reaches the
  request that way); a whitespace-only model value falls back to
  `GEMINI_MODEL_DEFAULT`; `httpx.InvalidURL` from either `_http_generate` or
  `_http_generate_groq` surfaces as `AIBadResponse`, not an unhandled
  exception.

## 2026-07-19 (v2.15 — Groq fallback AI provider)

`docs/AI_FALLBACK_PLAN.md` (build spec, merged in #43) implemented as-is. Adds a
second, free-tier provider (Groq) that `ai_core.ask()` tries automatically —
only on the two "Gemini's quota is exhausted" branches (`AIBudgetExceeded`, or
the 429-cooldown `AIUnavailable`), never on `AITimeout`/`AIBadResponse`.
Admin opt-in, off by default; `harmonize` is hard-excluded regardless of the
toggle. With no `CSS_GROQ_API_KEY` set, or `ai_fallback_enabled=0` (the
shipped default), behavior is byte-for-byte identical to today.

- **`ai_core.py`** — `CSS_GROQ_API_KEY`/`CSS_GROQ_MODEL` config
  (`groq_configured()`, `ai_groq_model()`), `fallback_enabled(conn)` (the
  `ai_fallback_enabled` setting), a separate Groq 429 cooldown
  (`_GROQ_COOLDOWN_UNTIL`/`_groq_in_cooldown`/`_set_groq_cooldown`/
  `groq_cooldown_remaining`/`reset_groq_cooldown`), `_http_generate_groq`
  (mirrors `_http_generate`'s retry/timeout/schema contract against Groq's
  OpenAI-compatible `chat/completions` endpoint), `_try_groq_fallback`
  (feature/setting/config/rate-limit gate), and `_fold_groq_error`. `ask()`'s
  `AIBudgetExceeded` and (newly split-out) `AIUnavailable` branches now
  attempt the fallback before re-raising; `AITimeout`/`AIBadResponse` are
  untouched. `_log_interaction`/`create_ai_interaction` gain a `provider`
  kwarg (default `"gemini"`). New `test_groq_connection()` for the admin
  smoke test.
- **`storage.py`** — `ai_interaction.provider TEXT` column (guarded ALTER in
  `_add_missing_columns`); `create_ai_interaction`, `_ai_interaction_row`,
  `list_ai_interactions` thread it through (`_ai_interaction_row` reads NULL
  as `"gemini"`).
- **`ratelimit.py`** — `"ai_groq": (10, 60)` bucket, independent of the
  existing `"ai"` bucket.
- **`app.py`** — `admin_ai` passes Groq status (`groq_configured`,
  `groq_model`, `groq_cooldown_remaining`, `fallback_enabled`) into the
  template; `admin_ai_settings` reads/saves `ai_fallback_enabled`; new
  `POST /admin/ai/test-groq` route mirroring `admin_ai_test`.
- **`templates/admin_ai.html`** — a Groq status row, an `ai_fallback_enabled`
  checkbox (with a note that `harmonize` is always excluded), a "Test Groq
  connection" button, and a provider column on the interaction log.
- **`tests/test_ai_core.py`** — 10 new tests: Groq success on budget-exceeded
  and on Gemini 429 (the latter asserting Gemini's own cooldown survives);
  two backward-compat regressions (no key / toggle off); Groq itself 429ing
  (both cooldowns end up set, both failures folded into one logged error);
  `AITimeout`/`AIBadResponse` never attempting Groq; `harmonize` never
  attempting Groq; the `ai_groq` ratelimit bucket blocking the attempt.
- **Deploy note:** `CSS_GROQ_API_KEY` still needs to be added as an HF Space
  secret before this can do anything in production.

## 2026-07-19 (v2.14 — Fix AI: default Gemini model was deprecated; log 429 bodies)

Live diagnosis (`/admin/ai` interaction log): the key was configured and mode
was `assistant`, yet the very first real call — and every call after — failed
with `Gemini rate limit (429)`. A first-call 429 is quota `limit: 0`, not a
burst limit: Google deprecated `gemini-2.0-flash` (June 1, 2026) and free-tier
quota now only covers Gemini 2.5 models, so a free-tier key calling the old
default is refused outright.

- **`ai_core.py`** — `GEMINI_MODEL_DEFAULT` is now `gemini-2.5-flash` (was
  `gemini-2.0-flash`; `CSS_GEMINI_MODEL` still overrides). The 429 branch of
  `_http_generate` now appends the first 300 chars of Google's response body to
  the `AIUnavailable` message, so the `ai_interaction` log distinguishes a real
  burst limit from "this model has zero quota" — the ambiguity that made this
  outage look like ordinary rate-limiting.
- **`docs/AI_INTEGRATION_PLAN.md`** — default-model note updated to match.

## 2026-07-19 (v2.13 — Phase 10 of the AI integration plan: Filipino translation review)

`docs/AI_INTEGRATION_PLAN.md` Phase 10, the lowest-priority, one-off phase — an
offline dev tool rather than a web feature, so there is no route/RBAC surface.

- **`tools/i18n_review.py`** (new) — CLI script (`python tools/i18n_review.py`)
  that walks every DRAFT Filipino string in `i18n.py` (`B_TEXT_FIL`, `A_TEXT_FIL`,
  `C_TEXT_FIL`, `CONSENT_TMPL_FIL`, `LIKERT5_FIL`, `OSQ4_FIL`, `REMARK_CHIPS_FIL`,
  and the `UI` chrome dict — everything except the already-official
  `ARTA_TEXT_FIL`), paired with its English source in `app.py`, and batches them
  (20/call) through `ai.ask(feature="i18n_review", response_schema=...)` asking
  for a natural, formal-register revision of each. Suggestions are validated
  against a per-batch key allow-list (a key the model wasn't asked about is
  dropped) and a placeholder-preservation check (a suggestion that drops or
  rewrites a `{subject}`/`{months}` token is rejected with a "needs manual fix"
  reason instead of being shown as usable) — same "model output is never
  trusted" discipline as every other phase. The script only prints a
  side-by-side report (optionally to `--out file.md`); it never writes back to
  `i18n.py` — the office still copies in whatever wording it wants by hand.
  Gates on the same `ai_configured()`/`ai_mode`/`feature_enabled()` checks as
  every route-based feature, with a plain-language early-exit message for each.
  Not added to `deploy_hf.py`'s `RUNTIME_PY`/`ALLOW` — it's a dev-machine-only
  tool, never shipped to the Space, same as the existing `tools/contrast_check.py`.
- **`ai_core.py`** — `"i18n_review": 20` added to `FEATURE_DEFAULTS`, which
  automatically wires it into `/admin/ai`'s per-feature cap/flag settings (that
  page iterates `ai.FEATURES`, no template change needed).
- **`version.py`** — `APP_VERSION` 2.12 → 2.13, CHANGELOG entry prepended.
- **`tests/test_i18n_review.py`** (new) — `build_review_items()` covers every
  DRAFT group with unique keys and skips `ARTA_TEXT_FIL`; `review_batch()`
  accepts a valid mocked suggestion, rejects one missing a required
  placeholder, and ignores a key it never asked about (prompt-injection
  guard); `main()`'s three early-exit gates (unconfigured, mode off, feature
  disabled); an end-to-end run with `--limit`/`--out`; and that an `AIError`
  mid-run is skipped and reported rather than crashing the script.

## 2026-07-19 (v2.06 — Phase 3 of the AI integration plan: UX Insights "Analyze now")

`docs/AI_INTEGRATION_PLAN.md` Phase 3, the lowest-risk real feature (admin-only,
zero PII — the handoff payload is already pseudonymized). Ships with
`ux_analysis` already present in `ai_core.FEATURE_DEFAULTS` (cap 5/day) since
Phase 0, so no new setting/table/`admin_ai.html` changes were needed.

- **`app.py`** — `POST /admin/ux-insights/analyze` (new, next to the existing
  `GET /admin/ux-insights/handoff`): builds the identical `uxh.build_handoff(...)`
  payload as the download route, renders it with `uxh.render_handoff_markdown`,
  and hands that Markdown to `ai.ask(feature="ux_analysis", max_output_tokens=2048,
  timeout=30.0)` with a short system prompt steering toward a concise,
  numbered improvement write-up. Any `AIError` returns `{"ok": false, "notice":
  ...}` pointing back at the existing download link — the feature never surfaces
  an error, and export never depends on AI. A successful call is audited the
  same way as the handoff download (`action="export"`). No new gating code:
  inherits `manage_users` via the existing `/admin` prefix rule.
- **`templates/ux_insights.html`** — "✨ Analyze now" button beside the
  existing download links; inline `<script>` posts to the new route and
  renders the result as an in-page card with 👍/👎 feedback chips, reusing the
  same `sendBeacon`-first pattern as `static/js/start.js`'s feedback wiring
  (posts to the existing generic `/api/ai/feedback`, no new feedback route).
- **`version.py`** — `APP_VERSION` 2.05 → 2.06, CHANGELOG entry prepended.
- **`tests/test_ux_analysis.py`** (new) — RBAC, success shape, `AIError` and
  budget-exceeded fallback (both return `ok: false` with a notice, never an
  error status), audit row, and an end-to-end leak test proving an unmasked
  digit posted through `/telemetry` never reaches the prompt handed to
  `ai_core.ask()`.

## 2026-07-19 (v2.04 — Phase 1 of the AI integration plan: NL landing page + router mode)

`docs/AI_INTEGRATION_PLAN.md` Phase 1, built on Phase 0's `ai_core.py`. Ships
with `ai_mode` still defaulting to `off` — the new page always renders and
always answers something, but the router itself is inert until an admin
opts in from `/admin/ai`.

- **`app.py`** — `ai_route_catalog(user)` (new): the NL router's
  destination allow-list, same role/cap filtering as `search_index_for` but
  keyed by `key` (what the router validates against) instead of flattened
  by section. `GET /start` (any signed-in user, no new gating — renders
  regardless of AI mode). `POST /api/ai/route`: builds the prompt from the
  catalog, calls `ai.ask(feature="nl_router", response_schema=...)`,
  then validates the model's `destination` against the catalog and its
  `confidence` against a 0.5 floor server-side before ever building a URL —
  the URL always comes from the catalog entry, never from model text; an
  unknown destination or sub-floor confidence is logged as
  `rejected_validation` (via the new `storage.update_ai_interaction_outcome`)
  and falls back. `POST /api/ai/feedback`: 👍/👎 posted via
  `sendBeacon`, rate-limited on the existing `"telemetry"` bucket (costs no
  AI budget), ownership-checked in `storage.set_ai_feedback`.
  `login_submit`: a fresh sign-in with `next=/` redirects to `/start` instead
  of the hub when AI is configured, mode ≥ router, and the admin-set
  `ai_landing_default` setting (added in Phase 0) is `start` — rollback is
  flipping either setting back.
- **`storage.py`** — `update_ai_interaction_outcome` (new): lets a feature
  backfill the router-only `destination`/`confidence` columns and/or
  override the outcome `ai_core.ask()` already logged, for the case where
  the call reached Gemini fine but the feature's own server-side validation
  doesn't trust the answer.
- **`templates/start.html`** + **`static/js/start.js`** (new): a centered
  "What do you want to do?" box in the `dash_layout` shell, greeting via the
  existing `_account_first_name`, 4–6 suggestion chips from
  `nav_groups_for(user)`. `start.js` copies `search.js`'s debounce/abort
  pattern client-side (9s timeout vs. the server's 8s), shows a result card
  with Go/Cancel + feedback chips and a ~1.5s auto-navigate, and falls back
  to `window.CSSSearch` (the existing keyword palette engine) on any
  non-`navigate` response, timeout, or network error.
- **`templates/home.html`** — a "✨ Try the assistant" link to `/start`
  beside the role chip.
- **`tests/test_ai_router.py`** (new) — per-role destination routing;
  prompt-injection (a mocked model steering a viewer to an admin-only
  destination still falls back); malformed/out-of-catalog destinations and
  sub-floor confidence rejected server-side; budget-exceeded falls back;
  feedback ownership/RBAC; `/start` renders for all four roles; the login
  redirect honors both settings and leaves a plain `next=/` alone otherwise.

## 2026-07-19 (v2.03 — Phase 0 of the AI integration plan: `ai_core.py` foundation)

`docs/AI_INTEGRATION_PLAN.md` Phase 0: the module every future AI feature is
a thin caller of. Ships with `ai_mode=off` — behavior is byte-for-byte
unchanged; this is purely plumbing + the admin console to operate it.

- **`ai_core.py`** (new) — the only module that ever calls Gemini. Config
  gates (`ai_configured`/`ai_model`/`ai_mode`/`feature_enabled`); error
  taxonomy (`AIError` ← `AIUnavailable`/`AIBudgetExceeded`/`AITimeout`/
  `AIBadResponse`); `budget_check_and_consume` (atomic `BEGIN IMMEDIATE`
  upsert+check+increment on `ai_budget`, keyed by local calendar date —
  survives a restart, no scheduler needed); `_http_generate` (the sole
  network call site — Gemini REST v1beta `generateContent` via `httpx.post`,
  connect timeout 3s/total 8s default, retries once on 5xx/timeout, a 429
  sets a 60s in-memory cooldown and never retries); `mask_for_log` (email +
  digit-run masking, mirrors `ui_telemetry.sanitize_text`); `ask()` (the
  single entry point — config/mode/feature gate → `ratelimit.allow("ai", ip)`
  → budget consume → HTTP → `ai_interaction` log on every outcome, success or
  fallback); `test_connection()` (the `/admin/ai` egress smoke test, bypasses
  mode/feature gates since `ai_mode=off` is the shipped default).
- **`storage.py`** — new `ai_interaction` (full call log incl. masked
  prompt/response, outcome, latency/tokens, and a 👍/👎 `rating` column) and
  `ai_budget` (day+feature keyed daily spend counter) tables in
  `_add_missing_columns`; `create_ai_interaction`, `set_ai_feedback`
  (row-ownership check), `list_ai_interactions` (feature/outcome/rating/since
  filters), `purge_stale_ai_interactions`, `purge_stale_ai_budget`. Both
  tables registered in `pull_backup.py`'s `_CHECK_TABLES`.
- **`retention.py`** — `purge_stale_ai_log` (`--ai-log` CLI flag, mirrors
  `--ui-events`): purges `ai_interaction` past `ai_log_retention_days`
  (default 90) plus the matching stale `ai_budget` day-rows.
- **`ratelimit.py`** — new `"ai"` burst bucket, `(20, 60)` default,
  env-overridable via `CSS_RL_AI`.
- **`app.py`** — `GET /admin/ai` (status card + settings form + interaction
  log browser, filterable by feature/outcome/👍👎), `POST /admin/ai/settings`
  (mode, global + per-feature daily caps, per-feature enable flags, prompt
  logging on/off, log retention, post-login landing default — all
  validated/clamped + `_audit`ed), `POST /admin/ai/test` (calls
  `ai_core.test_connection`, audited either way). Admin-gated for free via
  the existing `/admin` prefix in `_required_cap` — no new gating code.
  `NAV_GROUPS` gains an Admin → AI entry.
- **`templates/admin_ai.html`** (new) — modeled on `ux_insights.html` +
  `feedback_board.html`: status card with per-feature usage bars vs caps and
  a cooldown indicator, the settings form, and the log browser with
  expandable masked prompt/response/error per row.
- **Housekeeping** — `httpx` promoted from the QA section of
  `requirements.txt` to a runtime dependency (this is the app's first
  outbound HTTP call from a request handler); `ai_core.py` registered in
  `deploy_hf.py`'s `RUNTIME_PY`; `version.py` → 2.03 with a plain-language
  entry; `tests/test_ai_core.py` + `tests/test_ai_admin.py` (new) cover the
  budget/cooldown/retry/masking contract and the admin console's RBAC +
  settings clamp + audit trail.

## 2026-07-18 (v2.02 — Downloadable UX handoff + the two dormant telemetry signals)

Three additions to the UX telemetry system shipped in v2.01: a downloadable
AI-analysis handoff, live `search_empty` dispatch, and a `form_abandon`
detector.

- **`ux_handoff.py`** (new, pure — no DB/FastAPI, same testability contract as
  `ui_telemetry.py`) — builds the handoff payload over `build_digest()`:
  `events_per_day`/`event_type_counts`, `pseudonymize_events` (drops
  id/user_id, session ids → per-export `s1`/`s2`… pseudonyms, ≤200 most
  recent), `map_routes_to_handlers` (masked route → app.py handler name, by
  segment-shape match against route objects' `.path`/`.name`),
  `feature_usage` (every NAV_GROUPS destination ranked by pageviews, with
  rarely-used/NEVER-used buckets — the "redesign around what staff actually
  use" section), `build_handoff` (adds `nav_flows`, which `build_digest`
  deliberately omits) and `render_handoff_markdown` (deterministic, pipe-
  escaped, self-describing: app context, vocabulary, sanitization semantics
  and the analysis brief travel inside the file).
- **`app.py`** — new `GET /admin/ux-insights/handoff?days=&fmt=md|json`
  (admin-gated for free via the `/admin` prefix): same window clamp + fetch
  block as `ux_insights`, audited like the Spot Feedback export, ships
  `UX_Handoff_{days}d_{ts}.md`/`.json` as `Content-Disposition: attachment`.
  `_clean_telemetry_meta` now also passes `meta.fields` (a small int — the
  form_abandon touched-field count, clamped 1–500). UX Insights nav keywords
  extended with "handoff export download ai".
- **`static/js/telemetry.js`** — `form_abandon` detector: Map of form →
  touched-field Set built from capture-phase `input`/`change`, cleared on
  `submit`, emitted on `pagehide` only (a tab switch is not abandonment) with
  `meta={fields: n}` — never field names or values. Search/filter forms opt
  out via `[data-search]`/`[role="search"]`/`[data-telemetry-ignore]`; the
  Spot Feedback overlay stays excluded.
- **`static/js/search.js`** — dispatches `csi:search-empty` (the event
  telemetry.js has listened for since v2.01) when a palette/inline query has
  zero page hits AND the debounced `/api/search` fetch settles empty; once
  per term per page load.
- **`templates/_telemetry.html`** (new) — `search_empty_signal(term,
  is_empty)` macro for server-rendered zero-result pages (waits for
  DOMContentLoaded so the deferred telemetry.js listener exists first); used
  by `search.html`, `encode_home.html`, `people.html`. `help.html`'s inline
  topic filter dispatches the same event, debounced. `ux_insights.html`
  gains the download control; `dash_layout.html` cache-busters bumped.
- **Housekeeping** — `ux_handoff.py` registered in `deploy_hf.py`'s
  `RUNTIME_PY`; `version.py` → 2.02 with a plain-language entry.
- **Tests** — new `tests/test_ux_handoff.py` (pure fixtures); handoff-
  endpoint coverage in `tests/test_ux_insights.py` incl. an end-to-end leak
  test (raw digits POSTed through `/telemetry` never surface in the export);
  `meta.fields` ingest coverage in `tests/test_telemetry_ingest.py`.

## 2026-07-17 (v2.01 — Build telemetry + passive UX-behavior telemetry pipeline)

Two additions, both admin-facing: which build is actually running (`/ops`), and a
ranked "what to fix first" digest of passive interface-friction signals (`/admin/
ux-insights`) — dead/rage clicks, failed searches, client errors — ported from
`jongsky25/ofis-platform`'s `lib/telemetry.ts` + `Telemetry.tsx` + ingest/digest
routes (commit `7a7e369`) per `docs/UX_TELEMETRY_HANDOFF_PLAN.md`, adapted to this
app's Flask/Jinja/SQLite stack (that reference is Next.js + Supabase).

- **`deploy_hf.py`** — new `write_build_info(version, deployed_by)` stamps
  `build_info.json` (version, git commit SHA + short SHA, deploy timestamp,
  deployer) right before `upload_folder`, added to `ALLOW` so it ships in the
  same bundle it describes. `ui_telemetry.py` added to `RUNTIME_PY`.
- **`app.py`** — new `_load_build_info()` reads `build_info.json` (falls back to
  just `version.APP_VERSION` on a local/dev run with no deploy metadata). New
  `POST /telemetry` ingest route: login-gated via the existing auth middleware,
  rate-limited (`ratelimit.py`), caps batch size, re-sanitizes every field
  server-side rather than trusting the client's own masking alone. New
  `GET /admin/ux-insights` (admin-gated for free via the existing `/admin`-prefix
  → `manage_users` cap) with a 7/30/90-day window switcher, plus
  `POST /admin/ux-insights/retention` to save the admin-configurable retention
  window. New `NAV_GROUPS` entries for both.
- **`storage.py`** — new `ui_event` table (additive, mirrors the
  `spot_feedback`/`audit_log` conventions) + `create_ui_events`/`list_ui_events`
  (with a `since` window filter) + `purge_stale_ui_events`.
- **`ui_telemetry.py`** (new) — the controlled event-type vocabulary, text/
  selector sanitizers, `mask_route` (a generic segment-shape sibling to
  `monitoring.bucket_path`'s hand-curated table; idempotent, so re-running it
  server-side over an already-masked client value is safe), and the aggregation
  half ported from `lib/telemetry.ts`: `top_routes`/`nav_flows`/`exit_routes`,
  `empty_search_terms`/`errors_by_route`, `friction_by_target`/`friction_score`
  (rage-weighted, user-damped), `correlate_feedback` (matches Spot Feedback by
  route+selector), and `build_digest` (the ranked, feedback-boosted opportunity
  list). All pure — plain dict rows in, no DB — so they're cheap to unit test.
- **`static/js/telemetry.js`** (new) — vanilla-JS capture script (no client
  router here, unlike the React reference): pageview, dead-click, rage-click,
  client-error detection; `sessionStorage`-backed session id (a JS var would
  fragment every full page load into its own "session"); ships via `sendBeacon`
  with a `fetch`/`keepalive` fallback. Wired into `dash_layout.html`, signed-in
  shell only.
- **`templates/ops.html`** — new "Build" panel. **`templates/ux_insights.html`**
  (new) — ranked opportunities table + top-screens/exit-routes/failed-searches/
  errors side panels + the retention-window settings form.
- **`retention.py`** — new `purge_stale_ui_events` (CLI: `--ui-events [--days N]`),
  reading the `ui_telemetry_retention_days` app_setting (default 90 days) when
  `--days` isn't given. Kept independent of the existing attendee-PII job
  (different legal basis, months-based, audited) rather than merged — manual/
  cron-invoked only, matching how that job already runs today (no in-process
  scheduler exists for either yet).
- **Fix found via manual verification** (not code review): running the app
  locally and driving it with Playwright caught `INTERACTIVE`'s `[data-tour]` and
  bare `[tabindex]` clauses — ported as-is from the OFIS reference — both
  matching ancestors present on nearly every click in this app specifically
  (`data-tour` tags whole page regions here, not individual controls; the shared
  `<main tabindex="-1">` skip-link target wraps every page's content), which was
  silently disabling single dead-click detection app-wide. Fixed by dropping
  `[data-tour]` and scoping `[tabindex]` to `:not([tabindex="-1"])`.
- **Tests** — 42+ new tests: pure sanitizer/`mask_route`/aggregation unit tests
  (including OFIS's own ranking-acceptance case — a feedback-correlated hotspot
  outranking a higher-raw-count one), storage round-trips, ingest-route RBAC/
  validation/re-sanitization tests, retention purge tests, and digest-view RBAC/
  rendering tests. Full suite: 634 passed (3 pre-existing failures unrelated to
  this change, dependent on a large seeded production `css_is.db`).
- Out of scope for this pass (matching the handoff doc's own suggested order):
  wiring `retention.py --ui-events` into an automatic schedule — it's manual/
  cron-invoked only right now, same as the existing attendee-PII purge.

PR #26.

## 2026-07-17 (v2.00 — Quick-pick comment chips capped at 3, opposite pairs mutually exclusive)

Respondents could tap every canned "quick-pick" comment chip on a survey form at
once (`REMARK_CHIPS` in `app.py`), producing walls of tags and, worse,
self-contradictory pairs (e.g. "Fast service" + "Long wait" both landing in the
same `remarks` free-text field).

- **`app.py`** — `REMARK_CHIPS` restructured from a flat list of strings per
  survey kind to a list of `(word, group)` pairs; `group` is `None` for
  standalone chips or a shared key (`speed`, `process`, `clarity`, `timing`)
  for chips that are opposites of each other. New `MAX_REMARK_CHIPS = 3`
  constant, passed into the `rating.html` / `combined_form.html` render
  contexts as `max_remark_chips`.
- **`i18n.py`** — `REMARK_CHIPS_FIL` restructured with the same group keys,
  index-aligned with `REMARK_CHIPS`; `chips_hint` copy (en + fil) updated to
  mention the 3-chip limit.
- **`templates/rating.html`, `templates/combined_form.html`** — chip loop
  unpacks `(word, group)` and renders `data-group` / the container's
  `data-max-chips`; `toggleChip()` in both templates now frees a conflicting
  chip's slot (same `data-group`) before re-checking the cap, so tapping a
  chip's opposite swaps it in even while already at the limit, and a `.chips.
  at-max` CSS rule dims the remaining inactive chips once the cap is hit.
- **`static/js/app.js`** — new shared `window.refreshChipCap(container)`
  helper (reads `data-max-chips`, toggles `.at-max`), called from both
  templates' `toggleChip()` and from the draft-resume chip re-lighting logic
  so a resumed draft saved before this change (with more than 3 words) shows
  the correct dimmed state.
- No backend/schema change — `remarks` stays free text; the cap/conflict
  rules are a chip-authoring aid only, so typing past 3 phrases by hand is
  still allowed.
- **Verified** with Playwright against the running app: cap enforcement,
  opposite-pair swap-while-at-cap, and draft-resume re-hydration all behave
  correctly; confirmed both `/r/<token>` and `/seq?tokens=...` render the new
  markup.

PR #18.

## 2026-07-17 (v1.99 — Type-2 activity XLSX "Relevant Findings" reformatted to the official MRR layout)

The Type-2 activity inventory Excel download (`/reports/activities-export` and
`/reports/activities/export-selected`, Sheet 1 `AGENDA 4_Sheet1`) had its
"Relevant Findings" cell reformatted to match the official MRR report's
letterhead layout, per a direct format spec from the bureau.

- **`app.py`** — `_activity_relevant_findings(e)` (replaces `_activity_css_seed`)
  builds the cell as: activity title / full date / modality, blank line,
  `SERVQUAL Score: <gap> (<verdict>)` and `Overall SERVQUAL Rating: <OSQ>
  (<band>)` (reusing `dashboard_insights.activity_servqual`, the same official
  scorecard the per-activity report page already shows — so the export and the
  screen can never disagree), `Response Rate:` / `Total Number of Responses:` /
  `Total Number of Participants (Pax):`, blank line, then `COMMENTS:` with up
  to 5 verbatim remarks typed into the form's free-text comment box (never the
  pre-selected rating items).
- New `_attach_activity_findings(atoms, conn, events)` mutates each event dict
  in place with `report` (the SERVQUAL scorecard) and `comments` (deduplicated,
  capped-at-5 remarks via the existing `_dedup_remarks`/`_meaningful_remark`
  helpers, which already drop throwaway answers like "none"/"n/a"/"wala").
  Called from both export routes before the connection closes, since the
  comment fetch needs an open `conn`. The `export-selected` route's `events`
  come from the memoized `view_memo("events", ...)` view, so `chosen` is built
  as `[dict(e) for e in events if ...]` — copies, so the in-place mutation
  never corrupts the shared cache.
- New `_fmt_activity_date_full` (full month name, e.g. "January 15, 2026") for
  the letterhead line, alongside the existing abbreviated `_fmt_activity_date`
  used in Sheet 2's inventory table.
- **Tests** — full suite green against a fresh empty DB (no regressions); the
  new formatter and the `_dedup_remarks` cap/filter behavior were additionally
  smoke-tested directly against fabricated event/report/comment payloads (no
  new test file — no seeded fixture activity exists to assert the exact cell
  text against end-to-end; the existing `test_bulk_actions.py` export-selected
  test only checks that a workbook downloads, not cell content).

PR #17.

Second half of the spot-feedback #67 fix. Root cause of the duplicate event that
prompted v1.96: `POST /create` had zero duplicate-submission protection — no
client-side disable-on-submit guard, no idempotency token, no server-side check.
The two live duplicate pairs (26 minutes and 3 minutes apart, same creator, same
title/date/venue/organizer) don't look like a reflexive double-click; more likely
the creator didn't realize the first save had already succeeded and re-ran Create
from scratch.

Considered blocking the second submit server-side with an interstitial "are you
sure?" page, but that changes what `POST /create` does on a matching title+date —
and the existing test suite (test_modality.py, test_date_range.py,
test_registration_dedup.py, test_event_e.py, test_certificate.py,
test_date_handling.py) has ~25 cases across 6 files that legitimately recreate an
identically-titled/dated activity under the same manager fixture within one test
session (session-scoped shared DB), which is indistinguishable from the real
duplicate case by title+date+creator alone. Blocking broke all of them. Went with
a **live, non-blocking** check instead: it warns, it never blocks Save, so
`POST /create`'s behavior is completely unchanged and every existing test still
holds — including new tests that pin this down explicitly.

- **`storage.py`** — new `find_recent_duplicate_event(conn, title, event_date, created_by, within_hours=6)`: the most recent event with the same title (case/space-insensitive) and date, made by the SAME creator inside the lookback window. Returns `{id, event_token, created_at, event_kind, responses}` or `None`.
- **`app.py`** — new `GET /create/check-duplicate?activity_name=&event_date=` (JSON, login-required via the existing middleware): calls the storage helper for the signed-in user and returns `{"duplicate": null}` or the match with a human-readable timestamp (`_humandt`). Read-only, no side effects.
- **`templates/form_create.html`** — new `#dupWarn` note box (hidden by default) and `checkDuplicate()`: a 500ms-debounced fetch fired on `activity_name` input / `event_date` change. On a hit it shows when the existing one was made, its response count, and a link straight to it (`/monitor/<token>` for a bureau event, `/activities/<token>/manage` for an outside one). Never touches form submission.
- **`static/css/app.css`** — `.dup-warn`, amber-toned (a heads-up, not the red `.errors` block) since the form is otherwise valid and submitting is still allowed.
- **Tests** — new `tests/test_create_duplicate_warning.py`: the storage matcher (same-creator hit, different-creator miss, different-date miss, outside-lookback-window miss), the JSON endpoint (hit, miss, login-required), and — the key regression guard — `test_create_still_allows_a_genuine_second_activity_with_the_same_name` locking in that `/create` itself is unchanged. Full suite green (589 passed; the same pre-existing `test_backups.py` failure and `test_csm_official.py` collection error as v1.96, both unrelated).

## 2026-07-15 (v1.96 — archive/restore reach bureau & outside events, not just standalone forms)

Prompted by spot-feedback #67: a same-day duplicate bureau event (created by mistake, zero
responses) had no reachable Archive button. The only inline archive on the Ongoing feed
(`/activities/instance/<fid>/archive`, v1.74) requires the activity still be in that feed —
which a bureau event with no `close_at` leaves at the end of its event day — and the "Your
recent activities" strip's inline archive (`/activities/form/<fid>/archive`) explicitly
refuses anything with an event record. Once an event ages out of Ongoing there was **no
one-click Archive control left anywhere** (its own manage page's Archive button is
`event_kind == 'outside'`-only). Separately, an event archived via the Ongoing feed or the
Activities-page bulk action had **no restore path in the UI at all** — `/activities/archived`
and its bulk-restore route both filtered to standalone forms only, even though the bulk
archive action's own confirmation message claims "An admin can restore them."

- **`storage.py` `activities_by_creator`** — new `has_event` field per row (`tok is not None`),
  alongside the existing `archivable` (unchanged: standalone-only, drives the per-form route).
  Lets a template pick the right archive/restore route per row shape.
- **`app.py` `activity_inline_archive`** (`POST /activities/instance/{fid}/archive`) — now
  accepts `restore=1`, mirroring every other archive route. Restore expands to the full
  event bundle exactly like the archive direction does, via `st.set_form_archived`. Kept the
  existing permission model (`create_activity`, no per-creator ownership check) for both
  directions, since that already matched production behavior for archiving a bureau/outside
  event from the Ongoing feed.
- **`app.py` `/activities/archived`** (GET) — now lists rows where `archivable` **or**
  `has_event` is true, so event-bundled archives are finally visible and restorable.
- **`app.py` `/activities/archived/bulk`** — extended to detect `info["has_event"]` per ticked
  id and, when set, expand to the event's full form bundle and restore it under the
  `create_activity` gate; standalone rows keep the exact prior ownership-scoped behavior
  (creator or admin) so `test_bulk_restore_skips_other_owners_form` still holds.
- **`templates/home.html`** — "Your recent activities" now renders an Archive button for
  event-bundled rows too (`a.has_event`, posting to the instance route with the same confirm
  dialog the Ongoing feed uses), not only standalone ones (`a.archivable`, unchanged route).
  Copy on both variants of the feed subtitle updated to drop "standalone".
- **`templates/activities_archived.html`** — per-row Restore posts to
  `/activities/form/<fid>/archive` for standalone rows (unchanged) or
  `/activities/instance/<fid>/archive` for event-bundled ones (new); page copy no longer says
  "Standalone activities."
- **Tests** — `tests/test_home_feeds.py`: restore round-trip for a bureau event via the
  instance route (archive → appears on Archived page → restore → both bundled forms come
  back), and a new "Recent activities" render test confirming a bureau event gets an Archive
  button. `tests/test_bulk_actions.py`: bulk-restore of a bundled event (both forms come back,
  gated on `manage_event`/`create_activity`). Full existing suite green (589 passed; the one
  `test_backups.py` failure and the `test_csm_official.py` collection error are pre-existing
  environment artifacts unrelated to this change — reproduced identically with these changes
  stashed out).

## 2026-07-13 (v1.95 — manager-entered respondent count as the completion-rate denominator)
Builds on v1.94 (which folds the not-pre-registered responses into the rate). A section manager (on activities they created) or an admin (on any) can now **override the completion-rate denominator** with the real number of respondents, instead of being tied to the online-registration count. Even after v1.94 counts walk-ins, the denominator is still `registered + unattributed` — which misses attendees who took part but neither pre-registered nor left an attributable response; an organizer who knows the true headcount can now set it directly.

The whole funnel is read from one function (`storage.event_registration_summary`, which `list_events` calls per event and the SSE stream/realtime push seed from), so the math changed in a single place and propagates to every surface — the `/monitor` index, the per-activity page, and the live stream.
- **`storage.py`** — new `event.respondent_target` column (nullable `INTEGER`, lightweight `ALTER TABLE` guard beside `created_by`), threaded through `_EVENT_COLS` + `_event_row` so it reaches every `get_event` caller. New `set_event_respondent_target(conn, event_id, value)` (stores a positive int, `NULL` clears). New `_completion_rate_target(numerator, target)` — `min(100, round(numerator*100/target))`, `None` when target falsy. `event_registration_summary` now branches: with a target set it returns `(completed + unattributed) / target` and `denominator_source="target"`; **with no target it keeps v1.94's default** `(completed + unattributed) / (registered + unattributed)` and `denominator_source="registered"`. It also returns `respondent_target`. Docstring notes the multi-form approximation (`unattributed` is a response-row count, so a walk-in answering two forms counts twice).
- **`app.py`** — new `POST /activities/{event_token}/respondents` (beside the window/dates editors, same `_can_manage_event` creator-or-admin gate). Blank clears; a non-integer or negative → `?err=badtarget`; a value **below** the current respondent count (`completed + unattributed`) → `?err=targettoolow` (nothing saved), so the rate can't be pushed past 100% at save time. Audits `event_respondent_target_set`. `_manage_ctx` now carries `reg_summary` so the editor can pre-fill and show the floor.
- **`templates/activity_manage.html`** — new `#respondents` manage card: number input pre-filled from `ev.respondent_target`, current-state line ("measured against N" vs "live registered count (N registered)"), and the two error flashes.
- **`templates/monitor_event.html` + `monitor.html`** — the completion-rate card appends "· of N expected" when `denominator_source == 'target'` (with a target-aware tooltip on the detail page that keeps v1.94's everyone-who-took-part copy for the default); the SSE handler updates that label live from the streamed `denominator_source` / `respondent_target` (already in the summary dict, so no payload change).
- **Tests** — `tests/test_monitor.py`: `test_respondent_target_overrides_completion_denominator` (default → 100, override 10 → 50 counting walk-ins, clear → back to default), `test_completion_rate_target_clamps_at_100` (unit incl. later-drift clamp and `None`), plus four route tests (set/clear/reject-badtarget, reject-below-actual, non-creator forbidden → `/e/{tok}`, admin on any). Storage + monitor/RBAC/event-link suites green; the three route-level failures under a fresh checkout are the pre-existing seeded-DB fixture gap (they reproduce identically on the base branch).

## 2026-07-13 (v1.94 — Monitor completion rate now counts everyone who took part, including the not-pre-registered)
Follow-up to v1.93's funnel work. The Monitor's "Completion rate" was computed over the pre-registered roster only — `completed / registered` — while walk-in / QR / paper responses were reported separately in the "Not pre-registered" card and never entered the rate. Per request, the rate now measures the share of **everyone who took part** who finished: the not-pre-registered responses are folded into **both** the numerator and the denominator, each counted as a completed submission (it is already an answer that came in).
- **`storage.py` `event_registration_summary`** — `completion_rate` is now `_completion_rate(completed + unattributed, registered + unattributed)`, i.e. `(completed + unattributed) / (registered + unattributed)`. Because the `unattributed` term appears in both numerator and denominator, the v1.93 invariant is preserved: the rate hits **100% only when every REGISTERED person has finished** (the extra term cancels), a near-complete event still reads 99, and a walk-in helps rather than dilutes. `_completion_rate(done, total)` is generalized from `(completed, registered)` to a `done`-out-of-`total` helper with the same `None`-when-empty / cap-at-99 behavior; it now returns `None` only when nobody took part at all (a pure-walk-in event that answered reads 100).
- **`templates/monitor_event.html`** — the "Completion rate" and "Not pre-registered" card tooltips and the explanatory note are reworded so the copy matches the new meaning (walk-ins count toward completion; 100% still requires all registered done).
- **Tests** — `tests/test_monitor.py`: `test_unattributed_responses_counted_separately` and `test_completed_never_exceeds_registered_with_walk_ins` updated to the new values (1 completed + 4 walk-ins → `(1+4)/(2+4)` = 83), plus a new `test_completion_rate_includes_not_pre_registered` locking in the include-not-pre-registered behavior and the "100% only when all registrants finish" guard. All 34 monitor tests green (the route-level `FileNotFoundError`s remain the pre-existing seeded-DB fixture gap).

## 2026-07-09 (v1.93 — Spot Feedback #63/#64: Monitor "Completed CSS" could read higher than "Registered"; funnel invariant enforced)
Two Spot Feedback items on the same Monitor page (`/monitor/05cf28a05990`, the headline stat cards): the "Completed CSS" figure could read *more than* "Registered" and jump on refresh (e.g. 41→42) (#64), and a registrant who had finished the survey showed as "Not started" (#63). Root cause of #64: the "Completed CSS" card was fed by **two different metrics**. The server render seeds it with `summ.completed` — registrants who answered every non-archived form (bounded by `registered`). But the live SSE stream (`/api/monitor/{token}/stream`), which the page's `EventSource` connects to a fraction of a second after load and on every new response, pushed `event_response_total(event_id)` instead — the **raw response-row count** across the event's forms, including unattributed walk-in / QR / paper responses and counting each row. So a moment after load the card was overwritten with the total-responses number, which can exceed `registered` and ticks on every walk-in. (Confirmed on the live event: 40 registered, 39 completed, **3 unattributed** → the old stream pushed 42, exactly the "41–42 / more completed than registered" reported. #63 is the attribution corollary — that one "Not started" registrant answered without her personalized `att` link, so her response is one of the 3 unattributed and her roster row stayed "Not started".)

The fix makes the whole funnel move as one authoritative unit, and pins the invariant *Completed ≤ Registered, and 100% only when they are equal*:
- **`storage.py` `_completion_rate(completed, registered)`** (new) — `None` with no registrants, exactly `100` only when `completed == registered`, otherwise `min(99, round(...))` so a near-complete event (199/200 = 99.5%) reads **99**, never rounding up to a misleading 100%. `event_registration_summary` now derives `completion_rate` through it. Since `completed` is a subset of the registrant roster, the rate is always in `[0, 100]`.
- **`app.py` + `realtime.py`** — the live channel now carries the **entire funnel dict** (registered / completed / in_progress / not_started / completion_rate / unattributed), not a bare count. `monitor_live_stream` seeds and streams `event_registration_summary(...)`; both `realtime.broadcast` sites (single-form and combined-QR submit paths) push the same summary; `realtime.broadcast(event_id, payload)` documents the payload. So "Completed" tracks registrants who finished — never the raw response total — and updates in lockstep with the "Registered"/"In progress"/"Not started"/rate cards.
- **`templates/monitor_event.html`** — each stat card carries an id; the SSE handler updates *all* of them together (and formats the rate `%` / `—`), so the display can never show Completed above the live Registered, or a rate over 100%, even when a new person registers-and-completes after the page loaded. (The removed `event_completed_count` helper from the first cut is superseded by streaming the full summary.) A new **"Not pre-registered"** card surfaces `summ.unattributed` — the walk-in / QR / paper responses that came in with no registration — as its own dashed-border figure (previously it lived only in the prose note), and it live-updates with the rest of the funnel. The note is reworded to point at the card rather than repeat the count (so it can't go stale on a live tick).
- **`app.py` `_build_monitor_xlsx`** — the roster export's funnel line now also carries "Not pre-registered (walk-in / QR / paper): N", so the downloaded XLSX matches the page.
- **Tests** — `tests/test_monitor.py`: `test_completed_never_exceeds_registered_with_walk_ins` (1 completed + 1 not-started + 4 walk-ins → `completed == 1 ≤ registered == 2` and `rate ≤ 100`, while `event_response_total == 6`, the number the old stream would have shown); `test_completion_rate_hits_100_only_when_all_registrants_complete` (unit cases incl. 199/200 → 99 and 40/40 → 100, plus an end-to-end 199-of-200 summary reading 99, not 100). Storage-layer monitor suite green (the route-level `FileNotFoundError`s are the pre-existing seeded-DB fixture gap and reproduce identically on the base branch).

## 2026-07-09 (v1.92 — individual person report download now carries the respondent comments too)
Follow-up to v1.91: the single-person report page (`/dashboard/people/<id>`) shows a comments panel on screen (`story_panel` over the person's response ids), but its **Download** button — the same `/dashboard/export?visual=person` path — was deliberately built to omit them ("a named-person file shouldn't carry them off-screen"). Since the on-screen page already shows them, the download now matches, using the same de-duplicated `×N` block as the per-activity and aggregate reports.
- **`app.py` `_visual_payload` (`visual == "person"`)** — attaches `payload["comments"] = {items, total, unique}`. The response ids are the union of this person's walk-in (`di.arta_slice`) and speaker (`di.rp_slice`) responses over the already-scoped `atoms` (the `a`/`r` slices computed for the date span) — the SAME rids the on-screen `dashboard_person` route feeds to `story_panel`. Flattened via `di._flatten_quotes` and de-duplicated via the existing `_dedup_remarks(..., cap=_COMMENT_CAP)`. Honors the period/single-activity scope. Stale "everything the page shows EXCEPT the verbatim quotes" comment updated.
- **`dashboard_docs.py` `person_pdf`** — adds a bottom "Respondent comments (N)" section (same shape as `event_pdf`: intro, one quoted `rd._comment_text(q)` line per unique, "…and N more" past the cap). Omitted when empty.
- **`dashboard_docs.py` `person_pptx`** — adds an "In their words" quotes slide after the methods slide (`rd._quotes_slide`, neutral column, `×N` on repeats). Omitted when empty.
- **`dashboard_docs.py` `METHODS_PERSON`** — the note that read "Verbatim comments are intentionally omitted from this file" now describes the included de-duplicated comments.
- **`dashboard_export.py` `_tables` (`visual == "person"`)** — adds a "Respondent comments" sheet (`Comment`, `Count`), most-repeated first. Omitted when empty.
- **Verification** — `tests/test_activity_report_comments.py` extended with 5 person-report tests (PDF heading/count + `×N` + empty-omit, PPTX "In their words" slide, XLSX `Comment`/`Count` sheet + empty-omit). Full suite: 582 passed, 3 failed — the same 3 pre-existing seed-dependent failures as v1.91, identical on the base branch.

## 2026-07-09 (v1.91 — per-activity report download now carries the respondent comments)
The single-activity report page (`/reports/activities/<id>`) shows a comments panel on screen, but its **Download** button goes through a different path than the v1.90 reports: it hits `/dashboard/export?visual=event&event_id=<id>&fmt=…` → `_visual_payload(visual="event")` → `dashboard_export.export` → `dashboard_docs.event_{pdf,pptx}` / `dashboard_export._tables`. That path was built "NO verbatims" and v1.90 never touched it, so every per-activity download (PDF/PPTX/XLSX) omitted the comments the page displayed. This wires the same de-duplicated comment block into that path.
- **`app.py` `_visual_payload` (`visual == "event"`)** — now flattens the activity's verbatims (`di._flatten_quotes(st.verbatims_for_responses(conn, ev["response_ids"]))`, the SAME source the on-screen `story_panel` reads) and runs them through the existing `_dedup_remarks(..., cap=_COMMENT_CAP)`, attaching `payload["comments"] = {items, total, unique}` — one flat `×N` list, since SERVQUAL comments aren't typed positive/negative. Stale "NO verbatims" comment updated.
- **`dashboard_docs.py` `event_pdf`** — adds a bottom "Respondent comments (N)" section before the Methods box: an intro line, one quoted line per unique comment via `rd._comment_text(q)` (appends `(×N)` only when `count > 1`), and an "…and N more unique comments" note when the unique count exceeds the cap. Omitted entirely when there are no comments.
- **`dashboard_docs.py` `event_pptx`** — adds an "In their words" quotes slide (reusing `rd._quotes_slide`) after the methods slide, feeding the top comments in a single neutral column (`rd._SOFTP`) with `×N` on repeats. Omitted when empty.
- **`dashboard_export.py` `_tables` (`visual == "event"`)** — adds a "Respondent comments" sheet (`Comment`, `Count`) after the "Who responded" table, most-repeated first. Feeds the XLSX and the PPTX table fallback. Omitted when empty.
- **Verification** — new `tests/test_activity_report_comments.py` (7 tests): the flatten+dedup source matches the on-screen verbatims (dup collapsed to `×2`, item-note kept, "none" dropped); the PDF story carries the heading/count, `×N` quotes, the overflow note, and omits the section when empty; the PPTX blob has the "In their words" slide; the XLSX has the `Comment`/`Count` sheet with the right count and is omitted when empty. Full suite: 577 passed, 3 failed — the 3 (`test_search::test_api_search_activities`, `test_audit_insights::test_audit_page_shows_friendly_labels`, `test_integrity::test_headline_counts_present`) are pre-existing and reproduce identically on the base branch (they need a richer seeded demo DB than a fresh clone's `setup_db.py` builds).

## 2026-07-09 (v1.90 — downloadable reports: de-duplicated respondent comments at the bottom, with ×N repeat counts)
The downloadable reports repeated identical free-text answers verbatim (and capped each ARTA bucket at 12, so a busy period both duplicated and truncated). They now collapse repeats into one counted entry and list them at the foot of the report.
- **`app.py`** — new `_dedup_remarks(items, cap)`: drops throw-away answers via `_meaningful_remark` (blanks, pure punctuation, "none"/"n/a"/"wala"/"ok"…), folds case + internal whitespace to group identical remarks, keeps the first-seen spelling, and returns `(grouped, shown_total, unique_total)` where each entry is `{text, count, type}` sorted by count desc then first appearance. So the listing carries only real feedback, with genuine repeats collapsed into one `×N` line. `test_comments_split_by_feedback_type` updated to assert throw-away answers are dropped; new `test_comments_deduplicate_with_counts` locks the fold + count.
- **`app.py` `_arta_comments`** — rewritten on top of the helper: still splits positive/negative/other, but each bucket is now de-duplicated and capped at `_COMMENT_CAP` (50) uniques, with per-bucket `_shown` (non-blank raw count) and `_unique` (distinct before cap) added, plus report-level `total`/`unique`. The old `limit=12` per-bucket slice is gone.
- **`app.py` `_servqual_official`** — attaches `block["comments"] = {items, total, unique}` built from each response's free-text `comment` via the same helper (one flat list — SERVQUAL comments aren't typed). Only DOCX/XLSX read it; PDF/PPTX ignore the key.
- **`report_docs.py`** — new `_comment_text(q)` renders `text  (×N)` only when `count > 1`. `arta_docx` now lists the full de-duplicated buckets with an "…and N more unique comments" note when a bucket exceeds the cap; `servqual_docx` gains a bottom "Respondent comments" section (it had none); `servqual_xlsx` gains a "Comments" summary sheet (distinct comment + count) beside the raw per-respondent column; `arta_pdf`/`arta_pptx` keep their curated few-quotes but feed from the de-duplicated list and show `×N`, with the PDF note pointing at the DOCX for the complete list.
- **Verification** — `tests/test_arta_report.py`, `tests/test_servqual_raw_responses.py`, `tests/test_report_activity_verbatims.py`, `tests/test_comment_bucketing.py` all pass; a direct render smoke confirms the ARTA DOCX/PDF/PPTX and SERVQUAL DOCX build and the SERVQUAL XLSX carries a populated "Comments" sheet with correct counts. (The `test_search.py` / `test_audit_insights.py` / `test_integrity.py` failures in the sandbox are pre-existing — they need a seeded demo DB absent from a fresh clone — and reproduce identically on the base branch.)

## 2026-07-09 (v1.89 — terminology: "activity report" → "customer satisfaction survey report"; "verdict" → "interpretation")
Renamed two user-facing terms across the interface and the downloadable reports. Display strings only — no logic, data-key, or stored-data changes: CSS classes (`.verdict`, `.jverdict`), the `_servqual_verdict` helper, dict keys (`servqual_verdict`, `d["verdict"]`), and template variables are untouched, so scores and saved responses are identical. The word "activity" as an *event* (create/manage/close activity, the Activities list, the "Activity / Event Satisfaction" report type) is a distinct concept and was left as-is — only the phrase "activity report" changed.
- **`app.py`** — the per-event report title fed to `dx.VisualMeta` (the header on the PDF/PPTX/PNG/XLSX export) is now `… — Customer Satisfaction Survey Report`.
- **`templates/reports.html`** — the "View individual … reports →" link now reads "customer satisfaction survey reports"; the consolidated SERVQUAL dimension table column header is now "Interpretation".
- **`templates/home.html`** — the home feed hover tooltip now opens "the customer satisfaction survey report".
- **`templates/activity.html`** — the satisfaction-journey card caption "overall verdict" → "overall interpretation" (the per-dimension "Interpretation" header was already in place).
- **`templates/team.html`** + **`dashboard_insights.py`** (`_confidence_note`, `confidence_phrase`) — the low-sample notes now say "an early hint, not an interpretation".
- **`report_docs.py`** — the Word (`.docx`) and Excel (`.xlsx`) SERVQUAL dimension table header "Verdict" → "Interpretation".
- **`dashboard_docs.py`** — the event PDF SERVQUAL dimension table header "Verdict" → "Interpretation".
- **`dashboard_export.py`** — the Excel export's SERVQUAL sheet column key "Verdict" → "Interpretation".
- **Verification** — `py_compile` clean on all edited modules; `tests/test_activity_report.py` passes. Rendered against a seeded demo DB: the activity report page and its `.xlsx`/`.pdf`/`.pptx` downloads show "Interpretation" (no "Verdict") and the "Customer Satisfaction Survey Report" title. (The `test_routes.py` failures in the sandbox are pre-existing — they need a delivered `css_is.db` fixture absent from the repo — and reproduce identically on the base branch.)

## 2026-07-09 (v1.88 — Spot Feedback #59: a closed activity lingered on the home "Ongoing" feed until the next day)
Closing an activity ("reporting is already closed") left it under "Ongoing — CSS collecting" on the home dashboard for hours. Two compounding faults in the home "ongoing" feeds' time test, both because the feeds reached for SQLite's `date/datetime('now','localtime')` instead of the app's canonical clock:
1. **Wrong timezone.** Every stored timestamp (`event_date`, `close_at`, `submitted_at`) is written in Asia/Manila via `tzutil` — precisely because the container runs in UTC (a Hugging Face Space; see `tzutil`'s own note). But `'localtime'` follows the *container* zone (UTC), so the feeds compared a UTC "now" against Manila-stamped `close_at` — an ~8 h skew that kept a just-closed activity "collecting" until UTC caught up.
2. **Separator mismatch.** `close_at` is ISO with a **'T'** (`…T08:57:40`); `datetime('now','localtime')` renders with a **space**. With `close_at` unwrapped, the compare was raw text, and on the same date `' '` (0x20) sorts before `'T'` (0x54), so `now <= close_at` stayed true all day.

(The public `/seq` form was unaffected: `_window_state` compares `_now_local().isoformat()` — Manila, 'T' — against `close_at`, so both zone and separator matched and the link closed on time. The bug was confined to the dashboard classification.)

The fix makes the feeds read the app clock, not the container's:
- **`storage.py`** — new `_local_now()` / `_local_today()` (thin `tzutil` wrappers). `upcoming_events`, `ongoing_events`, `ongoing_standalone`, and `ongoing_invited` now **bind** the Manila now/today as query parameters instead of `date/datetime('now','localtime')`, and compare `datetime(?) <= datetime(fi.close_at)` (the `datetime()` wrap also normalises `close_at`'s 'T' separator). `today_local()` and the two "event day has passed" checks (`event_css_done`, `list_shared_events`) likewise derive today from `tzutil`, so the whole lifecycle splits the day on the same Manila boundary everywhere.
- **`storage.py` `lifecycle_of`** — normalises both operands (`.replace("T"," ")`) before the text compare; its caller now passes a Manila `tz.now_iso()` (was `datetime('now','localtime')`).
- **Tests** — `tests/test_outside_activity.py`: pinning the app clock (`_local_now`/`_local_today`) either side of an 08:57 close flips `ongoing_invited`, proving it honours the bound Manila clock, not the container's `'localtime'` — the failure mode a past-date test (date part alone) never caught; `lifecycle_of` reads a same-day post-close now as concluded. Suite green (547 passed; pre-existing env-only failures unchanged).

## 2026-07-09 (v1.87 — Spot Feedback #60/#61/#62: an activity's freshly-encoded responses could vanish from the reports)
Three reports on one invited activity ("Reorientation to PK Excel Workbook and Live Encoding", event 10, 286 responses): its Manage page counted 286 responses and offered a "View resource-person results" link, but the Type-3 report showed "No responses in this scope", the 286 responses didn't appear, and the activity was missing from the report's Activity picker. The data was intact in the database — the responses had simply fallen out of the in-memory analytics cache (`atoms`), so every view built on that cache misbehaved (the Type-3 scope was empty; `build_events` **skips** an event whose cached responses total 0, which dropped it from the Activity picker and from `event_rp_results_url`'s target), while raw-SQL views like the Manage page's own counts still saw all 286.
Root cause: the atoms cache appends only answers past a stored high-water mark of `answer.id`. Every build path (`_build_blocking`, `_refresh_worker`, and the persisted-snapshot writer) read that mark with a **separate** `SELECT MAX(id)` taken *after* the frame was loaded. Any answer another connection committed in the gap between "load the frame" and "read the mark" landed *past* the frame but *under* the mark, so every later `a.id > mark` incremental append skipped it permanently. The throttled pickle then persisted the short frame under a count/max data-key that looked complete, and `_hydrate_atoms_from_pickle` reloaded it on each Space restart — making the gap sticky. A busy live-encoding session (this activity's answers, id 463078–466223) hit exactly that window; live Type-3 totalled 14,767 responses where a from-scratch load of the same DB totalled 15,053 — the difference was exactly event 10's 286.
- **`storage.py` `load_atoms`** — new `upto_answer_id` bound (loads `a.id <= that`). A build now snapshots the mark first and loads up to it, so the frame and the mark it's stored with cover exactly the same rows. The `upto`/`after` windows tile the answers with no gap and no overlap (old + delta == full).
- **`app.py`** — new `_answer_maxid(conn)` helper; `_build_blocking` and `_refresh_worker` snapshot the mark **before** loading and bound the load to it (full and incremental paths), removing the after-the-load `MAX(id)` read entirely.
- **`app.py` snapshot cache** — the sidecar now records the exact mark the frame was built to (`atoms-v2` format: tag + `repr(key)` + amax), and `_hydrate_atoms_from_pickle` restores the frame *with* that mark instead of re-reading `MAX(id)`. Bumping the tag also makes any older tag-less sidecar (including a short one left by the pre-fix path) fail to match, so a stale pickle is dropped and rebuilt clean on the next boot — self-healing the live gap on deploy.
- **Tests** — `tests/test_atoms_cache.py`: `upto`/`after` tile cleanly (`old ⊎ delta == full`); a commit that races the mark snapshot is deferred (behind the mark, out of the frame) and folded in by the next append, never stranded; the v2 snapshot round-trips the frame with its mark; a legacy sidecar is refused. Suite green (no new failures).

## 2026-07-06 (v1.86 — a still-open invited activity now shows on the home "Ongoing" feed)
An invited / "outside" activity (`event_kind='outside'`) is a set of Form-3 speaker reviews grouped under an event record, gathered through one combined `/seq` QR — it has **no Form 2**. The two home "Ongoing" feeds each excluded it by construction: `ongoing_events` filters `survey_type = 2` (it has none) and `ongoing_standalone` filters `ef.form_instance_id IS NULL` (it *has* an event record). Its only home was the "Your recent activities" strip, which drops anything more than 7 days past its `event_date` (`activities_by_creator(..., since_days=7)`). So an invited activity whose event was >7 days ago but whose `/seq` window was still open (`close_at` NULL or future — `_window_state` keeps the public form live) vanished from every home feed while still collecting responses: live to raters, unmanageable by its creator. Reported as a working combined-QR link that "doesn't reflect" under Upcoming/Ongoing/Recent.
- **`storage.py`** — new `ongoing_invited(conn, limit=20)`: one row per `event_kind='outside'` event that has started (`date(event_date) <= today`) and whose window is still open (`close_at IS NULL OR now <= close_at`, matching the public `/seq` form rather than the event-day-only rule the other feeds use for a NULL close). Collapses an activity's speaker forms to a single row carrying the event title, the total response count across its speakers, its speakers, and a `/activities/<token>/manage` link. Rows are shaped like the feed's standalone branch (`standalone=True`, `event_token=None`); `id` is a representative form id, which the inline-archive route already expands to the whole event.
- **`app.py` `home`** — the Ongoing feed is now `ongoing_events + ongoing_standalone + ongoing_invited` (still sorted newest-first). No template change: the existing standalone branch renders the new rows (response count + manage link), and no dedup is needed — the three feeds are mutually exclusive by shape.
- **Tests** — `tests/test_outside_activity.py`: `ongoing_invited` lists an open past activity as one collapsed manage-linked row; excludes a future (not-yet-held) one; excludes one whose window has elapsed; includes one with a future close; and end-to-end, the home page surfaces an open invited activity with its manage link. Full `test_outside_activity.py` green (22); suite green.

## 2026-07-06 (v1.85 — Spot Feedback #57: open a registrant's own response from the Monitor page)
The Monitor roster showed each registrant's CSS status but gave no way to see the response behind it. Feedback #57 asked for a click-through from a registrant to their actual ratings and comments. Read-only, back-office only, and scoped to registrants who answered via the link tree — anonymous walk-in/QR/paper responses (`attendee_id NULL`) are never attributable and never surface here.
- **`storage.py`** — new read-only `attendee_response_detail(conn, event_id, attendee_id)`: that registrant's responses to the event's non-archived forms (answers, per-item notes, overall verbatim). Only rows carrying the given `attendee_id` are returned. No schema change.
- **`app.py`** — new route `GET /monitor/{event_token}/attendee/{attendee_id}/response`, gated to the activity creator/admin (same gate as Monitor). Reuses `survey_spec` so wording and scale labels match what the rater saw (e.g. 5 → "Strongly agree", 4 → "Excellent"). The view is audited (`attendee_view_response`). A purged (identity-removed) registrant is shown as such with no answers surfaced.
- **`templates/monitor_attendee_response.html`** (new) + **`monitor_event.html`** — the CSS-status cell links to the new page only for answered, non-purged registrants.
- **Tests** — `tests/test_monitor.py`: only-own/attributed rows, N/A preserved, rendered answers + verbatim + item note, roster link present, creator-only redirect, purged identity hidden, audit entry written. Green.

## 2026-07-06 (v1.84 — Spot Feedback #54: third "Mixed" column on the Verbatims page)
The Verbatims drill-down (`/reports/verbatims`) rendered two columns (Appreciate / Improve) and credited a "Mixed" comment to **both** sides. Feedback #54 asked for Mixed to be its own column. Change is scoped to this one page — the seven other `story_panel` callers keep the mixed-on-both-sides behaviour, gated behind a new flag.
- **`dashboard_insights.py` `story_panel`** — new `split_mixed=False` param. When `True`, a mixed-sentiment quote routes to its own `mixed` bucket group instead of being duplicated across `appreciate`/`improve`. Return dict always carries a `mixed` group (empty unless split) — additive, so existing consumers are untouched.
- **`app.py` `reports_verbatims`** — calls `story_panel(..., split_mixed=True)`.
- **`templates/verbatims.html`** — three-column grid (`repeat(3, 1fr)`, stacks ≤1050px); new "Mixed — good and bad" column (accent-tinted); updated the explanatory copy / badge tooltips that said Mixed shows "on both columns".
- **Tests** — `tests/test_verbatims_mixed_column.py`: split routes mixed to its own group (and off the two sides); default keeps it on both with an empty mixed group; the page renders all three column headers. Green.

## 2026-07-06 (v1.83 — Spot Feedback #56: per-submission "Responses" sheet in the SERVQUAL Excel)
The Type 2/3 raw-data Excel (`servqual_xlsx`) carried only consolidated figures (Dimensions, Summary, Respondent profile) — no way to see the numbers behind them. Feedback #56 asked for "raw data or actual responses (disaggregated per submission) for each activity or resource person". Adds a per-submission sheet, honouring the report's existing activity/RP scope narrowing.
- **`app.py`** — new pure helper `_servqual_response_rows(df, dim_map)`: one row per `response_id` with that respondent's own per-dimension means (each answered item counted once per person), their overall (mean of their dimension means), expectation (item A) and overall service quality (item C). `_servqual_official` attaches `block["responses"]` (metadata merged in), ordered oldest→newest. **Additive** — only the XLSX extract reads the key; DOCX/PDF/PPTX and the on-screen report ignore it.
- **`storage.py`** — new `response_context_for_ids(conn, response_ids)`: submitted time + human activity name + response-level comment for **every** response (unlike `verbatims_for_responses`, which is comment-only), so comment-less rows are still labelled.
- **`report_docs.py` `servqual_xlsx`** — renders the new "Responses" sheet (`#`, Submitted, Activity, the five dimensions, Overall, Expectation (A), Overall SQ (C), Comment).
- **Tests** — `tests/test_servqual_raw_responses.py`: the pure per-response maths, the rendered XLSX sheet, and an end-to-end Resource-Persons download narrowed to one activity (one distinct row per submission; every row labelled). Green.

## 2026-07-05 (v1.82 — scheduled backup was ON but never fired: seed the anchor)
The admin Backups schedule was `backup_enabled=1` (daily 02:00) on live yet had **never run** — every `backup_run` audit row was a manual "Back up now", `last_backup_at` was empty, and zero `(scheduler)`/`auto` rows existed. Root cause: `next_due(cfg, "")` treats an empty `last_backup_at` as "measure from now", which always lands on the *next future* slot, so `is_due` is `False` at every hour (verified) — and a manual backup never sets `last_backup_at`, so the anchor that would break the deadlock is never seeded. The in-process `_scheduler_loop` ticked every 60s but `is_due` was perpetually false. (Data was never at risk: the separate persistence loop `_snapshot_to_bucket` still writes `_auto` snapshots continuously, and the v1.80 GitHub off-site layer is independent.)
- **`backups.py`** — new `ensure_schedule_anchor(conn)`: seeds `last_backup_at` to `_now()` when the schedule is enabled but has never recorded a run (idempotent; no-op when off or already anchored). Seeds to *now*, not a past slot, preserving the "no surprise immediate run" intent while letting the first real slot fire. `next_due`/`is_due` math is unchanged.
- **`app.py` `_scheduler_loop`** — calls `bk.ensure_schedule_anchor(conn)` each tick before the due-check, so the **currently stuck live state self-heals** on deploy (no admin re-save needed). Once anchored, "stays due" semantics mean a slot missed while the Space is asleep runs on the next wake (e.g. first morning login) rather than being skipped.
- **`app.py` `admin_backups_settings`** — also anchors right after `write_config`, so newly enabling the schedule from the UI is immediately effective.
- **Tests** — `tests/test_backups.py`: `test_empty_anchor_is_never_due_without_seeding` (documents the deadlock at every hour), `test_ensure_schedule_anchor_seeds_then_it_fires` (seed → set → idempotent → due-after-past-slot incl. sleep catch-up), `test_ensure_schedule_anchor_noop_when_disabled`. Full `test_backups.py` green (33).

## 2026-07-05 (v1.80 — off-site (GitHub) backup history on the Backups page)
The off-site daily backup was moved off the user's Windows PC (a 20:00 Task-Scheduler job that only ran when the machine was awake + plugged in, so most evenings it silently skipped) to a **GitHub Actions workflow** in the private `jongsky25/css-is-db-backups` repo (`.github/workflows/offsite-backup.yml` + standalone `offsite_backup.py`): daily `0 3 * * *` UTC, it logs into live, takes a fresh snapshot, downloads + integrity-checks it, GPG/AES256-encrypts it (same recipe as the old PC mirror, so README's decrypt cmd still works), and commits the ciphertext via an orphan force-push (flat history). This change surfaces that layer **inside the app** so an admin can confirm an off-HF copy exists without leaving to the GitHub Actions tab.
- **`app.py`** — new **`POST /offsite-backup/ping`**: a token-gated machine callback the workflow hits after a successful push. Public path (added to `_PUBLIC_EXACT`; CI has no session) but authenticated by `hmac.compare_digest` of the `X-Backup-Token` header against `CSS_OFFSITE_PING_TOKEN` (503 if the env var is unset on the Space, 401 on mismatch). Writes one `audit_log` row (`action=offsite_backup`, actor `(github-actions)`, `target_id`=filename, summary with human size + short SHA), returns 204. Added `import hmac`.
- **`app.py` `admin_backups`** — now also reads `st.list_audit(conn, action="offsite_backup", limit=10)` and computes `offsite_last` + `offsite_stale` (naive-local `datetime.fromisoformat` vs `_tz.now_local()`, >48h ⇒ stale), passed to the template.
- **`storage.py`** — `_AUDIT_ACTIONS["offsite_backup"] = ("Off-site backup to GitHub", "Data & backups")` so the Audit log reads it in plain English. (History is stored in `audit_log` — reused, so **no schema migration**.)
- **`templates/backups.html`** — new "Off-site backups (GitHub)" panel above Schedule: green "Off-site copy current" / amber "overdue" badge, a plain-language explainer, a >48h stale warning pointing at the Actions tab, and a table of recent pings (when · encrypted file · "GitHub · encrypted").
- **Secrets/infra (outside the app repo):** `CSS_OFFSITE_PING_TOKEN` set as a GitHub repo secret; the workflow's final step `curl`s the ping (best-effort — a failed ping never fails the job). ⚠️ Requires the **same `CSS_OFFSITE_PING_TOKEN` added to the HF Space variables** for pings to be accepted. The old Windows Task "CSS-IS daily prod backup" is disabled.

## 2026-07-02 (v1.78 — report link on a closed activity's Manage page)
Closes Spot Feedback #49 (ray — "when i close the activity, the report should be automatically generated"), a follow-on to the v1.76 close-now button. Interpreted as a *prominent report link* (the report already exists and stays live the moment responses arrive — no stored snapshot needed). Invited/outside activities already showed a "View resource-person results →" link in their closed banner; the gap was the regular (bureau) Manage page, whose closed state (added in v1.76) offered only Reopen.
- **`storage.event_report_url(conn, event_id)`** (new) — the kind-aware report link for an activity, or None if it has no live forms. Chooses by where the responses actually are (a cheap `EXISTS` per form), not merely which forms exist, so it matches what `build_events` renders and never points at an empty per-activity report: Form-2 side answered → `/reports/activities/{repr}`; answered only on the RP side, or Form-3-only → `/reports?type=3&activity={repr}`. `repr` = min(non-archived form_instance id), the id both report routes match (same basis as `event_rp_results_url`).
- **`app.py` `_manage_ctx`** — now carries `report_url` (from the helper) and `responses_total` (`event_response_total`).
- **`activity_manage.html`** — the closed branch of the "Stop accepting responses" card leads with a prominent filled **"View the report →"** button (gated on `report_url and responses_total`), with Reopen demoted to a ghost button beside it. The close redirect already lands on this `#danger` card, so the report is right there after closing.
- **Tests** — `tests/test_monitor.py`: `test_event_report_url_follows_the_responses` (Form-2-answered → activity report; RP-answered-only and Form-3-only → Type-3; no forms → None) and `test_closed_activity_manage_shows_report_link` (link hidden while open, shown on close with the correct URL). outside_manage's closed-banner link is unchanged and already covered. Full suite green.

## 2026-07-02 (v1.77 — RP results from home + Type-3 Excel + remove a stray registrant)
Closes three Spot Feedback items, all orbiting the invited HRH PK Reorientation activity (event id 2, Form-3-only, 328 responses): #48 (ray — "why can't i still see the report for this?"), #44 (vcdulfo — "where's the excel option" on `/reports?type=3`), and #45 (vcdulfo — "is it possible to delete an entry?").
- **#48 — `app.py` home "concluded" feed.** An f2-less (invited / resource-person) activity linked to the generic `/activities/outside` list, so "open the report" never showed its numbers. Now it links to `/reports?type=3&activity={e['id']}` — the Type-3 report narrowed to that activity (`e['id']` is the build_events representative id, exactly the Type-3 Activity filter value; same target as `event_rp_results_url`). The feed filter already guarantees an f2-less row here has responses, so the link always has something to show. `home.html` tip updated ("Open the resource-person results"). Test `test_recently_concluded_links_resolve` rewritten to assert the invited branch links to the Type-3 report and that it's actually exercised by the delivered DB.
- **#44 — Type-3 raw-data Excel.** `report_docs.servqual_xlsx(sq, meta)` (new) renders the consolidated SERVQUAL payload — dimensions (Mean as a real number so the sheet is computable, plus the gap/verdict strings), the SERVQUAL summary, and the respondent profile — one table per sheet. `app.py`: added `xlsx` to `_REPORT_FMT`; `/reports/export` now dispatches `servqual_{fmt}` for `fmt=xlsx` on Type 2/3, and coerces a stray `type=1&fmt=xlsx` to docx (ARTA has no servqual_xlsx). `reports.html`: a "Raw data → Excel (.xlsx)" link in the Type-3 download menu (honors the org/period/activity scope). Tests: `test_reports_type3_xlsx_export`, `test_reports_type1_xlsx_coerced_to_docx`.
- **#45 — remove a registrant entry.** `storage.delete_attendee_entry(conn, event_id, attendee_id)` hard-deletes a roster entry **only when it has no responses** (returns `('ok'|'notfound'|'hasresponses', n)`). Deliberately NOT a response delete: `response`/`answer` are append-only under the durability high-water guard (`backups._HIGHWATER_TABLES`, MAX(rowid)), and a responded entry's ratings belong to the reports — same rule as "can't remove a speaker that has responses". Route `POST /monitor/{token}/attendee/{id}/delete` (creator/admin gate, audit `attendee_delete`, flash redirect); `monitor_event` takes a `flash` param. `monitor_event.html`: per-row "Remove" button (confirm) shown only when `not p.n_answered`, plus a flash banner + `.act-btn.danger`/`.flashmsg` styles. Tests: `test_delete_attendee_entry_rules`, `test_monitor_delete_attendee_route`, `test_non_creator_cannot_delete_attendee`.

## 2026-07-02 (v1.76 — close-now for every activity + "open until" on Monitor)
Closes Spot Feedback #46 (vcdulfo@doh.gov.ph — "how to close the survey without waiting for the end of window period") and #47 ("put details on until when it is open"). The close/reopen machinery already existed (`storage.close_event_now`/`reopen_event_now`/`event_is_closed`, v1.62) but was reachable only by invited ("outside") activities — the two POST routes gated on `_get_outside_event` (which enforces `event_kind == "outside"`), and only `outside_manage.html` rendered the buttons. A link-tree activity could only be stopped by hand-setting the window's "closes" date. The storage layer is already kind-agnostic (it joins `event_form`), so this is a surfacing change, not new mechanism.
- **`app.py`** — new `_get_manage_event` helper (get_event + `_can_manage_event`, no kind check; mirrors `_get_outside_event`'s (ev, None)/(None, redirect) shape). Renamed the two routes `outside_close`/`outside_reopen` → `activity_close`/`activity_reopen` (audit actions `event_close`/`event_reopen`) and pointed them at the new helper, so **any** activity's creator/admin can close/reopen. `_manage_ctx` now carries `is_closed`. The regular `monitor_event` render now passes `entry_window` + `is_closed` (read while the conn is open, before the finally).
- **Templates** — `activity_manage.html`: new "Stop accepting responses" card (id `#danger`, the anchor the routes already redirect to) with a **Close survey now** button (JS confirm) that swaps to **Reopen to make a correction** once closed — mirrors the outside-manage wording. `monitor_event.html`: a status line under the title — "Open until <date>" / "Open — no closing date set" / "Closed".
- **Tests** — `tests/test_monitor.py` (3 new: link-tree close↔reopen cycle + the manage button swap; ownership gate on close; the Monitor "open until"→"Closed" surface). Existing `tests/test_outside_activity.py` close/reopen tests still green against the generalized routes. Full suite green.

## 2026-06-30 (v1.75 — comment raffle now supports online activities)
Closes Spot Feedback #41 (ray@gmail.com — "online activities should also have a raffle draw"). The comment raffle (v1.47) was hard-gated to face-to-face responses, even though its claim-code identity model — built for anonymous walk-ins — already fits online entrants exactly: an online respondent sees a code on their thank-you screen and presents it (e.g. in chat) to claim. The fix removes the modality gate in all three places it appeared; no schema or new identity mechanism needed.
- **`storage.py` `raffle_pool`** — dropped the `COALESCE(fi.modality,'f2f')='f2f'` filter, so an online response with a real comment is now an eligible entry (still excludes archived forms, no-comment responses and demographic-only notes). Docstring + the two raffle section comments updated.
- **`app.py`** — both submit handlers (single-form `submit` and combined `/seq`) previously issued a claim code only when `ctx.modality == 'f2f'`; now they issue it whenever the activity's raffle is on, so online raters get their ticket on the thank-you screen. Section comment broadened.
- **Templates** — copy de-scoped from "face-to-face" on `activity_manage.html` / `outside_manage.html` (the raffle card hint) and `raffle.html` (the empty-pool message, server- and client-side). The raffle card was already shown for online activities — only the wording implied otherwise.
- **Tests** — `tests/test_raffle.py`: flipped `test_pool_excludes_online_responses` → `test_pool_enters_online_responses` (online comments now pooled), added `test_thanks_shows_claim_code_for_online_submission` (online `/seq` thank-you renders a 5-char code), updated the module docstring. Full `test_raffle.py` green (18); full suite green.

## 2026-06-30 (v1.74 — inline Archive on the home "Ongoing" feed)
Closes the discoverability gap behind Spot Feedback #42/#43 (ray@gmail.com — two "archive. test data" notes filed from the home Ongoing strip). Archiving an activity already worked from several places (the Recent-activities strip for standalones, the invited-activity manage page, and the `/reports/activities` Edit/merge bulk action), but NOT from the read-only "Ongoing — CSS collecting" feed where a stray/test activity is most often spotted — so it read as "no way to archive from here". This adds the control where the feedback was filed.
- **`app.py`** — new route `activity_inline_archive` → `POST /activities/instance/{fid}/archive` (`create_activity`-gated). Resolves the feed row's form-instance id to the right scope: a row backed by an `event_form` archives EVERY form the event bundles (the Type-2 review + its speaker Type-3s) so the whole activity leaves the feeds; a standalone form archives just itself. Reuses the harmonize journal (`aa.ensure_backup()` + `aa.new_batch()` + `aa.archive_activities`, same auto-backup + per-change undo as the Edit/merge bulk archive), then `invalidate_atoms()`. Redirects home.
- **`templates/home.html`** — each Ongoing row is now wrapped in the existing `.mine-row` flex shell for admins (`mine_all`), with an inline `.mine-arch` Archive form beside the link (confirm dialog; reuses the same CSS as the Recent-activities strip's Archive button — no new styles). Admin-only; the route itself still enforces `create_activity` as defence in depth.
- **Tests** — `tests/test_home_feeds.py` (3 new: standalone archive from the feed hides the row; bureau-event archive covers every bundled form; a viewer is blocked by the permission gate). Full suite green.

## 2026-06-26 (v1.73 — durability: persist-loop watchdog + honest /ops stall detection)
Closes the two blind spots behind a live durability incident (2026-06-26): the background persist loop had stopped saving for ~5h while `/ops` still showed green. Root cause — a snapshot worker hung on bucket (FUSE) I/O froze the loop, so the recorded state stayed at the last `ok` forever (no skip/fail recorded → card never went red). No data was lost (live held the richest copy + was pulled off-site); fixed live via Back-up-now → Restore (`reset_highwater`) → restart. These changes prevent recurrence. Full incident record in the `hf-staging-data-loss` memory note.
- **`app.py` `_persist_loop`** — each snapshot attempt is now bounded by `CSS_PERSIST_OP_TIMEOUT` (default 30s) via `asyncio.wait_for`, so a stalled bucket write can no longer wedge the loop forever; on timeout it records a `fail` (→ /ops red) and keeps ticking. Added a per-tick monotonic **heartbeat** (`last_tick_mono`) written at the top of every iteration, and unified the "last saved data_version" into `_PERSIST_HEALTH["saved_ver"]` so the health view can tell whether live has unsaved changes.
- **`app.py` `_persist_health_view`** — now flips the /ops durability card **RED independently of the recorded state**: if the loop has stopped ticking, OR unsaved changes have gone unwritten, for longer than `CSS_PERSIST_STALL_TICKS` ticks (default 5). This is what was missing on 2026-06-26 — a frozen `ok` state read green while nothing was being saved.
- **`backups.py`** — new pure `persist_is_stalled(...)` (the testable stall rule: loop-not-ticking OR unsaved-too-long, with a `last_tick is None` → not-stalled guard so a just-booted app isn't flagged). Note: a timed-out worker thread may still be stuck on the syscall, but the loop survives and reports — degrading to "loop alive + card red" instead of a silent freeze.
- **Tests** — `tests/test_backups.py` (4 new: `persist_is_stalled` not-before-first-tick / loop-stopped-ticking / unsaved-unwritten / never-saved-window) + new `tests/test_persist_health.py` (4: card green when healthy, red when the loop stops ticking, red when unsaved changes go unwritten, hidden when persistence off). Full suite green.
- **Follow-up still open:** a true bucket lock for the sub-second split-brain window (what advances the high-water mark above a surviving snapshot in the first place) — unchanged from before.

## 2026-06-26 (durability — high-water guard now protects login accounts)
Root-cause of the "user accounts/passwords reset on update" report. Persistence itself is healthy (the live Space mounts the durable bucket `equityinhealth/office-connect-data` at `/data`; the persist loop self-snapshots and the newest snapshot holds all current accounts — verified). The realized resets traced to a snapshotter **wedge** (a ~2-day gap in bucket snapshots, June 23→25 — the same incident as the June-24 loss): while wedged, the newest *valid* snapshot goes stale, so a deploy/restart during the stall restores stale state and accounts revert. The v1.63 self-heal (orphaned-high-water realign) + pre-deploy backup gate already address the wedge; this closes the account-specific blind spot.
- **`backups.py`** — added `admin_user` to `_HIGHWATER_TABLES`. The boot stale-view guard (`_await_fresh_snapshot`) and the persist-loop guard (`live_db_is_stale`) only tracked survey/audit/feedback tables, so a new account/password (which touches *only* `admin_user`) left the high-water mark unchanged — a stale FUSE view could restore a pre-account snapshot and the guards wouldn't notice. Now an account change advances the mark, so such a restore is caught (crash-loop + self-heal) instead of silently resetting accounts. Safe because production never hard-deletes accounts (deactivation = `UPDATE active=0`, rowid unchanged → monotonic).
- **Tests** — new `tests/test_backups.py::test_highwater_protects_accounts` (real, un-patched `_HIGHWATER_TABLES`): an account-only insert advances the mark and a snapshot predating the account reads as stale. Full `tests/test_backups.py` green (24).
- **`report_docs.py`** — guarded a pre-existing None-gap crash surfaced by the pre-deploy test gate: `_na_sq_summary` + two PPTX builders did `g['label'].lower()` under only an `if g:` check, but a partial Form-2 activity (perception rated, expectation item A blank) yields `gap={'label': None, …}` (truthy) → `AttributeError` that 500'd the event PDF/DOCX/PPTX export. Now guarded `if g and g.get("label")` (same "None gap = neutral" treatment as the v1.69 activity.html fix). Unblocked `test_routes.py::test_dashboard_event_export_all_formats`; full suite green.
- **Shipped together** as part of the v1.72 deploy (the staged RP-activity-filter release). A pre-existing stray `_backups/scheduled/css_is_20260625_100908_auto.db-shm` sits in the bucket — harmless (ignored by the snapshot name regex), noted not deleted.

## 2026-06-25 (v1.69 — Invited-activity → RP-results deep link + activity-report None-gap fix)
Two changes. (a) Non-bureau RP-CSS navigation (spec `docs/OUTSIDE_RP_RESULTS_NAV_PLAN.md`): an outside activity is Form-3-only, so it has no Form-2 SERVQUAL report — its scores live only in the Type-3 report's Activity filter (v1.65), with nothing linking there from the activity. (b) A latent 500 on the per-activity report for partial Form-2 data.
- **`storage.py`** — new `event_rp_results_url(conn, event_id)`: returns `/reports?type=3&activity=<min non-archived form_instance id>` (= the `build_events` representative id the Activity filter matches, NOT `event.id`), or None when the event has no live RP forms.
- **`app.py`** — `outside_events_index` attaches `e["rp_results_url"]` per outside event. `_outside_manage_ctx` `report_url` switched from `/reports/activities/{ev['id']}` (404'd for ALL outside events — f2-less AND event.id ≠ build_events id) to `event_rp_results_url`.
- **`templates/outside_events.html`** — new "View resource-person results" action link (shown when `rp_results_url and responses`). **`templates/outside_manage.html`** — the closed-bar link relabelled "View resource-person results →", guarded on `report_url and responses_total`.
- **`templates/activity.html`** — the dimension-table gap cell guards `d.gap is none` → neutral 'zero' class (was `None > 0.005` → `TypeError`, 500-ing the report when a Form-2 response answered perception items but not the expectation item A; `gap_shown` already rendered "—"). Only the one template line had this unsafe comparison.
- **Known build_events quirk (noted, not fixed):** an F3-only outside event is named after its first F3 topic, not the event title — so the Invited-events page (event title) and the RP report it links to (F3 topic) can label the same activity differently.
- **Tests** — `tests/test_outside_rp_results_link.py` (4: helper min-id/excludes-archived/None; page link responses-gated; linked id narrows the report; manage page links to RP results not the 404 report) + `tests/test_activity_report_none_gap.py` (1: perception-only F2 renders 200 with a "—" gap). Updated `test_outside_activity::test_close_hard_locks...` (asserted the old broken link). Full pytest 515 green.

## 2026-06-25 (v1.68 — Invited/outside-event visibility: dedicated list + home "Recently concluded" + Invited badge)
Addresses Spot Feedback #29/#30 (non-bureau activities missing from the home strip / Monitor) and the root cause behind a "missing" June-17 invited activity (data was always intact; it was a visibility gap). A concluded outside event used to fall off every dashboard surface except `/reports/activities`: the Monitor is lifecycle-filtered to upcoming/ongoing, and the home "Recently concluded" strip was Form-2-only (outside events are often Form-3-only). Spec: `docs/OUTSIDE_EVENTS_VISIBILITY_PLAN.md`. Three layers, all reuse the existing `lifecycle_of` / `build_events` — no storage-layer change.
- **Layer ① — dedicated page.** New `app.py` route `outside_events_index` → `GET /activities/outside` (`manage_event`-gated; admin sees all, section_manager sees own). Lists ALL outside events across every lifecycle via `st.list_events(created_by=owner)` (no lifecycle filter) filtered to `event_kind=='outside'`, each enriched with `st.event_response_total`. New `templates/outside_events.html` (lifecycle badge + "Invited" badge + response total; links to Manage/Monitor by token — NOT the report, since `/reports/activities/{id}` 404s on f2-less events and build_events uses a synthetic id ≠ event.id). New nav item key `outside` ("Invited events") under Manage in `NAV_GROUPS` (also feeds the Ctrl-K search index). `templates/monitor.html` invited section now links concluded ones to the page.
- **Layer ② — home "Recently concluded".** `home()` concluded filter relaxed from `e.get("f2")` to `(f2 OR respondents)`, so invited/F3-only activities with responses appear. Each item now carries `url` (report for f2 events, else `/activities/outside`) + an `invited` flag; `home.html` concluded JS uses `a.url` and renders an amber "Invited" badge. `tests/test_home_feeds.py::test_recently_concluded_links_resolve` updated to follow each item's `url` (the old contract assumed every concluded id → a report).
- **Layer ③ — badge + monitor hand-off.** Amber "Invited" badge on the home "Your recent activities" strip (`home.html`, keyed on `a.event_kind=='outside'`, already carried by `activities_by_creator`). DECISION: KEPT the 7-day "Your recent" window (the deliberate v1.10 narrowing) rather than widening to 30 — ①/② already give invited events their homes.
- **Tests** — new `tests/test_outside_events_page.py` (5: concluded invited event shows here but NOT on the Monitor; upcoming shows; scoped to outside-only; auth gate; home strip badge) + `tests/test_home_concluded_invited.py` (2: invited F3 appears + links to the list; real bureau f2 events keep their report link). Full pytest exit 0.
- **Known latent bug (out of scope, flagged separately):** `templates/activity.html:274` 500s on a None Form-2 dimension gap (partial responses); real data renders fine today.

## 2026-06-25 (v1.67 — Audit log: plain-language actions + a "what's been happening" breakdown)
Addresses Spot Feedback #27 (ray@gmail.com) — "a bit of an insight on the audit log would do good? plan". v1.60 had already added the at-a-glance counts (today / week / all-time / busiest / most-common); this makes the log itself readable to a non-technical admin and adds the recent-activity distribution.
- **`storage.py`** — new `_AUDIT_ACTIONS` map (≈60 codes → `(label, category)`), `audit_label(code)` (plain English; **humanize fallback** for any unmapped/new code so it's never blank), and `audit_category(code)` (→ "Other" when unmapped). New `audit_breakdown(conn, days=7, top=6)`: ranked action types (`by_type`, each with label + category + count + bar `pct`) and busiest actors (`by_actor`) over the PH-local window; returns None for an empty window. `audit_insights` now also carries the friendly `label` on its `common`/`last` entries.
- **`app.py`** — registered Jinja filters `audit_label` / `audit_category`; `admin_audit` route now also passes `breakdown`.
- **`templates/audit.html`** — the entries-table action chip now shows the friendly label (raw code kept as the `title=` tooltip + still the filter value, so filtering/forensics are unchanged), tinted by a coarse category grouping (blue = sign-in/feedback · amber = accounts/data/sharing · green = activities/comments/directory · neutral = other), all token-backed/dark-mode safe. The at-a-glance "most recent"/"most common" lines use labels; the filter dropdown lists friendly names (raw value preserved). New "What's been happening · last 7 days" panel: ranked action kinds with count bars + busiest people. Decorative bars are pure CSS; no new color tokens.
- **Scope:** read-only presentation + aggregation over the existing `audit_log`; no schema change, no change to what gets recorded or to the hash-chain integrity check. `/admin/audit` stays admin-gated.
- **Tests** — new `tests/test_audit_insights.py` (5): `audit_label` known + humanize-fallback + empty; `audit_category` incl. unmapped→"Other"; `audit_breakdown` ranks types/actors with labels and a full top bar over the 7-day window; empty-window → None; the page renders the friendly "Signed in" label. Full pytest exit 0.

## 2026-06-25 (v1.66 — /ops: live "who's using it" + "lately" reads)
Addresses Spot Feedback #26 (ray@gmail.com) — "plan for additional layman data. like current users? etc…" on `/ops`. v1.60 had added static all-time inventory counts; this adds the live "who's on the system" + recent-activity signals those counts don't give. No schema change — derived from the audit log (sign-ins) and existing timestamp columns.
- **`storage.py`** — new `usage_pulse(conn)`: from `audit_log` it returns `active_now` (distinct actors with ANY audit action in the last 15 min — a soft presence proxy, since there is no live session store), `signed_in_today` / `signed_in_week` (distinct `action='login'` actors, PH-local windows), `last_login`, and `recent_logins[]` (last 6). From the cheap timestamp columns it returns the "lately" deltas: `responses_today` / `responses_week` (`response.submitted_at`), `activities_week` (`event.created_at`), `participants_week` (`attendee.created_at`). All naive-local stamps, so `date(ts)` and lexical `>=` stay correct (tzutil strips tzinfo — no UTC-shift). Cheap COUNT/GROUP, computed on demand.
- **`app.py` `ops()`** — calls `st.usage_pulse`; builds two plain-language card rows (`people`, `lately`), a `last_login_line`, and a `recent_logins` list (timestamps via `_humandt`), passed to the template.
- **`templates/ops.html`** — two new `.panel`s after "What's in the system": **"Who's using it · sign-in activity"** (the people cards + "Last sign-in:" line + a recent-sign-ins list) and **"Lately · last 7 days"** (the freshness cards). Reuses the existing `.signals`/`.sig` card styles (dark-mode safe); one small `.signins` list style added; the recent list carries an `aria-label`. "Active now" is labelled "in the last 15 min" so it never overpromises real-time presence.
- **Privacy/scope:** `/ops` is `manage_users`-gated (admins only) and `/audit` already shows actor names, so surfacing sign-ins here adds no new exposure. Deliberately NOT adding a session/heartbeat store — the 15-min audit-activity proxy is the honest signal without new infrastructure.
- **Tests** — new `tests/test_ops_usage.py` (4): `usage_pulse` window arithmetic (active-now vs stale vs today vs week, distinct-actor counting, newest-login ordering), the "lately" 7-day deltas, the empty-system zero case, and that `/ops` renders the new panels for an admin. Full pytest exit 0.

## 2026-06-25 (v1.65 — Resource-person report: filter by a single activity)
Addresses Spot Feedback #28 (gbcanoy@doh.gov.ph) — "filter RP Responses by Activity … to quickly locate and review responses for a specific activity." The Type-3 (Resource Persons) report at `/reports?type=3` previously scoped only by Scope (org) + Period; there was no way to isolate one activity.
- **`app.py`** — new `_rp_activity_options(conn, atoms)`: reuses the memoized `di.build_events(...)` (same source as `/reports/activities/{id}`) to list events that carry resource-person (F3) data, each with its `instance_ids`. So the dropdown labels/ids match the rest of the activities views.
- **`app.py` `reports()`** — new `activity` query param (RP-only; coerced to `""` for types 1/2). When set, the atoms fed to `eng.scope(..., survey_type=3)` are narrowed to that event's form instances *before* scoping, so the overall score, per-dimension grid, respondent count and verbatims all reflect the one activity. `activity_opts` + `sel_activity` are passed to the template; the selected activity's name is appended to `scope_label`.
- **`app.py` `reports_export()`** — same `activity` param threaded through for download parity (Word/PDF/PPTX), narrowing the same way and reflecting the activity in the document's scope line.
- **`templates/reports.html`** — an "Activity" `<select>` (default "All activities") added to the filter bar, shown only for `rtype == 3`; auto-submits like Scope/Period and is carried on the existing filter form so it composes with org/period. `report_downloads(...)` macro gained an `activity` arg and threads `&activity=` into each export link (Type-3 call site passes `sel_activity`).
- **Scope/composition:** the Activity filter stacks with Scope + Period (intersection); switching report type via the tabs drops it (the tab links don't carry `activity`). Backlog activities not in the `event` table follow build_events' existing grouping, same as every other activities view.
- **Tests** — new `tests/test_rp_report_filter.py` (2): two bureau activities with distinct response counts → the dropdown lists both, selecting one narrows the report to exactly its respondents (3 vs 2) and marks the option selected; a stray `activity` param on Type 1/2 is ignored (200, no narrowing). Full pytest exit 0.

## 2026-06-25 (v1.63 — persistence self-heal for the orphaned-high-water deadlock + loud /ops durability health)
**Incident (2026-06-25, diagnosed from live container logs).** A ~2-day SILENT persistence outage lost June 24 data (CSS responses + activities + Spot Feedback #28–37). Live logs showed `[persist] SKIP snapshot (timer): live DB is BELOW the high-water mark …` repeating non-stop: the v1.61 stale-lineage guard was WEDGED. The bucket's monotonic high-water mark (HWM) had been advanced ABOVE every surviving snapshot (a split-brain peer raised it, then its snapshot was lost/reverted), so the live container — booted from the best surviving (lower) snapshot — was permanently "stale" and refused to EVER auto-snapshot. Manual `make_backup` bypasses the guard (how the recovery snapshots succeeded) but `write_highwater` is monotonic, so it couldn't lower the mark; only a deliberate restore (`reset_highwater`) could. A deploy restart then restored the last good (June 23) snapshot and finalised the loss. Distinct from v1.55 (seed-revert) and v1.61 (stale-but-valid SNAPSHOT revert): here NO snapshot was written for ~36h, silently.
- **Immediate (no deploy):** unblocked live by scripting Back-up-now → Restore (calls `reset_highwater`), realigning the mark down to current data; a fresh `_auto` snapshot appeared 2 s later, confirming the loop resumed.
- **`backups.py`** — new pure `persist_action(live_marker, best_snapshot_marker, highwater)` → `ok` / `skip` / `realign`. `skip` only when a snapshot strictly RICHER than live exists (the original protection is intact); `realign` when live is below the mark but NO snapshot beats it = the mark is orphaned.
- **`app.py` `_snapshot_to_bucket`** — uses `persist_action`: on `realign` it `reset_highwater(DB)` + snapshots (self-heals the deadlock within one ~60 s tick) instead of skipping forever; on `skip` it still protects the good backup. New `_PERSIST_HEALTH` + `_persist_note()` track last-ok / state / consecutive-bad.
- **`app.py` `/ops`** — `_persist_health_view()` adds a plain-language "is live data being saved right now?" line to the System-health "is the data safe?" list, and a `down` state escalates the overall verdict to RED — so a silent outage is now impossible to miss.
- **`deploy_hf.py`** — NEW pre-deploy redundant-backup gate (separate, already in place): forces + verifies a fresh live snapshot before the upload/restart, aborts if it can't (`--skip-backup` / `CSS_DEPLOY_SKIP_BACKUP=1` override).
- **Recovery tooling (local-only, NOT shipped):** `refile_lost_feedback.py` re-POSTed Spot Feedback #28–37 to live (annotated `[RECOVERED …]`; live back to 37). June 24 survey responses + activities are unrecoverable (in no snapshot). Lost-feedback text saved at `_backups/LOST_feedback_28-37_captured_2026-06-25.md`.
- **Tests** — `tests/test_backups.py` +3: `persist_action` ok/skip/realign rule table. Full pytest exit 0.

## 2026-06-25 (v1.62 — closing an invited activity is now a real hard-stop: locks entry + details, surfaces report)
Addresses a Spot Feedback cluster (#31 "concluded events should not be editable", #33 "[Close] should deactivate + generate reports", #34 "closed but input fields still open") on invited/outside activities. Before, `Close` only set `close_at` (gating the public link); paper entry via `/encode` was never enforced, and the manage page stayed fully editable.
- **State model (no migration):** "closed" = every non-archived form of the event carries `encoding_locked=1`, set alongside `close_at` by `close_event_now`. Reused existing columns. Decision: gate paper entry on the explicit `encoding_locked` signal, NOT a merely-elapsed window — so legitimate back-keying of never-formally-closed events is preserved (no surprise regression on link-tree events).
- **`storage.py`** — `close_event_now` now also sets `encoding_locked=1` (hard-stops paper entry + drops the form from the encode picker, which already filters `encoding_locked`). New `reopen_event_now` (clears `close_at` + `encoding_locked`) and `event_is_closed` (true iff ≥1 non-archived form and all are locked). `get_form_context` now returns `encoding_locked`.
- **`app.py`** — new `POST /activities/{event_token}/reopen` (outside-event guarded, audited as `outside_reopen`). `_outside_manage_ctx` adds `is_closed` + `report_url` (`/reports/activities/{id}`). `submit_encode` now refuses a locked form (409, re-renders the form in its locked state) — server-side teeth for the data-integrity path. `encode_form` GET passes `locked`.
- **`templates/encode_form.html`** — locked forms show a red "this activity is closed" notice and the entry form is replaced by a back-link (no submit). The old window-closed "paper entry still allowed" note is retained for the elapsed-window-but-not-locked case.
- **`templates/outside_manage.html`** — when closed: a top banner with **View activity report →** + **Reopen to make a correction**; the editable cards (speakers, dates, window, raffle) are wrapped in a `[inert]` `locked-region` (dimmed, non-interactive) with a 🔒 flag; the danger-zone Close button is swapped for an "already closed → use Reopen" note. Close confirm copy updated to say it locks details + paper entry. (Manage-field lock is client-side `inert`; the actor is the authorized creator/admin and Reopen is one click, so no per-route server guard was added — the paper-entry block, which is the integrity-critical surface, IS server-enforced.)
- **Scope:** outside/invited activities only (the `/manage` Close button is outside-only). Link-tree activities are unaffected unless globally locked via the existing admin "Close all to encoding".
- **Tests** — `tests/test_outside_activity.py` +2: close hard-locks paper entry (encode GET shows locked state, POST → 409, records nothing) + flags `event_is_closed` + manage page shows banner/report-link/Reopen/inert lock and drops the Close button; reopen reverses it (entry accepted again). Drive-by: fixed a date-drift time-bomb in `tests/test_my_activities.py::test_home_renders_the_strip_for_its_creator` (hardcoded `2026-06-16` had fallen outside the home strip's 7-day window now that "today" is past it → now dates relative to `_today_local()`). Full pytest exit 0.

## 2026-06-22 (v1.56 — read-only Spot Feedback JSON endpoint + local `feedback.py` reader)
Closes the "download the whole DB just to read feedback" loop. Live data lives on the HF bucket (not reachable via the HF API), so reviewing Spot Feedback meant pulling the 21 MB DB from `/admin/backups` by hand. New thin path lets the current feedback be read from a local tool with no download.
- **`app.py`** — new `GET /admin/feedback.json` (gated by the existing `triage_feedback` permission, read-only, mutates nothing). Returns `{generated_at, statuses, counts, total, filter, items[]}`; each item carries `id/created_at/updated_at/submitter/status/page_url/element_selector/message/admin_note/archived_at` plus its `updates[]` reply trail (reuses `st.list_spot_feedback` + `st.list_feedback_updates`). Optional `?status=` filter. Region blob intentionally omitted (noisy).
- **`feedback.py`** (NEW, local-only — NOT in deploy_hf ALLOW, never ships) — logs in via `pull_backup`'s session machinery, GETs the JSON, prints a readable digest (`--json` for raw, `--status`, `--open` to hide Done/Won't-fix). Creds resolve flags → env → gitignored `.env.local` → prompt.
- **`.env.local`** (NEW, gitignored) — holds `CSS_ADMIN_USER`/`CSS_ADMIN_PASS`/optional `CSS_BASE_URL` so repeat checks need no re-entry. `.gitignore` updated.
- The loop is now: `python feedback.py` (read live) → edit → `python deploy_hf.py` (ship) — all without a manual DB download.

## 2026-06-22 (v1.55 — boot-restore hardening: stop a slow bucket mount from reverting live data)
**Incident root cause.** The live Space restarted (~3:10 PM); on boot `_ensure_live_db()` called `bk.newest_valid_snapshot()`, which returns `None` for BOTH a genuinely empty bucket AND a `/data` FUSE mount that simply isn't readable yet. The old code treated `None` as "first boot", copied the shipped seed (`css_is.db`, where `DB == SEED_DB` since `CSS_DB` is unset) over the live DB, and the snapshotter then wrote that seed back and pruned the good snapshots (`PERSIST_KEEP=24` minute-snapshots → a very shallow window). Net effect: live data silently reverted to an older state and recent feedback/account changes were lost. Mount config was fine (`CSS_PERSIST_DIR=/data` set; Dockerfile runs as root) — the bug was the boot path conflating "not ready" with "empty".
- **`backups.py`** — new boot-safety helpers, all unit-tested:
  - `bucket_writable(d)` — real create+read+delete probe (the only reliable "is the FUSE mount actually here?" test; `isdir()` lies during mount lag).
  - `wait_for_bucket(d, timeout=60, interval=2)` — block until the mount proves writable, riding out FUSE lag at boot.
  - `snapshots_present()` — any snapshot file present (valid or not), to tell "empty bucket" apart from "snapshots exist but none open".
  - `boot_decision(...)` — pure decision function returning `restore` / `seed` / `abort`. Only seeds on a POSITIVELY confirmed first boot (mount ready + truly empty + never initialized) or an explicit `CSS_PERSIST_ALLOW_SEED=1` override; otherwise aborts rather than overwrite live data.
  - `prune_backups(keep, keep_daily=0)` — additive deep-retention: also protects the newest snapshot of each of the last `keep_daily` days, so a burst of writes can't churn the 24 minute-snapshots and rotate every older restore point off the bucket. Default 0 keeps the admin schedule's behaviour unchanged.
- **`app.py`** — rewrote the `PERSIST_DIR` branch of `_ensure_live_db()` to: wait for the mount, then act on `bk.boot_decision(...)`. On `abort` it `raise`s (the container crash-loops visibly and self-heals on the next boot once the mount is back — far safer than a silent revert). New `_persist_sentinel()` / `_persist_mark_initialized()` write a `/data/.css_initialized` marker on every good boot so a later empty bucket is recognised as an anomaly, not a first boot. New env knobs: `CSS_PERSIST_KEEP_DAILY` (14), `CSS_PERSIST_BOOT_WAIT` (60), `CSS_PERSIST_ALLOW_SEED`. The snapshot loop now calls `prune_backups(PERSIST_KEEP, keep_daily=PERSIST_KEEP_DAILY)`.
- **Tests** — `tests/test_backups.py` +4: `boot_decision` rule table (restore/seed/abort/override), `prune_backups` daily-anchor retention, `bucket_writable`/`wait_for_bucket` happy + timeout paths, `snapshots_present`. Existing prune test unchanged (default `keep_daily=0`). Full pytest exit 0.

## 2026-06-22 (v1.54 — locale-proof date display + resource person optional for bureau activities)
Two reported issues. (1) A Spot Feedback report (rsmanaloto@doh.gov.ph) flagged `#event_date` on `/create` showing the wrong order — a US-locale desktop rendered the native `<input type=date>` as mm/dd, a dd/mm machine as dd/mm. The stored value was always correct ISO; the confusion was purely the locale-bound display, which the page can't override. (2) A bureau-organized activity was forced to have ≥1 resource person even though it produces a Form 2 event review on its own.
- **`static/js/app.js`** — new zero-dependency date-field enhancer (final IIFE). Every `<input type=date>` keeps its native control (calendar, min/max, keyboard, mobile picker, ISO value) but is made invisible and overlaid with a FIXED, locale-independent `22 Jun 2026` display; inputs with `data-echo` also get a spelled-out `Monday, 22 June 2026` line below. A `MutationObserver` on the `type` attribute drops the overlay (`.raw`) when the "Add specific time" toggle swaps the field to `datetime-local`.
- **`static/css/app.css`** — `.datefix` / `.datefix-disp` / `.datefix-echo` styles using existing tokens (`--surface`/`--ink`/`--line`/`--accent`/`--ring`); verified in dark mode. app.css `?v=` → `20260622b`.
- **`templates/form_create.html`** — `event_date` + `end_date` carry `data-echo` + `data-placeholder`; resource-person section 4 reworded as "optional for a bureau-organized activity", and the bureau/outside type hints updated. app.js `?v=` → `20260622b`.
- **`app.py` (`create_survey`)** — the "Add at least one resource person" validation now applies only when `event_type == "outside"`; a bureau activity with no speakers creates its lone Form 2 + event link tree as before.
- **`static/js/sw.js`** — `CACHE_VERSION` → `v1.54-a` so installed survey PWAs purge the old app-shell and pick up the new CSS/JS.
- **Tests** — new `tests/test_bureau_no_rp.py` (2): a no-RP bureau activity persists with a lone Form 2; an outside event with no RP is still rejected. Affected suites (outside/date/event) green; full pytest exit 0.

## 2026-06-22 (v1.53 — UX #21 deploy 2: SR data-table fallback for Pulse, Participation & Verbatims charts)
Finishes UX #21 (WCAG 1.1.1). Extends the deploy-1 `chart_table()` macro + `.sr-only` utility to the remaining dashboard data charts. No CSS/asset change (utilities already shipped in v1.52) — templates + one builder only.
- **`dashboard_insights.py` (`_count_geom`)** — additively returns `main_table` (period × count, missing periods as “—”), mirroring the `_svg_geom` change. Covers `volume_view` + `engagement_trend`; `coverage_trend` already routes through `_svg_geom` so it inherited its table in v1.52.
- **`templates/participation.html`** — the shared `linechart(G, …)` macro now emits `chart_table(ytitle, ['Period', ytitle], G.main_table)` after each `</svg>` (guarded on `G.main_table`), so every volume / coverage / engagement line gets its table in one place.
- **`templates/pulse.html`** — each vital tile's sparkline now ships a small SR table built from `t.micro_pts` (period × shown value), captioned with the tile title.
- **`templates/verbatims.html`** — the 3-way tone chart's SR table combines the appreciation `main_table` with the improve/mixed `dims_table` (both already on `sent.breakdown.geom` from the v1.52 `_svg_geom` change) into one Period | Appreciation | Areas to improve | Mixed table — no new Python.
- **Classification (no change needed):** the `role="img"` SVGs on `result.html`, `login.html`, `arta_link.html` are the decorative Equity-in-Health logo, and `outside_manage.html`'s is the 🔒 lock status glyph — all already have correct `aria-label`s; none is a data chart.
- **Tests** — `tests/test_a11y_charts.py` extended (+3): `_count_geom` table shape + “—”, the Verbatims table is genuinely 3-way (4 headers, 3 tone cells/row), and Pulse/Participation/Verbatims each ship an SR table where a chart renders. Full pytest exit 0.

## 2026-06-22 (v1.52 — UX #21 deploy 1: skip-to-content link + SR data-table fallback for Trends charts)
WCAG 2.2 work (DOH/government deployment). Two gaps closed: **2.4.1 Bypass Blocks** (a keyboard skip-link) and **1.1.1 Non-text Content** (a screen-reader data table behind each chart). This is the first of two deploys — Trends charts only; the remaining dashboard charts (pulse / verbatims / participation) follow in deploy 2.
- **`static/css/app.css`** — new `.sr-only` utility (clip-rect; visually hidden but kept in the a11y tree) + `.skip-link` (fixed, off-screen via `translateY(-160%)` until `:focus` brings it on-screen). Reuses `--accent`/`--on-accent`/`--ring` (already AA-audited), so `tools/contrast_check.py` needs no new pairs.
- **`templates/dash_layout.html` + `public_layout.html`** — `<a class="skip-link" href="#maincontent">` as the first body child; content target is now a `<main id="maincontent" tabindex="-1">` landmark (`.wrap` is a bare class selector — div→main is style-safe; verified no `.wrap >`/`.pub-wrap >` child rules). app.css `?v=` → `20260622a`.
- **`templates/_components.html`** — new `chart_table(caption, headers, rows)` macro rendering an `<table class="sr-only chart-data">` with `<caption>` + `scope`'d headers. The chart SVG keeps its `role="img"` short summary; the table is the full navigable fallback.
- **`dashboard_insights.py` (`_svg_geom`)** — additively returns `main_table` (period × value) and `dims_table` (period × one column per area/segment, missing points as “—”), built from the already-windowed, index-aligned `vseries`/`vdims`. One change covers all five Trends charts (main, low-raters, by-area, segment-split, comment-sentiment), which all route through `_svg_geom`.
- **`templates/trends.html`** — each of the five charts now emits its SR table after `</svg>` via the macro (single-series → `*.main_table`; multi-series → `*.dims_table`, guarded for the no-dims case).
- **`static/js/sw.js`** — `CACHE_VERSION` → `v1.52-a` so installed survey PWAs purge the old app-shell and pick up the new CSS.
- **Tests** — new `tests/test_a11y_charts.py` (5): `_svg_geom` table shape + “—” for nulls + no dims_table when single-series; skip-link present in both layouts; Trends charts always ship their SR table. Full pytest exit 0.

## 2026-06-22 (v1.51 — Directory email edits re-point the linked account's login)
Pilot bug: editing a BLHSD staff member's email in the Directory did not change the email they sign in with, so reactivating or resetting their account kept reverting to the old address. **Root cause:** the login email lives in `admin_user.username`, copied **once** from `resource_person.email` at account-creation time (`_provision_account`); `update_rp` only ever wrote `resource_person.email`, so the two diverged silently.
- **`storage.py`** — new `set_admin_username(conn, user_id, username)` helper (one-line `UPDATE admin_user SET username=?`), placed beside the other `admin_user` mutators.
- **`app.py` (`POST /directory/person/{id}/update`)** — after `update_rp`, if the person has a linked account, re-point its `username` to the new directory email. Guarded: only when the new email is **valid, changed, and not already owned by another account**. On a collision the directory edit still saves but the login is left intact and a warning is surfaced via `?err=` on the redirect; clearing/invalidating the email leaves the existing login untouched (never blanks a username). Each successful re-point is audited as `change_login_email` (before/after).
- **Tests** — new `tests/test_account_email_sync.py` (3): email edit re-points the account login (old email no longer resolves), collision leaves both logins unchanged + warns, clearing the directory email keeps the existing login. Related directory/user/account/monitor suite green.

## 2026-06-22 (v1.49 — Multi-day activity date range + PDF-only Certificate of Appearance)
Two pilot-feedback items (Spot Feedback from ray@gmail.com). (1) Activities can now carry an optional **start→end date range** for multi-day events; (2) the Certificate of Appearance is now **PDF-only** (the editable PowerPoint export is removed, so an official certificate can't be altered after issue).
- **Schema (`storage.py`)** — additive nullable `end_date TEXT` on both `form_instance` and `event`, added to the `CREATE TABLE` blocks **and** the idempotent `PRAGMA table_info`→`ALTER TABLE ADD COLUMN` migration guards (safe on the live bucket DB). `NULL` = single-day. `create_form_instance`/`create_event` take an optional `end_date`; `_EVENT_COLS`/`_event_row` and `get_form_context` expose it; `_outside_event_context`+`add_event_speaker` propagate it so a late-added speaker inherits the range.
- **Date range is display + lifecycle only — reporting is unchanged.** Year/quarter/semester/month bucketing (`css_is_engine.assign_periods`) still keys **only** off `event_date` (the start), verified by test. `lifecycle_of()` gains an optional `end_date`: with no explicit feedback deadline a multi-day activity stays **"ongoing" through its last day** (`start ≤ today ≤ end`), single-day behaviour byte-identical. `events_with_lifecycle` selects + threads `e.end_date`.
- **Creation (`app.py` `POST /create` + `form_create.html`)** — new optional "to" date input beside the start (min bound to start via inline JS). Shared validator `_norm_end_date(start, raw)`: blank or ≤ start → single-day (no error), non-date → error, beyond the +2yr cap → error. Threaded `end_date` into all three `create_form_instance` calls + both `create_event` calls; echoed back on validation error; result summary shows the range.
- **Manage editing (NEW capability — dates were previously un-editable post-creation)** — `set_event_dates()` re-dates the event row **and** every non-archived form (via `event_form`) so the link tree and reporting atoms never disagree. New `POST /activities/{token}/dates` (same `_can_manage_event` gate + `_audit`), reusing `_norm_end_date`; **calls `invalidate_atoms()`** because moving the start date re-buckets the reporting period (the entry-window save deliberately does not). New "Activity dates" card on `activity_manage.html` + `outside_manage.html` with success/error flashes (`dateok`/`err=baddates`).
- **Display (`humandaterange` filter)** — new Jinja filter renders `June 16–18, 2026` (collapses shared month/year; widens across months/years), falling back to `humandate` for single-day so existing rendering is unchanged. Swapped in at the activity-centric sites: link_tree, rating (survey header), combined_form, monitor (list), monitor_event, monitor_outside, both manage headers. Certificate body uses an equivalent `_long_date_range()` for the "held on …" clause.
- **Certificate PDF-only (`certificate.py`, `app.py`, templates, `i18n.py`)** — removed `render_pptx` + the `_TEMPLATE` asset ref + the module's two-format docstring; the `/e/{token}/certificate` route now always renders PDF (a stale/forged `?fmt=pptx` falls back to PDF, asserted by test). Dropped the "PowerPoint version" buttons from `thanks.html` + `link_tree.html`, the orphaned `thanks_cert_pptx` i18n key, and reworded the manage-page cert help to "print-ready PDF".
- **Tests** — new `tests/test_date_range.py` (10): `humandaterange` collapse/widen, single-day keeps `end_date` NULL, multi-day round-trips to event+forms, end≤start → single-day, non-date end → 400, manage re-dates event+forms, clearing end returns to single-day, bad start rejected/no-change, reporting keys off start. `test_certificate.py` updated (PDF-only assertions, no `render_pptx`), `test_monitor.py` lifecycle test +3 multi-day cases.

## 2026-06-22 (v1.48 — Comment-tone trend over time: 3-way sentiment on the verbatims page)
Extends the verbatim sentiment work longitudinally (UX-queue item #14). `dashboard_insights.sentiment_trend()` already produced a binary "% positive" line (used on Trends/person/team); it now **additively** returns a 3-way `breakdown` (appreciation / areas-to-improve / mixed — mutually exclusive, shares total 100% per period) reusing the segment-chart geometry, plus a new `_sentiment_breakdown_read()`. The binary line stays **byte-identical** (a mixed-overridden comment is still text-classified for it), so the three existing callers are untouched.
- **`/reports/verbatims`** (`app.py` + `templates/verbatims.html`) — new "Tone of comments over time" chart above the digest, built over the **full history** (org scope, period filter dropped) for a single survey type (`survey_type=0`/All shows no chart). Grain toggle (monthly/quarterly/yearly). Figure-axis-standard compliant: labelled X/Y axis titles, legend (green/amber/accent = appreciate/improve/mixed), "how it's computed" calcnote, and a **period-agnostic** person·place·time·(N) caption (place from `crumbs[-1]`, time from the charted range, so it never contradicts the period-ignoring chart).
- **Downloads parity** — `dashboard_docs._chart_sentiment_breakdown()` renders the 3-line chart into the verbatims **PDF** (`rd._fig_block`) and **PPTX** (`rd._chart_slide`) with a figure-number counter + captions; the `app.py` export branch builds the breakdown over full history (`get_atoms` re-scoped) and the page's Download link now carries `&grain`. PNG stays the single themes chart; XLSX stays raw rows + themes (per the per-format download-output roles).
- **Tests** — `tests/test_verbatim_sentiment.py` +6 (shares sum to 100% per period, binary line unchanged, override-mixed bucketing without polluting the positive line, rising-improve read = "bad" tone, single-period + no-comment fallbacks). Full pytest green; `qa_smoke` 153 checks pass; `contrast_check` green (no token change).

## 2026-06-22 (v1.47 — Comment raffle: engagement draw from face-to-face commenters)
New opt-in, per-activity feature: draw a random raffle winner from everyone who left a comment, for both bureau and outside ("invited") activities. The hard constraint shaped the design — bureau responses carry the registered attendee's name, but outside responses are anonymous by design (no name/email ever captured) — so identity is **name-when-known, else a stable CLAIM CODE** shown to the respondent at submission. Eligibility = any non-empty comment on a **face-to-face** response (online/archived excluded; SEX/AFFIL demographic notes don't count).
- **`storage.py`** — migration adds `event.raffle_enabled` (0/1, default 0) + `event.raffle_prize` (TEXT), and a `raffle_draw` history/audit table (event_id, response_id, prize, drawn_at, drawn_by). `_EVENT_COLS`/`_event_row` extended (so `get_event*` expose the two fields). New: `claim_code()` (sha256→5 chars over an unambiguous alphabet, no 0/O/1/I; deterministic + non-sequential; a display label only — response_id is the source of truth), `raffle_pool()` (one entry per f2f comment, attendee name or None, comment = overall remark else non-demographic item notes), `set_event_raffle`, `raffle_record_draw`, `raffle_drawn_ids`, `raffle_winners`, `raffle_reset`.
- **`app.py`** — four routes, all gated by the existing `_can_manage_event` ownership/admin check: `POST …/raffle/settings` (on/off + prize, audited), `GET …/raffle` (projector draw screen), `POST …/raffle/draw` (fair `secrets.choice` from the pool minus prior winners unless `allow_repeat`; prize falls back to the activity's configured prize; returns JSON + audits each draw), `POST …/raffle/reset`. The single-form (`POST /r/{token}`) and combined (`POST /seq`) submit handlers now capture the new response id and, when the activity's raffle is on and the f2f response carries a real comment, pass the claim code(s) to the thank-you page. Added `import secrets`; `submit_combined` now resolves `lang`.
- **`templates/thanks.html`** — a gold "🎟️ You're entered in the raffle!" ticket showing the claim code(s) + keep-this-to-claim note, bilingual EN/FIL inline (no new i18n keys), guarded with `is defined` so other thank-you renders are unaffected.
- **`templates/activity_manage.html` + `outside_manage.html`** — a "🎟️ Comment raffle" card (On/Off badge, enable toggle, prize field, "Open draw screen ↗" when enabled).
- **`templates/raffle.html`** (new, standalone full-screen) — projector draw stage with **four live-selectable animations** (slot reels / prize wheel / name-shuffle+spotlight / lottery tumbler) and a **selectable synthesized audio** picker (Off / Suspense / Arcade — Web Audio API, no audio files, offline-safe), confetti, winner reveal (name|"Anonymous" + claim code + comment + prize), "Draw again", allow-repeat toggle, spacebar-to-draw, live winners list; animation + sound choices persist in `localStorage`. Server-side pick is the source of truth; a ~3.2s minimum spin holds the suspense regardless of network.
- **Tests** — `tests/test_raffle.py` (17): claim-code stability/cleanliness, pool eligibility (real comments only, f2f only, item-note inclusion, demographic-only + no-comment exclusion, named vs anonymous, outside activities), settings/draw/winners/reset storage round-trips, and HTTP draw (picks/records/excludes-repeats, allow-repeat, empty vs exhausted, reset, manager-gating) + thank-you code surfacing. Full suite green (446 passed).

## 2026-06-21 (v1.44 — Phase 3 UI sweep, batch 7: public survey path + auth — FINAL batch)
Seventh and **final** batch of the Phase 3 rubric sweep (`UI_IMPROVEMENT_PLAN.md`, sweep order items 11–13 — public/auth). **Phase 3 is now complete** → Phase 4 (tutorial system) is unblocked. Mapped the respondent-facing + auth templates (mobile lens = top priority; `public_layout.html` confirms `data-theme` applies to public pages, so dark mode is in scope here too). Most were already compliant; the real defects were two unlabeled inputs and one dark-mode hex. NOTE: an Explore pass over-flagged several "mobile overflow" risks that did NOT reproduce and were verified false in Preview at 360px (see below) — they were left unchanged.
- **`templates/rating.html`** — (1) the per-question optional note `<input class="note">` had only a `placeholder` (not a reliable accessible name) → added `aria-label="{{ t('note_ph', lang) }}"` (matches the visible placeholder, i18n-aware). (2) `.conv-error` (the one-at-a-time "please answer first" warning) `color:#c00`→`var(--red)` — the literal maroon was unreadable on dark; the token reads correctly in light/dark/contrast.
- **`templates/combined_form.html`** — same note-input fix: added `aria-label="{{ t('note_ph', lang) }}"` to the per-item `<input class="note">`.
- **Verify-only (no change):** `thanks.html` (no inline style; pub-card + `var(--green)` tokens), `login.html`, `set_password.html`, `forgot.html` (all `.pub-card` with token colours + labelled inputs + `role="img"`/`aria-label` brand mark + `flash err role=alert` error states), `shared.html` (extends `dash_layout`, already uses `empty_state()` + tokens + `aria-hidden` on the `→` glyph). `reset_password.html` does **not exist** (the `/reset-password` route reuses `set_password.html`) — dropped from the batch list.
- **Explore false-alarms, verified NON-defects at 360px (left as-is):** the `@media (max-width:419px)` scale-wrap in rating/combined_form DOES cover 360px (max-width is "≤", so the scale already wraps there — `flex-wrap:wrap` confirmed computed at 360); the `max-width:380px/400px` on `.pub-card` (login/set_password/forgot) is responsive — `max-width` caps but the card still shrinks (measured 331px wide at a 360px viewport, zero page overflow). No breakpoint or width changes made.
- **Verified (Preview, 360px, real tokens):** `/r/af7466fb8215` (rating, open form) renders 200 with **zero horizontal overflow**, scale `flex-wrap:wrap`, note `aria-label`="Add a note about this (optional)", `.conv-error` computed `rgb(197,48,48)`=`--red`; `/seq?tokens=af7466fb8215` (combined) 200, zero overflow, note `aria-label` set; `/login`, `/forgot`, `/set-password` all 200 with zero overflow (cards 331px). All 7 batch-7 templates compile against the app's real Jinja env. `contrast_check` green (no `app.css`/token change); full pytest. Version bumped to **1.44**. **Phase 3 page sweep DONE (batches 1–7).**

## 2026-06-21 (v1.43 — Phase 3 UI sweep, batch 6: admin/ops pages, table-reflow + a11y + dark-mode pass)
Sixth batch of the Phase 3 rubric sweep (`UI_IMPROVEMENT_PLAN.md`, sweep order item 9 — admin/ops). Mapped all 17 admin/ops/manage templates with an Explore pass. Most were already rubric-compliant (use `page_header()`/`empty_state()`, responsive tables, semantic badges) — the real defects were a cluster of non-responsive tables, decorative glyphs missing `aria-hidden`, and a few dark-mode-breaking hex literals. Two findings were **non-defects per the established v1.37 header-audit decision** and left alone: the "manual `<h1>`" on the detail pages (`monitor_event`, `monitor_outside`, `outside_manage`, `activity_manage`, `cleanup`) are the exempt composite name+badge `.mhead` headers (`page_header` escapes its title, can't hold the badge/span — same exemption as person/team); and `directory.html` list avatars stay `alt=""` (decorative, visible text fallback) per the plan.
- **`templates/backups.html`** — the Snapshots table (raw `<table>`, unwrapped, with a Restore *text input* in a cell that would clip badly on mobile) → wrapped in `.table-wrap` + `class="resp-table"` + `data-label` on every `<td>` (full stacked reflow at 360px). Dark-mode hex: `.badge.off` `background:#f3f4f7`→`var(--surface-2)`.
- **`templates/encode_home.html`** — the forms table (already in `.table-wrap`, scroll-only) upgraded to `class="resp-table"` + `data-label`s for a proper stacked reflow.
- **`templates/activity_manage.html`** — the `bucket_card` macro's `.res-tbl` (3-button form-table) wrapped in `.table-wrap`; the per-row `res-kind` leading glyph wrapped `<span aria-hidden="true">` (paired with its own visible text label). The inline `.empty` notes (335/386/456) and "Currently:…" spans (411/413) LEFT as styled status notes — they sit beside add-forms/controls, not blank content areas (Phase-1 deferral guidance; `.empty` is styled muted-italic globally `app.css:472` + locally).
- **`templates/outside_manage.html`** — the headerless `.sp-tbl` form-table wrapped in `.table-wrap` (graceful internal scroll; stacking it would fight the custom right-aligned form cells). The disabled-remove `🔒` glyph given `role="img" aria-label="Locked — has responses, can't be removed"` so it announces meaning instead of reading as a bare emoji.
- **`templates/directory.html`** — `aria-hidden="true"` on the 3 decorative `🔍` search-box glyphs (the inputs already carry `aria-label`); dark-mode hex `.dcard button.del` `border-color:#f0caca`→`var(--red-ln)`; added a local `.dcard td.empty` rule (muted/centered/italic) so the 4 `<td class="empty">` table-cell empties read as designed empty states (kept as `<td>` — the block-level `empty_state()` macro can't sit in a `<tr>`; 4 cells on one page is below the 3-page threshold to promote a shared `app.css` class).
- **`templates/ops.html`** — `aria-hidden="true"` on the decorative `.verdict .icon` and the `.safety .dot` status glyphs (✔/⚠/●/·); each is paired with descriptive text and a tone class, so colour/glyph is not the sole signal.
- **`templates/audit.html`** — the leading `✔`/`⚠` in the chain-status badges wrapped `<span aria-hidden="true">` (the badge text already states "Chain intact"/"CHAIN BROKEN").
- **Verify-only (no change):** `users.html`, `cleanup.html`, `admin_sharing.html`, `monitor.html`, `monitor_event.html`, `monitor_outside.html`, `my_feedback.html`, `feedback_board.html`, `feedback_detail.html`, `result.html` (its `class="list"` summary is a 2-col key/value table — never overflows at 360px; stacking would be worse). All `.empty` notes on these are styled muted (global `app.css:472` + per-template) and are inline/link-bearing status notes the plan keeps as-is.
- **Verified:** all 9 edited templates compile against the app's real Jinja env (incl. the `activity_manage` macro); `/admin/backups`, `/encode`, `/directory`, `/ops`, `/admin/audit`, and `/activities/<token>/manage` (outside) all render 200 with no traceback; **zero document horizontal overflow at 360px** on backups/encode/directory/outside-manage (backups + encode fully reflow via `resp-table`; the manage `.sp-tbl` scrolls inside its `.table-wrap` without pushing the page); 3 directory search icons confirmed `aria-hidden`; `td.empty` rule present. `contrast_check` green (no `app.css`/token change); full pytest. Version bumped to **1.43**.

## 2026-06-21 (v1.42 — Phase 3 UI sweep, batch 5: reports/verbatims, dark-mode + mobile pass)
Fifth batch of the Phase 3 rubric sweep (`UI_IMPROVEMENT_PLAN.md`, sweep order item 8 — reports). `verbatims.html` was already fully rubric-compliant (`page_header()` + `empty_state()`, all-token colours, `.vb-cols` reflow at 780px, single column with no horizontal scroll at 360px) — **verify-only**. All real defects were on `reports.html`: light-only hardcoded hex that ignored dark mode, plus two raw breakdown tables that weren't wrapped for narrow screens. Per the locked decision, fixed by swapping the literals to existing themed tokens rather than adding parallel `[data-theme]` blocks; edits are template-local `<style>` (no `app.css` change, so no cache-bust needed).
- **`templates/reports.html`** — (1) the answer-distribution bar's neutral middle segment `.bar .m` `#cbd5e1`→`var(--line-strong)` (light value `#cdd5e1` is byte-near-identical; dark now resolves to `#3b4c66` instead of staying light grey); (2) the two `border-bottom:1px solid #f1f3f6` rules (`.cc-card .cc-details td`, `.tblk td`)→`var(--line)` (dark now `#2c3a4f` instead of a near-white line); (3) wrapped the two previously-unwrapped tables in `.table-wrap` — the `tally_block` respondent-profile table and the `cc_card` "Full breakdown" `<details>` table (the plan's cross-cutting backlog item for `reports.html`). The wide tables were already handled: the ARTA SQD table is `.resp-table` with `data-label` cells, the SERVQUAL dims tables are already in `.table-wrap`.
- **Deliberately KEPT:** `--grey` fine-print (`.scale-note`, `.cc-base`) per the Phase-1 AA-exempt decision; the `var(--accent,#hex)` fallbacks (`.rtab.on`, `.sharebar i`) — the hex is only a fallback when the token is absent; the green/red bar segments (already tokens). `verbatims.html`'s "Nothing on this side in this scope." note left as a styled inline note (pure status inside a narrow coloured column — the block-level `empty_state()` would read heavy there).
- **Verified (Preview, forged admin cookie):** `/reports?type=1/2/3` + `/reports/verbatims` all render 200 with no console errors; the swapped tokens resolve correctly in both light (`.bar .m`=`rgb(205,213,225)`) and dark (`.bar .m`=`rgb(59,76,102)`, `.tblk td` border=`rgb(44,58,79)`); both Reports and Verbatims have **zero horizontal overflow at 360px** (`scrollWidth==clientWidth==360`, no offenders); the 5 `tally_block` + 3 `cc_card` tables confirmed inside `.table-wrap`. `contrast_check` not re-run for tokens (no `app.css`/token change); full pytest. Version bumped to **1.42**.

## 2026-06-21 (v1.41 — Phase 3 UI sweep, batch 4: activities/activity/activities_archived, empty-state pass)
Fourth batch of the Phase 3 rubric sweep (`UI_IMPROVEMENT_PLAN.md`, sweep order item 7 — activities). Same finding as the prior batches: the list pages were already rubric-compliant. `activities.html` + `activities_archived.html` already use `page_header()` + `empty_state()` (adopted in the v1.37 pass) and have a reflowing `.resp-table`, sticky sortbar on `--stuck-top`, and aria-hidden on standalone arrow/caret glyphs — verify-only. The one real "States" defect was on the detail page.
- **`templates/activity.html`** — the three genuine empties rendered as bare `<p class="sublab" style="margin:0;">` inside a `.panel` migrated to the `empty_state()` macro (import added): the no-section-comparison branch (only activity in scope that year, `icon="⇄"`), the no-Form-2-scores branch (`icon="◔"`), and the no-demographic-data branch (`icon="◔"`, conditional "— enter it below" manager text preserved via `{% set %}`→macro so the HTML-escaping macro keeps the text). Composite name+pill report header LEFT as the bespoke `.rpt-head` `<h1>` per the v1.37 detail-page header exemption (matches person/team).
- **`templates/activities_archived.html`** — removed the now-dead `.empty` CSS rule (the page moved to `empty_state()` in v1.37; the class had no remaining users).
- **Deliberately KEPT:** the demographics/meter brand-blue gradient fills (`#4299e1→#2b6cb0`) and the categorical demographic colours (male/female/DOH blue·pink·green·grey, each paired with a legend dot) — data-series identity, read fine on dark; and the inline `✎`/`⚙` glyphs that sit *within* link/summary text (read as part of the label, consistent with `activities.html`'s un-hidden `✎ Edit / merge`).
- **Verified (forged admin cookie, Preview):** all 49 listed activity reports render 200 with no traceback at desktop + 360px; demographics empty-state confirmed rendering (`◔` + aria-hidden + conditional manager text); SERVQUAL table reflows via `.resp-table` at 360px with no horizontal scroll. The no-Form-2 / no-section-comparison branches are data-gated (every live activity has a Form-2 report and peers) so unexercised at runtime, but the whole template compiles clean on every render (a syntax error would 500 all of them). `contrast_check` green (no colour/token change); full pytest. Version bumped to **1.41**.

## 2026-06-21 (v1.40 — Chart/data-viz dark-mode token sweep on trends + participation)
Follow-up to the batch-3 deferral: the light-only structural hex in the Trends + Participation chart styles (gridlines, SPC bands, limit lines, legend swatches, progress-bar tracks) glared near-white on dark cards. **Resolved by swapping the literals to the existing themed tokens** — NOT by adding a parallel `[data-theme="dark"]` block. Suitable tokens already existed (`--surface-3`≈#eef1f6, `--line-strong`≈#cdd5e1, `--grey-tone`=#94a3b8, `--soft`, `--ink-soft`), so a direct swap is byte-near-identical in light, auto-correct in dark **and** contrast (one edit covers all three themes), and actually *removes* hex rather than doubling it. The badge palette needed its own dark block only because it had no token backing; these did.
- **`templates/trends.html`** — `.chart .grid`/`.ctl-band` `#eef2f7`→`var(--surface-3)`; `.chart .lim`/`.dimline.flat` + `.bandnote .sw.band` border `#cbd5e1`→`var(--line-strong)`; `.bandnote .sw.band` bg `#eef2f7`→`var(--surface-3)`; `.mover` base `#fbfdff`→`var(--surface-2)`; `.axtitle` `#475569`→`var(--soft)` and `.calcnote b` `#475569`→`var(--ink-soft)` (now matches participation, which already used these). Two inline body swatches: Overall key `#94a3b8`→`var(--grey-tone)` (byte-identical light), and the by-area legend flat swatch literal `#cbd5e1`→`var(--line-strong)` in the `{% set sw %}` expr (the expr already mixed `var(--green)` + hex, so this is consistent).
- **`templates/participation.html`** — same `.chart` grid/ctl-band/lim/sw.band swaps; plus `.cover .track` + `.unit .track` `#eef1f5`→`var(--surface-3)` and `.unit.zero .fill` `#e2e8f0`→`var(--line-strong)`.
- **Deliberately KEPT (read fine on dark; data-series identity):** saturated line/bar/badge fills — `.mainline.cov`/`.dot.cov` `#2f855a`, `.eng` `#805ad5`, `.unit .fill` gradients, `.unit.down .mv` `#c05621`, the green confidence ribbon, white dot markers; and the `#d97706` down-trend (line **and** its legend swatch both use it, so they stay matched) + the mid-grey `#64748b` centre line. These are mid/strong tones with adequate contrast on the dark `--surface`.
- **`templates/team.html` — NO CHANGE:** the `.pbadge` earned-badge palette is **already** dark-covered by the existing block in `app.css:745–764` (higher-specificity `[data-theme="dark"] .pbadge.bg-*`), which `contrast_check.py` already audits green. The task's team.html premise was stale. Contrast theme is light-based (`--bg:#fff`), so the light pastels are correct there too — no contrast override needed.
- **Verified:** _pending_ — jinja render (forged admin cookie) of both pages in default + dark + contrast; `contrast_check` green; full pytest. Version bumped to **1.40** (ships together with the held v1.39 a11y batch in one deploy).

## 2026-06-21 (v1.39 — Phase 3 UI sweep, batch 3: teams/team/trends/participation, a11y pass)
Third batch of the Phase 3 rubric sweep (`UI_IMPROVEMENT_PLAN.md`, sweep order items 4–6). Same finding as batches 1–2: the unit-detail + time-series pages are already structurally compliant (single h1 via `page_header`, full-width lede, charts with `role="img"`/aria-label + axis titles + "how computed" notes, reflowing grids). Only real defects were decorative emoji/arrow glyphs missing `aria-hidden`, one un-migrated empty state, and a divider hex that ignored dark mode.
- **`templates/teams.html`** — `aria-hidden="true"` on the two `.uglyph` unit-type emoji spans inside the `ucard()` macro (covers every bureau/division/section card glyph). Unit name is the adjacent visible label, so the glyph is purely decorative.
- **`templates/team.html`** — `.uglyph` header emoji + the `↑` drill-up arrow wrapped `aria-hidden`. The no-data `<div class="panel">` (with inline `style`) migrated to the `empty_state()` macro (import added) — consistent with the v1.37 adoption pass; the period note moves to the title string (drops only the bold, which the macro can't carry). The `.coach-motiv` divider `rgba(0,0,0,.07)` → `var(--line)` (the one dark-mode-breaking hex with a clean token). Composite name+badge+meta header LEFT as a raw `<h1>` per the v1.37 header-audit exemption for detail pages (matches `person.html`).
- **`templates/trends.html`** — leading trend emoji (📈📉➡️🔍) on the two `.read-sub` reads wrapped `aria-hidden`. The `.larr` legend arrows LEFT readable — they're the only directional cue on an unsigned score (informative, not decorative).
- **`templates/participation.html`** — leading 📋/🔍 read emoji + the link `→` affordance wrapped `aria-hidden`; the `▲/▼` movement triangles on the vcard delta and per-unit rows wrapped `aria-hidden` because the **signed** delta beside them already conveys direction in text (redundant glyph).
- **Deliberately deferred (user-confirmed follow-up):** the light-only badge/chart-series hex palettes (`team.html` `.pbadge` gold/rose/violet/teal/indigo/stone/fuchsia ×9; `participation.html` chart swatches/bars; `trends.html` legend `#d97706`/`#cbd5e1`/`#94a3b8`). No token equivalents exist — converting would mean inventing accent tokens, which the sweep rule forbids. Tracked as a separate "dark-mode palette" item, not expanded into this batch.
- **Verified:** _pending_ — jinja parse of all four + render (forged admin cookie) of the team.html empty-state; `contrast_check` green; full pytest. Version bumped to **1.39**.

## 2026-06-21 (v1.38 — Phase 3 UI sweep, batches 1–2: home/pulse + people, a11y pass)
First two batches of the Phase 3 page-by-page rubric sweep (`UI_IMPROVEMENT_PLAN.md`). Both page-sets were already largely rubric-compliant (single h1, full-width lede, styled empty-states, responsive, no 360px overflow, aria-labelled charts); the only real defects were decorative SVGs and content `<img>`s missing accessibility attributes. Batch 1 was folded into this deploy (it was screen-reader-only on its own).
- **`templates/home.html`** — added `aria-hidden="true"` to the 11 decorative inline icon SVGs (the 4 activity-feed headers + the role-filtered module-card icons). The labelled search-box icon already had it.
- **`templates/dash_layout.html`** — added `aria-hidden="true"` to the shared command-palette (Ctrl-K) search icon SVG; benefits every dashboard page.
- **`templates/people.html`, `person.html`, `person_activity.html`** — content avatar `<img>`s changed from `alt=""` to `alt="{{ name }}"` so screen readers announce who each photo is (the no-photo fallback already shows visible initials). The directory list avatars keep `alt=""` (decorative — they have a visible text fallback beside them).
- **Verified (forged admin cookie, Preview):** home + /dashboard → 0 unhandled decorative SVGs, single h1, no 360px overflow; people / person (with photo) / person-activity → avatar alt = name, single h1, no 360px overflow. Full pytest green. Version bumped to **1.38**.

## 2026-06-21 (v1.37 — Phase 1 UI follow-through: empty-state adoption, header audit, contrast tooling)
Layers onto the v1.35 Phase 1 work (the `page_header`/`empty_state` macros and contrast pass). Adoption + audit, no new plumbing.
- **`empty_state()` adoption** — migrated 17 genuine content-area empty states to the macro across 12 templates (people, activities, verbatims, trends, participation, audit, encode_home, activities_archived, feedback_board, my_feedback, reports ×4, shared ×2). Conditional messages use `{% set %}`→macro so scope/query text survives. DELIBERATELY LEFT for the Phase 3 page sweep: `directory.html` `<td class="empty">` table cells, inline `.empty` muted-note spans (`activity_manage` "Currently:…", `outside_manage` 🔒 lock), and link/markup-bearing notes (`monitor.html`, `my_feedback:99`) — the macro escapes HTML, so those become empty-state CTAs later.
- **`static/css/app.css`** — fixed the one accent×theme pair the v1.35 pass missed: amber **accent** preset `#a65f00`→`#a05c00` (was 4.48:1 on its own `--accent-bg`; now 4.74). The v1.35 fixes covered semantics + teal/emerald accents but not amber-on-tint.
- **`templates/admin_sharing.html`** — plain title+lede → `page_header()` macro (now `<h1 class="page">`). **`templates/cleanup.html`** — its description used `class="lead"`, which is **undefined in app.css** (rendered unstyled); fixed to `.lede`.
- **`tools/contrast_check.py`** (new) **supersedes `tools/contrast_audit.py`** (deleted). The old script transcribed tokens by hand (already drifted — still listed the pre-fix amber accent) and never checked `accent`-on-`accent-bg`. The new one **parses `app.css` live** (no drift) and covers a superset: all 18 accent×theme combos + `accent`/`accent-bg`, `accent`/`blue-bg`, `accent-ink`, and the 7 bespoke dark badge pairs. Exit-coded gate; this is the one to run before every deploy now.
- **Header audit** — confirmed the remaining 21 raw-`<h1>` templates skip the macro for deliberate reasons (8 public-layout centered-card pages, 8 dashboard detail pages with composite name+badge+meta headers, 3 form pages, home hero).
- **Verified:** jinja parse of all edits, live render (forged admin cookie) of a people empty-state + the admin_sharing header, contrast_check green, full pytest green. Version bumped to **1.37**.

## 2026-06-21 (v1.35 — Phase 1 UI: contrast fixes, card/panel dedup, page_header macro)
Completes PHASE1_HANDOFF.md. Four tasks: WCAG 2.2 AA contrast fixes, `.card`/`.panel` CSS dedup, dark-mode badge comment block, and `page_header()` macro rollout to all 24 dashboard templates.
- **`tools/contrast_audit.py`** — new stdlib-only script; checks 78 text/bg pairs (24 theme-only + 54 accent×theme) against 4.5:1 AA; exits 1 with failure table if any fail. Run before every deploy.
- **`static/css/app.css`** — fixed 4 failing pairs: `--green` light (#2f7f5a, was #2f855a, 4.39→4.71), `--amber` light (#9e6217, was #b7791f, 3.50→4.79), teal light accent (#0f7a7a, was #0f8a8a, 4.18→5.13), emerald light accent (#1c7e4f, was #1f8a55, 4.35→5.06). Deduped `.card` and `.panel` blocks into a single shared rule. Added comment block explaining bespoke badge hex overrides.
- **`templates/_components.html`** — added `page_header(title, lede="")` macro.
- **24 dashboard templates** — added `{% from "_components.html" import page_header %}` and replaced all `<h1 class="page">` tags with `{{ page_header(...) }}` calls (4 with plain lede passed to macro; 20 with h1 only or dynamic lede left inline).

## 2026-06-21 (v1.34 — Saved views + deep-linkable / shareable report filters)
Completes UX-queue #9. The URL already carries the full filter state (the scope bar and every filter pill are GET query-params), so a report view *is* its URL. This adds the missing affordances on the shared scope bar: copy a shareable deep-link, and pin/recall named views. **No DB, no Python route changes** — per-device localStorage only (locked decision); cross-person sharing is via the copied link.
- **`templates/dash_layout.html`** — inside the `.scopebar` (so it appears on every `show_scope` page): a `.savedviews` group with **★ Save view**, **Saved views ▾** (popover, hidden until ≥1 saved), and **Copy link** buttons, plus an empty `data-sv-menu` the JS fills. All `type="button"`, `hidden` until JS reveals them (graceful no-JS). Emits `window.SAVED_VIEW_CTX = {key: cur, scopeLabel}` reusing the template's existing per-page `cur` nav key.
- **`static/js/app.js`** — new saved-views IIFE: localStorage `css_views_<key>` (array of `{name,url}`, de-dupe by name, cap 20); render popover, navigate on click, `×` to delete; smart default name from `scopeLabel` + lit `.seg a.on` pills. **Copy link** uses `navigator.clipboard.writeText` with an `execCommand('copy')` textarea fallback. Hoisted a shared `window.cssToast()` (reuses `.offline-toast` styling) for the confirm toast; the offline module keeps its own copy untouched.
- **`static/css/app.css`** — `.savedviews` / `.sv-btn` / `.sv-menu` / `.sv-row` / `.sv-go` / `.sv-del` styles matching the scope-bar + palette-popover look; right-aligned, wraps under on mobile. Cache-bust → `v=20260621c` (app.css + app.js refs in `dash_layout.html` and `public_layout.html`).
- **`tests/test_saved_views.py`** — render assertions: control + `SAVED_VIEW_CTX` present on a scope-bar page, absent on `/login`.
- **Verified:** _pending_ — preview DOM checks (save → localStorage round-trip, recall navigates, copy, delete) + full pytest. Version bumped to **1.34**.

## 2026-06-21 (v1.33 — Offline response capture + sync, PWA Phase 2)
Completes UX-queue #5: a survey submitted with no connection is saved on-device and replayed automatically when connectivity returns. JS + a tiny server dedup; the two forms and the online happy-path are untouched.
- **`storage.py`** — new `submission_log(client_submission_id PK, created_at)` table (added in `_add_missing_columns`) + `submission_seen()` / `mark_submission()` (INSERT, swallow IntegrityError). Idempotency ledger so a replayed offline submission records once.
- **`app.py`** — `submit_rating` & `submit_combined` read `submission_id`; if already in `submission_log` they short-circuit with `200 {ok,deduped}` **before** the window check (so an already-recorded item always dequeues even if its window has since closed); after a successful record they call `mark_submission`. Online submits carry no id → byte-for-byte unchanged.
- **`static/js/app.js`** — new offline IIFE: IndexedDB `css_offline/queue`; capture-phase `submit` interceptor that, **only when `navigator.onLine === false`**, `preventDefault`s, serialises `new URLSearchParams(new FormData(form))` (byte-identical to a native POST) + an attached `submission_id`, queues it, and swaps the form for a “Saved on your device” panel. `flush()` runs on page load + the `online` event (mutex-guarded): 2xx→delete, 4xx→mark **failed** & surface (reject-and-surface), 5xx/network→keep & retry. A bottom pill shows “N waiting to send” and failed items with a Discard action; a green toast confirms sends.
- **`static/js/sw.js`** — `sync` handler (`css-flush`) runs the same IDB-read + POST flush so queued answers can go out with no tab open (Android/Chrome; iOS lacks Background Sync → page-flush is the universal path). `CACHE_VERSION` → `v1.33-a`.
- **`i18n.py` / `public_layout.html`** — offline UI strings (EN + draft FIL) injected as `window.OFFLINE_I18N`. **`app.css`** — saved-panel / pending+failed badge / sent-toast styles; cache-bust → `v=20260621b`.
- **Verified:** offline submit queues to IndexedDB + shows the panel; flush POSTs and records server-side; replaying the same `submission_id` adds **no** duplicate; a closed-window replay is marked failed and surfaced. Version bumped to **1.33**.

## 2026-06-21 (v1.32 — Installable PWA + offline app-shell load, Phase 1)
First cut of UX-queue #5. Makes the app **installable** and lets an already-opened survey **load with no signal**; offline *submission* (IndexedDB queue + background sync + dedup) is the deferred Phase 2.
- **New `static/js/sw.js`** — root-scope service worker. Precaches the public app shell (`app.css`, `app.js`, `search.js`, `offline.html`, icons; per-item `cache.add` so one 404 can't abort install). Fetch strategy: non-GET passes straight through (never touches submit); same-origin `/static/*` GET → stale-while-revalidate; navigations → network-first with a cached-page then `/static/offline.html` fallback, runtime-caching only public survey paths (`/r/`, `/seq`, `/e/`) so admin pages stay live. `CACHE_VERSION` (`v1.32-a`) is bumped per deploy; `activate` deletes stale `css-is-*` caches.
- **`app.py`** — `GET /manifest.webmanifest` returns a dynamic manifest (`application/manifest+json`); `?start=` sets `start_url` so installing from a survey link reopens that survey (validated to a same-origin path, else `/`). `GET /sw.js` serves the worker from the **root** path (whole-origin scope) with `Cache-Control: no-cache` + `Service-Worker-Allowed: /`.
- **`static/offline.html`** — minimal offline fallback styled with `app.css`. **`static/img/icons/`** — generated 192/512/512-maskable + 180 apple-touch icons from `equity-mark.png` (Pillow).
- **`templates/public_layout.html`** — `<head>` gains the per-page `rel="manifest"` link, `theme-color`, Android/iOS install meta, icon links, and a tiny inline `serviceWorker.register('/sw.js')`. Wired on public survey pages only (admin dashboard untouched).
- **Verified:** manifest `start_url` echoes the form path; `/sw.js` serves with the right type/headers; SW registers + controls the page; shell cache present. Version bumped to **1.32**.

## 2026-06-20 (v1.22 — Bilingual survey form: English ↔ Filipino)
First-cut i18n, scoped to the **respondent-facing survey form only** (admin UI stays English). No schema change; stored answers are language-independent (keyed by item id + numeric value, which never change between languages).
- **New `i18n.py`** — single office-editable file holding every Filipino string. `pick(request)` resolves the language (cookie `lang` → `Accept-Language` `tl`/`fil` → `en`); `t(key, lang)` looks up static UI chrome (English value matches the template byte-for-byte, so the English render is unchanged). SQD items use the official ARTA Harmonized CSM Tagalog; the rest are drafts marked `# DRAFT — office to refine`.
- **`app.py`** — `survey_spec(ctx, lang="en")` selects the `*_FIL` text/scale/chip maps when `lang=="fil"` (default keeps all 6 existing callers, incl. admin paper-entry, English). New public `GET /lang/{code}` sets a 1-year `lang` cookie and 303s back same-site; added `/lang/` to `_PUBLIC_PREFIXES` so anonymous respondents can switch. `lang` computed via `i18n.pick` and passed on the public render paths (rating GET/POST, closed, thanks, `/seq`); `t` registered as a Jinja global.
- **Templates** — `rating.html` + `closed.html` chrome moved to `t('slug', lang)` (the pluralised intro line branches on `lang` to keep the English output identical). `public_layout.html` gains a prominent left-aligned `EN | FIL` toggle in the public top bar (plain links, works without JS; shown only on survey-flow pages via `{% if lang is defined %}`) and a dynamic `<html lang>`. `.lang-toggle` pill styles added to `app.css` (cache-bust → `v=20260620a`).
- **Verified:** type-1 (ARTA), type-2 (event) and type-3 (resource-person, `{subject}` interpolated) forms render fully in both languages; the toggle persists across navigation and submit; a Filipino submission records correctly (then cleaned up); English output unchanged. Version bumped to **1.22**.

## 2026-06-19 (v1.20 — Global dark-mode text colour sweep)
Full audit of hardcoded `color:` hex values across all templates and app.css; replaced every dark-only value with the appropriate CSS token so all themes work.

**Group 1 — Semantic token swaps (9 files):**
- `app.css` — `.sf-toast color:#fff` → `color:var(--bg)` (inverts correctly against the `var(--ink)` background)
- `directory.html` — `.warn` amber colours, `.hint` muted text
- `backups.html` — `.kind.pre_restore` amber warning
- `cleanup.html` — 9 rules: `.banner.ok` (green), `.restore button` (amber), `.flag.f-low` (amber), `.nm .rid` (grey), `.b-ext` (soft), `.b-hid` (accent/blue), `.f-caps/.f-hon/.f-ros/.f-dup` (amber/green/red/blue), `.arrow` (grey)
- `participation.html` — `.calcnote b`, `.bandnote b` (ink-soft); `.miniread .mt b` (ink); SVG `.ctl-lab` (grey), `.axtitle` (soft)
- `trends.html` — `.read.neutral` border (grey); `.bandnote b` (ink-soft); `.endcap.down`, `.lowline`, `.lowdot` (amber); `.legend span.li.flat` (grey); `.legend button.li.on` highlight (surface-3/line)
- `staff_form.html` — `.warn` amber
- `outside_manage.html` — `.danger` border (red-ln), `.danger h2` (red), `.btn-warn` (amber), `.btn-danger`/`.btn-del` (red)
- `form_create.html` — `.hint` (soft), `.btn-del` (red)

**Group 2 — Badge palette dark mode (app.css):**
Added `:root[data-theme="dark"] .pbadge.bg-*` and `.ublegend .bg-*` overrides for all 10 badge colours (gold, green, blue, rose, violet, amber, teal, indigo, stone, fuchsia). Higher specificity (0,4,0) beats per-template light-mode definitions (0,2,0) so no template edits needed.

## 2026-06-19 (v1.19 — Verbatims scopebar + activity dark-mode contrast)
- **Verbatims page now shows the standard scope/period selectors.** `reports_verbatims()` was passing `org_opts`/`sel_org`/`sel_period` but not `show_scope=True`, `period_opts`, or `crumbs`, so `dash_layout.html`'s scopebar never rendered. Added `period_opts = _period_options(atoms)`, `crumbs = _crumbs(org, org_opts)`, `show_scope=True`, and `scope_extra={"survey_type": survey_type}` (so tab-switching preserves the selected scope). Removed the now-redundant scope badge chip from `verbatims.html`.
- **Activity page dark-mode contrast fixed.** Four hero-card `background:linear-gradient(…)` rules used hardcoded light hex colours (`#eef4ff`, `#f3fbff`, etc.) that stayed pale in dark mode while `var(--ink)` flipped to near-white — making the big numbers invisible. Replaced with token-based gradients (`var(--blue-bg)`, `var(--green-bg)`, `var(--amber-bg)`, `var(--red-bg)`, `var(--surface)`). Also replaced 9 occurrences of hardcoded chip/verdict text colours (`#234e75` → `var(--accent-ink)`; `#7a5300` → `var(--amber)`) that were illegible on dark surfaces.

## 2026-06-18 (v1.18 — Atoms-frame perf: categorical dtypes + unique-date period map)
- **Performance sweep, two phases, no behaviour change.** The shared in-memory atoms frame (the table every dashboard/report is computed from — ~396K rows on the live data) was costing 353 MB resident and ~5.4 s to build cold. Both addressed; output is byte-identical (full pytest + qa_smoke green after each phase).
- **Phase 1 — categorical dtypes (`storage.py`).** 14 low-cardinality label columns (`organizer_ref`, `topic`, `org_path`, `rateable_unit`, `organizer_type`, `year`/`quarter`/`semester`/`month`, `modality`, `form`, `item_id`, `service`, `served_by_rp_id`) were stored as plain strings — e.g. `year` (6 distinct values) alone ate 21 MB. `load_atoms` now downcasts them to `category` via `_categorize_atoms()` (`_ATOMS_CAT_COLS`). Result: **frame 353 → 53 MB (6.7x)**, cold-start pickle **101 → 34 MB (3x)**, dashboard groupby ~2.8x faster. The F1 incremental-append path needed care: pandas 3.0 `pd.concat` silently widens mismatched categoricals back to `str`, so added `storage.concat_atoms()` (`union_categoricals`, cost ∝ len(add)) and `app._refresh_worker` now calls it instead of `pd.concat`. **`event_date` is deliberately NOT categorical** — it's used in ordered ops (`ed >= since` window filter in `_apply_window`, `.min()/.max()` spans) that an unordered categorical rejects (caught by the export tests); kept it a plain ISO string (sorts chronologically). Contract locked by a new dtype assertion in `tests/test_atoms_cache.py::test_incremental_equals_full`.
- **Phase 2 — unique-date period map (`css_is_engine.assign_periods`).** Was running `pd.to_datetime` + string-building over all 396K rows; but `event_date` has only ~814 distinct values, so it now parses/formats the DISTINCT dates once into a lookup and `.map()`s back. **1100 → 403 ms (2.7x)**, verified bit-identical (`year`/`quarter`/`semester`/`month`) to the old per-row `.loc[valid]` version; works unchanged on the incremental delta.
- **Not pursued (logged):** the cold-build SQL `fetchall` (~2.8 s) is the remaining large cost, but the JOIN itself is optimal (`COUNT(*)` over the full join = 247 ms, all PK lookups) — the time is marshalling 19 cols × 396K rows. A dimensional load+merge could shave ~1.5 s but rewrites the path feeding every dashboard aggregate for a build that's rarely on the request path (pickle hydrate + stale-while-revalidate cover the common cases); deferred as poor risk/reward.
- **Verified:** pytest exit-0 (407 tests) and qa_smoke 153 ALL PASSED after both phases; atoms frame 53 MB and period columns category-typed with correct values on the live DB. Single-process constraint unchanged (`--workers 1`). Version bumped to **1.18**.

## 2026-06-18 (v1.17 — Verbatims in-place re-tag + "Apply all changes" on the curate bar)
- **Acted on two Spot Feedback items (2026-06-18 batch).**
- **Feedback (sdeguzman247, `/reports/verbatims`): "no 'done' marking; the page suddenly refreshes when we finish tagging, causing confusion about what's already tagged."** Root cause: each re-tag was a plain `<form>` POST to `/dashboard/comment-tag` that returned a `303` full-page redirect, so every tag reloaded the page, reset scroll, AND re-sorted the comment into a different column — the curator lost their place after every action. Fixed by progressively enhancing the control to post over `fetch` and update the card in place; no reload.
  - **app.py (`comment_tag`):** content-negotiates — when the request `Accept`s `application/json` it returns `{ok, tag, prev, response_id, item_id}` instead of redirecting. The classic `303` path is unchanged, so it still works with JS off.
  - **templates/_story.html (`retag_control` macro):** added `data-retag`/`data-rid`/`data-item`/`data-back`/`data-sentiment` on the wrapper and `data-tag`/`data-label` on each button so JS can re-render the control; the "✓ re-tagged" marker is now always present (hidden until overridden) rather than conditionally emitted.
  - **static/js/app.js:** new block 8b intercepts `.retag form` submits, posts via `fetch` (Accept JSON), and on success rebuilds the control in place — flips the sentiment, shows "✓ re-tagged as <label>", recolours the Verbatims `.vb-dot`, and pulses `.just-tagged`. Falls back to a normal submit on network error or if `fetch`/the data attrs are absent. The comment stays put (no column re-sort) so the curator keeps their place.
  - **static/css/app.css:** promoted the `.retag`/`.retag-mark`/button styles out of the `.story`-scoped selector (the Verbatims page renders the control outside `.story`) and added the `.just-tagged` pulse (respecting `prefers-reduced-motion`).
- **Feedback (gbcanoy, `/reports/activities` `#curateBar`): "if I change both Rename/Merge and Refile, which button saves both? Add an 'Apply both' button."** Root cause: the curate bar is one form but each button submits a single `action` (`rename` | `section` | `untag` | `archive`); the backend handled exactly one. So filling both fields then clicking one button applied only that one.
  - **app.py (`activity_bulk`):** added an `all` action and refactored rename + re-file into `_do_rename()`/`_do_section()` helpers that run inside the **same** `aa.new_batch()`, so a single undo reverses both. `all` applies whichever fields are filled (name and/or section), with a combined flash ("Updated N: renamed to "X" and re-filed to <section>."). Single-action paths and messages preserved.
  - **templates/activities.html:** new "Apply both" group with an `action=all` button (`data-needs-any`); the section `<select>` got `id="cbSection"`; the enable/disable script now also watches the section and enables "Apply all changes" when a name or section is set.
- **Verified (HTTP, against a copy of the live DB with a scratch admin):** combined `all` renamed + re-filed activity 9184 under one undo batch (`curate_…` carrying both `fi_topic` and `fi_lead_org` rows); single rename/section/untag and the empty-`all` guard all behave; `comment_tag` returns JSON (200, `application/json`) with `Accept: application/json` and `303` without; the rendered Verbatims DOM carries all new data attributes; the bumped `app.js`/`app.css` (`?v=20260618a`) are served. Browser click-through wasn't possible in this environment (preview proxy unreachable). Version bumped to **1.17**.

## 2026-06-18 (v1.16 — Durable persistence: bucket-backed live DB, no more rebuild wipes)
- **Root cause of the June-18 data loss, fixed.** HF Spaces have an ephemeral filesystem; the live SQLite DB shipped in the repo, so every deploy/restart reset it to the shipped snapshot — wiping any runtime writes (e.g. gbcanoy's rename/merge curate work, which was never in any exported DB). HF has also retired the classic `/data` persistent-storage tier in favour of **Storage Buckets**.
- **Architecture chosen (Path B — safe from BOTH wipe and corruption):** the live DB stays on the fast local disk (WAL intact, real POSIX locking); a mounted bucket holds **durable snapshots**. On boot the newest valid snapshot is restored from the bucket; the DB is snapshotted back after every change + on shutdown. SQLite is NOT run directly over the object-storage FUSE mount (locking/fsync there is unsafe — verified via `davanstrien/bucket-sqlite-probe-*`).
- **Run as ROOT (Dockerfile):** removed the `USER user` (UID 1000) switch. HF bucket mounts are id-mapped `user_id=0` — a non-root container gets `unable to open database file` on `/data` (the probe's documented failure mode). Root is the same mode Gradio Spaces use.
- **backups.py:** `_default_sched_dir()` now prefers `CSS_PERSIST_DIR` (the bucket, e.g. `/data`) over the live-DB dir, so snapshots land on persistent storage while the DB stays local. New `newest_valid_snapshot()` skips a torn final file (container killed mid-write) and falls back to the previous good one (`quick_check` + real-CSS-DB guard).
- **app.py:** `_ensure_live_db()` gained the Path-B branch (restore newest bucket snapshot on boot, else first-boot seed from the repo + write the first snapshot). New durability engine: `_persist_loop()` snapshots to the bucket on change (gated by `PRAGMA data_version`, every `CSS_PERSIST_TICK`=60s, keep `CSS_PERSIST_KEEP`=24) and a `shutdown` hook snapshots on SIGTERM — shrinking the planned-restart loss window to ~zero. Both no-op unless `CSS_PERSIST_DIR` is set.
- **HF config (one-time):** created private bucket `equityinhealth/office-connect-data`, mounted R/W at `/data` (`set_space_volumes`), set Space var `CSS_PERSIST_DIR=/data`.
- **deploy_hf.py:** the DB "pull/swap" carrier step is retired once persistence is live — the bucket is the source of truth and the repo `css_is.db` is only a first-boot seed. Version bumped to **1.16**.

## 2026-06-18 (v1.15 — Activities list: jump-to-page + prominent foot search)
- **Acted on Spot Feedback #20 (gbcanoy, `/reports/activities?...&page=2`).** The activities list runs to hundreds of pages (PAGE_SIZE=25 over ~10K F2 events) but the pager only offered ±1 (`← Newer` / `Older →`), so reaching a far page meant clicking one step at a time. Added a direct page-jump and surfaced search at the foot of the list.
- **templates/activities.html (template-only, no route change):** the `.pager` block gained a `form.jump` — `<input type="number" name="page" min="1" max="{{ pages }}">` + Go, carrying the current `sort`/`org`/`period`/`q` as hidden inputs so the jump preserves scope. Out-of-range/junk input is already safe: `dashboard_activities` clamps `page = min(max(1, page), pages)` server-side. Also added a `.foot-search` card (repeat of the top search, prefilled `q`, with Clear) nudging "searching is faster than paging through N pages" — the better path for a 10K-row list. First real CSS for `.pager`/`.page-info` (previously unstyled inline); all new styles use existing theme tokens so they track dark mode + accent. Both only render when `pages > 1`.
- **Verified:** Jinja parse-check passes; standalone render of the block (page 2 of 412, q="workshop") produces correct bounds (`min=1 max=412 value=2`), carried filters in every hidden field, and Newer/Older links preserving `q`. No backend/storage/test changes. Version bumped to **1.15**.

## 2026-06-18 (v1.14 — Activities curate: preserve page/sort/filter on action)
- **Acted on Spot Feedback #18 (gbcanoy, `/reports/activities?...&page=2`).** Renaming/merging/re-filing/archiving from the "Edit & merge activities" list dumped the curator back to page 1: `activity_bulk` (`app.py`) redirected to a bare `/reports/activities?{ok|err}=msg`, discarding the `page`/`sort`/`org`/`period`/`q` scope the GET route reads. On a multi-page list (PAGE_SIZE=25) every curate action lost their place.
- **app.py:** added a `_back(key, msg)` closure in `activity_bulk` that rebuilds the redirect from the submitted scope params (`urlencode`) and routed all four exit points through it (success, "pick an action", "no matching activities", empty-title). Imported `urlencode`.
- **templates/activities.html:** `#curateForm` now carries `sort`, `q`, `page` hidden inputs (it already posted `org`/`period`), so the POST knows which page/sort/search to return to. The client-side "✓ Done editing" toggle never navigated — the page-1 jump was purely the action submit, now fixed.
- **Safe on shrink:** if the last row on a page is archived, the GET route already clamps `page` to the valid range, so the curator lands on the nearest existing page rather than an empty one. Version bumped to **1.14**.

## 2026-06-18 (v1.13 — Home-page perf: index the hot stats joins)
- **Acted on Spot Feedback #17 ("the response is a bit slow", home page, admin Ray).** Root cause: `home_stats()` (`app.py`) computes 4 metrics × 4 time windows (All/YTD/Quarter/30-day) and the top-2-box satisfaction query joined `answer` (396K rows) → `response` (36K) → `form_instance` with **no indexes on any of those three tables**, so every windowed metric did a full `SCAN answer` — `EXPLAIN QUERY PLAN` confirmed `SCAN a`. Memoised, so it only bites on cold start (worker restart, day rollover, any new response) — exactly the "after the app wakes up" sluggishness reported, and the same cold-start class as the atoms-rebuild work that never covered `home_stats`.
- **storage.py:** added three `CREATE INDEX IF NOT EXISTS` to the schema bootstrap (beside `idx_attendee_event_email`): `idx_answer_response ON answer(response_id)`, `idx_response_submitted ON response(submitted_at)`, `idx_response_form_instance ON response(form_instance_id)`. Created idempotently by `init_db()` at startup, so the live DB picks them up on the next boot — no manual DB surgery, and harmless if re-run.
- **Verified:** on a scratch copy of the live DB, the windowed satisfaction queries dropped ~78 ms → ~21 ms each (4-window block 356 → 190 ms; the irreducible all-time full scan stays ~125 ms), halving cold `home_stats`. Post-fix `EXPLAIN QUERY PLAN` now reads `SEARCH … USING COVERING INDEX idx_response_submitted` / `idx_answer_response` instead of `SCAN`. `init_db()` on a DB copy creates all three cleanly (schema script parses). Benefits every dashboard/report page on these joins, not just home. Feedback #17 replied to + marked **Done**. Version bumped to **1.13**.

## 2026-06-18 (v1.12 — Single-activity downloads: scorecard, not a one-point timeline)
- **The per-activity person download (visual=person + `event_id`) no longer renders a degenerate "Scores over time" — a single session has exactly one trend point, so the timeline was a lone dot / one-row table across all four formats.** Replaced with a one-time-engagement scorecard. Threaded a `payload["single"]` flag (set in `app.py` `_visual_payload` when `event_id` resolves) so the normal all-time person report is untouched (guarded).
- **dashboard_export.py:** new `_fig_person_single()` — headline score (+ band, respondents, "scoring {cmp.phrase}") with the dimension breakdown given full width (PNG/JPEG). `_tables()` person branch swaps the "Scores over time" table for a one-row **"This session"** summary (Score · Band · Respondents · Bureau average · Difference) when `single`.
- **dashboard_docs.py:** `person_pdf`/`person_pptx` skip the "Scores over time" figure-block / slide when `single` — the PDF Summary box and the PPTX hero slide already carry the headline scorecard, so nothing is lost.
- **Bug fixed (same change):** the download's "vs average" comparison computed the bureau benchmark from the **single-session slice itself**, so it always read "right around the average of X" (score vs itself). `app.py` now sources the benchmark — and the TA "vs the norm" context (`bureau_dims`) — from the FULL atoms (`bench_src = atoms_all if single else atoms`) for the single case. Verified: Vlanche April Dulfo @ *Reorientation to PK Excel Workbook* now reads **6.8 vs the real bureau average 6.5 ("above")** instead of the bogus 6.8-vs-6.8.
- **Verified:** all 5 formats (pdf/pptx/xlsx/png/csv) for the single engagement render with no "Scores over time" (CSV/table scan confirms) and the corrected comparison; PNG layout eyeballed (headline + full-width breakdown, footnotes clear). Regression: the normal person report still carries "Scores over time" + "Year on year" + "Peer standing". **Full pytest 395 green.** Version bumped to **1.12**.

## 2026-06-18 (v1.11 — Per-activity resource-person engagement reports)
- **A resource person now has a per-activity drill-down — their own scorecard + downloadables for ONE activity, scoped strictly to their speaker review (never the activity aggregate).** Covers BOTH invited/outside and bureau-led activities, gated to `event_date ≥ 2026-06-15` (`di.RP_ENGAGEMENT_SINCE`) — the date before which the data is too messy to break down cleanly per activity. Motivation: the existing person report blends every session together and the activity report has no per-speaker drill, so "how did RP X do at this one activity" had no home or export.
- **dashboard_insights.py:** new `RP_ENGAGEMENT_SINCE = "2026-06-15"` + `rp_activity_engagements(events, rp_id, since)` — filters `build_events()` output to activities on/after the cutoff that the person spoke at, returning one row each with the person's OWN F3 score (`shown`/`band`), respondents, and a `kind` tag (`outside`|`bureau`, plus `is_external`). Newest first.
- **app.py:** `GET /dashboard/people/{rp_id}/activity/{event_id}` — guards on (activity exists, `date ≥ cutoff`, person is a speaker) then scopes via new `_person_event_atoms(atoms, rp_id, instance_ids)` (the person's `survey_type==3` atoms within that event's instances) and reuses `person_card`/`person_dimensions`/`story_panel`/`ta_advice`. The person route (`dashboard_person`) now also passes `engagements` (memoised `build_events`). The `visual == "person"` export branch gained an `event_id` scope: same per-person×activity slice, peer-standing/year-on-year/badges suppressed (meaningless for one session), meta title/place/period reframed to the activity. The export route already carried the `event_id` param.
- **Templates:** `templates/person.html` gained a "Per-activity engagements" panel (list with per-row Invited/Bureau-led chips, linking to the detail page); new `templates/person_activity.html` (focused scorecard reusing the `_story`/`_export` macros, conditional "Invited engagement" vs "Bureau-led activity" badge, Download dropdown pointing at `visual=person&event_id=…`).
- **Verified (TestClient, on the live DB copy, no writes):** outside engagement (Vlanche April Dulfo @ *Reorientation to PK Excel Workbook*, build-events id 11568) renders 200 with her 6.8/7 "Excellent" · 164 ratings, dimension bars, session verbatims, TA coaching; all 4 download formats return valid files (PDF/PPTX/XLSX/PNG). Bureau-led path exercised by lowering the cutoff in-process against bureau event 9141 → 200 with the "Bureau-led activity" badge + "As speaker" 6.8 panel + all 4 exports. Guards confirmed: pre-cutoff and non-speaker requests 303-redirect / 404. Production has 0 bureau-led activities since the cutoff yet (only the 1 outside), so the Bureau-led row appears automatically once a post-cutoff bureau activity collects ratings. Version bumped to **1.11**.

## 2026-06-17 (v1.10 — Recent activities window: 30 days → 7 days)
- **Home "Recent activities" strip now spans the last 7 days instead of 30.** The count next to the heading (was "59" under the 30-day window) is just `len(my_activities)` — the rows `storage.activities_by_creator` returns after collapsing each bureau event to one row and filtering by `event_date` within the window (NULL/future dates always kept). Narrowing the window to a week drops the count to this week's activities only.
- **app.py:** both call sites in the home route pass `since_days=7` (was `30`) — the admin `all_creators=True` branch and the section-manager branch. No storage change: `activities_by_creator(..., since_days=N)` already keys on `event_date`. Verified live (admin) 59 → 7.
- **templates/home.html:** the strip's sub-line copy updated "last 30 days" → "last 7 days" (both the admin and manager wordings).
- **Verified:** `storage.activities_by_creator(since_days=7)` returns 7 rows vs 59 for `30`/`None` (the 30-day list happened to hit the strip's 60-row collapse cap, hence the matching 59); existing `tests/test_my_activities.py` still green (it exercises the `since_days` parameter directly, not the route's chosen window). Version bumped to **1.10**.

## 2026-06-17 (v1.7 — Archive standalone activities)
- **Admin/creator can now archive a STANDALONE activity (a Form-3 speaker review with no event record) and restore it — closing the gap the event-level archive couldn't reach.** Motivation: 4 ongoing speaker reviews with 0 responses needed to come off all lists/counts without a destructive delete; `form_instance.archived=1` already removes a row from every analytic (`storage.py` `_LOAD_SQL` `WHERE COALESCE(fi.archived,0)=0`) and feed, but `set_event_archived` only reaches forms joined through `event_form`, so standalone forms had no UI path.
- **storage.py:** new `set_form_archived(conn, fid, archived)` (sibling of `set_event_archived`) and `form_archive_info(conn, fid)` (creator + archived state + whether it belongs to an event, for the route's auth + refusal check). `activities_by_creator` gained an `archived` flag (0=live strip, 1=Archived page) and now returns `fid` + `archivable` (True only for standalone forms) per row.
- **app.py:** `POST /activities/form/{fid}/archive` (restore=1 to undo) — refuses missing/bureau-event forms, authorizes via the existing `_can_manage_event` rule (creator or admin), then `set_form_archived` → `invalidate_atoms()` → `_audit("form_archive")`; archive redirects home, restore redirects to the Archived page. `GET /activities/archived` (gated on `manage_event`) lists the manager's archived standalone activities (admins see all creators') with a Restore button.
- **Templates:** home "Your recent activities" strip gained an inline **Archive** button per standalone row (sibling to the row link, not nested) + a "View archived activities →" footer link; new `templates/activities_archived.html`.
- **Verified:** new `tests/test_form_archive.py` (archive drops it from the strip + `ongoing_standalone`, creator/admin allowed + other manager refused, restore round-trip, bureau-event form refused) + full suite green; live click-through on the home strip → Archive → Archived page → Restore. Version bumped to **1.7**.

## 2026-06-11 (External directory fields + fresh-start wipe)
- **External resource persons get structured fields: honorific, agency, email.** `agency` column added to `resource_person` (schema + migration + `add_rp`/`update_rp`/`list_resource_persons`); `honorific` + `email` already existed. New **dedicated add/edit form** for external RPs (`templates/external_rp_form.html` + routes `GET/POST /directory/external[/{id}][/new|/edit]`), kept separate from the plantilla-shaped internal `staff_form.html`: honorific dropdown (Mr./Ms./Mrs./Dr./Engr./Atty.), required name, optional agency + email. The directory's External section now shows Name/Agency/Email columns + an Edit link, and a "+ Add external resource person" button. Verified: add/edit roundtrip persists all fields, internal-via-external-edit guard redirects, directory renders the new columns.
- **Wiped the entire external resource-person registry for a fresh start** (user request — "remove them all"). `wipe_external_rps.py`: set-based, child→parent deletes with FK enforcement off for the batch + a `PRAGMA foreign_key_check` that PROVES no dangling refs before commit. Removed **155 external RPs + 954 Type-3 speaker forms + 5,290 responses**; **45 BLHSD staff and all Type-2 event data untouched** (event feedback is keyed by activity/org, not resource_person). Consistent backup `_backups/css_is_20260611_232703_pre_external_wipe.db`; result: 0 orphans, fk_check clean, integrity ok, audit chain ok, `external_wipe` audited. (Lesson: `cp` of the live DB makes a torn snapshot → use the SQLite backup API for copies; row-by-row `delete_speaker` tripped the `event_form`/`response` FKs, so the wipe is set-based.)
- **Note:** done under explicit "allow everything, I'll check afterwards" authorization while a parallel honorific workstream was co-editing `app.py`/`name_cleanup.py`/`staff_form.html`. Verified my edits survived. pytest + qa_smoke green; the dev server was down (nothing on :8000) so the in-place wipe had no lock contention.

## 2026-06-11 (Home hub — task-oriented landing)
- **NEW role-aware home at `/` ("What would you like to do?")** replacing the old landing behaviour (managers were dropped straight onto the create-activity form; everyone else onto Pulse). `templates/home.html` extends the dash layout (top nav stays). A **glanceable stats strip** — responses in the last 30 days, people rated (distinct non-archived speakers/staff), overall satisfaction (top-2-box % positive, computed per each survey type's scale: ARTA 1-5, F2/F3 1-7), and all-time responses collected — over a grid of **task-module cards filtered by capability**: *See how we're doing* (`/dashboard`, all) · *Official reports* (`/reports`, all) · *Enter paper responses* (`/encode`, encode) · *Run a survey* (`/create`+`/arta`, create_activity) · *Directory & people* (`/directory` incl. the name cleanup tool, directory) · *Administration* (users/audit/backups/health, manage_users). Each card has a primary link + sub-link pills. No new permissions — cards gate on the existing capability map.
- **Routing:** the create-activity form moved from `GET /` to **`GET /create`** (it always lived behind the `create_activity` cap via `/create`'s gate; the POST handler was already there). `home_stats()` memoises the heavy atoms calc against the atoms cache + current month; the open-survey count is a tiny live query. Nav updated: brand → `/`, "New survey" → `/create`, new `home` active-state.
- **Verified:** renders 200 for every role with the right card count (viewer 2 → encoder 3 → section_manager 4 → admin 6); stats compute (111 this month, 82% positive, 40,986 all-time); `GET /create` still serves the form; live screenshot of the admin hub. pytest + qa_smoke green; production `css_is.db` untouched.

## 2026-06-11 (Name cleanup tool — external resource-person directory)
- **NEW temporary admin tool `/directory/cleanup`** to fix the resource-person roster fast (user request: "create a temporary UI at the directory to help me fix all of this names faster"). Directory-gated (section_manager+); linked from the top of `/directory`. Lists all 218 resource persons with auto-detected flags — **ALL-CAPS** (11), **honorific prefix** (125), **roster** (one field holding several people, 17), and **duplicate candidates** (92) — plus client-side search + filter chips with live counts.
- **Per-record one-click actions:** proper-case an ALL-CAPS name (`RAY JUSTIN VENTURA`→`Ray Justin Ventura`, preserving initials `T.`/roman numerals/credentials), strip leading honorifics (`Dr.`/`Ms.`/`Ma'am`… — but NOT Filipino `Ma.`=Maria), inline rename, archive/hide a non-person, **merge** a duplicate (one-click "fold in" for each suggested dupe, or pick any record via a shared datalist), and **split** a roster (each parsed name pre-resolved to the best-matching existing person via a dropdown, with skip; ratings are duplicated to every individual). Bulk "Fix all ALL-CAPS" button.
- **Backend `name_cleanup.py`** reuses the proven `apply_speakers` machinery (`merge_speaker`/`copy_instance_to`/`delete_instance`/`split_roster`) so a split duplicates each session's ratings per person exactly as the earlier roster passes did. A higher-recall candidate matcher (token-subset / shared-token / typo-fuzzy) surfaces sub-name duplicates `storage.names_match` misses (`Corachea`⊆`Andrea Corachea`, `Ross Rosales`⊆`Dr. Ross Jacob Rosales`). **Internal-name rule enforced:** a merge involving exactly one internal (plantilla) record always keeps the internal record as the survivor, regardless of merge direction.
- **Safety:** first destructive op of a server run takes one automatic `_backups/css_is_*_precleanup.db` snapshot (plus a manual "Save restore point" button); every op is audited (`name_cleanup`/`name_cleanup_merge`/`name_cleanup_split`/`name_cleanup_backup`) and busts the atoms cache. Nothing is auto-applied — the operator confirms each change.
- **Verified:** all ops exercised on a DB copy (rename/strip/title-case/archive/merge incl. internal-protection swap/split) → 0 orphans, audit chain intact; full HTTP layer driven via TestClient on a copy (all routes 303, audit rows written, chain ok); live UI screenshotted (filters, merge fold-in suggestions for Andrea Corachea, split of `Rosales, Loyola, Gawilan, Garcia, Baldonado` each pre-resolved). **pytest 109 passed**; production `css_is.db` untouched by the build.

## 2026-06-10 (QA pass — Cowork)
- **P0 (app down) FIXED:** `app.py` was truncated mid-statement (SyntaxError) — the build did not start. Truncation also dropped `_token_of`/`_qr_data_uri`/`_build_qrs`, which `/create` and `/arta` call (would NameError). Restored tail from snapshot + reconciled with current code. 2278→2324 lines.
- **P0 (Activities 500) FIXED:** `templates/activities.html` truncated mid-tag (`{% en`) → Jinja TemplateSyntaxError on `/dashboard/activities`. Restored the pager block. 151→157 lines.
- **P1 (process):** `.git` is an empty skeleton (0 objects/commits) — the claimed "git per cycle / revert to roll back" safety net never persisted in this mount. Root cause of both P0s: in-app file tools silently truncate large files. Recommend shell-only edits + a real repo on the host, and `python -c "import app"` as a delivery gate.
- **NEW regression suite:** `tests/` (pytest, 84 tests: routes/auth+RBAC/input-abuse/integrity), `pytest.ini`, `run_tests.sh`. Runs on a throwaway DB copy.
- **qa_smoke.py:** added backward-compatible env knobs (QA_SAMPLE/QA_FORMATS/QA_GRAINS) for a fast subset; defaults unchanged.
- **Verified green:** 84/84 pytest pass; export smoke passes all 6 formats; `integrity_check=ok`, 0 orphans, unique tokens; 40,935 responses / 449,423 atoms; PERF-3 resolved (Activities ~0.22s warm). `css_is.db` not modified. Originals in `_backups/qa_20260610_210455/`. Full report: `QA_FINDINGS_2026-06-10.md`.

## 2026-06-11
- **Performance monitoring + audit hooks — completes the "perf monitoring + backups" task.** New `monitoring.py`: in-memory rolling window (last 2000 requests) behind a thread lock, exposing the **four golden signals** — traffic (req/min, totals), latency (p50/p95/p99/max over 5 min), errors (5xx/4xx counts + rate), saturation (in-flight + peak, slow >1s count, DB size + growth-since-start). Path bucketing collapses ids/tokens (`/r/{token}`, `/directory/person/{id}/edit`) so the per-route table stays low-cardinality. Structured **per-request JSONL log** → `requests.log` (size-rotated at 5 MB → `.1`; best-effort, never breaks a request). A second outermost `@app.middleware` (`_metrics_gate`) times every request, counts by status (records 500 on handler exceptions), and logs it. **`GET /health`** — public liveness/readiness JSON (process up + `SELECT 1`; 200 ok / 503 degraded). **`GET /ops`** — admin dashboard (gated via `_required_cap` → manage_users): golden-signal cards, integrity+backup status (audit-chain check + backup schedule), per-route latency table, recent-request log tail; template `templates/ops.html`; nav link added. DB-growth baseline captured at startup. **Missing audit hooks added:** login (`login`/`login_failed`/`first_run_admin`), `logout`, and directory CRUD (`directory_add`/`directory_edit`/`directory_delete` for divisions/sections/bureau/people/external-orgs/photos, plus `clear_sample_data`). Verified: 9 new pytest in tests/test_monitoring.py (bucketing, percentiles, snapshot signals, health payload, /health public, /ops admin-only, logout/directory/failed-login audited) + full suite **109 passed**; qa_smoke 122 pass; live-checked /health + /ops on a demo copy (golden signals, per-route table, audit entry); production css_is.db untouched. Added `.gitignore` for runtime artifacts (requests.log, _backups/scheduled/, css_is_demo.db). Note: the metrics store + scheduler live in the single uvicorn worker (the documented run mode); /ops shows since-process-start, not historical.
- **Admin Backups module (/admin/backups) — easy self-service scheduled backups.** New `backups.py` engine: consistent snapshots via the SQLite backup API into `_backups/scheduled/` (separate from the hand-made pre-cleanup snapshots, never pruned together); make/list/prune/delete/restore + schedule config (in a new `app_setting` key/value table) + pure `is_due`/`next_due` arithmetic. In-process async scheduler (startup hook, 60s tick, `CSS_NO_SCHEDULER=1` opt-out) fires `run_scheduled_job` = **backup → prune to "keep newest N" → 6-month attendee-PII purge** (folds in the retention rule). Admin UI: status header (ON/OFF, next due, counts/sizes), schedule form (frequency h6/h12/daily/weekly + time + weekday + keep N + purge toggle), "Back up now", and a snapshots table with Download / **Restore** (typed RESTORE confirm + auto pre-restore safety snapshot, then `invalidate_atoms()`) / Delete. Routes under `/admin/backups*` (admin-only via the existing `/admin`→manage_users gate); every action audited (`backup_run`/`backup_settings`/`backup_restore`/`backup_download`/`backup_delete`/`backup_failed`). storage: get/set/get_settings. Verified: 11 new pytest in tests/test_backups.py (schedule math, prune-keeps-pre_restore, restore round-trip, job purges, RBAC, restore-needs-confirm) + full suite **100 passed**; qa_smoke 122 pass; live click-through on a demo copy (back-up-now → schedule ON/Weekly → next-due 2026-06-17 23:30 → snapshot row); production css_is.db untouched. Part of the queued "performance monitoring + backups" task (backups slice; golden signals / /health / /ops / request logs / directory+login audit hooks still to come).
- **E — Event link tree + attendee identity capture (Data Privacy Act).** New persistent `eve
## 2026-06-11 (UX redesign — Cowork, full execution)
- **ROOT CAUSE of recurring truncations found:** the agent-workspace mount truncates/zero-pads file tails when syncing large files. All file writes in this pass were made shell-side and verified (`python -c "import app"`, Jinja parse, null-byte scan) after every step; a real git history now exists for rollback (tags `pre-redesign` → `redesign-v1`).
- **P0 repairs before redesign:** `app.py` tail (dashboard routes + `_crumbs`/`_scope_ctx`/`_scoped`/`_nresp`, `/dashboard/report-pack` tail, `_token_of`/`_qr_data_uri`/`_build_qrs`) restored from `_backups` + bytecode; `storage.py` rebuilt 6 dropped functions (`load_atoms`, `get_form_context`, `search_form_instances`, `set_lead_org`, `lead_org_of`, `set_response_window`) from the cpython-314 bytecode constants — atoms SQL recovered verbatim; `dashboard_export.py` `_pack_pptx` tail; `dashboard_insights.py` `_rp_event_overalls` tail; `tests/conftest.py` `sample_ids` tail; `harmonize.py` `__main__` tail; null bytes stripped from `import_csm_blhsd.py`/`harmonize_report.md`; truncated sandbox copies of `encode_home/encode_form.html` re-mirrored. **`css_is.db` was corrupt (failed integrity_check)** — replaced from the newest clean snapshot `_backups/css_is_20260611_180449_prerosters.db` (41,092 responses, integrity ok); corrupt copy kept as `_backups/css_is_CORRUPT_kept_20260611.db`.
- **UX redesign (REDESIGN_PLAN.md, all phases):**
  - *Design system:* new `static/css/app.css` (tokens, components, focus rings, print/reduced-motion) + `static/js/app.js` (loading states, confirms, survey progress, expand/collapse, nav) + `templates/_components.html` macros + `templates/public_layout.html`; `/static` mounted & public-prefixed.
  - *Navigation:* `dash_layout.html` rebuilt — grouped role-aware dropdown nav (Dashboard / Data entry / Manage / Admin) with `aria-current`, mobile hamburger, breadcrumb block. Verified per role: viewer sees only Dashboard; admin sees all four.
  - *Every authenticated page now shares the layout:* converted `form_create`, `directory`, `staff_form`, `reports`, `verbatims`, `arta_link`, `result` from standalone HTML.
  - *Respondent (public) screens* rebuilt mobile-first on `public_layout`: `rating.html` (progress bar, question count + time estimate, equal-width segmented scales with end anchors, neutral N/A, anonymity note), `link_tree` (field-level required/optional marks, consent required client+server), `thanks` (what-happens-to-my-answers note, sequence celebration), `sequence`, `closed`, `login`, `forgot`, `set_password`.
  - *Manager dashboards:* activities — manager forms collapsed behind “⚙ Manage this event”, Expand/Collapse-all, clearer score labels; pulse — real empty states, sparkline aria-labels; people — affiliation counts now respect the active search, search-term highlighting, “no ratings yet” microcopy; person — breadcrumbs; reports — “How to read these numbers” legend (bands/flags/gap thresholds/item codes), report-pack download on page; verbatims — **pagination (?page=, 50/page replaces the hard 300 cap)** + survey-type filter pills + breadcrumbs.
  - *Encoder:* encode_home — public-window status column (Always open/Open/Not yet/Closed), Date/Responses sort, ＋New survey button; encode_form — sticky save bar with session counter + “Done — back to forms”, per-section counters, numbered items, neutral N/A, collected-on help text, mobile-stacking CSM grids.
  - *Feedback & a11y:* role-change now Apply-button + confirm (was silent auto-submit), deactivate confirms, audit log ip-toggle/was-now diff labels/chain-broken recovery hint, `data-loading` submit states, `:focus-visible` rings, `.table-wrap` overflow guards.
- **Behavior changes (exhaustive):** /static mount; verbatims pagination params; people counts after search; encode_home `sort` param + window state; users role-change needs Apply click. All form field names/values, routes, RBAC and POST semantics unchanged.
- **Verified:** full pytest suite green in chunks (**109/109**: rbac 41, routes 24, event_e 5, input_abuse 9, integrity 10, monitoring 9, backups 11); live TestClient walk-throughs — all 4 roles' nav + page access, full respondent journey (/e consent → /r rating → thanks → sequence-next), server-side consent/email validation, export PNG + report-pack PDF byte-checked. Work done on DB copies; the restored `css_is.db` only changed by the corruption fix above.
ck-office: bypasses the response window, defaults items to N/A, adds a "Date collected" field stored as `submitted_at` (the period a walk-in slip counts in). Every save audited as `manual_entry`; views invalidated.
- templates/encode_home.html, encode_form.html: NEW. dash_layout.html: `✎ Paper entry` nav link gated on `can(role,'encode')`.
- Verified end-to-end over HTTP on a temp DB copy (walk-in ARTA + Type-3 SERVQUAL, RBAC 403/404/redirect). Production css_is.db untouched; qa_smoke 122 checks pass.

## 2026-06-09
- migrate.py, verify_migration.py: NEW — idempotent migration of legacy spreadsheets + verifier.
- app.py: harden public `POST /r/{qr_token}` against malformed/out-of-range/hostile input and invalid served_by (BUG-1).
- app.py: anchor Jinja2 templates dir to module path so the app runs from any working directory (BUG-2).
- css_is_engine.py: assign_periods uses errors="coerce
