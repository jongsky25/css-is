# Native recorder v3 — direct owned-state canary, not range-enumeration inference

V2 51a1b3b removes the initial access violation by supplying external mutable state,
but result export fails on reading .protection from a null Process.findRangeByAddress
result. Its concurrency result never reaches the host validator; no concurrency pass
or workload qualification is claimed. Complete failure capture remains.

Correction to the storage interpretation: a null range lookup is INCONCLUSIVE for
agent-owned memory; it does not establish unmapped/read-only state. The earlier
read-only diagnostic remains unchanged as raw evidence. Do not change protections,
permissions, or use an external compiler to make the lookup succeed.

V3 proves native symbol/state correspondence and writability directly in an OWNED
canary field: JS writes 0x0123456789abcdef and C must read it exactly; C writes
0x1122334455667788 and JS must read it exactly. Native state_size must fit its
allocation; added final canary remains within the zeroed header. Record ABI stays
72 and limit/capacity stay unchanged. Optional range/module enumeration metadata
may be null; it cannot replace a canary or successful concurrent writes.

Freeze before ONE NEW full preflight: 20 clock brackets; four x256 events with all
1,024 complete immutable phase/time/pointer values and distinct TIDs; separate four
x17 limit32 overflow with 32 records /36 drops. Preserve both outputs and all prior
failures. Exact renderer, self-test-only prefix, no live ready state and no agent
error are checked. No live hook/workload, forced GC, pressure/cache change, permission
change or favourable identical retry. Only a full pass permits separate type/lifetime
proof, then fixed unchanged-threshold calibration. No product or application change.
