# Lifecycle v3 — verify departing-document delivery before fixed capture

V2 (ee886ce) completed all four workload slots with the effective BFCache-disabled
flag true. Both probes captured all eleven pagehide(persisted=false) trace markers
and native shutdown calls, but the Playwright console callback delivered zero
pagehide records in every arm. V2 therefore fails its declared independent-delivery
gate; this failure is retained, not relabelled a pass. Its native timestamps also
show pool returns AFTER the sealed window, during trace transfer/export. Those
cannot satisfy the prior within-window reclamation requirement.

V3 replaces ONLY the departing-document message transport with CDP Runtime.addBinding
and Runtime.bindingCalled, installed before fixture navigation in all arms. The
read-only pagehide listener calls that binding; native-timeline timeStamp markers
remain. No network request, document retention, dwell, extra document, geometry,
GC, cache policy or release-hook change. Runtime.enable/addBinding happen before
measurement. Fixed total stage time still includes callback delivery work.

Freeze before an opt-in, two-document exact-browser transport capability test.
It requires exactly the known document 0 departure with persisted=false. If it
fails, no four-slot capture. If it passes, run exactly four NEW control/probe/probe/
control slots under the same frozen code. This transport check is separately
retained and never counted as a memory/control slot. All v1 fixture/coverage/timing
and interpretation boundaries stay, with the v2 read-only effective flag check.

Every full slot must still deliver all eleven pagehide records before sealing;
probes must independently match all trace markers and native shutdown coverage.
All original membership/reclamation failures remain separate. Natural GC may be
absent as an observation result; application_qualified and acceptance remain false.
All v1 setup failures, v2 delivery failures, new test and all v3 samples stay.
No unchanged rerun, forced GC, longer window, application collection or product fix.
