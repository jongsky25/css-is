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

    # viewer sees only the ungated groups; admin sees them all
    assert [g["name"] for g in app_mod.nav_groups_for(U("viewer"))] == \
        ["Dashboard", "Wellness", "Reports"]
    assert [g["name"] for g in app_mod.nav_groups_for(U("admin"))] == \
        ["Dashboard", "Wellness", "Reports", "Data entry", "Manage", "Admin"]
    # in_nav=False items stay out of the menu even when the cap is met
    admin_nav_urls = {it["url"] for g in app_mod.nav_groups_for(U("admin")) for it in g["items"]}
    assert "/directory/cleanup" not in admin_nav_urls


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
    r = admin.get("/css")
    assert r.status_code == 200
    assert 'data-search' in r.text                       # inline box present
    assert "window.SEARCH_INDEX" in r.text               # palette index injected
    assert "/static/js/search.js" in r.text


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
