"""
Team-scope resolution — the guard that keeps the Office Connect landing page
from showing one person another team's filings.

The landing page shows EVERY signed-in user their team, with no chief-only route
guard in front of it. That removes the assumption `_org_scope_for_user` was
written under (see its docstring: "Admins — and any account with no directory
org unit — monitor everyone"), so an account with no directory link must resolve
to "no team" rather than falling through to the whole bureau.
"""
from __future__ import annotations

import pytest

import storage as st


@pytest.fixture
def org(app_mod):
    """Two sections in different divisions, plus an account with no directory
    link at all — the three cases team_scope_for_user has to tell apart."""
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    conn.execute("DELETE FROM admin_user WHERE username LIKE 'ts-%@test.local'")
    conn.execute("DELETE FROM resource_person WHERE name LIKE 'TS-%'")
    conn.execute("DELETE FROM org_unit WHERE path LIKE 'TSCOPE%'")
    units = {}
    for path, short in (("TSCOPE/D1/S1", "S1"), ("TSCOPE/D2/S2", "S2")):
        units[path] = conn.execute(
            "INSERT INTO org_unit(name, short_name, level, path) VALUES (?,?,?,?)",
            (short, short, "section", path)).lastrowid
    def person(name, unit, designation=""):
        return conn.execute(
            "INSERT INTO resource_person(name, is_internal, org_unit_id, designation)"
            " VALUES (?,1,?,?)", (name, unit, designation)).lastrowid
    s1_rp = person("TS-One", units["TSCOPE/D1/S1"])
    s1_chief_rp = person("TS-One Chief", units["TSCOPE/D1/S1"], "Section Head")
    s2_rp = person("TS-Two", units["TSCOPE/D2/S2"])
    mk = lambda u, role, rp: st.create_admin_user(conn, u, "x", "y", role, rp_id=rp)
    out = {
        "conn": conn,
        "s1": mk("ts-s1@test.local", "viewer", s1_rp),
        "s1_chief": mk("ts-s1chief@test.local", "section_manager", s1_chief_rp),
        "s2": mk("ts-s2@test.local", "viewer", s2_rp),
        "unlinked": st.create_admin_user(conn, "ts-none@test.local", "x", "y", "viewer"),
        "admin": st.create_admin_user(conn, "ts-adm@test.local", "x", "y", "admin"),
    }
    conn.commit()
    yield out
    conn.close()


def _u(conn, uid):
    r = st.get_admin_user_by_id(conn, uid)
    return {"id": r["id"], "username": r["username"], "role": r["role"]}


def test_linked_staff_scope_to_their_own_unit(org):
    conn = org["conn"]
    for key, path in (("s1", "TSCOPE/D1/S1"), ("s2", "TSCOPE/D2/S2")):
        scope, kind = st.team_scope_for_user(conn, _u(conn, org[key]))
        assert (scope, kind) == (path, "unit")


def test_admin_scopes_to_the_whole_bureau(org):
    conn = org["conn"]
    assert st.team_scope_for_user(conn, _u(conn, org["admin"])) == (None, "bureau")


def test_unlinked_account_gets_no_team_not_the_bureau(org):
    """The whole point of the helper. _org_scope_for_user returns None here —
    indistinguishable from an admin — which would have shown this account every
    wellness and work-arrangement filing in the bureau."""
    conn = org["conn"]
    user = _u(conn, org["unlinked"])

    assert st.team_scope_for_user(conn, user) == (None, "none")

    # and the underlying helper really is the trap being guarded against
    assert st._org_scope_for_user(conn, user) is None
    assert st._path_in_scope("TSCOPE/D2/S2", None) is True


def test_scope_does_not_leak_across_sibling_sections(org):
    """A prefix test done with bare startswith would let 'TSCOPE/D1/S1' match a
    sibling like 'TSCOPE/D1/S10'. _path_in_scope requires a separator."""
    assert st._path_in_scope("TSCOPE/D1/S1", "TSCOPE/D1/S1") is True
    assert st._path_in_scope("TSCOPE/D1/S1/Team", "TSCOPE/D1/S1") is True
    assert st._path_in_scope("TSCOPE/D1/S10", "TSCOPE/D1/S1") is False
    assert st._path_in_scope("TSCOPE/D2/S2", "TSCOPE/D1/S1") is False


def test_week_rollup_is_scoped_and_carries_face_columns(org):
    """wellness_week_rollup is what the landing page reads instead of the full
    wellness_dashboard_data. It must scope like its parent and carry the joined
    columns a faces grid needs, without a second query."""
    conn = org["conn"]
    week = st.wellness_week_start()

    roll = st.wellness_week_rollup(conn, week, _u(conn, org["s1"]))
    names = {r["name"] for r in roll["rows"]}
    assert "TS-One" in names
    assert "TS-Two" not in names                      # the other division
    assert roll["scope_path"] == "TSCOPE/D1/S1"

    row = next(r for r in roll["rows"] if r["name"] == "TS-One")
    for key in ("rp_id", "has_photo", "avatar_kind", "position", "designation",
                "org_path", "used", "left"):
        assert key in row, key

    # an admin sees both sections
    all_names = {r["name"] for r in
                 st.wellness_week_rollup(conn, week, _u(conn, org["admin"]))["rows"]}
    assert {"TS-One", "TS-Two"} <= all_names


def test_dashboard_data_still_agrees_with_the_rollup(org):
    """wellness_dashboard_data is now built ON wellness_week_rollup. The point of
    that split is that the monitoring register and the landing page can never
    quietly disagree — so assert the shared numbers are literally the same."""
    conn = org["conn"]
    user = _u(conn, org["s1_chief"])
    week = st.wellness_week_start()

    roll = st.wellness_week_rollup(conn, week, user)
    full = st.wellness_dashboard_data(conn, week, user)

    assert [r["user_id"] for r in full["rows"]] == [r["user_id"] for r in roll["rows"]]
    assert full["week_used"] == roll["week_used"]
    assert full["week_entitled"] == roll["week_entitled"]
    assert full["week_pct"] == roll["week_pct"]
    assert full["sections"] == roll["sections"]
    # ...and the full view still adds what the cheap one deliberately drops
    assert "queue" in full and "reflect_rate" in full
    assert "queue" not in roll


def test_roster_carries_face_columns_without_a_second_query(org):
    conn = org["conn"]
    period = st.work_arrangement_period()
    roster = st.work_arrangement_roster(conn, period, _u(conn, org["s1"]))
    assert roster, "expected the viewer's own section on the roster"
    for key in ("rp_id", "has_photo", "avatar_kind"):
        assert key in roster[0], key
    assert {r["name"] for r in roster} == {"TS-One", "TS-One Chief"}


def test_activity_instances_expose_the_creator(app_mod):
    """The creator relation is one of the few links between a STAFF MEMBER and an
    activity (attendees are external registrants with no account), so the CSS
    panel needs this column."""
    conn = st.connect(app_mod.DB)
    try:
        st.init_db(conn)
        conn.execute("DELETE FROM form_instance WHERE qr_token = 'ts-creator-tok'")
        conn.execute(
            "INSERT INTO form_instance(survey_type, form, qr_token, event_date,"
            " topic, created_by) VALUES (2,'F2','ts-creator-tok','2026-08-01',"
            " 'TS Creator Probe','ts-owner@test.local')")
        conn.commit()
        rows = st.list_activity_instances(conn)
        mine = [r for r in rows if r["topic"] == "TS Creator Probe"]
        assert mine, "the probe row should come back from list_activity_instances"
        assert mine[0]["created_by"] == "ts-owner@test.local"
        assert all("created_by" in r for r in rows)
    finally:
        conn.execute("DELETE FROM form_instance WHERE qr_token = 'ts-creator-tok'")
        conn.commit()
        conn.close()
