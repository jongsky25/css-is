# Intake review with fewer steps

Candidate 10.06, November 7, 2026. Branch `feat/documents-intake-review`,
initially stacked on the navigation/workspace increment in PR #596.

## User flow

The Inbox offers an explicit **Review** / **Resume review** button. This posts to
the existing claim action with CSRF and the current revision; merely opening a
file remains read-only. Another reviewer's active claim cannot be taken over.

**Read and fill empty fields** saves entered values, reads the current source
through the existing bounded external worker, and fills empty metadata fields.
Existing corrections, sender-derived direction rules and original receipt times
are preserved. Requests and focus areas remain separate suggestions requiring
review, with confirmations cleared on a fresh reading. No document number,
assignment, approval, signature or dispatch is created by reading.

Source suggestions and draft prefilling commit together after rechecking the
current revision, claim, account authority, folder and source content. Cached
suggestions can fill empty fields without another provider call; explicit reread
refreshes the source. Failed reads retain saved entries for retry or manual review.
The prior extract/reread/apply actions remain supported for existing clients.

Document details appear before request interpretation. Save, Register and Register
and review next share a responsive action bar. The review-next behavior remains
the existing numbered registration followed by claiming the next eligible item.
Unsupported files show manual-review guidance; body-only emails keep their
existing manual review with no OCR action. No JavaScript is required for this flow.

## Verification and limits

Synthetic service, route and browser checks cover preserved corrections, cached
reads, forced rereads, concurrent edits, changed source, mismatched OCR provenance,
revoked authority, expired claims, changed folder, disabled module, CSRF, stale
submissions, provider failure and external admission capacity. Phone/desktop and
JavaScript-disabled browser journeys perform inbox review, read/prefill and
registration-next, verifying one record and no premature assignment.

The initial focused run passed 138 tests; 23 overlapping browser/email checks
passed after the final mobile action-bar and checkbox layout adjustment. The final
28 source-control checks passed, including unsupported files and body-only mail.
Full normal/shuffled CI and release gates remain required. No live Drive, Gmail,
notification or personal data was used; real Google preview access and staff
completion times have not been measured. No schema or dependency change.

The broader manual registration flow, progressive request-entry controls,
queue-return context and unified request execution remain later increments in
DOCUMENT_EXPERIENCE.md. This increment is implemented for review; only #596 has
explicit merge authorization in the current request.
