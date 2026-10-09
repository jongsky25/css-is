"""Conference room R7: the Rooms layer on the Office calendar, its filters, the API and the personal feed."""
from __future__ import annotations
from datetime import date, timedelta

import pytest

import calendar_ics as cics
import office_calendar as oc
import rooms
import storage as st
from test_calendar_home import world                                  # noqa: F401  (throwaway org + accounts)

MON = date(2030, 3, 4)
THU = date(2030, 3, 7)


def S(conn, *hours):
    by = {s["start_time"]: s["id"] for s in rooms.list_slots(conn)}
    return [by[f"{h:02d}:00"] for h in hours]


@pytest.fixture()
def w(world):                                                          # noqa: F811
    rooms.ensure_slots(world["conn"])
    world["boss"] = {"id": st.create_admin_user(world["conn"], "boss@test.local", "x", "y", "admin"),
                     "username": "boss@test.local", "role": "admin"}
    return world


def book(w, who="s1", hours=(9, 10), title="Planning", approve=True, day=THU):
    r = rooms.request(w["conn"], title=title, day=day, slot_ids=S(w["conn"], *hours),
                      requester_user_id=w[who]["id"], today=MON)
    return rooms.approve(w["conn"], r["id"], "boss@test.local", today=MON) if approve else r


def items(w, who, scope="blend", layers=("rooms",), **kw):
    return oc.items_between(w["conn"], w[who], THU, THU, scope=scope, layers=list(layers) if layers else None, **kw)


# --------------------------------------------------------------- who sees what ---

def test_an_approved_booking_is_visible_to_everyone_signed_in(w):
    book(w, title="Budget review")
    for who in ("s1", "s1b", "s3", "dir", "nobody"):                  # same unit, other unit, leadership, unlinked
        got = items(w, who)
        assert [i["title"] for i in got] == ["Budget review"], who
    assert [i["title"] for i in items(w, "s3", scope="bureau")] == ["Budget review"]


def test_a_pending_request_is_visible_only_to_the_requester_and_the_deciders(w):
    book(w, title="Not yet", approve=False)
    assert [i["status"] for i in items(w, "s1")] == ["tentative"]       # the requester
    assert [i["status"] for i in items(w, "boss")] == ["tentative"]      # a room approver (admin role fallback)
    for who in ("s1b", "s3", "dir", "nobody"):
        assert items(w, who) == [], who


def test_mine_shows_only_your_own_bookings(w):
    book(w, "s1", (9,), title="Mine"); book(w, "s3", (13,), title="Theirs")
    assert [i["title"] for i in items(w, "s1", scope="mine")] == ["Mine"]
    assert [i["title"] for i in items(w, "s1")] == ["Mine", "Theirs"]


def test_bookings_that_went_away_are_not_shown(w):
    a = book(w, "s1", (9,), title="Withdrawn"); rooms.withdraw(w["conn"], a["id"], w["s1"]["id"])
    b = rooms.request(w["conn"], title="Declined", day=THU, slot_ids=S(w["conn"], 11), requester_user_id=w["s1"]["id"], today=MON)
    rooms.decline(w["conn"], b["id"], "boss@test.local", "no")
    c = book(w, "s1", (13,), title="Cancelled")
    rooms.add_block(w["conn"], "boss@test.local", THU, None, "Fumigation", confirm=True, today=MON)
    assert items(w, "boss") == []


# ----------------------------------------------------------------- the item ---

def test_the_item_carries_the_hours_the_requesters_unit_and_a_link(w):
    b = book(w, "s1", (9, 10), title="Budget review")
    (i,) = items(w, "s3")
    assert (i["layer"], i["kind"], i["status"], i["key"]) == ("rooms", "room", "confirmed", f"room:{b['id']}")
    assert (i["start"], i["end"], i["start_time"], i["end_time"], i["all_day"]) == ("2030-03-07", "2030-03-07", "09:00", "11:00", False)
    assert i["venue"] == "Conference room" and i["url"] == "/rooms?week=2030-03-07" and not i["editable"]
    assert i["owner_label"] == "S1" and i["owner_org_id"] == w["unit"]["T/D1/S1"] and i["tone"] in oc.UNIT_TONES
    assert [p["user_id"] for p in i["people"]] == [w["s1"]["id"]] and i["flags"] == []


def test_a_staff_member_with_no_directory_unit_is_not_called_a_guest(w):
    book(w, "nobody", title="Unlinked")
    (i,) = items(w, "s1")
    assert i["owner_label"] == "" and i["owner_org_id"] is None


def test_a_pending_item_says_it_awaits_approval(w):
    book(w, title="Not yet", approve=False)
    (i,) = items(w, "s1")
    assert i["status"] == "tentative" and i["flags"] == ["awaiting approval"]


def test_a_guest_booking_shows_the_organisation_and_no_contact_details(w):
    r = rooms.request_external(w["conn"], name="Ana Cruz", org="Partner NGO", email="ana@ngo.org", phone="0917 555 1234",
                               title="Site visit", day=THU, slot_ids=S(w["conn"], 13), consent=True, today=MON)
    rooms.approve(w["conn"], r["id"], "boss@test.local", today=MON)
    (i,) = items(w, "s1")
    assert i["owner_label"] == "Guest · Partner NGO" and i["people"] == [] and i["tone"] == "grey"
    assert "ana@ngo.org" not in str(i) and "0917" not in str(i) and "Ana Cruz" not in str(i)


def test_other_layers_and_the_emails_are_unaffected(w):
    book(w)
    assert items(w, "s1", layers=("entries", "activities")) == []        # what emails, the home card and answers ask for
    assert [i["layer"] for i in items(w, "s1", layers=None)] == ["rooms"]  # the page asks for everything


def test_filtering_by_kind(w):
    book(w, title="Room thing")
    st.cal_create(w["conn"], "A meeting", THU.isoformat(), audience="bureau", by="x")
    got = items(w, "s1", layers=None, filters={"kinds": {"room"}})
    assert [i["title"] for i in got] == ["Room thing"]


def test_a_database_without_the_room_tables_just_has_no_rooms(w):
    w["conn"].execute("DROP TABLE room_reservation_slot"); w["conn"].execute("DROP TABLE room_reservation"); w["conn"].commit()
    assert items(w, "s1") == []


# ----------------------------------------------------------------- the feed ---

def test_my_bookings_reach_my_calendar_app_and_the_ones_that_went_away_are_cancelled(w):
    ok = book(w, "s1", (9, 10), title="Approved one", day=date(2030, 3, 11))
    pend = book(w, "s1", (13,), title="Pending one", approve=False, day=date(2030, 3, 11))
    gone = book(w, "s1", (15,), title="Withdrawn one", day=date(2030, 3, 11)); rooms.withdraw(w["conn"], gone["id"], w["s1"]["id"])
    other = book(w, "s3", (11,), title="Someone elses", day=date(2030, 3, 11))
    feed = oc.build_feed(w["conn"], w["s1"], "https://x.test", today=MON)
    ev = {e.split("SUMMARY:")[1].split("\r\n")[0]: e for e in feed.split("BEGIN:VEVENT")[1:]}
    assert "Someone elses" not in ev
    assert f"UID:room-{ok['id']}@office-connect" in ev["Approved one"] and "STATUS:CONFIRMED" in ev["Approved one"]
    assert "STATUS:TENTATIVE" in ev["Pending one"] and "STATUS:CANCELLED" in ev["Withdrawn one"]
    assert "DTSTART;TZID=" in ev["Approved one"] and "LOCATION:Conference room" in ev["Approved one"]


def test_the_feed_and_the_approval_email_share_one_uid(w):
    b = book(w)
    res = rooms.get_reservation(w["conn"], b["id"])
    assert oc.room_event(res, ("09:00", "11:00"))["uid"] == f"room-{b['id']}@office-connect"
    assert f"UID:room-{b['id']}@office-connect" in oc.build_feed(w["conn"], w["s1"], "", today=MON)


def test_a_booking_changed_later_gets_a_higher_sequence(w):
    b = book(w, day=date(2030, 3, 11))
    res = rooms.get_reservation(w["conn"], b["id"])
    first = oc.room_event(res, ("09:00", "11:00"))["sequence"]
    w["conn"].execute("UPDATE room_reservation SET updated_at='2030-03-05T10:00:00' WHERE id=?", (b["id"],)); w["conn"].commit()
    assert oc.room_event(rooms.get_reservation(w["conn"], b["id"]), ("09:00", "11:00"))["sequence"] > first
