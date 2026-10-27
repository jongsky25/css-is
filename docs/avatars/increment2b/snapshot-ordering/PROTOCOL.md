# Component-order diagnostic v1 — current-only calibration

Question: can the natural-GC position of the existing RSS/proc/heap/DOM reads be
observed at navigation 5 and 10 without the prior rotation gap or intrusive native
dump? The latest uninjected cat-gradient archive has no event timestamps. Its
40 navigation samples and 32 adjacent transitions are first re-audited offline;
all original gates remain unchanged. A source-specific allocation owner cannot
be inferred from this archive or from this proposed timing diagnostic.

Freeze this protocol, harness and auditor before collection. Run exactly four
fresh-process/current cf363bf slots, control/probe/probe/control, one complete
30-second warm-desktop workload each, ordinal zero. Exact Chromium 156.0.8078.47,
ELF build 1c5dca8527a61d07372e489142bee26af1bcaf71; same locked dependencies.
No product changes, replaced samples, forced GC, cache flushing, memory-pressure
notification, injected allocator hooks, native dumps, heap snapshots, polling
thread or concurrent heavy analysis. The host environment is recorded: this is
new diagnostic evidence, never replacement acceptance evidence.

All 13 original snapshots and all 20 navigations remain. Probe slots bracket each
existing Page.evaluate, CDPSession.send and /proc status/smaps read during a
snapshot with host monotonic timestamps, preserving call order and return values.
Controls retain overall snapshot/navigation brackets only. A single 64MiB trace
covers navigation, starting after the background snapshot and stopping after
sealed navigation 20. Categories are the previously used devtools.timeline,
cppgc, disabled-by-default-cppgc and disabled-by-default-v8.gc. There is no
navigation-10 rotation. Trace transfer and compression occur after measurement.
Clock-marker requests at the trace edges retain both host bounds; no exact
midpoint clock is assumed. Trace setup is inside the navigation timing window.

Every capture must preserve all scenario and navigation snapshots byte-equivalent
as JSON values, valid renderer census, frozen source/probe identities and all file
hashes. Probe calls must match the exact existing request/read inventory in order;
no additional browser request or /proc read is permitted inside a snapshot. Both
probes need an unambiguous app renderer, no trace loss/forced-GC/dump event, observed
natural major collection and native sweep activity, and full conservative trace
coverage of every component at navigation 5 and 10. No event observation does not
prove whole-heap sweep completion or strong reachability.

Calibration gates: <=20% first/final control duration variation; probe duration
<=120% of its adjacent control in both orders; <=250ms maximum observation pause;
<=5% total observation pause/navigation duration in every slot. The latter two
use the entire five navigation snapshots plus trace setup as a conservative
instrumentation-cost bound, including original observation work. They do not
subtract original costs to obtain a more favorable result. All scheduled slots
are retained if any fails; never replace a failing or collection-free slot.

If calibration fails, stop source comparison and retain all results. If it passes,
independently audit and interpret component ordering before freezing any further
source comparison; none is automatically launched by this runner. A future
comparison would need a separate committed protocol and qualified calibration.
No RSS pass, product correction, 2B acceptance or later-increment advancement can
follow from calibration. Ownership of page allocations still requires separate
source-linked evidence; this diagnostic addresses timing ambiguity only.
