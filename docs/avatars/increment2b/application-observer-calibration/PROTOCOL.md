# Frozen real-application observer calibration v1

Scope: only current product cf363bfe547d5e23619eee28cdaf68bd4b6d7753, one warm-desktop
sample per fresh process. No original/candidate comparison, product change, forced
GC, cache flush, runtime budget waiver, 2B acceptance or later increment. The user
requests application-specific calibration after native instrument qualification.

Prerequisites: verify retained hosted native qualification artifact SHA
2c1de48749d1eefeb04782e2034879bf7392ce137bddb1b3a16f734159b25a0d and all its internal
hashes; independently reproduce its qualified audit. Require unchanged native agent,
exact Python 3.12.14/Playwright 1.62.0/Frida 17.5.1/Chromium 156.0.8078.47 ELF
1c5dca8527a61d07372e489142bee26af1bcaf71. Actual hosted CPU model, four visible CPUs,
Microsoft hypervisor and max quota must match the qualified resource condition.
Fresh native selftest on this host must pass before any application fixture runs.

Use full historical real HTTP baseline: eight scenarios at original 30-second
settings, 13 snapshots, all 20 forward home navigations and checkpoints 1/5/10/15/20.
Preserve actual auth/care/picker/preview behavior in the synthetic test DB with fixed
clock, cat, random seed, warm desktop, CPU rate 1. No production DB/user data/secrets.
Application/backend/template/JS source remains pinned cf363bf; copy only declared
test harness files into temporary product worktrees. Preserve all baseline outputs.

Native setup is explicit: all arms first load one tiny same-origin test-only empty
route, discover the actual renderer and verify BFCache launch policy. The fixture
route is removed afterward and does not change product routes/source. Probe/proof
arms attach the qualified native agent there, tracking allocation history throughout
all earlier scenarios to avoid assigning unknown pre-attachment pages as known.
Controls perform the same empty-route/identity setup without hooks. This is a new
instrument setup condition, not historical memory-acceptance replacement.

Before calibration: one full-workload real-app receiver proof. After the eighth
baseline snapshot, select exactly one .oc-pet .avwrap[data-kind=cat] live home SVG;
first 32 SVG descendants. Other group: last 32 HTML body descendants outside any
.avwrap. Require >=32 pools; never lower the sample if the app is different. Match
128 native absent-namespace getter receivers against 128 independent native geometry
references, repeated/disjoint groups, real element tags/namespaces and known query
brackets. Require actual native null returns. Snapshot selected attribute STRINGS
through getAttributeNames/getAttribute within each synchronous query, unchanged
before/after; do not iterate NamedNodeMap or materialize existing Attr nodes.
Geometry reference work is proof-only and absent in calibration. Type vectors from
this actual app proof must match all later measured selections. Preserve full app
workload even in the proof; stop before calibration if the proof fails.

Then exactly four fresh same-source control/probe/probe/control full workloads, no
replacements. Observe only the 20 navigation mounts with four groups of 32 receiver
calls each (avatar/other, repeat0/1); query atomically before the unchanged 220ms wait.
Record phase arming/census/checkpoint brackets in all arms. Native callbacks are
active before navigation for allocation provenance; all captured native preparation,
including earlier scenarios, is conservatively charged against the navigation window.
Count complete census, phase-arming, all five existing baseline snapshot envelopes,
trace setup and native preparation, including preparation already inside census.
Identity/setup before workload is retained separately; no trace-transfer/export work
is hidden in the window. Full trace only for probes, 64MiB, deferred transfer after
end. No additional CPU sampler, forced collection or heap dump.

Unchanged qualification gates: <=5% conservative observation and <=250ms single
observation; <=20% same-source control variation and <=1.20 paired probe/control
navigation durations. Also require these stability/paired limits over complete
workload durations. Native ABI, clocks, immutable records, canary, no pending/drops,
exact 2560 measured native receiver calls per probe, repeated/disjoint identity,
positive known generation joins >=90% IN EACH group. Require measured labelled
returns for BOTH app groups in BOTH probes, with natural MajorGC/native sweeps and
trace coverage. Unknown lifetimes remain unknown; no post-window rescue or owned-
byte attribution. Groups are structural regions, not an exclusive CSS/script/heap
partition: outside-wrapper HTML may still contain avatar-related scripts/styles.

All original memory-budget and baseline-acceptance obligations remain. Only a full
pass may qualify this observer for a separately frozen application attribution
experiment. No RSS acceptance is inferred from injected measurements. Failures,
partial prerequisites and every attempted slot are retained with hashes. Freeze
code/policy/tests and exact workflow SHA before opening one new workflow-only PR;
opened-only trigger prevents documentation updates from rerunning measurements.
