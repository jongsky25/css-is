"""Conference room pages: availability board, request panel, My reservations (R2).

Rules live in rooms.py; this module only reads the request, calls them and renders.
Any signed-in user may use these pages (the auth middleware already requires login);
approving is a later increment."""
from __future__ import annotations
import re
from datetime import date, timedelta
from urllib.parse import parse_qs, quote, urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

import auth
import ratelimit as rl
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
_NEXT_OK = ("/activities/", "/rooms", "/monitor/", "/calendar/entries/")


def _errkey(back):
    """The query key for an error shown on the page we send them back to: an activity page already uses `err`
    for its own codes, so room messages travel as `roomerr` there."""
    return "roomerr" if (back or "").startswith(("/activities/", "/calendar/entries/")) else "err"


def _safe_next(value, default):
    """A same-site path we are willing to send someone back to (an activity page or the room pages)."""
    v = (value or "").strip()
    return v if v.startswith(_NEXT_OK) and "//" not in v and "\\" not in v and len(v) < 300 else default


def _date_or_none(s):
    try:
        return date.fromisoformat(s or "")
    except ValueError:
        return None


def make_router(templates, get_conn, today_local, *, base_url=None, qr_data_uri=None):
    """`base_url(request)` and `qr_data_uri(url)` are app.py's own (this module cannot import app)."""
    router = APIRouter()
    templates.env.globals["room_hour"] = rooms.hour_label
    templates.env.globals["room_modalities"] = MODALITY_LABELS

    async def _posted(request):
        raw = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
        return {k: (v[0] if v else "").strip() for k, v in raw.items()}

    def _board_page(request, conn, q, *, f=None, error="", status_code=200, ok=None, bump=None, series=None):
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
            "bump": bump, "series": series,
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
                kw = dict(title=f.get("title"), requester_user_id=user["id"], purpose=f.get("purpose"),
                          attendees=int(attendees) if attendees else None, modality=f.get("modality") or "f2f",
                          meals_requested=bool(f.get("meals")), actor=user["username"], today=today_local(),
                          standby=bool(f.get("standby")))
                if f.get("repeat") in ("1", "2"):
                    until = _date_or_none(f.get("until"))
                    if until is None:
                        raise rooms.RoomError("Say the last date the meeting repeats on.")
                    made = rooms.request_series(conn, every_weeks=int(f["repeat"]), until=until, skip_bad=bool(f.get("skip_bad")),
                                                day=day, slot_ids=ids, **kw)
                    res = made["reservations"][0]
                    res["_n"] = len(made["reservations"])
                else:
                    res = rooms.request(conn, day=day, slot_ids=ids, **kw)
            except rooms.SeriesIssues as e:
                return _board_page(request, conn, {"week": f.get("day", "")}, f=f, status_code=409, series=e.plan,
                                   error=f"{e} Nothing has been requested yet.")
            except rooms.RoomError as e:
                return _board_page(request, conn, {"week": f.get("day", "")}, f=f, error=str(e),
                                   status_code=400)
        finally:
            conn.close()
        return RedirectResponse(f"/rooms/mine?ok={res['ref_code']}" + (f"&series={res['_n']}" if res.get("_n", 1) > 1 else ""), status_code=303)

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
                ev = conn.execute("SELECT event_token, title FROM event WHERE id=?", (r["event_id"],)).fetchone() if r["event_id"] else None
                r["activity"] = {"token": ev[0], "title": ev[1]} if ev else None
                r["linked"] = rooms.linked_to(conn, r)
                if r["status"] == "requested" and r["standby"]:
                    r["badge"] = ("amber", "○ Provisional (standby)")
                r["offers"] = rooms.suggestions_for(conn, r, today=today)
                r["series"] = rooms.series_summary(conn, r)
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
                    n = q.get("series", "")
                    msg = (f"Request {r['ref_code']} sent" + (f" for {n} dates" if n.isdigit() else "") +
                           ". The Administrative Section will decide; you'll see the result here.")
            elif q.get("done") == "series":
                msg = f"Withdrew {q.get('n', '')} date(s) of the repeating request. The hours are free again."[:200]
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

    @router.post("/rooms/{rid}/withdraw-series")
    async def rooms_withdraw_series(rid: int, request: Request):
        f = await _posted(request)
        user = request.state.user
        conn = get_conn()
        try:
            try:
                n = rooms.withdraw_series(conn, rid, user["id"], reason=f.get("reason"), actor=user["username"], today=today_local())
            except rooms.RoomError as e:
                return RedirectResponse("/rooms/mine?" + urlencode({"err": str(e)}), status_code=303)
        finally:
            conn.close()
        return RedirectResponse("/rooms/mine?" + urlencode({"done": "series", "n": n}), status_code=303)

    @router.post("/rooms/{rid}/withdraw")
    async def rooms_withdraw(rid: int, request: Request):
        f = await _posted(request)
        user = request.state.user
        back = _safe_next(f.get("next"), "")
        conn = get_conn()
        try:
            try:
                rooms.withdraw(conn, rid, user["id"], reason=f.get("reason"), actor=user["username"])
            except rooms.RoomError as e:
                return RedirectResponse((back or "/rooms/mine") + ("&" if "?" in back else "?") + urlencode({_errkey(back): str(e)}),
                                        status_code=303)
        finally:
            conn.close()
        return RedirectResponse(back or "/rooms/mine?done=withdrawn", status_code=303)

    @router.get("/rooms/api/day")
    def rooms_api_day(request: Request, date: str = ""):
        """One day's hours for the activity form's room chip (signed in): free / requested / booked /
        closed, never a title. Uses the staff rules: two working days' notice, 90 days ahead."""
        d = _date_or_none(date)
        if d is None:
            return JSONResponse({"error": "Pick a date."}, status_code=400)
        conn = get_conn()
        try:
            return JSONResponse(rooms.day_view(conn, d, today_local()))
        finally:
            conn.close()

    @router.post("/rooms/{rid}/move")
    async def rooms_move(rid: int, request: Request):
        """Make a reservation follow its activity to a new day (see rooms.request_move)."""
        f = await _posted(request)
        user = request.state.user
        back = _safe_next(f.get("next"), "/rooms/mine")
        sep = "&" if "?" in back else "?"
        conn = get_conn()
        try:
            try:
                day = _date_or_none(f.get("day"))
                if day is None:
                    raise rooms.RoomError("Pick a date.")
                new = rooms.request_move(conn, rid, day, user, today=today_local())
            except rooms.RoomError as e:
                return RedirectResponse(back + sep + urlencode({_errkey(back): str(e)}), status_code=303)
        finally:
            conn.close()
        return RedirectResponse(back + sep + urlencode({"roomok": "Move requested" if new["source"] == "move" else "Request moved"}),
                                status_code=303)

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
        back = _safe_next(f.get("next"), "")
        conn = get_conn()
        try:
            try:
                ids = [int(x) for x in (f.get("slots") or "").split(",") if x.strip().isdigit()]
                new = rooms.take_suggestion(conn, rid, user["id"], f.get("day", ""), ids,
                                            today=today_local(), actor=user["username"])
            except (rooms.RoomError, ValueError) as e:
                return RedirectResponse((back or "/rooms/mine") + ("&" if "?" in back else "?") + urlencode({_errkey(back): str(e)}),
                                        status_code=303)
        finally:
            conn.close()
        if back:
            return RedirectResponse(back + ("&" if "?" in back else "?") + urlencode({"roomok": "New time booked"
                                                                                       if new["status"] == "approved" else "New request sent"}),
                                    status_code=303)
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

    # ====================================================================
    # Guests: the permanent QR page (/room) and their tracking link. No login.
    # ====================================================================
    def _public_page(request, conn, *, f=None, error="", status_code=200, sent=False):
        f = f or {}
        today = today_local()
        days = rooms.public_days(conn, today)
        wanted = (request.query_params.get("date") or f.get("day") or "").strip()
        picked = next((d for d in days if d["day"] == wanted), None)
        slots = rooms.list_slots(conn)
        form = {"from_slot": str(slots[2]["id"]) if len(slots) > 2 else "", "modality": "f2f", **f}
        form.setdefault("to_slot", form["from_slot"])
        return templates.TemplateResponse(request, "room_public.html", {
            "days": days, "soon": days[:14], "later": days[14:], "picked": picked,
            "avail": rooms.public_day(conn, wanted, today) if picked else None,
            "f": form, "error": error, "sent": sent, "slots": slots,
            "earliest": rooms.earliest_bookable(conn, today), "show_scope": False}, status_code=status_code)

    @router.get("/room", response_class=HTMLResponse)
    @router.get("/room/", response_class=HTMLResponse)
    def room_public(request: Request):
        conn = get_conn()
        try:
            return _public_page(request, conn, sent=request.query_params.get("sent") == "1")
        finally:
            conn.close()

    @router.get("/room/day")
    def room_public_day(request: Request, date: str = ""):
        """One day's hours for the page's date picker: free / requested / booked / closed, no titles."""
        if not rl.allow("room_view", request.client.host if request.client else None):
            return JSONResponse({"error": "Too many look-ups. Please wait a moment."}, status_code=429)
        d = _date_or_none(date)
        if d is None:
            return JSONResponse({"error": "Pick a date."}, status_code=400)
        conn = get_conn()
        try:
            return JSONResponse(rooms.public_day(conn, d, today_local()))
        finally:
            conn.close()

    @router.post("/room")
    async def room_public_submit(request: Request):
        f = await _posted(request)
        ip = request.client.host if request.client else None
        conn = get_conn()
        try:
            if f.get("website"):                       # the hidden field only a bot fills in: look like it worked
                return RedirectResponse("/room?sent=1", status_code=303)
            if not rl.allow("room", ip):
                return _public_page(request, conn, f=f, status_code=429, error=(
                    "You've sent several requests in a short time. Please wait a while, or call the "
                    "Administrative Section."))
            try:
                day = _date_or_none(f.get("day"))
                if day is None:
                    raise rooms.RoomError("Pick a day first.")
                ids = rooms.slot_range(conn, f.get("from_slot"), f.get("to_slot"))
                attendees = f.get("attendees", "")
                if attendees and not attendees.isdigit():
                    raise rooms.RoomError("Attendees must be a number.")
                res = rooms.request_external(
                    conn, name=f.get("name"), org=f.get("org"), email=f.get("email"), phone=f.get("phone"),
                    title=f.get("title"), day=day, slot_ids=ids, consent=bool(f.get("consent")),
                    purpose=f.get("purpose"), attendees=int(attendees) if attendees else None,
                    modality=f.get("modality") or "f2f", meals_requested=bool(f.get("meals")),
                    today=today_local())
            except rooms.RoomError as e:
                return _public_page(request, conn, f=f, error=str(e), status_code=400)
        finally:
            conn.close()
        return RedirectResponse(f"/room/t/{quote(auth.make_room_track_token(res['id']))}?new=1", status_code=303)

    def _track(conn, token):
        rid = auth.verify_room_track_token(token)
        res = rooms.get_reservation(conn, rid) if rid else None
        return res if res and res["requester_user_id"] is None else None

    def _track_page(request, conn, token, res, *, msg="", err="", new=False, status_code=200):
        today = today_local()
        res = rooms.get_reservation(conn, res["id"])
        res["hours"] = rooms.hours_text(conn, res)
        res["when"] = rooms.queue_when(res)
        offers = rooms.suggestions_for(conn, res, today=today)
        return templates.TemplateResponse(request, "room_track.html", {
            "r": res, "token": token, "badge": STATUS_BADGE.get(res["status"], ("grey", res["status"].title())),
            "timeline": rooms.timeline(conn, res, names=False), "offers": offers,
            "was_bumped": res["status"] == "cancelled" and res["bumped_by_reservation_id"] is not None,
            "can_withdraw": res["status"] in ("requested", "approved") and rooms._d(res["day"]) >= today,
            "msg": msg, "err": err, "new": new, "show_scope": False}, status_code=status_code)

    @router.get("/room/t/{token}", response_class=HTMLResponse)
    def room_track(request: Request, token: str):
        conn = get_conn()
        try:
            res = _track(conn, token)
            if not res:
                return templates.TemplateResponse(request, "room_track.html", {"invalid": True, "show_scope": False},
                                                  status_code=404)
            new = request.query_params.get("new") == "1"
            if not new and not res["ext_email_verified_at"]:
                rooms.mark_email_verified(conn, res["id"])
            q = request.query_params
            msg = {"withdrawn": "Your request was withdrawn. The hours are free again."}.get(q.get("done"), "")
            return _track_page(request, conn, token, res, msg=msg, err=(q.get("err") or "")[:200], new=new)
        finally:
            conn.close()

    @router.post("/room/t/{token}/withdraw")
    async def room_track_withdraw(request: Request, token: str):
        f = await _posted(request)
        conn = get_conn()
        try:
            res = _track(conn, token)
            if not res:
                return templates.TemplateResponse(request, "room_track.html", {"invalid": True, "show_scope": False},
                                                  status_code=404)
            try:
                rooms.withdraw(conn, res["id"], None, reason=f.get("reason"), guest=True)
            except rooms.RoomError as e:
                return RedirectResponse(f"/room/t/{quote(token)}?" + urlencode({"err": str(e)}), status_code=303)
        finally:
            conn.close()
        return RedirectResponse(f"/room/t/{quote(token)}?done=withdrawn", status_code=303)

    @router.post("/room/t/{token}/take")
    async def room_track_take(request: Request, token: str):
        f = await _posted(request)
        conn = get_conn()
        try:
            res = _track(conn, token)
            if not res:
                return templates.TemplateResponse(request, "room_track.html", {"invalid": True, "show_scope": False},
                                                  status_code=404)
            try:
                ids = [int(x) for x in (f.get("slots") or "").split(",") if x.strip().isdigit()]
                new = rooms.take_suggestion(conn, res["id"], None, f.get("day", ""), ids, today=today_local(), guest=True)
            except rooms.RoomError as e:
                return RedirectResponse(f"/room/t/{quote(token)}?" + urlencode({"err": str(e)}), status_code=303)
        finally:
            conn.close()
        return RedirectResponse(f"/room/t/{quote(auth.make_room_track_token(new['id']))}?new=1", status_code=303)

    # ---- the door / TV display (R10) ----
    def _display_response(request, conn):
        base = base_url(request) if base_url else str(request.base_url).rstrip("/")
        data = rooms.display_data(conn, rooms.tz.now_local())
        resp = templates.TemplateResponse(request, "rooms_display.html", {
            "d": data, "qr": qr_data_uri(base + "/room") if qr_data_uri else None, "url": base + "/room", "show_scope": False})
        resp.headers["Cache-Control"] = "no-store"
        resp.headers["X-Robots-Tag"] = "noindex, nofollow"
        return resp

    @router.get("/rooms/display", response_class=HTMLResponse)
    def rooms_display(request: Request):
        """The door screen for anyone signed in (a laptop on a lectern). A TV, which can't sign in, uses its own
        private address from the setup page."""
        conn = get_conn()
        try:
            return _display_response(request, conn)
        finally:
            conn.close()

    @router.get("/rooms/display/{token}", response_class=HTMLResponse)
    def rooms_display_token(request: Request, token: str):
        conn = get_conn()
        try:
            if not rooms.display_token_ok(conn, token):
                return HTMLResponse("This display address isn't valid. Ask the Administrative Section for the current one.", status_code=404,
                                    headers={"X-Robots-Tag": "noindex, nofollow"})
            return _display_response(request, conn)
        finally:
            conn.close()

    @router.get("/rooms/display-setup", response_class=HTMLResponse)
    def rooms_display_setup(request: Request):
        return _display_setup(request)

    def _display_setup(request, msg=""):
        conn = get_conn()
        try:
            if not rooms.is_room_admin(conn, request.state.user):
                return _forbidden(request)
            base = base_url(request) if base_url else str(request.base_url).rstrip("/")
            url = f"{base}/rooms/display/{rooms.display_token(conn)}"
            return templates.TemplateResponse(request, "rooms_display_setup.html", {
                "nav_active": "rooms", "tab": "display", "url": url, "qr": qr_data_uri(url) if qr_data_uri else None,
                "titles": rooms.display_titles_on(conn), "msg": msg or (request.query_params.get("msg") or "")[:200],
                "room_pending": rooms.pending_count(conn), "mine_open": 0})
        finally:
            conn.close()

    @router.post("/rooms/display-setup")
    async def rooms_display_setup_post(request: Request):
        f = await _posted(request)
        conn = get_conn()
        try:
            if not rooms.is_room_admin(conn, request.state.user):
                return _forbidden(request)
            if f.get("action") == "reset":
                rooms.reset_display_token(conn)
                msg = "New address made. The old one no longer works, so update the TV."
            elif f.get("action") == "titles":
                st.set_setting(conn, rooms.DISPLAY_TITLES_KEY, "1" if f.get("show_titles") else "0")
                msg = "Saved."
            else:
                msg = ""
        finally:
            conn.close()
        return RedirectResponse("/rooms/display-setup?" + urlencode({"msg": msg}), status_code=303)

    # ---- the printable QR poster (section members) ----
    @router.get("/rooms/poster", response_class=HTMLResponse)
    def rooms_poster(request: Request):
        conn = get_conn()
        try:
            if not rooms.is_room_admin(conn, request.state.user):
                return _forbidden(request)
            url = (base_url(request) if base_url else str(request.base_url).rstrip("/")) + "/room"
            return templates.TemplateResponse(request, "rooms_poster.html", {
                "nav_active": "rooms", "tab": "poster", "url": url,
                "qr": qr_data_uri(url) if qr_data_uri else None,
                "room_pending": rooms.pending_count(conn),
                "mine_open": len(rooms.list_for_user(conn, request.state.user["id"], upcoming_only=True, today=today_local()))})
        finally:
            conn.close()

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
                elif f.get("action") == "confirm_standby":
                    res = rooms.confirm_standby(conn, rid, user["username"], f.get("note"), today=today_local())
                    q = {"ok": f"Confirmed {res['ref_code']}: {res['title']}."
                         + (f" {len(res['bumped'])} booking(s) released." if res["bumped"] else "")}
                elif f.get("action") == "decline":
                    res = rooms.decline(conn, rid, user["username"], f.get("note"))
                    q = {"ok": f"Declined {res['ref_code']}."}
                elif f.get("action") == "approve_series":
                    out = rooms.approve_series(conn, rid, user["username"], f.get("note"), today=today_local(),
                                               decline_rivals=bool(f.get("decline_rivals")))
                    msg = f"Approved {len(out['approved'])} date(s)."
                    if out["skipped"]:
                        msg += " Not approved: " + "; ".join(f"{m['day']} ({why.rstrip('.')})" for m, why in out["skipped"]) + "."
                    q = {"ok": msg}
                elif f.get("action") == "decline_series":
                    out = rooms.decline_series(conn, rid, user["username"], f.get("note"))
                    q = {"ok": f"Declined {len(out['declined'])} date(s)."}
                else:
                    raise rooms.RoomError("Choose Approve or Decline.")
            except rooms.RoomError as e:
                q = {"err": str(e)}
        finally:
            conn.close()
        return RedirectResponse("/approvals?" + urlencode(q) + "#rooms", status_code=303)

    return router
