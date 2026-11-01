# Operational monitoring

## Candidate 9.58 — November 1, 2026

Owner requested automatic outage, backup and new-audit-failure alerts, including a
phone delivery test. Implementation is on `feat/operational-monitoring`; deployment
and delivery evidence belong in [setup status](SETUP_STATUS.md). Do not claim the
schedule or phone delivery is verified from source/tests alone.

### Independent checker

`.github/workflows/operational-monitor.yml` schedules checks at minutes 2, 7, 12,
and every five minutes thereafter. It runs on GitHub's infrastructure, independently
of the Hugging Face app. Scheduling is **best effort**, can be delayed or dropped,
and is not a five-minute availability guarantee. GitHub outages affect this checker.
GitHub can disable public-repository schedules after 60 days without repository
activity; check workflow state as part of ongoing ownership.

`scripts/operational_monitor.py` uses only Python's standard library and fixed
production/GitHub origins. It takes two observations twenty seconds apart.
Matching failures open an incident; matching successes close it; mixed/unknown
observations preserve the incident state. It never forces an outage, backup,
restore, audit rewrite or real business notification to test detection.

| Signal | What is checked |
| --- | --- |
| Uptime | Public `/health` must return valid app/database `ok` JSON. A down app never triggers an admin login attempt. |
| Backup | Saver health must show recent successful durability, and the enabled scheduled-backup job must not report failure or exceed its next due time by 15 minutes. This does not verify backup integrity or recovery. |
| Audit | `storage.audit_health()['ok']`: changed reviewed history or new inconsistencies fail; the exact acknowledged historical incident alone stays healthy. |
| Monitor | A live app whose authenticated status cannot be read produces a separate monitoring-configuration incident. Unknown internal checks never resolve backup/audit incidents. |

The private GET `/admin/monitoring-status` uses existing current-session/admin
capability checks and returns only schema/version and closed status enums. It
includes no record text, actors, IPs, paths, hashes or provider exception details.
It performs no backup or repair. The saver gets at most five minutes of startup
grace; a saver that never starts then becomes stale.

The runner reuses existing deployment secret names `CSS_ADMIN_USER` and
`CSS_ADMIN_PASS` without copying or reading their values through connectors. It
signs in once, reuses that session for the two checks, and signs out afterward.
Normal sign-in/out audit events still occur. Missing/rejected credentials produce
a monitoring incident; rejected credentials are not retried within the same run.
Main-only repository/ref guards exist in both workflow and script. PRs and alternate
branch dispatches do not receive/use production credentials for these checks.

### Delivery and incident state

GitHub is the initial channel, pending the owner's channel choice. Confirmed
problems create issues labeled `office-connect-monitor`, assigned to `jongsky25`.
Open bot-created incident issues are the durable deduplication state. No repeated
comments or new issues are posted while the same incident stays open. Two healthy
observations close it. Manually closing an unresolved issue allows a new alert on
the next confirmed failure. A successful workflow run means checking/reconciliation
completed, not necessarily that every application signal is healthy; open incident
issues show active problems.

**This repository is public.** Incident issues contain only generic operational
status and fixed System health/run links. They never include backup names, private
audit records, exception messages, credentials or personal data. The workflow logs
only booleans/null and fixed signal names. The read-only app endpoint stays private.

Phone/email notifications for assigned issues depend on the owner's GitHub account
and mobile notification settings. GitHub accepting an issue/assignment does not
prove a phone received a push. Configure GitHub mobile push/email for assignments,
or choose a private provider as a separate configuration step. The checker itself
failing produces a failed Actions run; Actions failure notifications also depend on
account settings. No paid external service is provisioned.

### Planned release grace

An active `deploy` job gets at most ten minutes of outage grace; long verification
suites do not suppress outages. The monitor-configuration signal gets at most
90 minutes of grace while the **exact monitor source commit** is awaiting its
initial app deployment. This allows the new private protocol to arrive without
false configuration incidents. Backup/audit failures are never masked by this
protocol rollout grace, and healthy observations can still resolve configuration
incidents. Failed/completed releases and expired windows do not receive this grace.

### Activate and verify

Merge/deploy only through the existing required checks and backup/version gates.
The schedule becomes available from main; alternate branch runs intentionally skip.
Verify a successful normal run after the app endpoint is deployed, then send one
explicitly marked delivery test:

```bash
gh workflow run operational-monitor.yml --ref main
gh workflow run operational-monitor.yml --ref main -f test_notification=true
```

The test creates an owner-assigned **Monitoring test notification** issue, clearly
marked as a test. It does not fabricate a production incident. An already-open test
issue prevents repeated test notifications. Ask the owner to confirm receipt on
their phone and close the test issue. Do not describe delivery as verified until
receipt is confirmed. Existing GitHub credentials could read source/Actions but
could not access the repository secrets public-key API; no new secret was required.

Synthetic tests cover actual sign-in/check/sign-out, access control, safe schemas,
backup deadlines, never-started savers, acknowledged/new audit states, no-login
outages, deduplication, recovery, deployment grace, and test notification semantics.
No production database was used as an application test fixture.

## Historical assessment — October 31, 2026

Assessed from source and existing setup evidence on 2026-10-31. This guide adds
no production instrumentation, external service, scheduled automation or alert
recipient. Existing behavior remains in place.

## What is already available

| Signal | Existing source | What it establishes and limits |
| --- | --- | --- |
| Process/database availability | Public `/health`, app.py | HTTP 200/status ok when a trivial DB query succeeds; does not verify snapshot durability or audit integrity. |
| Traffic, latency, errors, saturation | monitoring.py and admin `/ops` | Rolling in-memory metrics, up to 2,000 recent requests; resets on process restart. |
| Request diagnostics | requests.log and rotated requests.log.1 | Best-effort local JSON logs, about 5 MiB rotation threshold checked periodically. These are not verified durable/offsite logs. |
| Durability | `/ops` save status and snapshot metadata | Save/stall/failure state; owner confirmed current saving. Backup existence alone does not establish integrity or recovery. |
| Audit consistency | storage.verify_audit_chain and `/ops` | Detects stored hash/link inconsistencies; current #8949 warning remains unresolved. It does not identify an actor or cause. |
| Build/runtime diagnostics | Hugging Face build/run logs | Hosting logs were readable in bounded samples; no independent retention was verified. |
| Change verification | GitHub Actions CI/release/deploy workflows | Metadata, dependencies, full normal/shuffled tests and aggregate gate; deployment checks run for main. No new pipeline was added. |
| Recovery evidence | Existing snapshot and backups.restore_backup | Isolated database restore passed. Full app recovery, cold-start mount access and agreed RPO/RTO remain separate checks. |

Source inspection found no configured Sentry integration, OTLP exporter or external
uptime checker in application/workflow configuration. Transitive observability
packages do not establish that an exporter is configured. Connected access did
not establish account-level external monitors or phone notification settings.
There is **no verified automatic outage alert to your phone**. Do not describe
manual monitoring as continuous coverage or promise alerts after ending a chat.

## Use the existing checks

At the start of a hosting investigation or after an authorized deployment, the
agent checks the actual host/runtime state and `/health`, verifies deployed build
provenance, then examines the relevant bounded hosting logs. Log in to production
Operations only with the owner's authorized account. Never treat the preview as
production-health evidence. Do not restart or restore merely because a check fails.

For an owner check, open [production Operations](https://equityinhealth-office-connect.hf.space/ops)
and [Backups](https://equityinhealth-office-connect.hf.space/admin/backups).
Record the save verdict/time, backup schedule, latest backup status and any warning.
A screenshot is useful if it excludes personal records and credentials. Application
status times use Philippine local time; record timezone when comparing to UTC logs.
These checks are manual and symptom-driven; no recurring reminder was scheduled.

| Symptom | Next investigation |
| --- | --- |
| App unavailable or `/health` fails | Check hosting stage, recent build/run logs and the last deployed commit before changing anything. |
| Save status bad or snapshots stop appearing | Check mount/configuration and last successful snapshot. Preserve recovery copies; do not bypass lineage/backup gates. |
| Audit warning | Preserve history and compare existing snapshots read-only. Do not rehash or delete the chain to hide the warning. |
| CI failure | Inspect the failed gate and reproduce the relevant check; report missing prerequisites or skipped tests honestly. |
| Private preview blank/404 on iOS | Check private HF authorization, cookie restrictions, preview frame headers and deployed commit before changing app logic. |

Request logs include IP/user fields and paths; only some path families are bucketed.
Do not assume all routes are redacted. Exceptions and provider logs can contain
sensitive content. Keep raw logs, query strings, cookies, record text and credential
values out of issues, chat and committed evidence. Save only the small, redacted
facts needed to explain the outcome.

## Remaining monitoring choices

External outage detection/phone alerts, durable centralized diagnostics and provider
access-audit retention are gaps. They require a real destination, account access,
retention/privacy choices and a delivery test. No duplicate monitoring SDK or paid
service was added simply to complete the checklist. If requested later, prepare the
concrete configuration, confirm any cost/data-sharing decision, and verify delivery
before claiming automatic coverage. Existing GitHub failure notifications depend
on the owner's account settings and were not tested by generating a failure.

The [operations record](OPERATIONS_ACCESS.md) separately tracks the earlier public
backup exposure, mount identity, independent backup retention, recovery objectives
and audit mismatch. They remain visible while collaboration work proceeds.
