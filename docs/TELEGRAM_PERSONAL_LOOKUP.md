# Private travel, meal and work-arrangement lookup (T7.3a–T7.5a)

These independent read children stay in draft PR #572, candidate 9.62. The owner
approved building them together before deployment, activation and live testing.
No production configuration or source business record is changed by lookup.

| Scope | Commands | Results |
| --- | --- | --- |
| `travel.read` | `/my_travel [BEFORE_ID]`, `/travel_status ID` | Own non-purged travel reference, activity title/dates, kind, filing state, deadline, paper-review state and source link. Detail adds the count from the source completeness check. |
| `meals.read` | `/my_meals [BEFORE_ID]`, `/meal_status ID` | Own standalone meal request reference/date, parent request state and individual meal order/delivery states. |
| `meals.read` | `/my_room_meals [BEFORE_ID]`, `/room_meal_status ID` | Own room-linked meal form reference/date, room request state and each selected meal state. Room approval never implies meal ordering/delivery. |
| `arrangements.read` | `/my_arrangements [BEFORE_ID]`, `/arrangement_status ID` | Own filing period, requested arrangement type, filing state and link to the ordinary arrangement hub. |

IDs are the positive numeric values shown in results, up to SQLite's signed
64-bit limit. Lists use up to five rows, newest numeric ID first, and may be
shorter to fit Telegram's message budget. Follow the exact next-page command;
permissions are applied before the limit. Pages query current records, not cached
results. Start a new first-page query to see newly created records.

## Controls

Each separate unchecked permission maps to a default-off host switch:

- `CSS_TELEGRAM_TRAVEL_READ_ENABLED`
- `CSS_TELEGRAM_MEALS_READ_ENABLED`
- `CSS_TELEGRAM_ARRANGEMENTS_READ_ENABLED`

The existing inbound/delivery/link controls, current active account, linked bot
fingerprint, private destination and valid public HTTPS origin must also pass.
These commands require webhook reply mode. Direct reply mode and group/topic
messages do not run them. No outgoing provider call or new service is needed.

Travel additionally honors the source `travel.enabled` setting. Ordinary meal
and work-arrangement screens have no source master switch, so no fictitious
source setting is added. Their separate Telegram host switches still pause all
lookup. Documents, Collaborative work and Supplies can independently be paused.

Existing links do not gain these scopes. At eventual activation, disconnect and
relink using the existing two-channel flow, retaining desired previous choices
and explicitly choosing each new read checkbox. Consent never widens source
ownership: even an administrator, Administrative Section reviewer, meal manager
or arrangement approver can read only their own filings/requests through these
commands. Unknown, purged or another person's detail has one neutral denial.

## Source semantics and privacy

Travel uses existing kind/status/review labels and the pure
`travel.missing_for` completeness calculation. Its count can include missing
checklist material and outstanding verification issues; it is not a count of
files alone. No state is synchronized or marked ready by reading. A zero count
or paper-review approval does not mean physical office receipt or payment/claim
approval. Purged filings are absent from both list and detail. Filing status and
paper-review status remain distinct. A submitted/withdrawn filing remains
readable to its owner until purged.

Travel never projects monetary amounts, answers, DPO numbers, routes/venues,
reviewer names, flags/review notes, attachments, Drive/file URLs or generated
content. Detail opens the source checklist for that information. Only the
source-generated travel reference is used for its source link; a damaged
reference cannot become an arbitrary URL path.

Meal lookups use source status labels and selected (`wanted`) room-meal rows.
They expose no activity title, venue, headcount, dietary/special request,
requester/recipient name, contact information or status note. Standalone and
room-linked requests have distinct commands/links so their IDs cannot be
silently confused. A room request's own approval state is labelled separately
from each meal's order/delivery state.

Arrangement lookup shows a filing's requested type and recorded state, not a
calculation of the schedule currently in force. Pending changes, superseded rows,
shared-week effectivity, No AWA tags and other source schedule rules still require
the ordinary schedule hub. No weekday schedule, reason, approver remark/name,
coverage information or colleagues' arrangements are projected.

## Delivery, pause and acceptance

Reads occur under the existing intake writer transaction. Current ownership,
module/host controls, grants, account and bot configuration are checked before
reading and again at reply handoff. Telegram receipts store only ordinary
command/body-hash metadata and the existing uncertain one-time response marker,
never rendered personal contents. Duplicate update IDs do not repeat a response;
a fresh command requests current data. Telegram does not return success/message
ID for webhook-response delivery, and an already received message cannot be
recalled. Existing restore/disconnect/revocation fences remain in effect.

Pause any capability with its host switch, revoke that scope or disconnect. No
stale lookup is replayed after re-enabling. No travel review/submission, meal
ordering/cancellation, arrangement change/decision, receipt acknowledgment,
notification or scheduled push is included.

All automated tests use synthetic records and forbidden outgoing Telegram calls.
Live deployment, personal consent and actual user receipt remain deferred until
the owner explicitly requests release/testing. No dependency or schema change
is introduced.
