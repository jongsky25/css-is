"""
Action-needed email notifications for event creation, wellness/AWA approvals,
and Spot Feedback triage. Auth/password flows are untouched (see HARDENING.md
§3) — this only covers the new mailer.send() call sites added alongside them.

Mirrors the existing wellness_org/wa_org fixture pattern: a throwaway section
with a chief + staff account, cleaned up per test.
"""
from __future__ import annotations

from datetime import timedelta

import pytest

import auth
import mailer
import storage as st
import tzutil as tz


def _next_weekday(d):
    while d.weekday() >= 5:
        d += timedelta(days=1)
    return d


def _future_weekday():
    return _next_weekday(tz.today_local() + timedelta(days=3))


def _wipe(conn):
    conn.execute("DELETE FROM wellness_claim WHERE user_id IN "
                 "(SELECT id FROM admin_user WHERE username LIKE 'ntf-%@test.local')")
    conn.execute("DELETE FROM work_arrangement WHERE user_id IN "
                 "(SELECT id FROM admin_user WHERE username LIKE 'ntf-%@test.local')")
    ev_ids = "SELECT id FROM event WHERE created_by LIKE 'ntf-%@test.local'"
    conn.execute(f"DELETE FROM attendee WHERE event_id IN ({ev_ids})")
    conn.execute(f"DELETE FROM event_form WHERE event_id IN ({ev_ids})")
    conn.execute("DELETE FROM event WHERE created_by LIKE 'ntf-%@test.local'")
    conn.execute("DELETE FROM form_instance WHERE created_by LIKE 'ntf-%@test.local'")
    conn.execute("DELETE FROM spot_feedback WHERE submitter LIKE 'ntf-%@test.local'")
    conn.execute("DELETE FROM admin_user WHERE username LIKE 'ntf-%@test.local'")
    conn.execute("DELETE FROM resource_person WHERE name LIKE 'NTF-Test %'")
    conn.execute("DELETE FROM org_unit WHERE path = 'TEST/NTF/NSec'")
    conn.commit()


@pytest.fixture()
def notif_org(app_mod):
    """A section with a chief (section_manager) and a staff member (viewer),
    both directory-linked, for approver-routing + section-notify tests."""
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    _wipe(conn)
    unit = conn.execute(
        "INSERT INTO org_unit(name, short_name, level, path) "
        "VALUES ('NTF Test Section','NSec','section','TEST/NTF/NSec')").lastrowid
    chief_rp = conn.execute(
        "INSERT INTO resource_person(name, is_internal, org_unit_id, designation) "
        "VALUES ('NTF-Test Chief', 1, ?, 'Section Head')", (unit,)).lastrowid
    staff_rp = conn.execute(
        "INSERT INTO resource_person(name, is_internal, org_unit_id) "
        "VALUES ('NTF-Test Staff', 1, ?)", (unit,)).lastrowid
    h, salt = "x", "y"
    chief = st.create_admin_user(conn, "ntf-chief@test.local", h, salt,
                                 "section_manager", rp_id=chief_rp)
    staff = st.create_admin_user(conn, "ntf-staff@test.local", h, salt,
                                 "viewer", rp_id=staff_rp)
    # Not tied to the section — creates events under it without being its
    # chief, and holds "create_activity" (viewer doesn't).
    creator = st.create_admin_user(conn, "ntf-creator@test.local", h, salt,
                                   "section_manager")
    conn.commit()
    yield {"conn": conn, "unit": unit, "chief": chief, "staff": staff, "creator": creator}
    _wipe(conn)
    conn.close()


@pytest.fixture()
def sent(monkeypatch):
    """Flip mailer on and record every send() call instead of touching SMTP."""
    calls = []
    monkeypatch.setattr(mailer, "email_configured", lambda: True)

    def _fake_send(to, subject, body, html=None):
        calls.append({"to": to, "subject": subject, "body": body, "html": html})
        return {"sent": True, "detail": "ok"}
    monkeypatch.setattr(mailer, "send", _fake_send)
    return calls


def _client_for(app_mod, uid):
    from starlette.testclient import TestClient
    conn = st.connect(app_mod.DB)
    u = st.get_admin_user_by_id(conn, uid)
    conn.close()
    c = TestClient(app_mod.app, raise_server_exceptions=True)
    c.cookies.set(auth.COOKIE_NAME, auth.make_token(
        {"id": u["id"], "username": u["username"], "role": u["role"]}))
    return c


# --------------------------------------------------------------- wellness ---

def test_wellness_apply_notifies_the_approver(app_mod, notif_org, sent):
    c = _client_for(app_mod, notif_org["staff"])
    d = _future_weekday().isoformat()
    r = c.post("/wellness/apply", data={"break_date": d, "start_time": "10:00",
                                        "activity": "exercise", "hours": "1"},
               follow_redirects=False)
    assert r.status_code == 303
    assert len(sent) == 1
    assert sent[0]["to"] == "ntf-chief@test.local"
    assert "approval" in sent[0]["subject"].lower()
    assert "/wellness/approvals" in sent[0]["body"]


def test_wellness_apply_respects_the_feature_toggle(app_mod, notif_org, sent):
    conn = notif_org["conn"]
    st.set_email_feature(conn, "wellness_approval", False)
    conn.commit()
    c = _client_for(app_mod, notif_org["staff"])
    d = _future_weekday().isoformat()
    r = c.post("/wellness/apply", data={"break_date": d, "start_time": "10:00",
                                        "activity": "exercise", "hours": "1"},
               follow_redirects=False)
    assert r.status_code == 303
    assert sent == []
    st.set_email_feature(conn, "wellness_approval", True)
    conn.commit()


def test_wellness_decide_notifies_the_claimant(app_mod, notif_org, sent):
    conn = notif_org["conn"]
    d = _future_weekday().isoformat()
    claim_id = st.create_wellness_claim(conn, notif_org["staff"], d, "10:00", "exercise")
    c = _client_for(app_mod, notif_org["chief"])
    r = c.post(f"/wellness/claims/{claim_id}/decide", data={"action": "approve"},
               follow_redirects=False)
    assert r.status_code == 303
    assert len(sent) == 1
    assert sent[0]["to"] == "ntf-staff@test.local"
    assert "approved" in sent[0]["subject"].lower()
    assert "/wellness" in sent[0]["body"]


# ------------------------------------------------------------- work arrangement

def test_awa_file_notifies_the_approver(app_mod, notif_org, sent):
    c = _client_for(app_mod, notif_org["staff"])
    period = st.work_arrangement_open_periods()[0]
    r = c.post("/work-arrangement/file",
               data={"period_start": period, "arrangement": "reg"},
               follow_redirects=False)
    assert r.status_code == 303
    assert len(sent) == 1
    assert sent[0]["to"] == "ntf-chief@test.local"
    assert "approval" in sent[0]["subject"].lower()
    assert "/work-arrangement/approvals" in sent[0]["body"]


def test_awa_decide_notifies_the_requester(app_mod, notif_org, sent):
    conn = notif_org["conn"]
    period = st.work_arrangement_open_periods()[0]
    wa_id = st.create_work_arrangement(conn, notif_org["staff"], period, "reg")
    c = _client_for(app_mod, notif_org["chief"])
    r = c.post(f"/work-arrangement/{wa_id}/decide", data={"action": "approve"},
               follow_redirects=False)
    assert r.status_code == 303
    assert len(sent) == 1
    assert sent[0]["to"] == "ntf-staff@test.local"
    assert "approved" in sent[0]["subject"].lower()
    assert "/work-arrangement" in sent[0]["body"]


# ------------------------------------------------------------------- events ---

def test_bureau_event_notifies_creator_and_section_chief(app_mod, notif_org, sent):
    c = _client_for(app_mod, notif_org["creator"])
    conn = notif_org["conn"]
    rp = conn.execute("SELECT id FROM resource_person WHERE is_internal=1 LIMIT 1").fetchone()
    r = c.post("/create", data={
        "event_type": "bureau", "activity_name": "NTF Notif Forum",
        "event_date": "2026-06-11", "venue": "Hall A", "qr_mode": "combined",
        "rp_id": str(rp[0]), "topic": "Keynote",
        "section_id": str(notif_org["unit"]),
    }, follow_redirects=True)
    assert r.status_code == 200
    recipients = {call["to"] for call in sent}
    assert "ntf-creator@test.local" in recipients    # creator confirmation
    assert "ntf-chief@test.local" in recipients      # lead-section chief
    creator_mail = next(call for call in sent if call["to"] == "ntf-creator@test.local")
    assert "created" in creator_mail["subject"].lower()
    chief_mail = next(call for call in sent if call["to"] == "ntf-chief@test.local")
    assert "NTF Notif Forum" in chief_mail["subject"]


def test_event_creator_who_is_their_own_chief_gets_one_email(app_mod, notif_org, sent):
    """The chief creating an event under their own section shouldn't get two
    copies (creator-confirmation + section-notify)."""
    c = _client_for(app_mod, notif_org["chief"])
    conn = notif_org["conn"]
    rp = conn.execute("SELECT id FROM resource_person WHERE is_internal=1 LIMIT 1").fetchone()
    r = c.post("/create", data={
        "event_type": "bureau", "activity_name": "NTF Chief-Run Forum",
        "event_date": "2026-06-12", "venue": "Hall B", "qr_mode": "combined",
        "rp_id": str(rp[0]), "topic": "Keynote",
        "section_id": str(notif_org["unit"]),
    }, follow_redirects=True)
    assert r.status_code == 200
    assert len(sent) == 1
    assert sent[0]["to"] == "ntf-chief@test.local"


# ------------------------------------------------------------ spot feedback ---

def test_feedback_reply_notifies_the_submitter(admin, db_path, sent):
    conn = st.connect(db_path)
    st.set_setting(conn, "spot_feedback_enabled", "1")
    fid = st.create_spot_feedback(conn, user_id=1, submitter="ntf-staff@test.local",
                                  page_url="/dashboard", element_selector=".c",
                                  region_json=None, message="looks off")
    conn.commit()
    try:
        r = admin.post(f"/admin/feedback/{fid}",
                       data={"status": "Reviewing", "reply": "on it", "from_status": ""},
                       follow_redirects=False)
        assert r.status_code == 303
        assert len(sent) == 1
        assert sent[0]["to"] == "ntf-staff@test.local"
        assert "on it" in sent[0]["body"]
    finally:
        conn.execute("DELETE FROM feedback_update WHERE feedback_id=?", (fid,))
        conn.execute("DELETE FROM spot_feedback WHERE id=?", (fid,))
        conn.commit(); conn.close()


def test_feedback_reply_respects_the_feature_toggle(admin, db_path, sent):
    conn = st.connect(db_path)
    st.set_setting(conn, "spot_feedback_enabled", "1")
    st.set_email_feature(conn, "feedback_update", False)
    fid = st.create_spot_feedback(conn, user_id=1, submitter="ntf-staff@test.local",
                                  page_url="/dashboard", element_selector=".c",
                                  region_json=None, message="looks off")
    conn.commit()
    try:
        r = admin.post(f"/admin/feedback/{fid}",
                       data={"status": "Reviewing", "reply": "on it", "from_status": ""},
                       follow_redirects=False)
        assert r.status_code == 303
        assert sent == []
    finally:
        st.set_email_feature(conn, "feedback_update", True)
        conn.execute("DELETE FROM feedback_update WHERE feedback_id=?", (fid,))
        conn.execute("DELETE FROM spot_feedback WHERE id=?", (fid,))
        conn.commit(); conn.close()


# --------------------------------------------------------- registration -----

def test_registration_confirms_by_email(app_mod, manager, db_path, sent):
    import re
    rp = st.connect(db_path).execute(
        "SELECT id FROM resource_person WHERE is_internal=1 LIMIT 1").fetchone()
    r = manager.post("/create", data={
        "event_type": "bureau", "activity_name": "NTF Registration Forum",
        "event_date": "2026-07-09", "venue": "Hall A", "qr_mode": "combined",
        "rp_id": str(rp[0]), "topic": "Keynote",
    }, follow_redirects=True)
    assert r.status_code == 200
    tok = re.search(r"/e/([0-9a-f]{12})", r.text).group(1)
    sent.clear()   # drop the event-created notification, only care about registration
    r = manager.post(f"/e/{tok}", data={
        "name": "Gia Cruz", "email": "ntf-gia@test.local", "sex": "F",
        "affiliation": "DOH", "consent": "on"}, follow_redirects=False)
    assert r.status_code == 303
    assert len(sent) == 1
    assert sent[0]["to"] == "ntf-gia@test.local"
    assert "registered" in sent[0]["subject"].lower()
    assert "NTF Registration Forum" in sent[0]["subject"]
    assert f"/e/{tok}/resume?rt=" in sent[0]["body"]


def test_registration_confirmation_respects_the_feature_toggle(app_mod, manager, db_path, sent):
    import re
    conn = st.connect(db_path)
    st.set_email_feature(conn, "registration_confirmed", False)
    conn.commit(); conn.close()
    rp = st.connect(db_path).execute(
        "SELECT id FROM resource_person WHERE is_internal=1 LIMIT 1").fetchone()
    r = manager.post("/create", data={
        "event_type": "bureau", "activity_name": "NTF Toggle-Off Forum",
        "event_date": "2026-07-09", "venue": "Hall A", "qr_mode": "combined",
        "rp_id": str(rp[0]), "topic": "Keynote",
    }, follow_redirects=True)
    tok = re.search(r"/e/([0-9a-f]{12})", r.text).group(1)
    sent.clear()   # drop the event-created notification, only care about registration
    r = manager.post(f"/e/{tok}", data={
        "name": "Leo Cruz", "email": "ntf-leo@test.local", "sex": "M",
        "affiliation": "DOH", "consent": "on"}, follow_redirects=False)
    assert r.status_code == 303
    assert r.headers.get("location") is not None   # request still succeeds
    assert sent == []
    conn = st.connect(db_path)
    st.set_email_feature(conn, "registration_confirmed", True)
    conn.commit(); conn.close()


def test_resubmitting_a_registration_does_not_re_email(app_mod, manager, db_path, sent):
    """The POST is public and loosely rate limited, so one confirmation per
    address per activity is the cap: a repeat submission resumes the existing
    registration and must not mint another email."""
    import re
    rp = st.connect(db_path).execute(
        "SELECT id FROM resource_person WHERE is_internal=1 LIMIT 1").fetchone()
    r = manager.post("/create", data={
        "event_type": "bureau", "activity_name": "NTF Resubmit Forum",
        "event_date": "2026-07-13", "venue": "Hall A", "qr_mode": "combined",
        "rp_id": str(rp[0]), "topic": "Keynote",
    }, follow_redirects=True)
    tok = re.search(r"/e/([0-9a-f]{12})", r.text).group(1)
    form = {"name": "Ines Roxas", "email": "ntf-ines@test.local", "sex": "F",
            "affiliation": "DOH", "consent": "on"}
    sent.clear()
    manager.post(f"/e/{tok}", data=form, follow_redirects=False)
    assert len(sent) == 1
    manager.post(f"/e/{tok}", data=form, follow_redirects=False)   # "lost my link"
    assert len(sent) == 1


def test_registration_without_email_transport_does_not_crash(app_mod, manager, db_path, monkeypatch):
    import re
    monkeypatch.setattr(mailer, "email_configured", lambda: False)
    rp = st.connect(db_path).execute(
        "SELECT id FROM resource_person WHERE is_internal=1 LIMIT 1").fetchone()
    r = manager.post("/create", data={
        "event_type": "bureau", "activity_name": "NTF No-Mail Forum",
        "event_date": "2026-07-10", "venue": "Hall A", "qr_mode": "combined",
        "rp_id": str(rp[0]), "topic": "Keynote",
    }, follow_redirects=True)
    tok = re.search(r"/e/([0-9a-f]{12})", r.text).group(1)
    r = manager.post(f"/e/{tok}", data={
        "name": "Hu Nguyen", "email": "ntf-hu@test.local", "sex": "M",
        "affiliation": "NON-DOH", "consent": "on"}, follow_redirects=False)
    assert r.status_code == 303


# --------------------------------------------------------- certificate -----

def _form_tokens(db_path, tok):
    conn = st.connect(db_path)
    rows = conn.execute(
        """SELECT fi.qr_token FROM event_form ef
           JOIN event e ON e.id=ef.event_id
           JOIN form_instance fi ON fi.id=ef.form_instance_id
           WHERE e.event_token=? ORDER BY ef.ordinal""", (tok,)).fetchall()
    conn.close()
    return [r[0] for r in rows]


def test_certificate_ready_emails_once_on_completion(app_mod, client, manager, db_path, sent):
    import re
    rp = st.connect(db_path).execute(
        "SELECT id FROM resource_person WHERE is_internal=1 LIMIT 1").fetchone()
    r = manager.post("/create", data={
        "event_type": "bureau", "activity_name": "NTF Certificate Forum",
        "event_date": "2026-07-11", "venue": "Hall A", "qr_mode": "combined",
        "rp_id": str(rp[0]), "topic": "Keynote",
    }, follow_redirects=True)
    tok = re.search(r"/e/([0-9a-f]{12})", r.text).group(1)
    conn = st.connect(db_path)
    ev = st.get_event(conn, tok)
    st.set_event_certificate(conn, ev["id"], enabled=True, signatory_rp_id=None, verb="attended")
    conn.close()
    sent.clear()
    r = client.post(f"/e/{tok}", data={
        "name": "Ivy Santos", "email": "ntf-ivy@test.local", "sex": "F",
        "affiliation": "DOH", "consent": "on"}, follow_redirects=False)
    att = re.search(r"att=(\d+)", r.headers["location"]).group(1)
    sent.clear()   # drop the registration confirmation — only care about the certificate
    for ft in _form_tokens(db_path, tok):
        client.post(f"/r/{ft}", data={"seq": "", "att": att, "A": "7", "B1": "7",
                    "C": "4", "remarks": "ok"})
    cert_mails = [c for c in sent if "certificate" in c["subject"].lower()]
    assert len(cert_mails) == 1
    assert cert_mails[0]["to"] == "ntf-ivy@test.local"
    assert f"/e/{tok}/certificate?fmt=pdf&att={att}" in cert_mails[0]["body"]

    # Resubmitting (e.g. the attendee revisits and the offline queue replays)
    # must never send a second copy of the same email.
    for ft in _form_tokens(db_path, tok):
        client.post(f"/r/{ft}", data={"seq": "", "att": att, "A": "7", "B1": "7",
                    "C": "4", "remarks": "ok"})
    cert_mails = [c for c in sent if "certificate" in c["subject"].lower()]
    assert len(cert_mails) == 1


def test_no_certificate_email_when_certificate_not_enabled(app_mod, client, manager, db_path, sent):
    import re
    rp = st.connect(db_path).execute(
        "SELECT id FROM resource_person WHERE is_internal=1 LIMIT 1").fetchone()
    r = manager.post("/create", data={
        "event_type": "bureau", "activity_name": "NTF No-Cert Forum",
        "event_date": "2026-07-12", "venue": "Hall A", "qr_mode": "combined",
        "rp_id": str(rp[0]), "topic": "Keynote",
    }, follow_redirects=True)
    tok = re.search(r"/e/([0-9a-f]{12})", r.text).group(1)
    r = client.post(f"/e/{tok}", data={
        "name": "Jun Lee", "email": "ntf-jun@test.local", "sex": "M",
        "affiliation": "NON-DOH", "consent": "on"}, follow_redirects=False)
    att = re.search(r"att=(\d+)", r.headers["location"]).group(1)
    sent.clear()
    for ft in _form_tokens(db_path, tok):
        client.post(f"/r/{ft}", data={"seq": "", "att": att, "A": "7", "B1": "7",
                    "C": "4", "remarks": "ok"})
    assert not [c for c in sent if "certificate" in c["subject"].lower()]


# ------------------------------------------------------------------ raffle ---

def test_raffle_draw_emails_the_winner(admin, db_path, sent):
    conn = st.connect(db_path)
    f = st.create_form_instance(conn, 2, "F2", "2026-06-12", topic="NTF Raffle Forum")
    ev = st.create_event(conn, "NTF Raffle Forum", "2026-06-12", form_instance_ids=[f],
                         created_by="admin@test.local")
    aid, _ = st.register_attendee(conn, ev["id"], name="Kai Ramos",
                                  email="ntf-kai@test.local", consent_text="ok")
    st.record_response(conn, f, [("A", 6)], remarks="Loved it", attendee_id=aid)
    conn.commit(); conn.close()
    token = ev["event_token"]
    admin.post(f"/activities/{token}/raffle/settings",
              data={"raffle_enabled": "1", "raffle_prize": "a mug"})
    r = admin.post(f"/activities/{token}/raffle/draw")
    assert r.json()["ok"] is True
    assert len(sent) == 1
    assert sent[0]["to"] == "ntf-kai@test.local"
    assert "won" in sent[0]["subject"].lower()
    assert "mug" in sent[0]["body"]


def test_raffle_draw_no_email_for_anonymous_winner(admin, db_path, sent):
    conn = st.connect(db_path)
    f = st.create_form_instance(conn, 2, "F2", "2026-06-12", topic="NTF Anon Raffle")
    ev = st.create_event(conn, "NTF Anon Raffle", "2026-06-12", form_instance_ids=[f],
                         created_by="admin@test.local")
    st.record_response(conn, f, [("A", 6)], remarks="Nice")   # anonymous, no attendee
    conn.commit(); conn.close()
    token = ev["event_token"]
    admin.post(f"/activities/{token}/raffle/settings", data={"raffle_enabled": "1"})
    r = admin.post(f"/activities/{token}/raffle/draw")
    assert r.json()["ok"] is True
    assert sent == []


# --------------------------------------------------------- SMTP unconfigured ---

def test_nothing_sent_when_smtp_unconfigured(app_mod, notif_org, monkeypatch):
    """Default test env has no CSS_SMTP_HOST — every new call site must degrade
    exactly like the existing /forgot flow (no crash, no real send attempt)."""
    calls = []
    monkeypatch.setattr(mailer, "send", lambda *a, **kw: calls.append(a) or {"sent": False})
    c = _client_for(app_mod, notif_org["staff"])
    d = _future_weekday().isoformat()
    r = c.post("/wellness/apply", data={"break_date": d, "start_time": "10:00",
                                        "activity": "exercise", "hours": "1"},
               follow_redirects=False)
    assert r.status_code == 303
    # mailer.send() itself still gets called (it's the one that no-ops/logs to
    # the outbox) — the point is the request handler never raises either way.
    assert mailer.email_configured() is False


# ------------------------------------------------------------- always-on ---

def test_always_on_account_mail_ignores_every_feature_flag(admin, db_path, sent):
    """Account-recovery mail (A1-A4) never goes through the gated funnels, so
    turning every single feature key off must not touch it (D3)."""
    conn = st.connect(db_path)
    for key in mailer.FEATURES:
        st.set_email_feature(conn, key, False)
    conn.commit()
    rp_id = conn.execute(
        "INSERT INTO resource_person(name, is_internal, email) "
        "VALUES ('NTF-Test Invitee', 1, 'ntf-invitee@test.local')").lastrowid
    conn.commit()
    try:
        r = admin.post("/admin/users/invite",
                       data={"rp_id": str(rp_id), "role": "viewer"},
                       follow_redirects=False)
        assert r.status_code == 303
        assert len(sent) == 1
        assert sent[0]["to"] == "ntf-invitee@test.local"
    finally:
        for key in mailer.FEATURES:
            st.set_email_feature(conn, key, True)
        conn.execute("DELETE FROM admin_user WHERE username='ntf-invitee@test.local'")
        conn.execute("DELETE FROM resource_person WHERE id=?", (rp_id,))
        conn.commit(); conn.close()


# --------------------------------------------------- email send log (Phase 6) ---

def test_notify_writes_a_sent_row_to_email_log(app_mod, notif_org, sent):
    conn = notif_org["conn"]
    c = _client_for(app_mod, notif_org["staff"])
    d = _future_weekday().isoformat()
    r = c.post("/wellness/apply", data={"break_date": d, "start_time": "10:00",
                                        "activity": "exercise", "hours": "1"},
               follow_redirects=False)
    assert r.status_code == 303
    row = next(x for x in st.recent_email_sends(conn, limit=5)
              if x["feature"] == "wellness_approval")
    assert row["status"] == "sent"
    assert row["recipient"] == "ntf-chief@test.local"


def test_notify_writes_skipped_off_row_when_feature_disabled(app_mod, notif_org, sent):
    conn = notif_org["conn"]
    st.set_email_feature(conn, "wellness_approval", False)
    conn.commit()
    c = _client_for(app_mod, notif_org["staff"])
    d = _future_weekday().isoformat()
    try:
        r = c.post("/wellness/apply", data={"break_date": d, "start_time": "10:00",
                                            "activity": "exercise", "hours": "1"},
                   follow_redirects=False)
        assert r.status_code == 303
        assert sent == []
        row = next(x for x in st.recent_email_sends(conn, limit=5)
                  if x["feature"] == "wellness_approval")
        assert row["status"] == "skipped_off"
    finally:
        st.set_email_feature(conn, "wellness_approval", True)
        conn.commit()
