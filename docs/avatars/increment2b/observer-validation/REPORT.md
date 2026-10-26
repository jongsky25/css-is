# Exact observer validation and preview timeout diagnosis

Product remains f700187. 2B is unaccepted; 3A and later increments remain paused.

## Observer experiment

[Hosted run 40323560666](https://github.com/jongsky25/css-is/actions/runs/40323560666)
uses source b374358: current / observer-disabled / observer-disabled / current,
five complete samples in each cohort. The intervention is exactly
`if (false && window.ResizeObserver)`, matching the previous source screen.
All other product sources remain f700187. Full 30-second warm-desktop workloads,
Chromium 156.0.8078.47, no concurrent instrumentation or local analysis on the
measurement host. No replacement samples. Status: running, not acceptance.

The predeclared criterion remains at least 5 MiB RSS improvement at both navigation
10 and 20 in both orders, with no checkpoint RSS/heap worsening above 10 MiB.
Every sample and source identity must validate. Passing this isolation experiment
would justify further investigation of observer ownership, not product promotion.

## Preview diagnosis

The opt-in `tests/test_avatar_preview_diagnostic.py` uses the real HTTP fixture,
Chromium 156, the desktop viewport and the same four outfit selections. The
normal unmodified layout passes all four selections. Moving the preview panel
10,000 px below the viewport deliberately exercises lazy-loading deferral:
all four updates time out after 30 seconds, with the iframe retaining its previous
URL/outfit. Scrolling it into view completes each update. No page errors.
Raw frame bounds, src, current document URL, ready state and outfits are retained
in `unchanged/preview-loading.json`.

A routed diagnostic script sets `frame.loading='eager'` when updating its src.
All eight normal/displaced cases then complete without scrolling or timeout.
The exact proposed script patch is retained, but is NOT applied to product or
the measurement fixture. Routing changes caching and these are functional
checks only, never memory evidence. Initial iframe loading remains lazy.

This confirms a reproducible lazy-loading failure mode and a candidate correction.
It does NOT prove the cause of the historical hosted timeout: the failed run did
not preserve iframe state, and its normal layout could differ during loading.
Do not relabel that incomplete cohort as valid or substitute diagnostic samples.

## Container-only resize check

The three existing geometry browser checks pass with observers disabled. Their
combined resize/scroll test does not isolate container-only resizing: scrolling
also invalidates the cache. A new real keyboard-input regression grows the play
container by 150 px, with no window resize or scroll, then moves the avatar down.
Current product reaches 394.797 px in the 395 px container. The exact disabled
observer intervention stops at 244.797 px, 150 px short. Scroll stays at zero in
both runs. The check passes on current and fails on the diagnostic intervention;
raw logs and measured bounds are retained in `resize-behavior/`.

Observer removal therefore cannot be promoted unchanged even if memory improves.
Any correction must pass this new behavior check as well as the existing gates.

## Separate preview correction

Candidate `794c796` on `codex/avatar-preview-loading` implements eager loading on
preview edits and bumps the script cache version. Both real HTTP regressions fail
on old code and pass on the candidate; all 24 selected appearance checks pass.
See that branch's `docs/avatars/increment2b/preview-loading-fix/REPORT.md` for logs,
including the retained initial run with an incorrect scheduling-test clock.
The candidate is not part of the running comparison and is not promoted to this
branch. Its behavior checks are not memory acceptance.
