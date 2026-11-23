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
                 {"name": "Name as in the DPO", "unit": "AU"}]
    }

What it does (docs/ORG_RESTRUCTURE_ASSESSMENT.md, Phase 2):
  * reused units keep their id (staff, history and references follow them) and
    are moved/renamed into place; missing plan units are created;
  * with "create_missing": true, a listed name that has NO directory record is
    added as a new internal staff record (ambiguous names still stop the run);
  * listed staff move to their new unit (designation updated when given; a former
    lead listed as a member loses the lead title). Names are matched tolerantly
    (order, accents, titles, middle initials, small typos); an unknown or
    ambiguous name stops the run and is reported with the candidates;
  * listed old units are RETIRED, never deleted -- retiring refuses while
    current staff remain there; an acting OIC set on a retiring unit is cleared
    (and logged), since that seat no longer exists;
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
from directory_restructure import (  # noqa: E402,F401  (re-exported for tests and callers)
    DEFAULT_PLAN, PLAN_ROOT, build, load_plan, _name_score, _name_tokens, _person)


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
