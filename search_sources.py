"""Record sources for /api/search.

Each source is a dict

    {"key": str, "section": str, "scopes": {"all", "css", ...},
     "run": run(conn, user, terms, ctx) -> list[row]}

and a row is the shape window.SEARCH_INDEX already uses:
{title, hint, url, section, kw}.

`ctx` carries what a source needs from app.py as callables/values — `get_atoms`,
`view_memo`, `humandate`, `is_chief`, `today` — so this module never imports
`app` (same pattern as office_connect.team_view_data).

`run_sources` is the one loop: it picks the sources for the requested scope,
isolates each in try/except (one broken source never breaks search), caps each
section and the whole response.
"""
from __future__ import annotations

import logging
from datetime import date, timedelta

import dashboard_insights as di
import office_calendar as oc
import office_connect as oconn
import rooms
import storage as st

log = logging.getLogger("search_sources")

SECTION_CAP = 5
TOTAL_CAP = 30
SCOPES = ("all", "css")


def _like_where(terms, cols):
    """(clause, params) — AND across terms, OR across columns, LIKE match."""
    parts, params = [], []
    for t in terms:
        parts.append("(" + " OR ".join(f"lower(COALESCE({c},'')) LIKE ?" for c in cols) + ")")
        params.extend(f"%{t}%" for _ in cols)
    return " AND ".join(parts), params


def _activities(conn, user, terms, ctx):
    # Search the SAME event list the Activities report is built from (atoms
    # grouped into events), so a hit's id matches /reports/activities/<id>.
    # The plain `event` table holds only link-tree events, not the historical
    # backlog — those activities live as grouped form instances. build_events
    # is memoized + prewarmed, so this is an in-memory filter, not a rebuild.
    atoms = ctx["get_atoms"](conn)
    events = ctx["view_memo"]("events", ("", "all"),
                              lambda: di.build_events(atoms, st.list_activity_instances(conn)))
    rows = []
    for e in events:
        if not e["f2"]:                       # listing shows only F2-reviewed events
            continue
        hay = " ".join([e["name"] or "", e.get("organizer") or "",
                        e.get("venue") or ""]).lower()
        if all(t in hay for t in terms):
            rows.append({
                "title": e["name"],
                "hint": (e["organizer"] or "Event") + " · " + ctx["humandate"](e["date"]),
                "url": f"/reports/activities/{e['id']}",
                "section": "Activities", "kw": "",
            })
            if len(rows) >= SECTION_CAP:      # events are newest-first already
                break
    return rows


def _people(conn, user, terms, ctx):
    w, p = _like_where(terms, ["rp.name", "rp.position", "rp.designation", "rp.focus_area"])
    rows = []
    for r in conn.execute(
        f"SELECT rp.id, rp.name,"
        f" COALESCE(rp.position, rp.designation, '') AS role_text,"
        f" COALESCE(ou.name, rp.agency, '') AS unit"
        f" FROM resource_person rp"
        f" LEFT JOIN org_unit ou ON ou.id = rp.org_unit_id"
        f" WHERE {w} LIMIT {SECTION_CAP}", p
    ).fetchall():
        hint = " · ".join(x for x in [r["role_text"], r["unit"]] if x) or "Directory"
        rows.append({
            "title": r["name"],
            "hint": hint,
            "url": f"/dashboard/people/{r['id']}",
            "section": "People", "kw": "",
        })
    return rows


# ── office-wide sources (scope "all" only) ───────────────────────────────────
#
# Each one calls the SAME function as the page it links to, as the signed-in person, so search
# can never show something that page would not. No new SQL where an existing function answers.

CAL_BACK_DAYS = 30
CAL_AHEAD_DAYS = 90


def _long_enough(terms):
    return len(" ".join(terms)) >= 2


def _span(a, b):
    f = lambda d: f"{d:%b} {d.day}"                                  # noqa: E731
    return f(a) if a == b else f"{f(a)} – {f(b)}"


def _calendar(conn, user, terms, ctx):
    if not _long_enough(terms):
        return []
    today = ctx["today"]
    items = oc.items_between(conn, user, today - timedelta(days=CAL_BACK_DAYS),
                             today + timedelta(days=CAL_AHEAD_DAYS), scope="blend",
                             layers=["entries", "activities"])
    live = [i for i in items if i["kind"] != "banner" and i["status"] not in ("cancelled", "postponed")]
    hits = [i for i in live if all(t in (i["title"] or "").lower() for t in terms)]

    def nearest(i):                                    # upcoming first, then past; closest day first
        a = date.fromisoformat(i["start"])
        return (a < today, abs((a - today).days))
    hits.sort(key=nearest)
    rows = []
    for i in hits[:SECTION_CAP]:
        a, b = date.fromisoformat(i["start"]), date.fromisoformat(i["end"])
        # date, time and "tentative" only — never notes, a meeting link or a leave reason
        bits = [_span(a, b)]
        if i["start_time"]:
            bits.append(i["start_time"])
        if i["status"] == "tentative":
            bits.append("tentative")
        rows.append({"title": i["title"], "hint": " · ".join(bits), "url": i["url"] or "/calendar",
                     "section": "Calendar", "kw": ""})
    return rows


def _todo(conn, user, terms, ctx):
    if not _long_enough(terms):
        return []
    rows = []
    for t in oconn.home_tasks(conn, user, ctx["today"]):
        hay = f"{t['title']} {t.get('detail') or ''}".lower()
        if all(x in hay for x in terms):
            rows.append({"title": t["title"], "hint": t.get("detail") or "To do", "url": t["url"],
                         "section": "My to-do", "kw": ""})
            if len(rows) >= SECTION_CAP:
                break
    return rows


def _requests(conn, user, terms, ctx):
    """The person's OWN wellness claims and work arrangement — never anyone else's, whatever
    their role (an approver's queue is a different page)."""
    if not _long_enough(terms):
        return []
    uid, hd, rows = user["id"], ctx["humandate"], []
    for c in st.list_my_wellness_claims(conn, uid, limit=SECTION_CAP * 2):
        hay = " ".join(["wellness break", c["break_date"], hd(c["break_date"]), c["status"]]).lower()
        if all(t in hay for t in terms):
            rows.append({"title": f"Wellness break · {hd(c['break_date'])}",
                         "hint": f"{c['start_time']} · {c['status']}", "url": "/wellness",
                         "section": "My requests", "kw": ""})
    open_ps = st.work_arrangement_open_periods()
    if open_ps:
        ps = open_ps[0]
        wa = st.my_pending_work_arrangement(conn, uid, ps) or st.my_work_arrangement_for(conn, uid, ps)
        if wa:
            label = st.work_arrangement_period_label(ps)
            hay = " ".join(["work arrangement awa", label, wa.get("arrangement_label") or "",
                            wa["status"]]).lower()
            if all(t in hay for t in terms):
                rows.append({"title": f"Work arrangement · {label}",
                             "hint": f"{wa.get('arrangement_label') or ''} · {wa['status']}".strip(" ·"),
                             "url": "/work-arrangement", "section": "My requests", "kw": ""})
    return rows[:SECTION_CAP]


_ROOM_WORDS = ("room", "conference", "book")


def _room(conn, user, terms, ctx):
    if not _long_enough(terms):
        return []
    rows, hd = [], ctx["humandate"]
    if any(w in t for t in terms for w in _ROOM_WORDS):
        rows.append({"title": "Book the conference room", "hint": "Request a time slot", "url": "/rooms",
                     "section": "Conference room", "kw": ""})
    for r in rooms.list_for_user(conn, user["id"], upcoming_only=True, today=ctx["today"]):
        hay = " ".join([r["title"] or "", r["day"], hd(r["day"]), "conference room"]).lower()
        if all(t in hay for t in terms):
            rows.append({"title": r["title"] or "Conference room", "hint": f"{hd(r['day'])} · {r['status']}",
                         "url": "/rooms/mine", "section": "Conference room", "kw": ""})
    return rows[:SECTION_CAP]


def _help(conn, user, terms, ctx):
    if not _long_enough(terms):
        return []
    rows = []
    for g in ctx["help_catalog"]():
        texts = [(s.get("title") or "", s.get("body") or "") for s in g["steps"]]
        hay = (g["label"] + " " + " ".join(a + " " + b for a, b in texts)).lower()
        if all(t in hay for t in terms):
            hit = next((a for a, b in texts if all(t in (a + " " + b).lower() for t in terms)), "")
            rows.append({"title": f"How to use {g['label']}", "hint": hit or "Page guide",
                         "url": g["replay_url"], "section": "Help", "kw": ""})
            if len(rows) >= SECTION_CAP:
                break
    return rows


def _today_label(state):
    return {"onsite": "In the office today", "wfh": "Working from home today",
            "field": "In the field today", "leave": "On leave today",
            "off": "Off today"}.get(state, st.BASIC_STATUS_LABELS["unknown"])


def _colleagues(conn, user, terms, ctx):
    """People in the directory — name, nickname, position or unit — with today's BASIC status
    only (see storage.colleague_status_for; it honours the admin's bureau/team switch)."""
    if not _long_enough(terms):
        return []
    hits = []
    for p in st.colleague_directory(conn):
        hay = " ".join([p["name"], p["nickname"], p["position"], p["unit"]]).lower()
        if not all(t in hay for t in terms):
            continue
        words = p["name"].lower().split()
        exact = (words and terms[0] == words[0]) or terms[0] == p["nickname"].lower()
        hits.append((0 if exact else 1, p["name"].lower(), p))
    if not hits:
        return []
    hits.sort(key=lambda h: h[:2])
    status = st.colleague_status_for(conn, user, ctx["today"])
    rows = []
    for _rank, _n, p in hits[:SECTION_CAP]:
        bits = [b for b in (p["position"], p["unit"]) if b]
        bits.append(_today_label(status.get(p["user_id"])))
        rows.append({"title": p["name"], "hint": " · ".join(bits), "url": f"/people/{p['user_id']}",
                     "section": "Colleagues", "kw": ""})
    return rows


def _documents(conn, user, terms, ctx):
    import documents
    if not documents.enabled(conn):
        return []
    query = " ".join(terms)
    return [{"title": doc["subject"], "hint": doc["number"], "url": "/documents/"+str(doc["id"]),
             "section": "Documents", "kw": ""} for doc in documents.list_page(conn,user,query,limit=SECTION_CAP,totals=False,snippets=False)['documents']]


SOURCES = [
    {"key": "documents", "section": "Documents", "scopes": {"all"}, "run": _documents},
    {"key": "activities", "section": "Activities", "scopes": {"all", "css"}, "run": _activities},
    {"key": "people", "section": "People", "scopes": {"all", "css"}, "run": _people},
    {"key": "calendar", "section": "Calendar", "scopes": {"all"}, "run": _calendar},
    {"key": "todo", "section": "My to-do", "scopes": {"all"}, "run": _todo},
    {"key": "requests", "section": "My requests", "scopes": {"all"}, "run": _requests},
    {"key": "room", "section": "Conference room", "scopes": {"all"}, "run": _room},
    {"key": "help", "section": "Help", "scopes": {"all"}, "run": _help},
    {"key": "colleagues", "section": "Colleagues", "scopes": {"all"}, "run": _colleagues},
]


def normalize_scope(scope):
    return scope if scope in SCOPES else "all"


def run_sources(conn, user, terms, ctx, scope="all", sources=None):
    """Rows from every source for `scope`, in source order. A source that raises is
    logged and skipped; each section is capped at SECTION_CAP and the response at
    TOTAL_CAP."""
    scope = normalize_scope(scope)
    out = []
    for src in (SOURCES if sources is None else sources):
        if scope not in src["scopes"]:
            continue
        try:
            rows = src["run"](conn, user, terms, ctx)[:SECTION_CAP]
        except Exception:
            log.exception("search source %r failed", src.get("key"))
            continue
        out.extend(rows)
    return out[:TOTAL_CAP]
