# Christmas theme assessment and design plan

Assessed November 1, 2026 against main `a7b9b38`.
Scope: design planning only; no runtime changes, preview publication or release.
Assessment is based on source inspection, not a live-site visual review.

## Current assessment

Christmas is an accent treatment rather than a complete seasonal environment.
In `static/css/appearance.css` it sets four green accent tokens for light/dark
appearance and displays a small floating snowflake/tree emoji when effects are on.
The animation moves the emoji vertically; it is not a snow scene. Turning effects
off removes this decoration entirely. Platform emoji rendering also varies.

Halloween has a coordinated surface palette, navigation, illustrated banner,
background scenery, pet stage and footer. Christmas has none of these equivalents.
The shared scene in `templates/_seasonal_scene.html` is Halloween-specific and is
included before content throughout the dashboard layout. Copying its large banner
onto every Christmas page would push work down, especially on phones.

`appearance.py` defaults artwork on only for Halloween and uses a Halloween fallback
message for every theme. The admin form labels artwork and the greeting as Halloween,
while advertising snow in its animation control. Christmas outfits are already
available separately from theme selection; retain that independence.

## Recommended direction: Paskong Office Connect

A warm Filipino Christmas office: illuminated parol lanterns, evergreen foliage,
cream paper, restrained cranberry ribbons and brass-gold highlights. Use a softly
illustrated office window or courtyard at dusk as the main scene. Match the existing
companion illustration style. Snow is optional secondary atmosphere; lanterns and
warm light establish the identity without animation or a winter landscape.

Proposed colour references (starting points, not verified accessible combinations):

| Role | Light appearance | Dark appearance |
| --- | --- | --- |
| Page | Warm ivory `#F7F2E8` | Deep pine `#101F1A` |
| Cards | Cream-white `#FFFCF5` | Evergreen charcoal `#192D25` |
| Primary action | Evergreen `#216746` | Soft mint `#80D5A4` |
| Decorative highlight | Brass `#B68A3B` | Warm gold `#E2BC70` |
| Ribbon accent | Cranberry `#9C3046` | Muted berry `#DA8293` |

Reserve red for sparse illustration details; preserve the established meaning of
errors, warnings and successes. Verify all text, borders, controls and focus states
against their actual backgrounds before finalizing tokens.

## Design scope and priority

1. **Complete static identity first.** Coordinate page surfaces, header, navigation,
   borders and focus states in both light and dark appearance. Keep the Office
   Connect brand identifiable. Use parol/garland art in bounded header or scene
   areas, outside menus and touch targets.
2. **Give Home the main scene.** A parol-lit office, small tree, wrapped gifts and
   space for the greeting: “A season of gratitude. A little brighter together.”
   Keep it compact on phones, with essential work reachable without a large hero
   taking the first screen. Use a slim seasonal detail on task/form/report pages.
3. **Bring companions into the scene.** A small illustrated gift-and-lantern stage
   around the existing companion. Refine Santa hats/ribbons as needed; check every
   species and growth stage for clipping before adding further outfit variants.
   Preserve personal species, name, growth and nonseasonal preferences.
4. **Add restrained optional motion.** Slow lantern glow or occasional twinkle
   confined to illustration. No fullscreen particle layer, rapid flashing, sound,
   or decorations over inputs. The effects switch and reduced-motion preference
   must stop all motion; static artwork remains independently available.
5. **Make controls describe the theme correctly.** Generalize admin labels, use
   theme-aware fallback greetings and provide Christmas artwork defaults for new
   selections. Preserve explicit saved choices and custom copy. Verify scheduled
   transitions update scenes, labels, message and outfits without reloading forms.

## Implementation sequence

- First: produce desktop and phone visual mockups for Home and a working form,
  with light/dark and effects-off examples. Review composition and artwork density.
- Then: add local static illustration assets and Christmas tokens; adapt the scene
  template for seasonal variants and page-specific prominence. Avoid new remote
  fonts or animation libraries. Maintain clear artwork/effects controls.
- Next: fix default copy and admin labels, compatibility of saved configurations,
  and live transition behaviour. Add companion refinements only after the main
  scene and navigation work well.
- Finally: run isolated appearance behaviour/browser checks, contrast checks and
  focused visual review. Save a candidate branch and publish the existing private
  preview for phone review when implementation is requested. Production promotion
  remains subject to an explicit release request and repository release gates.

## Acceptance criteria

- Recognizable Christmas identity with animation off; artwork off leaves a complete,
  usable palette. High-contrast mode prioritizes its existing accessibility palette.
- No clipped navigation, horizontal scrolling or obscured controls at 320, 390,
  768 and 1440 CSS pixels, including enlarged text and keyboard navigation.
- Home feels celebratory; task forms and tables retain clear hierarchy and useful
  initial-screen space. Print output excludes seasonal scenery and animation.
- Light/dark text and controls meet applicable WCAG AA contrast requirements;
  decorative colours are not used as the only status signal.
- Default, Halloween and Christmas transitions work with effects/artwork on and
  off, reduced motion, custom/blank greetings and independently selected outfits.
- Switching themes on an open form preserves input, focus and scroll. Hidden scenes
  do not create duplicate accessible headings or misleading seasonal labels.

## Next action

Review the proposed Filipino Christmas direction, then prepare visual mockups before
implementing the theme. This plan does not claim that production currently uses
Christmas or that a live visual/accessibility assessment has been completed.
