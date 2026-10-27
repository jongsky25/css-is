# Live activity creation from a private draft (v8.95)

M3.10 adds `get_activity_creation_context`, `prepare_activity_from_draft` and
`get_activity_creation_operation`, disabled by default. It follows
[PR #506](https://github.com/jongsky25/css-is/pull/506), merge
`8d1d6b547fb005f7a67879be197f0bd42e2191ec`. Hosted acceptance remains pending.

## Exact action and separate authority

This pilot creates **one live bureau activity and one Form 2 event review** from
an original owner-private activity draft. It is neither another private save nor
a request pending approval: the existing Create workflow has no approval step.
Public registration/feedback links are created under the existing page and
consent rules, with no configured entry window. The activity's title, date,
organizing section and venue become public activity details through those links.
The owner takes the next step of managing and sharing the activity normally.

Separate optional `activities:draft:create` consent, current ordinary Create
capability and independent `CSS_MCP_ACTIVITY_CREATION_ENABLED=1` plus global
`CSS_MCP_ENABLED=1` are required. Old grants/default reads do not widen. Private
save/date/read scopes cannot authorize live creation. The private-save hosting
flag need not be enabled: an ordinary role-gated private draft is also eligible.
Other managers/admins cannot convert another person's private copy.

First delivery accepts only the already-supported private fields: one single-day,
face-to-face bureau activity with a current organizing section and no speakers.
The date must be today or later and within the ordinary Create horizon. Historical
draft copies can still use ordinary manual Create; they cannot bypass this pilot's
first-delivery date rule. No field override, end date, online mode, speakers,
participant/email list, duplicate override, entry window, calendar/room/travel
link, approval, signature or cancellation input is accepted.

## Fresh context and exact signed-in review

Use the UUID `draft_key` from `/activity-drafts/KEY` with
`get_activity_creation_context`. Current original ownership, immutable saved-field
digest, Create role, date/section policy, existing confirmed-creation mapping and
normal duplicate checks are applied before returning the exact revision, draft
ID/date, one-form count, weak-hint count and internal-notice recipient count.
No activity title, venue, requester/recipient identity or address is returned.

`prepare_activity_from_draft` accepts only that UUID, the exact lowercase 64-hex
`expected_revision` and one random 16–80 character `operation_id`. The ten-minute
preview binds the original draft identity/fields, current requester/directory,
section-at-save and current section, duplicate metadata hash, exact internal
recipients and current mail feature/pause state. A new strong duplicate always
blocks this pilot; it cannot accept the normal Create duplicate-override key.
Weak hints follow ordinary policy and are shown as a count without copying
another activity's title or private metadata. A changed hint requires fresh review.

The signed-in owner sees every public field, current creator/section, fixed
bureau/F2 defaults, public-link and no-window effects, and exact internal mail
recipients/addresses/features. A changed section since private save is explicit.
The page distinguishes creation from approval, registration or invitation and
explains normal future reminders and independent ordinary manual Create.
Existing bounded three-field, same-origin CSRF POST confirmation explicitly says
**Confirm: create live activity**. It supports a 320px phone without JavaScript.

## Shared creation service and atomic one-time mapping

`activity_creation.create_bureau_in_transaction` shares ordinary Create role/
section/field validation and the existing `storage.create_form_instance` and
`storage.create_event` services. Both storage functions now accept caller-owned
`commit=False`, requiring an open transaction. Default ordinary callers retain
normal commit behavior. Compatible plain-bureau submissions in the existing
Create screen use the same atomic helper; broader ordinary speaker/multiday/
outside/legacy forms retain their existing paths and validation. Normal UI
notifications, QR rendering, optional links and room handling remain outside this
MCP path and retain their usual behavior.

Under one writer transaction, confirmed creation rechecks all current conditions
and atomically commits event, F2, grouping, original public identities, domain/
integration audits, permanent draft-to-activity mapping, receipt and initial mail
states. A failure rolls back all of them. No provider I/O runs in that transaction.
The normal event/F2/public-page defaults apply; no attendee or response is added.
The operation creates no Form 3, public resource/document, room reservation,
calendar entry, travel filing, approval or signature.

The retained `activity_draft_creation` mapping makes one private key eligible
at most once through this confirmed flow. Independent operation keys racing for
that draft cannot create twice. Same-key retries return the original receipt.
Later event edits, registrations, archive or source deletion never free the key
for another creation. Original event token/creation stamp and original F2 ID/token/
link plus current management authority are checked on recovery; reused numeric
IDs cannot bind an old result. Deleted/unavailable sources produce unavailable
receipts, not another creation. A timeout is not proof of no commit: recover the
original operation and inspect the private/live sources before another key.

Private preparation fields remain unchanged. Their source shows an existing
confirmed creation with a Manage link, or warns that the original source is now
unavailable. This is a mapping for this flow, not a claim to track all later manual
uses. Ordinary manual Create remains independent and can still create another
activity after its own explicit review/duplicate warning. The private save receipt
retains its original meaning and never claims that content was never shared.

## Internal mail and durable transport attempts

Initial notices match normal bureau Create: `event_created` to the creator and
`event_section_notify` to current section chiefs other than the creator. No
participant invitation is sent and no administrator fallback recipient is invented.
A maximum of 25 total recipient/feature pairs is allowed in this first pilot.
Normal composers contain creator/activity names, date and a signed-in Monitor
link, without attachments or automatic decision links. The browser shows every
recipient and feature state before confirmation.

Feature/global-pause state is bound at confirmation. A notice disabled then is
recorded immediately as terminal `skipped_off`, with no retained mail payload and
a normal skip log. Later enabling mail cannot send it. Enabled notices commit as
`queued`; queued means neither sent nor delivered. Their normal feature/pause
and configured transport are checked again before sending.

`activity_creation_delivery.run` handles five pending notices per scheduler tick
(maximum batch 20). Before committing a unique `attempting` claim it rechecks the
original active grant/owner/Create authority, current management of the original
event/form, unchanged approved source metadata, current recipient membership/
name/address, creator identity and payload digest. Missing or changed source/
recipient/authority cancels instead of retargeting mail. No network transaction
is open during I/O. Concurrent workers cannot claim a notice twice.

The worker uses normal mail configuration/delivery policy and logs each handled
outcome. True sent means transport acceptance, not reading or guaranteed delivery.
False, exceptions, process death and failure recording a transport success never
automatically requeue. A stale attempting marker becomes `uncertain` after ten
minutes. No resend endpoint is added. Ordinary manual Create emails and future
activity reminders/later messages remain separate existing events; the new
confirmation never calls the Create route's synchronous sender.

Terminal/expired mail payloads clear; queued notices older than 24 hours cancel.
Bounded cleanup runs even while the pilot is disabled. The completed receipt
reports original live event/date, one form, Manage/public links, organizer next
role, original internal recipient count and current notice-state counts. It
returns no title, venue, names, emails or survey/attendee data. Later settings and
responses are separate from the historical result.

## Retention, capacity and rollback

Completed/expired preview/snapshot copies clear in independently committed lazy
batches of 100 before prepare/recover/browser access. Hash/key operation
tombstones, minimal original result, draft-to-live identities and delivery markers
remain for idempotency. Mail copies clear separately; private draft and live
activity records retain their normal retention. Purges must preserve private-save,
creation and MCP tombstones; rollback never deletes identities to make a key reusable.

Limits remain 50 live previews and 10,000 total keys per actor, one creation per
private key, one event/F2 per action, 25 internal notices and the shared process-
local 30/minute action limiter. Multi-worker hosting needs coordinated rate
limiting; database writer locks protect the create and transport claims themselves.
No bulk creation, arbitrary survey schema or external invitation dispatch exists.

Rollback: disable `CSS_MCP_ACTIVITY_CREATION_ENABLED` and restart if needed. New
MCP creation/context/recovery and initial delivery stop; cleanup continues.
Private copies, retained mappings, already-created live sources, ordinary manual
Create and normal future reminders retain their usual behavior. Rollback never
cancels a live activity, reverses publication, frees a creation key or replays an
attempted email. No hosted activation is claimed by this implementation.

## Operator acceptance

1. Deploy v8.95 or newer after local release/import-closure, MCP/ordinary Create,
   public-page, rollback/race and mail checks. Record deployed SHA and named roles.
2. Complete hosted acceptance before a real creator pilot. Enable global MCP and
   `CSS_MCP_ACTIVITY_CREATION_ENABLED=1`, reconnect with the new create consent and
   refresh tools. Verify save/date/read-only grants cannot call the action.
3. Use an own synthetic private draft. Compare fresh revision and exact browser
   fields/current section, today/future date, public-link/no-window effects,
   creator/chief addresses/features and duplicate policy with ordinary Create.
   Verify no event/form/mail queue before explicit confirmation.
4. Confirm once: compare event/F2/group/defaults, stable original public identities,
   mapping, audits, original receipt, public/Manage links and initial notice states.
   Verify private fields remain unchanged and no attendee, response, participant
   invitation, room/calendar/travel record, approval or signature appears.
5. Exercise same/different-key races, refresh/lost response, final-audit rollback,
   changed original draft/profile/section/role/date/routing, new strong duplicates,
   unsupported fields, expiry, CSRF/Origin/session/grant loss and deleted/reused IDs.
   Original receipts must preserve later ordinary edits and registration and never
   recreate the draft after archive/deletion.
6. With synthetic transport only, test owner/chief messages, independent features,
   skip-at-confirmation then enable, pause/configuration gates, lost recipients,
   changed source, concurrent workers, false/error/crash and failure recording a
   successful send. No second automatic attempt is allowed; no retargeting occurs.
7. Compare supported normal Create with the shared helper and verify broader old
   forms/duplicate overrides remain normal UI workflows. Check private-source
   conversion notice, 320px/no-JavaScript confirmation, minimal receipts,
   preview/mail cleanup, limits and runtime packaging. Record IDs/keys/states and
   timings. Local checks do not establish hosted acceptance or enable any flag.
