"""Generate the latest2B report without overwriting historical failed evidence."""
import json
from pathlib import Path
root=Path('docs/avatars/increment2b');out=root/'layout-fix'
read=lambda path:json.loads(path.read_text())
a=read(out/'assessment.json');accepted=a['status']=='complete'
focus=[]
for kind,checks in a['focused'].items():
    samples=checks['samples']
    focus.append(f"| {kind} | {[round(r['frame_p95_ms'],1) for r in samples]} | {[round(r['max_reported_owned_script_ms'],1) for r in samples]} | {'PASS' if checks['passed'] else 'FAIL'} |")
primary='The final-source original20 matrix has not completed; acceptance remains blocked.'
if a['primary_samples']==20:
    comparison=read(out/'comparison.json');rows=[]
    for group in comparison['groups']:
        lcp=group['scenarios']['home_idle']['lcp_ms'];frames=group['scenarios']['home_interaction']['frame_p95_ms']['after']
        rows.append(f"| {'Mobile CPU4' if group['mobile'] else 'Desktop CPU1'} {group['cache']} | {lcp['before']['median']:.0f} / {lcp['before']['worst']:.0f} | {lcp['after']['median']:.0f} / {lcp['after']['worst']:.0f} | {lcp['median_delta']:+.0f} | {frames['median']:.1f} / {frames['worst']:.1f} |")
    matched=a['matched_control']
    primary=f'''[All20 raw samples](layout-fix/application/summary.json) and the
[complete comparison](layout-fix/comparison.json) retain medians and worst runs.

| Fixture | Increment0 LCP median/worst ms | Current LCP median/worst ms | Median delta ms | Interaction framep95 median/worst ms |
|---|---:|---:|---:|---:|
{chr(10).join(rows)}

The unchanged original-source overlay control has median
{matched['control_median_ms']:.0f}ms. Current cold-desktop values
**{matched['current_values_ms']}**, median **{matched['current_median_ms']:.0f}ms**,
worst **{matched['current_worst_ms']:.0f}ms**, delta
**{matched['median_delta_ms']:+.0f}ms** against the unchanged100ms limit.
All secondary latency/heap/RSS gates are included in the assessment.
Combined added gzip CSS+JS: **{comparison['css_js_gzip_delta_bytes']}B**.
Maximum median Home document increase: **{max(g['home_encoded_delta'] for g in comparison['groups']):.0f}B**;
picker: **{max(g['picker_encoded_delta'] for g in comparison['groups']):.0f}B**.
Worst runs remain included; none was dropped to satisfy a median gate.
[Runner log](layout-fix/performance-tests.txt).'''
gates='\n'.join(f"- `{key}`: **{'PASS' if passed else 'FAIL'}**" for key,passed in a['gates'].items())
(root/'REPORT.md').write_text(f'''# Increment2B — fern, mushroom and succulent

**{'Accepted: increment2B is complete. Increment3A is next.' if accepted else 'Blocked: do not start increment3A.'}**
Frozen product source: `{a['source_commit']}`.
[Assessment](layout-fix/assessment.json) records every gate.

## Fix

The earlier LCP fixes (`853c93d`, `41c8e01`, `00d76bc`) retain lazy artwork
compilation and deferred Home search initialization. `b7daa79` batches chase/drag
reads, avoids reflow for absent reaction classes, and makes decorative picker
cards static. Its focused motion failures remained unresolved.

`b2c9b82` removes live bounds reads from repeated pointer, drag and chase updates.
It caches wrapper, head and play-area geometry; resize observers, scrolling and
artwork replacement invalidate it. Owned movement translates cached bounds.
Curiosity still reads the complete geometry set before writing transforms.
The mutation observer initializes incoming companions or refreshes replaced art,
instead of rescanning all companions after every decorative heart insertion/removal.
`765bd42` shares the new scheduler, body observer and global resize/scroll listeners
across repeated script evaluation. No new infrastructure accumulates on that path.
The final correction captures ResizeObserver geometry in its completed-layout
phase, instead of deferring the read until the next pre-render animation frame.
A later sparse kernel diagnostic exposed another180.4ms click containing162.6ms
forced layout in active happy replay. The final source restarts the existing
bounce/spark CSS Animation objects via currentTime/play, without removing the class
or reading offsetWidth. A real browser verifies restart, completion and0offsetWidth
reads during tap handlers.

Selected animation, head-angle limits, dog excitement/cooldowns, tap/hold/drag,
keyboard movement, care, audio, scoring, account identity and seasonal geometry
remain functional. No new dependency, external request, artwork simplification,
compositing hint or containment rule was added.

## Focused motion gate

Five mature-stage6 warm mobileCPU4 runs per plant use the original30-second
interaction sequence. Native LoAF, LongTask and EventTiming plus a lightweight
frame counter run without timer/event/rAF wrappers, callback clocks, stack capture
or tracing. Every run must meet framep95≤33ms and reported owned script≤50ms.
Zero reported duration means no owned script in a reported long frame, not zeroCPU.

| Species | Five framep95 values ms | Five maximum reported owned scripts ms | Gate |
|---|---|---|---|
{chr(10).join(focus)}

Raw data: [fern](layout-fix/native-control/fern/native-control.json),
[mushroom](layout-fix/native-control/mushroom/native-control.json),
[succulent](layout-fix/native-control/succulent/native-control.json).
[Runner](layout-fix/native-tests.txt).

## Original performance matrix

{primary}

The original protocol remains fixed Chromium154.0.8037.57, CPU1/4,
desktop1440×1000/mobile390×844, synthetic July15 date/seed, local gzip,
overlay filesystem, five runs per device/cache and30-second idle/interaction
scenarios. Source hashes prove the same product revision for native checks,
primary matrix and functional verification. No benchmark scenario or budget changed.

{gates}

## Visual and functional verification

- [260 tests](layout-fix/validation-tests.txt) pass, covering care, audio,
  rendering, appearance, onboarding, search and bounded lazy compilation.
- [Four browser tests](layout-fix/functional/tests.txt) pass. Repeated input makes
  [zero live bounds reads](layout-fix/functional/geometry-behavior.json); drag clamps
  remain correct after resize/scroll, and the new listeners/cache stay stable after
  twenty script evaluations. [Head tracking](layout-fix/functional/pointer-behavior.json),
  [static picker/keyboard replay](layout-fix/functional/static-preview-policy.json)
  and [responsive Home search navigation](layout-fix/functional/home-search-boot.json) pass.
- [1,734 SVG equivalence checks](layout-fix/artwork-equivalence.json) preserve exact
  paths, attributes, text, deterministic IDs and unknown fallback; only interelement
  whitespace is normalized. CSS/defs differ only in the earlier static-preview
  policy and runtime cache key.
- [51 fresh sheets](layout-fix/visual/sheets/index.json), covering all16 species,
  six stages,17outfits and three surfaces, retain
  [4,896 pixel-identical cells](layout-fix/visual/unchanged-species.json).
- [486 reaction cases/21 reduced-motion transitions](layout-fix/visual/motion-rig-check.json)
  pass. Original [small/hero artwork comparisons](before-after-bare-light.png) apply.
- [Native hidden/touch/keyboard](layout-fix/native-functional/application/native-visibility-touch.json)
  verifies actual document.hidden, zero hidden rAF frames, touch/keyboard movement
  and zero animated picker thumbnails. [Runner](layout-fix/native-functional-tests.txt).
- [Real care](layout-fix/care/live-plant-care.json) verifies all three mature plants:
  Home→Wellness→carePOST→SQLite timestamp→wet-soil UI. [Runner](layout-fix/care-tests.txt).

## Retained failures and attribution limits

The original failed20 samples remain in `application/`: median664ms,
+292ms versus matched overlay control. [Original blocked report](REPORT-blocked.md).
The prior motion failure remains in [its report](REPORT-motion-blocked.md) and
`lcp-unblock/native-control/`: fern framep95 reached33.4ms and reported owned
callbacks reached295.8ms. Those measurements were not waived or overwritten.
The `00d76bc` full20 LCP-passing cohort remains under `lcp-unblock/pre-motion-fix/`;
it does not substitute for final-source validation. Earlier stopped attempts remain.

[Three matched native CPU trace pairs](layout-fix/cpu-before/summary.json) compare
old/new artwork on the same prior runtime. None reproduced a callback over50ms;
wall/thread CPU and losslessly compressed raw traces remain per species. This
locates the investigation without proving the cause of earlier stalls. Prior
recorder-overhead diagnostics are retained as diagnostics, not acceptance evidence.
The partial `b2c9b82` cohort was stopped to fix the new infrastructure's repeated
script-loading lifecycle; its samples remain under
[pre-lifecycle-fix](layout-fix/pre-lifecycle-fix/STOPPED.json), outside final acceptance. The subsequent `765bd42` fern cohort exposed an84.6ms
cache-refresh callback with84.5ms forced layout. Its complete samples remain in
[pre-observer-phase-fix](layout-fix/pre-observer-phase-fix/STOPPED.json); that real
failure motivated the completed-layout observer correction. The subsequent
`788dcbe` native cohort still failed (maximum449.8ms owned callback and33.3ms
framep95), preserved under [pre-replay-fix](layout-fix/pre-replay-fix/STOPPED.json).
Its external5ms matched and after-only controls did not reproduce stalls; a25ms
sampler did reproduce them with substantial CPU upper bounds, including the162.6ms
forced-layout click. This did not establish descheduling as the cause. All raw
native records and losslessly gzipped kernel samples remain there. That confirmed
active-replay reflow motivated the final source change.

No sample was replaced and no threshold relaxed. These are local throttled-browser
results, not physical-phone60fps claims. Native LoAF reports scripts in long frames;
EventTiming has a16ms floor. RSS includes shared renderer pages and is not PSS.
Full-matrix automation forces active pages; the separate native check proves actual
hidden behavior. Static picker thumbnails are resolved. Existing selected-companion
offscreen animation, chase/idle/roam timers and per-wrapper same-document listener
retention remain separate release blockers. No production deployment or3A work.

## Reproduce

```sh
# Use fresh directories and preserve prior cohorts.
CSS_TEST_NOW=2026-07-15T12:00:00 CSS_AVATAR_BASELINE=1 CSS_AVATAR_MATURE=1 CSS_AVATAR_NATIVE_AFTER_ONLY=1 CSS_AVATAR_OUT=<fresh>/native-control/application .venv/bin/python -m pytest tests/test_avatar_native_control.py -s
CSS_TEST_NOW=2026-07-15T12:00:00 CSS_AVATAR_BASELINE=1 CSS_AVATAR_RUNS=5 CSS_AVATAR_SECONDS=30 CSS_AVATAR_OUT=<fresh>/application .venv/bin/python -m pytest tests/test_avatar_baseline_browser.py -k real_application_baseline -s
.venv/bin/python scripts/avatar_baseline/summarize.py docs/avatars/increment2b/layout-fix/application
.venv/bin/python scripts/avatar_baseline/compare.py --after docs/avatars/increment2b/layout-fix/application
.venv/bin/python scripts/avatar_baseline/assess_layout_fix.py
.venv/bin/python scripts/avatar_baseline/report_layout_fix.py
```
''')
print('Latest2B status:',a['status'])
