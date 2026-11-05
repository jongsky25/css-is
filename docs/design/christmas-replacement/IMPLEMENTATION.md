# Paskong Pinoy implementation

Candidate 9.96 on `feat/paskong-pinoy-theme`, based on main `75a7eb4` (9.95).
The user instructed execution after reviewing the three-direction study; this
implements the recommended Paskong Pinoy direction. Production release is separate.

## Result

- Original capiz-parol artwork, evergreen, cranberry ribbons, gold lighting and
  warm ivory work surfaces replace the flat Christmas hero illustration.
- The illustration is a self-hosted 1536 × 1024 WebP, 282,284 bytes. It was
  generated for this task and encoded at quality 84; no external image service or
  font is requested by the application. The source reference is the original
  concept board, not a third-party photograph.
- Desktop uses separate copy/art columns. Phones stack copy above 190 px of art.
  The top-aligned crop retains the main parol; the outer tree and gifts may crop
  with the container. All greeting text remains real HTML.
- The new fallback greeting is “Maligayang Pasko!” with “A little brighter,
  together.” Existing nonblank administrator greetings remain unchanged; no
  configuration migration or live setting mutation is included.
- Matching light strands decorate the navigation, footer and companion stage.
  The companion retains its existing full-width placement, size, rig, outfit,
  sound and edit controls. Its scenery changes to a green/gold lighted setting.
  The concept's compact rabbit card is not substituted for the established controls.
- Christmas-only selectors preserve the other seasonal themes. Artwork-off,
  high contrast, reduced motion, forced colours and print remain supported.
  The Christmas hero is static even when optional effects are on.

## Verification

Python 3.11 locked setup, dependency compatibility and cloud doctor passed.
The appearance, appearance-browser, seasonal and companion groups passed:
**40 tests, zero failures/skips**. A pre-existing Starlette/httpx deprecation
warning remains. A first screenshot review caught a mobile cascade issue that
the overflow-only checks missed; it was fixed and an explicit vertical-stacking
assertion was added before the successful final 40-test run.

Browser coverage includes 320/390/768/1440 px seasonal Home/form views in
light/dark appearance with enlarged text, plus the named companion at 1024 px,
its sound controls, private preview isolation, live form-state retention, long
custom greetings, image delivery/decoding, forced colours, contrast and print.
Eight new text/background pairs passed 4.5:1, ranging from 6.25:1 to 11.68:1.
This is not a complete accessibility audit or native Safari acceptance.

After the final artwork crop adjustment, the three relevant layout/opt-out/
companion browser tests passed again: **3 passed, zero failures/skips**.
Release metadata, JavaScript syntax, SVG XML and diff checks passed.
Full normal/shuffled CI, dependency audits and hosted phone acceptance are still
required before a production release. No shared preview has been replaced.

## Real application screenshots

Synthetic fixture accounts/data; these are local application renders, not
production observations. The fixture's date is intentionally independent of today.

- [Phone, light](implemented-phone.png)
- [Desktop, light](implemented-desktop.png)
- [Desktop, dark](implemented-dark.png)
- [Named companion, desktop](implemented-companion.png)

## Review

In an isolated instance, choose Christmas and enable artwork in Appearance, then
update the private preview. A pre-existing saved custom greeting will still be
displayed; clear the greeting in the draft to see the new fallback. Check phone
layout, dark mode and the companion controls. Do not use Publish now on a live
instance merely to review the candidate.
