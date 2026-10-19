"""The "Coming up" card on the landing page (office calendar C1): the next seven days
from the same calendar /calendar shows, for the Team and Me tabs."""
from __future__ import annotations
from datetime import date, timedelta

import pytest

import office_calendar as ocal
import office_connect as oc
import storage as st
import tzutil as tz

TODAY = date(2026, 10, 9)                      # a Friday


def iso(n):
    return (TODAY + timedelta(days=n)).isoformat()


@pytest.fixture()
def world(tmp_path):
    conn = st.connect(str(tmp_path / "home.db")); st.init_db(conn)
    unit = {}
    for path, level in (("T", "bureau"), ("T/D1", "division"), ("T/D2", "division"),
                        ("T/D1/S1", "section"), ("T/D1/S2", "section"), ("T/D2/S3", "section"),
                        ("T/OD", "office")):
        unit[path] = conn.execute("INSERT INTO org_unit(name, short_name, level, path) VALUES (?,?,?,?)",
                                  (path, path.rsplit("/", 1)[-1], level, path)).lastrowid

    def acct(label, path=None, designation=None):
        rp = conn.execute("INSERT INTO resource_person(name, is_internal, org_unit_id, designation) "
                          "VALUES (?,1,?,?)", (f"P {label}", unit.get(path), designation)).lastrowid if path else None
        uid = st.create_admin_user(conn, f"{label}@test.local", "x", "y", "viewer", rp_id=rp)
        return {"id": uid, "username": f"{label}@test.local", "role": "viewer"}

    w = {"conn": conn, "unit": unit, "s1": acct("s1", "T/D1/S1"), "s1b": acct("s1b", "T/D1/S1"),
         "d1": acct("d1", "T/D1", "Division Chief"),
         "s3": acct("s3", "T/D2/S3"), "dir": acct("dir", "T/OD", "Director"), "nobody": acct("nobody")}
    return w


def add(w, title, day=0, *, owner="T/D1/S1", audience="unit", end=None, people=(), **kw):
    return st.cal_create(w["conn"], title, iso(day), end_date=iso(end) if end is not None else None,
                         owner_org_id=w["unit"].get(owner), audience=audience,
                         people=[p if isinstance(p, tuple) else p["id"] for p in people], **kw)


def block(w, who, view="team"):
    return oc.calendar_week_block(w["conn"], w[who], view=view, today=TODAY)


def titles(b):
    return [i["title"] for i in b["items"]]


# ----------------------------------------------------------------- scope ---

def test_team_follows_the_directory_and_me_is_yours_plus_bureau_wide(world):
    add(world, "S1 huddle")                                    # S1's own
    add(world, "S3 huddle", owner="T/D2/S3")
    add(world, "All hands", owner="T", audience="bureau")
    add(world, "My thing", owner="T/D2/S3", people=[world["s1"]])
    assert block(world, "s1")["scope"] == "section" and block(world, "s1", "me")["scope"] == "blend"
    # Team is owned by my unit; the calendar's section scope also includes bureau-wide items.
    assert titles(block(world, "s1")) == ["S1 huddle"]
    assert sorted(titles(block(world, "s1", "me"))) == ["All hands", "My thing"]
    assert sorted(titles(block(world, "s3"))) == ["My thing", "S3 huddle"]
    assert sorted(titles(block(world, "d1"))) == ["S1 huddle"]
    b = block(world, "dir")
    assert b["scope"] == "bureau" and sorted(titles(b)) == ["All hands", "My thing", "S1 huddle", "S3 huddle"]


def test_an_unlinked_account_gets_the_personal_scope_whichever_tab(world):
    add(world, "Unit thing"); add(world, "All hands", owner="T", audience="bureau")
    for view in ("team", "me"):
        b = block(world, "nobody", view)
        assert b["scope"] == "blend" and titles(b) == ["All hands"]


def test_team_card_keeps_its_own_bureau_wide_item_and_excludes_other_sections_trips(world):
    add(world, "S1 announcement", audience="bureau")
    add(world, "S2 announcement", owner="T/D1/S2", audience="bureau")
    add(world, "S2 trip", owner="T/D1/S2", audience="bureau", kind="travel",
        people=[(world["s1"]["id"], "travel")])
    team = block(world, "s1")
    assert titles(team) == ["S1 announcement"]
    assert team["away"] == []
    assert "S2 announcement" in titles(block(world, "s1", "me"))


def test_joint_item_appears_for_each_involved_section(world):
    add(world, "Joint visit", owner="T/D1/S1", extra_org_ids=[world["unit"]["T/D2/S3"]])
    add(world, "S2 only", owner="T/D1/S2", audience="bureau")
    assert titles(block(world, "s1")) == ["Joint visit"]
    assert titles(block(world, "s3")) == ["Joint visit"]
    assert set(titles(block(world, "d1"))) == {"Joint visit", "S2 only"}


@pytest.mark.parametrize("who, view", [("s1", "team"), ("s1", "me"), ("s3", "team"), ("s3", "me"), ("dir", "team"),
                                       ("nobody", "team"), ("nobody", "me")])
def test_the_card_never_shows_more_than_the_calendar_page_would(world, who, view):
    for n, (title, owner, aud) in enumerate([("A", "T/D1/S1", "unit"), ("B", "T/D2/S3", "unit"),
                                             ("C", "T", "bureau"), ("D", None, "unit"),
                                             ("E", "T/D1/S2", "unit")]):
        add(world, title, n, owner=owner, audience=aud)
    add(world, "Private", 1, owner="T/D1/S1", audience="people", people=[world["s3"]])
    b = block(world, who, view)
    page = ocal.items_between(world["conn"], world[who], TODAY, TODAY + timedelta(days=6), scope=b["scope"])
    assert set(titles(b)).issubset({i["title"] for i in page})
    assert ("Private" in titles(b)) == (who == "s3" and view == "me")       # only the person it names, on their Me tab


# ---------------------------------------------------------------- window ---

def test_the_window_is_today_through_six_days_ahead(world):
    add(world, "Yesterday", -1); add(world, "Today", 0); add(world, "Day six", 6)
    add(world, "Day seven", 7); add(world, "Trip under way", -3, end=2)
    b = block(world, "s1")
    assert titles(b) == ["Trip under way", "Today", "Day six"]            # the trip began on day -3: sorted by its start
    assert b["range"] == "Oct 9–15"


def test_labels_times_dates_and_status(world):
    add(world, "Now", 0, start_time="09:00", end_time="10:30")
    add(world, "Soon", 1, status="tentative", venue="Room 4")
    add(world, "Later", 3)
    add(world, "Trip under way", -2, end=3, kind="travel")
    by = {i["title"]: i for i in block(world, "s1")["items"]}
    assert (by["Now"]["when"], by["Now"]["time"], by["Now"]["is_today"]) == ("Today", "09:00–10:30", True)
    assert (by["Soon"]["when"], by["Soon"]["status"], by["Soon"]["venue"]) == ("Tomorrow", "tentative", "Room 4")
    assert by["Later"]["when"] == "Mon, Oct 12" and by["Later"]["dates"] == ""
    assert (by["Trip under way"]["when"], by["Trip under way"]["dates"]) == ("Today", "Oct 7–12")


def test_at_most_five_items_with_a_count_of_the_rest_and_no_cancelled_ones(world):
    for n in range(8):
        add(world, f"Item {n}", n % 7)
    gone = add(world, "Cancelled", 0); st.cal_cancel(world["conn"], gone)
    b = block(world, "s1")
    assert len(b["items"]) == 5 and b["n_more"] == 3 and b["n_total"] == 8 and "Cancelled" not in titles(b)


def test_holidays_are_listed_separately_and_do_not_count_as_items(world):
    st.set_holiday(world["conn"], TODAY + timedelta(days=2), "Special day", "special")
    add(world, "Only item", 1)
    b = block(world, "s1")
    assert b["holidays"] == [{"title": "Special day", "when": "Sun, Oct 11"}] and titles(b) == ["Only item"]
    assert b["n_total"] == 1


def test_an_empty_week_is_an_empty_list_not_an_error(world):
    b = block(world, "s1")
    assert b["items"] == [] and b["away"] == [] and b["n_more"] == 0 and b["holidays"] == []
    assert b["add_url"] == "/calendar/new?day=2026-10-09" and b["calendar_url"] == "/calendar?scope=section"


# ------------------------------------------------------------------ away ---

def test_who_is_away_comes_from_trips_with_people_on_them(world):
    s1, s1b = world["s1"], world["s1b"]
    add(world, "TA Palawan", 1, end=3, kind="travel", people=[(s1["id"], "travel")])
    add(world, "Field visit", 2, kind="travel", people=[(s1["id"], "travel"), (s1b["id"], "travel")])
    add(world, "A meeting they attend", 1, people=[(s1b["id"], "attending")])
    add(world, "Maybe trip", 1, kind="travel", status="tentative", people=[(world["s3"]["id"], "travel")])
    add(world, "Trip nobody is on", 1, kind="travel")
    away = block(world, "s1")["away"]
    assert [a["name"] for a in away] == ["P s1", "P s1b"]
    assert [t["title"] for t in away[0]["trips"]] == ["TA Palawan", "Field visit"]     # one chip per person
    assert away[0]["trips"][0]["dates"] == "Oct 10–12" and away[1]["trips"][0]["dates"] == "Oct 11"
    assert away[0]["initials"] == "PS"


def test_the_away_strip_respects_scope_and_is_capped(world):
    for n in range(9):
        a = st.create_admin_user(world["conn"], f"away{n}@test.local", "x", "y", "viewer")
        add(world, f"Trip {n}", 1, kind="travel", audience="bureau", owner="T/D2/S3", people=[(a, "travel")])
    b = block(world, "s3")
    assert len(b["away"]) == 6 and b["n_away_more"] == 3
    add(world, "S1 only trip", 2, kind="travel", people=[(world["s1"]["id"], "travel")])
    assert "P s1" not in [a["name"] for a in block(world, "s3")["away"]]        # s3 may not see that entry


# ------------------------------------------------------------- the page ---

def test_home_shows_the_card_on_both_tabs_and_links_to_the_calendar(app_mod, admin, viewer):
    conn = st.connect(app_mod.DB); st.init_db(conn)
    today = tz.today_local()
    eid = st.cal_create(conn, "CALHM Staff huddle", (today + timedelta(days=1)).isoformat(), audience="bureau",
                        start_time="09:00")
    try:
        for client in (admin, viewer):
            for url in ("/", "/?view=me"):
                html = client.get(url).text
                assert "Coming up" in html and "CALHM Staff huddle" in html, (url,)
                assert f'href="/calendar/entries/{eid}"' in html and "Open the calendar" in html
                assert "Tomorrow" in html and "09:00" in html
    finally:
        st.cal_delete(conn, eid); conn.close()


def test_home_card_empty_state_and_escaping(app_mod, viewer):
    conn = st.connect(app_mod.DB); st.init_db(conn)
    today = tz.today_local()
    empty = viewer.get("/").text
    assert "CALHM" not in empty
    eid = st.cal_create(conn, "CALHM <b>bold</b>", today.isoformat(), audience="bureau")
    try:
        html = viewer.get("/").text
        assert "<b>bold</b>" not in html and "&lt;b&gt;bold&lt;/b&gt;" in html
    finally:
        st.cal_delete(conn, eid); conn.close()
    assert "Coming up" in empty                      # the card is always there; with nothing on, it says so


def test_home_still_renders_when_the_card_fails(viewer, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("calendar down")
    monkeypatch.setattr(oc, "calendar_week_block", boom)
    r = viewer.get("/")
    assert r.status_code == 200 and "Coming up" not in r.text and "Hi" in r.text
