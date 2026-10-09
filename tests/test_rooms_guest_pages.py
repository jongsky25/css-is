"""Conference room R6 over HTTP: /room needs no login, the tracking page, the honeypot, rate limit, poster."""
from __future__ import annotations
from urllib.parse import quote

import pytest
from conftest import in_the_directory

import auth
import ratelimit
import rooms
import storage as st
import tzutil as tz

@pytest.fixture(autouse=True)
def _admin_account_is_in_the_section(app_mod):
    """Only Administrative Section members approve, so the seeded admin account joins it."""
    with in_the_directory(app_mod, "admin@test.local", path="ADMINFX/ADMIN"):
        yield


@pytest.fixture()
def conn(app_mod):
    c = st.connect(app_mod.DB); st.init_db(c); rooms.ensure_slots(c)
    yield c
    for t in ("room_reservation_slot", "room_reservation", "room_block", "room_notice"):
        c.execute(f"DELETE FROM {t}")
    c.commit(); c.close()


def day(conn, extra=3):
    return rooms.add_working_days(conn, tz.today_local(), rooms.LEAD_WORKING_DAYS + extra)


def sid(conn, hour):
    return next(s["id"] for s in rooms.list_slots(conn) if s["start_time"] == f"{hour:02d}:00")


def form(conn, **kw):
    f = {"day": day(conn).isoformat(), "from_slot": sid(conn, 9), "to_slot": sid(conn, 10), "title": "Site visit",
         "modality": "f2f", "name": "Ana Cruz", "org": "Partner NGO", "email": "ana@ngo.org", "consent": "1"}
    f.update(kw)
    return f


def submit(client, conn, **kw):
    r = client.post("/room", data=form(conn, **kw), follow_redirects=False)
    assert r.status_code == 303, r.text[:300]
    return r.headers["location"]


# ----------------------------------------------------------------------- the page ---

def test_the_page_opens_without_a_login(client, conn):
    for path in ("/room", "/room/"):
        r = client.get(path)
        assert r.status_code == 200 and "Request the conference room" in r.text and "Pick a day" in r.text
        assert "Approvals" not in r.text                                    # no staff navigation leaks onto it


def test_picking_a_day_shows_its_hours_and_the_form_without_any_titles(client, conn):
    d = day(conn)
    staff = st.get_admin_user(conn, "encoder@test.local")["id"]
    r = rooms.request(conn, title="Confidential budget", day=d, slot_ids=[sid(conn, 13)], requester_user_id=staff)
    rooms.approve(conn, r["id"], "admin")
    page = client.get(f"/room?date={d.isoformat()}").text
    assert "Booked" in page and "Free" in page and "Send my request" in page
    assert "Confidential budget" not in page
    assert "Send my request" not in client.get("/room").text                # no day chosen: no form yet


def test_the_day_json_is_public_and_title_free(client, conn):
    d = day(conn)
    staff = st.get_admin_user(conn, "encoder@test.local")["id"]
    rooms.approve(conn, rooms.request(conn, title="Confidential budget", day=d, slot_ids=[sid(conn, 9)], requester_user_id=staff)["id"], "admin")
    j = client.get(f"/room/day?date={d.isoformat()}")
    assert j.status_code == 200 and j.json()["hours"][2]["state"] == "booked" and "Confidential" not in j.text
    assert client.get("/room/day?date=nope").status_code == 400


def test_the_day_lookup_is_rate_limited(client, conn, monkeypatch):
    monkeypatch.setenv("CSS_RL_ROOM_VIEW", "3/60")
    d = day(conn).isoformat()
    codes = [client.get(f"/room/day?date={d}").status_code for _ in range(5)]
    assert codes == [200, 200, 200, 429, 429]


# ------------------------------------------------------------------- the request ---

def test_a_guest_request_lands_on_their_tracking_page(client, conn):
    loc = submit(client, conn, attendees="8", meals="1")
    assert loc.startswith("/room/t/") and loc.endswith("?new=1")
    page = client.get(loc).text
    assert "Request sent" in page and "ana@ngo.org" in page and "CR-" in page and "Site visit" in page
    row = conn.execute("SELECT status, source, attendees, meals_requested, ext_email_verified_at FROM room_reservation").fetchone()
    assert row == ("requested", "external", 8, 1, None)


def test_the_email_counts_as_confirmed_only_when_the_link_is_opened_later(client, conn, admin):
    loc = submit(client, conn)
    client.get(loc)                                                          # the redirect right after submitting
    assert "email not confirmed" in admin.get("/approvals").text
    client.get(loc.split("?")[0])                                            # the link from the email
    assert "email not confirmed" not in admin.get("/approvals").text
    assert "Guest" in admin.get("/approvals").text and "Partner NGO" in admin.get("/approvals").text


def test_errors_come_back_with_what_was_typed(client, conn):
    r = client.post("/room", data=form(conn, consent="", title="Keep me"))
    assert r.status_code == 400 and "tick the box" in r.text and 'value="Keep me"' in r.text
    r = client.post("/room", data=form(conn, email="nope"))
    assert r.status_code == 400 and "look right" in r.text
    r = client.post("/room", data={"title": "x"})
    assert r.status_code == 400 and "Pick a day" in r.text
    assert conn.execute("SELECT COUNT(*) FROM room_reservation").fetchone()[0] == 0


def test_the_honeypot_drops_bot_posts_quietly(client, conn):
    r = client.post("/room", data=form(conn, website="http://spam.example"), follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/room?sent=1"
    assert conn.execute("SELECT COUNT(*) FROM room_reservation").fetchone()[0] == 0
    assert "Request received" in client.get("/room?sent=1").text


def test_the_sixth_submission_in_an_hour_is_refused(client, conn):
    ratelimit.reset()
    for i in range(5):
        client.post("/room", data=form(conn, from_slot=sid(conn, 7 + i), to_slot=sid(conn, 7 + i), email=f"g{i}@x.org"))
    r = client.post("/room", data=form(conn, from_slot=sid(conn, 15), to_slot=sid(conn, 15), email="g9@x.org"))
    assert r.status_code == 429 and "several requests" in r.text
    assert conn.execute("SELECT COUNT(*) FROM room_reservation").fetchone()[0] == 5


def test_no_more_than_three_open_requests_per_email(client, conn):
    for h in (7, 9, 11):
        submit(client, conn, from_slot=sid(conn, h), to_slot=sid(conn, h))
    r = client.post("/room", data=form(conn, from_slot=sid(conn, 13), to_slot=sid(conn, 13)))
    assert r.status_code == 400 and "3 open requests" in r.text


# ------------------------------------------------------------------ tracking page ---

def test_a_guest_sees_status_without_staff_names_then_withdraws(client, admin, conn):
    loc = submit(client, conn).split("?")[0]
    rid = conn.execute("SELECT id FROM room_reservation").fetchone()[0]
    admin.post(f"/rooms/{rid}/decide", data={"action": "approve", "note": "ok"})
    page = client.get(loc).text
    assert "Approved" in page and "the Administrative Section" in page and "admin@test.local" not in page
    r = client.post(loc + "/withdraw", data={"reason": "Changed plans"}, follow_redirects=False)
    assert r.status_code == 303 and "done=withdrawn" in r.headers["location"]
    assert "withdrawn" in client.get(r.headers["location"]).text.lower()
    assert rooms.get_reservation(conn, rid)["status"] == "withdrawn"


def test_a_bumped_guest_picks_a_new_time_from_the_page(client, admin, conn):
    loc = submit(client, conn).split("?")[0]
    rid = conn.execute("SELECT id FROM room_reservation").fetchone()[0]
    admin.post(f"/rooms/{rid}/decide", data={"action": "approve"})
    admin.post("/rooms/encode", data={"day": day(conn).isoformat(), "from_slot": sid(conn, 9), "to_slot": sid(conn, 10),
                                      "title": "Director", "for_name": "Director", "bump": "1", "bump_reason": "Director needs the room"})
    page = client.get(loc).text
    assert "Director needs the room" in page and "booked at once" in page
    o = rooms.suggestions_for(conn, rooms.get_reservation(conn, rid))[0]
    r = client.post(loc + "/take", data={"day": o["day"], "slots": ",".join(map(str, o["slot_ids"]))}, follow_redirects=False)
    assert r.status_code == 303 and "?new=1" in r.headers["location"]
    assert "Approved" in client.get(r.headers["location"]).text


@pytest.mark.parametrize("tok", ["garbage", "a.b", ""])
def test_a_bad_link_is_a_dead_end(client, conn, tok):
    assert client.get(f"/room/t/{tok or 'x'}").status_code == 404
    assert client.post(f"/room/t/{tok or 'x'}/withdraw", data={}).status_code == 404


def test_a_guest_link_cannot_reach_a_staff_reservation(client, conn):
    staff = st.get_admin_user(conn, "encoder@test.local")["id"]
    r = rooms.request(conn, title="Staff", day=day(conn), slot_ids=[sid(conn, 9)], requester_user_id=staff)
    tok = quote(auth.make_room_track_token(r["id"]))
    assert client.get(f"/room/t/{tok}").status_code == 404
    assert client.post(f"/room/t/{tok}/withdraw", data={}).status_code == 404
    assert rooms.get_reservation(conn, r["id"])["status"] == "requested"


# ------------------------------------------------------------------------ poster ---

def test_the_poster_is_for_section_members_and_carries_the_permanent_address(admin, viewer, client, conn):
    assert viewer.get("/rooms/poster").status_code == 403
    assert client.get("/rooms/poster", follow_redirects=False).status_code in (302, 303, 401)
    page = admin.get("/rooms/poster").text
    assert "Scan to request the room" in page and "data:image/png;base64," in page
    assert "/room</p>" in page.replace("\n", "") or "/room<" in page
