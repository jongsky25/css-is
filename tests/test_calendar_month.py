"""Office calendar month grid + filters (increment A5)."""
from __future__ import annotations
import re
from datetime import date

import pytest

import office_calendar as oc
import storage as st

TODAY = date(2026, 10, 9)


def item(title, start, end=None, *, layer="entries", kind="meeting", status="confirmed",
         tags=(), owner=None, time=None, tone="grey"):
    return {"title": title, "start": start, "end": end or start, "layer": layer, "kind": kind,
            "status": status, "tags": list(tags), "owner_org_id": owner, "start_time": time,
            "tone": tone, "owner_label": None, "url": "/x"}


# ------------------------------------------------------------------ pure grid ---

@pytest.mark.parametrize("y, m, first, last", [
    (2026, 10, date(2026, 9, 27), date(2026, 10, 31)),     # starts Thu, ends Sat
    (2026, 2, date(2026, 2, 1), date(2026, 2, 28)),        # exactly four whole weeks
    (2026, 11, date(2026, 11, 1), date(2026, 12, 5)),      # starts Sun, ends Mon
    (2026, 8, date(2026, 7, 26), date(2026, 9, 5)),        # six rows
])
def test_month_span_is_whole_sunday_to_saturday_weeks(y, m, first, last):
    assert oc.month_span(y, m) == (first, last)
    assert first.weekday() == 6 and last.weekday() == 5


def test_grid_shape_and_navigation_keys():
    g = oc.month_grid([], 2026, 10, TODAY)
    assert len(g["weeks"]) == 5 and all(len(w["days"]) == 7 for w in g["weeks"])
    assert (g["title"], g["prev"], g["next"]) == ("October 2026", "2026-09", "2026-11")
    assert oc.month_grid([], 2026, 12, TODAY)["next"] == "2027-01"
    assert oc.month_grid([], 2026, 1, TODAY)["prev"] == "2025-12"
    days = [d for w in g["weeks"] for d in w["days"]]
    assert [d["in_month"] for d in days[:5]] == [False] * 4 + [True]      # Sep 27-30 are padding
    assert sum(d["is_today"] for d in days) == 1


def test_multi_day_item_is_one_bar_per_week_cut_where_it_continues():
    trip = item("Trip", "2026-10-08", "2026-10-14")                       # Thu .. Wed
    g = oc.month_grid([trip], 2026, 10, TODAY)
    bars = [(n, b) for n, w in enumerate(g["weeks"]) for b in w["bars"]]
    assert [(n, b["col"], b["span"], b["left_cut"], b["right_cut"]) for n, b in bars] == [
        (1, 5, 3, False, True), (2, 1, 4, True, False)]


def test_overlapping_items_stack_in_lanes_and_others_share_a_lane():
    a, b = item("A", "2026-10-05", "2026-10-07"), item("B", "2026-10-06")
    c = item("C", "2026-10-08")
    bars = {x["item"]["title"]: x["lane"] for w in oc.month_grid([a, b, c], 2026, 10, TODAY)["weeks"]
            for x in w["bars"]}
    assert bars == {"A": 1, "B": 2, "C": 1}


def test_overflow_is_counted_per_day_never_dropped():
    many = [item(f"E{n}", "2026-10-06") for n in range(5)]
    wk = oc.month_grid(many, 2026, 10, TODAY)["weeks"][1]
    assert len(wk["bars"]) == 3 and wk["rows"] == 4
    assert [d["more"] for d in wk["days"]] == [0, 0, 2, 0, 0, 0, 0]
    # a long item hidden by lanes counts on every day it covers
    wide = many[:3] + [item("Wide", "2026-10-05", "2026-10-07")]
    wk = oc.month_grid(wide, 2026, 10, TODAY)["weeks"][1]
    assert [d["more"] for d in wk["days"]] == [0, 0, 1, 0, 0, 0, 0]


def test_holidays_label_their_day_and_are_not_bars():
    hol = item("Holiday", "2026-10-14", layer="holidays", kind="holiday")
    g = oc.month_grid([hol], 2026, 10, TODAY)
    assert all(not w["bars"] for w in g["weeks"])
    day = next(d for w in g["weeks"] for d in w["days"] if d["iso"] == "2026-10-14")
    assert day["holidays"][0]["title"] == "Holiday"


def test_items_outside_the_month_but_inside_the_grid_still_show():
    g = oc.month_grid([item("Edge", "2026-09-28")], 2026, 10, TODAY)
    assert [b["item"]["title"] for b in g["weeks"][0]["bars"]] == ["Edge"]


def test_timed_flag_only_for_single_day_timed_items():
    g = oc.month_grid([item("T", "2026-10-06", time="09:00"),
                       item("L", "2026-10-07", "2026-10-08", time="09:00")], 2026, 10, TODAY)
    assert {b["item"]["title"]: b["timed"] for b in g["weeks"][1]["bars"]} == {"T": True, "L": False}


# -------------------------------------------------------------------- filters ---

def test_filters_combine_and_never_drop_holidays():
    items = [item("PK trip", "2026-10-06", kind="travel", tags=["PK"], owner=1),
             item("PK meeting", "2026-10-06", tags=["PK"], owner=2),
             item("Plain trip", "2026-10-06", kind="travel", owner=1),
             item("Maybe", "2026-10-06", status="tentative", tags=["PK"], owner=1),
             item("Hol", "2026-10-06", layer="holidays", kind="holiday")]
    names = lambda f: sorted(i["title"] for i in oc.apply_filters(items, f))      # noqa: E731
    assert names(None) == names({}) == names({"kinds": None}) == sorted(i["title"] for i in items)
    assert names({"kinds": {"travel"}}) == ["Hol", "PK trip", "Plain trip"]
    assert names({"tags": {"PK"}}) == ["Hol", "Maybe", "PK meeting", "PK trip"]
    assert names({"kinds": {"travel"}, "tags": {"PK"}}) == ["Hol", "PK trip"]
    assert names({"owner_org_ids": {2}}) == ["Hol", "PK meeting"]
    assert names({"statuses": {"tentative"}, "owner_org_ids": {1}}) == ["Hol", "Maybe"]
    assert names({"tags": {"nope"}}) == ["Hol"]


# ------------------------------------------------------------------------ page ---

@pytest.fixture()
def conn(app_mod):
    c = st.connect(app_mod.DB)
    st.init_db(c)
    yield c
    for (i,) in c.execute("SELECT id FROM calendar_entry WHERE title LIKE 'CALMO %'").fetchall():
        st.cal_delete(c, i)
    c.execute("DELETE FROM holiday WHERE name LIKE 'CALMO %'")
    c.execute("DELETE FROM org_unit WHERE path LIKE 'CALMO%'")
    c.commit()
    c.close()


def make(conn, title, day, **kw):
    kw.setdefault("audience", "bureau")
    return st.cal_create(conn, f"CALMO {title}", day, **kw)


def test_month_view_renders_bars_across_weeks_with_cuts(viewer, conn):
    eid = make(conn, "Trip", "2026-10-08", end_date="2026-10-14", kind="travel")
    html = viewer.get("/calendar?view=month&month=2026-10").text
    assert "October 2026" in html and ">Sun<" in html and ">Sat<" in html
    assert html.count(f'href="/calendar/entries/{eid}"') == 2            # one bar in each week
    assert "cut-r" in html and "cut-l" in html


def test_month_view_marks_status_and_shows_times_and_holidays(viewer, conn):
    make(conn, "Maybe", "2026-10-06", status="tentative")
    make(conn, "Timed", "2026-10-07", start_time="13:30")
    st.set_holiday(conn, date(2026, 10, 14), "CALMO Holiday", "special")
    html = viewer.get("/calendar?view=month&month=2026-10").text
    assert "(tentative)" in html and "<b>13:30</b>" in html and "★ CALMO Holiday" in html


def test_plus_n_more_links_to_that_days_agenda(viewer, conn):
    for n in range(5):
        make(conn, f"Busy{n}", "2026-10-06")
    html = viewer.get("/calendar?view=month&month=2026-10").text
    assert "+2 more" in html and "day=2026-10-06" in html


def test_month_navigation_and_bad_input(viewer):
    html = viewer.get("/calendar?view=month&month=2026-12").text
    assert "December 2026" in html and "month=2026-11" in html and "month=2027-01" in html
    assert "Nov 2026" in html and "Jan 2027" in html
    r = viewer.get("/calendar?view=month&month=nonsense", follow_redirects=False)
    assert r.status_code == 303 and "view=month" in r.headers["location"]
    assert viewer.get("/calendar?view=sideways").status_code == 200       # unknown view -> agenda


def test_view_toggle_and_scope_pills_keep_the_month(viewer):
    html = viewer.get("/calendar?view=month&month=2026-10&scope=mine").text
    assert 'view=month' in html and 'month=2026-10' in html
    assert 'aria-current="true">Month' in html and "Agenda</a>" in html


def test_filters_narrow_month_and_agenda_and_keep_options(viewer, conn):
    make(conn, "Palawan", "2026-10-06", kind="travel", tags=["PK"])
    make(conn, "Huddle", "2026-10-06", kind="meeting", tags=["BHW"])
    st.set_holiday(conn, date(2026, 10, 7), "CALMO Holiday", "special")
    for url in ("/calendar?view=month&month=2026-10&kind=travel",
                "/calendar?day=2026-10-05&kind=travel"):
        html = viewer.get(url).text
        assert "CALMO Palawan" in html and "CALMO Huddle" not in html and "CALMO Holiday" in html
        assert "Clear filters" in html and "· filtered" in html
        assert '<option value="BHW"' in html and '<option value="PK"' in html   # menus keep every option
    html = viewer.get("/calendar?day=2026-10-05&kind=travel&tag=BHW").text
    assert "CALMO Palawan" not in html and "CALMO Huddle" not in html


def test_status_and_tag_filters(viewer, conn):
    make(conn, "Maybe", "2026-10-06", status="tentative", tags=["PK"])
    make(conn, "Sure", "2026-10-06", tags=["PK"])
    html = viewer.get("/calendar?day=2026-10-05&status=tentative&tag=PK").text
    assert "CALMO Maybe" in html and "CALMO Sure" not in html


def test_unit_chips_filter_and_toggle_off(viewer, conn):
    a = conn.execute("INSERT INTO org_unit(name, short_name, level, path) "
                     "VALUES ('Alpha','CALMO-A','section','CALMO/A')").lastrowid
    b = conn.execute("INSERT INTO org_unit(name, short_name, level, path) "
                     "VALUES ('Beta','CALMO-B','section','CALMO/B')").lastrowid
    conn.commit()
    make(conn, "From A", "2026-10-06", owner_org_id=a)
    make(conn, "From B", "2026-10-06", owner_org_id=b)
    html = viewer.get(f"/calendar?day=2026-10-05&unit={a}").text
    assert "CALMO From A" in html and "CALMO From B" not in html
    assert "CALMO-A" in html and "CALMO-B" in html                    # both chips stay
    chips = html.split('class="cal-units"')[1].split("</p>")[0]
    on = chips.split("CALMO-A")[0].rsplit("<a ", 1)[1]
    assert 'aria-current="true"' in chips.split("CALMO-B")[0] and f"unit={a}" not in on   # active chip links to "off"
    both = viewer.get("/calendar?day=2026-10-05").text
    assert "CALMO From A" in both and "CALMO From B" in both


def test_bad_filter_values_are_ignored_not_errors(viewer, conn):
    make(conn, "Fine", "2026-10-06")
    html = viewer.get("/calendar?day=2026-10-05&kind=galaxy&status=cancelled&unit=abc").text
    assert "CALMO Fine" in html and "Clear filters" not in html        # nothing valid was chosen


def test_a_free_text_tag_is_escaped_where_it_is_echoed(viewer, conn):
    make(conn, "Fine", "2026-10-06")
    html = viewer.get("/calendar?day=2026-10-05&tag=%3Cscript%3Ealert(1)%3C/script%3E").text
    assert "<script>alert(1)</script>" not in html and "CALMO Fine" not in html


def test_filters_survive_month_navigation_links(viewer):
    html = viewer.get("/calendar?view=month&month=2026-10&kind=travel&tag=PK").text
    assert "month=2026-09" in html and "kind=travel" in html and "tag=PK" in html


# ------------------------------------- the compact month for phones (CALENDAR_UX_PLAN Phase 2) ---

def day_of(g, iso):
    return next(d for w in g["weeks"] for d in w["days"] if d["iso"] == iso)


def test_each_day_counts_what_touches_it_and_lists_up_to_four_distinct_unit_colours():
    trip = item("Trip", "2026-10-08", "2026-10-10", tone="cyan")
    a, b = item("A", "2026-10-09", tone="green"), item("B", "2026-10-09", tone="green")
    g = oc.month_grid([trip, a, b], 2026, 10, TODAY)
    assert (day_of(g, "2026-10-08")["n"], day_of(g, "2026-10-08")["tones"]) == (1, ["cyan"])
    d9 = day_of(g, "2026-10-09")
    assert d9["n"] == 3 and d9["tones"] == ["cyan", "green"]                  # one dot per unit, not per item
    assert day_of(g, "2026-10-11")["n"] == 0 and day_of(g, "2026-10-11")["tones"] == []


def test_a_day_with_more_than_four_units_shows_four_dots_and_the_full_count():
    tones = ["green", "yellow", "magenta", "orange", "cyan", "blue"]
    many = [item(f"E{n}", "2026-10-06", tone=t) for n, t in enumerate(tones)]
    d = day_of(oc.month_grid(many, 2026, 10, TODAY, max_lanes=3), "2026-10-06")
    assert len(d["tones"]) <= 4 and d["n"] == 6                                # 3 bars + 3 counted as "more"


def test_items_hidden_by_the_lane_limit_still_count_on_their_day():
    many = [item(f"E{n}", "2026-10-06") for n in range(5)]
    assert day_of(oc.month_grid(many, 2026, 10, TODAY), "2026-10-06")["n"] == 5


def test_the_page_has_both_the_full_month_and_the_compact_one_and_a_day_opens_its_agenda(viewer):
    html = viewer.get("/calendar?view=month&month=2026-10").text
    assert 'class="cal-month"' in html and 'class="cal-mgrid"' in html and "needs a wider screen" not in html
    cell = html.split('class="cal-mday')[1].split("</a>")[0]
    assert 'role="gridcell"' in cell and "view=agenda" not in cell
    assert re.search(r'href="/calendar\?[^"]*day=2026-09-27', html.split('class="cal-mgrid"')[1])   # first cell, links to that day
    assert 'aria-label="Sunday, September 27: 0 items"' in html


def test_every_compact_day_names_itself_for_a_screen_reader(viewer):
    html = viewer.get("/calendar?view=month&month=2026-10").text.split('class="cal-mgrid"')[1]
    cells = html.count('class="cal-mday')
    assert cells >= 28 and html.count('aria-label="') >= cells
