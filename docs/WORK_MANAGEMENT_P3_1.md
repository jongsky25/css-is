# P3.1 — Shared team views

October 16, 2026 (Asia/Manila). **In review**, version **6.70**, branch `codex/team-views`. The user authorized this increment after the Phase 2 technical acceptance recommendation; Phase 2 is recorded as accepted. This increment is not merged or deployed.

## Delivered

- Team contributions is available from shared-work navigation at `/work/team`. List and board show the same canonical contributions across work items the viewer can currently access.
- Filters cover contribution/work-item title, contributing unit, owner (including assigned to me and unassigned), status, blockers/prerequisites/changed decisions, overdue internal targets and missing targets. Active contributions are the default; done and cancelled remain available through status filters.
- Cards identify the parent work item, confirmed owner, contributing unit, internal target, required status, blockers, dependencies and pending decision reviews. Expected output and submitted evidence are available before accepting a contribution; detail/history remains one link away.
- Both views reuse task action forms and the existing task mutation service. Required notes, output evidence, confirmation authority, review authority, target rules, revision checks and history apply identically. Changes appear in My work and detail pages on their next request.
- Filter selections survive view changes, pagination and successful updates. A successful update explains that a contribution may leave the selected filter. Invalid/stale forms retain their text and display the latest affected contribution separately, even if it no longer matches the current page.
- Native links, details, selects and forms provide keyboard operation without drag gestures or JavaScript. Board columns stack on narrow screens; state changes require the same explicit action forms as the list.

## Permissions and integrity

Current active-account and complete linked-document visibility checks happen before rendering task metadata, counts, blockers or decisions. Team membership and official document access are not granted by filters or board actions. Technical administrators have no content bypass.

Every POST checks session-bound CSRF and delegates to `work_tasks.mutate`, which reloads permissions, task state and revision inside the transaction. Cross-case task references, revoked users and unauthorized transitions are rejected. Blockers/dependencies/changed decisions prevent premature submission or acceptance. Disabled work and closed/locked migrated sources remain readable to authorized users with actions unavailable. Inactive or restricted owners surface a warning and hide actions that cannot succeed.

No new schema or duplicate task store is introduced. `work_team.py` is included in the deployment module allowlist. Formal document decisions, deadlines, approvals, signing and dispatch remain in Documents.

## Pagination and scope

Pages show at most 25 contributions, newest first, using stable task-ID boundaries. Each request scans at most 250 matching candidates, then applies complete visibility and attention checks. A page can contain fewer or no visible contributions while offering continuation; older permitted work remains reachable. Counts are explicitly page counts, not team totals. Filter options use the existing staff/unit directory and do not expose restricted work titles or counts.

Unit selection matches the contributing unit exactly. Views are refreshed by requests, without live push updates. Saved views, drag-and-drop, digests and management-wide metrics are outside this increment. This does not certify live integrations or operational rollout.

## Verification

**254 passed**, zero failures/errors/skips, across shared work, Documents, setup, routes, Workspace operations, notifications, Meet, short links and travel pages. Only the existing Starlette/httpx deprecation warning remains. Report: `/tmp/work-p31-tests.xml`.

New checks cover filters, visibility, terminal states, overdue targets, dependencies/decisions, bounded pagination beyond hidden records, read-only behavior, inactive owners, revoked access, invalid filter values, HTML escaping, CSRF, stale forms, retained input, cross-case actions, denied self-acceptance, and consistency across list/board/My work/detail. Existing deployment packaging checks cover the new module.

Chromium journey uses two contributors and a reviewer: filter assigned work, switch to board by keyboard, start by keyboard, submit from list, see My work's review wait, verify a peer cannot accept, inspect evidence and accept from the reviewer board, then verify Done in board/detail and removal from the owner's action inbox. Desktop 1440px and mobile 390px passed without horizontal overflow or browser errors; screenshots were visually reviewed. Local artifacts: `/workspace/scratch/work-p31`. The initial browser run stopped on an ambiguous test locator; a specific summary locator corrected the runner, and the full journey passed with a fresh synthetic database.

## Next

Review and merge P3.1. P3.2 introduces consolidation and review inbox integration, including identified outgoing versions and retained review feedback. Live whole-workflow and operational acceptance remain Phase 4 gates.
