# Activity document templates: refresh from the office's "Documents Templates" folder

Status: plan only. No code or template is changed by this file.

Source: the shared Drive folder **Documents Templates** (owner `blhsdpurokalusugan@doh.gov.ph`), ten Google Docs / Word files:
a **Blank** and a **Sample** each for Concept Note and Program, Executive Briefer, Letter - Invitation - External,
Memo - Invitation - Internal and Notice of Meeting (NOM).

Every measurement below was read from the `.docx` export of the file (page setup, header/footer XML, paragraph
indents and spacing, table grids), not judged by eye. Units: 1 in = 72 pt = 1440 twips.

## 1. Map: where each file goes

| Drive file (Blank / Sample) | Our document key | Builder in `apps_script/activity_templates.gs` | Payload in `activity_docs.py` | Status |
|---|---|---|---|---|
| Concept Note and Program | `concept_note` **and** `program_flow` (the sample is one file: the note, then a "Tentative Program Flow" page) | `at_buildConceptNote_`, `at_buildProgramFlow_` | `_concept_note`, `_program_flow` | Exists; layout differs (section 3) |
| Memo - Invitation - Internal | `invitation` ("Invitation (memorandum)") | `at_buildInvitation_` | `payload(... "invitation")` | Exists; layout differs |
| Notice of Meeting | `notice_of_meeting` | `at_buildNotice_` | `_notice_of_meeting` | Exists; very different (its own letterhead, From/Subject/Date/Time/Venue/Agenda block) |
| Letter - Invitation - External | none | none | none | **New**: `invitation_external` |
| Executive Briefer | none | none | none | **New**: `executive_briefer` |
| (not in the folder) | `dpo`, `minutes` | `at_buildDpo_`, `at_buildMinutes_` | | Unchanged; only the shared letterhead/footer helpers move |

How the pieces connect today: the app builds a `DocPayload` (`fields`, `blocks`, `rows`, `extras`) in `activity_docs.py`,
`gdocs_relay` signs it, and `travel_docs.gs` copies the Google Doc named by `TPL_<key>` and replaces `{{placeholders}}`.
A template change therefore never needs a database migration; it needs the template rebuilt
(`rebuildActivityTemplates()`) and, for the two new types, new payload code, a `DOCS` entry and tests.

## 2. The layout the office's files actually use

### Page and margins (strict)

| File | Paper | Margins T/B/L/R | Header / footer distance | Different first page |
|---|---|---|---|---|
| Concept Note | Letter 8.5 x 11 in | 1 in all round | header 0.5 in; footer 0.3 in on the first page (432 twips), 0.5 in after | yes |
| Executive Briefer | Letter | 1 in all round | 0.5 in / 0.5 in | yes |
| Letter - External | Letter | 1 in all round | 0.5 in / 0.5 in | no (letterhead is in the default header, plus an even-page header) |
| Memo - Internal | Letter | 1 in all round | 0.5 in / 0.5 in | yes |
| Notice of Meeting | **A4** (11906 x 16838 twips) | 1 in all round | 0.5 in / 0.5 in | yes |

Text width is 6.5 in (468 pt) on Letter and about 6.27 in on the A4 NOM. Our builders never set paper size or margins; they rely on the Docs
default (Letter, 1 in), which happens to match four of five. The NOM is the exception.

### Type

Body is **Times New Roman 12 pt** in all ten files (the style default is Arial 11, overridden in every run). Single line
spacing (`line=240`) everywhere except the NOM (`line=288`/`331` on its date, title and From/Subject block).
Letterhead text: 9 pt "Republic of the Philippines", larger bold "DEPARTMENT OF HEALTH", italic "Office of the Secretary".
Footer: 8 pt, centred.

### Letterhead (header)

Seal (about 75 pt square) and Bagong Pilipinas logo (about 103 x 106 pt) are **floating images anchored in the header**, with
the three centred lines between them. The Executive Briefer header is logos only (two images of about 75 pt, no title text).
Ours: 90 pt-tall inline images in a 100 / 268 / 100 pt table, in the default header, so it repeats on every page.

The sample files put the full letterhead on the **first page only** (Different first page) for the memo, NOM, concept note and
briefer. The letter has it in the default header.

### Footer

Memo, Letter and Concept Note: a rule line, then two 8 pt centred lines (address; telephone/fax/URL/e-mail).
The NOM uses the **new 8-digit numbers** (Trunk Line 8651-7800, Direct Line 8711-9502 / 8711-9503, Fax 8743-1829); the other
four still print the old 7-digit numbers. Ours (`AT_FOOTER_LINES`) matches the old numbers. The Executive Briefer has no footer text.

### Per-document specifics

- **Memo (internal)**: date right-aligned; `MEMORANDUM` bold; `FOR:` at left 1.5 in with a 1 in hanging indent (labels at 0.5 in, text at 1.5 in), each addressee's title and office
  stacked below at 2.5 in; `FROM:` first-line indent 0.5 in; `SUBJECT:` bold, hanging 1 in; a bold underscore rule; body justified with 12 pt before and after each paragraph;
  bulleted list at 0.5 in with a 0.25 in hanging indent, 12 pt before the first and after the last item; initials block as a 4-column bordered table
  (825 / 4035 / 825 / 4035 twips = two repeating 2-column blocks, i.e. the file-copy page). The sample holds the memo **twice** (original and file copy), like our DPO file copy.
- **Letter (external)**: no `MEMORANDUM`; date, then addressee in bold, address, `Subject:` bold, salutation, body justified with 12 pt before and after, "Very truly yours," and the signatory in bold. Also duplicated (file copy).
- **Concept Note**: centred bold `CONCEPT NOTE`, centred activity title; sections numbered 1 to 7 with hanging indent 0.5 in / 0.25 in, bold; participants table (7695 / 1200 twips),
  operational-details table (1850 / 7370), program-of-activities table (1215 / 7995), then the signature block (2370 / 4575 / 2415). The sections and their order match ours (Background and Rationale, Objectives, Expected Outputs, Participants, Methodology, Operational Details, Proposed Program of Activities); the **Tentative Program Flow** page follows (Date/Time 2370, Topic 4575, Person Responsible 2415).
  What differs is the Participants table (Participant | Number with a total row and a Note line, which we write as a block), the program of activities (Day | Activity, one row per day, not Day | AM | PM) and the signature block (Prepared / Noted by, then Recommended by and Approved by, with fixed names for the last two).
- **Executive Briefer**: one two-column table, label column 2445 twips and content 8475 twips (10920 twips = 7.58 in in total, **wider than the 6.5 in text area**, with a negative left indent of 540 twips),
  roman-numeral rows I to VI (the sample repeats "VI" for both Date/Venue/References and Prepared by; the blank says the same), then Approved by.
- **Notice of Meeting**: A4; right-aligned date; centred bold `NOTICE OF MEETING`; a 2-column bordered table of invited people (Name | Office; 4005 / 5730 twips);
  `FROM:`, `SUBJECT:`, `DATE:`, `TIME:`, `VENUE:`, `AGENDA:` as bold labels at left -90 twips with a borderless 3-column table for the values (1365 / 735 / 7275); agenda as a bulleted list (0.5 in, 0.25 in hanging, no spacing).

## 3. Gap list: current template versus the office's file

| Area | Today | Office's file | Action |
|---|---|---|---|
| Paper | Docs default (Letter) for all | NOM is A4 | Set A4 on `notice_of_meeting` only, after confirming (question 1) |
| Margins | default 1 in | 1 in | Set 1 in explicitly on every builder so a future Docs default cannot change it |
| First-page letterhead | in the default header, every page | first page only | Use `setHeader` with different first page: letterhead in the first-page header, empty default header |
| Letterhead art | 90 pt inline images in a 3-column table | floating images, about 75 pt seal and 103 pt logo | Size to the sample's EMU values; keep the fixed-width table so nothing falls off the page (see lesson 5) |
| Footer | no rule line; old numbers | rule line; NOM has new numbers | Add the rule; use one footer constant. Question 2 on which numbers |
| Concept note | same 7 sections; participants as a block; program rows Day / AM / PM; no Approved by | participants table with total, Day / Activity rows, fixed grids, Recommended by and Approved by | Rebuild to the sample; keep placeholder names where they still fit |
| Memo | simple paragraphs, 1 table | hanging-indent FOR/FROM/SUBJECT, justified, 12 pt spacing, bulleted asks, file copy | Rebuild; reuse the DPO file-copy mechanism (`addFileCopy_`) |
| NOM | flowing paragraphs | table of invitees, From/Subject/Date/Time/Venue/Agenda grid | Rebuild; the app already has the data (`meeting_when`, `venue`, `invited`, `agenda`) |
| Letter (external) | not offered | exists | New doc key |
| Executive Briefer | not offered | exists | New doc key |

## 4. Lessons from the existing templates (from `CHANGELOG.md`, `docs/ACTIVITY_DOCS_SETUP.md`)

1. **Measure from the office's sample, in points, and name the numbers as constants** (DPO, spot feedback #170, #180, #182: `AT_DPO_*`). Do the same for each new layout; do not eyeball.
2. **Set both the start indent and the first-line indent** for any indented single-line paragraph. Setting only the start indent left one-line paragraphs at the left margin (#182). Hanging indents need both.
3. **Every paragraph and table starts plain.** Docs copies the formatting of the paragraph above, and one bold line made a whole DPO bold (#154). Keep `at_add_` / `at_table_`.
4. **Do not delete the header's first blank paragraph**; shrink it (`at_dropLeadingBlank_`). Deleting it makes the document unsaveable (#157 fix).
5. **Give letterhead and signatory tables fixed column widths that add up to the text width.** Default equal columns wrapped the title and pushed the right logo off the page (changelog "Fix for the new letterhead").
   This is the main risk for the Executive Briefer, whose own table is wider than the margins.
6. **The letterhead lives in the real header**, not the first table of the body, so it repeats correctly and the relay's title-casing never touches "DEPARTMENT OF HEALTH" (#157).
7. **The relay formats after filling** (`travel_docs.gs` `formatDoc_`): it sets Times New Roman 12, justifies left-aligned paragraphs of 60 characters or more and bolds/Title-Cases short titles. A new template must not rely on formatting that pass will change; check
   what `looksLikeTitle_` would do to a label such as `FOR:` or `Subject:`.
8. **One template change = rebuild.** Existing templates are not updated in place; run `rebuildActivityTemplates()`, redeploy the scripts (and `activity_logos.gs`), and note it in the changelog (every prior layout change did).
9. **Never guess names or numbers** (DPO number, signatures are left blank for the person). The same rule applies to the new letter and briefer.
10. **A template carrying a real person's name** (Perez, Sayson-Garcia, Gajitos in the samples) must come from settings/the directory (`head_of_office`, `REVIEWERS`), not be hard-coded into the document body. The sample files hard-code them; ours must not.

## 5. Plan

### Phase 0: confirm (no code)
Questions in section 6 answered. Save the ten files into the repo as `docs/templates/reference/*.docx` (reference only, not shipped) so the numbers above can be re-checked.

### Phase 1: shared building blocks in `activity_templates.gs`
- `AT_PAGE` constants (Letter or A4, margins 72 pt, header 36 pt, footer 36 pt/21.6 pt) and `at_page_(doc, size)`.
- `at_letterhead_` rewritten for first-page-only, sample-sized logos, fixed table widths; `at_logoOnlyHeader_` for the briefer.
- `at_footer_` with the rule line and one `AT_FOOTER_LINES` (numbers per question 2).
- Layout helpers with the constants from section 2: `at_hanging_(p, left, hang)`, `at_numbered_heading_`, `at_label_value_grid_`.
- A scripted **layout check** `checkActivityLayout()` that opens each built template and logs paper, margins, fonts, table widths against the text width, so a regression shows in the Execution log before anyone drafts.

### Phase 2: update the existing templates (one change per PR, smallest risk first)
1. Memo (`invitation`): rebuild to the sample; add file copy (`extras: {"file_copy": true}`). New/changed placeholders: `for_*` becomes a repeatable block (several addressees), `details`, `bullets` rows.
2. Notice of meeting: A4, invitee table (`inv_name`, `inv_office` one row), From/Subject/Date/Time/Venue/Agenda grid; `_notice_of_meeting` supplies a row list instead of a block.
3. Concept note and program flow: participants table with total row; per-day program rows (`pd_day`, `pd_text`); Approved by block, tables with the sample's grids; `_concept_note` and `_program_flow` updated.
4. DPO and minutes: only pick up the shared header/footer/margins.

### Phase 3: new documents
- `invitation_external` (Letter): `DOCS` entry, `suggest` rule (outside office or partner invited), `_letter_external`, `TPL_invitation_external`; salutation and addressee are left for the person unless the item names a host.
- `executive_briefer`: `DOCS` entry, `_executive_briefer`; fields from the calendar item (subject, requested action, background, outputs, participants, date/venue/references, prepared by, noted by, approver); background and requested action are prompts, not invented text.

### Phase 4: tests and rollout
- Extend `tests/test_activity_docs.py`: each new/changed key returns the expected `template_key`, placeholders, rows and blocks, and a payload never contains a hard-coded signatory name.
- A Python test that parses the template builder source for the layout constants and asserts they equal the table in section 2 (guards against drift).
- `docs/ACTIVITY_DOCS_SETUP.md` placeholder table updated; `CHANGELOG.md` entry per phase; release steps: replace the three `.gs` files, enable the Docs service (already needed for the file copy), `rebuildActivityTemplates()`, `checkActivityLayout()`.
- Compare each produced draft with the matching Sample by exporting both to PDF and viewing them side by side before marking a phase done.

## 6. Questions that decide the work

1. The **NOM is A4** while everything else is Letter. Is that deliberate, or should the NOM follow Letter like the rest?
2. The footer numbers differ between files (NOM: 8651-7800 style; others: 651-7800). Which is current? I would use the NOM's.
3. The Executive Briefer's table is wider than the margins and the sample numbers two sections "VI". Copy this as is, or correct it (fit the margins, number to VII)? The brief says strictly adhere, so my default is to copy the widths and fix nothing silently; tell me if you want the numbering corrected.
4. Both the letter and memo samples hold the document twice (original plus file copy). Should the new letter get the same file-copy page as the DPO?
5. Priority order of the five documents.
