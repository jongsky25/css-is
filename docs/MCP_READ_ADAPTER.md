# Office Connect read connection for ChatGPT (A24)

This optional MCP endpoint lets an authorized Office Connect user ask ChatGPT about their current shared work, document status, calendar events, room bookings, supply queues, personal travel filings and permitted activity progress. ChatGPT can receive only records the connected user can see at the time of each request. It cannot approve, edit, submit, download files, or read document bodies and private task submissions through this connection. v8.78 adds a separate default-off [notification action pilot](MCP_WRITE_PILOT.md): ChatGPT can prepare marking one own work notice read, but only the user can execute it by confirming on a signed-in Office Connect page.

## Supported questions

For separately consented, default-off action pilots, see the
[notification confirmation](MCP_WRITE_PILOT.md) and
[new personal supply draft](MCP_SUPPLY_DRAFT_PILOT.md) runbooks, plus
[private task comment drafts](MCP_COMMENT_DRAFT_PILOT.md) and
[personal saved report views](MCP_REPORT_VIEW_PILOT.md). Ordinary read
grants do not gain action permissions.

- “What work needs my attention?” and “What am I waiting on?”
- “Find the document about the budget review and show its status.”
- “Which contribution tasks are attached to work item 123?”
- “What calendar events and activities can I see over the next two weeks?”
- “Which conference room bookings are approved, and which of my requests are waiting?”
- “Which of my supply requests need action, and which stock warnings can I see?”
- “What is the status of my travel filings?”
- “How are the activities I manage progressing?”
- “Give me an overview of what needs my attention across the areas I allowed.”

The tools return titles, status, dates, permitted metadata, and links back to Office Connect. A result can be summarized or compared in ChatGPT, subject to the connected ChatGPT workspace's data handling policies. Opening a source link still uses the normal Office Connect sign-in and permissions.

## Enable and connect

1. Deploy a release containing A24 and configure a canonical HTTPS `CSS_BASE_URL` (or the hosted `SPACE_HOST`). Set `CSS_MCP_ENABLED=1` to expose `/mcp` and its OAuth endpoints. Leave the flag unset until deployment and security checks are complete.
2. In a ChatGPT workspace that supports custom remote MCP connectors, add the server URL `https://<office-connect-host>/mcp`. Choose the OAuth sign-in flow and review the offered read permissions: `work:read`, `documents:read`, `calendar:read`, `supplies:read`, `travel:read` and `activities:read`. ChatGPT may call the registered connector an app. An existing connection needs to be reconnected to add permissions; old grants are not silently expanded.
3. Sign in to Office Connect as yourself. On the consent page, review the listed read permissions, confirm your Office Connect password, and allow access. Return to ChatGPT to finish creating and installing the plugin; approving the grant alone does not install it in a chat.
4. In Office Connect, visit **My profile → Connected tools** to check for an active ChatGPT connection or disconnect it. Disconnecting invalidates its access and refresh tokens.

The previous `/api/v1` bearer integration keys cannot connect ChatGPT's custom MCP client. This adapter uses delegated OAuth grants with PKCE, a fixed resource audience, short lived access tokens, rotating refresh tokens, and an explicit user consent step. It accepts only ChatGPT callback URLs at client registration. Each tool checks the current account, grant, scope, and object permissions. Account security changes and historical restore revoke grants. The baseline tools are read only and each successful read records an audit event without copying a search term or record title into the audit summary.

## Operations and limits

| Tool | Scope | Data |
| --- | --- | --- |
| `list_my_notifications` | `notifications:read` | Own unread shared-work notice metadata only, up to 25 entries |
| `get_room_availability` | `calendar:read` | Conference-room slots for one local date, up to 25 per page |
| `my_work` | `work:read` | Current or waiting inbox, up to 25 entries |
| `list_work_items`, `get_work_item`, `list_work_tasks` | `work:read` | Visible shared work and contribution task metadata |
| `find_documents`, `get_document` | `documents:read` | Visible document metadata, status, and source link |
| `list_calendar_events` | `calendar:read` | Visible calendar entries, activities and room bookings, dates, status, venue and source link |
| `list_supply_queue` | `supplies:read` | Own request metadata, approvals in a current grant scope, and stock warnings for current custodians or auditors |
| `list_my_travel_filings` | `travel:read` | Own travel filing reference, activity, status, dates and deadline |
| `list_activity_progress` | `activities:read` | Activity manager's team-scoped schedules and aggregate registration progress |
| `my_office_overview` | Each included module's own scope | Small current summaries from granted areas; ungranted areas marked `not_granted` |

List requests are paged at 25 items or fewer. Calendar reads cover at most 31 days per request and use the calendar's current viewer and audience rules. Approved room bookings are shared office information; pending requests are visible only to the requester and room approvers. Linked bookings follow the calendar's existing duplicate folding, so their event may carry the room venue instead of appearing twice. Attendee names, meeting URLs, leave and birthdays are excluded. Supply queues use the same role and unit checks as the Supply dashboard; warning quantities require a current custodian or auditor grant. Travel reads are owner-only and use stored deadlines, which may be stale until the filing is reopened in Office Connect. Activity progress uses the same management scope as the Monitor and excludes individual registration and response data. Connected reads use the integration read rate limit. Public OAuth requests have a separate rate limit and bounded request size. Consent attempts use the integration issuance rate limit. Access tokens last one hour; refresh grants last up to 30 days and rotate on use. These read tools expose no mutations or file content. The separate v8.78 notification pilot is documented in [MCP_WRITE_PILOT.md](MCP_WRITE_PILOT.md).

## Verification and rollout boundary

The automated synthetic journey covers OAuth discovery, client registration, consent, PKCE exchange, MCP initialization, permitted and hidden records, permission withdrawal, refresh rotation, and disconnect. It does not prove that a particular ChatGPT workspace can add the connector or that the production host exposes the endpoint correctly. After deployment, use a supported ChatGPT workspace and a low privilege test account to complete one real connection and compare the returned records with Office Connect. Keep the feature flag off or disconnect the test connection if that check fails.

If the consent step does not return to ChatGPT, check **My profile → Connected tools → ChatGPT connections**. If no active connection appears, the grant did not complete. The consent response displays an HTML error and a retry link where appropriate; it should not download a file named `mcp-consent`. Repeat the connection on ChatGPT web and capture the visible error. The default consent covers the supported read areas; a client that explicitly requests fewer scopes receives only those scopes unless the person explicitly selects additional read permissions on the consent page. Optional permissions are unchecked and bounded by the client registration; existing grants are never widened.


If consent lists only work access, select needed areas under **Optional additional read access** before confirming. All registered ChatGPT clients, including legacy work-only registrations, can select from the server's supported read areas. Registration eligibility does not grant data access: optional scopes stay unchecked, the token contains only requested and explicitly selected permissions, and existing grants and their refresh tokens remain unchanged. After this fix is deployed, start a fresh authorization flow; deleting and recreating the app is not required to see the additional choices.

Scope-choice regression: `python -m pytest tests/test_mcp_read.py` exercises narrow consent, opt-in calendar access, token/refresh scope parity and legacy-registration recovery and rejection of unsupported/write scopes, alongside the baseline OAuth/read/revocation journey. This remains synthetic evidence; verify the updated deployed consent and one calendar query in the actual ChatGPT client before calling the live issue resolved.


## M1.1 pilot switches and acceptance

Deploy v8.42 or later. Set `CSS_MCP_NOTIFICATIONS_ENABLED=1` and/or `CSS_MCP_AVAILABILITY_ENABLED=1` in the host environment and restart to enable each new read independently; absent flags leave tools discoverable but returning `availability: not_available`. Disable the relevant flag to roll back. Shared work and documents must also be enabled for notifications. Room slots must already have been initialized through ordinary Office Connect setup: MCP never initializes slots while reading.

Reconnect to explicitly approve `notifications:read`. Older work/calendar grants do not acquire this personal scope. The notification tool covers only unread shared-work notices, not the full bell or all personal request statuses. It excludes titles, authors, message bodies, wellness, approval queues and other people's notices, and does not mark read. Follow `next_before` even on an empty filtered page. At most 250 candidate notices are scanned per call before returning a continuation; this is a bounded service scan, not an unbounded export. Cursor order uses notice IDs descending; permissions are checked again per call.

Room availability covers the conference room only, not personal free/busy. Pass `day` as YYYY-MM-DD in Asia/Manila, and follow `next_offset`. States match the signed-in picker: free, requested, booked, closed. Requested slots do not hold a booking; `available_for_request` is a snapshot, not confirmation. Booking titles, people, reasons and meeting links are excluded. Holidays, weekends, blocked hours, approved reservations and the booking horizon follow the source service. Booking actions still check conflicts in Office Connect.

The overview includes a notifications module with `not_granted` for old grants, `not_available` when disabled and successful empty data when enabled but empty. All new calls retain current account/grant checks, rate limits and content-free read auditing. No writes or new tables are added.

Automated checks: `python -m pytest tests/test_mcp_read.py tests/test_mcp_m1_reads.py`. Before wider use, compare low-privilege and manager results with `/work/updates` and the room picker, remove work visibility and disconnect the grant, test empty/disabled states and pagination, and record deployed SHA/version and hosted latency/query counts. Live acceptance and capacity measurements remain pending; a successful earlier calendar read alone does not prove these new tools. Keep sensitive notice domains outside this increment.


## M1.2 first delivery: monthly Type 1 CSM

`get_csm_summary(year, month)` requires a separately approved `surveys:csm:read` scope. Enable `CSS_MCP_CSM_ENABLED=1` and restart after deploying v8.44 or later; the flag defaults off. Disable it to roll back. Existing grants never gain this scope through refresh. A narrow grant can opt in during fresh authorization. The UI report is bureau-wide and available to current signed-in view roles; the service reloads the account and applies that same role boundary. This does not grant access to Type 2/3 surveys.

The first projection accepts fixed, non-overlapping calendar months only, by submission date in the application's local reporting convention. It returns a matching `/reports?type=1&date_from=...&date_to=...` link, as-of timestamp, submission count and pooled valid SQD1–SQD8 answer count. It shares the current report predicate (including archived/canonical walk-in handling) and exact SQD scoring, including existing numeric normalization. SQD0 is excluded from the headline. N/A does not become a zero score; counts describe form submissions/answers, not unique humans.

No respondent identities, raw answers, comments, demographics, person/service filters, rankings or file content are exposed. Per-item/overall score fields are withheld when fewer than ten submissions exist or any populated SQD item has fewer than ten valid responses, avoiding a pooled headline revealing a suppressed item's numerator. This is a new MCP projection rule; the signed-in source report is unchanged. Empty, no-valid-ratings and insufficient-sample states are explicit and do not mean 0% satisfaction. Aggregate results can still change as new responses arrive; this pilot is not a guarantee against every inference across repeated snapshots.

The service reads at most 5,001 response IDs and refuses a month above 5,000, linking to the source report instead of silently truncating. The bounded result contains nine SQD items at most. No arbitrary SQL or date-window export tool is published. Services/demographic breakdowns, comparisons and Types 2/3 remain separate increments with their own permission and suppression review. The general office overview does not silently add survey scores.

Before enabling the pilot, compare October/adjacent-month summaries with the same source report, check N/A-only, archived and month-end timestamp fixtures, verify old grants are denied, and disconnect a test grant. Record deployed SHA/version, numerical parity and hosted capacity measurements. Local tests are synthetic; live acceptance remains pending.


## M1.2 second delivery: quarterly Type 2 activity satisfaction

`get_activity_survey_summary(year, quarter)` returns a bureau-wide aggregate for a fixed calendar quarter (1–4), using activity **start dates**, including late submissions. It uses separate `surveys:activities:read` consent; ordinary `activities:read` progress permission cannot read survey results. After deploying v8.45 or later, enable `CSS_MCP_ACTIVITY_SURVEYS_ENABLED=1` and restart for a pilot. Default off; disable the switch to roll back. Reconnect and approve the new scope; existing grants/refresh tokens remain unchanged.

Current signed-in view roles can read the existing bureau-wide Type 2 report; the new service reloads that same account authority and applies the delegated grant/scope checks on each call. It reads fresh data in the authorization snapshot and links to the exact `/reports?type=2&period=quarter:YYYY-Qn` selection. It does not add office/person/activity filters or narrow/widen an unknown selection. Type 3 speaker ratings are never included.

The shared SERVQUAL block computes perception as the mean of available dimension means, each formed from its item means. This is not a top-box percentage or the mean of individual submission scores. Expectation (A) and B perception items use 1–7; overall service quality (C) uses 1–4. Gap is perception minus expectation. Invalid/nonfinite, out-of-scale, missing and N/A answers retain the existing engine's treatment. Results include denominator definitions: `submissions` is all active form receipts, `report_submissions` is receipts with answer records represented in the historical report atoms, `rated_respondents` contributes valid dimension ratings, and dimension counts are valid item answers. These are not unique humans across activities.

No identities, demographics, comments, response details, speaker scores or rankings are returned or loaded from context services. A score projection is withheld if fewer than ten respondents contribute perception scores or any populated A/B/C item has fewer than ten distinct valid respondents. This suppression includes every mean, gap and dimension score to avoid indirect subtraction. No-valid-ratings and no-matching-responses are explicit, never zero satisfaction. Suppression intentionally differs from the signed-in UI, and does not establish a guarantee against inference across changing snapshots.

Capacity is bounded at 5,000 active responses and 100,000 answer rows per quarter, with a capacity refusal instead of partial scores. All answer-backed rows are counted for historical-report parity, but only the engine's permitted scale values contribute scores. Archived forms/responses are excluded; consolidated-report handling of pooled forms is preserved. There is no arbitrary query/export tool, new table or business mutation.

Acceptance: compare all published means, gaps, dimension counts and source filters with the report, including sparse/N/A-only data, late submissions, archived records, Type 3 exclusion and receipts without answers. Verify activity-progress-only and disconnected grants are denied, compare low/high-privilege view accounts, and record deployed SHA/version and hosted query/latency measurements. Local tests are synthetic; hosted acceptance remains pending. Individual activity summaries, unit trends and Type 3 remain later increments.


## M1.2 third delivery: annual Type 3 resource-person summaries

`get_resource_person_survey_summary(resource_person_id, year)` requires separate `surveys:resource_persons:read` consent. After deploying v8.46 or later, set `CSS_MCP_RESOURCE_PERSON_SURVEYS_ENABLED=1` and restart for a pilot. The flag defaults off and returns no person name while disabled. Disable it to roll back. Existing CSM/activity/progress grants do not gain person ratings through refresh; reconnect for explicit approval.

The service reloads the active account and current directory person each call. It shares the existing person-profile rule: ordinary view roles may read visible people; hidden people and the current Director require the existing `hide` capability. Missing and unavailable IDs produce the same generic error. Archived directory people still resolve historically, as on the existing profile; archived forms/responses are excluded. This is visibility parity with the profile, not a new requester/manager ownership rule. Check directory visibility before enabling the pilot.

The fixed annual selection uses activity start dates and includes late submissions for that year's Type 3 forms. It returns an exact year-filtered person-dashboard link, effective dates and as-of timestamp. Other people's forms and Types 1/2 are excluded. Only the permitted person's name/ID and aggregates are projected; no contacts, respondent identities, individual answers, comments, survey rosters, peer comparisons or rankings.

The published headline is the person dashboard's quality index (0–100): normalize valid B answers (1–7) and C (1–4) to 0–100, average available answers within each response, then average across responses. A is excluded. This differs from the consolidated SERVQUAL mean of dimension means and is labelled explicitly. OSQ is the valid C mean on 1–4. Dimension means use DIM_MAP_FORM3, with Assurance B6–B7, Empathy B8 and Tangible B9; all dimension means use 1–7. No separate speaker-mean or expectation/gap headline is introduced in this delivery.

Counts distinguish all active form receipts, answer-backed historical report submissions, respondents with valid perception ratings and quality-index contributors (B or C). They count submissions, not unique humans across engagements. Require at least ten valid perception and quality contributors and ten distinct valid respondents for every populated B/C item before publishing any score. A-only and C-only data return no_valid_ratings for this perception-summary tool; empty, small-sample and capacity-refused results are distinct and are not zero satisfaction. Caps remain 5,000 responses and 100,000 answer rows, refusing all scores rather than truncating. There are no activity filters or annual comparisons, so merged forms for the selected person contribute once through each stored response without representative-ID selection ambiguity. Changing snapshots can still allow inference; this pilot is not a formal anonymity guarantee.

Acceptance: compare quality index, OSQ and dimension means with the selected annual person dashboard, including asymmetric Type 3 dimension scores, late submissions and archived records. Change hidden/Director flags and confirm denial on the next call for a viewer while existing administrator access remains intact. Verify other people and Type 2 are excluded, partial item cells suppress all scores, progress-only grants are denied, and disconnect stops fresh reads. Record deployed SHA/version and hosted performance. Local tests are synthetic; live acceptance remains pending.


## Individual activity discovery and satisfaction details

After v8.48 deployment, set `CSS_MCP_ACTIVITY_DETAILS_ENABLED=1` and restart for this independent pilot. Default off; disable the variable to roll back. Reconnect for explicit `surveys:activity_details:read` consent. Quarterly `surveys:activities:read`, progress `activities:read` and existing grants do not automatically gain discovery or detail access.

`find_survey_activities(year, quarter, query='', limit=10, offset=0)` searches current Type 2 activity titles within a fixed start-date quarter. Query is limited to 120 characters; page size is 1–25. Results have a representative activity ID, title (bounded to 250 characters with a truncation marker), dates and source link. Search uses the full title. Metadata includes no scores, counts, speaker names, venue or organizer details. Only groups with active Type 2 answer-backed responses are eligible, including unrated/N/A-only records. Planned or empty forms and speaker-only groups are not a complete calendar/activity inventory. `next_offset` orders by start date and representative ID descending; each page is a fresh snapshot, so changes between pages can shift results.

`get_activity_survey_detail(activity_id)` accepts either the representative ID or any current member form ID of an eligible group. It uses the same current date/normalized-venue/organizer grouping as the report. A member that becomes archived/pooled or leaves the current group is resolved only against the new current inventory; unavailable IDs never fall back to an unfiltered report. The full merged group is formed before filtering/pagination/scoring. Only Type 2 responses contribute, even if the representative/member ID is a speaker form. Current valid view roles share the existing signed-in report authority; the service reloads account and grant checks on every call.

The scorecard matches `dashboard_insights.activity_servqual` on `/reports/activities/{representative_id}`: all five Type 2 dimensions, expectation (A), OSQ (C) and SERVQUAL gap. The activity list card's event-only headline can differ and is not relabelled as this score. A/B are 1–7 and C is 1–4. Counts distinguish receipts, answer-backed report submissions and valid perception contributors, not unique humans across forms. No comments, attendance rosters, individuals, demographics, speaker scores or rankings are loaded into the result. Small populated A/B/C cells or fewer than ten perception respondents suppress all scores.

Discovery can find N/A-only groups whose scorecard is unavailable. No-valid-ratings is explicit; when only people dimensions have valid ratings and the source detail page has no event score, return `not_available/source_report_unavailable` instead of publishing a divergent headline. Empty results never mean zero satisfaction.

As of v8.65, archive size alone does not refuse discovery. Group active non-pooled Type 2/3 metadata for the requested start quarter inside SQLite, using the source report's Python grouping key (date, Unicode-trimmed/lowercased venue, and external organizer or lead unit). Filter the full first-Type-2 title with literal Unicode casefold matching after complete grouping, then order by date/representative ID and fetch at most `limit + 1` rows. Each page contains at most 25 results; offset is bounded to 1,000,000. No directory/contact joins or global Python inventory load are needed.

Detail resolves the requested active representative/member ID directly and loads only its complete current group, including Type 3 members when establishing identity. Metadata queries stop at 20 million SQLite VM steps or five seconds and return `capacity_limit` without partial results; the connection's progress handler is cleared afterward. Per-group metadata is capped at 2,000 forms. Detail scoring retains caps of 500 active Type 2 member forms, 5,000 responses and 100,000 answer rows. Refuse over-cap results without splitting groups or publishing partial scores. Read audits omit search terms and titles; neither tool writes business state.

Acceptance: compare discovery and representative/member links against the source activities and full detail scorecard; test merged sessions, title/date changes, archiving, unknown IDs, N/A-only and people-only records, page boundaries and source links. Verify old quarterly/progress grants are denied, disconnect stops reads, and record deployed SHA/version and hosted latency/query counts. Local tests are synthetic; pilot evidence remains pending. Unit comparisons, period trends and writes are separate increments.

## Unit discovery and quarterly Type 2 summaries — v8.49

`find_survey_units(query='', limit=10, offset=0)` and `get_unit_activity_survey_summary(unit_id, year, quarter)` require new `surveys:units:read` consent. Enable `CSS_MCP_UNIT_SURVEYS_ENABLED=1` and restart only for an operator pilot; defaults off, disable for rollback. Existing bureau-quarter, progress, individual-activity and person grants do not acquire unit access. Refresh the ChatGPT app's tool catalog separately from reconnecting for consent; phone-only refresh remains a client limitation. Hosted acceptance remains pending.

Discovery returns current unit IDs, names and paths, with literal case-insensitive search (120 characters), deterministic path/ID ordering and pages of at most 25. Refuse inventories above 2,000 units. These units are report selectors, not a list of units with survey responses. Each page is a fresh snapshot.

The quarterly summary matches `/reports?type=2&period=quarter:YYYY-Qn&org=PATH`. Like that report, all current active report viewers can select any unit; it is not a manager-only or own-unit restriction. Type 2 attribution comes from the current form's `lead_org_id` and the current unit path, including the exact selected path and slash-delimited descendants. Similar prefixes, wildcard characters, attendee units, event management records and speaker affiliation do not substitute for lead-unit attribution. A unit rename, move, form reassignment, archival or account deactivation takes effect on the next read. Unknown IDs never fall back to bureau totals. Forms with missing lead-unit paths are excluded from unit summaries; pooled-form treatment matches the consolidated report.

Reuse the bureau-quarter scoring: mean of five available dimension means, expectation A (1–7), perception B (1–7), OSQ C (1–4), gap, valid-item denominators and distinct counts for receipts, answer-backed report submissions and rated respondents. Counts are not unique people across activities. No respondent identities, demographics, comments, speaker scores, comparisons or rankings. Withhold all scores if fewer than ten perception respondents contribute or any populated A/B/C item has fewer than ten valid respondents. This suppression is not a formal anonymity guarantee: overlapping parent/child reports and changing snapshots can permit inference. Do not describe these results as anonymized exports.

Caps remain 5,000 active responses and 100,000 answer rows per selection, refusing excess without partial scores. Queries run under the shared authorization snapshot; audit records omit search text and unit identity. No schema/dependency/business mutation. The overview remains unchanged.

Acceptance: compare parent/child quarter selections and five-dimension scores against the linked consolidated report, including literal wildcard-like paths, sibling-prefix collisions, pooled forms, late responses, archive changes and current reassignment. Confirm small/empty/N/A states, missing units, scope denial, account deactivation, disconnect and hosted latency/capacity. Record deployed SHA/version and synthetic-account results before broader enablement. Period comparisons remain a separate increment.

## Consecutive-quarter unit comparisons — v8.50

`compare_unit_activity_surveys(unit_id, year, quarter)` compares exactly two disjoint calendar quarters: the selected quarter and its immediately preceding quarter (including prior-year Q4 for Q1). Valid selected periods are 1900 Q2 through 9998 Q4. No arbitrary dates, peer units, rankings or extra filters. New `surveys:unit_trends:read` consent and default-off `CSS_MCP_UNIT_TRENDS_ENABLED=1` govern this independent pilot. Unit summary and bureau/activity scopes cannot read comparisons. `find_survey_units` still requires its own `surveys:units:read` permission and `CSS_MCP_UNIT_SURVEYS_ENABLED`; once a unit ID is known the comparison flag works independently of that summary flag. Reconnect for the new scope and refresh ChatGPT's catalog separately. Hosted acceptance remains pending.

Both periods use the current form lead-unit/descendant rules, current role/account/grant authority, consolidated Type 2 arithmetic and source links, within the same authorization snapshot. Historical values can change with current reassignment, path changes, archival and late responses. The comparison is descriptive across different activity/response mixes, not a matched-person study or evidence of causation/significance. No personal answers, comments, speaker scores or demographics are loaded.

Each period independently caps at 5,000 active responses and 100,000 answer rows; at most two such selections are processed per call. Both must be rated under all existing small-item/ten-respondent rules before any scores or changes are returned. If either fails, return `comparison_state=not_comparable`, period metadata/states/counts only, and no scores from the other period. Capacity refusal also makes overall availability `not_available`. Empty or unrated periods are never zero satisfaction. Original unit summaries retain their existing behavior.

For comparable periods, return both source scorecards and `changes` as current minus previous: overall, expectation, OSQ, SERVQUAL gap and each dimension mean. A/B remain 1–7, C remains 1–4; deltas are original scale points, not percent or percentage-point changes. A missing optional metric/dimension in either period produces a null delta, not zero. Parent/child overlap and changing snapshots still permit inference; this is not a formal anonymity guarantee.

Acceptance: compare both linked source selections, year rollover and within-year boundaries, asymmetric/sparse ratings, missing optional metrics, one empty/small/N/A period on either side, capacity refusal, current unit reassignment/archival, wrong scope, inactive/revoked grant and no-business-write behavior. Disable the comparison flag to roll back. Record hosted version/SHA and latency/query counts before broader enablement; earlier pilots remain pending.

## Consecutive-month CSM comparisons — v8.52

`compare_csm_months(year, month)` compares exactly two disjoint bureau-wide Type 1 calendar months by submission date: the selected month and immediately preceding month (including previous-year December for January). Valid selected months are February 1900 through December 9998. New `surveys:csm_trends:read` consent and default-off `CSS_MCP_CSM_TRENDS_ENABLED=1` govern this independent pilot; the existing `surveys:csm:read` grant does not expand. The CSM summary flag can remain off while the comparison flag is on. Refresh ChatGPT's tool catalog separately from OAuth consent when supported client access is available. All hosted pilot acceptance remains pending.

Both months run in one current account/grant authorization snapshot and follow the existing official CSM active-form/response/date predicates, including the permanent standing walk-in form archive exception (individual archived responses remain excluded). Activity date is not the submission period. Report viewers share the existing bureau-wide authority; there is no additional service, unit, person, demographic or custom-date selection. Return the exact source URLs for both months. No comments, respondent identities or demographic/contact metadata are loaded.

For each period, the overall is the pooled proportion of valid SQD1–SQD8 answers rated 4 or 5, excluding SQD0. Item SQD0–SQD8 percentages use their own valid-answer denominators; N/A/missing values retain the source report's treatment. This is not a mean of item percentages. Publish the same one-decimal percentages as the reports. Changes are current minus previous published percentages, rounded to one decimal, in percentage points (e.g. 50% to 60% is +10 percentage points). They are not relative growth or claims of causation/significance. Different months can have different service and respondent mixes; submission counts are not unique people.

Cap each month at 5,000 active response receipts and 100,000 loaded SQD-answer rows, at most two such selections per call. No partial scores. Both months must pass the existing CSM small-sample rules (at least ten submissions and ten valid answers for every populated SQD item) before any percentages, positive/NA item counts or changes are published. If either period is empty, unrated, too small or over capacity, return `comparison_state=not_comparable`, period metadata/states/aggregate counts only, and withhold both scorecards and all changes. A capacity refusal also returns overall `availability=not_available`. A missing optional item in either rated period yields a null item delta, not zero. Source-month summaries retain their existing behavior. Overlapping other reports and changing snapshots can still permit inference; this is not a formal anonymity guarantee.

Acceptance: compare both linked official reports and their pooled/per-item denominators, one-decimal percentages and percentage-point changes, including unequal item counts, SQD0 exclusion, leap-month and year rollover boundaries, both timestamp separators, archived records, sparse/empty/N/A months, missing optional items, response/answer limits, old-scope denial, current account/grant revocation and no-business-write behavior. Record hosted version/SHA and performance before broader enablement. Disable the comparison flag for rollback; broader CSM breakdowns remain later increments.

## Resource-person discovery and consecutive-year comparisons — v8.53

`find_survey_resource_persons(query='', limit=10, offset=0)` and `compare_resource_person_surveys(resource_person_id, year)` require new `surveys:resource_person_trends:read` consent and default-off `CSS_MCP_RESOURCE_PERSON_TRENDS_ENABLED=1`. The existing named annual `surveys:resource_persons:read` grant cannot discover people or compare years. This pilot works independently of the annual summary switch. Reconnect for explicit consent; refresh ChatGPT's catalog separately when supported client access becomes available. Live acceptance, including earlier pilots, remains pending.

Discovery returns only ID, name (250-character bound plus truncation marker), historical/archive status and a person-dashboard link. Literal case-insensitive name search uses the full name, at most 120 query characters, up to 25 records/page and a 2,000-person global inventory cap before projection. Apply the existing `can_view_resource_person` hidden/Director predicate before searching/paging. Report viewers see permitted people; current hide-capability administrators retain the source dashboard's hidden/Director access. Include archived directory people because their historical reports remain available, and label them as archived. Discovery does not imply that someone has Type 3 responses. Order by casefolded name and ID, not by score; each page is a fresh snapshot. No contacts, positions, designations, unit affiliations, respondent data, survey counts or scores are projected. Position/designation/hidden flags are read only to evaluate current visibility.

The annual comparison accepts one selected year from 1901 through 9998 and compares it with the previous calendar year, based on activity start dates (late submissions follow that basis). Both periods use current person/account/grant authority in one snapshot. Missing and currently forbidden IDs return the same generic denial. Recheck hidden/Director changes on every request before returning metadata; disabled comparison returns no name. No peer selection, ranking, demographics, activity filters or arbitrary dates. Named annual summaries keep their existing output/flag behavior, using a bounded minimal person lookup instead of a full-directory load.

Reuse the person's source dashboard quality index: normalize valid B (1–7) and C (1–4) to 0–100, average within each respondent, then average across respondents. A is excluded; Type 2 and other people never contribute. Return exact year-filtered source URLs, quality index, OSQ and Type 3 dimensions for both years only if both meet every existing minimum-sample/item check. Changes are current minus previous: quality-index points on 0–100, OSQ mean points on 1–4 and dimension mean points on 1–7. Missing optional metrics yield null changes, not zero. Different years may reflect different activity/response mixes; these changes are not relative growth, causal findings or statistical-significance claims. Counts are not unique humans across activities.

Each year independently caps at 5,000 active responses and 100,000 answer rows; at most two selections per comparison. Empty, unrated, small or over-capacity periods return `comparison_state=not_comparable` and suppress both scorecards and all changes. Return period metadata/states/aggregate counts only. Capacity failure also makes overall availability `not_available`. Current archive, person assignment and visibility rules apply on the next read. Overlapping source reports and changing snapshots can still permit inference; this is not a formal anonymity guarantee. No comments, raw answers or contact records are loaded into these projections, no new schema/dependency or business writes; audit records omit name searches and person identity.

Acceptance: compare both annual person dashboards and all dimension/quality/OSQ values, include missing metrics, sparse C/B cells, empty/N/A/archived years, Type 2/other-person exclusion, late submissions, exact bounds, inventory refusal and no writes. Verify hidden/Director search exclusion before pagination, administrator visibility and role downgrade, renamed/archived directory people, account/grant revocation, and old annual-scope denial for both tools. Record deployed version/SHA and hosted latency/capacity evidence before broader use. Disable the independent flag for rollback. Earlier live pilots remain pending.

### Phone-accessible readiness (v8.62)

Open **My profile → Connected tools → Check ChatGPT readiness**, or visit
`/account/integrations/mcp` while signed in. The page is a status view, with no
settings writes and no business-tool calls. It reads the running server's actual
registered tool names, deployed build metadata, an explicit allowlist of pilot
switches, and only the signed-in owner's latest 50 OAuth grants. Registration,
activation and each connection's consent are separate checks. A grant being
active means unrevoked with refresh lifetime remaining; the page cannot identify
which connection ChatGPT uses or verify its saved access token. Existing role,
module, record, sample and capacity checks still apply to actual reads.

Selectable prompts cover Type 1 monthly summaries/comparisons, Type 2 bureau,
individual activity and unit reports/comparisons, and Type 3 person summaries and
comparisons. Fixed 2026 source links are examples; individual activity, unit and
person verification must use the exact source links returned by those tools.
No hosted pilot acceptance is marked complete by visiting this page.

A disabled server and an unavailable catalog are shown explicitly, rather than
reported as a successful empty catalog. The page cannot inspect or refresh
ChatGPT's saved tool snapshot; that remains a separate ChatGPT app-management
step on a supported desktop browser.

### Linked Type 3 person selection through activity progress (v8.71)

`list_activity_progress` keeps its existing arguments and `activities:read`
authority. An outside activity now includes `survey_context.survey_type=3`, the
existing `event_rp_results_url` activity-filtered source link, and an explanation
that its management response count spans linked non-archived forms rather than a
verified Type 2 scorecard or unique-person total. The source link remains subject
to browser sign-in/report permissions.

`survey_context.resource_persons` is supplemental metadata. Require the same
current OAuth grant's `surveys:resource_persons:read` permission and existing
`CSS_MCP_RESOURCE_PERSON_SURVEYS_ENABLED=1` switch. Recheck current account/view
and shared hidden-person/Director visibility; select only active linked Type 3
forms from an activity already selected through the actor's permitted event
feed. Deduplicate people, apply visibility before sorting/limiting to 25, and
return `truncated` when further permitted people exist. Per-activity distinct
person inventories above 2,000 refuse metadata without partial output. Archived
directory people remain eligible for historical annual reports and are labelled.
No form subjects, respondent identities/answers, contacts, counts per person,
rankings or score fields are returned here.

Use each returned `resource_person_id` and `annual_summary_year` with the existing
`get_resource_person_survey_summary`. Annual scores can include other activities;
they must not be labelled as the selected activity's scores. Use
`activity_report_url` for that activity's own Type 3 source report. Missing person
consent or a disabled pilot is explicit and does not block ordinary activity
progress. No new tool, argument, scope, flag or stored grant widening is added;
existing tool registrations can consume the extra response metadata after deploy.
Hosted Summit person/annual verification remains pending.

### Type 3 scorecard for one resource person at one activity (v8.74)

Tool: `get_resource_person_activity_survey(activity_id, resource_person_id)`.
Scope: `surveys:person_activities:read`. Pilot switch:
`CSS_MCP_PERSON_ACTIVITY_SURVEYS_ENABLED=1` (off unless explicitly configured).
This is separate from annual `surveys:resource_persons:read`: existing grants and
refresh tokens cannot acquire it automatically, and neither annual nor Type 2
pilot activation substitutes for the new switch. The optional consent checkbox
and phone readiness page show this separate permission/activation.

Find a managed outside activity with existing `list_activity_progress`; its
`survey_context.activity_id` is the current linked form ID and its permitted
person selectors supply `resource_person_id`. Those selectors retain their own
activities/annual permission checks. IDs may also come from signed-in source
reports; the new read itself needs only the new scope and current report/person
authority. A newly registered tool needs the saved ChatGPT catalog refreshed on a
supported desktop browser before use; phone-only users can defer activation.

Resolve the activity's current full non-archived, non-pooled Type 2/3 group with
the shared source grouping key. Accept representative or member IDs, but return
the canonical minimum form ID. Require a currently visible named person's
answer-backed Type 3 engagement on/after the source cutoff (June 15, 2026).
Current hidden-person/Director visibility applies even if the original grant
was issued when a person was visible. Unknown, stale, archived and unrelated
IDs produce a generic unavailable-record error; no annual or bureau fallback.

Read only this person's active Type 3 receipts/answer values within that group.
The headline matches `/dashboard/people/{person_id}/activity/{representative}`:
normalized B/C quality index 0–100 (A excluded), OSQ C on 1–4 and five Type 3
dimension means on 1–7. Return that person/activity source URL and a separately
labelled activity-filtered Type 3 aggregate report URL. The aggregate report's
pooled SERVQUAL headline is a different measure; it does not verify a person's
quality index. Do not present annual, other-person or whole-activity scores as
this scorecard. Counts are receipts/contributors rather than unique people.

Reuse annual Type 3 suppression: at least ten quality contributors and valid
perception respondents, plus ten distinct valid respondents for every populated
B/C item; any insufficient cell withholds all score fields. Empty/unrated
results stay explicit. Bound metadata to 2,000 forms for the selected group,
20 million SQLite VM steps or five seconds; bound this person's forms to 500,
responses to 5,000 and answer rows to 100,000. Refuse over-cap reads without
partial scores; clear metadata query handlers even on errors. No respondent
identities, comments, demographics, peer comparisons/ranks, causal claims or
business writes. One current actor/grant snapshot, fixed-family minimized audit.

Acceptance remains pending hosted activation: discover the Summit's two IDs,
retrieve each activity-specific scorecard, compare with that person's exact
activity page, and distinguish it from the 2026 annual summary. Synthetic checks
cover source scoring, combined sessions, Type 2/other-person/other-activity and
archived/pooled exclusions, rare-cell suppression, current visibility, source
cutoff, capacity, representative/member resolution, scope/flag independence and
revocation. Existing annual and Type 2 reads retain their own behavior.

Personal calendar entry preparation is a separate default-off pilot: see
[M2.5 setup and acceptance](MCP_PERSONAL_CALENDAR_PILOT.md).

Unsubmitted reimbursement checklists are a separate default-off pilot: see
[M2.6 setup and acceptance](MCP_TRAVEL_DRAFT_PILOT.md).

Own task acknowledgement is a separate default-off M3 pilot using canonical API
receipts: see [setup and acceptance](MCP_TASK_ACKNOWLEDGEMENT_PILOT.md).

Own task submission for review is a separate default-off M3 pilot using canonical
API receipts: see [setup and acceptance](MCP_TASK_SUBMISSION_PILOT.md).

Own supply request submission is a separate default-off M3 pilot: see
[setup and acceptance](MCP_SUPPLY_SUBMISSION_PILOT.md).

Own travel papers review requests are a separate default-off M3 pilot with durable
notification status: see [setup and acceptance](MCP_TRAVEL_REVIEW_PILOT.md).

Recording an owner-attested travel paper handover is a separate default-off M3
pilot: see [setup and acceptance](MCP_TRAVEL_SUBMISSION_PILOT.md).

A linked room request is a separate default-off M3 pilot with pending/no-booking
semantics: see [setup and acceptance](MCP_ROOM_REQUEST_PILOT.md).

The default-off M3.7 standalone meal submission contract and hosted acceptance
steps are in [the meal request runbook](MCP_MEAL_REQUEST_PILOT.md).

The default-off M3.8 work-arrangement filing contract and hosted acceptance
steps are in [the work-arrangement runbook](MCP_WORK_ARRANGEMENT_PILOT.md).

The default-off M3.9 activity date-update contract and hosted acceptance steps
are in [the activity date runbook](MCP_ACTIVITY_DATE_PILOT.md).

The default-off M2.7 private activity draft foundation and hosted acceptance
steps are in [the activity draft runbook](MCP_ACTIVITY_DRAFT_PILOT.md).

The default-off M3.10 live creation from an own private activity draft is covered
in [the activity creation runbook](MCP_ACTIVITY_CREATION_PILOT.md).


The separate default-off first pinned-update publication pilot is documented in
[M3.11 setup and acceptance](MCP_ACTIVITY_ANNOUNCEMENT_PILOT.md). It publishes on
registered-participant pages only after browser confirmation, without emailing
registrants or dispatching an official invitation.


The separate default-off confirmed-lead task acceptance decision is documented in
[M4.1 setup and named pilot acceptance](MCP_TASK_ACCEPTANCE_PILOT.md). It requires
exact browser review and separation from the owner/actual submitter, with a
recorded hosted go/no-go before any staff decision pilot.


The separate default-off scoped full supply approval decision is documented in
[M4.2 setup and named pilot acceptance](MCP_SUPPLY_APPROVAL_PILOT.md). It requires
exact browser review of initial reservations/shortage, preserves stock on-hand,
and needs a recorded hosted go/no-go before any staff decision pilot.
