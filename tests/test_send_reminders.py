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


def _next_weekday(d):
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _future_weekday():
    return _next_weekday(tz.today_local() + timedelta(days=3))


def _wellness_org(conn):
    """A section with a chief + one staff member, directory-linked — enough
    for get_approvers_for to route the staffer's claim to the chief."""
    unit = conn.execute(
        "INSERT INTO org_unit(name, short_name, level, path) "
        "VALUES ('SR Wellness Section','SRW','section','TEST/SR/Wellness')").lastrowid
    chief_rp = conn.execute(
        "INSERT INTO resource_person(name, is_internal, org_unit_id, designation) "
        "VALUES ('SR Wellness Chief', 1, ?, 'Section Head')", (unit,)).lastrowid
    staff_rp = conn.execute(
        "INSERT INTO resource_person(name, is_internal, org_unit_id) "
        "VALUES ('SR Wellness Staff', 1, ?)", (unit,)).lastrowid
    chief = st.create_admin_user(conn, "sr-w-chief@test.local", "x", "y",
                                 "section_manager", rp_id=chief_rp)
    staff = st.create_admin_user(conn, "sr-w-staff@test.local", "x", "y",
                                 "viewer", rp_id=staff_rp)
    conn.commit()
    return chief, staff


def _backdate_claim(conn, claim_id, days, status=None):
    old = (tz.now_local() - timedelta(days=days)).isoformat()
    if status:
        conn.execute("UPDATE wellness_claim SET created_at=?, status=? WHERE id=?",
                    (old, status, claim_id))
    else:
        conn.execute("UPDATE wellness_claim SET created_at=? WHERE id=?", (old, claim_id))
    conn.commit()


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


# --------------------------------------------------------- wellness expiry ---

def test_reminds_approver_of_expiring_wellness_claim(tmp_path, sent):
    conn = _fresh(tmp_path)
    chief, staff = _wellness_org(conn)
    claim_id = st.create_wellness_claim(conn, staff, _future_weekday().isoformat(),
                                        "10:00", "exercise")
    _backdate_claim(conn, claim_id, days=12)   # within the 11-14 day reminder window
    n = sr.remind_wellness_expiring(conn, "https://css.example")
    assert n == 1
    assert sent[0]["to"] == "sr-w-chief@test.local"
    assert "still needs your approval" in sent[0]["subject"].lower()
    assert "action=approve" in sent[0]["body"] and "action=deny" in sent[0]["body"]


def test_does_not_remind_too_early_or_too_late(tmp_path, sent):
    conn = _fresh(tmp_path)
    chief, staff = _wellness_org(conn)
    fresh_id = st.create_wellness_claim(conn, staff, _future_weekday().isoformat(),
                                        "10:00", "exercise")
    old_id = st.create_wellness_claim(conn, staff, _future_weekday().isoformat(),
                                      "11:00", "exercise")
    _backdate_claim(conn, old_id, days=20)     # link already expired, not "about to"
    # fresh_id is left at age 0 — nowhere near expiry either.
    n = sr.remind_wellness_expiring(conn, "https://css.example")
    assert n == 0
    assert sent == []


def test_does_not_remind_a_decided_claim(tmp_path, sent):
    conn = _fresh(tmp_path)
    chief, staff = _wellness_org(conn)
    claim_id = st.create_wellness_claim(conn, staff, _future_weekday().isoformat(),
                                        "10:00", "exercise")
    _backdate_claim(conn, claim_id, days=12, status="approved")
    n = sr.remind_wellness_expiring(conn, "https://css.example")
    assert n == 0
    assert sent == []


# ------------------------------------------------------------------ digest ---

def test_digest_bundles_wellness_and_awa_for_one_approver(tmp_path, sent):
    conn = _fresh(tmp_path)
    chief, staff = _wellness_org(conn)
    st.create_wellness_claim(conn, staff, _future_weekday().isoformat(), "10:00", "exercise")
    period = st.work_arrangement_open_periods()[0]
    st.create_work_arrangement(conn, staff, period, "reg")
    n = sr.send_approvals_digest(conn, "https://css.example")
    assert n == 1
    assert sent[0]["to"] == "sr-w-chief@test.local"
    assert "pending approvals" in sent[0]["subject"].lower()
    assert "/wellness/approvals" in sent[0]["body"]
    assert "/work-arrangement/approvals" in sent[0]["body"]


def test_digest_skips_approver_with_nothing_pending(tmp_path, sent):
    conn = _fresh(tmp_path)
    _wellness_org(conn)
    n = sr.send_approvals_digest(conn, "https://css.example")
    assert n == 0
    assert sent == []


def test_digest_omits_already_decided_items(tmp_path, sent):
    conn = _fresh(tmp_path)
    chief, staff = _wellness_org(conn)
    claim_id = st.create_wellness_claim(conn, staff, _future_weekday().isoformat(),
                                        "10:00", "exercise")
    st.decide_wellness_claim(conn, claim_id, {"id": chief, "role": "section_manager"}, "approve")
    n = sr.send_approvals_digest(conn, "https://css.example")
    assert n == 0
    assert sent == []


# --------------------------------------------------------------- CSM (RP) ---

def _rp_form(conn, event_date, *, close_at=None, rp_has_account=True, answered=True):
    """An outside (Form-3-only) activity with one speaker session. Returns
    (event, form_instance_id, rp_id)."""
    rp_id = conn.execute(
        "INSERT INTO resource_person(name, is_internal, email) "
        "VALUES ('SR CSM Speaker', 1, 'sr-speaker@test.local')").lastrowid
    if rp_has_account:
        st.create_admin_user(conn, "sr-speaker@test.local", "x", "y", "viewer", rp_id=rp_id)
    conn.commit()
    f = st.create_form_instance(conn, 3, "F3", event_date, rp_id=rp_id, topic="SR Session")
    if close_at is not None:
        st.set_response_window(conn, f, None, close_at)
    ev = st.create_event(conn, "SR CSM Activity", event_date, form_instance_ids=[f],
                         created_by="sr-csm-creator@test.local", event_kind="outside")
    if answered:
        st.record_response(conn, f, [("RP1", 6)], served_by_rp_id=rp_id)
    conn.commit()
    return ev, f, rp_id


def test_emails_rp_once_window_closes(tmp_path, sent):
    conn = _fresh(tmp_path)
    past_close = (tz.now_local() - timedelta(hours=1)).isoformat(timespec="minutes")
    _ev, f, _rp = _rp_form(conn, "2026-01-05", close_at=past_close)
    n = sr.send_csm_results_to_rps(conn, "https://css.example")
    assert n == 1
    assert sent[0]["to"] == "sr-speaker@test.local"
    assert "csm results" in sent[0]["subject"].lower()
    assert "SR Session" in sent[0]["subject"]
    assert "/reports?type=3&activity=" in sent[0]["body"]
    # Idempotent: a second run doesn't re-email the same form.
    n2 = sr.send_csm_results_to_rps(conn, "https://css.example")
    assert n2 == 0
    assert len(sent) == 1


def test_emails_rp_after_delay_with_no_close_at(tmp_path, sent):
    conn = _fresh(tmp_path)
    old_date = (tz.now_local() - timedelta(days=4)).date().isoformat()
    _rp_form(conn, old_date)
    n = sr.send_csm_results_to_rps(conn, "https://css.example")
    assert n == 1


def test_no_email_before_delay_elapses(tmp_path, sent):
    conn = _fresh(tmp_path)
    recent_date = (tz.now_local() - timedelta(days=1)).date().isoformat()
    _rp_form(conn, recent_date)
    n = sr.send_csm_results_to_rps(conn, "https://css.example")
    assert n == 0
    assert sent == []


def test_no_email_without_a_response_yet(tmp_path, sent):
    conn = _fresh(tmp_path)
    old_date = (tz.now_local() - timedelta(days=4)).date().isoformat()
    _rp_form(conn, old_date, answered=False)
    n = sr.send_csm_results_to_rps(conn, "https://css.example")
    assert n == 0
    assert sent == []


def test_no_email_when_rp_has_no_login_but_retries_once_they_do(tmp_path, sent):
    conn = _fresh(tmp_path)
    old_date = (tz.now_local() - timedelta(days=4)).date().isoformat()
    ev, f, rp_id = _rp_form(conn, old_date, rp_has_account=False)
    n = sr.send_csm_results_to_rps(conn, "https://css.example")
    assert n == 0
    assert sent == []
    # The RP later gets an account -> the still-unmarked form is picked up.
    st.create_admin_user(conn, "sr-speaker@test.local", "x", "y", "viewer", rp_id=rp_id)
    conn.commit()
    n2 = sr.send_csm_results_to_rps(conn, "https://css.example")
    assert n2 == 1
    assert sent[0]["to"] == "sr-speaker@test.local"


# --------------------------------------------------------- CSM (activity) ---

def _bureau_event_for_csm(conn, event_date, *, close_at=None, answered=True,
                          created_by="sr-a-creator@test.local", lead_org_id=None):
    f = st.create_form_instance(conn, 2, "F2", event_date, topic="SR CSM Bureau",
                                lead_org_id=lead_org_id)
    if close_at is not None:
        st.set_response_window(conn, f, None, close_at)
    ev = st.create_event(conn, "SR CSM Bureau Activity", event_date, form_instance_ids=[f],
                         created_by=created_by, lead_org_id=lead_org_id)
    if answered:
        st.record_response(conn, f, [("A", 6)])
    conn.commit()
    return ev, f


def test_emails_creator_and_chief_once_window_closes(tmp_path, sent):
    conn = _fresh(tmp_path)
    st.create_admin_user(conn, "sr-a-creator@test.local", "x", "y", "section_manager")
    conn.commit()
    past_close = (tz.now_local() - timedelta(hours=1)).isoformat(timespec="minutes")
    ev, _f = _bureau_event_for_csm(conn, "2026-01-05", close_at=past_close)
    n = sr.send_csm_results_to_activity(conn, "https://css.example")
    assert n == 1
    assert sent[0]["to"] == "sr-a-creator@test.local"
    assert "csm results" in sent[0]["subject"].lower()
    assert "/reports/activities/" in sent[0]["body"]
    # Idempotent: a second run doesn't re-email the same event.
    n2 = sr.send_csm_results_to_activity(conn, "https://css.example")
    assert n2 == 0
    assert len(sent) == 1


def test_emails_creator_and_a_different_chief(tmp_path, sent):
    conn = _fresh(tmp_path)
    unit = conn.execute(
        "INSERT INTO org_unit(name, short_name, level, path) "
        "VALUES ('SR CSM Section','SRC','section','TEST/SR/Csm')").lastrowid
    chief_rp = conn.execute(
        "INSERT INTO resource_person(name, is_internal, org_unit_id, designation) "
        "VALUES ('SR CSM Chief', 1, ?, 'Section Head')", (unit,)).lastrowid
    st.create_admin_user(conn, "sr-csm-chief@test.local", "x", "y",
                         "section_manager", rp_id=chief_rp)
    st.create_admin_user(conn, "sr-a-creator@test.local", "x", "y", "section_manager")
    conn.commit()
    past_close = (tz.now_local() - timedelta(hours=1)).isoformat(timespec="minutes")
    _bureau_event_for_csm(conn, "2026-01-06", close_at=past_close, lead_org_id=unit)
    n = sr.send_csm_results_to_activity(conn, "https://css.example")
    assert n == 2
    assert {c["to"] for c in sent} == {"sr-a-creator@test.local", "sr-csm-chief@test.local"}


def test_no_csm_activity_email_before_delay_elapses(tmp_path, sent):
    conn = _fresh(tmp_path)
    st.create_admin_user(conn, "sr-a-creator@test.local", "x", "y", "section_manager")
    conn.commit()
    recent_date = (tz.now_local() - timedelta(days=1)).date().isoformat()
    _bureau_event_for_csm(conn, recent_date)
    n = sr.send_csm_results_to_activity(conn, "https://css.example")
    assert n == 0
    assert sent == []


def test_no_csm_activity_email_without_a_response(tmp_path, sent):
    conn = _fresh(tmp_path)
    st.create_admin_user(conn, "sr-a-creator@test.local", "x", "y", "section_manager")
    conn.commit()
    old_date = (tz.now_local() - timedelta(days=4)).date().isoformat()
    _bureau_event_for_csm(conn, old_date, answered=False)
    n = sr.send_csm_results_to_activity(conn, "https://css.example")
    assert n == 0
    assert sent == []
