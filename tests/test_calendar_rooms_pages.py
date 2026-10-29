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
    assert "09:00" in page and "Conference room" in page and "/calendar/rooms/" in page


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


def test_a_booking_card_opens_its_details_and_the_booker_can_start_the_item(viewer, conn):
    b = book(conn, who="viewer@test.local")
    page = viewer.get(f"/calendar/rooms/{b['id']}").text
    assert "Budget review" in page and "Make the calendar item for this booking" in page
    r = viewer.post(f"/calendar/rooms/{b['id']}/make-item", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/calendar/entries/")
    assert rooms.get_reservation(conn, b["id"])["calendar_entry_id"]
    again = viewer.get(f"/calendar/rooms/{b['id']}", follow_redirects=False)
    assert again.status_code == 303 and again.headers["location"].startswith("/calendar/entries/")


def test_someone_else_sees_the_booking_but_cannot_start_its_item(viewer, conn):
    b = book(conn)                                                # booked by the encoder
    page = viewer.get(f"/calendar/rooms/{b['id']}").text
    assert "Budget review" in page and "Make the calendar item for this booking" not in page
    viewer.post(f"/calendar/rooms/{b['id']}/make-item", follow_redirects=False)
    assert not rooms.get_reservation(conn, b["id"])["calendar_entry_id"]


def test_an_administrator_can_start_the_item_for_someone_elses_booking(admin, conn):
    b = book(conn)                                                # booked by the encoder
    assert "Make the calendar item for this booking" in admin.get(f"/calendar/rooms/{b['id']}").text
    r = admin.post(f"/calendar/rooms/{b['id']}/make-item", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith("/calendar/entries/")
    entry_id = rooms.get_reservation(conn, b["id"])["calendar_entry_id"]
    assert entry_id and st.cal_get(conn, entry_id)["people"][0]["user_id"] == b["requester_user_id"]


def test_the_booker_sees_the_room_features_their_role_allows(encoder, manager, conn):
    b = book(conn)                                                # booked by the encoder
    page = encoder.get(f"/calendar/rooms/{b['id']}").text
    assert "Make the calendar item for this booking" in page
    assert f'href="/rooms/meals/{b["id"]}"' in page and f'action="/rooms/{b["id"]}/withdraw"' in page
    assert 'href="/rooms/mine"' in page and "from_room=" not in page          # an encoder cannot create CSS activities
    m = book(conn, who="manager@test.local", title="Section meeting", hours=(13, 14))
    assert f'href="/create?from_room={m["id"]}"' in manager.get(f"/calendar/rooms/{m['id']}").text


def test_someone_else_sees_the_booking_but_none_of_its_actions(viewer, conn):
    b = book(conn)
    page = viewer.get(f"/calendar/rooms/{b['id']}").text
    assert "Budget review" in page and "Only the person who booked it" in page
    assert "/rooms/meals/" not in page and "from_room=" not in page and "/withdraw" not in page


def test_an_administrator_gets_the_item_but_cannot_withdraw_someone_elses_booking(admin, conn):
    b = book(conn)
    page = admin.get(f"/calendar/rooms/{b['id']}").text
    assert "Make the calendar item for this booking" in page and "/withdraw" not in page


def test_a_booking_tied_to_a_css_activity_opens_the_activity_page(encoder, conn):
    import test_rooms_activity as tra
    ev = tra.event(conn)
    b = book(conn)
    conn.execute("UPDATE room_reservation SET event_id=? WHERE id=?", (ev["id"], b["id"])); conn.commit()
    r = encoder.get(f"/calendar/rooms/{b['id']}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/activities/{ev['event_token']}/manage"
