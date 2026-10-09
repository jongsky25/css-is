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
MODALITIES = ("f2f", "online", "hybrid")
_SEED_KEY = "room_slots_seeded"


class RoomError(Exception):
    """A request the rules refuse. The message is safe to show the user."""


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


def day_closed_reason(conn, day, today=None, *, override_lead=False):
    """Why `day` can't be requested at all, or None. Plain words for the UI."""
    day, today = _d(day), today or tz.today_local()
    if day.weekday() >= 5:
        return "The conference room is closed on weekends."
    h = st.get_holiday(conn, day)
    if h:
        return f"Closed: {h['name']}."
    if day < today:
        return "That date has already passed."
    if not override_lead and day < earliest_bookable(conn, today):
        return (f"Requests need at least {LEAD_WORKING_DAYS} working days' notice "
                f"(earliest: {earliest_bookable(conn, today).strftime('%b %d')}).")
    if day > today + timedelta(days=MAX_DAYS_AHEAD):
        return f"Requests open up to {MAX_DAYS_AHEAD} days ahead."
    return None


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
         "calendar_entry_id, meals_requested, created_by, created_at, updated_at")


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
            attendees=None, modality="f2f", meals_requested=False, actor=None, today=None):
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
    reason = day_closed_reason(conn, day, today)
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
            "title, purpose, attendees, modality, day, status, source, meals_requested, "
            "created_by, created_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?, 'requested', ?,?,?,?,?)",
            (requester_user_id, ext.get("name"), ext.get("org"), ext.get("email"), ext.get("phone"),
             title, (purpose or "").strip() or None, attendees, modality, day_iso,
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
    return get_reservation(conn, rid)


def _must_be_open(res, want):
    if res is None:
        raise RoomError("That reservation no longer exists.")
    if res["status"] not in want:
        raise AlreadyDecided(
            f"Already {res['status']}"
            + (f" by {res['decided_by']}" if res["decided_by"] else "")
            + (f" at {res['decided_at'].replace('T', ' ')}" if res["decided_at"] else "") + ".",
            res["decided_by"], res["decided_at"], res["status"])


def approve(conn, rid, by, note=None, today=None):
    """First to act wins. Raises AlreadyDecided if someone already decided, or
    SlotTaken if another reservation holds one of the hours."""
    res = get_reservation(conn, rid)
    _must_be_open(res, ("requested",))
    if _d(res["day"]) < (today or tz.today_local()):
        raise RoomError("That date has already passed.")
    try:
        conn.execute("UPDATE room_reservation_slot SET is_approved=1 WHERE reservation_id=?", (rid,))
        conn.execute(
            "UPDATE room_reservation SET status='approved', decided_by=?, decided_at=?, "
            "decide_note=?, updated_at=? WHERE id=? AND status='requested'",
            (by, _stamp(), (note or "").strip() or None, _stamp(), rid))
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
    return get_reservation(conn, rid)


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
    return get_reservation(conn, rid)


def withdraw(conn, rid, user_id, reason=None, actor=None):
    """The requester takes their own request back (requested or approved). Frees the hours."""
    res = get_reservation(conn, rid)
    if res is None:
        raise RoomError("That reservation no longer exists.")
    if res["requester_user_id"] is None or res["requester_user_id"] != user_id:
        raise RoomError("You can only withdraw your own reservation.")
    _must_be_open(res, ("requested", "approved"))
    before = res["status"]
    conn.execute("UPDATE room_reservation_slot SET is_approved=0 WHERE reservation_id=?", (rid,))
    conn.execute("UPDATE room_reservation SET status='withdrawn', decide_note=COALESCE(?, decide_note), "
                 "updated_at=? WHERE id=?", ((reason or "").strip() or None, _stamp(), rid))
    conn.commit()
    st.audit(conn, actor or f"user:{user_id}", "room_withdraw", target_type="room_reservation",
             target_id=rid, summary=f"{res['title']} on {res['day']}", before=before, after="withdrawn")
    first = conn.execute("SELECT MIN(s.start_time) FROM room_reservation_slot rs "
                         "JOIN room_slot s ON s.id=rs.slot_id WHERE rs.reservation_id=?", (rid,)).fetchone()[0]
    start = datetime.fromisoformat(f"{res['day']}T{first or '00:00'}:00")
    late = before == "approved" and start - tz.now_local() < timedelta(hours=24)
    out = get_reservation(conn, rid)
    out["late_withdrawal"] = late          # later increments alert the section on this
    return out
