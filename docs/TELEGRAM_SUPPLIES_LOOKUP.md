# Private Telegram supplies-request lookup (T7.2a)

The next independent read child adds your own supply-request approval and
collection status. It remains in draft PR #572, candidate 9.63. Deployment,
activation and real-user acceptance stay deferred by the owner.

| Command | Result |
| --- | --- |
| `/my_supplies [all\|active\|needs_action\|completed] [PAGE]` | Up to five of your requests, newest first. Defaults to all/page 1. Follow the exact next-page command. |
| `/supply_status REQUEST_ID` | Your request's current approval and requester-stage status, needed date and signed-in link. |

The existing Supplies requester queue defines filters. `needs_action` includes
unsent/returned requests and pending receipt confirmations. `completed` includes
rejected/withdrawn requests and source-defined fulfilled requests; it is not a
claim that every listed request was approved or collected. Page values are
1–10,000; request IDs use the source module's positive 32-bit range. Pages read
current records and can shift as new requests arrive; start again at page 1 for
the newest state. Empty/out-of-range pages say no requests on this page.

Results include only numeric request ID, control number (or an unsent-draft
label), approval status, the existing source requester-stage label/neutral
guidance, needed date and signed-in `/supplies/requests/ID` link. The source stage
distinguishes approval, waiting for stock, ready for pickup, pending receipt
confirmation, reported problems and received supplies. Approval alone never
implies a handover or confirmed receipt. Named approver guidance is replaced with
a fixed awaiting-approval sentence. No purpose, item descriptions, quantities,
stock numbers, account/approver names, decision reasons, receipt notes or history
are projected.

## Controls and authority

- `CSS_TELEGRAM_SUPPLIES_READ_ENABLED` defaults off, independently of Documents,
  work, calendar and all task-write switches.
- Supplies must be enabled, along with the existing Telegram inbound/delivery/link
  controls and valid bot/webhook/public HTTPS configuration.
- The active linked account must explicitly consent to `supplies.read`, shown as
  **Read my supply request approval and collection status in private**. The box
  defaults unchecked and appears only while its host pilot switch is enabled.
- Existing links do not gain this grant. At eventual activation, disconnect and
  relink, selecting prior permissions to retain plus supply-read consent.
- Lookup is owner-only. Even a custodian, scoped approver, auditor or technical
  administrator cannot use these commands to read someone else's request.
  Unknown and another owner's IDs return the same neutral message.
- Current account and source permissions are reloaded. Historical own-request
  reading does not require a new current directory assignment; the existing
  requester queue's read policy remains authoritative. Directory requirements
  for saving/submitting requests are unchanged.

Private webhook replies only: group/topic messages and direct reply mode do not
run these lookups. There is no catalog/stock lookup, draft/submission, approval,
handover, withdrawal, or receipt-acknowledgment command in this increment. Use
Office Connect for those actions. No notification or outgoing provider call is
introduced, and no stock/business/audit row is changed by reading.

Source queries and reply rendering share intake's writer transaction. Access is
checked before source reads and again at handoff. Queues retain validated command
receipt metadata/body hashes and an uncertain one-time response marker, never
rendered supply contents. Duplicate updates cannot replay replies. Telegram does
not confirm webhook-response execution; fresh commands retrieve current state.
Messages already received cannot be recalled. Existing disconnect/account/bot/
restore fences remain unchanged.

Pause with the supply-read switch, revoke the grant, disconnect or disable
Supplies. No stale lookup is replayed after re-enabling. Documents/Collaborative
work can remain paused without blocking independently consented Supplies reads.

Tests use synthetic requests, actual source approval/handover/acknowledgment
services and forbidden outgoing Telegram. Live delivery remains unverified and
requires a separately authorized later pilot. No migration, dependency, service
or production setting change is included.
