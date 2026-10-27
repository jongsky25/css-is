# CPU attribution v2 — trace-based V8 coverage across navigation

V1's four completed slots are retained as partial V8 coverage, not replaced.
Its child-ID audit was corrected to join unique Python name/module/line identities.
Open greenlet/Page._sync frames (nactualcall=0) retain self CPU and are flagged.
V8 signed timeDeltas are retained, without assigning negative elapsed weights.

V2 replaces page-session Profiler.start/stop with Chromium trace Profile/ProfileChunk
capture via disabled-by-default-v8.cpu_profiler, in the existing two navigation
segments. Full raw chunks survive context changes. A three-navigation local HTTP
capability smoke retained smokeWork0/1/2. No fixed trace sampling frequency is
claimed; report sample counts, not exact per-function CPU. Reconstruct timestamps
including signed deltas; require observations in EVERY one of the 20 bounded
navigation intervals. Missing coverage is explicitly partial, never manufactured.
Preserve idle/program/GC, outside-window samples and all raw node identities.

All other v1 requirements remain: a NEW fixed current control/profile/profile/
control schedule, full 30-second workload, pinned browser/date/ordinal, unchanged
product and source/probe identities. Python Yappi 1.7.3 CPU clock, all threads and
builtins, native tts/tdur coverage without nested double counting, scheduler and
cgroup observations in both arms, natural-only post-workload dump, deferred trace
transfer. Complete all four slots, no reuse/replacement, no concurrent analysis.
All prior timing/reader limits are reported; intrusive profiles remain diagnostic.
No source comparison or acceptance even if limits pass. Archive and re-audit.
