# Learned rules assessment — November 4, 2026

Read-only assessment requested by the owner. Sources: authenticated production `/admin/rules` and `/admin/ai`, plus `qa_rules.py`, rule storage/query code, answer slots and help/navigation catalogs at main `d93eb737`. No rule, toggle, hit counter, question or production configuration was changed by the assessment; matching probes ran locally against the pure matcher.

## Scope and evidence

The FAQ layer is ON. All 57 rules are enabled and tagged seed; none is tagged manual or promoted. Lifetime hits total six. Only one rule has a last-hit date within October 5–November 4: the personal conference-room bookings rule, October 10. Creation/update dates are stored but not displayed, so the UI cannot establish when each rule was added or edited.

The candidate panel contains 27 questions, ranked across retained interaction history rather than a selected recent period. The AI log returned 139 rows (below its 200-row cap), spanning July 19–November 4. Filtering visible timestamps to October 5–November 4 gives 52 interactions across all features; 15 are routing/templated-answer/help rows: 14 successful and one rejected. One successful row used provider=rules, 13 used Gemini. This is a small logged sample, not a complete measure of all searches, unique users or savings. Grounded-answer follow-up rows are excluded from that routing denominator.

## Repair first

1. **Unavailable encoding-help target.** The enabled `how do i encode responses` rule targets `help:encode`, absent from the live admin's help catalog. The navigation target `encode` does exist. `_ai_try_rules` falls through when a help target cannot be resolved, so this rule cannot serve through that catalog. Add the intended encoding guide, or deliberately change the rule to Paper entry navigation with corresponding wording; do not assume navigation equals instruction.
2. **Navigation versus balance intent.** Replaying `my wellness break` against the live rule set selects `answer:wellness_left`. The candidate panel instead records that phrase as navigation to `wellness`; an October 9 successful model response corroborates that navigation intent. Prefer an exact navigation rule for this phrase, while preserving explicit remaining-hours questions as balance answers. No production query was submitted to test this.
3. **Calendar month versus rolling 30 days.** Existing exact phrases such as `how many responses this month` target `responses_30d`; the renderer explicitly answers for the last 30 days. Similar month wording affects satisfaction, activities and people-rated slots. Implement calendar-month semantics or make the input expectation explicit; do not describe a rolling window as the current calendar month.
4. **Ambiguous matches need restraint.** Local probes show `what do i have` selecting `approvals_waiting`, and `our tasks` selecting the personal `todo_summary`. Stopword removal drops personal/team qualifiers, and token coverage alone can be overconfident. Keep explicit personal phrases, add ambiguity/intent safeguards, and regression-test negative examples before broadening keywords. These are reproduced matcher behaviors, not claims of observed staff complaints.

All 57 stored canonical phrases match their intended stored targets in a pure-matcher replay. The encoding-help issue arises afterward during target resolution. No other target was absent from the live admin catalog; this does not establish availability for every role.

## Targeted additions worth preparing

| Phrase or family | Suggested handling | Evidence and caveat |
| --- | --- | --- |
| Reserve conference room; book conference | Navigate to `rooms` | Two candidate phrases; successful October 13 and October 10 navigation records. Open booking UI, never imply a reservation was created. |
| How many wellness do I avail this week | Answer `wellness_left` when clearly asking remaining entitlement | One candidate; October 29 answer has positive feedback. Matcher currently misses it. Distinguish hours remaining from hours already used. |
| BLHSD AWA | Navigate to `work_arrangement` | One candidate and October 30 successful navigation. |
| Request ballpen | Navigate to `supplies` | One candidate and October 30 successful navigation; do not imply a request was filed. |
| My wellness break | Navigate to `wellness` | Resolve the existing balance/navigation ambiguity described above. |

These should be narrow exact phrases with positive and negative tests, not broad keyword bundles. Evidence is sparse: model confidence and a successful classification alone are not proof of task completion.

## Do not bulk-promote

- Named activities and requests for specific respondent lists need dynamic activity selection and access checks. Navigating to Monitor does not establish that the requested list exists or may be disclosed. Do not persist personal names or activity-specific text as reusable public-facing defaults.
- Explicit-year questions (for example totals for 2026) must retain their year. Mapping a fixed year to `responses_ytd` would silently change meaning in January. Use a date-aware answer path or explicit clarification.
- Missing-results questions need troubleshooting, not a generic Monitor shortcut presented as a solution.
- The highest-frequency candidate is shown as navigation without a destination. Source inspection shows the UI treats every feature other than `nl_answer`/`nl_help` as navigation; grounded answers can therefore be mislabelled. Candidate aggregation also chooses feature and destination independently, and does not display feedback or the date range. Correct this before treating the promotion panel as authoritative.

## Console improvements

Add a recent-period selector, created/updated/last-used dates, period-specific hits and outcomes, and a rule dry-run showing matched phrase, target and availability by role. Preserve `(feature, destination)` pairs when grouping candidates and explicitly represent grounded-answer/action/unsupported cases. Show feedback and counts of conflicting resolutions before promotion. Detect broken targets, conflicting exact patterns and overlaps before saving.

Ten canonical phrases in the current source seed list are absent from the live table. The bootstrap intentionally skips seeding once rules exist to preserve administrator curation, so deployment does not imply seed synchronization. Review omissions explicitly rather than automatically restoring them. Do not disable zero-hit rules solely for inactivity in this small sample.

## Recommendation

First repair the encoding target, wellness navigation ambiguity and month semantics. Then prepare the small navigation/entitlement phrase set with matcher regressions. Improve the console's recency and candidate classification before any broad promotion effort. This assessment does not change live rules or implement those fixes. No application test suite was needed for this documentation-only save; local matcher replay and documentation diff/link checks provide the assessment evidence.
