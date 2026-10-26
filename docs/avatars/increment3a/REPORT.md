# Increment 3A — artwork implemented; acceptance pending

Dog, rabbit, bird and turtle now have 24 illustrated stages with changing head/body proportions, ears, wings and shell anatomy. Existing care, identity, growth, movement and seasonal policy remain. Original authored SVG reuses the existing gradient palette and adds head/neck accessory anchors. The illustrated rendering avoids the old drop-shadow filter.

Visual evidence: [light before/after](before-after-bare-light.png), [dark](before-after-bare-dark.png), [contrast](before-after-bare-contrast.png), [motion recording](before-after-motion.webm), [51 seasonal sheets](sheets/index.json), [216 stage/mood/theme rig checks](motion-rig-check.json). Reviewed small/hero silhouettes and monthly overview. Every rig responds to its existing CSS hook, and reduced motion suppresses those animations.

Local checks: 103 unit/integration/harness tests, 17 verifier regressions after harness parameterization, and four real authenticated/persisted animal-care browser checks pass. Local Chromium 154 evidence is functional/visual only; it is not combined with Chromium 156 performance cohorts. System ffmpeg was used for the local recording.

The gallery now loads the complete historical template tree, preserving the before version's split imports. Focused/whole-runtime benchmark species are configurable, retaining the original five runs, 30-second windows, controls and 50/33.3 ms budgets. A dedicated workflow measures this batch against fresh original baselines on pinned Chromium 156.

**Performance acceptance remains pending. Do not start 3B until the raw hosted functional, focused, runtime and application-matrix evidence passes review. Release readiness remains false.**
