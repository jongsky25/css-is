"""Birthday greetings, phase 2 (docs/BIRTHDAY_GREETINGS_PLAN.md): the landing page greets in the
six days before a birthday and on the day, with one celebration card per phase, and never after."""
from __future__ import annotations
import re
from datetime import date

import pytest

import birthdays as bd
import mailer
import storage as st
from tests.conftest import _auth_client

WED = date(2026, 10, 14)


def hat(page):
    """The companion is celebrating too (a line under the pet; the CSS class is on every page)."""
    return 'class="oc-pet-party"' in page


def _viewer_id(app_mod):
    conn = st.connect(app_mod.DB)
    try:
        return st.get_admin_user(conn, "viewer@test.local")["id"]
    finally:
        conn.close()


@pytest.fixture()
def me(app_mod, monkeypatch):
    """The test viewer with a Oct 14 birthday, 'today' pinned by the test, and no leftovers."""
    uid = _viewer_id(app_mod)

    def setup(today, month=10, day=14):
        conn = st.connect(app_mod.DB)
        st.set_birthday(conn, uid, month, day, "none")
        conn.execute("UPDATE admin_user SET bday_greeted=NULL, avatar_kind=?, avatar_name='Pip' WHERE id=?",
                     (st.AVATAR_DEFAULT, uid)); conn.commit(); conn.close()
        monkeypatch.setattr(app_mod, "_today_local", lambda: today)
        return _auth_client(app_mod, "viewer")

    yield setup
    conn = st.connect(app_mod.DB)
    st.clear_birthday(conn, uid)
    conn.execute("UPDATE admin_user SET bday_greeted=NULL WHERE id=?", (uid,)); conn.commit(); conn.close()


def test_on_the_day_the_page_greets_in_both_languages_with_the_card(me):
    page = me(WED).get("/").text
    assert "Maligayang kaarawan" in page and "Happy birthday!" in page
    assert 'id="oc-bday-card"' in page and "BLHSD" in page
    assert hat(page)                                                # the companion joins in


def test_the_card_is_a_first_visit_only_then_a_quiet_heading(me):
    c = me(WED)
    assert 'id="oc-bday-card"' in c.get("/").text
    again = c.get("/").text
    assert 'id="oc-bday-card"' not in again and "Maligayang kaarawan" in again


def test_the_week_before_has_a_lead_in_and_never_says_belated(me):
    page = me(date(2026, 10, 12)).get("/").text                      # Monday, two days out
    assert "Malapit na ang kaarawan mo" in page and "Your birthday is on Wednesday." in page
    assert hat(page) and "belated" not in page.lower()
    assert "Malapit na ang kaarawan mo bukas" not in page


def test_tomorrow_is_said_as_tomorrow(me):
    page = me(date(2026, 10, 13)).get("/").text
    assert "Your birthday is tomorrow." in page and "bukas" in page


def test_each_phase_gets_its_own_card(me, app_mod):
    c = me(date(2026, 10, 12))
    assert 'id="oc-bday-card"' in c.get("/").text                    # lead-in card
    assert 'id="oc-bday-card"' not in c.get("/").text
    app_mod._today_local = lambda: WED                               # the day arrives
    assert 'id="oc-bday-card"' in c.get("/").text                    # a new card for the day itself


@pytest.mark.parametrize("today", [date(2026, 10, 15), date(2026, 10, 20), date(2026, 10, 6)])
def test_after_the_day_and_too_early_nothing_special(me, today):
    page = me(today).get("/").text
    assert "Maligayang kaarawan" not in page and "Malapit na ang kaarawan" not in page
    assert 'id="oc-bday-card"' not in page and not hat(page)


def test_no_birthday_no_greeting(app_mod, monkeypatch):
    monkeypatch.setattr(app_mod, "_today_local", lambda: WED)
    conn = st.connect(app_mod.DB); st.clear_birthday(conn, _viewer_id(app_mod)); conn.close()
    page = _auth_client(app_mod, "viewer").get("/").text
    assert "Maligayang kaarawan" not in page and not hat(page)


def test_the_day_uses_the_same_message_as_the_email(me, app_mod):
    uid = _viewer_id(app_mod)
    tl, en = mailer.GREETING_POOL[(uid + 2026) % len(mailer.GREETING_POOL)]
    page = me(WED).get("/").text
    assert tl.replace("'", "&#39;") in page and en in page


def test_lead_in_phrases():
    assert bd.lead_in_phrases(10, 14, date(2026, 10, 13)) == ("bukas", "tomorrow")
    assert bd.lead_in_phrases(10, 17, date(2026, 10, 14)) == ("sa Sabado", "on Saturday")
