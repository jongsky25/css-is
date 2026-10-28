# Avatar completion review candidate — 2026-10-28 (Asia/Manila)

All remaining product increments are implemented in reviewable commits after the
accepted 0a91f73 baseline: recovered 3A animals; new 3B animals; wardrobe model;
profile customization; shared motion; integration fixes and review evidence.
No unrelated reader or isolated shared-gradient candidate was promoted. No merge
into main, deployment or third-party messaging has occurred.

## Functional and visual evidence

- Recovered 3A: 86 core tests, four persisted-care browser checks, 216 rig cases,
  2,448 unchanged-species comparisons; frozen 20-sample native frame gate passes
  at 16.7–16.8 ms p95 on Chromium 154.0.8037.57, CPU4, 390×844.
- Integrated regression suite: 133 tests pass before the final scarf-slot coverage
  addition; 18 focused wardrobe tests pass afterward. The exhaustive render test
  now covers 1,584 compatible equipment/stage combinations plus 1,632 seasonal
  combinations (96 bases × 17 monthly/seasonal selections).
- 26 additional onboarding/PWA/native-visibility/render tests pass. Accounting
  regressions: 27 pass. qa_preflight is GREEN (only missing backup-directory warning).
- New mobile browser checks prove read-only preview, Cancel, Save, compatible
  filtering and persistence on Home/Wellness. Motion checks prove reduced-motion,
  offscreen suspend/resume and removal cleanup. Existing actual hidden-tab, touch,
  keyboard, audio, care, seasonal-live-refresh and static-preview checks pass.
- 216 3B stage/mood/theme rig cases pass. [Six final contact sheets](sheets/index.json)
  cover 96 bases and 294 equipment thumbnails per surface, including forced colors.
  [Mobile customization](browser/mobile-customizer.png) and [3B reactions](../increment3b/reactions-light.png)
  were actually rendered and inspected. Final small placement refinements give
  turtle neck items a smaller neck anchor and bonsai finishes a shallow-pot scale.

See retained logs/XML and asset manifest. Development failures remain in
[development-failures](development-failures/); interrupted syntax-error attempts
are not passing evidence. A subsequent real night-time petting regression was
fixed by waking the companion before the held-pet action. No 2B result changed.

## Performance and release status

The 2B provisional acceptance and unresolved failures remain intact. It grants no
exception to the new work. Local 3A frame evidence is scoped to that frozen batch,
not the later integrated runtime. Zero runtime JavaScript dependencies, remote
artwork or paid services were added. Physical-phone testing is unavailable.

A single hosted completion workflow is prepared using the established Linux x64
runner and pinned Chromium 156.0.8078.47. It runs functional checks, five 30-second
whole-runtime samples per representative plant/ground animal/flyer/swimmer in both
accepted-2B/current arms, then the full five-run cold/warm desktop/mobile matrix.
It retains all scenarios and navigation memory comparisons with the unchanged
10 MiB limit. No GC/native instrumentation research is included. All phases retain
failures independently. Full integrated performance acceptance remains pending.

Draft review: [PR #526](https://github.com/jongsky25/css-is/pull/526). Initial
hosted run [40616347893](https://github.com/jongsky25/css-is/actions/runs/40616347893)
installed pinned Chromium successfully; it is superseded by the leaf-placement
correction before performance acceptance. The final customizer browser trio passes,
including a regression that confirms watering rotates inner paths without replacing
a leaf placement transform. Source changes require a fresh hosted run; no cancelled
or partial cohort is acceptance evidence.

Separate [before](motion/before-motion.webm) and [after](motion/after-motion.webm)
recordings use each arm's own CSS/JavaScript for fern, dog, bat and fish; care replies
are synthetic. [Hero overview](hero-overview.png) shows the final catalog with two
optional accessory examples.

New script and service-worker cache versions, version.py/CHANGELOG, original-art
[asset manifest](asset-manifest.json) and [rollback instructions](ROLLBACK.md) are
included. This candidate is for review; release readiness remains false until the
remaining performance evidence passes. No production deployment is authorized.

### Standard CI collection repair

The initial standard PR CI failed during collection because archived analysis
modules imported optional Frida at module load. This also exists in accepted
baseline 0a91f73 (global imports remain there; Frida is a separate optional lock).
Frida imports now occur only in explicit diagnostic entry points in six archived
modules and their PageHistory helper. No diagnostic behavior/protocol, raw archive
or numerical finding was changed, and no instrumentation was launched. The
previously blocked offline/collection regression set passes without Frida; its
opt-in browser calibrations remain skipped. Standard application CI is rerun.

Exact compressed CSS/JS deltas are +5,683 bytes against increment 0 and +2,489
bytes against accepted 2B, both below 15 KiB; see payload-budget.json. This source
budget does not establish HTTP document-transfer, timing or memory acceptance.

### Final motion arbitration and hosted phase visibility

Idle gestures now reserve their part transforms through recovery, so pointer
tracking/roaming cannot compete with a running head/ear gesture. Thirty-two motion,
pointer, customizer and audio regressions pass on this final runtime.

The hosted workflow now uploads functional, runtime and application-matrix
artifacts independently. Each phase's before/after arms still share one runner,
browser and filesystem; distinct phases use independent runners and their own
controls. A functional failure can therefore be inspected immediately without
waiting for the longer performance phases. Earlier cancelled/partial runs are
retained as such and do not establish final acceptance.

### Final integrated seasonal and collection checks

The global /appearance/avatar renderer explicitly uses seasonal preferences, so
shared seasonal illustrations cannot pick up the viewer's personal equipment.
Unsaved seasonal customizer previews follow real global outfit updates, while
saved personal mode and equipment remain unchanged. All 24 wardrobe/customizer/
appearance checks pass, including this flow. All 432 current animal stage/mood/
theme rigs pass. Sheets and recordings were regenerated on the final product.

The corrected leaf fixture establishes its own mature growth state instead of
relying on a caller environment variable. This closes the hosted functional
failure recorded under hosted-development/; its original archive/hash is retained.

Normal CI uses the explicitly scoped [application suite](application-suite-selection.md).
The existing zero-failure/zero-skip gate remains intact. Dedicated avatar CI still
executes current functional/browser and full performance checks; disabled archived
experiments are not launched. Full integrated performance acceptance is pending.
