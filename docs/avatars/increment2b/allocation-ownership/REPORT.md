# Allocation ownership investigation — native sites resolved, retaining paths pending

The twenty archived navigation profiles contain 929 native allocation samples.
All 92 archive members verify; all 1,655 unique Chromium frame offsets resolve
against the exact ELF build ID `1c5dca8527a61d07372e489142bee26af1bcaf71`.
No new browser measurement or forced collection was run. Product f700187 remains
unchanged; **2B remains blocked**.

See [compact summary](summary.json), [complete symbolized attribution](native-attribution.json.gz),
and the unchanged raw archives in [residency evidence](../residency-attribution/REPORT.md).
These historical original/current/current/original profiles are separate from the
newer timing experiment and cannot reconstruct its divergent slot 7's heap.

## What the native stacks identify

Observed allocation sites include Blink paint/layout, SVG painting and DevTools
network response decoding (`InspectorNetworkAgent`, `NetworkResourcesData`,
`InspectorPageAgent::SegmentedBufferContent`). Inspector-network-inclusive sampling
estimates range from 0.3125 to 0.5625 MiB across the twenty profiles. This is an
observed instrumentation allocation path, not proof that it retains documents.
It remains part of total RSS; nothing is subtracted from an acceptance gate.

At navigation 20:

| Cohort | Documents | Native samples | Native sampling estimate MiB |
|---|---:|---:|---:|
| Original 0 | 6 | 63 | 2.500 |
| Current 1 | 2 | 42 | 1.844 |
| Current 2 | 14 | 33 | 1.594 |
| Original 3 | 6 | 38 | 1.625 |

These are sampled allocation stacks, not a complete heap graph, individual JS
object inventory, document-to-root retaining paths, or RSS decomposition. `size`
is sampled object size; `total` is a sampling estimate. Function attribution is
inclusive, deduplicated within each sample, and overlaps across stack frames;
never sum functions to estimate a heap. No specific app reference retaining the
extra documents is established. Fewer samples or missing document-constructor
stacks cannot establish absence of a leak.

## Exact-browser capability check: JavaScript profiling forces GC

Chromium tag `156.0.8078.47` pins V8 revision
`392e44423f46d75904da712fadea4c7d5d97967f`. The matching source files, source URLs
and SHA-256 hashes are retained under [source/manifest.json](source/manifest.json).

- `v8-heap-profiler-agent-impl.cc:579`: CDP `HeapProfiler.startSampling` always
  sets `kSamplingForceGC`; its public parameters do not disable that flag.
- `getSamplingProfile` invokes `GetAllocationProfile`. In
  `sampling-heap-profiler.cc:306`, that flag causes `CollectAllGarbage`.
  `stopSampling` also calls `getSamplingProfile` first. Merely avoiding an explicit
  `collectGarbage` request would therefore not preserve natural collection.
- `heap-snapshot-generator.cc:3872`: a normal heap snapshot calls
  `CollectAllAvailableGarbage` before collecting the graph.
- Native `Memory.getSamplingProfile` is a different path through Chromium's
  native sampling profiler (`inspector_memory_agent.cc:147–159`). The existing
  native profiles do not supply JavaScript retaining paths.

The standard JS profiling/snapshot APIs inspected here cannot deliver retaining
paths while preserving the observed natural-GC state. This is a limitation of
these available methods, not proof that all possible non-GC debugging methods
are impossible. No prohibited API was invoked on a real browser during this work.

## Concrete next action prepared, not run

The [pending forensic protocol](FORENSIC_PROTOCOL_PENDING.md) and opt-in runner
prepare four fixed original/current/current/original workloads. Each would take
one heap snapshot **after** all natural observations and the trace have been
saved, before context teardown. Before/after DOM and heap values, source identity
and explicit `intentional_forced_gc: true` separate that snapshot from natural
measurements. All failures remain retained, with no replacement slots.

The diagnostic would inspect strong retaining paths to detached documents after
forced GC. It could reveal product closures/listeners, inspector roots, or other
native references; it could also collect the transient objects and leave the
original ownership question unanswered. No resulting memory number could pass
an acceptance gate. Product fixes would still need unchanged functional and
uninstrumented memory validation.

Execution is pending an explicit exception to the handoff's “No GC/cache flushing”
rule. The runner refuses execution without its explicit opt-in; its browser test
is skipped by default. Mock tests exercise snapshot serialization and labeling
without invoking Chromium. The selected suite passes 123 tests, with that one
forensic browser test intentionally skipped. No measurement is active.
