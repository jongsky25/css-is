# Native-buffer handle/caller diagnostic v1

Freeze before capture. Prior context journal2c898c6 completes all four slots with
low retention, known context cleanup observed, but other root owners uncovered.
This changes instrumentation and coverage; it is not an unchanged favorable rerun.

Use the same lifecycle v12 runner/documents/censuses/counters/12 mounts/220ms waits.
Fixed order: buffer-only / buffer+original membership / buffer+original membership /
buffer-only. Every slot is instrumented diagnostic evidence, never an uninjected
control or qualification sample. Keep the original membership C agent unchanged.

Remove per-event JS callbacks and the added Runtime subscription. A separate
CModule records all observed GlobalHandles::Create/NodeSpace::Release/MakeWeak
entries, not just births nested in known owners, and the same source-audited owner
scopes/GC epilogues. Add native caller return PCs; validate a positive known call
at per-context constructor offset0xfd4bb86 against the matching ELF/disassembly.
All callback records are immutable native values; JS decodes only after the window.
No V8 API, object query, snapshot, collection request, memory dump, extra wait,
cache flush, product change or automatic application/native calibration.

Owned RW buffer,72-byte ABI,50000 records, mutex-protected append and deferred
snapshot. Preserve ready/begin/end times, raw API arguments/return slots, thread,
caller PC and entry serial. Sole data read is the live MakeWeak(Address**) argument
cell. No V8 object/owner field reads. Before all measurements, prove this new native
buffer's two-way storage canary,20 clock samples,1024 immutable records on four
threads and explicit overflow32 stored/36 dropped. A failed preflight stops before
workloads. No drops/pending/serial holes or overlapping handle generations allowed.

Reuse exact Chromium ELF1c5dca8527a61d07372e489142bee26af1bcaf71 and previous
context-journal ABI/source evidence. NodeSpace::Release is static with arg0 equal
to the handle slot (Node::FromLocation is a cast). Decode caller PCs relative to
this exact image only; outside-image PCs stay unresolved. Constructors identify
only their source-audited first context-handle creation. Other scoped/unscoped
births retain caller sites and raw evidence without assigning target types.

Reconstruct observed slot generations using creation/transition completion times.
At each GC epilogue, retain ALL older unreleased candidates, including previously
weakened ones; separately list those without observed weakening. Inlined release/
weak transitions and weakness restoration may be unobserved. Candidate handles
are not a census of strong roots; absence claims about other roots are prohibited.
Pre-attach roots are unknown. Slot addresses track handle generations, not V8
object identity across compaction. Caller sites identify creation code, not root
ownership, retained bytes, or the reason for an earlier failure.

Archive all slots/raw buffers/traces, proof, source hashes and failures. Re-audit
proof and every raw slot independently. Resolve caller addresses offline using
matching debug symbols. No substituted slot, favorable unchanged rerun, source
cleanup patch, qualification,2B acceptance, merge or deployment follows automatically.
Buffer allocation/hooks still perturb execution; lower per-event JS activity is
an implementation fact, not a qualified cost or proof that GC behavior is unchanged.
