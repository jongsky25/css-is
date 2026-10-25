# Private Telegram reminders (T4.3.2)

Implementation: [scheduler and policy](../telegram_reminders.py),
[settings routes](../telegram_preference_routes.py),
[existing durable sender](../telegram_bot.py),
[channel/quiet-hour controls](TELEGRAM_NOTIFICATION_PREFERENCES.md),
[progress plan](TELEGRAM_TWO_WAY_PLAN.md).

## Staff controls and scope

The signed-in `/account/telegram/notifications` page has a separate native form
for private Telegram reminders, usable without JavaScript and while pilots are
paused. Each category starts **Off**. Staff may choose 15, 30, 60 minutes or one
day before the start, independently for:

- Confirmed timed calendar entries they created or participate in, including each
  supported recurring occurrence. Normal calendar visibility must still permit
  access. An all-day entry has no inferred reminder clock. Activity overlays and
  unrelated calendar layers remain outside this increment.
- Their own approved conference-room bookings, at the first currently stored
  booked slot. Pending/declined/withdrawn/cancelled/expired requests are excluded.

Reminders go only to the linked person's private chat. They grant no read/write
permission, booking approval or sharing consent. There are no group reminders,
new email reminder transport or automatic email fallback. Existing email/daily
reminders and Apprise digests retain their existing controls. Calendar and room
are separate opt-ins: enabling both may produce both reminders for a linked
meeting/booking. Disable one when only one is wanted.

Both the independent reminder pilot and current read/link/inbound/delivery gates
must be enabled by an operator later. Each category also honors the Telegram bit
from the existing channel choices: Email-only or Neither suppresses these new
Telegram reminders. Choosing a lead time does not enable any pilot or email path.

Saving uses existing Origin/session/CSRF protection, a bounded allowlisted form,
an own-account revision check, and atomic settings/cancellation/audit. No submitted
account ID is accepted. Unchanged settings may be saved safely; changing a lead or
disabling a category cancels its existing queued reminders and fences sending
claims. Re-enabling/changing a lead does not replay a previously recorded
occurrence. The new lead applies to future unrecorded occurrences.

## Scheduler, deduplication and current authority

The existing one-minute Telegram tick scans at most five opted-in accounts and
20 sources per account per category per invocation, using persisted round-robin
account/source cursors. It considers current local today/tomorrow only, matching
the maximum one-day lead, and expands the existing bounded recurrence rules.
It never mutates a calendar entry or room request. Large backlogs take several
ticks; delivery timing is best effort, not a precise alarm service.

A due occurrence is recorded and handed to the existing outbox in one serialized
SQLite writer transaction. The SHA-256 occurrence key covers account, category,
source incarnation and UTC start instant. Retries, restart and multiple schedulers
cannot create a second handoff. Lead time, connection generation and bot config
are deliberately not part of the key, so changing them cannot replay that same
occurrence. A rescheduled start has a new key; stale work for the old start is
suppressed. A title-only edit before delivery renders the current title. A
recurring skipped date or cancelled source fails current validation. Reusing a
numeric source ID has a fresh incarnation and cannot authorize the old message.

The original expiry is the occurrence start. A restarted worker can catch a due
reminder while that start is still in the future; no past-start catch-up is sent.
A multi-day event receives a reminder at the occurrence start, not daily during
the span. The source date, clock, approved status, visibility, creator/participant
or requester relationship, account/link/grant, current lead/channel choice and
bot fingerprint are checked again before provider I/O. Source edits and grant,
connection or preference changes fence in-flight claims. HTTP already in flight
cannot be recalled and can become uncertain; it is never blindly retried.

## Quiet hours and provider outcomes

Private reminders use the recipient's explicit Asia/Manila quiet window. A
separate `not_before` gate defers without consuming attempts. Clearing/changing
quiet hours resets that gate on pending reminders but preserves `retry_at`, so a
Telegram 429 delay is never shortened. Current policy/source checks run on wake.
If quiet hours extend to/past the start, the reminder is cancelled instead of
extending its expiry. Opting back in or clearing quiet hours does not revive that
cancelled occurrence.

Reminders reuse sender pacing, committed sending markers, conditional finalizers,
limited definite-429 retries and uncertain-never-retry behavior. A definite
provider rejection records the existing automatic-notice destination pause. A
fresh authenticated recognized command in that private conversation can clear
the pause; it does not replay cancelled/uncertain reminders.

## Migration, restore and retention

Initialization adds `telegram_reminder_preference` and the minimal
`telegram_reminder_occurrence` tombstone table, plus one scheduler cursor setting
and source/slot/grant fences. Existing calendar/room sources without change heads
receive metadata-only identities without fabricated events. Repeated installation
preserves source identities, opt-ins and existing queue state.

Outbox descriptors contain source/occurrence IDs, lead, incarnation and binding
metadata, never rendered business text. Ordinary delivery metadata retains the
existing 180-day cleanup. After that, only occurrence hash/time tombstones remain
for deduplication until bot retirement; these contain no account/source/destination
columns or message body. Expired pending reminders are cancelled in batches of 20.

The existing restore hook pauses links, revokes grants, rotates generations,
cancels pending deliveries and marks sending uncertain. Reminder preferences and
occurrence tombstones persist in the restored snapshot; no historical reminders
are replayed automatically. An older snapshot may lack later hashes/settings, so
exactly-once behavior across snapshot rollback remains unproven. Review restored
choices and reconcile provider outcomes before any reactivation.

## Operator pilot and rollback

All switches and per-account lead times remain off by default. No deployment,
credential/configuration change, webhook registration, real send or hosted pilot
is claimed. For the later T4.4 pilot, use synthetic staff first with verified
HTTPS origin, linked private account and appropriate read consent. Independently
opt into `CSS_TELEGRAM_REMINDERS_ENABLED=1` only in that later approved rollout;
change notices are not a dependency of reminders.

Verify a timed calendar occurrence and approved own room booking end to end,
midnight/UTC and recurring skips, restart/repeated ticks, reschedule/cancel/current
permission loss, quiet expiry and 429 delay, blocked provider pause, source changes
at send time and snapshot recovery. Record the deployed SHA and actual provider
outcome separately from mocked tests. Pause using the reminder switch, per-category
Off, read/link/delivery switches or disconnect. Preserve hashes, source identities,
settings and restore fences on rollback; do not bulk replay old actions or sends.
