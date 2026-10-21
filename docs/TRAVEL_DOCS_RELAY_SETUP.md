# Travel documents relay setup

The travel pages can make the filled-in forms (Appendix A and B, travel report, certifications, CENRR, RER) as Google Docs in the office Drive. A second Google Apps Script, running as the office mailbox, does the copying and filling. The Space talks to it over HTTPS with a signed request. It is separate from the mail relay (`docs/MAIL_RELAY_SETUP.md`) so each has its own secret and scopes.

Until this is done the travel pages still work: people paste a link to a form they made themselves.

## What a person has to do

1. **Create the script.** Sign in as the office mailbox, open <https://script.google.com>, New project, paste in `apps_script/travel_docs.gs` (the file in this repo is the source of truth).
2. **Make the templates (one script does it).** The office's forms are Word files (Appendix A and B, the Post Travel Report, the Job Order certification, the MC 114 sheet) and Excel files (CENRR and RER). Add `apps_script/travel_templates.gs` to the same Apps Script project (File, New, Script, paste it in). At the top, set `TM_SOURCE_FOLDER_ID` to the id of the "Travel Reimbursement Template" folder (the part of its address after `/folders/`); the office mailbox must be able to open that folder. Also add the Drive API service (Services, the + beside it, Drive API, version v3, Add). Run `makeTravelTemplates` once, allow the permissions it asks for, and read the Execution log. It converts each file into a Google Doc or Sheet in a `_templates` folder inside the root folder, swaps the sample names, dates and amounts for the `{{placeholders}}` listed in `docs/TRAVEL_FILING_PLAN.md` section 9, saves each template's id as its `TPL_<key>` property, and lists any placeholder that did not land. Open each template once and check it looks like the original. `checkTravelTemplates` re-checks them later. To redo one template, delete its `TPL_` property and run again.
3. **Make the Drive folder.** Create a root folder under the office mailbox. Generated documents go in sub-folders named after the filing.
4. **Set Script Properties** (Project settings): `SHARED_SECRET` (a long random string), `ROOT_FOLDER_ID` and `ALLOWED_DOMAIN` = `doh.gov.ph`. The seven `TPL_<key>` properties (`TPL_appendix_a`, `TPL_appendix_b`, `TPL_mc114_justification`, `TPL_jo_cert`, `TPL_travel_report`, `TPL_cenrr`, `TPL_rer`) are set for you by `makeTravelTemplates`; a value is the id of a Google Doc, or of a Google Sheet for `TPL_cenrr` and `TPL_rer`.
5. **Deploy.** Deploy, New deployment, Web app. (After adding the template script or changing any script file, use Deploy, Manage deployments, edit, New version, so the web app picks up the change and its permissions.) Execute as: Me. Who has access: **Anyone**. Authorise the Drive and Documents scopes when asked. Copy the `/exec` URL. Every later change to the script needs Deploy, Manage deployments, New version.
6. **Set the Space secrets:** `CSS_DOCS_RELAY_URL` (the `/exec` URL) and `CSS_DOCS_RELAY_SECRET` (the same string as `SHARED_SECRET`). Restart the Space.
7. **Test.** Open Administration, Travel filing settings, press **Test the relay**. It should say the relay answered. The press also records the script version; the checklist's **Choose file or take photo** button appears only once the relay has answered as version 2 (the version with `upload_file` and `trash_file`). After updating the script, use Deploy, Manage deployments, New version, then press **Test the relay** again.

Other things the office has to supply, not part of this setup: name the template administrators (same settings page), load the 2027 holidays before 2027 deadlines are trusted, and send the per diem rules when they exist.

## The claim forms (7.60)

The office's current forms live in the "Claims Templates" Drive folder, one sub-folder per claim: **Cash Advance**, **Liquidation** and **Reimbursement**, each with a blank and a "Sample" file. The app now makes:

- a **cash advance**: Appendix A alone (`TPL_appendix_a`, made from `Sample [CASH ADVANCE / PERA] .docx`);
- a **liquidation**: Appendix A and Appendix B as **one document** (`TPL_claim_liq`, from `Sample [LIQUIDATION] .docx`), with the Cash Advance and Reimbursement lines under the total;
- a **reimbursement**: Appendix A and B as one document (`TPL_claim_rei`, from `Sample [REIMBURSEMENT] .docx`), with the "Expenses Incidental" column heading.

The one document is credited to both the Appendix A and the Appendix B checklist rows. A liquidation's Appendix A is now always required (before, only when the itinerary had changed).

To set up: replace `travel_templates` in the Apps Script project with the new version (it already holds the Claims Templates folder id in `TM_CLAIMS_FOLDER_ID`; the mailbox must be able to open that folder), then run `rebuildClaimTemplates()` and read the Execution log. It lists every placeholder that did not land, as before; send that log if any are missing. `debugTravelTemplates()` prints how the converted tables and checkbox lines really look. The old `TPL_appendix_b` is no longer used.

The liquidation sample lists the evidence before the justification; the reimbursement sample (and the blank forms) put the explanation first. Each template follows its own sample.

## How it is protected

- The endpoint is open to anyone, so nothing is trusted without a signature. The Space signs `timestamp.payload` with HMAC-SHA256; the script rejects a wrong signature or a timestamp more than 5 minutes off. Keep both secrets out of chat and screenshots.
- The script only copies templates it has a `TPL_` property for, only creates folders under the root folder (names limited to letters, digits, `_` and `-`), and only shares with addresses ending `@doh.gov.ph`.
- Asking for the same `request_id` twice returns the document already made, so a retry never makes a duplicate.
- `upload_file` saves a photo or PDF (JPG, PNG, WebP, PDF, under 7 MB) in `ROOT/<filing>/<checklist row>/`, so a row with several files links to one folder, and shares that folder (view only) with the claimant's `@doh.gov.ph` address. The Space keeps only the folder link and id, never the file. `trash_file` trashes an uploaded folder or file and refuses anything that is not under the root folder. The Space calls it when a person removes or replaces uploaded files and when the retention purge runs (a filing whose files cannot be trashed is purged on a later run, so no file outlives its record). Uploaded files count against the office mailbox's Drive quota.
- `check_link` tells the Space a pasted link's file name and type if the office mailbox can open it. Only signed requests from the Space can ask.

## Live evidence and remaining checks

[PR #261](https://github.com/jongsky25/css-is/pull/261) records a successful live relay response
and creation of all seven templates from the office's real forms. This supersedes older notes
saying the relay/template maker had never run. Visual layout and the following behavior still
need representative live acceptance:

- replacement text containing `$` or a backslash comes out unchanged;
- `TableRow.replaceText` fills a copied row of Appendix A (merged cells);
- `makeTravelTemplates` left each converted form looking like the original (the Word and Excel conversions can shift tables, logos and merged cells), and the CENRR's single repeating line and the sample date row were removed correctly;
- a CENRR with several rides grows its rows and keeps the total underneath;
- whether the person is emailed when a document is shared (7.55: sharing now goes through `Drive.Permissions.create` with `sendNotificationEmail: false`, so it should not; `addEditor` is only the fallback);
- five documents in one go finish inside one script run (Apps Script allows several minutes).

## If something goes wrong

The test button gives a plain reason. "Rejected the signature" means the two secrets differ or the Space clock is off. "The script did not run" means the web app access is not Anyone. "Not reached" means the URL is wrong or Google is down.

## Reuse for Documents

The document-management module reuses this connection and its existing credentials. Add the
`documents_relay.gs` companion and update the current deployment as described in
[Document management setup](DOCUMENT_MANAGEMENT_SETUP.md#update-the-existing-workspace-deployments).
Existing travel actions are preserved. Document operations require their own private correspondence
folder; they do not assume the travel output folder has appropriate access.
