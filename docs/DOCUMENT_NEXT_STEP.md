# Document next-step guidance — A15, first slice (7.81)

The document detail page starts with **What happens next?** It identifies the
responsible person when the record names one, otherwise the responsible role.
It explains the next step, the first relevant blocker and how to resolve it.
People see links to the existing controls available to them. A person waiting
for someone else sees the reason and responsible role instead of an unavailable
action. Available legacy contribution steps link to their existing assignment
cards; migrated work links only to permitted work items.

## Workflow coverage

- Verify source details; correct a returned record and verify it again.
- Obtain the initial Director instruction, confirm the lead and reconcile changes.
- Finish required contributions and supply closure evidence for incoming records.
- Attach an exact outgoing draft; request review; revise a returned draft and
  renew approval. Current reviewer authority and access are checked for advice.
- Renew shared-work consolidation review when its inputs change. Private work
  identifiers, titles and links are not added to the guidance.
- Sign the approved version, prepare release and record actual dispatch evidence.
  Approval, signature, delivery, acknowledgment and closure remain separate.
- Inspect pending/running/uncertain signing or sending requests and their service
  receipts before requesting another effect. Accepted and uncertain recipient
  deliveries are never presented as safe resend targets.
- Record required acknowledgments, review closure requirements and retain history.
  Closed records can be reopened with a reason and a new deadline by the lead or
  records officer. Archived records require restoration by the workflow admin.

## Implementation and boundaries

`documents_guidance.build` reads the existing permission-filtered detail snapshot
and local workflow data. It makes no provider request and changes no document,
revision, job, assignment, review, dispatch or audit event. There is no new API,
background worker, schema, dependency or permission grant. The release runtime
manifest includes the new module.

Advice is a point-in-time view. Existing POST handlers independently recheck the
current account, permission, revision, exact draft, policy and operation state.
Opening a guidance link opens enclosing details and focuses the target control;
it never submits a form. Bookmark navigation, repeated links and malformed
fragments are handled. Existing forms and manual correction remain available.

Structural closure checks are shared with the existing close action so advice
uses its actual blockers. An explicit `closure: []` policy means no additional
evidence fields; a missing closure policy still blocks closure. This distinction
is also shown in the existing close form. The order and meaning of write gates
are preserved.

The panel presents the next relevant blocker, not a promise that the whole record
or linked work item is complete. Staff must still check actual evidence and
provider receipts. Existing delivery retry/reconciliation restrictions apply.

## Verification and rollout

Focused tests cover real incoming/outgoing journeys, corrections, returned
approval, material revisions, signatures, delivery and acknowledgment, closure,
reopening, role revocation, stale revisions, private shared work, changed
consolidation inputs, interrupted operations, partial/uncertain recipients,
read-only GETs and escaped historical feedback. Browser tests exercise keyboard
navigation, focus, nested details, bookmarked/repeated links and mobile/desktop
light/dark layouts without POSTs.

Run the complete required normal and shuffled suites, dependency audit and
release metadata gate for the exact PR revision before merge. Manual production
testing remains deferred. This implements the first A15 engineering slice;
staff baseline tasks, observed before/after completion times, assistance, errors
and confidence remain pilot work. It does not claim A15's pilot exit gate.

To roll back this slice, remove the guidance integration/template and restore the
previous fragment navigation if needed. No data rollback or migration is needed;
retain all document history and the current security checks.
