# Private activity draft pilot (v8.94)

M2.7 adds a real owner-private activity preparation record before any future live
draft-submission/invitation workflow. It follows [PR #505](https://github.com/jongsky25/css-is/pull/505),
merged at `f06424dbfa71668de598f9d0dac5129783348497`. Hosted MCP acceptance is pending.

## Preparation, consent and current authority

The ordinary Create screen creates live survey activities. New private draft
screens (`/activity-drafts/new`, `/activity-drafts`, and stable UUID source URLs)
save a separate preparation copy. They do not add a draft status to live events.
The ordinary form and MCP use the same `activity_drafts.save_in_transaction`
service. Normal draft screens require the current ordinary `create_activity`
capability (section manager/admin); MCP additionally requires separate optional
`activities:draft:save` consent and default-off
`CSS_MCP_ACTIVITY_DRAFTS_ENABLED=1` plus `CSS_MCP_ENABLED=1`.

Existing OAuth grants/default read scopes do not widen. Read/date-update scopes
or creator ownership without current Create capability cannot save these drafts.
Technical admins, team managers and collaborators cannot inspect another person's
private draft through its source, collection, operation receipt or Create prefill.
Current account/session/grant/resource/role facts are read from the database.

`get_activity_draft_context(limit=25, offset=0)` supplies current organizing section
IDs/names and the shared ordinary Create date bounds, plus fixed draft defaults.
Section choices are the same ones available in Create; scope does not confer new
unit-management rights. Pages are 1–25 items, offset 0–500, with explicit
`next_offset`. No private draft content, person/contact data or activity results
are returned. The chosen section ID can be obtained from this context rather
than guessed or requiring a separate directory read scope.

`prepare_activity_draft` accepts only:

- `activity_name`: nonempty one-line text, at most 200 characters after trimming.
- `event_date`: exact YYYY-MM-DD within the current ordinary Create picker range
  (five years back through two years ahead, using the shared leap-day handling).
- `section_id`: strict positive 64-bit integer for a current section; booleans and
  numeric strings are rejected by MCP.
- `venue`: optional one-line text, at most 240 characters, trimmed.
- `operation_id`: one random 16–80 character key retained for retry/recovery.

First delivery is fixed to a single-day bureau-organized face-to-face activity
without speakers, using normal combined-QR defaults only when later loaded into
Create. No end date, outside organizer, online mode, speaker list, survey window,
public token, invitation, email recipient, calendar/room/travel link or status
field is accepted. Control characters are rejected. The ordinary new draft form
supports the same bounded fields and explicit Save button, without needing MCP.

## Exact confirmation and atomic save

MCP preparation saves an expiring preview, not a permanent draft or live activity.
The signed-in owner sees exact normalized title/date/section/venue, requester,
fixed draft type and owner-only visibility. It clearly states that save/load
creates no event, survey, public registration/link, calendar item, booking, travel
filing, invitation or email. The preview binds actor/current grant/audience,
exact payload and snapshot hashes, requester identity/directory, organizing
section identity/name/path, expiry and one random UUID v4 domain key. It expires
after ten minutes. Current Create capability, date validity and section/requester
snapshot are checked again under the database writer lock.

The existing bounded three-field same-origin CSRF confirmation POST explicitly
saves the private record. The domain service requires a caller-owned transaction;
source, retained save-key identity, domain/integration audits and MCP completion
receipt commit together. Any failure rolls back all effects. No provider I/O,
notification queue, public activity or survey service is called.

The ordinary draft form uses a bounded six-field (8 KiB maximum) same-origin CSRF
POST and browser-issued UUID save key. It shares normalization, role/section/date
checks, key conflict/ownership rules, transactional source/identity/audit writes
and stable replay. A normal-form audit failure also rolls back source and key.

Same-key concurrent confirmation/replay produces one draft. Different keys are
separate preparation copies, even for identical text. A lost response is not
proof of no save: recover the original operation/source before another key.

## Private collection, source and guarded Create prefill

The ordinary owner-only collection lists 20 records per page with a bounded
owner-filtered ID cursor; source URLs use unique UUID save keys. Sources show the
saved title/date/section-at-save/venue and timestamp. They remain ordinary private
screens after MCP disconnect or pilot disablement while the owner retains Create
capability. A renamed section is called out; deleted/retyped sections or dates
outside current Create rules leave the saved copy readable but block loading.
Role removal blocks source, collection and prefill on the next request.

**Load into Create for separate review** is a GET that rechecks current ownership,
Create capability, date bounds and section validity and preloads only the exact
supported fields/defaults. Mixing a draft with `from_entry` or `from_room` is
refused. The loaded screen has private/no-store headers and explains that its
ordinary Create button is a separate live action: it can create surveys/public
links and send the normal creator/section emails. Opening or reloading never
submits, books, sends, consumes or changes the private draft.

Saved drafts are independent preparation copies, not tracked publication states.
Later manual creation does not mark a draft consumed, prevent another manual
Create submission or prove that its content was never shared. The normal Create
workflow keeps its existing duplicate warning, validation, permission and email
rules. The pilot introduces no live-creation or invitation tool.

## Receipt identity, privacy, cleanup and capacity

`get_activity_draft_operation` requires the same active connection/scope/resource,
current Create capability and original source ownership/key/ID. The minimal receipt
reports original private-draft ID/save time, `saved_status=private_draft`,
`notification_status=none_created`, owner-only source and next actor
`owner_review_in_create`. It returns no title, venue, requester or section snapshot.
It never claims that a live activity was submitted or a draft never used manually.

A separate `activity_draft_save` key registry retains owner, payload digest and
original source ID even if the source is purged under ordinary retention. Thus an
old key cannot recreate a purged draft through the normal form or MCP, and an
old source URL/receipt cannot bind to a reused numeric ID. Deleted sources produce
unavailable results rather than another save. Existing source copies are immutable
through these screens; no edit, overwrite, delete, cancel or discard action is
added to MCP or the new normal draft screens.

Completed/expired MCP preview/snapshot copies clear. Independently committed lazy
cleanup removes at most 100 expired copies before prepare/recover/browser actions,
even if the following action is rejected or the pilot is disabled. Hash/key
operation tombstones and minimal result metadata remain for idempotency. Permanent
private source text has ordinary operator-managed retention, separately from the
ten-minute preview; this implementation adds no automatic source purge or export.
Source purge must preserve save-key/MCP tombstones so old keys never recreate it.

Limits are 50 live MCP previews and 10,000 total MCP keys per actor, 1,000 retained
private source records and 10,000 domain save keys per owner, plus the shared
process-local 30/minute action limiter for MCP and normal saves. Collections and
section choices are bounded. At capacity use the ordinary Create screen; nothing
is silently deleted to make space. Multi-worker hosting needs coordinated rate
limits; database writer locks protect save/key claims themselves.

## Operator acceptance and rollback

1. Deploy v8.94 or newer after release/import-closure and draft/ordinary Create/MCP
   checks. Record deployed SHA and named owner/other manager/admin/viewer roles.
2. Verify ordinary `/activity-drafts/new` save, owner-only collection/source and
   guarded Create prefill with MCP flags disabled. Compare all fields and confirm
   that save/load creates no event/form/registration/response/link/booking/mail.
3. Complete hosted write acceptance before a real ChatGPT pilot. Enable global
   MCP and `CSS_MCP_ACTIVITY_DRAFTS_ENABLED=1`, reconnect with the new consent and
   refresh the catalog. Other flags and old grants stay independent.
4. Read current section choices/date range, prepare a synthetic draft and compare
   every exact preview field and fixed draft/visibility boundary with the normal
   form. Verify no permanent source before signed-in confirmation.
5. Confirm once and compare private source, original receipt, audits, key registry
   and collection; retry/refresh must return one result. Test another manager and
   admin against source, receipt, collection and prefill; they must not gain access.
6. Exercise changed requester/role/section, invalid/aged date, section deletion,
   expiry/corruption, CSRF/Origin/form tampering, grant/scope/session loss, same-key
   races, final-audit rollback and normal save rollback. Check deleted/reused IDs
   and old keys, bounded pagination, cleanup and capacity without live activity
   creation or real mail.
7. Load the ordinary Create form without submitting; compare title/date/section/
   venue/defaults and mixed-source refusal. With synthetic mail only, separately
   create a live activity through the existing explicit form and verify ordinary
   behavior; original draft recovery must not repeat or claim that submission.
8. Check 320px preview/source and no-JavaScript save/load, escaped untrusted text,
   minimal receipts and runtime packaging. Record IDs/keys/fields/timings/results.
   Local checks are not hosted acceptance and do not enable a flag.

Rollback: disable `CSS_MCP_ACTIVITY_DRAFTS_ENABLED` and restart if needed. MCP
preparation/confirmation/recovery stop; ordinary role-gated draft save/source/
collection and Create prefill remain available. Bounded expired-preview cleanup
still runs before rejected action access. Rollback never deletes a private copy,
creates or reverses a live activity, or sends a message. No hosted activation is
claimed by this implementation.
