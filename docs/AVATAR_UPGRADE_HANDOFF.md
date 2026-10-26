# Avatar upgrade: new-chat handoff

Last updated: **2026-10-26 12:20 UTC**. Repository: `jongsky25/css-is`.

## Current blocking correction

The 2B acceptance in `f46d7af` was withdrawn: the comparison/audit omitted
memory budgets for offscreen, reduced-motion, background and repeated navigation.
Final run 40263865865 warm-desktop RSS deltas are +11.335938, +11.097656 and
+18.835938 MiB for the three omitted scenarios (10 MiB limit). Renderer counts
match. Prior targeted candidate evidence also contains unreported reverse-order
background +26.171875 MiB and seasonal-preview +12.710938 MiB. No memory waiver.
Read the corrected `docs/avatars/increment2b/REPORT.md` before other instructions.
Checker correction `a3717e8` enforces all eight scenarios plus five navigation
checkpoints: 104 memory comparisons, eleven RSS failures, no invalid cohorts.
All 27 focused checker tests pass. Recompute with `memory_audit.py`; the complete
numeric/visual archive and corrected assessments are under `final-verification/`.
`native-memory-breakdown.json` records retained smaps/DOM/heap comparisons without
rerunning workloads. Native private and shared measurements differ; a cause or
product fix has not been established. Do not equate low JS heap with an RSS pass.

3A artwork/correction is preserved on `codex/avatar-3a` (product `cb2220f`).
The preserved 3A branch is `9abc5ec` after receiving the complete memory checker.
The source run 40280615190 was cancelled by pause commit `2b6d154` after the
2B prerequisite failure was discovered. Do not restart/accept 3A until 2B is fixed.
The prepared audit branch `codex/avatar-3a-artifact-audit` is explicitly paused at `ade949e`; do not
trigger it as an acceptance audit of the cancelled cohort. No later increments,
merge to main or deployment occurred. The historical handoff below is superseded by this
correction wherever it suggests CI success establishes complete memory acceptance.

## Exact observer validation complete — proceed to SVG validation

[Run 40323560666](https://github.com/jongsky25/css-is/actions/runs/40323560666)
completed all 20 samples with 112 verified source hashes. The exact observer-disable
intervention does not qualify: forward navigation 10/20 improve by 20.273/19.340
MiB, but reverse navigation 10/20 worsen by 25.555/20.094 MiB, with six RSS failures.
The unchanged-current repeat passes. No sample exclusions or budget waivers.
See [the retained audit](avatars/increment2b/observer-validation/REPORT.md).
The workflow is paused; do not rerun this unchanged intervention or subdivide its
registrations based on the earlier two-sample lead. Exact SVG validation is now running as
[40327763515](https://github.com/jongsky25/css-is/actions/runs/40327763515), source
`7c9f711`, five samples in current/SVG/SVG/current order. Do not start a duplicate. The runner/auditor support
`--validation-arm svg`; this is diagnostic artwork rollback, never a product fix.

A new container-only resize test passes current and fails observer removal by
150 px. Include it in any eventual geometry correction gate. Separately, preview
candidate `794c796` on `codex/avatar-preview-loading` passes 24 functional checks
(two regressions fail on old code); it remains separate from all memory cohorts.
The historical preview timeout cause is still unproven. Product stays f700187;
2B and every later increment remain blocked.

## Latest source screen and geometry candidate — not promoted

Read [source isolation](avatars/increment2b/source-isolation/REPORT.md) and
[the final geometry report](avatars/increment2b/geometry-lifecycle/REPORT.md).
All 16 local screening samples and both orders completed; geometry-observer
removal and original SVG qualified as leads, preview wrapper restoration did not.
Candidate cccf843 shares observation and disconnects it on discarded navigation.
Nine browser checks and 44 accounting checks pass, with artwork unchanged.

Hosted run 40315985656 did not pass. Its complete forward candidate/original pair
fails six RSS budgets, reaching +49.984 MiB against 10 MiB. The reverse candidate
pair passes, but the reverse unchanged-current control timed out at the seasonal
preview and completed only two samples. The overall independent audit is
inconclusive: 106 source hashes and 156 valid comparisons, one invalid cohort.
All 27 completed samples and the failure log are retained. No replacement samples.

Candidate branch `codex/avatar-2b-geometry-lifecycle` preserves the experiment and
is paused. The primary verification branch retains f700187 product plus evidence.
Full acceptance, 3A and later increments remain paused. Before another product
correction, validate the exact isolated observer/SVG intervention with five
samples in both orders; the two-sample screen alone was insufficient. Investigate
the current-control preview timeout separately. Do not promote the geometry
candidate, roll back the artwork, waive budgets, or rerun for a favourable sample.

## Native residency implementation — 2026-10-26

The combined collection/allocator probe and isolated runner are implemented and
validated across four original/current/current/original workloads. Read
[the residency report](avatars/increment2b/residency-attribution/REPORT.md) and
[usage](avatars/increment2b/residency-attribution/README.md). All 52 dumps match
unambiguously by checkpoint clock intervals; exported trace IDs differ from CDP
GUIDs. Disjoint dump fragments are joined, overlapping/ambiguous data rejected.
48 analysis/accounting tests pass. Natural collection leaves heap capacity well
above allocated-object totals in both sources, but no repeatable source-level
cause or validated product correction is established. Product f700187 is unchanged;
2B and subsequent increments remain blocked. No acceptance rerun was launched.

## Natural-collection attribution follow-up — 2026-10-26

The requested next experiment is complete. Read
[the collection report](avatars/increment2b/collection-attribution/REPORT.md).
Eight full instrumented workloads retain both orders, 104 native profiles and
C++/V8 collection traces. The initial trace lacked `cppgc`; its corrected repeat
is retained separately. Collection is natural (all explicit forced flags false).
The delta is mainly in the app renderer. Documents are reclaimed, but RSS can
remain elevated with fewer documents, so a persistent app reference is not
established. No new product fix or acceptance claim. Product remains f700187;
2B/3A status is unchanged. Next attribution question: live native allocations
versus allocator-resident capacity after natural sweep completion. Preserve all
measurements and the unchanged 10 MiB total-RSS/heap gates.

## Latest 2B investigation — candidate rejected, 2026-10-26

Read [the follow-up report](avatars/increment2b/lifecycle-memory-fix/REPORT.md).
Unchanged-source run 40287821303 retained 20 full warm-desktop samples and still
fails reverse-order seasonal-preview RSS (+10.797 MiB). Candidate 509cd1a on
`codex/avatar-2b-lifecycle-candidate` cancels owned animation effects on discarded
pages. Its behavior check passes, but run 40292908517 (30 samples, three sources,
both orders) fails both candidate memory gates: eight RSS failures up to +28.738
MiB, plus a JS-heap failure +10.063 MiB. It also worsens three reverse-order RSS
checks against unchanged current. The independent audit verifies 134 source
hashes and 234 comparisons without validity errors. **Do not promote it.**

The candidate branch preserves the rejected product and has its targeted workflow
paused. The primary verification branch retains product f700187, with diagnostic
evidence and audit tools. Full acceptance was not run after the failed targeted
gate. All raw numeric evidence is preserved in the report's two hosted ZIPs and
three native-probe ZIPs. Native allocation probes are instrumented diagnostics;
early exploratory probes overlapped trace parsing and cannot establish causality.

The next experiment must correlate natural Blink/V8 collection, navigation,
renderer roles/PIDs and native allocation stacks on original/current source in
both orders. Matching native debug symbols are now verified and reproducible;
see `native-sampling/assessment.json` and `symbolize_native_memory.py`. Do not
force GC, flush additional caches, subtract browser-UI/shared memory from RSS,
or choose favourable samples. Do not rerun the rejected candidate without a new
hypothesis. 2B remains unaccepted; 3A and later increments remain paused.

## Historical start here

Read this file, repository instructions, then [the execution plan](AVATAR_VISUAL_UPGRADE_PLAN.md).
Continue the already authorized work one increment at a time. First finish the
2B artifact audit and acceptance documentation; then execute 3A, 3B, 4A, 4B, 5,
and 6 in order, validating and updating the execution ledger after each.
Do not start over, repeat successful benchmarks without cause, or waive budgets.
Do not deploy or merge without separate authorization. Do not spawn agents unless
the user explicitly requests delegation. Keep the user informed during long runs.

Suggested new-chat prompt:

> Continue the avatar upgrade in jongsky25/css-is. Read
> docs/AVATAR_UPGRADE_HANDOFF.md and docs/AVATAR_VISUAL_UPGRADE_PLAN.md.
> Finish the pending 2B artifact audit and update acceptance/ledger, then execute
> all remaining increments sequentially with their visual and performance gates.
> Preserve prior evidence and failures. Prepare reviewable changes; do not deploy.

## Current result: final CI passed; evidence audit pending

The final full CI run **40263865865** completed successfully. This was checked
directly through its job API at the timestamp above; it is no longer running.

- [Final run](https://github.com/jongsky25/css-is/actions/runs/40263865865)
- Job: `121381866232`, conclusion `success`.
- Source: `e909de12c42fe8fe99ce58d922bbef71c711e574`.
- Functional/visual, focused artwork/native frame, complete original/current
  runtime, and full original/current application matrix: **all passed**.
- Evidence upload and job cleanup: also passed.
- Source artifact: `avatar-2b-complete`, ID **12629865325**, 167,820,720 bytes.
- SHA-256: `b3bcfbf6146afdf38e4ab7f1ee872ac77c4ad063d2cb0fbcf2f5c36a70bee1f4`.
- Source artifact expires **2026-11-02 05:23:02 UTC**. Preserve it promptly through
  the prepared audit workflow, which retains full evidence for 30 days.

**Do not equate this CI success with a completed manual evidence audit.** Raw
results still need checking and the final report/assessment/ledger need updating.
Their older “running” and “pending final verification” descriptions are stale.
In particular, the root assessment mixes historical Chromium 154 measurements
with later candidates; preserve historical records, then rewrite its current
status clearly rather than treating those old numbers as this run's results.

## Repository and portable state

- Main checkout: `/workspace/css-is`, local branch `work`.
- Product fix: `f700187553bd555dd3a9b638d5aa8e5fb59f3142`.
- Final harness source: `e909de12c42fe8fe99ce58d922bbef71c711e574`.
- Before this handoff, local HEAD was `46a8994b5d497d9ceb91613dbeba57c89f0217ca`;
  latest remote verification branch push was `7cacf19`.
- Remote working branch: `codex/avatar-2b-verification`.
- Audit checkout: `/workspace/avatar-2b-artifact-audit`, branch
  `codex/avatar-2b-artifact-audit`, HEAD
  `679eb18dd70d2e0da6a1b46a480d9a680b17932a`.
- Audit checkout has two intentional uncommitted files: its workflow and
  `scripts/avatar_baseline/package_review.py`. They target the final run and add
  a 30-day upload of the complete raw evidence.
- Their exact portable diff is saved in
  [final-artifact-audit.patch](avatars/increment2b/handoff/final-artifact-audit.patch).
  If the workspace is lost, fetch the audit branch at the stated base and apply
  this patch. If the edits already exist, do not apply it twice.
- Ignored local checkpoint `avatar-verification/SESSION_STATE.json` is older than
  this handoff. It still says the matrix is running; this document supersedes it.
- No local benchmark process needs resuming. The final remote run is completed.

## Finish 2B: exact next actions

1. Refresh final run status/artifact metadata and retrieve completed job logs.
   Confirm the source/artifact identity above. Do not rerun successful CI merely
   to obtain logs or a different measurement.
2. Inspect the prepared audit changes. Commit them in the audit checkout, then
   push the audit branch **from the primary checkout** (credentials previously
   worked there but failed when pushing from the audit checkout):

   ```sh
   git -C /workspace/avatar-2b-artifact-audit add .github/workflows/avatar-2b-artifact-audit.yml scripts/avatar_baseline/package_review.py
   git -C /workspace/avatar-2b-artifact-audit commit -m "test: audit final avatar 2B evidence and preserve raw traces"
   git -C /workspace/css-is push origin codex/avatar-2b-artifact-audit:refs/heads/codex/avatar-2b-artifact-audit
   ```

3. Locate the new audit run, wait for completion, and inspect its result. It runs
   `assess_complete.py`, packages all JSON/XML/text/PNG evidence with trace hashes,
   and uploads `avatar-2b-reviewed-evidence` plus
   `avatar-2b-full-reviewed-evidence`. If it fails, diagnose the actual failure.
4. Download the compact reviewed artifact through the GitHub tool, then use its
   Sediment file ID with `download_file`. Extract the ZIP and enclosed tar.gz.
   The complete source ZIP is about 168 MB and exceeds the 32 MiB download tool
   limit; the compact review archive is designed to remain below 25 MiB.
5. Audit the evidence, not merely the workflow badge:
   - Source commit, product file hashes, browser version and cohort completeness.
   - All four phase assessments, original/current controls, raw samples, and
     unchanged limits: callbacks 50 ms; frame p95 33.3 ms; memory growth 10 MiB.
   - All desktop/mobile and cold/warm memory medians; recompute deltas from raw
     data as needed. Renderer process counts must be positive and comparable.
   - 51 static PNGs, 4,896 cells, passing same-paint-mode comparison; check PNG
     hashes against `preview_sha256` and reference hashes/report.
   - No new JS errors or external requests, functional/seasonal behavior intact.
   - Manifest hashes match retained files; preserve the complete raw artifact link.
6. Save compact final evidence under
   `docs/avatars/increment2b/final-verification/`. Preserve earlier failures and
   reports before replacing current summaries.
7. Update `docs/avatars/increment2b/REPORT.md`, its `assessment.json`, and the
   status/2B row/appendix of `docs/AVATAR_VISUAL_UPGRADE_PLAN.md`. Record actual
   final metrics, source commits, run/artifact links, retention, and limitations.
   Accept 2B only if this audit supports it. **Keep `release_ready: false`**:
   existing lifecycle findings belong to increment 5 and later work is unfinished.
8. Commit/push documentation with `[skip ci]` to the verification branch to avoid
   another full benchmark. Then proceed to 3A under the plan's normal gates.

## Diagnosis and fix already completed

The former product `c2f404fa5aa58abebbe0127bbb537b5592993ce5` passed all timing
gates in full run **40247047928** but failed warm desktop picker/growth renderer
RSS: **+11,743,232 bytes (11.199 MiB)** against the 10 MiB budget.

Opposite-order diagnostic **40257027634**, source `afcbaf9`, reproduced memory
growth at **+14.51953125 and +12.62890625 MiB**. Each comparison used five full
30-second samples per arm. Private memory also increased; this was not explained
solely by shared-page noise. There was no demonstrated accumulating preview leak.
Local runtime `will-change` removal and a native allocation probe were diagnostic,
not acceptance evidence; their inconclusive results were retained.

Fix `f700187` makes noninteractive previews genuinely static:

- `templates/_avatars.html`: optional `static_preview=false` macro parameter.
  Static rendering omits motion wrappers and invisible reaction groups while
  preserving body/costume art and seasonal attachment anchors.
- `templates/me.html` and `templates/_growth.html`: request static variants;
  the picker also drops an unused sway class.
- Interactive SVG output and runtime JavaScript remain unchanged.
- Actual profile elements: 2,053 → 1,827; diagnostic DOM count: 5,086 → 4,561.
- 1,032 SVG nodes removed per 96-preview sheet. The checker’s 1,033 fixture DOM
  delta also includes one reference-only style node; do not call it 1,033 SVG nodes.

Candidate matched-memory run **40260864049** passed both opposite-order comparisons:
**+8.55078125 and +8.28515625 MiB**, with the unchanged 10 MiB limit. All samples
used 30 seconds, all 16 selections, and the same three renderer processes.

Validation already done:

- 1,734 exact normalized interactive SVG comparisons passed.
- 4,896 static cells (16 species × 6 stages × 17 outfits/months × 3 surfaces)
  were pixel-identical **under the same uncomposited paint mode**.
- Removing compositor layers changes edge antialiasing compared with the original
  composited raster. Both initial differing images and controlled comparisons are
  preserved. Do not claim the original rasterized pixels were unchanged.
- Eight browser regressions, native visibility/touch/keyboard behavior, persisted
  care for the three plants, and seasonal live refresh passed.
- Seasonal updates preserve unsaved form state and costume/accessory anchors.
- Final CI passed all 17 harness checks and all four full verification phases.

## Harness history and measurement rules

- Superseded run **40263432618** (`b1079aa`) was cancelled after finding an old
  macro/new caller API mismatch. `e909de1` fixes it by loading historical callers
  with historical macros: `_avatars.html`, `_avatars_art.html`, `_growth.html`,
  and `me.html`. Historical code is not modernized to fit the current API.
- Dedicated verification workflow uses `cancel-in-progress: true`. Do not push
  unrelated non-skip commits while relying on an active verification run.
- Browser: **Chromium 156.0.8078.47**, Debian package
  `156.0.8078.47-1~deb13u1` for Chromium and common. Earlier 154 packages became
  unavailable; all current acceptance deltas use fresh matched 156 cohorts.
- Container: `python:3.12-trixie@sha256:0d0db5b17f11b1b7d1aafa74ceadaa64ba0944b267ff6fc22008a197acd6b9ad`.
- Do not combine historical 154 failures with current 156 samples. Native throttle
  probing did not authorize subtracting scheduler pauses or rewriting timings.
- The only approved frame exception is **33 → 33.3 ms**. There is no memory or
  callback waiver. No GC/cache flushing, outlier hiding, or budget relaxation.
- Current runtime SHA-256:
  `c69e444b8d72fe84d0521d6ccabce07e9463209f5e451d96169b19aaca4191fb`.

## Evidence map

- `docs/avatars/increment2b/static-preview-fix/`: local functional/visual evidence,
  SVG equivalence, original and controlled compositing comparisons, seasonal
  checks, ~27 MB local evidence tarball, targeted hosted-memory ZIP/summary.
- `docs/avatars/increment2b/memory-diagnosis/`: reproduced original failure,
  local compositor hint tests, native allocation probe and raw diagnostic records.
- `docs/avatars/increment2b/hosted-complete/`: earlier complete run’s audited
  results; its memory failure is historical, not the final run’s result.
- `docs/avatars/increment2b/verification-repair/`: previous setup/harness history.
- Candidate memory artifact `12624908294`, SHA-256
  `aca84a2071edfbfb68edfa84b56bceda8fbe4802b95bb6bb9ae54cf76024a685`.
- Prior memory diagnosis artifact `12624200637`, SHA-256
  `ad964a49b82afca427b18ed61ba8896a444edc32ea37842791ad717422072c60`.
- Local extracted evidence (workspace-specific): `/workspace/avatar-static-memory-reviewed`,
  `/workspace/avatar-memory-reviewed`, `/workspace/avatar-hosted-review`,
  `/workspace/avatar-hosted-images`. Prefer committed evidence for portability.

## Tool and environment notes

Discover current connector tools rather than assuming their names never change.
Previously available GitHub tools were `github_fetch_workflow_run_jobs`,
`github_fetch_workflow_job_logs`, `github_fetch_workflow_run_artifacts`, and
`github_download_workflow_artifact`, prefixed `mcp__codex_apps__` through `tools`.
They take `repo_full_name: "jongsky25/css-is"` and the relevant run/job/artifact ID.
Completed job logs are available; a 404 while a job was active was not proof of a
failed run. Do not print signed artifact URLs or credentials.

**The commit-workflow-runs tool filters to PR-triggered runs.** Empty results do
not mean a push-triggered run is missing. Discover push runs through the public
Actions page, then query run/job IDs directly:

```text
https://github.com/jongsky25/css-is/actions?query=branch%3Acodex%2Favatar-2b-artifact-audit
```

Its JSON script payload contains `payload.allWorkflowRunsRoute.workflowRuns`.
Direct CLI `api.github.com` access was blocked by the environment; use the
connector/public Actions page without changing or bypassing network policy.

If local Docker is needed, clear conflicting Docker selectors and explicitly use
`--host=unix:///var/run/docker.sock`. Existing local image `avatar-ci-preflight`
has locked dependencies/Chromium 156; host venv/browser differ and are unsuitable
for mixing acceptance metrics. Read applicable environment instructions/skills.

## Remaining plan after 2B acceptance

The execution plan remains authoritative for all detailed deliverables and gates.

| Order | Work | Essential acceptance |
|---|---|---|
| 3A | Dog, rabbit, bird, turtle; six stages each | Recognizable growth, seasonal fit, mood/care checks, small and hero sheets, performance gates |
| 3B | Fish, dolphin, owl, bat; six stages each | Preserve swimmer water separation, owl tracking and characteristic motion; same visual/performance gates |
| 4A | Wardrobe catalog, rendering, persisted preferences | Compatible stable IDs, at most two items, server validation, additive storage; seasonal/personal/none precedence |
| 4B | Accessible profile customization and integration | Explicit save/cancel, no writes during preview, keyboard support, cross-surface consistency, seasonal updates and species switching |
| 5 | Expressive motion and lifecycle policy | Hidden/offscreen/reduced-motion handling for CSS and JS; cleanup, bounded timers/listeners; before/after recordings |
| 6 | Complete regression, polish and release readiness | All combinations/surfaces, integration/accessibility/performance evidence, licenses/cache/rollback/changelog; no deployment without authorization |

Increments 0, 1 and 2A are complete. Existing offscreen motion, timer/listener and
remount findings remain visible until increment 5 resolves and measures them.
Preserve growth, wellness, identity, care cooldowns, sound preferences, seasonal
administration and accessibility. No new framework, remote art dependency, paid
service or live inference. Use original authored/coherent vector art or properly
licensed pinned assets with a manifest. Review the concrete visual results after
each bounded batch; passing source inspections alone is insufficient.
