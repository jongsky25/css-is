# Travel papers review-request pilot (v8.88)

M3.4 adds `get_my_travel_review_context`, `prepare_travel_review_request` and
`get_travel_review_request_operation`, disabled by default. Hosted write
acceptance remains pending. It follows supply submission merged in
[PR #499](https://github.com/jongsky25/css-is/pull/499), commit
`1b6fe7fa7f759ed37486e3dbfa312776699915dc`.

## Action and exact preview

Separate optional `travel:review:request` consent allows a current owner to
prepare review of an open filing with review state blank or Changes needed.
Read, draft and other write grants do not authorize it; default OAuth scopes and
old grants remain unchanged. The filing must have no readiness blockers or
running generation job. Choose a current Administrative Section reviewer other
than the traveller. Technical administration alone does not qualify a reviewer.

Inputs are positive 64-bit filing/reviewer IDs, the source's exact current
`updated_at` value as `expected_updated_at` (1–80 characters), and one random
16–80 character operation key. Unknown financial, document, email-address and
decision fields are rejected. The selected recipient is resolved from the
current eligible account, never a model-supplied address.

Call `get_my_travel_review_context(filing_id, before=0, limit=10)` first. Under
this same explicit scope it returns the exact current update stamp, readiness
booleans and a page of eligible reviewer account IDs/display names (maximum 25,
seek cursor `next_before`). It does not return emails, document links, notes or
financial fields. Existing travel reads remain unchanged. Resource-person IDs
are not reviewer account IDs; use the context result rather than guessing.

The signed-in browser shows exact filing reference/title/dates, update stamp,
current document checklist, reviewer name/account/email, prior sent-note count,
normal email feature setting and the message-content summary. It links the
normal filing so the user can inspect the exact saved papers. Snapshot hashes
bind the full filing, checklist links/state, flags and notes without copying
raw document links or financial fields into the preview table. The actor must
review the chosen recipient before **Confirm: request travel review**.

Confirmation keeps filing status Open, sets review Requested, assigns the chosen
reviewer, increments the review round and marks earlier sent feedback notes
resolved. The selected reviewer acts next through the normal queue. This does
not approve papers or a claim, mark ready, record paper submission, generate
files, change financial values or make payment.

## Atomic state, email and recovery

The ten-minute preview binds actor, connection, payload and source/reviewer/mail
setting snapshot. Origin, CSRF, registered session, active grant/scope, enabled
switches, current ownership, source update stamp, complete papers and current
reviewer eligibility are rechecked inside a writer transaction. Same-second
paper/note changes are detected by the content digest even when `updated_at`
has not changed.

The existing travel review service now accepts `commit=False` under a caller's
transaction; its ordinary UI retains default commit and notification behavior.
MCP commits the normal filing/note changes, review-request audit, durable receipt
and one queued email together. A unique filing/round key and stable persisted
operation UUID prevent duplicate queue entries. Any failure rolls all effects
back. Confirmation/recovery never calls the mail transport.

The queued notice uses the normal `travel_review_request_message` composer and
mailer. It contains traveller name, filing reference, activity title and an
authenticated review-page link; no document URLs, attachments or amounts. Its
payload digest is retained separately to detect changed queue content. The
existing scheduler invokes a bounded worker (five rows/tick, maximum 20).
Delivery rechecks owner/connection, source/round, current selected reviewer and
recipient address, normal email feature settings and transport configuration.
An obsolete, revoked or invalid queued request is cancelled. Disabled email is
`skipped_off`; no configured transport is `not_configured`.

Before network I/O, the worker commits `attempting` and a unique attempt ID.
Only queued rows can be claimed. Concurrent workers cannot claim the same row.
Exactly one call to the existing transport is allowed per notice. A true `sent`
result means transport-reported acceptance, not mailbox delivery or reading.
False results, exceptions, timeouts or crashed attempts are `uncertain` and are
**never automatically retried**. Stale attempting rows become uncertain after
ten minutes. If recording a result fails after sending, the persisted attempt
marker still prevents another send. An in-flight attempt cannot be recalled by
a later settings/grant change; the worker rechecks authority before claiming it.
This provides at-most-once attempts, not guaranteed delivery.

The receipt distinguishes original review-request completion from current
notification state (`queued`, `attempting`, `sent`, `uncertain`, `skipped_off`,
`not_configured`, `cancelled`). It returns original Requested state/round,
selected reviewer ID and source, without titles, note text, document links,
recipient address or financial values. Current ownership/grant checks protect
recovery. Later approval/feedback remains separate and is never overwritten by
retry. A timeout/unavailable result is not proof of failure: inspect the original
operation/source and reviewer queue before another key or separate notification.
There is no MCP resend, reviewer decision, cancellation or withdrawal action.

## Retention and operation

Completed/expired preview copies clear; the worker performs bounded cleanup even
when sending is disabled. Queued payloads older than 24 hours are cancelled and
cleared; terminal and stale-attempt payloads clear too. Receipt/attempt markers
and hashes remain, so keys are not recycled. Email attempt outcomes also use the
normal email log. Ordinary filing, feedback and audit retention is unchanged.
Limits are 50 live previews and 10,000 total keys per owner plus the shared
process-local 30/minute action limiter. Multi-worker rate limits still require
shared coordination; delivery claims themselves use the database writer lock.

## Operator acceptance and rollback

1. Deploy v8.88 or newer after release, import-closure, travel/MCP and delivery
   tests. Keep hosted acceptance separate from local results.
2. For a named traveller/reviewer pilot, enable `CSS_MCP_ENABLED=1`,
   `CSS_MCP_TRAVEL_REVIEW_REQUESTS_ENABLED=1` and normal Travel. Reconnect to the
   separate review-request permission and refresh tools. Other write flags are
   independent. Keep normal email feature/transport settings intentional.
3. Prepare a complete synthetic filing with the current update stamp and a real
   eligible pilot reviewer. Compare every preview field, selected email and saved
   papers with the ordinary filing. Verify no request/queue entry before confirm.
4. Confirm once: one round increment, correct reviewer queue entry, prior sent
   notes resolved and one queued notification. Compare source/receipt. Verify
   email remains queued until the worker; verify actual pilot transport logging
   without substituting a queued state for delivered mail.
5. Test refresh between preview and confirm, duplicate confirmation/lost response,
   two keys on the same source, final-audit rollback, stale papers/notes/stamps,
   missing documents, running generation, reviewer loss, self-review, revoked
   owner/grant/session, feature disable and mail settings. Later reviewer decisions
   must survive receipt recovery.
6. With synthetic transports, verify concurrent workers send once, success logs,
   `skipped_off`, `not_configured`, ambiguous failures, crash after claim and a
   failed post-send result write. No uncertain attempt may automatically retry.
   Check bounded queue/attempt expiry and cleanup while sending is disabled.
7. Record deployment SHA, roles, exact source/stamp/round, operation keys, delivery
   states, timings and results. Review the normal queue and mail log before any
   separate manual notice for an uncertain message. Local tests are not hosted
   acceptance evidence.

Rollback: disable `CSS_MCP_TRAVEL_REVIEW_REQUESTS_ENABLED` and restart if needed.
New MCP actions and delivery stop. Queued notices pause; cleanup still cancels
aged rows. Re-enabling rechecks current authority before any unattempted send.
Disconnect revokes the connection and prevents its queued notice from being
claimed. Normal review queues and committed receipts remain. Already attempted
mail is never replayed or silently undone, and rollback never reverses a review
round or deletes feedback history. No live activation is claimed here.
