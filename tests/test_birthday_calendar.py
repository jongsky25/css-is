"""Birthdays on the calendar, the home line, the greeting and the monthly list (office calendar F2)."""
from __future__ import annotations
from datetime import date, timedelta

import pytest

import birthdays as bd
import office_calendar as oc
import office_connect as oconn
import storage as st
from test_calendar_home import world                                  # noqa: F401  (throwaway org + accounts)

TODAY = date(2026, 10, 14)                                            # a Wednesday


# ----------------------------------------------------------- pure rules ---

def test_feb_29_sits_on_feb_28_in_a_non_leap_year():
    assert bd.occurrence(2, 29, 2028) == date(2028, 2, 29)
    assert bd.occurrence(2, 29, 2027) == date(2027, 2, 28)
    assert bd.occurrences_between(2, 29, date(2027, 2, 1), date(2027, 3, 1)) == [date(2027, 2, 28)]
    assert bd.is_today(2, 29, date(2027, 2, 28))


def test_a_window_across_new_year_finds_it_once():
    assert bd.occurrences_between(12, 31, date(2026, 12, 28), date(2027, 1, 3)) == [date(2026, 12, 31)]
    assert bd.occurrences_between(1, 2, date(2026, 12, 28), date(2027, 1, 3)) == [date(2027, 1, 2)]
    assert bd.occurrences_between(6, 1, date(2026, 12, 28), date(2027, 1, 3)) == []


@pytest.mark.parametrize("display, nick, want", [
    ("Maria Teresa Santiago", "Riza", "Riza"), ("Maria Teresa Santiago", "", "Maria"),
    ("DELA CRUZ, Juan P.", None, "Juan"), ("", None, "")])
def test_the_name_is_the_nickname_else_the_first_name(display, nick, want):
    assert bd.first_name(display, nick) == want


def test_weekend_birthdays_are_labelled():
    wed = date(2026, 10, 14)
    assert bd.week_label(date(2026, 10, 17), wed) == "Sat (weekend)"
    assert bd.week_label(wed, wed) == "Today" and bd.week_label(date(2026, 10, 15), wed) == "Tomorrow"
    assert bd.week_label(date(2026, 10, 19), wed) == "Mon"


P = lambda uid, share, sec, div: {"user_id": uid, "share": share, "section_path": sec, "division_path": div}  # noqa: E731
V = lambda uid, sec, div: {"user_id": uid, "section_path": sec, "division_path": div}                         # noqa: E731


@pytest.mark.parametrize("share, same_sec, same_div, other, want", [
    ("none", False, False, False, False), ("section", True, True, False, True),
    ("section", False, True, False, False), ("division", False, True, False, True),
    ("division", False, False, False, False), ("bureau", False, False, False, True)])
def test_the_share_matrix(share, same_sec, same_div, other, want):
    person = P(1, share, "T/D1/S1", "T/D1")
    viewer = V(2, "T/D1/S1" if same_sec else ("T/D1/S2" if same_div else "T/D2/S3"),
               "T/D1" if same_div else "T/D2")
    assert bd.shared_with(person, viewer) is want


def test_you_always_see_your_own_even_if_not_shared():
    assert bd.shared_with(P(1, "none", None, None), V(1, None, None))


def test_unlinked_people_are_only_reachable_bureau_wide():
    assert not bd.shared_with(P(1, "section", None, None), V(2, None, None))
    assert bd.shared_with(P(1, "bureau", None, None), V(2, None, None))


@pytest.mark.parametrize("scope, share, want", [
    ("bureau", "bureau", True), ("mine", "bureau", False), ("blend", "bureau", True),
    ("blend", "section", False), ("section", "section", True), ("division", "division", True)])
def test_scope_narrows_what_sharing_allows(scope, share, want):
    person = P(1, share, "T/D1/S1", "T/D1")
    assert bd.in_scope(scope, person, V(2, "T/D1/S1", "T/D1")) is want


# ------------------------------------------------------- the layer (DB) ---

def birthday(w, who, month, day, share):
    st.set_birthday(w["conn"], w[who]["id"], month, day, share)


def titles(w, viewer, scope="bureau", a="2026-10-01", b="2026-10-31"):
    return sorted(i["title"] for i in oc.items_between(w["conn"], w[viewer], a, b, scope=scope, layers=["birthdays"]))


def who(w, viewer, scope="bureau"):
    return sorted(i["people"][0]["user_id"] for i in oc.items_between(
        w["conn"], w[viewer], "2026-10-01", "2026-10-31", scope=scope, layers=["birthdays"]))


def test_each_share_reaches_exactly_the_right_viewers(world):                                  # noqa: F811
    birthday(world, "s1", 10, 14, "section"); birthday(world, "s3", 10, 15, "division")
    birthday(world, "dir", 10, 16, "bureau"); birthday(world, "nobody", 10, 17, "none")
    ids = lambda *k: sorted(world[x]["id"] for x in k)                                          # noqa: E731
    assert who(world, "s1b") == ids("s1", "dir")                    # same section + bureau-wide; not S3's division share
    assert who(world, "s3") == ids("s3", "dir")
    assert who(world, "dir") == ids("dir")                          # no section, no division
    assert who(world, "nobody") == ids("nobody", "dir")             # unlinked: own + bureau-wide only


def test_a_private_birthday_is_visible_only_to_its_owner(world):                               # noqa: F811
    birthday(world, "s1", 10, 14, "none")
    assert len(titles(world, "s1")) == 1
    for other in ("s1b", "s3", "dir", "nobody"):
        assert titles(world, other) == []


def test_default_scope_is_mine_plus_bureau_wide_only(world):                                   # noqa: F811
    birthday(world, "s1b", 10, 14, "section"); birthday(world, "dir", 10, 15, "bureau")
    ids = lambda *k: sorted(world[x]["id"] for x in k)                                          # noqa: E731
    assert who(world, "s1", "blend") == ids("dir")                  # the Director's, not the section mate's
    assert who(world, "s1", "section") == ids("s1b")
    assert who(world, "s1", "bureau") == ids("s1b", "dir")
    assert who(world, "s1", "mine") == []


def test_archived_and_inactive_people_drop_off(world):                                         # noqa: F811
    c = world["conn"]
    birthday(world, "s1b", 10, 14, "bureau"); birthday(world, "s3", 10, 15, "bureau")
    c.execute("UPDATE admin_user SET active=0 WHERE id=?", (world["s3"]["id"],))
    c.execute("UPDATE resource_person SET archived_at='2026-01-01' WHERE id=(SELECT rp_id FROM admin_user WHERE id=?)",
              (world["s1b"]["id"],))
    c.commit()
    assert titles(world, "s1") == []


def test_it_repeats_every_year_and_never_carries_a_year(world):                                # noqa: F811
    birthday(world, "s1", 3, 9, "bureau")
    got = oc.items_between(world["conn"], world["s1"], "2026-01-01", "2028-12-31", scope="mine", layers=["birthdays"])
    assert [i["start"] for i in got] == ["2026-03-09", "2027-03-09", "2028-03-09"]
    assert got[0]["kind"] == "birthday" and got[0]["layer"] == "birthdays" and got[0]["people"][0]["role"] == "celebrant"


def test_feb_29_in_the_layer(world):                                                           # noqa: F811
    birthday(world, "s1", 2, 29, "bureau")
    got = oc.items_between(world["conn"], world["s1"], "2027-02-01", "2028-03-01", scope="mine", layers=["birthdays"])
    assert [i["start"] for i in got] == ["2027-02-28", "2028-02-29"]


def test_the_title_uses_the_nickname(world):                                                   # noqa: F811
    st.set_user_nickname(world["conn"], world["s1"]["id"], "Riza")
    birthday(world, "s1", 10, 14, "bureau")
    assert titles(world, "s1", "mine") == ["🎂 Riza"]


# ------------------------------------------------------ home + the list ---

def test_the_home_line_lists_the_week_with_day_labels(world):                                  # noqa: F811
    birthday(world, "s1b", 10, 14, "section"); birthday(world, "s1", 10, 17, "section")
    birthday(world, "s3", 10, 15, "none")
    blk = oconn.calendar_week_block(world["conn"], world["s1"], view="team", today=TODAY)
    assert [(c["when"], c["today"]) for c in blk["celebrating"]] == [("Today", True), ("Sat (weekend)", False)]
    assert all(i["kind"] != "birthday" for i in blk["items"])           # not mixed into the agenda cards
    me = oconn.calendar_week_block(world["conn"], world["s1"], view="me", today=TODAY)
    assert [c["when"] for c in me["celebrating"]] == ["Sat (weekend)"]   # blend: yours only (nothing bureau-wide)


def test_a_birthday_does_not_make_the_card_nonempty(world):                                    # noqa: F811
    birthday(world, "s1", 10, 14, "bureau")
    blk = oconn.calendar_week_block(world["conn"], world["s1"], view="me", today=TODAY)
    assert blk["items"] == [] and blk["n_total"] == 0


# ------------------------------------------------------------- pages ---

@pytest.fixture()
def acct(app_mod):
    c = st.connect(app_mod.DB); st.init_db(c)
    uid = st.get_admin_user(c, "viewer@test.local")["id"]
    yield c, uid
    st.clear_birthday(c, uid); c.close()


def test_the_celebrant_is_greeted_on_the_day_only(app_mod, viewer, acct):
    c, uid = acct
    from datetime import date as d
    today = app_mod._today_local()
    st.set_birthday(c, uid, today.month, today.day, "none")
    assert "Happy birthday" in viewer.get("/").text
    other = today + timedelta(days=3)
    st.set_birthday(c, uid, other.month, other.day, "none")
    html = viewer.get("/").text
    assert "Happy birthday" not in html and "Hi, " in html


def test_the_monthly_page_lists_what_you_may_see_and_prints(app_mod, viewer, acct):
    c, uid = acct
    st.set_birthday(c, uid, 10, 14, "bureau")
    html = viewer.get("/calendar/birthdays?month=10").text
    assert "October celebrants" in html and "window.print()" in html and "14" in html
    assert viewer.get("/calendar/birthdays?month=13", follow_redirects=False).status_code == 303
    st.clear_birthday(c, uid)
    assert "No shared birthdays in October" in viewer.get("/calendar/birthdays?month=10").text


def test_the_calendar_page_offers_the_list_and_filters_by_type(app_mod, viewer, acct):
    c, uid = acct
    today = app_mod._today_local()
    st.set_birthday(c, uid, today.month, today.day, "none")
    html = viewer.get("/calendar?scope=mine").text
    assert "Birthdays</a>" in html and "🎂" in html
    st.set_user_nickname(c, uid, "Zedrick")
    assert "🎂 Zedrick" in viewer.get("/calendar?scope=mine").text
    assert "🎂 Zedrick" not in viewer.get("/calendar?scope=mine&kind=meeting").text
    st.set_user_nickname(c, uid, "")
