"""
Bureau-wide access — an explicit per-account grant, never a side effect of a role.

Scope comes from the directory: you see the unit you are recorded in. Some seats
genuinely need more — the Admin Officer consolidating ANNEX C for the whole
bureau — so `admin_user.bureau_access` grants it by name, at one of two levels:

  'awa' — the work arrangement only: the team schedule and the ANNEX C print.
  'all' — every scoped view, wellness register included.

The load-bearing assertions are the ones that prove 'awa' stops where it says it
does. A grant handed out so someone could print a schedule must not quietly open
every section's wellness claims, and it must not make its holder an approver.
"""
from __future__ import annotations

import pytest

import auth
import storage as st


def _drop_fixture_rows(conn):
    conn.execute("DELETE FROM work_arrangement WHERE user_id IN "
                 "(SELECT id FROM admin_user WHERE username LIKE 'ba-%@test.local')")
    conn.execute("DELETE FROM admin_user WHERE username LIKE 'ba-%@test.local'")
    conn.execute("DELETE FROM resource_person WHERE name LIKE 'BA-%'")
    conn.execute("DELETE FROM org_unit WHERE path LIKE 'BACC%'")
    conn.commit()


@pytest.fixture
def org(app_mod):
    """Two sections in different divisions, one person each, plus the three
    accounts the levels are tested through."""
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    _drop_fixture_rows(conn)

    units = {}
    for path, short in (("BACC/D1/S1", "S1"), ("BACC/D2/S2", "S2")):
        units[path] = conn.execute(
            "INSERT INTO org_unit(name, short_name, level, path) VALUES (?,?,?,?)",
            (short, short, "section", path)).lastrowid

    def account(name, path, role="viewer", designation=""):
        rp = conn.execute(
            "INSERT INTO resource_person(name, is_internal, org_unit_id, designation)"
            " VALUES (?,1,?,?)", (name, units[path], designation)).lastrowid
        return st.create_admin_user(conn, f"ba-{name.lower()}@test.local",
                                    "x", "y", role, rp_id=rp)

    out = {
        "conn": conn,
        # everyone below is recorded in S1 — the grant, not the seat, is what varies
        "plain": account("BA-Plain", "BACC/D1/S1"),
        "officer": account("BA-Officer", "BACC/D1/S1"),
        "super": account("BA-Super", "BACC/D1/S1", role="admin"),
        "other": account("BA-Other", "BACC/D2/S2"),
    }
    st.set_bureau_access(conn, out["officer"], "awa")
    st.set_bureau_access(conn, out["super"], "all")
    conn.commit()
    yield out
    _drop_fixture_rows(conn)       # session DB is shared: don't leave "S1"/"S2" for other modules
    conn.close()


def _u(conn, uid):
    r = st.get_admin_user_by_id(conn, uid)
    return {"id": r["id"], "username": r["username"], "role": r["role"]}


def _client(app_mod, conn, uid):
    from starlette.testclient import TestClient
    c = TestClient(app_mod.app, raise_server_exceptions=True)
    c.cookies.set(auth.COOKIE_NAME, auth.make_token(_u(conn, uid)))
    return c


# --- the grant itself -------------------------------------------------------

def test_the_default_is_no_grant_at_all(org):
    conn = org["conn"]
    assert st.bureau_access_of(conn, _u(conn, org["plain"])) == ""
    assert st.user_sees_whole_bureau(conn, _u(conn, org["plain"]), "awa") is False
    scope, kind = st.team_scope_for_user(conn, _u(conn, org["plain"]))
    assert (scope, kind) == ("BACC/D1/S1", "unit")


def test_an_admin_role_is_not_a_grant(org):
    """The role says what you may DO. A fresh admin with no grant still sees only
    the unit the directory puts them in — that is the whole point of the split."""
    conn = org["conn"]
    plain_admin = st.create_admin_user(conn, "ba-adm-nogrant@test.local", "x", "y", "admin")
    conn.commit()
    try:
        assert st.bureau_access_of(conn, _u(conn, plain_admin)) == ""
        assert st.user_sees_whole_bureau(conn, _u(conn, plain_admin)) is False
    finally:
        conn.execute("DELETE FROM admin_user WHERE id=?", (plain_admin,))
        conn.commit()


def test_an_unknown_level_is_refused(org):
    conn = org["conn"]
    with pytest.raises(ValueError):
        st.set_bureau_access(conn, org["plain"], "everything")


def test_the_grant_is_read_from_the_row_not_the_session(org):
    """The request user dict comes out of a signed cookie minted at sign-in. If
    the check trusted it, a revoked grant would keep working until the cookie
    expired."""
    conn = org["conn"]
    stale = dict(_u(conn, org["plain"]), bureau_access="all")
    assert st.user_sees_whole_bureau(conn, stale) is False


# --- 'awa': the work arrangement, and nothing else --------------------------

def test_awa_grant_widens_the_roster_to_every_section(org):
    conn = org["conn"]
    names = {r["name"] for r in
             st.work_arrangement_roster(conn, st.work_arrangement_period(),
                                        _u(conn, org["officer"]))}
    assert {"BA-Officer", "BA-Other"} <= names          # across both divisions

    # ...while an account without the grant still sees only its own section
    plain = {r["name"] for r in
             st.work_arrangement_roster(conn, st.work_arrangement_period(),
                                        _u(conn, org["plain"]))}
    assert "BA-Other" not in plain


def test_awa_grant_does_not_open_the_wellness_register(org):
    """The narrow grant exists so someone can consolidate schedules. Wellness
    claims are health information and are not part of that job."""
    conn = org["conn"]
    week = st.wellness_week_start()
    names = {r["name"] for r in
             st.wellness_week_rollup(conn, week, _u(conn, org["officer"]))["rows"]}
    assert "BA-Officer" in names
    assert "BA-Other" not in names

    pat = st.wellness_pattern(conn, week, _u(conn, org["officer"]))
    assert pat is not None                              # scoped, not widened


def test_awa_grant_does_not_widen_the_landing_page(org):
    """The landing page spans all three modules, so only a full grant widens it."""
    conn = org["conn"]
    assert st.team_scope_for_user(conn, _u(conn, org["officer"])) == \
        ("BACC/D1/S1", "unit")


def test_awa_grant_does_not_make_you_an_approver(org):
    """Sight is not authority. Whoever prints the bureau's ANNEX C must not gain
    the power to decide their colleagues' schedules as a side effect."""
    conn = org["conn"]
    officer = _u(conn, org["officer"])
    assert st.user_can_view_work_arrangement_schedule(conn, officer) is True
    assert st.user_is_approving_chief(conn, officer) is False
    assert st.list_work_arrangement_approvals(conn, officer) == []


# --- 'all': every scoped view ----------------------------------------------

def test_all_grant_widens_every_view(org):
    conn = org["conn"]
    user = _u(conn, org["super"])
    week = st.wellness_week_start()

    assert st.team_scope_for_user(conn, user) == (None, "bureau")
    assert st.user_sees_whole_bureau(conn, user, "awa") is True
    assert st.user_sees_whole_bureau(conn, user, "wellness") is True
    wellness = {r["name"] for r in st.wellness_week_rollup(conn, week, user)["rows"]}
    assert {"BA-Plain", "BA-Other"} <= wellness
    roster = {r["name"] for r in
              st.work_arrangement_roster(conn, st.work_arrangement_period(), user)}
    assert {"BA-Plain", "BA-Other"} <= roster


# --- the routes -------------------------------------------------------------

def test_the_schedule_and_annex_open_for_an_awa_grant(app_mod, org):
    """What was asked for: see every section's arrangement, and print it."""
    conn = org["conn"]
    c = _client(app_mod, conn, org["officer"])
    assert c.get("/work-arrangement/schedule").status_code == 200
    for fmt in ("xlsx", "pdf"):
        r = c.get(f"/work-arrangement/annex-c.{fmt}")
        assert r.status_code == 200, fmt
        assert r.content, fmt

    # the approvals queue is a different power and stays shut
    assert _client(app_mod, conn, org["officer"]).get(
        "/work-arrangement/approvals").status_code == 403


def test_the_schedule_stays_shut_without_a_grant(app_mod, org):
    conn = org["conn"]
    c = _client(app_mod, conn, org["plain"])
    assert c.get("/work-arrangement/schedule").status_code == 403
    assert c.get("/work-arrangement/annex-c.pdf").status_code == 403


def test_the_schedule_link_is_offered_to_a_grant_holder(app_mod, org):
    conn = org["conn"]
    html = _client(app_mod, conn, org["officer"]).get("/work-arrangement").text
    assert 'href="/work-arrangement/schedule"' in html
    assert 'href="/approvals' not in html                       # not an approver


def test_admins_can_change_the_grant_and_it_is_audited(app_mod, org):
    conn = org["conn"]
    admin = _client(app_mod, conn, org["super"])
    r = admin.post(f"/admin/users/{org['plain']}/bureau-access",
                   data={"bureau_access": "awa"}, follow_redirects=False)
    assert r.status_code == 303
    assert st.bureau_access_of(conn, _u(conn, org["plain"])) == "awa"

    row = conn.execute(
        "SELECT summary FROM audit_log WHERE action='change_bureau_access' "
        "ORDER BY id DESC LIMIT 1").fetchone()
    assert row and "ba-ba-plain@test.local" in row[0]

    # and it can be taken away again
    admin.post(f"/admin/users/{org['plain']}/bureau-access",
               data={"bureau_access": ""}, follow_redirects=False)
    assert st.bureau_access_of(conn, _u(conn, org["plain"])) == ""


def test_only_user_managers_may_change_the_grant(app_mod, org):
    conn = org["conn"]
    r = _client(app_mod, conn, org["plain"]).post(
        f"/admin/users/{org['officer']}/bureau-access",
        data={"bureau_access": "all"}, follow_redirects=False)
    assert r.status_code == 403
    assert st.bureau_access_of(conn, _u(conn, org["officer"])) == "awa"   # unchanged


# --- the named grants -------------------------------------------------------

def test_the_named_accounts_are_granted_once_and_a_revoke_sticks(app_mod, tmp_path):
    """The two seats the bureau asked for are granted on the first start after
    the account exists — and never re-granted, so an administrator who takes the
    grant away in Admin → Users does not find it back after the next deploy."""
    db = str(tmp_path / "seed.db")
    conn = st.connect(db)
    st.init_db(conn)                       # neither account exists yet: no-op

    medel = st.create_admin_user(conn, "armedel@doh.gov.ph", "x", "y", "viewer")
    ray = st.create_admin_user(conn, "ray@gmail.com", "x", "y", "viewer")
    conn.commit()
    st.init_db(conn)                       # next start applies them

    assert st.get_admin_user_by_id(conn, medel)["bureau_access"] == "awa"
    assert st.get_admin_user_by_id(conn, ray)["bureau_access"] == "all"
    assert st.get_admin_user_by_id(conn, ray)["role"] == "admin"

    st.set_bureau_access(conn, ray, "")
    st.init_db(conn)
    assert st.get_admin_user_by_id(conn, ray)["bureau_access"] == ""
    conn.close()
