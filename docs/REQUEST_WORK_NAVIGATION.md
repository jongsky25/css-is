# Request-to-work navigation

Candidate 10.15, stacked behind #605 on `feat/request-work-navigation`.
The owner authorized implementation and queuing behind #605. Release order is
#604, then #605, then this slice, with complete verification and guarded deployment
between releases. #605's performance blocker is not waived.

Opening existing work from a reviewed request now carries a `source_task` identity
and a validated Documents queue URL. Both existing-work links in the receipt use
this route. The work detail page offers a native link back to the exact request
receipt/comparison and, when present, the filtered Documents queue. Source changes
remain visible; viewing does not acknowledge, reconcile or overwrite anything.

The existing `documents_request_work.task_source` service checks current document
and work access. The task must belong to the displayed case. Missing, malformed,
inaccessible or wrong-case source identities create no context banner. Queue URLs
use the existing bounded allowlist, including My next steps filters and anchors;
query values never grant authority. Ordinary work entry without source context
retains its existing behavior and available per-task source links.

Standard contribution action forms retain context on validation errors and after
successful 303 redirects. Their CSRF, permission, revision and mutation services are
unchanged. This bounded slice does not extend context into discussion, decisions,
blocker subforms, consolidation, handoff, case-level actions or completion screens.
It adds no proposal creation, assignment, reconciliation, schema or provider calls.

Synthetic checks cover source changes, read-only state, denied work access,
malformed and wrong-case identities, hostile queue URLs, stale-revision errors,
successful contribution updates, and native keyboard phone round trips with and
without scripts. Existing request comparison/proposal and work tests also run.
Full exact-head normal/shuffled CI, AI evidence, audit, synchronized metadata and
Required checks remain mandatory before release. Reconcile against current main
after #605, recheck reviews/protection and merge bound to the verified head.
No staff study, production-data testing or manual deployment was performed.

Validation: 214 request/proposal/comparison/work regressions passed, followed by
16 final focused navigation checks (overlapping groups), with no failures/errors/
skips. Phone (390px) and desktop (1280px), JavaScript enabled/disabled, native
keyboard round trips and mobile screenshot inspection passed. Candidate 10.15
metadata, dependency lock inputs, vendor integrity, AI contract, JS syntax,
Markdown links and whitespace checks passed. Full CI remains pending.

## Extension to the discussion, draft and completion screens (10.23)

The context described above (the "Back to reviewed request and comparison" and
"Back to Documents queue" links and the source-change note) now also appears on the work
item's discussion, working draft and handoff, and release and completion screens when
they are opened from a request's work. The same validated `source_task` and `return_to`
values travel on the links from the work item to these screens and between them, in the
form actions and redirects (posting a message, following a discussion, saving a draft or
handoff, completion actions) and on re-shown error pages. The notice itself now lives in
the shared work layout and is attached only to these screens and the work item. Access
is unchanged: the request is re-checked on every page (a task from another case or a
forged value shows nothing, and a hostile queue address is dropped).

Still not extended: consolidation, decisions and decision detail, message edit history
and actions, blocker subforms, the team and manager screens. Measured effect (synthetic):
[before and after](request-work-journey-2026-11-10-context-screens.json).
