# P3.2 — Consolidation and review inbox

October 16, 2026 (Asia/Manila). **In review**, version **6.71**, branch `codex/consolidation-review`. P3.1 was merged at `eded7ce` before development. P3.2 is not merged or deployed.

## Delivered

- Each work item has a **Consolidate and review** screen showing accepted and outstanding required contributions, owners, submitted evidence, blockers/reconciliation needs, and linked outgoing documents. Working drafts, supporting files and handoffs remain accessible from the same screen.
- An outgoing document must already have a verified exact version attached through Documents. Its version ID, recorded fingerprint, current formal state and Google file link are shown before requesting review. A working-draft pointer alone cannot establish an exact reviewed version.
- A concerned officer requests review under the existing routine/Director authority checks. The selected reviewer must already have access to the work item and every linked document. No assignment or document access is granted by the request.
- Requests retain immutable contribution revisions, outputs, source references, working-draft selection, supporting-file identities, exact outgoing version, requester, reviewer and authority note. Review uses the existing Documents service; the recorded review points directly to its request, even when the same version is requested again within the same second.
- The existing Approvals inbox includes permitted consolidation context, exact version/fingerprint and accepted/outstanding counts as recorded at request. The reviewer can open the consolidation screen to approve that version or return it with required feedback. The document page also displays consolidation context and formal review feedback.
- Returns, renewed requests and approvals retain their separate feedback and snapshots. The consolidation screen shows the latest 30 requests; full formal review feedback remains on the document page. Invalid/stale forms retain entered notes.

## Changed-input protection

For a document explicitly routed through consolidation, task revisions, case revisions, selected working draft/supporting links, linked-source content/version/directive/policy/verification/deadline changes or closure/cancellation and new outgoing draft versions invalidate its active review. The same transaction clears approval/signature pointers, changes the outgoing status to Changes requested, increments its revision and appends the reason. Dependent consolidation reviews are invalidated as well. Prior reviews and signature evidence remain historical records.

This is deliberately conservative: a changed contribution revision or minor new draft attachment still requires renewed consolidation review. A signed derivative with the recorded approved source lineage remains valid. Discussion edits and handoff notes do not change the captured input state and leave formal approval intact.

Every approval rechecks the current snapshot, exact submitted version, document revision, reviewer authority and source visibility. Signing/release gates also reject stale consolidation context. If a dependent sign/dispatch operation is running or uncertain, a source change that would invalidate it is rolled back until the operation is reconciled. Pending jobs do not authorize stale signing. Already released/closed/cancelled documents retain their historical state; this increment does not reverse an external effect.

Once a document has a consolidation review binding, it cannot silently drop that context or switch to a different work item on renewed review. Ordinary standalone document reviews remain supported; merely linking an existing document as a reference does not declare it a consolidated output.

## Integrity and boundaries

Additive tables retain requests, indexed source references and invalidations. A nullable `document_review.work_packet_id` identifies the relevant request without changing existing reviews. Repeated installation is safe. History has update/delete guards, and audit failures roll back the entire change. `work_review.py` is included in the deployment allowlist.

Current account, case and linked-document checks protect the consolidation screen and inbox summaries. Document-only readers do not receive restricted case snapshots. CSRF protects requests; all formal writes retain the existing transactional document authority checks. Work feature flags control consolidation requests; authorized history remains readable.

Outstanding required contributions are shown explicitly and captured in the authority note/request context. They are not silently completed or treated as a release approval. Mandatory completion and formal release integration belong to P3.3. Unresolved changed-work decisions must be reconciled before a consolidation review can be requested.

Recorded fingerprints identify inspected versions, but Google links open live files. This increment does not freeze Google files or continuously monitor external edits. Out-of-app Drive changes require the existing inspection/attachment and signing/dispatch fingerprint checks. App access is not proof of Drive access. No live Drive, OCR, signing, mail or deployment success is certified here.

## Verification

**264 tests passed**, zero failures/errors/skips, across shared work, Documents, setup, HTTP routes, Workspace operations, notifications, Meet, short links and travel pages. The final run includes ten consolidation tests. Only the existing Starlette/httpx deprecation warning remains. Report: `/tmp/work-p32-tests.xml`.

New coverage includes exact-version rejection, return/re-request/approval with retained feedback, missing contributions, stale input hashes, source directives and deadline changes, task reopening, working-draft changes, changed-decision gates, downstream invalidation, signed derivatives, minor new drafts, external-operation locks, audit rollback, revoked source visibility, technical-admin denial, repeated schema installation, immutable requests, HTTP CSRF, escaped feedback, and Approvals integration.

Chromium journey: an officer requests Director review with one accepted and one outstanding contribution; the Director opens the request from Approvals, returns it with feedback, and approves a renewed request; a contributor starts the outstanding input and the approval becomes stale while both feedback entries remain visible. Keyboard request submission, 1440px desktop and 390px mobile passed without horizontal overflow or browser errors. Local artifacts: `/workspace/scratch/work-p32`. The browser runner was corrected to await keyboard-triggered navigation, then the complete journey passed on a fresh synthetic database. Drive inspection was simulated; external Google files were not opened.

## Next

Review and merge P3.2. **P3.3 — Formal release and case completion** connects signing/dispatch evidence and mandatory-contribution requirements to the shared outcome. Operational/live acceptance remains in Phase 4.
