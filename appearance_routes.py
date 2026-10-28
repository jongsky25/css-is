"""Administrator appearance editor and request-scoped seasonal rendering."""
import asyncio
import hashlib
import hmac
import time
from urllib.parse import parse_qsl

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

import companion_wardrobe as wardrobe
import appearance as rules
import appearance_storage as store
import auth
import storage as st

PRIVATE = {"Cache-Control": "private, no-store"}


def csrf(request):
    return hmac.new(auth._secret(), ("appearance:" + request.cookies.get(auth.COOKIE_NAME, "")).encode(), hashlib.sha256).hexdigest()


def install_context(app, get_conn, read_db):
    # Install before the authentication middleware, so auth runs first and the
    # registered session has already established the actor on request.state.
    @app.middleware("http")
    async def appearance_context(request: Request, call_next):
        if not getattr(request.state, "user", None):
            return await call_next(request)

        def read():
            def load(conn):
                active = rules.resolve(store.load(conn))
                actor = st.get_admin_user_by_id(conn, request.state.user['id']) or {}
                personal = {'kind': actor.get('avatar_kind') or st.AVATAR_DEFAULT,
                            'preferences': wardrobe.normalize(actor.get('avatar_kind') or st.AVATAR_DEFAULT, actor.get('avatar_appearance_mode'), actor.get('avatar_equipment'))}
                return active, personal
            return read_db(load)

        active, personal = await asyncio.to_thread(read)
        if request.query_params.get("appearance_preview") == "1" and auth.can(request.state.user["role"], "manage_users"):
            try:
                active.update(rules.selection(request.query_params.get("theme", "default"),
                                              request.query_params.get("outfit", "monthly"),
                                              request.query_params.get("effects") == "1",
                                              request.query_params.get("artwork") == "1" if "artwork" in request.query_params else None,
                                              request.query_params.get("banner", "")))
                active.update(month=rules.accessory_month(active["outfit"]), preview=True)
            except ValueError:
                return HTMLResponse("Choose a valid preview theme and outfit.", status_code=400, headers=PRIVATE)
        if active.get("preview"):
            personal["preferences"] = {"mode": "seasonal", "items": []}
        request.state.appearance = active
        token = rules.current.set(active)
        personal_token = wardrobe.current.set(personal)
        try:
            return await call_next(request)
        finally:
            rules.current.reset(token)
            wardrobe.current.reset(personal_token)


def make_router(templates, get_conn, read_db):
    router = APIRouter()

    def screen(request, *, error="", status=200, submitted=None):
        conn = get_conn()
        try:
            config = store.load(conn)
            active = rules.resolve(config)
            selected = config["draft"]
            submitted_selection = selected
            if submitted:
                try:
                    submitted_selection = rules.from_form(submitted)
                    if submitted.get("action") in ("draft", "publish", "defaults"):
                        selected = submitted_selection
                except ValueError:
                    pass
            editing = next((e for e in config["events"] if e["id"] == request.query_params.get("edit")), None)
            event_values = {}
            event_selection = rules.selection()
            if editing:
                event_values = {"event_id": editing["id"], "name": editing["name"], "status": editing["status"],
                                "timezone": editing["timezone"],
                                "start": rules.date_label(editing["start"], editing["timezone"], form=True),
                                "end": rules.date_label(editing["end"], editing["timezone"], form=True)}
                event_selection = editing["selection"]
            if submitted and submitted.get("action") == "event":
                event_values = submitted
                event_selection = submitted_selection
            upcoming = sorted((e for e in config["events"] if e["status"] == "published" and e["start"] > time.time()), key=lambda e: e["start"])
            context = {"show_scope": False, "nav_active": "appearance", "config": config,
                       "active": active, "selected": selected, "editing": editing,
                       "event_values": event_values, "event_selection": event_selection,
                       "upcoming": upcoming[0] if upcoming else None,
                       "events": sorted(config["events"], key=lambda e: e["start"]),
                       "themes": rules.THEMES, "outfits": rules.OUTFITS, "date_label": rules.date_label,
                       "history": store.history(conn), "csrf": csrf(request), "error": error,
                       "override_expires": submitted.get("expires", "") if submitted else "",
                       "saved": request.query_params.get("saved") == "1"}
            return templates.TemplateResponse(request, "admin_appearance.html", context, status_code=status, headers=PRIVATE)
        finally:
            conn.close()

    @router.get("/admin/appearance", response_class=HTMLResponse)
    def editor(request: Request):
        return screen(request)

    def save(request, form):
        conn = get_conn()
        try:
            store.mutate(conn, request.state.user["username"], form.get("revision"), form.get("action"), form,
                         ip=request.client.host if request.client else None)
        except ValueError as exc:
            return screen(request, error=str(exc), status=400, submitted=form)
        finally:
            conn.close()
        return RedirectResponse("/admin/appearance?saved=1", status_code=303, headers=PRIVATE)

    @router.post("/admin/appearance")
    async def update(request: Request):
        data = bytearray()
        async for chunk in request.stream():
            data.extend(chunk)
            if len(data) > 16384:
                return HTMLResponse("The form is too large.", status_code=413, headers=PRIVATE)
        try:
            fields = parse_qsl(data.decode("utf-8"), keep_blank_values=True, max_num_fields=25)
            form = dict(fields)
            if len(fields) != len(form) or not hmac.compare_digest(form.get("csrf", "").encode(), csrf(request).encode()):
                raise ValueError()
        except (ValueError, UnicodeError):
            return HTMLResponse("The form expired or is invalid. Reload and try again.", status_code=400, headers=PRIVATE)
        return await asyncio.to_thread(save, request, form)

    @router.get("/appearance/current")
    def active(request: Request):
        # Preview query parameters cannot affect the public resolver response.
        return JSONResponse(read_db(lambda conn: rules.resolve(store.load(conn))), headers=PRIVATE)

    @router.get("/appearance/avatar/{kind}/{stage}", response_class=HTMLResponse)
    def avatar(request: Request, kind: str, stage: int):
        if not st.valid_avatar_kind(kind) or not 1 <= stage <= 6:
            return HTMLResponse("Unknown avatar.", status_code=404, headers=PRIVATE)
        module = templates.env.get_template("_avatars.html").module
        return HTMLResponse(str(module.avatar_svg(kind, stage, preferences=False)), headers=PRIVATE)

    return router
