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


SYSTEM = ["/admin/backups", "/admin/audit", "/admin/sharing", "/ops",
          "/admin/ux-insights", "/admin/rules"]


def test_the_six_system_screens_share_one_tab_bar(admin):
    for url in SYSTEM:
        r = admin.get(url)
        assert r.status_code == 200, url
        hrefs, cur = _tabs(r.text)
        assert hrefs == SYSTEM and cur == [url], url
        assert re.search(r'<a href="/admin/backups" aria-current="page">System', r.text), url


def test_system_is_one_menu_entry_for_admins_only(app_mod, viewer):
    class A:
        role = "admin"
    admin_menu = [it for g in app_mod.nav_groups_for(A()) for it in g["items"]]
    urls = {it["url"] for it in admin_menu}
    assert "/admin/backups" in urls
    assert not set(SYSTEM[1:]) & urls
    assert next(it for it in admin_menu if it["url"] == "/admin/backups")["label"] == "System"
    assert set(SYSTEM) <= {e["url"] for e in app_mod.search_index_for(A())}
    # still admin-only, tab by tab
    for url in SYSTEM:
        assert viewer.get(url, follow_redirects=False).status_code in (302, 303, 403), url
