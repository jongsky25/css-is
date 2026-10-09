"""The Timeline layout and the quick-add sheet (office calendar H2)."""
from __future__ import annotations
from datetime import date, timedelta
from urllib.parse import urlencode

import pytest

import office_calendar as oc
import storage as st
import tzutil as tz
from conftest import in_the_directory
from test_calendar_home import world                                  # noqa: F401  (throwaway org + accounts)

FORM = {"Content-Type": "application/x-www-form-urlencoded"}
MON = date(2026, 10, 12)


def tl_for(w, who="s1", start=MON, layers=("entries", "activities", "leave")):
    items = oc.items_between(w["conn"], w[who], start, start + timedelta(days=27), scope="bureau", layers=list(layers))
    return oc.timeline(w["conn"], w[who], start, items, date(2026, 10, 14))


# ----------------------------------------------------------- the model ---

def test_four_weeks_of_days_with_weekends_and_holidays_marked(world):                          # noqa: F811
    c = world["conn"]
    c.execute("INSERT OR REPLACE INTO holiday(day, name, kind) VALUES ('2026-10-20', 'Foundation Day', 'special')"); c.commit()
    tl = tl_for(world)
    assert tl["ncols"] == 28 and len(tl["days"]) == 28 and len(tl["weeks"]) == 4
    assert [d["weekend"] for d in tl["days"][:7]] == [False] * 5 + [True, True]
    assert tl["days"][0]["iso"] == "2026-10-12" and tl["days"][2]["is_today"] and not tl["days"][0]["is_today"]
    assert next(d for d in tl["days"] if d["iso"] == "2026-10-20")["holiday"] == "Foundation Day"
    assert tl["weeks"][0]["label"] == "Oct 12–18" and tl["weeks"][3]["label"] == "Nov 2–8"
    assert tl["prev"] == "2026-09-14" and tl["next"] == "2026-11-09"
    assert tl["label"] == "Oct 12 – Nov 8, 2026"


def test_each_person_has_a_row_and_their_items_are_bars(world):                                 # noqa: F811
    c = world["conn"]
    st.cal_create(c, "Palawan trip", "2026-10-14", end_date="2026-10-16", kind="travel", audience="bureau",
                  people=[(world["s1"]["id"], "travel")], by="x@x")
    st.cal_create(c, "Training", "2026-10-26", audience="bureau", people=[(world["s1b"]["id"], "attending")], by="x@x")
    tl = tl_for(world)
    by = {p["user_id"]: p for sec in tl["sections"] for p in sec["people"]}
    trip = by[world["s1"]["id"]]["bars"][0]
    assert (trip["item"]["title"], trip["col"], trip["span"]) == ("Palawan trip", 3, 3)           # Wed-Fri of week 1
    assert [b["item"]["title"] for b in by[world["s1b"]["id"]]["bars"]] == ["Training"]
    assert by[world["s1b"]["id"]]["bars"][0]["col"] == 15                                         # Monday of week 3


def test_a_bar_that_runs_off_either_end_is_cut_not_dropped(world):                              # noqa: F811
    st.cal_create(world["conn"], "Long", "2026-10-01", end_date="2026-12-01", audience="bureau",
                  people=[(world["s1"]["id"], "attending")], by="x@x")
    bar = tl_for(world)["sections"][0]["people"][0]["bars"][0]
    assert bar["left_cut"] and bar["right_cut"] and (bar["col"], bar["span"]) == (1, 28)


def test_reported_leave_is_a_bar_without_a_reason(world):                                       # noqa: F811
    c = world["conn"]
    c.execute("INSERT INTO whereabouts(user_id, day, status, note, updated_at) VALUES (?,?,?,?,?)",
              (world["s1b"]["id"], "2026-10-21", "leave", "secret reason", "x")); c.commit()
    tl = tl_for(world)
    bars = [b for sec in tl["sections"] for p in sec["people"] for b in p["bars"] if b["item"]["kind"] == "leave"]
    assert len(bars) == 1 and "on leave" in bars[0]["item"]["title"] and "secret reason" not in repr(tl)


def test_an_item_naming_nobody_in_the_team_sits_in_the_band(world):                             # noqa: F811
    st.cal_create(world["conn"], "All-hands", "2026-10-15", audience="bureau", by="x@x")
    tl = tl_for(world)
    assert tl["has_band"] and [b["item"]["title"] for b in tl["band"]["bars"]] == ["All-hands"]


def test_overflow_is_counted_not_dropped(world):                                                # noqa: F811
    for i in range(5):
        st.cal_create(world["conn"], f"Same day {i}", "2026-10-14", audience="bureau",
                      people=[(world["s1"]["id"], "attending")], by="x@x")
    mine = [p for sec in tl_for(world)["sections"] for p in sec["people"] if p["user_id"] == world["s1"]["id"]][0]
    assert len(mine["bars"]) == oc.TIMELINE_LANES and mine["more"][2] == 2 and mine["rows"] == oc.TIMELINE_LANES + 1


def test_the_team_is_the_directory_s_and_an_unlinked_account_gets_none(world):                  # noqa: F811
    assert tl_for(world, "nobody")["kind"] == "none" and tl_for(world, "nobody")["n_people"] == 0
    assert tl_for(world, "s3")["n_people"] >= 1
    s1_team = {p["user_id"] for sec in tl_for(world, "s1")["sections"] for p in sec["people"]}
    assert world["s3"]["id"] not in s1_team


# ------------------------------------------------------------------- pages ---

def test_the_timeline_page_renders_with_its_views_and_sheet(app_mod, viewer):
    with in_the_directory(app_mod, "viewer@test.local", path="CALTL/D1/S1"):
        html = viewer.get("/calendar?view=timeline&day=2026-10-12").text
        assert 'class="cal-timeline"' in html and 'role="table"' in html and "Oct 12 – Nov 8, 2026" in html
        assert 'aria-current="true">Timeline</a>' in html and "← Earlier" in html and "Later →" in html
        assert 'id="cal-quick"' in html and "/static/js/calendar.js" in html and 'action="/calendar/new"' in html
        assert 'name="next"' in html and "Whose calendar" not in html                  # team layouts have no scope pills
        assert viewer.get("/calendar?view=timeline&day=nonsense", follow_redirects=False).status_code == 303


def test_the_timeline_follows_the_filters(app_mod, viewer):
    with in_the_directory(app_mod, "viewer@test.local", path="CALTL/D1/S1"):
        uid = st.get_admin_user(st.connect(app_mod.DB), "viewer@test.local")["id"]
        c = st.connect(app_mod.DB)
        e = st.cal_create(c, "CALTL Retreat", "2026-10-14", kind="meeting", audience="bureau", people=[(uid, "attending")], by="x@x")
        try:
            assert "CALTL Retreat" in viewer.get("/calendar?view=timeline&day=2026-10-12").text
            assert "CALTL Retreat" not in viewer.get("/calendar?view=timeline&day=2026-10-12&kind=training").text
        finally:
            st.cal_delete(c, e); c.close()


def test_the_home_calendar_tab_offers_the_timeline_and_the_sheet(app_mod, viewer):
    with in_the_directory(app_mod, "viewer@test.local", path="CALTL/D1/S1"):
        html = viewer.get("/?view=calendar&layout=timeline").text
        assert 'class="cal-timeline"' in html and 'id="cal-quick"' in html
        assert "Timeline</a>" in viewer.get("/?view=calendar").text


# ----------------------------------------------------------------- quick add ---

@pytest.fixture()
def made(app_mod, viewer):
    c = st.connect(app_mod.DB); st.init_db(c)
    yield c
    for (i,) in c.execute("SELECT id FROM calendar_entry WHERE title LIKE 'QUICK %'").fetchall():
        st.cal_delete(c, i)
    c.close()


def quick(client, **over):
    base = {"title": "QUICK Training", "kind": "training", "status": "confirmed", "repeat": "none", "start_date": "2026-10-20",
            "audience": "people", "owner_org_id": "", "next": "/calendar?scope=mine&view=timeline&day=2026-10-12"}
    return client.post("/calendar/new", content=urlencode({**base, **over}), headers=FORM, follow_redirects=False)


def test_quick_add_creates_the_item_and_returns_to_the_page_with_a_message(app_mod, viewer, made):
    uid = st.get_admin_user(made, "viewer@test.local")["id"]
    r = quick(viewer, people=str(uid))
    assert r.status_code == 303
    loc = r.headers["location"]
    assert loc.startswith("/calendar?scope=mine&view=timeline&day=2026-10-12") and "ok=Added" in loc
    e = made.execute("SELECT id, kind, audience, created_by FROM calendar_entry WHERE title='QUICK Training'").fetchone()
    assert e[1:] == ("training", "people", "viewer@test.local")
    assert made.execute("SELECT user_id FROM calendar_entry_person WHERE entry_id=?", (e[0],)).fetchall() == [(uid,)]
    assert "Added to the calendar." in viewer.get(loc).text


def test_the_message_is_escaped_and_never_repeats(app_mod, viewer):
    html = viewer.get("/calendar?ok=%3Cscript%3Ealert(1)%3C/script%3E").text
    assert "<script>alert(1)" not in html and "&lt;script&gt;" in html


@pytest.mark.parametrize("bad", ["//evil.example/x", "https://evil.example/", "/admin/users", "/calendar?x=1\\evil",
                                 "javascript:alert(1)", "/calendarevil", "", "/calendar?x=//evil.example"])
def test_a_return_address_that_is_not_a_calendar_page_is_ignored(app_mod, viewer, made, bad):
    uid = st.get_admin_user(made, "viewer@test.local")["id"]
    r = quick(viewer, people=str(uid), next=bad)
    assert r.status_code == 303 and r.headers["location"].startswith("/calendar/entries/")


def test_the_home_tab_is_a_valid_return_address(app_mod, viewer, made):
    uid = st.get_admin_user(made, "viewer@test.local")["id"]
    r = quick(viewer, people=str(uid), next="/?view=calendar&scope=mine")
    assert r.headers["location"].startswith("/?view=calendar&scope=mine") and "ok=" in r.headers["location"]


def test_every_rule_of_the_ordinary_route_still_applies(app_mod, viewer, made):
    r = quick(viewer)                                                               # "only the people on it" with nobody on it
    assert r.status_code == 400 and "who this is for" in r.text
    assert made.execute("SELECT COUNT(*) FROM calendar_entry WHERE title='QUICK Training'").fetchone()[0] == 0
    assert quick(viewer, start_date="nope", people="1").status_code == 400


def test_the_sheet_offers_my_section_only_when_there_is_one(app_mod, viewer):
    with in_the_directory(app_mod, "viewer@test.local", path="CALTL/D1/S1"):
        assert "Everyone in my section" in viewer.get("/calendar").text
    html = viewer.get("/calendar").text
    assert "Everyone in my section" not in html and 'value="people" selected' in html


# ------------------------------------------------------------------ the JS ---

def test_the_script_is_served_and_builds_the_page_without_innerhtml(app_mod, client):
    r = client.get("/static/js/calendar.js")
    assert r.status_code == 200 and "showModal" in r.text and "data-quick" in r.text
    assert "innerHTML" not in r.text and "eval(" not in r.text and "document.write" not in r.text
