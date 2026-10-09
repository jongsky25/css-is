"""The Week layout, people x days (office calendar C3)."""
from __future__ import annotations
from datetime import date, timedelta

import pytest

import office_calendar as ocal
import storage as st
import tzutil as tz
from conftest import in_the_directory
from test_calendar_home import world                                # noqa: F401  (throwaway org with accounts)

MON = date(2026, 10, 12)


def iso(n):
    return (MON + timedelta(days=n)).isoformat()


@pytest.fixture()
def w(world):                                                        # noqa: F811
    for who in ("s1", "s1b", "s3", "dir"):
        world[who]["_name"] = f"P {who}"
    world["conn"].execute("UPDATE resource_person SET is_internal=1")
    world["conn"].commit()
    return world


def add(w, title, d0, d1=None, *, owner="T/D1/S1", audience="unit", people=(), **kw):
    return st.cal_create(w["conn"], title, iso(d0), end_date=iso(d1) if d1 is not None else None,
                         owner_org_id=w["unit"].get(owner), audience=audience,
                         people=[p if isinstance(p, tuple) else p["id"] for p in people], **kw)


def grid(w, who):
    items = ocal.items_between(w["conn"], w[who], MON, MON + timedelta(days=4), scope="bureau")
    return ocal.people_week(w["conn"], w[who], MON, items)


def rows(g):
    return {p["name"]: p for sec in g["sections"] for p in sec["people"]}


def titles(row):
    return [b["item"]["title"] for b in row["bars"]]


# ------------------------------------------------------------------ rows ---

def test_rows_are_the_viewers_team_grouped_by_section(w):
    g = grid(w, "s1")
    assert g["kind"] == "unit" and [s["section"] for s in g["sections"]] == ["S1"]
    assert sorted(rows(g)) == ["P s1", "P s1b"] and g["n_people"] == 2
    assert [d["iso"] for d in g["days"]] == [iso(i) for i in range(5)]
    assert all(len(p["cells"]) == 5 for p in rows(g).values())


def test_a_bureau_wide_viewer_sees_every_section(w):
    g = grid(w, "dir")
    assert g["kind"] == "bureau" and {s["section"] for s in g["sections"]} >= {"S1", "S3"}
    assert {"P s1", "P s1b", "P s3"} <= set(rows(g))


def test_an_unlinked_account_gets_no_team_not_everyone(w):
    g = grid(w, "nobody")
    assert g["kind"] == "none" and g["sections"] == [] and g["n_people"] == 0


# ------------------------------------------------------------------ bars ---

def test_an_item_lands_on_the_row_of_each_person_on_it(w):
    add(w, "TA Palawan", 1, 3, kind="travel", people=[(w["s1"]["id"], "travel"), (w["s1b"]["id"], "travel")])
    r = rows(grid(w, "s1"))
    for name in ("P s1", "P s1b"):
        (b,) = r[name]["bars"]
        assert (b["item"]["title"], b["col"], b["span"], b["lane"]) == ("TA Palawan", 2, 3, 1)
    assert not grid(w, "s1")["has_band"]


def test_a_trip_running_into_the_weekend_is_cut_at_friday(w):
    add(w, "Long trip", 3, 8, people=[w["s1"]])                   # Thu .. next Tue
    (b,) = rows(grid(w, "s1"))["P s1"]["bars"]
    assert (b["col"], b["span"], b["right_cut"], b["left_cut"]) == (4, 2, True, False)


def test_a_trip_that_began_earlier_is_cut_on_the_left(w):
    add(w, "Under way", -4, 1, people=[w["s1"]])
    (b,) = rows(grid(w, "s1"))["P s1"]["bars"]
    assert (b["col"], b["span"], b["left_cut"], b["right_cut"]) == (1, 2, True, False)


def test_weekend_only_and_other_week_items_are_not_shown(w):
    add(w, "Saturday thing", 5, people=[w["s1"]])
    add(w, "Next week", 8, people=[w["s1"]])
    g = grid(w, "s1")
    assert titles(rows(g)["P s1"]) == [] and not g["has_band"]


def test_items_naming_nobody_in_the_team_go_in_the_band(w):
    add(w, "Whole unit", 0, 1, owner="T/D1/S1")                                          # nobody named
    add(w, "Bureau all-hands", 2, owner="T", audience="bureau")
    add(w, "Outside person", 3, owner="T", audience="bureau", people=[w["s3"]])          # not in S1's team
    g = grid(w, "s1")
    assert g["has_band"]
    assert sorted(b["item"]["title"] for b in g["band"]["bars"]) == ["Bureau all-hands", "Outside person", "Whole unit"]
    assert all(titles(p) == [] for p in rows(g).values())


def test_a_person_in_the_team_takes_it_off_the_band(w):
    add(w, "Mixed", 0, owner="T", audience="bureau", people=[w["s1"], w["s3"]])
    g = grid(w, "s1")
    assert titles(rows(g)["P s1"]) == ["Mixed"] and not g["has_band"]


def test_what_the_viewer_may_not_see_is_not_drawn(w):
    add(w, "Private", 0, audience="people", people=[w["s1"]], by="someone-else@test.local")
    assert titles(rows(grid(w, "s1"))["P s1"]) == ["Private"]            # s1 is named
    g = grid(w, "s1b")                                                    # same team, not named
    assert titles(rows(g)["P s1"]) == [] and not g["has_band"]
    assert titles(rows(grid(w, "dir"))["P s1"]) == []                      # not even the Director


def test_overlapping_items_stack_and_the_overflow_is_counted(w):
    for n in range(5):
        add(w, f"Busy {n}", 1, people=[w["s1"]])
    row = rows(grid(w, "s1"))["P s1"]
    assert [b["lane"] for b in row["bars"]] == [1, 2, 3] and row["more"] == [0, 2, 0, 0, 0] and row["rows"] == 4


def test_cancelled_items_are_not_drawn(w):
    eid = add(w, "Gone", 1, people=[w["s1"]])
    st.cal_cancel(w["conn"], eid)
    assert titles(rows(grid(w, "s1"))["P s1"]) == []


# ------------------------------------------------------------ whereabouts ---

def test_leave_carries_no_reason_and_field_shows_where(w):
    uid = w["s1"]["id"]
    w["conn"].execute("INSERT INTO whereabouts(user_id, day, status, note, updated_at) VALUES (?,?,?,?,?)",
                      (uid, iso(1), "leave", "dentist appointment", "x"))
    w["conn"].execute("INSERT INTO whereabouts(user_id, day, status, note, updated_at) VALUES (?,?,?,?,?)",
                      (uid, iso(2), "field", "Palawan", "x"))
    w["conn"].commit()
    cells = rows(grid(w, "s1"))["P s1"]["cells"]
    assert (cells[1]["state"], cells[1]["note"], cells[1]["text"]) == ("leave", "", "On leave")
    assert (cells[2]["state"], cells[2]["note"]) == ("field", "Palawan")
    assert "dentist" not in repr(grid(w, "s1"))


def test_a_holiday_has_no_cells_and_names_the_day(w):
    st.set_holiday(w["conn"], MON + timedelta(days=2), "Office closed", "special")
    g = grid(w, "s1")
    assert g["days"][2]["holiday"]["name"] == "Office closed"
    assert rows(g)["P s1"]["cells"][2]["state"] == "holiday"


# ------------------------------------------------------------------- page ---

def test_the_week_page_renders_for_everyone_and_keeps_to_its_own_links(app_mod, viewer, admin):
    for client in (viewer, admin):
        r = client.get("/calendar?view=week&day=2026-10-14")
        assert r.status_code == 200 and ("cal-people-week" in r.text or "isn't linked" in r.text or "nobody in your team" in r.text)
        assert 'aria-current="true">Week' in r.text and "Last week" in r.text and "Next week" in r.text
        assert "day=2026-10-05" in r.text and "day=2026-10-19" in r.text
        assert 'aria-label="Whose calendar"' not in r.text            # the scope pills do not apply here
    tab = viewer.get("/?view=calendar&layout=week&day=2026-10-14").text
    assert 'aria-current="true">Week' in tab and "view=calendar" in tab and "layout=week" in tab


def test_an_unlinked_viewer_is_told_why_there_is_no_team(viewer):
    assert "isn't linked to a directory record" in viewer.get("/calendar?view=week").text


def test_bad_week_input_falls_back(viewer):
    r = viewer.get("/calendar?view=week&day=nonsense", follow_redirects=False)
    assert r.status_code in (303, 200)
    assert viewer.get("/?view=calendar&layout=week&day=nonsense").status_code == 200


def test_the_page_shows_a_team_with_bars_and_no_leave_reason(app_mod, viewer):
    conn = st.connect(app_mod.DB); st.init_db(conn)
    with in_the_directory(app_mod, "viewer@test.local", path="CALWK/D1/S1"):
        uid = st.get_admin_user(conn, "viewer@test.local")["id"]
        conn.execute("UPDATE resource_person SET is_internal=1 WHERE name LIKE 'LF-%'")
        eid = st.cal_create(conn, "CALWK Trip <b>x</b>", "2026-10-13", end_date="2026-10-14", audience="bureau",
                            people=[(uid, "travel")], kind="travel")
        conn.execute("INSERT OR REPLACE INTO whereabouts(user_id, day, status, note, updated_at) VALUES (?,?,?,?,?)",
                     (uid, "2026-10-15", "leave", "secret reason", "x"))
        conn.commit()
        html = viewer.get("/calendar?view=week&day=2026-10-12").text
        assert "cal-pw-row" in html and "CALWK Trip &lt;b&gt;x&lt;/b&gt;" in html and "<b>x</b>" not in html
        assert "secret reason" not in html and "On leave" in html
        assert f'href="/calendar/entries/{eid}"' in html
        flt = viewer.get("/calendar?view=week&day=2026-10-12&kind=meeting").text
        assert "CALWK Trip" not in flt
        st.cal_delete(conn, eid)
        conn.execute("DELETE FROM whereabouts WHERE note='secret reason'")
        conn.commit()
    conn.close()
