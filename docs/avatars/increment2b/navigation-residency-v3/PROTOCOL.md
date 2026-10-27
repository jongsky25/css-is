# Bounded navigation trace, v3

Frozen before calibration. Diagnostic only; product original 1c964dc/current
f700187, Chromium 156.0.8078.47, fixture date July 15, full 30-second warm-desktop
workload and ordinal adapter unchanged. No forced GC, cache flush, screenshot
change, product patch, waiver, replacement samples or acceptance classification.

Remove all 20 in-workload allocator dumps and 40 extra full snapshots from v2.
Keep the existing five navigation checkpoints. Poll known renderer status every
100ms from background checkpoint through navigation 20, preserving actual bounds.
Trace navigation in four five-navigation segments, explicitly excluding other
categories, retaining devtools.timeline for CommitLoad PID identification and
CppGC/V8-GC categories. Request a 64MiB buffer per segment. Record begin/end clock
bounds and EVERY trace completion. Drain after checkpoints 5/10/15; all rotation
pauses are measured. Compress only after browser teardown. Correlations crossing
trace gaps are explicitly unavailable, never interpreted as no GC. Retain every
successive app-RSS drop >=5MiB, including uncovered intervals. Poll interval and
clock uncertainty remain explicit. GC overlap does not prove ownership/causation.

After the final navigation snapshot is sealed, stop polling, finish the last
navigation trace, and request ONE detailed natural allocator dump in a separate
trace with determinism=none. The endpoint is not a contemporaneous navigation
snapshot and cannot explain earlier physical-page release. Keep overlapping
allocator families separate; never subtract them from RSS. No exact page-owner
claim is possible without page mapping evidence.

## Fixed calibration gate

Four CURRENT-source fresh process/database/browser workloads, ordinal 0:
control / trace / trace / control. Controls retain the same five snapshots and
status polling; no tracing or endpoint dump. Preserve all outcomes, no replacement.
Require four valid workloads, complete sealed measurements, exact source/probe
hashes, all trace segments intact, uniquely identified app PID for traced slots,
no allocator dumps in navigation, and endpoint dump strictly after measurements.

For EACH slot, sum of explicit navigation trace-start/rotation pauses <=5% of
navigation wall time; maximum individual pause <=250ms. Traced navigation wall
time <=1.20 times its paired control in BOTH orders (0/1 and 3/2). Final control
wall time must stay within 20% of first control. These are instrumentation screening
limits, not product-performance budgets. They measure explicit pauses plus a
coarse same-source wall-time check; they cannot prove zero tracing/memory effect.
Keep all 13 checkpoint RSS/heap comparisons descriptively; do not use favorable
RSS to qualify the instrument or waive memory acceptance. Report maximum actual
poll gaps rather than deleting drops during natural stalls.

Only if calibration passes, run eight entirely new trace slots in fixed order:
original/current/current/original, current/original/original/current. Block 0 uses
ordinal 0, block 1 ordinal 1, preserving original screenshot behavior. Same committed
probe and analyzer; runner records the calibration audit hash. No concurrent heavy
analysis during measurement. Complete all eight slots even if one fails; no retries.
Recheck integrity and explicit pause limits for each comparison slot. Preserve all
four source pairs and four unchanged-source pairs at all 13 RSS/heap checkpoints.
Unchanged controls use absolute 10MiB stability, source pairs current-original use
10MiB upper bound, descriptively only. A passed diagnostic is not 2B acceptance.

Archive all raw evidence and failed attempts, verify file/source identities and
independently re-audit extracted archives. If calibration fails, stop before the
comparison and report the failed gate. Do not silently revise limits or rerun.
