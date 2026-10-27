# Lifecycle discrimination — labelled pages reclaimed naturally, diagnostic still fails gates

**2B remains blocked.** The latest fixed four-slot experiment observes natural major
GC, native sweeping and ten previously labelled normal-page generations returning
to the pool in one probe. The other probe records no collection or return during
its measured window. Both retain exact sampled receiver identities. Overhead and
control-stability gates still fail, so no application comparison or product fix is
qualified. All original memory budgets/failures remain. No 3A, merge or deployment.

## Source inspection resolves the next diagnostic question

Playwright's pinned launcher includes --disable-back-forward-cache. Runtime checks
confirm that flag in every completed slot, reading only its boolean presence from
the known launched browser's /proc command line. No flags or policy were changed.
The previously proposed history-cache explanation is not supported for this fixture.

Pinned Document::Shutdown stops frame/layout/style state; it is not object GC.
Pinned sweeper.cc destroys a normal page only when empty and configured to destroy
empty pages. Partly occupied pages can remain while free ranges are discarded.
NormalPage::Destroy routes to PageBackend::FreeNormalPageMemory; releasing pooled
regions is a later path. Exact source, symbols, disassembly, checksums and launcher
excerpt are in `source/`. This explains why shutdown, collection, pool return and
OS release must be separate observations, not interchangeable conclusions.

The diagnostic keeps the same twelve documents and 4,096 SVG paths per fixture
group. It adds independently corroborated pagehide delivery, native shutdown and
release hooks, natural-GC tracing, and separately timestamped heap/DOM counters.
It never forces GC, snapshots a heap, dumps native allocators, flushes caches,
adds dwell/documents, changes browser policy or runs heavy concurrent analysis.

## Every attempt retained

Each revision was frozen before collection. Failed slots/tests were not replaced.
The revisions address observed setup, delivery or cost failures; none changes a
2B memory gate or accepts an earlier failed experiment.

| Revision | Frozen harness | Scheduled result |
|---|---|---|
| v1 | 18d3eaa | All four processes stop before workload: Browser.getBrowserCommandLine requires absent --enable-automation. Full setup failures retained. |
| v2 | ee886ce | Four full slots; /proc verifies effective flag. Probe traces have all eleven false-persisted pagehide markers, but Playwright console delivers zero records in every arm. Delivery gate fails. |
| v3 | b676607 | Two-document CDP-binding transport capability fails with zero departures delivered. No four-slot capture launched. |
| v4 | ef32149 | Same-origin beacon capability passes. Four full slots agree on all departures; all four exceed the conservative 5% observation bound. |
| v5 | 97bd66c | Four full slots batch identical census calls. Both probes and final control exceed 5%; control duration variation and first paired duration also fail. |
| v6 | 5364334 | Four full slots use an explicitly smaller fixed sample. Both probes exceed 5%; control variation and first paired duration fail. Natural source-labelled reclamation is observed in one probe only. |

V4's only new network traffic is eleven bounded same-origin beacons to the local
fixture server in every arm, carrying index/persisted only. It fixes departing-
document delivery without relying on an event channel already known to lose it.
V5 batches the identical four ordered group/repeat censuses into one evaluate and
one pair of native phase RPCs per document. Exact receiver counts/repeats detect
missing, shifted or extra native calls; overflow gets an explicit label.
V6 reduces the predeclared census from 128 to 32 paths per group, twice: 1,536
receiver records per probe. It still renders all 8,192 paths per document; it does
not claim coverage of the unselected elements. Thresholds remain unchanged.

All source hashes, samples, errors and protocols accompany the archives. The
original geometry-census capability remains independently evaluated; this lifecycle
result never waives its through-reclamation requirement.

## Latest v6 timing and integrity

Exact Chromium **156.0.8078.47**, ELF
**1c5dca8527a61d07372e489142bee26af1bcaf71**, Frida **17.5.1**. Four fresh processes,
control/probe/probe/control. Each completes twelve documents. Every arm receives
all eleven departed fixture documents (0–10), persisted=false, before sealing;
probes independently match all native-timeline pagehide markers. Last document 11
is still active when measurement seals. Both probes record 36 shutdown entries and
matching shutdown trace activity across all twelve navigation phases; extra internal
documents are not assigned to the main fixture by name or count alone.

| Slot | Mode | Duration ms | Conservative observation bound | Largest observation ms | Measured native return result |
|---|---|---:|---:|---:|---|
| 0 | control | 4055.694 | 3.545% | 16.235 | not injected |
| 1 | probe | 5215.486 | **6.687%** | 38.145 | 500 normal-page returns |
| 2 | probe | 4185.410 | **5.322%** | 18.586 | zero normal-page returns |
| 3 | control | 5226.617 | 4.865% | 53.435 | not injected |

Controls vary **28.871%** (limit 20%). Paired duration ratios are **1.28597 / 0.80079**
(limit 1.20). The 5% bound includes entire batched census work, both sequential
counter calls, trace setup and native callback preparation; preparation within a
batch is deliberately counted again rather than favorably subtracted. No cost
was removed from older audits to turn them into passes. All pauses stay <250ms.

Both probes match **1,536/1,536** declared receiver observations to captured page
generations, with exact repeats/disjoint identities, unchanged DOM, positive
coverage per census and 12 mixed-group generations. No reported trace loss, forced-
GC/dump event, dropped record, agent error or source/renderer mismatch. All counter
brackets and trace-edge uncertainties are retained. Every numerical gate failure
above remains explicit despite this capture integrity.

## Source-labelled reclamation observed in one probe

Slot 1 records one MajorGC, CppGC marking/weak processing/sweeping and 500 measured
normal-page pool-return calls. Ten returned generations had contained sampled
elements from fixture documents **0–9**. All ten return brackets overlap recorded
native sweep intervals with conservative clock bounds. The ten returns span about
4.744ms; no heap dump or forced collection was requested. This is the first retained
within-window link from these selected source-labelled elements to page return.

Sequential document counters progress 6,8,…,24, then **1 / 3** at the last two
stages; JS heap observations progress to 5.076MiB, then **1.502 / 1.183MiB**. MajorGC
reports its own before/after values in the trace; those are not the same instants
as the separately bracketed counters. The all-stage raw values and GC overlap
classifications are retained in `v6-native-periods.json.gz` and `v6-audit.json`.

Slot 2 finishes at **28 documents / 5.887MiB heap**, with no recorded major/native
GC or pool return during the window. Both controls also finish at 28 observed
documents; they do not carry GC traces. No conclusion about their complete event
history follows from counters alone. The differing collection histories are
observations, not permission to align/exclude checkpoints or subtract memory.

Mixed generations contain members of both fixture groups, so neither group owns
all their bytes. Membership/page return does not identify every style/layout/text
object, a strong retaining path, an exclusive source owner, physical backing or
RSS saving. Outlined NormalPage::Destroy/ReleasePooledPages hooks record no calls;
500 FreeNormalPageMemory calls are observed, so those outlined hooks do not provide
complete destruction-path coverage (inlined/unobserved paths remain a limit).
This is not a proof that all possible page-release paths are covered.

## Post-window evidence stays separate

V2 and v4 also record many pool returns AFTER measurement seals, while tracing is
stopped/transferred and native export remains attached. V2's first returns start
291.763/317.520ms after sealing; both probes then have 13 previously labelled
returned generations. This is forensic evidence, not a passed within-window gate.
Its GC chronology is unavailable after the trace ends, so no event correlation is
invented. V5 has post-window returns in only one probe. V6 has no outside-window
native events in either probe; the 500 returns above occur inside its window.

The summary code classifies inside/before/after/straddling events separately, rejects
ambiguous page generations, and never converts post-window returns into measured
reclamation. A boundary-straddling return cannot pass the within-window predicate.

## Independent audit and validation

Five scheduled archives reconstruct and re-audit identically: v1 setup failures,
v2 delivery failures, v4/v5 overhead failures and v6. Full captures/traces, logs,
source/hook identities and all failed audits remain. V1 reconstructs 15 files;
each completed-workload archive reconstructs **21 files**. Each completed audit
verifies **14 source hashes** (six archived harness sources and eight runtime probe
hash checks) and **14 cohort files**, including both renderer identity traces and
native ready PIDs. Initial transport tests remain separately committed.

**34 focused unit tests pass**, existing Starlette deprecation warning only.
The beacon capability test passes; the earlier binding capability fails and remains
retained. Tests cover lost/missing/persisted pagehide records, unsupported transport,
trace/GC/dump integrity, unchanged prior reclamation failure, census batch brackets,
known receiver identity/reuse/ambiguity, and post-window/straddling return handling.
Source product files remain byte-identical to cf363bf. No application comparison,
new artwork, release acceptance, merge or deployment was performed.

## Next bounded decision

Do not rerun v6 unchanged or qualify application collection from its single
reclamation-positive probe. It fails overhead and controls. Existing 2B RSS and
lifecycle failures remain. The source review plus labelled returns now support
ordinary document shutdown followed by variably timed collection/reclamation for
this fixture; they do not select a product fix or explain all RSS capacity.

Next reduce the source-linked receiver observation's cost before another application
probe. Retained cost data locate the dominant work in the census, not merely the
heap/DOM reads. A concrete alternative to investigate in pinned source is a native
absent-attribute getter: unlike getClientRects, it may avoid layout flush/rectangle
allocation. Prove a separate exact native receiver hook/ABI and its absence/read-only
semantics on the controlled fixture before collection; do not assume an inlined
attribute method supplies a hook or assign pooled bytes to one group. Freeze any
changed instrument and all coverage/cost gates before running it. A failed prerequisite
stops application use. No next product correction is established yet.

## Reproduce offline

```sh
.venv/bin/python -m scripts.avatar_baseline.package_cat_gradients \
  docs/avatars/increment2b/native-membership-lifecycle/v6-evidence.zip \
  --unpack-to /tmp/membership-lifecycle-v6
.venv/bin/python -m scripts.avatar_baseline.analyze_membership_lifecycle \
  /tmp/membership-lifecycle-v6/calibration --ref 5364334 \
  --out /tmp/membership-lifecycle-v6-audit.json
.venv/bin/python -m scripts.avatar_baseline.summarize_membership_lifecycle \
  /tmp/membership-lifecycle-v6/calibration --ref 5364334 \
  --out /tmp/membership-lifecycle-v6-periods.json.gz
```

Compare JSON values for the gzip summary. Prior archive filenames/refs are in their
versioned protocols and manifests. No browser run is needed to reproduce audits.
