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
may be outside the reading. Adjacent sentences, unmarked imperatives and complex
coordination remain manual-review cases. Abbreviated month support is described below.

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


## Proposed work from a reviewed request (10.01)

Open **Review requests and focus areas / history**, then the saved request's
work link. Save corrections first. Confirmed explicit, inferred or manually
entered requests with status Requests can produce one shared work item and one
unassigned contribution in Proposed status. Unclear interpretations must be
resolved first. Review the title (250 characters), required expected output,
concerned unit and optional target date, then explicitly confirm creation.
The source's named recipient is never mapped automatically to a staff account.
The concerned officer still confirms responsibility through the existing workflow.

Creation requires enabled Documents and Shared work, current document visibility,
document work permission, and an active incoming record outside approval/release.
Director routing must be issued before shared work starts. Existing official
deadline constraints apply to the proposed contribution; the document's deadline,
instructions and assignments are unchanged. A missing output must be supplied.

An additive `document_request_work` table preserves the selected request and focus
snapshot, creator/time, case/task links and hashes. Creation, source link, audit and
receipt are atomic. Document revision and source hashes reject stale forms. The
unique document/request-position key prevents retries from creating duplicates;
a matching retry returns the existing receipt after current access checks. A
changed payload must be reconciled in the existing work. Later source corrections
show a warning on the receipt and never overwrite work. Request positions remain
reserved even if the source is cleared or replaced or work is cancelled. This
increment does not append to existing cases or propose staff owners automatically.

Receipt access requires both current document and linked work access; history
snapshots do not introduce additional readership. The receipt retains the original
source, not the complete OCR text. Drive analysis still requires manual activation
of the existing Docs/travel relay update; this increment adds no relay changes.


## Source and work comparison (10.02)

The request work receipt now compares the preserved source to the latest saved
review, alongside current contribution title, output and target where applicable.
Changed fields are expanded; unchanged fields are available in a disclosure.
The comparison covers requested action, output, deadline, recipient, submission,
evidence/location, interpretation/confirmation, request status and focus areas/
evidence/confirmation. It counts source-field changes, not work edits. Differences
between source and work may be intentional and are labelled without declaring the
work incorrect or complete. Current case title/status and contribution status,
unit and revision help staff identify the work they are reviewing.

A cleared request is identified explicitly while its original evidence and work
remain available. Current document AND work access are rechecked; removing the
original source link does not grant source access to other work readers. The
comparison is read-only, remains available when modules are disabled, and never
changes assignments, targets, source hashes, reconciliation flags or acknowledgments.
Use existing work controls or review the interpretation to make an authorized
change. No automatic reconciliation or new workflow action is introduced.

All source text remains escaped. The responsive comparison works without scripts
and wraps long source passages at phone width. No schema, dependency or relay
change. Drive analysis still needs the existing manual Apps Script relay activation.


## Request follow-up overview (10.03)

Incoming document detail and review pages summarize the latest saved review:
request count, interpretations needing review, visible contribution count, request
status and primary focus/confirmation. Each current request lists missing output,
recipient, deadline, submission instructions, supporting passage and source
location. These are not mandatory-source requirements: absent details may simply
not appear in the document. This is not a new OCR run or a completeness score.

Accessible contributions show their current status and source-change warning,
with a link to the preserved source/comparison. Cleared request positions retain
that link for current work readers. Work status/counts and cleared receipts are
omitted for document readers who cannot access that work. No staff assignment or
completion is inferred from a confirmed interpretation. Proposal links require
an actionable confirmed request, no existing receipt, enabled modules and the
existing editable incoming-document predicate; the proposal submission still
checks Director routing, document revision and official deadlines.

The overview is read-only and uses the same document/work access checks as the
receipt. Disabled modules retain readable existing work but do not offer new
proposals. No new schema, dependency or relay change. Drive text analysis still
requires manual activation of the existing Apps Script relay update.


## Abbreviated deadline dates (10.04)

Explicit request deadlines now accept Jan, Feb, Mar, Apr, Jun, Jul, Aug, Sep/Sept,
Oct, Nov and Dec, with an optional period, in either day-month-year or
month-day-year order. May remains a complete month name. A four-digit year and
explicit deadline marker are still required. Examples: `by 20 Nov. 2026`,
`on or before NOV 20, 2026`. Existing full names and ISO dates remain supported.
English month parsing uses an explicit map rather than the process locale.

Sentence splitting protects abbreviation periods only inside complete recognized
date spans; ordinary sentence endings and paragraph breaks still separate text.
Wrapped dates stay together, with the existing whitespace normalization. Original
spelling and punctuation are retained in evidence; only the proposed deadline is
normalized to ISO. No rewriting of OCR text or persisted reviews occurs.

Calendar validation and all uncertainty safeguards still apply. Invalid leap days,
missing/two-digit years, numeric ambiguity, alternatives/ranges, conflicting and
relative dates remain blank with a warning. Event dates without deadline markers
do not become request deadlines. Local-reader and Drive-relay text use this same
parser. Review and confirmation remain mandatory; no automatic document deadline
or assignment change. No dependency/schema/relay API change. The prior Drive relay
activation requirement remains.
