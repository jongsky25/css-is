"""Build the bounded plant-batch report only after required evidence is present."""
import argparse
import json
from pathlib import Path

p=argparse.ArgumentParser();p.add_argument('--out',default='docs/avatars/increment2a');a=p.parse_args();out=Path(a.out)
comparison=json.loads((out/'comparison.json').read_text());summary=json.loads((out/'application/summary.json').read_text())
assert comparison['complete'] and all(comparison['gates'].values()),comparison['gates']
native=json.loads((out/'application/native-visibility-touch.json').read_text())
assert native['hidden_end']['hidden'] and native['touch_drag_changed_style']
assert native['illustrated_svg_filters'] and set(native['illustrated_svg_filters'])=={'none'}
assert json.loads((out/'unchanged-species.json').read_text())['cells']==3978
assert json.loads((out/'motion-rig-check.json').read_text())['cases']==324
care=json.loads((out/'live-plant-care.json').read_text())
assert len(care['results'])==3 and all(r['wet_soil_visible'] and r['care_persisted'] for r in care['results'])
sample_count=summary['samples']
assert sample_count==20, 'Acceptance requires a fresh complete 20 on final source'
initial=json.loads((out/'pre-sync-fix/comparison.json').read_text())
assert not initial['gates']['home_lcp_median_regression_le_100ms']
diag=json.loads((out/'cold-lcp-diagnostic.json').read_text())
assert diag['current_home_cat_svg_identical_to_increment1']
def feedback_ticks(n):
    return sum(value-n['hidden_start']['ticks'].get(key,0) for key,value in n['hidden_end']['ticks'].items() if 'avatars.js' in key and ':820:' in key)
pre_native=json.loads((out/'pre-sync-fix/application/native-visibility-touch.json').read_text())
old_feedback=feedback_ticks(pre_native);new_feedback=feedback_ticks(native)
assert old_feedback>new_feedback, 'Natural hidden-tab observer feedback did not decrease'

diag_rows='\n'.join(f"| {g['version']} | {g['lcp_median_ms']:.1f} | {g['lcp_worst_ms']:.1f} |" for g in diag['groups'])
traces=[]
for kind in ['cactus','bonsai','sunflower']:
    data=json.loads((out/f'targeted/{kind}/long-task-attribution.json').read_text())
    for row in data:
        assert row['kind']==kind and row['mature_fixture']
        calls=[c['duration_ms'] for task in row['trace_long_tasks'] for c in task['calls'] if c['file'].startswith(('avatars.js','avatar-audio.js'))]
        if row['version']=='after':assert max(calls,default=0)<=50
        duration = f"{max(calls):.3f}" if calls else "No identified call"
        traces.append(f"| {kind} | {row['version']} | {len(row['trace_long_tasks'])} | {duration} |")
def pair(metric):return f"{metric['median']:.1f} / {metric['worst']:.1f}"
rows=[]
for group in comparison['groups']:
    idle=group['scenarios']['home_idle']['lcp_ms'];interact=group['scenarios']['home_interaction']
    rows.append(f"| {'Mobile 4×' if group['mobile'] else 'Desktop 1×'} {group['cache']} | {pair(idle['before'])} | {pair(idle['after'])} | {idle['median_delta']:+.1f} | {pair(interact['frame_p95_ms']['after'])} | {pair(interact['interaction_duration_per_run_median_ms']['after'])} |")
max_rss=max(g['scenarios']['home_interaction']['renderer_rss_sum_bytes']['median_delta'] for g in comparison['groups'])/1048576
report=f'''# Increment 2A — cactus, bonsai and sunflower

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
{chr(10).join(rows)}

- Added compressed avatar CSS+JS: **{comparison['css_js_gzip_delta_bytes']} B** over increment 0 (15 KiB budget). `avatars.js` is unchanged; audio sync updates icon text only when it changes.
- Largest median compressed Home document increase: **{max(g['home_encoded_delta'] for g in comparison['groups']):.0f} B** (30 KiB budget).
- Largest median compressed profile/picker document increase: **{max(g['picker_encoded_delta'] for g in comparison['groups']):.0f} B** (120 KiB budget). These include actual transferred inline SVG.
- All four LCP median deltas ≤100 ms and interaction median deltas ≤20 ms; every final mobile interaction sample's frame p95 ≤33 ms. Zero JavaScript exceptions and external request attempts.
- Largest matched interaction renderer-RSS median change: **{max_rss:+.2f} MiB**, within the 10 MiB relative budget. Raw JS heap, renderer counts, DOM/listener and navigation trends are retained.

## Gate failure, fix and fresh measurement

The [pre-fix 20-run comparison](pre-sync-fix/comparison.json) failed two gates: cold-desktop LCP median 472 ms (+148 ms versus baseline 324 ms), and one warm-mobile interaction frame p95 of 33.4 ms (33 ms budget; matching baseline warm fixture worst 16.8 ms). All failed samples, native checks and traces are retained under [pre-sync-fix](pre-sync-fix/README.md). They are not part of final acceptance.

The existing `AvatarAudio.sync()` rewrote an unchanged button icon using `textContent`. That child-list mutation triggered the global avatar observer, scheduling another initialization/sync every 200 ms. The final patch checks the icon text before assigning it, breaking this feedback without changing sound preferences, playback or accessibility state. A browser regression test verifies twenty repeated sync calls create zero text mutations in either sound state, while an actual state change still updates the glyph and aria-pressed. The audio script cache key was bumped to v8.12. Native hidden-tab measurements record **{old_feedback} → {new_feedback} observer-scheduled init callbacks over 30 seconds**, confirming this specific repeating feedback is removed; chase/idle/roam timers remain.

The [investigation plan](investigation-plan.json) initially proposed five extra desktop runs; it was explicitly superseded **before collecting them** when the warm-frame miss required a source change. Final acceptance uses a fresh full 20 on the fixed code, with all original 20 preserved. No favorable runs were selected, no failed sample was removed from its cohort, and thresholds were not changed. The final full 20 independently includes the corrected sunflower Seedling/Budding stages.

A [counterbalanced art-only cold-load diagnostic](cold-lcp-diagnostic.json) uses the final optimized audio script for all art versions. Current Home cat SVG is byte-identical to increment 1 after normalizing UUIDs. These 2-second observations supplement the full-duration data; they cannot by themselves attribute the original failures or substitute for the accepted 20. The observed LCP candidate is the account-link notice, so this is page-level timing, not an isolated avatar-paint metric.

| Art version | Diagnostic LCP median | Worst (ms) |
|---|---:|---:|
{diag_rows}

## Mature plant traces

[Matched before/after 30-second Home input traces](targeted/), each at 4× mobile CPU with a synthetic account that reaches stage 6 through forty fixture-only completed claims. Before art is `10a7d0d`; after art is the accepted batch. Both sides use the final optimized audio script, so this isolates artwork under the accepted runtime. These are diagnostic traces, not the untraced 20-run latency sample set.

| Species | Version | Page-wide tasks >50 ms | Longest identified avatar callback inside those tasks (ms) |
|---|---|---:|---:|
{chr(10).join(traces)}

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
'''
(out/'REPORT.md').write_text(report)
print('Accepted bounded plant report written')
