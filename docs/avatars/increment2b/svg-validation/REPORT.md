# Exact SVG source validation

[Run 40327763515](https://github.com/jongsky25/css-is/actions/runs/40327763515)
uses source `7c9f711`. Status: measuring, not acceptance.

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
