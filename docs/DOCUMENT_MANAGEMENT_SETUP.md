# Documents: implementation and acceptance setup

This implements the D1–D11 application paths behind **disabled** switches. It is not D12
launch acceptance. No live files, mail, spreadsheet imports, accounts, or deployment settings
were changed during implementation. The production relay has **not** been implemented or
validated against a chosen provider; the application includes an authenticated relay client,
operation protocol, and fake-adapter tests. The exact Drive/OCR/signing/mail provider choices
remain O06–O08 gates. Do not present those integration contracts as working production services.

## Safe evaluation

1. Back up the database with the repository's SQLite backup tooling. Use a copy for acceptance.
2. Run `storage.init_db` on that copy. The additive schema is repeatable. All existing APIs retain
   their commit behavior unless explicitly passed `commit=False` by Documents.
3. Agree the named workflow/grant administrator with the owner. Bootstrap that **existing active
   account** explicitly:

   ```sh
   python tools/configure_documents.py --db /path/to/acceptance.db --grant-admin 123 --reason 'Named by records owner for acceptance'
   ```

   This records authorization in the business event and platform audit logs. It changes neither
   switch and does not infer grants from the technical-admin role. Other records/signatory grants
   are managed on `/documents/rules` by the designated grant administrator.
4. Set `documents.enabled=1` on the acceptance copy through `storage.set_setting`. Keep
   `documents.sending_enabled=0` until deliberately testing delivery with authorized recipients.
   Both settings default to `0`, including on repeat migration. Never enable the production
   module solely because the local tests passed.
5. Run the application with `CSS_DB` pointing at the copy. Office → Documents shows the registry.
   All authenticated write forms carry a session-bound CSRF token. Service actions reload active
   accounts and resolve current grants/directory/OIC authority, rather than trusting posted roles.
6. Configure versioned rules, timing, release and closure evidence in Rules and policies.
   Missing settings fail closed for the affected transition; no default signing authority,
   official mailbox, deadlines, retention period or sender is silently selected.

## What is implemented

| Increment | Application implementation | Acceptance still required |
|---|---|---|
| D1 | Additive tables, annual Manila numbering, serialized transactions, optimistic revisions, explicit scoped grants, directory/OIC checks, shared visibility, append-only events and platform audit | O02/O05/O10 policy sign-off and deployment-copy migration |
| D2 | Incoming/outgoing intake, receipt/reference metadata, missing-scan handling, verification/correction, restricted views, Drive link validation, duplicate warnings | Representative office intake and sensitive-submission policy |
| D3 | Declarative rule conditions, priority/conflicts, immutable successor versions, activation/disable/restore, preview, explicit reevaluation, assignments, directives and lead reconciliation | Initial rule catalog, authority limits and unmatched fallback sign-off |
| D4 | Durable immediate notice intent, in-app queues, access-checked email, send feature/preview/CLI registry, retries with evidence, unknown-operation handling | Scheduler cadence, real delivery and revoked-access acceptance |
| D5 | Explicit/default working-day dates, buffered contributor dates, internal milestones, 3/1/due notices, collapsed elapsed reminders, urgency, overdue escalation and deadline history | O03 exact timing/anchor decisions; confirmed holiday years |
| D6 | Numbered independent outgoing drafts, many-to-many relationships, directory-authorized review routes, exact-version approval, material invalidation/minor lineage, approvals inbox | Authority and minor-change classification policies |
| D7 | External signed-copy recording; signatory-only durable stored-signature request, source fingerprint and own-identity confirmation, result lineage | Implement/configure production signing adapter, final placement/preview format and live visual validation |
| D8 | Release checklists, existing-email/physical evidence, direct-send operation contract, recipient outcomes, acknowledgment, duplicate gates and read-only receipt reconciliation | Implement/configure official sender adapter and real recipient-level evidence |
| D9 | Bounded relay extraction request, sanitized untrusted suggestions/excerpts, explicit field confirmation, no persistent extracted content, manual fallback | Implement/configure PDF/Docs/OCR adapter and test scanned/ambiguous/protected/oversized files live |
| D10 | Configured closure evidence, mandatory-contribution checks, released-reply gate, reopening, receipt linking, merge preview and correction with retained history/access intersection | Owner acceptance of type-specific evidence and correction procedure |
| D11 | My actions/register/verification/review/release/unassigned queues, overview metrics, scoped record search/CSV, calendar candidate check and explicit link/private reminder | Role-based user acceptance and complete bureau-wide browser journeys |

D0 is not falsely marked complete. Open policy values in the plan remain unresolved. D12 and
D13 remain unimplemented. The external adapters and live checks above are **first-release
blockers**, not deferred features or optional scope. The development implementation is ready
for review and configuration; it is not a claim that all D1–D11 acceptance criteria have passed.

## Policy semantics

- Rule fields are `type`, `field` (subject/sender/type), `keywords`, `mode` (any/all/exact),
  `priority`, proposed `lead_id` / `lead_unit_id`, contributing `unit_ids`, `assignees`, and `policy`. No executable expressions are accepted.
- Conflicting leads are never silently resolved by priority. All proposed people receive scoped
  preverification access and notices. A concerned officer confirms the lead. Equal-priority
  conflicting policy values remain unset and are shown as conflicts.
- Unmatched records are visible to their submitter and authorized verifying officers. No named
  fallback recipient is invented; directory Director/OIC and explicitly granted records officers
  are included where their authority and access allow.
- `default_days` requires `anchor` (`receipt` or `registration`). `buffer_days` proposes an internal
  working-day deadline. Explicit weekend/holiday dates stay unchanged. Officers set/extend external
  dates; lead/officers adjust internal milestones with reasons.
- Deadline scheduling requires `cutoff`, `reminder_time`, `escalate_chief_days`, and
  `escalate_director_days`. Times are Manila wall-clock times. The escalation values are calendar
  days after the due date; advance reminders use working days. Reminders collapse elapsed milestones,
  and are deduplicated by record/assignment, date, recipient, milestone and reopened cycle.
- Mark holiday-year coverage explicitly with `documents.holidays_confirmed.YEAR=1` only after
  review. Having one holiday in a year does not prove full coverage.
- `release` and `closure` list evidence labels. `signature_required` and `ack_required` must be
  explicitly configured before release. The closure label `released_reply` additionally requires
  linked outgoing replies to be released; all mandatory contributions must be completed independently
  of evidence text. Do not infer a document's actual action from unreviewed spreadsheet blanks.
- Restricted access is explicit even for Director, records officers, signatories and workflow admins.
  Manage access before assigning a restricted record. Changing app visibility never changes Drive ACLs.
- A minor revision requires an officer's classification and explanation. It retains an annotated
  approval lineage, but **always invalidates the old signature**. Material edits, changed directives,
  and policy reevaluation invalidate approval/signing.
- Merge leaves original records, receipts, files, assignments and dispatches in place, with a canonical
  redirect and readable original authored timeline. Canonical readership becomes the intersection.
  Reversing a merge retains restricted access and requires reconciliation; no history is deleted.
- Calendar links live in Documents. New private calendar reminders have the generic title
  “Document follow-up” with no document title/number/link, so later document-access revocation does
  not leave private correspondence content in calendar audiences. Rescheduling is explicitly handled
  in Calendar. CSS surveys are never created automatically.

## External relay contract (must be implemented before live use)

Set `DOCUMENTS_RELAY_URL` to the reviewed HTTPS endpoint and `DOCUMENTS_RELAY_SECRET` through the
normal secret configuration, not in the repository. The client sends:

```json
{"ts":"epoch_seconds","payload":"canonical JSON string","signature":"hex HMAC-SHA256(ts + '.' + payload)"}
```

The signed payload contains `action`, durable `operation_id`, authenticated `actor_id`, and the
operation-specific metadata. The production relay must verify the HMAC, reject replay outside a
bounded timestamp window, implement durable deduplication by operation ID, and enforce its own
service identity and resource limits. A shared secret is not permission for staff to use another
person's signature.

Every reply echoes `operation_id`. Client timeout is 45 seconds, metadata responses are bounded
at 1 MiB, source requests at 20 MiB. Redirects are not followed. Never send extracted text, signature
bytes, or document binaries back for storage in the app. The relay must bound file types, pages,
processing time, and transient retention, reject encrypted/unreadable inputs with actionable errors,
and **never execute instructions found inside a document**.

| Action | Required response / guarantees |
|---|---|
| `inspect` | `accessible:true`, `file_id`, stable exact `fingerprint`, integer `size`; access is for the adapter identity only |
| `extract` | `state:"confirmed"`, `suggestions` (subject/sender/references/type/due_date/keywords), `excerpts`, `warnings`; OCR/model provider and transient-content deletion must be validated |
| `sign` | Compare source fingerprint atomically before effect. Apply only authenticated actor's own authorized signature. Return confirmed `source_fingerprint`, `signatory_id`, signed Drive `url`, signed `fingerprint`, evidence. Preserve original. |
| `dispatch` | Compare fingerprint atomically before send; use configured official sender and persist immutable receipt per recipient. Return confirmed fingerprint/sender and `recipients:{address:{outcome:"accepted" or "failed",evidence}}`. Acceptance is not recipient acknowledgment. |
| `status` | Read the prior operation's durable receipt **without repeating the effect**. Return the same confirmed sign/dispatch result. No result/timeout remains uncertain. |

Set `documents.official_sender` to the reviewed mailbox. A URL alone is insufficient version evidence.
The travel relay is **not** used as if it implements these contracts. Stored-signature application is
not represented as certificate-based digital signing.

A timeout, crash after claiming an operation, malformed result, or recipient ambiguity is visible as
`running`/`unknown`, blocks edits and repeat operations, and requires reconciliation. Query the service
receipt first. Only a pending unexecuted request may be cancelled; a new request after uncertainty
requires recorded evidence of no external effect. Partial-success retries may target only recipients
without accepted/unknown outcomes for that version. Official dispatch evidence lives independently
of the notification `email_log` retention.

## Scheduler and recovery

`python send_reminders.py --documents --dry-run` previews notice delivery without changing records.
The existing scheduled-job registry also includes `documents`/`job_documents`; wire its cadence for
prompt delivery during acceptance. Notice generation and external operations remain quiet when the
module is off; sending also requires `documents.sending_enabled=1` and the mail feature setting.
Immediate notices are enqueued in the originating transaction; in-app tasks do not depend on email.

Delivery attempts are claimed before network I/O. Successful notices are not resent by repeated runs.
A crashed/ambiguous notice is visible for a human to reconcile/retry; the application does not promise
exactly-once delivery from a non-idempotent SMTP service. Access is rechecked before delivery, and email
contains only an authenticated app link. For notices the configured directory email is preferred.
Official dispatch uses the stronger durable operation/recipient protocol above.

Emergency rollback: disable sending, then disable module writes. Existing permitted records remain
readable. Preserve operation IDs, official sequences and event history. Restore metadata using SQLite
backup procedures and separately check original/signed Drive artifacts. Reconcile external receipts
before replaying anything. No new correspondence retention/purge rule is enabled.

## Verification evidence

Synthetic tests live in `tests/test_documents.py` and `tests/test_documents_routes.py`. They exercise
concurrent annual numbering/year rollover; rollback including audit/notices; restricted/direct-ID
access and spoofed roles; OIC scopes; stale edits; rule conflicts; holidays and explicit Sunday dates;
version/approval/signature gates; complete outgoing release/ack/closure; unknown-send receipt queries;
untrusted transient extraction; merge/correction; calendar confirmation; delivery access revocation;
CSRF and disabled/read-only HTTP behavior. No test uses live external recipients.

Chromium checks on a separate synthetic database: register incoming → verify → browse register;
rule page rendering; no horizontal overflow at 390px; desktop register at 1280px.
`qa_preflight.py` is green. Full-suite baseline and final counts are recorded in the implementation PR.
Live external-service acceptance, production-directory inspection, file-format visual validation and
D12 launch rehearsal have not been performed.
