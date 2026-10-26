# Per-navigation natural collection timing v1 — frozen before measurement

Question: do document/JS-heap differences remain in paired original/current
observations at similar naturally occurring MajorGC phases? This is descriptive
attribution, not acceptance or proof of a persistent leak/native RSS owner.

Eight fixed slots: original/current/current/original, then
current/original/original/current. Fresh pytest process, database and Chromium
156.0.8078.47 for each slot. Original 1c964dcba2fa19de1eab077b00e0e5748d742554;
current f700187553bd555dd3a9b638d5aa8e5fb59f3142. No product changes.
Run the complete warm-desktop baseline, 30-second scenarios, all selections and
20 navigations. The established sample-ordinal adapter sets ordinal 0 for block
0 and ordinal 1 for block 1, preserving first-sample-only screenshots.

Trace natural V8/CppGC events throughout the workload. Immediately after each
existing 220 ms navigation wait, bracket two CDP calls (DOM counters, heap usage)
with trace clock markers and host monotonic timestamps. Preserve existing full
snapshots at mounts 1,5,10,15,20. No new waits, forced GC, cache flushing, allocator
dumps, native sampling or RSS subtraction. Trace and polling perturb execution;
record elapsed probe latency and acknowledge tracing overhead is unmeasured.
File persistence also adds latency outside the measured probe bracket.

Retain all eight scheduled slots, every observation and failure. No replacements.
Do not analyze concurrently on the measurement host. Any failed/missing slot,
source mismatch, unmatched renderer identity, missing/duplicate markers, trace
loss, forced-GC flag or incomplete workload makes the full comparison inconclusive.
Archive source identities, adapted fixtures, raw traces, all logs and raw metrics.

Analysis uses MajorGC END times in the uniquely identified app renderer. Retain
GC age as an interval from before to after marker; flag collection overlapping
the observation window. V8 event completion does not certify Blink sweep completion.
Predeclared phase bins: [0,1), [1,3), [3,infinity) seconds since last completed
MajorGC. Unknown age, GC overlap or a bin-boundary crossing is unmatched. Match
only observations at the SAME navigation ordinal in the SAME adjacent source
pair and phase bin; never seek a later favorable sample. Report unmatched data
alongside matched data and all unconditional comparisons. Phase matching is
observational conditioning on a source-influenced variable, not causal adjustment.

Adjacent pairs are slots (0,1),(2,3),(4,5),(6,7), two in each order. Same-source
controls are (0,3),(1,2),(4,7),(5,6), two per source. Report all DOM/heap differences,
phase matches and per-slot overhead. Retain original 13-point RSS/heap metrics
and describe same-source absolute deviations above 10 MiB without altering the
acceptance gate. Eight slots do not establish the earlier five-pair stability
criterion. No repeatable-effect classification or product promotion from this run.

Next decision: if matched-phase differences persist in both orders with small
same-source differences, investigate specific allocations with a separate probe;
otherwise report timing/variance or insufficient matched coverage, without
claiming there is no source effect. Full 2B acceptance remains a separate gate.
