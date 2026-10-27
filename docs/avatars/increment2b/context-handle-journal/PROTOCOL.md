# Snapshot-free context/handle diagnostic v1

Freeze before one fixed four-slot capture. This follows the complete root-graph
diagnostic whose four slots all had the low-retention profile. Preserve that
archive and application attempt5's failed qualification. No unchanged rerun.

Question: in a retained-document capture, do source-audited context-owner handles
remain strong at natural GC, or have their owners already weakened/released them?

Use unchanged native lifecycle v12 documents,12 mounts,220ms waits,censuses and
counters. Observe Runtime context-created/destroyed/cleared metadata; do not retain
remote object handles or evaluate new JS. After original renderer identity proof,
attach a separate context journal. Fixed order is journal-only / journal+original
membership / journal+original membership / journal-only. The journal-only slots
are instrumented diagnostics, not uninjected controls. All four remain retained.

Exact Chromium ELF 1c5dca8527a61d07372e489142bee26af1bcaf71 offsets come from its
matching debug symbols and checked disassembly. Record constructor/dispose/dtor
scopes for ScriptState, V8PerContextData, gin::ContextHolder, and extensions::
ScriptContext; record GlobalHandles::Create, NodeSpace::Release and both MakeWeak
operations, plus Isolate::CheckDetachedContextsAfterGC. The first global creation
in each audited owner initializer is its context handle. Record every scoped
creation raw, including subsequent handles that receive no inferred context label.

Only one data read: the valid Address** API argument cell of MakeWeak(Address**),
read synchronously on entry for its handle-slot address. Never dereference a V8
object or owner field. Copy arguments/return values immediately as immutable
strings. Node::FromLocation is a cast (object field offset0); Release's static
arg0 therefore matches Create's returned handle slot. Reuse gets a fresh generation.
Validate entry bytes, exact build, PID, monotonic clock20 samples, complete event
sequence, balanced scopes, no drops/pending, matched transitions and no generation
overlap. Cap30000 events; any overflow/error makes diagnostic completeness fail.

ScriptState::DisposePerContextData inlines V8PerContextData::Dispose: destroy its
gin holder, reset event loop, make context_ phantom. extensions::ScriptContext::
Invalidate resets v8_context_. Checked source: Chromium156.0.8078.47; V8 revision
392e44423f46d75904da712fadea4c7d5d97967f. Keep source excerpts/hashes and ABI evidence.

Export once before Browser.close, after unchanged measurement/trace work. No
snapshot, GC request, forced-GC flag, object query, cache flush, memory dump or
extra wait. The journal's JS callbacks/CDP subscription still perturb execution;
its overhead is unqualified. No native/application qualification, acceptance,
source-attributed bytes, exclusive ownership or causal inference about earlier
runs follows. Missing bad-profile reproduction remains a limit, not a passing fix.

Offline reconstruct only known owner handle generations. At each GC epilogue,
report known strong handles and their creation stage, including old ones. Weak
means the audited explicit weakening occurred; it does not imply collectability.
Pre-attach owners, other roots and V8 object moves are unobserved. Raw local-handle
cells or tagged object values are not stable identities across GC. No favorable
replacement, automatic calibration, product change, merge or deployment follows.
