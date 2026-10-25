# Increment 2B — chase write follow-up

**The user accepts the observed33.3ms mushroom frame result. Overall acceptance still awaits the remaining checks.** [Assessment](chase-write-fix/assessment.json).

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
