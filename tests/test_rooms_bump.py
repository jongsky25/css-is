"""Conference room R4: suggestions, admin encode, 'Book anyway', blocks, competing requests."""
from __future__ import annotations
from datetime import date, timedelta

import pytest

import rooms
import storage as st

MON = date(2030, 3, 4)                      # a fixed Monday
THU = date(2030, 3, 7)


@pytest.fixture()
def conn(tmp_path):
    c = st.connect(str(tmp_path / "r.db")); st.init_db(c); rooms.ensure_slots(c)
    return c


@pytest.fixture()
def users(conn):
    return [st.create_admin_user(conn, f"u{i}@test.local", "x", "y", "viewer") for i in range(3)]


def S(conn, *hours):
    by = {s["start_time"]: s["id"] for s in rooms.list_slots(conn)}
    return [by[f"{h:02d}:00"] for h in hours]


def ask(conn, user, day, *hours, title="Planning"):
    return rooms.request(conn, title=title, day=day, slot_ids=S(conn, *hours), requester_user_id=user, today=MON)


def booked(conn, user, day, *hours, title="Held"):
    r = ask(conn, user, day, *hours, title=title)
    return rooms.approve(conn, r["id"], "ana", today=MON)


def enc(conn, day, *hours, **kw):
    kw.setdefault("title", "Director's meeting")
    kw.setdefault("ext", {"name": "Director"})
    return rooms.encode(conn, by="admin", day=day, slot_ids=S(conn, *hours), today=MON, **kw)


# ----------------------------------------------------------------- suggestions ---

def test_suggestions_go_same_hours_next_days_then_same_day(conn, users):
    booked(conn, users[0], THU, 9, 10)
    got = rooms.suggest(conn, THU, S(conn, 9, 10), n=4, today=MON)
    assert [(g["day"], g["slot_ids"]) for g in got[:2]] == [("2030-03-08", S(conn, 9, 10)),
                                                          ("2030-03-11", S(conn, 9, 10))]   # Fri, then Mon (weekend skipped)
    assert any(g["day"] == "2030-03-07" and g["why"] == "Same day, other hours" for g in
               rooms.suggest(conn, THU, S(conn, 9, 10), n=10, today=MON))


def test_suggestions_skip_holidays_blocks_and_booked_hours(conn, users):
    st.set_holiday(conn, "2030-03-08", "Test holiday")
    booked(conn, users[0], date(2030, 3, 11), 9, 10)
    rooms.add_block(conn, "admin", date(2030, 3, 12), None, "Training", today=MON)
    got = rooms.suggest(conn, THU, S(conn, 9, 10), n=3, today=MON)
    assert "2030-03-08" not in [g["day"] for g in got]               # holiday
    assert "2030-03-11" not in [g["day"] for g in got if g["slot_ids"] == S(conn, 9, 10)]   # booked
    assert "2030-03-12" not in [g["day"] for g in got]               # whole-day block
    assert got[0]["day"] == "2030-03-13"


def test_extra_taken_hides_the_slot_about_to_be_booked(conn):
    got = rooms.suggest(conn, THU, S(conn, 9), n=20, today=MON, extra_taken={("2030-03-07", S(conn, 10)[0])})
    assert not any(g["day"] == "2030-03-07" and g["slot_ids"] == S(conn, 10) for g in got)


def test_suggestions_have_no_room_notice_cutoff(conn):
    ok = rooms.suggest(conn, MON, S(conn, 9), n=3, today=MON, respect_lead=False)
    strict = rooms.suggest(conn, MON, S(conn, 9), n=3, today=MON, respect_lead=True)
    assert ok[0]["day"] == "2030-03-05" and strict[0]["day"] == "2030-03-05"


# ---------------------------------------------------------------------- encode ---

def test_encode_is_approved_at_once_for_a_guest_or_an_account(conn, users):
    g = enc(conn, THU, 9, 10)
    assert g["status"] == "approved" and g["source"] == "encoded" and g["ext_name"] == "Director"
    a = enc(conn, THU, 13, ext=None, requester_user_id=users[0], title="Mine")
    assert a["requester_user_id"] == users[0]
    assert rooms.slot_states(conn, THU)[S(conn, 9)[0]]["state"] == "approved"


def test_encode_rules(conn, users):
    with pytest.raises(rooms.RoomError, match="Who is this booking for"):
        enc(conn, THU, 9, ext=None)
    assert enc(conn, MON, 9)["status"] == "approved"
    r = enc(conn, date(2030, 3, 5), 9, note="Urgent call from the Secretary")
    assert r["decide_note"].startswith("Urgent") and r["status"] == "approved"
    with pytest.raises(rooms.RoomError, match="weekends"):
        enc(conn, date(2030, 3, 9), 9)
    with pytest.raises(rooms.RoomError, match="passed"):
        enc(conn, date(2030, 2, 25), 9, note="x")


# ----------------------------------------------------------------- Book anyway ---

def test_booking_over_an_approved_one_needs_a_reason_and_names_who_is_bumped(conn, users):
    old = booked(conn, users[0], THU, 9, 10, title="Section planning")
    with pytest.raises(rooms.NeedsBump) as e:
        enc(conn, THU, 10, 11)
    a = e.value.affected[0]
    assert a["id"] == old["id"] and a["title"] == "Section planning" and a["suggestions"]
    assert rooms.get_reservation(conn, old["id"])["status"] == "approved"      # nothing changed yet


def test_book_anyway_is_atomic_and_links_the_two(conn, users):
    old = booked(conn, users[0], THU, 9, 10)
    new = enc(conn, THU, 10, 11, bump_reason="Director needs the room")
    got = rooms.get_reservation(conn, old["id"])
    assert got["status"] == "cancelled" and got["bumped_by_reservation_id"] == new["id"]
    assert got["decide_note"] == "Director needs the room" and new["bumped"] == [old["id"]]
    states = rooms.slot_states(conn, THU)
    assert states[S(conn, 9)[0]]["state"] == "free"                           # only the new booking's hours are taken
    assert states[S(conn, 10)[0]]["state"] == "approved" and states[S(conn, 11)[0]]["state"] == "approved"
    acts = {x["action"] for x in st.list_audit(conn)}
    assert {"room_encode", "room_cancel"} <= acts


def test_a_failed_book_anyway_leaves_the_old_booking_alone(conn, users, monkeypatch):
    old = booked(conn, users[0], THU, 9)
    real = rooms._cancel_in_txn
    monkeypatch.setattr(rooms, "_cancel_in_txn", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("boom")))
    with pytest.raises(RuntimeError):
        enc(conn, THU, 9, bump_reason="x")
    monkeypatch.setattr(rooms, "_cancel_in_txn", real)
    assert rooms.get_reservation(conn, old["id"])["status"] == "approved"
    assert conn.execute("SELECT COUNT(*) FROM room_reservation").fetchone()[0] == 1


def test_one_new_booking_can_bump_several(conn, users):
    a = booked(conn, users[0], THU, 9)
    b = booked(conn, users[1], THU, 10)
    new = enc(conn, THU, 9, 10, bump_reason="Whole-bureau meeting")
    assert sorted(new["bumped"]) == sorted([a["id"], b["id"]])


# ---------------------------------------------------------- the bumped person ---

def test_bumped_person_is_offered_fresh_times_and_the_pick_is_approved(conn, users):
    old = booked(conn, users[0], THU, 9, 10)
    enc(conn, THU, 9, 10, bump_reason="Director needs the room")
    cancelled = rooms.get_reservation(conn, old["id"])
    offers = rooms.suggestions_for(conn, cancelled, today=MON)
    assert offers
    pick = offers[0]
    new = rooms.take_suggestion(conn, old["id"], users[0], pick["day"], pick["slot_ids"], today=MON)
    assert new["status"] == "approved" and new["source"] == "bump_accept" and new["moves_reservation_id"] == old["id"]
    assert rooms.suggestions_for(conn, cancelled, today=MON) == []             # one move per cancellation
    with pytest.raises(rooms.RoomError, match="already took"):
        rooms.take_suggestion(conn, old["id"], users[0], offers[1]["day"], offers[1]["slot_ids"], today=MON)


def test_only_offered_times_are_accepted_and_only_by_the_owner(conn, users):
    old = booked(conn, users[0], THU, 9)
    enc(conn, THU, 9, bump_reason="x")
    with pytest.raises(rooms.RoomError, match="no longer free"):
        rooms.take_suggestion(conn, old["id"], users[0], "2030-04-01", S(conn, 9), today=MON)     # not offered
    with pytest.raises(rooms.RoomError, match="your own"):
        rooms.take_suggestion(conn, old["id"], users[1], "2030-03-08", S(conn, 9), today=MON)


def test_an_offer_that_gets_taken_first_is_refused(conn, users):
    old = booked(conn, users[0], THU, 9)
    enc(conn, THU, 9, bump_reason="x")
    pick = rooms.suggestions_for(conn, rooms.get_reservation(conn, old["id"]), today=MON)[0]
    booked(conn, users[1], date.fromisoformat(pick["day"]), 9, title="Grabbed it")
    with pytest.raises(rooms.RoomError, match="no longer free"):
        rooms.take_suggestion(conn, old["id"], users[0], pick["day"], pick["slot_ids"], today=MON)


def test_a_declined_requester_re_requests_under_the_normal_rules(conn, users):
    a = ask(conn, users[0], THU, 9)
    ask(conn, users[1], THU, 9, title="Rival")
    rooms.decline(conn, a["id"], "ana", "Room is for training")
    pick = rooms.suggestions_for(conn, rooms.get_reservation(conn, a["id"]), today=MON)[0]
    new = rooms.take_suggestion(conn, a["id"], users[0], pick["day"], pick["slot_ids"], today=MON)
    assert new["status"] == "requested" and new["source"] == "internal" and new["moves_reservation_id"] == a["id"]


# ----------------------------------------------------------- competing requests ---

def test_approving_can_decline_the_rivals_in_one_step(conn, users):
    a = ask(conn, users[0], THU, 9, 10, title="Alpha")
    b = ask(conn, users[1], THU, 10, 11, title="Bravo")
    c = ask(conn, users[2], THU, 14, title="Elsewhere")
    rooms.approve(conn, a["id"], "ana", today=MON, decline_rivals=True)
    got = rooms.get_reservation(conn, b["id"])
    assert got["status"] == "declined" and a["ref_code"] in got["decide_note"]
    assert rooms.get_reservation(conn, c["id"])["status"] == "requested"        # unrelated stays open
    assert rooms.suggestions_for(conn, got, today=MON)                                  # and Bravo is offered times


def test_approving_without_the_option_leaves_rivals_open(conn, users):
    a = ask(conn, users[0], THU, 9)
    b = ask(conn, users[1], THU, 9)
    rooms.approve(conn, a["id"], "ana", today=MON)
    assert rooms.get_reservation(conn, b["id"])["status"] == "requested"


# ----------------------------------------------------------------------- blocks ---

def test_blocking_a_booked_day_asks_first_then_cancels(conn, users):
    old = booked(conn, users[0], THU, 9, 10)
    with pytest.raises(rooms.NeedsBump) as e:
        rooms.add_block(conn, "admin", THU, None, "Fumigation", today=MON)
    assert e.value.affected[0]["id"] == old["id"]
    assert rooms.get_reservation(conn, old["id"])["status"] == "approved"
    out = rooms.add_block(conn, "admin", THU, None, "Fumigation", confirm=True, today=MON)
    got = rooms.get_reservation(conn, old["id"])
    assert out["cancelled"] == [old["id"]] and got["status"] == "cancelled" and "Fumigation" in got["decide_note"]
    assert got["bumped_by_reservation_id"] is None
    assert not any(g["day"] == "2030-03-07" for g in rooms.suggestions_for(conn, got, today=MON))   # never the blocked day
    with pytest.raises(rooms.SlotTaken):
        ask(conn, users[1], THU, 9)


def test_block_some_hours_list_and_reopen(conn):
    out = rooms.add_block(conn, "admin", THU, S(conn, 14, 15), "Aircon repair", today=MON)
    (g,) = rooms.list_blocks(conn, today=MON)
    assert g["hours"] == "2 PM – 4 PM" and not g["whole_day"] and g["ids"] == out["ids"]
    assert rooms.slot_states(conn, THU)[S(conn, 14)[0]]["state"] == "blocked"
    rooms.remove_block(conn, "admin", g["ids"])
    assert rooms.list_blocks(conn, today=MON) == [] and rooms.slot_states(conn, THU)[S(conn, 14)[0]]["state"] == "free"


def test_block_needs_a_reason_and_a_future_date(conn):
    with pytest.raises(rooms.RoomError, match="why"):
        rooms.add_block(conn, "admin", THU, None, " ", today=MON)
    with pytest.raises(rooms.RoomError, match="passed"):
        rooms.add_block(conn, "admin", date(2030, 2, 1), None, "x", today=MON)


def test_account_options_lists_active_accounts(conn, users):
    names = [n for _i, n in rooms.account_options(conn)]
    assert "u0@test.local" in names
