# Increment 2B — accepted after final evidence audit

**2B is complete. Release readiness remains false; increments 3A–6 are pending.**
Product `f700187` and harness `e909de1` passed final [run 40263865865](https://github.com/jongsky25/css-is/actions/runs/40263865865).
[Audit 40277957839](https://github.com/jongsky25/css-is/actions/runs/40277957839) passed, and independent local review verified the raw data rather than relying on the workflow badge.

The final cohort uses Chromium **156.0.8078.47**, five 30-second samples per arm/configuration. All four phases passed: functional/visual, focused artwork/native, whole runtime, and original/current application matrix. All 40 matrix samples remain available. The original controls use historical callers with historical macros.

## Measured results

| Configuration | Home LCP median / worst (ms) | Median LCP delta (ms) | Picker RSS median delta (MiB) |
|---|---:|---:|---:|
| Desktop cold | 292 / 520 | +16 | -49.504 |
| Desktop warm | 96 / 116 | +4 | +6.121 |
| Mobile cold | 436 / 468 | +24 | -63.070 |
| Mobile warm | 196 / 236 | -8 | -10.336 |

- Maximum current owned callback: **3.505 ms** focused; **4.080 ms** whole runtime (50 ms limit).
- Current native/trace and mobile interaction frame p95: **16.7–16.8 ms** (33.3 ms approved limit; original 33 ms retained in evidence).
- Largest renderer RSS median increase across all five scenarios and four configurations: **8.5625 MiB**, warm-desktop seasonal preview. Warm-desktop picker: **6.1211 MiB**. All renderer/JS-heap median deltas meet 10 MiB; positive renderer counts match across arms. Cold RSS decreases are observed cohort differences, not a claim that SVG trimming alone saves that amount.
- Added gzip CSS/JS: **3,194 bytes**; maximum Home/picker transferred document increase **1,247 / 2,370 bytes**, below 15/30/120 KiB budgets.
- Every scenario's LCP and interaction median delta meets 100/20 ms. No new JavaScript errors or external requests.

## Evidence audit and visual acceptance

[Independent audit](final-verification/independent-audit.json) verifies 156 retained file hashes, source-file hashes against `e909de1`, all 51 PNG hashes against reference/preview hashes, 4,896 static cells, and recomputes all memory medians from raw samples. All same-paint-mode cells are identical. Reviewed the final bare contact sheet; existing six-stage/seasonal artwork acceptance remains applicable because geometry is unchanged. Static rasterization differs from the original composited antialiasing; the original differences remain retained.

Eight browser regressions, 1,734 interactive SVG comparisons, seasonal live refresh without losing unsaved form state, native visibility/touch/keyboard and persisted fern/mushroom/succulent care pass. Static previews remove 1,032 SVG nodes per 96-cell sheet while preserving live SVG output.

[Compact numeric/visual archive](final-verification/numeric-and-visual-evidence.tar.gz) retains all JSON/XML/text/PNG evidence. [Manifest](final-verification/review-manifest.json) hashes 60 compressed traces retained in the full remote artifact; those trace bytes were not downloaded/rehashed locally. [Provenance](final-verification/provenance.json) records artifact digests.
Full raw evidence: [artifact 12630379820](https://github.com/jongsky25/css-is/actions/runs/40277957839/artifacts/12630379820), retained until **2026-11-25 06:08 UTC**. Compact artifact 12630544140 has the same 30-day retention. The original artifact expires November 2; its full copy is now preserved.

## Limits and history

No physical mobile device was tested. CPU throttling is a proxy; RSS includes shared resident pages. Page-wide tasks are not automatically avatar-attributable. Existing offscreen motion, recurring timers and remount/listener findings remain increment 5 release blockers. No deployment or merge occurred.

[Prior report](REPORT-before-final-audit.md) and [prior assessment](assessment-before-final-audit.json) preserve all historical failures and superseded status statements, including Chromium 154 cohorts, rejected diagnostics, and the earlier 11.199 MiB failure. They are not mixed into this final matched Chromium 156 cohort. No sample was replaced or threshold relaxed.

Next increment: **3A — dog, rabbit, bird, turtle**, six stages each with visual and performance gates.
