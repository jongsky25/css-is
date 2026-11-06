# Incoming document understanding — candidate 10.00

The registration form and Drive intake review now capture up to five requests,
with requested action, expected output, recipient named in the source, request
deadline, submission details, source passage/location, interpretation and
individual reviewer confirmation. Primary and optional secondary focus areas
have a separate confirmation. Sender requests remain separate from internal
instructions; this feature never creates assignments, sends notices, or changes
routing rules by itself.

## Reading and review

Local PDF/native-text and selected-page OCR results include conservative English
phrase matches such as “please submit” or “requested to provide.” Each request
suggestion includes its source passage and page. The reviewer explicitly adds a
suggestion into an empty request slot, edits its details, and confirms it. The
extractor suggests literal deliverables following submission/preparation verbs,
named subjects immediately before “are/is requested,” explicit deadline dates
and submission channels within the same request passage. Every detail carries
its own source evidence; the reviewer checks and corrects the suggested details. Ambiguous, indirect, multilingual and handwritten requests can be
missed. No language model or new vendor is involved.

Focus suggestions use a controlled starter vocabulary in
[`documents_understanding.py`](../documents_understanding.py): governance,
financing, workforce, service delivery, information/reporting, capacity development
and administration. They are topic suggestions, not approved section assignments.
The reviewer chooses the primary and secondary topic. Updating this vocabulary
currently requires a code change; there is no administrator vocabulary editor.

Only supplied pages/text are analyzed. Existing selected-page coverage warnings
remain visible; absence of a recognized request means “unclear,” never “no action.”
“For information only” wording is a suggestion requiring explicit human
confirmation. It cannot be saved alongside a populated request. More than five
matches produces an overflow warning; remaining requests must be recorded
separately. Details and evidence can also be entered without JavaScript or OCR.

Local source changes retain entered corrections for comparison but clear all
confirmations and suggestion controls. Rereading resets confirmations. Drive
content changes discard structured understanding from the affected draft while
preserving other registration fields; sibling attachment changes invalidate the
primary email review confirmations. Existing revision and content checks still
block stale submissions.

## Drive relay activation

The application requests `understanding: true` on content-checked intake extraction.
The updated [`documents_relay.gs`](../apps_script/documents_relay.gs) returns at
most the existing 100,000-character extraction limit as transient
`understanding_text`, only for that explicit intake request. The server extracts
bounded requests and focus evidence and never persists the full text. Drive
conversion does not preserve trustworthy page numbers: the UI explicitly says
“page unavailable,” and a reviewer may enter a source location.

Deploy a new version of the existing Docs/travel relay web app before enabling
these Drive suggestions in production. The existing endpoint/secret is reused.
An older relay remains compatible: manual entry works and an explicit unavailable
message replaces request analysis. Local PDF reading does not require the relay.
This implementation does not deploy the relay or application.

## Storage and access

An additive, idempotent `document_understanding` table records bounded reviewed
fields, reviewer ID and creation time in the same registration transaction.
Failed confirmation or validation rolls back the document, number and review.
Registration receipts retain existing retry semantics. Saved understanding appears
on the permitted document detail page. Authorized staff can revise it through the review page described below. Search
filters, task conversion and automatic section routing remain outside these increments.

Unlike earlier intake metadata-only suggestions, this feature deliberately retains
bounded supporting passages in intake suggestion JSON and the reviewed snapshot.
They inherit existing intake/document access and database/backup retention. Full
OCR text and binary images remain transient. Browser rendering uses text nodes or
Jinja escaping; passages are never executable instructions or HTML. No browser
storage, content logging, model calls or new dependencies were introduced.

## Verification

Synthetic tests cover page mapping, multiple requests, unknown readings, explicit
information-only confirmation, field bounds, invalid dates/classifications,
registration rollback, persistence, source changes, old relay fallback and
transient text. The real Apps Script harness checks opt-in text and source binding.
Real registration-route browser tests cover phone layout, literal hostile text,
individual confirmation, edits, changed sources and saved detail rendering.

The full normal/shuffled suite and dependency audit remain required in CI before
any production release. Real office scans and physical iPhone validation remain
additional acceptance work; synthetic passing checks do not establish live OCR
accuracy.

## Request-detail extraction (9.99)

The parser uses the existing transient text and requires no additional relay API,
model or dependency. The 9.98 relay update is still necessary for Drive text.
Local PDF and Drive suggestions use the same parser. Review cards show each
suggested detail with its evidence before the user adds it to an empty request
slot. Adding a suggestion never confirms it or overwrites existing entries.

Deadline recognition requires an explicit marker such as “by,” “on or before,”
“not later than” or “deadline:”, followed by a complete ISO date or full English
month/day/year date. Event dates introduced only by “on” are not deadlines.
Ambiguous numeric dates, missing years, relative dates, invalid calendar dates,
competing alternatives and conflicting explicit deadlines stay blank with a
warning. Identical repeated dates are accepted. Deadlines are not resolved from
the receipt date or copied across neighboring requests.

Multiple explicit requests within a sentence are split at their request phrases.
Named recipients are extracted only when their subject is wholly present, never
from a “to” destination or inferred organizational responsibility. Pronoun-only
outputs remain blank. Long passages are bounded and warn that additional details
may be outside the reading. Adjacent sentences, unmarked imperatives, complex
coordination and abbreviated months remain manual-review cases.

## Saved-review corrections and history (10.00)

The incoming document detail page links to **Review requests and focus areas /
history**. Staff with the existing document work permission can correct saved
requests or add the first review to older records. They must confirm populated
requests and focus areas, choose the request status, enter a reason/source checked,
and confirm the overall review. The form starts with confirmations unchecked.
Editing any field clears the overall confirmation; editing a request or focus
field clears its own confirmation too. Manual entry works without JavaScript.

The additive `document_understanding_revision` table preserves each reviewed
snapshot, reviewer ID, timestamp and reason. Existing intake snapshots are copied
into revision 1 on the first correction, preserving their original author and
time; no bulk rewrite of old documents occurs. Older records without a snapshot
start at revision 1 with their first review. The latest snapshot remains in
`document_understanding` for the existing detail view. History shows at most ten
reviews per page with an older-reviews link, and inherits current document access.

The save and history append run inside the document transaction. A stale document
revision cannot overwrite a newer review. Invalid confirmation, invalid data or
audit failure rolls back the entire change. Validation errors preserve submitted
entries; stale forms retain their old revision and offer a link to compare the
latest review in a new tab. No silent overwrite or automatic retry occurs.

Saving increments the document revision, records the review revision and reason
in its existing audit/event stream, flags reconciliation and uses the existing
change-notification/linked-work invalidation path. It does not create assignments,
replace Director instructions, set the document-wide deadline, change routing or
call external services. Reviewers can explicitly clear a mistaken interpretation
by selecting “unclear” with a reason; the original remains in history.

Editing is blocked for outgoing, merged, archived, closed/cancelled, approval and
released documents, and while the module is disabled. Existing visibility rules
still apply, including restricted-record and linked-work access. A viewer without
work permission can inspect permitted history but cannot edit it. The history and
editor responses are no-store; content is escaped and bounded by the existing
field limits. Review snapshots and reasons inherit database/backup retention.
