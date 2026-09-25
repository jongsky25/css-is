"""Monitor + Invited events and Directory + Name cleanup as tabbed families
(v3.29), on the shared templates/_page_tabs.html component."""
import html as _h
import re


def _tabs(page):
    nav = re.search(r'<nav class="page-tabs".*?</nav>', page, re.S).group(0)
    hrefs = [_h.unescape(x) for x in re.findall(r'href="([^"]+)"', nav)]
    cur = [_h.unescape(x) for x in re.findall(r'href="([^"]+)"[^>]*aria-current="page"', nav)]
    return hrefs, cur


def test_monitor_and_invited_events_share_one_tab_bar(admin):
    for url in ("/monitor", "/activities/outside"):
        r = admin.get(url)
        assert r.status_code == 200, url
        hrefs, cur = _tabs(r.text)
        assert hrefs == ["/monitor", "/activities/outside"] and cur == [url], url
        # the Monitor menu entry lights up on both
        assert re.search(r'<a href="/monitor" aria-current="page">Monitor', r.text), url


def test_directory_and_name_cleanup_share_one_tab_bar(admin):
    for url in ("/directory", "/directory/cleanup"):
        r = admin.get(url)
        assert r.status_code == 200, url
        hrefs, cur = _tabs(r.text)
        assert hrefs == ["/directory", "/directory/cleanup"] and cur == [url], url
        assert re.search(r'<a href="/directory" aria-current="page">Directory', r.text), url


def test_invited_events_leaves_the_menu_but_stays_searchable(app_mod):
    class U:
        role = "admin"
    menu = {it["url"] for g in app_mod.nav_groups_for(U()) for it in g["items"]}
    assert "/activities/outside" not in menu and "/directory/cleanup" not in menu
    assert "/monitor" in menu and "/directory" in menu
    idx = {e["url"] for e in app_mod.search_index_for(U())}
    assert {"/activities/outside", "/directory/cleanup"} <= idx
