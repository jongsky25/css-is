"""Office calendar — the layer registry and the SCOPE rules.

ONE function, `items_between`, is what every calendar consumer calls (the
/calendar page, the home card, ICS, emails, the bell, a later API). Each source
of dates is a PROVIDER registered in `LAYERS`; a provider turns its rows into the
one plain-dict `CalItem` shape documented below. See docs/OFFICE_CALENDAR_PLAN.md
§2 (architecture) and §3 (data model).

SCOPE IS THE SAFETY-CRITICAL PART. Who may SEE an item is decided here, once,
before any provider's output reaches a caller, and it never depends on what the
caller asked for:

  * VISIBILITY (what you are allowed to see) comes from the DIRECTORY, through
    `storage.team_scope_for_user`, exactly like the Office Connect landing page.
    An account with no directory link resolves to kind "none" and sees only
    bureau-audience items plus the ones it is personally listed on or created.
    An `admin` role buys nothing here.
  * SCOPE (what you asked to look at: mine / section / division / bureau) can only
    NARROW the visible set, never widen it.

Entry audience rules (calendar_entry.audience):
  bureau  every signed-in user.
  unit    people inside the owning unit's subtree, plus anyone whose team scope
          contains the owning unit (a chief sees what sits below them). An entry
          with no owner unit is visible only to its own people.
  people  only the listed attendees and the creator — not even the bureau-wide
          viewer. (Whoever is named on an entry always sees it, whatever its
          audience.)

Dates are ISO strings ('YYYY-MM-DD') so items are JSON-ready for the later API.
"""
from __future__ import annotations

from datetime import date

import storage as st

SCOPES = ("blend", "mine", "section", "division", "bureau")
DEFAULT_SCOPE = "blend"            # mine + bureau-wide

# Colour tokens for the owner unit (the Word legend): the template resolves a
# token to a CSS variable; this module never emits a colour value.
UNIT_TONES = ("green", "yellow", "magenta", "orange", "cyan", "blue", "grey")
_TONES_SETTING = "calendar_unit_tones"      # JSON {org_unit_id: tone}, set by the importer (B2)


# ── viewer context ───────────────────────────────────────────────────────────

def _ancestors(path):
    """'A/B/C' -> ['A/B/C', 'A/B', 'A'] (the unit and every unit above it)."""
    out, parts = [], (path or "").split("/") if path else []
    while parts:
        out.append("/".join(parts))
        parts.pop()
    return out


def viewer_context(conn, user):
    """Who is looking, resolved ONCE from the directory.

    kind        "bureau" | "unit" | "none"   (storage.team_scope_for_user)
    scope_path  the team subtree path, or None for bureau/none
    section_path / division_path
                the viewer's own section (their unit) and the division above it;
                None when they have no unit / no division."""
    scope_path, kind = st.team_scope_for_user(conn, user)
    ctx = {"user_id": user["id"], "username": user.get("username"),
           "kind": kind, "scope_path": scope_path,
           "section_path": None, "division_path": None}
    row = conn.execute("""
        SELECT ou.path FROM admin_user a
        JOIN resource_person rp ON rp.id = a.rp_id
        JOIN org_unit ou ON ou.id = rp.org_unit_id
        WHERE a.id = ? AND rp.archived_at IS NULL LIMIT 1""", (user["id"],)).fetchone()
    if row and row[0]:
        ctx["section_path"] = row[0]
        levels = dict(conn.execute(
            "SELECT path, level FROM org_unit WHERE path IN (%s)"
            % ",".join("?" * len(_ancestors(row[0]))), _ancestors(row[0])))
        for p in _ancestors(row[0]):
            if levels.get(p) == "division":
                ctx["division_path"] = p
                break
    return ctx


# ── small lookups shared by providers ────────────────────────────────────────

def _initials(name):
    parts = [p for p in (name or "").replace(".", " ").split() if p]
    return ("".join(p[0] for p in parts[:2]) or "?").upper()


def _units(conn, ids):
    """{org_unit_id: {path, label, level}} for the owner units in play."""
    ids = sorted({i for i in ids if i})
    if not ids:
        return {}
    rows = conn.execute(
        "SELECT id, path, COALESCE(NULLIF(short_name,''), name), level FROM org_unit "
        "WHERE id IN (%s)" % ",".join("?" * len(ids)), ids)
    return {r[0]: {"path": r[1], "label": r[2], "level": r[3]} for r in rows}


def _tone_map(conn):
    import json
    try:
        raw = json.loads(st.get_setting(conn, _TONES_SETTING) or "{}")
    except ValueError:
        raw = {}
    return {int(k): v for k, v in raw.items() if v in UNIT_TONES and str(k).isdigit()}


def _tone(unit, unit_id, tones):
    if unit_id in tones:
        return tones[unit_id]
    return "green" if unit and unit["level"] == "bureau" else "grey"


def _people_cards(conn, user_ids):
    """{user_id: {name, initials, photo_url}} for the attendees shown on cards."""
    ids = sorted({i for i in user_ids if i})
    if not ids:
        return {}
    out = {}
    for uid, uname, rp_id, rp_name, has_photo in conn.execute(
            "SELECT a.id, a.username, a.rp_id, rp.name, (rp.photo IS NOT NULL) "
            "FROM admin_user a LEFT JOIN resource_person rp ON rp.id = a.rp_id "
            "WHERE a.id IN (%s)" % ",".join("?" * len(ids)), ids):
        name = rp_name or uname
        out[uid] = {"name": name, "initials": _initials(name),
                    "photo_url": f"/photo/{rp_id}" if rp_id and has_photo else None}
    return out


# ── visibility + scope ───────────────────────────────────────────────────────

def _under(path, root):
    """Is `path` the unit `root` or inside it?"""
    return bool(path and root) and (path == root or path.startswith(root + "/"))


def entry_visible(ctx, entry, owner_path):
    """May this viewer see this entry at all? (Independent of the scope asked for.)"""
    listed = {p["user_id"] for p in entry["people"]}
    if ctx["user_id"] in listed or (ctx["username"] and entry["created_by"] == ctx["username"]):
        return True                               # your own items, whatever the audience
    audience = entry["audience"]
    if audience == "bureau":
        return True
    if audience == "people" or ctx["kind"] == "none":
        return False
    # audience == "unit": it must belong to a unit, or nobody outside its people sees it
    if not owner_path:
        return False
    if ctx["kind"] == "bureau":
        return True
    mine = ctx["section_path"]
    return _under(mine, owner_path) or _under(owner_path, ctx["scope_path"])


def _in_scope(ctx, scope, entry, owner_path):
    """Does a VISIBLE entry fall inside the scope the viewer asked for?"""
    mine = (ctx["user_id"] in {p["user_id"] for p in entry["people"]}
            or (bool(ctx["username"]) and entry["created_by"] == ctx["username"]))
    bureau_wide = entry["audience"] == "bureau"
    if scope == "bureau":
        return True
    if scope == "mine":
        return mine
    if scope == "blend":
        return mine or bureau_wide
    root = ctx["section_path"] if scope == "section" else ctx["division_path"]
    # a section/division view is that unit's own items, plus what is bureau-wide
    return _under(owner_path, root) or bureau_wide


# ── providers ────────────────────────────────────────────────────────────────

def _entries_layer(conn, ctx, start, end, scope):
    entries = st.cal_list_between(conn, start, end)
    units = _units(conn, [e["owner_org_id"] for e in entries])
    tones = _tone_map(conn)
    cards = _people_cards(conn, [p["user_id"] for e in entries for p in e["people"]])
    out = []
    for e in entries:
        unit = units.get(e["owner_org_id"])
        path = unit["path"] if unit else None
        if not entry_visible(ctx, e, path) or not _in_scope(ctx, scope, e, path):
            continue
        out.append({
            "key": f"entry:{e['id']}", "layer": "entries", "title": e["title"],
            "start": e["start_date"], "end": e["end_date"] or e["start_date"],
            "start_time": e["start_time"], "end_time": e["end_time"],
            "all_day": e["start_time"] is None, "time_note": e["time_note"],
            "kind": e["kind"], "status": e["status"],
            "owner_org_id": e["owner_org_id"],
            "owner_label": unit["label"] if unit else None,
            "tone": _tone(unit, e["owner_org_id"], tones),
            "people": [{"user_id": p["user_id"], "role": p["role"],
                        **cards.get(p["user_id"], {"name": "", "initials": "?",
                                                   "photo_url": None})}
                       for p in e["people"]],
            "tags": e["tags"], "venue": e["venue"], "modality": e["modality"],
            "meeting_url": e["meeting_url"], "url": f"/calendar/entries/{e['id']}",
            "css": None,
            "flags": [e["status"]] if e["status"] in ("tentative", "postponed") else [],
            "editable": True, "private": False,
        })
    return out


def _holidays_layer(conn, ctx, start, end, scope):
    """Holidays and work suspensions: shown to everyone, in every scope."""
    out = []
    for iso, h in sorted(st.holidays_between(
            conn, date.fromisoformat(start), date.fromisoformat(end)).items()):
        out.append({
            "key": f"holiday:{iso}", "layer": "holidays", "title": h["name"],
            "start": iso, "end": iso, "start_time": None, "end_time": None,
            "all_day": True, "time_note": None,
            "kind": "holiday", "status": "confirmed",
            "owner_org_id": None, "owner_label": h["kind_label"], "tone": "grey",
            "people": [], "tags": [], "venue": None, "modality": None,
            "meeting_url": None, "url": None, "css": None,
            "flags": [], "editable": False, "private": False,
            "holiday_kind": h["kind"],
        })
    return out


# name -> provider(conn, ctx, start_iso, end_iso, scope) -> [CalItem]. Later
# layers (activities, leave, birthdays, deadlines) are one line each.
LAYERS = {
    "entries": _entries_layer,
    "holidays": _holidays_layer,
}

# Within one day, what leads: the day's own banner (a holiday), then the rest.
_DISPLAY_ORDER = ("holidays", "birthdays", "deadlines", "activities", "entries", "leave")
_LAYER_ORDER = {name: i for i, name in enumerate(_DISPLAY_ORDER)}


def items_between(conn, user, start, end, *, scope=DEFAULT_SCOPE, layers=None):
    """Every calendar item `user` may see between `start` and `end` (inclusive;
    dates or ISO strings), merged across layers and sorted by day, then time.

    `scope` only narrows (see module docstring); an unknown scope raises
    ValueError rather than guessing. `layers` limits which providers run
    (default: all registered)."""
    if scope not in SCOPES:
        raise ValueError(f"scope must be one of {', '.join(SCOPES)}")
    start, end = _iso(start), _iso(end)
    if end < start:
        raise ValueError("end is before start")
    unknown = set(layers or ()) - set(LAYERS)
    if unknown:
        raise ValueError(f"unknown layer: {', '.join(sorted(unknown))}")
    ctx = viewer_context(conn, user)
    items = []
    for name, provider in LAYERS.items():
        if layers is None or name in layers:
            items.extend(provider(conn, ctx, start, end, scope))
    items.sort(key=lambda i: (i["start"], i["start_time"] or "", _LAYER_ORDER.get(i["layer"], len(_LAYER_ORDER)),
                              i["title"].lower(), i["key"]))
    return items


def _iso(d):
    return d.isoformat() if isinstance(d, date) else date.fromisoformat(str(d)).isoformat()
