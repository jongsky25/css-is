# Navigation allocator/residency correlation — v1

Diagnostic only. No acceptance, waiver or product changes. Original 1c964dc and
current f700187, pinned Chromium 156.0.8078.47, same fixture date and full 30-second
warm-desktop workload. Eight fixed fresh process/database/browser slots:
original/current/current/original, then current/original/original/current.
The existing ordinal adapter uses run 0 for block 0 and run 1 for block 1,
preserving its screenshot difference. Complete every scheduled slot, keep all
failures, no replacements. No concurrent analysis during measurement.

At each of 20 navigations, after the existing 220ms wait: retain RSS/smaps, DOM,
JS heap and long tasks; record before marker; request a detailed allocator dump
with explicit determinism=none; record after marker; retain a separate post-dump
snapshot. Poll known renderer /proc/status at 100ms from navigation 1 observation
through navigation 20, recording read bounds, missing PIDs and actual intervals.
No native allocation sampling or HeapProfiler APIs. No forced GC or cache flush.

Trace natural V8/CppGC/Blink activity and memory-infra, using a 256MiB trace buffer.
Tracing/dumps/probes can change collection timing and costs; these numbers cannot
replace uninstrumented gates or establish user-visible performance. Dump intervals
must be distinguished from the between-dump navigation intervals. Status read and
clock request midpoint alignment includes explicit roundtrip/read uncertainty;
no claim of atomic snapshots or exact event-to-drop causation.

Audit exact source/probe and artifact identities. Require eight completed valid
slots, twenty uniquely bounded app-renderer dumps per slot, complete markers,
no trace loss, no forced collection flag. Trace IDs need not equal CDP GUIDs;
join only within the matching before/after interval and app PID. Merge disjoint
allocator fragments only; reject overlaps and ambiguity. Keep allocator attribute
names/values distinct: families overlap, and capacity/allocated bytes are not RSS.

Retain every status observation; list ALL successive app-RSS drops >=5MiB as a
predeclared descriptive threshold, with clock uncertainty, dump overlap, and GC
events. Keep baseline and all per-navigation data even when no drop reproduces.
Compare original/current and same-source repeats descriptively in both blocks;
no post-hoc source-effect classification or sample exclusion. A coincident GC
marker does not prove which allocator released memory. Preserve full traces,
raw allocator attributes, failures, archive hashes and independent re-audit.

## v2 instrumentation correction, frozen before the new schedule

V1 tracing overflowed in its first two completed slots. The attempt was stopped
while slot 2 was running; slots 3–7 did not run. This deviates from the initial
complete-schedule rule because the instrument was invalid, not because of any RSS
outcome. All partial data, failed logs and source fixtures remain in invalid-v1.zip;
none is reused as a v2 sample or accepted measurement.

V2 starts tracing after the background checkpoint, immediately before repeated
navigation, rather than during the preceding interaction/preview workload. It
uses V8, CppGC, devtools.timeline and memory-infra categories, omitting broad Blink
and loading categories. The same full workload, eight-slot order, dump schedule,
100ms sampling, and source refs remain. No forced collection. A failed completion
now preserves the trace stream/provenance before rejecting data loss. Absence of
GC events is reported as an observation, not manufactured into a collection event.
All eight v2 slots are newly scheduled; failures remain in v2 and no replacements
are permitted. If trace integrity still fails, no source-effect claim is made.
