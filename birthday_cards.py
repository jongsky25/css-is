"""Birthday cards from teammates (docs/BIRTHDAY_GREETINGS_PLAN.md, Phase 3).

A second FastAPI APIRouter (like calendar_routes.py) so app.py does not grow. It cannot import
`app`, so app.py hands over the Jinja environment, the connection factory, "today" and its audit
helper. Login is enforced by app._auth_gate by path, and /admin/* additionally requires manage_users.

Who may send a card is decided in office_calendar.card_celebrants: only someone whose birthday the
sender may already see, only in the six days before it and on the day. Cards are held until the
morning of the birthday (birthdays.revealed_card_year).
"""
from __future__ import annotations

from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import auth
import birthdays as bd
import office_calendar as oc
import ratelimit
import storage as st

# Tap-to-fill starter lines, Tagalog then English. {name} is filled in by the page.
STARTERS = (
    "Maligayang kaarawan, {name}! Salamat sa lahat ng tulong mo. / Happy birthday, {name}! Thank you for all your help.",
    "Pagbati, {name}! Sana'y masaya ang araw mo. / Greetings, {name}! Hope you have a wonderful day.",
    "Mabuhay ka, {name}! Pagpalain ka nawa. / Cheers to you, {name}! May you be blessed.",
)


def make_router(templates, get_conn, today_local, audit):
    router = APIRouter()

    def _page(request, name, ctx, status_code=200):
        return templates.TemplateResponse(request, name, {"nav_active": "", "show_scope": False, **ctx},
                                          status_code=status_code)

    def _target(conn, viewer_id, uid, today):
        return next((c for c in oc.card_celebrants(conn, viewer_id, today) if c["user_id"] == uid), None)

    @router.get("/birthday/cards", response_class=HTMLResponse)
    def card_list(request: Request, msg: str = "", err: str = ""):
        conn = get_conn()
        try:
            today = today_local()
            rows = oc.card_celebrants(conn, request.state.user["id"], today)
        finally:
            conn.close()
        return _page(request, "birthday_cards.html", {"rows": rows, "today": today, "msg": msg, "err": err})

    def _form(request, conn, uid, today, err="", message="", design="confetti", status_code=200):
        target = _target(conn, request.state.user["id"], uid, today)
        if not target:
            return RedirectResponse("/birthday/cards?err=" + quote(
                "You can send a card to a teammate in the week before their birthday, "
                "if they have shared it with you."), status_code=303)
        if target["sent"]:
            return RedirectResponse("/birthday/cards?msg=" + quote(
                f"You already sent {target['name']} a card."), status_code=303)
        return _page(request, "birthday_card_form.html", {
            "t": target, "designs": st.CARD_DESIGNS, "max": st.CARD_MAX, "err": err,
            "message": message, "design": design,
            "starters": [x.format(name=target["name"]) for x in STARTERS],
            "on_the_day": target["date"] == today}, status_code=status_code)

    @router.get("/birthday/card/{uid}", response_class=HTMLResponse)
    def card_form(request: Request, uid: int):
        conn = get_conn()
        try:
            return _form(request, conn, uid, today_local())
        finally:
            conn.close()

    @router.post("/birthday/card/{uid}")
    async def card_send(request: Request, uid: int):
        from urllib.parse import parse_qsl
        posted = dict(parse_qsl((await request.body()).decode("utf-8"), keep_blank_values=True))
        me = request.state.user["id"]
        conn = get_conn()
        try:
            today = today_local()
            target = _target(conn, me, uid, today)
            if not target or target["sent"]:
                return _form(request, conn, uid, today)
            design, message = posted.get("design", ""), posted.get("message", "")
            if not ratelimit.allow("card", f"u{me}"):
                return _form(request, conn, uid, today, "Too many cards too fast. Wait a minute and try again.",
                             message, design, 429)
            try:
                st.card_send(conn, uid, me, target["date"].year, design, message)
            except ValueError as e:
                return _form(request, conn, uid, today, str(e), message, design, 400)
            audit(request, conn, "birthday_card_sent", target_type="user", target_id=uid,
                  summary="sent a birthday card")                    # never the message or the date
        finally:
            conn.close()
        return RedirectResponse("/birthday/cards?msg=" + quote(
            f"Your card for {target['name']} is saved. They will see it on their birthday."), status_code=303)

    @router.get("/me/cards", response_class=HTMLResponse)
    def my_cards(request: Request, msg: str = ""):
        uid = request.state.user["id"]
        conn = get_conn()
        try:
            b = st.get_birthday(conn, uid)
            cards = st.cards_for(conn, uid, bd.revealed_card_year(b["month"], b["day"], today_local())) if b else []
        finally:
            conn.close()
        return _page(request, "my_cards.html", {"cards": cards, "has_birthday": bool(b), "msg": msg})

    @router.post("/me/cards/{card_id}/hide")
    def hide_my_card(request: Request, card_id: int):
        uid = request.state.user["id"]
        conn = get_conn()
        try:
            card = st.card_get(conn, card_id)
            if card and card["to_user_id"] == uid:
                st.card_set_hidden(conn, card_id, True)
                audit(request, conn, "birthday_card_hidden", target_type="user", target_id=uid,
                      summary="hid a birthday card they received")
        finally:
            conn.close()
        return RedirectResponse("/me/cards?msg=" + quote("The card is hidden."), status_code=303)

    @router.get("/admin/birthday-cards", response_class=HTMLResponse)
    def admin_cards(request: Request, msg: str = ""):
        if not auth.can(request.state.user["role"], "manage_users"):
            return RedirectResponse("/", status_code=303)
        conn = get_conn()
        try:
            today = today_local()
            cards = st.cards_for_admin(conn, today.year) + st.cards_for_admin(conn, today.year + 1)
        finally:
            conn.close()
        return _page(request, "admin_birthday_cards.html", {"cards": cards, "msg": msg, "nav_active": "users"})

    @router.post("/admin/birthday-cards/{card_id}/hidden")
    async def admin_card_hidden(request: Request, card_id: int):
        if not auth.can(request.state.user["role"], "manage_users"):
            return RedirectResponse("/", status_code=303)
        from urllib.parse import parse_qsl
        hide = dict(parse_qsl((await request.body()).decode("utf-8"))).get("hide") == "1"
        conn = get_conn()
        try:
            card = st.card_get(conn, card_id)
            if card:
                st.card_set_hidden(conn, card_id, hide)
                audit(request, conn, "birthday_card_moderated", target_type="user", target_id=card["to_user_id"],
                      summary=f"admin {'hid' if hide else 'restored'} a birthday card")
        finally:
            conn.close()
        return RedirectResponse("/admin/birthday-cards?msg=" + quote("Saved."), status_code=303)

    return router
