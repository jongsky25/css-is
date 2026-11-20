# Advisory review and approval

Candidate 10.41 continues the [private drafts](ADVISORY_DRAFTS.md).
The owner's instruction to merge and continue the development cycle authorizes
implementation and guarded releases of the remaining plan. No test uses live data
or sends a real notification. No Sheet integration or external memo edit is included.

## Working policy defaults

The implementation uses the recommendations in the [plan](ADVISORY_TRACKER_INTEGRATION_PLAN.md):
initiator plus explicitly authorized releasing staff may issue; stable first-save
number/date and separate actual issue date; one advisory per activity; active eligible
internal roster captured at issue; audience/external-address changes require renewed
review; Director approval is sufficient without a separate signature. Current formal
OIC assignments substitute for the corresponding seat. Three different people must
prepare, endorse and approve. These are implementation defaults under the owner's
instruction to complete development, not a claim of separately answered policy questions.

## Shared services and behavior

`advisory_review` adapts Documents transactions, immutable review decisions, document
events, revision guards and queued notices. It creates a real Work case with a linked
document and uses Work comment/reply storage. Explicit document access permits the
assigned reviewers to read that case; generic discussion edits are blocked so each
comment remains bound to an advisory revision. Corrections are replies. Concern
resolution/reopening is append-only and limited to current Chief/Director authority.

Submission snapshots the exact saved revision, artifact digest, owning division,
Chief, Director and policy. Chief endorsement advances to Director without creating
an approval. Approval binds the exact version. Returns clear approval and put the
initiator back in control. Editing is allowed only in draft/changes-requested states;
a new submission always restarts Chief review. Unchanged discussion does not advance
or reset a stage. Withdrawal, cancellation and explicit rerouting retain history.
Current roles are rechecked on decisions; vacancy, ambiguity, self-review or changed
routing block the decision. The initiator explicitly restarts routing when needed.

My desk uses the same Documents selection and advisory guidance. The canonical screen
shows stage, permitted actions, version-linked comments and paginated action history.
Existing generic Documents/Drive review, release and editing bypasses remain blocked.
Stage notifications use Documents delivery, feature switches, stable event/recipient
keys and authorization checks. Obsolete notices are suppressed. Failed no-transport
attempts can be retried; uncertain sends are never automatically resent. Delivery
failure does not undo a review decision. Ordinary comments do not send email.

Issuance, external delivery, final public publication and dashboard filters are the
next development slice. Approval itself sends no advisory attachment and publishes nothing.

## Verification

Synthetic service tests cover both return loops, renewed Chief review, idempotency,
stale decisions, OIC replacement, self-review, discussion/concerns, module switches,
My desk guidance and notice failures/retry. Phone browser journeys cover Director
return, revision and renewed approval with JavaScript enabled and disabled.
Full hosted release checks remain mandatory before merging.
