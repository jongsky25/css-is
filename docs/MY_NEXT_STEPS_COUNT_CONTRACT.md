# My next steps: count and filter contract

Implementation candidate 10.14, November 7, 2026. The owner's subsequent “do that”
authorized implementing this specification. Branch: `feat/my-next-steps-filters`,
based on the planning commit `a50807c` and #604 head
`7de2a9be7b15f535ed3aeb9c1811fc778ee09ca4`. #604 has its own checked-merge
authorization; this feature does not inherit its merge/deployment authorization.
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
a draft; no feature merge or deployment is authorized.


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
