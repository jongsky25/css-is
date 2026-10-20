"""Repeating calendar items (office calendar H1)."""
from __future__ import annotations
import tzutil as _test_tz
from datetime import date, timedelta
from urllib.parse import urlencode

import pytest

import calendar_ics as ics
import mailer
import office_calendar as oc
import recurrence as rc
import send_reminders as sr
import storage as st
import tzutil as tz
from test_calendar_home import world                                  # noqa: F401  (throwaway org + accounts)

TUE = date(2026, 10, 13)                          # a Tuesday
FORM = {"Content-Type": "application/x-www-form-urlencoded"}


# --------------------------------------------------------------- the rules ---

@pytest.mark.parametrize("repeat, start, until, want", [
    ("weekdays", TUE, date(2026, 11, 13), "FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;UNTIL=20261113"),
    ("weekly", TUE, date(2026, 11, 10), "FREQ=WEEKLY;BYDAY=TU;UNTIL=20261110"),
    ("biweekly", TUE, date(2026, 12, 1), "FREQ=WEEKLY;INTERVAL=2;BYDAY=TU;UNTIL=20261201"),
    ("monthly_date", TUE, date(2027, 3, 1), "FREQ=MONTHLY;BYMONTHDAY=13;UNTIL=20270301"),
    ("monthly_nth", TUE, date(2027, 3, 1), "FREQ=MONTHLY;BYDAY=2TU;UNTIL=20270301"),
    ("monthly_nth", date(2026, 10, 29), date(2027, 3, 1), "FREQ=MONTHLY;BYDAY=-1TH;UNTIL=20270301"),   # a 5th is "the last"
])
def test_the_form_choices_build_these_rules(repeat, start, until, want):
    assert rc.build(repeat, start, until) == want
    assert rc.validate(want, start) == want                                   # and they are accepted as stored


def test_nothing_to_build_when_it_does_not_repeat():
    assert rc.build("none", TUE, None) is None and rc.build("", TUE, None) is None


@pytest.mark.parametrize("repeat, until, msg", [
    ("weekly", None, "last date"), ("weekly", date(2026, 10, 1), "before the first"),
    ("weekly", date(2029, 1, 1), "2 years"), ("hourly", date(2026, 11, 1), "list")])
def test_the_form_refuses_a_bad_series(repeat, until, msg):
    with pytest.raises(ValueError, match=msg):
        rc.build(repeat, TUE, until)


@pytest.mark.parametrize("rule", [
    "FREQ=DAILY;UNTIL=20261120", "FREQ=WEEKLY;BYDAY=TU", "FREQ=WEEKLY;COUNT=3;BYDAY=TU;UNTIL=20261120",
    "FREQ=WEEKLY;INTERVAL=9;BYDAY=TU;UNTIL=20261120", "FREQ=WEEKLY;BYDAY=2TU;UNTIL=20261120",
    "FREQ=MONTHLY;BYMONTHDAY=13;BYDAY=2TU;UNTIL=20270101", "FREQ=MONTHLY;UNTIL=20270101", "garbage", "",
    "FREQ=WEEKLY;BYDAY=XX;UNTIL=20261120", "FREQ=WEEKLY;BYDAY=TU;BYDAY=WE;UNTIL=20261120",
    "FREQ=WEEKLY;BYDAY=TU;UNTIL=nope", "FREQ=WEEKLY;BYSETPOS=1;BYDAY=TU;UNTIL=20261120"])
def test_unsupported_rules_are_refused(rule):
    with pytest.raises(ValueError):
        rc.validate(rule, TUE)


def test_the_first_date_must_fit_the_pattern():
    with pytest.raises(ValueError, match="doesn't fit"):
        rc.validate("FREQ=WEEKLY;BYDAY=WE;UNTIL=20261120", TUE)               # starts on a Tuesday


def occ(rule, start=TUE, ex=None, a=date(2026, 10, 1), b=date(2027, 4, 1), span=0):
    return [d.isoformat() for d in rc.occurrences(start, rule, ex, a, b, span)]


def test_weekly_biweekly_and_weekday_occurrences():
    assert occ(rc.build("weekly", TUE, date(2026, 11, 3))) == ["2026-10-13", "2026-10-20", "2026-10-27", "2026-11-03"]
    assert occ(rc.build("biweekly", TUE, date(2026, 11, 10))) == ["2026-10-13", "2026-10-27", "2026-11-10"]
    wk = occ(rc.build("weekdays", date(2026, 10, 12), date(2026, 10, 19)), date(2026, 10, 12))
    assert wk == ["2026-10-12", "2026-10-13", "2026-10-14", "2026-10-15", "2026-10-16", "2026-10-19"]


def test_monthly_by_date_skips_short_months_and_by_weekday_keeps_the_pattern():
    jan31 = date(2026, 1, 31)
    assert occ(rc.build("monthly_date", jan31, date(2026, 6, 30)), jan31, a=date(2026, 1, 1), b=date(2026, 6, 30)) == [
        "2026-01-31", "2026-03-31", "2026-05-31"]
    assert occ(rc.build("monthly_nth", TUE, date(2027, 1, 31))) == [
        "2026-10-13", "2026-11-10", "2026-12-08", "2027-01-12"]                # every 2nd Tuesday
    last = date(2026, 10, 27)                                                  # the 4th Tuesday AND the last
    assert rc.build("monthly_nth", last, date(2027, 1, 31)).endswith("BYDAY=4TU;UNTIL=20270131")


def test_skipped_dates_are_removed_and_garbage_in_the_list_is_ignored():
    rule = rc.build("weekly", TUE, date(2026, 11, 3))
    assert occ(rule, ex="2026-10-20, junk ,2026-11-03") == ["2026-10-13", "2026-10-27"]
    assert rc.parse_exdates("2026-10-20,x,2026-10-20,2026-10-13") == [date(2026, 10, 13), date(2026, 10, 20)]
    assert rc.join_exdates([date(2026, 10, 20), date(2026, 10, 13), date(2026, 10, 20)]) == "2026-10-13,2026-10-20"
    assert rc.join_exdates([]) is None


def test_a_multi_day_occurrence_that_began_earlier_counts():
    rule = rc.build("weekly", TUE, date(2026, 11, 3))
    got = occ(rule, a=date(2026, 10, 21), b=date(2026, 10, 21), span=2)         # Tue 20 runs Tue-Thu
    assert got == ["2026-10-20"]
    assert occ(rule, a=date(2026, 10, 23), b=date(2026, 10, 23), span=2) == []


def test_a_plain_item_is_just_itself():
    assert occ(None, a=date(2026, 10, 13), b=date(2026, 10, 13)) == ["2026-10-13"]
    assert occ(None, a=date(2026, 10, 14), b=date(2026, 10, 20)) == []


def test_describe_and_preselect_round_trip():
    for repeat in ("weekdays", "weekly", "biweekly", "monthly_date", "monthly_nth"):
        rule = rc.build(repeat, TUE, date(2027, 3, 1))
        assert rc.kind_of(rule, TUE) == (repeat, date(2027, 3, 1))
    assert rc.describe(rc.build("weekly", TUE, date(2026, 12, 29)), TUE) == "Every Tuesday until Dec 29, 2026"
    assert rc.describe(rc.build("monthly_nth", TUE, date(2027, 3, 1)), TUE) == "Monthly on the 2nd Tuesday until Mar 1, 2027"
    assert rc.describe(rc.build("monthly_date", TUE, date(2027, 3, 1)), TUE).startswith("Monthly on the 13th")
    assert rc.kind_of("nonsense", TUE) == ("none", None) and rc.describe("nonsense", TUE) == ""


# ----------------------------------------------------------------- storage ---

def series(w, who=("s1",), repeat="weekly", until=date(2026, 11, 3), **kw):
    kw.setdefault("audience", "bureau")
    return st.cal_create(w["conn"], "Section meeting", TUE.isoformat(), rrule=rc.build(repeat, TUE, until),
                         people=[(w[p]["id"], "attending") for p in who], by="editor@x", **kw)


def titles(w, a="2026-10-01", b="2026-11-30", who="s1", scope="bureau"):
    return [(i["start"], i["key"]) for i in oc.items_between(w["conn"], w[who], a, b, scope=scope, layers=["entries"])]


def test_a_series_is_one_row_that_expands_into_items(world):                                   # noqa: F811
    e = series(world)
    assert world["conn"].execute("SELECT COUNT(*) FROM calendar_entry").fetchone()[0] == 1
    assert titles(world) == [(d, f"entry:{e}:{d}") for d in ("2026-10-13", "2026-10-20", "2026-10-27", "2026-11-03")]


def test_a_skipped_date_is_not_on_the_calendar_and_the_sequence_moves(world):                  # noqa: F811
    c = world["conn"]
    e = series(world)
    before = st.cal_get(c, e)["sequence"]
    st.cal_update(c, e, by="x@x", exdates="2026-10-20")
    assert [d for d, _k in titles(world)] == ["2026-10-13", "2026-10-27", "2026-11-03"]
    assert st.cal_get(c, e)["sequence"] == before + 1


def test_a_window_inside_the_series_still_finds_it(world):                                     # noqa: F811
    series(world)
    assert [d for d, _k in titles(world, "2026-10-26", "2026-10-28")] == ["2026-10-27"]
    assert titles(world, "2026-11-04", "2027-02-01") == []                       # after the last date
    assert titles(world, "2026-09-01", "2026-10-12") == []                       # before the first


def test_items_link_to_the_series_with_the_date_and_say_they_repeat(world):                    # noqa: F811
    e = series(world)
    first = oc.items_between(world["conn"], world["s1"], "2026-10-01", "2026-10-31", scope="bureau", layers=["entries"])[0]
    assert first["url"] == f"/calendar/entries/{e}?date=2026-10-13" and "repeats" in first["flags"]


def test_an_occurrence_on_a_holiday_says_so(world):                                            # noqa: F811
    c = world["conn"]
    series(world)
    c.execute("INSERT OR REPLACE INTO holiday(day, name, kind) VALUES ('2026-10-20', 'Foundation Day', 'special')"); c.commit()
    flags = {i["start"]: i["flags"] for i in oc.items_between(c, world["s1"], "2026-10-01", "2026-10-31", scope="bureau", layers=["entries"])}
    assert "falls on Foundation Day" in flags["2026-10-20"] and "falls on Foundation Day" not in flags["2026-10-13"]


def test_a_cancelled_series_disappears_and_comes_back(world):                                  # noqa: F811
    c = world["conn"]
    e = series(world)
    st.cal_cancel(c, e); assert titles(world) == []
    st.cal_restore(c, e); assert len(titles(world)) == 4


def test_rules_are_validated_on_the_way_in(world):                                             # noqa: F811
    c = world["conn"]
    with pytest.raises(ValueError):
        st.cal_create(c, "x", "2026-10-13", rrule="FREQ=DAILY;UNTIL=20261120")
    with pytest.raises(ValueError, match="trip"):
        st.cal_create(c, "x", "2026-10-13", kind="travel", rrule=rc.build("weekly", TUE, date(2026, 11, 3)))
    ev = st.create_event(c, "Act", "2026-10-13", form_instance_ids=[st.create_form_instance(c, 2, "F2", "2026-10-13", topic="a")])
    c.commit()
    with pytest.raises(ValueError, match="activity"):
        st.cal_create(c, "x", "2026-10-13", event_id=ev["id"], rrule=rc.build("weekly", TUE, date(2026, 11, 3)))
    e = series(world)
    with pytest.raises(ValueError):
        st.cal_update(c, e, start_date="2026-10-14")                              # no longer fits the pattern
    with pytest.raises(ValueError, match="trip"):
        st.cal_update(c, e, kind="travel")


def test_skipped_dates_are_tidied_and_cleared_with_the_rule(world):                            # noqa: F811
    c = world["conn"]
    e = series(world)
    st.cal_update(c, e, exdates="2026-10-27, bad,2026-10-20,2026-10-20")
    assert st.cal_get(c, e)["exdates"] == "2026-10-20,2026-10-27"
    st.cal_update(c, e, rrule=None)
    got = st.cal_get(c, e)
    assert got["rrule"] is None and got["exdates"] is None


def test_a_series_that_has_not_ended_still_counts_as_upcoming(world):                          # noqa: F811
    e = st.cal_create(world["conn"], "Old start", "2026-01-06", rrule=rc.build("weekly", date(2026, 1, 6), date(2027, 12, 29)),
                      people=[(world["s1"]["id"], "attending")], by="x@x")
    assert [u["entry_id"] for u in st.cal_unseen_for_user(world["conn"], world["s1"]["id"], date(2026, 10, 1))] == [e]
    assert st.cal_unseen_for_user(world["conn"], world["s1"]["id"], date(2028, 1, 3)) == []        # ended


def test_last_day_of_a_series_is_its_until(world):                                             # noqa: F811
    e = series(world)
    assert st.cal_last_day(st.cal_get(world["conn"], e)) == "2026-11-03"


# ----------------------------------------------------- everything downstream ---

def test_a_series_makes_a_double_booking_on_any_of_its_days(world):                            # noqa: F811
    c = world["conn"]
    series(world, start_time="09:00", end_time="10:00")
    c.execute("UPDATE calendar_entry SET start_time='09:00', end_time='10:00'"); c.commit()
    st.cal_create(c, "Clash", "2026-10-27", start_time="09:30", end_time="10:30", audience="bureau",
                  people=[(world["s1"]["id"], "attending")], by="x@x")
    got = [m for m in oc.mismatches(c, [world["s1"]["id"]], "2026-10-26", "2026-10-30") if m["kind"] == "double_booked"]
    assert [m["day"] for m in got] == ["2026-10-27"]


def test_leave_on_a_day_of_the_series_is_flagged(world):                                       # noqa: F811
    c = world["conn"]
    series(world)
    c.execute("INSERT INTO whereabouts(user_id, day, status, note, updated_at) VALUES (?,?,?,?,?)",
              (world["s1"]["id"], "2026-10-20", "leave", None, "x")); c.commit()
    got = oc.mismatches(c, [world["s1"]["id"]], "2026-10-19", "2026-10-23")
    assert [(m["kind"], m["day"]) for m in got] == [("leave_on_entry", "2026-10-20")]


def test_the_day_before_reminder_follows_the_series(world):                       # noqa: F811
    c = world["conn"]
    sid = series(world)
    assert [e["title"] for e in oc.entries_starting_on(c, date(2026, 10, 20))[world["s1"]["id"]]] == ["Section meeting"]
    assert oc.entries_starting_on(c, date(2026, 10, 21)) == {}
    st.cal_update(c, sid, by="x@x", exdates="2026-10-20")
    assert oc.entries_starting_on(c, date(2026, 10, 20)) == {}


def test_a_series_cannot_be_turned_into_an_activity():
    assert not oc.entry_can_collect_feedback({"kind": "meeting", "status": "confirmed", "event_id": None,
                                              "rrule": "FREQ=WEEKLY;BYDAY=TU;UNTIL=20261110"})
    assert oc.entry_can_collect_feedback({"kind": "meeting", "status": "confirmed", "event_id": None, "rrule": None})


def test_skipping_a_date_tells_the_people_on_it(world):                                        # noqa: F811
    c = world["conn"]
    far = _test_tz.today_local() + timedelta(days=30)
    e = st.cal_create(c, "Weekly", far.isoformat(), rrule=rc.build("weekly", far, far + timedelta(days=60)),
                      people=[(world["s1"]["id"], "attending")], by="editor@x")
    c.execute("DELETE FROM calendar_outbox"); c.commit()
    st.cal_update(c, e, by="editor@x", exdates=(far + timedelta(days=7)).isoformat())
    assert c.execute("SELECT kind, detail FROM calendar_outbox").fetchall() == [("changed", "exdates")]


# --------------------------------------------------------------------- ics ---

def test_a_series_is_one_ics_event_with_an_rrule_and_exdates(world):                           # noqa: F811
    c = world["conn"]
    e = series(world, start_time="09:00", end_time="10:00")
    st.cal_update(c, e, by="x@x", exdates="2026-10-20,2026-10-27")
    text = ics.vcalendar([ics.entry_event(st.cal_get(c, e))])
    lines = text.replace("\r\n ", "").split("\r\n")
    assert text.count("BEGIN:VEVENT") == 1
    assert "RRULE:FREQ=WEEKLY;BYDAY=TU;UNTIL=20261103" in lines
    assert "EXDATE;TZID=Asia/Manila:20261020T090000,20261027T090000" in lines
    assert "DTSTART;TZID=Asia/Manila:20261013T090000" in lines


def test_all_day_exdates_use_dates(world):                                                     # noqa: F811
    c = world["conn"]
    e = series(world)
    st.cal_update(c, e, by="x@x", exdates="2026-10-20")
    lines = ics.vcalendar([ics.entry_event(st.cal_get(c, e))]).split("\r\n")
    assert "EXDATE;VALUE=DATE:20261020" in lines


def test_the_feed_has_one_event_for_a_whole_series(world):                                     # noqa: F811
    c = world["conn"]
    today = tz.today_local()
    e = st.cal_create(c, "Weekly", today.isoformat(), rrule=rc.build("weekly", today, today + timedelta(days=60)),
                      people=[(world["s1"]["id"], "attending")], audience="bureau", by="x@x")
    text = oc.build_feed(c, world["s1"], "https://x", scope="mine", today=today)
    assert text.count("BEGIN:VEVENT") == 1 and "RRULE:FREQ=WEEKLY" in text and f"UID:{st.cal_get(c, e)['uid']}" in text


# -------------------------------------------------------------------- pages ---

@pytest.fixture()
def pg(app_mod, viewer):
    c = st.connect(app_mod.DB); st.init_db(c)
    made = []
    yield c, made
    for (i,) in c.execute("SELECT id FROM calendar_entry WHERE title LIKE 'RECTEST %'").fetchall():
        st.cal_delete(c, i)
    c.close()


def post_new(client, **over):
    base = {"title": "RECTEST Standup", "kind": "meeting", "status": "confirmed", "start_date": "2026-10-13",
            "audience": "bureau", "repeat": "weekly", "until": "2026-11-10"}
    return client.post("/calendar/new", content=urlencode({**base, **over}), headers=FORM, follow_redirects=False)


def one(c, title="RECTEST Standup"):
    return c.execute("SELECT id, rrule, exdates FROM calendar_entry WHERE title=? ORDER BY id DESC", (title,)).fetchone()


def test_the_add_form_creates_a_series(app_mod, viewer, pg):
    c, _ = pg
    assert 'name="repeat"' in viewer.get("/calendar/new").text
    r = post_new(viewer)
    assert r.status_code == 303
    eid, rule, ex = one(c)
    assert rule == "FREQ=WEEKLY;BYDAY=TU;UNTIL=20261110" and ex is None
    page = viewer.get(f"/calendar/entries/{eid}").text
    assert "Every Tuesday until Nov 10, 2026" in page and "Cancelling this item cancels the whole series" in page


@pytest.mark.parametrize("over, msg", [({"until": ""}, "last date"), ({"until": "2030-01-01"}, "2 years"),
                                       ({"repeat": "hourly"}, "list"), ({"kind": "travel"}, "trip")])
def test_a_bad_series_shows_an_error_and_saves_nothing(app_mod, viewer, pg, over, msg):
    c, _ = pg
    r = post_new(viewer, **over)
    assert r.status_code == 400 and msg in r.text and one(c) is None


def test_the_edit_form_preselects_the_series_and_can_stop_it(app_mod, viewer, pg):
    c, _ = pg
    post_new(viewer, repeat="monthly_nth", until="2027-03-01")
    eid = one(c)[0]
    html = viewer.get(f"/calendar/entries/{eid}/edit").text
    assert 'value="monthly_nth" selected' in html and 'value="2027-03-01"' in html
    got = st.cal_get(c, eid)
    form = {"title": got["title"], "kind": "meeting", "status": "confirmed", "start_date": got["start_date"], "audience": "bureau",
            "repeat": "none", "until": "", "updated_at": got["updated_at"]}
    assert viewer.post(f"/calendar/entries/{eid}/edit", content=urlencode(form), headers=FORM, follow_redirects=False).status_code == 303
    assert st.cal_get(c, eid)["rrule"] is None


def test_an_occurrence_opens_with_its_actions_and_skip_and_put_back_work(app_mod, viewer, pg):
    c, _ = pg
    post_new(viewer)
    eid = one(c)[0]
    html = viewer.get(f"/calendar/entries/{eid}?date=2026-10-20").text
    assert "Change just this one" in html and "Skip this date" in html and "Tuesday, October 20" in html
    assert "Change just this one" not in viewer.get(f"/calendar/entries/{eid}?date=2026-10-21").text      # not a repeat
    assert viewer.post(f"/calendar/entries/{eid}/skip", content="date=2026-10-20", headers=FORM, follow_redirects=False).status_code == 303
    assert one(c)[2] == "2026-10-20"
    assert "put back" in viewer.get(f"/calendar/entries/{eid}").text
    viewer.post(f"/calendar/entries/{eid}/unskip", content="date=2026-10-20", headers=FORM)
    assert one(c)[2] is None


def test_skip_refuses_a_date_that_is_not_a_repeat(app_mod, viewer, pg):
    c, _ = pg
    post_new(viewer)
    eid = one(c)[0]
    r = viewer.post(f"/calendar/entries/{eid}/skip", content="date=2026-10-21", headers=FORM, follow_redirects=False)
    assert "err=" in r.headers["location"] and one(c)[2] is None
    r = viewer.post(f"/calendar/entries/{eid}/skip", content="date=garbage", headers=FORM, follow_redirects=False)
    assert "err=" in r.headers["location"]


def test_changing_just_one_makes_a_one_off_and_skips_the_date(app_mod, viewer, pg):
    c, _ = pg
    post_new(viewer, venue="Room 5")
    eid = one(c)[0]
    page = viewer.get(f"/calendar/entries/{eid}/detach?date=2026-10-20").text
    assert 'name="detach_from"' in page and "Changing just" in page and 'value="2026-10-20"' in page and "Room 5" in page
    r = post_new(viewer, title="RECTEST Standup (moved)", start_date="2026-10-20", repeat="none", until="",
                 start_time="14:00", detach_from=str(eid), detach_date="2026-10-20")
    assert r.status_code == 303
    assert one(c, "RECTEST Standup (moved)")[1] is None and one(c)[2] == "2026-10-20"
    days = [i["start"] for i in oc.items_between(c, {"id": st.get_admin_user(c, "viewer@test.local")["id"], "username": "viewer@test.local",
                                                      "role": "viewer"}, "2026-10-13", "2026-10-27", scope="bureau", layers=["entries"])
            if i["title"].startswith("RECTEST")]
    assert sorted(days) == ["2026-10-13", "2026-10-20", "2026-10-27"]               # the series' 13th and 27th + the one-off 20th
    assert viewer.get(f"/calendar/entries/{eid}/detach?date=2026-10-21", follow_redirects=False).status_code == 303


def test_a_stale_detach_is_refused_and_creates_nothing(app_mod, viewer, pg):
    c, _ = pg
    post_new(viewer)
    eid = one(c)[0]
    st.cal_update(c, eid, by="x@x", exdates="2026-10-20")                              # someone skipped it meanwhile
    r = post_new(viewer, title="RECTEST Late", start_date="2026-10-20", repeat="none", until="",
                 detach_from=str(eid), detach_date="2026-10-20")
    assert r.status_code == 400 and one(c, "RECTEST Late") is None
