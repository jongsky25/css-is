# User levels assessment — November 24, 2026

> **Status:** owner decided on November 24 (section 5). Candidate **10.50** implements the
> new levels on `claude/gracious-einstein-10xohq` (PR #644). Not released.

Owner request: "with a bigger feature base and increase in number of users, maybe it
is time to assess the current user level." This is a read-only code assessment of
main at `741ef68` (10.49 candidate merged). No code changed. Live account counts per role
were not read. Production data is not used from a cloud session. The owner can see them
on Admin → Users & roles.

## 1. What exists today

Access is decided by **four separate layers**, and they have grown independently.

| Layer | Where | What it decides |
|---|---|---|
| **Global role** (one per account) | `auth.py:32-57` `ROLES`/`ROLE_CAPS`; path gate `app.py:2115` | Viewer, Encoder, Section Manager, Administrator |
| **Directory position** | `storage.py` `_org_rank`, `org_unit_chiefs`, `section_oic`, `team_scope_for_user` | Director / chief / section head / acting OIC: approvals, team views, advisory review, calendar visibility |
| **Per-module grants** | `document_role_grant`, `supply_role_grant`, `document_access`, the `travel.template_admins` setting, Admin Section membership (`rooms.is_room_admin`) | Documents, supplies, travel, rooms, meals |
| **Per-account extras** | `admin_user.bureau_access` (''/awa/all), `birthday_coordinator`, Telegram/MCP/integration grants | How far a person sees; channel consent |

The four roles were designed for the original survey (CSS) system. Their descriptions
still mention only survey work. Since then most of the app (documents, work, supplies, travel, rooms,
approvals, calendar) decides access through the directory and the module grants. That
design is sound: authority follows the person's actual seat. The global roles were not
re-shaped to match.

### What each role still controls

- **Viewer**: sign in. The `view` capability is in every role, so its 16 checks
  never deny anyone.
- **Encoder**: Viewer plus `/encode` (paper survey entry). One page, one nav item and one home tile.
- **Section Manager**: create/manage activities, the event monitor, edit survey data and add
  outside resource persons. Despite the name, **it is not tied to any section**.
  Its reach comes from wherever the person sits in the directory.
- **Administrator**: everything under `/admin` (65 routes: users, email, backups, AI,
  restructure, travel settings, appearance, audit and more), directory editing, hiding
  people, merges and walk-in edits. It is also a **catch-all override** in about 15 places
  (any activity, supplies stock, approvals screen, orphaned requests, late wellness,
  calendar colours/notices, Telegram groups).

## 2. Findings, most important first

1. **Section Manager is unscoped in calendar actions.** `calendar_notice.can_send`
   (`calendar_notice.py:41`) and `_may_start_item` (`calendar_routes.py:1055`) allow
   any Section Manager to email notices about, or start, **any** calendar item in the bureau.
   `office_calendar.py:341` sets the manage flag the same way.
   Activity management is scoped (`activity_permissions.py:6-16`), but only to the person's
   directory unit. A non-chief Section Manager placed at division level manages the
   whole division's activities (`team_scope_for_user` gives every placed person a "unit"
   scope, `storage.py:8378-8385`).
2. **An Administrator with no directory seat sees bureau-wide team data.**
   `team_scope_for_user` deliberately gives admins no extra sight. However,
   `user_is_approving_chief` admits every admin (`storage.py:8246`), and `_org_scope_for_user`
   turns "no team" into "whole bureau" (`storage.py:8389`). As a result the wellness rollup,
   wellness dashboard and AWA roster/ANNEX C show everyone to such an admin. This
   contradicts the stated rule that sight is granted only through `bureau_access`.
   The nav `chief` capability includes admin, while `/approvals` itself excludes admin, so the
   two disagree.
3. **Authority is set in code.** `BUREAU_ACCESS_SEED` (`storage.py:5327-5370`) names
   specific accounts. On first boot it grants them bureau access, and for one of them it **forces
   the Administrator role**. `NON_STAFF_ACCOUNTS` (`storage.py:5340`) is also a named list.
   Personal addresses in source, and a role that is changed outside the audited Users page,
   become riskier as accounts grow.
4. **"Administrator" means three different things.** There is the app role, Documents
   `grant_admin`/`workflow_admin`, and "Admin Section" (`is_room_admin`, which governs rooms,
   meals **and** travel verification). These are easy to confuse when assigning people.
5. **"Chief" is defined at least three ways.** `_org_rank` matches words in the designation
   text, `org_unit_chiefs` uses unit level, and Documents `seats()` counts only division/office/bureau
   chiefs, so section heads never count. OIC lookups are rewritten as raw SQL in
   `documents_permissions.py`, `documents_rules.py` and `advisory_review.py` instead of
   using `get_section_oic`. After the restructure, a renamed designation can silently
   change who approves.
6. **Travel template administrators** are a free-text username list in a setting
   (`travel.py:18, 397`). Unlike the supplies/documents grant tables, it has no audit
   trail and no scope.
7. **Supplies stock visibility is computed three ways.** These are `supplies_permissions.py:61-67`,
   `supplies_routes.py:63` and `mcp_read.py:1217`. The web page, the template and MCP can
   disagree about who sees stock numbers.
8. **Unreachable or redundant checks:**
   - `/admin/documents/readiness` also admits Documents grant holders (`work_readiness.py:28`),
     but `/admin` already requires Administrator, so those holders can never reach it.
   - `triage_feedback` always sits behind the same admin gate.
   - `wipe` is defined (`auth.py:55`) and never checked.
9. **Role checks are inconsistent.** There are 35 direct `role == "admin"`-style comparisons across
   about 15 files, alongside `can(role, "manage_users")` elsewhere. The list of valid roles is
   hard-coded six more times (`travel_drafts.py:79`, `calendar_actions.py:59`, four
   Telegram SQL queries). Adding or renaming a role today means hunting these down.

## 3. Recommended direction

Keep what works (directory seats and module grants decide domain authority) and
re-shape the global role so it answers one question only: **what may this account do
system-wide?**

| Proposed level | Replaces | Can do |
|---|---|---|
| **Staff** | Viewer | Everything their seat, unit and grants allow; nothing system-wide |
| **Activity organiser** | Section Manager | Create and run activities, monitor and survey curation, **limited to their own unit** (chief-level reach only for chiefs/OICs) |
| **System administrator** | Administrator | Accounts, settings, backups, directory, restructure. **No automatic override** of approvals, team sight or activities. Sight comes from `bureau_access` like everyone else. |

- **Encoder becomes a grant** ("Survey encoder") that any Staff account can hold, not a level.
- Optional later step: split System administrator into *Accounts admin* (users, roles, OIC,
  bureau access) and *Operations admin* (backups, email, AI, deploy settings) if more
  than one or two people need admin access.
- One `authority.py` (or extended `auth.py`) is the only place that answers "is admin",
  "is chief of X", "is OIC of X" and "valid role". Module code calls it instead of comparing
  strings or re-querying `section_oic`.
- Move `travel.template_admins` into a grant table with audit, matching supplies/documents.
- Remove the account-named seeds from source. Keep their effect as ordinary
  audited assignments that already exist in the live database.

### Phased plan (each phase one release candidate)

1. **Safety fixes, no visible change for correctly placed people**:
   - Scope calendar notice/start to the activity-management rule (finding 1).
   - Stop admin-only bureau sight on wellness/AWA pages unless `bureau_access` grants it (finding 2).
   - Unify supplies stock visibility (finding 7).
   - Fix or move the readiness page (finding 8).
   - Tests for each.
2. **One authority helper**: route all admin/chief/OIC/valid-role checks through it,
   delete the duplicates and dead `wipe`, and add a test that fails on new raw
   `role ==` comparisons.
3. **Rename and re-shape levels**: migrate stored roles (viewer→staff, encoder→staff +
   survey-encoder grant, section_manager→organiser, admin→sysadmin). Update the Users page
   wording and role descriptions. Telegram/MCP/integration grants already revoke on
   role change, so the migration must preserve the role meaning to avoid mass revocation,
   or announce the re-link.
4. **Travel template grant table; remove code seeds.**

## 4. Decisions needed from the owner

1. Should a **System administrator keep overriding** approvals, team sight and any activity, or
   should they see only what their seat and `bureau_access` grant? (Recommended: no override.)
2. Should **Section Manager/Organiser be limited to their own unit**, including calendar
   notices? (Recommended: yes.)
3. **Merge Viewer and Encoder** into Staff, with encoding as a grant? (Recommended: yes.)
4. Split admin into Accounts and Operations now, or later? (Recommended: later, unless more
   than two people need admin.)
5. Before phase 1: on Admin → Users & roles, how many accounts hold each role, and
   who holds Administrator and Section Manager today? This sizes the migration and tells us
   whether finding 2 currently affects anyone.

## 5. Owner decisions and live counts (November 24, 2026)

Live accounts, counted once from Admin → Users & roles at the owner's request
(counts only; no names copied): **73 accounts: 17 Administrators, 38 Section
Managers (10 still pending invites), 17 Viewers, 1 Encoder (pending)**. 16 admins are linked
to a directory seat (7 at a top-level unit, 9 deeper) and 1 is unlinked. Section Managers: 4 at a
top-level unit, 8 one level down, 26 deeper. Bureau-wide sight grants: 2 "work
arrangement", 1 "everything". These counts are before the restructure is applied.

Decisions:
1. **Keep a full-power level, but not for every administrator.** A *Super Administrator*
   keeps all current powers and overrides. A narrower *Administrator* has neither.
2. **Section Managers are limited to their own unit**, and a **Division Manager** level is added.
3. **Viewer and Encoder merge** into Staff, with survey encoding as an option.
4. **Split administration now:** the Super Administrator keeps accounts, roles, sight grants, OICs,
   backups, audit, sharing, integrations, restructure and module setup. The Administrator runs operations
   and settings.

### What 10.50 does

| Level (label) | Stored code | Reach |
|---|---|---|
| Staff | `viewer` | Their seat, unit and grants |
| Staff + survey encoding | `encoder` | Staff + `/encode` |
| Section Manager | `section_manager` | Activities, monitor, notices for **their own unit**. At division/office level, that unit alone unless they are its chief or acting OIC. |
| Division Manager | `division_manager` | The same, for the **whole division** they sit in |
| Administrator | `system_admin` | Section Manager reach + capability `operate` (most of `/admin`, `/ops`) + directory, hide, merges, walk-ins, feedback. **No overrides.** |
| Super Administrator | `admin` | Everything, including `manage_users` pages and the overrides |

The stored codes are unchanged for existing accounts. A role change signs the person out and
revokes their Telegram/MCP/integration grants, so relabelling `admin` as Super Administrator
avoided doing that to 16 active people. All 17 current administrators are therefore Super
Administrators after deploy. **Owner action after release:** on Admin → Users &
roles, move everyone who should not keep full power to *Administrator*, and consider
moving the 4 Section Managers placed at a top-level unit to *Division Manager* where that
is their job. Encoding stays a role variant ("Staff + survey encoding") rather than a
separate account flag, which gives the same result without a schema change.

Not in 10.50 (still open from section 2): seatless Super Administrator bureau sight is kept
on purpose (decision 1); findings 3 (account seeds in code), 5 (one "chief" helper), 6
(travel template grant table), 7 (supplies stock visibility) and 8 (readiness page).
Supplies configuration and Documents setup remain Super Administrator only.
