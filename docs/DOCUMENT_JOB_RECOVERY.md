# Document operation recovery

Introduced in **7.75**, the second A14 increment. This uses the existing SQLite
jobs, Workspace relays and durable service receipts. No new credentials,
dependencies, infrastructure or Apps Script deployment are required.

## Staff experience

Documents show **Pending**, **Running**, **Completed** or **Needs review** for
external operations. A completed dispatch means its recipient results were
recorded; check those results for individual failures. Last and next receipt
checks appear when available. Active operations ask staff to wait. Receipt
checks never resend a document. Manual confirmation of no effect still requires
current authority and evidence; cancel is available only for an unstarted job.

An interrupted extraction cannot restore its unsaved preview. Staff are asked
to extract again or enter the fields manually. Excerpts and signature images
are not added to the durable job payload.

## Ownership and recovery

- Each execution atomically claims a unique owner token in a short SQLite writer
  transaction. The lease lasts **600 seconds**, longer than the Workspace call
  budget. No database writer transaction spans a provider call.
- Initial execution, receipt checks and manual reconciliation respect an active
  lease across processes. A replacement owner fences both late successful writes
  and late failure writes from the previous owner. Ownership expiry alone does
  not modify a document or prove that an external effect did not happen.
- Startup starts a cancellable recovery loop unless `CSS_NO_SCHEDULER=1`.
  Every **30 seconds**, it admits at most one operation per process through the
  shared two-slot external pool. Actual worker completion retains capacity after
  request timeout or task cancellation. Other processes coordinate through leases.
- Pending sign/send jobs older than **30 seconds** may make their first attempt
  after current account, access, source version, approval, signature and sending
  settings pass validation. Failed validation requires review instead of sending.
- Expired running jobs and uncertain jobs query **status only**, with the same
  operation ID and original actor. Legacy running jobs without a lease wait
  **600 seconds** after their last update before a status check.
- Unconfirmed receipts schedule checks after 60, 120, 240, 480 and 960 seconds
  (general delay capped at one hour). Automatic work stops after **six total
  claims**, including the original attempt. Manual receipt checks can bypass
  the automatic schedule and limit after current authorization checks.
- Missing receipts, missing relay configuration and known receipt identity
  conflicts require review. A missing receipt never authorizes another send or
  signature. A known unstarted, unconfigured first attempt can fail safely;
  missing configuration during a status check keeps the uncertain outcome.
- Additive, repeatable schema migration preserves existing jobs and results.
  The recovery index includes state, blocked flag and scheduling/lease fields.
  Rolling back code leaves the additive columns available but stops automatic
  recovery; unresolved jobs still require receipt reconciliation before retry.

## Status access

`GET /documents/{document_id}/operations/{operation_id}` returns a minimal,
uncached progress response to the original actor or concerned officer with
current document visibility. It omits provider payloads, recipients, signature
hashes and ownership tokens. This is a local read and makes no provider call.
The existing CSRF-protected action checks the service receipt explicitly.

## Verification and limits

Synthetic tests terminate a separate Python worker immediately after writing a
successful service receipt, leaving its job running. After ownership expiry, a
fresh worker queries that receipt and records one signature or dispatch. Tests
also cover independent process claims, stale result fencing, access revocation,
source/signature changes, disabled sending, backoff, manual reconciliation,
transient extraction and private progress responses. Existing shared-loop
responsiveness and cancellation/timeout tests remain in place.

Live production testing is deferred. Recovery assumes a shared, durable SQLite
file, a working wall clock and retained service receipts. It is not a distributed
queue across independent database copies, and cannot reconstruct a lost receipt.
Current authorization or approval changes can deliberately stop recovery for
manual review. Background Gmail synchronization capacity and staff usability
pilots remain separate A14/A15 work.
