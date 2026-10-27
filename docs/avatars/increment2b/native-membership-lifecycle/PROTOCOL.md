# Membership lifecycle v1 — disposition/collection discrimination only

Read native-element-membership/REPORT.md first. Both prior membership capabilities
fail through-reclamation coverage. This diagnostic neither reruns those experiments
unchanged nor waives their gates. It answers the explicit missing question: are
these documents entering history cache, shutting down without observed natural
collection, or undergoing collection without observed normal-page return?

## Evidence before collection

The locked Playwright launch switches in coreBundle.js include
--disable-back-forward-cache. The new run must record the effective boolean from
Browser.getBrowserCommandLine; it does not add/remove the flag or retain unrelated
possibly sensitive arguments. Runtime false fails the intended fixture policy.

Pinned Document::Shutdown emits the blink trace event Document::shutdown and stops
layout/style/frame state; shutdown is not GC or native page destruction. Pinned
sweeper.cc destroys a normal page only when its sweep result is empty and the policy
is kDestroy; partially occupied pages can remain, with free ranges optionally
discarded. NormalPage::Destroy calls PageBackend::FreeNormalPageMemory; source and
exact-build symbols/disassembly are retained. ReleasePooledPages removes already
pooled regions. A missing pool-return hook is not a proof that nothing was reclaimed.

## Fixed capture

Freeze this protocol, runner, hook and auditor before exactly four fresh-process
synthetic slots control/probe/probe/control. Same v2 twelve-document fixture: 4,096
paths per labelled SVG group; last 128 avatar paths and first 128 other paths,
twice, fixed DOM order. Same 220ms wait. Do not add documents, dwell, allocation
pressure or fixture geometry to obtain a collection. Exact Chromium 156.0.8078.47,
ELF 1c5dca8527a61d07372e489142bee26af1bcaf71 and Frida 17.5.1.

All arms receive a DOM-read-only pagehide listener recording document index and
persisted, a console.timeStamp marker, and a console debug record. No elements are
retained by telemetry. Expect the eleven departed fixture documents 0..10 exactly
once, persisted=false; fixture document 11 is still active at measurement end.
Browser shutdown occurs after export and is not evidence of in-window reclamation.

All arms bracket Runtime.getHeapUsage and Memory.getDOMCounters after each stage.
These sequential reads remain distinct; do not fabricate an atomic heap state.
Probes retain receiver/page hooks and add entry/exit hooks for Document::Shutdown
0x100208d0, NormalPage::Destroy 0x5aa4490 and ReleasePooledPages 0x5ab09d0. No native
memory is dereferenced. Entry alone is not proof a document was active on entry.

Probes record one 64MiB trace from before the first fixture navigation until sealed
navigation 12: devtools.timeline, blink, cppgc, disabled-by-default-cppgc and
disabled-by-default-v8.gc. Clock sync markers retain both host bounds. Trace setup
is inside total measured duration; transfer/compression/export occur after sealing.
No native dumps, forced GC, heap snapshots, cache flushing, pressure notifications,
privilege changes, concurrent heavy analysis or replaced slots.

## Integrity and diagnostic gates

Every scheduled slot and failure remains. All source/harness and file hashes,
build/renderer identity, every census/repeat and original live-membership coverage
must verify. Require all eleven pagehide records plus matching trace markers in
probes; native shutdown entries for each of twelve navigation phases (initial
empty document plus eleven fixture departures) and corresponding shutdown trace
coverage. No reported trace loss, forced-GC/dump event, agent error or dropped record.
Retain all native events outside the measured interval explicitly; they cannot
satisfy the measured membership/reclamation predicate.

Counters must map into the trace with conservative clock uncertainty. Preserve any
final-stage edge ambiguity; all earlier stage counters need full coverage. Report
all GC phases actually recorded for the identified app renderer, including zero.
An event-free window answers an observation question, not complete GC-instrument
coverage or a passed through-reclamation capability. Do not lower a prior gate.

Timing gates stay <=20% control duration variation, <=120% paired probe duration,
<=5% conservative observation bound and <=250ms individual observation. Bound sums
whole census intervals (including geometry and RPC), sequential counter calls,
trace setup and native callback preparation. Callback cost inside census intervals
is deliberately counted twice rather than favorably subtracted. Paired duration
checks cover unmeasured overhead too. Report every failure; no source comparison.

## Interpretation boundary

Keep the original membership qualification and errors alongside this independent
lifecycle result. It can report complete_lifecycle_diagnostic only if these integrity
and overhead checks pass; application_qualified and acceptance always stay false.
No pool return is needed to report its absence or zero recorded GC, and that absence
never becomes a qualified membership/reclamation instrument. No product fix, RSS
saving, 2B acceptance, 3A, merge or deployment follows from this diagnostic alone.
