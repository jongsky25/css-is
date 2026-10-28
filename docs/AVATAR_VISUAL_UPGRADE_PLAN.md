# Avatar visual upgrade — phased execution plan for Sol

Status: 2B is provisionally accepted and unblocked by explicit user approval on 2026-10-28 (Asia/Manila), with unresolved memory risk accepted. Stop GC/instrumentation research. Full performance validation remains unproven. No deployment or later increment starts automatically.
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
or if it exceeds an applicable performance gate. Apply the explicit user-approved
2B exception below; preserve every measured failure. Other increments retain their
gates unless the user separately changes them.

## User-approved 2B provisional acceptance — current policy

[Decision](avatars/increment2b/PROVISIONAL_ACCEPTANCE.md): the user accepted the
recommendation to stop the disproportionate GC investigation and unblock the avatar
provisionally. The +10 MiB memory criterion and related unresolved memory/control/
observer prerequisites are deferred as blockers for provisional 2B acceptance only.
No numeric replacement limit is invented and no failed result is converted to pass.
The absence of significant slowdown is not guaranteed; full performance validation
remains incomplete. Keep current product cf363bf; leave candidate cd94bf3 isolated.

No new GC/native observer experiment, prepared disposal probe or acceptance matrix
is queued. Follow the next requested product task. No merge, deployment, candidate
promotion or later increment is automatically authorized. Historical blocked-status
and next-step instructions below are superseded by this explicit decision.

## Historical investigations — retained evidence

## Original failed-GC offline audit — disposal witness is missing

[Latest report](avatars/increment2b/original-gc-audit/REPORT.md), [assessment](avatars/increment2b/original-gc-audit/assessment.json)
and [prepared minimal probe](avatars/increment2b/original-gc-audit/NEXT_PROBE.md). Zero new browser
measurements. All **145** original hashes verify; the original failed native audit
reproduces exactly. **36 focused tests pass.** No failed result is rescued.

The failed probe runs natural marking, weak processing and observed sweeping.
Both probes have 21 completed shutdown calls/six pagehide markers/six beacon receipts
before first marking. The passing probe returns five labelled generations before
its second major, so a universal second-GC requirement is insufficient. Receiver
joins remain exact 1,536; source-labelled page reclamation is the failing prerequisite.

Pinned source distinguishes proxy disposal, ScriptState cleanup and notification
from Document shutdown. The old capture lacks these call records and retaining
edges. The context-notification trace event is conditional; its absence does not
prove notification was skipped. Marked proxy counts are not root/context identities.

Next implement/validate/freeze the prepared four-function native disposal witness:
proxy lifecycle/reuse args, nested ScriptState disposal, V8 notification and GC
boundary. No broad handle hooks, object-field reads, snapshots, Runtime subscription,
collection requests or repeated per-slot startup RPC loop. No new collector has
run. No supported product fix, qualification, 2B acceptance, merge or deployment.

## Uninjected GC comparison — low retention in both factors

[Latest report](avatars/increment2b/uninjected-gc-contrast/REPORT.md) and
[run40609043507](https://github.com/jongsky25/css-is/actions/runs/40609043507):
frozen 8f7b7d4 completes counter/trace/trace/counter without Frida attachment or
SYS_PTRACE. All four have one document, 9,007 nodes at stage 6 and 6,008 at stage 11.
Both trace slots record two natural major collections, three marked global proxies
and 756,936 bytes after each collection. Counter-only GC counts are unobserved.
Low retention therefore does not require native observation or measurement tracing;
two slots/factor establish no causal effect, correction or population failure rate.

**32 local/cloud tests pass**; all **39** hashes and independent analyses match.
The final DOM-counter trace bounds are uncertain in both traced slots and remain
flagged. Retained setup logs have the same 103 downloaded package versions as the
failed job, but CPU model differs (old AMD 7763/current Intel 8573C). Earlier AMD
captures also had low retention; no environment explanation is established.

No supported correction or qualification. Next audit the retained failed sample's
GC/weak-reference/disposal chronology against pinned source, identify missing root
evidence and a specific reproduction condition/change before more measurements.
No unchanged retry, product change, candidate promotion, acceptance or deployment.
PR #523 remains unmerged; no active measurement. Original 2B gates remain blocked.

## Native-buffer caller diagnostic — weak queue identified, failure still absent

[Latest report](avatars/increment2b/native-handle-buffer/REPORT.md) and
[run40605880095](https://github.com/jongsky25/css-is/actions/runs/40605880095):
frozen 76baed0 completes four captures with 9,543 native records each. It removes
per-event JS callbacks and the added Runtime subscription, and covers 1,011 births
per slot outside known owners. The sole older unreleased candidate among observed
births resolves to V8's WeakFixedArray compilation queue; its function entries are
weak. This is not evidence that the queue strongly retains old documents.

All four show low retention. No supported correction yet. **47 local/cloud tests
pass**; all **42** hashes, four independent analyses, new native buffer proof and
original preflight audit match. The buffer proves 20 clock samples, 1,024 immutable
records/four threads and deliberate overflow. Candidates are not a strong-root
census; inlined transitions/restoration and pre-attach roots can be missing.

Next compare uninjected captures with and without GC tracing in a separately frozen
fixed design, before another intrusive graph. No unchanged rerun, qualification,
application transport cost result or 2B acceptance follows. PR #522 is unmerged;
no active measurement, product change, candidate promotion or deployment.

## Snapshot-free context journal — cleanup observed, failed root still unknown

[Latest report](avatars/increment2b/context-handle-journal/REPORT.md) and
[run40599450345](https://github.com/jongsky25/css-is/actions/runs/40599450345):
frozen 2c898c6 completes four journal-only/journal+membership captures. At natural
GC stages 6/11, zero known older context-owner handles remain strong; all eight known
strong handles belong to the current navigation. All four show the low-retention
profile, so this confirms cleanup only in those captures and does not explain the
previous failure. Other/pre-attach roots are unobserved; weak is not collectable.

**47 local/cloud preflight tests pass**; all **39** result hashes verify and all four
independent journal analyses plus native preflight audit match. No snapshot, GC
request or extra wait. Callback/subscription overhead remains unqualified; no
native/application qualification, supported correction or 2B acceptance follows.
Next cover other handle owners/native caller sites with a separately frozen native
buffer diagnostic to reduce per-event JS/subscription effects. No unchanged rerun,
product change, candidate promotion, merge or deployment. PR #521 remains reviewable.

## Native root diagnostic — complete, retaining root not identified

[Latest report](avatars/increment2b/native-root-retention/REPORT.md) and
[run40596878155](https://github.com/jongsky25/css-is/actions/runs/40596878155):
frozen 2a1f2f4 completes four root captures after the first natural major GC.
All four show the low-retention profile, with three native contexts and one native
HTMLDocument. Their paths cannot identify the extra roots in the previous failure.
All **42** manifest hashes verify; all four independent graph analyses and the
native selftest audit match. **43 local/cloud preflight tests pass.**

Previous failed-run evidence shows the same retained-document profile in an
uninjected control; the passing probe already reclaims selected pages during its
first GC. Hooks alone and a universal second-GC requirement are insufficient
explanations. Snapshot generation finishes some sweeping and changes scheduling:
this is diagnostic evidence, never a replacement qualification or memory result.

No supported correction yet. Next record context disposal and persistent-handle
ownership around natural GC without snapshots or forced collections. Application
transport remains unmeasured, original 2B gates unchanged. PR520 is unmerged; no
active measurement, product change, candidate promotion, acceptance or deployment.

## Application observer calibration — fresh native prerequisite blocked

[Latest report](avatars/increment2b/application-observer-calibration/REPORT.md) and
[run 40532187252](https://github.com/jongsky25/css-is/actions/runs/40532187252):
frozen lossless transport 9e47c14 passes **80 cloud/local preflight and 102 expanded
local analysis tests**, but fresh full native qualification fails source-labelled
natural page returns in the first probe. Both probes retain 1,536 exact joins and
pass timing/cost; the second probe passes all gates. Application proof and all four
application slots correctly do not launch, so new transport cost is unknown.
All **145** artifact hashes verify and independent native audit reproduces failure.

Previous complete application attempt 3cdbb37 passes actual receiver proof, stable
main-content selection, 100% coverage and natural labelled reclamation in both probes,
but fails the unchanged 5% cost gate at **5.6545% / 5.3103%**. All four full workloads
and 196 verified hashes are retained; independent audits agree. Every earlier failed
attempt is archived. New transport preserves every DOM read and 128 getters/mount;
all decoding remains charged. No favorable unchanged rerun, GC forcing or gate waiver.

[PR #519](https://github.com/jongsky25/css-is/pull/519) remains unmerged and reviewable;
superseded PRs515–518 are closed. Product cf363bf and candidate cd94bf3 remain unchanged.
No active run, app attribution qualification, 2B acceptance, merge or deployment.
Next inspect the failed native generation/trace evidence before freezing a supported
change; prior successes cannot replace qualification of the current job.

## Hosted native calibration — instrument prerequisite passed

[Latest report](avatars/increment2b/hosted-native-calibration/REPORT.md) and [cloud run](https://github.com/jongsky25/css-is/actions/runs/40508949824):
frozen 0af68b8 passes fresh native/receiver proofs and the full four-slot schedule.
Probe costs **2.7115/2.9615%**, control variation **1.8382%**, paired durations
**1.01442/1.01464**; exact 1,536 joins and DOM4/SVG3/style3 measured returns per probe,
all twenty overlapping native sweeps with natural MajorGC. All gates unchanged.
Proof/screen/period outputs independently reproduce; 57 artifact hashes verify.
**104 local and 60 cloud tests pass.** Instrument qualified for a separately frozen
application calibration on this hosted condition; application/2B acceptance false.
Controller mistakes/incidental controls are retained and cannot replace samples.
Separate native setup PR #513 is unmerged; no product changes/deployment. Next
freeze application-specific selection/integrity/cost calibration before memory
attribution or app comparisons. Earlier failed budgets/acceptance obligations stand.

## Mobile hosted runner — cloud diagnostic succeeds, registration pending

[Latest report](avatars/increment2b/mobile-runner/REPORT.md): setup [PR #511](https://github.com/jongsky25/css-is/pull/511)
adds only a phone-accessible workflow and instructions to main, with frozen harness
92b8428 checked out separately. Standard hosted run 40503804962 completes four
controls (3900.752/3818.159/3845.508/3893.634ms; ~2.16% range), zero reported CPU
steal/throttle, and identical independent audits. All initial image/timer failures
remain archived. **101 focused tests pass.** User acceptance supersedes the earlier
reserved-runner-only prerequisite; no physical isolation claim is made.
The cloud result is viewable now. Run workflow button registration remains pending
main's existing release-version check; no merge/version bump/deployment occurred.
No native probe calibration, application comparison or 2B acceptance follows.
Next freeze a complete native-recorder calibration on this hosted condition with
all unchanged gates; never reinterpret the control-only diagnostic as qualification.

## Runner isolation capability — external infrastructure required

[Latest report](avatars/increment2b/runner-isolation/REPORT.md) confirms a hard runner-access blocker. Frozen inventory
ccb4365 reports KVM, five visible CPUs/four-CPU quota, no exclusive cpuset and CPU
controls not writable by this user. Connected runtime tools have no reservation,
migration or capacity-change action. GitHub runner inventory was denied; alternate
runner availability remains unknown. No environment changes or performance runs.
A [concrete runner handoff](avatars/increment2b/runner-isolation/RUNNER_REQUIREMENTS.md) specifies required access, provider isolation
evidence, exact toolchain and resume order. No unchanged local experiment is
queued: supply a documented reserved runner/new host condition before freezing
another comparison. Prior v12 control failure and 2B block remain unchanged.

## Control timing diagnostic — host contention signal, qualification still blocked

[Latest report](avatars/increment2b/control-phase-timing/REPORT.md): frozen 84ce8e9 completes four uninjected controls with
108 operation brackets each; all d867258 initialization failures are preserved.
Navigation and before-DOM serialization dominate the slow/fast difference. The
slowest first navigation/serialization coincide with **31.03/38.74% aggregate CPU
steal** and no cgroup quota-throttle increments. Pressure counters are unavailable.
This supports investigating runner contention/isolation; it does not prove the
historical v12 failure's cause. Diagnostic variation of 16.1449% does not replace
v12's failed **20.7568% >20%** result. Both archives re-audit identically; **97 focused
tests pass**. Product unchanged; no application calibration or 2B advance. Next
obtain provider/runtime scheduling evidence and a supported runner-isolation
intervention before a newly frozen complete comparison. No quiet-window retries,
slow-sample exclusion, timing subtraction or budget waiver.

## Native callback recorder — costs passed, control stability failed

[Latest report](avatars/increment2b/native-callback-recorder/REPORT.md): frozen native preflight b2bf252 and live receiver proof
f676f7a pass. Calibration 04ca993 (lifecycle v12) preserves 1,536/1,536 receiver
joins per probe and all-mode source-labelled reclamation: DOM4/SVG3/style3 each,
all twenty labelled generations overlapping natural sweeps. Cost bounds pass at
2.9486/3.7522%; paired durations pass. Controls vary **20.7568% >20%**, so the
instrument remains unqualified for application calibration and 2B stays blocked.
All three completed archives reconstruct/re-audit identically; failed native
attempts remain. 81 focused tests pass; product unchanged. Next freeze a separate
control timing diagnostic to distinguish navigation/wait/serialization from host
scheduling. No unchanged favorable rerun, time subtraction or budget waiver.

## Mixed getter fixture — representative reclamation passed, one cost gate remains

[Latest report](avatars/increment2b/mixed-reclamation-getter/REPORT.md): exact-type capability covers HTML div/span and SVG paths
against 384 geometry references. The fixture reproduces qualified d732b70 DOM/SVG/
style document bytes. Four distinct fixed calibration revisions retain all failures.
Latest d0eeb19 (lifecycle v11) preserves 1,536/1,536 receivers in both probes and
observes labelled page returns for all three modes, with natural MajorGC/sweeps.
Ten/eight labelled generations return inside measurement; all 18 overlap sweeping.
Cost still fails one probe: 5.2188% versus 5%; other probe 4.2179%. Controls vary
18.1054% (<20%); paired durations pass. Instrument/application calibration remains
unqualified; no 2B advance. All four screen and four proof archives re-audit
identically; 67 focused tests pass. Product unchanged. Next prove a cheaper native
callback/buffer recorder before another fixed calibration; no unchanged favourable
rerun, omitted observer work, forced GC, sample reduction or budget waiver.

## Absent-attribute receiver — capability and cost screen passed; reclamation still missing

[Latest report](avatars/increment2b/absent-attribute-receiver/REPORT.md): exact native getter/geometry cross-check (f4ed9d9) passes
128/128 identities and null returns with unchanged DOM. Frozen screen 3190099
completes four fixed slots; both probes preserve 1,536/1,536 selected native page
joins and pass cost/integrity gates. Observation bounds 4.9961/4.9588% are below 5%
(first margin only 0.00394 percentage points); controls vary 0.5199%, paired ratios
1.06259/0.95624. No collection or page return is observed in either probe, so the
independent through-reclamation capability still fails. No application comparison
or 2B acceptance. All 23 archive files reconstruct/re-audit identically; 46 focused
tests pass. Product cf363bf unchanged. Next inspect the previously qualified fixed
DOM/SVG/style fixture as a source-supported natural-reclamation capability test;
do not repeat this screen for favorable GC or waive its missing prerequisite.

## Native lifecycle discrimination — labelled reclamation observed, gates still fail

[Latest report](avatars/increment2b/native-membership-lifecycle/REPORT.md): pinned source/runtime show BFCache disabled and normal
nonpersisted document departures. Latest v6 (5364334) preserves 1,536/1,536 sampled
receiver/page joins in both probes. One records MajorGC, native sweep and 500 page
returns inside the window, including ten generations previously containing labelled
elements from fixture documents 0–9. All ten return brackets overlap native sweep.
The other probe records no collection or return. This is synthetic membership and
reclamation evidence, not exclusive ownership or a product-memory pass.

V6 still fails observation bounds (6.687/5.322%), 28.871% control duration variation
and first probe/control ratio 1.28597. No application comparison. All earlier setup,
message-delivery, transport-test and overhead failures remain; five archives re-audit
identically. 34 focused tests pass, and the beacon capability passes. Product cf363bf
unchanged; 2B/later blocked. Next prove a cheaper native receiver observable (for
example a source-verified absent-attribute getter) before new controlled qualification.
No unchanged favorable rerun, forced collection, budget waiver or product promotion.

## Native element membership — live coverage passes, reclamation unqualified

[Latest report](avatars/increment2b/native-element-membership/REPORT.md): two distinct frozen four-slot synthetic experiments complete.
V1 (3375008) fails first-document page coverage, pool-return coverage and paired timing.
V2 (02f59cb) uses larger fixed documents and a smaller predetermined census: both
probes map all 6,144 receiver observations to captured page generations, demonstrate
12 mixed-group generations, and pass unchanged timing gates. Neither records a
pool-return call, so reclamation capability fails and no application collection
runs. Both 17-file archives re-audit identically; 12 source identities / 12 cohort
files verify per experiment; 28 focused tests pass. No production source change,
fix, acceptance or 3A advance. Next establish document/history lifetime and natural
release-path observability on the controlled fixture before application use.

## Component-order diagnostic — calibration failed coverage

[Latest diagnostic](avatars/increment2b/snapshot-ordering/REPORT.md): frozen harness f84ef99 completes four current-only
control/probe/probe/control workloads on the exact Chromium build. All timing and
control-duration gates pass, but slot 1 has no recorded navigation major collection
or native sweeping, failing its predeclared coverage gate. No replacement or source
comparison. All 128 source hashes / 30 cohort files verify; reconstructed 36-file
archive re-audits identically. Initial auditor reporting failure is retained; the
correction preserves missing-coverage failure and every slot's timing. 27 focused
tests pass after that correction. All 40 prior gradient navigation samples and
32 adjacent intervals were reviewed offline. No product fix or memory acceptance
follows. Next prove a concrete source-ownership discriminant on a controlled
fixture, including allocations carried from earlier scenarios; do not rerun the
unchanged calibration for collection events. 2B/later remain blocked.

## Shared cat-gradient candidate tested — memory screen failed

[Latest report](avatars/increment2b/shared-cat-gradients/REPORT.md): candidate cd94bf3 shares identical cat gradients through
the existing page registry. Six-cat markup loses 41 elements / 90 attributes;
30 visual sheets (2,880 cells), the new real-HTTP test, eight applicable browser
regressions and 32 gate tests pass. Historical pagehide diagnostic fails identically
on unchanged and candidate sources; both failures and the pre-measurement test
selection correction are preserved. No lifecycle fix is claimed.

All eight uninjected workloads complete under frozen harness 52ed2ea. Forward RSS
fails at navigation 5 (+11.699MiB) and 10 (+16.301MiB); both same-source controls
fail stability (largest absolute swing 36.379MiB). All heap checks pass; renderer
counts match. 128 source/probe hashes and 24 files verify; extracted archive re-audit
is identical. Candidate remains isolated on codex/avatar-shared-cat-gradients;
product cf363bf stays unchanged. No larger validation, 2B acceptance or 3A advance.
Earlier attribute-simplification next-step notes are superseded by this result.

## Native page history captured — focused attribute-storage hypothesis

[Application history report](avatars/increment2b/page-history-application/REPORT.md) records a passed four-slot calibration and
all eight fixed comparison slots. All 1,160 stack offsets resolve; 80 files and
348 source/probe hashes verify; both archives re-audit identically; 33 tests pass.
Observed page-request histories show broad parsing/layout/style activity and many
returns within the capture. ShareableElementData caller requests rise in all four
source pairs (+33, +14, +20, +20), but total requests and same-source counts vary.
No avatar-specific byte ownership or product fix is established. Injected RSS is
not acceptance: the existing 10 source/16 control RSS failures still block 2B.
Next inspect the rendered cat's attribute storage/sharing for one supported
simplification, then require visual/functional and uninjected memory gates.
No 3A or other later increment. Earlier “history missing” notes are historical.

## Latest native allocation inventory — types identified, pool history missing

[All-slot raw type extraction](avatars/increment2b/native-type-ownership/REPORT.md)
reconciles per-page/global type bytes and counts to heap totals; 33 tests pass.
Large repeat variation spans layout/style/text/DOM, with pooled capacity larger
than the allocated-object difference. The raw type inventory existed but was
omitted from earlier summaries. Detailed dumps finish pending sweeps, so the next
causal gap is allocation history before pages enter the pool, not another endpoint
snapshot. No new measurements/product edits; 2B memory failures and later-phase
pause remain unchanged.

## Latest offline analysis — GC/sweep ordering, still no 2B acceptance

[Reader-retention report](avatars/increment2b/reader-retention/REPORT.md) covers all
eight archived slots, re-audits the evidence and passes 30 focused tests. Major GC
occurs inside the largest-gap snapshot, with native sweeping observed afterward;
endpoint pooled native capacity differs materially. No new browser run, product
change or waiver. Next evidence must identify native allocation ownership and
separate component observation timing; existing 10 source and 16 repeat-control
RSS failures stand. Do not select another cleanup fix from GC timing alone.

## Latest 2B verification — reader candidate does not clear memory

Candidate `cf363bf`, harness `586f81c`: thread-owned session/appearance connection
reuse is implemented and behavior-tested (220 distinct tests passing). Four-slot
calibration passes with 0.169% control duration change. The authorized fixed eight-
slot memory comparison completes with all integrity/overhead gates passing, but
10 source RSS and 16 same-source RSS checks fail the unchanged 10MiB limit.
Heap/count gates pass; this is not 2B acceptance. 336 source/probe hashes and 110
files verify; archives re-audit identically. Candidate remains on the verification
branch without deployment/promotion. Next investigate captured renderer document/
native-heap reclamation before another allocation change. No active measurement.
See [full report](avatars/increment2b/sqlite-reader/REPORT.md). Older status entries
below remain historical evidence; 3A and later stay paused.

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
  CPU throttle, p95 frame interval <= 33.3 ms during the defined interaction scenario
  (original33ms budget plus the user-approved0.3ms exception).
  Record baseline and regression; do not claim 60 fps solely from requestAnimationFrame.
- Renderer/JS memory growth <= 10 MiB over baseline after identical scenarios.
  **2B exception:** explicitly deferred as a provisional-acceptance blocker by the
  user on 2026-10-28; preserve measured failures and associated control uncertainty.
  This exception does not claim full performance validation or apply to later increments.
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
| 2B Fern/mushroom/succulent | Provisionally accepted — user-approved memory exception | Avatar `f700187` in current `cf363bf`; `cd94bf3` remains isolated | Existing visual/functional passes retained | [Provisional decision](avatars/increment2b/PROVISIONAL_ACCEPTANCE.md); historical failures retained in the [report](avatars/increment2b/REPORT.md): warm desktop offscreen +11.336, reduced motion +11.098, background +18.836 MiB; 10 MiB limit. Prior checker omitted these scenarios. [Exact source validation](avatars/increment2b/svg-validation/REPORT.md): all 40 observer/SVG samples complete, neither intervention qualifies in both orders; same-source repeat also fails +11.895 MiB. [Paired variance](avatars/increment2b/paired-variance/REPORT.md): 20 valid slots, 10 unstable control metric sets; late-navigation current RSS higher in all source pairs, but no qualified effect. No correction promoted. |
| 3A Ground animals + bird | Pending | — | — | — |
| 3B Swimmers + owl + bat | Pending | — | — | — |
| 4A Wardrobe model/rendering | Pending | — | — | — |
| 4B Wardrobe UI/integration | Pending | — | — | — |
| 5 Movement | Pending | — | — | — |
| 6 Release readiness | Pending | — | — | — |

## New-chat invocation

Use Sol. Continue `jongsky25/css-is` on `codex/avatar-2b-verification` and read
[the authoritative restart handoff](AVATAR_UPGRADE_HANDOFF.md#start-here--sol-handoff-current-after-component-order-calibration)
before the historical ledger. **Unblock 2B only; do not advance to 3A or later
increments.** Latest shared-cat-gradient candidate `cd94bf3` passed visual checks
but failed its memory screen; completed evidence is recorded in `dc06be8`.
A validated memory correction, stable same-source controls and complete audited
acceptance remain outstanding. Start with retained evidence, preserve all failures,
and execute one supported intervention with its frozen validation gates. Do not
merge, deploy, waive budgets or repeat unchanged failed candidates for a favorable
result. Update the handoff and ledger after the next completed experiment.

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
to original 2B. Static picker thumbnails are now resolved; selected offscreen
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

### Increment2B native throttle attribution and hosted verification

Product remains `c2f404f`; diagnostic/harness commits `f421044`, `0bd9092`.
The unchanged native Chromium SIGUSR2 throttle handler pauses up to345.950ms
inside the input window. This establishes emulator stalls independently of avatar
callbacks, without proving all previous callback failures were emulator time.
The ten instrumented diagnostic passes are not acceptance evidence. An independent
kernel-cpuset trial fails148.967ms and is rejected. See the [report](avatars/increment2b/REPORT.md)
and [native records](avatars/increment2b/signal-attribution/signal-analysis.json).

The dedicated verification branch now includes all independent functional,
focused and original/current matrix phases; no failed prerequisite suppresses
another phase. Original/current matrices share a runner, browser and filesystem;
RSS requires matching renderer counts. All failed samples are retained, with
callback50ms unchanged and the approved frame33.3ms ceiling. Local driver compile
and workflow parse checks pass. GitHub confirms the branch exists but reports no
workflow run; hosted results are unavailable and the cause is not established.
**2B acceptance remains unresolved;3A pending.** No merge or deployment.

### Increment2B verification repair — 2026-10-26

See the [current report](avatars/increment2b/REPORT.md). GitHub did start the earlier
workflows; the commit-run connector returned empty lists. Direct run/job lookup
reveals missing Chromium154 packages caused installation failure. Workflow65f1e16
uses exact Chromium 156 with fresh before/current baselines, validates all test
results, continues independent checks, and adds whole-runtime old/current traces.
Run40247047928 has passed setup and13 driver tests and is executing four sequential
phases. Final acceptance awaits all raw artifacts. Product unchanged atc2f404f;
no main merge/deployment. Historical154 results remain separate and unaltered.


### Complete hosted outcome and memory attribution — 2026-10-26

Run40247047928 completed on harness65f1e16, unchanged productc2f404f,
Chromium 156.0.8078.47. Audit40256359917 independently verified all raw cohorts,
source identities and controls. Functional, focused and whole-runtime phases pass.
All40 matrix samples completed. Current callback maxima across focused/runtime
traces are3.257/4.079ms; framep95 stays16.7–16.8ms. No50ms waiver.

One gate fails: warm desktop picker RSS median grows11,743,232bytes (11.199MiB),
exceeding10MiB by1,257,472bytes (1.199MiB). Other picker deltas are
−782,336bytes desktopcold, +561,152 mobilecold, +3,801,088 mobilewarm.
Warmdesktop picker has one live document in every sample, stable5086 DOM
counter nodes and106 listeners; heap median growth913,388bytes. This does
not establish a preview-retention leak. Native allocations need attribution.

[All numeric/log evidence](avatars/increment2b/hosted-complete/numeric-evidence.tar.gz)
includes source manifests and hashes for full traces retained in the original
artifact12622154659 (expires2026-11-02). Compact audit artifact12622139879
expires2026-11-25. Neither the failing cohort nor historical local failures
is replaced. Diagnostic branchcodex/avatar-2b-memory measures two opposite-order
original/current warm desktop cohorts with per-renderer status andsmaps_rollup;
no forced GC, RSS subtraction, product edit or changed budget. Diagnostics alone
cannot grant acceptance. Fix an established source, then validate affected gates.

Standalone summarize/compare tools now use the same approved33.3ms helper as CI
and expose original/current frame-budget metadata. Reprocessing a separate copy
of all40 hosted matrix samples leaves every original numeric value and verdict
unchanged. Archived source artifacts were not modified.


Memory attribution completed in [run40257027634](https://github.com/jongsky25/css-is/actions/runs/40257027634):
20 full-duration warm desktop samples, original/current/current/original, five
per cohort. RSS median deltas reproduce the regression in both orders:
+14.520MiB and+12.629MiB. Private memory also rises; this is not solely shared
page noise. [All raw evidence](avatars/increment2b/memory-diagnosis/hosted-evidence.zip)
and [summary](avatars/increment2b/memory-diagnosis/assessment.json) are retained.
Hosted old/current desktop screenshots have identical1440×3498 dimensions,
excluding a changed page-height explanation. The local paint-hint and allocation
probes remain diagnostic; neither established a fix. A static-preview trimming
candidate is under visual/functional validation. No acceptance status changed.


### Static-preview memory candidate — 2026-10-26

Picker and growth previews now request a static SVG variant that omits movement
wrappers and invisible care/spark/sleep reaction layers. Live companion SVGs and
JavaScript remain unchanged. This removes1,032 SVG DOM nodes per96-preview sheet. The raw fixture delta
is1,033 because the reference additionally injects one paint-mode style element.
All1,734 interactive SVG equivalence checks pass. The first original-pixel
comparison changed because removing will-change-backed rasterization sharpens
edges; those images and the failed exact comparison are retained. A controlled
reference with the same static paint mode gives4,896 pixel-identical cells
across all stages, outfits and three surfaces. No artwork geometry was removed.

Eight browser regressions, actual hidden/touch/keyboard checks, persisted care
for allthree plants and live seasonal updates pass. Seasonal updates still
preserve unsaved form edits and replace existing costume/accessory anchors.
[Candidate assessment and all evidence](avatars/increment2b/static-preview-fix/assessment.json).
Memory improvement is not yet claimed; hosted measurement is next.2B stays blocked.

Candidatef700187 memory verification: [run40260864049](https://github.com/jongsky25/css-is/actions/runs/40260864049), two opposite-order five-run pairs. Full final verification follows only if the measured memory candidate succeeds.


Static-preview candidatef700187 passes both targeted memory orders in
[run40260864049](https://github.com/jongsky25/css-is/actions/runs/40260864049):
+8.551MiB and+8.285MiB, both below unchanged10MiB. All20 samples have
matching three-renderer counts,30-second windows, all16 selections, browser156
and no JS errors or external requests. Picker DOM counters fall from5086 on
priorc2f404f to4561 on the candidate; original baseline is4878.
[All raw candidate memory samples](avatars/increment2b/static-preview-fix/hosted-memory-evidence.zip).
Full functional/focused/runtime/device-cache verification follows.2B is not yet accepted.
Final workflow exposes each sequential phase independently and records native
allocation details in both matrix arms, without changing any measurement or budget.


Final verifier preflight found a historical-control compatibility issue after
startingrun40263432618 (b1079aa): its old-art overlay loaded only the old macro,
while current growth callers now passstatic_preview. The control loader now
uses the matching original5b580d9 growth/profile caller templates as well;
historical macros are not patched or modernized. A regression renders six
stages through both historical/current caller APIs; all17 driver checks pass.
The obsolete run is superseded using verification-branch concurrency cancellation.
Productf700187 and both passing memory cohorts remain unchanged.

Final [run40263865865](https://github.com/jongsky25/css-is/actions/runs/40263865865) uses harness`e909de1`, unchanged product`f700187`. Setup and all17 verifier regressions pass; four gate phases are running sequentially. Supersededrun40263432618 is confirmed cancelled.

Monitoring diagnosis correction: the commit-workflow-runs tool explicitly filters
to PR-triggered runs. Its empty result for a push-triggered run was expected;
the assistant inference that no workflow had started was wrong. Public Actions
discovery plus direct run/job queries now track the actual runs.

### Final 2B acceptance — 2026-10-26

Final run 40263865865 and audit 40277957839 passed. Independent audit verified source identities, 156 retained file hashes, 51 PNGs/4,896 cells and all raw matrix memory medians. [Final report](avatars/increment2b/REPORT.md) supersedes earlier pending/blocked statements for 2B while preserving their historical evidence. All unchanged budgets pass; release_ready remains false. Full traces retained to November 25. Proceed to 3A.

### Acceptance correction — complete memory audit

The earlier final-acceptance appendix is superseded. It checked five active scenarios only and therefore did not establish the full memory gate. The corrected report retains the original evidence and records all uncovered failures. 3A remains unaccepted and paused on its separate branch; no 3B or later work has started.

### 2B lifecycle correction experiment — 2026-10-26 — rejected

The guarded pagehide cleanup candidate `509cd1a` fails eight RSS and one JS-heap comparison against the unchanged 10 MiB limit. Maximum increases are +28.738 MiB RSS and +10.063 MiB heap. The independent audit covers all 234 comparisons and 134 source hashes. The verification branch retains product `f700187`; the rejected candidate and raw evidence are preserved separately. Full acceptance and 3A/later increments remain paused. Next: correlate natural document collection, renderer lifetimes and native allocations before another product correction. See the [follow-up report](avatars/increment2b/lifecycle-memory-fix/REPORT.md).

### Natural collection attribution — complete, 2B still blocked

Eight instrumented workloads in both orders establish natural C++/V8 collection and locate the dominant RSS delta in the app renderer. Documents are reclaimed but RSS can remain elevated, so no persistent application reference or validated product correction is established. Product stays f700187; full acceptance and later increments remain paused. See the [complete evidence and next attribution question](avatars/increment2b/collection-attribution/REPORT.md).

### Native residency implementation — 2026-10-26

Combined native allocator/collection tooling is implemented and validated: four counterbalanced diagnostic workloads, 52 matched dumps, 48 passing analysis/accounting tests. Heap capacity remains above allocated-object totals in both sources; no repeatable source-level correction is established. Product remains f700187, 2B blocked, later increments paused. See the [implementation and findings](avatars/increment2b/residency-attribution/REPORT.md).

### Source isolation and geometry candidate — 2026-10-26 — not promoted

The 16-sample counterbalanced screen identified geometry observers and original SVG as leads. A shared-observer/navigation-cleanup candidate passed nine browser checks, but its hosted gate has six complete forward RSS failures (up to +49.984 MiB) and an incomplete reverse unchanged-current cohort caused by a preview timeout. Overall audit is inconclusive; the candidate is not promoted. All 27 completed samples and the failure log remain. Product stays f700187; full acceptance and later increments remain paused. See the [final candidate report](avatars/increment2b/geometry-lifecycle/REPORT.md).

### Late-navigation timing follow-up — 2026-10-26

Offline analysis of all four archived residency cohorts verifies 92 members and
passes sixteen analysis tests. Natural reclamation and retained capacity occur
in both sources; five navigation snapshots change document counts across the
dump window. See [timing report](avatars/increment2b/navigation-collection/REPORT.md).
No new acceptance samples or product changes; 2B and subsequent increments remain
blocked. Next diagnostic requires finer lightweight timing with paired controls.

### Per-navigation paired timing completed — 2026-10-26

Eight fixed local diagnostic slots, 160 observations; all 164 source/probe hashes
and 60 evidence files verify. 112 selected tests pass. Same-source variations
exceed 10 MiB at ten checkpoint/metric differences; no stable source fix established.
Current repeats retain a 31-document/~6.18 MiB JS-heap offset at seven matching
V8 GC-age observations, despite recorded natural collection/sweep activity.
See [report](avatars/increment2b/navigation-timing/REPORT.md) for all comparisons,
overhead, raw traces and the separate post-hoc follow-up. Retaining paths remain
unknown. Product unchanged; 2B/3A/later gates remain blocked, no measurement active.

### Allocation ownership analysis — 2026-10-26

Resolved 929 archived native samples (1,655 offsets; 92 members verified). Native
allocation sites do not identify document retaining references. Exact Chromium/V8
source confirms standard JS profile reads and heap snapshots force GC. Prepared
four-slot forensic snapshot protocol/runner remains unexecuted pending an explicit
exception; no natural/acceptance measurement changes. 123 selected tests pass,
one opt-in forensic browser test skipped. See [ownership report](avatars/increment2b/allocation-ownership/REPORT.md).
2B and subsequent increments remain blocked; product unchanged, no active run.

### Authorized forensic retaining paths completed — 2026-10-26

Four fixed captures at 6568ac8 completed. Current slot 2's 43 documents at navigation
20 fell to two before forced-GC capture. Graphs identify the live HTML document and
isolated SVG-image document, not the earlier transient owners. Exact-hash recovery
of one late telemetry response preserves sealed natural observations; raw failure
and artifact remain archived. Future writer freezes rows. 86 source/probe hashes,
40 files and 80 natural observations verify; 139 selected tests pass. See
[report](avatars/increment2b/retaining-paths/REPORT.md). Forensic GC exception does
not alter acceptance. Product unchanged, 2B/later blocked, no active run.

### Shared stylesheet candidate — 2026-10-27 — visual gate unresolved

Candidate 6960562 extracts byte-identical CSS. Nine browser regressions and strict
HTTP body reuse pass. Visual comparison fails exact pixels, including same-source
controls; software rendering and same-document restoration do not resolve it.
All diagnostics retained in [report](avatars/increment2b/shared-stylesheet/REPORT.md).
34 focused tests pass. Prepared memory screen enforces the visual prerequisite;
no memory run, promotion, 2B acceptance or later increment. Primary unchanged.

### Visual fixture resolved; fixed memory screen failed — 2026-10-27

[Visual evidence](avatars/increment2b/shared-stylesheet/visual-resolution/REPORT.md):
shared-layer painting varies despite unchanged DOM/styles/geometry; isolated
fixture painting plus nonmutating caret capture passes 30 sheets/2,880 cells.
Forty focused tests and one dedicated browser regression pass. Product unchanged.
[Fixed screen](avatars/increment2b/shared-stylesheet/memory-screen/REPORT.md), harness
b521760: all eight workloads complete, 114 source hashes/20 files verified, 104
comparisons independently recomputed. Reverse navigation 20 +12.863281 MiB and
both unstable repeat controls block qualification. Candidate 6960562 preserved;
no promotion, larger validation, 2B acceptance or later increments. No active run.

### Targeted native allocator correlation — 2026-10-27 — inconclusive

[Full report](avatars/increment2b/navigation-residency/REPORT.md): v1 trace-loss
attempt preserved; all eight v2 slots ran from bbcba53, seven valid and one trace-
loss failure. 164 source hashes/67 files verified, 140 allocator dumps retained,
38 focused tests pass. Probe overhead and missing memory maps limit attribution;
no reproduction of prior 52MiB anonymous release or validated product correction.
No waiver, replacement sample, 2B acceptance or later increment. No active run.

### Deferred trace transfer — 2026-10-27 — control stability still blocks comparison

[Latest report](avatars/increment2b/navigation-residency-v5/REPORT.md): three fixed
four-slot calibrations preserved. V3/v4 fail pause gates; v5 (`08daa22`) defers
trace I/O beyond sealed navigation and both traced runs pass integrity/pause checks.
V5 controls vary 16.757/8.474 seconds, failing the unchanged 20% duration gate.
116 source/probe hashes and 30 files verify; extracted archive audit identical;
53 focused tests pass. No source comparison, replacement, waiver or product fix.
Next evidence gap is scheduling/throttling attribution for the early control stall.
2B and later increments remain blocked; no measurement active.

### Navigation scheduling evidence — 2026-10-27 — control gate still fails

[V6 report](avatars/increment2b/navigation-residency-v6/REPORT.md), `75c6e85`:
all four fixed workloads complete; 120 source/probe hashes and 30 files verify;
archive re-audit identical; 65 focused tests pass. All trace/pause/reader CPU gates
pass, but control duration differs 21.62% (>20%), preventing source comparison.
No recorded cgroup throttling; extra Page.goto time accompanies additional Python
and renderer CPU execution, with smaller queue-delay changes. Function-level and
execution-rate cause remains open. No rerun, exclusion, waiver or product change;
2B/later remain blocked. No measurement active.

### Python/Chromium CPU attribution — 2026-10-27 — complete diagnostic, no acceptance

[Report](avatars/increment2b/navigation-cpu-v2/REPORT.md), `bcbf0b4`: four fixed
workloads complete, V8 samples cover all 20 navigations, 124 source/probe hashes
and 32 files verify, archive audit identical, 83 tests pass. Partial v1 preserved.
SQLite connection setup is ~89% of execute CPU; fixed per-PRAGMA probe shows deleting
journal_mode shifts cost to synchronous. Connection reuse with explicit thread/
transaction safety is the next concrete candidate; not implemented. Native browser
style/paint dominates recorded categories. Intrusive profiling fails timing gates;
no source comparison, product fix, memory waiver or acceptance. No measurement active.
