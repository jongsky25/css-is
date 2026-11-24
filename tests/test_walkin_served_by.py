"""Type 1 (walk-in / CSM) forms ask "Who served you?": the public QR form and the paper-entry form both offer
an optional pick of internal staff, store it on the response, and drop anything that is not a current
internal staff record. Activity (Type 2) forms do not ask it."""
from __future__ import annotations
import tzutil as _test_tz

import pytest

import storage as st

FORM = {"content-type": "application/x-www-form-urlencoded"}
SQD = ["SQD0", "SQD1", "SQD2", "SQD3", "SQD4", "SQD5", "SQD6", "SQD7", "SQD8"]


@pytest.fixture
def walkin(app_mod):
    conn = st.connect(app_mod.DB); st.init_db(conn)
    token = st.get_or_create_walkin_form(conn)["qr_token"]
    conn.close()
    return token


@pytest.fixture
def people(app_mod):
    conn = st.connect(app_mod.DB)
    internal = conn.execute("INSERT INTO resource_person(name, is_internal) VALUES ('Served Bytest', 1)").lastrowid
    external = conn.execute("INSERT INTO resource_person(name, is_internal) VALUES ('Outside Speaker', 0)").lastrowid
    conn.commit(); conn.close()
    return {"internal": internal, "external": external}


def _answers(score="5"):
    return "&".join(f"{s}={score}" for s in SQD)


def _latest_served(app_mod, token):
    conn = st.connect(app_mod.DB)
    row = conn.execute("SELECT r.served_by_rp_id FROM response r JOIN form_instance fi ON fi.id=r.form_instance_id "
                       "WHERE fi.qr_token=? ORDER BY r.id DESC LIMIT 1", (token,)).fetchone()
    conn.close()
    return row[0]


def test_the_public_form_offers_internal_staff_only(client, walkin, people):
    html = client.get(f"/r/{walkin}").text
    assert 'name="served_by_rp_id"' in html and "Who served you?" in html
    assert f'<option value="{people["internal"]}">Served Bytest' in html
    assert "Outside Speaker" not in html
    assert "Sino ang tumulong sa iyo?" in client.get(f"/r/{walkin}", cookies={"lang": "fil"}).text


def test_the_question_comes_after_about_you_and_is_its_own_step(client, walkin, people):
    html = client.get(f"/r/{walkin}").text
    assert html.index('data-conv="demo"') < html.index('data-conv="served"') < html.index('data-conv="cc"')


def test_a_public_answer_is_stored(client, app_mod, walkin, people):
    r = client.post(f"/r/{walkin}", content=_answers() + f"&served_by_rp_id={people['internal']}", headers=FORM)
    assert r.status_code == 200, r.text[:300]
    assert _latest_served(app_mod, walkin) == people["internal"]


@pytest.mark.parametrize("value", ["", "abc", "999999999", "-1"])
def test_blank_or_unknown_answers_store_nothing(client, app_mod, walkin, value):
    r = client.post(f"/r/{walkin}", content=_answers() + f"&served_by_rp_id={value}", headers=FORM)
    assert r.status_code == 200
    assert _latest_served(app_mod, walkin) is None


def test_an_external_person_cannot_be_credited(client, app_mod, walkin, people):
    r = client.post(f"/r/{walkin}", content=_answers() + f"&served_by_rp_id={people['external']}", headers=FORM)
    assert r.status_code == 200
    assert _latest_served(app_mod, walkin) is None


def test_the_paper_entry_form_asks_and_stores_it(admin, app_mod, walkin, people):
    html = admin.get(f"/encode/{walkin}").text
    assert 'name="served_by_rp_id"' in html and "Who served the client?" in html
    assert "Served Bytest" in html and "Outside Speaker" not in html
    r = admin.post(f"/encode/{walkin}", content=_answers() + f"&served_by_rp_id={people['internal']}",
                   headers=FORM, follow_redirects=False)
    assert r.status_code == 303, r.text[:300]
    assert _latest_served(app_mod, walkin) == people["internal"]


def test_the_activity_form_does_not_ask(client, app_mod):
    conn = st.connect(app_mod.DB); st.init_db(conn)
    f2 = st.create_form_instance(conn, 2, "F2", _test_tz.today_local().isoformat(), topic="SERVED Forum")
    token = conn.execute("SELECT qr_token FROM form_instance WHERE id=?", (f2,)).fetchone()[0]
    conn.close()
    assert 'name="served_by_rp_id"' not in client.get(f"/r/{token}").text
