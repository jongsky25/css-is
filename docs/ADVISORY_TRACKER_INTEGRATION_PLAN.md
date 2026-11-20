# Office Connect advisory workflow — implementation scope and handoff

Updated November 20, 2026. Planning-only PR; baseline main `3eea227`.
This document supersedes the November 19 exploratory scope and conflicting earlier chat proposals.
The initial planning authorization covered finalizing the plan, committing, pushing and creating a PR.
The owner subsequently said **“start building”**, authorizing the first implementation slice;
see [private drafts and implementation boundaries](ADVISORY_DRAFTS.md). Merge, deployment,
real email and external file changes remain unauthorized.

## Confirmed scope

- Office Connect fully owns advisory preparation, register, review, approval, issuance, notifications, dashboard and history.
- No Sheet dependency, reporting mirror, synchronization, import, transition or reconciliation project. The draft memo and Sheet are requirements references only. This does not authorize deleting the external Sheet or existing application records.
- Initiator prepares; the owning Division Chief reviews and endorses; the Director approves. ManCom-wide notification is not collective approval.
- Internal issuance distributes to Office Connect users; external issuance uses explicitly entered recipients.
- Reviewer and approver can comment and return for changes. The initiator revises, responds and resubmits with previous comments, versions and actions visible.
- Reuse the existing activity advisory editor, rendering and activity association, plus existing email and Documents/Work capabilities where suitable.

## Detailed planning defaults

These defaults make the plan reviewable; they are recommendations rather than additional explicit owner decisions. Resolve the bounded policy questions below before dependent implementation.

- Internal audience means all active users with a deliverable email address; inactive accounts are excluded and missing addresses are reported. Both internal and external may be selected together.
- The initiator selects audience/recipients before review. Approval covers the content and distribution intent. External addresses are validated/deduplicated and never exposed to other recipients.
- After a Director return, revised content goes back through the Division Chief and then the Director. An answer without content/audience changes can remain in the current review stage.
- Issuance is a separate authorized action after approval, with final copy and recipient count confirmation. Approval does not auto-send to the audience.
- Final approved PDF is attached to distribution email; external users need no Office Connect login. Public-page visibility is a separate choice, never implied by internal circulation.

## Evidence and existing behavior

- [Draft memo and Annex B](https://docs.google.com/document/d/1k40EiuHVdNhAuOzCwnIggG2adTGSt9sR09ndXFJmuP0/edit): Draft, For Review, Approved, Issued, Superseded, Cancelled; automatic numbering; working and final copies; ManCom notification on submission.
- [Proposed tracker](https://docs.google.com/spreadsheets/d/1jcUoLynGR6yInmZmcNcwQo9rmSIOj4VPmXJamR-xuG0/edit): register, dashboard, notification configuration and status definitions. Read on November 19: one issued record. Its script behavior was not tested.
- [Slides template](https://docs.google.com/presentation/d/1T750K6cphrzOo6_-3GlP_9vdEt-fKXLWnZSjCGWbHY4/edit): sample and three template variants. Text was inspected; no visual equivalence claim.
- [Existing advisory feature](ADVISORY_POSTERS.md), `activity_advisory.py`, `activity_advisory_routes.py`, and editor: opening Public advisory prepares an unsaved draft from activity details. First save creates its number. Publishing exposes PNG/PDF on the activity page. Scheduling alone does not create or issue an advisory. Published content currently changes with each saved edit.
- Current storage holds one advisory per activity. Number is allocated from first-save date and retained, although documentation calls this issue date. There is no separate advisory review/approval state or frozen approved copy in these modules.
- Documents/Work already contains version-specific approval and release concepts (`work_review.py`, `documents_actions.py`). Reuse requires a bounded integration assessment; it is not already wired to activity advisories. `document_event` is an audit-event table, not a calendar relationship.

Code evidence establishes current-main behavior, not current production configuration or real Google script execution.

## Staff journey and states

1. From a managed activity, open Advisory. Reuse title, dates, venue, registration and resource links; retain editable draft fields. Saving an activity alone does not request approval or issue an advisory.
2. Save a draft with owning division, initiator, audience and recipients. Display it in the central register and activity view as one record.
3. Submit a specific revision. Resolve the responsible Division Chief from existing organizational roles and create the review task and notification.
4. The Division Chief comments, returns with required feedback, or endorses the revision. Endorsement routes to the Director and sends an approval-request notification.
5. The Director comments, returns with required feedback, or approves that exact revision. Approval notifies the initiator and configured releasing staff.
6. Authorized staff issue the approved PDF to the confirmed recipients. Associate the issued artifact with the activity automatically. Show distribution progress and failures separately from the issuance record.
7. Subsequent edits create a new draft; they cannot alter the issued artifact. Supersession links the replacement and prior advisory and retains both histories.

Lifecycle labels: Draft → For Review → Approved → Issued, with Superseded and Cancelled terminal outcomes. For Review must expose its current stage: Division Chief review or Director approval. A return shows Draft / Changes requested and the responsible initiator. Delivery has independent pending/sent/failed/unknown/partial results; Issued must not imply every email was delivered.

Persist release authorization and its frozen recipient/artifact snapshot before queued dispatch. An all-failed attempt remains visibly undelivered; retries target only eligible failed recipients. Provider acceptance is not proof that recipients read or even received the email. Unknown outcomes require checking provider evidence before retry, not blind resending.

## Review, comments and resubmission

- Comment is a discussion action; Return for changes is a decision requiring an explanation and transferring the next action to the initiator.
- Each comment records author, time, target revision and thread. Decision history is append-only; corrections are additional entries, not silent replacements.
- The initiator responds to feedback and supplies a change summary on resubmission. Reviewers can mark concerns resolved or reopen them; initiator replies alone do not establish reviewer acceptance.
- Show earlier versions, content/audience differences, feedback, responses, endorsements, approvals and issuance/delivery events in a readable timeline. Retain links from each decision to the exact version examined.
- Revision or audience changes invalidate outstanding endorsement/approval for the changed draft. A stale browser cannot endorse, approve or issue an obsolete revision.
- While review is pending, changes require withdrawing/returning that submission into revision; do not silently change a packet a reviewer is considering.
- Director returns with content changes restart Division Chief review. Unchanged clarifications remain with the current reviewer/approver.
- Email links open the appropriate authorized advisory screen. Decisions occur in Office Connect, not by interpreting an email reply.

## Authority and notifications

Routing uses the advisory's owning division, not whichever division the editor currently belongs to. Store the selected chief, Director and policy version at submission; validate current authority when acting. If a role is vacant or ambiguous, show a routing problem. Use existing formally designated OIC/delegation rules where applicable; reassignment is explicit and audited. A user cannot acquire approval authority merely by managing the activity. Shared preparer/reviewer/approver identities require an explicit separation-of-duties policy; do not silently auto-endorse.

| Trigger | Email recipient | Work item/result |
|---|---|---|
| Submit/resubmit | Assigned Division Chief | Review current revision |
| Chief endorsement | Director | Approve current revision |
| Either role returns | Initiator | Feedback and revision task |
| Director approval | Initiator and designated releasing staff | Ready for issuance |
| Issue | Confirmed internal/external audience | Approved PDF and advisory identity |

Reuse existing mail transport/configuration and delivery recording where suitable. Queue notifications with stable action/revision/recipient keys. Repeated saves, refreshes and retries must not duplicate messages. A notification failure must not undo a valid review decision; make failures visible and retryable. Optional ordinary-comment emails can be deferred to prevent excess messages.

## Data and integration outline

Use one canonical advisory identity across activity, register, My desk/review queue and history. Model draft revisions separately from immutable endorsed/approved/issued snapshots. Persist owning division, initiator, number, audience intent, explicit external recipients, routing/decisions, comment threads, change summaries, artifact identity, issued recipient snapshot, distribution attempts, publication state and supersession links.

Inspect the existing Documents/Work version-approval, routing, release and mail services before selecting an adapter. Record a concrete service/schema map and avoid a second independent approval engine. Documents registration identifiers, if needed, are distinct from advisory numbers. Do not assume a digital signature is required just because Documents supports one.

Current renderer draws from mutable fields and serves the latest published revision. Replace that coupling with a frozen issued artifact, retained even when fields, source links, fonts or renderer code change. Drafts and comments remain permission-controlled; internal documents must not leak through public activity URLs.

The scope does not include an external Slides integration by default. If later required, approval must bind to a captured reviewed artifact, not just a mutable Slides URL. Reuse the built-in editor for the first increment unless the owner chooses otherwise.

No legacy import, reconciliation or operational cutover tasks belong in the implementation backlog. Ordinary schema compatibility must preserve existing app data/URLs without fabricating historical approvals or silently renumbering records; define this technical behavior during design without introducing a migration project.

## Bounded policy questions before dependent implementation

1. **Issuing authority:** may the initiator issue after Director approval, or only designated releasing staff? Recommended: initiator plus explicitly authorized releasing staff.
2. **Number/date semantics:** retain first-save reservation and label its date correctly, or allocate at issuance? Recommended first increment: retain existing stable reservation; store actual issue date separately. No renumbering existing records.
3. **Coverage:** standalone advisories and several advisories per activity were suggested but not explicitly decided. Recommended first increment: existing activity entry, model ready for later multiple/standalone support; do not create artificial calendar events.
4. **Internal roster:** recommend snapshotting active eligible users at issuance because the approved intent is “all active users,” rather than requiring reapproval for ordinary roster changes. Audience mode and explicit external recipient changes require renewed review. Confirm this policy.
5. **Formalities:** confirm whether final Director approval is sufficient or a separate signature is required, plus the permitted delegation/self-review exception rules. No invented approval exceptions.

These are the remaining choices only. Register ownership, no Sheet work, Division Chief review and Director approval are settled and must not be reopened as unknowns.

## Implementation design continuation — November 20, 2026

The [service map and first-slice specification](ADVISORY_IMPLEMENTATION_DESIGN.md) now records
inspected reuse points, required shared-service extensions, additive schema, compatibility,
transaction/idempotency boundaries and synthetic acceptance criteria. The five-policy package
was presented to the owner. The subsequent build instruction authorizes slice 1 using the
recommended P2/P3 defaults; P1/P4/P5 remain pending for dependent implementation.

## Delivery plan and acceptance gates

### 1. Bounded implementation design

Inspect current main and relevant authorization, document/work, mail, queue and artifact-storage code. Map reusable services and identify necessary schema changes, existing-record compatibility and unresolved policies above. Produce a small implementation breakdown with synthetic test fixtures. This is the next action for a continued planning session, not permission to start shipping features.

### 2. Register, revisions and activity integration

Add shared advisory record, ownership, audience draft, immutable revisions and central listing. Preserve existing editor convenience and show the same record from the activity. Acceptance: no duplicate record/number on repeated save; correct division visibility; drafts private; current data preserved; changing activity details flags differences instead of silently rewriting a reviewed copy.

### 3. Review and approval loop

Add Chief → Director routing, comments, returns, initiator responses, resubmission, history and queued notifications. Acceptance: end-to-end normal approval; return at either stage; revised Director-return routes through Chief again; unchanged clarification stays at stage; permissions/OIC handling; stale decisions rejected; historical comments and artifacts remain available; mail failure/retry does not duplicate decisions or notifications.

### 4. Controlled issuance and distribution

Add final snapshot, issue confirmation, internal/external recipient resolution, PDF email, delivery results and optional public publication. Acceptance: cannot issue unapproved or stale version; internal audience excludes inactive accounts and reports missing emails; duplicate external/internal addresses receive one copy; external users can read attachment without login; no recipient disclosure; retries avoid successful deliveries; unknown outcomes do not auto-resend; issued content remains immutable while revisions proceed.

### 5. Dashboard and memo alignment

Add counts by status/month/division/audience and actionable queues: awaiting Chief, awaiting Director, changes requested, approved awaiting issuance, distribution failures. Counts and links must share permission/filter semantics. Amend the memo instructions in a separately authorized edit to match the final Office Connect workflow. No Sheet-related work.

Verification uses synthetic data with outbound notifications disabled. Cover phone-width and no-JavaScript journeys where supported, normal approval and both return loops, frozen public output, recipient/privacy rules, concurrent actions, retry behavior and count/filter consistency. Full repository release gates apply to later implementation releases; targeted tests do not replace them.

## Saved handoff and new-chat starter

Branch: `plan/advisory-tracker-integration`, draft PR #633. The owner authorized building slice 1
with “start building.” Candidate 10.40 now implements private drafts/register/revisions; see
[the implementation checkpoint](ADVISORY_DRAFTS.md) and SETUP_STATUS.md for validation.
No live workflow, external file edit, real notification, merge or deployment is authorized.

Next: review slice 1, then resolve issuing authority, internal roster timing and formalities
(P1/P4/P5) before their dependent review/issuance implementation. Chief review followed by
Director approval and the no-Sheet scope remain settled. Preserve comments, returns,
resubmissions and internal/external distribution in later slices.

New-chat starter:

> Office Connect: continue draft PR #633 on plan/advisory-tracker-integration. Read AGENTS.md,
> docs/SETUP_STATUS.md, docs/ADVISORY_TRACKER_INTEGRATION_PLAN.md, docs/ADVISORY_IMPLEMENTATION_DESIGN.md
> and docs/ADVISORY_DRAFTS.md. The first private-draft/register/revision slice was authorized by
> “start building” and uses P2/P3 recommended defaults. Check its saved implementation and tests.
> Resolve only the remaining P1/P4/P5 policy choices for later review/issuance work. Everything
> stays in Office Connect with Division Chief review and Director approval, comments, returns,
> resubmissions/history and internal/external distribution. No Sheet work, merge, deployment or
> real notifications. Save progress to the same review branch.
