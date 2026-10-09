"""Conference room R5: notices (bell + email), escalation, summaries, reminders, decide-by-email link."""
from __future__ import annotations
import time
from datetime import date, datetime, timedelta

import pytest

import auth
import mailer
import rooms
import rooms_notify as rn
import storage as st

MON = date(2030, 3, 4)
THU = date(2030, 3, 7)
BASE = "https://x.test"
NOW = datetime(2030, 3, 4, 9, 0, 0)          # a Monday morning


class Mail:
    def __init__(self, fail=0):
        self.sent, self.fail, self.attachments = [], fail, []

    def __call__(self, to, subject, body, html=None, attachments=None):
        if self.fail:
            self.fail -= 1
            return {"sent": False, "detail": "relay down"}
        self.sent.append((to, subject, body))
        self.attachments.append(attachments)
        return {"sent": True, "detail": "ok"}


@pytest.fixture()
def w(tmp_path, monkeypatch):
    import tzutil
    monkeypatch.setattr(tzutil, "now_local", lambda: NOW)                  # the whole suite lives in March 2030
    monkeypatch.setattr(tzutil, "now_iso", lambda: NOW.isoformat(timespec="seconds"))
    conn = st.connect(str(tmp_path / "n.db")); st.init_db(conn); rooms.ensure_slots(conn)
    unit = conn.execute("INSERT INTO org_unit(name, short_name, level, path) VALUES ('Admin','ADMIN','section','BLHSD/ADMIN')").lastrowid
    other = conn.execute("INSERT INTO org_unit(name, short_name, level, path) VALUES ('Eq','EQ','section','BLHSD/EQ')").lastrowid

    def acct(name, org=None, desig=None):
        rp = conn.execute("INSERT INTO resource_person(name, is_internal, org_unit_id, designation) VALUES (?,1,?,?)",
                          (name, org, desig)).lastrowid
        return st.create_admin_user(conn, f"{name.lower()}@test.local", "x", "y", "viewer", rp_id=rp)

    return {"conn": conn, "head": acct("Head", unit, "Admin Head"), "staff": acct("Staff", unit),
            "req": acct("Req", other), "other": acct("Other", other)}


def S(conn, *hours):
    by = {s["start_time"]: s["id"] for s in rooms.list_slots(conn)}
    return [by[f"{h:02d}:00"] for h in hours]


def ask(w, who="req", day=THU, *hours, title="Planning", **kw):
    hours = hours or (9, 10)
    return rooms.request(w["conn"], title=title, day=day, slot_ids=S(w["conn"], *hours),
                         requester_user_id=w[who], today=MON, **kw)


def notices(w, kind=None):
    sql = "SELECT user_id, kind, reservation_id, bell, email_status, text FROM room_notice"
    return w["conn"].execute(sql + (" WHERE kind=?" if kind else "") + " ORDER BY id", (kind,) if kind else ()).fetchall()


def flush(w, mail, at=NOW):
    return rn.flush(w["conn"], BASE, now=at, send=mail)


# --------------------------------------------------------------- new request ---

def test_a_request_notifies_each_approver_but_not_the_requester(w):
    ask(w)
    assert sorted(n[0] for n in notices(w, "new_request")) == sorted([w["head"], w["staff"]])
    ask(w, "staff", date(2030, 3, 8), 9)                                   # an approver asking: not told about their own
    assert w["staff"] not in [n[0] for n in notices(w, "new_request") if n[2] == 2]


def test_flush_sends_once_with_decide_links_and_never_again(w):
    r = ask(w, title="Budget review")
    mail = Mail()
    assert flush(w, mail) == {"sent": 2}
    (to, subj, body), *_ = [m for m in mail.sent if m[0] == "head@test.local"]
    assert "Budget review" in subj and f"{BASE}/rooms/decide/{r['id']}?token=" in body and "action=decline" in body
    assert flush(w, mail) == {} and len(mail.sent) == 2                    # idempotent
    assert {x[0] for x in w["conn"].execute("SELECT status FROM email_log")} == {"sent"}


def test_each_decide_link_names_its_own_approver(w):
    r = ask(w)
    mail = Mail(); flush(w, mail)
    for to, _s, body in mail.sent:
        tok = body.split("token=")[1].split("&")[0].split()[0]
        from urllib.parse import unquote
        rid, uid = auth.verify_room_decide_token(unquote(tok))
        assert rid == r["id"] and st.get_admin_user_by_id(w["conn"], uid)["username"] == to


def test_switching_a_feature_off_logs_a_skip_and_sends_nothing(w):
    ask(w)
    st.set_email_feature(w["conn"], "room_new_request", False)
    mail = Mail()
    assert flush(w, mail) == {"skipped_off": 2} and mail.sent == []
    assert {x[0] for x in w["conn"].execute("SELECT status FROM email_log")} == {"skipped_off"}


def test_new_request_email_is_dropped_if_decided_before_it_goes(w):
    r = ask(w)
    rooms.approve(w["conn"], r["id"], "head@test.local", today=MON)
    mail = Mail(); flush(w, mail)
    assert not [m for m in mail.sent if "request" in m[1].lower() and "Conference room request" in m[1]]


# ---------------------------------------------------------- the requester hears ---

def test_approval_reaches_the_requester_with_a_calendar_file_and_a_bell_row(w):
    r = ask(w, title="Budget review")
    rooms.approve(w["conn"], r["id"], "head@test.local", today=MON)
    (n,) = [x for x in notices(w, "approved")]
    assert n[0] == w["req"] and n[3] == 1                                   # bell
    mail = Mail(); flush(w, mail)
    sent = [(m, a) for m, a in zip(mail.sent, mail.attachments) if m[0] == "req@test.local"]
    (m, att), = sent
    assert "approved" in m[1] and r["ref_code"] in m[2]
    name, mime, data = att[0]
    assert name == "conference-room.ics" and b"SUMMARY:Budget review" in data and b"DTSTART;TZID=" in data
    assert [b["text"] for b in rn.bell_rows(w["conn"], w["req"])] == [n[5]]


def test_you_are_not_told_about_what_you_just_did(w):
    r = ask(w, "staff")
    rooms.approve(w["conn"], r["id"], "staff@test.local", today=MON)        # a section member approving their own
    assert notices(w, "approved") == []


def test_decline_email_carries_the_reason_and_nearby_free_times(w):
    r = ask(w)
    rooms.decline(w["conn"], r["id"], "head@test.local", "Room is for training")
    mail = Mail(); flush(w, mail)
    (to, subj, body), = [m for m in mail.sent if m[0] == "req@test.local"]
    assert "declined" in subj and "Reason: Room is for training" in body and "Nearest free times" in body


def test_a_bumped_person_is_told_why_and_offered_times(w):
    r = ask(w, title="Section planning")
    rooms.approve(w["conn"], r["id"], "head@test.local", today=MON)
    rooms.encode(w["conn"], by="head@test.local", title="Director", day=THU, slot_ids=S(w["conn"], 9, 10),
                 ext={"name": "Director"}, bump_reason="Director needs the room", today=MON)
    n = [x for x in notices(w, "cancelled")]
    assert len(n) == 1 and n[0][0] == w["req"] and "Director needs the room" in n[0][5]
    mail = Mail(); flush(w, mail)
    (to, subj, body), = [m for m in mail.sent if m[0] == "req@test.local" and "cancelled" in m[1]]
    assert "Reason: Director needs the room" in body and "Nearest free times" in body


def test_closing_the_room_tells_the_people_in_the_way(w):
    r = ask(w); rooms.approve(w["conn"], r["id"], "head@test.local", today=MON)
    rooms.add_block(w["conn"], "head@test.local", THU, None, "Fumigation", confirm=True, today=MON)
    assert [n[0] for n in notices(w, "cancelled")] == [w["req"]]


def test_booking_for_someone_tells_them(w):
    rooms.encode(w["conn"], by="head@test.local", title="Visit", day=THU, slot_ids=S(w["conn"], 13),
                 requester_user_id=w["req"], today=MON)
    assert [n[0] for n in notices(w, "encoded")] == [w["req"]]


def test_a_guest_gets_email_only(w):
    r = rooms.request(w["conn"], title="Site visit", day=THU, slot_ids=S(w["conn"], 13), today=MON,
                      ext={"name": "Ana", "org": "NGO", "email": "Ana@NGO.org"})
    rooms.approve(w["conn"], r["id"], "head@test.local", today=MON)
    (n,) = notices(w, "approved")
    assert n[0] is None and n[3] == 0
    mail = Mail(); flush(w, mail)
    assert any(m[0] == "Ana@NGO.org" and "approved" in m[1] for m in mail.sent)


def test_a_guest_without_an_email_is_simply_not_emailed(w):
    r = rooms.request(w["conn"], title="Walk-in", day=THU, slot_ids=S(w["conn"], 13), today=MON,
                      ext={"name": "Ana", "phone": "0917"})
    rooms.approve(w["conn"], r["id"], "head@test.local", today=MON)
    assert notices(w, "approved") == []


# --------------------------------------------------------------- short notice ---

def test_a_late_withdrawal_alerts_the_section_but_an_early_one_does_not(w, monkeypatch):
    r = ask(w); rooms.approve(w["conn"], r["id"], "head@test.local", today=MON)
    monkeypatch.setattr(rooms.tz, "now_local", lambda: datetime(2030, 3, 6, 18, 0))     # the evening before
    out = rooms.withdraw(w["conn"], r["id"], w["req"])
    assert out["late_withdrawal"] and sorted(n[0] for n in notices(w, "withdrawn_late")) == sorted([w["head"], w["staff"]])
    assert [b["text"] for b in rn.bell_rows(w["conn"], w["head"])][0].startswith("1 conference room booking withdrawn")
    r2 = ask(w, day=date(2030, 3, 12)); rooms.approve(w["conn"], r2["id"], "head@test.local", today=MON)
    monkeypatch.setattr(rooms.tz, "now_local", lambda: datetime(2030, 3, 4, 9, 0))
    rooms.withdraw(w["conn"], r2["id"], w["req"])
    assert len(notices(w, "withdrawn_late")) == 2                                          # unchanged


# ----------------------------------------------------------------- escalation ---

def test_a_request_waiting_a_day_goes_to_the_admin_head_once(w):
    r = ask(w, day=date(2030, 3, 20))
    w["conn"].execute("UPDATE room_reservation SET created_at=? WHERE id=?", ("2030-03-03T08:00:00", r["id"])); w["conn"].commit()
    assert rn.queue_escalations(w["conn"], NOW) == 1 and rn.queue_escalations(w["conn"], NOW) == 0
    assert [n[0] for n in notices(w, "escalation")] == [w["head"]]                 # the head, not the whole section
    mail = Mail(); flush(w, mail)
    esc = [m for m in mail.sent if "still waiting" in m[1]]
    assert len(esc) == 1 and esc[0][0] == "head@test.local" and "action=approve" in esc[0][2]


def test_a_fresh_request_for_a_far_date_is_not_escalated(w):
    ask(w, day=date(2030, 3, 20))
    w["conn"].execute("UPDATE room_reservation SET created_at=?", ("2030-03-04T08:30:00",)); w["conn"].commit()
    assert rn.queue_escalations(w["conn"], NOW) == 0


def test_a_request_for_a_date_two_days_off_is_escalated_at_once(w):
    ask(w, day=date(2030, 3, 6))
    assert rn.queue_escalations(w["conn"], NOW) == 1


# -------------------------------------------------- summaries and reminders ---

def test_morning_summary_only_when_something_waits_and_once_a_day(w):
    assert rn.queue_morning_digest(w["conn"], NOW) == 0
    ask(w)
    assert rn.queue_morning_digest(w["conn"], NOW) == 2 and rn.queue_morning_digest(w["conn"], NOW) == 0
    assert rn.queue_morning_digest(w["conn"], NOW + timedelta(days=1)) == 2           # a new day, a new summary
    mail = Mail(); flush(w, mail, NOW + timedelta(days=1))
    assert any("request waiting" in m[1] for m in mail.sent)


def test_afternoon_schedule_and_reminders_cover_tomorrow_only(w):
    r = ask(w, "req", THU, 9, 10, title="Planning", attendees=8, meals_requested=True)
    rooms.approve(w["conn"], r["id"], "head@test.local", today=MON)
    other = ask(w, "other", date(2030, 3, 12), 9, title="Later"); rooms.approve(w["conn"], other["id"], "head@test.local", today=MON)
    wed = datetime(2030, 3, 6, 16, 5)
    assert rn.queue_afternoon(w["conn"], wed) == 3 and rn.queue_afternoon(w["conn"], wed) == 0
    mail = Mail(); flush(w, mail, wed)
    sched = [m for m in mail.sent if "tomorrow" in m[1].lower() and m[0] == "head@test.local"]
    assert sched and "Planning" in sched[0][2] and "8 attending, meals requested" in sched[0][2] and "Later" not in sched[0][2]
    assert any(m[0] == "req@test.local" and m[1].startswith("Reminder") for m in mail.sent)
    assert not any(m[0] == "other@test.local" and m[1].startswith("Reminder") for m in mail.sent)


def test_a_reminder_is_dropped_if_the_booking_was_withdrawn(w):
    r = ask(w); rooms.approve(w["conn"], r["id"], "head@test.local", today=MON)
    rn.queue_afternoon(w["conn"], datetime(2030, 3, 6, 16, 5))
    rooms.withdraw(w["conn"], r["id"], w["req"])
    mail = Mail(); flush(w, mail, datetime(2030, 3, 6, 16, 6))
    assert not any(m[1].startswith("Reminder") for m in mail.sent)


def test_tick_respects_the_time_of_day(w):
    r = ask(w); rooms.approve(w["conn"], r["id"], "head@test.local", today=MON)
    mail = Mail()
    rn.tick(w["conn"], BASE, now=datetime(2030, 3, 6, 7, 0), send=mail)
    assert not any(n[1] in ("digest", "tomorrow", "reminder") for n in notices(w))
    rn.tick(w["conn"], BASE, now=datetime(2030, 3, 6, 16, 0), send=mail)
    assert {"tomorrow", "reminder"} <= {n[1] for n in notices(w)}


def test_expiring_old_requests(w):
    r = ask(w)
    assert rn.expire_past_requests(w["conn"], date(2030, 3, 8)) == 1
    assert rooms.get_reservation(w["conn"], r["id"])["status"] == "expired"
    assert [n[0] for n in notices(w, "expired")] == [w["req"]]
    assert rn.expire_past_requests(w["conn"], date(2030, 3, 8)) == 0
    with pytest.raises(rooms.AlreadyDecided):
        rooms.approve(w["conn"], r["id"], "head@test.local", today=MON)


# ------------------------------------------------------------ delivery rules ---

def test_failed_sends_are_retried_later_and_given_up_after_three(w, monkeypatch):
    monkeypatch.setattr(mailer, "email_configured", lambda: True)       # so a refused send counts as 'failed'
    ask(w); w["conn"].execute("DELETE FROM room_notice WHERE user_id=?", (w["staff"],)); w["conn"].commit()
    mail = Mail(fail=99)
    assert flush(w, mail) == {"failed": 1}
    assert flush(w, mail, NOW + timedelta(minutes=1)) == {}                      # too soon
    assert flush(w, mail, NOW + timedelta(minutes=6)) == {"failed": 1}
    assert flush(w, mail, NOW + timedelta(minutes=12)) == {"failed": 1}
    assert flush(w, mail, NOW + timedelta(minutes=30)) == {}                     # three attempts: stop
    ok = Mail()
    w["conn"].execute("UPDATE room_notice SET email_status=NULL, attempts=0"); w["conn"].commit()
    assert flush(w, ok, NOW + timedelta(minutes=40)) == {"sent": 1}


def test_without_a_public_url_emails_wait(w):
    ask(w)
    assert rn.flush(w["conn"], "", now=NOW, send=Mail()) == {}
    assert w["conn"].execute("SELECT COUNT(*) FROM room_notice WHERE email_status IS NULL").fetchone()[0] == 2


def test_with_no_mail_transport_they_wait_too(w, monkeypatch):
    ask(w)
    monkeypatch.setattr(mailer, "email_configured", lambda: False)
    assert rn.flush(w["conn"], BASE, now=NOW) == {}
    assert w["conn"].execute("SELECT COUNT(*) FROM room_notice WHERE email_status IS NULL").fetchone()[0] == 2


def test_old_notices_are_not_sent_as_news(w):
    ask(w)
    w["conn"].execute("UPDATE room_notice SET created_at='2030-02-20T09:00:00'"); w["conn"].commit()
    mail = Mail()
    assert flush(w, mail) == {"skipped_none": 2} and mail.sent == []


def test_a_notice_failure_never_breaks_the_booking(w, monkeypatch):
    monkeypatch.setattr(rn, "on_requested", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    r = ask(w)
    assert rooms.get_reservation(w["conn"], r["id"])["status"] == "requested"


def test_admin_accounts_outside_the_section_are_not_approvers(tmp_path):
    conn = st.connect(str(tmp_path / "f.db")); st.init_db(conn); rooms.ensure_slots(conn)
    st.create_admin_user(conn, "boss@test.local", "x", "y", "admin")
    assert rn.approver_accounts(conn) == []


# ------------------------------------------------------------------- tokens ---

def test_decide_token_is_bound_expires_and_cannot_be_forged():
    t = auth.make_room_decide_token(5, 9)
    assert auth.verify_room_decide_token(t) == (5, 9)
    assert auth.verify_room_decide_token(t, now=time.time() + 15 * 24 * 3600) == (None, None)
    assert auth.verify_room_decide_token(t[:-3] + "abc") == (None, None)
    assert auth.verify_room_decide_token(auth.make_wellness_decide_token(5, 9)) == (None, None)    # wrong purpose
    assert auth.verify_room_decide_token("") == (None, None)


def test_every_room_email_has_a_preview():
    for k in ("room_new_request", "room_decided", "room_reminder", "room_admin_alerts", "room_digest"):
        assert k in mailer.FEATURES and mailer.sample_message(k)[0]
