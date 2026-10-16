# P2.3 — Blockers and dependencies

October 16, 2026. **Accepted**, version **6.62**, branch `codex/work-blockers`. P2.2 was merged at `4a44fc0` before this increment. P2.3 was subsequently merged at `d44d868` as release **6.64**, preserving newer Google Meet changes through 6.63 on main. The originally prepared version was 6.62. Live deployment success has not been independently verified.

Phase 2 acceptance was recorded when the user authorized P3.1 after the [technical acceptance review](WORK_MANAGEMENT_PHASE_2_ACCEPTANCE.md). Historical verification notes below remain unchanged.

## Delivered

- Record or update a contribution blocker with a reason, an eligible follow-up owner and a date. Resolve it with an explanation. Blockers remain separate from the existing contribution lifecycle.
- The contribution owner, follow-up owner, lead or authorized officer can maintain a blocker. Contributors can take responsibility themselves or retain the existing follow-up owner; leads/officers can assign another person who already has access. A follow-up assignment never creates work membership or source access.
- Add/remove prerequisite contributions by name within the same work item. The lead or an authorized officer manages these links with a reason. Self-links, duplicate links, cross-item links and cycles are rejected. Opposing concurrent writes serialize before cycle validation.
- Unresolved blockers and prerequisites prevent submission and acceptance. Preparation can still start. An accepted prerequisite satisfies its direct dependency; cancellation does not, so a coordinator must explicitly remove a withdrawn requirement. Reopening a prerequisite blocks future downstream submission/acceptance. Already accepted downstream work retains its history and displays a review warning; no prior formal decision is silently invalidated.
- Contribution cards show the blocker, follow-up person/date, prerequisite status and targets, and whether follow-up access has been lost. My work includes follow-up responsibilities and explains waiting prerequisites. Follow-up dates are planning dates, not scheduled email alerts.
- Updates use the task revision and immutable work history. The history names prerequisite contributions, follow-up owners and dates, and retains resolved blocker reasons. Official document deadlines, contribution targets, case revisions, document approvals and dispatch settings are unchanged by blocker/dependency writes.

## Authority and persistence

All writes refresh the actor, check complete work/source visibility, enforce the existing enabled/open-work gates, validate the target revision and commit changes with audit history atomically. A failed audit rolls back task and graph changes. Inactive or revoked follow-up owners cannot act; the lead/officer can choose a currently eligible replacement.

Additive blocker columns on `work_task` and a `work_dependency` table/index retain existing tasks. Repeat installation preserves both. Compatibility writes continue through the shared task service, including the new submission/acceptance gates. `work_blockers.py` is included in the explicit deployment module allowlist. Version/changelog bumped to 6.62.

## Verification

**150 passed** across shared work, Documents, setup, routes, Workspace operations and notifications. Only the existing Starlette/httpx deprecation warning. New coverage includes blocker creation/resolution, follow-up authority and My work, unchanged document and case state, stale writes, revoked/disabled access, same-item graph boundaries, cycles including concurrent opposing links, accepted/cancelled/reopened prerequisites, audit rollback, repeated schema installation, HTTP CSRF and escaped blocker content. Existing deployment dependency and compatibility tests also pass.

Chromium journey: coordinator sets a prerequisite and gets a visible cycle rejection; dependent contributor can prepare but cannot submit; upstream owner records and resolves a blocker and sees the follow-up in My work; upstream acceptance unlocks downstream submission. Desktop 1440px and mobile 390px passed without horizontal overflow or browser errors. Local screenshots and runner: `/workspace/scratch/work-p23`. Test report: `/tmp/work-p23-tests.xml`.

## Next

Review and merge P2.3, then P2.4 — turn discussion into proposed tasks and record authorized decisions with source links. Phase 2 acceptance and live deployment success remain separate checks.
