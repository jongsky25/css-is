# Advisory Google Slides setup

Increment 1 of the [advisory Slides plan](ADVISORY_SLIDES_PLAN.md) (10.51). Office Connect asks the
office's existing documents relay (the Apps Script that makes travel forms, see
[TRAVEL_DOCS_RELAY_SETUP.md](TRAVEL_DOCS_RELAY_SETUP.md)) to make each advisory as a Google Slides
file. No new secret, URL or Space setting is needed: it uses `CSS_DOCS_RELAY_URL` and
`CSS_DOCS_RELAY_SECRET` that are already set. Until the steps below are done, nothing changes for
users. The new advisory pages arrive in a later update.

## What a person has to do (once)

1. **Add the script file.** Sign in as the office mailbox and open the travel documents Apps Script
   project. File, New, Script, name it `advisory_slides`, and paste in `apps_script/advisory_slides.gs`.
   Also replace `travel_docs.gs` with the version in this repository (it now hands `advisory_*`
   requests to the new file). The Drive API service (v3) is already on for travel.
2. **Make the master template.** In the editor, choose `makeAdvisoryTemplate` and Run. Allow the
   Slides permission it asks for. It copies the office template
   ([BLHSDTO-Advisory-Template](https://docs.google.com/presentation/d/1T750K6cphrzOo6_-3GlP_9vdEt-fKXLWnZSjCGWbHY4/edit))
   into the `_templates` folder, changes the sample number to `{{number}}`, and saves the copy's id as
   the `TPL_advisory` property. The Execution log shows the master's link.
3. **Put the placeholders in the master** (open the link from step 2). Every slide in the master is
   one choice people will see, so delete the sample slide if it should not be offered. On each slide,
   replace the sample words with these placeholders, typed exactly with the double braces. Format
   them as you like: font, size and colour carry over to the filled-in text.

   | Placeholder | Filled with | Example from the sample |
   |---|---|---|
   | `{{number}}` | Advisory number | 2026-1113-001 (done by step 2) |
   | `{{title}}` | Advisory title | Confirmation of Participants for JOAS under UNA Batch 2 |
   | `{{dates}}` | Activity dates | December 15-17, 2026 |
   | `{{venue}}` | Venue or "Online" | venue TBA |
   | `{{message}}` | The main paragraph | We are actively finalizing the logistics… |
   | `{{attention}}` | Who it is for | LHSD Division Chiefs, Heads of HPUs… |
   | `{{contact}}` | Contact names, phone, email | Mr. June Dela Cruz … blhsd@doh.gov.ph |
   | `{{link}}` | The main link, printed | https://bit.ly/joasbatch2confirm |
   | `{{qr}}` | The QR code picture | Make a square box whose only text is `{{qr}}`; the code replaces the box at the same size and place. |

   A slide does not need every placeholder. Any part you leave as ordinary text stays as it is, and
   people edit it freely in their copy. The deadlines table can stay as ordinary text for people to
   edit.
4. **Check.** Run `checkAdvisoryTemplate` and read the Execution log. It lists each slide's
   placeholders and which ones are missing. "Missing" is only a reminder, not an error.
5. **Deploy a new version.** Deploy, Manage deployments, edit, New version, Deploy. The web app keeps
   the same `/exec` URL.

To start over, delete the `TPL_advisory` property and run `makeAdvisoryTemplate` again.

## How it is protected

- It uses the same signed requests as travel: nothing happens without the Space's signature.
- The relay only creates, copies or changes files under `ROOT/advisories/`, and refuses any other file.
- It only shares with `@doh.gov.ph` addresses, without Google's "shared with you" email.
- Asking to create with the same request id returns the file already made, so a retry never
  makes a duplicate.
- A review copy (PDF and image) is refused if someone edits the slide while it is being copied.
  The app checks each copy against its SHA-256 digest before saving it.

## Still needs a live check by a person

Synthetic tests (`tests/test_advisory_slides.py`, Node harness `tests/js/advisory_slides_harness.js`)
cover the script's logic with fake Google services. These need a real run after deployment:

- the filled text keeps the placeholder's formatting, and long text wraps sensibly;
- the QR picture lands in the `{{qr}}` box at the right size;
- the slide picture export (`/export/png`) works with the script's sign-in;
- `Drive.Permissions.remove` and the `commenter` role behave as expected, and nobody is emailed;
- open Slides comments are read back with their replies.
