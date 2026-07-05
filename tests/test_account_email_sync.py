"""Editing a linked staff member's directory email must re-point their account's
login email (admin_user.username) — otherwise activate/reset/sign-in keep using
the stale email captured when the account was first created.
"""
from __future__ import annotations
import storage as st, auth


def _internal_with_account(conn, *, name, email, role="viewer"):
    """An internal staff person plus a linked admin account on `email`."""
    rp_id = st.add_rp(conn, name, is_internal=True, email=email)
    h, salt = auth.hash_password(auth.DEFAULT_PASSWORD)
    st.create_admin_user(conn, email, h, salt, role, created_by="test",
                         rp_id=rp_id, active=True, must_change=True)
    return rp_id


def _update(admin, rp_id, **fields):
    return admin.post(f"/directory/person/{rp_id}/update",
                      data={"confirm": "1", **fields}, follow_redirects=False)


def test_email_edit_repoints_account_login(admin, app_mod):
    conn = st.connect(app_mod.DB)
    try:
        rp_id = _internal_with_account(conn, name="Nina Sync", email="old@doh.local")
    finally:
        conn.close()

    r = _update(admin, rp_id, name="Nina Sync", email="new@doh.local")
    assert r.status_code == 303

    conn = st.connect(app_mod.DB)
    try:
        acct = st.get_admin_user_by_rp(conn, rp_id)
        assert acct["username"] == "new@doh.local"     # login follows the directory
        assert st.get_admin_user(conn, "old@doh.local") is None
    finally:
        conn.close()


def test_email_collision_leaves_login_unchanged(admin, app_mod):
    conn = st.connect(app_mod.DB)
    try:
        keep = _internal_with_account(conn, name="Keeper", email="taken@doh.local")
        mover = _internal_with_account(conn, name="Mover", email="mover@doh.local")
    finally:
        conn.close()

    # Try to move `mover`'s email onto the one `keep` already owns.
    r = _update(admin, mover, name="Mover", email="taken@doh.local")
    assert r.status_code == 303
    assert "err=" in r.headers["location"]              # warning surfaced

    conn = st.connect(app_mod.DB)
    try:
        assert st.get_admin_user_by_rp(conn, mover)["username"] == "mover@doh.local"
        assert st.get_admin_user_by_rp(conn, keep)["username"] == "taken@doh.local"
    finally:
        conn.close()


def test_clearing_email_keeps_existing_login(admin, app_mod):
    conn = st.connect(app_mod.DB)
    try:
        rp_id = _internal_with_account(conn, name="Cleared", email="keep@doh.local")
    finally:
        conn.close()

    # Blanking the directory email must not strip the account's login.
    r = _update(admin, rp_id, name="Cleared", email="")
    assert r.status_code == 303

    conn = st.connect(app_mod.DB)
    try:
        assert st.get_admin_user_by_rp(conn, rp_id)["username"] == "keep@doh.local"
    finally:
        conn.close()
