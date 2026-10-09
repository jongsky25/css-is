"""
Office Connect UX telemetry handoff — a downloadable, self-describing analysis brief.
=============================================================================

The presentation layer over ui_telemetry.py's digest: GET /admin/ux-insights/
handoff (app.py) calls build_handoff() and ships the result as one Markdown (or
JSON) file an admin can hand to an AI assistant — the file itself carries the
domain context, the event vocabulary, the sanitization semantics, and the
analysis brief, so no extra explanation is needed alongside it. There is
deliberately NO LLM call in-app; the handoff is a static artifact.

Privacy: the export is strictly MORE private than what's stored. Rows arrive
already masked (see ui_telemetry sanitizers + the /telemetry re-sanitize pass);
this module additionally drops user_id/id and replaces session_id with
per-export pseudonyms (s1, s2, …) before anything leaves the server.

Everything here is PURE (no DB, no FastAPI import) so it's cheap to unit test —
same contract as ui_telemetry.py. The route passes in everything environmental
(rows, digest, nav destinations, app routes, version, timestamps).
"""
from __future__ import annotations

import json
import re

import ui_telemetry as ui_tel

# Below this many pageviews (in the window) a nav destination counts as
# "rarely used" in the feature-usage section. Deliberately a small constant —
# the full ranked table ships alongside, so the threshold only labels, never
# hides.
RARELY_USED_MAX_VIEWS = 3

# Raw-event appendix cap — enough to reason over, small enough to paste.
SAMPLE_CAP = 200

APP_CONTEXT_MD = """\
Office Connect is the BLHSD (Bureau of Local Health Systems Development, Philippine
Department of Health) office platform. Its Customer Satisfaction Survey module lets staff
create survey activities, respondents scan QR codes to rate services
(CSM/SERVQUAL), and staff monitor responses, manage rosters and directories,
and generate official reports. The app is server-rendered (FastAPI + Jinja2,
full page loads, no client router); staff sign in with role-based capabilities
(viewer / encoder / section_manager / admin), so some screens are only visible
to some roles. This telemetry covers the signed-in staff dashboard only — the
public respondent survey pages are NOT instrumented. The system is subject to
the Philippine Data Privacy Act, which is why everything below is aggressively
masked (see "Sanitization semantics")."""

TASK_MD = """\
You are looking at real usage telemetry from the staff dashboard described
above. Using only this file:

1. Rank the interface problems by user impact and say, for each, what a
   concrete fix would look like (the pre-computed scores are a starting
   point — override them where the evidence justifies it).
2. Read the feature-usage coverage (section below) and recommend how the
   interface could be reorganized around what staff actually use — what
   deserves more prominence, and which rarely/never-used screens should be
   consolidated, demoted, or rethought. Mind the role caveat: a screen gated
   to admins can never be visited by most users, so low traffic there is not
   by itself evidence of a problem.
3. Flag route-level patterns (a screen that combines exits + errors + failed
   searches is worth more attention than any single signal).
4. Say what instrumentation is missing — questions this data cannot answer
   but should.

To locate anything in code: handlers live in app.py (the route → handler map
below gives the function names), `component` values are `data-tour` region
anchors in the Jinja templates, and `element_selector` is a capped CSS path."""


def events_per_day(rows):
    """Daily event counts, one column per event type + total, ascending by day.
    created_at is a naive local ISO string (tz.now_iso()), so the date is a
    plain prefix slice."""
    by_day = {}
    for r in rows:
        at = r.get("created_at") or ""
        if len(at) < 10:
            continue
        day = at[:10]
        e = by_day.setdefault(day, {"day": day, "total": 0})
        e[r["event_type"]] = e.get(r["event_type"], 0) + 1
        e["total"] += 1
    return sorted(by_day.values(), key=lambda d: d["day"])


def event_type_counts(rows):
    """Total events per type, every vocabulary type present (0 for silent ones —
    an analyst should see 'form_abandon: 0' and know the detector exists)."""
    out = {t: 0 for t in sorted(ui_tel.UI_EVENT_TYPES | ui_tel.SERVER_EVENT_TYPES)}
    for r in rows:
        if r["event_type"] in out:
            out[r["event_type"]] += 1
    return out


def pseudonymize_events(rows, sample_cap=SAMPLE_CAP):
    """The raw-event appendix: drop id/user_id entirely, replace session_id with
    stable per-call pseudonyms (s1, s2, … in order of first appearance), keep
    the already-masked behavioral fields. `rows` come newest-first from
    storage.list_ui_events — the cap keeps the most recent."""
    session_alias = {}
    out = []
    for r in rows[:sample_cap]:
        sid = r.get("session_id")
        if sid and sid not in session_alias:
            session_alias[sid] = f"s{len(session_alias) + 1}"
        out.append({
            "at": r.get("created_at"),
            "session": session_alias.get(sid),
            "role": r.get("role"),
            "event_type": r["event_type"],
            "route": r["route"],
            "component": r.get("component"),
            "element_selector": r.get("element_selector"),
            "element_text": r.get("element_text"),
            "meta": r.get("meta"),
        })
    return out


_MASK_SEGMENTS = {"{id}", "{token}", "{date}"}


def map_routes_to_handlers(masked_routes, app_routes):
    """Map masked telemetry routes (e.g. /directory/person/{id}/edit) to app
    handler function names, so an analyst can grep app.py directly.
    `app_routes` is a list of (path, name) tuples (route objects' .path/.name,
    passed in so this module stays pure). A masked route matches an app path
    when segment counts agree, literal segments are equal, and any app {param}
    segment lines up with a masked {id}/{token}/{date} placeholder (or an exact
    literal — a real path like /r/{qr_token} never reaches telemetry unmasked,
    but static routes match themselves)."""
    def segs(p):
        return [s for s in str(p).split("/") if s]

    def matches(masked_s, app_s):
        if len(masked_s) != len(app_s):
            return False
        for m, a in zip(masked_s, app_s):
            if a.startswith("{") and a.endswith("}"):
                continue                     # app param swallows any mask/literal
            if m in _MASK_SEGMENTS:
                return False                 # masked placeholder vs app literal
            if m != a:
                return False
        return True

    prepared = [(segs(path), name) for path, name in app_routes if name]
    out = {}
    for route in masked_routes:
        ms = segs(route)
        for app_s, name in prepared:
            if matches(ms, app_s):
                out[route] = name
                break
    return out


def feature_usage(rows, nav_destinations, rarely_max=RARELY_USED_MAX_VIEWS):
    """Usage coverage of the app's nav destinations — the 'redesign around what
    people actually use' section. `nav_destinations` is a list of (route, label,
    group) tuples built from app.py's NAV_GROUPS (passed in to stay pure).

    Returns ranked most-used, rarely-used (1..rarely_max views), NEVER-used
    (zero views in the window), plus non-nav routes seen in telemetry (deep
    links like /activity/{id} that aren't nav destinations themselves)."""
    views = {}
    for r in rows:
        if r["event_type"] != "pageview":
            continue
        e = views.setdefault(r["route"], {"views": 0, "sessions": set(), "users": set()})
        e["views"] += 1
        if r.get("session_id"):
            e["sessions"].add(r["session_id"])
        if r.get("user_id"):
            e["users"].add(r["user_id"])

    # Destinations that differ only by query string (e.g. the report types all
    # living under /reports?...) collapse to one masked route — merge them into
    # ONE row so the same pageviews are never claimed once per label.
    by_masked = {}
    for route, label, group in nav_destinations:
        masked = ui_tel.mask_route(route)
        e = by_masked.setdefault(masked, {"labels": [], "groups": []})
        if label not in e["labels"]:
            e["labels"].append(label)
        if group not in e["groups"]:
            e["groups"].append(group)
    nav_routes = set(by_masked)
    ranked = []
    for masked, nav in by_masked.items():
        e = views.get(masked)
        ranked.append({
            "route": masked, "label": " / ".join(nav["labels"]),
            "group": " / ".join(nav["groups"]),
            "views": e["views"] if e else 0,
            "sessions": len(e["sessions"]) if e else 0,
            "users": len(e["users"]) if e else 0,
        })
    ranked.sort(key=lambda x: (-x["views"], x["label"]))

    other = [{"route": route, "views": e["views"], "sessions": len(e["sessions"]),
              "users": len(e["users"])}
             for route, e in views.items() if route not in nav_routes]
    other.sort(key=lambda x: (-x["views"], x["route"]))

    return {
        "ranked": ranked,
        "rarely_used": [d for d in ranked if 0 < d["views"] <= rarely_max],
        "never_used": [d for d in ranked if d["views"] == 0],
        "other_routes": other,
        "rarely_max_views": rarely_max,
    }


def _resanitize(rows):
    """Defense-in-depth at the EXPORT boundary, mirroring the ingest pass in
    app.py's telemetry_ingest: rows are supposed to arrive sanitized from
    storage, but this file leaves the system — re-mask rather than trust any
    single earlier layer. Idempotent over already-clean rows (see
    ui_telemetry.mask_route's docstring)."""
    out = []
    for r in rows:
        meta = r.get("meta")
        if isinstance(meta, dict):
            m = dict(meta)
            if isinstance(m.get("from"), str):
                m["from"] = ui_tel.mask_route(m["from"])
            if isinstance(m.get("term"), str):
                m["term"] = ui_tel.sanitize_text(m["term"], max_len=80)
            if isinstance(m.get("message"), str):
                m["message"] = ui_tel.sanitize_text(m["message"], max_len=80)
            if "source" in m:
                m["source"] = ui_tel.clean_error_source(m["source"])
            if "frames" in m:
                m["frames"] = ui_tel.clean_error_frames(m["frames"])
            for k in ("line", "col"):
                if k in m:
                    m[k] = ui_tel.clean_line_number(m[k])
            meta = {k: v for k, v in m.items() if v is not None}
            meta = meta or None
        out.append({**r,
                    "route": ui_tel.mask_route(r.get("route")),
                    "element_selector": ui_tel.sanitize_selector(r.get("element_selector")),
                    "element_text": ui_tel.sanitize_text(r.get("element_text"), max_len=300),
                    "meta": meta})
    return out


def build_handoff(rows, feedback, *, window_days, now, app_version, generated_at,
                  retention_days, truncated, nav_destinations, app_routes=None,
                  include_sample=True):
    """Assemble the full JSON-serializable handoff payload: re-sanitize the
    rows (export boundary — see _resanitize), then build the same digest the
    UX Insights page shows, plus the handoff-only sections (nav flows —
    build_digest deliberately omits them — events/day, feature usage, route →
    handler map, pseudonymized sample)."""
    rows = _resanitize(rows)
    digest = ui_tel.build_digest(rows, feedback, window_days=window_days, now=now)
    usage = feature_usage(rows, nav_destinations)
    route_set = set()
    for o in digest["opportunities"]:
        route_set.add(o["route"])
    for section in (digest["top_screens"], digest["dead_ends"], digest["errors"]):
        for item in section:
            route_set.add(item["route"])
    for d in usage["ranked"]:
        if d["views"]:
            route_set.add(d["route"])
    route_handlers = (map_routes_to_handlers(sorted(route_set), app_routes)
                      if app_routes else {})
    return {
        "generated_at": generated_at,
        "app_version": app_version,
        "window": digest["window"],
        "retention_days": retention_days,
        "truncated": truncated,
        "totals": digest["totals"],
        "event_type_counts": event_type_counts(rows),
        "opportunities": digest["opportunities"],
        "top_screens": digest["top_screens"],
        "nav_flows": ui_tel.nav_flows(rows),
        "dead_ends": digest["dead_ends"],
        "events_per_day": events_per_day(rows),
        "feature_usage": usage,
        "route_handlers": route_handlers,
        "failed_searches": digest["failed_searches"],
        "errors": digest["errors"],
        "outcomes": digest["outcomes"],
        "search": digest["search"],
        "speed": digest["speed"],
        "devices": digest["devices"],
        "screens_by_role": ui_tel.screens_by_role(rows),
        "versions": ui_tel.events_by_version(rows),
        "sample_events": pseudonymize_events(rows) if include_sample else [],
    }


# ── Markdown rendering ───────────────────────────────────────────────────────

def _cell(v):
    """One Markdown table cell: escape pipes (element_text may contain them),
    keep newlines out, dash for empty."""
    if v is None or v == "":
        return "—"
    return re.sub(r"\s+", " ", str(v)).replace("|", "\\|")


def _matched_feedback_lines(opportunities):
    """Each matched Spot Feedback comment ONCE, with the opportunity ranks it
    matched. Several opportunities on one route share its route-level comments,
    so listing them per opportunity repeated the same comment 3-4 times."""
    seen = {}
    for o in opportunities:
        for f in o["feedback"]:
            key = (o["route"], f["created_at"], f["message"])
            seen.setdefault(key, {"f": f, "ranks": []})["ranks"].append(o["rank"])
    lines = []
    for (route, _, _), v in sorted(seen.items(), key=lambda kv: (kv[0][0], kv[0][1])):
        f = v["f"]
        ranks = ", ".join(f"#{r}" for r in v["ranks"])
        lines.append(f"- {route} ({f['created_at']}, status {_cell(f['status'])}"
                     f"{', this element' if f.get('exact') else ''}; matches {ranks}): "
                     f"“{_cell(f['message'])}”")
    return lines


def _table(headers, rows_of_cells):
    lines = ["| " + " | ".join(headers) + " |",
             "| " + " | ".join("---" for _ in headers) + " |"]
    for cells in rows_of_cells:
        lines.append("| " + " | ".join(_cell(c) for c in cells) + " |")
    return "\n".join(lines)


def render_handoff_markdown(payload):
    """The Markdown artifact. Deterministic: same payload, same bytes."""
    p = payload
    w = p["window"]
    out = []
    add = out.append

    add("# Office Connect UX Telemetry Handoff — for AI-assisted interface review\n")
    add(f"Generated {p['generated_at']} · app version {p['app_version']} · "
        f"window: last {w['days']} day(s) ({w['from'] or '—'} → {w['to'] or '—'}) · "
        f"{p['totals']['events']} event(s) from {p['totals']['sessions']} session(s) / "
        f"{p['totals']['users']} signed-in user(s) · retention {p['retention_days']} day(s).")
    if p["truncated"]:
        add("\n> **Note:** the window holds more events than one read returns — "
            "everything below is computed from the most recent "
            f"{p['totals']['events']} events, not literally every event in the window.")

    add("\n## 1. What this app is\n")
    add(APP_CONTEXT_MD)

    add("\n## 2. How to read this data\n")
    add("### Event vocabulary\n")
    add(_table(
        ["event_type", "meaning", "captured in window"],
        [["pageview", "One full page load; meta.from is the same-origin referring "
                      "route, enabling the nav-flow and exit analysis", p["event_type_counts"]["pageview"]],
         ["dead_click", "A click on something non-interactive — the user expected "
                        "an action and nothing happened", p["event_type_counts"]["dead_click"]],
         ["rage_click", "≥3 clicks within 800 ms / 24 px — frustration on one spot. "
                        "When the burst lands on a real control (a button, link, "
                        "input) it is counted as a rapid tap instead — usually play "
                        "or impatience with slow feedback, not a dead affordance",
          p["event_type_counts"]["rage_click"]],
         ["search_empty", "A search/filter that returned zero results; meta.term "
                          "is the (sanitized) term", p["event_type_counts"]["search_empty"]],
         ["client_error", "An uncaught JS error or unhandled promise rejection; "
                          "meta has name + sanitized message", p["event_type_counts"]["client_error"]],
         ["form_abandon", "A form left with unsaved edits when the page was left; "
                          "meta.fields is how many fields were touched (never their "
                          "contents)", p["event_type_counts"]["form_abandon"]],
         ["form_submit", "A form submitted (the other half of form_abandon — "
                         "together they give an abandon rate)",
          p["event_type_counts"]["form_submit"]],
         ["form_error", "A page that came back showing an error banner — a "
                        "submitted task that didn't go through; meta.from is the "
                        "screen it came from (the message is never recorded)",
          p["event_type_counts"]["form_error"]],
         ["http_error", "Recorded by the SERVER: a 403 / 404 / 5xx a signed-in "
                        "person hit; meta.status", p["event_type_counts"]["http_error"]],
         ["search", "Every completed search, with meta.hits = how many results "
                    "(no term; the empty ones are also search_empty, with theirs)",
          p["event_type_counts"]["search"]],
         ["page_timing", "How long a page took: meta.ttfb_ms / dom_ms / load_ms "
                         "from the browser's navigation timing",
          p["event_type_counts"]["page_timing"]]]))
    add("\nSince v3.26 every event also carries `meta.v`, the app version that "
        "received it, and every pageview `meta.vp` (phone / tablet / desktop). "
        "Events recorded earlier have neither, and the new event types start "
        "from that release — early windows will read low on them.")
    add("\n### Sanitization semantics\n")
    add("- Routes are patterns, never concrete URLs: numeric ids → `{id}`, hex "
        "tokens → `{token}`, date segments → `{date}`; query strings and "
        "fragments are dropped.\n"
        "- Any run of 3+ digits in visible text is masked to `###`; text is "
        "whitespace-collapsed and length-capped.\n"
        "- User ids are removed from this export entirely; `session` values are "
        "per-export pseudonyms (s1, s2, …) with no meaning outside this file. "
        "`role` is kept because capability gating shapes which screens a user "
        "can even visit.\n"
        "- Nothing a respondent or staff member typed into a form is ever "
        "captured — only which screen and which element.")
    add("\n### Scoring\n")
    add("Friction score = rage_clicks × 3 + dead_clicks + rapid_taps, damped by "
        "distinct users (≥3 users ×1, 2 users ×0.8, 1 user ×0.6), then ×1.5 if an "
        "OPEN Spot Feedback comment (a typed, explicit complaint) matches the same "
        "element, or the same route when no comment names the element. Resolved "
        "comments only count on an exact element match, and never boost. Clicks on "
        "the page background, on drawing canvases, and ones that end a text "
        "selection are not recorded as friction at all.")

    add("\n## 3. Your task\n")
    add(TASK_MD)

    add("\n## 4. Ranked friction opportunities\n")
    if p["opportunities"]:
        add(_table(
            ["#", "route", "component", "selector", "element text", "score",
             "rage", "dead", "rapid taps", "errors", "sessions", "users", "hint"],
            [[o["rank"], o["route"], o["component"], o["selector"], o["element_text"],
              o["score"], o["signals"]["rage_clicks"], o["signals"]["dead_clicks"],
              o["signals"].get("rapid_taps", 0),
              o["signals"]["client_errors"], o["signals"]["sessions"],
              o["signals"]["users"], o["hint"]] for o in p["opportunities"]]))
        fb_lines = _matched_feedback_lines(p["opportunities"])
        if fb_lines:
            add("\n### Spot Feedback matched to these opportunities\n")
            add("\n".join(fb_lines))
    else:
        add("No repeated friction hotspots in this window.")

    add("\n## 5. Traffic & flows\n")
    add("### 5.1 Top screens (by pageviews)\n")
    add(_table(["route", "views", "sessions", "users"],
               [[s["route"], s["views"], s["sessions"], s["users"]]
                for s in p["top_screens"]]) if p["top_screens"] else "No pageviews recorded.")
    add("\n### 5.2 Navigation flows (from → to, by frequency)\n")
    add(_table(["from", "to", "count"],
               [[f["from"], f["to"], f["count"]] for f in p["nav_flows"]])
        if p["nav_flows"] else "Not enough linked pageviews yet.")
    add("\n### 5.3 Where sessions end (last screen seen)\n")
    add(_table(["route", "exits"], [[e["route"], e["exits"]] for e in p["dead_ends"]])
        if p["dead_ends"] else "Not enough sessions yet.")
    add("\n### 5.4 Events per day\n")
    day_types = sorted(ui_tel.UI_EVENT_TYPES | ui_tel.SERVER_EVENT_TYPES)
    add(_table(["day"] + day_types + ["total"],
               [[d["day"]] + [d.get(t, 0) for t in day_types] + [d["total"]]
                for d in p["events_per_day"]])
        if p["events_per_day"] else "No events recorded.")

    add("\n## 6. Feature usage & coverage\n")
    u = p["feature_usage"]
    add("Every navigation destination the app offers, ranked by pageviews in "
        "this window — the basis for 'redesign around what people actually "
        "use'. Remember the role caveat from section 3.\n")
    add(_table(["route", "screen", "nav group", "views", "sessions", "users"],
               [[d["route"], d["label"], d["group"], d["views"], d["sessions"], d["users"]]
                for d in u["ranked"]]))
    add(f"\n**Never used in this window ({len(u['never_used'])}):** "
        + (", ".join(f"{d['label']} (`{d['route']}`)" for d in u["never_used"])
           if u["never_used"] else "none — every screen was visited."))
    add(f"\n**Rarely used (≤{u['rarely_max_views']} views, {len(u['rarely_used'])}):** "
        + (", ".join(f"{d['label']} (`{d['route']}`, {d['views']})" for d in u["rarely_used"])
           if u["rarely_used"] else "none."))
    if u["other_routes"]:
        add("\n### Non-nav routes seen (deep links / sub-pages)\n")
        add(_table(["route", "views", "sessions", "users"],
                   [[d["route"], d["views"], d["sessions"], d["users"]]
                    for d in u["other_routes"]]))

    add("\n## 7. Route → handler map\n")
    if p["route_handlers"]:
        add("Handler function names in app.py, for locating each screen in code.\n")
        add(_table(["route", "handler"],
                   [[r, fn] for r, fn in sorted(p["route_handlers"].items())]))
    else:
        add("No route mapping available.")

    add("\n## 8. Failed searches\n")
    add(_table(["term", "count", "routes"],
               [[f["term"], f["count"], ", ".join(f["routes"])]
                for f in p["failed_searches"]])
        if p["failed_searches"] else "None recorded in this window.")

    add("\n## 9. Client errors\n")
    if p["errors"]:
        add("Grouped by route + error + message + location. `location` is the "
            "script path (masked like a route) or `external:<host>` for a "
            "third-party script, then line:column. A message of \"Script error.\" "
            "with no location is the browser hiding a cross-origin script's "
            "details.\n")
        add(_table(["route", "error", "message", "location", "count"],
                   [[e["route"], e["name"], e.get("message"), e.get("location"), e["count"]]
                    for e in p["errors"]]))
        traces = [e for e in p["errors"] if e.get("frames")]
        if traces:
            add("\nTop stack frames (first seen per row):\n")
            for e in traces:
                add(f"- {e['route']} — {_cell(e['name'])}: "
                    + " ← ".join(f"`{_cell(f)}`" for f in e["frames"]))
    else:
        add("None recorded in this window.")

    add("\n## 10. Task outcomes by screen\n")
    if p["outcomes"]:
        add("Forms submitted vs. left with unsaved edits (abandon rate = "
            "abandons ÷ (submits + abandons)), pages that came back showing an "
            "error banner, and HTTP errors the server returned to signed-in "
            "people. Worst first.\n")
        add(_table(["route", "submits", "abandons", "abandon %", "error banners",
                    "HTTP errors"],
                   [[o["route"], o["submits"], o["abandons"],
                     "—" if o["abandon_rate"] is None else f"{o['abandon_rate']}%",
                     o["form_errors"],
                     ", ".join(f"{k}×{v}" for k, v in sorted(o["http_errors"].items())) or "—"]
                    for o in p["outcomes"]]))
    else:
        add("None recorded in this window.")

    add("\n## 11. Search\n")
    sr = p["search"]
    if sr["total"]:
        add(f"{sr['total']} searches, {sr['empty']} with no results "
            f"({sr['empty_rate']}% empty).\n")
        add(_table(["route", "searches", "empty", "empty %"],
                   [[e["route"], e["searches"], e["empty"],
                     "—" if e["empty_rate"] is None else f"{e['empty_rate']}%"]
                    for e in sr["by_route"]]))
    else:
        add("No searches recorded in this window.")

    add("\n## 12. Page speed and devices\n")
    if p["speed"]:
        add("Browser-measured, per screen with at least 3 loads; slowest 90th "
            "percentile first.\n")
        add(_table(["route", "loads", "median load (ms)", "p90 load (ms)",
                    "median first byte (ms)"],
                   [[e["route"], e["samples"], e["load_median_ms"], e["load_p90_ms"],
                     e["ttfb_median_ms"]] for e in p["speed"]]))
    else:
        add("No page timings recorded in this window.")
    dv = p["devices"]
    seen = sum(dv["counts"].values())
    if seen:
        add("\nPageviews by device: " + ", ".join(
            f"{k} {v} ({round(100 * v / seen)}%)" for k, v in dv["counts"].items())
            + (f"; {dv['unknown']} earlier pageviews carry no device." if dv["unknown"] else "."))

    add("\n## 13. Screens by role\n")
    sbr = p["screens_by_role"]
    if sbr["rows"]:
        add("Pageviews per screen by the viewer's role — read low traffic "
            "against who can open the screen at all.\n")
        add(_table(["route", "total"] + sbr["roles"],
                   [[r["route"], r["total"]] + [r["by_role"].get(role, 0) for role in sbr["roles"]]
                    for r in sbr["rows"]]))
    else:
        add("No pageviews recorded.")

    add("\n## 14. Events by app version\n")
    if p["versions"]:
        add(_table(["version", "first seen", "last seen", "events", "client errors",
                    "HTTP errors"],
                   [[v["version"], v["first"], v["last"], v["events"],
                     v["client_errors"], v["http_errors"]] for v in p["versions"]]))
    else:
        add("No events recorded.")

    add("\n## 15. Appendix — sampled raw events (pseudonymized)\n")
    if p["sample_events"]:
        add(f"The {len(p['sample_events'])} most recent events (cap {SAMPLE_CAP}), "
            "newest first, pseudonymized as described in section 2.\n")
        add("```json")
        add(json.dumps(p["sample_events"], ensure_ascii=False, indent=1))
        add("```")
    else:
        add("No sample included.")

    return "\n".join(out) + "\n"
