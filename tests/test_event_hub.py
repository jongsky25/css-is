"""Event page as a registration hub (docs/EVENT_REGISTRATION_HUB_PLAN.md, PR-1).

  * the page reads as registration, not "sign in for feedback"
  * feedback is held back until the activity starts (page AND /r/ routes)
  * the personal link + QR show only to a device recognized by its cookie
  * the personal link lives until the activity's last day + 30 days
  * "email me this link" is cookie-only and rate-limited
  * the organizer's pinned update
"""
from __future__ import annotations
import re
import time
from datetime import date, timedelta
from urllib.parse import parse_qs, urlparse

import auth
import mailer
import ratelimit as rl
import storage as st
from starlette.testclient import TestClient

_FUTURE = (date.today() + timedelta(days=60)).isoformat()   # well ahead of today
_PAST = (date.today() - timedelta(days=5)).isoformat()      # already started
_LONG_AGO = (date.today() - timedelta(days=200)).isoformat()  # > 30-day buffer past


def _reg(name="Ana Cruz", email="ana@example.com", **kw):
    d = {"name": name, "email": email, "sex": "F", "affiliation": "DOH", "consent": "on"}
    d.update(kw)
    return d


def _db_event(db_path, event_date, end_date=None, title="Hub Forum"):
    """An event with one feedback form, created straight in the shared test DB so
    its date is fully controlled. Returns (event_token, form_qr_token)."""
    conn = st.connect(db_path)
    f2 = st.create_form_instance(conn, 2, "F2", event_date, topic="Event review")
    ev = st.create_event(conn, title, event_date, form_instance_ids=[f2],
                         created_by="hub@test.local")
    if end_date:
        conn.execute("UPDATE event SET end_date=? WHERE id=?", (end_date, ev["id"]))
        conn.commit()
    qr = conn.execute("SELECT qr_token FROM form_instance WHERE id=?", (f2,)).fetchone()[0]
    tok = ev["event_token"]
    conn.close()
    return tok, qr


def _manager_event(manager, db_path, event_date=_FUTURE):
    conn = st.connect(db_path)
    rp = conn.execute("SELECT id FROM resource_person WHERE is_internal=1 LIMIT 1").fetchone()
    conn.close()
    r = manager.post("/create", data={
        "event_type": "bureau", "activity_name": "Hub Managed Forum",
        "event_date": event_date, "venue": "Hall A", "qr_mode": "combined",
        "rp_id": str(rp[0]), "topic": "Keynote",
    }, follow_redirects=True)
    assert r.status_code == 200
    return re.search(r"/e/([0-9a-f]{12})", r.text).group(1)


def _register(app_mod, tok, **kw):
    """A fresh client (own cookie jar) that registers and follows the redirect."""
    c = TestClient(app_mod.app, raise_server_exceptions=True)
    r = c.post(f"/e/{tok}", data=_reg(**kw), follow_redirects=False)
    assert r.status_code == 303
    return c, r


# ---- 1. copy ---------------------------------------------------------------

def test_form_page_reads_as_registration(client, db_path):
    tok, _ = _db_event(db_path, _FUTURE)
    r = client.get(f"/e/{tok}")
    assert r.status_code == 200
    assert "Register for this activity" in r.text
    assert "Sign in to give your feedback" not in r.text
    assert 'name="consent"' in r.text and 'name="email"' in r.text
    assert "personal link" in r.text            # the intro promises one


# ---- 2/3/4. feedback held back until the activity starts ------------------------

def test_future_activity_locks_feedback_everywhere(app_mod, db_path):
    tok, qr = _db_event(db_path, _FUTURE)
    c, _ = _register(app_mod, tok)
    page = c.get(f"/e/{tok}").text
    assert f"/r/{qr}" not in page and "Feedback opens when the activity starts" in page
    # The form route itself refuses, on GET and on a crafted POST.
    assert c.get(f"/r/{qr}").status_code == 403
    assert c.post(f"/r/{qr}", data={"seq": "", "att": ""}).status_code == 403


def test_started_activity_shows_feedback(app_mod, db_path):
    tok, qr = _db_event(db_path, _PAST)
    c, _ = _register(app_mod, tok)
    assert f"/r/{qr}" in c.get(f"/e/{tok}").text
    assert c.get(f"/r/{qr}").status_code == 200


def test_activity_starting_today_is_open(app_mod, db_path):
    tok, qr = _db_event(db_path, date.today().isoformat())
    c, _ = _register(app_mod, tok)
    assert f"/r/{qr}" in c.get(f"/e/{tok}").text


def test_form_with_its_own_window_keeps_its_behaviour(app_mod, db_path):
    # A form whose own open_at has passed is open even though the activity is a
    # long way off — the explicit window wins.
    tok, qr = _db_event(db_path, _FUTURE)
    conn = st.connect(db_path)
    fid = conn.execute("SELECT id FROM form_instance WHERE qr_token=?", (qr,)).fetchone()[0]
    st.set_response_window(conn, fid, "2020-01-01T00:00", None)
    conn.close()
    c, _ = _register(app_mod, tok)
    assert f"/r/{qr}" in c.get(f"/e/{tok}").text
    assert c.get(f"/r/{qr}").status_code == 200


def test_feedback_state_helper_never_raises_on_bad_dates(app_mod):
    f = {"open_at": None, "close_at": None}
    assert app_mod._feedback_state({"event_date": None}, f) == "open"
    assert app_mod._feedback_state({"event_date": "garbage"}, f) == "open"
    assert app_mod._feedback_state({"event_date": _FUTURE}, f) == "not_yet"


# ---- 5/6. save-your-link panel --------------------------------------------

def test_panel_after_registration_with_cookie(app_mod, db_path):
    tok, _ = _db_event(db_path, _FUTURE)
    c, r = _register(app_mod, tok)
    assert "new=1" in r.headers["location"] and "att=" in r.headers["location"]
    page = c.get(r.headers["location"]).text
    assert "You're registered" in page
    assert f"/e/{tok}/resume?rt=" in page
    assert "data:image/png;base64" in page
    head = page.split('<details class="panel tint-green save-link"', 1)[1].split(">", 1)[0]
    assert "open" in head


def test_panel_collapsed_on_later_visits(app_mod, db_path):
    tok, _ = _db_event(db_path, _FUTURE)
    c, _ = _register(app_mod, tok)
    page = c.get(f"/e/{tok}").text           # bare link, cookie only
    assert f"/e/{tok}/resume?rt=" in page
    head = page.split('<details class="panel tint-green save-link"', 1)[1].split(">", 1)[0]
    assert "open" not in head


def test_panel_absent_without_cookie(app_mod, db_path):
    tok, _ = _db_event(db_path, _FUTURE)
    c, r = _register(app_mod, tok)
    att = parse_qs(urlparse(r.headers["location"]).query)["att"][0]
    stranger = TestClient(app_mod.app, raise_server_exceptions=True)
    page = stranger.get(f"/e/{tok}?att={att}").text
    assert "/resume?rt=" not in page and "data:image/png;base64" not in page


def test_resubmitting_does_not_reopen_the_welcome_panel(app_mod, db_path):
    tok, _ = _db_event(db_path, _FUTURE)
    c, _ = _register(app_mod, tok)
    r = c.post(f"/e/{tok}", data=_reg(), follow_redirects=False)
    assert "new=1" not in r.headers["location"]


# ---- 7. personal-link expiry ----------------------------------------------

def test_verify_recovery_token_expires_at():
    now = time.time()
    old = auth.make_recovery_token(7, issued_at=now - 200 * 24 * 3600)
    assert auth.verify_recovery_token(old, now=now) is None                  # 90-day rule
    assert auth.verify_recovery_token(old, now=now, expires_at=now + 60) == 7
    assert auth.verify_recovery_token(old, now=now, expires_at=now - 1) is None
    fresh = auth.make_recovery_token(7, issued_at=now)
    assert auth.verify_recovery_token(fresh, now=now) == 7                   # default path


def test_link_expiry_is_last_day_plus_30(app_mod):
    exp = app_mod._personal_link_expiry({"event_date": "2026-11-24", "end_date": "2026-11-27"})
    from datetime import datetime
    got = datetime.fromtimestamp(exp, app_mod.LOCAL_TZ)
    assert (got.year, got.month, got.day, got.hour, got.minute) == (2026, 12, 27, 23, 59)
    assert app_mod._personal_link_expiry({"event_date": None}) is None
    assert app_mod._personal_link_expiry({"event_date": "bad"}) is None


def test_early_registrant_link_outlives_90_days(app_mod, db_path):
    far = (date.today() + timedelta(days=150)).isoformat()
    tok, _ = _db_event(db_path, far)
    c, r = _register(app_mod, tok)
    att = int(parse_qs(urlparse(r.headers["location"]).query)["att"][0])
    stale = auth.make_recovery_token(att, issued_at=time.time() - 100 * 24 * 3600)
    new = TestClient(app_mod.app, raise_server_exceptions=True)
    r = new.get(f"/e/{tok}/resume", params={"rt": stale}, follow_redirects=False)
    assert r.status_code == 303 and f"att={att}" in r.headers["location"]
    assert any("css_att_e" in v for v in r.headers.get_list("set-cookie"))


def test_link_past_the_buffer_is_expired(app_mod, db_path):
    tok, _ = _db_event(db_path, _LONG_AGO)
    c, r = _register(app_mod, tok)
    att = int(parse_qs(urlparse(r.headers["location"]).query)["att"][0])
    t = auth.make_recovery_token(att)
    new = TestClient(app_mod.app, raise_server_exceptions=True)
    r = new.get(f"/e/{tok}/resume", params={"rt": t}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/e/{tok}?expired=1"
    assert "has expired" in new.get(f"/e/{tok}?expired=1").text


def test_cookie_lasts_through_a_distant_activity(app_mod, db_path):
    far = (date.today() + timedelta(days=150)).isoformat()
    tok, _ = _db_event(db_path, far)
    _, r = _register(app_mod, tok)
    cookie = [v for v in r.headers.get_list("set-cookie") if "css_att_e" in v][0]
    max_age = int(re.search(r"Max-Age=(\d+)", cookie).group(1))
    assert max_age > 150 * 24 * 3600


# ---- 8. email me this link -------------------------------------------------

def _mail_sink(monkeypatch):
    calls = []
    monkeypatch.setattr(mailer, "email_configured", lambda: True)
    monkeypatch.setattr(mailer, "send",
                        lambda to, subj, body, html=None: calls.append((to, subj, body)) or {"sent": True})
    return calls


def test_email_link_needs_the_cookie(app_mod, db_path, monkeypatch):
    calls = _mail_sink(monkeypatch)
    tok, _ = _db_event(db_path, _FUTURE)
    c, r = _register(app_mod, tok)
    att = parse_qs(urlparse(r.headers["location"]).query)["att"][0]
    calls.clear()
    stranger = TestClient(app_mod.app, raise_server_exceptions=True)
    r = stranger.post(f"/e/{tok}/email-link?att={att}", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/e/{tok}"
    assert calls == []


def test_email_link_sends_to_the_registered_address_and_cools_down(app_mod, db_path, monkeypatch):
    calls = _mail_sink(monkeypatch)
    rl._HITS.clear() if hasattr(rl, "_HITS") else None
    tok, _ = _db_event(db_path, _FUTURE)
    c, _ = _register(app_mod, tok, email="mara@example.com", name="Mara Go")
    # The registration email itself was just logged as sent -> inside the cooldown.
    conn = st.connect(db_path)
    st.log_email_send(conn, "registration_confirmed", "mara@example.com", "s", "sent")
    conn.close()
    r = c.post(f"/e/{tok}/email-link", data={"email": "victim@example.com"},
               follow_redirects=False)
    assert "emailed=wait" in r.headers["location"]
    # Age the log row past the cooldown: now it sends — and only to Mara.
    conn = st.connect(db_path)
    conn.execute("UPDATE email_log SET created_at='2000-01-01T00:00:00' "
                 "WHERE recipient='mara@example.com'")
    conn.commit()
    conn.close()
    calls.clear()
    r = c.post(f"/e/{tok}/email-link", data={"email": "victim@example.com"},
               follow_redirects=False)
    assert "emailed=1" in r.headers["location"]
    assert [x[0] for x in calls] == ["mara@example.com"]
    assert "/resume?rt=" in calls[0][2]
    assert "m•••@example.com" in c.get(r.headers["location"]).text


def test_email_button_hidden_when_mail_not_configured(app_mod, db_path, monkeypatch):
    tok, _ = _db_event(db_path, _FUTURE)
    c, _ = _register(app_mod, tok)
    monkeypatch.setattr(mailer, "email_configured", lambda: False)
    assert "email-link" not in c.get(f"/e/{tok}").text


# ---- 9. pinned update ------------------------------------------------------

def test_pinned_update_flow(app_mod, manager, db_path):
    tok = _manager_event(manager, db_path)
    c, _ = _register(app_mod, tok)
    r = manager.post(f"/activities/{tok}/announcement",
                     data={"announcement": "Moved to Room 3B <b>now</b>"}, follow_redirects=False)
    assert r.status_code == 303
    assert "Moved to Room 3B &lt;b&gt;now&lt;/b&gt;" in c.get(f"/e/{tok}").text   # escaped
    # Not shown to someone who has not registered.
    assert "Moved to Room 3B" not in TestClient(app_mod.app).get(f"/e/{tok}").text
    # The manage card shows it, and re-saving the same text keeps its posted time.
    conn = st.connect(db_path)
    before = conn.execute("SELECT announcement_at FROM event WHERE event_token=?", (tok,)).fetchone()[0]
    conn.close()
    assert before
    manager.post(f"/activities/{tok}/announcement",
                 data={"announcement": "Moved to Room 3B <b>now</b>"})
    conn = st.connect(db_path)
    after = conn.execute("SELECT announcement_at FROM event WHERE event_token=?", (tok,)).fetchone()[0]
    conn.close()
    assert after == before
    # Blank removes it.
    manager.post(f"/activities/{tok}/announcement", data={"announcement": ""})
    assert "Moved to Room 3B" not in c.get(f"/e/{tok}").text


def test_pinned_update_is_capped(app_mod, manager, db_path):
    tok = _manager_event(manager, db_path)
    manager.post(f"/activities/{tok}/announcement", data={"announcement": "x" * 5000})
    conn = st.connect(db_path)
    n = conn.execute("SELECT length(announcement) FROM event WHERE event_token=?", (tok,)).fetchone()[0]
    conn.close()
    assert n == st.ANNOUNCEMENT_MAX


def test_pinned_update_refused_for_non_managers(app_mod, client, viewer, manager, db_path):
    tok = _manager_event(manager, db_path)
    for who in (client, viewer):
        who.post(f"/activities/{tok}/announcement", data={"announcement": "hijack"},
                 follow_redirects=False)
    conn = st.connect(db_path)
    row = conn.execute("SELECT announcement FROM event WHERE event_token=?", (tok,)).fetchone()
    conn.close()
    assert not row[0]


# ---- PR-2: organizer side ----------------------------------------------------

def test_manage_page_has_poster_qr(app_mod, manager, db_path):
    tok = _manager_event(manager, db_path)
    page = manager.get(f"/activities/{tok}/manage").text
    assert "data:image/png;base64" in page
    assert f"{tok}-qr.png" in page and "Download QR" in page


def test_manage_qr_uses_the_custom_link_when_set(app_mod, manager, db_path):
    tok = _manager_event(manager, db_path)
    manager.post(f"/activities/{tok}/slug", data={"slug": "hub-poster-test"})
    page = manager.get(f"/activities/{tok}/manage").text
    assert "hub-poster-test-qr.png" in page


def test_monitor_shows_when_personal_links_expire(app_mod, manager, db_path):
    tok = _manager_event(manager, db_path, event_date=_FUTURE)
    page = manager.get(f"/monitor/{tok}").text
    assert "Personal links stay valid until" in page
    want = app_mod._link_valid_until({"event_date": _FUTURE, "end_date": None})
    assert want in page
    assert app_mod._link_valid_until({"event_date": None}) is None
