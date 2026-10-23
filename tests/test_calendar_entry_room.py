"""The conference-room line on the calendar item form: create, edit, banner, one item on the calendar, the feed,
and the carry-over when the item becomes a CSS activity."""
from __future__ import annotations
from urllib.parse import urlencode

import pytest

import office_calendar as oc
import rooms
import storage as st
import tzutil as tz
from conftest import in_the_directory

FORM = {"Content-Type": "application/x-www-form-urlencoded"}


@pytest.fixture(autouse=True)
def _admin_in_the_section(app_mod):
    with in_the_directory(app_mod, "admin@test.local", path="ADMINFX/ADMIN"):
        yield


@pytest.fixture()
def conn(app_mod):
    c = st.connect(app_mod.DB); st.init_db(c); rooms.ensure_slots(c)
    yield c
    for t in ("room_reservation_slot", "room_reservation", "room_block", "room_notice"):
        c.execute(f"DELETE FROM {t}")
    for (i,) in c.execute("SELECT id FROM calendar_entry WHERE title LIKE 'CALROOM %'").fetchall():
        st.cal_delete(c, i)
    c.commit(); c.close()


def day(conn, extra=3):
    return rooms.add_working_days(conn, tz.today_local(), rooms.LEAD_WORKING_DAYS + extra)


def S(conn, *hours):
    by = {s["start_time"]: s["id"] for s in rooms.list_slots(conn)}
    return [by[f"{h:02d}:00"] for h in hours]


def post(client, url, d, **fields):
    data = {"title": "CALROOM Meeting", "kind": "meeting", "status": "confirmed", "start_date": d.isoformat(),
            "audience": "bureau", **fields}
    return client.post(url, content=urlencode(list(data.items())), headers=FORM, follow_redirects=False)


def entry_id(resp):
    return int(resp.headers["location"].split("/calendar/entries/")[1].split("?")[0])


def test_the_form_offers_the_room_line_with_the_date_and_time_fields_wired(manager, conn):
    page = manager.get("/calendar/new").text
    assert 'id="room-chip"' in page and "Also reserve the conference room for this calendar item" in page
    assert 'data-date="start_date"' in page and 'data-start="start_time"' in page and 'id="start_date"' in page


def test_ticking_the_room_files_a_request_tied_to_the_new_item(manager, conn):
    s9, s10 = S(conn, 9, 10)
    r = post(manager, "/calendar/new", day(conn), reserve_room="1", room_from=s9, room_to=s10, modality="online")
    assert r.status_code == 303
    eid = entry_id(r)
    row = conn.execute("SELECT title, status, calendar_entry_id, modality FROM room_reservation").fetchone()
    assert row == ("CALROOM Meeting", "requested", eid, "online")
    page = manager.get(r.headers["location"]).text
    assert "Conference room requested" in page                                   # the banner on the item's page
    assert "File travel claim" not in page and "File a travel claim" not in page  # the venue is the office


def test_a_room_choice_that_cannot_work_stops_before_the_item_is_saved(manager, conn):
    s9, s10 = S(conn, 9, 10)
    r = post(manager, "/calendar/new", tz.today_local(), reserve_room="1", room_from=s9, room_to=s10, room_meals="1")
    assert r.status_code == 400 and "Conference room:" in r.text and "Untick the room line" in r.text
    assert conn.execute("SELECT COUNT(*) FROM calendar_entry WHERE title LIKE 'CALROOM %'").fetchone()[0] == 0
    assert 'name="reserve_room" value="1" id="room-chip-box" checked' in r.text    # the choice is kept


def test_taken_hours_with_standby_save_the_item_and_file_a_provisional_request(manager, conn):
    d = day(conn)
    held = rooms.request(conn, title="Held", day=d, slot_ids=S(conn, 9), requester_user_id=st.get_admin_user(conn, "encoder@test.local")["id"])
    rooms.approve(conn, held["id"], "admin@test.local")
    r = post(manager, "/calendar/new", d, reserve_room="1", room_standby="1", room_from=S(conn, 9)[0], room_to=S(conn, 10)[0])
    assert r.status_code == 303
    assert conn.execute("SELECT status, standby FROM room_reservation WHERE title='CALROOM Meeting'").fetchone() == ("requested", 1)
    assert "Provisional (standby)" in manager.get(r.headers["location"]).text


def test_editing_an_item_with_a_room_never_files_a_second_one_and_moves_with_the_date(manager, conn):
    d = day(conn)
    s9, s10 = S(conn, 9, 10)
    r = post(manager, "/calendar/new", d, reserve_room="1", room_from=s9, room_to=s10)
    eid = entry_id(r)
    page = manager.get(f"/calendar/entries/{eid}/edit").text
    assert 'id="room-chip"' not in page and "Conference room requested" in page   # banner instead of a second chip
    later = rooms.add_working_days(conn, d, 2)
    e = st.cal_get(conn, eid)
    resp = post(manager, f"/calendar/entries/{eid}/edit", later, updated_at=e["updated_at"] or "", reserve_room="1",
                room_from=s9, room_to=s10)
    assert resp.status_code == 303
    assert conn.execute("SELECT COUNT(*) FROM room_reservation").fetchone()[0] == 1
    page = manager.get(f"/calendar/entries/{eid}").text
    assert "booked for a different day" in page and "Move the request to" in page
    res = conn.execute("SELECT id FROM room_reservation").fetchone()[0]
    manager.post(f"/rooms/{res}/move", data={"day": later.isoformat(), "next": f"/calendar/entries/{eid}"})
    assert rooms.get_reservation(conn, res)["day"] == later.isoformat()


def test_a_cancelled_item_offers_to_release_its_room(manager, conn):
    s9, s10 = S(conn, 9, 10)
    eid = entry_id(post(manager, "/calendar/new", day(conn), reserve_room="1", room_from=s9, room_to=s10))
    manager.post(f"/calendar/entries/{eid}/cancel")
    page = manager.get(f"/calendar/entries/{eid}").text
    assert "cancelled but still holds the room" in page and "Withdraw the booking" in page
    res = conn.execute("SELECT id FROM room_reservation").fetchone()[0]
    manager.post(f"/rooms/{res}/withdraw", data={"next": f"/calendar/entries/{eid}", "reason": "The calendar item was cancelled."})
    assert rooms.get_reservation(conn, res)["status"] == "withdrawn"


def test_the_calendar_draws_the_item_and_its_room_once(conn, app_mod):
    d = day(conn)
    me = {"id": st.get_admin_user(conn, "admin@test.local")["id"], "username": "admin@test.local", "role": "admin"}
    eid = st.cal_create(conn, "CALROOM Once", d.isoformat(), kind="meeting", audience="bureau", by="admin@test.local")
    r = rooms.request(conn, title="CALROOM Once", day=d, slot_ids=S(conn, 9, 10), requester_user_id=me["id"], calendar_entry_id=eid)
    rooms.approve(conn, r["id"], "admin@test.local")
    got = oc.items_between(conn, me, d, d, scope="bureau", layers=["entries", "rooms"])
    mine = [i for i in got if i["title"] == "CALROOM Once"]
    assert [i["layer"] for i in mine] == ["entries"] and mine[0]["time_note"] == "🏢 09:00–11:00"
    assert mine[0]["venue"] == "Conference room"
    feed = oc.build_feed(conn, me, "https://x.test", today=d)
    assert f"UID:room-{r['id']}@office-connect" not in feed                       # the item carries it


def test_turning_the_item_into_an_activity_keeps_its_room(manager, conn, app_mod):
    import calendar_routes as cr
    d = day(conn)
    s9, s10 = S(conn, 9, 10)
    eid = entry_id(post(manager, "/calendar/new", d, reserve_room="1", room_from=s9, room_to=s10, kind="training"))
    form = manager.get(f"/create?from_entry={eid}").text
    assert "linked to your conference room reservation" in form and 'name="reserve_room" value="1" id="room-chip-box"' not in form


def test_the_room_follows_the_item_into_its_activity_and_the_calendar_still_shows_one(manager, conn):
    d = day(conn)
    s9, s10 = S(conn, 9, 10)
    eid = entry_id(post(manager, "/calendar/new", d, title="CALROOM Training", reserve_room="1", room_from=s9, room_to=s10, kind="training"))
    res = conn.execute("SELECT id, ref_code FROM room_reservation").fetchone()
    r = manager.post("/create", data={"event_type": "bureau", "activity_name": "CALROOM Training", "event_date": d.isoformat(),
                                      "qr_mode": "combined", "modality": "f2f", "from_entry": str(eid),
                                      "from_room": str(res[0]), "from_room_ref": res[1]}, follow_redirects=True)
    assert r.status_code == 200 and "Linked to your reservation" in r.text
    ev = conn.execute("SELECT id FROM event WHERE title='CALROOM Training' ORDER BY id DESC LIMIT 1").fetchone()[0]
    assert conn.execute("SELECT event_id, calendar_entry_id FROM room_reservation").fetchone() == (ev, eid)
    me = {"id": st.get_admin_user(conn, "manager@test.local")["id"], "username": "manager@test.local", "role": "manager"}
    got = [i for i in oc.items_between(conn, me, d, d, scope="bureau", layers=["entries", "activities", "rooms"])
           if i["title"] == "CALROOM Training"]
    assert [i["layer"] for i in got] == ["activities"]
    # tidy: the activity is a real row in the shared test database
    forms = [x[0] for x in conn.execute("SELECT form_instance_id FROM event_form WHERE event_id=?", (ev,))]
    conn.execute("DELETE FROM event_form WHERE event_id=?", (ev,))
    for fid in forms:
        conn.execute("DELETE FROM form_instance WHERE id=?", (fid,))
    conn.execute("DELETE FROM calendar_entry WHERE event_id=?", (ev,))
    conn.execute("DELETE FROM event WHERE id=?", (ev,)); conn.commit()


def test_my_reservations_and_the_approvals_card_show_what_the_room_is_for_and_standby(manager, conn):
    d = day(conn)
    held = rooms.request(conn, title="Held", day=d, slot_ids=S(conn, 9), requester_user_id=st.get_admin_user(conn, "encoder@test.local")["id"])
    rooms.approve(conn, held["id"], "admin@test.local")
    r = post(manager, "/calendar/new", d, reserve_room="1", room_standby="1", room_from=S(conn, 9)[0], room_to=S(conn, 10)[0])
    eid = entry_id(r)
    mine = manager.get("/rooms/mine").text
    assert "Provisional (standby)" in mine and f"/calendar/entries/{eid}" in mine and "Calendar item:" in mine
    assert "Create a CSS activity for this" not in mine.split("CALROOM Meeting")[1].split("</tr>")[0]
    q = [x for x in rooms.queue(conn) if x["title"] == "CALROOM Meeting"][0]
    assert q["linked"]["kind"] == "Calendar item" and q["standby"] == 1
    import rooms_notify
    rooms_notify.on_requested(conn, rooms.get_reservation(conn, q["id"]))
    assert conn.execute("SELECT COUNT(*) FROM room_notice WHERE text LIKE '%STANDBY%'").fetchone()[0] >= 1


def test_a_form_sent_back_with_an_error_keeps_the_room_choice_the_person_made(manager, conn):
    """Spot Feedback #114: the page auto-ticks the room for an online item; after an error the re-rendered form
    must be marked as already decided, or it would tick the room again over the person's untick."""
    d = day(conn)
    fresh = manager.get("/calendar/new").text
    assert 'data-decided' not in fresh                                       # a blank form may still auto-tick
    bad = post(manager, "/calendar/new", d, title="", modality="online")      # no room ticked, but invalid
    assert bad.status_code == 400 and 'data-decided="1"' in bad.text
    assert conn.execute("SELECT COUNT(*) FROM room_reservation").fetchone()[0] == 0
