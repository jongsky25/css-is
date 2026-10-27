# Work arrangement filing pilot (v8.92)

M3.8 adds `get_my_work_arrangement_context`,
`prepare_work_arrangement_request` and `get_work_arrangement_operation`, disabled
by default. It follows [PR #503](https://github.com/jongsky25/css-is/pull/503),
merged at `7e833bbb6350cad34f1e6a00c38f4ac6951dbd0f`. Hosted acceptance is pending.

## Exact action and consent

Separate optional `work_arrangements:request` consent prepares one **new own
Pending filing** for an open or administratively reopened half-month period.
Existing grants/default read scopes are unchanged. Other write flags/scopes
cannot authorize this action. Current active-account eligibility matches the
normal filing screen. Director filings that auto-approve in the normal service
must use that screen; this pending-only pilot cannot make an approval.

Read context with an exact `period_start` (YYYY-MM-01 or YYYY-MM-16). It returns
that period's label/deadline, open/reopened state, own live-filing/No AWA flags,
arrangement/weekday choices and initial chain-notice recipient count. No other
person's filing, note or approver identity/address is returned.

Preparation accepts only `period_start`, `arrangement` (`REG`, `CWW`, `WFH`),
`weekday` (strict integer Monday=0 through Friday=4 for CWW/WFH; absent/null for
REG), `note` (optional plain text, max 1000 characters) and one random 16–80
character `operation_id`. Invalid dates/codes, unsupported fields and boolean/numeric-string weekdays
are rejected rather than coerced. Notes are
trimmed; line breaks/tabs are allowed and other control characters rejected.
There is no user override, status, decision, supersedes/replacement ID, effective
date override, signature, annex export, No AWA override, whereabouts report,
calendar relay, cancellation or withdrawal input.

This files a request for another person's approval. It does not change a
schedule currently in force. Existing approved or Pending filings block a new
filing for that period; the pilot does not invoke the ordinary change flow.
No AWA is preserved, never silently removed. REG nominates no alternative day.

## Shared policy and exact browser review

`storage.work_arrangement_new_fields` is the shared side-effect-free validator
used by ordinary creation and MCP. It reuses period/open/reopen/deadline, No AWA,
existing filings and boundary-week rules. A weekday recurs through the period.
Where an earlier adjacent filing owns a shared week, the canonical service may
defer the later filing's effectivity; an earlier filing cannot take priority
away from a later live filing automatically. The browser shows the computed
effectivity and explanatory note, plus nominated dates before normal holiday
exclusions. These are proposed dates subject to a separate approval and ordinary
schedule display rules.

The signed-in owner reviews exact period/deadline/reopened status, arrangement,
weekday, effectivity, nominated dates, full note, current requester identity,
coverage advisory and initial approval-email recipients/addresses. Thin section
coverage remains advisory and never by itself forbids filing. A changed advisory
requires a fresh preview so the reviewed warning stays current. The preview
explains that normal own-hub, authorized approval-queue and permitted team/bureau
schedule/annex visibility apply; schedule grants do not grant decision authority.
Later membership/grant changes can change visibility.

The preview also shows the email feature state, initial recipients and the normal
message content: requester name, period, arrangement type and authenticated
approvals-inbox link. The initial email does not include the note or weekday.
Normal weekly approval digests and later decision emails remain separate events
with existing controls. Zero chain recipients produces a warning and retains the
normal orphan-request fallback; it does not invent or email an administrator.

The ten-minute preview binds actor, current grant/audience, exact payload/hash,
current requester/directory identity, period reopening, effective dates, coverage
advisory, routing and mail feature state. Confirmation uses the shared bounded
three-field same-origin CSRF POST form and supports a 320-pixel phone screen
without JavaScript. Every condition is rechecked under the database writer lock.
No model-provided source revision is invented for a new filing.

## Atomic effects and recoverable receipts

`storage.create_work_arrangement(..., commit=False)` requires a caller-owned
transaction and refuses auto-approved Director filings before insertion. The
ordinary `commit=True` path retains its existing auto-approval behavior. The MCP
path atomically commits the new Pending record, normal filing audit, body-free
integration audit, original source identity, completed receipt and one queued
initial email per bound chain recipient. No external I/O occurs in that
transaction. Any failure rolls back all effects.

Same-key retries and browser races return one original receipt. Different keys
racing for one person/period commit at most one live filing through shared rules
and database guards. A lost response is not proof of no filing: recover the same
key and inspect its source before another key. Replays preserve later ordinary
approval/denial/withdrawal/change decisions and never resend notices.

The receipt reports original `filed_status=pending`, next-party role, initial
recipient count, current initial-notice state counts and source/confirmation
links. It does not disclose period, weekday, note, directory names or addresses.
Pending does not mean approved; queued does not mean delivered. The next-party
role is the chain approver, or the existing orphan fallback when no chain
recipient exists.

The exact source page is owner-only, tied to the operation key and original
record identity, and shows current status/note/effectivity/decision with a normal
hub link. Another approver uses ordinary queues, not this owner-only page.
Receipt recovery requires the same current active grant/scope/resource and
current source ownership. The ordinary signed-in source view remains available
to its owner after disconnect or pilot disablement; it gives no mutation rights.
Source identity cascades on record deletion while the operation tombstone
remains. Neither recovery nor an old source URL can bind to a reused numeric ID.

## Durable initial approval email

`work_arrangement_delivery.run` handles five queued recipients per scheduler tick
(maximum batch 20). It rechecks original active connection/source ownership,
Pending state, unchanged filing content, current chain/OIC recipient membership,
approved address/name and requester name, and payload digest. Obsolete or
revoked work cancels before sending. It uses the normal `awa_pending_message`
composer and signed-in inbox link, without automatic approval links.

The `awa_approval` feature/global pause and configured transport apply. Disabled
mail becomes `skipped_off`; missing transport becomes `not_configured`. Before
network I/O the worker commits one unique `attempting` marker. Concurrent workers
cannot claim it twice. A true sent result means transport acceptance, not reading
or approval. False, exceptions, crashes and failure recording a transport success
never requeue. Stale attempting markers become `uncertain` after ten minutes.
No resend endpoint is added. Ordinary UI filing emails, digests and later decision
messages retain their existing paths; the new action never invokes the UI route's
synchronous sender.

Mail payload copies clear on terminal outcomes, stale-attempt cleanup and queued
expiry (24 hours). Cleanup runs even while sending is disabled. Expired/completed
preview/snapshot text clears in bounded batches of 100; hashes, source identity,
minimal result and delivery states remain for idempotency. Normal records/audits
retain normal retention. Limits are 50 live previews and 10,000 total keys per
owner plus the shared process-local 30/minute action limiter. Multi-worker
hosting needs coordinated rate limiting; writer transactions protect claims and
filings themselves.

## Operator acceptance and rollback

1. Deploy v8.92 or newer after local release/import-closure and MCP/domain/mail
   checks. Record SHA and named synthetic requester/chief/OIC/fallback actors.
2. Finish hosted write acceptance before a real requester pilot. Enable
   `CSS_MCP_ENABLED=1` and `CSS_MCP_WORK_ARRANGEMENTS_ENABLED=1`, reconnect with the
   new consent and refresh tools. Other flags and old grants stay independent.
3. Compare fresh context and exact preview with ordinary filing: valid half-month
   period, open/reopened deadline, REG/CWW/WFH weekday rules, notes and visibility,
   boundary-week effectivity and advisory section coverage. Check No AWA,
   duplicate/approved filings and Director refusal. No record/mail before confirm.
4. Confirm once and compare Pending row, period/weekday/effectivity/note, identity,
   audits, receipt, initial notices and ordinary approval queue. Verify no approved
   schedule or replacement. Check owner-only source versus another approver and
   technical admin; ordinary queue authority remains unchanged.
5. Exercise stale routing/OIC/directory, reopening closure/deadline rollover,
   boundary-week changes, expiry, CSRF/Origin/session/grant/scope loss, competing
   keys and duplicate confirmation. Inject final-audit failure; no partial filing
   or notice may remain. Verify later separately authorized decisions survive
   receipt recovery and deleted/reused source IDs never rebind it.
6. With synthetic transports check two recipients, concurrent workers, feature,
   pause, configuration, lost recipient/grant, changed record, timeout/crash and
   failure recording send success. Never automatically make a second attempt.
   Distinguish initial notice states from separate ordinary digests/decisions.
7. Verify mobile without JavaScript, escaped text, preview/mail cleanup, capacity,
   source links and minimal receipts. Record IDs/keys/states/timings. Local tests
   are not hosted acceptance and do not enable a flag.

Rollback: disable `CSS_MCP_WORK_ARRANGEMENTS_ENABLED` and restart if needed. New
MCP previews/confirmations/receipt recovery and initial email sending stop;
bounded cleanup and normal own source access continue. Existing filings and
separately authorized decisions, digests and ordinary follow-up retain their
usual behavior. Rollback never cancels a filing, reverses a decision or replays
an attempted notice. No hosted activation is claimed by this implementation.
