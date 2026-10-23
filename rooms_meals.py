"""Conference room meal request forms (docs/ROOM_RESERVATION_PLAN.md section 8, R9).

When a reservation asks for meals the system prepares a form with the fields the Administrative
Section orders from: title of the activity, number of pax, special request for meals, and for each of
breakfast / AM snack / lunch / PM snack a yes-no with the requested delivery time. The yes/no and the
times are filled in from the booked hours, and the requester can correct them. The Administrative
Section then tags each wanted meal as it goes: pending -> requested -> delivered, not delivered or
cancelled. This module is the one place those rules live."""
from __future__ import annotations
import json
import re

import rooms
import storage as st
import tzutil as tz

MEALS = (("breakfast", "Breakfast"), ("am_snack", "AM snack"), ("lunch", "Lunch"), ("pm_snack", "PM snack"))
LABEL = dict(MEALS)
# A meal is suggested when the booking covers this hour; and asked to arrive at this time. Both can be
# changed without code through the `room_meal_times` app setting: {"lunch": {"hour": 12, "time": "11:45"}}.
DEFAULT_HOUR = {"breakfast": 7, "am_snack": 10, "lunch": 12, "pm_snack": 15}
DEFAULT_TIME = {"breakfast": "07:30", "am_snack": "10:00", "lunch": "12:00", "pm_snack": "15:00"}
STATUSES = ("pending", "requested", "delivered", "not_delivered", "cancelled")
STATUS_LABEL = {"pending": "Not yet requested", "requested": "Requested", "delivered": "Delivered",
                "not_delivered": "Not delivered", "cancelled": "Cancelled"}
STATUS_BADGE = {"pending": "amber", "requested": "blue", "delivered": "green", "not_delivered": "red", "cancelled": "grey"}
# From -> the statuses an admin may move it to. "Reopen" is how a slip is undone.
MOVES = {"pending": ("requested", "cancelled"),
         "requested": ("delivered", "not_delivered", "cancelled", "pending"),
         "delivered": ("requested",), "not_delivered": ("requested",), "cancelled": ("pending",)}
_HHMM = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")
EARLIEST, LATEST = "06:00", "19:00"


class MealError(rooms.RoomError):
    """A meal form change the rules refuse; the message is safe to show."""


def _settings(conn):
    """The admin's overrides of when each meal is suggested and when it arrives, or {} (see DEFAULT_*)."""
    try:
        raw = json.loads(st.get_setting(conn, "room_meal_times") or "{}")
    except ValueError:
        return {}
    return raw if isinstance(raw, dict) else {}


def hour_of(cfg, meal):
    h = (cfg.get(meal) or {}).get("hour")
    return h if isinstance(h, int) and 0 <= h <= 23 else DEFAULT_HOUR[meal]


def time_of(cfg, meal):
    t = (cfg.get(meal) or {}).get("time")
    return t if isinstance(t, str) and _HHMM.match(t) else DEFAULT_TIME[meal]


# ----------------------------------------------------------------- the form ---

def derive(conn, res):
    """The four lines as they should start: wanted when the booked hours include the meal's hour,
    each with its usual delivery time."""
    cfg = _settings(conn)
    by = {s["id"]: int(s["start_time"][:2]) for s in rooms.list_slots(conn, active_only=False)}
    covered = {by[i] for i in res["slot_ids"] if i in by}
    return [{"meal": m, "label": lab, "wanted": hour_of(cfg, m) in covered, "deliver_at": time_of(cfg, m)} for m, lab in MEALS]


def ensure_form(conn, rid, by=None, force=False, today=None):
    """Create the form for a reservation that asked for meals (or, with force, for one that now does).
    Safe to call again. A reservation that came from a move copies its predecessor's form."""
    res = rooms.get_reservation(conn, rid)
    if res is None or (not res["meals_requested"] and not force):
        return None
    if conn.execute("SELECT 1 FROM room_meal WHERE reservation_id=?", (rid,)).fetchone():
        return get_form(conn, rid)
    if reason := rooms.meal_request_reason(res["day"], today):
        raise MealError(reason)
    now = tz.now_iso()
    pax, special, lines = res["attendees"], None, derive(conn, res)
    prev = res["moves_reservation_id"] if res["source"] == "move" else None
    if prev:
        old = conn.execute("SELECT pax, special_request FROM room_meal WHERE reservation_id=?", (prev,)).fetchone()
        olines = {r[0]: r for r in conn.execute("SELECT meal, wanted, deliver_at FROM room_meal_item WHERE reservation_id=?", (prev,))}
        if old:
            pax, special = old
            lines = [{**ln, "wanted": bool(olines[ln["meal"]][1]), "deliver_at": olines[ln["meal"]][2] or ln["deliver_at"]}
                     if ln["meal"] in olines else ln for ln in lines]
    conn.execute("INSERT INTO room_meal(reservation_id, pax, special_request, form_version, created_at, updated_at, updated_by) "
                 "VALUES (?,?,?,1,?,?,?)", (rid, pax, special, now, now, by or "system"))
    conn.executemany("INSERT INTO room_meal_item(reservation_id, meal, wanted, deliver_at) VALUES (?,?,?,?)",
                     [(rid, ln["meal"], 1 if ln["wanted"] else 0, ln["deliver_at"]) for ln in lines])
    if not res["meals_requested"]:
        conn.execute("UPDATE room_reservation SET meals_requested=1, updated_at=? WHERE id=?", (now, rid))
    conn.commit()
    return get_form(conn, rid)


def get_form(conn, rid):
    """The form with its reservation facts, or None when there isn't one."""
    head = conn.execute("SELECT pax, special_request, form_version, created_at, updated_at, updated_by "
                        "FROM room_meal WHERE reservation_id=?", (rid,)).fetchone()
    res = rooms.get_reservation(conn, rid)
    if not head or res is None:
        return None
    rows = {r[0]: r for r in conn.execute(
        "SELECT meal, wanted, deliver_at, status, status_by, status_at, status_note FROM room_meal_item WHERE reservation_id=?", (rid,))}
    items = []
    for m, lab in MEALS:
        r = rows.get(m)
        items.append({"meal": m, "label": lab, "wanted": bool(r and r[1]), "deliver_at": (r[2] if r else None) or DEFAULT_TIME[m],
                      "status": r[3] if r else "pending", "status_by": r[4] if r else None, "status_at": r[5] if r else None,
                      "status_note": r[6] if r else None})
    name, unit, ext = rooms.requester_label(conn, res)
    return {"reservation": res, "reservation_id": rid, "pax": head[0], "special_request": head[1], "version": head[2],
            "created_at": head[3], "updated_at": head[4], "updated_by": head[5], "items": items,
            "title": res["title"], "when": rooms.queue_when(res), "hours": rooms.hours_text(conn, res),
            "requester_name": name, "requester_unit": unit, "is_external": ext,
            "locked": any(i["wanted"] and i["status"] != "pending" for i in items),
            "wanted": [i for i in items if i["wanted"]]}


def overall(form):
    """One word for the whole form, for lists: none / pending / requested / delivered / mixed / cancelled."""
    seen = {i["status"] for i in form["items"] if i["wanted"]}
    if not seen:
        return "none"
    live = seen - {"cancelled"}
    if not live:
        return "cancelled"
    return next(iter(live)) if len(live) == 1 else "mixed"


def todo(form):
    """What is left to do on a meal request, as [{"done": bool, "text": str, "optional": bool}] in the order
    it happens: the room is approved, the form is filled in, then the Administrative Section orders and the
    meals arrive. Read-only, so the page can show it to the requester and the guest alike."""
    res, wanted = form["reservation"], form["wanted"]
    live = [i for i in wanted if i["status"] != "cancelled"]
    steps = [
        {"done": res["status"] == "approved", "text": "The Administrative Section approves the room"
         if res["status"] != "approved" else "The room is approved", "optional": False},
        {"done": bool(form["pax"]), "text": "Enter the number of pax", "optional": False},
        {"done": bool(live), "text": "Mark at least one meal as needed", "optional": False},
        {"done": bool(live) and all(i["deliver_at"] for i in live), "text": "Set a delivery time for each meal you need",
         "optional": False},
        {"done": bool((form["special_request"] or "").strip()), "text": "Add any special request, such as dietary needs",
         "optional": True},
        {"done": bool(live) and all(i["status"] in ("requested", "delivered") for i in live),
         "text": "The Administrative Section orders the meals", "optional": False},
        {"done": bool(live) and all(i["status"] == "delivered" for i in live), "text": "The meals are delivered",
         "optional": False},
    ]
    return steps


# --------------------------------------------------------------- editing ---

def _clean_time(value, label):
    v = (value or "").strip()
    if not _HHMM.match(v):
        raise MealError(f"Give a delivery time for {label} like 10:00.")
    if not (EARLIEST <= v <= LATEST):
        raise MealError(f"Delivery for {label} should be between {EARLIEST} and {LATEST}.")
    return v


def save_form(conn, rid, by, *, pax, special_request, wanted, times, is_admin=False, today=None):
    """Save the requester's (or an admin's) entries. `wanted` = set of meal keys ticked yes; `times` = {meal: 'HH:MM'}.

    A requester can change the form only until the Administrative Section starts ordering from it; after
    that they ask the section. An admin may always change it: a meal whose time or yes/no they alter after
    it was requested goes back to "Not yet requested" so it is ordered again."""
    res = rooms.get_reservation(conn, rid)
    if res is None or res["status"] not in ("requested", "approved"):
        raise MealError("This reservation is no longer active, so its meal form can't be changed.")
    if wanted and (reason := rooms.meal_request_reason(res["day"], today)):
        raise MealError(reason)
    form = ensure_form(conn, rid, by, force=True, today=today)
    if form["locked"] and not is_admin:
        raise MealError("The Administrative Section has already started ordering these meals. Please ask them to change anything.")
    try:
        pax_n = int(pax) if str(pax or "").strip() else None
    except ValueError:
        raise MealError("Number of pax must be a number.")
    if pax_n is not None and not (1 <= pax_n <= 1000):
        raise MealError("Number of pax must be between 1 and 1000.")
    wanted = {m for m in wanted if m in LABEL}
    if wanted and pax_n is None:
        raise MealError("Please say how many pax the meals are for.")
    if len((special_request or "")) > 800:
        raise MealError("The special request is too long (800 characters at most).")
    clean = {m: (_clean_time(times.get(m), lab) if m in wanted else None) for m, lab in MEALS}
    now, changed = tz.now_iso(), []
    old = {i["meal"]: i for i in form["items"]}
    for m, lab in MEALS:
        o = old[m]
        want_now, time_now = m in wanted, clean[m] or o["deliver_at"]
        if want_now != o["wanted"] or (want_now and time_now != o["deliver_at"]):
            changed.append(lab)
            reset = o["wanted"] and o["status"] in ("requested", "delivered", "not_delivered")
            conn.execute("UPDATE room_meal_item SET wanted=?, deliver_at=?, status=CASE WHEN ? THEN 'pending' ELSE status END, "
                         "status_note=CASE WHEN ? THEN ? ELSE status_note END, status_by=CASE WHEN ? THEN ? ELSE status_by END, "
                         "status_at=CASE WHEN ? THEN ? ELSE status_at END WHERE reservation_id=? AND meal=?",
                         (1 if want_now else 0, time_now, reset, reset, f"Changed after it was {STATUS_LABEL[o['status']].lower()}: was {o['deliver_at']}.",
                          reset, by, reset, now, rid, m))
    sp = (special_request or "").strip() or None
    if pax_n != form["pax"] or sp != form["special_request"]:
        changed.append("pax / special request")
    if changed:
        conn.execute("UPDATE room_meal SET pax=?, special_request=?, form_version=form_version+1, updated_at=?, updated_by=? WHERE reservation_id=?",
                     (pax_n, sp, now, by, rid))
        conn.commit()
        st.audit(conn, by, "room_meal_edit", target_type="room_reservation", target_id=rid,
                 summary=f"{res['title']}: changed " + ", ".join(changed))
    out = get_form(conn, rid)
    out["changed"] = changed
    if changed and res["status"] == "approved":
        _notify(conn, "meal_revised", out)
    return out


# ------------------------------------------------------------------ tagging ---

def tag(conn, rid, meal, new_status, by, note=None, today=None):
    """Move one wanted meal along. Ordering needs the room approved; delivered / not delivered can be
    said only on or after the day; every tag records who and when."""
    if meal not in LABEL or new_status not in STATUSES:
        raise MealError("That isn't something that can be tagged.")
    res = rooms.get_reservation(conn, rid)
    form = get_form(conn, rid)
    if res is None or form is None:
        raise MealError("There is no meal form for that reservation.")
    item = next(i for i in form["items"] if i["meal"] == meal)
    if not item["wanted"]:
        raise MealError(f"{LABEL[meal]} isn't part of this request.")
    if new_status == item["status"]:
        return form
    if new_status not in MOVES[item["status"]]:
        raise MealError(f"{LABEL[meal]} is {STATUS_LABEL[item['status']].lower()}; it can't go straight to {STATUS_LABEL[new_status].lower()}.")
    if new_status == "requested" and res["status"] != "approved":
        raise MealError("Meals can be ordered only once the room booking is approved.")
    if new_status in ("delivered", "not_delivered") and rooms._d(res["day"]) > (today or tz.today_local()):
        raise MealError("That meal's day hasn't come yet, so it can't be tagged delivered or not delivered.")
    now = tz.now_iso()
    conn.execute("UPDATE room_meal_item SET status=?, status_by=?, status_at=?, status_note=? WHERE reservation_id=? AND meal=?",
                 (new_status, by, now, (note or "").strip() or None, rid, meal))
    conn.commit()
    st.audit(conn, by, "room_meal_tag", target_type="room_reservation", target_id=rid,
             summary=f"{res['title']}: {LABEL[meal]} {item['status']} -> {new_status}" + (f" ({note.strip()})" if (note or "").strip() else ""),
             before=item["status"], after=new_status)
    return get_form(conn, rid)


def tag_all_requested(conn, rid, by, note=None):
    """The Administrative Section has placed the whole order: every wanted meal still pending becomes requested."""
    form = get_form(conn, rid)
    if form is None:
        raise MealError("There is no meal form for that reservation.")
    n = 0
    for i in form["items"]:
        if i["wanted"] and i["status"] == "pending":
            tag(conn, rid, i["meal"], "requested", by, note)
            n += 1
    if not n:
        raise MealError("Nothing is waiting to be requested on this form.")
    return get_form(conn, rid)


def release(conn, rid, reason):
    """The reservation is over (withdrawn, declined, cancelled, expired or moved): its meals are not needed.
    Lines not yet delivered become cancelled; if any had already been REQUESTED the section is told to cancel
    with the supplier. Returns the number of lines that were already requested."""
    form = get_form(conn, rid)
    if form is None:
        return 0
    now, ordered = tz.now_iso(), 0
    for i in form["items"]:
        if i["wanted"] and i["status"] in ("pending", "requested"):
            ordered += i["status"] == "requested"
            conn.execute("UPDATE room_meal_item SET status='cancelled', status_by='system', status_at=?, status_note=? "
                         "WHERE reservation_id=? AND meal=?", (now, reason, rid, i["meal"]))
    conn.commit()
    if ordered:
        _notify(conn, "meal_cancel", get_form(conn, rid), text=f"{reason} Please cancel the order with the supplier.")
    return ordered


# ------------------------------------------------------------------ listing ---

def list_for_admin(conn, start, end, show="action", include_unapproved=False):
    """Meal forms for reservations from start..end (ISO dates), soonest first, each with `overall`.
    show: 'action' = something still to order or to tag; 'all' = everything in the window."""
    out = []
    for (rid,) in conn.execute(
            "SELECT m.reservation_id FROM room_meal m JOIN room_reservation r ON r.id=m.reservation_id "
            "WHERE r.day BETWEEN ? AND ? ORDER BY r.day, r.id", (start, end)).fetchall():
        f = get_form(conn, rid)
        if f is None or not f["wanted"]:
            continue
        approved = f["reservation"]["status"] == "approved"
        if not approved and not include_unapproved and f["reservation"]["status"] in ("requested",):
            f["awaiting_room"] = True
            continue
        f["awaiting_room"] = f["reservation"]["status"] == "requested"
        f["overall"] = overall(f)
        if show == "action" and not any(i["wanted"] and i["status"] in ("pending", "requested") for i in f["items"]):
            continue
        if show == "action" and f["reservation"]["status"] not in ("approved",):
            continue
        out.append(f)
    return out


def counts(conn, today=None):
    """For the tab badge: meal lines still to be requested on approved reservations from today on."""
    return conn.execute(
        "SELECT COUNT(*) FROM room_meal_item i JOIN room_reservation r ON r.id=i.reservation_id "
        "WHERE i.wanted=1 AND i.status='pending' AND r.status='approved' AND r.day>=?",
        ((today or tz.today_local()).isoformat(),)).fetchone()[0]


def _notify(conn, kind, form, text=None):
    try:
        import rooms_notify
        rooms_notify.on_meal(conn, kind, form, text)
    except Exception:                                    # noqa: BLE001 — a notice must never break the change
        try:
            conn.rollback()
        except Exception:                                # noqa: BLE001
            pass
