# Uninjected GC comparison: low retention with and without tracing

[Run 40609043507](https://github.com/jongsky25/css-is/actions/runs/40609043507),
[PR #523](https://github.com/jongsky25/css-is/pull/523).
Harness **8f7b7d4c7970ef09cfa3c71b2ce6b40b720ffd85**, workflow
**0ab5c339192b709427a7e10e7f2fa4df7527fcbb**. Completed 2026-10-28.

All four fixed slots complete without browser injection. Both counter-only slots
and both trace-only slots show low retention: one document/9,007 nodes at stage 6,
one document/6,008 nodes at stage 11. Thus low retention does not require a native
observer or measurement GC trace. This small comparison does **not** explain the
previous high-retention state or establish a correction. Product memory and
native/application observer qualification remain blocked.

## Results

| Slot | Measurement | Duration ms | Nodes stage 6 / stage 11 | Recorded major GC |
| --- | --- | ---: | ---: | ---: |
| 0 | counters only | 3506.747 | 9,007 / 6,008 | unobserved |
| 1 | counters + GC trace | 3614.134 | 9,007 / 6,008 | 2 |
| 2 | counters + GC trace | 3551.350 | 9,007 / 6,008 | 2 |
| 3 | counters only | 3562.790 | 9,007 / 6,008 | unobserved |

Both trace slots record natural collections finalized by task, **three marked JS
global proxies** and **756,936 bytes after collection** in each major-GC statistic.
Counter-only GC counts were not collected; they are not zero. No source-labelled
native page joins/returns are measured. This is not the original RSS acceptance
matrix, native calibration, observer cost bound or product comparison. Two slots
per factor cannot establish a causal effect, failure rate or timing improvement.

The final DOM counter in each trace slot has conservative clock bounds extending
beyond the final marker; its full trace coverage is uncertain. All other counter
bounds are covered. The raw coverage flags remain preserved; no marker padding,
midpoint clock assumption, discarded sample or unchanged rerun repairs this limit.

## Injection and workload integrity

The job explicitly drops SYS_PTRACE and runtime confirms that capability is absent.
Frida attach/spawn/injection guards record **zero attempts** in every slot. The
original runner executes control mode in all four processes, with no native
history, added Runtime subscription, new page evaluation, snapshot, dump, collection
request or workload wait. Its imported Frida client version metadata is not an
attached browser agent. No native preflight runs in this job.

Same source: lifecycle v12 runner, 12 mounts, DOM/SVG/style fixture documents,
32 receivers/group/two repetitions, 220ms waits, both DOM witnesses, heap/DOM counters
and 11 pagehide beacons. Raw document and serialized-DOM hashes, complete samples,
null results, tags, lifecycle, PID/build, source and command schedules all match.
Command-name/timing logging and common initial identity tracing remain baseline
instrumentation. Trace-only adds the 64MiB measurement trace/marker before the first
original navigation, inside its measured interval. Trace end/completion pumping
and transfer occur after the measured loop. These effects remain unqualified;
absence of failure is not proof that observation is harmless.

## Existing-environment comparison

[Retained environment comparison](environment-comparison.json) finds the same
103 downloaded apt package versions, same kernel/affinity and cgroup inventory
between application attempt 5 and this job. Pinned Python/browser/Playwright and
image are unchanged. CPU model differs: failed-job AMD EPYC 7763 versus this job's
Intel Xeon Platinum 8573C. Earlier AMD root/buffer captures also showed low retention,
so CPU model alone is not an explanation. This checks retained inventories and
package-version logs, not every runtime binary. No environment correction or
physical exclusivity is established. Resources were not reconfigured.

## Durable evidence

**32 local/cloud preflight tests pass.** All **39** result-manifest hashes verify,
every archived harness source matches the frozen commit, and independent analysis
of every raw capture/trace exactly matches cloud output. Fixtures were pinned
before capture from the independently verified native-buffer archive.

Artifact **12781893879** is retained byte-for-byte as
[contrast-v1-evidence.zip](contrast-v1-evidence.zip), SHA256
`955062f534f69936fd4b0e4daae59d3e400b6ead0d458c186ff4651e1e74b881`.
[Assessment](assessment.json), [protocol](PROTOCOL.md), fixture hashes and reviewed
workflow are committed. Setup logs outside the 39-file result manifest are preserved
under the full ZIP hash. Every slot remains retained without replacements.

## Next bounded work

Do not repeat this comparison unchanged or add another broad handle-birth trace.
The earlier failed sample is still the evidence containing extra surviving
contexts. Next audit its incremental marking, weak-reference and context-disposal
chronology against pinned engine source using the retained traces/captures. State
which root information is absent and establish a specific reproduction condition
or source-supported diagnostic change before another measurement. Do not infer a
fix from subsequent clean runs, change a GC/memory gate or substitute samples.

Fresh native qualification must still pass before the frozen lossless application
observer cost can be measured; original 2B acceptance remains outstanding. No run is
active. Product cf363bf and unpromoted candidate cd94bf3 remain unchanged. PR #523 is
reviewable and unmerged. No product fix, candidate promotion, later increment,
merge or deployment occurred.
