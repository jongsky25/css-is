# Native residency diagnostic — implemented and validated

Product remains f700187. **2B is still blocked; this is not an accepted product fix.**

The combined probe, isolated counterbalanced runner, and analyzer are implemented. Four complete workloads retain 52 matched detailed allocator dumps, natural C++/V8 collection events, native samples and RSS before/after each dump. All 48 focused analysis/accounting tests pass; 78 source hashes and all 92 archived files were verified. The compact event archives reproduce all four summaries exactly. See [usage](README.md), [manifest](manifest.json), [full summary](residency-summary.json) and [test output](tests.txt).

## Diagnostic RSS observations

Current minus original, MiB; both orders retain every checkpoint. These single-sample instrumented differences do not replace or pass the uninstrumented gate.

| Checkpoint | Forward | Reverse |
|---|---:|---:|
| home_idle | +0.867 | +9.688 |
| home_interaction | -4.730 | +7.391 |
| wellness_care | +0.492 | +6.973 |
| picker_growth | -3.277 | +1.406 |
| seasonal_preview | +0.375 | -4.141 |
| offscreen | +5.707 | -4.266 |
| reduced_motion | +5.148 | -3.555 |
| background | -3.930 | +2.305 |
| navigation_1 | +6.641 | +45.746 |
| navigation_5 | +7.102 | +51.520 |
| navigation_10 | +4.777 | +37.992 |
| navigation_15 | -7.098 | +10.961 |
| navigation_20 | -6.633 | +20.094 |

## Heap capacity and allocated objects

At navigation 20 the exact Blink fields show that heap size and allocated-object size are distinct. Allocated objects may include garbage awaiting collection. Neither field is interchangeable with process RSS.

| Cohort | Documents | Blink heap `size` MiB | Allocated objects `size` MiB | Total renderer RSS MiB |
|---|---:|---:|---:|---:|
| 0-original | 6 | 59.125 | 9.567 | 507.895 |
| 1-current | 2 | 54.250 | 3.311 | 501.262 |
| 2-current | 14 | 49.750 | 23.437 | 504.098 |
| 3-original | 6 | 39.500 | 9.478 | 484.004 |

The first current arm retains a 54.250 MiB Blink heap with 3.311 MiB allocated objects after natural collection. The original arms also retain substantially larger heaps than their allocated-object totals. This supports allocator capacity as part of the explanation; it does not prove that all excess RSS is unused capacity, nor identify a product reference causing a leak. The forward and reverse RSS differences disagree, and allocated-object counts differ across collection epochs. A repeatable source-level cause remains unestablished.

## Validation and limits

The first analyzer attempt deliberately rejected duplicate PID/GUID entries. Inspection showed disjoint fragments of one dump; these are now joined only with matching timestamp/identity and disjoint allocator keys. A second validation exposed independently renumbered trace IDs: CDP request GUIDs cannot be equated with exported trace IDs. The final analyzer requires a unique app-renderer dump in each checkpoint clock interval, retaining both identifiers. Missing or ambiguous matches, overlapping fragments, forced collection, trace loss and incomplete cohorts fail analysis. Regression tests cover the observed formats.

Full traces, raw allocator dictionaries, all native profiles, smaps/RSS observations, source metadata and runner logs are retained in four ZIPs. No forced GC, extra cache flushing, sample exclusion, allocator subtraction or budget changes. Allocator families can overlap; no totals are obtained by summing them. A preceding sweep event is not proof that the entire heap finished sweeping, and snapshots are sequential rather than atomic.

This implements the requested attribution tooling and completes its first counterbalanced validation. No speculative product patch was applied. Full 2B acceptance and subsequent increments remain paused until an attributable correction passes the unchanged gates.
