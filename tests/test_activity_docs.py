"""Documents an activity needs (Spot Feedback #136): the suggestion, the owner's choice, the Google Doc draft."""
from __future__ import annotations
import json
import shutil
import subprocess
from urllib.parse import urlencode

import pytest

import activity_docs as ad
import storage as st
from test_calendar_entry_pages import conn, create, uid, FORM  # noqa: F401  (shared calendar fixtures)
from test_travel_generate import relay  # noqa: F401


# -------------------------------------------------------------- the suggestion ---

def entry(**kw):
    return {"id": 1, "kind": "meeting", "audience": "unit", "people": [], **kw}


def test_travelling_people_suggest_a_dpo():
    out = ad.suggest(entry(people=[{"user_id": 1, "role": "travel"}, {"user_id": 2, "role": "travel"}]))
    assert out["dpo"] == (True, "2 people are travelling for this activity.")
    assert ad.suggest(entry(people=[{"user_id": 1, "role": "travel"}]))["dpo"][1] == "1 person is travelling for this activity."


def test_a_trip_suggests_a_dpo_and_an_internal_meeting_suggests_nothing():
    assert ad.suggest(entry(kind="travel"))["dpo"][0] is True
    plain = ad.suggest(entry())
    assert plain["dpo"][0] is False and plain["invitation"][0] is False


def test_a_bureau_wide_or_training_item_suggests_an_invitation():
    assert ad.suggest(entry(audience="bureau"))["invitation"] == (True, "It is open to everyone in the bureau.")
    assert ad.suggest(entry(kind="training"), "Training / workshop")["invitation"][0] is True


def test_when_and_where_read_as_one_line_each():
    e = {"start_date": "2026-10-12", "end_date": "2026-10-14", "start_time": "09:00", "end_time": "16:00",
         "venue": "Hotel Ozamiz", "modality": "hybrid", "time_note": None}
    assert ad.when_text(e).endswith(", 09:00 to 16:00") and ad.where_text(e) == "Hotel Ozamiz (hybrid)"
    assert ad.where_text({"venue": "", "modality": ""}) == "To be announced"
    assert ad.where_text({"venue": "Room 2", "modality": "f2f"}) == "Room 2"


# ------------------------------------------------------------------- the page ---

def entry_page(viewer, eid):
    r = viewer.get(f"/calendar/entries/{eid}")
    assert r.status_code == 200
    return r.text


def test_the_page_lists_both_documents_with_the_reason(viewer, conn):
    eid = create(viewer, audience="bureau")
    html = entry_page(viewer, eid)
    assert "Documents for this activity" in html and "Department Personnel Order (DPO)" in html
    assert "It is open to everyone in the bureau." in html and "Nobody is marked as travelling." in html
    assert html.index("Invitation") > 0 and "Suggested" in html


def test_an_item_that_never_needs_these_has_no_section(viewer, conn):
    eid = create(viewer, kind="deadline")
    assert "Documents for this activity" not in entry_page(viewer, eid)


def test_the_owner_can_overrule_the_suggestion_and_go_back(viewer, conn):
    eid = create(viewer, audience="bureau")
    r = viewer.post(f"/calendar/entries/{eid}/documents/invitation/needed", content=urlencode({"needed": "no"}),
                    headers=FORM, follow_redirects=False)
    assert r.status_code == 303 and "ok=" in r.headers["location"]
    assert ad.get_rows(conn, eid)["invitation"]["needed"] == 0
    html = entry_page(viewer, eid)
    assert "Your choice" in html and "Use the suggestion" in html
    assert "Draft in Google Docs" not in html                                   # not needed, so nothing to draft
    viewer.post(f"/calendar/entries/{eid}/documents/invitation/needed", content=urlencode({"needed": "auto"}), headers=FORM)
    assert ad.get_rows(conn, eid)["invitation"]["needed"] is None


def test_a_bad_choice_or_document_changes_nothing(viewer, conn):
    eid = create(viewer)
    for key, val in (("invitation", "maybe"), ("memo", "yes")):
        r = viewer.post(f"/calendar/entries/{eid}/documents/{key}/needed", content=urlencode({"needed": val}),
                        headers=FORM, follow_redirects=False)
        assert r.status_code == 303 and "err=" in r.headers["location"]
    assert ad.get_rows(conn, eid) == {}


# ------------------------------------------------------------------ drafting ---

def draft(viewer, eid, key):
    return viewer.post(f"/calendar/entries/{eid}/documents/{key}/draft", content="", headers=FORM, follow_redirects=False)


def test_drafting_an_invitation_sends_the_entry_details_and_links_the_doc(viewer, conn, relay):
    eid = create(viewer, audience="bureau", title="CALEP Planning Workshop", venue="Hotel Ozamiz",
                 meeting_url="https://meet.google.com/abc-defg-hij", note="private: budget is tight")
    r = draft(viewer, eid, "invitation")
    assert r.status_code == 303 and "ok=" in r.headers["location"]
    call = relay.calls[0]
    assert call["template_key"] == "invitation" and call["folder_key"] == f"act-{eid}"
    assert call["request_id"] == f"act{eid}:invitation:1" and call["title"] == "Invitation - CALEP Planning Workshop"
    assert call["fields"]["title"] == "CALEP Planning Workshop" and call["fields"]["invited"] == "All personnel of the bureau"
    details = call["blocks"]["details"]
    assert details[0] == "What: CALEP Planning Workshop" and "Where: Hotel Ozamiz" in details[2]
    assert "Join online: https://meet.google.com/abc-defg-hij" in details
    assert "budget" not in str(call)                                           # an entry's private note is never copied
    row = ad.get_rows(conn, eid)["invitation"]
    assert row["doc_state"] == "done" and row["doc_url"].startswith("https://docs.google.com/") and row["rev"] == 1
    assert "Open the latest draft" in entry_page(viewer, eid)


def test_a_dpo_follows_the_doh_order_and_leaves_the_blanks(viewer, conn, relay):
    eid = create(viewer, kind="travel", title="CALEP Field Visit", venue="Cebu City",
                 start_date="2026-10-12", end_date="2026-10-16", people=[str(uid(conn, "viewer@test.local"))])
    st.set_setting(conn, "travel.sig.head_name", "Dr. Ana Reyes"); st.set_setting(conn, "travel.sig.head_title", "Director IV")
    assert draft(viewer, eid, "dpo").status_code == 303
    call = relay.calls[0]
    f = call["fields"]
    assert call["template_key"] == "dpo"
    # the number, date and funding source are never guessed
    assert f["dpo_no"] == ad.BLANK and f["dpo_date"] == ad.BLANK and f["funding_source"] == ad.BLANK
    assert f["dpo_year"] == "2026"
    assert f["subject"].startswith("Authority for Select") and "CALEP Field Visit" in f["subject"] and "in Cebu City" in f["subject"]
    assert "CALEP Field Visit" in f["background"] and f["intro"].startswith("Authority is hereby given to the following select")
    assert f["intro"].endswith(":") and "October 12-16, 2026" in f["intro"]
    assert f["head_name"] == "DR. ANA REYES" and f["head_title"] == "Director IV"      # the signatory is printed in capitals
    # the personnel go in as a Name | Position table, and as lines for a template that still has a {{personnel}} line
    table = call["rows"]["personnel"]
    assert table["marker"] == "p_name" and len(table["data"]) == 1 and table["data"][0]["p_name"].startswith("1. ")
    assert set(table["data"][0]) == {"p_name", "p_position"}
    assert len(call["blocks"]["personnel"]) == 1 and call["blocks"]["personnel"][0].startswith("1. ")


def test_a_dpo_without_a_venue_or_unit_still_reads_as_a_sentence(viewer, conn, relay):
    eid = create(viewer, kind="travel", title="CALEP Field Visit", venue="", owner_org_id="")
    draft(viewer, eid, "dpo")
    f = relay.calls[0]["fields"]
    assert " in " not in f["subject"].split("CALEP Field Visit")[1] and f["subject"].startswith("Authority for Select Personnel")
    assert f["intro"].startswith("Authority is hereby given to the following select personnel")


def test_a_second_draft_is_a_new_revision(viewer, conn, relay):
    eid = create(viewer, audience="bureau")
    draft(viewer, eid, "invitation"); draft(viewer, eid, "invitation")
    assert [c["request_id"] for c in relay.calls] == [f"act{eid}:invitation:1", f"act{eid}:invitation:2"]
    assert ad.get_rows(conn, eid)["invitation"]["rev"] == 2


@pytest.mark.parametrize("code, words", [("template_not_set", "makeActivityTemplates"), ("unauthorized", "setup problem"),
                                         ("unreachable", "Try again")])
def test_a_failed_draft_says_what_to_do_in_plain_words(viewer, conn, relay, code, words):
    eid = create(viewer, audience="bureau")
    relay.fail["invitation"] = code
    r = draft(viewer, eid, "invitation")
    assert r.status_code == 303 and "err=" in r.headers["location"]
    row = ad.get_rows(conn, eid)["invitation"]
    assert row["doc_state"] == "failed" and words in row["note"] and row["doc_url"] == ""
    assert "secret" not in row["note"].lower() and "signature" not in row["note"].lower()
    assert words in entry_page(viewer, eid)


def test_nothing_is_drafted_when_google_docs_is_not_set_up(viewer, conn, monkeypatch):
    import gdocs_relay as gr
    monkeypatch.delenv(gr.ENV_URL, raising=False); monkeypatch.delenv(gr.ENV_SECRET, raising=False)
    eid = create(viewer, audience="bureau")
    r = draft(viewer, eid, "invitation")
    assert "err=" in r.headers["location"] and ad.get_rows(conn, eid) == {}
    assert "not switched on" in entry_page(viewer, eid)


def test_a_cancelled_item_cannot_be_drafted(viewer, conn, relay):
    eid = create(viewer, audience="bureau")
    viewer.post(f"/calendar/entries/{eid}/cancel", headers=FORM, follow_redirects=False)
    assert "err=" in draft(viewer, eid, "invitation").headers["location"] and relay.calls == []


# ------------------------------------------------ the Apps Script template and the app agree ---

@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_every_placeholder_in_the_dpo_template_is_one_the_app_fills(viewer, conn, relay):
    """Runs the template builder against a fake Docs API (the real one only runs in Google), then checks the
    placeholders it writes against what a draft sends, so a template and the app cannot drift apart."""
    out = subprocess.run(["node", "tests/js/activity_templates_stub.js", "apps_script/activity_templates.gs"],
                         capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    built = json.loads(out.stdout)
    assert built["missing"] == [] and set(built["expect"]) <= set(built["found"])      # it writes everything it promises
    eid = create(viewer, kind="travel", title="CALEP Field Visit", people=[str(uid(conn, "viewer@test.local"))])
    draft(viewer, eid, "dpo")
    call = relay.calls[0]
    filled = set(call["fields"]) | set(call["blocks"]) | {r["marker"] for r in call["rows"].values()} | {
        k for r in call["rows"].values() for d in r["data"] for k in d}
    unfilled = set(built["found"]) - filled
    assert unfilled == set(), f"in the template but never filled by the app: {sorted(unfilled)}"
