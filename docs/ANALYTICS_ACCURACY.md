# Analytics accuracy — A09 / candidate 7.29

Local implementation following deployed 7.28. No production data migration or manual live testing.

## Root causes

Pandas categorical item columns retain the full survey-item vocabulary after slicing. The default groupby included unused categories, whose means were NaN. A dimension average could therefore become NaN even when its actual answers were valid. This contaminated five MRR narrative/export tests: the weakest dimension and corrective advice were wrong, including modality-specific recommendations. Explicit `observed=True` aggregation fixes the cause without changing the locked dimension maps.

Null organization paths also produced non-boolean scope masks. Trends passed non-finite points to Python statistics. Both now handle absent values explicitly.

## Calculation contract

- A scored answer must be explicitly rated, numeric, finite and within its item's scale: SQD 1–5, A/B 1–7, C 1–4. Numeric strings are accepted. Unknown items and missing flags are not scored.
- Explicit N/A and invalid/missing values are separate diagnostic categories. `answer_quality` returns disjoint counts and a validity mask. Source frames and stored records remain untouched. Official SERVQUAL payloads expose these counts and the report page shows an exclusion notice; ARTA item detail exposes invalid counts.
- Dimension = mean of its present item means. Overall perception = mean of present dimension means. Unanswered dimensions do not become zero and do not enter the denominator.
- Overall perception's `n` counts people with valid perception answers. Official report `respondents` still counts all submitted people. Item/dimension `n` counts valid answers. Low-sample flags remain based on contributing people.
- Empty scores, expectation gaps without an expectation, and standard deviations with fewer than two valid observations are absent, not NaN or zero.
- Trend descriptions use finite observations only; fewer than two returns an insufficient-data message. No interpolation or confidence claim is added.
- Existing organization-prefix semantics are retained; missing paths do not match a selected organization.
- Existing saved, edited or AI-authored narratives are not rewritten. Newly generated default narratives use the corrected calculations.

## Independent reference

`tests/test_sparse_analytics.py` runs the same source dataset with ordinary and categorical item columns:

| Input / result | Independently expected |
|---|---|
| B1 answers 7 and 3 | Mean 5, n=2 |
| B2 answer 5 | Mean 5, n=1 |
| Reliability | (5+5)/2 = 5, n=3 |
| B5 answer 3 / Responsiveness | 3, n=1 |
| Overall perception | (5+3)/2 = 4, two contributing people |
| Quality Index | Mean of respondent indices 66⅔ and 33⅓ = 50 |
| Remaining rows | One explicit N/A; five invalid (NaN, infinity, malformed, out-of-range, null) |
| Total submissions | Eight distinct people, separate from two rated people |
| Missing A and C | No expectation, gap or OSQ |

Reference totals are verified in the official report payload and rendered DOCX, PDF, PPTX and XLSX. The XLSX raw rows contain only scorable respondents. The locally rendered report page separately displays rated people, all submissions and excluded answers. Existing MRR coverage verifies all five dimensions and online/in-person/hybrid advice; the activity HTML textarea now has an exact equality assertion against its Excel action text.

## Rollout and remaining work

This is a local candidate until merged/deployed. No schema migration is required. Historical scores with unused categories or invalid answers may change because they are recalculated correctly. Existing source values remain available for investigation. Reverting the code would also restore the original calculation defects.

A10 remains next: deterministic fixtures/date handling and required release gates. The full suite is not presumed green; verification results and remaining failures are recorded separately in `docs/phase1/analytics/verification.json`. Production functional verification remains deferred by user direction.

## A18 follow-up — 7.91

The [report clarity increment](REPORT_SCOPE_CLARITY.md) retains this independent arithmetic reference and adds authenticated HTML/export reconciliation for both item-column representations. The Excel Responses sheet now retains all eight represented submissions, with six blank-score rows, instead of only scorable respondents. Count definitions distinguish form submissions from unique humans, and exact node/descendant matching replaces text-prefix matching within technical reports and their downloads. Historical A09 verification statements above describe that earlier increment.
