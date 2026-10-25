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
.venv/bin/python scripts/avatar_baseline/measure.py --runs 5 --seconds 30
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

## Measurement interpretation

Chromium uses the system executable; its exact version is recorded in raw.json.
Compare only identical versions, viewport, throttle, platform and harness revision.
Desktop: 1440 × 1000, CPU 1×. Mobile proxy: 390 × 844, CPU 4×.
No claim of physical-device results. Each sample uses a fresh browser context;
warm performs a priming navigation. The clock is fixed to noon July 15, 2026;
seasonal rendering is explicit. Audio remains off. Behavior randomness is currently
unseeded; timing samples therefore contain natural idle variation.

Home is a standalone macro fixture, **not full-application Home LCP**. Interaction
latency measures a requestAnimationFrame after scripted actions, not Event Timing
or input-to-paint latency. Long tasks include fixture/browser work and require
attribution before calling them avatar regressions. Heap deltas cover JS heap,
not total renderer memory, and navigation discards old documents; audit.py also
checks same-document remounts. No CSS/JS/art changes are made in this increment,
so no before/after regression or release performance pass can be inferred.

The harness currently does not provide an authenticated care backend (the local
POST returns 501), real picker selection controls, wardrobe (not implemented),
seasonal live-update controls, actual hidden-tab measurement, full renderer memory,
or transferred compressed HTTP sizes (gzip values are deterministic estimates of
uncompressed fixture bodies). These limits must be resolved before increment 0
is accepted and before increment 1 starts. The `--seconds` switch supports smoke
runs; anything below 30 seconds is **not** the required release baseline.

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
