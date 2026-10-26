# Retaining-path capture — authorized for this four-slot experiment

The handoff forbids forced GC. Chromium 156 heap snapshots force it internally.
The user explicitly approved this exception with “yes run it” on 2026-10-26;
it does not alter any acceptance workload or budget.

Four fixed fresh-browser/database slots: original/current/current/original,
using the existing full warm-desktop workload and per-navigation timing probe.
Exact product refs remain 1c964dc and f700187; Chromium stays 156.0.8078.47.
All four slots use sample ordinal zero. A frozen fixture adapter saves the completed
baseline JSON before context teardown, sealing its hash before the snapshot. Preserve every slot and failure; no
replacement or extension to obtain a favorable outcome.

After navigation 20's natural baseline observation and after the natural trace
has been closed and saved, capture exactly one `HeapProfiler.takeHeapSnapshot`
with internal/native nodes exposed, before closing the browser context. Stream
the graph to gzip; record DOM/heap immediately before and after, source hashes
and explicit `intentional_forced_gc: true`. Do not enable JS allocation sampling.
No snapshot measurements may enter acceptance or natural-collection comparisons.

Inspect strong root-to-detached-document paths in all four resulting snapshots,
separating weak edges, inspector/automation roots and product closures/listeners.
Retain all unresolved native/hidden edges. A path after forced GC is a forensic
lead, not proof it explains earlier natural samples; absence can mean the snapshot
collected the transient objects. No change is promoted without separate functional
and unchanged uninstrumented memory gates.

Authorized entry point:

```sh
CSS_AVATAR_FORENSIC_GC=authorized .venv/bin/python scripts/avatar_baseline/run_retaining_paths.py --output /workspace/scratch/avatar-retaining-paths --browser-dir /workspace/scratch/chromium156-bin
```

The runner still requires the explicit opt-in. Authorization covers these four
post-workload forensic snapshots only; natural/acceptance gates remain unchanged.
The original preparation and pending status are preserved in commit 8ff10ee.
