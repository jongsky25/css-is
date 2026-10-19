> For the unified review queue, My Drive/Shared Drive support, body-only email,
> and the current rollout, see [Document workspace setup](DOCUMENT_WORKSPACE_PHASES.md).
> The sections below describe the earlier incremental implementation. Enabling the
> new intake workflow routes future Gmail imports through review before numbering.

# Gmail document intake: incremental implementation

## Byte-array compatibility update (v7.14)

An office pilot diagnostic confirmed that the Apps Script advanced Gmail service
returns `MessagePartBody.data` as decoded byte arrays for both bodies and attachments.
The former string-only reader rejected these with `gmail_body_unavailable` and
`attachment_size`, even when the actual and declared byte counts matched.

Replace **only `gmail_documents_import.gs`** in the existing mail project with the
updated file. It now accepts signed/unsigned byte arrays and base64url strings,
checks numeric byte ranges and size limits, and retains the attachment's exact
expected length and Drive checksum checks. No web-app redeployment is needed.
Keep the existing properties, receipt indexes, folder IDs and other script files.

For receipts created by the failed pilot, run **`retryGmailDocumentReadFailures`**
once with the importer configured/enabled, then run **`importGmailDocuments`**.
The retry function reads at most the first 20 indexed receipts and resets only
pending/blocked `gmail_body_unavailable` or `attachment_size` failures without a
saved request payload or confirmed uploaded files. It validates mailbox/folder
binding, records the executing mailbox and repair reason, and preserves reserved
file IDs and source metadata. It does not itself download, upload or submit mail.
Completed imports and other failures are untouched. For later receipt pages use
the existing individual `retryGmailDocument` control with the receipt ID and reason.
Genuine size mismatches will fail validation again. Confirm the live import result
before scheduling the trigger; synthetic checks do not establish live acceptance.

## Phase 1 — intake foundation

Implemented locally: an authenticated machine endpoint, disabled-by-default switch,
mailbox/account binding, transactional registration, attachment provenance and duplicate
tracking. No Gmail polling, Drive uploads, trigger, or production configuration is included.
The sender supplies links to files already saved in Drive; link syntax is validated but
live file accessibility and content are not checked in this phase.

The endpoint creates incoming, pending-verification, preverification-visible records.
The type is `Unclassified`. Rules, assignments and inferred deadlines are deferred; a
records officer must classify the record and explicitly reevaluate routing through the
existing workflow. Normal registration notices and append-only audit history are retained.
No email body or attachment bytes are stored. Files are reference attachments, not approved
versions. Existing application permissions and independent Drive permissions still apply.

### Configuration for an acceptance instance

In v7.13 and later, open **Documents → Intake → Drive and Gmail intake settings**
(`/documents/intake/settings`). The **Work email / Gmail** section lets an active
account with bureau-wide Records officer and Workflow administrator grants select
the mailbox, records owner and intake switch. The owner dropdown contains only active
accounts with bureau-wide Records officer authority. Saving rechecks those grants.
Enabling requires Documents enabled, a hosting intake secret of at least 32 characters,
the unified review queue enabled and a recorded successful Drive check. The page only
reports secret presence/length; matching it to Apps Script is verified by a signed import.
Pause remains available if the importer account or hosting secret later becomes invalid.
This form does not change Drive settings, create accounts/grants, start Apps Script or
install a trigger. Keep the importer paused until these settings are saved, then run a
manual import and check the Waiting queue before scheduling it.

Use the existing server-side settings mechanism (`storage.set_setting`) to configure:

| Setting | Value |
| --- | --- |
| `documents.enabled` | `1`, after existing Documents setup |
| `documents.gmail_intake_enabled` | Defaults to `0`; set to `1` for acceptance |
| `documents.gmail_mailbox` | Exact mailbox email address |
| `documents.gmail_actor_id` | ID of a designated active account with a bureau-wide Documents `records` grant |

Set environment variable `CSS_GMAIL_INTAKE_SECRET` to a dedicated random secret of at
least 32 characters. Keep it outside source control. This is a separate inbound credential,
not the existing outbound mail or Docs relay secret. The importer account is rechecked for
active status and its records grant on every request, including duplicate requests.
No role or account is created automatically. Disabling intake stops new and retry requests.

### Request contract

`POST /integrations/gmail/documents` accepts UTF-8 JSON, bounded to 64 KiB:

```json
{
  "mailbox": "office@example.test",
  "message_id": "19abc123",
  "subject": "Incoming memorandum",
  "sender": "Sender <sender@example.test>",
  "received_at": "2026-10-17T10:00:00+08:00",
  "attachments": [
    {
      "attachment_id": "gmail_attachment_id",
      "drive_url": "https://drive.google.com/file/d/sourcefile12345/view"
    }
  ]
}
```

Only these fields are accepted. Use Gmail's API message ID, not the RFC Message-ID.
One message creates one record with 1–20 reference attachments. Received time must carry
a timezone. The server chooses direction, type, actor, verification and permissions.

Required headers:

- `X-CSS-Timestamp`: Unix timestamp in **seconds**, a ten-digit decimal string.
- `X-CSS-Signature`: lowercase hexadecimal HMAC-SHA256, using the intake secret, of
  `timestamp + "." + exact raw request body bytes`.

Use HTTPS. The timestamp must be within five minutes of the server clock. The exact
endpoint bypasses browser session authentication and enforces its own signature; browser
cookies confer no intake authority. There is no broad public integration-path exemption.

Responses:

- `201`: `{ "document_id": 123, "duplicate": false }`.
- `200`: same document ID with `duplicate: true` for an identical retry.
- `400`: invalid payload or Documents disabled.
- `401`: missing/invalid signature, expired timestamp, or missing/short server secret.
- `403`: intake disabled, mailbox mismatch, inactive account, or missing records grant.
- `409`: same mailbox/message ID with different normalized content; investigate, do not
  automatically create a new message ID to bypass the conflict.
- `413`: request exceeds the body limit.

Uniqueness is `(mailbox, message_id)`. Registration, reference attachments, audit events,
sequence allocation and the import row commit together under an immediate transaction.
Concurrent retries serialize. Reordering attachments does not create a conflict. A retry
must reuse the original metadata and Drive file links; it must not upload new copies.
An expired signed request can be resigned with a fresh timestamp and identical payload.

Successful imports are tracked in `document_email_import` with status `registered`, source
identifiers, a normalized payload hash, received time and attachment provenance. The document's
verification status remains separate. Invalid or rolled-back requests leave no import row.
Phase 5 keeps failure/attempt history and operator controls with the Apps Script/Drive checkpoints; rejected requests do not create Python import rows.

### Validation

Run `python -m pytest -q tests/test_documents_email.py tests/test_documents.py`.
Tests use temporary SQLite databases and synthetic metadata, without external services.

## Phase 2 — Gmail discovery and preview

Implemented in `apps_script/gmail_documents.gs`. Add it as a companion file in the
existing mail Apps Script project. It declares no `doPost` and does not change the
existing mail relay. Enable the **Gmail API v1** advanced service if not already enabled.
The script uses the executing account's mailbox and checks it against the configured
address; an alias alone does not select a different mailbox.

### Configure and preview

1. In the target Gmail mailbox, create a user label such as `CSS-Documents`.
2. Create a Gmail filter using the approved sender/subject criteria and apply that
   label automatically. Choose criteria using representative office mail. Existing
   labeled messages are eligible only when their received time meets the start date.
3. Add these **Script Properties** in the existing Apps Script project's settings:

   | Property | Example / requirement |
   | --- | --- |
   | `GMAIL_DOCUMENTS_PREVIEW_ENABLED` | Exact value `true`; absent means disabled |
   | `GMAIL_DOCUMENTS_MAILBOX` | Primary mailbox address, e.g. `office@example.test` |
   | `GMAIL_DOCUMENTS_LABEL` | Exact user label name, e.g. `CSS-Documents` |
   | `GMAIL_DOCUMENTS_START_AT` | Required ISO instant with timezone, e.g. `2026-10-17T00:00:00+08:00` |
   | `GMAIL_DOCUMENTS_PAGE_SIZE` | Optional, defaults to `25`; range `1`–`100` |

4. Select **previewGmailDocuments** in the Apps Script editor and run it manually.
   Authorize Gmail reading if prompted. No web-app redeployment or intake secret is
   needed for an editor-run preview. The Phase 1 CSS-IS intake switch can remain off.
5. Inspect the JSON in the execution log: `candidates`, `excluded`, `errors`, and
   `next_page_token`. This explicit preview logs correspondence metadata (subject,
   sender, filenames and IDs), so restrict project/log access appropriately. Bodies,
   attachment bytes, secrets and raw provider errors are not logged.
6. If `next_page_token` is non-null, inspect the next page with an editor wrapper:

   ```javascript
   function previewNextGmailDocumentsPage() {
     console.log(JSON.stringify(previewGmailDocumentsPage('PASTE_NEXT_PAGE_TOKEN'), null, 2));
   }
   ```

   Continue manually until the token is null. Do not reuse tokens after changing
   filters/configuration; restart the preview. A token is not an import checkpoint.

Do **not** create a scheduled trigger for this preview function. Use the separate Phase 3
importer below for attachment storage and message checkpointing. This preview
never creates Drive files, posts to CSS-IS, marks mail read, changes labels, or sends mail.

### Candidate selection

- Gmail search is scoped by the exact label ID and start instant, excluding spam,
  trash, sent mail and drafts. Each returned message is checked again for label,
  folder and exact received-time eligibility (including the start boundary).
- MIME parts are traversed for PDF, plain text, supported Office formats and PNG/JPEG/GIF
  attachments. Inline/CID signature images, archives, attached emails, empty or oversized
  files (over 20 MiB), and parts without downloadable attachment IDs are excluded.
- One candidate groups all supported attachments of one email. Missing/oversized subject
  or sender fields, more than 20 attachments, and repeated attachment IDs require review.
  `ready_for_import` means only that metadata passes these preliminary checks; it is not
  approval, a content safety check, or confirmation that the document belongs in the registry.
- Unsupported attachments are listed alongside supported ones. Emails with no supported
  attachments are excluded. Message inspection errors are reported without stopping other
  messages in the page. MIME depth/part limits bound malformed messages.
- Only one bounded page is read per invocation. Preview is repeatable and stores no cursor.
  Gmail's full-message API supplies the MIME structure; body content is ignored, and
  attachment bytes are never fetched. Filenames/MIME types are metadata, not file validation.

Run `python -m pytest -q tests/test_gmail_documents_script.py` for ten simulated Apps
Script contracts. Live mailbox matching, account authorization and quota behavior still
require an office acceptance preview; no live Gmail account was accessed during this build.

## Phase 3 — attachment storage and automatic registration

Implemented in `apps_script/gmail_documents_import.gs`. The importer uses the Phase 2
selection rules, uploads supported attachments and submits the Phase 1 signed request.
Preview remains read-only and is still a separate function. Importing does not mark mail
read, change labels, send email, approve records or apply document routing rules.

### Acceptance setup

1. Deploy the Phase 1 Python code and apply its additive database migration using the
   application's normal initialization. Configure its mailbox, records actor, dedicated
   intake secret and enablement switch as described above.
2. Add `gmail_documents_import.gs` and `gmail_documents_ops.gs` beside `gmail_documents.gs` in the **same** existing
   mail Apps Script project. Enable **Drive API v3**, in addition to **Gmail API v1**.
3. Choose an office-controlled private folder in the executing account's **My Drive**.
   The importer does not create or modify sharing permissions. Check that its inherited
   access is limited to designated records/recovery staff. Shared drives are not supported
   by this first importer. Checkpoints and attachments both live in this folder.
4. Keep the Phase 2 Script Properties and set these additional properties:

   | Property | Value |
   | --- | --- |
   | `GMAIL_DOCUMENTS_IMPORT_ENABLED` | Exact `true` to enable; absent/off prevents importing |
   | `GMAIL_DOCUMENTS_FOLDER_ID` | Private destination folder ID |
   | `GMAIL_DOCUMENTS_INTAKE_URL` | Exact HTTPS endpoint, e.g. `https://your-host/integrations/gmail/documents` |
   | `CSS_GMAIL_INTAKE_SECRET` | Same dedicated secret as the Python endpoint |

   Both preview configuration and import enablement are required. The endpoint must be
   directly reachable without a redirect or interactive login. Secrets stay in Script
   Properties/environment variables, never source files or execution logs.
5. Run **importGmailDocuments** manually with a narrow test label/start date. Authorize
   the required Gmail read, Drive write and external-request scopes. Confirm the files
   and one pending-verification registry entry, then run again and confirm no duplicates.
6. After acceptance, add a **time-driven trigger every five minutes** for
   `importGmailDocuments`, owned by the configured mailbox account. No trigger is
   installed automatically by this code. Editor/time-trigger execution does not require
   changing the existing relay web-app deployment.

### Checkpoints and retries

- A script lock serializes invocations within this one Apps Script project. Use only
  **one importer project** per mailbox; a second project has independent checkpoints.
- Before creating a receipt, the script reserves a Drive ID and stores it under a
  `GDI_RECEIPT_<hash>` Script Property. Receipt JSON pins the original candidate metadata,
  destination/endpoint binding, reserved attachment IDs, checksums and registry payload.
- Every attachment ID is reserved and checkpointed before upload. After an ambiguous
  upload, the next attempt reads that same ID and verifies location, source identity,
  size and checksum. It never allocates a replacement merely because a request timed out.
- The exact JSON payload is checkpointed before HTTP. A timeout after registry commit
  retries the same payload with a fresh signature; the server returns the existing record.
  A failed final receipt update is recovered the same way. Success records the document ID.
- Requests use HTTPS with redirects disabled. Only a valid `200`/`201` document receipt
  marks completion. Other HTTP statuses and malformed responses leave the receipt pending.
- One invocation inspects up to five messages (or the smaller configured page size).
  A scan token advances through pages and resets at the end, so completed recent messages
  do not permanently prevent older candidates from being examined. A four-minute budget
  stops starting additional candidates and retains the current page. An individual Google
  or HTTP operation can still consume the remaining Apps Script execution time.
- Phase 5 retries saved pending receipts independently of Gmail discovery, with backoff
  and attention states as described below. If the source email is deleted before all
  attachment bytes have been saved, restoring the source may still be necessary.
  Invalid discovery page tokens restart the scan on the next run.

Execution reports include registered/already-registered counts, review-needed and excluded
counts, excluded attachment counts, and message IDs with bounded error codes. They do not
log subjects, senders, filenames, secrets or raw provider errors. Unsupported attachments
are not uploaded; inspect the Phase 2 preview before enabling filters for a document type.

Do not delete checkpoint properties, receipts or attachment files to force retries. Do not
change the destination folder or endpoint for unfinished receipts: binding checks stop those
imports rather than silently redirecting them. Keep the same project/properties when upgrading.
The current per-message Script Property index is bounded by Google's property-storage quota;
when exhausted, new imports fail before creating files. Phase 5 exposes property capacity and bounded recovery controls, but does not delete or
compact this identity index: deleting it could allocate duplicate Drive files. Capacity
planning remains necessary for a large archive backfill; this version targets a limited
mailbox pilot.

### Validation

`python -m pytest -q tests/test_gmail_import_script.py tests/test_gmail_documents_script.py tests/test_documents_email.py tests/test_documents_workspace.py`

The importer harness exercises 23 contracts, including interrupted file/receipt creation,
registry timeouts, permission failures, checksum conflicts, redirects, config changes and
replays. A cross-language test sends the exact JavaScript-signed UTF-8 payload to the Python
endpoint and verifies that replay creates no duplicate. All services are simulated; live
Drive permissions, Gmail scopes, hosting reachability and trigger operation require acceptance.

## Phase 4 — review imported records and extraction suggestions

The registry now marks imported records **Imported from Gmail** and provides two queues:

- **From Gmail** shows imported records the current user may view.
- **Gmail: needs verification** shows pending/correction imports the current user is
  authorized to verify. Closed, cancelled and merged originals are excluded. Search,
  visible counts and CSV export use the same permission-filtered queue.

On a permitted record, the source panel identifies the mailbox, Gmail API message ID,
received instant and registration time. This is provenance, not permission to open the
mailbox. Document access remains governed by the existing visibility and scoped records
rules; restricted records do not become visible just because they were imported.

For an open record the user can work on, **Suggest fields from an imported attachment**
selects an existing reference attachment. The server resolves its Drive URL from the
record's own file versions; a submitted file-version ID from another record is rejected.
The existing arbitrary-Drive-link extraction form remains available for other sources.

Extraction uses the existing configured Docs relay (`CSS_DOCS_RELAY_URL` and
`CSS_DOCS_RELAY_SECRET`) and its supported formats. Phase 3 can store Office attachments
that the extractor does not read directly; those remain available for manual review.
No extraction is triggered by the Gmail importer itself.

The suggestions screen links to the selected source and shows escaped, untrusted excerpts.
Subject, type and sender remain editable and are applied only when the user explicitly
confirms them with a reason. Deadline/reference/keyword suggestions are displayed separately;
deadlines still require an officer's explicit deadline action. Extraction does not change
business fields, verification, ownership or due dates. It records operation/audit metadata.
Confirmed field changes remain pending verification and require explicit routing reevaluation.

Suggestions and excerpts are not persisted; the response uses `Cache-Control: no-store`.
The confirmation form retains the revision captured before external extraction, so another
person's intervening correction cannot be overwritten by a stale suggestion form. Permission
is checked again before returning the result. If extraction fails, the original fields and
manual correction form remain available, with a generic error rather than provider details.

Validation: `python -m pytest -q tests/test_documents_gmail_review.py tests/test_documents_email.py tests/test_documents.py tests/test_documents_workspace.py`

The tests cover queue/CSV permissions, restricted records, verification/correction transitions,
attachment ownership, CSRF, explicit field confirmation, transient/escaped excerpts, failure
fallback, and stale suggestions after concurrent corrections. Live extraction still requires
acceptance against the configured relay and representative office files.

## Phase 5 — retry operations and sync health

Add `apps_script/gmail_documents_ops.gs` to the **same** Apps Script project before using
this version of `importGmailDocuments`. Existing receipts are compatible; missing attempt
and history fields are initialized on first use. No new Python schema or secrets are needed.
The operational interface is the Apps Script editor and its execution reports. This phase
does not add a remote operations dashboard to CSS-IS or expose controls on a public endpoint.
Only designated staff who already have access to the script project should operate it.

### Automatic recovery

Each run first inspects a rotating page of up to 20 reserved receipt IDs, including receipts
for messages no longer returned by Gmail. It attempts eligible pending work before newly
discovered candidates, sharing a five-message/four-minute budget. A discovery failure does
not prevent saved work from recovering. Pending receipts use their pinned metadata, IDs and
payload. Completed receipts are never resubmitted merely because they appear in recovery.

Attempts and their next eligible time are checkpointed before effects. Retry delays begin
at one minute and double to a one-hour maximum; the actual attempt occurs on a subsequent
scheduled invocation. After eight failed attempts, the receipt needs operator attention.
Known request/auth/configuration conflicts (`400`, `401`, `403`, `404`, `409`, `413`), missing
previously uploaded files, or attachment identity/size conflicts require attention sooner.
Transient timeouts, `429` and server errors remain retryable within the attempt limit.

Each receipt retains its latest 30 attempt/failure/recovery events, last error code, attempt
count, last attempt, next retry time, and final registry document ID. This is bounded retained
history, not a permanent audit archive. The operational properties also retain the latest
20 run summaries and 10 pause/resume events. Raw provider errors and correspondence bodies
are excluded. Existing business registration audit history in CSS-IS is unchanged.

An unreadable/missing receipt is reported by reserved ID; it is never replaced with a new
identity. If receipt creation failed before any candidate metadata was saved, rediscovery
of the original message is still needed to reconstruct it at the reserved ID. Restore
permissions or the original checkpoint rather than deleting the index to force progress.

### Inspect health and failures

Run **gmailDocumentsStatus** in the editor. Its JSON execution report shows:

- Importer paused/enabled state; current run state and last run/finish times.
- `last_success_at`: last completed batch without errors, attention or deferred work;
  this is not proof the entire mailbox has been synchronized.
- A stale-trigger flag when enabled and no run has started within 15 minutes. A terminated
  run can remain `running`; check its start time and the Apps Script execution history.
- Recent run summaries, pause/resume history, receipt states and retry/error history.
- Receipt-index count and approximate Script Property bytes, with a warning above 400 KiB.
  Google quotas still apply; quota failures stop progress rather than discarding identities.

The receipt page contains at most 20 items. When `next_offset` is present, use a wrapper
calling `gmailDocumentsStatus(next_offset)` to inspect the next page. Health describes the
last batch and recovery page; it does not claim global failure counts for uninspected pages.
The status report is read-only and works while importing is paused. Restrict execution-log
access because message/receipt IDs and operator reasons are included.

### Pause and resume

1. Set Script Property `GMAIL_DOCUMENTS_OPERATOR_REASON` to a short reason (1–500 characters).
2. Run **pauseGmailDocuments** or **resumeGmailDocuments** in the editor.
3. Confirm the returned `paused` or `ready` state and inspect the status report.

Controls record the effective Google account and reason. They share the importer lock: if
an import is running, the control reports busy and must be retried after it finishes. A pause
leaves triggers/checkpoints/files in place; subsequent trigger calls exit without importing.
Resume validates configuration and destination access before retaining enablement. It does
not itself import, create a trigger, enable the Python intake switch, or override Gmail
permissions. Remove a trigger separately if you no longer want paused invocations to run.

### Retry a corrected failure

1. Use the status report to identify the receipt and its error. Resolve the underlying
   cause first (credentials, endpoint, folder access, source availability or conflict).
2. Set `GMAIL_DOCUMENTS_RETRY_RECEIPT_ID` to that exact indexed receipt ID and
   `GMAIL_DOCUMENTS_OPERATOR_REASON` to the recovery reason.
3. Run **retryGmailDocument**. It records the operator/reason, resets the retry budget,
   clears the delay and directs the recovery scan to that receipt.
4. Resume if paused, then run the importer or allow the next trigger to process it.

This command schedules work only. It never alters the pinned registry payload, Drive file
IDs, or stored source metadata and cannot retry a completed or unknown receipt. A conflict
will recur until its underlying cause is resolved. Do not edit an uncertain payload or
change its source ID to bypass server duplicate checks.

Validation adds failure recovery without Gmail discovery, interrupted operations, exponential
backoff, retry exhaustion, bounded recovery scans, operator retry restrictions, stale health,
and pause/resume behavior. Tests use simulated Google services plus the real Python intake
endpoint. Production quotas, permissions, execution timing and outage recovery still require
Phase 6 acceptance with the office mailbox.

## Next increments

6. One-mailbox acceptance pilot, access checks and gradual filter expansion.

True Gmail push notifications remain optional after scheduled polling is validated.

### Authentication retry after updating the importer

The importer signs and sends the same UTF-8 byte array, including email text.
Replace `gmail_documents_import.gs` in the existing Apps Script project to apply
this change. For a receipt blocked by `intake_http_401`, set Script Properties
`GMAIL_DOCUMENTS_RETRY_RECEIPT_ID` to its receipt ID (from `gmailDocumentsStatus`)
and `GMAIL_DOCUMENTS_OPERATOR_REASON` to the repair reason. Run
`retryGmailDocument`, then `importGmailDocuments`. This preserves the pinned
payload and existing file IDs; completed receipts are not reset.

Pilot verification on October 19, 2026: the operator reported `queued: 1`,
`already_queued: 1`, and `errors: []` after applying the byte-signing update.
