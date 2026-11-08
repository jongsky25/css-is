# My next steps: count and filter contract

Implementation candidate 10.14, November 7, 2026. The owner's subsequent “do that”
authorized implementing this specification. Branch: `feat/my-next-steps-filters`,
based on the planning commit `a50807c` and #604 head
`7de2a9be7b15f535ed3aeb9c1811fc778ee09ca4`. The owner later explicitly queued #605 after #604, authorizing its checked release
without waiving the performance criteria. #604 is now merged and deployed at
`e471261c08b8ca58a8d606dc3642ce401288242d` (workflow 42443789666).
The original proposal is retained on `docs/my-next-steps-count-contract`.

## Outcome and scope

A person can identify documents with ready, waiting or attention steps across
their entire permitted My next steps scope, then return to the same filtered
view after inspecting a document. Counts describe documents, not productivity.

Scope is `/documents/actions?view=mine` only. Division follow-up, request-execution
changes, new workflow actions, staff studies, schema changes and notifications
are deferred. Preserve shipped #596–603. See the [handoff](DOCUMENTS_NEXT_PHASE_HANDOFF.md).

## Baseline evidence (before this candidate)

- [documents_actions.py](../documents_actions.py) selects up to 30 documents before
  card generation; `document_count` is selected page length, not a full-scope total.
- `_load` caps instructions and legacy contributions at three per document.
  `_cards` can emit multiple cards or no cards for a candidate. Neither selected
  rows nor rendered card totals is a correct full-scope matching-document count.
- [documents_guidance.py](../documents_guidance.py) owns workflow advice. Attention
  stages take precedence over the presence of an action link. Reconciliation
  is not in that attention-stage set.
- [documents_navigation.py](../documents_navigation.py) currently preserves only
  `view`, `before`, `due` on My desk. New filter keys require explicit allowlisting.
- [actions.html](../templates/documents/actions.html) uses loop-position anchors;
  filter-dependent ordering needs stable step anchors or a safe document fallback.

These are source observations, not measured performance or staff-usability results.

## Implemented rules

1. Keep existing current-account, canonical active-document and personal candidate
   selection. Do not broaden assignment or Director scope through a count feature.
2. Classify every eligible personal step before display truncation: unread tagged
   instruction, eligible legacy contribution, and existing responsible-person
   workflow card. Migrated contributions remain in Shared work.
3. Each document contributes at most one to each count. All means documents with
   at least one visible eligible step. No-step candidates contribute zero.
4. A document can match several states. Label the control group “Documents with…”
   and explain: “A document can appear in more than one group.”
5. State options: All, Ready for you, Waiting, Needs attention. A separate
   “Overdue only” checkbox intersects with state at the SAME STEP level.
   Due today is not overdue; absent deadlines never count as overdue. Use one
   application-local date and one database read snapshot per response.
6. Counts on state controls reflect the selected deadline restriction but ignore
   the selected state. Thus Ready's badge equals the number of distinct documents
   reachable through every page of Ready with that deadline restriction.
7. Visible waiting-only documents are included; hidden work is never counted as
   an additional step. Retain existing permitted generic blocker messages without
   introducing private task identities, counts, status or inferred details.

State classification retains current rules. Instructions are ready when Documents
is enabled, otherwise waiting. Eligible contributions wait when the module is
disabled, initial routing is pending or an unresolved operation blocks progress.
Workflow stages operation, delivery_unknown, delivery_partial, consolidation,
review_authority, closure_policy and release_policy are attention; other workflow
cards are ready if advice exposes a permitted action, otherwise waiting.
Reconciliation stays ready/waiting. These labels describe the current guidance,
not a guarantee that a POST will remain authorized later.

## Synthetic truth table

Fix local date at 2026-11-07. R/W/A mean eligible ready/waiting/attention steps;
“late” means deadline 2026-11-06, “today” means 2026-11-07. Each row is one
distinct accessible active canonical document unless stated otherwise.

| ID | Eligible steps | All | R | W | A | All overdue | R overdue | W overdue | A overdue |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| D1 | R today | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| D2 | W late | 1 | 0 | 1 | 0 | 1 | 0 | 1 | 0 |
| D3 | R today, W late | 1 | 1 | 1 | 0 | 1 | 0 | 1 | 0 |
| D4 | R late, A unknown deadline | 1 | 1 | 0 | 1 | 1 | 1 | 0 | 0 |
| D5 | Four R late contributions | 1 | 1 | 0 | 0 | 1 | 1 | 0 | 0 |
| D6 | No eligible steps | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| D7 | Inaccessible document, R late | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| D8 | R unknown deadline; private linked task excluded | 1 | 1 | 0 | 0 | 0 | 0 | 0 | 0 |
| D9 | A late | 1 | 0 | 0 | 1 | 1 | 0 | 0 | 1 |
| Total | | 7 | 5 | 2 | 2 | 5 | 2 | 2 | 1 |

Expected sets, specified independently of implementation: All = D1,D2,D3,D4,D5,D8,D9;
Ready = D1,D3,D4,D5,D8; Waiting = D2,D3; Attention = D4,D9.
Ready overdue = D4,D5, excluding D3. Removing the hidden task from D8 must not
alter any count or new explanation. Disable Documents in a separate fixture:
eligible steps become waiting under existing read-only guidance, with no actions.

## Paging, cards and navigation

Apply current authority, candidate selection, complete step classification and
state/deadline predicates before document pagination. Preserve document paging
(30 by default, existing maximum 50) and existing earliest applicable deadline /
descending document-ID ordering, with unknown dates last. Filtering selects a
subset of this order; it does not introduce a separate work-priority policy.

Within selected documents, render matching cards. Apply each child-kind display
cap AFTER filtering; a fourth child that alone matches must be visible. Retain
the existing link to all instructions/contributions. Do not claim an exact total
number of steps from truncated cards. Display “N matching documents; M on this
page” separately from “K steps shown.”

Proposed query keys are `step_state=all|ready|waiting|attention` and
`overdue=0|1`; missing keys use all/0. Reject invalid values with 400 and an
accessible reset link. Native GET form submission works without JavaScript;
changing either filter resets the seek cursor. Page/first-page/detail-return
links preserve validated filters. Division view receives no new controls or
counts; reject personal filter parameters there with a clear reset path.

Use stable step identity (document + kind + directive/assignment ID, or workflow
identity) for return anchors, with matching narrow navigation validation.
If the step no longer matches after a save, retain filters and provide a normal
empty/result state; do not force the completed step back into the list.

Revalidate permissions on every request. Cursors contain ordering values only,
never grants. Show snapshot time and Refresh/First page. Between requests,
changed access or deadlines may move results; do not promise frozen traversal.

## Implementation approach

Use a compact classification projection shared by cards and counts.
Keep instruction/assignment IDs, state, due date and permitted navigation facts;
load display bodies only for the selected page. Reuse guidance policy with
batched facts, rather than reproducing its decision tree in independent SQL.
Characterize current guidance versus action-page facts before extraction, including
cases where display-capped assignments could affect advice. Any discovered policy
discrepancy needs explicit characterization rather than a silent counting change.

Measure linked-work visibility and review/release readiness separately. A design
that invokes expensive detail context once per full-scope document is unacceptable
without a demonstrated bound. This candidate uses bounded internal scans with shared SQL visibility facts;
a bounded scan limits Python row batches but does not make total work constant.
Do not add cross-user count caching in this first slice.

## Acceptance and performance plan

- Expand the independent fixture above to at least 65 eligible documents; traverse
  every filter to compare distinct IDs with expected sets and badge totals.
- Include more than three children, mixed-state and same-step deadline cases,
  unknown dates, same-day ties, zero matches, aliases, closed/archived/cancelled
  records, private work, migrated assignments and inaccessible linked sources.
- Revoke account/document/reviewer access between pages. Verify no stale counts
  or action links survive fresh authorization. Retain division/OIC regressions.
- Verify count/card/detail guidance agreement for each stage, including disabled
  modules, blocked contributions and changed review authority.
- Browser journeys: 390px and 1280px, keyboard, zoom, JavaScript disabled, filter
  submit, next page, document inspection/save and return. Preserve existing write
  guards and prove GETs do not mutate documents, audits, claims or provider state.
- Use existing isolated fixture/provider-blocking conventions. Begin with
  test_document_action_pages.py, test_document_action_routes.py,
  test_documents_guidance.py and navigation/workspace regressions.

Record baseline on shipped `6452931` and compare a future candidate using identical
hardware, clock, fixture and page size. Use 100/1,000/10,000 synthetic records,
with separate ordinary, linked/shared-work and restricted/alias-heavy datasets.
Capture SQL count, projected rows/bytes, peak memory, median/p95 latency, query
plans and cold/warm measurements. Use at least 30 timed requests per scenario;
report sample size and variability rather than treating a small p95 as definitive.

Provisional goals: no per-document detail fetch growth for ordinary records,
bounded display-body loading and no more than 20% median regression against the
same baseline. Set an absolute p95 budget only after baseline measurement. Do not
hide linked-work costs in the ordinary average or ship inaccurate counts to meet
a budget. The original planning stage ran neither benchmarks nor executable tests;
candidate validation and performance evidence are recorded below.

## Review and next action

The owner selected implementation of the bounded My next steps contract. Review
the candidate, validation evidence and performance limitation below before any
release decision. Division counts and later phases remain separate.
Before any future release reconcile with then-current main, synchronize release
metadata and pass every existing release/backup gate. Candidate 10.14 must be reconciled with main after #604 merges and then pass
fresh complete normal/shuffled CI, audit, metadata and Required checks. It remains
a draft because the performance gate remains unmet; checked release is now authorized
only after that blocker and all release gates are satisfied.


## Candidate implementation details

`documents_actions.page` scans permitted candidate facts in 1,024-row batches in
one read snapshot, counts matching distinct documents, and retains only the next
page plus one matching document. Cards and counts call the same guidance builder.
It does not invoke document detail context for every candidate.

The complete child sets are represented exactly for document/state/overdue counts:
all eligible contributions on a document share its paused/ready state, so the
minimum effective deadline establishes overdue membership; all unread instructions
share its module-enabled state and document deadline. SQL selects those representatives
from the entire eligible child set before any display cap. This is NOT an exact
step total. For display, overdue filtering occurs before child ranking/caps; text
is fetched only for displayed children. A change to per-child state semantics must
update this projection and its independent expected-set tests together.

Visible work links use RegistryScope.work_view_sql, the existing SQL counterpart
of strict work visibility, with alias resolution and every linked source checked.
Only the newest permitted case ID is projected, without case/task bodies. The
existing consolidation/release services remain authoritative where the actual
workflow branch needs them. Consolidation facts are loaded lazily; no shared
state is cached across requests. Complex review/release graphs still have costs
beyond the ordinary batch count and require separate profiling.

The route preserves validated filter keys and stable workflow/instruction/assignment
anchors, and sends private/no-store responses. It uses a native GET form without
JavaScript. Filter changes reset pagination. Division controls and count semantics
are unchanged. No new schema, dependency, workflow action, provider or background job.

### Reproducible validation

Use the isolated commands in [CLOUD_WORKSPACE.md](CLOUD_WORKSPACE.md). The optional
benchmark is intentionally outside normal pytest filename discovery:

```bash
.venv/bin/python scripts/cloud_workspace.py test tests/bench_document_steps.py -s --junitxml=/tmp/document-step-benchmark.xml
.venv/bin/python scripts/cloud_workspace.py test tests/test_document_action_pages.py tests/test_document_action_routes.py tests/test_document_action_browser.py tests/test_documents_navigation.py tests/test_documents_guidance.py tests/test_document_guidance_routes.py tests/test_document_guidance_browser.py tests/test_document_step_filters.py tests/test_document_step_filters_browser.py tests/test_document_workspace_navigation.py --junitxml=/tmp/document-step-checks.xml
.venv/bin/python scripts/check_release.py junit /tmp/document-step-checks.xml
```

The benchmark loads the shipped action-page module from `6452931` and compares
it to the candidate on the same disposable fixture. Its first request is reported
separately, followed by 30 warm requests per scenario/size. Rows and logical UTF-8
value bytes measure data fetched into Python, not physical database I/O. Peak
memory is Python tracemalloc, not total SQLite/process RSS. Each result also
includes SQL count and EXPLAIN QUERY PLAN; temporary sort structures remain in
SQLite. These synthetic local measurements do not establish production latency
or staff completion times. Detailed output remains in local /tmp test artifacts.

### Measured read cost and remaining performance decision

Nine scenarios completed on Python 3.11.17 in the managed workspace. Times below
are milliseconds, page size 30; each warm distribution contains 30 requests.
Linked scenarios have one visible case and one contribution per document.
Restricted/alias scenarios hide one third and alias one third of the seeded rows.

| Records | Scenario | Baseline median | Candidate median | Candidate p95 | Candidate SQL reads | Python peak MiB |
| ---: | --- | ---: | ---: | ---: | ---: | ---: |
| 100 | ordinary | 2.31 | 3.50 | 3.97 | 25 | 0.20 |
| 100 | linked contributions | 5.67 | 5.45 | 7.14 | 26 | 0.29 |
| 100 | restricted aliases | 2.43 | 2.81 | 3.08 | 25 | 0.10 |
| 1,000 | ordinary | 3.03 | 18.08 | 20.10 | 25 | 1.91 |
| 1,000 | linked contributions | 17.01 | 29.02 | 34.58 | 26 | 2.87 |
| 1,000 | restricted aliases | 2.72 | 7.33 | 8.10 | 25 | 0.64 |
| 10,000 | ordinary | 10.02 | 164.10 | 258.67 | 79 | 3.55 |
| 10,000 | linked contributions | 149.13 | 434.32 | 469.31 | 80 | 3.83 |
| 10,000 | restricted aliases | 6.00 | 58.24 | 65.75 | 43 | 3.33 |

The provisional <=20% median-regression goal is **not met** in most scenarios.
Complete scope classification adds work that the shipped page-only view avoids;
the batch design bounds Python materialization, not total classification cost.
This is an explicit draft-review limitation, not a passed performance gate or
permission to relax one. The largest measured p95 was below 500 ms, but that is
an observation, not an approved production budget. Complex consolidation/release
review graphs are not represented by these simple linked-contribution fixtures;
profile those before claiming a general bound. Release readiness needs an explicit
performance-budget decision or further optimization, plus normal full CI.

At 10,000 records the candidate projects approximately 10,050 rows / 689,905 logical bytes (ordinary), 30,140 rows / 1,066,656 logical bytes (linked contributions), 3,377 rows / 230,610 logical bytes (restricted aliases). Subject/number and child text are limited to the selected page.
Query plans use the existing document/assignment indexes and SQLite temporary
sorting; no schema/index change was made. A rollback needs only code/navigation
restoration, preserving every document, receipt, work item and audit record.


### Candidate verification result

348 document/shared-work/registry/navigation/guidance regressions passed in 92.03s.
A final focused run including the added migrated-child check passed 15 filter and
browser cases in 14.83s. Groups overlap and are not additive unique-test totals.
Both JUnit reports passed the no-failures/errors/skips gate. Nine benchmark scenarios
also completed; their completion does not mean the latency goal passed. Existing
Starlette/httpx deprecation warning only. Phone/desktop, keyboard, no-script,
filter reset, return links and actual HTTP save/redirect context are covered.
Synthetic screenshots were inspected. Cross-SQLite tests execute actual selection,
child and permission statements under the OS SQLite parser as well as Python's.
Release metadata 10.14, JavaScript syntax, local Markdown links and diff whitespace
passed. Full normal/shuffled CI and dependency/release gates are still required;
there is no production preview, staff study, merge or deployment claim.


### November 8 release assessment — blocked on performance criteria

#604 is merged/deployed; this review branch is reconciled with main `e471261`.
The owner authorized releasing #605 when ready, but did not waive the <=20%
median-regression goal. No runtime optimization or policy change is claimed in
this follow-up: it adds missing graph profiling and fixes benchmark accounting.

The extended fixture links ten outgoing documents per shared case, with three
accepted contributions, current exact versions and current consolidation packets.
Every document reaches both consolidation-current and release-contribution checks.
The final measurement ran alone, with 30 warm requests per implementation/scenario.
[Compact reproducible results](document-step-performance-2026-11-08.json):

| Records / scenario | Baseline median ms | Candidate median ms | Candidate p95 ms | Baseline / candidate SQL reads |
| --- | ---: | ---: | ---: | ---: |
| 100 ordinary | 2.528 | 3.817 | 4.430 | 18 / 25 |
| 100 review/release graph | 33.705 | 84.917 | 89.262 | 6,318 / 15,885 |
| 1,000 review/release graph | 40.758 | 678.922 | 727.210 | 6,318 / 125,685 |

At 1,000 graph records the allowed median under the existing target is 48.91 ms;
the candidate is approximately 16.7 times baseline. This is a diagnostic fixture,
not a production forecast. The 10,000-record graph was not measured, and no bound
for larger graphs or concurrent users is asserted. Profiles locate the dominant
cost in guidance → consolidation summaries → strict work access and review snapshot
construction. Those checks enforce current source access and exact review inputs;
removing them or copying approximate status rules would be incorrect. The existing
bounded scan/compact projections already avoid full ordinary document detail loads;
small rendering changes cannot remove this whole-scope review cost.

Memory-accounting correction: the earlier table's tracemalloc peak also retained
SQL trace strings, so it is not an application-only memory estimate. The benchmark
now records SQL separately from peak allocation. Corrected candidate peaks for
these three scenarios are 185,562 / 337,432 / 2,811,168 bytes respectively. Raw query
plans and cumulative profiles are emitted with each optional benchmark run.

Reproduce with the cloud test wrapper and `tests/bench_document_steps.py -s -k
'100-ordinary or 100-review_release_graph or 1000-review_release_graph'`. Three
selected benchmark cases completed; completion is not acceptance of their latency.
The 15 focused filter/browser checks also passed after reconciliation, without
failures/errors/skips. Release metadata 10.14 passed against current main. Fresh
full CI remains required for the new head, even though the performance gate blocks
release independently.

Owner decision needed: retain the relative target and expand the design beyond
this bounded scan (shared batched classification or explicitly maintained facts,
with a separate permission/revision invalidation design), or agree an absolute
latency and supported-scope budget and measure that budget before release. An
absolute budget has not been selected or approved. Recommend retaining the target
and reviewing a redesign rather than releasing this scan on green CI alone.
#605 remains draft; #606 remains queued. The release automation is paused at this
user decision, not marked complete. Staff testing and production data are not used.
