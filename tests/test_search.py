"""
Search palette — the role-aware index, the /search fallback page, and the
landing-page wiring.

The index is built server-side (search_index_for), so the key guarantee is that
a user is never even handed links they aren't allowed to open. We assert that
both at the helper level and through the rendered /search page.
"""
from __future__ import annotations


def _urls(items):
    return {it["url"] for it in items}


def test_index_role_filtering(app_mod):
    class U:  # minimal stand-in for request.state.user
        def __init__(self, role): self.role = role

    viewer = app_mod.search_index_for(U("viewer"))
    admin = app_mod.search_index_for(U("admin"))

    vurls, aurls = _urls(viewer), _urls(admin)
    # everyone gets the dashboards + reports + Home
    assert "/" in vurls and "/dashboard/trends" in vurls and "/reports?type=1" in vurls
    # admin-only destinations must NOT reach a viewer
    for gated in ("/admin/users", "/admin/audit", "/ops", "/encode", "/create"):
        assert gated not in vurls
        assert gated in aurls
    # the search-only item (not in the top nav) is still searchable for admins
    assert "/directory/cleanup" in aurls


def test_nav_groups_track_the_index(app_mod):
    class U:
        def __init__(self, role): self.role = role

    # Four product groups, Wellness first (it is the busiest screen in the app).
    # A viewer meets no admin cap, so Administrator drops out entirely.
    assert [g["name"] for g in app_mod.nav_groups_for(U("viewer"))] == \
        ["Wellness", "CSS", "AWA"]
    assert [g["name"] for g in app_mod.nav_groups_for(U("admin"))] == \
        ["Wellness", "CSS", "AWA", "Administrator"]
    # in_nav=False items stay out of the menu even when the cap is met
    admin_nav_urls = {it["url"] for g in app_mod.nav_groups_for(U("admin")) for it in g["items"]}
    assert "/directory/cleanup" not in admin_nav_urls

    # CSS carries its sixteen destinations as headed sections, in this order;
    # every item lands in exactly one and `items` stays the flat union.
    css = next(g for g in app_mod.nav_groups_for(U("admin")) if g["name"] == "CSS")
    assert [s["name"] for s in css["sections"]] == \
        ["See how we're doing", "Official reports", "Run a survey", "Data entry"]
    assert sum(len(s["items"]) for s in css["sections"]) == len(css["items"])
    # a single-section group renders as one unnamed block, i.e. a plain list
    awa = next(g for g in app_mod.nav_groups_for(U("viewer")) if g["name"] == "AWA")
    assert [s["name"] for s in awa["sections"]] == [""]

    # A section whose every item is capped away must vanish, not leave a stray
    # heading: an encoder can reach Paper entry but none of "Run a survey".
    enc = next(g for g in app_mod.nav_groups_for(U("encoder")) if g["name"] == "CSS")
    assert [s["name"] for s in enc["sections"]] == \
        ["See how we're doing", "Official reports", "Data entry"]
    assert all(s["items"] for s in enc["sections"])


def test_chief_cap_gates_the_team_pages(app_mod):
    """The wellness/AWA team pages gate at runtime on directory RANK, not on an
    account role, so NAV_GROUPS marks them cap="chief" and the request middleware
    supplies the answer. A plain viewer must not even be handed the links."""
    class U:
        def __init__(self, role): self.role = role

    # both queues' nav entries now open the one approvals inbox
    team_urls = {"/wellness/dashboard", "/work-arrangement/schedule", "/approvals"}

    def urls(user, is_chief):
        return {it["url"] for g in app_mod.nav_groups_for(user, is_chief) for it in g["items"]}

    assert not (team_urls & urls(U("viewer"), False))    # ordinary staff: none
    assert team_urls <= urls(U("viewer"), True)          # a section chief: all of them
    assert team_urls <= urls(U("admin"), False)          # admins always, chief flag or not

    # the search palette must make the same call, or the two drift apart
    idx = {e["url"] for e in app_mod.search_index_for(U("viewer"), False)}
    assert not (team_urls & idx)
    assert team_urls <= {e["url"] for e in app_mod.search_index_for(U("viewer"), True)}

    # A bureau-wide WORK-ARRANGEMENT grant is offered the schedule it exists for
    # — and only that. Not the approvals queue (sight is not authority) and not
    # the wellness register (that grant is a different, wider one).
    class G:
        def __init__(self, role, access):
            self.role, self.bureau_access = role, access

    granted = urls(G("viewer", "awa"), False)
    assert "/work-arrangement/schedule" in granted
    assert "/approvals" not in granted
    assert "/wellness/dashboard" not in granted


def test_search_page_requires_login(app_mod):
    # a fresh, cookie-less client — the shared `client` fixture accumulates a
    # session cookie from earlier login tests.
    from starlette.testclient import TestClient
    c = TestClient(app_mod.app)
    r = c.get("/search", follow_redirects=False)
    assert r.status_code == 303                        # bounced to /login
    assert "/login" in r.headers["location"]


def test_search_page_matches_and_links(admin):
    r = admin.get("/search?q=trends")
    assert r.status_code == 200
    assert "/dashboard/trends" in r.text
    assert "1 result" in r.text                          # exactly one page matches "trends"


def test_search_page_respects_role(viewer):
    # a viewer searching for an admin term gets no admin link
    r = viewer.get("/search?q=audit")
    assert r.status_code == 200
    assert "/admin/audit" not in r.text


def test_landing_wires_the_search_box(admin):
    r = admin.get("/")
    assert r.status_code == 200
    assert 'data-search' in r.text                       # inline box present
    assert 'data-scope="all"' in r.text
    assert "window.SEARCH_INDEX" in r.text               # palette index injected
    assert "/static/js/search.js" in r.text


def test_calendar_tab_has_no_inline_box(admin):
    r = admin.get("/?view=calendar")
    assert r.status_code == 200
    assert "data-search" not in r.text


def test_css_hub_search_is_scoped_to_css(admin):
    r = admin.get("/css")
    assert r.status_code == 200
    assert 'data-scope="css"' in r.text
    assert "CSS hub" in r.text
    assert "What would you like to do" not in r.text
    assert "Try the assistant" not in r.text


def test_nav_search_button_only_when_signed_in(admin, app_mod):
    assert 'id="navSearchBtn"' in admin.get("/").text
    from fastapi.testclient import TestClient
    anon = TestClient(app_mod.app)
    assert 'id="navSearchBtn"' not in anon.get("/login").text


# ── /api/search ──────────────────────────────────────────────────────────────

def test_api_search_requires_login(app_mod):
    from starlette.testclient import TestClient
    c = TestClient(app_mod.app)
    r = c.get("/api/search?q=test", follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in r.headers["location"]


def test_api_search_short_query(admin):
    assert admin.get("/api/search?q=a").json() == []


def test_api_search_empty_query(admin):
    assert admin.get("/api/search?q=").json() == []


def test_api_search_result_shape(admin):
    r = admin.get("/api/search?q=test")
    assert r.status_code == 200
    data = r.json()
    assert isinstance(data, list)
    for item in data:
        for key in ("title", "hint", "url", "section"):
            assert key in item, f"missing '{key}' in {item}"


def test_api_search_activities(admin):
    """A real seeded activity surfaces in the Activities section, and its link
    points at the /reports/activities/<id> the report page actually resolves."""
    r = admin.get("/api/search?q=learning")
    assert r.status_code == 200
    data = r.json()
    acts = [it for it in data if it["section"] == "Activities"]
    assert acts, "expected at least one Activities hit for 'learning'"
    assert any("Learning" in it["title"] for it in acts)
    # the link must resolve to a real activity report page (not 404)
    url = next(it["url"] for it in acts if "Learning" in it["title"])
    assert url.startswith("/reports/activities/")
    detail = admin.get(url)
    assert detail.status_code == 200


def test_api_search_excludes_comments(admin):
    """Verbatim comments are no longer searchable — no Comments section."""
    # 'good' matches plenty of verbatims in the seed but must surface none here.
    data = admin.get("/api/search?q=good").json()
    assert all(it["section"] != "Comments" for it in data)


def test_api_search_people(admin, app_mod):
    """Seed a person and verify they appear in the People section."""
    import sqlite3
    db_path = app_mod.DB
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute(
            "INSERT OR IGNORE INTO resource_person (name, is_internal)"
            " VALUES ('Zirconium Testperson', 1)"
        )
        conn.commit()
    finally:
        conn.close()

    r = admin.get("/api/search?q=zirconium")
    assert r.status_code == 200
    data = r.json()
    sections = [it["section"] for it in data]
    assert "People" in sections
    titles = [it["title"] for it in data if it["section"] == "People"]
    assert any("Zirconium" in t for t in titles)


def test_rendered_nav_shows_groups_and_sections(admin):
    """The data-level assertions above don't prove dash_layout renders it. Guard
    the actual markup: four group summaries, and CSS's sub-headings present."""
    html = admin.get("/dashboard").text
    for group in ("Wellness", "CSS", "AWA", "Administrator"):
        assert f"<summary>{group}</summary>" in html, group
    for sec in ("Official reports", "Run a survey", "Data entry", "Setup &amp; records"):
        assert f'<div class="msec">{sec}</div>' in html, sec
    # (the "See how we're doing" heading renders with Jinja's escaped apostrophe)
    assert '<div class="msec">See how we&#39;re doing</div>' in html
    # the old seven-group shape is gone
    assert "<summary>Data entry</summary>" not in html
    assert "<summary>Manage</summary>" not in html


# ── scoped search (Phase 2) ──────────────────────────────────────────────────

def test_index_entries_carry_their_module(app_mod):
    class U:
        role = "admin"

    idx = app_mod.search_index_for(U())
    assert idx and all(e.get("mod") for e in idx)
    assert {e["mod"] for e in idx} >= {"core", "css", "wellness", "awa", "administrator"}
    by_url = {e["url"]: e["mod"] for e in idx}
    assert by_url["/css"] == "core" and by_url["/me"] == "core"


def test_css_scoped_page_has_the_exit_hooks(admin):
    r = admin.get("/css")
    assert 'data-scope="css"' in r.text and "/static/js/search.js?v=20261009b" in r.text


def test_api_search_scope_css_returns_only_activity_and_people_sections(admin):
    for q in ("learning", "good", "a b"):
        for row in admin.get(f"/api/search?q={q}&scope=css").json():
            assert row["section"] in ("Activities", "People")


def test_api_search_unknown_scope_is_treated_as_all(admin):
    assert (admin.get("/api/search?q=good&scope=nonsense").json()
            == admin.get("/api/search?q=good").json())


# ── source registry + rate limit (Phase 3) ──────────────────────────────────

def test_a_broken_source_does_not_break_search(admin, monkeypatch):
    import search_sources as ss

    def boom(conn, user, terms, ctx):
        raise RuntimeError("source down")

    monkeypatch.setattr(ss, "SOURCES", [
        {"key": "bad", "section": "Bad", "scopes": {"all", "css"}, "run": boom},
        {"key": "ok", "section": "Ok", "scopes": {"all", "css"},
         "run": lambda conn, user, terms, ctx: [{"title": "fine", "hint": "", "url": "/x",
                                                 "section": "Ok", "kw": ""}]},
    ])
    r = admin.get("/api/search?q=anything")
    assert r.status_code == 200
    assert [row["title"] for row in r.json()] == ["fine"]


def test_sections_and_response_are_capped(app_mod):
    import search_sources as ss
    many = lambda conn, user, terms, ctx: [{"title": str(i), "section": "S"} for i in range(50)]
    src = [{"key": str(i), "section": "S", "scopes": {"all"}, "run": many} for i in range(10)]
    out = ss.run_sources(None, None, ["x"], {}, "all", sources=src)
    assert len(out) == ss.TOTAL_CAP
    assert len(ss.run_sources(None, None, ["x"], {}, "all", sources=src[:1])) == ss.SECTION_CAP


def test_scope_filters_which_sources_run(app_mod):
    import search_sources as ss
    run = lambda tag: (lambda conn, user, terms, ctx: [{"title": tag}])
    src = [{"key": "a", "section": "A", "scopes": {"all", "css"}, "run": run("a")},
           {"key": "b", "section": "B", "scopes": {"all"}, "run": run("b")}]
    assert [r["title"] for r in ss.run_sources(None, None, [], {}, "css", sources=src)] == ["a"]
    assert [r["title"] for r in ss.run_sources(None, None, [], {}, "all", sources=src)] == ["a", "b"]
    assert [r["title"] for r in ss.run_sources(None, None, [], {}, "bogus", sources=src)] == ["a", "b"]


def test_the_121st_search_in_a_minute_returns_nothing(admin, monkeypatch):
    import search_sources as ss
    monkeypatch.setattr(ss, "SOURCES", [
        {"key": "ok", "section": "Ok", "scopes": {"all"},
         "run": lambda conn, user, terms, ctx: [{"title": "fine", "hint": "", "url": "/x",
                                                 "section": "Ok", "kw": ""}]}])
    for _ in range(120):
        assert admin.get("/api/search?q=zz").json() != []
    assert admin.get("/api/search?q=zz").json() == []
