# Isolated Telegram pilot — operator runbook

Stage 2 authorized by the owner's **“do stage 2”** instruction on 2026-11-03.
This authorizes the isolated protected target, owner-selected bot setup, selected
private feature batches and real test replies described in the
[pilot plan](TELEGRAM_STAGE2_PILOT_PLAN.md). It does not authorize production
publication, bot replacement, activation, main merge or stage 3. No paid upgrade,
public source publication, group/scheduled delivery or email is included.

## Existing bot reuse — November 4, 2026 (Asia/Manila)

The owner explicitly instructed **“reuse it. office connect”** after discussing
Telegram's single-webhook constraint. Reuse the existing bot for this isolated
pilot; creating a new bot is no longer a prerequisite. This supersedes earlier
“dedicated/new bot only” wording in the plan and handoff. It does not authorize
production application deployment, main merge or expanded participant access.

The expected @username and token binding are still unavailable. Configure the
existing token as cloud `OFFICE_TELEGRAM_PILOT_BOT_TOKEN`; do not paste it into
chat or extract credentials from production. Use `getMe` and `getWebhookInfo`
before mutation. Record the current registration and a viable restoration path
privately before redirecting it to the verified pilot. Telegram cannot read back
an existing webhook secret: an old URL alone does not establish rollback readiness.
Check for an existing polling consumer and unexplained pending updates; do not
run competing consumers, discard updates or process production messages as fixtures.
If inspection reveals an unresolved interruption/restoration issue, report that
concrete blocker. The reuse decision itself needs no repeated approval.

All synthetic data, sender allowlist, selected-batch, explicit consent and receipt
requirements remain. This session changed no bot registration or hosted app.

## Target and current boundary

Target: [equityinhealth/office-connect-telegram-pilot](https://huggingface.co/spaces/equityinhealth/office-connect-telegram-pilot).
[Secret and variable settings](https://huggingface.co/spaces/equityinhealth/office-connect-telegram-pilot/settings).
App origin: `https://equityinhealth-office-connect-telegram-pilot.hf.space`.
Callback path: `/integrations/telegram/webhook`.

Created on CPU Basic with **protected** visibility: authenticated metadata says
`visibility=protected`, `private=true`; anonymous source README fetch returns
401. Creation commit `e2d291524f61103636baeb65b68ec82185c9556b` has no app bundle;
metadata reports `NO_APP_FILE`. This is not a running/accepted deployment.
Only new `CSS_SESSION_SECRET` and `CSS_TELEGRAM_WEBHOOK_SECRET` secret names are
present, and `OFFICE_TELEGRAM_PILOT_BATCH=off`. No bot registration or message has
occurred. Production and the shared companion preview remain untouched.

## Credential setup — never paste values into chat

| Name/location | Required value and purpose |
| --- | --- |
| Cloud `HF_TOKEN` | Existing configured identity; creation of this target succeeded. Prefer target-scoped rights. |
| Cloud `OFFICE_TELEGRAM_PILOT_BOT_TOKEN` | Existing bot token selected by the owner for reuse; used for identity/registration checks and copied only to this pilot's `CSS_TELEGRAM_BOT_TOKEN` secret after the reuse preflight above. |
| Pilot `OFFICE_TELEGRAM_PILOT_PASSWORDS` | JSON object with exactly `staff`, `officer`, `peer`, `admin`; four different passwords of 16–128 characters, kept in the owner's password manager. |
| Pilot `OFFICE_TELEGRAM_PILOT_SENDERS` | JSON list of one or two explicitly nominated positive numeric Telegram user IDs. Owner and nominated peer only. No group/chat-topic IDs. |
| Pilot `CSS_TELEGRAM_BOT_TOKEN` | Owner-selected existing token, after identity and reuse preflight. |
| Pilot `CSS_TELEGRAM_WEBHOOK_SECRET` | New random 32–256 character URL-safe secret; already created. |
| Pilot `CSS_SESSION_SECRET` | Independent random session secret of at least 32 characters; already created. |
| Pilot variable `OFFICE_TELEGRAM_PILOT_BATCH` | `off` by default. Approved batch `A`, `B`, `C`, `D`, `E` or `F`; never a production switch. |

Synthetic logins are `pilot-staff@example.invalid`, `pilot-officer@example.invalid`,
`pilot-peer@example.invalid`, and `pilot-admin@example.invalid`, using the matching
password values. Changing a batch/secret restarts the disposable app and resets
records, links and sessions. Record the old results before doing so. Missing or
invalid settings abort startup; there is no open first-admin registration mode.

The selected existing bot must be identified by its expected @username and `getMe`, with
no token-bearing URLs or raw API errors in logs. Inspect `getWebhookInfo` first:
apply the reuse preflight above if registered elsewhere or pending updates exist.
Do not drop pending updates to make setup pass.
If the owner does not know their numeric ID, agree a one-time setup phrase and
have them send it privately to the selected bot before registration. A read-only
`getUpdates` inspection can extract only the matching non-bot private sender ID,
without logging bodies or identities; save that ID privately in the pilot secret.
A second participant requires their own explicit nomination/setup; do not infer
membership from arbitrary incoming messages.

HF secrets cannot be read back. If registration needs a webhook secret whose
value is no longer in the current process, generate a new one **only on the
paused test target**, set it there, wait for the new boot and then register that
same value with Telegram. Never rotate the production secret. Tokens, passwords,
IDs, cookies and raw provider payloads stay outside chat and repository evidence.

## Local verification and publication

Use Python 3.11 and hashed dependencies as in [cloud setup](CLOUD_WORKSPACE.md).
The separate pilot publisher does not invoke `deploy_hf.py` or modify the existing
private preview publisher. Its exact target is fixed; it rejects public/private
visibility, wrong target, missing secret names and an active batch before upload.

```bash
bash scripts/cloud_setup.sh
mkdir -p /workspace/office-test-tmp
.venv/bin/python scripts/cloud_workspace.py test tests/test_telegram_pilot_setup.py tests/test_preview_setup.py tests/test_telegram_bot.py tests/test_telegram_webhook_replies.py tests/test_release_checks.py tests/test_deploy_hf.py --basetemp=/workspace/office-test-tmp/pilot-run --junitxml=/workspace/pilot-run.xml
.venv/bin/python scripts/check_release.py junit /workspace/pilot-run.xml
.venv/bin/python scripts/deploy_telegram_pilot_hf.py
```

The last command is a network-free dry run. For an authorized publish, use the
hashed deployment-tool environment with `requirements-deploy.txt` installed,
from the clean committed review head after its complete CI/avatar gates pass:

```bash
/workspace/telegram-pilot-deploy/bin/python scripts/deploy_telegram_pilot_hf.py --publish
```

The bundle carries `pilot-build.json` with Git SHA, application version, fixed
target and SHA-256 hashes for every other bundled file. It includes no DB, backup,
`.env`, production uploader or deployment credentials. The test-only launcher
retains application 9.91: production runtime files/version/closure are unchanged.
New tooling still requires fresh exact-head CI; old 8803e35 checks do not certify it.

After upload verify protected source visibility, actual Space commit, CPU Basic,
RUNNING, manifest/source/version and sampled bundle hashes. `/pilot-health` exposes
only environment, source/version, selected batch, disposable flag and boot identity.
Confirm anonymous record/fixture access is denied and no bootstrap account can be
created; then sign in through the exact app origin. `/pilot-fixtures` is signed-in
only and displays synthetic record IDs for positive and foreign/restricted denial
cases. The banner links to it. No live identities or source contents are in this index.

## Isolation, fixtures and limits

The launcher precreates a fresh empty SQLite DB before app import, removes all
inherited application/provider/persistence variables, keeps scheduling off, forces
webhook replies, and blocks Python socket egress using the existing preview guard.
It allows only the selected batch's known flags, plus inbound/delivery/link.
Groups, change notices, reminders and Apprise remain off. SMTP/relay/AI credentials
are absent. This Python guard is not an OS sandbox for arbitrary native programs.

Intake authenticates the webhook secret before reading/parsing its bounded body;
rejects duplicate secret headers, non-private/unlisted/bot/topic senders and
unsupported callbacks; then delegates to the unchanged native webhook. Messages
at or before the current boot's timestamp are acknowledged without processing,
so queued old messages cannot replay into the new empty ledger. Fresh same-boot
updates retain native deduplication. This conservative seconds-resolution fence
may discard a legitimate message sent during startup: send a new command after
readiness. It is not durable restart/restore or exactly-once acceptance.

Seeded through native setup/domain APIs:

- Four distinct password-backed accounts, internal staff/unit linkage, a scoped
  records officer, separate administrative-section room approver/custodian, and
  permitted/restricted document-work pairs. Technical admin is not a substitute
  for business roles.
- Proposed, To do, In progress, For review, Done, Cancelled and peer-owned tasks;
  one prerequisite and blocker; lead assignment; own/peer discussion, reply,
  follow/notice and edited/long-Unicode examples.
- Active paper stock, own/foreign draft requests, a returned numbered request and
  a submitted request with normal synthetic approval queue. No provider mail.
- A plain meeting on the next source-defined working day, pending and approved
  own room requests in other slots, plus own/foreign travel, meal and arrangement
  requests. Meal dates follow native lead rules; arrangement periods are open.

Record actual fixture IDs/date/slot from the signed-in index at each boot. Inspect
availability before the planned 10:00–11:00 meeting action. More specialized
formal-review, recurrence/import/managed-calendar, linked-room-meal, zero-approver,
concurrency, fault and restore cases still need their documented source setup or
isolated automated evidence. Do not mark such cases hosted Pass from fixture
existence, and do not inject faults into production.

## Provider registration and acceptance sequence

After matching manifest, local/CI gates, secret presence, target visibility and
bot identity, set test batch A and verify the new boot. Register only the owner-selected
bot's callback with its current secret and `allowed_updates=["message"]`; do not
use `drop_pending_updates`. Inspect registration again without publishing tokens.
Wrong/missing-secret probes must fail and unlisted senders must produce no reply
or business action. Registration/HTTP handoff does not prove receipt.

Owner phone batch A: open the app, sign in as synthetic staff, send `/start` to
the selected bot, select calendar read on `/account/telegram`, submit the actual
received code, then `/status` and its exact `/confirm` in the same private chat.
Do not issue another `/start` while confirmation is pending. Verify `/calendar`,
`/menu`, `/status`, source navigation, denied work commands and explicit disconnect.
Record actual owner receipt and observed source state. Never obtain confirmation
codes from the database as a substitute for delivery.

Proceed to B–F only after recording the previous batch's outcome, selecting its
host batch and explicitly relinking/consenting after the resulting restart.
Lifecycle batch G uses the selected feature batch's native revoke/disconnect/
deactivate/source-loss controls; destructive fault/restore cases stay local.
Use every applicable row in the [live checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md)
and the plan's evidence fields. Keep real receipts distinct from local mocked
responses. Owner acceptance of the final named build/matrix is required to close
stage 2. T4.4, production merge/deploy and production activation remain deferred.
