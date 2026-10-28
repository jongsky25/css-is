# Uninjected counter/GC-trace comparison v1

Freeze before one fixed counter-only / trace-only / trace-only / counter-only
schedule. Native-buffer diagnostic76baed0 completed all four slots with low
retention; its one older candidate resolves to V8's weak compilation queue. No
supported correction follows. This new factor comparison removes all browser
injection and compares measurement tracing with baseline counters; it is not a
favorable unchanged rerun or a qualification/acceptance replacement.

Reuse the unchanged lifecycle v12 runner in mode=control for EVERY slot. Preserve
12 DOM/SVG/style mounts,3000-element documents,32 receivers/group/two repeats,
220ms waits, both DOM witnesses, heap/DOM counters and11 pagehide beacons. No
additional page evaluation, query, workload wait, Runtime subscription, native
hook, snapshot, memory dump or GC request. Standard Playwright/identity tracing
is common to all slots; the baseline is not literally free of instrumentation.

Both factors log their explicit browser/page CDP command names/times. Source
freeze and allowlists enforce the original counters; no HeapProfiler command or
extra Runtime query is allowed. Frida attach/spawn/injection APIs fail closed on
any attempt, all captures must have no native history, and the job explicitly
drops SYS_PTRACE (runtime checks absence). Imported Frida client metadata in the
original runner is not browser injection. No native preflight runs in this job.

Trace-only starts a64MiB timeline/blink/cppgc/V8-GC trace immediately before the
first original fixture goto, inside its measured navigation interval. Clock marker
and trace setup are included in measured duration. All subsequent original work
is unchanged. The second marker, trace end/completion pumping and stream transfer
occur AFTER the measured loop; no wait or trace data read pads its denominator.
Counter-only starts no measurement trace beyond the common initial PID proof.

Validate exact Python3.12.14/Chromium156.0.8078.47/Playwright1.62.0 and ELF build
1c5dca8527a61d07372e489142bee26af1bcaf71. Preserve frozen sources and raw captures.
Fixture DOM hashes are pinned from the independently verified native-buffer
archivefc779f61af86700f16b4d6255e96c4c5ff1c04fba49e1ee02ad6f8f3f3441718
(42 verified result hashes); current raw document hashes must also match.

All four slots run even on individual failure. Audit schedule, byte-identical
fixtures, tags, null results, complete samples, stage/counter intervals, lifecycle,
PID, Frida guard and command counts. Trace slots additionally require exact config,
no loss/forced GC/dumps, deferred transfer and unique clock anchors. Keep conservative
clock envelopes and each counter's coverage/GC-before/overlap uncertainty. Record
natural major collections and V8 marked-global-proxy/heap statistics without
assuming a whole sweep, ownership or a root path.

Only two slots/factor: descriptive diagnostic, not a causal estimate or population
failure-rate claim. Command logging/tracing/setup can affect execution; absence of
failure does not prove a fix. All previous samples/gates remain unchanged. No
selected replacement, unchanged retry, product change, native/application
qualification, memory acceptance, later increment, merge or deployment follows.
