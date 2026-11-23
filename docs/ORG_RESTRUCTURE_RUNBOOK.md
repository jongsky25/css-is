# Directory restructure runbook (Phase 2)

How to move the live directory onto the
[interim structure](org/BLHSD_INTERIM_STRUCTURE_2026.md) without losing history.
Background and decisions: [assessment](ORG_RESTRUCTURE_ASSESSMENT.md).

**Prerequisites:** the two-Director release (10.43) and this tooling are
deployed; the DPO number/effective date is known; a fresh verified backup exists.
Never run this against production to "try it": dry-run on a downloaded copy first.

## 1. Prepare the private mapping

Copy [the example](org/restructure-mapping.example.json) to a file whose name
contains `restructure-mapping` (git-ignored) **outside the repository or
uncommitted**. It holds staff record ids, so it must never be committed.

- `bureau_path`: the live bureau root path (the Directory page shows paths).
- `reuse`: existing units that become a plan unit and keep their id, so their
  staff and history follow. Keep the Office of the Director → `OD4` and the
  Administrative Section → `AU` (its path must keep ending in `/ADMIN`).
- `retire`: every old division/section that does not continue. Retired units
  stay for history and disappear from pickers; they are never deleted.
- `staff`: every current staff member's new unit (plan key) and, where it
  changes, their designation. Leads need: Director titles with their grade
  ("Director IV"/"Director III"), "Division Chief", "Section Head",
  "Unit Head" (MSU lead), "Admin Head" (AU lead). Use `rp_id` (from the staff
  edit URL `/directory/person/<id>/edit`) or the `name` as written in the DPO:
  matching ignores order, accents, titles/credentials, middle initials and small
  typos, and an unknown or ambiguous name stops the run with the candidates listed.
- **Every lead must carry its designation in the mapping.** A staff member listed
  without one keeps their current designation unless it is a lead title (Section
  Head, Division Chief, Admin/Unit Head, Director), which is cleared: only the
  leads named in the order lead in the new structure.
- `"create_missing": true` adds a directory record for each DPO name that has none
  (the Nov 22 dry run found 30, including five leads). Ambiguous names still stop.
- Staff with more than one assignment in the order get one home unit (owner
  decision: AU members, including division admins and Director-office support,
  are AU staff). Unnamed vacancies are left out.

## 2. Dry run on a copy

```bash
.venv/bin/python scripts/restructure_directory.py --db /path/to/copy.db --mapping /path/to/restructure-mapping.json
```

It prints every MOVE / CREATE / UPDATE / STAFF / RETIRE line and any routing rule
(`REMAP`) that still targets a retired unit, then rolls back. A problem (for
example, a retired unit that still has staff) stops it with nothing written.
Repeat until the output is exactly what the office expects.

## 3. Apply

Take an admin backup, then run the same command with `--apply`. It writes a
sibling `*.pre-restructure-*.db` copy first and applies everything in one
transaction. Re-running afterwards is a no-op.

## 4. After applying

1. Re-map each `REMAP` routing rule in Documents → routing rules (retired units
   are refused for new routing).
2. Set OICs for the OIC-led divisions (Divisions 1, 3, 4) where an acting
   designation is needed beyond the "Division Chief" designation.
3. Check: Directory shows both offices; a Division 4 chief's request names the
   Director III; the Director III's request names the Director IV.

## What it deliberately does not do

- Reassign open Work, documents, approvals or supplies requests: the DPO keeps
  existing commitments with their current owners. They stay readable under
  their old (retired) unit.
- Delete anything. `Remove` on the Directory page is refused for any unit still
  referenced anywhere; retire it instead.
