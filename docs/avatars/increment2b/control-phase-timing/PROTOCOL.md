# Control phase timing diagnostic v1 — frozen before capture

Question: which operations contribute to the prior v12 control duration variation
(3702.241/4470.708ms; 20.7568% >20%)? That failed qualification remains unchanged.
This diagnostic does not qualify an instrument, correct durations, or run the app.

Exactly four fresh Python/Playwright/browser processes, controls only, one capture
per slot with no replacements. Keep pinned Chromium 156.0.8078.47 and native ELF
1c5dca8527a61d07372e489142bee26af1bcaf71; original 12-document DOM/SVG/style schedule,
3,000-element fixtures, four 32-receiver groups, selector caching, absent-attribute
null getter and 220ms fixed waits. Verify independent renderer identity before
measurement using the short identity trace; no native injection or full trace
inside measurement, forced GC, cache flush, app DB or user data. No CPU/quota/
affinity adjustments, extra workloads or concurrent heavy analysis during capture.

Explicit host monotonic brackets for each navigation, fixed wait, DOM serialization
before/after, census, hashing, heap/DOM counters and added navigation timing query.
At each phase boundary, record separately bracketed bounded snapshots: aggregate
process CPU ticks, start time, faults and main-thread schedstat for this Python,
its direct Node driver, known browser and renderer PIDs; cgroup cpu.stat; aggregate
/proc/stat CPU ticks; load averages; pressure files if available. Preserve missing
pressure and zero schedstat explicitly; do not infer zero scheduling delay. Capture
cgroup membership/quota and affinity once. No arbitrary cmdlines or environments.
Record browser performance navigation timings separately from host clock values.

Telemetry is synchronous, occurs outside operation brackets and adds work. Retain
its duration and unbracketed residual, never subtract it from a qualification
result. CPU snapshots span operation plus their own reads; cgroup counters describe
shared context and main-thread schedstat does not describe all threads. Missing
pressure limits attribution. A positive throttle increment proves concurrent
cgroup throttling, not that it caused an operation's duration. No acceptance-style
20% gate applies to these newly instrumented diagnostic samples.

Freeze collector, fixture, diagnostic/runner/checker and imported lifecycle/identity
validators. Preserve every capture, error, identity and runner output with hashes.
Validate all 108 ordered phases per capture, host brackets, full schedule, fixed
wait floor, exact known serialized fixture hashes, census counts/types/nulls,
beacons, process start identity and monotonic CPU/cgroup counters. No partial
capture may be silently dropped. Commit code, policy and passing preflight tests
before running. Archive and independently re-audit the complete four-slot result.
Report both reproduced and absent variation without replacing earlier failures.
A new qualification screen requires a supported explanation/intervention first.
