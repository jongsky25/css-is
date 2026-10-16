# P1.2 — Contribution task lifecycle

October 16, 2026. Status: **In review**. Implementation owner: Codex. Branch: `codex/contribution-lifecycle`. Prepared version: **6.51**. P1.1 was first merged into main at `e4c5da2` as requested; P1.2 has not been merged or deployed. Staff acceptance remains open.

## Implemented

A shared work item now contains named contributions with expected outputs, a contributing unit, a suggested/confirmed responsible person, an internal target, and submitted evidence text. Forms show people and task names; users do not enter database IDs.

The lifecycle is **Proposed → To do → In progress → For review → Done**. The contributing unit's officer confirms an assignment. The responsible person acknowledges/starts and submits. The shared work lead or work item's concerned officer returns or accepts the contribution. Return requires a reason and preserves prior submissions. A coordinator may reopen accepted work with a reason. A contributing unit officer may reassign unfinished work or cancel it, also with a reason. Reassignment resets it to To do and retains the earlier evidence.

Officers can start/submit for their contributing unit, recording the actual officer as actor and requiring a note. Self-acceptance is permitted only when the owner independently holds lead or concerned-officer authority; ordinary ownership never confers acceptance authority. No configurable separation-of-duties policy exists for these tasks yet, and no document approval rule is altered.

Each task has its own revision. Progress on one contribution does not invalidate a different contribution's form or change the work item revision. Stale updates to the same task return a conflict. Required notes, submissions, active owners, and target dates are validated. Errors preserve typed submission text. All mutations and immutable history events commit together or roll back together.

## Visibility and authority

Confirmed task owners join the shared work audience; proposed owners do not. Officers scoped to a contributing unit can read the work item to confirm/manage that unit's tasks. Every reader must still have current access to **every** linked document. This expands P1.1's audience deliberately to support contributors and cross-unit confirmation without granting document permissions.

Reassignment removes the old owner's task-based access unless another role or confirmed contribution still grants it. Cancellation removes that contribution's ownership-based access, while scoped officers retain history access. Revoked document access hides the work item and its reverse links.

Linking documents remains limited to the creator, confirmed lead, or work item's concerned officer. All assigned contributors must already be permitted to read a newly linked document. Internal targets cannot exceed a linked official deadline at proposal/confirmation or when adding another document. Later official deadline changes are still governed by Documents; they do not silently rewrite task dates.

Contribution acceptance never signs, releases, closes, or approves correspondence. Existing document numbers and assignments are unchanged. The legacy Documents acceptance predicate is corrected so a confirmed document lead may complete another person's contribution; it still does not let that lead submit someone else's work without officer authority. Legacy state semantics and migration remain for P1.3.

## Verification

- **74 tests passed** across `tests/test_work.py`, `tests/test_documents.py`, `tests/test_documents_routes.py`, `tests/test_documents_workspace.py`, and `tests/test_documents_setup.py`.
- New coverage includes independent contributors, return/resubmission evidence, lead acceptance, invalid jumps, scoped cross-unit confirmation, proposal access, reassignment/cancellation, source access revocation, deadline validation, stale revisions, inactive owners, audit rollback, CSRF, escaped submissions, disabled writes, and legacy lead acceptance.
- Actual Chromium/Playwright workflow: create shared work, confirm lead, propose two contributions, confirm both owners, start/submit the first, return it, resubmit, and accept. The second contribution remains To do throughout. History contains the return reason and both submission versions.
- Desktop and 390px mobile views checked; no horizontal overflow or browser script errors. Task anchors account for the fixed navigation bar.
- Existing Starlette/httpx deprecation warning remains. `git diff --check` passes.

Workspace-only evidence: `/tmp/work-p12-tests.xml` and `/workspace/scratch/work-p12/` (synthetic database, browser checker, desktop/mobile screenshots). No live mail, Drive, signature, or production data was used.

## Setup, recovery, and next increment

Normal initialization additively creates `work_task`; it preserves P1.1 work and settings. Both `documents.enabled=1` and `work.enabled=1` remain necessary for writes. No operational switches were enabled. Use the disposable evaluation setup described in [P1.1](WORK_MANAGEMENT_P1_1.md).

Disable `work.enabled` to stop work writes while preserving authorized reads and history. Keep the new tables. Do not downgrade to a pre-P1.2 application for ordinary operation: it does not include contribution membership and linking checks. No legacy assignments were migrated or dual-written.

This increment includes text evidence and current task ownership. It does not include file upload/versioning, discussions, dependencies/blockers, notifications, task metadata editing, a personal task inbox, or operational migration. Large work items still render their task/history collections together; pagination and the fuller interface remain follow-up work. Staff walkthroughs and live readiness checks remain outstanding.

Next: **P1.3 — Assignment compatibility and migration rehearsal**. Map legacy contributor IDs idempotently on a database copy, reconcile owners/states/mandatory contributions, preserve prior evidence, and route both entry points through one task service before cutover. Do not infer groups or auto-migrate operational data.
