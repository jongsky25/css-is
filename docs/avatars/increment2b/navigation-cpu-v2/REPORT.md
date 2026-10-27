# CPU attribution complete — repeated connection setup is a concrete hotspot

**Both profiled runs cover all 20 navigations. 2B is still blocked.** The fixed
current-code control/profile/profile/control schedule completed from `bcbf0b4`.
Audit verifies 124 source/probe hashes and 32 cohort files; all six traces are
intact, all measured checkpoints match sealed output, and V8 coverage is present
for every navigation in both profiles. No sample was excluded or replaced.
The extracted 39-member archive reproduces the serialized audit exactly.
Eighty-three focused tests pass. Product remains f700187; no source comparison,
acceptance, later increment or active measurement.

## Python: repeatedly initializing SQLite connections

| Observed across 20 navigations | Profile 1 | Profile 2 |
| --- | ---: | ---: |
| Python function self CPU, all threads | 9657.895ms | 8080.490ms |
| SQLite execute calls / self CPU | 4240 / 1562.434ms | 4240 / 1387.893ms |
| storage.connect calls / cumulative CPU | 240 / 1500.960ms | 240 / 1321.498ms |
| Its four setup PRAGMAs: calls / CPU | 960 / 1397.646ms | 960 / 1229.742ms |
| Setup share of SQLite execute CPU | 89.45% | 88.60% |

The specific path is `app.get_conn → storage.connect → Connection.execute`.
The four statements are busy_timeout, foreign_keys, journal_mode=WAL and
synchronous=NORMAL. There are roughly 12 connections per navigation across the
full request activity. This is connection setup, not simply expensive application
SELECT statements. These CPU costs are profiled observations, not production
latency or a measured saving; cumulative and self values must not be added.

Other recurring costs include Playwright message decoding, middleware, template
rendering and compression. The avatar macro's cumulative Python CPU is about
241ms in each profile; that alone does not account for browser rendering cost.
All functions, caller records and threads remain in the raw profile. Threads
already running before profiling are covered by a dedicated regression test.

### The tempting PRAGMA removal does not solve it

An additional isolated, fixed 200-connection probe used a fresh synthetic schema
(619 schema objects, SQLite 3.53.1), with full/no-WAL/no-WAL/full blocks of 50.
No browser, production database or application code was changed. CPU was measured
with thread_time_ns without Yappi; all connection settings were verified afterward.

| Block | Setup | Median open + setup CPU | Expensive statement median |
| --- | --- | ---: | ---: |
| 0 | full | 7.922ms | journal_mode: 7.178ms |
| 1 | skip journal_mode after initial WAL setup | 8.279ms | synchronous: 7.459ms |
| 2 | skip journal_mode after initial WAL setup | 7.520ms | synchronous: 6.981ms |
| 3 | full | 8.735ms | journal_mode: 8.169ms |

Removing journal_mode shifts the cost to synchronous; it does not eliminate
fresh-connection initialization. The probe supports investigating connection
churn, not deleting database durability/concurrency settings. It does not by itself
prove which internal SQLite initialization operation is responsible or reproduce
browser concurrency. The full script and every observation are retained.

## Chromium: style and paint dominate the recorded native categories

| Renderer main-thread CPU attribution | Profile 1 | Profile 2 |
| --- | ---: | ---: |
| Union of recorded native CPU intervals | 3035.211ms | 2231.254ms |
| UpdateLayoutTree | 700.674ms | 548.942ms |
| Paint | 552.491ms | 364.825ms |
| FunctionCall, innermost recorded intervals | 330.448ms | 326.210ms |
| ParseHTML | 269.516ms | 258.923ms |
| Layout | 209.237ms | 187.177ms |

The attribution uses thread CPU timestamps, restricts events to conservative
navigation bounds, and assigns overlapping intervals to the smallest recorded
enclosing event. Nested categories are not summed twice. This is recorded
main-thread coverage, not a complete native-stack profile or all renderer threads.
It does not establish that all style/paint work belongs to avatars.

Trace V8 profiles retain 57,179/57,340 samples, with observations in every one of
20 navigations. Most leaves are idle/program; 141 leaf samples point to avatars.js
in each run. Native DOM work can appear under builtins/program rather than avatar
JS leaves, so this is NOT proof that avatars are cheap. Signed deltas and samples
outside navigation intervals remain counted explicitly; no negative per-function
time is invented. Hardware cycle counters are unavailable, so execution frequency
versus instruction-count changes remain unresolved.

## Instrumentation costs and disposition

| Slot | Mode | Navigation ms | Largest explicit pause | Scheduler reader CPU |
| --- | --- | ---: | ---: | ---: |
| 0 | control | 8358.599 | 0.002ms | 0.523% |
| 1 | profile | 15619.406 | 342.212ms | 1.745% |
| 2 | profile | 13502.857 | 412.200ms | 1.341% |
| 3 | control | 9098.553 | 0.002ms | 0.657% |

Controls differ by 8.85%, but profiles are 86.87%/48.41% slower than their paired
controls. Both exceed the unchanged 250ms individual-pause, 1% reader-CPU and
20% paired-duration limits. Total explicit pause fractions are 2.34%/3.19%; the
rest of profiler overhead cannot be inferred by subtracting those pauses.
Cgroup throttling increases are 0/158626/0/361013 microseconds across the four
slots; these container-wide counters are retained, not attributed solely to avatars.
Python profile tails beyond the sealed window are 3.24/4.11ms.

Status complete_cpu_diagnostic means the attribution data is complete, NOT that
calibration or acceptance passed. The intrusive profiles cannot explain historical
unprofiled control variation causally or establish an original/current RSS effect.
The original 2B memory failures remain unresolved.

The concrete next candidate is reducing repeated SQLite connection initialization
with explicit thread ownership and transaction cleanup. Validate connection-count
reduction, authentication/transaction behavior, then the unchanged unprofiled
control and memory gates before treating it as a fix. Removing PRAGMAs or widening
budgets is not supported. Browser style/paint attribution remains a separate
potential target requiring source-specific evidence. No candidate was implemented.

## Evidence and retained repairs

- `assessment-evidence.zip` / `assessment-manifest.json`: all raw slots, frozen
  harness, source identities and archive/member hashes; independent re-audit.
- `assessment.json` and `summary.json`: full audit and compact findings.
- `sqlite-setup-probe.py` / `.json`: fixed isolated connection experiment.
- `capability-smoke.*`, `capability-result.json`: cross-navigation V8 capability.
- `tests.txt`, `PROTOCOL.md`: focused validation and frozen schedule.
- `archive-reaudit-note.json`: initial in-memory integer versus JSON string-key
  comparison failure; normalized JSON re-audit is identical. No measurements changed.

[V1](../navigation-cpu/REPORT.md) remains preserved as partial: its page-session
V8 profiler retained only the last navigation. Python merged child IDs are resolved
by unique function identity; open call frames and signed V8 deltas remain explicit.
The initial/intermediate failed audits and repaired partial audit are retained.
V2 is a distinct instrument and schedule, with no reused or replacement samples.
