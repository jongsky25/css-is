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
    current staff or an acting OIC remain there;
  * open Work, documents, approvals and supplies are NOT reassigned: the
    transition rule keeps existing commitments with their current owners;
  * reports active document routing rules that still point at retired units,
    which an administrator must re-map.
"""
from __future__ import annotations

import argparse
import json
import re
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


# Titles and credentials that never identify a person ("Dr. ... MD, MPH").
_NOISE = set("dr dra mr ms mrs miss engr atty prof hon sir maam doc md mph msc mba mpm mpa "
             "rn rmt rph phd ceso iii iv jr sr".split())


# Common Filipino name abbreviations, written either way in official lists.
_ALIASES = {"ma": "maria", "ma.": "maria", "jo": "jose"}


def _name_tokens(name):
    """Comparable name tokens: accents folded (Reñeva -> reneva), punctuation and
    titles/credentials dropped, single-letter middle initials ignored."""
    import unicodedata
    text = unicodedata.normalize("NFKD", str(name or "")).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"[^a-z ]", " ", text.replace("-", " "))
    return [_ALIASES.get(t, t) for t in text.split() if len(t) > 1 and t not in _NOISE]


def _name_score(a, b):
    """0..1 likeness of two names in any order ("Canares, Rustom" = "Rustom Cañares").
    Tokens match when spelled within a typo ("Ralie"/"Raile"); every token of the
    shorter name must match, and at least two must."""
    from difflib import SequenceMatcher
    ta, tb = _name_tokens(a), _name_tokens(b)
    if not ta or not tb:
        return 0.0
    short, long_ = (ta, tb) if len(ta) <= len(tb) else (tb, ta)
    pool, hits = list(long_), 0
    for t in short:
        best = max(pool, key=lambda u: SequenceMatcher(None, t, u).ratio(), default=None)
        if best is not None and SequenceMatcher(None, t, best).ratio() >= 0.7:
            pool.remove(best)
            hits += 1
    if hits < min(2, len(short)) or hits < len(short):
        return 0.0
    return 0.9 + 0.1 * hits / len(long_)


def _person(conn, entry, people=None):
    """(rp_id, name) of the current internal staff record an entry means: by rp_id,
    else the single best name match. Raises LookupError naming the candidates when
    the name is unknown or ambiguous -- never a guess."""
    if entry.get("rp_id"):
        row = conn.execute("SELECT id, name FROM resource_person WHERE id=? AND is_internal=1 "
                           "AND archived_at IS NULL", (int(entry["rp_id"]),)).fetchone()
        if not row:
            raise LookupError(f"No current internal staff record #{entry['rp_id']}.")
        return row
    if people is None:
        people = conn.execute("SELECT id, name FROM resource_person WHERE is_internal=1 "
                              "AND archived_at IS NULL").fetchall()
    scored = sorted(((_name_score(entry.get("name"), n), i, n) for i, n in people), reverse=True)
    scored = [x for x in scored if x[0] > 0]
    if not scored:
        raise LookupError(f"No current staff record matches {entry.get('name')!r}.")
    if len(scored) > 1 and scored[1][0] >= scored[0][0] - 0.02:
        raise LookupError(f"{entry.get('name')!r} matches more than one record: "
                          + ", ".join(f"#{i} {n}" for _s, i, n in scored[:3]) + ". Use rp_id.")
    return scored[0][1], scored[0][2]


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

    people = conn.execute("SELECT id, name FROM resource_person WHERE is_internal=1 "
                          "AND archived_at IS NULL").fetchall()
    problems, placed = [], {}
    for entry in mapping.get("staff") or []:
        if entry.get("unit") not in ids:
            problems.append(f"{entry.get('name') or entry.get('rp_id')!r}: unknown unit {entry.get('unit')!r}.")
            continue
        try:
            rp_id, name = _person(conn, entry, people)
        except LookupError as exc:
            # Opt-in: a DPO name with NO directory record at all becomes a new
            # internal staff record. An ambiguous name never does.
            if not (mapping.get("create_missing") and entry.get("name") and str(exc).startswith("No current")):
                problems.append(str(exc))
                continue
            name = entry["name"].strip()
            rp_id = conn.execute("INSERT INTO resource_person(name, is_internal, org_unit_id) VALUES (?,1,?)",
                                 (name, ids[entry["unit"]])).lastrowid
            log.append(f"NEW    #{rp_id} {name} (no directory record; created)")
        if rp_id in placed:
            problems.append(f"#{rp_id} {name} is listed twice ({placed[rp_id]} and {entry['unit']}).")
            continue
        placed[rp_id] = entry["unit"]
        conn.execute("UPDATE resource_person SET org_unit_id=? WHERE id=?", (ids[entry["unit"]], rp_id))
        line = f"STAFF  #{rp_id} {name} -> {entry['unit']}"
        if entry.get("designation") is not None:
            conn.execute("UPDATE resource_person SET designation=? WHERE id=?",
                         (entry["designation"].strip() or None, rp_id))
            line += f" as {entry['designation']!r}"
        else:
            # Only the listed leads lead in the new structure: a former section head
            # or chief placed as a member loses that title (and the approvals it
            # carries); any other designation is kept.
            old = conn.execute("SELECT designation FROM resource_person WHERE id=?", (rp_id,)).fetchone()[0]
            if old and st._org_rank(old, None) >= 1:
                conn.execute("UPDATE resource_person SET designation=NULL WHERE id=?", (rp_id,))
                line += f" (lead title {old!r} cleared)"
        log.append(line)
    if problems:
        raise ValueError("Staff could not be matched:\n  - " + "\n  - ".join(problems))

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
