# Native throttling attribution

Diagnostic only; application source remains c2f404f. Compile
`scripts/avatar_baseline/native/throttle_probe.c` with gcc -shared -fPIC -O2 -ldl
to `/tmp/avatar-throttle-probe.so`. The opt-in signal diagnostic runs the original
callback-trace scenarios while measuring entry/exit around Chromium's unchanged
SIGUSR2 handler. No JS API wrapper, handler replacement logic, changed throttle
rate, or acceptance-time subtraction. The wrapper's scheduling/measurement effect
is a limitation, so these ten runs are not promoted to acceptance.

All ten diagnostic callback maxima are below50ms, but direct native records show
handler pauses up to345.950ms during the30-second input window. This establishes
that large emulator pauses can occur independently of avatar callbacks. It does
not prove that each earlier slow avatar callback was caused by such a pause.
The source implementation caps nominal CPU4 busy-waits at3ms:
https://github.com/chromium/chromium/blob/154.0.8037.57/third_party/blink/renderer/platform/scheduler/common/thread_cpu_throttler.cc

`signal-analysis.json` correlates CLOCK_MONOTONIC records with trace windows on
the same renderer PID. Native records and browser traces are losslessly gzipped.
Reproduce analysis with `scripts/avatar_baseline/analyze_throttle_signals.py`.

The subsequent Docker cpuset candidate was rejected after a148.967ms callback.
Hosted CI now compares original/current source sequentially on one runner and
runs independent focused/functional phases. Previous evidence remains intact.
