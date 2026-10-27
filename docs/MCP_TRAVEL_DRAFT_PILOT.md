# Unsubmitted reimbursement draft pilot (v8.84)

M2.6 adds `prepare_travel_reimbursement_draft` and
`get_travel_draft_operation`. Implementation is default-off; hosted acceptance is
pending. It follows personal calendar entries merged in
[PR #495](https://github.com/jongsky25/css-is/pull/495), commit
`9db1f2c1c877cdee1aea9c0cac90375e699be9e7`.

## What confirmation does

Separate optional `travel:filing:draft` consent permits preparing an own NEW
standalone reimbursement filing. Existing grants and default read scopes are not
widened. Travel must be enabled and the account must be a current staff account
without a pending password change. The signed-in owner must review the proposed
activity title/dates/venue, DPO number/date, role and every checklist answer,
including No answers, then press **Confirm: open my reimbursement draft**.

This creates the normal **In progress** (`open`) filing and its missing-document
checklist through `travel.create_filing(..., commit=False)`. The ordinary deadline
is five working days after the activity's last day, including applicable holidays.
The preview shows that deadline, checklist and normal Admin Unit visibility. It
also explains that ordinary due-date notices and scheduled reminders may follow.
A draft is an actual in-progress filing, not a private scratchpad. Opening one
neither submits a claim nor establishes approval or entitlement to reimbursement.

The pilot fixes kind to reimbursement, source to standalone/manual (`blank`),
MC 114 to none and document generation to idle. No linked activity/calendar,
cash advance, liquidation, amount, upload, document generation, reviewer request,
readiness/submission transition, approval, stock movement or payment is performed.
Normal source visibility is owner plus authorized Admin Unit readers; MCP receipt
recovery remains owner-only. Later ordinary travel actions are separate.

## Input and confirmation contract

Title and venue are bounded to 200 characters and DPO number to 60. Title and DPO
are required. Text is single-line and escaped on review. ISO YYYY-MM-DD activity
dates must be in years 1900–9998 and span 0–366 days; DPO date is optional. Role
must be participant, secretariat, resource person or technical support. The
`answers` object supports only the fourteen normal reimbursement drivers as
strict booleans. Omitted drivers propose No and all are shown for explicit review.
Unknown fields, other filing kinds, user IDs, financial values, links and linked
source IDs are rejected. For cash advances, liquidation, linked activities or
other options, use the normal travel screen. Inspect existing filings and cash
advances before opening a standalone draft: different operation keys can create
separate filings and this pilot cannot infer a linked activity from its title.

A ten-minute preview binds the owner, original connection, normalized fields and
normal deadline/checklist snapshot. Confirmation rechecks the current signed-in
session, canonical Origin, CSRF, exact preview digest, active grant and scope,
account authority, enabled switches and current domain policy under a writer
transaction. A newly declared holiday or changed checklist invalidates the old
preview. The filing, checklist, original-identity mapping, completed receipt and
content-free integration audit commit atomically. There are no relay calls in
that transaction.

Reuse one random 16–80 character operation key across retries and recover the
original operation before preparing a replacement after timeout/unavailability.
A fresh OAuth refresh token preserves connection identity while rotating bearer
credentials. Completed means creation succeeded; the normal source page reports
current status. Recovery never overwrites later edits, submission or withdrawal.
The owner-bound mapping has a cascading foreign key to the original filing and
checks its reference/opened timestamp; a deleted/replaced or purged filing cannot
be rebound to its receipt. Unavailability is not proof of failed creation.

Preview fields and derived checklist snapshots clear on completion and lazily on
expiry in independent batches of up to 100. Hashes and durable receipt tombstones
remain so keys are not recycled; normal travel records keep their ordinary
retention. Limits are 50 live previews and 10,000 lifetime keys per account, plus
the shared process-local 30/minute action limiter. Multiple application workers
require a shared limiter before relying on that limit across instances.

## Operator setup and acceptance

1. Deploy v8.84 or newer with release and runtime import-closure checks passing.
2. Enable `CSS_MCP_ENABLED=1`, `CSS_MCP_TRAVEL_DRAFTS_ENABLED=1` and the normal
   `travel.enabled` setting only for the intended pilot. Other write switches are
   independent and are not required.
3. Reconnect/reconsent and select the separate reimbursement draft permission;
   refresh the ChatGPT tool catalog. Old read grants cannot perform the action.
4. Prepare a synthetic standalone reimbursement with exact activity/DPO fields
   and a mixture of Yes/No answers. Compare every proposed field, initial checklist
   and working-day deadline against the ordinary travel form and policy.
5. Verify no filing before browser confirmation, one own In progress filing
   afterward and an exact ordinary `/travel/f/{ref}` source. Check normal Admin
   Unit visibility and denial to another unprivileged user. Verify missing-item
   states, no amounts, no generated URLs, no reviewer assignment/request and no
   readiness/submission/approval/payment. Normal due-date notices may appear.
6. Test retries, duplicate confirmations, token refresh between preview and save,
   expired preview, revoked grant/session, module disabled and a holiday/policy
   change. Replays must not create a second filing or overwrite a later UI edit.
7. Record deployment SHA, roles, exact synthetic fields/source IDs, outcomes and
   timings. Local automated checks are not hosted acceptance evidence.

Rollback: disable `CSS_MCP_TRAVEL_DRAFTS_ENABLED` and restart if needed. MCP
previews and receipts become unavailable; previously opened filings remain in
normal travel screens with their ordinary authority, deadlines and retention.
Disconnect immediately revokes that connection. Rollback does not silently
withdraw or delete a confirmed filing.
