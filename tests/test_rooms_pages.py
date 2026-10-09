"""Conference room pages (R2): availability board, request panel, My reservations."""
from __future__ import annotations
from datetime import timedelta

import pytest

import rooms
import storage as st
import tzutil as tz


@pytest.fixture()
def conn(app_mod):
    c = st.connect(app_mod.DB); st.init_db(c); rooms.ensure_slots(c)
    yield c
    for t in ("room_reservation_slot", "room_reservation", "room_block", "room_notice"):
        c.execute(f"DELETE FROM {t}")
    c.commit(); c.close()


def bookable_day(conn, extra=3):
    return rooms.add_working_days(conn, tz.today_local(), rooms.LEAD_WORKING_DAYS + extra)


def slot_id(conn, hour):
    return next(s["id"] for s in rooms.list_slots(conn) if s["start_time"] == f"{hour:02d}:00")


def form(conn, day, **kw):
    f = {"day": day.isoformat(), "from_slot": slot_id(conn, 9), "to_slot": slot_id(conn, 10),
         "title": "Planning meeting", "modality": "f2f"}
    f.update(kw)
    return f


# ------------------------------------------------------------------ access ---

def test_pages_need_a_login(client):
    for path in ("/rooms", "/rooms/mine"):
        r = client.get(path, follow_redirects=False)
        assert r.status_code in (302, 303, 401)


def test_any_signed_in_user_can_open_the_board(viewer, conn):
    r = viewer.get("/rooms")
    assert r.status_code == 200
    assert "Request the room" in r.text and "Conference room" in r.text


def test_it_is_in_the_navigation(viewer):
    assert 'href="/rooms"' in viewer.get("/rooms").text


# ------------------------------------------------------------------- board ---

def test_board_shows_twelve_hours_and_a_free_cell(viewer, conn):
    html = viewer.get(f"/rooms?week={bookable_day(conn).isoformat()}").text
    assert html.count('scope="row"') >= 12
    assert 'class="rm-cell st-free' in html and "7 AM" in html and "6 PM" in html


def test_board_marks_closed_days_with_a_reason(viewer, conn):
    html = viewer.get(f"/rooms?week={tz.today_local().isoformat()}").text
    assert "rm-cell st-closed" in html            # today is inside the two-working-day notice


def test_approved_booking_shows_its_title_and_cannot_be_clicked(viewer, conn):
    day = bookable_day(conn)
    uid = st.get_admin_user(conn, "encoder@test.local")["id"]
    r = rooms.request(conn, title="Budget hearing", day=day, slot_ids=[slot_id(conn, 13)],
                      requester_user_id=uid)
    rooms.approve(conn, r["id"], "admin")
    html = viewer.get(f"/rooms?week={day.isoformat()}").text
    assert "Budget hearing" in html and "rm-cell st-approved" in html
    assert f'data-day="{day.isoformat()}" data-slot="{slot_id(conn, 13)}"' not in html


def test_other_peoples_pending_requests_show_a_count_not_a_title(viewer, conn):
    day = bookable_day(conn)
    uid = st.get_admin_user(conn, "encoder@test.local")["id"]
    rooms.request(conn, title="Secret plan", day=day, slot_ids=[slot_id(conn, 9)], requester_user_id=uid)
    html = viewer.get(f"/rooms?week={day.isoformat()}").text
    assert "Secret plan" not in html and "1 requested" in html


def test_navigating_weeks_works(viewer, conn):
    d = bookable_day(conn)
    assert viewer.get(f"/rooms?week={d.isoformat()}").status_code == 200
    assert viewer.get("/rooms?week=not-a-date").status_code == 200


# ------------------------------------------------------------------ request ---

def test_requesting_creates_a_pending_reservation_and_lands_on_my_reservations(viewer, conn):
    day = bookable_day(conn)
    r = viewer.post("/rooms/request", data=form(conn, day, attendees="6", meals="1"), follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/rooms/mine?ok=CR-")
    mine = viewer.get(r.headers["location"])
    assert "Planning meeting" in mine.text and "Requested" in mine.text and "Request CR-" in mine.text
    assert "Meals" in mine.text
    row = conn.execute("SELECT status, meals_requested, attendees FROM room_reservation").fetchone()
    assert row == ("requested", 1, 6)


def test_errors_come_back_on_the_board_with_what_you_typed(viewer, conn):
    day = bookable_day(conn)
    r = viewer.post("/rooms/request", data=form(conn, day, title=""))
    assert r.status_code == 400 and "title" in r.text.lower()
    r = viewer.post("/rooms/request", data=form(conn, tz.today_local(), title="Too soon"))
    assert r.status_code == 400 and "notice" in r.text and 'value="Too soon"' in r.text
    r = viewer.post("/rooms/request", data=form(conn, day, attendees="lots"))
    assert r.status_code == 400 and "number" in r.text
    r = viewer.post("/rooms/request", data={"title": "x"})
    assert r.status_code == 400 and "Pick a date" in r.text
    assert conn.execute("SELECT COUNT(*) FROM room_reservation").fetchone()[0] == 0


def test_end_before_start_is_treated_as_a_range_either_way(viewer, conn):
    day = bookable_day(conn)
    viewer.post("/rooms/request", data=form(conn, day, from_slot=slot_id(conn, 11), to_slot=slot_id(conn, 9)))
    r = rooms.get_reservation(conn, conn.execute("SELECT id FROM room_reservation").fetchone()[0])
    assert len(r["slot_ids"]) == 3


def test_cannot_request_an_hour_that_is_already_approved(viewer, conn):
    day = bookable_day(conn)
    uid = st.get_admin_user(conn, "encoder@test.local")["id"]
    a = rooms.request(conn, title="Held", day=day, slot_ids=[slot_id(conn, 9)], requester_user_id=uid)
    rooms.approve(conn, a["id"], "admin")
    r = viewer.post("/rooms/request", data=form(conn, day))
    assert r.status_code == 400 and "already booked" in r.text


# --------------------------------------------------------------- my reservations ---

def test_my_reservations_lists_only_my_own(viewer, encoder, conn):
    day = bookable_day(conn)
    viewer.post("/rooms/request", data=form(conn, day, title="Viewer meeting"))
    assert "Viewer meeting" not in encoder.get("/rooms/mine").text
    assert "Viewer meeting" in viewer.get("/rooms/mine").text


def test_withdraw_frees_the_hours_and_shows_in_earlier(viewer, conn):
    day = bookable_day(conn)
    viewer.post("/rooms/request", data=form(conn, day))
    rid = conn.execute("SELECT id FROM room_reservation").fetchone()[0]
    r = viewer.post(f"/rooms/{rid}/withdraw", data={"reason": "Cancelled"}, follow_redirects=False)
    assert r.status_code == 303 and "done=withdrawn" in r.headers["location"]
    page = viewer.get(r.headers["location"]).text
    assert "withdrawn" in page.lower() and "Earlier" in page
    assert conn.execute("SELECT status FROM room_reservation WHERE id=?", (rid,)).fetchone()[0] == "withdrawn"


def test_cannot_withdraw_someone_elses_reservation(viewer, encoder, conn):
    day = bookable_day(conn)
    viewer.post("/rooms/request", data=form(conn, day))
    rid = conn.execute("SELECT id FROM room_reservation").fetchone()[0]
    r = encoder.post(f"/rooms/{rid}/withdraw", data={}, follow_redirects=True)
    assert "your own" in r.text
    assert conn.execute("SELECT status FROM room_reservation WHERE id=?", (rid,)).fetchone()[0] == "requested"


def test_success_banner_only_for_your_own_reference(viewer, encoder, conn):
    day = bookable_day(conn)
    ref = rooms.get_reservation(conn, rooms.request(
        conn, title="Mine", day=day, slot_ids=[slot_id(conn, 9)],
        requester_user_id=st.get_admin_user(conn, "viewer@test.local")["id"])["id"])["ref_code"]
    assert f"Request {ref} sent" in viewer.get(f"/rooms/mine?ok={ref}").text
    assert "Request CR-" not in encoder.get(f"/rooms/mine?ok={ref}").text
    assert "Request CR-" not in viewer.get("/rooms/mine?ok=<script>").text


def test_declined_request_shows_the_reason(viewer, conn):
    day = bookable_day(conn)
    viewer.post("/rooms/request", data=form(conn, day))
    rid = conn.execute("SELECT id FROM room_reservation").fetchone()[0]
    rooms.decline(conn, rid, "admin@test.local", "Room is for training")
    page = viewer.get("/rooms/mine").text
    assert "Declined" in page and "Room is for training" in page
