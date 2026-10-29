# Activity reference measurements

Increment 0 of the activity refresh uses the D1–D7 defaults in planning
PR [#546](https://github.com/jongsky25/css-is/pull/546). Its handoff and measurement
plan are not yet on main; read those files in that PR.

## Measure exports

Save the office's five **Blank** DOCX exports outside the repository, using stable
names: `concept_note_program.docx`, `executive_briefer.docx`,
`invitation_external.docx`, `invitation_internal.docx`, `notice_of_meeting.docx`.
Then run from the repository root:

```bash
python3 tools/docx_layout.py --omit-header-footer-text /scratch/activity-blanks/*.docx > /scratch/activity_reference.json
```

Compare with section 2 of `ACTIVITY_TEMPLATE_REFRESH_PLAN.md` in PR #546 before
copying the result to `docs/templates/activity_reference.json`. Retain the
original exports in scratch to reproduce the SHA-256 provenance. The source
files may contain names even when labelled Blank; do not commit them.
Omit header/footer text in the committed reference to keep only measurements.
Without that flag, the tool also reports header/footer wording for local checks
of the differing telephone numbers (D3). Body text is never included.

The report keeps raw OOXML units and values rather than rounding: 1440 twips per
inch, 20 twips per point, two half-points per point, and 12700 EMUs per point.
`line` is in 240ths of a line for `lineRule=auto` (also the default), otherwise
in twips. Section header/footer references inherit from earlier sections when
omitted; `effective_references` records that inheritance. `titlePg=false` disables
the first-page variant even if that variant is inherited.

Formatting profiles aggregate identical direct paragraph/run properties; styles,
document defaults and numbering definitions are reported separately. Absent values
mean inherited or unspecified, not zero. The tool does not render pages or resolve
the full Word style cascade. Table grids, table and cell border overrides, merged
cells and image extents are recorded, so the reference can retain the briefer's
wide grid and the NOM's A4 page without silently correcting them.

## Measured reference (October 29, 2026)

`activity_reference.json` is the unmodified measuring-tool output for all five
Blanks downloaded on October 29, 2026. Google Docs export and the public Drive
folder were verified with HTTP 200 responses; the NOM was downloaded directly
from Drive as its original DOCX. Each report includes its source SHA-256.
The exports are retained at `/workspace/scratch/activity-blanks/` for this session.
Their stable names map to the source IDs below (folder and IDs from handoff #546):

| Report key | Blank source ID | Retrieval |
|---|---|---|
| `concept_note_program` | `1Fo3xQzduUhkplrmT1SHmNus2tbu0eXJ-lpMfmoyeI-k` | Docs DOCX export |
| `executive_briefer` | `1CxvTGKyRkTZNL7bdVmvn1N2yx3HpDMvxCADWoVw2kng` | Docs DOCX export |
| `invitation_external` | `1tlMxL39GEPvu-kH_TiczXKfEpiOipOcOHVxqwQZ8Agg` | Docs DOCX export |
| `invitation_internal` | `127Rf4nDgCqLPx8tXbSX6ogs29a7jZygShZFufPG8V-E` | Docs DOCX export |
| `notice_of_meeting` | `1HQGBRm84BAB8f9KZ6ln-azgJsdTBYeDT` | Drive original DOCX |

Use `https://docs.google.com/document/d/<id>/export?format=docx` for the four
Google Docs, and `https://drive.google.com/uc?export=download&id=<id>` for the NOM.
Google may change export bytes on a later download; the hashes identify these
measured exports, not an assumed permanent byte representation.

### Comparison with measurement plan section 2

All five use 1440-twip margins and 720-twip header distances. Four use Letter
(12240 × 15840 twips); NOM uses A4 (11906 × 16838), as D2 requires. Footer
distances are 720 except the first concept-note section, whose raw export value
is `431.99999999999994` (the plan rounds this to 432). The concept note has two
sections, both with different-first-page enabled. That setting is also enabled
for the memo, NOM and briefer, and disabled for the external letter. References
and inherited references are retained exactly, including the letter's even-page
variant and the concept note's first-page-only footer references.

| Blank | Comparison |
|---|---|
| Concept note/program | All four grids match: 7695/1200, 1850/7370, 1215/7995, 2370/4575/2415. Body uses Times New Roman with 24-half-point runs and single spacing; the activity-title run is 28 half-points. |
| Executive briefer | Grid 2445/8475 (10920 total) exceeds the 9360-twip text area, preserved per D4. The -540 offset is a paragraph left indent in this export, not a `tblInd`. Both VI labels remain in the source. Body runs are Times New Roman 24 half-points; first header has two roughly 75-point anchored logos and no text; footer has no text. |
| External letter | Justified body has 240-twip before/after spacing and line=240. Two closing labels confirm the original/file-copy body duplication. Default header has the anchored letterhead; even-page header is empty. |
| Internal memo | FOR hanging indent 2160/1440, FROM first-line 720, justified body with before/after=240 and line=240 match. Two MEMORANDUM labels confirm duplication. **Blank differs from the Sample grid described in the plan:** initials table is 825/4035 (two columns), not 825/4035/825/4035. Preserve the Blank. |
| NOM | Invitee and values grids match 4005/5730 and 1365/735/7275, each appearing twice. Labels retain left=-90; line=288 and 331 and agenda hanging indent 720/360 match. Unlike the generic 103 × 106-point logo description, its first header has two roughly 75-point anchored logos. |

The memo, external letter and concept note first headers retain the roughly
75-point seal and 103 × 106-point logo. Footer text was inspected locally only:
NOM uses the newer eight-digit numbers; memo, letter and concept note keep the
older numbers; briefer has no footer text. D3 preserves each source's footer;
the telephone-number mismatch remains an office follow-up for a later increment.
Body wording and header/footer wording are absent from the committed report.
These source distinctions refine the plan's combined Blank/Sample description;
no template, numbering, grid, logo or footer has been corrected.

## Verification status

- Passed: `python3 -m pytest tests/test_docx_layout.py tests/test_activity_docs.py tests/test_release_checks.py` (123 tests).
- Passed: standalone fixture tests with Python site packages disabled for the CLI.
- Passed: `python3 scripts/check_release.py release --base origin/main` (9.30).
- The 123-test result above is from the existing PR validation. This resumed
  environment has no `pytest` module, so that suite could not be rerun here.
  This follow-up changes only the measured reference and documentation.
- Full `bash run_tests.sh` was not run; this increment changes no application logic.
- Passed: all five actual Blanks measured; reference compared with plan section 2
  above, including the Blank/Sample distinctions and raw export precision.
- Passed: reference regenerated byte-for-byte with `python3 -S`; five source hashes
  verified and no document-text fields included.
- No Google maker or real draft is needed for this tooling-only increment. When a
  later increment changes a template, follow handoff section 6: maker log, real
  calendar draft, DOCX measurement comparison and side-by-side Sample/draft PDFs.

Increment 0's five-file measurement is complete. PR #548 remains a draft for
review of the documented source distinctions. Increment 1 belongs in a separate PR.
