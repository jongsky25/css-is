"""Write historical lazy-template evidence; use report_layout_fix.py for current2B."""
import json
from pathlib import Path
root=Path('docs/avatars/increment2b');out=root/'lcp-unblock'
read=lambda p:json.loads(p.read_text())
a=read(out/'assessment.json')
if a['primary_samples'] == 0:
    rows=[]
    for kind,check in a['avatar_callback_checks'].items():
        samples=check['samples']
        frames=[round(r['frame_p95_ms'],1) for r in samples]
        callbacks=[round(r['max_reported_owned_script_ms'],1) for r in samples]
        rows.append(f"| {kind} | {frames} | {callbacks} | {'PASS' if check['passed'] else 'FAIL'} |")
    (root/'REPORT-motion-blocked.md').write_text(f'''# Increment 2B — acceptance follow-up

**Blocked. Do not start increment 3A.** Final product source: `{a['source_commit']}`.

The LCP blocker was improved, but final-source motion acceptance still fails.
The [assessment](lcp-unblock/assessment.json) retains all 15 focused native runs.
No threshold was relaxed, failed sample replaced, or earlier-source matrix reused.
The planned full 20 final-source matrix was not started because its focused
prerequisite failed.

## Changes and validation

- `853c93d`: split the artwork into lazily loaded species modules; Home compiles
  only its requested companion. Shared helpers and fixed allowlist retain fallback.
- `41c8e01`: batch pointer geometry reads before transform writes.
- `00d76bc`: move Home's viewport-dependent search placeholder query from a
  mid-body inline script into the existing deferred initializer.
- `b7daa79`: read chase/drag bounds before style writes, skip forced reflow when
  starting an absent animation class, and keep decorative wrappers/picker cards
  static. Existing selected-companion reactions and keyboard replay remain active.

[260 tests pass](lcp-unblock/validation-tests.txt). [Three real browser tests](lcp-unblock/static-functional/tests.txt)
verify static picker cards, live selected animation, repeated keyboard reactions,
pointer/head limits and responsive search with actual Wellness navigation.
[Picker measurements](lcp-unblock/static-functional/static-preview-policy.json)
show 16 cards and 0 running animations, while Home has 1 live animation.

[1,734 SVG comparisons](lcp-unblock/artwork-equivalence.json) preserve paths,
attributes, text, deterministic IDs and unknown fallback across 16 species × 6 stages × 17 outfits.
Only interelement whitespace is normalized. CSS/defs differ only in the documented
static-preview policy and runtime cache key. [51 fresh visual sheets](lcp-unblock/static-previews/sheets/index.json)
contain 4,896 cells, all [pixel-identical to original 2B](lcp-unblock/static-previews/unchanged-species.json).
[486 reaction cases and 21 reduced-motion transitions](lcp-unblock/static-previews/motion-rig-check.json)
pass. No artwork geometry, scoring, account, care policy, sound or runtime dependency changed.
No containment/compositing hint or external asset was shipped.

[Native hidden/touch/keyboard verification](lcp-unblock/native-functional/application/native-visibility-touch.json)
passes on the final product revision: actual document.hidden, zero hidden rAF frames,
working touch/keyboard movement and zero animated picker thumbnails.
[Real care verification](lcp-unblock/care/live-plant-care.json) passes for mature
fern, mushroom and succulent: Home→Wellness→care POST→SQLite timestamp→wet-soil UI.
[Native runner](lcp-unblock/native-functional-tests.txt), [care runner](lcp-unblock/care-tests.txt).

## Failed final-source focused gate

Five mature-stage 6 warm mobile CPU 4 runs per species use the original 30 s interaction
sequence. Native LongAnimationFrame, LongTask, EventTiming and a lightweight frame
counter record results without timer/event/rAF wrappers, tracing, callback clocks
or stack capture. Every run must meet frame p95≤33ms and reported avatar-owned
script duration≤50ms. Zero duration means no owned script was reported in a long
frame, not zero CPU. [Runner log](lcp-unblock/native-control/tests.txt).

| Species | Five frame p95 values ms | Five maximum reported owned scripts ms | Gate |
|---|---|---|---|
{chr(10).join(rows)}

Raw records: [fern](lcp-unblock/native-control/fern/native-control.json),
[mushroom](lcp-unblock/native-control/mushroom/native-control.json),
[succulent](lcp-unblock/native-control/succulent/native-control.json).

Fern records a 190.5 ms chase callback with 0 forced layout; another run records
61.7ms curiosity work including 54.9 ms forced layout, 186.3 ms pointer-up,
295.8 ms timeout, 105.1 ms initAll and 222.9 ms chase. These native durations do not
isolate scheduling, GC or another cause. Several small callbacks exceed the
budget without attributed forced layout; that observation cannot dismiss them.
The 33.4 ms fern frame miss is retained as a strict failure, without rounding down.

## Earlier cohorts and remaining work

The complete 20-run `00d76bc` cohort passed its primary gates: cold desktop
LCP median 328 ms/worst 652 ms, +4ms versus historical 324 ms and −44 ms versus the
matched overlay control 372 ms. Desktop warm median 148 ms, mobile cold 564 ms,
mobile warm 308 ms; all mobile interaction frame p95 values 16.7–16.8 ms.
[Its complete comparison](lcp-unblock/pre-motion-fix/comparison.json) and
[raw summary](lcp-unblock/pre-motion-fix/application/summary.json) remain intact.
The 1412 ms cold-mobile worst run and its timing investigation are retained there.
These measurements do **not** validate the final product revision.

Fresh focused instrumented traces subsequently failed. An exploratory recorder
added excessive stack-capture overhead; all data remain under `pre-motion-fix/`.
Thirty counterbalanced old/new-art runs without API wrappers/tracing then found
a genuine new mushroom chase callback 60.4 ms with 41.6 ms forced layout. That result
motivated `b7daa79`; the final 15 runs above still fail acceptance.

Original failed 20 runs (cold-desktop median 664 ms, +292 ms over matched control)
remain in `application/`: [original blocked report](REPORT-blocked.md),
[original assessment](assessment-blocked.json). Earlier 183.3 ms frame and 504 ms
cold-LCP attempts remain in `lcp-unblock/pre-frame-fix/` and `pre-startup-fix/`.
All failed and exploratory cohorts remain separate; no favorable subset is used.

Next: isolate the remaining callback/layout stalls with an uninstrumented matched
control and browser-native CPU attribution before making another bounded fix.
After the focused gate passes, run a fresh original 20 matrix plus real care and
native hidden/touch/keyboard checks. Keep 3A pending. Static picker thumbnails
are resolved; selected offscreen motion, chase/idle/roam timers and same-document
listener retention remain separate release blockers. No production deployment.

These are local throttled-browser results, not physical-phone 60 fps claims.
EventTiming has a 16 ms reporting floor; native LoAF reports scripts in long frames,
not complete script CPU. RendererRSS includes shared pages. The full matrix uses
forced-active automation; actual hidden behavior requires the separate native check.

## Reproduce

```sh
CSS_TEST_NOW=2026-07-15T12:00:00 CSS_AVATAR_BASELINE=1 CSS_AVATAR_MATURE=1 CSS_AVATAR_NATIVE_AFTER_ONLY=1 CSS_AVATAR_OUT=<fresh>/native-control/application .venv/bin/python -m pytest tests/test_avatar_native_control.py -s
.venv/bin/python scripts/avatar_baseline/assess_lazy_artwork.py
.venv/bin/python scripts/avatar_baseline/report_lazy_artwork.py
```
''')
    print('Latest2B status: blocked; final-source primary matrix not run')
    raise SystemExit(0)
c=read(out/'comparison.json')
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
(root/'REPORT-motion-blocked.md').write_text(f'''# Increment 2B — fern, mushroom and succulent

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

| Fixture | Increment0 LCP median/worst ms | Current LCP median/worst ms | Median delta ms | Interaction frame p95 median/worst ms |
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

Fresh mature-stage 6, mobile CPU 4 checks use five30s runs per plant and native
LongAnimationFrame attribution, with no API wrappers, tracing recorder, callback
clocks or stack capture. Every run must meet frame p95≤33ms and every reported
avatar-owned script≤50ms. Zero reported duration means no owned script in a
reported long frame, not zero CPU. [Raw native records](lcp-unblock/native-control/fern/native-control.json).

| Species | Worst run frame p95 ms | Largest reported owned script ms | Gate |
|---|---:|---:|---|
{chr(10).join(focused)}

## Visual and functional gates

- [1,734 SVG checks](lcp-unblock/artwork-equivalence.json) compare all16species,
  six stages,17outfits and unknown fallback. Only interelement whitespace is
  normalized; paths, attributes, text and deterministic IDs match exactly.
  Shared CSS/defs differ only in the documented static-preview policy and script cache key.
- [51 fresh sheets](lcp-unblock/static-previews/sheets/index.json) cover4,896cells;
  every cell matches the original 2B sheets pixel-for-pixel. Original
  [64px/170px comparisons](before-after-bare-light.png) remain applicable.
- [486 reaction cases and 21 reduced-motion checks](lcp-unblock/static-previews/motion-rig-check.json)
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

The `00d76bc` full 20 cohort passed its primary gates, but fresh focused traces
failed. Those results remain under `lcp-unblock/pre-motion-fix/`. An exploratory
recorder added excessive stack-capture overhead; its measurements are retained
as diagnostics. Subsequent controls removed timer/event/rAF wrappers and tracing.
Thirty counterbalanced old/new-art native samples identified a genuine new
mushroom chase callback60.4ms, including41.6ms forced layout. That failure motivated
the final chase/drag/replay fix. The fresh final-source checks above determine
acceptance; earlier failures were not dismissed as recorder overhead.

This is a local throttled-browser result, not a physical-phone 60 fps claim.
EventTiming has a 16 ms reporting floor; page-wide long tasks alone cannot establish
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
(out/'assessment.json').write_text(json.dumps(a,indent=2))
print('Latest2B status:',a['status'])
