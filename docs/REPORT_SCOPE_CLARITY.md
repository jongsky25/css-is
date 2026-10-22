# Survey report scope and export clarity — A18 / 7.91

This increment follows the 7.90 survey form work. It makes `/reports` selections and downloads easier to interpret and fixes selection differences between the screen and exports. Production functional testing remains deferred at the user's direction.

## Selection contract

- Type 1 is bureau-wide and uses active walk-in **submission dates**. Its office selector is removed, incoming office scope is normalized to the bureau and the report explains this boundary. Period options come from active submission receipts, including records without rated answers, rather than the periods available across other survey types.
- Type 2/3 use **activity start dates**, including multi-day activities and responses submitted later. The selected year, quarter or semester is shown as an inclusive date range. The calculations and dimension maps are unchanged.
- Office selections match the exact organization path and its descendants. Similar text prefixes such as `ROOT/DIV2` do not match `ROOT/DIV`. Unknown scopes remain explicit and do not get labelled as the whole bureau.
- Resource-person activity filters resolve both representative and member form IDs of an existing merged activity. HTML, DOCX/PDF/PPTX/XLSX downloads and the roster use the same resolver. Unknown/stale IDs select an empty set; they cannot silently widen an export. Activities with unrated answer records remain selectable.
- Valid but unlisted saved filters remain selected in the controls. Malformed periods are rejected with status 400; the report screen offers a readable correction/reset page. Independent export routes validate their period too. Explicit BLHSD date overrides are validated and the workbook names the effective range.
- Walk-in screen rows, raw extracts and comment drill-down share one active-row/date predicate. Archived forms and responses are excluded. An exclusive next-day upper bound includes both stored timestamp separators and fractional seconds at the end of the selected day while preserving timestamp index comparisons.
- Comment return links retain survey type, office, period and activity. The comment tone trend intentionally spans all periods; report selection does not turn it into a single-point series.

## Reading the report

The report shows the current selection, inclusive dates, total submissions and the contributing sample. Choose filters, then press **Apply filters**; selecting a value does not unexpectedly navigate away. Native submission also works without JavaScript. **Reset report filters** keeps the report type.

Count definitions and download contents are available in an expandable section:

- Submissions are form responses, not unique humans across activities or speakers. SERVQUAL totals follow the active answer records represented in the existing analytics source; this increment does not redesign the atom cache to discover legacy response records that have no answer rows at all.
- Overall SERVQUAL `n` counts responses with valid dimension ratings. Dimension-table `n` counts valid item answers, so one submission can contribute more than one answer. Missing, invalid and N/A values do not become zero scores.
- ARTA overall top-box uses pooled valid SQD1–SQD8 **answers**, not a headcount. Each item uses its own valid-answer denominator.
- SERVQUAL Total is the sum of available dimension means, not a response count. Average is the mean of available dimension means, and can differ from the mean of the individual submission scores in Excel.
- No matching submissions and existing submissions without valid ratings have separate next-step guidance. An empty scope does not imply a zero satisfaction score.

## Downloads and boundaries

All SERVQUAL formats distinguish submission totals and contributing rated responses, including empty/unrated scopes. Date meaning is printed separately from the scope caption. The Excel Responses sheet retains each source submission, leaving scores blank where no valid answers exist; it no longer drops wholly unrated source submissions. Summary coordinates used by existing readers remain stable, with rated-response count appended.

Type 2 gains a direct individual-submission Excel link. The MRR activity inventory has a different row unit (activity). The named resource-person roster groups rated speakers by activity and continues to omit the bureau Director from the named list; aggregate ratings retain the existing policy. Official CO-CSM templates retain their prescribed layout and existing saved narrative behavior.

A download is a fresh request against the then-current data. New submissions, archives or corrections can change later results; no immutable report snapshot is claimed. The plain-language dashboard uses distinct presentation metrics and time-window controls; this increment reconciles the technical report and its downloads, not every dashboard metric or saved narrative. Existing access checks, source values, reporting scales, submission rules and provider boundaries remain in place. No schema migration or dependency is added.

The shared searchable selector now names both its field label and visible selected option through `aria-labelledby`, including after selection changes. Report styles preserve its hidden native select geometry, wrap card actions on small screens and keep filter/apply/reset controls usable on touch devices. Changed shared JavaScript references and the service-worker cache are versioned 7.91.

## Verification

- Focused server/export/reference/archive/draft/browser regression: **110 passed**, no failures or skips. The final additional browser disclosure checks also pass separately.
- CI exposed a pre-existing confirmation-test race: visible receipt HTML can precede the deferred draft initializer. A controlled 300ms script delay reproduces it; the test now waits for matching draft removal rather than equating HTML visibility with completed browser cleanup. Production draft behavior is unchanged.
- Real authenticated HTTP exports exercise member/stale activity IDs across DOCX/PDF/PPTX/XLSX, roster selection, exact organization boundaries, malformed/unlisted filters, fractional end-of-day receipt dates, archived responses, bureau-wide ARTA and comment return filters.
- The independent sparse reference runs with object and categorical item columns: eight submissions, two contributing responses, overall 4.00, dimension total 8.00. HTTP HTML and all four export formats agree; Excel retains all eight rows with six blank-score rows. Existing analytics arithmetic tests remain in force.
- Chromium journeys cover 390px/1440px, light/dark, keyboard Apply/download/reset/search, deliberate filter application and operation without JavaScript. No mutation is sent by these browser journeys. Sampled page overflow is zero.
- Pinned axe-core 4.14.0 samples the filter/context/download regions in filtered, expanded-note and empty-result states. See [machine-readable evidence](audits/2026-10-19/A18_REPORT_AUTOMATED_EVIDENCE.json) for detected findings, incomplete checks and exact scope. Mobile presentation was visually reviewed. These samples do not certify the whole application; real screen-reader/browser/device checks and staff task observations remain open.

Reproduce the focused suite with `python -m pytest -q tests/test_report_scope_clarity.py tests/test_report_scope_browser.py tests/test_sparse_analytics.py tests/test_rp_report_filter.py tests/test_servqual_raw_responses.py tests/test_arta_report.py tests/test_csm_official.py tests/test_report_activity_verbatims.py tests/test_ai_report_draft.py tests/test_form_archive.py`.

For optional local accessibility evidence, provide a pinned local axe bundle through `A18_REPORT_AXE_PATH` and an output directory through `A18_REPORT_EVIDENCE` when running `tests/test_report_scope_browser.py`. Ordinary tests do not download or require npm packages.

## Release and rollback

7.91 increments verified main 7.90 with aligned app/changelog/cache metadata. Publish through the existing required-check and deployment workflow after merge review. Roll back by reverting this increment and publishing a new app/cache version; there is no data migration to reverse. Preserve the corrected activity resolver and archive/date selection during a forward UI repair so a stale filter cannot broaden downloads again.
