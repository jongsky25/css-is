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
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.concurrency import run_in_threadpool

import auth
import mailer
import calendar_import as ci
import calendar_import_apply as cia
import calendar_people as cp
import office_calendar as oc
import storage as st

MAX_UPLOAD = 8 * 1024 * 1024            # a calendar .docx is well under 1 MB
MAX_UNZIPPED = 80 * 1024 * 1024         # refuse a zip bomb before python-docx inflates it

AGENDA_DAYS = 14        # the agenda shows two weeks from the chosen day

# What a person can choose when adding or editing an item. "activity" is not here: a CSS
# activity is made through Create and shows on the calendar by itself.
FORM_KIND_LABELS = {"meeting": "Meeting", "training": "Training / workshop",
                    "travel": "Trip / field work", "deadline": "Deadline",
                    "audit_mr": "Audit / management review", "banner": "Bureau-wide notice"}
# What the filter menu and the cards can name: the above plus the CSS activities.
KIND_LABELS = {**FORM_KIND_LABELS, "activity": "CSS activity", "leave": "On leave", "birthday": "Birthday"}
STATUS_LABELS = {"confirmed": "Confirmed", "tentative": "Tentative",
                 "postponed": "Postponed", "cancelled": "Cancelled"}
MODALITY_LABELS = {"": "Not set", "f2f": "Face to face", "online": "Online", "hybrid": "Hybrid"}
AUDIENCE_LABELS = {"unit": "Everyone in the owning unit",
                   "bureau": "Everyone in the bureau",
                   "people": "Only the people I add"}


def _filters(kind, status, tag, unit):
    """Validated filter choices -> (filters dict for office_calendar, clean values)."""
    clean = {"kind": kind if kind in KIND_LABELS else "",
             "status": status if status in STATUS_LABELS and status != "cancelled" else "",
             "tag": (tag or "").strip()[:50], "unit": unit if (unit or "").isdigit() else ""}
    return ({"kinds": {clean["kind"]} if clean["kind"] else None,
             "statuses": {clean["status"]} if clean["status"] else None,
             "tags": {clean["tag"]} if clean["tag"] else None,
             "owner_org_ids": {int(clean["unit"])} if clean["unit"] else None}, clean)


def build_calendar_page(conn, user, today, q, *, base="/calendar", layout_key="view", fixed=None):
    """Everything the calendar body (agenda / month, filters, scope pills) needs, as a dict
    for templates/_calendar_body.html — or None when `q` holds a date that isn't one.

    Two places render that body: the /calendar page (base "/calendar", layout in `view=`)
    and the home page's Calendar tab (base "/", layout in `layout=`, plus the fixed
    `view=calendar` that selects the tab). `q` is the raw query (a dict of strings); every
    link the body builds goes back to `base` carrying `fixed`, so a tab never turns into
    the other page. Visibility is office_calendar's job; nothing here widens it."""
    fixed = dict(fixed or {})
    layout = q.get(layout_key) if q.get(layout_key) in ("month", "week") else "agenda"
    try:
        if layout == "month":
            m = date.fromisoformat((q.get("month") or today.strftime("%Y-%m")) + "-01")
            start, end = oc.month_span(m.year, m.month)
        elif layout == "week":
            start = oc.monday_of(date.fromisoformat(q["day"]) if q.get("day") else today)
            end = start + timedelta(days=4)                # Monday-Friday: the working week
        else:
            start = date.fromisoformat(q["day"]) if q.get("day") else today
            end = start + timedelta(days=AGENDA_DAYS - 1)
    except ValueError:
        return None                             # a hand-typed or stale date: caller falls back to today
    filters, clean = _filters(q.get("kind", ""), q.get("status", ""), q.get("tag", ""), q.get("unit", ""))
    ctx = oc.viewer_context(conn, user)
    choices = oc.scope_choices(ctx)
    scope = q.get("scope") or oc.DEFAULT_SCOPE
    if scope not in {c["key"] for c in choices}:
        scope = oc.DEFAULT_SCOPE                 # also catches a pill this viewer isn't offered
    # The Week layout is "who is where" for the viewer's whole team: its rows come from the
    # directory, so the items must not be narrowed to "mine" or the others' trips would vanish.
    # Visibility is unchanged — items_between still only returns what this viewer may see.
    # (The Week layout draws leave itself, from the same whereabouts, so it skips that layer.)
    everything = oc.items_between(conn, user, start, end, scope="bureau" if layout == "week" else scope,
                                  layers=[n for n in oc.LAYERS if not (layout == "week" and n in ("leave", "birthdays"))])
    items = oc.apply_filters(everything, filters)
    entries = [i for i in everything if i["layer"] in ("entries", "activities")]
    # the filter menus list what is IN this window (before filtering), so choosing
    # one never makes the other options vanish
    units = {}
    for i in entries:
        if i["owner_org_id"]:
            units[i["owner_org_id"]] = {"id": i["owner_org_id"], "label": i["owner_label"],
                                        "tone": i["tone"]}
    month_param = m.strftime("%Y-%m") if layout == "month" and q.get("month") else ""
    params = {**fixed, "scope": scope, layout_key: layout if layout != "agenda" else "",
              "month": month_param, **clean}

    def qs(**over):
        """A link to this body with the current choices and `over` applied; `layout=` names
        the layout whatever key this page really uses, and empty values are dropped."""
        merged = {**params, **{(layout_key if k == "layout" else k): v for k, v in over.items()}}
        return base + "?" + urlencode([(k, v) for k, v in merged.items() if v not in ("", None)])

    n = sum(1 for i in items if i["layer"] != "holidays")
    page = {
        "layout": layout, "can_import": auth.can(user["role"], "manage_users"),
        "scope": scope, "scopes": choices, "today": today, "start": start, "end": end,
        "n_items": n, "f": clean, "filtered": any(clean.values()),
        "kinds": KIND_LABELS,
        "statuses": {k: v for k, v in STATUS_LABELS.items() if k != "cancelled"},
        "tags": sorted({t for i in entries for t in i["tags"]}, key=str.lower),
        "units": sorted(units.values(), key=lambda u: u["label"].lower()),
        "qs": qs, "form_action": base,
        "clear_filters": qs(kind="", status="", tag="", unit=""),
    }
    hidden = [(k, v) for k, v in fixed.items()] + [("scope", scope)]
    noun = "item" if n == 1 else "items"
    if layout == "week":
        pw = oc.people_week(conn, user, start, items)
        hidden += [(layout_key, "week"), ("day", start.isoformat())]
        page.update(week=pw, is_today_window=start == oc.monday_of(today), add_day=max(start, today).isoformat()
                    if start <= today <= end else start.isoformat(),
                    range_label=f"{pw['label']} · {n} {noun}")
    elif layout == "month":
        grid = oc.month_grid(items, m.year, m.month, today)
        hidden += [(layout_key, "month"), ("month", m.strftime("%Y-%m"))]
        page.update(grid=grid, weekdays=oc.WEEKDAY_NAMES,
                    is_today_window=(m.year, m.month) == (today.year, today.month),
                    range_label=f"{grid['title']} · {n} {noun}",
                    add_day=(today if (m.year, m.month) == (today.year, today.month) else m).isoformat())
    else:
        page.update(days=oc.agenda_days(items, start, end, today),
                    prev_day=(start - timedelta(days=AGENDA_DAYS)).isoformat(),
                    next_day=(start + timedelta(days=AGENDA_DAYS)).isoformat(),
                    is_today_window=start == today, add_day=start.isoformat(),
                    range_label=f"{start.strftime('%b')} {start.day} – "
                                f"{end.strftime('%b')} {end.day}, {end.year} · {n} {noun}")
    page["hidden"] = hidden
    return page


def prefill_from_entry(conn, user, entry_id):
    """The /create form's starting values for "Collect feedback (CSS)" on a calendar item, or
    None when the id is not one this person may turn into an activity (can't see it, already
    linked, cancelled, or a kind that takes no CSS form). Speakers are the item's LEADS who have
    a directory record, each with the item's title as their topic (every speaker needs one);
    attendees are not speakers, so they are left off."""
    if not str(entry_id or "").isdigit():
        return None
    e = oc.viewable_entry(conn, user, int(entry_id))
    if e is None or not oc.entry_can_collect_feedback(e):
        return None
    sections = {s["id"] for s in st.list_org_units(conn, level="section")}
    speakers = []
    for p in e["people"]:
        if p["role"] != "lead":
            continue
        row = conn.execute("SELECT rp_id FROM admin_user WHERE id=?", (p["user_id"],)).fetchone()
        if row and row[0]:
            speakers.append((str(row[0]), e["title"]))
    return {"from_entry": str(e["id"]), "from_entry_title": e["title"], "event_type": "bureau",
            "activity_name": e["title"], "event_date": e["start_date"], "end_date": e["end_date"] or "",
            "venue": e["venue"] or e["meeting_url"] or "",
            "modality": e["modality"] if e["modality"] in ("f2f", "online", "hybrid") else "f2f",
            "section_id": str(e["owner_org_id"]) if e["owner_org_id"] in sections else "",
            "speakers": speakers}


def link_after_create(conn, user, entry_id, event_id):
    """Called by /create once the activity exists: make the calendar item it was started from
    the activity's overlay. Returns the item's title, or None — and never raises, because the
    activity is already created and a failed link must not undo or hide that."""
    if not str(entry_id or "").isdigit():
        return None
    try:
        e = oc.viewable_entry(conn, user, int(entry_id))
        if e is None or not oc.entry_can_collect_feedback(e):
            return None
        st.cal_link_event(conn, e["id"], event_id, by=user["username"])
        return e["title"]
    except ValueError:
        return None


LOCKED_WHEN_LINKED = ("title", "kind", "status", "start_time", "end_time", "time_note",
                      "venue", "modality", "meeting_url")


def make_router(templates, get_conn, today_local, *, can_manage_event=None, notify_email=None,
                base_url=None, on_event_changed=None, check_dates=None):
    """`can_manage_event(user, event, conn)`, `notify_email(conn, to, subject, body, html,
    feature)`, `base_url(request)`, `on_event_changed()` (drops the reporting cache) and
    `check_dates(start, end) -> (end_or_None, error_or_None)` are app.py's own rules, handed in
    because this module cannot import app. All optional: without them a linked item's dates
    simply stay locked."""
    router = APIRouter()


    @router.get("/calendar", response_class=HTMLResponse)
    def calendar_page(request: Request):
        q = dict(request.query_params)
        conn = get_conn()
        try:
            page = build_calendar_page(conn, request.state.user, today_local(), q)
        finally:
            conn.close()
        if page is None:
            return RedirectResponse("/calendar" + ("?view=month" if q.get("view") == "month" else ""),
                                    status_code=303)
        return templates.TemplateResponse(request, "calendar.html",
                                          {"nav_active": "calendar", "show_scope": False, **page})

    # ── add / view / edit / cancel / restore ────────────────────────────────
    # Everyone signed in may add and edit (owner decision). What a person may
    # SEE still rules: an entry they cannot see answers 404, same as a missing one.

    def _not_found(request):
        return templates.TemplateResponse(request, "calendar_entry.html",
                                          {"nav_active": "calendar", "missing": True},
                                          status_code=404)

    def _form_page(request, conn, f, *, entry=None, error="", conflict=None, status_code=200,
                   confirm=0):
        activity = st.get_event_by_id(conn, entry["event_id"]) if entry and entry["event_id"] else None
        can_dates = bool(activity and can_manage_event
                         and can_manage_event(request.state.user, activity, conn)
                         and check_dates)
        return templates.TemplateResponse(request, "calendar_entry_form.html", {
            "nav_active": "calendar", "f": f, "entry": entry, "error": error,
            "activity": activity, "can_dates": can_dates, "confirm": confirm,
            "conflict": conflict, "kinds": FORM_KIND_LABELS, "statuses": STATUS_LABELS,
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

    def _activity_of(conn, e):
        return st.get_event_by_id(conn, e["event_id"]) if e.get("event_id") else None

    def _entry_form(e, activity=None):
        if activity:                      # the activity owns the title, dates and venue
            e = {**e, "title": activity["title"], "venue": activity.get("venue"),
                 "start_date": (activity["event_date"] or e["start_date"])[:10],
                 "end_date": (activity.get("end_date") or "")[:10] or None}
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
        if f["kind"] not in FORM_KIND_LABELS:
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

    @router.get("/calendar/updates", response_class=HTMLResponse)
    def calendar_updates(request: Request):
        """What is new or changed for you, newest schedule first. Opening it is what clears the
        bell row, so the count in the bell and the list here can never disagree."""
        user = request.state.user
        conn = get_conn()
        try:
            unseen = st.cal_unseen_for_user(conn, user["id"], today_local())
            st.cal_mark_seen(conn, user["id"], [u["entry_id"] for u in unseen])
        finally:
            conn.close()
        for u in unseen:
            a = date.fromisoformat(u["start"])
            b = date.fromisoformat(u["end"])
            u["when"] = f"{a:%a, %b} {a.day}" + (f" – {b:%a, %b} {b.day}" if b != a else "")
        return templates.TemplateResponse(request, "calendar_updates.html", {
            "nav_active": "calendar", "show_scope": False, "items": unseen,
            "labels": {"new": "New", "changed": "Changed", "cancelled": "Cancelled"}})

    @router.get("/calendar/birthdays", response_class=HTMLResponse)
    def calendar_birthdays(request: Request, month: str = ""):
        """The month's celebrants, grouped by section and printable — for the welfare or
        celebrations committee. Lists only the birthdays this viewer may already see."""
        today = today_local()
        try:
            m = int(month) if month else today.month
            if not 1 <= m <= 12:
                raise ValueError
        except ValueError:
            return RedirectResponse("/calendar/birthdays", status_code=303)
        year = today.year
        first = date(year, m, 1)
        last = (date(year + (m == 12), m % 12 + 1, 1)) - timedelta(days=1)
        conn = get_conn()
        try:
            items = oc.items_between(conn, request.state.user, first, last, scope="bureau",
                                     layers=["birthdays"])
        finally:
            conn.close()
        groups = {}
        for i in items:
            d = date.fromisoformat(i["start"])
            groups.setdefault(i["owner_label"] or "Other", []).append(
                {"name": i["title"].replace("🎂 ", ""), "day": d.day, "weekday": d.strftime("%a"),
                 "date": d, "today": d == today})
        for g in groups.values():
            g.sort(key=lambda r: (r["day"], r["name"].lower()))
        return templates.TemplateResponse(request, "calendar_birthdays.html", {
            "nav_active": "calendar", "show_scope": False, "month": m, "year": year,
            "month_name": first.strftime("%B"), "n": len(items),
            "groups": sorted(groups.items(), key=lambda kv: (kv[0] == "Other", kv[0].lower())),
            "prev": (m - 2) % 12 + 1, "next": m % 12 + 1,
        })

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
            st.cal_mark_seen(conn, user["id"], [entry_id])      # opening it IS seeing it
            heads_up = oc.entry_heads_up(conn, user, e)
            can_css = auth.can(user["role"], "create_activity")
            linked = st.get_event_by_id(conn, e["event_id"]) if e["event_id"] else None
            eligible = can_css and oc.entry_can_collect_feedback(e)
            css = {"linked": linked, "eligible": eligible, "manage": auth.can(user["role"], "manage_event"),
                   "candidates": oc.activity_candidates_for_entry(conn, e) if eligible else []}
        finally:
            conn.close()
        who = lambda u: names.get(u, u or "someone")           # noqa: E731
        return templates.TemplateResponse(request, "calendar_entry.html", {
            "nav_active": "calendar", "e": e, "ok": ok, "err": err, "css": css, "heads_up": heads_up,
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
            return _form_page(request, conn, _entry_form(e, _activity_of(conn, e)), entry=e)
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
            activity = _activity_of(conn, e)
            if activity:                  # locked to the activity: ignore whatever was posted
                shown = _entry_form(e, activity)
                for k in LOCKED_WHEN_LINKED:
                    f[k] = shown[k]
                f["title"] = activity["title"]
                f["venue"] = shown["venue"]
            fields, people, tags, error = _parse(
                f, e, {p["user_id"] for p in oc.people_choices(conn)})
            if error:
                return _form_page(request, conn, f, entry=e, error=error, status_code=400)
            redate = None
            if activity:
                shown = _entry_form(e, activity)
                new_start, new_end = f["start_date"], f.get("end_date", "")
                if (new_start, new_end) != (shown["start_date"], shown["end_date"]):
                    if not (can_manage_event and check_dates
                            and can_manage_event(user, activity, conn)):
                        f["start_date"], f["end_date"] = shown["start_date"], shown["end_date"]
                        return _form_page(request, conn, f, entry=e, status_code=403, error=(
                            "Only the people who manage this activity can change its dates."))
                    end_ok, bad = check_dates(new_start, new_end)
                    if bad:
                        return _form_page(request, conn, f, entry=e, error=bad, status_code=400)
                    redate = (new_start, end_ok)
                    fields["end_date"] = end_ok
                    if "start_date" in fields:
                        fields["start_date"] = new_start
                    notify = f.get("notify", "")
                    reachable = [a for a in st.event_attendees_status(conn, activity["id"])
                                 if a.get("email")]
                    if reachable and notify not in ("yes", "no"):
                        return _form_page(request, conn, f, entry=e, confirm=len(reachable))
                else:
                    fields["start_date"], fields["end_date"] = e["start_date"], e["end_date"]
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
            if redate:
                _redate_activity(request, conn, activity, redate, notify == "yes", user)
        finally:
            conn.close()
        return RedirectResponse(f"/calendar/entries/{entry_id}?ok={quote('Saved.')}",
                                status_code=303)

    def _redate_activity(request, conn, activity, redate, notify, user):
        """Write the new dates through the same path as the activity's own Dates card: the
        event and every form of it, the reporting cache, an audit row, and (if chosen) one
        email per registrant with an address."""
        start, end = redate
        old = _when(activity["event_date"][:10], (activity.get("end_date") or "")[:10])
        n = st.set_event_dates(conn, activity["id"], start, end)
        new = _when(start, end)
        st.audit(conn, user["username"], "event_dates_set", target_type="event",
                 target_id=activity["id"],
                 summary=f"Set activity dates to {new} on {n} form(s) (from the calendar).")
        if on_event_changed:
            on_event_changed()
        if not (notify and notify_email and base_url):
            return
        base = base_url(request)
        for a in st.event_attendees_status(conn, activity["id"]):
            if not a.get("email"):
                continue
            link = (f"{base}/e/{activity['event_token']}/resume?rt="
                    f"{quote(auth.make_recovery_token(a['id']))}")
            subj, body, html = mailer.event_dates_changed_message(
                a.get("name"), activity["title"], old, new, activity.get("venue"), link)
            notify_email(conn, a["email"], subj, body, html, "event_dates_changed")

    def _when(start, end):
        a = date.fromisoformat(start)
        if not end or end == start:
            return f"{a:%B} {a.day}, {a.year}"
        b = date.fromisoformat(end)
        return f"{a:%B} {a.day} – {b:%B} {b.day}, {b.year}"

    @router.post("/calendar/entries/{entry_id}/link-activity")
    async def calendar_link_activity(request: Request, entry_id: int):
        user = request.state.user
        if not auth.can(user["role"], "create_activity"):
            return templates.TemplateResponse(request, "forbidden.html",
                                              {"capability": "linking a calendar item to an activity",
                                               "show_scope": False}, status_code=403)
        raw = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
        ev = (raw.get("event_id") or [""])[0].strip()
        conn = get_conn()
        try:
            e = oc.viewable_entry(conn, user, entry_id)
            if e is None:
                return _not_found(request)
            try:
                if not ev.isdigit():
                    raise ValueError("Choose the activity to link.")
                st.cal_link_event(conn, entry_id, int(ev), by=user["username"])
                note = f"ok={quote('Linked. The activity now owns the title, dates and venue.')}"
            except ValueError as ex:
                note = f"err={quote(str(ex))}"
        finally:
            conn.close()
        return RedirectResponse(f"/calendar/entries/{entry_id}?{note}", status_code=303)

    @router.get("/create/check-calendar")
    def create_check_calendar(request: Request, activity_name: str = "", event_date: str = "",
                              end_date: str = ""):
        """Behind the /create screen's second heads-up: calendar items this person may see that
        look like the activity being typed (same dates, similar title, not linked yet). Purely
        a suggestion — the screen offers a button; nothing is linked until Create is pressed."""
        try:
            start = date.fromisoformat(event_date).isoformat()
            end = date.fromisoformat(end_date).isoformat() if end_date else start
        except ValueError:
            return JSONResponse({"entries": []})
        conn = get_conn()
        try:
            found = oc.entry_candidates_for_activity(conn, request.state.user, activity_name, start, end)
        finally:
            conn.close()
        return JSONResponse({"entries": found[:5]})

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
        n_names = (sum(1 for r in cia.people_state(conn, batch)[0] if r["decision"] is None and not r["ignored"])
                   if batch["imported_at"] else 0)
        return templates.TemplateResponse(request, "calendar_import_review.html", {
            "n_names": n_names,
            "nav_active": "calendar", "batch": batch, "errors": list(errors),
            "rows": cia.review_rows(drafts, existing, posted),
            "stats": batch["payload"]["stats"], "file_warnings": batch["payload"]["warnings"],
            "holidays": [{**h, "known": h["date"] in have_hol} for h in batch["payload"]["holidays"]],
            "owners": [(k, ci.OWNER_LABELS[k], cia.OWNER_TONES[k]) for k in ci.OWNERS],
            "mapping": mapping, "units": oc.unit_choices(conn),
            "audience": (posted or {}).get("audience", "bureau"),
            "kinds": dict(FORM_KIND_LABELS),
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

    @router.get("/calendar/import/{batch_id}/people", response_class=HTMLResponse)
    def calendar_import_people(request: Request, batch_id: int, ok: str = ""):
        denied = _admin_only(request)
        if denied:
            return denied
        conn = get_conn()
        try:
            batch = st.cal_import_get(conn, batch_id)
            if batch is None or not batch["imported_at"]:
                return RedirectResponse(f"/calendar/import/{batch_id}" if batch else "/calendar/import",
                                        status_code=303)
            rows, directory = cia.people_state(conn, batch)
            by_id = {p["user_id"]: p for p in directory}
            for r in rows:
                r["cands"] = [by_id[u] for u in r["match"]["candidates"] if u in by_id]
                st_ = r["match"]["status"]
                r["picked"] = (r["decision"] if isinstance(r["decision"], int) else
                               r["match"]["candidates"][0] if st_ in ("alias", "guided", "suggested") else
                               "ignore" if st_ in ("not_person", "no_account") else None)
            return templates.TemplateResponse(request, "calendar_import_people.html", {
                "nav_active": "calendar", "batch": batch, "ok": ok,
                "pending": [r for r in rows if r["decision"] is None and not r["ignored"]],
                "done": [r for r in rows if r["decision"] is not None or r["ignored"]],
                "everyone": sorted((p for p in directory if not p["inactive"]),
                                   key=lambda p: p["name"].lower()),
                "levels": cp.LEVEL_LABELS, "all_people": directory,
            })
        finally:
            conn.close()

    @router.post("/calendar/import/{batch_id}/people")
    async def calendar_import_people_apply(request: Request, batch_id: int):
        denied = _admin_only(request)
        if denied:
            return denied
        raw = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
        posted = {k: (v[0] if v else "").strip() for k, v in raw.items()}
        conn = get_conn()
        try:
            batch = st.cal_import_get(conn, batch_id)
            if batch is None or not batch["imported_at"]:
                return RedirectResponse("/calendar/import", status_code=303)
            r = cia.apply_people(conn, batch, posted, request.state.user["username"])
        finally:
            conn.close()
        msg = (f"Added {r['added']} {'person' if r['added'] == 1 else 'people'} to {r['items']} "
               f"{'item' if r['items'] == 1 else 'items'}; marked {r['ignored']} as not a person.")
        return RedirectResponse(f"/calendar/import/{batch_id}/people?ok={quote(msg)}", status_code=303)

    @router.get("/calendar/nicknames", response_class=HTMLResponse)
    def calendar_nicknames(request: Request, ok: str = ""):
        denied = _admin_only(request)
        if denied:
            return denied
        conn = get_conn()
        try:
            rows = cp.nickname_proposals(cp.load_directory(conn))
        finally:
            conn.close()
        return templates.TemplateResponse(request, "calendar_nicknames.html", {
            "nav_active": "calendar", "rows": rows, "ok": ok})

    @router.post("/calendar/nicknames")
    async def calendar_nicknames_apply(request: Request):
        denied = _admin_only(request)
        if denied:
            return denied
        raw = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
        ticked = {x for x in raw.get("apply", []) if x.isdigit()}
        by = request.state.user["username"]
        conn = get_conn()
        try:
            n, names = 0, []
            for r in cp.nickname_proposals(cp.load_directory(conn)):
                p = r["person"]
                # the nickname comes from the server's own list, never from the form
                if p and str(p["user_id"]) in ticked and r["status"] in ("ready", "has_nickname"):
                    st.set_user_nickname(conn, p["user_id"], r["proposed"])
                    n += 1
                    names.append(f"{p['name']} → {r['proposed']}")
            if n:
                st.audit(conn, by, "calendar_nicknames", target_type="admin_user",
                         summary=f"Set {n} nicknames: " + "; ".join(names))
        finally:
            conn.close()
        return RedirectResponse(f"/calendar/nicknames?ok={quote(f'Set {n} nicknames.')}", status_code=303)

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
