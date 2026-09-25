"""
Passive UX telemetry — sanitizer + route-mask + aggregation unit tests
(docs/UX_TELEMETRY_HANDOFF_PLAN.md).

Pure-function tests for ui_telemetry.py, no DB — mirrors the edge cases OFIS's own
__tests__/telemetry.ts suite covers for the reference implementation being ported:
sanitizeText / maskRoute (whitespace collapse, digit masking, length cap, root
route, empty input, query/hash stripped, origin stripped, static path untouched)
and the aggregation/ranking functions (topRoutes/navFlows/exitRoutes,
emptySearchTerms/errorsByRoute, frictionByTarget/frictionScore,
correlateFeedback, buildDigest's ranking acceptance case).
"""
import ui_telemetry as ui_tel


def _ev(event_type, **kw):
    """A minimal ui_event-shaped dict, defaults matching storage.list_ui_events'
    output shape. Mirrors the OFIS test suite's ev() helper."""
    row = {"route": "/", "created_at": "2026-07-10T02:00:00", "session_id": None,
           "user_id": None, "component": None, "element_selector": None,
           "element_text": None, "meta": None, "event_type": event_type}
    row.update(kw)
    return row


# ---- sanitize_text -----------------------------------------------------------

def test_sanitize_text_empty_is_none():
    assert ui_tel.sanitize_text("") is None
    assert ui_tel.sanitize_text(None) is None
    assert ui_tel.sanitize_text("   ") is None


def test_sanitize_text_collapses_whitespace():
    assert ui_tel.sanitize_text("  a\n  b   c ") == "a b c"


def test_sanitize_text_masks_digit_runs():
    assert ui_tel.sanitize_text("Total 1,234") == "Total 1,###"
    assert ui_tel.sanitize_text("attendee 90210") == "attendee ###"


def test_sanitize_text_keeps_short_numbers():
    assert ui_tel.sanitize_text("Q2 42") == "Q2 42"


def test_sanitize_text_caps_length():
    out = ui_tel.sanitize_text("x" * 300)
    assert len(out) == 161  # 160 + the ellipsis char
    assert out.endswith("…")


# ---- sanitize_selector --------------------------------------------------------

def test_sanitize_selector_empty_is_none():
    assert ui_tel.sanitize_selector("") is None
    assert ui_tel.sanitize_selector(None) is None


def test_sanitize_selector_caps_length():
    out = ui_tel.sanitize_selector("a" * 1500)
    assert len(out) == ui_tel.MAX_SELECTOR


# ---- mask_route ----------------------------------------------------------------

def test_mask_route_root_stays_root():
    assert ui_tel.mask_route("/") == "/"


def test_mask_route_empty_is_root():
    assert ui_tel.mask_route("") == "/"
    assert ui_tel.mask_route(None) == "/"


def test_mask_route_masks_numeric_id():
    assert ui_tel.mask_route("/directory/person/482/edit") == "/directory/person/{id}/edit"


def test_mask_route_masks_hex_token():
    assert ui_tel.mask_route("/r/9f2c1e4a1234") == "/r/{token}"


def test_mask_route_masks_date_segment():
    assert ui_tel.mask_route("/x/2025-01-31") == "/x/{date}"
    assert ui_tel.mask_route("/x/2025-01") == "/x/{date}"


def test_mask_route_drops_query_and_hash():
    assert ui_tel.mask_route("/dashboard?tab=ar#top") == "/dashboard"


def test_mask_route_strips_origin():
    assert ui_tel.mask_route("https://app.example.com/reports/activities/91") == \
        "/reports/activities/{id}"


def test_mask_route_static_path_untouched():
    assert ui_tel.mask_route("/reports/activities-export") == "/reports/activities-export"


def test_mask_route_is_idempotent():
    """Masking an already-masked route (what the client sends) must be a no-op —
    this is exactly what makes server-side re-masking safe defense-in-depth."""
    once = ui_tel.mask_route("/directory/person/482/edit")
    twice = ui_tel.mask_route(once)
    assert once == twice == "/directory/person/{id}/edit"


# ---- top_routes / nav_flows / exit_routes -------------------------------------

def test_top_routes_nav_flows_exit_routes():
    rows = [
        _ev("pageview", route="/a", session_id="s1", user_id=1, created_at="2026-07-10T02:00:00"),
        _ev("pageview", route="/b", session_id="s1", user_id=1, meta={"from": "/a"},
            created_at="2026-07-10T02:01:00"),
        _ev("pageview", route="/a", session_id="s2", user_id=2, created_at="2026-07-10T02:02:00"),
        _ev("pageview", route="/b", session_id="s2", user_id=2, meta={"from": "/a"},
            created_at="2026-07-10T02:03:00"),
    ]
    top = ui_tel.top_routes(rows)
    assert len(top) == 2 and top[0]["views"] == 2
    assert next(t for t in top if t["route"] == "/a")["users"] == 2

    flows = ui_tel.nav_flows(rows)
    assert flows[0]["from"] == "/a" and flows[0]["to"] == "/b" and flows[0]["count"] == 2

    exits = ui_tel.exit_routes(rows)
    assert exits[0]["route"] == "/b" and exits[0]["exits"] == 2   # both sessions end on /b


# ---- empty_search_terms / errors_by_route -------------------------------------

def test_empty_search_terms_and_errors_by_route():
    rows = [
        _ev("search_empty", route="/directory", meta={"term": "acme"}),
        _ev("search_empty", route="/directory", meta={"term": "acme"}),
        _ev("search_empty", route="/reports", meta={"term": "xyz"}),
        _ev("client_error", route="/directory/person/{id}/edit", meta={"name": "TypeError"}),
    ]
    terms = ui_tel.empty_search_terms(rows)
    assert terms[0]["term"] == "acme" and terms[0]["count"] == 2

    errs = ui_tel.errors_by_route(rows)
    assert errs[0]["name"] == "TypeError" and errs[0]["count"] == 1


# ---- friction_by_target / friction_score ---------------------------------------

def test_friction_by_target_and_score():
    rows = [
        _ev("dead_click", route="/books", component="save-btn", element_text="Save",
            session_id="s1", user_id=1),
        _ev("rage_click", route="/books", component="save-btn", session_id="s1", user_id=1),
        _ev("rage_click", route="/books", component="save-btn", session_id="s2", user_id=2),
    ]
    targets = ui_tel.friction_by_target(rows)
    assert len(targets) == 1
    t = targets[0]
    assert t["dead_clicks"] == 1 and t["rage_clicks"] == 2
    assert t["users"] == 2
    assert t["element_text"] == "Save"

    # base = 2*3 + 1 = 7; users=2 -> weight 0.8 -> 5.6
    assert ui_tel.friction_score(t) == 5.6
    single = ui_tel.friction_score({"rage_clicks": 2, "dead_clicks": 1, "users": 1})
    assert single < ui_tel.friction_score(t)


# ---- correlate_feedback ---------------------------------------------------------

def test_correlate_feedback_matches_route_and_selector():
    targets = ui_tel.friction_by_target([
        _ev("dead_click", route="/directory", component="export", element_selector="#export"),
    ])
    feedback = [
        {"page_url": "/directory?tab=ar", "element_selector": "#export",
         "message": "export does nothing", "status": "New", "created_at": "2026-07-09T02:00:00"},
        {"page_url": "/reports", "element_selector": None, "message": "unrelated",
         "status": "New", "created_at": "2026-07-09T02:00:00"},
    ]
    with_fb = ui_tel.correlate_feedback(targets, feedback)
    assert len(with_fb[0]["feedback"]) == 1
    assert with_fb[0]["feedback"][0]["message"] == "export does nothing"


# ---- build_digest — ranking (the acceptance-critical bit) ----------------------

def test_build_digest_feedback_correlated_hotspot_outranks_higher_count_one():
    """Hotspot A: higher raw clicks, no feedback. Hotspot B: fewer clicks, but has
    matching spot feedback — the feedback boost should lift B above A."""
    rows = [
        # A: 3 rage across 3 users -> base 9, weight 1 -> 9
        _ev("rage_click", route="/a", component="compA", session_id="s1", user_id=1),
        _ev("rage_click", route="/a", component="compA", session_id="s2", user_id=2),
        _ev("rage_click", route="/a", component="compA", session_id="s3", user_id=3),
        # B: 2 rage + 1 dead across 3 users -> base 7, weight 1 -> 7, x1.5 feedback -> 10.5
        _ev("rage_click", route="/b", component="compB", element_selector="#b",
            session_id="s1", user_id=1),
        _ev("rage_click", route="/b", component="compB", element_selector="#b",
            session_id="s2", user_id=2),
        _ev("dead_click", route="/b", component="compB", element_selector="#b",
            session_id="s3", user_id=3),
    ]
    feedback = [{"page_url": "/b", "element_selector": "#b", "message": "broken",
                "status": "New", "created_at": "2026-07-09T02:00:00"}]
    digest = ui_tel.build_digest(rows, feedback, window_days=30, limit=10)

    assert digest["opportunities"][0]["rank"] == 1
    assert digest["opportunities"][0]["route"] == "/b"
    assert digest["opportunities"][0]["component"] == "compB"
    assert "spot-feedback" in digest["opportunities"][0]["hint"] or \
        "reported this" in digest["opportunities"][0]["hint"]
    assert digest["totals"]["users"] == 3 and digest["totals"]["sessions"] == 3
    assert digest["window"]["days"] == 30


def test_build_digest_empty_rows_no_error():
    digest = ui_tel.build_digest([], [], window_days=30)
    assert digest["opportunities"] == []
    assert digest["totals"] == {"sessions": 0, "users": 0, "events": 0}
    assert digest["window"]["from"] is None


# ---- noise filtering: rapid taps, background + canvas clicks ------------------

def test_rage_on_a_real_control_counts_as_rapid_taps_not_rage():
    """Feeding the companion fast is play, not a dead button: a rage burst on a
    <button> (meta.interactive, or — for rows recorded before that flag — a
    selector ending in a control tag) scores like a dead click, not x3."""
    btn = "#maincontent > div:nth-of-type(2) > span > button:nth-of-type(1)"
    targets = ui_tel.friction_by_target([
        _ev("rage_click", route="/wellness", element_selector=btn, user_id=1),
        _ev("rage_click", route="/wellness", element_selector=btn, user_id=2),
        _ev("rage_click", route="/wellness", element_selector="#pet",
            meta={"interactive": True}, user_id=3),
        _ev("rage_click", route="/wellness", element_selector="#maincontent > div > span",
            user_id=4),
    ])
    by_sel = {t["selector"]: t for t in targets}
    assert by_sel[btn]["rapid_taps"] == 2 and by_sel[btn]["rage_clicks"] == 0
    assert by_sel["#pet"]["rapid_taps"] == 1
    assert by_sel["#maincontent > div > span"]["rage_clicks"] == 1
    assert ui_tel.friction_score(by_sel[btn]) == 1.6          # 2 x 1, 2 users x0.8


def test_background_and_canvas_clicks_are_not_friction():
    targets = ui_tel.friction_by_target([
        _ev("dead_click", route="/", element_selector="html > body"),
        _ev("dead_click", route="/", element_selector="#maincontent"),
        _ev("dead_click", route="/me", element_selector="#sigCanvas"),
        _ev("rage_click", route="/me", element_selector="#sigCanvas"),
        _ev("dead_click", route="/", element_selector="#maincontent > div > div:nth-of-type(1)"),
    ])
    assert [t["selector"] for t in targets] == ["#maincontent > div > div:nth-of-type(1)"]


def test_resolved_route_level_feedback_neither_attaches_nor_boosts():
    """A Done comment about something else on the same screen says nothing
    about this element — it must not ride along (or boost) on every hotspot of
    that route. Open route-level comments still attach and boost."""
    rows = [_ev("dead_click", route="/a", element_selector="#x", user_id=u) for u in (1, 2, 3)]
    done = {"page_url": "/a", "element_selector": "#other", "message": "old",
            "status": "Done", "created_at": "2026-06-01T00:00:00"}
    digest = ui_tel.build_digest(rows, [done], window_days=30)
    assert digest["opportunities"][0]["feedback"] == []
    assert digest["opportunities"][0]["score"] == 3

    open_fb = dict(done, status="Reviewing", message="still odd")
    digest = ui_tel.build_digest(rows, [done, open_fb], window_days=30)
    assert [f["message"] for f in digest["opportunities"][0]["feedback"]] == ["still odd"]
    assert digest["opportunities"][0]["score"] == 4.5


def test_resolved_exact_element_feedback_attaches_without_boost():
    rows = [_ev("dead_click", route="/a", element_selector="#x", user_id=u) for u in (1, 2, 3)]
    done = {"page_url": "/a", "element_selector": "#x", "message": "fixed?",
            "status": "Done", "created_at": "2026-06-01T00:00:00"}
    o = ui_tel.build_digest(rows, [done], window_days=30)["opportunities"][0]
    assert o["feedback"][0]["exact"] is True
    assert o["score"] == 3
    assert "may not have landed" in o["hint"]
