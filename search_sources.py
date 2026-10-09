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

import dashboard_insights as di
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


SOURCES = [
    {"key": "activities", "section": "Activities", "scopes": {"all", "css"}, "run": _activities},
    {"key": "people", "section": "People", "scopes": {"all", "css"}, "run": _people},
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
