# Avatar visual upgrade — phased execution plan for Sol

Status: Increment 0 in progress; baseline acceptance remains unmet. No artwork increments started.
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
- Artwork: templates/_avatars_art.html; frame, gradients and CSS:
  templates/_avatars.html.
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
| 0 Baseline | In progress — acceptance unmet | `d426cc5` (harness/report); evidence in following commit | [Fixed-noon contact sheets](avatars/smoke/) | [Report](avatars/BASELINE_REPORT.md); five short smoke runs per viewport/cache only; full-duration application scenarios still required. Existing offscreen animation and chase-listener retention observed. |
| 1 Cat + plant slice | Pending | — | — | — |
| 2 Plants | Pending | — | — | — |
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
