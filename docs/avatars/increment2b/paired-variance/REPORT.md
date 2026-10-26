# Paired memory variance — measuring

[Run 40335305139](https://github.com/jongsky25/css-is/actions/runs/40335305139)
uses source `d27cb89`. Read [the protocol frozen before measurement](PROTOCOL.md).
No measurement result or repeatable source effect has been established yet.

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
