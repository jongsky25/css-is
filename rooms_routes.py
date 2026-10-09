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

import auth
import rooms
import rooms_notify
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

    def _board_page(request, conn, q, *, f=None, error="", status_code=200, ok=None, bump=None):
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
        can_encode = rooms.is_room_admin(conn, request.state.user)
        return templates.TemplateResponse(request, "rooms.html", {
            "room_pending": rooms.pending_count(conn) if can_encode else None,
            "nav_active": "rooms", "tab": "board", "board": board, "board2": board2,
            "active_day": active, "f": form, "error": error, "ok": ok, "slots": slots,
            "mine_open": mine_open, "earliest": board["earliest"], "today": today,
            "can_encode": can_encode, "accounts": rooms.account_options(conn) if can_encode else [],
            "bump": bump,
        }, status_code=status_code)

    @router.get("/rooms", response_class=HTMLResponse)
    def rooms_board(request: Request):
        q = dict(request.query_params)
        conn = get_conn()
        try:
            ok = (q.get("flash") or "")[:300] or None
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
            rooms_notify.mark_seen(conn, user["id"], rooms_notify.REQUESTER_KINDS)
            rows = rooms.list_for_user(conn, user["id"])
            for r in rows:
                r["hours"] = rooms.hours_text(conn, r)
                r["timeline"] = rooms.timeline(conn, r)
                r["badge"] = STATUS_BADGE.get(r["status"], ("grey", r["status"].title()))
                r["day_date"] = date.fromisoformat(r["day"])
                r["offers"] = rooms.suggestions_for(conn, r, today=today)
                r["was_bumped"] = r["status"] == "cancelled" and r["bumped_by_reservation_id"] is not None
            upcoming = sorted((r for r in rows if r["status"] in ("requested", "approved")
                               and r["day_date"] >= today), key=lambda r: (r["day"], r["id"]))
            attention = [r for r in rows if r["offers"]]            # cancelled/declined, date still ahead, needs a new time
            earlier = [r for r in rows if r not in upcoming and r not in attention]
            msg = err = None
            if q.get("took"):
                r = rooms.get_by_ref(conn, q.get("ok", ""))
                if r and r["requester_user_id"] == user["id"]:
                    msg = (f"New time booked: {r['ref_code']}." if r["status"] == "approved"
                           else f"New request {r['ref_code']} sent. The Administrative Section will decide.")
            elif _REF.match(q.get("ok", "")):
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
                "attention": attention,
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

    def _forbidden(request):
        return templates.TemplateResponse(
            request, "forbidden.html", {"capability": "room approvals", "show_scope": False}, status_code=403)

    @router.post("/rooms/encode")
    async def rooms_encode(request: Request):
        """An Administrative Section member books the room for someone: approved at once.
        When approved bookings are in the way the page comes back asking for a reason (Book
        anyway) and nothing changes until it is given."""
        f = await _posted(request)
        user = request.state.user
        conn = get_conn()
        try:
            if not rooms.is_room_admin(conn, user):
                return _forbidden(request)
            try:
                day = _date_or_none(f.get("day"))
                if day is None:
                    raise rooms.RoomError("Pick a date.")
                ids = rooms.slot_range(conn, f.get("from_slot"), f.get("to_slot"))
                attendees = f.get("attendees", "")
                if attendees and not attendees.isdigit():
                    raise rooms.RoomError("Attendees must be a number.")
                for_user = int(f["for_user"]) if (f.get("for_user") or "").isdigit() else None
                res = rooms.encode(
                    conn, by=user["username"], title=f.get("title"), day=day, slot_ids=ids,
                    requester_user_id=for_user,
                    ext={"name": f.get("for_name"), "org": f.get("for_org")} if not for_user else None,
                    purpose=f.get("purpose"), attendees=int(attendees) if attendees else None,
                    modality=f.get("modality") or "f2f", meals_requested=bool(f.get("meals")),
                    note=f.get("note"), bump_reason=f.get("bump_reason") if f.get("bump") else None,
                    today=today_local())
            except rooms.NeedsBump as e:
                return _board_page(request, conn, {"week": f.get("day", "")}, f=f, status_code=409,
                                   error="Those hours are already booked. Nothing has changed yet.",
                                   bump={"affected": e.affected, "reason": f.get("bump_reason", "")})
            except rooms.RoomError as e:
                return _board_page(request, conn, {"week": f.get("day", "")}, f=f, error=str(e), status_code=400)
        finally:
            conn.close()
        msg = f"Booked {res['ref_code']}: {res['title']}."
        if res.get("bumped"):
            msg += f" {len(res['bumped'])} earlier booking(s) cancelled; their owners can pick a new time."
        return RedirectResponse(f"/rooms?week={res['day']}&" + urlencode({"flash": msg}), status_code=303)

    @router.post("/rooms/{rid}/take")
    async def rooms_take(rid: int, request: Request):
        """The owner of a cancelled/declined reservation picks one of the offered new times."""
        f = await _posted(request)
        user = request.state.user
        conn = get_conn()
        try:
            try:
                ids = [int(x) for x in (f.get("slots") or "").split(",") if x.strip().isdigit()]
                new = rooms.take_suggestion(conn, rid, user["id"], f.get("day", ""), ids,
                                            today=today_local(), actor=user["username"])
            except (rooms.RoomError, ValueError) as e:
                return RedirectResponse("/rooms/mine?" + urlencode({"err": str(e)}), status_code=303)
        finally:
            conn.close()
        return RedirectResponse("/rooms/mine?" + urlencode({"ok": new["ref_code"], "took": new["status"]}), status_code=303)

    @router.get("/rooms/blocks", response_class=HTMLResponse)
    def rooms_blocks(request: Request):
        return _blocks_page(request)

    def _blocks_page(request, *, error="", msg="", f=None, confirm=None, status_code=200):
        conn = get_conn()
        try:
            if not rooms.is_room_admin(conn, request.state.user):
                return _forbidden(request)
            slots = rooms.list_slots(conn)
            return templates.TemplateResponse(request, "rooms_blocks.html", {
                "nav_active": "rooms", "tab": "blocks", "blocks": rooms.list_blocks(conn, today_local()),
                "slots": slots, "error": error, "msg": msg, "f": f or {}, "confirm": confirm,
                "room_pending": rooms.pending_count(conn),
                "mine_open": len(rooms.list_for_user(conn, request.state.user["id"], upcoming_only=True,
                                                     today=today_local())),
                "min_day": today_local()}, status_code=status_code)
        finally:
            conn.close()

    @router.post("/rooms/blocks")
    async def rooms_block_add(request: Request):
        f = await _posted(request)
        user = request.state.user
        conn = get_conn()
        try:
            if not rooms.is_room_admin(conn, user):
                return _forbidden(request)
            try:
                day = _date_or_none(f.get("day"))
                if day is None:
                    raise rooms.RoomError("Pick a date.")
                ids = None if f.get("whole_day") else rooms.slot_range(conn, f.get("from_slot"), f.get("to_slot"))
                out = rooms.add_block(conn, user["username"], day, ids, f.get("reason"),
                                      confirm=bool(f.get("confirm")), today=today_local())
            except rooms.NeedsBump as e:
                conn.close()
                return _blocks_page(request, f=f, confirm=e.affected, status_code=409,
                                    error="Approved bookings are in the way. Nothing has changed yet.")
            except rooms.RoomError as e:
                conn.close()
                return _blocks_page(request, f=f, error=str(e), status_code=400)
        finally:
            try:
                conn.close()
            except Exception:
                pass
        msg = "Room closed." + (f" {len(out['cancelled'])} booking(s) cancelled." if out["cancelled"] else "")
        return RedirectResponse("/rooms/blocks?" + urlencode({"msg": msg}), status_code=303)

    @router.post("/rooms/blocks/reopen")
    async def rooms_block_reopen(request: Request):
        raw = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
        user = request.state.user
        conn = get_conn()
        try:
            if not rooms.is_room_admin(conn, user):
                return _forbidden(request)
            try:
                rooms.remove_block(conn, user["username"], [i for i in (raw.get("ids", [""])[0]).split(",") if i.isdigit()])
            except rooms.RoomError as e:
                return RedirectResponse("/rooms/blocks?" + urlencode({"msg": str(e)}), status_code=303)
        finally:
            conn.close()
        return RedirectResponse("/rooms/blocks?" + urlencode({"msg": "Room reopened."}), status_code=303)

    # ---- decide by email link (public: the signed token IS the credential) ----
    def _link_approver(conn, rid, token):
        """The approver this token is valid for on this reservation, or None. They must still be
        an active account that may decide room requests today."""
        t_rid, uid = auth.verify_room_decide_token(token)
        if t_rid != rid or not uid:
            return None
        u = st.get_admin_user_by_id(conn, uid)
        if not u or not u.get("active") or not rooms.is_room_admin(conn, {"id": uid, "role": u.get("role")}):
            return None
        return u

    def _link_card(conn, rid):
        res = rooms.get_reservation(conn, rid)
        if not res:
            return None
        name, unit, ext = rooms.requester_label(conn, res)
        return {**res, "requester_name": name, "requester_unit": unit, "is_external": ext,
                "hours": rooms.hours_text(conn, res), "when": rooms.queue_when(res)}

    @router.get("/rooms/decide/{rid}", response_class=HTMLResponse)
    def rooms_decide_link_form(request: Request, rid: int, token: str = "", action: str = "approve"):
        """The confirm page the emailed link opens: a preview and a button the approver must click,
        so a mail client or link scanner prefetching the GET can't decide anything on its own."""
        action = action if action in ("approve", "decline") else "approve"
        conn = get_conn()
        try:
            approver = _link_approver(conn, rid, token)
            card = _link_card(conn, rid) if approver else None
            err = ""
            if card and card["status"] != "requested":
                who = rooms.person_label(conn, card["decided_by"])
                err = f"This request was already {card['status']}" + (f" by {who}." if who else ".")
                card = None
        finally:
            conn.close()
        return templates.TemplateResponse(request, "rooms_decide_link.html", {
            "valid": bool(card), "card": card, "token": token, "action": action, "err": err,
            "show_scope": False}, status_code=200 if card else 400)

    @router.post("/rooms/decide/{rid}")
    async def rooms_decide_link_submit(request: Request, rid: int):
        f = await _posted(request)
        token, action = f.get("token", ""), f.get("action", "")
        conn = get_conn()
        try:
            approver = _link_approver(conn, rid, token)
            if not approver or action not in ("approve", "decline"):
                return templates.TemplateResponse(request, "rooms_decide_link.html",
                                                  {"valid": False, "show_scope": False}, status_code=400)
            try:
                if action == "approve":
                    res = rooms.approve(conn, rid, approver["username"], f.get("note"), today=today_local())
                else:
                    res = rooms.decline(conn, rid, approver["username"], f.get("note"))
            except rooms.AlreadyDecided as e:
                return templates.TemplateResponse(request, "rooms_decide_link.html", {
                    "valid": False, "show_scope": False, "err": f"{e}"}, status_code=400)
            except rooms.RoomError as e:                  # e.g. a decline with no reason, or the hours were taken
                return templates.TemplateResponse(request, "rooms_decide_link.html", {
                    "valid": True, "card": _link_card(conn, rid), "token": token, "action": action,
                    "err": str(e), "show_scope": False}, status_code=400)
            card = _link_card(conn, rid)
        finally:
            conn.close()
        return templates.TemplateResponse(request, "rooms_decide_link.html", {
            "valid": True, "done": True, "verb": "approved" if action == "approve" else "declined",
            "card": card, "show_scope": False})

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
                    res = rooms.approve(conn, rid, user["username"], f.get("note"), today=today_local(),
                                        decline_rivals=bool(f.get("decline_rivals")))
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
