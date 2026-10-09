"""Birthday greetings, phase 1 (docs/BIRTHDAY_GREETINGS_PLAN.md): the window rules and the email."""
from __future__ import annotations
from datetime import date

import pytest

import birthdays as bd
import mailer
import send_reminders as sr
import storage as st
import tzutil as tz
from test_birthday_reminders import BASE, bday, pretend_today, sent, world        # noqa: F401

MON, TUE, WED, THU, FRI, SAT, SUN = (date(2026, 10, d) for d in (12, 13, 14, 15, 16, 17, 18))


# ------------------------------------------------------------ window rules ---

def test_the_window_is_the_six_days_before_and_the_day_never_after():
    assert bd.greeting_phase(10, 14, date(2026, 10, 14)) == "today"
    assert bd.greeting_phase(10, 14, date(2026, 10, 8)) == "before"     # six days out: the first day
    assert bd.greeting_phase(10, 14, date(2026, 10, 13)) == "before"
    assert bd.greeting_phase(10, 14, date(2026, 10, 7)) == "none"       # seven days out: too early
    assert bd.greeting_phase(10, 14, date(2026, 10, 15)) == "none"      # the day after: no belated greeting
    assert bd.greeting_phase(10, 14, date(2026, 10, 20)) == "none"


def test_the_window_crosses_new_year_and_handles_feb_29():
    assert bd.greeting_phase(1, 2, date(2026, 12, 30)) == "before"
    assert bd.greeting_phase(1, 2, date(2027, 1, 2)) == "today"
    assert bd.greeting_phase(1, 2, date(2027, 1, 3)) == "none"
    assert bd.greeting_phase(2, 29, date(2027, 2, 28)) == "today"       # a non-leap year keeps it on Feb 28
    assert bd.greeting_phase(2, 29, date(2028, 2, 29)) == "today"


def test_the_email_date_rolls_back_to_a_working_day():
    work = lambda d: d.weekday() < 5                                    # noqa: E731
    assert bd.email_send_date(10, 14, 2026, work) == WED
    assert bd.email_send_date(10, 17, 2026, work) == FRI                # a Saturday birthday
    assert bd.email_send_date(10, 18, 2026, work) == FRI                # a Sunday birthday
    assert bd.email_send_date(10, 14, 2026, lambda d: work(d) and d != WED) == TUE      # a holiday
    assert bd.email_send_date(1, 1, 2028, work) == date(2027, 12, 31)   # Jan 1 2028 is a Saturday: lands in the year before


# --------------------------------------------------------------- the email ---

def test_the_message_is_bilingual_signed_by_blhsd_and_has_no_age_or_date():
    for v in range(len(mailer.GREETING_POOL) + 3):                       # the pick wraps
        subj, body, html = mailer.birthday_greeting_message("Mae", v, BASE)
        assert "Maligayang kaarawan" in subj and "Happy birthday" in subj and "Mae" in subj
        assert "BLHSD" in body and "BLHSD" in html
        tl, en = mailer.GREETING_POOL[v % len(mailer.GREETING_POOL)]
        assert tl in body and en in body
        for word in ("age", "turning", "years old", "taong gulang"):
            assert word not in (tl + en).lower().split() and word not in (tl + en).lower()


def test_the_html_escapes_the_name():
    _s, _b, html = mailer.birthday_greeting_message("<b>Mae</b>", 0, BASE)
    assert "<b>Mae</b>" not in html and "&lt;b&gt;Mae&lt;/b&gt;" in html


def test_it_goes_to_the_celebrant_only_on_the_day(world, monkeypatch, sent):                  # noqa: F811
    bday(world, "s1", 10, 14, "none")                                    # even "Don't share" is greeted
    bday(world, "s1b", 10, 15, "bureau")
    pretend_today(monkeypatch, TUE)
    assert sr.send_birthday_greetings(world["conn"], BASE) == 0 and sent == []
    pretend_today(monkeypatch, WED)
    assert sr.send_birthday_greetings(world["conn"], BASE) == 1
    assert [to for to, _s, _b in sent] == ["s1@test.local"]
    assert sent[0][1].endswith("(2026)")


def test_once_a_year_and_never_late(world, monkeypatch, sent):                                # noqa: F811
    bday(world, "s1", 10, 14, "none")
    pretend_today(monkeypatch, WED)
    assert sr.send_birthday_greetings(world["conn"], BASE) == 1
    assert sr.send_birthday_greetings(world["conn"], BASE) == 0          # a re-run does not double up
    pretend_today(monkeypatch, THU)
    assert sr.send_birthday_greetings(world["conn"], BASE) == 0          # and nothing goes the day after
    assert len(sent) == 1


def test_a_weekend_birthday_is_greeted_on_the_friday_before(world, monkeypatch, sent):        # noqa: F811
    bday(world, "s1", 10, 17, "none")                                    # a Saturday
    pretend_today(monkeypatch, THU)
    assert sr.send_birthday_greetings(world["conn"], BASE) == 0
    pretend_today(monkeypatch, FRI)
    assert sr.send_birthday_greetings(world["conn"], BASE) == 1
    pretend_today(monkeypatch, SAT)
    assert sr.send_birthday_greetings(world["conn"], BASE) == 0


def test_a_holiday_birthday_is_greeted_the_working_day_before(world, monkeypatch, sent):      # noqa: F811
    world["conn"].execute("INSERT INTO holiday(day, name, kind) VALUES (?,?,?)",
                          (WED.isoformat(), "Test holiday", next(iter(st.HOLIDAY_KINDS))))
    world["conn"].commit()
    bday(world, "s1", 10, 14, "none")
    pretend_today(monkeypatch, TUE)
    assert sr.send_birthday_greetings(world["conn"], BASE) == 1


def test_a_january_birthday_is_greeted_in_december(world, monkeypatch, sent):                 # noqa: F811
    bday(world, "s1", 1, 1, "none")                                      # Jan 1 2028 is a Saturday -> Fri Dec 31, 2027
    pretend_today(monkeypatch, date(2027, 12, 31))
    assert sr.send_birthday_greetings(world["conn"], BASE) == 1
    assert sent[0][1].endswith("(2028)")


def test_inactive_accounts_and_people_without_a_birthday_get_nothing(world, monkeypatch, sent):  # noqa: F811
    bday(world, "s1", 10, 14, "none")
    world["conn"].execute("UPDATE admin_user SET active=0 WHERE id=?", (world["s1"]["id"],))
    world["conn"].commit()
    pretend_today(monkeypatch, WED)
    assert sr.send_birthday_greetings(world["conn"], BASE) == 0 and sent == []


def test_dry_run_sends_nothing(world, monkeypatch, sent):                                      # noqa: F811
    bday(world, "s1", 10, 14, "none")
    pretend_today(monkeypatch, WED)
    assert sr.send_birthday_greetings(world["conn"], BASE, dry_run=True) == 1 and sent == []


def test_the_job_is_registered_with_an_admin_switch_and_a_preview():
    assert "birthday_greeting" in sr._ALL_JOBS
    key = sr.JOB_FEATURE["birthday_greeting"]
    assert key in mailer.FEATURES and key in mailer._PREVIEWS and mailer._PREVIEWS[key]()[0]


def test_the_admin_switch_stops_it(world, monkeypatch, sent):                                  # noqa: F811
    bday(world, "s1", 10, 14, "none")
    pretend_today(monkeypatch, WED)
    st.set_email_feature(world["conn"], sr.JOB_FEATURE["birthday_greeting"], False)
    path = world["conn"].execute("PRAGMA database_list").fetchone()[2]
    monkeypatch.setenv("CSS_BASE_URL", BASE)
    report = sr.run(path, jobs={"birthday_greeting"})
    assert "birthday_greeting" not in report and sent == []
