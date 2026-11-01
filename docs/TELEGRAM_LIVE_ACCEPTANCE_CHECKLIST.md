# Pending private Telegram live-acceptance checklist

This is a reviewable plan for later execution, not evidence of live acceptance.
The owner has explicitly deferred deployment, activation and live testing. Every
case below is **Pending**. Do not execute it, merge main or change live controls
without the owner's later release/testing instruction.

## Before the later pilot

1. Identify the reviewed PR/source commit and candidate version (currently 9.77).
   Verify the actual candidate's required metadata/dependency/full normal/shuffled/
   aggregate CI, main freshness and synchronized versions. Old-head checks do not
   establish readiness. Follow existing release and verified-backup gates.
2. Agree which capabilities to activate, which synthetic linked staff accounts to
   use, and a controlled test meeting/room window. Use a low-privilege account plus
   a separate operator/approver account where required. Never use a live staff
   document or real financial/health/dietary data as the negative-test fixture.
3. Keep publication, host feature activation and account consent separate. A code
   deploy enables none of the default-off pilot switches. Record only switch
   names, source/version and safe outcomes; never tokens, passwords, codes,
   cookies, destination IDs or private contents.
4. For the eventual authorized release, use the canonical backup-gated deployment
   workflow, verify the actual hosted version/SHA and inspect current read-only
   Operations diagnostics. Configured syntax/API handoff is not actual receipt.
5. Enable only the agreed pilots, then explicitly consent through the existing
   browser/private-chat link flow. Preserve desired previous scope choices when
   relinking. Staff check the displayed account/permissions before confirmation.

## Private functional acceptance

| Case | Action / expected result | Status |
| --- | --- | --- |
| Task prerequisite addition | Separate consent/pilot, current lead/officer, exact direction and task statuses, confirm/retry once; same-work/self/duplicate/cycle/cancelled-prerequisite guards; no deadline/progress changes | Pending |
| Task prerequisite removal | Separate consent/pilot, exact existing link including cancelled upstream, native remaining blocker/decision rules and no automatic submission | Pending |
| Dependency protections/recovery | Both task changes/deletion/reused IDs, graph changes, lost source rights, revoke/pause/expiry/restore/formal review; atomic failure/concurrent confirmation, recovery without replay | Pending |
| Work/task comments | Separate work/task comment consent/pilots, current source visibility, exact target/text preview, confirmation/retry once; ordinary reader allowed and no task/approval changes | Pending |
| Discussion boundaries | Work-level versus task thread, strict plain text, literal @name without mentions, no reply/edit fields, normal permitted follower notices; terminal/formal-review discussion stays informal | Pending |
| Comment protection/recovery | Changed/lost source and original context, revoke/pause/expiry/restore, atomic notice/receipt/handoff failure, concurrent retries, deleted/reused targets, later edited revision recovery without replay/text disclosure | Pending |
| Work/task replies | Independent reply scopes/pilots, source visibility and exact parent/thread selection; preview parent ID/revision/link plus entered text without stored parent content; confirm/retry once | Pending |
| Reply boundaries/notices | Reject cross-work/work-vs-task/other-task parents; edit parent before pull/confirm then prepare fresh; nested reply allowed; normal eligible parent/follower notices without mentions/access grants | Pending |
| Reply protection/recovery | Terminal/formal discussion stays informal, changed/lost source/context and revoke/pause/expiry/restore protections, immutable parent/FK references, rollback/concurrent retries, later reply-revision recovery without replay/text | Pending |
| Edit own work/task comment | Independent edit consent/pilots; select visible comment/revision, exact replacement preview and confirmation; one retained new revision, no new comment or task/approval changes | Pending |
| Author/thread/stale edit protection | Reader/lead/officer/technical admin cannot edit another author; cross-work/task targets refused; newer edit before preview/confirmation needs fresh current revision | Pending |
| Edit mentions/history/recovery | Existing eligible mentions retained without new selection; inactive/lost-access mention blocks; earlier history/reply parent retained; rollback/concurrent retry and recorded-vs-current revision recovery without text/replay | Pending |
| Link and discover | Complete `/start` → signed-in consent → private `/status` → exact confirmation. `/menu` and `/help` agree and expose only enabled/consented commands. | Pending |
| Pending-link help | Before final confirmation, `/menu` directs the same sender to `/status`; it does not replace the pending challenge. | Pending |
| Limited permissions | With calendar-read consent only, calendar commands appear; work/document/request/write commands do not. No additional grant is created. | Pending |
| Explain blockers | On an otherwise working connection, pause one feature/source or omit its consent. Menu hides its commands; `/status` explains the applicable reason and missing consent. A whole inbound/delivery pause can prevent replies entirely: inspect signed-in controls instead. | Pending |
| Menu examples and navigation | Use displayed task-filter/search examples with fake data. List detail commands contain the correct IDs; detail/back/paging/source links reach the same permitted records. | Pending |
| Current-menu refresh | Revoke one scope or pause one pilot, then request a fresh menu. Removed commands disappear and the actual operation is denied too. An old menu never keeps authority alive. | Pending |
| Tasks read | Compare overdue/upcoming/review filters, owner task status and work summary with Office Connect. Manila date boundaries, empty states and next pages agree; hidden linked documents suppress related work/tasks. | Pending |
| Unified private search | Use `/find WORDS` with fake task/work titles, document numbers/subjects and meeting titles. Compare current source visibility/status and detail targets, Unicode/literal text, the explicit 31-day meeting window and recurrence links. Missing scopes/hidden records/notes/outputs/body text produce no matches or counts; search changes no records and retains no query descriptor. | Pending |
| Daily work brief | Compare `/brief` with the permitted calendar, task summary and own request sources. Verify Manila date range, newest-two/all-status labels, empty sections, section preferences and detail commands; omit revoked/paused scopes. No record is changed. | Pending |
| Staged brief reminder choices | Save section choices, a preferred Manila time and the future reminder preference from the phone form. Save confirms scheduled delivery is not active; no reminder or queued daily delivery appears. Existing calendar/room choices are unchanged. | Pending |
| Task actions | With separate read/acknowledge/submit consent, preview then confirm own To do → In progress → For review. Output is entered in the signed-in form. Source blockers/open-work/revisions remain enforced; readonly users get no write hint. | Pending |
| Task proposal | Consent separately to work read/task proposal. `/new_task` → signed-in fields → exact private preview/confirmation creates one required contribution in proposed state with no confirmed owner. Retry/recover creates no second task. The native officer must still confirm assignment; proposing an account grants no document access. | Pending |
| Proposal source rules | Hidden/completed work, linked official deadlines, changed work/unit/account, expired/revoked previews and source pauses prevent stale creation. Long/multiline/Unicode previews stay bounded and exact. Native assignment enforces linked-document access and review/completion rules; proposal confirmation cannot replace that decision. | Pending |
| Officer task cancellation | Separately consent to work read and task cancellation. A concerned contributing-unit officer gives a reason via `/task_cancel`, checks identified work/task, required/optional flag, current → Cancelled and completion/dependency effects, then confirms exactly. Work lead or owner alone cannot cancel. | Pending |
| Cancellation source effects | Proposed/To do/In progress/For review tasks may be cancelled; Done/already-cancelled tasks and completed work refuse the action. Owner fields, previous submission/output, deadline and history remain. Cancelled contributions are excluded from outstanding checks, while dependencies requiring their acceptance remain blocked. Work completion/official document decisions stay separate; no task deletion or access grant occurs. | Pending |
| Cancellation protections and recovery | Active formal review before/after preview, changed source, lost officer rights and revoked/expired contexts prevent stale cancellation. Retry/concurrent confirmation records once. Cancelled tasks cannot use task reopening; receipt and deletion/ID-reuse checks never replay or cancel a replacement. Use synthetic fixtures for fault cases. | Pending |
| Reopen accepted task | Separately consent to work read and reopening. The concerned case officer or confirmed work lead uses `/task_reopen`, reviews the source submission and gives a reason, checks task/current owner/Done → In progress in the private preview, then confirms exactly. Ownership alone grants no reopening authority. | Pending |
| Reopening source boundaries | Owner, previous submission/output, deadline and pending direction/dependency information remain preserved. Owner must still be active and read every linked document. Completed work must be reopened separately in Office Connect first; active formal review, changed source, lost rights and expired/revoked context block the bot action. No official document is reopened/approved. | Pending |
| Reopening recovery | Duplicate/concurrent confirmation records one task reopening. Normal resubmission/review still applies, including unresolved blockers. Receipt reports later current status without replay; deletion/ID reuse cannot expose or reopen a replacement task. | Pending |
| Officer task reassignment | Separately consent to work read and reassignment. A concerned contributing-unit officer uses `/task_reassign`, explicitly chooses another eligible active person and gives a reason. Preview shows old/new owner, current state and the reset to To do, including In progress/For review tasks. Exact confirmation transfers once. | Pending |
| Transfer source and history | New owner must already read every linked document. Initial-assignment consent, ownership or work-lead status alone cannot transfer. Existing submission/output, deadline, proposal, blockers/dependencies/changed-decision reviews and history remain preserved; no document access is granted. Proposed/done/cancelled tasks, completed work, active formal review and stale/revoked contexts refuse transfer. | Pending |
| Transfer recovery | Duplicate/concurrent confirmation records one transfer. A competing owner preview cannot transfer the updated task again. Receipt reports later current owner/status without replay; deletion/ID reuse cannot expose or transfer a replacement. Use synthetic fixtures for failures and review transitions. | Pending |
| Initial task assignment | Separately consent to work read and task assignment. A concerned contributing-unit officer uses `/task_assign`, explicitly selects an active person in the signed-in form, checks the task/person/unchanged deadline and Proposed → To do preview, then confirms exactly. The suggestion is not automatically selected. Owner confirmation does not acknowledge/submit/review the task. | Pending |
| Assignment source access | The selected person must already read every linked document; missing or revoked access blocks preview/confirmation and grants no document access. Work lead/proposer/suggested-owner status alone cannot assign. Current task-unit officer authority, active account, linked deadline, open work, formal-review and stale/revoked/expired-context rules remain enforced. | Pending |
| Assignment recovery | Retry/recover records one native initial assignment. Competing previews selecting another person cannot reassign it. Later source reassignment is reported as current state without replay. Deleted/reused IDs cannot expose or assign a replacement. Use synthetic fixtures for fault cases. | Pending |
| Internal task deadline | With separate work-read/deadline consent, an authorized officer or confirmed work lead uses `/task_deadline`, the signed-in form and exact preview/confirmation to set/change or explicitly clear an internal deadline with a reason. Owner, progress, submission and official dates stay unchanged. | Pending |
| Deadline authority and recovery | Task ownership alone grants no deadline authority. Changed source/official deadline, revoked rights, closed work, done/cancelled task or active formal consolidation review blocks confirmation. Retry/recover records one milestone; deleted-task recovery never touches a reused ID. Use synthetic fixtures for fault cases. | Pending |
| Record task blocker | Separately consent to work read and blocker recording. `/task_block` → signed-in IDs/reason/eligible follow-up person/exact date → private preview/confirmation records a new blocker. A noncoordinator task owner selects only themselves; a lead/concerned officer may choose another existing permitted member. No task deadline or dependency changes. | Pending |
| Clear recorded blocker | Independently consent to blocker clearing. `/task_unblock` requires a resolution reason, identifies the current task, and clears the current blocker and follow-up fields only after exact confirmation. Stored blocker details stay in Office Connect; the actor-entered resolution is shown in Telegram/history. Prerequisites and pending changed decisions remain unresolved. | Pending |
| Blocker authority and recovery | Native task-owner/current-follow-up/lead/officer permissions, active task/open work/source visibility and formal-review guards are rechecked. New follow-up must already read work/all documents; no access is granted. Recording refuses existing blockers; stale changes, expired/revoked context and cross-protocol attempts fail. Duplicate/concurrent confirmation changes once; deletion/ID reuse and receipt recovery cannot replay. | Pending |
| Task blockers and prerequisites | Separately consent to work read and blocker metadata. `/task_blockers WORK_ID TASK_ID` shows recorded-blocker/pending-direction flags, native waiting/clear check, permitted follow-up owner/date and unfinished prerequisite IDs/titles/states/deadlines. Blocker/decision/submission text remains only in the source work page. | Pending |
| Blocker freshness and paging | Follow source resolution, prerequisite acceptance/cancellation and changed-decision review with fresh lookup. Only Done satisfies a prerequisite; Cancelled remains waiting. Unicode pages have no skips/duplicates and do not imply a global empty list. Inactive/lost-access follow-up owners are neutral; hidden/wrong-case/inconsistent dependency sources share denial. | Pending |
| Read-only resolution boundary | Open the exact source task anchor to inspect reasons/resolve issues through normal permissions. Telegram reads create no operation/preview or source change and grant no resolution rights. Historical done/cancelled/completed state remains labelled; current modules/scopes/private context and direct/group/topic/duplicate fences remain enforced. | Pending |
| Review queue metadata | Separately consent to work read and review-queue metadata. `/review_queue` lists only current For review tasks that the case officer/work lead can review, with task/work/owner/deadline metadata and `/review_task WORK_ID TASK_ID`. Stored submissions/output/blocker notes remain in Office Connect. | Pending |
| Queue actions stay separate | With queue-only consent, no accept/return commands are offered or previews created. With each separately consented and enabled action, the detail gives the existing `/task_accept` or `/task_return` start command and IDs; the signed-in form and exact confirmation remain required. Blocked acceptance can still offer a permitted return. | Pending |
| Queue freshness and pages | Source visibility, current lead/officer rights, open work, owner eligibility and formal-review guards are checked on every list/detail read. Hidden/unknown/ineligible details share a neutral denial. Bounded source scans may offer a continuation without eligible rows; continue it to check older permitted candidates. Unicode pages remain bounded; read requests are never queued or replayed as pushes. | Pending |
| Accept submitted task | Separately consent to work read and task acceptance. Authorized officer/confirmed work lead reviews the submission in Office Connect, prepares `/task_accept`, checks identified work/task, For review → Done and reason, then confirms exactly. Owner, submission and dates stay unchanged; work is not completed and official documents are not approved. | Pending |
| Return for changes | Separately consent to task return. `/task_return` → signed-in reason → private preview/confirmation returns For review → In progress for the current owner, preserving the submission. Task ownership alone grants no review authority. Acceptance consent alone grants no return authority, and vice versa. | Pending |
| Review blockers and recovery | Synthetic recorded blocker, unfinished prerequisite or unresolved changed-decision review blocks acceptance. A fresh permitted return can request changes without resolving these blockers. Changed submission/source/authority, formal consolidation review and revoked/expired contexts block stale confirmation. Retry/recover records one transition; opposite previews and deleted/reused IDs cannot change a confirmed result. | Pending |
| Task recovery | Repeat an already consumed confirmation and request its receipt. One task transition/audit outcome is recorded; no second mutation or submission is created. | Pending |
| Documents | Find a synthetic permitted number/subject and compare workflow/routing/paper status. Body/file/people/notes are absent. Unknown and another test account's restricted ID have the same denial. | Pending |
| Supplies | Compare own approval, waiting-stock/pickup, handover and receipt-confirmation stages with the source UI. Reading changes no stock/request/receipt state; another person's request is denied even to an administrator through the bot. | Pending |
| Travel | Compare own deadline, filing state, paper-review state and completeness count with the source checklist. No amounts, files, DPO number or review notes appear. Paper review never claims payment/office receipt. Purged filings are unavailable. | Pending |
| Meals | Check standalone and room-linked requests separately. Only requested meal states/date/parent state appear; no quantities, dietary request, venue or notes. Room approval does not imply meal delivery. | Pending |
| Arrangements | Compare filing period/requested type/state. Notes/approver remarks/colleagues are absent. The bot links to the actual schedule instead of asserting a pending/old filing is in force. | Pending |
| Calendar-only creation | `/meeting` returns its signed-in guide. Prepare form → `/meeting_preview OPERATION_ID` → exact confirmation → receipt. One correct calendar entry exists; no room was requested implicitly. | Pending |
| Meeting reschedule | Consent separately to calendar read/reschedule; use `/meeting_reschedule` → signed-in exact form → private preview → confirmation. Only date/start/end change on an own plain meeting; repeat/recover produces no second edit. | Pending |
| Meeting cancellation | Consent separately to calendar read/cancel; use `/meeting_cancel` and exact preview/confirmation. Source record is marked cancelled, kept for source recovery, with one revision/audit/outcome. Recovery reports current state without repeating a write. | Pending |
| Management blockers | Another creator, stale/reverted source, recurrence/import/activity/video-managed entry, or newly linked active room booking is blocked. Read/create consent alone grants no management; missing read/write grant, disconnect or paused pilot prevents confirmation. Do not alter live data to induce faults; synthetic tests cover rollbacks. | Pending |
| Room withdrawal | Consent separately to room read/withdraw; `/room_withdraw` → own reference/form → exact private preview → confirmation. Pending requests become withdrawn; approved hours release. The preview identifies pending move children also withdrawn; withdrawing only a move keeps the original booking. No calendar or meal action occurs. | Pending |
| Room date move | Consent separately to room read/move; prepare a new date for the same hours. Pending requests change in place and remain pending. Approved bookings retain old hours while one new move awaits normal approval; only actual source approval releases the original booking. No implicit approval occurs. | Pending |
| Linked room move and blockers | Linked date must match the current permitted meeting and needs calendar read. Changes/approval after preview, target conflicts, revoked scopes and special meal/series/standby/activity/guest/on-behalf-of cases deny stale action. Existing read/request permission grants neither new action. Fault/rollback/concurrency cases stay synthetic. | Pending |
| Combined room request | Explicitly opt into one room block, review the exact preview and confirm. Meeting is saved and room request says pending approval/no booking held. Actual approval remains an Administrative Section action. | Pending |
| Separate room request | `/room_request` → form → `/room_preview OPERATION_ID` → confirmation submits one request for a permitted meeting. No new meeting or automatic approval occurs. | Pending |
| Partial/recovery behavior | If a genuine controlled conflict occurs, verify the actual recorded partial outcome and use its parent-bound room-only retry. Do not introduce a live outage or corrupt source records to simulate failure. Recovery must not recreate a meeting; automated tests cover forced faults. | Pending |
| Privacy and lifecycle | Another synthetic account cannot fetch the first account's previews, receipts or own-only requests. Disconnect/revoke/deactivate as agreed and confirm the next protected read/write fails. No stale queued/uncertain attempt is replayed. | Pending |

Group command/membership verification, automatic change notices/reminders and
outgoing provider connectivity are outside this private acceptance batch. The
complete T4.4 group → calendar → room approval → Telegram update/reminder/revocation/
rollback pilot remains open until separately verified. Do not mark it complete
from successful private webhook replies.

## Evidence and pause plan

Record for each attempted case: source SHA/version, time/timezone, synthetic role,
Observed/Failed/Blocked status and sanitized outcome. Record actual user receipt,
not just HTTP 200, queue counts or a handed-off JSON method. Failed/blocked cases
stay incomplete; do not silently substitute mocked evidence.

If a capability fails, pause its agreed host switch and inspect current safe
Operations fields/source records. Preserve confirmed business records, operation
receipts and uncertain history. Never bulk replay deliveries, reset IDs/keys,
recreate a meeting to recover a room request, or bypass backup/release gates.
Host restarts/transport rollback follow the existing reviewed procedure; private
webhook previews have no outgoing push to revive after switching modes.

After the later pilot, update this checklist and the plan with actual observed
results and remaining limits. Nothing here authorizes an external message,
provider registration, secret/configuration change, merge or deployment now.
