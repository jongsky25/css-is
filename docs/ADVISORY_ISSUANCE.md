# Advisory issuance and distribution

Candidate 10.42 completes the development scope after [drafts](ADVISORY_DRAFTS.md)
and [review](ADVISORY_REVIEW.md). Release status is recorded in [setup status](SETUP_STATUS.md).

## Issuance and authority

The initiator can issue after exact-version Director approval. An initiator can also
give explicit advisory release access to a staff account with an existing scoped
Documents Records officer grant. Both grant and advisory access must remain current;
application administrator status alone grants no release authority. Grant removal is
recorded and checked again before a queued send. Approval notices include assigned
releasing staff. Documents and Shared work switches remain authoritative.

The issuance preview shows the approved PDF, deduplicated recipient addresses and
accounts without deliverable email. Confirmation binds the exact version, PDF hash,
review packet and roster snapshot. A changed roster requires a fresh preview, but
ordinary roster changes do not require content reapproval. Issuance records its own
date, separate from the stable number reservation date. Concurrent/replayed requests
cannot create a second issue or delivery set.

Internal means active Office Connect accounts: unlinked staff accounts and accounts
linked to current internal directory people; inactive accounts, archived directory
people and external directory accounts are excluded. Directory email takes priority,
with username as fallback. Invalid/missing addresses are reported and require explicit
acknowledgment. The recorded internal audience includes those missing-email accounts,
which can still open the issued copy from **Advisories → Issued advisories for you**.
Recipients receive no access to drafts, discussions or external recipient lists.
Audience mode and explicit external-address edits always require a new reviewed revision.

## Existing services, delivery and uncertainty

`advisory_issue` freezes the approved version, PDF digest, audience and recipient roster.
`advisory_delivery` maps each recipient attempt to an existing `document_job` dispatch.
The existing Documents background worker, operation lock, durable lease, recovery
ownership and delivery ledgers are reused. The local-artifact adapter reads the frozen
PDF and uses the configured mailer through `send_reminders._send`, with one recipient
and one PDF attachment per message. No new email provider, mailbox or scheduler exists.
Documents sending and the `document_dispatch` email feature must be enabled for sends;
this code does not enable them. The existing mail relay source supports attachments.

A successful transport records recipient acceptance in `document_dispatch` /
`document_dispatch_recipient`. Acceptance is not a read receipt or proof of inbox
arrival. A transport timeout, negative/ambiguous reply or crash after starting is
**unknown**. Recovery never sends that attempt again: an authorized issuer must inspect
mail-service evidence and record accepted or confirmed no effect. A missing transport
is a definite failure. Only the latest failed/no-effect attempt can be retried; a
successful, active, superseded or uncertain attempt cannot be resent. Every manual
outcome requires a reason/evidence and remains in the action ledger. Real provider
claims are not inferred from synthetic tests.

Issuance remains **Issued** even if every email fails. Delivery status is independent.
Pending sends recheck current access and issue validity. Cancellation/supersession
refuses unresolved running/unknown outcomes, cancels unstarted jobs and preserves all
prior attempts. Already delivered mail cannot be recalled.

## Publication, replacement and register

Publication is explicit and binds an exact issued PDF/PNG. Internal-only issues cannot
be public. Public activity links serve frozen issued bytes and the issued headline,
never the current draft. Existing public copies retain their compatibility behavior
until an explicit publication change. Removing a public copy or cancelling an issue
removes it from the activity page. Issuing a replacement does not auto-publish it.

Starting a replacement creates a draft workflow within the same advisory identity.
Saving changed content creates a new immutable revision; Chief and Director review
repeat. The old issued bytes stay intact, including any explicitly published copy,
until replacement issuance or an explicit removal. Replacement issuance links the two
issues and marks the old issue superseded. Cancellation records a terminal issue action.
Historical artifacts remain accessible to authorized workflow participants.

The register has matching permission-filtered rows/counts and status queues for Chief,
Director, changes requested, approved-awaiting-issuance and distribution attention.
Division/audience/month filters apply to counts and rows before pagination. Month uses
the latest actual issue month, or reservation month if not yet issued. Status-count links
preserve other filters. My desk continues to use the shared Documents action provider.

## Verification and remaining operational boundaries

Synthetic checks cover exact PDF attachment bytes, recipient deduplication/privacy,
missing email, inactive accounts, no draft access for audience members, preview drift,
concurrent/replayed issuance, explicit release grants, revocation, per-recipient retry,
unknown outcomes, cancellation, frozen public copies/replacement and filtered counts.
Phone journeys exercise issuance, publication, failed-delivery retry and filters with
JavaScript enabled and disabled. Shared Documents jobs, guidance and advisory rendering
regressions are checked separately; hosted release gates remain mandatory.

No real notification was sent for validation. No production database was used. No
external memo or Sheet was edited. The matching [memo text](ADVISORY_MEMO_TEXT.md)
is prepared in the repository for a separately authorized external document edit.
Standalone and multiple advisories per activity, Slides integration and ordinary
comment emails remain the explicitly deferred options from the agreed first increment.
