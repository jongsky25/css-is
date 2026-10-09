"""
The / landing page ↔ /css hub fork.

/ is the Office Connect Team View: how your team is doing across all three
modules, with a personal view a tap away and the three doors still on it. The
classic role-filtered hub stayed at /css. Covers: the landing renders for every
role and still carries all three doors and the adopted companion, the Team|Me
toggle works, the hub is reachable at /css, the /start opt-in still takes
precedence, and the onboarding guard still sits on / (not /css).
"""
from __future__ import annotations

import pytest

import auth
import storage as st
from tests.conftest import _auth_client, in_the_directory as _in_the_directory


@pytest.mark.parametrize("role", ["viewer", "encoder", "section_manager", "admin"])
def test_landing_renders_all_three_doors_for_every_role(app_mod, role):
    """The doors are what the Team View replaced a chooser with — they must not
    regress. Nothing on this page may become harder to reach than it was."""
    c = _auth_client(app_mod, role)
    r = c.get("/")
    assert r.status_code == 200
    assert 'href="/wellness"' in r.text
    assert 'href="/work-arrangement"' in r.text
    assert 'href="/css"' in r.text
    assert "Wellness — my 2-hour break" in r.text


@pytest.mark.parametrize("role", ["viewer", "encoder", "section_manager", "admin"])
def test_personal_view_renders_for_every_role(app_mod, role):
    mine = _auth_client(app_mod, role).get("/?view=me").text
    assert "Activities you spoke at" in mine
    assert "Your wellness break" in mine


def test_team_toggle_appears_only_when_there_is_a_team(app_mod):
    """The toggle is a real link, not JS. It is offered only to someone who HAS
    a team: an account with no directory link resolves to no team at all, and
    showing it a Team tab that could only ever be empty would be a lie."""
    with _in_the_directory(app_mod, "admin@test.local"):
        admin = _auth_client(app_mod, "admin").get("/").text
        assert ">Team</a>" in admin                    # in the directory, so a team

    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    u = st.get_admin_user(conn, "viewer@test.local")
    unlinked = conn.execute("SELECT rp_id FROM admin_user WHERE id=?",
                            (u["id"],)).fetchone()[0] is None
    conn.close()
    if unlinked:
        page = _auth_client(app_mod, "viewer").get("/").text
        assert ">Team</a>" not in page                 # no Team tab; Me and Calendar stay
        assert "directory record" in page              # the explainer instead


def test_an_admin_role_alone_is_not_a_team(app_mod):
    """The role used to be a shortcut to a bureau-wide roster. It is not one now:
    an admin with no directory record gets the personal view and the explainer,
    the same as any other unlinked account."""
    page = _auth_client(app_mod, "admin").get("/").text
    assert ">Team</a>" not in page
    assert "directory record" in page


def test_landing_never_calls_activities_attendance(app_mod):
    """There is no staff->activity attendance relation in this schema, so the
    panel must not imply one. The disclaimer is load-bearing copy."""
    html = _auth_client(app_mod, "admin").get("/").text
    assert "Attendance isn" in html                    # "Attendance isn't recorded here"
    assert "you attended" not in html.lower()


def test_hub_lives_at_css(app_mod):
    c = _auth_client(app_mod, "admin")
    r = c.get("/css")
    assert r.status_code == 200
    # the role-filtered module cards + the CSS-scoped search box are hub features
    assert 'id="css-modules"' in r.text
    assert "data-search" in r.text


def test_landing_shows_the_adopted_companion(app_mod):
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    u = st.get_admin_user(conn, "encoder@test.local")
    st.set_user_avatar(conn, u["id"], "turtle", "Shelly")
    st.mark_onboarded(conn, u["id"])
    conn.close()
    c = _auth_client(app_mod, "encoder")
    r = c.get("/")
    assert "Shelly" in r.text            # the pet's name renders on the landing page


def test_start_optin_still_precedes_the_chooser(app_mod, db_path, monkeypatch):
    """With the AI landing default set to 'start', a fresh sign-in still lands on
    /start rather than the landing page (STAFF_ONBOARDING_AVATAR_PLAN.md §7)."""
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


def test_login_without_optin_lands_on_the_landing_page(app_mod, db_path, monkeypatch):
    import app as A
    import ai_core as ai
    monkeypatch.setattr(ai, "ai_available", lambda conn: False)
    from starlette.testclient import TestClient
    c = TestClient(A.app)
    r = c.post("/login", data={"username": "admin@test.local", "password": "Test1234!"},
               follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"


def test_css_hub_is_not_jailed_by_onboarding(app_mod):
    """The onboarding guard is on the landing page (/), not the hub: /css stays a
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
        # the landing page bounces to /welcome ...
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


def test_team_view_renders_all_three_panels(app_mod):
    """A viewer the directory places in a section has a team, so every team panel
    has something to draw. Guards the markup, not just the payload: the data
    layer is unit-tested in test_office_connect.py, but nothing there proves the
    template renders it."""
    with _in_the_directory(app_mod, "admin@test.local", "encoder@test.local"):
        html = _auth_client(app_mod, "admin").get("/").text

    assert "Wellness this week" in html
    assert "Alternative Work Arrangement" in html
    assert "Activities your team ran or spoke at" in html
    assert 'class="faces"' in html                     # the people wall
    assert 'class="oc-bar"' in html                    # the stacked filing bar
    assert 'class="oc-seg"' in html                    # the Team|Me toggle


def test_landing_uses_tokens_not_hardcoded_colour(app_mod):
    """3 themes x 6 accents x 2 densities: a literal hex in this page's own
    markup would be wrong in nearly every combination. (The shared avatar art
    has its own palette and is excluded — this checks the page we wrote.)"""
    import re
    html = _auth_client(app_mod, "admin").get("/").text
    # Just this page's own <style> block — it opens with the .oc-hero rule.
    # The shared avatar art and the face partial ship their own blocks before it.
    start = html.index(".oc-hero {")
    own = html[start:html.index("</style>", start)]
    assert not re.search(r"#[0-9a-fA-F]{3,6}\b", own), \
        f"hardcoded colour in the landing page's own CSS: {own[:400]}"
