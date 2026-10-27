# Mixed getter v10 — one local pool per selector, identical sampled nodes

V9 (c78a6c5) preserves all four fixed slots. It fails probe 1's 5% observation bound
(5.8458%) and probe 2's labelled-reclamation coverage, despite native page returns
for other objects. Controls and paired elapsed gates pass; probe 2's bound 4.8510%
passes. No favourable rerun or waiver. All data and post-window calls remain.

The next supported cost correction removes duplicate DOM selection work. Each
single census evaluate creates a LOCAL Map keyed by selector. DOM now queries
3,000 divs once and 3,000 spans once, reusing those pools for the second repeat;
SVG/style query the 3,000-element pool once, reusing it for both groups/repeats.
No global/window cache or reference survives the evaluate. Fixed last/pre-last
32 selections and their order, 1,536 getter calls per probe, documents, waits and
memory/control policies remain unchanged. This is reduced observer allocation/work,
not a smaller fixture or sampling change.

Returned selector query counters must be [1,1,2,2] for DOM and [1,1,1,1] for SVG/
style, independently verified in every stage. Count/repeat/type/native null/DOM/
source/capability/overflow and query-bracket checks all stay. Unexpected counts or
wrong reuse policy fail; do not silently deduplicate old v8/v9 observations.

Because shared selection source changes, freeze before ONE new three-document
exact-type capability with unchanged 384 getter/reference observations. Every
single-query capability evaluate must report exactly one selector query. Capability
remains non-performance. Only on a pass may four NEW fixed control/probe/probe/
control slots use the same frozen source and copied capability proof.

Keep every v8/v9 through-reclamation criterion for BOTH probes: labelled returned
pages for each DOM/SVG/style mode plus natural MajorGC and sweep history inside
measurement. Keep <=5% observation bound, <=250ms pause, <=120% paired duration,
<=20% control variation, all trace/identity/counter/lifecycle gates, fixed twelve
original document bytes and 220ms wait. Preserve every prior failure and new
sample, without GC, dump/snapshot, cache/policy/permission change, more dwell or
work, heavy concurrent analysis, replacement, memory subtraction or budget waiver.
Only synthetic instrument readiness for separate application calibration can pass;
no application comparison, product fix, 2B acceptance, later increment or deployment.
