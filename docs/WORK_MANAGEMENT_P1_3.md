# P1.3 — Assignment compatibility and migration rehearsal

> **Subsequent status, October 16, 2026:** The user explicitly accepted Phase 1 and authorized P2.1. Earlier review notes below are retained as implementation evidence; live integration verification remains a separate rollout requirement.
October 16, 2026. **In review**, implementation owner Codex. Branch `codex/assignment-compatibility`; prepared version **6.52**. P1.2 was merged first at `aeba93e` as requested. P1.3 was subsequently merged into main on the user’s instruction at `027d76bc5fa183cf051f7b50eb892957d88d42c9`. Operational deployment and migration are not recorded.

## Explicit mapping and retained history

`work_compat.migrate` requires the current concerned officer, document revision, expected outcome, and migration reason. Each explicitly selected active document gets its own new work item. The service does not infer grouping from matching subjects or attach assignments to an existing case.

| Legacy state | Initial shared task state |
|---|---|
| proposed | Proposed; suggested owner only |
| assigned | To do |
| acknowledged | In progress |
| in_progress | In progress |
| submitted | For review |
| completed | Done |
| superseded | Cancelled |

Contributor mappings preserve source assignment IDs, owner/suggested owner, internal dates, mandatory flags, evidence, and creation timestamps. Lead rows map to ownership provenance with no redundant task. The document's confirmed lead becomes the work lead; an unambiguous proposed lead remains a suggestion when there is no confirmed lead. Multiple/unresolved lead candidates are retained in the immutable source snapshots and reported as unresolved ownership.

Original assignment rows and document events remain unchanged. Mapping snapshots retain every source field. New case/task creator attribution identifies the officer performing the import; original authorship remains in source history. Repeating the migration returns the existing reconciliation, without overwriting subsequent progress or adding duplicate work. Unsupported states/roles, inactive active-task owners, missing source access, closed/cancelled records, merged source histories, and running/uncertain signing or dispatch operations block migration for explicit resolution. Historical targets after an official deadline are preserved and reported for correction.

## One authoritative progress store

After mapping, `work_task` owns contribution progress. Database triggers protect original assignment rows and the mapping from modification/deletion. `document_assignment_effective` presents current task owners, states, dates, evidence, and mandatory flags to document screens, permissions, metrics, reminders, and closure checks. Legacy lead rows are no longer counted as incomplete contribution tasks.

New contributions added to an imported work item also appear in that document's effective assignments and default to mandatory. Compatibility IDs for these new contributions are negative task IDs; user-facing actions link to named tasks in Shared work rather than requiring these IDs.

The legacy contribution/milestone service delegates to the same transactional task mutation service and requires `task_revision` in addition to the document revision. Both entry points enforce task permissions and reject stale task updates. Task submission evidence remains in the shared work audience; document compatibility events record identifiers/action metadata rather than copying confidential output into document history.

The document detail page reflects current progress and links to Shared work. It hides task details when a reader cannot access the entire linked work item. Current visibility is also checked for milestone notices. Existing document permissions are not silently expanded or removed. Lead ownership changes through Shared work update the associated official document lead and audit history atomically under the existing concerned-officer rule.

Internal targets can now be adjusted by the lead/concerned officer with a reason and task revision. They cannot exceed linked official deadlines. Mandatory unfinished tasks block closure; optional, completed, and superseded contributions do not. Closed/cancelled imported documents and running/uncertain external operations block task changes. Reopen the official record or reconcile the external operation first.

Legacy assign/lead/routing reevaluation mutations on migrated records are refused with a Shared work instruction, preventing a second writable assignment store. Merging migrated documents is also blocked pending a dedicated ownership reconciliation. Unmigrated documents retain their existing behavior.

## Copy-only rehearsal

The CLI opens the source SQLite database **read-only**, uses SQLite backup for a consistent copy, refuses any existing destination, initializes the copy, enables Documents/Shared work only there, and keeps sending disabled. It applies an explicit plan and repeats every migration to verify idempotency. It checks owner/state/date/mandatory/evidence reconciliation and outputs a JSON report.

Example plan (use real IDs/revisions from the permitted evaluation source):

```json
[
  {"document_id": 123, "revision": 4, "outcome": "One supported response", "reason": "Approved rehearsal selection"}
]
```

Run from the repository with its Python environment:

```sh
python scripts/rehearse_work_migration.py \
  --source /path/to/evaluation-source.db \
  --destination /path/to/new-rehearsal.db \
  --plan /path/to/explicit-plan.json \
  --actor-id 42 > /path/to/reconciliation-report.json
```

The actor must already hold the required authority in the source. A failed run exits nonzero; any destination left behind is an incomplete rehearsal, not ready for operation. Review warnings and policy decisions even when all mechanical checks pass. This tool does not deploy a database or turn on operational migration.

## Evidence

- **82 tests passed** across the work, Documents service/HTTP, Workspace, and setup suites.
- Coverage includes all seven mappings, source-row preservation, repeated initialization/import, immutable history, rollback on audit failure, stale task conflicts across entry points, mandatory/optional closure, new contributions, lead synchronization, disabled-feature behavior, milestone reminders, restricted audience filtering, source-file hash preservation, and destination overwrite refusal.
- An actual CLI rehearsal on fictional records produced a report confirming preserved source rows, owners, states, dates, mandatory flags, evidence, and repeat-run identity.
- Actual Chromium browser workflow: navigate from migrated document to shared work, see one contribution with no duplicate lead task, start/submit/accept, then verify document progress/evidence reflects the accepted task. Desktop and 390px mobile capture checked; no horizontal overflow or browser errors.
- Workspace evidence: `/tmp/work-p13-tests.xml` and `/workspace/scratch/work-p13/` (synthetic source, plan, copied database, report, browser checker, screenshots). No production records, mail, signatures, or live Drive were used. Existing Starlette/httpx deprecation warning remains.

## Recovery and remaining gates

Disable `work.enabled` to stop task writes while preserving authorized reads. Mapped records continue to read current task state; disabling the feature does not resume legacy assignment writes. Retain task tables, mappings, and history. Do not downgrade to older code after cutover, because it reads obsolete assignment states and lacks these protections. Rehearsal failure recovery is to inspect/discard the dedicated copy and rerun into a new destination; never replace the source with it automatically.

No operational migration, automatic grouping, bureau-wide activation, or staff acceptance is claimed. Grouping already-merged records, routing reevaluation after cutover, and migrating an agreed operational set remain explicit later decisions. P4.2 still requires an active-record cutover and recovery rehearsal.

Next: **P1.4 — My work and home integration**, selecting actual personal tasks/decisions with next actions, dates, and permission-safe navigation rather than treating broad officer visibility as personal obligations.
