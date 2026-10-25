# Increment 1 — cat and blossom plant slice

Status: **Complete for the bounded two-species increment. Existing release blockers remain.**

Six stages of original authored SVG replace the cat and blossom plant. The cat gains changing head/body proportions, paws, muzzle, curled tail, haunches, cheek/chest/ear tufts and expressive eyes. The plant develops a germinating seed, sprout, leafy seedling, closed buds, open blooms and flowering branches. Storage stage labels, growth scoring, care cooldowns, account identity, sounds and global appearance policy are unchanged.

## Visual and functional evidence

- [Bare before/after — light](before-after-bare-light.png), [dark](before-after-bare-dark.png), [contrast](before-after-bare-contrast.png): all six stages at 64 px and 170 px. Pre-upgrade macros are read from commit `1c964dc`.
- [Gallery prototypes](before-after-light.png): one bandana and one pot wrap attached to actual per-stage owning groups. They have no persistence and never appear on normal application surfaces.
- [Before/after motion recording](before-after-motion.webm): real avatar scripts, play and care reactions. Sound remains off by default. The recording uses a development-only mocked care response; real care persistence is verified by the application runner.
- [51 seasonal/monthly sheets](sheets/index.json) cover 4,896 combinations across light/dark/contrast. The two revised species were reviewed for silhouette, shading, growth and seasonal attachment. The other fourteen species remain unchanged: [4,284 pixel-identical cells](unchanged-species.json).
- [Token/anchor contract](ART_CONTRACT.md), [original-asset manifest](asset-manifest.json), [growth semantics equivalence](plant-semantics-equivalence.json). Local UUID-prefixed SVG gradients prevent collisions between copies. Seasonal live updates continue replacing only existing costume/accessory children, preserving body state and local gradient references.
- **102 relevant tests passed**, including render/care, audio, onboarding storage and real appearance browser checks. New tests verify local gradient references, unique IDs, behavioral anchors, empty normal-surface prototype slots and Seedling/Budding/In bloom stage semantics.

## Final controlled performance comparison

Twenty final samples: five per desktop/mobile × cold/warm configuration, each with 30 seconds idle and at least 30 seconds trusted input. Chromium 154.0.8037.57, CPU 1× desktop / 4× mobile proxy, identical synthetic account sequence and dates to increment 0. No physical-device claim. [Raw results](application/), [summary](application/summary.json), [machine-readable comparison](comparison.json).

Values show **median / worst run**, milliseconds. LCP delta compares medians. Reported interaction duration uses Event Timing’s ≥16 ms floor, with per-run medians then median/worst across five runs.

| Configuration | Baseline LCP | Final LCP | Median delta | Final interaction frame p95 | Final interaction duration |
|---|---:|---:|---:|---:|---:|
| Desktop 1× cold | 324.0 / 660.0 | 332.0 / 628.0 | +8.0 | 16.7 / 16.8 | 16.0 / 32.0 |
| Desktop 1× warm | 120.0 / 232.0 | 124.0 / 156.0 | +4.0 | 16.7 / 16.8 | 24.0 / 32.0 |
| Mobile 4× cold | 576.0 / 720.0 | 516.0 / 584.0 | -60.0 | 16.8 / 16.8 | 24.0 / 32.0 |
| Mobile 4× warm | 260.0 / 288.0 | 248.0 / 280.0 | -12.0 | 16.7 / 16.8 | 24.0 / 32.0 |

Measured gates:

- Added compressed avatar CSS+JS: **124 B**, below 15 KiB. The two runtime JavaScript files are byte-identical to baseline; zero dependencies added.
- Largest median compressed Home document increase: **1245 B**, below 30 KiB.
- Largest median compressed profile/picker increase: **2008 B**, below 120 KiB. These are actual complete HTTP documents, including inline SVG, not template file sizes.
- All four median LCP deltas are ≤100 ms; interaction-duration deltas are ≤20 ms; every final mobile interaction sample has frame p95 ≤33 ms. No runtime JavaScript exceptions or external requests occurred.
- Largest matched interaction renderer-RSS median change: **-1.46 MiB**, below 10 MiB. Raw JS heap, renderer count, DOM/listener and 20-navigation trends are retained. RSS sums shared resident pages and is not private/PSS memory; compare identical process counts/scenarios.

## Paint-cost investigation

Initial aggregate results passed the byte/latency/frame/memory comparisons, but warm mobile showed more page-wide long tasks. Targeted traces found expensive avatar callbacks in one replay and reproduced expensive callbacks in the unchanged baseline in another. We retained those results under [pre-shadow-optimization](pre-shadow-optimization/) rather than discard them.

The final two-species rendering removes the inherited SVG drop-shadow and droopy color filter. Both species already draw their own ground shadows; droopy mood retains pose/eyelid cues with 0.86 opacity. Other species keep their existing filter policy. The final native check asserts the illustrated SVG filter is `none`.

[Final paired warm-mobile trace](long-task-attribution.json): 30 seconds per old/new art version, same trusted input and 4× CPU throttle. Callback durations below are taken from actual avatar-script FunctionCall events inside long tasks; a short avatar call within a long rendering task does not establish that the avatar caused that whole task.

- before: 5 page-wide long tasks; longest identified avatar callback 5.008 ms; 0 identified avatar callbacks >50 ms.
- after: 2 page-wide long tasks; longest identified avatar callback 8.683 ms; 0 identified avatar callbacks >50 ms.

No new avatar callback over 50 ms was observed in the final targeted trace. Page-wide rendering/trace overhead cannot be fully attributed by this probe, so it is not a proof that every paint task is avatar-independent. The final untraced 20-sample measurements, including all outliers, are authoritative for latency/frame comparisons. Cold server/template warm-up and long-task variability remain visible in worst-run results.

## Boundaries and remaining release issues

Native hidden/touch/keyboard checks passed on the final code. Actual hidden state stops frame callbacks; the pre-existing chase/init/idle/roam timers, offscreen motion, seven animated plant picker thumbnails and same-document remount listener retention are still recorded. This increment adds no scheduling code and does not claim those release gates pass. Resolve them during motion/integration work before release.

Only two species were redesigned. No wardrobe persistence or controls, library import, framework, animation player, external service, new global theme, deployment or scoring change was introduced. Normal user surfaces render the chosen stage and no gallery-only equipment. Phase 2 is next; release readiness still requires the later regression/integration gates.

Reproduce:

```sh
.venv/bin/python scripts/avatar_baseline/slice.py
.venv/bin/python scripts/avatar_baseline/sheets.py --out docs/avatars/increment1/sheets
CSS_TEST_NOW=2026-07-15T12:00:00 CSS_AVATAR_BASELINE=1 CSS_AVATAR_OUT=docs/avatars/increment1/application \
  .venv/bin/python -m pytest tests/test_avatar_baseline_browser.py -s
.venv/bin/python scripts/avatar_baseline/summarize.py docs/avatars/increment1/application
.venv/bin/python scripts/avatar_baseline/compare.py
.venv/bin/python scripts/avatar_baseline/check_slice_equivalence.py
```

Run browser workloads sequentially. Playwright video capture requires its ffmpeg helper. The standalone equivalence check isolates the stage-3/4 art correction; final performance data independently covers the full filter-free implementation.

Implementation commits: `58cf98f` (slice), `0be7fc3` (ear rig), `ad4e7ad` (stage semantics), `d464461` (drawn-shadow optimization and verification tooling). Visuals, raw results and ledger are in the evidence revision containing this report.
