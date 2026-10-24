# A25 capacity and recovery assessment — v8.29

## Decision

**Retain the current single-writer SQLite deployment for now.** This local run shows that the corrected code can complete a mixed read/write workload at a response count close to the older recorded 35,808-response office copy, and that an isolated backup restores correctly. It does **not** establish a production capacity envelope or justify a database/hosting migration. The next operational gate is a hosted measurement using real traffic, storage and queue metadata without copying private content into benchmark artifacts.

The immediate engineering risk is the memory and time required by large reporting workloads. The synthetic 35,000-response run peaked at about 1.31 GiB RSS and a Type-1 Word export took 7.94 seconds. The peak was already about 1.13 GiB before the export. Compare those values against the actual instance memory and concurrent export frequency before setting a safe operating limit. Do not add replicas while the SQLite writer and in-process caches have not been evaluated across processes.

## Reproduce the local rehearsal

```sh
python scripts/assess_capacity.py --responses 35000 --concurrency 4 --requests-per-worker 12 --output /tmp/a25.json
```

The command builds a new temporary SQLite database containing only synthetic survey rows. It runs the current app through one in-process ASGI loop, then removes the database and backup files. JSON contains aggregate timings and system details only. The defaults (`1,000` responses, four concurrent readers) are a quick diagnostic, not a capacity claim. Use the same Python, dependency lock and parameters when comparing revisions; run more repetitions and report distribution ranges before setting service targets.

The harness measures full atom refresh, cold and warm dashboard, health, committed survey writes, event-loop heartbeat lag, Type-1 Word export, four concurrent first-use schema checks, a controlled 100 ms SQLite writer hold, document-job state counts, local snapshot and restore, CPU and peak RSS. The restore deliberately adds one post-snapshot write and verifies that restoration returns to the saved count with `PRAGMA integrity_check = ok`. A missing job-age result is explicit: no synthetic document job was queued.

## Evidence from this workspace, October 24, 2026

Linux x86_64, Python 3.12.14, SQLite 3.53.1; 35,000 generated responses, 315,000 generated answers, 14.5 MB SQLite main file; four readers, 12 requests each, 12 committed writes. Numbers are one run and should be treated as diagnostic samples, especially p95/p99 from 12–24 observations.

| Observation | Result |
| --- | ---: |
| Full atoms refresh | 1.81 s p50 (2 samples) |
| Cold first dashboard | 2.72 s |
| Concurrent dashboard | 411 ms p50, 577 ms p95 (24 samples) |
| Concurrent health | 192 ms p50, 345 ms p95 (24 samples) |
| Committed survey write | 24 ms p50, 36 ms p95 (12 samples) |
| HTTP/read/write errors | 0 in this run |
| Event-loop heartbeat lag | 7 ms p50, 146 ms p95 (75 samples) |
| Type-1 Word export | 7.94 s, HTTP 200 |
| Peak process RSS | 1.31 GiB (1.13 GiB before export) |
| Four concurrent first-use checks | 0 errors; 19 ms maximum |
| Injected 100 ms writer hold | waiting write completed in 106 ms, below 5 s busy timeout |
| Local snapshot / restore | 13 ms / 38 ms; 35,013 responses reconciled; integrity OK |

The first run found an actual defect: a full-office walk-in export bound all response IDs into one `IN` query and failed with `too many SQL variables`. v8.29 batches related answer/remark lookups in groups of 500. A regression over 1,100 responses and the same 35,000-response export now pass.

## What remains unmeasured

- Hosted p50/p95/p99 latency, error rate, CPU/RSS, event-loop lag and SQLite lock waits during real concurrent workflows. In-process ASGI omits network, host limits and provider latency.
- Real document queue age and external-operation recovery. No synthetic document jobs were enqueued, and there were no provider calls.
- Hosted bucket snapshot lag, cold restart, restored sessions/integrations, and failure during a write. The local temporary disk is not the production bucket, so 13/38 ms do not establish recovery objectives.
- Staff mix, peak concurrency, export frequency and data growth. The synthetic rows have one survey type, nine ratings per response, no attachments and no representative document workload.

## Hosted decision gate, when live measurement is available

1. Record deployment SHA/version, host memory/CPU limit, DB and attachment sizes, snapshot destination, current queue depths and oldest pending age. Record aggregate metadata only.
2. Sample normal and peak traffic by route: request counts, p50/p95/p99, 5xx, CPU/RSS, event-loop lag, SQLite busy/lock waits, export/refresh duration and background queue age. Compare to the available host headroom and agreed user-facing objectives.
3. Restore a current snapshot into isolation, reconcile table counts and selected business totals, verify associated files and session/integration invalidation, and measure actual recovery time and snapshot lag. Agree the recovery-point and recovery-time objectives with the owner before declaring a pass.
4. Rehearse a clean restart and concurrent first-use requests on the actual deployment topology. Check that background jobs resume once and external receipts reconcile without duplicate effects.
5. Keep SQLite if the measured envelope has headroom and recovery meets agreed objectives. Consider a separate durable worker for queue pressure, a bounded reporting path for memory/latency pressure, and PostgreSQL only for sustained writer contention or a genuine multi-writer requirement. Any migration gets its own reconciliation and rollback plan.

No production benchmark or live recovery claim is made by this release.
