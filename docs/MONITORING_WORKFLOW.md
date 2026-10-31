# Monitoring assessment and working procedure

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
