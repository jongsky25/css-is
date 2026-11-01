# Seasonal theme integration — November 1, 2026

Branch: `feat/seasonal-theme-design`, based on main `a7b9b38` (9.59), with an
isolated worktree at `/workspace/office-connect-seasonal`. Original planning branch
and interactive study are preserved. This is an implementation candidate, not a
release. No PR, merge or production deployment. The private preview is now live
as described below.

## Hosted preview — November 1, 2026

Owner explicitly requested preview publication. Before upload, remote metadata
showed the old collaboration preview (`f03125c2`) on private CPU Basic; Telegram's
current handoff explicitly deferred its preview/deployment. No Telegram candidate
was replaced. Published seasonal source
`5f6a18c2f5171dc17e6ee7462db2a8e77fe9ac64` to the existing fixed target:
[private preview](https://huggingface.co/spaces/equityinhealth/office-connect-preview).
Space commit `d5ed25c6bc88f4b7e194ca5c8ed8b463135b3071` is RUNNING, private, CPU Basic.
The remote `preview-build.json` matches the source commit. This publication replaces
the old disposable data; production was untouched and no hardware was upgraded.

Authenticated hosted observations: `/preview-health` 200 with exact readiness text;
`/login` 200 with PREVIEW banner, login form and `x-office-connect-environment:
preview`. Anonymous health/login requests both 404. Seasonal CSS, countdown JS and
both parol SVGs return 200. Code-only staging dry run passed (945 files). Isolated
preview bundle tests: 3 passed in 9.12s; JUnit gate passed without failures/skips.

The preview account password secret already existed remotely and was neither read
nor changed. It is not available in this process, so no hosted app sign-in or
signed-in hosted action is claimed. Local synthetic login/mobile/action checks
passed in the preview-bundle group; they are not hosted phone acceptance.

Phone review: open the Hub preview while signed into Hugging Face, then sign in
as `preview@example.invalid` with the saved preview password. Open Appearance,
choose Christmas, enable artwork and tap Update preview. Inspect the private
Home frame in light/dark; then choose New Year with target year 2027 and update
again. The preview selection does not publish. To inspect full-page work forms,
Publish now changes only this disposable preview instance; no production settings
are reachable through it. Check that an unsaved profile edit survives changing
the theme from a second tab. Report cramped text, awkward scrolling or missing art.
Midnight behaviour is locally clock-tested; no hosted clock override was installed.

This is the shared preview's current candidate. Serialize further publications;
recheck its manifest before collecting acceptance if another task has published.
Owner phone acceptance remains pending. See the existing iOS cookie guidance in
[preview setup](HF_PREVIEW_SETUP.md) if login does not persist.

## Implemented

### Richer festive revision

The owner requested more festive designs after opening the initial preview.
Christmas now has a fuller illustrated tree, hanging parols, ornaments, gifts,
city silhouettes, evergreen/ribbon garlands and warm lights. New Year has static
illustrated fireworks, a city skyline, a prominent configured year, gold/lilac
bunting and framed countdown tiles. Both have decorative Home ribbons, gold card
edges, a companion setting and a matching festive footer. Phone layouts now retain
150px of scene artwork rather than hiding it. Working-page greetings stay compact.
Sound is still deferred; fireworks are illustration, not flashing animation.
Artwork-off, reduced-motion, contrast and print controls remain in force.

- [Richer Christmas phone](design/seasonal/festive-christmas-phone.png)
- [Richer New Year desktop](design/seasonal/festive-newyear-desktop.png)

Initial focused appearance/seasonal/preview-bundle run: 19 passed. After the year
display, cache-key and mobile-visibility refinements, final seasonal group: 13
passed in 24.63s, zero failures/skips; JUnit gate passed. The latter includes all
32 enlarged-text layout combinations and checks artwork visibility on phones and
desktop. Christmas phone and New Year desktop screenshots were visually inspected.
SVG XML parsing, JavaScript syntax and diff checks passed. No dependencies added.
Before revision publication the shared preview still contained our original source
`5f6a18c`; Telegram's current handoff continued to defer preview publication.

- Coordinated Christmas and New Year palettes for light/dark appearance, parol scene
  artwork, a fuller Home greeting and compact greetings on working pages. Existing
  brand, personal companions and outfit preferences are retained. Companion stages
  receive a subtle gold setting; no new species or outfit identifier is introduced.
- New Year countdown on Home uses a server-supplied epoch and `performance.now()`,
  with the existing appearance refresh/focus flow for resynchronization. No
  per-second server requests. Configured target year remains fixed after midnight;
  the initial year is 2027, not a year inferred from the visitor's device clock.
- At midnight, a static greeting replaces the timer. One four-second bounded
  confetti effect is allowed only when visible, artwork/effects enabled, reduced
  motion off and no target-year session marker exists. No replay on opening after
  midnight or after tab suspension. No audio assets, prompts or playback.
- Artwork off retains the countdown and usable palette. Reduced motion stops
  animations; contrast mode keeps its established palette; print hides the scene.
  Without JavaScript, the target date remains readable and a server-rendered
  post-midnight greeting is available. No per-second live announcements.
- Theme-aware fallback copy, general admin labels and validated target year
  (2027–2100). New Year scheduled intervals must include January 1 midnight of the
  selected year in Asia/Manila. Old JSON settings gain a target-year default through
  normalization; no table migration. Explicit saved artwork/copy/outfit choices are
  retained. Clear an old saved Halloween greeting in a Christmas selection to use
  the new Christmas fallback; existing nonblank copy is not silently overwritten.

## How to review on an isolated instance

Use the existing `scripts/cloud_workspace.py` workflow. In Appearance, choose
Christmas or New Year, set artwork/effects independently, choose an outfit and
target year, then use the private preview. Check Home and an open profile form.
Saving drafts/previews must not publish; Publish now is an explicit instance change.
No live instance settings were changed during implementation.

The proposed Christmas → New Year dates in
[the build handoff](SEASONAL_THEME_BUILD_HANDOFF.md) remain an editable plan. No
events/defaults were automatically installed or published. Enter and review events
in Appearance when seasonal activation is actually wanted.

- [Integrated Christmas desktop](design/seasonal/integrated-christmas-desktop.png)
- [Integrated New Year phone](design/seasonal/integrated-newyear-phone.png)

Screenshots use synthetic fixture accounts/data. The fixture date differs from the
real calendar. These are real application renders, not a production observation.

## Verification and limits

Python 3.11 hashed test-lock setup, dependency compatibility and cloud doctor passed.
Existing appearance unit/browser group: 22 passed. Combined appearance/new-countdown
group before the final layout test: 34 passed. Expanded new-season group: 13 passed,
including 32 real-page layout combinations (two seasons × four widths × two colour
modes × Home/profile) with enlarged text, reduced motion and contrast checks.
Counts overlap; do not sum them as unique tests. JUnit gates pass with zero skips,
failures or errors. One existing Starlette/httpx deprecation warning is present.
Desktop Christmas and phone New Year real-page screenshots were visually inspected.

Coverage includes wrong device clock, midnight transition, no-script post-midnight view,
private-preview isolation, invalid year and invalid schedule atomic rollback,
saved preferences, open-form retention and print. Baseline contrast tool passed;
16 new text/action palette pairs meet 4.5:1. JavaScript syntax and diff checks pass.
This does not claim a complete accessibility audit or native screen-reader review.

Final focused browser/new-season run after the admin-copy refinement: 16 passed
in 34.01 seconds, zero failures/skips, JUnit gate passed. Full normal/shuffled suites, dependency/container audits,
version metadata gate and hosted phone acceptance remain required before release.
Version/changelog/service-worker metadata is intentionally unchanged until release
order with Telegram is known. The candidate is not release-ready on that basis.

## Parallel Telegram work

Refreshed main and `origin/feat/telegram-private-work-lookup` at `6a83c07`.
Only `docs/SETUP_STATUS.md` currently overlaps by changed path. Shared layout changes
here are limited to loading dedicated seasonal assets and including a dedicated
scene. No Telegram/application service, dependency or release-version edits.
Do not merge or publish over Telegram's work automatically. Path comparison does
not establish behavioural compatibility or future mergeability.

Next: collect hosted phone review of the current seasonal candidate, resolve feedback,
refresh current main/Telegram diffs, and test the combined result after the first
feature merges. Reconcile release versions only once order is known. Keep both
status entries during reconciliation. Production release requires an explicit user
instruction and all existing release/backup gates.
