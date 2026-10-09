"""The Monday week-ahead, the day-before reminder and the roll-up lines (office calendar G3)."""
from __future__ import annotations
from datetime import date, timedelta

import pytest

import mailer
import office_calendar as oc
import send_reminders as sr
import storage as st
import tzutil as tz
from test_calendar_home import world                                  # noqa: F401  (throwaway org + accounts)

BASE = "https://x.test"
MON = date(2026, 10, 12)                       # a Monday
TUE = MON + timedelta(days=1)


@pytest.fixture()
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(mailer, "email_configured", lambda: True)
    monkeypatch.setattr(mailer, "send", lambda to, subj, body, html=None: out.append((to, subj, body)) or
                        {"sent": True, "detail": "ok"})
    return out


def today(monkeypatch, d):
    monkeypatch.setattr(tz, "today_local", lambda: d)


def add(w, title, day, who=("s1",), **kw):
    kw.setdefault("audience", "bureau")
    return st.cal_create(w["conn"], title, day.isoformat(), people=[(w[p]["id"], "attending") for p in who],
                         by="editor@x", **kw)


# --------------------------------------------------------------- week ahead ---

def test_the_week_ahead_is_what_this_person_may_see(world):                                    # noqa: F811
    add(world, "Mine", MON, start_time="09:00", end_time="10:00")
    add(world, "Bureau wide", TUE, who=("s3",))
    add(world, "Someone else's", TUE, who=("s3",), audience="people")
    add(world, "Banner", MON, who=("s3",), kind="banner")
    gone = add(world, "Cancelled", MON); st.cal_cancel(world["conn"], gone)
    add(world, "Next week", MON + timedelta(days=7))
    got, more = oc.week_ahead(world["conn"], world["s1"], MON)
    assert [t for _l, t in got] == ["Mine", "Bureau wide"] and more == 0
    assert got[0][0] == "Mon 12 · 09:00" and got[1][0] == "Tue 13"


def test_a_trip_under_way_shows_its_days_this_week(world):                                     # noqa: F811
    st.cal_create(world["conn"], "Retreat", (MON - timedelta(days=2)).isoformat(),
                  end_date=(MON + timedelta(days=2)).isoformat(), audience="bureau",
                  people=[(world["s1"]["id"], "attending")], by="x@x")
    got, _more = oc.week_ahead(world["conn"], world["s1"], MON)
    assert got == [("Mon 12–Wed 14", "Retreat")]


def test_the_week_ahead_is_capped(world):                                                      # noqa: F811
    for i in range(11):
        add(world, f"Item {i:02d}", MON)
    got, more = oc.week_ahead(world["conn"], world["s1"], MON)
    assert len(got) == oc.WEEK_AHEAD_MAX and more == 3


def test_the_monday_email_carries_it_only_when_wanted(world, sent, monkeypatch):               # noqa: F811
    c = world["conn"]
    add(world, "Planning meeting", MON)
    monkeypatch.setattr(sr, "_whereabouts_window", lambda conn, key, offset=0: (MON, MON))
    st.set_calendar_email_extras(c, world["s3"]["id"], week=False)
    add(world, "For S3", MON, who=("s3",))
    sr.send_whereabouts_weekly(c, BASE)
    mine = next(m for m in sent if m[0] == world["s1"]["username"])[2]
    assert "On the calendar this week" in mine and "Planning meeting" in mine
    theirs = next(m for m in sent if m[0] == world["s3"]["username"])[2]
    assert "On the calendar this week" not in theirs


def test_the_monday_email_still_keeps_its_weekday_gate(world, sent, monkeypatch):              # noqa: F811
    add(world, "Planning meeting", MON)
    today(monkeypatch, MON + timedelta(days=2))                                                # a Wednesday
    assert sr.send_whereabouts_weekly(world["conn"], BASE) == 0 and sent == []


def test_the_message_text():
    _s, plain, html = mailer.whereabouts_week_message(
        "Ana", "Oct 12-16", [("Monday", "Office")], "https://x", events=[("Mon 12", "A <b>x</b>")], events_more=2)
    assert "On the calendar this week" in plain and "…and 2 more" in plain
    assert "A <b>x</b>" not in html and "A &lt;b&gt;x&lt;/b&gt;" in html


# ---------------------------------------------------------------- day before ---

def test_only_live_non_activity_non_banner_entries_starting_that_day(world):                   # noqa: F811
    add(world, "Tomorrow", TUE); add(world, "Maybe", TUE, status="tentative")
    add(world, "Other day", MON); add(world, "Banner", TUE, kind="banner")
    gone = add(world, "Gone", TUE); st.cal_cancel(world["conn"], gone)
    c = world["conn"]
    fid = st.create_form_instance(c, 2, "F2", TUE.isoformat(), topic="Act")
    ev = st.create_event(c, "Activity", TUE.isoformat(), form_instance_ids=[fid]); c.commit()
    add(world, "Overlay", TUE, event_id=ev["id"])
    got = oc.entries_starting_on(c, TUE)
    assert sorted(e["title"] for e in got[world["s1"]["id"]]) == ["Maybe", "Tomorrow"]


def test_one_reminder_per_person_listing_everything(world, sent, monkeypatch):                 # noqa: F811
    add(world, "Morning thing", TUE, start_time="09:00", end_time="10:00", venue="Room 5")
    add(world, "Afternoon thing", TUE, start_time="14:00")
    add(world, "Solo", TUE, who=("s3",))
    today(monkeypatch, MON)
    assert sr.send_calendar_day_before(world["conn"], BASE) == 2
    mine = next(m for m in sent if m[0] == world["s1"]["username"])
    assert mine[1].startswith("Tomorrow: 2 things on your calendar") and "Morning thing" in mine[2]
    assert "09:00–10:00" in mine[2] and "Room 5" in mine[2] and "Solo" not in mine[2]
    single = next(m for m in sent if m[0] == world["s3"]["username"])
    assert single[1].startswith("Tomorrow: Solo")


def test_the_reminder_is_once_per_day_and_dry_run_is_silent(world, sent, monkeypatch, capsys):   # noqa: F811
    add(world, "Thing", TUE)
    today(monkeypatch, MON)
    assert sr.send_calendar_day_before(world["conn"], BASE, dry_run=True) == 1
    assert sent == [] and "calendar day-before" in capsys.readouterr().out
    assert sr.send_calendar_day_before(world["conn"], BASE) == 1
    assert sr.send_calendar_day_before(world["conn"], BASE) == 0 and len(sent) == 1


def test_switched_off_or_inactive_people_get_nothing(world, sent, monkeypatch):                # noqa: F811
    c = world["conn"]
    add(world, "Thing", TUE, who=("s1", "s1b", "s3"))
    st.set_calendar_email_extras(c, world["s1"]["id"], daybefore=False)
    c.execute("UPDATE admin_user SET active=0 WHERE id=?", (world["s1b"]["id"],)); c.commit()
    today(monkeypatch, MON)
    sr.send_calendar_day_before(c, BASE)
    assert [m[0] for m in sent] == [world["s3"]["username"]]


def test_an_activity_is_never_reminded_twice(world, sent, monkeypatch):                        # noqa: F811
    c = world["conn"]
    fid = st.create_form_instance(c, 2, "F2", TUE.isoformat(), topic="Orientation")
    ev = st.create_event(c, "Orientation", TUE.isoformat(), form_instance_ids=[fid]); c.commit()
    add(world, "Orientation", TUE, event_id=ev["id"])                                          # the overlay on it
    today(monkeypatch, MON)
    assert sr.send_calendar_day_before(c, BASE) == 0 and sent == []                            # left to --events


def test_the_job_is_registered_with_a_toggle_and_a_preview():
    assert "calendar_day_before" in sr._ALL_JOBS
    f = sr.JOB_FEATURE["calendar_day_before"]
    assert f in mailer.FEATURES and f in mailer._PREVIEWS and mailer._PREVIEWS[f]()[0].startswith("Tomorrow")


# ------------------------------------------------------------------ roll-up ---

def test_the_chiefs_lines_carry_names_and_days_never_titles(world, monkeypatch):               # noqa: F811
    c = world["conn"]
    st.cal_create(c, "Secret Palawan mission", MON.isoformat(), kind="travel", audience="people",
                  people=[(world["s1"]["id"], "travel")], by="x@x")
    st.cal_create(c, "Private clinic visit", TUE.isoformat(), audience="people",
                  people=[(world["s1b"]["id"], "attending")], by="x@x")
    for u, d, s_ in ((world["s1"], MON, "office"), (world["s1b"], TUE, "leave")):
        c.execute("INSERT INTO whereabouts(user_id, day, status, note, updated_at) VALUES (?,?,?,?,?)",
                  (u["id"], d.isoformat(), s_, None, "x"))
    c.commit()
    staff = {world["s1"]["id"]: "Ana Cruz", world["s1b"]["id"]: "Ben Lim"}
    lines = sr._rollup_calendar_lines(c, staff, MON)
    assert len(lines) == 2 and lines[0].startswith("Ana Cruz — Mon 12:") and lines[1].startswith("Ben Lim — Tue 13:")
    assert "Secret" not in " ".join(lines) and "clinic" not in " ".join(lines)
    assert sr._rollup_calendar_lines(c, {world["s3"]["id"]: "Cy"}, MON) == []


def test_the_rollup_message_gains_a_section_only_when_there_is_something():
    _s, plain, html = mailer.whereabouts_rollup_message("Chief", "Oct 12-16", ["A"], 4, "https://x",
                                                        calendar_lines=["Ana — Mon 12: reported…"])
    assert "Calendar and report disagree (1)" in plain and "Ana — Mon 12" in html
    _s, plain, html = mailer.whereabouts_rollup_message("Chief", "Oct 12-16", ["A"], 4, "https://x")
    assert "disagree" not in plain and "disagree" not in html


def test_the_rollups_hand_over_who_they_cover(world, monkeypatch):                             # noqa: F811
    c = world["conn"]
    c.execute("INSERT INTO whereabouts_week(user_id, week_start, emailed_at) VALUES (?,?,?)",
              (world["s1"]["id"], MON.isoformat(), "2026-10-12T07:00:00")); c.commit()
    monkeypatch.setattr(st, "get_approvers_for", lambda conn, uid: [world["dir"]["id"]])
    got = st.whereabouts_rollups(c, MON)
    assert got[world["dir"]["id"]]["staff"] == {world["s1"]["id"]: got[world["dir"]["id"]]["missing"][0]}


def test_the_profile_switches(app_mod, viewer):
    from urllib.parse import urlencode
    c = st.connect(app_mod.DB); st.init_db(c)
    uid = st.get_admin_user(c, "viewer@test.local")["id"]
    base = {"avatar_kind": st.AVATAR_DEFAULT, "avatar_name": "Milo", "nickname": "", "designation": ""}
    F = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        html = viewer.get("/me").text
        assert "cal_email_week" in html and "cal_email_daybefore" in html
        assert st.calendar_email_extras(c, uid) == {"week": True, "daybefore": True}
        viewer.post("/me", content=urlencode({**base, "notify_present": "1", "cal_email_week": "1"}), headers=F)
        assert st.calendar_email_extras(c, uid) == {"week": True, "daybefore": False}
        viewer.post("/me", content=urlencode(base), headers=F)                       # no field: untouched
        assert st.calendar_email_extras(c, uid) == {"week": True, "daybefore": False}
    finally:
        st.set_calendar_email_extras(c, uid, week=True, daybefore=True)
        st.set_bday_notify_pref(c, uid, True); st.set_calendar_email_pref(c, uid, True); c.close()
