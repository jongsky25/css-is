"""Insights — the five CSS dashboards as tabs of one page (v3.28)."""
import re

TABS = [("pulse", "/dashboard"), ("people", "/dashboard/people"),
        ("participation", "/dashboard/participation"), ("teams", "/dashboard/teams"),
        ("trends", "/dashboard/trends")]


def _tab_hrefs(html):
    nav = re.search(r'<nav class="ins-tabs".*?</nav>', html, re.S).group(0)
    import html as _h
    unesc = lambda xs: [_h.unescape(x) for x in xs]
    return unesc(re.findall(r'href="([^"]+)"', nav)), unesc(re.findall(
        r'href="([^"]+)"[^>]*aria-current="page"', nav))


def test_every_dashboard_shows_the_same_tab_bar_with_itself_current(admin):
    for key, url in TABS:
        r = admin.get(url)
        assert r.status_code == 200, url
        hrefs, current = _tab_hrefs(r.text)
        assert [h.split("?")[0] for h in hrefs] == [u for _k, u in TABS], url
        assert current == [url], url
        assert "Insights" in r.text


def test_tabs_carry_org_everywhere_and_period_only_where_it_means_the_same(admin):
    hrefs, _ = _tab_hrefs(admin.get("/dashboard/people?org=X&period=year:2026").text)
    by_path = {h.split("?")[0]: h for h in hrefs}
    assert by_path["/dashboard"] == "/dashboard?org=X"          # Pulse's window is `win`
    assert by_path["/dashboard/trends"] == "/dashboard/trends?org=X&period=year%3A2026"
    hrefs, _ = _tab_hrefs(admin.get("/dashboard?win=ytd").text)
    assert all("?" not in h for h in hrefs)                      # `win` is never carried


def test_the_menu_has_one_insights_entry_but_search_still_finds_each_tab(app_mod):
    class U:
        role = "viewer"
    css = next(g for g in app_mod.nav_groups_for(U()) if g["name"] == "CSS")
    urls = [it["url"] for it in css["items"]]
    assert "/dashboard" in urls
    assert not {"/dashboard/people", "/dashboard/teams", "/dashboard/trends",
                "/dashboard/participation"} & set(urls)
    assert next(it for it in css["items"] if it["url"] == "/dashboard")["label"] == "Insights"
    idx = {e["url"] for e in app_mod.search_index_for(U())}
    assert {"/dashboard/people", "/dashboard/teams", "/dashboard/trends",
            "/dashboard/participation"} <= idx


def test_each_tab_keeps_its_own_page_key_but_lights_up_insights(admin):
    """Saved views, the page tour and PAGE_KEY are per page — only the menu
    highlight is shared across the five tabs."""
    html = admin.get("/dashboard/trends").text
    assert 'key: "trends"' in html and 'window.PAGE_KEY="trends"' in html
    assert re.search(r'<a href="/dashboard" aria-current="page">Insights', html)
