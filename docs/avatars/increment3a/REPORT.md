# Increment 3A — artwork implemented; acceptance pending

Dog, rabbit, bird and turtle now have 24 illustrated stages with changing head/body proportions, ears, wings and shell anatomy. Existing care, identity, growth, movement and seasonal policy remain. Original authored SVG reuses the existing gradient palette and adds head/neck accessory anchors. The illustrated rendering avoids the old drop-shadow filter.

Visual evidence: [light before/after](before-after-bare-light.png), [dark](before-after-bare-dark.png), [contrast](before-after-bare-contrast.png), [motion recording](before-after-motion.webm), [51 seasonal sheets](sheets/index.json), [216 stage/mood/theme rig checks](motion-rig-check.json). Reviewed small/hero silhouettes and monthly overview. Every rig responds to its existing CSS hook, and reduced motion suppresses those animations.

Local checks: 103 unit/integration/harness tests, 18 verifier regressions covering both default and four-animal batch selection, and four real authenticated/persisted animal-care browser checks pass. Local Chromium 154 evidence is functional/visual only; it is not combined with Chromium 156 performance cohorts. System ffmpeg was used for the local recording.

The gallery now loads the complete historical template tree, preserving the before version's split imports. Focused/whole-runtime benchmark species are configurable, retaining the original five runs, 30-second windows, controls and 50/33.3 ms budgets. A dedicated workflow measures this batch against fresh original baselines on pinned Chromium 156.

**Performance acceptance remains pending. Do not start 3B until the raw hosted functional, focused, runtime and application-matrix evidence passes review. Release readiness remains false.**

Verification source: `d0df557`, [run 40279025648](https://github.com/jongsky25/css-is/actions/runs/40279025648). [Exact untouched-species checks](unchanged-species.json): 2,448 static/interactive SVG comparisons; runtime/audio unchanged.

Initial run 40279025648 failed only preflight accounting (hardcoded species in the regression test); all benchmark phases were skipped. [Failure evidence](preflight-failure/README.md) is retained. The test now exercises both species configurations. The comparison recording now includes all companions in two rows.

A frozen 900 ms hide frame exposed the larger turtle head outside its shell despite the original animation hook passing. [Before](pre-retraction-fix/exposed-head.png) and [corrected](turtle-retraction-corrected.png) retain the visual evidence. Turtle-only retraction variables now tuck the face inside every stage's shell. The rig check verifies actual eye occlusion through browser hit testing at all 18 stage/mood combinations per theme. All 216 rig cases and reduced-motion checks pass; 2,448 untouched-species comparisons still pass. Local checks taken before commit record the base HEAD plus exact working-tree file hashes.

Run 40279416578 passed functional/visual gates but is superseded during focused timing because the turtle correction changes product CSS/art. Its partial measurements cannot accept the corrected source. A fresh complete cohort is required; no budgets change.

Current validation: source `cb2220f`, [run 40280615190](https://github.com/jongsky25/css-is/actions/runs/40280615190). The prepared audit branch splits retained evidence into bounded archive parts; do not rerun benchmarks merely to fix the current workflow’s compact packaging limit.
