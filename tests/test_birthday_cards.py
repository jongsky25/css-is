"""Birthday cards from teammates (docs/BIRTHDAY_GREETINGS_PLAN.md, Phase 3)."""
from __future__ import annotations
from datetime import date

import pytest

import birthdays as bd
import office_calendar as oc
import ratelimit
import storage as st
import tzutil as tz
from test_birthday_reminders import bday, pretend_today, world           # noqa: F401
from tests.conftest import ROLE_USERS, _auth_client

WED = date(2026, 10, 14)


# ----------------------------------------------------------------- the card ---

@pytest.mark.parametrize("design, message", [("nope", "hi"), ("cake", ""), ("cake", "   \n "),
                                             ("cake", "x" * (st.CARD_MAX + 1)), ("", "hi")])
def test_a_bad_card_is_refused_with_a_sentence(design, message):
    with pytest.raises(ValueError):
        st.card_check(design, message)


def test_a_good_card_is_kept_as_plain_text():
    assert st.card_check("cake", "  Maligayang kaarawan!\n\n\n\nSalamat.  ") == ("cake", "Maligayang kaarawan!\n\nSalamat.")
    assert st.card_check("cake", "x" * st.CARD_MAX)[1] == "x" * st.CARD_MAX


def test_one_card_per_sender_per_year_and_old_years_are_dropped(world):                         # noqa: F811
    c, a, b = world["conn"], world["s1"]["id"], world["s1b"]["id"]
    st.card_send(c, b, a, 2026, "cake", "Hi")
    with pytest.raises(ValueError):
        st.card_send(c, b, a, 2026, "star", "Again")
    st.card_send(c, b, a, 2027, "star", "Next year is fine")
    st.card_send(c, b, a, 2028, "star", "Two years on")                   # drops 2026 (before 2027)
    assert {r[0] for r in c.execute("SELECT year FROM birthday_card")} == {2027, 2028}
    assert st.cards_sent_by(c, a, 2027) == {b}


def test_cards_are_held_until_the_day():
    assert bd.revealed_card_year(10, 14, date(2026, 10, 13)) == 2025      # the day before: last year's only
    assert bd.revealed_card_year(10, 14, date(2026, 10, 14)) == 2026
    assert bd.revealed_card_year(10, 14, date(2026, 12, 1)) == 2026


# ------------------------------------------------------------- eligibility ---

def who(world, viewer, today=WED):                                       # noqa: F811
    return [(c["user_id"], c["sent"]) for c in oc.card_celebrants(world["conn"], world[viewer]["id"], today)]


def test_you_can_send_to_whoever_shares_with_you_inside_the_window(world):                      # noqa: F811
    bday(world, "s1b", 10, 17, "section"); bday(world, "dir", 10, 14, "bureau"); bday(world, "s3", 10, 16, "division")
    assert sorted(who(world, "s1")) == sorted([(world["s1b"]["id"], False), (world["dir"]["id"], False)])


def test_dont_share_means_no_cards_and_nobody_sends_to_themselves(world):                       # noqa: F811
    bday(world, "s1b", 10, 15, "none"); bday(world, "s1", 10, 15, "bureau")
    assert who(world, "s1") == []
    assert who(world, "s1b") == [(world["s1"]["id"], False)]


def test_the_window_is_the_six_days_before_and_the_day(world):                                  # noqa: F811
    bday(world, "s1b", 10, 20, "section")                                 # six days out
    assert who(world, "s1") == [(world["s1b"]["id"], False)]
    bday(world, "s1b", 10, 21, "section")                                 # seven days out: too early
    assert who(world, "s1") == []
    bday(world, "s1b", 10, 13, "section")                                 # yesterday: too late
    assert who(world, "s1") == []


def test_already_sent_is_marked(world):                                                          # noqa: F811
    bday(world, "s1b", 10, 15, "section")
    st.card_send(world["conn"], world["s1b"]["id"], world["s1"]["id"], 2026, "cake", "Hi")
    assert who(world, "s1") == [(world["s1b"]["id"], True)]


# ---------------------------------------------------------------- the bell ---

def bell(world, viewer, today=WED):                                      # noqa: F811
    return oc.card_bell_row(world["conn"], world[viewer]["id"], today)


def test_the_bell_points_straight_at_a_single_card(world):                                       # noqa: F811
    bday(world, "s1b", 10, 17, "section")
    row = bell(world, "s1")
    assert row["url"] == f"/birthday/card/{world['s1b']['id']}" and "Sat" in row["text"] and row["count"] == 1


def test_the_bell_lists_several_and_goes_quiet_once_sent_or_switched_off(world):                 # noqa: F811
    bday(world, "s1b", 10, 17, "section"); bday(world, "dir", 10, 14, "bureau")
    row = bell(world, "s1")
    assert row["url"] == "/birthday/cards" and "2 birthday cards" in row["text"]
    st.card_send(world["conn"], world["dir"]["id"], world["s1"]["id"], 2026, "cake", "Hi")
    assert bell(world, "s1")["url"].endswith(str(world["s1b"]["id"]))
    st.card_send(world["conn"], world["s1b"]["id"], world["s1"]["id"], 2026, "cake", "Hi")
    assert bell(world, "s1") is None
    st.set_bday_notify_pref(world["conn"], world["s3"]["id"], False)
    bday(world, "s1b", 10, 17, "bureau")
    assert bell(world, "s3") is None


def test_the_bell_is_quiet_when_nothing_is_coming_or_it_is_private(world):                       # noqa: F811
    assert bell(world, "s1") is None
    bday(world, "s1b", 10, 17, "none"); bday(world, "dir", 11, 30, "bureau")
    assert bell(world, "s1") is None


def test_the_bell_finds_a_leap_day_birthday_on_feb_28(world):                                    # noqa: F811
    bday(world, "s1b", 2, 29, "section")
    assert bell(world, "s1", date(2027, 2, 27)) is not None


# ------------------------------------------------------------------ routes ---

@pytest.fixture()
def cast(app_mod, monkeypatch):
    """The encoder has a Saturday birthday shared with the bureau; the viewer may send them a card."""
    conn = st.connect(app_mod.DB)
    ids = {r: st.get_admin_user(conn, ROLE_USERS[r])["id"] for r in ("viewer", "encoder", "admin", "section_manager")}
    st.set_birthday(conn, ids["encoder"], 10, 17, "bureau")
    st.clear_birthday(conn, ids["viewer"])
    conn.execute("DELETE FROM birthday_card"); conn.commit()
    monkeypatch.setattr(tz, "today_local", lambda: WED)
    ratelimit._HITS.clear()
    yield conn, ids
    conn.execute("DELETE FROM birthday_card"); conn.commit()
    st.clear_birthday(conn, ids["encoder"]); conn.close()


def send(app_mod, ids, message="Maligayang kaarawan!", design="cake", frm="viewer", to="encoder"):
    c = _auth_client(app_mod, frm)
    from urllib.parse import urlencode
    return c.post(f"/birthday/card/{ids[to]}", content=urlencode({"design": design, "message": message}),
                  headers={"Content-Type": "application/x-www-form-urlencoded"}, follow_redirects=False)


def test_the_form_opens_for_an_eligible_celebrant(app_mod, cast):
    conn, ids = cast
    r = _auth_client(app_mod, "viewer").get(f"/birthday/card/{ids['encoder']}")
    assert r.status_code == 200 and "Pick a design" in r.text and "Save the card" in r.text


def test_sending_a_card_saves_it_and_audits_without_the_message(app_mod, cast):
    conn, ids = cast
    r = send(app_mod, ids, "A very private note")
    assert r.status_code == 303 and "/birthday/cards" in r.headers["location"]
    card = conn.execute("SELECT to_user_id, from_user_id, year, design, message FROM birthday_card").fetchone()
    assert card == (ids["encoder"], ids["viewer"], 2026, "cake", "A very private note")
    logged = " ".join(str(x) for row in conn.execute("SELECT * FROM audit_log WHERE action='birthday_card_sent'") for x in row)
    assert "birthday_card_sent" in logged and "A very private note" not in logged
    assert send(app_mod, ids).status_code == 303                          # a second one is turned away
    assert conn.execute("SELECT COUNT(*) FROM birthday_card").fetchone()[0] == 1


def test_a_private_or_out_of_window_birthday_cannot_get_a_card(app_mod, cast):
    conn, ids = cast
    st.set_birthday(conn, ids["encoder"], 10, 17, "none")
    r = send(app_mod, ids)
    assert r.status_code == 303 and "err=" in r.headers["location"]
    st.set_birthday(conn, ids["encoder"], 11, 30, "bureau")
    assert "err=" in send(app_mod, ids).headers["location"]
    assert conn.execute("SELECT COUNT(*) FROM birthday_card").fetchone()[0] == 0
    st.set_birthday(conn, ids["viewer"], 10, 17, "bureau")                # nobody can send to themselves
    assert "err=" in send(app_mod, ids, to="viewer").headers["location"]


@pytest.mark.parametrize("message, design, fragment", [("", "cake", "short message"), ("x" * 281, "cake", "280"),
                                                       ("hi", "bogus", "design")])
def test_bad_input_shows_a_reason_and_saves_nothing(app_mod, cast, message, design, fragment):
    conn, ids = cast
    r = send(app_mod, ids, message, design)
    assert r.status_code == 400 and fragment in r.text
    assert conn.execute("SELECT COUNT(*) FROM birthday_card").fetchone()[0] == 0


def test_a_flood_is_rate_limited(app_mod, cast, monkeypatch):
    conn, ids = cast
    monkeypatch.setattr(ratelimit, "allow", lambda bucket, key, now=None: False)
    assert send(app_mod, ids).status_code == 429
    assert conn.execute("SELECT COUNT(*) FROM birthday_card").fetchone()[0] == 0


def test_the_celebrant_sees_nothing_until_the_day_then_the_cards_escaped(app_mod, cast, monkeypatch):
    conn, ids = cast
    send(app_mod, ids, "<script>alert(1)</script>")
    me = _auth_client(app_mod, "encoder")
    assert "alert" not in me.get("/me/cards").text                        # held: three days early
    monkeypatch.setattr(tz, "today_local", lambda: date(2026, 10, 17))
    page = me.get("/me/cards").text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in page and "<script>alert(1)" not in page
    assert "🎂" in page


def test_the_landing_page_mentions_cards_on_the_day(app_mod, cast, monkeypatch):
    conn, ids = cast
    send(app_mod, ids)
    monkeypatch.setattr(tz, "today_local", lambda: date(2026, 10, 17))
    conn.execute("UPDATE admin_user SET bday_greeted=NULL WHERE id=?", (ids["encoder"],)); conn.commit()
    page = _auth_client(app_mod, "encoder").get("/").text
    assert "May 1 card para sa iyo" in page and 'href="/me/cards"' in page


def test_the_celebrant_can_hide_a_card_and_only_their_own(app_mod, cast, monkeypatch):
    conn, ids = cast
    send(app_mod, ids)
    cid = conn.execute("SELECT id FROM birthday_card").fetchone()[0]
    monkeypatch.setattr(tz, "today_local", lambda: date(2026, 10, 17))
    _auth_client(app_mod, "section_manager").post(f"/me/cards/{cid}/hide", follow_redirects=False)
    assert conn.execute("SELECT hidden FROM birthday_card").fetchone()[0] == 0     # someone else cannot
    _auth_client(app_mod, "encoder").post(f"/me/cards/{cid}/hide", follow_redirects=False)
    assert conn.execute("SELECT hidden FROM birthday_card").fetchone()[0] == 1
    assert "Maligayang kaarawan!" not in _auth_client(app_mod, "encoder").get("/me/cards").text


def test_an_admin_can_hide_and_restore_a_card_and_nobody_else_can(app_mod, cast, monkeypatch):
    conn, ids = cast
    send(app_mod, ids)
    cid = conn.execute("SELECT id FROM birthday_card").fetchone()[0]
    assert _auth_client(app_mod, "viewer").get("/admin/birthday-cards").status_code in (303, 403)
    assert _auth_client(app_mod, "section_manager").get("/admin/birthday-cards").status_code in (303, 403)
    admin = _auth_client(app_mod, "admin")
    assert "Maligayang kaarawan!" in admin.get("/admin/birthday-cards").text
    hdr = {"Content-Type": "application/x-www-form-urlencoded"}
    admin.post(f"/admin/birthday-cards/{cid}/hidden", content="hide=1", headers=hdr, follow_redirects=False)
    assert conn.execute("SELECT hidden FROM birthday_card").fetchone()[0] == 1
    monkeypatch.setattr(tz, "today_local", lambda: date(2026, 10, 17))
    assert "Maligayang kaarawan!" not in _auth_client(app_mod, "encoder").get("/me/cards").text
    admin.post(f"/admin/birthday-cards/{cid}/hidden", content="hide=0", headers=hdr, follow_redirects=False)
    assert conn.execute("SELECT hidden FROM birthday_card").fetchone()[0] == 0
