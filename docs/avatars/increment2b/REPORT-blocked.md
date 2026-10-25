# Increment 2B — fern, mushroom and succulent

Status: **Artwork implemented; increment 2B is blocked by the cold-desktop LCP gate. Increment 3A has not started.**

Eighteen original authored SVG stages finish the seven-plant artwork collection; performance acceptance remains incomplete. Fern develops from a coiled fiddlehead through unfurling shoots into a six-frond crown with sori. Mushroom develops a domed coral cap, expressive cream stalk, gills, a veil ring and a small fruiting cluster. Succulent develops layered fleshy rosettes, blushed tips, a closed bud, open flowers and a connected basal offset in a shallow glazed bowl. Growth thresholds/names, account identity, scoring, sounds and care cooldowns are unchanged.

## Visual and functional evidence

- All six stages at 64 px and 170 px, before/after: [light](before-after-bare-light.png), [dark](before-after-bare-dark.png), [contrast](before-after-bare-contrast.png). Before art is `5b580d9`.
- [51 monthly/seasonal sheets](sheets/index.json), 4,896 full-catalog combinations across three surfaces, including witch/vampire/pumpkin/Christmas. Reviewed changed silhouettes, distinct growth, cap headwear and pot-costume clearance. [Thirteen untouched species are pixel-identical across 3,978 cells](unchanged-species.json).
- [Motion recording](before-after-motion.webm) uses real scripts with play/watering and default-off sound. Only its care response is mocked. [Real authenticated mature-plant care](live-plant-care.json) independently confirms Home/Wellness rendering, persisted timestamps, cooldown and wet-soil visibility for each species.
- [486 phase/stage/mood/theme cases](motion-rig-check.json) exercise relevant ripple, wobble, spore, blink, plump, blossom and watering states. Part centers stay inside the SVG and expected animation names are checked. Twenty-one reduced-motion transitions leave zero animated SVG styles. Example sheets: [ripple](ripple-moods-light.png), [cap wobble](wobble-moods-dark.png), [spores](spore-moods-light.png), [plump](plump-moods-light.png), [watering](water-moods-dark.png).
- **107 relevant tests passed**: render/care, local IDs, rig invariants, stage semantics, seasonal replacement-slot order, audio, onboarding storage, appearance policy and browser integration. [Test log](validation-tests.txt). Real care, native hidden/touch/keyboard checks and three paired plant traces also passed.
- [Art/anchor contract](ART_CONTRACT.md), [original asset manifest](asset-manifest.json). Scope-local leaf/cap gradients and drawn shadows; no imported graphics, new runtime dependencies, filters, external assets or JavaScript changes. Seasonal slots retain back/accessory/front order at every stage/outfit, and mushroom headwear stays cap-owned.

## Bounded motion/accessibility corrections

The existing static-idle succulent rule outranked its intended occasional `av-do-plump`. A species-scoped selector restores that reaction while preserving reduced-motion suppression. It adds no scheduling code. A reduced-motion transition during watering also exposed animated drop paths without classes escaping the class-based media rule; the same media rule now explicitly suppresses those paths. The browser matrix validates both fixes before acceptance measurements. Frond/cap/spore/blossom positioning belongs to plain outer groups, with animated inner groups, so CSS never replaces SVG placement.

## Controlled performance gates

[20 raw samples and summary](application/summary.json), [comparison to increment 0](comparison.json). Five runs per desktop/mobile × cold/warm configuration. Each includes 30 seconds idle and at least 30 seconds trusted interaction, full picker selection/scrolling, growth and seasonal previews, real care, offscreen/reduced-motion probes and 20 navigations. Chromium 154.0.8037.57, CPU 1× desktop / 4× mobile proxy, same synthetic fixtures, dates and seeded randomness as the original baseline. Source revision: `6ddce82`; runtime source hashes are retained in environment metadata.

Values are median / worst run in milliseconds. Event Timing uses its ≥16 ms reporting floor; interaction values are per-run medians then median/worst across five runs.

| Configuration | Baseline LCP | Final LCP | Median delta | Interaction frame p95 | Interaction duration |
|---|---:|---:|---:|---:|---:|
| Desktop 1× cold | 324.0 / 660.0 | 664.0 / 812.0 | +340.0 | 16.8 / 16.8 | 32.0 / 32.0 |
| Desktop 1× warm | 120.0 / 232.0 | 156.0 / 180.0 | +36.0 | 16.7 / 16.8 | 32.0 / 32.0 |
| Mobile 4× cold | 576.0 / 720.0 | 576.0 / 792.0 | +0.0 | 16.8 / 16.8 | 32.0 / 32.0 |
| Mobile 4× warm | 260.0 / 288.0 | 236.0 / 272.0 | -24.0 | 16.8 / 16.8 | 32.0 / 32.0 |

- Added compressed avatar CSS+JS: **188 B** over increment 0 (15 KiB budget). Both runtime JS files are byte-identical to increment 2A.
- Largest median compressed Home document increase: **1259 B** (30 KiB budget).
- Largest median compressed profile/picker increase: **2648 B** (120 KiB budget). Complete HTTP documents include transferred inline SVG.
- **Cold-desktop LCP failed:** median 664 ms versus historical 324 ms, +340 ms (100 ms budget). The other three Home LCP configurations passed. All Home interaction deltas are ≤20 ms, and every mobile interaction sample has frame p95 ≤33 ms. Zero runtime JavaScript exceptions and external request attempts.
- Largest matched interaction renderer-RSS median change: **-1.71 MiB**, within 10 MiB. Raw JS heap, renderer counts, DOM/listener and 20-navigation trends remain available.

## LCP investigation and blocked acceptance

The [assessment](assessment-blocked.json) retains the failed historical comparison and a corrected same-filesystem original-source control. No current sample was replaced and no budget was changed.

| Desktop cold source | LCP samples (ms) | Median | Worst |
|---|---|---:|---:|
| Current `6ddce82` | 812, 336, 664, 728, 308 | 664 | 812 |
| Original `1c964dc`, overlayfs control | 724, 320, 372, 320, 376 | 372 | 724 |

The corrected control still gives **+292 ms** current-build regression, exceeding the same 100 ms budget. **This batch is not accepted.** The measured gate is page-level LCP, so unchanged Home cat artwork does not excuse the failure.

[Protocol proof](control-protocol-proof.json) verifies that the original primary benchmark, reset, snapshot and browser probe match the initially measured current protocol; fixture setup, dependency file, storage and auth source are also identical. The [predeclared investigation](investigation-plan.json) reproduces exactly five original-source full-duration cold-desktop runs. The first [tmpfs control](reproduced-control/README.md) used a different source filesystem and is retained as exploratory evidence. The corrected [overlayfs control](reproduced-overlay-control/application/summary.json) asserts matching filesystem types and uses the immutable original source, same browser/Python/Playwright, fixture date/seed, viewport, CPU1, compression and full scenario sequence. All five results are retained, regardless of outcome.

[Three instrumented full-scenario runs](navigation-diagnostic/application/False-cold.json), not acceptance resamples, recorded LCPs 720/572/412 ms, HTML TTFB 441.0/133.5/54.4 ms and DOM-interactive times 631.1/424.9/302.7 ms. The LCP candidate is the account-link notice. Several unrelated first-party scripts also took 100–240 ms in the second run. This locates response/static-resource and page-startup delays but does not establish a causal avatar hot path. Navigation/resource instrumentation was added in `a607092` for further investigation; production artwork/CSS remains `6ddce82`.

The [2-second counterbalanced art-only diagnostic](lcp-investigation/cold-lcp-diagnostic.json) had medians current 328/original 340/previous-art 364 ms. Home cat SVG is identical to the earlier foundation after normalizing UUIDs. A test-only compositing variant had median 316 ms, a 12 ms difference; it was not applied to production code. These short observations neither reproduce nor override the complete-fixture failure. They share current runtime JavaScript for art isolation and are not a full original-build control.

Picker/growth, seasonal-preview and care LCP/interaction/memory deltas pass their recorded budgets; [secondary scenario checks](assessment-blocked.json) retain all values. The unresolved gate is cold-desktop Home LCP. Next required work is attribution of response/static-resource and full-scenario startup delay, followed by a demonstrated fix and fresh gate validation. **Do not advance to 3A while this gate is failed.**

## Mature plant traces

[Matched old/new 30-second Home input traces](targeted/), one pair per mature plant at 4× mobile CPU. Forty fixture-only completed claims produce stage 6 through the real growth calculation. Before art is `5b580d9`; after art is the implemented batch. Both sides use the unchanged runtime JavaScript; template CSS follows each art revision. The primary 20-run Home timing fixture remains cat for historical comparability; the full picker includes the changed plants. These focused traces are additional diagnostics, not five-run per-species Home benchmarks.

| Species | Version | Page-wide tasks >50 ms | Longest identified avatar callback inside those tasks (ms) |
|---|---|---:|---:|
| fern | before | 2 | No identified call |
| fern | after | 2 | 1.144 |
| mushroom | before | 1 | No identified call |
| mushroom | after | 7 | 0.313 |
| succulent | before | 3 | No identified call |
| succulent | after | 6 | 24.336 |

No identified avatar callback exceeds 50 ms in the final sampled traces. A short callback nested in a long rendering task does not establish that it caused the task. Trace overhead and page-wide paint costs cannot be fully attributed; raw long-task/paint records and all identified calls are retained. Primary latency/frame comparisons use the original untraced 20 current samples, including the failed LCP result.

## Limits and remaining release work

Native hidden-state verification stops frame callbacks, and touch/keyboard movement still works. Existing offscreen motion, chase/idle/roam timers, seven animated plant picker thumbnails and same-document remount listener retention remain release blockers. The prior audio/init feedback fix remains in place. This batch does **not** claim the static-picker or full lifecycle release gates pass; resolve them during motion/integration work before release.

No physical phone was tested. Timer/event probes add overhead and match the baseline. rAF intervals alone do not prove 60 fps. Event Timing omits events below 16 ms; absent entries are not zero latency. Renderer RSS sums shared resident pages, is not private/PSS memory, and requires matching renderer counts. The primary Home fixture measures unchanged cat artwork; new mature plants have one old/new diagnostic trace each. All worst runs remain reported. No production deployment or wardrobe persistence.

Next pending work: **complete increment 2B’s cold-load investigation and satisfy its gate**. Increment 3A (dog, rabbit, bird and turtle) remains pending.

## Reproduction

Run browser workloads sequentially:

```sh
.venv/bin/python scripts/avatar_baseline/slice.py --out docs/avatars/increment2b --before 5b580d9 --kinds fern,mushroom,succulent --no-prototypes
.venv/bin/python scripts/avatar_baseline/plant_motion.py --out docs/avatars/increment2b --kinds fern,mushroom,succulent --phases ripple,wobble,spore,blink,plump,bloom,water
.venv/bin/python scripts/avatar_baseline/sheets.py --out docs/avatars/increment2b/sheets
.venv/bin/python scripts/avatar_baseline/check_unchanged_species.py --before docs/avatars/increment2a/sheets --after docs/avatars/increment2b/sheets --changed fern,mushroom,succulent
CSS_TEST_NOW=2026-07-15T12:00:00 CSS_AVATAR_BASELINE=1 CSS_AVATAR_MATURE=1 CSS_AVATAR_PLANTS=fern,mushroom,succulent CSS_AVATAR_OUT=docs/avatars/increment2b/application .venv/bin/python -m pytest tests/test_avatar_baseline_browser.py -k plant_care_live_surfaces -s
# Repeat for fern, mushroom and succulent:
CSS_TEST_NOW=2026-07-15T12:00:00 CSS_AVATAR_BASELINE=1 CSS_AVATAR_KIND=fern CSS_AVATAR_MATURE=1 CSS_AVATAR_BEFORE=5b580d9 CSS_AVATAR_OUT=docs/avatars/increment2b/targeted/fern/application .venv/bin/python -m pytest tests/test_avatar_baseline_browser.py -k slice_long_task_attribution -s
CSS_TEST_NOW=2026-07-15T12:00:00 CSS_AVATAR_BASELINE=1 CSS_AVATAR_OUT=docs/avatars/increment2b/application .venv/bin/python -m pytest tests/test_avatar_baseline_browser.py -k 'real_application_baseline or native_visibility_and_touch' -s
.venv/bin/python scripts/avatar_baseline/summarize.py docs/avatars/increment2b/application
.venv/bin/python scripts/avatar_baseline/compare.py --after docs/avatars/increment2b/application
# Preserve current results; reproduce the original control in a fresh output directory:
bash scripts/avatar_baseline/reproduce_cold_control.sh docs/avatars/increment2b/control-replay
# Recreate assessment from retained historical/current/corrected control data:
.venv/bin/python scripts/avatar_baseline/assess_remaining_plants.py
.venv/bin/python scripts/avatar_baseline/report_remaining_plants.py
```

Final evidence and the execution ledger are in the revision containing this report.
