# Remaining failure repairs — A10 step 1 / candidate 7.30

Scope: resolve the 16 failures recorded after the 7.29 analytics work. This increment does not implement the rest of A10 (suite-wide fixture isolation, Python 3.11 parity or mandatory CI release gates).

## Findings and repairs

| Failures | Cause | Repair |
|---|---|---|
| 1 profile growth test | Application defect: `/me` computed ladder/growth context but the template never rendered it. | Render the existing shared growth component, styles, stage thresholds and guidance on the profile. |
| 3 CSM drafting/export tests | Test-data assumption: Q1 2026 Type-1 responses were claimed to exist but were never seeded. Correct application behavior was an empty-report response. | Create a real Type-1 submission with a timestamp inside the requested quarter; remove it after each test. AI remains mocked. |
| 1 concluded-feed link test | Test-data assumption: a production snapshot was expected to contain an invited/Form-3-only activity with responses. | Seed separate Form-2 and Form-3 examples, assert both appear, then follow both destination links. |
| 1 activity-search test | Test-data assumption: a production activity containing “Learning” was expected. | Seed a uniquely named activity and assert its exact result URL resolves. |
| 9 integrity tests | Missing database: opening absent `css_is.db` silently created an empty SQLite file; schema queries failed. Historical production row-count thresholds were unrelated to the checkout. | Initialize an isolated temporary application database with all three survey types, ratings, notes and a linked person. Preserve integrity queries; assert the exact reference counts. These are storage tests, not production health checks. |
| 1 room-window test | Test clock mismatch: the answer renderer used 14 October 2026 while the block-creation guard used actual today. | Pass the same explicit reference date to `add_block`; production past-date validation stays enabled. |

`reference_form` creates actual rows through storage functions and cleans up after each consuming test, including failures. No survey, search, export or authorization logic is bypassed. No failing test was skipped or marked expected-failure.

## Additional findings from the full run

The first full run fixed all original 16 failures but found two stale assertions from the final 7.29 report wording changes. The unmatched-activity case now asserts “No valid ratings in this scope.” The activity-filter case asserts both rated-person and total-submission counts, retaining its scope-isolation checks. Both modules pass independently after these assertion updates.

## Verification

**Final result: 4,194 passed, zero failures, 16 existing skips.** The original 16 cases pass alone; all 116 tests in their six modules pass. The two additional report modules contribute five passing tests, and all four deployment-packaging checks pass.

Machine-readable results are in `docs/phase1/test-repairs/verification.json`. The original 16 cases are also run alone (the historical production-count test is renamed to reflect its reference dataset). Full-suite results are checked after the targeted repairs.

Testing is local on Python 3.12. Manual production testing remains deferred. Existing environment-dependent skips are reported separately. A passing full run does not imply all possible test subsets or dates are deterministic; that remains A10 step 2.

## Release

Candidate 7.30 updates the application version, changelog and service-worker cache. No database migration is needed. Merge/deployment are separate from this local repair increment.
