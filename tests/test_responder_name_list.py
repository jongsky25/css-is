"""A name list of the people who responded, from an activity's report (Spot Feedback #91).

The report page is open to more people than the roster is, so the button appears only for people who may manage the
activity (the Monitor page's own rule), and the roster page can show just the registered people who responded.
Survey answers stay anonymous: only registered people have a name; walk-in and paper responses are counted, not named."""
from __future__ import annotations
import tzutil as _test_tz
import re
from datetime import date, timedelta

import pytest
from starlette.testclient import TestClient

import storage as st

_PAST = (_test_tz.today_local() - timedelta(days=5)).isoformat()


def _activity(db_path, title, created_by="admin@test.local", event_date=_PAST):
    conn = st.connect(db_path)
    f2 = st.create_form_instance(conn, 2, "F2", event_date, topic="Event review")
    ev = st.create_event(conn, title, event_date, form_instance_ids=[f2], created_by=created_by)
    qr = conn.execute("SELECT qr_token FROM form_instance WHERE id=?", (f2,)).fetchone()[0]
    out = {"token": ev["event_token"], "id": ev["id"], "qr": qr, "report": None}
    conn.close()
    return out


def _register(app_mod, tok, name, email):
    c = TestClient(app_mod.app, raise_server_exceptions=True)
    r = c.post(f"/e/{tok}", data={"name": name, "email": email, "sex": "F", "affiliation": "DOH", "consent": "on"},
               follow_redirects=False)
    assert r.status_code == 303
    return c, re.search(r"att=([^&]+)", r.headers["location"]).group(1)


def _respond(client, qr, att):
    r = client.post(f"/r/{qr}", data={"seq": "", "att": att, "A": "6", "B1": "6", "C": "4", "remarks": "fine"})
    assert r.status_code == 200


def _report_url(db_path, act):
    import app as app_mod
    app_mod.invalidate_atoms(); app_mod.invalidate_views()            # the report reads cached views; make them see this data
    conn = st.connect(db_path)
    url = st.event_report_url(conn, act["id"])
    conn.close()
    return url


@pytest.fixture
def activity(app_mod, db_path):
    """One activity: Ana responded, Ben registered but did not, plus one walk-in response with no name."""
    act = _activity(db_path, "NAMELIST Forum")
    ana, ana_att = _register(app_mod, act["token"], "Ana Responder", "ana-nl@example.com")
    _register(app_mod, act["token"], "Ben Quiet", "ben-nl@example.com")
    _respond(ana, act["qr"], ana_att)
    TestClient(app_mod.app).post(f"/r/{act['qr']}", data={"A": "5", "B1": "5", "C": "3"})        # a walk-in, no name
    act["report"] = _report_url(db_path, act)
    assert act["report"], "the activity should have a report once it has responses"
    return act


# ------------------------------------------------------------------ the button on the report ---

def test_an_admin_sees_the_button_with_the_counts(admin, activity):
    html = admin.get(activity["report"]).text
    assert "See the name list" in html
    assert f'href="/monitor/{activity["token"]}?show=responded"' in html
    assert "1 of 2 registered people responded" in html
    assert "1 more answered without a name" in html
    assert "Names are shown only to the people who manage this activity." in html


def test_someone_who_cannot_manage_the_activity_gets_no_button_and_no_names(viewer, activity):
    r = viewer.get(activity["report"])
    assert r.status_code == 200                                  # the report itself is theirs to read
    assert "See the name list" not in r.text and "/monitor/" not in r.text
    assert "Ana Responder" not in r.text and "Ben Quiet" not in r.text and "registered people responded" not in r.text


def test_the_creator_of_the_activity_sees_the_button(app_mod, db_path):
    act = _activity(db_path, "NAMELIST Creator Forum", created_by="viewer@test.local")
    ana, att = _register(app_mod, act["token"], "Cara Creator", "cara-nl@example.com")
    _respond(ana, act["qr"], att)
    url = _report_url(db_path, act)
    from tests.conftest import _auth_client
    assert "See the name list" in _auth_client(app_mod, "viewer").get(url).text


def test_no_button_when_nobody_registered(admin, app_mod, db_path):
    # its own date: activities that share a date, venue and organizer are merged into one report
    act = _activity(db_path, "NAMELIST Walk-in Forum", event_date=(_test_tz.today_local() - timedelta(days=40)).isoformat())
    TestClient(app_mod.app).post(f"/r/{act['qr']}", data={"A": "5", "B1": "5", "C": "3"})
    url = _report_url(db_path, act)
    r = admin.get(url)
    assert r.status_code == 200 and "See the name list" not in r.text


# ------------------------------------------------------------------ the name list itself ---

def test_the_name_list_shows_only_people_who_responded(admin, activity):
    page = admin.get(f"/monitor/{activity['token']}?show=responded").text
    assert "Ana Responder" in page and "Ben Quiet" not in page
    assert "Showing the 1 registered participant who responded" in page and "out of 2 registered" in page
    assert f'href="/monitor/{activity["token"]}"' in page            # a way back to everyone


def test_the_plain_roster_is_unchanged_and_offers_the_filtered_view(admin, activity):
    page = admin.get(f"/monitor/{activity['token']}").text
    assert "Ana Responder" in page and "Ben Quiet" in page
    assert "Show only the people who responded" in page and "Showing the" not in page


def test_the_reminder_count_does_not_depend_on_the_view(admin, activity):
    def count(url):
        m = re.search(r'id="remindAll"[^>]*data-count="(\d+)"', admin.get(url).text)
        return m.group(1) if m else None
    assert count(f"/monitor/{activity['token']}?show=responded") == count(f"/monitor/{activity['token']}")


def test_an_empty_responded_view_says_so(admin, app_mod, db_path):
    act = _activity(db_path, "NAMELIST Quiet Forum")
    _register(app_mod, act["token"], "Dan Silent", "dan-nl@example.com")
    page = admin.get(f"/monitor/{act['token']}?show=responded").text
    assert "No registered participant has responded yet." in page and "Dan Silent" not in page


def test_the_roster_stays_closed_to_people_who_cannot_manage_the_activity(viewer, activity):
    r = viewer.get(f"/monitor/{activity['token']}?show=responded", follow_redirects=False)
    assert r.status_code in (303, 403) and "Ana Responder" not in r.text


def test_a_merged_report_offers_one_name_list_per_activity(admin, app_mod, db_path):
    """Activities with the same date, venue and organizer share one report; each keeps its own roster."""
    day = (_test_tz.today_local() - timedelta(days=61)).isoformat()
    a = _activity(db_path, "NAMELIST Session One", event_date=day)
    b = _activity(db_path, "NAMELIST Session Two", event_date=day)
    for act, who in ((a, "Eve One"), (b, "Fay Two")):
        c, att = _register(app_mod, act["token"], who, f"{who.split()[0].lower()}-nl@example.com")
        _respond(c, act["qr"], att)
    html = admin.get(_report_url(db_path, a)).text
    assert html.count("See the name list") == 2
    assert f'/monitor/{a["token"]}?show=responded' in html and f'/monitor/{b["token"]}?show=responded' in html
    assert "NAMELIST Session One" in html and "NAMELIST Session Two" in html
