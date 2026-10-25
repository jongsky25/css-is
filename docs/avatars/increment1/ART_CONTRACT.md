# Cat / blossom plant art foundation

Original authored SVG; no third-party assets, upstream vector parts, runtime
libraries, external URLs or new filters. Palette light comes from the upper left.

| Token | Purpose |
|---|---|
| `--av-outline` #815b43 | Warm rounded animal outline, 1–1.5 viewBox units |
| `--av-leaf-outline` #41664c | Botanical outlines and stem base |
| `--av-rose-outline` #b46883 | Blossom contours |
| scoped `fur` | Cream-gold highlight → apricot → terracotta shadow |
| scoped `cream` | Warm white → shaded cream |
| scoped `leaf` | Pale sage highlight → green → cool shadow |

`avatar_svg` generates a UUID prefix for each cat/plant SVG. Gradient definitions
and references stay inside that SVG; other species retain the existing once-per-
page `avg-*` definitions. Live seasonal replacements use the existing shared
costume gradients, so cloning seasonal children cannot import foreign local IDs.

The outer `.avmove` and inner `.avstage` layers remain unchanged. `.av-head`,
`.av-ear-l`, `.av-ear-r`, `.av-tail`, `.av-eye > .av-lid`, `.av-food`, `.av-soil`,
`.av-soilwet`, `.av-bloom`, `.av-acc`, and the two costume groups retain their
behavioral roles. No JavaScript behavior or care/growth/persistence logic changes.

The upgraded SVGs use only drawn ground shadows, with the inherited SVG filter
disabled. Droopy mood retains its pose/eyelid cues and uses 0.86 opacity instead
of a color-matrix filter. Other species keep their existing rendering policy.

| Species | Anchor | Owner | Local coordinates | Draw order |
|---|---|---|---|---|
| Cat | `head` | `.av-head` | (60,49), before headwear | Face → anchor → seasonal hat |
| Cat | `neck` | Growth-scaled `.av-body` | (60,98) | Body/head → costume/regalia → prototype |
| Plant | `pot` | `.av-body` | (60,119) | Pot/stems/blooms → prototype → seasonal ribbon/regalia/costume |

Cat coordinates are inside the retained `translate(60 96) scale(stage)` costume
rig; accessory geometry must not apply that scale a second time. Plant anchors
are unscaled viewBox coordinates. Each anchor uses an empty group with stable
`data-anchor`; no persistence or user-supplied markup is accepted.

Gallery-only bandana and pot-wrap prototypes are injected by `slice.py` into
these actual owning groups. They are shown alongside the existing earned regalia
intentionally; this is a layering proof, not the future wardrobe precedence model.
Normal application renders have empty prototype anchors and no equipment UI.

Growth: cat stages add whiskers, a fully curled tail / mature body proportions,
haunches and cheek tufts, chest ruff, then ear tufts. Plant stages progress from a
split germinating seed, two leaves, a leafy seedling, closed buds on a side branch, open blooms,
then three blooms with a second branch and fuller leaf structure.

Reproduce before/after 64px and 170px sheets and motion recording:

```sh
.venv/bin/python scripts/avatar_baseline/slice.py
```

Bare contact sheets use the `before-after-bare-*` filenames; the original
`before-after-*` sheets add the gallery prototypes. Motion is recorded in
`before-after-motion.webm`. The script reads pre-upgrade macros from commit `1c964dc`, never from production.
Playwright video capture requires its ffmpeg helper; this environment uses the
installed `/usr/bin/ffmpeg` through the helper's expected local cache path.
