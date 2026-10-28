# Increment 2B — user-approved provisional acceptance

Decision date: **2026-10-28 (Asia/Manila)**.
Status: **Provisionally accepted and unblocked. GC investigation stopped.**

The user accepted the recommendation to stop the disproportionate GC investigation
and unblock the avatar provisionally, with the unresolved memory risk documented.
Their confirmation was: **"okay do that"**. This is an explicit change to the
acceptance policy and supersedes earlier instructions requiring a memory correction
and native/application observer qualification before unblocking 2B.

## Scope of the decision

For this avatar increment, the original **+10 MiB renderer/JS memory gate is deferred
as a blocker to provisional acceptance**. The associated unstable controls,
incomplete full memory acceptance matrix and unfinished GC/observer qualification
are also deferred as blockers for this decision. There is no replacement numeric
budget and no claim that the original thresholds passed.

Existing artwork and visual/functional evidence are retained. No guarantee of
"no significant slowdown" has been established. The recent diagnostics did not
establish a significant user-visible slowdown attributable to the avatar, but they
also did not complete reliable full performance validation. Other functional,
accessibility and user-visible performance requirements remain applicable. This
exception is specific to 2B; it is not a blanket relaxation for later increments.

Current product reference remains **cf363bfe547d5e23619eee28cdaf68bd4b6d7753**, including
avatar artwork f700187. This decision changes status/policy only. The isolated
shared-gradient candidate **cd94bf35d29b796ca0d6467756221e4b545a40be** is not promoted,
and unrelated changes are not newly approved by this decision.

## Evidence and uncertainty preserved

The latest uninjected candidate screen reported navigation RSS differences of
**+11.699 / +16.301 MiB**, exceeding the original +10 MiB criterion. Same-source
controls were unstable, including a largest repeat swing of **36.379 MiB**, so the
source-attributable effect remains unresolved. Earlier offscreen, background,
reduced-motion and navigation failures, lifecycle findings, raw samples and
measurement limits remain in the [report](REPORT.md) and linked archives.

All raw assessment flags, failed checks and diagnostic qualification results stay
unchanged. A provisional acceptance decision does not convert them into passing
measurements. Full performance validation and memory correction remain unproven.

## Stop condition and future work

Stop the GC, root-retention, native-hook and observer-calibration work now. The
prepared [disposal probe](original-gc-audit/NEXT_PROBE.md) is archived, not an active
next step. Do not run more diagnostics or reopen the memory blocker just because
historical handoffs list them as prerequisites. No further test run is required to
record this policy decision.

Subsequent requested product work may use 2B's provisional acceptance as its
baseline. Revisit performance if the user requests it or a new reproducible
user-visible regression, crash or sustained growth warrants a bounded investigation;
start with the actual application rather than resuming the entire research chain.

This decision does **not** authorize a merge, deployment, candidate promotion,
release, or automatic start of a later increment. No such action was taken.
