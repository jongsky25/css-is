"""
Staff onboarding — Phase 5 (unify the wellness mascot + the /me edit page).

The wellness hub renders the ADOPTED companion (species from the profile, growth
stage derived as before), falling back to the default plant for accounts that
never chose. The /me page lets a user re-pick or rename after onboarding.
"""
from __future__ import annotations

import re

import pytest

import auth
import storage as st
from tests.conftest import _auth_client


def _fresh(app_mod, username, kind=None, name=None, onboarded=True):
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    conn.execute("DELETE FROM admin_user WHERE username=?", (username,))
    h, salt = auth.hash_password("Test1234!")
    uid = st.create_admin_user(conn, username, h, salt, "viewer", active=True)
    if kind:
        st.set_user_avatar(conn, uid, kind, name or "Pet")
    if onboarded:
        st.mark_onboarded(conn, uid)
    conn.commit()
    conn.close()
    return uid


def _client(app_mod, uid, username):
    from starlette.testclient import TestClient
    c = TestClient(app_mod.app)
    c.cookies.set(auth.COOKIE_NAME, auth.make_token(
        {"id": uid, "username": username, "role": "viewer"}))
    return c


# --- wellness hub renders the chosen companion ------------------------------

def test_wellness_hub_renders_adopted_animal(app_mod):
    uid = _fresh(app_mod, "pe-turtle@test.local", "turtle", "Shelly")
    c = _client(app_mod, uid, "pe-turtle@test.local")
    r = c.get("/wellness")
    assert r.status_code == 200
    assert "Shelly" in r.text                 # the pet's name
    assert "fam-animal" in r.text             # rendered as an animal
    assert "Hatchling" in r.text              # animal stage name at stage 1
    conn = st.connect(app_mod.DB)
    conn.execute("DELETE FROM admin_user WHERE id=?", (uid,)); conn.commit(); conn.close()


def test_wellness_hub_defaults_to_plant_when_unchosen(app_mod):
    uid = _fresh(app_mod, "pe-none@test.local", kind=None)
    c = _client(app_mod, uid, "pe-none@test.local")
    r = c.get("/wellness")
    assert r.status_code == 200
    assert "fam-plant" in r.text              # default species
    assert "Seed" in r.text                   # plant stage name at stage 1
    conn = st.connect(app_mod.DB)
    conn.execute("DELETE FROM admin_user WHERE id=?", (uid,)); conn.commit(); conn.close()


# --- /me edit page ----------------------------------------------------------

def test_me_prefills_current_choice(app_mod):
    uid = _fresh(app_mod, "pe-me@test.local", "bonsai", "Ficus")
    c = _client(app_mod, uid, "pe-me@test.local")
    r = c.get("/me")
    assert r.status_code == 200
    assert 'value="Ficus"' in r.text          # name prefilled
    # bonsai is the checked radio, nothing else
    checked = re.findall(r'value="(\w+)"\s+checked', r.text)
    assert checked == ["bonsai"]
    conn = st.connect(app_mod.DB)
    conn.execute("DELETE FROM admin_user WHERE id=?", (uid,)); conn.commit(); conn.close()


def test_me_updates_species_and_name(app_mod):
    uid = _fresh(app_mod, "pe-upd@test.local", "plant", "Fern")
    c = _client(app_mod, uid, "pe-upd@test.local")
    r = c.post("/me", data={"avatar_kind": "cat", "avatar_name": "  Milo "},
               follow_redirects=False)
    # Saving lands on the wellness break page so the updated mascot is visible.
    assert r.status_code == 303 and r.headers["location"].startswith("/wellness")
    conn = st.connect(app_mod.DB)
    acct = st.get_admin_user_by_id(conn, uid)
    conn.execute("DELETE FROM admin_user WHERE id=?", (uid,)); conn.commit(); conn.close()
    assert acct["avatar_kind"] == "cat"
    assert acct["avatar_name"] == "Milo"      # trimmed


def test_me_requires_a_name(app_mod):
    uid = _fresh(app_mod, "pe-noname@test.local", "cat", "Milo")
    c = _client(app_mod, uid, "pe-noname@test.local")
    r = c.post("/me", data={"avatar_kind": "cat", "avatar_name": ""})
    assert r.status_code == 200
    assert "Give your companion a name" in r.text
    conn = st.connect(app_mod.DB)
    acct = st.get_admin_user_by_id(conn, uid)
    conn.execute("DELETE FROM admin_user WHERE id=?", (uid,)); conn.commit(); conn.close()
    assert acct["avatar_name"] == "Milo"      # unchanged


def test_me_rejects_unknown_species(app_mod):
    uid = _fresh(app_mod, "pe-bad@test.local", "cat", "Milo")
    c = _client(app_mod, uid, "pe-bad@test.local")
    r = c.post("/me", data={"avatar_kind": "dragon", "avatar_name": "Smaug"})
    assert r.status_code == 200
    assert "pick a companion" in r.text.lower()
    conn = st.connect(app_mod.DB)
    conn.execute("DELETE FROM admin_user WHERE id=?", (uid,)); conn.commit(); conn.close()


def test_me_is_discoverable_in_search_index(app_mod):
    c = _auth_client(app_mod, "viewer")
    r = c.get("/css")                         # SEARCH_INDEX is injected on every page
    assert '"url": "/me"' in r.text or '"url":"/me"' in r.text
