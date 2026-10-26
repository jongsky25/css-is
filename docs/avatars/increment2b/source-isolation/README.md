# Controlled source isolation

This screens three focused interventions against unchanged product f700187.
It is not acceptance and none of the diagnostic reversions is promotable as-is.

Order: current / geometry / preview / SVG / SVG / preview / geometry / current.
Each arm runs two complete 30-second warm-desktop workloads on pinned Chromium
156.0.8078.47, serially, without traces, native sampling, detailed dump requests,
concurrent analysis, forced collection or extra cache flushing. Every sample and
all 13 checkpoints are retained. The renderer memory detail reads are the same
as earlier uninstrumented targeted cohorts.

Interventions:

- Geometry disables only the ResizeObserver registrations inside trackGeometry.
  Cached geometry, pointer handling, audio and artwork remain current. This may
  regress resize behavior and is diagnostic only.
- Preview reverts only f700187's omission of static movement/reaction wrappers,
  using its parent versions of `_avatars.html`, `_growth.html`, and `me.html`.
  Current artwork and the static animation policy remain.
- SVG restores original species shapes through the original art dispatcher,
  adapted to accept the unused scope argument, and suppresses v2 local gradients
  and data marker. Current runtime and static-preview omission remain. This is
  an intentional visual reversion, never a final fix.

Before measurement, the selection rule was fixed: at least 5 MiB RSS improvement
at both navigation 10 and navigation 20 in both execution orders, no RSS or heap
checkpoint worsening over 10 MiB, and valid samples/renderer counts. Both current
control cohorts remain visible. Two-sample results only screen candidates; an
apparent improvement requires five-sample original/current/candidate validation,
then the full acceptance matrix after a proper product correction.

```sh
.venv/bin/python scripts/avatar_baseline/source_isolation.py \
  --output /absolute/path/to/new-output \
  --browser-dir /directory/containing/pinned/chromium
.venv/bin/python scripts/avatar_baseline/analyze_source_isolation.py \
  /absolute/path/to/new-output
```

The runner creates isolated temporary checkouts, retains exact variant sources
and diffs, restores its copied files and removes only its own checkouts. The
analyzer verifies raw source hashes, both samples, full checkpoint coverage,
browser/workload settings, application errors, renderer counts and finite memory
values. It reports all comparisons, not only selected improvements.
