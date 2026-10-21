# Activity documents (DPO and invitation): one-time setup

A calendar item can say it needs a **DPO** or an **invitation** (Spot Feedback #136) and offer to draft it in Google
Docs. The app sends the item's details to the same signed relay the travel forms use. The relay fills a Google Doc
template, so the two templates must exist once before **Draft in Google Docs** can work.

Until then the button is shown, and a failed draft says the template has not been set up. Nothing else is affected.

## Steps (an administrator, once)

1. Open the Apps Script project that runs the travel relay (`travel_docs.gs`).
2. Add `apps_script/activity_templates.gs` to the same project (File > New > Script, paste the file).
3. Run `makeActivityTemplates()` as the office mailbox, the same account that runs the travel relay. The first run
   asks for permission to use Drive and Docs.
4. Read the Execution log. Each template reports `all placeholders present` or lists the ones that did not land.
5. No new web-app deployment is needed: the relay already accepts any template key that has a `TPL_<key>` property,
   and this script sets `TPL_dpo` and `TPL_invitation`. If you changed `travel_docs.gs` since the last deployment,
   redeploy it as usual.

`checkActivityTemplates()` re-checks the templates that are already set. Run `makeActivityTemplates()` again any time:
a template that is already set and has every placeholder is kept.

## Restyling a template

Both templates are plain Google Docs in the `_templates` folder under the relay's root folder. Restyle them freely
(letterhead, fonts, wording) and keep the `{{placeholders}}`; a placeholder you remove is left empty on the draft.

| Template | Placeholders |
|---|---|
| `dpo` | `dpo_year`, `dpo_no`, `dpo_date`, `subject`, `background`, `intro`, `funding_source`, `p_name` and `p_position` (one table row, copied per person), `head_name`, `head_title`, `unit_name`. Also available: `title`, `purpose`, `dates`, `venue`, `prepared_by`, and a `{{personnel}}` line of numbered names |
| `invitation` (the DOH memorandum) | `date`, `for_name`, `for_title`, `for_office`, `from_name`, `from_title`, `unit_name`, `subject`, `opening`, `details` (a block of What / When / Where lines), `a_area` and `a_request` (one table row, copied per request), `contact_name`, `contact_email`, `contact_phone`. Also available: `title`, `invited`, `sender_name`, `sender_title`, `contact`, `head_name`, `head_title` |
| `concept_note` | `title`, `date_duration`, `venue`, `participant_count`, `facilitators`, `budget`, `prepared_by`, `prepared_title`, `noted_by_name`, `noted_by_title`, `recommended_name`, `recommended_title`, `unit_name`; blocks `background`, `objectives`, `outputs`, `participants`, `methodology`; one table row `pd_day` / `pd_am` / `pd_pm` copied per day |
| `program_flow` | `title`; one table row `pf_time` / `pf_topic` / `pf_person` copied for each day heading and each empty row |

## What the app fills in, and what it leaves for you

- The DPO number, DPO date and funding source are left as blank lines to complete by hand. The app never guesses
  a number, a source of funds or a signature.
- The signatory is the Director settings already used by the travel forms (`travel.sig.head_name` and `head_title`).
- The personnel are the people marked as travelling on the item; if none, the people on the item; if none, the person
  drafting.
- An item's private **note** is never copied into a draft.
- The draft is shared with the person who asked for it. Only the choice (needed or not) and the link are stored; the
  content of a draft is built when it is asked for and not kept.

## The DPO follows the DOH Department Personnel Order layout

The DPO template (version 7.47 onwards) is built to the DOH order format: the "Republic of the Philippines / DEPARTMENT OF
HEALTH / Office of the Secretary" letterhead, the date at the top right, "DEPARTMENT PERSONNEL ORDER No. 2026 - ____", a
bold underlined SUBJECT, a background paragraph, "Authority is hereby given to the following select ... personnel", a
Name / Position table, the expenses paragraphs, "By Authority of the Secretary of Health:", the signatory in capitals and the
DOH address footer.

- **Updating an existing setup:** replace the `activity_templates` file in the Apps Script project with the new one and run
  `makeActivityTemplates()` again. The old DPO template lacks the new placeholders, so it is rebuilt and `TPL_dpo` points to
  the new Doc. The old copy stays in `_templates`. The invitation template is already good and is kept.
- **Logos (7.53):** the DOH seal and the Bagong Pilipinas logo are embedded in `apps_script/activity_logos.gs`, taken from the
  DOH package. Add that file to the Apps Script project next to `activity_templates` (File > New > Script, name it
  `activity_logos`), replace `activity_templates` with the new version and run `rebuildActivityTemplates()`. All four
  documents (DPO, memorandum, concept note, program flow) then start with the seal, "Republic of the Philippines /
  DEPARTMENT OF HEALTH / Office of the Secretary" and the Bagong Pilipinas logo, and carry the DOH address footer.
  `rebuildActivityTemplates()` makes new Docs even though the old ones were good; the old ones stay in `_templates`.
  To use other pictures, replace the base64 text in `activity_logos.gs`, or put Drive file ids in `AT_LOGO_LEFT_ID` and
  `AT_LOGO_RIGHT_ID`, which win over the embedded ones. Every draft keeps what is in the template.
- **Left for the person:** the DPO number, the DPO date and the funding source stay as blank lines. The subject, background,
  authority line and the Name / Position table are written from the calendar item and its people.

## Real header and footer, and the DPO's file-copy page (spot feedback #157, #158)

**Letterhead in the real header.** The four templates now build the seal, "Republic of the Philippines / DEPARTMENT OF
HEALTH / Office of the Secretary" and the Bagong Pilipinas logo into the document's header, so it repeats on each page and is
not part of the body text (the address footer was already a real footer). To apply it, replace `activity_templates` in the
Apps Script project and run `rebuildActivityTemplates()`. Existing drafts and templates are not changed.

**A DPO for one person** is written as one sentence with no table. Replace `travel_docs` (the relay) with the new version and
**deploy a new version of the web app** (Deploy > Manage deployments > pencil > Version: New version > Deploy); until then the
Name / Position table stays with one blank row.

**The file-copy page.** Each DPO ends with a second page holding the same content with **no letterhead and no address footer**,
followed by two tables: BLHSD / Initials / Date, and Keywords / Related issuances, laws, directives. Google Docs repeats a header
on every page of a section, so the copy starts a new section with an empty header and footer. The Apps Script document service
cannot make a section, so this needs the **Google Docs advanced service**:

1. In the Apps Script project, open **Services** (the + beside it in the left sidebar), choose **Google Docs API**, keep
   identifier `Docs`, and **Add**. (The project already uses the Drive service the same way.)
2. If the project's `appsscript.json` lists `oauthScopes` by hand, add `https://www.googleapis.com/auth/documents`.
3. Deploy a new version of the web app, as above, and approve the permission prompt the first time a DPO is drafted.

If the service is not on, the DPO is still made, without the second page, and the draft message says so. If Google refuses
the section change on a given draft, the same message appears; "Draft again" tries once more. The second page is a copy made
when the draft is created: edit the order first, then use the copy, or edit both.

## The invitation follows the DOH memorandum to the regions (7.51 onwards)

The invitation is the DOH **memorandum** format: the date, MEMORANDUM, FOR / FROM / SUBJECT, a rule, the request, the what / when
/ where lines, an "Area / Requested Assistance" table, the contact line, the thanks and an Initials / Date block.

- **Updating an existing setup:** replace the `activity_templates` file in the Apps Script project and run
  `makeActivityTemplates()` again. The old invitation lacks the new placeholders, so it is rebuilt and `TPL_invitation`
  points to the new Doc (the old copy stays in `_templates`). The DPO is kept if it is already current.
- **Left for the person:** who it is FOR (name, title, office) and the telephone number stay as blank lines. The FROM is the
  Director set in the travel settings. The Requested Assistance table starts with Participants, Venue, Meals and Coordination;
  edit the wording on the draft.

## The concept note and the program flow (7.52 onwards)

The rest of the DOH package is drafted too.

- **Concept note:** the numbered DOH sections (Background and Rationale, Objectives, Expected Outputs, Participants, Methodology),
  the Operational Details table, the Proposed Program of Activities (one row per day, AM and PM empty) and the Prepared by /
  Noted by / Recommended by block. The app fills what the calendar item knows: the title, dates, venue, the people on the item,
  the unit as the facilitator, and the Director as the one recommending. The Background, Objectives, Outputs and Methodology
  start as bracketed prompts in square brackets for the person to replace. The budget and the Noted by name are blank lines.
- **Program flow:** "Activity: ..." and "Tentative Program Flow:" with a Date/Time, Topic/Activity and Person Responsible table:
  a heading row for each day ("Day 1 - October 12, 2026") with two empty rows under it. The schedule is the person's to write.
- **When they are suggested:** a concept note for a training, a trip, or anything lasting several days; a program flow for a
  training or anything lasting several days. The person can overrule either.
- **Updating an existing setup:** replace the `activity_templates` file in the Apps Script project and run `makeActivityTemplates()`
  again. It creates the two new templates and keeps the DPO and the invitation if they are already current.
- **Database:** the first start of 7.52 rebuilds the small `calendar_entry_doc` table so it accepts the two new document types.
  Existing choices and draft links are kept.
