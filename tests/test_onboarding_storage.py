"""
Staff onboarding + avatar companion — Phase 1 (schema + storage).

Covers the guarded migration (columns exist and are idempotent), the avatar
catalog + per-family stage-name resolution, and the three account helpers
(set_user_avatar / mark_onboarded / get_user_profile). No HTTP surface yet —
these are the building blocks the /welcome flow and chooser sit on.
"""
from __future__ import annotations

import pytest

import storage as st
import tzutil as tz


@pytest.fixture()
def conn(app_mod):
    c = st.connect(app_mod.DB)
    st.init_db(c)
    yield c
    c.close()


def _mk_account(conn, username, role="viewer", rp_id=None):
    return st.create_admin_user(conn, username, "h", "s", role,
                                created_by="test", active=True, rp_id=rp_id)


# --- migration --------------------------------------------------------------

def test_new_columns_exist(conn):
    cols = {row[1] for row in conn.execute("PRAGMA table_info(admin_user)")}
    assert {"avatar_kind", "avatar_name", "onboarded_at",
            "avatar_last_care_at", "avatar_care_streak"} <= cols


def test_migration_is_idempotent(conn):
    # init_db already ran once via the fixture; running it again must not raise
    # (guarded ALTERs) and must not disturb existing columns.
    before = {row[1] for row in conn.execute("PRAGMA table_info(admin_user)")}
    st.init_db(conn)
    after = {row[1] for row in conn.execute("PRAGMA table_info(admin_user)")}
    assert before == after


def test_fresh_account_starts_unonboarded(conn):
    uid = _mk_account(conn, "onb-fresh@test.local")
    acct = st.get_admin_user_by_id(conn, uid)
    assert acct["avatar_kind"] is None
    assert acct["avatar_name"] is None
    assert acct["onboarded_at"] is None


# --- avatar catalog + stage names -------------------------------------------

def test_catalog_has_both_families():
    families = {a["family"] for a in st.AVATAR_CATALOG}
    assert families == {"plant", "animal"}
    assert st.AVATAR_DEFAULT in st.AVATAR_KEYS


def test_catalog_has_fifteen_species_with_blurbs():
    assert len(st.AVATAR_CATALOG) == 15
    assert len(st.AVATAR_KEYS) == 15          # keys are unique
    assert all(a.get("blurb") for a in st.AVATAR_CATALOG)


def test_valid_avatar_kind():
    assert st.valid_avatar_kind("cat")
    assert st.valid_avatar_kind("plant")
    assert st.valid_avatar_kind("bat")
    assert st.valid_avatar_kind("succulent")
    assert not st.valid_avatar_kind("dragon")
    assert not st.valid_avatar_kind(None)
    assert not st.valid_avatar_kind("")


def test_avatar_family_falls_back_for_unknown():
    assert st.avatar_family("cat") == "animal"
    assert st.avatar_family("bonsai") == "plant"
    assert st.avatar_family("fish") == "animal"
    assert st.avatar_family("bat") == "animal"
    assert st.avatar_family("mushroom") == "plant"
    assert st.avatar_family("sunflower") == "plant"
    # unknown/None never KeyErrors — falls back to the default species' family
    assert st.avatar_family("dragon") == st.avatar_family(st.AVATAR_DEFAULT)
    assert st.avatar_family(None) == st.avatar_family(st.AVATAR_DEFAULT)


def test_stage_name_resolution_per_family():
    assert st.avatar_stage_name("plant", 1) == "Seed"
    assert st.avatar_stage_name("plant", 6) == "Flourishing"
    assert st.avatar_stage_name("cat", 1) == "Hatchling"
    assert st.avatar_stage_name("cat", 6) == "Flourishing"


def test_stage_name_clamps_out_of_range():
    # gamification drift must never index-error the label lookup
    assert st.avatar_stage_name("plant", 0) == "Seed"
    assert st.avatar_stage_name("plant", 99) == "Flourishing"
    assert st.avatar_stage_name("cat", None) == "Hatchling"


def test_wellness_stage_names_alias_the_plant_array():
    # single source of truth — the classic wellness vocabulary IS the plant
    # family's array, so mascot and plant avatar can't drift.
    assert st.WELLNESS_STAGE_NAMES == st.AVATAR_STAGE_NAMES["plant"]


def test_clean_avatar_name_trims_and_caps():
    assert st.clean_avatar_name("  Sir Reginald  ") == "Sir Reginald"
    assert st.clean_avatar_name("") == ""
    assert st.clean_avatar_name(None) == ""
    long = "x" * 100
    assert len(st.clean_avatar_name(long)) == st.AVATAR_NAME_MAXLEN


# --- account helpers --------------------------------------------------------

def test_set_user_avatar_persists(conn):
    uid = _mk_account(conn, "onb-set@test.local")
    st.set_user_avatar(conn, uid, "turtle", "  Shelly  ")
    acct = st.get_admin_user_by_id(conn, uid)
    assert acct["avatar_kind"] == "turtle"
    assert acct["avatar_name"] == "Shelly"          # trimmed
    # choosing an avatar does not mark onboarding complete on its own
    assert acct["onboarded_at"] is None


def test_set_user_avatar_rejects_unknown_species(conn):
    uid = _mk_account(conn, "onb-bad@test.local")
    with pytest.raises(ValueError):
        st.set_user_avatar(conn, uid, "dragon", "Smaug")
    assert st.get_admin_user_by_id(conn, uid)["avatar_kind"] is None


def test_mark_onboarded_stamps_and_is_idempotent(conn):
    uid = _mk_account(conn, "onb-mark@test.local")
    st.mark_onboarded(conn, uid, when="2026-07-20T00:00:00+08:00")
    assert st.get_admin_user_by_id(conn, uid)["onboarded_at"] == "2026-07-20T00:00:00+08:00"
    # re-stamp just refreshes; still non-NULL
    st.mark_onboarded(conn, uid)
    assert st.get_admin_user_by_id(conn, uid)["onboarded_at"]


def test_get_user_profile_unlinked_account(conn):
    uid = _mk_account(conn, "onb-loner@test.local")
    prof = st.get_user_profile(conn, uid)
    assert prof["user_id"] == uid
    assert prof["rp_id"] is None
    assert prof["person_name"] == ""
    assert prof["has_photo"] is False
    assert prof["onboarded"] is False
    # avatar_kind is normalized to the default so callers can always draw one
    assert prof["avatar_kind"] == st.AVATAR_DEFAULT
    assert prof["avatar_name"] == ""


def test_get_user_profile_linked_account(conn):
    cur = conn.execute(
        "INSERT INTO org_unit(name, short_name, level, path) "
        "VALUES ('Onb Test Sec','OSec','section','TEST/ONB/OSec')")
    unit = cur.lastrowid
    cur = conn.execute(
        "INSERT INTO resource_person(name, is_internal, org_unit_id, designation) "
        "VALUES ('Onb-Test Pat', 1, ?, 'Section Head')", (unit,))
    rp_id = cur.lastrowid
    conn.commit()
    uid = _mk_account(conn, "onb-linked@test.local", role="section_manager", rp_id=rp_id)
    st.set_user_avatar(conn, uid, "cat", "Milo")
    st.mark_onboarded(conn, uid)

    prof = st.get_user_profile(conn, uid)
    assert prof["rp_id"] == rp_id
    assert prof["person_name"] == "Onb-Test Pat"
    assert prof["org_path"] == "TEST/ONB/OSec"
    assert prof["designation"] == "Section Head"
    assert prof["avatar_kind"] == "cat"
    assert prof["avatar_name"] == "Milo"
    assert prof["onboarded"] is True

    # cleanup so the shared session DB isn't polluted for other tests
    conn.execute("DELETE FROM admin_user WHERE id=?", (uid,))
    conn.execute("DELETE FROM resource_person WHERE id=?", (rp_id,))
    conn.execute("DELETE FROM org_unit WHERE id=?", (unit,))
    conn.commit()


def test_get_user_profile_unknown_account(conn):
    assert st.get_user_profile(conn, 999999) is None
