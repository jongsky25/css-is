# Request reconciliation: design proposal

**Status: approved by the owner on November 10, 2026. Slice R1 (service and tests, no
visible change) was authorized and is built in the PR that carries 10.18; R2 (interface)
and R3 are not started and each needs its own instruction. Release always needs an
explicit instruction.** The text below is the original proposal; the R1 result and the
answer to verify item 1 are recorded at the end. It answers the open
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

## R1 result (10.18)

Built as designed: additive table `document_request_work_review` (append-only; updates
and deletes abort), `documents_request_work.acknowledge()` and `latest_acknowledgement()`,
and 20 tests for the scenarios above. Nothing visible changes: the existing "changed"
warning still compares against the original snapshot until R2 adopts the acknowledged
baseline. Choices made while building: acknowledgement writes only its own row plus a
global audit entry. It deliberately does **not** use `work._event`, because that also
calls `work_review.invalidate` and would retire formal reviews. A repeat of the same
`(document, request, source hash)` returns the original record; acknowledging an
unchanged source is rejected; an acknowledgement of a cleared request is allowed.

**Verify item 1, answered.** Pinned in a test: editing a request on an incoming document
sets that document's `reconcile` flag, and because that flag is part of a linked
outgoing document's consolidation snapshot, the outgoing document's review becomes not
current. This is existing behavior, not added by R1, and acknowledgement neither causes
nor undoes it. Whether staff should be warned before such an edit, or whether the edit
should avoid touching linked reviews, is a separate decision for the owner.

**Rollback.** The table is additive and older code ignores it. Dropping the service call
sites restores today's behavior and keeps every record; no data restore is needed. The
append-only triggers are created with the table.

## Staff warning before a request edit (10.19)

The owner chose to warn staff rather than change the edit itself (November 10, 2026).
The incoming-request review screen now lists, above the save button, the linked
outgoing documents whose consolidation review is currently valid, and says that
saving flags this document for reconciliation and so makes those reviews out of date.
`work_review.stale_if_source_edited()` finds them through direct links and aliases,
returns only items the person may read (nothing about hidden work or documents is
disclosed), writes nothing, and the page load is covered by a no-write test. Saving
behaves exactly as before and still marks the linked reviews not current; a renewed
review must still be requested. Not done: any change to the edit itself, and any
warning on the other screens that can trigger the same flag.

## R2 result (10.20): acknowledge from the comparison screen

Built as designed. On the request comparison/receipt screen, when the source changed,
the case lead or an authorized unit officer sees a "Mark this source change as reviewed"
form (confirmation required, optional note up to 500 characters); everyone else with
access sees the warning and a sentence saying who can mark it. The submission goes to
`POST /documents/{id}/requests/{index}/work/acknowledge`, which uses the existing form
token check and the R1 service, then returns to the same receipt keeping the return
context. A conflict or invalid input re-shows the page with the message, the note kept
and a form carrying the current source reference.

`existing()['changed']` now means "differs from the last reviewed source (or from the
proposal if none was reviewed) and has not simply returned to the proposed source", so
the comparison screen, the document's request overview and the work item all switch
together. `changed_since_proposal` keeps the old meaning and the comparison still lists
every field that differs from the proposal. A later source change brings the warning
back with "changed again after that review". Acknowledging remains a record only: it
changes no work, document or formal review (tested), and page loads write nothing.

Not done: R3 (prefilled link to the existing due-date action); showing acknowledgement
history beyond the latest entry; any browser test for the new form (the workspace has
no Chromium; the form is a plain POST that works without JavaScript).

## R3 result (10.21): prefilled link to the existing target form

Built as designed (November 10, 2026). When a request's source deadline changed since the
proposal, the comparison screen shows "Review the internal target" with the new date. It
links to the work item with a `suggest_target=1` flag; the work page then opens the
existing "Adjust internal target" form for that task with the date filled in and a note.
Nothing is applied by following it. The person adds a reason and saves through the
existing form, so the form token, work revision check, lead-or-officer authority and the
rule that a target cannot follow a linked official deadline all still apply.

The link appears only when the deadline changed since the proposal, is a valid
`YYYY-MM-DD` date different from the work's current target, shared work is enabled, the
case is open, the task is not done or cancelled, and the same predicate that shows the
target form would show it to this person (`work_tasks.actions`). The date is recomputed
on the server from the saved source: a date in the URL is ignored (tested). The flag is
dropped after a save, and the return context is kept. No work, document or review data
is written by loading either page.

Not done: no change to any other work field (title and expected output stay as
proposed); marking the change reviewed stays a separate action; no browser test for the
link (this workspace has no Chromium; the link and form are plain HTML).

## Acknowledgement history (10.22)

Built after R1-R3 (November 10, 2026). When a request's source change has been reviewed
more than once, the comparison screen lists the reviews in a "History of reviews of
source changes" disclosure, newest first: time, who checked, the saved review it
followed, any note, and a "(latest)" mark. One entry stays as the existing status line.
Up to 20 entries are listed; a notice says how many earlier ones are not shown and that
the full record is kept. It links to the saved review history for the request versions.

`acknowledgement_history()` takes the object returned by `existing()`, which has already
checked current document and work access, so it takes no user and cannot read another
request's history. It writes nothing; notes are escaped; the warning logic is unchanged.
Not done: paging beyond 20 entries (the record itself is complete); showing the compared
field values inside each entry (the saved review history holds them).
