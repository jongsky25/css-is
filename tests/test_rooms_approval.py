"""Conference room approval (R3): who may decide, the Approvals inbox queue, first-to-act."""
from __future__ import annotations
import pytest

import rooms
import storage as st
import tzutil as tz
from conftest import in_the_directory

ADMIN_UNIT = "BLHSD/ADMIN"
OTHER_UNIT = "BLHSD/HSMED/Equity"

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


def uid(conn, username):
    return st.get_admin_user(conn, username)["id"]


def ask(conn, who, hour=9, *, title="Planning", extra=3, n=1):
    return rooms.request(conn, title=title, day=day(conn, extra), slot_ids=[sid(conn, hour + i) for i in range(n)],
                         requester_user_id=uid(conn, who))


# ------------------------------------------------------------------ who decides ---

def test_administrative_section_members_may_decide(app_mod, conn):
    with in_the_directory(app_mod, "viewer@test.local", path=ADMIN_UNIT):
        assert rooms.is_room_admin(conn, {"id": uid(conn, "viewer@test.local"), "role": "viewer"})


def test_other_staff_may_not(app_mod, conn):
    with in_the_directory(app_mod, "viewer@test.local", path=OTHER_UNIT):
        assert not rooms.is_room_admin(conn, {"id": uid(conn, "viewer@test.local"), "role": "viewer"})
    assert not rooms.is_room_admin(conn, {"id": uid(conn, "encoder@test.local"), "role": "encoder"})
    assert not rooms.is_room_admin(conn, None)


def test_admin_role_is_not_an_approver_outside_the_section(conn):
    assert not rooms.is_room_admin(conn, {"id": uid(conn, "encoder@test.local"), "role": "admin"})


def test_the_sections_acting_oic_may_not_decide_unless_a_member(app_mod, conn):
    with in_the_directory(app_mod, "encoder@test.local", path=ADMIN_UNIT):
        unit = conn.execute("SELECT id FROM org_unit WHERE path=?", (ADMIN_UNIT,)).fetchone()[0]
        oic = {"id": uid(conn, "viewer@test.local"), "role": "viewer"}
        st.set_section_oic(conn, unit, oic["id"])
        try:
            assert not rooms.is_room_admin(conn, oic)
        finally:
            st.clear_section_oic(conn, unit)


# ------------------------------------------------------------------- the inbox ---

def test_a_section_member_who_is_not_a_chief_can_open_approvals(app_mod, viewer, conn):
    ask(conn, "encoder@test.local", title="Budget review")
    with in_the_directory(app_mod, "viewer@test.local", path=ADMIN_UNIT):
        r = viewer.get("/approvals")
        assert r.status_code == 200
        assert "Budget review" in r.text and "Conference room" in r.text
        assert "Wellness breaks" not in r.text.split("inbox-jump")[1].split("</nav>")[0]   # no chief queues
        assert 'href="/approvals"' in viewer.get("/rooms").text                             # nav item appears


def test_everyone_else_still_gets_forbidden(viewer, conn):
    assert viewer.get("/approvals").status_code == 403
    assert viewer.post("/rooms/1/decide", data={"action": "approve"}).status_code == 403


def test_bell_counts_room_requests_for_approvers_only(app_mod, viewer, encoder, conn):
    ask(conn, "encoder@test.local")
    with in_the_directory(app_mod, "viewer@test.local", path=ADMIN_UNIT):
        assert "1 conference room request waiting on your decision" in viewer.get("/rooms").text
    assert "conference room request" not in encoder.get("/rooms").text


def test_requests_tab_shows_for_approvers(app_mod, viewer, encoder, conn):
    ask(conn, "encoder@test.local")
    with in_the_directory(app_mod, "viewer@test.local", path=ADMIN_UNIT):
        assert "/approvals#rooms" in viewer.get("/rooms").text
    assert "Requests" not in encoder.get("/rooms/mine").text.split("rm-tabs")[1].split("</nav>")[0]


# -------------------------------------------------------------------- deciding ---

def test_approve_from_the_inbox(app_mod, viewer, conn):
    r = ask(conn, "encoder@test.local", title="Budget review")
    with in_the_directory(app_mod, "viewer@test.local", path=ADMIN_UNIT):
        resp = viewer.post(f"/rooms/{r['id']}/decide", data={"action": "approve", "note": "ok"},
                           follow_redirects=False)
        assert resp.status_code == 303 and resp.headers["location"].startswith("/approvals?ok=")
        assert "Approved" in viewer.get(resp.headers["location"]).text
    got = rooms.get_reservation(conn, r["id"])
    assert got["status"] == "approved" and got["decided_by"] == "viewer@test.local"


def test_decline_needs_a_reason(app_mod, viewer, conn):
    r = ask(conn, "encoder@test.local")
    with in_the_directory(app_mod, "viewer@test.local", path=ADMIN_UNIT):
        resp = viewer.post(f"/rooms/{r['id']}/decide", data={"action": "decline", "note": ""}, follow_redirects=True)
        assert "reason" in resp.text and rooms.get_reservation(conn, r["id"])["status"] == "requested"
        viewer.post(f"/rooms/{r['id']}/decide", data={"action": "decline", "note": "Training that day"})
    assert rooms.get_reservation(conn, r["id"])["status"] == "declined"


def test_second_approver_is_told_who_got_there_first(app_mod, viewer, admin, conn):
    r = ask(conn, "encoder@test.local")
    admin.post(f"/rooms/{r['id']}/decide", data={"action": "approve"})
    with in_the_directory(app_mod, "viewer@test.local", path=ADMIN_UNIT):
        resp = viewer.post(f"/rooms/{r['id']}/decide", data={"action": "approve"}, follow_redirects=True)
    assert "Already approved by admin@test.local" in resp.text


def test_unknown_action_changes_nothing(admin, conn):
    r = ask(conn, "encoder@test.local")
    resp = admin.post(f"/rooms/{r['id']}/decide", data={"action": "shrug"}, follow_redirects=True)
    assert "Choose Approve or Decline" in resp.text
    assert rooms.get_reservation(conn, r["id"])["status"] == "requested"


# ----------------------------------------------------------------- the queue card ---

def test_queue_shows_competing_requests_then_withholds_approve_once_booked(admin, conn):
    a = ask(conn, "encoder@test.local", 9, title="Alpha", n=2)
    b = ask(conn, "viewer@test.local", 10, title="Bravo", n=2)
    page = admin.get("/approvals").text
    assert "1 competing" in page and "Alpha" in page and "Bravo" in page
    admin.post(f"/rooms/{a['id']}/decide", data={"action": "approve"})
    page = admin.get("/approvals").text
    assert "Already booked" in page and rooms.get_reservation(conn, b["id"])["status"] == "requested"
    q = {x["id"]: x for x in rooms.queue(conn)}
    assert q[b["id"]]["can_approve"] is False and q[b["id"]]["held_by"]["ref"] == a["ref_code"]


def test_external_requests_are_labelled_as_guests(admin, conn):
    rooms.request(conn, title="Site visit", day=day(conn), slot_ids=[sid(conn, 13)],
                  ext={"name": "Ana Cruz", "org": "Partner NGO", "email": "ana@ngo.org"})
    page = admin.get("/approvals").text
    assert "Ana Cruz" in page and "Guest" in page and "Partner NGO" in page


def test_hours_blocked_after_the_request_cannot_be_approved(conn):
    r = ask(conn, "encoder@test.local", 14)
    conn.execute("INSERT INTO room_block(day, slot_id, reason) VALUES (?,NULL,?)", (r["day"], "Fumigation")); conn.commit()
    assert rooms.queue(conn)[0]["can_approve"] is False
    with pytest.raises(rooms.SlotTaken, match="Fumigation"):
        rooms.approve(conn, r["id"], "admin")


# ------------------------------------------------- standby (provisional) requests ---

def test_a_standby_card_offers_confirm_and_the_route_releases_the_held_booking(admin, conn):
    held = ask(conn, "encoder@test.local", 9, title="Holder")
    admin.post(f"/rooms/{held['id']}/decide", data={"action": "approve"})
    sb = rooms.request(conn, title="Urgent briefing", day=held["day"], slot_ids=[sid(conn, 9)],
                       requester_user_id=uid(conn, "viewer@test.local"), standby=True)
    page = admin.get("/approvals").text
    assert "Standby · provisional" in page and "Confirm standby" in page
    # a reason is required, and nothing changes without one
    resp = admin.post(f"/rooms/{sb['id']}/decide", data={"action": "confirm_standby", "note": ""}, follow_redirects=True)
    assert "reason" in resp.text and rooms.get_reservation(conn, sb["id"])["status"] == "requested"
    resp = admin.post(f"/rooms/{sb['id']}/decide", data={"action": "confirm_standby", "note": "Emergency briefing"},
                      follow_redirects=True)
    assert "Confirmed" in resp.text
    assert rooms.get_reservation(conn, sb["id"])["status"] == "approved"
    assert rooms.get_reservation(conn, held["id"])["status"] == "cancelled"


def test_standby_is_refused_when_the_hours_are_closed_and_a_plain_request_still_is(conn):
    r = rooms.request(conn, title="x", day=day(conn), slot_ids=[sid(conn, 14)], requester_user_id=uid(conn, "encoder@test.local"))
    conn.execute("INSERT INTO room_block(day, slot_id, reason) VALUES (?,NULL,?)", (r["day"], "Fumigation")); conn.commit()
    with pytest.raises(rooms.SlotTaken):
        rooms.request(conn, title="y", day=r["day"], slot_ids=[sid(conn, 14)], requester_user_id=uid(conn, "viewer@test.local"))
    sb = rooms.request(conn, title="y", day=r["day"], slot_ids=[sid(conn, 14)], requester_user_id=uid(conn, "viewer@test.local"), standby=True)
    with pytest.raises(rooms.SlotTaken, match="Fumigation"):
        rooms.confirm_standby(conn, sb["id"], "admin", "Emergency")


def test_the_request_form_and_route_accept_a_standby_tick(admin, encoder, conn):
    held = ask(conn, "viewer@test.local", 10, title="Holder")
    admin.post(f"/rooms/{held['id']}/decide", data={"action": "approve"})
    assert "provisional (standby)" in encoder.get("/rooms").text
    form = {"day": held["day"], "from_slot": sid(conn, 10), "to_slot": sid(conn, 11), "title": "Urgent", "modality": "f2f"}
    assert encoder.post("/rooms/request", data=form).status_code in (200, 400, 409) and \
        not any(r["title"] == "Urgent" for r in rooms.list_pending(conn))      # without the tick it's refused
    encoder.post("/rooms/request", data={**form, "standby": "1"})
    got = [r for r in rooms.list_pending(conn) if r["title"] == "Urgent"]
    assert got and got[0]["standby"] == 1
