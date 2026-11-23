# Office restructure — impact assessment (November 23, 2026)

Input: the interim BLHSD structure DPO, saved as
[the structure reference](org/BLHSD_INTERIM_STRUCTURE_2026.md) and
[machine-readable units](org/blhsd_interim_structure_2026.json).
Assessed against `main` at `40d15e9` (10.42). Read-only assessment; no code,
data or deployment changes were made.

## Summary

Office Connect already models the bureau as data (`org_unit` tree with
`bureau > division > section` paths, plus one `office` for the Director), and
most features read that tree. So **renaming people and units is mostly a
directory task**. The real blockers are structural assumptions in code:

1. **Exactly one Director.** The new order has two (Director IV over Divisions
   1–3; Director III over Divisions 4–5 and the MSU). Entering a second Director
   today would **break advisory review** outright and **mis-route approvals**.
2. **Only three levels, one office.** There is no place for two Director
   offices, or for the MSU and AU as units that are neither division nor section.
3. **History and routing are tied to unit IDs.** Units cannot be moved or
   retired, and the deletion check ignores documents, Work, supplies and
   advisories. Rewriting the tree in place would relabel past records.
4. **Old names are hardcoded** in a handful of imports, templates, signature
   blocks and Apps Script replacements.

**Do not enter Director III or the new units in the live directory until the
Phase 1 code changes ship.** Doing so first will break or mis-route live
workflows.

## 1. Breaks if a second Director is entered (critical)

| Area | Location | What happens |
|---|---|---|
| Advisory review | `advisory_review.py:26` `effective_director` | Raises "Exactly one current Director…" → no advisory can be submitted or endorsed |
| Wellness/AWA/rank approvals | `storage.py:7899` `get_approvers_for` | Division chiefs escalate to **both** Directors, regardless of oversight |
| Self-approval | `storage.py` `_is_director` | Every "director" auto-approves their own filings; Director III would bypass Director IV |
| Chief notifications | `storage.py:7713` `org_unit_chiefs` | Bureau-level notices go to both Directors |
| Team scope | `storage.py:8027` `team_scope_for_user` | Any director sees the whole bureau (should Director III see only their units?) |
| Documents authority | `documents_permissions.py:31,40` `seats`, `director` | Any rank-3 person holds Director-class review authority; `office` units are not seats |
| Signatures | `storage.py:7766` `org_seat_holder(…, 3)` → `travel.py:552`, `activity_docs.py:364` | "First director found" is printed as head of office on travel/DPO forms |
| Signatory picker | `storage.py:3705–3757` | Both ranked identically; both excluded from CSS per-person rankings |

## 2. No place for the new units

- `org_structure` (`storage.py:3601`) surfaces one directorate and treats any
  section directly under the bureau as "administrative"; MSU and AU would both
  be shown as admin sections and the second office would be hidden.
- `_ORG_LEVEL_RANK` has no `office`/`unit` level; MSU/AU staff have no division
  parent, so section-head → division-chief escalation finds nobody
  (`get_approvers_for`), and travel certification finds no certifying officer
  (`travel.py` `_division_path`).
- Documents accepts only `division/bureau/section` as lead office
  (`documents.py:510`), so a Director's office or the MSU cannot own a document.
- Dashboards (`app.py:13183, 14367, 14737–14806, 16174`,
  `dashboard_insights.py:3781`) render one directorate card + divisions + admin
  sections.
- Staff assignment picker (`templates/staff_form.html:84–98`) has fixed
  optgroups for one Director's office, division chiefs and "Administrative".
- Room, meal and travel-review approvers find the Administrative Section by a
  path segment `ADMIN` (`rooms.py:704`, `travel_review.py:44`, `rooms_notify.py:37`).
  **The AU must keep an `…/ADMIN` path** or these silently stop working.

## 3. History, routing and transition

- `update_org_unit` only renames; there is no move/re-parent or retire.
  Renaming "Section 2" into "Section 7" would make past CSS events, documents,
  Work items and supplies requests look like they belonged to the new section.
  Supplies already store a `unit_snapshot`; events, documents and Work do not.
- `org_unit_deletable` checks only children, staff and surveys — deleting an old
  unit could orphan documents, Work, supplies, advisories and grants.
- Document routing rules store unit IDs and keyword topics
  (`documents_rules.py:60–90`). Topics moved between units (e.g. LIPH/AOP now
  Section 7; equity/IP now Section 3) need re-mapping.
- `section_oic` holds one OIC per unit and is the right tool for the three OIC
  division chiefs; it also needs office-level support for Director coverage.
- Staff hold **one** unit (`resource_person.org_unit_id`). The order gives several
  people two or three assignments (Director-office support, AU member, division
  admin). Division admins are a new role with no seat in the app.
- The order's transition rule (two-week carry-over; DPCR/IPCR commitments stay
  with the original staff) means **open Work tasks, documents and approvals
  must not be auto-reassigned** when people move units.

## 4. Hardcoded old names and people

| Location | Item |
|---|---|
| `app.py:8522–8525` | CSM report signatories hardcoded (names a Director IV who is no longer the incumbent) |
| `apply_directory.py:29–38, 102–117` | Old HSDD/HSMED + S1–S5 tree; re-running it would recreate the old structure |
| `calendar_import.py:12–99`, `calendar_import_apply.py`, `calendar_import_suggest.py` | Owners fixed to bureau + s1–s5 and colour → section map |
| `work_arrangement_backfill.py:73–111` | August 2026 roster with old division strings (runs at boot; one-shot) |
| `storage.py:11419` `seed_wa_prepared_by_default`, `storage.py:5173` access seed | AWA "Prepared by" and bureau access pinned to a named AU lead |
| `travel.py:14,16`; `apps_script/travel_templates.gs:280–467` | "OIC-Director", "Director IV", "Medical Officer V", "Division: HSDD", old section literal |
| `templates/public_layout.html:89` and aria-labels in `login.html`, `result.html`, `arta_link.html`, `dash_layout.html` | "Equity in Health Section" branding — that section no longer exists by that name |
| `templates/directory.html:103,171,235,259`, `dashboard_insights.py:1925`, `mailer.py` previews | Headings/examples assuming old names or "Section N - Name" |

Historical changelog text and demo seeds are fine to leave.

## Recommended plan

Each phase is a separate review branch with tests and release gates. Phases 1–2
must ship before the live directory is changed.

**Phase 0 — decisions and data (no code).** Confirm the open points in the
reference (DPO number/effective date, Annex A, Division 5 acronym) and the
policy questions below. Prepare the seat-holder list privately.

**Phase 1 — multi-office model.** Tree becomes
`bureau > office (OD4, OD3) > division > section`, with MSU under OD3 and AU
under the bureau at `…/ADMIN` (proposed paths in the JSON). Then:
"Director" = head of the nearest ancestor office; division chiefs escalate to
their own office's Director; `effective_director(unit)`; `org_seat_holder` and
signatures resolve per unit; `office`/`unit` levels become valid seats, lead
offices and escalation stops (unit lead = rank 1, reports to the office head);
`org_structure`, dashboards and the staff picker render several offices and
units; OIC coverage at office level. Tests with synthetic two-Director data.

**Phase 2 — safe transition tooling.** Add retire (not delete) for units and
re-parenting; widen the deletion guard to every referencing table; add unit
snapshots where history needs the old label; a dry-run, backed-up restructure
script driven by the JSON (replaces `apply_directory.py`) that creates new
units, retires old ones, moves staff, and **leaves open work items with their
current owners**; a routing-rule re-map review screen. Optional: secondary
assignments for staff with more than one role and a "division admin" seat.

**Phase 3 — hardcoded names.** Move CSM/AWA signatories into the directory or
settings, update calendar import owners, travel template replacements,
Equity-section branding and directory examples.

**Phase 4 — reuse the reference.** Suggest document routing from section
topics/mailboxes, add "who handles X" verified answers, and use the mailboxes
for intake mapping.

## Decisions (owner, November 23, 2026)

1. **Director III's own requests** (leave/AWA/wellness) are approved by the
   **Director IV**. Only the Director IV keeps automatic self-approval.
2. **Final approval** for advisories and division-owned documents goes to the
   **Director who oversees the owning division** (Director IV for Divisions 1–3;
   Director III for Divisions 4–5 and MSU). Items owned by a Director's office
   go to that Director. Items owned by the bureau or the AU go to Director IV.
3. **Director III's team views** default to Divisions 4–5 and the MSU, with an
   option to switch to the whole bureau.
4. **Old units are kept as retired history**, not renamed or deleted. Past records
   keep their original unit; new work uses the new units.
5. **AU approvals:** the AU lead's own requests and AU-owned items go to the
   **Director IV**. All AU staff, including those who also serve as division
   admins or Director-office support, are approved by the **AU lead** (one home
   unit per person; no secondary-assignment feature needed for approvals).

## Phase 1 implementation (candidate 10.43)

Built on `claude/funny-bohr-qif52k`. Directory-driven; no schema change.

- **Who is "the Director" for a unit:** the Director attached to the nearest
  `office` unit above it; otherwise the top Director (highest grade read from
  "Director IV"/"Director III" in designation or position). One shared resolver
  in `storage.py` (`director_accounts_for_path`, `director_seat_holder`,
  `_decider_seat`) feeds approvals, approver copy, notifications, signatures,
  advisory review and Documents.
- **Approvals:** division chiefs → their overseeing Director; a unit head
  directly under an office (MSU, designation "Unit Head") → that Director;
  Director-office staff → their Director; AU lead ("Admin Head") → top Director;
  Director III → Director IV; only the top Director auto-approves. An OIC set on
  an office is added beside that Director.
- **Advisory review / Documents:** Director stage and Director-class review
  follow the owning unit; office units are valid seats and lead offices.
- **Team views:** a non-top Director sees her office subtree; the existing
  per-account bureau access grant (Admin → Users) widens it to the whole bureau.
- **Signatures:** travel head of office = Director over the filer's unit;
  activity DPO and AWA annex = top Director.
- **Directory UI:** every office is listed and selectable; units outside
  divisions show their office.
- **Unchanged with one Director:** every rule resolves exactly as before.

**Data the directory needs before switching:** offices at level `office` with
divisions nested under them (proposed paths in the JSON), Director titles that
include their grade, the MSU lead designated "Unit Head", and the AU kept at a
path ending in `/ADMIN`. Re-parenting existing units needs Phase 2 tooling.

**Known limits left for later phases:** Teams/dashboard cards still show one
directorate card; travel certifier for MSU/AU staff falls back to settings;
the Documents Director inbox (`director()`) remains open to any Director;
hardcoded names (Phase 3) are untouched.

## Phase 2 implementation (safe restructure tooling)

- `org_unit.retired_at` (additive column). Retired units stay readable for history
  and rollups, are marked in the directory/staff picker, and are refused for new
  staff, documents, routing rules, Work cases, newly chosen contribution units and
  new advisories. Existing items keep working under their old unit.
- `move_org_unit` re-parents a unit and its subtree (ids unchanged), refusing
  cycles, taken paths and retired parents. `retire_org_unit` refuses while current
  staff, an acting OIC or unretired children remain.
- Deletion is refused for any unit referenced through any foreign key
  (introspected), not only staff and surveys.
- `scripts/restructure_directory.py`: plan (committed JSON) + private mapping;
  dry run by default, `--apply` backs up then applies in one transaction; reports
  routing rules to re-map; never reassigns open work. Runbook:
  [ORG_RESTRUCTURE_RUNBOOK.md](ORG_RESTRUCTURE_RUNBOOK.md).
- MSU and AU are stored at section level (units outside divisions).

## Phase 3 progress (hardcoded names)

Done:
- Official CSM report "Approved by" now follows the head of office set under
  Travel filing settings, else the top Director in the directory (the code
  constant named a former Director IV). "Prepared by" is unchanged.
- `apply_directory.py` refuses to run without `--legacy-structure`, so the
  superseded two-division tree cannot be recreated by accident.
- Teams and dashboard unit cards show every Director office, including in
  scoped views.

Needs owner input before changing:
- "Equity in Health Section" branding on public/login pages: which unit (if any)
  the app is credited to now.
- Calendar import colour → section mapping (`calendar_import.py`): the colours
  the office will use for the ten new sections.
- Travel Apps Script template literals (`apps_script/travel_templates.gs`):
  depend on the updated official templates.
- Travel certifying officer for MSU/AU staff (no division chief): who certifies.
