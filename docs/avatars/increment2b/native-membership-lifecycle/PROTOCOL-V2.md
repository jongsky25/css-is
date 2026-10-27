# Lifecycle v2 — read-only launch-flag verification repair

Frozen v1 at 18d3eaa completed its four scheduled processes but every slot stopped
BEFORE the fixture workload: Browser.getBrowserCommandLine rejects reads without
--enable-automation. No membership, timing or GC sample was collected. All four
failure captures/logs and the failed audit are retained in v1-setup-failure-evidence.zip.
This is not evidence that the back/forward cache flag is present at runtime.

The sole capture-method correction is to obtain the launched browser PID from
SystemInfo.getProcessInfo, read that known PID's /proc cmdline, and persist only the
boolean presence of --disable-back-forward-cache. No full argument values, unrelated
processes, secrets or credentials are output. No launch flag or browser policy is
added, removed or bypassed. No unsupported CDP method is retried.

Freeze v2 before four NEW control/probe/probe/control slots. All v1 fixture, capture,
telemetry, native hooks, timing/integrity gates and interpretation limits stay in
PROTOCOL.md. A false runtime BFCache-disabled flag fails the intended fixture policy;
it is retained, never corrected by changing the launch. Setup is not a replacement
for a measured slot; the v1 failure and v2 result stay separate. No forced GC,
extended dwell, extra documents, cache flush, RSS adjustment, application collection,
product correction or later increment.
