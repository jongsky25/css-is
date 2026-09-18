"""send_reminders.py — the standalone, cron-driven job that emails tomorrow's
event reminders (creator + section chief + every registrant with an email on
file). Runs directly against storage.py, same isolation style as
test_registration_dedup.py's storage-layer tests: its own throwaway DB, no
HTTP client, no live mail transport (mailer.send is monkeypatched)."""
from __future__ import annotations
from datetime import timedelta

import pytest

import mailer
import storage as st
import send_reminders as sr
import tzutil as tz


def _fresh(tmp_path):
    conn = st.connect(str(tmp_path / "reminders.db"))
    st.init_db(conn)
    return conn


@pytest.fixture()
def sent(monkeypatch):
    calls = []

    def _fake_send(to, subject, body, html=None):
        calls.append({"to": to, "subject": subject, "body": body})
        return {"sent": True, "detail": "ok"}
    monkeypatch.setattr(mailer, "send", _fake_send)
    return calls


def _tomorrow():
    return (tz.today_local() + timedelta(days=1)).isoformat()


def test_reminds_creator_and_registrant(tmp_path, sent):
    conn = _fresh(tmp_path)
    st.create_admin_user(conn, "creator@test.local", "x", "y", "section_manager")
    conn.commit()
    f = st.create_form_instance(conn, 2, "F2", _tomorrow(), topic="Reminder Forum")
    ev = st.create_event(conn, "Reminder Forum", _tomorrow(), form_instance_ids=[f],
                         created_by="creator@test.local")
    st.register_attendee(conn, ev["id"], name="Reg Person",
                         email="reg@test.local", consent_text="x")
    conn.commit()
    n = sr.remind_tomorrows_events(conn, "https://css.example")
    assert n == 2
    recipients = {c["to"] for c in sent}
    assert recipients == {"creator@test.local", "reg@test.local"}
    reg_mail = next(c for c in sent if c["to"] == "reg@test.local")
    assert "/e/" in reg_mail["body"] and "/resume?rt=" in reg_mail["body"]
    assert "tomorrow" in reg_mail["subject"].lower()


def test_creator_who_is_also_chief_gets_one_email(tmp_path, sent):
    conn = _fresh(tmp_path)
    unit = conn.execute(
        "INSERT INTO org_unit(name, short_name, level, path) "
        "VALUES ('SR Test Section','SRT','section','TEST/SR/Sect')").lastrowid
    chief_rp = conn.execute(
        "INSERT INTO resource_person(name, is_internal, org_unit_id, designation) "
        "VALUES ('SR Chief', 1, ?, 'Section Head')", (unit,)).lastrowid
    chief = st.create_admin_user(conn, "sr-chief@test.local", "x", "y",
                                 "section_manager", rp_id=chief_rp)
    conn.commit()
    f = st.create_form_instance(conn, 2, "F2", _tomorrow(), topic="Chief Forum",
                                lead_org_id=unit)
    st.create_event(conn, "Chief Forum", _tomorrow(), form_instance_ids=[f],
                    created_by="sr-chief@test.local", lead_org_id=unit)
    n = sr.remind_tomorrows_events(conn, "https://css.example")
    assert n == 1                       # creator == chief -> one email, not two
    assert sent[0]["to"] == "sr-chief@test.local"


def test_notifies_a_different_chief_separately(tmp_path, sent):
    conn = _fresh(tmp_path)
    unit = conn.execute(
        "INSERT INTO org_unit(name, short_name, level, path) "
        "VALUES ('SR Other Section','SRO','section','TEST/SR/Other')").lastrowid
    chief_rp = conn.execute(
        "INSERT INTO resource_person(name, is_internal, org_unit_id, designation) "
        "VALUES ('SR Other Chief', 1, ?, 'Section Head')", (unit,)).lastrowid
    st.create_admin_user(conn, "sr-other-chief@test.local", "x", "y",
                         "section_manager", rp_id=chief_rp)
    st.create_admin_user(conn, "sr-other-creator@test.local", "x", "y", "section_manager")
    conn.commit()
    f = st.create_form_instance(conn, 2, "F2", _tomorrow(), topic="Other Forum",
                                lead_org_id=unit)
    st.create_event(conn, "Other Forum", _tomorrow(), form_instance_ids=[f],
                    created_by="sr-other-creator@test.local", lead_org_id=unit)
    n = sr.remind_tomorrows_events(conn, "https://css.example")
    assert n == 2
    assert {c["to"] for c in sent} == {"sr-other-creator@test.local", "sr-other-chief@test.local"}


def test_does_not_remind_events_on_other_days(tmp_path, sent):
    conn = _fresh(tmp_path)
    st.create_admin_user(conn, "later@test.local", "x", "y", "section_manager")
    conn.commit()
    f = st.create_form_instance(conn, 2, "F2", "2099-01-01", topic="Far Off")
    st.create_event(conn, "Far Off", "2099-01-01", form_instance_ids=[f],
                    created_by="later@test.local")
    n = sr.remind_tomorrows_events(conn, "https://css.example")
    assert n == 0
    assert sent == []


def test_dry_run_sends_nothing(tmp_path, sent, capsys):
    conn = _fresh(tmp_path)
    st.create_admin_user(conn, "dry@test.local", "x", "y", "section_manager")
    conn.commit()
    f = st.create_form_instance(conn, 2, "F2", _tomorrow(), topic="Dry Forum")
    st.create_event(conn, "Dry Forum", _tomorrow(), form_instance_ids=[f],
                    created_by="dry@test.local")
    n = sr.remind_tomorrows_events(conn, "https://css.example", dry_run=True)
    assert n == 1
    assert sent == []
    assert "dry-run" in capsys.readouterr().out


def test_base_url_required(monkeypatch):
    monkeypatch.delenv("CSS_BASE_URL", raising=False)
    with pytest.raises(SystemExit):
        sr._base_url()


def test_run_uses_css_base_url(tmp_path, sent, monkeypatch):
    monkeypatch.setenv("CSS_BASE_URL", "https://from.env/")
    conn = st.connect(str(tmp_path / "reminders2.db"))
    st.init_db(conn)
    st.create_admin_user(conn, "envcheck@test.local", "x", "y", "section_manager")
    conn.commit()
    f = st.create_form_instance(conn, 2, "F2", _tomorrow(), topic="Env Forum")
    st.create_event(conn, "Env Forum", _tomorrow(), form_instance_ids=[f],
                    created_by="envcheck@test.local")
    conn.close()
    report = sr.run(db_path=str(tmp_path / "reminders2.db"), jobs={"events"})
    assert report == {"events": 1}
    assert sent[0]["to"] == "envcheck@test.local"
