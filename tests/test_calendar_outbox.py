"""Batched calendar change emails: one per person per burst, never the editor (office calendar G1)."""
from __future__ import annotations
from datetime import datetime, timedelta

import pytest

import mailer
import office_calendar as oc
import storage as st
import tzutil as tz
from test_calendar_home import world                                  # noqa: F401  (throwaway org + accounts)

BASE = "https://x.test"
def now():
    return tz.now_local()          # read at call time: a long suite run must not age the constants


def later():
    return now() + timedelta(minutes=11)


FAR = (tz.today_local() + timedelta(days=20)).isoformat()                # not today/tomorrow: waits
SOON = tz.today_local().isoformat()


class Mail:
    def __init__(self):
        self.sent = []

    def __call__(self, to, subj, body, html=None):
        self.sent.append((to, subj, body))
        return {"sent": True, "detail": "ok"}


@pytest.fixture()
def mail(monkeypatch):
    m = Mail()
    monkeypatch.setattr(mailer, "email_configured", lambda: True)
    return m


def add(w, title="Planning", day=FAR, people=("s1", "s1b"), by="editor@x", **kw):
    return st.cal_create(w["conn"], title, day, people=[(w[p]["id"], "attending") for p in people], by=by, **kw)


def queued(w):
    return w["conn"].execute("SELECT user_id, entry_id, kind, detail, urgent, sent_at FROM calendar_outbox ORDER BY id").fetchall()


def flush(w, mail, at=None):
    return oc.flush_outbox(w["conn"], BASE, now=at or later(), send=mail)


# --------------------------------------------------------------- enqueue ---

def test_creating_queues_a_notice_for_each_person_except_the_editor(world):                    # noqa: F811
    c = world["conn"]
    e = add(world, by=world["s1"]["username"])
    assert queued(world) == [(world["s1b"]["id"], e, "added", None, 0, None)]


def test_an_import_never_queues(world):                                                        # noqa: F811
    add(world, source="import", import_key="k1")
    assert queued(world) == []


def test_a_cancelled_or_finished_entry_queues_nothing(world):                                  # noqa: F811
    add(world, status="cancelled")
    add(world, day=(tz.today_local() - timedelta(days=3)).isoformat())
    assert queued(world) == []


def test_changes_cancel_restore_and_people_each_queue_the_right_kind(world):                   # noqa: F811
    c = world["conn"]
    e = add(world, people=("s1",))
    c.execute("DELETE FROM calendar_outbox"); c.commit()
    st.cal_update(c, e, by="editor@x", venue="Cebu", note="n")                 # material + not
    st.cal_update(c, e, by="editor@x", note="only a note")                      # not material: nothing
    assert [(q[2], q[3]) for q in queued(world)] == [("changed", "venue")]
    st.cal_update(c, e, by="editor@x", people=[(world["s1"]["id"], "attending"), (world["s3"]["id"], "attending")])
    assert [(q[0], q[2]) for q in queued(world)][-1] == (world["s3"]["id"], "added")
    st.cal_update(c, e, by="editor@x", people=[(world["s3"]["id"], "attending")])
    assert [(q[0], q[2]) for q in queued(world)][-1] == (world["s1"]["id"], "removed")
    st.cal_cancel(c, e, by="editor@x")
    assert [(q[0], q[2]) for q in queued(world)][-1] == (world["s3"]["id"], "cancelled")
    n = len(queued(world))
    st.cal_restore(c, e, by="editor@x")
    assert len(queued(world)) == n + 1 and queued(world)[-1][2] == "changed" and "status" in queued(world)[-1][3]


def test_a_notice_for_today_or_tomorrow_is_urgent(world):                                      # noqa: F811
    add(world, day=SOON); add(world)
    assert [q[4] for q in queued(world)] == [1, 1, 0, 0]


# ----------------------------------------------------------------- flush ---

def test_a_burst_of_edits_is_one_email_after_the_quiet_period(world, mail):                    # noqa: F811
    c = world["conn"]
    e = add(world, people=("s1",))
    st.cal_update(c, e, by="editor@x", venue="Cebu")
    st.cal_update(c, e, by="editor@x", start_time="09:00", end_time="10:00")
    assert flush(world, mail, at=now()) == 0 and mail.sent == []                  # still being edited
    assert flush(world, mail, at=later()) == 1
    assert len(mail.sent) == 1 and mail.sent[0][0] == world["s1"]["username"]
    to, subj, body = mail.sent[0]
    assert subj == "Added to the calendar: Planning" and "Cebu" in body          # added + changes = one 'added', fresh details
    assert all(q[5] for q in queued(world))
    assert flush(world, mail, at=later() + timedelta(hours=1)) == 0               # nothing left to send


def test_people_on_the_same_item_each_get_their_own_one(world, mail):                          # noqa: F811
    add(world)
    flush(world, mail)
    assert sorted(m[0] for m in mail.sent) == sorted([world["s1"]["username"], world["s1b"]["username"]])


def test_one_email_lists_several_items(world, mail):                                           # noqa: F811
    add(world, "A", people=("s1",)); add(world, "B", people=("s1",))
    flush(world, mail)
    assert len(mail.sent) == 1 and mail.sent[0][1] == "Calendar update: 2 items"
    assert "A" in mail.sent[0][2] and "B" in mail.sent[0][2]


def test_today_and_tomorrow_skip_the_wait(world, mail):                                        # noqa: F811
    add(world, "Today thing", day=SOON, people=("s1",))
    assert flush(world, mail, at=now()) == 1


def test_added_then_cancelled_in_one_burst_says_nothing(world, mail):                          # noqa: F811
    e = add(world, people=("s1",))
    st.cal_cancel(world["conn"], e, by="editor@x")
    assert flush(world, mail) == 0 and mail.sent == []
    assert queued(world)[0][5]                                                    # closed, not left hanging


def test_cancelling_a_known_item_says_cancelled(world, mail):                                  # noqa: F811
    c = world["conn"]
    e = add(world, people=("s1",))
    flush(world, mail); mail.sent.clear()
    st.cal_cancel(c, e, by="editor@x")
    flush(world, mail, at=later() + timedelta(minutes=30))
    assert mail.sent[0][1] == "Cancelled: Planning"


def test_a_long_edit_session_still_sends_after_the_max_wait(world, mail):                      # noqa: F811
    e = add(world, people=("s1",))
    st.cal_update(world["conn"], e, by="editor@x", venue="V")
    assert flush(world, mail, at=now() + timedelta(minutes=5)) == 0
    assert flush(world, mail, at=now() + timedelta(minutes=61)) == 1


def test_the_persons_own_switch_and_the_admin_switch_are_respected(world, mail):               # noqa: F811
    c = world["conn"]
    add(world)
    st.set_calendar_email_pref(c, world["s1"]["id"], False)
    st.set_setting(c, "email_feature.calendar_changes", "1")
    flush(world, mail)
    assert [m[0] for m in mail.sent] == [world["s1b"]["username"]]                # s1 opted out
    add(world, "Second", people=("s1b",))
    st.set_setting(c, "email_feature.calendar_changes", "0")
    mail.sent.clear()
    assert flush(world, mail) == 0 and mail.sent == []
    assert c.execute("SELECT status FROM email_log WHERE feature='calendar_changes' ORDER BY id DESC").fetchone()[0] == "skipped_off"
    assert not [q for q in queued(world) if q[5] is None]                          # closed, not retried forever


def test_inactive_people_get_nothing(world, mail):                                             # noqa: F811
    add(world, people=("s1",))
    world["conn"].execute("UPDATE admin_user SET active=0 WHERE id=?", (world["s1"]["id"],)); world["conn"].commit()
    assert flush(world, mail) == 0


def test_mail_not_configured_keeps_the_notice_then_it_expires(world, monkeypatch):             # noqa: F811
    monkeypatch.setattr(mailer, "email_configured", lambda: False)
    add(world, people=("s1",))
    fail = lambda *a, **k: {"sent": False, "detail": "no"}                         # noqa: E731
    assert flush(world, fail) == 0
    assert queued(world)[0][5] is None
    assert flush(world, fail, at=now() + timedelta(days=3)) == 0
    assert w_result(world) == "expired"


def w_result(w):
    return w["conn"].execute("SELECT result FROM calendar_outbox ORDER BY id DESC").fetchone()[0]


def test_a_failing_send_gives_up_after_three_tries(world, monkeypatch):                        # noqa: F811
    monkeypatch.setattr(mailer, "email_configured", lambda: True)
    add(world, people=("s1",))
    fail = lambda *a, **k: {"sent": False, "detail": "smtp down"}                  # noqa: E731
    for i in range(3):
        flush(world, fail, at=later() + timedelta(minutes=i))
    assert w_result(world) == "failed"


def test_the_email_links_back_and_never_carries_the_editor(world, mail):                       # noqa: F811
    e = add(world, people=("s1",), by=world["s1b"]["username"])
    flush(world, mail)
    assert f"{BASE}/calendar/entries/{e}" in mail.sent[0][2]
    assert world["s1b"]["username"] not in mail.sent[0][2]


def test_a_deleted_entry_is_dropped(world, mail):                                              # noqa: F811
    e = add(world, people=("s1",))
    world["conn"].execute("DELETE FROM calendar_entry WHERE id=?", (e,)); world["conn"].commit()
    assert flush(world, mail) == 0 and w_result(world) == "dropped"


def test_the_message_has_a_preview_and_an_admin_toggle():
    assert "calendar_changes" in mailer.FEATURES and "calendar_changes" in mailer._PREVIEWS
    subj, body, html = mailer._PREVIEWS["calendar_changes"]()
    assert "Calendar update" in subj and "<table" in html


def test_titles_are_escaped_in_the_html(world):                                                # noqa: F811
    _s, _b, html = mailer.calendar_changes_message(
        "Ana", [{"kind": "added", "title": "<b>x</b>", "when": "Tue", "where": "<i>r</i>", "what": "", "url": ""}], "https://x")
    assert "<b>x</b>" not in html and "&lt;b&gt;x&lt;/b&gt;" in html


def test_the_profile_switch(app_mod, viewer):
    from urllib.parse import urlencode
    c = st.connect(app_mod.DB); st.init_db(c)
    uid = st.get_admin_user(c, "viewer@test.local")["id"]
    base = {"avatar_kind": st.AVATAR_DEFAULT, "avatar_name": "Milo", "nickname": "", "designation": ""}
    F = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        assert "cal_email_changes" in viewer.get("/me").text and st.calendar_email_pref(c, uid)
        viewer.post("/me", content=urlencode({**base, "notify_present": "1"}), headers=F)          # box unticked
        assert not st.calendar_email_pref(c, uid)
        viewer.post("/me", content=urlencode(base), headers=F)                                      # form without the field
        assert not st.calendar_email_pref(c, uid)                                                   # untouched
        viewer.post("/me", content=urlencode({**base, "notify_present": "1", "cal_email_changes": "1"}), headers=F)
        assert st.calendar_email_pref(c, uid)
    finally:
        st.set_calendar_email_pref(c, uid, True); c.close()


def test_a_queued_notice_never_blocks_deleting_an_account(world):                              # noqa: F811
    c = world["conn"]
    add(world, people=("s1",))
    c.execute("DELETE FROM calendar_entry_person WHERE user_id=?", (world["s1"]["id"],))
    c.execute("DELETE FROM admin_user WHERE id=?", (world["s1"]["id"],))
    c.commit()
    assert flush(world, Mail()) == 0 and w_result(world) == "dropped"
