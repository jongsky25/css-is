# Per-navigation timing experiment — complete, no product fix established

All eight predeclared workloads completed without retries or exclusions. All 160
navigation observations, 164 source/probe hashes and 60 evidence files verify.
The archive re-audit exactly matches the first audit; separate arithmetic checks
reproduce all 160 phase assignments and 480 DOM/node/heap pair differences.
All 112 selected analysis/accounting tests pass. **2B remains blocked.**

Source/harness: `1d03efd`. Original/current products are unchanged `1c964dc` and
`f700187`. This run used the local managed workspace and Chromium 156.0.8078.47,
with a fresh browser/database per slot. No concurrent analysis ran during capture.
It is a separate instrumented diagnostic, not additional samples for the hosted
20-slot experiment or replacement acceptance evidence. See [frozen protocol](PROTOCOL.md),
[assessment](assessment.json), [archive re-audit](independent-assessment.json),
[raw ZIP](evidence.zip), [provenance](provenance.json), and [test output](tests.txt).

## Frozen phase comparison

At each of 20 navigations, DOM and heap calls are bracketed by trace markers.
Phases are under 1 second, 1–3 seconds and over 3 seconds since the END of the last
app-renderer MajorGC event. Two observations remain unclassified: slot 1 navigation
12 crosses a phase boundary; navigation 16 overlaps GC. All data remains retained.
Phase matching conditions on a source-influenced variable, uses broad age bins,
and does not establish equal Blink sweep completion or causal effects.

There are 44 phase-matched source comparisons out of 80 total; 22 of 44 comparisons
at navigation 10–20 match. These repeated observations come from eight workloads,
not 160 independent samples. Current minus original:

| Adjacent pair (original/current slot) | Order | Matched / 20 | Matched late / 11 | Late matched median document delta | Late matched median JS heap delta MiB |
|---|---|---:|---:|---:|---:|
| 0 / 1 | Forward | 12 | 5 | -2 | -0.591 |
| 3 / 2 | Reverse | 16 | 7 | +2 | +0.924 |
| 5 / 4 | Reverse | 6 | 5 | +2 | +0.863 |
| 6 / 7 | Forward | 10 | 5 | +33 | +7.058 |

The large positive document/heap difference in the last pair also appears in an
unchanged-current control. It cannot be attributed to the product difference.
Neither order provides a consistent, control-stable source result across blocks.

## Same-source variation and retained documents

All four same-source pairs have at least one absolute baseline memory difference
over 10 MiB. Across their 104 checkpoint/metric differences, nine RSS differences
and one JS-heap difference exceed that threshold. Maximum absolute RSS variation
is 29.441 MiB (original slots 5→6, navigation 5). The current slots 4→7 navigation
20 JS-heap difference is +10.061 MiB. These diagnostics do not pass or waive the
historical acceptance gates; the earlier five-pair stability criterion is not
replaced by this smaller experiment.

The current slots 4 and 7 have matching phase bins at 17 navigations. At seven
consecutive matched observations (11–17), slot 7 has **31 more documents and about
6.18 MiB more JS heap**. Slot 4 falls from 31 documents at navigation 10 to 2 at 11;
slot 7 rises from 31 to 33. At navigation 20 they have 8 versus 51 documents, but
those two observations are in different phase bins and remain unmatched.

A post-hoc inspection of all eight cohorts' navigation 10–20 events is preserved
separately in [GC follow-up](gc-followup.json). Both current slots record natural
V8 major collection and C++ atomic/concurrent sweep activity near navigation 11.
V8 `usedHeapSizeAfter` is approximately 5.25 MiB in slot 4 versus 11.04 MiB in slot
7. A concurrent sweep duration end or a space-level `Sweeping finished` event is
not proof of whole-heap sweep completion. The trace therefore does not establish
whether delayed reclamation, reachable references, or another retention mechanism
owns the extra documents. It does show that elapsed time since V8 GC alone is
insufficient to align the document/JS state. Do not label this a persistent leak
or explain all extra RSS as unused native capacity.

The follow-up is exploratory and does not alter the frozen bins, exclude a slot,
or reclassify any source/control result.

## Unconditional RSS observations

At the existing full baseline checkpoints, current minus original total renderer
RSS is lower in both first-block pairs and higher in both second-block pairs:

| Pair (original/current slot) | Navigation 10 MiB | Navigation 15 MiB | Navigation 20 MiB |
|---|---:|---:|---:|
| 0 / 1 | -12.859 | -6.371 | -16.723 |
| 3 / 2 | -19.941 | -19.020 | -17.961 |
| 5 / 4 | +50.004 | +34.375 | +24.332 |
| 6 / 7 | +32.531 | +26.297 | +32.781 |

All 13 baseline points per slot and all unconditional per-navigation DOM/heap
pair differences are retained in the assessment. This instrumented, local result
does not cancel the earlier hosted observation of higher current RSS in every
late-navigation source pair. Instrumentation, host and cohort design differ.

## Measurement overhead and limits

The median bracketed probe latency is 5.539 ms; maximum is 285.790 ms. Total
bracketed time per slot ranges from 92.122 to 654.258 ms. The maximum is retained,
not discarded. Tracing overhead and JSON persistence outside the bracket are
unmeasured, so this is not proof of negligible observer effect. No allocator dumps,
native sampling, forced GC, extra cache flush, favorable-phase waiting, memory
subtraction or product change occurred.

Next target: identify the document/JS allocations or references that remain after
observed natural collection in the divergent same-source repeat. Separate that
ownership question from whole-heap sweep completion and native capacity. The
current traces contain no retaining paths, so another unchanged phase/acceptance
rerun would not answer it. No observer/SVG/lifecycle candidate is promoted. Full
2B acceptance, 3A and later increments remain paused; no measurement is active.
