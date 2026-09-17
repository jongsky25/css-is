"""
Auth & RBAC — login flow, session integrity/expiry, capability gating per role,
and single-use invite/reset tokens.
"""
import time
import pytest
import auth
import storage as st
from tests.conftest import ROLE_USERS, PW, _auth_client

# capability requirements by path prefix (mirrors app._required_cap)
# (path, method, cap_required)
GATED = [
    ("/admin/users",            "get",  "manage_users"),
    ("/admin/audit",            "get",  "manage_users"),
    ("/directory",              "get",  "directory"),
    ("/directory/staff/new",    "get",  "directory"),
    ("/create",                 "post", "create_activity"),
    ("/arta",                   "get",  "create_activity"),
    ("/encode",                 "get",  "encode"),
    ("/arta/entries",           "get",  "manage_walkin_entries"),
]
ROLES = ["viewer", "encoder", "section_manager", "admin"]

def _client_for(app_mod, role):
    return _auth_client(app_mod, role)

@pytest.mark.parametrize("path,method,cap", GATED)
@pytest.mark.parametrize("role", ROLES)
def test_capability_gating(app_mod, role, path, method, cap):
    c = _client_for(app_mod, role)
    allowed = auth.can(role, cap)
    fn = getattr(c, method)
    r = fn(path, follow_redirects=False) if method == "get" else fn(path, data={}, follow_redirects=False)
    if allowed:
        # rendered or did its own thing — never the RBAC 403
        assert r.status_code != 403, f"{role} should access {path} (cap {cap})"
    else:
        # denied: 403 forbidden page (GET) — must NOT succeed
        assert r.status_code == 403, f"{role} must be 403 on {path} (cap {cap}), got {r.status_code}"

# ---- unauthenticated access ----

def test_unauth_get_redirects_to_login(client):
    r = client.get("/dashboard", follow_redirects=False)
    assert r.status_code == 303
    assert "/login" in r.headers["location"]

def test_unauth_post_is_401(client):
    r = client.post("/create", data={}, follow_redirects=False)
    assert r.status_code == 401

def test_public_routes_need_no_login(client, sample_ids):
    for p in ("/login", f"/r/{sample_ids['qr_token']}"):
        assert client.get(p, follow_redirects=False).status_code in (200, 404)

# ---- session token integrity / expiry ----

def test_tampered_cookie_rejected(app_mod):
    from starlette.testclient import TestClient
    user = {"id": 1, "username": "x", "role": "admin"}
    tok = auth.make_token(user)
    body, sig = tok.rsplit(".", 1)
    forged = body + "." + ("0" * len(sig))      # wrong signature
    c = TestClient(app_mod.app)
    c.cookies.set(auth.COOKIE_NAME, forged)
    r = c.get("/dashboard", follow_redirects=False)
    assert r.status_code == 303 and "/login" in r.headers["location"]

def test_role_cannot_be_escalated_via_cookie(app_mod):
    """A viewer cannot flip their own role to admin in the (signed) cookie."""
    from starlette.testclient import TestClient
    conn = st.connect(app_mod.DB); u = st.get_admin_user(conn, ROLE_USERS["viewer"]); conn.close()
    payload_user = {"id": u["id"], "username": u["username"], "role": "admin"}  # forged role
    # attacker can't re-sign; mint with wrong secret to simulate tamper
    import hmac, hashlib, json, base64
    raw = json.dumps({"uid": u["id"], "u": u["username"], "r": "admin",
                      "iat": int(time.time())}, separators=(",", ":")).encode()
    b = base64.urlsafe_b64encode(raw).decode().rstrip("=")
    sig = hmac.new(b"not-the-real-secret", b.encode(), hashlib.sha256).hexdigest()
    c = TestClient(app_mod.app); c.cookies.set(auth.COOKIE_NAME, f"{b}.{sig}")
    r = c.get("/admin/users", follow_redirects=False)
    assert r.status_code == 303  # rejected -> login, not 200

def test_expired_session_rejected():
    user = {"id": 1, "username": "x", "role": "admin"}
    old = auth.make_token(user, issued_at=time.time() - (13 * 3600))  # > 12h
    assert auth.parse_token(old) is None

def test_valid_session_parses():
    user = {"id": 1, "username": "x", "role": "admin"}
    assert auth.parse_token(auth.make_token(user))["r"] == "admin"

# ---- login form ----

def test_login_wrong_password(client):
    r = client.post("/login", data={"username": ROLE_USERS["admin"], "password": "wrong"},
                    follow_redirects=False)
    assert r.status_code == 401

def test_login_success_sets_cookie(client):
    r = client.post("/login", data={"username": ROLE_USERS["admin"], "password": PW},
                    follow_redirects=False)
    assert r.status_code == 303
    assert auth.COOKIE_NAME in r.cookies or "set-cookie" in {k.lower() for k in r.headers}

def test_inactive_account_cannot_login(app_mod, client):
    r = client.post("/login", data={"username": "pending@test.local", "password": PW},
                    follow_redirects=False)
    assert r.status_code == 401

# ---- action tokens: invite / reset ----

def test_invite_token_single_use_semantics(app_mod):
    """Invite token signed with empty hash stops working once a password is set."""
    conn = st.connect(app_mod.DB)
    u = st.get_admin_user(conn, "pending@test.local")
    tok = auth.make_action_token(u["id"], auth.PURPOSE_INVITE, "")   # pending hash ''
    assert auth.verify_action_token(tok, "", auth.PURPOSE_INVITE) == u["id"]
    # simulate password set -> hash changes -> old token invalid
    h, salt = auth.hash_password(PW)
    assert auth.verify_action_token(tok, h, auth.PURPOSE_INVITE) is None
    conn.close()

def test_reset_token_expires():
    tok = auth.make_action_token(5, auth.PURPOSE_RESET, "abc",
                                 issued_at=time.time() - 7200)  # 2h > 1h max
    assert auth.verify_action_token(tok, "abc", auth.PURPOSE_RESET) is None

def test_reset_token_wrong_purpose_rejected():
    tok = auth.make_action_token(5, auth.PURPOSE_INVITE, "abc")
    assert auth.verify_action_token(tok, "abc", auth.PURPOSE_RESET) is None

# ---- pilot flow: temporary password + forced reset on first sign-in ----

def _make_temp_account(app_mod, username):
    """Create an active account on the default pilot password (must_change)."""
    conn = st.connect(app_mod.DB)
    h, salt = auth.hash_password(auth.DEFAULT_PASSWORD)
    uid = st.create_admin_user(conn, username, h, salt, "viewer",
                               created_by="test", active=True, must_change=True)
    conn.commit(); conn.close()
    return uid

def test_temp_password_login_forces_reset(app_mod, client):
    """Signing in with the temp password issues NO session — it redirects to the
    reset page instead, so the user must choose their own password."""
    _make_temp_account(app_mod, "tempuser@test.local")
    r = client.post("/login", data={"username": "tempuser@test.local",
                                     "password": auth.DEFAULT_PASSWORD},
                    follow_redirects=False)
    assert r.status_code == 303
    assert "/reset-password?token=" in r.headers["location"]
    # crucially, no real session cookie was set
    assert auth.COOKIE_NAME not in r.cookies

def test_temp_reset_clears_must_change_and_signs_in(app_mod, client):
    """Following the forced reset sets the real password, clears must_change,
    and the new password then logs in normally (no more forced reset)."""
    uid = _make_temp_account(app_mod, "temp2@test.local")
    r = client.post("/login", data={"username": "temp2@test.local",
                                     "password": auth.DEFAULT_PASSWORD},
                    follow_redirects=False)
    token = r.headers["location"].split("token=", 1)[1]
    new_pw = "BrandNew99"
    r2 = client.post("/reset-password", data={"token": token, "password": new_pw},
                     follow_redirects=False)
    assert r2.status_code == 303
    conn = st.connect(app_mod.DB)
    u = st.get_admin_user_by_id(conn, uid); conn.close()
    assert u["must_change"] is False
    assert auth.verify_password(new_pw, u["pw_hash"], u["salt"])
    # the new password now logs in straight to the app, not the reset page
    r3 = client.post("/login", data={"username": "temp2@test.local", "password": new_pw},
                     follow_redirects=False)
    assert r3.status_code == 303 and "/reset-password" not in r3.headers["location"]

def test_admin_reset_sends_a_reset_link_and_keeps_old_password_until_used(admin, app_mod):
    """The admin 'Send reset link' action emails (or, unconfigured, hands back) a
    reset link; the account's existing password keeps working until it's used."""
    uid = _make_temp_account(app_mod, "temp3@test.local")
    # user sets a real password first
    conn = st.connect(app_mod.DB)
    h, salt = auth.hash_password("RealPass12")
    st.set_admin_password(conn, uid, h, salt); conn.commit(); conn.close()
    # admin sends a reset link — SMTP isn't configured in tests, so the link
    # comes back on the redirect instead of being emailed
    r = admin.post(f"/admin/users/{uid}/reset-default", follow_redirects=False)
    assert r.status_code == 303
    assert "link=" in r.headers["location"]
    token = r.headers["location"].split("token%3D", 1)[1].split("&", 1)[0]
    conn = st.connect(app_mod.DB)
    u = st.get_admin_user_by_id(conn, uid); conn.close()
    # old password still works — nothing changes until the link is followed
    assert auth.verify_password("RealPass12", u["pw_hash"], u["salt"])
    new_pw = "AfterReset99"
    r2 = admin.post("/reset-password", data={"token": token, "password": new_pw},
                    follow_redirects=False)
    assert r2.status_code == 303
    conn = st.connect(app_mod.DB)
    u = st.get_admin_user_by_id(conn, uid); conn.close()
    assert auth.verify_password(new_pw, u["pw_hash"], u["salt"])

def test_reset_default_requires_manage_users(viewer, app_mod):
    uid = _make_temp_account(app_mod, "temp4@test.local")
    r = viewer.post(f"/admin/users/{uid}/reset-default", follow_redirects=False)
    assert r.status_code == 403

def test_admin_reset_surfaces_send_failure_detail_not_unconfigured(admin, app_mod, monkeypatch):
    """When SMTP IS configured but the actual send blows up (bad creds, network
    block, etc.), the admin must see the real error — not the generic 'email
    isn't configured' message, which would send them chasing the wrong fix."""
    import mailer
    uid = _make_temp_account(app_mod, "temp5@test.local")
    monkeypatch.setattr(mailer, "email_configured", lambda: True)
    monkeypatch.setattr(mailer, "send", lambda *a, **kw:
                        {"sent": False, "detail": "Email send failed: (535, b'bad creds')"})
    r = admin.post(f"/admin/users/{uid}/reset-default", follow_redirects=False)
    assert r.status_code == 303
    from urllib.parse import unquote
    location = unquote(r.headers["location"])
    assert "isn't configured" not in location
    assert "bad creds" in location
