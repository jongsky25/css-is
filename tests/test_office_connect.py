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

from datetime import date

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


def _payload(world, who, memo=None, today=None):
    """`today` is worth passing for anything that asserts on the WINDOW: left to
    the real clock, a test with fixed event dates passes today and silently stops
    exercising anything the day those dates age out of the 90-day cut."""
    conn = world["conn"]
    return oc.team_view_data(conn, _u(conn, world[who]), get_atoms=_atoms,
                             view_memo=memo or _memo_with(_events_for(world)),
                             **({"today": today} if today else {}))


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

def test_personal_is_speaking_only(world):
    """"Me" is the one view whose claim is about YOU, so it is the narrowest:
    speaker matches, nothing else. Ana both filed and spoke at hers, and only
    the speaking is what puts it on her card."""
    p = _payload(world, "ana")
    rows = p["panels"]["css"]["personal"]["rows"]
    assert [r["name"] for r in rows] == ["Ana's activity"]
    assert rows[0]["roles"] == ["spoke"]
    assert p["panels"]["css"]["personal"]["linked"] is True


def test_creating_an_activity_does_not_put_it_on_your_own_card(world):
    """`created_by` records who filled in the form, which is a fact about the
    app, not about whose work the activity was."""
    conn = world["conn"]
    conn.execute("UPDATE form_instance SET created_by=? WHERE id=?",
                 ("oc-ana@test.local", world["fi_b"]))
    conn.commit()

    rows = _payload(world, "ana")["panels"]["css"]["personal"]["rows"]
    assert "Ben's activity" not in [r["name"] for r in rows]


def test_personal_is_empty_without_a_directory_link(world):
    """An account with no rp_id can never match as a speaker, and creating is
    no longer a way in — so an unlinked account matches nothing at all. The
    card's own empty state is what explains why."""
    conn = world["conn"]
    conn.execute("UPDATE form_instance SET created_by=? WHERE id=?",
                 ("oc-none@test.local", world["fi_a"]))
    conn.commit()

    p = _payload(world, "unlinked")
    assert p["panels"]["css"]["personal"]["rows"] == []
    assert p["panels"]["css"]["personal"]["linked"] is False


def test_team_rows_say_how_each_one_qualified(world):
    row = _payload(world, "ana")["panels"]["css"]["team"]["rows"][0]
    assert "unit" in row["roles"]          # her section ran it
    assert "spoke" in row["roles"]         # and one of hers spoke
    assert row["who"] == ["OC-Ana"]


def test_an_admin_filing_for_another_section_stays_out_of_both_views(world):
    """THE REGRESSION THIS SUITE EXISTS FOR. An administrator sets activities up
    for sections all over the bureau; `created_by` used to qualify a row on its
    own, so every one of them landed on that administrator's card and on their
    section's. The organising unit is what decides."""
    conn = world["conn"]
    # the S1-seated admin files S10's activity. Nobody from S1 speaks at it.
    conn.execute("UPDATE form_instance SET created_by=? WHERE id=?",
                 ("oc-adm-s1@test.local", world["fi_b"]))
    conn.commit()

    p = _payload(world, "admin_s1")
    assert p["scope"]["path"] == "OCT/D1/S1"
    names = [r["name"] for r in p["panels"]["css"]["team"]["rows"]]
    assert "Ben's activity" not in names   # S10's, and filing it changes nothing
    assert names == ["Ana's activity"]     # S1's own is still there
    assert p["panels"]["css"]["personal"]["rows"] == []   # they spoke at neither


def test_a_teammate_speaking_elsewhere_still_counts_for_the_team(world):
    """The other half of the rule: work your people actually did at another
    section's event is still your team's work."""
    conn = world["conn"]
    events = [_event(world["fi_b"], instance_ids=[world["fi_b"]],
                     name="S10's activity",
                     speakers=[{"rp_id": world["rp_ana"], "name": "OC-Ana",
                                "value": 6.6, "shown": "6.6",
                                "band": "Excellent", "hidden": False}])]
    p = _payload(world, "ana", memo=_memo_with(events))
    row = p["panels"]["css"]["team"]["rows"][0]
    assert row["name"] == "S10's activity"
    assert row["roles"] == ["spoke"]        # not ours to run, but ours who spoke
    assert row["who"] == ["OC-Ana"]


def test_a_row_that_qualified_still_says_who_organised_it(world):
    """"Organised" survives as a CHIP on a row that already qualified — worth
    saying out loud, never a reason to be in the list."""
    row = _payload(world, "ana")["panels"]["css"]["team"]["rows"][0]
    assert "ran" in row["roles"]           # Ana filed it and Ana's section ran it


def test_no_internal_sets_leak_into_the_payload(world):
    """rp_ids/creators/lead_paths/speakers_by_rp are matching machinery, not
    display data — and sets aren't JSON-serialisable, so they must not reach the
    template."""
    for scope in ("personal", "team"):
        for row in _payload(world, "ana")["panels"]["css"][scope]["rows"]:
            assert not ({"rp_ids", "creators", "lead_paths",
                         "speakers_by_rp"} & set(row))


# --- the CSS insights deck --------------------------------------------------

def test_insights_read_the_same_activities_the_list_does(world):
    """The deck is built from the ids the predicate let through, so it can never
    disagree with the rows above it about which activities count."""
    p = _payload(world, "ana")
    assert p["panels"]["css"]["team"]["insights"]["total"] == 1
    assert p["panels"]["css"]["personal"]["insights"]["total"] == 1


def test_insights_are_none_when_there_is_nothing_to_draw(world):
    """An empty chart reads as "the data is broken" rather than "nothing has
    happened yet" — so there is no chart at all."""
    assert _payload(world, "unlinked")["panels"]["css"]["personal"]["insights"] is None


def test_every_insight_chart_ships_its_screen_reader_table(world):
    ins = _payload(world, "ana")["panels"]["css"]["team"]["insights"]
    for table in (ins["volume"]["table"], ins["mix_table"], ins["speakers_table"]):
        assert table["headers"] and table["rows"]
        assert table["caption"]


def test_insights_emit_tones_never_colours(world):
    """A hex here breaks 35 of the 36 theme x accent combinations."""
    assert "#" not in repr(_payload(world, "ana")["panels"]["css"]["team"]["insights"])


def test_the_deck_reads_the_same_window_as_the_list(world):
    """THE CARD MAKES ONE WINDOW CLAIM, in its header, and it has to be true on
    every slide under it. The deck used to quietly cover a year while the header
    said "Last 90 days", so four slides out of five were mislabelled."""
    cv = _payload(world, "ana")["panels"]["css"]["team"]
    assert oc.INSIGHT_DAYS == oc.WINDOW_DAYS
    assert cv["insights"]["window_days"] == cv["window_days"]


def test_the_volume_chart_covers_only_the_months_the_window_touches(world):
    """A 90-day window spans three or four calendar months depending on where in
    the month today falls — never a fixed twelve."""
    ins = _payload(world, "ana", today=date(2026, 8, 16))["panels"]["css"]["team"]["insights"]
    bars = [b["short"] for b in ins["volume"]["bars"]]
    assert bars == ["May", "Jun", "Jul", "Aug"]          # cut lands 2026-05-18
    assert len(ins["volume"]["bars"]) == ins["months"]
    assert ins["since"] == "May 18"                      # said out loud, not implied


def test_month_span_flags_the_partial_ends(world):
    """The first and last buckets of a 90-day window are part-months. Fine to
    draw — the bar is a true count of what happened inside the window — but not
    fine to rank, which is what the `whole` flag is for."""
    span = oc._month_span(date(2026, 5, 18), date(2026, 8, 16))
    assert [k for k, _w in span] == [(2026, 5), (2026, 6), (2026, 7), (2026, 8)]
    assert [w for _k, w in span] == [False, True, True, False]

    # a window landing exactly on month boundaries has no partial end
    span = oc._month_span(date(2026, 6, 1), date(2026, 7, 31))
    assert [w for _k, w in span] == [True, True]


_SPEAKER = {"name": "OC-Ana", "value": 6.6, "shown": "6.6",
            "band": "Excellent", "hidden": False}


def _on(world, *dates):
    """One event per date, all spoken at by Ana, so only the month matters."""
    speaker = {**_SPEAKER, "rp_id": world["rp_ana"]}
    return [_event(world["fi_a"] if i else world["fi_b"], name=f"Activity {i}",
                   instance_ids=[world["fi_a"] if i else world["fi_b"]],
                   date=d, speakers=[speaker])
            for i, d in enumerate(dates)]


def test_no_busiest_month_is_claimed_on_a_tie(world):
    """On a tie the superlative is simply false, and picking whichever month
    sorted first is how a chart ends up disagreeing with its own caption."""
    ins = _payload(world, "ana", memo=_memo_with(_on(world, "2026-07-10", "2026-06-10")),
                   today=date(2026, 8, 16))["panels"]["css"]["team"]["insights"]
    assert ins["total"] == 2
    assert "busiest" not in ins["said"]["volume"]
    assert ins["said"]["volume"].endswith(".")


def test_no_busiest_month_is_claimed_for_a_part_month(world):
    """A 90-day window ends mid-month, so August can "win" on sixteen days
    against July's thirty-one. That is not a fact about a month."""
    # August leads the chart outright — and is still not called the busiest,
    # because today is the 16th and the window only covers half of it.
    ins = _payload(world, "ana", memo=_memo_with(_on(world, "2026-08-10", "2026-07-10")),
                   today=date(2026, 8, 16))["panels"]["css"]["team"]["insights"]
    aug = next(b for b in ins["volume"]["bars"] if b["short"] == "Aug")
    assert aug["n"] == 1 and aug["peak"] is True          # it does lead the chart
    assert "busiest" not in ins["said"]["volume"]

    # a WHOLE month leading is said out loud
    ins = _payload(world, "ana",
                   memo=_memo_with(_on(world, "2026-07-10", "2026-07-20")),
                   today=date(2026, 8, 16))["panels"]["css"]["team"]["insights"]
    assert "Jul 2026 was the busiest with 2." in ins["said"]["volume"]


def test_who_spoke_most_ranks_the_team_not_outsiders(world):
    """An outside resource person topping your section's list is true but
    useless — the slide is asking who among US is carrying the speaking."""
    events = [_event(world["fi_a"], instance_ids=[world["fi_a"]],
                     name="Ana's activity",
                     speakers=[{"rp_id": world["rp_ana"], "name": "OC-Ana",
                                "value": 6.6, "shown": "6.6",
                                "band": "Excellent", "hidden": False},
                               {"rp_id": 99999, "name": "Someone external",
                                "value": 7.0, "shown": "7.0",
                                "band": "Excellent", "hidden": False}])]
    ins = _payload(world, "ana", memo=_memo_with(events))["panels"]["css"]["team"]["insights"]
    assert [s["label"] for s in ins["speakers"]] == ["OC-Ana"]
    assert "OC-Ana spoke at the most" in ins["said"]["speakers"]


def test_the_personal_rating_slide_reads_your_score_not_the_events(world):
    """The event review rates the EVENT. Handing you its score because you
    happened to speak there is the misleading claim to avoid."""
    events = [_event(world["fi_a"], instance_ids=[world["fi_a"]], overall=6.9,
                     band="Excellent", name="Ana's activity",
                     speakers=[{"rp_id": world["rp_ana"], "name": "OC-Ana",
                                "value": 4.9, "shown": "4.9", "band": "Fair",
                                "hidden": False}])]
    p = _payload(world, "ana", memo=_memo_with(events))
    mine = {m["label"]: m["n"] for m in p["panels"]["css"]["personal"]["insights"]["mix"]}
    team = {m["label"]: m["n"] for m in p["panels"]["css"]["team"]["insights"]["mix"]}
    assert mine["Fair"] == 1 and mine["Excellent"] == 0       # her own speaker band
    assert team["Excellent"] == 1 and team["Fair"] == 0       # the event's band


def test_a_thin_activity_is_counted_apart_from_the_bands(world):
    """A score nobody can read is not a "Poor" and not an "Excellent" — it gets
    its own row so the band mix stays a statement about ratings that hold up."""
    events = [_event(world["fi_a"], instance_ids=[world["fi_a"]],
                     name="Thin activity", respondents=3, overall=7.0)]
    ins = _payload(world, "ana", memo=_memo_with(events))["panels"]["css"]["team"]["insights"]
    mix = {m["label"]: m["n"] for m in ins["mix"]}
    assert mix["Too few responses to read"] == 1
    assert mix["Excellent"] == 0
    assert ins["said"]["mix"] is None      # nothing rated well enough to say so


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


def test_awa_panel_carries_the_worked_fortnight_and_the_filed_one_apart(world):
    """Two different fortnights, and the card needs both. `team` is the period
    open for filing — the only one that affords action, since a period's
    deadline is the Friday before it starts. `now` and `in_force` are the
    fortnight being WORKED, which is what the card leads with."""
    p = _payload(world, "ana")["panels"]["awa"]
    open_ps = st.work_arrangement_open_periods()
    worked = st.work_arrangement_period_label(st.work_arrangement_schedule_period())

    assert p["personal"]["period_label"] == st.work_arrangement_period_label(open_ps[0])
    assert p["personal"]["state"] in ("open", "closing_today")
    assert p["personal"]["in_force"]["period_label"] == worked

    assert p["team"]["period_label"] == st.work_arrangement_period_label(open_ps[0])
    assert p["team"]["headcount"] >= 1
    assert p["team"]["coverage"]["table"]["headers"][0] == "Weekday"

    # The worked fortnight is a summary of its own, never a slice of the filing
    # one — they cover different dates and different rosters.
    assert p["now"]["period_label"] == worked
    assert p["now"]["period_label"] != p["team"]["period_label"]
    assert p["now"]["coverage"]["table"]["headers"][0] == "Weekday"


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
