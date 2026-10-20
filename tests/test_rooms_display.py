"""Conference room R10: the door / TV display (what it shows, who can see it) and repeat-weekly over HTTP."""
from __future__ import annotations
from datetime import datetime

import pytest

import rooms
import storage as st
import tzutil as tz
from conftest import in_the_directory

ADMIN_UNIT = "BLHSD/ADMIN"
THU = "2030-03-07"

@pytest.fixture(autouse=True)
def _admin_account_is_in_the_section(app_mod):
    """Only Administrative Section members approve, so the seeded admin account joins it."""
    with in_the_directory(app_mod, "admin@test.local", path="ADMINFX/ADMIN"):
        yield


def at(hh, mm=0, day=THU):
    return datetime.fromisoformat(f"{day}T{hh:02d}:{mm:02d}:00")


@pytest.fixture()
def conn(app_mod):
    c = st.connect(app_mod.DB); st.init_db(c); rooms.ensure_slots(c)
    yield c
    for t in ("room_meal_item", "room_meal", "room_reservation_slot", "room_reservation", "room_block", "room_notice"):
        c.execute(f"DELETE FROM {t}")
    c.execute("DELETE FROM holiday WHERE day='2030-03-07'")                              # the shared test database must stay as found
    for k in (rooms.DISPLAY_TOKEN_KEY, rooms.DISPLAY_TITLES_KEY):
        c.execute("DELETE FROM app_setting WHERE key=?", (k,))
    c.commit(); c.close()


def S(conn, *hours):
    by = {s["start_time"]: s["id"] for s in rooms.list_slots(conn)}
    return [by[f"{h:02d}:00"] for h in hours]


def book(conn, title, hours, who="encoder@test.local", day=THU):
    r = rooms.request(conn, title=title, day=day, slot_ids=S(conn, *hours), requester_user_id=st.get_admin_user(conn, who)["id"],
                      today=datetime(2030, 3, 4).date())
    return rooms.approve(conn, r["id"], "admin@test.local", today=datetime(2030, 3, 4).date())


# --------------------------------------------------------------- what it shows ---

def test_free_with_the_next_booking_and_the_whole_days_schedule(conn):
    book(conn, "Morning huddle", (9, 10)); book(conn, "Budget hearing", (13, 14, 15))
    d = rooms.display_data(conn, at(11, 30))
    assert d["current"] is None and d["free_until"] == "13:00" and d["free_until_label"] == "1 PM"
    assert d["next"]["title"] == "Budget hearing" and d["next"]["label"] == "1 PM – 4 PM"
    assert [(s["title"], s["state"]) for s in d["schedule"]] == [("Morning huddle", "done"), ("Budget hearing", "next")]
    assert d["date_label"] == "Thursday 7 March 2030" and d["time"] == "11:30:00"


def test_in_use_now_and_the_one_after(conn):
    book(conn, "Morning huddle", (9, 10)); book(conn, "Budget hearing", (13, 14))
    d = rooms.display_data(conn, at(10, 15))
    assert d["current"]["title"] == "Morning huddle" and d["current"]["label"] == "9 AM – 11 AM" and d["free_until"] is None
    assert d["next"]["title"] == "Budget hearing"
    assert rooms.display_data(conn, at(9, 0))["current"] and not rooms.display_data(conn, at(11, 0))["current"]     # the end hour is already free


def test_a_multi_hour_booking_is_one_line_and_after_hours_say_so(conn):
    book(conn, "Workshop", (8, 9, 10, 11))
    d = rooms.display_data(conn, at(12))
    assert len(d["schedule"]) == 1 and d["free_until"] == "19:00" and d["next"] is None
    late = rooms.display_data(conn, at(19, 30))
    assert late["after_hours"] and late["free_until"] is None
    assert rooms.display_data(conn, at(6, 15))["before_hours"]


def test_pending_and_withdrawn_bookings_never_appear(conn):
    rooms.request(conn, title="Not approved", day=THU, slot_ids=S(conn, 9), requester_user_id=st.get_admin_user(conn, "encoder@test.local")["id"],
                  today=datetime(2030, 3, 4).date())
    w = book(conn, "Withdrawn", (11,)); rooms.withdraw(conn, w["id"], st.get_admin_user(conn, "encoder@test.local")["id"])
    assert rooms.display_data(conn, at(8))["schedule"] == []


@pytest.mark.parametrize("day, why", [("2030-03-09", "weekends"), ("2030-03-10", "weekends")])
def test_weekends_say_closed(conn, day, why):
    assert why in rooms.display_data(conn, at(10, day=day))["closed"]


def test_holidays_and_whole_day_closures_say_closed(conn):
    st.set_holiday(conn, THU, "Test holiday")
    assert "Test holiday" in rooms.display_data(conn, at(10))["closed"]
    rooms.add_block(conn, "admin@test.local", datetime(2030, 3, 11).date(), None, "Fumigation", today=datetime(2030, 3, 4).date())
    assert "Fumigation" in rooms.display_data(conn, at(10, day="2030-03-11"))["closed"]


def test_titles_can_be_hidden(conn):
    book(conn, "Disciplinary hearing", (13, 14))
    d = rooms.display_data(conn, at(13, 30), show_titles=False)
    assert d["current"]["title"] == "Reserved" and d["current"]["who"] == "" and "Disciplinary" not in str(d)
    st.set_setting(conn, rooms.DISPLAY_TITLES_KEY, "0")
    assert rooms.display_data(conn, at(13, 30))["current"]["title"] == "Reserved"


def test_a_guest_booking_shows_the_organisation(conn):
    r = rooms.request_external(conn, name="Ana", org="Partner NGO", email="a@x.org", phone="", title="Site visit", day=THU, slot_ids=S(conn, 9),
                               consent=True, today=datetime(2030, 3, 4).date())
    rooms.approve(conn, r["id"], "admin@test.local", today=datetime(2030, 3, 4).date())
    assert rooms.display_data(conn, at(9, 30))["current"]["who"] == "Guest · Partner NGO" and "a@x.org" not in str(rooms.display_data(conn, at(9, 30)))


# ------------------------------------------------------------- the address ---

def test_the_secret_is_made_once_and_replaced_on_demand(conn):
    assert rooms.display_token(conn, create=False) is None
    t = rooms.display_token(conn)
    assert len(t) >= 24 and rooms.display_token(conn) == t and rooms.display_token_ok(conn, t)
    new = rooms.reset_display_token(conn)
    assert new != t and not rooms.display_token_ok(conn, t) and rooms.display_token_ok(conn, new)
    assert not rooms.display_token_ok(conn, "") and not rooms.display_token_ok(conn, None)


def test_the_screen_opens_by_its_private_address_without_a_login(client, conn):
    tok = rooms.display_token(conn)
    r = client.get(f"/rooms/display/{tok}")
    assert r.status_code == 200 and 'http-equiv="refresh" content="60"' in r.text and "Scan to request the room" in r.text
    assert r.headers["cache-control"] == "no-store" and "noindex" in r.headers["x-robots-tag"] and "noindex" in r.text
    assert "data:image/png;base64," in r.text and "alt=\"QR code to request the conference room\"" in r.text


def test_a_wrong_or_replaced_address_shows_nothing(client, conn):
    tok = rooms.display_token(conn)
    for bad in ("nope", tok[:-1] + ("x" if tok[-1] != "x" else "y")):
        r = client.get(f"/rooms/display/{bad}")
        assert r.status_code == 404 and "Conference room" not in r.text and "noindex" in r.headers["x-robots-tag"]
    rooms.reset_display_token(conn)
    assert client.get(f"/rooms/display/{tok}").status_code == 404


def test_without_a_token_you_must_be_signed_in(client, viewer, conn):
    assert client.get("/rooms/display", follow_redirects=False).status_code in (302, 303, 401)
    assert viewer.get("/rooms/display").status_code == 200


def test_the_page_itself_hides_titles_when_they_are_off(client, conn, monkeypatch):
    """Whatever time it is, with titles off the HTML must not carry the meeting's title."""
    monkeypatch.setattr(tz, "now_local", lambda: at(10, 15))
    book(conn, "Disciplinary hearing", (9, 10, 11))
    tok = rooms.display_token(conn)
    assert "Disciplinary hearing" in client.get(f"/rooms/display/{tok}").text
    st.set_setting(conn, rooms.DISPLAY_TITLES_KEY, "0")
    page = client.get(f"/rooms/display/{tok}").text
    assert "Disciplinary hearing" not in page and "Reserved" in page and "In use now" in page


# ---------------------------------------------------------------------- setup ---

def test_only_the_section_sets_it_up(viewer, admin, conn):
    assert viewer.get("/rooms/display-setup").status_code == 403
    assert viewer.post("/rooms/display-setup", data={"action": "reset"}).status_code == 403
    page = admin.get("/rooms/display-setup").text
    assert "/rooms/display/" in page and "Make a new address" in page and "data:image/png;base64," in page


def test_a_section_member_can_set_it_up_and_make_a_new_address(app_mod, viewer, client, conn):
    with in_the_directory(app_mod, "viewer@test.local", path=ADMIN_UNIT):
        old = viewer.get("/rooms/display-setup").text.split("/rooms/display/")[1].split('"')[0].split("<")[0]
        assert client.get(f"/rooms/display/{old}").status_code == 200
        viewer.post("/rooms/display-setup", data={"action": "reset"})
        assert client.get(f"/rooms/display/{old}").status_code == 404


def test_the_titles_switch_is_saved(admin, conn):
    admin.post("/rooms/display-setup", data={"action": "titles"})                        # box unticked
    assert not rooms.display_titles_on(conn)
    admin.post("/rooms/display-setup", data={"action": "titles", "show_titles": "1"})
    assert rooms.display_titles_on(conn)
    assert "Show meeting titles" in admin.get("/rooms/display-setup").text
