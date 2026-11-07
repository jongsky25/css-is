# My next steps: proposed count and filter contract

Planning specification, November 7, 2026. No implementation or release authority.
Branch: `docs/my-next-steps-count-contract`, based on #604 head
`7de2a9be7b15f535ed3aeb9c1811fc778ee09ca4`. #604 has its own checked-merge
authorization; this branch does not inherit that authorization.

## Outcome and scope

A person can identify documents with ready, waiting or attention steps across
their entire permitted My next steps scope, then return to the same filtered
view after inspecting a document. Counts describe documents, not productivity.

Scope is `/documents/actions?view=mine` only. Division follow-up, request-execution
changes, new workflow actions, staff studies, schema changes and notifications
are deferred. Preserve shipped #596–603. See the [handoff](DOCUMENTS_NEXT_PHASE_HANDOFF.md).

## Current evidence

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

## Recommended rules

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

## Proposed implementation boundaries, after authorization

Build a compact, uncapped classification projection shared by cards and counts.
Keep instruction/assignment IDs, state, due date and permitted navigation facts;
load display bodies only for the selected page. Reuse guidance policy with
batched facts, rather than reproducing its decision tree in independent SQL.
Characterize current guidance versus action-page facts before extraction, including
cases where display-capped assignments could affect advice. Any discovered policy
discrepancy needs explicit characterization rather than a silent counting change.

Measure linked-work visibility and review/release readiness separately. A design
that invokes expensive detail context once per full-scope document is unacceptable
without a demonstrated bound. Decide SQL projection versus bounded internal scans
after profiling; a bounded scan may limit memory but does not make total work constant.
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
a budget. Baseline measurements and executable tests have NOT been run here.

## Review and next action

This document supplies recommended semantics, not owner-approved product decisions.
Review overlapping document counts, same-step overdue intersection, matching-card
display and retained document ordering. Then explicitly authorize the bounded
My next steps implementation. Division counts and later phases remain separate.
Before any future release reconcile with then-current main, synchronize release
metadata and pass every existing release/backup gate. This planning branch carries
10.13 only through its parent #604; it is not a separate release candidate.
