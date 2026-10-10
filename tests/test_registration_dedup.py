"""Duplicate pre-registration fix — a participant who lost their ?att= link must
RESUME their registration (by email, or via the per-event cookie) rather than mint
a second attendee row.

Two layers, mirroring test_monitor / test_event_e:
  * storage logic on an isolated temp DB — the resume-by-email primitive, the
    non-empty-field refresh, and the purge/event scoping of the lookup.
  * routes on the shared test DB — the dedup-aware POST, the cookie recognition
    on the bare link, and the PII-free /check probe.
"""
from __future__ import annotations
import re
from datetime import date
import auth
import ratelimit as rl
import storage as st
import merge_duplicate_attendees as merge
from starlette.testclient import TestClient

# A future event date that stays within the create form's "no more than 2 years
# ahead" guard (computed relative to today so it never drifts out of bounds).
_FUTURE_DATE = date.today().replace(year=date.today().year + 1).isoformat()


# --------------------------------------------------------------------------
# storage layer — deterministic, on its own throwaway database
# --------------------------------------------------------------------------

def _fresh(tmp_path):
    conn = st.connect(str(tmp_path / "dedup.db"))
    st.init_db(conn)
    return conn


def _event(conn, event_date="2099-01-01"):
    f2 = st.create_form_instance(conn, 2, "F2", event_date, topic="Event review")
    ev = st.create_event(conn, "Forum", event_date,
                         form_instance_ids=[f2], created_by="manager@test.local")
    return ev["id"]


def test_register_resumes_same_email(tmp_path):
    conn = _fresh(tmp_path)
    eid = _event(conn)
    id1, resumed1 = st.register_attendee(conn, eid, name="Ana", email="ana@x.com",
                                         sex="F", affiliation="DOH", consent_text="x")
    assert resumed1 is False
    # Same email, different case + whitespace -> resume the SAME row, no new insert.
    id2, resumed2 = st.register_attendee(conn, eid, name="Ana", email="  ANA@x.com ",
                                         sex="F", affiliation="DOH", consent_text="x")
    assert resumed2 is True and id2 == id1
    assert st.count_attendees(conn) == 1


def test_resume_refreshes_nonempty_keeps_blank_and_consent(tmp_path):
    conn = _fresh(tmp_path)
    eid = _event(conn)
    aid, _ = st.register_attendee(conn, eid, name="Ana", email="ana@x.com",
                                  contact="0917", sex="F", affiliation="DOH",
                                  consent_text="first")
    first_consent = st.get_attendee(conn, aid)["consent_at"]
    # Resume: new contact (refresh), blank name (must NOT wipe), new consent_text
    # is ignored (consent record is immutable after first capture).
    st.register_attendee(conn, eid, name="", email="ana@x.com", contact="0920",
                         sex="F", affiliation="DOH", consent_text="second")
    row = conn.execute("SELECT name, email, contact, consent_at, consent_text "
                       "FROM attendee WHERE id=?", (aid,)).fetchone()
    assert row[0] == "Ana"           # blank did not overwrite
    assert row[1] == "ana@x.com"     # email untouched
    assert row[2] == "0920"          # non-empty refreshed
    assert row[3] == first_consent and row[4] == "first"   # consent immutable


def test_find_ignores_purged_and_scopes_event(tmp_path):
    conn = _fresh(tmp_path)
    eid = _event(conn)
    other = _event(conn)
    st.register_attendee(conn, eid, name="Ana", email="ana@x.com", consent_text="x")
    # Same email under a DIFFERENT event must not match.
    assert st.find_attendee_by_email(conn, other, "ana@x.com") is None
    # After a purge nulls the email, the row no longer matches -> a fresh row.
    st.purge_expired_attendees(conn, "2999-01-01")
    assert st.find_attendee_by_email(conn, eid, "ana@x.com") is None
    _id, resumed = st.register_attendee(conn, eid, name="Ana", email="ana@x.com",
                                        consent_text="x")
    assert resumed is False and st.count_attendees(conn) == 2


# --------------------------------------------------------------------------
# routes — shared test DB + the manager client (mirrors test_event_e)
# --------------------------------------------------------------------------

def _make_event(manager, db_path):
    conn = st.connect(db_path)
    rp = conn.execute("SELECT id FROM resource_person WHERE is_internal=1 LIMIT 1").fetchone()
    conn.close()
    r = manager.post("/create", data={
        "event_type": "bureau", "activity_name": "Dedup Forum",
        "event_date": _FUTURE_DATE, "venue": "Hall A", "qr_mode": "combined",
        "rp_id": str(rp[0]), "topic": "Keynote",
    }, follow_redirects=True)
    assert r.status_code == 200
    return re.search(r"/e/([0-9a-f]{12})", r.text).group(1)


def test_duplicate_post_reuses_attendee(client, manager, db_path):
    tok = _make_event(manager, db_path)
    before = st.count_attendees(st.connect(db_path))
    data = {"name": "Bea", "email": "bea@example.com", "sex": "F",
            "affiliation": "DOH", "consent": "on"}
    r1 = client.post(f"/e/{tok}", data=data, follow_redirects=False)
    att1 = re.search(r"att=([^&]+)", r1.headers["location"]).group(1)
    # "Lost my link" -> re-submit the SAME email -> resume, no duplicate row.
    r2 = client.post(f"/e/{tok}", data=data, follow_redirects=False)
    att2 = re.search(r"att=([^&]+)", r2.headers["location"]).group(1)
    assert att2 == att1
    assert st.count_attendees(st.connect(db_path)) == before + 1


def test_check_endpoint_is_pii_free(client, manager, db_path):
    tok = _make_event(manager, db_path)
    client.post(f"/e/{tok}", data={"name": "Cy Tan", "email": "cy@example.com",
                "sex": "M", "affiliation": "DOH", "consent": "on"})
    r = client.get(f"/e/{tok}/check", params={"email": "cy@example.com"})
    assert r.status_code == 200 and r.json() == {"registered": True}
    assert "Cy Tan" not in r.text                      # no identity leaked
    assert client.get(f"/e/{tok}/check",
                      params={"email": "nobody@example.com"}).json() == {"registered": False}


def test_cookie_recognizes_returning_participant(app_mod, manager, db_path):
    tok = _make_event(manager, db_path)
    # Fresh client (own cookie jar) so the recognition is purely cookie-driven.
    c = TestClient(app_mod.app, raise_server_exceptions=True)
    r = c.post(f"/e/{tok}", data={"name": "Deo", "email": "deo@example.com",
               "sex": "M", "affiliation": "NON-DOH", "consent": "on"},
               follow_redirects=False)
    assert r.status_code == 303
    assert any("css_att_e" in v for v in r.headers.get_list("set-cookie"))
    # The bare link (NO ?att=) is now recognized via the cookie -> the registered view
    # (its "start fresh" link) shows. Rating links are NOT the signal here: this
    # event is a year out, so its feedback is held back until it starts.
    r = c.get(f"/e/{tok}")
    assert r.status_code == 200 and f"/e/{tok}/forget" in r.text


# --------------------------------------------------------------------------
# Item 1 — confirm-don't-collapse on a shared email
# --------------------------------------------------------------------------

def _reg(name, email, **kw):
    d = {"name": name, "email": email, "sex": "F", "affiliation": "DOH",
         "consent": "on"}
    d.update(kw)
    return d


def test_same_name_resumes_silently(client, manager, db_path):
    tok = _make_event(manager, db_path)
    data = _reg("Ela Reyes", "ela@example.com")
    a1 = re.search(r"att=([^&]+)",
                   client.post(f"/e/{tok}", data=data, follow_redirects=False)
                   .headers["location"]).group(1)
    # Same person, same email -> straight 303 resume, no interstitial.
    r = client.post(f"/e/{tok}", data=data, follow_redirects=False)
    assert r.status_code == 303
    assert re.search(r"att=([^&]+)", r.headers["location"]).group(1) == a1


def test_different_name_shows_confirm_and_does_not_collapse(client, manager, db_path):
    tok = _make_event(manager, db_path)
    client.post(f"/e/{tok}", data=_reg("Fay Lim", "shared@office.example"))
    before = st.count_attendees(st.connect(db_path))
    # A different name on the SAME email -> interstitial, NOT a silent overwrite.
    r = client.post(f"/e/{tok}", data=_reg("Gil Tan", "shared@office.example"),
                    follow_redirects=False)
    assert r.status_code == 200 and "Is this you?" in r.text
    assert st.count_attendees(st.connect(db_path)) == before   # nothing written
    # The first person's name is untouched.
    conn = st.connect(db_path)
    names = [r[0] for r in conn.execute(
        "SELECT name FROM attendee WHERE LOWER(email)=?",
        ("shared@office.example",)).fetchall()]
    conn.close()
    assert names == ["Fay Lim"]


def test_resolve_new_creates_separate_attendee(client, manager, db_path):
    tok = _make_event(manager, db_path)
    client.post(f"/e/{tok}", data=_reg("Hana Cruz", "team@office.example"))
    before = st.count_attendees(st.connect(db_path))
    # "I'm a different person" -> a deliberate second registration on the shared email.
    r = client.post(f"/e/{tok}", data=_reg("Ian Cruz", "team@office.example",
                    resolve="new"), follow_redirects=False)
    assert r.status_code == 303
    assert st.count_attendees(st.connect(db_path)) == before + 1
    conn = st.connect(db_path)
    names = sorted(r[0] for r in conn.execute(
        "SELECT name FROM attendee WHERE LOWER(email)=?",
        ("team@office.example",)).fetchall())
    conn.close()
    assert names == ["Hana Cruz", "Ian Cruz"]


def test_resolve_resume_reuses_existing(client, manager, db_path):
    tok = _make_event(manager, db_path)
    a1 = re.search(r"att=([^&]+)",
                   client.post(f"/e/{tok}", data=_reg("Jo Yu", "jo@example.com"),
                               follow_redirects=False).headers["location"]).group(1)
    before = st.count_attendees(st.connect(db_path))
    # "Yes that's me" -> resume the existing row, no new attendee.
    r = client.post(f"/e/{tok}", data=_reg("Jo Yu Jr", "jo@example.com",
                    resolve="resume"), follow_redirects=False)
    assert r.status_code == 303
    assert re.search(r"att=([^&]+)", r.headers["location"]).group(1) == a1
    assert st.count_attendees(st.connect(db_path)) == before


# --------------------------------------------------------------------------
# Item 2 — "Not you?" clears the device cookie (shared-device safety)
# --------------------------------------------------------------------------

def test_forget_clears_cookie_and_shows_form(app_mod, manager, db_path):
    tok = _make_event(manager, db_path)
    c = TestClient(app_mod.app, raise_server_exceptions=True)
    c.post(f"/e/{tok}", data=_reg("Kay Diaz", "kay@example.com"))
    assert f"/e/{tok}/forget" in c.get(f"/e/{tok}").text   # recognized via cookie
    # "Not you?" -> clears the cookie and routes to a blank form.
    r = c.get(f"/e/{tok}/forget", follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"].endswith("?fresh=1")
    assert any("css_att_e" in v and ("Max-Age=0" in v or "expires=" in v.lower())
               for v in r.headers.get_list("set-cookie"))
    # The next person on this device sees the consent form, not Kay's session.
    r = c.get(f"/e/{tok}")
    assert 'name="consent"' in r.text and "/r/" not in r.text


def test_fresh_param_ignores_cookie(app_mod, manager, db_path):
    tok = _make_event(manager, db_path)
    c = TestClient(app_mod.app, raise_server_exceptions=True)
    c.post(f"/e/{tok}", data=_reg("Lia Sun", "lia@example.com"))
    # Even with the cookie still set, ?fresh=1 forces the blank form.
    r = c.get(f"/e/{tok}?fresh=1")
    assert 'name="consent"' in r.text and "/r/" not in r.text


# --------------------------------------------------------------------------
# Recovery "magic link" — token + /resume route + organizer endpoints
# --------------------------------------------------------------------------

def test_recovery_token_roundtrip_tamper_expiry():
    t = auth.make_recovery_token(4242)
    assert auth.verify_recovery_token(t) == 4242
    assert auth.verify_recovery_token(t + "x") is None        # tampered sig
    assert auth.verify_recovery_token("garbage") is None
    # Minted far in the past -> expired.
    old = auth.make_recovery_token(7, issued_at=0)
    assert auth.verify_recovery_token(old, now=auth._RECOVER_MAX_AGE + 10) is None


def test_resume_link_recognizes_on_fresh_device(app_mod, manager, db_path):
    tok = _make_event(manager, db_path)
    reg = TestClient(app_mod.app, raise_server_exceptions=True)
    att = re.search(r"att=([^&]+)", reg.post(f"/e/{tok}", data=_reg("Mara Go", "mara@example.com"),
                    follow_redirects=False).headers["location"]).group(1)
    rtok = auth.make_recovery_token(auth.verify_attendee_token(att))
    # A brand-new device (no cookie) opens the recovery link -> recognized + cookie set.
    c = TestClient(app_mod.app, raise_server_exceptions=True)
    r = c.get(f"/e/{tok}/resume", params={"rt": rtok}, follow_redirects=False)
    assert r.status_code == 303 and "att=" in r.headers["location"]
    assert any("css_att_e" in v for v in r.headers.get_list("set-cookie"))
    assert f"/e/{tok}/forget" in c.get(f"/e/{tok}").text   # now recognized by the cookie


def test_resume_bad_token_falls_back_to_page(client, manager, db_path):
    tok = _make_event(manager, db_path)
    r = client.get(f"/e/{tok}/resume", params={"rt": "nope"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == f"/e/{tok}?expired=1"


def test_organizer_recovery_link_and_it_resumes(manager, db_path, app_mod):
    tok = _make_event(manager, db_path)
    c = TestClient(app_mod.app, raise_server_exceptions=True)
    att = re.search(r"att=([^&]+)", c.post(f"/e/{tok}", data=_reg("Noli Sy", "noli@example.com"),
                    follow_redirects=False).headers["location"]).group(1)
    # Organizer mints the link...
    r = manager.get(f"/monitor/{tok}/recovery-link/{auth.verify_attendee_token(att)}")
    assert r.status_code == 200
    link = r.json()["link"]
    assert f"/e/{tok}/resume?rt=" in link
    # ...and the minted link actually works end to end.
    path = link.split("//", 1)[-1].split("/", 1)[-1]      # strip scheme+host
    r = c.get("/" + path, follow_redirects=False)
    assert r.status_code == 303 and f"att={att}" in r.headers["location"]


def test_resend_without_smtp_tells_organizer_to_copy(manager, db_path, app_mod):
    tok = _make_event(manager, db_path)
    c = TestClient(app_mod.app, raise_server_exceptions=True)
    att = re.search(r"att=([^&]+)", c.post(f"/e/{tok}", data=_reg("Ofe Tan", "ofe@example.com"),
                    follow_redirects=False).headers["location"]).group(1)
    r = manager.post(f"/monitor/{tok}/resend/{auth.verify_attendee_token(att)}")
    body = r.json()
    assert body["sent"] is False and "Copy link" in body["detail"]


def test_recovery_link_requires_manage_cap(viewer, manager, db_path):
    tok = _make_event(manager, db_path)
    # The /monitor cap gate blocks viewers/encoders from the whole area.
    assert viewer.get(f"/monitor/{tok}/recovery-link/1").status_code == 403


# --------------------------------------------------------------------------
# Rate limiting (ratelimit.py + the /check gate)
# --------------------------------------------------------------------------

def test_ratelimit_allow_then_block():
    rl.reset()
    assert rl.allow("check", "1.2.3.4", now=1000) is True
    # A blank IP is never limited.
    assert all(rl.allow("check", "", now=1000) for _ in range(1000))


def test_check_returns_429_over_limit(client, manager, db_path, monkeypatch):
    tok = _make_event(manager, db_path)
    monkeypatch.setenv("CSS_RL_CHECK", "2/60")     # tiny window for the test
    rl.reset()
    assert client.get(f"/e/{tok}/check", params={"email": "a@x.com"}).status_code == 200
    assert client.get(f"/e/{tok}/check", params={"email": "b@x.com"}).status_code == 200
    assert client.get(f"/e/{tok}/check", params={"email": "c@x.com"}).status_code == 429
    rl.reset()


# --------------------------------------------------------------------------
# merge_duplicate_attendees.py — accidental-dup cleanup (NOT shared inboxes)
# --------------------------------------------------------------------------

def test_merge_collapses_accidental_dups_only(tmp_path):
    conn = _fresh(tmp_path)
    eid = _event(conn)
    # Two ACCIDENTAL dups (same email + same name) + a feedback response on each.
    f = conn.execute("SELECT form_instance_id FROM event_form WHERE event_id=?",
                     (eid,)).fetchone()[0]
    a1 = st.add_attendee(conn, eid, name="Pam Uy", email="pam@x.com", consent_text="x")
    st.record_response(conn, f, [("B6", 6)], attendee_id=a1)
    a2 = st.add_attendee(conn, eid, name="pam  uy", email="PAM@x.com", consent_text="x")
    st.record_response(conn, f, [("B6", 5)], attendee_id=a2)
    # A legitimate shared inbox: same email, DIFFERENT name -> must be left alone.
    b = st.add_attendee(conn, eid, name="Other Person", email="pam@x.com", consent_text="x")

    groups = merge.run(conn=conn, apply=True)
    assert len(groups) == 1 and groups[0]["survivor"] == a1 and groups[0]["dups"] == [a2]
    # a2 merged into a1; both responses now point at a1; shared-inbox row b survives.
    assert st.get_attendee(conn, a2) is None
    assert st.get_attendee(conn, b) is not None
    n = conn.execute("SELECT COUNT(*) FROM response WHERE attendee_id=?", (a1,)).fetchone()[0]
    assert n == 2
