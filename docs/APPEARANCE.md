# Seasonal themes and avatar styling

Administrators open **Administrator → Appearance** (`/admin/appearance`).
Choose Default, Halloween, or Christmas for the page, and independently choose
an avatar outfit. The initial fallback preserves automatic monthly accessories.
“Default · no accessory” removes the seasonal accessory. Species, names, earned
growth regalia, wellness progress, and care behavior remain personal.

## Editing and publishing

- **Save draft** stores an administrator draft without changing the live page.
- Selecting a theme automatically updates the actual home page in a private
  iframe. **Update preview** also refreshes it on demand. Desktop and mobile
  widths are available. Preview links only affect an authenticated
  administrator's request, and never write the chosen styling to settings.
- **Publish now** applies a manual override. Set an optional expiry in
  Asia/Manila; leaving it blank keeps the override until an administrator clears it.
- **Return to schedule** clears the manual override.
- **Restore default** creates an indefinite override using the saved fallback,
  so an active scheduled event cannot immediately replace it.
- **Save selections as default** changes the fallback appearance.

The editor warns before leaving unsaved changes. A revision check rejects stale
submissions from another tab or administrator; reload and review before retrying.
Administrator mutations use the existing session/role and same-origin boundary,
plus a session-bound CSRF token. Bearer integration credentials grant no access.

## Full Halloween design

Halloween enables illustrated artwork by default. Light mode uses parchment and
cream surfaces, orange actions and purple navigation; dark mode uses a midnight
palette. A large haunted-office banner includes a moon, bats, friendly ghost,
pumpkins, bare trees and a cobweb. Companion stages have pumpkin and lantern
props; the page ends in an illustrated skyline. These are local SVG assets and
require no third-party requests. The static design remains seasonal with motion
disabled. Private previews suppress automatic onboarding tours.

Administrators independently control **illustrated scenery**, **ambient
animation**, **avatar costume**, and a **banner message** (up to 100 characters).
Animation adds slowly drifting mist and a bat in the banner. Reduced-motion
preferences suppress it. Turning artwork off retains the seasonal palette.
High-contrast mode retains its own colors, and scenery is hidden when printing.

Three Halloween outfits are available: witch hat/cape, vampire collar/cape and
pumpkin suit. Potted plants receive coordinated pot treatments; headwear follows
each species' existing head anchor. The costume layers preserve the animated
head/body elements and earned regalia during live changes. Existing saved
configurations and history entries acquire the new settings when read, so
restoration remains compatible.

## Scheduling and restoration

Events have a name, theme, outfit, decoration setting, local start/end, IANA
timezone (initially Asia/Manila), and draft/published/disabled status. Edit an
event to change its status or settings. Remove old events when no longer needed;
up to 100 can be retained. Annual recurrence is outside this first release.

The server stores instants as UTC epoch seconds and retains each event's timezone
for editing. Ambiguous or nonexistent daylight-saving times are rejected. Start
times are inclusive; end times are exclusive. Published windows cannot overlap;
adjacent windows are allowed. Disabled and draft events do not activate.

Resolution order: active manual override → active published event → fallback.
An expiring override resumes this resolution at expiry, including any event
already underway. No cron worker is required. Existing pages poll at most once
per minute, refresh at the next boundary and on focus/visibility, and update
styles and accessory artwork without reloading or discarding forms. Hidden
pages refresh when shown. Network failures retain the last working appearance
and retry. Device clock skew can delay an open page's update until the next poll;
new requests always resolve against server time.

History shows the latest 50 configuration changes, including schedule edits.
Restore creates a new revision and restores the snapshot's fallback, manual
override (including its original expiry), draft, and schedules. Past windows
remain past; an expired override does not reactivate. All changes, including
draft edits, are recorded in the existing hash-chained audit log. SQLite commits
configuration, history, and audit atomically.

## Integration and maintenance

- `appearance.py`: curated preset catalog and deterministic resolution rules.
- `appearance_storage.py`: JSON configuration in `app_setting` under
  `appearance.config`, plus the `appearance_history` table.
- `storage.init_db`: creates the history table on existing and fresh databases.
- `appearance_routes.py`: administrator editor, current appearance, validated
  avatar SVG endpoint, and request-scoped rendering context.
- `dash_layout.html`: styles all pages using the shared signed-in dashboard layout.
  Standalone survey, login, print/export, and email templates keep their formats.
- `_avatars.html` / `_avatars_art.html`: the monthly SVG art and full Halloween
  costume layers. Christmas uses Santa hats or festive ribbons. All 16 species
  and six growth stages are supported.
- Seasonal CSS preserves personal light/dark mode, high-contrast colors,
  semantic status colors, and reduced-motion preferences. Decorations are
  optional and hidden when printing.

No new production dependency, external asset service, or deployment task is
required. Add future curated presets to the catalog and stylesheet. Custom asset
uploads and individual costume wardrobes are deferred.

## Verification

```bash
python qa_preflight.py
python -m pytest -q tests/test_appearance.py tests/test_appearance_browser.py tests/test_avatar_care.py tests/test_browser_security.py
node --check static/js/appearance.js
node --check static/js/appearance-admin.js
```

Browser checks use real application handlers and isolated test SQLite data.
They launch an installed Chromium or Playwright Chromium and skip if neither is
available. Checks cover publishing, preview isolation, mobile layout, reduced
motion, contrast, live accessory updates, schedule expiry, and preserving unsaved
profile input. Backend checks cover access, CSRF/origin validation, atomic
rollback, stale revisions, overlapping schedules, restoration and art rendering.
