# Private Telegram document lookup

This draft addition is held with the private-task batch in PR #572, candidate
9.71. The owner requested building before live deployment/testing. Nothing in
this change enables production delivery or document access automatically.

| Command | Result |
| --- | --- |
| `/documents [BEFORE_ID]` | Up to five currently permitted, non-archived canonical documents, newest first. Follow the supplied next-page command. |
| `/find_documents WORDS` | Literal, case-insensitive number/subject search, up to 80 characters and five visible results. Narrow the search if more results exist. |
| `/document_status DOCUMENT_ID` | Current workflow, verification, due date, routing instruction state, lead/reviewer assignment indicators and current-version approval indicator, with a signed-in source link. |

Lookups show numeric ID, document number and clipped subject. They exclude
bodies, OCR, attachments, file URLs, senders, references, instructions, review
comments, account names and history. Search covers only number and subject;
it does not search hidden file contents. A lookup is not an approval or release.
A recorded workflow state and the current-version approval indicator are shown
separately. Existing permitted archived records may be opened by ID; default
lists/search exclude archives. A permitted merged alias resolves to the current
canonical record; invalid/cyclic aliases fail closed.

## Consent and activation

`CSS_TELEGRAM_DOCUMENTS_READ_ENABLED` defaults off. An eventual reviewed release
also requires the existing inbound/delivery/link switches, valid bot/webhook and
public HTTPS origin, and Documents enabled. Collaborative work can remain paused:
document lookup does not depend on the work module or its permission.

The account must explicitly choose **Read permitted document metadata and status
in private** during two-channel linking. It is unchecked by default and appears
only while the pilot is enabled. Existing links must disconnect/relink, selecting
all previous permissions to retain plus this one. Calendar/work read grants never
grant document lookup. Work/task actions remain independently controlled.

These commands are private and webhook-only. They do not run in groups/topics,
queue an outgoing provider call, send notifications, mark instructions read, or
change a document. Direct reply mode ignores them. Normal Office Connect source
permissions still apply, including restricted records and current scoped access;
a technical administrator role alone grants no blanket document visibility.
Authorization is applied before result limits and rechecked before reply handoff.
Unknown and inaccessible IDs return the same neutral message.

Search text and rendered document metadata remain in memory during the serialized
webhook transaction. They are not retained in Telegram update/delivery payloads,
logs, or URLs. Only the inbound body hash, ordinary command receipt metadata and
an uncertain one-time response marker are retained. Duplicate updates cannot
replay responses. Telegram does not provide a success result for webhook replies.
The same restore/disconnect/account/grant/configuration fences continue to apply.
Previously received messages cannot be recalled; a new command reads current data.

Pause with `CSS_TELEGRAM_DOCUMENTS_READ_ENABLED=0`, disable Documents or revoke
this grant. No old lookup is replayed after re-enabling. No schema migration,
new service or dependency is introduced.

## Personal work summary

`/my_summary` is part of work lookup, not document lookup. It needs existing
`work.read` consent, `CSS_TELEGRAM_WORK_READ_ENABLED`, active Documents and
Collaborative work, and the ordinary private connection controls. It works in
both existing direct and webhook read transports.

The summary uses the current Manila date and reports owned unfinished overdue
tasks, owned unfinished tasks due today through seven days ahead, owned tasks
with `for_review` status, and distinct currently accessible work cases containing
review tasks. Counts are computed across the authorized set rather than only the
first page. Hidden linked source documents exclude their work/tasks entirely.
The categories can overlap; they are not a total to be summed. Source links and
filter commands lead to the current records. No titles, document information or
other owners' task details are added to the summary. It sends no scheduled push.

Local automated acceptance uses only synthetic users/documents/tasks and forbids
outgoing Telegram sends. Actual deployed commands, real account consent and user
receipt remain deferred until the owner requests live release/testing.
