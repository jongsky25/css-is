"""
Office Connect landing payload (office_connect.team_view_data).

Pure assembly, so these tests drive it directly with injected cache primitives —
no HTTP, no route. The `view_memo` seam is what makes that possible: a fake memo
hands `_activity_index` a fabricated events list, so the activity predicates can
be tested without seeding a whole atoms DataFrame.

The load-bearing assertions are the SCOPE ones. This page has no chief-only route
guard, so a mistake there shows one section another section's filings.
"""
from __future__ import annotations

import pandas as pd
import pytest

import office_connect as oc
import storage as st


# --- injected cache primitives ---------------------------------------------

def _atoms(_conn):
    """An empty atoms frame. The events list is injected via the memo instead,
    so nothing here depends on seeded survey responses."""
    return pd.DataFrame()


def _memo_with(events):
    """A no-op memo that serves a fabricated 'events' view and recomputes
    everything else. Mirrors app.view_memo's (name, key_parts, builder) shape."""
    def memo(name, _key, builder):
        return list(events) if name == "events" else builder()
    return memo


def _caching_memo_with(events):
    """Same, but a real dict-backed cache — used to prove that a WARM index does
    not leak between viewers (the index is bureau-wide by design; the filtering
    that keeps teams apart happens per request)."""
    store = {}
    def memo(name, key, builder):
        if name == "events":
            return list(events)
        k = (name, key)
        if k not in store:
            store[k] = builder()
        return store[k]
    return memo


def _event(eid, *, instance_ids, name="Activity", date="2026-08-10",
           respondents=40, overall=6.4, band="Excellent", speakers=()):
    """A build_events-shaped event. Only the keys _activity_index reads."""
    f2 = None
    if overall is not None:
        f2 = {"overall": overall, "overall_shown": f"{overall:.1f}", "band": band,
              "respondents": respondents}
    return {"id": eid, "name": name, "date": date, "venue": "Room A",
            "organizer": "Bureau", "respondents": respondents, "f2": f2,
            "speakers": [dict(s) for s in speakers], "instance_ids": list(instance_ids),
            "closed": True, "end_date": None, "is_external": False}


# --- fixture ----------------------------------------------------------------

@pytest.fixture
def world(app_mod):
    """Two sections in different divisions, each with a person and an activity
    they ran, plus an unlinked account. Sections are named so that one is a
    strict string prefix of a sibling (S1 vs S10) — the boundary a bare
    startswith would get wrong."""
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    # Order matters: form_instance -> org_unit and admin_user -> resource_person
    # -> org_unit are real foreign keys, so children go first.
    conn.execute("DELETE FROM form_instance WHERE qr_token LIKE 'oc-tok-%'")
    conn.execute("DELETE FROM admin_user WHERE username LIKE 'oc-%@test.local'")
    conn.execute("DELETE FROM resource_person WHERE name LIKE 'OC-%'")
    conn.execute("DELETE FROM org_unit WHERE path LIKE 'OCT%'")

    unit = {}
    for path, short in (("OCT/D1/S1", "S1"), ("OCT/D1/S10", "S10")):
        unit[path] = conn.execute(
            "INSERT INTO org_unit(name, short_name, level, path) VALUES (?,?,?,?)",
            (short, short, "section", path)).lastrowid

    def person(name, path):
        return conn.execute(
            "INSERT INTO resource_person(name, is_internal, org_unit_id)"
            " VALUES (?,1,?)", (name, unit[path])).lastrowid

    rp_a = person("OC-Ana", "OCT/D1/S1")
    rp_b = person("OC-Ben", "OCT/D1/S10")
    rp_c = person("OC-Cy", "OCT/D1/S1")

    def account(u, role, rp=None):
        return st.create_admin_user(conn, u, "x", "y", role, rp_id=rp)

    a = account("oc-ana@test.local", "viewer", rp_a)
    b = account("oc-ben@test.local", "viewer", rp_b)
    unlinked = account("oc-none@test.local", "viewer")
    admin = account("oc-adm@test.local", "admin")
    # an admin-ROLE account the DIRECTORY puts in S1 — the role buys no extra reach
    admin_s1 = account("oc-adm-s1@test.local", "admin", rp_c)

    def instance(tok, path, created_by):
        return conn.execute(
            "INSERT INTO form_instance(survey_type, form, qr_token, event_date,"
            " topic, lead_org_id, created_by) VALUES (2,'F2',?,?,?,?,?)",
            (tok, "2026-08-10", f"Activity {tok}", unit[path], created_by)).lastrowid

    fi_a = instance("oc-tok-a", "OCT/D1/S1", "oc-ana@test.local")
    fi_b = instance("oc-tok-b", "OCT/D1/S10", "oc-ben@test.local")
    conn.commit()
    yield {"conn": conn, "ana": a, "ben": b, "unlinked": unlinked, "admin": admin,
           "admin_s1": admin_s1, "rp_ana": rp_a, "rp_ben": rp_b, "rp_cy": rp_c,
           "fi_a": fi_a, "fi_b": fi_b}
    conn.close()


def _u(conn, uid):
    r = st.get_admin_user_by_id(conn, uid)
    return {"id": r["id"], "username": r["username"], "role": r["role"]}


def _events_for(world):
    """Ana's activity (she both ran and spoke at it) and Ben's (his section)."""
    return [
        _event(world["fi_a"], instance_ids=[world["fi_a"]], name="Ana's activity",
               speakers=[{"rp_id": world["rp_ana"], "name": "OC-Ana", "value": 6.6,
                          "shown": "6.6", "band": "Excellent", "hidden": False}]),
        _event(world["fi_b"], instance_ids=[world["fi_b"]], name="Ben's activity",
               speakers=[{"rp_id": world["rp_ben"], "name": "OC-Ben", "value": 5.9,
                          "shown": "5.9", "band": "Good", "hidden": False}]),
    ]


def _payload(world, who, memo=None):
    conn = world["conn"]
    return oc.team_view_data(conn, _u(conn, world[who]), get_atoms=_atoms,
                             view_memo=memo or _memo_with(_events_for(world)))


# --- scope ------------------------------------------------------------------

def test_scope_resolves_per_viewer(world):
    assert _payload(world, "ana")["scope"]["kind"] == "unit"
    assert _payload(world, "ana")["scope"]["path"] == "OCT/D1/S1"
    assert _payload(world, "unlinked")["scope"]["kind"] == "none"


def test_the_directory_decides_the_scope_not_the_app_role(world):
    """An admin the directory places in S1 gets S1 — the same team Ana gets, and
    nothing from S10. An admin with no directory record has no team at all,
    exactly like any other unlinked account."""
    adm = _payload(world, "admin_s1")
    assert adm["scope"]["kind"] == "unit"
    assert adm["scope"]["path"] == "OCT/D1/S1"
    assert "OC-Ben" not in repr(adm)

    assert _payload(world, "admin")["scope"]["kind"] == "none"
    assert _payload(world, "admin")["panels"]["wellness"]["team"] is None


def test_unlinked_account_gets_no_team_payload_at_all(world):
    """The guard that matters. Not an empty team — NO team, and no colleague
    from any section anywhere in the payload."""
    p = _payload(world, "unlinked")

    for key in ("wellness", "awa", "css"):
        assert p["panels"][key]["team"] is None, key
    assert p["scope"]["size"] == 0
    assert any(n["key"] == "unlinked" for n in p["notes"])

    blob = repr(p)
    assert "OC-Ana" not in blob and "OC-Ben" not in blob


def test_two_sections_never_see_each_other(world):
    ana = _payload(world, "ana")
    ben = _payload(world, "ben")

    ana_people = {c["name"] for c in ana["panels"]["wellness"]["team"]["cells"]}
    ben_people = {c["name"] for c in ben["panels"]["wellness"]["team"]["cells"]}

    assert "OC-Ana" in ana_people and "OC-Ben" not in ana_people
    assert "OC-Ben" in ben_people and "OC-Ana" not in ben_people
    assert not (ana_people & ben_people)


def test_sibling_section_is_not_a_prefix_match(world):
    """OCT/D1/S1 must not swallow OCT/D1/S10. A bare startswith would."""
    ana = _payload(world, "ana")
    names = [r["name"] for r in ana["panels"]["css"]["team"]["rows"]]
    assert "Ana's activity" in names
    assert "Ben's activity" not in names


@pytest.mark.parametrize("order", [("ana", "ben"), ("ben", "ana")])
def test_warm_index_does_not_leak_between_viewers(world, order):
    """The activity index is bureau-wide and shared on purpose. Prove that a
    WARM one still yields per-viewer results, in both request orders."""
    memo = _caching_memo_with(_events_for(world))
    first = _payload(world, order[0], memo=memo)
    second = _payload(world, order[1], memo=memo)

    def acts(p):
        return {r["name"] for r in p["panels"]["css"]["team"]["rows"]}

    assert acts(first) != acts(second)
    assert not (acts(first) & acts(second))


# --- the CSS predicate ------------------------------------------------------

def test_personal_matches_speaker_and_creator_roles(world):
    p = _payload(world, "ana")
    rows = p["panels"]["css"]["personal"]["rows"]
    assert [r["name"] for r in rows] == ["Ana's activity"]
    # she filed it AND spoke at it, so both roles are named
    assert rows[0]["roles"] == ["ran", "spoke"]
    assert p["panels"]["css"]["personal"]["linked"] is True


def test_personal_still_works_without_a_directory_link(world):
    """An account with no rp_id can never match as a speaker, but creator
    matching is on the username and still works."""
    conn = world["conn"]
    conn.execute("UPDATE form_instance SET created_by=? WHERE id=?",
                 ("oc-none@test.local", world["fi_a"]))
    conn.commit()

    p = _payload(world, "unlinked")
    rows = p["panels"]["css"]["personal"]["rows"]
    assert [r["name"] for r in rows] == ["Ana's activity"]
    assert rows[0]["roles"] == ["ran"]
    assert p["panels"]["css"]["personal"]["linked"] is False


def test_team_rows_say_how_each_one_qualified(world):
    row = _payload(world, "ana")["panels"]["css"]["team"]["rows"][0]
    assert "unit" in row["roles"]          # her section ran it
    assert "spoke" in row["roles"]         # and one of hers spoke
    assert row["who"] == ["OC-Ana"]


def test_no_internal_sets_leak_into_the_payload(world):
    """rp_ids/creators/lead_paths are matching machinery, not display data —
    and sets aren't JSON-serialisable, so they must not reach the template."""
    for scope in ("personal", "team"):
        for row in _payload(world, "ana")["panels"]["css"][scope]["rows"]:
            assert not ({"rp_ids", "creators", "lead_paths"} & set(row))


# --- scores -----------------------------------------------------------------

def test_low_n_is_flagged_not_hidden(world):
    events = [_event(world["fi_a"], instance_ids=[world["fi_a"]],
                     name="Thin activity", respondents=3, overall=7.0)]
    p = _payload(world, "ana", memo=_memo_with(events))
    row = p["panels"]["css"]["team"]["rows"][0]
    assert row["low_n"] is True
    assert row["respondents"] == 3
    assert row["shown"] == "7.0"           # shown, so nobody thinks it vanished


def test_f3_only_activity_avoids_the_404_route(world):
    """/reports/activities/{id} 404s when there is no Form-2 block, so an
    f3-only activity must link to the type-3 report instead."""
    events = [_event(world["fi_a"], instance_ids=[world["fi_a"]], overall=None,
                     name="Speaker only",
                     speakers=[{"rp_id": world["rp_ana"], "name": "OC-Ana",
                                "value": 6.1, "shown": "6.1", "band": "Good",
                                "hidden": False}])]
    row = _payload(world, "ana", memo=_memo_with(events))["panels"]["css"]["team"]["rows"][0]
    assert row["f3_only"] is True
    assert row["score_kind"] == "speaker"
    assert row["shown"] == "6.1"
    assert row["url"] == f"/reports?type=3&activity={world['fi_a']}"


def test_activity_with_no_score_at_all_is_still_listed(world):
    events = [_event(world["fi_a"], instance_ids=[world["fi_a"]], overall=None,
                     name="Unscored")]
    row = _payload(world, "ana", memo=_memo_with(events))["panels"]["css"]["team"]["rows"][0]
    assert row["score"] is None and row["score_kind"] is None
    assert row["tone"] == "soft"


# --- the other two panels ---------------------------------------------------

def test_wellness_panel_carries_faces_rings_and_an_sr_table(world):
    team = _payload(world, "ana")["panels"]["wellness"]["team"]
    cell = team["cells"][0]

    assert cell["state"] == "none" and cell["tone"] == "soft"
    assert cell["ring"]["dash"] == 0.0            # nothing filed -> empty ring
    assert cell["initials"] == "O"                # "OC-Ana" is one token
    assert cell["photo_url"] is None              # no photo -> companion/initials
    # the chart needs its screen-reader fallback (tests/test_a11y_charts.py rule)
    assert team["table"]["headers"][0] == "Person"
    assert len(team["table"]["rows"]) == len(team["cells"])
    assert "percent" in team["aria_label"]


def test_awa_panel_leads_with_the_period_open_for_filing(world):
    """Not the period in force: its deadline is the Friday before it starts, so
    by the time it is current it is closed and affords no action."""
    p = _payload(world, "ana")["panels"]["awa"]
    open_ps = st.work_arrangement_open_periods()

    assert p["personal"]["period_label"] == st.work_arrangement_period_label(open_ps[0])
    assert p["personal"]["in_force"]["period_label"] == \
        st.work_arrangement_period_label(st.work_arrangement_period())
    assert p["personal"]["state"] in ("open", "closing_today")
    assert p["team"]["headcount"] >= 1
    assert p["team"]["coverage"]["table"]["headers"][0] == "Weekday"


def test_awa_team_view_always_carries_the_coverage_chart(world):
    """Every team view is now a directory unit — there is no bureau-wide fan-out
    to defer — so the weekday coverage chart is always built."""
    p = _payload(world, "admin_s1")["panels"]["awa"]
    assert p["team"] is not None
    assert p["team"]["coverage"]["bars"], "expected Mon-Fri bars for a unit scope"


# --- geometry ---------------------------------------------------------------

def test_ring_geom_is_a_closed_dasharray():
    import dashboard_insights as di
    full, half, empty = di.ring_geom(100), di.ring_geom(50), di.ring_geom(0)
    assert full["gap"] == 0.0
    assert empty["dash"] == 0.0
    assert round(half["dash"] + half["gap"], 1) == round(half["circ"], 1)
    # out-of-range input is clamped, never negative
    assert di.ring_geom(150)["gap"] == 0.0
    assert di.ring_geom(-10)["dash"] == 0.0


def test_bars_geom_flags_the_thin_day_and_emits_no_colour():
    import dashboard_insights as di
    totals = [{"idx": 0, "name": "Monday", "onsite": 8, "offsite": 2,
               "empty_sections": []},
              {"idx": 4, "name": "Friday", "onsite": 0, "offsite": 10,
               "empty_sections": ["S1"]}]
    g = di.bars_geom(totals, 10)

    assert g["bars"][0]["onsite"]["tone"] == "green"
    assert g["bars"][1]["onsite"]["tone"] == "red"      # nobody on-site
    assert g["bars"][1]["thin"] is True
    assert g["thinnest"]["name"] == "Friday"
    assert g["table"]["rows"][1][3] == "S1"
    # tones only — a literal hex would break 35 of the 36 theme/accent combos
    assert "#" not in repr(g)


def test_initials_handle_the_directory_name_format():
    """The directory stores 'Surname, First', so the comma has to split like a
    space or everyone in the bureau gets a single letter."""
    assert oc._initials("Reyes, Ana Maria") == "RA"
    assert oc._initials("Ana Reyes") == "AR"
    assert oc._initials("Madonna") == "M"
    assert oc._initials("") == "?"
    assert oc._initials(None) == "?"
