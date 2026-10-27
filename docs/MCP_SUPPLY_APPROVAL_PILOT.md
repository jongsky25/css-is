# Full-quantity supply approval pilot (v8.98)

M4.2 adds `get_supply_approval_context`, `prepare_supply_request_approval` and
`get_supply_approval_operation`, disabled by default. It follows
[PR #509](https://github.com/jongsky25/css-is/pull/509), merge
`bf066ada663c92b754dad05675a7b94fad4d9427`. Hosted decision acceptance and a
named-pilot go/no-go remain pending.

## Exact decision, authority and initial stock effects

The pilot approves one Submitted supply request at **every exact requested
quantity** and records its initial stock reservations through the existing
oldest-first allocator. Approval is not issuance: physical on-hand and stock
movements remain unchanged. A supply custodian separately issues reserved stock
or awaits replenishment. Approved demand may exceed available stock.

Separate optional `supplies:request:approve` consent, global `CSS_MCP_ENABLED=1`,
independent `CSS_MCP_SUPPLY_APPROVALS_ENABLED=1`, enabled Supplies and a current
scoped `request_approver` module grant are required. Grant scope is checked against
the immutable submitted unit, using current unit paths. A requester cannot approve
their own request; technical administrator, custodian or auditor access alone
does not grant decision authority. Old read/draft/submit grants do not widen.

The requester must remain active and the immutable submitted actor must match
that requester. Supported requests have 1–20 unchanged active catalog lines and
no earlier reservation cycle. Ordinary returned/resubmitted requests without a
previous approval/reservation are eligible; post-approval correction cycles use
the normal Supplies workflow. The pilot accepts a nonempty decision reason of
at most 2,000 characters, even though ordinary full approval permits an empty one.

This first pilot supports at most 25 existing approved reservation rows per item
(including retained fulfilled/cancelled rows). It refuses any projected change to
another request's existing reservation. Larger queues, displacement, reductions,
return/rejection and post-approval corrections use ordinary Supplies. These are
pilot limits; the ordinary allocator and decision UI retain their broader policy.

## Exact context and review

Use a request ID from its normal Supplies link with `get_supply_approval_context`.
The tool returns IDs, current and submitted revisions, a lowercase 64-hex exact
`expected_revision`, line count and source URL. It returns no purpose, requester/
approver names, item details, quantities, stock totals or another request's data.

The revision binds request/header/immutable submitted lines, current catalog,
scoped approver identity/grants/unit paths, stock totals and movement counts,
existing reservation metadata/versions and the exact projected allocation effects.
The projection uses bounded queues and shared native oldest-first arithmetic.
Other requests' metadata and stock calculations remain internal: the browser
snapshot stores only this request's exact line effects plus the revision hash.

`prepare_supply_request_approval` accepts only positive integer `request_id`,
current numeric `revision`, exact `expected_revision`, nonempty `reason` and one
random 16–80 character `operation_id`. It cannot accept approved quantities,
line overrides, reduction reasons, return/rejection, issue, receipt, purchase,
payment, dispatch/signature or email inputs. Preparation saves a private preview
and audit without deciding or reserving stock.

Signed-in browser review shows control number, requester and submitted unit,
current approver, purpose/date, exact immutable submitted revision, every item/
unit/requested quantity, identical approved quantity, initial reserved quantity,
quantity awaiting stock and decision reason. It explains the oldest-first rule,
non-displacement constraint, separate custodian fulfillment and normal warning
processing. Other requests' identities, contents and allocation details are not
shown. Text is escaped and multiline purpose/reason text stays readable.

**Confirm: approve full quantities and reserve** explicitly authorizes the decision
and initial reservations. The common bounded three-field CSRF/same-origin form
works at 320px without JavaScript. The preview expires in ten minutes. Changed
source, catalog, scope, stock or queue effects require fresh context and review.

## Shared transaction and allocation guard

Ordinary `supplies_approvals.decide_request` now delegates to
`decide_request_in_transaction`, retaining its existing arguments and operation
payload/digest. The caller-owned helper rechecks the same current scoped authority,
submitted revision, catalog and quantities, then writes the native immutable
decision, approved lines, reservations, request revision, operation/event and audit.
The optional internal allocation guard is not an HTTP/MCP input.

`supplies_allocations.projected_quantities` supplies the existing oldest-first
arithmetic to both writer and preview. After the approved rows are inserted but
before allocation, the domain helper recomputes actual effects and compares them
with the reviewed plan. A clock-boundary ordering change or any mismatch fails
and rolls back, rather than applying different reservations. No other request's
reservation may change through the pilot. Negative/corrupt stock/demand requires
reconciliation rather than negative allocation.

The decision, all initial reservations and allocation events, normal durable stock-
warning snapshots, domain operation/audit, minimal MCP receipt and integration
audit commit in one writer transaction. No hidden nested commit or provider I/O
occurs. A final-audit, allocation-guard, allocator or warning-enqueue failure rolls
back the entire business decision and receipt. Competing keys/clients commit at
most one decision for the same submitted revision.

The normal Supplies transaction projects committed stock-warning snapshots into
custodian in-app notices after commit. Projection failure leaves pending durable
snapshots and preserves the successful decision/receipt; normal reconciliation
can retry the notice projection without approving or reserving again. No direct
email, invitation, supplier order, financial posting, physical stock movement,
issue/handover, official signature or dispatch is added by this pilot.

## Recovery, retention and rollback

The same active grant/resource/scope, enabled pilot/module and current scoped
non-requester approval authority are required to recover a receipt. Original
request identity, immutable submitted header, approved decision/actor and native
`supply_operation` result are checked. Another user's operation or new OAuth
connection cannot recover the original key. Current grant/unit-scope withdrawal
removes access rather than preserving old authority through a receipt.

The minimal original receipt returns request/status/revisions, line count, initial
allocation-recorded status, native operation ID, custodian next role and source.
It omits purpose, decision text, names, items, quantities and other queue/stock data.
It does not claim that stock is still reserved, issued or delivered: later
ordinary issuance, stock changes, cancellations or corrections remain separate.
Same-key replay and canonical native operation replay never reallocate or issue.

Completed preview/snapshot copies clear with the commit; expired copies clear in
independently committed batches of 100 before prepare/recover/browser access,
even when later checks fail. Normal warning projection may run after those
transactions under existing Supplies policy. Minimal operation/hash/result
identities and immutable domain history remain for recovery. Preview cleanup is
not deletion of a shared supply decision or its original reason.

Limits remain 50 live previews and 10,000 total operation keys per actor, one
request with 1–20 lines per action, 25 existing reservation rows per item and the
shared process-local 30/minute action limiter. Multi-worker hosting needs
coordinated rate limiting; SQLite writer transactions serialize business writes.

Rollback disables `CSS_MCP_SUPPLY_APPROVALS_ENABLED` and restarts if required.
New context/prepare/confirmation/recovery stop; lazy cleanup and existing normal
warning reconciliation remain available. Committed decisions, reservations,
receipts and native history remain. Rollback never unapproves, releases stock,
issues supplies, frees a key or replays an operation automatically.

## Named pilot acceptance and go/no-go

1. Deploy v8.98 or newer after local OAuth/browser, native approval/allocation,
   stock/issue/correction/warning, API/integration, packaging and release checks.
   Record deployed SHA and the operator responsible for rollback.
2. Before a staff decision pilot, record a named scoped approver, independent
   requester, custodian and synthetic/agreed request/item IDs. Reconnect with the
   exact new consent; verify self, technical-admin, custodian/auditor-only,
   out-of-scope and revoked-grant accounts cannot approve.
3. Compare context and browser review with ordinary submitted Supplies records:
   immutable fields/lines, identical full approval quantities, each initial
   reservation/shortage, decision reason, current scope and effect boundaries.
   Verify no decision/reservation before explicit confirmation and no exposure of
   another request's private purpose, identity or queue details.
4. Confirm once; reconcile decision/domain/MCP receipts, history/audits and each
   line equation: approved = issued + cancelled + reserved + awaiting stock.
   Verify physical on-hand is unchanged, 0 ≤ reserved ≤ on-hand per item, older
   existing reservations are preserved, and a separate custodian issue remains
   necessary. Compare shortage, zero-stock and older-demand cases.
5. Race two keys/clients, simulate lost response, final-audit/allocator/guard/
   warning-enqueue failures, stock/catalog/queue changes, expiry/CSRF/Origin,
   session/grant/unit-path withdrawal and unsupported quantity/decision inputs.
   There must be no unexplained partial decision, reservation or missing receipt.
6. Fail post-commit notice projection; verify pending durable warning snapshots,
   recover the completed decision, reconcile notices normally and prove there is
   no second approval/allocation. Issue/correct stock normally, then replay the
   original MCP/domain key and verify those later changes survive.
7. Test queue/preview limits, text cleanup, 320px/no-JavaScript and flag rollback.
   Record observed quantities, states, IDs/keys, notice outcomes and a specific
   go/no-go before enabling a named staff pilot or expanding it. Local tests and
   previous M3/M4 acceptance do not activate this decision or other posting tools.
