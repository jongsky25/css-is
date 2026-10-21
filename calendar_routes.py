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
import re
import zipfile

from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse, Response
from starlette.concurrency import run_in_threadpool

import activity_docs
import auth
import calendar_ics as cics
import gdocs_relay
import ratelimit
import mailer
import meet_relay
import calendar_import as ci
import calendar_import_apply as cia
import calendar_import_suggest as cis
import calendar_people as cp
import office_calendar as oc
import recurrence
import rooms
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
KIND_LABELS = {**FORM_KIND_LABELS, "activity": "CSS activity", "leave": "On leave", "birthday": "Birthday",
               "room": "Conference room"}
STATUS_LABELS = {"confirmed": "Confirmed", "tentative": "Tentative",
                 "postponed": "Postponed", "cancelled": "Cancelled"}
MODALITY_LABELS = {"": "Not set", "f2f": "Face to face", "online": "Online", "hybrid": "Hybrid"}
AUDIENCE_LABELS = {"unit": "Everyone in the owning unit",
                   "bureau": "Everyone in the bureau",
                   "people": "Only the people I add"}


SEARCH_MAX = 80


def _filters(kind, status, tag, unit, text=""):
    """Validated filter choices -> (filters dict for office_calendar, clean values)."""
    clean = {"kind": kind if kind in KIND_LABELS else "",
             "status": status if status in STATUS_LABELS and status != "cancelled" else "",
             "tag": (tag or "").strip()[:50], "unit": unit if (unit or "").isdigit() else "",
             "q": re.sub(r"\s+", " ", text or "").strip()[:SEARCH_MAX]}
    return ({"kinds": {clean["kind"]} if clean["kind"] else None,
             "statuses": {clean["status"]} if clean["status"] else None,
             "tags": {clean["tag"]} if clean["tag"] else None,
             "owner_org_ids": {int(clean["unit"])} if clean["unit"] else None,
             "text": clean["q"] or None}, clean)


# ── preferred layout and whose calendar ──────────────────────────────────────
# A cookie, read on the server, so a bare visit opens the saved view immediately.
# Explicit links still mean exactly what they say, and browsing does not replace the preference.
PREF_COOKIE = "cal_pref"
_PREF_PARAMS = ("scope", "day", "month", "kind", "status", "tag", "unit", "q")
PREF_LAYOUTS = ("agenda", "week", "timeline", "month")
DEFAULT_PAGE_SCOPE = "bureau"            # Everything I can see, subject to each item's visibility rules


def read_pref(request):
    """(layout, scope) from the cookie, or ("", "") when absent or not something we wrote."""
    m = re.fullmatch(r"(agenda|week|timeline|month):([a-z_]{1,20})", request.cookies.get(PREF_COOKIE, ""))
    return (m.group(1), m.group(2)) if m else ("", "")


def is_bare(q, layout_key):
    return not any(q.get(k) for k in (layout_key, *_PREF_PARAMS))


def with_pref(q, request, layout_key):
    """`q`, with the remembered layout and scope filled in when this is a bare visit."""
    if not is_bare(q, layout_key):
        return q
    layout, scope = read_pref(request)
    out = dict(q)
    if layout and layout != "agenda":
        out[layout_key] = layout
    if scope:
        out["scope"] = scope
    return out


def preferred_matches(request, page):
    return read_pref(request) == (page["layout"], page["scope"])


def entry_calendar_back(request, start_date):
    """Return to the item's date without dropping a saved layout or scope."""
    layout, scope = read_pref(request)
    params = {"scope": scope} if scope else {}
    if layout == "month":
        params.update(view="month", month=start_date[:7])
    else:
        if layout in ("week", "timeline"):
            params["view"] = layout
        params["day"] = start_date
    return "/calendar?" + urlencode(params)


def build_calendar_page(conn, user, today, q, *, base="/calendar", layout_key="view", fixed=None):
    """Everything the calendar body (agenda / month, filters, scope pills) needs, as a dict
    for templates/_calendar_body.html — or None when `q` holds a date that isn't one.

    Two places render that body: the /calendar page (base "/calendar", layout in `view=`)
    and the home page's Calendar tab (base "/", layout in `layout=`, plus the fixed
    `view=calendar` that selects the tab). `q` is the raw query (a dict of strings); every
    link the body builds goes back to `base` carrying `fixed`, so a tab never turns into
    the other page. Visibility is office_calendar's job; nothing here widens it."""
    fixed = dict(fixed or {})
    layout = q.get(layout_key) if q.get(layout_key) in ("month", "week", "timeline") else "agenda"
    try:
        if layout == "month":
            m = date.fromisoformat((q.get("month") or today.strftime("%Y-%m")) + "-01")
            start, end = oc.month_span(m.year, m.month)
        elif layout == "week":
            start = oc.monday_of(date.fromisoformat(q["day"]) if q.get("day") else today)
            end = start + timedelta(days=4)                # Monday-Friday: the working week
        elif layout == "timeline":
            start = oc.monday_of(date.fromisoformat(q["day"]) if q.get("day") else today)
            end = start + timedelta(days=7 * oc.TIMELINE_WEEKS - 1)
        else:
            start = date.fromisoformat(q["day"]) if q.get("day") else today
            end = start + timedelta(days=AGENDA_DAYS - 1)
    except ValueError:
        return None                             # a hand-typed or stale date: caller falls back to today
    filters, clean = _filters(q.get("kind", ""), q.get("status", ""), q.get("tag", ""), q.get("unit", ""),
                              q.get("q", ""))
    searching = bool(clean["q"]) and layout == "agenda"
    if searching:                              # a search in the agenda looks across the whole year
        start, end = date(start.year, 1, 1), date(start.year, 12, 31)
    ctx = oc.viewer_context(conn, user)
    choices = oc.scope_choices(ctx)
    scope = q.get("scope") or DEFAULT_PAGE_SCOPE
    if scope not in {c["key"] for c in choices}:
        scope = DEFAULT_PAGE_SCOPE               # also catches a pill this viewer isn't offered
    # The Week layout is "who is where" for the viewer's whole team: its rows come from the
    # directory, so the items must not be narrowed to "mine" or the others' trips would vanish.
    # Visibility is unchanged — items_between still only returns what this viewer may see.
    # (The Week layout draws leave itself, from the same whereabouts, so it skips that layer.)
    team_layout = layout in ("week", "timeline")                  # both are "everyone in my team"
    skip_layers = {"week": ("leave", "birthdays", "rooms"), "timeline": ("birthdays", "rooms")}.get(layout, ())
    everything = oc.items_between(conn, user, start, end, scope="bureau" if team_layout else scope,
                                  layers=[n for n in oc.LAYERS if n not in skip_layers])
    items = oc.apply_filters(everything, filters)
    entries = [i for i in everything if i["layer"] in ("entries", "activities")]
    # the filter menus list what is IN this window (before filtering), so choosing
    # one never makes the other options vanish
    units = {}
    for i in entries:
        for u in i.get("owner_units") or ([{"id": i["owner_org_id"], "label": i["owner_label"], "tone": i["tone"]}]
                                          if i["owner_org_id"] else []):
            units[u["id"]] = u
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
        "clear_filters": qs(kind="", status="", tag="", unit="", q=""),
        "searching": False, "year": None,
    }
    owner = ""
    if ctx["section_path"]:
        r = conn.execute("SELECT id FROM org_unit WHERE path=?", (ctx["section_path"],)).fetchone()
        owner = str(r[0]) if r else ""
    # The quick-add sheet posts to the ordinary add route (so every rule there applies) and comes back here.
    page["quick"] = {"owner": owner, "me": user["id"], "kinds": FORM_KIND_LABELS, "next": qs()}
    page["cal_flash"] = (q.get("ok") or "")[:120]      # not "flash": the home page imports a macro of that name
    hidden = [(k, v) for k, v in fixed.items()] + [("scope", scope)]
    noun = "item" if n == 1 else "items"
    if layout == "week":
        pw = oc.people_week(conn, user, start, items)
        hidden += [(layout_key, "week"), ("day", start.isoformat())]
        page.update(week=pw, is_today_window=start == oc.monday_of(today), add_day=max(start, today).isoformat()
                    if start <= today <= end else start.isoformat(),
                    range_label=f"{pw['label']} · {n} {noun}")
    elif layout == "timeline":
        tl = oc.timeline(conn, user, start, items, today)
        hidden += [(layout_key, "timeline"), ("day", start.isoformat())]
        page.update(tl=tl, is_today_window=start == oc.monday_of(today), add_day=max(start, today).isoformat()
                    if start <= today <= end else start.isoformat(),
                    range_label=f"{tl['label']} · {n} {noun}")
    elif layout == "month":
        grid = oc.month_grid(items, m.year, m.month, today)
        hidden += [(layout_key, "month"), ("month", m.strftime("%Y-%m"))]
        page.update(grid=grid, weekdays=oc.WEEKDAY_NAMES,
                    is_today_window=(m.year, m.month) == (today.year, today.month),
                    range_label=f"{grid['title']} · {n} {noun}",
                    add_day=(today if (m.year, m.month) == (today.year, today.month) else m).isoformat())
    elif searching:
        # A search reads like a list of matches through the year, not a two-week window: only days that
        # have a match, and "earlier / later" step a whole year.
        page.update(days=[d for d in oc.agenda_days(items, start, end, today) if d["rows"] or d["holidays"]],
                    searching=True, year=start.year,
                    prev_day=date(start.year - 1, 1, 1).isoformat(), next_day=date(start.year + 1, 1, 1).isoformat(),
                    is_today_window=start.year == today.year,
                    add_day=(today if start.year == today.year else start).isoformat(),
                    range_label=f"Search in {start.year} · {n} {'match' if n == 1 else 'matches'}")
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
    held = next((r for r in rooms.reservations_for_entry(conn, e["id"]) if r["status"] in ("requested", "approved")), None)
    room = {"from_room": str(held["id"]), "from_room_ref": held["ref_code"]} if held and not held["event_id"] else {}
    return {**room, "from_entry": str(e["id"]), "from_entry_title": e["title"], "event_type": "bureau",
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
        conn.execute("UPDATE room_reservation SET event_id=? WHERE calendar_entry_id=? AND event_id IS NULL "
                     "AND status IN ('requested','approved')", (event_id, e["id"]))   # its room now follows the activity
        conn.commit()
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
        shown = with_pref(q, request, "view")
        conn = get_conn()
        try:
            page = build_calendar_page(conn, request.state.user, today_local(), shown)
        finally:
            conn.close()
        if page is None:
            return RedirectResponse("/calendar" + ("?view=month" if q.get("view") == "month" else ""),
                                    status_code=303)
        resp = templates.TemplateResponse(request, "calendar.html",
                                          {"nav_active": "calendar", "show_scope": False,
                                           **page, "preferred": preferred_matches(request, page)})
        return resp

    @router.post("/calendar/preference")
    async def save_calendar_preference(request: Request):
        form = await request.form()
        layout = str(form.get("layout", ""))
        scope = str(form.get("scope", ""))
        conn = get_conn()
        try:
            choices = oc.scope_choices(oc.viewer_context(conn, request.state.user))
        finally:
            conn.close()
        if layout not in PREF_LAYOUTS or scope not in {c["key"] for c in choices}:
            return HTMLResponse("Invalid calendar preference.", status_code=400)
        next_url = str(form.get("next", ""))
        if not (next_url == "/calendar" or next_url.startswith("/calendar?")
                or next_url == "/?view=calendar" or next_url.startswith("/?view=calendar&")) \
                or "//" in next_url or any(c in next_url for c in "\r\n\\"):
            next_url = "/calendar"
        resp = RedirectResponse(next_url, status_code=303)
        resp.set_cookie(PREF_COOKIE, f"{layout}:{scope}", max_age=365 * 24 * 3600,
                        httponly=True, samesite="lax", path="/")
        return resp

    # ── add / view / edit / cancel / restore ────────────────────────────────
    # Everyone signed in may add and edit (owner decision). What a person may
    # SEE still rules: an entry they cannot see answers 404, same as a missing one.

    def _travel_block(conn, user, e, on=""):
        """The "Travel claim" block on an item's page: the viewer's filing, or a way to start one.
        Never raises: the page must open even if travel filing is off or broken."""
        try:
            import travel
            if not travel.enabled(conn):
                return None
            key = ("event", e["event_id"]) if e["event_id"] else ("entry", e["id"])
            chips = travel.filing_summaries(conn, user["id"], [] if e["event_id"] else [e["id"]],
                                            [e["event_id"]] if e["event_id"] else [])
            new_url = f"/travel/new?entry={e['id']}" + (f"&date={on}" if on and not e["event_id"] else "")
            return {"chip": chips.get(key), "new_url": new_url}
        except Exception:                                   # noqa: BLE001
            return None

    DOC_KINDS = ("meeting", "training", "travel", "audit_mr", "activity")      # items that can need a DPO or an invitation

    def _doc_owner_label(conn, e):
        units = oc._units(conn, [e["owner_org_id"]]) if e["owner_org_id"] else {}
        return (units.get(e["owner_org_id"]) or {}).get("label", "")

    def _documents_block(conn, e):
        """The "Documents for this activity" block, or None. Never raises: the page must open regardless."""
        try:
            if e["status"] == "cancelled" or e["kind"] not in DOC_KINDS:
                return None
            return {"items": activity_docs.state_for(conn, e, KIND_LABELS.get(e["kind"], "")),
                    "relay": gdocs_relay.configured()}
        except Exception:                                   # noqa: BLE001
            return None

    def _not_found(request):
        return templates.TemplateResponse(request, "calendar_entry.html",
                                          {"nav_active": "calendar", "missing": True},
                                          status_code=404)

    def _form_page(request, conn, f, *, entry=None, error="", conflict=None, status_code=200,
                   confirm=0, detach=None):
        activity = st.get_event_by_id(conn, entry["event_id"]) if entry and entry["event_id"] else None
        can_dates = bool(activity and can_manage_event
                         and can_manage_event(request.state.user, activity, conn)
                         and check_dates)
        return templates.TemplateResponse(request, "calendar_entry_form.html", {
            "nav_active": "calendar", "f": f, "entry": entry, "error": error,
            "activity": activity, "can_dates": can_dates, "confirm": confirm,
            "repeats": recurrence.REPEATS, "detach": detach,
            "conflict": conflict, "kinds": FORM_KIND_LABELS, "statuses": STATUS_LABELS,
            "modalities": MODALITY_LABELS, "audiences": AUDIENCE_LABELS,
            "units": oc.unit_choices(conn), "people": oc.people_choices(conn),
            "room_slots": rooms.list_slots(conn), "noun": "calendar item",
            "show_room_chip": not (entry and entry.get("event_id")) and not (
                entry and any(r["status"] in ("requested", "approved") for r in rooms.reservations_for_entry(conn, entry["id"]))),
            "room_link": _room_link(request, conn, entry) if entry else None,
            # A form sent back with an error / conflict / confirm step is the person's own answer coming
            # home: the room line must keep it, not auto-tick again (Spot Feedback #114).
            "room_decided": bool(error or conflict or confirm or status_code != 200),
            "chip_date": "start_date", "chip_venue": "venue", "chip_format": "modality",
            "chip_start": "start_time", "chip_end": "end_time",
        }, status_code=status_code)

    def _room_link(request, conn, e):
        """What a calendar item's page should say about its conference room, or None. A failure here must never stop the
        page loading. An item that is an overlay on a CSS activity shows the activity's room on the activity instead."""
        if e.get("event_id"):
            return None
        try:
            s = rooms.entry_room_status(conn, e, request.state.user, today_local())
            s["next"] = f"/calendar/entries/{e['id']}"
            s["edit_url"] = f"/calendar/entries/{e['id']}/edit"
            s["flash_ok"] = (request.query_params.get("roomok") or "")[:80]
            s["flash_err"] = (request.query_params.get("roomerr") or "")[:240]
            return s
        except Exception:                                    # noqa: BLE001
            return None

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
                "owner_org_id": owner, "extra_org_ids": [], "audience": "unit", "people": [], "tags": "",
                "updated_at": "", "repeat": "none", "until": ""}

    def _activity_of(conn, e):
        return st.get_event_by_id(conn, e["event_id"]) if e.get("event_id") else None

    def _repeat_of(e):
        if not e.get("rrule"):
            return "none", ""
        key, until = recurrence.kind_of(e["rrule"], date.fromisoformat(e["start_date"]))
        return key, until.isoformat() if until else ""

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
                "owner_org_id": str(e["owner_org_id"] or ""),
                "extra_org_ids": [str(i) for i in e["extra_org_ids"]], "audience": e["audience"],
                "people": [str(p["user_id"]) for p in e["people"]],
                "tags": ", ".join(e["tags"]), "updated_at": e["updated_at"] or "",
                **dict(zip(("repeat", "until"), _repeat_of(e)))}

    async def _posted_form(request):
        raw = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
        one = {k: (v[0] if v else "").strip() for k, v in raw.items()}
        one["people"] = [x for x in raw.get("people", []) if x.isdigit()]
        one["extra_org_ids"] = [x for x in raw.get("extra_org_ids", []) if x.isdigit()]
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
                      owner_org_id=int(f["owner_org_id"]) if f["owner_org_id"].isdigit() else None,
                      extra_org_ids=[int(x) for x in f.get("extra_org_ids", [])])
        repeat = f.get("repeat") or "none"
        if (existing or {}).get("event_id"):
            repeat = "none"                                      # an activity's item never repeats
        try:
            start = date.fromisoformat(f["start_date"])
            until = date.fromisoformat(f["until"]) if f.get("until") else None
            fields["rrule"] = recurrence.build(repeat, start, until)
        except ValueError as ex:
            return None, None, None, (str(ex) if repeat != "none" else "Pick a real start date.")
        if repeat != "none" and f["kind"] == "travel":
            return None, None, None, "A trip can't repeat. Add each trip on its own."
        had = {p["user_id"]: p["role"] for p in (existing or {}).get("people", [])}
        default = "travel" if f["kind"] == "travel" else "attending"
        people = [(int(u), "lead" if had.get(int(u)) == "lead" else default)
                  for u in f["people"]]
        tags = [t for t in f.get("tags", "").split(",")]
        return fields, people, tags, ""

    def _safe_back(raw):
        """Where the quick-add sheet may send you back to: a calendar page of this site, never
        anywhere else (no scheme, no host, no protocol-relative or backslash tricks)."""
        raw = (raw or "").strip()
        if (raw.startswith(("/calendar?", "/?view=calendar")) or raw == "/calendar") and "//" not in raw \
                and "\\" not in raw and "\n" not in raw and "\r" not in raw:
            return re.sub(r"[&?]ok=[^&]*", "", raw)
        return ""

    def _blank_form_defaults():
        return {"title": "", "kind": "meeting", "status": "confirmed", "start_date": "",
                "end_date": "", "start_time": "", "end_time": "", "time_note": "",
                "venue": "", "modality": "", "meeting_url": "", "note": "",
                "owner_org_id": "", "extra_org_ids": [], "audience": "unit", "tags": "", "updated_at": "",
                "repeat": "none", "until": "", "reserve_room": "", "room_from": "", "room_to": "",
                "room_meals": "", "room_standby": ""}

    # ── the conference room line on the form (rooms R8, for calendar items) ─────

    def _room_precheck(conn, f):
        """An error for a room choice that can't work, or "" — caught BEFORE the item is saved."""
        if not f.get("reserve_room") or not f.get("start_date"):
            return ""
        try:
            rooms.precheck(conn, date.fromisoformat(f["start_date"]), rooms.slot_range(conn, f["room_from"], f["room_to"]),
                           today_local(), standby=bool(f.get("room_standby")))
        except rooms.RoomError as e:
            return f"Conference room: {e} Untick the room line to save the item without it."
        except ValueError:
            return ""                                       # the date check reports a bad date
        return ""

    def _room_after_save(conn, user, entry_id, title, f):
        """File the ticked room request, tied to the item, and say what happened in one sentence. Never raises: the
        item is already saved and a room problem must not undo it."""
        if not f.get("reserve_room"):
            return ""
        try:
            r = rooms.request(conn, title=title, day=f["start_date"], slot_ids=rooms.slot_range(conn, f["room_from"], f["room_to"]),
                              requester_user_id=user["id"], purpose="Reserved with the calendar item.",
                              modality=f.get("modality") if f.get("modality") in rooms.MODALITIES else "f2f",
                              meals_requested=bool(f.get("room_meals")), actor=user["username"], today=today_local(),
                              calendar_entry_id=entry_id, standby=bool(f.get("room_standby")))
            if r.get("standby"):
                return f" Conference room: provisional standby request {r['ref_code']} (those hours are taken, so nothing is held)."
            return f" Conference room requested ({r['ref_code']}); the Administrative Section will decide."
        except rooms.RoomError as e:
            return f" Conference room not requested: {e} You can ask again by editing the item."
        except Exception:                                    # noqa: BLE001
            return " Conference room not requested because of a problem. You can ask again by editing the item."

    # ── the read API (H3) ───────────────────────────────────────────────────────

    API_LAYERS = ("entries", "activities", "leave", "holidays", "birthdays", "rooms")
    API_MAX_DAYS = 92

    def _api_item(i):
        """What the API hands out for one calendar item: a WHITELIST, so a field added to the internal
        item later is private until someone decides otherwise. Notes and meeting links are never in it
        (only that a link exists), and a leave item carries no reason because none is ever stored."""
        return {
            "id": i["key"], "layer": i["layer"], "title": i["title"], "kind": i["kind"], "status": i["status"],
            "start": i["start"], "end": i["end"], "start_time": i["start_time"], "end_time": i["end_time"],
            "all_day": i["all_day"], "owner": i["owner_label"], "venue": i["venue"], "modality": i["modality"],
            "has_meeting_link": bool(i["meeting_url"]), "tags": i["tags"], "url": i["url"],
            "repeats": "repeats" in (i["flags"] or []),
            "people": [{"user_id": p["user_id"], "name": p["name"], "role": p["role"]} for p in i["people"]],
            "activity": ({"lifecycle": i["css"]["lifecycle"], "registered": i["css"]["registered"]} if i["css"] else None),
        }

    @router.get("/api/calendar")
    def api_calendar(request: Request):
        """The calendar as JSON, for the assistant and for tools. It is `office_calendar.items_between`
        — the very function behind the /calendar page — so what it returns is exactly what that person
        may see there, in the scope they ask for, and never more. Window: at most 92 days."""
        user = request.state.user
        if not user:
            return JSONResponse({"error": "sign in required"}, status_code=401)
        q = request.query_params

        def bad(msg):
            return JSONResponse({"error": msg}, status_code=400)
        today = today_local()
        try:
            start = date.fromisoformat(q.get("start") or today.isoformat())
            end = date.fromisoformat(q.get("end") or (start + timedelta(days=13)).isoformat())
        except ValueError:
            return bad("start and end must be dates like 2026-10-19")
        if end < start:
            return bad("end is before start")
        if (end - start).days + 1 > API_MAX_DAYS:
            return bad(f"ask for at most {API_MAX_DAYS} days at a time")
        layers = [x for x in (q.get("layers") or "entries,activities,holidays").split(",") if x]
        if not layers or any(x not in API_LAYERS for x in layers):
            return bad("layers must be some of " + ", ".join(API_LAYERS))
        conn = get_conn()
        try:
            ctx = oc.viewer_context(conn, user)
            allowed = {c["key"] for c in oc.scope_choices(ctx)}
            scope = q.get("scope") or oc.DEFAULT_SCOPE
            if scope not in allowed:
                return bad("scope must be one of " + ", ".join(sorted(allowed)))
            kind = q.get("kind") or ""
            if kind and kind not in KIND_LABELS:
                return bad("unknown kind")
            items = oc.items_between(conn, user, start, end, scope=scope, layers=layers,
                                     filters={"kinds": {kind}} if kind else None)
        finally:
            conn.close()
        return JSONResponse({"start": start.isoformat(), "end": end.isoformat(), "scope": scope,
                             "count": len(items), "items": [_api_item(i) for i in items]},
                            headers={"Cache-Control": "no-store"})

    # ── .ics: one item, and the personal feed (G4) ──────────────────────────────

    @router.get("/calendar/entries/{entry_id}/event.ics")
    def calendar_entry_ics(request: Request, entry_id: int):
        """Download one item as an .ics. Same visibility as its page: what you cannot see is a 404."""
        conn = get_conn()
        try:
            e = oc.viewable_entry(conn, request.state.user, entry_id)
            if e is None:
                return Response(status_code=404)
            body = cics.vcalendar([cics.entry_event(e, base_url(request) if base_url else "")], method="PUBLISH")
        finally:
            conn.close()
        return Response(content=body.encode("utf-8"), media_type="text/calendar; charset=utf-8",
                        headers={"Content-Disposition": f'attachment; filename="calendar-item-{entry_id}.ics"'})

    @router.get("/calendar/feed/{token}.ics")
    def calendar_feed(request: Request, token: str):
        """The subscription feed. No login (calendar apps cannot sign in): the long random token in
        the URL is the credential, and resetting it kills the old link. Wrong, reset or switched-off
        tokens all answer the same 404, so nothing leaks about which exist."""
        conn = get_conn()
        try:
            acct = st.feed_owner(conn, token)
            if acct is None:
                return Response(status_code=404)
            cfg = st.feed_get(conn, acct["id"])
            body = oc.build_feed(conn, acct, base_url(request) if base_url else "", scope=cfg["scope"],
                                 birthdays=cfg["birthdays"], today=today_local())
        finally:
            conn.close()
        return Response(content=body.encode("utf-8"), media_type="text/calendar; charset=utf-8",
                        headers={"Cache-Control": "private, max-age=900", "X-Robots-Tag": "noindex"})

    def _back_to_me(msg="", err=""):
        q = (f"msg={quote(msg)}" if msg else f"err={quote(err)}")
        return RedirectResponse(f"/me?{q}#calendar-feed", status_code=303)

    @router.post("/me/calendar-feed/reset")
    def me_feed_reset(request: Request):
        conn = get_conn()
        try:
            had = st.feed_get(conn, request.state.user["id"])
            st.feed_reset(conn, request.state.user["id"])
            st.audit(conn, request.state.user["username"], "calendar_feed_reset", target_type="user",
                     target_id=request.state.user["id"], summary="created a new calendar feed link" if had else "created a calendar feed link")
        finally:
            conn.close()
        return _back_to_me("Your calendar link is ready. Any older link no longer works.")

    @router.post("/me/calendar-feed/off")
    def me_feed_off(request: Request):
        conn = get_conn()
        try:
            st.feed_off(conn, request.state.user["id"])
            st.audit(conn, request.state.user["username"], "calendar_feed_off", target_type="user",
                     target_id=request.state.user["id"], summary="turned off their calendar feed link")
        finally:
            conn.close()
        return _back_to_me("Your calendar link was turned off.")

    @router.post("/me/calendar-feed/settings")
    async def me_feed_settings(request: Request):
        raw = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
        scope = (raw.get("scope") or [""])[0]
        conn = get_conn()
        try:
            if not st.feed_get(conn, request.state.user["id"]):
                return _back_to_me(err="Create your calendar link first.")
            try:
                st.feed_set(conn, request.state.user["id"], scope, (raw.get("birthdays") or [""])[0] == "1")
            except ValueError as ex:
                return _back_to_me(err=str(ex))
        finally:
            conn.close()
        return _back_to_me("Saved. Your calendar app picks the change up the next time it refreshes.")

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
            f = _blank_form(conn, request.state.user, day)
            # "More options…" on the quick-add sheet hands over what was already typed there.
            q = request.query_params
            for k in ("title", "kind", "audience", "owner_org_id", "end_date", "start_time", "end_time"):
                if q.get(k):
                    f[k] = q[k][:200]
            if q.getlist("people"):
                f["people"] = q.getlist("people")
            if q.getlist("extra_org_ids"):
                f["extra_org_ids"] = [x for x in q.getlist("extra_org_ids") if x.isdigit()]
            return _form_page(request, conn, f)
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
            series = None
            if not error and f.get("detach_from"):              # "just this one": the series must still repeat then
                series = (oc.viewable_entry(conn, request.state.user, int(f["detach_from"]))
                          if f["detach_from"].isdigit() else None)
                ctx = _series_ctx(series, f.get("detach_date", "")) if series else None
                if not ctx or not ctx["occ"]:
                    error = "That repeat is gone or was already changed. Open the series again."
            if not error:
                error = _room_precheck(conn, f)
            if not error:
                try:
                    title = fields["title"]
                    eid = st.cal_create(conn, fields.pop("title"), fields.pop("start_date"),
                                        people=people, tags=tags,
                                        by=request.state.user["username"], **fields)
                except ValueError as e:
                    error = str(e)
            if error:
                detach = ({"id": series["id"], "date": f["detach_date"], "date_label": f["detach_date"]}
                          if series else None)
                return _form_page(request, conn, f, error=error, status_code=400, detach=detach)
            if series:
                _add_skip(conn, series, ctx["occ"], request.state.user["username"])
            said = ("Added to the calendar." + _room_after_save(conn, request.state.user, eid, title, f)
                    + meet_relay.sync(conn, eid, by=request.state.user["username"]))
        finally:
            conn.close()
        back = _safe_back(f.get("next", ""))
        if back:                                              # the quick-add sheet returns to the page it came from
            return RedirectResponse(back + ("&" if "?" in back else "?") + "ok=" + quote(said),
                                    status_code=303)
        return RedirectResponse(f"/calendar/entries/{eid}?ok={quote(said)}",
                                status_code=303)

    def _series_ctx(e, on):
        """What the item page needs for a repeating series: how it repeats, the dates skipped so
        far, and — when it was opened from one occurrence (`?date=`) — that occurrence."""
        if not e.get("rrule"):
            return None
        first = date.fromisoformat(e["start_date"])
        span = (date.fromisoformat(e["end_date"] or e["start_date"]) - first).days
        skipped = recurrence.parse_exdates(e["exdates"])
        occ = None
        try:
            d = date.fromisoformat(on)
            if d in recurrence.occurrences(first, e["rrule"], e["exdates"], d, d, span):
                occ = d
        except ValueError:
            pass
        until = recurrence.until_of(e["rrule"])
        nxt = recurrence.occurrences(first, e["rrule"], e["exdates"], max(today_local(), first),
                                     until or today_local(), span) if until else []
        return {"text": recurrence.describe(e["rrule"], first), "skipped": skipped, "occ": occ,
                "next": nxt[0] if nxt else None}

    def _add_skip(conn, e, d, by):
        """Skip one occurrence: add it to the series' skipped dates (a schedule change, so it bumps
        the sequence and the people on it are told). Returns an error sentence or ''."""
        first = date.fromisoformat(e["start_date"])
        span = (date.fromisoformat(e["end_date"] or e["start_date"]) - first).days
        if d not in recurrence.occurrences(first, e["rrule"], e["exdates"], d, d, span):
            return "That date isn't one of this item's repeats."
        st.cal_update(conn, e["id"], by=by, exdates=recurrence.join_exdates(recurrence.parse_exdates(e["exdates"]) + [d]))
        return ""

    @router.post("/calendar/entries/{entry_id}/skip")
    async def calendar_skip(request: Request, entry_id: int):
        raw = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
        conn = get_conn()
        try:
            e = oc.viewable_entry(conn, request.state.user, entry_id)
            if e is None:
                return _not_found(request)
            try:
                d = date.fromisoformat((raw.get("date") or [""])[0])
                err = "" if e["rrule"] else "That item doesn't repeat."
            except ValueError:
                d, err = None, "Pick one of the dates."
            err = err or _add_skip(conn, e, d, request.state.user["username"])
        finally:
            conn.close()
        note = f"err={quote(err)}" if err else f"ok={quote('Skipped ' + d.strftime('%b ') + str(d.day) + '. The rest of the series is unchanged.')}"
        return RedirectResponse(f"/calendar/entries/{entry_id}?{note}", status_code=303)

    @router.post("/calendar/entries/{entry_id}/unskip")
    async def calendar_unskip(request: Request, entry_id: int):
        raw = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
        conn = get_conn()
        try:
            e = oc.viewable_entry(conn, request.state.user, entry_id)
            if e is None:
                return _not_found(request)
            try:
                d = date.fromisoformat((raw.get("date") or [""])[0])
            except ValueError:
                d = None
            skipped = recurrence.parse_exdates(e["exdates"])
            if d is None or d not in skipped:
                err = "That date isn't skipped."
            else:
                st.cal_update(conn, entry_id, by=request.state.user["username"],
                              exdates=recurrence.join_exdates([x for x in skipped if x != d]))
                err = ""
        finally:
            conn.close()
        note = f"err={quote(err)}" if err else f"ok={quote('Put back ' + d.strftime('%b ') + str(d.day) + '.')}"
        return RedirectResponse(f"/calendar/entries/{entry_id}?{note}", status_code=303)

    @router.get("/calendar/entries/{entry_id}/detach", response_class=HTMLResponse)
    def calendar_detach(request: Request, entry_id: int):
        """"Change just this one": a new one-off item pre-filled from the series for that date.
        Saving it also skips the date in the series (see calendar_create)."""
        d_raw = request.query_params.get("date", "")
        conn = get_conn()
        try:
            e = oc.viewable_entry(conn, request.state.user, entry_id)
            if e is None:
                return _not_found(request)
            ctx = _series_ctx(e, d_raw)
            if not ctx or not ctx["occ"]:
                return RedirectResponse(f"/calendar/entries/{entry_id}?err={quote('Pick one of the repeats to change.')}",
                                        status_code=303)
            f = _entry_form(e)
            span = (date.fromisoformat(e["end_date"] or e["start_date"]) - date.fromisoformat(e["start_date"])).days
            f.update(start_date=ctx["occ"].isoformat(), updated_at="", repeat="none", until="",
                     end_date=(ctx["occ"] + timedelta(days=span)).isoformat() if span else "")
            return _form_page(request, conn, f, detach={"id": entry_id, "date": ctx["occ"].isoformat(),
                                                        "date_label": f"{ctx['occ']:%A, %B} {ctx['occ'].day}"})
        finally:
            conn.close()

    @router.get("/calendar/entries/{entry_id}", response_class=HTMLResponse)
    def calendar_entry(request: Request, entry_id: int, ok: str = "", err: str = ""):
        # room messages (roomok / roomerr) are read by _room_link from the query string
        user = request.state.user
        conn = get_conn()
        try:
            e = oc.viewable_entry(conn, user, entry_id)
            if e is None:
                return _not_found(request)
            cards = oc._people_cards(conn, [p["user_id"] for p in e["people"]])
            owner_units = oc._units(conn, [e["owner_org_id"], *e["extra_org_ids"]])
            owners = [owner_units[i]["label"] for i in (e["owner_org_id"], *e["extra_org_ids"]) if i in owner_units]
            revs = st.cal_revisions(conn, entry_id)
            names = oc.display_names(conn, [e["created_by"], e["updated_by"]]
                                     + [r["changed_by"] for r in revs])
            st.cal_mark_seen(conn, user["id"], [entry_id])      # opening it IS seeing it
            series = _series_ctx(e, request.query_params.get("date", ""))
            heads_up = oc.entry_heads_up(conn, user, e)
            can_css = auth.can(user["role"], "create_activity")
            linked = st.get_event_by_id(conn, e["event_id"]) if e["event_id"] else None
            eligible = can_css and oc.entry_can_collect_feedback(e)
            css = {"linked": linked, "eligible": eligible, "manage": auth.can(user["role"], "manage_event"),
                   "candidates": oc.activity_candidates_for_entry(conn, e) if eligible else []}
            room_link = _room_link(request, conn, e)
            filing = _travel_block(conn, user, e, request.query_params.get("date", ""))
            documents = _documents_block(conn, e)
            # A requested or booked conference room makes the venue the office: no travel to claim.
            if filing and not filing["chip"] and room_link and room_link.get("state") in (
                    "requested", "booked", "move_pending", "mismatch", "archived_holds"):
                filing = None
        finally:
            conn.close()
        who = lambda u: names.get(u, u or "someone")           # noqa: E731
        return templates.TemplateResponse(request, "calendar_entry.html", {
            "nav_active": "calendar", "e": e, "ok": ok, "err": err, "css": css, "heads_up": heads_up, "series": series,
            "calendar_back": entry_calendar_back(request, e["start_date"]),
            "room_link": room_link, "filing": filing, "documents": documents,
            "owner": " + ".join(owners) or None, "owners": owners,
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
            if activity or any(r["status"] in ("requested", "approved") for r in rooms.reservations_for_entry(conn, entry_id)):
                f["reserve_room"] = ""                       # it already has a room (or its activity does): never a second one
            elif not error:
                error = _room_precheck(conn, f)
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
            said = ("Saved." + (_room_after_save(conn, user, entry_id, f["title"], f) if f.get("reserve_room") else "")
                    + meet_relay.sync(conn, entry_id, by=user["username"]))
        finally:
            conn.close()
        return RedirectResponse(f"/calendar/entries/{entry_id}?ok={quote(said)}",
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

    @router.post("/calendar/entries/{entry_id}/documents/{key}/needed")
    async def calendar_document_needed(request: Request, entry_id: int, key: str):
        """Say whether this activity needs a DPO or an invitation: yes, no, or 'auto' to follow the suggestion."""
        raw = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
        choice = (raw.get("needed") or [""])[0]
        user = request.state.user
        conn = get_conn()
        try:
            e = oc.viewable_entry(conn, user, entry_id)
            if e is None:
                return _not_found(request)
            if key not in activity_docs.DOCS or choice not in ("yes", "no", "auto") or e["status"] == "cancelled":
                note = f"err={quote('That choice was not understood.')}"
            else:
                activity_docs.set_needed(conn, entry_id, key, {"yes": True, "no": False, "auto": None}[choice], user["username"])
                st.audit(conn, user["username"], "activity_doc_needed", target_type="calendar_entry", target_id=entry_id,
                         summary=f"{key}: {choice}")
                note = f"ok={quote(activity_docs.DOCS[key]['label'] + ': saved.')}"
        finally:
            conn.close()
        return RedirectResponse(f"/calendar/entries/{entry_id}?{note}#documents", status_code=303)

    @router.post("/calendar/entries/{entry_id}/documents/{key}/draft")
    async def calendar_document_draft(request: Request, entry_id: int, key: str):
        """Draft the document as a Google Doc from the entry's details. The relay call can take a few seconds, so
        it runs off the event loop; the database work stays on this thread (a connection is not shared)."""
        user = request.state.user
        raw = parse_qs((await request.body()).decode("utf-8"), keep_blank_values=True)
        positions = (raw.get("positions") or [""])[0] == "1"          # positions are written only when asked for
        conn = get_conn()
        try:
            e = oc.viewable_entry(conn, user, entry_id)
            if e is None:
                return _not_found(request)
            if key not in activity_docs.DOCS or e["status"] == "cancelled" or e["kind"] not in DOC_KINDS:
                note = f"err={quote('That document cannot be drafted for this item.')}"
            elif not gdocs_relay.configured():
                note = f"err={quote(activity_docs.PLAIN_ERRORS['not_configured'])}"
            elif not ratelimit.allow("activity_doc_draft", f"u{user['id']}"):
                note = f"err={quote('Too many requests. Wait a minute and try again.')}"
            else:
                prep = activity_docs.prepare(conn, e, key, user, _doc_owner_label(conn, e), positions=positions)
                relay_res = await run_in_threadpool(prep.call)        # only the network call leaves this thread
                res = activity_docs.record(conn, prep, relay_res, user)
                st.audit(conn, user["username"], "activity_doc_draft", target_type="calendar_entry", target_id=entry_id,
                         summary=f"{key}: {'drafted' if res['ok'] else 'failed'}")
                label = activity_docs.DOCS[key]["label"]
                note = f"ok={quote(label + ': draft made and shared with you in Google Docs. No email is sent, so open it from the link below, complete the blanks and check it.')}" if res["ok"] else f"err={quote(res['error'])}"
        finally:
            conn.close()
        return RedirectResponse(f"/calendar/entries/{entry_id}?{note}#documents", status_code=303)

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
            meet_relay.sync(conn, entry_id, by=user["username"])
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
                "warnings": res.warnings, "stats": res.stats, "unmapped_colors": res.unmapped_colors,
                "suggestions": {"owners": cis.suggest_owners([d.to_dict() for d in res.drafts]),
                                "series": cis.suggest_series([d.to_dict() for d in res.drafts])}})
        finally:
            conn.close()
        return RedirectResponse(f"/calendar/import/{batch_id}", status_code=303)

    def _review_page(request, conn, batch, posted=None, errors=(), status_code=200, undone=None):
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
            "rows": cia.review_rows(drafts, existing, posted, batch["payload"].get("suggestions")),
            "unit_labels": dict(ci.OWNER_LABELS),
            "stats": batch["payload"]["stats"], "file_warnings": batch["payload"]["warnings"],
            "holidays": cia.holiday_choices(batch, have_hol),
            "hol_ticked": {k[4:] for k in (posted or {}) if k.startswith("hol_")},
            "hol_kinds": dict(st.HOLIDAY_KINDS),
            "undo": cia.undo_preview(conn, batch) if batch["imported_at"] else None,
            "undone": undone,
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
            q = request.query_params
            undone = ({"removed": q.get("removed"), "kept": q.get("kept"), "holidays": q.get("holidays")}
                      if q.get("undone") else None)
            return _review_page(request, conn, batch, undone=undone)
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

    @router.post("/calendar/import/{batch_id}/undo")
    def calendar_import_undo(request: Request, batch_id: int):
        denied = _admin_only(request)
        if denied:
            return denied
        conn = get_conn()
        try:
            batch = st.cal_import_get(conn, batch_id)
            if batch is None or not batch["imported_at"]:
                return RedirectResponse(f"/calendar/import/{batch_id}" if batch else "/calendar/import",
                                        status_code=303)
            r = cia.undo(conn, batch, request.state.user["username"])
        finally:
            conn.close()
        return RedirectResponse(f"/calendar/import/{batch_id}?undone=1&removed={r['removed']}"
                                f"&kept={len(r['kept'])}&holidays={r['holidays']}", status_code=303)

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
