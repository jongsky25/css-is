# Increment2B — preference-cache follow-up

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
