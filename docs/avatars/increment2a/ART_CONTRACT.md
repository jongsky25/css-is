# Plant batch 2A art contract

Original authored inline SVG for cactus, bonsai and sunflower, using increment 1's
sage leaf gradient and rounded outline palette. Each SVG owns its UUID-prefixed
leaf gradient. Existing shared pot, bark and flower-disc gradients remain shared.
No new filters, scripts, remote references, libraries or runtime dependencies.

All three retain `.av-body`, `.av-stem`, `.av-soil`, `.av-soilwet`, `.av-acc`,
seasonal costume front/back and earned regalia. Sunflower retains `.av-bloom`;
cactus flowers and bonsai blossoms also use that compatible hook. Bloom placement
belongs to an outer SVG group; CSS motion belongs to its inner `.av-bloom` so
rotation cannot replace the positioning transform. Sunflower headwear uses local
coordinates inside that positional group. Empty pot anchors are (60,121), after
botanical artwork and before monthly ribbons, regalia and seasonal pot fronts.

Draw order: costume back → drawn ground shadow/pot/soil → stems and branches →
foliage and blooms → pot anchor → monthly ribbon → regalia → seasonal pot front.
Cactus includes sand pebbles, bonsai a shallow glazed bowl with moss and visible
root flares, sunflower a terracotta pot and striped seed. Existing wet-soil and
watering-droplet overlays remain visible; no care logic changes.

| Stage | Cactus | Bonsai | Sunflower |
|---|---|---|---|
| 1 | Rounded cactus seedling | Bent sapling with one canopy | Striped seed |
| 2 | First arm | Second branch/canopy | Stem and paired cotyledons |
| 3 | Opposing arm | Left branch, three canopies | Heart-shaped leaves and closed bud |
| 4 | Taller ribs and closed flower bud | Upper branch, four canopies | First open flower |
| 5 | Open pink flower | Fifth canopy and blossoms | Full sun head and upper leaves |
| 6 | Second flower and basal pup | Mature crown and fuller branching | Larger head and secondary flowering branch |

The sunflower preserves its previous species-specific bud at stage 3 and first
flower at stage 4. Account growth thresholds and labels are unchanged. The three
other pending plants retain their original art and animation hooks.
