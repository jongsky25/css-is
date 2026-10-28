# 5 shared motion policy — implementation, validation pending

One IntersectionObserver plus page visibility and live reduced-motion preference
controls idle/roaming timers and CSS playback. Removed companions release their
observer/listener/timer state. Chase runs only after mouse input and stops on
inactivity, suspension or removal. The existing shared five-minute sleep clock
remains; it also refreshes the policy after sleep transitions.

Care/petting takes priority over idle, roaming and pointer tracking. Actions replace
previous actions rather than stacking. Breathing includes a rest, species have
varied breathing/sway periods, and watering gives leaves restrained follow-through.
Accessories inherit their rig transforms without independent timers. Pickers and
onboarding thumbnails are static. Existing drag, keyboard, care and audio remain.

Browser regressions, hidden/offscreen/removal checks and performance validation
are pending. No release acceptance, main merge or deployment is claimed.

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
