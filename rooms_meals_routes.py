"""Conference room meal pages (R9): the form a requester fills in, the printable PDF, and the Administrative
Section's page where each meal is tagged requested / delivered / not delivered / cancelled.

Rules live in rooms_meals.py; this module reads the request, calls them and renders. Guests reach their own form
through the signed tracking link (/room/t/<token>/meals), exactly like the rest of their reservation."""
from __future__ import annotations
from datetime import date, timedelta
from urllib.parse import parse_qs, quote, urlencode

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

import auth
import room_meal_form
import rooms
import rooms_meals as rm
import rooms_notify
import storage as st


def _d(s):
    try:
        return date.fromisoformat(s or "")
    except ValueError:
        return None


def make_router(templates, get_conn, today_local):
    router = APIRouter()
    templates.env.globals["meal_status_label"] = rm.STATUS_LABEL
    templates.env.globals["meal_status_badge"] = rm.STATUS_BADGE
    templates.env.globals["meal_clock"] = room_meal_form.clock

    def _badge():
        """Meal lines still waiting to be requested, for the Meals tab. Opens its own connection: the tab is drawn by
        a template that has none, and only section members ever ask."""
        conn = get_conn()
        try:
            return rm.counts(conn, today_local())
        except Exception:                                # noqa: BLE001
            return 0
        finally:
            conn.close()

    templates.env.globals["room_meals_badge"] = _badge

    async def _posted(request):
        raw = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
        return {k: (v[0] if v else "").strip() for k, v in raw.items()}

    def _forbidden(request):
        return templates.TemplateResponse(request, "forbidden.html", {"capability": "room meals", "show_scope": False}, status_code=403)

    def _may(conn, user, res):
        return bool(res) and bool(user) and (res["requester_user_id"] == user["id"] or rooms.is_room_admin(conn, user))

    def _read_form(f):
        """(pax, special, wanted, times) from a posted meal form."""
        wanted = {m for m, _l in rm.MEALS if f.get(f"want_{m}") == "1"}
        return f.get("pax"), f.get("special"), wanted, {m: f.get(f"time_{m}", "") for m, _l in rm.MEALS}

    # ==================================================================== the form ===
    def _form_page(request, conn, rid, *, base, user=None, token=None, err="", ok="", status_code=200):
        res = rooms.get_reservation(conn, rid)
        form = rm.get_form(conn, rid)
        guest = token is not None
        admin = bool(user) and rooms.is_room_admin(conn, user)
        live = bool(res) and res["status"] in ("requested", "approved")
        return templates.TemplateResponse(request, "rooms_meal_form.html", {
            "layout": "public_layout.html" if guest else "dash_layout.html", "nav_active": "rooms", "tab": "meals_form",
            "res": res, "when": rooms.queue_when(res), "hours": rooms.hours_text(conn, res), "f": form, "base": base, "guest": guest,
            "admin": admin, "live": live, "err": err, "ok": ok, "show_scope": False, "meals": rm.MEALS,
            "can_edit": live and (admin or not (form and form["locked"])), "room_pending": None, "mine_open": 0,
        }, status_code=status_code)

    @router.get("/rooms/meals/{rid}", response_class=HTMLResponse)
    def meal_form(request: Request, rid: int):
        conn = get_conn()
        try:
            res = rooms.get_reservation(conn, rid)
            if not _may(conn, request.state.user, res):
                return _forbidden(request)
            q = request.query_params
            return _form_page(request, conn, rid, base=f"/rooms/meals/{rid}", user=request.state.user,
                              ok="Meal form saved." if q.get("saved") else "", err=(q.get("err") or "")[:240])
        finally:
            conn.close()

    @router.post("/rooms/meals/{rid}/start")
    async def meal_start(rid: int, request: Request):
        user = request.state.user
        conn = get_conn()
        try:
            res = rooms.get_reservation(conn, rid)
            if not _may(conn, user, res):
                return _forbidden(request)
            if res["status"] not in ("requested", "approved"):
                return RedirectResponse(f"/rooms/meals/{rid}?" + urlencode({"err": "This reservation is no longer active."}), status_code=303)
            rm.ensure_form(conn, rid, user["username"], force=True)
        finally:
            conn.close()
        return RedirectResponse(f"/rooms/meals/{rid}", status_code=303)

    @router.post("/rooms/meals/{rid}")
    async def meal_save(rid: int, request: Request):
        f, user = await _posted(request), request.state.user
        conn = get_conn()
        try:
            res = rooms.get_reservation(conn, rid)
            if not _may(conn, user, res):
                return _forbidden(request)
            pax, special, wanted, times = _read_form(f)
            try:
                out = rm.save_form(conn, rid, user["username"], pax=pax, special_request=special, wanted=wanted, times=times,
                                   is_admin=rooms.is_room_admin(conn, user))
            except rm.MealError as e:
                page = _form_page(request, conn, rid, base=f"/rooms/meals/{rid}", user=user, err=str(e), status_code=400)
                return page
        finally:
            conn.close()
        return RedirectResponse(f"/rooms/meals/{rid}?saved=1", status_code=303)

    @router.get("/rooms/meals/{rid}/form.pdf")
    def meal_pdf(request: Request, rid: int):
        conn = get_conn()
        try:
            res = rooms.get_reservation(conn, rid)
            if not _may(conn, request.state.user, res):
                return _forbidden(request)
            form = rm.get_form(conn, rid)
            if form is None:
                return Response(status_code=404)
            return Response(room_meal_form.render_pdf(form), media_type="application/pdf",
                            headers={"Content-Disposition": f'inline; filename="{room_meal_form.filename(form)}"'})
        finally:
            conn.close()

    # ============================================================ guests (signed link) ===
    def _guest(conn, token):
        rid = auth.verify_room_track_token(token)
        res = rooms.get_reservation(conn, rid) if rid else None
        return res if res and res["requester_user_id"] is None else None

    def _gone(request):
        return templates.TemplateResponse(request, "room_track.html", {"invalid": True, "show_scope": False}, status_code=404)

    @router.get("/room/t/{token}/meals", response_class=HTMLResponse)
    def guest_meal_form(request: Request, token: str):
        conn = get_conn()
        try:
            res = _guest(conn, token)
            if not res:
                return _gone(request)
            q = request.query_params
            return _form_page(request, conn, res["id"], base=f"/room/t/{quote(token)}/meals", token=token,
                              ok="Meal form saved." if q.get("saved") else "", err=(q.get("err") or "")[:240])
        finally:
            conn.close()

    @router.post("/room/t/{token}/meals/start")
    async def guest_meal_start(request: Request, token: str):
        conn = get_conn()
        try:
            res = _guest(conn, token)
            if not res:
                return _gone(request)
            if res["status"] in ("requested", "approved"):
                rm.ensure_form(conn, res["id"], f"guest:{res['ref_code']}", force=True)
        finally:
            conn.close()
        return RedirectResponse(f"/room/t/{quote(token)}/meals", status_code=303)

    @router.post("/room/t/{token}/meals")
    async def guest_meal_save(request: Request, token: str):
        f = await _posted(request)
        conn = get_conn()
        try:
            res = _guest(conn, token)
            if not res:
                return _gone(request)
            pax, special, wanted, times = _read_form(f)
            try:
                rm.save_form(conn, res["id"], f"guest:{res['ref_code']}", pax=pax, special_request=special, wanted=wanted, times=times)
            except rm.MealError as e:
                return _form_page(request, conn, res["id"], base=f"/room/t/{quote(token)}/meals", token=token, err=str(e), status_code=400)
        finally:
            conn.close()
        return RedirectResponse(f"/room/t/{quote(token)}/meals?saved=1", status_code=303)

    @router.get("/room/t/{token}/meals/form.pdf")
    def guest_meal_pdf(request: Request, token: str):
        conn = get_conn()
        try:
            res = _guest(conn, token)
            form = rm.get_form(conn, res["id"]) if res else None
            if not form:
                return Response(status_code=404)
            return Response(room_meal_form.render_pdf(form), media_type="application/pdf",
                            headers={"Content-Disposition": f'inline; filename="{room_meal_form.filename(form)}"'})
        finally:
            conn.close()

    # ================================================= the Administrative Section's page ===
    @router.get("/rooms/meals", response_class=HTMLResponse)
    def meals_admin(request: Request):
        user = request.state.user
        today = today_local()
        conn = get_conn()
        try:
            if not rooms.is_room_admin(conn, user):
                return _forbidden(request)
            q = request.query_params
            start = _d(q.get("from")) or today
            end = _d(q.get("to")) or (start + timedelta(days=14))
            if end < start:
                end = start
            show = q.get("show") if q.get("show") in ("action", "all") else "action"
            forms = rm.list_for_admin(conn, start.isoformat(), end.isoformat(), show=show, include_unapproved=(q.get("waiting") == "1"))
            rooms_notify.mark_seen(conn, user["id"], rooms_notify.MEAL_KINDS)
            waiting = conn.execute(
                "SELECT COUNT(*) FROM room_meal m JOIN room_reservation r ON r.id=m.reservation_id WHERE r.status='requested' "
                "AND r.day BETWEEN ? AND ?", (start.isoformat(), end.isoformat())).fetchone()[0]
            return templates.TemplateResponse(request, "rooms_meals.html", {
                "nav_active": "rooms", "tab": "meals", "forms": forms, "start": start, "end": end, "show": show,
                "today": today, "waiting": waiting, "include_waiting": q.get("waiting") == "1",
                "msg": (q.get("msg") or "")[:200], "err": (q.get("err") or "")[:240],
                "room_pending": rooms.pending_count(conn), "mine_open": 0, "show_scope": False})
        finally:
            conn.close()

    def _back(f):
        keep = {k: f[k] for k in ("from", "to", "show", "waiting") if f.get(k)}
        return "/rooms/meals" + ("?" + urlencode(keep) if keep else "")

    @router.post("/rooms/meals/{rid}/tag")
    async def meal_tag(rid: int, request: Request):
        f, user = await _posted(request), request.state.user
        conn = get_conn()
        try:
            if not rooms.is_room_admin(conn, user):
                return _forbidden(request)
            back = _back(f)
            sep = "&" if "?" in back else "?"
            try:
                rm.tag(conn, rid, f.get("meal", ""), f.get("status", ""), user["username"], f.get("note"), today=today_local())
            except rooms.RoomError as e:
                return RedirectResponse(back + sep + urlencode({"err": str(e)}) + f"#r{rid}", status_code=303)
        finally:
            conn.close()
        return RedirectResponse(back + f"#r{rid}", status_code=303)

    @router.post("/rooms/meals/{rid}/tag-all")
    async def meal_tag_all(rid: int, request: Request):
        f, user = await _posted(request), request.state.user
        conn = get_conn()
        try:
            if not rooms.is_room_admin(conn, user):
                return _forbidden(request)
            back = _back(f)
            sep = "&" if "?" in back else "?"
            try:
                rm.tag_all_requested(conn, rid, user["username"], f.get("note"))
            except rooms.RoomError as e:
                return RedirectResponse(back + sep + urlencode({"err": str(e)}) + f"#r{rid}", status_code=303)
        finally:
            conn.close()
        return RedirectResponse(back + sep + urlencode({"msg": "Marked as requested."}) + f"#r{rid}", status_code=303)

    return router
