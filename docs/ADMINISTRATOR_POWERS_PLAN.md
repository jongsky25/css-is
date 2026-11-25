# Administrator powers — November 25, 2026

Owner asked to give the **Administrator** level (`system_admin`) more administration,
but to limit its power to delete in **Users & roles** and **Directory**. Built as candidate 10.53 on `claude/eloquent-sagan-theglm` (PR #648); not merged or released.

## 1. Where things stand (10.51/10.52 on `main`)

1. Administrator = Section Manager + survey data fixes. It cannot open `/admin/*`,
   `/directory/*` (except adding an outside resource person) or `/ops`.
2. Access is decided by URL prefix in `_required_cap` (`app.py`): `/admin/users` and other
   `_SUPER_ADMIN_PATHS` need `manage_users`; the rest of `/admin` and `/ops` need `operate`;
   `/directory` needs `directory`. All three are Super Administrator only (`auth.py`).
3. The comment in `_required_cap` says the rest of `/admin` is "open to the Administrator";
   that is out of date since the owner narrowed the level on Nov 24. Fix the comment in step 4.

## 2. Proposed split

Rule: the Administrator may **add and correct**; anything that **removes, deactivates,
combines records or raises someone's access** stays with the Super Administrator.

**Users & roles** (`/admin/users`)

| Action | Administrator |
|---|---|
| 1. Invite an account; reset to the default password | Yes |
| 2. Set birthdays and birthday coordinators | Yes |
| 3. Set or clear an acting OIC | Yes |
| 4. Change a role among Staff, Staff + encoding, Section Manager, Division Manager | Yes |
| 5. Grant or remove Administrator / Super Administrator, or change any admin's account | No |
| 6. Deactivate an account (the app's "delete"; there is no hard delete) | Below Administrator only (answer 2) |
| 7. Bureau-wide sight grants | No (raises access) |
| 8. Audit, backups, sharing, integrations, restructure, Documents setup | No |

**Directory** (`/directory`)

| Action | Administrator |
|---|---|
| 1. Add or edit divisions, sections and the bureau | Yes |
| 2. Add or edit staff, photos, birthdays; add or edit outside resource persons and organizations | Yes |
| 3. Clean-up: title case, rename | Yes |
| 4. Delete a unit | **No** |
| 5. Archive a person; "archive low-use"; Clear sample data | **No** |
| 6. Merge duplicate people; split a person | **No** (combines or rewrites records) |

## 3. Owner answers (November 25, 2026)

1. No settings, Ops, feedback triage or hiding people for the Administrator.
2. Yes: the Administrator may deactivate and reactivate accounts below Administrator
   (Staff, Staff + encoding, Section Manager, Division Manager).
3. No: merging (and splitting) people stays with the Super Administrator.

Also kept with the Super Administrator while building: signatures (forgery risk), the
Name cleanup AI suggestions (they feed merges), and editing the directory entry of anyone
holding an Administrator or Super Administrator account (the directory email is the login
email, so editing it could take over that account through a reset link).

## 4. Build steps (built as candidate 10.53)

1. `auth.py`: add `users_edit` and `directory_edit` to the Administrator; keep `manage_users`
   and `directory` as the Super Administrator's full powers. Update `ROLE_BLURB`.
2. `app.py` `_required_cap`: open `/admin/users` and `/directory` to the new edit
   capabilities, with a list of Super-only paths (`/bureau-access`,
   `/unit/*/delete`, `/person/*/archive`, `/clear-sample`, `/cleanup/archive-low`,
   `/cleanup/merge`, `/cleanup/split`, `/cleanup/ai-suggest`, signature image, quick-fix archive) that still need the full capability.
3. Role-change handler: refuse assigning `system_admin`/`admin`, and refuse any change to an
   account that holds either role, unless the actor is Super Administrator.
4. Templates (`users.html`, `directory.html`, `cleanup.html`): hide the delete, deactivate,
   archive, merge and split buttons for the Administrator; show a short note who can do it.
5. Tests: every route above, per role (Administrator allowed/refused, Super allowed), including
   direct POSTs that bypass the hidden buttons; audit entries unchanged.
6. Candidate version on a review branch; release only on owner instruction.
