# Increment 0 baseline — completed 2026-10-25

Status: **Complete: reproducible baseline established. Release gates are not passed.**
No production artwork, behavior, account model, stylesheet or route changed. Increment 1 is the next pending increment. No deployment performed.

## Reproduction and evidence

- [Commands, environment and inventory](README.md); runner: `tests/test_avatar_baseline_browser.py`.
- [Environment and source hashes](application/environment.json); [timing-start provenance](application/timing-start-environment.json). System Chromium 154.0.8037.57; Playwright 1.62.0; synthetic accounts and copied temporary SQLite database only.
- [Raw desktop cold](application/False-cold.json), [desktop warm](application/False-warm.json), [mobile cold](application/True-cold.json), [mobile warm](application/True-warm.json); [complete summary](application/summary.json).
- [Native visibility, touch and keyboard evidence](application/native-visibility-touch.json); [earlier remount probe](baseline/lifecycle.json).
- [51 visual sheets and index](sheets/index.json): all 96 combinations at 64 px, bare plus all 12 months and four explicit seasonal outfits, each on light/dark/high-contrast backgrounds. [Earlier hero/mood sheets](smoke/) retain all three moods. Real application Home and profile captures are under `application/`.
- Four full application cases passed (20 timing samples); the separate native lifecycle/touch case passed. The final relevant regression suite passed 100 tests, with five opt-in baseline cases skipped in the ordinary run. Existing Starlette/httpx deprecation warning only.

## Controlled measurements

Twenty samples: five per viewport/cache configuration. Each contains 30 seconds of Home idle and at least 30 seconds of trusted petting/tapping/cursor/drag input. Desktop 1440 × 1000 at CPU 1×; mobile proxy 390 × 844 at CPU 4×. Timing sweep ran sequentially without competing browser probes. The four cases took 29 min 23 s in total.

The synthetic stage-1 cat starts uncared in each case; successful Wellness care writes persist across the five runs, so later Home samples are happy. Reproduce the whole sequence for comparisons. Server date is July 15, 2026; browser noon and random seed are controlled without replacing Performance APIs.

Values are **median / worst run**, in ms. Interaction duration is the median reported Event Timing duration within each run, then median/worst across five runs; events below the 16 ms reporting floor are absent. Raw entries remain available.

| Configuration | Home LCP | Idle frame p95 | Interaction frame p95 | Interaction duration |
|---|---:|---:|---:|---:|
| Desktop 1× cold | 324.0 / 660.0 | 16.8 / 16.8 | 16.8 / 16.8 | 32.0 / 32.0 |
| Desktop 1× warm | 120.0 / 232.0 | 16.7 / 16.8 | 16.7 / 16.8 | 32.0 / 32.0 |
| Mobile 4× cold | 576.0 / 720.0 | 16.7 / 16.8 | 16.8 / 50.0 | 32.0 / 40.0 |
| Mobile 4× warm | 260.0 / 288.0 | 16.7 / 16.8 | 16.8 / 16.8 | 32.0 / 32.0 |

The second cold mobile run missed 33 ms (50 ms frame p95), with page-wide long tasks up to 582 ms. The remaining nine mobile interaction samples were near 16.8 ms. The slow sample is retained, not discarded or replaced. Inspection confirmed substantial main-thread work during that sample; the PerformanceLongTask probe cannot attribute it to a particular script or paint operation. Root cause remains unresolved. These results do not establish a 60 fps or real-phone claim.

## Transfer and memory baseline

Actual GZip HTTP encoded document medians: Home **24,807 B**, full profile/picker **29,145 B** (whole pages including inline SVG). Cold avatar/audio script bodies total **14,676 B**; warm navigations validate cached scripts with small 304 responses. Response encodings, transfer/body sizes and cache behavior are retained per sample. These are whole-document values, not template sizes or claims that all document bytes belong to avatars. Standalone CSS gzip estimate remains 4,034 B; inline CSS is also included in actual document transfers.

Production changes add **0 B** of CSS/JS, markup or assets, **zero runtime JavaScript dependencies**, and **zero external requests** in the recorded application scenarios. The relative LCP, interaction and memory gates become before/after comparisons in increment 1; no improvement or regression is inferred from a baseline-only change.

Memory values below are MiB, median / worst. Renderer RSS sums resident pages across renderer processes and may count shared pages more than once; it is not private/PSS or avatar-only memory. Compare identical scenarios and renderer counts. JS heap changes compare navigation 1 and navigation 20 without forcing GC.

| Configuration | Interaction renderer RSS | JS heap change after navigation sequence |
|---|---:|---:|
| Desktop 1× cold | 240.4 / 294.5 | -4.1 / -2.5 |
| Desktop 1× warm | 243.0 / 246.5 | -4.2 / -0.1 |
| Mobile 4× cold | 281.1 / 281.9 | -1.7 / 1.7 |
| Mobile 4× warm | 230.8 / 237.9 | -3.2 / 1.7 |

There is no consistent increasing JS-heap trend across the navigation samples; the largest final-minus-initial heap increase is about 1.8 MiB. Document pointer listener counts remain flat across real navigations. This does not override the separately confirmed same-document remount leak. Raw DOM counts expose garbage collection rather than hiding drops or transient growth.

## Lifecycle, interaction and functional findings

- All 16 real profile radios were checked and scrolled; growth was rendered; all four seasonal outfits were verified in the real administrator preview iframe. Care returned a successful JSON response and a persisted timestamp in the temporary database, including subsequent cooldown responses. Existing appearance browser tests cover publishing, live updates, unsaved form preservation and mobile/contrast behavior. Wardrobe is not yet implemented and is N/A for this baseline.
- Native Chromium tabs connected with `no_defaults=True` produced **document.hidden=true and zero frame callbacks for 30 seconds**. This avoids Playwright’s default forced-active-page emulation. The ordinary timing sweep’s `hidden_verified=false` records that automation limitation; it is not hidden-state evidence.
- **Existing hidden timer work:** over those 30 hidden seconds, chase checks ran 30 times, initialization/MutationObserver callbacks 30 times, idle callbacks twice and roam callbacks three times. The five-minute sleep timer is not the only scheduled work. CSS animation objects remain logically running, although native hidden rendering stops frame callbacks.
- **Existing offscreen work:** the native 30-second offscreen observation recorded 1,802 frame callbacks and one active avatar animation; chase, idle, roam and initialization callbacks continued. Reduced motion stopped avatar CSS animations in all 20 main samples.
- **Existing initialization feedback:** `initAll()` calls `AvatarAudio.sync()`, which replaces the sound button text; the child-list MutationObserver schedules `initAll()` again. The native probe recorded about 5 initialization callbacks per second while offscreen, throttled to about 1 per second hidden. Fix this within motion/lifecycle work rather than silently modifying the measured baseline.
- **Existing static-picker gate failure:** all seven plant thumbnails have running `av-sway` animations concurrently. Native evidence lists each species. The ordinary wrapper-only animation counter does not detect these SVG-only picker spans; use the native picker list for this gate.
- **Existing remount leak:** twenty same-document macro remounts increased document pointermove listeners from 2 to 22. Real full-document navigation did not reproduce listener accumulation. Preserve both results; they exercise different lifetimes.
- Trusted native touch dragging changed Home companion position; a keyboard ArrowLeft nudge changed it again. Tests assert both actions and preserve the saved style in native evidence.

## Visual review and limits

All 51 compact sheets rendered 96 cells with unique IDs. Review of bare, witch, vampire, pumpkin and Christmas sheets across the three surfaces, plus the [all-month mature-stage overview](sheets/monthly-stage6-overview.png), confirms recognizable catalog silhouettes, six-stage progression and baseline seasonal attachment. Existing contrast weaknesses include the very pale rabbit and some muted plant/animal details on light backgrounds; there is no new visual polish in this increment. Hero/mood and all monthly sheets are retained for future before/after comparison. Production profile captures demonstrate the actual catalog and growth UI; full-page captures taken after scrolling may place sticky navigation within the image. Native theme captures begin from the profile navigation and provide cleaner surface references.

No imported artwork or third-party asset library was added. Physical-device testing, precise private renderer memory and script-level long-task attribution are unavailable in this baseline. Release readiness remains blocked by the documented frame, picker, lifecycle and remount issues. Do not relax budgets or claim these gates pass. The next artwork increment must preserve the relative gates and compare the same fixtures against this baseline; lifecycle/picker issues must be fixed before release.

Implementation commit: `94269dd` plus the evidence/ledger revision containing this report. The initial incomplete smoke results remain historical evidence, not the accepted timing baseline.
