# Version2: stable app-main scope and shared read-only census metadata

Attempt3 (379e4e9/782962b, run40521460498) passes same-job native qualification and
the corrected full-app receiver proof (128 references/getters). All four full app
workloads complete with 13 snapshots/20 navigations. Frozen audit rejects all four
because actual non-avatar tag vectors differ from proof. Keep every raw sample,
source failure, snapshot and trace; independent re-audit reproduces those errors.

Concrete source cause: body-suffix selection shifts when an asynchronous hidden
<div class=offline-badge> appears. app.js refreshBadge creates it in an IndexedDB
promise and appends to document.body; it lies outside main#maincontent. Avatar
65-element pool/type vectors remain stable. This is not a missing user action.

Additional offline arithmetic (not qualification/waiver) finds conservative bounds
6.0715/6.2445/6.2902/5.4673%, all above5%. Census totals263–312ms plus146–149ms of
unchanged baseline checkpoints dominate. Source correction alone is insufficient.
Do not omit snapshot reads, relax the gate, pad waits, or repeat this build.

Implement separately versioned application-membership-v2:
- Retain32 live-cat SVG receivers, unchanged.
- Other scope is last32 HTML div/span/a elements within main#maincontent outside
  .avwrap, the server-rendered main-card/link region. Require one main root and
  actual inside-main receipts for every selected node. This general structural
  boundary excludes all appended body chrome, not a blacklist of one badge. It is
  a new explicit comparator region, not an exclusive ownership/heap partition.
- In one synchronous evaluate, compute each group's selection/type/attribute-string
  metadata once, take attribute strings before both repeated getter batches and
  after both. Keep every one of the128 getter calls, same repeats/order, native
  phase counts and positive null/identity checks. No other JS task can interleave;
  no write occurs between reads. Both repetitions are enclosed by the witness.
- Return one compact group descriptor with two32-value arrays. Expand to the same
  four auditable rows in Python INSIDE the recorded census interval. Thus neither
  DOM work, wire transfer nor metadata normalization is hidden from accounting.

All32-element samples,2560 native calls/probe, five unchanged baseline snapshot
envelopes, complete full workloads, prior/fresh native qualification and actual app
receiver proof remain. All <=5%/250ms,20%,1.20,90% coverage and measured two-group
reclamation/naturalGC/trace/source gates stay unchanged. No extra startup wait or
load filter. Legacyv1 audits must retain identical failure results.

Freeze code/tests and exact new source before a new opened-only workflow attempt.
Close superseded PR517 without merging. Preserve all prior failures and compare
implemented observer changes explicitly, never claim this is an unchanged rerun.
