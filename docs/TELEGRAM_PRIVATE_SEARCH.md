# Private unified metadata search

Draft PR #572, candidate 9.67. Deployment, activation and live testing remain
deferred. `/find WORDS` searches independently permitted sources in the existing
private webhook reply; it creates no records or scheduled deliveries.

Use a literal phrase of up to 80 characters, for example `/find budget`.
Matching uses Unicode case folding. Apostrophes, `%` and `_` are literal text,
not query syntax or wildcards. Empty/overlong terms and embedded control
characters return usage without querying business records. No separate copy of the query is
echoed as a header or retained in Telegram update/delivery descriptors; intake
keeps only the existing raw-update hash and uncertain handoff receipt. Duplicate
updates cannot repeat a response, and uncertain replies are not replayed.

## Sources and boundaries

| Source | Searched fields | Current policy and result |
| --- | --- | --- |
| Tasks | Task title | Own assigned tasks within source-visible work only. Current task status, due date and `/task_status WORK_ID TASK_ID`. |
| Work | Work title | Canonical RegistryScope visibility, including linked-document restrictions. Due date and `/work_status WORK_ID`; work has no authoritative overall status field. |
| Documents | Number and subject | Canonical, non-archived registry records under the existing document visibility policy. Workflow status and `/document_status ID`. |
| Meetings | Meeting title | The calendar's canonical `blend` scope, `entries` layer, `meeting` kind, today through 30 days ahead inclusive in Asia/Manila. Source status, occurrence date/time, `/calendar DATE` and the exact signed-in entry/occurrence URL. |

Meeting results cover the full dated range, including earlier entries today and
multi-day meetings overlapping the window. Canonical recurrence expansion,
skipped dates and source visibility run before title matching and the result
limit. CSS activity overlays, travel entries, holidays and room availability are
outside this meeting search. A repeated series can match several occurrences;
the source link identifies the occurrence when applicable.

Task output, work outcome, document content/OCR, sender, note, annotation,
people, venue and meeting-URL fields are not searched or projected. Source titles
and subjects are user-authored and can themselves contain identifying text.
There is no full-text index or new schema, scope, provider or dependency.

Each area still needs its existing consent, enabled source module, host pilot
and working private reply configuration. Tasks/work use `work.read`, documents
use `documents.read`, and meetings use `calendar.read`. There is no umbrella
grant; selecting brief sections does not affect search. Disabled/unconsented
sources are omitted before business reads. With none available, the reply points
to `/status`. The menu advertises `/find` only if a supported source is available.

Results are grouped, with at most two per category. Database visibility,
ownership and literal matching precede each limit, so hidden records cannot
consume slots or inflate a "more matches" hint. Tasks/work/documents show newest
matches; meetings show earliest matching occurrences. More matches prompt a
narrower search without a retained search cursor. Complete sections stay within
the UTF-16 message budget; `/menu` leads to the full source lookups.

The active account, original private sender/chat, bot identity/fingerprint and
link generation are checked inside the existing intake transaction. Group/topic,
unlinked and direct-transport requests cannot retrieve results. Existing rate
limits, disconnect/restore fences and signed-in record access remain in force.

Synthetic verification covers mixed/single/missing scopes, hidden linked source
documents, ownership before limits, archive filtering, Unicode/literal matching,
nonretention, meeting range/type/visibility/recurrence, invalid terms, identity
and transport lifecycle fences, duplicate updates and unchanged business records.
The six existing real 390×844 JavaScript-disabled consent/read flows now exercise
search with the selected scope, then verify denial after disconnect, with outgoing
Telegram calls forbidden. Later hosted acceptance is still **Pending** in the
[live checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md).
