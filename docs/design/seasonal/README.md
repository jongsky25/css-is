# Seasonal design study — first build stage

Application integration now exists on the same branch. See
[the implementation handoff](../../SEASONAL_THEME_IMPLEMENTATION.md) for actual
behaviour, real-page screenshots, verification and remaining release checks.
The study below remains a separate simulated design artifact.

Branch: `feat/seasonal-theme-design`, separate worktree
`/workspace/office-connect-seasonal`, based on main `a7b9b38` (9.59).
The user requested starting the seasonal work while avoiding conflict with ongoing
Telegram work. This stage creates isolated visual/interaction mockups, not runtime
integration. The original planning branch is preserved.

Open [the standalone HTML study](index.html) in a browser after downloading it.
No build, server, account, application database, network assets or dependencies are
needed. Controls switch Christmas/New Year, Home/form, light/dark, artwork and
effects. Preview midnight runs a three-second countdown; reset restores sample time.
The countdown is explicitly simulated. Form submission only displays a local message.
The companion is illustrative; application integration must use existing avatars.

- [Christmas desktop screenshot](christmas-desktop.png)
- [New Year phone screenshot](newyear-phone.png)
- [Full build handoff](../../SEASONAL_THEME_BUILD_HANDOFF.md)

## Verification

Chromium/Playwright checked 32 combinations (320/390/768/1440 widths × two seasons ×
two colour modes × Home/form), without horizontal overflow. Sample title/details
survived theme, colour and artwork changes. Three-second midnight transition and
reset passed; no JavaScript page errors. Desktop Christmas and phone New Year
screenshots were visually inspected. Direct file navigation in the managed browser
was policy-blocked; verification rendered the exact HTML using `page.set_content`.
The standalone browser tooling used the image's installed Python/Playwright;
application Python setup and tests were not needed or run for this static study.

Remaining: final palette contrast validation, screen reader/keyboard review,
enlarged text, print, high contrast and no-script fallback; actual companion art,
server-time synchronization, target validation, midnight effects and configuration
compatibility are runtime implementation work. The prototype's mobile hero omits
the large illustration to keep work close; refine a compact parol detail during
integration. No runtime accessibility or full release gate pass is claimed.

## Telegram coexistence and merge procedure

Inspected open draft [PR #572](https://github.com/jongsky25/css-is/pull/572),
branch `feat/telegram-private-work-lookup`. Its description identifies candidate
9.75; actual main is 9.59. Do not allocate a competing release number now.
Fetched its branch and compared changed filenames against main. At this stage,
the only common changed file is `docs/SETUP_STATUS.md`; this branch adds one
separate status entry and does not replace Telegram history.

No application, Telegram, dependency, version, changelog, service-worker or shared
layout changes are included in this design stage. No preview is published or
reserved. No Telegram messages or PR comments are sent.

Before runtime work, refresh both branches and their changed-file lists. Keep new
seasonal assets/logic in dedicated files where practical and shared-layout edits
small. After either feature merges, update the other from main and run relevant
combined appearance/Telegram regressions plus the required release checks on the
final commit. Reconcile release metadata once the order is known. Coordinate the
shared private preview before publishing. Main is production-connected; this
request does not authorize merge or deployment.

Next: integrate the selected compositions into the existing appearance system,
starting with static assets/tokens, then theme configuration and synchronized
countdown. Continue the full scope and acceptance criteria in the build handoff.
