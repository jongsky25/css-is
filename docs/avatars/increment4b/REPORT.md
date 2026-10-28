# 4B customization — implementation, validation pending

/me#companion now offers three appearance modes, two compatible-item selectors,
a read-only live preview, Save companion, Cancel changes, Remove accessories and
Reset to seasonal. Native labeled controls support keyboard use and a live status
announces preview/errors. Only the existing profile POST saves preferences; preview
GETs validate allowlisted inputs and never write. Existing authentication and
same-origin write protection apply. Other profile fields and care records remain.

Fresh persistence, permissions, render, cross-surface and browser checks follow.
No release acceptance, deployment or main merge is claimed.

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
evidence and limits. Broad normal/shuffled application CI is separately pending.
No deployment or main merge occurred; earlier failures remain recorded.
