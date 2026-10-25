# Increment 2B — chase write follow-up

**Current verification fails the50ms callback gate (141.084ms). The user-approved33.3ms mushroom frame exception remains accepted.** [Assessment](chase-write-fix/assessment.json).

Removed repeated chase class, transition and facing writes. The new browser
regression also exposed numerical drift at a clamped boundary: transforms changed
from4.2e-6px to5.6e-6px, producing10 writes/second despite no visible movement.
Chase axis deltas below0.01 CSSpx now leave position unchanged. Direct drag and
keyboard precision are unchanged. Direction reversal still works.

[Seven browser checks](chase-write-fix/tests.txt) pass, including zero movement-style
mutations while clamped chase remains active. [1,734 SVG comparisons](chase-write-fix/artwork-equivalence.json)
pass; CSS/geometry are unchanged apart from the JS cache key8.20.

Five mature fern CPU4 native30-second runs pass16.7–16.8ms framep95.
The first mushroom run reaches33.3ms. The user has explicitly accepted this0.3ms exception to the original33ms threshold.
The cohort had already been stopped; all completed samples remain under
[chase-write-fix/native](chase-write-fix/native-tests.txt) and
[remaining-run log](chase-write-fix/native-remaining-tests.txt).
No rejected thread pinning was used. No trace or full-matrix acceptance is claimed.

[Protocol and source hashes](chase-write-fix/plan.json) identify the working-tree
patch measured on base df0cfb6; this patch and its evidence are committed together.
The [earlier report](REPORT-layout-fix.md) preserves prior failures and diagnostics.
3A remains pending. No deployment.

## Current verification

**2B remains blocked by callback timing, not the accepted0.3ms frame overrun.**
Five counterbalanced old/new-art fern pairs completed on the current runtime.
Current callback maxima: [6.235, 141.084, 9.715, 5.255, 15.526]ms;
old-art controls: [5.147, 7.467, 12.332, 9.858, 5.448]ms.
Current framep95 values are16.8ms in four runs and33.3ms in one, matching the small overrun the user accepted. One current pointer-move listener
callback reaches141.084ms against50ms. No JavaScript errors or trace loss.
The same-source seven browser tests and1,734 SVG checks remain valid.
The remaining species/full-matrix checks were not started after this prerequisite
failure. User acceptance of the recorded33.3ms frame result remains in force.
[Verification assessment](verification-current/assessment.json)
and [all raw traces](verification-current/traces/fern/summary.json)
retain every sample; no CPU/GC subtraction or cause claim.
