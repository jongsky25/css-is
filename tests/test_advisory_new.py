"""Increment 2 of docs/ADVISORY_SLIDES_PLAN.md: the New advisory flow, with a fake relay (no network)."""
import base64
import re
import uuid
from datetime import date, timedelta
from html import unescape

import pytest

import advisory_new as new_flow
import advisory_workflow as aw
import gdocs_relay
import storage as st
from tests.conftest import ROLE_USERS

def _png():
    from PIL import Image, ImageDraw
    import io
    img = Image.new("RGB", (320, 453), "white")
    d = ImageDraw.Draw(img)
    d.rectangle([0, 0, 320, 70], fill=(20, 60, 140)); d.rectangle([20, 110, 300, 130], fill=(200, 200, 200))
    d.rectangle([20, 150, 260, 165], fill=(220, 220, 220)); d.rectangle([220, 360, 300, 440], fill=(0, 0, 0))
    buf = io.BytesIO(); img.save(buf, "PNG"); return buf.getvalue()


PNG = _png()


class FakeRelay:
    def __init__(self):
        self.calls, self.fail_create = [], None

    def __call__(self, action, **fields):
        self.calls.append((action, fields))
        if action == "advisory_info":
            return gdocs_relay.RelayResult(True, data={"variants": [
                {"variant": n, "slide_id": f"s{n}", "placeholders": ["number", "title"],
                 "png_b64": base64.b64encode(PNG).decode()} for n in (1, 2, 3)]})
        if action == "advisory_create":
            if self.fail_create:
                return gdocs_relay.RelayResult(False, error=self.fail_create)
            n = fields["request_id"].split("-")[1]
            return gdocs_relay.RelayResult(True, data={"id": f"SLIDES{n:0>20}", "url": f"https://docs.google.com/presentation/d/x{n}/edit",
                                                       "name": fields["title"], "version": "2", "unfilled": ["venue"], "qr": "placed"})
        return gdocs_relay.RelayResult(False, error="unknown_action")

    def created(self):
        return [f for a, f in self.calls if a == "advisory_create"]


@pytest.fixture
def flow(manager, db_path, monkeypatch):
    c = st.connect(db_path)
    user = st.get_admin_user(c, ROLE_USERS["section_manager"])
    division = st.add_org_unit(c, "Health Systems Division", "division", "NEWADV/HSD", "HSD")
    section = st.add_org_unit(c, "Equity Section", "section", "NEWADV/HSD/EQ", "EQ")
    me = st.add_rp(c, "Mara Manager", True, section, email="mara@doh.gov.ph")
    mate = st.add_rp(c, "Sam Section", True, section, email="sam@doh.gov.ph")
    st.add_rp(c, "Old Staff", True, section, email="gone@doh.gov.ph")
    c.execute("UPDATE resource_person SET archived_at='2026-01-01' WHERE email='gone@doh.gov.ph'")
    st.add_rp(c, "Outside Person", False, section, email="out@example.com")
    c.execute("UPDATE admin_user SET rp_id=? WHERE id=?", (me, user["id"]))
    viewer = st.get_admin_user(c, ROLE_USERS["viewer"])
    c.execute("UPDATE admin_user SET rp_id=? WHERE id=?", (mate, viewer["id"]))
    day = (date.today() + timedelta(days=20)).isoformat()
    ev = st.create_event(c, "JOAS Batch 2", day, venue="Manila", created_by=user["username"], lead_org_id=section)
    st.set_setting(c, "documents.enabled", "1"); st.set_setting(c, "work.enabled", "1"); c.commit()
    relay = FakeRelay()
    monkeypatch.setenv(gdocs_relay.ENV_URL, "https://relay.example.invalid/exec")
    monkeypatch.setenv(gdocs_relay.ENV_SECRET, "test-secret")
    monkeypatch.setattr(gdocs_relay, "call", relay)
    import mailer
    monkeypatch.setattr(mailer, "send", lambda *a, **k: pytest.fail("No email may be sent"))
    yield {"c": c, "user": user, "division": division, "section": section, "ev": ev, "relay": relay, "day": day}
    c.close()


def hidden(page):
    return {n: unescape(v) for n, v in re.findall(r'<input type="hidden" name="([^"]+)" value="([^"]*)">', page.text)}


def details_form(page, **over):
    data = hidden(page)
    data.update({"title": "JOAS Batch 2 confirmation", "dates": "Dec 15-17, 2026", "venue": "Manila", "message": "",
                 "attention": "LHSD Chiefs", "contact": "June, loc 1308", "link": "", "variant": "2",
                 "audience": "internal", "external": ""})
    data.update(over)
    return data


def test_register_offers_new_advisory_and_explains_the_steps(flow, manager):
    page = manager.get("/advisories")
    assert page.status_code == 200
    assert 'href="/advisories/new"' in page.text and "How advisories work" in page.text
    assert "No advisories yet." in page.text


def test_step_one_shows_three_choices_and_finds_my_activities(flow, manager, encoder):
    page = manager.get("/advisories/new")
    for text in ("An activity already in Office Connect", "A new activity", "Not about an activity"):
        assert text in page.text
    listing = manager.get("/advisories/new?pick=activity&q=joas")
    assert "JOAS Batch 2" in listing.text and f"event={flow['ev']['event_token']}" in listing.text
    assert "No activity you manage" in manager.get("/advisories/new?pick=activity&q=nothing-like-this").text
    assert "JOAS Batch 2" not in encoder.get("/advisories/new?pick=activity").text


def test_activity_advisory_is_created_with_a_slides_file_shared_with_the_section(flow, manager, viewer):
    c, ev = flow["c"], flow["ev"]
    page = manager.get(f"/advisories/new/details?kind=activity&event={ev['event_token']}")
    assert page.status_code == 200
    assert 'value="JOAS Batch 2"' in page.text and "/advisories/designs/1.png" in page.text
    assert f'<option value="{flow["division"]}" selected' in page.text          # owning division guessed from my section
    data = details_form(page)
    made = manager.post("/advisories/new", data=data, follow_redirects=False)
    assert made.status_code == 303 and made.headers["location"].endswith("?made=1")
    record = aw.for_event(c, ev["id"])
    assert record["kind"] == "activity" and record["section_id"] == flow["section"]
    assert re.fullmatch(r"\d{4}-\d{4}-\d{3}", record["number"])
    sent = flow["relay"].created()[0]
    assert sent["variant"] == 2 and sent["fields"]["number"] == record["number"]
    assert sent["editors"] == ["mara@doh.gov.ph", "sam@doh.gov.ph"]             # no archived or outside people
    assert sent["fields"]["link"].endswith(f"/e/{ev['event_token']}") and "qr_png_b64" in sent
    home = manager.get(made.headers["location"])
    assert "Open in Google Slides" in home.text and "Advisory created" in home.text
    assert "left empty: venue" in home.text and 'aria-current="step">Draft' in home.text
    # replaying the same form returns the same advisory; no second number or file
    assert manager.post("/advisories/new", data=data, follow_redirects=False).headers["location"].startswith(
        made.headers["location"].split("?")[0])
    assert c.execute("SELECT COUNT(*) FROM advisory_record").fetchone()[0] == 1
    assert len(flow["relay"].created()) == 1
    # a section member can open it; the activity entry and a second start go to the same advisory
    assert viewer.get(made.headers["location"].split("?")[0]).status_code == 200
    assert manager.get(f"/activities/{ev['event_token']}/advisory/draft", follow_redirects=False).headers["location"] == \
        made.headers["location"].split("?")[0]
    again = manager.get(f"/advisories/new/details?kind=activity&event={ev['event_token']}", follow_redirects=False)
    assert again.status_code == 303
    assert c.execute("SELECT COUNT(*) FROM document_notice").fetchone()[0] == 0


def test_general_advisory_needs_no_activity_and_appears_in_the_register(flow, manager, admin):
    page = manager.get("/advisories/new/details?kind=general")
    assert "A general advisory" in page.text and 'name="dates"' not in page.text
    made = manager.post("/advisories/new", data=details_form(page, title="Office closed on Friday", link=""),
                        follow_redirects=False)
    aid = int(made.headers["location"].split("/")[2].split("?")[0])
    record = flow["c"].execute("SELECT kind,event_id FROM advisory_record WHERE id=?", (aid,)).fetchone()
    assert tuple(record) == ("general", None)
    assert "qr_png_b64" not in flow["relay"].created()[0]                       # no link, no QR
    register = manager.get("/advisories")
    assert "Office closed on Friday" in register.text and "General" in register.text
    assert f"/advisories/{aid}" not in admin.get("/advisories").text            # private to those preparing it
    assert admin.get(f"/advisories/{aid}").status_code == 404


def test_new_activity_is_made_together_with_its_advisory(flow, manager):
    c = flow["c"]
    page = manager.get("/advisories/new/details?kind=new_activity")
    assert "Organizing section" in page.text
    bad = manager.post("/advisories/new", data=details_form(page, activity_date="", section_id=str(flow["section"]),
                                                             title="Planning workshop"), follow_redirects=False)
    assert bad.status_code == 422 and "Choose the date" in bad.text and 'value="Planning workshop"' in bad.text
    made = manager.post("/advisories/new", data=details_form(page, activity_date=flow["day"], section_id=str(flow["section"]),
                                                             title="Planning workshop"), follow_redirects=False)
    assert made.status_code == 303
    ev = c.execute("SELECT id,title,lead_org_id FROM event WHERE title='Planning workshop'").fetchone()
    assert ev is not None and ev[2] == flow["section"]
    assert aw.for_event(c, ev[0])["kind"] == "activity"


def test_mistakes_keep_what_was_typed_and_say_how_to_fix_them(flow, manager):
    page = manager.get("/advisories/new/details?kind=general")
    cases = [({"title": ""}, "Give the advisory a title"),
             ({"audience": "both", "external": ""}, "Add at least one outside email address"),
             ({"audience": "internal", "external": "a@example.org"}, "chose office staff only"),
             ({"audience": "both", "external": "not-an-email"}, '"not-an-email" is not an email address'),
             ({"link": "www.example.org"}, "should start with https://"),
             ({"variant": "9"}, "Choose a design")]
    for over, message in cases:
        reply = manager.post("/advisories/new", data=details_form(page, message="Keep my words", **over), follow_redirects=False)
        assert reply.status_code == 422, over
        assert message in unescape(reply.text) and "Keep my words" in reply.text
        assert "Go to it" in reply.text
    assert flow["c"].execute("SELECT COUNT(*) FROM advisory_record").fetchone()[0] == 0


def test_relay_failure_leaves_a_try_again_button_that_makes_one_file(flow, manager, viewer):
    flow["relay"].fail_create = "unreachable"
    page = manager.get("/advisories/new/details?kind=general")
    made = manager.post("/advisories/new", data=details_form(page), follow_redirects=False)
    assert made.headers["location"].endswith("?made=0")
    home = manager.get(made.headers["location"])
    assert "Google Slides could not be reached" in home.text and "Try again" in home.text
    aid = made.headers["location"].split("/")[2].split("?")[0]
    flow["relay"].fail_create = None
    assert manager.post(f"/advisories/{aid}/slides", follow_redirects=False).headers["location"].endswith("?made=1")
    assert manager.post(f"/advisories/{aid}/slides", follow_redirects=False).status_code == 303
    assert len([1 for f in flow["relay"].created()]) == 2                       # one failure, then one success
    assert len({f["request_id"] for f in flow["relay"].created()}) == 1         # same request id on retry
    assert "Open in Google Slides" in manager.get(f"/advisories/{aid}").text


def test_switched_off_relay_explains_itself_and_keeps_the_old_editor(flow, manager, monkeypatch):
    monkeypatch.delenv(gdocs_relay.ENV_URL)
    assert "not switched on yet" in manager.get("/advisories/new").text
    page = manager.get("/advisories/new/details?kind=general")
    assert "fieldset disabled" in page.text
    reply = manager.post("/advisories/new", data=details_form(page), follow_redirects=False)
    assert reply.status_code == 422
    legacy = manager.get(f"/activities/{flow['ev']['event_token']}/advisory/draft", follow_redirects=False)
    assert legacy.status_code == 200


def test_numbers_continue_the_day_count_across_old_and_new_records(flow):
    c = flow["c"]
    day = date(2026, 11, 24)
    c.execute("INSERT INTO event_advisory(event_id,number,seq_date,seq,headline,created_by,created_at,updated_by,updated_at) "
              "VALUES (?,?,?,?,?,?,?,?,?)", (flow["ev"]["id"], "2026-1124-004", day.isoformat(), 4, "Old", "x", "t", "x", "t"))
    assert new_flow._reserve_number(c, day) == "2026-1124-005"


def test_send_for_review_waits_for_the_next_update(flow, manager):
    page = manager.get("/advisories/new/details?kind=general")
    made = manager.post("/advisories/new", data=details_form(page), follow_redirects=False)
    aid = made.headers["location"].split("/")[2].split("?")[0]
    reply = manager.post(f"/advisories/{aid}/actions", data={"action": "submit", "expected_revision": "1",
                                                              "operation_key": str(uuid.uuid4()), "reason": "x"})
    assert reply.status_code == 409 and "next update" in reply.text
