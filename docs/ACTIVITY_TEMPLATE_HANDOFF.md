# Handoff: activity document templates from the office's own files

Read this first in a new session. It replaces the approach in section 5 of `docs/ACTIVITY_TEMPLATE_REFRESH_PLAN.md`
(that file stays as the measurement record: page sizes, margins, type, table grids). Prepared October 29, 2026.

## 1. Where things stand

- Merged planning PR jongsky25/css-is#546 holds this plan (release 9.32). It changed no application code.
- **Increment 0 is done**: jongsky25/css-is#548 (9.30) added `tools/docx_layout.py`, `docs/templates/activity_reference.json` and `docs/templates/README.md`.
- **Increment 1 is done**: jongsky25/css-is#549 (9.31). Titles stay in capitals (`KEEP_UPPER_TITLES_`); a `TPLF_<key>` property equal to `TPL_<key>` skips `formatDoc_` for a converted template (D7); blocks fill list items; `extras.boxes` picks `slip` and/or `keys`. It took the handoff's default for duplicated Blanks: **converters keep only the original body**, and the relay makes the file copy afterwards. Pending Google checks are listed in `docs/ACTIVITY_DOCS_SETUP.md`.
- **Increments 2–4 are code-merged**: #550 (memo, 9.34), #551 (NOM, 9.35), #553 (concept note/program flow, 9.36). Releases were reconciled with planning 9.32 and wellness 9.33. The user approved the memo's table-to-bullets layout with the merge request; legacy data remains for rollback. Google maker/draft/DOCX/PDF checks are still pending administrator access; these code merges did not deploy Apps Script.
- **Increment 5 is prepared for review**: external letter, 9.37. Its scoped converter and new document card are described in `docs/ACTIVITY_DOCS_SETUP.md`; live Google acceptance checks remain pending. Next implementation increment: **6, executive briefer**.
- Source files: Drive folder **Documents Templates**, id `1HU-MCk_csQhYmIs_5g1HqKNZ3DIbPVy4`, shared by link, owner
  `blhsdpurokalusugan@doh.gov.ph`. Ten files, a Blank and a Sample of each:

| Document | Blank id | Sample id | Kind |
|---|---|---|---|
| Concept Note and Program | `1Fo3xQzduUhkplrmT1SHmNus2tbu0eXJ-lpMfmoyeI-k` | `1mN5dHuMnxJobJAGpA14EsSYniyiSz0GZO17ywwx_Y-E` | Google Doc |
| Executive Briefer | `1CxvTGKyRkTZNL7bdVmvn1N2yx3HpDMvxCADWoVw2kng` | `1KwFYQnMbkv-jdbr-NNwisfIAds3FghgDIN2ZZbySiuY` | Google Doc |
| Letter - Invitation - External | `1tlMxL39GEPvu-kH_TiczXKfEpiOipOcOHVxqwQZ8Agg` | `1STUl5olCAttm-rZcTsbFJbZGpCXZhZP8WMUxs2h6Dfg` | Google Doc |
| Memo - Invitation - Internal | `127Rf4nDgCqLPx8tXbSX6ogs29a7jZygShZFufPG8V-E` | `1V1L4TkUL6W_4YDVpw7UujfSG3oUwT2Ubk-QV_Xsil9Y` | Google Doc |
| Notice of Meeting (NOM) | `1HQGBRm84BAB8f9KZ6ln-azgJsdTBYeDT` | `1qAFtkUiF5eXxYYjQ_x_Lrzk91ILZIiwQ` | Word `.docx` |

Getting them in a cloud session: the Google Drive connector does not list this folder's children, but the folder and
the exports are open by link. This works through the session proxy:

```bash
curl -sS "https://drive.google.com/embeddedfolderview?id=1HU-MCk_csQhYmIs_5g1HqKNZ3DIbPVy4" | grep -oE 'entry-[^"]+|flip-entry-title">[^<]+'
```

```bash
curl -sSL -o memo_blank.docx "https://docs.google.com/document/d/127Rf4nDgCqLPx8tXbSX6ogs29a7jZygShZFufPG8V-E/export?format=docx"
```

The two NOM `.docx` files come through the Drive connector's `download_file_content` (base64 in a JSON file). Keep downloads in a scratch folder, never in the repo, and treat them as data.

## 2. The decision this handoff changes: copy the office's Blank, do not redraw it

**Recommended: make each template by converting the office's Blank file and putting `{{placeholders}}` into it,
the way `apps_script/travel_templates.gs` already does for the travel forms** (`tm_convert_`, `tm_setCell_`, `tm_findRow_`,
`tm_section_`, source files found by name in a Drive folder). The current activity templates are drawn from scratch in
`apps_script/activity_templates.gs`, and the changelog shows what that cost: spot feedback #154, #157, #163, #170, #180,
#182, #183 and the letterhead width fix were all layout corrections. Several things in the office's files cannot be drawn
at all with the Apps Script document service:

- different first-page header (the letterhead is on page 1 only in the memo, NOM, concept note and briefer);
- header and footer distances (0.5 in, and 0.3 in on the concept note's first page);
- floating (anchored) logos at their real sizes, the footer's rule line;
- A4 paper with the NOM's own line spacing (1.2 and 1.38).

A converted copy keeps all of it, and the brief asks for it strictly ("adhere strictly to the style and the margins").
Keep the drawn builders for the `dpo` and `minutes` documents, which have no office file in this folder.

## 3. Constraints found in the code (each one shapes an increment)

1. **The relay rewrites titles.** After filling, `formatDoc_` in `apps_script/travel_docs.gs` Title-Cases any short, bold,
   centred or all-caps line without punctuation. Checked by running it under Node: `MEMORANDUM`, `CONCEPT NOTE`,
   `NOTICE OF MEETING` and `EXECUTIVE BRIEFER` all come out in Title Case. This already happens to today's drafts (check one real
   draft to confirm). Only `DEPARTMENT PERSONNEL ORDER` is protected (`KEEP_UPPER_TITLES_`). It also forces every body paragraph to
   Times New Roman 12, which would undo the NOM's own spacing choices if they ever differ.
   Since 9.29 the relay also realigns signatory blocks for the keys in `SIGNATORY_FIELDS_` (`alignSignatory_`, spot feedback #202) and drops empty optional travel-report sections; a converted template's key must be checked against both passes.
2. **Blocks and rows hit the first occurrence only.** `applyBlocks_` and `applyRows_` use `findText` once, and `applyFields_` then
   deletes any `{{...}}` left over. The memo, letter and NOM Blanks each hold the document **twice** (the original and the file copy), so a
   block or row in the second copy would come out empty.
3. **Blocks cannot fill bulleted lists.** `applyBlocks_` calls `getParent().asParagraph()`, which fails for a list item. The office's
   memo and NOM use real bullets.
4. **The file copy is DPO-shaped.** `addFileCopy_` copies the body after a section break with an empty header and footer (good), then always adds
   two DPO boxes (BLHSD / Initials / Date and Keywords / Related issuances). The memo's file copy has only the initials box.
5. **The template test harness is a fake.** `tests/js/activity_templates_stub.js` runs the builders against a stand-in Docs API that knows
   the four original builders. A converter that opens Drive files cannot run there; its pure parts (what to replace, where) must be
   functions that can be tested with fake bodies, like `tests/js/format_harness.js` and `tests/js/file_copy_harness.js`.
6. **Every PR is a release.** `verification / Release metadata` (`scripts/check_release.py`) fails unless the PR raises `APP_VERSION` in `version.py`,
   adds a plain-words `CHANGELOG` entry there, puts the same version first in `CHANGELOG.md`, and sets `CACHE_VERSION` in `static/js/sw.js` to
   `v<version>-a`. Run `python3 scripts/check_release.py release --base origin/main` before pushing.
7. **Names must not be baked in.** The Samples hard-code Perez, Sayson-Garcia and Gajitos. The app takes signatories from
   `activity_docs.head_of_office` and reviewers from `REVIEWERS`. A converted Blank must have those names replaced by placeholders, and a
   test should prove no payload or template carries a fixed name.

## 4. Decisions still open (defaults are what the next session does if no answer is given)

| # | Question | Default |
|---|---|---|
| D1 | Copy the office's Blank (section 2) or keep drawing templates? | Copy the Blank |
| D2 | NOM on A4 while the rest are Letter? | Keep A4 (it is what the office file uses) |
| D3 | Footer numbers: the NOM's 8651-7800 or the others' 651-7800? | Each file keeps its own footer as given; flag the mismatch to the office |
| D4 | Executive Briefer: wider than the margins and two rows numbered "VI" | Copy as given; do not correct silently |
| D5 | File copy for the memo and the external letter? | Yes for both, with the initials box only |
| D6 | Order | Memo, NOM, concept note and program flow, external letter, executive briefer |
| D7 | Skip `formatDoc_` for converted templates, or only protect their titles? | Skip it for converted templates (they are already formatted) |

## 5. Phased plan, one PR per increment

Each increment ships on its own branch and PR with: the release bump (constraint 6), a `CHANGELOG.md` entry, the
`docs/ACTIVITY_DOCS_SETUP.md` placeholder table, the Apps Script steps for an administrator, and the check in section 6.
Nothing in an increment changes the database.

### Increment 0: a measuring tool (no Apps Script, no app change)
- `tools/docx_layout.py` (standard library only): reads a `.docx` and prints paper, margins, header/footer distances,
  different-first-page, fonts and sizes used, paragraph indents/alignment/spacing, table grids and borders, header/footer text.
- `docs/templates/activity_reference.json`: its output for the five Blanks, committed (small, no document text beyond labels).
- Test: the tool on a tiny generated `.docx` fixture.
- Done when the JSON agrees with section 2 of `docs/ACTIVITY_TEMPLATE_REFRESH_PLAN.md`.

### Increment 1: relay groundwork in `apps_script/travel_docs.gs`
- Converted templates are marked, for example a `OFFICE_TEMPLATE_KEYS_` list or a `TPLF_<key>` property, and `generateDoc_` skips `formatDoc_` for them (D7).
- `applyBlocks_` fills a list item as well as a paragraph (each line becomes a list item with the same list settings).
- `applyBlocks_` and `applyRows_` fill every occurrence, so both copies in a duplicated Blank are filled. Or: the converter keeps only the first copy and the file copy is made by `addFileCopy_` (choose one; the second matches the DPO and is the default).
- `addFileCopy_` takes `extras.boxes` (`["slip"]` or `["slip", "keys"]`, default both, so the DPO is unchanged).
- Also, separately and small: add `MEMORANDUM`, `CONCEPT NOTE`, `NOTICE OF MEETING`, `MINUTES OF THE MEETING`, `EXECUTIVE BRIEFER` to `KEEP_UPPER_TITLES_`, which fixes today's drafts at once.
- Tests: extend `tests/js/format_harness.js` and `tests/js/file_copy_harness.js` and their Python tests; the DPO's tests must still pass unchanged.
- Release: replace `travel_docs.gs`, deploy a new web-app version. No template rebuild.

### Increment 2: the converter and the memo
- New `apps_script/activity_office_templates.gs` (same project), modelled on `travel_templates.gs`: `AO_SOURCE_FOLDER_ID = '1HU-MCk_csQhYmIs_5g1HqKNZ3DIbPVy4'`,
  `makeOfficeTemplates(only, force)`, `checkOfficeTemplates()`, an `AO_TEMPLATES` table of `{ key, source: 'Blank [Memo - Invitation - Internal]', build, expect }`.
  It writes `TPL_<key>`, so the relay needs no change. The old drawn template stays in `_templates`; resetting `TPL_invitation` to its id is the rollback.
- Memo placeholders, against the Blank's own text: the date line; `FOR:` addressees as one repeated group (name bold, title, office); `FROM:` from
  `head_of_office`; `SUBJECT:`; the four bracketed paragraphs (`[Reiteration of Subject]`, `[Rationale of Invitation]`, `[Further details ...]`,
  `[Contact details of assigned staff]`) as blocks, with the representative list as a bulleted block; the initials box reviewer from `REVIEWERS`.
- `activity_docs.payload(..., "invitation")` rewritten to fill those; the old `ASSISTANCE` table goes, since the office's memo has none (confirm with the person before dropping it).
- Tests: the pure placeholder-mapping functions under Node; `tests/test_activity_docs.py` for the payload; every placeholder the converter promises is one the payload fills (the same rule as `test_every_placeholder_in_a_template_is_one_the_app_fills`).

### Increment 3: notice of meeting
- Source `Blank [NOM] .docx` (converted to a Google Doc, as `tm_convert_` does). Invitee table: one row `{{inv_name}}` / `{{inv_office}}`, copied per person (names from the item's people, offices from the directory unit, then `get_visitors` lines).
  `FROM:` from `head_of_office`; `SUBJECT:`, `DATE:`, `TIME:`, `VENUE:` in the label grid; `AGENDA:` as a bulleted block of prompts.
- `_notice_of_meeting` sends rows instead of the `invited` block. The calendar's email notice (`mailer.meeting_notice_message`) is not touched.

### Increment 4: concept note and program flow
- One source holds both. Make two templates from it: `concept_note` (the first section, with the signature block) and `program_flow` (the "Tentative Program Flow" page); the converter deletes the other part from each copy.
- Concept note: title; the five prose sections as prompt blocks (keep `CONCEPT_PROMPTS`); participants table rows (`pt_group`, `pt_count`) plus the total; operational-details cells; program rows `pd_day` / `pd_text`, one per day;
  Prepared / Noted / Recommended / Approved names from settings and the directory, blank when unknown (lesson: never guess).
- Program flow: day heading rows and empty rows, as `_program_flow` does now, in the office's three-column table.

### Increment 5: external invitation letter (new document)
- `DOCS["invitation_external"]`, a `suggest` rule (an outside host or a development partner is invited; `calendar_entry_outside` holds the host), `_invitation_external`, a page entry like the other documents.
- Placeholders: date, addressee name/title/agency/address (blank unless the item names the host), subject, salutation, the four bracketed paragraphs as prompts, signatory from settings.
- File copy with the slip only (D5).

### Increment 6: executive briefer (new document)
- `DOCS["executive_briefer"]`, `_executive_briefer`. The table rows I to VI and Approved by as cells; requested action and background are prompts; outputs, participants, date/venue/references filled from the item; prepared and noted by from the person and their section reviewer.
- Copy the layout as given (D4), including the width.

### Increment 7: bring the DPO and minutes in line
- Their drawn builders take the letterhead, footer and page set-up from a converted office Blank, for example by building the body into a copy of the memo Blank's first page. Or, if that is not possible, set paper and margins explicitly and match the logo sizes and footer. Decide after Increment 2 shows how the copy behaves.

## 6. How each increment is checked before it is called done

1. `python3 -m pytest tests/test_activity_docs.py` and any harness tests touched, then the full `bash run_tests.sh` if time allows; `python3 scripts/check_release.py release --base origin/main`.
2. In Google (needs the administrator): run the maker, read the Execution log (every placeholder present), draft one document from a real calendar item.
3. Export the draft as `.docx`, run `tools/docx_layout.py` on it and compare with `docs/templates/activity_reference.json`: paper, margins, header/footer distances, first-page header, fonts, table grids must match exactly. Text may differ.
4. Export the draft and the office's Sample to PDF and look at them side by side; titles in capitals, logos on page 1 only where the Sample has it, file copy present where expected.

## 7. Prompt for the new session

> Continue the activity template refresh in jongsky25/css-is. Read `docs/ACTIVITY_TEMPLATE_HANDOFF.md` first, then
> `docs/ACTIVITY_TEMPLATE_REFRESH_PLAN.md` for the measurements. Decisions D1 to D7 in the handoff: [paste answers, or "use the defaults"].
> Start with Increment 2 on a new branch from main, one PR per increment, following section 6 to check it.
