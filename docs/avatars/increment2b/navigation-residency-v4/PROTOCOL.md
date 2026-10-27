# Bounded navigation trace, v4

V3 calibration is archived as FAILED: slot 2's explicit pause fraction was 5.408%,
above the unchanged 5% gate. No v3 comparison was launched or sample replaced.

V4 changes only trace segmentation: TWO ten-navigation windows, rotation after
checkpoint 10, plus the separate endpoint-only dump after navigation 20 is sealed.
Keep the 64MiB requested buffer and explicit categories. No in-workload dump,
extra full snapshot, forced GC, cache flush or production change. V3 traces are
small enough to justify testing this bounded segmentation; integrity must pass.

All other [v3 protocol](../navigation-residency-v3/PROTOCOL.md) requirements apply:
a NEW current-source control/trace/trace/control calibration, ordinal 0, same
committed fixture; <=5% total explicit pauses, <=250ms each, <=20% paired duration
increase in BOTH orders, <=20% control duration variation, all identities and
trace integrity checks. No threshold change, replacement, sample exclusion or
reuse. If calibration passes, eight NEW original/current/current/original then
current/original/original/current slots; same frozen harness, block ordinals 0/1,
full workload. All failures retained. Per-comparison integrity/pause gates remain.
No concurrent heavy analysis; archive and independently re-audit all evidence.
Physical page ownership remains unavailable; endpoint allocations are after, not
contemporaneous with, sealed workload snapshots. Diagnostic only, not acceptance.
