"""Signed-in meal requests and the Administrative Section's order queue."""
from datetime import timedelta
from urllib.parse import parse_qs

from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

import meals
import rooms
import rooms_meals as rm


def make_router(templates, get_conn, today_local):
    router = APIRouter()

    async def posted(request):
        return {k: v[0].strip() for k, v in parse_qs((await request.body()).decode(), keep_blank_values=True).items()}

    def render(request, template, conn, **ctx):
        status = ctx.pop("status_code", 200)
        return templates.TemplateResponse(request, template, {
            "nav_active": "rooms_meals" if request.url.path == "/meals" else
                          "rooms_meals_mine" if request.url.path == "/meals/new" else "meals_mine", "show_scope": False,
            "meal_admin": rooms.is_room_admin(conn, request.state.user), "meal_types": rm.MEALS,
            "meal_labels": rm.LABEL, "status_labels": meals.STATUS_LABEL, "status_badges": rm.STATUS_BADGE,
            "today": today_local(), "meal_user_id": request.state.user["id"], **ctx,
        }, status_code=status)

    def forbidden(request, conn):
        return render(request, "forbidden.html", conn, capability="meal requests", status_code=403)

    @router.get("/meals/mine")
    def mine(request: Request):
        conn = get_conn()
        try:
            user = request.state.user
            records = meals.list_requests(conn, user_id=user["id"])
            linked = []
            for (rid,) in conn.execute("SELECT m.reservation_id FROM room_meal m JOIN room_reservation r "
                                      "ON r.id=m.reservation_id WHERE r.requester_user_id=? ORDER BY r.day DESC,r.id DESC",
                                      (user["id"],)).fetchall():
                form = rm.get_form(conn, rid)
                form["overall"] = rm.overall(form)
                linked.append(form)
            return render(request, "meals_list.html", conn, records=records, linked=linked, managing=False)
        finally:
            conn.close()

    @router.get("/meals/new")
    def new(request: Request):
        conn = get_conn()
        try:
            return render(request, "meals_new.html", conn, f={}, err="",
                          earliest=(today_local() + timedelta(days=rooms.MEAL_LEAD_DAYS)).isoformat(), times=rm.DEFAULT_TIME)
        finally:
            conn.close()

    @router.post("/meals/new")
    async def create(request: Request):
        f = await posted(request)
        conn = get_conn()
        try:
            try:
                record = meals.create(conn, request.state.user, title=f.get("title"), day=f.get("day"), venue=f.get("venue"),
                                      pax=f.get("pax"), special_request=f.get("special"),
                                      wanted={m for m, _ in rm.MEALS if f.get(f"want_{m}") == "1"},
                                      times={m: f.get(f"time_{m}") for m, _ in rm.MEALS}, today=today_local())
            except meals.MealError as e:
                return render(request, "meals_new.html", conn, f=f, err=str(e), status_code=400,
                              earliest=(today_local() + timedelta(days=rooms.MEAL_LEAD_DAYS)).isoformat(), times=rm.DEFAULT_TIME)
            return RedirectResponse(f"/meals/{record['id']}", status_code=303)
        finally:
            conn.close()

    @router.get("/meals")
    def queue(request: Request):
        conn = get_conn()
        try:
            if not rooms.is_room_admin(conn, request.state.user):
                return forbidden(request, conn)
            # Include withdrawn and completed requests so supplier cancellations and history stay visible.
            return render(request, "meals_list.html", conn, records=sorted(meals.list_requests(conn), key=lambda r: (r["day"] < today_local().isoformat(), r["day"], r["id"])),
                          linked=rm.list_for_admin(conn, "0001-01-01", "9999-12-31", show="all", include_unapproved=True), managing=True)
        finally:
            conn.close()

    @router.get("/meals/{rid}")
    def detail(request: Request, rid: int):
        conn = get_conn()
        try:
            record = meals.get(conn, rid)
            if not record or not (record["requester_user_id"] == request.state.user["id"] or
                                  rooms.is_room_admin(conn, request.state.user)):
                return forbidden(request, conn)
            return render(request, "meals_detail.html", conn, r=record, err="", moves=rm.MOVES)
        finally:
            conn.close()

    @router.post("/meals/{rid}/tag")
    async def tag(request: Request, rid: int):
        f = await posted(request)
        conn = get_conn()
        try:
            if not rooms.is_room_admin(conn, request.state.user):
                return forbidden(request, conn)
            record = meals.get(conn, rid)
            if not record:
                return forbidden(request, conn)
            try:
                meals.tag(conn, rid, f.get("meal"), f.get("status"), request.state.user, f.get("note"), today=today_local())
            except meals.MealError as e:
                return render(request, "meals_detail.html", conn, r=record, err=str(e), moves=rm.MOVES, status_code=400)
            return RedirectResponse(f"/meals/{rid}", status_code=303)
        finally:
            conn.close()

    @router.post("/meals/{rid}/withdraw")
    async def withdraw(request: Request, rid: int):
        conn = get_conn()
        try:
            record = meals.get(conn, rid)
            if not record or record["requester_user_id"] != request.state.user["id"]:
                return forbidden(request, conn)
            meals.withdraw(conn, rid, request.state.user)
            return RedirectResponse(f"/meals/{rid}", status_code=303)
        finally:
            conn.close()

    return router
