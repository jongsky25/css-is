# Synthetic page-allocation history capability, v1

Before any application experiment, test the exact Chromium 156 ELF/build ID with
Frida 17.5.1 diagnostic hooks at symbol-verified PageBackend normal-page allocation
and return-to-pool functions (0x5ab0350 / 0x5ab0550). Record monotonic times, backend,
page address, thread, allocation caller stack and phase. Hook installation changes
the diagnostic process only; no production package/dependency/browser change.

Fixed twelve fresh-document navigations on localhost: DOM/SVG/style repeated four
times; 3000 synthetic items each, existing 220ms wait. Empty page warm-up identifies
the renderer via CommitLoad before attaching. No application DB/data, forced GC,
heap snapshot, detailed dump, pressure notification or cache flush. Preserve errors
and all scheduled outcomes; do not retry a failed identical capability run.

Require exact build/version, successful attachment, no agent errors/overflow, all
12 navigations, nonempty allocation/return history, valid address lifecycle, useful
symbolized caller stacks for the three known fixture modes and observed page reuse
before considering this capable. Unobserved pre-attachment page allocations remain
unknown. A phase labels the interval in which an allocation triggers a page request;
it does not assign every object in that page to the phase or identify a JS owner.

This is NOT overhead calibration, source comparison, memory acceptance or a fix.
If capable, a distinct fixed control/probe/probe/control calibration must pass
unchanged timing/reader gates before applying the instrument to CSS-IS. Slow-path
page requests omit object allocations that fit existing buffers; coverage limits
must remain explicit. No process permission/kernel setting changes if attach fails.
