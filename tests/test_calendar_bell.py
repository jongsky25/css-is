"""Bell rows and seen-tracking for the office calendar (G2)."""
from __future__ import annotations
from datetime import timedelta

import pytest

import office_calendar as oc
import storage as st
import tzutil as tz
from test_calendar_home import world                                  # noqa: F401  (throwaway org + accounts)

TODAY = tz.today_local()
D = lambda n: (TODAY + timedelta(days=n)).isoformat()                  # noqa: E731


def add(w, title="Planning", day=5, who=("s1",), by="editor@x", **kw):
    return st.cal_create(w["conn"], title, D(day), people=[(w[p]["id"], "attending") for p in who], by=by, **kw)


def unseen(w, who="s1"):
    return [(u["title"], u["kind"]) for u in st.cal_unseen_for_user(w["conn"], w[who]["id"], TODAY)]


# --------------------------------------------------------------- tracking ---

def test_an_item_someone_else_added_is_new_until_seen(world):                                  # noqa: F811
    add(world)
    assert unseen(world) == [("Planning", "new")]
    st.cal_mark_seen(world["conn"], world["s1"]["id"])
    assert unseen(world) == []


def test_what_you_add_or_change_yourself_is_never_new_to_you(world):                           # noqa: F811
    e = add(world, who=("s1", "s1b"), by=world["s1"]["username"])
    assert unseen(world, "s1") == [] and unseen(world, "s1b") == [("Planning", "new")]
    st.cal_mark_seen(world["conn"], world["s1b"]["id"])
    st.cal_update(world["conn"], e, by=world["s1"]["username"], start_date=D(6))
    assert unseen(world, "s1") == [] and unseen(world, "s1b") == [("Planning", "changed")]


def test_only_a_schedule_change_resurfaces_it(world):                                          # noqa: F811
    e = add(world)
    st.cal_mark_seen(world["conn"], world["s1"]["id"])
    st.cal_update(world["conn"], e, by="editor@x", note="just a note", venue="Room 5")        # sequence unmoved
    assert unseen(world) == []
    st.cal_update(world["conn"], e, by="editor@x", start_time="09:00", end_time="10:00")
    assert unseen(world) == [("Planning", "changed")]


def test_a_cancellation_is_reported_as_cancelled(world):                                       # noqa: F811
    e = add(world)
    st.cal_mark_seen(world["conn"], world["s1"]["id"])
    st.cal_cancel(world["conn"], e, by="editor@x")
    assert unseen(world) == [("Planning", "cancelled")]


def test_past_items_and_other_peoples_are_not_counted(world):                                  # noqa: F811
    add(world, day=-5)
    add(world, "Mine only", who=("s1b",))
    assert unseen(world, "s1") == []


def test_a_multi_day_item_still_under_way_counts(world):                                       # noqa: F811
    st.cal_create(world["conn"], "Retreat", D(-2), end_date=D(2), people=[(world["s1"]["id"], "attending")], by="editor@x")
    assert unseen(world) == [("Retreat", "new")]


def test_an_import_never_floods_the_bell(world):                                               # noqa: F811
    add(world, source="import", import_key="k1")
    assert unseen(world) == []


def test_everything_that_existed_before_the_bell_is_already_seen(world):                       # noqa: F811
    c = world["conn"]
    add(world)
    c.execute("UPDATE calendar_entry_person SET seen_seq=NULL"); c.commit()
    st.set_setting(c, "cal_seen_backfilled", "0")
    st.init_db(c)
    assert unseen(world) == []
    add(world, "Later one")                                                                    # but new ones still count
    st.init_db(c)
    assert unseen(world) == [("Later one", "new")]


def test_marking_one_leaves_the_rest(world):                                                   # noqa: F811
    a = add(world, "A"); add(world, "B")
    st.cal_mark_seen(world["conn"], world["s1"]["id"], [a])
    assert unseen(world) == [("B", "new")]
    assert st.cal_mark_seen(world["conn"], world["s1"]["id"], []) == 0


def test_marking_is_per_person(world):                                                         # noqa: F811
    add(world, who=("s1", "s1b"))
    st.cal_mark_seen(world["conn"], world["s1"]["id"])
    assert unseen(world, "s1b") == [("Planning", "new")]


# --------------------------------------------------------------- bell rows ---

def rows(w, who="s1", today=TODAY):
    return oc.bell_rows(w["conn"], w[who]["id"], today)


def test_the_bell_counts_new_items_with_the_right_words(world):                                # noqa: F811
    add(world, "A"); 
    assert rows(world) == [{"text": "1 new or changed calendar item for you", "url": "/calendar/updates", "count": 1}]
    add(world, "B")
    assert rows(world)[0]["text"] == "2 new or changed calendar items for you" and rows(world)[0]["count"] == 2


def test_nothing_to_say_means_no_rows(world):                                                  # noqa: F811
    assert rows(world) == []


def monday_next():
    return TODAY - timedelta(days=TODAY.weekday()) + timedelta(days=7)


def test_a_trip_you_reported_differently_asks_you_to_confirm(world):                           # noqa: F811
    c = world["conn"]
    mon = monday_next()
    st.cal_create(c, "Palawan trip", mon.isoformat(), kind="travel", people=[(world["s1"]["id"], "travel")],
                  by=world["s1"]["username"])
    assert rows(world) == []                                                                   # nothing reported yet: no mismatch
    c.execute("INSERT INTO whereabouts(user_id, day, status, note, updated_at) VALUES (?,?,?,?,?)",
              (world["s1"]["id"], mon.isoformat(), "office", None, "x")); c.commit()
    got = rows(world)
    assert got == [{"text": "Confirm where you'll be: Palawan trip", "count": 1,
                    "url": f"/work-arrangement/week?week={mon.isoformat()}"}]


def test_a_trip_that_moved_after_you_confirmed_says_so(world):                                 # noqa: F811
    c = world["conn"]
    mon = monday_next()
    e = st.cal_create(c, "Cebu trip", mon.isoformat(), kind="travel", people=[(world["s1"]["id"], "travel")],
                      by=world["s1"]["username"])
    c.execute("INSERT INTO whereabouts_week(user_id, week_start, submitted_at) VALUES (?,?,?)",
              (world["s1"]["id"], mon.isoformat(), "2000-01-01T00:00:00")); c.commit()
    assert st.cal_trip_changes_after_confirm(c, world["s1"]["id"], mon) == []                 # never moved
    st.cal_update(c, e, by="editor@x", start_date=(mon + timedelta(days=1)).isoformat())
    assert [r["text"] for r in rows(world)][-1] == "Cebu trip changed after you confirmed your week"
    c.execute("UPDATE whereabouts_week SET submitted_at='2999-01-01T00:00:00'"); c.commit()  # confirmed again afterwards
    assert not [r for r in rows(world) if "changed after" in r["text"]]


def test_a_week_never_confirmed_has_no_changed_after_row(world):                               # noqa: F811
    c = world["conn"]
    mon = monday_next()
    e = st.cal_create(c, "Bohol", mon.isoformat(), kind="travel", people=[(world["s1"]["id"], "travel")], by="x@x")
    st.cal_update(c, e, by="x@x", start_date=(mon + timedelta(days=1)).isoformat())
    assert not [r for r in rows(world) if "changed after" in r["text"]]


# -------------------------------------------------------------------- pages ---

@pytest.fixture()
def page(app_mod, viewer):
    c = st.connect(app_mod.DB); st.init_db(c)
    uid = st.get_admin_user(c, "viewer@test.local")["id"]
    made = []
    yield c, uid, made
    for e in made:
        st.cal_delete(c, e)
    c.close()


def test_the_bell_the_list_and_the_item_page_agree(app_mod, viewer, page):
    c, uid, made = page
    st.cal_mark_seen(c, uid)
    made.append(st.cal_create(c, "BELLTEST One", D(3), audience="bureau", people=[(uid, "attending")], by="editor@x"))
    made.append(st.cal_create(c, "BELLTEST Two", D(4), audience="bureau", people=[(uid, "attending")], by="editor@x"))
    home = viewer.get("/").text
    assert "2 new or changed calendar items for you" in home
    listing = viewer.get("/calendar/updates").text
    assert "BELLTEST One" in listing and "BELLTEST Two" in listing and listing.count("calendar/entries/") >= 2
    assert st.cal_unseen_for_user(c, uid, TODAY) == []
    assert "new or changed calendar item" not in viewer.get("/").text
    assert "all caught up" in viewer.get("/calendar/updates").text


def test_opening_an_item_clears_just_that_one(app_mod, viewer, page):
    c, uid, made = page
    st.cal_mark_seen(c, uid)
    a = st.cal_create(c, "BELLTEST A", D(3), audience="bureau", people=[(uid, "attending")], by="editor@x")
    b = st.cal_create(c, "BELLTEST B", D(4), audience="bureau", people=[(uid, "attending")], by="editor@x")
    made += [a, b]
    assert viewer.get(f"/calendar/entries/{a}").status_code == 200
    assert [u["title"] for u in st.cal_unseen_for_user(c, uid, TODAY)] == ["BELLTEST B"]
