"""Conference room R8: the link with CSS activities (service rules)."""
from __future__ import annotations
from datetime import date

import pytest

import rooms
import storage as st

MON = date(2030, 3, 4)
THU = date(2030, 3, 7)
NEXT_THU = date(2030, 3, 14)


@pytest.fixture()
def conn(tmp_path):
    c = st.connect(str(tmp_path / "a.db")); st.init_db(c); rooms.ensure_slots(c)
    return c


@pytest.fixture()
def me(conn):
    uid = st.create_admin_user(conn, "me@test.local", "x", "y", "section_manager")
    return {"id": uid, "username": "me@test.local", "role": "section_manager"}


@pytest.fixture()
def other(conn):
    uid = st.create_admin_user(conn, "other@test.local", "x", "y", "viewer")
    return {"id": uid, "username": "other@test.local", "role": "viewer"}


@pytest.fixture()
def boss(conn):
    uid = st.create_admin_user(conn, "boss@test.local", "x", "y", "admin")
    return {"id": uid, "username": "boss@test.local", "role": "admin"}


def S(conn, *hours):
    by = {s["start_time"]: s["id"] for s in rooms.list_slots(conn)}
    return [by[f"{h:02d}:00"] for h in hours]


def event(conn, day=THU, title="Quarterly review", modality="f2f"):
    f2 = st.create_form_instance(conn, survey_type=2, form="F2", event_date=day.isoformat(), end_date=None,
                                 venue=None, modality=modality, topic=title, lead_org_id=None, created_by="me@test.local")
    return st.create_event(conn, title, day.isoformat(), venue=None, modality=modality, organizer="x",
                           lead_org_id=None, form_instance_ids=[f2], created_by="me@test.local")


def book(conn, user, ev=None, day=THU, hours=(9, 10), approve=True, title="Quarterly review"):
    r = rooms.request(conn, title=title, day=day, slot_ids=S(conn, *hours), requester_user_id=user["id"], today=MON,
                      event_id=ev["id"] if ev else None)
    return rooms.approve(conn, r["id"], "boss@test.local", today=MON) if approve else r


def status(conn, ev, user, today=MON):
    return rooms.activity_room_status(conn, st.get_event_by_id(conn, ev["id"]), user, today)


# --------------------------------------------------------------------- precheck ---

def test_precheck_says_what_request_would_say_and_writes_nothing(conn, me):
    assert rooms.precheck(conn, THU, S(conn, 9, 10), MON) == S(conn, 9, 10)
    with pytest.raises(rooms.RoomError, match="notice"):
        rooms.precheck(conn, date(2030, 3, 5), S(conn, 9), MON)
    with pytest.raises(rooms.RoomError, match="back-to-back"):
        rooms.precheck(conn, THU, S(conn, 9, 11), MON)
    book(conn, me)
    with pytest.raises(rooms.SlotTaken, match="already booked"):
        rooms.precheck(conn, THU, S(conn, 10), MON)
    assert conn.execute("SELECT COUNT(*) FROM room_reservation").fetchone()[0] == 1


# ------------------------------------------------------------------- linking ---

def test_a_request_can_be_tied_to_an_activity_at_the_start(conn, me):
    ev = event(conn)
    r = book(conn, me, ev)
    assert r["event_id"] == ev["id"] and [x["id"] for x in rooms.reservations_for_event(conn, ev["id"])] == [r["id"]]


def test_linking_rules(conn, me, other, boss):
    ev, ev2 = event(conn), event(conn, title="Another")
    r = book(conn, me, approve=False)
    with pytest.raises(rooms.RoomError, match="isn't yours"):
        rooms.link_event(conn, r["id"], ev["id"], other)
    assert rooms.link_event(conn, r["id"], ev["id"], me)["event_id"] == ev["id"]
    with pytest.raises(rooms.RoomError, match="already linked"):
        rooms.link_event(conn, r["id"], ev2["id"], boss)                 # even a room approver can't steal it
    rooms.withdraw(conn, r["id"], me["id"])
    with pytest.raises(rooms.RoomError, match="can't be linked"):
        rooms.link_event(conn, r["id"], ev["id"], me)


def test_a_room_approver_may_link_someone_elses(conn, me, boss):
    ev = event(conn)
    r = book(conn, me, approve=False)
    assert rooms.link_event(conn, r["id"], ev["id"], boss)["event_id"] == ev["id"]


def test_prefill_from_a_reservation(conn, me, other, boss):
    r = book(conn, me, title="Budget hearing")
    got = rooms.prefill_activity(conn, r["id"], me)
    assert got == {"activity_name": "Budget hearing", "event_date": "2030-03-07", "modality": "f2f", "venue": "Conference room",
                   "from_room": r["id"], "from_room_ref": r["ref_code"]}
    assert rooms.prefill_activity(conn, r["id"], boss)                                  # the section may
    assert rooms.prefill_activity(conn, r["id"], other) is None                         # nobody else
    assert rooms.prefill_activity(conn, "nope", me) is None and rooms.prefill_activity(conn, 999, me) is None
    rooms.link_event(conn, r["id"], event(conn)["id"], me)
    assert rooms.prefill_activity(conn, r["id"], me) is None                            # already has an activity
    d = rooms.request(conn, title="x", day=THU, slot_ids=S(conn, 13), requester_user_id=me["id"], today=MON)
    rooms.decline(conn, d["id"], "boss@test.local", "no")
    assert rooms.prefill_activity(conn, d["id"], me) is None                            # not live


# ------------------------------------------------------------------ the banner ---

def test_banner_states_follow_the_reservation(conn, me, other, boss):
    ev = event(conn)
    s = status(conn, ev, me)
    assert s["state"] == "none" and s["upcoming"] is True and s["event_when"] == "Thu 7 Mar 2030"
    r = book(conn, me, ev, approve=False)
    assert status(conn, ev, me)["state"] == "requested"
    rooms.approve(conn, r["id"], "boss@test.local", today=MON)
    s = status(conn, ev, me)
    assert s["state"] == "booked" and s["res"]["hours"] == "9 AM – 11 AM" and s["can_act"] and s["mine"]
    s2 = status(conn, ev, other)
    assert s2["state"] == "booked" and not s2["can_act"]                    # everyone who manages it sees it; only owner/section act
    assert status(conn, ev, boss)["can_act"] and not status(conn, ev, boss)["mine"]


def test_no_banner_for_a_past_activity_without_a_room(conn, me):
    ev = event(conn, day=date(2030, 2, 1))
    assert status(conn, ev, me)["upcoming"] is False


def test_banner_notices_when_the_activity_moved(conn, me):
    ev = event(conn)
    book(conn, me, ev)
    st.set_event_dates(conn, ev["id"], NEXT_THU.isoformat(), None)
    s = status(conn, ev, me)
    assert s["state"] == "mismatch" and s["event_day"] == "2030-03-14" and s["res"]["day"] == "2030-03-07"


def test_banner_when_the_room_was_cancelled_offers_times_to_the_owner(conn, me, other):
    ev = event(conn)
    book(conn, me, ev)
    rooms.encode(conn, by="boss@test.local", title="Director", day=THU, slot_ids=S(conn, 9, 10), ext={"name": "D"},
                 bump_reason="Director needs the room", today=MON)
    s = status(conn, ev, me)
    assert s["state"] == "lost" and s["res"]["decide_note"] == "Director needs the room" and s["offers"] and s["mine"]
    new = rooms.take_suggestion(conn, s["res"]["id"], me["id"], s["offers"][0]["day"], s["offers"][0]["slot_ids"], today=MON)
    assert new["event_id"] == ev["id"]                                      # the activity keeps its room
    again = status(conn, ev, me)
    assert again["state"] in ("booked", "mismatch") and again["res"]["id"] == new["id"]


def test_banner_for_an_archived_activity_that_still_holds_the_room(conn, me):
    ev = event(conn)
    book(conn, me, ev)
    conn.execute("UPDATE form_instance SET archived=1"); conn.commit()
    assert status(conn, ev, me)["state"] == "archived_holds"


# ------------------------------------------------------------------------ moves ---

def test_an_undecided_request_just_changes_day(conn, me):
    ev = event(conn)
    r = book(conn, me, ev, approve=False)
    out = rooms.request_move(conn, r["id"], NEXT_THU, me, today=MON)
    assert out["id"] == r["id"] and out["day"] == "2030-03-14"
    assert conn.execute("SELECT DISTINCT day FROM room_reservation_slot WHERE reservation_id=?", (r["id"],)).fetchall() == [("2030-03-14",)]
    assert "request moved" in [x["summary"] for x in st.list_audit(conn, action="room_move")][0]


def test_an_approved_booking_is_kept_until_the_move_is_approved(conn, me):
    ev = event(conn)
    old = book(conn, me, ev)
    st.set_event_dates(conn, ev["id"], NEXT_THU.isoformat(), None)           # the activity moved first, then the room follows
    assert status(conn, ev, me)["state"] == "mismatch"
    mv = rooms.request_move(conn, old["id"], NEXT_THU, me, today=MON)
    assert mv["id"] != old["id"] and mv["source"] == "move" and mv["moves_reservation_id"] == old["id"] and mv["event_id"] == ev["id"]
    assert mv["status"] == "requested" and mv["slot_ids"] == old["slot_ids"]
    assert rooms.get_reservation(conn, old["id"])["status"] == "approved"           # still held
    assert status(conn, ev, me)["state"] == "move_pending"
    with pytest.raises(rooms.RoomError, match="already waiting"):
        rooms.request_move(conn, old["id"], date(2030, 3, 21), me, today=MON)
    q = rooms.queue(conn)[0]
    assert q["move_of"]["ref"] == old["ref_code"] and q["can_approve"]
    rooms.approve(conn, mv["id"], "boss@test.local", today=MON)
    gone = rooms.get_reservation(conn, old["id"])
    assert gone["status"] == "withdrawn" and mv["ref_code"] in gone["decide_note"]
    assert rooms.slot_states(conn, THU)[S(conn, 9)[0]]["state"] == "free"
    assert rooms.slot_states(conn, NEXT_THU)[S(conn, 9)[0]]["state"] == "approved"
    assert status(conn, ev, me)["state"] == "booked"


def test_declining_a_move_keeps_the_old_booking(conn, me):
    ev = event(conn)
    old = book(conn, me, ev)
    mv = rooms.request_move(conn, old["id"], NEXT_THU, me, today=MON)
    rooms.decline(conn, mv["id"], "boss@test.local", "Taken that week")
    assert rooms.get_reservation(conn, old["id"])["status"] == "approved"


def test_withdrawing_the_old_booking_withdraws_its_pending_move(conn, me):
    ev = event(conn)
    old = book(conn, me, ev)
    mv = rooms.request_move(conn, old["id"], NEXT_THU, me, today=MON)
    rooms.withdraw(conn, old["id"], me["id"])
    assert rooms.get_reservation(conn, mv["id"])["status"] == "withdrawn"


def test_move_rules(conn, me, other, boss):
    ev = event(conn)
    old = book(conn, me, ev)
    with pytest.raises(rooms.RoomError, match="isn't yours"):
        rooms.request_move(conn, old["id"], NEXT_THU, other, today=MON)
    with pytest.raises(rooms.RoomError, match="already on that day"):
        rooms.request_move(conn, old["id"], THU, me, today=MON)
    with pytest.raises(rooms.RoomError, match="notice"):
        rooms.request_move(conn, old["id"], date(2030, 3, 5), me, today=MON)
    with pytest.raises(rooms.RoomError, match="weekends"):
        rooms.request_move(conn, old["id"], date(2030, 3, 16), me, today=MON)
    assert rooms.request_move(conn, old["id"], NEXT_THU, boss, today=MON)["source"] == "move"   # the section may move it for them


def test_a_move_to_a_taken_day_says_which_times_are_free(conn, me, other):
    ev = event(conn)
    old = book(conn, me, ev)
    book(conn, other, None, day=NEXT_THU, hours=(9, 10), title="Already there")
    with pytest.raises(rooms.SlotTaken) as e:
        rooms.request_move(conn, old["id"], NEXT_THU, me, today=MON)
    assert "already booked" in str(e.value) and "Nearest free times:" in str(e.value)
    assert rooms.get_reservation(conn, old["id"])["day"] == "2030-03-07" and conn.execute(
        "SELECT COUNT(*) FROM room_reservation WHERE source='move'").fetchone()[0] == 0
