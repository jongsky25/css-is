# Bounded background document processing

Introduced in **7.78**, completing A14's document execution work after the
[7.74 responsiveness](DOCUMENT_EXTERNAL_RESPONSIVENESS.md) and
[7.75 operation recovery](DOCUMENT_JOB_RECOVERY.md) increments.

## What staff see

- Check Drive now saves a durable request and returns immediately. The queue
  shows queued, running, waiting to retry or needs attention, with the last
  successful listing, last finished turn and next listing due time. Refresh the
  queue to see changes; this screen does not promise instant provider completion.
- Registered files show pending, being checked, waiting to retry, needs review or
  completed filing. Last and next attempts are shown where available. Filing
  failure leaves the registered document and its number intact.
- Authorized records staff can request another filing check from the registered
  queue or the document, including individual attachments. The original filing
  operation ID and payload stay unchanged. Current permission checks still apply.
- Check/retry requests are protected by the existing session and CSRF controls.
  Busy checks coalesce. Changing settings or requesting a filing retry while a
  check owns the database lease asks staff to wait. These actions never start an
  unbounded request background task.

## Capacity and scheduling

One tracked scheduler starts with the application and cancels on shutdown;
`CSS_NO_SCHEDULER=1` disables it for tests/CLI. It checks for due work every
**30 seconds**, alternating priority between sign/send receipt recovery and
Drive intake. If one side has no due work, the other can use the turn. Failed
listing attempts consume their turn, preventing recovery starvation.

Both kinds of background work share **one admitted background slot** in the
existing **two-worker** document-service pool per process. Admission has no
waiting queue. A busy pool defers work to a later tick. Timeout/cancellation
retains the background slot until the actual worker finishes; the remaining
slot can admit interactive document work. Admission does not reserve CPU or
control unrelated application services or workers on another database copy.

A Drive turn performs at most one listing page (up to 100 metadata entries) and
one filing attempt. These share one **120-second elapsed service budget**,
including HTTP phase/redirect/chunk checks. If listing exhausts that budget,
filing stays due for a fresh turn without consuming a filing attempt. Intake
registration checks also share this budget and use bounded interactive
admission. A failed registration check does not allocate a document number.

## Durable coordination and retries

A singleton SQLite sync record stores ownership, a **600-second expiry**, the
listing schedule and failure state. The same lease coordinates discovery,
manual requests and filing across processes. Each write after provider I/O
checks its unique owner token. Expired/replaced workers cannot overwrite newer
cursors, diagnostics, filing results or history. No writer transaction spans
provider I/O. A fresh manual request or saved settings also fences an expired
owner. Folder changes remain blocked while queued reviews or filing remain.

Normal listings are due every **180 seconds**. Transient failures wait 180, 360,
720, 1,440 and 2,880 seconds; delays cap at one hour. After **six** consecutive
listing failures, automatic intake pauses for review. Known configuration,
authorization and malformed-listing failures pause sooner. Check Drive now or
saving corrected settings restarts listing checks after current authorization.
A successful listing clears its failure history and diagnostic.

Each filing retains its attempt count, last/next attempt and review flag.
Transient failures use the same backoff and six-attempt limit. New pending files
can run between listing checks. A failing file's future retry time allows other
due files to progress. Known source/operation/folder conflicts and lost authority
require review instead of endless retries. An interrupted sixth attempt is marked
for review after expiry; explicit retry resets only its attempt schedule, keeping
the original operation identity and registered number.

The existing Apps Script `intake_file` operation atomically stores its receipt
marker with the move/rename in Drive metadata. Retrying the identical operation
checks that marker and source content instead of moving the file again. This
is the existing filing contract; sign/send recovery continues to query status
receipts without replaying its business action. Current configured and original
filing actors, document visibility and folders are rechecked. Binary files,
excerpts, provider bodies, credentials and worker tokens are not added to the UI
or retry payload.

## Verification and rollout

Coverage includes independent process claims; real process exit after remote
filing; unchanged operation/payload and one completion event after recovery;
fenced late success/failure/cursor writes; backoff and manual restart; authority
revocation; repeatable schema migration; scheduler fairness and lifecycle;
shared admission after timeout/cancellation; protected request/retry routes; and
same-loop HTTP navigation during two-second background/registration stalls.
The existing Apps Script harness verifies one actual simulated move after a
lost response, unchanged marker recovery and source-conflict rejection.

The additive migration preserves registered records and old filing payloads.
No new dependency, credentials, external service or Apps Script deployment is
needed. Deployment packaging includes `documents_sync.py`. Old pending/error
filing becomes eligible under the new bounded scheduler; confirmed filing stays
complete. Rollback leaves additive columns but restores the previous scheduler
and its capacity limitations. Review unresolved operations before manual action.

A14's engineering scope is complete with these three increments. Manual live
production testing remains deferred, and production latency/capacity measurement
belongs to A25. The shared SQLite file, reliable clocks and retained provider
markers/receipts remain prerequisites; independent database copies do not share
leases. Staff observation and the Documents-to-Work usability pilot are A15.
