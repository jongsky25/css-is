"""Basic colleague status, visible to every signed-in user (docs/HOME_SEARCH_ASSISTANT_PLAN.md
Phase 5): storage.basic_status_for_day / colleague_status_for, the colleague search source,
and the /people/{id} card. The point of most checks: only a bare state ever leaves."""
from __future__ import annotations

from datetime import date

import pytest
from starlette.testclient import TestClient

import auth
import storage as st

WED = date(2026, 10, 14)          # an ordinary working day, inside the 2026-10-01 period
SAT = date(2026, 10, 17)
HOLIDAY = date(2026, 10, 13)      # a Tuesday we declare a holiday for the test
SECRET = "Secretplace Xyzzy"


def _client(app_mod, conn, uid):
    u = st.get_admin_user_by_id(conn, uid)
    c = TestClient(app_mod.app, raise_server_exceptions=True)
    c.cookies.set(auth.COOKIE_NAME, auth.make_token({"id": u["id"], "username": u["username"], "role": u["role"]}))
    return c


@pytest.fixture()
def org(app_mod):
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    st.basic_status_clear_cache()
    units = {}
    for path, short in (("CSTAT/D1/SA", "CS-A"), ("CSTAT/D1/SB", "CS-B")):
        units[path] = conn.execute(
            "INSERT INTO org_unit(name, short_name, level, path) VALUES (?,?,?,?)",
            (short, short, "section", path)).lastrowid

    def person(name, path, user, position="Planning Officer"):
        rp = conn.execute("INSERT INTO resource_person(name, is_internal, org_unit_id, position) VALUES (?,1,?,?)",
                          (name, units[path], position)).lastrowid
        return st.create_admin_user(conn, user, "x", "y", "viewer", rp_id=rp)

    out = {"conn": conn,
           "alice": person("Zeta Alice", "CSTAT/D1/SA", "cs-alice@test.local"),
           "bob": person("Zeta Bob", "CSTAT/D1/SB", "cs-bob@test.local"),
           "unlinked": st.create_admin_user(conn, "cs-unlinked@test.local", "x", "y", "viewer")}
    conn.commit()
    yield out
    for tbl in ("whereabouts", "work_arrangement"):
        conn.execute(f"DELETE FROM {tbl} WHERE user_id IN (SELECT id FROM admin_user WHERE username LIKE 'cs-%')")
    conn.execute("DELETE FROM holiday WHERE day=?", (HOLIDAY.isoformat(),))
    conn.execute("DELETE FROM app_setting WHERE key='colleague_status_scope'")
    conn.execute("DELETE FROM admin_user WHERE username LIKE 'cs-%'")
    conn.execute("DELETE FROM resource_person WHERE name LIKE 'Zeta %'")
    conn.execute("DELETE FROM org_unit WHERE path LIKE 'CSTAT%'")
    conn.commit()
    st.basic_status_clear_cache()
    conn.close()


def _report(conn, uid, day, status, note=None):
    conn.execute("INSERT OR REPLACE INTO whereabouts(user_id, day, status, note) VALUES (?,?,?,?)",
                 (uid, day.isoformat(), status, note))
    conn.commit()
    st.basic_status_clear_cache()


def test_values_are_bare_strings(org):
    _report(org["conn"], org["bob"], WED, "field", SECRET)
    got = st.basic_status_for_day(org["conn"], WED)
    assert got[org["bob"]] == "field"
    assert all(isinstance(v, str) and v in st.BASIC_STATES for v in got.values())


def test_a_report_beats_the_filing(org):
    conn = org["conn"]
    conn.execute("INSERT INTO work_arrangement(user_id, period_start, arrangement, weekday, status, created_at) "
                 "VALUES (?, '2026-10-01', 'WFH', 2, 'approved', '2026-09-20')", (org["alice"],))
    conn.commit()
    st.basic_status_clear_cache()
    assert st.basic_status_for_day(conn, WED)[org["alice"]] == "wfh"          # the filing says so
    _report(conn, org["alice"], WED, "office")
    assert st.basic_status_for_day(conn, WED)[org["alice"]] == "onsite"       # their own word wins


def test_weekend_and_holiday_read_off_for_everyone(org):
    conn = org["conn"]
    assert set(st.basic_status_for_day(conn, SAT).values()) == {"off"}
    st.set_holiday(conn, HOLIDAY.isoformat(), "Test holiday")
    st.basic_status_clear_cache()
    assert set(st.basic_status_for_day(conn, HOLIDAY).values()) == {"off"}


def test_bureau_switch_unlinked_viewer_sees_status_team_switch_does_not(org):
    conn = org["conn"]
    _report(conn, org["bob"], WED, "office")
    assert st.colleague_status_scope(conn) == "bureau"
    assert st.colleague_status_for(conn, st.get_admin_user_by_id(conn, org["unlinked"]), WED)[org["bob"]] == "onsite"
    st.set_colleague_status_scope(conn, "team")
    assert st.colleague_status_for(conn, st.get_admin_user_by_id(conn, org["unlinked"]), WED) == {}


def test_team_switch_hides_someone_outside_your_section(org):
    conn = org["conn"]
    _report(conn, org["bob"], WED, "office")
    _report(conn, org["alice"], WED, "office")
    st.set_colleague_status_scope(conn, "team")
    alice = st.get_admin_user_by_id(conn, org["alice"])
    got = st.colleague_status_for(conn, alice, WED)
    assert org["alice"] in got and org["bob"] not in got


def test_a_bad_scope_is_refused(org):
    with pytest.raises(ValueError):
        st.set_colleague_status_scope(org["conn"], "everyone")


def test_search_finds_a_colleague_with_a_basic_status_and_no_secrets(app_mod, org):
    conn = org["conn"]
    today = app_mod._today_local()
    if today.weekday() < 5:
        _report(conn, org["bob"], today, "field", SECRET)
    c = _client(app_mod, conn, org["unlinked"])
    rows = [r for r in c.get("/api/search?q=zeta bob").json() if r["section"] == "Colleagues"]
    assert [r["title"] for r in rows] == ["Zeta Bob"]
    assert rows[0]["url"] == f"/people/{org['bob']}"
    assert "Planning Officer" in rows[0]["hint"] and "CS-B" in rows[0]["hint"]
    assert SECRET.lower() not in c.get("/api/search?q=zeta").text.lower()


def test_colleagues_is_not_in_the_css_scope(app_mod, org):
    c = _client(app_mod, org["conn"], org["unlinked"])
    assert not [r for r in c.get("/api/search?q=zeta&scope=css").json() if r["section"] == "Colleagues"]


def test_exact_first_name_ranks_first(app_mod, org):
    conn = org["conn"]
    rp = conn.execute("INSERT INTO resource_person(name, is_internal, position) VALUES ('Quentin Zeta Smith',1,'Clerk')").lastrowid
    st.create_admin_user(conn, "cs-quentin@test.local", "x", "y", "viewer", rp_id=rp)
    conn.commit()
    c = _client(app_mod, conn, org["unlinked"])
    titles = [r["title"] for r in c.get("/api/search?q=zeta").json() if r["section"] == "Colleagues"]
    assert titles[0] == "Zeta Alice" or titles[0] == "Zeta Bob"      # first-name "zeta" beats a surname hit
    assert titles[-1] == "Quentin Zeta Smith"


def test_card_shows_the_basics_and_never_the_note(app_mod, org):
    conn = org["conn"]
    today = app_mod._today_local()
    if today.weekday() < 5:
        _report(conn, org["bob"], today, "field", SECRET)
    c = _client(app_mod, conn, org["unlinked"])
    r = c.get(f"/people/{org['bob']}")
    assert r.status_code == 200
    assert "Zeta Bob" in r.text and "Planning Officer" in r.text and "CS-B" in r.text
    assert SECRET.lower() not in r.text.lower()
    assert "cs-bob@test.local" not in r.text                      # no email


def test_card_status_follows_the_switch(app_mod, org):
    conn = org["conn"]
    today = app_mod._today_local()
    if today.weekday() >= 5:
        pytest.skip("weekend: everyone reads Off today")
    _report(conn, org["bob"], today, "office")
    c = _client(app_mod, conn, org["unlinked"])
    assert "In the office today" in c.get(f"/people/{org['bob']}").text
    st.set_colleague_status_scope(conn, "team")
    st.basic_status_clear_cache()
    assert "In the office today" not in c.get(f"/people/{org['bob']}").text


def test_card_404s_for_unknown_and_unlinked_ids_and_needs_login(app_mod, org):
    c = _client(app_mod, org["conn"], org["alice"])
    assert c.get("/people/999999").status_code == 404
    assert c.get(f"/people/{org['unlinked']}").status_code == 404
    anon = TestClient(app_mod.app)
    r = anon.get(f"/people/{org['bob']}", follow_redirects=False)
    assert r.status_code in (302, 303, 307) and "login" in r.headers["location"]


def test_admin_can_flip_the_switch(app_mod, org, admin):
    r = admin.post("/admin/work-arrangement/colleague-status", data={"scope": "team"}, follow_redirects=False)
    assert r.status_code == 303
    assert st.colleague_status_scope(org["conn"]) == "team"
    assert "checked" in admin.get("/admin/work-arrangement").text
    bad = admin.post("/admin/work-arrangement/colleague-status", data={"scope": "nope"}, follow_redirects=False)
    assert "err=" in bad.headers["location"]
    assert st.colleague_status_scope(org["conn"]) == "team"
