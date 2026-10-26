# Avatar upgrade: new-chat handoff

Last verified: **2026-10-26; continuation in progress**. Repository: `jongsky25/css-is`.

## Current continuation

2B is **accepted** in commit `f46d7af` on `codex/avatar-2b-verification`.
Final raw artifact audit `40277957839` passed; full evidence is preserved through
November 25. See `docs/avatars/increment2b/REPORT.md` and `final-verification/`.
The historical handoff below is retained for provenance; its pending 2B actions
are completed and must not be repeated.

3A is implemented in `d0df55779e3fe18ba945029fd549d9079425e53d` on
`codex/avatar-3a` (current checkout). Local 103 unit/integration/harness checks,
4 real animal-care checks, 51 sheets, 216 rig cases and 2,448 unchanged-species
SVG comparisons pass. Its first hosted preflight failed a hardcoded-species harness assertion before benchmarks. The repaired harness `512df84` passes all 18 accounting checks, including both batch configurations. Run below is superseded during focused timing by the turtle retraction correction (the previous larger head stayed exposed). A new complete run is required on the correction; discover it from the branch Actions page:
https://github.com/jongsky25/css-is/actions/runs/40279416578
Job: `121429157804`. Do not push non-skip commits to this branch while relying
on that run. Audit the raw result before accepting 3A or starting 3B. The workflow uploads full `avatar-3a-complete` and compact `avatar-3a-review` artifacts for 30 days. Extract the compact archive and run `scripts/avatar_baseline/audit_batch.py <evidence> --kinds dog,rabbit,bird,turtle --output <assessment.json>`; inspect screenshots and retain all raw failures.

Current local dependencies: `/workspace/css-is/.venv`; local Chromium 154 is
for functional/visual checks only. The previous Docker preflight image is absent.
Full 2B evidence is extracted at `/workspace/avatar-final-review/evidence`.
All later increments remain sequentially gated. No merge or deployment.

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
