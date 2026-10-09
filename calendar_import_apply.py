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


def review_rows(drafts, existing, posted=None):
    """One row per draft for the review table. `posted` (the submitted form, after a
    validation error) wins over the parser's guesses so nothing the person typed is lost."""
    rows = []
    for i, d in enumerate(drafts):
        p = posted or {}
        have = d["import_key"] in existing
        rows.append({
            "i": i, "d": d, "existing": have,
            "include": (f"inc_{i}" in p) if posted is not None else not have,
            "title": p.get(f"title_{i}", d["title"]), "kind": p.get(f"kind_{i}", d["kind"]),
            "status": p.get(f"status_{i}", d["status"]), "owner": p.get(f"owner_{i}", d["owner"] or ""),
            "start": p.get(f"start_{i}", d["start_date"]), "end": p.get(f"end_{i}", d["end_date"] or ""),
            "month": d["start_date"][:7],
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
                modality=d["modality"], audience=aud)
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
