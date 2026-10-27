# Own supply submission pilot (v8.87)

This default-off M3.3 increment adds `prepare_supply_request_submission` and
`get_supply_submission_operation`. Hosted write acceptance remains pending.
It follows task submission merged in
[PR #498](https://github.com/jongsky25/css-is/pull/498), commit
`5c09167e51882e6e4d7f4b1b50d2904ce41caafa`.

## Exact action and permission

Separate optional `supplies:request:submit` consent permits preparation for an
existing **own draft or returned request**. The read and supply-draft scopes do
not authorize submission, and no old grant is widened. Default OAuth scopes stay
read-only. Supplies must be enabled; the owner must be a current account linked
to non-archived internal staff with an organizational unit. Custodian, approver
and technical admin authority do not allow this tool to submit another owner's
request.

Inputs are strict integer request ID (1–2147483647), current request revision
(1–2147483646) and one random 16–80 character operation key. No purpose, line,
quantity, approval or stock fields are accepted. Edit the request in its normal
UI first, then read the current revision and prepare. Never silently retry a new
revision after a conflict or timeout.

Preparation returns a signed-in browser confirmation link and changes no request,
control sequence, submitted version, reservation or stock ledger. The owner
reviews the exact purpose/date, every line's catalog code/description/unit and
quantity, current requester/unit, request state/revision and approval routing.
Requester identity is reloaded from the current directory as in the normal UI.
A new control number is assigned at confirmation, never guessed/reserved during
preview; returned requests retain their existing number.

The preview explicitly shows the count of eligible approvers excluding the
requester. The normal domain permits submission with zero eligible approvers:
this pilot preserves that behavior and shows a prominent routing warning before
confirmation and on the original completion result. It means the request awaits
configured unit-scoped approval, not that anyone has approved or received an
external message. Approver account IDs bind the private preview but are not
returned to MCP; receipts contain only routing role, unit, count and warning.

## Confirmation, effects and recovery

The ten-minute preview binds the actor, original connection, exact IDs/revision,
request contents, active catalog revisions/snapshots, current requester identity,
approver eligibility and numbering year. Signed-in confirmation rechecks Origin,
CSRF, exact digest, session, active grant/scope, switches and all current domain
conditions under the writer lock. Request/catalog/directory/routing changes or an
inactive item invalidate the old preview. Missing or stale catalog descriptions
must be confirmed by editing/saving the normal draft first.

`supplies_requests.submit_in_transaction` reuses the ordinary submission service.
Its immutable submitted header/lines, control number, request state/revision,
canonical supply operation/event/audit, MCP completion and historical routing
metadata commit together. Failure rolls back every effect, including numbering.
The normal owning wrapper still uses the Supplies transaction's post-commit
warning projection and reconciliation behavior. This pilot uses that transaction
boundary as well; it creates no request email or external relay operation.

Submission changes the request to **submitted** and creates the next immutable
submitted version. Eligible unit approvers, normal custodians and auditors can
then read it under the ordinary Supplies visibility rules. It does not decide or
approve quantities, create reservations, issue stock, post ledger movements,
create a purchase, make payment, withdraw or cancel anything. Any subsequent
approval, return or stock workflow remains separate.

The result contains the actual original control number, submitted status,
request revision/version, next-party role/unit/eligible count and source URL
`/supplies/requests/{id}`. It returns no purpose, item text or quantities. One
persisted domain UUID key supplies the existing immutable `supply_operation`
receipt and exact normal-domain replay; the user-facing MCP recovery key stays
separate. Recovery rechecks current ownership, canonical actor/action/result and
the original immutable submitted version, preventing linkage to a replacement
record. There is no new public supply-operation API endpoint.

Exact retries, duplicate confirmations and refresh recover that original result
without submitting twice, consuming another number or overwriting a later
approval, return or edited draft. Independent keys against one revision commit
at most once. Completed status/routing are historical; open the normal source for
current state. A timeout/unavailable receipt is not proof of failed submission:
inspect the original operation/source before making a replacement key.

Completed/expired preview purpose/line/identity/snapshot copies clear, with expiry
cleanup in independent batches of up to 100. Hashes, original keys and receipt
markers persist; canonical Supply history/submitted versions keep normal
retention. Limits are 50 live previews and 10,000 total keys per owner, plus the
shared process-local action limiter (30/minute). Multiple workers need a shared
limiter before relying on that cap across instances.

## Operator acceptance and rollback

1. Deploy v8.87 or newer after release, runtime import-closure and Supplies/MCP
   checks. Keep hosted write acceptance separate from local automated results.
2. For the named requester pilot, enable `CSS_MCP_ENABLED=1`,
   `CSS_MCP_SUPPLY_SUBMISSIONS_ENABLED=1` and normal Supplies. Reconnect and select
   the new submission permission, then refresh the tool catalog. Other write
   flags are independent and are not activated by this delivery.
3. Prepare a synthetic own draft using its current revision. Compare every
   purpose/date/item/quantity/catalog field, current requester/unit and approval
   routing with the normal UI. Verify no control number/version before confirm.
4. Confirm once and compare the actual control number, submitted version/state
   and source with the normal submission service. Check approver/custodian/auditor
   visibility, denial to unrelated staff and unchanged reservations/stock ledger.
   With zero eligible approvers, verify the explicit warning and waiting state.
5. Return a submitted request through a real authorized approver, edit it, then
   prepare/resubmit it. Preserve the original control number and immutable old
   version; create exactly one new version. Recovery of older operations must
   never overwrite later returns/edits/decisions.
6. Exercise refresh between preview and confirm, exact replay, duplicate/lost
   responses, two independent clients on one revision, numbering capacity and
   final-audit failure. Confirm no partial number/snapshot/receipt on failure.
   Catalog/identity/unit/routing/revision changes, inactivity, expired previews,
   revoked scopes/connections/sessions and disabled switches must block writes.
7. Record deployment SHA, named roles, exact synthetic request/revisions,
   operation keys, outcomes and timings. Local tests are not hosted acceptance.

Rollback: disable `CSS_MCP_SUPPLY_SUBMISSIONS_ENABLED` and restart if needed.
MCP previews/receipts become unavailable; ordinary request sources, control
numbers and immutable submitted history retain normal authority and behavior.
Disconnect immediately revokes that connection. Rollback never silently
withdraws a submitted request or deletes its version, number or receipt.
