# Request reconciliation: design proposal

**Status: proposal for owner review. No code, schema or behavior changes here, and
nothing in this document authorizes implementation or release.** It answers the open
decisions in [the Documents handoff](DOCUMENTS_NEXT_PHASE_HANDOFF.md) for the case where a
reviewed request changes after work was proposed from it. Facts below were read from the
code at `74cefa6` (10.16); items I could not confirm are listed under "Verify before
building".

## What happens today (verified in code)

- A confirmed reviewed request can create one proposed case and one unassigned task.
  `document_request_work` keeps the original `source_json`, `source_hash` and
  `payload_hash` for `(document_id, request_index)`, and the slot is never freed
  (`documents_request_work.py`).
- `existing()` computes `changed` by comparing the current source hash with the
  **original** snapshot hash. So once the source changes, the warning stays on forever:
  there is no way for anyone to say "I reviewed this change".
- The comparison screen shows original source, current source and current work, and
  never writes.
- Existing work writes (`work_tasks.mutate`) can change only owner, status, due date
  (the "Adjust internal target" milestone action) and submission, plus blocker fields.
  **I found no statement in the Python source that edits a task's title or expected output**, so any rule that "updates
  the work to match the source" would need a brand-new write capability.
- Authority to decide on a work item is the case lead or a unit officer
  (`work_decisions.can_decide`). Writes use one transaction, check case and task
  revisions (`work._check_revision`), require shared work to be enabled
  (`work.writable`) and the case to be open (`work_compat.require_open`).
- Source history already exists: `document_understanding_revision` keeps every saved
  version of the reviewed requests.

## The gap

People see a permanent "the saved request changed" warning and can only act by hand in
other screens. They cannot record that they checked the change, so the warning cannot
mean "needs attention" for long.

## Options considered

| Option | What it adds | Risk | Verdict |
| --- | --- | --- | --- |
| A. Acknowledge only | An append-only record that a named person reviewed a specific source change; the warning then compares against the last acknowledged source. No work field changes. | Low; one additive table | **Recommended first** |
| B. A plus a due-date shortcut | A link from the comparison to the existing "Adjust internal target" form, prefilled with the new request deadline. The change itself still goes through the existing milestone action and its checks. | Low; reuses an existing write | Recommended second, only if A ships |
| C. Edit task title/output from the source | A new write path for fields that are immutable today | Medium; changes what "work" means after assignment | Not recommended now |
| D. Automatic reconciliation | Source changes rewrite work | High; overwrites intentional edits | Rejected (the handoff forbids it) |

## Recommended answers to the open decisions

| Decision | Recommendation |
| --- | --- |
| Which fields may change? | None through reconciliation itself. Only the due date, and only through the existing milestone action (option B). Title and expected output stay as proposed; differences remain visible in the comparison. |
| Who decides? | The case lead or a unit officer for that work item (the existing `can_decide` rule). A records user who edited the source but has no authority over the work sees the warning and cannot acknowledge it. |
| Is the original source immutable? | Yes. The proposal snapshot is never edited. An acknowledgement stores the acknowledged source hash and its understanding revision number, not a copy, so history stays in `document_understanding_revision`. |
| Where is acknowledgement recorded? | A new additive append-only table, for example `document_request_work_review(document_id, request_index, source_hash, understanding_revision, task_revision, actor_id, note, created_at)`, created idempotently like the other installers. This is a schema change, so it needs your explicit approval and a reversible plan (below). Alternative without a schema change: a work event holding the hash, which keeps no queryable latest-acknowledged state and is harder to test. |
| What does "changed" mean after acknowledgement? | Source differs from the **last acknowledged** source (or the original if none). The comparison screen still shows original, acknowledged and current. |
| Does it need human confirmation? | Yes: an explicit confirm checkbox plus an optional short note, after the person has seen the difference. |
| Atomic checks | In one transaction: signed-in actor, current document access, current work access, shared work enabled, case open, CSRF, submitted source hash equals the current source hash, submitted task revision equals the current one, and uniqueness on `(document_id, request_index, source_hash)` so a double click or retry returns the same record. A stale hash or revision returns a conflict and writes nothing. |

## What it must never do

- Change any work field, status, owner or assignment, or create a second proposal.
- Bump the document revision, set the document `reconcile` flag, send notifications, or
  invalidate or re-approve a formal consolidation review or release. Acknowledgement is a
  record about the work item, not a document event.
- Write on a read (GET), on a closed or completed case, on migrated legacy work, or when
  shared work is disabled.
- Reveal task titles, counts or statuses to someone who cannot read the work.

## Acceptance scenarios (to write first, as failing tests)

Double click and retry produce one record. A stale source hash, task revision or case
revision conflicts and writes nothing. Denied work access shows nothing and cannot write.
A user without authority sees the warning but no acknowledge control. A closed case, a
disabled module and migrated work block the write. A cleared source keeps its receipt and
history. After acknowledgement the warning clears, and a later source change brings it
back. No work, document, review or notification rows change. No GET changes anything.
Phone and desktop, keyboard only, with and without JavaScript.

## Verify before building

1. `understanding.revise` finishes with `{'reconcile': 1}` on the incoming document. A
   linked source's `reconcile` value is part of the formal-review snapshot hash for other
   documents in the case, so editing a request may already invalidate a consolidation
   review today. I did not test this. A synthetic test should pin the existing behavior
   first; reconciliation must not add to it.
2. Confirm every screen that shows the "changed" warning (overview, receipt, work page
   from 10.15) so all of them switch to the acknowledged baseline together.
3. Confirm how additive tables are installed and ordered at startup, and whether the
   step-generation triggers should cover the new table (they cover `document_*` tables
   by name, so they will).

## Slices, rollout and rollback

1. **R1, service and tests, no UI.** Table, install, service with the checks above, and the
   scenarios as tests. Nothing visible changes.
2. **R2, UI.** Acknowledge form on the comparison screen, baseline-aware warnings on the
   overview, receipt and work page.
3. **R3, optional due-date shortcut (option B).**

Rollback of the UI restores the permanent warning and keeps every record. The new table
is additive and ignored by older code, so no data restore is needed; a schema change
always needs its own reversible plan and the normal backup and version gates. No
production data, staff contact or provider activity is involved in building or testing.

## What I need from you

Approve or change each recommended answer above, and say whether R1 may be built. A
schema addition and each release need your explicit instruction; merging to `main`
deploys.
