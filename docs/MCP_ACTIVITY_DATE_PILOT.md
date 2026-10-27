# Upcoming activity date pilot (v8.93)

M3.9 adds `get_activity_date_context`, `prepare_activity_date_update` and
`get_activity_date_operation`, disabled by default. It follows
[PR #504](https://github.com/jongsky25/css-is/pull/504), merged at
`24d348416133bc9494285ccfdd9410557427ee44`. Hosted acceptance remains pending.

## Existing workflow and exact consent

This is the expansion plan's permitted activity schedule update, reusing the
normal Manage → Dates action. The current Create screen creates live activities;
it has no persisted activity-draft state to submit. This increment does not
create such a state or expose live activity creation/invitation publication.

New optional `activities:dates:update` consent is separate from read, calendar
and creation authority. Existing OAuth grants/default read scopes do not widen.
The independent `CSS_MCP_ACTIVITY_DATES_ENABLED` flag defaults off.

Current authority is shared with the ordinary Manage screen through
`activity_permissions.can_manage`: activity creator, app admin, or a section
manager with permitted directory-team scope over the activity. A general viewer,
read-only/bureau schedule grant or another user's prepared operation does not
confer this authority. Current account, grant/scope/resource, directory/team and
record authority are rechecked; session claims never replace current DB facts.

Read context using `event_token` from an existing `/monitor/TOKEN` or
`/activities/TOKEN/manage` source link; a current custom activity slug also works.
Tokens/slugs are bounded lowercase letters/digits/hyphens (3–40 characters).
This resolves the exact positive `event_id` for preparation (the **event record
ID**, not a survey form ID or merged survey activity-group ID), revision, current
date, ordinary two-year ceiling, one-form count, timezone and canonical Manage
link. Use the returned ID/revision instead of guessing IDs or requiring a new
read scope merely to resolve a link already available in the ordinary UI.
No title, venue/meeting URL, organizer messages, respondent identities, private
text or survey results are returned.

Preparation accepts only positive strict 64-bit `event_id`, exact lowercase
64-hex `expected_revision`, exact YYYY-MM-DD `event_date` and one random 16–80
character `operation_id`. The new date must differ, be after today in Asia/Manila
and remain within the same ordinary two-year horizon used by the UI (including
leap-day handling). No end date, title, venue, source-token override, form list,
invitation, email, status, booking, filing, approval or cancellation input exists.

## Eligibility and exact signed-in review

Both preparation and confirmation require:

- A future single-day bureau activity, with no end date and exactly one linked
  Form 2 event review; no outside activity or speaker/multiple-form activity.
- A matching single-day form date with no archive, pooling, encoding lock,
  response window or recorded attendance count (even zero). Manual activity
  demographic overrides are also excluded.
- No registration rows, including identities later purged; no response rows,
  including archived responses. Counts are checked with bounded existence queries
  without loading any person's identity or response content.
- No form shared with another event and no linked calendar entry, room reservation
  or travel filing, including inactive historical links. The ordinary screen
  handles those cases; this pilot cannot silently leave linked work out of sync.

Context fingerprints full stored event/form metadata and current requester/team
facts. Preparation binds that exact revision, actor/grant/audience, payload hash,
source identity, expiry and random domain key. Browser review shows escaped exact
activity title, source ID, old/new dates, timezone, one form affected and the fact
that the start date controls reporting month/quarter/year. Private venue/messages
are hashed for freshness without being copied into the preview or tool result.

Existing activity/survey links will show the changed date; someone may already
have received a link without registering. The page explicitly states that no
rescheduling email or invitation is sent and that normal communication remains
the organizer's responsibility. Normal future activity reminder jobs retain their
existing controls and use current source dates. No claim is made that a link was
never shared or that notification delivery occurred.

The preview expires after ten minutes. Current authority, revision, unused state,
future-day/horizon and absent linked work are checked again under the writer lock.
A new registration/response, private metadata edit, team retagging, linked record
or the activity day starting blocks a stale confirmation. The shared bounded
three-field same-origin CSRF POST form works at 320px without JavaScript.

## Atomic date change and cache handling

`activity_scheduling.change_in_transaction` requires a caller-owned writer
transaction and uses `storage.set_event_dates(..., commit=False)` to update the
existing event and exactly its one non-archived F2 together. The normal service
retains default commit behavior for existing UI callers. No partial form/event
dates may commit: source checks, both dates, domain/integration audits and receipt
commit together; any failure rolls back the whole change.

The ordinary app date bounds and management check now call shared helpers. The
broader normal UI remains able to perform its existing multi-day/multiple-form
operations under its existing rules; these pilot eligibility restrictions do not
replace ordinary UI policy.

After a confirmed HTTP commit, the existing `invalidate_atoms` callback clears
application atom/view caches. It runs after the DB transaction, including repeat
confirmation of the original key. A callback/rendering failure or lost response
cannot undo a committed date change: recover the original receipt/source and retry
that same confirmation link to refresh caches, never invent another key. Cache
invalidation follows the existing application's in-process/multi-worker policy;
this pilot adds no coordinated cross-worker cache service. Because responses are
excluded, it never moves existing ratings between reporting periods.

No new event/form, public token/link, survey window, respondent/response, room,
calendar entry, travel filing, approval, export, notification or email is created
or edited by this operation. The immutable public event/form tokens are retained.

## Receipts, retries and retention

The receipt reports original old/new date, one updated form, before/after
reporting quarter/year, completion time, `change_status=date_updated`,
`notification_status=none_created` and permission-checked Manage source link. It
returns no title, venue, messages, identities or survey content. It represents
the historical date change, not an invented Pending or approved workflow status;
inspect the source for current dates and subsequent ordinary edits.

Same-key replay/confirmation returns that original result without overwriting a
later ordinary UI edit. Independent keys racing against one revision commit at
most one date change. Recovery requires the same active connection/scope/resource,
current management authority and original event token/creation identity. A deleted
and reused numeric event ID cannot rebind the original receipt. Completion does
not require the event to remain unused forever: later normal registration,
responses and event completion do not recreate or repeat the old change.

Completed/expired preview/snapshot copies clear. Independently committed lazy
cleanup prunes at most 100 expired previews before prepare/recover/browser calls,
even if the later action fails or the pilot is disabled. Hash/key tombstones and
minimal original result remain for recovery. There is no mail payload or outbox.
Normal domain records/audits retain ordinary retention. Caps are 50 live previews
and 10,000 total keys per owner plus the shared process-local 30/minute action
limiter; multi-worker hosting needs coordinated rate limits. Writer locks protect
source checks and date commits.

## Operator acceptance and rollback

1. Deploy v8.93 or newer after release/import-closure and MCP/activity/date/UI
   checks; record deployed SHA and named creator/team manager/admin/outsider roles.
2. Finish hosted write acceptance before a real organizer pilot. Enable
   `CSS_MCP_ENABLED=1` and `CSS_MCP_ACTIVITY_DATES_ENABLED=1`, reconnect with the
   new consent and refresh tools. Other flags remain independent; old grants do
   not widen.
3. Compare fresh context/preview with Manage → Dates on a synthetic future bureau
   event with one unused F2. Verify exact source ID/revision, old/new dates, public
   link visibility consequences and reporting period. No change before confirm.
4. Confirm once and compare both event/F2 dates, stable IDs/tokens, source page,
   audits and receipt. Verify cache epoch/view refresh, no extra record, email,
   rating, invitation or linked work. Test month/quarter/year boundaries and the
   leap-day horizon.
5. Exercise stale private metadata, role/team changes, new registrations/responses,
   archived/pooled/locked/windowed forms, shared/extra forms, attendance, outside or
   multiday source, links to calendar/room/travel, current/past/same/far future
   targets and activity-day rollover. Reject without partial changes.
6. Check CSRF/Origin/form tampering, session/grant/scope withdrawal, expiry, payload
   corruption, same-key and two-key races, final-audit rollback, deleted/reused IDs,
   later ordinary UI edits and post-commit cache failure/lost response. Recover
   the original key; never treat timeout as proof of failure.
7. Verify owner-scoped operations, normal creator/admin/team authority parity,
   escaped mobile preview without JavaScript, minimal receipts, cleanup/capacity
   and runtime packaging. Record IDs/keys/dates/timings/results. Local checks are
   not hosted acceptance and do not enable a feature flag.

Rollback: disable `CSS_MCP_ACTIVITY_DATES_ENABLED` and restart if needed. New
previews, confirmation and MCP recovery stop; normal Manage screens retain their
usual permissions and behavior. Cleanup still runs before rejected action access.
Rollback never reverses a date edit, cancels an activity or sends a message.
No hosted activation is claimed by this implementation.
