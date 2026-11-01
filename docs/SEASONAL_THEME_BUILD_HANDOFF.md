# Build handoff — Christmas and New Year, November 1, 2026

## Outcome and saved state

The user requested a firmer design plan and a handoff so implementation can start
in a later session. Planning is complete; no application implementation is authorized
by this handoff alone. Repository: `jongsky25/css-is`. Saved branch:
`docs/christmas-theme-design-plan`. Initial Christmas plan commit: `1ec3fdd`.
This document and the updated status are saved in the subsequent handoff commit
on that branch. No PR created, preview published, merge or deployment performed.

Start a later session with: “office connect — build the Christmas and New Year
themes from docs/SEASONAL_THEME_BUILD_HANDOFF.md.” Read current AGENTS.md and
workflow/status first; inspect changes since the assessment before implementing.

## Agreed scope

- Enhance Christmas using [Paskong Office Connect](CHRISTMAS_THEME_PLAN.md): warm
  Filipino Christmas, parol lanterns, evergreen, cream, restrained cranberry/gold,
  illustrated Home scene and coordinated companion stage.
- Add a distinct New Year theme: “A brighter year, together.” Midnight blue,
  champagne gold and warm white, parol continuity, restrained starbursts and a
  companion setting with ribbons/stars. Provide light and dark variants.
- Put the main seasonal scene and New Year countdown on Home. Use compact seasonal
  accents on work pages; avoid repeating a tall hero above forms and reports.
- Sound is explicitly deferred. Do not add audio assets, autoplay, sound controls
  or a sound-enablement prompt in this build.
- Preserve independent theme, artwork, ambient-effects and avatar-outfit choices.
  Christmas already has an outfit. A dedicated New Year outfit is optional later;
  the first build can use the chosen existing companion with a festive stage.

## New Year countdown behaviour

Initial target: January 1, 2027 at 00:00 Asia/Manila (December 31, 2026 at
16:00 UTC). Show the timezone beside the countdown. Prefer a validated target-year
setting, not a browser-local date or hardcoded display year. Keep the target fixed
through the greeting phase; never silently roll to the next year at midnight.

Before the target, display days, hours, minutes and seconds. On phones, use a compact
four-part row or wrapping grid with readable unit labels. No layout shifts as digits
change. The timer is functional content and remains available with artwork/effects
off. If JavaScript is unavailable, show the target date/time as a readable fallback.

Use server-provided UTC time and target timestamp, then advance elapsed time with a
monotonic browser clock. Recalculate remaining time from timestamps, rather than
subtracting one per tick. Resynchronize on visibility/focus and through the existing
appearance refresh where practical; do not request the server every second. Pause
unnecessary display updates in background tabs. If synchronization fails, retain the
last valid basis and the fixed target; initial sync failure leaves the date fallback.
This is a celebration display, not an authoritative transaction deadline.

At zero, clamp all values and replace the timer with “Happy New Year, Office
Connect!” A user opening Home after the target sees that greeting immediately.
Keep this separate from the customizable seasonal greeting so the countdown does
not overwrite administrator copy.

For a visible Home page crossing midnight, allow one brief confetti flourish inside
the illustration, only with effects enabled and reduced motion off. Stop within
five seconds; never loop or cover controls. Record a target-year session marker to
avoid replay on navigation. Opening after midnight shows the static greeting without
replaying the flourish. No per-second screen-reader announcements: accessible unit
labels and one polite announcement when the greeting changes are sufficient.

## Scheduling proposal

Use the existing Appearance scheduler and Asia/Manila half-open intervals. Suggested
defaults for the 2026/27 season:

| Appearance | Start (inclusive) | End (exclusive) |
| --- | --- | --- |
| Christmas | December 1, 2026, 00:00 | December 28, 2026, 00:00 |
| New Year | December 28, 2026, 00:00 | January 8, 2027, 00:00 |

After New Year, return to the configured everyday default. These dates are proposed
editable presets, not instructions to publish events or overwrite an existing
schedule/default. Keep manual overrides and expiry precedence intact. Midnight
changes the countdown into a greeting; the New Year appearance continues until its
scheduled end. Validate that scheduled New Year events contain the configured target
and that intervals do not overlap. Do not infer a new target on every refresh.

## Build order and likely touchpoints

1. Inspect current main and saved appearance configuration/schema before starting
   a feature branch. Read dependency/cloud-workspace instructions for isolated runs.
2. Produce phone/desktop visual mockups of Christmas Home, New Year countdown Home,
   post-midnight greeting and a working form. Include light/dark and effects off.
3. Build static seasonal tokens and local illustrations in `static/css/appearance.css`
   and `static/img/seasonal/`. Adapt `templates/_seasonal_scene.html`,
   `templates/dash_layout.html` and `templates/home.html` for Home prominence and
   compact details elsewhere. Keep the existing brand and operational status colours.
4. Extend `appearance.py` and its actual persistence/routes with New Year selection
   and validated target configuration. Inspect storage integration before choosing
   a migration. Preserve saved choices and define backward-compatible normalization.
   Replace Halloween-specific defaults/labels with theme-aware copy in
   `templates/admin_appearance.html`; inspect admin JavaScript too.
5. Extend `static/js/appearance.js` and server appearance responses with consistent
   timing/target data. Ensure live transitions can reveal correct scenes and change
   timer state without replacing the page or losing in-progress form data.
6. Refine companion art/stages only after the static composition and countdown work.
   Preserve species, growth, names, personal preferences and independent outfits.
7. Verify in isolation, save the candidate, then use the existing private preview
   workflow for phone review. Release follows a separate explicit release request
   and all repository gates.

## Verification required during build

- Appearance unit/browser coverage: old saved settings, valid/invalid targets,
  scheduling boundaries, overrides, independent artwork/effects/outfits and every
  seasonal transition. Check that admin preview does not publish changes.
- Timer boundary cases: before/at/after midnight, opening after target, wrong device
  clock, timezone differences, suspended tab/resume, sync failure and theme changes.
  Confirm no negative countdown, duplicate timers, repeated confetti or audio.
- Browser review at 320, 390, 768 and 1440 CSS pixels: keyboard, enlarged text,
  contrast, reduced motion, high contrast, print and no-JavaScript date fallback.
  Use existing appearance tests and `tools/contrast_check.py` where applicable.
- Inspect all companion species/growth stages for clipping. Confirm hidden scenes
  are absent from accessibility navigation and timers do not announce every tick.
- Verify an open form retains input, focus and scroll across theme/countdown updates.
  Record actual test counts, preview commit and phone feedback in the next handoff.

## Current verification, limits and next action

This session performs documentation diff and relative-link checks only. No app tests
or live-site visual review have been performed for this plan; there is no built
candidate or phone acceptance yet. Palette references still require contrast checks.
Monitoring/audit/storage operational follow-ups remain separate and must not resume
automatically as part of this design task.

Next action when the user starts the build: refresh main, reconcile this plan with
current appearance code, and create the seasonal visual mockups on a feature branch.
