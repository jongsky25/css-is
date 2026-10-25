# Calendar and room change capture and routing (T4.1)

Implementation: [telegram_changes.py](../telegram_changes.py),
[storage installation/restore hook](../telegram_storage.py),
[bounded scheduler](../telegram_bot.py),
[progress ledger](TELEGRAM_TWO_WAY_PLAN.md).

T4.1 records committed changes and prepares permission-checked routing
metadata. [T4.2 change notices](TELEGRAM_CHANGE_NOTICES.md) now adds the separate
atomic handoff, safe renderer and final transport checks. The T4.1 boundary below
describes capture/routing alone. It renders no notification, adds no Telegram delivery row, and calls
no message provider. T4.2 must connect eligible routes to the existing durable
transport with final authority checks. All switches remain off by default;
production activation and recovery remain unverified.

## Writer inventory and transactional capture

SQLite triggers run in the business writer's transaction, whether the caller is
a signed-in page, import, scheduler, trusted Telegram action or supported service.
They do not copy email/bell queues or invoke Python/provider code.

| Source/writer | Captured changes |
| --- | --- |
| [storage calendar services](../storage.py), [calendar UI](../calendar_routes.py), [calendar actions](../calendar_actions.py) | Stored calendar creation, business-field updates including title-only edits, cancellation/restore, deletion and import/link changes. Calendar `sequence` alone is insufficient: not every edit increments it. |
| Calendar people/tags/units and [activity document services](../activity_docs.py) | Participant/role membership, tags, extra units, document/outside-invitation/citation metadata. Read-seen stamps and courtesy timestamps are excluded. No document text/URL is copied into an event. |
| Activity edits linked to a stored calendar overlay | Parent activity title/date/end/venue/modality/organizer/unit changes invalidate that overlay's source revision. There is at most one overlay per activity. |
| [room services](../rooms.py), [room UI](../rooms_routes.py), calendar-to-room UI and [room actions](../room_actions.py) | Internal/guest/encoded/series/standby/move/bump request records; requester, source link, day and decision changes; slot membership/approval changes; deletion. Existing normal permissions and approval rules stay in the writers. |
| [room notification scheduler](../rooms_notify.py), [meal services](../rooms_meals.py) | Expiry and reservation-level meal-state changes, including writes made outside the main room service. Email/notice dispatch bookkeeping is excluded. |
| Room slot and block configuration | Metadata-only `availability.changed` events. No subscriber or broadcast policy is invented for configuration changes. These events are retained but do not produce routes in T4.1. |

The scope is stored calendar entries/overlays and room domain records. Synthetic
calendar layers (birthdays, work arrangements, holidays, etc.), other module
notifications and external Google/Outlook synchronization remain separately
scoped. Activity-only records with no stored overlay are not represented as new
calendar entries. No existing writer is rerouted through a privileged bot account.

Same-value updates, read acknowledgements and repeated idempotent calendar imports
produce no extra change. Multiple row changes in one transaction may record
several metadata events; only the latest revision remains eligible for routing.
A failed transaction or rolled-back child savepoint leaves no event for its
rolled-back business mutation. UI room courtesy notifications can fail after
commit without losing the already committed source event.

## Source and event identity

Normal initialization installs three additive tables and capture/fence triggers:

- `telegram_change_head`: source entity/number, random incarnation, monotonically
  increasing change revision and deletion marker. No business body or audience
  snapshot. A new insertion with a reused numeric ID gets a new incarnation.
- `telegram_change_event`: stable random event key, sequence, restore epoch,
  source identity/revision, event kind and UTC recording time, plus routing state
  and continuation cursors. Metadata fields are immutable. There is a unique
  epoch/entity/incarnation/revision identity.
- `telegram_change_route`: unique event/destination/topic, current connection and
  registration generations, bot identity/fingerprint, projection category and
  prepared/cancelled state. No rendered body, token, name, title, decision reason,
  participant list or guest contact is stored here.

Existing records are not backfilled as invented historical changes. The first
subsequent mutation gets a current source identity. Source identities retain a
minimal tombstone so deleting/recreating a row never makes an old event current.
The event key is independent of Telegram action identities; replaying an event
never calls a create, confirm, approve or other business mutation.

Every source change supersedes prior pending/routed events and cancels prepared
routes for that source in the same transaction. Older event metadata remains
available for bounded retention, but cannot route a stale snapshot. Deletion is
captured and suppresses source routes; this increment does not infer permission
to disclose deleted content or generate deletion notices.

## Routing and current permission checks

Preparation requires valid canonical HTTPS bot/link configuration and independent
inbound, delivery, link and `CSS_TELEGRAM_CHANGE_NOTICES_ENABLED=1` switches. The
appropriate calendar/room read switch and current delegated read grant are also
required. Write consent is not inferred or required for an authorized read notice.
The change switch stays `0` by default and does not activate a sender in T4.1.

One worker call considers one pending event and at most twenty active connections
plus twenty active registrations. Durable cursors resume larger audiences after
restart; cursor and route inserts share `BEGIN IMMEDIATE`. Unique keys and the
writer lock make concurrent/repeated workers safe. Events expire for routing
after 24 hours. Preparation uses current data, so enabling the pilot can consider
recent eligible changes within that window, never replaying the business action.

Routing policy is deliberately bounded:

- Private calendar routes go to current creator/participants who can still view
  the stored source through `office_calendar.viewable_entry`. Bureau visibility
  or administrator role alone does not subscribe everyone to every change.
- Private room routes go only to the current internal requester with `rooms.read`.
  Guest contacts, approvers and unrelated administrators are not private recipients.
- Shared calendar routes require the registered owner, current read consent,
  active exact topic/generation and explicit current exact-version source-share
  consent. Source edits revoke existing sharing; a fresh approval is required.
- Group room routes are anonymous availability categories, only for the original
  room operation's exact group/topic/generation and current requester connection.
  They carry no request reference, title, requester or decision reason. A sibling
  topic or unrelated registered group receives no route. The future renderer
  must use the existing safe anonymous day-slot projection.

`authorize_route` rechecks switches, bot, epoch, expiry, source incarnation/revision,
active account/link/grant, source visibility/ownership and exact routing/sharing.
`verify_route` additionally performs fresh existing group owner/bot/requester
membership proof outside the writer lock, accounts for elapsed proof time, then
rechecks local eligibility. It sends nothing and stores no reusable proof. A
provider membership change after a check cannot be locked or recalled.

Connection/account/grant/group/share changes fence prepared routes. Source edits
also fence them transactionally. Directory or environment changes without SQL
triggers are checked whenever the route is used and during bounded maintenance.
T4.2 must recheck again at the actual final send boundary and preserve the
existing accepted/failed/uncertain transport semantics; a prepared route is not a
provider acknowledgement or a guarantee of eventual delivery.

## Restore, retention, pilot and rollback

Normal restart preserves source/event identities, routing cursors and deduplication.
Restore rotates the change epoch and cancels pending/routed work and prepared
routes, alongside the existing link/grant/group/action fences. Older snapshots
without these tables remain supported. Relinking cannot revive an old route.
Snapshot rollback can lose committed events; no exactly-once promise is made.

Each maintenance tick expires at most twenty old pending events, checks at most
twenty prepared routes, and removes at most twenty cancelled routes older than 30 days and twenty
unreferenced terminal events older than 180 days. Routes have no provider receipt
in this increment, so unused numeric destination data can be removed earlier. Source identity tombstones
remain. The existing scheduler now runs local maintenance even with inbound and
delivery off, so default-off capture has a retention path. Disabled switches
still prevent processing, provider reads and sends.

Keep the pilots off for this PR. Before a later synthetic pilot, verify deployed
SHA, durable DB/snapshot recovery, canonical webhook/bot ownership and egress.
Verify UI-originated edits and room decisions, rollback, duplicate/restart routing,
exact group sharing/topic, source/grant revocation, deletion and restore. T4.2
must first supply a safe renderer and durable transport handoff; no live evidence
or actual notification delivery is claimed here.

Pause routing with the change-notice switch or inbound/delivery/read gates. This
does not stop normal Office Connect writes or their metadata capture. Preserve
source tombstones, event/route metadata and restore hooks during code rollback;
never replay old actions or blindly resend uncertain deliveries. Notifications,
reminders/quiet hours and the complete live workflow remain T4.2–T4.4.

T4.2 extends routes with a durable handoff key, fences their outbox rows on cancellation, and retains provider outcome metadata under the existing sender rules. See the [notice runbook](TELEGRAM_CHANGE_NOTICES.md) for rejection recovery and migration/retention details.
