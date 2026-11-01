# Private Telegram task and work lookup (T6.1a)

This optional read-only capability uses the existing linked private bot chat.
It works with webhook replies on Hugging Face; it needs no outbound Telegram
connection for interactive results. It sends no automatic notifications.

## Commands

| Command | Result |
| --- | --- |
| `/my_tasks` | Up to ten tasks currently assigned to you, newest first, with title, status, deadline and signed-in work link. Includes terminal statuses. |
| `/task_status WORK_ID TASK_ID` | Current metadata for one task assigned to you within that work item. |
| `/my_work` | Up to ten work items you may currently view, newest first. This can include scoped officer access. |
| `/work_status WORK_ID` | Work title, deadline and counts by task state. There is no invented overall case status. |

Follow the exact next-page command when a reply offers one. Lists accept a
positive `BEFORE_ID` cursor; permissions are applied before the page limit.
Replies use current source data and can change between pages. New records appear
on a new first-page request. Empty lists say no items on this page.

## Activation and consent

Source defaults remain off. After a reviewed release, an operator must explicitly
set `CSS_TELEGRAM_WORK_READ_ENABLED=1` alongside the existing inbound, delivery
and linking switches, configured bot/webhook and valid public HTTPS origin.
Documents and Collaborative work must both be enabled. The account must be
active, onboarded and linked with a current bot-bound `work.read` grant.

The signed-in `/account/telegram` page offers **Read my tasks and permitted work
status in private** only when this pilot switch is enabled. It is unchecked by
default. Existing links do not gain this permission: disconnect and repeat the
existing two-channel linking flow, selecting the previous permissions you want
to retain as well as work lookup. In webhook mode use `/status` after the browser
consent form, then the exact `/confirm` command shown privately. Never forward
link codes or send Office Connect passwords to the bot.

Deployment, enabling the switch and consenting are separate steps. This change
has not enabled any live switch or verified real task replies.

## Access and retained data

Task lists and detail are owner-only, even for administrators. Work lists/detail
reuse existing work visibility; they do not turn a generic administrator role
into universal work access. A hidden linked source document hides its work item
and tasks. Unknown, unowned and inaccessible details return the same neutral
message. No results are returned in groups or topics.

Only title, numeric record references, due dates, task states/counts and signed-in
source links are projected. No submissions, outcomes, expected output, discussion,
attachments, linked document contents, account names or other owners' task details
are included. Work counts cover the tasks the existing work screen permits within
that visible case; they are not owner-only counts. No record is acknowledged,
changed, submitted or marked read by a command.

Durable Telegram queues store validated command/record IDs, not rendered titles
or source content. Access is checked at intake, processing and render/send.
Revocation, disconnect, account deactivation, disabled modules, restore and bot
configuration changes retain the existing fences. Rendering uses a current
serialized snapshot; later changes are reflected by subsequent commands, and an
in-flight response cannot be recalled.

## Delivery, pilot and rollback

Private webhook responses retain one-time uncertain handoff semantics: Telegram
provides no delivery result. Duplicate updates cannot replay the response. A fresh
command can request current information. Direct mode uses the existing durable
sender, pacing and uncertainty policy. Never bulk retry uncertain deliveries.

Before live acceptance, use synthetic linked staff to check all four commands,
empty states, paging, ownership and hidden-source denial, then disconnect and
confirm access stops. Record deployed SHA and actual user receipt separately from
mocked tests. The complete group/calendar/room T4.4 pilot remains incomplete.

Pause with `CSS_TELEGRAM_WORK_READ_ENABLED=0`; queued task/work replies become
ineligible. Disabling this switch does not alter calendar/room grants, existing
business records or unrelated notification preferences. Restore retains the
existing global integration revocation behavior. No schema migration or new
third-party dependency is introduced.

## Draft batch: filters, acknowledgement and review submission

The owner requested building the next batch before any live deployment/testing.
These additions are held in the same draft PR and candidate release 9.60.
They do not claim that the full Telegram hosted pilot is complete.

- `/my_tasks overdue`: unfinished tasks with due date before today in Asia/Manila.
- `/my_tasks upcoming`: unfinished tasks due today through seven days ahead,
  inclusive. Tasks without a due date are excluded.
- `/my_tasks review`: tasks with status `for_review`.
- `/my_tasks all`: all owned tasks, including completed/cancelled records.
- Each filter accepts an optional `BEFORE_ID`; the supplied next-page command
  retains the filter. Date filters apply before the page limit.
- `/work_status WORK_ID` also reports completed/total tasks and counts by state;
  the denominator includes all current task states. This is a task progress
  summary, not an invented overall work-case status.

### Acknowledge a task

With separate `tasks.acknowledge` consent and
`CSS_TELEGRAM_TASKS_ACKNOWLEDGE_ENABLED=1`, send
`/task_ack WORK_ID TASK_ID` in your linked private chat. It returns the task,
status transition, note, operation ID, five-minute expiry and exact
`/task_confirm CODE` command. Nothing changes until you send that confirmation.
The normal workflow moves an owned `todo` task to `in_progress`.

### Submit output for review

With separate `tasks.submit` consent and
`CSS_TELEGRAM_TASKS_SUBMIT_ENABLED=1`, send
`/task_submit WORK_ID TASK_ID`. Open the signed-in link, enter output/evidence
(up to 1,800 characters) and a note (up to 500), then prepare the preview.
This does not submit the task. Send the displayed `/task_preview OPERATION_ID`
in the original private chat, review the exact normalized output, then send its
`/task_confirm CODE`. A current owned `in_progress` task moves to `for_review`;
this is not acceptance/completion. Existing blockers, prerequisite acceptance,
open-work checks, current source-document access and review rules still apply.
Long Unicode input can require shortening to fit Telegram's message limit.
Line breaks are preserved; other control characters are replaced with spaces
in the preview and saved output alike. Attachments are outside this increment.

### Shared action rules

Both actions require `work.read`, its host switch, active Documents/Collaborative
work and current separate action consent. All new switches default off and
consent checkboxes default unchecked. Existing links must explicitly relink;
no grant is added by deployment. Task actions use webhook mode only; direct-mode
commands are ignored and cannot mutate a task. Calendar/room workflows retain
their existing transports and permissions. No group task action is exposed.

The form is signed-in, CSRF protected, bounded, rate limited and revision bound.
The private confirmation is actor/connection/bot/context bound. Current workflow
and revisions are rechecked under the writer lock. The change, domain audit,
consumed preview, operation receipt and uncertain webhook handoff commit
atomically. Partial action failures roll back before a neutral error response.
No network request occurs under that transaction. Duplicate update IDs do not
repeat a command; repeated confirmation returns the recorded outcome without
repeating the task mutation. Two confirmations racing serialize to one mutation.

Use `/task_receipt OPERATION_ID` for the recorded outcome and current task status.
Receipt access still requires current ownership/read/action grants; it cannot
keep source access alive after reassignment or revocation. Telegram provides no
webhook delivery result. A lost response can be recovered with an explicit fresh
receipt command; uncertain sends are not replayed automatically.

Submission text is entered only in the signed-in form. It is retained in the
bounded expiring action preview, shown in the private Telegram preview with
explicit consent, and saved to the ordinary work record/audit on confirmation.
It is not stored in Telegram update/delivery payloads, logs, message links or
URL arguments. Expiry, consumption, disconnect, restore and work-read/action
grant revocation scrub pending preview fields with the existing retention rules.
The new work-read revocation fence also applies on upgraded databases.

Pause individual actions with their host switches; pause all task/work access
with `CSS_TELEGRAM_WORK_READ_ENABLED=0`. No disabled action can confirm. Existing
confirmed work records are preserved. Live activation/acceptance remains deferred
by the owner's explicit request; all test users, records and providers are fake.

## Personal summary and document lookup

The same draft now includes `/my_summary`: current authorized-set counts for
overdue tasks, deadlines today through seven days ahead, owned tasks awaiting
review and accessible work with review tasks. Categories overlap; no scheduled
push is created. It uses existing work-read consent. Document lookup has separate
consent and controls; see the [document/summary runbook](TELEGRAM_DOCUMENT_LOOKUP.md).
