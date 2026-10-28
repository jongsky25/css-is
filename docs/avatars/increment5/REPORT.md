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
