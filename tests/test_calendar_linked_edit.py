"""Editing a calendar item that is linked to a CSS activity, and the once-only
"collect feedback?" nudge (office calendar D3)."""
from __future__ import annotations
from datetime import timedelta
from urllib.parse import urlencode

import pytest

import mailer
import send_reminders as sr
import storage as st
import tzutil as tz
from test_calendar_home import world                                  # noqa: F401  (throwaway org + accounts)
from test_calendar_link import conn, entry, new_event, FORM              # noqa: F401

TODAY = tz.today_local()
DAY = (TODAY + timedelta(days=5)).isoformat()
NEW = (TODAY + timedelta(days=9)).isoformat()


@pytest.fixture()
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(mailer, "email_configured", lambda: True)
    monkeypatch.setattr(mailer, "send", lambda to, subj, body, html=None: out.append((to, subj, body)) or
                        {"sent": True, "detail": "ok"})
    return out


# ------------------------------------------------------------------ nudge ---

def past(w, title, days_ago=1, kind="training", by=None, **kw):
    """A calendar item that ended `days_ago` days ago, added before it ended."""
    day = (TODAY - timedelta(days=days_ago)).isoformat()
    eid = st.cal_create(w["conn"], title, day, kind=kind, by=(by or w["s1"]["username"]), **kw)
    w["conn"].execute("UPDATE calendar_entry SET created_at=? WHERE id=?",
                      ((TODAY - timedelta(days=days_ago + 10)).isoformat() + "T08:00:00", eid))
    w["conn"].commit()
    return eid


def test_a_past_training_is_nudged_once(world, sent):                                          # noqa: F811
    c = world["conn"]
    eid = past(world, "Basic Life Support")
    assert sr.nudge_calendar_css(c, "https://x.test") == 1
    assert len(sent) == 1 and sent[0][0] == world["s1"]["username"]
    assert f"https://x.test/calendar/entries/{eid}" in sent[0][2]
    assert st.cal_get(c, eid) and c.execute("SELECT css_nudged_at FROM calendar_entry WHERE id=?",
                                            (eid,)).fetchone()[0]
    assert sr.nudge_calendar_css(c, "https://x.test") == 0 and len(sent) == 1          # never again


def test_only_trainings_in_the_window_are_nudged(world, sent):                                  # noqa: F811
    c = world["conn"]
    for k in ("meeting", "travel", "audit_mr", "banner", "deadline"):
        past(world, f"A {k}", kind=k)
    past(world, "Too old", days_ago=6)
    past(world, "Cancelled one"); st.cal_cancel(c, st.cal_list_between(c, "2000-01-01", "2100-01-01")[-1]["id"])
    st.cal_create(c, "Today", TODAY.isoformat(), kind="training", by="x@test.local")   # not yet over
    st.cal_create(c, "Imported later", (TODAY - timedelta(days=1)).isoformat(), kind="training",
                  by=world["s1"]["username"])                                          # created after it ended
    assert sr.nudge_calendar_css(c, "https://x.test") == 0 and sent == []


def test_a_multi_day_training_is_nudged_after_its_last_day(world, sent):                       # noqa: F811
    c = world["conn"]
    eid = past(world, "Three-day workshop", days_ago=1)
    c.execute("UPDATE calendar_entry SET start_date=?, end_date=? WHERE id=?",
              ((TODAY - timedelta(days=3)).isoformat(), (TODAY - timedelta(days=1)).isoformat(), eid))
    c.commit()
    assert sr.nudge_calendar_css(c, "https://x.test") == 1


def test_an_item_that_already_became_an_activity_is_never_nudged(world, sent):                 # noqa: F811
    c = world["conn"]
    day = (TODAY - timedelta(days=1)).isoformat()
    past(world, "LIPH IS Orientation")
    new_event(c, "LIPH IS Orientation", day)                                  # exists, just not linked
    assert sr.nudge_calendar_css(c, "https://x.test") == 0 and sent == []
    assert c.execute("SELECT css_nudged_at FROM calendar_entry WHERE title='LIPH IS Orientation'"
                     ).fetchone()[0]                                          # and it won't be retried


def test_a_dry_run_sends_and_marks_nothing(world, sent, capsys):                                # noqa: F811
    c = world["conn"]
    eid = past(world, "Dry run training")
    assert sr.nudge_calendar_css(c, "https://x.test", dry_run=True) == 1
    assert sent == [] and "calendar CSS nudge" in capsys.readouterr().out
    assert c.execute("SELECT css_nudged_at FROM calendar_entry WHERE id=?", (eid,)).fetchone()[0] is None


def test_a_failed_send_is_retried_the_next_day(world, monkeypatch):                             # noqa: F811
    c = world["conn"]
    eid = past(world, "Flaky mail")
    monkeypatch.setattr(mailer, "email_configured", lambda: True)
    monkeypatch.setattr(mailer, "send", lambda *a, **k: {"sent": False, "detail": "boom"})
    sr.nudge_calendar_css(c, "https://x.test")
    assert c.execute("SELECT css_nudged_at FROM calendar_entry WHERE id=?", (eid,)).fetchone()[0] is None


def test_the_job_follows_the_admin_toggle(world, sent):                                         # noqa: F811
    c = world["conn"]
    past(world, "Switched off")
    st.set_setting(c, "email_feature.job_calendar_css_nudge", "0")
    assert not st.email_feature_enabled(c, "job_calendar_css_nudge")
    assert "calendar_css_nudge" in sr._ALL_JOBS and sr.JOB_FEATURE["calendar_css_nudge"] in mailer.FEATURES


# ------------------------------------------------------------------ pages ---

def linked(c, admin_name="admin", title="CALLK Linked", **kw):
    eid, token, _ = new_event(c, title, created_by=admin_name) if False else new_event(c, title)
    c.execute("UPDATE event SET created_by=? WHERE id=?", (admin_name, eid))
    ent = entry(c, title, people=[], note="keep me")
    st.cal_link_event(c, ent, eid)
    c.commit()
    return ent, eid, token


def post(client, ent, got, **over):
    form = {"updated_at": got["updated_at"], "title": got["title"], "kind": "training", "status": "confirmed",
            "start_date": DAY, "end_date": "", "owner_org_id": str(got["owner_org_id"] or ""),
            "audience": "bureau", "tags": "", "note": got["note"] or "", **over}
    return client.post(f"/calendar/entries/{ent}/edit", content=urlencode(form), headers=FORM,
                       follow_redirects=False)


def test_a_linked_item_shows_what_it_cannot_change(app_mod, admin, conn):
    ent, eid, token = linked(conn)
    html = admin.get(f"/calendar/entries/{ent}/edit").text
    assert "Linked to the CSS activity" in html and 'name="title" readonly' in html
    assert 'name="kind" disabled' in html and "You can move its dates below" in html


def test_locked_fields_ignore_whatever_is_posted(app_mod, admin, conn):
    ent, eid, token = linked(conn)
    got = st.cal_get(conn, ent)
    r = post(admin, ent, got, title="Hijacked", kind="meeting", venue="Elsewhere", note="new note",
             tags="PK")
    assert r.status_code == 303
    after = st.cal_get(conn, ent)
    assert after["title"] == "CALLK Linked" and after["kind"] == "training" and after["venue"] == got["venue"]
    assert after["note"] == "new note" and after["tags"] == ["PK"]                       # the rest is editable


def test_moving_the_dates_goes_through_the_activity(app_mod, admin, conn, sent):
    ent, eid, token = linked(conn)
    mark = conn.execute("SELECT COALESCE(MAX(id), 0) FROM audit_log").fetchone()[0]
    seq = st.cal_get(conn, ent)["sequence"]
    r = post(admin, ent, st.cal_get(conn, ent), start_date=NEW, end_date="")
    assert r.status_code == 303
    assert conn.execute("SELECT event_date FROM event WHERE id=?", (eid,)).fetchone()[0][:10] == NEW
    assert conn.execute("SELECT DISTINCT fi.event_date FROM form_instance fi JOIN event_form ef "
                        "ON ef.form_instance_id=fi.id WHERE ef.event_id=?", (eid,)).fetchall() == [(NEW,)]
    got = st.cal_get(conn, ent)
    assert got["start_date"] == NEW and got["sequence"] == seq + 1                       # attendees' calendars update
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE id>? AND action='event_dates_set'",
                        (mark,)).fetchone()[0] == 1
    assert sent == []                                                                   # nobody registered


def test_registrants_are_asked_before_the_dates_move(app_mod, admin, conn, sent):
    ent, eid, token = linked(conn)
    st.register_attendee(conn, eid, name="Ana Reg", email="ana@reg.test", consent_text="ok")
    st.register_attendee(conn, eid, name="No Mail", consent_text="ok")
    r = post(admin, ent, st.cal_get(conn, ent), start_date=NEW)
    assert r.status_code == 200 and "1 person registered" in r.text
    assert conn.execute("SELECT event_date FROM event WHERE id=?", (eid,)).fetchone()[0][:10] == DAY
    assert sent == []


def test_choosing_to_notify_emails_each_registrant_with_a_resume_link(app_mod, admin, conn, sent):
    ent, eid, token = linked(conn)
    st.register_attendee(conn, eid, name="Ana Reg", email="ana@reg.test", consent_text="ok")
    r = post(admin, ent, st.cal_get(conn, ent), start_date=NEW, notify="yes")
    assert r.status_code == 303
    assert [m[0] for m in sent] == ["ana@reg.test"]
    assert f"/e/{token}/resume?rt=" in sent[0][2] and "New date" in sent[0][1]
    assert conn.execute("SELECT status FROM email_log WHERE feature='event_dates_changed' "
                        "ORDER BY id DESC").fetchone()[0] == "sent"


def test_choosing_not_to_notify_moves_the_dates_quietly(app_mod, admin, conn, sent):
    ent, eid, token = linked(conn)
    st.register_attendee(conn, eid, name="Ana Reg", email="ana@reg.test", consent_text="ok")
    assert post(admin, ent, st.cal_get(conn, ent), start_date=NEW, notify="no").status_code == 303
    assert conn.execute("SELECT event_date FROM event WHERE id=?", (eid,)).fetchone()[0][:10] == NEW
    assert sent == []


def test_only_people_who_manage_the_activity_can_move_its_dates(app_mod, admin, viewer, conn):
    ent, eid, token = linked(conn)
    html = viewer.get(f"/calendar/entries/{ent}/edit").text
    assert "Only the people who manage the activity can move its dates" in html
    r = post(viewer, ent, st.cal_get(conn, ent), start_date=NEW)
    assert r.status_code == 403
    assert conn.execute("SELECT event_date FROM event WHERE id=?", (eid,)).fetchone()[0][:10] == DAY
    # but they may still change the parts that are theirs
    assert post(viewer, ent, st.cal_get(conn, ent), note="mine").status_code == 303
    assert st.cal_get(conn, ent)["note"] == "mine"


@pytest.mark.parametrize("start, end", [("2026-13-40", ""), ("", ""), (NEW, "not-a-date")])
def test_bad_dates_change_nothing(app_mod, admin, conn, start, end):
    ent, eid, token = linked(conn)
    r = post(admin, ent, st.cal_get(conn, ent), start_date=start, end_date=end)
    assert r.status_code == 400
    assert conn.execute("SELECT event_date FROM event WHERE id=?", (eid,)).fetchone()[0][:10] == DAY
    assert st.cal_get(conn, ent)["start_date"] == DAY


def test_the_reporting_cache_is_dropped_when_dates_move(app_mod, admin, conn):
    ent, eid, token = linked(conn)
    before = app_mod._atoms_state["epoch"]
    post(admin, ent, st.cal_get(conn, ent), start_date=NEW)
    assert app_mod._atoms_state["epoch"] > before


def test_a_stale_form_is_a_conflict_and_leaves_the_activity_alone(app_mod, admin, conn):
    ent, eid, token = linked(conn)
    stale = st.cal_get(conn, ent)
    st.cal_update(conn, ent, by="someone", note="changed meanwhile")
    stale["updated_at"] = "2000-01-01T00:00:00"                 # what the form was opened on
    r = post(admin, ent, stale, start_date=NEW)
    assert r.status_code == 409
    assert conn.execute("SELECT event_date FROM event WHERE id=?", (eid,)).fetchone()[0][:10] == DAY
