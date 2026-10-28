# Prepared design: minimal navigation-disposal witness

Design only. No collector implementation or new capture has run. Implement and
freeze source/protocol/ABI preflight before any measurement. This is the specific
observability gap established by the offline audit, not a supported product fix.

Question: when the high-retention state occurs, does navigation reach the ordinary
proxy-disposal path, complete ScriptState cleanup, and notify V8 before marking?

Observe only four exact-build function entries/exits with native C callbacks:

| Function | ELF offset | Entry data to copy |
| --- | --- | --- |
| LocalWindowProxy::DisposeContext | 0xef965e0 | opaque this, next Lifecycle (low32 arg1), FrameReuseStatus (low32 arg2) |
| ScriptState::DisposePerContextData | 0xfd46800 | opaque this and native caller |
| v8::Isolate::ContextDisposedNotification(bool) | 0x4fde210 | opaque isolate, dependent-context bool |
| Isolate::CheckDetachedContextsAfterGC | 0x51184b0 | opaque isolate, native GC boundary |

Matching ELF/debug symbols and entry disassembly are preserved under source/.
Build ID remains 1c5dca8527a61d07372e489142bee26af1bcaf71. Linux x64 argument ABI
and immutable scalar copies require fresh validation. Read no owner fields, V8
objects or API pointer cells. Keep per-thread call nesting and generation-aware
opaque addresses; pointer equality is not document/receiver ownership.

Source navigation requests Lifecycle::kGlobalObjectIsDetached (enum 3) and
kFrameWillBeReused (enum 1). For an initialized context, DisposeContext calls
WillReleaseScriptContext, debugger notification, global detach, ScriptState cleanup,
then V8 context-disposal notification. Other lifecycle branches may return early.
Without reading current lifecycle, missing nested calls mean an ambiguous path,
not proof of a cleanup bug. Notification on main frames maps to no-dependants;
Linux notification permits later GC and does not guarantee immediate collection.

Use an owned native buffer with no per-event JS callbacks, all-global-handle hooks,
Runtime subscription, snapshot, V8 API invocation, GC request, extra workload wait
or per-navigation RPC. Validate buffer canary, clock, concurrency, overflow,
call-site/argument witnesses, complete records and scope nesting. Put 20 clock
proof samples in a separate preflight; avoid a repeated per-slot startup RPC loop.
Capture the unchanged workload and all declared slots. If the failed state is absent,
state that limit; if cleanup completes in the failed state, investigate retaining
edges rather than inventing a disposal patch.

This must remain diagnostic only. Original failed samples/gates remain unchanged.
No qualification, memory acceptance, candidate promotion, merge or deployment follows.
