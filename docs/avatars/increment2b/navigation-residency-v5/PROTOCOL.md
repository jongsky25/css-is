# Bounded navigation trace, v5 — deferred trace transfer

V3 and v4 calibration failures remain archived, with no source comparisons run.
V5 changes only trace stream transfer timing from v4. At checkpoint 10, stop the
first trace, retain its completed stream handle, and start the second trace.
Do not read or write either trace's bytes until AFTER navigation 20 is sealed.
Keep two ten-navigation segments, the 64MiB requested buffer, explicit categories,
and one separate post-workload natural allocator dump. Record every transfer's
host start/end and byte count; reject any transfer within measured navigation.
Compression remains after browser teardown. Trace completion/integrity and all
raw events remain mandatory. Closed stream retention can itself affect browser
memory; total renderer RSS remains unadjusted, and controls remain required.

All [v4](../navigation-residency-v4/PROTOCOL.md) and inherited v3 gates remain:
NEW fixed current control/trace/trace/control calibration, ordinal 0; <=5% explicit
pause sum; <=250ms individual pause; <=20% paired navigation duration increase in
both orders; <=20% control duration variation; exact source/probe/artifact hashes,
sealed snapshots, natural-only collection and intact bounded traces. No threshold
change, replacement, sample deletion or reuse. A failed calibration stops comparison.

If calibration passes, run eight NEW original/current/current/original then
current/original/original/current trace slots, block ordinals 0/1, same frozen
harness. Retain every result and per-slot integrity/overhead gate, all 13 checkpoints
and all eight pair comparisons. Preserve clock uncertainty, uncovered trace gaps
and every >=5MiB RSS step. No concurrent analysis, forced GC or source changes.
Archive and re-audit. Diagnostic only; no causal owner claim or 2B acceptance.
