"""Conference room R6: the public QR page, guests' tracking link, abuse limits and retention."""
from __future__ import annotations
from datetime import date, datetime, timedelta
from urllib.parse import quote

import pytest

import auth
import rooms
import rooms_notify as rn
import storage as st
import tzutil as tz

MON = date(2030, 3, 4)
THU = date(2030, 3, 7)
GUEST = dict(name="Ana Cruz", org="Partner NGO", email="ana@ngo.org", phone="")


@pytest.fixture()
def conn(tmp_path):
    c = st.connect(str(tmp_path / "g.db")); st.init_db(c); rooms.ensure_slots(c)
    return c


def S(conn, *hours):
    by = {s["start_time"]: s["id"] for s in rooms.list_slots(conn)}
    return [by[f"{h:02d}:00"] for h in hours]


def ask(conn, day=THU, *hours, consent=True, title="Site visit", **kw):
    guest = {**GUEST, **{k: kw.pop(k) for k in list(kw) if k in GUEST}}
    return rooms.request_external(conn, title=title, day=day, slot_ids=S(conn, *(hours or (9, 10))),
                                  consent=consent, today=MON, **guest, **kw)


# ------------------------------------------------------------------ the request ---

def test_a_guest_request_is_filed_with_consent_and_a_reference(conn):
    r = ask(conn)
    assert r["status"] == "requested" and r["source"] == "external" and r["requester_user_id"] is None
    assert r["ext_consent_at"] and r["ext_email_verified_at"] is None and r["ref_code"].startswith("CR-")


@pytest.mark.parametrize("kw, msg", [
    (dict(consent=False), "tick the box"),
    (dict(name=" "), "your name"),
    (dict(email="", phone=""), "email address or a phone"),
    (dict(email="not-an-email"), "doesn't look right"),
    (dict(email="", phone="12"), "doesn't look right"),
    (dict(title=""), "title"),
])
def test_guest_form_rules(conn, kw, msg):
    with pytest.raises(rooms.RoomError, match=msg):
        ask(conn, **kw)
    assert conn.execute("SELECT COUNT(*) FROM room_reservation").fetchone()[0] == 0


def test_a_phone_alone_is_enough(conn):
    assert ask(conn, email="", phone="0917 555 1234")["ext_phone"] == "0917 555 1234"


def test_the_notice_and_horizon_rules_apply_to_guests(conn):
    assert ask(conn, MON)["day"] == MON.isoformat()
    with pytest.raises(rooms.RoomError, match="60 days"):
        ask(conn, MON + timedelta(days=77))
    ask(conn, MON + timedelta(days=58))                                   # inside 60 days is fine


def test_at_most_three_open_requests_per_email(conn):
    for h in (9, 11, 13):
        ask(conn, THU, h)
    with pytest.raises(rooms.RoomError, match="already has 3 open requests"):
        ask(conn, THU, 15, email="ANA@ngo.org")                           # case does not matter
    other = ask(conn, THU, 15, email="someone@else.org")
    assert other["id"]
    first = conn.execute("SELECT id FROM room_reservation ORDER BY id").fetchone()[0]
    rooms.withdraw(conn, first, None, guest=True)                          # withdrawing frees a place
    assert ask(conn, THU, 17)["id"]


# ------------------------------------------------------------- what a guest sees ---

def test_guests_see_free_requested_booked_and_closed_but_never_a_title(conn):
    staff = st.create_admin_user(conn, "s@test.local", "x", "y", "viewer")
    held = rooms.request(conn, title="Secret budget", day=THU, slot_ids=S(conn, 9), requester_user_id=staff, today=MON)
    rooms.approve(conn, held["id"], "admin", today=MON)
    rooms.request(conn, title="Pending thing", day=THU, slot_ids=S(conn, 11), requester_user_id=staff, today=MON)
    conn.execute("INSERT INTO room_block(day, slot_id, reason) VALUES (?,?,?)", (THU.isoformat(), S(conn, 14)[0], "Private reason"))
    conn.commit()
    d = rooms.public_day(conn, THU, MON)
    states = {h["start"]: h["state"] for h in d["hours"]}
    assert states["9 AM"] == "booked" and states["11 AM"] == "requested" and states["2 PM"] == "closed" and states["8 AM"] == "free"
    flat = str(d)
    assert "Secret budget" not in flat and "Pending thing" not in flat and "Private reason" not in flat


def test_the_day_list_starts_at_the_earliest_date_and_skips_closed_days(conn):
    st.set_holiday(conn, "2030-03-07", "Test holiday")
    days = rooms.public_days(conn, MON)
    assert days[0]["day"] == MON.isoformat() and days[0]["open"] == 12
    got = [d["day"] for d in days]
    assert "2030-03-07" not in got and "2030-03-09" not in got            # holiday and a Saturday
    assert got[-1] <= (MON + timedelta(days=60)).isoformat()


def test_a_fully_booked_day_still_lists_with_nothing_open(conn):
    staff = st.create_admin_user(conn, "s@test.local", "x", "y", "viewer")
    r = rooms.request(conn, title="All day", day=THU, slot_ids=[s["id"] for s in rooms.list_slots(conn)], requester_user_id=staff, today=MON)
    rooms.approve(conn, r["id"], "admin", today=MON)
    assert next(d for d in rooms.public_days(conn, MON) if d["day"] == "2030-03-07")["open"] == 0


# ------------------------------------------------------ guest actions by their link ---

def test_a_guest_can_withdraw_and_only_their_own_kind_of_reservation(conn):
    r = ask(conn)
    out = rooms.withdraw(conn, r["id"], None, reason="Changed plans", guest=True)
    assert out["status"] == "withdrawn"
    staff = st.create_admin_user(conn, "s@test.local", "x", "y", "viewer")
    mine = rooms.request(conn, title="Staff", day=THU, slot_ids=S(conn, 13), requester_user_id=staff, today=MON)
    with pytest.raises(rooms.RoomError, match="your own"):
        rooms.withdraw(conn, mine["id"], None, guest=True)               # a guest link can't reach a staff booking
    with pytest.raises(rooms.RoomError, match="your own"):
        rooms.take_suggestion(conn, mine["id"], None, "2030-03-08", S(conn, 13), today=MON, guest=True)


def test_a_bumped_guest_takes_a_new_time_and_keeps_their_details(conn):
    r = ask(conn, title="Site visit"); rooms.approve(conn, r["id"], "head", today=MON)
    rooms.encode(conn, by="head", title="Director", day=THU, slot_ids=S(conn, 9, 10), ext={"name": "Director"},
                 bump_reason="Director needs the room", today=MON)
    cancelled = rooms.get_reservation(conn, r["id"])
    offers = rooms.suggestions_for(conn, cancelled, today=MON)
    assert offers and all(o["day"] <= (MON + timedelta(days=60)).isoformat() for o in offers)
    new = rooms.take_suggestion(conn, r["id"], None, offers[0]["day"], offers[0]["slot_ids"], today=MON, guest=True)
    assert new["status"] == "approved" and new["source"] == "bump_accept"
    assert (new["ext_name"], new["ext_email"], new["ext_org"]) == ("Ana Cruz", "ana@ngo.org", "Partner NGO")
    assert new["requester_user_id"] is None and new["ext_consent_at"] == cancelled["ext_consent_at"]


def test_a_declined_guest_re_requests_as_an_ordinary_request(conn):
    r = ask(conn); rooms.decline(conn, r["id"], "head", "Training that day")
    o = rooms.suggestions_for(conn, rooms.get_reservation(conn, r["id"]), today=MON)[0]
    new = rooms.take_suggestion(conn, r["id"], None, o["day"], o["slot_ids"], today=MON, guest=True)
    assert new["status"] == "requested" and new["ext_email"] == "ana@ngo.org"


def test_the_email_check_is_soft(conn):
    r = ask(conn)
    assert rooms.queue(conn)[0]["email_unconfirmed"] is True
    rooms.mark_email_verified(conn, r["id"])
    assert rooms.queue(conn)[0]["email_unconfirmed"] is False
    assert rooms.queue(conn)[0]["can_approve"] is True                    # never a block either way


# ----------------------------------------------------------------- tokens, emails ---

def test_the_tracking_token_is_bound_expires_and_cannot_be_forged():
    t = auth.make_room_track_token(7)
    assert auth.verify_room_track_token(t) == 7
    assert auth.verify_room_track_token(t, now=__import__("time").time() + 151 * 24 * 3600) is None
    assert auth.verify_room_track_token(t[:-3] + "abc") is None
    assert auth.verify_room_track_token(auth.make_room_decide_token(7, 1)) is None     # wrong purpose
    assert auth.verify_room_track_token("") is None


class Mail:
    def __init__(self):
        self.sent = []

    def __call__(self, to, subject, body, html=None, attachments=None):
        self.sent.append((to, subject, body)); return {"sent": True, "detail": "ok"}


def test_a_guest_gets_a_receipt_and_every_later_email_carries_their_tracking_link(conn, monkeypatch):
    import tzutil
    now = datetime(2030, 3, 4, 9, 0)
    monkeypatch.setattr(tzutil, "now_local", lambda: now); monkeypatch.setattr(tzutil, "now_iso", lambda: now.isoformat(timespec="seconds"))
    r = ask(conn)
    rooms.approve(conn, r["id"], "head", today=MON)
    mail = Mail(); rn.flush(conn, "https://x.test", now=now, send=mail)
    got = {s[1].split(":")[0]: s for s in mail.sent if s[0] == "ana@ngo.org"}
    assert any("received" in k for k in got) and any("approved" in k for k in got)
    for _to, _subj, body in (s for s in mail.sent if s[0] == "ana@ngo.org"):
        tok = body.split("/room/t/")[1].split()[0]
        from urllib.parse import unquote
        assert auth.verify_room_track_token(unquote(tok.split("?")[0])) == r["id"]


# ----------------------------------------------------------------------- retention ---

def test_guest_details_are_blanked_after_twelve_months_but_the_booking_stays(conn):
    old = rooms.request(conn, title="Old visit", day=date(2029, 1, 10), slot_ids=S(conn, 9),
                        ext={"name": "Old Guest", "email": "old@x.org"}, today=date(2029, 1, 2))
    new = ask(conn)
    staff = st.create_admin_user(conn, "s@test.local", "x", "y", "viewer")
    mine = rooms.request(conn, title="Staff old", day=date(2029, 1, 11), slot_ids=S(conn, 9), requester_user_id=staff, today=date(2029, 1, 2))
    conn.execute("INSERT INTO room_notice(recipient, email, kind, reservation_id, created_at) VALUES ('e:old@x.org','old@x.org','approved',?,?)",
                 (old["id"], "2029-01-05T09:00:00")); conn.commit()
    assert rooms.purge_guest_details(conn, today=date(2030, 3, 4)) == 1
    got = rooms.get_reservation(conn, old["id"])
    assert (got["ext_name"], got["ext_email"], got["ext_phone"]) == (None, None, None) and got["title"] == "Old visit"
    assert rooms.get_reservation(conn, new["id"])["ext_email"] == "ana@ngo.org"           # recent: kept
    assert rooms.get_reservation(conn, mine["id"])["requester_user_id"] == staff           # staff: untouched
    assert conn.execute("SELECT COUNT(*) FROM room_notice WHERE recipient='e:old@x.org'").fetchone()[0] == 0
    assert rooms.purge_guest_details(conn, today=date(2030, 3, 4)) == 0                    # idempotent
    assert rooms.requester_label(conn, got)[0] == "Guest"


def test_the_daily_tick_runs_the_purge_once(conn):
    rooms.request(conn, title="Old", day=date(2029, 1, 10), slot_ids=S(conn, 9), ext={"name": "G", "email": "g@x.org"}, today=date(2029, 1, 2))
    now = datetime(2030, 3, 4, 9, 0)
    rn.tick(conn, "", now=now, send=Mail())
    assert conn.execute("SELECT ext_email FROM room_reservation").fetchone()[0] is None
    assert st.get_setting(conn, "room_guest_purge_on") == "2030-03-04"
