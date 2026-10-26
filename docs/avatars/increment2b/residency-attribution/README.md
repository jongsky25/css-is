# Native residency attribution

This implements the follow-up to the natural-collection investigation. It is an
opt-in diagnostic, never acceptance evidence. The product remains unchanged.

Run with the project's locked test environment and the pinned Chromium binary:

```sh
.venv/bin/python scripts/avatar_baseline/run_residency.py \
  --output /absolute/path/to/new-evidence-directory \
  --browser-dir /directory/containing/pinned/chromium
.venv/bin/python scripts/avatar_baseline/analyze_residency.py \
  /absolute/path/to/new-evidence-directory
```

The runner requires a new output directory, creates temporary original/current
worktrees at `1c964dc` and `f700187`, copies the same measurement fixture to both,
and executes original/current/current/original serially. Each arm uses the full
30-second warm desktop scenario sequence once, with 13 checkpoints. Fixtures are
restored and the owned worktrees removed afterward. A failed arm is preserved and
stops the runner; analysis never runs concurrently with a browser measurement.

At each original checkpoint the probe keeps the original RSS/heap/DOM observation,
emits a trace clock marker, samples native allocation stacks, requests a detailed
browser-wide allocator dump, then records a separate post-dump snapshot. Tracing
includes natural C++/V8 collection and memory-infra. It neither forces collection
nor flushes extra caches. This instrumentation changes overhead and can change
natural collection timing; its numbers cannot replace the uninstrumented gates.

Chromium’s JSON trace exporter renumbers dump IDs separately from CDP GUIDs.
The analyzer requires exactly one app-renderer dump inside each checkpoint clock
interval and retains both identifiers. It joins fragments only when PID, trace ID
and timestamp agree and allocator keys are disjoint. It retains per-allocator
byte attributes, records preceding sweep events, and keeps total renderer RSS
unchanged. Missing/duplicate dumps, incorrect timestamps, ambiguous app renderer
mapping and forced collection invalidate analysis. A sweep event is not proof
that every heap sweep has completed. Allocated objects can include garbage
awaiting collection; reserved/committed capacity is not interchangeable with RSS.
Overlapping allocator families must never be summed or subtracted from RSS.

The compact retained event stream omits VM-map detail but preserves exact
allocator dictionaries, collection events, navigation commits and clock markers.
The complete original trace is separately retained and hashed.
