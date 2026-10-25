"""Write the current 2B report from fresh, complete evidence."""
import json
from pathlib import Path
root=Path('docs/avatars/increment2b');out=root/'lcp-unblock'
read=lambda p:json.loads(p.read_text())
a=read(out/'assessment.json');c=read(out/'comparison.json')
assert c['complete'] and '260 passed' in (out/'validation-tests.txt').read_text()
assert '3 passed' in (out/'static-functional/tests.txt').read_text()
matched=a['same_filesystem_control'];rows=[]
for group in c['groups']:
    idle=group['scenarios']['home_idle']['lcp_ms'];frame=group['scenarios']['home_interaction']['frame_p95_ms']['after']
    rows.append(f"| {'Mobile 4×' if group['mobile'] else 'Desktop 1×'} {group['cache']} | {idle['before']['median']:.0f} / {idle['before']['worst']:.0f} | {idle['after']['median']:.0f} / {idle['after']['worst']:.0f} | {idle['median_delta']:+.0f} | {frame['median']:.1f} / {frame['worst']:.1f} |")
focused=[]
for kind,check in a['avatar_callback_checks'].items():
    samples=check['samples']
    focused.append(f"| {kind} | {max(s['frame_p95_ms'] for s in samples):.1f} | {max(s['max_reported_owned_script_ms'] for s in samples):.1f} | {'PASS' if check['passed'] else 'FAIL'} |")
status='Accepted. Increment 2B is complete; 3A is next.' if a['status']=='complete' else 'Blocked. Increment 3A must not start.'
(root/'REPORT.md').write_text(f'''# Increment 2B — fern, mushroom and succulent

**{status}** Source: `{a['source_commit']}`.

The eighteen illustrated stages retain their original geometry, seasonal layers,
identity and movement hooks. Four bounded performance changes follow the artwork:

- Load only the requested species template, with shared helpers and a fixed allowlist.
- Read pointer geometry before writing transforms.
- Move the Home responsive search-placeholder lookup into its existing deferred initializer.
- Read chase/drag bounds before style writes, skip reflow when starting an absent
  animation class, and keep decorative wrappers and picker cards static. Active
  reaction replay and the selected companion's animation remain functional.

No new runtime dependency, containment/compositing hint, external artwork, scoring,
account, sound or care-policy change was introduced.

## Performance acceptance

[Assessment](lcp-unblock/assessment.json), [comparison](lcp-unblock/comparison.json)
and [all20 raw samples](lcp-unblock/application/summary.json) retain every result.
The original protocol uses Chromium154.0.8037.57, CPU1/4, fixed viewports,
synthetic July15 date/seed, gzip, overlay filesystem, five runs per cache/device
and30s idle/30s interaction. Provenance hashes include the new template modules
and Home/search sources. Budgets and scenario behavior remain unchanged.

| Fixture | Increment0 LCP median/worst ms | Current LCP median/worst ms | Median delta ms | Interaction framep95 median/worst ms |
|---|---:|---:|---:|---:|
{chr(10).join(rows)}

The retained original-source overlay control has cold-desktop median
{matched['control_median_ms']:.0f}ms. Current five values are
**{matched['current_values_ms']}**, median **{matched['current_median_ms']:.0f}ms**,
worst **{matched['current_worst_ms']:.0f}ms**; median delta
**{matched['median_delta_ms']:+.0f}ms** against the unchanged100ms budget.
Secondary care/picker/appearance latency and memory gates are included in the
assessment. Added CSS+JS gzip: **{c['css_js_gzip_delta_bytes']}B**; maximum median
Home document increase **{max(g['home_encoded_delta'] for g in c['groups']):.0f}B**,
picker **{max(g['picker_encoded_delta'] for g in c['groups']):.0f}B**.
Worst samples remain in the raw results; median gates do not exclude them.

Fresh mature-stage6, mobileCPU4 checks use five30s runs per plant and native
LongAnimationFrame attribution, with no API wrappers, tracing recorder, callback
clocks or stack capture. Every run must meet framep95≤33ms and every reported
avatar-owned script≤50ms. Zero reported duration means no owned script in a
reported long frame, not zeroCPU. [Raw native records](lcp-unblock/native-control/fern/native-control.json).

| Species | Worst run framep95 ms | Largest reported owned script ms | Gate |
|---|---:|---:|---|
{chr(10).join(focused)}

## Visual and functional gates

- [1,734 SVG checks](lcp-unblock/artwork-equivalence.json) compare all16species,
  six stages,17outfits and unknown fallback. Only interelement whitespace is
  normalized; paths, attributes, text and deterministic IDs match exactly.
  Shared CSS/defs differ only in the documented static-preview policy and script cache key.
- [51 fresh sheets](lcp-unblock/static-previews/sheets/index.json) cover4,896cells;
  every cell matches the original2B sheets pixel-for-pixel. Original
  [64px/170px comparisons](before-after-bare-light.png) remain applicable.
- [486 reaction cases and21 reduced-motion checks](lcp-unblock/static-previews/motion-rig-check.json)
  pass with gallery wrappers explicitly representing selected companions.
- [260 tests](lcp-unblock/validation-tests.txt) pass, including care/audio,
  rendering, appearance, onboarding, search and bounded lazy compilation.
- [Three browser tests](lcp-unblock/static-functional/tests.txt) verify sixteen
  static picker cards, selected animation and keyboard replay, pointer/head limits,
  responsive Home search and actual Wellness-result navigation.
  [Static preview measurements](lcp-unblock/static-functional/static-preview-policy.json).
- [Real mature-plant care](lcp-unblock/live-plant-care.json) verifies authenticated
  Home→Wellness→carePOST→SQLite timestamp→wet-soil UI for all three species.
- [Native visibility/touch/keyboard](lcp-unblock/application/native-visibility-touch.json)
  verifies actual document.hidden, zero hidden rAF frames, drag/keyboard and zero
  animated picker thumbnails. [Performance runner log](lcp-unblock/performance-tests.txt).

## Retained failures and attribution limits

The original failed20 samples remain in `application/`, with median664ms,
+292ms versus the corrected overlay control: [blocked assessment](assessment-blocked.json),
[blocked report](REPORT-blocked.md). All exploratory controls remain separate.
`lcp-unblock/pre-frame-fix/` retains a183.3ms frame miss; `pre-startup-fix/`
retains cold-desktop median504ms. No sample was replaced and no threshold relaxed.

[Server profiling](lcp-unblock/server/server-template-profile.txt) found about
1.47million calls/629ms cold rendering; [lazy compilation](lcp-unblock/lazy-server/server-template-profile.txt)
reduced this to0.77million/320ms. Warm rendering was small in both cases. The
[startup trace](lcp-unblock/startup-diagnostic/startup-trace.json) found a large
layout while parsing paused at the viewport script. These instrumented diagnostics
identify avoidable work; they do not explain every timing spike.

The `00d76bc` full20 cohort passed its primary gates, but fresh focused traces
failed. Those results remain under `lcp-unblock/pre-motion-fix/`. An exploratory
recorder added excessive stack-capture overhead; its measurements are retained
as diagnostics. Subsequent controls removed timer/event/rAF wrappers and tracing.
Thirty counterbalanced old/new-art native samples identified a genuine new
mushroom chase callback60.4ms, including41.6ms forced layout. That failure motivated
the final chase/drag/replay fix. The fresh final-source checks above determine
acceptance; earlier failures were not dismissed as recorder overhead.

This is a local throttled-browser result, not a physical-phone60fps claim.
EventTiming has a16ms reporting floor; page-wide long tasks alone cannot establish
avatar ownership. Native LoAF attribution covers scripts in long frames.
RendererRSS includes shared pages. The full matrix uses forced-active automation;
the separate native check proves actual hidden behavior. Selected-companion
offscreen motion, chase/idle/roam timers and same-document listener retention
remain separate release blockers. Static picker thumbnails are resolved.
No production deployment or3A implementation occurred.

## Reproduce

```sh
.venv/bin/python scripts/avatar_baseline/check_lazy_equivalence.py
# Preserve every prior cohort; use fresh output directories.
CSS_TEST_NOW=2026-07-15T12:00:00 CSS_AVATAR_BASELINE=1 CSS_AVATAR_MATURE=1 CSS_AVATAR_NATIVE_AFTER_ONLY=1 CSS_AVATAR_OUT=<fresh>/native-control/application .venv/bin/python -m pytest tests/test_avatar_native_control.py -s
CSS_TEST_NOW=2026-07-15T12:00:00 CSS_AVATAR_BASELINE=1 CSS_AVATAR_RUNS=5 CSS_AVATAR_SECONDS=30 CSS_AVATAR_OUT=<fresh>/application .venv/bin/python -m pytest tests/test_avatar_baseline_browser.py -k real_application_baseline -s
.venv/bin/python scripts/avatar_baseline/summarize.py docs/avatars/increment2b/lcp-unblock/application
.venv/bin/python scripts/avatar_baseline/compare.py --after docs/avatars/increment2b/lcp-unblock/application
.venv/bin/python scripts/avatar_baseline/assess_lazy_artwork.py
.venv/bin/python scripts/avatar_baseline/report_lazy_artwork.py
```
''')
(root/'assessment.json').write_text(json.dumps(a,indent=2))
print('Latest2B status:',a['status'])
