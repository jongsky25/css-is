"""
The landing page's insight decks — what the wellness and AWA cards say once you
swipe past the lead number.

Three layers, tested apart:
  * storage.wellness_pattern — the counts (WHEN a break is taken, what people do
    with it, whether it helped). Scoped exactly like wellness_week_rollup.
  * dashboard_insights.count_bars_geom / heat_geom — geometry, tone TOKENS and
    the chart_table fallback every chart in this app owes a screen reader.
  * the rendered page — that the slides are actually there, and that a deck
    still works with JavaScript switched off.
"""
from __future__ import annotations

from datetime import date, timedelta

import pytest

import dashboard_insights as di
import storage as st
from tests.conftest import _auth_client, in_the_directory


# --- fixture ----------------------------------------------------------------

def _wipe(conn):
    """Children before parents — wellness_reflection -> wellness_claim ->
    admin_user -> resource_person -> org_unit are all real foreign keys, and a
    delete in the wrong order fails the constraint and leaves the transaction
    open for the next test to trip over."""
    conn.execute(
        "DELETE FROM wellness_reflection WHERE claim_id IN (SELECT c.id"
        " FROM wellness_claim c JOIN admin_user a ON a.id = c.user_id"
        " WHERE a.username LIKE 'ins-%@test.local')")
    conn.execute(
        "DELETE FROM wellness_claim WHERE user_id IN (SELECT id FROM admin_user"
        " WHERE username LIKE 'ins-%@test.local')")
    conn.execute("DELETE FROM work_arrangement WHERE user_id IN (SELECT id FROM"
                 " admin_user WHERE username LIKE 'ins-%@test.local')")
    conn.execute("DELETE FROM admin_user WHERE username LIKE 'ins-%@test.local'")
    conn.execute("DELETE FROM resource_person WHERE name LIKE 'INS-%'")
    conn.execute("DELETE FROM org_unit WHERE path LIKE 'INS%'")
    conn.commit()


@pytest.fixture
def team(app_mod):
    """Two sections, one person each, and a fortnight of wellness claims for the
    S1 person: three Wednesday-morning breaks and one late Friday."""
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    _wipe(conn)

    units = {}
    for path in ("INS/D1/S1", "INS/D2/S2"):
        units[path] = conn.execute(
            "INSERT INTO org_unit(name, short_name, level, path) VALUES (?,?,?,?)",
            (path[-2:], path[-2:], "section", path)).lastrowid

    def account(name, path):
        rp = conn.execute(
            "INSERT INTO resource_person(name, is_internal, org_unit_id)"
            " VALUES (?,1,?)", (name, units[path])).lastrowid
        return st.create_admin_user(conn, f"ins-{name.lower()}@test.local",
                                    "x", "y", "viewer", rp_id=rp)

    one = account("INS-One", "INS/D1/S1")
    two = account("INS-Two", "INS/D2/S2")

    this_week = date.fromisoformat(st.wellness_week_start())

    def claim(uid, weeks_ago, weekday, start, activity="exercise", status="completed",
              reflection=None):
        wk = this_week - timedelta(weeks=weeks_ago)
        break_date = wk + timedelta(days=weekday)
        cid = conn.execute(
            "INSERT INTO wellness_claim(user_id, week_start, break_date, start_time,"
            " hours, activity, status, created_at) VALUES (?,?,?,?,1,?,?,?)",
            (uid, wk.isoformat(), break_date.isoformat(), start, activity, status,
             wk.isoformat())).lastrowid
        if reflection:
            conn.execute(
                "INSERT INTO wellness_reflection(claim_id, mood_before, mood_after,"
                " felt_refreshed) VALUES (?,?,?,?)", (cid, *reflection))
        return cid

    for weeks_ago in (0, 1, 2):                       # Wednesday, 09:00
        claim(one, weeks_ago, 2, "09:00", reflection=(3, 5, 1))
    claim(one, 1, 4, "15:00", activity="hobby")       # Friday, mid-afternoon
    claim(two, 0, 0, "13:00")                         # the other section entirely
    # a pending request is a PLAN, not behaviour — it must not reach the pattern
    claim(one, 0, 1, "08:00", status="pending")
    conn.commit()
    yield {"conn": conn, "one": one, "two": two, "week": st.wellness_week_start()}
    _wipe(conn)
    conn.close()


def _u(conn, uid):
    r = st.get_admin_user_by_id(conn, uid)
    return {"id": r["id"], "username": r["username"], "role": r["role"]}


# --- the counts -------------------------------------------------------------

def test_pattern_buckets_by_weekday_and_start_time(team):
    conn = team["conn"]
    pat = st.wellness_pattern(conn, team["week"], _u(conn, team["one"]))

    assert pat["claims"] == 4                      # the pending one is excluded
    assert pat["people"] == 1
    assert pat["peak_day"]["name"] == "Wednesday"
    assert pat["peak_day"]["n"] == 3
    assert pat["by_day"][2]["n"] == 3              # Wednesday
    assert pat["by_day"][4]["n"] == 1              # Friday
    # Wednesday x "Before 10", and Friday x "After 2pm"
    assert pat["grid"][2][0] == 3
    assert pat["grid"][4][3] == 1
    assert pat["peak_slot"]["label"] == "Before 10"


def test_pattern_reads_the_activity_mix_and_the_reflections(team):
    conn = team["conn"]
    pat = st.wellness_pattern(conn, team["week"], _u(conn, team["one"]))

    mix = {a["label"]: a["n"] for a in pat["by_activity"]}
    assert mix["Physical exercise"] == 3
    assert mix["Hobby & creative recreation"] == 1

    assert pat["mood"]["reflections"] == 3
    assert pat["mood"]["delta"] == 2.0             # 3 -> 5, three times
    assert pat["mood"]["refreshed_pct"] == 100


def test_pattern_is_scoped_to_the_viewers_own_unit(team):
    """Same guard as the rest of the landing page: S1 must never be able to read
    S2's habits, and the pattern query is a second door into the same data."""
    conn = team["conn"]
    one = st.wellness_pattern(conn, team["week"], _u(conn, team["one"]))
    two = st.wellness_pattern(conn, team["week"], _u(conn, team["two"]))

    assert one["claims"] == 4
    assert two["claims"] == 1                      # only its own


def test_only_user_id_is_a_persons_own_history(team):
    """The Me view asks for one person, and you may always see yourself — so that
    call takes no scope filter at all."""
    conn = team["conn"]
    mine = st.wellness_pattern(conn, team["week"], only_user_id=team["two"])
    assert mine["claims"] == 1
    assert mine["by_day"][0]["n"] == 1             # Monday


def test_someone_who_left_the_bureau_is_out_of_the_pattern(team):
    """The wall of faces on the card excludes archived people, so the eight weeks
    behind it must too — otherwise one card's two halves disagree about who is on
    the team. Their own history stays their own to read."""
    conn = team["conn"]
    rp_id = st.get_admin_user_by_id(conn, team["one"])["rp_id"]
    st.set_rp_archived(conn, rp_id, True, reason="resigned")
    try:
        pat = st.wellness_pattern(conn, team["week"], _u(conn, team["two"]))
        assert pat["claims"] == 1                  # only the S2 person's own
        mine = st.wellness_pattern(conn, team["week"], only_user_id=team["one"])
        assert mine["claims"] == 4                 # ...but theirs is still theirs
    finally:
        st.set_rp_archived(conn, rp_id, False)


def test_the_window_is_the_last_n_weeks(team):
    conn = team["conn"]
    pat = st.wellness_pattern(conn, team["week"], _u(conn, team["one"]), weeks=1)
    assert pat["claims"] == 1                      # only this week's Wednesday
    assert len(pat["by_week"]) == 1


# --- the geometry -----------------------------------------------------------

def test_count_bars_marks_the_peak_and_mirrors_its_own_table():
    g = di.count_bars_geom(
        [{"name": "Monday", "short": "Mon", "n": 2},
         {"name": "Tuesday", "short": "Tue", "n": 5},
         {"name": "Wednesday", "short": "Wed", "n": 0}],
        caption="Breaks by weekday", key_header="Weekday", value_header="Breaks")

    peaks = [b["name"] for b in g["bars"] if b["peak"]]
    assert peaks == ["Tuesday"]
    assert [b["tone"] for b in g["bars"]] == ["soft", "accent", "soft"]
    # the SR table is the chart, in words — same numbers, same order
    assert g["table"]["rows"] == [["Monday", "2"], ["Tuesday", "5"], ["Wednesday", "0"]]
    assert g["table"]["headers"] == ["Weekday", "Breaks"]
    assert "Tuesday 5" in g["aria_label"]
    # a zero-height bar still sits on the axis rather than below it
    assert g["bars"][2]["h"] == 0
    assert g["bars"][2]["y"] == g["axis_y"]


def test_count_bars_emits_no_colour():
    """35 of the 36 theme x accent combinations would be wrong with a literal."""
    g = di.count_bars_geom([{"name": "Monday", "n": 1}], caption="x")
    blob = repr(g)
    assert "#" not in blob and "rgb" not in blob


def test_count_bars_survives_an_all_zero_series():
    g = di.count_bars_geom([{"name": "Monday", "n": 0}, {"name": "Tuesday", "n": 0}],
                           caption="Breaks by weekday")
    assert g["empty"] is True
    assert g["ymax"] == 1                          # never divides by zero
    assert not any(b["peak"] for b in g["bars"])
    assert "nothing yet" in g["aria_label"]


def test_heat_geom_steps_finds_the_peak_and_drops_empty_days():
    grid = [[0, 0], [0, 0], [3, 0], [0, 0], [1, 1], [0, 0], [0, 0]]
    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            "Saturday", "Sunday"]
    g = di.heat_geom(grid, days, ["Before 10", "After 10"],
                     caption="Breaks by day and start time")

    # Monday, Tuesday, Thursday and the weekend never happened — a permanently
    # blank row only makes the days that did happen smaller.
    assert [r["label"] for r in g["rows"]] == ["Wednesday", "Friday"]
    assert g["peak"] == {"row": "Wednesday", "col": "Before 10", "n": 3}
    steps = {c["n"]: c["step"] for c in g["cells"]}
    assert steps[0] == 0
    assert steps[3] == di.HEAT_STEPS                # the busiest cell is full strength
    assert steps[1] >= 1                            # ...and a single break is visible
    assert g["table"]["rows"] == [["Wednesday", "3", "0"], ["Friday", "1", "1"]]


def test_heat_geom_with_nothing_filed_still_draws_a_week():
    g = di.heat_geom([[0, 0], [0, 0]], ["Monday", "Tuesday"], ["Before 10", "After 10"],
                     caption="Breaks by day and start time")
    assert g["peak"] is None
    assert len(g["rows"]) == 2                      # the empty week, not an empty box
    assert "nothing yet" in g["aria_label"]


# --- the page ---------------------------------------------------------------

def test_the_landing_cards_are_decks_with_more_than_one_view(app_mod, team):
    """The point of the change: each team card carries several readings of the
    same thing, and every chart on every slide still ships its data table."""
    conn = team["conn"]
    conn.execute("UPDATE admin_user SET onboarded_at=? WHERE id=?",
                 ("2026-01-01T00:00:00", team["one"]))
    conn.commit()

    import auth
    from starlette.testclient import TestClient
    c = TestClient(app_mod.app, raise_server_exceptions=True)
    c.cookies.set(auth.COOKIE_NAME, auth.make_token(_u(conn, team["one"])))
    html = c.get("/").text

    assert html.count('class="deck-slide"') >= 4
    assert "When breaks happen" in html
    assert "What people do with it" in html
    assert "The day people are away" in html
    # the swipe track is native CSS, so the deck works with JS switched off
    assert 'class="deck-track"' in html
    assert "deck.js" in html
    # and every chart still has its screen-reader table
    assert html.count("sr-only chart-data") >= 3


def test_a_deck_slide_says_what_its_chart_means(app_mod, team):
    """A chart nobody can summarise is a chart nobody acted on, so each slide
    carries the sentence with it — computed in Python, not guessed at by eye."""
    conn = team["conn"]
    conn.execute("UPDATE admin_user SET onboarded_at=? WHERE id=?",
                 ("2026-01-01T00:00:00", team["one"]))
    conn.commit()

    import auth
    from starlette.testclient import TestClient
    c = TestClient(app_mod.app, raise_server_exceptions=True)
    c.cookies.set(auth.COOKIE_NAME, auth.make_token(_u(conn, team["one"])))
    html = c.get("/").text

    assert "Wednesday" in html                      # the peak day, said out loud
    assert 'class="deck-say"' in html


def test_the_awa_card_leads_with_the_dates_it_covers(app_mod):
    """"Team filing" named the action; the card is about a fortnight, and which
    fortnight is the first thing a reader needs."""
    with in_the_directory(app_mod, "admin@test.local"):
        html = _auth_client(app_mod, "admin").get("/").text

    open_ps = st.work_arrangement_open_periods()
    assert "Alternative Work Arrangement" in html
    assert "Team filing" not in html
    if open_ps:
        assert st.work_arrangement_period_label(open_ps[0]) in html
