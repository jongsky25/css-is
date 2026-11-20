# Advisory implementation design and first slice

Planning checkpoint: November 20, 2026. Continues draft [PR #633](https://github.com/jongsky25/css-is/pull/633)
at `de8bda2`; inspected main is `3eea227` (also the plan's application baseline).
The [scope and workflow plan](ADVISORY_TRACKER_INTEGRATION_PLAN.md) remains authoritative.
This document records the original planning design. The owner subsequently said **“start
building”**, authorizing slice 1. See [implemented boundaries](ADVISORY_DRAFTS.md).
P2/P3 recommendations are used as first-slice implementation defaults; no broader policy
acceptance, merge, deployment or notification authorization is inferred.
Everything stays in Office Connect. No Sheet import, transition, reconciliation,
synchronization, external file editing, or operational cutover work is proposed.

## Policy decision record

The following package was presented during planning. P2/P3 are the working defaults for the
authorized first slice. P1/P4/P5 remain pending for dependent implementation; no blanket
acceptance of the five-policy package is recorded.

| ID | Recommended choice | Dependency |
|---|---|---|
| P1 | Initiator plus explicitly authorized releasing staff may issue after Director approval. Activity-management or general Documents assignment alone confers no issuing authority. | Issuance slice |
| P2 | Reserve the existing stable number on first save; call `seq_date` reservation date. Store actual `issued_at` separately, using the application's local timezone for display. Never renumber existing records. | First slice numbering labels/contract |
| P3 | First build exposes one advisory per existing activity. Use a separate advisory ID and nullable activity association in the new model so future standalone/multiple support does not require artificial calendar events; keep a unique activity association for now. | First slice schema and entry points |
| P4 | Approval covers “all active internal users” intent. Resolve and freeze eligible addresses at issuance. Audience mode or explicit external-address changes require renewed review; ordinary roster changes do not. | Review fingerprint and issuance |
| P5 | Director approval is sufficient without a separate signature. Only current formally designated OICs may substitute; no preparer self-review/self-approval or same-person Chief/Director exceptions. Ambiguous/vacant/conflicting routing blocks submission until explicit reassignment. | Review and release policy |

P5 defines no new delegation mechanism. Existing seats must be checked for the owning division
and selected role, and their evidence recorded. No blanket Director substitute for the Chief stage.
The five original choices are the only owner questions; settled scope and roles are not reopened.
The authorized first slice uses the recommended P2/P3 defaults. P1/P4/P5 do not prevent
preparing the foundation design, but prevent implementing their dependent behavior.

## Service map and reuse boundaries

Paths refer to inspected source, not verified production configuration.

| Existing service | Evidence and proposed use | Necessary extension / limitation |
|---|---|---|
| [Activity advisory](../activity_advisory.py), [routes](../activity_advisory_routes.py), [renderer](../advisory.py) | Keep defaults, normalization, layout validation, `format_number`, PNG/PDF rendering and activity entry. | `save` commits internally and rolls back on allocation conflicts; cannot be nested in a new multi-record transaction. Extract a caller-transaction variant, preserving the compatibility wrapper. Add expected-revision checks. Public routes currently render mutable latest fields. |
| [Documents](../documents.py) `register_in_transaction`, `check`, `mutate`, `finish` | Reuse outgoing document identity, transaction/revision checks, review records and audit. | `review_route` selects routine OR Director; `review` can directly approve. Add a staged advisory policy to this shared service, enforced on generic routes too. Never simulate Chief endorsement by temporarily setting final approval. |
| [Permissions](../documents_permissions.py) `actor`, `seats`, `director`, `review_authority`, `can_view` | Re-read active account, directory scope and current OIC seats on every action. Reuse restricted access. | Existing routine review permits bureau authority; `can_release` allows officers/assignees. Advisory stage and issuer predicates must narrow these rules. Draft visibility cannot default to bureau visibility. |
| [Work review](../work_review.py) `prepare`, `require_current`, `invalidate` | Reuse exact-version/source-digest concepts and existing consolidation behavior when actually applicable. | These functions concern Work consolidation, not a general two-stage review engine. `prepare` is a no-op without a case; a case snapshot does not cover advisory audience. Add an advisory packet binding to shared review checks, rather than creating fake consolidation tasks. |
| [Work discussion](../work_discussion.py), [Work storage](../work_storage.py) | Reuse parent/reply relationships, permission checks and append-only comment edit versions. | Requires a genuine Work case and matching access. Add revision/packet binding and concern resolve/reopen events; replies alone never resolve concerns. Do not duplicate comment bodies in a second table. |
| [Document storage](../documents_storage.py) `transaction`, `event` | Reuse `BEGIN IMMEDIATE`, `document_event` append-only history, `document_review`, notices, jobs and dispatch records. | `document_event` is audit history, not calendar linkage. Existing file versions require Drive-oriented URL/file ID fields. Extend storage with an explicit local-artifact backend; do not invent Drive IDs. |
| [Action queues](../documents_actions.py) | Reuse shared queue/filter/count path and link to the canonical advisory detail. | Add Chief endorsement, Director approval and issuance labels; Chief stage must never appear “approved awaiting release.” Avoid a second independent inbox/count implementation. |
| [Notices](../documents_notify.py), `documents.notify` | Reuse durable notice keys, permissions at send time and sending feature gates. | `notify` currently fans out to officers/access holders and `finish` calls it for every action. Add explicit advisory trigger/recipient policy, quiet draft saves, and advisory detail links. Do not inadvertently email everyone with access or every comment edit. |
| [Operations](../documents_operations.py) `release_gate`, `queue`, `persist_dispatch` | Reuse exact approved-version checks, operation identity and recipient outcome records. | Current dispatch requires Drive metadata, limits each operation to 100 recipients, and sets released only when all are accepted. Add local artifact adapter and an issuance authorization snapshot before sending; issuance is independent of delivery results. |
| [Jobs](../documents_jobs.py), [external runner](../documents_external.py) | Reuse durable lease ownership, bounded execution, recovery state and stale-worker rejection. | Runner is not a durable queue. Existing recovery assumes receipt-capable operations; local mail must not automatically resend uncertain effects. Split a large audience into bounded jobs without changing the approved/frozen audience. |
| [Mailer](../mailer.py) `send(..., attachments=...)` | Reuse configured transport, delivery policy, PDF attachments and email logging. | Boolean `sent=False` is insufficient to prove no delivery: SMTP/relay timeout can follow acceptance. Record attempted-but-unconfirmed outcomes as unknown; missing configuration before send is safely unsent. No exactly-once delivery claim. |

## Chosen technical design

Use an advisory-specific adapter around the existing Documents lifecycle. Each managed advisory
has one linked outgoing document; that document is the authority for decisions, current approved
version and audit history. Advisory metadata supplies activity linkage, editable fields, audience
intent and publication/issuance pointers. Do not maintain a competing approval state machine.
Document registration numbers remain internal identifiers distinct from the advisory number.

A real linked Work case provides collaboration in the review slice; it does not fabricate calendar
entries or consolidation inputs. Its membership must grant the same intended draft access as the
document. Advisory comments bind to a revision/packet independently of the editable Work case;
ordinary replies do not change the reviewed content fingerprint. Existing Work consolidation
invalidation remains unchanged for other document types.

Extend shared document review checks with a policy discriminator and immutable advisory packet:
revision ID, PDF/PNG hashes, content/audience hash, owning division, selected Chief/Director,
authority evidence and policy version. Every decision checks expected document revision, packet,
stage, current actor authority and immutable artifact identity inside one transaction. Generic
Documents review, attachment, signature, release and publication routes must enforce the same
advisory policy; hiding UI buttons is insufficient. In particular, the existing “minor” attachment
path must not preserve an advisory approval after changed content or audience.

| Action | Preconditions | Atomic result |
|---|---|---|
| Submit/resubmit | Authorized initiator; valid immutable revision; unambiguous current routing; change summary on resubmission | New packet, Chief stage, exact recipient notice, history |
| Chief endorse | Assigned current division authority; matching packet/version | Endorsement history, Director stage; `approved_version` remains empty |
| Director approve | Assigned current Director; matching Chief endorsement and packet | Final `approved_version`, approval event and ready-for-issuance notice |
| Return (either stage) | Current reviewer/approver; required explanation | Changes requested, next action initiator, approval cleared, prior evidence retained |
| Clarification/reply | Authorized participant; current or historical thread | Discussion entry only; current review stage unchanged |
| Withdraw/revise | Authorized initiator; no unresolved external effect | Retire active submission; new content/audience revision requires Chief then Director again |
| Issue | P1 authority; final approval and required formalities; current confirmation | Immutable issuance and audience snapshot plus queued jobs; no network call in transaction |

A formal Return always transfers the action to the initiator. “Unchanged clarification stays at
stage” means a discussion reply while review remains open, not silently undoing a return.
History retains all earlier decisions and versions; approval invalidation clears current pointers,
not prior evidence. Later supersession links replacement and predecessor explicitly. Cancellation
and supersession are audited actions and cannot delete issued evidence. Their operational UI is
outside slice 1; do not invent additional authority exceptions there.

## Proposed additive data contract

Names below describe planned tables/extensions, not existing schema. All foreign references must
be checked for advisory/document ownership, not merely existence.

- `advisory_record`: stable ID, unique document ID, nullable activity ID (unique for P3), immutable
  number/reservation date/sequence, owning division, initiator account ID, working revision pointer,
  optional Work case ID. Document holds workflow status. Conditional updates use its revision token.
- `advisory_revision`: unique `(advisory_id, ordinal)`, parent, normalized content JSON, audience
  mode and normalized explicit external recipients, source-activity snapshot/hash, content/audience
  digest, author/time/change summary, local artifact references. Content is append-only; no-op save
  returns the existing revision. Snapshot excludes discussion and routine internal roster changes.
- Local artifact storage: proposed bounded SQLite BLOB table for generated one-page PDF/PNG,
  SHA-256, media type and byte length, immutable once referenced. This keeps bytes and metadata
  in the same backed-up transaction without relying on ephemeral process cache. Establish a byte
  cap from synthetic maximum-size renders during implementation; reject oversize output before save.
  Extend `document_file_version` with an explicit backend/reference contract, retaining Drive
  semantics for existing records. Authenticated reads check document access; public reads require
  a separately authorized frozen publication pointer. Never regenerate approved/issued bytes.
- Review extension: packet and stage records linked to `document_review`/`document_event`;
  endorsement is distinct from final approval. Append-only authority/policy evidence and concern
  events; revision bindings point at existing Work comments. No second review-history store.
- `advisory_issuance`: unique issue operation key, advisory/revision/document version, approved
  artifact hashes, issuer/time, confirmed audience snapshot and public-publication choice.
  Recipient rows freeze normalized address, internal/external provenance and skipped-account
  explanations. Dispatch attempts reference the issuance, existing jobs and recipient outcomes.
- Idempotency ledger: actor + action + client operation key, payload hash and resulting identity.
  Same key/same payload returns the recorded result; changed payload conflicts. Constraints protect
  one current submission/issuance and unique sequence allocation. Serialize competing writes before
  checking expected revision; a losing stale action has no audit, notice or partial data effects.

Internal distribution uses active accounts and the existing account/contact address resolution;
missing/invalid addresses are visible exclusions in the confirmation. Normalize/deduplicate across
internal/external lists, preserve provenance, and send one message per address to avoid disclosure.
Do not silently truncate at the current 100-recipient job limit. Freeze the whole audience and
partition dispatch work; a retry never re-resolves the roster or adds a new recipient.

The record remains Issued even if every dispatch fails. Show pending, accepted, failed, unknown
and partial delivery separately; provider acceptance is not proof of receipt/read. Definite failures
may be retried with a new attempt linked to the same issuance. Accepted or unknown recipients
are excluded from automatic retries. A crash after network acceptance but before recording is
unknown and requires provider evidence; an expired lease alone cannot authorize another send.

## Existing application compatibility

Keep existing `event_advisory` rows, numbers, public URLs and publication facts. No bulk copy,
backfill of approvals, historical issuance-date inference or renumbering. Unmanaged existing
records remain explicitly “existing publication; approval history unavailable,” not Approved/Issued.
They can be listed through a read-only compatibility projection with authorized access.

New workflow records use the existing activity URL to open their canonical advisory. For managed
records, every old save/publish/download route must resolve that identity and enforce its policy.
The direct publish shortcut is unavailable before the issuance/publication slice. For existing
records, an explicitly requested next edit can create the linked draft under the same advisory
number while preserving the old public output as a compatibility artifact; capture it before the
first write and label capture time honestly. If capture fails, leave everything unchanged. A new
draft must never replace an existing public copy until a newly approved publication is authorized.
This is ordinary additive schema/read-path compatibility, not an import or transition project.

## First implementation slice, ready for separate authorization

**Deliverable:** privately save and reopen an activity advisory with owning division, audience
intent, immutable revision history and a central permitted register. Activity and register open the
same identity. This slice ends before submission, approval, issuance or notifications.

1. Add the record/revision/idempotency/artifact foundation through an idempotent schema installer.
   Extend document version storage for local artifacts. Keep foreign-key checks and append-only
   constraints. Re-running installation preserves all existing values; no data import job.
2. Extract caller-owned advisory saving/number allocation. In one `BEGIN IMMEDIATE` transaction,
   reserve the advisory number, register the linked OUT document via the existing registration
   service, persist restricted access and quiet draft audit, attach exact rendered bytes, and save
   metadata/revision. Ensure registration rules cannot auto-route or widen advisory access.
   Render/validate before the write lock where possible; recheck source/expected revision at commit.
3. Update the current editor with owning division, internal/external/both audience, recipient fields,
   expected revision and idempotency key. No-op saves keep identity/number/revision. Phone forms
   retain entered values on validation/conflict. Render uses saved snapshots, not mutable activity
   fields; show changed activity details for explicit adoption into a new draft.
4. Add the central advisory listing/detail/history using shared permission predicates and identical
   list/count filters. Entry requires activity-management authority; after creation, document access
   also governs reads/edits. Initiator and assigned roles receive explicit restricted access; merely
   selecting “internal” does not expose a draft to every internal recipient. Do not grant approval
   authority to activity managers or technical administrators.
5. Add managed-record guards to old advisory publish/file routes and generic Documents mutation
   paths. Until later slices exist, server-side submit/review/issue/sign/dispatch actions for these
   records fail with a clear “not available yet” result. All draft save/registration operations are
   quiet: no notice insertion, mail dispatch, Telegram, shortening request or other outbound call.
   Reuse an existing stored activity link or local application URL for QR defaults in isolated tests.

Expected touched areas: `storage.py`, new `advisory_workflow.py` / `advisory_storage.py`,
`activity_advisory.py`, `activity_advisory_routes.py`, `documents.py`, `documents_permissions.py`,
`documents_storage.py`, local artifact access in `documents_operations.py`, application route wiring,
`templates/activity_advisory.html`, proposed register/history templates and corresponding tests.
Use an additive internal adapter API (`save_draft`, `get_visible`, `list_visible`, `history`) with
an explicit actor and expected revision; the adapter owns orchestration and delegates shared checks.
Read Documents/Work feature switches at runtime; if prerequisites are disabled, show an unavailable
state and never enable them automatically. Full review/distribution requires later authorized slices.

### Synthetic acceptance contract

Use temporary data and disabled integrations following [cloud workspace guidance](CLOUD_WORKSPACE.md).
Fixtures: initiator, own-division Chief, other-division Chief, Director, designated OIC, unrelated
active staff, inactive staff; two activities/divisions; one existing published advisory; fake external
addresses under `example.invalid`. Inject renderer/transport doubles where appropriate.

| Scenario | Required result |
|---|---|
| First save; repeated request; reload from activity/register | One advisory/document/number; identical canonical identity and rendered bytes |
| Two creators or editors race; replay key with altered payload | One winning write; loser conflicts without partial history/number/document |
| Changed content/audience versus no-op save | New immutable revision only for changed normalized payload; old bytes/history remain readable |
| Change activity date/venue/source links | Difference notice; no silent revision or artifact mutation |
| Other division, unrelated/inactive staff, forged role, direct file URL | Consistent denial across detail, history, exports/list/count and files; audience choice grants no draft access |
| Old published record; managed draft; old publish and generic review/dispatch routes | Existing number/URL preserved; no fabricated approval; managed draft cannot become public or issue |
| Installer rerun; render/storage failure; malformed recipients | Preserved existing rows; atomic rollback; actionable validation and no partial artifact/record |
| All save/list/history flows | Zero outbound calls and zero queued outbound notifications |
| Phone width and no-JavaScript form journey | Save/reopen/history and conflict correction work without horizontal overflow |

Existing regression anchors: [advisory tests](../tests/test_advisory.py),
[Documents tests](../tests/test_documents.py), [action routes](../tests/test_document_action_routes.py),
[Director/OIC tests](../tests/test_director_and_oic_routing.py), and later
[job tests](../tests/test_documents_jobs.py) / [mailer tests](../tests/test_mailer.py).
New tests must exercise behavior and bypass paths, not merely duplicate implementation.
No tests above were run in this planning session; they are future acceptance criteria.

## Subsequent slices and handoff

After the private foundation: (2) staged shared review, genuine Work discussion, returns,
resubmissions, exact-version history and narrowly routed notices; (3) issuance authorization,
frozen internal/external audience, local-PDF dispatch and independent delivery status/publication;
(4) dashboard queues/counts and final memo alignment when separately authorized.

Slice 1 is now authorized and implemented using P2/P3 working defaults; see the linked implementation
checkpoint. Before dependent review/issuance, record P1/P4/P5. Inspect current branch/main again
and preserve newer work. No merge/deploy authorization is implied by any policy answer.
Documentation validation: all 162 local Markdown targets across the three planning/status
files resolved; `git diff --check` passed.
Application tests, live workflows, previews and production configuration checks were not run.
