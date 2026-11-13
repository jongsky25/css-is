# Public advisory posters

Added in 10.33. An activity (link tree) can produce the BLHSD **ADVISORY** image, a shareable announcement with a
number, deadlines and links, a QR code and a contact person, and can show it on its public page.

## Using it

1. Manage the activity, then open **Public advisory** (`/activities/<token>/advisory`). Anyone who may manage the
   activity may use it (`activity_permissions.can_manage`: admins, the creator, and a section manager whose team runs it).
2. The form starts from the activity: headline (title and dates), a message (title, dates, venue), and table rows
   (a Registration row with its due time when the activity has a registration window, then each link-tree resource
   link that is not "after the activity"). Everything is editable; **Attention** and the contact person are typed by hand.
   `**double asterisks**` make words bold. The contact you save is offered again on the next advisory.
3. **Save** assigns the number once, `YYYY-MMDD-NNN` (issue date, then the day's running count). Editing keeps the number
   and raises the revision. Text that cannot fit the poster is refused with a plain message instead of being clipped.
4. Preview, **Download image** (PNG, 2544 x 3600) or **Download PDF** (one A4 page).
5. **Publish on link tree** shows the image, with download links, at the top of the activity's public page
   (`/e/<token>`); **Withdraw** hides it. Saved edits to a published advisory go live at once. A draft is never public.
   Invited ("outside") activities have no link tree and cannot publish one.

## How it is built

| Piece | File |
|---|---|
| Renderer (pure: draws a dict to PNG/PDF, autofits text, QR code) | `advisory.py` |
| Table, numbering, defaults from the activity, save/publish | `activity_advisory.py`, `storage.py` (`event_advisory`) |
| Routes: manager editor and files, public image/PDF | `activity_advisory_routes.py` |
| Editor page, link-tree card, Manage entry | `templates/activity_advisory.html`, `link_tree.html`, `activity_manage.html` |
| Fonts, logos, icons | `assets/advisory/` (see its README for licences) |
| Tests | `tests/test_advisory.py` |

- The layout is the office's advisory image on a 1272 x 1800 design grid (A4 proportions). Fonts are open-licence
  look-alikes (Fraunces, Libre Caslon Text, Poppins); replace the files in `assets/advisory/` with the exact fonts, or
  `bagong_pilipinas.png` with the official logo (the bundled one was cropped from a sample and is low resolution).
- The poster holds activity details only: no attendee data is read.
- The site-wide browser policy forces `no-store` outside `/static/`, so browsers re-request the image; the server keeps
  each rendered revision in memory (24 entries) so a render (about 1.3 s) is not repeated per view.
- The QR code and printed link are the activity's link-tree URL, shortened by `short_links.share` when Short.io is
  enabled (`CSS_SHORT_LINKS=1`); the URL is stored when the advisory is first saved.

## Deployment note

`deploy_hf.py` ships an explicit file allowlist; the three new modules are in `RUNTIME_PY`, and `assets/**` already ships.
No new dependency (Pillow, reportlab and qrcode were already locked). Merging to `main` deploys; see `DEPLOY.md`.

## Not done / ideas

- Posting the advisory to a Telegram group automatically.
- Exact fonts and the official Bagong Pilipinas logo.
- A "regions covered" or "attention" picker; both are free text today.
