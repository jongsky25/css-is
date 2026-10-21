# Document external-operation responsiveness

Introduced in **7.74**, the first A14 increment.

## Behavior

The document action handler parses its form/JSON and verifies session-bound CSRF
on the request loop. Its database work, external calls and template rendering
then run in a worker with a SQLite connection created and closed in that worker.
Existing actor, permission, revision, source-version and operation-receipt checks
remain in the domain services.

Covered interactive service work has **two slots per application process**:

- Attach a Drive source, signature placement preview, external-signature recording.
- Extract, sign, dispatch, record dispatch, and check an operation's service receipt.
- The new-correspondence Drive preview, file-text indexing and ink source validation.
- Intake review's extract/reread actions, which were already off the request loop.

Ordinary document actions also run off-loop without occupying these external
slots. The existing PDF/OCR subprocess limits remain separate.

There is no application waiting queue. Excess covered work returns **503** with
`Retry-After: 3` and `state: not_started` for JSON clients, before creating a job or
changing the document. Navigation and health requests use neither external slot.

## Timeout and cancellation

The browser request waits at most **120 seconds** for an admitted external worker.
If still incomplete, it returns **504**, `state: unconfirmed`, and a link back to
the record. It does not advertise automatic retry. A cancelled request likewise
does not cancel an admitted worker or free its slot early. The actual worker
future releases capacity only when it ends and can still settle its existing
operation receipt. This avoids admitting an unbounded number of calls after
clients leave or time out.

The Workspace relay retains one authenticated POST and follows only approved
Google result-host redirects with GET. It applies one **120-second elapsed call
budget**, checked before requests, between streamed chunks and before accepting
a response. HTTP read/write phases are capped at 90 seconds, connect/pool phases
at 10 seconds, and subsequent requests use the smaller remaining budget. Response
metadata remains capped at 1 MiB. Provider text and credential-bearing transport
URLs are not copied into action errors.

Python threads are not forcibly killed. An already-blocked network read can run
until its phase timeout even after the elapsed budget expires; its slot stays
occupied. The 120-second browser wait does not promise that all external effects
have stopped. The UI explicitly asks users to check the record before resubmitting.

## Operation consistency

A process-local guard excludes overlapping execution, service-status lookup and
manual reconciliation for the same operation ID. An overlapping request receives
409 and leaves the active job unchanged. Different operations can use both slots.
The guard also prevents a manual "confirmed no effect" decision from racing a
live send and enabling a duplicate attempt.

Existing pending/running/unknown/confirmed job states and relay receipts remain
authoritative. Provider timeout leaves signing/dispatch unknown and blocks blind
retry; a known receipt still records one dispatch and its recipient outcomes.
Transient extraction suggestions remain unsaved. No service POST is automatically
retried by this increment or by the service worker.

## Verification

`tests/test_documents_external.py` drives complete HTTP requests on one event
loop, with synthetic accounts/documents and fake providers. Each relay call in
the responsiveness cases blocks for **two seconds**. While extraction, attachment
or source preview is active, health and new-document navigation must both finish
within **1.5 seconds combined**, before the service request completes. SQLite's
normal thread checks remain enabled, and the test asserts external calls use a
worker thread.

Other cases check two-slot saturation, no queued job/revision change for a third
request, timeout and cancellation while retaining capacity, eventual settlement
of exactly one dispatch/recipient receipt, unknown outcomes without replay,
CSRF/private-record denial before provider I/O, and execution/reconciliation races.
Workspace regressions verify remaining-time propagation, deadline expiry without
another POST/GET, and a trickled response exceeding its elapsed budget.

These are local synthetic/failure-injection checks, not production latency or
capacity measurements. No manual production testing was performed.

## Rollout and remaining A14 work

No new dependencies, schema changes or data migrations. The deployment closure
includes `documents_external.py`.

This pool and guard are process-local. They do not coordinate multiple application
processes, automatically resume jobs after restart, or guarantee a live worker
survives process shutdown. Existing job/relay receipts support the existing
explicit recovery flow. Durable leases, restart recovery, operator-facing job
status improvements and background sync scheduling/admission remain the next
A14 increment. No new email, Drive or infrastructure credentials are needed.

The next slice, **7.75**, adds [durable ownership and restart recovery](DOCUMENT_JOB_RECOVERY.md) around these jobs and existing receipts. Background synchronization capacity remains separate.

**7.78 completes A14:** [bounded background synchronization](DOCUMENT_BACKGROUND_SYNC.md) adds shared background admission, fair scheduling, durable Drive ownership and controlled filing retries.
