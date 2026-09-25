"""
Avatar companions — care/mood layer + the 16-species art surface.

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


# --- care day-streak + the Devoted caretaker badge ---------------------------

def _care_on_days(conn, uid, days):
    """Care once per day for `days` consecutive days ending at NOW+days."""
    out = None
    for d in range(days):
        out = st.record_avatar_care(conn, uid, now=NOW + timedelta(days=d))
    return out


def test_streak_counts_consecutive_days(conn):
    uid = _mk_account(conn, "streak-run@test.local")
    assert _care_on_days(conn, uid, 3)["streak"] == 3
    # a second counted care the SAME day (outside the 6h cooldown) keeps it
    same_day = st.record_avatar_care(conn, uid, now=NOW + timedelta(days=2, hours=7))
    assert same_day["counted"] is True
    assert same_day["streak"] == 3
    # a >1-day gap resets to 1
    lapsed = st.record_avatar_care(conn, uid, now=NOW + timedelta(days=6))
    assert lapsed["streak"] == 1


def test_streak_survives_uncounted_taps(conn):
    uid = _mk_account(conn, "streak-tap@test.local")
    _care_on_days(conn, uid, 2)
    spam = st.record_avatar_care(conn, uid, now=NOW + timedelta(days=1, hours=1))
    assert spam["counted"] is False
    assert spam["streak"] == 2                        # unmoved by cooldown taps


def test_badge_awarded_once_at_seven_days(conn):
    uid = _mk_account(conn, "streak-badge@test.local")
    conn.execute("DELETE FROM wellness_badge WHERE user_id=?", (uid,))
    conn.commit()
    results = [st.record_avatar_care(conn, uid, now=NOW + timedelta(days=d))
               for d in range(8)]
    assert results[5]["badge"] is None                # day 6: not yet
    assert results[6]["streak"] == 7
    assert results[6]["badge"] == st.WELLNESS_BADGES["avatar_care_7"][0]
    assert results[7]["badge"] is None                # already held — never re-fires
    n = conn.execute("SELECT COUNT(*) FROM wellness_badge WHERE user_id=? AND badge=?",
                     (uid, "avatar_care_7")).fetchone()[0]
    assert n == 1
    # and it shows up in the wellness hub's badge row
    badges = st.wellness_stats(conn, uid)["badges"]
    assert any(b["key"] == "avatar_care_7" for b in badges)


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


def test_care_endpoint_reports_streak_and_badge(viewer, app_mod):
    conn = st.connect(app_mod.DB)
    conn.execute("UPDATE admin_user SET avatar_kind='dog', avatar_last_care_at=NULL, "
                 "avatar_care_streak=NULL WHERE username='viewer@test.local'")
    conn.commit(); conn.close()
    body = viewer.post("/avatar/care", data={"action": "feed"}).json()
    assert body["streak"] == 1
    assert body["badge"] is None


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
            assert "av-zzz" in svg, (a["key"], stage)   # the sleep Zzz layer
            assert "None" not in svg and "Undefined" not in svg, (a["key"], stage)


def test_every_species_and_month_renders(app_mod):
    # seasonal accessories: every species × every month (and bare month 0)
    tpl = app_mod.templates.env.from_string(
        '{% from "_avatars_art.html" import species_art %}{{ species_art(kind, 4, m) }}')
    for a in st.AVATAR_CATALOG:
        for m in range(0, 13):
            svg = tpl.render(kind=a["key"], m=m)
            assert "None" not in svg and "Undefined" not in svg, (a["key"], m)
            if m:
                assert "av-acc" in svg, (a["key"], m)   # accessory present


def test_sound_toggle_rendered_with_care(app_mod):
    tpl = app_mod.templates.env.from_string(
        '{% from "_avatars.html" import avatar %}'
        '{{ avatar("dog", 3, name="Rex", interactive=true, care=true) }}')
    out = tpl.render()
    assert "av-sound-btn" in out and 'aria-pressed="false"' in out


def test_avatar_macro_family_and_care_button(app_mod):
    tpl = app_mod.templates.env.from_string(
        '{% from "_avatars.html" import avatar %}'
        '{{ avatar(kind, 3, name="Pip", interactive=true, mood="okay", care=true) }}')
    bat = tpl.render(kind="bat")
    assert "fam-animal" in bat and 'data-care-action="feed"' in bat
    fern = tpl.render(kind="fern")
    assert "fam-plant" in fern and 'data-care-action="water"' in fern
    assert 'data-mood="okay"' in fern


# --- dolphin + the swimmer water backdrop ------------------------------------

def test_dolphin_in_catalog_and_swims():
    d = next((a for a in st.AVATAR_CATALOG if a["key"] == "dolphin"), None)
    assert d is not None and d["family"] == "animal"
    assert st.valid_avatar_kind("dolphin")
    assert st.avatar_care_verb("dolphin") == "feed"     # an animal is fed
    assert st.avatar_is_swimmer("dolphin") is True
    assert st.avatar_is_swimmer("fish") is True
    assert st.avatar_is_swimmer("cat") is False


def test_swimmer_water_backdrop_is_static_and_behind(app_mod):
    # Regression: the fish/dolphin "home water" used to sit INSIDE .avmove and
    # drifted across the SVG as the creature swam. avatar_svg must now draw it
    # once, BEHIND and OUTSIDE the moving layer, so it stays put.
    tpl = app_mod.templates.env.from_string(
        '{% from "_avatars.html" import avatar_svg %}{{ avatar_svg(kind, 4) }}')
    for kind in ("fish", "dolphin"):
        svg = tpl.render(kind=kind)
        assert 'class="av-water"' in svg, kind
        assert svg.index("av-water") < svg.index("avmove"), kind   # behind + static
    # non-swimmers never get a water surface
    for kind in ("plant", "cat", "bat", "owl"):
        assert 'class="av-water"' not in tpl.render(kind=kind), kind


def test_fish_art_no_longer_embeds_its_own_water(app_mod):
    # species_art must not draw the water itself anymore (avatar_svg owns it),
    # else a swimming fish would carry a second, moving bowl.
    tpl = app_mod.templates.env.from_string(
        '{% from "_avatars_art.html" import species_art %}{{ species_art(kind, 4, 0) }}')
    assert "avg-water" not in tpl.render(kind="fish")
    assert "avg-water" not in tpl.render(kind="dolphin")


# --- watering visibility (CSS contract) --------------------------------------

def _defs_css(app_mod):
    return app_mod.templates.env.from_string(
        '{% from "_avatars.html" import avatar_defs %}{{ avatar_defs() }}').render()


def test_watering_droplet_css_contract(app_mod):
    # Regression: the base hide must target the drop PATHS, not the .av-drops
    # group — a child animating its opacity inside an opacity:0 parent stays
    # invisible, which made watering show no droplets on every plant.
    css = _defs_css(app_mod)
    assert ".av-drops path { opacity:0; }" in css
    assert ".av-food, .av-drops {" not in css          # group no longer in the hide list
    # and the succulent (whose animation:none outranks av-perk) has its own
    # higher-specificity watered response
    assert '.avwrap[data-kind="succulent"].av-caring-water .avstage' in css


def test_defs_carry_new_behavior_css(app_mod):
    # the roam gaits, petting, and explore overlay all ship in avatar_defs()
    css = _defs_css(app_mod)
    for marker in ("av-trot", "av-bound", "av-plod", "av-do-zoom",
                   "av-heart", "av-nuzzle", "av-explore-layer", "z-index:14",
                   "pointer-events:none"):
        assert marker in css, f"missing {marker} in avatar_defs()"


# --- personality data attributes ---------------------------------------------

def test_avatar_macro_personality_attrs(app_mod):
    tpl = app_mod.templates.env.from_string(
        '{% from "_avatars.html" import avatar %}'
        '{{ avatar("dog", 3, name="Rex", interactive=true, care=true,'
        ' person=person, care_streak=streak, last_care=last) }}')
    out = tpl.render(person="Maria", streak=5, last="2026-07-21T09:00:00")
    assert 'data-person="Maria"' in out
    assert 'data-care-streak="5"' in out
    assert 'data-last-care="2026-07-21T09:00:00"' in out
    bare = tpl.render(person="", streak=0, last="")
    for attr in ("data-person", "data-care-streak", "data-last-care"):
        assert attr not in bare                        # optional: absent when empty


def test_explore_button_only_for_swimmers(app_mod):
    tpl = app_mod.templates.env.from_string(
        '{% from "_avatars.html" import avatar %}'
        '{{ avatar(kind, 3, name="P", interactive=true, care=care) }}')
    assert "av-explore-btn" in tpl.render(kind="fish", care=True)
    assert "av-explore-btn" in tpl.render(kind="dolphin", care=True)
    assert "av-explore-btn" not in tpl.render(kind="dog", care=True)     # no water to swim
    assert "av-explore-btn" not in tpl.render(kind="fish", care=False)   # hub-only surface


def test_wellness_hub_renders_personality_markers(viewer, app_mod):
    conn = st.connect(app_mod.DB)
    conn.execute("UPDATE admin_user SET avatar_kind='fish', avatar_name='Bubbles' "
                 "WHERE username='viewer@test.local'")
    conn.commit(); conn.close()
    r = viewer.get("/wellness")
    assert r.status_code == 200
    assert "av-explore-btn" in r.text                  # swimmer gets the 🌊 toggle
    # the care data attributes appear once the account has actually cared
    r2 = viewer.post("/avatar/care", data={"action": "feed"})
    assert r2.status_code == 200
    r3 = viewer.get("/wellness")
    assert "data-care-streak=" in r3.text
    assert "data-last-care=" in r3.text


def test_profile_includes_care_streak(conn):
    uid = _mk_account(conn, "streak-prof@test.local")
    assert st.get_user_profile(conn, uid)["avatar_care_streak"] == 0
    st.record_avatar_care(conn, uid, now=NOW)
    st.record_avatar_care(conn, uid, now=NOW + timedelta(days=1))
    assert st.get_user_profile(conn, uid)["avatar_care_streak"] == 2


# ---------------------------------------------------------------------------
# The growth ladder — "what am I working toward, and how do I get there?"
# ---------------------------------------------------------------------------
# The companion had six growth stages from the start, but only ever showed the
# one you were on. Nothing said the others existed or how to reach them.

def test_growth_ladder_marks_where_you_are(app_mod):
    ladder = st.avatar_growth_ladder("turtle", {"stage": 3})

    assert [s["stage"] for s in ladder] == [1, 2, 3, 4, 5, 6]
    assert [s["points_at"] for s in ladder] == st.WELLNESS_LEVELS
    assert [s["reached"] for s in ladder] == [True, True, True, False, False, False]
    assert [s["current"] for s in ladder].count(True) == 1
    assert next(s for s in ladder if s["current"])["stage"] == 3
    # names follow the SPECIES family, not a single hardcoded set
    assert ladder[0]["name"] == st.avatar_stage_name("turtle", 1)
    assert st.avatar_growth_ladder("cactus", {"stage": 1})[0]["name"] != ladder[0]["name"]


def test_growth_ladder_survives_missing_or_odd_stats(app_mod):
    """Gamification is derived on every read, so a caller may have no stats at
    all (a brand-new account) — the ladder must still render, at stage 1."""
    for stats in (None, {}, {"stage": 0}, {"stage": 99}):
        ladder = st.avatar_growth_ladder("plant", stats)
        assert len(ladder) == 6
        assert all(s["name"] for s in ladder)


def test_growth_actions_are_read_from_the_scoring_constants(app_mod):
    """The explanation must not be able to drift from the arithmetic that
    actually drives the avatar."""
    how = st.avatar_growth_actions("cat")
    pts = {a["points"] for a in how["points"]}

    assert st.WELLNESS_PTS_BREAK in pts
    assert st.WELLNESS_PTS_REFLECTION in pts
    assert st.WELLNESS_PTS_STREAK_WEEK in pts
    assert str(st.WELLNESS_WEEKLY_HOURS) in " ".join(a["label"] for a in how["points"])
    # you FEED an animal and WATER a plant
    assert how["care"]["verb"] == st.avatar_care_verb("cat")
    assert st.avatar_growth_actions("fern")["care"]["verb"] != how["care"]["verb"]
    # care earns a badge, not points — said plainly so it doesn't read as a
    # fifth way to level up
    assert how["care"]["badge"] == st.WELLNESS_BADGES["avatar_care_7"][0]


def test_landing_and_profile_both_show_the_ladder(app_mod):
    from tests.conftest import _auth_client
    c = _auth_client(app_mod, "admin")
    for path in ("/", "/me"):
        html = c.get(path).text
        assert "gl-strip" in html, path
        assert "grows" in html, path
        # every locked stage advertises the threshold that unlocks it
        assert "pts" in html, path


def test_growth_actions_link_to_where_you_do_them(app_mod):
    """Each "how it grows" line reads like a to-do and got clicked like one —
    so each is a link to where that action happens."""
    how = st.avatar_growth_actions("cat")
    assert all(a.get("href") for a in how["points"])
    from tests.conftest import _auth_client
    html = _auth_client(app_mod, "admin").get("/").text
    assert '<a href="/wellness/apply">Take a wellness break →</a>' in html


def test_home_greeting_opens_your_profile(app_mod):
    from tests.conftest import _auth_client
    html = _auth_client(app_mod, "admin").get("/").text
    assert 'class="oc-me" href="/me"' in html


def test_the_space_around_the_companion_taps_it(app_mod):
    """The pet's name, stage line and the gaps beside it were dead clicks on
    home and the wellness hub; they are now a [data-pet-area] that
    avatars.js forwards to the companion, and telemetry counts as a control."""
    from tests.conftest import _auth_client
    import os
    html = _auth_client(app_mod, "admin").get("/wellness").text
    assert '<div class="avatar-box" data-pet-area' in html
    root = os.path.dirname(app_mod.__file__)
    home = open(os.path.join(root, "templates", "office_connect.html")).read()
    assert '<div class="oc-pet" data-pet-area>' in home
    js = open(os.path.join(root, "static", "js", "avatars.js")).read()
    assert 'closest("[data-pet-area]")' in js
    tel = open(os.path.join(root, "static", "js", "telemetry.js")).read()
    assert "[data-pet-area]" in tel
