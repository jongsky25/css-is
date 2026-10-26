# Paired memory variance — complete, controls unstable

[Run 40335305139](https://github.com/jongsky25/css-is/actions/runs/40335305139)
uses source `d27cb89`. Read [the protocol frozen before measurement](PROTOCOL.md).
All 20 slots completed with valid evidence and no exclusions. The independent audit
verifies 390 source hashes and matches the producer assessment exactly. The result
is `measurement_variation`, with no repeatable increase/decrease under the
predeclared control-stability criterion. This does not establish absence of a source effect.

Twenty scheduled slots cover five counterbalanced blocks, original/current in
both orders plus same-source negative controls. Each slot uses a fresh process,
database and browser with the existing full workload. The adapter preserves the
original ordinal-dependent screenshot behavior. This deliberate session/order
change cannot replace historical acceptance evidence or separate ordering from
session reuse as individual causes. The repository workload fixture and product
files are unchanged. All 76 selected accounting tests pass, including 21 new
paired-audit tests and a complete synthetic 390-source-hash audit.

No observer/SVG intervention, preview candidate, GC forcing, extra cache flushing,
RSS subtraction, or budget waiver is applied. 2B remains blocked; later increments
remain paused. No source correction is justified until the declared controls and
repeatability conditions are evaluated from complete evidence.

## Historical control context — descriptive, outside the new sample set

Recomputing repeats from already retained data finds absolute changes above 10 MiB
even when the one-sided release-budget check passes. These are differences of
five-sample cohort medians, not new measurements or paired single-sample controls:

| Retained experiment / repeated source | RSS minimum delta MiB | RSS maximum delta MiB | Checkpoints with absolute change >10 MiB |
|---|---:|---:|---:|
| Observer / unchanged current | -15.699 | +2.156 | 2 |
| Observer / unchanged observer-disabled | +4.996 | +37.449 | 6 |
| SVG / unchanged current | -5.070 | +11.895 | 1 |
| SVG / unchanged original-SVG intervention | -10.555 | -3.332 | 1 |

All deltas are later minus earlier. No JS heap absolute repeat delta exceeds
10 MiB in these cohort-median comparisons. Full records are retained in
`historical-controls.json`. A decline is still variation, even though it is not a
release-budget regression. This descriptive analysis does not alter the protocol
or merge historical observations into the new paired sample set.

The retained renderer-PID audit covers every scenario and navigation checkpoint
in all 40 observer/SVG samples. No measured renderer PID overlaps between samples
within any of their eight cohorts (`historical-renderer-pids.json`). Thus the new
fresh-session protocol must not be characterized as eliminating demonstrated
renderer reuse: the historical renderers were already distinct. Browser-parent,
database and ordering effects remain separate possibilities, not established causes.

## Completed result

Nine RSS checkpoint/control sets and one JS-heap set fail the symmetric 10 MiB
stability requirement. Fifteen of 260 individual same-source metric differences
exceed the budget in absolute value: original has five RSS differences (maximum
13.566 MiB), current has eight RSS differences (maximum 15.348 MiB) and two JS-heap
differences (maximum 11.827 MiB). Original's JS-heap controls all remain within
10 MiB. Every recorded difference is retained; none is discarded or replaced.

| Checkpoint | Largest absolute same-source RSS delta MiB | Forward paired median current−original MiB | Reverse paired median current−original MiB | RSS controls stable |
|---|---:|---:|---:|---|
| home_idle | 6.457 | -5.082 | -0.855 | yes |
| home_interaction | 9.137 | -9.305 | -1.156 | yes |
| wellness_care | 10.988 | -8.684 | -0.449 | no |
| picker_growth | 13.566 | -6.949 | +0.516 | no |
| seasonal_preview | 9.570 | -8.094 | -1.266 | yes |
| offscreen | 10.559 | -1.301 | +1.938 | no |
| reduced_motion | 10.457 | -2.148 | +1.848 | no |
| background | 10.980 | -6.012 | +0.141 | no |
| navigation_1 | 7.812 | -4.578 | +2.539 | yes |
| navigation_5 | 12.336 | +0.926 | +3.406 | no |
| navigation_10 | 13.891 | +24.402 | +28.477 | no |
| navigation_15 | 11.379 | +20.148 | +23.309 | no |
| navigation_20 | 15.348 | +22.965 | +30.484 | no |

## Late-navigation signal and its limit

Current RSS exceeds original in **all ten source pairs at each of navigation 10,
15 and 20**. These are the same ten pairs observed at three checkpoints, not thirty
independent samples. Paired median increases are +24.402/+28.477 MiB at navigation
10, +20.148/+23.309 MiB at navigation 15, and +22.965/+30.484 MiB at navigation 20
(forward/reverse). Traditional differences of medians also exceed 10 MiB in both
orders at all three points; they remain separately recorded in the audit.

This is a consistent observed direction and a useful attribution target. It does
not qualify as a repeatable effect under the frozen protocol because current's
same-source controls fail at those checkpoints. Do not change that criterion
after seeing the data, claim no source effect exists, or blame variation solely
on the host. Original has its own control failures at earlier scenarios.

The raw document counters also differ. At navigation 20, original document counts
are 4,4,4,4,4,4,2,10,12,6, while current counts are 22,20,20,3,22,36,36,20,20,21
(in schedule order within each source). Median JS heap there is 5.833 MiB for
original and 11.086 MiB for current. At navigation 10 the medians are 6.377 and
16.384 MiB. These snapshots do not prove a persistent leak or identify an owning
component; natural collection timing and retained native capacity remain distinct
possibilities, consistent with the earlier collection/residency investigation.

## Verification and disposition

The artifact digest and ZIP CRCs verify. Independent recomputation from the raw
rows confirms all 520 source/control pair differences and 52 paired/aggregate
median pairs. Exactly slots 0,1,2,3 contain profile screenshots, matching the frozen
ordinal adapter; all later slots retain their original screenshot-free workload.
All 76 selected accounting tests passed before launch, including 21 paired-audit
tests. Full raw evidence, producer/independent assessments and source log are
preserved in `hosted/`.

No product change or memory waiver is promoted. The workflow is paused, with no
active measurement run. 2B remains blocked and 3A/later increments remain paused.
The next investigation should focus on allocation/collection timing at navigation
10,15,20: distinguish transient live-document accumulation from capacity retained
after natural collection, using the existing diagnostic tools and original/current
sources. This identifies a workload region to investigate, not a confirmed
component to edit. Do not force GC, subtract RSS, relax budgets, or rerun this
unchanged protocol hoping for favourable controls. Session structure and ordering
were changed together, so this result cannot attribute variation to either alone
or replace historical acceptance evidence.
