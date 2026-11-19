# Advisory tracker integration — scope for discussion

Planning only, November 19, 2026. Baseline inspected: main `3eea227`.
No application change, release, notification, or Google file edit is proposed for this session.

## Evidence and existing behavior

- [Draft memo and Annex B](https://docs.google.com/document/d/1k40EiuHVdNhAuOzCwnIggG2adTGSt9sR09ndXFJmuP0/edit): Draft, For Review, Approved, Issued, Superseded, Cancelled; automatic numbering; working and final copies; ManCom notification on submission.
- [Proposed tracker](https://docs.google.com/spreadsheets/d/1jcUoLynGR6yInmZmcNcwQo9rmSIOj4VPmXJamR-xuG0/edit): register, dashboard, notification configuration and status definitions. Read on November 19: one issued record. Its script behavior was not tested.
- [Slides template](https://docs.google.com/presentation/d/1T750K6cphrzOo6_-3GlP_9vdEt-fKXLWnZSjCGWbHY4/edit): sample and three template variants. Text was inspected; no visual equivalence claim.
- [Existing advisory feature](ADVISORY_POSTERS.md), `activity_advisory.py`, `activity_advisory_routes.py`, and editor: opening Public advisory prepares an unsaved draft from activity details. First save creates its number. Publishing exposes PNG/PDF on the activity page. Scheduling alone does not create or issue an advisory. Published content currently changes with each saved edit.
- Current storage holds one advisory per activity. Number is allocated from first-save date and retained, although documentation calls this issue date. There is no separate advisory review/approval state or frozen approved copy in these modules.
- Documents/Work already contains version-specific approval and release concepts (`work_review.py`, `documents_actions.py`). Reuse requires a bounded integration assessment; it is not already wired to activity advisories. `document_event` is an audit-event table, not a calendar relationship.

Code evidence establishes current-main behavior, not current production configuration or real Google script execution.

## Recommended experience

Office Connect should own the advisory record and process, with the Sheet optionally serving as an export/reporting view. This is a recommendation awaiting the owner's decision.

1. Schedule/manage activity. Open its existing Advisory section; no second entry of title, dates, venue or resource links.
2. Create an advisory draft or attach an existing working copy. Retain the built-in poster as the default; allow Slides for layouts needing external editing.
3. Save once into the shared register. Show advisory number, preparer, owner, intended recipients, status and related activity.
4. Submit a specific revision for review. Reviewers see the same record in their existing work queue; email links to that review. Merely saving a draft sends no review email.
5. Return with feedback or approve the exact revision. Record who decided and when. Request changes can be a review outcome returning to Draft, preserving the memo's six top-level states.
6. Issue the approved copy through an explicit authorized action. Record issue date and distribution evidence; publish the released version on the activity page when appropriate.
7. Edit a new draft without changing the released copy. A correction/new advisory can supersede a prior issuance, with both retained and cross-linked.

The activity page, central register and reviewer queue are views of the same advisory, not separate records requiring synchronization by staff. Linking the final copy to the activity should be automatic after issuance.

## Scope boundaries and decisions

| Topic | Proposed rule | Decision still needed |
|---|---|---|
| Official register | Office Connect; Sheet is export/reporting | Confirm system of record and transition timing |
| Coverage | Activity-linked and standalone advisories in one register | Must standalone be included in first increment? |
| Activity relationship | One activity may have several advisories: invitation, reminder, change, cancellation | Confirm initial need; current one-per-activity storage must change if included |
| Review authority | Separate preparation, review, approval and issuance permissions | Does any designated ManCom reviewer suffice, are all required, and who formally approves/releases? |
| Numbering | One allocator for all entry paths; preserve old numbers, never silently renumber | Reserve on first save or allocate on issue? If reserved early, date in number means reservation date, distinct from issue date |
| Working copy | Built-in editor or linked Slides; same workflow | Is Google editing required for first release? |
| Final copy | Immutable snapshot associated with approved revision | Accepted format and whether signature is required |
| Issuance | Separate release record from email delivery and public visibility | Does public posting constitute official issuance, or must dispatch be recorded? |
| Changed activity | Flag potentially outdated draft/issued details; offer refresh with review | Which changes require a replacement advisory? |

For external Slides, approval cannot attach only to an editable URL: preserve the reviewed snapshot and its source revision/content identity. If source changes before issue, require reconciliation and renewed approval where applicable. Frozen PDF/PNG artifacts must remain stable even if source files or rendering code change later.

Do not map existing `published=true` directly to formal approval or historical issuance. Inventory and reconcile legacy records, preserving original publication evidence and marking unknown approval evidence honestly. An archived activity should not erase its advisory history. Withdrawing public visibility, cancelling an advisory and cancelling an activity are distinct actions.

## Data and integration outline

An advisory needs stable identity, optional activity link, unique number, owner/preparer, subject, structured recipients, six-state lifecycle, working-source type, draft revisions, approved revision, issued artifact, issue/publication timestamps, supersession reference, and audit history. Store review decisions and delivery attempts against the relevant revision.

Assess linking advisories to existing Documents/Work services for review, approval, release and My desk before introducing a parallel approval engine. Preserve the advisory number as a separate identifier if Documents has its own registration number. Do not assume every advisory requires a signature merely because Documents supports signing.

Notification attempts must be tied to a submission/revision and recipient, with clear pending/failed/unknown results. Refreshes, retries and repeated saves must not generate duplicate review messages. Record publication and dispatch separately; a failed email must not look successfully delivered.

## Delivery increments and acceptance

1. **Agree process:** settle register ownership, approval chain, numbering/date meaning, issuance meaning, standalone/multiple coverage, and Slides requirement. Walk through one normal advisory and one correction together.
2. **Register and activity integration:** extend the existing editor/links, build central listing and filters, inventory legacy Office Connect/Sheet records, and reconcile number collisions before enabling the shared allocator. Preserve existing URLs. Acceptance: one saved record visible from activity and register; retries do not duplicate records/numbers; source history preserved.
3. **Review and controlled issuance:** reuse assessed services, add revision-specific decisions, frozen outputs, reviewer queue and notification receipts. Acceptance: drafts stay private; unauthorized decisions fail; editing invalidates stale approval; issued output remains unchanged; concurrent edits/decisions are detected; repeat issue/notification attempts do not duplicate effects.
4. **Reporting and transition:** reproduce status/month/office dashboard, outstanding review, approved-awaiting-issue and missing-evidence views. Sheet export includes stable IDs and clearly states reporting direction. Acceptance: totals match the same permission-filtered register; existing records retain number and provenance; no two systems independently allocate new numbers.

Keep the Sheet operating under a clear interim authority until cutover. Inventory actual app records and Sheet records with appropriate access during implementation; the one observed Sheet entry does not establish the app's record count. Avoid bidirectional editing in the first release.

## Memo changes after scope agreement

Replace separate Sheet entry/manual template-copy/manual reattachment steps with the activity's Advisory action and shared register. Describe standalone entry where supported. Define reviewer/approver/releasing roles, returned drafts, version-specific approval, number/date rules, how final copies are retained, and how issuance differs from publication/delivery. Replace per-user script authorization instructions if Office Connect handles the integration centrally. Revise the memo only after these choices are settled.

## Session handoff

Saved on `plan/advisory-tracker-integration`. Next: discuss the decisions above, then turn the agreed scope into implementation acceptance criteria. No feature implementation or merge/deployment authorization is implied. Verification in this session is source/document inspection and documentation diff/link checks, not runtime or automation testing.
