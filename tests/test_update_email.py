"""Emailing registrants when a pinned update is posted ("Also email registrants").

Rules under test: opt-in per post; only registrants with an email on file get it
(everyone else is skipped silently); one blast per activity per cooldown; a daily
cap across activities; the admin switch and the "email not configured" case; only
the activity's manager can trigger it; the text is escaped.
"""
from __future__ import annotations
import tzutil as _test_tz
import re
from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

import email_params
import mailer
import storage as st
from starlette.testclient import TestClient

_FUTURE = (_test_tz.today_local() + timedelta(days=60)).isoformat()


def _event(manager, db_path):
    conn = st.connect(db_path)
    rp = conn.execute("SELECT id FROM resource_person WHERE is_internal=1 LIMIT 1").fetchone()
    count = conn.execute("SELECT COUNT(*) FROM event").fetchone()[0]
    # Distinct dates represent distinct activities; duplicate protection stays active.
    from datetime import date, timedelta
    event_day = (date.fromisoformat(_FUTURE) + timedelta(days=count)).isoformat()
    conn.close()
    r = manager.post("/create", data={
        "event_type": "bureau", "activity_name": "Update Mail Forum",
        "event_date": event_day, "venue": "Hall A", "qr_mode": "combined",
        "rp_id": str(rp[0]), "topic": "Keynote",
    }, follow_redirects=True)
    assert r.status_code == 200
    return re.search(r"/e/([0-9a-f]{12})", r.text).group(1)


def _register(app_mod, tok, email, name="Reg Istrant"):
    c = TestClient(app_mod.app, raise_server_exceptions=True)
    r = c.post(f"/e/{tok}", data={"name": name, "email": email, "sex": "F",
               "affiliation": "DOH", "consent": "on"}, follow_redirects=False)
    assert r.status_code == 303


def _add_raw(db_path, tok, name, email, purged=False):
    conn = st.connect(db_path)
    ev = st.get_event(conn, tok)
    aid = st.add_attendee(conn, ev["id"], name=name, email=email, contact="",
                          sex="F", affiliation="DOH", consent_text="t", ip=None)
    if purged:
        conn.execute("UPDATE attendee SET purged_at='2026-01-01T00:00:00', name=NULL, "
                     "email=NULL WHERE id=?", (aid,))
        conn.commit()
    conn.close()


def _reset_limits(db_path):
    conn = st.connect(db_path)
    for k, in conn.execute("SELECT key FROM app_setting WHERE key LIKE 'event_update_email%'").fetchall():
        st.set_setting(conn, k, "")
    st.set_email_feature(conn, "event_update", True)
    conn.close()


def _mail(monkeypatch, configured=True):
    sent = []
    monkeypatch.setattr(mailer, "email_configured", lambda: configured)
    monkeypatch.setattr(mailer, "send",
                        lambda to, subj, body, html=None: sent.append(
                            {"to": to, "subject": subj, "body": body, "html": html or ""})
                        or {"sent": True})
    return sent


def _post(manager, tok, text="Moved to Room 3B", tick=True, **extra):
    data = {"announcement": text, **extra}
    if tick:
        data["email_registrants"] = "on"
    return manager.post(f"/activities/{tok}/announcement", data=data, follow_redirects=False)


def _qs(r):
    return {k: v[0] for k, v in parse_qs(urlparse(r.headers["location"]).query).items()}


def _fixture(app_mod, manager, db_path, monkeypatch, emails=("a@x.com", "b@x.com")):
    _reset_limits(db_path)
    sent = _mail(monkeypatch)
    tok = _event(manager, db_path)
    for i, e in enumerate(emails):
        _register(app_mod, tok, e, name=f"Person {i}")
    sent.clear()                      # drop the registration confirmations
    return tok, sent


def test_unticked_box_posts_without_emailing(app_mod, manager, db_path, monkeypatch):
    tok, sent = _fixture(app_mod, manager, db_path, monkeypatch)
    r = _post(manager, tok, tick=False)
    assert r.status_code == 303 and "ann=" not in r.headers["location"]
    assert sent == []


def test_ticked_box_emails_each_registrant_with_their_own_link(app_mod, manager, db_path, monkeypatch):
    tok, sent = _fixture(app_mod, manager, db_path, monkeypatch)
    r = _post(manager, tok, "Moved to Room 3B")
    q = _qs(r)
    assert q["ann"] == "sent" and q["annn"] == "2" and q["annm"] == "0"
    assert sorted(m["to"] for m in sent) == ["a@x.com", "b@x.com"]
    assert all(m["subject"].startswith("Update — ") for m in sent)
    assert all("Moved to Room 3B" in m["body"] for m in sent)
    links = [re.search(r"(https?://\S+/resume\?rt=\S+)", m["body"]).group(1) for m in sent]
    assert len(set(links)) == 2                    # each person gets their own link


def test_registrants_without_an_email_are_skipped_silently(app_mod, manager, db_path, monkeypatch):
    tok, sent = _fixture(app_mod, manager, db_path, monkeypatch, emails=("a@x.com",))
    _add_raw(db_path, tok, "No Email", "")
    _add_raw(db_path, tok, "Gone", "g@x.com", purged=True)
    q = _qs(_post(manager, tok))
    assert q["ann"] == "sent" and q["annn"] == "1" and q["annm"] == "0"
    assert [m["to"] for m in sent] == ["a@x.com"]


def test_nobody_with_an_email_reports_none(app_mod, manager, db_path, monkeypatch):
    tok, sent = _fixture(app_mod, manager, db_path, monkeypatch, emails=())
    assert _qs(_post(manager, tok))["ann"] == "none" and sent == []


def test_cooldown_blocks_a_second_blast_but_still_posts(app_mod, manager, db_path, monkeypatch):
    tok, sent = _fixture(app_mod, manager, db_path, monkeypatch)
    _post(manager, tok, "First")
    sent.clear()
    r = _post(manager, tok, "Second")
    assert _qs(r)["ann"].startswith("wait:") and sent == []
    page = TestClient(app_mod.app).get(f"/e/{tok}").text
    conn = st.connect(db_path)
    assert st.get_event(conn, tok)["announcement"] == "Second"      # the post itself went through
    conn.close()


def test_daily_cap_leaves_the_overflow_out(app_mod, manager, db_path, monkeypatch):
    tok, sent = _fixture(app_mod, manager, db_path, monkeypatch, emails=("a@x.com", "b@x.com", "c@x.com"))
    monkeypatch.setattr(email_params, "PARAMS", {**email_params.PARAMS, "update_email_daily_cap": ("cap", 2, 1, 1000)})
    q = _qs(_post(manager, tok))
    assert q["ann"] == "sent" and q["annn"] == "2" and q["annm"] == "1"
    assert len(sent) == 2
    # The quota is shared across activities: a second activity finds it spent.
    tok2 = _event(manager, db_path)
    _register(app_mod, tok2, "z@x.com")
    sent.clear()
    assert _qs(_post(manager, tok2))["ann"] == "cap" and sent == []


def test_admin_switch_off_sends_nothing(app_mod, manager, db_path, monkeypatch):
    tok, sent = _fixture(app_mod, manager, db_path, monkeypatch)
    conn = st.connect(db_path)
    st.set_email_feature(conn, "event_update", False)
    conn.close()
    try:
        assert _qs(_post(manager, tok))["ann"] == "off" and sent == []
    finally:
        _reset_limits(db_path)


def test_mail_not_configured_sends_nothing(app_mod, manager, db_path, monkeypatch):
    tok, sent = _fixture(app_mod, manager, db_path, monkeypatch)
    monkeypatch.setattr(mailer, "email_configured", lambda: False)
    assert _qs(_post(manager, tok))["ann"] == "nomail" and sent == []


def test_removing_the_update_never_emails(app_mod, manager, db_path, monkeypatch):
    tok, sent = _fixture(app_mod, manager, db_path, monkeypatch)
    r = _post(manager, tok, text="")
    assert "ann=" not in r.headers["location"] and sent == []


def test_non_managers_cannot_trigger_it(app_mod, client, viewer, manager, db_path, monkeypatch):
    tok, sent = _fixture(app_mod, manager, db_path, monkeypatch)
    for who in (client, viewer):
        who.post(f"/activities/{tok}/announcement",
                 data={"announcement": "spam", "email_registrants": "on"}, follow_redirects=False)
    assert sent == []


def test_update_text_is_escaped_in_the_email(app_mod, manager, db_path, monkeypatch):
    tok, sent = _fixture(app_mod, manager, db_path, monkeypatch, emails=("a@x.com",))
    _post(manager, tok, "Hi <script>alert(1)</script>\r\nSecond line")
    assert "<script>" not in sent[0]["html"] and "&lt;script&gt;" in sent[0]["html"]
    assert "<br>" in sent[0]["html"]


def test_manage_page_shows_the_option_and_the_reach(app_mod, manager, db_path, monkeypatch):
    tok, sent = _fixture(app_mod, manager, db_path, monkeypatch)
    page = manager.get(f"/activities/{tok}/manage").text
    assert 'name="email_registrants"' in page and "2 people have an email on file" in page
    empty = _event(manager, db_path)
    page = manager.get(f"/activities/{empty}/manage").text
    assert "nobody has registered with an email yet" in page


def test_manage_page_explains_the_outcome(app_mod, manager, db_path, monkeypatch):
    tok, sent = _fixture(app_mod, manager, db_path, monkeypatch)
    page = manager.get(f"/activities/{tok}/manage?ann=sent&annn=2&annm=1").text
    assert "emailing 2 registrants" in page and "1 more was left out" in page
