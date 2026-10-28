# Avatar upgrade review — 2026-10-28 (Asia/Manila)

All remaining product increments are implemented on `codex/avatar-upgrade-completion`:
3A dog/rabbit/bird/turtle, 3B fish/dolphin/owl/bat, optional wardrobe, accessible
profile customization, shared motion, cache versions and release documentation.
[Draft PR #526](https://github.com/jongsky25/css-is/pull/526) targets accepted
`codex/avatar-2b-verification`. No main merge or production deployment occurred.

The frozen product/measurement snapshot is **fecd276a9d888691c000c297d4ca1c1f6a958535**.
Later CI/documentation/test-fixture changes do not change its production sources.
The full [hosted run](https://github.com/jongsky25/css-is/actions/runs/40620559865)
retains every sample, failure and original trace. All scoped automated acceptance
phases pass. This is a review candidate;
physical-phone testing, production deployment and main merging are not claimed.

## Product changes

- All eight remaining animals have six structural stages and their existing
  interaction hooks. Swimmer water stays outside the moving creature.
- Thirteen authored, allowlisted accessories have species compatibility, slots,
  stage anchors and draw order, with at most two items. Persistence is additive;
  existing accounts default to seasonal appearance. Identity and care data remain.
- `/me#companion` offers seasonal/personal/none modes, read-only live preview,
  explicit Save/Cancel, removal and seasonal reset. Invalid saves are atomic;
  existing authentication and Origin protection apply. Preferences are actor-scoped
  across Home, Wellness and profile; shared admin art stays seasonal.
- Shared motion suspends offscreen, hidden and reduced-motion companions. Care,
  petting, idle and pointer movement arbitrate their transforms. Script evaluation
  is idempotent, removed companions unregister, and plant followthrough preserves
  leaf placement. Sounds remain opt-in; no accessory has its own perpetual timer.
- Version 8.57, changed script URLs and service-worker cache were updated. No new
  runtime dependency, external artwork, paid service or runtime AI generation.

## Verified evidence

Final hosted functional acceptance passes **126 tests, zero failures/skips**:
9 browser regressions, 104 core/wardrobe checks, 3 customization flows, 8 animal
care checks, seasonal refresh and native visibility/touch/keyboard. All **432**
animal stage/mood/theme rigs pass. Source and artifact hashes were independently
checked in [the offline functional audit](hosted-functional-audit.json).
The retained functional ZIP matches GitHub SHA-256
`c4b38a23b0b4504a727b2cd9e5d008097f5d0405fe61778cc342702ef5d4be34`.

The final hosted runtime phase passes: four representative kinds (cat, fern,
fish, bat), five 30-second CPU4 samples each, in both matched source arms.
All 20 current samples meet the unchanged 50 ms callback and 33.3 ms frame limits.
Worst owned callback is **3.364 ms**; worst frame p95 is **16.8 ms**.
Empty controls pass. [Independent runtime audit](hosted-runtime-audit.json)
rehashes 20 numeric/visual files and verifies source identities; 40 original
compressed traces and their hashes remain in the full hosted runtime artifact.
The portable [runtime review part](hosted-runtime/avatar-review-runtime-1.tar.gz)
and [index](hosted-runtime/avatar-review-runtime-parts.json) are retained locally.

Additional completed checks include 1,584 compatible equipment/stage renders,
1,632 seasonal renders, 35 motion/pointer/customizer/audio regressions,
24 wardrobe/customizer/appearance checks, 26 onboarding/PWA/native checks and
27 accounting regressions. qa_preflight is GREEN (backup-directory warning only).
[51 sheets](small-sheets/index.json) cover **4,896 actual 64 px cells** across all
six stages, outfits and surfaces. All 36 turtle cap/crown retraction cases hide
the eyes; [measurements](turtle-equipped-retraction.json) and
[rendered evidence](turtle-equipped-retraction.png) are retained.

Exact compressed CSS/JS source growth is **5,733 bytes versus increment 0** and
**2,539 bytes versus accepted 2B**, below 15 KiB; see [payload-budget.json](payload-budget.json).
This byte calculation does not prove cumulative timing/memory versus increment 0.

## Final matrix and application acceptance

The complete five-run cold/warm desktop/mobile application matrix **passes** on
fecd276 against accepted 2B. All 104 scenario/navigation median RSS and heap
comparisons meet the unchanged 10 MiB criterion, with matched renderer counts.
Largest RSS median increase is **7.742 MiB**; largest heap increase is **3.673 MiB**.
Every mobile interaction frame p95 is at most 16.8 ms. The largest group-median
LCP change is +4 ms; no interaction-duration median increases. Home document
transfer grows at most 255 bytes and picker transfer at most 1,552 bytes.
No JavaScript errors or external requests were recorded. Empty controls,
visibility/reduced-motion/background checks, complete cohorts and all matrix gates
pass. No later memory budget was waived.

[Independent matrix audit](hosted-matrix-audit.json) recomputes all 104 comparisons,
checks every source identity and rehashes 35 portable numeric/visual files.
The [complete matrix ZIP](hosted-matrix.zip) matches GitHub SHA-256
`a3a02238cb8e1f9097c65160b54eb49b118f645fd5e37b0e654f01e539abf824`.
All four matrix transport ZIP digests and both portable tar-part hashes were
verified before extraction. These results concern this exact hosted comparison;
they do not resolve the older 2B findings or establish physical-phone performance.

Full [application CI 40628692333](https://github.com/jongsky25/css-is/actions/runs/40628692333)
**passes** in both normal and shuffled (seed 311) orders: **7,060 tests per order,
zero failures/errors/skips**. Each strict AI evaluation gate passes all 447 offline
fixture cases. Release metadata, dependency audit and the aggregate Required
checks job also pass. [The independent application audit](hosted-application/audit.json)
verifies archive hashes, all JUnit cases and the untouched AI evidence against
GitHub's exact temporary PR checkout. Original archives are retained under
[hosted-application](hosted-application/README.md).

The tested branch snapshot is 559301e; GitHub's temporary checkout 23e4a7ad has
an identical tree. Later report-only changes do not repeat those tests. Checkout,
optional-import/selection, test reader-lifecycle and release-payload integration
fixes are documented in [the bounded CI repair evidence](application-ci-repair/README.md).
Production reader code is unchanged. One executable archived profiler case is
explicitly deselected, not counted as a pass; the documented
[application selection](application-suite-selection.md) keeps 17 offline profile
analysis cases and all other selected application tests. Earlier timed-out,
cancelled, failing and local browser-skipped runs remain as recorded.

The accepted 2B exception remains scoped to 2B. Its +11.699/+16.301 MiB navigation
RSS differences, 36.379 MiB same-source control swing, and earlier failures remain
recorded. No claim of reliable cumulative performance versus increment 0 or
physical-phone testing is made. No GC/root-retention/native-hook/observer research
was restarted; the disposal probe remains archived. The isolated shared-gradient
candidate was not promoted.

[Validation history](VALIDATION_HISTORY.md) retains development failures and
superseded attempts. [Original asset manifest](asset-manifest.json),
[before](motion/before-motion.webm)/[after](motion/after-motion.webm) motion recordings
(synthetic care replies), [hero overview](hero-overview.png), and
[rollback instructions](ROLLBACK.md) are available for review.
