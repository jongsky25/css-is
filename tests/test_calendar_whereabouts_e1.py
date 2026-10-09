"""A trip on the calendar plots Field in the weekly whereabouts, and reported leave shows on the
calendar as "On leave" (office calendar E1)."""
from __future__ import annotations
from datetime import timedelta

import pytest

import office_calendar as oc
import storage as st
import tzutil as tz
from test_calendar_home import world                                  # noqa: F401  (throwaway org + accounts)

MON = tz.today_local() - timedelta(days=tz.today_local().weekday()) + timedelta(days=7)   # next Monday
D = lambda n: (MON + timedelta(days=n)).isoformat()                                         # noqa: E731


def trip(w, who="s1", start=0, end=2, **kw):
    kw.setdefault("kind", "travel"); kw.setdefault("venue", "Palawan"); kw.setdefault("audience", "bureau")
    return st.cal_create(w["conn"], "Palawan monitoring", D(start), end_date=D(end) if end != start else None,
                         people=[(w[who]["id"], "travel")], by="x", **kw)


def week(w, who="s1"):
    return {d["iso"]: d for d in st.whereabouts_week(w["conn"], w[who]["id"], MON)}


# ------------------------------------------------------------ the default ---

def test_a_trip_plots_field_with_its_venue(world):                                             # noqa: F811
    trip(world)
    d = week(world)
    for n in (0, 1, 2):
        assert (d[D(n)]["default"], d[D(n)]["choice"], d[D(n)]["note"]) == ("field", "field", "Palawan")
        assert d[D(n)]["trip"]["title"] == "Palawan monitoring"
    assert (d[D(3)]["choice"], d[D(3)]["note"], d[D(3)]["trip"]) == ("office", "", None)


def test_weekends_and_other_people_get_nothing(world):                                          # noqa: F811
    trip(world, start=4, end=6)                       # Friday to Sunday
    assert set(st.cal_travel_defaults(world["conn"], D(0), D(6))) == {(world["s1"]["id"], D(4))}
    assert week(world, "s1b")[D(4)]["choice"] == "office"


@pytest.mark.parametrize("over", [{"status": "tentative"}, {"status": "postponed"}, {"kind": "meeting"}])
def test_only_a_confirmed_trip_counts(world, over):                                            # noqa: F811
    trip(world, **over)
    assert week(world)[D(0)]["choice"] == "office"


def test_a_cancelled_trip_gives_nothing_back(world):                                           # noqa: F811
    e = trip(world)
    st.cal_cancel(world["conn"], e)
    assert week(world)[D(0)]["choice"] == "office"
    st.cal_restore(world["conn"], e)
    assert week(world)[D(0)]["choice"] == "field"


def test_the_note_falls_back_to_the_title(world):                                              # noqa: F811
    trip(world, venue=None)
    assert week(world)[D(0)]["note"] == "Palawan monitoring"


def test_a_moved_trip_moves_the_default(world):                                                # noqa: F811
    e = trip(world, start=0, end=0)
    st.cal_update(world["conn"], e, start_date=D(2))
    d = week(world)
    assert d[D(0)]["choice"] == "office" and d[D(2)]["choice"] == "field"


def test_the_persons_own_report_always_wins(world):                                            # noqa: F811
    c = world["conn"]
    trip(world)
    st.save_whereabouts_week(c, world["s1"]["id"], MON, {D(0): ("office", ""), D(1): ("field", "Cebu")},
                             today=MON)
    d = week(world)
    assert (d[D(0)]["choice"], d[D(0)]["note"]) == ("office", "")           # said Office despite the trip
    assert (d[D(1)]["choice"], d[D(1)]["note"]) == ("field", "Cebu")
    assert d[D(2)]["choice"] == "field" and d[D(2)]["note"] == "Palawan"      # untouched day: still the default
    st.cal_update(c, st.cal_travel_defaults(c, D(0), D(0))[(world["s1"]["id"], D(0))]["entry_id"],
                  start_date=D(3), end_date=D(4))
    assert week(world)[D(0)]["choice"] == "office" and week(world)[D(1)]["note"] == "Cebu"   # confirmed rows untouched


def test_confirming_the_prefilled_day_saves_a_real_row(world):                                 # noqa: F811
    c = world["conn"]
    trip(world)
    d = week(world)
    st.save_whereabouts_week(c, world["s1"]["id"], MON, {D(0): (d[D(0)]["choice"], d[D(0)]["note"])}, today=MON)
    assert c.execute("SELECT status, note FROM whereabouts WHERE user_id=? AND day=?",
                     (world["s1"]["id"], D(0))).fetchone() == ("field", "Palawan")


def test_defaults_carry_the_trip_for_the_monday_email(world):                                  # noqa: F811
    trip(world)
    assert st.whereabouts_defaults(world["conn"], MON)[world["s1"]["id"]][D(0)][0] == "field"


# ---------------------------------------------------- who's in / roster ---

def cell(w, who, n, viewer="s1"):
    wk = st.whereabouts_roster_week(w["conn"], MON, w[viewer])
    for sec in wk["sections"]:
        for p in sec["people"]:
            if p["user_id"] == w[who]["id"]:
                return p["cells"][n]


def test_the_roster_plots_an_unreported_trip_as_field(world):                                  # noqa: F811
    trip(world)
    mine = cell(world, "s1", 0)
    assert mine["state"] == "field" and mine["plotted"] and mine["note"] == "Palawan"
    assert cell(world, "s1", 3)["state"] != "field"


def test_a_report_beats_the_trip_in_the_roster_and_the_day_view(world):                        # noqa: F811
    c = world["conn"]
    trip(world)
    st.save_whereabouts_week(c, world["s1"]["id"], MON, {D(0): ("office", "")}, today=MON)
    assert cell(world, "s1", 0)["state"] == "onsite"
    day = st.work_arrangement_day(c, MON, world["s1"])
    assert world["s1"]["id"] in {p["user_id"] for p in day["groups"]["onsite"]}


def test_the_day_view_shows_the_trip_as_field(world):                                          # noqa: F811
    trip(world)
    day = st.work_arrangement_day(world["conn"], MON, world["s1"])
    row = next(p for p in day["groups"]["field"] if p["user_id"] == world["s1"]["id"])
    assert row["remarks"] == "Palawan" and row["from_calendar"] and not row["reported"]


def test_a_private_trips_place_stays_private(world):                                           # noqa: F811
    trip(world, audience="people")
    assert cell(world, "s1", 0)["state"] == "field" and cell(world, "s1", 0)["note"] == ""
    day = st.work_arrangement_day(world["conn"], MON, world["s1"])
    assert next(p for p in day["groups"]["field"] if p["user_id"] == world["s1"]["id"])["remarks"] == ""
    assert week(world)[D(0)]["note"] == "Palawan"                      # but the person sees their own


# ------------------------------------------------------------- leave layer ---

def leave(w, who, *days):
    for n in days:
        w["conn"].execute("INSERT OR REPLACE INTO whereabouts(user_id, day, status, note, updated_at) "
                          "VALUES (?,?,?,?,?)", (w[who]["id"], D(n), "leave", None, "x"))
    w["conn"].commit()


def items(w, viewer, scope="bureau", a=0, b=13):
    return [i for i in oc.items_between(w["conn"], w[viewer], D(a), D(b), scope=scope, layers=["leave"])]


def test_your_own_leave_is_a_bar_with_no_reason(world):                                        # noqa: F811
    leave(world, "s1", 1, 2)
    got = items(world, "s1", "blend")
    assert [(i["start"], i["end"], i["kind"], i["layer"]) for i in got] == [(D(1), D(2), "leave", "leave")]
    assert got[0]["title"].endswith("— on leave") and got[0]["people"][0]["user_id"] == world["s1"]["id"]


def test_leave_runs_join_across_a_weekend_only(world):                                         # noqa: F811
    leave(world, "s1", 3, 4, 7, 8, 10)                # Thu-Fri + Mon-Tue (one run), Thu (another)
    assert [(i["start"], i["end"]) for i in items(world, "s1")] == [(D(3), D(8)), (D(10), D(10))]


def who(got):
    return sorted(i["people"][0]["user_id"] for i in got)


def test_colleagues_leave_follows_the_whos_in_visibility(world):                              # noqa: F811
    leave(world, "s1", 1); leave(world, "s1b", 1); leave(world, "s3", 1)
    ids = lambda *k: sorted(world[x]["id"] for x in k)                                          # noqa: E731
    assert who(items(world, "s1", "bureau")) == ids("s1", "s1b")           # my section only, not S3's
    assert who(items(world, "s3", "bureau")) == ids("s3")
    assert who(items(world, "dir", "bureau")) == ids("s1", "s1b", "s3")    # the Director's team is the bureau
    assert who(items(world, "s1", "blend")) == who(items(world, "s1", "mine")) == ids("s1")
    assert who(items(world, "s1", "section")) == ids("s1", "s1b")
    assert who(items(world, "dir", "section")) == []                       # the Director has no section
    assert who(items(world, "nobody", "bureau")) == []                     # unlinked: no team, no leave


def test_leave_shows_on_the_calendar_page_and_never_a_reason(world):                           # noqa: F811
    world["conn"].execute("INSERT OR REPLACE INTO whereabouts(user_id, day, status, note, updated_at) "
                          "VALUES (?,?,?,?,?)", (world["s1"]["id"], D(1), "leave", "secret reason", "x"))
    world["conn"].commit()
    got = oc.items_between(world["conn"], world["s1"], D(0), D(4), scope="mine")
    assert any(i["layer"] == "leave" for i in got)
    assert "secret reason" not in repr(got)


def test_archived_and_inactive_people_drop_off(world):                                         # noqa: F811
    leave(world, "s1b", 1)
    world["conn"].execute("UPDATE admin_user SET active=0 WHERE id=?", (world["s1b"]["id"],))
    world["conn"].commit()
    assert who(items(world, "s1", "bureau")) == []


# ---------------------------------------------------------------- pages ---

def test_the_form_opens_already_showing_the_trip(app_mod, viewer):
    c = st.connect(app_mod.DB); st.init_db(c)
    uid = st.get_admin_user(c, "viewer@test.local")["id"]
    this = st.whereabouts_week_start()
    e = st.cal_create(c, "E1PAGE Visayas trip", this.isoformat(), kind="travel", venue="Iloilo",
                      people=[(uid, "travel")], audience="bureau", by="x")
    try:
        html = viewer.get(f"/work-arrangement/week?week={this.isoformat()}").text
        assert "Filled in from the calendar: E1PAGE Visayas trip" in html and 'value="Iloilo"' in html
        viewer.post("/work-arrangement/week", data={"week": this.isoformat(), f"s_{this.isoformat()}": "field",
                                                    f"n_{this.isoformat()}": "Iloilo"})
        again = viewer.get(f"/work-arrangement/week?week={this.isoformat()}").text
        assert "Filled in from the calendar" not in again            # now it is their own word
    finally:
        st.cal_delete(c, e)
        c.execute("DELETE FROM whereabouts WHERE user_id=? AND day=?", (uid, this.isoformat()))
        c.commit(); c.close()
