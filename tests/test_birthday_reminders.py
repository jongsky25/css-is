"""Birthday reminders (office calendar F3): the bell, the Monday line, and the optional
coordinators' day-before and monthly emails."""
from __future__ import annotations
from datetime import date, timedelta
from urllib.parse import urlencode

import pytest

import mailer
import office_calendar as oc
import send_reminders as sr
import storage as st
import tzutil as tz
from test_calendar_home import world                                  # noqa: F401  (throwaway org + accounts)

WED = date(2026, 10, 14)
BASE = "https://x.test"


def bday(w, who, month, day, share):
    st.set_birthday(w["conn"], w[who]["id"], month, day, share)


def pretend_today(monkeypatch, d):
    monkeypatch.setattr(tz, "today_local", lambda: d)


@pytest.fixture()
def sent(monkeypatch):
    out = []
    monkeypatch.setattr(mailer, "email_configured", lambda: True)
    monkeypatch.setattr(mailer, "send", lambda to, subj, body, html=None: out.append((to, subj, body)) or
                        {"sent": True, "detail": "ok"})
    return out


# -------------------------------------------------------------- the bell ---

def test_the_bell_lists_todays_celebrants_you_may_see(world):                                  # noqa: F811
    bday(world, "s1b", 10, 14, "section"); bday(world, "s3", 10, 14, "division"); bday(world, "dir", 10, 14, "bureau")
    row = oc.birthday_bell_row(world["conn"], world["s1"]["id"], WED)
    assert row["count"] == 1 and row["url"] == "/calendar/birthdays"
    assert row["text"].startswith("🎂 Today: ")
    assert len(row["text"].split(", ")) == 2                 # the section mate + the Director; not S3's division share


def test_you_are_never_reminded_about_yourself(world):                                         # noqa: F811
    bday(world, "s1", 10, 14, "bureau")
    assert oc.birthday_bell_row(world["conn"], world["s1"]["id"], WED) is None


def test_private_birthdays_and_other_days_say_nothing(world):                                  # noqa: F811
    bday(world, "s1b", 10, 14, "none"); bday(world, "dir", 10, 15, "bureau")
    assert oc.birthday_bell_row(world["conn"], world["s1"]["id"], WED) is None


def test_the_bell_switch(world):                                                               # noqa: F811
    bday(world, "dir", 10, 14, "bureau")
    st.set_bday_notify_pref(world["conn"], world["s1"]["id"], False)
    assert oc.birthday_bell_row(world["conn"], world["s1"]["id"], WED) is None
    st.set_bday_notify_pref(world["conn"], world["s1"]["id"], True)
    assert oc.birthday_bell_row(world["conn"], world["s1"]["id"], WED)


def test_feb_29_people_are_on_the_bell_on_feb_28_in_a_non_leap_year(world):                    # noqa: F811
    bday(world, "dir", 2, 29, "bureau")
    assert oc.birthday_bell_row(world["conn"], world["s1"]["id"], date(2027, 2, 28))
    assert oc.birthday_bell_row(world["conn"], world["s1"]["id"], date(2028, 2, 28)) is None
    assert oc.birthday_bell_row(world["conn"], world["s1"]["id"], date(2028, 2, 29))


def test_the_bell_rows_include_it_and_it_clears_at_midnight(world):                            # noqa: F811
    bday(world, "dir", 10, 14, "bureau")
    assert oc.bell_rows(world["conn"], world["s1"]["id"], WED)[0]["text"].startswith("🎂")
    assert oc.bell_rows(world["conn"], world["s1"]["id"], WED + timedelta(days=1)) == []


# ------------------------------------------------------- first working day ---

@pytest.mark.parametrize("year, month, want", [(2026, 10, date(2026, 10, 1)), (2026, 12, date(2026, 12, 1)),
                                                (2026, 8, date(2026, 8, 3))])
def test_first_working_day_skips_weekends(world, year, month, want):                           # noqa: F811
    assert oc.first_working_day(world["conn"], year, month) == want


def test_first_working_day_skips_a_holiday(world):                                             # noqa: F811
    c = world["conn"]
    c.execute("INSERT OR REPLACE INTO holiday(day, name, kind) VALUES ('2026-10-01', 'Suspension', 'suspension')")
    c.commit()
    assert oc.first_working_day(c, 2026, 10) == date(2026, 10, 2)


# ------------------------------------------------------------ coordinators ---

def coordinator(w, who="s1"):
    st.set_birthday_coordinators(w["conn"], [w[who]["id"]])


def test_nobody_ticked_means_no_coordinator_emails(world, sent, monkeypatch):                  # noqa: F811
    bday(world, "s1b", 10, 15, "bureau")
    pretend_today(monkeypatch, WED)
    assert sr.send_birthday_coordinators(world["conn"], BASE) == 0 and sent == []
    pretend_today(monkeypatch, date(2026, 10, 1))
    assert sr.send_birthday_month(world["conn"], BASE) == 0 and sent == []


def test_a_coordinator_hears_the_day_before_only_about_shared_birthdays(world, sent, monkeypatch):   # noqa: F811
    coordinator(world, "s1")
    bday(world, "s1b", 10, 15, "section")       # shared with the coordinator's section
    bday(world, "s3", 10, 15, "division")       # not shared with them
    bday(world, "dir", 10, 16, "bureau")        # not tomorrow
    pretend_today(monkeypatch, WED)
    assert sr.send_birthday_coordinators(world["conn"], BASE) == 1
    to, subj, body = sent[0]
    assert to == world["s1"]["username"] and subj.startswith("Tomorrow: ") and "birthdays" not in subj
    assert "Thursday, October 15" in body and body.count("•") == 1


def test_a_coordinator_is_never_told_about_their_own_birthday(world, sent, monkeypatch):        # noqa: F811
    coordinator(world, "s1")
    bday(world, "s1", 10, 15, "bureau")
    pretend_today(monkeypatch, WED)
    assert sr.send_birthday_coordinators(world["conn"], BASE) == 0


def test_the_day_before_email_is_once_per_day(world, sent, monkeypatch):                       # noqa: F811
    coordinator(world, "s1")
    bday(world, "s1b", 10, 15, "bureau")
    pretend_today(monkeypatch, WED)
    assert sr.send_birthday_coordinators(world["conn"], BASE) == 1
    assert sr.send_birthday_coordinators(world["conn"], BASE) == 0 and len(sent) == 1


def test_a_dry_run_sends_and_logs_nothing(world, sent, monkeypatch, capsys):                   # noqa: F811
    coordinator(world, "s1")
    bday(world, "s1b", 10, 15, "bureau")
    pretend_today(monkeypatch, WED)
    assert sr.send_birthday_coordinators(world["conn"], BASE, dry_run=True) == 1
    assert sent == [] and "birthday tomorrow" in capsys.readouterr().out
    assert sr.send_birthday_coordinators(world["conn"], BASE) == 1               # still owed


def test_the_monthly_list_goes_on_the_first_working_day_once(world, sent, monkeypatch):         # noqa: F811
    coordinator(world, "s1")
    bday(world, "s1b", 10, 20, "bureau"); bday(world, "dir", 10, 5, "bureau"); bday(world, "s3", 11, 2, "bureau")
    pretend_today(monkeypatch, date(2026, 10, 1))
    assert sr.send_birthday_month(world["conn"], BASE) == 1
    to, subj, body = sent[0]
    assert subj == "October 2026 celebrants" and body.index("Mon 5") < body.index("Tue 20") and "Nov" not in body
    assert f"{BASE}/calendar/birthdays?month=10" in body
    assert sr.send_birthday_month(world["conn"], BASE) == 0                       # not twice


def test_a_sleeping_app_catches_up_until_the_7th_then_gives_up(world, sent, monkeypatch):       # noqa: F811
    coordinator(world, "s1")
    bday(world, "s1b", 10, 20, "bureau")
    pretend_today(monkeypatch, date(2026, 10, 8))
    assert sr.send_birthday_month(world["conn"], BASE) == 0
    pretend_today(monkeypatch, date(2026, 10, 3))
    assert sr.send_birthday_month(world["conn"], BASE) == 1


def test_the_monthly_list_waits_for_the_first_working_day(world, sent, monkeypatch):             # noqa: F811
    coordinator(world, "s1")
    bday(world, "s1b", 8, 20, "bureau")
    pretend_today(monkeypatch, date(2026, 8, 2))                                  # a Sunday
    assert sr.send_birthday_month(world["conn"], BASE) == 0
    pretend_today(monkeypatch, date(2026, 8, 3))
    assert sr.send_birthday_month(world["conn"], BASE) == 1


def test_the_jobs_are_registered_with_admin_toggles_and_previews():
    for j in ("birthday_coordinators", "birthday_month"):
        assert j in sr._ALL_JOBS and sr.JOB_FEATURE[j] in mailer.FEATURES and sr.JOB_FEATURE[j] in mailer._PREVIEWS
        assert mailer._PREVIEWS[sr.JOB_FEATURE[j]]()[0]


# ------------------------------------------------------------- Monday line ---

def test_the_monday_email_gets_one_birthday_line_only_when_there_is_one():
    days = [("Monday, October 12", "Office")]
    _s, plain, html = mailer.whereabouts_week_message("Ana", "Oct 12-16", days, "https://x", birthdays=[("Riza", "Wed"), ("Tek", "Sat")])
    assert "Birthdays this week: Riza (Wed), Tek (Sat)" in plain and "Riza (Wed), Tek (Sat)" in html
    _s, plain, html = mailer.whereabouts_week_message("Ana", "Oct 12-16", days, "https://x")
    assert "Birthdays" not in plain and "Birthdays" not in html


def test_the_weekly_job_adds_the_line_for_each_person_by_their_own_scope(world, sent, monkeypatch):   # noqa: F811
    c = world["conn"]
    monday = st.whereabouts_week_start(tz.today_local())
    wed = monday + timedelta(days=2)
    bday(world, "s1b", wed.month, wed.day, "section"); bday(world, "dir", wed.month, wed.day, "bureau")
    monkeypatch.setattr(sr, "_whereabouts_window", lambda conn, key, offset=0: (monday, monday))
    st.set_bday_notify_pref(c, world["s3"]["id"], False)
    sr.send_whereabouts_weekly(c, BASE)
    by_to = {m[0]: m[2] for m in sent}
    assert "Birthdays this week" in by_to[world["s1"]["username"]]                # section mate + the Director
    assert by_to[world["s1"]["username"]].count("(") >= 2
    assert "Birthdays this week" not in by_to.get(world["s3"]["username"], "")      # switched off


# ----------------------------------------------------------------- admin ---

def test_only_admins_set_coordinators_and_unknown_ids_are_ignored(app_mod, admin, viewer):
    c = st.connect(app_mod.DB); st.init_db(c)
    uid = st.get_admin_user(c, "viewer@test.local")["id"]
    F = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        assert viewer.post("/admin/users/birthday-coordinators", content=urlencode([("coordinator", uid)]),
                           headers=F, follow_redirects=False).status_code in (303, 403) and uid not in {x["id"] for x in st.birthday_coordinators(c)}
        r = admin.post("/admin/users/birthday-coordinators",
                       content=urlencode([("coordinator", uid), ("coordinator", 999999), ("coordinator", "x")]),
                       headers=F, follow_redirects=False)
        assert r.status_code == 303 and [x["id"] for x in st.birthday_coordinators(c)] == [uid]
        assert "birthday-coordinators" in admin.get("/admin/users").text
        admin.post("/admin/users/birthday-coordinators", content="", headers=F)
        assert st.birthday_coordinators(c) == []
    finally:
        st.set_birthday_coordinators(c, []); c.close()


def test_the_profile_switch_for_teammates_birthdays(app_mod, viewer):
    c = st.connect(app_mod.DB); st.init_db(c)
    uid = st.get_admin_user(c, "viewer@test.local")["id"]
    base = {"avatar_kind": st.AVATAR_DEFAULT, "avatar_name": "Milo", "nickname": "", "designation": ""}
    F = {"Content-Type": "application/x-www-form-urlencoded"}
    try:
        assert "bday_notify" in viewer.get("/me").text and st.bday_notify_pref(c, uid)
        viewer.post("/me", content=urlencode({**base, "notify_present": "1"}), headers=F)
        assert not st.bday_notify_pref(c, uid)
        viewer.post("/me", content=urlencode(base), headers=F)                                      # no field: untouched
        assert not st.bday_notify_pref(c, uid)
        viewer.post("/me", content=urlencode({**base, "notify_present": "1", "bday_notify": "1", "cal_email_changes": "1"}), headers=F)
        assert st.bday_notify_pref(c, uid)
    finally:
        st.set_bday_notify_pref(c, uid, True); st.set_calendar_email_pref(c, uid, True)
        st.set_calendar_email_extras(c, uid, week=True, daybefore=True); c.close()
