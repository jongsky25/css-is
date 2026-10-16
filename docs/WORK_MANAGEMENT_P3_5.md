# P3.5 — Manager support overview

October 17, 2026 (Asia/Manila). **In review**, version **6.77**, branch `codex/manager-overview`, based on merged P3.4 (`ccdc142`), incorporating main through `eb4ecf0` and preserving the calendar form release. Prepared for merge on the user’s instruction. Live deployment success has not been independently verified. Phase 3 acceptance remains open.

## Delivered

**Manager support** is available in shared-work navigation at `/work/support`. It presents ten support categories with exact totals and paginated matching record lists. Every count opens its underlying category; each record links to the existing work item, contribution anchor or official document. Actions retain the existing service authority and revision checks on those screens.

The viewer must be the confirmed case lead or have existing officer authority over the case, and must retain access to the case and every linked document. Contributor or creator membership alone does not confer management scope. Technical administrator status alone does not confer it either. Account and directory/grant authority are reloaded, and restricted document access remains authoritative. Unit options come only from visible managed work. A unit filter means the work item’s concerned unit, including its cross-unit contributions.

Only open cases are included. Completed cases and migrated workflows whose official source is closed, cancelled or merged are excluded. Done and cancelled contributions are excluded from active contribution metrics. Reopening a case restores eligibility. The screen remains read-only and available for permitted history while work writes are disabled; it does not change read markers, tasks, deadlines, approvals or records.

## Defined counts

| Category | Count unit | Rule |
|---|---|---|
| Outcomes needing support | Distinct work items | At least one ownership, waiting or date signal listed below |
| Lead confirmation needed | Work items | No confirmed lead |
| No work-item target | Work items | No internal case target date |
| Unassigned contributions | Contributions | No confirmed owner, including proposals |
| Owner access needs attention | Contributions | Confirmed owner inactive or without current case/source access |
| Blocked or waiting | Contributions | Explicit blocker, prerequisite not accepted, or changed decision pending review |
| Contribution review waits | Contributions | Status is for review |
| Overdue contribution targets | Contributions | Internal target before the current Philippine date |
| No contribution target | Contributions | No internal target date |
| Formal review waits | Distinct documents | Linked canonical official record is in review; shared links count once |

Counts overlap and are never added together as a workload score. Cases, contributions and documents stay explicitly labelled as separate units. Missing dates are never interpreted as overdue. Due today is not overdue.

A work item needs support if it has a missing/unavailable lead, an unassigned/unavailable contribution owner, a waiting contribution, an overdue contribution or case target, a case target within seven calendar days including today, or an overdue required official record. One case with several signals counts once and displays each distinct reason. Missing dates alone do not create a risk flag. An overdue reference document does not impose a formal release obligation or create this risk signal; required records use the existing completion scope.

Review wait age is elapsed calendar days from the latest recorded task submission or official review routing. Later milestone edits do not reset it. Missing or future timestamps produce an explicit unknown age. Longest known waits appear first. Age is not an SLA breach or staff performance score.

## Consistency and deployment

The service uses one SQLite read transaction for authority, totals and matching rows, then closes the snapshot without mutations. Each category uses the same collected rows for its count and list; there is no partial scan presented as a total. Lists show up to 25 records per page. Refreshing or changing pages reflects current permissions and work state; intervening changes can alter totals and page membership.

Exact totals require checking all open managed candidates and their source access. This increment does not introduce cached bureau-wide totals, persisted dashboards or a claim of large-scale performance validation. Representative larger-volume performance remains a rollout consideration.

No schema changes. `work_support.py` is added to the explicit HF runtime deployment allowlist. The version/changelog is **6.77**.

## Verification

**346 passed**, zero failures, errors or skips across shared work, Documents, setup, routes, Workspace operations, notifications, admin email, reminder scheduling and calendar entry pages. Only the existing Starlette/httpx deprecation warning. JUnit: `/tmp/work-p35-tests.xml`.

New coverage verifies overlapping categories versus distinct case counts, exact record links and totals, due-today/seven-day boundaries, missing dates, management authority versus participation, technical-admin isolation, inactive users, source access revocation, scoped unit filters, submission-based review age, unavailable owners, cancelled-task exclusion, shared-document deduplication, pagination, closed migrated workflows, read-only behavior with writes disabled, invalid filters, HTTP escaping, grant revocation, completed/reopened cases, and required versus reference deadlines. The access-revocation fixture uses a different authorized officer because the existing Documents service explicitly preserves access for the officer changing restrictions.

Chromium checks passed at 1440px desktop and 390px mobile: metric navigation, contribution record link, recorded review age, unit filtering via keyboard, and exclusion of a creator without management authority. No horizontal overflow or browser errors. The final singular-count wording was checked in the browser and HTTP test. Synthetic local artifacts: `/workspace/scratch/work-p35`. No live messages or external record operations were performed.

## Next

Review and merge P3.5, then perform the **Phase 3 acceptance review** across P3.1–P3.5. Phase 4 begins after acceptance and covers the whole workflow and live integration gates, operational cutover/recovery, role guidance and bureau trial. A local technical pass does not claim successful live deployment or operational acceptance.
