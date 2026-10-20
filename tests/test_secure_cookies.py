"""
Session/recognition cookies must be markable Secure (HTTPS-only) in production.

HTTPS configuration enables Secure automatically; the explicit flag remains
available for local testing. Local HTTP LAN development keeps working. We assert the raw Set-Cookie header carries (or omits)
the `Secure` attribute accordingly — checking the header, not the client-stored
cookie, since an http test client won't retain a Secure cookie.
"""
from starlette.testclient import TestClient

from tests.conftest import ROLE_USERS, PW
import auth


def _login_set_cookie(app_mod):
    c = TestClient(app_mod.app)
    r = c.post("/login", data={"username": ROLE_USERS["admin"], "password": PW},
               follow_redirects=False)
    assert r.status_code == 303, r.status_code
    # The session cookie line among possibly several Set-Cookie headers.
    lines = [v for k, v in r.headers.raw_items() if k.decode().lower() == "set-cookie"
             ] if hasattr(r.headers, "raw_items") else r.headers.get_list("set-cookie")
    sess = [ln if isinstance(ln, str) else ln.decode() for ln in lines]
    sess = [ln for ln in sess if ln.startswith(auth.COOKIE_NAME + "=")]
    assert sess, "no session Set-Cookie header found"
    return sess[0]


def test_session_cookie_not_secure_by_default(app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "SECURE_COOKIES", False)
    header = _login_set_cookie(app_mod)
    assert "secure" not in header.lower()
    # The other hardening attributes stay intact.
    assert "httponly" in header.lower()
    assert "samesite=lax" in header.lower()


def test_session_cookie_secure_when_enabled(app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "SECURE_COOKIES", True)
    header = _login_set_cookie(app_mod)
    assert "secure" in header.lower()
    assert "httponly" in header.lower()


def test_secure_flag_parses_truthy_env():
    from browser_security import secure_cookies_enabled
    for val, want in [("", False), ("0", False), ("false", False),
                      ("False", False), ("1", True), ("true", True), ("yes", True)]:
        assert secure_cookies_enabled({"CSS_SECURE_COOKIES": val}) is want
