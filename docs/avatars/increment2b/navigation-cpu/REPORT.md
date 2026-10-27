# CPU attribution v1 — partial V8 coverage retained

All four fixed control/profile/profile/control workloads completed from 00aa466.
The first auditor rejected Yappi child IDs: its aggregated function table merges
contexts while child records retain original IDs. Joining unique name/module/line
identities resolves every edge without dropping any. Greenlet and Page._sync
frames open across the recording boundary have nactualcall=0 with self CPU but
zero completed cumulative time; they are retained and explicitly marked open.
The original failed audit is preserved in initial-audit.json.

The corrected audit verifies source/artifact identities and retains Python and
native renderer attribution, but marks the experiment partial: CDP Profiler.stop
returns only the final navigation's V8 profile (roughly 0.5–0.6 seconds), not the
whole navigation window. These samples cannot establish full-window JS attribution.
No run is replaced or accepted. See assessment.json for all durations and limits.

A local three-navigation capability smoke demonstrated that Chromium's trace-based
V8 Profile/ProfileChunk events retain all three distinct smoke functions. V2 will
use this mechanism, preserving full chunks and checking coverage at every one of
20 navigation intervals, before a NEW fixed four-slot diagnostic. It does not reuse
v1 samples. The local data-URL smoke was blocked by browser policy; a normal local
HTTP fixture provided the capability test, with harmless favicon requests logged
as errors by the minimal fixture. No browser policy was changed.

The existing calibration/acceptance limits remain unchanged. CPU profiles are
forensic, not source comparison or 2B acceptance. All raw v1 data, failures, SHA
identities and extracted-archive re-audit are preserved. Product remains f700187.

Final offline repair is in v1-repaired-audit.json; assessment.json preserves the
intermediate rejection. V8 emits signed timeDeltas, so the repaired reader retains
all samples and reports counts without assigning negative per-function time.
The repaired status is partial_cpu_diagnostic with 124 source/probe hashes and
32 files verified, no identity errors. Both profiled runs exceed timing/reader
limits; these failures remain reported. The archive's identical re-audit refers
to the intermediate assessment, preserved with its historical auditor version.
