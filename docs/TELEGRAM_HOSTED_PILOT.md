# T4.4 hosted pilot: execution runbook and evidence ledger

Status: **Blocked — live verification has not run.**
Prepared: October 25, 2026. Owner: Codex.

Detailed guides: [combined meeting/room flow](TELEGRAM_MEETING_ROOMS.md),
[change notices](TELEGRAM_CHANGE_NOTICES.md),
[channel choices and quiet hours](TELEGRAM_NOTIFICATION_PREFERENCES.md),
[private reminders](TELEGRAM_REMINDERS.md),
[switch and transport contract](TELEGRAM_T0_CONTRACT.md#switches-extraction-and-acceptance-handoff).

This is the next dependency-ready increment after T4.3.2. A merged implementation,
local rehearsal or green deployment workflow does not prove the Telegram workflow
works on the hosted application. Keep T4.4 blocked until the evidence below exists.
T5/T6 and other increments depending on T4.4 remain unready.

## Current evidence and blockers

| Check | Observation | Meaning / unblock action |
| --- | --- | --- |
| Candidate | `d68fc899dd343f94235c2d4b1e49b27d824ed98b`, release 8.77 | T4.3.2 is merged; record the actual hosted build separately. |
| PR CI | [Run 40199717541](https://github.com/jongsky25/css-is/actions/runs/40199717541): 7,132 tests in each full normal/shuffled order, metadata, dependency audit and Required checks passed at `2de4144` | Required implementation checks passed; this is not live verification. |
| Local rehearsal | 218 tests passed, no failures/skips, report `/tmp/telegram-t4-4-local-rehearsal.xml`, tested candidate `2de4144` | Combined flow, private/group boundaries, notices, preferences, reminders, revocation/restore and mobile forms use synthetic records and mocked Telegram. |
| Hosted reachability | 2026-10-25: HEAD to `https://equityinhealth-office-connect.hf.space/login` failed at CONNECT with HTTP 403 from the enforced proxy | No application response obtained. Configure supported HTTPS egress to the selected pilot host; do not bypass the proxy. |
| Workspace credentials | Runtime readiness current; no configured secrets/runtime variables/outbound identities. Expected deployment/admin/Telegram environment variables absent (presence checks only) | Configure credentials securely through the environment secret setup; do not paste them into chat, GitHub or commands. This says nothing about secrets stored in GitHub Actions or on the Space. |
| Approved test audience | No hosted test staff, owner, approver, bot or exact group/topic supplied | Identify the pilot environment and approved synthetic audience before linking or sending. Real staff/group details belong in a restricted operator record. |
| Deployment | Candidate [run 40201896975](https://github.com/jongsky25/css-is/actions/runs/40201896975) is in progress at handoff; actual candidate hosting/Telegram behavior remains unverified; previous [run 40198542493](https://github.com/jongsky25/css-is/actions/runs/40198542493) reported successful v8.76 deployment at source `3e88262`, Space commit `647d4bf8f0b8397140736ba67146ed1edbc45fda` and matching login version. That is not candidate v8.77 or Telegram pilot evidence. | Observe existing automatic deployment; do not claim the candidate is live from merge status. |
| Hosted configuration | Unknown; no flags changed by this work | Source defaults remain off. Inspect actual hosted configuration through an authorized operator before activation. |

The repository names the Hugging Face Space above as its deployment target.
That is a candidate destination, not confirmation that it is the approved pilot
environment. No real provider message, credential/configuration change, webhook
registration, hosted login or business write has been performed in this increment.

## Inputs and deployment gates

1. Name the approved isolated pilot environment and canonical HTTPS origin. If
   using the existing Space, first verify its intended use and that active bot
   links/groups and eligible queued work belong only to the approved synthetic
   pilot audience. Otherwise use an isolated pilot instance. Global feature flags
   must not unexpectedly release notices to unrelated linked accounts.
2. Assign aliases **PilotRequester**, **PilotGroupOwner**, **PilotApprover** and
   **PilotObserver** in the restricted operator record. The group owner must meet
   the Office Connect admin and Telegram administrator requirements. The approver
   must actually satisfy `rooms.is_room_admin` (active internal Administrative
   Section appointment); Office Connect admin role alone is insufficient. The
   requester may also be the owner if explicitly designated.
3. Identify one test bot and one approved exact group/topic. Record ownership,
   bot/owner/requester membership and the all-current/future-members audience
   consent privately. Do not put bot tokens, numeric chat IDs, member names,
   passwords, cookies or private message bodies in this repository or test artifacts.
4. Use the existing `.github/workflows/deploy-hf.yml` path, which serializes
   deployments under `hf-deploy` and reruns the complete release checks. Do not
   start a second deployment while one is active. Do not bypass its verified
   pre-deploy backup gate, alter the database carrier or restart the Space blind.
   Secure a current snapshot plus verified secondary copy before a hosted restart.
5. Record the workflow run, successful deploy outcome, source Git SHA from
   `build_info.json` / the signed-in `/ops` build panel, Space upload commit and
   observed application version. `/health` and `/login` alone do not prove the
   full source SHA or Telegram delivery. Confirm they agree with the candidate
   actually selected for the pilot, including any intervening release.
6. Confirm the real database/snapshot path, writable persistence and scheduler
   health. Observe a controlled recovery on the isolated pilot instance before
   allowing writes. Keep receipts, source identities, occurrence hashes and
   sending-marker fences intact. An older snapshot can lose later tombstones;
   exactly-once recovery is not claimed.
7. Configure the selected host/provider HTTPS access and credentials using the
   supported environment/hosting mechanisms. Test bot ownership with the official
   provider API without logging token-bearing URLs. There must be one webhook
   owner. Do not use getUpdates/polling concurrently with the webhook.

## Configuration and explicit consent

All ten independent two-way switches are default-off in source. A complete pilot
needs explicit operator configuration of inbound, delivery, linking, groups,
calendar read/create, room read/request, change notices and reminders. No switch
creates a delegated grant or source-sharing approval. Preserve the separate
`CSS_APPRISE_TELEGRAM_ENABLED` and existing email controls.

Configure the reviewed batch before establishing test links. A hosting
configuration change may restart the service; a snapshot hydration can rotate
connection generations, revoke grants and pause registrations. After any such
recovery, prove the fence and perform fresh private linking/group registration
through the UI. Never repair consent by editing SQLite rows or copying cookies.

Register exactly `POST /integrations/telegram/webhook` at the verified canonical
HTTPS origin using the configured webhook secret. Confirm the secret header and
wrong-secret denial without recording the secret. Invalid/unknown configuration
must fail closed. Check the provider webhook status without storing private
payloads or token-bearing URLs in evidence.

PilotRequester starts privately, signs in at `/account/telegram`, selects the
separate `calendar.read`, `calendar.create`, `rooms.read` and `rooms.request`
consents and confirms in the original private chat. PilotGroupOwner registers the
observed exact group/topic at `/account/telegram/groups` and consents to its stated
purpose/audience. Existing links get no new grants automatically. `/group_status`
in another group or sibling topic must not acquire that registration.

## Execute and record the complete workflow

Use synthetic titles and participants only. Choose a permitted working date and
available configured room slots; respect ordinary lead times, closure, holiday,
horizon and conflict rules. Agree a pilot window spanning the permitted room
booking lead time and actual reminder due time. Keep unfinished observations
pending across sessions; do not change hosted clocks or relax booking rules to
finish the pilot in one chat.

| ID | Action | Required observed outcome |
| --- | --- | --- |
| P1 | In the approved group/topic send `/meeting`; open its signed-in guide without JavaScript on a phone-sized screen. Select meeting fields and the initially unchecked room option. | Current actor/group context is bound; meeting and room clocks/durations are separate; no business write before confirmation. |
| P2 | Review the private preview, then send its expiring `/meeting_confirm CODE` privately. | Exactly one calendar entry, one linked room request and separate durable receipts. Room is requested/pending approval, with no booking held. Group sees no title, participant, reference, reason or private preview. |
| P3 | Reuse the original confirmation and recover `/meeting_receipt OPERATION_ID`. | Original result returns without a second calendar entry, room request or business execution. Acceptance by Telegram is distinguished from reading. |
| P4 | PilotApprover reviews and approves through the ordinary signed-in Office Connect room screen. | Actual eligible approver acts; source becomes approved/booked. Requester receives current private status; only anonymous availability may return to the original eligible group/topic. |
| P5 | PilotRequester edits the meeting time through the ordinary UI. Separately approve exact current source sharing in the group screen, then use `/group_calendar YYYY-MM-DD` to check the newly approved fields. | Current permitted private update arrives. Previously approved sharing is revoked on source edit; no stale shared fields leak. Fresh exact-version consent is required for any subsequent shared projection. Reapproval does not replay an already suppressed change notice. |
| P6 | Exercise a declined/withdrawn test request and a known room conflict after preview. Recover the partial outcome with a fresh room-only request when needed. | Pending/booked/declined states are truthful. A room failure can preserve the calendar, its partial receipt and one fresh room child; it never auto-approves or recreates the calendar. |
| P7 | Choose Telegram-only/Email-only and quiet hours at `/account/telegram/notifications`; separately opt into a reminder lead. | Existing calendar email field remains shared with My profile. Email-only suppresses new Telegram reminders. Due reminders defer without attempts; no delivery after occurrence start. Interactive replies stay immediate. |
| P8 | Observe one timed calendar occurrence and one approved own room booking becoming due; repeat scheduler runs and a controlled restart/recovery. | One handoff per occurrence; current source/authority on wake. If recovery pauses consent, old work cancels and fresh consent is required. Accepted/failed/cancelled/uncertain outcomes are distinct; no blind replay. |
| P9 | Change/cancel/reschedule a pending reminder source; revoke a test read grant or disconnect before delivery. | Old source/destination work is suppressed, pending work cancelled and sending claims fenced. Re-enabling or relinking does not replay cancelled/uncertain occurrences. |
| P10 | Remove a test member/bot, close a test topic, or revoke registration/source sharing in a controlled isolated case. | Permission and exact-topic fences deny stale routing. Definite provider rejection pauses automatic notices; a fresh recognized command can recover only after current consent/membership is valid. |
| P11 | Deactivate the synthetic requester through the authorized account screen, then try lookup/preview/confirmation/receipt and allow a queued notice to be considered. | Revoked/inactive actor is denied; no business execution or disclosure. Reactivation does not silently revive the old link. |
| P12 | Perform the rollback procedure below and verify the stopped state. | No new bot writes or automatic sends; normal Office Connect calendar/room approval remains usable. Evidence and tombstones are preserved. |

Record UTC execution times alongside Manila meeting/booking clocks. Capture
operation/source aliases and counts privately. For provider acceptance retain a
restricted message reference and sanitized outcome, not private content. Never
fabricate a Telegram update to the hosted webhook as proof that Telegram actually
delivered one. Do not induce real 429s or ambiguous sends by spamming or blocking
production traffic; use isolated fault injection and label that evidence clearly.

## Pause, cleanup and rollback

1. Pause the write switches (`CALENDAR_CREATE`, `ROOMS_REQUEST`) to stop new
   commits; pause change notices/reminders and delivery/inbound as required to
   stop routing and sends. Existing queued work can expire/cancel; do not promise
   that resuming a switch replays it.
2. Revoke test source sharing and pause/revoke the test registration through the
   signed-in group controls. Disconnect private test bindings while sending/link
   gates are paused; the browser disconnect path must still work.
3. Resolve or withdraw only the known synthetic requests/entries through normal
   Office Connect permissions. Do not delete receipts, overwrite the live DB or
   mass-clear queues. No bulk replay of confirmations or uncertain attempts.
4. Keep existing persistence, backup and restore hooks. A code rollback does not
   reverse business writes or erase additive metadata. Record the selected build,
   configuration state and rollback time, plus any acceptance still in flight.
5. Confirm stale confirmations and revoked users fail, new automatic delivery is
   stopped, and ordinary signed-in calendar/room workflows continue. Stop the
   test webhook only if this pilot owns it and there is no other intended consumer.
6. Preserve sanitized evidence and privately reconcile uncertain provider sends
   before any fresh activation. Leave independent email and digest controls as
   they were unless the pilot explicitly changed its own account choices.

## Evidence ledger and completion rule

| Evidence | Status / reference |
| --- | --- |
| Approved pilot destination/audience and test role checks | Not supplied |
| Deployed source SHA / Space upload commit / build version | Not observed from host |
| Backup/persistence/recovery proof | Not observed from host |
| Webhook owner, health and wrong-secret denial | Not executed |
| P1–P6 group → preview → calendar → room decision → correct updates | Not executed |
| P7–P9 preferences, quiet/reminders, duplicate/restart/source/revocation | Not executed |
| P10–P11 group lifecycle and deactivated account denial | Not executed |
| P12 rollback, stopped state and normal UI operation | Not executed |
| Local mocked rehearsal | 218 passed; not live evidence |

Only mark **pilot verified** when all required hosted observations have execution
times and sanitized references, the actual deployed SHA is recorded, rollback has
been exercised, and no unresolved disclosure, duplicate execution or recovery
failure remains. Otherwise retain **blocked** with the exact missing inputs and
unblock action in [the plan](TELEGRAM_TWO_WAY_PLAN.md). Do not begin T5/T6 work by
substituting this runbook or local tests for T4.4 verification.
