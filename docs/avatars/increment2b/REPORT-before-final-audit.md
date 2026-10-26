# Increment2B — complete hosted verification

Current candidate: **`f700187`**, static picker/growth SVG trimming. Eight browser
regressions, actual native input/visibility, persisted care, seasonal live refresh
and1,734 unchanged live SVG checks pass locally.4,896 static cells match the
full SVG under the same uncomposited paint mode. Original rasterized pixels differ
(sharper static edges); both comparisons are retained.
[Candidate evidence](static-preview-fix/assessment.json).

The original warm desktop memory failure reproduced in both execution orders:
+14.520MiB and+12.629MiB. Candidate memory verification passed both orders (+8.551/+8.285MiB) in
[40260864049](https://github.com/jongsky25/css-is/actions/runs/40260864049).
Complete final verification is running in [40263865865](https://github.com/jongsky25/css-is/actions/runs/40263865865), harness`e909de1`;2B acceptance remains pending. The completed timing results
below apply to the unchanged-runtime prior productc2f404f.


**One remaining acceptance failure: warm desktop picker renderer memory.**
[Audited results](hosted-complete/summary.json) and
[all numeric evidence](hosted-complete/numeric-evidence.tar.gz).

Hosted run40247047928 completed all four phases. Functional, focused/native,
whole-runtime, controls and all callback/frame gates pass. The only failed gate
is warm desktop picker RSS: +11.199MiB, exceeding10MiB by1.199MiB.
Other picker device/cache groups pass. Source remainsc2f404f.
A memory diagnostic records per-process RSS/private/shared allocations in both
execution orders before selecting an optimization. No gate is waived.

The sections below preserve the earlier investigation chronologically; their
“running”/“no run” statements are superseded by this completed outcome.

## Historical preference-cache follow-up

**Acceptance remains unresolved.** Product revision `c2f404fa5aa58abebbe0127bbb537b5592993ce5`.
[Assessment](preference-cache-fix/assessment.json).

Avatar input/timer handlers now read an event-updated reduced-motion boolean
instead of querying MediaQueryList.matches each time. The existing preference
listener updates it live, with legacy addListener support. A queued curiosity
frame rechecks the cached preference before writing transforms.

[Eight browser checks](preference-cache-fix/tests.txt) pass. The new regression
confirms zero avatar preference-query reads during pointer input and correct live
reduced-motion on/off behavior. [1,734 SVG comparisons](preference-cache-fix/artwork-equivalence.json)
pass; artwork/CSS remain unchanged apart from JS cache key8.21.

Five counterbalanced fern pairs, mature6/CPU4/30s, produced:

- Current callback maxima: [20.765, 49.782, 210.804, 13.408, 13.204]ms.
- Old-art control callback maxima: [81.97, 6.265, 6.399, 163.949, 158.973]ms.
- Current framep95: [16.8, 33.4, 16.8, 16.8, 16.8]ms.
- Old-art framep95: [16.8, 16.7, 16.8, 99.9, 66.7]ms.

The current210.804ms event is the chase timer. Controls also have large stalls;
this does not isolate the underlying cause or waive any result. No errors or
trace loss. [Every sample and raw trace](preference-cache-fix/traces/fern/summary.json)
and [runner log](preference-cache-fix/trace-tests.txt) are retained. Synthetic
throttle time remains inside measured callback wall duration; none is subtracted.
The user-approved33.3ms frame exception remains accepted. Callback50ms and
uncompleted acceptance checks remain required. Remaining trace species/native
cohorts/full matrix were not started after the failure.3A remains pending.

[Prior verification and frame exception](REPORT-chase-write-fix.md).
No deployment or additional application changes based on an unproven stall cause.


## Native throttle attribution and complete verification follow-up

Harness revision `f421044`, hardened at `0bd9092`; product remains `c2f404f`.
[Native signal records](signal-attribution/signal-analysis.json) show unchanged
Chromium throttling-handler pauses up to **345.950ms** during input. All ten
instrumented diagnostic callback maxima are below50ms. These are diagnostic
results, not acceptance: the native probe affects scheduling, and cannot explain
away every prior slow callback. No time is subtracted from a gate.

An independent kernel-cpuset fixture still recorded a **148.967ms** current-art
callback and was [rejected](cpuset-fixture/PLAN.json). No fixture or product
change from that experiment is enabled in acceptance runs.

The [verification branch](https://github.com/jongsky25/css-is/tree/codex/avatar-2b-verification)
contains a complete hosted workflow: functional checks, empty controls/native15/
trace30, and sequential original20/current20 matrices on one runner. Independent
phases retain results even when another fails. RSS comparisons require identical
renderer counts. Browser version, source hashes, failed samples, logs and all raw
measurements are retained; callbacks stay50ms and the user-approved frame ceiling
stays33.3ms. The driver compiles and the workflow parses locally.

The branch is present on GitHub, but the workflow query has reported **no run**.
No hosted pass, installed CI browser, or completed matrix is claimed. The reason
GitHub has not started the workflow is unknown. A workflow_dispatch trigger is
included, subject to GitHub's default-branch discovery rules. The same driver can
be run on a configured runner as `python scripts/avatar_baseline/ci_verify.py`
with each of `functional`, `focused`, and `matrix` in turn. **2B remains unresolved;
3A stays pending.** Nothing was merged or deployed.


## Verification repair — 2026-10-26

Correction: the earlier statement that GitHub had no workflow run was based on
an empty result from the commit-workflow-runs connector. The public Actions page
shows runs40245277942 and40245566959; direct job/log queries confirm dependency
installation failed because Chromium154.0.8037.57 is absent from Debian's current
repositories. [Exact error](verification-repair/hosted-install-failure.txt).
Actions was running. The commit-run tool explicitly filters to PR-triggered runs;
I incorrectly treated its empty result as evidence that no push-triggered run
existed. Direct run/job queries and public Actions discovery resolve that monitoring error.

Harness `65f1e16` fixes independent-check error isolation, validates JUnit counts
and exit codes, rejects missing/skipped/lost/duplicate samples, and reports invalid
controls as inconclusive. Test assertions use the already approved33.3ms ceiling;
callbacks remain50ms. Historical baseline failures are retained separately from
current failures. A new whole-runtime phase checks out pre-2B `5b580d9`, including
its original JavaScript, rather than only substituting SVG into current runtime.
All four hosted phases run sequentially and retain their outputs despite failures.

The hosted protocol now explicitly pins Chromium156.0.8078.47 and collects fresh
original/current comparisons with that same browser. No historical154 timing is
mixed into156 deltas. The Python container is digest-pinned to the image whose
exact browser and hash-locked Python dependency installation passed locally.
[Setup evidence](verification-repair/setup-assessment.json).

Thirteen driver regression tests pass. The unchanged product passes eight browser
regressions,1734 exact SVG comparisons, actual hidden/touch/keyboard checks, and
persisted care for all three plants on154. Six blank-page CPU1/CPU4 controls also
pass on156; that diagnostic is not avatar acceptance. All retained checks are in
[verification-repair](verification-repair/functional-assessment.json).

[Hosted run40247047928](https://github.com/jongsky25/css-is/actions/runs/40247047928)
has passed installation and driver tests and is executing complete verification.
Final performance verdict is pending its artifacts. Product remains `c2f404f`;
no new application optimization, merge, or deployment has been made.


Additional local preflight: all functional checks also pass on156. The new
artifact auditor has16 combined driver/audit regression tests. It checks raw
cohort identities, source/browser consistency and missing artifacts rather than
trusting green phase labels alone. A one-sample whole-runtime smoke comparison
confirms genuinely different old/current JavaScript hashes; old/current callbacks
are13.658/45.450ms and both framep95 values16.8ms. This validates harness operation,
not acceptance or a statistically established regression. [Smoke evidence](verification-repair/runtime-smoke/assessment.json).

The Chromium native throttler source file is byte-identical between154 and156;
no throttler implementation fix is claimed from the browser upgrade. Its purpose
is reproducible installation and a fresh matched protocol. Hosted measurements
remain necessary. The final artifact audit can be reproduced with
`python scripts/avatar_baseline/assess_complete.py <downloaded-artifact-root>`.
