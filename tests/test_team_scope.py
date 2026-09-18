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
    _wipe(conn)
    units = {}
    for path, short, level in (("TSCOPE/D1/S1", "S1", "section"),
                               ("TSCOPE/D2/S2", "S2", "section"),
                               ("TSCOPE/OD", "OD", "office")):
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
    s2_chief_rp = person("TS-Two Chief", units["TSCOPE/D2/S2"], "Section Head")
    # A section head who ALSO holds the admin role, and a Director who does not:
    # the two cases that tell "team comes from the directory" apart from "team
    # comes from the account role".
    s1_chief_admin_rp = person("TS-One Chief Two", units["TSCOPE/D1/S1"], "Section Head")
    director_rp = conn.execute(
        "INSERT INTO resource_person(name, is_internal, org_unit_id, designation, position)"
        " VALUES (?,1,?,?,?)",
        ("TS-Director", units["TSCOPE/OD"], None, "Director IV")).lastrowid
    mk = lambda u, role, rp: st.create_admin_user(conn, u, "x", "y", role, rp_id=rp)
    out = {
        "conn": conn,
        "s1": mk("ts-s1@test.local", "viewer", s1_rp),
        "s1_chief": mk("ts-s1chief@test.local", "section_manager", s1_chief_rp),
        "s1_chief_admin": mk("ts-s1chiefadm@test.local", "admin", s1_chief_admin_rp),
        "s2": mk("ts-s2@test.local", "viewer", s2_rp),
        "s2_chief": mk("ts-s2chief@test.local", "section_manager", s2_chief_rp),
        "director": mk("ts-dir@test.local", "viewer", director_rp),
        "unlinked": st.create_admin_user(conn, "ts-none@test.local", "x", "y", "viewer"),
        "admin": st.create_admin_user(conn, "ts-adm@test.local", "x", "y", "admin"),
    }
    conn.commit()
    yield out
    # Wipe on the way OUT as well as on the way in. The DB is session-scoped, so
    # anything this fixture leaves behind is visible to every later module — and
    # this one seats a DIRECTOR, which the escalation chain looks for bureau-wide
    # with no org path. Left in place it becomes a second Director for
    # test_wellness's chain tests, which is a failure in someone else's file.
    _wipe(conn)
    conn.commit()
    conn.close()


def _wipe(conn):
    """Remove every row this fixture creates. Claims outlive the accounts that
    filed them (no FK cascade) and list_wellness_approvals reads wellness_claim
    directly, so those go first or they resurface under a reused id."""
    conn.execute("DELETE FROM wellness_reflection WHERE claim_id IN"
                 " (SELECT id FROM wellness_claim WHERE user_id IN"
                 "  (SELECT id FROM admin_user WHERE username LIKE 'ts-%@test.local'))")
    conn.execute("DELETE FROM wellness_claim WHERE user_id IN"
                 " (SELECT id FROM admin_user WHERE username LIKE 'ts-%@test.local')")
    conn.execute("DELETE FROM wellness_claim WHERE user_id NOT IN (SELECT id FROM admin_user)")
    conn.execute("DELETE FROM admin_user WHERE username LIKE 'ts-%@test.local'")
    conn.execute("DELETE FROM resource_person WHERE name LIKE 'TS-%'")
    conn.execute("DELETE FROM org_unit WHERE path LIKE 'TSCOPE%'")


def _u(conn, uid):
    r = st.get_admin_user_by_id(conn, uid)
    return {"id": r["id"], "username": r["username"], "role": r["role"]}


def test_linked_staff_scope_to_their_own_unit(org):
    conn = org["conn"]
    for key, path in (("s1", "TSCOPE/D1/S1"), ("s2", "TSCOPE/D2/S2")):
        scope, kind = st.team_scope_for_user(conn, _u(conn, org[key]))
        assert (scope, kind) == (path, "unit")


def test_an_admin_with_no_seat_has_no_team_until_it_is_granted(org):
    """The role is not a way to see everyone, not even for a system administrator
    with no seat on the org chart. They get the personal view and the "link your
    profile" note — and, when they genuinely need the bureau, an explicit
    bureau_access grant that is set per account, audited and revocable
    (BUREAU_ACCESS_LEVELS; see tests/test_bureau_access.py). Same reach as the
    old role shortcut, named rather than implied."""
    conn = org["conn"]
    admin = _u(conn, org["admin"])
    assert st.team_scope_for_user(conn, admin) == (None, "none")

    st.set_bureau_access(conn, org["admin"], "all")
    try:
        assert st.team_scope_for_user(conn, admin) == (None, "bureau")
    finally:
        st.set_bureau_access(conn, org["admin"], "")


def test_the_directory_outranks_the_account_role(org):
    """THE RULE: where someone sits on the org chart decides their team; "admin"
    decides what they may administer. A section head who also administers the app
    used to open the wellness register and the AWA schedule on every section,
    because this short-circuited on role == "admin" before it ever looked at the
    directory. Their team is their section, same as any other section head."""
    conn = org["conn"]
    linked_admin = _u(conn, org["s1_chief_admin"])
    assert linked_admin["role"] == "admin"

    assert st.team_scope_for_user(conn, linked_admin) == ("TSCOPE/D1/S1", "unit")
    assert st._org_scope_for_user(conn, linked_admin) == "TSCOPE/D1/S1"

    # ...and it really is scoped downstream, not just in the helper
    roll = st.wellness_week_rollup(conn, st.wellness_week_start(), linked_admin)
    names = {r["name"] for r in roll["rows"]}
    assert "TS-One" in names and "TS-Two" not in names


def test_the_director_still_gets_the_whole_bureau(org):
    """The one directory seat that is NOT scoped to its own unit: the Director's
    team is the bureau, and the Office of the Director is not it. Rank is read
    from position too (_org_rank), which is where 'Director IV' lives."""
    conn = org["conn"]
    director = _u(conn, org["director"])
    assert director["role"] == "viewer"          # not an admin — the seat decides
    assert st.team_scope_for_user(conn, director) == (None, "bureau")


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


def test_the_approvals_queue_follows_the_chain_not_the_role(org, future_weekday):
    """Same rule, applied to the queue: an admin is the fallback ABOVE the chain,
    not a bypass around it. A section head who administers the app used to open a
    queue holding every section's routine claims; now they get their own chain's
    claims plus the ORPHANS — the ones no chief can reach — so nothing is
    stranded and nothing routine leaks sideways."""
    conn = org["conn"]
    day = future_weekday
    st.create_wellness_claim(conn, org["s1"], day, "09:00", "exercise")
    st.create_wellness_claim(conn, org["s2"], day, "10:00", "exercise")
    st.create_wellness_claim(conn, org["unlinked"], day, "11:00", "exercise")

    def claimants(uid):
        return {c["user_id"] for c in st.list_wellness_approvals(conn, _u(conn, uid))}

    # the S1 section head, who is also an admin: their own section's claim...
    mine = claimants(org["s1_chief_admin"])
    assert org["s1"] in mine
    assert org["s2"] not in mine                   # the other division's — not theirs
    assert org["unlinked"] in mine                 # ...plus the orphan nobody can reach

    # a section head who is NOT an admin gets their chain and nothing else
    plain = claimants(org["s1_chief"])
    assert plain == {org["s1"]}

    # and an admin with no seat on the org chart still catches every orphan
    assert org["unlinked"] in claimants(org["admin"])


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
                 st.wellness_week_rollup(conn, week,
                                         _u(conn, org["s1_chief_admin"]))["rows"]}
    assert "TS-One" in adm_names
    assert "TS-Two" not in adm_names

    # the Director sees both; so does an unscoped call (the bureau-wide exports)
    dir_names = {r["name"] for r in
                 st.wellness_week_rollup(conn, week, _u(conn, org["director"]))["rows"]}
    assert {"TS-One", "TS-Two"} <= dir_names
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
    assert {r["name"] for r in roster} == {"TS-One", "TS-One Chief", "TS-One Chief Two"}


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
