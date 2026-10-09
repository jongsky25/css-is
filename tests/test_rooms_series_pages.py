"""Conference room R10 over HTTP: repeat-weekly requests, the series on the approval card, and withdrawing a series."""
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
    for t in ("room_meal_item", "room_meal", "room_reservation_slot", "room_reservation", "room_block", "room_notice"):
        c.execute(f"DELETE FROM {t}")
    c.commit(); c.close()


def day(conn, extra=3):
    return rooms.add_working_days(conn, tz.today_local(), rooms.LEAD_WORKING_DAYS + extra)


def S(conn, *hours):
    by = {s["start_time"]: s["id"] for s in rooms.list_slots(conn)}
    return [by[f"{h:02d}:00"] for h in hours]


def form(conn, repeat="1", weeks=3, **kw):
    d = day(conn)
    f = {"day": d.isoformat(), "from_slot": S(conn, 9)[0], "to_slot": S(conn, 10)[0], "title": "Weekly huddle", "modality": "f2f",
         "repeat": repeat, "until": (d + timedelta(weeks=weeks)).isoformat()}
    f.update(kw)
    return f


def rows(conn):
    return conn.execute("SELECT day, status, series_id FROM room_reservation ORDER BY day").fetchall()


def test_the_panel_offers_a_repeat(viewer, conn):
    page = viewer.get("/rooms").text
    assert 'name="repeat"' in page and "Every week" in page and "Every 2 weeks" in page and 'name="until"' in page


def test_a_weekly_request_files_every_date_and_says_so(viewer, conn):
    r = viewer.post("/rooms/request", data=form(conn), follow_redirects=False)
    assert r.status_code == 303 and "series=4" in r.headers["location"]
    got = rows(conn)
    assert len(got) == 4 and len({g[2] for g in got}) == 1 and got[0][2] is not None
    assert "for 4 dates" in viewer.get(r.headers["location"]).text


def test_a_single_request_still_works_when_repeat_is_off(viewer, conn):
    r = viewer.post("/rooms/request", data=form(conn, repeat=""), follow_redirects=False)
    assert r.status_code == 303 and "series=" not in r.headers["location"] and len(rows(conn)) == 1


def test_repeat_needs_an_end_date(viewer, conn):
    r = viewer.post("/rooms/request", data=form(conn, until=""))
    assert r.status_code == 400 and "last date the meeting repeats" in r.text and rows(conn) == []


def test_dates_that_cannot_be_had_are_shown_first_then_the_rest_can_be_requested(viewer, encoder, conn):
    d = day(conn)
    held = rooms.request(conn, title="Held", day=(d + timedelta(weeks=1)).isoformat(), slot_ids=S(conn, 9),
                         requester_user_id=st.get_admin_user(conn, "encoder@test.local")["id"])
    rooms.approve(conn, held["id"], "admin@test.local")
    before = len(rows(conn))
    r = viewer.post("/rooms/request", data=form(conn))
    assert r.status_code == 409 and "Check these dates first" in r.text and "already booked" in r.text and "Request the 3 dates that work" in r.text
    assert len(rows(conn)) == before                                                       # nothing filed yet
    ok = viewer.post("/rooms/request", data=form(conn, skip_bad="1"), follow_redirects=False)
    assert ok.status_code == 303 and "series=3" in ok.headers["location"] and len(rows(conn)) == before + 3


def test_the_approval_card_offers_the_whole_series(admin, viewer, conn):
    viewer.post("/rooms/request", data=form(conn))
    page = admin.get("/approvals").text
    assert "Repeating request:" in page and "Approve all 4" in page and "Decline all 4" in page
    rid = conn.execute("SELECT id FROM room_reservation ORDER BY day LIMIT 1").fetchone()[0]
    resp = admin.post(f"/rooms/{rid}/decide", data={"action": "approve_series", "note": "ok"}, follow_redirects=True)
    assert "Approved 4 date(s)" in resp.text
    assert {g[1] for g in rows(conn)} == {"approved"}


def test_declining_the_series_needs_a_reason(admin, viewer, conn):
    viewer.post("/rooms/request", data=form(conn))
    rid = conn.execute("SELECT id FROM room_reservation ORDER BY day LIMIT 1").fetchone()[0]
    assert "reason" in admin.post(f"/rooms/{rid}/decide", data={"action": "decline_series", "note": ""}, follow_redirects=True).text
    admin.post(f"/rooms/{rid}/decide", data={"action": "decline_series", "note": "Room is for training"})
    assert {g[1] for g in rows(conn)} == {"declined"}


def test_a_taken_date_is_reported_when_approving_the_series(admin, viewer, encoder, conn):
    viewer.post("/rooms/request", data=form(conn))
    first = conn.execute("SELECT id, day FROM room_reservation ORDER BY day").fetchall()
    held = rooms.request(conn, title="Held", day=first[2][1], slot_ids=S(conn, 9), requester_user_id=st.get_admin_user(conn, "encoder@test.local")["id"])
    rooms.approve(conn, held["id"], "admin@test.local")
    resp = admin.post(f"/rooms/{first[0][0]}/decide", data={"action": "approve_series"}, follow_redirects=True)
    assert "Approved 3 date(s)" in resp.text and "Not approved" in resp.text and first[2][1] in resp.text


def test_my_reservations_shows_the_series_and_can_withdraw_all_of_it(viewer, conn):
    viewer.post("/rooms/request", data=form(conn))
    page = viewer.get("/rooms/mine").text
    assert "Repeats: 4 dates in this request" in page and "Withdraw the whole series" in page
    rid = conn.execute("SELECT id FROM room_reservation ORDER BY day LIMIT 1").fetchone()[0]
    resp = viewer.post(f"/rooms/{rid}/withdraw-series", data={"reason": "Not needed"}, follow_redirects=True)
    assert "Withdrew 4 date(s)" in resp.text and {g[1] for g in rows(conn)} == {"withdrawn"}
    assert "nothing left" in viewer.post(f"/rooms/{rid}/withdraw-series", data={}, follow_redirects=True).text


def test_someone_else_cannot_withdraw_my_series(viewer, encoder, conn):
    viewer.post("/rooms/request", data=form(conn))
    rid = conn.execute("SELECT id FROM room_reservation ORDER BY day LIMIT 1").fetchone()[0]
    assert "your own" in encoder.post(f"/rooms/{rid}/withdraw-series", data={}, follow_redirects=True).text
    assert {g[1] for g in rows(conn)} == {"requested"}
