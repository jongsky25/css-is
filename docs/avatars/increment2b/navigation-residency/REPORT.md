# Per-navigation allocator capture — partial evidence, no product fix

**Overall status: inconclusive. No 2B acceptance or product change.** The fixed v2
experiment attempted all eight slots from `bbcba53`: original/current/current/
original, then current/original/original/current. Seven workloads and traces pass;
slot 4 (current) reports trace data loss and remains invalid. It was not replaced.
All 164 source/probe hashes and 67 cohort files verify. Seven intact slots provide
140 uniquely bounded app-renderer allocator dumps and continuous status samples.

## Instrumentation failure history

V1 (`cd71d3a`) traced the whole workload. Its first two slots completed their
navigation captures but reported trace loss; it was stopped during slot 2.
Slots 3–7 were not run. This was an explicit deviation from the initial schedule
because the instrument was invalid, not an RSS-based stopping decision. The
partial files, failed logs, harness and abort are preserved in `invalid-v1.zip`
and its manifest. No v1 sample enters v2 or acceptance.

V2 starts tracing immediately before repeated navigation, omits broad Blink and
loading categories, and preserves the trace stream before rejecting data loss.
It retains the original full workload, source refs, eight-slot order, ordinal
screenshot behavior and every scheduled result. It requests a 256MiB trace buffer;
that request does not itself establish effective capacity or prevent data loss.
The failed v2 slot's full trace and raw navigation records remain archived.

The initial auditor stopped at invalid slot 4. Its result is preserved. The final
auditor verifies every slot's identity, retains slot 4 explicitly as invalid, and
continues auditing later slots. Overall status remains inconclusive; the two
comparison pairs involving slot 4 are explicitly unavailable. No missing slot is
filled using another observation. Thirty-eight focused tests pass.

## Findings and measurement costs

Across seven intact slots, there are 249 successive sampled RSS drops of at least
5MiB, the predeclared descriptive threshold. Seventy-seven overlap marked dump
intervals. Of 172 outside those intervals, 66 overlap traced GC-category events.
Outside a marked request interval does NOT rule out delayed dump effects, and
GC-category overlap is not proof of causation or completion of all sweeping.
All drops and their nearest allocator brackets are retained, not just examples.

| Slot / source | Dumps | Median dump ms | Median post-minus-pre RSS MiB | Navigation-20 Blink heap size / allocated objects MiB |
| --- | ---: | ---: | ---: | ---: |
| 0 original | 20 | 348.9 | +7.451 | 33.125 / 13.310 |
| 1 current | 20 | 361.9 | +8.135 | 38.000 / 9.813 |
| 2 current | 20 | 347.7 | +9.256 | 37.375 / 13.378 |
| 3 original | 20 | 353.1 | +8.771 | 36.875 / 13.684 |
| 4 current | invalid | — | — | — |
| 5 original | 20 | 388.2 | +7.619 | 31.500 / 9.846 |
| 6 original | 20 | 394.8 | +5.834 | 50.625 / 13.955 |
| 7 current | 20 | 389.1 | +8.346 | 52.875 / 6.709 |

Post-dump shared-memory RSS typically rises 6.35–8.20MiB (per-slot medians). The
largest dump interval is 3.105 seconds. Actual status polling gaps reach 1.184
seconds despite the requested 100ms period; timestamps and clock-request bounds
are preserved. This probe substantially changes timing and memory residency.
Its RSS changes must not be interpreted as production savings or acceptance data.

For example, current slot 7 has a sampled -25.723MiB RSS step outside a marked
dump interval, with CppGC sweeping events overlapping its uncertainty window.
Only -6.840MiB is anonymous RSS; -18.883MiB is shared-memory RSS. Bracketing dumps
at navigation 5/6 show Blink allocated-object size falling 46.142→6.757MiB while
reported heap size stays roughly 52.5–52.875MiB. Malloc, V8 and partition values
also change and overlap; they cannot be summed to explain RSS. This demonstrates
collection with retained heap size, not the owner of the earlier anonymous drop.

The largest anonymous step in any intact slot is -32.426MiB, on original code.
Current's largest is -28.129MiB. The previous uninstrumented current sample's
roughly -52MiB anonymous release was not reproduced. These are distinct runs;
none reconstructs that prior event. All eight exported traces contain process
totals, allocator attributes and allocator graphs, but no process memory-map
entries (`trace-structure.json`). They do not associate resident anonymous pages
with an exact allocator or application reference.

## Disposition

The evidence supports natural collection/reclamation and retained native heap
capacity in BOTH sources. It does not establish an avatar-specific leak, identify
a corrective product component, or provide a complete valid source comparison.
Descriptive navigation-20 app-RSS deltas are +11.047/+1.586MiB for the first block's
source pairs and -1.414MiB for the remaining valid second-block source pair; the
other pair is unavailable. No source-effect classification or acceptance follows.

Do not ship forced GC, allocator subtraction, the visual fixture's paint hint,
or another unvalidated cleanup as a fix. Before another attribution experiment,
the probe needs less observer overhead and bounded trace segments, with verified
trace integrity. Any new schedule must preserve this failed/partial experiment;
no replacement runs were launched here. Product remains f700187, all 2B gates
remain unchanged, later increments remain paused, and no measurement is active.

## Evidence

- `evidence-v2.zip` and `manifest-v2.json`: all raw traces, navigation snapshots,
  status polls, workload outputs, frozen plan and fixtures, including slot 4.
- `assessment.json.gz`: complete audit, every valid dump, raw allocator attributes,
  all qualifying sampled drops and all eight comparison-pair dispositions.
- `drop-brackets.json.gz`: every qualifying drop with adjacent allocator observations;
  these intervals are not atomic before/after heap snapshots.
- `summary.json`, `trace-structure.json`, `archive-audit.json`: compact findings,
  memory-map availability and independent extracted-archive verification.
- `initial-audit.json.gz`, `invalid-v1.*`, `tests*.txt`: failure and repair history.
