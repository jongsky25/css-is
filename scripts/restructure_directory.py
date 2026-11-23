"""Restructure the Office Connect directory to a new bureau structure.

Dry run by default: prints exactly what would change and touches nothing.
`--apply` first writes a sibling backup of the database, then makes every
change in ONE transaction (all or nothing).

    .venv/bin/python scripts/restructure_directory.py --db PATH \
        --mapping PRIVATE.json [--plan docs/org/blhsd_interim_structure_2026.json] [--apply]

The plan (committed, no names) lists the target units by key, parent and path.
The mapping (PRIVATE -- holds staff names/ids; never commit it) says how the
current directory moves onto the plan:

    {
      "bureau_path": "BLHSD",                       # live bureau root path
      "reuse":  {"BLHSD/OD": "OD4", "BLHSD/ADMIN": "AU"},   # existing unit -> plan key
      "retire": ["BLHSD/HSDD/S1", "BLHSD/HSDD", ...],       # old units kept as history
      "staff":  [{"rp_id": 12, "unit": "S7", "designation": "Section Head"},
                 {"name": "Exact Directory Name", "unit": "AU"}]
    }

What it does (docs/ORG_RESTRUCTURE_ASSESSMENT.md, Phase 2):
  * reused units keep their id (staff, history and references follow them) and
    are moved/renamed into place; missing plan units are created;
  * listed staff move to their new unit (designation updated when given);
  * listed old units are RETIRED, never deleted -- retiring refuses while
    current staff or an acting OIC remain there;
  * open Work, documents, approvals and supplies are NOT reassigned: the
    transition rule keeps existing commitments with their current owners;
  * reports active document routing rules that still point at retired units,
    which an administrator must re-map.
"""
from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

import storage as st  # noqa: E402

DEFAULT_PLAN = os.path.join(ROOT, "docs", "org", "blhsd_interim_structure_2026.json")
PLAN_ROOT = "BLHSD"


def _target_path(bureau_path, plan_path):
    if plan_path != PLAN_ROOT and not plan_path.startswith(PLAN_ROOT + "/"):
        raise ValueError(f"Plan path {plan_path} is not under {PLAN_ROOT}.")
    return bureau_path + plan_path[len(PLAN_ROOT):]


def _ordered(units):
    """Plan units parents-first (by path depth), so a parent exists before its children."""
    return sorted(units, key=lambda u: (u["path"].count("/"), u["path"]))


def _unit_by_path(conn, path):
    row = conn.execute("SELECT id, name, short_name, level, retired_at FROM org_unit WHERE path=?",
                       (path,)).fetchone()
    return dict(zip(("id", "name", "short_name", "level", "retired_at"), row)) if row else None


def _person(conn, entry):
    if entry.get("rp_id"):
        row = conn.execute("SELECT id, name FROM resource_person WHERE id=? AND is_internal=1 "
                           "AND archived_at IS NULL", (int(entry["rp_id"]),)).fetchone()
    else:
        found = conn.execute("SELECT id, name FROM resource_person WHERE name=? AND is_internal=1 "
                             "AND archived_at IS NULL", (entry.get("name") or "",)).fetchall()
        if len(found) > 1:
            raise ValueError(f"More than one current staff record is named {entry.get('name')!r}; use rp_id.")
        row = found[0] if found else None
    if not row:
        raise ValueError(f"No current internal staff record for {entry!r}.")
    return row


def build(conn, plan, mapping, log):
    """Apply the plan inside the caller's transaction. Raises on any problem."""
    bureau = conn.execute("SELECT id, path FROM org_unit WHERE level='bureau' ORDER BY id LIMIT 1").fetchone()
    if not bureau:
        raise ValueError("The directory has no bureau unit.")
    bureau_path = mapping.get("bureau_path") or bureau[1]
    if bureau_path != bureau[1]:
        raise ValueError(f"Mapping bureau_path {bureau_path!r} does not match the live bureau path {bureau[1]!r}.")
    units = {u["key"]: u for u in plan["units"]}
    reuse = {key: old for old, key in (mapping.get("reuse") or {}).items()}
    unknown = [k for k in reuse if k not in units]
    if unknown:
        raise ValueError(f"Mapping reuses unknown plan keys: {unknown}")

    ids = {}
    for u in _ordered(plan["units"]):
        target = _target_path(bureau_path, u["path"])
        parent_path = target.rsplit("/", 1)[0]
        parent = _unit_by_path(conn, parent_path)
        if not parent:
            raise ValueError(f"Parent {parent_path} of {u['key']} does not exist.")
        segment = target.rsplit("/", 1)[1]
        existing = _unit_by_path(conn, target)
        if u["key"] in reuse and not existing:
            old = _unit_by_path(conn, reuse[u["key"]])
            if not old:
                raise ValueError(f"Reused unit {reuse[u['key']]} does not exist.")
            st.move_org_unit(conn, old["id"], parent["id"], segment, commit=False)
            log.append(f"MOVE   {reuse[u['key']]} -> {target}")
            existing = _unit_by_path(conn, target)
        if existing:
            if existing["retired_at"]:
                st.restore_org_unit(conn, existing["id"], commit=False)
                log.append(f"RESTORE {target}")
            if (existing["name"], existing["short_name"], existing["level"]) != (u["name"], u["key"], u["level"]):
                conn.execute("UPDATE org_unit SET name=?, short_name=?, level=? WHERE id=?",
                             (u["name"], u["key"], u["level"], existing["id"]))
                log.append(f"UPDATE {target}: {existing['name']!r} ({existing['level']}) -> {u['name']!r} ({u['level']})")
            ids[u["key"]] = existing["id"]
        else:
            ids[u["key"]] = conn.execute(
                "INSERT INTO org_unit(name, short_name, level, path) VALUES (?,?,?,?)",
                (u["name"], u["key"], u["level"], target)).lastrowid
            log.append(f"CREATE {target} [{u['level']}] {u['name']}")

    for entry in mapping.get("staff") or []:
        if entry.get("unit") not in ids:
            raise ValueError(f"Staff entry names unknown unit {entry.get('unit')!r}.")
        rp_id, name = _person(conn, entry)
        conn.execute("UPDATE resource_person SET org_unit_id=? WHERE id=?", (ids[entry["unit"]], rp_id))
        if entry.get("designation") is not None:
            conn.execute("UPDATE resource_person SET designation=? WHERE id=?",
                         (entry["designation"].strip() or None, rp_id))
        log.append(f"STAFF  #{rp_id} -> {entry['unit']}"
                   + (f" as {entry['designation']!r}" if entry.get("designation") is not None else ""))

    retired = []
    for path in sorted(mapping.get("retire") or [], key=lambda p: -p.count("/")):
        unit = _unit_by_path(conn, path)
        if not unit:
            raise ValueError(f"Unit to retire {path} does not exist.")
        if path in {_target_path(bureau_path, u["path"]) for u in plan["units"]}:
            raise ValueError(f"{path} is part of the new structure; it cannot be retired.")
        try:
            st.retire_org_unit(conn, unit["id"], commit=False)
        except ValueError as exc:
            raise ValueError(f"Cannot retire {path}: {exc}") from exc
        retired.append(unit["id"])
        refs = st.org_unit_references(conn, unit["id"])
        log.append(f"RETIRE {path}" + (f" (history kept: {', '.join(f'{t}={n}' for t, n in sorted(refs.items()))})" if refs else ""))

    has_rules = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='document_rule_version'").fetchone()
    if retired and has_rules:
        for rid, name, body in conn.execute(
                "SELECT id, name, body_json FROM document_rule_version WHERE state='active'").fetchall():
            data = json.loads(body or "{}")
            hits = sorted(set(data.get("unit_ids") or []) | ({data["lead_unit_id"]} if data.get("lead_unit_id") else set()))
            stale = [u for u in hits if u in retired]
            if stale:
                log.append(f"REMAP  routing rule #{rid} {name!r} still targets retired unit id(s) {stale}")
    return ids


def backup(db_path):
    dst = f"{db_path}.pre-restructure-{datetime.now():%Y%m%d_%H%M%S}.db"
    src, out = sqlite3.connect(db_path), sqlite3.connect(dst)
    try:
        with out:
            src.backup(out)
    finally:
        src.close()
        out.close()
    return dst


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--db", required=True, help="SQLite database to restructure (no default, on purpose)")
    ap.add_argument("--plan", default=DEFAULT_PLAN)
    ap.add_argument("--mapping", required=True, help="PRIVATE mapping JSON (holds staff; never commit)")
    ap.add_argument("--apply", action="store_true", help="write the changes (default: dry run)")
    args = ap.parse_args(argv)
    if not os.path.exists(args.db):
        ap.error(f"{args.db} does not exist")
    with open(args.plan, encoding="utf-8") as f:
        plan = json.load(f)
    with open(args.mapping, encoding="utf-8") as f:
        mapping = json.load(f)

    saved = backup(args.db) if args.apply else None
    conn = st.connect(args.db)
    st.init_db(conn)
    log = []
    try:
        conn.execute("BEGIN IMMEDIATE")
        build(conn, plan, mapping, log)
        if args.apply:
            conn.commit()
        else:
            conn.rollback()
    except Exception as exc:
        conn.rollback()
        print("\n".join(log))
        print(f"\nSTOPPED, nothing changed: {exc}", file=sys.stderr)
        return 2
    finally:
        conn.close()
    print("\n".join(log) or "Nothing to change.")
    print(f"\nApplied. Backup: {saved}" if args.apply else "\nDry run only: nothing was written. Re-run with --apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
