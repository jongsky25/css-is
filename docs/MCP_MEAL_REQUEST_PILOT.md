# Standalone meal request pilot (v8.91)

M3.7 adds `get_my_meal_request_context`, `prepare_meal_request` and
`get_meal_request_operation`, disabled by default. It follows room requests
merged in [PR #502](https://github.com/jongsky25/css-is/pull/502), commit
`2eae19c9567bf2056d7ae5ee14dc5ff0428c8ba2`. Hosted acceptance remains pending.

## Consent, fields and destination

Separate optional `meals:request` consent prepares one own standalone meal
request, using the same active-account eligibility as `/meals/new`. Existing
OAuth grants and default read scopes remain unchanged. Room/calendar write
permissions and flags are independent and cannot authorize this action.

Read current preparation context first: earliest permitted activity date,
Asia/Manila timezone, two-calendar-day lead time, meal keys/labels, delivery time
limits, maximum headcount and current Administrative Section queue staff count.
This returns no other person's request or staff names/contact details.

Preparation accepts only these fields:

- `title`: one-line activity title, 1–240 characters after trimming.
- `day`: exact YYYY-MM-DD activity date, at least two calendar days ahead at both
  preparation and confirmation, using Asia/Manila. This is calendar-day notice,
  not working-day room booking policy; ordinary meal rules allow weekends.
- `venue`: one-line delivery location, 1–240 characters after trimming.
- `pax`: strict integer, 1–1000; booleans and numeric strings are rejected.
- `meals`: 1–4 unique lines, each containing only a supported `meal` key
  (`breakfast`, `am_snack`, `lunch`, `pm_snack`) and exact `deliver_at` HH:MM from
  06:00 through 19:00. Unselected meals are not added.
- `special_request`: optional plain text, up to 800 characters; line breaks and
  tabs are allowed. This is shared request content and may contain sensitive
  dietary details: the browser shows it in full and explains section visibility.
- `operation_id`: one random 16–80 character key retained for retries/recovery.

There is no requester override, linked room/calendar/activity ID, status,
supplier, order, approval, delivery, payment or withdrawal input. No external
recipient or email payload is accepted. Strict nested schemas reject extra
fields. Reordering selected meal lines is normalized to the same exact request.

## Exact signed-in review

Preparation saves only an expiring preview. The owner signs into Office Connect
to review every activity/date/location/headcount/meal/time/special-request field,
current requester name and current Administrative Section queue staff. Special
instructions are escaped, preserved and visibly shared with the section. The
page works on a narrow phone screen without JavaScript. Explicit POST confirmation
uses the existing strict three-field, bounded, same-origin CSRF form.

The preview binds actor, active grant, resource audience, payload hash, current
requester/directory identity, current queue membership/names, meal notice/time
policy, expiry and one domain key. It expires after ten minutes. Changed identity,
queue routing or policy requires a fresh preview; the current deadline is checked
again even if midnight passed without any source edit. No existing business
record is being edited, so no invented source revision is accepted from the model.

Requests are visible to the owner and current Administrative Section staff under
the existing meal detail/queue permissions. Technical administration alone does
not grant queue or ordering authority. Membership changes may change queue
visibility after submission. Zero queue staff produces an explicit warning and
count; it does not block a submission that the ordinary service permits.

## Atomic submission, recovery and no external sends

`meals.validate` is shared between previews and normal creation. The existing
`meals.create(..., commit=False)` joins a caller-owned writer transaction and
refuses a clean connection. Ordinary callers retain their default commit
behavior. A confirmed operation atomically creates one Submitted request, only
the selected pending meal lines, normal meal audit, retained source identity,
body-free integration audit and completed receipt. No service commits early in
the MCP path. An audit/receipt failure rolls back the whole submission.

The receipt reports the original reference, Submitted header, pending/Awaiting
order meal state, Administrative Section ordering role and queue staff count at
confirmation. It includes a permission-checked `/meals/{id}` source link, without
returning activity title, location, headcount, dietary text or staff identities.
It reports `notification_status=none_created`: standalone meal creation has no
normal notification effect and the pilot adds none. It creates no room, slot,
calendar entry or linked room-meal form. Submitted is not a supplier order,
delivery, approval or payment. The section separately orders and records progress
using the existing UI.

Retrying or confirming the same key returns its original result and never edits
later normal meal state. Same-key concurrent browser clients create at most one
request. Different keys are separate requests, even for identical fields. A
lost response is not proof of failure: recover the original key and inspect the
source before preparing a replacement. No email/outbox/transport worker is needed
because no external send occurs.

Recovery rechecks the same active connection/scope/resource, current active
account, current request ownership, retained original identity mapping and
reference/creation identity. It preserves the historical creation result after
later ordering, delivery or ordinary withdrawal; inspect the source for current
state. Deleting a source cascades its identity mapping while retaining the
operation tombstone, preventing old receipts from rebinding a reused request ID
or silently recreating the request. No MCP update, delete, cancel, withdraw or
status-tagging capability is added.

Completed and expired preview/snapshot text clears; bounded lazy cleanup runs
before preparation, recovery and browser review in an independently committed
transaction (100 expired previews per call). Operation keys/hashes and minimal
source receipt metadata remain for idempotency. Normal meal records/audits retain
ordinary retention. Limits are 50 live previews and 10,000 total keys per owner,
plus the shared process-local 30/minute action limiter. Multi-worker deployments
need coordinated rate limits; database writer locks protect confirmation itself.

## Operator acceptance and rollback

1. Deploy v8.91 or newer after release/import-closure and MCP/meal tests.
2. Complete hosted write acceptance with named synthetic actors before enabling
   the requester pilot. Set `CSS_MCP_ENABLED=1` and
   `CSS_MCP_MEAL_REQUESTS_ENABLED=1`, reconnect with the new consent, and refresh
   the catalog. Other flags remain independent. Existing grants do not widen.
3. Compare context/preview with `/meals/new`: exact date, location, headcount,
   selected meals/times, requester, shared instructions, section routing and
   two-calendar-day deadline. Verify no request before confirmation. Check zero
   staff, weekend dates and control/extra-field rejection without a real order.
4. Confirm once; compare reference, owner, Submitted header, pending lines,
   source links and next-party count with `/meals/{id}` and `/meals`. Verify no
   room/calendar/notification/order/delivery/payment. Check that unrelated users
   and a technical admin outside the section cannot inspect the source/queue.
5. Exercise refresh, lost response, same-key races, independent keys, audit
   rollback, changed requester/membership, midnight cutoff, expiry, revoked scope,
   grant, session/account and reused deleted IDs. Recovery must preserve later
   separately authorized ordering, delivery and withdrawal without repeating them.
6. Verify mobile without JavaScript, escaped untrusted text, CSRF/Origin checks,
   receipt privacy, preview cleanup, limits and packaging closure. Record deployed
   SHA, roles, request IDs/keys, observed states and timings. Local tests are not
   hosted acceptance and do not activate a feature flag.

Rollback: disable `CSS_MCP_MEAL_REQUESTS_ENABLED` and restart if necessary. New
previews, confirmation and recovery stop; ordinary meal records/queues and
separately authorized ordering/delivery continue. Bounded expired-preview cleanup
still runs on action access. Rollback never cancels a request, reverses an order
or sends a message. No hosted activation is claimed by this implementation.
