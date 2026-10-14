# Travel documents relay setup

The travel pages can make the filled-in forms (Appendix A and B, travel report, certifications, CENRR, RER) as Google Docs in the office Drive. A second Google Apps Script, running as the office mailbox, does the copying and filling. The Space talks to it over HTTPS with a signed request. It is separate from the mail relay (`docs/MAIL_RELAY_SETUP.md`) so each has its own secret and scopes.

Until this is done the travel pages still work: people paste a link to a form they made themselves.

## What a person has to do

1. **Create the script.** Sign in as the office mailbox, open <https://script.google.com>, New project, paste in `apps_script/travel_docs.gs` (the file in this repo is the source of truth).
2. **Make the templates.** For each form, convert the Word file to a Google Doc (File, Save as Google Docs) and replace the values with the `{{placeholders}}` listed in `docs/TRAVEL_FILING_PLAN.md` section 9. Check the tables, since the conversion can shift Appendix A.
3. **Make the Drive folder.** Create a root folder under the office mailbox. Generated documents go in sub-folders named after the filing.
4. **Set Script Properties** (Project settings): `SHARED_SECRET` (a long random string), `ROOT_FOLDER_ID`, `ALLOWED_DOMAIN` = `doh.gov.ph`, and one `TPL_<key>` per template: `TPL_appendix_a`, `TPL_appendix_b`, `TPL_mc114_justification`, `TPL_jo_cert`, `TPL_travel_report`, `TPL_cenrr`, `TPL_rer` (the value is the Google Doc id).
5. **Deploy.** Deploy, New deployment, Web app. Execute as: Me. Who has access: **Anyone**. Authorise the Drive and Documents scopes when asked. Copy the `/exec` URL. Every later change to the script needs Deploy, Manage deployments, New version.
6. **Set the Space secrets:** `CSS_DOCS_RELAY_URL` (the `/exec` URL) and `CSS_DOCS_RELAY_SECRET` (the same string as `SHARED_SECRET`). Restart the Space.
7. **Test.** Open Administration, Travel filing settings, press **Test the relay**. It should say the relay answered.

Other things the office has to supply, not part of this setup: name the template administrators (same settings page), load the 2027 holidays before 2027 deadlines are trusted, and send the per diem rules when they exist.

## How it is protected

- The endpoint is open to anyone, so nothing is trusted without a signature. The Space signs `timestamp.payload` with HMAC-SHA256; the script rejects a wrong signature or a timestamp more than 5 minutes off. Keep both secrets out of chat and screenshots.
- The script only copies templates it has a `TPL_` property for, only creates folders under the root folder (names limited to letters, digits, `_` and `-`), and only shares with addresses ending `@doh.gov.ph`.
- Asking for the same `request_id` twice returns the document already made, so a retry never makes a duplicate.
- `check_link` tells the Space a pasted link's file name and type if the office mailbox can open it. Only signed requests from the Space can ask.

## Things to verify live before relying on it

These could not be tested without Google (the tests fake the relay):
- replacement text containing `$` or a backslash comes out unchanged;
- `TableRow.replaceText` fills a copied row of Appendix A (merged cells);
- whether `addEditor` emails the person;
- five documents in one go finish inside one script run (Apps Script allows several minutes).

## If something goes wrong

The test button gives a plain reason. "Rejected the signature" means the two secrets differ or the Space clock is off. "The script did not run" means the web app access is not Anyone. "Not reached" means the URL is wrong or Google is down.
