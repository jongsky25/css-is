# Recoverable correspondence registration — A11 increment

## Protected workflow

The `POST /documents/new` form now carries a signed submission identifier
issued for the current account. Its database receipt, permanent document
number, registry record, references, receipt evidence, notifications, work
link, new work item and proposed tasks commit in one `BEGIN IMMEDIATE`
transaction. The existing lifecycle and guided-intake rules still perform
the business validation. Registration does not call an external provider.

A repeated request with the same account, identifier and payload returns the
original permitted result. It does not allocate another number, recreate tasks
or emit another registration event. Competing SQLite connections serialize
before looking up the receipt. If validation, work creation or receipt
insertion fails, the whole transaction rolls back and a corrected request can
reuse the identifier. A different payload after a successful save returns 409;
it does not overwrite the saved record or start a second registration.

`GET /documents/registrations/{submission_id}` is read-only and no-store. It
returns minimal result metadata and a permitted document/work link. Both
replay and status lookup resolve the active account and current document
visibility. A receipt never grants access. If linked work is no longer
readable but the registered document is, recovery links to the document.
Status recovery remains available when Documents is disabled; a new write
still requires the module to be enabled. CSRF and origin checks remain in
force on every POST, including retries.

## Browser behavior

The registration script runs after the existing approval/scan guards. On
submit it retains the exact form body in memory and disables editing while
the outcome is uncertain. It shows Saving, then opens the confirmed result.
On a lost/HTML/timed-out response it makes a read-only status check. It never
automatically resends a POST. Check saved result and Retry same submission are
explicit actions; a retry uses the original body even if the DOM changed.
A definite 400 validation response releases the controls for correction.
Feedback is announced through a focusable live region and includes a saved
record link and a link to the user's document register.

An absent committed receipt means **unconfirmed**, not failed: the original
transaction may still be running. The page therefore offers another check or
the same submission, without silently changing its identifier. A writer lock
that exhausts the existing busy timeout returns 503 and Retry-After: 3. The
registration connection is owned by a worker thread, keeping the event loop
available while SQLite waits for another writer.

Native form submissions retain the existing 303 redirect and server-rendered
validation page. Their hidden identifier survives a browser POST resubmission
and validation error rendering. New forms must include this identifier;
previously opened forms or custom callers without one are rejected before
creating anything, with instructions to check the document register and open
a new form. Forms from before this release cannot be retroactively deduplicated.

No source file or form draft is added to local/session storage or IndexedDB.
In-memory values are retained only while the page remains open. Closing or
reloading a page can lose unsent field values; this increment does not add a
draft-recovery system. Server receipts survive connection/application restarts.

## Storage, security and rollout

The additive `document_registration` table stores the account, random
submission key, keyed payload fingerprint, document/work IDs and timestamp.
It stores no duplicate form body or OCR text. Account and payload signatures
use domain-separated HMACs; session cookies and CSRF fields are not part of
the business fingerprint. The identifier is bound to the account rather than
one login session; it is not a bearer credential. Another active account cannot
reuse it or read its outcome. Changing the signing secret invalidates old
form signatures; staff must use their document register for those outcomes.

There is no automatic receipt expiry. Keep receipts with their records and
include this table in ordinary SQLite backups. Deleting a receipt can remove
retry protection for an old form. No existing record or permission is changed
and no dependency is added. Preserve the table through a forward repair;
older registration code would no longer honor its retry contract.

This increment covers the registry form's legacy/reference/new-work/existing-
work choices. Internal imports, other creation forms, edits, dispatch, provider
jobs and cross-user duplicate correspondence matching retain their existing
contracts. It does not add a public integration API or claim system-wide
exactly-once execution. Other A11 mutation paths remain separate increments.

## Verification

Synthetic tests exercise two simultaneous database connections, lost replies
after commit, read-only in-flight status, payload conflicts, failed task and
receipt insertion rollback, number/event/task stability, repeated schema
installation, a restarted connection, current authorization, inactive users,
module disablement, session CSRF, writer contention and responsiveness on one
ASGI event loop. Chromium tests use the actual form, registration route and
database with dropped requests/responses/checks, verifying immutable manual
retries, no automatic write replay, validation recovery and one saved record.
Full normal/shuffled Python 3.11 and dependency gates remain mandatory. Manual
production workflow testing remains deferred. Deployment retains the fresh
database backup and live-version checks.
