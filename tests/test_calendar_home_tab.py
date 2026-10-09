"""The Calendar tab on the landing page (office calendar C2) and its to-do task."""
from __future__ import annotations
import re
from datetime import timedelta

import pytest

import calendar_routes
import office_connect as oc
import storage as st
import tzutil as tz
from conftest import in_the_directory
from test_calendar_home import add, world, TODAY      # noqa: F401  (fixtures + helpers shared with C1)


@pytest.fixture()
def conn(app_mod):
    c = st.connect(app_mod.DB); st.init_db(c)
    yield c
    for (i,) in c.execute("SELECT id FROM calendar_entry WHERE title LIKE 'CALTB %'").fetchall():
        st.cal_delete(c, i)
    c.execute("DELETE FROM holiday WHERE name LIKE 'CALTB %'")
    c.execute("DELETE FROM org_unit WHERE path LIKE 'CALTB%'")
    c.commit(); c.close()


def mk(conn, title, offset=0, **kw):
    kw.setdefault("audience", "bureau")
    day = (tz.today_local() + timedelta(days=offset)).isoformat()
    return st.cal_create(conn, f"CALTB {title}", day, **kw)


def hrefs(html):
    return re.findall(r'href="([^"]+)"', html)


# ------------------------------------------------------------------ the tab ---

@pytest.mark.parametrize("who", ["viewer", "encoder", "manager", "admin"])
def test_every_role_gets_a_calendar_tab(request, who, conn):
    mk(conn, "Staff huddle", 1)
    html = request.getfixturevalue(who).get("/?view=calendar").text
    assert "CALTB Staff huddle" in html and 'class="cal-bar"' in html
    assert 'aria-current="true">Calendar</a>' in html and 'href="/?view=me"' in html


def test_the_tab_shows_only_the_calendar_and_keeps_the_tab_switch(viewer, conn):
    mk(conn, "Today thing", 0)
    html = viewer.get("/?view=calendar").text
    assert '<h1 class="cal-h1">Calendar</h1>' in html and "CALTB Today thing" in html
    assert 'href="/?view=me"' in html and 'aria-current="true">Calendar</a>' in html       # leaving is one tap
    for gone in ("Your to-do", "Hi", "Coming up", "Your wellness break", "class=\"doors\"",
                 "How your companion grows", "class=\"oc-pet\"", "class=\"oc-photo\"", "class=\"oc-me\""):
        assert gone not in html, gone


def test_the_other_tabs_still_have_the_greeting_and_to_do(viewer, conn):
    for url in ("/", "/?view=me"):
        html = viewer.get(url).text
        assert "Hi" in html and 'class="oc-hero"' in html and "cal-h1" not in html, url


def test_the_calendar_tab_does_not_build_the_team_panels_or_the_to_do_list(viewer, conn, monkeypatch):
    """None of it is drawn there, so none of it should be computed (it is the slow part of the home page)."""
    def boom(*a, **k):
        raise AssertionError("built something the Calendar tab never shows")
    for name in ("team_view_data", "home_tasks", "calendar_week_block"):
        monkeypatch.setattr(oc, name, boom)
    monkeypatch.setattr(st, "wellness_stats", boom)
    r = viewer.get("/?view=calendar")
    assert r.status_code == 200 and 'class="cal-bar"' in r.text


def test_links_on_the_tab_stay_on_the_home_page(viewer, conn):
    mk(conn, "Linked", 1)
    html = viewer.get("/?view=calendar&layout=month&month=2026-10&kind=meeting").text
    nav = [h for h in hrefs(html) if (h.startswith("/?") and h != "/?view=me") or h.startswith("/calendar?")]
    assert nav and all(h.startswith("/?view=calendar") for h in nav), [h for h in nav if not h.startswith("/?view=calendar")]
    assert 'action="/"' in html and 'name="view" value="calendar"' in html
    assert 'name="layout" value="month"' in html and 'name="month" value="2026-10"' in html
    assert "layout=month" in html and "kind=meeting" in html           # filters survive the links
    # ...while the Add button and an item's own page are the real calendar pages
    assert any(h.startswith("/calendar/new") for h in hrefs(html))


def test_agenda_and_month_both_render_on_the_tab(viewer, conn):
    mk(conn, "Trip", 1, end_date=(tz.today_local() + timedelta(days=3)).isoformat(), kind="travel")
    agenda = viewer.get("/?view=calendar").text
    assert "CALTB Trip" in agenda and "cal-day" in agenda and "Earlier" in agenda
    month = viewer.get("/?view=calendar&layout=month").text
    assert "cal-month" in month and "CALTB Trip" in month
    assert 'aria-current="true">Month' in month


def test_bad_input_falls_back_quietly(viewer):
    for q in ("day=nonsense", "layout=month&month=zzzz", "scope=galaxy", "kind=galaxy&unit=abc"):
        r = viewer.get(f"/?view=calendar&{q}")
        assert r.status_code == 200 and 'class="cal-bar"' in r.text, q


def test_scope_param_picks_the_pill(viewer):
    assert re.search(r'<option value="mine" selected>Mine only</option>', viewer.get("/?view=calendar&scope=mine").text)
    viewer.cookies.delete("cal_pref")                       # a plain visit would otherwise remember "mine"
    assert re.search(r'<option value="blend" selected>Mine \+ bureau-wide</option>', viewer.get("/?view=calendar").text)


def test_the_tab_never_shows_more_than_the_calendar_page(app_mod, viewer, conn):
    with in_the_directory(app_mod, "viewer@test.local", path="CALTB/D1/S1"):
        other = conn.execute("INSERT INTO org_unit(name, short_name, level, path) "
                             "VALUES ('o','o','section','CALTB/D9/S9')").lastrowid
        mine = conn.execute("SELECT id FROM org_unit WHERE path='CALTB/D1/S1'").fetchone()[0]
        mk(conn, "Mine unit", 1, audience="unit", owner_org_id=mine)
        mk(conn, "Other unit", 1, audience="unit", owner_org_id=other)
        conn.commit()
        for url in ("/?view=calendar&scope=bureau", "/calendar?scope=bureau"):
            html = viewer.get(url).text
            assert "CALTB Mine unit" in html and "CALTB Other unit" not in html, url
        conn.execute("DELETE FROM calendar_entry_revision WHERE entry_id IN (SELECT id FROM calendar_entry WHERE title LIKE 'CALTB %')")
        conn.execute("DELETE FROM calendar_entry WHERE title LIKE 'CALTB %'")
        conn.execute("DELETE FROM org_unit WHERE path='CALTB/D9/S9'")
        conn.commit()


def test_the_tab_opens_on_the_scope_of_the_tab_you_came_from(app_mod, viewer, conn):
    with in_the_directory(app_mod, "viewer@test.local", path="CALTB/D1/S1"):
        team = viewer.get("/").text
        me = viewer.get("/?view=me").text
        assert 'href="/?view=calendar&scope=section"' in team          # Team -> my team
        assert 'href="/?view=calendar&scope=blend"' in me              # Me -> mine + bureau-wide
        assert '>Team</a>' in team
        cal = viewer.get("/?view=calendar&scope=section").text
        assert re.search(r'<option value="section" selected>My section</option>', cal) and 'aria-current="true">Calendar</a>' in cal


def test_an_unlinked_account_has_me_and_calendar_but_no_team_tab(viewer):
    html = viewer.get("/").text
    assert '>Team</a>' not in html and 'href="/?view=calendar&scope=blend"' in html
    assert 'aria-current="true">Me</a>' in html


def test_the_tab_survives_the_calendar_failing(viewer, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("down")
    monkeypatch.setattr(calendar_routes, "build_calendar_page", boom)
    r = viewer.get("/?view=calendar")
    assert r.status_code == 200 and "couldn't be loaded" in r.text and 'aria-current="true">Calendar</a>' in r.text


def test_titles_are_escaped_on_the_tab(viewer, conn):
    mk(conn, "<img src=x onerror=alert(1)>", 1)
    assert "<img src=x" not in viewer.get("/?view=calendar").text


# ------------------------------------------------------------------ the task ---

def test_the_to_do_counts_todays_items_and_links_to_the_tab(viewer, conn):
    assert "things on the calendar today" not in viewer.get("/").text
    mk(conn, "Standup", 0, start_time="09:00")
    html = viewer.get("/").text
    assert "1 thing on the calendar today" in html and "09:00 CALTB Standup" in html
    assert 'href="/?view=calendar"' in html and "Open the calendar" in html
    mk(conn, "Second", 0); mk(conn, "Third", 0)
    html = viewer.get("/").text
    assert "3 things on the calendar today" in html and "+1 more" in html


def test_banners_holidays_and_other_days_do_not_count(world):                       # noqa: F811
    add(world, "Moratorium", 0, kind="banner", owner="T", audience="bureau")
    add(world, "Tomorrow only", 1, owner="T", audience="bureau")
    add(world, "Yesterday", -1, owner="T", audience="bureau")
    st.set_holiday(world["conn"], TODAY, "Holiday today", "special")
    assert oc._task_calendar_today(world["conn"], world["s1"], TODAY) is None
    add(world, "Real thing", 0, owner="T", audience="bureau")
    t = oc._task_calendar_today(world["conn"], world["s1"], TODAY)
    assert t["title"] == "1 thing on the calendar today" and t["tone"] == "info" and t["key"] == "calendar_today"


def test_the_task_is_your_items_plus_bureau_wide_not_the_whole_team(world):          # noqa: F811
    add(world, "Team only", 0, owner="T/D1/S1")                       # my section's, not mine
    add(world, "Mine", 0, owner="T/D1/S1", people=[world["s1"]])
    add(world, "Everyone", 0, owner="T", audience="bureau")
    t = oc._task_calendar_today(world["conn"], world["s1"], TODAY)
    assert t["title"] == "2 things on the calendar today" and "Team only" not in t["detail"]
    assert oc._task_calendar_today(world["conn"], world["s3"], TODAY)["title"] == "1 thing on the calendar today"


def test_task_order_and_one_failure_never_hides_the_rest(world, monkeypatch):         # noqa: F811
    add(world, "Today thing", 0, owner="T", audience="bureau")
    monkeypatch.setattr(oc, "_task_approvals", lambda *a: None)
    monkeypatch.setattr(oc, "_task_wellness", lambda *a: {"key": "w", "tone": "todo", "title": "Wellness", "icon": "x", "cta": "Go", "url": "/"})
    monkeypatch.setattr(oc, "_task_awa", lambda *a: {"key": "a", "tone": "done", "title": "AWA", "icon": "x", "cta": "Go", "url": "/"})
    monkeypatch.setattr(oc, "_task_office_today", lambda *a: None)
    monkeypatch.setattr(oc, "_task_activities", lambda *a: [])
    tasks = oc.home_tasks(world["conn"], world["s1"], TODAY)
    assert [t["key"] for t in tasks] == ["w", "calendar_today", "a"]            # to do, then for information, then done
    monkeypatch.setattr(oc, "_task_calendar_today", lambda *a: (_ for _ in ()).throw(RuntimeError("calendar down")))
    assert [t["key"] for t in oc.home_tasks(world["conn"], world["s1"], TODAY)] == ["w", "a"]
