# Private Telegram discussion digests

This first Apprise pilot adds an optional private Telegram reminder for unread shared-work discussions. Open **Shared work → Notification preferences** (`/work/notification-preferences`) and use **Telegram discussion digest**. Choose Off, Daily or Weekly. Email preferences and existing in-app/required workflow alerts keep their separate delivery rules.

A reminder contains only “You have unread discussion updates in Office Connect” and a sign-in link to `/work/updates`. It contains no account names, counts, work titles, message contents, document identifiers, attachments or approval links. Sending does not mark discussions read. Only private, positive numeric Telegram chat IDs are accepted; group/channel destinations and arbitrary Apprise URLs are not supported in this pilot.

## Enable the application modules first

Discussion digests require **Documents** and **Collaborative work** to be enabled inside Office Connect, independently of the hosting secrets. Open `/admin/documents/setup` as a current system administrator with an explicit all-unit Documents permissions-administrator appointment. Enable Documents in **Documents feature**, leaving document sending disabled, then enable **Collaborative work**. Each form requires a reason and confirmation and affects the whole instance under existing staff permissions. No account roles are granted by enabling a module. If the enable form is unavailable, ask an already appointed permissions administrator to review the account's authority; initial role setup is not reopened.

The Collaborative work control also permits a current system administrator to pause shared-work changes and discussion delivery. Existing permitted work stays readable; pausing does not disconnect Telegram or change cadence, claims, document sending or unrelated modules. Documents and Collaborative work forms share one revision so stale forms are rejected. All changes record actor and reason transactionally. Deployment and viewing these pages do not enable anything automatically.

Notification preferences now list every locally detected blocker separately: disabled Documents, disabled Collaborative work, host master switch, invalid/missing HTTPS public address, missing or malformed target JSON, setup-code mismatch and invalid token/private-chat-ID format. The check never displays bot credentials, other users' setup codes or destination values, and makes no network request. Administrators receive a setup link; other staff are directed to their administrator. Configured still means local syntax/readiness, not real Telegram connectivity.

## Hosting setup

Code deployment alone does not activate Telegram delivery. The host master switch defaults to off, each user defaults to Off, and no credentials are bundled into the application or test data.

1. In Notification preferences, save a Telegram preference to generate a personal setup code. Saving **Off** can be used to prepare the connection before opting in. Give the current code to the hosting administrator.
2. Create/use the office's Telegram bot and start a private conversation with it. The administrator obtains its BotFather token and the staff member's positive private chat ID using trusted Telegram administration tools, verifying that the chat belongs to that staff member.
3. Add **hosting secrets** on the Hugging Face Space. Do not paste bot credentials into Office Connect forms, source control, command history or support messages. Configure:
   - `CSS_APPRISE_TELEGRAM_TARGETS`: a JSON object keyed by the exact personal setup code, with only `bot_token` and `chat_id` string fields.
   - `CSS_APPRISE_TELEGRAM_ENABLED`: `1` to allow delivery, or `0` to pause all Telegram delivery.
   - Existing `CSS_BASE_URL`: the actual HTTPS Office Connect origin used by staff; this supplies the sign-in link and must match the app's normal public host.

Example shape; replace every placeholder with the verified private configuration:

```json
{
  "SETUP_CODE_COPIED_FROM_PERSONAL_PREFERENCES": {
    "bot_token": "BOT_TOKEN_FROM_BOTFATHER",
    "chat_id": "123456789"
  }
}
```

4. After hosting restart, the user's page shows **Telegram is configured for your account** when the configuration has valid syntax and delivery is enabled. This does not prove live provider connectivity. Choose/save Daily or Weekly to opt in.
5. Verify delivery with a fresh, eligible discussion update after setup. No real Telegram messages are sent by automated tests. Actual provider activation/delivery requires the administrator's real credentials and the user's opt-in.

Malformed/missing configuration is treated as unavailable without echoing secrets. Configuration is limited to 64 KiB. Private setup codes are opaque routing identifiers, not bot credentials. They are generated only on an explicit save, bound to the account and never reused. A new account cannot inherit a deleted account's channel.

## Cadence and delivery history

The existing scheduler checks delivery every minute, from the office's morning reminder hour (7am Philippine time). Daily users receive at most one attempted digest per day. Weekly users use the configured discussion-digest weekday, Monday by default, with both weekly-period and daily deduplication. Space restarts after the morning hour can catch up. No unread eligible updates means no attempt.

Up to five account attempts are handled per tick; later ticks drain other eligible accounts. Each batch marks up to 1,000 eligible notice IDs, with remaining updates available to later batches. No copied message content is stored in the channel outbox. Access, account status, read state, preference, work-module availability, master switch and destination configuration are checked before claiming and immediately before transport.

A committed `sending` claim precedes all network I/O. Telegram acceptance records `sent`; exceptions/uncertain responses record `unknown`. Interrupted `sending` and uncertain attempts are never automatically retried, including on a later date, cadence change or destination change. New unread notices can produce a later digest. `cancelled` means eligibility was removed before transport; those notice IDs are released for future eligible batches. Recent history is visible only to its owner and contains timestamps/states, never destination credentials. “Sent” confirms API acceptance, not device display or that a person read the message.

**Disconnect Telegram** turns the preference off and replaces the setup code, immediately invalidating the old host mapping. Reconnection needs the new code and explicit opt-in. A deliberate historical backup restore also turns channel preferences off, rotates setup codes and preserves uncertain in-flight history; it must not revive old destinations or replay old attempts. Routine boot recovery from the latest snapshot preserves claims.

## Implementation and verification

`work_channels.py` owns additive account-scoped preferences, durable claims and delivery history. It does not reuse email attempt markers. `apprise_transport.py` uses the pinned Apprise Telegram plugin with a fixed HTTPS Bot API endpoint, certificate verification, 3-second connect/7-second read timeouts, no HTTP redirects, no service retries, no owner autodetection, no images/previews/attachments and memory-only provider storage. Credential-bearing Apprise and HTTP debug logs are suppressed. All credentials stay in hosting secrets; only a one-way destination/binding fingerprint is stored with an attempt.

Apprise **2.0.1** is BSD-2-Clause and is pinned through the existing hashed runtime/test dependency locks. The ordinary production-image dependency audit and SBOM include its dependency graph. No additional service or provider account is provisioned by this change. Microsoft Teams, ntfy and other Apprise providers remain future candidates rather than enabled channels.

```sh
CSS_TEST_CHROMIUM=/usr/bin/chromium CSS_TEST_NOW=2026-10-20T06:00:00 python -m pytest tests/test_work_channels.py tests/test_work_channels_browser.py tests/test_deploy_hf.py tests/test_mcp_read.py
CSS_TEST_NOW=2026-10-20T06:00:00 python -m pytest tests/test_work.py -k 'digest or notification_preferences or routine_bell or quiet_preferences'
```

Tests cover owner/CSRF/revision checks, default-off/idempotent migrations, disconnect/account reuse, morning/weekly cadence, independent email delivery, bounded fair ticks, dry-run/no-write behavior, committed concurrent claims, read/access/account/config revocation, failed/crash uncertainty, queue rollback, deliberate restore and stale finalizers. The real Apprise plugin is exercised with mocked HTTP to inspect endpoint/payload/TLS/timeouts/no redirects/retries and credential-safe logs. A real local ASGI server and Chromium exercise native form redirects, mobile layout, conflict recovery, private setup and script-disabled disconnect without real sends.
