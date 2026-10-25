# Remaining plant artwork and rigs

Original authored inline SVG; no imported graphics, runtime libraries, external
references or filters. Fern/succulent own UUID-prefixed sage leaf gradients;
mushroom owns a UUID-prefixed coral cap gradient. Existing shared cream stem and
terracotta/glazed pot definitions are reused. All three have drawn ground shadows
and use the established illustrated SVG filter policy, including droopy opacity.

| Species | Growth structure | Existing motion/care contract |
|---|---|---|
| Fern | Coiled fiddlehead → unfurling pair → three open fronds → new curled shoot → five-frond fan with sori → six-frond crown | `.av-frond-1..6`, exactly one `.av-frond-top`, wet soil and watering |
| Mushroom | Button → pinhead/face → domed cap/gills → veil ring → broad fruiting cap with one companion → mature cap and two companions | `.av-cap`, `.av-spore`, `.av-head`, `.av-eye > .av-lid`, wet soil |
| Succulent | Fleshy cotyledons → first radial whorl → layered rosette → larger whorl/blushed tips/closed bud → flower → flowering branch and connected basal offset | Whole `.avstage` plump, `.av-bloom`, wet soil and species-specific watered plump |

Fern and mushroom do not gain biologically inappropriate flowers to illustrate
the shared family stage names; their mature fronds/sori and fruiting structures
express those levels. Succulent stages 3/4/5 remain seedling/closed bud/open flower.
Account thresholds, stage names, care cooldowns and scoring are unchanged.

Placement and rotation belong to plain outer groups. CSS ripple/unfurl, cap
wobble, spore rise and blossom turn belong to inner groups with no positioning
transform attribute. This prevents CSS animation from replacing SVG placement.
Mushroom headwear lives inside its cap rig with local coordinates and retains the
existing three seasonal replacement slots (back, accessory, front), in that order.
Fern and succulent retain the same pot-mounted monthly accessory contract.

Pot anchors are empty groups at (60,121). Draw order: costume back → drawn
shadow/pot/soil → main botanical parts and cap/leaf-owned headwear → offsets/cluster
→ pot anchor → pot bow where applicable → earned regalia → seasonal pot front.
Mushroom stems sit inside the soil ellipse, fern soil has moss/grit, and the
succulent has a shallow glazed bowl with grit and an attached offset.

The existing static-idle succulent rule outranked its occasional `av-do-plump`.
A narrowly scoped CSS selector restores that intended selected-companion reaction.
It adds no timer or JavaScript and leaves reduced-motion suppression in force.

A mid-care reduced-motion transition exposed animated water-drop paths without
classes escaping the existing class-based suppression. The same media rule now
explicitly includes `.avwrap .av-drops path`. The browser matrix checks every
SVG descendant after reduced motion is enabled during each reaction, in all
three themes; no animated style may remain. No JavaScript timing logic changes.
