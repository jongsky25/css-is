"""
Office Connect UX telemetry — passive interface-friction signal.
=========================================================

Ported from jongsky25/ofis-platform's lib/telemetry.ts (commit 7a7e369, "Add
passive UX-behavior telemetry with a ranked improvement digest") per
docs/UX_TELEMETRY_HANDOFF_PLAN.md. Three halves, mirroring the reference:
  1. Controlled vocabulary (UI_EVENT_TYPES).
  2. Sanitizers — run client-side (static/js/telemetry.js) and again here as
     defense-in-depth (the /telemetry ingest route in app.py calls these).
  3. Pure aggregators + build_digest — take plain dict rows, no DB. build_digest
     is the point of the whole system: a ranked, source-located,
     feedback-correlated "what to fix" summary (see app.py's /admin/ux-insights).

Distinct from Spot Feedback (storage.py's spot_feedback table): that's what a
user bothers to type up. This is what happens passively — dead/rage clicks,
failed searches, client errors — so friction can eventually be ranked without
anyone having to report it.

Everything here is PURE (no DB, no FastAPI import) so it's cheap to unit test
and safe to import from both the /telemetry route and the digest view.
"""
from __future__ import annotations
import re

# ── Controlled vocabulary (a TEXT column, not a real enum — a new type needs
# no migration). form_abandon has no detector wired yet (matching the OFIS
# reference itself, which declares it but has never shipped detection either)
# — kept in the vocabulary so a future capture-script addition needs no schema
# change.
UI_EVENT_TYPES = {
    "pageview", "dead_click", "rage_click", "search_empty", "client_error", "form_abandon",
    # v3.26 — the questions the 30-day handoff couldn't answer: did the task
    # succeed (form_submit / form_error, plus the server's own http_error), how
    # often does search come up empty (search = every search, not just the
    # empty ones), and how long do pages take (page_timing).
    "form_submit", "form_error", "search", "page_timing",
    # v6.10 — the assistant in the search box and on /start: asked, answered, or fell back.
    "ask",
}

# What a search found, by kind of result (counts only, never the term) — the section names the home
# box can return. Anything else a browser sends is dropped.
SEARCH_SECTIONS = ("Activities", "People", "Calendar", "My to-do", "My requests", "Conference room",
                   "Help", "Colleagues", "Go to", "CSS", "Wellness", "AWA", "Office", "Administrator")
ASK_STAGES = ("fired", "answered", "fallback")
ASK_KINDS = ("navigate", "answer", "help", "action")

# Written by the server itself (app.py's _metrics_gate), never accepted from a
# browser: a 403 / 404 / 5xx a signed-in person actually hit.
SERVER_EVENT_TYPES = {"http_error"}

VIEWPORTS = ("phone", "tablet", "desktop")

MAX_TEXT = 160
MAX_SELECTOR = 1000
MAX_BATCH = 50


def sanitize_text(s, max_len=MAX_TEXT):
    """Collapse whitespace, mask any run of 3+ digits (ids/phone numbers/amounts)
    as '###', cap length. Mirrors lib/telemetry.ts's sanitizeText, minus the
    OFIS-specific TIN pattern. Returns None for empty input."""
    if not s:
        return None
    clean = re.sub(r"\s+", " ", str(s)).strip()
    if not clean:
        return None
    clean = re.sub(r"\d{3,}", "###", clean).strip()
    if not clean:
        return None
    return clean if len(clean) <= max_len else clean[:max_len] + "…"


def sanitize_selector(s, max_len=MAX_SELECTOR):
    """Trim + cap a CSS selector path (already built client-side)."""
    if not s:
        return None
    clean = str(s).strip()
    if not clean:
        return None
    return clean if len(clean) <= max_len else clean[:max_len]


_DATE_RE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")
_HEX_TOKEN_RE = re.compile(r"^[0-9a-f]{6,}$", re.IGNORECASE)
_NUMERIC_ID_RE = re.compile(r"^\d+$")


def mask_route(path):
    """Turn a concrete pathname into a route PATTERN: numeric ids, hex tokens
    (the /r/<token>, /e/<token>, /encode/<token> link shapes), and date segments
    become {id} / {token} / {date}. Query string and fragment are dropped.

    Same curly-brace convention as monitoring.bucket_path — that table is a
    hand-curated per-route map (used for the /ops request-log breakdown); this
    is its generic sibling, a catch-all segment-shape rule so a route not yet
    added there still never carries a raw id/token into ui_event.

    Idempotent: masking an already-masked route (e.g. what the client sent,
    already masked by static/js/telemetry.js) is a no-op, since none of the
    three patterns above match a literal '{id}'/'{token}'/'{date}' segment —
    which is exactly what makes it safe to re-run here as the server-side
    'never trust the client mask alone' pass."""
    if not path:
        return "/"
    p = str(path)
    cut = min((i for i in (p.find("?"), p.find("#")) if i >= 0), default=-1)
    if cut >= 0:
        p = p[:cut]
    p = re.sub(r"^https?://[^/]+", "", p, flags=re.IGNORECASE)
    if not p.startswith("/"):
        p = "/" + p
    segs = []
    for seg in p.split("/"):
        if not seg:
            segs.append(seg)
        elif _DATE_RE.match(seg):
            segs.append("{date}")
        elif _HEX_TOKEN_RE.match(seg):
            segs.append("{token}")
        elif _NUMERIC_ID_RE.match(seg):
            segs.append("{id}")
        else:
            segs.append(seg)
    masked = "/".join(segs)
    if len(masked) > 1 and masked.endswith("/"):
        masked = masked[:-1]
    return masked


# ─────────────────────────────────────────────────────────────────────────────
# Aggregation (pure — take plain dict rows, e.g. from storage.list_ui_events /
# storage.list_spot_feedback). Built to RANK opportunities, not just count.
# Mirrors lib/telemetry.ts's aggregation half; field names are this app's own
# snake_case (user_id/session_id/element_selector/element_text), not a
# mechanical rename of the TS camelCase.
# ─────────────────────────────────────────────────────────────────────────────

def top_routes(rows, limit=10):
    """Top screens by pageview count, with distinct sessions/users."""
    by_route = {}
    for r in rows:
        if r["event_type"] != "pageview":
            continue
        e = by_route.setdefault(r["route"], {"views": 0, "sessions": set(), "users": set()})
        e["views"] += 1
        if r.get("session_id"):
            e["sessions"].add(r["session_id"])
        if r.get("user_id"):
            e["users"].add(r["user_id"])
    out = [{"route": route, "views": e["views"], "sessions": len(e["sessions"]),
            "users": len(e["users"])} for route, e in by_route.items()]
    out.sort(key=lambda x: (-x["views"], x["route"]))
    return out[:limit]


def nav_flows(rows, limit=15):
    """Navigation flows from consecutive pageviews (meta.from -> route)."""
    counts = {}
    for r in rows:
        if r["event_type"] != "pageview":
            continue
        frm = (r.get("meta") or {}).get("from")
        if not frm or frm == r["route"]:
            continue
        key = (frm, r["route"])
        counts[key] = counts.get(key, 0) + 1
    out = [{"from": f, "to": t, "count": c} for (f, t), c in counts.items()]
    out.sort(key=lambda x: -x["count"])
    return out[:limit]


def empty_search_terms(rows, limit=15):
    """Search/filter terms that returned nothing, by frequency."""
    counts = {}
    for r in rows:
        if r["event_type"] != "search_empty":
            continue
        term = (r.get("meta") or {}).get("term")
        if not term:
            continue
        e = counts.setdefault(term, {"count": 0, "routes": set()})
        e["count"] += 1
        e["routes"].add(r["route"])
    out = [{"term": t, "count": e["count"], "routes": sorted(e["routes"])}
           for t, e in counts.items()]
    out.sort(key=lambda x: (-x["count"], x["term"]))
    return out[:limit]


# ── client_error location (script + line + top stack frames) ─────────────────
# Without these every error arrived as a bare "Error" nobody could act on. A
# location is code, not personal data, but it is still re-validated here: a
# same-origin script is kept as its masked path, anything else as
# "external:<host>" only (no third-party URL, query or fragment ever kept), and
# a frame must match the one shape the capture script builds or it is dropped.

_EXTERNAL_RE = re.compile(r"^external:[A-Za-z0-9.-]{1,120}(:\d{1,5})?$")
_FRAME_RE = re.compile(
    r"^([A-Za-z0-9_$.<>\[\] -]{1,80}) "
    r"((?:/[A-Za-z0-9_./{}~-]{0,200})|external:[A-Za-z0-9.-]{1,120}(?::\d{1,5})?):"
    r"(\d{1,7}):(\d{1,7})$")
MAX_FRAMES = 3


def clean_error_source(src):
    """A script location: a same-origin path (masked like a route, query
    dropped) or "external:<host>". Anything else -> None."""
    if not isinstance(src, str):
        return None
    src = src.strip()[:300]
    if _EXTERNAL_RE.match(src):
        return src
    if src.startswith("/"):
        return mask_route(src)
    return None


def clean_error_frames(frames):
    """Up to MAX_FRAMES "fn /path:line:col" strings, each re-validated against
    the exact shape telemetry.js emits; a frame that doesn't match is dropped."""
    if not isinstance(frames, list):
        return None
    out = []
    for f in frames[:MAX_FRAMES]:
        if not isinstance(f, str):
            continue
        m = _FRAME_RE.match(f.strip())
        if not m:
            continue
        fn, where, line, col = m.groups()
        where = where if where.startswith("external:") else mask_route(where)
        out.append(f"{fn} {where}:{line}:{col}")
    return out or None


def clean_line_number(v):
    if isinstance(v, bool) or not isinstance(v, int):
        return None
    return v if 0 < v <= 10_000_000 else None


def error_location(meta):
    """"<source>:<line>:<col>" (or as much as is known), or None."""
    meta = meta or {}
    src = meta.get("source")
    if not src:
        return None
    loc = src
    if meta.get("line"):
        loc += f":{meta['line']}"
        if meta.get("col"):
            loc += f":{meta['col']}"
    return loc


def errors_by_route(rows, limit=15):
    """Client errors grouped by route + error name + message + location, so two
    different bugs on one screen stay two rows. Carries the first stack frames
    seen for each group."""
    groups = {}
    for r in rows:
        if r["event_type"] != "client_error":
            continue
        meta = r.get("meta") or {}
        name = meta.get("name") or "Error"
        message = meta.get("message")
        location = error_location(meta)
        if not location and meta.get("frames"):
            # an unhandled rejection has no filename/lineno — its top frame is
            # the best location there is
            location = meta["frames"][0].split(" ", 1)[-1]
        key = (r["route"], name, message, location)
        g = groups.get(key)
        if not g:
            g = groups[key] = {"route": r["route"], "name": name, "message": message,
                               "location": location, "frames": meta.get("frames"),
                               "count": 0}
        g["count"] += 1
        if not g["frames"] and meta.get("frames"):
            g["frames"] = meta["frames"]
    out = sorted(groups.values(), key=lambda x: -x["count"])
    return out[:limit]


# ── Outcomes, search, speed, device, role, version (v3.26) ──────────────────

def _median(vals):
    vals = sorted(vals)
    if not vals:
        return None
    mid = len(vals) // 2
    return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) // 2


def _pct(vals, q):
    vals = sorted(vals)
    if not vals:
        return None
    return vals[min(len(vals) - 1, int(round(q * (len(vals) - 1))))]


def task_outcomes(rows, limit=15):
    """Per screen: forms submitted vs left with edits, pages that came back
    showing an error message, and the HTTP errors people hit (by status).
    Sorted by how much went wrong."""
    by = {}
    for r in rows:
        et = r["event_type"]
        if et not in ("form_submit", "form_abandon", "form_error", "http_error"):
            continue
        e = by.setdefault(r["route"], {"route": r["route"], "submits": 0, "abandons": 0,
                                       "form_errors": 0, "http_errors": {}})
        if et == "form_submit":
            e["submits"] += 1
        elif et == "form_abandon":
            e["abandons"] += 1
        elif et == "form_error":
            e["form_errors"] += 1
        else:
            status = str((r.get("meta") or {}).get("status") or "?")
            e["http_errors"][status] = e["http_errors"].get(status, 0) + 1
    out = []
    for e in by.values():
        started = e["submits"] + e["abandons"]
        e["abandon_rate"] = round(100 * e["abandons"] / started) if started else None
        e["http_error_total"] = sum(e["http_errors"].values())
        out.append(e)
    out.sort(key=lambda e: (-(e["abandons"] + e["form_errors"] + e["http_error_total"]),
                            e["route"]))
    return out[:limit]


def search_stats(rows, limit=10):
    """Every search (search events) against the empty ones, overall and per
    screen. Rows recorded before v3.26 only have search_empty, so a screen's
    total is never shown below its empty count."""
    by = {}
    for r in rows:
        if r["event_type"] not in ("search", "search_empty"):
            continue
        e = by.setdefault(r["route"], {"route": r["route"], "searches": 0, "empty": 0})
        if r["event_type"] == "search":
            e["searches"] += 1
        else:
            e["empty"] += 1
    for e in by.values():
        e["searches"] = max(e["searches"], e["empty"])
        e["empty_rate"] = round(100 * e["empty"] / e["searches"]) if e["searches"] else None
    per_route = sorted(by.values(), key=lambda e: (-e["searches"], e["route"]))[:limit]
    total = sum(e["searches"] for e in by.values())
    empty = sum(e["empty"] for e in by.values())
    return {"total": total, "empty": empty,
            "empty_rate": round(100 * empty / total) if total else None,
            "by_route": per_route}


def search_sections(rows):
    """{section: results shown} added up over every search that reported its sections."""
    out = {}
    for r in rows:
        if r["event_type"] != "search":
            continue
        for name, n in ((r.get("meta") or {}).get("sections") or {}).items():
            if name in SEARCH_SECTIONS and isinstance(n, int):
                out[name] = out.get(name, 0) + n
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))


def ask_stats(rows):
    """How the assistant is used: asks fired, how many got an answer (and of what kind), how many
    fell back to plain search results, and where. Rows before v6.10 have none."""
    fired = answered = fallback = 0
    kinds, by_route = {}, {}
    for r in rows:
        if r["event_type"] != "ask":
            continue
        m = r.get("meta") or {}
        e = by_route.setdefault(r["route"], {"route": r["route"], "fired": 0, "answered": 0, "fallback": 0})
        stage = m.get("stage")
        if stage == "fired":
            fired += 1
            e["fired"] += 1
        elif stage == "answered":
            answered += 1
            e["answered"] += 1
            if m.get("kind") in ASK_KINDS:
                kinds[m["kind"]] = kinds.get(m["kind"], 0) + 1
        elif stage == "fallback":
            fallback += 1
            e["fallback"] += 1
    return {"fired": fired, "answered": answered, "fallback": fallback, "kinds": kinds,
            "answer_rate": round(100 * answered / fired) if fired else None,
            "by_route": sorted(by_route.values(), key=lambda e: (-e["fired"], e["route"]))}


def page_speed(rows, limit=12, min_samples=3):
    """Median and 90th-percentile page load (and time to first byte) per
    screen, slowest first. Screens with fewer than `min_samples` loads are
    left out — one slow load is an anecdote."""
    by = {}
    for r in rows:
        if r["event_type"] != "page_timing":
            continue
        m = r.get("meta") or {}
        if not isinstance(m.get("load_ms"), int):
            continue
        e = by.setdefault(r["route"], {"load": [], "ttfb": []})
        e["load"].append(m["load_ms"])
        if isinstance(m.get("ttfb_ms"), int):
            e["ttfb"].append(m["ttfb_ms"])
    out = [{"route": route, "samples": len(e["load"]),
            "load_median_ms": _median(e["load"]), "load_p90_ms": _pct(e["load"], 0.9),
            "ttfb_median_ms": _median(e["ttfb"])}
           for route, e in by.items() if len(e["load"]) >= min_samples]
    out.sort(key=lambda x: (-x["load_p90_ms"], x["route"]))
    return out[:limit]


def device_mix(rows):
    """Pageviews by viewport class (phone / tablet / desktop), overall."""
    counts = {v: 0 for v in VIEWPORTS}
    unknown = 0
    for r in rows:
        if r["event_type"] != "pageview":
            continue
        vp = (r.get("meta") or {}).get("vp")
        if vp in counts:
            counts[vp] += 1
        else:
            unknown += 1
    return {"counts": counts, "unknown": unknown}


def screens_by_role(rows, limit=15):
    """Pageviews per screen split by the viewer's role — so low traffic on a
    screen only some roles can open reads against the people who could."""
    by, roles = {}, set()
    for r in rows:
        if r["event_type"] != "pageview":
            continue
        role = r.get("role") or "unknown"
        roles.add(role)
        e = by.setdefault(r["route"], {"route": r["route"], "total": 0, "by_role": {}})
        e["total"] += 1
        e["by_role"][role] = e["by_role"].get(role, 0) + 1
    out = sorted(by.values(), key=lambda e: (-e["total"], e["route"]))[:limit]
    return {"roles": sorted(roles), "rows": out}


def events_by_version(rows):
    """Events per app version (stamped by the server at ingest), oldest
    version first — lines a spike up with the deploy that caused it. Rows
    recorded before v3.26 carry no version."""
    by = {}
    for r in rows:
        v = (r.get("meta") or {}).get("v") or "(before v3.26)"
        e = by.setdefault(v, {"version": v, "events": 0, "client_errors": 0,
                              "http_errors": 0, "first": r.get("created_at"),
                              "last": r.get("created_at")})
        e["events"] += 1
        if r["event_type"] == "client_error":
            e["client_errors"] += 1
        elif r["event_type"] == "http_error":
            e["http_errors"] += 1
        at = r.get("created_at")
        if at and (not e["first"] or at < e["first"]):
            e["first"] = at
        if at and (not e["last"] or at > e["last"]):
            e["last"] = at
    return sorted(by.values(), key=lambda e: (e["first"] or ""))


def exit_routes(rows, limit=10):
    """Where sessions end — the last pageview of each session is an 'exit' for
    that route. created_at is a naive local ISO string throughout this app
    (tz.now_iso()), so plain string comparison already sorts chronologically."""
    last_by_session = {}
    for r in rows:
        if r["event_type"] != "pageview" or not r.get("session_id"):
            continue
        sid = r["session_id"]
        at = r["created_at"]
        cur = last_by_session.get(sid)
        if not cur or at >= cur["at"]:
            last_by_session[sid] = {"route": r["route"], "at": at}
    counts = {}
    for v in last_by_session.values():
        counts[v["route"]] = counts.get(v["route"], 0) + 1
    out = [{"route": route, "exits": n} for route, n in counts.items()]
    out.sort(key=lambda x: (-x["exits"], x["route"]))
    return out[:limit]


# ── Friction (the ranked-opportunity core) ──────────────────────────────────

# Selectors that are never a broken control — the page background (clicking
# empty space to deselect/dismiss) and the app's drawing surfaces (every stroke
# on the /me signature pad is a "click" on a non-interactive element). The
# capture script stops sending these (static/js/telemetry.js NON_ACTIONABLE /
# isBackground); filtering here too keeps rows recorded before that fix, still
# inside the retention window, from topping the board.
NON_ACTIONABLE_SELECTORS = {
    "html", "body", "html > body", "main", "#maincontent",
    "#sigCanvas", "#cropCanvas", "#confetti",
}

# Tags that are real controls. A rage-click whose selector ENDS in one of these
# (e.g. "… > span > button:nth-of-type(1)", the companion's Feed button) landed
# on something that does respond — the pre-meta.interactive fallback.
_INTERACTIVE_TAGS = {"a", "button", "input", "select", "textarea", "label", "summary", "option"}


def _last_selector_tag(selector):
    last = re.split(r"\s*>\s*|\s+", selector.strip())[-1]
    return re.match(r"[a-z0-9]*", last).group(0)


def is_non_actionable(selector):
    return bool(selector) and selector.strip() in NON_ACTIONABLE_SELECTORS


def is_interactive_rage(row):
    """A rage-click burst on a real control — play (feeding the companion) or
    impatience with a slow/silent control, not an affordance that does nothing.
    New rows carry meta.interactive from the capture script; older ones are
    recognised by the selector's last tag."""
    if (row.get("meta") or {}).get("interactive"):
        return True
    sel = row.get("element_selector")
    return bool(sel) and _last_selector_tag(sel) in _INTERACTIVE_TAGS


def friction_by_target(rows):
    """Group dead + rage clicks by route + component (source anchor). Rage
    bursts on a real control are counted apart, as rapid_taps."""
    by_key = {}
    for r in rows:
        if r["event_type"] not in ("dead_click", "rage_click"):
            continue
        if is_non_actionable(r.get("element_selector")):
            continue
        component = r.get("component")
        selector = r.get("element_selector")
        key = (r["route"], component or selector or "?")
        t = by_key.get(key)
        if not t:
            t = {"route": r["route"], "component": component,
                 "element_text": r.get("element_text"), "selector": selector,
                 "dead_clicks": 0, "rage_clicks": 0, "rapid_taps": 0,
                 "_sessions": set(), "_users": set()}
            by_key[key] = t
        if r["event_type"] == "rage_click":
            if is_interactive_rage(r):
                t["rapid_taps"] += 1
            else:
                t["rage_clicks"] += 1
        else:
            t["dead_clicks"] += 1
        if r.get("session_id"):
            t["_sessions"].add(r["session_id"])
        if r.get("user_id"):
            t["_users"].add(r["user_id"])
        if not t["element_text"] and r.get("element_text"):
            t["element_text"] = r["element_text"]
    out = []
    for t in by_key.values():
        sessions, users = t.pop("_sessions"), t.pop("_users")
        t["sessions"], t["users"] = len(sessions), len(users)
        out.append(t)
    return out


def friction_score(target):
    """Rank a friction target. Rage clicks weigh more than dead clicks (stronger
    frustration), and the whole thing is DAMPED by distinct users so one
    frustrated person can't top the board alone. Rapid taps on a real control
    weigh like a dead click — worth a look (does it give visible feedback?) but
    not the ×3 of a burst on something that does nothing. Deterministic,
    unit-tested."""
    base = (target["rage_clicks"] * 3 + target["dead_clicks"]
            + target.get("rapid_taps", 0))
    users = target["users"]
    weight = 1 if users >= 3 else (0.8 if users == 2 else 0.6)
    return round(base * weight, 2)


FEEDBACK_BOOST = 1.5   # a hotspot with a matching complaint jumps the queue.

# Mirrors storage.SPOT_RESOLVED_STATUSES (kept literal: this module stays DB-free).
RESOLVED_FEEDBACK_STATUSES = {"Done", "Won't fix"}


def _is_open(f):
    return f.get("status") not in RESOLVED_FEEDBACK_STATUSES


def correlate_feedback(targets, feedback):
    """Attach explicit spot-feedback to friction targets. A hotspot people ALSO
    complained about is the strongest 'fix this' signal. Match on masked route
    (feedback page_url -> mask_route) + exact selector; fall back to a
    route-only match so a complaint on the same screen still associates — but
    only an OPEN one: a months-old, already-Done comment about something else
    on the same screen says nothing about this element (the /wellness Feed
    button was carrying 12 unrelated, mostly resolved comments). An exact
    element match is kept whatever its status (a Done complaint on an element
    still drawing clicks means the fix didn't land). Only open feedback earns
    the boost — see build_digest. `feedback` rows come from
    storage.list_spot_feedback (page_url, element_selector, message, status,
    created_at)."""
    prepared = [{"route": mask_route(f["page_url"]), "selector": f.get("element_selector"),
                 "message": f["message"], "status": f.get("status"),
                 "created_at": f["created_at"]} for f in feedback]
    out = []
    for t in targets:
        exact = [f for f in prepared
                 if f["route"] == t["route"] and t.get("selector") and f["selector"] == t["selector"]]
        matched = exact if exact else [f for f in prepared
                                       if f["route"] == t["route"] and _is_open(f)]
        out.append({**t, "feedback": [{"message": f["message"], "status": f["status"],
                                       "created_at": f["created_at"],
                                       "exact": bool(exact)} for f in matched]})
    return out


# ── The digest — the human-facing deliverable ───────────────────────────────

def _hint_for(o):
    """One deterministic, human-orienting cause line per opportunity (no LLM in
    the loop)."""
    parts = []
    sig = o["signals"]
    if sig["rage_clicks"] > 0:
        parts.append("Users rage-click this element — it looks interactive but does "
                     "nothing. Make it actionable, or remove the affordance.")
    elif sig["dead_clicks"] > 0:
        parts.append("Users click here expecting an action; the element is inert.")
    elif sig.get("rapid_taps", 0) > 0:
        parts.append("Users tap this control repeatedly in quick succession — it "
                     "works, so check it answers instantly and visibly (a slow or "
                     "silent response reads as broken), or it may just be play.")
    if sig["client_errors"] > 0:
        parts.append("This screen also throws client-side errors.")
    open_fb = [f for f in o["feedback"] if _is_open(f)]
    if open_fb:
        parts.append(f"{len(open_fb)} open spot-feedback comment(s) — "
                     "someone already reported this.")
    elif o["feedback"]:
        parts.append(f"{len(o['feedback'])} resolved spot-feedback comment(s) on this "
                     "exact element — the fix may not have landed.")
    return " ".join(parts) or "Recurring friction on this element."


def build_digest(rows, feedback, *, window_days=None, now=None, limit=15):
    """Build the ranked improvement digest. `rows` (ui_event) and `feedback`
    (spot_feedback) are expected to already be scoped to the window by the
    caller (SQL/storage filtering) — window_days/now only annotate `window`."""
    sessions, users = set(), set()
    for r in rows:
        if r.get("session_id"):
            sessions.add(r["session_id"])
        if r.get("user_id"):
            users.add(r["user_id"])

    empty_by_route, error_by_route = {}, {}
    for r in rows:
        if r["event_type"] == "search_empty":
            empty_by_route[r["route"]] = empty_by_route.get(r["route"], 0) + 1
        elif r["event_type"] == "client_error":
            error_by_route[r["route"]] = error_by_route.get(r["route"], 0) + 1

    with_feedback = correlate_feedback(friction_by_target(rows), feedback)
    scored = []
    for t in with_feedback:
        base = friction_score(t)
        boosted = any(_is_open(f) for f in t["feedback"])
        score = round(base * (FEEDBACK_BOOST if boosted else 1), 2)
        partial = {
            "route": t["route"], "component": t["component"],
            "element_text": t["element_text"], "selector": t["selector"], "score": score,
            "signals": {
                "rage_clicks": t["rage_clicks"], "dead_clicks": t["dead_clicks"],
                "rapid_taps": t["rapid_taps"],
                "empty_searches": empty_by_route.get(t["route"], 0),
                "client_errors": error_by_route.get(t["route"], 0),
                "sessions": t["sessions"], "users": t["users"],
            },
            "feedback": t["feedback"],
        }
        partial["hint"] = _hint_for(partial)
        scored.append(partial)
    scored.sort(key=lambda o: (-o["score"], -o["signals"]["rage_clicks"]))
    scored = scored[:limit]
    for i, o in enumerate(scored):
        o["rank"] = i + 1

    times = sorted(r["created_at"] for r in rows if r.get("created_at"))
    return {
        "window": {"days": window_days, "from": times[0] if times else None,
                   "to": now or (times[-1] if times else None)},
        "totals": {"sessions": len(sessions), "users": len(users), "events": len(rows)},
        "opportunities": scored,
        "dead_ends": exit_routes(rows),
        "top_screens": top_routes(rows),
        "failed_searches": empty_search_terms(rows),
        "errors": errors_by_route(rows),
        "outcomes": task_outcomes(rows),
        "search": search_stats(rows),
        "search_sections": search_sections(rows),
        "ask": ask_stats(rows),
        "speed": page_speed(rows),
        "devices": device_mix(rows),
    }
