# Notification channels and quiet hours (T4.3.1)

Implementation: [preferences](../telegram_preferences.py),
[signed-in routes](../telegram_preference_routes.py),
[notice handoff/sender](../telegram_notices.py),
[delivery plan](TELEGRAM_TWO_WAY_PLAN.md).

T4.3 is split into two dependent children under the plan's small-increment rule:
this PR supplies channel/quiet-hour controls; T4.3.2 adds the durable reminder
scheduler. T4.4 waits for both. This increment introduces no reminder generator
or live activation. Every Telegram pilot remains off by default.

## Staff controls

Open **Calendar and room notification channels and quiet hours** from the private
Telegram account page, or `/account/telegram/notifications`. It works while
Telegram linking/delivery is paused, and requires a current Office Connect session.

- Choose Email only, Telegram only, both, or neither for private calendar changes
  and your own room status updates. Selecting one avoids copies in both channels.
- The calendar email switch is the same existing setting shown in My profile;
  there is no second stored copy. Room email controls apply to internal
  requester-status messages, including decisions, rather than approver alerts.
- Independently control automatic shared calendar and anonymous room updates to
  groups you own. A requester's personal choices do not control somebody else's
  group. Existing exact-topic registration, sharing and read permissions remain.
- Optionally enter both quiet-hour times in Asia/Manila. Start is inclusive and
  end exclusive; 22:00–07:00 crosses midnight. Empty times disable quiet hours.
  Equal start/end is rejected; use channel off to silence a category all day.

Quiet hours apply to these automatic calendar changes, own room status messages
and owned-group updates. Interactive lookups, previews, confirmation receipts and
status replies remain immediate. Existing reminders, approval/admin alerts,
account/security mail, birthday mail and the independent Apprise discussion
digest keep their existing controls. The reminder child will explicitly reuse
these policies; it is not delivered by T4.3.1.

Channels still need their normal global configuration and current permission.
Choosing Telegram does not enable the pilot or grant read/write access. The page
shows Telegram readiness; it introduces no automatic email fallback when Telegram
is paused, blocked or unavailable. No approval authority or new sharing consent
is inferred from a preference.

Defaults preserve the previous behavior: current calendar-email choice, room
status email enabled, Telegram/group change categories enabled subject to their
independent default-off pilots and read consent, and no quiet window. Existing
accounts are not backfilled into the new preference table merely by viewing it.

## Quiet delivery and race handling

The new nullable `telegram_delivery.not_before` is independent of `retry_at`.
Quiet deferral therefore cannot shorten Telegram's mandatory 429 retry delay.
The queue selects a notice only when both relevant gates are due. A quiet check
before claim defers without consuming an attempt or a group-provider proof.
Changing/clearing the quiet window removes its old `not_before` gate on affected
pending automatic notices; the next worker recalculates the current window while
retaining the provider retry deadline.

Handoff stores identifiers only, with the original event expiry. If quiet time
would outlive that expiry, the route is cancelled rather than extending stale
content. After waking, all source/grant/ownership/group checks still run. Source
edits coalesce, revoke, supersede or cancel deferred work under the existing event
and route rules. This does not promise every historical edit will be delivered.

Private messages use the recipient's quiet window. Group messages use the current
registered owner's window, including when the original room requester is another
member. Channel choices are checked before enqueue, proof/render and final send.
Disabling a category cancels its prepared routes atomically with the preference;
queued work cancels and sending loses its claim as uncertain. Re-enabling does
not replay cancelled or uncertain Telegram attempts. A quiet change after claim
can suppress that attempt at the final fence. Messages already in flight cannot
be recalled.

Calendar change email and own room-status email check the current channel/quiet
choice before building and immediately before provider I/O. Quiet email waits
without attempts; normal expiration, feature pauses, batching and email retry
rules remain. Calendar email opt-out keeps the existing skipped outcome; room
status opt-out uses the existing skipped-off outcome. Bell rows and approver
emails remain governed by their existing rules. Existing email queues use current
preferences when considered by their senders; this change does not introduce a
new email transport/receipt mechanism.

## Session, migration, restore and rollback

Saving requires the existing Origin guard and cookie-bound CSRF, a 4 KiB allowlist
form, a current session, a preference revision and the expected current shared
calendar-email bit. Stale preference forms or a calendar-email change made through
My profile conflict rather than overwriting the newer value through this form.
No submitted account ID is accepted. The save transaction includes preferences,
shared calendar-email update, pending Telegram cancellation/defer reset and audit.
Only revision metadata is copied into the audit record.

Initialization adds `telegram_notification_preference` keyed by account and the
nullable outbox timing column. No new service, external credential, grant or
feature switch is introduced. Repeated initialization preserves values. User
choices persist across restart, disconnect/relink and restore; existing restore
epoch/grant/connection/route fences still cancel historical Telegram work. An old
snapshot can contain older preferences, so hosted recovery must include reviewing
settings before reactivating pilots. Exactly-once behavior across snapshot
rollback is still unproven.

Keep pilots off until a later verified deployment and synthetic staff/group pilot.
Verify save ownership/CSRF/stale forms, Email-only/Telegram-only combinations,
quiet midnight/UTC boundaries, deferred retry/source expiry, role/grant/source
revocation, owned-group scope, immediate interactive replies, restart and restore.
No deployed SHA, real provider send or hosted verification is claimed here.

Pause channels through this page or the existing global read/delivery/change
switches. Preserve preference values, handoff identities and restore fences on
rollback; never bulk replay old actions or uncertain sends. T4.3.2 next adds opt-in
reminders with occurrence deduplication and reschedule/cancel/restart checks.
