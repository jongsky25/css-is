# Shared stylesheet candidate — visual gate unresolved

Candidate `69605628393d044f9a0426ea0be3abdf99527bc3` on
`codex/avatar-shared-stylesheet` extracts the existing 15,883-byte avatar CSS into
`static/css/avatars.css`, linked at `/static/css/avatars.css?v=1`. Replacing the
link with the extracted style reconstructs f700187's template byte-for-byte.
No artwork, CSS rules or runtime changes. This tests an allocation-reduction
hypothesis, not an established cause of the memory regression.

Nine existing browser regressions pass. The additional real HTTP check passes:
first load transfers the compressed CSS body; subsequent Wellness/Home visits
revalidate without transferring the body (encoded/decoded body sizes zero).
No service-worker/offline claim. The strict body-size assertion was corrected
and rerun; the earlier wrong-checkout setup failure is preserved.

## Visual investigation

All completed comparisons use Chromium 156.0.8078.47 and thirty sheets, each with
96 cells: three backgrounds, five outfits, live and static-preview markup.
CSSOM rules match exactly in every completed comparison. Exact pixels do not:

| Experiment | Nonidentical sheets / 30 |
| --- | ---: |
| Initial completed current/candidate comparison | 3 |
| Awaited animation readiness and two rendering frames | 6 |
| Same unchanged source in both fresh contexts | 6 |
| Software rendering (`--disable-gpu`) | 3 |

Differences are in preview sheets. Consecutive screenshots in the same document
match, but fresh contexts and stylesheet reinsertion can differ. The unchanged
control establishes fixture/rendering variability; it does not prove the candidate
has no visual regression or identify the precise renderer cause. No tolerance
was introduced to turn these failures into passes.

Follow-up same-document swaps preserve forward and restoration screenshots when
restoration fails. Even with animation freezing and continuous stylesheet coverage,
the reverse restoration failed before completing the full matrix. The first
forward diagnostic image was pixel-identical; that single sheet is not acceptance.
The final fixture also adds UTF-8 metadata after inspection found mojibake in live
button labels. Earlier runs remain archived, including missing-helper setup failure.
Earlier evolving fixture source versions were not independently frozen; the archive
contains their logs/results and the final diagnostic implementation, not a claim
of exact source provenance for each preliminary run.

## Gate and next step

**No memory screen was run. No candidate promotion or 2B acceptance.** Primary
product remains f700187. The eight-workload screen and independent auditor are
prepared under [PROTOCOL.md](PROTOCOL.md); a failing visual assessment now stops
the runner before worktrees or browser collection. All 34 focused accounting and
gate tests pass. Candidate changes remain isolated on their branch.

Next: identify the preview rasterization variation with captured DOM/computed-style
and geometry comparisons, then establish a repeatable visual comparison. Keep the
current failures. Only after that gate passes, run the fixed current/candidate/
candidate/current screen, and advance to full validation only if its controls and
both orders qualify. Do not restart 3A or later increments yet.

`evidence.zip` retains all local functional outputs, visual images, failed logs,
and final harness sources; `manifest.json` records every member hash and archive
hash. Archive extraction/hash verification is recorded in `archive-audit.json`.
