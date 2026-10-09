"""Office calendar routes (docs/OFFICE_CALENDAR_PLAN.md).

The first FastAPI APIRouter in the repo, so app.py (already ~16k lines) does not
grow. It cannot import `app` (that would be circular), so app.py hands it the
three things it needs through `make_router` — the Jinja environment, the DB
connection factory and the PH-local "today".

Login is enforced by app._auth_gate, which decides by URL path: every /calendar
route is behind it. Who may SEE which item is decided in office_calendar.py.
"""
from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse

import office_calendar as oc

AGENDA_DAYS = 14        # the agenda shows two weeks from the chosen day


def make_router(templates, get_conn, today_local):
    router = APIRouter()

    @router.get("/calendar", response_class=HTMLResponse)
    def calendar_agenda(request: Request, scope: str = oc.DEFAULT_SCOPE, day: str = ""):
        user = request.state.user
        today = today_local()
        try:
            start = date.fromisoformat(day) if day else today
        except ValueError:
            # a hand-typed or stale date bounces to today rather than 500-ing
            return RedirectResponse("/calendar", status_code=303)
        end = start + timedelta(days=AGENDA_DAYS - 1)
        conn = get_conn()
        try:
            ctx = oc.viewer_context(conn, user)
            choices = oc.scope_choices(ctx)
            if scope not in {c["key"] for c in choices}:
                scope = oc.DEFAULT_SCOPE         # also catches a pill this viewer isn't offered
            items = oc.items_between(conn, user, start, end, scope=scope)
        finally:
            conn.close()
        return templates.TemplateResponse(request, "calendar.html", {
            "nav_active": "calendar", "show_scope": False,
            "scope": scope, "scopes": choices,
            "days": oc.agenda_days(items, start, end, today),
            "start": start, "end": end, "today": today,
            "n_items": sum(1 for i in items if i["layer"] != "holidays"),
            "prev_day": (start - timedelta(days=AGENDA_DAYS)).isoformat(),
            "next_day": (start + timedelta(days=AGENDA_DAYS)).isoformat(),
            "is_today_window": start == today,
            "range_label": f"{start.strftime('%b')} {start.day} – "
                           f"{end.strftime('%b')} {end.day}, {end.year}",
        })

    return router
