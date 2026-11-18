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


## Remaining work screens and accessibility — candidate 10.36

Review branch: `feat/documents-context-accessibility`, based on main `39d346e`.
The November 18 instruction resumes navigation and accessibility improvements.
This candidate is for review; it is not merged or deployed.

The reviewed-request return links and source-change note now follow consolidation,
decision lists/details, message actions/history, blocker and prerequisite forms,
and Team contributions and Manager support. Case-level actions and older draft/file
links also retain context. Successful saves and validation errors keep the return path.
Aggregate GET filters use hidden validated context fields; list/board and pagination
links preserve their filters. Links to another case or an external provider do not
inherit the originating request. Current document/work access is checked again on
every page, including aggregate views. Ordinary entry without a request remains ordinary.

The two return links have named navigation semantics, visible keyboard focus and
at least 44-pixel target heights; they wrap within phone widths. No client script is
needed for the return path. Automated checks exercise Chromium and an opt-in Firefox
runner at 390px and 1280px, with scripts enabled and disabled, including native GET
filter submission, Tab/Shift+Tab and Enter. Chromium also exercises emulated touch.
The browser harness isolates passive telemetry while capturing business POSTs.

Local verification: the broader work/request regression run passed **206 tests**;
the final expanded context/accessibility run passed **24 tests**, including four
Firefox journeys. These groups overlap and must not be added as a distinct total.
Both reports have zero failures/errors/skips. Release metadata 10.36, dependency
lock inputs, vendor integrity and diff checks passed. Full required normal/shuffled
CI and dependency advisory auditing still need to complete on the PR.

Verification commands:

```bash
.venv/bin/python scripts/cloud_workspace.py test tests/test_request_context_screens.py tests/test_request_context_extended.py tests/test_request_context_accessibility.py tests/test_request_work_navigation.py tests/test_request_work_target_link.py tests/test_work.py --junitxml=/tmp/context.xml
.venv/bin/python -m playwright install firefox
.venv/bin/python scripts/cloud_workspace.py test tests/browser_request_context_firefox.py --junitxml=/tmp/context-firefox.xml
```

The Firefox runner is opt-in because the normal required CI environment installs
Chromium only. An explicitly requested Firefox run fails if its browser is missing;
it does not report a skipped check as success. Required release CI remains unchanged.

Limits: these checks are not a screen-reader session, a real touch-device test or
staff usability evidence. Staff timing/error measurements, review-history pagination
and the large-volume count performance exception remain separate backlog items.
Actual formal review, signing, dispatch and closure retain their existing services.
