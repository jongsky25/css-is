"""
Avatar companions — care/mood layer + the 15-species art surface.

Covers the derived mood (avatar_mood), the once-per-cooldown counting rule
(record_avatar_care), the POST /avatar/care endpoint, and a render sweep of
every species × stage through the app's real Jinja environment (the art is
inline SVG, so a template typo would 500 every page that draws a companion).
"""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest

import storage as st


@pytest.fixture()
def conn(app_mod):
    c = st.connect(app_mod.DB)
    st.init_db(c)
    yield c
    c.close()


def _mk_account(conn, username):
    return st.create_admin_user(conn, username, "h", "s", "viewer",
                                created_by="test", active=True)


NOW = datetime(2026, 7, 21, 12, 0, 0)


# --- mood derivation ---------------------------------------------------------

def test_mood_thresholds():
    assert st.avatar_mood(NOW.isoformat(), now=NOW) == "happy"
    assert st.avatar_mood((NOW - timedelta(hours=23)).isoformat(), now=NOW) == "happy"
    assert st.avatar_mood((NOW - timedelta(hours=25)).isoformat(), now=NOW) == "okay"
    assert st.avatar_mood((NOW - timedelta(hours=71)).isoformat(), now=NOW) == "okay"
    assert st.avatar_mood((NOW - timedelta(hours=73)).isoformat(), now=NOW) == "droopy"


def test_mood_never_raises_on_garbage():
    # a never-cared-for or hand-edited stamp must degrade, not error
    assert st.avatar_mood(None) == "droopy"
    assert st.avatar_mood("") == "droopy"
    assert st.avatar_mood("not-a-date") == "droopy"


def test_care_verb_by_family():
    assert st.avatar_care_verb("plant") == "water"
    assert st.avatar_care_verb("fern") == "water"
    assert st.avatar_care_verb("dog") == "feed"
    assert st.avatar_care_verb("bat") == "feed"
    # unknown species fall back through avatar_family to the default (a plant)
    assert st.avatar_care_verb("dragon") == "water"


# --- record_avatar_care cooldown ---------------------------------------------

def test_record_care_counts_then_cools_down(conn):
    uid = _mk_account(conn, "care-cd@test.local")
    first = st.record_avatar_care(conn, uid, now=NOW)
    assert first["counted"] is True
    assert first["mood"] == "happy"
    stamp = first["last_care_at"]

    # inside the cooldown: not counted, timestamp untouched
    again = st.record_avatar_care(conn, uid, now=NOW + timedelta(hours=1))
    assert again["counted"] is False
    assert again["last_care_at"] == stamp

    # after the cooldown: counted again, timestamp moves
    later = st.record_avatar_care(
        conn, uid, now=NOW + timedelta(hours=st.AVATAR_CARE_COOLDOWN_HOURS, minutes=1))
    assert later["counted"] is True
    assert later["last_care_at"] != stamp


def test_record_care_unknown_account(conn):
    res = st.record_avatar_care(conn, 999999, now=NOW)
    assert res["counted"] is False


def test_profile_carries_mood(conn):
    uid = _mk_account(conn, "care-prof@test.local")
    assert st.get_user_profile(conn, uid)["avatar_mood"] == "droopy"
    st.record_avatar_care(conn, uid)
    assert st.get_user_profile(conn, uid)["avatar_mood"] == "happy"


# --- POST /avatar/care -------------------------------------------------------

def test_care_endpoint_requires_auth(client):
    r = client.post("/avatar/care", data={"action": "feed"}, follow_redirects=False)
    assert r.status_code in (302, 303, 401)


def test_care_endpoint_counts_once(viewer, app_mod):
    conn = st.connect(app_mod.DB)
    conn.execute("UPDATE admin_user SET avatar_kind='dog', avatar_last_care_at=NULL "
                 "WHERE username='viewer@test.local'")
    conn.commit(); conn.close()

    r = viewer.post("/avatar/care", data={"action": "feed"})
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True and body["counted"] is True and body["mood"] == "happy"

    r2 = viewer.post("/avatar/care", data={"action": "feed"})
    assert r2.json()["counted"] is False          # inside the 6h cooldown


def test_care_endpoint_rejects_wrong_action(viewer, app_mod):
    conn = st.connect(app_mod.DB)
    conn.execute("UPDATE admin_user SET avatar_kind='dog' WHERE username='viewer@test.local'")
    conn.commit(); conn.close()
    r = viewer.post("/avatar/care", data={"action": "water"})   # you don't water a dog
    assert r.status_code == 400
    assert r.json()["error"] == "wrong_action"


def test_care_endpoint_action_optional(viewer, app_mod):
    conn = st.connect(app_mod.DB)
    conn.execute("UPDATE admin_user SET avatar_kind='fern' WHERE username='viewer@test.local'")
    conn.commit(); conn.close()
    r = viewer.post("/avatar/care", data={})
    assert r.status_code == 200 and r.json()["ok"] is True


# --- rendered surfaces -------------------------------------------------------

def test_wellness_hub_renders_care_ui(viewer, app_mod):
    conn = st.connect(app_mod.DB)
    conn.execute("UPDATE admin_user SET avatar_kind='owl', avatar_name='Hooty' "
                 "WHERE username='viewer@test.local'")
    conn.commit(); conn.close()
    r = viewer.get("/wellness")
    assert r.status_code == 200
    for marker in ("av-play", "data-mood=", "av-care-btn", "avatars.js",
                   'data-kind="owl"', "data-drag"):
        assert marker in r.text, f"missing {marker} on /wellness"


def test_me_picker_offers_every_species(viewer):
    r = viewer.get("/me")
    assert r.status_code == 200
    assert r.text.count('name="avatar_kind"') == len(st.AVATAR_CATALOG)
    for a in st.AVATAR_CATALOG:
        assert a["blurb"] in r.text


def test_every_species_and_stage_renders(app_mod):
    # the whole catalog × all 6 stages through the app's real Jinja env: a
    # broken macro would 500 the hub/pickers, so catch it here instead.
    tpl = app_mod.templates.env.from_string(
        '{% from "_avatars.html" import avatar_svg %}{{ avatar_svg(kind, stage) }}')
    for a in st.AVATAR_CATALOG:
        for stage in range(1, 7):
            svg = tpl.render(kind=a["key"], stage=stage)
            assert "avmove" in svg and "avstage" in svg, (a["key"], stage)
            assert "None" not in svg and "Undefined" not in svg, (a["key"], stage)


def test_avatar_macro_family_and_care_button(app_mod):
    tpl = app_mod.templates.env.from_string(
        '{% from "_avatars.html" import avatar %}'
        '{{ avatar(kind, 3, name="Pip", interactive=true, mood="okay", care=true) }}')
    bat = tpl.render(kind="bat")
    assert "fam-animal" in bat and 'data-care-action="feed"' in bat
    fern = tpl.render(kind="fern")
    assert "fam-plant" in fern and 'data-care-action="water"' in fern
    assert 'data-mood="okay"' in fern
