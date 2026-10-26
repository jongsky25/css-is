# Geometry lifecycle candidate — awaiting memory gate

The counterbalanced source screen identifies geometry observation as a lead:
disabling only observer registrations improves navigation-10/20 RSS in both
orders by approximately 15–29 MiB, without a >10 MiB worsening elsewhere.
See [screen](../source-isolation/REPORT.md). This does not establish acceptance.

The candidate replaces per-wrapper observer closures with one shared geometry
observer, observing the body, wrappers and play containers. Its callback measures
currently connected wrappers after layout. On non-persisted pagehide it disconnects
the observer and cancels a pending geometry RAF; persisted pages keep their state.
Artwork, avatar CSS, audio and search are byte-identical to f700187. The only
template change is the runtime cache version.

Nine real-browser checks pass. The first four cover: resize/scroll/drag/chase, transition geometry,
unused plant-head reads, and shared observation with real navigation teardown.
The existing repeated-runtime-evaluation check confirms stable listener counts.
The additional motion-preference, chase-write, pointer, static-preview and search-boot checks also pass. The new shared-observer regression fails on unchanged f700187 (two wrapper observer owners) and passes on candidate (one).
44 focused accounting checks pass. These are functional results, not memory proof.

Next gate: five full warm-desktop samples for each arm in
original/current/candidate/candidate/current/original order on pinned Chromium
156.0.8078.47. The independent raw/source audit covers every checkpoint and both
orders. Full acceptance and later increments remain paused until this gate passes.

Hosted run: [40315985656](https://github.com/jongsky25/css-is/actions/runs/40315985656), source `cccf843825b5705df5f04242cd25f23fb755280f`. Functional and accounting steps passed; 30-sample memory measurement and independent audit remain pending.
