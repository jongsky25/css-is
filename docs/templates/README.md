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

## Verification status

- Passed: `python3 -m pytest tests/test_docx_layout.py tests/test_activity_docs.py tests/test_release_checks.py` (123 tests).
- Passed: standalone fixture tests with Python site packages disabled for the CLI.
- Passed: `python3 scripts/check_release.py release --base origin/main` (9.30).
- Full `bash run_tests.sh` was not run; this increment changes no application logic.
- **Pending:** measure the actual five Blanks and commit `activity_reference.json`.
  This environment has no source exports and its configured network allowlist
  excludes `docs.google.com` and `drive.google.com`. Values transcribed from the
  plan would not be measuring-tool output, so no substitute reference is supplied.
- No Google maker or real draft is needed for this tooling-only increment. When a
  later increment changes a template, follow handoff section 6: maker log, real
  calendar draft, DOCX measurement comparison and side-by-side Sample/draft PDFs.

Keep Increment 0 in draft until the five-file reference has been measured and
checked against the plan. Increment 1 belongs in a separate PR.
