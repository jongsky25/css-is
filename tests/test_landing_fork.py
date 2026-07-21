"""
Staff onboarding — Phase 3 (the / chooser ↔ /css hub fork).

The post-login landing is now a two-door chooser (Wellness | CSS); the classic
role-filtered hub moved to /css. Covers: the chooser renders both doors for
every role and shows the adopted companion, the hub is reachable at /css, the
/start opt-in still takes precedence over the chooser, and the onboarding guard
sits on / (not /css).
"""
from __future__ import annotations

import pytest

import auth
import storage as st
from tests.conftest import _auth_client


@pytest.mark.parametrize("role", ["viewer", "encoder", "section_manager", "admin"])
def test_chooser_renders_both_doors_for_every_role(app_mod, role):
    c = _auth_client(app_mod, role)
    r = c.get("/")
    assert r.status_code == 200
    assert "What would you like to do?" in r.text
    assert 'href="/wellness"' in r.text
    assert 'href="/css"' in r.text
    assert "Wellness — my 2-hour break" in r.text


def test_hub_lives_at_css(app_mod):
    c = _auth_client(app_mod, "admin")
    r = c.get("/css")
    assert r.status_code == 200
    # the role-filtered module cards + the inline search box are hub features
    assert 'id="css-modules"' in r.text
    assert "data-search" in r.text


def test_chooser_shows_the_adopted_companion(app_mod):
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    u = st.get_admin_user(conn, "encoder@test.local")
    st.set_user_avatar(conn, u["id"], "turtle", "Shelly")
    st.mark_onboarded(conn, u["id"])
    conn.close()
    c = _auth_client(app_mod, "encoder")
    r = c.get("/")
    assert "Shelly" in r.text            # the pet's name renders on the chooser


def test_start_optin_still_precedes_the_chooser(app_mod, db_path, monkeypatch):
    """With the AI landing default set to 'start', a fresh sign-in still lands on
    /start rather than the new chooser (STAFF_ONBOARDING_AVATAR_PLAN.md §7)."""
    import app as A
    import ai_core as ai
    monkeypatch.setattr(ai, "ai_available", lambda conn, feature=None: True)
    monkeypatch.setattr(ai, "mode_at_least", lambda conn, m: True)
    conn = st.connect(db_path)
    st.set_setting(conn, "ai_landing_default", "start")
    conn.close()
    from starlette.testclient import TestClient
    c = TestClient(A.app)
    r = c.post("/login", data={"username": "admin@test.local", "password": "Test1234!"},
               follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/start"
    conn = st.connect(db_path)
    st.set_setting(conn, "ai_landing_default", "hub")     # restore
    conn.close()


def test_login_without_optin_lands_on_chooser(app_mod, db_path, monkeypatch):
    import app as A
    import ai_core as ai
    monkeypatch.setattr(ai, "ai_available", lambda conn: False)
    from starlette.testclient import TestClient
    c = TestClient(A.app)
    r = c.post("/login", data={"username": "admin@test.local", "password": "Test1234!"},
               follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"


def test_css_hub_is_not_jailed_by_onboarding(app_mod):
    """The onboarding guard is on the chooser (/), not the hub: /css stays a
    reachable deep link even for an un-onboarded account."""
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    u = st.get_admin_user(conn, "manager@test.local")
    before = conn.execute("SELECT onboarded_at FROM admin_user WHERE id=?",
                          (u["id"],)).fetchone()[0]
    conn.execute("UPDATE admin_user SET onboarded_at=NULL WHERE id=?", (u["id"],))
    conn.commit()
    conn.close()
    try:
        c = _auth_client(app_mod, "section_manager")
        # chooser bounces to /welcome ...
        r = c.get("/", follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"].startswith("/welcome")
        # ... but the hub is still directly reachable
        r2 = c.get("/css", follow_redirects=False)
        assert r2.status_code == 200
    finally:
        conn = st.connect(app_mod.DB)
        conn.execute("UPDATE admin_user SET onboarded_at=? WHERE id=?", (before, u["id"]))
        conn.commit()
        conn.close()
