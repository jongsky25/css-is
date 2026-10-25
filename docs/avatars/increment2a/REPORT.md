# Increment 2A — cactus, bonsai and sunflower

Status: **Complete for the plan's first bounded plant batch. Increment 2B remains pending. Existing release blockers remain.**

Eighteen original authored SVG stages replace cactus, bonsai and sunflower art. Cactus grows rounded ribs, opposing arms, a closed bud, pink flowers and a basal pup. Bonsai develops a curved trunk, connected branching, layered foliage, blossoms and a mature crown. Sunflower develops from a striped seed through cotyledons and a closed bud into a full flower and secondary flowering branch. Species-specific soil, sand/moss/root details and terracotta/shallow ceramic pots share the existing palette.

## Visual and functional acceptance

- All six stages at 64 px and 170 px: [light](before-after-bare-light.png), [dark](before-after-bare-dark.png), [contrast](before-after-bare-contrast.png). Before art comes from `10a7d0d`.
- [51 seasonal sheets](sheets/index.json): 4,896 full-catalog combinations, including every month and witch/vampire/pumpkin/Christmas across three surfaces. Reviewed changed silhouettes and seasonal attachment; generic pot costumes stay below the growth structure. Thirteen untouched species are [pixel-identical across 3,978 cells](unchanged-species.json).
- [Motion recording](before-after-motion.webm): real scripts, play and watering; only the recording's care response is mocked. [Real authenticated mature-plant care](live-plant-care.json) independently verifies response, cooldown, persistence and visible wet soil for all three species.
- [Frozen bloom-turn/mood sheet](bloom-moods-light.png), [watering/mood sheet](water-moods-dark.png), [324 checked stage/mood/theme/reaction cases](motion-rig-check.json). Bloom position and CSS rotation use separate groups; sunflower headwear uses local coordinates. These corrections and the sunflower Seedling/Budding stage fix were made before the accepted measurements.
- **105 relevant tests passed**: care/render/gradient IDs and rig invariants, audio, onboarding storage, appearance policy and browser appearance integration. [Test log](validation-tests.txt). Supplemental care, three paired traces and native visibility/touch checks also passed.
- [Art/anchor contract](ART_CONTRACT.md), [original asset manifest](asset-manifest.json). No imported artwork, runtime dependencies, filters or external assets. Account identity, growth thresholds, wellness scoring, sound behavior, accessibility, care cooldown and seasonal administration are unchanged. No production deployment.

## Controlled performance gates

[20 final raw samples and summary](application/summary.json), [comparison to increment 0](comparison.json). Five runs per desktop/mobile × cold/warm configuration. Each includes 30 seconds idle and at least 30 seconds trusted interaction, full picker selection/scrolling, growth and seasonal previews, real care, offscreen/reduced-motion probes and 20 navigations. Chromium 154.0.8037.57, CPU 1× desktop / 4× mobile proxy, synthetic fixture and dates identical to the original baseline. The matched primary Home fixture remains cat; the full picker includes all changed art. Mature changed plants also receive separate matched Home traces below; this is not a five-run per-species Home benchmark.

Values are median / worst run in milliseconds. Interaction duration uses Event Timing's ≥16 ms reporting floor, per-run medians then median/worst across five runs.

| Configuration | Baseline LCP | Final LCP | Median delta | Interaction frame p95 | Interaction duration |
|---|---:|---:|---:|---:|---:|
| Desktop 1× cold | 324.0 / 660.0 | 352.0 / 680.0 | +28.0 | 16.7 / 16.8 | 16.0 / 32.0 |
| Desktop 1× warm | 120.0 / 232.0 | 148.0 / 208.0 | +28.0 | 16.8 / 16.8 | 32.0 / 32.0 |
| Mobile 4× cold | 576.0 / 720.0 | 560.0 / 664.0 | -16.0 | 16.8 / 16.8 | 32.0 / 40.0 |
| Mobile 4× warm | 260.0 / 288.0 | 248.0 / 296.0 | -12.0 | 16.8 / 16.8 | 32.0 / 40.0 |

- Added compressed avatar CSS+JS: **178 B** over increment 0 (15 KiB budget). `avatars.js` is unchanged; audio sync updates icon text only when it changes.
- Largest median compressed Home document increase: **1248 B** (30 KiB budget).
- Largest median compressed profile/picker document increase: **2299 B** (120 KiB budget). These include actual transferred inline SVG.
- All four LCP median deltas ≤100 ms and interaction median deltas ≤20 ms; every final mobile interaction sample's frame p95 ≤33 ms. Zero JavaScript exceptions and external request attempts.
- Largest matched interaction renderer-RSS median change: **-0.92 MiB**, within the 10 MiB relative budget. Raw JS heap, renderer counts, DOM/listener and navigation trends are retained.

## Gate failure, fix and fresh measurement

The [pre-fix 20-run comparison](pre-sync-fix/comparison.json) failed two gates: cold-desktop LCP median 472 ms (+148 ms versus baseline 324 ms), and one warm-mobile interaction frame p95 of 33.4 ms (33 ms budget; matching baseline warm fixture worst 16.8 ms). All failed samples, native checks and traces are retained under [pre-sync-fix](pre-sync-fix/README.md). They are not part of final acceptance.

The existing `AvatarAudio.sync()` rewrote an unchanged button icon using `textContent`. That child-list mutation triggered the global avatar observer, scheduling another initialization/sync every 200 ms. The final patch checks the icon text before assigning it, breaking this feedback without changing sound preferences, playback or accessibility state. A browser regression test verifies twenty repeated sync calls create zero text mutations in either sound state, while an actual state change still updates the glyph and aria-pressed. The audio script cache key was bumped to v8.12. Native hidden-tab measurements record **30 → 0 observer-scheduled init callbacks over 30 seconds**, confirming this specific repeating feedback is removed; chase/idle/roam timers remain.

The [investigation plan](investigation-plan.json) initially proposed five extra desktop runs; it was explicitly superseded **before collecting them** when the warm-frame miss required a source change. Final acceptance uses a fresh full 20 on the fixed code, with all original 20 preserved. No favorable runs were selected, no failed sample was removed from its cohort, and thresholds were not changed. The final full 20 independently includes the corrected sunflower Seedling/Budding stages.

A [counterbalanced art-only cold-load diagnostic](cold-lcp-diagnostic.json) uses the final optimized audio script for all art versions. Current Home cat SVG is byte-identical to increment 1 after normalizing UUIDs. These 2-second observations supplement the full-duration data; they cannot by themselves attribute the original failures or substitute for the accepted 20. The observed LCP candidate is the account-link notice, so this is page-level timing, not an isolated avatar-paint metric.

| Art version | Diagnostic LCP median | Worst (ms) |
|---|---:|---:|
| current | 304.0 | 796.0 |
| increment0 | 308.0 | 648.0 |
| increment1 | 344.0 | 820.0 |

## Mature plant traces

[Matched before/after 30-second Home input traces](targeted/), each at 4× mobile CPU with a synthetic account that reaches stage 6 through forty fixture-only completed claims. Before art is `10a7d0d`; after art is the accepted batch. Both sides use the final optimized audio script, so this isolates artwork under the accepted runtime. These are diagnostic traces, not the untraced 20-run latency sample set.

| Species | Version | Page-wide tasks >50 ms | Longest identified avatar callback inside those tasks (ms) |
|---|---|---:|---:|
| cactus | before | 8 | 1.169 |
| cactus | after | 4 | No identified call |
| bonsai | before | 5 | 7.579 |
| bonsai | after | 5 | 15.705 |
| sunflower | before | 2 | No identified call |
| sunflower | after | 1 | No identified call |

No identified avatar callback exceeds 50 ms in the final sampled traces. A short callback nested in a long rendering task does not establish that it caused the task. Trace overhead and page-wide rendering cannot be fully attributed; all long tasks and identified calls remain in the raw JSON.

## Limits and remaining work

Native hidden/touch/keyboard checks passed; actual hidden state stops frame callbacks. The inherited release blockers remain: offscreen motion, recurring chase/idle/roam timers, seven animated plant picker thumbnails, and same-document remount listener retention. The unnecessary audio/init feedback is fixed; the remaining lifecycle work is unchanged. The static-picker and lifecycle release gates are **not passed** by this artwork batch; resolve them in motion/integration work before release.

No physical phone was tested. Timer/event probes add overhead and are identical in the baseline and final fixtures. rAF intervals alone do not establish 60 fps. Event Timing misses events below 16 ms and absent entries are not zero. Renderer RSS sums shared resident pages, is not private/PSS memory, and must be compared at identical renderer counts. The primary Home timing fixture measures unchanged cat art; focused changed-species traces cover mature plant behavior but have only one old/new run per species. Worst runs and page-wide long-task variability remain visible.

Next pending batch: **2B — fern, mushroom and succulent across six stages**, preserving frond/cap/spore/plumping hooks and the same visual/performance checks. No wardrobe persistence is included here.

## Reproduction

Run browser workloads sequentially:

```sh
.venv/bin/python scripts/avatar_baseline/slice.py --out docs/avatars/increment2a --before 10a7d0d --kinds cactus,bonsai,sunflower --no-prototypes
.venv/bin/python scripts/avatar_baseline/plant_motion.py
.venv/bin/python scripts/avatar_baseline/sheets.py --out docs/avatars/increment2a/sheets
.venv/bin/python scripts/avatar_baseline/check_unchanged_species.py --before docs/avatars/increment1/sheets --after docs/avatars/increment2a/sheets --changed cactus,bonsai,sunflower
CSS_TEST_NOW=2026-07-15T12:00:00 CSS_AVATAR_BASELINE=1 CSS_AVATAR_MATURE=1 CSS_AVATAR_OUT=docs/avatars/increment2a/application .venv/bin/python -m pytest tests/test_avatar_baseline_browser.py -k plant_care_live_surfaces -s
# Repeat for cactus, bonsai and sunflower:
CSS_TEST_NOW=2026-07-15T12:00:00 CSS_AVATAR_BASELINE=1 CSS_AVATAR_KIND=cactus CSS_AVATAR_MATURE=1 CSS_AVATAR_BEFORE=10a7d0d CSS_AVATAR_OUT=docs/avatars/increment2a/targeted/cactus/application .venv/bin/python -m pytest tests/test_avatar_baseline_browser.py -k slice_long_task_attribution -s
CSS_TEST_NOW=2026-07-15T12:00:00 CSS_AVATAR_BASELINE=1 CSS_AVATAR_OUT=docs/avatars/increment2a/application .venv/bin/python -m pytest tests/test_avatar_baseline_browser.py -k 'real_application_baseline or native_visibility_and_touch' -s
# Supplemental art-only load diagnostic:
CSS_TEST_NOW=2026-07-15T12:00:00 CSS_AVATAR_BASELINE=1 CSS_AVATAR_OUT=docs/avatars/increment2a/application .venv/bin/python -m pytest tests/test_avatar_lcp_diagnostic.py -s
.venv/bin/python scripts/avatar_baseline/summarize.py docs/avatars/increment2a/application
.venv/bin/python scripts/avatar_baseline/compare.py --after docs/avatars/increment2a/application
.venv/bin/python scripts/avatar_baseline/report_plants.py
```

Implementation: `6064a82`; mature-care/trace fixture: `1b453e0`; sync/stage correction: `28fbb7b`. Final evidence and ledger are in the revision containing this report.
