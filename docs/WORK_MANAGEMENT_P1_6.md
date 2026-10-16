# P1.6 — Contextual work item interface

October 16, 2026. **In review**; implementation owner Codex. Branch `codex/contextual-work`; prepared version **6.58**. P1.5 was already merged at `7249534`. P1.6 is not merged or deployed. Staff acceptance remains open.

## Work item context

The work item starts with counts for proposed, preparing, submitted, accepted, and cancelled contributions. It names each required contribution still outstanding and links directly to it. These are task counts, not a completion percentage or a claim that correspondence is approved for release.

“Your next actions” highlights available confirmation, own start/submit, or contribution review actions. Each task also describes its next step or what it is waiting for. Accept and return are both visible for review; reassignment, cancellation, milestone changes, reopening, and officer intervention are grouped as other authorized actions. This changes presentation, not the authority to perform those actions.

A returned contribution displays its correction reason beside the expected output and latest submission. Adjusting its target does not erase that reason. Resubmission replaces the active correction prompt while retaining the earlier decision and output in history. Other contributions keep their independent state and revision.

The screen suppresses controls that cannot currently work because the mapped document is closed/cancelled or has an uncertain external operation. Inactive owners or owners lacking source access receive an explanatory message; permitted reassignment/cancellation controls remain available. Existing disabled-module behavior remains read-only.

## Named people and task history

People selectors display staff names with account identifiers for disambiguation; accounts without a directory name retain their username fallback. Existing inactive people remain identifiable in permitted history without becoming selectable as new active owners.

Every contribution has its own expandable history. The shared timeline links events back to their task and shows actor, local date/time, status, owner at the recorded step, and decision note. Submitted evidence is shown at submission events rather than repeated at each later state change. Original data and immutable history are unchanged.

## Existing document assignments

Unmigrated documents display named assignment cards with person, role, status, internal target, and evidence. Available progress and target forms sit inside the relevant assignment card. Assignment IDs are hidden form values, never values the user must find and type. Replacement assignment selection shows its description, owner, and state.

Owners/officers receive the existing permitted progress choices; leads/officers receive completion and milestone controls under the existing predicates. Completed/superseded assignments and closed/cancelled records have no contribution-update controls. The backend still checks document revision and authority, including forged form requests. Migrated assignments continue linking to the shared task service; no alternate task store or migration is introduced.

Document person selectors and timeline actor labels use names. This increment targets contribution and ownership interaction; unrelated technical fields for file versions, duplicate merges, and administrator visibility configuration retain their existing interfaces.

## Verification

**101 tests passed** across work, Documents service/HTTP, Workspace, and setup suites, including deployment-module coverage. New checks cover:

- Two contributing units with independent owners/states; return, milestone adjustment, resubmission, acceptance, and remaining required work.
- Task-specific next steps, preserved submission history, and permitted reviewer choices.
- Named legacy assignment forms, hidden identity values, scoped progress options, stale document revisions, and named replacement selection.
- Inactive owner and closed-document controls matching service prerequisites.

An actual Chromium/Playwright walkthrough used two fictional divisions and four staff accounts. The officer confirmed both owners; each contributor started their own task; the lead returned one contribution; its owner resubmitted; the lead accepted it while the other division remained in progress. Forms were opened using keyboard focus/Enter, with no typed database IDs. The task history showed named authors and retained return evidence. Desktop and 390px mobile layouts passed without horizontal overflow or browser script errors.

Evidence: `/tmp/work-p16-tests.xml` and `/workspace/scratch/work-p16/` (synthetic setup/database, browser checker, desktop/mobile screenshots). Existing Starlette/httpx deprecation warning remains. `git diff --check` passed. No live integrations or operational records were used.

## Rollout and remaining gates

No new schema, write authority, or feature switch is introduced. Existing module flags and all task/document mutation checks remain authoritative. Templates are included by the existing deployment allowlist; no runtime module is added. Presentation rollback to P1.5 preserves all work, assignments, and history.

Automated checks do not establish staff usability acceptance or live deployment success. A push to main triggers the configured deployment workflow; this increment remains on its development branch pending merge.

Next: **P1.7 — Guided administrator readiness**: role, policy, holiday, and integration checks with precise next setup actions, without inventing signing authority or enabling dispatch inadvertently.
