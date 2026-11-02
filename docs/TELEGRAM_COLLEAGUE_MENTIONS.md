# Colleague mentions in private work/task comments and replies

Draft PR #572, candidate 9.79. Optional colleague selection is implemented in the
existing comment and reply forms for later activation. Deployment, preview
publication, activation and personal/live testing remain deferred. Local checks
use synthetic data and blocked providers.

## Existing commands, separate mention consent

Use `/work_comment`, `/task_comment`, `/work_reply` or `/task_reply` and their
existing exact preview/confirmation/receipt commands. No duplicate posting command
or alternate mutation protocol was added. Optional recipient selection requires
independent `work.mentions` consent and the default-off
`CSS_TELEGRAM_WORK_MENTIONS_ENABLED` switch, plus `work.read` and the relevant
existing comment/reply permission and pilot. Mention consent alone grants no post,
reply, edit, source membership or document access. A comment/reply grant alone
provides no structured mention selection. Unmentioned messages remain available
without mention consent; literal `@name` text does not select a recipient.

Existing account-link consent and current private inbound/link/delivery/account/
bot/chat proof still apply. The menu exposes colleague selection only alongside
a separately enabled and consented comment/reply action; status explains the
missing prerequisite. Direct/group/topic paths retain their existing protections.

## Source-scoped, explicit people selection

When mention permission is available, choose the work item and (for task messages)
the task in **Load eligible colleagues**. Replies may also provide the parent
comment number in this loader. It is a separate read-only GET form that submits
only source IDs and the original private request identifier. Draft message text,
CSRF/action keys and recipient selections are not submitted in that URL. Loading
choices prepares no operation and posts no message.

The server verifies current source visibility and returns only active colleagues
who already read that work and every linked document, using native discussion
mention eligibility. Missing/inaccessible work/task/parent produces no directory
or hidden names. No choices appear before a source is selected or when mention
consent/pilot is unavailable. Nothing is selected automatically. The main POST
form retains its separate required fields and CSRF/key/context checks.

Select up to 20 distinct accounts using labelled checkboxes. The server validates
strict account IDs, rejects duplicates/malformed/over-limit/ineligible selections,
and normalizes selection order. Selected names, identities, active state and current
source access are checked before preparation, preview retrieval and confirmation.
Changed names/accounts/access require a fresh preview. A changed document grant
without a document revision change still prevents a stale mention.

## Exact private preview and native notice effects

The existing five-minute preview shows the complete entered message, exact source
thread, parent number/revision for replies and **each explicitly selected name and
account number**. These names are disclosed as part of the new mention consent.
Recipient identity snapshots bind the selected accounts to that preview. Stored
parent/discussion text and submissions remain in Office Connect. Oversized Unicode
previews are refused rather than silently dropping people or truncating message
text. Shorten the text, select fewer people or use Office Connect if necessary.
Confirm in the original private chat only after reviewing message and recipients.

The existing unchanged `work_discussion.post_in_transaction` receives the validated
IDs and uses native `work_updates.record`. It creates one immutable message/first
revision, structured `work_mention` rows, normal permitted in-app notices and the
author-read marker. Normal follower and eligible parent-author notices still apply.
If a selected person is already a follower or parent author, native recipient
priority/deduplication produces one notice for that person/message. Mentioning
yourself records the structured mention without a self-notice. No follow or
notification preferences, permissions or external Telegram destination are added.
Existing independent digest policies may later include ordinary source notices;
this feature enables or executes no scheduler/digest/provider delivery.

Selection grants no new access. Work/task status, ownership, revisions, submissions,
blockers, prerequisites, deadlines, events and formal approval/review records stay
unchanged. Existing informal terminal/formal-review discussion behavior remains
native. Existing text edits continue preserving their already-recorded structured
mentions with native eligibility checks; changing mention selection on an existing
message remains an Office Connect action.

## Atomicity, revocation and recovery

Source message/revision/mentions/notices/read marker, consumed preview, stored
outcome, receipt and private reply handoff commit together. Notice/receipt/handoff
failure rolls back all. Duplicate/concurrent confirmations create one message and
one applicable notice per recipient. Current source modules, base/auxiliary consent
and pilots, names/eligibility, expiry and original context are checked at the write.
Revocation, pause, account changes, disconnect and restore prevent stale creation.

Revoking `work.mentions` conservatively cancels and scrubs pending work/task comment
and reply previews, including any unmentioned pending preview in those four flows;
prepare a fresh unmentioned message if desired. Existing text-edit previews and
committed source messages remain governed by their own grants. Pausing the mention
pilot blocks selected-mention confirmation; it does not disable fresh unmentioned
posting when its own permissions remain valid.

Existing source/thread/author-bound receipts report the original post and current
comment revision without projecting stored recipient names or repeating delivery.
They do not recreate a mention or retract an immutable posted message. Existing
delete/revocation/restore/retention fences remain in place. No native posting rule,
new source table or receipt identifier column was introduced.

The shared no-script form router now supports explicitly declared optional repeated
fields and source-ID query context only for these comment/reply routes. Other
fields remain single-valued and allowlisted; unrelated forms retain their original
contracts. Body/field limits bound multi-selection, and no message text is loaded
from query parameters. Native source-scoped candidate lookup is reused.

## Verification and deferred acceptance

Use [isolated Python 3.11 commands](CLOUD_WORKSPACE.md), with separate larger-volume
scratch paths for concurrent long suites. Focused files are
`tests/test_telegram_mentions.py` and `tests/test_telegram_mentions_browser.py`.
Coverage includes all four existing posting flows, independent auxiliary/base
consent, source-scoped empty/loading/paused choices, strict/duplicate/20-person
selection, current account/name/work/every-document eligibility, stale permission/
name/context/revoke/pause/restore/expiry checks, deduplicated parent/follower/mention
notices, self mentions, unchanged source/access/preferences, atomic failures and
concurrent retries. Four 390×844 JavaScript-disabled phone flows check consent,
source-only loader URLs, no prepared/posting effect during loading, blank default
selection, CSRF/allowlists, invalid recipients, full exact message/recipient preview,
confirmation/retry, unchanged work/tasks, native notice/mention rows, no outgoing
provider delivery and expired sessions. Existing unmentioned post/reply/edit and
shared-form flows are included in regression checks.

Exact evidence is in [SETUP_STATUS.md](SETUP_STATUS.md). All later
[live acceptance cases](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md) remain Pending.
