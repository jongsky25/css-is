# 2B natural-collection attribution

Status: diagnostic investigation, not acceptance. Product remains f700187.
The rejected pagehide candidate is not included. The 10 MiB budget is unchanged.

## Protocol and evidence

Pinned Chromium 156.0.8078.47, original 1c964dc and unchanged current f700187,
original/current/current/original order, one complete 30-second warm-desktop
workload per arm. Browser-wide trace begins before the first navigation. Each
of the 13 original checkpoints retains total renderer RSS, per-PID observations,
DOM counters, frame/target census, a clock marker and target-renderer native
allocation samples. No forced collection, extra cache flush, memory subtraction
or sample filtering. These instrumented, single-sample arms are not acceptance
cohorts. Browser workloads ran serially; trace parsing and symbolization waited
until all four arms completed.

The first experiment is retained in four ZIPs alongside its exact probe and
runner. All four workloads completed without application errors or reported
trace loss. All 78 fixture/product source hashes and 144 archived files were
verified. Its 52 native profiles resolve 3,255 Chromium function addresses with
matching build ID 1c5dca8527a61d07372e489142bee26af1bcaf71. Debug information reports
line-table warnings; function symbols resolve, source-line locations are not used.

The first trace includes V8 collection but no separately named C++ collection
phases. The C++ tracer uses `cppgc` and `disabled-by-default-cppgc`, rather than
the selected Blink categories. A corrected second experiment is recorded
separately; neither experiment replaces or hides the other.

## First experiment observations

| Order | Checkpoint | Total RSS delta MiB | App renderer delta MiB | Other renderers delta MiB | Documents original/current |
|---|---|---:|---:|---:|---|
| Forward | seasonal preview | +11.953 | +12.703 | −0.750 | 7 / 12 |
| Reverse | seasonal preview | +13.191 | +15.172 | −1.980 | 9 / 12 |
| Forward | navigation 10 | −20.602 | −19.980 | −0.621 | 29 / 12 |
| Reverse | navigation 10 | −21.250 | −19.129 | −2.121 | 6 / 2 |
| Forward | navigation 20 | −33.297 | −33.070 | −0.227 | 20 / 6 |
| Reverse | navigation 20 | −4.688 | −2.820 | −1.867 | 16 / 2 |

CommitLoad events map the app frame to one renderer PID in each run. Browser UI
and spare/background renderers remain included in total RSS. The changing spare
PID after the background tab is not mistaken for an app renderer restart.

The current forward run has 16 documents at navigation 1, then a natural major
collection before navigation 5 drops the count to 2. The original forward run
has no major collection over navigations 1–10 and grows to 29 documents; a later
major collection precedes its drop to 10. Counts drop in the reverse pair too.
This supports collection timing as a contributor to variability. It does not
prove a persistent application reference or establish that all RSS is collectible.

Native samples contain rendering/display-list allocations, strings, script and
inspector buffers. Samples are allocation-site estimates, not retaining paths or
complete RSS. Preview sampled totals are higher on current in both orders, while
navigation-20 totals are close. They do not isolate a source correction.

## Corrected C++ collection experiment

All four corrected workloads also completed, with 10,636 / 4,715 / 4,169 /
7,857 C++ trace events respectively. All 25,652 events carrying an explicit
`forced` flag report false. Marking, concurrent and incremental sweeping, and
sweep finalization are present. Each raw trace and all 52 additional native
profiles are retained under [cppgc](cppgc/manifest.json), with another 78 verified
source hashes and 144 hash-verified archived files.

| Order | Checkpoint | Total RSS delta MiB | App renderer delta MiB | Documents original/current |
|---|---|---:|---:|---|
| Forward | seasonal preview | +7.629 | +7.836 | 12 / 11 |
| Reverse | seasonal preview | +2.254 | +1.562 | 11 / 12 |
| Forward | navigation 10 | +26.152 | +26.473 | 4 / 33 |
| Reverse | navigation 10 | +21.090 | +20.430 | 12 / 10 |
| Forward | navigation 20 | +26.523 | +27.121 | 24 / 12 |
| Reverse | navigation 20 | +21.723 | +21.074 | 14 / 6 |

The current forward run has 43 documents at navigation 15. Natural collection
and subsequent sweeping reduce this to 12 at navigation 20; total RSS decreases
from approximately 563.7 to 542.4 MiB, but remains above original. In the reverse
pair, current has fewer documents at navigation 20 yet higher RSS. Document
counts alone therefore cannot account for the full resident-memory difference.
The preview difference also falls below 10 MiB in this second instrumented
experiment. Neither first-experiment nor corrected-experiment numbers can replace
the existing uninstrumented gate results. Instrumentation and natural collection
timing differ; no favourable experiment is selected as acceptance.

## Result and continuation

The investigation establishes natural C++/V8 collection and identifies the app
renderer as the main source of the observed delta. It does **not** establish a
persistent application retaining reference or an allocation site responsible
for all excess RSS. Native samples identify allocation sites, not retaining
paths; RSS also includes allocator-resident pages and memory outside sampled
allocations. Those remain possible explanations, not demonstrated causes.

No new product correction is justified by these observations. Product remains
f700187; 2B remains blocked and full acceptance/3A are paused. The next specific
question is whether excess app-renderer RSS after natural sweep completion is
live allocation or allocator-resident capacity. A follow-up must align detailed
native allocator dumps and smaps with the same natural collection epochs,
retaining total RSS and the existing workload. Only then choose a source
correction; do not reintroduce the old audio/observer allocation loop, force GC,
subtract resident pages, or relax the budget.

Validation: eight complete instrumented workloads, 104 checkpoint native profiles,
156 verified source hashes, 288 archived files verified by round-trip hashes,
and 41 collection-analysis/accounting tests pass. Four tests guard PID/interval
mapping, duplicate clock markers, unexpected app-renderer changes and forced
collection. Snapshots and clock markers are sequential, not atomic; timestamps
establish intervals rather than exact instantaneous collection causality.
