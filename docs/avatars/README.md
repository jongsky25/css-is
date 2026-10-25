# Avatar baseline harness (increment 0)

This development-only HTTP server imports the actual `_avatars.html` and
`_avatars_art.html` macros; it never imports the application, opens a database,
adds a production route, or reads account data. Catalog entries come from the
literal `AVATAR_CATALOG` assignment in storage.py. Template helper semantics are
mirrored locally; integration tests remain necessary to detect helper drift.

```sh
uv venv .venv
uv pip install --python .venv/bin/python -r requirements-test.in
.venv/bin/python scripts/avatar_baseline/gallery.py
# Separate terminal, repository root:
# Optional exploratory macro audit (not the authoritative application baseline):
.venv/bin/python scripts/avatar_baseline/audit.py
.venv/bin/python -m pytest tests/test_avatar_care.py tests/test_avatar_audio.py tests/test_onboarding_storage.py tests/test_appearance.py tests/test_appearance_browser.py -q
```

Open http://127.0.0.1:8765/ for 16 × 6 × 3 moods. Query parameters:
`theme=light|dark`, `scene=gallery|home|picker`, `month=0..12`, and
`outfit=default|halloween|halloween_vampire|halloween_pumpkin|christmas`.
Use `outfit=default&month=1` through `12` for monthly accessories.
The server binds only loopback. Do not expose it as a production service.

`baseline/` holds contact sheets, raw per-run measurements, aggregate medians and
worst runs, and lifecycle observations. All artifact names encode their surface
and costume. The gallery deliberately renders more than a normal user surface.
No assets were imported, so no upstream artwork license is introduced.

## Actual application baseline

The authoritative runner is `tests/test_avatar_baseline_browser.py`. It starts
Uvicorn over loopback with a copied synthetic test database, issues an ordinary
registered administrator session, and serves the unmodified application routes.
A test-local GZip ASGI wrapper models a controlled compression proxy. It does
not change production middleware or add a deployed route. App startup tasks are
disabled (`lifespan=off`), as in existing TestClient integration tests.

```sh
CSS_TEST_NOW=2026-07-15T12:00:00 CSS_AVATAR_BASELINE=1 \
  .venv/bin/python -m pytest tests/test_avatar_baseline_browser.py -s
.venv/bin/python scripts/avatar_baseline/summarize.py
# Run visual capture separately, with no timing sweep running:
.venv/bin/python scripts/avatar_baseline/sheets.py
```

The runner requires system Chromium `154.0.8037.57`; another session must install
that version or explicitly set `CSS_AVATAR_CHROMIUM` and establish a new baseline.
Playwright is pinned by requirements-test.in. Python, platform, source hashes,
clock and seed are recorded in `application/environment.json`.
Desktop: 1440 × 1000, CPU 1×. Mobile proxy: 390 × 844, CPU 4×, touch-capable
context. These are virtual fixtures, not physical-device results.

Each viewport/cache configuration has five independent browser contexts. Home idle
and trusted mouse input each run for at least 30 seconds. Cold clears HTTP cache;
warm primes Home in the same context. HTTP caching stays enabled: there is no
Playwright request routing, and service workers are blocked. Resource timings and
response encodings distinguish actual cache reuse from a priming navigation.
Browser Date is controlled without mocking Performance APIs. Math.random uses
seed 12345, and the server date is fixed via the repository's test clock.

The remaining checks select all 16 profile radios, scroll to growth, perform and
verify a persisted care write, cycle seasonal previews through the real admin
iframe, inspect offscreen/reduced-motion state and observe 20 real navigations.
Normal Home has no care button, so care is exercised on Wellness. There is no
wardrobe in the baseline application; that scenario starts when increment 4 adds it.

Raw samples retain long tasks and slow frames. Summary statistics report medians
and worst runs. Event Timing has a 16 ms reporting floor; a missing entry does
not mean zero latency. Long tasks are page-wide: attribution requires a separate
trace before assigning a regression to avatar code. JS heap and DOM/listener
counts are supplemented by summed OS renderer RSS. Shared resident pages may be
counted more than once; this is not private/PSS memory. Compare identical renderer
counts and scenarios rather than treating RSS as precise avatar-only memory.

Playwright's regular page initialization forces focused/active emulation, so the
main sweep records `hidden_verified=false` when another page fails to hide it.
A separate native-Chromium tab check connects with `no_defaults=True`, retaining
native page visibility. It records actual hidden state, frame callbacks and timer
activity, then exercises touch dragging and a keyboard nudge on Home. Do not
interpret the main sweep's failed background attempt as successful hidden testing.

`application/` is authoritative performance evidence. `sheets/` contains 64 px
six-stage sheets for all monthly and explicit seasonal outfits in light, dark
and white high-contrast backgrounds. The earlier `smoke/` hero sheets include
all three moods. `measure.py` and `audit.py` are retained as exploratory standalone
macro probes, not application performance acceptance tools. Their short samples
and gzip estimates must not replace the actual HTTP results.

## Inventory and update paths

- `_avatars_art.html`: 16-species dispatcher, six-stage art, monthly/seasonal
  accessories and costume back layer. `_avatars.html`: shared gradient IDs,
  CSS, `avatar_defs`, `avatar_svg`, `avatar`; loads avatars.js and avatar-audio.js.
- `office_connect.html`: Home hero with care/drag/chase. `wellness_hub.html`:
  selected companion and wellness growth. `me.html`, `welcome.html`: SVG pickers.
  `_growth.html`: growth ladder; `_faces.html`: shared companion faces;
  `admin_appearance.html`: appearance preview. Preserve all consumers.
- `app.py`: template avatar helpers, welcome/profile render/save, POST
  `/avatar/care`, wellness context. `storage.py`: catalog, family/swimmer rules,
  name validation, stage/ladder, mood/care cooldowns and profile persistence.
- `appearance.py`, `appearance_storage.py`, `appearance_routes.py`,
  `static/js/appearance.js`: resolve/persist seasonal policy, administrator
  previews and live costume updates; preserve unsaved form and companion state.
- `avatars.js`: delegated click/play/care/explore; document pointer tracking;
  per-wrapper pointer drag/petting and keyboard movement; localStorage position;
  idle/roam/gait/action/wake/bubble timers; chase/heart intervals;
  pointer requestAnimationFrame; MutationObserver initialization; reduced-motion
  change listener; five-minute sleep clock. CSS animates whole body and parts.
  Movement layer `.avmove` remains separate from `.avstage`; swimmer water is
  outside both. Audio has independent opt-in controls and visibility behavior.
- Tests: `test_avatar_care.py`, `test_avatar_audio.py`,
  `test_onboarding_storage.py`, `test_onboarding_flow.py`, `test_appearance.py`,
  `test_appearance_browser.py`; broader profile and browser security coverage
  under tests. Inventory command: `rg -n 'avatar|companion' templates app.py
  storage.py appearance*.py static/js/avatars.js static/js/appearance.js`.

## Existing issues to carry forward

Source audit finds no shared offscreen observer in avatars.js, recurring idle
scheduling even when reduced/hidden, and document-level chase pointer handlers
created for each draggable chase companion without an explicit detach path.
These are baseline concerns, not newly introduced regressions. Verify measured
lifecycle output before assigning severity; fix within the motion increment,
not by silently changing the baseline fixture's CSS or JS.
