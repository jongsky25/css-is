"""Directory restructure engine (docs/ORG_RESTRUCTURE_ASSESSMENT.md, Phase 2).

Shared by the admin page (/admin/restructure, restructure_routes.py) and the
command-line wrapper scripts/restructure_directory.py. `build` applies a plan and
a private staff mapping inside the CALLER's transaction; the caller commits
(apply) or rolls back (preview). See the runbook: docs/ORG_RESTRUCTURE_RUNBOOK.md.
"""
from __future__ import annotations

import json
import os
import re

import storage as st

DEFAULT_PLAN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "docs", "org", "blhsd_interim_structure_2026.json")
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


_EMAIL = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def _set_email(conn, rp_id, email, is_new):
    """Give a staff record its email only when the record is new, or not yet in
    use: it has no email of its own and no active account (owner rule). Never
    overwrites, and never reuses an address another current record holds."""
    if not _EMAIL.fullmatch(email):
        raise ValueError(f"Not an email address: {email!r}.")
    current = conn.execute("SELECT email FROM resource_person WHERE id=?", (rp_id,)).fetchone()[0]
    active = conn.execute("SELECT 1 FROM admin_user WHERE rp_id=? AND active=1", (rp_id,)).fetchone()
    if not is_new and ((current or "").strip() or active):
        return " (email kept: record already in use)"
    taken = conn.execute("SELECT id FROM resource_person WHERE lower(email)=? AND id<>? AND archived_at IS NULL",
                         (email, rp_id)).fetchone()
    if taken:
        return f" (email not set: {email} already belongs to record #{taken[0]})"
    conn.execute("UPDATE resource_person SET email=? WHERE id=?", (email, rp_id))
    return f" email {email}"


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
    problems, placed, created = [], {}, set()
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
            created.add(rp_id)
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
        email = (entry.get("email") or "").strip().lower()
        if email:
            note = _set_email(conn, rp_id, email, rp_id in created)
            if note:
                line += note
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
        oic = conn.execute("SELECT so.admin_user_id, COALESCE(rp.name, a.username) FROM section_oic so "
                           "JOIN admin_user a ON a.id = so.admin_user_id LEFT JOIN resource_person rp ON rp.id = a.rp_id "
                           "WHERE so.org_unit_id=?", (unit["id"],)).fetchone()
        if oic:
            # An acting OIC of a unit that is going away covers a seat nobody reports
            # to any more; set OICs again on the new units where still needed.
            conn.execute("DELETE FROM section_oic WHERE org_unit_id=?", (unit["id"],))
            log.append(f"CLEAR  acting OIC of {path} (account #{oic[0]} {oic[1]}): the unit is retired")
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


def load_plan(path=None):
    with open(path or DEFAULT_PLAN, encoding="utf-8") as f:
        return json.load(f)
