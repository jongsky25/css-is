# Incoming document understanding — candidate 9.99

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
on the permitted document detail page. It is an intake snapshot; post-registration
editing, search filters, task conversion and automatic section routing are outside
these first increments.

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
