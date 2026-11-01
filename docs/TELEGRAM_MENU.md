# Personalized private Telegram menu

Draft PR #572, candidate 9.77. Deployment, activation and real-user testing remain
deferred. This addition changes discovery/guidance, not permissions or records.

- `/menu` aliases the existing private `/help` path. Both show the same current
  account-specific menu, grouped Calendar, Tasks and work, Documents and Requests.
- Only enabled, explicitly consented features with their source modules,
  prerequisite grants and required reply transport available appear as commands.
- `/status` explains available features and why other features are unavailable:
  paused host/source controls, unsupported delivery mode or exact missing consent.
  It names no unavailable feature commands. An account being linked still gets
  its original private confirmation flow; `/menu` directs it to `/status` instead
  of replacing its pending challenge with another start command.
- Examples cover date/calendar lookup, task filters and number/subject search.
  ID/reference placeholders must be replaced with the values in the user's own
  results; an example never supplies an operation/confirmation credential.
- `/brief` appears in webhook mode when at least one supported read source is
  currently available. The [daily brief](TELEGRAM_DAILY_BRIEF.md) respects its own
  section choices as well as every underlying read scope; reminder choices are
  saved separately and do not activate scheduled delivery.
- `/find WORDS` appears in webhook mode when work, document or calendar reads
  are available. [Unified private search](TELEGRAM_PRIVATE_SEARCH.md) includes
  only the independently permitted metadata sources; no new grant is created.
- Meeting rescheduling and cancellation have separate current consent/pilot
  entries. Their [private guided actions](TELEGRAM_MEETING_MANAGEMENT.md) require
  a plain meeting created by the actor; linked room/video/recurring cases remain
  in Office Connect.
- [Room withdrawal/date moves](TELEGRAM_ROOM_MANAGEMENT.md) also have separate
  consent and host controls. Only the actual owner can act; a move of an approved
  booking still requires normal approval and retains the original hours meanwhile.
- `/new_task` appears only with separate task-proposal/work-read consent and an
  available source module/pilot. [Task proposals](TELEGRAM_TASK_PROPOSALS.md) stay
  proposed until native officer assignment; the bot does not assign anyone.

Menus read current account/link/bot/grant/settings state on every rendering.
They query no source business records and cache no feature entitlement. A menu
is a discovery aid: individual records, ownership, revisions, current modules and
workflow rules are still checked by every command. Write features in a menu are
not permission to mutate an arbitrary record or skip confirmation. A future
change can invalidate an earlier displayed menu; issue a fresh `/menu` or `/status`.

Unlinked help stays neutral and does not advertise business commands. Group/topic
messages cannot obtain this private menu. Direct transport retains supported
calendar/room/work and existing guided-action discovery but hides webhook-only
features. Whole inbound/delivery pauses can prevent any bot reply; use the
signed-in account page/Operations for those global conditions. A command menu
cannot repair an offline provider or change host settings.

## Result guidance

Lists now include their own detail command with the actual record ID/reference;
detail views supply a back command. Existing paging/source links remain intact.
Task detail and task receipts offer acknowledgement/submission only when the
current owner, separate write grant/switch, read grant, source module, reply
transport, open-work and task/blocker rules permit that action. The offered
command still prepares a preview; it cannot commit without confirmation.

Meeting/room guides keep the source form link last, previews keep their exact
confirmation/recovery instructions, and receipts name the matching recovery
command and `/menu`. No hint silently starts another action or causes a retry.
Calendar/room reads retain their existing paging and signed-in source navigation.
No inaccessible titles, counts, people, queued messages or credentials are used
to build menu examples or availability explanations.

There is no Telegram global BotFather command registration, shared command list,
inline callback keyboard, new endpoint, schema, scope or external provider call.
Type `/menu` in the existing private chat. This avoids globally advertising
features or requiring a working outgoing setup call. The signed-in connection
page now points staff to the menu and status commands.

Automated tests cover limited/all/no-grant menus, size limits, current revocation,
source/host pauses, direct-mode restrictions, pending linking, private-only alias
handling, and task-specific write hints. Real phone-width no-script consent/read
flows also exercise the menu/status before disconnect. All records/providers are
synthetic and outgoing Telegram is forbidden. Later live acceptance uses the
[pending private pilot checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md).

- `/task_deadline` requires separate deadline/work-read consent and the current
  pilot. [Internal deadline changes](TELEGRAM_TASK_DEADLINES.md) require native
  officer or confirmed work-lead authority and an exact private confirmation.

- `/task_accept` and `/task_return` each require their separate review consent,
  pilot and work read. [Submitted-task reviews](TELEGRAM_TASK_REVIEWS.md) require
  current source officer or confirmed work-lead authority; acceptance preserves
  prerequisite, recorded-blocker and changed-decision review rules.

- `/task_assign` requires separate assignment/work-read consent and its pilot.
  [Initial task assignment](TELEGRAM_TASK_ASSIGNMENT.md) uses current native
  contributing-unit officer authority; a work lead or suggested owner alone
  cannot assign. The selected person needs existing linked-document access.

- `/task_reassign` has separate reassignment/work-read consent and its own pilot.
  [Officer transfers](TELEGRAM_TASK_REASSIGNMENT.md) preview old/new owner, current
  status and the reset to To do, preserving submission/deadline and native access.

- `/task_reopen` requires separate reopening/work-read consent and its own pilot.
  [Accepted-task reopening](TELEGRAM_TASK_REOPENING.md) uses current case-officer
  or confirmed work-lead authority and preserves owner/submission/deadlines.
- Status lists each missing consent label, with relinking instructions once in
  the footer rather than after every feature. This keeps the expanded status
  within Telegram's message limit without dropping permission explanations.

- `/task_cancel` requires independent cancellation/work-read consent and its pilot.
  [Officer cancellation](TELEGRAM_TASK_CANCELLATION.md) previews current/Cancelled
  state, required/optional contribution and completion/dependency effects before
  exact confirmation. Work-lead or owner status alone is insufficient.

- `/review_queue` and `/review_task WORK_ID TASK_ID` require separate review-queue
  metadata/work-read consent and their pilot. The [queue](TELEGRAM_REVIEW_QUEUE.md)
  uses current source review authority and eligibility; accept/return hints each
  require their separate write consent, pilot and native action.

- `/task_blockers WORK_ID TASK_ID [BEFORE_ID]` requires independent blocker-metadata
  consent, work read and its own pilot. [Blocker lookup](TELEGRAM_TASK_BLOCKERS.md)
  shows current flags, unfinished prerequisites and permitted follow-up owner/date.
  Own-task and review details offer this hint only with that read grant/pilot.

- `/task_block` and `/task_unblock` each require separate write consent, work read
  and an independent pilot. [Blocker management](TELEGRAM_BLOCKER_MANAGEMENT.md)
  uses native participant/coordinator authority, explicit follow-up selection and
  exact private confirmation. Blocker metadata consent alone grants no write.

Dependency addition/removal use independent private workflows: see
[task dependency management](TELEGRAM_DEPENDENCY_MANAGEMENT.md).

Plain work/task posts use separate private confirmations and discussion visibility:
[work and task comments](TELEGRAM_COMMENT_MANAGEMENT.md).

Replies have independent consent and exact parent/thread checks:
[work and task replies](TELEGRAM_REPLY_MANAGEMENT.md).

Author-owned text revisions use independent consent and exact revision previews:
[work and task comment editing](TELEGRAM_COMMENT_EDITING.md).
