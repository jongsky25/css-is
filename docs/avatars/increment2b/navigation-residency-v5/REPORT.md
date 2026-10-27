# Lighter capture implemented; comparison blocked by calibration control variance

**2B remains blocked. No product change, source comparison or acceptance.**
V5 removes allocator dumps and extra full snapshots from measured navigation,
uses two bounded GC traces, and defers all trace transfer until after navigation
20 is sealed. The final natural allocator dump is separate and post-workload.
All historical failures remain recorded; no forced GC or sample replacement.

## Validation and fixed calibration

The probe and gates were frozen at `08daa22`. All four current-source slots ran in
control/trace/trace/control order. Audit verifies 116 source/probe hashes and 30
files. Both traced runs have all three trace segments intact (two navigation and
one endpoint); no trace loss, allocator dump or stream transfer inside measured
navigation. Sealed checkpoints exactly match workload output. The extracted raw
archive independently reproduces the complete audit. Fifty-three focused tests pass.

| Slot | Mode | Navigation ms | Explicit pause fraction | Maximum pause ms | Maximum status poll gap ms |
| --- | --- | ---: | ---: | ---: | ---: |
| 0 | control | 16756.587 | <0.001% | 0.005 | 871.582 |
| 1 | trace | 8765.435 | 2.288% | 179.996 | 152.988 |
| 2 | trace | 8642.379 | 2.581% | 199.472 | 126.243 |
| 3 | control | 8474.311 | <0.001% | 0.001 | 122.459 |

Explicit trace pauses pass the unchanged 5% total / 250ms individual limits.
Both trace/control duration ratios pass the <=1.20 upper bound. However the final
control is **49.43% faster** than the first, failing the unchanged 20% control
stability limit. Overall status is **inconclusive**, with the exact failed gate
in `calibration.json`. This is not permission to discard slot 0 or infer that
tracing improves performance. No eight-slot source comparison was launched.

## Slow-control review

All five checkpoints from all four runs are retained in `control-review.json`.
The first control reaches navigation 5 at 9497.782ms, versus 2175.147ms for the
final control. Its first page has three long tasks totaling 590ms (228/138/224ms),
LCP 628ms, and the first two checkpoint calls take about 225/229ms. The status
sampler also experiences a 304ms read and an 872ms polling gap. The final control's
maximum read is 22ms and gap 122ms. Later first-control navigations are faster.

These observations localize the slowdown to the early navigation interval; they
do not distinguish natural browser work, scheduler delay or external host load.
The slow control has no GC trace by design. No historical CPU throttling/scheduler
counters were captured, so a post-run system configuration cannot establish the
cause. Do not attribute this variation to avatars or use these instrumented
current-only runs as an original/current memory comparison.

## Retained calibration failures

- [V3](../navigation-residency-v3/REPORT.md), `abef17c`: four five-navigation trace
  windows. All traces intact, but slot 2 explicit pauses consume 5.408%, over 5%.
- [V4](../navigation-residency-v4/REPORT.md), `e46a7d9`: two ten-navigation windows.
  All traces intact, but both traced slots exceed 250ms per rotation (323/351ms).
- V5, `08daa22`: same two windows; trace transfer deferred past measurement. Both
  traced slots pass pause limits, but the unchanged controls fail duration stability.

Each revision completed its full four-slot schedule, with fresh processes,
databases and browsers. All raw evidence and failed gates are archived. No revision
reuses a sample, changes a limit, or launches a source comparison after failure.

## Remaining step

Before another comparison, establish why the control workload sometimes stalls.
The next useful evidence would be timestamped process scheduling and cgroup CPU
throttling observations spanning the navigation interval, correlated with the
existing page long tasks and status polls. That requires a newly frozen diagnostic
and calibration; it must not be an unchanged rerun seeking a favorable control.
No such new measurement is active. Product remains f700187, the original 2B memory
failures remain unresolved, and 3A/later increments remain paused.

Evidence: `calibration-evidence.zip`, `calibration-manifest.json` (all member hashes,
archive hash and identical re-audit), `calibration.json` (all checks, pair metrics,
drops and endpoint allocators), `control-review.json`, `tests*.txt`, and `PROTOCOL.md`.
