"""
User levels (docs/USER_LEVELS_ASSESSMENT.md, 10.51).

* Super Administrator (stored "admin") keeps every power and the overrides.
* Administrator ("system_admin") is a Section Manager who can also fix survey
  data (walk-in entries, activity merges). No settings, directory or overrides.
* Section Manager reaches their own unit; at division level that is the
  division unit alone unless they are its chief or acting OIC.
* Division Manager reaches the whole division they sit in.
"""
from __future__ import annotations

import pytest
from starlette.testclient import TestClient

import activity_permissions
import auth
import calendar_notice
import storage as st
from tests.conftest import session_token

P = "ULVL"


def test_role_catalogue():
    assert auth.ROLES == ["viewer", "encoder", "section_manager", "division_manager",
                          "system_admin", "admin"]
    assert all(auth.valid_role(r) for r in auth.ROLES)
    assert auth.ROLE_LABELS["admin"] == "Super Administrator"
    assert auth.ROLE_LABELS["system_admin"] == "Administrator"
    assert auth.ROLE_LABELS["viewer"] == "Staff"
    assert auth.ROLE_CAPS["admin"] - auth.ROLE_CAPS["system_admin"] == {
        "manage_users", "operate", "directory", "hide", "triage_feedback"}
    assert auth.ROLE_CAPS["system_admin"] - auth.ROLE_CAPS["section_manager"] == {
        "manage_walkin_entries", "merge_activity"}
    assert auth.ROLE_CAPS["division_manager"] == auth.ROLE_CAPS["section_manager"]
    assert not auth.can("section_manager", "operate")
    assert "wipe" not in set().union(*auth.ROLE_CAPS.values())
    assert set(auth.role_sql_list().replace("'", "").split(",")) == set(auth.ROLE_CAPS)


@pytest.mark.parametrize("path,cap", [
    ("/admin/users", "manage_users"), ("/admin/users/5/role", "manage_users"),
    ("/admin/audit", "manage_users"), ("/admin/backups", "manage_users"),
    ("/admin/sharing", "manage_users"), ("/admin/restructure", "manage_users"),
    ("/admin/integrations", "manage_users"), ("/admin/documents/setup", "manage_users"),
    ("/admin/email", "operate"), ("/admin/holidays", "operate"), ("/admin/ai", "operate"),
    ("/admin/rules", "operate"), ("/admin/feedback", "operate"), ("/admin/travel", "operate"),
    ("/admin/appearance", "operate"), ("/admin/usersx", "operate"), ("/ops", "operate"),
])
def test_admin_paths_split(app_mod, path, cap):
    assert app_mod._required_cap(path) == cap


@pytest.fixture
def world(app_mod):
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    _wipe(conn)
    unit = {}
    for path, level in ((P, "bureau"), (P + "/D1", "division"), (P + "/D1/S1", "section"),
                        (P + "/D1/S2", "section"), (P + "/D2", "division"), (P + "/D2/S3", "section")):
        unit[path] = conn.execute("INSERT INTO org_unit(name, short_name, level, path) VALUES (?,?,?,?)",
                                  (path, path.rsplit("/", 1)[-1], level, path)).lastrowid

    def account(key, role, path, designation=""):
        rp = conn.execute("INSERT INTO resource_person(name, is_internal, org_unit_id, designation)"
                          " VALUES (?,1,?,?)", ("ULVL-" + key, unit[path], designation)).lastrowid
        uid = st.create_admin_user(conn, f"ulvl-{key}@test.local", "x", "y", role, rp_id=rp,
                                   created_by="test", active=True)
        return {"id": uid, "username": f"ulvl-{key}@test.local", "role": role}

    w = {"conn": conn, "unit": unit,
         "sm_s1": account("sm_s1", "section_manager", P + "/D1/S1"),
         "sm_d1": account("sm_d1", "section_manager", P + "/D1"),
         "chief_d1": account("chief_d1", "section_manager", P + "/D1", "Division Chief"),
         "oic_d1": account("oic_d1", "section_manager", P + "/D1"),
         "dm_s1": account("dm_s1", "division_manager", P + "/D1/S1"),
         "sys_s1": account("sys_s1", "system_admin", P + "/D1/S1"),
         "super": account("super", "admin", P + "/D2/S3")}
    conn.execute("INSERT INTO section_oic(org_unit_id, admin_user_id, set_at) VALUES (?,?,?)",
                 (unit[P + "/D1"], w["oic_d1"]["id"], "2026-11-24"))
    ev = {}
    for key, path in (("s1", P + "/D1/S1"), ("s2", P + "/D1/S2"), ("d1", P + "/D1"), ("s3", P + "/D2/S3")):
        ev[key] = {"id": conn.execute(
            "INSERT INTO event(event_token, title, event_date, lead_org_id) VALUES (?,?,?,?)",
            ("ulvl-" + key, "ULVL " + key, "2026-12-01", unit[path])).lastrowid,
            "created_by": "someone-else@test.local"}
    w["ev"] = ev
    conn.commit()
    yield w
    _wipe(conn)
    conn.commit()
    conn.close()


def _wipe(conn):
    conn.execute("DELETE FROM section_oic WHERE admin_user_id IN"
                 " (SELECT id FROM admin_user WHERE username LIKE 'ulvl-%@test.local')")
    conn.execute("DELETE FROM event WHERE event_token LIKE 'ulvl-%'")
    conn.execute("DELETE FROM login_session WHERE user_id IN"
                 " (SELECT id FROM admin_user WHERE username LIKE 'ulvl-%@test.local')")
    conn.execute("DELETE FROM admin_user WHERE username LIKE 'ulvl-%@test.local'")
    conn.execute("DELETE FROM resource_person WHERE name LIKE 'ULVL-%'")
    conn.execute("DELETE FROM org_unit WHERE path = ? OR path LIKE ?", (P, P + "/%"))


def _manages(w, who):
    return {k for k, e in w["ev"].items() if activity_permissions.can_manage(w[who], e, w["conn"])}


def test_section_manager_reaches_own_section(world):
    assert _manages(world, "sm_s1") == {"s1"}


def test_section_manager_at_division_level_reaches_that_unit_only(world):
    assert st.activity_scope_for_user(world["conn"], world["sm_d1"]) == (P + "/D1", "unit", True)
    assert _manages(world, "sm_d1") == {"d1"}


def test_division_chief_and_acting_oic_keep_the_division(world):
    assert _manages(world, "chief_d1") == {"d1", "s1", "s2"}
    assert _manages(world, "oic_d1") == {"d1", "s1", "s2"}


def test_division_manager_reaches_whole_division(world):
    assert st.activity_scope_for_user(world["conn"], world["dm_s1"]) == (P + "/D1", "unit", False)
    assert _manages(world, "dm_s1") == {"d1", "s1", "s2"}


def test_administrator_has_no_override(world):
    assert _manages(world, "sys_s1") == {"s1"}


def test_super_administrator_keeps_override(world):
    assert _manages(world, "super") == {"s1", "s2", "d1", "s3"}


def test_feed_matches_management_reach(world):
    owner, team_scope, kind = st.event_feed_scope(world["conn"], world["sm_d1"])
    titles = {e["title"] for e in st.list_events(world["conn"], created_by=owner, team_scope=team_scope)
              if e["title"].startswith("ULVL")}
    assert titles == {"ULVL d1"}


def _item(world, path):
    return {"status": "scheduled", "created_by": "someone-else@test.local", "people": [],
            "owner_org_id": world["unit"][path]}


def test_calendar_notice_is_limited_to_the_managers_unit(world):
    c = world["conn"]
    assert calendar_notice.can_send(world["sm_s1"], _item(world, P + "/D1/S1"), c)
    assert not calendar_notice.can_send(world["sm_s1"], _item(world, P + "/D2/S3"), c)
    assert not calendar_notice.can_send(world["sm_s1"], _item(world, P + "/D2/S3"))
    assert calendar_notice.can_send(world["dm_s1"], _item(world, P + "/D1/S2"), c)
    assert calendar_notice.can_send(world["super"], _item(world, P + "/D1/S2"))
    item = _item(world, P + "/D2/S3")
    item["people"] = [{"user_id": world["sm_s1"]["id"]}]
    assert calendar_notice.can_send(world["sm_s1"], item, c)


def test_administrator_pages(app_mod, world):
    client = TestClient(app_mod.app, raise_server_exceptions=True)
    client.cookies.set(auth.COOKIE_NAME, session_token(world["sys_s1"]))
    for path in ("/admin/users", "/admin/audit", "/admin/backups", "/admin/restructure",
                 "/admin/email", "/admin/holidays", "/admin/rules", "/admin/feedback", "/ops",
                 "/directory"):
        assert client.get(path, follow_redirects=False).status_code == 403, path
    assert client.get("/arta/entries", follow_redirects=False).status_code == 200
    client.close()


def test_release_switch_keeps_one_super_administrator(tmp_path):
    """10.51 switch: every old admin becomes Administrator except the seeded
    super account; it runs once and never leaves the system without one."""
    conn = st.connect(str(tmp_path / "split.db"))
    st.init_db(conn)
    a = st.create_admin_user(conn, "split-a@test.local", "x", "y", "admin", active=True)
    b = st.create_admin_user(conn, "split-b@test.local", "x", "y", "admin", active=False)
    m = st.create_admin_user(conn, "split-m@test.local", "x", "y", "section_manager", active=True)
    conn.commit()
    st.init_db(conn)                     # no super account yet: nothing changes
    assert st.get_admin_user_by_id(conn, a)["role"] == "admin"
    assert not st.get_setting(conn, st.SUPER_ADMIN_SPLIT_MARKER)

    keep = [u for u, _l, r in st.BUREAU_ACCESS_SEED if r == "admin"][0]
    s = st.create_admin_user(conn, keep, "x", "y", "viewer", active=True)
    conn.commit()
    st.init_db(conn)                     # seed makes it admin, then the split runs
    role = lambda uid: st.get_admin_user_by_id(conn, uid)["role"]
    assert role(s) == "admin"
    assert role(a) == "system_admin" and role(b) == "system_admin"
    assert role(m) == "section_manager"
    assert st.get_setting(conn, st.SUPER_ADMIN_SPLIT_MARKER)
    assert conn.execute("SELECT COUNT(*) FROM audit_log WHERE action='change_role' "
                        "AND after_text='system_admin'").fetchone()[0] == 2

    st.set_admin_role(conn, a, "admin")  # a later promotion sticks
    st.init_db(conn)
    assert role(a) == "admin"
    conn.close()
