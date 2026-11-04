# Complete UX coverage and clearer wellness filing

Candidate 9.92, branch `feat/ux-coverage-wellness`, based on main `b052f13` and the November 4 UX review. The owner authorized implementation after reviewing the proposed scope.

## Behavior

- Dashboard, Markdown/JSON export and AI analysis include all retained events in the bounded requested date range (maximum 365 days), with an optional exact app-version filter. Blank means all versions; `unknown` selects unstamped events. SQL parameters bind dates and version. The debugging storage reader retains its default limit.
- Requested and observed dates are distinct, including empty results. Reports warn when the requested period exceeds the current retention setting and explain that unrecorded or deleted events cannot be recovered. Historical retention changes cannot be reconstructed from current settings alone.
- Detailed export examples remain capped at 200 independently of complete aggregate inputs. Existing sanitization, admin access and AI actor/data freshness checks remain in place.
- The exact-time option is visible and focuses its input; typing selects it. Unavailable slots explain their reason on tap or keyboard. Previously entered time/date/duration/activity/note remain available after a server error, with focus on the affected field.
- A same-origin authenticated read-only preflight shares validation with `create_wellness_claim`. The write rechecks the rules. A successful preflight reserves nothing, changes no claim and sends no notification. Network failures preserve entries for retry; edits during validation require a fresh submission.
- Pending preflight submit events neither count as actual form submissions nor clear abandonment tracking. The subsequent validated submit counts once.

## Verification

Synthetic regressions cover an older hotspot surviving 5,010 newer events, exact version and unknown-version selection, future/out-of-range exclusion, empty/retention coverage, bounded samples and full-period AI analysis. Wellness regressions cover no preflight writes, overlap arising after a prior valid check, authoritative rejection, entry retention, and date/duration/time/activity errors.

The 390-pixel Chromium flow exercises touch and keyboard explanations, exact-time selection, an overlap error, a network failure with retry, and a successful filing with preserved note. An isolated browser check verifies actual submission/abandonment telemetry across preflight attempts. It does not establish Safari acceptance.

Final focused suites: **181 passed** in normal order (27.32s) and **181 passed** shuffled with seed 311 (27.31s), with zero failures/errors/skips. JUnit reports passed the repository gate. Release metadata, dependency-lock inputs, vendor integrity, AI evaluation contract and whitespace checks passed. The existing Starlette/httpx deprecation warning remains. Full repository/container/advisory CI remains a separate review gate; no production deployment is authorized by this implementation request.

## Operational limits

Reporting currently materializes the full selected retained-event range for the existing aggregators, so memory and runtime scale with event volume; there is no silent fallback to newest events. SQL aggregation or streaming can be considered if measured larger installations require it. This change recovers coverage only for events still stored. No production database was used as a test fixture, and no production form was submitted.
