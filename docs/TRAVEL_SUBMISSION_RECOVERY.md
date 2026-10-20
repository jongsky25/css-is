# Travel filing submission recovery — A11, first workflow

Opening a travel filing (`POST /travel/new`) now uses a server-issued,
account-bound operation ID. Repeating the same submission returns its original
checklist instead of creating another filing. Other travel edits, document
generation, uploads, and external provider jobs are separate workflows and do
not acquire this guarantee from this change.

## What the user sees

The new-filing form has a submission-status link. With JavaScript, it keeps the
entered answers on screen while submitting. A lost response or a 20-second
request timeout triggers a status lookup, without another POST. A completed
operation opens the existing checklist. An unconfirmed operation keeps the
answers locked and offers status checking and an explicit retry of the same
captured submission. Validation errors preserve answers and provide a fresh
attempt key; cash-advance warnings still require a separate Continue anyway click.

The native HTML form also carries the operation ID, so repeated submissions
remain safe without JavaScript. Its status page links to the existing checklist
or explains how to retry the original form. If the form is lost, Close this
unfinished attempt waits for any writer, checks for a completed result, and
retires only an unfinished operation before offering a new form.

The form's URL retains the issued operation ID. Reloading a ready form reuses
that ID; reloading after completion returns the existing checklist. Reloading
an unfinished or rejected attempt shows its recovery status rather than silently
issuing another submission. Validation corrections update the form URL and key.

An older open form without an operation ID is rejected with its entered values
and a refreshed form. It never creates a filing without a tracked operation.
Separate new forms represent separate intents; identical contents with different
operation IDs are not globally deduplicated.

## Transaction contract

`travel_submissions.py` implements the state machine on the same SQLite database
as the travel filing. Only keys issued by the server for the current account are
accepted. The first accepted payload binds a SHA-256 fingerprint of parsed,
trimmed form fields, excluding the operation ID. Reusing a key with different
answers returns a conflict. Raw submitted answers are not copied into receipts.

| Stored state | Meaning | Recovery |
|---|---|---|
| `ready` | Form issued; no completed effect recorded | Submit the original form or close the attempt |
| `pending` | Intent committed; result not yet confirmed | Check status, retry the same payload, or close safely |
| `completed` | Filing and receipt committed together | Return the original checklist; never create again |
| `rejected` | Validation rejected or unfinished form explicitly closed | Review a new form with a fresh key |

An HTTP or transport result can be **unknown** while the durable row remains
pending or completed. An error response is never taken as proof that creation
failed. A missing result or a removed filing never authorizes recreating a
previously completed operation.

1. Commit the pending marker and request fingerprint.
2. Acquire `BEGIN IMMEDIATE`, then re-read the receipt under the writer lock.
3. If already completed, return the original reference.
4. Otherwise create the filing, checklist rows, carried cash-advance link, and
   audit entry, then mark the receipt completed in that same transaction.
5. Commit once. A process exit before this commit rolls back all business writes;
   the pending marker remains resumable. A response lost after commit is recovered
   by reading the completed receipt.

Concurrent requests serialize through SQLite's writer lock. Closing a pending
attempt uses the same lock: it either observes a completed filing or prevents a
later execution of that key. Closing an unfinished attempt records one audit
entry in the same transaction; repeated closure does not add another entry,
and an audit failure rolls back the closure. This contract is for local database work only.
Callbacks must not commit independently or perform external side effects.
External jobs need their own receipts, delivery/reconciliation contracts and
recovery policy before adopting retries.

## Security and storage

- Current-account authentication and exact-origin write checks remain required.
- Status lookup and closing are restricted to the issuing account, including
  when another account has an administrator role. Missing and foreign keys
  produce the same response. Revoked accounts cannot read or replay receipts.
- Completed results recheck ownership of the filing. Removed or transferred
  filings are not exposed or recreated.
- Forms, JSON receipts, and status pages use `Cache-Control: no-store`.
- `travel_submission` is an additive schema change initialized through the usual
  database startup path. It stores the ID, account ID, state, request hash,
  result reference and timestamps. Keys are never recycled or automatically
  expired; receipt tombstones prevent old requests from becoming new writes.
  Unused form keys remain as small records until an explicit retention policy
  is introduced. No new dependency or external service is required.
- Existing backup routines capture the receipt and business tables together.
  If rolling back to a build that lacks this contract, disable travel creation
  until a protected build is restored: older handlers ignore operation IDs.

## Verification

`tests/test_travel_submissions.py` covers repeated native/JSON submissions,
commit-then-lost-response recovery, partial writes and audit failures, a real
child-process exit with uncommitted work, independent concurrent connections,
database contention, payload conflicts, account isolation/revocation, removed
results, cache headers, and safe closing while a writer is active.

`tests/test_travel_ux.py` adds browser coverage for lost-response recovery,
explicit retry without automatic write replay, preserved answers after
validation, and explicit confirmation of a cash-advance warning. Test helpers
obtain operation IDs from real form GETs. Production authentication, origin
checks and business validation remain active in these tests.

Before PR verification: 118 focused backend/travel checks passed; the final
source is also exercised by the required normal and shuffled Python 3.11 CI
jobs with Chromium and production OCR dependencies. Manual production testing
remains deferred.
