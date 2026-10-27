# M4.4 — Travel reviewer papers decisions (v9.00)

This pilot stays off by default. It follows room approval (M4.3), merged in
[PR #512](https://github.com/jongsky25/css-is/pull/512). Per the agreed work order,
automated checks accompany each implementation; hosted ChatGPT acceptance of both
room and travel decisions comes last. Implementation is not hosted go/no-go.

## Setup after review and merge

Keep `CSS_MCP_ENABLED=1` and ordinary Travel enabled. Only for the named pilot,
set `CSS_MCP_TRAVEL_REVIEW_DECISIONS_ENABLED=1`. Existing review-request and
paper-submission flags do not grant this decision. Reconnect Office Connect in
ChatGPT and separately check the consent permission for selected reviewer travel
papers decisions (`travel:review:decide`). Existing grants do not gain it.

The current account must be the filing's selected reviewer and still belong to
the Administrative Section under normal directory policy. Technical admin rank
alone does not qualify. The reviewer must not own the filing. The traveller must
still have an active account. Use a synthetic filing ID from the signed-in
reviewer page; the pilot adds no broad inbox or private-paper read tool.

The readiness page lists the hosting switch, separate permission and these tools:

- `get_travel_review_decision_context(filing_id)` returns revision, state, round,
  draft-note count, permitted-decision booleans and signed-in source link.
- `prepare_travel_review_decision(filing_id, decision, expected_revision,
  operation_id)` accepts `approve` or `return_notes` and a stable operation key.
- `get_travel_review_decision_operation(operation_id)` recovers the original
  result on the same active connection with current reviewer authority.

Preparation saves only a private ten-minute preview. It makes no decision or mail
send. Open its confirmation URL in the same reviewer's signed-in browser. Inspect
the exact saved papers on the normal reviewer page, then confirm the exact
checklist, round, traveller recipient, decision and notes shown in the preview.
Returning notes requires drafts already saved in Office Connect; the MCP tool
accepts no note text, arbitrary recipients or document mutations. Changed papers,
notes, round, people or mail policy require fresh context and a new preview.

## Effects and boundaries

`approve` requires Open + Requested, no generation in progress, complete required
papers/resolved flags and no draft notes. It records papers Approved and leaves
the filing Open. The traveller separately marks Ready and hands in papers.
`return_notes` requires at least one current-round draft; it sends those exact
existing notes and records Changes needed, keeping Open. The traveller fixes the
papers and requests another review. Older drafts must be resolved in ordinary UI.

The native approval/feedback service joins the transaction containing the domain
and integration audits, minimal original receipt, unique permanent filing-source/
round identity and one mail marker. Same-key retries recover; two keys cannot
repeat a round. Receipt recovery does not rewrite later Ready/submission, edits
or another review round. Current selected reviewer, active connection/scope,
source reference/opened identity and original traveller are still required.

Model results contain IDs/status/counts/source links, never papers, financial
fields, note text, names or recipient addresses. Exact private display is escaped
in the signed-in browser. The pilot bounds a filing to 60 saved checklist rows,
100 flags and 100 historical notes, with at most 50 live previews and 10,000 total
keys per actor. Larger filings use ordinary review. Expired private preview
copies are pruned in bounded independently committed batches of 100 even when a
later request fails. Completed payload/snapshot copies are immediately cleared.

This records completeness of papers, not approval or payment of the claim.
No signing, official dispatch, generation, document edits, Ready transition,
physical paper-submission record, attachments or financial posting is performed.

## Result email and recovery

The normal `travel_review_result` message goes to the exact reviewed traveller
account email. Returning notes includes every exact reviewed note, as ordinary
review does; approval includes no notes. The email has a signed-in filing link,
no paper links or attachments. Normal feature/global-pause settings apply.
Disabled at confirmation is terminal `skipped_off` and logged; later enablement
never sends that notice. The confirmation transaction does not contact a provider.

The scheduler's travel-review tick runs the bounded worker (5 by default, maximum
20). Before a claim it rechecks the original active grant, selected reviewer,
traveller identity/recipient and complete post-decision source digest. Later edits,
Ready, another review round, reviewer reassignment or recipient changes cancel an
obsolete notice. Feature/pause off skips it; missing provider configuration is
terminal `not_configured`. These native travel notices have no room quiet-hour or
ICS behavior. The unique transport claim commits before external I/O.

Strict provider `sent=True` means reported acceptance, not inbox receipt or read.
False, exceptions or ambiguous outcomes become terminal `uncertain`; process death
or receipt-write failure leaves `attempting`, retired to `uncertain` after ten
minutes. Queued messages expire after 24 hours. Cleanup continues with delivery
flags off and clears private mail copies on terminal outcomes. Permanent marker/
source identity and minimal receipts remain for deduplication. A second worker,
restart or repeated confirmation never resends. No resend endpoint is added.
Review source and mail logs before any separately arranged notification.

## Automated evidence and hosted acceptance last

Automated checks cover both decisions, exact escaped browser review and 320px
without JavaScript, separate scope/refresh and SDK/HTTP dispatch, self/foreign/
revoked authority, stale papers/notes/recipient/policy, rollback, concurrent keys,
worker races, provider/process/result-write failures, retention and packaging.
Native travel review/request/submission behavior is checked alongside MCP pilots.

After the room and travel code is reviewed and merged, a named reviewer/operator
records hosted acceptance against the deployed version and exact tool names:

1. Reconnect a synthetic room approver; verify consent, readiness and plain-room
   approval. Check held hours, original receipt and normal requester notice.
2. Reconnect a selected travel reviewer; verify separate decision consent and
   context. Approve complete synthetic papers and confirm Open + Approved with
   the traveller as next actor. Inspect actual native message and mail log.
3. Draft synthetic review notes in ordinary UI; prepare `return_notes`, compare
   every word/recipient in the browser, confirm Changes needed and exactly one
   result email attempt. Fix and re-request; verify the old receipt stays original
   and the new round requires its own preview/confirmation.
4. Exercise stale preview, missing papers/drafts, non-selected/self reviewer,
   revoked permission, paused mail and a receipt recovery after later edits.
5. Record operator, deployed version, references, outcomes and mail states. Keep
   flags off if any authority, content, booking/decision or email assertion fails.

No hosted tests have been performed for this increment. Do not infer acceptance
from an enabled hosting switch or registered tool count. Roll back by disabling
`CSS_MCP_TRAVEL_REVIEW_DECISIONS_ENABLED`; turn off the room approval flag separately
if needed. Preserve operation/notice identity tables; do not reset mail states or
replay writes. Ordinary signed-in travel review remains available.
