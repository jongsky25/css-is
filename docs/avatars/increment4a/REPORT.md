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
