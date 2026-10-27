# Reader candidate implemented; memory screen still fails

**Calibration passed, but 2B remains blocked.** Candidate `cf363bf` implements
safe connection reuse for session and appearance reads. Frozen harness `586f81c`
completed all four calibration slots and all eight comparison slots. No replacement,
exclusion, forced GC or threshold change. All captures pass integrity/overhead;
336 source/probe hashes and 110 files verify. Both extracted archives independently
reproduce the audits exactly (40 and 82 members).

## Product change and behavior

`sqlite_reader.py` owns one SQLite connection on one dedicated worker thread.
Only synchronous session/appearance read callbacks use it; each still queries
current data. SQLite retains its default same-thread enforcement, query_only
blocks writes, successful callbacks roll back any read transaction, and errors
close the handle. Path/inode changes and schema refresh invalidate reuse. Shutdown
rejects new submissions, drains accepted reads and closes on the owning thread.
Startup supports a fresh lifecycle. Writes and all four connection PRAGMAs remain
unchanged. No authentication or appearance result cache was introduced.

Sixty reads from eight caller threads open one connection in the ownership test.
Current committed values and session revocation remain visible. Behavioral checks
cover write rejection, callback failure, transaction cleanup, nesting, replacement,
refresh and shutdown/restart. Existing auth, appearance, backup and security suites
pass. Across the broad check and final additions, 220 distinct tests pass; the
separate opt-in scheduler attribution test is skipped. The final focused run is
23 passing tests. An initial command named a nonexistent scheduler test file;
that invocation error and the corrected results are preserved.

This candidate reduces a demonstrated setup cost but adds one worker and retained
connection. It does not change database contents or prove a renderer-memory saving.
Single-worker reads serialize; only the short, materialized read callbacks belong
there. No production deployment, merge, or later increment occurred.

## Calibration: all unchanged gates pass

| Slot | Mode | Navigation ms | Pause sum | Largest pause ms | Reader CPU |
| --- | --- | ---: | ---: | ---: | ---: |
| 0 | control | 7739.958 | ~0% | 0.001 | 0.635% |
| 1 | trace | 8276.598 | 2.660% | 200.555 | 0.464% |
| 2 | trace | 7929.726 | 2.231% | 154.484 | 0.447% |
| 3 | control | 7726.901 | ~0% | 0.001 | 0.483% |

Control duration varies 0.169%; paired trace increases are 6.93% and 2.62%.
Limits remain 20% for each, 5% pause sum, 250ms individual pause and 1% reader CPU.
No Python/V8 CPU profiler runs in these slots. This qualifies the capture protocol;
it is not a matched old/current latency experiment or proof the reader caused
control stability. Historical failed calibrations remain failed.

## Fixed memory comparison: failures preserved

Two blocks: original/candidate/candidate/original, then candidate/original/original/
candidate. Original `1c964dc`, candidate `cf363bf`; fresh process/database/browser,
full warm-desktop workload, ordinals 0/1. The candidate includes the current avatar
changes and backend reader change, so source effects cannot be assigned to one.
All eight workloads, all 24 trace segments and every per-slot overhead gate pass.

| Checks | RSS failures / checks | Heap failures / checks |
| --- | ---: | ---: |
| Original versus candidate | 10 / 52 | 0 / 52 |
| Same-source repeat controls | 16 / 52 | 0 / 52 |

All renderer counts match. Source failures are navigation checkpoints: forward
block 0 at mounts 1/5/10/15/20; reverse block 0 at mount 10; reverse block 1 at
5/10/15/20. Forward block 1 has no failure. Largest source delta is **+62.137 MiB**
at block 0 navigation 10. Largest same-source absolute delta is **60.488 MiB**
at candidate block 1 navigation 15. Controls also fail background/seasonal preview.
The 10MiB budget is unchanged. Complete_diagnostic means intact measurement,
not a passing memory screen or 2B acceptance. Unstable same-source controls prevent
causal interpretation of the source deltas; they do not waive any failure.

### What the newly qualified capture reveals

At navigation 15, candidate slots 4/7 have renderer RSS 551.609/491.121 MiB.
Status-read anonymous memory is 239.836/180.027 MiB (59.809 MiB difference);
file/shared differences are only 0.172/0.500 MiB. Status reads and the main RSS
sample are separately timed, so their small numerical discrepancy is retained.

Both live pages contain 1075 nodes, but CDP counters report 44/24 documents and
37044/31126 total nodes. JS heap goes the opposite way, 5.150/12.206 MiB. At the
later post-workload dump, Blink GC allocated size is 85.375/52.750 MiB. These are
separate observations: the endpoint dump is after navigation 20 and is not an
allocation breakdown of navigation 15. Do not sum nested allocator sizes or call
these counters a proven leak/owner. Counts decline naturally by navigation 20.

The remaining investigation should use these already captured navigation traces
to locate document/native-heap reclamation and reduce browser DOM/style allocation
only when ownership supports it. Further SQLite changes are not supported as an
RSS fix by this screen. Do not rerun unchanged for favorable samples or widen gates.
The reader remains an unpromoted candidate, not a solution to 2B.

## Reproduction and evidence

`PROTOCOL.md` records the schedule before measurements. `calibration.json` and
`comparison.json` retain all checks and raw-derived observations. Evidence ZIPs
include every slot, source manifests, frozen harness, runner logs and experiment
plan. Manifest files record archive/member hashes and identical re-audits.
`summary.json` is regenerated by `python docs/avatars/increment2b/sqlite-reader/summarize.py`.

Audit either extracted archive with:

```sh
.venv/bin/python -m scripts.avatar_baseline.analyze_navigation_light EXTRACTED \
  --harness-ref 586f81c --candidate-ref cf363bf --out audit.json
```

No measurement remains active. 3A and later stay paused.
