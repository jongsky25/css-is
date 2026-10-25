# Avatar visual upgrade — phased execution plan for Sol

Status: Increments0,1,2A complete. 2B preference-cache fix c2f404f passes8 browser checks and1,734 SVG comparisons. Current chase callback still reaches210.804ms; old-art controls also stall. Performance acceptance remains unresolved; the user-approved33.3ms frame exception is retained.3A pending.
Created: 2026-10-25
Repository: jongsky25/css-is
Owner request: Material improvement to companion artwork, optional animal dress-up,
plant accessories, and movement without significant performance regression.

## Execution contract

Use Sol to execute this plan in order. Read repository instructions and inspect
the current implementation before editing; file locations below are discovery
anchors, not assumptions that the code is unchanged. Complete one bounded increment
at a time, validate it, and record its commit, evidence, and remaining issues here.
Each increment must leave the application usable and be independently reviewable.
Do not mark a phase complete based only on source inspection.

Proceed autonomously with reversible implementation and local validation. This plan
does not itself authorize production deployment. Do not introduce a new framework,
animation player, remote asset dependency, paid service, or live AI inference.
Do not delegate to other agents unless the executing user explicitly requests it.
Retain existing account identity, growth, wellness scoring, care cooldowns, sounds,
seasonal administration, and accessibility behavior.

A phase fails if its visuals remain essentially the same except for color changes,
or if it exceeds a performance gate. Fix or reduce complexity before expanding it.

## Current implementation and constraints

- Sixteen species, each with six growth stages: 96 base combinations.
- Plants: blossom plant, cactus, bonsai, sunflower, fern, mushroom, succulent.
- Animals: cat, bird, turtle, dog, rabbit, fish, dolphin, owl, bat.
- Artwork: templates/_avatar_species/*.html; shared helpers: templates/_avatars_shared.html;
  allowlisted dispatcher: templates/_avatars_art.html; frame, gradients and CSS: templates/_avatars.html.
- Behavior: static/js/avatars.js; audio: static/js/avatar-audio.js.
- Catalog, growth and care: storage.py; profile and care routes: app.py.
- Appearance policy: appearance.py, appearance_routes.py, appearance_storage.py.
- Surfaces include templates/me.html, templates/office_connect.html, onboarding,
  Wellness, profile growth previews and administrator appearance previews.
- Existing behavior uses SVG groups for head, eyes, ears, tail, wings, fins, and
  plant parts. Preserve these hooks or explicitly migrate and test every consumer.
- Keep the outer movement layer separate from the inner animation layer.
  Swimmers' water backdrop stays outside the moving creature.
- Existing global outfits include monthly, Halloween witch/vampire/pumpkin, and
  Christmas. Existing seasonal live updates must retain form and companion state.
- Existing visibility/reduced-motion checks are a starting point, not proof that
  every animation and timer stops. Audit CSS and JavaScript together.

## Visual direction and deliverables

Build a cohesive illustrated collection: rounded silhouettes, intentional proportions,
expressive eyes, layered but restrained shading, consistent light direction, and
clear separation of body parts. Use soft color gradients and simple drawn shadows.
Maintain recognition at approximately 64 px and polish at the current hero size.

Growth must change anatomy or structure, not simply enlarge the same drawing:
animal proportions and features mature; plants gain meaningful leaves, stems,
branches, blooms or clusters. All stages must remain attractive. Maintain adequate
room around ears, wings, hats, capes and pots.

Use one consistent palette and outline/shadow system across species and accessories.
Do not add detailed backgrounds behind each avatar. Keep characters legible on
light, dark, and high-contrast surfaces.

Asset sources evaluated:
- Microsoft Fluent Emoji: https://github.com/microsoft/fluentui-emoji — MIT.
  Preferred starting source for visual language and selected reusable vector parts.
  Cat and potted-plant assets have Color, Flat, High Contrast and 3D variants.
- Google Noto Emoji: https://github.com/googlefonts/noto-emoji — most image
  resources Apache 2.0; fonts separately licensed.
- OpenMoji: https://github.com/hfg-gmuend/openmoji — graphics CC BY-SA 4.0.
- Twemoji: https://github.com/twitter/twemoji — graphics CC BY 4.0.

Prefer Fluent-compatible vector work or original authored SVG for the final coherent
set. These libraries do not supply our growth stages or animation rigs. Do not
promise a drop-in import. Avoid mixing visibly different illustration styles.
Choose exact assets, pin upstream revision and preserve required notices before reuse.
Record source URL, revision, file, license and modifications in an asset manifest.
Sanitize imported SVG: no scripts, foreignObject, external references or event handlers.
Do not install or ship a whole emoji library for a handful of assets.
Hugging Face generation is optional future design tooling, outside this plan.

## Performance acceptance gates

These are proposed release budgets, not measured claims. Establish and preserve a
baseline in increment 0. If the existing application already misses an absolute
budget, record that separately; this work must still meet the relative gates.

Measure the same fixtures and browser settings before and after, with cold and warm
cache, at desktop and mobile viewport sizes. Use five runs and report medians plus
worst run. Use a fixed Chromium version and a documented CPU throttle for comparisons.
A throttled browser is a proxy for a low-end phone, not a physical-device result.

Scenarios:
1. Home with one active companion, idle for 30 seconds.
2. Home during petting, care, cursor-follow and dragging for 30 seconds.
3. Full 16-species picker, scrolling and selecting.
4. Growth preview, wardrobe, and seasonal appearance preview.
5. Offscreen companion, hidden tab, reduced motion, repeated navigation.

Hard gates:
- Zero new runtime JavaScript dependencies and zero external asset/API requests.
- Added compressed avatar CSS + JS combined <= 15 KiB over baseline.
- Added compressed avatar markup/assets on Home <= 30 KiB over baseline.
- Added compressed avatar markup/assets for the full picker <= 120 KiB over baseline.
  Count the transferred content, including inline SVG, rather than template file size.
- Median LCP regression <= 100 ms; scripted interaction latency regression <= 20 ms
  in the controlled fixtures. Investigate unstable results rather than hiding outliers.
- No new avatar-attributable main-thread long tasks over 50 ms.
- Animation work fits the display frame budget on the desktop fixture; under mobile
  CPU throttle, p95 frame interval <= 33 ms during the defined interaction scenario.
  Record baseline and regression; do not claim 60 fps solely from requestAnimationFrame.
- Renderer/JS memory growth <= 10 MiB over baseline after identical scenarios.
  State measurement limits when browser memory APIs cannot capture all renderer memory.
- No accumulating listeners, timers, DOM nodes or memory trend after 20 mounts or
  navigations. No repeating visual animation work while hidden or offscreen.
  A sparse clock/sleep-state timer may remain if measured and documented.
- Static picker thumbnails; animate only the selected preview or intentional focus/
  hover preview, at most one picker preview at a time.
- Avoid animated SVG filters, blur, turbulence, path morphing, and per-frame layout
  reads. Prefer transform and opacity. Do not animate dozens of decorative particles.
- Load/render only the chosen stage and equipped items on normal user surfaces.
  The development gallery may intentionally render all combinations.

If a budget fails, simplify paths/layers, remove expensive effects, reduce simultaneous
motion, or cache static thumbnails. Do not silently relax the thresholds. Report
an unresolved tradeoff explicitly.

## Increment 0 — Baseline and reproducible gallery

Dependencies: none.
Deliver:
- A deterministic local/development gallery using the actual Jinja macros, with all
  16 species × six stages, light/dark surfaces, current costumes and mood states.
  Keep it out of public production navigation and avoid exposing account data.
- Baseline screenshots and a reproducible browser measurement script.
- A concise baseline report under docs/avatars/ with environment, fixture, measurements,
  commands and limitations. Use synthetic accounts and deterministic appearance dates.
- Inventory all avatar call sites, event handlers, update paths and relevant tests.
Acceptance: another session can reproduce both the visuals and measurements.
Commit: documentation/fixture/performance baseline only.

## Increment 1 — Art foundation and two-species vertical slice

Dependencies: 0.
Deliver:
- Cohesive design tokens, gradient definitions, consistent SVG group conventions and
  accessory anchor contract. Scope IDs so multiple copies never collide.
- Redesign cat and blossom plant across all six stages.
- Provide before/after contact sheets at small and hero sizes and motion recordings.
- Implement one animal accessory (bandana) and one plant accessory (pot wrap) in the
  gallery to prove layering and anchoring, without adding persistence yet.
- Preserve current behavioral hooks, growth semantics and seasonal compatibility.
Acceptance: obvious silhouette, expression, shading and growth improvement; no clipped
art or broken animation; budgets pass on Home and picker fixtures.
If a design needs user taste feedback, show a concrete preview while continuing
independent validation. Do not expand all species around an unresolved visual direction.

## Increment 2 — Complete plant artwork

Dependencies: 1.
Deliver cactus, bonsai, sunflower, fern, mushroom and succulent at six stages each.
Distinct silhouettes and growth progression must be evident without their labels.
Add species-appropriate soil/pot details and care reaction artwork.
Keep bloom, frond, cap/spore and plumping animation anchors compatible.
Acceptance: contact sheets for every stage, both themes, and supported seasonal outfits;
no generic pot decoration obscures the plant or its growth.
Commit in two batches if needed: cactus/bonsai/sunflower, then fern/mushroom/succulent.

## Increment 3 — Complete animal artwork

Dependencies: 1; may follow 2 sequentially.
Deliver remaining eight animals in two bounded batches:
- 3A: dog, rabbit, bird, turtle.
- 3B: fish, dolphin, owl, bat.
Preserve characteristic movements, owl pointer tracking, turtle hiding, and swimmer
water separation. Growth must alter proportions/features coherently.
Acceptance: six-stage sheets, small-size recognition, seasonal fit, mood and care
checks; pass budgets after each batch. No removal of species to meet a budget.

## Increment 4 — Optional wardrobe and plant add-ons

Dependencies: 2 and 3.
4A: catalog, rendering and persisted preferences.
4B: accessible profile controls and full integration.

Launch catalog:
- Animals: bandana, bow tie, small cap, flower crown, scarf and simple cape.
- Plants: terracotta/ceramic pot finishes, pot wrap, ribbon, plant label, small trellis
  and a restrained decorative stake.
- Each entry declares compatible species, slot, stage anchors and draw order.
  A trellis is available only where it visually and botanically makes sense.
- At most two equipped decorative items per companion: one head/body item plus one
  secondary item for animals; one pot finish/wrap plus one ornament for plants.
  Pot finish and wrap share a slot. Reject incompatible combinations server-side.
- Show available compatible items only; no locked/reward/purchase economy.

Persistence and precedence:
- Store stable catalog IDs, never user-supplied SVG/HTML, arbitrary URLs or CSS.
- Add preferences through the repository's normal additive migration path.
- Default mode: Follow seasonal appearance, preserving current behavior.
- Other explicit modes: My accessories; No accessories.
- Seasonal mode uses the resolved global outfit and suppresses personal equipment.
  My accessories uses the saved personal equipment and suppresses seasonal costume.
  No accessories suppresses both. Global page themes remain independently effective.
- Validate ownership, authentication, CSRF protections and input limits using current
  project conventions. Persist preferences with the normal profile save operation.
- On species change, clear incompatible equipment and explain that in the UI.
  Unknown/deleted IDs safely render nothing and never break profile loading.
- Existing users retain seasonal mode; do not erase saved appearance or care data.

UI:
- Add a compact Customize companion area at /me#companion with live preview, explicit
  save/cancel, remove item, and reset to seasonal defaults.
- Use native keyboard-accessible controls, visible focus, descriptive labels and
  concise saved/error feedback. Preview does not write until Save.
- Carry the resolved preferences to Home, Wellness, growth previews and applicable
  onboarding/profile displays. Define shared-view behavior consistently.
- Global appearance live updates must respect the user's selected mode.

Acceptance: reload and cross-surface consistency; authorization and invalid-ID tests;
all applicable stage/accessory combinations render correctly; no extra fetch per avatar
or repeated database query per rendered thumbnail.

## Increment 5 — Expressive movement with bounded work

Dependencies: artwork increments; wardrobe can precede motion.
Deliver a shared motion policy that preserves drag, chase, sleep and current behaviors.
Use visibility observation, page visibility and reduced-motion settings consistently
for CSS animations and JavaScript scheduling; clean up on removal/navigation.

Movement vocabulary:
- Animals: breathing, irregular blinking, anticipation and recovery around an existing
  hop/wag/stretch; ears and tails settle naturally after movement.
- Plants: slight stem/leaf follow-through, varied sway, gentle bloom opening, fern
  ripple and a short water response.
- Accessories follow their owning body part. Allow subtle secondary rotation within
  the existing animation, without an independent perpetual timer for each accessory.
- Care and petting have priority over idle; dragging suppresses roaming/chase.
  Prevent competing transforms and repeated actions stacking.
- Use varied pauses instead of constant performance. No full-page particle effects.
- Reduced motion renders a stable pose with immediate state/text feedback.
  Sounds remain independently opt-in, with no extra assets required.

Acceptance: motion feels deliberate and species-specific; no overlap, teleporting,
layout shift or clipped costumes; hidden/offscreen work stops; input stays responsive.
Capture short before/after recordings for a plant, ground animal, flyer and swimmer.

## Increment 6 — Regression, polish and rollout readiness

Dependencies: all preceding increments.
Deliver:
- Automated render sweep of all 96 base combinations, supported seasonal costumes
  and applicable accessory/stage combinations.
- Visual review/contact sheets for the entire catalog; scrutinize silhouettes,
  accessory attachment, growth, care and mood readability.
- Integration coverage for persistence, migration, preference precedence, permissions,
  seasonal live update, species switching and unknown IDs.
- Browser checks for Home, profile, Wellness, onboarding, appearance previews,
  light/dark/high contrast, reduced motion, touch dragging and keyboard controls.
- Final performance report against increment 0, with raw results and reproduction
  commands. Run physical mobile checks if available; state clearly if unavailable.
- Verify offline/static caching and cache-version updates using project conventions.
- License manifest, notices and no accidental upstream-library bundle.
- A rollback procedure: revert artwork/behavior release commits; additive preference
  storage can remain unused. Preserve users' saved preferences and care records.
- Changelog and implementation status updated.

Release gate: all hard budgets and functional checks pass; any remaining limitation
is explicit. Prepare reviewable commits/PR following repository workflow.
Deploy only when separately authorized by the executing user/session.

## Testing guidance

Start with tests/test_avatar_care.py, tests/test_avatar_audio.py and
tests/test_onboarding_storage.py; discover appearance, profile and browser tests.
Extend tests for behavior contracts and new preference logic, not literal SVG path data.
Run relevant tests after each increment; run the repository's required final checks
after integration. Do not claim real-device testing or deployment if only local
browser tests ran.

## Execution ledger

| Increment | Status | Commit | Visual evidence | Performance evidence / notes |
|---|---|---|---|---|
| 0 Baseline | Complete — baseline established; release gates remain unmet | `94269dd` + evidence/ledger revision | [51 sheets](avatars/sheets/index.json), [monthly overview](avatars/sheets/monthly-stage6-overview.png), [hero/moods](avatars/smoke/) | [Report](avatars/BASELINE_REPORT.md), [20 full samples + summary](avatars/application/summary.json), native hidden/touch check; existing frame, picker, timer and remount failures retained. |
| 1 Cat + plant slice | Complete — measured relative gates passed | `58cf98f`, `0be7fc3`, `ad4e7ad`, `d464461` + evidence revision | [Bare comparison](avatars/increment1/before-after-bare-light.png), [motion](avatars/increment1/before-after-motion.webm), [51 seasonal sheets](avatars/increment1/sheets/index.json) | [Report](avatars/increment1/REPORT.md), [20-sample comparison](avatars/increment1/comparison.json); 102 tests, native touch/keyboard/filter checks, sampled callback trace passed; baseline lifecycle/picker blockers retained. |
| 2A Cactus/bonsai/sunflower | Complete — measured relative gates passed | `6064a82`, `1b453e0`, `28fbb7b` + evidence revision | [Six-stage comparison](avatars/increment2a/before-after-bare-light.png), [51 sheets](avatars/increment2a/sheets/index.json), [motion](avatars/increment2a/before-after-motion.webm) | [Report](avatars/increment2a/REPORT.md), [fresh 20 comparison](avatars/increment2a/comparison.json); 105 tests, 324 visual reaction cases, mature care/traces and native checks passed. Pre-fix failures retained; audio-sync feedback fixed. Remaining lifecycle/picker blockers persist. |
| 2B Fern/mushroom/succulent | Blocked — confirmed layout fixes implemented; residual timing unresolved | Artwork `6ddce82`; performance fixes through `c57d9be`; rejected fixture `c571122` | [Six-stage comparison](avatars/increment2b/before-after-bare-light.png), [51 sheets](avatars/increment2b/layout-fix/visual/sheets/index.json), [reaction checks](avatars/increment2b/layout-fix/visual/motion-rig-check.json) | [Report](avatars/increment2b/REPORT.md), [assessment](avatars/increment2b/assessment.json). 260 tests and6 browser checks pass; 1,734 exact SVG checks,486 reactions/21 reduced-motion transitions and4,896 pixel-identical cells. Prior same-product native15 frames pass16.7–16.8ms, but direct trace fails265.347ms/33.4ms. Independent thread-pinning cohort fails fern133.3ms framep95; candidate rejected. All records retained; final full matrices not started;3A pending. |
| 3A Ground animals + bird | Pending | — | — | — |
| 3B Swimmers + owl + bat | Pending | — | — | — |
| 4A Wardrobe model/rendering | Pending | — | — | — |
| 4B Wardrobe UI/integration | Pending | — | — | — |
| 5 Movement | Pending | — | — | — |
| 6 Release readiness | Pending | — | — | — |

## New-chat invocation

Use Sol. Read docs/AVATAR_VISUAL_UPGRADE_PLAN.md in jongsky25/css-is and the
repository instructions. Inspect the execution ledger and current code, then
execute the next pending increment completely. Preserve the plan's visual and
performance gates. Record evidence, tests, commit and remaining work in the ledger.
Continue through subsequent increments if the session permits. Prepare reviewable
changes; do not deploy without deployment authorization.

### Increment 0 execution note — 2026-10-25

Development-only macro gallery, measurement/lifecycle scripts, contact sheets and
call-site inventory added. All 100 selected tests passed. Baseline acceptance is
not claimed: the short smoke sweep is not the required five-run, 30-second full
application baseline. See [remaining acceptance work](avatars/BASELINE_REPORT.md).
Increment 1 remains blocked by increment 0. No production changes or deployment.

Harness/report commit: `d426cc5` (`test: add local avatar gallery and baseline probes`).

### Increment 0 completion — 2026-10-25

The earlier partial status is superseded. Four real-HTTP configurations each ran
five samples with 30 seconds of Home idle and at least 30 seconds of interaction.
The runner also checked persisted care, every profile species selection, growth,
seasonal administrator previews, offscreen/reduced motion and 20 navigations.
A separate native-tab check verified true hidden state for 30 seconds, touch drag
and keyboard movement. All five opt-in cases passed; final relevant regression
tests passed 100 cases (five opt-in skips in the ordinary run).

Captured 51 compact sheets (4,896 cells) across months/costumes/surfaces, retained
hero/mood sheets, and reviewed the catalog plus monthly/seasonal overviews.
Reproduction commands, environment/source hashes, transfer sizes, event timings,
frame/long-task samples, JS heap, renderer RSS and DOM/listener trends are recorded
in [the baseline report](avatars/BASELINE_REPORT.md).

Existing gate misses: one mobile cold sample had frame p95 50 ms and substantial
page-wide long tasks; seven plant picker thumbnails animate together; offscreen
motion continues; native hidden rendering stops frame callbacks but chase/init/idle/
roam timers continue; AvatarAudio.sync and MutationObserver initialization form a
repeating update loop; same-document remounts retain document pointer listeners.
Do not discard the slow sample, relax thresholds, or treat baseline completion as
release approval. Artwork and behavior remain unchanged. Increment 1 can now use
this baseline for its before/after gates; existing lifecycle issues remain release
blockers to resolve during motion/integration work. No deployment performed.

### Increment 1 completion — 2026-10-25

Redesigned the cat and blossom plant across six anatomical/structural growth
stages, with consistent palette/outline tokens, local UUID-scoped gradients and
a documented head/neck/pot anchor contract. Gallery-only bandana and pot-wrap
prototypes prove layering without persistence. No runtime JavaScript, scoring,
care cooldown, account identity or seasonal policy changes. Other fourteen
species are pixel-identical in 4,284 captured cells.

Bare/prototype contact sheets cover 64px and hero size on three surfaces; the
before/after motion recording and 51 monthly/seasonal sheets are retained.
Corrected mature ear tuft ownership and kept stage 3 Seedling / stage 4 Budding
semantics. Source and render-equivalence evidence identify these corrections.

A first comparison passed aggregate budgets but targeted traces exposed long
avatar callbacks in one replay. The final art uses drawn shadows instead of
inherited SVG drop-shadow/color filters, keeping droopy pose/eyelid cues and
opacity feedback. Historical diagnostics are retained separately. The final
paired trace observed no avatar callback >50ms (maximum about 8.7ms); page-wide
paint-task attribution remains limited as documented.

Final comparison: twenty full-duration samples, five per viewport/cache case.
LCP median deltas: desktop cold +8ms, desktop warm +4ms, mobile cold -60ms, mobile
warm -12ms. All measured relative comparison gates passed; every final mobile
interaction p95 was under 33ms, with no JavaScript errors or external requests.
Added compressed CSS/JS 124B; largest median document increases Home 1,245B and
picker/profile 2,008B. Renderer-RSS medians decreased in all cases.

102 relevant tests passed; native hidden/touch/keyboard and computed-filter
checks passed. No physical-device claim. Existing offscreen motion, hidden
timers/initialization feedback, animated plant thumbnails and remount-listener
retention remain release blockers for motion/integration work. Increment 2 is
next; no deployment performed. See [the full report](avatars/increment1/REPORT.md).


### Increment 2A completion — 2026-10-25

Completed the first bounded plant batch permitted by increment 2: cactus, bonsai
and sunflower at six stages each. Original outlined vectors use scoped leaf
gradients and drawn shadows. Cactus gains arms, ribbing, buds/flowers and a basal
pup; bonsai gains a curved connected branching structure, canopies and blossoms;
sunflower gains cotyledons, heart-shaped foliage, a closed stage-4 bud and a
secondary flowering branch. Seedling/Budding/In bloom labels and thresholds are
preserved. Wet-soil care layers, seasonal pot decorations, bloom animation and
empty pot accessory anchors remain compatible. Bloom positioning and animation
use separate groups; sunflower headwear uses local coordinates.

Accepted visual evidence includes 64px/170px comparisons, 51 light/dark/contrast
monthly/seasonal sheets, a motion recording, and 324 stage/mood/reaction checks.
The thirteen unchanged species are pixel-identical across 3,978 sheet cells.
105 render/care/audio/onboarding/appearance tests passed. Mature synthetic plants
passed real authenticated Home/Wellness care persistence and wet-soil checks;
touch/keyboard/native hidden checks and three matched mature-plant traces passed.

The initial 20 were **not accepted**: cold-desktop LCP median472 ms exceeded the
baseline by 148 ms and one warm-mobile frame p95 reached33.4 ms. All raw results and
traces are retained under `avatars/increment2a/pre-sync-fix/`. The proposed
five-run extension was superseded before collection by a source fix and a fresh
full 20. `AvatarAudio.sync()` now leaves unchanged icon text intact, preventing the
child-list observer/init feedback; its cache key is v8.12. A regression test
verifies idempotent sync in both sound states. Native hidden measurements show
observer-scheduled init callbacks falling from 30 to 0 over 30 seconds; chase/idle/
roam timers remain. No threshold was changed and no outlier was dropped.

The fresh 20 on `28fbb7b` passed all measured relative byte, LCP, interaction,
renderer-memory and frame gates against increment 0; each final mobile interaction
sample met 33 ms. Raw medians/worst runs, source hashes, the art-only counterbalanced
load diagnostic, attribution limits and remaining release blockers are in the
[report](avatars/increment2a/REPORT.md). The primary timing fixture still uses
cat; new mature plants have separate matched mobile traces, not five-run
per-species Home benchmarks. No physical-phone or 60 fps claim, new dependency,
external asset request, account/scoring change, wardrobe persistence or deployment.

Next pending increment is **2B: fern, mushroom and succulent**, preserving their
frond/cap/spore/plumping hooks. Remaining offscreen motion, chase/idle/roam timers,
seven animated picker thumbnails and same-document listener retention still block
release and must be resolved in motion/integration work.


### Increment 2B execution — 2026-10-25 — blocked on LCP

Implemented fern, mushroom and succulent at all six stages in `6ddce82`, finishing
the plant artwork deliverables but **not** performance acceptance for increment 2.
Fern gains fiddleheads/unfurling shoots and a frond fan with sori; mushroom gains
a domed cap, expressive stalk, gills, veil and fruiting cluster; succulent gains
fleshy rosettes, buds/flowers and a connected basal offset. Scoped leaf/cap
gradients, drawn shadows and pot/soil details follow the established collection.
Existing frond/top-frond, cap/spore, blink, bloom and plump hooks remain. Plain
outer groups own placement; animated inner groups retain it during CSS motion.
Mushroom seasonal slot count/order is preserved. Both runtime JS files and all
account/growth/scoring/care policy are unchanged from 2A.

A bounded selector restores the existing succulent idle-plump reaction that the
static-idle rule had overridden. Mid-care reduced-motion testing exposed unclassed
water-drop paths escaping the media rule; that rule now includes those paths.
107 tests, 486 relevant reaction/stage/mood/theme cases and 21 reduced-motion
transitions passed. All 51 monthly/seasonal sheets and 64px/170px comparisons are
retained. The thirteen untouched species are pixel-identical across 3,978 cells.
Real authenticated mature-plant care, native hidden/touch/keyboard checks and three
matched mobile input traces passed; no identified avatar callback exceeded 50 ms.

**The cold-desktop LCP gate failed.** The complete 20 current samples passed other
measured byte, interaction, frame and renderer-memory gates with zero JavaScript
errors/external attempts. Cold-desktop LCPs were 812/336/664/728/308 ms: median 664 ms,
+340 ms versus the historical increment-0 median 324 ms (100 ms budget). All ten
mobile interaction samples met 33 ms. Picker/growth, seasonal-preview and care
latency/memory deltas also passed; raw values are in the assessment.

The [predeclared investigation](avatars/increment2b/investigation-plan.json)
preserved every current sample and reproduced five original-source cold-desktop
runs from immutable `1c964dc`. Protocol/probe ASTs, fixture setup, dependencies,
storage and auth inputs match the originally measured current protocol. The first
control used tmpfs while current source uses overlayfs, so it is retained only as
exploratory evidence. The corrected control used sibling overlay storage and
recorded 724/320/372/320/376 ms: median 372 ms. Current 664 ms remains **+292 ms** over
the corrected control, still failing 100 ms. No threshold or favorable sample was
substituted. All historical/current/control data are retained separately.

Navigation/resource instrumentation in `a607092` supports further attribution.
Three diagnostic full-scenario runs recorded LCP 720/572/412 ms, with HTML TTFB
441/133.5/54.4 ms and DOM-interactive 631.1/424.9/302.7 ms; several unrelated scripts
also showed 100–240 ms delivery. A short counterbalanced art-only diagnostic had
similar current/original medians 328/340 ms and did not reproduce the complete-
fixture gap. Its test-only compositing experiment saved 12 ms and was not applied
to production. These diagnostics do not override the failure or isolate a causal
avatar hot path. See the [original blocked report](avatars/increment2b/REPORT-blocked.md) for limits
and exact reproduction commands.

**Next pending work remains 2B:** attribute and resolve cold-load response/resource
and complete-fixture startup delay, then demonstrate the gate with fresh controlled
validation. Do not start 3A while the gate fails. Existing offscreen motion,
chase/idle/roam timers, seven animated picker thumbnails and same-document listener
retention remain separate release blockers. No wardrobe persistence or deployment.


### Increment 2B acceptance follow-up — 2026-10-25 — motion remains blocked

Implemented four bounded fixes: lazy species compilation (`853c93d`), pointer
read/write batching (`41c8e01`), deferred responsive Home search lookup (`00d76bc`),
and chase/drag read batching plus conditional reaction replay/static previews
(`b7daa79`). No art geometry, scoring, account, care policy, sound or dependency
change. The selected companion remains animated; all16 picker cards have0running
animations. Keyboard reaction replay, pointer/head limits and actual responsive
search-result navigation pass three browser checks.

Validation:260 tests,1,734 exact SVG comparisons,486 reaction cases and21
reduced-motion transitions pass. All51 fresh sheets/4,896cells are pixel-identical
to original2B. Static picker thumbnails are now resolved; selected offscreen
motion, chase/idle/roam timers and same-document listener retention remain separate
release blockers.

The complete20-run `00d76bc` cohort passed all primary gates: cold-desktop LCP
median328ms/worst652ms (+4ms vs historical324ms;−44ms vs overlay control372ms).
Desktop warm148ms, mobile cold564ms, mobile warm308ms; mobile interaction
framep95 values16.7–16.8ms. All20 samples and the1412ms cold-mobile worst run
remain under [pre-motion-fix](avatars/increment2b/lcp-unblock/pre-motion-fix/application/summary.json).
Those measurements do not validate the subsequent product revision.

Fresh focused instrumented traces failed after that matrix. An exploratory
recorder introduced excessive stack-capture overhead; its raw data were retained.
Thirty counterbalanced old/new-art runs without API wrappers or tracing identified
a genuine new mushroom chase callback60.4ms, including41.6ms forced layout.
This motivated `b7daa79`; that source's fresh fifteen native focused checks still
fail. Fern includes33.4ms framep95 and295.8ms reported avatar callback; mushroom
includes160.7ms. Several callbacks report0forced layout; scheduling/GC or another
cause remains unproven. These are retained failures, not waived outliers.

The [current assessment](avatars/increment2b/assessment.json) and
[report](avatars/increment2b/REPORT.md) record every final native result and exact
budgets (33ms framep95,50ms owned callback). The final-source original20 matrix
was intentionally not started because its focused prerequisite failed. Earlier
failed20, stopped attempts and all diagnostics remain separate. No budget changed,
sample replaced, deployment performed, or3A implementation started.

**Next pending work remains2B:** isolate the remaining native callback/layout
stalls before another bounded fix. Once focused gates pass, rerun the original20
matrix and native hidden/touch/keyboard/real-care checks on that same source.

Final-source behavior checks also pass: [native hidden/touch/keyboard](avatars/increment2b/lcp-unblock/native-functional/application/native-visibility-touch.json)
confirms actual document.hidden with zero hidden rAF frames, working movement and
zero animated picker cards. [Real care](avatars/increment2b/lcp-unblock/care/live-plant-care.json)
confirms all three mature plants' authenticated care POST, SQLite timestamp and
wet-soil UI. These passing checks do not override the failed motion prerequisite.


### Increment 2B geometry/layout follow-up — 2026-10-25 — final validation

Product changes through `c57d9be` remove repeated live geometry reads from
interaction callbacks, refresh geometry in ResizeObserver’s completed-layout
phase, and restart existing happy CSS animations without forced offsetWidth
reflow. Cached movement follows actual CSS transition timing/easing; repeated
clamped destinations retain the existing timeline. Only head-tracking species
measure SVG head bounds (mature mushroom: six unnecessary reads before, zero now).
The new geometry scheduler and global observers/listeners remain stable after
twenty script evaluations. Artwork, care policy, account identity, scoring and
sounds remain unchanged. No new dependency, containment or compositing hint.

[260 tests](avatars/increment2b/layout-fix/validation-tests.txt),
[six browser checks](avatars/increment2b/layout-fix/functional/tests.txt),
[1,734 exact SVG checks](avatars/increment2b/layout-fix/artwork-equivalence.json),
[4,896 pixel-identical cells](avatars/increment2b/layout-fix/visual/unchanged-species.json)
and [486 reactions/21 reduced-motion transitions](avatars/increment2b/layout-fix/visual/motion-rig-check.json) pass.
Browser checks include actual transition-position agreement, drag bounds after
resize/scroll, stable geometry infrastructure, active animation replay without
layout reads, pointer/head limits and responsive search navigation. Every previous
failed/stopped cohort remains under `layout-fix/pre-*`; no sample is replaced.

The [attribution correction](avatars/increment2b/layout-fix/attribution-plan.json)
implements the original “avatar-attributable main-thread long tasks over 50 ms”
rule with direct native timeline FunctionCall wall spans. A blank page with no
avatar/application code reports a 143 ms native invoker duration for an empty
callback, so an invoker URL alone cannot establish owned work. Native invoker
records remain diagnostic. No CPU/GC/baseline subtraction or threshold relaxation
is permitted; both untraced and traced frame p95 must remain ≤33 ms. This does not
establish the cause of every earlier stall or attribute all page-wide rendering.

The [controlled fixture](avatars/increment2b/isolated-fixture/final-fixture.json)
uses three-core affinity with unchanged Chromium154, CPU1/4, viewport, date/seed
and 30-second scenarios. Fresh original-source `1c964dc` and current-source
matrices must share this setting and pass both fresh matched and original
historical budgets. The CSS compositing candidate was rejected: no frame
improvement. Final callback traces, original20 matrices and current-source native
hidden/touch/keyboard/persisted care checks are pending below; acceptance remains
blocked until their recorded gates all pass. No deployment or3A work.

The first final-source untraced15 all pass16.7–16.8ms, but direct tracing still
finds fern33.4ms/265.347ms. [All records remain](avatars/increment2b/layout-fix/pre-thread-pin-fixture/STOPPED.json).
A separate profile diagnostic finds gaps and no nested layout, including old-art
failures. Chromium154’s POSIX throttle busy-waits in SIGUSR2 and blocks SIGPROF;
this limits attribution but does not waive any result. The predeclared
[thread-pinning diagnostic](avatars/increment2b/layout-fix/thread-pin-plan.json)
passes all four old/new-art runs (callbacks19.632/23.374/14.013/7.703ms; frames16.8).
Fresh native15/trace30 now use renderer main/throttler CPU1 affinity within the
existing CPUs0–2 fixture. Both full original/current matrices must share it and
pass historical budgets too; diagnostic results cannot substitute for acceptance.


#### Final outcome of the geometry/layout follow-up

**2B remains blocked.** Product fixes through `c57d9be` preserve every artwork
cell and pass260 unit/integration tests plus6 functional browser checks.
The original final-product untraced15 all meet16.7–16.8ms framep95, but the
same-product direct fern trace still fails: startPet70.488ms, chase265.347ms
(threadCPU205.621ms), frame33.4ms. No nested layout events appear in those
callbacks. Subsequent CPU profiles show long sampling gaps and reproduce slow
callbacks with old and new art; this does not isolate another application hot
spot or establish host scheduling as the cause. No CPU/GC time is subtracted.

The independent thread-pinning acceptance cohort fails fern framep95
**[16.8,16.8,16.8,133.3,33.4]ms**, so the candidate is **rejected** despite its
four successful diagnostic runs. All5 fern and2 completed mushroom samples
remain in [the stopped cohort](avatars/increment2b/layout-fix/native-control/STOPPED.json).
No succulent, subsequent trace30 or fresh original/current full matrices were
started after this prerequisite failure. The optional pin helper remains solely
for reproducing this rejected experiment; it is disabled by default and never
loaded by application code. It must not be presented as the performance fix.

Current-source native hidden/touch/keyboard and real persisted plant-care checks
are recorded in the [report](avatars/increment2b/REPORT.md). Source/layout fixes
are reviewable independently of acceptance. Remaining work is to reproduce the
residual stall with a validated runner, isolate attributable work before another
product edit, then pass all original focused and complete-matrix gates. Historical
passing cohorts, raw invoker records and diagnostics cannot substitute for those
checks. No threshold relaxation, sample replacement, deployment or3A work.

### Increment2B chase write follow-up

Removed redundant chase class/transition/facing writes. A browser regression
exposed subpixel numerical drift at the movement boundary, causing10 transform
writes/second; ignoring chase-axis steps below0.01 CSSpx eliminates these writes
while preserving active chase and direction reversal. Direct drag/keyboard input
precision remains unchanged. Seven browser checks and1,734 exact SVG checks pass.
Five native mature fernCPU4 runs pass16.7–16.8ms framep95. The first mushroom
run fails33.3ms against33ms, so the cohort stops before subsequent trace/full
matrices. No rejected pinning, relaxed budget or sample replacement.
[Current report](avatars/increment2b/REPORT.md) and
[assessment](avatars/increment2b/chase-write-fix/assessment.json) retain all results
and measured working-tree source hashes on base df0cfb6. **2B still blocked;3A pending.**

### User-approved frame exception

The user explicitly accepts the recorded mushroom33.3ms frame-p95 result despite
the original33ms threshold. The0.3ms overrun is approximately0.9%;33.3ms is
approximately a30fps frame interval. This result no longer blocks2B. Preserve the
raw measurement and original budget; record this as an explicit acceptance
exception, not a changed historical result. Larger frame failures, the50ms
avatar-attributable callback limit, and all uncompleted performance checks remain
outstanding.2B cannot yet be marked complete solely from this exception.

### Current-source verification after the frame exception

**2B remains blocked by callback timing, not the accepted0.3ms frame overrun.**
Five counterbalanced old/new-art fern pairs completed on the current runtime.
Current callback maxima: [6.235, 141.084, 9.715, 5.255, 15.526]ms;
old-art controls: [5.147, 7.467, 12.332, 9.858, 5.448]ms.
Current framep95 values are16.8ms in four runs and33.3ms in one, matching the small overrun the user accepted. One current pointer-move listener
callback reaches141.084ms against50ms. No JavaScript errors or trace loss.
The same-source seven browser tests and1,734 SVG checks remain valid.
The remaining species/full-matrix checks were not started after this prerequisite
failure. User acceptance of the recorded33.3ms frame result remains in force.
[Verification assessment](avatars/increment2b/verification-current/assessment.json)
and [all raw traces](avatars/increment2b/verification-current/traces/fern/summary.json)
retain every sample; no CPU/GC subtraction or cause claim.

### Increment2B preference-cache follow-up

`c2f404f` removes repeated MediaQueryList.matches reads from input/timer handlers
using a boolean updated by the live preference-change event. Legacy addListener
is supported and queued curiosity frames recheck reduced motion. Eight browser
checks pass, including zero input-time preference reads and live motion toggling;
1,734 SVG equivalence checks pass.

Five counterbalanced fern trace pairs still fail the50ms callback limit: current
chase reaches210.804ms. Old-art controls also stall (framep95 up to99.9ms), so
these results do not establish another application hot spot or a scheduling cause.
Every sample remains in the [current report](avatars/increment2b/REPORT.md) and
[assessment](avatars/increment2b/preference-cache-fix/assessment.json). Remaining
trace/native/full-matrix checks were not started after failure. The user's33.3ms
frame exception remains accepted; no callback/large-frame waiver. Establish a
stable control fixture and attributable cause before further product changes.
**2B acceptance unresolved;3A pending.**
