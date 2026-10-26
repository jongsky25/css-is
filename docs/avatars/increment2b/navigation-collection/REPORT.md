# Late-navigation collection timing — archived evidence analysis

2B remains blocked. No product edit, new benchmark sample, forced collection or budget change. This post-hoc analysis uses all four historical original/current/current/original residency cohorts, separately from the newer 20-sample uninstrumented comparison. It cannot establish the cause of that comparison's RSS increase.

## Method and validation

`python -m scripts.avatar_baseline.analyze_navigation_collection docs/avatars/increment2b/residency-attribution --out docs/avatars/increment2b/navigation-collection/assessment.json`

The analyzer verifies all four ZIP identities and all 92 member hashes against the existing manifest, then reads the full traces and reconstructs the established app-renderer/dump mapping. All 52 checkpoints are processed; all 20 navigation checkpoints are retained in assessment.json. No sample is excluded. Natural collection and trace completeness checks remain enforced. Sixteen timing/collection/residency tests pass, including interval-end boundaries, renderer isolation, unsupported trace phases, and separation of snapshot-time versus dump-time GC events.

MajorGC intervals are assigned by **event end timestamp**, not start. A completed V8 MajorGC event does not certify that the whole Blink heap has finished sweeping. GC count below is since the preceding recorded checkpoint; age is time from the most recent completed event to the checkpoint marker. RSS and documents are initial snapshot observations; allocator fields come from the later dump.

## Late-navigation observations

All memory columns are MiB. Objects can include garbage awaiting collection. Heap capacity is not RSS; allocator fields are neither summed nor subtracted from RSS.

| Cohort | Navigation | Documents | Completed MajorGC | GC age (s) | Blink objects | Blink heap | Total renderer RSS |
|---|---:|---:|---:|---:|---:|---:|---:|
| 0-original | 10 | 8 | 1 | 1.888 | 13.166 | 59.125 | 502.309 |
| 0-original | 15 | 18 | 0 | 4.410 | 29.602 | 59.125 | 513.484 |
| 0-original | 20 | 6 | 2 | 1.034 | 9.567 | 59.125 | 507.895 |
| 1-current | 10 | 12 | 1 | 2.087 | 19.681 | 54.250 | 507.086 |
| 1-current | 15 | 12 | 1 | 2.024 | 19.321 | 54.250 | 506.387 |
| 1-current | 20 | 2 | 2 | 0.194 | 3.311 | 54.250 | 501.262 |
| 2-current | 10 | 12 | 1 | 2.193 | 19.702 | 49.750 | 504.059 |
| 2-current | 15 | 4 | 2 | 0.620 | 6.601 | 49.750 | 497.859 |
| 2-current | 20 | 14 | 0 | 3.186 | 23.437 | 49.750 | 504.098 |
| 3-original | 10 | 12 | 1 | 2.036 | 18.909 | 24.609 | 466.066 |
| 3-original | 15 | 22 | 0 | 4.600 | 35.501 | 39.125 | 486.898 |
| 3-original | 20 | 6 | 2 | 1.146 | 9.478 | 39.500 | 484.004 |

Both sources show reclamation. From navigation 15 to 20, original cohort 0 drops from 18 to 6 documents and original cohort 3 from 22 to 6; each interval contains two completed MajorGC events. Current cohort 1 drops from 12 to 2, also with two events. Current cohort 2 instead grows from 4 to 14 with no completed MajorGC in that interval. These different collection phases make a single checkpoint's document count a poor basis for declaring a persistent leak.

Heap capacity persists despite reclamation. Current cohort 1 ends with 3.311 MiB allocated objects inside a 54.250 MiB Blink heap. Original cohort 0 ends with 9.567 MiB inside 59.125 MiB. This behavior occurs in both sources and does not identify a source-specific owner or quantify how much process RSS is unused capacity. The historical instrumented RSS differences disagree by order, as already reported in the residency investigation.

## Newly quantified observation skew

Across the 20 navigation checkpoints, allocator dumps occur 330.5–763.2 ms after checkpoint markers; the initial snapshots precede those markers. Five initial/post-dump document counts differ: current cohort 1 navigation 5 (24→2) and 15 (12→2), current cohort 2 navigation 5 (21→2) and 10 (12→2), and original cohort 3 navigation 15 (22→2). No V8 MajorGC duration ends specifically between marker and dump in these records. This does not rule out sweeping or collection elsewhere in the sequential snapshot/profile/dump window.

Consequently, pairing the initial document count with the allocator dump as one atomic state is unjustified. The analyzer now retains both document observations, dump delay, GC completion boundaries, and post-dump RSS explicitly. The existing data demonstrates transient document accumulation and capacity retention, but cannot resolve their timing more finely or identify the owner of the newer uninstrumented source difference.

## Next bounded experiment

Before a product patch, capture lightweight timestamped DOM/heap observations and natural GC trace events at every navigation on unmodified original/current sources in both orders, with same-source controls. Keep the existing workload and budgets; place detailed allocator sampling in a separate diagnostic cohort because its sequential delays are material. Declare observation overhead and ordering in advance, retain all failures, and do not call the instrumented result acceptance. The target is whether source differences persist at comparable natural collection phases; no forced GC, waiting for a favorable phase, RSS subtraction, or unchanged acceptance rerun.

No existing observer, SVG, animation-cleanup or geometry candidate is rehabilitated by this analysis. Full acceptance and subsequent increments remain paused.
