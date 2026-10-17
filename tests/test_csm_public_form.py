"""The public Type-1 (walk-in service / CSM) form follows the official ARTA Client Satisfaction Measurement form
(MC 2022-05 as amended by 2023-05): the intro and confidentiality text, the client questions, the Citizen's Charter
definition and CC1-CC3, and suggestions and email (Spot Feedback #121). Only Type 1 changes: the activity (Type 2) and
resource-person (Type 3) forms are untouched. Everything except the SQD ratings is optional."""
from __future__ import annotations
import re
from datetime import date

import pytest

import app
import i18n
import storage as st

FORM = {"content-type": "application/x-www-form-urlencoded"}
NOT_KNOWN = app.CSM_CC1_OPTS[3]


# ------------------------------------------------------------------ what is stored (pure) ---

def meta(**kw):
    return app._csm_public_meta(kw)


def test_good_answers_are_kept_in_the_words_the_report_counts():
    got = meta(csm_client_type="Business", sex="f", csm_age="34", csm_region="NCR", csm_service="Technical Assistance",
               csm_email="ana@example.com", csm_cc1=app.CSM_CC1_OPTS[0], csm_cc2=app.CSM_CC2_OPTS[1], csm_cc3=app.CSM_CC3_OPTS[0])
    assert got == {"CLIENT_TYPE": "Business", "SEX": "Female", "AGE": "34", "REGION": "NCR", "SERVICE": "Technical Assistance",
                   "EMAIL": "ana@example.com", "CC1": app.CSM_CC1_OPTS[0], "CC2": app.CSM_CC2_OPTS[1], "CC3": app.CSM_CC3_OPTS[0]}


def test_nothing_is_required_and_blanks_store_nothing():
    assert meta() == {}
    assert meta(csm_client_type="", sex="", csm_age="", csm_region="", csm_service="  ", csm_email="") == {}


def test_values_the_report_does_not_know_are_dropped():
    got = meta(csm_client_type="Alien", sex="X", csm_age="-4", csm_region="Mars", csm_email="not-an-email",
               csm_cc1="whatever", csm_cc2=app.CSM_CC2_OPTS[0], csm_cc3=app.CSM_CC3_OPTS[0])
    assert got == {}                                              # a CC2/CC3 with no valid CC1 is dropped too
    assert meta(csm_age="0") == {} and meta(csm_age="121") == {} and meta(csm_age="12.5") == {} and meta(csm_age="1e3") == {}
    assert meta(csm_age="120") == {"AGE": "120"} and meta(csm_age="7") == {"AGE": "7"}


def test_the_service_is_free_text_but_cleaned_and_capped():
    assert meta(csm_service="Data\x00 Request\n") == {"SERVICE": "Data Request"}
    assert len(meta(csm_service="x" * 500)["SERVICE"]) == 120


def test_not_knowing_what_a_charter_is_marks_cc2_and_cc3_not_applicable():
    got = meta(csm_cc1=NOT_KNOWN, csm_cc2=app.CSM_CC2_OPTS[0], csm_cc3=app.CSM_CC3_OPTS[0])
    assert got == {"CC1": NOT_KNOWN, "CC2": app.CSM_CC2_OPTS[4], "CC3": app.CSM_CC3_OPTS[3]}
    assert got["CC2"] == got["CC3"] == "Not applicable"
    assert meta(csm_cc1=app.CSM_CC1_OPTS[1]) == {"CC1": app.CSM_CC1_OPTS[1]}               # aware: CC2/CC3 are whatever they answered


@pytest.mark.parametrize("sex,want", [("M", "Male"), ("m", "Male"), ("F", "Female"), ("Female", "")])
def test_sex_is_stored_as_the_report_spells_it(sex, want):
    assert meta(sex=sex).get("SEX", "") == want


def test_the_display_labels_line_up_with_the_stored_options():
    assert (len(i18n.CSM_CC1_FIL), len(i18n.CSM_CC2_FIL), len(i18n.CSM_CC3_FIL)) == \
        (len(app.CSM_CC1_OPTS), len(app.CSM_CC2_OPTS), len(app.CSM_CC3_OPTS))
    for key in ("csm_intro", "csm_cc_instr", "csm_cc1_q", "csm_suggest", "csm_confidential", "csm_ct_government"):
        assert i18n.UI[key]["en"] and i18n.UI[key]["fil"] and i18n.UI[key]["en"] != i18n.UI[key]["fil"]


# ------------------------------------------------------------------ the page ---

@pytest.fixture
def walkin(app_mod):
    conn = st.connect(app_mod.DB); st.init_db(conn)
    token = st.get_or_create_walkin_form(conn)["qr_token"]
    conn.close()
    return token


@pytest.fixture
def activity_form(app_mod):
    conn = st.connect(app_mod.DB); st.init_db(conn)
    f2 = st.create_form_instance(conn, 2, "F2", date.today().isoformat(), topic="CSMTEST Forum")
    token = conn.execute("SELECT qr_token FROM form_instance WHERE id=?", (f2,)).fetchone()[0]
    conn.close()
    return token


def test_the_walk_in_form_carries_the_official_text_and_questions(client, walkin):
    html = client.get(f"/r/{walkin}").text
    assert "Help us serve you better!" in html
    assert "tracks the customer experience of government offices" in html
    assert "Personal information shared will be kept confidential and you always have the option to not answer this form." in html
    assert "The Citizen's Charter is an official document that reflects the services of a government agency/office" in html \
        or "The Citizen&#39;s Charter is an official document that reflects the services of a government agency/office" in html
    for name in ("csm_client_type", "sex", "csm_age", "csm_region", "csm_service", "affil", "csm_cc1", "csm_cc2", "csm_cc3", "csm_email"):
        assert f'name="{name}"' in html, name
    assert "Suggestions on how we can further improve our services" in html
    assert "Government (employee or another agency)" in html
    for opt in app.CSM_CC1_OPTS + app.CSM_CC2_OPTS + app.CSM_CC3_OPTS:
        assert f'value="{opt}"'.replace("'", "&#39;") in html or f'value="{opt}"' in html, opt
    for service in app.CSM_SERVICES:                                 # the bureau's own service list
        assert f'<option value="{service}">' in html, service


def test_the_date_is_shown_not_asked(client, walkin):
    html = client.get(f"/r/{walkin}").text
    today = date.today()
    assert f"{today:%B} {today.day}, {today.year}" in html
    assert 'name="csm_date"' not in html and 'type="date"' not in html


def test_only_the_ratings_are_required(client, walkin):
    html = client.get(f"/r/{walkin}").text
    required = re.findall(r'<(?:input|select|textarea)[^>]*\brequired\b[^>]*name="([^"]+)"|<(?:input|select|textarea)[^>]*name="([^"]+)"[^>]*\brequired\b', html)
    names = {a or b for a, b in required}
    assert names and all(n.startswith("SQD") for n in names), names
    assert "(optional)" in html


def test_the_form_reads_in_filipino_too(client, walkin):
    html = client.get(f"/r/{walkin}", cookies={"lang": "fil"}).text
    assert "Tulungan kaming magsilbi nang mas mahusay!" in html
    assert i18n.CSM_CC1_FIL[3] in html and i18n.CSM_CC2_FIL[0] in html
    assert f'value="{app.CSM_CC1_OPTS[3]}"' in html or f'value="{app.CSM_CC1_OPTS[3]}"'.replace("'", "&#39;") in html   # the stored value stays English


def test_the_activity_form_is_unchanged(client, activity_form):
    html = client.get(f"/r/{activity_form}").text
    assert "Help us serve you better" not in html and "csm_cc1" not in html and "csm_age" not in html
    assert 'name="sex" required' in html or re.search(r'<select id="f-sex" name="sex" required', html)
    assert re.search(r'<select id="f-affil" name="affil" required', html)
    assert "Your answers are anonymous." in html


# ------------------------------------------------------------------ submitting ---

def _answers():
    return "&".join(f"SQD{i}=5" for i in range(9))


def _remarks(app_mod, token):
    conn = st.connect(app_mod.DB)
    rid = conn.execute("SELECT MAX(r.id) FROM response r JOIN form_instance fi ON fi.id=r.form_instance_id WHERE fi.qr_token=?",
                       (token,)).fetchone()[0]
    rows = dict(conn.execute("SELECT item_id, text FROM item_remark WHERE response_id=?", (rid,)).fetchall())
    conn.close()
    return rows


def test_a_full_submission_is_stored_the_way_the_paper_entry_stores_it(client, app_mod, walkin):
    body = (_answers() + "&csm_client_type=Citizen&sex=M&affil=NON-DOH&csm_age=41&csm_region=Region+III&csm_service=Data+Request"
            f"&csm_email=ana%40example.com&csm_cc1={NOT_KNOWN.replace(' ', '+').replace(chr(39), '%27')}"
            "&csm_cc2=Easy+to+see&csm_cc3=Helped+very+much&remarks=Thank+you")
    r = client.post(f"/r/{walkin}", content=body, headers=FORM)
    assert r.status_code == 200, r.text[:300]
    got = _remarks(app_mod, walkin)
    assert got["CLIENT_TYPE"] == "Citizen" and got["SEX"] == "Male" and got["AFFIL"] == "NON-DOH"
    assert (got["AGE"], got["REGION"], got["SERVICE"], got["EMAIL"]) == ("41", "Region III", "Data Request", "ana@example.com")
    assert got["CC1"] == NOT_KNOWN and got["CC2"] == "Not applicable" and got["CC3"] == "Not applicable"


def test_a_ratings_only_submission_still_works(client, app_mod, walkin):
    r = client.post(f"/r/{walkin}", content=_answers(), headers=FORM)
    assert r.status_code == 200
    got = _remarks(app_mod, walkin)
    assert not ({"CLIENT_TYPE", "AGE", "REGION", "SERVICE", "EMAIL", "CC1", "CC2", "CC3"} & set(got))


def test_hostile_values_are_dropped_not_stored(client, app_mod, walkin):
    body = (_answers() + "&csm_client_type=%3Cscript%3E&sex=Z&csm_age=999&csm_region=%27%3B+DROP+TABLE&csm_email=a%40b"
            "&csm_cc1=x&csm_cc2=y&csm_cc3=z&csm_service=" + "A" * 900)
    r = client.post(f"/r/{walkin}", content=body, headers=FORM)
    assert r.status_code == 200
    got = _remarks(app_mod, walkin)
    assert not ({"CLIENT_TYPE", "SEX", "AGE", "REGION", "EMAIL", "CC1", "CC2", "CC3"} & set(got))
    assert len(got["SERVICE"]) == 120


def test_online_responses_now_show_up_in_the_official_report_rows(client, app_mod, walkin):
    body = _answers() + "&csm_client_type=Business&sex=F&csm_age=29&csm_region=NCR&csm_service=Inquiry"
    assert client.post(f"/r/{walkin}", content=body, headers=FORM).status_code == 200
    conn = st.connect(app_mod.DB)
    rows = app._csm_blhsd_rows(conn)
    conn.close()
    mine = [r for r in rows if r["SERVICE"] == "Inquiry" and r["AGE"] == "29"]
    assert mine and mine[-1]["CLIENT_TYPE"] == "Business" and mine[-1]["SEX"] == "Female" and mine[-1]["REGION"] == "NCR"
