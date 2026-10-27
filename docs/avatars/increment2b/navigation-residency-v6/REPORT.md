# Scheduler evidence: extra CPU execution, no recorded quota throttling

**Calibration fails; 2B remains blocked.** All four V6 slots completed from
`75c6e85`, with new scheduling observations in control/trace/trace/control order.
No source comparison was launched. The first/final controls take 10.702/8.388
seconds, a **21.62% change**, exceeding the unchanged 20% stability gate. The
failure is retained, not rounded down, excluded or replaced.

## What the new evidence establishes

Every navigation is bounded by host timestamps. Cgroup CPU counters, per-process
CPU/fault counters and main-thread scheduler counters span the navigation window.
Both controls have **zero increases in nr_throttled and throttled_usec**. In fact,
all four runs have zero recorded cgroup throttling. Cumulative historical throttle
counts observed before the experiment are not evidence of throttling in these runs.

| Measurement | First control | Final control |
| --- | ---: | ---: |
| Navigation wall time | 10702.468ms | 8388.222ms |
| Sum of Page.goto time | 5886.531ms | 3763.165ms |
| Sum of existing waits | 4474.079ms | 4442.407ms |
| Python process CPU, all threads | 5350ms | 3690ms |
| Python main-thread running / runnable wait | 1383.443 / 562.104ms | 733.910 / 374.034ms |
| Dominant observed renderer process CPU, all threads | 6780ms | 4220ms |
| That renderer main-thread running / runnable wait | 4008.896 / 674.242ms | 2529.564 / 383.325ms |
| Cgroup CPU usage, all tasks | 19647.928ms | 12740.955ms |
| Observed major page faults, retained edge tasks | 0 | 0 |

About 2.123 seconds of the 2.314-second wall-time difference occurs inside
Page.goto. The waits differ by only 31.672ms. The slower renderer spends about
1.479 seconds more running on its main thread and 0.291 seconds more queued;
Python also runs longer. These concurrent times must NOT be added to account for
elapsed wall time. The process-wide CPU totals include worker threads; schedstat
is main-thread only. Cgroup usage includes every task in the container.

The dominant renderer is described by its observed CPU use, not asserted to be the
page PID: untraced controls deliberately have no CommitLoad association. Every
observed PID, identity, delta, missing task and navigation bracket is preserved.
The slow control is broadly slower across navigation, unlike V5's concentrated
early stall. One retained checkpoint contains 146ms of long tasks; this does not
explain the full wall-time difference or reconstruct the untraced intervals.

The data supports extra measured CPU execution and some queue delay, rather than
recorded cgroup quota throttling, as contributors in this NEW cohort. It does not
show which Python/Chromium function did extra work or whether effective CPU
execution speed changed. Pressure-stall metrics are unavailable in this environment.
It cannot retrospectively establish the cause of V5's 16.76-second control.

## Instrumentation and gates

| Slot | Mode | Navigation ms | Explicit trace pauses | Largest pause ms | Scheduler reader CPU |
| --- | --- | ---: | ---: | ---: | ---: |
| 0 | control | 10702.468 | <0.001% | 0.001 | 0.882% |
| 1 | trace | 9127.850 | 2.177% | 159.068 | 0.623% |
| 2 | trace | 8771.072 | 2.102% | 165.527 | 0.739% |
| 3 | control | 8388.222 | <0.001% | 0.001 | 0.687% |

All explicit pause limits (5% total / 250ms individual), paired trace/control
duration upper bounds and the NEW <=1% scheduler-reader CPU limit pass. All six
trace segments are intact, sealed snapshots match, and no allocator dump or trace
transfer occurs inside measured navigation. Only the unchanged-control duration
stability gate fails. Reader CPU cost is not a proof of zero observational effect.

Audit verifies **120 source/probe hashes and 30 cohort files**. The archive contains
36 members; independent extraction/re-audit reproduces the full assessment.
**65 focused tests pass**, including counter reset, PID reuse, missing core data,
bounded navigation, deferred transfer and existing trace/overhead checks.
No CPU quota, affinity, kernel setting, cache, screenshot or product was changed.

## Disposition and next evidence

Preserve this failed calibration and all V3/V4/V5 evidence. Do not rerun this
unchanged instrument for a favorable control or launch the source comparison.
No memory waiver, product correction, original/current conclusion or 2B acceptance.
Product remains f700187 and later increments remain paused. No measurement active.

The next targeted diagnostic should profile CPU work in BOTH the Python server/
driver and Chromium during the navigation window, with explicit costs and fixed
controls. Function-level work and CPU execution-rate evidence are needed before
choosing a warm-up, host-isolation or product change. The current data does not
justify picking any of those as the fix. That diagnostic has not been launched.

Evidence: `calibration-evidence.zip`, `calibration-manifest.json` (archive/member
hashes and identical re-audit), `calibration.json` (all raw arithmetic, navigation
brackets and pair metrics), `scheduler-review.json` (all four runs, process CPU
and checkpoint long tasks), `tests.txt`, and `PROTOCOL.md`.
