# System Health performance diagnostics

Candidate 9.95, branch `feat/system-health-timings`, November 5, 2026.
The owner requested the next diagnostic step after reporting slow System Health
responses. This implements instrumentation; it is not a confirmed performance fix.

## Production evidence

The owner initially reported a 4.5-second speed reading. The subsequent screenshot,
at 15:47 Asia/Manila, showed 1.6 seconds, 46 requests in the last minute, 103
requests in five minutes with no server errors, one in-flight request, and a
47.9 MB database. These describe intermittent server latency. Low instantaneous
concurrency does not rule out an earlier burst or CPU/memory pressure.

The prior read-only assessment is saved on GitHub branch
`docs/system-slowness-diagnosis-2026-11-05`, commit `7cbd150`. Public health and
bounded hosting logs were available; an authenticated production admin browser
session was not. No root cause was established from those observations.

## Measurements

Administrator-only `/ops` includes an expandable Performance details panel.
The top 20 routes are ranked by slow-request count then p95, with request count,
count taking at least one second, median, p95, maximum and server errors. Methods
remain separate. Labels use matched framework templates; unmatched/early-denied
requests share a generic label. Mounted API routes retain their fixed `/api/v1`
prefix. The new labels do not contain raw identifiers or query strings.

Fixed operation timings cover session lookup, signed-in navigation/permission
reads, and health-page database connection, backup listing/status, full audit
verification, inventory counts, usage counts and Telegram queue status. Exceptions
are counted as failures without retaining their text. Existing call results and
exception behavior remain authoritative.

The new process-local buffers are capped at 2,000 samples each and filtered to
the last five minutes. They reset on restart. Operations can age out faster than
requests because each request measures several operations. No new per-operation
log or database write is introduced. Existing request logging remains unchanged.

The current refresh's completed operations appear immediately; its whole-request
measurement appears on the next refresh. Session timing includes the existing
thread dispatch/wait. These are wall-clock elapsed times, not CPU measurements.
Operations cover different requests and may overlap: their percentiles cannot be
added to reconstruct a request. The speed card describes 95th-percentile server
responses, replacing the inaccurate browser-load/"9 in 10" wording.

The aggregate JSON is embedded under `performance-data` on the authenticated admin
page for authorized extraction. It contains no actors, IPs, query strings, record
IDs or exception text. Public health exposes no diagnostics. Existing Operations
authorization remains in force.

## Verification

- Locked Python 3.11 cloud setup and doctor passed.
- Initial focused run: 98 tests passed in 39.69 seconds, no failures/skips.
- Final focused shuffled run (seed 311): 99 tests passed in 53.99 seconds,
  including the subsequent mounted-route test. No failures/skips.
- Coverage includes slow-route ranking, five-minute expiry, bounded buffers/reset,
  exception timing, safe route labels, query/ID redaction, public exclusion,
  authorization, and deterministic attribution of a synthetic 1.6-second audit
  delay to both audit and total health-page latency. Related auth, usage and
  persistence health tests are included. No production data was used.
- Release metadata 9.95, evaluation contract 1.12.0, dependency lock inputs and
  whitespace checks passed. Full exact-head CI remains required before release.

## Live collection after release

After an explicitly authorized release, use the app normally for a few minutes,
then open System Health → Performance details. Record sample counts and the
largest slow-route/operation values. Refresh once to include the preceding health
request. Compare backup/audit costs against ordinary routes and shared auth costs
before choosing an optimization. The synthetic delay validates attribution, not
a live root cause. Existing full CI and backup/version gates remain required.

## Production release verified — November 5, 2026

The owner explicitly authorized deployment after reviewing the effects.
[PR #585](https://github.com/jongsky25/css-is/pull/585) passed complete normal and
shuffled CI, dependency/metadata/aggregate gates and avatar acceptance on
`c043489de7c59396862967d2b676f67fb2ee95ff`, then merged as
`75a7eb494528156f4c73228937738238884151ed` at 16:49 Asia/Manila. Main's tree matches
the reviewed tree. No unresolved review threads or required approvals blocked
the merge; strict required-check rules were inspected again immediately before it.

[Production workflow 41997410104](https://github.com/jongsky25/css-is/actions/runs/41997410104)
completed successfully at 17:41 Asia/Manila. Its exact-main full normal/shuffled
suites, dependency audit, metadata and required aggregate checks all passed.
Deployment logs confirm a newly secured/integrity-verified backup, code-only
upload, no backup bypass, and the expected live login version. The workflow's
three authenticated Operations observations succeeded afterward. The initial
automatic-merge request was unsupported by repository configuration; the agent
waited and merged normally only after every PR gate passed, without changing
repository rules.

Fresh independent checks at approximately 17:42 Asia/Manila established:

- Hosting stage RUNNING on CPU Basic; Space commit
  `db0ddd2be363a26891a4ac9faab014b507990917`.
- Hosted build version 9.95, source
  `75a7eb494528156f4c73228937738238884151ed`, deployed at 17:39:25 application time.
- Hosted app.py, monitoring.py and templates/ops.html match reviewed files.
- Public `/health` HTTP 200, app/database ok; one probe took 361 ms including
  network/proxy overhead. `/login` showed 9.95; anonymous `/ops` required login.
- The configured writable `/data` bucket mount and persistence variable were
  verified before deployment. No storage-topology change was performed.

The new production process had only ten completed requests at the health probe;
that is not a representative performance sample. No live authenticated timing
table was retrieved in this workspace. Use the admin Performance details panel
after ordinary traffic to establish the actual bottleneck. A successful release
does not establish a performance improvement or verified recovery objectives.

This post-release documentation is saved on `docs/9-95-release-verification`;
it does not trigger another production release. Raw logs, backups and credentials
are excluded from the record. Documentation whitespace and new link checks pass.
