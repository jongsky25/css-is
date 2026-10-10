"""A bare attendee id must never be an identity (docs/EVENT_REGISTRATION_HUB_PLAN.md,
"Known issue"). `?att=`, the per-event cookie, the rating form's hidden field and
certificate links all carry a SIGNED token instead. These tests pin down that
guessing or forging an integer id gets an attacker nothing, on every path that used
to accept one.
"""
from __future__ import annotations
import re
import time
from datetime import date, timedelta

import auth
import storage as st
from starlette.testclient import TestClient

_PAST = (date.today() - timedelta(days=5)).isoformat()


def _event(db_path, event_date=_PAST, title="Hardening Forum"):
    conn = st.connect(db_path)
    f2 = st.create_form_instance(conn, 2, "F2", event_date, topic="Event review")
    ev = st.create_event(conn, title, event_date, form_instance_ids=[f2],
                         created_by="hard@test.local")
    qr = conn.execute("SELECT qr_token FROM form_instance WHERE id=?", (f2,)).fetchone()[0]
    st.set_event_certificate(conn, ev["id"], enabled=True, signatory_rp_id=None,
                             verb="attended")
    tok = ev["event_token"]
    conn.close()
    return tok, qr


def _register(app_mod, tok, email="victim@example.com", name="Vic Tim"):
    c = TestClient(app_mod.app, raise_server_exceptions=True)
    r = c.post(f"/e/{tok}", data={"name": name, "email": email, "sex": "F",
               "affiliation": "DOH", "consent": "on"}, follow_redirects=False)
    assert r.status_code == 303
    token = re.search(r"att=([^&]+)", r.headers["location"]).group(1)
    return c, token, auth.verify_attendee_token(token)


def _finish(client, qr, token):
    return client.post(f"/r/{qr}", data={"seq": "", "att": token, "A": "7", "B1": "7",
                       "C": "4", "remarks": "ok"})


def _stranger(app_mod):
    return TestClient(app_mod.app, raise_server_exceptions=True)


def test_redirect_carries_a_signed_token_not_an_id(app_mod, db_path):
    tok, _ = _event(db_path)
    _, token, aid = _register(app_mod, tok)
    assert not token.isdigit() and "." in token and isinstance(aid, int)


def test_guessed_id_does_not_open_a_registrants_page(app_mod, db_path):
    tok, _ = _event(db_path)
    _, _, aid = _register(app_mod, tok)
    page = _stranger(app_mod).get(f"/e/{tok}?att={aid}").text
    assert "Vic Tim" not in page and f"/e/{tok}/forget" not in page
    assert "Register for this activity" in page            # an empty form instead


def test_forged_cookie_with_a_bare_id_is_not_recognized(app_mod, db_path):
    tok, _ = _event(db_path)
    _, _, aid = _register(app_mod, tok)
    eid = st.get_event(st.connect(db_path), tok)["id"]
    c = _stranger(app_mod)
    c.cookies.set(app_mod._attendee_cookie_name(eid), str(aid))
    page = c.get(f"/e/{tok}").text
    assert "Vic Tim" not in page and "Register for this activity" in page


def test_guessed_id_cannot_download_a_certificate(app_mod, db_path):
    tok, qr = _event(db_path)
    c, token, aid = _register(app_mod, tok)
    assert _finish(c, qr, token).status_code == 200
    assert c.get(f"/e/{tok}/certificate?att={token}&fmt=pdf").status_code == 200   # owner
    r = _stranger(app_mod).get(f"/e/{tok}/certificate?att={aid}&fmt=pdf")
    assert r.status_code == 403


def test_guessed_id_cannot_submit_feedback_as_someone_else(app_mod, db_path):
    tok, qr = _event(db_path)
    _, _, aid = _register(app_mod, tok)
    _finish(_stranger(app_mod), qr, str(aid))              # forged identity
    conn = st.connect(db_path)
    n = conn.execute("SELECT COUNT(*) FROM response WHERE attendee_id=?", (aid,)).fetchone()[0]
    conn.close()
    assert n == 0                                          # recorded unattributed, if at all


def test_signed_token_still_tags_the_owners_rating(app_mod, db_path):
    tok, qr = _event(db_path)
    c, token, aid = _register(app_mod, tok)
    _finish(c, qr, token)
    conn = st.connect(db_path)
    n = conn.execute("SELECT COUNT(*) FROM response WHERE attendee_id=?", (aid,)).fetchone()[0]
    conn.close()
    assert n == 1


def test_rating_form_does_not_echo_a_forged_att(app_mod, db_path):
    tok, qr = _event(db_path)
    _, token, aid = _register(app_mod, tok)
    forged = _stranger(app_mod).get(f"/r/{qr}?att={aid}").text
    assert f'name="att" value="{aid}"' not in forged
    ok = _stranger(app_mod).get(f"/r/{qr}?att={token}").text
    assert f'name="att" value="{token}"' in ok


def test_token_is_scoped_to_its_own_activity(app_mod, db_path):
    tok_a, _ = _event(db_path, title="Forum A")
    tok_b, _ = _event(db_path, title="Forum B")
    _, token_a, _ = _register(app_mod, tok_a)
    page = _stranger(app_mod).get(f"/e/{tok_b}?att={token_a}").text
    assert "Vic Tim" not in page and "Register for this activity" in page


def test_tampered_token_is_rejected(app_mod, db_path):
    tok, _ = _event(db_path)
    _, token, _ = _register(app_mod, tok)
    body, sig = token.rsplit(".", 1)
    bad = body + "." + ("0" if sig[0] != "0" else "1") + sig[1:]
    assert auth.verify_attendee_token(bad) is None
    assert "Vic Tim" not in _stranger(app_mod).get(f"/e/{tok}?att={bad}").text


def test_resume_and_session_tokens_are_not_interchangeable(app_mod, db_path):
    tok, _ = _event(db_path)
    _, token, aid = _register(app_mod, tok)
    recover = auth.make_recovery_token(aid)
    assert auth.verify_recovery_token(token) is None       # session token can't resume
    assert auth.verify_attendee_token(recover) is None     # resume token isn't a session
    assert "Vic Tim" not in _stranger(app_mod).get(f"/e/{tok}?att={recover}").text
    r = _stranger(app_mod).get(f"/e/{tok}/resume", params={"rt": token}, follow_redirects=False)
    assert r.headers["location"].endswith("?expired=1")


def test_session_token_expires_after_400_days():
    now = time.time()
    old = auth.make_attendee_token(5, issued_at=now - 401 * 24 * 3600)
    assert auth.verify_attendee_token(old, now=now) is None
    assert auth.verify_attendee_token(auth.make_attendee_token(5, issued_at=now - 300 * 24 * 3600), now=now) == 5


def test_nobody_is_locked_out_after_the_personal_link_expires(app_mod, db_path):
    # An activity long past its last day + 30 days: the emailed resume link is dead,
    # but registering again with the same email still gets the person back in.
    long_ago = (date.today() - timedelta(days=200)).isoformat()
    tok, qr = _event(db_path, event_date=long_ago)
    c, token, aid = _register(app_mod, tok)
    assert _finish(c, qr, token).status_code == 200
    back, token2, aid2 = _register(app_mod, tok)           # same email -> resumes the row
    assert aid2 == aid
    assert back.get(f"/e/{tok}/certificate?att={token2}&fmt=pdf").status_code == 200
    assert "Vic Tim" in back.get(f"/e/{tok}").text
