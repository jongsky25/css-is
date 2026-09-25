"""
UX telemetry handoff — pure-function tests for ux_handoff.py, no DB.

Covers: per-day/per-type counting, pseudonymization (user ids dropped, stable
session aliases), the masked-route → handler segment-shape matching, the
feature-usage most/rarely/never-used bucketing, build_handoff round-tripping
through json.dumps, and the Markdown render (all sections present, no raw
identifiers leaking).
"""
import json

import ui_telemetry as ui_tel
import ux_handoff as uxh


def _ev(event_type, **kw):
    """A minimal ui_event-shaped dict, defaults matching storage.list_ui_events'
    output shape — same helper as test_ui_telemetry.py."""
    row = {"route": "/", "created_at": "2026-07-10T02:00:00", "session_id": None,
           "user_id": None, "component": None, "element_selector": None,
           "element_text": None, "meta": None, "event_type": event_type}
    row.update(kw)
    return row


NAVS = [("/", "Home", "Go to"),
        ("/monitor", "Monitor", "Manage"),
        ("/admin/backups", "Backups", "Admin")]


# ---- events_per_day / event_type_counts --------------------------------------

def test_events_per_day_buckets_and_totals():
    rows = [_ev("pageview", created_at="2026-07-10T02:00:00"),
            _ev("dead_click", created_at="2026-07-10T09:30:00"),
            _ev("pageview", created_at="2026-07-11T01:00:00")]
    days = uxh.events_per_day(rows)
    assert [d["day"] for d in days] == ["2026-07-10", "2026-07-11"]
    assert days[0] == {"day": "2026-07-10", "total": 2, "pageview": 1, "dead_click": 1}
    assert days[1] == {"day": "2026-07-11", "total": 1, "pageview": 1}


def test_event_type_counts_lists_every_vocabulary_type():
    counts = uxh.event_type_counts([_ev("pageview"), _ev("pageview"), _ev("rage_click")])
    assert counts["pageview"] == 2
    assert counts["rage_click"] == 1
    # silent types still show as explicit zeros — the analyst should see them
    assert set(counts) == ui_tel.UI_EVENT_TYPES | ui_tel.SERVER_EVENT_TYPES
    assert counts["form_abandon"] == 0


# ---- pseudonymize_events ------------------------------------------------------

def test_pseudonymize_drops_ids_and_aliases_sessions_stably():
    rows = [_ev("pageview", session_id="real-uuid-A", user_id=7, route="/monitor"),
            _ev("dead_click", session_id="real-uuid-B", user_id=8, route="/monitor"),
            _ev("pageview", session_id="real-uuid-A", user_id=7, route="/")]
    out = uxh.pseudonymize_events(rows)
    assert [e["session"] for e in out] == ["s1", "s2", "s1"]
    for e in out:
        assert "user_id" not in e and "id" not in e
        assert "real-uuid" not in json.dumps(e)


def test_pseudonymize_caps_sample_keeping_most_recent_first():
    rows = [_ev("pageview", session_id=f"sess{i}") for i in range(10)]
    out = uxh.pseudonymize_events(rows, sample_cap=3)
    assert len(out) == 3
    assert [e["session"] for e in out] == ["s1", "s2", "s3"]


# ---- map_routes_to_handlers ---------------------------------------------------

def test_route_handler_matching_masked_params():
    app_routes = [("/directory/person/{person_id}/edit", "directory_person_edit"),
                  ("/monitor", "monitor_home"),
                  ("/r/{qr_token}", "respond")]
    mapping = uxh.map_routes_to_handlers(
        ["/directory/person/{id}/edit", "/monitor", "/r/{token}"], app_routes)
    assert mapping == {"/directory/person/{id}/edit": "directory_person_edit",
                       "/monitor": "monitor_home",
                       "/r/{token}": "respond"}


def test_route_handler_matching_negatives():
    app_routes = [("/monitor", "monitor_home"),
                  ("/directory/person/{person_id}/edit", "directory_person_edit")]
    mapping = uxh.map_routes_to_handlers(
        ["/monitor/extra",                    # segment count differs
         "/{id}",                             # placeholder vs literal
         "/nowhere"], app_routes)             # no such route
    assert mapping == {}


# ---- feature_usage ------------------------------------------------------------

def test_feature_usage_buckets_most_rarely_never():
    rows = ([_ev("pageview", route="/monitor", session_id=f"s{i}", user_id=i + 1)
             for i in range(10)]
            + [_ev("pageview", route="/", session_id="s1", user_id=1)]
            + [_ev("pageview", route="/activity/{id}", session_id="s1", user_id=1)]
            + [_ev("dead_click", route="/admin/backups")])   # not a pageview
    usage = uxh.feature_usage(rows, NAVS)
    ranked = {d["route"]: d for d in usage["ranked"]}
    assert ranked["/monitor"]["views"] == 10
    assert ranked["/monitor"]["users"] == 10
    assert ranked["/"]["views"] == 1
    assert ranked["/admin/backups"]["views"] == 0
    assert usage["ranked"][0]["route"] == "/monitor"          # ranked by views desc
    assert [d["route"] for d in usage["never_used"]] == ["/admin/backups"]
    assert [d["route"] for d in usage["rarely_used"]] == ["/"]
    assert [d["route"] for d in usage["other_routes"]] == ["/activity/{id}"]


def test_feature_usage_nav_labels_and_groups_carried_through():
    usage = uxh.feature_usage([], NAVS)
    home = next(d for d in usage["ranked"] if d["route"] == "/")
    assert home["label"] == "Home" and home["group"] == "Go to"
    assert len(usage["never_used"]) == len(NAVS)


def test_feature_usage_merges_destinations_sharing_a_masked_route():
    """Nav urls that differ only by query string collapse to one masked route —
    they must merge into ONE row (labels joined), never claim views once per
    label."""
    navs = NAVS + [("/reports?type=1", "ARTA Walk-in", "Reports"),
                   ("/reports?type=2", "Activities", "Reports")]
    rows = [_ev("pageview", route="/reports", session_id="s1", user_id=1)]
    usage = uxh.feature_usage(rows, navs)
    reports = [d for d in usage["ranked"] if d["route"] == "/reports"]
    assert len(reports) == 1
    assert reports[0]["label"] == "ARTA Walk-in / Activities"
    assert reports[0]["group"] == "Reports"
    assert reports[0]["views"] == 1


# ---- build_handoff / render_handoff_markdown ---------------------------------

def _handoff(rows, feedback=(), **kw):
    args = dict(window_days=30, now="2026-07-18T08:00:00",
                app_version="9.99", generated_at="2026-07-18T08:00:00",
                retention_days=90, truncated=False, nav_destinations=NAVS,
                app_routes=[("/monitor", "monitor_home"), ("/", "home")])
    args.update(kw)
    return uxh.build_handoff(rows, list(feedback), **args)


def _rows():
    return [
        _ev("pageview", route="/monitor", session_id="sessA", user_id=7,
            meta={"from": "/"}),
        _ev("pageview", route="/", session_id="sessA", user_id=7),
        _ev("rage_click", route="/monitor", session_id="sessA", user_id=7,
            component="roster", element_text="Save | all"),
        _ev("rage_click", route="/monitor", session_id="sessB", user_id=8,
            component="roster", element_text="Save | all"),
        _ev("search_empty", route="/", session_id="sessA", user_id=7,
            meta={"term": "certificates"}),
        _ev("client_error", route="/monitor", session_id="sessB", user_id=8,
            meta={"name": "TypeError", "message": "x is null"}),
    ]


def test_build_handoff_json_serializable_with_expected_keys():
    payload = _handoff(_rows())
    for key in ("generated_at", "app_version", "window", "totals",
                "event_type_counts", "opportunities", "top_screens", "nav_flows",
                "dead_ends", "events_per_day", "feature_usage", "route_handlers",
                "failed_searches", "errors", "sample_events"):
        assert key in payload, key
    json.dumps(payload)                       # must round-trip cleanly
    assert payload["nav_flows"] == [{"from": "/", "to": "/monitor", "count": 1}]
    assert payload["route_handlers"]["/monitor"] == "monitor_home"


def test_build_handoff_sample_can_be_excluded():
    assert _handoff(_rows(), include_sample=False)["sample_events"] == []


def test_markdown_contains_every_section_header():
    md = uxh.render_handoff_markdown(_handoff(_rows()))
    for header in ("# Office Connect UX Telemetry Handoff",
                   "## 1. What this app is", "## 2. How to read this data",
                   "## 3. Your task", "## 4. Ranked friction opportunities",
                   "## 5. Traffic & flows", "## 6. Feature usage & coverage",
                   "## 7. Route → handler map", "## 8. Failed searches",
                   "## 9. Client errors", "## 10. Task outcomes by screen",
                   "## 11. Search", "## 12. Page speed and devices",
                   "## 13. Screens by role", "## 14. Events by app version",
                   "## 15. Appendix"):
        assert header in md, header


def test_markdown_reports_usage_and_escapes_pipes():
    md = uxh.render_handoff_markdown(_handoff(_rows()))
    assert "Backups (`/admin/backups`)" in md          # never-used callout
    assert "Save \\| all" in md                        # element_text pipe escaped
    assert "certificates" in md                        # failed search term
    assert "monitor_home" in md                        # handler map


def test_markdown_never_leaks_raw_identifiers():
    md = uxh.render_handoff_markdown(_handoff(_rows()))
    assert "sessA" not in md and "sessB" not in md     # sessions pseudonymized
    assert '"user_id"' not in md                       # user ids dropped outright
    assert '"session": "s1"' in md


def test_build_handoff_resanitizes_at_the_export_boundary():
    """Rows are supposed to arrive sanitized from storage, but the export must
    never trust a single earlier layer: raw digits/ids planted directly in the
    rows (e.g. a row written around the ingest path) get re-masked."""
    rows = [_ev("rage_click", route="/directory/person/482/edit",
                session_id="sessA", user_id=7, element_text="Call 09171234567"),
            _ev("search_empty", route="/encode", session_id="sessA", user_id=7,
                meta={"term": "batch 12345"})]
    md = uxh.render_handoff_markdown(_handoff(rows))
    assert "482" not in md and "/directory/person/{id}/edit" in md
    assert "09171234567" not in md
    assert "12345" not in md and "batch ###" in md


def test_markdown_is_deterministic():
    a = uxh.render_handoff_markdown(_handoff(_rows()))
    b = uxh.render_handoff_markdown(_handoff(_rows()))
    assert a == b


def test_markdown_lists_each_matched_feedback_once():
    """Two hotspots on one route share its open route-level comment — the
    export lists that comment once, naming both ranks, not once per hotspot."""
    rows = [_ev("dead_click", route="/wellness", element_selector=sel,
                session_id=f"s{u}", user_id=u)
            for sel in ("#a", "#b") for u in (1, 2, 3)]
    fb = [{"page_url": "/wellness", "element_selector": None, "message": "confusing page",
           "status": "New", "created_at": "2026-07-10T00:00:00"}]
    md = uxh.render_handoff_markdown(_handoff(rows, fb))
    assert md.count("confusing page") == 1
    assert "matches #1, #2" in md


def test_markdown_client_errors_show_message_location_and_frames():
    rows = [_ev("client_error", route="/wellness", session_id="sessA", user_id=7,
                meta={"name": "TypeError", "message": "pet is null",
                      "source": "/static/js/avatars.js", "line": 612, "col": 9,
                      "frames": ["careClick /static/js/avatars.js:612:9"]})]
    md = uxh.render_handoff_markdown(_handoff(rows))
    assert "pet is null" in md
    assert "/static/js/avatars.js:612:9" in md
    assert "`careClick /static/js/avatars.js:612:9`" in md


def test_handoff_answers_the_new_measurement_questions():
    rows = [
        _ev("pageview", route="/wellness/apply", role="viewer", meta={"vp": "phone", "v": "3.26"}),
        _ev("pageview", route="/wellness/apply", role="section_manager", meta={"vp": "desktop", "v": "3.26"}),
        _ev("form_submit", route="/wellness/apply"),
        _ev("form_abandon", route="/wellness/apply", meta={"fields": 2}),
        _ev("form_abandon", route="/wellness/apply", meta={"fields": 1}),
        _ev("form_error", route="/wellness/apply"),
        _ev("http_error", route="/admin/users", meta={"status": 403}),
        _ev("search", route="/people", meta={"hits": 4}),
        _ev("search", route="/people", meta={"hits": 0}),
        _ev("search_empty", route="/people", meta={"term": "zz"}),
    ] + [_ev("page_timing", route="/", meta={"load_ms": ms, "ttfb_ms": 100})
         for ms in (900, 1000, 4000)]
    md = uxh.render_handoff_markdown(_handoff(rows))
    assert "| /wellness/apply | 1 | 2 | 67% | 1 | — |" in md        # abandon rate
    assert "403×1" in md
    assert "2 searches, 1 with no results (50% empty)" in md
    assert "| / | 3 | 1000 | 4000 | 100 |" in md                   # median / p90 / ttfb
    assert "phone 1 (50%)" in md and "desktop 1 (50%)" in md
    assert "section_manager" in md and "## 14. Events by app version" in md
    assert "| 3.26 |" in md
