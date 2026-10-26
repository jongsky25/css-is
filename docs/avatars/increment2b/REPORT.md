# Increment 2B — acceptance withdrawn: uncovered memory failures

**2B is not accepted. Release readiness remains false.** The acceptance recorded in `f46d7af` was premature: the CI comparison and my first audit checked memory for five active scenarios but omitted offscreen, reduced-motion, background and navigation measurements. Those omissions cannot waive the unchanged 10 MiB budget.

The existing final run 40263865865 already contains these failures; no benchmark was rerun or sample replaced:

| Warm desktop scenario | Original RSS median (bytes) | Current RSS median (bytes) | Increase (MiB) |
|---|---:|---:|---:|
| Offscreen | 479,694,848 | 491,581,440 | 11.335938 |
| Reduced motion | 481,587,200 | 493,223,936 | 11.097656 |
| Background probe | 613,728,256 | 633,479,168 | 18.835938 |

All five runs per arm have matching positive renderer counts (three for offscreen/reduced motion, four for the background probe). Background visibility is an automation limitation recorded in raw samples; this is the controlled background-probe RSS comparison, not a claim of physical hidden-tab behavior.

The earlier candidate's opposite-order retained memory run also contains a background RSS increase of **26.171875 MiB** and seasonal-preview increase of **12.710938 MiB** in its reverse-order pair. Its passing picker numbers alone never established all-scenario acceptance. Repeated-navigation RSS differences also exceed 10 MiB (warm desktop +32.300781 MiB at mount 20); lifecycle findings remain unresolved.

The largest final background increase is mostly shared resident pages: median summed Shared_Clean rises about 23.17 MiB, while summed Private_Dirty is slightly lower and PSS rises about 3.60 MiB. This does not prove a JavaScript retention leak, establish the root cause, or authorize subtracting shared memory from the RSS budget. An attributable, validated correction is still required.

All functional/visual, callback/frame and five-active-scenario findings remain preserved in [the incomplete audit report](REPORT-incomplete-audit.md), [its assessment](assessment-incomplete-audit.json), and [the full numeric/visual archive](final-verification/numeric-and-visual-evidence.tar.gz). Full raw traces remain in [artifact 12630379820](https://github.com/jongsky25/css-is/actions/runs/40277957839/artifacts/12630379820), retained until November 25. The green workflow/audit labels did not cover the omitted gates.

3A work is preserved on `codex/avatar-3a`, but its workflow has been paused and run 40280615190 cancelled after this prerequisite failure was discovered. No 3B, wardrobe, motion increment or release work may be accepted on this basis. No merge or deployment occurred.
