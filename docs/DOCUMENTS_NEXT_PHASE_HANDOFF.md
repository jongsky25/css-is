# Documents: next-phase handoff

Prepared November 7, 2026 after the complete guarded deployment of PR #603.
Repository: **jongsky25/css-is**, Office Connect BLHSD (Python 3.11, FastAPI/Jinja).
Review branch: **docs/documents-next-phase-handoff**, PR #604. Candidate **10.13**
promotes this documentation under the repository release policy; it does not
implement the next phase.

## Goal and authority

Make Documents intuitive on a phone: show what needs the current person's action,
retain context and entered information, and avoid repeated navigation and entry.
Keep accountable human decisions and server safeguards visible at the moment needed.

The owner authorized feature merges/deployments through #603; those are complete.
The subsequent instruction “assess and fix 604 then merge when ready” authorizes
repairing and merging #604 after all gates pass, including its normal guarded
deployment. It does not authorize implementing later features. This handoff covers
assessment/planning of **My desk counts/filters, closer request-execution integration,
and staff usability testing**. Obtain a new implementation instruction before
building those phases and release authorization before merging/deploying them.
No staff invitations, notifications, production-data testing, relay activation,
repository-setting changes or manual deployment are authorized.

Read current AGENTS.md, CLOUD_COLLABORATION.md and SETUP_STATUS.md first. Historical
feature guides and appended status entries contain old draft-only cutoffs and
pending-run snapshots; the verified baseline here supersedes those snapshots, not
current code or later owner instructions. Recheck main and open PRs in a new chat.

## Verified shipped baseline

Verified main and final merge: `6452931b25d953b10a20dcea4750003e2ecd147d`. Version **10.12**.
The entire guarded [final deployment](https://github.com/jongsky25/css-is/actions/runs/42411602460) succeeded:
normal/shuffled verification, metadata, dependency audit, Required checks, deploy,
and post-deploy diagnostics. This is workflow evidence; no manual live staff test
or production-data inspection was performed.

| PR | Version / behavior | Exact reviewed head | Exact merge | Full PR CI | Guarded main deployment |
| --- | --- | --- | --- | --- | --- |
| [#596](https://github.com/jongsky25/css-is/pull/596) | 10.05 — My desk and workspace | `067f128378f2ca75d31a5aaec2d852f1aeb0da10` | `4c9657d028f605b2bdad2a243cf295b5dd454920` | [run 42339512542](https://github.com/jongsky25/css-is/actions/runs/42339512542) | [run 42343521324](https://github.com/jongsky25/css-is/actions/runs/42343521324) |
| [#597](https://github.com/jongsky25/css-is/pull/597) | 10.06 — Direct review and read/fill | `4d7dc8b0e19d8702339ea2c422d8fe014d407923` | `0ee1cffffebe69147ba951fd1d71fda1b13bf0b4` | [run 42343527614](https://github.com/jongsky25/css-is/actions/runs/42343527614) | [run 42348890661](https://github.com/jongsky25/css-is/actions/runs/42348890661) |
| [#598](https://github.com/jongsky25/css-is/pull/598) | 10.07 — Progressive request entry | `fbcc376ecde0186352975de1462a84408d70d9c5` | `043c9069927e4dc447a3afd1083e6ec3cf091eda` | [run 42348932141](https://github.com/jongsky25/css-is/actions/runs/42348932141) | [run 42362949336](https://github.com/jongsky25/css-is/actions/runs/42362949336) |
| [#599](https://github.com/jongsky25/css-is/pull/599) | 10.08 — Return context | `e3e6fb113408b0f4cc4f9be1eb9ce118215b495d` | `1bb67b198c2a4515377e0f86cd4ebbfb0c66ce30` | [run 42362957347](https://github.com/jongsky25/css-is/actions/runs/42362957347) | [run 42371458688](https://github.com/jongsky25/css-is/actions/runs/42371458688) |
| [#600](https://github.com/jongsky25/css-is/pull/600) | 10.09 — Manual-first registration | `f8e9c72e16183b8ab5087411ae2d882187599d60` | `55ffa5e598ad7d1e9c2a802ba5f4b685cd2c329f` | [run 42375841984](https://github.com/jongsky25/css-is/actions/runs/42375841984) | [run 42381842494](https://github.com/jongsky25/css-is/actions/runs/42381842494) |
| [#601](https://github.com/jongsky25/css-is/pull/601) | 10.10 — Inbox review availability | `87d19da15fd33d780e0886096466ccc85eb4ef81` | `65bde2751ebb40f6b2cb1acea8c2ca3d8796856c` | [run 42381850727](https://github.com/jongsky25/css-is/actions/runs/42381850727) | [run 42398402696](https://github.com/jongsky25/css-is/actions/runs/42398402696) |
| [#602](https://github.com/jongsky25/css-is/pull/602) | 10.11 — Inbox file/subject search | `facdb06f76c42ced8b187b1eb77d029f57a4cdb4` | `7ac74d4e76a3dbd4e774965b693ba4ac7b749bfc` | [run 42398412987](https://github.com/jongsky25/css-is/actions/runs/42398412987) | [run 42405641240](https://github.com/jongsky25/css-is/actions/runs/42405641240) |
| [#603](https://github.com/jongsky25/css-is/pull/603) | 10.12 — Filtered review-next | `3f3f317af9ed75806f0e12f0ec9a6d734c8e4923` | `6452931b25d953b10a20dcea4750003e2ecd147d` | [run 42405652151](https://github.com/jongsky25/css-is/actions/runs/42405652151) | [run 42411602460](https://github.com/jongsky25/css-is/actions/runs/42411602460) |

All listed PRs are merged and all listed guarded deployments completed successfully.
#599 deployment and #601 PR CI succeeded on attempt 2; earlier failed/cancelled
attempts remain evidence and must not be mistaken for the release result. Full
normal/shuffled PR counts respectively: #597 10,804 each; #598 10,809; #599 10,822;
#600 10,825; #601 10,830; #602 10,836; #603 10,844. Their JUnit gates rejected
failures/errors/skips. Consult #596's linked run for its exact full-suite total;
do not derive it from later counts. Metadata, dependency audit and aggregate gates
passed for each released head. No increment changed avatar acceptance paths.
Immediately before each merge the current head/main, reviews, unresolved threads,
and active strict no-bypass ruleset 26274179 were checked. Native auto-merge is off.

### Completed repairs and evidence limits

- #596 repaired a stale browser expectation after source details became collapsed;
  persistence, confirmation and escaping assertions remained (12 local checks).
- #599 restored absent dashboard sort/direction defaults (19 focused browser checks).
- #600 repaired the no-script registration harness: loopback HTTP to isolated
  TestClient, scripts disabled at context creation, actual 303/destination and
  exactly one POST/document/registration (10 focused browser checks).
- Shared Files-disclosure test repair `f8e9c72` waits for the hashchange callback's
  open attribute and focus, retaining form values/no-write checks. A delayed callback
  reproduced the old failure; eight targeted checks passed. No runtime workaround.
- #601 shuffled CI initially hung in Playwright near the calendar browser interval.
  Its 72-test neighborhood passed locally; a complete retry passed. Root cause is
  **unproven**. A recurring hang needs diagnostics, not repeated blind retries,
  timeout inflation, skipped tests or a weakened gate.

Focused/local groups in feature guides overlap and are not additive full-suite
counts. They use synthetic fixtures. Full CI confirms automated checks, not staff
usability. There are **no observed staff timings, error rates or completion metrics**
for these increments. Live Google preview behavior was not validated. Existing
Drive text-analysis relay activation remains deferred; do not activate it here.

## Current flow and source map

1. Documents opens `/documents/actions` (My desk). My next steps and division
   follow-up lead to an existing authorized action, instruction or permitted work.
2. Inbox searches file names/email subjects and filters status plus claim availability
   before pagination. Review/Resume explicitly POSTs a claim; opening a page does not.
3. Review saves corrections and reads/fills empty fields. Requests and focus suggestions
   require review. Source/revision/claim changes prevent stale registration.
4. Manual registration shows Incoming/Outgoing and editable fields immediately;
   optional PDF/link reading is a disclosure. Entered requests remain visible;
   Add request reveals another slot. No-script mode retains native request controls.
5. Registration preserves numbering/retry semantics. Review-next uses the originating
   permitted Inbox scope; conflicts/no next item return to that filtered Inbox.
6. Registered document: next-step/source → requests and shared work → evidence,
   review, signing, dispatch, acknowledgment and closure through distinct authorities.
   Return context preserves supported queue/search/page/sort through ordinary saves.

The links below pin inspected code to the shipped baseline, so later edits cannot
silently change the meaning of this map. Check current main as well before editing.

| Area | Files / functions | Relevant tests |
| --- | --- | --- |
| My desk | [documents_actions.py](https://github.com/jongsky25/css-is/blob/6452931b25d953b10a20dcea4750003e2ecd147d/documents_actions.py) — page, _selection, _page_records, _load, _cards; document pagination then card generation | [tests/test_document_action_pages.py](https://github.com/jongsky25/css-is/blob/6452931b25d953b10a20dcea4750003e2ecd147d/tests/test_document_action_pages.py) |
| Workflow advice | [documents_guidance.py](https://github.com/jongsky25/css-is/blob/6452931b25d953b10a20dcea4750003e2ecd147d/documents_guidance.py) — build, assignment_choices; documents.closure_blockers is shared with writes | [tests/test_documents_guidance.py](https://github.com/jongsky25/css-is/blob/6452931b25d953b10a20dcea4750003e2ecd147d/tests/test_documents_guidance.py) |
| Routes and detail | [documents_routes.py](https://github.com/jongsky25/css-is/blob/6452931b25d953b10a20dcea4750003e2ecd147d/documents_routes.py) — make_router: action_screen, detail_context, request_work_submit, understanding_submit, handle_action | [tests/test_document_action_routes.py](https://github.com/jongsky25/css-is/blob/6452931b25d953b10a20dcea4750003e2ecd147d/tests/test_document_action_routes.py) |
| Current action UI | [static/js/document_action_link.js](https://github.com/jongsky25/css-is/blob/6452931b25d953b10a20dcea4750003e2ecd147d/static/js/document_action_link.js) — reveal; moves existing authorized forms, expands ancestors and focuses summary | [tests/test_document_workspace_navigation.py](https://github.com/jongsky25/css-is/blob/6452931b25d953b10a20dcea4750003e2ecd147d/tests/test_document_workspace_navigation.py) |
| Intake scope and claims | [documents_intake.py](https://github.com/jongsky25/css-is/blob/6452931b25d953b10a20dcea4750003e2ecd147d/documents_intake.py) — queue_query, review_filter, review_counts, list_page, next_review, claim, extract, register | [tests/test_document_review_next_scope.py](https://github.com/jongsky25/css-is/blob/6452931b25d953b10a20dcea4750003e2ecd147d/tests/test_document_review_next_scope.py) |
| Intake routes | [documents_intake_routes.py](https://github.com/jongsky25/css-is/blob/6452931b25d953b10a20dcea4750003e2ecd147d/documents_intake_routes.py) — make_router; claim, review and registration completion paths | [tests/test_document_intake_friction_browser.py](https://github.com/jongsky25/css-is/blob/6452931b25d953b10a20dcea4750003e2ecd147d/tests/test_document_intake_friction_browser.py) |
| Return navigation | [documents_navigation.py](https://github.com/jongsky25/css-is/blob/6452931b25d953b10a20dcea4750003e2ecd147d/documents_navigation.py) — safe_return, record_url, context, return_to_record | [tests/test_document_inbox_search.py](https://github.com/jongsky25/css-is/blob/6452931b25d953b10a20dcea4750003e2ecd147d/tests/test_document_inbox_search.py) |
| Reviewed source | [documents_understanding.py](https://github.com/jongsky25/css-is/blob/6452931b25d953b10a20dcea4750003e2ecd147d/documents_understanding.py) — clean, read, revise, can_edit; stable need_N fields and confirmations | [tests/test_document_understanding_review.py](https://github.com/jongsky25/css-is/blob/6452931b25d953b10a20dcea4750003e2ecd147d/tests/test_document_understanding_review.py) |
| Request work | [documents_request_work.py](https://github.com/jongsky25/css-is/blob/6452931b25d953b10a20dcea4750003e2ecd147d/documents_request_work.py) — source, existing, propose, comparison, overview, task_source | [tests/test_document_request_work.py](https://github.com/jongsky25/css-is/blob/6452931b25d953b10a20dcea4750003e2ecd147d/tests/test_document_request_work.py) |
| Request receipt UI | [templates/documents/request_work.html](https://github.com/jongsky25/css-is/blob/6452931b25d953b10a20dcea4750003e2ecd147d/templates/documents/request_work.html) — preserved source/current comparison and existing work links | [tests/test_document_request_comparison_routes.py](https://github.com/jongsky25/css-is/blob/6452931b25d953b10a20dcea4750003e2ecd147d/tests/test_document_request_comparison_routes.py) |
| Registration retries | [documents_registration.py](https://github.com/jongsky25/css-is/blob/6452931b25d953b10a20dcea4750003e2ecd147d/documents_registration.py) — issue, status, register; atomic registration receipt | [tests/test_document_registration_browser.py](https://github.com/jongsky25/css-is/blob/6452931b25d953b10a20dcea4750003e2ecd147d/tests/test_document_registration_browser.py) |
| Access and selection | [documents_permissions.py](https://github.com/jongsky25/css-is/blob/6452931b25d953b10a20dcea4750003e2ecd147d/documents_permissions.py) — RegistryScope; current actor and permitted document scope | [tests/test_document_registry_pagination.py](https://github.com/jongsky25/css-is/blob/6452931b25d953b10a20dcea4750003e2ecd147d/tests/test_document_registry_pagination.py) |
| Shared-work review | [work_review.py](https://github.com/jongsky25/css-is/blob/6452931b25d953b10a20dcea4750003e2ecd147d/work_review.py) — snapshot, version_matches, current, require_current, prepare, summaries | [tests/test_documents_guidance.py](https://github.com/jongsky25/css-is/blob/6452931b25d953b10a20dcea4750003e2ecd147d/tests/test_documents_guidance.py) |
| Existing aggregate reference | [documents_dashboard.py](https://github.com/jongsky25/css-is/blob/6452931b25d953b10a20dcea4750003e2ecd147d/documents_dashboard.py) — report; permission-filtered snapshot aggregates, not My desk step counts | [tests/test_documents_dashboard.py](https://github.com/jongsky25/css-is/blob/6452931b25d953b10a20dcea4750003e2ecd147d/tests/test_documents_dashboard.py) |

Also inspect `templates/documents/actions.html`, `detail.html`, `intake_queue.html`,
`intake_review.html`, `new.html`; `static/js/work-intake.js`; `work.py`, `work_tasks.py`,
`work_completion.py`; tests for Inbox focus/search, request entry, overview,
comparison, work routes, registry grid/exports and document guidance browsers.
Read DOCUMENT_EXPERIENCE.md, DOCUMENT_INTAKE_EXPERIENCE.md, DOCUMENT_ACTION_PAGES.md,
DOCUMENT_NEXT_STEP.md, DOCUMENT_UNDERSTANDING.md, DOCUMENT_REQUEST_ENTRY.md,
DOCUMENT_RETURN_CONTEXT.md, DOCUMENT_REGISTRATION_ENTRY.md, DOCUMENT_INBOX_FOCUS.md,
DOCUMENT_INBOX_SEARCH.md and DOCUMENT_REVIEW_NEXT_SCOPE.md. Do not rebuild their
shipped increments.

## Prioritized phases (proposed, not implementation authorization)

| Phase | Bounded outcome and dependency | Acceptance / exit evidence |
| --- | --- | --- |
| 0: count contract | First next action: assess My desk classification against guidance and write an executable-spec plan with synthetic truth table and query-cost baseline. No UI change yet. | Owner can review document-versus-step units, mixed-state examples, privacy rules and snapshot/paging behavior; identify reusable classification before choosing SQL. |
| 1: My desk counts and filters | After phase 0 decisions, implement one scoped counts/filter slice on My next steps; extend division view only after parity is proved. | Independent expected full-scope totals match every filter traversal; beyond-page fixtures, access revocation, migrated/private work, deadlines and no-script/keyboard cases pass; no mutation or provider calls. |
| 2: request execution | Assess existing overview/receipt journey, then propose one read-only contextual link/comparison improvement before adding any write operation. Depends on verified source/slot/access contract. | Fewer measured transitions on synthetic tasks, unchanged identity and authority; duplicate/retry/stale-source/private-work scenarios retain guards. New reconciliation writes require separate design/authorization. |
| 3: staff usability study | Plan baseline tasks now; execute with staff only after explicit authorization and an approved synthetic preview. Compare the shipped baseline with the selected next slice. | Accessible sessions, recorded metrics and errors, clear observed results versus hypotheses; iterate the bounded change before expanding scope. |

Why start with the count contract: `documents_actions.page` currently returns
`document_count = len(documents)` for its selected page. `_cards` may emit several
instruction/contribution/workflow cards per document and may emit none for some
candidates. Child displays are capped at three of each kind. Counting rendered
cards or filtering those 30 documents would give false full-scope totals. Reusing
the current detail guidance avoids creating a second contradictory workflow policy.

### My desk count/filter design to resolve in phase 0

Use two explicitly named units: **documents with matching steps** (distinct canonical
active document IDs) and **steps** (stable workflow/instruction/contribution identity).
Do not label either as staff workload, productivity or completed work. The first
UI slice should show document counts; show step totals only if complete, uncapped
step classification is implemented and the label is clear. Current truncated child
cards cannot supply exact step totals.

Preserve existing per-step semantics from `_cards` and `documents_guidance.build`:
Ready for you means a currently permitted action is available; Waiting means no
such action and the responsible role/blocker should be explained; Needs attention
covers operation, unknown/partial delivery, consolidation, revoked review authority,
closure-policy and release-policy states as currently classified. Overdue is a
separate deadline dimension, not automatically attention. Reconciliation's current
classification must be characterized, not silently relabeled. Disabled-module
read-only behavior, unread instructions, prerequisite-gated contributions and
migrated shared work must agree with existing advice.

**Proposed document-count rule:** a document matches a state if at least one of its
permitted steps has that state. State sets can overlap; show “documents with…” and
explain that their sum may exceed All. If mutually exclusive tabs are required,
choose an explicit precedence (e.g. attention, then ready, then waiting) with the
owner; do not invent that precedence in implementation. All counts distinct IDs
with at least one visible step. A no-step candidate contributes zero. Restricted
work details and hidden tasks must not leak through either counts or explanations.

Compute authority + candidate scope + full state classification + selected filter
**before pagination**, in one read snapshot with one fixed date/time. Reuse current
account, division and alias/canonical rules; never trust a client cursor as authority.
Share the classification projection with displayed cards and regression-test it
against `guidance.build`; avoid hand-copying its decision tree into unrelated SQL.
Design compact facts/shared-work visibility batches, then choose between a shared
SQL projection and bounded internal scans; do not materialize all histories, OCR,
files, job payloads or work bodies to count. Reject a design that simply calls the
expensive detail context for every document without a measured bound.

Retain deterministic earliest applicable deadline, descending document ID ties,
unknown dates last; define stable step tie-breakers if paging steps is later chosen.
Filters reset cursor; page links preserve scope; changed permissions/deadlines can
move results between requests, so show snapshot time and a first-page refresh.
No cross-user cached counts; if caching is proposed, key/invalidate on authority and
workflow changes and prove no leakage. A read must not acquire a claim, acknowledge
an instruction, assign work, enqueue an effect or send notifications.

Test >30 documents, >3 child steps, mixed-state documents, same-day ties, unknown
and overdue dates, inactive/revoked actors, restricted aliases, private work,
module-disabled views, division/OIC changes and empty filters. Compare total counts
to an independent exhaustive synthetic oracle, not the implementation itself.
Measure query count, rows/bytes projected, memory and latency on 100/1,000/10,000
synthetic records. Proposed budget: no per-document detail fetch growth for ordinary
unlinked records, and no more than 20% median latency regression versus the recorded
baseline for the same scope/hardware; establish absolute p95 targets after profiling.
Shared-work graph cost must be measured separately, not hidden by an average.

## Request-execution integration assessment

Already shipped before this queue: confirmed reviewed requests can explicitly create
one proposed case and one unassigned contribution. `document_request_work` reserves
(document_id, request_index), stores original source/focus snapshot and hashes, and
links case/task. Matching retry returns the receipt after access checks; changed
payload/source conflicts. Clearing/replacing a request or cancelling work does not
free its slot. Existing comparison shows preserved source, current saved source and
current work; the overview suppresses inaccessible contribution details/counts.

Proposed first UX improvement: keep a request's evidence, source-change warning and
permitted existing-work link together through a clear return path. Audit existing
screens first; avoid a duplicate receipt, second work creation route or automatic
assignment. Source recipient text is not a staff identity. Confirmation of an
interpretation is not approval, assignment, completed contribution or release.

For any later reconciliation action, explicitly decide which fields may change,
who decides, whether the original source remains immutable, and how stale work
revisions, source hashes and document revisions are checked atomically. Preserve
claim checks at intake, CSRF, current account/document AND work access, module state,
Director routing, official deadlines, source slot identity and idempotency. Require
human confirmation after a meaningful source/direction change. Never overwrite
intentional work edits merely because source differs; retain evidence and audit.

Shared-work completion/consolidation must use existing work services and exact-version
review snapshots. Formal Director approval, signatory authority, dispatch evidence,
acknowledgment and closure remain distinct. Unknown/partial deliveries require
receipt reconciliation, never a suggested blind resend. Migrated assignments stay
in Shared work; do not revive legacy controls. Defer bulk proposals, automatic staff
matching, automated reconciliation, attaching requests to existing cases, new relay
features and schema changes until separately scoped and authorized.

Acceptance scenarios: double-click/retry yields one proposal; stale source/work
revision blocks an update; cleared source retains its receipt; denied work access
reveals no task title/count/status; a source update cannot invalidate/reapprove
formal release implicitly; no read changes database/audit/provider state.

## Staff usability study plan (not yet conducted)

Use fake names/files/emails and seeded isolated records only. No real staff have
been invited and no production data is needed. An accessible authenticated preview
and consent/recording arrangements are prerequisites for actual sessions; the local
cloud server alone is not a public phone preview. Offer keyboard-only sessions,
screen-reader compatibility, zoom/high-contrast, breaks and an unrecorded option.
Do not record credentials, personal documents or hidden identifiers. Store any later
consented observations with restricted access and an agreed retention/deletion date.

| Persona | Synthetic task and risk probe |
| --- | --- |
| Records staff | Find a named Inbox file; Resume own review; read/fill while preserving a correction; register and review next within the search; return to queue when exhausted. Repeat manual incoming registration without scripts. |
| Director | Find pending routing from My desk, inspect evidence, issue the authorized instruction; distinguish proposed work from assigned responsibility. Test a changed/revoked authority fixture. |
| Contributor | Find own ready step among waiting items, inspect request and existing work, submit an outcome, return to the same queue. Include private linked work and a changed source. |
| Outgoing release officer/signatory | Register draft, attach exact version, request review, inspect returned/changed draft, then authorized signing/dispatch evidence. An uncertain delivery must lead to receipts, not resend. |

Run equivalent phone (390px and actual approved device), desktop (1280px), keyboard,
and no-script variants. Use a counterbalanced baseline/candidate order and fresh
synthetic cases to limit learning effects. Proposed pilot: 2–3 participants per
persona plus accessibility coverage; small samples guide iteration and do not prove
population-wide productivity gains. A facilitator gives the same goal, avoids
coaching until the participant requests help, and records assistance separately.

Measure from task start to confirmed saved outcome: taps/clicks, page transitions,
fields reentered, active time (exclude recorded interruptions), wrong turns, validation
errors, duplicate attempts, assistance, completion/abandonment and confidence (1–5).
Separate deliberate safety confirmations from avoidable navigation. Count server-
confirmed outcomes, not just a success-looking page. Record network/device conditions.

Proposed thresholds, subject to baseline and owner review: at least 90% unassisted
completion of core tasks; median avoidable taps/transitions down 20%; repeated field
entry down 30%; median active time down 15%; no increase in errors or assistance;
zero unauthorized actions, lost corrections or duplicate registrations. Any safety
failure blocks rollout regardless of speed. Report per persona/modality; do not mask
no-script or accessibility regressions with pooled averages.

Session record template:

| Session/task | Build SHA / fixture seed | Persona / device / input mode | Taps / transitions / repeated fields | Active seconds | Errors / assistance / outcome | Observation and quote (consented) | Hypothesis / follow-up |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Not run | — | — | — | — | — | No staff evidence yet | Test the proposed navigation improvements |

Before/after summary template: task + modality, n, median and range for each metric,
completion numerator/denominator, critical incidents, exclusions with reasons, and
next decision. Keep raw observations separate from interpretation and proposed fixes.

## Reproducible isolated setup and verification

Read DEPENDENCIES.md, CLOUD_WORKSPACE.md and current release workflow first. From a
fresh review checkout (preserve other worktrees and dirty files):

```bash
bash scripts/cloud_setup.sh
.venv/bin/python scripts/cloud_workspace.py doctor
.venv/bin/python scripts/cloud_workspace.py test tests/test_document_action_pages.py tests/test_document_action_routes.py tests/test_document_action_browser.py tests/test_documents_guidance.py --junitxml=/tmp/desk.xml
.venv/bin/python scripts/check_release.py junit /tmp/desk.xml
.venv/bin/python scripts/cloud_workspace.py test tests/test_document_request_work.py tests/test_document_request_work_routes.py tests/test_document_request_comparison.py tests/test_document_request_overview.py tests/test_document_understanding_review.py --junitxml=/tmp/requests.xml
.venv/bin/python scripts/check_release.py junit /tmp/requests.xml
.venv/bin/python scripts/cloud_workspace.py test --junitxml=/tmp/full.xml --ai-evaluation-report=/tmp/full-ai.json
.venv/bin/python scripts/check_release.py junit /tmp/full.xml
.venv/bin/python scripts/ai_evaluation.py check /tmp/full-ai.json
.venv/bin/python scripts/cloud_workspace.py test --shuffle-seed=311 --junitxml=/tmp/shuffled.xml --ai-evaluation-report=/tmp/shuffled-ai.json
.venv/bin/python scripts/check_release.py junit /tmp/shuffled.xml
.venv/bin/python scripts/ai_evaluation.py check /tmp/shuffled-ai.json
```

Use separate scratch/report paths for concurrent runs; pytest basetemp deletes its
contents. The wrapper fixes the test clock, creates synthetic databases and excludes
inherited application credentials; it is not an outbound firewall. Follow existing
fixture isolation, block/mock providers and do not run the app against live data.
`cloud_workspace.py serve` is loopback with disposable data, not a production preview.

Future release: fetch exact main; reconcile on a review branch; synchronize version.py,
CHANGELOG.md and service-worker cache; run `scripts/check_release.py release --base
origin/main` using the venv. Require exact-head normal/shuffled full suites with no
failures/errors/skips, AI evaluation evidence, hashed locks/container and vendored
dependency audits, metadata, Required checks and applicable avatar acceptance.
Recheck current reviews/unresolved threads, head/main and active strict no-bypass
protection immediately before regular SHA-bound merge. A merge triggers guarded
main verification, pre-deploy backup, strict live-version check, deployment and
post-deploy verification/diagnostics. Never bypass a gate or manually activate/deploy.
Historical DEPLOY.md storage claims conflict: verify effective persistence before
any future restore; this handoff does not resolve those operations questions.

The original documentation draft at `e97835e` retained version 10.12. CI
[42419745505](https://github.com/jongsky25/css-is/actions/runs/42419745505)
passed both complete test orders and dependency audit, but failed release metadata
and the aggregate gate. Candidate 10.13 synchronizes version.py, CHANGELOG.md and
the service-worker cache, and corrects this handoff and the current setup next action.
No workflow policy, schema, dependency or feature implementation changes are included.
The new head must pass fresh complete CI; earlier successful tests do not establish
its readiness. Merge only with current reviews, resolved threads, strict no-bypass
protection and a SHA-bound regular merge. Verify the resulting guarded deployment.

## Decisions, risks and rollback

Open decisions: overlapping state counts versus exclusive precedence; document versus
step paging; whether counts include visible waiting work with no actionable card;
division scope rollout; performance budget after profiling; source-to-existing-case
integration; permitted reconciliation fields/actors; preview access and staff consent.
Resolve the count contract first, recording examples and rationale before code.

Risks: count privacy leaks, divergent guidance, truncated-step totals, stale live
cursors, expensive shared-work graphs, accidental duplicate proposals and mistaken
release authority. Tests and small phases above address them; retain known CI hang
as an unresolved engineering observation. No usability benefit is asserted as measured.
A UI/count rollback should restore previous navigation while retaining all records,
receipts, source snapshots, audit history and server guards. Any schema change needs
its own reversible migration/recovery plan; never restore production data merely
to undo a UI change. Rollback deployment itself requires explicit authority and
normal backup/version gates. This documentation branch needs no data rollback.

## New-chat starter

Use the current merged handoff on main after #604, or its current review head
before merge. The original planning snapshot remains available at `e97835e`. The
starter below is planning-only; it must not be read as feature implementation approval.

> Continue Office Connect in jongsky25/css-is. Read docs/DOCUMENTS_NEXT_PHASE_HANDOFF.md
> on current main after PR #604, or the current docs/documents-next-phase-handoff
> review head if it is still open; verify and record its exact SHA. Read current AGENTS.md,
> docs/CLOUD_COLLABORATION.md and docs/SETUP_STATUS.md; verify current main, PRs and
> deployment state before assessing/planning phase 0: My desk count/filter semantics.
> Baseline #596–603 is shipped through 6452931b25d953b10a20dcea4750003e2ecd147d;
> do not rebuild those increments. Prepare the bounded count-contract assessment,
> synthetic truth table and performance plan first. Future implementation, merging,
> deployment, staff contact and production-data use are not authorized. Preserve
> source/slot identity, confirmations, permission/revision/claim checks and distinct
> approval/release authority. Keep work on a review branch and preserve concurrent edits.
