# P2.4 — Turn discussion into tasks and decisions

October 16, 2026 (Asia/Manila). **In review**, version **6.65**, branch `codex/work-decisions`. P2.3 was merged at `d44d868` as 6.64 before development, preserving intervening Google Meet changes and their changelog entries. P2.4 was subsequently merged at `855b7bb` on the user’s instruction. Live deployment success has not been independently verified.

## Delivered

### Create a proposed task from a message

A message action opens the exact source text and lets a permitted participant name the contribution, output, suggested owner, unit and internal target. Creation goes through the existing proposed-task service: officer confirmation is still required, and no membership or source permission is granted. The task retains an immutable reference to the exact message revision and displays its original text with a link to discussion history.

There is one derived task per source message, preventing duplicate retries or simultaneous creation. Later message edits do not change the task's saved source. A stale source preview is rejected; unsaved form input is preserved for comparison with the current source.

### Authorized work decisions

The accountable lead or concerned officer can record a coordination decision or a change in work direction from a message. Each record contains:

- Exact source message revision, decision text/reason, actor, authority at recording and timestamp.
- One to twenty affected contributions, with immutable snapshots of ownership, state, expected output, submitted evidence, target dates and task revision.
- Optional supporting correspondence already linked to the work item, recording its document revision and current file-version reference.
- An optional predecessor decision. Replacement requires a change in direction and inclusion of all previously affected contributions. A decision can have only one direct successor; superseded records remain readable.

These are work coordination records. A discussion message or work decision cannot approve, sign, release, issue a formal document directive, or alter official deadlines. Existing Documents actions retain those requirements. UI copy makes this boundary explicit.

### Review changed work

A change in direction preserves current task states and submitted/accepted outputs. It increments affected task revisions so pre-change forms cannot silently apply, and creates a pending review for every affected contribution. Task cards and My work surface this review, including previously accepted work. Submission and acceptance remain blocked until pending change reviews are resolved.

The lead or concerned officer explicitly records whether existing work remains valid, with an explanation, or needs revision. For revision, accepted work is reopened and submitted work is returned through the existing task service. Earlier outputs and acceptance history remain intact. Proposed or unsubmitted tasks retain their lifecycle state for their owner to continue; cancelled work cannot be silently restarted. Reviews and successor records are append-only, and stale/repeated resolutions are rejected.

## Access, storage and deployment

Every public read/write refreshes current access to the work item and all linked source documents. Technical administrators gain no decision authority. Existing enablement/open-work gates apply. Source, task and optional document revisions are checked at save time. Proposal, decision, affected-task revisions and audit history commit atomically; audit failure rolls back all changes.

Additive `work_task_source`, `work_decision`, `work_decision_task` and `work_decision_resolution` tables, foreign keys, indexes and immutable-history triggers preserve existing data. Repeated installation is safe. `work_decisions.py` is included in the explicit deployment allowlist. Version/changelog is 6.65.

## Verification

**170 passed** across shared work, Documents, setup, routes, Workspace operations, notifications and Google Meet relay tests. Only the existing Starlette/httpx deprecation warning. Evidence covers exact source preservation, duplicate/concurrent proposals, proposed-owner access boundaries, authority and cross-case rejection, stale sources/tasks/documents/reviews, unchanged approved document state, retained accepted outputs, explicit reopening, successor coverage and stale successor rejection, revoked access, disabled writes, atomic audit rollback, repeated schema installation, immutable history, HTTP CSRF and escaping.

Chromium journey: participant proposes a task from a message; officer records coordination, then replaces it using a new source; affected accepted output remains visible; officer requests revision and explicitly reopens it while preserving earlier evidence; the other contribution remains a proposal after a retain review. Desktop 1440px and mobile 390px passed without overflow or browser errors. Local artifacts: `/workspace/scratch/work-p24`. Test report: `/tmp/work-p24-tests.xml`.

## Next

Review and merge P2.4, then P2.5 — collaborative draft handoff. Phase 2 acceptance and live deployment verification remain separate checks.
