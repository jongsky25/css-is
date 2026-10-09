"""Conference room R8 over HTTP: the activity form's room line, /create?from_room, the banner and its buttons."""
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
    # The activities these tests create are real rows in the shared test database: take them out again, or they
    # turn up on other tests' home pages ("Coming up").
    for (eid,) in c.execute("SELECT id FROM event WHERE title LIKE 'R8 %'").fetchall():
        forms = [r[0] for r in c.execute("SELECT form_instance_id FROM event_form WHERE event_id=?", (eid,))]
        c.execute("DELETE FROM event_form WHERE event_id=?", (eid,))
        for fid in forms:
            c.execute("DELETE FROM form_instance WHERE id=?", (fid,))
        c.execute("DELETE FROM event WHERE id=?", (eid,))
    c.commit(); c.close()


def day(conn, extra=3):
    return rooms.add_working_days(conn, tz.today_local(), rooms.LEAD_WORKING_DAYS + extra)


def S(conn, *hours):
    by = {s["start_time"]: s["id"] for s in rooms.list_slots(conn)}
    return [by[f"{h:02d}:00"] for h in hours]


def uid(conn, name):
    return st.get_admin_user(conn, name)["id"]


def create(client, conn, name, d=None, **extra):
    data = {"event_type": "bureau", "activity_name": name, "event_date": (d or day(conn)).isoformat(),
            "qr_mode": "combined", "modality": "f2f"}
    data.update(extra)
    return client.post("/create", data=data, follow_redirects=True)


def event_of(conn, title):
    return conn.execute("SELECT id, event_token FROM event WHERE title=? ORDER BY id DESC LIMIT 1", (title,)).fetchone()


# -------------------------------------------------------------- the form's room line ---

def test_the_form_has_a_collapsed_room_line_with_hours(manager, conn):
    page = manager.get("/create").text
    assert 'id="room-chip"' in page and "Also reserve the conference room" in page
    assert page.count('name="room_from"') == 1 and "room_chip.js" in page
    assert "<details class=\"room-chip\" id=\"room-chip\" >" in page or "<details class=\"room-chip\" id=\"room-chip\">" in page


def test_ticking_the_room_files_a_request_tied_to_the_new_activity(manager, conn):
    s9, s10 = S(conn, 9, 10)
    r = create(manager, conn, "R8 activity with a room", reserve_room="1", room_from=s9, room_to=s10, room_meals="1")
    assert r.status_code == 200 and "Requested (CR-" in r.text
    ev = event_of(conn, "R8 activity with a room")
    res = conn.execute("SELECT title, status, event_id, meals_requested, modality FROM room_reservation").fetchone()
    assert res == ("R8 activity with a room", "requested", ev[0], 1, "f2f")


def test_a_room_choice_that_cannot_work_stops_before_the_activity_is_saved(manager, conn):
    s9, s10 = S(conn, 9, 10)
    r = create(manager, conn, "R8 too soon", d=tz.today_local(), reserve_room="1", room_from=s9, room_to=s10)
    assert r.status_code == 400 and "Conference room:" in r.text and "notice" in r.text and "Untick the room line" in r.text
    assert event_of(conn, "R8 too soon") is None and conn.execute("SELECT COUNT(*) FROM room_reservation").fetchone()[0] == 0
    assert 'name="reserve_room" value="1" id="room-chip-box" checked' in r.text                 # what they chose is kept


def test_taken_hours_are_caught_too(manager, conn):
    held = rooms.request(conn, title="Held", day=day(conn), slot_ids=S(conn, 9), requester_user_id=uid(conn, "encoder@test.local"))
    rooms.approve(conn, held["id"], "admin@test.local")
    r = create(manager, conn, "R8 clash", reserve_room="1", room_from=S(conn, 9)[0], room_to=S(conn, 10)[0])
    assert r.status_code == 400 and "already booked" in r.text and event_of(conn, "R8 clash") is None


def test_without_the_tick_no_room_is_asked_for(manager, conn):
    create(manager, conn, "R8 no room needed")
    assert conn.execute("SELECT COUNT(*) FROM room_reservation").fetchone()[0] == 0


# --------------------------------------------------------- from a reservation ---

def test_create_activity_from_a_reservation_starts_filled_in_and_links_back(manager, conn):
    r = rooms.request(conn, title="R8 from the room", day=day(conn), slot_ids=S(conn, 13, 14),
                      requester_user_id=uid(conn, "manager@test.local"), modality="online")
    page = manager.get(f"/create?from_room={r['id']}").text
    assert 'value="R8 from the room"' in page and r["day"] in page and f'value="{r["id"]}"' in page and r["ref_code"] in page
    assert 'id="room-chip-box"' not in page                                   # already has a room: no second line
    done = create(manager, conn, "R8 from the room", d=tz.today_local().__class__.fromisoformat(r["day"]), from_room=str(r["id"]),
                  from_room_ref=r["ref_code"], modality="online")
    assert done.status_code == 200 and f"Linked to your reservation {r['ref_code']}" in done.text
    ev = event_of(conn, "R8 from the room")
    assert rooms.get_reservation(conn, r["id"])["event_id"] == ev[0]
    assert conn.execute("SELECT COUNT(*) FROM room_reservation").fetchone()[0] == 1            # it did not file a second one


def test_someone_elses_reservation_does_not_prefill(manager, encoder, conn):
    r = rooms.request(conn, title="Not yours to use", day=day(conn), slot_ids=S(conn, 9), requester_user_id=uid(conn, "encoder@test.local"))
    assert "Not yours to use" not in manager.get(f"/create?from_room={r['id']}").text


def test_my_reservations_offers_the_shortcut_and_shows_the_activity(manager, conn):
    r = rooms.request(conn, title="R8 shortcut", day=day(conn), slot_ids=S(conn, 9), requester_user_id=uid(conn, "manager@test.local"))
    assert f"/create?from_room={r['id']}" in manager.get("/rooms/mine").text
    create(manager, conn, "R8 shortcut", d=tz.today_local().__class__.fromisoformat(r["day"]), from_room=str(r["id"]))
    page = manager.get("/rooms/mine").text
    assert "CSS activity:" in page and "Create a CSS activity for this" not in page


def test_the_day_lookup_for_the_form_is_signed_in_only_and_shows_no_titles(manager, client, conn):
    held = rooms.request(conn, title="Confidential", day=day(conn), slot_ids=S(conn, 9), requester_user_id=uid(conn, "encoder@test.local"))
    rooms.approve(conn, held["id"], "admin@test.local")
    j = manager.get(f"/rooms/api/day?date={held['day']}")
    assert j.status_code == 200 and j.json()["hours"][2]["state"] == "booked" and len(j.json()["slots"]) == 12 and "Confidential" not in j.text
    assert manager.get("/rooms/api/day?date=nope").status_code == 400
    assert client.get(f"/rooms/api/day?date={held['day']}", follow_redirects=False).status_code in (302, 303, 401)


# ----------------------------------------------------------------- the banner ---

def make(manager, conn, name, hours=(9, 10), approve=True):
    r = create(manager, conn, name, reserve_room="1", room_from=S(conn, hours[0])[0], room_to=S(conn, hours[-1])[0])
    ev = event_of(conn, name)
    rid = conn.execute("SELECT id FROM room_reservation WHERE event_id=?", (ev[0],)).fetchone()[0]
    if approve:
        rooms.approve(conn, rid, "admin@test.local")
    return ev, rid


def test_the_activity_page_shows_the_room_and_a_prompt_when_there_is_none(manager, conn):
    create(manager, conn, "R8 no room yet")
    assert "Need the conference room for this activity?" in manager.get(f"/activities/{event_of(conn, 'R8 no room yet')[1]}/manage").text
    ev, rid = make(manager, conn, "R8 with room")
    page = manager.get(f"/activities/{ev[1]}/manage").text
    assert "Conference room reserved" in page


def test_moving_the_activity_prompts_a_move_and_the_button_files_it(manager, admin, conn):
    ev, rid = make(manager, conn, "R8 will move")
    new = rooms.add_working_days(conn, tz.today_local(), 10)
    st.set_event_dates(conn, ev[0], new.isoformat(), None)
    page = manager.get(f"/activities/{ev[1]}/manage").text
    assert "booked for a different day" in page and "Request a move to" in page
    r = manager.post(f"/rooms/{rid}/move", data={"day": new.isoformat(), "next": f"/activities/{ev[1]}/manage"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].startswith(f"/activities/{ev[1]}/manage?roomok=")
    after = manager.get(r.headers["location"]).text
    assert "A move is waiting for approval" in after and "Move requested" in after
    assert rooms.get_reservation(conn, rid)["status"] == "approved"
    q = admin.get("/approvals").text
    assert "Move" in q and "Approving releases the old hours" in q


def test_a_bad_move_comes_back_to_the_activity_with_a_message_in_its_own_key(manager, conn):
    ev, rid = make(manager, conn, "R8 bad move")
    back = f"/activities/{ev[1]}/manage"
    r = manager.post(f"/rooms/{rid}/move", data={"day": "2020-01-01", "next": back}, follow_redirects=False)
    assert r.headers["location"].startswith(back + "?roomerr=")                     # not `err`: the manage page owns that one
    assert "already passed" in manager.get(r.headers["location"]).text


def test_the_redirect_target_must_be_on_this_site(manager, conn):
    ev, rid = make(manager, conn, "R8 safe next")
    for bad in ("https://evil.example/x", "//evil.example/x", "/admin/users", "/activities/../x//y"):
        r = manager.post(f"/rooms/{rid}/move", data={"day": "2020-01-01", "next": bad}, follow_redirects=False)
        assert r.headers["location"].startswith("/rooms/mine"), bad


def test_a_cancelled_room_shows_on_the_activity_with_times_to_pick(manager, admin, conn):
    ev, rid = make(manager, conn, "R8 loses its room")
    r = rooms.get_reservation(conn, rid)
    admin.post("/rooms/encode", data={"day": r["day"], "from_slot": S(conn, 9)[0], "to_slot": S(conn, 10)[0], "title": "Director",
                                      "for_name": "Director", "bump": "1", "bump_reason": "Director needs the room"})
    page = manager.get(f"/activities/{ev[1]}/manage").text
    assert "no room any more" in page and "Director needs the room" in page and "booked at once" in page
    o = rooms.suggestions_for(conn, rooms.get_reservation(conn, rid))[0]
    back = f"/activities/{ev[1]}/manage"
    resp = manager.post(f"/rooms/{rid}/take", data={"day": o["day"], "slots": ",".join(map(str, o["slot_ids"])), "next": back},
                        follow_redirects=False)
    assert resp.headers["location"].startswith(back + "?roomok=")
    assert "no room any more" not in manager.get(resp.headers["location"]).text


def test_an_archived_activity_offers_to_release_its_room(manager, conn):
    ev, rid = make(manager, conn, "R8 archived")
    conn.execute("UPDATE form_instance SET archived=1 WHERE id IN (SELECT form_instance_id FROM event_form WHERE event_id=?)", (ev[0],)); conn.commit()
    page = manager.get(f"/activities/{ev[1]}/manage").text
    assert "archived but still holds the room" in page and "Withdraw the booking" in page
    r = manager.post(f"/rooms/{rid}/withdraw", data={"next": f"/activities/{ev[1]}/manage", "reason": "The activity was archived."},
                     follow_redirects=False)
    assert rooms.get_reservation(conn, rid)["status"] == "withdrawn" and r.headers["location"] == f"/activities/{ev[1]}/manage"
