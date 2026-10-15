# Documents Management — phased incremental development plan v1

**Status:** D1–D11 application implementation added behind disabled switches; acceptance and live-integration gates remain open. See [implementation/setup evidence](DOCUMENT_MANAGEMENT_SETUP.md).
**Owner decisions recorded through:** 2026-10-15.
**Repository baseline:** main at a6bcb64a451611535d9e3a9b6a61b93f2690aeed; recheck integration points before each implementation PR.
**Launch:** bureau-wide introduction with a trial period, covering incoming and outgoing documents.
**Scope boundary:** new documents from an agreed cutover date; historical import is a later increment.
**Tracking:** mark an increment complete only after its acceptance evidence is linked here. A merged plan is not evidence that a feature is built.

## 1. Purpose and evidence

Office Connect becomes BLHSD's main document registry. DTRAK numbers remain external references.
A document must be traceable from receipt or preparation through assignment, action, review,
signing, dispatch, and closure. The existing staff directory and office workflows remain the
shared foundation.

The current [receiving spreadsheet](https://docs.google.com/spreadsheets/d/1BuGpGIIxI_-HUSarA1EXKrz73nFGLbLCRPGbvaWZCQ4/edit)
was reviewed as a downloaded snapshot on 2026-10-14. It has January–October tabs and 1,604 rows
with a received date or control number, excluding placeholder-only rows. These are register
rows, not a verified count of unique documents. Findings informing this plan:

- 131 rows use BOTH DIVISIONS: one lead must coordinate multiple independent contributions.
- 871 rows have an action note but no process-owner response date: missing dates cannot mean overdue.
- Control numbers include repeated references, multiple references, and 16 cells stored as dates.
- Scan, remarks, and processing-time columns change meanings across months.
- Outgoing responses are embedded in action notes; the sheet is not a complete outgoing registry.
- Forwarding, attending, filing for reference, signing, and responding have different completion conditions.

The sheet informs workflow design; it is not imported by this plan or included in the repository.

### 1.1 Existing capabilities and reuse boundaries

| Existing source | Reuse | Boundary |
|---|---|---|
| [storage.py](../storage.py), [auth.py](../auth.py) | Accounts, staff/unit directory, chief hierarchy, OIC designation, holiday calendar | Document permissions must be explicit; technical admin is not automatically a records officer, signatory, or unrestricted reader |
| [office_connect.py](../office_connect.py), [app.py](../app.py) | Home tasks, approvals page, navigation, bell | Register document sources without duplicating queues or changing unrelated module permissions |
| [search_sources.py](../search_sources.py) | Scoped record search | Apply the same document access predicate to titles, counts, snippets, exports, and detail pages |
| [office_calendar.py](../office_calendar.py), [calendar_routes.py](../calendar_routes.py) | Calendar suggestions, existing event matching | Human confirms creation/linking; no automatic invitation-to-CSS conversion |
| [rooms_notify.py](../rooms_notify.py), [send_reminders.py](../send_reminders.py), [mailer.py](../mailer.py) | Notification builders, scheduler, feature settings, retry patterns | Official dispatch needs durable evidence; expiring/skipped notices are not proof of release |
| [gdocs_relay.py](../gdocs_relay.py), [travel_docs.py](../travel_docs.py) | Signed relay interface, fakeable adapter, request identifiers | Existing travel generation is not general extraction, signing, access enforcement, or official dispatch |
| [TRAVEL_DOCS_RELAY_SETUP.md](TRAVEL_DOCS_RELAY_SETUP.md) | Deployment and live-check checklist pattern | The travel documentation reports outstanding live Google checks; do not assert production readiness |
| [calendar_import_apply.py](../calendar_import_apply.py) | Review-before-apply and repeat-import protection | Historical document import is deferred; do not infer closed/pending from blank cells |
| [backups.py](../backups.py), [retention.py](../retention.py) | Database recovery and scheduled maintenance | DB backup does not back up Drive files; survey/travel/email retention windows do not govern correspondence |
| [report_docs.py](../report_docs.py), [dashboard_docs.py](../dashboard_docs.py) | Report export conventions if useful | These generate survey reports; they are not an existing correspondence registry |

Keep FastAPI, Jinja, and SQLite initially. This volume does not itself require a platform or
database migration. Assess the deployed version, identity links, holiday coverage, and existing
test baseline before implementing. Repository code is not proof of deployed configuration.

## 2. Confirmed requirements and traceability

The following decisions are accepted requirements. Proposed mechanics and unresolved details
are labeled separately in sections 3–10.

| ID | Confirmed requirement | Primary increments |
|---|---|---|
| R01 | Office Connect is the main BLHSD registry; DTRAK is an external reference | D1, D2 |
| R02 | Any staff member may register incoming documents; receiving/Admin staff, concerned division chiefs, and the Director may verify | D1, D2 |
| R03 | Manual entry and assisted extraction both belong in the first release; staff confirm extracted values before submission | D2, D9 |
| R04 | Separate automatic annual incoming/outgoing numbers: BLHSD-IN-2026-000001 and BLHSD-OUT-2026-000001 | D1, D2, D6 |
| R05 | Outgoing numbering occurs at initial draft registration; canceled documents retain their numbers/history | D1, D6 |
| R06 | A rules UI uses document type and keywords to propose routing and immediately notify the Director and concerned officers/staff | D3, D4 |
| R07 | Notifications and preliminary work start before verification; mark entries Awaiting verification | D2, D3, D4 |
| R08 | Before directives, permit acknowledgment, gathering information, internal coordination, and drafting; external responses/commitments require authorization | D3, D6, D8 |
| R09 | Rules propose a lead; verifying officers may confirm/change it; Director may override | D3 |
| R10 | Conflicting lead suggestions notify all suggested units; authorized officers resolve ownership | D3, D4 |
| R11 | Rules propose section/staff assignments; division chief may confirm/change them | D3 |
| R12 | Multiple contributors have internal deadlines reserving time for consolidation/approval; rules propose dates; lead/chief may adjust with reason | D3, D5 |
| R13 | A changed Director directive notifies affected people, preserves prior work, and requires lead reconciliation | D3, D4 |
| R14 | Existing designated OIC covers approvals; concerned division chief or Director may reassign staff tasks with logged changes/notices | D1, D3, D6 |
| R15 | Use stated deadline or document-type default; authorized officers may adjust with recorded reason | D5 |
| R16 | Working days are Monday–Friday excluding holidays; explicit weekend/holiday deadlines remain unchanged | D5 |
| R17 | Reminders at three working days before, one working day before, and on due date; immediate urgent/short-notice alerts | D4, D5 |
| R18 | Once overdue, notify assignee/lead, then escalate to chief and Director at configurable intervals | D5 |
| R19 | Awaiting external response does not pause deadlines; extensions need authorization/reason | D3, D5 |
| R20 | Use both in-app and email notifications; assignments, urgent items, and approval requests alert immediately | D4, D5, D6 |
| R21 | Chiefs approve routine responses within authority; policy decisions/commitments go to Director/OIC; rules propose level and chief confirms/escalates | D6 |
| R22 | External signing and stored-signature application both belong in first release; only the signatory may apply their own signature after final review | D7 |
| R23 | Log minor formatting/typographical changes without renewed approval; substantive changes require renewed approval | D6, D7 |
| R24 | Assigned staff, concerned chief, Director, or receiving/Admin staff may release authorized documents | D8 |
| R25 | Release evidence depends on document type/channel; support existing-email dispatch recording and direct official-email sending | D8 |
| R26 | Before verification, visibility is submitter + authorized verifying officers + staff identified by routing rules | D1, D2, D3 |
| R27 | After verification, bureau-wide visibility is default; only receiving/Admin staff, chiefs, and Director may mark restricted/manage access | D1, D2 |
| R28 | Files stay in Drive; staff manage Drive permissions; check access where possible without automatic permission changes | D2, D7, D9 |
| R29 | Closure requirements vary by document type/action; reopening allowed to lead, concerned chief, Director, or receiving/Admin staff with reason/notices | D10 |
| R30 | Only designated workflow administrators edit routing rules, deadline defaults, and closure requirements; log changes | D1, D3, D5, D10 |
| R31 | Warn on possible duplicates; authorized verifying officers can link receipts or merge duplicates preserving references/files/history | D2, D10 |
| R32 | Suggest calendar entries for confirmation, checking existing events first | D11 |
| R33 | Launch bureau-wide with a trial period, both directions, new records from cutover; import history later | D12, D13 |

## 3. Proposed domain and workflow contract

### 3.1 Separate verification, workflow, assignments, and visibility

Do not make one overloaded status represent every dimension.

- Verification: pending, verified, needs_correction.
- Incoming workflow: registered, in_action, awaiting_external, ready_to_close, closed, cancelled.
- Outgoing workflow: draft, in_review, changes_requested, approved, ready_to_release, released,
  awaiting_acknowledgment, closed, cancelled.
- Assignment: proposed, assigned, acknowledged, in_progress, submitted, completed, superseded.
- Visibility: preverification scope, bureau, or restricted.
- Derived badges: overdue, due soon, unassigned, directive needs reconciliation, approval invalidated.

Exact user-facing labels are reviewed in D0. Status transitions are server-side actions with
actor checks, expected revision, evidence requirements, timestamp, and audit event.
A notification is not acknowledgment. Forwarding is not completion. Approved is not signed.
Signed is not dispatched. Transport acceptance is not recipient acknowledgment.

Incoming:
Register -> verify (in parallel with early work) -> directive/assignment -> action ->
linked outgoing response where needed -> satisfy type-specific closure rule.

Outgoing:
Register draft/allocate number -> confirm approval route -> review/revise -> approve exact
version -> sign where required -> satisfy release checklist -> dispatch -> acknowledgment
where required -> close.

An outgoing document may be independent, reply to several incoming documents, or be one of
several replies to one incoming document. Use typed many-to-many links, not a single reply field.
A received response may also reopen or relate to an existing thread.

### 3.2 Proposed data model (additive, finalized in D1)

| Entity | Responsibilities |
|---|---|
| document | Permanent ID, direction, official number, subject/type, origin/recipients, received/document dates, verification/workflow state, priority, visibility, lead, due date, revision |
| document_sequence | Transactional sequence per year/direction; unique number; no reuse after cancellation/merge |
| document_reference / document_relation | DTRAK and other textual references; replies, follow-ups, related records, canonical merge redirects |
| document_receipt | Each receipt channel/time/sender/evidence, including repeated delivery of the same document |
| document_assignment | Unit/person, lead/contributor role, action, acknowledgment, internal due date, outcome, supersession history |
| document_directive | Issuing officer, instruction text, timestamp/version, affected assignments and reconciliation |
| document_file_version | Drive file ID/link, document role, version/revision evidence, fingerprint where available, author, final/signed classification |
| document_review / document_signature | Review stage, authorized actor, exact reviewed version, decision/reason, signing execution and artifact evidence |
| document_dispatch / document_dispatch_recipient | Channel, sender, final version, recipient outcomes, evidence, attempt identifiers, acknowledgment |
| document_event | Append-only business timeline; original event time and recording time; linked to platform audit |
| document_rule_version / document_match | Versioned conditions, proposed actions, precedence, explanation, evaluation snapshot |
| document_access / document_role_grant | Explicit restricted viewers and scoped records/workflow permissions |
| document_notice / document_job | Durable notification and external-operation jobs, deduplication keys, attempts, outcomes |
| document_import_batch | Deferred D13 provenance, original values, mapping, exceptions, repeat-import protection |

Keep binary documents in Drive. Extracted content, signatures, and previews require defined
transient handling; do not silently create a permanent second file repository.
Store metadata sufficient to identify and verify reviewed/released versions. A mutable URL
alone is insufficient evidence.

### 3.3 Permission contract

All document actions intersect operational authority with document visibility. Workflow
administration does not grant blanket access to restricted document contents.

| Actor | Scope |
|---|---|
| Signed-in staff | Register; view permitted records; work on assignments; initiate outgoing drafts (proposed default to confirm in D0) |
| Receiving/Admin personnel | Verify; route; manage restrictions; resolve duplicates; release/reopen within authorized scope |
| Concerned division chief | Same relevant operational powers; assign staff; confirm review level; approve routine responses; extend/reassign within scope |
| Director / authorized OIC | Direct/override; approve policy decisions/commitments; exercise delegated authority with identity recorded |
| Lead owner | Coordinate, adjust internal contributor deadlines with reason, reconcile directives, reopen; other powers require applicable grants |
| Assigned staff | Preliminary work and authorized release; no implied approval/signature authority |
| Signatory | Apply only their own stored signature to the reviewed final version |
| Workflow administrator | Edit versioned policies; no implied signing, release, or restricted-content rights |

Existing personal-request auto-approval and technical-admin fallbacks must not automatically
authorize document signing or policy commitments. An OIC signs as themselves under recorded
delegation, never by applying another person's stored signature.

## 4. Cross-cutting implementation contracts

1. **Atomic changes:** persist state, business event, audit, and notification/job intent together.
   Review existing internally committing helpers; provide transaction-aware document helpers
   without changing unrelated callers. Rollback must not leave an allocated live record without history.
2. **Concurrency:** expected-revision checks on verification, assignment, approval, merge, release,
   and rule activation. First valid action wins; stale forms show the current actor/time/state.
3. **Numbering:** proposed year boundary is registration time in Asia/Manila, separate from document
   issue date. Concurrent registrations must not collide. Retain aliases after merge and never reuse numbers.
4. **Rules:** editable conditions (type, normalized keywords, field searched, match mode), recipients,
   proposed lead/assignees, defaults, approval class, and closure/release requirements. Include preview,
   explanations, priority/conflict handling, draft/active versions, disable and rollback.
   No arbitrary executable expressions. Existing documents retain applied rule versions; configuration
   changes do not silently reroute active records. Explicit reevaluation shows a diff before applying.
5. **Rule conflicts:** union eligible notification recipients; never silently select among conflicting
   leads. Proposed unmatched fallback is Director plus receiving/Admin verification queue, pending D0 confirmation.
6. **Notifications:** immediate means enqueue on action, then promptly deliver through scheduler.
   Deduplicate by event/recipient/channel; record failure and retry. Recheck access at delivery time.
   Email should use minimal authorized details and an authenticated app link, especially for restricted records.
7. **Deadlines:** use shared holiday data and Manila time. Store explicit/default provenance, policy
   version, original due date, changes/reasons, and internal milestones. Never move an explicit date
   merely because it is nonworking. Missing holiday coverage must be visible.
8. **Short notice:** collapse already-past advance reminders into one immediate notice; do not flood
   users or invent elapsed milestones. Warn when consolidation/approval buffers cannot fit.
   Recompute unsent notices after deadline/assignment changes; retain sent history.
9. **Drive:** allow supported Google links, parse file IDs, and bound fetch size/type/time. Adapter
   access proves access for that adapter identity only, not every staff member. Display that distinction.
   Changing app visibility never changes Drive permissions. Lost access is actionable, not a silent success.
10. **Versions and signing:** review ties to a concrete version; minor edits create an annotated successor
    with diff/reason and preserved approval lineage. Material edits invalidate approval. Any changed
    signed artifact requires the signatory to sign the resulting version again; approval exemption for a
    typo does not authorize altering a previously signed artifact invisibly.
11. **External effects:** use durable operation IDs and explicit outcomes for extraction, signing, and
    sending. A timeout after a possible send must enter unknown/reconcile state, not an unconditional
    resend. Official dispatch evidence survives notification/email-log cleanup.
12. **Authorization:** protect every route and mutation; include CSRF protection for authenticated writes.
    Shared search, calendar, exports, bell, previews, and jobs must enforce document-level visibility.
13. **Extraction:** linked document text is untrusted data. It may suggest fields but cannot activate rules,
    change permissions, approve, send, or execute instructions. Show source excerpts and uncertain values.
    Parsing failure leaves manual entry usable; do not auto-assign based on unconfirmed extracted values.
14. **Recovery:** feature switches disable new work/side effects while preserving existing records and
    controlled read access. Back up metadata and verify Drive artifact availability separately. Do not
    inherit unrelated purge jobs. Retention/disposal needs its own policy.

## 5. Phases, dependencies, and release meaning

Each increment should fit a focused implementation PR. Split further if necessary, retaining
the increment ID and acceptance criteria. All checkboxes start unchecked.

Development phases are NOT permission to reduce the agreed first-release scope.
D1–D11 can merge behind a disabled module switch. D12 is the first operational bureau-wide launch.
It requires manual and assisted entry, both signing methods, both email release methods, and
both incoming/outgoing workflows. Do not silently ship an incoming-only or manual-only release.

| Phase | Increments | Outcome |
|---|---|---|
| Foundation | D0–D1 | Validated contracts, additive schema, authorization, sequence/history foundation |
| Intake and action | D2–D5 | Registration, Drive links, routing, assignments, notifications, deadlines |
| Outgoing lifecycle | D6–D8 | Review, version-specific signing, release and dispatch evidence |
| Completion and integration | D9–D11 | Assisted entry, closure/duplicates, shared UX and calendar |
| Operational launch | D12 | Bureau-wide trial with all first-release gates satisfied |
| Later expansion | D13 | Optional reviewed historical import |

Dependency chain:
D0 -> D1 -> D2 -> D3 -> D4 -> D5;
D3 + D4 -> D6 -> D7 -> D8;
D2 + D4 -> D9;
D3 + D5 + D8 -> D10;
D4 + D5 + D10 -> D11;
D0–D11 + live integration evidence -> D12 -> optional D13.

D9 may proceed alongside outgoing development once its dependencies are complete.
D0 investigates the hardest external dependencies early; development order must not hide
Drive, extraction, signing, or mail feasibility until launch.

## 6. Increment backlog

### D0 — Process catalog, integration feasibility, and acceptance fixtures

- [ ] Capture a representative synthetic/anonymized set: reference memo, urgent request, invitation,
  routine reply, policy commitment, joint-division response, duplicate, revised directive, restricted item.
- [ ] Draft and review the initial type/rule catalog, role matrix, closure/release checklist, screen sketches,
  unmatched fallback, and unresolved policy values from section 10.
- [ ] Check current deployment, directory/OIC links, mail jobs/settings, holiday years, and test baseline.
- [ ] Prove adapter contracts for authenticated Drive access, readable PDFs/Docs, scanned-document extraction,
  exact version identification, signatory-only signing, and official-mail send reconciliation.
- [ ] Document live checks still requiring configured accounts; fakes are not live evidence.

**Deliverable:** reviewed catalog/fixtures and adapter decisions linked from this plan.
**Acceptance:** every confirmed requirement has an implementation/test owner; unresolved items have a
named gate; no provider choice silently changes file storage or permission policy.
**Dependencies:** none. **Boundary:** no live document mutation or outgoing mail during discovery.

### D1 — Schema, permissions, numbering, audit, and feature switch

- [ ] Add document tables/migrations, explicit role grants, access predicates, event/audit model,
  transaction helpers, and disabled-by-default module switch.
- [ ] Add incoming/outgoing numbering with uniqueness and cancellation/merge retention.
- [ ] Map directory chiefs and OICs without broad technical-admin shortcuts.

**Acceptance/tests:** repeat migration is safe; two concurrent registrations get distinct numbers;
year rollover uses agreed timezone; spoofed actor/role and direct-ID access are denied; rollback
removes partial state/history/job intent; restricted access is tested across directory roles.
**Dependencies:** D0. **Boundary:** no operational UI or automatic external effects.

### D2 — Manual registry, verification, Drive references, and intake shell

- [ ] Add Office -> Documents, incoming registration/detail/list, original receipt details,
  external references, Drive links/version metadata, verification/correction actions.
- [ ] Show Awaiting verification; honor preverification scope and verified bureau/restricted scope.
- [ ] Provide duplicate candidate warnings using reference, subject/sender/date, and Drive ID;
  no hard uniqueness on DTRAK.
- [ ] Allow missing scan to be explicit rather than making up a link; final requirements are type-driven.

**Acceptance/tests:** any staff member can register; permitted verifying actors can act; required
fields explain errors; restricted/unverified records do not leak through URL, list, or counts;
Drive failures are visible and manual entry remains usable.
**Dependencies:** D1. **Boundary:** routing waits for D3; operational launch remains disabled.

### D3 — Rule editor, directives, ownership, and contributor work

- [ ] Add workflow-admin rule UI with preview, explanation, priority/conflicts, versions, and rollback.
- [ ] Apply confirmed-field rules on submission, propose lead/assignments, and record notification intent.
- [ ] Support verification in parallel with preliminary work, acknowledgment, handoff, contribution,
  reassignment, Director overrides, and directive reconciliation.
- [ ] Add joint-unit consolidation and an unresolved-ownership queue.

**Acceptance/tests:** keywords/type drive explainable proposals; conflicts notify all eligible
suggested units without choosing a hidden lead; actors beyond Admin can verify/route; pre-directive
external action is blocked; OIC/reassignment and changed-directive histories are preserved.
**Dependencies:** D2. **Boundary:** rule edits affect future evaluations unless reevaluation is explicit.

### D4 — Bell/email events and durable job execution

- [ ] Wire document events into home tasks, bell, mail feature settings/previews, and scheduler.
- [ ] Register any new mail job in all required registries (currently job lists, feature mapping,
  mailer feature catalog, and previews); recheck current implementation.
- [ ] Implement persistent delivery attempts, deduplication, visibility rechecks, failure/retry UI.

**Acceptance/tests:** new submissions notify before verification; all recipient classes work;
repeated processing/restart does not duplicate a delivered notice; one failed email does not hide
the in-app assignment; revoked access is respected; jobs remain quiet when module sending is disabled.
**Dependencies:** D3. **Boundary:** reminders D5; official outgoing dispatch D8.

### D5 — Working-day deadlines, milestones, proactive reminders, escalation

- [ ] Implement stated/default deadlines and policy provenance, internal contributor buffers,
  recorded extensions, and unpaused awaiting-external status.
- [ ] Implement 3-working-day, 1-working-day, and due-date notices, urgent/short-notice collapse,
  overdue escalation, and reassignment/deadline-change recalculation.
- [ ] Provide configurable escalation intervals and holiday-coverage warnings.

**Acceptance/tests:** holiday/weekend crossings, explicit Sunday deadline, year boundary, shortened
deadline, impossible buffers, due-time boundary, delayed scheduler, reopened work, and duplicate
scheduler runs. Before-deadline reminders occur proactively; overdue notices follow the escalation chain.
**Dependencies:** D4. **Boundary:** do not invent timing values still pending in section 10.

### D6 — Outgoing drafts, review routes, approvals, and revision classification

- [ ] Register independent/linked outgoing drafts with official number immediately.
- [ ] Rules propose review authority; chief confirms routine authority or escalates to Director/OIC.
- [ ] Add review stages, return-for-revision, exact-version decisions, minor-change annotation,
  material-change invalidation, and approvals-page integration.

**Acceptance/tests:** independent outgoing and many-to-many replies work; unauthorized commitments
cannot bypass approval; concurrent/stale approval is rejected; minor correction preserves a traceable
approval lineage; substantive changes invalidate it; canceled numbers are not reused.
**Dependencies:** D3, D4. **Boundary:** approval cannot count as signing or dispatch.

### D7 — External signing and signatory-only stored-signature execution

- [ ] Record externally signed final Drive copies and implement stored-signature execution through
  a confirmed adapter with explicit final preview and signatory confirmation.
- [ ] Tie output to reviewed content/version; persist operation ID and confirmed output metadata.
- [ ] Preserve older versions and detect changes before release.

**Acceptance/tests:** only the signatory can invoke their own signature (including direct API calls);
a releasing officer/delegate cannot apply it; OIC uses their own identity; retry does not create
untracked signed artifacts; changed source invalidates stale signing; signed output is checked
visually against representative formats in live acceptance.
**Dependencies:** D6 and D0 adapter proof. **Boundary:** stored image application is not advertised
as certificate-based digital signing; no permanent binary storage in the app.

### D8 — Release checklists, existing-email evidence, direct official email

- [ ] Add channel/type-specific release checklists and authorized release actions.
- [ ] Support manual recording of existing-email/physical/other dispatch and direct official-mail
  sending, retaining exact released version, recipients, sender, channel, time, and evidence.
- [ ] Track per-recipient dispatch outcome, acknowledgment where required, retry/reconciliation,
  canceled requests, and duplicate submission prevention.

**Acceptance/tests:** required evidence blocks premature release; approval/signing gate is enforced;
one failed recipient is visible; a timeout after possible send requires reconciliation; retry does
not blindly resend; email-log retention cannot erase the official dispatch record; real configured
sender/domain and representative recipient delivery are verified before D12.
**Dependencies:** D7, D4. **Boundary:** no automatic sending from extraction/routing rules.

### D9 — Assisted extraction and confirmation

- [ ] Fetch supported Drive documents using authorized access and bounded processing.
- [ ] Extract suggested subject, sender, references, type, stated deadline, and keywords from
  supported text and scanned formats; show source excerpts/uncertainties.
- [ ] Let staff correct/confirm; run routing only on the submitted confirmed values.
- [ ] Add cancellation, retries, timeout/error handling, and transient-content cleanup.

**Acceptance/tests:** clean text, scan, ambiguous date, unreadable/password-protected file,
inaccessible link, oversized input, conflicting extracted values, and hostile instructions in
document text. No suggestions can authorize actions or bypass visibility. Manual entry always works.
**Dependencies:** D2, D4, D0 extraction contract. **Boundary:** required before first operational launch.

### D10 — Closure, reopening, duplicate linking/merge, and thread integrity

- [ ] Configure type/action-specific closure evidence through workflow-admin settings.
- [ ] Require all mandatory contributions/release steps or an authorized recorded disposition.
- [ ] Implement reopening with reason/notices and deadline reconciliation.
- [ ] Add repeated receipt linking and merge preview for authorized verifying officers; choose a
  canonical record while preserving numbers, files, dispatches, assignments, and original event authors.

**Acceptance/tests:** one contributor cannot close a joint response early; forwarding alone is not
completion; reference and response documents have different evidence; unauthorized reopen fails;
merge preserves old-number lookup and does not broaden visibility; conflicting owners/deadlines
require resolution; merge reversal/correction strategy is demonstrated without deleting history.
**Dependencies:** D3, D5, D8. **Boundary:** do not invent historical completion dates or rerun past sends.

### D11 — Shared UX, calendar suggestions, search, reporting, and exports

- [ ] Complete My action queue, incoming/outgoing registers, verification/review/release queues,
  team monitoring, detail timeline, and bureau overview within permitted scope.
- [ ] Add confirmed calendar suggestions, matching/linking existing entries and tracking source links.
- [ ] Add scoped search and monthly/register exports with status/definition notes.
- [ ] Measure unassigned, unacknowledged, due soon, overdue, awaiting review/release, and known
  turnaround durations; show unknown/missing timestamp counts explicitly.

**Acceptance/tests:** invitation confirmation links/creates once; rescheduling needs confirmation;
restricted document titles/links are not exposed to broader calendar audiences; identical record
permissions govern dashboard/export/search; accessible keyboard and narrow-screen workflows work.
**Dependencies:** D4, D5, D10. **Boundary:** no automatic CSS survey creation.

### D12 — Bureau-wide launch, trial, and operational handoff

- [ ] Close section 10 blockers; confirm accounts/grants, rule catalog, holidays, Drive identity,
  extraction/signing adapters, official mailbox, and support ownership.
- [ ] Execute complete incoming/outgoing journeys with representatives from both divisions, receiving
  staff, and Director's office before enabling bureau-wide use. This is acceptance testing, not a
  limited operational pilot replacing the selected bureau-wide launch.
- [ ] Set launch date/trial duration, provide role-based quick guides, and identify feedback/incident owners.
- [ ] Capture backup/recovery evidence, failed-job recovery, emergency send-disable and rollback procedures.
- [ ] Start new records from cutover; retain spreadsheet for pre-cutover history and a documented
  continuity process if module writes or external services are temporarily unavailable.

**Acceptance:** D1–D11 complete; both entry/signing/email modes demonstrably work; no unresolved
unauthorized-access, lost-record, duplicate-dispatch, or version-integrity defect; full required
regressions and representative browser-to-data-to-external-service journeys are evidenced.
**Dependencies:** all first-release increments. **Rollback:** disable new writes/sends, retain read
access/audit and queued operation state, reconcile external effects before replay, never delete
new records or rewind official sequences to make a rollback appear clean.

### D13 — Optional historical import (after launch)

- [ ] Build month-specific mapping, preview, raw-value preservation, exception queue, and source
  spreadsheet/tab/row provenance.
- [ ] Review dates/control numbers/duplicate candidates/links; unknown historical status stays unknown.
- [ ] Make import repeat-safe and reconcile reviewed totals; do not send historical reminders by default.

**Acceptance:** repeated upload creates no duplicate; existing edited records are not overwritten;
uncertain values remain visible; historical timestamps are distinguished from import timestamps.
**Dependencies:** D12 and explicit prioritization. **Boundary:** not a first-release gate.

## 7. Proposed code layout and UI

- documents.py: orchestration/services and transaction boundaries.
- documents_storage.py: schema helpers and document persistence integrated through storage.init_db.
- documents_permissions.py: shared access/action predicates and scoped grants.
- documents_rules.py: pure routing, deadline, closure, and release policy evaluation.
- documents_routes.py: APIRouter; route guards, validation, thin handlers.
- documents_notify.py: durable event notices, reminders, and escalation.
- documents_drive.py: narrow adapter over validated relay/API capabilities.
- documents_extract.py, documents_sign.py, documents_dispatch.py: independently testable external workflows.
- templates/documents/ and focused static assets; reuse shared layouts, forms, statuses, and approvals.
- tests/test_documents_*.py: focused behavioral and integration contracts.

Implementation uses the proposed service boundaries; external Drive, extraction, signing and dispatch orchestration is consolidated in `documents_operations.py`. Keep app.py integration small.
Do not couple document workflow logic to CSS response/answer tables or travel-specific form policies.

Primary screens: My actions; Incoming; Outgoing; For verification; For review; For release;
Team monitoring; Rules/settings. Detail page: reference/header, current action and deadline,
assignments, instructions, versions, related records, dispatches, timeline.
Show who acted and when; avoid color-only state cues. Show stale-edit conflicts and corrective
actions without losing entered text.

## 8. Acceptance scenarios and release evidence

Each implementation PR updates its increment checkbox, tests run, known limitations, and PR link.
Tests use synthetic data and fake adapters; D12 additionally requires live integration evidence
with authorized test recipients and no unsolicited real external communications.

| Scenario | Required result | Increments |
|---|---|---|
| Staff submits invitation before verification | Scoped visibility, immediate routing notices, preliminary work allowed | D2–D4 |
| Two rules nominate different leads | All eligible suggested units notified; unresolved lead visible | D3 |
| Two divisions contribute | Independent milestones, one consolidator, no early closure | D3, D5, D10 |
| Director changes instructions mid-work | Prior work retained; affected staff notified; reconciliation recorded | D3–D4 |
| Explicit deadline on holiday/weekend | Date unchanged; working-day advance reminders; due-date alert still sent | D5 |
| Staff waits for external input | Deadline keeps running until authorized extension | D5 |
| Routine response becomes policy commitment | Chief escalates; prior insufficient approval cannot release | D6 |
| Signed Drive file changes before release | Version mismatch blocks stale release; required reapproval/resigning applied | D6–D8 |
| OIC handles an absent chief's approval | Delegation/actor recorded; another person's signature cannot be applied | D6–D7 |
| Direct send times out after possible acceptance | Unknown outcome shown; reconcile before retry | D8 |
| Scan extraction suggests wrong deadline | Staff corrects before submission; routing uses confirmed data | D9 |
| Duplicate merged into restricted record | References/history retained; no broader visibility or repeated sends | D10 |
| Closure reopened by lead | Reason, new action/deadline handling, notices and history preserved | D10 |
| Calendar/search/export show document | Same access rules; no private content leaks into broader calendar | D11 |
| Restore metadata after incident | Sequences/history consistent; external jobs reconciled; Drive artifacts checked | D12 |

Verification should cover migrations on a database copy, access matrix, state transitions,
transactions/concurrency, boundary dates, adapter failure/retry, and affected shared features.
Run repository-required checks appropriate to each change; distinguish pre-existing failures
from introduced regressions against that PR's actual base. Documentation-only PRs need content,
links, requirement coverage, and diff checks; they do not claim application test execution.

## 9. Suggested first-release measures

Definitions must be visible beside metrics:

- Verification backlog and receipt-to-verification time.
- Assignments awaiting acknowledgment, due soon, and overdue.
- Contributor, consolidation, approval, and release queue time.
- Completed within deadline versus late, using known timestamps and the applicable deadline policy.
- Awaiting-external work with unchanged deadline and separately identified extensions.
- Dispatch failures/unknown outcomes and outstanding required acknowledgments.
- Unassigned/conflicting routes, inaccessible Drive links, and rules needing improvement.

Do not label all blank dates as pending, infer performance from incomplete history, or count
one document with several contributions as several independent incoming documents.

## 10. Open decisions and gates

These refine confirmed requirements; they are not permission to replace them. Record final
values/owners here during D0 and subsequent design reviews, without reopening settled choices.

| ID | Still to specify | Gate |
|---|---|---|
| O01 | Initial types, keyword fields/match modes, rules, priorities, routine authority limits, and unmatched fallback (proposed Director + receiving/Admin) | D3 activation, D6 |
| O02 | Named records/verifying personnel, workflow administrators, scoped grants and their grant/revoke authority; originating outgoing-draft eligibility | D1, D12 |
| O03 | Default durations/buffers, receipt-vs-registration anchor, due-date time cutoff, reminder send time, escalation intervals, overdue-extension reporting | D5 |
| O04 | Exact closure/release evidence by type/channel, required recipient acknowledgment, cancellation authority, major/minor revision classification authority | D6, D8, D10 |
| O05 | Restricted-document authorized viewer policy, unexpected sensitive preverification submissions, search/email redaction, and restriction review | D1–D3 |
| O06 | Supported Drive formats and identities; metadata/version guarantees; OCR/model/provider and transient data treatment | D7, D9 |
| O07 | Stored-signature artifact formats/placement and final-preview confirmation; approval-preserving minor edits still need honest version lineage | D7 |
| O08 | Official sender account, reply handling, recipient-level success/evidence, delivery reconciliation and authenticated adapter configuration | D8 |
| O09 | Record/attachment retention, archival/disposal authority, recovery responsibilities for Drive originals and signed copies | D12 |
| O10 | Missing holiday-year coverage procedure; timezone/year-boundary proposal validation | D1, D5, D12 |
| O11 | Launch date, trial duration, support owner, feedback triage cadence, continuity and rollback procedure | D12 |
| O12 | Future historical import scope and sequencing | D13 only |

Default implementation stance while these are pending: module disabled operationally, no automated
purge, no inferred signing/approval powers, no silent deadline assumptions, and no claim that a
file's Drive link alone proves an immutable signed version. Resolve launch gates before enabling
bureau-wide use; blocked first-release integrations remain visible blockers, not deferred features.

## 11. Development handoff checklist

For every incremental PR:

- State increment ID, user-visible outcome, requirements covered, dependencies, and exclusions.
- Use additive migrations and safe module-off behavior; document recovery for external effects.
- Include appropriate permission, failure, and concurrency cases rather than only happy-path tests.
- Recheck current shared APIs and deployed prerequisites; the baseline above is a point-in-time review.
- Update this plan with actual status, PR links, evidence, and any explicitly approved scope change.
- Preserve prior module behavior and keep optional future work separate from first-release gates.

The D1–D11 development implementation adds application tables, service workflows, screens and shared
integration hooks. `documents.enabled` and `documents.sending_enabled` default to `0`. It has not
connected production Google/OCR/signing/mail providers, sent live mail, imported spreadsheet data,
or deployed code. The unchecked acceptance items above intentionally remain open until their full
policy, integration and operational evidence exists; local fake-adapter tests do not close those gates.

### Implementation evidence — October 15, 2026

Implementation review: [draft PR #264](https://github.com/jongsky25/css-is/pull/264).

- [Setup, increment coverage, adapter contracts and recovery](DOCUMENT_MANAGEMENT_SETUP.md).
- [Synthetic lifecycle contracts](../tests/test_documents.py) and [HTTP/CSRF contracts](../tests/test_documents_routes.py).
- Browser acceptance on a synthetic database: incoming registration, verification, register and rules
  at 390px/1280px; no horizontal overflow on checked phone screens.
- Repeated migrations and repository preflight passed. Full regression results and the clean-main
  comparison are recorded in the implementation PR.
- O01–O11 remain owner/configuration/live-acceptance gates. D12 launch and D13 import are not performed.
