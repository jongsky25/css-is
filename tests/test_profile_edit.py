"""
Staff onboarding — Phase 5 (unify the wellness mascot + the /me edit page).

The wellness hub renders the ADOPTED companion (species from the profile, growth
stage derived as before), falling back to the default plant for accounts that
never chose. The /me page lets a user re-pick or rename after onboarding.
"""
from __future__ import annotations

from tests.conftest import session_token
import base64
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
    c.cookies.set(auth.COOKIE_NAME, session_token(
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
    # Saving closes the profile — lands back on the home chooser, not /me.
    assert r.status_code == 303 and r.headers["location"].startswith("/?msg=")
    conn = st.connect(app_mod.DB)
    acct = st.get_admin_user_by_id(conn, uid)
    conn.execute("DELETE FROM admin_user WHERE id=?", (uid,)); conn.commit(); conn.close()
    assert acct["avatar_kind"] == "cat"
    assert acct["avatar_name"] == "Milo"      # trimmed


# --- profile photo for every viewer + editable designation ------------------

# A 1x1 transparent PNG as a data URL — the smallest valid image upload.
_PNG_DATA_URL = (
    "data:image/png;base64,"
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg=="
)


def test_unlinked_viewer_can_set_own_photo(app_mod):
    """An account with no directory person (rp_id is NULL) can still upload a
    profile photo — it lands on the account row and is served from /me/photo."""
    uid = _fresh(app_mod, "pe-photo@test.local", "cat", "Milo")
    c = _client(app_mod, uid, "pe-photo@test.local")
    # The photo panel is offered even without a linked directory person.
    assert 'name="photo_data"' in c.get("/me").text
    r = c.post("/me", data={"avatar_kind": "cat", "avatar_name": "Milo",
                            "photo_data": _PNG_DATA_URL}, follow_redirects=False)
    assert r.status_code == 303
    conn = st.connect(app_mod.DB)
    stored = st.get_user_photo(conn, uid)
    conn.close()
    assert stored is not None and stored[1] == "image/png"
    # And the account's own photo is served back to it.
    assert c.get("/me/photo").status_code == 200
    conn = st.connect(app_mod.DB)
    conn.execute("DELETE FROM admin_user WHERE id=?", (uid,)); conn.commit(); conn.close()


def test_me_saves_designation(app_mod):
    uid = _fresh(app_mod, "pe-desig@test.local", "cat", "Milo")
    c = _client(app_mod, uid, "pe-desig@test.local")
    c.post("/me", data={"avatar_kind": "cat", "avatar_name": "Milo",
                        "designation": "  Section Head "}, follow_redirects=False)
    conn = st.connect(app_mod.DB)
    prof = st.get_user_profile(conn, uid)
    conn.close()
    assert prof["designation"] == "Section Head"   # trimmed and persisted
    # And it renders prefilled on the profile page for editing.
    assert 'value="Section Head"' in c.get("/me").text
    conn = st.connect(app_mod.DB)
    conn.execute("DELETE FROM admin_user WHERE id=?", (uid,)); conn.commit(); conn.close()


def test_me_cannot_change_linked_directory_designation(app_mod):
    """Directory titles drive authority and cannot be edited through /me."""
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    conn.execute("DELETE FROM admin_user WHERE username=?", ("pe-link@test.local",))
    rp_id = st.add_rp(conn, "Linked Staffer", True, designation="Old Title")
    h, salt = auth.hash_password("Test1234!")
    uid = st.create_admin_user(conn, "pe-link@test.local", h, salt, "viewer",
                               active=True, rp_id=rp_id)
    st.set_user_avatar(conn, uid, "cat", "Milo")
    st.mark_onboarded(conn, uid)
    conn.commit(); conn.close()
    c = _client(app_mod, uid, "pe-link@test.local")

    assert 'readonly' in c.get('/me').text.split('id="designation"', 1)[1].split('>', 1)[0]
    # A forged field cannot change authority, even if a stale client sends it.
    c.post("/me", data={"avatar_kind": "cat", "avatar_name": "Milo",
                        "designation": "Section Head"}, follow_redirects=False)
    conn = st.connect(app_mod.DB)
    assert st.get_rp(conn, rp_id)["designation"] == "Old Title"
    assert st.get_user_profile(conn, uid)["designation"] == "Old Title"
    conn.close()

    # Clearing the field cannot erase an administrator-maintained title either.
    c.post("/me", data={"avatar_kind": "cat", "avatar_name": "Milo",
                        "designation": ""}, follow_redirects=False)
    conn = st.connect(app_mod.DB)
    assert st.get_rp(conn, rp_id)["designation"] == "Old Title"
    conn.execute("DELETE FROM admin_user WHERE id=?", (uid,))
    conn.execute("DELETE FROM resource_person WHERE id=?", (rp_id,))
    conn.commit(); conn.close()


# --- the drawn signature ----------------------------------------------------

def test_me_offers_a_signature_pad(app_mod):
    uid = _fresh(app_mod, "pe-sigpad@test.local", "cat", "Milo")
    c = _client(app_mod, uid, "pe-sigpad@test.local")
    r = c.get("/me")
    assert r.status_code == 200
    assert 'name="signature_data"' in r.text and 'id="sigCanvas"' in r.text
    # Without this the first finger stroke scrolls the page instead of drawing,
    # and nothing else in the suite would notice.
    assert "touch-action:none" in r.text
    conn = st.connect(app_mod.DB)
    conn.execute("DELETE FROM admin_user WHERE id=?", (uid,)); conn.commit(); conn.close()


def test_unlinked_viewer_can_draw_their_signature(app_mod):
    """No directory row, no admin, no file to upload: the drawing lands on the
    account and comes back only to its owner."""
    uid = _fresh(app_mod, "pe-sig@test.local", "cat", "Milo")
    c = _client(app_mod, uid, "pe-sig@test.local")
    assert c.get("/me/signature.png").status_code == 404      # nothing on file yet

    r = c.post("/me", data={"avatar_kind": "cat", "avatar_name": "Milo",
                            "signature_data": _PNG_DATA_URL}, follow_redirects=False)
    assert r.status_code == 303
    conn = st.connect(app_mod.DB)
    stored = st.get_user_signature(conn, uid)
    conn.close()
    assert stored is not None and stored[1] == "image/png"
    r = c.get("/me/signature.png")
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert r.headers["cache-control"] == "no-store"           # sensitive: never cached

    # Saving the profile again without drawing must NOT wipe it.
    c.post("/me", data={"avatar_kind": "cat", "avatar_name": "Milo"},
           follow_redirects=False)
    conn = st.connect(app_mod.DB)
    assert st.get_user_signature(conn, uid) is not None
    conn.execute("DELETE FROM admin_user WHERE id=?", (uid,)); conn.commit(); conn.close()


def test_me_rejects_a_signature_that_is_not_a_png(app_mod):
    """The declared mime is the client's word; the magic bytes are not."""
    uid = _fresh(app_mod, "pe-sigbad@test.local", "cat", "Milo")
    c = _client(app_mod, uid, "pe-sigbad@test.local")
    c.post("/me", data={"avatar_kind": "cat", "avatar_name": "Milo",
                        "signature_data": "data:image/png;base64,"
                                          + base64.b64encode(b"\xff\xd8\xff not a png").decode()},
           follow_redirects=False)
    conn = st.connect(app_mod.DB)
    assert st.get_user_signature(conn, uid) is None
    conn.execute("DELETE FROM admin_user WHERE id=?", (uid,)); conn.commit(); conn.close()


def test_linked_account_signs_on_its_directory_row(app_mod):
    """A linked account has ONE signature: the directory field certificates
    already sign with. Drawing on /me fills it; the remove box clears it."""
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    conn.execute("DELETE FROM admin_user WHERE username=?", ("pe-siglink@test.local",))
    rp_id = st.add_rp(conn, "Signing Staffer", True, designation="Section Head")
    h, salt = auth.hash_password("Test1234!")
    uid = st.create_admin_user(conn, "pe-siglink@test.local", h, salt, "viewer",
                               active=True, rp_id=rp_id)
    st.set_user_avatar(conn, uid, "cat", "Milo")
    st.mark_onboarded(conn, uid)
    conn.commit(); conn.close()
    c = _client(app_mod, uid, "pe-siglink@test.local")

    c.post("/me", data={"avatar_kind": "cat", "avatar_name": "Milo",
                        "signature_data": _PNG_DATA_URL}, follow_redirects=False)
    conn = st.connect(app_mod.DB)
    assert st.get_rp_signature(conn, rp_id) is not None       # the shared field
    assert st.get_user_signature(conn, uid) is None           # not the account's
    assert st.get_user_profile(conn, uid)["has_signature"] is True
    conn.close()
    assert c.get("/me/signature.png").status_code == 200

    c.post("/me", data={"avatar_kind": "cat", "avatar_name": "Milo",
                        "remove_signature": "1"}, follow_redirects=False)
    conn = st.connect(app_mod.DB)
    assert st.get_rp_signature(conn, rp_id) is None
    assert c.get("/me/signature.png").status_code == 404
    conn.execute("DELETE FROM admin_user WHERE id=?", (uid,))
    conn.execute("DELETE FROM resource_person WHERE id=?", (rp_id,))
    conn.commit(); conn.close()


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
