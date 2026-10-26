# Source isolation screen

Completed all 16 full warm-desktop samples. 224 source hashes verified; 55 analysis/accounting tests pass. This is a two-sample screen, not acceptance.

| Intervention | Order | Navigation 10 RSS delta MiB | Navigation 20 RSS delta MiB | Checkpoints worsening over 10 MiB | Qualifies |
|---|---|---:|---:|---:|---|
| geometry | forward | -15.090 | -15.592 | 0 | True |
| geometry | reverse | -29.115 | -24.934 | 0 | True |
| preview | forward | -4.631 | +15.320 | 2 | False |
| preview | reverse | -11.676 | +5.090 | 0 | False |
| svg | forward | -8.262 | -14.453 | 0 | True |
| svg | reverse | -11.021 | -6.779 | 0 | True |

All deltas are intervention minus unchanged product. The same-source current repeat has no increase above 10 MiB across the 26 RSS/heap comparisons. No sample was excluded. Both geometry and original-SVG arms satisfy the predeclared screen; preview does not.

The geometry observer correction was investigated first to preserve the upgraded artwork. Disabling observers is not a final fix because resize behavior must remain correct. Share one observer across geometry targets and release it on non-persisted pagehide, preserving back/forward-cache behavior; validate real navigation and geometry first, then five-sample original/current/candidate cohorts in both orders. Source changes remain a hypothesis until that gate passes.

See [protocol](README.md), [all measurements](assessment.json), [source variants](variants), and [archive hashes](manifest.json).

## Follow-up outcome

The implemented shared-observer/discarded-page cleanup candidate cccf843 did not pass its hosted gate. Six forward RSS comparisons exceed 10 MiB; the reverse unchanged-current control is incomplete after a seasonal-preview timeout. The candidate is not promoted. The screen remains evidence of a lead, not a validated cause or fix. See the [complete candidate report](../geometry-lifecycle/REPORT.md).
