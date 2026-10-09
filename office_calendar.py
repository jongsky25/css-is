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

from datetime import date, timedelta

import auth
import storage as st
import tzutil as tz

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
    awa_path, awa_kind = st.team_scope_for_user(conn, user, area="awa")     # who's-in visibility
    rp = conn.execute("SELECT rp_id FROM admin_user WHERE id = ?", (user["id"],)).fetchone()
    ctx = {"user_id": user["id"], "username": user.get("username"), "role": user.get("role"),
           "rp_id": rp[0] if rp else None,
           "kind": kind, "scope_path": scope_path,
           "awa_path": awa_path, "awa_kind": awa_kind,
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
        if e["event_id"]:
            continue            # an overlay on a CSS activity: the activities layer draws it, once
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


_LIFE_TEXT = {"upcoming": "registration open", "ongoing": "feedback open", "concluded": "concluded"}


def _activities_layer(conn, ctx, start, end, scope):
    """Every CSS activity (the `event` table) that overlaps the window, with no copying and
    no backfill: if it exists, it is on the calendar. The activity owns its title, dates,
    venue and format; an OVERLAY entry (calendar_entry.event_id) adds people, tags, kind and
    an audience on top and is never drawn as a second item.

    Visibility: an activity is bureau-wide information (staff register and give feedback
    through it) unless its overlay narrows the audience, in which case the overlay's rules
    (office_calendar.entry_visible) decide. Scope is separate from visibility: a section's
    view shows the activities that unit ORGANISES (or that its people spoke at), "mine" the
    ones you created, speak at or are put on, so one section's schedule is not flooded by the
    whole bureau's. Archived activities (every form put away) are not shown."""
    rows = conn.execute("""
        SELECT e.id, e.event_token, e.title, e.event_date, e.end_date, e.venue, e.modality,
               e.event_kind, e.created_by, e.lead_org_id,
               (SELECT fi.close_at FROM event_form ef JOIN form_instance fi ON fi.id = ef.form_instance_id
                  WHERE ef.event_id = e.id AND fi.survey_type = 2 LIMIT 1)
        FROM event e
        WHERE COALESCE(e.event_date, '') <> ''
          AND substr(e.event_date, 1, 10) <= ?
          AND substr(COALESCE(NULLIF(e.end_date, ''), e.event_date), 1, 10) >= ?
          AND NOT (EXISTS (SELECT 1 FROM event_form ef WHERE ef.event_id = e.id)
                   AND NOT EXISTS (SELECT 1 FROM event_form ef JOIN form_instance fi ON fi.id = ef.form_instance_id
                                    WHERE ef.event_id = e.id AND COALESCE(fi.archived, 0) = 0))
        ORDER BY e.event_date, e.id""", (end, start)).fetchall()
    if not rows:
        return []
    ids = [r[0] for r in rows]
    overlays = st.cal_overlays_for_events(conn, ids)
    units = _units(conn, [r[9] for r in rows] + [o["owner_org_id"] for o in overlays.values()])
    tones = _tone_map(conn)
    speakers = {}                                           # event id -> {rp_id: (account id or None)}
    for eid, rp_id, uid in conn.execute(
            "SELECT DISTINCT ef.event_id, fi.rp_id, a.id FROM event_form ef "
            "JOIN form_instance fi ON fi.id = ef.form_instance_id AND fi.survey_type = 3 "
            "LEFT JOIN admin_user a ON a.rp_id = fi.rp_id AND a.active = 1 "
            "WHERE ef.event_id IN (%s) AND fi.rp_id IS NOT NULL" % ",".join("?" * len(ids)), ids):
        speakers.setdefault(eid, {})[rp_id] = uid
    today, now = tz.today_local().isoformat(), tz.now_iso()
    cards = _people_cards(conn, [p["user_id"] for o in overlays.values() for p in o["people"]]
                          + [u for m in speakers.values() for u in m.values() if u])
    out = []
    for (eid, token, title, ed, end_d, venue, modality, ekind, created_by, lead_id, close_at) in rows:
        ov = overlays.get(eid)
        lead = units.get(ov["owner_org_id"] if ov and ov["owner_org_id"] else lead_id)
        path = lead["path"] if lead else None
        acct = {u for u in speakers.get(eid, {}).values() if u}
        on = {p["user_id"] for p in (ov["people"] if ov else [])} | acct
        pseudo = {"audience": (ov["audience"] if ov and ov["audience"] in ("bureau", "people") else "unit"),
                  "people": [{"user_id": u} for u in on], "created_by": created_by}
        if ov and not entry_visible(ctx, ov, path):
            continue
        mine = (ctx["user_id"] in on or (ctx["username"] and created_by == ctx["username"])
                or ctx["rp_id"] in speakers.get(eid, {}))
        if not _in_scope_activity(ctx, scope, pseudo, path, mine):
            continue
        s_iso = ed[:10]
        e_iso = (end_d or ed)[:10]
        life = st.lifecycle_of(ed, close_at, today, now, end_date=end_d or None)
        summ = st.event_registration_summary(conn, eid)
        answered = summ["completed"] + summ["unattributed"]
        chip = (f"{summ['registered']} registered" if life == "upcoming" else
                f"feedback open · {answered} answered" if life == "ongoing" else
                f"concluded · {answered} {'response' if answered == 1 else 'responses'}")
        who = {}
        for p in (ov["people"] if ov else []):
            who[p["user_id"]] = p["role"]
        for u in acct:
            who.setdefault(u, "lead")
        manage = bool(ctx["role"]) and auth.can(ctx["role"], "manage_event")
        out.append({
            "key": f"event:{eid}", "layer": "activities", "title": title or "Untitled activity",
            "start": s_iso, "end": max(e_iso, s_iso), "start_time": None, "end_time": None,
            "all_day": True, "time_note": None,
            "kind": "activity", "status": "confirmed",
            "owner_org_id": ov["owner_org_id"] if ov and ov["owner_org_id"] else lead_id,
            "owner_label": lead["label"] if lead else None,
            "tone": _tone(lead, ov["owner_org_id"] if ov and ov["owner_org_id"] else lead_id, tones),
            "people": [{"user_id": u, "role": r, **cards.get(u, {"name": "", "initials": "?", "photo_url": None})}
                       for u, r in who.items()],
            "tags": ov["tags"] if ov else [], "venue": venue, "modality": modality if modality in ("f2f", "online", "hybrid") else None,
            "meeting_url": None,
            "url": (f"/monitor/{token}" if manage else f"/e/{token}") if token else None,
            "css": {"event_id": eid, "lifecycle": life, "life_text": _LIFE_TEXT[life], "registered": summ["registered"],
                    "answered": answered, "chip": chip, "event_kind": ekind or "bureau"},
            "flags": [], "editable": False, "private": False,
        })
    return out


def _in_scope_activity(ctx, scope, pseudo, owner_path, mine):
    """Scope narrowing for an activity: like an entry's, but "mine" also counts being the
    creator or a speaker, and "section"/"division" mean the unit that organises it."""
    if scope == "bureau":
        return True
    if scope == "mine":
        return mine
    if scope == "blend":
        return mine or pseudo["audience"] == "bureau"
    root = ctx["section_path"] if scope == "section" else ctx["division_path"]
    return _under(owner_path, root) or pseudo["audience"] == "bureau"


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


def _leave_layer(conn, ctx, start, end, scope):
    """Days people REPORTED themselves on leave (the weekly whereabouts), shown as "<name> — on
    leave", one bar per unbroken run of working days. Never a reason: none is ever stored.
    Who sees whom is the Who's-in page's rule (team_scope_for_user, area "awa"), so the two
    pages cannot disagree; an unlinked account sees only itself. Scope then narrows: "mine" and
    the default "blend" show only your own leave, so a section's calendar is not flooded."""
    if scope in ("blend", "mine") or ctx["awa_kind"] == "none":
        only_me = True
    else:
        only_me = False
    args = [start, end]
    sql = ("SELECT w.user_id, w.day, ou.path, ou.id FROM whereabouts w "
           "JOIN admin_user a ON a.id = w.user_id AND a.active = 1 "
           "LEFT JOIN resource_person rp ON rp.id = a.rp_id "
           "LEFT JOIN org_unit ou ON ou.id = rp.org_unit_id "
           "WHERE w.status = 'leave' AND w.day BETWEEN ? AND ? "
           "AND (rp.id IS NULL OR rp.archived_at IS NULL)")
    if only_me:
        sql += " AND w.user_id = ?"
        args.append(ctx["user_id"])
    days = {}
    owner = {}
    for uid, day, path, unit_id in conn.execute(sql + " ORDER BY w.user_id, w.day", args):
        if uid != ctx["user_id"]:
            if ctx["awa_kind"] == "unit" and not _under(path, ctx["awa_path"]):
                continue
            if scope == "section" and not _under(path, ctx["section_path"]):
                continue
            if scope == "division" and not _under(path, ctx["division_path"]):
                continue
        days.setdefault(uid, []).append(date.fromisoformat(day))
        owner[uid] = (path, unit_id)
    if not days:
        return []
    cards = _people_cards(conn, list(days))
    units = _units(conn, [u for _p, u in owner.values()])
    out = []
    for uid, ds in days.items():
        runs = [[ds[0], ds[0]]]
        for d in ds[1:]:
            gap = [runs[-1][1] + timedelta(days=n) for n in range(1, (d - runs[-1][1]).days)]
            if all(g.weekday() >= 5 for g in gap):         # only a weekend between: same run
                runs[-1][1] = d
            else:
                runs.append([d, d])
        card = cards.get(uid, {"name": "", "initials": "?", "photo_url": None})
        unit = units.get(owner[uid][1])
        for a, b in runs:
            out.append({
                "key": f"leave:{uid}:{a.isoformat()}", "layer": "leave",
                "title": f"{card['name'] or 'Someone'} — on leave",
                "start": a.isoformat(), "end": b.isoformat(), "start_time": None, "end_time": None,
                "all_day": True, "time_note": None, "kind": "leave", "status": "confirmed",
                "owner_org_id": owner[uid][1], "owner_label": unit["label"] if unit else None,
                "tone": "grey", "people": [{"user_id": uid, "role": "attending", **card}],
                "tags": [], "venue": None, "modality": None, "meeting_url": None, "url": None,
                "css": None, "flags": [], "editable": False, "private": False,
            })
    return out


# ── soft mismatches between what the calendar says and what people reported (E2) ──
#
# One function decides all of them (docs/OFFICE_CALENDAR_PLAN.md §4). They are heads-ups: nothing
# here blocks, changes or deletes anything, and each is derived at read time from the entries
# and the person's own whereabouts rows.

MISMATCH_KINDS = ("trip_conflict", "leave_on_entry", "double_booked")


def _hhmm(t):
    return t if t and len(t) >= 5 else None


def mismatches(conn, user_ids, start, end, *, kinds=MISMATCH_KINDS):
    """Heads-ups for the given accounts over working days between `start` and `end`:

      trip_conflict   on a confirmed trip, but reported Office / AWA / Leave that day
      leave_on_entry  reported Leave on a day a live entry lists them (a trip is trip_conflict)
      double_booked   listed on two timed entries that overlap in time the same day

    Each is {kind, user_id, day, entry_id, title, other_title, detail}. Cancelled entries never
    count, and a person who reported Field on a trip day, or has nothing reported, is no mismatch."""
    ids = sorted({int(u) for u in user_ids})
    if not ids:
        return []
    s_iso = start.isoformat() if isinstance(start, date) else str(start)
    e_iso = end.isoformat() if isinstance(end, date) else str(end)
    marks = ",".join("?" * len(ids))
    reported = {(u, d): (stt, note) for u, d, stt, note in conn.execute(
        f"SELECT user_id, day, status, note FROM whereabouts WHERE user_id IN ({marks}) "
        f"AND day BETWEEN ? AND ?", (*ids, s_iso, e_iso))}
    out = []
    trips = st.cal_travel_defaults(conn, s_iso, e_iso)
    if "trip_conflict" in kinds:
        for (uid, iso), t in sorted(trips.items(), key=lambda kv: (kv[0][1], kv[0][0])):
            rep = reported.get((uid, iso))
            if uid in ids and rep and rep[0] != "field":
                out.append({"kind": "trip_conflict", "user_id": uid, "day": iso,
                            "entry_id": t["entry_id"], "title": t["title"], "other_title": None,
                            "detail": f"On {t['title']}, but reported {st.WHEREABOUTS_LABELS.get(rep[0], rep[0])}"})
    if not ({"leave_on_entry", "double_booked"} & set(kinds)):
        return out
    by_day = {}
    for uid, eid, title, a, b, t1, t2 in conn.execute(
            f"SELECT cp.user_id, e.id, e.title, e.start_date, COALESCE(NULLIF(e.end_date, ''), e.start_date), "
            f"e.start_time, e.end_time FROM calendar_entry e "
            f"JOIN calendar_entry_person cp ON cp.entry_id = e.id "
            f"WHERE cp.user_id IN ({marks}) AND e.status <> 'cancelled' AND e.start_date <= ? "
            f"AND COALESCE(NULLIF(e.end_date, ''), e.start_date) >= ? ORDER BY e.id", (*ids, e_iso, s_iso)):
        day, last = max(date.fromisoformat(a), date.fromisoformat(s_iso)), min(date.fromisoformat(b), date.fromisoformat(e_iso))
        while day <= last:
            if day.weekday() < 5:
                by_day.setdefault((uid, day.isoformat()), []).append((eid, title, _hhmm(t1), _hhmm(t2)))
            day += timedelta(days=1)
    for (uid, iso), rows in sorted(by_day.items(), key=lambda kv: (kv[0][1], kv[0][0])):
        if "leave_on_entry" in kinds and (reported.get((uid, iso)) or (None,))[0] == "leave":
            for eid, title, _t1, _t2 in rows:
                if (uid, iso) in trips and trips[(uid, iso)]["entry_id"] == eid:
                    continue                                    # reported as trip_conflict
                out.append({"kind": "leave_on_entry", "user_id": uid, "day": iso, "entry_id": eid,
                            "title": title, "other_title": None,
                            "detail": f"On leave, but listed on {title}"})
        if "double_booked" in kinds:
            timed = [r for r in rows if r[2] and r[3]]
            for i, (e1, t1, s1, f1) in enumerate(timed):
                for e2, t2, s2, f2 in timed[i + 1:]:
                    if s1 < f2 and s2 < f1:
                        out.append({"kind": "double_booked", "user_id": uid, "day": iso, "entry_id": e1,
                                    "title": t1, "other_title": t2, "other_entry_id": e2,
                                    "detail": f"{t1} and {t2} overlap"})
    return out


def entry_heads_up(conn, user, entry):
    """Sentences for an entry's page: mismatches among the people on it, shown only to the
    person concerned, the entry's leads and whoever added it — never to the wider audience."""
    ids = [p["user_id"] for p in entry["people"]]
    if not ids or entry["status"] == "cancelled":
        return []
    leads = {p["user_id"] for p in entry["people"] if p["role"] == "lead"}
    is_owner = bool(entry.get("created_by")) and entry["created_by"] == user.get("username")
    start = entry["start_date"]
    end = min(entry["end_date"] or start, (date.fromisoformat(start) + timedelta(days=60)).isoformat())
    cards = _people_cards(conn, ids)
    out = []
    for m in mismatches(conn, ids, start, end):
        if m["entry_id"] != entry["id"] and m.get("other_entry_id") != entry["id"]:
            continue
        if not (m["user_id"] == user["id"] or user["id"] in leads or is_owner):
            continue
        who = "You" if m["user_id"] == user["id"] else cards.get(m["user_id"], {}).get("name") or "Someone"
        d = date.fromisoformat(m["day"])
        out.append(f"{who}: {m['detail']} ({d.strftime('%a, %b')} {d.day}).")
    return out


# name -> provider(conn, ctx, start_iso, end_iso, scope) -> [CalItem]. Later
# layers (activities, leave, birthdays, deadlines) are one line each.
LAYERS = {
    "entries": _entries_layer,
    "activities": _activities_layer,
    "holidays": _holidays_layer,
    "leave": _leave_layer,
}

# Within one day, what leads: the day's own banner (a holiday), then the rest.
_DISPLAY_ORDER = ("holidays", "birthdays", "deadlines", "activities", "entries", "leave")
_LAYER_ORDER = {name: i for i, name in enumerate(_DISPLAY_ORDER)}


def items_between(conn, user, start, end, *, scope=DEFAULT_SCOPE, layers=None, filters=None):
    """Every calendar item `user` may see between `start` and `end` (inclusive;
    dates or ISO strings), merged across layers and sorted by day, then time.

    `scope` only narrows (see module docstring); an unknown scope raises
    ValueError rather than guessing. `layers` limits which providers run
    (default: all registered). `filters` is `apply_filters`' dict."""
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
    return apply_filters(items, filters)


def apply_filters(items, filters):
    """Narrow items by what the viewer chose: filters is a dict with any of
    `kinds`, `statuses`, `tags`, `owner_org_ids` (sets; a missing/empty one means
    "any"). Holidays are never filtered out: they are the calendar's own backdrop,
    not something a person added. An item with no tags can't match a tag filter."""
    f = {k: set(v) for k, v in (filters or {}).items() if v}
    if not f:
        return items
    keep = []
    for i in items:
        if i["layer"] == "holidays":
            keep.append(i)
        elif ((not f.get("kinds") or i["kind"] in f["kinds"])
              and (not f.get("statuses") or i["status"] in f["statuses"])
              and (not f.get("tags") or f["tags"] & set(i["tags"]))
              and (not f.get("owner_org_ids") or i["owner_org_id"] in f["owner_org_ids"])):
            keep.append(i)
    return keep


def _iso(d):
    return d.isoformat() if isinstance(d, date) else date.fromisoformat(str(d)).isoformat()


# ── presentation helpers (pure; used by the /calendar page) ──────────────────

SCOPE_LABELS = {
    "blend": "Mine + bureau-wide", "mine": "Mine only", "section": "My section",
    "division": "My division", "bureau": "Everything I can see",
}


def scope_choices(ctx):
    """The scope pills this viewer is offered, in display order. A viewer with no
    section/division is not offered a pill that could only ever be empty."""
    out = ["blend", "mine"]
    if ctx["section_path"]:
        out.append("section")
    if ctx["division_path"]:
        out.append("division")
    out.append("bureau")
    return [{"key": k, "label": SCOPE_LABELS[k]} for k in out]


def agenda_days(items, start, end, today):
    """Group items by day for the agenda. A multi-day item appears on every day it
    covers inside the window, tagged "day 2 of 4". Days with nothing on are left
    out, except today, which is always pinned so the page says so plainly.
    `start`/`end`/`today` are dates; items carry ISO strings."""
    out, d = [], start
    while d <= end:
        iso = d.isoformat()
        todays = []
        for it in items:
            if it["start"] <= iso <= it["end"]:
                span = (date.fromisoformat(it["end"]) - date.fromisoformat(it["start"])).days + 1
                nth = (d - date.fromisoformat(it["start"])).days + 1
                todays.append({**it, "day_n": nth if span > 1 else None, "day_of": span})
        if todays or d == today:
            out.append({
                "iso": iso, "date": d, "label": d.strftime("%a, %b ") + str(d.day),
                "is_today": d == today, "is_weekend": d.weekday() >= 5,
                "holidays": [i for i in todays if i["layer"] == "holidays"],
                "rows": [i for i in todays if i["layer"] != "holidays"],
            })
        d += timedelta(days=1)
    return out


# ── helpers for the add / edit / detail pages (A4) ───────────────────────────

FIELD_LABELS = {
    "title": "title", "kind": "type", "status": "status", "start_date": "start date",
    "end_date": "end date", "start_time": "start time", "end_time": "end time",
    "time_note": "time note", "venue": "venue", "modality": "format",
    "meeting_url": "meeting link", "note": "notes", "owner_org_id": "owning unit",
    "audience": "who can see it", "people": "people", "tags": "tags",
    "event_id": "linked activity", "rrule": "repeat", "exdates": "skipped dates",
}


def viewable_entry(conn, user, entry_id):
    """The entry if THIS viewer may see it, else None. A caller turns None into a
    404, so an entry the viewer isn't allowed to see is indistinguishable from one
    that doesn't exist."""
    e = st.cal_get(conn, entry_id)
    if e is None:
        return None
    owner = _units(conn, [e["owner_org_id"]]).get(e["owner_org_id"])
    return e if entry_visible(viewer_context(conn, user), e, owner["path"] if owner else None) else None


def people_choices(conn):
    """Active accounts a person can be put on an entry as: [{user_id, name}]."""
    return sorted(
        ({"user_id": r[0], "name": r[1] or r[2]} for r in conn.execute(
            "SELECT a.id, rp.name, a.username FROM admin_user a "
            "LEFT JOIN resource_person rp ON rp.id = a.rp_id "
            "WHERE a.active = 1 AND (rp.id IS NULL OR rp.archived_at IS NULL)")),
        key=lambda p: p["name"].lower())


def unit_choices(conn):
    """Org units to own an entry, indented by depth: [{id, label, path}]."""
    out = []
    for uid, name, path in conn.execute(
            "SELECT id, COALESCE(NULLIF(short_name,''), name), path FROM org_unit "
            "ORDER BY path"):
        out.append({"id": uid, "path": path,
                    "label": (" " * path.count("/")) + name})
    return out


def display_names(conn, usernames):
    """{username: display name} — the directory name when linked, else the login."""
    names = sorted({u for u in usernames if u})
    if not names:
        return {}
    return {r[0]: r[1] or r[0] for r in conn.execute(
        "SELECT a.username, rp.name FROM admin_user a "
        "LEFT JOIN resource_person rp ON rp.id = a.rp_id WHERE a.username IN (%s)"
        % ",".join("?" * len(names)), names)}


def describe_change(diff):
    """'changed venue and start date' for a revision's diff."""
    order = list(FIELD_LABELS)
    labels = [FIELD_LABELS.get(f, f) for f in
              sorted(diff, key=lambda f: order.index(f) if f in order else len(order))]
    if not labels:
        return "saved"
    return "changed " + (", ".join(labels[:-1]) + " and " + labels[-1]
                         if len(labels) > 1 else labels[0])


# ── month grid ────────────────────────────────────────────────────────────────

WEEKDAY_NAMES = ("Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat")     # Sunday first, like the Word calendar


def month_span(year, month):
    """(grid_start, grid_end): the Sunday on/before the 1st through the Saturday
    on/after the last day — whole weeks, so the grid has no ragged rows."""
    first = date(year, month, 1)
    last = date(year + (month == 12), month % 12 + 1, 1) - timedelta(days=1)
    return (first - timedelta(days=(first.weekday() + 1) % 7),
            last + timedelta(days=(5 - last.weekday()) % 7))


def _lay_out(items, w0, ncols, max_lanes):
    """Stack the items that overlap the `ncols` days starting at `w0` into lanes.
    Returns (bars, lanes_used, more): each bar is {item, col (1-based), span, lane (1-based),
    left_cut, right_cut, timed}; `more[c]` counts the items hidden below `max_lanes` on day c
    (never silently dropped). Holidays are not bars."""
    w_end = w0 + timedelta(days=ncols - 1)
    iso0, iso_end = w0.isoformat(), w_end.isoformat()
    mine = sorted((i for i in items if i["layer"] != "holidays"
                   and i["start"] <= iso_end and i["end"] >= iso0),
                  key=lambda i: (i["start"], -(date.fromisoformat(i["end"])
                                                - date.fromisoformat(i["start"])).days,
                                 i["start_time"] or "", i["title"].lower()))
    lanes, bars, more = [], [], [0] * ncols
    for i in mine:
        c0 = max((date.fromisoformat(i["start"]) - w0).days, 0)
        c1 = min((date.fromisoformat(i["end"]) - w0).days, ncols - 1)
        lane = next((n for n, taken in enumerate(lanes)
                     if not any(c0 <= b and a <= c1 for a, b in taken)), len(lanes))
        if lane == len(lanes):
            lanes.append([])
        lanes[lane].append((c0, c1))
        if lane < max_lanes:
            bars.append({"item": i, "col": c0 + 1, "span": c1 - c0 + 1, "lane": lane + 1,
                         "left_cut": i["start"] < iso0, "right_cut": i["end"] > iso_end,
                         "timed": i["start_time"] is not None and i["start"] == i["end"]})
        else:
            for c in range(c0, c1 + 1):
                more[c] += 1
    return bars, len(lanes), more


def month_grid(items, year, month, today, max_lanes=3):
    """Lay items out as weeks of seven days. Each entry that overlaps a week is a
    BAR: `col` (1-7) where it starts in that week, `span` days wide, `lane` (row
    stacked under the day numbers), and `left_cut` / `right_cut` when it continues
    from the previous / into the next week — so a four-day trip is one bar, not
    four chips. Only `max_lanes` rows are drawn; anything below is counted per day
    in `more` ("+N more"), never silently dropped. Holidays are not bars: they
    label and tint their day."""
    start, end = month_span(year, month)
    weeks, w0 = [], start
    while w0 <= end:
        w6 = w0 + timedelta(days=6)
        days = []
        for n in range(7):
            d = w0 + timedelta(days=n)
            iso = d.isoformat()
            days.append({
                "date": d, "iso": iso, "num": d.day, "in_month": d.month == month,
                "is_today": d == today, "is_weekend": d.weekday() >= 5,
                "holidays": [i for i in items if i["layer"] == "holidays" and i["start"] == iso],
                "more": 0,
            })
        bars, lanes, more = _lay_out(items, w0, 7, max_lanes)
        for c, n in enumerate(more):
            days[c]["more"] = n
        weeks.append({"days": days, "bars": bars,
                      "rows": min(lanes, max_lanes) + (1 if any(d["more"] for d in days) else 0)})
        w0 += timedelta(days=7)
    first = date(year, month, 1)
    prev = (first - timedelta(days=1)).strftime("%Y-%m")
    nxt = (date(year + (month == 12), month % 12 + 1, 1)).strftime("%Y-%m")
    return {"weeks": weeks, "title": first.strftime("%B %Y"), "prev": prev, "next": nxt,
            "prev_label": date.fromisoformat(prev + "-01").strftime("%b %Y"),
            "next_label": date.fromisoformat(nxt + "-01").strftime("%b %Y"),
            "start": start, "end": end}


# ── people x days (the Week layout, C3) ───────────────────────────────────────

WEEK_LANES = 3          # bars drawn per person per week; the rest are counted, not dropped
_STATE_TEXT = {"onsite": "In office", "wfh": "Home", "dayoff": "Day off", "field": "Field",
               "leave": "On leave", "holiday": "Holiday", "noawa": "No AWA", "unfiled": "", "none": ""}


def monday_of(d):
    return d - timedelta(days=d.weekday())


def people_week(conn, user, monday, items):
    """The Week layout: one row per person in the viewer's team, Monday-Friday across.

    Everything about WHERE a person is comes from `storage.whereabouts_roster_week` — the
    very function behind the "Who's in" week page — so its rules carry over unchanged:
    scope is the directory (an unlinked account gets no team, not everyone), a person's own
    report outranks the filing, a holiday has no cells, and LEAVE NEVER CARRIES A REASON.
    On top of that, each person's calendar items are laid out as bars across their days.

    `items` are calendar items the viewer is already allowed to see (items_between did that
    once, centrally). An item names the people on it: it goes on the row of each of them who
    is in this team. One that names nobody in this team (the whole unit, the bureau, someone
    outside) goes in the band at the top instead, so nothing visible is ever left off the page.
    Weekend days are not shown: a trip that runs into one is simply cut at Friday."""
    roster = st.whereabouts_roster_week(conn, monday, user)
    ncols = len(roster["days"])
    fri = monday + timedelta(days=ncols - 1)
    work = [i for i in items if i["layer"] in ("entries", "activities") and i["start"] <= fri.isoformat()
            and i["end"] >= monday.isoformat()]
    team = {p["user_id"] for sec in roster["sections"] for p in sec["people"]}
    per_person, band = {}, []
    for i in work:
        on = [p["user_id"] for p in i["people"] if p["user_id"] in team]
        if on:
            for uid in on:
                per_person.setdefault(uid, []).append(i)
        else:
            band.append(i)
    band_bars, band_lanes, band_more = _lay_out(band, monday, ncols, WEEK_LANES)
    sections = []
    for sec in roster["sections"]:
        rows = []
        for p in sec["people"]:
            bars, lanes, more = _lay_out(per_person.get(p["user_id"], []), monday, ncols, WEEK_LANES)
            cells = []
            for c in p["cells"]:
                state = c["state"]
                cells.append({"state": state, "text": _STATE_TEXT.get(state, ""),
                              "note": c.get("note") or "", "plotted": c.get("plotted", False)})
            rows.append({"user_id": p["user_id"], "name": p["name"], "cells": cells, "bars": bars,
                         "more": more, "rows": max(min(lanes, WEEK_LANES), 1) + (1 if any(more) else 0)})
        sections.append({"section": sec["section"], "people": rows})
    return {
        "kind": roster["kind"], "label": roster["label"], "days": roster["days"],
        "sections": sections, "n_people": len(team),
        "band": {"bars": band_bars, "more": band_more,
                 "rows": max(min(band_lanes, WEEK_LANES), 1) + (1 if any(band_more) else 0)},
        "has_band": bool(band),
        "team_label": ", ".join(s["section"] for s in sections),
        "prev": (monday - timedelta(days=7)).isoformat(), "next": (monday + timedelta(days=7)).isoformat(),
        "monday": monday,
    }


# ── linking calendar items and CSS activities (D2) ───────────────────────────

LINKABLE_KINDS = ("meeting", "training")      # internal meetings, audits, banners... never get a CSS form


def _norm_title(t):
    return " ".join("".join(c if c.isalnum() else " " for c in (t or "").lower()).split())


def similar_titles(a, b):
    """Do two titles plausibly name the same activity? Equal after normalising, one inside
    the other (6+ characters, so "Mtg" doesn't match everything), or very close. A
    suggestion only: nothing is ever linked without a person pressing the button."""
    from difflib import SequenceMatcher
    na, nb = _norm_title(a), _norm_title(b)
    if not na or not nb:
        return False
    if na == nb:
        return True
    if min(len(na), len(nb)) >= 6 and (na in nb or nb in na):
        return True
    return SequenceMatcher(None, na, nb, autojunk=False).ratio() >= 0.75


def entry_can_collect_feedback(entry):
    """May this calendar item be turned into a CSS activity? Only a live, unlinked meeting
    or training: a trip, audit, banner or deadline has nobody to ask for feedback."""
    return (entry["kind"] in LINKABLE_KINDS and not entry["event_id"]
            and entry["status"] != "cancelled")


def activity_candidates_for_entry(conn, entry):
    """Activities that overlap this item's dates, have a similar title and no calendar item
    linked yet — "this may already be an activity". Archived activities are not offered."""
    start = entry["start_date"]
    end = entry["end_date"] or start
    out = []
    for eid, token, title, ed, end_d in conn.execute("""
            SELECT e.id, e.event_token, e.title, e.event_date, e.end_date FROM event e
            WHERE COALESCE(e.event_date, '') <> '' AND substr(e.event_date, 1, 10) <= ?
              AND substr(COALESCE(NULLIF(e.end_date, ''), e.event_date), 1, 10) >= ?
              AND NOT EXISTS (SELECT 1 FROM calendar_entry c WHERE c.event_id = e.id)
              AND NOT (EXISTS (SELECT 1 FROM event_form ef WHERE ef.event_id = e.id)
                       AND NOT EXISTS (SELECT 1 FROM event_form ef JOIN form_instance fi
                                        ON fi.id = ef.form_instance_id
                                       WHERE ef.event_id = e.id AND COALESCE(fi.archived, 0) = 0))
            ORDER BY e.event_date, e.id""", (end, start)):
        if similar_titles(title, entry["title"]):
            out.append({"id": eid, "token": token, "title": title, "date": ed[:10]})
    return out


def entry_candidates_for_activity(conn, user, title, start, end=None):
    """Calendar items THIS viewer may see that could be the activity being created: same
    dates, similar title, not already linked, a kind that can take a CSS form."""
    end = end or start
    out = []
    for e in st.cal_list_between(conn, start, end):
        if not entry_can_collect_feedback(e) or not similar_titles(e["title"], title):
            continue
        if viewable_entry(conn, user, e["id"]) is not None:
            out.append({"id": e["id"], "title": e["title"], "start": e["start_date"],
                        "end": e["end_date"] or e["start_date"], "url": f"/calendar/entries/{e['id']}"})
    return out
