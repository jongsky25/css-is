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

If the consent step does not return to ChatGPT, check **My profile → Connected tools → ChatGPT connections**. If no active connection appears, the grant did not complete. The consent response displays an HTML error and a retry link where appropriate; it should not download a file named `mcp-consent`. Repeat the connection on ChatGPT web and capture the visible error. The default consent covers all six read areas listed above; a client that explicitly requests fewer scopes receives only those scopes.
