"""Conference room R4 pages: encode, Book anyway, closures, 'Needs a new time', competing requests."""
from __future__ import annotations
import pytest

import rooms
import storage as st
import tzutil as tz
from conftest import in_the_directory

ADMIN_UNIT = "BLHSD/ADMIN"


@pytest.fixture()
def conn(app_mod):
    c = st.connect(app_mod.DB); st.init_db(c); rooms.ensure_slots(c)
    yield c
    for t in ("room_reservation_slot", "room_reservation", "room_block"):
        c.execute(f"DELETE FROM {t}")
    c.commit(); c.close()


def day(conn, extra=3):
    return rooms.add_working_days(conn, tz.today_local(), rooms.LEAD_WORKING_DAYS + extra)


def sid(conn, hour):
    return next(s["id"] for s in rooms.list_slots(conn) if s["start_time"] == f"{hour:02d}:00")


def uid(conn, name):
    return st.get_admin_user(conn, name)["id"]


def booked(conn, who, hour=9, n=2, title="Held", extra=3):
    r = rooms.request(conn, title=title, day=day(conn, extra), slot_ids=[sid(conn, hour + i) for i in range(n)],
                      requester_user_id=uid(conn, who))
    return rooms.approve(conn, r["id"], "admin")


def form(conn, **kw):
    f = {"day": day(conn).isoformat(), "from_slot": sid(conn, 9), "to_slot": sid(conn, 10),
         "title": "Director's meeting", "modality": "f2f", "for_name": "Director"}
    f.update(kw)
    return f


# ---------------------------------------------------------------------- encode ---

def test_only_section_members_can_encode(viewer, conn):
    assert viewer.post("/rooms/encode", data=form(conn)).status_code == 403
    assert "Book it now" not in viewer.get("/rooms").text


def test_encode_books_straight_away(app_mod, viewer, conn):
    with in_the_directory(app_mod, "viewer@test.local", path=ADMIN_UNIT):
        assert "Book it now" in viewer.get("/rooms").text
        r = viewer.post("/rooms/encode", data=form(conn), follow_redirects=False)
        assert r.status_code == 303 and "flash=Booked" in r.headers["location"]
        assert "Booked CR-" in viewer.get(r.headers["location"]).text
    got = conn.execute("SELECT status, source, ext_name FROM room_reservation").fetchone()
    assert got == ("approved", "encoded", "Director")


def test_encode_for_an_account_lands_in_their_my_reservations(admin, encoder, conn):
    admin.post("/rooms/encode", data=form(conn, for_user=str(uid(conn, "encoder@test.local")), for_name="", title="Planning"))
    page = encoder.get("/rooms/mine").text
    assert "Planning" in page and "Approved" in page


def test_encode_errors_come_back_on_the_board(admin, conn):
    r = admin.post("/rooms/encode", data=form(conn, for_name=""))
    assert r.status_code == 400 and "Who is this booking for" in r.text
    r = admin.post("/rooms/encode", data=form(conn, day=tz.today_local().isoformat()))
    assert r.status_code == 400
    assert conn.execute("SELECT COUNT(*) FROM room_reservation").fetchone()[0] == 0


# ----------------------------------------------------------------- Book anyway ---

def test_book_anyway_asks_first_then_does_it(admin, conn):
    old = booked(conn, "encoder@test.local", 9, 2, title="Section planning")
    r = admin.post("/rooms/encode", data=form(conn, from_slot=sid(conn, 10), to_slot=sid(conn, 11)))
    assert r.status_code == 409 and "will be cancelled" in r.text and "Section planning" in r.text
    assert "They will be offered" in r.text
    assert rooms.get_reservation(conn, old["id"])["status"] == "approved"            # nothing changed yet
    r = admin.post("/rooms/encode", data=form(conn, from_slot=sid(conn, 10), to_slot=sid(conn, 11),
                                              bump="1", bump_reason="Director needs the room"),
                   follow_redirects=False)
    assert r.status_code == 303
    got = rooms.get_reservation(conn, old["id"])
    assert got["status"] == "cancelled" and got["decide_note"] == "Director needs the room"


def test_book_anyway_needs_a_reason(admin, conn):
    old = booked(conn, "encoder@test.local", 9, 1)
    r = admin.post("/rooms/encode", data=form(conn, from_slot=sid(conn, 9), to_slot=sid(conn, 9), bump="1", bump_reason=" "))
    assert r.status_code == 409 and rooms.get_reservation(conn, old["id"])["status"] == "approved"


def test_bumped_person_sees_it_and_picks_a_new_time(admin, encoder, conn):
    old = booked(conn, "encoder@test.local", 9, 2, title="Section planning")
    admin.post("/rooms/encode", data=form(conn, bump="1", bump_reason="Director needs the room"))
    page = encoder.get("/rooms/mine").text
    assert "Needs a new time" in page and "Director needs the room" in page and "booked at once" in page
    offers = rooms.suggestions_for(conn, rooms.get_reservation(conn, old["id"]))
    o = offers[0]
    r = encoder.post(f"/rooms/{old['id']}/take", data={"day": o["day"], "slots": ",".join(map(str, o["slot_ids"]))},
                     follow_redirects=False)
    assert r.status_code == 303 and "took=approved" in r.headers["location"]
    assert "New time booked" in encoder.get(r.headers["location"]).text
    assert "Needs a new time" not in encoder.get("/rooms/mine").text


def test_taking_a_time_that_was_never_offered_is_refused(admin, encoder, conn):
    old = booked(conn, "encoder@test.local", 9, 1)
    admin.post("/rooms/encode", data=form(conn, from_slot=sid(conn, 9), to_slot=sid(conn, 9), bump="1", bump_reason="x"))
    r = encoder.post(f"/rooms/{old['id']}/take", data={"day": "2031-01-06", "slots": str(sid(conn, 9))}, follow_redirects=True)
    assert "no longer free" in r.text
    assert conn.execute("SELECT COUNT(*) FROM room_reservation WHERE moves_reservation_id=?", (old["id"],)).fetchone()[0] == 0


def test_someone_else_cannot_take_the_time(admin, encoder, viewer, conn):
    old = booked(conn, "encoder@test.local", 9, 1)
    admin.post("/rooms/encode", data=form(conn, from_slot=sid(conn, 9), to_slot=sid(conn, 9), bump="1", bump_reason="x"))
    o = rooms.suggestions_for(conn, rooms.get_reservation(conn, old["id"]))[0]
    r = viewer.post(f"/rooms/{old['id']}/take", data={"day": o["day"], "slots": ",".join(map(str, o["slot_ids"]))}, follow_redirects=True)
    assert "your own" in r.text


# --------------------------------------------------------------------- closures ---

def test_closures_page_is_for_section_members(viewer, conn):
    assert viewer.get("/rooms/blocks").status_code == 403
    assert viewer.post("/rooms/blocks", data={"day": day(conn).isoformat(), "reason": "x"}).status_code == 403


def test_close_the_room_and_reopen_it(admin, conn):
    d = day(conn)
    r = admin.post("/rooms/blocks", data={"day": d.isoformat(), "whole_day": "1", "reason": "Fumigation"}, follow_redirects=False)
    assert r.status_code == 303
    page = admin.get(r.headers["location"]).text
    assert "Fumigation" in page and "Whole day" in page
    assert "rm-cell st-blocked" in admin.get(f"/rooms?week={d.isoformat()}").text
    ids = ",".join(str(i) for i in rooms.list_blocks(conn)[0]["ids"])
    admin.post("/rooms/blocks/reopen", data={"ids": ids})
    assert rooms.list_blocks(conn) == []


def test_closing_over_a_booking_asks_then_cancels(admin, encoder, conn):
    old = booked(conn, "encoder@test.local", 9, 2, title="Section planning")
    d = day(conn)
    r = admin.post("/rooms/blocks", data={"day": d.isoformat(), "whole_day": "1", "reason": "Fumigation"})
    assert r.status_code == 409 and "Section planning" in r.text and "will be cancelled" in r.text
    assert rooms.get_reservation(conn, old["id"])["status"] == "approved" and rooms.list_blocks(conn) == []
    r = admin.post("/rooms/blocks", data={"day": d.isoformat(), "whole_day": "1", "reason": "Fumigation", "confirm": "1"})
    assert rooms.get_reservation(conn, old["id"])["status"] == "cancelled"
    assert "Fumigation" in encoder.get("/rooms/mine").text


# ------------------------------------------------------------------ rivals dialog ---

def test_approving_with_the_option_declines_the_rivals(admin, encoder, viewer, conn):
    d = day(conn)
    a = rooms.request(conn, title="Alpha", day=d, slot_ids=[sid(conn, 9)], requester_user_id=uid(conn, "encoder@test.local"))
    b = rooms.request(conn, title="Bravo", day=d, slot_ids=[sid(conn, 9)], requester_user_id=uid(conn, "viewer@test.local"))
    page = admin.get("/approvals").text
    assert "Also decline the 1 competing request" in page
    admin.post(f"/rooms/{a['id']}/decide", data={"action": "approve", "decline_rivals": "1"})
    assert rooms.get_reservation(conn, b["id"])["status"] == "declined"
    mine = viewer.get("/rooms/mine").text
    assert "Needs a new time" in mine and "Other times that are free" in mine and "Another request for these hours" in mine


def test_without_the_option_the_rival_stays_open(admin, conn):
    d = day(conn)
    a = rooms.request(conn, title="Alpha", day=d, slot_ids=[sid(conn, 9)], requester_user_id=uid(conn, "encoder@test.local"))
    b = rooms.request(conn, title="Bravo", day=d, slot_ids=[sid(conn, 9)], requester_user_id=uid(conn, "viewer@test.local"))
    admin.post(f"/rooms/{a['id']}/decide", data={"action": "approve"})
    assert rooms.get_reservation(conn, b["id"])["status"] == "requested"
