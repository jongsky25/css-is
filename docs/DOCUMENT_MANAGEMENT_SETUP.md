# Documents: implementation and acceptance setup

This implements the D1–D11 application paths behind **disabled** switches. It is not D12
launch acceptance. No live files, mail, spreadsheet imports, accounts, or deployment settings
were changed during implementation. Documents now reuses the existing Workspace connections:
`CSS_DOCS_RELAY_URL` / `CSS_DOCS_RELAY_SECRET` for Drive, OCR and signing, and
`CSS_MAIL_RELAY_URL` / `CSS_MAIL_RELAY_SECRET` for official dispatch. The Apps Script
implementations are included; they still require updating the existing deployments and live
acceptance. No new Workspace account, OAuth connection or model-provider account is required.

The travel connection already has live evidence in [PR #261](https://github.com/jongsky25/css-is/pull/261):
the relay answered and all seven templates were created from the office forms. Some older travel
setup statements saying it had never run were stale. That evidence does not establish that the new
Documents operations have been deployed or live-tested.

## Safe evaluation

1. Back up the database with the repository's SQLite backup tooling. Use a copy for acceptance.
2. Run `storage.init_db` on that copy. The additive schema is repeatable. All existing APIs retain
   their commit behavior unless explicitly passed `commit=False` by Documents.
3. Agree the named workflow/grant administrators with the owner. While both switches are disabled,
   sign in as an active system administrator and open **Administrator → Documents setup**
   (`/admin/documents/setup`). Enter the existing active account emails, one per line, and record
   who authorized the appointments. Select **Review appointments**, verify every account, check the
   confirmation box and select **Appoint these administrators**. Include everyone in this initial
   batch: setup closes after saving. Each selected account receives the bureau-wide `grant_admin`
   and `workflow_admin` roles, with the operator and reason in the business event/platform audit.
   No accounts, records-officer roles, signing permissions or restricted-document access are created.
   Neither switch changes. The system administrator receives no implicit Documents role.

   Existing grant-administrator history (including revoked grants), or the completion marker, closes
   this initial setup route. Later changes belong to designated grant administrators; losing every
   grant administrator requires an explicitly authorized server-side recovery. A stale preview is
   rejected if an account changes or either switch is enabled before confirmation.

   For an offline acceptance database, the existing operator tool remains available:

   ```sh
   python tools/configure_documents.py --db /path/to/acceptance.db --grant-admin 123 --reason 'Named by records owner for acceptance'
   ```

   This also records authorization in the business event and platform audit logs. It changes neither
   switch and does not infer grants from the technical-admin role. Other records/signatory grants
   are managed on `/documents/rules` by the designated grant administrator.
4. On the acceptance instance, open **Administrator → Documents setup** as an active system
   administrator who also has a bureau-wide Documents `grant_admin` appointment. Under
   **Documents feature**, enter the reason, confirm **Enable Documents with sending disabled**,
   then select **Enable Documents**. This sets `documents.enabled=1` and keeps sending off.
   The page also allows an active system administrator to disable Documents and sending together;
   each setting change records the actor/reason and rejects stale submissions. Enablement applies
   to the whole instance, with normal record permissions enforced; it is not a private sandbox.
   An offline database operator can alternatively use `storage.set_setting`. Keep
   `documents.sending_enabled=0` until deliberately testing delivery with authorized recipients.
   Both settings default to `0`, including on repeat migration. Never enable the production
   module solely because the local tests passed.
5. Run the application with `CSS_DB` pointing at the copy. Office → Documents shows the registry.
   All authenticated write forms carry a session-bound CSRF token. Service actions reload active
   accounts and resolve current grants/directory/OIC authority, rather than trusting posted roles.
6. Configure versioned rules, timing, release and closure evidence in Rules and policies.
   Missing settings fail closed for the affected transition; no default signing authority,
   official mailbox, deadlines, retention period or sender is silently selected.

## What is implemented

| Increment | Application implementation | Acceptance still required |
|---|---|---|
| D1 | Additive tables, annual Manila numbering, serialized transactions, optimistic revisions, explicit scoped grants, directory/OIC checks, shared visibility, append-only events and platform audit | O02/O05/O10 policy sign-off and deployment-copy migration |
| D2 | Incoming/outgoing intake, receipt/reference metadata, missing-scan handling, verification/correction, restricted views, Drive link validation, duplicate warnings | Representative office intake and sensitive-submission policy |
| D3 | Declarative rule conditions, priority/conflicts, immutable successor versions, activation/disable/restore, preview, explicit reevaluation, assignments, directives and lead reconciliation | Initial rule catalog, authority limits and unmatched fallback sign-off |
| D4 | Durable immediate notice intent, in-app queues, access-checked email, send feature/preview/CLI registry, retries with evidence, unknown-operation handling | Scheduler cadence, real delivery and revoked-access acceptance |
| D5 | Explicit/default working-day dates, buffered contributor dates, internal milestones, 3/1/due notices, collapsed elapsed reminders, urgency, overdue escalation and deadline history | O03 exact timing/anchor decisions; confirmed holiday years |
| D6 | Numbered independent outgoing drafts, many-to-many relationships, directory-authorized review routes, exact-version approval, material invalidation/minor lineage, approvals inbox | Authority and minor-change classification policies |
| D7 | External signed-copy recording; signatory-only durable stored-signature request, source fingerprint and own-identity confirmation, result lineage | Redeploy the existing Docs relay; validate marker placement, signed PDF layout and access live |
| D8 | Release checklists, existing-email/physical evidence, direct-send operation contract, recipient outcomes, acknowledgment, duplicate gates and read-only receipt reconciliation | Redeploy the existing mail relay with Gmail API enabled; validate official sender and recipient-level evidence |
| D9 | Bounded relay extraction request, sanitized untrusted suggestions/excerpts, explicit field confirmation, no persistent extracted content, manual fallback | Redeploy existing Docs relay; validate Google Drive OCR against scanned/ambiguous/protected/oversized files |
| D10 | Configured closure evidence, mandatory-contribution checks, released-reply gate, reopening, receipt linking, merge preview and correction with retained history/access intersection | Owner acceptance of type-specific evidence and correction procedure |
| D11 | My actions/register/verification/review/release/unassigned queues, overview metrics, scoped record search/CSV, calendar candidate check and explicit link/private reminder | Role-based user acceptance and complete bureau-wide browser journeys |

D0 is not falsely marked complete. Open policy values in the plan remain unresolved. D12 and
D13 remain unimplemented. External adapter deployment and the live checks above are **first-release
blockers**, not deferred features or optional scope. The development implementation is ready
for review and configuration; it is not a claim that all D1–D11 acceptance criteria have passed.

## Policy semantics

- Rule fields are `type`, `field` (subject/sender/type), `keywords`, `mode` (any/all/exact),
  `priority`, proposed `lead_id` / `lead_unit_id`, contributing `unit_ids`, `assignees`, and `policy`. No executable expressions are accepted.
- Conflicting leads are never silently resolved by priority. All proposed people receive scoped
  preverification access and notices. A concerned officer confirms the lead. Equal-priority
  conflicting policy values remain unset and are shown as conflicts.
- Unmatched records are visible to their submitter and authorized verifying officers. No named
  fallback recipient is invented; directory Director/OIC and explicitly granted records officers
  are included where their authority and access allow.
- `default_days` requires `anchor` (`receipt` or `registration`). `buffer_days` proposes an internal
  working-day deadline. Explicit weekend/holiday dates stay unchanged. Officers set/extend external
  dates; lead/officers adjust internal milestones with reasons.
- Deadline scheduling requires `cutoff`, `reminder_time`, `escalate_chief_days`, and
  `escalate_director_days`. Times are Manila wall-clock times. The escalation values are calendar
  days after the due date; advance reminders use working days. Reminders collapse elapsed milestones,
  and are deduplicated by record/assignment, date, recipient, milestone and reopened cycle.
- Mark holiday-year coverage explicitly with `documents.holidays_confirmed.YEAR=1` only after
  review. Having one holiday in a year does not prove full coverage.
- `release` and `closure` list evidence labels. `signature_required` and `ack_required` must be
  explicitly configured before release. The closure label `released_reply` additionally requires
  linked outgoing replies to be released; all mandatory contributions must be completed independently
  of evidence text. Do not infer a document's actual action from unreviewed spreadsheet blanks.
- Restricted access is explicit even for Director, records officers, signatories and workflow admins.
  Manage access before assigning a restricted record. Changing app visibility never changes Drive ACLs.
- A minor revision requires an officer's classification and explanation. It retains an annotated
  approval lineage, but **always invalidates the old signature**. Material edits, changed directives,
  and policy reevaluation invalidate approval/signing.
- Merge leaves original records, receipts, files, assignments and dispatches in place, with a canonical
  redirect and readable original authored timeline. Canonical readership becomes the intersection.
  Reversing a merge retains restricted access and requires reconciliation; no history is deleted.
- Calendar links live in Documents. New private calendar reminders have the generic title
  “Document follow-up” with no document title/number/link, so later document-access revocation does
  not leave private correspondence content in calendar audiences. Rescheduling is explicitly handled
  in Calendar. CSS surveys are never created automatically.

## Update the existing Workspace deployments

No new relay URLs or secrets are needed. The obsolete draft `DOCUMENTS_RELAY_*` settings are no
longer used. Keep the current `CSS_DOCS_RELAY_*` and `CSS_MAIL_RELAY_*` values on the Space.

### Existing travel Docs Apps Script project

1. Update `travel_docs.gs` from `apps_script/travel_docs.gs`. Its existing `ping`, `check_link`
   and `generate_doc` actions remain unchanged; the addition dispatches `document_*` actions.
2. Add `apps_script/documents_relay.gs` as another script file in that same project. Keep the
   existing `travel_templates.gs`, template properties, `SHARED_SECRET` and travel `ROOT_FOLDER_ID`.
3. The **Drive API v3** service used by the existing template maker must be enabled.
4. Set a separate `DOCUMENTS_ROOT_FOLDER_ID` to an office-controlled **private correspondence
   folder**, accessible to the relay owner and only designated recovery operators. It stores signed
   outputs and durable operation receipts. Do not use a broadly shared travel folder without reviewing
   its access. The app does not change Drive ACLs. Staff must be given appropriate access to released
   copies through the office's Drive process; app permissions alone do not grant Drive access.
5. Add an hourly time-driven trigger for `cleanupDocumentOcrTemps`. Normal extraction permanently
   deletes its temporary OCR document in `finally`; the trigger removes this module's tagged OCR
   imports older than an hour after a terminated script or an ambiguous import response. Temporary
   OCR imports are created in the owner's My Drive, without inheriting shared output-folder permissions.
6. **Deploy → Manage deployments → Edit the existing deployment → New version → Deploy.** Keep
   Execute as Me and the same endpoint; authorize any newly requested Drive/Docs scopes.

### Existing mail Apps Script project

1. Keep the **same existing shared-secret value**. If the old script declares it inline, put that
   existing value into Script Properties as `SHARED_SECRET`. Do not put it in source control or chat.
2. Replace the old mail script with `apps_script/mail_relay.gs` and add the same
   `apps_script/documents_relay.gs` companion file. There must be just one `doPost` in this project.
   Legacy messages still use the existing secret/body/html/attachment envelope and `MailApp.sendEmail`.
3. Add **Gmail API v1** and **Drive API v3** under Services. Official Documents dispatch uses Gmail's
   message API to obtain message IDs; existing notifications continue using MailApp.
4. Set `DOCUMENTS_ROOT_FOLDER_ID` to the private correspondence folder accessible to this relay owner.
   The mail identity must also be able to read the final Drive files; no automatic sharing is performed.
5. Redeploy a **New version of the existing deployment**, keeping its URL, and authorize the new scopes.
6. Set application setting `documents.official_sender` to the existing relay mailbox or one of its
   authorized Gmail aliases. This is the approved From address, not a new account. The relay rejects
   any other sender. Keep `documents.sending_enabled=0` until authorized acceptance testing.

### Supported document operations

- **Inspect:** checks Drive accessibility and returns `drive-v3:<file-id>:<version>` from Drive v3.
  For exported attachments it checks the version before and after export. Size is bounded to 20 MiB;
  access proves access for the relay identity only.
- **Extract:** reads Google Docs, bounded Google Sheets (20,000 cells), and UTF-8 plain text directly.
  PDFs and PNG/JPEG/GIF scans use Google Drive's OCR import to a temporary Google Doc. Plain PDF text
  and scans follow the same conversion path. No additional AI/model provider is used. Extracted text
  is limited to 100,000 characters, and only bounded suggestions/excerpts reach the confirmation UI.
  Deterministic label matching suggests subject, sender, references, type and keywords. A deadline is
  suggested only when exactly one valid ISO date appears on deadline-related lines; ambiguous dates
  stay unconfirmed. OCR quality, protected PDFs and Google conversion limits require live testing.
- **Preview/sign:** native Google Docs use exactly one `{{OFFICE_CONNECT_SIGNATURE}}` marker on a
  paragraph of its own, inserted **before approval**. The preview checks the approved source and
  marker, links to that source, and shows the signer's current profile signature. On confirmation,
  the app loads only that authenticated signatory's existing `storage.user_signature`; it never trusts
  uploaded signature bytes or another actor ID from the form. The operation pins the signature hash;
  replacing the profile signature before execution blocks that queued request. Signature bytes are
  sent transiently inside the signed request, not saved in job/event/receipt metadata. The relay checks
  actor/signatory identity and hash, copies the exact approved source, replaces the marker with the
  proportional image (maximum 160 × 80 pixels), and creates a separate signed PDF in Drive. The
  working copy is removed; the original is untouched. Existing PDFs/Sheets use the external-signature
  workflow. This is an image signature, not certificate-based digital signing. Validate real layouts.
- **Dispatch:** exports/pins the approved file bytes with a before/after version check, then attaches
  those bytes to one email per recipient from the existing mailbox/authorized alias. Native Docs,
  Sheets and Slides export to PDF; binary files retain their MIME type. The cover subject includes
  the registry number and subject, with an editable cover message. No external send occurs from rules
  or extraction. Each message has an operation-derived RFC Message-ID. Gmail's returned message ID
  is stored as transport-acceptance evidence, independently of expiring notification logs.
- **Status:** reads the stored receipt without repeating the effect. After an uncertain Gmail call,
  it searches Sent by exact RFC Message-ID and checks message identity/recipient/sender. A missing
  hit is **not** proof of no send. Recipients never attempted after an interrupted send are identified
  separately as confirmed failures, so a subsequent request can target those recipients only.

The existing travel HMAC envelope is reused: `{ts, payload, sig}`, timestamp in **milliseconds**,
HMAC-SHA256 over `ts.payload`, five-minute acceptance window. Actions are namespaced `document_*`.
Docs allows inspect/preview/extract/sign/status; mail allows dispatch/status. Every operation result
carries the same `operation_id`. Bodies, signatures and arbitrary provider errors are not logged.

The Python client follows Apps Script ContentService 302/303 responses using **GET only** to
`script.googleusercontent.com`, at most three times; it never forwards the signed POST to a redirect
or automatically retries an effect. Responses are bounded to 1 MiB and timeout is 90 seconds.
An old deployment's `{ok:true}` alone is never accepted as an official dispatch receipt.

Durable receipts are JSON files in `document_operation_receipts` under the configured private folder.
A script lock serializes claims, and the semantic request hash prevents reusing an operation ID with
changed inputs. State is persisted before an external effect. A repeated request returns its existing
result or `unknown`, never blindly reruns. Do not edit/delete these receipts to force retries. A crash
at an unavoidable Drive/Gmail boundary may leave an output requiring manual reconciliation; operation
IDs are included in generated file names and receipts. Recovery operators must reconcile these before
issuing another operation. No automatic correspondence retention is enabled.

## Live checks after updating existing deployments

The runtime available during implementation has no deployed relay credentials, so none of these
checks has been performed by this change:

1. Existing travel relay ping, link check and representative Docs/Sheets form generation still work.
2. Existing mail test and calendar attachment still arrive at an authorized test address.
3. Inspect a readable/unreadable file; change a source after approval and confirm signing/release block.
4. Extract a clean Doc, a scanned PDF, an unreadable/protected PDF, an ambiguous date and oversized input;
   confirm manual entry survives failures and tagged OCR artifacts are removed.
5. Preview and sign a representative Doc using the signer's saved profile signature. Visually compare
   the PDF, check marker placement and signature size, and verify a different account cannot sign it.
6. Send an approved synthetic final document to authorized recipients. Confirm sender, attachment,
   per-recipient Gmail receipt and a repeated status query without additional mail. Test interrupted
   delivery and manually reconcile an uncertain outcome before any retry.

D12 launch remains gated on these results and the office-policy decisions in the plan.

## Scheduler and recovery

`python send_reminders.py --documents --dry-run` previews notice delivery without changing records.
The existing scheduled-job registry also includes `documents`/`job_documents`; wire its cadence for
prompt delivery during acceptance. Notice generation and external operations remain quiet when the
module is off; sending also requires `documents.sending_enabled=1` and the mail feature setting.
Immediate notices are enqueued in the originating transaction; in-app tasks do not depend on email.

Delivery attempts are claimed before network I/O. Successful notices are not resent by repeated runs.
A crashed/ambiguous notice is visible for a human to reconcile/retry; the application does not promise
exactly-once delivery from a non-idempotent SMTP service. Access is rechecked before delivery, and email
contains only an authenticated app link. For notices the configured directory email is preferred.
Official dispatch uses the stronger durable operation/recipient protocol above.

Emergency rollback: disable sending, then disable module writes. Existing permitted records remain
readable. Preserve operation IDs, official sequences and event history. Restore metadata using SQLite
backup procedures and separately check original/signed Drive artifacts. Reconcile external receipts
before replaying anything. No new correspondence retention/purge rule is enabled.

## Verification evidence

Synthetic tests live in `tests/test_documents.py` and `tests/test_documents_routes.py`. They exercise
concurrent annual numbering/year rollover; rollback including audit/notices; restricted/direct-ID
access and spoofed roles; OIC scopes; stale edits; rule conflicts; holidays and explicit Sunday dates;
version/approval/signature gates; complete outgoing release/ack/closure; unknown-send receipt queries;
untrusted transient extraction; merge/correction; calendar confirmation; delivery access revocation;
CSRF and disabled/read-only HTTP behavior. No test uses live external recipients.

Chromium checks on a separate synthetic database: register incoming → verify → browse register;
rule page rendering; no horizontal overflow at 390px; desktop register at 1280px.
`qa_preflight.py` is green. Full-suite baseline and final counts are recorded in the implementation PR.
Live external-service acceptance, production-directory inspection, file-format visual validation and
D12 launch rehearsal have not been performed.

### Transient PDF intake

The first step of **Receive or prepare correspondence** accepts a local text or scanned PDF
or a public HTTPS PDF link. **Read and pre-fill** fills empty fields and offers
replacements for existing entries. Review every suggestion and its page evidence
before registering. A source link used for reading is separate from the optional
Drive reference link that is saved on registration.

The `/documents/intake/read` endpoint accepts raw `application/pdf` bytes or JSON
`{"url":"https://…"}`, with the existing session and an `X-CSRF-Token` header.
Raw uploads avoid multipart temporary-file spooling. Files, extracted text, and
suggestions stay in memory; responses use `Cache-Control: no-store`. The reader
does not call the Drive OCR relay or an AI provider and does not write database
records. Existing registration still saves only the confirmed form fields and
any separately entered attachment reference.

Limits: 6 MiB, 50 pages, and 100,000 extracted characters. Extraction is conservative:
it recognizes labelled subjects, senders, document types, document dates,
deadlines, and references; conflicting or ambiguous values remain for manual
entry. Sparse-text pages use local English OCR, including in mixed text/scan PDFs.
OCR processes at most 10 pages per request at up to 200 dpi (12 million pixels per
page), with a 45-second overall processing budget and a 15-second Tesseract timeout
per page. PDFium rendering is serialized because the library is not thread safe;
concurrent OCR requests receive a retry message. Page images are rendered to memory
and piped into Tesseract through stdin; recognized text returns through stdout.
No temporary PDF/image files or Drive OCR artifacts are created. OCR-derived
suggestions retain page evidence and show a review warning for names, numbers,
and dates. Encrypted, malformed, or unreadable PDFs still require manual entry.

The Docker image installs `tesseract-ocr` and `tesseract-ocr-eng`; Python dependencies
include `pypdfium2`. Local installations also need Tesseract with English language
data on PATH. There is no external OCR service or credential requirement.
Private Drive links should be downloaded by
the user and selected locally; no account cookies or credentials are forwarded.

Link reads require public HTTPS on port 443. DNS addresses and every redirect are
validated, and TLS connections are pinned to a validated IP while retaining
hostname certificate checks. Downloads are size bounded with network timeouts.
This downloader requires direct HTTPS egress; it deliberately does not inherit
credential-bearing proxy configuration. If deployment egress is proxy-only,
local PDF selection remains available.

The older `/documents/intake/preview` relay endpoint remains for compatibility;
it is not used by this first-step reader. Existing registered-document extraction
and signing workflows retain their existing storage behavior.

PDF intake reports selection and validation status before reading. Files over
6 MiB are explicitly marked as not uploaded/read (OCR did not run). Successful
reads identify OCR page numbers or direct text extraction and expose an expandable
transient preview (up to 2,000 characters per page, first 10 pages). Preview limits
are labelled. The Remove file / clear reading button clears the selected source
and displayed reading, aborts the browser request, and ignores late responses.
Already entered/applied form values remain for review. Server processing already
underway can finish within its existing limits; its response is discarded.
