# 2B lifecycle memory correction

Status: diagnosis; 2B blocked, 3A paused.

1. Repeat the exact full warm-desktop sequence, five samples per arm in original/current/current/original order on pinned Chromium 156.0.8078.47. Compare all eight scenarios and five navigation checkpoints. Product remains f700187; original is 1c964dc. Retain every sample and both order comparisons.
2. Attribute the native allocations using separate diagnostic traces and controlled source changes. Distinguish rendering/SVG surfaces, preview document retention, navigation caching and runtime resource lifetime. Diagnostics do not substitute for uninstrumented acceptance.
3. Make only a demonstrated product correction; test the affected behavior and visual output, then recheck both execution orders.
4. Run full final-source functional/visual, native frame/callback, runtime and application matrix gates. Independently audit all 104 memory comparisons, each <=10 MiB, valid cohorts/renderer counts and lifecycle trends. Update acceptance only when every required gate passes.

No forced GC, extra cache flushing, shared-page subtraction, outlier deletion or budget waiver. Historical failures remain. No deployment or merge to main.
