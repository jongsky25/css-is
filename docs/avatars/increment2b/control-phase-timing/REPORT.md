# Control timing diagnostic: navigation and serialization delays with CPU steal

**The separate control diagnostic is complete.** Slower operations coincide with
substantial aggregate CPU steal time, providing concrete evidence of virtual-host
contention during this diagnostic. Cgroup quota counters show no throttling.
This narrows the runner investigation; it does **not** prove the cause of the
previous v12 control failure or qualify its instrument. **2B remains blocked.**

## Frozen attempts and integrity

Initial harness **d867258** attempted all four slots. Each stopped before the
measurement window because `/proc/<python>/task/<python>/children` is absent in
this runtime. All four errors, captures and identity traces are preserved in
`diagnostic-v1-failure-evidence.zip`. A read-only path check isolated this missing
file; the required stat, schedstat, cgroup and load files were readable. None of
these initialization failures is a timing observation.

Repair **84ce8e9** uses pinned Playwright PipeTransport's existing subprocess PID
and validates its parent PID against this Python process. Its distinct fixed
four-slot attempt completed, without replacements. Same pinned Chromium
156.0.8078.47 / ELF 1c5dca8527a61d07372e489142bee26af1bcaf71, twelve original
3,000-element DOM/SVG/style fixtures and four 32-receiver groups per document.
Each capture contains 108 ordered operation brackets and 216 bounded CPU snapshots,
plus initial host context, exact DOM hashes, census results and beacon disposition.
No native injection or full measurement trace, application DB or user workload.

[Archive recheck](archive-recheck.json) reconstructs both archives: **19 logical
files each** and identical audits. The complete diagnostic verifies five frozen
source files and twelve cohort files. The failed diagnostic's checker reports
zero cohort files verified because it rejects each nonzero exit first; all twelve
raw cohort files are nevertheless preserved and content-addressed by the archive.
The complete archive independently reproduces the offline CPU-context summary.

## Four uninjected diagnostic controls

| Slot | Total ms | Navigation ms | Before-DOM serialization ms | Telemetry ms | Aggregate CPU steal | Quota throttle ms |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 0 | 4074.812 | 876.877 | 161.325 | 63.942 | 3.0141% | 0 |
| 1 | 3687.714 | 634.005 | 117.275 | 61.582 | 0.9831% | 0 |
| 2 | 4283.092 | 1018.697 | 279.534 | 65.545 | 8.6096% | 0 |
| 3 | 3784.391 | 702.127 | 131.494 | 65.280 | 1.0621% | 0 |

All operation intervals, CPU deltas and browser navigation timings are in
[cpu-context-summary.json](cpu-context-summary.json); the full audited phase/counter
breakdown is in diagnostic-v2-audit.json.gz. CPU steal percentages use the first
eight aggregate `/proc/stat` CPU columns; guest counters are not counted twice.
They describe CPU context sampled around calls, not a fraction of per-process wall
time or a quantity to subtract. Snapshots are sequential, not atomic.

The slowest/fastest total difference is **595.378ms (16.1449%)** in this instrumented
diagnostic. Navigation contributes **384.691ms**, and before-DOM serialization
**162.258ms** of that difference. Fixed waits contribute only **12.591ms**. This
localizes the bulk of the difference to navigation/serialization rather than the
nominal 220ms wait, getter census or recorder (which is absent).

The clearest observation is slot 2's first DOM document:

| Operation | Slot 1 ms | Slot 2 ms | Slot 2 aggregate CPU steal |
| --- | ---: | ---: | ---: |
| Host navigation call | 50.187 | 284.795 | 31.0345% |
| Before-DOM serialization | 11.569 | 171.235 | 38.7387% |

Slot 2 browser Navigation Timing reports **112.600ms**, versus the host navigation
call's **284.795ms**. The **172.195ms** difference includes work before/after the
browser navigation timeline and IPC/scheduling; it is not proof of where every
millisecond was spent. During serialization, renderer aggregate CPU advances
20ms at 10ms tick resolution; its main-thread runqueue wait advances 6.613ms.
The rest cannot be assigned exclusively to one process or scheduler. The concurrent
CPU-steal signal supports investigating virtual-host contention; it does not
establish exclusive causation or an exact correction to durations.

## Host limits and qualification status

The runtime reports affinity CPUs 0–4 and cgroup quota `400000 100000` (four CPU
seconds per second). Throttled-period and throttled-time counters do not advance
in any operation bracket. Host and cgroup CPU-pressure files are unavailable and
are explicitly retained as missing. Main-thread schedstat is readable in the
completed captures but covers only those threads; zero values alone would not
prove absent scheduling delays. Other browser processes and shared cgroup work
are not attributed to the four tracked processes.

Telemetry adds **61.582–65.545ms** per run, and the added navigation-timing queries
add **20.767–28.254ms**. Both are retained. These new diagnostic durations cannot
replace or adjust original qualification samples. In particular, this diagnostic's
16.1449% range does **not** reverse v12's **20.7568% >20%** control failure. No CPU
steal counters were captured in v12, so its historical cause remains unproven.

The C recorder's prior cost/reclamation success remains evidence, but the
instrument is still unqualified for application calibration. Product cf363bf is
unchanged; isolated candidate cd94bf3 is unpromoted. No acceptance, later increment,
merge or deployment follows. **97 focused tests pass** (existing Starlette warning).

## Next bounded work

Investigate **runner contention/isolation** before another qualification screen.
Obtain provider/runtime evidence of the virtual CPU scheduling constraints and a
concrete supported isolation or reserved-capacity intervention while preserving
pinned browser, fixture and resource comparability. This session establishes a
host-level signal but does not identify its provider-side source or demonstrate
an intervention. No environment resource or affinity settings were changed.

Do not repeat unchanged v12 until a quiet interval appears, discard high-steal
samples, use a post-hoc load gate, subtract scheduling time, or relax budgets. Any
new runner condition and capture policy must be frozen before a new complete
fixed comparison; all slots and failures remain. Application memory comparisons
still require a fully qualified instrument. No product memory fix is established.

```sh
.venv/bin/python -m scripts.avatar_baseline.package_cat_gradients \
  docs/avatars/increment2b/control-phase-timing/diagnostic-v2-evidence.zip \
  --unpack-to /tmp/control-phase-evidence
.venv/bin/python -m scripts.avatar_baseline.control_phase_timing audit \
  --out /tmp/control-phase-evidence/diagnostic-v2
.venv/bin/python -m scripts.avatar_baseline.summarize_control_timing \
  /tmp/control-phase-evidence/diagnostic-v2 --out /tmp/control-phase-summary.json
```
