"""The companion leaderboard (spot feedback #196): ranking, tie-breaks, periods, who is compared, and the pages."""
from __future__ import annotations
from datetime import date

import pytest

import companion_leaderboard as lb
import storage as st
from test_calendar_home import world                                  # noqa: F401  (throwaway org + accounts)

TODAY = date(2030, 3, 13)                                             # a Wednesday; its week starts 2030-03-11


def breaks(w, who, *days, status="completed", reflect=()):
    """Completed 1-hour breaks for `who` on ISO `days`; the ones in `reflect` also get a reflection."""
    for d in days:
        wk = st.wellness_week_start(date.fromisoformat(d))
        cid = w["conn"].execute("INSERT INTO wellness_claim(user_id, week_start, break_date, start_time, hours, activity, status) "
                                "VALUES (?,?,?,?,1,'exercise',?)", (w[who]["id"], wk, d, "10:00", status)).lastrowid
        if d in reflect:
            w["conn"].execute("INSERT INTO wellness_reflection(claim_id) VALUES (?)", (cid,))
    w["conn"].commit()


def rows(w, who, period="month", scope="bureau"):
    return lb.board(w["conn"], w[who], period, scope, TODAY)["rows"]


def test_points_follow_the_pets_own_formula_and_people_are_ranked_best_first(world):
    breaks(world, "s1", "2030-03-11", "2030-03-12", reflect=("2030-03-11",))      # 2 breaks + 1 reflection + a full week
    breaks(world, "s1b", "2030-03-11")
    got = {r["user_id"]: r for r in rows(world, "s3")}
    assert got[world["s1"]["id"]]["points"] == 10 + 10 + 5 + 5 and got[world["s1"]["id"]]["breaks"] == 2
    assert got[world["s1b"]["id"]]["points"] == 10
    order = [r["user_id"] for r in rows(world, "s3")]
    assert order[:2] == [world["s1"]["id"], world["s1b"]["id"]]
    assert [r["rank"] for r in rows(world, "s3")][:2] == [1, 2]
    assert world["nobody"]["id"] not in order                                       # no directory person, no place on the board


def test_ties_share_a_rank_then_the_care_streak_and_badges_break_them(world):
    c = world["conn"]
    c.execute("UPDATE admin_user SET avatar_care_streak=5 WHERE id=?", (world["s1b"]["id"],)); c.commit()
    r = {x["user_id"]: x for x in rows(world, "s3")}                                # nobody has points: care streak decides
    assert r[world["s1b"]["id"]]["rank"] == 1
    others = {r[world[k]["id"]]["rank"] for k in ("s1", "s3", "d1", "dir")}
    assert others == {2}                                                            # the rest tie for second, shared rank


def test_a_pet_shows_by_its_name_and_falls_back_to_its_species(world):
    c = world["conn"]
    c.execute("UPDATE admin_user SET avatar_name='Mango', avatar_kind='fern' WHERE id=?", (world["s1"]["id"],)); c.commit()
    r = {x["user_id"]: x for x in rows(world, "s3")}
    assert r[world["s1"]["id"]]["pet"] == "Mango" and r[world["s1"]["id"]]["species"] == "Fern"
    assert r[world["s1b"]["id"]]["pet"] == r[world["s1b"]["id"]]["species"]         # unnamed: the species label
    assert "P s1" not in str(rows(world, "s3"))                                     # never the person's own name


def test_the_period_decides_what_counts(world):
    breaks(world, "s1", "2030-03-12", "2030-02-12", "2030-01-15", "2029-11-20")
    pts = lambda p: next(r for r in rows(world, "s1", p) if r["user_id"] == world["s1"]["id"])["points"]
    assert pts("month") == 10                                                       # only March
    assert pts("quarter") == 30                                                     # January to March
    assert pts("all") == 40 + 2 * 1                                                 # everything, plus the 1-week current streak bonus


def test_the_all_time_board_adds_the_current_streak_like_the_hub(world):
    breaks(world, "s1", "2030-03-12", "2030-03-05", "2030-02-26")                  # three weeks in a row ending this week
    me = next(r for r in rows(world, "s1", "all") if r["user_id"] == world["s1"]["id"])
    hub = st.wellness_stats(world["conn"], world["s1"]["id"])
    assert me["streak"] == 3 and me["points"] == 30 + 3 * 2
    assert me["stage"] == min(sum(1 for t in st.WELLNESS_LEVELS if me["points"] >= t), 6)
    assert hub["completed"] == 3 and hub["streak"] in (0, 3)                        # the hub counts from the real today


def test_pending_and_cancelled_breaks_earn_nothing(world):
    breaks(world, "s1", "2030-03-11", status="pending"); breaks(world, "s1", "2030-03-12", status="cancelled")
    assert all(r["points"] == 0 for r in rows(world, "s1"))


@pytest.mark.parametrize("scope, who", [("section", {"s1", "s1b"}), ("division", {"s1", "s1b", "d1"}),
                                        ("bureau", {"s1", "s1b", "d1", "s3", "dir"})])
def test_the_viewer_chooses_who_is_compared(world, scope, who):
    got = {r["user_id"] for r in rows(world, "s1", scope=scope)}
    assert got == {world[k]["id"] for k in who}


def test_without_a_section_or_division_the_choices_are_just_the_bureau(world):
    b = lb.board(world["conn"], world["nobody"], "month", "section", TODAY)         # an account with no directory person
    assert b["scope"] == "bureau" and [k for k, _ in b["scope_options"]] == ["bureau"]
    d = lb.board(world["conn"], world["dir"], "month", "section", TODAY)            # T/OD: no section, but its own division-level group
    assert d["scope"] == "bureau" and [k for k, _ in d["scope_options"]] == ["division", "bureau"]
    assert [k for k, _ in lb.board(world["conn"], world["s1"], "month", "bureau", TODAY)["scope_options"]] == ["section", "division", "bureau"]


def test_unknown_choices_fall_back_to_the_defaults(world):
    b = lb.board(world["conn"], world["s1"], "forever", "everyone", TODAY)
    assert (b["period"], b["scope"]) == (lb.DEFAULT_PERIOD, lb.DEFAULT_SCOPE)


@pytest.mark.parametrize("period, today, expected", [
    ("month", date(2030, 3, 13), ("2030-03-01", "2030-03-31")), ("month", date(2030, 12, 5), ("2030-12-01", "2030-12-31")),
    ("month", date(2028, 2, 10), ("2028-02-01", "2028-02-29")),
    ("quarter", date(2030, 3, 13), ("2030-01-01", "2030-03-31")), ("quarter", date(2030, 5, 2), ("2030-04-01", "2030-06-30")),
    ("quarter", date(2030, 11, 30), ("2030-10-01", "2030-12-31")), ("all", date(2030, 3, 13), (None, None))])
def test_the_period_ranges(period, today, expected):
    assert lb.period_range(period, today) == expected


def test_the_home_card_shows_the_top_and_always_the_viewers_own_row(world):
    for who in ("s1b", "d1", "s3", "dir"):
        breaks(world, who, "2030-03-12")
    card = lb.home_card(world["conn"], world["s1"], TODAY, top=3)                   # s1 has no points: outside the top three
    assert card["total"] == 5 and len(card["shown"]) == 4 and card["shown"][-1]["is_me"]
    mine = lb.home_card(world["conn"], world["d1"], TODAY, top=3)                    # inside the top: not shown twice
    assert [r["is_me"] for r in mine["shown"]].count(True) == 1 and len(mine["shown"]) == 3


def test_the_full_page_offers_the_periods_and_groups(viewer):
    page = viewer.get("/wellness/leaderboard")
    assert page.status_code == 200 and "Companion leaderboard" in page.text
    for label in ("This month", "This quarter", "All time", "Whole bureau"):
        assert label in page.text
    assert viewer.get("/wellness/leaderboard?period=quarter&scope=division").status_code == 200
    assert viewer.get("/wellness/leaderboard?period=%27&scope=x").status_code == 200  # junk is just the defaults


def test_the_page_needs_a_login(client):
    assert client.get("/wellness/leaderboard", follow_redirects=False).status_code in (302, 303, 401)


def test_the_home_page_carries_the_leaderboard_card_and_its_link(app_mod):
    from tests.conftest import _auth_client, in_the_directory
    with in_the_directory(app_mod, "viewer@test.local", path="LBFX/D1/S1"):
        c = _auth_client(app_mod, "viewer")
        home = c.get("/")
        assert home.status_code == 200
        assert 'data-tour="oc-leaderboard"' in home.text and 'href="/wellness/leaderboard"' in home.text
        assert "You are <strong>#" in home.text
        full = c.get("/wellness/leaderboard?scope=section&period=all")
        assert full.status_code == 200 and "My section" in full.text and "You are #" in full.text
        assert 'data-tour="oc-leaderboard"' not in c.get("/?view=calendar").text      # the calendar tab draws only the calendar
