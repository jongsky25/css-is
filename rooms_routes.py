"""Conference room pages: availability board, request panel, My reservations (R2).

Rules live in rooms.py; this module only reads the request, calls them and renders.
Any signed-in user may use these pages (the auth middleware already requires login);
approving is a later increment."""
from __future__ import annotations
import re
from datetime import date, timedelta
from urllib.parse import parse_qs, urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import rooms
import storage as st

MODALITY_LABELS = {"f2f": "Face-to-face", "online": "Online", "hybrid": "Hybrid"}
STATUS_BADGE = {   # status -> (badge colour, icon + word)
    "requested": ("amber", "○ Requested"), "approved": ("green", "✓ Approved"),
    "declined": ("red", "✕ Declined"), "withdrawn": ("grey", "↩ Withdrawn"),
    "cancelled": ("red", "✕ Cancelled"), "expired": ("grey", "– Expired"),
}
_REF = re.compile(r"^CR-\d{4}-\d{4}$")


def _date_or_none(s):
    try:
        return date.fromisoformat(s or "")
    except ValueError:
        return None


def make_router(templates, get_conn, today_local):
    router = APIRouter()
    templates.env.globals["room_hour"] = rooms.hour_label
    templates.env.globals["room_modalities"] = MODALITY_LABELS

    async def _posted(request):
        raw = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
        return {k: (v[0] if v else "").strip() for k, v in raw.items()}

    def _board_page(request, conn, q, *, f=None, error="", status_code=200, ok=None):
        today = today_local()
        f = f or {}
        wanted = _date_or_none(q.get("week")) or _date_or_none(f.get("day")) or today
        board = rooms.board(conn, wanted, request.state.user["id"], today)
        board2 = rooms.board(conn, board["next"], request.state.user["id"], today)
        # The one day the phone layout shows: ?day=, else the form's date, else today, else
        # the first open day of the week.
        dates = [d["iso"] for d in board["days"]]
        active = next((x for x in (q.get("day"), f.get("day"), today.isoformat()) if x in dates), None)
        if not active:
            active = next((d["iso"] for d in board["days"] if not d["closed"]), dates[0])
        slots = board["slots"]
        defaults = {"day": q.get("date") or "", "from_slot": q.get("from") or "",
                    "to_slot": q.get("to") or "", "modality": "f2f"}
        form = {**defaults, **f}
        if not form["from_slot"] and slots:
            form["from_slot"] = str(slots[2]["id"] if len(slots) > 2 else slots[0]["id"])   # 9 AM
            form["to_slot"] = form["to_slot"] or form["from_slot"]
        mine_open = len(rooms.list_for_user(conn, request.state.user["id"], upcoming_only=True, today=today))
        return templates.TemplateResponse(request, "rooms.html", {
            "room_pending": rooms.pending_count(conn) if rooms.is_room_admin(conn, request.state.user) else None,
            "nav_active": "rooms", "tab": "board", "board": board, "board2": board2,
            "active_day": active, "f": form, "error": error, "ok": ok, "slots": slots,
            "mine_open": mine_open, "earliest": board["earliest"], "today": today,
        }, status_code=status_code)

    @router.get("/rooms", response_class=HTMLResponse)
    def rooms_board(request: Request):
        q = dict(request.query_params)
        conn = get_conn()
        try:
            ok = None
            if _REF.match(q.get("ok", "")):
                r = rooms.get_by_ref(conn, q["ok"])
                if r and r["requester_user_id"] == request.state.user["id"]:
                    ok = (f"Request {r['ref_code']} sent. The Administrative Section will decide, "
                          "and you'll see the result under My reservations.")
            return _board_page(request, conn, q, ok=ok)
        finally:
            conn.close()

    @router.post("/rooms/request")
    async def rooms_request(request: Request):
        f = await _posted(request)
        user = request.state.user
        conn = get_conn()
        try:
            try:
                day = _date_or_none(f.get("day"))
                if day is None:
                    raise rooms.RoomError("Pick a date.")
                ids = rooms.slot_range(conn, f.get("from_slot"), f.get("to_slot"))
                attendees = f.get("attendees", "")
                if attendees and not attendees.isdigit():
                    raise rooms.RoomError("Attendees must be a number.")
                res = rooms.request(
                    conn, title=f.get("title"), day=day, slot_ids=ids,
                    requester_user_id=user["id"], purpose=f.get("purpose"),
                    attendees=int(attendees) if attendees else None,
                    modality=f.get("modality") or "f2f",
                    meals_requested=bool(f.get("meals")), actor=user["username"],
                    today=today_local())
            except rooms.RoomError as e:
                return _board_page(request, conn, {"week": f.get("day", "")}, f=f, error=str(e),
                                   status_code=400)
        finally:
            conn.close()
        return RedirectResponse(f"/rooms/mine?ok={res['ref_code']}", status_code=303)

    @router.get("/rooms/mine", response_class=HTMLResponse)
    def rooms_mine(request: Request):
        q = dict(request.query_params)
        user = request.state.user
        today = today_local()
        conn = get_conn()
        try:
            rows = rooms.list_for_user(conn, user["id"])
            for r in rows:
                r["hours"] = rooms.hours_text(conn, r)
                r["timeline"] = rooms.timeline(conn, r)
                r["badge"] = STATUS_BADGE.get(r["status"], ("grey", r["status"].title()))
                r["day_date"] = date.fromisoformat(r["day"])
            upcoming = sorted((r for r in rows if r["status"] in ("requested", "approved")
                               and r["day_date"] >= today), key=lambda r: (r["day"], r["id"]))
            earlier = [r for r in rows if r not in upcoming]
            msg = err = None
            if _REF.match(q.get("ok", "")):
                r = rooms.get_by_ref(conn, q["ok"])
                if r and r["requester_user_id"] == user["id"]:
                    msg = (f"Request {r['ref_code']} sent. The Administrative Section will decide; "
                           "you'll see the result here.")
            elif q.get("done") == "withdrawn":
                msg = "Reservation withdrawn. The hours are free again."
            elif q.get("err"):
                err = q["err"][:200]
            return templates.TemplateResponse(request, "rooms_mine.html", {
                "room_pending": rooms.pending_count(conn) if rooms.is_room_admin(conn, user) else None,
                "nav_active": "rooms", "tab": "mine", "upcoming": upcoming, "earlier": earlier,
                "msg": msg, "err": err, "mine_open": len(upcoming), "today": today})
        finally:
            conn.close()

    @router.post("/rooms/{rid}/withdraw")
    async def rooms_withdraw(rid: int, request: Request):
        f = await _posted(request)
        user = request.state.user
        conn = get_conn()
        try:
            try:
                rooms.withdraw(conn, rid, user["id"], reason=f.get("reason"), actor=user["username"])
            except rooms.RoomError as e:
                return RedirectResponse("/rooms/mine?err=" + str(e).replace(" ", "+"), status_code=303)
        finally:
            conn.close()
        return RedirectResponse("/rooms/mine?done=withdrawn", status_code=303)

    @router.post("/rooms/{rid}/decide")
    async def rooms_decide(rid: int, request: Request):
        """Approve or decline a request from the Approvals inbox. First to act wins: a
        second approver is told who got there first."""
        f = await _posted(request)
        user = request.state.user
        conn = get_conn()
        try:
            if not rooms.is_room_admin(conn, user):
                return templates.TemplateResponse(
                    request, "forbidden.html", {"capability": "room approvals", "show_scope": False},
                    status_code=403)
            try:
                if f.get("action") == "approve":
                    res = rooms.approve(conn, rid, user["username"], f.get("note"), today=today_local())
                    q = {"ok": f"Approved {res['ref_code']}: {res['title']}."}
                elif f.get("action") == "decline":
                    res = rooms.decline(conn, rid, user["username"], f.get("note"))
                    q = {"ok": f"Declined {res['ref_code']}."}
                else:
                    raise rooms.RoomError("Choose Approve or Decline.")
            except rooms.RoomError as e:
                q = {"err": str(e)}
        finally:
            conn.close()
        return RedirectResponse("/approvals?" + urlencode(q) + "#rooms", status_code=303)

    return router
