# Natural collection and retained native capacity explain part of the RSS variation

**Offline analysis completed; no new browser runs or product changes. 2B remains
blocked.** All eight qualified reader-comparison slots are included. The 82-member
archive is hash-verified, extracted and independently re-audited against the frozen
harness/source commits; the result exactly matches the preserved comparison audit.
The analysis retains every checkpoint, every adjacent status interval and every
observed GC epoch. Thirty focused tests pass.

## Largest same-source gap: collection occurs inside the snapshot

Candidate slot 4, navigation 15, reports 551.609 MiB total renderer RSS, 44 documents
and 5.150 MiB JS heap. Slot 7 reports 491.121 MiB, 24 documents and 12.206 MiB JS heap.
The app renderer accounts for approximately 60.352 MiB of the 60.488 MiB RSS gap;
its anonymous-memory difference is 60.012 MiB. Separate `/proc` reads and the main
RSS measurement are not simultaneous; their small discrepancy is preserved.

The trace now locates the important ordering within slot 4:

| Event | Milliseconds from conservative snapshot lower bound |
| --- | ---: |
| Snapshot lower bound | 0 |
| MajorGC starts | 17.205 |
| MajorGC ends | 31.817 |
| Snapshot upper bound | 75.322 |
| Last observed native sweep event ends | 132.636 |

MajorGC reports JS heap falling from 18.162 to 5.150 MiB. The recorded snapshot's
heap value matches that post-collection state, while native sweeping is still
observed **57.313ms after the snapshot's upper bound**. Its two adjacent status
intervals show anonymous-memory drops of 6.410 and 12.063 MiB overlapping that
sweeping. One interval's total RSS actually rises because shared RSS rises; total
RSS drops alone would miss this anonymous release.

`snapshot()` reads RSS, detailed process memory, JS heap and DOM counters
sequentially. Its aggregate record is not an atomic heap state. There are no
per-call timestamps to order each component against the GC precisely. The trace
does establish that V8 collection finishing does not imply native cleanup is done.
A low JS value with many documents and high RSS is therefore not proof of an
application reference leak. Do not relabel or discard this failing checkpoint.

## Every slot, not just the largest example

| Slot | Source | Observed major collections | Documents at mounts 1 / 5 / 10 / 15 / 20 | Endpoint Blink committed MiB | Endpoint pooled MiB |
| --- | --- | ---: | --- | ---: | ---: |
| 0 | original | 3 | 4 / 6 / 8 / 4 / 14 | 30.125 | 1.500 |
| 1 | candidate | 2 | 15 / 23 / 25 / 12 / 6 | 69.125 | 38.250 |
| 2 | candidate | 3 | 7 / 15 / 25 / 2 / 4 | 56.250 | 33.000 |
| 3 | original | 3 | 16 / 7 / 6 / 16 / 4 | 43.875 | 14.875 |
| 4 | candidate | 1 | 16 / 24 / 34 / 44 / 12 | 85.375 | 40.875 |
| 5 | original | 1 | 16 / 24 / 12 / 22 / 32 | 56.875 | 0 |
| 6 | original | 1 | 16 / 24 / 4 / 14 / 24 | 63.375 | 16.500 |
| 7 | candidate | 2 | 15 / 4 / 14 / 24 / 6 | 52.750 | 17.250 |

All 648 adjacent app-renderer status intervals are retained. Twelve show anonymous
RSS drops of at least 5MiB; eleven overlap actual CppGC sweep events. This is
correlation, not allocation ownership or a complete explanation of RSS. Thirty-one
status intervals cross conservative capture boundaries/gaps and receive no event
correlation. Six navigation-10 checkpoint envelopes straddle the trace edge;
they remain explicitly flagged, with no invented continuous history. A major
collection overlaps checkpoint bounds in slot 1/mount 10 and slot 4/mount 15.

Live-page node counts are fixed at 1038 for original and 1075 for candidate across
all five checkpoints. The extra total documents vary over time in both sources;
they are not growth of the currently attached page's node count. Slot 4 has no
observed major collection in its first trace segment and only one in the second.
The first navigation also carries objects from earlier workload scenarios; it is
not an empty-heap starting point. History in rotation gaps is unknown.

## Native capacity remains after collection

At the **post-navigation-20** dump, slot 4's Blink heap reports 85.375 MiB committed,
20.517 MiB allocated objects and 40.875 MiB pooled. Slot 7 reports 52.750, 11.386 and
17.250 MiB respectively. Thus different reported heap capacity persists even after
natural object reclamation. These fields are not an additive RSS decomposition;
allocated objects are not a proof of a fully reachable live set, and endpoint dumps
cannot be retroactively assigned to navigation 15.

The browser can collect objects without immediately returning all capacity to the
OS. Exact RSS ownership remains unavailable: these captures contain GC tasks and
one endpoint allocation dump, not per-checkpoint native stacks, memory maps or
retaining paths. Last observed sweep activity is explicitly **not** a claim of
whole-heap sweep completion.

## Fix decision and remaining blocker

No new application fix is justified by these traces alone. They support delayed
natural document cleanup and retained native capacity, not a specific avatar
closure, listener or SQLite connection retaining renderer pages. Adding another
cleanup handler, forcing GC, waiting for a favorable phase, subtracting pooled
memory or weakening the budget would not be an evidenced fix. The previous shared-
stylesheet candidate already failed its memory screen; this analysis does not
resurrect it as a proven solution.

The next concrete evidence needed is **which DOM/style/SVG allocations account
for the candidate's extra native capacity under natural collection**. Existing
native samples identified broad Blink/SVG sites but no owner of this capacity;
prior post-GC retaining-path captures missed the transient high-document state.
Another unchanged acceptance run or another post-GC snapshot would repeat those
gaps. A bounded native-allocation attribution probe must preserve the transient
state and pass its own overhead calibration before any new product reduction is
selected. Per-component snapshot timestamps would also remove the ordering
ambiguity exposed here, without changing or excluding any memory observation.

The existing 10 source RSS failures and 16 repeat-control RSS failures stand.
Reader code remains an unpromoted candidate. No later increment, merge, deployment,
forced GC or new measurement occurred. No process remains active.

## Reproduce

```sh
.venv/bin/python -m scripts.avatar_baseline.analyze_reader_retention \
  docs/avatars/increment2b/sqlite-reader \
  --out docs/avatars/increment2b/reader-retention/analysis.json.gz
.venv/bin/python docs/avatars/increment2b/reader-retention/summarize.py
```

`analysis.json.gz` contains the full all-slot result and source archive/audit hashes;
`summary.json` and its script reproduce the compact findings. `tests.txt` records
boundary/uncertainty, completion-versus-start, instant event, nested duration,
PID filtering, forced-GC rejection and trace-gap checks plus existing audit tests.
The first analyzer draft rejected Chromium instant (`ph=I`) GC events. They are
now retained explicitly as instants with zero interval duration; unsupported or
malformed duration events still fail. No capture was rerun or altered for this repair.
