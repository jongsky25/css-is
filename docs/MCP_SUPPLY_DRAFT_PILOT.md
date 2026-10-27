# MCP personal supply draft pilot — M2.2

Implemented for v8.79; independently disabled by default. Hosted acceptance is
pending. This follows the notification action merged in
[PR #489](https://github.com/jongsky25/css-is/pull/489) and its
[common confirmation/receipt contract](MCP_WRITE_PILOT.md).

## Exact capability

`prepare_supply_request_draft(purpose, lines, operation_id, date_needed=None)`
prepares creation of a **new** draft for the currently connected person. Each
line has an exact active catalog `item_id` and integer `requested_quantity`.
Use IDs from the signed-in Office Connect catalog, never guessed IDs. This
increment adds no catalog export, stock read or item-discovery tool.

Purpose is 1–2,000 characters under the existing UI text rules. Date needed is
optional YYYY-MM-DD. Accept 1–20 lines, with positive whole quantities and item
IDs bounded by 2,147,483,647. Strict nested schemas reject boolean/string
quantities and unknown line fields. The shared UI service combines duplicate
items and rejects out-of-range totals. It does not impose a different date or
quantity policy from the ordinary draft screen.

The MCP result contains an operation key, status, expiry and signed-in
confirmation link. No business draft exists yet. The browser preview shows the
exact current requester/unit, normalized purpose/date, catalog codes,
descriptions, units and combined quantities. Only the user can click **Confirm:
save my supply draft**. Model text/booleans cannot perform this confirmation.

The tool cannot edit an existing draft, submit, assign a control number,
approve, reserve/issue stock, cancel/withdraw or notify an approver. A saved
draft is reviewed and submitted later through the ordinary Office Connect UI.

## Permission and transaction contract

- New `supplies:request:draft` consent is separate from `supplies:read` and
  `notifications:mark_read`. It is eligible at registration but excluded from
  server default scopes. Existing grants and refreshes never gain permission.
- `CSS_MCP_SUPPLY_DRAFTS_ENABLED=1`, global MCP activation and the Supplies module
  must all be enabled. The notification pilot switch is not required.
- A current internal staff directory linkage with an organizational unit is
  required, using the same requester service as the UI. Technical administration
  or a custodian role does not substitute for personal requester eligibility.
- The ten-minute preview binds actor, exact OAuth grant, deployment resource,
  normalized input digest, requester/catalog snapshot digest and operation key.
  Creation has no existing request revision; the snapshot captures each selected
  item's revision/code/description/unit and the requester/unit identity instead.
- Same-origin, registered-session CSRF and exact preview-digest checks protect
  browser confirmation. Current account, grant/scope, switches, staff linkage
  and catalog state are checked again under the writer lock. Changed items or
  requester identity require a new preview. Inactive/missing items are refused.
- The UI's `save_draft_in_transaction` service creates the draft, lines and
  existing Supplies history. The MCP completion receipt and audit commit in the
  same transaction. Any audit failure rolls everything back. No stock or
  downstream provider operation occurs in this path.
- The server derives a separate Supplies operation UUID from the actor,
  connection, resource and MCP key. Replays/races recover the same draft; a
  changed payload or different connection cannot reuse a key. Ordinary UI edits
  after completion are never overwritten by an MCP retry.
- `get_supply_draft_operation(operation_id)` recovers the original preview/save
  through the same active grant. Its completed receipt records `saved_status:
  draft` and the original revision; it does not claim that this remains the
  request's current status. Follow the returned source link for current state.
- Token rotation retains grant identity. Disconnect, security changes, revoked
  scope/account/session and historical restore block pending execution. Other
  accounts cannot inspect the preview or receipt. Completed receipt recovery
  also rechecks ownership of the created request.

Use a random 16–80 character key and retain it across timeouts. Notification and
supply-draft keys have separate action namespaces and separate recovery tools.
Never create a replacement key merely because a response was lost. Inspect the
original receipt/source first. Pending previews are limited to 50 and total
operation tombstones to 10,000 per actor for this pilot.

Pending payloads temporarily store the user-provided purpose/date/lines and the
requester/catalog snapshot. Completion clears those extra preview copies; the
ordinary saved draft and Supplies audit/history retain their normal domain
content. Each pilot entry point independently commits cleanup of up to 100
expired payload/snapshot copies before processing the action, even if the
action subsequently fails. Key/hash/ID/timestamp tombstones remain to prevent
replay. This is lazy cleanup, not a wall-clock deletion guarantee on an idle
host; an operator can call `prune(conn)` in a transaction for additional
maintenance. Wider rollout needs a scheduled retention policy. Credentials and
tokens are never copied into these rows or action audit summaries.

## Operator pilot

1. Deploy v8.79 or later and record running version/commit. Keep unrelated write
   switches off. Enable `CSS_MCP_ENABLED=1`, `CSS_MCP_SUPPLY_DRAFTS_ENABLED=1` and
   the normal Supplies module; restart.
2. Refresh ChatGPT's app tools to load `prepare_supply_request_draft` and
   `get_supply_draft_operation`. Reauthorize and explicitly select the supply
   draft action permission. Readiness displays it independently.
3. Use an agreed test account linked to current internal staff with a unit. Open
   the Supplies catalog and choose one active item by its actual ID.
4. Ask ChatGPT to prepare a new draft with a test purpose, optional date and a
   small quantity. Verify that no request exists before browser confirmation.
5. Review all fields on the confirmation page and confirm yourself. Verify one
   own draft with the exact fields/lines and a source link. Confirm no control
   number, submission, reservation, stock change or approval notice occurred.
6. Retry the same key, recover after a dropped response and reopen/repost the
   confirmation page: there must still be one draft. Change a selected item's
   unit or directory linkage in a separate test between preparation and
   confirmation: the old preview must fail without creating a request. Check
   read-only/notification-only grants, another account and disconnect denial.
7. Record version/SHA, role, field/source parity, denial/recovery results and
   observed latency before recording hosted acceptance. All hosted write
   acceptance remains pending in this implementation.

Disable `CSS_MCP_SUPPLY_DRAFTS_ENABLED` and restart to block further preparation,
confirmation and receipt disclosure. Revoke the test connection to invalidate
its previews permanently. Pending previews may resume before their ten-minute
expiry if the switch is re-enabled. Saved drafts stay saved; rollback does not
delete, cancel or reverse them through MCP.

## Verification

Local tests cover exact preview/save/source parity, no pre-confirmation request,
one draft on concurrent/repeated confirmation, unchanged stock/submission/alert
state, later UI edit preservation, atomic audit failure, strict item inputs,
stale directory/catalog/module/scope/switch/expiry checks, cross-account and
connection denial, origin/CSRF/digest checks, expired-text cleanup and mobile
confirmation without JavaScript. The remote OAuth/MCP probe adds separate
optional supply consent and refresh scope parity, an open preview surviving
rotation, browser confirmation, completed-receipt recovery and unchanged stock.
