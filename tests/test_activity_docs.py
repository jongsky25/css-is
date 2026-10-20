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


def test_a_training_or_a_multi_day_item_suggests_a_concept_note_and_a_program():
    training = ad.suggest(entry(kind="training"), "Training / workshop")
    assert training["concept_note"][0] is True and training["program_flow"][0] is True
    multi = ad.suggest(entry(start_date="2026-10-12", end_date="2026-10-16"))
    assert multi["concept_note"][0] is True and multi["program_flow"][0] is True
    travelling = ad.suggest(entry(people=[{"user_id": 1, "role": "travel"}]))
    assert travelling["concept_note"][0] is True and travelling["program_flow"][0] is False     # a short trip needs no program
    plain = ad.suggest(entry(start_date="2026-10-12", end_date="2026-10-12"))
    assert plain["concept_note"][0] is False and plain["program_flow"][0] is False


def test_an_old_table_that_only_allowed_two_keys_is_rebuilt_and_keeps_its_rows(tmp_path):
    import sqlite3
    c = st.connect(str(tmp_path / "old.db")); st.init_db(c)
    c.executescript("""DROP TABLE calendar_entry_doc;
        CREATE TABLE calendar_entry_doc (entry_id INTEGER NOT NULL REFERENCES calendar_entry(id) ON DELETE CASCADE,
          doc_key TEXT NOT NULL CHECK (doc_key IN ('dpo','invitation')), needed INTEGER CHECK (needed IN (0,1)),
          doc_url TEXT, doc_state TEXT, note TEXT, rev INTEGER NOT NULL DEFAULT 0, updated_by TEXT, updated_at TEXT,
          PRIMARY KEY (entry_id, doc_key));
        INSERT INTO calendar_entry(id, uid, title, start_date) VALUES (7, 'u7', 'x', '2026-10-12');
        INSERT INTO calendar_entry_doc VALUES (7, 'dpo', 1, 'https://docs.google.com/d/1', 'done', '', 2, 'a', 't');""")
    with pytest.raises(sqlite3.IntegrityError):
        c.execute("INSERT INTO calendar_entry_doc(entry_id, doc_key) VALUES (7, 'concept_note')")
    st.init_db(c)
    assert c.execute("SELECT doc_key, needed, doc_url, rev FROM calendar_entry_doc").fetchall() == [
        ("dpo", 1, "https://docs.google.com/d/1", 2)]
    c.execute("INSERT INTO calendar_entry_doc(entry_id, doc_key) VALUES (7, 'concept_note')")
    st.init_db(c)                                                         # a second run changes nothing
    assert c.execute("SELECT COUNT(*) FROM calendar_entry_doc").fetchone()[0] == 2


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
    assert "Concept note" in html and "Program flow" in html


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
    assert call["request_id"] == f"act{eid}:invitation:1" and call["title"] == "Memorandum - CALEP Planning Workshop"
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

def test_the_invitation_is_the_doh_memorandum_with_the_request_table(viewer, conn, relay):
    st.set_setting(conn, "travel.sig.head_name", "Dr. Ana Reyes"); st.set_setting(conn, "travel.sig.head_title", "OIC - Director IV")
    eid = create(viewer, audience="bureau", title="CALEP Planning Workshop", venue="Hotel Ozamiz",
                 start_date="2026-10-12", end_date="2026-10-16")
    assert draft(viewer, eid, "invitation").status_code == 303
    f, call = relay.calls[0]["fields"], relay.calls[0]
    assert f["subject"] == "Request for Assistance in the Conduct of CALEP Planning Workshop"
    assert "respectfully request" in f["opening"] and "CALEP Planning Workshop" in f["opening"]
    assert "October 12-16, 2026" in f["opening"] and f["opening"].rstrip().endswith("in Hotel Ozamiz.")
    # who it is for, and the phone, are never guessed
    assert f["for_name"] == f["for_title"] == f["for_office"] == f["contact_phone"] == ad.BLANK
    assert f["from_name"] == "DR. ANA REYES" and f["from_title"] == "OIC - Director IV"
    assert f["contact_name"] and f["contact_email"] == "viewer@test.local"
    table = call["rows"]["assistance"]
    assert table["marker"] == "a_area" and [r["a_area"] for r in table["data"]] == ["Participants", "Venue", "Meals", "Coordination"]
    assert all(set(r) == {"a_area", "a_request"} and r["a_request"] for r in table["data"])


def test_a_concept_note_fills_what_the_item_knows_and_prompts_for_the_rest(viewer, conn, relay):
    eid = create(viewer, kind="training", title="CALEP Planning Workshop", venue="Hotel Ozamiz",
                 start_date="2026-10-12", end_date="2026-10-14", people=[str(uid(conn, "viewer@test.local"))])
    assert draft(viewer, eid, "concept_note").status_code == 303
    call = relay.calls[0]
    f, blocks = call["fields"], call["blocks"]
    assert call["template_key"] == "concept_note" and call["title"] == "Concept Note - CALEP Planning Workshop"
    assert f["title"] == "CALEP Planning Workshop" and f["venue"] == "Hotel Ozamiz" and "October 12-14, 2026" in f["date_duration"]
    assert f["participant_count"] == "1" and f["budget"] == ad.BLANK and f["noted_by_name"] == ad.BLANK
    assert blocks["participants"][0].startswith("1. ")
    for key in ("background", "objectives", "outputs", "methodology"):          # theirs to write: a prompt, never invented text
        assert blocks[key] and any("[" in line for line in blocks[key]), key
    days = call["rows"]["program"]
    assert days["marker"] == "pd_day" and [r["pd_day"] for r in days["data"]] == [
        "Day 1 \u2013 October 12, 2026", "Day 2 \u2013 October 13, 2026", "Day 3 \u2013 October 14, 2026"]
    assert all(r["pd_am"] == "" and r["pd_pm"] == "" for r in days["data"])      # the program itself is theirs to write


def test_a_concept_note_with_no_venue_or_people_still_reads_properly(viewer, conn, relay):
    eid = create(viewer, kind="training", title="CALEP Planning Workshop", venue="")
    draft(viewer, eid, "concept_note")
    call = relay.calls[0]
    assert call["fields"]["venue"] == "To be determined"
    assert call["blocks"]["participants"] == ["[List who takes part, by group, and how many.]"] or call["blocks"]["participants"][0].startswith("1. ")


def test_a_program_flow_has_a_heading_and_two_empty_rows_for_each_day(viewer, conn, relay):
    eid = create(viewer, kind="training", title="CALEP Planning Workshop", start_date="2026-10-12", end_date="2026-10-13")
    assert draft(viewer, eid, "program_flow").status_code == 303
    call = relay.calls[0]
    assert call["template_key"] == "program_flow" and call["fields"] == {"title": "CALEP Planning Workshop"}
    flow = call["rows"]["flow"]
    assert flow["marker"] == "pf_time" and len(flow["data"]) == 6
    assert [r["pf_time"] for r in flow["data"] if r["pf_time"]] == ["Day 1 \u2013 October 12, 2026", "Day 2 \u2013 October 13, 2026"]
    assert all(set(r) == {"pf_time", "pf_topic", "pf_person"} for r in flow["data"])


def build_templates():
    out = subprocess.run(["node", "tests/js/activity_templates_stub.js", "apps_script/activity_templates.gs",
                          "apps_script/activity_logos.gs"], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("key", ["dpo", "invitation", "concept_note", "program_flow"])
def test_every_template_has_the_letterhead_logos_and_address_footer(key):
    built = build_templates()[key]
    assert [i.split()[2] for i in built["images"]] == ["image/png", "image/png"]
    assert built["footer"] is True


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
@pytest.mark.parametrize("key, over", [
    ("dpo", {"kind": "travel"}), ("invitation", {"audience": "bureau"}),
    ("concept_note", {"kind": "training", "start_date": "2026-10-12", "end_date": "2026-10-13"}),
    ("program_flow", {"kind": "training", "start_date": "2026-10-12", "end_date": "2026-10-13"})])
def test_every_placeholder_in_a_template_is_one_the_app_fills(viewer, conn, relay, key, over):
    """Runs the template builders against a fake Docs API (the real one only runs in Google), then checks the
    placeholders each writes against what a draft sends, so a template and the app cannot drift apart."""
    built = build_templates()[key]
    assert built["missing"] == [] and set(built["expect"]) <= set(built["found"])      # it writes everything it promises
    eid = create(viewer, title="CALEP Field Visit", people=[str(uid(conn, "viewer@test.local"))], **over)
    draft(viewer, eid, key)
    call = relay.calls[0]
    filled = set(call["fields"]) | set(call["blocks"]) | {r["marker"] for r in call["rows"].values()} | {
        k for r in call["rows"].values() for d in r["data"] for k in d}
    unfilled = set(built["found"]) - filled
    assert unfilled == set(), f"in the {key} template but never filled by the app: {sorted(unfilled)}"


def test_the_embedded_logos_are_small_transparent_pngs():
    import base64
    import re
    import struct
    src = open("apps_script/activity_logos.gs", encoding="utf-8").read()
    for name in ("LEFT", "RIGHT"):
        text = re.search(r"AT_LOGO_%s_B64 = \[(.*?)\]\.join" % name, src, re.S).group(1)
        data = base64.b64decode("".join(re.findall(r"'([^']+)'", text)))
        size = [int(n) for n in re.search(r"AT_LOGO_%s_SIZE = \[(\d+), (\d+)\]" % name, src).groups()]
        assert data[:8] == b"\x89PNG\r\n\x1a\n" and len(data) < 60_000
        assert list(struct.unpack(">II", data[16:24])) == size                         # the stated size is the real one
        assert data[25] in (3, 6)                                                       # palette or RGBA, so transparency is kept
