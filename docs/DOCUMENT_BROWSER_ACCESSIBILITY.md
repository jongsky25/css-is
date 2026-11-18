# Documents browser and accessibility increment

Candidate **10.38**, branch `test/documents-webkit-accessibility`, stacked after
#630. The November 18 instruction “okay queue one by one” queues this increment
first, then division follow-up counts/filters. Preserve sequential guarded releases
for #629 and #630; this candidate is queued for review, not yet authorized for merge. Staff invitations and real-device sessions are
not part of this automated increment.

## Changes

- Reuse request-context, source-review, target-date and history-pagination journeys
  in WebKit on Linux, at phone and desktop widths with JavaScript on/off.
- Check native keyboard focus/navigation, form validation and persisted writes,
  emulated touch, and 320 CSS-pixel reflow with the root text size enlarged to 200%.
- Fix actual overflow found by those checks: the mobile work grid used an implicit
  minimum content width; long controls/buttons and the new-correspondence link
  exceeded the viewport. Grid tracks now allow shrinking and affected controls/
  buttons wrap within their available width. WebKit's select painting is contained
  within the control; options remain selectable and their full labels stay in the
  native menu. No page-level overflow hiding is used.
- Isolate passive telemetry in the synthetic route harness while retaining exact
  business POST counts, native validation and database assertions.
- Add `Documents WebKit accessibility` to the shared release workflow and to the
  aggregate Required checks prerequisites. It installs the existing hashed test
  lock and Playwright WebKit/system dependencies; a missing browser, failure,
  skipped case or missing/empty JUnit report fails the gate. PR and guarded main
  deployment both run it. Existing complete normal/shuffled suites and audit gates
  remain mandatory.

## Verification

The final focused run passed **81 tests**, with no failures, errors or skips:
21 WebKit journeys and 60 Chromium/context/reconciliation/release-gate checks.
The JUnit gate, candidate 10.38 metadata, locked inputs and diff checks passed.
Full hosted normal/shuffled CI and standard WebKit CI remain required.

## Reproduce

```bash
bash scripts/cloud_setup.sh
.venv/bin/python -m playwright install --with-deps webkit
.venv/bin/python scripts/cloud_workspace.py test tests/browser_documents_webkit.py --junitxml=/tmp/documents-webkit.xml
.venv/bin/python scripts/check_release.py junit /tmp/documents-webkit.xml
.venv/bin/python scripts/cloud_workspace.py test tests/test_request_context_accessibility.py tests/test_request_reconciliation_browser.py tests/test_release_checks.py --junitxml=/tmp/documents-accessibility.xml
```

The cloud image initially lacked WebKit libraries and administrator installation.
For local verification, official Debian trixie packages were downloaded over HTTPS,
checked against SHA-256 from the Debian package index and extracted into the
user-owned Playwright bundle. A temporary local runner launched the same WebKit
executable explicitly because host-library validation cannot find user-local
libraries. No application fixtures, assertions or release workflow gates were
bypassed. Hosted CI uses standard `install --with-deps webkit` and the unmodified
runner; it must pass before release. The local runner is not committed.

Linux WebKit is not actual Safari on an iPhone. Emulated touch is not a physical
device test. Text resizing/reflow and semantic keyboard checks do not constitute
a VoiceOver or other screen-reader pass. Staff task timing/error improvements
remain unmeasured. Real device/screen-reader sessions and staff pilot participation
require their own arranged testing.

## Next queued increment

Assess and extend full-scope document counts and Ready/Waiting/Needs attention
filters to Division follow-up using current chief/OIC scope and the existing shared
classifier. Define mixed-state document semantics consistently with My next steps;
filter before pagination and prove no restricted-document or private-work count
leaks. Benchmark synthetic scopes and preserve current sort/queue return behavior.
The existing conditional follow-up will build this as a separate draft PR after
#630 deployment and #631 reconciliation/fresh CI assessment; do not combine it here.
The accepted 10k count-performance exception remains accepted, not a new blocker.
