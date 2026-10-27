# Shared stylesheet allocation screen, v1

Prepared before memory collection; collection remains blocked by the visual prerequisite. This is a candidate screen, not 2B acceptance.

Current: f700187553bd555dd3a9b638d5aa8e5fb59f3142.
Candidate: 69605628393d044f9a0426ea0be3abdf99527bc3.
The only product difference extracts the exact 15,883-byte inline avatar CSS to
/static/css/avatars.css?v=1. Artwork, runtime and CSS rules remain identical.
Allocation evidence suggests repeated document/style/network buffers are worth
reducing; it does not establish CSS as the cause of the original regression.

Prerequisites: nine existing browser regressions, real HTTP stylesheet loading and
body reuse, exact template reconstruction, and all 30 visual sheets (2,880 cells)
matching after deterministic animation freezing. No completed comparison has passed.
The normal renderer showed small preview differences even for unchanged-source
comparisons (six of thirty sheets). Software rendering also failed (three of thirty). Preserve
both failures; software mode was visual-only, not a change to memory settings. Preserve setup failures and the
initial visual comparison. No memory run until those checks pass.

Run current/candidate/candidate/current, two samples per cohort, eight full
warm-desktop workloads total. Fresh process/database per cohort; same existing
baseline workload, Chromium 156.0.8078.47, 30-second scenarios, 20 navigations,
fixture date 2026-07-15T12:00:00, renderer pinning off. Observe all eight scenarios
and navigation checkpoints 1/5/10/15/20. Only fixture adaptation adds the external
CSS file to source hashes. No forced GC, tracing, native profiling, routing,
cache flush, concurrent analysis, replacements or favorable reruns. Complete all
four scheduled cohorts even if one fails.

Independently audit exact source and fixture hashes, artifact hashes, two samples,
matched positive renderer counts, and complete checkpoint records. Compare
candidate minus current in both orders, plus current and candidate repeat controls.
The candidate qualifies for larger five-sample original/current/candidate
validation only if BOTH orders improve median RSS at navigation 10 AND 20 by at
least 5 MiB, neither order worsens ANY RSS/heap checkpoint by more than 10 MiB,
and BOTH same-source controls have absolute median differences at EVERY checkpoint
and metric of at most 10 MiB. Invalid evidence is inconclusive. A failed screen
stops promotion and retains all evidence. A pass is not acceptance and does not
waive the original baseline or any existing functional/performance gate.

Run scripts/avatar_baseline/stylesheet_screen.py only with a passing
--visual-assessment (the runner enforces this before creating worktrees), then independently audit with
scripts/avatar_baseline/analyze_stylesheet_screen.py against the frozen harness
commit recorded in experiment.json. Archive raw outputs and re-audit an extracted
copy. Primary product remains f700187 until full acceptance gates are satisfied.
