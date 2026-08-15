"""
Team-scope resolution — the guard that keeps the Office Connect landing page
from showing one person another team's filings.

The landing page shows EVERY signed-in user their team, with no chief-only route
guard in front of it. That removes the assumption `_org_scope_for_user` is
written under — an account with no directory org unit monitors everyone — so an
account with no directory link must resolve to "no team" here rather than falling
through to the whole bureau.

The DIRECTORY is what decides the team, not the app role. An `admin` role is a
permission to operate the system; it is not standing over every section's
wellness and work-arrangement filings, and it no longer grants a bureau-wide
view. Bureau-wide is reached one way: by being recorded at a unit the sections
hang off, whose subtree is everyone.
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
    for path, short, level in (("TSCOPE", "TSCOPE", "division"),
                               ("TSCOPE/D1/S1", "S1", "section"),
                               ("TSCOPE/D2/S2", "S2", "section")):
        units[path] = conn.execute(
            "INSERT INTO org_unit(name, short_name, level, path) VALUES (?,?,?,?)",
            (short, short, level, path)).lastrowid
    def person(name, unit, designation=""):
        return conn.execute(
            "INSERT INTO resource_person(name, is_internal, org_unit_id, designation)"
            " VALUES (?,1,?,?)", (name, unit, designation)).lastrowid
    s1_rp = person("TS-One", units["TSCOPE/D1/S1"])
    s1_chief_rp = person("TS-One Chief", units["TSCOPE/D1/S1"], "Section Head")
    s2_rp = person("TS-Two", units["TSCOPE/D2/S2"])
    s1_adm_rp = person("TS-One Admin", units["TSCOPE/D1/S1"])
    # No designation: a seat title here would enter the bureau-wide org chain and
    # change who other suites' escalation tests resolve as an approver.
    top_rp = person("TS-Top", units["TSCOPE"])
    mk = lambda u, role, rp: st.create_admin_user(conn, u, "x", "y", role, rp_id=rp)
    out = {
        "conn": conn,
        "s1": mk("ts-s1@test.local", "viewer", s1_rp),
        "s1_chief": mk("ts-s1chief@test.local", "section_manager", s1_chief_rp),
        "s2": mk("ts-s2@test.local", "viewer", s2_rp),
        "unlinked": st.create_admin_user(conn, "ts-none@test.local", "x", "y", "viewer"),
        "admin": st.create_admin_user(conn, "ts-adm@test.local", "x", "y", "admin"),
        # an admin-role account the DIRECTORY places in one section, and a
        # viewer-role account the directory places above both sections
        "s1_admin": mk("ts-s1adm@test.local", "admin", s1_adm_rp),
        "top": mk("ts-top@test.local", "viewer", top_rp),
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


def test_the_directory_decides_the_team_not_the_app_role(org):
    """An `admin` role is a permission to operate the system, not standing over
    every section's filings. An admin the directory places in S1 gets S1 —
    exactly what a viewer in the same seat gets."""
    conn = org["conn"]
    assert st.team_scope_for_user(conn, _u(conn, org["s1_admin"])) == \
        ("TSCOPE/D1/S1", "unit")
    assert st._org_scope_for_user(conn, _u(conn, org["s1_admin"])) == "TSCOPE/D1/S1"


def test_a_seat_above_the_sections_sees_every_section_below_it(org):
    """Scope is a pure path-SUBTREE test, so someone recorded at an ancestor unit
    — a division, or the bureau-level unit every section hangs off — sees
    everything beneath it. That is now the only route to a bureau-wide view, and
    it comes from the directory."""
    conn = org["conn"]
    scope, kind = st.team_scope_for_user(conn, _u(conn, org["top"]))
    assert (scope, kind) == ("TSCOPE", "unit")
    assert st._path_in_scope("TSCOPE/D1/S1", scope) is True
    assert st._path_in_scope("TSCOPE/D2/S2", scope) is True


def test_admin_with_no_directory_link_gets_no_team_either(org):
    """The role used to be a shortcut to the whole bureau. It no longer is: an
    admin with nothing in the directory has no team to show, and the landing page
    must offer the personal view and the 'link your profile' note instead."""
    conn = org["conn"]
    assert st.team_scope_for_user(conn, _u(conn, org["admin"])) == (None, "none")


def test_unlinked_account_gets_no_team_not_the_bureau(org):
    """The whole point of the helper. _org_scope_for_user returns None here —
    indistinguishable from an unscoped bureau-wide call — which would have shown
    this account every wellness and work-arrangement filing in the bureau."""
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

    # an ADMIN-role account the directory places in S1 sees S1 and nothing else
    adm_names = {r["name"] for r in
                 st.wellness_week_rollup(conn, week, _u(conn, org["s1_admin"]))["rows"]}
    assert "TS-One" in adm_names
    assert "TS-Two" not in adm_names

    # a seat above both sections sees both; an unscoped call still sees everyone
    top_names = {r["name"] for r in
                 st.wellness_week_rollup(conn, week, _u(conn, org["top"]))["rows"]}
    assert {"TS-One", "TS-Two"} <= top_names
    assert {"TS-One", "TS-Two"} <= {r["name"] for r in
                                    st.wellness_week_rollup(conn, week)["rows"]}


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
    assert {r["name"] for r in roster} == {"TS-One", "TS-One Chief", "TS-One Admin"}


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
