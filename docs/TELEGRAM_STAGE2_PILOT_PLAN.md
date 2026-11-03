# Telegram stage-2 isolated pilot and acceptance plan

Prepared 2026-11-03 for draft [PR #572](https://github.com/jongsky25/css-is/pull/572).
Status: **plan prepared; publication, activation and real messages not authorized**.
Optional features are frozen. This is the concrete proposed test scope, not a
claim that a target, bot, pilot launcher or hosted acceptance already exists.

## Candidate and evidence boundary

Application baseline: `1f25bbdbd5720873f2adea778e91ba13acd45395`, version **9.91**;
inspected review head: `edcc4375c5dfa044251726ab1ba8a968f9cc2e8c` (handoff docs).
Main: `625c60f2fc91ddf98519a9084a5c4217fd1f2e56`, version 9.62, already an ancestor.
The final documentation commit containing this plan becomes the next candidate:
freeze its actual full SHA only after its own complete CI and avatar gates pass.
Record that SHA in the PR evidence without creating another source-only commit.
Any later pilot tooling/runtime fix needs a new reviewed SHA, appropriate tests,
fresh gates and an explicit assessment of acceptance that must be repeated.

Use the [live checklist](TELEGRAM_LIVE_ACCEPTANCE_CHECKLIST.md) as the detailed
case inventory. Every case remains Pending. Historical local tests and older
owner-reported linking/calendar success do not count as this candidate's pilot.

## Proposed target and reachability decision

Reserve **`equityinhealth/office-connect-telegram-pilot`** as the proposed isolated
Hugging Face Docker target, CPU Basic only. This is a proposed name, not a live
URL or an availability/entitlement claim. Do not reuse production
`equityinhealth/office-connect` or replace the shared
`equityinhealth/office-connect-preview`.

Preferred first provider pilot: a **protected** HF Docker Space (private source,
publicly reachable app), with application
sign-in, a dedicated test bot, and only the authenticated Telegram machine
callback exposed without a browser session. The webhook path is
`/integrations/telegram/webhook`; `CSS_BASE_URL` must be the actual verified HTTPS
app origin, not the Hub page. Telegram supplies
`X-Telegram-Bot-Api-Secret-Token`; preserve its existing validation and limits.
Never put the HF token, bot token or webhook secret into the callback URL.

A private Hub-authenticated Space is unsuitable unless independent provider
reachability is demonstrated: Telegram cannot use the owner's browser session.
The preferred target uses HF's **protected** visibility, not private visibility.
Read-only `whoami-v2` on 2026-11-03 confirmed the configured identity matches
`equityinhealth` and reports `isPro=true`. Current
[HF Spaces documentation](https://huggingface.co/docs/hub/spaces-overview#space-visibility)
states protected visibility is included in Pro, keeps source private and exposes
the app at its embed origin. This identifies an existing-plan option without a
purchase; it does not prove target creation/write permissions or actual Telegram
reachability. Verify both before registration and stop if protected mode cannot
be selected. No public-source fallback, paid upgrade, proxy or new host is
authorized. Public source publication would require a separate explicit decision.

Authenticated target metadata returned HTTP 404 for the proposed name; this
means inaccessible/not found, not proof the name is available or creatable.
The existing shared preview was observed private/Docker at Space commit
`d98f59e4aa973dfba99c67e1a0a5b7c17eb90cb2`, SLEEPING, requested CPU Basic. It was
not woken, changed or republished. No current production runtime was inspected.

Existing `deploy_preview_hf.py` rejects public targets and has a fixed destination;
existing `preview_app.py` strips Telegram configuration and denies outbound
sockets. Do not alter either to turn the shared preview into a provider pilot.
A separate test-only launcher/bundler is a prerequisite, not existing capability.

## Local preparation required before publication approval

The proposed protected target determines the bundle design. Implement and
verify the following isolated tooling before asking to publish that bundle:

1. Fixed pilot destination; dry-run by default; clean committed source manifest
   with full Git SHA, application version and bundle hashes. Reject production
   and shared-preview targets. Never invoke the production uploader or include
   DBs, backups, logs, `.env`, credential files or production session keys.
2. Fresh synthetic DB precreated before application import; no source seed copy,
   production mount, bucket, snapshot or startup restore. Fail closed if required
   pilot credentials/participant configuration are missing. Create only the
   predeclared synthetic accounts through native setup APIs; no open bootstrap.
3. Separate pilot secrets, no inherited integration credentials. Keep
   `CSS_NO_SCHEDULER=1`, `CSS_TELEGRAM_REPLY_TRANSPORT=webhook`,
   `CSS_APPRISE_TELEGRAM_ENABLED=0`; omit all SMTP/relay credentials. Block direct
   Telegram send/membership calls and other application outbound providers.
   Interactive webhook-response messages still count as real messages.
4. Authenticate the webhook before parsing; enforce a pilot-only numeric private
   sender/chat allowlist before any linking response or business action. The
   current application has no dedicated participant allowlist switch: implement
   this in the separate wrapper and test it, do not invent a production flag.
   Validate body bounds, private chat equals sender, no topics/groups, known
   participant and fail-closed config. Do not log bodies, codes or numeric IDs.
5. Add a persistent PILOT / SYNTHETIC DATA label and build/boot identity. A process
   restart deliberately resets this first pilot DB, sessions, grants and receipts;
   stop the batch on an unexpected boot change. This disposable profile cannot
   establish durable restart/restore acceptance. Never replay old updates into a
   fresh DB or infer exactly-once behavior across resets. Register only fresh test
   interactions after an agreed reset, and record the new boot identity.
6. Locally test the actual staged bundle: seed isolation/sentinel untouched,
   provider blocking, missing/wrong webhook secret, unlisted sender/group denial,
   no bootstrap bypass, valid allowlisted intake and strict signed-in forms.
   Use Python 3.11, hashed locks and the cloud wrapper. Test real browser flows
   with fake webhook responses; label them local, not provider receipt.

This session prepares the plan only. None of this new pilot tooling is claimed
implemented or tested. The existing reviewed application remains unchanged.

## Accounts, fixture allowlist and secrets

Only the owner and one explicitly nominated test participant operate Telegram
identities. Bind those numeric identities privately in pilot host secrets; never
store them in GitHub/chat evidence. One Telegram identity links to one app account
at a time: disconnect and relink explicitly when changing roles. A second actual
identity is required for cross-user provider acceptance; browser-only role tests
cannot substitute for it.

| Synthetic account | Native role/fixture authority | Purpose |
| --- | --- | --- |
| `pilot-staff@example.invalid` | Low-privilege active employee with directory/person/unit linkage and permitted documents/work; task owner | Reads, own requests, task actions, discussion author |
| `pilot-officer@example.invalid` | Separate current concerned-unit officer/work lead with explicit source visibility | Assignment/review/deadline/dependency authority and foreign-owner denials |
| `pilot-peer@example.invalid` | Another ordinary eligible employee; distinct owned requests/comments | Mentions, foreign ownership, lost-access/negative cases |
| `pilot-admin@example.invalid` | Isolated administrator and native room/supply approval configuration | Fixture setup and source approvals; admin role must not defeat own-only bot checks |

Accounts are a proposed fixture specification, not provisioned identities. Keep
unique test passwords in the pilot's secret store/password manager. Do not copy
production passwords. Native officer appointments, document access and staff
linkages must be created explicitly; synthetic admin alone is insufficient.

Fixture set: one permitted and one restricted document/work pair; proposed,
To do, In progress, For review, Done and Cancelled tasks; blocked/prerequisite and
formal-review cases; separate work/task top-level and nested comments with long
Unicode text and two revisions; own and foreign unread notices/follows; active
catalog lines and own draft/returned/submitted supplies requests; zero-approver
and normal synthetic routing variants; plain/recurring/foreign meetings and own
pending/approved room requests; own/foreign travel, meals and arrangement states.
Use obviously fake labels and `.invalid` recipients throughout. Never seed live
staff data or actually mail the synthetic approval queue.

Choose one future ordinary business day within the native room horizon at test
execution. Record Asia/Manila date and 10:00–11:00 test slot after confirming the
synthetic board is free. Use a separate slot for a controlled conflict. Source
approvals are performed by the synthetic authorized actor through normal UI.

Secret locations/names only: scoped cloud `HF_TOKEN` for this target, test host
`CSS_TELEGRAM_BOT_TOKEN`, `CSS_TELEGRAM_WEBHOOK_SECRET`, `CSS_SESSION_SECRET`, and
new pilot-specific account/participant configuration defined by the reviewed
launcher. Do not read or replace production secrets. Owner creates the dedicated
bot in BotFather and saves its token through supported secret settings; never
paste it into chat. Check bot identity privately and confirm it is not production.

## Sequential feature and consent allowlist

For each batch set the listed host switches to `1` **only after its scoped
activation approval**. Names below are suffixes in
`CSS_TELEGRAM_<UPPERCASE_SUFFIX>_ENABLED`. All other switches remain `0` unless
needed by the current batch. Baseline is `inbound`, `delivery`, `link`. Each
capability also requires explicit browser consent; host enablement grants none.
Scope names are the suffix with underscores changed to dots except
`work_comment_edit` → `work.comment_edit`, `tasks_comment_edit` →
`tasks.comment_edit`, `tasks_dependency_add` → `tasks.dependency_add`, and
`tasks_dependency_remove` → `tasks.dependency_remove`.

| Batch | Additional switches | Acceptance and source evidence |
| --- | --- | --- |
| A — identity/discovery | First `calendar_read`, then selected batch switches | Start → signed-in explicit scopes → status → confirm; pending-link help; limited permissions; fresh menu/status; negative/revoked scope and longest enabled menu. Never issue another start while confirmation is pending. |
| B — calendars/rooms | `calendar_read`, `calendar_create`, `calendar_reschedule`, `calendar_cancel`, `rooms_read`, `rooms_request`, `rooms_withdraw`, `rooms_move` | Exact preview/no pre-confirm write; one meeting/request; ordinary approval; moves/withdrawals; own/foreign/managed/conflict denials; partial room-only recovery. Calendar and room approval remain separate. |
| C — work/tasks | `work_read`, `tasks_acknowledge`, `tasks_submit`, `tasks_create`, `tasks_deadline`, `tasks_accept`, `tasks_return`, `tasks_assign`, `tasks_reassign`, `tasks_reopen`, `tasks_cancel`, `tasks_block`, `tasks_unblock`, `tasks_dependency_add`, `tasks_dependency_remove`, `tasks_review_read`, `tasks_blockers_read` | All task/checklist rows: native actor/linked-document authority, exact status transitions, prerequisites, formal review, stale state, duplicate/receipt recovery and no implicit completion/approval. Use separate fixtures for incompatible transitions. |
| D — discussions | `work_read`, `work_comment`, `tasks_comment`, `work_reply`, `tasks_reply`, `work_comment_edit`, `tasks_comment_edit`, `work_mentions`, `work_updates_read`, `work_updates_acknowledge`, `work_follow`, `work_follows_read`, `work_discussion_search`, `work_discussion_read` | Every discussion/read/search/follow/inbox/shortcut row: independent consent; current text/revision/ownership; nested pages/parts; strict forms; read acknowledgements only by exact confirmation; no read/follow change from lookup. |
| E — supplies | `supplies_read`, then independently `supplies_draft` and `supplies_submit` | Draft/no number; submit without draft grant; exact full routing preview; one number/version/normal queued notice; zero approvers; returned number retention; stale/current/foreign and receipt cases. No stock hold/issue or real email. |
| F — other reads and composition | `documents_read`, `travel_read`, `meals_read`, `arrangements_read`, `supplies_read`, `work_read`, `calendar_read`, `rooms_read` | All private-read, unified search, brief/preference rows; current source parity, excluded fields, empty/paging/timezone and independent scopes. Preference saves do not activate scheduling. |
| G — lifecycle | Only the capability under test plus its dependencies | Revoke, disconnect, deactivate, pause, source loss, stale cached form, duplicate and receipt. Preserve original/current outcomes. Destructive faults and restore/concurrency are isolated local cases, separately labelled. |

Always off: `groups`, `change_notices`, `reminders`, Apprise and all scheduled
workers. No production bot registration, group membership calls, direct send,
email, scheduled reminder or monitoring alert belongs to this private pilot.
Read `telegram_links.claim` prerequisites as well: rooms request needs calendar
and room read; task/discussion actions need work read; notice acknowledgement
also needs inbox read; supplies draft/submit each need supplies read. Mentions
need the matching posting/reply grant. Do not bulk-select all consents for every
actor merely because all switches were exercised in discovery.

## Ordered external execution, only after approval

1. Complete stage 1 on the final source, local launcher/bundle checks, visibility
   decision, participant list and secret provisioning. Review manifest and scope.
2. Create/publish only the agreed HF target. Confirm exact bundle/source/version,
   expected visibility, CPU Basic, RUNNING, health/login and PILOT label. Anonymous
   app requests must not expose records or create accounts. Confirm callbacks
   reach the app and missing/wrong secret requests fail before linking.
3. Approve/register only the dedicated bot's webhook at the verified callback,
   with a new secret token and only needed update types. Inspect its current
   registration before changing it; stop if it belongs to another workflow.
   Do not reset/drop existing pending updates without separately agreed handling.
4. Enable baseline and Batch A; owner verifies actual private reply receipt and
   phone sign-in. A successful webhook HTTP response or `uncertain` handoff is
   not receipt. Then execute approved B–G batches, recording each checklist row.
5. Stop on missing receipt, wrong role/source, duplicate mutation, unexpected
   outbound call or changed build/boot. Pause affected pilot/inbound/delivery,
   preserve sanitized evidence and existing receipts; investigate locally.
6. Fix only actual findings on the review branch; repeat affected checks and
   required CI. Reconcile approved re-publication scope and repeat affected
   hosted acceptance on the new exact build. No feature expansion.

## Evidence record and stage-2 exit

For every applicable checklist row record: stable case label, UTC and Manila
execution time, full source SHA/version, Space commit, bundle and boot identity,
batch, synthetic role alias, selected switches/scopes, expected result, observed
source state/count/revision, actual user receipt, result (Pass/Fail/Blocked/Pending),
and sanitized evidence locator. Keep private identifiers, message bodies, codes,
passwords and cookies out of the record. Capture only redacted synthetic screens.

Use local-only for fault injection, rollback/concurrency and unavailable second
identity cases; do not mark them hosted Pass. Every row of the existing checklist
must either have evidence or a specific agreed exclusion. No blanket batch pass
from one successful command. Any untested capability remains disabled in the
proposed production activation list.

Stage 2 closes only after the owner accepts the named tested candidate and matrix,
all in-scope blockers are fixed, and excluded capabilities are recorded. Full T4.4
(group → meeting → room approval → outgoing update/reminder → revocation/rollback)
remains **Pending** under this private-only proposal. Durable restart/restore and
scheduled/group/provider transport need a separately scoped isolated persistent
pilot; a disposable private-webhook run cannot establish them.

## Pause, cleanup and later production gate

On failure first disable the affected pilot or inbound/delivery at the test host;
stop if a restart would erase evidence before recording safe results. Unregister
only the dedicated test webhook when the approved test window closes; do not
change production registration. Never replay uncertain handoffs, reset operation
IDs to retry a write, or recreate a meeting to recover its room child. Delivered
Telegram text cannot be recalled by a code rollback. Preserve receipt evidence
before any agreed reset; revoke test links and remove test credentials/target
only within agreed cleanup scope.

Stage 3 remains deferred. Before an explicit production instruction, assemble the
accepted SHA/version, selected production flags/accounts, exact-head CI/avatar
and review/rules/main checks, verified effective persistence, fresh verified
predeploy backup plan and monitoring/rollback. Then use only the canonical
main workflow: full verification → backup/version gates → code deployment →
actual merged-SHA/hosted source/version/health/persistence checks → separately
approved activation and receipt. No backup bypass or synthetic seed upload.
See [finishing handoff](TELEGRAM_FINISHING_HANDOFF.md#stage-3--explicitly-approved-production-release-and-selected-activation).

## Decisions and current blockers

- Owner has not approved creation/publication/visibility, test activation, bot
  registration or real replies. No approval is inferred from this plan.
- Existing account Pro entitlement and documented protected mode are verified;
  target availability, actual protected-mode provisioning, webhook reachability
  and scoped create/write access remain unverified. No purchase is authorized.
- Dedicated bot, participant identities and account secrets are not configured
  or verified. Obtain them through supported secret configuration, never chat.
- Separate isolated launcher/bundler and its local checks must be completed
  before publication. Existing preview cannot substitute.
- Hosted and phone acceptance are all Pending. No current provider connectivity,
  receipt, production persistence or release readiness claim is made here.
