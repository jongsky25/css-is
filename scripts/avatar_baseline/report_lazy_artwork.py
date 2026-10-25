"""Write the latest 2B report from the complete lazy-template cohort."""
import json
from pathlib import Path

root = Path('docs/avatars/increment2b')
out = root / 'lcp-unblock'
read = lambda p: json.loads(p.read_text())
a = read(out / 'assessment.json')
c = read(out / 'comparison.json')
assert c['complete']
assert '260 passed' in (out / 'validation-tests.txt').read_text()
native = read(out / 'application/native-visibility-touch.json')
assert native['hidden_end']['hidden'] and native['hidden_end']['frame_count'] == 0
assert native['touch_drag_changed_style']
care = read(out / 'live-plant-care.json')
assert [r['kind'] for r in care['results']] == ['fern', 'mushroom', 'succulent']
assert all(r['care_persisted'] and r['wet_soil_visible'] for r in care['results'])
rows = []
for group in c['groups']:
    idle = group['scenarios']['home_idle']['lcp_ms']
    frame = group['scenarios']['home_interaction']['frame_p95_ms']['after']
    rows.append(f"| {'Mobile 4×' if group['mobile'] else 'Desktop 1×'} {group['cache']} | {idle['before']['median']:.0f} / {idle['before']['worst']:.0f} | {idle['after']['median']:.0f} / {idle['after']['worst']:.0f} | {idle['median_delta']:+.0f} | {frame['median']:.1f} / {frame['worst']:.1f} |")
matched = a['same_filesystem_control']
accepted = a['status'] == 'complete'
status = '**Accepted. Increment 2B is complete; 3A is next.**' if accepted else '**Blocked. Increment 3A must not start.**'
(root / 'REPORT.md').write_text(f'''# Increment 2B — fern, mushroom and succulent

Status: {status}

The eighteen illustrated plant stages, existing movement hooks and seasonal layers
are preserved. The LCP follow-up begins in `853c93d` and final source
`{a['source_commit'][:7]}` loads only the
requested species artwork template. A single Home companion no longer compiles
all sixteen species. Shared helpers and a fixed allowlist preserve the existing
`species_art`/`costume_back` API and unknown-kind fallback. The follow-up also batches pointer-tracking geometry reads before transform
writes, preserving 3D lean, head tracking and dog excitement/cooldown. Home also moves its responsive search-placeholder query from a parser-blocking
inline script into the existing deferred search initializer. Desktop/mobile text
and Wellness-result navigation are verified. No CSS containment or compositing
hint was shipped. No new dependency, art geometry,
scoring, account, sound or care-policy change.

## Result and retained failures

[Fresh assessment](lcp-unblock/assessment.json) and
[complete comparison](lcp-unblock/comparison.json) contain all gates. The fresh
20 samples use the original fixed Chromium154.0.8037.57, CPU1/4, viewports,
syntheticdate/seed, local gzip, overlay source and30s idle/30s interaction protocol.
Only source-provenance metadata was extended to hash the new template modules
and the Home/search bootstrap sources; benchmark scenario behavior is unchanged.
The earlier stopped lazy-only attempt and all exploratory CSS/thread diagnostics
remain under `lcp-unblock/pre-frame-fix/` and sibling diagnostic directories.
The subsequent stopped `41c8e01` attempt had coldLCP504ms (+132ms vs matched
control) and is retained under `lcp-unblock/pre-startup-fix/`.
No sample was dropped or substituted and no budget was relaxed.

| Fixture | Increment0 LCP median/worst ms | Fresh LCP median/worst ms | Median delta ms | Interaction frame p95 median/worst ms |
|---|---:|---:|---:|---:|
{chr(10).join(rows)}

Cold desktop also compares with the retained original-source same-filesystem
control: current values **{matched['current_values_ms']}**, median
**{matched['current_median_ms']:.0f}ms**, worst **{matched['current_worst_ms']:.0f}ms**;
control median **{matched['control_median_ms']:.0f}ms**, worst
**{matched['control_worst_ms']:.0f}ms**. Delta **{matched['median_delta_ms']:+.0f}ms**
against the unchanged100ms budget. Matched gate: **{'PASS' if matched['passed'] else 'FAIL'}**.

The original failed20 remain intact in `application/`; their median664ms and
+292ms versus the corrected control are preserved in
[the blocked assessment](assessment-blocked.json) and
[the original blocked report](REPORT-blocked.md). Exploratory tmpfs controls,
corrected overlay controls and all earlier navigation/compositing diagnostics
remain separate from the fresh acceptance cohort.

## Attribution and implementation

[Server profiling before](lcp-unblock/server/server-template-profile.txt) showed
~1.47million calls and629ms in the first Home render, dominated by compilation.
[After splitting](lcp-unblock/lazy-server/server-template-profile.txt), that render
used ~0.77million calls and320ms. Later warm renders were small in both cases.
These are instrumented diagnostics, not acceptance timings. Older artwork also
paid substantial compilation cost; this identifies avoidable startup work but
does not prove it caused every earlier run-to-run LCP variation or resource delay.
The [startup trace](lcp-unblock/startup-diagnostic/startup-trace.json) also showed
a large native layout pass while parsing was paused before a mid-body viewport
script. Moving that query into deferred search initialization removes that parser
interruption. A [five-pair startup diagnostic](lcp-unblock/placeholder-diagnostic/summary.json)
had medians392ms before/364ms after; trace/profile/routing overhead and2s duration
make this attribution evidence only. The full browser cohort above determines acceptance.

Artwork now lives under `templates/_avatar_species/`, with helpers in
`templates/_avatars_shared.html` and the existing `_avatars_art.html` dispatcher.
The single-companion cache check proves only its species module is compiled.
[1,734 SVG-equivalence checks](lcp-unblock/artwork-equivalence.json) cover all16
species×6stages×17outfits plus the unknown-kind fallback. Only interelement
whitespace is normalized; path bytes, attributes, text and deterministic IDs
match exactly. Shared CSS/defs match except for the runtime cache-key bump. This carries forward the
[51 visual sheets](sheets/index.json), [64px/170px comparisons](before-after-bare-light.png),
[486 motion cases and21 reduced-motion transitions](motion-rig-check.json),
[3,978 unchanged-species pixel cells](unchanged-species.json), and
[fresh mature-plant matched traces](lcp-unblock/targeted/fern/long-task-attribution.json).
SVG geometry and CSS remain unchanged. The new pointer-read batching is separately
compared against the pre-batching script in
[paired runtime traces](lcp-unblock/batch-diagnostic/interaction-trace.json).
[Pointer behavior](lcp-unblock/pointer-behavior.json) verifies lean, head-angle limits
and reset outside the companion for cat/dog/bird/owl. The refreshed mature-plant traces exercise the final pointer runtime; each
recorded avatar callback meets50ms. Historical botanical traces remain preserved
under `targeted/` and predate this runtime change.

## Functional verification and limits

- [260 tests passed](lcp-unblock/validation-tests.txt), including bounded lazy compilation,
  rendering, care, audio, onboarding, seasonal policy and browser integration.
- [Home search boot](lcp-unblock/home-search-boot.json) verifies responsive
  placeholders and actual search-result navigation on desktop/mobile.
- [Real authenticated mature-plant care](lcp-unblock/live-plant-care.json) verifies
  Home→Wellness→carePOST→SQLite timestamp→wet-soil response for fern/mushroom/succulent.
- [Native hidden/touch/keyboard check](lcp-unblock/application/native-visibility-touch.json)
  confirms document.hidden and zero hidden rAF frames, plus working drag/keyboard.
- [All20 raw samples](lcp-unblock/application/summary.json) retain page-wide long tasks,
  script errors/external attempts, resource timings, memory and navigation trends.
  [Runner log](lcp-unblock/performance-tests.txt).
- CSS+JS added: {c['css_js_gzip_delta_bytes']}B. Maximum median Home increase:
  {max(g['home_encoded_delta'] for g in c['groups']):.0f}B; picker:
  {max(g['picker_encoded_delta'] for g in c['groups']):.0f}B. Complete compressed
  HTTP documents include inline SVG. No new runtime dependency or external asset.

The stopped lazy-only attempt passed cold-desktop LCP at408ms but had a183.3ms
mobile interaction framep95. An exploratory trace reproduced116.7ms. Those failed
samples remain; GPU-root promotion and layout containment were not shipped.
Batching addresses an identified read/write layout flush, but does not establish
that it explains every earlier timing spike. The fresh complete matrix above
alone determines the final measured gates.

This is a local throttled-browser result, not a physical-phone/60fps claim.
Event Timing has a16ms reporting floor; page-wide long tasks do not establish
avatar attribution. Renderer RSS includes shared pages and is not private/PSS.
The full matrix uses forced-active automation; the separate native check proves
actual hidden behavior. Offscreen motion, chase/idle/roam timers, seven animated
picker thumbnails and same-document listener retention remain separate release
blockers. No production deployment, wardrobe persistence or 3A implementation.

## Reproduce

```sh
.venv/bin/python scripts/avatar_baseline/check_lazy_equivalence.py
.venv/bin/python -m pytest tests/test_avatar_care.py tests/test_avatar_audio.py tests/test_onboarding_storage.py tests/test_appearance.py tests/test_appearance_browser.py tests/test_search.py tests/test_search_sources.py tests/test_search_telemetry.py tests/test_home_assistant_box.py tests/test_office_connect.py tests/test_home_request_reads.py tests/test_home_feeds.py tests/test_calendar_week_ahead.py
# Use a fresh output directory; preserve every prior cohort.
CSS_TEST_NOW=2026-07-15T12:00:00 CSS_AVATAR_BASELINE=1 CSS_AVATAR_RUNS=5 CSS_AVATAR_SECONDS=30 CSS_AVATAR_OUT=<fresh>/application .venv/bin/python -m pytest tests/test_avatar_baseline_browser.py -k real_application_baseline -s
.venv/bin/python scripts/avatar_baseline/summarize.py docs/avatars/increment2b/lcp-unblock/application
.venv/bin/python scripts/avatar_baseline/compare.py --after docs/avatars/increment2b/lcp-unblock/application
.venv/bin/python scripts/avatar_baseline/assess_lazy_artwork.py
.venv/bin/python scripts/avatar_baseline/report_lazy_artwork.py
```
''')
(root / 'assessment.json').write_text(json.dumps(a, indent=2))
print('Latest 2B report status:', a['status'])
