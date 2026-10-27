# Native callback/buffer recorder — preflight before instrument or workload

Prior mixed getter lifecycle v11 d0eeb19 demonstrates representative source-labelled
reclamation in both probes but fails one cost bound, 5.2188% >5%. No unchanged rerun
or gate waiver. A concrete new recording-cost intervention moves timestamp/phase/
pointer/event capture from per-event JS callbacks to CModule callbacks and a fixed
native buffer. JS decodes/formats after sealing only. No product change or RSS claim.

Freeze before ONE preflight on exact Chromium 156.0.8078.47 / ELF
1c5dca8527a61d07372e489142bee26af1bcaf71, Frida 17.5.1, Linux x64. CModule uses ONLY
its internal toolchain, GUM's invocation API, system clock_gettime(CLOCK_MONOTONIC),
gettid and the loaded GLib mutex/thread functions. No kernel/permission/browser
policy/network change, external compiler or privileged fallback if unavailable.
The actual module path for mutex functions is retained; 16-byte aligned zeroed
storage supplies the system GLib GMutex ABI, proved under the configured runtime.

Record layout is exactly 72 bytes: six uint64 fields (begin/ready/end, backend,
address, native thread) and six uint32 fields (kind, phase ID/type/document/group,
null-return flag). Invocation state is separate GUM listener data. Pointer values
are copied as integer bits at native call boundaries; no element/page target is
dereferenced, and no recycled InvocationReturnValue wrapper is retained. Original
phase/count/overflow/null/identity/generation and time semantics must survive.

Native buffer capacity stays 50,000. Mutexes serialize phase/cursor state, append
and snapshot, without holding locks across intercepted application functions. A
snapshot copies complete committed records to separate native storage, records
capture-end clock, count/drop/active limit and unfinished invocations atomically.
An unfinished invocation makes the proof/capture fail, not silently disappear.
Later events are beyond an explicit capture end, never used for measured coverage.
Raw address strings are decoded only from the agent's OWN record storage afterward.
Injected buffer memory is diagnostic, never an acceptance RSS saving/subtraction.

Preflight mode installs NO live hooks and runs no fixture workload. It must:
- Compile with internal CModule and exactly match the 72-byte ABI.
- Return 20 native clock values inside their Python monotonic RPC brackets.
- Run four real native threads, 256 synthetic events each: all 1,024 immutable
  pointer/phase/time records unique and intact, four distinct native TIDs, no drops,
  no unfinished calls, snapshot clock in its host bracket. Phase ID/document pairs
  must remain coherent despite concurrent updates.
- Exercise the SAME bounded append path with active test limit 32 and four x17
  attempts: exactly 32 retained / 36 dropped. Production limit remains 50,000 and
  a test/reset RPC is forbidden when live hooks are installed. Preserve both full
  synthetic buffers before the next separately retained test resets its state.

The preflight process is distinct from future capability/calibration processes;
no fake event may enter a live history. Capture all results/errors and all native
metadata. A compile, clock, race, pointer, overflow or identity failure stops before
workload collection. No repeated unchanged preflight for a favourable result.

Only after preflight passes may a separately frozen exact receiver/page-generation
capability compare this recorder with known geometry identities and the existing
JS recorder. Then, only after equivalence passes, a new fixed four-slot mixed
calibration must keep identical documents/samples/waits, all-mode labelled natural
reclamation and <=5%/250ms/1.20/20% gates. No forced GC, snapshot/dump, cache flush,
extra pressure/dwell/work, heavy concurrent analysis, dropped sample or budget change.
No application workload, product fix, 2B acceptance, later increment or deployment.
