# 2B lifecycle memory correction

Status: diagnosis; 2B blocked, 3A paused.

1. Repeat the exact full warm-desktop sequence, five samples per arm in original/current/current/original order on pinned Chromium 156.0.8078.47. Compare all eight scenarios and five navigation checkpoints. Product remains f700187; original is 1c964dc. Retain every sample and both order comparisons.
2. Attribute the native allocations using separate diagnostic traces and controlled source changes. Distinguish rendering/SVG surfaces, preview document retention, navigation caching and runtime resource lifetime. Diagnostics do not substitute for uninstrumented acceptance.
3. Make only a demonstrated product correction; test the affected behavior and visual output, then recheck both execution orders.
4. Run full final-source functional/visual, native frame/callback, runtime and application matrix gates. Independently audit all 104 memory comparisons, each <=10 MiB, valid cohorts/renderer counts and lifecycle trends. Update acceptance only when every required gate passes.

No forced GC, extra cache flushing, shared-page subtraction, outlier deletion or budget waiver. Historical failures remain. No deployment or merge to main.

## Candidate gate (not accepted)

The unchanged-product hosted repeat 40287821303 completed all 20 measurements.
The forward pair passed; the reverse pair fails seasonal-preview RSS by +10.797
MiB. Same-current-source repeat medians differ by +32.195 MiB at navigation 10.
See `unchanged-hosted/independent-audit.json`; this does not waive any budget.

The candidate cancels owned avatar animation effects during **non-persisted**
pagehide, preserving cached-page animation state. The real navigation regression
check fails on unchanged source (one owned animation still running) and passes
on the candidate (zero), while an unrelated animation remains running and a
persisted pagehide preserves the companion's animation. The initial console-based
probe lost its navigation log and is retained as inconclusive; the corrected
probe stores its observation synchronously in sessionStorage.

Before any promotion, measure three sources on the pinned runner in fixed order:
original 1c964dc, unchanged current f700187, candidate, candidate, unchanged
current, original. Five complete warm-desktop sequences per cohort. Compare all
13 checkpoints and both memory metrics in both orders; retain same-source repeats
and candidate-versus-current results. No tracing or concurrent trace analysis in
these cohorts. Functional teardown alone does not establish a memory correction.
Only a validated candidate proceeds to the full final-source acceptance matrix.
