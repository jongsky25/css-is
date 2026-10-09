"""Conference room R7 over HTTP: the calendar page, its layouts and filter, the legend, and the API."""
from __future__ import annotations
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


def day(conn, extra=2):
    return rooms.add_working_days(conn, tz.today_local(), rooms.LEAD_WORKING_DAYS + extra)


def book(conn, who="encoder@test.local", title="Budget review", approve=True, hours=(9, 10)):
    by = {s["start_time"]: s["id"] for s in rooms.list_slots(conn)}
    r = rooms.request(conn, title=title, day=day(conn), slot_ids=[by[f"{h:02d}:00"] for h in hours],
                      requester_user_id=st.get_admin_user(conn, who)["id"])
    return rooms.approve(conn, r["id"], "admin@test.local") if approve else r


def test_the_agenda_shows_an_approved_booking_to_anyone_with_its_hours_and_icon(viewer, conn):
    book(conn)
    page = viewer.get("/calendar").text
    assert "Budget review" in page and 'data-kind="room"' in page and "🏢" in page
    assert "09:00" in page and "Conference room" in page and "/rooms?week=" in page


def test_a_pending_request_is_hidden_from_others_and_marked_for_its_owner(viewer, encoder, conn):
    book(conn, title="Not decided yet", approve=False)
    assert "Not decided yet" not in viewer.get("/calendar").text
    mine = encoder.get("/calendar").text
    assert "Not decided yet" in mine and 'data-status="tentative"' in mine and "Awaiting approval" in mine


def test_the_kind_filter_and_the_legend_know_about_rooms(viewer, conn):
    book(conn)
    page = viewer.get("/calendar").text
    assert '<option value="room"' in page and "Conference room</span>" in page.replace("\n", "")
    only = viewer.get("/calendar?kind=room").text
    assert "Budget review" in only
    assert "Budget review" not in viewer.get("/calendar?kind=meeting").text


def test_the_month_view_shows_it_but_the_who_is_where_layouts_do_not(viewer, conn):
    book(conn)
    assert "Budget review" in viewer.get("/calendar?view=month").text
    assert "Budget review" not in viewer.get("/calendar?view=week").text
    assert "Budget review" not in viewer.get("/calendar?view=timeline").text


def test_the_more_menu_offers_the_room(viewer, conn):
    assert "Reserve the conference room" in viewer.get("/calendar").text


def test_the_api_serves_rooms_only_when_asked_and_never_a_hidden_request(viewer, encoder, conn):
    book(conn, title="Approved one"); book(conn, title="Pending one", approve=False, hours=(13,))
    start = tz.today_local().isoformat()
    default = viewer.get(f"/api/calendar?start={start}").json()
    assert not any(i["layer"] == "rooms" for i in default["items"])
    asked = viewer.get(f"/api/calendar?start={start}&layers=rooms").json()
    assert [i["title"] for i in asked["items"]] == ["Approved one"]
    got = asked["items"][0]
    assert got["kind"] == "room" and got["venue"] == "Conference room" and got["start_time"] == "09:00" and got["end_time"] == "11:00"
    mine = encoder.get(f"/api/calendar?start={start}&layers=rooms").json()
    assert sorted(i["title"] for i in mine["items"]) == ["Approved one", "Pending one"]
    assert viewer.get(f"/api/calendar?start={start}&layers=rooms&kind=room").status_code == 200
