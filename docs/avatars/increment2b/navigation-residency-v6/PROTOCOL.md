# V6: scheduling and CPU-quota evidence for control stalls

V5 remains a failed calibration; its slow first control is retained, not replaced.
V6 adds NEW observations to distinguish possible sources of stalls. No product,
CPU quota, affinity, cache, screenshot, GC or workload change. Use the same pinned
Chromium, full 30-second warm-desktop fixture, original/current refs, and existing
five memory checkpoints. V5's two bounded traces and deferred transfer remain.

In BOTH controls and traced runs, record host bounds for all 20 Page.goto calls
and subsequent existing 220ms waits. Add cgroup cpu.stat and process stat/schedstat
reads to the existing 100ms status sampler. Cover all known renderer main threads,
pytest main thread and sampler thread. Record start-time identity, runtime, runnable
queue delay, process CPU ticks/faults, per-read bounds/errors and reader-thread CPU
cost. Take explicit scheduler snapshots just before/after the navigation window,
before any endpoint dump/transfer. Preserve all observations and missing processes.
Record CPU quota, effective CPUs, process affinity and cgroup identity. Missing
pressure/schedstats-configuration files remain unavailable; do not change kernel
settings or invent pressure measurements. This environment's schedstat values are
readable, but cgroup pressure files and sched_schedstats config are unavailable.

Analyze cumulative counter deltas, not absolute historical totals. Reject resets,
PID reuse, malformed bounds or missing cgroup data. Retain every per-navigation
bracket and every adjacent sampled delta; bracket intervals overlap and must not
be summed by navigation. Cgroup throttling covers ALL tasks in this cgroup, while
schedstat covers individual main threads, not every renderer worker. CPU waiting,
throttling and page long tasks may overlap; no automatic causal attribution or
historical reconstruction of V5. Read errors remain explicit.

NEW fixed calibration: current control/trace/trace/control, fresh process/database/
browser, ordinal 0. Complete all four slots, keep failures, no replacements.
All V5 limits unchanged: <=5% explicit trace pause sum, <=250ms individual pause,
<=20% trace/control duration increase in both orders and <=20% control duration
variation. Add scheduler reader CPU <=1% of navigation wall time per slot.
This screens reader CPU cost, not all possible measurement effects. Missing core
telemetry fails integrity; no favorable RSS selection or acceptance claim.

Only after the complete calibration passes: eight NEW original/current/current/
original, current/original/original/current traced comparison slots, block ordinals
0/1, same committed harness, calibration audit hash recorded. Retain every result,
all 13 RSS/heap checkpoints and all eight source/control pairs. Per-slot pause,
reader-cost and trace-integrity gates remain. No concurrent heavy analysis during
measurement. No replacement slots, forced GC, relaxed budgets, or 2B acceptance.
If calibration fails, preserve it and stop comparison. Archive all evidence and
independently re-audit. Later increments remain paused.
