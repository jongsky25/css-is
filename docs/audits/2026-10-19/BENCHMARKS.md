# Current peer-platform benchmarks

Official documentation was reviewed on **19 October 2026**. These are feature, architecture and workflow comparisons with systems that overlap parts of Office Connect. They are not hands-on product trials, security certifications, price quotes or comparative throughput measurements. No single peer covers all of the local survey, personnel, room, travel and document rules.

“Better” is assessed against a particular outcome: clearer task completion, more dependable authorization/recovery, a documented integration boundary, or predictable execution at growing load. The documentation supports adopting the patterns below; it does not establish that replacing the whole application would improve every outcome.

## Comparison and recommended response

| Reference | Relevant documented pattern | Office Connect at reviewed revision | Incremental response |
|---|---|---|---|
| **OpenProject** — workflow and collaboration | Work-package views/table configuration; documented API, OAuth applications, webhooks and MCP integration [O1–O5] | Documents/Work already have assignments, version-aware approvals, permissions and personal work views. The general browser route schema lacks typed contracts/security declarations, and list permissions produce growing query counts. | Retain local workflow rules; adopt bounded saved views, clearer task/status navigation, scoped API access and a thin MCP boundary. Phases 2, 4–5. |
| **Frappe / ERPNext ecosystem** — Python business platform | Document/resource APIs, token/OAuth access, background jobs and migration practices [F1–F3] | Python business modules and domain helpers exist, but browser parsing, shared authority resolution, job execution and schema/runbook evolution are uneven. | Adopt common domain service contracts, durable job conventions and explicit migration/release discipline. Use the framework as a design reference; changing frameworks is not required. Phases 1–4. |
| **Microsoft 365 / SharePoint / Power Automate** — documents and approvals | SharePoint document-approval flows, approval actions/responses and sequential approvals [M1–M3] | Local exact-version approvals and document receipts are valuable. Users still need clear pending/approved/delivered states and reliable external status reconciliation. | Preserve local approval semantics; make decision/status history visible and expose an adapter for an actual Microsoft 365 workflow if the organization uses it. Phases 2–4. |
| **Google Workspace Calendar** — rooms and scheduling | Availability-based room booking and appointment scheduling [G1–G2] | Room rules, recurring reservations, approval flows, multiple calendar views and ICS already exist. Feed privacy, predictable retry/status behavior and user task completion need verification/improvement. | Benchmark find-a-slot → reserve → change/cancel → confirm availability as one journey. Preserve local approval/meal rules and define one source of truth for each synchronized field. Phases 1, 3–4. |
| **LimeSurvey** — survey automation | RemoteControl APIs for survey/participant operations and response export [L1–L3] | Public survey tokens, offline submission IDs, localized forms and local reporting calculations already exist. Null/NaN robustness and survey controls have confirmed defects; integration contracts are thin. | Retain specialized reporting calculations while improving data-quality behavior, touch interaction and a supported export/automation boundary. Consider replacement only if a concrete survey capability gap remains. Phases 1, 3–4. |
| **n8n** — non-AI integration orchestration | Queue mode separates trigger handling and workers using Redis and a persistent database [N1] | Workspace relays and some persistent operation records exist; synchronous request work and fragmented scheduling remain. | Adopt the intent/job/receipt/reconciliation pattern; evaluate n8n as an external adapter when connector demand warrants it. Redis or n8n is not a prerequisite for fixing blocking calls. Phases 2, 4, 6. |
| **Official Full Stack FastAPI Template** — related stack reference | FastAPI, typed database models, PostgreSQL, frontend/test tooling and CI conventions [T1] | FastAPI/Jinja/SQLite is a valid smaller deployment shape. The local suite is substantial but not green or required by deployment; dependencies and generated contracts need improvement. | Adopt reproducible builds, typed service boundaries and required tests. Retain Jinja unless measured user requirements justify a different frontend. Evaluate PostgreSQL only after corrected-system load/recovery measurements. Phases 1, 4, 6. |

Feature availability, hosting model, identity requirements and licensing/edition restrictions must be confirmed before procurement or adoption. Current documentation is evidence of the referenced pattern, not a promise that every edition includes it.

## Benchmarks against the five goals

| Goal | Current evidence | Comparison standard | Measure for the improvement program |
|---|---|---|---|
| Current platforms | Useful local workflows coexist with weaker shared boundaries and contracts | Peer task flows and documented interfaces above | Complete identical business scenarios and compare task success, steps/errors, operational recovery and total cost |
| Security | F01/F03 authority/session defects; F04–F08 boundary/configuration/privacy/dependency gaps | Current OWASP session/password/LLM guidance plus explicit local threat model | No privilege gain through profile fields; revocation works; required negative tests pass; artifact vulnerabilities and recovery evidence reviewed |
| User friendliness | Responsive sampled pages; concrete accessibility failures; task success/time not yet measured | Clear task/status patterns from workflow and calendar peers; WCAG 2.2 AA | Completion, time, assistance, wrong actions, accessible controls and error recovery on agreed journeys |
| AI and non-AI integration | ICS/exports/Workspace relays exist; generic OpenAPI contracts are incomplete; model grounding is self-asserted in an optional mode | Scoped APIs, reliable events, source-backed AI and MCP authorization practices | Independent client success, narrow/revocable permissions, safe replay, source accuracy, abstention and cost/latency |
| Performance | Fast small local responses but avoidable SQL growth and event-loop blocking | Bounded pagination, background jobs, measured capacity/recovery | p95/p99 under representative concurrency, SQL growth, loop lag, queue age, memory, snapshot lag and restore time |

## Repeatable hands-on comparison protocol

Use the same synthetic organization, role matrix and task records in Office Connect and any selected peer trial. Record product version, edition, configuration, hosting region and client/network conditions. Configure the minimum legitimate equivalent workflow; do not compare a configured application to an empty installation.

1. **Document/work:** find a restricted record, assign work, submit a revision, approve the exact version, release it, revoke access and verify old sessions/links. Measure time, steps, mistakes, permission outcomes and audit trace.
2. **Calendar/rooms:** find an available room, book a recurring series with a conflict, adjust one occurrence, approve/cancel, subscribe and reconcile a delayed change. Measure recovery clarity and synchronization correctness.
3. **Survey/report:** complete mobile bilingual/sparse input, retry a submission after connection loss, filter by organizational scope/date, and export a report with independently known totals. Measure accessibility, duplicate prevention and statistical consistency.
4. **Integration:** use a scoped external credential to read/update permitted work; revoke it; replay an event; drop a response after commit. Measure contract completeness, duplicate effects, delivery lag and operator recovery.
5. **AI:** ask a question with known authorized facts, one with missing facts and one with adversarial content in a retrieved document. Change permissions between requests. Measure factual accuracy, source traceability, abstention, access boundaries, latency and cost.
6. **Operations:** restart during a write/job, fail a dependency, restore a backup and compare business totals. Measure recovery point/time and data integrity. Benchmark load only on authorized isolated environments with equivalent resources and representative record counts.

Start with staff priorities and at most two or three relevant peer trials. Keep separate results for security, usability, operational reliability, integration effort and cost; a weighted overall score is useful only after the owner chooses the weights. Include migration, training, identity, backups, support, data residency and ongoing connector maintenance in total cost. Do not select a platform solely from a feature checklist.

## Primary sources

### OpenProject

- **O1:** [API documentation](https://www.openproject.org/docs/api/).
- **O2:** [API and webhooks administration](https://www.openproject.org/docs/system-admin-guide/api-and-webhooks/).
- **O3:** [OAuth applications](https://www.openproject.org/docs/system-admin-guide/authentication/oauth-applications/).
- **O4:** [MCP server integration](https://www.openproject.org/docs/system-admin-guide/integrations/mcp-server/).
- **O5:** [Work-package views](https://www.openproject.org/docs/user-guide/work-packages/work-package-views/) and [table configuration](https://www.openproject.org/docs/user-guide/work-packages/work-package-table-configuration/).

### Python business-platform and stack references

- **F1:** [Frappe API](https://docs.frappe.io/framework/user/en/api).
- **F2:** [Frappe background jobs](https://docs.frappe.io/framework/user/en/api/background_jobs).
- **F3:** [Frappe database migrations](https://docs.frappe.io/framework/user/en/database-migrations).
- **T1:** [Official Full Stack FastAPI Template](https://github.com/fastapi/full-stack-fastapi-template/blob/master/README.md).

### Microsoft and Google workflow references

- **M1:** [Require document approval using Power Automate](https://learn.microsoft.com/en-us/sharepoint/dev/business-apps/power-automate/guidance/require-doc-approval).
- **M2:** [Modern approvals](https://learn.microsoft.com/en-us/power-automate/modern-approvals?tabs=new-designer).
- **M3:** [Sequential approvals](https://learn.microsoft.com/en-us/power-automate/sequential-modern-approvals).
- **G1:** [Add a room to a Google Calendar event](https://support.google.com/calendar/answer/143753?hl=en).
- **G2:** [Google Calendar appointment schedules](https://support.google.com/calendar/answer/10729749?hl=en).

### Survey and integration references

- **L1:** [LimeSurvey RemoteControl 2 API](https://www.limesurvey.org/manual/RemoteControl_2_API).
- **L2:** [LimeSurvey RemoteControl](https://www.limesurvey.org/manual/RemoteControl).
- **L3:** [RemoteControl handler reference](https://api.limesurvey.org/classes/remotecontrol-handle.html).
- **N1:** [n8n queue mode](https://docs.n8n.io/hosting/scaling/queue-mode/).

### Security and authorization references

- [OWASP Session Management Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Session_Management_Cheat_Sheet.html).
- [OWASP Password Storage Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/Password_Storage_Cheat_Sheet.html).
- [OWASP LLM Prompt Injection Prevention Cheat Sheet](https://cheatsheetseries.owasp.org/cheatsheets/LLM_Prompt_Injection_Prevention_Cheat_Sheet.html).
- [MCP authorization specification, version 2025-11-25](https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2025-11-25/basic/authorization.mdx) — pin the version implemented by the selected client/server and check changes before delivery.
- [SQLite `PRAGMA data_version` semantics](https://www.sqlite.org/pragma.html#pragma_data_version).

These sources complement direct code/tests. They do not establish production security, compliance, accessibility certification or superior vendor performance.
