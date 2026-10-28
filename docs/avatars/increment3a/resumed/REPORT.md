# 3A resumed validation — 2026-10-28

Recovered product from cb2220f onto the provisionally accepted 0a91f73 baseline.
Only four species and turtle retraction/v2 marker are imported into product code;
no unrelated diagnostics, reader changes or gradient candidate are promoted.
Historical evidence remains in the parent directory and is not new acceptance.

Fresh local Python 3.12 / Chromium 154.0.8037.57 checks:
- 86 care, audio and onboarding tests pass.
- Four authenticated browser care tests pass and verify saved care.
- 216 real stage/mood/theme motion-rig cases pass, including turtle eye occlusion
  and reduced motion. Actual rendered contact sheet was inspected.
- 2,448 unchanged-species SVG comparisons pass; runtime/audio remain byte identical.

Commands use .venv/bin/python and repository locked test dependencies.
Native five-run, 30-second CPU4/mobile interaction checks for all four animals are
in progress. Acceptance remains pending. No physical-phone testing, deployment
or main merge. The 2B exception does not waive any 3A gate.

Frozen 3A native check completed: all four species × five 30-second CPU4/mobile
interaction runs pass the 33.3 ms frame ceiling (p95 range 16.7–16.8 ms). All 20
samples are retained under performance/. Chromium 154 results remain separate from
historical 156 results. Product files stayed fixed in /workspace/css-is while
later implementation used a separate worktree. This verifies this frame gate only;
LoAF reporting no owned callback is not proof of the separate 50 ms callback gate.
Later integrated wardrobe/motion changes need their own performance verification.
