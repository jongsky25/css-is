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
| `invitation` (converted office memo, 9.34) | Fields `date`, `for_name`, `for_title`, `for_office`, `from_name`, `from_title`, `unit_name`, `subject`; blocks `reiteration`, `rationale`, `details`, `representatives` (bullets), `contact_details`. `extras.addressees` repeats the name/title/office paragraph group; unknown addressees remain blank. Legacy `opening`, contact fields, `a_area`/`a_request` rows and other fields remain available for the old drawn template. |
| `concept_note` | `title`, `date_duration`, `venue`, `participant_count`, `facilitators`, `budget`, `prepared_by`, `prepared_title`, `noted_by_name`, `noted_by_title`, `recommended_name`, `recommended_title`, `unit_name`; blocks `background`, `objectives`, `outputs`, `participants`, `methodology`; one table row `pd_day` / `pd_am` / `pd_pm` copied per day |
| `notice_of_meeting` (converted office NOM, 9.33) | Fields `date`, `subject`, `meeting_date`, `meeting_time`, `venue`, `meeting_link`, `head_name`, `head_title`, `unit_name`; one repeatable row `inv_name` / `inv_office`; block `agenda` in the grid's bulleted cell. Legacy `title`, `meeting_when`, `prepared_by`, `prepared_title` and `invited` remain for the drawn template. |
| `minutes` | `title`, `meeting_when`, `venue`, `prepared_by`, `prepared_title`, `approved_by`, `unit_name`; blocks `attendees`, `agenda`, `discussion`, `next_steps`; one table row `m_action` / `m_who` / `m_due` |
| `program_flow` | `title`; one table row `pf_time` / `pf_topic` / `pf_person` copied for each day heading and each empty row |

## What the app fills in, and what it leaves for you

- The DPO number and DPO date are left as blank lines to complete by hand. The funding source is cited as "BLHSD - Local Health Systems Development Assistance funds". The venue is blank when the item has none. The app never guesses
  a number or a signature.
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


## Activity template refresh: Increment 0 (measurement only)

The defaults D1–D7 in planning PR [#546](https://github.com/jongsky25/css-is/pull/546)
apply. Increment 0 adds the offline measuring tool described in
[templates/README.md](templates/README.md). The placeholder table above is unchanged.
No Apps Script replacement, maker run, template rebuild or relay deployment is
needed for this increment. Keep the five Blank exports outside the repository;
the measured JSON is committed in `docs/templates/activity_reference.json`.
The comparison with section 2 of the plan, including Blank/Sample distinctions,
is recorded in `docs/templates/README.md`.

The Google maker/draft/export/PDF checks in handoff section 6 apply when later
increments change the templates or relay. Increment 0 verifies the measuring tool
with a generated DOCX and checks the actual Blank measurements against the plan.

## Activity template refresh: Increment 1 (relay groundwork, 9.31)

The placeholder table above is unchanged. This increment updates only the relay:
activity headings stay in capitals, blocks can fill list items, converted office
templates can preserve their formatting, and file copies can select their boxes.

Administrator release steps:

1. Replace `travel_docs.gs` in the existing relay project with this release and
   deploy a new version of the existing web app. Keep its URL and settings.
2. Do not rebuild templates or set office-format markers yet. Increment 2 will
   create the first converted template. Existing drafts are unaffected; new
   drafts use the updated heading rules.
3. From a real calendar item, draft an invitation and a DPO. Check that
   MEMORANDUM and DEPARTMENT PERSONNEL ORDER stay in capitals, that the DPO's
   file copy still has its separate header/footer and both routing boxes, and
   that the remaining payload fields are filled.
4. Follow handoff section 6 for Google validation: retain the execution log and
   export the real draft as DOCX/PDF for layout and visual comparison. The
   current drawn templates still have the layout gaps recorded in the plan;
   matching the office reference becomes the acceptance check for each later
   converted template. There is no new maker to run in this increment.

Converted-template contract for Increment 2 and later:

- After conversion, set `TPL_<key>` to the converted document ID and set
  `TPLF_<key>` to that same ID. The relay skips `formatDoc_` only when the two
  properties match. A stale marker does not affect a restored template ID;
  deleting `TPLF_<key>` also restores the formatter. No request field can opt out.
- Keep only the original document body in the converted template. Blocks and
  repeating rows still fill their first occurrence. The converter must remove
  the office Blank's embedded file-copy body before inserting placeholders;
  use `extras.file_copy = true` to create the copy after all content is filled.
- For memo and external letter copies send `extras.boxes = ["slip"]`.
  Omitting `boxes` preserves the DPO's `slip` and `keys` boxes. Explicit `[]`
  adds no boxes. Supported names are `slip` and `keys`; unknown names are ignored,
  duplicates are not repeated, and boxes retain slip-before-keys order.
- Put a block marker alone in a paragraph or list item (including inside a table
  cell). Each supplied line becomes a paragraph or a list item of the same
  type; list copies retain glyph/nesting/attributes and join the original list.
  Empty input leaves the original item with empty text, matching paragraph blocks.
- Do not request `rows.*.fit` for fixed office grids: that option intentionally
  resizes existing drawn tables. Preserve the converted grid instead.

Verification: the focused activity, travel-script, office-relay and release tests
pass (142 tests). The original Increment 0 focused suite also passes (123 tests)
in the restored test environment. The release metadata check and `git diff --check`
pass. The full suite was not run. Google deployment, execution log, real-calendar
draft and DOCX/PDF checks remain pending administrator access; keep this increment
in draft until those checks are recorded. The Node harnesses check relay behavior,
not Google's rendering or pagination.

## Activity template refresh: Increment 2 (office memo, 9.34)

This increment prepares the internal memo only. The DPO, NOM, concept note,
program flow, external letter and executive briefer are not converted here.
The memo is copied from `Blank [Memo - Invitation - Internal]` in the handoff's
Documents Templates folder. The converter retains its page setup, first-page
header, footer and anchored artwork. It uses label positions instead of fixed
personal names, replaces the original signatory details with placeholders and
removes the embedded duplicate body and its named initials table. The relay
makes the file copy from the filled original and adds the initials box only.

The user approved the proposed office layout when requesting the merge of this
increment: the same four assistance requests move into editable bullets. The app
retains the old table's payload rows for rollback; the converted template has no
ASSISTANCE table. Administrator validation remains required before activation.

Administrator rollout (requires access to the relay project and office mailbox):

1. Save the current `TPL_invitation` document ID for rollback. Keep its document
   in `_templates`. Ensure Drive API v3 and Google Docs API advanced services are
   enabled in the existing relay project.
2. Add `activity_office_templates.gs` to the same project. Replace `travel_docs.gs`
   and `activity_templates.gs` with this release and deploy a new version of the
   existing relay web app **before** enabling the new template. The legacy maker
   now skips a template whose `TPLF_<key>` matches its `TPL_<key>`, even if forced.
3. Deploy the 9.34 app payload before activating the converted memo. Until then,
   keep the old drawn template selected. The 9.34 payload retains its legacy
   fields/table data, so it can fill that template during the transition.
4. Run `makeOfficeTemplates()` as the office
   mailbox. It makes only the memo in this increment. Read the Execution log:
   it must report `all placeholders present` and the previous template ID. A
   changed/ambiguous source or missing placeholder is a failure; the old active
   properties remain unchanged. Failed candidate documents stay in `_templates`
   for inspection. Run `checkOfficeTemplates()` to check the active placeholders
   and office-format marker. `rebuildOfficeMemoTemplate()` forces a fresh copy.
5. Draft an invitation from a real calendar item. Check its date, FOR / FROM /
   SUBJECT, activity details, editable rationale/request bullets and contact line.
   Names not known to the app stay blank. FROM uses the configured head and the
   bureau name; the file-copy reviewer follows the drafter's section via REVIEWERS,
   or stays blank if no reviewer is known. No name is taken from the source file.
6. Follow handoff section 6: retain the maker execution log; export the real draft
   as DOCX and compare its original section with
   `docs/templates/activity_reference.json` (`invitation_internal`); compare PDFs
   of the office Sample and draft side by side. Confirm Letter paper, one-inch
   margins, half-inch header/footer distances, first-page letterhead, the original
   footer numbers and matching artwork/type. Confirm the file copy has no header
   or footer, has only the initials box and contains all filled content. The
   reference's two-column initials grid belongs to the source's embedded copy;
   the relay-generated initials box replaces it, so compare that separately.

Rollback: restore the saved old `TPL_invitation` ID, and delete `TPLF_invitation`
(or leave its now-stale value). The relay resumes the old formatter and the app's
retained legacy fields/rows fill the old drawn template. If reverting app code
as well, restore the old template before reverting the app payload. Existing
created drafts are not modified. To opt back into the office template, run the
office maker again; do not use the old activity maker to manage it.

`extras.addressees` is a list of objects with `for_name`, `for_title`, `for_office`.
The relay repeats the three prototype paragraphs, preserving name bolding and
plain stacked title/office styling, and prints FOR once. The current app has no
structured addressee editor and sends one blank group; the person completes it
in the draft. This does not guess addressees from the activity's participant list.
The four old assistance requests remain starting text for editing, not inferred
commitments. The private calendar note is never copied.

Local verification: 148 focused activity, travel-script, office-relay, converter
and release tests passed before the final documentation pass. The real Blank was
re-exported and accepted by the pure mapping function (12 replacements). Its page
setup and body measurements match the committed reference exactly. Header/footer
measurements match after normalizing anchored-image order only: Google reversed
the two image records in this export. The source exports remain outside Git.
The full suite was not run. Administrator deployment, maker log, real draft and
DOCX/PDF checks remain pending; these remain administrator acceptance checks after the code merge.

## Activity template refresh: Increment 3 (Notice of Meeting, 9.35)

This increment is stacked on Increment 2, PR #550. It adds the NOM only; it does
not activate the memo or resolve that PR's pending ASSISTANCE-table choice.
The office's `Blank [NOM] .docx` is a Word file, copied and converted to Google
Docs by the same Drive API path as the travel forms. A fresh download matches
the committed NOM reference exactly, including its SHA-256.

The converter keeps A4 (11906 × 16838 twips), one-inch margins, half-inch
header/footer distances, first-page letterhead, original eight-digit footer
numbers and the two table grids (4005/5730 and 1365/735/7275 twips). It replaces
source head details with settings-backed fields and keeps one invitee prototype
row for expansion. It removes the embedded duplicate and clears the following
page-break paragraph while retaining the required paragraph after the last table.
The relay creates a filled copy in its own section with empty headers/footers
and `extras.boxes = []`, because the source NOM has no initials/keywords boxes.

The Word invitee table lives inside a content control. Drive conversion must
expose it as a normal Google Docs table. A missing/unflattened table, unexpected
labels, changed table dimensions, populated source invitee cells or an unexpected
duplicate structure cause validation to fail before activation. Do not work
around a failed log by setting `TPL_notice_of_meeting` manually.

Administrator rollout:

1. Complete the applicable relay setup from Increment 2 and save the current
   `TPL_notice_of_meeting` ID for rollback. Add/replace this release's
   `activity_office_templates.gs`. Drive API v3 and Google Docs API advanced
   services must be enabled. The relay code is unchanged by Increment 3.
2. Deploy the 9.35 app payload before activating the new NOM. Its legacy fields
   and invited block can still fill the drawn template during the transition.
3. Run **`makeOfficeNoticeTemplate()`** as the office mailbox. This selects the
   NOM only and avoids rebuilding/activating the pending memo. Read the Execution
   log: it must report `all placeholders present` and the previous template ID.
   Run `checkOfficeTemplates()` and verify the NOM's office-format marker matches.
   Use `rebuildOfficeNoticeTemplate()` only when a fresh converted copy is needed.
4. Draft a NOM from a real meeting with internal invitees and at least one saved
   free-text visitor. Names follow the item order; directory unit names fill the
   Office column when available. A free-text visitor line stays intact in Name,
   with Office blank: commas can be part of names/credentials and are not parsed.
   Unknown invitees/offices are left blank. No private note is copied.
5. Check FROM against the head settings and the bureau name. Check SUBJECT, the
   separate date and time cells (including time ranges/time notes), venue and
   online link, the editable bulleted agenda, and the filled file copy. The
   calendar email notice is unchanged by this work.
6. Follow handoff section 6: retain the maker log, export the real draft as DOCX,
   compare the original section with `activity_reference.json`'s
   `notice_of_meeting`, and compare the office Sample and draft PDFs side by side.
   Verify A4, margins, distances, first-page-only logos, exact table grids and
   paragraph/list spacing. Row counts and content vary with invitees and agenda;
   widths must not be fitted/resized. Confirm no duplicate blank notice, trailing
   blank page or inherited first-page letterhead/footer on the file copy.

Rollback: restore the saved old `TPL_notice_of_meeting` ID and delete its
`TPLF_notice_of_meeting` marker (or leave it stale). The retained legacy payload
fields and invited block fill the old drawn template again. Restore the old
pointer before reverting the app payload. Existing drafts are not edited.

Local verification: 153 focused activity, travel-script, office-relay, converter
and release tests pass. They cover NOM mapping/failed activation, table-row and
agenda expansion with preserved grids, source-name removal, payload/template
agreement, directory offices, intact visitors, unknown invitees and separate
meeting times. The actual Word structure is accepted by the pure mapper after
unwrapping its content-control table for the offline check. This does not verify
Google's conversion of that control. Release metadata and whitespace checks pass.
The full suite was not run. Administrator conversion, maker log, real-calendar
draft and DOCX/PDF comparisons remain pending; these remain administrator acceptance checks after the code merge.
