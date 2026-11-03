# Guided own supply drafts in private Telegram

Draft PR #572, candidate 9.90. In review; deployment, preview publication,
activation, real messages and personal/live testing remain deferred.

## Consent and scope

New independent `supplies.draft` consent and default-off
`CSS_TELEGRAM_SUPPLIES_DRAFT_ENABLED` require separate `supplies.read` consent
and `CSS_TELEGRAM_SUPPLIES_READ_ENABLED`, plus current linking, inbound/delivery,
webhook reply mode and the normal Supplies module. Existing read grants and MCP
consent do not widen. Current native internal-staff linkage and an organizational
unit are required; technical administration or custodian roles do not substitute.
Private sender/chat, account, bot, connection generation, disconnect and restore
barriers are rechecked throughout. Group/topic/foreign/callback contexts cannot
start, confirm or recover the action.

## Guided form and exact confirmation

Start `/supply_draft` privately. Open its signed-in, JavaScript-free page. Opening
without a matching live private request exposes no preparation form/catalog and
creates no origin. With a current request, search active catalog code/description
and page through 25 results at a time. Choose up to five lines, positive whole
quantities, a purpose of at most 1000 characters and an optional exact date.
Search/page changes clear unsaved fields; search before completing the draft.
Selected active items are retained when a failed POST redisplays the form.
Catalog choices expose only IDs/code/description/unit/revision, not stock totals,
reservations or other requesters. Missing/inactive choices are rejected.

The form uses strict fields, same-origin/session CSRF and a random operation key.
Unknown owner/request/status/approval/stock fields are refused. Native normalization
combines duplicate items and validates totals and dates. Normal native requestable
quantity checks run during preparation, preview and confirmation; drafts never
hold availability. A stock change is allowed only if current native checks still
permit the selected quantities. No balance is promised or reserved by the preview.

Preparing creates only a five-minute preview. Send
`/supplydraft_preview OPERATION_ID` in the original private chat. It displays the
complete current requester/unit, normalized purpose/date and every selected
item's ID, code, description, unit and combined quantity. Nothing is silently
truncated. An oversized exact preview or unsupported control characters require
fewer lines, a shorter purpose, corrected source labels or the ordinary UI.
`/supplydraft_confirm TOKEN` explicitly confirms that exact preview. Current
requester identity and selected catalog revisions/labels must still match; a
changed/inactive item, changed directory identity or insufficient current
availability requires a fresh preview. Work/task permissions are not required
for this independent supplies workflow.

## Native save and receipt recovery

Confirmation calls the UI's `save_draft_in_transaction` with a Telegram-namespaced
deterministic domain UUID. The draft, lines, native history/audit, consumed preview,
Telegram outcome and incoming reply handoff share the existing writer transaction.
An audit, late authority/expiry or handoff failure rolls everything back. Duplicate
updates, repeated tokens and concurrent confirmations create at most one draft
for the original operation. This is not a promise about user-created new operations.

`/supplydraft_receipt OPERATION_ID` reports the original saved draft revision,
current owner-only status/revision and source URL. Review and submit separately
in Office Connect. A later UI edit/submission is not overwritten by recovery.
No control number, submission revision, approval, stock reservation/issue,
collection acknowledgement, alert or approver email is created by this action.
Requester eligibility, module, current grants/pilots and ownership remain required
for receipt disclosure. A source deletion tombstone prevents receipt retargeting
if a request ID is reused. Generic 180-day Telegram receipt retention still applies.

Pending previews temporarily retain entered fields and requester/catalog snapshots
under existing Telegram retention. Completion, prerequisite/scope revocation and
expiry cleanup scrub these extra copies; the native draft/history retain their
ordinary content. Descriptors retain no purpose/catalog/body projection. Pausing
a pilot blocks use; revocation/disconnect/restore invalidate the original context.
No provider registration, scheduled/group delivery or activation is introduced.

## Evidence and later acceptance

Service tests cover consent/prerequisites, requester/catalog/module/stock races,
strict inputs, private contexts, expiry/restore/revocation, concurrency, source-ID
reuse, no catalog stock-column SQL, exact preview bounds/control text and atomic
audit/handoff rollback. Two synthetic 390×844 no-script phone flows cover genuine
linking, catalog search/seek pages, one/multiple lines, strict form/CSRF, no request
before confirmation, stale catalog rejection/fresh preparation, one native draft,
receipt retry, own source navigation and unchanged inventory/submission/mail state.
See [status](SETUP_STATUS.md), [plan](TELEGRAM_TWO_WAY_PLAN.md),
[native requester workflow](SUPPLIES_MANAGEMENT_S2_1.md) and the
[pending live checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md). Hosted acceptance
remains Pending; isolated checks do not establish personal/live receipt.

## Separate next action

[Own submission](TELEGRAM_SUPPLY_SUBMISSION.md) is an optional independently
consented capability after draft review. Draft consent does not grant submission;
creating a draft still performs none of its numbering, submitted-version or
approval-notice effects. The native UI remains available for review/submission.
