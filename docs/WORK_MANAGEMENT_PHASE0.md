# Phase 0: workflow baseline and proposed contract

Date: October 16, 2026 (Asia/Manila). Baseline: `ab50e56`.

This is the evidence packet for P0.1–P0.3 of [the phased plan](COLLABORATIVE_WORK_MANAGEMENT_PLAN.md). Repository inspection and a fictional interactive walkthrough are complete; staff usability sessions, policy acceptance, and production configuration verification have not taken place. No production records or settings were changed.

## Increment record

| Increment | Status | Evidence | Remaining acceptance |
|---|---|---|---|
| P0.1 | In review | Current journeys, local baseline, and open decisions below | Representative staff validate the journeys; office owner nominates actual policy and integration owners; baseline timing is measured |
| P0.2 | In review | Proposed authority/state/migration contract below | Office owner and concerned chiefs confirm terminology and the stated authority choices |
| P0.3 | In review | [Interactive sample screens](prototypes/work-management.html), with fictional people and records | Contributors, lead, and reviewer complete the walkthrough and record corrections |

The P0 gate is **open**, not accepted. P1.1 was subsequently merged and P1.2 implemented under the user-authorized development exception recorded below. Preparing the contract and prototype alongside the baseline is allowed here because they are proposals for the same P0 review; they do not claim that an unaccepted dependency is operationally ready.

## P0.1 — Current workflow and baseline

### Local execution evidence

- Existing tests in `test_documents.py`, `test_documents_routes.py`, `test_documents_workspace.py`, and `test_documents_setup.py` passed on the local sample database. The runner emitted a Starlette/httpx deprecation warning.
- Local `documents.enabled=0`, `documents.sending_enabled=0`, and document count is zero. This is a development database, not an office deployment snapshot.
- Names/presence checked: `CSS_DOCS_RELAY_URL`, `CSS_DOCS_RELAY_SECRET`, `CSS_MAIL_RELAY_URL`, and `CSS_MAIL_RELAY_SECRET` are absent locally. No values or credential files were read.
- Live file access, OCR, signature placement, official-mail delivery, and office holiday configuration remain unverified. The existing Documents setup instructions remain applicable.
- No observed staff handling-time, adoption, or turnaround measurements are available. Do not substitute test runtime or prototype task counts for those measures.

### Current journeys and required improvements

| Journey | Existing route through the feature | Proposed work journey and acceptance scenario |
|---|---|---|
| Receipt requiring action | Register IN record; verify/rule-route; confirm lead and assignments on document detail | Register receipt, link/start an outcome, confirm accountable lead, assign named contributions; permitted preliminary work can start before verification |
| Two divisions contribute | Separate assignment rows on one record; progress/outcome posted through a numeric assignment form | Two independent tasks, internal dates, one shared draft, and consolidation dependent on accepted contributions; a return does not erase the other division's work |
| Internally initiated outgoing memo | Register OUT draft, attach a version, select review authority, approve/sign/release | Start an internal work item without an invented incoming record; retain the numbered OUT draft and formal version controls |
| For information/reference | Register and process a record according to its configured closure policy | Choose reference-only intake; no personal task is created solely because a record exists; formal retention/closure still follows policy |
| Restricted request | Explicit document viewers; app and Drive rights remain separate | Restricted work audience and document audiences must be compatible; unauthorized lists, search, notifications, and relations reveal no title or content |
| Changed Director instruction | Directive invalidates approval/signature and marks reconciliation | Preserve all contributions, show affected tasks, require an authorized reconciliation decision, and re-review changed final content |
| OIC handoff | Directory/OIC authority is checked by formal actions | Revalidate active authority at action time; preserve earlier authorship; explicitly reassign outstanding tasks and notify affected people |

### Code findings to carry into implementation

1. `documents.list_visible(queue='mine')` uses broad work permission, so records a chief can administer may appear as their personal obligations. P1.4 must select actual task/decision responsibilities.
2. `documents_notify.home_task` shows a document count rather than individual next actions. P1.4 should expose task-level work while avoiding duplicate entries in approvals.
3. `documents.mutate(action='contribution')` first requires assignee-or-officer, then requires coordinator for completion. A lead who is neither the assignee nor officer cannot confirm another contributor's work despite the completion message saying the lead can. P1.2 must resolve this through one explicit authorization predicate and regression coverage.
4. Current contribution updates validate allowed target labels but do not model the proposed full transition graph. The new service must reject invalid jumps, including self-acceptance where the owner lacks acceptance authority.
5. Current access, assignment, and relationship forms request raw IDs; the detail page exposes technical evidence beside everyday work. P1.6 replaces those inputs with contextual choices and an advanced evidence view.
6. Review decisions currently refer to exact document versions. That contract must remain authoritative when tasks and discussion are added.

### Measurements to collect during the staff walkthrough

For each participant, record role, scenario, success/failure, help requested, time to locate their next action/current draft, and misinterpreted labels. During the trial measure receipt-to-owner time, accepted contributions on time, time blocked, review waits, and requests for status outside the system. Record missing dates separately. Agree numerical targets after observing the baseline.

### Outstanding decisions and responsible roles

These are proposed responsible office roles, not appointments of specific people.

| Decision or evidence | Proposed responsible role | Recommendation / next action |
|---|---|---|
| Top-level term | Office product owner and staff representatives | Use **Work item** in the UI; `work_case` remains an internal entity name |
| Lead acceptance of contributions | Concerned chief / office workflow owner | A confirmed lead may accept or return contributors' work, but cannot grant themselves official approval/signing authority |
| Cross-unit task assignments | Concerned chiefs | Lead proposes; authorized chief/officer confirms unless a separately approved delegation exists |
| Restricted work audience | Designated records/access authority | One audience per work item initially; require explicit compatible access before linking restricted material |
| Live relays and artifact access | Existing Workspace deployment operator | Verify capabilities against authorized acceptance files and recipients; do not infer readiness from local tests |
| Deadlines, holidays, release and closure policy | Office workflow owner and designated administrator | Resolve the existing D0 policy entries; guided readiness should explain precisely what is missing |
| Trial measurement and support | Office product owner | Nominate a trial coordinator and role representatives before P4 |

## P0.2 — Proposed domain and authority contract

### Entities and invariants

- **Work item:** one expected outcome, one accountable lead when confirmed, contributing units, audience, stage, priority, and external deadline/provenance if applicable. An unconfirmed lead remains visibly unresolved.
- **Task:** belongs to one work item; has one responsible person when assigned, expected output, internal deadline where needed, submission evidence, and acceptance authority. Collaborators/followers do not share accountability automatically.
- **Document link:** references the existing official document. Numbers, versions, reviews, signatures, dispatches, and original audit events remain in their current records. One primary preparation/release case; other case links are references.
- **Discussion:** contextual messages and edits with author/time/source. A message never becomes an official directive or approval merely because its author is senior.
- **Decision:** explicit authorized action, reason, affected tasks, and relevant exact document version. Supersession preserves prior decisions.
- **Dependency:** directed prerequisite between tasks in the same work item initially; reject cycles. Cross-item dependencies require a later explicit access design. Blocker status does not pause an external deadline.
- **Concurrency:** task revisions protect task edits; work item revisions protect work item edits; comments append independently; document revision/version controls retain their separate meaning.

### Task lifecycle

`Proposed → To do → In progress → For review → Done`.

- Proposed → To do: authorized officer confirms assignment; unresolved/inactive owner is rejected.
- To do → In progress: assigned person acknowledges and starts, with an explicit officer intervention path where needed.
- In progress → For review: assigned person submits output/evidence. The lead can see what changed.
- For review → In progress: lead or authorized officer returns it with a reason.
- For review → Done: lead or authorized officer accepts the contribution, subject to any configured separation-of-duties rule. This is contribution acceptance, not official document approval.
- Done → In progress: authorized coordinator reopens with a reason and records the effect on dependent work. Do not silently revoke released correspondence.
- Cancellation/supersession: explicit authorized action with reason; retain prior owner and evidence. A replacement task must link its predecessor.
- Blocked/waiting: a condition with reason, follow-up owner, and follow-up date; preserve the underlying lifecycle state. A prerequisite prevents advancement that depends on its output, not all preliminary work.

### Authority matrix

All actions also require current active account status and appropriate visibility. The matrix proposes collaboration permissions while preserving formal document authority.

| Action | Contributor | Confirmed lead | Concerned officer/chief | Designated reviewer / signatory |
|---|---|---|---|---|
| Read permitted work; discuss | Yes | Yes | Yes | When a participant or otherwise permitted |
| Propose a task | Within permitted work | Yes | Yes | No additional authority from review role |
| Confirm/reassign someone else's task | No | Only with explicit delegation | Yes within scope | No additional authority from review role |
| Submit contribution | Own assigned task | Own assigned task | Explicit recorded intervention | Own assigned task |
| Accept/return contribution | No by default | Yes, proposed policy | Yes within scope | Only if separately authorized as coordinator |
| Adjust internal milestone | Request change | Yes with reason within external deadline | Yes with reason | No additional authority from review role |
| Extend official deadline | Request change | Request unless separately authorized | Yes under existing rules | No additional authority from review role |
| Grant restricted access | No | Request unless separately authorized | Existing access authority only | Review/signatory role alone grants no access |
| Approve exact outgoing version | No | No automatic authority | Only when designated reviewer under applicable rules | Designated reviewer only |
| Apply signature | No | No automatic authority | No automatic authority | Authorized signatory applies own signature |
| Release / close official record | Existing document rules | Existing document rules | Existing document rules | Existing document rules |

Technical administrators do not receive implicit records, signing, or restricted-reading rights. OIC authority must be resolved from current directory records, not cached role labels. Revoked users cannot retain access through followers, mentions, summaries, notifications, or calendar links.

### Task identity and migration

P1.3 will introduce an idempotent mapping from legacy contributor assignment IDs to authoritative task IDs. Preserve the original assignment history. Lead assignment rows map to work item ownership; do not create a redundant lead task. Proposed, acknowledged, submitted, completed, and superseded states require explicit mappings and reconciliation, not a blanket “open” conversion.

Both old document entry points and new work views must call the same task service after cutover. Do not dual-write independent progress states. Reconcile a database copy before operational migration. No existing task grouping or document merging is inferred merely from similar subjects. A release remains controlled by the document service even when displayed inside a work item.

## P0.3 — Screen walkthrough

Open `docs/prototypes/work-management.html` in a browser. It is a standalone fictional demonstration with no network requests or production connection. State lasts only until refresh or Reset. Its role switch demonstrates proposed experiences; it is not authentication or a security implementation.

1. As **Ana · Contributor**, open My work, inspect the Division A task, and submit an output note.
2. Switch to **Mira · Lead**, open My work, inspect the submitted contribution, return it with a reason, then switch back to Ana and resubmit.
3. As Mira, accept the contribution. Confirm the Division B blocker still prevents consolidation. The other contributor's state must not be overwritten.
4. Open the work item and its discussion; post a note and confirm it appears with the current fictional author. Open the working draft sample.
5. Switch to **Noel · Reviewer**, open Review, inspect the separate exact-version sample, and record a simulated approve/return decision. This does not sign, send, or mark the main case complete.
6. As **Jo · Receiving**, inspect the reference-only example and confirm that no contribution task is created. Try the restricted example as an unauthorized sample role: no confidential title/content should appear.
7. Repeat on a narrow viewport and using keyboard navigation. Record unclear labels, extra steps, and missing context.

Reviewer screen data is a separate fictional item already ready for review. It must not imply that the main case has bypassed its blocked inputs. Sample dates are fixed in October 2026 and are illustrative, not real office deadlines.

### Evidence and acceptance boundary

Automated browser checks cover the contribution submit/return/resubmit/accept journey, the separate reviewer decision, blocked consolidation, a discussion update, reference-only and restricted samples, and narrow-screen layout. These checks demonstrate the prototype's interaction, not backend authorization or staff acceptance.

Checks passed in headless system Chromium using Playwright. No browser script errors occurred, and the 390-pixel viewport had no horizontal overflow. Desktop and mobile captures were visually reviewed. The local verification script and screenshots are retained in `/workspace/scratch/work-phase0/`. Browser file-URL navigation is restricted in this environment, so the checker rendered the permitted local HTML through Playwright's `set_content`; it did not change browser policy. A normal browser can open the standalone HTML directly.

The Phase 0 increment changed no application routes, migrations, feature switches, live relay deployments, or release version. These are design/evidence artifacts, not a shipped application feature. Subsequent P1.1 implementation is recorded separately in [its evidence](WORK_MANAGEMENT_P1_1.md).

The outstanding acceptance gate is a representative staff walkthrough and confirmation of the authority choices above. The user's subsequent instruction to continue authorized P1.1 development against this proposal with writes disabled by default. It does not establish staff acceptance or operational readiness. Do not mark P0 Accepted on the strength of a static prototype or automated tests alone.
