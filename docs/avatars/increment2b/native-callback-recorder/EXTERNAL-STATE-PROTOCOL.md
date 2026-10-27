# Native recorder v2 preflight — explicitly owned writable state

V1 6e7a8f1 compiles and passes all 20 native/Python clock brackets. Its first native
thread test fails with an access violation before producing a result; no workload
measurement or live hook collection occurs. Complete failure capture/assessment
remains. The one read-only storage inspection at 9edef02 resolves record size 72
but finds NO mapped range for the CModule's static snapshot buffer address. No
attempt is made to write/protect/repair that range or change permissions.

The supported repair supplies ALL mutable state as an explicit external symbol:
a Memory.alloc-owned read/write block containing records, snapshot records, mutex,
phase/cursor/counters and snapshot metadata. CModule keeps only code/constants and
an extern RecorderState declaration. Header is zeroed before initialization; C
state_size must fit the allocated block, and first/last state byte ranges must be
writable. No native target address is dereferenced. Capacity/layout and metadata
semantics remain 50,000 records / 72-byte records. No system permission change.

Freeze before ONE NEW complete preflight, same exact browser/build/Frida and fixed
20 clock brackets, four x256 concurrent records, then four x17 with test limit32.
All v1 clock/thread/phase/value/overflow/pending/snapshot checks remain; both complete
raw results are retained. Add actual owned-state size/bounds/protection checks.
Failure stops before live hooks/workload; no unchanged favourable retry or external
compiler fallback. Successful preflight still is not receiver/lifetime or overhead
qualification: those require separately frozen capabilities/calibration. No product,
application DB/data, forced GC, cache/policy change, later increment or acceptance.
