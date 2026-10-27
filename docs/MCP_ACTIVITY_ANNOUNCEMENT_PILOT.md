# First activity pinned-update publication (v8.96)

M3.11 adds `get_activity_announcement_context`, `prepare_activity_announcement`
and `get_activity_announcement_operation`, disabled by default. It follows
[PR #507](https://github.com/jongsky25/css-is/pull/507), merge
`673b93111c5df53d18b0613e90b48e7079f0e527`. Hosted acceptance remains pending.

## Exact action and authority

This publishes one nonempty, plain-text pinned update using the existing activity
Manage → pinned update feature. The text appears on registered participants'
activity pages under the existing consent/access rules, including for future
registrants. It is not an official invitation memorandum, document dispatch,
email, registration or approval. Invitation memoranda continue through the
existing document workflow; signing and official dispatch are outside this phase.

Separate optional `activities:announcement:publish` consent, current ordinary
activity-management authority, global `CSS_MCP_ENABLED=1` and independent
`CSS_MCP_ACTIVITY_ANNOUNCEMENTS_ENABLED=1` are required. Existing read/save/create/
date grants do not widen. Creator, administrator and scoped team-manager authority
match ordinary Manage, using fresh active accounts and current directory scope.
A general read scope never authorizes participant-page publication.

The first pilot accepts a current or future bureau activity with 1–25 linked
survey forms, including at least one active form, and no existing nonempty pinned
update or retained MCP publication for the original activity. Existing
registrations, responses, linked work and entry windows are permitted because
publication changes none of them. Historical activities and outside activities
use ordinary Manage. Multi-day activities are eligible only while their start
date is today or later. Ordinary UI publication history before this pilot is not
tracked; an empty ordinary update without an MCP tombstone remains eligible.

## Context, exact review and atomic publication

Use the token/slug from the activity's Monitor/Manage URL with
`get_activity_announcement_context`. The tool returns event ID/date, timezone,
exact revision, registration count, text limit and Manage link. No title, venue,
private messages, participant identity, contact details or roster are returned.
The registration count is records, not unique people or delivered/read messages.

The revision binds all event and bounded survey metadata, current managing actor/
directory/team scope, and registration count/latest ID. Source, audience-count,
form or authority changes require fresh context/review. The audience always means
registered participants now and in the future; it is not a fixed list of email
recipients. Source reads use a bounded 26-form eligibility probe and indexed
registration aggregate rather than loading a roster.

`prepare_activity_announcement` accepts only positive integer `event_id`, exact
lowercase 64-hex `expected_revision`, nonempty string `announcement` of at most
1,000 characters, and a random 16–80 character `operation_id`. Outer whitespace
is trimmed; newlines/tabs are retained, other control characters are refused.
No title/date/link/token override, recipient list, email checkbox, replace/clear,
booking, approval or signature input is accepted. Preparation creates only a
private preview and audit, without publishing or planning a send.

Signed-in browser review shows the exact title, ID/date, full escaped plain text,
current registration count, participant-page visibility and effect boundaries.
Confirmation uses the shared bounded three-field CSRF/same-origin form and says
**Confirm: publish pinned update**. The page works at 320px without JavaScript.
The preview expires ten minutes after preparation and is revalidated inside the
writer transaction immediately before the publication.

`activity_announcements.save_in_transaction` shares existing normal Manage
saving and audit semantics, including its ordinary edit/clear support. The
storage setter now accepts caller-owned `commit=False` only in an open
transaction, while its existing default commit behavior remains unchanged.
Normal UI saves retain request-IP auditing and separately optional existing
registrant email behavior. The MCP path never enters the email planner/sender.

The publication, permanent original event identity/operation-key tombstone,
domain/integration audits and original receipt commit in one writer transaction.
Any failure rolls them all back. At most one competing confirmation succeeds;
same-key retries recover the original receipt without writing or publishing again.
The tombstone remains even after normal UI edit, removal, archive or event deletion.
Another key cannot republish the same original activity after a normal clear.
Purges must preserve tombstones; no foreign key prevents ordinary event deletion.

## Recovery, limits and rollback

The same active grant/resource/scope and current management of the original event
are required for recovery. Original numeric ID, public token, creation stamp and
retained operation mapping are checked. Reused numeric IDs cannot bind the old
receipt. Later normal text, dates, registration, survey or archive changes do not
rewrite the original publication receipt. Recovery never restores cleared text,
overwrites later edits, sends mail or creates another publication.

The minimal receipt returns original publication time, event ID, source/participant
links, count at publication, organizer next role and `none_created` notification
status. It omits the announcement body, title, venue and all roster data.
Completed preview/snapshot text clears in the commit. Expired copies clear in
independently committed lazy batches of 100 before prepare/recover/browser access,
even when later authority/flag checks fail. Minimal hashes/results and tombstones
remain; the live text follows ordinary activity retention and Manage edits.

Limits are 50 live previews and 10,000 total operation keys per actor, one original
activity/one update per action, 1,000 text characters, 25 linked forms and the
shared process-local 30/minute action limiter. Multi-worker hosting needs
coordinated rate limiting; SQLite writer transactions serialize publication races.

Rollback disables `CSS_MCP_ACTIVITY_ANNOUNCEMENTS_ENABLED`. New context/prepare/
confirmation/recovery stop, while bounded cleanup still works. Already published
text and original receipts/tombstones remain; ordinary Manage can edit/remove
text and separately use its email option. Rollback never retracts text, frees a
key, resends a notice or changes ordinary future reminder jobs.

## Operator acceptance

1. Deploy v8.96 or newer after local release, packaging, OAuth, browser, existing
   pinned-update/email and race/rollback checks. Record SHA and named pilot roles.
2. Before real publication, test synthetic current/upcoming bureau activities.
   Enable the independent flag and reconnect with the new consent. Verify read,
   save/create/date-only grants and out-of-scope users cannot publish.
3. Compare fresh context and exact browser review against ordinary Manage:
   title/date/text, registration count, registered/future participant visibility,
   active-form rule and explicit no-email/no-invitation semantics. Preparation
   must leave the live update and all mail queues unchanged.
4. Confirm once, verify escaped post-consent participant text and no text shown
   pre-consent, one retained publication and both audits, original receipt and
   unchanged event/forms/registrations. No outbound mail or invitation may occur.
5. Race two keys/clients, replay one key, simulate lost response and final-audit
   failure, change source/form/audience/role/team/scope/grant/session/date, and test
   expiry, CSRF/Origin, unsupported fields and existing/previously published text.
6. Edit/clear through ordinary Manage; recovery must preserve that change and
   another key must not republish. Test deleted/reused numeric IDs, text cleanup,
   preview capacity, 320px/no-JavaScript and existing ordinary email/update flows.
7. Record outcomes and rollback evidence. Local checks do not establish hosted
   acceptance or enable any flag. Official invitation signing/dispatch and M4
   decisions remain separate work requiring their own bounded authority contract.
