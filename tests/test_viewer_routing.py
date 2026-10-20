"""
Staff onboarding — Phase 4 (viewer routing on the CSS door).

A plain viewer linked to a usable directory person lands on their OWN person
profile first (with their section one tap away via the banner); viewers with no
usable record, and every non-viewer role, go to the hub. Covers _css_entry_for's
branches, the chooser CSS-card target, and the self-banner on the person page.
"""
from __future__ import annotations

from tests.conftest import session_token
import pytest

import app as A
import auth
import dashboard_insights as di
import storage as st
from tests.conftest import _auth_client


def _renderable_person(app_mod):
    """First internal, visible person whose report actually renders (has rating
    data) AND is not already linked to an account — the person page bounces to
    the grid for anyone with zero ratings, and admin_user.rp_id is UNIQUE, so the
    self-banner fixture needs a rendering person we can freely link. None if
    there isn't one (the tests skip)."""
    conn = st.connect(app_mod.DB)
    try:
        st.init_db(conn)
        A.DB = app_mod.DB
        A._atoms_state.update({"key": None, "df": None, "built": 0.0})
        atoms = A.get_atoms(conn)
        people = st.list_resource_persons(conn)
        linked = {a["rp_id"] for a in st.list_admin_users(conn) if a["rp_id"]}
    finally:
        conn.close()
    for p in people:
        if (p["is_internal"] and not p["hidden_public"]
                and p["id"] not in linked and di.person_card(atoms, p)):
            return p
    return None


@pytest.fixture()
def routed_people(app_mod):
    """A section with: a linked visible viewer (self-routing), a linked viewer on
    a HIDDEN person (must fall back), and an unlinked viewer. Cleaned up after."""
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    conn.execute("DELETE FROM admin_user WHERE username LIKE 'vr-%@test.local'")
    conn.execute("DELETE FROM resource_person WHERE name LIKE 'VR-Test %'")
    conn.execute("DELETE FROM org_unit WHERE path = 'TEST/VR/Sec'")
    unit = conn.execute(
        "INSERT INTO org_unit(name, short_name, level, path) "
        "VALUES ('VR Sec','VRSec','section','TEST/VR/Sec')").lastrowid
    rp = conn.execute("INSERT INTO resource_person(name, is_internal, org_unit_id) "
                      "VALUES ('VR-Test Vince', 1, ?)", (unit,)).lastrowid
    hrp = conn.execute("INSERT INTO resource_person(name, is_internal, org_unit_id, "
                       "hidden_public) VALUES ('VR-Test Ghost', 1, ?, 1)", (unit,)).lastrowid
    h, salt = auth.hash_password("Test1234!")
    linked = st.create_admin_user(conn, "vr-linked@test.local", h, salt, "viewer",
                                  active=True, rp_id=rp)
    hidden = st.create_admin_user(conn, "vr-hidden@test.local", h, salt, "viewer",
                                  active=True, rp_id=hrp)
    loner = st.create_admin_user(conn, "vr-loner@test.local", h, salt, "viewer", active=True)
    for uid in (linked, hidden, loner):
        st.set_user_avatar(conn, uid, "plant", "Fern")
        st.mark_onboarded(conn, uid)
    conn.commit()
    conn.close()
    yield {"unit": unit, "rp": rp, "hrp": hrp,
           "linked": linked, "hidden": hidden, "loner": loner}
    conn = st.connect(app_mod.DB)
    conn.execute("DELETE FROM admin_user WHERE username LIKE 'vr-%@test.local'")
    conn.execute("DELETE FROM resource_person WHERE id IN (?,?)", (rp, hrp))
    conn.execute("DELETE FROM org_unit WHERE id=?", (unit,))
    conn.commit()
    conn.close()


def _entry(app_mod, uid, role="viewer"):
    conn = st.connect(app_mod.DB)
    try:
        return A._css_entry_for({"id": uid, "role": role}, conn)
    finally:
        conn.close()


# --- _css_entry_for branches ------------------------------------------------

def test_linked_visible_viewer_routes_to_own_profile(app_mod, routed_people):
    assert _entry(app_mod, routed_people["linked"]) == \
        f"/dashboard/people/{routed_people['rp']}"


def test_viewer_on_hidden_person_falls_back_to_hub(app_mod, routed_people):
    assert _entry(app_mod, routed_people["hidden"]) == "/css"


def test_unlinked_viewer_falls_back_to_hub(app_mod, routed_people):
    assert _entry(app_mod, routed_people["loner"]) == "/css"


def test_non_viewer_always_goes_to_hub(app_mod, routed_people):
    # even a linked account, if it isn't a viewer, lands on the hub
    assert _entry(app_mod, routed_people["linked"], role="section_manager") == "/css"
    assert _entry(app_mod, routed_people["linked"], role="admin") == "/css"


# --- chooser card + self banner ---------------------------------------------

def test_chooser_css_card_points_to_own_profile(app_mod, routed_people):
    from starlette.testclient import TestClient
    c = TestClient(app_mod.app)
    c.cookies.set(auth.COOKIE_NAME, session_token(
        {"id": routed_people["linked"], "username": "vr-linked@test.local", "role": "viewer"}))
    r = c.get("/")
    assert r.status_code == 200
    assert f'href="/dashboard/people/{routed_people["rp"]}"' in r.text


@pytest.fixture()
def linked_to_rendered(app_mod):
    """A viewer account linked to a real, renderable seed person (so the person
    page doesn't bounce). Yields (uid, person); unlinks the account after."""
    person = _renderable_person(app_mod)
    if not person:
        pytest.skip("no free renderable internal person in the seed data")
    conn = st.connect(app_mod.DB)
    try:
        conn.execute("DELETE FROM admin_user WHERE username='vr-self@test.local'")
        conn.commit()
        h, salt = auth.hash_password("Test1234!")
        uid = st.create_admin_user(conn, "vr-self@test.local", h, salt, "viewer",
                                   active=True, rp_id=person["id"])
        st.mark_onboarded(conn, uid)
    finally:
        conn.close()
    yield uid, person
    conn = st.connect(app_mod.DB)
    try:
        conn.execute("DELETE FROM admin_user WHERE id=?", (uid,))
        conn.commit()
    finally:
        conn.close()


def test_self_banner_shows_when_viewing_own_profile(app_mod, linked_to_rendered):
    uid, person = linked_to_rendered
    from starlette.testclient import TestClient
    c = TestClient(app_mod.app)
    c.cookies.set(auth.COOKIE_NAME, session_token(
        {"id": uid, "username": "vr-self@test.local", "role": "viewer"}))
    r = c.get(f"/dashboard/people/{person['id']}")
    assert r.status_code == 200
    assert "This is your profile" in r.text
    assert f"/dashboard/teams/{person['org_path']}" in r.text


def test_no_self_banner_when_viewing_someone_else(app_mod, linked_to_rendered):
    uid, person = linked_to_rendered
    from starlette.testclient import TestClient
    c = TestClient(app_mod.app)
    # a DIFFERENT viewer (the seeded one, unlinked) looking at this profile
    seeded = _auth_client(app_mod, "viewer")
    r = seeded.get(f"/dashboard/people/{person['id']}")
    assert r.status_code == 200
    assert "This is your profile" not in r.text
