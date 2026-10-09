"""Conference room R5 over HTTP: the bell, marking things seen, and the decide-by-email link."""
from __future__ import annotations
import time
from urllib.parse import quote

import pytest

import auth
import rooms
import rooms_notify as rn
import storage as st
import tzutil as tz
from conftest import in_the_directory

ADMIN_UNIT = "BLHSD/ADMIN"


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


def uid(conn, name):
    return st.get_admin_user(conn, name)["id"]


def ask(conn, who="encoder@test.local", hour=9, title="Planning"):
    return rooms.request(conn, title=title, day=day(conn), slot_ids=[sid(conn, hour)], requester_user_id=uid(conn, who))


def link(rid, approver, action="approve", **kw):
    return f"/rooms/decide/{rid}?token={quote(auth.make_room_decide_token(rid, approver, **kw))}&action={action}"


# ------------------------------------------------------------------------ bell ---

def test_the_requester_sees_the_decision_in_the_bell_until_they_open_my_reservations(admin, encoder, conn):
    r = ask(conn, title="Budget review")
    admin.post(f"/rooms/{r['id']}/decide", data={"action": "approve"})
    assert "Your conference room request was approved: Budget review" in encoder.get("/rooms").text
    encoder.get("/rooms/mine")                                        # reading it clears it
    assert "Your conference room request was approved" not in encoder.get("/rooms").text


def test_several_updates_roll_up_into_one_line(admin, encoder, conn):
    for h in (9, 11):
        admin.post(f"/rooms/{ask(conn, hour=h)['id']}/decide", data={"action": "approve"})
    assert "2 updates on your conference room reservations" in encoder.get("/rooms").text


def test_declined_says_why_in_the_bell(admin, encoder, conn):
    r = ask(conn)
    admin.post(f"/rooms/{r['id']}/decide", data={"action": "decline", "note": "Training that day"})
    assert "Reason: Training that day" in encoder.get("/rooms").text


def test_the_section_sees_short_notice_withdrawals_until_it_opens_approvals(app_mod, viewer, encoder, conn, monkeypatch):
    r = ask(conn); rooms.approve(conn, r["id"], "admin@test.local")
    monkeypatch.setattr(rooms.tz, "now_local", lambda: __import__("datetime").datetime.fromisoformat(r["day"] + "T00:00:00")
                        - __import__("datetime").timedelta(hours=6))
    rooms.withdraw(conn, r["id"], uid(conn, "encoder@test.local"))
    with in_the_directory(app_mod, "viewer@test.local", path=ADMIN_UNIT):
        conn.execute("DELETE FROM room_notice"); conn.commit()
        rn.on_withdrawn(conn, rooms.get_reservation(conn, r["id"]), True)
        assert "withdrawn at short notice" in viewer.get("/rooms").text
        viewer.get("/approvals")
        assert "withdrawn at short notice" not in viewer.get("/rooms").text


# ----------------------------------------------------------- decide by email link ---

def test_the_confirm_page_opens_without_login_and_changes_nothing(client, admin, conn):
    r = ask(conn, title="Budget review")
    page = client.get(link(r["id"], uid(conn, "admin@test.local")))
    assert page.status_code == 200 and "Confirm your decision" in page.text and "Budget review" in page.text
    assert rooms.get_reservation(conn, r["id"])["status"] == "requested"        # a link scanner prefetching it is harmless


def test_confirming_approves_and_tells_the_requester(client, conn):
    r = ask(conn)
    me = uid(conn, "admin@test.local")
    resp = client.post(f"/rooms/decide/{r['id']}", data={"token": auth.make_room_decide_token(r["id"], me), "action": "approve"})
    assert resp.status_code == 200 and "Approved" in resp.text
    got = rooms.get_reservation(conn, r["id"])
    assert got["status"] == "approved" and got["decided_by"] == "admin@test.local"
    assert [n[0] for n in conn.execute("SELECT kind FROM room_notice WHERE kind='approved'")] == ["approved"]


def test_declining_by_link_needs_a_reason(client, conn):
    r = ask(conn)
    tok = auth.make_room_decide_token(r["id"], uid(conn, "admin@test.local"))
    resp = client.post(f"/rooms/decide/{r['id']}", data={"token": tok, "action": "decline", "note": ""})
    assert resp.status_code == 400 and "reason" in resp.text and "Confirm your decision" in resp.text
    assert rooms.get_reservation(conn, r["id"])["status"] == "requested"
    resp = client.post(f"/rooms/decide/{r['id']}", data={"token": tok, "action": "decline", "note": "No room"})
    assert "Declined" in resp.text and rooms.get_reservation(conn, r["id"])["status"] == "declined"


@pytest.mark.parametrize("make", ["forged", "other_reservation", "expired", "not_an_approver"])
def test_bad_links_do_nothing(client, conn, make):
    r = ask(conn); other = ask(conn, hour=13)
    me, nobody = uid(conn, "admin@test.local"), uid(conn, "encoder@test.local")
    tok = {"forged": auth.make_room_decide_token(r["id"], me)[:-4] + "beef",
           "other_reservation": auth.make_room_decide_token(other["id"], me),
           "expired": auth.make_room_decide_token(r["id"], me, issued_at=int(time.time()) - 15 * 24 * 3600),
           "not_an_approver": auth.make_room_decide_token(r["id"], nobody)}[make]
    assert client.get(f"/rooms/decide/{r['id']}?token={quote(tok)}").status_code == 400
    assert client.post(f"/rooms/decide/{r['id']}", data={"token": tok, "action": "approve"}).status_code == 400
    assert rooms.get_reservation(conn, r["id"])["status"] == "requested"


def test_a_link_for_something_already_decided_says_who_decided(client, admin, conn):
    r = ask(conn)
    admin.post(f"/rooms/{r['id']}/decide", data={"action": "approve"})
    page = client.get(link(r["id"], uid(conn, "admin@test.local")))
    assert page.status_code == 400 and "already approved" in page.text and "admin@test.local" in page.text
    resp = client.post(f"/rooms/decide/{r['id']}", data={"token": auth.make_room_decide_token(r["id"], uid(conn, "admin@test.local")),
                                                       "action": "decline", "note": "x"})
    assert resp.status_code == 400


def test_a_hand_made_action_is_ignored(client, conn):
    r = ask(conn)
    tok = auth.make_room_decide_token(r["id"], uid(conn, "admin@test.local"))
    assert client.post(f"/rooms/decide/{r['id']}", data={"token": tok, "action": "delete"}).status_code == 400
    assert rooms.get_reservation(conn, r["id"])["status"] == "requested"
