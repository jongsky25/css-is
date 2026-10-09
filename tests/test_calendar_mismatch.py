"""Soft mismatches between the calendar and what people reported, and "Add this trip to the
calendar" (office calendar E2)."""
from __future__ import annotations
from datetime import timedelta

import pytest

import office_calendar as oc
import office_connect as oconn
import storage as st
import tzutil as tz
from test_calendar_home import world                                  # noqa: F401  (throwaway org + accounts)

MON = tz.today_local() - timedelta(days=tz.today_local().weekday()) + timedelta(days=7)
D = lambda n: (MON + timedelta(days=n)).isoformat()                                         # noqa: E731


def report(w, who, n, status, note=None):
    w["conn"].execute("INSERT OR REPLACE INTO whereabouts(user_id, day, status, note, updated_at) VALUES (?,?,?,?,?)",
                      (w[who]["id"], D(n), status, note, "x"))
    w["conn"].commit()


def entry(w, who, title, a=0, b=None, **kw):
    kw.setdefault("audience", "bureau")
    return st.cal_create(w["conn"], title, D(a), end_date=D(b) if b not in (None, a) else None,
                         people=[(w[who]["id"], kw.pop("role", "attending"))], by="x", **kw)


def kinds(w, *who):
    return sorted((m["kind"], m["day"]) for m in oc.mismatches(w["conn"], [w[x]["id"] for x in who], D(0), D(4)))


def test_a_trip_reported_as_office_is_a_mismatch(world):                                       # noqa: F811
    entry(world, "s1", "Palawan", 0, 2, kind="travel", venue="Palawan", role="travel")
    report(world, "s1", 0, "office"); report(world, "s1", 1, "leave"); report(world, "s1", 2, "field")
    assert kinds(world, "s1") == [("trip_conflict", D(0)), ("trip_conflict", D(1))]


def test_nothing_reported_or_reported_field_is_no_mismatch(world):                             # noqa: F811
    entry(world, "s1", "Palawan", 0, 1, kind="travel", role="travel")
    report(world, "s1", 1, "field", "Puerto")
    assert kinds(world, "s1") == []


def test_a_tentative_or_cancelled_trip_is_no_mismatch(world):                                  # noqa: F811
    t = entry(world, "s1", "Maybe trip", 0, kind="travel", status="tentative", role="travel")
    c = entry(world, "s1", "Gone trip", 1, kind="travel", role="travel")
    st.cal_cancel(world["conn"], c)
    report(world, "s1", 0, "office"); report(world, "s1", 1, "office")
    assert kinds(world, "s1") == []


def test_leave_on_a_day_listed_on_an_entry(world):                                             # noqa: F811
    entry(world, "s1", "Orientation", 2, kind="meeting")
    report(world, "s1", 2, "leave"); report(world, "s1", 3, "leave")
    assert kinds(world, "s1") == [("leave_on_entry", D(2))]
    cancelled = entry(world, "s1", "Cancelled mtg", 3, kind="meeting")
    st.cal_cancel(world["conn"], cancelled)
    assert kinds(world, "s1") == [("leave_on_entry", D(2))]


def test_a_trip_on_leave_is_one_mismatch_not_two(world):                                       # noqa: F811
    entry(world, "s1", "Palawan", 1, kind="travel", role="travel")
    report(world, "s1", 1, "leave")
    assert kinds(world, "s1") == [("trip_conflict", D(1))]


def test_double_booking_needs_overlapping_times(world):                                        # noqa: F811
    entry(world, "s1", "A", 0, start_time="09:00", end_time="10:30")
    entry(world, "s1", "B", 0, start_time="10:00", end_time="11:00")
    entry(world, "s1", "C", 0, start_time="10:30", end_time="11:30")        # touches A's end: fine
    entry(world, "s1", "All day", 0)                                         # untimed: never
    got = [m for m in oc.mismatches(world["conn"], [world["s1"]["id"]], D(0), D(4)) if m["kind"] == "double_booked"]
    assert sorted((m["title"], m["other_title"]) for m in got) == [("A", "B"), ("B", "C")]


def test_other_peoples_days_are_not_mine(world):                                               # noqa: F811
    entry(world, "s1", "Palawan", 0, kind="travel", role="travel")
    report(world, "s1", 0, "office")
    assert kinds(world, "s1b") == []


# ----------------------------------------------------------- entry heads-up ---

def test_heads_up_goes_to_the_person_the_lead_and_the_creator_only(world):                     # noqa: F811
    c = world["conn"]
    e = st.cal_create(c, "Field visit", D(1), kind="travel", audience="bureau", by="creator@x",
                      people=[(world["s1"]["id"], "travel"), (world["s1b"]["id"], "lead"), (world["s3"]["id"], "travel")])
    report(world, "s1", 1, "office")
    ent = st.cal_get(c, e)
    assert oc.entry_heads_up(c, world["s1"], ent) == ["You: On Field visit, but reported Office (%s)." % _fmt(D(1))]
    assert len(oc.entry_heads_up(c, world["s1b"], ent)) == 1                    # the lead
    assert len(oc.entry_heads_up(c, {"id": 999, "username": "creator@x"}, ent)) == 1
    assert oc.entry_heads_up(c, world["s3"], ent) == []                         # another attendee
    assert oc.entry_heads_up(c, world["dir"], ent) == []                        # a viewer


def _fmt(iso):
    from datetime import date
    d = date.fromisoformat(iso)
    return f"{d.strftime('%a, %b')} {d.day}"


# -------------------------------------------------------------- home task ---

def test_the_home_task_points_at_the_week_to_fix(world):                                       # noqa: F811
    c = world["conn"]
    entry(world, "s1", "Palawan", 0, 1, kind="travel", role="travel")
    report(world, "s1", 0, "office"); report(world, "s1", 1, "leave")
    t = oconn._task_whereabouts_mismatch(c, world["s1"], MON - timedelta(days=3))
    assert t["tone"] == "todo" and "+1 more" in t["detail"] and t["url"].endswith(f"week={MON.isoformat()}")
    assert oconn._task_whereabouts_mismatch(c, world["s1b"], MON - timedelta(days=3)) is None


# ------------------------------------------------------------ trip offers ---

def day(iso, saved, note="", trip=None, holiday=None):
    return {"iso": iso, "saved": saved, "note": note, "trip": trip, "holiday": holiday}


def test_offers_are_runs_of_the_same_reported_place_without_a_trip():
    days = [day(D(0), "field", "Cebu"), day(D(1), "field", "cebu"), day(D(2), "field", "Bohol"),
            day(D(3), "field", ""), day(D(4), "office")]
    assert [(o["start"], o["end"], o["note"]) for o in st.whereabouts_trip_offers(days)] == [
        (D(0), D(1), "Cebu"), (D(2), D(2), "Bohol")]


def test_nothing_is_offered_for_a_covered_or_holiday_or_unsaved_day():
    days = [day(D(0), "field", "Cebu", trip={"title": "x"}), day(D(1), None, "Cebu"),
            day(D(2), "field", "Cebu", holiday={"name": "h"})]
    assert st.whereabouts_trip_offers(days) == []


@pytest.fixture()
def page(app_mod, viewer):
    c = st.connect(app_mod.DB); st.init_db(c)
    uid = st.get_admin_user(c, "viewer@test.local")["id"]
    this = st.whereabouts_week_start()
    yield c, uid, this
    c.execute("DELETE FROM calendar_entry WHERE source='whereabouts' AND title LIKE 'E2PAGE %'")
    c.execute("DELETE FROM whereabouts WHERE user_id=?", (uid,))
    for (i,) in c.execute("SELECT id FROM calendar_entry WHERE title LIKE 'E2PAGE %'").fetchall():
        st.cal_delete(c, i)
    c.commit(); c.close()


def test_reporting_field_offers_the_trip_and_one_tap_adds_it(app_mod, viewer, page):
    c, uid, this = page
    d0 = this.isoformat()
    viewer.post("/work-arrangement/week", data={"week": d0, f"s_{d0}": "field", f"n_{d0}": "E2PAGE Bicol"})
    html = viewer.get(f"/work-arrangement/week?week={d0}").text
    assert "Add this trip to the calendar" in html and "E2PAGE Bicol" in html
    r = viewer.post("/work-arrangement/week/add-trip", data={"week": d0, "start": d0, "end": d0})
    assert r.status_code == 200 and "to the calendar" in r.text
    row = c.execute("SELECT kind, source, venue, audience FROM calendar_entry WHERE title='E2PAGE Bicol'").fetchone()
    assert row == ("travel", "whereabouts", "E2PAGE Bicol", "unit")
    assert c.execute("SELECT COUNT(*) FROM calendar_entry_person cp JOIN calendar_entry e ON e.id=cp.entry_id "
                     "WHERE e.title='E2PAGE Bicol' AND cp.user_id=?", (uid,)).fetchone()[0] == 1
    assert "Add this trip to the calendar" not in viewer.get(f"/work-arrangement/week?week={d0}").text   # now covered
    again = viewer.post("/work-arrangement/week/add-trip", data={"week": d0, "start": d0, "end": d0})
    assert again.status_code == 400 and c.execute("SELECT COUNT(*) FROM calendar_entry WHERE title='E2PAGE Bicol'").fetchone()[0] == 1


def test_a_forged_trip_is_refused(app_mod, viewer, page):
    c, uid, this = page
    d0 = this.isoformat()
    r = viewer.post("/work-arrangement/week/add-trip", data={"week": d0, "start": d0, "end": d0})
    assert r.status_code == 400
    assert c.execute("SELECT COUNT(*) FROM calendar_entry WHERE source='whereabouts' AND created_by='viewer@test.local'"
                     ).fetchone()[0] == 0


def test_the_form_warns_when_the_report_disagrees_with_a_trip(app_mod, viewer, page):
    c, uid, this = page
    d0 = this.isoformat()
    st.cal_create(c, "E2PAGE Iloilo", d0, kind="travel", venue="Iloilo", people=[(uid, "travel")],
                  audience="bureau", by="x")
    viewer.post("/work-arrangement/week", data={"week": d0, f"s_{d0}": "office"})
    html = viewer.get(f"/work-arrangement/week?week={d0}").text
    assert "The calendar has you on" in html and "E2PAGE Iloilo" in html and "you reported Office" in html
