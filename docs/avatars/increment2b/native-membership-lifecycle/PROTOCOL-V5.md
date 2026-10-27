# Lifecycle v5 — batch the identical census; preserve failed overhead gates

V4 (ef32149) passes its beacon capability and completes four full fixed slots.
All eleven pagehide receipts and probe trace markers agree; native shutdown,
source identities, no-GC/dump/loss checks and live receiver coverage pass. Paired
elapsed ratios/control variation pass. Nevertheless all four slots exceed the
conservative 5% observation bound: controls 5.122/5.775%, probes 10.655/10.818%.
No threshold or observation is removed to turn that result into a pass.

The supported cost correction is batching existing IPC. One page.evaluate per
document now performs the SAME four ordered group/repeat censuses, same last/first
128 paths, same geometry calls, same returned count/geometry arrays. One native
phase RPC before and after the batch replaces four before/after pairs. The receiver
hook assigns the four known labels by ordinal blocks of 128 calls, resetting only
at the explicit per-document batch marker. Missing, extra, duplicate, shifted or
reordered calls must fail the existing exact count/repeat/disjoint checks. It records
an explicit overflow label past 512 rather than discarding an unexpected call.

All four census records retain the same enclosing host batch bracket; the auditor
requires exactly four records with identical brackets before counting that ONE
actual interval once. This does not subtract underlying geometry or callback cost:
whole batch cost, sequential counter calls, trace setup and native preparation
(still double-counted where inside batch) comprise the conservative bound. Old
v1-v4 intervals are never deduplicated or recomputed using this new protocol.

Freeze before four NEW fresh control/probe/probe/control slots. All v4 fixture,
document count, 220ms waits, beacon cost, native hooks, trace, clocks, source/identity,
5%/250ms/1.20/20% thresholds and interpretation limits stay. Earlier failed overhead
result remains archived. No replacement, more documents/dwell, forced GC, cache
change, application capture, product change or waiver. Original within-window
membership reclamation errors remain independently reported even if this lifecycle
diagnostic qualifies its observation costs.
