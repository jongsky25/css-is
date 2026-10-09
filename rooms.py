"""Conference room reservation: the service core (docs/ROOM_RESERVATION_PLAN.md, R1).

One room, fixed one-hour slots between 07:00 and 19:00. Many people may *request*
the same hour; only one request can be *approved* for it, and the database
enforces that (ux_room_slot_taken). Every state change goes through this module so
the rules live in one place; routes and templates only call these functions.

Statuses: requested -> approved | declined | withdrawn | expired; approved ->
withdrawn | cancelled (cancel/bump arrives in a later increment).
"""
from __future__ import annotations
import sqlite3
from datetime import date, datetime, timedelta

import storage as st
import tzutil as tz

OPEN_HOUR, CLOSE_HOUR = 7, 19      # room hours: 07:00-19:00
LEAD_WORKING_DAYS = 2              # a request must be made 2 working days ahead
MAX_DAYS_AHEAD = 90                # booking horizon for signed-in users
GUEST_MAX_DAYS_AHEAD = 60          # ... and for guests using the public QR page
GUEST_OPEN_LIMIT = 3               # open requests allowed per guest email address
MODALITIES = ("f2f", "online", "hybrid")
_SEED_KEY = "room_slots_seeded"


class RoomError(Exception):
    """A request the rules refuse. The message is safe to show the user."""


def _emit(event, conn, *args):
    """Tell rooms_notify what happened. Notices are a courtesy: a failure here must never
    undo or block a booking decision that already committed."""
    try:
        import rooms_notify
        getattr(rooms_notify, "on_" + event)(conn, *args)
    except Exception:                                       # noqa: BLE001
        try:
            conn.rollback()
        except Exception:                                   # noqa: BLE001
            pass


class SlotTaken(RoomError):
    """The hour is already approved for another reservation."""
    def __init__(self, msg, other=None):
        super().__init__(msg)
        self.other = other


class AlreadyDecided(RoomError):
    """Someone else got there first; `decided_by` / `decided_at` say who and when."""
    def __init__(self, msg, decided_by=None, decided_at=None, status=None):
        super().__init__(msg)
        self.decided_by, self.decided_at, self.status = decided_by, decided_at, status


# ----------------------------------------------------------------- slots ---

def ensure_slots(conn):
    """Create the twelve 1-hour slots once. Keyed in app_setting so an admin who
    later edits or deactivates a slot never has it put back."""
    if st.get_setting(conn, _SEED_KEY) == "1":
        return
    for i, h in enumerate(range(OPEN_HOUR, CLOSE_HOUR)):
        conn.execute(
            "INSERT OR IGNORE INTO room_slot(code, label, start_time, end_time, sort, active) "
            "VALUES (?,?,?,?,?,1)",
            (f"H{h:02d}", f"{h:02d}:00-{h + 1:02d}:00", f"{h:02d}:00", f"{h + 1:02d}:00", i))
    st.set_setting(conn, _SEED_KEY, "1")
    conn.commit()


def list_slots(conn, active_only=True):
    ensure_slots(conn)
    sql = "SELECT id, code, label, start_time, end_time, sort, active FROM room_slot"
    if active_only:
        sql += " WHERE active=1"
    return [dict(zip(("id", "code", "label", "start_time", "end_time", "sort", "active"), r))
            for r in conn.execute(sql + " ORDER BY sort, id")]


# ------------------------------------------------------------- calendar ---

def _d(day):
    return day if isinstance(day, date) else date.fromisoformat(str(day))


def is_working_day(conn, day):
    """Monday-Friday and not a declared holiday / suspension."""
    day = _d(day)
    return day.weekday() < 5 and st.get_holiday(conn, day) is None


def add_working_days(conn, start, n):
    """The date n working days after `start` (start itself is not counted)."""
    day, left = _d(start), n
    while left > 0:
        day += timedelta(days=1)
        if is_working_day(conn, day):
            left -= 1
    return day


def earliest_bookable(conn, today=None):
    """First date an ordinary request may be for: two working days from today."""
    return add_working_days(conn, today or tz.today_local(), LEAD_WORKING_DAYS)


def day_closed(conn, day, today=None, *, override_lead=False, max_ahead=MAX_DAYS_AHEAD):
    """(short, long) reasons `day` can't be requested at all, or None. `short` is for a
    narrow grid header, `long` is plain words for an error message."""
    day, today = _d(day), today or tz.today_local()
    if day.weekday() >= 5:
        return "Weekend", "The conference room is closed on weekends."
    h = st.get_holiday(conn, day)
    if h:
        return h["name"], f"Closed: {h['name']}."
    if day < today:
        return "Past", "That date has already passed."
    if not override_lead and day < earliest_bookable(conn, today):
        return "Too soon", (f"Requests need at least {LEAD_WORKING_DAYS} working days' notice "
                            f"(earliest: {earliest_bookable(conn, today).strftime('%b %d')}).")
    if day > today + timedelta(days=max_ahead):
        return "Too far ahead", f"Requests open up to {max_ahead} days ahead."
    return None


def day_closed_reason(conn, day, today=None, *, override_lead=False, max_ahead=MAX_DAYS_AHEAD):
    """Why `day` can't be requested at all, or None. Plain words for the UI."""
    c = day_closed(conn, day, today, override_lead=override_lead, max_ahead=max_ahead)
    return c[1] if c else None


def slot_states(conn, day):
    """{slot_id: state dict} for one date, for the board and for validation.

    state is one of free / requested (others are waiting) / approved / blocked.
    `requested` still counts as requestable: the section decides between them."""
    day = _d(day).isoformat()
    out = {s["id"]: {"slot": s, "state": "free", "pending": 0, "reservation_id": None}
           for s in list_slots(conn)}
    for rid, sid, appr in conn.execute(
            "SELECT rs.reservation_id, rs.slot_id, rs.is_approved FROM room_reservation_slot rs "
            "JOIN room_reservation r ON r.id = rs.reservation_id "
            "WHERE rs.day=? AND r.status IN ('requested','approved')", (day,)):
        o = out.get(sid)
        if o is None:
            continue
        if appr:
            o.update(state="approved", reservation_id=rid)
        else:
            o["pending"] += 1
            if o["state"] == "free":
                o["state"] = "requested"
    for sid, reason in conn.execute("SELECT slot_id, reason FROM room_block WHERE day=?", (day,)):
        for k, o in out.items():
            if sid is None or sid == k:
                o.update(state="blocked", reason=reason)
    return out


# ------------------------------------------------------------- reading ---

_COLS = ("id, ref_code, requester_user_id, ext_name, ext_org, ext_email, ext_phone, on_behalf_of, "
         "title, purpose, attendees, modality, day, status, source, decided_by, decided_at, "
         "decide_note, bumped_by_reservation_id, moves_reservation_id, event_id, "
         "calendar_entry_id, meals_requested, created_by, created_at, updated_at, "
         "ext_email_verified_at, ext_consent_at")


def _row(conn, r):
    d = dict(zip(_COLS.replace("\n", " ").split(", "), r))
    d["slot_ids"] = [x[0] for x in conn.execute(
        "SELECT rs.slot_id FROM room_reservation_slot rs JOIN room_slot s ON s.id=rs.slot_id "
        "WHERE rs.reservation_id=? ORDER BY s.sort", (d["id"],))]
    return d


def get_reservation(conn, rid):
    r = conn.execute(f"SELECT {_COLS} FROM room_reservation WHERE id=?", (rid,)).fetchone()
    return _row(conn, r) if r else None


def get_by_ref(conn, ref_code):
    r = conn.execute(f"SELECT {_COLS} FROM room_reservation WHERE ref_code=?",
                     ((ref_code or "").strip().upper(),)).fetchone()
    return _row(conn, r) if r else None


def list_for_user(conn, user_id, upcoming_only=False, today=None):
    sql = f"SELECT {_COLS} FROM room_reservation WHERE requester_user_id=?"
    args = [user_id]
    if upcoming_only:
        sql += " AND day >= ? AND status IN ('requested','approved')"
        args.append((today or tz.today_local()).isoformat())
    return [_row(conn, r) for r in conn.execute(sql + " ORDER BY day DESC, id DESC", args)]


def list_pending(conn):
    """Open requests waiting for the Administrative Section, soonest date first."""
    return [_row(conn, r) for r in conn.execute(
        f"SELECT {_COLS} FROM room_reservation WHERE status='requested' ORDER BY day, id")]


def competing(conn, rid):
    """Other still-open requests that want any of this reservation's hours."""
    return [_row(conn, r) for r in conn.execute(
        f"SELECT {_COLS} FROM room_reservation WHERE status='requested' AND id<>? AND id IN ("
        " SELECT b.reservation_id FROM room_reservation_slot a JOIN room_reservation_slot b "
        " ON a.day=b.day AND a.slot_id=b.slot_id WHERE a.reservation_id=?)", (rid, rid))]


# ------------------------------------------------------------- writing ---

def _stamp():
    return tz.now_iso()


def _validate_slots(conn, slot_ids):
    """Active, distinct, and consecutive hours (one block, no gaps)."""
    ids = list(dict.fromkeys(int(s) for s in (slot_ids or [])))
    if not ids:
        raise RoomError("Pick at least one hour.")
    slots = {s["id"]: s for s in list_slots(conn)}
    if any(i not in slots for i in ids):
        raise RoomError("That hour isn't available for booking.")
    order = sorted(ids, key=lambda i: slots[i]["sort"])
    sorts = [slots[i]["sort"] for i in order]
    active_sorts = [s["sort"] for s in slots.values()]
    pos = [active_sorts.index(x) for x in sorts]
    if pos != list(range(pos[0], pos[0] + len(pos))):
        raise RoomError("Hours must be back-to-back. Send one request per separate block.")
    return order


def request(conn, *, title, day, slot_ids, requester_user_id=None, ext=None, purpose=None,
            attendees=None, modality="f2f", meals_requested=False, actor=None, today=None,
            max_ahead=MAX_DAYS_AHEAD, consent_at=None):
    """File a request. Internal (requester_user_id) or external (ext = dict of
    name/org/email/phone). Status starts `requested`; nothing is held."""
    title = (title or "").strip()
    if not title:
        raise RoomError("Please give the meeting a title.")
    if modality not in MODALITIES:
        raise RoomError("Choose face-to-face, online or hybrid.")
    if attendees is not None and int(attendees) < 1:
        raise RoomError("Attendees must be at least 1.")
    if requester_user_id is None and not (ext and (ext.get("name") or "").strip()
                                          and (ext.get("email") or ext.get("phone"))):
        raise RoomError("Who is asking? Add a name and an email or phone number.")
    ext = ext or {}
    today = today or tz.today_local()
    reason = day_closed_reason(conn, day, today, max_ahead=max_ahead)
    if reason:
        raise RoomError(reason)
    order = _validate_slots(conn, slot_ids)
    states = slot_states(conn, day)
    for sid in order:
        if states[sid]["state"] in ("approved", "blocked"):
            who = "booked" if states[sid]["state"] == "approved" else "unavailable"
            raise SlotTaken(f"{states[sid]['slot']['label']} is already {who} that day.")
    now = _stamp()
    day_iso = _d(day).isoformat()
    try:
        cur = conn.execute(
            "INSERT INTO room_reservation(requester_user_id, ext_name, ext_org, ext_email, ext_phone, "
            "ext_consent_at, title, purpose, attendees, modality, day, status, source, meals_requested, "
            "created_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?,?, 'requested', ?,?,?,?,?)",
            (requester_user_id, ext.get("name"), ext.get("org"), ext.get("email"), ext.get("phone"),
             consent_at, title, (purpose or "").strip() or None, attendees, modality, day_iso,
             "internal" if requester_user_id is not None else "external",
             1 if meals_requested else 0, actor, now, now))
        rid = cur.lastrowid
        conn.execute("UPDATE room_reservation SET ref_code=? WHERE id=?",
                     (f"CR-{_d(day_iso):%y%m}-{rid:04d}", rid))
        conn.executemany(
            "INSERT INTO room_reservation_slot(reservation_id, day, slot_id, is_approved) VALUES (?,?,?,0)",
            [(rid, day_iso, sid) for sid in order])
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    st.audit(conn, actor or "system", "room_request", target_type="room_reservation", target_id=rid,
             summary=f"{title} on {day_iso}")
    out = get_reservation(conn, rid)
    _emit("requested", conn, out)
    if requester_user_id is None:
        _emit("received", conn, out)
    return out


def _must_be_open(res, want):
    if res is None:
        raise RoomError("That reservation no longer exists.")
    if res["status"] not in want:
        raise AlreadyDecided(
            f"Already {res['status']}"
            + (f" by {res['decided_by']}" if res["decided_by"] else "")
            + (f" at {res['decided_at'].replace('T', ' ')}" if res["decided_at"] else "") + ".",
            res["decided_by"], res["decided_at"], res["status"])


def approve(conn, rid, by, note=None, today=None, decline_rivals=False):
    """First to act wins. Raises AlreadyDecided if someone already decided, or
    SlotTaken if another reservation holds one of the hours. With decline_rivals the
    other open requests for the same hours are declined in the same transaction (they
    are shown alternatives on My reservations)."""
    res = get_reservation(conn, rid)
    _must_be_open(res, ("requested",))
    if _d(res["day"]) < (today or tz.today_local()):
        raise RoomError("That date has already passed.")
    blocked = conn.execute(
        "SELECT b.reason FROM room_block b JOIN room_reservation_slot rs ON rs.day=b.day "
        "AND (b.slot_id IS NULL OR b.slot_id=rs.slot_id) WHERE rs.reservation_id=? LIMIT 1", (rid,)).fetchone()
    if blocked:
        raise SlotTaken(f"The room is unavailable for those hours ({blocked[0]}).")
    rivals = competing(conn, rid) if decline_rivals else []
    try:
        conn.execute("UPDATE room_reservation_slot SET is_approved=1 WHERE reservation_id=?", (rid,))
        conn.execute(
            "UPDATE room_reservation SET status='approved', decided_by=?, decided_at=?, "
            "decide_note=?, updated_at=? WHERE id=? AND status='requested'",
            (by, _stamp(), (note or "").strip() or None, _stamp(), rid))
        for o in rivals:
            conn.execute(
                "UPDATE room_reservation SET status='declined', decided_by=?, decided_at=?, decide_note=?, "
                "updated_at=? WHERE id=? AND status='requested'",
                (by, _stamp(), f"Another request for these hours was approved ({res['ref_code']}).",
                 _stamp(), o["id"]))
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        other = conn.execute(
            "SELECT r.id, r.title, r.ref_code FROM room_reservation_slot mine "
            "JOIN room_reservation_slot o ON o.day=mine.day AND o.slot_id=mine.slot_id "
            "AND o.is_approved=1 AND o.reservation_id<>mine.reservation_id "
            "JOIN room_reservation r ON r.id=o.reservation_id WHERE mine.reservation_id=? LIMIT 1",
            (rid,)).fetchone()
        raise SlotTaken("Another reservation is already approved for one of those hours"
                        + (f" ({other[1]}, {other[2]})." if other else "."),
                        other={"id": other[0], "title": other[1], "ref_code": other[2]} if other else None)
    except Exception:
        conn.rollback()
        raise
    st.audit(conn, by, "room_approve", target_type="room_reservation", target_id=rid,
             summary=f"{res['title']} on {res['day']}", before="requested", after="approved")
    for o in rivals:
        st.audit(conn, by, "room_decline", target_type="room_reservation", target_id=o["id"],
                 summary=f"{o['title']} on {o['day']}: another request approved", before="requested",
                 after="declined")
        _emit("decided", conn, get_reservation(conn, o["id"]), by)
    out = get_reservation(conn, rid)
    _emit("decided", conn, out, by)
    return out


def decline(conn, rid, by, note):
    """Decline an open request. A reason is required: the requester is told it."""
    if not (note or "").strip():
        raise RoomError("Please give a short reason so the requester knows why.")
    res = get_reservation(conn, rid)
    _must_be_open(res, ("requested",))
    conn.execute(
        "UPDATE room_reservation SET status='declined', decided_by=?, decided_at=?, decide_note=?, "
        "updated_at=? WHERE id=? AND status='requested'", (by, _stamp(), note.strip(), _stamp(), rid))
    conn.commit()
    st.audit(conn, by, "room_decline", target_type="room_reservation", target_id=rid,
             summary=f"{res['title']} on {res['day']}: {note.strip()}", before="requested", after="declined")
    out = get_reservation(conn, rid)
    _emit("decided", conn, out, by)
    return out


def _is_owner(res, user_id, guest):
    """A signed-in requester owns their own reservation; a guest (reached by their signed
    tracking link, so `guest=True`) owns only reservations filed without an account."""
    if guest:
        return res["requester_user_id"] is None
    return res["requester_user_id"] is not None and res["requester_user_id"] == user_id


def withdraw(conn, rid, user_id, reason=None, actor=None, guest=False):
    """The requester takes their own request back (requested or approved). Frees the hours."""
    res = get_reservation(conn, rid)
    if res is None:
        raise RoomError("That reservation no longer exists.")
    if not _is_owner(res, user_id, guest):
        raise RoomError("You can only withdraw your own reservation.")
    _must_be_open(res, ("requested", "approved"))
    before = res["status"]
    conn.execute("UPDATE room_reservation_slot SET is_approved=0 WHERE reservation_id=?", (rid,))
    conn.execute("UPDATE room_reservation SET status='withdrawn', decide_note=COALESCE(?, decide_note), "
                 "updated_at=? WHERE id=?", ((reason or "").strip() or None, _stamp(), rid))
    conn.commit()
    st.audit(conn, actor or (f"guest:{res['ref_code']}" if guest else f"user:{user_id}"), "room_withdraw", target_type="room_reservation",
             target_id=rid, summary=f"{res['title']} on {res['day']}", before=before, after="withdrawn")
    first = conn.execute("SELECT MIN(s.start_time) FROM room_reservation_slot rs "
                         "JOIN room_slot s ON s.id=rs.slot_id WHERE rs.reservation_id=?", (rid,)).fetchone()[0]
    start = datetime.fromisoformat(f"{res['day']}T{first or '00:00'}:00")
    late = before == "approved" and start - tz.now_local() < timedelta(hours=24)
    out = get_reservation(conn, rid)
    out["late_withdrawal"] = late
    _emit("withdrawn", conn, out, late)
    return out


# --------------------------------------------------- board & display ---

def hour_label(hhmm):
    """'07:00' -> '7 AM', '13:00' -> '1 PM' (the grid's row labels)."""
    h = int(str(hhmm)[:2])
    return f"{(h % 12) or 12} {'AM' if h < 12 else 'PM'}"


def monday_of(day):
    day = _d(day)
    return day - timedelta(days=day.weekday())


def slot_range(conn, first_slot_id, last_slot_id):
    """Slot ids from the first to the last hour inclusive (either order), for the form's
    From / To selects. Raises RoomError when either isn't a bookable hour."""
    slots = list_slots(conn)
    pos = {s["id"]: i for i, s in enumerate(slots)}
    try:
        a, b = pos[int(first_slot_id)], pos[int(last_slot_id)]
    except (KeyError, TypeError, ValueError):
        raise RoomError("Pick a start and end hour.")
    a, b = min(a, b), max(a, b)
    return [s["id"] for s in slots[a:b + 1]]


def person_label(conn, username):
    """A decider's directory name, falling back to their login."""
    if not username:
        return None
    u = st.get_admin_user(conn, username)
    if u:
        return st._account_display_name(conn, u["id"]) or username
    return username


def board(conn, week_start, user_id=None, today=None, days=5):
    """Everything the availability grid needs for one week (Mon-Fri by default).

    Each cell is {slot, state, pending, mine, title, ref, cont, reason}; state is one of
    free / requested / approved / blocked / closed. `mine` marks the viewer's own open
    request or booking. Titles are shown for approved bookings only (staff-wide); a
    pending request from someone else is just a count."""
    today = today or tz.today_local()
    start = monday_of(week_start)
    slots = list_slots(conn)
    dates = [start + timedelta(days=i) for i in range(days)]
    iso = [d.isoformat() for d in dates]
    earliest = earliest_bookable(conn, today)

    held = {}                                   # (day, slot_id) -> list of reservation info
    for day, sid, rid, appr, title, ref, uid in conn.execute(
            "SELECT rs.day, rs.slot_id, r.id, rs.is_approved, r.title, r.ref_code, r.requester_user_id "
            "FROM room_reservation_slot rs JOIN room_reservation r ON r.id=rs.reservation_id "
            "WHERE rs.day BETWEEN ? AND ? AND r.status IN ('requested','approved')", (iso[0], iso[-1])):
        held.setdefault((day, sid), []).append(
            {"id": rid, "approved": bool(appr), "title": title, "ref": ref, "mine": uid == user_id and uid is not None})
    blocks = {}
    for day, sid, reason in conn.execute(
            "SELECT day, slot_id, reason FROM room_block WHERE day BETWEEN ? AND ?", (iso[0], iso[-1])):
        blocks[(day, sid)] = reason

    out_days = []
    for d, di in zip(dates, iso):
        dc = day_closed(conn, d, today)
        closed = dc[1] if dc else None
        cells, prev_res = [], None
        for s in slots:
            cell = {"slot": s, "state": "free", "pending": 0, "mine": False, "title": None,
                    "ref": None, "cont": False, "reason": None, "rid": None}
            block = blocks.get((di, s["id"])) or blocks.get((di, None))
            if closed:
                cell.update(state="closed", reason=closed)
            elif block:
                cell.update(state="blocked", reason=block)
            else:
                for h in held.get((di, s["id"]), []):
                    if h["mine"]:
                        cell["mine"] = True
                        cell["rid"] = h["id"]
                    if h["approved"]:
                        cell.update(state="approved", title=h["title"], ref=h["ref"], rid=h["id"])
                        cell["mine"] = cell["mine"] or h["mine"]
                    else:
                        cell["pending"] += 1
                        if cell["state"] == "free":
                            cell["state"] = "requested"
            res = cell["rid"] if cell["state"] == "approved" else None
            cell["cont"] = bool(res and res == prev_res)
            prev_res = res
            cells.append(cell)
        out_days.append({"date": d, "iso": di, "closed": closed, "closed_short": dc[0] if dc else None,
                         "cells": cells,
                         "is_today": d == today})
    return {"start": start, "days": out_days, "slots": slots, "earliest": earliest,
            "prev": start - timedelta(days=7), "next": start + timedelta(days=7),
            "this_week": monday_of(today)}


def timeline(conn, res, names=True):
    """'Requested Oct 9 -> Approved Oct 9 by Ana': a short plain-words history."""
    def md(ts):
        try:
            return datetime.fromisoformat(ts).strftime("%b %d").replace(" 0", " ")
        except (TypeError, ValueError):
            return ""
    bits = [f"Requested {md(res['created_at'])}".strip()]
    word = {"approved": "Approved", "declined": "Declined", "cancelled": "Cancelled",
            "withdrawn": "Withdrawn", "expired": "Expired"}.get(res["status"])
    if word:
        when = md(res["decided_at"] or res["updated_at"])
        who = (person_label(conn, res["decided_by"]) if names else "the Administrative Section") if res["decided_by"] else None
        bits.append(f"{word} {when}".strip() + (f" by {who}" if who else ""))
    return " → ".join(bits)


def hours_text(conn, res):
    """'9 AM – 11 AM' for a reservation's booked hours."""
    by = {s["id"]: s for s in list_slots(conn, active_only=False)}
    ss = [by[i] for i in res["slot_ids"] if i in by]
    if not ss:
        return ""
    return f"{hour_label(ss[0]['start_time'])} – {hour_label(ss[-1]['end_time'])}"


# ------------------------------------------------------- who approves ---

# The Administrative Section is the directory unit whose path ends in /ADMIN
# (apply_directory.py creates it as "<bureau>/ADMIN"); anything beneath it counts too.
_ADMIN_UNIT_SQL = "(ou.path = 'ADMIN' OR ou.path LIKE '%/ADMIN' OR ou.path LIKE '%/ADMIN/%' OR ou.path LIKE 'ADMIN/%')"


def is_room_admin(conn, user):
    """May this account decide room requests? Members of the Administrative Section
    (and whoever is its temporary OIC), plus the app's `admin` role as the always-there
    fallback so a request can never be stranded by a gap in the directory."""
    if not user:
        return False
    if user.get("role") == "admin":
        return True
    uid = user.get("id")
    member = conn.execute(
        "SELECT 1 FROM admin_user a JOIN resource_person rp ON rp.id=a.rp_id AND rp.is_internal=1 "
        "AND rp.archived_at IS NULL JOIN org_unit ou ON ou.id=rp.org_unit_id "
        f"WHERE a.id=? AND a.active=1 AND {_ADMIN_UNIT_SQL} LIMIT 1", (uid,)).fetchone()
    if member:
        return True
    return conn.execute(
        "SELECT 1 FROM section_oic so JOIN org_unit ou ON ou.id=so.org_unit_id "
        f"WHERE so.admin_user_id=? AND {_ADMIN_UNIT_SQL} LIMIT 1", (uid,)).fetchone() is not None


def pending_count(conn):
    return conn.execute("SELECT COUNT(*) FROM room_reservation WHERE status='requested'").fetchone()[0]


def requester_label(conn, res):
    """(name, unit or organization, is_external) for a reservation's requester."""
    if res["requester_user_id"] is None:
        return (res["ext_name"] or "Guest", res["ext_org"] or "", True)
    name = st._account_display_name(conn, res["requester_user_id"]) or "Staff"
    row = conn.execute(
        "SELECT ou.short_name FROM admin_user a LEFT JOIN resource_person rp ON rp.id=a.rp_id "
        "LEFT JOIN org_unit ou ON ou.id=rp.org_unit_id WHERE a.id=?", (res["requester_user_id"],)).fetchone()
    return (name, (row[0] if row and row[0] else ""), False)


def queue(conn):
    """Open requests for the Administrative Section's inbox, soonest first. Each carries
    what a decider needs on one card: who, when, what, the other requests wanting the same
    hours, and whether something already holds them (then Approve is withheld)."""
    out = []
    for res in list_pending(conn):
        name, unit, ext = requester_label(conn, res)
        held = conn.execute(
            "SELECT DISTINCT r.id, r.ref_code, r.title FROM room_reservation_slot mine "
            "JOIN room_reservation_slot o ON o.day=mine.day AND o.slot_id=mine.slot_id AND o.is_approved=1 "
            "JOIN room_reservation r ON r.id=o.reservation_id WHERE mine.reservation_id=? LIMIT 1",
            (res["id"],)).fetchone()
        block = conn.execute(
            "SELECT b.reason FROM room_block b JOIN room_reservation_slot rs ON rs.day=b.day "
            "AND (b.slot_id IS NULL OR b.slot_id=rs.slot_id) WHERE rs.reservation_id=? LIMIT 1",
            (res["id"],)).fetchone()
        rivals = []
        for o in competing(conn, res["id"]):
            on, ou_, oext = requester_label(conn, o)
            rivals.append({"id": o["id"], "ref": o["ref_code"], "title": o["title"], "who": on,
                           "hours": hours_text(conn, o)})
        out.append({**res, "requester_name": name, "requester_unit": unit, "is_external": ext,
                    "email_unconfirmed": bool(ext and res["ext_email"] and not res["ext_email_verified_at"]),
                    "hours": hours_text(conn, res), "rivals": rivals,
                    "when": f"{_d(res['day']):%a} {_d(res['day']).day} {_d(res['day']):%b %Y}",
                    "held_by": ({"id": held[0], "ref": held[1], "title": held[2]} if held else None),
                    "blocked": block[0] if block else None,
                    "can_approve": not held and not block})
    return out


# ---------------------------------------------- suggestions, encode, bump, blocks ---

class NeedsBump(RoomError):
    """The hours are held by approved bookings. `affected` lists what would be cancelled;
    the caller asks for a reason and tries again."""
    def __init__(self, msg, affected):
        super().__init__(msg)
        self.affected = affected


def _approved_overlapping(conn, day_iso, slot_ids):
    if not slot_ids:
        return []
    qs = ",".join("?" * len(slot_ids))
    return [r[0] for r in conn.execute(
        f"SELECT DISTINCT reservation_id FROM room_reservation_slot "
        f"WHERE day=? AND is_approved=1 AND slot_id IN ({qs}) ORDER BY reservation_id", (day_iso, *slot_ids))]


def _blocked_reason(conn, day_iso, slot_ids):
    qs = ",".join("?" * len(slot_ids))
    r = conn.execute(f"SELECT reason FROM room_block WHERE day=? AND (slot_id IS NULL OR slot_id IN ({qs})) LIMIT 1",
                     (day_iso, *slot_ids)).fetchone()
    return r[0] if r else None


def _window_label(conn, day, slot_ids):
    by = {s["id"]: s for s in list_slots(conn, active_only=False)}
    ss = [by[i] for i in slot_ids]
    d = _d(day)
    return f"{d:%a} {d.day} {d:%b} · {hour_label(ss[0]['start_time'])} – {hour_label(ss[-1]['end_time'])}"


def suggest(conn, day, slot_ids, n=3, today=None, respect_lead=True, extra_taken=(), max_ahead=MAX_DAYS_AHEAD):
    """Nearest free alternatives to (day, slot_ids): the same hours on the next working
    days, then other hours the same day, then the same hours on earlier days that are still
    ahead. Holidays, weekends and blocks are skipped. `extra_taken` = {(day_iso, slot_id)}
    to treat as already gone (a booking about to be made)."""
    today = today or tz.today_local()
    slots = list_slots(conn)
    idx = {s["id"]: i for i, s in enumerate(slots)}
    ids = sorted(slot_ids, key=lambda i: idx[i])
    k, first = len(ids), idx[ids[0]]
    taken = set(extra_taken)

    def ok_day(d):
        return (is_working_day(conn, d) and d >= today
                and day_closed(conn, d, today, override_lead=not respect_lead, max_ahead=max_ahead) is None)

    def free(d, window):
        di = d.isoformat()
        return (not _approved_overlapping(conn, di, window) and not _blocked_reason(conn, di, window)
                and not any((di, w) in taken for w in window))

    out, seen = [], set()

    def add(d, window, why):
        key = (d.isoformat(), tuple(window))
        if key in seen or len(out) >= n:
            return
        seen.add(key)
        out.append({"day": d.isoformat(), "slot_ids": list(window), "why": why,
                    "label": _window_label(conn, d, window)})

    base = _d(day)
    d, steps = base, 0                                   # 1. same hours, following working days
    while len(out) < n and steps < 10:
        d += timedelta(days=1)
        if d > today + timedelta(days=max_ahead):
            break
        if ok_day(d) and free(d, ids):
            add(d, ids, "Same hours, next free day")
        steps += 1
    if ok_day(base):                                     # 2. same day, other hours (nearest first)
        wins = [[s["id"] for s in slots[i:i + k]] for i in range(0, len(slots) - k + 1) if i != first]
        for w in sorted(wins, key=lambda w: abs(idx[w[0]] - first)):
            if free(base, w):
                add(base, w, "Same day, other hours")
    d, steps = base, 0                                   # 3. same hours, earlier days still ahead
    while len(out) < n and steps < 10:
        d -= timedelta(days=1)
        if d < today:
            break
        if ok_day(d) and free(d, ids):
            add(d, ids, "Same hours, earlier day")
        steps += 1
    return out


def _check_fields(title, modality, attendees):
    if not (title or "").strip():
        raise RoomError("Please give the meeting a title.")
    if modality not in MODALITIES:
        raise RoomError("Choose face-to-face, online or hybrid.")
    if attendees is not None and int(attendees) < 1:
        raise RoomError("Attendees must be at least 1.")


def _cancel_in_txn(conn, rid, by, reason, bumped_by=None):
    conn.execute("UPDATE room_reservation_slot SET is_approved=0 WHERE reservation_id=?", (rid,))
    conn.execute(
        "UPDATE room_reservation SET status='cancelled', decided_by=?, decided_at=?, decide_note=?, "
        "bumped_by_reservation_id=?, updated_at=? WHERE id=?", (by, _stamp(), reason, bumped_by, _stamp(), rid))


def _affected_info(conn, rids, extra_taken=(), today=None):
    out = []
    for rid in rids:
        r = get_reservation(conn, rid)
        name, unit, ext = requester_label(conn, r)
        out.append({"id": rid, "ref": r["ref_code"], "title": r["title"], "who": name, "unit": unit,
                    "hours": hours_text(conn, r), "day": r["day"],
                    "when": f"{_d(r['day']):%a} {_d(r['day']).day} {_d(r['day']):%b}",
                    "suggestions": suggest(conn, r["day"], r["slot_ids"], today=today, respect_lead=False,
                                           extra_taken=extra_taken)})
    return out


def encode(conn, *, by, title, day, slot_ids, requester_user_id=None, ext=None, purpose=None,
           attendees=None, modality="f2f", meals_requested=False, note=None, bump_reason=None,
           today=None):
    """An admin books the room for someone: approved at once (source 'encoded').

    Inside the 2-working-day notice a reason (`note`) is needed. If an approved booking
    holds the hours, raises NeedsBump listing what would be cancelled; call again with
    `bump_reason` and the new booking and the cancellations happen in ONE transaction, so
    nobody can slip into the gap."""
    _check_fields(title, modality, attendees)
    ext = ext or {}
    if requester_user_id is None and not (ext.get("name") or "").strip():
        raise RoomError("Who is this booking for? Pick a person or type a name.")
    today = today or tz.today_local()
    closed = day_closed(conn, day, today, override_lead=True)
    if closed:
        raise RoomError(closed[1])
    if _d(day) < earliest_bookable(conn, today) and not (note or "").strip():
        raise RoomError(f"This is inside the {LEAD_WORKING_DAYS}-working-day notice. Please add a reason.")
    order = _validate_slots(conn, slot_ids)
    day_iso = _d(day).isoformat()
    block = _blocked_reason(conn, day_iso, order)
    if block:
        raise SlotTaken(f"The room is unavailable for those hours ({block}).")
    held = _approved_overlapping(conn, day_iso, order)
    if held and not (bump_reason or "").strip():
        raise NeedsBump("Those hours are already booked.",
                        _affected_info(conn, held, extra_taken={(day_iso, s) for s in order}, today=today))
    now = _stamp()
    try:
        cur = conn.execute(
            "INSERT INTO room_reservation(requester_user_id, ext_name, ext_org, ext_email, ext_phone, "
            "title, purpose, attendees, modality, day, status, source, decided_by, decided_at, decide_note, "
            "meals_requested, created_by, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?, 'approved','encoded',?,?,?,?,?,?,?)",
            (requester_user_id, ext.get("name"), ext.get("org"), ext.get("email"), ext.get("phone"),
             title.strip(), (purpose or "").strip() or None, attendees, modality, day_iso, by, now,
             (note or "").strip() or None, 1 if meals_requested else 0, by, now, now))
        rid = cur.lastrowid
        conn.execute("UPDATE room_reservation SET ref_code=? WHERE id=?", (f"CR-{_d(day_iso):%y%m}-{rid:04d}", rid))
        conn.executemany("INSERT INTO room_reservation_slot(reservation_id, day, slot_id, is_approved) VALUES (?,?,?,0)",
                         [(rid, day_iso, s) for s in order])
        for old in held:                                  # free the hours first, then take them
            _cancel_in_txn(conn, old, by, bump_reason.strip(), bumped_by=rid)
        conn.execute("UPDATE room_reservation_slot SET is_approved=1 WHERE reservation_id=?", (rid,))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    st.audit(conn, by, "room_encode", target_type="room_reservation", target_id=rid,
             summary=f"{title.strip()} on {day_iso}", after="approved")
    for old in held:
        st.audit(conn, by, "room_cancel", target_type="room_reservation", target_id=old,
                 summary=f"Cancelled for {title.strip()}: {bump_reason.strip()}", before="approved", after="cancelled")
    out = get_reservation(conn, rid)
    out["bumped"] = held
    _emit("encoded", conn, out, by)
    for old in held:
        _emit("cancelled", conn, get_reservation(conn, old), by)
    return out


def take_suggestion(conn, rid, user_id, day, slot_ids, today=None, actor=None, guest=False):
    """The owner of a cancelled or declined reservation takes one of the offered
    alternatives. After a bump it is booked already approved (the admin caused the move);
    after a decline it is an ordinary new request. Only times the server itself would
    suggest right now are accepted, so a posted form can't pick an arbitrary slot."""
    res = get_reservation(conn, rid)
    if res is None or not _is_owner(res, user_id, guest):
        raise RoomError("You can only change your own reservation.")
    if res["status"] not in ("cancelled", "declined"):
        raise RoomError("This reservation doesn't need a new time.")
    today = today or tz.today_local()
    bumped = res["status"] == "cancelled" and res["bumped_by_reservation_id"] is not None
    ids = [int(s) for s in slot_ids]
    offered = suggest(conn, res["day"], res["slot_ids"], n=8, today=today, respect_lead=not bumped,
                      max_ahead=GUEST_MAX_DAYS_AHEAD if guest else MAX_DAYS_AHEAD)
    if not any(o["day"] == str(day) and o["slot_ids"] == ids for o in offered):
        raise RoomError("That time is no longer free. Pick one of the fresh suggestions.")
    if conn.execute("SELECT 1 FROM room_reservation WHERE moves_reservation_id=? AND status IN ('requested','approved')",
                    (rid,)).fetchone():
        raise RoomError("You already took a new time for this one.")
    kw = dict(title=res["title"], day=day, slot_ids=ids, requester_user_id=None if guest else user_id,
              purpose=res["purpose"], attendees=res["attendees"], modality=res["modality"],
              meals_requested=bool(res["meals_requested"]), actor=actor or f"user:{user_id}", today=today)
    if guest:                                      # the same person: carry their contact details across
        kw["ext"] = {"name": res["ext_name"], "org": res["ext_org"], "email": res["ext_email"], "phone": res["ext_phone"]}
        kw["consent_at"] = res["ext_consent_at"]
        kw["max_ahead"] = GUEST_MAX_DAYS_AHEAD
    new = _book_accepted(conn, res, kw) if bumped else request(conn, **kw)
    conn.execute("UPDATE room_reservation SET moves_reservation_id=? WHERE id=?", (rid, new["id"]))
    conn.commit()
    st.audit(conn, kw["actor"], "room_accept", target_type="room_reservation", target_id=new["id"],
             summary=f"{new['title']} moved from {res['ref_code']} to {day}", after=new["status"])
    return get_reservation(conn, new["id"])


def _book_accepted(conn, old, kw):
    """A bumped person's chosen alternative: approved immediately, source 'bump_accept',
    notice rule waived (the cancellation, not the requester, caused the short notice)."""
    ids, day_iso = kw["slot_ids"], _d(kw["day"]).isoformat()
    if _approved_overlapping(conn, day_iso, ids) or _blocked_reason(conn, day_iso, ids):
        raise RoomError("That time was just taken. Pick one of the fresh suggestions.")
    now = _stamp()
    try:
        cur = conn.execute(
            "INSERT INTO room_reservation(requester_user_id, ext_name, ext_org, ext_email, ext_phone, ext_consent_at, "
            "title, purpose, attendees, modality, day, status, source, decided_by, decided_at, decide_note, "
            "meals_requested, created_by, created_at, updated_at) "
            "VALUES (?,?,?,?,?,?,?,?,?,?,?, 'approved','bump_accept',?,?,?,?,?,?,?)",
            (kw["requester_user_id"], (kw.get("ext") or {}).get("name"), (kw.get("ext") or {}).get("org"),
             (kw.get("ext") or {}).get("email"), (kw.get("ext") or {}).get("phone"), kw.get("consent_at"),
             kw["title"], kw["purpose"], kw["attendees"], kw["modality"], day_iso,
             old["decided_by"], now, f"Moved after {old['ref_code']} was cancelled.",
             1 if kw["meals_requested"] else 0, kw["actor"], now, now))
        rid = cur.lastrowid
        conn.execute("UPDATE room_reservation SET ref_code=? WHERE id=?", (f"CR-{_d(day_iso):%y%m}-{rid:04d}", rid))
        conn.executemany("INSERT INTO room_reservation_slot(reservation_id, day, slot_id, is_approved) VALUES (?,?,?,1)",
                         [(rid, day_iso, s) for s in ids])
        conn.commit()
    except sqlite3.IntegrityError:
        conn.rollback()
        raise RoomError("That time was just taken. Pick one of the fresh suggestions.")
    return get_reservation(conn, rid)


def suggestions_for(conn, res, n=4, today=None):
    """What to offer the owner of a cancelled/declined reservation whose date is still ahead."""
    today = today or tz.today_local()
    if res["status"] not in ("cancelled", "declined") or _d(res["day"]) < today:
        return []
    bumped = res["status"] == "cancelled" and res["bumped_by_reservation_id"] is not None
    if conn.execute("SELECT 1 FROM room_reservation WHERE moves_reservation_id=? AND status IN ('requested','approved')",
                    (res["id"],)).fetchone():
        return []
    return suggest(conn, res["day"], res["slot_ids"], n=n, today=today, respect_lead=not bumped,
                   max_ahead=MAX_DAYS_AHEAD if res["requester_user_id"] is not None else GUEST_MAX_DAYS_AHEAD)


# ---- blocks ---------------------------------------------------------------

def add_block(conn, by, day, slot_ids, reason, confirm=False, today=None):
    """Close the room for a whole day (slot_ids None/empty) or some hours. Approved bookings
    in the way are cancelled, but only once `confirm` is true; until then NeedsBump lists them."""
    reason = (reason or "").strip()
    if not reason:
        raise RoomError("Say why the room is unavailable.")
    today = today or tz.today_local()
    if _d(day) < today:
        raise RoomError("That date has already passed.")
    day_iso = _d(day).isoformat()
    order = _validate_slots(conn, slot_ids) if slot_ids else [s["id"] for s in list_slots(conn)]
    held = _approved_overlapping(conn, day_iso, order)
    if held and not confirm:
        raise NeedsBump("Approved bookings are in the way.", _affected_info(
            conn, held, extra_taken={(day_iso, s) for s in order}, today=today))
    try:
        ids = []
        rows = [None] if not slot_ids else order
        for s in rows:
            ids.append(conn.execute("INSERT INTO room_block(day, slot_id, reason, created_by, created_at) VALUES (?,?,?,?,?)",
                                    (day_iso, s, reason, by, _stamp())).lastrowid)
        for old in held:
            _cancel_in_txn(conn, old, by, f"The room is unavailable: {reason}")
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    st.audit(conn, by, "room_block", target_type="room_block", target_id=ids[0],
             summary=f"{day_iso}: {reason}" + (f" ({len(held)} booking(s) cancelled)" if held else ""))
    for old in held:
        st.audit(conn, by, "room_cancel", target_type="room_reservation", target_id=old,
                 summary=f"Room unavailable: {reason}", before="approved", after="cancelled")
        _emit("cancelled", conn, get_reservation(conn, old), by)
    return {"ids": ids, "cancelled": held}


def list_blocks(conn, today=None):
    """Upcoming blocks, grouped (same day and reason) with a readable hour range."""
    today = (today or tz.today_local()).isoformat()
    slots = {s["id"]: s for s in list_slots(conn, active_only=False)}
    groups = {}
    for bid, day, sid, reason in conn.execute(
            "SELECT id, day, slot_id, reason FROM room_block WHERE day>=? ORDER BY day, slot_id", (today,)):
        g = groups.setdefault((day, reason), {"day": day, "reason": reason, "ids": [], "slots": []})
        g["ids"].append(bid)
        g["slots"].append(sid)
    out = []
    for g in groups.values():
        whole = None in g["slots"]
        ss = [slots[i] for i in g["slots"] if i in slots]
        g["whole_day"] = whole
        g["hours"] = "Whole day" if whole or not ss else f"{hour_label(ss[0]['start_time'])} – {hour_label(ss[-1]['end_time'])}"
        g["when"] = f"{_d(g['day']):%a} {_d(g['day']).day} {_d(g['day']):%b %Y}"
        out.append(g)
    return out


def remove_block(conn, by, ids):
    ids = [int(i) for i in ids]
    if not ids:
        raise RoomError("Nothing to reopen.")
    qs = ",".join("?" * len(ids))
    conn.execute(f"DELETE FROM room_block WHERE id IN ({qs})", ids)
    conn.commit()
    st.audit(conn, by, "room_unblock", target_type="room_block", target_id=ids[0], summary=f"{len(ids)} block row(s) removed")


def account_options(conn):
    """(id, name) of active accounts for the encode form's 'booking for' picker."""
    return [(r[0], r[1]) for r in conn.execute(
        "SELECT a.id, COALESCE(NULLIF(rp.name, ''), a.username) FROM admin_user a "
        "LEFT JOIN resource_person rp ON rp.id=a.rp_id WHERE a.active=1 ORDER BY 2 COLLATE NOCASE")]


def queue_when(res):
    """'Thu 15 Oct 2026' for a reservation card."""
    d = _d(res["day"])
    return f"{d:%a} {d.day} {d:%b %Y}"


# ----------------------------------------------------- guests (public QR page) ---

_EMAIL_OK = __import__("re").compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def request_external(conn, *, name, org, email, phone, title, day, slot_ids, consent, purpose=None,
                     attendees=None, modality="f2f", meals_requested=False, today=None):
    """A request from the public QR page. Same rules as a signed-in one (two working days'
    notice, back-to-back hours), a shorter horizon (60 days), a consent tick, a sane email
    and at most three open requests per email address."""
    name, org, email, phone = (name or "").strip(), (org or "").strip(), (email or "").strip(), (phone or "").strip()
    if not consent:
        raise RoomError("Please tick the box to agree to how your details are kept.")
    if not name:
        raise RoomError("Please tell us your name.")
    if not email and not phone:
        raise RoomError("Please give an email address or a phone number so we can reach you.")
    if email and not _EMAIL_OK.match(email):
        raise RoomError("That email address doesn't look right.")
    if phone and sum(c.isdigit() for c in phone) < 7:
        raise RoomError("That phone number doesn't look right.")
    if max(len(name), len(org), len(email), len(phone)) > 160 or len((title or "")) > 200 or len(purpose or "") > 600:
        raise RoomError("Something you typed is too long.")
    today = today or tz.today_local()
    if email:
        n_open = conn.execute(
            "SELECT COUNT(*) FROM room_reservation WHERE lower(ext_email)=lower(?) AND status IN ('requested','approved') "
            "AND day>=?", (email, today.isoformat())).fetchone()[0]
        if n_open >= GUEST_OPEN_LIMIT:
            raise RoomError(f"This email address already has {GUEST_OPEN_LIMIT} open requests. "
                            "Please wait for a decision or withdraw one first.")
    return request(conn, title=title, day=day, slot_ids=slot_ids, ext={"name": name, "org": org, "email": email, "phone": phone},
                   purpose=purpose, attendees=attendees, modality=modality, meals_requested=meals_requested,
                   actor=f"guest:{email or phone}", today=today, max_ahead=GUEST_MAX_DAYS_AHEAD,
                   consent_at=_stamp())


def mark_email_verified(conn, rid):
    """The guest opened the emailed tracking link: their address works (a soft check, never a block)."""
    conn.execute("UPDATE room_reservation SET ext_email_verified_at=? WHERE id=? AND ext_email_verified_at IS NULL "
                 "AND ext_email IS NOT NULL", (_stamp(), rid))
    conn.commit()


def public_day(conn, day, today=None):
    """What a guest may see of one day: each hour free / requested (others asked, you still can) /
    booked / closed. Never a title or a name."""
    today = today or tz.today_local()
    closed = day_closed(conn, day, today, max_ahead=GUEST_MAX_DAYS_AHEAD)
    states = slot_states(conn, day)
    hours = []
    for sid, o in states.items():
        s = o["slot"]
        state = "closed" if closed else {"approved": "booked", "blocked": "closed"}.get(o["state"], o["state"])
        hours.append({"id": sid, "label": f"{hour_label(s['start_time'])} – {hour_label(s['end_time'])}",
                      "start": hour_label(s["start_time"]), "state": state})
    return {"day": _d(day).isoformat(), "closed": closed[1] if closed else None, "hours": hours,
            "label": f"{_d(day):%A} {_d(day).day} {_d(day):%B %Y}"}


def public_days(conn, today=None):
    """The days a guest can ask for, soonest first, each with how many hours are still open
    (free, or only asked for by others)."""
    today = today or tz.today_local()
    out, d = [], earliest_bookable(conn, today)
    last = today + timedelta(days=GUEST_MAX_DAYS_AHEAD)
    while d <= last:
        if day_closed(conn, d, today, max_ahead=GUEST_MAX_DAYS_AHEAD) is None:
            hrs = public_day(conn, d, today)["hours"]
            out.append({"day": d.isoformat(), "label": f"{d:%a} {d.day} {d:%b}",
                        "open": sum(1 for h in hrs if h["state"] in ("free", "requested")), "of": len(hrs)})
        d += timedelta(days=1)
    return out


GUEST_RETENTION_MONTHS = 12


def purge_guest_details(conn, today=None, months=GUEST_RETENTION_MONTHS):
    """Blank a guest's name, email and phone `months` after their reservation date (the booking
    itself stays on record), and drop their email notices. Returns how many reservations changed."""
    today = today or tz.today_local()
    y, m = today.year, today.month - months
    while m <= 0:
        m += 12; y -= 1
    cutoff = date(y, m, min(today.day, 28)).isoformat()
    ids = [r[0] for r in conn.execute(
        "SELECT id FROM room_reservation WHERE requester_user_id IS NULL AND day < ? "
        "AND (ext_name IS NOT NULL OR ext_email IS NOT NULL OR ext_phone IS NOT NULL)", (cutoff,))]
    if ids:
        qs = ",".join("?" * len(ids))
        conn.execute(f"UPDATE room_reservation SET ext_name=NULL, ext_email=NULL, ext_phone=NULL, updated_at=? "
                     f"WHERE id IN ({qs})", (_stamp(), *ids))
    conn.execute("DELETE FROM room_notice WHERE recipient LIKE 'e:%' AND created_at < ?", (cutoff + "T00:00:00",))
    conn.commit()
    if ids:
        st.audit(conn, "system", "room_purge_guests", target_type="room_reservation", target_id=ids[0],
                 summary=f"Removed guest contact details from {len(ids)} reservation(s) dated before {cutoff}")
    return len(ids)
