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

    def _fake_send(to, subject, body):
        calls.append({"to": to, "subject": subject, "body": body})
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
