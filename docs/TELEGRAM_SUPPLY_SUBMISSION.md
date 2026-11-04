# Submit an own supply draft or returned request

Draft PR #572, candidate 9.91. Deployment, previews, activation, real messages,
personal/live tests and main merge remain deferred.

## Independent consent and source authority

`supplies.submit` is a new independent consent, disabled by default through
`CSS_TELEGRAM_SUPPLIES_SUBMIT_ENABLED`. It requires current `supplies.read` consent
and its pilot, plus linked private account/bot/generation, inbound/delivery,
webhook replies, enabled Supplies and native internal-staff/unit eligibility.
Draft creation consent grants no submission permission; submission does not need
draft creation consent. Neither technical administration nor an approver role
permits submitting another person's request. Native owner/status checks remain
on every preparation and confirmation. Group/topic/callback/foreign contexts
cannot perform or recover this action.

## Exact current request, preview and confirmation

Review your request in Office Connect first. `/supply_status ID` now includes its
current request revision. For an own draft/returned request, current submission
consent/pilot can also offer a source-ID/revision form shortcut. This metadata
lookup projects no purpose/item text into Telegram and submits nothing. Start `/supply_submit`
privately, then open its signed-in no-script form. Opening a shortcut creates no
origin, preview, operation or submission. Only `request_id` and current `revision`
are accepted in preparation; no purpose/quantity/owner/decision/stock editing.
Same-origin/session CSRF and strict single-value fields remain required.

Prepare, then send `/supplysubmit_preview OPERATION_ID` in the original private
chat. The five-minute preview shows all current purpose/date/items/quantities,
requester/unit, status/revision, retained number (for a returned request) or
allocation-at-confirmation wording, next submitted version and eligible unit
approver count excluding the requester. No guessed/reserved next number is shown.
Approver IDs bind the pending state but are not projected into Telegram. A zero
count has a prominent warning; native policy still permits submission waiting
without a configured approver. Exact previews that exceed the private reply
budget or contain unsupported control characters are refused; use the native UI.
Nothing is silently truncated or substituted.

`/supplysubmit_confirm TOKEN` confirms exactly that preview. The writer lock
rechecks current request revision/status/contents, active catalog revisions and
stored code/description/unit snapshots, requester identity/unit, eligible approver
set, numbering year and native requestable quantities. Save updated catalog labels
in the normal draft before preparing submission. Changes require fresh review;
an old request revision is never silently upgraded. Concurrent independent keys
on one revision can submit at most once.

## Native effects, atomicity and historical receipts

Confirmation calls `supplies_requests.submit_in_transaction` with a separate
Telegram-namespaced operation UUID. Native numbering, immutable submitted header/
lines, state/revision, operation/event/audit, normal approval mail queue, Telegram
outcome, consumed preview and incoming response handoff commit together. Late
audit/authority/expiry or webhook-handoff failure rolls back every effect, including
the number, submitted snapshot and queued mail. The adapter performs no provider
I/O; this development work sends no real notifications.

The request becomes submitted for ordinary unit approval. Returned requests retain
the existing number and receive one new immutable submitted version. There is no
approval, inventory reservation, issuance, receipt acknowledgement or purchase.
Submitted demand participates in native requestable-quantity calculations even
though no inventory reservation/ledger movement is created. Normal approval
notifications are queued under the same policy as native submission; delivery is
separate and no worker/provider configuration is activated here.

`/supplysubmit_receipt OPERATION_ID` reports the original control number, submitted
version, request revision and original routing count/unit separately from current
owner-only status/revision. Recovery checks canonical native operation actor/action/
result, its immutable submitted version and original history event. Duplicate
confirmations/retries do not submit again, consume another number or overwrite
later returns/edits/approvals. Inspect the original receipt/source after a lost
response before using a replacement key. Independent user-created new operations
are not an exactly-once delivery promise.

Source deletion cancels/scrubs pending previews and tombstones completed source
references, preventing retargeting after ID reuse. Prerequisite/scope revocation,
disconnect and restore invalidate pending context. Expiry and successful completion
scrub extra preview fields/snapshots under existing Telegram retention; native
submitted versions/history retain ordinary retention. Descriptors contain no
purpose/item projection. Existing 180-day receipt cleanup applies.

## Verification and deferred hosted acceptance

Service checks cover owner-only independent consent, strict fields, request/
catalog/identity/routing/stock/year changes, numbering exhaustion, zero approvers,
returned resubmission with retained number, canonical historical receipt/retry,
concurrency, deletion, expiry/restore/revocation and full audit/handoff rollback.
Three 390×844 JavaScript-disabled phone flows cover draft, returned and zero-
approver paths, real linking, source-only prefill/no-origin GET, strict forms,
unchanged pre-confirmation state, stale request refusal/fresh revision, exact
private confirmation, original receipt and current source navigation. Inventory
is unchanged; normal approval-mail queue effects are verified using synthetic
recipients and disabled providers. Hosted/personal acceptance remains Pending.

See [status](SETUP_STATUS.md), [plan](TELEGRAM_TWO_WAY_PLAN.md),
[draft creation](TELEGRAM_SUPPLY_DRAFTS.md),
[native submission](SUPPLIES_MANAGEMENT_S2_1.md) and the
[live checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md).
