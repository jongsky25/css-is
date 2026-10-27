# Native root diagnostic: complete, failed retaining root still unknown

[Cloud run 40596878155](https://github.com/jongsky25/css-is/actions/runs/40596878155),
[PR #520](https://github.com/jongsky25/css-is/pull/520).
Frozen harness **2a1f2f43c1e6812abebb2e290e98cec3cff06356**, workflow
**85356907ea7725314ac027cb327f8837e2b8adac**.

One fixed control/probe/probe/control root diagnostic completes all four slots.
Each graph is written after the first natural major GC. All four show the
low-retention profile, so **none identifies the extra retaining root from the
previous failed native qualification**. No supported correction has been established.
This is perturbed diagnostic evidence; it does not qualify native/application
measurement or accept product memory. Application transport remains unmeasured.

## What the previous trace establishes

[Prior trace analysis](prior-trace-analysis.json) rechecks all 145 hashes of
application attempt 5 before reading its counters and V8 trace statistics.

| Previous slot | Mode | Nodes at stage 6 | Nodes at stage 11 | Outcome |
| --- | --- | ---: | ---: | --- |
| 0 | control | 9,007 | 6,008 | low-retention profile |
| 1 | probe | 45,063 | 72,120 | no labelled page returns |
| 2 | probe | 9,007 | 6,008 | ten labelled returns |
| 3 | control | 45,063 | 72,120 | retained-document profile |

The retained-document profile occurs without native hooks. Thus a recorder-only
cause is insufficient. The passing probe returns selected pages during its FIRST
GC, so a universal requirement for a second GC is also insufficient. First-major
V8 statistics show **11 versus 3 marked JS global proxies**, with used heap after
GC **2,501,964 versus 756,936 bytes** (failed/passing probes). Exact-version V8 source
confirms mark.js_global_proxies counts marked objects, not a duration or root path.
These differences locate the missing evidence in context/root retention; they do
not identify its owner or establish the cause of product RSS failures.

## New graphs and their limits

| Slot | Mode | Graph nodes | Native contexts | Nodes at stage 6 | Nodes at stage 11 |
| --- | --- | ---: | ---: | ---: | ---: |
| 0 | control | 151,199 | 3 | 9,007 | 6,008 |
| 1 | probe | 151,180 | 3 | 9,007 | 6,008 |
| 2 | probe | 152,140 | 3 | 9,007 | 6,008 |
| 3 | control | 151,845 | 3 | 9,007 | 6,008 |

All four graphs contain one native HTMLDocument and three native contexts.
Strong paths, excluding weak references and display shortcuts, go through global
handles: two V8PerContextData::context_ handles and one
extensions::ScriptContext::v8_context_ handle. These are references in the
low-retention captures. Their presence is **not evidence that any one of those
classes retained old contexts in the failed run**. All raw graph targets and paths
remain in the archive for review; presentation shortcut paths cannot establish
retention. Probe traces each contain two natural major collections, no forced
collection markers and no memory-dump events.

Pinned Chromium source maps to V8 revision 392e44423f46d75904da712fadea4c7d5d97967f.
Its heap-snapshot-on-gc=1 path invokes GenerateSnapshotAfterGC after a normal major
collection, avoiding the ordinary snapshot API's CollectAllAvailableGarbage.
It still makes the V8 heap iterable, finishes some sweeping, and pauses execution
to build/serialize the graph. Consequently its timing, natural GC schedule and
reclamation results cannot replace the original failed samples or qualify the
unchanged instrument. All four showing the low-retention profile does not prove
that the snapshot fixed retention; a timing effect and ordinary variation remain
unresolved. No unchanged graph rerun is justified to seek a different outcome.

## Validation and durable evidence

**43 local/cloud preflight tests pass.** The same-job native selftest passes and
its independent audit matches. All **42** result-manifest hashes verify; every
frozen harness source matches its commit. Independent decoding/path analysis of
all four raw graphs is exactly identical to the cloud output. The schema tests
cover reordered fields, cycles, weak/shortcut exclusion and malformed indices.

Artifact **12776532037** is retained as
[diagnostic-v1-evidence.zip](diagnostic-v1-evidence.zip), SHA256
`22f3159ba0415cb281d5617141d4c55d4d5ad4e65f43d8c4966ea41c83b5b14c`.
The ZIP also preserves the native preflight and setup logs outside the 42-file
result manifest. [Assessment](assessment.json), [frozen protocol](PROTOCOL.md),
[reviewed workflow](workflow-reviewed.yml) and pinned upstream excerpts/manifest
are committed. No source/sample substitution, forced GC, cache flush or added wait.

## Snapshot-free lifecycle follow-up

[Context handle journal](../context-handle-journal/REPORT.md) completes four fixed
captures without snapshots. At both GC checkpoints, no known context-owner handle
from an older navigation remains strong. All four show the low-retention profile,
so cleanup is confirmed only in those observed captures; the earlier retaining root
is still unknown. All 39 hashes and four independent analyses match; 47 local/cloud
preflight tests pass. No qualification or supported product correction follows.

## Next bounded work

The snapshot-free owner journal is complete; read its report first. The next
missing evidence is a retaining root in a high-retention capture. Broader handle
birth/release plus native caller-site recording with a native buffer could cover
other root owners while reducing callback/subscription effects. Freeze a distinct
bounded diagnostic before any capture. No unchanged rerun, forced collection or
prerequisite waiver. Original native/application qualification and 2B acceptance
remain unresolved.

No measurement remains active. PR #520 is reviewable and unmerged; PR #519 remains the
separate blocked application controller. Product cf363bf and unpromoted candidate
cd94bf3 remain byte-identical. No application comparison, 2B acceptance, later
increment, candidate promotion, merge or deployment occurred.
