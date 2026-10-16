# P1.4 — My work and home integration

> **Subsequent status, October 16, 2026:** The user explicitly accepted Phase 1 and authorized P2.1. Earlier review notes below are retained as implementation evidence; live integration verification remains a separate rollout requirement.
October 16, 2026. Status **In review**. Implementation owner: Codex. Branch `codex/my-work-home`; prepared version **6.53**. P1.3 was merged first at `027d76b` as requested. P1.4 was subsequently merged on the user’s instruction at `53f1fb462b2e9255b6c097d223824e40f58fd258`, rebased in release numbering to **6.55** to preserve the newer main releases 6.53/6.54. Packaging correction `ff100fe` released **6.56** to include `work_inbox.py`. Deployment and staff acceptance are not recorded.

## Personal responsibilities

Office → **My work** opens `/work/mine`. It has two views:

- **Needs my action:** confirmed personal contributions needing acknowledgement or output; proposals requiring the contributing unit's officer to confirm an owner; work items needing a concerned officer to confirm their lead; and submitted contributions awaiting the confirmed lead's review.
- **Waiting for review:** the current owner's submitted contributions while another person is responsible for reviewing them.

Cards show the contribution, related work item/document, next action, internal target, and overdue/due-today/upcoming indicator. Their links open the existing task actions. Targets do not extend official document deadlines. The selected view is marked visually and for assistive technology.

General officer visibility does not put everyone's assigned tasks in an officer's personal list. Officers see pending confirmation decisions within their scope. A confirmed active lead who can access the work item owns its review queue; the concerned officer is the fallback when no such lead is available. This chooses the personal queue recipient without removing the officer's existing intervention authority. Proposed owners do not get personal obligations solely from a suggestion.

Returned work reappears for its owner. Reassignment moves the responsibility to the new owner. Completed/cancelled contributions disappear from both personal views. Closed/cancelled imported documents and running/uncertain signing/dispatch operations do not produce actionable contribution cards.

## Home, notifications, and approvals

The home to-do strip shows up to three named current personal tasks with direct links, next steps, and internal dates. When the bounded scan has more pages, a My work link lets the user continue; this is not a claim of an exact remaining count. Waiting contributions remain available in the waiting view rather than becoming home action cards.

Formal document reviews remain in the existing Approvals inbox and are included in its existing home summary alongside wellness/work-arrangement approvals. They are not duplicated as contribution cards. Document notification rows use the same personal provider plus the formal-review inbox, replacing the broad “documents need attention” count. Contribution acceptance and formal document approval remain distinct decisions.

Unmigrated legacy contributor assignments appear as document-linked entries. Migrated assignments appear once, using their shared task identity. Legacy lead rows are not fabricated as contribution tasks. Existing formal approvals, document authority, and source visibility checks are retained.

## Visibility, pagination, and feature switches

Current active-account status, source visibility, ownership, and scoped authority are checked at read time. The shared case audience remains the intersection with every linked document. Revoked users cannot retain task titles through My work, home, or the notification list.

Pages use creation time and a stable source-specific numeric cursor, newest first. A bounded scan examines at most 250 candidates and returns at most 25 permitted responsibilities. It returns a continuation when that scan is exhausted, even if the page is empty. The cursor's creation timestamp is resolved internally; hidden titles, dates, and totals are not placed in pagination links. A task completing or being reassigned between requests does not invalidate its pagination boundary. Newly created work is available from Back to newest. Ordering is by creation, not a global urgency ranking.

Read-only personal lists remain available when writes are disabled, and cards explain that changes are disabled. Home/action notifications omit disabled task actions. No feature switch or operational setting is enabled by this increment. Existing Shared work, task, and document destinations remain available through the work navigation.

## Verification

**95 tests passed**: work service/HTTP, Documents service/HTTP, Workspace/setup, navigation/search-index alignment, and existing home wellness/approval checks. New scenarios cover:

- Proposal versus confirmed ownership, owner start/submit, waiting, lead review, return, and completion.
- No broad officer assignments; fallback review after lead deactivation; fresh officer scope after a grant change.
- Reassignment, restricted-source revocation, disabled writes, and permission-safe home/HTTP output.
- Legacy-to-shared migration deduplication and completed-task removal.
- Pagination across changing tasks and more than 250 unrelated hidden decision candidates.
- Formal document approval appearing once in the home approvals summary, separate from contribution tasks.

Actual Chromium/Playwright workflow passed: home task → contribution, personal next step/date, submission → waiting view, lead review without officer duplication, acceptance → removal from both personal lists and home. Desktop and 390px mobile captures were visually checked; no horizontal overflow or browser script errors occurred.

Local evidence: `/tmp/work-p14-tests.xml` and `/workspace/scratch/work-p14/` (fictional database, browser script, desktop/mobile captures). Existing Starlette/httpx deprecation warning remains. `git diff --check` passed. No live integrations or operational records were used.

## Recovery and next increment

No schema migration or new operational switches are introduced. Existing flags can pause writes without deleting work; keep P1.3 mappings and task data intact. A code rollback to the P1.3 version removes these presentation changes while retaining the contribution/migration protections. Do not roll back beyond those data compatibility protections after operational cutover.

Staff usability acceptance, operational activation, global due-date prioritization, and notification expansion remain outside this increment. Read-time pages reflect current state; they do not add background push notifications or automatically migrate old records.

Next: **P1.5 — Simplified intake and curated scenarios**: new/existing work selection, reference-only intake, and reviewed extraction suggestions while preserving manual entry and existing registration numbering rules.
