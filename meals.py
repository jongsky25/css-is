"""Meal requests for any activity, without a conference room reservation."""
from datetime import date

import rooms
import rooms_meals as rm
import storage as st
import tzutil as tz

STATUS_LABEL = {**rm.STATUS_LABEL, "pending": "Awaiting order", "requested": "Ordered"}


class MealError(rooms.RoomError):
    """A user-facing meal request error."""


def get(conn, request_id):
    cur = conn.execute("SELECT * FROM meal_request WHERE id=?", (request_id,))
    row = cur.fetchone()
    if row is None:
        return None
    item = dict(zip([c[0] for c in cur.description], row))
    cur = conn.execute("SELECT * FROM meal_request_item WHERE request_id=? ORDER BY deliver_at, meal", (request_id,))
    item["items"] = [dict(zip([c[0] for c in cur.description], r)) for r in cur.fetchall()]
    item["requester_name"] = st._account_display_name(conn, item["requester_user_id"]) or "Staff"
    states = {i["status"] for i in item["items"]}
    item["overall"] = ("Withdrawn" if item["status"] == "withdrawn" else
                       STATUS_LABEL[next(iter(states))] if len(states) == 1 else "Mixed — see each meal")
    return item


def list_requests(conn, *, user_id=None, start=None, end=None):
    where, args = [], []
    for clause, value in (("requester_user_id=?", user_id), ("day>=?", start), ("day<=?", end)):
        if value is not None:
            where.append(clause)
            args.append(value)
    sql = "SELECT id FROM meal_request" + (" WHERE " + " AND ".join(where) if where else "")
    return [get(conn, r[0]) for r in conn.execute(sql + " ORDER BY day DESC, id DESC", args).fetchall()]


def validate(*, title, day, venue, pax, special_request, wanted, times, today=None):
    """Normalize the same standalone meal fields for the UI and exact previews."""
    title, venue = (title or "").strip(), (venue or "").strip()
    if not title or len(title) > 240:
        raise MealError("Give an activity title (240 characters at most).")
    if not venue or len(venue) > 240:
        raise MealError("Give the activity venue or delivery location (240 characters at most).")
    try:
        activity_day = date.fromisoformat(day)
    except (ValueError, TypeError):
        raise MealError("Choose a valid activity date.")
    day = activity_day.isoformat()
    if reason := rooms.meal_request_reason(activity_day, today):
        raise MealError(reason)
    try:
        pax = int(pax)
    except (ValueError, TypeError):
        raise MealError("Number of pax must be a number.")
    if not 1 <= pax <= 1000:
        raise MealError("Number of pax must be between 1 and 1000.")
    special = (special_request or "").strip()
    if len(special) > 800:
        raise MealError("The special request is too long (800 characters at most).")
    if not wanted or not set(wanted) <= set(rm.LABEL):
        raise MealError("Select at least one meal.")
    try:
        clean = {m: rm._clean_time(times.get(m), rm.LABEL[m]) for m in wanted}
    except rm.MealError as e:
        raise MealError(str(e)) from e
    return dict(title=title, day=day, venue=venue, pax=pax, special_request=special,
                wanted=sorted(clean), times=clean)


def create(conn, user, *, title, day, venue, pax, special_request, wanted, times, today=None, commit=True):
    if not commit and not conn.in_transaction:
        raise RuntimeError('Meal creation requires a caller-owned transaction.')
    fields = validate(title=title, day=day, venue=venue, pax=pax, special_request=special_request,
                      wanted=wanted, times=times, today=today)
    title, day, venue, pax, special, clean = (fields[k] for k in ('title','day','venue','pax','special_request','times'))
    activity_day = date.fromisoformat(day)
    now = tz.now_iso()
    try:
        rid = conn.execute(
            "INSERT INTO meal_request(requester_user_id,title,day,venue,pax,special_request,created_at,updated_at) "
            "VALUES (?,?,?,?,?,?,?,?)", (user["id"], title, day, venue, pax, special or None, now, now)).lastrowid
        conn.execute("UPDATE meal_request SET ref_code=? WHERE id=?", (f"MR-{activity_day:%y%m}-{rid:04d}", rid))
        conn.executemany("INSERT INTO meal_request_item(request_id,meal,deliver_at) VALUES (?,?,?)",
                         [(rid, m, clean[m]) for m in clean])
        if commit:
            conn.commit()
    except Exception:
        if commit:
            conn.rollback()
        raise
    st.audit(conn, user["username"], "meal_request", target_type="meal_request", target_id=rid,
             summary=f"{title} on {day}: {pax} pax at {venue}", commit=commit)
    return get(conn, rid)


def tag(conn, rid, meal, status, user, note="", today=None):
    if not rooms.is_room_admin(conn, user):
        raise MealError("Only the Administrative Section can update meal orders.")
    req = get(conn, rid)
    if not req or req["status"] != "submitted":
        raise MealError("This meal request is no longer active.")
    item = next((i for i in req["items"] if i["meal"] == meal), None)
    if not item or status not in rm.STATUSES:
        raise MealError("Choose a meal and a valid status.")
    if status == item["status"]:
        return req
    if status not in rm.MOVES[item["status"]]:
        raise MealError("That status change is not allowed.")
    if status in ("delivered", "not_delivered") and date.fromisoformat(req["day"]) > (today or tz.today_local()):
        raise MealError("Delivery can be recorded only on or after the activity date.")
    note = (note or "").strip()
    if len(note) > 200:
        raise MealError("Keep the status note within 200 characters.")
    now = tz.now_iso()
    cur = conn.execute("UPDATE meal_request_item SET status=?,status_by=?,status_at=?,status_note=? "
                       "WHERE request_id=? AND meal=? AND status=? AND EXISTS "
                       "(SELECT 1 FROM meal_request WHERE id=request_id AND status='submitted')",
                       (status, user["username"], now, note or None, rid, meal, item["status"]))
    if not cur.rowcount:
        conn.rollback()
        raise MealError("This meal was just updated. Refresh the page and try again.")
    conn.execute("UPDATE meal_request SET updated_at=? WHERE id=?", (now, rid))
    conn.commit()
    st.audit(conn, user["username"], "meal_tag", target_type="meal_request", target_id=rid,
             summary=f"{rm.LABEL[meal]}: {STATUS_LABEL[status]}", before=item["status"], after=status)
    return get(conn, rid)


def withdraw(conn, rid, user):
    req = get(conn, rid)
    if not req or req["requester_user_id"] != user["id"]:
        raise MealError("You can only withdraw your own meal requests.")
    if req["status"] == "withdrawn":
        return req
    now = tz.now_iso()
    conn.execute("UPDATE meal_request SET status='withdrawn',updated_at=? WHERE id=?", (now, rid))
    conn.execute("UPDATE meal_request_item SET status_note=CASE WHEN status='requested' "
                 "THEN 'Withdrawn after ordering: cancel with the supplier.' ELSE 'Withdrawn by requester.' END, "
                 "status='cancelled',status_by=?,status_at=? WHERE request_id=? AND status IN ('pending','requested')",
                 (user["username"], now, rid))
    conn.commit()
    st.audit(conn, user["username"], "meal_withdraw", target_type="meal_request", target_id=rid,
             summary=f"Withdrew {req['ref_code']}: {req['title']}")
    return get(conn, rid)
