# Increment 2B — acceptance withdrawn: uncovered memory failures

## Offline unchanged-source residency review

[Archived per-renderer accounting](shared-stylesheet/memory-screen/REPORT.md)
localizes the 57.04 MiB repeat swing to anonymous/private residency in one stable
renderer, not renderer replacement or JS heap alone. The lowest-memory sample
also has slower navigation and long tasks; the responsible allocator/event is
not captured. All 25 raw archive members verify, 40 prior navigation deltas match,
and 17 focused tests pass. No browser rerun, sample exclusion, patch or acceptance.

## Shared stylesheet follow-up — visual resolved, memory screen failed

[Visual diagnosis](shared-stylesheet/visual-resolution/REPORT.md) isolates shared-layer
paint variation and removes a Playwright caret-induced DOM mutation. All 30 sheets
(2,880 cells) now match pixels/state; forty focused tests and one browser regression
pass. [Eight fixed memory workloads](shared-stylesheet/memory-screen/REPORT.md)
complete with 114 source hashes/20 files verified and 104 records independently
recomputed. Reverse navigation 20 is +12.863281 MiB; both same-source controls fail
stability. No promotion or larger validation; product unchanged, 2B blocked.

## Authorized forensic snapshot experiment completed

[Four captures](retaining-paths/REPORT.md) completed. One current slot reproduced
43 documents at navigation 20, but only two remained before snapshot-induced GC.
Graphs show the active HTML page and an isolated SVG-image document; no persistent
extra-document owner is established. A late telemetry bookkeeping mutation was
recovered byte-for-byte against the pre-snapshot hash and the writer was fixed.
139 selected tests pass. Post-GC results are forensic only; 2B remains blocked.


## Allocation ownership tooling and limitation

[Native ownership analysis](allocation-ownership/REPORT.md) resolves 929 samples
across twenty archived profiles, but allocation stacks do not identify retaining
references. Exact-browser source confirms standard JS sampling/snapshot APIs force
GC. A separate post-workload forensic capture is prepared, not run; it requires
an explicit exception to the handoff's no-GC rule. No acceptance or product change.


## Per-navigation paired timing completed

[Eight fixed instrumented slots](navigation-timing/REPORT.md) completed with 160
observations and verified source identities. Same-phase source results are
inconsistent; all four same-source controls exceed an absolute 10 MiB memory
difference somewhere. Two unchanged-current slots differ by 31 documents after
observed natural GC/sweep activity, narrowing the unresolved question to document/
JS retention and whole-heap reclamation. GC age alone does not align state.
112 accounting/analysis tests pass. No product fix or acceptance; f700187 unchanged.


## Latest paired variance diagnosis

[Twenty counterbalanced slots](paired-variance/REPORT.md) completed and independently
verified (390 source hashes). Same-source controls fail stability in nine RSS
checkpoints and one JS-heap checkpoint, so no source effect qualifies under the
predeclared criterion. Current RSS is nevertheless higher in all ten source pairs
at navigation 10,15,20, with paired median increases around 20–30 MiB in both orders.
This focuses the next allocation/collection-timing investigation on late navigation;
it does not establish a component fix or waive historical failures. Product f700187
is unchanged; 2B remains blocked. The workflow is paused, with no measurement active.


## Latest follow-up — both source leads unconfirmed

Five-sample observer and SVG validation completed all 40 samples. Both independent
audits agree with their producers, verifying 224 source hashes in total. Observer
removal fails six reverse-order RSS gates (maximum +25.555 MiB); original SVG fails
two forward-order RSS gates (maximum +13.102 MiB). The SVG experiment's unchanged
current repeat also fails navigation 20 at +11.895 MiB. No correction is promoted,
and the 10 MiB gates remain unchanged. See [observer results](observer-validation/REPORT.md)
and [SVG results / next prerequisite](svg-validation/REPORT.md). 2B remains blocked;
3A and later increments remain paused. No measurement run is active.


**2B is not accepted. Release readiness remains false.** The acceptance recorded in `f46d7af` was premature: the CI comparison and my first audit checked memory for five active scenarios but omitted offscreen, reduced-motion, background and navigation measurements. Those omissions cannot waive the unchanged 10 MiB budget.

The existing final run 40263865865 already contains these failures; no benchmark was rerun or sample replaced:

| Warm desktop scenario | Original RSS median (bytes) | Current RSS median (bytes) | Increase (MiB) |
|---|---:|---:|---:|
| Offscreen | 479,694,848 | 491,581,440 | 11.335938 |
| Reduced motion | 481,587,200 | 493,223,936 | 11.097656 |
| Background probe | 613,728,256 | 633,479,168 | 18.835938 |

All five runs per arm have matching positive renderer counts (three for offscreen/reduced motion, four for the background probe). Background visibility is an automation limitation recorded in raw samples; this is the controlled background-probe RSS comparison, not a claim of physical hidden-tab behavior.

The earlier candidate's opposite-order retained memory run also contains a background RSS increase of **26.171875 MiB** and seasonal-preview increase of **12.710938 MiB** in its reverse-order pair. Its passing picker numbers alone never established all-scenario acceptance. Repeated-navigation RSS differences also exceed 10 MiB (warm desktop +32.300781 MiB at mount 20); lifecycle findings remain unresolved.

Shared-page measurements differ substantially: median summed Shared_Clean rises about 23.17 MiB, while summed Private_Dirty is slightly lower and PSS rises about 3.60 MiB. This does not prove a JavaScript retention leak, establish the root cause, or authorize subtracting shared memory from the RSS budget. An attributable, validated correction is still required.

All functional/visual, callback/frame and five-active-scenario findings remain preserved in [the incomplete audit report](REPORT-incomplete-audit.md), [its assessment](assessment-incomplete-audit.json), and [the full numeric/visual archive](final-verification/numeric-and-visual-evidence.tar.gz). Full raw traces remain in [artifact 12630379820](https://github.com/jongsky25/css-is/actions/runs/40277957839/artifacts/12630379820), retained until November 25. The green workflow/audit labels did not cover the omitted gates.

3A work is preserved on `codex/avatar-3a`, but its workflow has been paused and run 40280615190 cancelled after this prerequisite failure was discovered. No 3B, wardrobe, motion increment or release work may be accepted on this basis. No merge to main or deployment occurred.

## Complete retained-memory audit

[104 recomputed comparisons](final-verification/complete-memory-audit.json) cover eight scenarios and five navigation checkpoints, two metrics, four device/cache groups. All cohorts and renderer counts are valid; eleven RSS comparisons fail. [Corrected overall assessment](final-verification/corrected-overall-assessment.json) rejects acceptance despite the four original green phase labels.

| Configuration | Scenario | RSS median delta (MiB) |
|---|---|---:|
| False-cold | navigation_10 | 26.011719 |
| False-cold | navigation_15 | 21.824219 |
| False-cold | navigation_20 | 12.851562 |
| False-warm | offscreen | 11.335938 |
| False-warm | reduced_motion | 11.097656 |
| False-warm | background | 18.835938 |
| False-warm | navigation_1 | 20.062500 |
| False-warm | navigation_5 | 20.753906 |
| False-warm | navigation_10 | 41.777344 |
| False-warm | navigation_15 | 26.195312 |
| False-warm | navigation_20 | 32.300781 |

The corrected checker includes every scenario/navigation checkpoint and rejects missing/duplicate cohorts, zero memory and mismatched browsers/renderer counts. All 27 focused checker regressions pass. No new product optimization is claimed: the native allocation/retention cause is not established, and earlier successful active-scenario results do not override these failures.

[Native allocation breakdown](final-verification/native-memory-breakdown.json) retains per-run smaps, DOM and heap comparisons for all 52 configuration/scenario checkpoints. Warm-desktop mount 20 has higher native private-dirty memory despite lower median JS heap and fewer DOM nodes; this does not establish an accumulating JavaScript-object leak. The next diagnosis must isolate native retained allocations/page caching on the pinned runner before choosing a product correction. No forced collection, cache flushing, RSS subtraction or favourable-sample replacement is authorized by these findings.

## Lifecycle correction experiment — rejected

Candidate `509cd1a` passed its cleanup behavior checks but failed the hosted memory gate: eight RSS comparisons and one JS-heap comparison exceeded 10 MiB, reaching +28.738 MiB RSS and +10.063 MiB heap. All 234 diagnostic comparisons and 134 source hashes were independently audited. The candidate remains on `codex/avatar-2b-lifecycle-candidate`; this verification branch retains unchanged product `f700187`. Full acceptance was not started and 3A remains paused. See the [complete follow-up report](lifecycle-memory-fix/REPORT.md) for retained evidence and the next attribution experiment.

### Natural collection attribution — complete, 2B still blocked

Eight instrumented workloads in both orders establish natural C++/V8 collection and locate the dominant RSS delta in the app renderer. Documents are reclaimed but RSS can remain elevated, so no persistent application reference or validated product correction is established. Product stays f700187; full acceptance and later increments remain paused. See the [complete evidence and next attribution question](collection-attribution/REPORT.md).

### Native residency implementation — 2026-10-26

Combined native allocator/collection tooling is implemented and validated: four counterbalanced diagnostic workloads, 52 matched dumps, 48 passing analysis/accounting tests. Heap capacity remains above allocated-object totals in both sources; no repeatable source-level correction is established. Product remains f700187, 2B blocked, later increments paused. See the [implementation and findings](residency-attribution/REPORT.md).

### Source isolation and geometry candidate — 2026-10-26 — not promoted

The 16-sample counterbalanced screen identified geometry observers and original SVG as leads. A shared-observer/navigation-cleanup candidate passed nine browser checks, but its hosted gate has six complete forward RSS failures (up to +49.984 MiB) and an incomplete reverse unchanged-current cohort caused by a preview timeout. Overall audit is inconclusive; the candidate is not promoted. All 27 completed samples and the failure log remain. Product stays f700187; full acceptance and later increments remain paused. See the [final candidate report](geometry-lifecycle/REPORT.md).
