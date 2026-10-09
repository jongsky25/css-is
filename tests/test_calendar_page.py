"""Office calendar agenda page (increment A3): /calendar is login-gated, honours
scope, is read-only, and renders what office_calendar.items_between returns.
Plus the pure agenda_days / scope_choices helpers."""
from __future__ import annotations
from datetime import date

import pytest

import office_calendar as oc
import storage as st
import tzutil as tz
from conftest import in_the_directory

DAY = "2026-10-05"           # a Monday


@pytest.fixture()
def conn(app_mod):
    c = st.connect(app_mod.DB)
    st.init_db(c)
    yield c
    ids = [r[0] for r in c.execute("SELECT id FROM calendar_entry WHERE title LIKE 'CALPG %'")]
    for i in ids:
        st.cal_delete(c, i)
    c.execute("DELETE FROM holiday WHERE name LIKE 'CALPG %'")
    c.commit()
    c.close()


def _entry(conn, title, day=DAY, **kw):
    kw.setdefault("audience", "bureau")
    return st.cal_create(conn, f"CALPG {title}", day, **kw)


# ------------------------------------------------------------------ access ---

def test_calendar_requires_login(client):
    r = client.get("/calendar", follow_redirects=False)
    assert r.status_code in (302, 303, 401)
    assert "Office calendar" not in r.text


@pytest.mark.parametrize("who", ["viewer", "encoder", "manager", "admin"])
def test_every_signed_in_role_can_open_it(request, who):
    c = request.getfixturevalue(who)
    r = c.get(f"/calendar?day={DAY}")
    assert r.status_code == 200 and "Office calendar" in r.text


def test_calendar_is_in_the_menu_for_everyone(viewer):
    assert 'href="/calendar"' in viewer.get("/").text


# ---------------------------------------------------------------- rendering ---

def test_agenda_shows_entries_holidays_and_multi_day_trips(viewer, conn):
    _entry(conn, "Strat Planning", start_time="09:00", end_time="12:00", venue="Room 4",
           tags=["PK"])
    _entry(conn, "TA Palawan", day="2026-10-06", end_date="2026-10-08", kind="travel")
    st.set_holiday(conn, date(2026, 10, 7), "CALPG Holiday", "special")
    html = viewer.get(f"/calendar?day={DAY}").text
    assert "CALPG Strat Planning" in html and "09:00–12:00" in html and "Room 4" in html
    assert "PK" in html
    assert html.count("CALPG TA Palawan") == 3          # one line per day it covers
    assert "day 2 of 3" in html
    assert "CALPG Holiday" in html and "Mon, Oct 5" in html


def test_status_flags_show_and_cancelled_entries_do_not(viewer, conn):
    _entry(conn, "Maybe", status="tentative")
    _entry(conn, "Later", status="postponed")
    gone = _entry(conn, "Gone")
    st.cal_cancel(conn, gone)
    html = viewer.get(f"/calendar?day={DAY}").text
    assert "CALPG Maybe" in html and "Tentative" in html and "Postponed" in html
    assert "CALPG Gone" not in html


def test_titles_are_escaped(viewer, conn):
    _entry(conn, "<script>alert(1)</script>")
    html = viewer.get(f"/calendar?day={DAY}").text
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


def test_window_is_two_weeks_and_navigation_links_move_by_two_weeks(viewer, conn):
    _entry(conn, "Inside", day="2026-10-18")
    _entry(conn, "Outside", day="2026-10-19")
    html = viewer.get(f"/calendar?day={DAY}").text
    assert "CALPG Inside" in html and "CALPG Outside" not in html
    assert "day=2026-09-21" in html and "day=2026-10-19" in html
    assert "Oct 5 – Oct 18, 2026" in html


def test_today_is_pinned_even_when_empty(viewer):
    html = viewer.get("/calendar").text
    assert "Today" in html and "Nothing scheduled today" in html


def test_bad_day_bounces_and_bad_scope_falls_back(viewer):
    r = viewer.get("/calendar?day=not-a-date", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/calendar"
    r = viewer.get(f"/calendar?day={DAY}&scope=galaxy")
    assert r.status_code == 200 and '<option value="blend" selected>Mine + bureau-wide</option>' in r.text


def test_it_is_read_only(viewer):
    assert viewer.post("/calendar", content="x=1").status_code in (404, 405)


def test_stylesheet_is_served(client):
    r = client.get("/static/css/calendar.css")
    assert r.status_code == 200 and "--cal-green" in r.text


# -------------------------------------------------------------------- scope ---

def test_unlinked_account_sees_bureau_items_only_and_is_offered_no_section_pill(viewer, conn):
    unit_entry = _entry(conn, "Unit only", audience="unit")
    _entry(conn, "For all")
    html = viewer.get(f"/calendar?day={DAY}&scope=bureau").text
    assert "CALPG For all" in html and "CALPG Unit only" not in html
    assert "My section" not in html and "My division" not in html
    assert unit_entry


def test_section_member_sees_their_unit_in_the_section_view(app_mod, viewer, conn):
    with in_the_directory(app_mod, "viewer@test.local", path="CALPG/D1/S1"):
        mine = conn.execute("SELECT id FROM org_unit WHERE path='CALPG/D1/S1'").fetchone()[0]
        other = conn.execute(
            "INSERT INTO org_unit(name, short_name, level, path) "
            "VALUES ('o','o','section','CALPG/D9/S9')").lastrowid
        _entry(conn, "Mine unit", audience="unit", owner_org_id=mine)
        _entry(conn, "Other unit", audience="unit", owner_org_id=other)
        conn.commit()
        html = viewer.get(f"/calendar?day={DAY}&scope=section").text
        assert "CALPG Mine unit" in html and "CALPG Other unit" not in html
        assert "My section" in html
        # the fixture's directory unit can only be removed once nothing points at it
        conn.execute("DELETE FROM calendar_entry_revision WHERE entry_id IN "
                     "(SELECT id FROM calendar_entry WHERE title LIKE 'CALPG %')")
        conn.execute("DELETE FROM calendar_entry WHERE title LIKE 'CALPG %'")
        conn.execute("DELETE FROM org_unit WHERE path='CALPG/D9/S9'")
        conn.commit()


# --------------------------------------------------------------- pure helpers ---

def _item(title, start, end=None, layer="entries"):
    return {"title": title, "start": start, "end": end or start, "layer": layer}


def test_agenda_days_groups_pins_today_and_tags_day_numbers():
    items = [_item("A", "2026-10-05"), _item("Trip", "2026-10-06", "2026-10-08"),
             _item("Hol", "2026-10-07", layer="holidays")]
    days = oc.agenda_days(items, date(2026, 10, 5), date(2026, 10, 18), date(2026, 10, 12))
    assert [d["iso"] for d in days] == ["2026-10-05", "2026-10-06", "2026-10-07",
                                        "2026-10-08", "2026-10-12"]
    assert [i["day_n"] for d in days for i in d["rows"] if i["title"] == "Trip"] == [1, 2, 3]
    assert days[2]["holidays"][0]["title"] == "Hol"
    assert days[-1]["is_today"] and days[-1]["rows"] == []
    assert days[0]["rows"][0]["day_n"] is None             # single day: no "day x of y"
    assert days[0]["label"] == "Mon, Oct 5"


def test_scope_choices_hide_pills_that_could_only_be_empty():
    none = {"section_path": None, "division_path": None}
    assert [c["key"] for c in oc.scope_choices(none)] == ["blend", "mine", "bureau"]
    full = {"section_path": "a/b", "division_path": "a"}
    assert [c["key"] for c in oc.scope_choices(full)] == [
        "blend", "mine", "section", "division", "bureau"]


def test_the_agenda_days_sit_in_one_grid_container_so_wide_screens_can_use_columns(viewer):
    html = viewer.get("/calendar").text
    assert html.count('<div class="cal-agenda">') == 1
    assert html.index('<div class="cal-agenda">') < html.index('class="cal-day') < html.index("cal-empty-hint")
