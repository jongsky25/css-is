# Pending private Telegram live-acceptance checklist

This is a reviewable plan for later execution, not evidence of live acceptance.
The owner has explicitly deferred deployment, activation and live testing. Every
case below is **Pending**. Do not execute it, merge main or change live controls
without the owner's later release/testing instruction.

## Before the later pilot

1. Identify the reviewed PR/source commit and candidate version (currently 9.62).
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
