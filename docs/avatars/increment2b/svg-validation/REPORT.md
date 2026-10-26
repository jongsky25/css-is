# Exact SVG source validation

[Run 40327763515](https://github.com/jongsky25/css-is/actions/runs/40327763515)
uses source `7c9f711`. Status: complete; SVG intervention does not qualify. All 20 samples are valid,
112 source hashes verified. Producer and independent audits agree on all cohorts
and 78 comparisons.

After the observer intervention failed its five-sample criterion in reverse order,
validate the remaining original-SVG lead from the two-sample source screen.
Order: current / SVG / SVG / current, five full 30-second warm-desktop samples
per cohort, Chromium 156.0.8078.47. No tracing, native sampling, forced GC, extra
cache clearing, or concurrent analysis on the measurement host. No replacement
samples. The same fixture and product base f700187 are used throughout.

The intervention is exactly the earlier screen: original `_avatars_art.html`
from 1c964dc with an unused `scope` argument adapter, and an empty scope assignment
in current `_avatars.html` to disable local v2 gradient emission. Current JS,
CSS, audio and static-preview policy remain unchanged. This is a diagnostic
artwork rollback, never promotable as a correction.

Predeclared criterion: at least 5 MiB RSS improvement at navigation 10 and 20 in
both orders, no RSS/heap checkpoint worsening above 10 MiB, and all five samples
plus source hashes valid in every cohort. A qualifying result would justify
isolating SVG costs while preserving the upgraded artwork, followed by full
original/current/candidate validation. No current 2B acceptance or later increments.

## Result

| Order | Navigation 10 RSS delta | Navigation 20 RSS delta | RSS checkpoints over +10 MiB | Qualifies |
|---|---:|---:|---:|---|
| Forward | -0.542969 MiB | +10.664062 MiB | 2 | No |
| Reverse | -17.148438 MiB | -9.480469 MiB | 0 | Yes |

Deltas are SVG intervention minus current, using all five samples per cohort.
Forward failures are navigation 5 +13.101562 MiB and navigation 20 +10.664062 MiB.
No JS heap gate fails. The unchanged-current repeat itself fails navigation 20 RSS
at +11.894531 MiB; navigation 10 changes by +6.050781 MiB. This same-source
variation limits causal interpretation. It does not waive the intervention's
failed criterion, invalidate otherwise complete samples, or permit replacing them.

The hosted job succeeds because measurement and auditing complete. Its own
assessment says `svg: false`; the independent audit agrees. All raw measurements,
producer/independent assessments, source log and artifact identity are in `hosted/`.

## Disposition and next prerequisite

Neither the exact observer intervention nor the exact SVG intervention survives
five-sample validation in both orders. The earlier two-sample screen is insufficient
support for either product correction. No artwork rollback, observer removal,
shared-observer candidate, or memory waiver is promoted. Product remains f700187;
2B is unaccepted, and 3A/later increments remain paused. Both completed isolation
workflows are paused; no unchanged rerun for a favourable result.

Before another product correction, establish a repeatable source effect with a
predeclared measurement-variance experiment: same-source negative controls and
paired source ordering, preserving the complete workload and unchanged RSS/heap
budgets. Distinguish live allocations from retained capacity using the existing
natural-collection evidence; no forced GC, extra cache flushing, RSS subtraction,
or discarded samples. This is the remaining investigation prerequisite, not a
validated fix or an acceptance claim. No additional measurement run is active.

The separately prepared preview-loading correction `794c796` passes 24 functional
checks, including two regressions that fail on unchanged code. It is retained on
`codex/avatar-preview-loading` and is not a memory fix. The primary full functional
gate now also requires the container-only resize regression (nine browser checks).
