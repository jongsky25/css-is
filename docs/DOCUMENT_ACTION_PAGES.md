# Current document action pages — A15, second slice (7.82)

“My actions” now explains whether a step is **Ready for you**, **Waiting**, or
**Needs attention**, with the responsible person or role, the next action and
its blocker. Workflow cards use the same `documents_guidance.build` service as
“What happens next?” on the document. A link opens the existing form or a
permitted shared-work screen; it never submits an action.

## Coverage

- Include current verification/ownership work for concerned records officers,
  corrections and outgoing drafts for their creators, assigned reviews, signing,
  lead follow-up, and queued operation recovery for the original requester.
- Preserve distinct unread tagged instructions and available legacy contribution
  steps. Contributions requiring the initial Director instruction or an unresolved
  signing/sending operation point to that prerequisite instead of an update form.
- Check current reviewer authority and exact-version/shared-work readiness. A stale
  review link no longer exposes a review form after the authority is removed.
- Return changed drafts to review preparation; direct partial/uncertain delivery
  to recipient outcomes or existing receipts. Never suggest blind resend.
- Show read-only guidance when Documents is disabled. Archived, closed, cancelled
  and merged source records are excluded from these active action lists.
- Apply the same current guidance to division exception pages, preserving current
  division authority and document access. Migrated contributions remain in Shared
  work; legacy assignment controls are not revived.

## Paging and read cost

The default page contains at most 30 **documents** (internal maximum 50), ordered
by their earliest applicable document/contribution deadline and descending ID for
same-day ties. Unknown deadlines sort last and are never marked overdue. The seek
cursor contains the deadline and ID, not authority. Both are validated; current
visibility, active account and division scope are reapplied before every LIMIT.
There is no unfiltered total or full-register materialization in the response.

A read savepoint keeps selection and page enrichment consistent. Core page data is
batched: current draft fingerprints, unresolved effect progress, instructions and
contributions. Each document shows at most three unread instructions and three
available legacy contribution steps in deadline order, plus its workflow card. The page explains
that opening a record shows all instructions and contributions. Only names needed
for the displayed responsibilities are loaded; full people/unit picker lists are
not loaded for the action screen.

Closure facts are read through shared SQL predicates and passed to the existing
closure checks. Delivery facts are aggregated for the current exact version.
Signatory and division scope use the existing current-account/directory/grant
scope. No provider request, signature bytes, job payloads or history bodies are
loaded by these ordinary action-page reads.

The existing strict shared-work visibility, consolidation snapshot and release
services remain authoritative for linked records on the selected page. Their
cost depends on those work graphs; this slice does not claim a constant query
count for arbitrary shared-work graphs or production latency. Routine query
count is checked against a growing synthetic register. The underlying SQL still
filters/sorts matching records, so database cost can grow with register size.

The cursor is a live view, not a saved assignment snapshot. If deadlines or
permissions change between visits, return to the first page to refresh priorities.
All POST handlers independently validate current permission, revision, policy,
exact version and external operation state.

## Verification and release

Tests cover complete workflow/card agreement, correction and returned review,
role revocation, pending initial routing, interrupted/uncertain effects, partial
and historical delivery, private shared-work inputs, deadline ties/unknowns,
permission-before-limit paging, cross-page revocation, current division OICs,
archived/closed/merged exclusion, disabled-module guidance, bounded child bodies,
read-only requests and escaped text. Real browser journeys follow cards using
keyboard navigation on mobile/light and desktop/dark layouts, focus the existing
nested form and refuse to expose a stale review form. The actual SQL is also
executed under the OS SQLite parser to catch deployment parser limits.

Version 7.82 follows main 7.81. Required normal/shuffled CI, release metadata and
dependency gates must pass for the exact PR head before merge. Manual production
workflow testing and observed staff before/after tasks remain deferred; A15's staff
pilot exit gate is still open. There is no schema or dependency change. Rolling
back the action-page integration requires no data rollback; preserve history and
current write authorization checks.
