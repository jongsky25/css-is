"""Applying a reviewed Word-calendar import (docs/OFFICE_CALENDAR_PLAN.md §9, B2).

`calendar_import.parse` guesses; a person reviews; this module turns the reviewed
drafts into calendar entries. Three rules keep it safe to run:

  * ALL-OR-NOTHING VALIDATION. Every ticked row is validated before the first is
    written (`storage.cal_create` commits per row, so a bad row discovered halfway
    would leave a half-import). Any error and nothing is written.
  * IDEMPOTENT. A draft whose `import_key` is already in the calendar is counted as
    "already there" and left alone — re-uploading the same file, or importing a
    batch twice, creates nothing new and never overwrites an edit made since.
  * ONE AUDIT LINE for the whole batch, not 380.

Colours: the Word legend names an OWNER (Bureau, Section 1-5); the app owns UNITS.
The mapping between them is chosen once here, remembered, and also written as the
unit colours the calendar draws (`calendar_unit_tones`, read by office_calendar).
"""
from __future__ import annotations

import json
import re

import calendar_import as ci
import calendar_people as cp
import storage as st

OWNER_TONES = {"bureau": "green", "s1": "yellow", "s2": "magenta",
               "s3": "orange", "s4": "cyan", "s5": "blue"}
_MAP_SETTING = "calendar_import_owner_units"       # JSON {owner key: org_unit id}
_TONES_SETTING = "calendar_unit_tones"             # JSON {org_unit id: tone}  (office_calendar)
IMPORT_KINDS = ("meeting", "training", "travel", "deadline", "audit_mr", "banner")
IMPORT_AUDIENCES = ("bureau", "unit")


def saved_mapping(conn):
    try:
        raw = json.loads(st.get_setting(conn, _MAP_SETTING) or "{}")
    except ValueError:
        raw = {}
    return {k: int(v) for k, v in raw.items() if k in ci.OWNERS and str(v).isdigit()}


def guess_mapping(conn):
    """owner key -> org_unit id: what was chosen last time, else a best guess from
    the unit names ("Section 3", "Sec 3", "... III"). Anything unsure stays unset."""
    out = dict(saved_mapping(conn))
    units = conn.execute("SELECT id, name, COALESCE(short_name, ''), level FROM org_unit").fetchall()
    for key in ci.OWNERS:
        if key in out:
            continue
        if key == "bureau":
            hit = [u for u in units if u[3] == "bureau"]
        else:
            n = key[1]
            rx = re.compile(rf"\b(section|sec\.?)\s*{n}\b|\bs{n}\b", re.I)
            hit = [u for u in units if u[3] == "section" and (rx.search(u[1]) or rx.search(u[2]))]
        if len(hit) == 1:
            out[key] = hit[0][0]
    return out


def _needs(d):
    """Why a draft wants a person's eyes: the parser's own warnings plus a status that is not
    plain "confirmed". No owner colour is the commonest reason and is shown by its own marker."""
    out = [w for w in d["warnings"] if not w.startswith("No owner")]
    if d["status"] != "confirmed":
        out.append(d["status"].capitalize() + " in the Word file.")
    return out


def review_rows(drafts, existing, posted=None, suggestions=None):
    """One row per draft for the review table. `posted` (the submitted form, after a
    validation error) wins over the parser's guesses so nothing the person typed is lost.
    `suggestions` is the batch's {"owners": {"<index>": {owner, why}}}: shown next to the row,
    never filled in. A row is `clean` when nothing about it needs a person's attention."""
    owners = (suggestions or {}).get("owners", {})
    rows = []
    for i, d in enumerate(drafts):
        p = posted or {}
        have = d["import_key"] in existing
        owner = p.get(f"owner_{i}", d["owner"] or "")
        needs = _needs(d)
        rows.append({
            "i": i, "d": d, "existing": have,
            "include": (f"inc_{i}" in p) if posted is not None else not have,
            "title": p.get(f"title_{i}", d["title"]), "kind": p.get(f"kind_{i}", d["kind"]),
            "status": p.get(f"status_{i}", d["status"]), "owner": owner,
            "start": p.get(f"start_{i}", d["start_date"]), "end": p.get(f"end_{i}", d["end_date"] or ""),
            "month": d["start_date"][:7],
            "needs": needs, "no_owner": not d["owner"],
            "suggest": owners.get(str(i)) if not d["owner"] else None,
            "clean": not needs and bool(d["owner"]) and not have,
        })
    return rows


def apply(conn, batch, posted, by):
    """(result, errors). `posted` is the review form as a flat {name: value} dict."""
    drafts = batch["payload"]["drafts"]
    errors = []

    mapping = {}
    for key in ci.OWNERS:
        v = posted.get(f"map_{key}", "")
        if v.isdigit():
            if conn.execute("SELECT 1 FROM org_unit WHERE id=?", (int(v),)).fetchone() is None:
                errors.append(f"{ci.OWNER_LABELS[key]}: that unit no longer exists.")
            else:
                mapping[key] = int(v)
    used = {}
    for key, uid in mapping.items():
        if uid in used:
            errors.append(f"{ci.OWNER_LABELS[used[uid]]} and {ci.OWNER_LABELS[key]} are both set "
                          "to the same unit; each colour needs its own.")
        used[uid] = key
    audience = posted.get("audience", "bureau")
    if audience not in IMPORT_AUDIENCES:
        errors.append("Choose who can see the imported items.")

    existing = st.cal_existing_import_keys(conn, [d["import_key"] for d in drafts])
    rows, no_unit = [], 0
    for i, d in enumerate(drafts):
        if f"inc_{i}" not in posted:
            continue
        label = f"Row {i + 1} ({d['start_date']}, {d['title'][:40]})"
        if d["import_key"] in existing:
            rows.append(("already", i, None, None))
            continue
        owner = posted.get(f"owner_{i}", "")
        if owner and owner not in ci.OWNERS:
            errors.append(f"{label}: unknown owner.")
            continue
        kind, status = posted.get(f"kind_{i}", d["kind"]), posted.get(f"status_{i}", d["status"])
        if kind not in IMPORT_KINDS:
            errors.append(f"{label}: pick a type from the list.")
            continue
        if status not in ("confirmed", "tentative", "postponed"):
            errors.append(f"{label}: pick a status from the list.")
            continue
        unit = mapping.get(owner) if owner else None
        if owner and unit is None:
            no_unit += 1
        aud = "unit" if audience == "unit" and unit else "bureau"
        try:
            fields = st.cal_validate(
                posted.get(f"title_{i}", ""), posted.get(f"start_{i}", ""),
                end_date=posted.get(f"end_{i}", "") or None, kind=kind, status=status,
                start_time=d["start_time"], end_time=d["end_time"], time_note=d["time_note"],
                modality=d["modality"], audience=aud,
                meeting_url=d.get("meeting_url"))
        except ValueError as e:
            errors.append(f"{label}: {e}.")
            continue
        rows.append(("new", i, fields, (unit, d["import_key"], d["tags"])))
    if errors:
        return None, errors

    created, already = [], 0
    for state, i, fields, extra in rows:
        if state == "already":
            already += 1
            continue
        unit, key, tags = extra
        title, start = fields.pop("title"), fields.pop("start_date")
        eid = st.cal_create(conn, title, start, owner_org_id=unit, source="import",
                            import_key=key, tags=tags, by=by, audit_it=False, **fields)
        created.append({"i": i, "entry_id": eid})
    _remember(conn, mapping)
    result = {"created": created, "already": already, "unmapped_owner": no_unit,
              "not_selected": len(drafts) - len(rows)}
    st.cal_import_finish(conn, batch["id"], result)
    st.audit(conn, by, "calendar_import", target_type="calendar_import_batch",
             target_id=batch["id"],
             summary=f"Imported {len(created)} calendar items from {batch['filename']} "
                     f"({already} already there)")
    return result, []


def _remember(conn, mapping):
    """Keep the owner->unit choice for next time, and give each mapped unit its legend
    colour on the calendar (leaving every other unit's colour alone)."""
    st.set_setting(conn, _MAP_SETTING, json.dumps(mapping))
    try:
        tones = json.loads(st.get_setting(conn, _TONES_SETTING) or "{}")
    except ValueError:
        tones = {}
    tones.update({str(uid): OWNER_TONES[key] for key, uid in mapping.items()})
    st.set_setting(conn, _TONES_SETTING, json.dumps(tones))


# ── the people step (B3) ───────────────────────────────────────────────────────

_ALIASES = "calendar_people_aliases"        # JSON {name key: user id}  (remembered answers)
_IGNORED = "calendar_people_ignored"        # JSON [name key]           (places, initialisms, ...)


def _json_setting(conn, key, default):
    try:
        v = json.loads(st.get_setting(conn, key) or "")
    except ValueError:
        return default
    return v if isinstance(v, type(default)) else default


def people_state(conn, batch):
    """(rows for the page, directory) — every name used by the items this batch created."""
    directory = cp.load_directory(conn)
    aliases = {k: int(v) for k, v in _json_setting(conn, _ALIASES, {}).items()}
    ignored = set(_json_setting(conn, _IGNORED, []))
    result = batch["result"] or {"created": []}
    created = {c["i"]: c["entry_id"] for c in result["created"]}
    rows = cp.collect(batch["payload"]["drafts"], created, directory, aliases, ignored,
                      result.get("people", {}))
    return rows, directory


def apply_people(conn, batch, posted, by):
    """Write the confirmed decisions. `posted` maps `who_<key>` to "" (decide later),
    "ignore" (not a person) or a user id. Returns {added, items, remembered, ignored}.
    Safe to run again: people already on an item are skipped, and a name left undecided
    stays on the list."""
    rows, directory = people_state(conn, batch)
    by_key = {r["key"]: r for r in rows}
    valid = {p["user_id"] for p in directory}
    result = batch["result"]
    created = {c["i"]: c["entry_id"] for c in result["created"]}
    drafts = batch["payload"]["drafts"]
    aliases = {k: int(v) for k, v in _json_setting(conn, _ALIASES, {}).items()}
    ignored = set(_json_setting(conn, _IGNORED, []))
    decided = dict(result.get("people", {}))
    added = touched = remembered = n_ignored = 0
    for key, row in by_key.items():
        dec = posted.get(f"who_{key}", "")
        if dec == "ignore":
            ignored.add(key); decided[key] = "ignore"; n_ignored += 1
            continue
        if not dec.isdigit() or int(dec) not in valid:
            continue
        uid = int(dec)
        for i in row["drafts"]:
            eid = created.get(i)
            if eid is None:
                continue
            role = "travel" if drafts[i]["kind"] == "travel" else "attending"
            n = st.cal_add_people(conn, eid, [(uid, role)], by=by, mark_seen=True)
            added += n
            touched += 1 if n else 0
        aliases[key] = uid; decided[key] = uid; remembered += 1
    st.set_setting(conn, _ALIASES, json.dumps(aliases))
    st.set_setting(conn, _IGNORED, json.dumps(sorted(ignored)))
    result["people"] = decided
    st.cal_import_set_result(conn, batch["id"], result)
    if added or remembered or n_ignored:
        st.audit(conn, by, "calendar_import_people", target_type="calendar_import_batch",
                 target_id=batch["id"],
                 summary=f"Matched names to people: {added} people added to {touched} items, "
                         f"{remembered} names remembered, {n_ignored} marked not a person")
    return {"added": added, "items": touched, "remembered": remembered, "ignored": n_ignored}
