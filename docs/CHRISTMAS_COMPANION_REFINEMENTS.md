# Christmas companion refinements — plan, November 2, 2026

User requested planning first after reviewing production 9.60. Base: main
`adb83b4`. No code, appearance settings, sound behaviour, preview or production
changes are authorized by this planning step. Do not commit the supplied personal
screenshot; use synthetic accounts for later mockups and tests.

## 1. Multiple Christmas outfits

The Christmas page palette does not currently change an independently saved
Halloween outfit. `appearance.py` has three Halloween variants but only one
Christmas choice; the admin gallery also emphasizes those Halloween variants.
The screenshot shows a vampire-style rabbit, but the actual saved configuration
has not been inspected. Do not claim a database diagnosis from the screenshot.

Propose five Christmas styles, with visibly distinct silhouettes:

| Style | Animal treatment | Plant treatment |
| --- | --- | --- |
| Santa | Soft Santa hat, red coat/vest with cream trim | Santa hat or festive pot sleeve appropriate to growth stage |
| Elf helper | Green pointed cap, short red/green collar or vest | Green pot wrap, striped ribbon and small elf-cap detail |
| Reindeer | Small antler headband and cranberry scarf; keep species recognizable | Antler ornament/stake and cranberry pot ribbon |
| Parol keeper | Gold ribbon/capelet with a small star-lantern ornament | Gold pot band and parol stake |
| Festive knit | Cream/red patterned scarf or sweater, proportioned to the body | Matching knitted pot cover |

These are seasonal outfits, not new species or growth stages. Adapt the treatments
for aquatic, flying, long-eared and small/early-stage companions. Keep eyes, ears,
faces, wings and growth features readable. Retain the existing Christmas outfit ID
as the Santa-compatible choice so saved settings remain valid.

Group the editor's gallery by season, show Christmas variants prominently when
Christmas is selected, and preview with the user's chosen companion where possible.
Clearly display both active page theme and active outfit. Keep the existing
“Use matching outfit” action, mapping Christmas to Santa, and make it easy to choose
another Christmas variant before preview/publish. A saved Halloween choice must
remain available as an intentional independent choice; show a clear mismatch hint
and matching action rather than silently replacing saved choices.

Personal accessories and No accessories modes remain respected. This first
refinement does not add automatic outfit rotation or change the personal wardrobe's
ownership model. Existing administrator seasonal outfit controls remain the scope.

## 2. Full available width and centred composition

Current `.oc-pet-stage` participates in the greeting's wrapping flex row with a
220px flex basis. Its contained background is scaled to that restricted box.
This can leave unused width to the right on a phone. The illustration also reads
as a separate image below the avatar rather than a setting surrounding it.

Make the companion a dedicated full-width section below the greeting across
mobile, tablet and desktop. Fill the content container, retaining the same outer
gutters as the search and task cards. Do not use `100vw`, stretch the avatar, or
stretch a small illustration disproportionately.

- Centre the avatar inside the illustrated stage, with scenery behind and to its
  sides. Remove the strong pale radial wash; use a restrained warm spotlight.
- Use layered/wide artwork with responsive edge crops and a protected central
  area. Important decorations must not disappear off the left or right edge.
- Keep the stage compact: initial target roughly 220–280px on phones, then adjust
  in mockups. Wider screens reveal more scenery rather than creating empty height
  or enlarging the companion excessively.
- Put existing companion controls in a separate accessible row below the scene.
  Preserve any existing sound controls/credits and Change companion action; no
  control should overlap the rabbit, decorations or another control. Do not add
  new seasonal sounds or change sound preferences in this refinement.

## 3. Complementary scenery, no repeated header tree

Keep the existing header's tree illustration. Stop using its scene asset as the
companion background. Author separate tree-free compositions:

| Scene | Composition | Why it complements the header |
| --- | --- | --- |
| Parol courtyard — recommended default | Warm capiz-window arches, hanging parols, low poinsettia planters and a simple courtyard floor | A Filipino Christmas setting with open central space for the companion |
| Festive sala | A cosy bench, woven textile accents, star-lantern window and small side arrangements | A welcoming indoor setting, with different forms from the header tree |
| Poinsettia veranda | Low red/cream poinsettias, brass lanterns and warm light strings around a veranda | Floral celebration with a clear central avatar area |

No tree silhouette, copied gift/tree grouping, duplicated city backdrop or reuse
of the header SVG in these companion scenes. Shared colours and small parol motifs
provide continuity; the full illustration must be distinct.

Design all three as mockup alternatives first. Implement the selected scene after
review; adding a permanent scene picker or saving per-user background preferences
is not assumed. New Year should eventually receive its own separate companion
scene too, rather than reusing the header fireworks, but that is outside this
Christmas refinement unless requested.

## Build/review sequence when implementation is requested

1. Refresh main and the active Telegram branch; work in a separate feature worktree.
   Preserve release 9.60 history. Keep edits confined to appearance/avatar art,
   companion layout, dedicated scenery and focused tests where possible.
2. Produce the five outfit contact sheets using a rabbit plus representative plant,
   aquatic and flying companions. Produce all three scene alternatives at phone,
   tablet and desktop sizes, including light/dark and effects off.
3. Review the full-width panel composition and scene choice, then implement the
   selected background and the outfit options without changing live settings.
4. Verify every species/growth stage/outfit combination for clipping and overlaps;
   test 320/390/768/1024/1440 widths, enlarged text, keyboard/touch controls,
   reduced motion, contrast, artwork off, saved configurations and live outfit
   changes. Assert that the companion stage fills its available container and
   uses a separate scene from the header. Preserve form input during refresh.
5. Coordinate the shared preview before publishing a saved candidate. Owner phone
   review precedes any separate release request and all existing release gates.

Acceptance: five distinct Christmas styles; a centred companion on a full-width
stage at all target widths; no repeated header tree/scene; no washed-out avatar,
overlapping controls or horizontal overflow. No runtime implementation or visual
verification is claimed by this plan.

Implementation was subsequently requested. Follow [the build handoff](CHRISTMAS_COMPANION_BUILD.md) for the isolated candidate, tests and preview evidence. The planning-only scope above records the original request, not the subsequent authorization.
