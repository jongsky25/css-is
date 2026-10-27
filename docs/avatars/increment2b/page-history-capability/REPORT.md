# Native normal-page history capability

The exact-build Frida probe captured normal-page requests and pool returns before
cleanup, without forcing GC. Synthetic DOM, SVG and style fixtures exercise the
caller stacks. This qualifies a diagnostic instrument, not memory acceptance.

The initial capture contains 1,023 requests and 652 pool returns, with all 325
module offsets resolved. The frozen four-slot control/probe/probe/control schedule
then passed: controls differ 5.644%; paired duration ratios are 1.03987 and 0.98712.
Explicit callback preparation occupies 3.397% and 3.689% of measured stage time;
maximum preparation is 2.558ms. No dropped records, agent errors or observed
call-order ambiguities. See `synthetic-calibration.json` and retained raw captures.

Capability harness: `3f06fd5`; synthetic calibration harness: `d732b70`.
Chromium 156.0.8078.47, build `1c5dca8527a61d07372e489142bee26af1bcaf71`;
Frida 17.5.1. Dependencies are diagnostic-only. No product or permission changes.

Synthetic stage durations exclude phase-marker gaps; the subsequent application
calibration includes those RPC costs in its total navigation window. Hook coverage
is limited to observed completed normal-page slow-path calls. It excludes large
pages, objects fitting existing buffers and unobserved/inlined entries. A requesting
stack is not the owner of every object on a page. Address reuse does not establish
a pool hit: release/unmap is not hooked. See [protocol](PROTOCOL.md).

The qualified next stage was executed; see the
[application report](../page-history-application/REPORT.md).
