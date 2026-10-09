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
from urllib.parse import parse_qs, quote, urlencode

import io
import zipfile

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

import auth
import calendar_import as ci
import calendar_import_apply as cia
import office_calendar as oc
import storage as st

MAX_UPLOAD = 8 * 1024 * 1024            # a calendar .docx is well under 1 MB
MAX_UNZIPPED = 80 * 1024 * 1024         # refuse a zip bomb before python-docx inflates it

AGENDA_DAYS = 14        # the agenda shows two weeks from the chosen day

KIND_LABELS = {"meeting": "Meeting", "training": "Training / workshop",
               "travel": "Trip / field work", "deadline": "Deadline",
               "audit_mr": "Audit / management review", "banner": "Bureau-wide notice"}
STATUS_LABELS = {"confirmed": "Confirmed", "tentative": "Tentative",
                 "postponed": "Postponed", "cancelled": "Cancelled"}
MODALITY_LABELS = {"": "Not set", "f2f": "Face to face", "online": "Online", "hybrid": "Hybrid"}
AUDIENCE_LABELS = {"unit": "Everyone in the owning unit",
                   "bureau": "Everyone in the bureau",
                   "people": "Only the people I add"}


def make_router(templates, get_conn, today_local):
    router = APIRouter()

    def _filters(kind, status, tag, unit):
        """Validated filter choices -> (filters dict for office_calendar, clean values)."""
        clean = {"kind": kind if kind in KIND_LABELS else "",
                 "status": status if status in STATUS_LABELS and status != "cancelled" else "",
                 "tag": tag.strip()[:50], "unit": unit if unit.isdigit() else ""}
        return ({"kinds": {clean["kind"]} if clean["kind"] else None,
                 "statuses": {clean["status"]} if clean["status"] else None,
                 "tags": {clean["tag"]} if clean["tag"] else None,
                 "owner_org_ids": {int(clean["unit"])} if clean["unit"] else None}, clean)

    def _qs(params, **over):
        """Query string for a link: the current choices with `over` applied, empty ones dropped."""
        merged = {**params, **over}
        return "?" + urlencode([(k, v) for k, v in merged.items() if v not in ("", None)])

    @router.get("/calendar", response_class=HTMLResponse)
    def calendar_page(request: Request, scope: str = oc.DEFAULT_SCOPE, day: str = "",
                      view: str = "agenda", month: str = "", kind: str = "",
                      status: str = "", tag: str = "", unit: str = ""):
        user = request.state.user
        today = today_local()
        view = "month" if view == "month" else "agenda"
        try:
            if view == "month":
                m = date.fromisoformat((month or today.strftime("%Y-%m")) + "-01")
                start, end = oc.month_span(m.year, m.month)
            else:
                start = date.fromisoformat(day) if day else today
                end = start + timedelta(days=AGENDA_DAYS - 1)
        except ValueError:
            # a hand-typed or stale date bounces to today rather than 500-ing
            return RedirectResponse("/calendar" + ("?view=month" if view == "month" else ""),
                                    status_code=303)
        filters, clean = _filters(kind, status, tag, unit)
        conn = get_conn()
        try:
            ctx = oc.viewer_context(conn, user)
            choices = oc.scope_choices(ctx)
            if scope not in {c["key"] for c in choices}:
                scope = oc.DEFAULT_SCOPE         # also catches a pill this viewer isn't offered
            everything = oc.items_between(conn, user, start, end, scope=scope)
        finally:
            conn.close()
        items = oc.apply_filters(everything, filters)
        entries = [i for i in everything if i["layer"] == "entries"]
        # the filter menus list what is IN this window (before filtering), so choosing
        # one never makes the other options vanish
        units = {}
        for i in entries:
            if i["owner_org_id"]:
                units[i["owner_org_id"]] = {"id": i["owner_org_id"], "label": i["owner_label"],
                                            "tone": i["tone"]}
        params = {"scope": scope, "view": "month" if view == "month" else "",
                  "month": m.strftime("%Y-%m") if view == "month" and month else "", **clean}
        page = {
            "nav_active": "calendar", "show_scope": False, "view": view,
            "can_import": auth.can(user["role"], "manage_users"),
            "scope": scope, "scopes": choices, "today": today, "start": start, "end": end,
            "n_items": sum(1 for i in items if i["layer"] != "holidays"),
            "f": clean, "filtered": any(clean.values()),
            "kinds": KIND_LABELS,
            "statuses": {k: v for k, v in STATUS_LABELS.items() if k != "cancelled"},
            "tags": sorted({t for i in entries for t in i["tags"]}, key=str.lower),
            "units": sorted(units.values(), key=lambda u: u["label"].lower()),
            "qs": lambda **over: _qs(params, **over),
            "clear_filters": _qs({**params, "kind": "", "status": "", "tag": "", "unit": ""}),
        }
        if view == "month":
            grid = oc.month_grid(items, m.year, m.month, today)
            page.update(grid=grid, weekdays=oc.WEEKDAY_NAMES, month_key=m.strftime("%Y-%m"),
                        is_today_window=(m.year, m.month) == (today.year, today.month),
                        range_label=f"{grid['title']} · {page['n_items']} "
                                    f"{'item' if page['n_items'] == 1 else 'items'}",
                        add_day=(today if (m.year, m.month) == (today.year, today.month)
                                 else m).isoformat())
        else:
            page.update(days=oc.agenda_days(items, start, end, today),
                        prev_day=(start - timedelta(days=AGENDA_DAYS)).isoformat(),
                        next_day=(start + timedelta(days=AGENDA_DAYS)).isoformat(),
                        is_today_window=start == today, add_day=start.isoformat(),
                        range_label=f"{start.strftime('%b')} {start.day} – "
                                    f"{end.strftime('%b')} {end.day}, {end.year} · "
                                    f"{page['n_items']} {'item' if page['n_items'] == 1 else 'items'}")
        return templates.TemplateResponse(request, "calendar.html", page)

    # ── add / view / edit / cancel / restore ────────────────────────────────
    # Everyone signed in may add and edit (owner decision). What a person may
    # SEE still rules: an entry they cannot see answers 404, same as a missing one.

    def _not_found(request):
        return templates.TemplateResponse(request, "calendar_entry.html",
                                          {"nav_active": "calendar", "missing": True},
                                          status_code=404)

    def _form_page(request, conn, f, *, entry=None, error="", conflict=None, status_code=200):
        return templates.TemplateResponse(request, "calendar_entry_form.html", {
            "nav_active": "calendar", "f": f, "entry": entry, "error": error,
            "conflict": conflict, "kinds": KIND_LABELS, "statuses": STATUS_LABELS,
            "modalities": MODALITY_LABELS, "audiences": AUDIENCE_LABELS,
            "units": oc.unit_choices(conn), "people": oc.people_choices(conn),
        }, status_code=status_code)

    def _blank_form(conn, user, day):
        ctx = oc.viewer_context(conn, user)
        owner = ""
        if ctx["section_path"]:
            r = conn.execute("SELECT id FROM org_unit WHERE path=?",
                             (ctx["section_path"],)).fetchone()
            owner = str(r[0]) if r else ""
        return {"title": "", "kind": "meeting", "status": "confirmed", "start_date": day,
                "end_date": "", "start_time": "", "end_time": "", "time_note": "",
                "venue": "", "modality": "", "meeting_url": "", "note": "",
                "owner_org_id": owner, "audience": "unit", "people": [], "tags": "",
                "updated_at": ""}

    def _entry_form(e):
        return {"title": e["title"], "kind": e["kind"], "status": e["status"],
                "start_date": e["start_date"], "end_date": e["end_date"] or "",
                "start_time": e["start_time"] or "", "end_time": e["end_time"] or "",
                "time_note": e["time_note"] or "", "venue": e["venue"] or "",
                "modality": e["modality"] or "", "meeting_url": e["meeting_url"] or "",
                "note": e["note"] or "",
                "owner_org_id": str(e["owner_org_id"] or ""), "audience": e["audience"],
                "people": [str(p["user_id"]) for p in e["people"]],
                "tags": ", ".join(e["tags"]), "updated_at": e["updated_at"] or ""}

    async def _posted_form(request):
        raw = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
        one = {k: (v[0] if v else "").strip() for k, v in raw.items()}
        one["people"] = [x for x in raw.get("people", []) if x.isdigit()]
        return one

    def _parse(f, existing=None, allowed_people=()):
        """(storage fields, people [(uid, role)], tags, error) from a posted form."""
        if f["kind"] not in KIND_LABELS:
            return None, None, None, "Pick a type from the list."
        if f["status"] not in STATUS_LABELS or f["status"] == "cancelled":
            return None, None, None, "Pick a status from the list."
        if any(int(u) not in allowed_people for u in f["people"]):
            return None, None, None, "One of the people you chose isn't an active account."
        if f["audience"] == "people" and not f["people"]:
            return None, None, None, "Choose who this is for, or pick a wider audience."
        if f["audience"] == "unit" and not f["owner_org_id"]:
            return None, None, None, ("Choose the unit this belongs to, or nobody outside "
                                      "the people you add will see it.")
        fields = {k: f.get(k, "") or None for k in (
            "end_date", "start_time", "end_time", "time_note", "venue", "modality",
            "meeting_url", "note")}
        fields.update(title=f["title"], start_date=f["start_date"], kind=f["kind"],
                      status=f["status"], audience=f["audience"],
                      owner_org_id=int(f["owner_org_id"]) if f["owner_org_id"].isdigit() else None)
        had = {p["user_id"]: p["role"] for p in (existing or {}).get("people", [])}
        default = "travel" if f["kind"] == "travel" else "attending"
        people = [(int(u), "lead" if had.get(int(u)) == "lead" else default)
                  for u in f["people"]]
        tags = [t for t in f.get("tags", "").split(",")]
        return fields, people, tags, ""

    def _blank_form_defaults():
        return {"title": "", "kind": "meeting", "status": "confirmed", "start_date": "",
                "end_date": "", "start_time": "", "end_time": "", "time_note": "",
                "venue": "", "modality": "", "meeting_url": "", "note": "",
                "owner_org_id": "", "audience": "unit", "tags": "", "updated_at": ""}

    @router.get("/calendar/new", response_class=HTMLResponse)
    def calendar_new(request: Request, day: str = ""):
        try:
            day = date.fromisoformat(day).isoformat() if day else today_local().isoformat()
        except ValueError:
            day = today_local().isoformat()
        conn = get_conn()
        try:
            return _form_page(request, conn, _blank_form(conn, request.state.user, day))
        finally:
            conn.close()

    @router.post("/calendar/new")
    async def calendar_create(request: Request):
        f = await _posted_form(request)
        for k, v in _blank_form_defaults().items():
            f.setdefault(k, v)
        conn = get_conn()
        try:
            fields, people, tags, error = _parse(
                f, allowed_people={p["user_id"] for p in oc.people_choices(conn)})
            if not error:
                try:
                    eid = st.cal_create(conn, fields.pop("title"), fields.pop("start_date"),
                                        people=people, tags=tags,
                                        by=request.state.user["username"], **fields)
                except ValueError as e:
                    error = str(e)
            if error:
                return _form_page(request, conn, f, error=error, status_code=400)
        finally:
            conn.close()
        return RedirectResponse(f"/calendar/entries/{eid}?ok={quote('Added to the calendar.')}",
                                status_code=303)

    @router.get("/calendar/entries/{entry_id}", response_class=HTMLResponse)
    def calendar_entry(request: Request, entry_id: int, ok: str = "", err: str = ""):
        user = request.state.user
        conn = get_conn()
        try:
            e = oc.viewable_entry(conn, user, entry_id)
            if e is None:
                return _not_found(request)
            cards = oc._people_cards(conn, [p["user_id"] for p in e["people"]])
            unit = oc._units(conn, [e["owner_org_id"]]).get(e["owner_org_id"])
            revs = st.cal_revisions(conn, entry_id)
            names = oc.display_names(conn, [e["created_by"], e["updated_by"]]
                                     + [r["changed_by"] for r in revs])
        finally:
            conn.close()
        who = lambda u: names.get(u, u or "someone")           # noqa: E731
        return templates.TemplateResponse(request, "calendar_entry.html", {
            "nav_active": "calendar", "e": e, "ok": ok, "err": err,
            "owner": unit["label"] if unit else None,
            "attendees": [{**cards.get(p["user_id"], {"name": "?", "initials": "?"}),
                           "role": p["role"]} for p in e["people"]],
            "kind_label": KIND_LABELS.get(e["kind"], e["kind"]),
            "status_label": STATUS_LABELS.get(e["status"], e["status"]),
            "audience_label": AUDIENCE_LABELS.get(e["audience"], e["audience"]),
            "created_by": who(e["created_by"]), "updated_by": who(e["updated_by"]),
            "history": [{"who": who(r["changed_by"]), "at": r["changed_at"],
                         "what": "created" if r["action"] == "create" else
                                 {"cancel": "cancelled it", "restore": "restored it"}.get(
                                     r["action"], oc.describe_change(r["diff"]))}
                        for r in revs],
        })

    @router.get("/calendar/entries/{entry_id}/edit", response_class=HTMLResponse)
    def calendar_edit_form(request: Request, entry_id: int):
        conn = get_conn()
        try:
            e = oc.viewable_entry(conn, request.state.user, entry_id)
            if e is None:
                return _not_found(request)
            if e["status"] == "cancelled":
                return RedirectResponse(
                    f"/calendar/entries/{entry_id}?err={quote('Restore it before editing.')}",
                    status_code=303)
            return _form_page(request, conn, _entry_form(e), entry=e)
        finally:
            conn.close()

    @router.post("/calendar/entries/{entry_id}/edit")
    async def calendar_edit(request: Request, entry_id: int):
        f = await _posted_form(request)
        for k, v in _blank_form_defaults().items():
            f.setdefault(k, v)
        user = request.state.user
        conn = get_conn()
        try:
            e = oc.viewable_entry(conn, user, entry_id)
            if e is None:
                return _not_found(request)
            if e["status"] == "cancelled":
                return RedirectResponse(
                    f"/calendar/entries/{entry_id}?err={quote('Restore it before editing.')}",
                    status_code=303)
            fields, people, tags, error = _parse(
                f, e, {p["user_id"] for p in oc.people_choices(conn)})
            if error:
                return _form_page(request, conn, f, entry=e, error=error, status_code=400)
            try:
                st.cal_update(conn, entry_id, by=user["username"], people=people, tags=tags,
                              expected_updated_at=f["updated_at"] or None, **fields)
            except st.CalendarConflict as c:
                last = (st.cal_revisions(conn, entry_id) or [{}])[0]
                names = oc.display_names(conn, [last.get("changed_by")])
                f["updated_at"] = c.entry["updated_at"] or ""      # saving again now overwrites
                conflict = {"who": names.get(last.get("changed_by"), last.get("changed_by")
                                             or "Someone"),
                            "at": last.get("changed_at"),
                            "what": oc.describe_change(last.get("diff") or {})}
                return _form_page(request, conn, f, entry=c.entry, conflict=conflict,
                                  status_code=409)
            except ValueError as ex:
                return _form_page(request, conn, f, entry=e, error=str(ex), status_code=400)
        finally:
            conn.close()
        return RedirectResponse(f"/calendar/entries/{entry_id}?ok={quote('Saved.')}",
                                status_code=303)

    @router.post("/calendar/entries/{entry_id}/cancel")
    def calendar_cancel(request: Request, entry_id: int):
        user = request.state.user
        conn = get_conn()
        try:
            if oc.viewable_entry(conn, user, entry_id) is None:
                return _not_found(request)
            st.cal_cancel(conn, entry_id, by=user["username"])
        finally:
            conn.close()
        return RedirectResponse(
            f"/calendar/entries/{entry_id}?ok={quote('Cancelled. You can restore it for 30 days.')}",
            status_code=303)

    @router.post("/calendar/entries/{entry_id}/restore")
    def calendar_restore(request: Request, entry_id: int):
        user = request.state.user
        conn = get_conn()
        try:
            if oc.viewable_entry(conn, user, entry_id) is None:
                return _not_found(request)
            try:
                st.cal_restore(conn, entry_id, by=user["username"])
                note = f"ok={quote('Restored.')}"
            except ValueError as ex:
                note = f"err={quote(str(ex).capitalize() + '.')}"
        finally:
            conn.close()
        return RedirectResponse(f"/calendar/entries/{entry_id}?{note}", status_code=303)

    # ── Word import (admin only) ────────────────────────────────────────────

    def _admin_only(request):
        if not auth.can(request.state.user["role"], "manage_users"):
            return templates.TemplateResponse(
                request, "forbidden.html",
                {"capability": "importing the calendar", "show_scope": False}, status_code=403)
        return None

    def _upload_page(request, conn, error="", status_code=200):
        return templates.TemplateResponse(request, "calendar_import.html", {
            "nav_active": "calendar", "error": error, "batches": st.cal_import_list(conn),
        }, status_code=status_code)

    @router.get("/calendar/import", response_class=HTMLResponse)
    def calendar_import_form(request: Request):
        denied = _admin_only(request)
        if denied:
            return denied
        conn = get_conn()
        try:
            return _upload_page(request, conn)
        finally:
            conn.close()

    @router.post("/calendar/import")
    async def calendar_import_upload(request: Request):
        denied = _admin_only(request)
        if denied:
            return denied
        form = await request.form()
        up = form.get("file")
        conn = get_conn()
        try:
            data = await up.read() if hasattr(up, "read") else b""
            if not data or not (up.filename or "").lower().endswith(".docx"):
                return _upload_page(request, conn, "Choose the calendar as a Word (.docx) file.", 400)
            if len(data) > MAX_UPLOAD:
                return _upload_page(request, conn, "That file is too large to be the calendar.", 400)
            try:
                with zipfile.ZipFile(io.BytesIO(data)) as z:
                    if sum(i.file_size for i in z.infolist()) > MAX_UNZIPPED:
                        raise ValueError("too large when unpacked")
                res = await run_in_threadpool(ci.parse, io.BytesIO(data))
            except Exception:                    # noqa: BLE001 — any unreadable file gets one friendly message
                return _upload_page(request, conn,
                                    "That doesn't look like the calendar Word file, so nothing was read.", 400)
            if not res.drafts:
                return _upload_page(request, conn,
                                    "No activities were found in that file. Is it the monthly calendar?", 400)
            batch_id = st.cal_import_create(conn, up.filename, request.state.user["username"], {
                "drafts": [d.to_dict() for d in res.drafts], "holidays": res.holidays,
                "warnings": res.warnings, "stats": res.stats, "unmapped_colors": res.unmapped_colors})
        finally:
            conn.close()
        return RedirectResponse(f"/calendar/import/{batch_id}", status_code=303)

    def _review_page(request, conn, batch, posted=None, errors=(), status_code=200):
        drafts = batch["payload"]["drafts"]
        existing = st.cal_existing_import_keys(conn, [d["import_key"] for d in drafts])
        years = {h["date"][:4] for h in batch["payload"]["holidays"]}
        have_hol = {row["day"] for y in years for row in st.list_holidays(conn, int(y))}
        mapping = ({k[4:]: int(v) for k, v in posted.items() if k.startswith("map_") and v.isdigit()}
                   if posted is not None else cia.guess_mapping(conn))
        return templates.TemplateResponse(request, "calendar_import_review.html", {
            "nav_active": "calendar", "batch": batch, "errors": list(errors),
            "rows": cia.review_rows(drafts, existing, posted),
            "stats": batch["payload"]["stats"], "file_warnings": batch["payload"]["warnings"],
            "holidays": [{**h, "known": h["date"] in have_hol} for h in batch["payload"]["holidays"]],
            "owners": [(k, ci.OWNER_LABELS[k], cia.OWNER_TONES[k]) for k in ci.OWNERS],
            "mapping": mapping, "units": oc.unit_choices(conn),
            "audience": (posted or {}).get("audience", "bureau"),
            "kinds": {k: v for k, v in KIND_LABELS.items()},
            "statuses": {k: v for k, v in STATUS_LABELS.items() if k != "cancelled"},
            "n_existing": sum(1 for r in drafts if r["import_key"] in existing),
        }, status_code=status_code)

    @router.get("/calendar/import/{batch_id}", response_class=HTMLResponse)
    def calendar_import_review(request: Request, batch_id: int):
        denied = _admin_only(request)
        if denied:
            return denied
        conn = get_conn()
        try:
            batch = st.cal_import_get(conn, batch_id)
            if batch is None:
                return RedirectResponse("/calendar/import", status_code=303)
            return _review_page(request, conn, batch)
        finally:
            conn.close()

    @router.post("/calendar/import/{batch_id}")
    async def calendar_import_apply(request: Request, batch_id: int):
        denied = _admin_only(request)
        if denied:
            return denied
        raw = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
        posted = {k: (v[0] if v else "").strip() for k, v in raw.items()}
        conn = get_conn()
        try:
            batch = st.cal_import_get(conn, batch_id)
            if batch is None or batch["imported_at"]:
                return RedirectResponse(f"/calendar/import/{batch_id}" if batch else "/calendar/import",
                                        status_code=303)
            result, errors = cia.apply(conn, batch, posted, request.state.user["username"])
            if errors:
                return _review_page(request, conn, batch, posted, errors, status_code=400)
        finally:
            conn.close()
        return RedirectResponse(f"/calendar/import/{batch_id}", status_code=303)

    @router.post("/calendar/import/{batch_id}/discard")
    def calendar_import_discard(request: Request, batch_id: int):
        denied = _admin_only(request)
        if denied:
            return denied
        conn = get_conn()
        try:
            st.cal_import_discard(conn, batch_id)
        finally:
            conn.close()
        return RedirectResponse("/calendar/import", status_code=303)

    return router
