# P3.3 — Formal release and case completion

October 17, 2026 (Asia/Manila). **In review**, version **6.74**, branch `codex/release-completion`. P3.2 was merged at `b788d34`. This increment incorporates main through `387ea48`, preserving the intervening Short.io/manual-short-link releases. P3.3 was subsequently merged at `516ad91` on the user’s instruction. Live deployment success has not been independently verified.

## Delivered

- **Release and completion** is available from work detail, consolidation and the shared-work list. It shows outstanding contributions and required official records, with approval/version lineage, signature evidence, recipient delivery outcomes, acknowledgments, closure readiness and pending/uncertain operations.
- The concerned officer confirms completion scope: internal work without formal release, or formal correspondence with named linked records requiring closure. Consolidated outgoing documents and migrated source records are required automatically. Other incoming/outgoing closure requirements are explicitly selected; reference links alone do not impose release obligations. Requirements are additive and cannot be removed through this screen or an internal-work declaration.
- Required contributions must be accepted or explicitly cancelled. Remaining optional contributions must likewise be finished or cancelled; blockers, prerequisite waits and unresolved changed-decision reviews still prevent completion. The same contribution gate applies before releasing an output bound to shared work or declared as a completion requirement.
- The accountable lead or concerned officer explicitly records the outcome and closure evidence after all gates pass. A confirmed, active lead with linked-record access is required. The completion retains its actor, timestamp and a snapshot of contribution revisions, required records, formal approvals, version/signature evidence, delivery recipients, acknowledgments and closure evidence.
- Completed work is labelled in detail and shared-work lists. Task, lead, document-link, draft, handoff and decision changes require reopening. Discussions remain available; formal records and their histories remain independently governed by Documents.
- An authorized case reopening requires a reason and retains the earlier completion. It never reopens, signs, sends or alters an official record. If a required official record changes so its completion requirements no longer hold, the case becomes open again with an audit event and the previous completion intact.

## Formal evidence and safety gates

A required outgoing record must have actual retained approval lineage for its current version, required signature evidence, recorded delivery to recipients, required acknowledgments and policy-compliant closure evidence. A Closed status alone is insufficient. Existing mandatory document assignments, including configured lead work, remain required by the original document closure service.

Required incoming records must satisfy their own verification, ownership, directive, assignment and closure checks. An authorized document cancellation can satisfy a withdrawn requirement only with retained cancellation authority/reason and no pending or uncertain signing/delivery operation.

Pending, running or unknown sign/dispatch operations prevent completion. The checklist links back to Documents for reconciliation; it contains no send/retry action. Existing version checks, recipient duplicate checks, operation IDs and uncertain-outcome reconciliation remain authoritative. No completion action performs external I/O.

Released documents remain historical evidence. If contribution inputs change after release, the checklist requires an explicitly linked, reviewed, delivered and closed follow-up in the same work item. An unrelated new release cannot stand in for that follow-up. Follow-up chains reject circular evidence. Official closure and case administration after release do not by themselves invalidate the recorded content snapshot.

## Access, consistency and storage

Every screen rechecks the active account, case membership and all linked-source permissions. Completion and scope changes use session-bound CSRF, a current case revision and service-side authority checks. Completion also compares a digest of the currently displayed contributions and formal evidence inside one immediate transaction. Stale forms retain the outcome note; invalid requirements cannot be bypassed by forging the form.

The schema adds an open/completed state and completion mode to existing work items, plus immutable required-record and completion-history tables. Existing cases start open with scope awaiting confirmation. Earlier completions, requirements and audit events cannot be edited/deleted by these services. Audit failures roll back completion and state changes together. `work_completion.py` is included in the deployment module allowlist.

The screen shows the latest 30 completion records; full reopen/scope events remain in work history. Completion snapshots contain metadata/evidence text, not file binaries. Google links still open live files and do not grant Drive access.

## Verification

**290 tests passed**, zero failures/errors/skips, after incorporating main's intervening changes. Only the existing Starlette/httpx deprecation warning remains. Report: `/tmp/work-p33-tests.xml`.

Coverage includes the shared-work suite, Documents lifecycle/setup/routes/Workspace operations, notifications, Meet, short links and travel pages. Thirteen added acceptance cases cover signed release/acknowledgment/closure, internal-work scope, incomplete contributions at release, unknown operations, missing acknowledgments and formal evidence, stale snapshots, disabled writes, atomic audit rollback, official-record reopening, immutable history, required-scope protection, explicit follow-ups, CSRF, escaped/retained notes and revoked access. Existing dispatch timeout/no-blind-retry tests still pass.

The initial regression run identified that configured lead assignments may carry mandatory work. The original document closure gate was preserved, and synthetic journeys complete that formal work through its service before closure.

Chromium journey: a lead sees completion blocked; a signatory records a synthetic externally signed version; an officer records existing email delivery; missing acknowledgment blocks both case completion and document closure; acknowledgment and formal closure enable case completion; keyboard completion freezes contribution changes; an authorized reopening retains the earlier outcome and evidence. The journey passed again after incorporating main. Desktop 1440px and mobile 390px had no horizontal overflow or browser errors. Local artifacts: `/workspace/scratch/work-p33`.

Drive inspection and all signature/delivery/acknowledgment evidence were synthetic. No actual file was signed, no email was sent, and live deployment/integration success is not claimed. The implementation is ready for review; operational/live acceptance remains in Phase 4.

## Next

Review and merge P3.3. **P3.4 — Notification preferences and digests** separates actionable notices from routine follower updates and introduces digest preferences without losing required alerts or exposing restricted work.
