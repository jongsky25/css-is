# Document workspace: implementation and rollout

## Office process

Office scans land in a dedicated To Review folder. Eligible messages from the
configured office Gmail mailbox join the same unnumbered queue. A records reviewer
checks the source, uses OCR when appropriate, and confirms the details. Only then
is a permanent identifier allocated. Incoming records wait for the Director/OIC's
digital routing instruction before chiefs and technical staff begin assigned work.
Existing draft, shared-work, approval, signing and dispatch paths remain available.

## Architecture and cost

- Retain FastAPI/Jinja, SQLite WAL, the current Google Workspace relays and Drive.
  No separate database, new paid service or model subscription is introduced.
- Keep source files in Drive. SQLite stores queue metadata, review drafts, bounded
  OCR field suggestions, routing instructions and durable operation state.
- PDFs, PNG/JPEG/GIF and text support explicit OCR. Office binary attachments
  (DOC/DOCX, XLS/XLSX, PPT/PPTX) support manual review and filing, up to 20 MiB each.
  Native Google Docs drafts remain linked through the registered workspace.
- Body-only messages have an Email body box and No attachment note in both intake
  and the registered workspace. They have no synthetic Drive file, OCR or filing
  job. Text is bounded to 16,000 characters, escaped for display and preserves line
  breaks. HTML-only email is converted to text. Empty/unreadable or oversized bodies
  require attention rather than silent truncation. Bodies are omitted from discovery
  and health logs; pinned importer receipts and the database retain the captured text.
- Queue pages load 30 entries. Discovery reads at most 100 metadata entries per
  page every 180 seconds while the app runs; each tick processes at most five
  pending filings. Ordinary queue views do not call Drive or OCR. Sleeping hosts
  do not run discovery. Keep the existing single application worker configuration.

## Review, registration and routing

- Bureau-wide records authority is required for queue access. Configuration also
  requires bureau-wide workflow-admin authority. Read access in the application
  never grants Google Drive permissions.
- Review claims last 30 minutes and saving renews them. Revision checks prevent
  stale updates. Changed content invalidates OCR suggestions and current review.
- Each email is one entry with its attachments grouped, sender, subject and received
  time prefilled, and original message ID/timezone-bearing receipt retained. A changed
  sibling invalidates the group's review. Dismissing/restoring affects the group.
- Signed webhook replay is idempotent. Importer retries retain the same attachment
  IDs and payload. Source markers prevent partially uploaded messages appearing as
  standalone scans; JSON receipts are excluded from discovery.
- Registration checks exact source versions outside the database transaction, then
  atomically rechecks revisions, allocates one identifier and records pending filing.
  A lost response never requires another number. Incoming assignment is deferred
  until Director instruction; previously registered records retain their lifecycle.
- Filing moves and renames the same file IDs into Filed/<registration year>/Incoming
  or Outgoing. Receipt dates remain independent. Retry the same durable operation
  after a timeout; checksum and operation markers reconcile an uncertain move.
- The Director selects a lead, office, additional recipients and optional action due
  date beside the source preview/body. Instructions, explicit access, assignments and
  notices are recorded atomically. Registered history respects later restricted access.

## Deployment through the existing GitHub workflow

The repository's `.github/workflows/deploy-hf.yml` deploys pushes to `main` to the
existing Hugging Face Space. Submit the application change as a pull request;
merging triggers the canonical `deploy_hf.py` with repository deployment secrets.
There is no need to download an application ZIP or deploy from a personal computer.
Keep the existing backup and persistence checks; do not bypass a failed backup gate.
The script checks the actual live persistence setting. Historical documentation
contains conflicting persistence descriptions, so local tests do not establish the
live storage mode or restart durability.

Apps Script projects are updated separately from the GitHub application deployment:

1. Pause Gmail import with `GMAIL_DOCUMENTS_IMPORT_ENABLED=false`. Inspect pending
   receipts before changing any existing destination. A receipt is bound to mailbox,
   folder and endpoint; reconcile unfinished receipts rather than resetting indexes
   or reuploading old messages to bypass a binding conflict.
2. In the existing Docs/travel project, update the main script from `travel_docs.gs`
   and its `documents_relay.gs` companion. Preserve templates, secrets and existing
   folder properties. Edit the existing web-app deployment to New version; keep its
   endpoint and execution/access settings.
3. Set `DOCUMENTS_INTAKE_FOLDER_ID` to To Review and `DOCUMENTS_FILED_FOLDER_ID` to
   Filed in that project. They must be distinct folders: both in the office account's
   My Drive, or both in the same actual Shared Drive. Cross-storage moves are blocked.
   Keep Filed outside To Review. The relay needs list/create/move/rename authority.
   Keep processing/signing receipts (`DOCUMENTS_ROOT_FOLDER_ID`) and travel output
   (`ROOT_FOLDER_ID`) in their separate existing roles.
4. In the existing mail project, update/add `gmail_documents.gs`,
   `gmail_documents_import.gs` and `gmail_documents_ops.gs`. Retain the existing
   main mail relay, project identity and Script Properties. Enable Gmail API v1
   and Drive API v3. These editor/time-trigger importer functions need no web-app
   redeployment. Run `gmailDocumentsStatus` while paused to inspect its status.
5. Set `GMAIL_DOCUMENTS_FOLDER_ID` to the SAME To Review folder. Keep the mailbox,
   label, deliberate start instant, signed intake endpoint and dedicated secret
   configured as described in `GMAIL_DOCUMENT_INTAKE.md`. Update existing projects
   in place; a new project would lose the receipt index. Confirm actual folder sharing
   and privacy for receipts, especially when several staff upload to the inbox.
6. Merge/deploy the application, verify version 7.03 and successful backup/deployment
   status in GitHub Actions. An active records/workflow-admin account opens Documents
   → Intake → Drive intake settings, enters the same two folder IDs and enables it.
   Documents itself must also be enabled. The saving account becomes the sync actor;
   revoking its authority stops discovery. Check Drive now performs a bounded refresh.
7. Enabling the workflow sets `documents.gmail_review_queue_enabled=1` permanently
   for normal operation. Pausing Drive keeps emails queued and never restores direct
   registration. Installations that have never enabled it retain the older Gmail
   registration behavior. Enable Gmail only after the updated app is configured.
8. Keep the existing five-minute Gmail trigger and label/date selection. Each invocation
   attempts at most five messages. A `queued` receipt acknowledges handoff to app review,
   not completed registration or staff action. The app tracks subsequent status.

## Pilot and live acceptance

Use narrow test correspondence: one scan, one email with multiple attachments and
one body-only email. Confirm one queue entry per correspondence, correct sender/time
and body text, source access for the reviewer, no premature number or assignment,
one number after confirmation, filing of every attachment, and Director-first routing.
Exercise replay, interrupted filing and an attachment change during review. Test
preview/Drive permissions with actual reviewer, Director and recipient accounts;
moving folders can change inherited access. Verify polling and database persistence
across an application restart. Do not treat a successful folder metadata read as
proof of upload/move authority or completed processing.

For the current office setup, the user verified both My Drive folders and their exact
property names in the Docs/travel execution log. The mail project can read its existing
processing folder. The user reports updating the Docs relay and installing the mail
scripts; the importer status showed paused, zero indexed receipts and no recorded runs.
Live endpoint behavior, remaining Gmail settings and application deployment still need
acceptance. Office folder IDs and credentials belong in configuration, not this guide.

## Verification and further increments

The October 19 release check passed 328 document/shared-work/relay/deployment tests.
These cover discovery replay, grouped
registration and dismissal, review claims, number rollback, restricted access,
revocation, source changes, body display, Director-only routing, and importer recovery.
The relay harness also checks My Drive filing and a lost response without repeating a
move. Tests use synthetic services and do not access office files or mail.

Earlier Chromium walkthroughs exercised intake → OCR → registration → Director
instruction → recipient access with synthetic accounts/preview; the 390px mobile
view had no horizontal overflow. Real Google login/embedding remains a pilot check.
A prior local 10,000-entry queue measurement returned one page/counts in a median
1.3 ms, without Drive calls; it is not a production latency guarantee. The legacy
all-document register/export retains its previous visibility implementation.

The next release adds page annotations, editable memo drafts and explicit search indexing
for supported Drive files. Existing restricted records should not be placed in the general
unregistered intake audience;
queue access currently requires bureau-wide records authority.

### Memorandum drafts, page annotations and Drive text (v7.18)

On an active outgoing record, someone with document work access can download an
editable Word memorandum draft. The internal and response layouts include record
context and user-entered fields. The draft is not an official letterhead or a final
artifact: review it, store the approved copy in Drive, then attach it through the
existing exact-version workflow. Downloading never approves, signs or dispatches.

Each listed file version has a page-annotation view. Permitted workers and the
assigned formal reviewer can add page-numbered notes; all current document viewers
can read them. Pen marks use a browser-selected local PDF, rendered by the bundled
PDF.js. The browser sends only the PDF SHA-256 and normalized strokes; the PDF bytes
stay in the browser. Before saving, the app checks the SHA-256 and Drive version
through the existing Docs relay. Notes and marks are append-only and tied to one
file version. They do not alter the Drive file or its approval state. For a native
Google Doc or non-PDF file, use page notes or the file's own Drive comments.

A permitted worker may explicitly index or remove searchable text for a current
draft or reference file. The Docs relay reads Google Docs, bounded Sheets, UTF-8
text, PDFs and supported image scans, confirms the file version before and after,
and deletes temporary OCR copies. Up to 100,000 characters are stored in the
application's search index and backups. Results are a snapshot, not a live read of
Drive. Search exposes file snippets only to the indexer or accounts explicitly
granted document access, and still applies the current document visibility check.
Drive sharing remains separate. If a Drive file changes, attach it as a new version before indexing again;
older draft indexes are excluded from current search results. An unchanged
version can be indexed again or its index removed.

To activate PDF matching and file-text indexing, replace **both**
`apps_script/documents_relay.gs` and `apps_script/travel_docs.gs` in the existing
travel Docs Apps Script project, then deploy a **new version of the same web app**.
Keep its URL, secrets, project properties and other script files. The application
fails closed for those actions until the updated relay is running. Memo drafts and
page notes need only the application release.

The **My actions** screen now collects unread tagged instructions, active document
contributions, formal reviews, Director routing and lead follow-up. It shows due
dates without treating unknown dates as overdue. Division chiefs and OICs can use
**Division follow-up** to see accessible records in their division with unresolved
ownership, overdue dates, changed instructions or outstanding contributions.
Migrated contributions remain in **My shared work**. Every card follows current
document access, so revoking access removes it from the screen.

Instruction tagging is available in the Documents workspace: type `@` in an
instruction to select a person or section, or use the accessible tag list. The
first Director routing instruction expands section tags into current active staff
and assigns those recipients through the existing routing flow. Later notes can be
posted by people working on the document; they notify only tagged staff who already
have document access, and never grant restricted access or alter approval/release
authority. Section membership comes from each staff account's current directory
section. The selected people and sections are saved with the instruction; recipients
can find tagged instructions in **Instructions for me** and mark them read. Sending
and any live delivery still require the existing module
configuration and acceptance checks.

The register and office-wide search now find words in stored record details,
references, receipt evidence, instructions and saved email bodies. The searchable
index is backfilled from existing records on migration and follows later edits; results
and excerpts use the same document visibility check as the register. Drive file
contents and temporary OCR output are not retained or indexed. Searching those
files requires a separate retention and indexing decision, especially for restricted
correspondence.

## Diagnosing a failed intake check

The Intake page preserves a specific diagnostic after a failed check and clears it
on the next successful listing. Known codes distinguish missing application relay
configuration, signature rejection, unknown intake actions, folder mismatch, HTTP
or timeout errors and local processing stages. Credentials, request URLs and arbitrary
provider text are not included. A successful editor listing does not verify the
application’s endpoint or the web app’s deployed code/execution account. Keep Gmail
paused until the application records a successful Drive check.

## Intake OCR source checks (v7.08)

Update only `documents_relay.gs` in the existing Docs/travel project and publish a
new version of the existing web app. The extract action is already allowlisted;
keep Code.gs, templates, secrets, folder properties and the deployment URL.

The app sends the queued content checksum and inbox binding for intake OCR. The
relay verifies the current file metadata, the actual blob handed to OCR, and the
file content/folder again afterwards. It returns the verified content key and latest
fingerprint. Metadata-only version drift is allowed for this unregistered-intake
mode; real content changes or moves block caching. Requests without intake mode
retain their previous strict version checks. Old relay replies without content
provenance are not accepted for caching; the reviewer sees an update instruction.
Suggestions contain only bounded fields/warnings, and temporary OCR files are still
removed. No content-check behavior for signing or approval is relaxed.

### v7.09 OCR pilot follow-up

Update `documents_relay.gs` in the existing Docs/travel project and deploy a new version of its existing web app. In an already reviewed intake item, use **Read scan again with OCR**, then **Fill empty fields with suggestions**. Existing entered values are preserved. Check the original PDF before registration: OCR supports labelled routing-slip fields but cannot guarantee recognition of every page, table or handwritten note. Ambiguous dates, direction and actual office receipt time require review. No additional OCR vendor or service is introduced.

### v7.10 originating-office direction rule

Direction now follows the reviewed Sender / originating office when saving, applying suggestions or registering: the full Bureau of Local Health Systems Development name or the standalone BLHSD abbreviation means Outgoing; other identified senders mean Incoming. Existing OCR suggestions gain the derived direction without another OCR call. The rule also applies to Gmail documents; email delivery alone no longer forces Incoming. Correct the sender if OCR misreads it. This is an application update and requires no further relay deployment.
