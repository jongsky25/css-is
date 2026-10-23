"""Meal requests work without reserving a room and remain private to their owner."""
from datetime import timedelta

import pytest

import meals
import rooms
import storage as st
import tzutil as tz
from conftest import in_the_directory


@pytest.fixture()
def conn(app_mod):
    c = st.connect(app_mod.DB)
    st.init_db(c)
    yield c
    c.close()


@pytest.fixture()
def section(app_mod, admin):
    with in_the_directory(app_mod, "admin@test.local", path="ADMINFX/ADMIN"):
        yield admin


def form(**kw):
    values = {"title": "Field activity catering", "day": (tz.today_local() + timedelta(days=2)).isoformat(),
              "venue": "City health office", "pax": "25", "special": "3 vegetarian", "want_lunch": "1", "time_lunch": "12:15"}
    return {**values, **kw}


def submit(client, **kw):
    return client.post("/meals/new", data=form(**kw), follow_redirects=False)


def test_request_order_monitor_delivery_without_any_room(viewer, section, conn, monkeypatch):
    page = viewer.get("/meals/new")
    assert page.status_code == 200 and "No conference room reservation is required" in page.text
    response = submit(viewer)
    assert response.status_code == 303
    url = response.headers["location"]
    rid = int(url.rsplit("/", 1)[1])
    assert conn.execute("SELECT COUNT(*) FROM room_reservation").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM room_reservation_slot").fetchone()[0] == 0
    for path in (url, "/meals/mine", "/meals"):
        client = section if path == "/meals" else viewer
        text = client.get(path).text
        assert "Field activity catering" in text and "Awaiting order" in text
    assert "Withdraw this meal request" in viewer.get(url).text
    response = section.post(f"{url}/tag", data={"meal": "lunch", "status": "requested", "note": "Supplier confirmed"})
    assert response.status_code == 200
    assert meals.get(conn, rid)["items"][0]["status"] == "requested"
    assert "Ordered" in viewer.get("/meals/mine").text
    response = section.post(f"{url}/tag", data={"meal": "lunch", "status": "delivered"})
    assert response.status_code == 400 and "on or after" in response.text
    activity_day = tz.today_local() + timedelta(days=2)
    monkeypatch.setattr(tz, "today_local", lambda: activity_day)
    assert section.post(f"{url}/tag", data={"meal": "lunch", "status": "delivered"}).status_code == 200
    assert meals.get(conn, rid)["overall"] == "Delivered"
    assert "Delivered" in viewer.get("/meals/mine").text


def test_other_users_cannot_read_change_or_withdraw_requests(viewer, encoder, admin, conn):
    response = submit(viewer)
    url = response.headers["location"]
    for path in (url, "/meals"):
        assert encoder.get(path).status_code == 403
    assert encoder.post(f"{url}/withdraw").status_code == 403
    assert encoder.post(f"{url}/tag", data={"meal": "lunch", "status": "requested"}).status_code == 403
    # An application administrator outside the Administrative Section has no order permission.
    assert admin.get("/meals").status_code == 403
    assert "Field activity catering" not in encoder.get("/meals/mine").text
    assert conn.execute("SELECT status FROM meal_request_item").fetchone()[0] == "pending"


@pytest.mark.parametrize("offset", [0, 1])
def test_two_calendar_day_cutoff_cannot_be_bypassed(viewer, conn, offset):
    response = submit(viewer, day=(tz.today_local() + timedelta(days=offset)).isoformat())
    assert response.status_code == 400 and "2 calendar days" in response.text
    assert 'value="Field activity catering"' in response.text
    assert conn.execute("SELECT COUNT(*) FROM meal_request").fetchone()[0] == 0


@pytest.mark.parametrize("values, message", [
    ({"venue": ""}, "venue"), ({"day": "bad"}, "valid activity date"), ({"pax": "0"}, "1 and 1000"),
    ({"want_lunch": "0"}, "at least one meal"), ({"time_lunch": "05:00"}, "06:00 and 19:00"),
])
def test_validation_writes_nothing(viewer, conn, values, message):
    response = submit(viewer, **values)
    assert response.status_code == 400 and message in response.text
    assert conn.execute("SELECT COUNT(*) FROM meal_request").fetchone()[0] == 0


def test_withdrawal_cancels_order_and_tells_section_to_contact_supplier(viewer, section, conn):
    url = submit(viewer).headers["location"]
    section.post(f"{url}/tag", data={"meal": "lunch", "status": "requested"})
    assert viewer.post(f"{url}/withdraw").status_code == 200
    assert "Withdrawn" in viewer.get("/meals/mine").text
    assert "supplier" in section.get("/meals").text
    response = section.post(f"{url}/tag", data={"meal": "lunch", "status": "pending"})
    assert response.status_code == 400 and "no longer active" in response.text
    assert conn.execute("SELECT status FROM meal_request_item").fetchone()[0] == "cancelled"


def test_existing_room_meals_are_accessible_in_my_meal_requests(viewer, conn):
    uid = st.get_admin_user(conn, "viewer@test.local")["id"]
    day = rooms.add_working_days(conn, tz.today_local(), 3)
    res = rooms.request(conn, title="Earlier room-linked meals", day=day,
                        slot_ids=[rooms.list_slots(conn)[0]["id"]], requester_user_id=uid, meals_requested=True)
    response = viewer.get("/meals/mine")
    assert "Earlier room-linked meals" in response.text
    assert f'/rooms/meals/{res["id"]}' in response.text


def test_new_routes_require_login(client):
    for path in ("/meals", "/meals/mine", "/meals/new", "/meals/1"):
        assert client.get(path, follow_redirects=False).status_code in (302, 303, 401)


def test_storage_upgrade_is_idempotent_and_preserves_requests(viewer, conn):
    submit(viewer)
    st.init_db(conn)
    st.init_db(conn)
    assert conn.execute("SELECT COUNT(*) FROM meal_request").fetchone()[0] == 1
    assert conn.execute("SELECT COUNT(*) FROM meal_request_item").fetchone()[0] == 1
