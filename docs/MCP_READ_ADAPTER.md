# Office Connect read connection for ChatGPT (A24)

This optional MCP endpoint lets an authorized Office Connect user ask ChatGPT about their current shared work, document status, calendar events, room bookings, supply queues, personal travel filings and permitted activity progress. ChatGPT can receive only records the connected user can see at the time of each request. It cannot approve, edit, submit, download files, or read document bodies and private task submissions through this connection.

## Supported questions

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

The previous `/api/v1` bearer integration keys cannot connect ChatGPT's custom MCP client. This adapter uses delegated OAuth grants with PKCE, a fixed resource audience, short lived access tokens, rotating refresh tokens, and an explicit user consent step. It accepts only ChatGPT callback URLs at client registration. Each tool checks the current account, grant, scope, and object permissions. Account security changes and historical restore revoke grants. The interface is read only and each successful read records an audit event without copying a search term or record title into the audit summary.

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

List requests are paged at 25 items or fewer. Calendar reads cover at most 31 days per request and use the calendar's current viewer and audience rules. Approved room bookings are shared office information; pending requests are visible only to the requester and room approvers. Linked bookings follow the calendar's existing duplicate folding, so their event may carry the room venue instead of appearing twice. Attendee names, meeting URLs, leave and birthdays are excluded. Supply queues use the same role and unit checks as the Supply dashboard; warning quantities require a current custodian or auditor grant. Travel reads are owner-only and use stored deadlines, which may be stale until the filing is reopened in Office Connect. Activity progress uses the same management scope as the Monitor and excludes individual registration and response data. Connected reads use the integration read rate limit. Public OAuth requests have a separate rate limit and bounded request size. Consent attempts use the integration issuance rate limit. Access tokens last one hour; refresh grants last up to 30 days and rotate on use. No MCP write tools or file content tools are published.

## Verification and rollout boundary

The automated synthetic journey covers OAuth discovery, client registration, consent, PKCE exchange, MCP initialization, permitted and hidden records, permission withdrawal, refresh rotation, and disconnect. It does not prove that a particular ChatGPT workspace can add the connector or that the production host exposes the endpoint correctly. After deployment, use a supported ChatGPT workspace and a low privilege test account to complete one real connection and compare the returned records with Office Connect. Keep the feature flag off or disconnect the test connection if that check fails.

If the consent step does not return to ChatGPT, check **My profile → Connected tools → ChatGPT connections**. If no active connection appears, the grant did not complete. The consent response displays an HTML error and a retry link where appropriate; it should not download a file named `mcp-consent`. Repeat the connection on ChatGPT web and capture the visible error. The default consent covers all eleven read areas listed above; a client that explicitly requests fewer scopes receives only those scopes unless the person explicitly selects additional read permissions on the consent page. Optional permissions are unchecked and bounded by the client registration; existing grants are never widened.


If consent lists only work access, select needed areas under **Optional additional read access** before confirming. All registered ChatGPT clients, including legacy work-only registrations, can select from the server's eleven supported read areas. Registration eligibility does not grant data access: optional scopes stay unchecked, the token contains only requested and explicitly selected permissions, and existing grants and their refresh tokens remain unchanged. After this fix is deployed, start a fresh authorization flow; deleting and recreating the app is not required to see the additional choices.

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

Bound current metadata inventory to 2,000 active non-pooled Type 2/3 forms before loading/grouping. This is a global inventory cap, so even a narrow quarter can receive a capacity refusal. Detail caps are 500 active Type 2 member forms, 5,000 responses and 100,000 answer rows. Refuse over-cap results without splitting groups or publishing partial scores. Read audits omit search terms and titles; neither tool writes business state.

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
