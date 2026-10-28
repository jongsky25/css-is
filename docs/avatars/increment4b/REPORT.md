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
