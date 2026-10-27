# Fixed navigation CPU attribution

The V6 calibration failure and all older evidence remain unchanged. This is a NEW
forensic diagnostic, not another acceptance calibration or a favorable rerun.
Four CURRENT f700187 slots: control / profile / profile / control, fresh pytest,
database and browser each time, ordinal 0, full 30-second warm-desktop workload,
pinned Chromium 156.0.8078.47 and July 15 fixture date. All four slots complete;
retain every sample/failure with no replacement. No concurrent heavy analysis.

Both arms retain V6's navigation bounds and scheduler/cgroup observations. Profile
arms retain the two ten-navigation traces and separate post-workload allocator dump
with deferred stream transfer. ADD Yappi 1.7.3 all-thread CPU-clock profiling,
including builtins, and V8 CPU samples at 2000us. Start after background snapshot
before navigation 1; stop after the sealed navigation-20 snapshot and scheduler
edge. Record host start/stop bounds and the post-window tail. Serialize profile
files after workload; never force collection, change quota/affinity or clear caches.
Yappi is installed only in the diagnostic venv, not production dependencies.

Preserve full Python function/caller/thread tables, V8 nodes/samples/deltas,
trace files, source hashes and all baseline output. Verify profiling captures
pre-existing server threads. Python self CPU is additive; cumulative/caller CPU
overlaps. V8 timeDeltas are sampled elapsed weights, not exact CPU ownership;
keep idle, program and GC samples. Native renderer main-thread tts/tdur event
intervals are CPU time: report union coverage attributed to smallest enclosing
recorded event, plus non-additive inclusive totals and unclassified/missing events.
Do not sum nested layout/script/task spans or conflate wall time with CPU time.
Conservatively restrict native events to the sealed navigation window using clock
marker bounds, and count boundary/outside events separately. Untraced controls
have no authoritative page/PID association. Profiles may have a
small tail beyond the sealed window; record it, do not call it exact navigation CPU.

All original timing/reader limits are evaluated and reported (5% explicit pauses,
250ms individual pause, 20% paired duration/control stability, 1% scheduler reader
CPU). A valid profile may be intrusive; report that rather than discarding it.
Even if all limits pass, these function-level diagnostics cannot qualify a source
comparison or 2B. No automatic original/current run, product patch or later increment.

Hardware CPU cycle counters are unavailable (read-only user-cycle perf_event_open
capability probe returned ENOENT). No privileged setting is changed or frequency
claim inferred. CPU function profiles and counters identify observed work, but do
not by themselves distinguish more instructions from lower effective execution
speed. Retain limitations and failures. Archive and independently re-audit.
