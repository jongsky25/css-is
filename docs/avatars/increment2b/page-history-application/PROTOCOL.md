# Bounded native page history on the unchanged application workload

Prerequisite: fixed synthetic v1 capability and four-arm synthetic overhead gate
passed. Candidate product stays cf363bf; original 1c964dc. Freeze harness before
measurement. No new product code, forced GC, heap snapshot, detailed memory dump,
cache flush, pressure notification or permission/kernel changes.

Run four NEW current control/probe/probe/control slots, ordinal 0, fresh process,
synthetic fixture DB and Chromium 156.0.8078.47 per slot, full 30-second warm-desktop
baseline unchanged. After background snapshot, every arm performs a bounded console
TimeStamp identity trace and verifies exact ELF build. It stops/exports before the
navigation clock begins. Probe arms attach the validated Frida normal-page request/
return hooks; controls do not. Capture every native event through sealed navigation
20, retain the original 13 snapshots verbatim, record all twenty goto brackets.
Phase marker RPC costs are INSIDE the application navigation window in probe arms.
History export, detach and gzip occur after the sealed window. No allocator dump
or GC trace runs in the measured navigation interval. There is no polling reader.

Gates stay <=20% first/final control variation, <=20% probe/control duration in both
orders, <=5% summed explicit callback preparation/navigation duration, <=250ms
individual preparation, no lost/overflow/agent-error records, verified source/
harness identity and complete workload. Callback preparation understates all
interceptor overhead, so paired duration checks are also mandatory. The agent
consumes renderer memory; injected RSS is NOT acceptance or a valid saving estimate.

Only if the complete application calibration passes, run eight NEW original/current/
current/original then current/original/original/current probe slots (ordinals 0/1),
same frozen harness, calibration audit hash recorded. Retain every scheduled result;
no replacements, excluded slots or relaxed thresholds. Preserve all earlier failures.
Per-slot callback/integrity gates still apply. Analyze page request caller stacks,
address generations and return/reuse history; do not assign every object on a page
to the requesting stack. First-observed pages may predate attachment; normal-page
hooks exclude large pages and objects fitting existing allocation buffers.

The two normal-page hooks do not provide allocation site for every object, JS
retaining paths or historical contents of pages already pooled before attachment.
Source comparisons are diagnostic history only, never 2B acceptance. No 3A,
deployment or merge. Archive and independently re-audit completed schedules.
