# Native-buffer handle diagnostic: caller resolved, failed state not reproduced

[Run 40605880095](https://github.com/jongsky25/css-is/actions/runs/40605880095),
[PR #522](https://github.com/jongsky25/css-is/pull/522).
Frozen harness **76baed0e1236c089a57ae8b768e9292877aa9009**, workflow
**e4ea57473530ec6c2980e45932a961130ff047bc**. Completed 2026-10-28 UTC.

All four fixed captures complete after the new native buffer's prerequisite proof
passes. Broader handle-birth coverage finds one older unreleased candidate among
observed births in every slot. Its creation caller is V8's baseline compilation
queue, whose function entries are weak references. This does not establish strong
retention of documents. Every slot again shows low retention; the original failed
retaining root remains unidentified. **No supported product correction follows.**

## Capture and caller evidence

| Slot | Instrumentation | Records | Nodes stage 6 / stage 11 | Older unreleased candidates at GC 6 / GC 11 |
| --- | --- | ---: | ---: | ---: |
| 0 | buffer only | 9,543 | 9,007 / 6,008 | 1 / 1 |
| 1 | buffer + membership | 9,543 | 9,007 / 6,008 | 1 / 1 |
| 2 | buffer + membership | 9,543 | 9,007 / 6,008 | 1 / 1 |
| 3 | buffer only | 9,543 | 9,007 / 6,008 | 1 / 1 |

Each slot records 4,539 handle creations, including 1,011 outside the previously
tracked owner constructors, 3,408 other creations within those constructors and 120
source-audited context handles. There are 4,540 release entries, 50 direct weakening
entries and 96 pointer-cell weakening entries. Some transitions refer to handles
that predate attachment: 371 releases and 2 pointer-cell weakenings per slot.
These remain explicitly unknown rather than assigned invented births.

At GC stages 6/11 the same older candidate, generation 778, originates in stage 0.
Its return PC is **0x567f0ab**. Matching debug symbols resolve the preceding
instruction to **v8::internal::baseline::BaselineBatchCompiler::Enqueue**.
Disassembly shows its call to GlobalHandles::Create at 0x567f0a6, followed by storing
the returned handle at 0x567f0ab. Exact-version source identifies the inlined
EnsureQueueCapacity helper: it creates a **WeakFixedArray** compilation queue;
Enqueue stores **MakeWeak(shared)** entries. A strong handle to this queue is not
evidence of a strong path through its weak entries to old contexts/documents.
No change to the browser compiler or product is justified by this candidate.

[Caller evidence](caller-source/assessment.json) preserves pinned source/hash,
excerpts, disassembly and symbol output. Function identity is established; no
source line is claimed from incomplete DWARF line resolution. Raw API object
values were not dereferenced and are not identities across moving GC.

## Integrity and scope

The recorder now uses C callbacks with immutable 72-byte records in an owned RW
buffer, mutex-protected append, 50000-record capacity and deferred decoding. It
adds neither per-event JS callbacks nor the extra Runtime subscription. Original
lifecycle runner, fixture documents and membership recorder remain unchanged.
No snapshot, forced collection, object query, memory dump, cache flush or extra wait.

New native preflight proves a two-way storage canary, 20 clock brackets, 1,024
immutable argument/return/caller records on four threads and deliberate overflow
with 32 stored/36 dropped. Live records have zero drops/pending, contiguous serials,
valid intervals, matched generations and a positive known per-context caller
witness at 0xfd4bb86. Both membership probes retain natural GC traces. The standard
original-recorder preflight also passes and re-audits independently.

These are **observed entry paths**, not a complete census of strong roots. Inlined
transitions and weakness restoration may be unobserved. All older unreleased
candidates remain included even after observed weakening. Pre-attach roots and
heap-edge reachability are missing. Caller sites identify creation code, not target
types, exclusive ownership or attributed bytes. Native allocation/hooks still
perturb execution; cost is unqualified. Fewer per-event JS callbacks does not prove
unchanged GC behavior. No prior failed sample is replaced by these captures.

## Durable evidence

**47 local/cloud preflight tests pass.** All **42** result-manifest hashes verify,
every archived source matches its frozen commit, and all four independent raw-buffer
analyses match cloud output exactly. New native proof and original native preflight
both independently reproduce. [Assessment](assessment.json) and [protocol](PROTOCOL.md).

Artifact **12780722669** is retained byte-for-byte as
[buffer-v1-evidence.zip](buffer-v1-evidence.zip), SHA256
`fc779f61af86700f16b4d6255e96c4c5ff1c04fba49e1ee02ad6f8f3f3441718`.
All proof, records, captures, traces, inventory, sources, setup logs and slots are
preserved. Setup/original preflight logs outside the 42-file result manifest remain
covered by the full ZIP hash. Runner is standard hosted AMD EPYC 7763, four affinity
CPUs, no container CPU quota. No physical exclusivity claim or resource changes.

## Next bounded work

Do not keep expanding handle-birth hooks or repeat this build unchanged. The gap
is reproduction of the high-retention state with enough GC evidence, including
pre-existing roots and heap edges. A distinct minimal diagnostic should compare
uninjected captures with and without GC tracing, preserving counter-only baseline
slots and trace-only slots in a frozen fixed order. This isolates tracing/attachment
conditions before attempting another intrusive root graph. Retain every slot and
any failure; no favorable replacement or qualification follows from this contrast.

Native/application qualification, the frozen lossless transport cost and original
2B memory acceptance remain blocked. No measurement remains active. Product cf363bf
and isolated candidate cd94bf3 remain unchanged. PR #522 is reviewable and unmerged;
no product fix, candidate promotion, later increment, merge or deployment occurred.
