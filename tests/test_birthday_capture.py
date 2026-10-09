"""Capturing a birthday with consent (office calendar F1): month and day only, opt-in sharing,
a consent record, and a one-click withdrawal."""
from __future__ import annotations
from urllib.parse import urlencode

import pytest

import storage as st

FORM = {"Content-Type": "application/x-www-form-urlencoded"}


@pytest.fixture()
def conn(tmp_path):
    c = st.connect(str(tmp_path / "bd.db")); st.init_db(c)
    return c


@pytest.fixture()
def uid(conn):
    return st.create_admin_user(conn, "bd@test.local", "x", "y", "viewer")


# ----------------------------------------------------------------- storage ---

@pytest.mark.parametrize("m, d", [(2, 29), (12, 31), (1, 1), ("10", "9")])
def test_real_dates_are_accepted(m, d):
    assert st.birthday_check(m, d) == (int(m), int(d))


@pytest.mark.parametrize("m, d", [(4, 31), (2, 30), (13, 1), (0, 5), (5, 0), ("x", 1), ("", ""), (None, 3)])
def test_impossible_dates_are_refused(m, d):
    with pytest.raises(ValueError):
        st.birthday_check(m, d)


def test_there_is_no_year_anywhere(conn, uid):
    cols = {r[1] for r in conn.execute("PRAGMA table_info(admin_user)") if r[1].startswith("birthday")}
    assert cols == {"birthday_month", "birthday_day", "birthday_share", "birthday_consent_at",
                    "birthday_consent_notice"}
    assert not [r for r in conn.execute("PRAGMA table_info(resource_person)") if "birth" in r[1]]
    with pytest.raises(TypeError):
        st.set_birthday(conn, uid, 3, 4, "none", 1990)                       # no year parameter


def test_default_is_nothing_and_not_shared(conn, uid):
    assert st.get_birthday(conn, uid) is None
    st.set_birthday(conn, uid, 10, 14)
    b = st.get_birthday(conn, uid)
    assert (b["month"], b["day"], b["share"], b["consent_at"], b["label"]) == (10, 14, "none", None, "October 14")


def test_sharing_records_consent_and_the_notice_shown(conn, uid):
    st.set_birthday(conn, uid, 10, 14, "section")
    b = st.get_birthday(conn, uid)
    assert b["share"] == "section" and b["consent_at"]
    notice = conn.execute("SELECT birthday_consent_notice FROM admin_user WHERE id=?", (uid,)).fetchone()[0]
    assert notice == st.BIRTHDAY_NOTICE


def test_an_unchanged_choice_keeps_the_original_consent_time(conn, uid):
    st.set_birthday(conn, uid, 10, 14, "section")
    conn.execute("UPDATE admin_user SET birthday_consent_at='2026-01-01T00:00:00' WHERE id=?", (uid,))
    st.set_birthday(conn, uid, 10, 15, "section")                            # fixed the day only
    assert st.get_birthday(conn, uid)["consent_at"] == "2026-01-01T00:00:00"
    st.set_birthday(conn, uid, 10, 15, "bureau")                             # a wider choice is a new consent
    assert st.get_birthday(conn, uid)["consent_at"] != "2026-01-01T00:00:00"


def test_switching_sharing_off_erases_the_consent_record(conn, uid):
    st.set_birthday(conn, uid, 10, 14, "bureau")
    st.set_birthday(conn, uid, 10, 14, "none")
    b = st.get_birthday(conn, uid)
    assert b["share"] == "none" and b["consent_at"] is None
    assert conn.execute("SELECT birthday_consent_notice FROM admin_user WHERE id=?", (uid,)).fetchone()[0] is None


def test_withdrawing_clears_everything(conn, uid):
    st.set_birthday(conn, uid, 10, 14, "division")
    st.clear_birthday(conn, uid)
    assert st.get_birthday(conn, uid) is None
    assert conn.execute("SELECT birthday_month, birthday_day, birthday_share, birthday_consent_at, "
                        "birthday_consent_notice FROM admin_user WHERE id=?", (uid,)).fetchone() == (None,) * 5


def test_an_unknown_sharing_choice_changes_nothing(conn, uid):
    st.set_birthday(conn, uid, 10, 14)
    with pytest.raises(ValueError):
        st.set_birthday(conn, uid, 11, 1, "everyone")
    assert st.get_birthday(conn, uid)["label"] == "October 14"


def test_the_staff_directory_and_user_list_never_carry_it(conn, uid):
    st.set_birthday(conn, uid, 10, 14, "bureau")
    acct = st.get_admin_user(conn, "bd@test.local")
    assert not [k for k in acct if "birth" in k]
    rp = conn.execute("INSERT INTO resource_person(name, is_internal) VALUES ('P', 1)").lastrowid
    assert not [k for k in st.get_rp(conn, rp) if "birth" in k]


# ------------------------------------------------------------------- pages ---

def me_post(client, **over):
    base = {"avatar_kind": st.AVATAR_DEFAULT, "avatar_name": "Milo", "nickname": "", "designation": ""}
    return client.post("/me", content=urlencode({**base, **over}), headers=FORM, follow_redirects=False)


@pytest.fixture()
def acct(app_mod):
    c = st.connect(app_mod.DB); st.init_db(c)
    uid = st.get_admin_user(c, "viewer@test.local")["id"]
    st.clear_birthday(c, uid)
    yield c, uid
    st.clear_birthday(c, uid); c.close()


def test_the_profile_form_shows_the_fields_and_the_notice(app_mod, viewer, acct):
    html = viewer.get("/me").text
    assert 'name="birthday_month"' in html and 'name="birthday_day"' in html and 'name="birthday_share"' in html
    assert "never your year" in html and "Remove my birthday" not in html


def test_saving_the_profile_stores_the_birthday_and_audits_without_the_date(app_mod, viewer, acct):
    c, uid = acct
    mark = c.execute("SELECT COALESCE(MAX(id), 0) FROM audit_log").fetchone()[0]
    assert me_post(viewer, birthday_present="1", birthday_month="2", birthday_day="29",
                   birthday_share="bureau").status_code == 303
    b = st.get_birthday(c, uid)
    assert (b["month"], b["day"], b["share"]) == (2, 29, "bureau") and b["consent_at"]
    rows = c.execute("SELECT action, summary FROM audit_log WHERE id>? AND action LIKE 'birthday%'", (mark,)).fetchall()
    assert [r[0] for r in rows] == ["birthday_set"] and "29" not in rows[0][1] and "Feb" not in rows[0][1]
    assert "Remove my birthday" in viewer.get("/me").text


def test_a_form_without_the_fields_never_wipes_a_saved_birthday(app_mod, viewer, acct):
    c, uid = acct
    st.set_birthday(c, uid, 10, 14, "section")
    assert me_post(viewer).status_code == 303
    assert st.get_birthday(c, uid)["label"] == "October 14"


@pytest.mark.parametrize("m, d", [("4", "31"), ("2", "30"), ("5", ""), ("", "5")])
def test_a_bad_date_shows_an_error_and_saves_nothing(app_mod, viewer, acct, m, d):
    c, uid = acct
    r = me_post(viewer, birthday_present="1", birthday_month=m, birthday_day=d, nickname="ShouldNotSave")
    assert r.status_code == 200 and ("real date" in r.text or "both a month" in r.text)
    assert st.get_birthday(c, uid) is None
    assert c.execute("SELECT nickname FROM admin_user WHERE id=?", (uid,)).fetchone()[0] != "ShouldNotSave"


def test_blank_month_and_day_clears_it(app_mod, viewer, acct):
    c, uid = acct
    st.set_birthday(c, uid, 10, 14, "section")
    me_post(viewer, birthday_present="1", birthday_month="", birthday_day="", birthday_share="section")
    assert st.get_birthday(c, uid) is None


def test_one_click_withdraw(app_mod, viewer, acct):
    c, uid = acct
    st.set_birthday(c, uid, 10, 14, "bureau")
    r = viewer.post("/me/birthday/remove", follow_redirects=False)
    assert r.status_code == 303 and "/me" in r.headers["location"]
    assert st.get_birthday(c, uid) is None
    assert c.execute("SELECT COUNT(*) FROM audit_log WHERE action='birthday_clear'").fetchone()[0] >= 1


def test_the_welcome_step_offers_it_too(app_mod, viewer, acct):
    c, uid = acct
    assert 'name="birthday_month"' in viewer.get("/welcome").text
    r = viewer.post("/welcome", content=urlencode({
        "avatar_kind": st.AVATAR_DEFAULT, "avatar_name": "Milo", "birthday_present": "1",
        "birthday_month": "12", "birthday_day": "25", "birthday_share": "section"}), headers=FORM, follow_redirects=False)
    assert r.status_code == 303 and st.get_birthday(c, uid)["label"] == "December 25"
    bad = viewer.post("/welcome", content=urlencode({
        "avatar_kind": st.AVATAR_DEFAULT, "avatar_name": "Milo", "birthday_present": "1",
        "birthday_month": "4", "birthday_day": "31"}), headers=FORM)
    assert bad.status_code == 200 and "real date" in bad.text


def test_the_form_keeps_choices_after_an_error(app_mod, viewer, acct):
    r = me_post(viewer, birthday_present="1", birthday_month="4", birthday_day="31", birthday_share="division")
    assert 'checked value="division"' in r.text and 'value="4" selected' in r.text
