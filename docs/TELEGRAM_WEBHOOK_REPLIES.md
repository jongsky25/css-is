# Private replies on Hugging Face

The live webhook accepts Telegram updates, but direct Requests and HTTPX
connections to Telegram time out before an HTTP response. This does not prove a
permanent platform restriction. All application code, data and credentials remain
in the existing Hugging Face Space; no extra host or proxy is required here.

Telegram's documented [webhook response requests](https://core.telegram.org/bots/api#making-requests-when-getting-updates)
allow a JSON response containing `method: sendMessage` and its parameters.
Telegram executes that method using the bot associated with the incoming webhook.
No bot token is included in the response. Telegram explicitly provides neither
success confirmation nor a message ID for this delivery method.

The default private reply transport is `webhook`, gated by the existing inbound
and delivery switches. Those switches continue to default off. Eligible `/start`,
`/help`, `/status`, `/confirm`, `/calendar`, `/calendar_next`, `/room_slots`,
`/my_rooms` and `/room_status` commands use this response. Linking, current account
state, delegated scopes and feature switches retain their existing checks.
`/disconnect` still revokes synchronously without sending a receipt.

An authenticated fresh update, its normal projection processing, current content
rendering and one consumed delivery record share one SQLite writer transaction.
The delivery is recorded as `uncertain` with `error_code=webhook_response` before
committing and returning the response. A duplicate update returns only an
acknowledgement. Workers cannot claim the consumed delivery, and an uncertain
handoff is never automatically retried. A crash after commit but before response
can lose a reply; users can issue a new command. A failed transaction returns 503
and can safely accept Telegram's retry because no response was handed off.
There is no exactly-once guarantee after restoring an older database snapshot.

The response is limited to the current update's authenticated positive private
chat and includes no-store caching headers. It cannot drain another user's
backlog, retry earlier uncertain sends, issue a group response, or process a
queued business action. Renderers for private reads can join this caller-owned
transaction explicitly; normal worker rendering keeps its own transaction.

Operations reports `reply_transport` and aggregate `webhook_responses` separately
from provider-confirmed accepted deliveries. Direct connection probes still use
read-only getMe requests. Their failures do not imply webhook replies failed.
A real user must verify receipt after deployment; mocked tests cannot establish
that Telegram executed the response.

## Remaining outgoing connection work

Scheduled notifications, reminders, group membership checks, group commands and
guided meeting/room actions still use the existing asynchronous outgoing path.
This release does not establish that these work on the live host. An incoming
webhook response cannot independently send a scheduled notification when there
is no incoming update. Keep the full Telegram live pilot incomplete until those
flows have been verified.

## Deployment and rollback

Use only the existing main-only serialized deployment workflow, complete normal
and shuffled verification and fresh verified database backup. No Hugging Face
variable or credential change is required for this transport change. Other
hosting proposals are not part of this release.

For a reviewed transport rollback, set `CSS_TELEGRAM_REPLY_TRANSPORT=direct` in
the existing Space, securing a fresh verified backup before the restart. This
returns private replies to the original worker path and does not retry previous
webhook handoffs. Pausing the existing delivery or inbound switch also prevents
new webhook handoffs. Messages already handed to Telegram cannot be recalled.
