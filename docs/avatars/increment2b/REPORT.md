# Increment 2B — acceptance follow-up

**Blocked. Do not start increment 3A.** Final product source: `b7daa792d4ef74e1f7537869604c07cce9d30528`.

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
| fern | [16.8, 16.8, 16.8, 33.4, 16.8] | [25.1, 190.5, 14.8, 295.8, 32.9] | FAIL |
| mushroom | [16.8, 16.8, 16.7, 16.7, 16.8] | [26.1, 17.6, 0, 0, 160.7] | FAIL |
| succulent | [16.8, 16.8, 16.8, 16.8, 16.8] | [0, 258.4, 289.3, 0, 7.6] | FAIL |

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
