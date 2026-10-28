# Snapshot-free context journal: cleanup observed, failed state not reproduced

[Run 40599450345](https://github.com/jongsky25/css-is/actions/runs/40599450345),
[PR #521](https://github.com/jongsky25/css-is/pull/521).
Harness **2c898c646f4f79d526f6fbc7f313c752a87ee0e3**, workflow
**47852d7590e27becca3d1aed2a2add16c9fbebf1**.

All four fixed captures complete. At both GC epilogues in every slot, **zero known
context-owner handles from earlier navigations remain strong**. The tracked old
handles were explicitly weakened or released. This establishes that these cleanup
paths work in the observed captures. All four have the low-retention profile;
they do **not** identify the owner of extra contexts in the previous failed run.
No supported correction or passing native/application calibration follows.

## Observed lifecycle

| Slot | Instrumentation | Nodes stage 6 / stage 11 | Old known strong handles at GC 6 / GC 11 |
| --- | --- | ---: | ---: |
| 0 | journal only | 9,007 / 6,008 | 0 / 0 |
| 1 | journal + membership | 9,007 / 6,008 | 0 / 0 |
| 2 | journal + membership | 9,007 / 6,008 | 0 / 0 |
| 3 | journal only | 9,007 / 6,008 | 0 / 0 |

The journal-only slots are instrumented diagnostics, not uninjected controls.
Each slot records 24 ScriptState and V8PerContextData constructions, 24 context
disposals, 48 extension-context invalidations, 3,528 scoped global creations,
3,234 matched releases and 46 explicit weak operations. DevTools reports 28 context
creations and 26 context-clear events; individual context-destroyed events are
absent. Native disposal observations are therefore necessary; do not invent missing
DevTools destruction records or equate clear events with one context apiece.

The source-audited first creation per owner identifies 120 context-handle generations
per slot. At the final export their states are:

| Owner handle | Released | Weak | Strong |
| --- | ---: | ---: | ---: |
| ScriptState::context_ | 22 | 2 | 0 |
| V8PerContextData::context_ | 22 | 0 | 2 |
| gin::ContextHolder::context_ | 22 | 0 | 2 |
| extensions::ScriptContext::v8_context_ | 44 | 0 | 4 |

At GC stages 6 and 11, the eight known strong handles all belong to that current
navigation: two V8PerContextData, two gin holders and four extension-context handles.
Multiple handles can refer to the same context: **eight handles is not eight
contexts**. Weakening is an observed operation, not proof of collectability. Owners
that predate attachment and unrelated root classes remain outside this coverage.
Tagged object values/local argument cells are not identities across a moving GC.

## Measurement integrity and limits

The original lifecycle v12 runner, fixture documents and membership recorder are
unchanged. No new page JS evaluation, snapshot, GC request, memory dump, cache
flush or wait is introduced. A separately attached journal records native owner
scopes, handle operations and GC epilogues; a Runtime subscription records metadata.
Probe traces retain two natural major collections. No forced-GC markers are present.

The only data dereference is a live MakeWeak(Address**) argument cell for its slot
address; no V8 object or owner field is read or modified. Function offsets/ABI are
checked against the exact ELF/debug symbols, source, disassembly and entry bytes.
Every argument/return value is copied synchronously. Scope/clock/sequence/generation
validation, zero drops/pending and source continuity checks pass in all four slots.

JS interception callbacks and the added Runtime subscription still perturb execution;
their cost is unqualified. These captures cannot establish what was retained during
application attempt5 or prove that instrumentation corrected it. No unchanged
rerun to seek a different retention outcome is justified. Original failed samples,
coverage, cost, stability and memory gates remain unchanged.

## Durable evidence

**47 local/cloud preflight tests pass.** Independent analysis of each raw journal
is exactly identical to cloud output. All **39** result-manifest hashes verify;
every archived source matches the frozen commit. The same-job native preflight
passes and independently re-audits identically. Unit tests cover missing weakening,
weak/released roots, reuse, invalid parents/generations, clocks, drops and identity.

Artifact **12777980663** is retained as
[journal-v1-evidence.zip](journal-v1-evidence.zip), SHA256
`18f0db1f93ed952a805f15e13c0887163cbe75a5e62acfebeddaa558ffbcacfb`.
The archive includes raw journals, traces, captures, setup/native-preflight logs,
inventory, frozen sources and all four slots. [Assessment](assessment.json),
[frozen protocol](PROTOCOL.md), reviewed workflow and ABI/source excerpts are committed.

## Native-buffer follow-up

[Native-buffer caller diagnostic](../native-handle-buffer/REPORT.md) completes all
four slots with 9,543 records each, including 1,011 unscoped births per slot. All 42
hashes and independent analyses/proofs match; 47 local/cloud tests pass. The one
older unreleased candidate resolves to V8's WeakFixedArray compilation queue,
not evidence of a strong document-retention path. All four again have low retention;
no supported correction or qualification follows. Read that report for next work.

## Next bounded work

The native-buffer follow-up above supersedes this historical next-step text.
Read its latest report before another capture.

The remaining evidence gap is a retaining root in a high-retention capture. Known
owner cleanup is observed here, but other roots are not covered. A supported next
diagnostic would record handle birth/release and native caller sites beyond these
owner initializers using a native buffer, avoiding per-event JS callbacks and the
extra Runtime subscription. Freeze and validate that distinct instrumentation before
any capture; do not repeat this journal unchanged or waive a prerequisite.

After a supported correction, fresh native qualification must pass before the
already-frozen lossless application transport can be measured. No product fix,
application attribution qualification or 2B memory acceptance is established.
No run remains active. Product cf363bf and isolated candidate cd94bf3 are unchanged;
PR #521 remains unmerged and reviewable. No candidate promotion, later increment,
merge or deployment occurred.
