# 4A wardrobe model — implementation, validation pending

Thirteen stable allowlisted IDs declare species, primary/secondary slots, owning
head/neck/pot/ornament/back anchors and draw order. At most two items are accepted.
The shared renderer uses fixed authored SVG paths inside each species' growth and
motion rig. No URLs, CSS or user-supplied artwork enter the catalog.

Two additive account columns default to seasonal mode and an empty item list.
Unknown saved IDs are ignored. Species changes prune incompatible saved items.
Preferences are loaded once per request alongside appearance context. Own-companion
surfaces share preferences; directory face illustrations use seasonal appearance.
Explicit administrator previews remain seasonal. Live seasonal updates skip personal
and no-accessory companions while keeping page themes current.

Profile Save/Cancel and the nonpersistent preview are delivered in 4B. Tests and
render sweeps follow integration. No acceptance, merge or deployment is claimed.

## Integrated validation update — 2026-10-28

Implementation and focused checks are complete. The combined source passes 432
actual animal stage/mood/theme rig cases; 1,584 compatible equipment/stage and
1,632 seasonal render cases; 24 wardrobe/customizer/appearance checks, including
real global updates while previewing an unsaved seasonal mode; and 32 motion,
pointer/customizer/audio regressions. All eight animal care interactions persist.
The leaf test now establishes maturity itself. See the completion report for
exact snapshots, retained failures and all evidence. Full hosted performance
acceptance remains pending; this is a review candidate, not a deployed release.
