# Shared accessibility — A16 engineering slice (7.83)

## Delivered

- Shared muted text uses readable light/dark colors; Wellness buttons use the theme's foreground on the accent background. A solid focus outline complements the existing focus shadow.
- Survey N/A radios have 24 × 24 CSS-pixel controls with associated labels at least 44 pixels tall. Carousel dots/arrows and companion care/sound/explore controls have 44-pixel hit areas. CSS hub period/filter buttons have a 44-pixel minimum height.
- Growth-stage strips receive keyboard focus and native horizontal scrolling. Home task cards and the assistant link wrap with enlarged text.
- Carousels use a named group of ordinary view buttons, referenced slide IDs, a polite current-view announcement and inactive-slide isolation. Arrow/Home/End keys work on view buttons; text-field cursor keys retain their normal behavior. Resize keeps the selected view; reaching a disabled arrow transfers focus to the selected view button. Native scroll/tab access remains available without JavaScript.
- Companions expose separate native play, care, sound and optional explore buttons within a named group. Care/sound no longer sit inside a button-like wrapper; play responses have a polite live region. Keyboard care performs one care request.
- Search results expose one option on each real destination link, with presentation-only list wrappers. The same structure covers page, database, Ask and scoped-exit rows; mouse links and input Arrow/Enter behavior remain available. Search has an explicit close button and labeled input.
- The mobile drawer, search, feedback, tours and daily snapshots share focus containment, background `inert` isolation, Escape dismissal and return focus. Nested overlays restore the underlying dialog; pre-existing inert regions are preserved. Drawer closure on a desktop resize falls back to main content when its trigger is hidden. Native navigation/display-settings dropdowns close on Escape and restore their summary.
- Keyboard activation of Send feedback opens a whole-page feedback dialog; pointer activation retains spot selection. Error/status messages are live regions. Snapshot daily/opt-out persistence and tour replay/seen behavior remain in place.

The helper performs no network or form action. Browser regressions intercept writes and use synthetic local data. No production workflow or staff account was exercised for this release. No application or test dependency was added.

## Automated evidence and limits

`tests/test_shared_accessibility.py` runs real Chromium journeys in CI: desktop/light/dark dropdowns, 320/390-pixel drawers, nested search, keyboard/pointer/error feedback, tours, snapshots, growth-strip scrolling, 200% text resizing on Home, 720-pixel reflow, companion actions, carousel navigation/resize/native no-JavaScript scrolling, public settings, dynamic/scoped search and field-error recovery. Survey tests check rendered text contrast in light/dark/contrast themes, associated names and control geometry. Chromium's native accessibility tree verifies inactive slides are not exposed; this does **not** substitute for using a screen reader.

The explicit local axe runner covers Home, CSS hub, Wellness, Dashboard and a public survey, plus open navigation, search, feedback, tour, snapshot and real carousel/validation components: **44 states**, light/dark, 1440 × 1000 and 390 × 844. It uses the WCAG 2 A/AA, 2.1 A/AA and 2.2 AA tags. The final run found **zero automated violations** across those 44 states. Results and tool provenance are in [the evidence file](audits/2026-10-19/A16_AUTOMATED_EVIDENCE.json). It retains incomplete results for manual review. A clean scan is limited to these synthetic states and this engine/browser version.

The original local 16-state baseline included contrast failures in Home/Dashboard/survey, nested companion controls, a non-keyboard-scrollable growth strip and undersized survey radios. Adding open states exposed nested search options and undersized mobile CSS hub filters; both were repaired. Original audit F16 also supplies the multi-view carousel findings; the small reference Home dataset does not render multiple views, so regression tests render the real shared carousel macro explicitly.

### Reproduce local axe evidence

Install the pinned engine outside the repository and run the explicit file; it is excluded from ordinary test discovery and CI has no npm axe dependency:

```sh
npm install --prefix /tmp/a16-audit --ignore-scripts --no-audit --no-fund axe-core@4.14.0
A16_AXE_PATH=/tmp/a16-audit/node_modules/axe-core/axe.min.js \
A16_REPORT=/tmp/a16-report.json CSS_TEST_NOW=2026-10-20T06:00:00 \
python -m pytest -q tests/browser/a16_axe_probe.py
```

Use the locked test environment and installed Chromium (the browser fixture uses `/usr/bin/chromium` if present, otherwise Playwright's installed Chromium). The evidence records the engine file SHA-256 and Chromium version. Published npm package integrity for axe-core 4.14.0:

`sha512-9WTZxEjsZ7b13TH8JPmbV2z8CHbl80/2hm3XPEG4JgNdQLK81IBRXmSxHfMAOkSqQeRxT/0dwNDz2GOm3zzpcQ==`

## Remaining validation before the A16 pilot exit gate

1. Run a real screen-reader/browser session (for example NVDA with Chrome on Windows), with staff and respondent roles. Check names/order, drawer/search nesting, view announcements, companion actions, survey groups, field errors and error recovery. Record versions, tasks, assistance and failures.
2. Review each retained axe `incomplete` result. These include icon-only name comparisons, references to a hidden search dialog, and text overlaid by neighboring elements/focus rings where the engine could not determine contrast. Confirm actual rendered contrast and labels in those states; do not count incomplete checks as passes.
3. Check real browser zoom at 200% and 400%, forced colors, touch and a representative mobile browser across primary journeys. The automated 200% text resize and narrow CSS viewports cover useful reflow behavior, not every zoom/browser configuration or every page.
4. Observe agreed staff tasks, including errors and dialogs, before expanding to A17/A18. Permission-dependent content, real long labels/data, larger datasets, other accent choices and pages outside this sample need their own checks. No claim of full WCAG 2.2 AA certification is made.

## CI follow-up: concurrent cold-start initialization

The first CI revision passed all 4,811 tests in normal order. Its shuffled run passed 4,810 tests and hit `database is locked` during Gmail-review fixture session setup: the first `get_conn()` seeding path was entered while TestClient lifespan workers could also initialize the same fresh database. Account setup already commits its writes. The fixture now obtains its genuine registered session before starting lifespan workers, consistent with the other authentication fixtures; its assertions and production session checks are retained. Twenty related Gmail review/intake tests pass locally after that change.

This test setup ordering change does not repair or establish production cold-start concurrency safety. Reproduce concurrent first-use initialization and investigate serialization/atomic seeding under A25 before claiming that behavior is verified. No A16 production database/session behavior was changed to suppress the failure.

## Release and rollback

Review 7.83, run the existing required release/dependency/full-suite gates, then merge through the normal release workflow. The service-worker cache and every changed static asset reference are versioned together. Roll back by reverting this release's frontend/templates and publishing a new application/cache version through the same workflow; there is no database migration or durable data conversion.
