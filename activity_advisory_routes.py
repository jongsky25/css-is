"""Routes for an activity's public advisory: the manager's editor (signed in) and the public image/PDF.

Managers (anyone `can_manage_event` allows) edit, preview, download, publish and withdraw it at
/activities/<token>/advisory. Once published, anyone may fetch the image or PDF at /e/<token>/advisory.png|pdf and the
activity's public link tree shows it. A draft is never served publicly."""
from __future__ import annotations

from collections import OrderedDict
from urllib.parse import parse_qsl, quote

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response

import activity_advisory as aa
import advisory
import storage as st

_CACHE: "OrderedDict[tuple, bytes]" = OrderedDict()      # rendered files by (event, revision, kind); revisions never repeat
_CACHE_MAX = 24
ROW_SLOTS = advisory.MAX_ROWS


def _cached(key, build):
    if key in _CACHE:
        _CACHE.move_to_end(key)
        return _CACHE[key]
    data = build()
    _CACHE[key] = data
    while len(_CACHE) > _CACHE_MAX:
        _CACHE.popitem(last=False)
    return data


def _form_fields(posted: dict) -> dict:
    rows = []
    for i in range(ROW_SLOTS):
        label, value = posted.get(f"row_label_{i}", ""), posted.get(f"row_value_{i}", "")
        if label.strip() or value.strip():
            rows.append((label, value))
    out = {k: posted.get(k, "") for k in ("headline", "attention", "body") + aa.CONTACT}
    out["rows"] = rows
    return out


def make_router(templates, get_conn, can_manage_event, share_url, base_url, audit):
    router = APIRouter()

    def _event(conn, token):
        return st.get_event(conn, token)

    def _public_event(conn, token):
        ev = st.get_event(conn, token)
        if not ev or ev.get("event_kind") == "outside" or st.event_is_archived(conn, ev["id"]):
            return None
        return ev

    def _file(a, fmt, scale=2.0):
        fields = aa.poster_fields(a, a["number"])
        if fmt == "pdf":
            return _cached((a["event_id"], a["revision"], "pdf"), lambda: advisory.render_pdf(fields)), "application/pdf"
        return _cached((a["event_id"], a["revision"], "png"), lambda: advisory.render_png(fields, scale)), "image/png"

    # ----- public ----------------------------------------------------------------------------------------------
    @router.get("/e/{event_token}/advisory.{fmt}")
    def public_advisory(event_token: str, fmt: str, download: str = ""):
        if fmt not in ("png", "pdf"):
            return Response("Not found.", status_code=404, media_type="text/plain")
        conn = get_conn()
        try:
            ev = _public_event(conn, event_token)
            a = aa.get(conn, ev["id"]) if ev else None
        finally:
            conn.close()
        if not a or not a["published"]:
            return Response("This advisory is not available.", status_code=404, media_type="text/plain")
        headers = {}                       # the site-wide browser policy decides caching (no-store); renders are cached here
        try:
            data, media = _file(a, fmt)
        except advisory.AdvisoryTooLong:
            return Response("This advisory cannot be shown.", status_code=422, media_type="text/plain")
        if download:
            headers["Content-Disposition"] = f'attachment; filename="{advisory.filename(a["number"], fmt)}"'
        return Response(data, media_type=media, headers=headers)

    # ----- managers --------------------------------------------------------------------------------------------
    def _guard(request, conn, token):
        ev = _event(conn, token)
        if not ev or not can_manage_event(request.state.user, ev, conn):
            return None
        return ev

    def _draft_values(conn, ev, request, fresh):
        """(stored advisory or None, the values the form shows)."""
        stored = aa.get(conn, ev["id"])
        if stored and not fresh:
            return stored, stored
        qr = (stored or {}).get("qr_url") or share_url(f"{base_url(request)}/e/{ev['event_token']}")
        return stored, aa.defaults(conn, ev, qr)

    @router.get("/activities/{event_token}/advisory", response_class=HTMLResponse)
    def advisory_page(request: Request, event_token: str, fresh: str = "", msg: str = "", err: str = ""):
        conn = get_conn()
        try:
            ev = _guard(request, conn, event_token)
            if not ev:
                return RedirectResponse("/", status_code=303)
            stored, values = _draft_values(conn, ev, request, bool(fresh))
            rows = list(values.get("rows") or [])
            rows += [("", "")] * max(0, min(ROW_SLOTS, len(rows) + 2) - len(rows))
            return templates.TemplateResponse(request, "activity_advisory.html", {
                "ev": ev, "adv": stored, "v": values, "rows": rows[:ROW_SLOTS], "fresh": bool(fresh),
                "msg": msg, "err": err, "limits": advisory.LIMITS, "max_rows": ROW_SLOTS,
                "rev": (stored or {}).get("revision", 0),
                "public_url": f"{base_url(request)}/e/{ev['event_token']}"})
        finally:
            conn.close()

    @router.get("/activities/{event_token}/advisory/file.{fmt}")
    def advisory_file(request: Request, event_token: str, fmt: str, draft: str = "", download: str = ""):
        """The saved advisory (or, before the first save, a preview of the starting draft) for a manager."""
        if fmt not in ("png", "pdf"):
            return Response("Not found.", status_code=404, media_type="text/plain")
        conn = get_conn()
        try:
            ev = _guard(request, conn, event_token)
            if not ev:
                return Response("Not available to you.", status_code=403, media_type="text/plain")
            stored = aa.get(conn, ev["id"])
            if stored and not draft:
                a = stored
            else:
                a = {**aa.defaults(conn, ev, share_url(f"{base_url(request)}/e/{ev['event_token']}")),
                     "event_id": ev["id"], "number": "DRAFT", "revision": f"draft-{ev['id']}"}
        finally:
            conn.close()
        try:
            if a["number"] == "DRAFT":                       # an unsaved draft is never cached
                fields = aa.poster_fields(a, "DRAFT")
                data = advisory.render_pdf(fields) if fmt == "pdf" else advisory.render_png(fields, 1.0)
                media = "application/pdf" if fmt == "pdf" else "image/png"
            else:
                data, media = _file(a, fmt)
        except advisory.AdvisoryTooLong as e:
            return Response(str(e), status_code=422, media_type="text/plain")
        headers = {"Cache-Control": "private, no-store"}
        if download:
            headers["Content-Disposition"] = f'attachment; filename="{advisory.filename(a["number"], fmt)}"'
        return Response(data, media_type=media, headers=headers)

    async def _posted(request):
        return dict(parse_qsl((await request.body()).decode("utf-8"), keep_blank_values=True))

    @router.post("/activities/{event_token}/advisory")
    async def advisory_save(request: Request, event_token: str):
        posted = await _posted(request)
        conn = get_conn()
        try:
            ev = _guard(request, conn, event_token)
            if not ev:
                return RedirectResponse("/", status_code=303)
            fields = _form_fields(posted)
            stored = aa.get(conn, ev["id"])
            fields["qr_url"] = (stored or {}).get("qr_url") or share_url(f"{base_url(request)}/e/{ev['event_token']}")
            problem = aa.validate(fields, (stored or {}).get("number") or "2026-0101-001")
            if problem:
                return RedirectResponse(f"/activities/{event_token}/advisory?err={quote(problem)}", status_code=303)
            saved = aa.save(conn, ev, fields, request.state.user)
            audit(request, conn, "advisory_save", target_type="event", target_id=ev["id"],
                  summary=f"Saved advisory No. {saved['number']} (revision {saved['revision']}) for “{ev['title']}”")
        finally:
            conn.close()
        return RedirectResponse(f"/activities/{event_token}/advisory?msg={quote('Saved as No. ' + saved['number'] + '.')}",
                                status_code=303)

    @router.post("/activities/{event_token}/advisory/publish")
    async def advisory_publish(request: Request, event_token: str):
        posted = await _posted(request)
        show = posted.get("publish") == "1"
        conn = get_conn()
        try:
            ev = _guard(request, conn, event_token)
            if not ev:
                return RedirectResponse("/", status_code=303)
            if show and (ev.get("event_kind") == "outside" or st.event_is_archived(conn, ev["id"])):
                return RedirectResponse(f"/activities/{event_token}/advisory?err=" + quote(
                    "This activity has no public link tree, so its advisory cannot be published."), status_code=303)
            if not aa.set_published(conn, ev["id"], show):
                return RedirectResponse(f"/activities/{event_token}/advisory?err=" + quote("Save the advisory first."),
                                        status_code=303)
            audit(request, conn, "advisory_publish", target_type="event", target_id=ev["id"],
                  summary=("Published" if show else "Withdrew") + f" the advisory for “{ev['title']}”")
        finally:
            conn.close()
        note = "Published on the activity's public link tree." if show else "Withdrawn from the public link tree."
        return RedirectResponse(f"/activities/{event_token}/advisory?msg={quote(note)}", status_code=303)

    return router
