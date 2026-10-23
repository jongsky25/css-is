"""Conference room R10: repeat-weekly requests (service rules)."""
from __future__ import annotations
from datetime import date

import pytest

import rooms
import rooms_notify as rn
import storage as st
from conftest import join_admin_section

MON = date(2030, 3, 4)
THU = date(2030, 3, 7)


@pytest.fixture()
def conn(tmp_path):
    c = st.connect(str(tmp_path / "s.db")); st.init_db(c); rooms.ensure_slots(c)
    return c


@pytest.fixture()
def me(conn):
    return st.create_admin_user(conn, "me@test.local", "x", "y", "viewer")


@pytest.fixture()
def boss(conn):
    return join_admin_section(conn, st.create_admin_user(conn, "boss@test.local", "x", "y", "admin"))


def S(conn, *hours):
    by = {s["start_time"]: s["id"] for s in rooms.list_slots(conn)}
    return [by[f"{h:02d}:00"] for h in hours]


def series(conn, me, every=1, until=date(2030, 4, 4), skip_bad=False, hours=(9, 10), **kw):
    return rooms.request_series(conn, every_weeks=every, until=until, skip_bad=skip_bad, title="Weekly huddle", day=THU,
                                slot_ids=S(conn, *hours), requester_user_id=me, today=MON, **kw)


def notices(conn, kind):
    return conn.execute("SELECT user_id, reservation_id, text FROM room_notice WHERE kind=? ORDER BY id", (kind,)).fetchall()


def test_the_dates_of_a_repeat():
    assert [d.isoformat() for d in rooms.series_dates(THU, 1, date(2030, 3, 28))] == ["2030-03-07", "2030-03-14", "2030-03-21", "2030-03-28"]
    assert [d.isoformat() for d in rooms.series_dates(THU, 2, date(2030, 4, 30))] == ["2030-03-07", "2030-03-21", "2030-04-04", "2030-04-18"]
    assert len(rooms.series_dates(THU, 1, date(2031, 12, 31))) == rooms.MAX_SERIES                    # capped
    assert rooms.series_dates(THU, 1, date(2030, 3, 7)) == [THU]


def test_a_series_is_filed_as_linked_requests(conn, me):
    out = series(conn, me)
    rs = out["reservations"]
    assert [r["day"] for r in rs] == ["2030-03-07", "2030-03-14", "2030-03-21", "2030-03-28", "2030-04-04"]
    assert {r["series_id"] for r in rs} == {rs[0]["id"]} and all(r["status"] == "requested" for r in rs)
    assert all(r["slot_ids"] == S(conn, 9, 10) for r in rs) and out["skipped"] == []
    ss = rooms.series_summary(conn, rs[2])
    assert ss == {"total": 5, "open": 5, "approved": 0}
    assert rooms.series_summary(conn, rooms.request(conn, title="x", day=date(2030, 5, 2), slot_ids=S(conn, 13), requester_user_id=me, today=MON)) is None


def test_the_section_is_told_once_not_once_per_date(conn, me, boss):
    series(conn, me)
    n = notices(conn, "new_request")
    assert len(n) == 1 and n[0][0] == boss and "(+4 more dates in this repeating request)" in n[0][2]


def test_bad_dates_are_listed_and_nothing_is_filed(conn, me):
    st.set_holiday(conn, "2030-03-14", "Test holiday")
    other = st.create_admin_user(conn, "o@test.local", "x", "y", "viewer")
    held = rooms.request(conn, title="Held", day=date(2030, 3, 21), slot_ids=S(conn, 10), requester_user_id=other, today=MON)
    rooms.approve(conn, held["id"], "boss@test.local", today=MON)
    rooms.add_block(conn, "boss@test.local", date(2030, 3, 28), None, "Repairs", today=MON)
    with pytest.raises(rooms.SeriesIssues) as e:
        series(conn, me)
    plan = {p["day"]: p for p in e.value.plan}
    assert [p["ok"] for p in e.value.plan] == [True, False, False, False, True]
    assert "Test holiday" in plan["2030-03-14"]["reason"] and "already booked" in plan["2030-03-21"]["reason"] and "unavailable" in plan["2030-03-28"]["reason"]
    assert conn.execute("SELECT COUNT(*) FROM room_reservation WHERE title='Weekly huddle'").fetchone()[0] == 0


def test_requesting_only_the_dates_that_work(conn, me):
    st.set_holiday(conn, "2030-03-14", "Test holiday")
    out = series(conn, me, skip_bad=True)
    assert [r["day"] for r in out["reservations"]] == ["2030-03-07", "2030-03-21", "2030-03-28", "2030-04-04"]
    assert [p["day"] for p in out["skipped"]] == ["2030-03-14"]


def test_no_date_works_and_bad_input(conn, me):
    with pytest.raises(rooms.SeriesIssues, match="None of those"):
        rooms.request_series(conn, every_weeks=1, until=date(2030, 3, 7), skip_bad=True, title="x", day=date(2030, 3, 5),
                             slot_ids=S(conn, 9), requester_user_id=me, today=MON, meals_requested=True)  # meals need two calendar days
    with pytest.raises(rooms.RoomError, match="every week or every 2 weeks"):
        series(conn, me, every=3)
    with pytest.raises(rooms.RoomError, match="end on or after"):
        series(conn, me, until=date(2030, 3, 1))
    with pytest.raises(rooms.RoomError, match="title"):
        rooms.request_series(conn, every_weeks=1, until=date(2030, 3, 28), title=" ", day=THU, slot_ids=S(conn, 9), requester_user_id=me, today=MON)
    assert conn.execute("SELECT COUNT(*) FROM room_reservation").fetchone()[0] == 0


def test_a_series_of_one_is_just_a_request(conn, me):
    out = series(conn, me, until=THU)
    assert len(out["reservations"]) == 1 and rooms.series_summary(conn, out["reservations"][0]) is None


def test_every_date_carries_the_meals_form(conn, me):
    out = series(conn, me, until=date(2030, 3, 14), meals_requested=True, attendees=12)
    import rooms_meals as rm
    assert all(rm.get_form(conn, r["id"])["pax"] == 12 for r in out["reservations"])


def test_approving_the_whole_series_tells_the_requester_once(conn, me, boss):
    rs = series(conn, me)["reservations"]
    out = rooms.approve_series(conn, rs[1]["id"], "boss@test.local", "ok", today=MON)               # from any date in it
    assert len(out["approved"]) == 5 and out["skipped"] == []
    assert {rooms.get_reservation(conn, r["id"])["status"] for r in rs} == {"approved"}
    n = notices(conn, "approved")
    assert len(n) == 1 and n[0][0] == me and "(+4 more dates in this repeating request)" in n[0][2]
    with pytest.raises(rooms.RoomError, match="Nothing in this series"):
        rooms.approve_series(conn, rs[0]["id"], "boss@test.local", today=MON)


def test_a_date_something_else_holds_is_skipped_and_reported_never_forced(conn, me, boss):
    rs = series(conn, me)["reservations"]
    other = st.create_admin_user(conn, "o@test.local", "x", "y", "viewer")
    rooms.approve(conn, rooms.request(conn, title="Held", day=date(2030, 3, 21), slot_ids=S(conn, 9), requester_user_id=other, today=MON)["id"],
                  "boss@test.local", today=MON)
    out = rooms.approve_series(conn, rs[0]["id"], "boss@test.local", today=MON)
    assert len(out["approved"]) == 4 and [m["day"] for m, _why in out["skipped"]] == ["2030-03-21"]
    assert "already approved" in out["skipped"][0][1] or "Another reservation" in out["skipped"][0][1]
    assert rooms.get_reservation(conn, rs[2]["id"])["status"] == "requested"                        # still waiting, to be decided on its own


def test_declining_the_whole_series_with_one_reason(conn, me, boss):
    rs = series(conn, me, until=date(2030, 3, 21))["reservations"]
    with pytest.raises(rooms.RoomError, match="reason"):
        rooms.decline_series(conn, rs[0]["id"], "boss@test.local", " ")
    out = rooms.decline_series(conn, rs[0]["id"], "boss@test.local", "Room is for training")
    assert len(out["declined"]) == 3 and {rooms.get_reservation(conn, r["id"])["decide_note"] for r in rs} == {"Room is for training"}
    assert len(notices(conn, "declined")) == 1


def test_one_date_can_still_be_decided_alone(conn, me, boss):
    rs = series(conn, me, until=date(2030, 3, 21))["reservations"]
    rooms.decline(conn, rs[1]["id"], "boss@test.local", "Not that week")
    assert [rooms.get_reservation(conn, r["id"])["status"] for r in rs] == ["requested", "declined", "requested"]
    assert rooms.series_summary(conn, rs[0]) == {"total": 3, "open": 2, "approved": 0}


def test_the_queue_shows_the_series(conn, me, boss):
    series(conn, me, until=date(2030, 3, 21))
    assert [q["series"]["open"] for q in rooms.queue(conn)] == [3, 3, 3]


def test_withdrawing_the_whole_series_from_today_on(conn, me, boss):
    rs = series(conn, me)["reservations"]
    rooms.approve_series(conn, rs[0]["id"], "boss@test.local", today=MON)
    assert rooms.withdraw_series(conn, rs[0]["id"], me, "Cancelled for good", today=date(2030, 3, 15)) == 3          # the past two stay
    assert [rooms.get_reservation(conn, r["id"])["status"] for r in rs] == ["approved", "approved", "withdrawn", "withdrawn", "withdrawn"]
    other = st.create_admin_user(conn, "o@test.local", "x", "y", "viewer")
    with pytest.raises(rooms.RoomError, match="your own"):
        rooms.withdraw_series(conn, rs[0]["id"], other, today=MON)
    with pytest.raises(rooms.RoomError, match="nothing left"):
        rooms.withdraw_series(conn, rs[0]["id"], me, today=date(2030, 4, 30))
