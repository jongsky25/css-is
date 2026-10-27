# Avatar upgrade: new-chat handoff

Last updated: **2026-10-27 UTC**. Repository: `jongsky25/css-is`.

## Current blocking correction

The 2B acceptance in `f46d7af` was withdrawn: the comparison/audit omitted
memory budgets for offscreen, reduced-motion, background and repeated navigation.
Final run 40263865865 warm-desktop RSS deltas are +11.335938, +11.097656 and
+18.835938 MiB for the three omitted scenarios (10 MiB limit). Renderer counts
match. Prior targeted candidate evidence also contains unreported reverse-order
background +26.171875 MiB and seasonal-preview +12.710938 MiB. No memory waiver.
Read the corrected `docs/avatars/increment2b/REPORT.md` before other instructions.
Checker correction `a3717e8` enforces all eight scenarios plus five navigation
checkpoints: 104 memory comparisons, eleven RSS failures, no invalid cohorts.
All 27 focused checker tests pass. Recompute with `memory_audit.py`; the complete
numeric/visual archive and corrected assessments are under `final-verification/`.
`native-memory-breakdown.json` records retained smaps/DOM/heap comparisons without
rerunning workloads. Native private and shared measurements differ; a cause or
product fix has not been established. Do not equate low JS heap with an RSS pass.

3A artwork/correction is preserved on `codex/avatar-3a` (product `cb2220f`).
The preserved 3A branch is `9abc5ec` after receiving the complete memory checker.
The source run 40280615190 was cancelled by pause commit `2b6d154` after the
2B prerequisite failure was discovered. Do not restart/accept 3A until 2B is fixed.
The prepared audit branch `codex/avatar-3a-artifact-audit` is explicitly paused at `ade949e`; do not
trigger it as an acceptance audit of the cancelled cohort. No later increments,
merge to main or deployment occurred. The historical handoff below is superseded by this
correction wherever it suggests CI success establishes complete memory acceptance.

## Native type inventory recovered — pooled capacity has no current type owner

[Latest report](avatars/increment2b/native-type-ownership/REPORT.md) recovers the
raw dumps' blink_objects type inventory omitted by earlier family summaries.
All eight page/global type counts/bytes reconcile exactly to heap object totals;
82 archive members and frozen comparison re-audit verify; 33 tests pass. No new
browser measurements or product changes. Slot 4 minus 7 endpoint: +32.625MiB
Blink heap size, including +23.625MiB pooled capacity; allocated objects +9.131MiB,
SVG-name subset +1.243MiB. Layout, computed styles, text and CSS dominate individual
increases, alongside 11 versus 5 HTML documents. Type names are not app owners.

Pinned source confirms detailed statistics finish pending native sweeping before
counting; determinism:none does NOT preserve the unswept state. Pooled pages have
no current object type to enumerate. DOM.getDetachedDomNodes also forces GC and
was NOT invoked. Do not use either as a natural-state retaining-path shortcut.
The next missing evidence is page/source-linked allocation history before pages
enter the pool, with coverage demonstrated on a controlled fixture first. No new
probe is launched. Existing 10 source and 16 control RSS failures stand; 2B/later
remain blocked. Earlier claims that raw dumps lack type inventories are superseded.

## Offline reader-trace analysis — native sweeping overlaps snapshots

[Latest analysis](avatars/increment2b/reader-retention/REPORT.md) independently
re-audits the 82-member comparison archive and analyzes all eight slots without
new browser measurements. Thirty focused tests pass. At the largest same-source
gap (slot 4, navigation 15), MajorGC occurs inside the snapshot bracket and native
sweeping continues at least 57.313ms beyond its upper bound. Snapshot components
are sequential, so low JS heap and high document/RSS counts are not an atomic
state. Eleven of twelve >=5MiB anonymous drops overlap native sweeping. Trace gaps
and six boundary-straddling checkpoint envelopes remain explicit, not excluded.

Endpoint Blink heap: slots 4/7 committed 85.375/52.750MiB, allocated objects
20.517/11.386MiB, pooled 40.875/17.250MiB. These are not additive RSS or nav-15
allocations. Natural cleanup and retained capacity are supported; avatar reference
ownership is still not established. No speculative product cleanup or acceptance
rerun is justified. Next evidence must identify DOM/style/SVG native allocation
ownership in the transient state; per-component snapshot timing must distinguish
the exposed ordering ambiguity. Prior native samples/post-GC snapshots did not
answer this; do not repeat them unchanged. Existing memory failures stand, no
active process, 2B and all later increments remain blocked.

## Reader candidate tested — calibration passes, memory still blocks 2B

[Latest report](avatars/increment2b/sqlite-reader/REPORT.md): candidate `cf363bf`
adds one thread-owned, read-only connection for session/appearance callbacks;
writes stay fresh, no result caching, cleanup/revocation/shutdown tested. 220 distinct
tests pass across checks (one separate opt-in test skipped). Harness `586f81c` runs
four fixed calibration slots and then eight fixed original/candidate comparisons.
All workloads/trace/overhead checks pass; 336 source/probe hashes and 110 files
verify; both extracted archives re-audit identically. All failures preserved.

Calibration controls differ only 0.169%, but the memory screen FAILS: 10/52 source
RSS checks and 16/52 same-source RSS controls exceed 10MiB. All 104 heap checks
pass; renderer counts match. Largest source increase +62.137MiB, largest repeat
swing 60.488MiB. At the latter checkpoint ~59.809MiB is anonymous renderer memory,
with identical live node counts but differing retained-document/native Blink heaps.
This does not prove a leak or avatar ownership; source effects remain confounded
by unstable memory controls. Backend reuse is NOT a validated 2B fix.

Next: analyze already captured document/native-heap reclamation in the qualified
comparison traces before selecting a browser allocation change. No unchanged
rerun, waiver, 3A or deployment. No active measurements. Candidate code is on this
verification branch only; original avatar product f700187 remains the pre-candidate
reference. Earlier sections below are historical and superseded where they say
connection reuse is not implemented or a new comparison has not run.

## CPU profiles complete — repeated SQLite setup is the next concrete candidate

[Latest report](avatars/increment2b/navigation-cpu-v2/REPORT.md): fixed four-slot
current control/profile/profile/control from `bcbf0b4` completes with 124 verified
source/probe hashes, 32 files, all six traces intact and V8 coverage at all 20
navigations in both profiles. Extracted archive audit matches; 83 tests pass.
V1 partial V8 coverage and all audit repairs remain preserved. Product unchanged.

Both profiles show 240 storage.connect calls and 960 setup PRAGMAs; setup consumes
1.23–1.40s CPU, about 89% of SQLite execute CPU. A separate fixed synthetic-schema
probe finds removing journal_mode only shifts initialization cost to synchronous.
Do not remove PRAGMAs as a fix. The concrete next candidate is reducing connection
churn with thread ownership/transaction cleanup, then behavioral tests and the
unchanged unprofiled control/memory gates. It has NOT been implemented.

Browser native coverage is dominated by style/paint, without avatar-specific
ownership proof. Profiles are intrusive: +86.87%/+48.41% paired duration, individual
pauses and reader CPU exceed gates. complete_cpu_diagnostic is attribution only,
not calibration, source comparison or 2B acceptance. Historical control slowdown
and RSS failures are not causally resolved. No new measurement active; 2B/later
remain blocked. Earlier sections are historical evidence.

## Scheduler capture — control variance persists without recorded throttling

[Latest report](avatars/increment2b/navigation-residency-v6/REPORT.md): new V6
four-slot calibration (`75c6e85`) records CPU/scheduling counters in EVERY slot.
All workloads/traces are intact; 120 source/probe hashes and 30 files verify;
archive re-audit matches; 65 focused tests pass. Trace overhead and <=1% scheduler
reader CPU gates pass. Controls still vary 10.702/8.388 seconds (21.62%; limit 20%).
No source comparison was launched, and no sample was replaced or excluded.

All four navigation windows have zero recorded cgroup throttling. About 2.123s
of the controls' 2.314s difference is inside Page.goto; waits differ only 31.7ms.
The slower control has more Python and renderer CPU execution plus smaller queue
delays. Counters do not identify the functions responsible, effective CPU speed,
or the cause of historical V5's stall. Next evidence needed: bounded Python and
Chromium CPU-work/execution-rate profiling, with costs and fixed controls, before
choosing a product or environment change. No such new run is active. Product
remains f700187; 2B and later remain blocked. Historical sections below are retained.

## Lightweight capture implemented — calibration control variance blocks comparison

[Latest report](avatars/increment2b/navigation-residency-v5/REPORT.md): v3/v4/v5
completed three distinct fixed four-slot current-only calibrations, all evidence
retained. V3 fails 5% total pause gate; v4 fails 250ms individual pause gate. V5
(`08daa22`) defers trace transfer until after sealed navigation 20. Both traced
runs have intact traces, no in-workload dumps/transfers, 2.288%/2.581% explicit
pauses and 180/199ms maxima. 116 source/probe hashes and 30 files verify; extracted
archive re-audit matches. Fifty-three focused tests pass.

V5 still FAILS calibration: first/final control navigation durations are
16.757/8.474 seconds (49.43% change; 20% limit). Slowdown is concentrated in early
navigation with page long tasks and delayed status reads; no scheduler/throttling
history exists to establish cause. Do not discard that control or rerun unchanged
for favorable data. No eight-slot comparison was launched. Next attribution gap:
timestamped scheduler/CPU-throttling evidence for the control stall, under a new
frozen diagnostic. Product remains f700187; no waiver, 2B acceptance, later increment
or active measurement. Historical v2 capture below remains preserved.

## Targeted navigation allocator capture — partial, no fix

[Capture report](avatars/increment2b/navigation-residency/REPORT.md): v1 aborted
on trace loss (two failed slots, third interrupted; all partial files retained).
Corrected navigation-only v2 ran all eight slots from `bbcba53`; seven pass, slot
4 current has trace loss and is not replaced. Audit verifies 164 source/probe
hashes and 67 files; 140 bounded dumps are valid, overall status inconclusive.
Thirty-eight focused tests pass. Every scheduled slot and pair disposition stays
visible; source comparisons involving slot 4 remain unavailable.

Dump instrumentation is material: median intervals 349–395ms, median post-dump
RSS increases 5.8–9.3MiB, mostly shared-memory RSS. Natural GC/sweeping overlaps
some sampled drops, but the prior 52MiB anonymous release was not reproduced.
Blink object allocations fall while reported heap size remains high in both
sources; no exact allocator/page or app owner is established. Full dumps have no
process memory-map entries. Raw traces and all failures are archived/re-audited.
No product correction, waiver, source-effect claim or acceptance. A future probe
needs lower overhead/bounded trace segments before another fixed schedule; no
replacement run is active. Primary product remains f700187; 2B/later stay blocked.

## Offline residency review — unchanged-code swing localized

[Per-renderer review](avatars/increment2b/shared-stylesheet/memory-screen/REPORT.md)
verifies all 25 archived screen members and analyzes eight samples/40 navigation
observations without new browser runs. The -57.037109 MiB current-repeat RSS swing
at navigation 20 is dominated by -53.556641 MiB anonymous RSS in one stable dominant
renderer; other renderers change only +1.251953 MiB, JS heap -0.426353 MiB. No swap
or renderer replacement. The unusually low sample has a 51.605469 MiB renderer
RSS drop from navigation 15 to 20, LCP 696 ms and 555 ms of long tasks at navigation
20. This is correlation, not proof of a particular GC/allocator event or app owner.
Seventeen focused tests pass; all 40 prior navigation metric deltas match. Details
and limits are in residency-review.json and residency-review-verification.json.
The next attribution gap is which native allocator/pages were released during
that interval; historical captures cannot reconstruct it. No candidate patch,
new measurement, waiver or acceptance. Product unchanged; 2B remains blocked.

## Shared stylesheet follow-up — visual resolved, memory screen failed

Candidate `6960562` remains isolated on `codex/avatar-shared-stylesheet`; primary
product stays f700187. [Visual diagnosis](avatars/increment2b/shared-stylesheet/visual-resolution/REPORT.md)
finds identical DOM/selected styles/geometry despite shared-layer pixel variation.
Fixture-only paint isolation and avoiding Playwright caret mutations yield all
30 sheets (2,880 cells) pixel/state identical. Forty focused tests and one dedicated
browser regression pass. No production paint hint or screenshot change.

[Fixed memory screen](avatars/increment2b/shared-stylesheet/memory-screen/REPORT.md)
completed all eight workloads from `b521760`, no replacements. Audit/re-audit verify
114 source hashes, 20 files and 104 direct arithmetic comparisons. Forward RSS
improves, but reverse navigation 20 worsens 12.863281 MiB (>10 MiB). Both controls
fail absolute stability (current repeat navigation 20: -57.037109 MiB).
Status screen_failed, not qualified for larger validation; no promotion or new
memory acceptance. All raw evidence is archived. No measurement active. Next use
archived repeat controls to understand the late-navigation RSS variation; do not
rerun the unchanged candidate for favorable data. 2B and all later gates remain.

## Authorized forensic captures complete — transient documents gone before snapshot

The user explicitly approved the four-slot post-workload snapshot exception.
All four original/current/current/original workloads completed from `6568ac8`;
no exclusions, replacements or additional browser runs. Read
[the forensic report](avatars/increment2b/retaining-paths/REPORT.md).

Current slot 2 had 43 documents at navigation 20, falling to 2 BEFORE the forced-GC
snapshot call. All four graphs show the active HTML document and an isolated
SVG-image XML document, plus a JS Document prototype object. No native document
candidate is explicitly detached; XML detachedness is unknown. These graphs do
not capture the earlier high-document state or establish an app retaining owner.
The forced-GC JS heap reduction is forensic only and cannot enter acceptance.

The first audit caught a sealed-row rewrite in final original slot 3: one late
telemetry response was appended after capture. The exact pre-snapshot bytes were
recovered against their stored SHA-256; all memory/other fields are identical.
Raw artifact and initial failure remain unchanged. The explicit recovery audit
and extraction re-audit agree: 86 source/probe hashes, 40 files, 80 natural timing
observations, four graphs verified. Future adapter v2 freezes nested row data;
139 selected tests pass and four real forensic browser workloads passed. No rerun.

The approval was for this isolated experiment; it does not waive natural-GC or
acceptance gates. Next focus transient allocation pressure/native capacity; no
persistent extra-document owner is established. Product f700187 unchanged, 2B
and later increments blocked, no measurement active. Older pending status below
is historical and superseded by this completed experiment.

## Allocation ownership analysis complete — forensic capture prepared, not run

Read [the ownership report](avatars/increment2b/allocation-ownership/REPORT.md).
All twenty archived navigation native profiles are symbolized: 929 samples,
1,655 resolved Chromium offsets, 92 archive members verified. Paint/layout and
DevTools network-buffer allocation sites are visible, but no document retaining
paths or specific app owner are established. No new browser workload was run.

Exact Chromium 156/V8 source inspection shows CDP JavaScript sampling profiles
force GC when read, and heap snapshots force GC before graph capture. Source
files and hashes are retained. Do not silently use these APIs as natural probes.
A four-slot post-workload heap-snapshot runner and
[pending protocol](avatars/increment2b/allocation-ownership/FORENSIC_PROTOCOL_PENDING.md)
are prepared, NOT authorized or executed. They require an explicit exception to
“No GC/cache flushing”; any snapshot is forensic only and cannot enter acceptance.
The default guard is tested. 123 selected tests pass, one forensic browser test is
intentionally skipped. Product unchanged, 2B/later increments blocked, no active run.

## Per-navigation paired timing experiment complete — no source fix

Read [the eight-slot report](avatars/increment2b/navigation-timing/REPORT.md).
Frozen source `1d03efd` ran all original/current/current/original then reverse
slots without exclusions. All 160 observations, 164 source/probe hashes and 60
files verify; archive re-audit matches and 112 analysis/accounting tests pass.
There are 44/80 phase-matched source comparisons, with inconsistent source deltas.
All four same-source controls have absolute baseline memory differences above
10 MiB (nine RSS, one JS heap); maximum RSS variation is 29.441 MiB.

Current repeats 4 and 7 differ by 31 documents and ~6.18 MiB JS heap at seven
matching-phase observations after recorded V8 collection and C++ sweep activity.
V8 GC age does not align document state or certify whole Blink sweep completion.
The post-hoc event extraction retains all eight cohorts separately; no frozen
criteria changed. No retaining paths are captured, so ownership is unresolved.
Next identify retained document/JS allocations/references versus delayed whole-heap
reclamation; do not rerun unchanged timing or acceptance for a favorable result.
Median probe latency 5.539 ms, maximum 285.790 ms; tracing/file-write overhead is
unmeasured. Product remains f700187, all gates intact, no active measurement.
2B and subsequent increments remain blocked. Raw archive and checks are committed.

## Late-navigation timing analysis complete

The archived four-cohort residency evidence has now been aligned by completed
MajorGC event end times. Read [the timing report](avatars/increment2b/navigation-collection/REPORT.md).
All four archive identities and 92 members verified; sixteen analysis tests pass.
Both sources reclaim documents while retaining Blink heap capacity. Five of twenty
navigation checkpoints change document counts between initial and post-dump
snapshots; dump delays of 330–763 ms prevent treating these as atomic states.
This historical instrumented evidence does not establish the cause of the newer
paired RSS signal. No product change or new measurement was made. Next use a
predeclared lightweight per-navigation timing diagnostic with paired controls;
keep detailed dumps separate, and preserve all acceptance gates. 2B stays blocked.

## Paired variance experiment complete — late-navigation target, unstable controls

[Run 40335305139](https://github.com/jongsky25/css-is/actions/runs/40335305139)
completed all 20 slots with no exclusions. Read the
[paired result](avatars/increment2b/paired-variance/REPORT.md) and its frozen protocol.
The independent audit verifies 390 source hashes, matches the producer, and raw
recomputation confirms 520 pair differences plus 52 paired/aggregate median pairs.
The screenshot ordinal adapter produced exactly four profile captures as planned.

Nine RSS checkpoint/control sets and one JS-heap set fail stability: 15 same-source
metric differences exceed 10 MiB in absolute value, with RSS swings up to 15.348
MiB and heap swings up to 11.827 MiB. Both original and current have RSS control
failures. No source effect qualifies under the declared stable-control criterion.
Nevertheless current RSS exceeds original in every source pair at navigation
10,15,20, with paired median increases of roughly 20–30 MiB in both orders. Treat
this as an attribution target, not a qualified fix or proof no source effect exists.

Next investigate natural allocation/collection timing in that late-navigation
region, distinguishing transient document accumulation from retained native heap
capacity. Snapshot document counts differ, but do not prove a leak or identify
an owner. Preserve all budgets and historical failures; no forced GC or RSS
subtraction. The fresh browser/database and block ordering changed together, so
this diagnosis cannot replace acceptance or identify either as the cause.
The earlier cohorts already used distinct measured renderer PIDs across samples.

All 76 selected accounting tests pass. Raw ZIP, identities, logs and both audits
are retained under `paired-variance/hosted/`. The workflow is paused; no measurement
run is active. Product remains f700187; 2B and later increments remain blocked.

## Both exact source interventions failed five-sample validation

All 40 samples completed with no exclusions across
[observer run 40323560666](https://github.com/jongsky25/css-is/actions/runs/40323560666)
and [SVG run 40327763515](https://github.com/jongsky25/css-is/actions/runs/40327763515).
Each independent audit verifies 112 source hashes and agrees with its producer on
all 78 comparisons. Observer removal fails six reverse-order RSS gates (maximum
+25.554688 MiB); original SVG fails two forward-order RSS gates (maximum
+13.101562 MiB). The SVG experiment's unchanged-current repeat itself fails
navigation 20 RSS at +11.894531 MiB. No JS heap failures; no budget waiver.

Read [observer results](avatars/increment2b/observer-validation/REPORT.md) and
[SVG results / next prerequisite](avatars/increment2b/svg-validation/REPORT.md).
The two-sample leads did not replicate in both orders. Do not promote either
intervention, subdivide a supposed confirmed observer/SVG cause, or rerun either
unchanged for a favourable sample. Raw ZIPs, source logs, identities and both audits
are retained in each report's `hosted/` folder. Both workflows are paused. No
measurement run is active. Product remains f700187; 2B and later increments remain
blocked. Before another product edit, establish a repeatable source effect with
predeclared same-source negative controls and paired ordering, without changing
budgets or the workload. Do not claim the current evidence identifies a fix.

A container-only resize test passes current and fails observer removal by 150 px;
it is now included in the full functional gate (nine browser checks). Separately,
preview-loading correction `794c796` on `codex/avatar-preview-loading` passes 24
functional checks; two new regressions fail on unchanged code. It remains a
separate candidate, not a memory fix or proof of the historical timeout's cause.

## Latest source screen and geometry candidate — not promoted

Read [source isolation](avatars/increment2b/source-isolation/REPORT.md) and
[the final geometry report](avatars/increment2b/geometry-lifecycle/REPORT.md).
All 16 local screening samples and both orders completed; geometry-observer
removal and original SVG qualified as leads, preview wrapper restoration did not.
Candidate cccf843 shares observation and disconnects it on discarded navigation.
Nine browser checks and 44 accounting checks pass, with artwork unchanged.

Hosted run 40315985656 did not pass. Its complete forward candidate/original pair
fails six RSS budgets, reaching +49.984 MiB against 10 MiB. The reverse candidate
pair passes, but the reverse unchanged-current control timed out at the seasonal
preview and completed only two samples. The overall independent audit is
inconclusive: 106 source hashes and 156 valid comparisons, one invalid cohort.
All 27 completed samples and the failure log are retained. No replacement samples.

Candidate branch `codex/avatar-2b-geometry-lifecycle` preserves the experiment and
is paused. The primary verification branch retains f700187 product plus evidence.
Full acceptance, 3A and later increments remain paused. Before another product
correction, validate the exact isolated observer/SVG intervention with five
samples in both orders; the two-sample screen alone was insufficient. Investigate
the current-control preview timeout separately. Do not promote the geometry
candidate, roll back the artwork, waive budgets, or rerun for a favourable sample.

## Native residency implementation — 2026-10-26

The combined collection/allocator probe and isolated runner are implemented and
validated across four original/current/current/original workloads. Read
[the residency report](avatars/increment2b/residency-attribution/REPORT.md) and
[usage](avatars/increment2b/residency-attribution/README.md). All 52 dumps match
unambiguously by checkpoint clock intervals; exported trace IDs differ from CDP
GUIDs. Disjoint dump fragments are joined, overlapping/ambiguous data rejected.
48 analysis/accounting tests pass. Natural collection leaves heap capacity well
above allocated-object totals in both sources, but no repeatable source-level
cause or validated product correction is established. Product f700187 is unchanged;
2B and subsequent increments remain blocked. No acceptance rerun was launched.

## Natural-collection attribution follow-up — 2026-10-26

The requested next experiment is complete. Read
[the collection report](avatars/increment2b/collection-attribution/REPORT.md).
Eight full instrumented workloads retain both orders, 104 native profiles and
C++/V8 collection traces. The initial trace lacked `cppgc`; its corrected repeat
is retained separately. Collection is natural (all explicit forced flags false).
The delta is mainly in the app renderer. Documents are reclaimed, but RSS can
remain elevated with fewer documents, so a persistent app reference is not
established. No new product fix or acceptance claim. Product remains f700187;
2B/3A status is unchanged. Next attribution question: live native allocations
versus allocator-resident capacity after natural sweep completion. Preserve all
measurements and the unchanged 10 MiB total-RSS/heap gates.

## Latest 2B investigation — candidate rejected, 2026-10-26

Read [the follow-up report](avatars/increment2b/lifecycle-memory-fix/REPORT.md).
Unchanged-source run 40287821303 retained 20 full warm-desktop samples and still
fails reverse-order seasonal-preview RSS (+10.797 MiB). Candidate 509cd1a on
`codex/avatar-2b-lifecycle-candidate` cancels owned animation effects on discarded
pages. Its behavior check passes, but run 40292908517 (30 samples, three sources,
both orders) fails both candidate memory gates: eight RSS failures up to +28.738
MiB, plus a JS-heap failure +10.063 MiB. It also worsens three reverse-order RSS
checks against unchanged current. The independent audit verifies 134 source
hashes and 234 comparisons without validity errors. **Do not promote it.**

The candidate branch preserves the rejected product and has its targeted workflow
paused. The primary verification branch retains product f700187, with diagnostic
evidence and audit tools. Full acceptance was not run after the failed targeted
gate. All raw numeric evidence is preserved in the report's two hosted ZIPs and
three native-probe ZIPs. Native allocation probes are instrumented diagnostics;
early exploratory probes overlapped trace parsing and cannot establish causality.

The next experiment must correlate natural Blink/V8 collection, navigation,
renderer roles/PIDs and native allocation stacks on original/current source in
both orders. Matching native debug symbols are now verified and reproducible;
see `native-sampling/assessment.json` and `symbolize_native_memory.py`. Do not
force GC, flush additional caches, subtract browser-UI/shared memory from RSS,
or choose favourable samples. Do not rerun the rejected candidate without a new
hypothesis. 2B remains unaccepted; 3A and later increments remain paused.

## Historical start here

Read this file, repository instructions, then [the execution plan](AVATAR_VISUAL_UPGRADE_PLAN.md).
Continue the already authorized work one increment at a time. First finish the
2B artifact audit and acceptance documentation; then execute 3A, 3B, 4A, 4B, 5,
and 6 in order, validating and updating the execution ledger after each.
Do not start over, repeat successful benchmarks without cause, or waive budgets.
Do not deploy or merge without separate authorization. Do not spawn agents unless
the user explicitly requests delegation. Keep the user informed during long runs.

Suggested new-chat prompt:

> Continue the avatar upgrade in jongsky25/css-is. Read
> docs/AVATAR_UPGRADE_HANDOFF.md and docs/AVATAR_VISUAL_UPGRADE_PLAN.md.
> Finish the pending 2B artifact audit and update acceptance/ledger, then execute
> all remaining increments sequentially with their visual and performance gates.
> Preserve prior evidence and failures. Prepare reviewable changes; do not deploy.

## Current result: final CI passed; evidence audit pending

The final full CI run **40263865865** completed successfully. This was checked
directly through its job API at the timestamp above; it is no longer running.

- [Final run](https://github.com/jongsky25/css-is/actions/runs/40263865865)
- Job: `121381866232`, conclusion `success`.
- Source: `e909de12c42fe8fe99ce58d922bbef71c711e574`.
- Functional/visual, focused artwork/native frame, complete original/current
  runtime, and full original/current application matrix: **all passed**.
- Evidence upload and job cleanup: also passed.
- Source artifact: `avatar-2b-complete`, ID **12629865325**, 167,820,720 bytes.
- SHA-256: `b3bcfbf6146afdf38e4ab7f1ee872ac77c4ad063d2cb0fbcf2f5c36a70bee1f4`.
- Source artifact expires **2026-11-02 05:23:02 UTC**. Preserve it promptly through
  the prepared audit workflow, which retains full evidence for 30 days.

**Do not equate this CI success with a completed manual evidence audit.** Raw
results still need checking and the final report/assessment/ledger need updating.
Their older “running” and “pending final verification” descriptions are stale.
In particular, the root assessment mixes historical Chromium 154 measurements
with later candidates; preserve historical records, then rewrite its current
status clearly rather than treating those old numbers as this run's results.

## Repository and portable state

- Main checkout: `/workspace/css-is`, local branch `work`.
- Product fix: `f700187553bd555dd3a9b638d5aa8e5fb59f3142`.
- Final harness source: `e909de12c42fe8fe99ce58d922bbef71c711e574`.
- Before this handoff, local HEAD was `46a8994b5d497d9ceb91613dbeba57c89f0217ca`;
  latest remote verification branch push was `7cacf19`.
- Remote working branch: `codex/avatar-2b-verification`.
- Audit checkout: `/workspace/avatar-2b-artifact-audit`, branch
  `codex/avatar-2b-artifact-audit`, HEAD
  `679eb18dd70d2e0da6a1b46a480d9a680b17932a`.
- Audit checkout has two intentional uncommitted files: its workflow and
  `scripts/avatar_baseline/package_review.py`. They target the final run and add
  a 30-day upload of the complete raw evidence.
- Their exact portable diff is saved in
  [final-artifact-audit.patch](avatars/increment2b/handoff/final-artifact-audit.patch).
  If the workspace is lost, fetch the audit branch at the stated base and apply
  this patch. If the edits already exist, do not apply it twice.
- Ignored local checkpoint `avatar-verification/SESSION_STATE.json` is older than
  this handoff. It still says the matrix is running; this document supersedes it.
- No local benchmark process needs resuming. The final remote run is completed.

## Finish 2B: exact next actions

1. Refresh final run status/artifact metadata and retrieve completed job logs.
   Confirm the source/artifact identity above. Do not rerun successful CI merely
   to obtain logs or a different measurement.
2. Inspect the prepared audit changes. Commit them in the audit checkout, then
   push the audit branch **from the primary checkout** (credentials previously
   worked there but failed when pushing from the audit checkout):

   ```sh
   git -C /workspace/avatar-2b-artifact-audit add .github/workflows/avatar-2b-artifact-audit.yml scripts/avatar_baseline/package_review.py
   git -C /workspace/avatar-2b-artifact-audit commit -m "test: audit final avatar 2B evidence and preserve raw traces"
   git -C /workspace/css-is push origin codex/avatar-2b-artifact-audit:refs/heads/codex/avatar-2b-artifact-audit
   ```

3. Locate the new audit run, wait for completion, and inspect its result. It runs
   `assess_complete.py`, packages all JSON/XML/text/PNG evidence with trace hashes,
   and uploads `avatar-2b-reviewed-evidence` plus
   `avatar-2b-full-reviewed-evidence`. If it fails, diagnose the actual failure.
4. Download the compact reviewed artifact through the GitHub tool, then use its
   Sediment file ID with `download_file`. Extract the ZIP and enclosed tar.gz.
   The complete source ZIP is about 168 MB and exceeds the 32 MiB download tool
   limit; the compact review archive is designed to remain below 25 MiB.
5. Audit the evidence, not merely the workflow badge:
   - Source commit, product file hashes, browser version and cohort completeness.
   - All four phase assessments, original/current controls, raw samples, and
     unchanged limits: callbacks 50 ms; frame p95 33.3 ms; memory growth 10 MiB.
   - All desktop/mobile and cold/warm memory medians; recompute deltas from raw
     data as needed. Renderer process counts must be positive and comparable.
   - 51 static PNGs, 4,896 cells, passing same-paint-mode comparison; check PNG
     hashes against `preview_sha256` and reference hashes/report.
   - No new JS errors or external requests, functional/seasonal behavior intact.
   - Manifest hashes match retained files; preserve the complete raw artifact link.
6. Save compact final evidence under
   `docs/avatars/increment2b/final-verification/`. Preserve earlier failures and
   reports before replacing current summaries.
7. Update `docs/avatars/increment2b/REPORT.md`, its `assessment.json`, and the
   status/2B row/appendix of `docs/AVATAR_VISUAL_UPGRADE_PLAN.md`. Record actual
   final metrics, source commits, run/artifact links, retention, and limitations.
   Accept 2B only if this audit supports it. **Keep `release_ready: false`**:
   existing lifecycle findings belong to increment 5 and later work is unfinished.
8. Commit/push documentation with `[skip ci]` to the verification branch to avoid
   another full benchmark. Then proceed to 3A under the plan's normal gates.

## Diagnosis and fix already completed

The former product `c2f404fa5aa58abebbe0127bbb537b5592993ce5` passed all timing
gates in full run **40247047928** but failed warm desktop picker/growth renderer
RSS: **+11,743,232 bytes (11.199 MiB)** against the 10 MiB budget.

Opposite-order diagnostic **40257027634**, source `afcbaf9`, reproduced memory
growth at **+14.51953125 and +12.62890625 MiB**. Each comparison used five full
30-second samples per arm. Private memory also increased; this was not explained
solely by shared-page noise. There was no demonstrated accumulating preview leak.
Local runtime `will-change` removal and a native allocation probe were diagnostic,
not acceptance evidence; their inconclusive results were retained.

Fix `f700187` makes noninteractive previews genuinely static:

- `templates/_avatars.html`: optional `static_preview=false` macro parameter.
  Static rendering omits motion wrappers and invisible reaction groups while
  preserving body/costume art and seasonal attachment anchors.
- `templates/me.html` and `templates/_growth.html`: request static variants;
  the picker also drops an unused sway class.
- Interactive SVG output and runtime JavaScript remain unchanged.
- Actual profile elements: 2,053 → 1,827; diagnostic DOM count: 5,086 → 4,561.
- 1,032 SVG nodes removed per 96-preview sheet. The checker’s 1,033 fixture DOM
  delta also includes one reference-only style node; do not call it 1,033 SVG nodes.

Candidate matched-memory run **40260864049** passed both opposite-order comparisons:
**+8.55078125 and +8.28515625 MiB**, with the unchanged 10 MiB limit. All samples
used 30 seconds, all 16 selections, and the same three renderer processes.

Validation already done:

- 1,734 exact normalized interactive SVG comparisons passed.
- 4,896 static cells (16 species × 6 stages × 17 outfits/months × 3 surfaces)
  were pixel-identical **under the same uncomposited paint mode**.
- Removing compositor layers changes edge antialiasing compared with the original
  composited raster. Both initial differing images and controlled comparisons are
  preserved. Do not claim the original rasterized pixels were unchanged.
- Eight browser regressions, native visibility/touch/keyboard behavior, persisted
  care for the three plants, and seasonal live refresh passed.
- Seasonal updates preserve unsaved form state and costume/accessory anchors.
- Final CI passed all 17 harness checks and all four full verification phases.

## Harness history and measurement rules

- Superseded run **40263432618** (`b1079aa`) was cancelled after finding an old
  macro/new caller API mismatch. `e909de1` fixes it by loading historical callers
  with historical macros: `_avatars.html`, `_avatars_art.html`, `_growth.html`,
  and `me.html`. Historical code is not modernized to fit the current API.
- Dedicated verification workflow uses `cancel-in-progress: true`. Do not push
  unrelated non-skip commits while relying on an active verification run.
- Browser: **Chromium 156.0.8078.47**, Debian package
  `156.0.8078.47-1~deb13u1` for Chromium and common. Earlier 154 packages became
  unavailable; all current acceptance deltas use fresh matched 156 cohorts.
- Container: `python:3.12-trixie@sha256:0d0db5b17f11b1b7d1aafa74ceadaa64ba0944b267ff6fc22008a197acd6b9ad`.
- Do not combine historical 154 failures with current 156 samples. Native throttle
  probing did not authorize subtracting scheduler pauses or rewriting timings.
- The only approved frame exception is **33 → 33.3 ms**. There is no memory or
  callback waiver. No GC/cache flushing, outlier hiding, or budget relaxation.
- Current runtime SHA-256:
  `c69e444b8d72fe84d0521d6ccabce07e9463209f5e451d96169b19aaca4191fb`.

## Evidence map

- `docs/avatars/increment2b/static-preview-fix/`: local functional/visual evidence,
  SVG equivalence, original and controlled compositing comparisons, seasonal
  checks, ~27 MB local evidence tarball, targeted hosted-memory ZIP/summary.
- `docs/avatars/increment2b/memory-diagnosis/`: reproduced original failure,
  local compositor hint tests, native allocation probe and raw diagnostic records.
- `docs/avatars/increment2b/hosted-complete/`: earlier complete run’s audited
  results; its memory failure is historical, not the final run’s result.
- `docs/avatars/increment2b/verification-repair/`: previous setup/harness history.
- Candidate memory artifact `12624908294`, SHA-256
  `aca84a2071edfbfb68edfa84b56bceda8fbe4802b95bb6bb9ae54cf76024a685`.
- Prior memory diagnosis artifact `12624200637`, SHA-256
  `ad964a49b82afca427b18ed61ba8896a444edc32ea37842791ad717422072c60`.
- Local extracted evidence (workspace-specific): `/workspace/avatar-static-memory-reviewed`,
  `/workspace/avatar-memory-reviewed`, `/workspace/avatar-hosted-review`,
  `/workspace/avatar-hosted-images`. Prefer committed evidence for portability.

## Tool and environment notes

Discover current connector tools rather than assuming their names never change.
Previously available GitHub tools were `github_fetch_workflow_run_jobs`,
`github_fetch_workflow_job_logs`, `github_fetch_workflow_run_artifacts`, and
`github_download_workflow_artifact`, prefixed `mcp__codex_apps__` through `tools`.
They take `repo_full_name: "jongsky25/css-is"` and the relevant run/job/artifact ID.
Completed job logs are available; a 404 while a job was active was not proof of a
failed run. Do not print signed artifact URLs or credentials.

**The commit-workflow-runs tool filters to PR-triggered runs.** Empty results do
not mean a push-triggered run is missing. Discover push runs through the public
Actions page, then query run/job IDs directly:

```text
https://github.com/jongsky25/css-is/actions?query=branch%3Acodex%2Favatar-2b-artifact-audit
```

Its JSON script payload contains `payload.allWorkflowRunsRoute.workflowRuns`.
Direct CLI `api.github.com` access was blocked by the environment; use the
connector/public Actions page without changing or bypassing network policy.

If local Docker is needed, clear conflicting Docker selectors and explicitly use
`--host=unix:///var/run/docker.sock`. Existing local image `avatar-ci-preflight`
has locked dependencies/Chromium 156; host venv/browser differ and are unsuitable
for mixing acceptance metrics. Read applicable environment instructions/skills.

## Remaining plan after 2B acceptance

The execution plan remains authoritative for all detailed deliverables and gates.

| Order | Work | Essential acceptance |
|---|---|---|
| 3A | Dog, rabbit, bird, turtle; six stages each | Recognizable growth, seasonal fit, mood/care checks, small and hero sheets, performance gates |
| 3B | Fish, dolphin, owl, bat; six stages each | Preserve swimmer water separation, owl tracking and characteristic motion; same visual/performance gates |
| 4A | Wardrobe catalog, rendering, persisted preferences | Compatible stable IDs, at most two items, server validation, additive storage; seasonal/personal/none precedence |
| 4B | Accessible profile customization and integration | Explicit save/cancel, no writes during preview, keyboard support, cross-surface consistency, seasonal updates and species switching |
| 5 | Expressive motion and lifecycle policy | Hidden/offscreen/reduced-motion handling for CSS and JS; cleanup, bounded timers/listeners; before/after recordings |
| 6 | Complete regression, polish and release readiness | All combinations/surfaces, integration/accessibility/performance evidence, licenses/cache/rollback/changelog; no deployment without authorization |

Increments 0, 1 and 2A are complete. Existing offscreen motion, timer/listener and
remount findings remain visible until increment 5 resolves and measures them.
Preserve growth, wellness, identity, care cooldowns, sound preferences, seasonal
administration and accessibility. No new framework, remote art dependency, paid
service or live inference. Use original authored/coherent vector art or properly
licensed pinned assets with a manifest. Review the concrete visual results after
each bounded batch; passing source inspections alone is insufficient.
