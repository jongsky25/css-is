# Increment 0 execution — 2026-10-25

Status: **in progress; acceptance not met**. Do not begin increment 1 yet.
Production code, art, CSS and behavior are unchanged. No deployment performed.

## Evidence collected

- Strict-Jinja sweep: all 16 species × six stages × three moods, all five
  explicit costume modes, plus Home and picker fixtures rendered successfully.
- 100 relevant tests passed: care, audio, onboarding storage, appearance policy,
  and real application appearance browser integration. Existing Starlette/httpx
  deprecation warning only. Command is in README.md.
- `baseline/lifecycle.json`: Home has two active CSS animations both visible and
  offscreen; reduced motion removes them. The picker fixture has 30 animations
  visible and offscreen, zero under reduced motion. This fixture uses wrappers;
  actual SVG-only production picker behavior still needs separate measurement.
- Twenty same-document Home remounts increase document `pointermove` listeners
  from 2 to 22. Picker fixture remounts keep that count at 1. This confirms a
  cleanup issue in the current chase initialization, rather than only a source
  suspicion. No production fix belongs in this baseline-only increment.
- `smoke/`: fixed-noon light/dark contact sheets for bare, July monthly,
  Halloween witch/vampire/pumpkin and Christmas. All 288 cells are intentionally
  included per sheet. `smoke/raw.json` and `summary.json` contain five short
  exploratory samples for each viewport/cache configuration. **One-second
  scenarios are smoke checks, not the required 30-second performance baseline.**

## Remaining acceptance work

The first full-duration sweep was stopped after discovering fixture gaps; it
must not be presented as a passing baseline. The checked-in short sweep exercises
measurement plumbing only. Re-run full duration after these gaps are corrected:

1. Route a synthetic authenticated Home, profile picker, growth, and administrator
   preview through the real application; include valid care writes and selecting
   each species. Add preview and scrolling scenarios rather than infer from Home.
2. Record actual transfer encoding, cold/warm HTTP cache behavior, and resource
   bytes. Current gzip estimates are useful size comparisons, not network evidence.
3. Seed idle randomness and keep the noon clock across screenshots and scenarios;
   screenshots now use explicit UTC/noon. Pin the executable version for subsequent
   comparisons. Initial screenshots followed machine bedtime and were discarded.
4. Capture actual hidden-tab work, retained timer counts and renderer memory;
   JS heap alone and listener counts cannot prove all lifecycle/memory budgets.
5. Run all scenarios for 30 seconds, five times, with no competing browser probes;
   report medians/worst LCP and interaction latency, p95 frames, attributed long
   tasks, memory and post-navigation trends. Validate touch and reduced motion.
6. Review complete sheets, including high contrast and every monthly outfit.
   Initial viewport inspection verified the gallery frame and early plant stages;
   this does not constitute catalog-wide visual approval.

The release gate remains unassessed. Known baseline issues are recorded without
relaxing thresholds. See README.md for commands, inventory and measurement limits.
