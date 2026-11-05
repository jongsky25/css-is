# System Health slowdown investigation — November 5, 2026

Read-only investigation at approximately 15:30–15:34 Asia/Manila. The owner
reported slowness and supplied the production `/ops` URL. No application fix,
restart, configuration change, release or production database download occurred.

## Observed production state

- Hosting API: RUNNING, CPU Basic, one replica. Writable bucket mounted at `/data`.
- Hosting source: `dcd268f6ca48b9baeda2cbf0c750503dd67889f3`.
- Hosted `build_info.json`: version 9.94, application source
  `bc8612d31496f3172df01a3127bddcb0234d6484`. Provenance comes from hosting
  metadata/source, not an authenticated rendered Operations page.
- Public `/health`: HTTP 200, app/database `ok`, uptime 14,057 seconds, 1,725
  requests. One probe took 337 ms including network/proxy overhead.
- `/login`: HTTP 200, 315 ms in one probe. Anonymous `/ops` redirected to login;
  its 555 ms measurement is the redirect/login flow, not Operations latency.
- Two bounded hosting runtime-log reads succeeded and ended on idle-stream
  timeouts. The first contained 3,986 lines and 1,775 parsed access records,
  with no parsed HTTP 5xx. The second contained 4,016 lines and no exact
  error-level, traceback, SQLite-lock, timeout or OOM matches. These overlapping
  samples are not independent/full-history coverage or CPU/memory measurements.
- Hosting access logs exposed no structured request-duration samples. Raw logs,
  user identities, addresses, private routes and record text were not published.

## Meaning of the warning

Deployed `monitoring.py` and relevant `app.py` code show that **Slow** means
five-minute p95 server request duration exceeds 1,000 ms. Samples come from a
rolling buffer of at most 2,000 requests, including assets, redirects, telemetry
and monitoring requests. This is not browser full-page load time. The card says
"9 in 10" although the calculation is p95. With no recent samples, the duration
defaults to zero; a Fast label then does not establish measured performance.

Headroom is inferred from concurrent requests (Getting busy above four), not
measured CPU, memory or disk capacity. Public health only checks basic app/DB
availability; it cannot rule out slow authenticated handlers or intermittent stalls.

## Source-supported candidates, not confirmed root causes

1. **Operations refresh does potentially expensive work.** Every `/ops` GET calls
   `backups.status`, which lists scheduled snapshots and checks file metadata on
   the bucket mount. It also calls `storage.audit_health`, which loads and hashes
   the complete audit table, then computes usage/inventory queries. Remote file
   metadata latency or growing audit history could make this page slow. Actual
   call durations and current record counts were not measured. The request is
   recorded after the snapshot is taken, so its latency enters later snapshots.
2. **Shared signed-in request overhead.** The async authentication middleware
   performs synchronous session/navigation/notification/authority DB reads before
   dispatch. Slow DB work can block the event loop and affect unrelated requests.
   This architecture is present; live blocking/lock contention was not observed.
3. **Historical intermittent calendar latency.** The November 4 UX review recorded
   calendar median load 622 ms/p90 3,151 ms and detail median 785 ms/p90 7,409 ms.
   Those mixed-version historical browser samples do not establish a 9.94 cause.

The deployed monitoring/storage/backups files were compared with the workspace
and match byte-for-byte. Hosted app.py differs in five unrelated event-management
permission calls; the inspected monitoring/Operations/authentication sections
match. No stale local implementation was assumed to represent the whole release.

## Next diagnostic step

The admin browser session is unavailable here. The owner was asked to copy the
Speed, How busy, Reliability and Headroom readings. Obtain a contemporaneous
authenticated five-minute per-route timing sample (or redacted local request-log
summary), then time backup enumeration, audit verification and shared auth work
separately. The current plain dashboard does not render its internal route table.
Do not choose a hardware upgrade or weaken audit checks without that evidence.

No application tests were run: this is a read-only assessment and documentation
change. Verification is live availability/provenance checks, bounded redacted
log analysis, deployed-source comparison and documentation whitespace/link checks.
Saved branch: `docs/system-slowness-diagnosis-2026-11-05`; no PR or deployment.
