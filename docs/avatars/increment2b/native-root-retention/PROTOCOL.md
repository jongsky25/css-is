# Native root-retention diagnostic v1

Freeze before capture. This is a separate, perturbed root diagnostic, never native
qualification, application calibration, RSS acceptance or a replacement sample.
Preserve application attempt 5 and its failed native prerequisite unchanged.

Evidence motivating this diagnostic: native attempt 5 probe 1 retains 45,063 nodes
at stage 6 and 72,120 at stage 11, with no labelled page return. Probe 2 drops to
9,007 and 6,008 respectively and returns ten labelled generations. Uninjected
control 3 has exactly the first profile; uninjected control 0 has the second. Thus
native hooks are not necessary for the retained-document profile. V8's first
natural major collection reports 11 versus 3 marked JS global proxies and
2,501,964 versus 756,936 used heap bytes. A second collection is not a universal
prerequisite: passing probe 2 already returns labelled pages during its first.
The precise retaining root is not present in the old trace.

Run one fixed control/probe/probe/control schedule, no replacement slots. Reuse
unchanged native lifecycle v12 fixture bytes, 12 mounts, 220ms waits, census,
DOM/heap counters and recorder. Add V8 --heap-snapshot-on-gc=1 and a slot-specific
--heap-snapshot-path only. This asks the exact browser to write one graph after
its FIRST natural major collection, not to trigger a collection. No CDP heap
snapshot command, force-GC API, extra wait, cache flush or product change.

Source checked against Chromium 156.0.8078.47 DEPS: V8 revision
392e44423f46d75904da712fadea4c7d5d97967f. Heap::CollectGarbage calls
WriteSnapshotToDiskAfterGC only after the normal major collection; the separate
GenerateSnapshotAfterGC path avoids CollectAllAvailableGarbage. It nevertheless
makes the V8 heap iterable/completes V8 sweeping and builds an embedder graph.
Therefore this diagnostic changes scheduling and sweep state. Its timing, pool
returns and subsequent GC counts cannot qualify the original instrument or
explain previous samples causally. Capture all four raw slots even on failures.

Retain pinned upstream source excerpts/hashes, harness commit, full logs, raw
gzipped snapshots, native captures, traces, inventory and file hashes. Missing
snapshot or unexpected flags/forced trace events is a diagnostic failure.

Offline analysis decodes schema field names and node/edge enum tables, checks all
indices and edge counts, and finds paths from the synthetic root excluding weak
and shortcut edges. Shortcut edges are presentation shortcuts, not retaining-root
evidence. Report document/native-context/window nodes, root category, path and
unreachable counts; retain raw graphs for review. A graph path is descriptive,
not exclusive ownership, attributed bytes or proof that the same root existed
in a previous run. No sampling reduction or gate waiver follows.
