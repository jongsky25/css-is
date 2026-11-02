# Christmas companion build handoff — November 2, 2026

## Release preparation requested

The user requested release preparation and full checks after the merge-readiness
assessment. Candidate 9.61 is based on current main `adb83b4` (9.60). Version,
in-app/Markdown changelogs and service-worker cache are now synchronized. Proposed
order: companion first, then update Telegram from main and preserve both 9.60 and
9.61 history. Telegram remains independent at `af51001` (candidate 9.79); its branch
has not been edited. If main advances first, reconcile the candidate and rerun
required checks. Merge/production release remains pending final owner approval.

The private preview retains feature source `a9441df`; subsequent application-facing
changes here are release metadata/cache/changelog only. Full exact-head CI results
will be recorded in the release PR so documentation updates do not restart an
otherwise verified source. Earlier statements below describe the build phase.

User requested implementation of the reviewed plan with isolation from ongoing
Telegram work. Branch: `feat/christmas-companion-refinements`; worktree:
`/workspace/office-connect-companion-build`; base main `adb83b4` (released 9.60).
No production merge/deployment or live appearance setting change is authorized by
this build request. The source candidate is saved before preview publication.

## Implemented

- Five Christmas styles: Santa (existing compatible `christmas` ID), elf helper,
  reindeer, parol keeper and festive knit. Dedicated shared SVG overlays reuse the
  existing head/body/pot anchors. Aquatic body treatments are reduced to preserve
  fins/faces. Plant styles use pot sleeves, ribbons and small ornaments.
- Seasonal editor gallery groups Christmas/Halloween/everyday styles, opens and
  visually prioritizes the chosen season, and includes Choose buttons. Samples
  use the signed-in actor's companion plus a representative alternate species.
  A Christmas/Halloween mismatch is explained without overwriting saved choices.
  Existing matching-outfit, private preview and explicit publishing flows remain.
- Home companion stage fills the content-container width on every target device,
  below the greeting. The actual illustration and button are centred, including
  the mobile SVG size override. Avatar sizing remains independent from panel width.
- Christmas uses a dedicated capiz-window/parol/poinsettia courtyard, with an open
  central area and a tiled wide composition. The header tree asset is unchanged
  and is no longer reused behind the companion. The pale radial wash is removed.
- Sound controls/credits and Change companion sit below the scenery. The edit link
  is now part of the same movable wrapper so drag cannot move sound controls over
  a stationary edit link. Existing play, audio, drag and personal-accessory rules
  are retained; no new audio or sound preferences are introduced.

The courtyard is the recommended working default. Two additional original tree-free
assets (festive sala and poinsettia veranda) are included for visual comparison,
not exposed as a new persistent scene-setting feature. The screenshots below are
synthetic accounts, never the owner's personal screenshot.

## Review artifacts

- [Phone companion panel](design/christmas-companions/phone-panel.png)
- [Desktop Home](design/christmas-companions/desktop.png)
- [Tablet dark Home](design/christmas-companions/tablet.png)
- Outfit contact sheets: [stage 1](design/christmas-companions/outfits-stage-1.png),
  [stage 3](design/christmas-companions/outfits-stage-3.png),
  [stage 6](design/christmas-companions/outfits-stage-6.png).
- Alternative mockups: [sala](design/christmas-companions/alternative-sala.png),
  [veranda](design/christmas-companions/alternative-veranda.png).

## Verification

Python 3.11 hashed cloud setup, dependency compatibility and browser doctor passed.
All application testing used temporary synthetic databases with external provider
credentials excluded and scheduling disabled. Main runs use cloud_workspace.py.

- Broader appearance/wardrobe/care/audio group: **132 passed** in 74.89s, no skips.
- Final Christmas group after layout refinements: **4 passed** in 22.56s. It
  covers 480 species/stage/outfit combinations plus opt-outs, all five editor
  choices, preview isolation, same-month live swapping and unsaved form retention.
  Real named-rabbit layouts cover 320/390/768/1024/1440 widths in light/dark with
  enlarged text, centred SVGs, full available width, no horizontal overflow,
  artwork/contrast states and controls below the art. Sound/volume expansion is
  exercised and the edit link remains below the expanded controls.
- Opt-in real-HTTP geometry, resize and clamped-chase group: **5 passed** in 17.81s.
  Its isolated environment uses the cloud helper's infrastructure allowlist plus
  CSS_AVATAR_BASELINE=1 and a fresh temporary database; no provider credentials.
  The old chase test assumed an 80px outside margin. It now uses a valid viewport
  position just outside the full-width stage, retaining all clamped-motion,
  facing-direction and redundant-style-write assertions.
- Tracked preview-bundle boot/login/mobile/outbound-blocking group: **3 passed**
  in 7.69s. The initial local staging check exposed the not-yet-tracked new
  template; adding the new runtime files to the candidate resolved it before
  publication. No broken bundle was published.
- JUnit no-failure/no-skip gates passed for all four reports. Groups overlap; do
  not sum them as unique tests. One existing Starlette/httpx deprecation warning.
  Changed Jinja templates and all scene SVGs parse; JavaScript syntax/diff checks
  pass. Contact sheets and phone/desktop real-page captures were visually inspected.

Full normal/shuffled release suites, dependency/container audits and a release
version increase remain required before merging. Version/changelog/service-worker
metadata is intentionally untouched until the release order with Telegram is known.
No release-ready CI claim is made for this build candidate.

## Parallel work and preview

**Published preview:** source `a9441df0d1869ac9e99c716cc47e359e98232f6b`,
Space commit `d98f59e4aa973dfba99c67e1a0a5b7c17eb90cb2`. The existing private
CPU Basic preview is RUNNING and its manifest matches that exact source. Authorized
health/login return 200; login has the PREVIEW banner/header. The new companion
stylesheet, courtyard SVG and editor script return 200 and match source SHA-256.
Anonymous health/login return 404. The existing password secret was unchanged.
Hosted app sign-in/owner phone acceptance are pending; the password is not available
in this process. Local staged login/mobile verification passed as recorded above.

Open [the private preview](https://huggingface.co/spaces/equityinhealth/office-connect-preview)
in Safari signed into Hugging Face, then use `preview@example.invalid` with the
saved preview password. Publication reset the synthetic profile and session.
Set a companion name/species in Profile if needed and choose Follow seasonal
appearance; then pick a Christmas outfit in Appearance and update the private view.

Latest compared main remains `adb83b4`; Telegram branch
`feat/telegram-private-work-lookup` is at `af51001`, candidate 9.79. Before adding
this handoff/status entry, there are **no shared changed paths**. Adding the required
status handoff creates only docs/SETUP_STATUS.md overlap; retain both entries later.
No Telegram runtime, workflow, dependency or release-version file is modified here.

The shared private preview was inspected before publication: it still held our
earlier seasonal source `f4438aa`. Telegram's current handoff explicitly defers
preview/deployment. Serialize publication and identify the current source manifest;
do not replace a newer unrelated candidate. Keep the existing preview password.

Phone review once this candidate is published: sign into the private Hub preview,
open Profile, choose/name a synthetic companion if none is shown, then Appearance.
Choose Christmas and a Christmas outfit, enable scenery, and update the private
preview. Publish now affects only this disposable preview if full-page testing is
needed. Check Home on phone/tablet/desktop and expand the volume control. A preview
restart resets synthetic data and sessions. No real account or production password
is needed; the saved preview password remains the appropriate login credential.

Next: verify published preview source/private/RUNNING/health/assets, collect owner
phone feedback, then coordinate any later release and rerun its full gates after
refreshing main/Telegram. Production 9.60 stays unchanged during review.
