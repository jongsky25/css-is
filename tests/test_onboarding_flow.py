"""
Staff onboarding — Phase 2 (the /welcome flow + login/landing redirects).

Covers: first sign-in routing into /welcome, the reset-before-onboarding
ordering, ?next= carried through onboarding, POST validation + persistence,
the no-directory-link degradation (avatar step only), and the landing guard
that stops a half-finished onboarding being skipped by URL.
"""
from __future__ import annotations

from tests.conftest import session_token
import pytest

import auth
import storage as st
from tests.conftest import _auth_client


@pytest.fixture()
def fresh_viewer(app_mod):
    """The seeded viewer as if it were their first sign-in after this update:
    onboarded_at reset to NULL. The DB is session-scoped and shared, so the
    prior onboarded state is snapshotted and RESTORED on teardown — otherwise
    later hub tests using the same seeded account would find it un-onboarded and
    get bounced to /welcome."""
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    u = st.get_admin_user(conn, "viewer@test.local")
    before = conn.execute(
        "SELECT onboarded_at, avatar_kind, avatar_name FROM admin_user WHERE id=?",
        (u["id"],)).fetchone()
    conn.execute("UPDATE admin_user SET onboarded_at=NULL, avatar_kind=NULL, "
                 "avatar_name=NULL WHERE id=?", (u["id"],))
    conn.commit()
    conn.close()
    yield u["id"]
    conn = st.connect(app_mod.DB)
    conn.execute("UPDATE admin_user SET onboarded_at=?, avatar_kind=?, avatar_name=? "
                 "WHERE id=?", (before[0], before[1], before[2], u["id"]))
    conn.commit()
    conn.close()


def _client(app_mod, username):
    from starlette.testclient import TestClient
    c = TestClient(app_mod.app)
    conn = st.connect(app_mod.DB)
    u = st.get_admin_user(conn, username)
    conn.close()
    c.cookies.set(auth.COOKIE_NAME, session_token(
        {"id": u["id"], "username": u["username"], "role": u["role"]}))
    return c


# --- landing guard ----------------------------------------------------------

def test_home_redirects_unonboarded_to_welcome(app_mod, fresh_viewer):
    c = _client(app_mod, "viewer@test.local")
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/welcome")


def test_welcome_renders_picker_with_all_species(app_mod, fresh_viewer):
    c = _client(app_mod, "viewer@test.local")
    r = c.get("/welcome")
    assert r.status_code == 200
    assert "Adopt your companion" in r.text
    for kind in ("plant", "cactus", "bonsai", "cat", "bird", "turtle"):
        assert f'value="{kind}"' in r.text
    assert "Name your pet" in r.text


# --- POST: persistence + validation -----------------------------------------

def test_post_welcome_saves_and_marks_onboarded(app_mod, fresh_viewer):
    c = _client(app_mod, "viewer@test.local")
    r = c.post("/welcome", data={"avatar_kind": "turtle", "avatar_name": "  Shelly ",
                                 "next": "/"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    conn = st.connect(app_mod.DB)
    acct = st.get_admin_user_by_id(conn, fresh_viewer)
    conn.close()
    assert acct["avatar_kind"] == "turtle"
    assert acct["avatar_name"] == "Shelly"          # trimmed
    assert acct["onboarded_at"]


def test_post_welcome_requires_name(app_mod, fresh_viewer):
    c = _client(app_mod, "viewer@test.local")
    r = c.post("/welcome", data={"avatar_kind": "cat", "avatar_name": "", "next": "/"})
    assert r.status_code == 200
    assert "Give your companion a name" in r.text
    # still not onboarded
    conn = st.connect(app_mod.DB)
    assert st.get_admin_user_by_id(conn, fresh_viewer)["onboarded_at"] is None
    conn.close()


def test_post_welcome_rejects_unknown_species(app_mod, fresh_viewer):
    c = _client(app_mod, "viewer@test.local")
    r = c.post("/welcome", data={"avatar_kind": "dragon", "avatar_name": "Smaug", "next": "/"})
    assert r.status_code == 200
    assert "pick a companion" in r.text.lower()


def test_deep_links_are_not_jailed_by_onboarding(app_mod, fresh_viewer):
    """Onboarding is encouraged, not a jail: only the landing (`/`) guards, so a
    direct deep link stays usable even before onboarding is finished."""
    c = _client(app_mod, "viewer@test.local")
    r = c.get("/wellness", follow_redirects=False)
    assert r.status_code == 200


def test_login_next_is_carried_through_onboarding(app_mod, fresh_viewer):
    """A ?next= that survives login is preserved across the one-time onboarding
    and honored right after (STAFF_ONBOARDING_AVATAR_PLAN.md §7)."""
    from starlette.testclient import TestClient
    c = TestClient(app_mod.app)
    r = c.post("/login", data={"username": "viewer@test.local", "password": "Test1234!",
                               "next": "/wellness"}, follow_redirects=False)
    assert r.status_code == 303
    loc = r.headers["location"]
    assert loc.startswith("/welcome?next=")
    from urllib.parse import parse_qs, urlparse
    assert parse_qs(urlparse(loc).query)["next"] == ["/wellness"]
    # finishing onboarding honors the carried next
    c.cookies.set(auth.COOKIE_NAME, r.cookies[auth.COOKIE_NAME])
    r2 = c.post("/welcome", data={"avatar_kind": "bird", "avatar_name": "Pip",
                                  "next": "/wellness"}, follow_redirects=False)
    assert r2.status_code == 303 and r2.headers["location"] == "/wellness"


def test_open_redirect_next_is_neutralized(app_mod, fresh_viewer):
    c = _client(app_mod, "viewer@test.local")
    r = c.post("/welcome", data={"avatar_kind": "cat", "avatar_name": "Milo",
                                 "next": "//evil.example.com"}, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"


# --- login redirect ordering (reset before onboarding) ----------------------

def test_login_routes_first_timer_to_welcome(app_mod, fresh_viewer):
    from starlette.testclient import TestClient
    c = TestClient(app_mod.app)
    r = c.post("/login", data={"username": "viewer@test.local", "password": "Test1234!"},
               follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/welcome")


def test_temp_password_reset_precedes_onboarding(app_mod):
    """An account on a temporary password is sent to reset FIRST — onboarding
    only intervenes after they've set a real password and signed in again."""
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    h, salt = auth.hash_password("Temp1234!")
    st.create_admin_user(conn, "onb-temp@test.local", h, salt, "viewer",
                         created_by="test", active=True, must_change=True)
    conn.commit()
    conn.close()
    from starlette.testclient import TestClient
    c = TestClient(app_mod.app)
    r = c.post("/login", data={"username": "onb-temp@test.local", "password": "Temp1234!"},
               follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"].startswith("/reset-password")   # NOT /welcome
    # cleanup
    conn = st.connect(app_mod.DB)
    conn.execute("DELETE FROM admin_user WHERE username='onb-temp@test.local'")
    conn.commit()
    conn.close()


def test_already_onboarded_lands_normally(app_mod):
    """A viewer who has completed onboarding is NOT bounced to /welcome."""
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    u = st.get_admin_user(conn, "encoder@test.local")
    st.set_user_avatar(conn, u["id"], "plant", "Fern")
    st.mark_onboarded(conn, u["id"])
    conn.close()
    c = _client(app_mod, "encoder@test.local")
    r = c.get("/", follow_redirects=False)
    assert r.status_code == 200
