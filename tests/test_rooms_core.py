"""Conference room service core (R1): slots, lead time, request / approve / decline / withdraw."""
from __future__ import annotations
from datetime import date, timedelta

import pytest

import rooms
import storage as st
import tzutil as tz

# A fixed Monday, so working-day arithmetic is deterministic.
MON = date(2030, 3, 4)
FRI = date(2030, 3, 8)


@pytest.fixture()
def conn(tmp_path):
    c = st.connect(str(tmp_path / "rooms.db")); st.init_db(c)
    rooms.ensure_slots(c)
    return c


@pytest.fixture()
def users(conn):
    return [st.create_admin_user(conn, f"u{i}@test.local", "x", "y", "viewer") for i in range(3)]


def ids(conn, *hours):
    by = {s["start_time"]: s["id"] for s in rooms.list_slots(conn)}
    return [by[f"{h:02d}:00"] for h in hours]


def ask(conn, user, day, *hours, title="Planning", today=MON, **kw):
    return rooms.request(conn, title=title, day=day, slot_ids=ids(conn, *hours),
                         requester_user_id=user, actor=f"u{user}", today=today, **kw)


# ------------------------------------------------------------------ slots ---

def test_twelve_hourly_slots_from_7_to_19(conn):
    s = rooms.list_slots(conn)
    assert len(s) == 12
    assert (s[0]["start_time"], s[0]["end_time"]) == ("07:00", "08:00")
    assert (s[-1]["start_time"], s[-1]["end_time"]) == ("18:00", "19:00")


def test_seeding_is_idempotent_and_respects_admin_edits(conn):
    conn.execute("UPDATE room_slot SET active=0 WHERE code='H07'"); conn.commit()
    rooms.ensure_slots(conn); rooms.ensure_slots(conn)
    assert len(rooms.list_slots(conn)) == 11
    assert conn.execute("SELECT COUNT(*) FROM room_slot").fetchone()[0] == 12


# -------------------------------------------------------------- lead time ---

def test_two_working_days_notice(conn):
    assert rooms.earliest_bookable(conn, MON) == date(2030, 3, 6)          # Mon -> Wed
    assert rooms.earliest_bookable(conn, FRI) == date(2030, 3, 12)         # Fri -> Tue
    assert rooms.day_closed_reason(conn, date(2030, 3, 5), MON)            # tomorrow: too soon
    assert rooms.day_closed_reason(conn, date(2030, 3, 6), MON) is None


def test_holidays_do_not_count_as_working_days(conn):
    st.set_holiday(conn, "2030-03-05", "Test holiday")
    assert rooms.earliest_bookable(conn, MON) == date(2030, 3, 7)          # Tue skipped
    assert "Test holiday" in rooms.day_closed_reason(conn, date(2030, 3, 5), MON)


def test_weekend_past_and_far_future_are_closed(conn):
    assert "weekend" in rooms.day_closed_reason(conn, date(2030, 3, 9), MON)
    assert "passed" in rooms.day_closed_reason(conn, date(2030, 3, 1), MON)
    assert "ahead" in rooms.day_closed_reason(conn, MON + timedelta(days=200), MON)


# ---------------------------------------------------------------- request ---

def test_request_creates_a_requested_reservation_with_a_ref(conn, users):
    r = ask(conn, users[0], date(2030, 3, 7), 9, 10, attendees=8, meals_requested=True)
    assert r["status"] == "requested" and r["source"] == "internal"
    assert r["ref_code"] == f"CR-3003-{r['id']:04d}"
    assert len(r["slot_ids"]) == 2 and r["meals_requested"] == 1
    assert rooms.get_by_ref(conn, r["ref_code"].lower())["id"] == r["id"]


def test_request_rules(conn, users):
    day = date(2030, 3, 7)
    with pytest.raises(rooms.RoomError, match="title"):
        ask(conn, users[0], day, 9, title=" ")
    with pytest.raises(rooms.RoomError, match="notice"):
        ask(conn, users[0], date(2030, 3, 5), 9)
    with pytest.raises(rooms.RoomError, match="back-to-back"):
        ask(conn, users[0], day, 9, 11)
    with pytest.raises(rooms.RoomError, match="at least one"):
        rooms.request(conn, title="x", day=day, slot_ids=[], requester_user_id=users[0], today=MON)
    with pytest.raises(rooms.RoomError, match="Who is asking"):
        rooms.request(conn, title="x", day=day, slot_ids=ids(conn, 9), today=MON)
    with pytest.raises(rooms.RoomError, match="face-to-face"):
        ask(conn, users[0], day, 9, modality="zoom")


def test_external_request_needs_name_and_contact(conn):
    r = rooms.request(conn, title="Visit", day=date(2030, 3, 7), slot_ids=ids(conn, 13),
                      ext={"name": "Ana", "org": "NGO", "email": "a@x.org"}, today=MON)
    assert r["source"] == "external" and r["requester_user_id"] is None and r["ext_org"] == "NGO"


def test_many_can_request_the_same_hour_until_one_is_approved(conn, users):
    day = date(2030, 3, 7)
    a = ask(conn, users[0], day, 9, 10)
    b = ask(conn, users[1], day, 10, 11)
    states = rooms.slot_states(conn, day)
    assert states[ids(conn, 10)[0]]["state"] == "requested" and states[ids(conn, 10)[0]]["pending"] == 2
    assert [x["id"] for x in rooms.competing(conn, a["id"])] == [b["id"]]
    rooms.approve(conn, a["id"], "admin")
    assert rooms.slot_states(conn, day)[ids(conn, 10)[0]]["state"] == "approved"
    with pytest.raises(rooms.SlotTaken):                       # new requests can't take an approved hour
        ask(conn, users[2], day, 10)


# ----------------------------------------------------------------- decide ---

def test_second_approval_of_the_same_hour_loses(conn, users):
    day = date(2030, 3, 7)
    a = ask(conn, users[0], day, 9, 10)
    b = ask(conn, users[1], day, 10, 11)
    rooms.approve(conn, a["id"], "ana")
    with pytest.raises(rooms.SlotTaken) as e:
        rooms.approve(conn, b["id"], "ben")
    assert e.value.other["ref_code"] == a["ref_code"]
    assert rooms.get_reservation(conn, b["id"])["status"] == "requested"      # rolled back cleanly
    assert conn.execute("SELECT COUNT(*) FROM room_reservation_slot WHERE reservation_id=? AND is_approved=1",
                        (b["id"],)).fetchone()[0] == 0


def test_database_itself_refuses_two_approved_rows_for_one_hour(conn, users):
    a = ask(conn, users[0], date(2030, 3, 7), 9)
    b = ask(conn, users[1], date(2030, 3, 7), 9)
    conn.execute("UPDATE room_reservation_slot SET is_approved=1 WHERE reservation_id=?", (a["id"],))
    with pytest.raises(Exception, match="UNIQUE"):
        conn.execute("UPDATE room_reservation_slot SET is_approved=1 WHERE reservation_id=?", (b["id"],))


def test_first_to_act_wins_and_the_loser_is_told_who(conn, users):
    r = ask(conn, users[0], date(2030, 3, 7), 9)
    rooms.approve(conn, r["id"], "ana", note="ok")
    with pytest.raises(rooms.AlreadyDecided) as e:
        rooms.approve(conn, r["id"], "ben")
    assert e.value.decided_by == "ana" and "ana" in str(e.value)
    with pytest.raises(rooms.AlreadyDecided):
        rooms.decline(conn, r["id"], "ben", "no")


def test_decline_needs_a_reason_and_frees_the_queue(conn, users):
    r = ask(conn, users[0], date(2030, 3, 7), 9)
    with pytest.raises(rooms.RoomError, match="reason"):
        rooms.decline(conn, r["id"], "ana", "  ")
    d = rooms.decline(conn, r["id"], "ana", "Room is for training")
    assert d["status"] == "declined" and d["decide_note"] == "Room is for training"
    assert rooms.list_pending(conn) == []


def test_cannot_approve_a_date_that_has_passed(conn, users):
    r = ask(conn, users[0], date(2030, 3, 7), 9)
    with pytest.raises(rooms.RoomError, match="passed"):
        rooms.approve(conn, r["id"], "ana", today=date(2030, 3, 8))


# --------------------------------------------------------------- withdraw ---

def test_withdraw_frees_an_approved_hour(conn, users):
    day = date(2030, 3, 7)
    r = ask(conn, users[0], day, 9, 10)
    rooms.approve(conn, r["id"], "ana")
    w = rooms.withdraw(conn, r["id"], users[0], reason="Meeting cancelled")
    assert w["status"] == "withdrawn"
    assert rooms.slot_states(conn, day)[ids(conn, 9)[0]]["state"] == "free"
    again = ask(conn, users[1], day, 9, 10)                    # hour can be requested and approved again
    assert rooms.approve(conn, again["id"], "ana")["status"] == "approved"


def test_only_the_owner_can_withdraw_and_only_once(conn, users):
    r = ask(conn, users[0], date(2030, 3, 7), 9)
    with pytest.raises(rooms.RoomError, match="your own"):
        rooms.withdraw(conn, r["id"], users[1])
    rooms.withdraw(conn, r["id"], users[0])
    with pytest.raises(rooms.AlreadyDecided):
        rooms.withdraw(conn, r["id"], users[0])


def test_withdrawing_a_declined_request_is_refused(conn, users):
    r = ask(conn, users[0], date(2030, 3, 7), 9)
    rooms.decline(conn, r["id"], "ana", "no")
    with pytest.raises(rooms.AlreadyDecided):
        rooms.withdraw(conn, r["id"], users[0])


# -------------------------------------------------------- blocks, listing ---

def test_blocked_hours_cannot_be_requested(conn, users):
    day = date(2030, 3, 7)
    conn.execute("INSERT INTO room_block(day, slot_id, reason) VALUES (?,?,?)",
                 (day.isoformat(), ids(conn, 14)[0], "Aircon repair")); conn.commit()
    with pytest.raises(rooms.SlotTaken, match="unavailable"):
        ask(conn, users[0], day, 14)
    assert rooms.slot_states(conn, day)[ids(conn, 14)[0]]["reason"] == "Aircon repair"


def test_listing_for_user_and_audit_trail(conn, users):
    a = ask(conn, users[0], date(2030, 3, 7), 9)
    ask(conn, users[1], date(2030, 3, 7), 13)
    rooms.approve(conn, a["id"], "ana")
    assert [r["id"] for r in rooms.list_for_user(conn, users[0])] == [a["id"]]
    acts = [x["action"] for x in st.list_audit(conn) if x["target_type"] == "room_reservation"]
    assert {"room_request", "room_approve"} <= set(acts)
    assert st.audit_label("room_approve") == "Approved a room reservation"
