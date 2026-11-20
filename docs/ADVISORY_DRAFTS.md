# Private activity advisory drafts — candidate 10.40

This is the first implementation slice of the [advisory workflow](ADVISORY_TRACKER_INTEGRATION_PLAN.md).
The owner authorized building with “start building” on November 20, 2026. The implementation uses
the recommended P2/P3 defaults: reserve the number on first save and support one advisory per
activity. Issuing authority, internal roster timing, signature/delegation and self-review policy
remain for the dependent review/issuance slices. Nothing here sends an advisory or approves it.

## Staff journey

When Documents and Shared work are enabled, **Open advisory** on an activity opens a private
preparation form. Those prerequisites are read at runtime and never enabled automatically.
`/activities/<token>/advisory/draft` also explains unavailable saving when either is disabled;
existing permitted drafts remain readable. The old poster feature remains compatible for
unmanaged records when those modules are disabled.

Choose the owning division, internal/external/both audience, and explicit external addresses.
Save the draft to reserve its stable advisory number and create a linked, restricted outgoing
Documents record. The Documents registration number is a separate internal identity. Only the
initiator initially has draft access; selecting an audience does not grant recipients access.
Current account status is always checked. Activity-management access permits initial preparation,
but another manager or technical administrator cannot read a subsequently private draft by default.

The activity and advisory register open the same record. Later content/audience/division changes
require a change summary and produce immutable revisions; no-op saves do not. History provides
the saved content, differences, author, time, summary and exact PDF/PNG for each revision. Ordinary
activity changes are shown for comparison and do not rewrite the draft. The comparison checkbox
records that the author considered the current source; it never replaces their entered text.

Validation errors preserve the form. A stale save is rejected with entered values intact and a
link to open the latest record in another tab; the server never silently updates the stale token.
Repeated delivery of the same save request returns the existing record. Reusing that request key
with different contents conflicts. The initiator may edit; explicit read access alone is insufficient.

## Existing records and public output

The separate **Existing activity advisories** view is a read-only, permission-checked projection
of unmanaged app records. It does not assign a division, approval, issue date or new number.
Preparing a private revision of an existing advisory retains its number and original row. On the
first successful private save of a published advisory, the existing renderer's output is captured
and frozen in the same transaction. Capture time is not represented as historical approval or
issuance time; historic PDF bytes that were never persisted cannot be recovered. Current rendered
content is retained, including the existing public PNG tested through its original URL.

The existing public URLs serve the captured copy, not the changing private draft. A new managed
draft is never public. Existing publish/save shortcuts and generic Documents mutation/release
operations reject managed records. Generic Documents detail links lead to the canonical advisory.
Review, comments/returns/resubmissions, approval, signatures, issuance, dispatch and publication
controls will be added in subsequent slices under the agreed Chief → Director workflow.

## Technical boundaries

- `advisory_storage.py` installs additive identity, revision, artifact, compatibility snapshot and
  request-idempotency tables. Existing app records are not copied in bulk or renumbered. Local
  document versions have an explicit `advisory` backend, authenticated artifact URLs and no fake
  Drive file IDs. Existing versions retain the `drive` default.
- `advisory_workflow.py` uses Documents registration, restricted access, shared registry visibility,
  current-actor checks and append-only audit events. It does not create another approval engine.
- The original number allocator now has a caller-owned transaction variant. `BEGIN IMMEDIATE`
  serializes number reservation, expected-revision checks, registration, artifacts, history and
  idempotency recording. Private saves do not change shared contact defaults.
- Rendering currently occurs inside the writer transaction so the reserved number and captured
  source cannot race. This is a bounded first-slice tradeoff: one-page locally generated artifacts,
  a 5 MiB cap per PDF/PNG, and no network work under the lock. Typical rendered artifacts and the
  renderer's existing layout limits are tested. A future render-outside-lock optimization must
  preserve atomic reservation and recheck inputs; it is not required for correctness here.
- Revision/artifact/request history and referenced file versions are protected against mutation;
  advisory identity fields are stable. Hash verification precedes artifact reads. PDF/PNG bytes
  live in the application SQLite database and follow its ordinary backup lifecycle.
- First-save registration suppresses notices and rule routing. Managed draft audit does not call
  ordinary Documents fan-out. There are no new workers, scheduled jobs, sending switches or
  external calls. External address lists are normalized/deduplicated and capped at 500 entries;
  actual recipient resolution/delivery belongs to the later issuance slice.
- The register has one shared permission/filter predicate for list and total counts, with keyset
  paging. Existing posters have a separately labeled view because they have no recorded division
  or approval history. Their permission scan streams rows and stops after a page of allowed items.

Source and acceptance map: [implementation design](ADVISORY_IMPLEMENTATION_DESIGN.md).
Tests: `test_advisory_workflow.py`, `test_advisory_draft_routes.py` and
`test_advisory_draft_browser.py`, plus existing advisory/Documents/routing/job/release regressions.
All fixtures are synthetic; browser requests stay in the test client. No production database,
provider, notification, deployment or preview is used. Targeted checks do not replace the complete
normal/shuffled, WebKit, dependency and release gates required for a future release.


## Saved verification

The final targeted run passed **164 tests** in 58.40 seconds, covering
`tests/test_advisory.py`, `tests/test_advisory_workflow.py`,
`tests/test_advisory_draft_routes.py`, `tests/test_documents.py`,
`tests/test_documents_routes.py`, `tests/test_document_action_routes.py`,
`tests/test_documents_jobs.py`, `tests/test_director_and_oic_routing.py`,
`tests/test_document_registry_sqlite_compat.py`, `tests/test_deploy_hf.py` and
`tests/test_release_checks.py`. The separate
`tests/test_advisory_draft_browser.py` run passed **2 tests** in 17.78 seconds,
with scripts enabled and disabled at phone width. JUnit gates rejected no tests:
there were no failures, errors or skips in either final report.

Run these through `.venv/bin/python scripts/cloud_workspace.py test`, supplying
`--junitxml=<temporary report path>`, then check each report with
`.venv/bin/python scripts/check_release.py junit <report path>`. Local report paths
were `/tmp/advisory-final-regression.xml` and `/tmp/advisory-browser.xml`; they are
workspace evidence, not durable attachments. Locked setup/doctor and
`check_release.py release --base 3eea227` passed. Changed-document local links and
`git diff --check` passed. No full release-suite, dependency audit, production or
hosted CI result is asserted by this checkpoint.

The combined regression run exposed a stale legacy render-cache key when activity
IDs/revisions repeat across databases. The cache now keys on actual poster content,
format and scale; the final run verifies the existing public image survives private
adoption unchanged. No cache clearing is used to hide the regression in tests.
