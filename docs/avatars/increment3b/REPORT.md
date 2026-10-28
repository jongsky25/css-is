# 3B implementation — validation pending

Fish, dolphin, owl and fruit bat have six illustrated stages each. Growth changes
fin structure, rostrum, facial discs, tufts and wing span. Existing eye/head,
wing/ear, fin, bubbles, care and seasonal hooks remain. Swimmer water stays outside
the moving creature. Artwork is original authored SVG using existing gradients.

This commit is implementation only. Fresh contact sheets, care/browser checks
and performance acceptance are pending. No deployment or main merge.

## Integrated validation update — 2026-10-28

Implementation and focused checks are complete. The combined source passes 432
actual animal stage/mood/theme rig cases; 1,584 compatible equipment/stage and
1,632 seasonal render cases; 24 wardrobe/customizer/appearance checks, including
real global updates while previewing an unsaved seasonal mode; and 32 motion,
pointer/customizer/audio regressions. All eight animal care interactions persist.
The leaf test now establishes maturity itself. See the completion report for
exact snapshots, retained failures and all evidence. Full hosted performance
acceptance remains pending; this is a review candidate, not a deployed release.


### Final hosted avatar acceptance (fecd276)

The integrated functional, runtime and complete application-matrix phases pass
on hosted run 40620559865. All 104 median RSS/heap comparisons meet 10 MiB against
accepted 2B; final runtime max callback is 3.364 ms and max frame p95 is 16.8 ms.
See [the completion report](../completion/REPORT.md) for audited sources, raw
evidence and limits. Full normal/shuffled application CI 40628692333 passes 7,060 tests per order
with zero failures/errors/skips, plus the strict offline AI and release gates.
No deployment or main merge occurred; earlier failures remain recorded.
