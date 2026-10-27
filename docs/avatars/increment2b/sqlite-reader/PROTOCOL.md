# Thread-owned reader candidate: fixed validation schedule

Candidate product: cf363bfe547d5e23619eee28cdaf68bd4b6d7753 (initial implementation 62b9307) (based on current avatar product f700187). Reuse only
session_actor and appearance reads on one dedicated worker, query_only enabled,
no result caching, rollback after each callback, discard on error/path replacement,
close on application shutdown. Fresh writes and all four SQLite setup PRAGMAs stay.
One extra worker/connection may increase Python memory; renderer RSS remains a
separate gate. This is a candidate, not promotion or proof of avatar causality.

Before browser measurements: behavioral tests for ownership/reuse, live committed
updates, revocation, write rejection, rollback, failure, file replacement, refresh,
shutdown/restart; existing auth, appearance, backup and security suites. No profiler
in measurement slots. Product and harness commits frozen before launch.

Use existing navigation-light-v6 fixture, browser 156.0.8078.47, 30-second full
warm-desktop workload, fresh process/database/browser per slot, ordinal 0. Fixed
candidate control/trace/trace/control calibration. All gates unchanged: <=5%
explicit trace pauses; <=250ms individual pause; <=20% trace/control increase in
both orders; <=20% first/final control variation; <=1% scheduler-reader CPU.
No Yappi or V8 CPU sampling. Keep every slot/failure; no replacements.

Only if calibration passes, run the existing fixed eight-slot original/candidate/
candidate/original then candidate/original/original/candidate memory comparison,
ordinals 0/1, same frozen harness. Original is 1c964dc. The candidate includes the
backend read change as well as current avatars: this comparison is NOT attribution
of a renderer effect exclusively to avatars or the reader. Keep all 13 RSS/heap
checkpoints, source and same-source control pairs, 10MiB limits and renderer counts.
Do not substitute this diagnostic screen for complete 2B acceptance. If calibration
fails, stop comparison and preserve failure. No force-GC, cache flush, concurrent
heavy work, threshold change, 3A, deployment or merge.

The runner accepts an explicit candidate commit, retaining historical defaults.
Audit must independently receive the same candidate ref; a plan cannot authorize
its own source identities. Each slot adds backend-source.json with hashes of app,
appearance routes, storage and the reader when present, checked against Git along
with the existing avatar sources and frozen probe. Archive and re-audit all slots.
