# Travel paper submission record pilot (v8.89)

This default-off M3.5 pilot adds `get_my_travel_submission_context`,
`prepare_travel_filing_submission` and `get_travel_submission_operation`.
Hosted write acceptance remains pending. It follows travel review requests
merged in [PR #500](https://github.com/jongsky25/css-is/pull/500), commit
`0ae91f1e8960512ae87c93cff91f1fb42295a846`.

## What this records

Separate optional `travel:filing:submit` consent permits an owner to prepare a
record of **paper handover that already happened**. It changes an existing Ready
filing to Submitted only after the registered owner explicitly confirms the
statement in the signed-in browser. This matches the ordinary travel screen's
paper-submission meaning. ChatGPT does not hand over, print, sign, send or upload
papers. This record does not establish office receipt, claim approval or payment.

The owner must already have completed the normal Ready step. The current
checklist must remain complete, with no running generation or unresolved flags.
The MCP pilot additionally rechecks the current review policy at confirmation:
if paper review is currently required, the saved review must be Approved. The
normal `mark_submitted` UI service and its existing default behavior remain
unchanged; this pilot applies that current-policy guard before calling it under
the writer lock. The action does not mark Ready or make a review decision.

Read, draft and review-request scopes do not authorize paper submission. Default
OAuth scopes and existing grants are unchanged. Other write flags are not needed.
Technical admin or reviewer access cannot record another traveller's handover.
The filing must belong to the current account and must not be purged.

## Input and browser confirmation

Use `get_my_travel_submission_context(filing_id)` first. Under this same explicit
scope, it returns current status, review/readiness booleans, exact update stamp
and normal source link, without title, document links, notes or amounts. Its
`ready_to_record` value is system eligibility, not proof that papers were handed
in. The model must not infer a physical event from that boolean.

Preparation accepts a positive 64-bit filing ID, the exact `expected_updated_at`
string (1–80 characters) and one random 16–80 character operation key. Unknown
status, financial, file and model-supplied handover-attestation fields are
rejected. Physical attestation comes only from browser confirmation, never an
argument chosen by the model.

The private preview shows the filing reference/title/dates, current source stamp,
Ready → Submitted, review requirement/state and required print checklist with
copy counts and signature reminders. A link opens the normal print list and
saved papers. The owner must read the explicit statement that the required
papers have already been physically handed in, then press **Confirm: record my
paper submission**. The next responsibility is the traveller's follow-up with
the receiving office, matching the existing guidance; no receiving officer or
confirmed receipt is invented.

## Atomicity, authority and recovery

The ten-minute preview binds owner, original connection, normalized IDs/stamp and
a full source/paper/flag/review snapshot digest. Document links and financial
fields participate in the digest without being copied into preview metadata or
returned to MCP. Same-second edits are detected even if `updated_at` did not
advance. Origin, CSRF, registered session, exact preview digest, grant/scope,
switches, ownership, Ready state, completeness and current review policy are
rechecked inside the writer transaction.

`travel.mark_submitted(..., commit=False)` joins the caller's transaction, while
its ordinary UI keeps default commit behavior. The Submitted state/timestamps,
paper-handover audit, integration audit and durable completion receipt commit
together. A failure rolls all effects back. No email, document, relay, stock or
financial operation occurs. Original source identity is retained by a foreign
key and reference/opened timestamp checks; a replacement or purged source cannot
be rebound to the receipt.

The completed result reports original Submitted status/time, the recorded owner
attestation, traveller follow-up role and source. It returns no document URLs,
notes or financial values. Exact retries, duplicate confirmations, refresh and
lost-response recovery return the original result without recording again or
overwriting later source changes. Independent keys on one Ready snapshot commit
at most once. A timeout/unavailable result is not proof of failure: recover the
original operation/source before creating a replacement key, and never silently
retry a new source stamp.

Completed/expired preview copies clear, with expiry cleanup in independent
batches of up to 100. Hashes, original keys, identity and receipt markers remain;
ordinary travel/audit retention is unchanged. Limits are 50 live previews and
10,000 total operation keys per owner, plus the shared process-local action
limiter (30/minute). Multiple workers need a shared limiter before relying on
that cap across instances; writer transactions protect the actual transition.

## Operator acceptance and rollback

1. Deploy v8.89 or newer after release, import-closure, MCP and travel checks.
2. Finish hosted write acceptance before activating the named traveller pilot.
   Enable `CSS_MCP_ENABLED=1`, `CSS_MCP_TRAVEL_SUBMISSIONS_ENABLED=1` and normal
   Travel. Reconnect/reconsent to the separate paper-submission permission and
   refresh the tool catalog. Other write flags remain independent.
3. Use a complete synthetic Ready filing with its required review approved, or
   the intended review-not-required policy. Read the context stamp and compare
   every private preview/checklist field to the normal filing and print list.
   Verify no state/timestamp or attestation before browser confirmation.
4. Confirm only for a real pilot handover or an explicitly synthetic test record:
   one Submitted transition, timestamp, paper-handover audit and receipt. Compare
   the source and result. Verify unchanged review, documents, financial values,
   stock and email queues; the result must not claim office receipt or payment.
5. Exercise refresh between preview and confirmation, duplicate/lost responses,
   same/different keys on one snapshot and final-audit failure. At most one
   transition may commit and a failure must leave Ready/no submitted timestamp.
6. Test changed stamps and same-second papers, missing documents, open/rejected
   flags, running generation, Open/withdrawn/submitted states, changed review or
   policy, owner/grant/session loss, disabled flags, expiry, tampering and purge.
   The pilot must never automatically mark Ready or bypass current review policy.
7. Record deployment SHA, named roles, exact synthetic source/stamp, keys, timings
   and outcomes. Local tests do not supply hosted acceptance or proof of an
   actual handover; the browser statement records the owner's assertion.

Rollback: disable `CSS_MCP_TRAVEL_SUBMISSIONS_ENABLED` and restart if needed.
MCP previews/receipts become unavailable while ordinary travel records retain
normal authority and behavior. Disconnect revokes the connection immediately.
Rollback never silently reverses a Submitted status or deletes the handover
record/audit. No live activation is claimed by this increment.
