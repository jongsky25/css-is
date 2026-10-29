"""Documents an activity needs (Spot Feedback #136): the suggestion, the owner's choice, the Google Doc draft."""
from __future__ import annotations
import json
import shutil
import subprocess
from urllib.parse import unquote, urlencode

import pytest

import activity_docs as ad
import storage as st
from test_calendar_entry_pages import conn, create, uid, FORM  # noqa: F401  (shared calendar fixtures)
import gdocs_relay as gr
import ratelimit
from test_travel_generate import Recorder, relay  # noqa: F401


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
                 start_date="2026-10-12", end_date="2026-10-16",
                 people=[str(uid(conn, "viewer@test.local")), str(uid(conn, "encoder@test.local"))])
    st.set_setting(conn, "travel.sig.head_name", "Dr. Ana Reyes"); st.set_setting(conn, "travel.sig.head_title", "Director IV")
    assert draft(viewer, eid, "dpo").status_code == 303
    call = relay.calls[0]
    f = call["fields"]
    assert call["template_key"] == "dpo"
    # the number, date and funding source are never guessed
    assert f["dpo_no"] == ad.BLANK and f["dpo_date"] == ad.BLANK
    # the funding source is cited (spot feedback #179); the template adds " funds."
    assert f["funding_source"] == "BLHSD - Local Health Systems Development Assistance"
    assert f["dpo_year"] == "2026"
    assert f["subject"].startswith("Authority for Select") and "CALEP Field Visit" in f["subject"] and "in Cebu City" in f["subject"]
    # spot feedback #170: the layout of the office's sample DPO. BLHSD conducts the activity, so its personnel conduct it.
    assert f["subject"] == ("Authority for Select Bureau of Local Health Systems Development (BLHSD) Personnel to Conduct the "
                            "CALEP Field Visit on October 12-16, 2026, in Cebu City")
    assert f["background"] == ("The DOH, through the Bureau of Local Health Systems Development (BLHSD), will conduct the "
                               "CALEP Field Visit on October 12-16, 2026, in Cebu City.")
    assert f["intro"] == ("Authority is hereby given to the following select BLHSD personnel to conduct the CALEP Field Visit "
                          "on October 12-16, 2026, in Cebu City:")
    assert "CALEP Field Visit" in f["background"] and f["intro"].startswith("Authority is hereby given to the following select")
    assert f["intro"].endswith(":") and "October 12-16, 2026" in f["intro"]
    assert f["head_name"] == "DR. ANA REYES" and f["head_title"] == "Director IV"      # the signatory is printed in capitals
    # the personnel go in as a Name | Position table, and as lines for a template that still has a {{personnel}} line
    table = call["rows"]["personnel"]
    assert table["marker"] == "p_name" and len(table["data"]) == 2 and table["data"][0]["p_name"].startswith("1. ")
    assert set(table["data"][0]) == {"p_name", "p_position"} and "remove" not in table
    assert len(call["blocks"]["personnel"]) == 2 and call["blocks"]["personnel"][0].startswith("1. ")


def test_a_dpo_without_a_venue_leaves_a_blank_for_it(viewer, conn, relay):
    eid = create(viewer, kind="travel", title="CALEP Field Visit", venue="", owner_org_id="")
    draft(viewer, eid, "dpo")
    f = relay.calls[0]["fields"]
    # spot feedback #178: the venue is always named, a blank line to complete when the item has none
    assert f["subject"].startswith("Authority for ") and f"in {ad.BLANK} on October 12, 2026" in f["subject"]
    assert f["intro"].startswith("Authority is hereby given to ") and f["intro"].endswith(".")


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

def test_the_invitation_supports_the_office_memo_and_retains_legacy_request_data(viewer, conn, relay):
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


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_letterhead_and_name_position_tables_fit_between_the_margins():
    """Docs' default is equal columns: the title wrapped and the right-hand logo or the Position column fell off the page."""
    dpo = build_templates()["dpo"]["widths"]
    assert dpo == [100, 268, 100, 234, 234] and sum(dpo[:3]) == 468 and sum(dpo[3:]) == 468


def test_a_draft_says_it_is_shared_without_an_email(viewer, conn, relay):
    """Spot feedback #143/#146: nobody should wonder whether a draft worked, or be mailed for each one."""
    eid = create(viewer, title="CALEP Field Visit", kind="travel", people=[str(uid(conn, "viewer@test.local"))])
    r = draft(viewer, eid, "dpo")
    assert "No email is sent" in unquote(r.headers["location"]).replace("+", " ")
    assert "no email is sent" in entry_page(viewer, eid)


def test_the_relay_shares_without_google_s_notification_email():
    src = open("apps_script/travel_docs.gs", encoding="utf-8").read()
    assert "sendNotificationEmail: false" in src
    assert src.count("addEditor(") == 1 and src.count("addViewer(") == 1          # only the fallback inside shareQuietly_
    assert "shareQuietly_(copy, a, 'writer')" in src and "shareQuietly_(folder, a, 'reader')" in src


def test_positions_are_blank_unless_the_person_asks_for_them(viewer, conn, relay):
    """Spot feedback #154: do not fill in positions on their own."""
    me = uid(conn, "viewer@test.local")
    conn.execute("UPDATE admin_user SET designation=? WHERE id=?", ("Planning Officer III", me)); conn.commit()
    eid = create(viewer, kind="travel", title="CALEP Field Visit", people=[str(me), str(uid(conn, "encoder@test.local"))])
    draft(viewer, eid, "dpo")
    assert relay.calls[0]["rows"]["personnel"]["data"][0]["p_position"] == ""
    viewer.post(f"/calendar/entries/{eid}/documents/dpo/draft", content="positions=1", headers=FORM, follow_redirects=False)
    assert relay.calls[1]["rows"]["personnel"]["data"][0]["p_position"] == "Planning Officer III"


def test_a_template_paragraph_never_inherits_bold_from_the_one_above():
    """Spot feedback #154: Docs copies the previous paragraph's formatting, which made whole documents bold."""
    src = open("apps_script/activity_templates.gs", encoding="utf-8").read()
    builders = src.split("function at_buildDpo_")[1]
    assert "body.appendParagraph(" not in builders and "body.appendTable(" not in builders
    assert "setBold(false)" in src and "img.getWidth()" in src


# ------------------------------------------------ outside activities (spot feedback #155) ---

def outside(viewer, eid, **fields):
    from urllib.parse import urlencode
    return viewer.post(f"/calendar/entries/{eid}/outside", content=urlencode(fields), headers=FORM, follow_redirects=False)


def test_a_dpo_for_an_activity_another_office_runs_keeps_a_broad_first_paragraph(viewer, conn, relay):
    eid = create(viewer, kind="travel", title="CALEP Field Visit", venue="Cebu City", start_date="2026-10-12",
                 end_date="2026-10-16", people=[str(uid(conn, "viewer@test.local")), str(uid(conn, "encoder@test.local"))])
    r = outside(viewer, eid, conducted_by="outside", host="Center for Health Development VII", invited_as="resource_person",
                invitation="  Per\nmemo dated   October 1, 2026, we are requested to  lecture on CALEP. ")
    assert r.status_code == 303 and "ok=" in r.headers["location"]
    assert ad.get_outside(conn, eid) == {"host": "Center for Health Development VII", "invited_as": "resource_person",
                                         "invitation": "Per memo dated October 1, 2026, we are requested to lecture on CALEP.",
                                         "file_url": "", "file_name": ""}
    draft(viewer, eid, "dpo")
    f = relay.calls[0]["fields"]
    # spot feedback #170: the activity, who conducts it and the rationale from the invitation
    assert f["background"] == ("Per memo dated October 1, 2026, we are requested to lecture on CALEP. In support of this, the "
                               "Center for Health Development VII will conduct the CALEP Field Visit on October 12-16, 2026, in Cebu City.")
    assert "to serve as resource person in the CALEP Field Visit" in f["intro"]
    assert f["subject"] == ("Authority for Select Bureau of Local Health Systems Development (BLHSD) Personnel to Serve as "
                            "Resource Person in the CALEP Field Visit on October 12-16, 2026, in Cebu City")
    # spot feedback #160: the signatory unit is always the bureau
    assert f["unit_name"] == "Bureau of Local Health Systems Development"


def test_switching_back_to_blhsd_restores_the_usual_dpo_wording(viewer, conn, relay):
    eid = create(viewer, kind="travel", title="CALEP Field Visit")
    outside(viewer, eid, conducted_by="outside", host="CHD VII", invited_as="attendee")
    outside(viewer, eid, conducted_by="blhsd")
    assert ad.get_outside(conn, eid) is None
    draft(viewer, eid, "dpo")
    assert "CHD VII" not in relay.calls[0]["fields"]["background"]


def test_an_outside_activity_needs_a_host_and_a_known_invitation_type(viewer, conn):
    eid = create(viewer, kind="travel", title="CALEP Field Visit")
    assert "err=" in outside(viewer, eid, conducted_by="outside", host="  ", invited_as="attendee").headers["location"]
    assert "err=" in outside(viewer, eid, conducted_by="outside", host="CHD VII", invited_as="boss").headers["location"]
    assert "err=" in outside(viewer, eid, conducted_by="maybe").headers["location"]
    assert ad.get_outside(conn, eid) is None
    assert "Who conducts this activity?" in entry_page(viewer, eid)


# ------------------------------------- the uploaded invitation (spot feedback #156) ---

PDF = b"%PDF-1.4 invitation"
UP = {"Content-Type": "application/octet-stream", "X-Filename": "CHD%20VII%20letter.pdf"}
LETTER = {"readable": True, "host": "Center for Health Development VII", "invited_as": "resource_person",
          "key_lines": "CHD VII invites BLHSD to lecture on CALEP on October 12, 2026 in Cebu City. Please send one speaker.",
          "note": "Check the date."}


class UploadRelay(Recorder):
    def __init__(self):
        super().__init__()
        self.uploads = []
        self.trashed = []
        self.trash_ok = True
        self.result = gr.RelayResult(True, {"id": "F1", "url": "https://drive.google.com/file/d/F1/view", "name": "n.pdf",
                                            "folder_url": "https://drive.google.com/drive/folders/FOLDER"})

    def upload_file(self, **kw):
        self.uploads.append(kw)
        return self.result

    def trash_file(self, file_id):
        self.trashed.append(file_id)
        return gr.RelayResult(self.trash_ok)


@pytest.fixture()
def up_relay(monkeypatch, conn):
    r = UploadRelay()
    monkeypatch.setenv(gr.ENV_URL, "https://script.google.com/macros/s/x/exec"); monkeypatch.setenv(gr.ENV_SECRET, "s" * 40)
    monkeypatch.setattr(gr, "get_relay", lambda: r)
    ratelimit._HITS.clear()
    st.set_setting(conn, "travel.relay_version", "2"); conn.commit()
    yield r
    st.set_setting(conn, "travel.relay_version", "0"); conn.commit()


def letter_up(viewer, eid, body=PDF, headers=None):
    return viewer.post(f"/calendar/entries/{eid}/outside/upload", content=body, headers={**UP, **(headers or {})})


def test_a_letter_is_kept_in_drive_read_once_and_only_offered_back(viewer, conn, up_relay, monkeypatch):
    from test_travel_scan import ai_on
    seen = ai_on(conn, monkeypatch, LETTER)
    eid = create(viewer, kind="travel", title="CALEP Field Visit")
    outside(viewer, eid, conducted_by="outside", host="CHD VII", invited_as="attendee")
    r = letter_up(viewer, eid)
    j = r.json()
    assert r.status_code == 200 and j["ok"] and j["reading"]["host"] == "Center for Health Development VII"
    assert j["reading"]["invited_as"] == "resource_person" and j["url"] == "https://drive.google.com/file/d/F1/view"
    assert len(up_relay.uploads) == 1 and up_relay.uploads[0]["folder_key"] == f"act-{eid}" and up_relay.uploads[0]["data"] == PDF
    # kept: the link and name only. The reading is a suggestion: nothing in the saved details changed.
    got = ad.get_outside(conn, eid)
    assert got["file_url"] == j["url"] and got["file_name"] == "CHD VII letter.pdf" and got["host"] == "CHD VII"
    assert got["invitation"] == "" and got["invited_as"] == "attendee"
    assert "Remove the link to the letter" in entry_page(viewer, eid)


def test_a_letter_the_ai_cannot_read_is_still_kept(viewer, conn, up_relay, monkeypatch):
    from test_travel_scan import ai_on
    ai_on(conn, monkeypatch, {"readable": False, "host": "", "invited_as": "unknown", "key_lines": "", "note": ""})
    eid = create(viewer, kind="travel", title="CALEP Field Visit")
    outside(viewer, eid, conducted_by="outside", host="CHD VII", invited_as="attendee")
    j = letter_up(viewer, eid).json()
    assert j["ok"] and j["reading"]["readable"] is False and ad.get_outside(conn, eid)["file_url"]


def test_with_ai_off_the_letter_is_kept_and_the_person_is_told(viewer, conn, up_relay, monkeypatch):
    monkeypatch.delenv("CSS_GEMINI_API_KEY", raising=False)
    eid = create(viewer, kind="travel", title="CALEP Field Visit")
    outside(viewer, eid, conducted_by="outside", host="CHD VII", invited_as="attendee")
    j = letter_up(viewer, eid).json()
    assert j["ok"] and j["reading"] is None and j["ai_off"] is True


def test_the_letter_needs_the_other_office_saved_first_and_a_real_file(viewer, conn, up_relay):
    eid = create(viewer, kind="travel", title="CALEP Field Visit")
    assert letter_up(viewer, eid).status_code == 400 and up_relay.uploads == []              # BLHSD: nothing to attach to
    outside(viewer, eid, conducted_by="outside", host="CHD VII", invited_as="attendee")
    assert letter_up(viewer, eid, body=b"not a pdf at all").status_code == 415
    assert letter_up(viewer, eid, body=b"%PDF-" + b"0" * (6 * 1024 * 1024 + 1)).status_code == 413
    assert up_relay.uploads == []


def test_uploading_is_off_until_the_relay_has_the_upload_version(viewer, conn, up_relay):
    st.set_setting(conn, "travel.relay_version", "0"); conn.commit()
    eid = create(viewer, kind="travel", title="CALEP Field Visit")
    outside(viewer, eid, conducted_by="outside", host="CHD VII", invited_as="attendee")
    assert letter_up(viewer, eid).status_code == 503 and "data-invitation-upload" not in entry_page(viewer, eid)


def test_removing_the_link_keeps_the_details_and_the_page_script_loads_only_when_useful(viewer, conn, up_relay, monkeypatch):
    from test_travel_scan import ai_on
    ai_on(conn, monkeypatch, LETTER)
    eid = create(viewer, kind="travel", title="CALEP Field Visit")
    assert "activity_invitation.js" not in entry_page(viewer, eid)                             # BLHSD: no script
    outside(viewer, eid, conducted_by="outside", host="CHD VII", invited_as="attendee", invitation="Please send one speaker.")
    assert "activity_invitation.js" in entry_page(viewer, eid)
    letter_up(viewer, eid)
    r = viewer.post(f"/calendar/entries/{eid}/outside/file/remove", content="", headers=FORM, follow_redirects=False)
    assert r.status_code == 303 and "ok=" in r.headers["location"]
    got = ad.get_outside(conn, eid)
    assert got["file_url"] == "" and got["host"] == "CHD VII" and got["invitation"] == "Please send one speaker."


def test_the_reading_is_cleaned_and_cannot_carry_a_surprise():
    import activity_invitation as ai_inv
    import ai_core
    out = ai_inv.clean({"readable": True, "host": "  CHD  VII ", "invited_as": "unknown", "key_lines": "A workshop.", "note": ""})
    assert out["host"] == "CHD VII" and out["invited_as"] == ""
    for bad in ("garbage", {"readable": True, "host": "", "key_lines": ""},
                {"readable": True, "host": "CHD", "invited_as": "boss", "key_lines": "x" * 900, "note": ""}):
        with pytest.raises(ai_core.AIBadResponse):
            ai_inv.clean(bad)


# ------------------------------------- one person on a DPO (spot feedback #157) ---

def one_person_dpo(viewer, conn, relay, **over):
    eid = create(viewer, kind="travel", title="CALEP Field Visit", venue="Cebu City", start_date="2026-10-12",
                 end_date="2026-10-16", people=[str(uid(conn, "viewer@test.local"))], **over)
    return eid, relay


def test_a_dpo_for_one_person_names_them_and_has_no_list(viewer, conn, relay):
    conn.execute("UPDATE admin_user SET designation=? WHERE id=?",
                 ("Planning Officer III", uid(conn, "viewer@test.local"))); conn.commit()
    eid, _ = one_person_dpo(viewer, conn, relay)
    viewer.post(f"/calendar/entries/{eid}/documents/dpo/draft", content="positions=1", headers=FORM, follow_redirects=False)
    f, rows = relay.calls[0]["fields"], relay.calls[0]["rows"]
    who = "viewer@test.local, Planning Officer III of the Bureau of Local Health Systems Development (BLHSD)"
    assert f["subject"] == f"Authority for {who} to Attend as Participant in the CALEP Field Visit in Cebu City on October 12-16, 2026"
    assert f["intro"] == f"Authority is hereby given to {who} to attend as Participant in the CALEP Field Visit in Cebu City on October 12-16, 2026."
    assert rows["personnel"]["remove"] is True and relay.calls[0]["blocks"]["personnel"] == [""]
    assert "Select" not in f["subject"] and "following" not in f["intro"]


def test_the_designation_is_left_blank_unless_asked_for(viewer, conn, relay):
    conn.execute("UPDATE admin_user SET designation=? WHERE id=?", ("Planning Officer III", uid(conn, "viewer@test.local"))); conn.commit()
    eid, _ = one_person_dpo(viewer, conn, relay)
    draft(viewer, eid, "dpo")
    f = relay.calls[0]["fields"]
    assert ad.BLANK in f["subject"] and "Planning Officer III" not in f["subject"] and ad.BLANK in f["intro"]


def test_an_invited_resource_person_attends_as_a_resource_speaker(viewer, conn, relay):
    eid, _ = one_person_dpo(viewer, conn, relay)
    outside(viewer, eid, conducted_by="outside", host="CHD VII", invited_as="resource_person")
    draft(viewer, eid, "dpo")
    f = relay.calls[0]["fields"]
    assert "to Attend as Resource Speaker in the CALEP Field Visit" in f["subject"] and "attend as Resource Speaker" in f["intro"]
    outside(viewer, eid, conducted_by="outside", host="CHD VII", invited_as="attendee")
    draft(viewer, eid, "dpo")
    assert "to Attend as Participant in the" in relay.calls[1]["fields"]["subject"]


def test_the_relay_can_drop_a_table_it_was_told_to_remove():
    src = open("apps_script/travel_docs.gs", encoding="utf-8").read()
    assert "if (spec.remove)" in src and "parent.removeChild(table)" in src


# ------------------------------- the real header and the file-copy page (spot feedback #157/#158) ---

def file_copy():
    out = subprocess.run(["node", "tests/js/file_copy_harness.js"], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    return json.loads(out.stdout)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_letterhead_is_built_into_the_real_header_of_every_template():
    for key, built in build_templates().items():
        assert built["header"] is True and built["bodyLetterhead"] is False, key
        assert [i.split()[2] for i in built["images"]] == ["image/png", "image/png"] and built["footer"] is True


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_file_copy_page_has_its_own_empty_header_and_footer_and_the_routing_tables():
    ok = file_copy()["ok"]
    assert ok["status"] == "ok"
    names = [c if isinstance(c, str) else next(iter(c)) for c in ok["calls"]]
    # find the mark, start a new section there, give THAT section an empty header and footer, then clear the mark
    assert names == ["get", "insertSectionBreak", "get", "createHeader", "createFooter", "updateSectionStyle", "replaceAllText"]
    assert ok["calls"][1]["insertSectionBreak"]["sectionType"] == "NEXT_PAGE"
    assert ok["calls"][3]["createHeader"]["type"] == "DEFAULT" and "sectionBreakLocation" in ok["calls"][3]["createHeader"]
    assert ok["calls"][4]["createFooter"]["sectionBreakLocation"] == ok["calls"][3]["createHeader"]["sectionBreakLocation"]
    kids = ok["children"]
    original = kids[:4]
    copy = kids[5:9]                                              # after the mark paragraph (index 4), the same four elements
    assert [(c["type"], c.get("text"), c.get("cells")) for c in copy] == [(c["type"], c.get("text"), c.get("cells")) for c in original]
    tables = [c["cells"] for c in kids[9:] if c["type"] == "TABLE"]
    assert tables == [[["", "BLHSD"], ["Initials", ""], ["Date", ""]],
                      [["Keywords", ""], ["Related issuances, laws, directives", ""]]]
    assert kids[4]["text"] == ""                                   # the mark is cleared from the order


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_without_the_docs_service_the_order_is_left_alone_and_a_failure_does_not_lose_it():
    out = file_copy()
    assert out["off"]["status"] == "docs_service_off" and len(out["off"]["children"]) == 4 and out["off"]["calls"] == []
    assert out["fail"]["status"] == "failed"                       # the order exists; the caller is told why there is no copy page


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_index_finders_read_a_docs_document_correctly():
    p = file_copy()["pure"]
    assert p == {"oneBreak": -1, "twoBreaks": 3, "missing": -1, "found": 4, "empty": -1, "emptyBreak": -1}


def test_dpo_and_invitation_ask_for_their_own_file_copy_boxes(viewer, conn, relay):
    eid = create(viewer, kind="travel", title="CALEP Field Visit", audience="bureau", people=[str(uid(conn, "viewer@test.local"))])
    draft(viewer, eid, "dpo"); draft(viewer, eid, "invitation")
    assert relay.calls[0].get("extras") == {"file_copy": True}
    assert relay.calls[1]["extras"]["file_copy"] is True
    assert relay.calls[1]["extras"]["boxes"] == ["slip"]


def test_the_relay_client_sends_extras_only_when_asked_for(monkeypatch):
    sent = []
    monkeypatch.setattr(gr, "call", lambda action, **kw: sent.append((action, kw)) or gr.RelayResult(True, {}))
    gr.Relay().generate_doc(request_id="r", template_key="dpo", folder_key="f", title="t")
    gr.Relay().generate_doc(request_id="r", template_key="dpo", folder_key="f", title="t", extras={"file_copy": True})
    assert "extras" not in sent[0][1] and sent[1][1]["extras"] == {"file_copy": True}


@pytest.mark.parametrize("extras, words", [("docs_service_off", "Google Docs service is not switched on"),
                                           ("failed", "could not be added this time"), ("ok", None), (None, None)])
def test_the_person_is_told_when_the_order_was_made_without_its_extra_page(viewer, conn, relay, monkeypatch, extras, words):
    eid = create(viewer, kind="travel", title="CALEP Field Visit", people=[str(uid(conn, "viewer@test.local"))])
    original = relay.generate_doc

    def with_extras(**kw):
        res = original(**kw)
        if extras:
            res.data["extras"] = extras
        return res
    monkeypatch.setattr(relay, "generate_doc", with_extras)
    r = draft(viewer, eid, "dpo")
    note = unquote(r.headers["location"]).replace("+", " ")
    assert "ok=" in note
    assert (words in note) if words else ("extra file-copy page" not in note)


# ------------------------------------------------ who signs (spot feedback #157) ---

def signatory(viewer, conn, relay, monkeypatch, director, **setting):
    for k in ("head_name", "head_title"):
        st.set_setting(conn, f"travel.sig.{k}", setting.get(k, ""))
    conn.commit()
    monkeypatch.setattr(st, "org_seat_holder", lambda c, rank, **kw: director if rank == 3 else None)
    eid = create(viewer, kind="travel", title="CALEP Field Visit", audience="bureau",
                 people=[str(uid(conn, "viewer@test.local"))])
    draft(viewer, eid, "dpo")
    return relay.calls[-1]["fields"]


def test_with_no_head_set_the_dpo_is_signed_by_the_directors_in_the_directory(viewer, conn, relay, monkeypatch):
    f = signatory(viewer, conn, relay, monkeypatch, ("Dr. Maria Santos", "Director IV"))
    assert f["head_name"] == "DR. MARIA SANTOS" and f["head_title"] == "Director IV"


def test_a_head_set_under_travel_filing_settings_wins_over_the_directory(viewer, conn, relay, monkeypatch):
    f = signatory(viewer, conn, relay, monkeypatch, ("Dr. Maria Santos", "Director IV"),
                  head_name="Juan Alfonso Perez IV, MD, MBA, MPM", head_title="OIC-Director IV")
    assert f["head_name"] == "JUAN ALFONSO PEREZ IV, MD, MBA, MPM" and f["head_title"] == "OIC-Director IV"


def test_with_neither_the_signatory_is_left_blank(viewer, conn, relay, monkeypatch):
    f = signatory(viewer, conn, relay, monkeypatch, None, head_title="OIC-Director")
    assert f["head_name"] == "" and f["head_title"] == "OIC-Director"


def test_the_settings_page_says_the_certifying_officer_is_only_a_fallback(admin):
    page = admin.get("/admin/travel").text
    assert "Certifying officer, fallback" in page and "depends on the division" in page
    assert "used only when the directory has no division head" in page
    assert "Leave the name blank to use the Director from the directory" in page


# ----------------------------------------------------------------- "DPO cites" (spot feedback #170) ---

def cites(client, eid, text):
    return client.post(f"/calendar/entries/{eid}/dpo-cites", content=urlencode({"dpo_cites": text}), headers=FORM,
                       follow_redirects=False)


RA = ("Republic Act No. 7883, or the Barangay Health Workers' Benefits and Incentives Act of 1995, provides for the "
      "training and continuing education of BHWs.")


def test_dpo_cites_open_the_first_paragraph_of_a_bureau_run_activity(viewer, conn, relay):
    eid = create(viewer, kind="travel", title="CALEP Field Visit", venue="Cebu City", start_date="2026-10-12",
                 end_date="2026-10-16", people=[str(uid(conn, "viewer@test.local")), str(uid(conn, "encoder@test.local"))])
    r = cites(viewer, eid, "  " + RA.replace(", or", ",\n or") + "  ")
    assert r.status_code == 303 and "ok=" in r.headers["location"] and ad.get_dpo_cites(conn, eid) == RA
    draft(viewer, eid, "dpo")
    assert relay.calls[0]["fields"]["background"] == (
        RA + " In support of this, the DOH, through the Bureau of Local Health Systems Development (BLHSD), will conduct "
        "the CALEP Field Visit on October 12-16, 2026, in Cebu City.")
    assert 'name="dpo_cites"' in viewer.get(f"/calendar/entries/{eid}").text and "DPO cites" in viewer.get(f"/calendar/entries/{eid}").text


def test_dpo_cites_win_over_the_invitation_lines_and_clearing_them_brings_the_invitation_back(viewer, conn, relay):
    eid = create(viewer, kind="travel", title="CALEP Field Visit", start_date="2026-10-12", end_date="2026-10-12",
                 people=[str(uid(conn, "viewer@test.local")), str(uid(conn, "encoder@test.local"))])
    outside(viewer, eid, conducted_by="outside", host="CHD VII", invited_as="attendee", invitation="Per memo of October 1.")
    cites(viewer, eid, "Per DM 2026-0412.")
    draft(viewer, eid, "dpo")
    assert relay.calls[-1]["fields"]["background"].startswith("Per DM 2026-0412. In support of this, the CHD VII will conduct")
    cites(viewer, eid, "   ")                                                      # empty clears it
    assert ad.get_dpo_cites(conn, eid) == ""
    draft(viewer, eid, "dpo")
    assert relay.calls[-1]["fields"]["background"].startswith("Per memo of October 1. In support of this")


def test_the_conducting_sentence_is_skipped_when_the_invitation_lines_already_name_the_host(viewer, conn, relay):
    eid = create(viewer, kind="travel", title="Update on Health Promotion", start_date="2026-10-20", end_date="2026-10-20",
                 people=[str(uid(conn, "viewer@test.local")), str(uid(conn, "encoder@test.local"))])
    outside(viewer, eid, conducted_by="outside", host="METRO MANILA center for health development",
            invited_as="resource_person", invitation="The Metro Manila Center For Health Development will conduct the Update.")
    draft(viewer, eid, "dpo")
    assert relay.calls[-1]["fields"]["background"] == "The Metro Manila Center For Health Development will conduct the Update."
    outside(viewer, eid, conducted_by="outside", host="CHD VII", invited_as="resource_person", invitation="Per memo of October 1.")
    draft(viewer, eid, "dpo")
    assert relay.calls[-1]["fields"]["background"].startswith("Per memo of October 1. In support of this, the CHD VII will conduct")


def test_without_any_citation_the_first_paragraph_only_says_who_conducts_it(viewer, conn, relay):
    eid = create(viewer, kind="travel", title="CALEP Field Visit", start_date="2026-10-12", end_date="2026-10-12",
                 people=[str(uid(conn, "viewer@test.local")), str(uid(conn, "encoder@test.local"))])
    draft(viewer, eid, "dpo")
    assert relay.calls[0]["fields"]["background"] == (
        "The DOH, through the Bureau of Local Health Systems Development (BLHSD), will conduct the CALEP Field Visit on October 12, 2026, in __________.")


def test_dpo_cites_cannot_be_set_for_an_entry_the_person_cannot_see(viewer, conn):
    private = st.cal_create(conn, "CALEP Private", "2026-10-12", kind="travel", audience="people",
                            people=[uid(conn, "admin@test.local")])
    conn.commit()
    assert cites(viewer, private, "x").status_code == 404 and ad.get_dpo_cites(conn, private) == ""


def test_a_typed_designation_is_written_and_a_funding_cited(viewer, conn, relay):
    a, b = uid(conn, "viewer@test.local"), uid(conn, "encoder@test.local")
    eid = create(viewer, kind="travel", title="CALEP Field Visit", venue="Cebu City", people=[str(a), str(b)])
    r = viewer.post(f"/calendar/entries/{eid}/documents/dpo/draft", data={f"designation_{a}": "Nurse III"}, follow_redirects=False)
    assert r.status_code == 303
    data = relay.calls[0]["rows"]["personnel"]["data"]
    assert data[0]["p_position"] == "Nurse III" and data[1]["p_position"] == ""
    assert relay.calls[0]["rows"]["personnel"]["fit"] is True


def test_a_meeting_can_draft_minutes(viewer, conn, relay):
    eid = create(viewer, kind="meeting", title="Planning Meeting")
    assert draft(viewer, eid, "minutes").status_code == 303
    call = relay.calls[0]
    assert call["template_key"] == "minutes" and call["fields"]["title"] == "Planning Meeting"
    assert "actions" in call["rows"]


# ---- venue from the invitation, the file copy's reviewer and suggestions, the notice of meeting (spot feedback #184-#192) ---

@pytest.mark.parametrize("text, venue", [
    ("The meeting is on October 20 at the Manila Grand Opera Hotel. Please confirm.", "Manila Grand Opera Hotel"),
    ("Venue: Manila Grand Opera Hotel, Manila", "Manila Grand Opera Hotel, Manila"),
    ("the venue is the Hotel Ozamiz; lunch is provided", "Hotel Ozamiz"),
    ("we are requested to lecture on CALEP", ""), ("", "")])
def test_the_venue_is_read_from_the_invitation_words(text, venue):
    assert ad.venue_from_text(text) == venue


def test_a_dpo_names_the_venue_of_the_invitation_when_the_item_has_none(viewer, conn, relay):
    eid = create(viewer, kind="travel", title="BHW Training", venue="", start_date="2026-10-20")
    outside(viewer, eid, conducted_by="outside", host="CHD NCR", invited_as="attendee",
            invitation="Training of BHWs on October 20, 2026 at the Manila Grand Opera Hotel.")
    draft(viewer, eid, "dpo")
    f = relay.calls[0]["fields"]
    assert "in Manila Grand Opera Hotel" in f["subject"] + f["intro"] and f"in {ad.BLANK}" not in f["subject"]
    assert f["venue"] == "Manila Grand Opera Hotel"
    assert "Manila Grand Opera Hotel" in f["background"]


def test_the_items_own_venue_wins_over_the_invitation(viewer, conn, relay):
    eid = create(viewer, kind="travel", title="BHW Training", venue="Cebu City")
    outside(viewer, eid, conducted_by="outside", host="CHD NCR", invited_as="attendee",
            invitation="Training at the Manila Grand Opera Hotel.")
    draft(viewer, eid, "dpo")
    assert "in Cebu City" in relay.calls[0]["fields"]["intro"]


def test_keywords_and_issuances_are_read_from_the_invitation():
    kw, laws = ad.suggest_file_copy("Orientation of Barangay Health Workers (BHWs) per RA 7883 and Administrative Order No. 2020-0019")
    assert kw == "Barangay Health Workers (BHWs)" and laws == "AO 2020-0019, RA 7883"
    assert ad.suggest_file_copy("BHWs only") == ("Barangay Health Workers (BHWs)", "RA 7883")
    assert ad.suggest_file_copy("a plain trip", "") == ("", "")


@pytest.mark.parametrize("section, name", [("S4", "MARIA LOURDES GAJITOS, MD, MPH"), ("S5", "MARIA LOURDES GAJITOS, MD, MPH"),
                                           ("S1", "KATHRINE JOYCE FLORES, MD, MPM"), ("S3", "KATHRINE JOYCE FLORES, MD, MPM"),
                                           ("ADMIN", "")])
def test_the_reviewer_follows_the_travellers_section(conn, monkeypatch, section, name):
    monkeypatch.setattr(st, "get_user_profile", lambda c, u: {"org_path": f"BLHSD/X/{section}"})
    got = ad.file_copy_reviewer(conn, {}, [1])
    assert got[0] == name and (got[1] == "Medical Officer V" if name else got == ("", ""))


def test_travellers_of_different_reviewers_leave_the_reviewer_blank(conn, monkeypatch):
    paths = {1: "BLHSD/HSMED/S4", 2: "BLHSD/HSDD/S1"}
    monkeypatch.setattr(st, "get_user_profile", lambda c, u: {"org_path": paths[u]})
    assert ad.file_copy_reviewer(conn, {}, [1, 2]) == ("", "")
    assert ad.file_copy_reviewer(conn, {}, [1])[0].startswith("MARIA")


def test_a_dpo_sends_the_reviewer_and_suggestions_to_the_file_copy(viewer, conn, relay, monkeypatch):
    real = st.get_user_profile
    monkeypatch.setattr(st, "get_user_profile", lambda c, u: {**(real(c, u) or {}), "org_path": "BLHSD/HSMED/S4"})
    eid = create(viewer, kind="travel", title="BHW Orientation", people=[str(uid(conn, "viewer@test.local"))])
    outside(viewer, eid, conducted_by="outside", host="CHD NCR", invited_as="attendee", invitation="BHWs under RA 7883.")
    draft(viewer, eid, "dpo")
    assert relay.calls[0]["extras"] == {"file_copy": True,
                                        "reviewer": {"name": "MARIA LOURDES GAJITOS, MD, MPH", "title": "Medical Officer V"},
                                        "keywords": "Barangay Health Workers (BHWs)", "issuances": "RA 7883"}


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_file_copy_boxes_carry_the_reviewer_centred_and_the_suggestions():
    t = file_copy()["tables"]
    assert t["none"] == {"slip": [["", "BLHSD"], ["Initials", ""], ["Date", ""]],
                         "keys": [["Keywords", ""], ["Related issuances, laws, directives", ""]]}
    assert t["full"]["slip"][1] == ["Initials", "KATHRINE JOYCE FLORES, MD, MPM\nMedical Officer V"]
    assert t["full"]["keys"] == [["Keywords", "BHWs"], ["Related issuances, laws, directives", "RA 7883"]]


def test_a_meeting_suggests_a_notice_and_minutes_and_nothing_else_does():
    sug = ad.suggest(entry(kind="meeting"))
    assert sug["notice_of_meeting"][0] and sug["minutes"][0]
    assert not ad.suggest(entry(kind="training"))["notice_of_meeting"][0]


def test_a_notice_of_meeting_is_drafted_with_the_details_and_the_invited(viewer, conn, relay):
    eid = create(viewer, kind="meeting", title="CALEP Planning", venue="Room 2", audience="bureau",
                 people=[str(uid(conn, "viewer@test.local"))], meeting_url="https://meet.google.com/abc-defg-hij")
    ad.set_visitors(conn, eid, "Dr. Cruz, CHD VII\n\nMs. Reyes, OSEC", "viewer@test.local")
    r = draft(viewer, eid, "notice_of_meeting")
    assert r.status_code == 303 and "ok=" in r.headers["location"]
    call = relay.calls[0]
    assert call["template_key"] == "notice_of_meeting" and call["title"] == "Notice of Meeting - CALEP Planning"
    assert call["fields"]["venue"] == "Room 2" and call["fields"]["meeting_link"] == "https://meet.google.com/abc-defg-hij"
    invited = call["blocks"]["invited"]
    assert invited[-2:] == ["2. Dr. Cruz, CHD VII", "3. Ms. Reyes, OSEC"] and len(invited) == 3
    assert "Notice of meeting" in entry_page(viewer, eid)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_file_copy_can_select_only_the_initials_box_without_changing_the_dpo_default():
    result = file_copy()
    assert result["both"] == result["ok"]
    slip = result["slip"]
    assert slip["status"] == "ok"
    assert [child["cells"] for child in slip["children"][9:] if child["type"] == "TABLE"] == [
        [["", "BLHSD"], ["Initials", ""], ["Date", ""]]]
    assert result["empty"]["status"] == "ok"
    assert not [child for child in result["empty"]["children"][9:] if child["type"] == "TABLE"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_office_memo_placeholders_have_payload_values_and_no_source_names(viewer, conn, relay, monkeypatch):
    result = subprocess.run(["node", "tests/js/office_templates_harness.js"], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    expected = set(json.loads(result.stdout)["built"]["expect"])
    st.set_setting(conn, "travel.sig.head_name", "Configured Head")
    st.set_setting(conn, "travel.sig.head_title", "Configured Director")
    monkeypatch.setattr(ad, "file_copy_reviewer", lambda *args: ("Configured Reviewer", "Reviewer Title"))
    eid = create(viewer, audience="bureau", title="Office Workshop", venue="Venue", note="PRIVATE MUST NOT COPY")
    draft(viewer, eid, "invitation")
    call = relay.calls[0]
    assert expected <= set(call["fields"]) | set(call["blocks"])
    assert call["fields"]["from_name"] == "CONFIGURED HEAD"
    assert call["fields"]["unit_name"] == ad.SIGNATORY_UNIT
    assert call["extras"]["addressees"] == [
        {"for_name": ad.BLANK, "for_title": ad.BLANK, "for_office": ad.BLANK}]
    assert len(call["blocks"]["representatives"]) == len(ad.ASSISTANCE)
    assert all(request in " ".join(call["blocks"]["representatives"]) for area, request in ad.ASSISTANCE)
    assert "[Rationale" in call["blocks"]["rationale"][0]
    assert call["extras"]["reviewer"] == {"name": "Configured Reviewer", "title": "Reviewer Title"}
    assert "PRIVATE MUST NOT COPY" not in json.dumps(call)
    assert all(word not in json.dumps(call).upper() for word in ("PEREZ", "SAYSON-GARCIA", "GAJITOS"))


def test_file_copy_disables_inherited_first_page_variants():
    style = file_copy()["ok"]["calls"][5]["updateSectionStyle"]
    assert style["sectionStyle"] == {"useFirstPageHeaderFooter": False}
    assert style["fields"] == "useFirstPageHeaderFooter"
    assert style["range"]["startIndex"] < style["range"]["endIndex"]


def test_notice_invitee_rows_use_directory_offices_and_keep_free_text_visitors(viewer, conn, relay):
    org = st.add_org_unit(conn, "Meeting Office", "section", "BLHSD/MEETING")
    rp = st.add_rp(conn, "Directory Person", True, org_unit_id=org)
    conn.execute("UPDATE admin_user SET rp_id=? WHERE id=?", (rp, uid(conn, "viewer@test.local")))
    st.set_setting(conn, "travel.sig.head_name", "Configured Head")
    st.set_setting(conn, "travel.sig.head_title", "Configured Title")
    conn.commit()
    eid = create(viewer, kind="meeting", title="Office Planning", venue="Room", people=[str(uid(conn, "viewer@test.local"))],
                 start_time="09:00", end_time="14:30", note="PRIVATE NOTE")
    ad.set_visitors(conn, eid, "Visitor, MD, External Office\nOther Visitor", "viewer@test.local")
    draft(viewer, eid, "notice_of_meeting")
    call = relay.calls[0]
    assert call["rows"]["invitees"] == {"marker": "inv_name", "data": [
        {"inv_name": "Directory Person", "inv_office": "Meeting Office"},
        {"inv_name": "Visitor, MD, External Office", "inv_office": ""},
        {"inv_name": "Other Visitor", "inv_office": ""}]}
    assert call["fields"]["meeting_time"] == "9:00 AM to 2:30 PM"
    assert call["fields"]["subject"] == "Office Planning"
    assert call["fields"]["head_name"] == "CONFIGURED HEAD" and call["fields"]["head_title"] == "Configured Title"
    assert call["fields"]["unit_name"] == ad.SIGNATORY_UNIT
    assert call["extras"] == {"file_copy": True, "boxes": []}
    assert "PRIVATE NOTE" not in json.dumps(call) and "PEREZ" not in json.dumps(call)


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_notice_template_and_payload_agree_with_unknown_invitees_left_blank(viewer, conn, relay):
    result = subprocess.run(["node", "tests/js/office_templates_harness.js"], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    expected = set(json.loads(result.stdout)["notice"]["expect"])
    eid = create(viewer, kind="meeting", title="No Invitees", people=[], start_time="", end_time="", time_note="After lunch")
    draft(viewer, eid, "notice_of_meeting")
    call = relay.calls[0]
    filled = set(call["fields"]) | set(call["blocks"]) | {
        key for row in call["rows"]["invitees"]["data"] for key in row}
    assert expected <= filled
    assert call["rows"]["invitees"]["data"] == [{"inv_name": ad.BLANK, "inv_office": ""}]
    assert call["fields"]["meeting_time"] == "After lunch"
    assert call["blocks"]["agenda"] == ["[First agenda item]", "[Second agenda item]"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_converted_concept_and_program_placeholders_have_payload_values(viewer, conn, relay):
    result = subprocess.run(["node", "tests/js/office_templates_harness.js"], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    templates = json.loads(result.stdout)["concepts"]
    st.set_setting(conn, "travel.sig.head_name", "Configured Head")
    st.set_setting(conn, "travel.sig.head_title", "Director")
    eid = create(viewer, kind="training", title="Current Activity", people=[str(uid(conn, "viewer@test.local"))],
                 start_date="2026-10-12", end_date="2026-10-13")
    for key in ("concept_note", "program_flow"):
        draft(viewer, eid, key)
        call = relay.calls[-1]
        filled = set(call["fields"]) | set(call["blocks"]) | {
            key for spec in call["rows"].values() for row in spec["data"] for key in row}
        assert set(templates[key]["expect"]) <= filled
        assert "PEREZ" not in json.dumps(call) and "SAYSON-GARCIA" not in json.dumps(call)
    concept, program = relay.calls
    assert concept["rows"]["participants"]["data"] == [{"pt_group": "viewer@test.local", "pt_count": "1"}]
    assert concept["fields"]["participant_count"] == "1"
    assert len(concept["rows"]["program"]["data"]) == 2
    assert all(row["pd_text"] == "[Activities for this day]" for row in concept["rows"]["program"]["data"])
    assert concept["fields"]["recommended_name"] == "CONFIGURED HEAD"
    assert concept["fields"]["approved_name"] == ad.BLANK
    assert concept["fields"]["approved_title"] == concept["fields"]["approved_unit"] == ad.BLANK
    assert len(program["rows"]["flow"]["data"]) == 6
    assert all(not row["pf_topic"] and not row["pf_person"] for row in program["rows"]["flow"]["data"])


def test_concept_supervisor_comes_from_own_directory_seat_and_unknown_counts_stay_blank(conn, monkeypatch):
    profiles = {10: {"person_name": "Drafter", "org_path": "BLHSD/S1", "rp_id": 123}}
    monkeypatch.setattr(st, "get_user_profile", lambda c, uid: profiles.get(uid, {}))
    seats = []
    def supervisor(c, rank, **kw):
        seats.append((rank, kw))
        return "Directory Supervisor", "Section Chief"
    monkeypatch.setattr(st, "org_seat_holder", supervisor)
    st.set_setting(conn, "travel.sig.head_name", "Configured Head")
    payload = ad.payload(conn, {"id": 1, "title": "Activity", "start_date": "2026-10-12", "people": []},
                         "concept_note", {"id": 10, "username": "drafter@test.local"})
    assert payload.fields["noted_by_name"] == "Directory Supervisor"
    assert seats == [(1, {"org_path": "BLHSD/S1", "exclude_rp_id": 123})]
    assert payload.fields["participant_count"] == ad.BLANK
    assert payload.rows["participants"]["data"] == [{"pt_group": "[Participant group]", "pt_count": ad.BLANK}]
    assert payload.fields["approved_name"] == ad.BLANK


def test_external_letter_suggestion_uses_explicit_outside_context():
    assert not ad.suggest(entry())["invitation_external"][0]
    assert ad.suggest(entry(), outside={"host": "Named Office"})["invitation_external"][0]
    assert ad.suggest(entry(), visitors="Named Partner")["invitation_external"][0]
    assert not ad.suggest(entry(), visitors="  None  ")["invitation_external"][0]
    assert not ad.suggest(entry(note="An outside partner is mentioned privately"))["invitation_external"][0]


def test_external_letter_card_and_needed_choice_use_existing_routes(viewer, conn):
    eid = create(viewer, audience="bureau")
    assert "Invitation (external letter)" in entry_page(viewer, eid)
    outside(viewer, eid, conducted_by="outside", host="Named Office", invited_as="attendee")
    item = next(row for row in ad.state_for(conn, {"id": eid, **entry()}) if row["key"] == "invitation_external")
    assert item["suggested"] and item["needed"]
    r = viewer.post(f"/calendar/entries/{eid}/documents/invitation_external/needed",
                    content=urlencode({"needed": "no"}), headers=FORM, follow_redirects=False)
    assert r.status_code == 303 and "ok=" in r.headers["location"]
    assert ad.get_rows(conn, eid)["invitation_external"]["needed"] == 0
    viewer.post(f"/calendar/entries/{eid}/documents/invitation_external/needed",
                content=urlencode({"needed": "auto"}), headers=FORM)
    assert ad.get_rows(conn, eid)["invitation_external"]["needed"] is None


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_external_letter_payload_matches_template_without_guessing_addressee(viewer, conn, relay, monkeypatch):
    st.set_setting(conn, "travel.sig.head_name", "Configured Head")
    st.set_setting(conn, "travel.sig.head_title", "Configured Director")
    monkeypatch.setattr(ad, "file_copy_reviewer", lambda *args: ("Configured Reviewer", "Reviewer Title"))
    eid = create(viewer, audience="bureau", title="Current Workshop", venue="Room 2", note="PRIVATE NOTE",
                 meeting_url="https://meet.google.com/abc-defg-hij")
    outside(viewer, eid, conducted_by="outside", host="Named Agency", invited_as="attendee", invitation="Pasted names must not become addressees")
    r = draft(viewer, eid, "invitation_external")
    assert r.status_code == 303 and "ok=" in r.headers["location"]
    call = relay.calls[0]
    assert call["template_key"] == "invitation_external" and call["folder_key"] == f"act-{eid}"
    fields = call["fields"]
    assert fields["addressee_agency"] == "Named Agency"
    for key in ("addressee_name", "addressee_title", "addressee_address", "salutation_name"):
        assert fields[key] == ad.BLANK
    assert fields["head_name"] == "CONFIGURED HEAD" and fields["head_title"] == "Configured Director"
    assert call["extras"] == {"file_copy": True, "boxes": ["slip"],
        "reviewer": {"name": "Configured Reviewer", "title": "Reviewer Title"}}
    assert "Current Workshop" in " ".join(call["blocks"]["letter_details"])
    assert "https://meet.google.com/abc-defg-hij" in " ".join(call["blocks"]["letter_details"])
    assert "viewer@test.local" in call["blocks"]["contact_details"][0]
    assert "[Explain" in call["blocks"]["activity_purpose"][0]
    assert "PRIVATE NOTE" not in json.dumps(call) and "Pasted names" not in json.dumps(call)
    result = subprocess.run(["node", "tests/js/office_templates_harness.js"], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    expected = set(json.loads(result.stdout)["letter"]["expect"])
    assert expected <= set(fields) | set(call["blocks"])
    assert ad.get_rows(conn, eid)["invitation_external"]["doc_state"] == "done"
    assert "Google Doc" in entry_page(viewer, eid)


def test_external_letter_without_host_has_blank_agency_and_clear_setup_failure(viewer, conn, relay):
    eid = create(viewer, audience="bureau")
    relay.fail["invitation_external"] = "template_not_set"
    draft(viewer, eid, "invitation_external")
    assert relay.calls[0]["fields"]["addressee_agency"] == ad.BLANK
    row = ad.get_rows(conn, eid)["invitation_external"]
    assert row["doc_state"] == "failed" and "external invitation template" in row["note"]


def test_executive_briefer_is_manual_and_uses_existing_choice_routes(viewer, conn):
    assert not ad.suggest(entry())["executive_briefer"][0]
    eid = create(viewer, audience="bureau")
    assert "Executive briefer" in entry_page(viewer, eid)
    response = viewer.post(f"/calendar/entries/{eid}/documents/executive_briefer/needed",
                           content=urlencode({"needed": "yes"}), headers=FORM, follow_redirects=False)
    assert response.status_code == 303 and "ok=" in response.headers["location"]
    assert ad.get_rows(conn, eid)["executive_briefer"]["needed"] == 1
    viewer.post(f"/calendar/entries/{eid}/documents/executive_briefer/needed",
                content=urlencode({"needed": "auto"}), headers=FORM)
    assert ad.get_rows(conn, eid)["executive_briefer"]["needed"] is None


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_executive_briefer_payload_agrees_with_template_and_uses_known_activity_data(viewer, conn, relay, monkeypatch):
    st.set_setting(conn, "travel.sig.head_name", "Configured Head")
    st.set_setting(conn, "travel.sig.head_title", "Director")
    monkeypatch.setattr(ad, "file_copy_reviewer", lambda *args: ("Section Reviewer", "Reviewer Title"))
    eid = create(viewer, kind="training", title="Current Workshop", venue="Room", people=[str(uid(conn, "viewer@test.local"))],
                 start_date="2026-10-12", end_date="2026-10-13", note="PRIVATE NOTE")
    ad.set_visitors(conn, eid, "Visitor, MD, Partner Office", "viewer@test.local")
    ad.set_dpo_cites(conn, eid, "AO 2026-0012", "viewer@test.local")
    response = draft(viewer, eid, "executive_briefer")
    assert response.status_code == 303 and "ok=" in response.headers["location"]
    call = relay.calls[0]
    assert call["template_key"] == "executive_briefer" and call["title"] == "Executive Briefer - Current Workshop"
    fields, blocks = call["fields"], call["blocks"]
    assert fields["subject"] == "Current Workshop" and fields["prepared_by"] == "viewer@test.local"
    assert fields["prepared_title"] == ""
    assert fields["noted_by_name"] == "Section Reviewer" and fields["noted_by_title"] == "Reviewer Title"
    assert fields["head_name"] == "CONFIGURED HEAD" and fields["head_title"] == "Director"
    assert fields["approved_unit"] == ad.SIGNATORY_UNIT
    assert blocks["requested_action"][0].startswith("[") and blocks["background"][0].startswith("[")
    assert blocks["outputs"] == ad.CONCEPT_PROMPTS["outputs"]
    assert blocks["participants"] == ["1. viewer@test.local", "2. Visitor, MD, Partner Office"]
    assert blocks["date_venue_references"] == ["Date: October 12-13, 2026", "Venue: Room", "References: AO 2026-0012"]
    assert not call.get("extras") and not call["rows"]
    assert "PRIVATE NOTE" not in json.dumps(call) and "PEREZ" not in json.dumps(call)
    result = subprocess.run(["node", "tests/js/office_templates_harness.js"], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0, result.stderr
    expected = set(json.loads(result.stdout)["briefer"]["expect"])
    assert expected <= set(fields) | set(blocks)
    assert ad.get_rows(conn, eid)["executive_briefer"]["doc_state"] == "done"


def test_briefer_leaves_unknown_signers_and_references_blank(conn, monkeypatch):
    monkeypatch.setattr(ad, "head_of_office", lambda *args: ("", ""))
    monkeypatch.setattr(ad, "file_copy_reviewer", lambda *args: ("", ""))
    monkeypatch.setattr(st, "get_user_profile", lambda *args: {"person_name": "Known Drafter", "designation": "Known Title"})
    payload = ad.payload(conn, {"id": 1, "title": "Activity", "start_date": "2026-10-12", "people": []},
                         "executive_briefer", {"id": 10, "username": "drafter@test.local"}, positions=True)
    assert payload.fields["prepared_title"] == "Known Title"
    for key in ("head_name", "head_title", "noted_by_name", "noted_by_title"):
        assert payload.fields[key] == ad.BLANK
    assert payload.blocks["participants"] == ["[List participants and key stakeholders.]"]
    assert payload.blocks["date_venue_references"][-1].startswith("References: [")
    assert not payload.extras


def test_missing_briefer_template_has_an_actionable_setup_message(viewer, conn, relay):
    eid = create(viewer, audience="bureau")
    relay.fail["executive_briefer"] = "template_not_set"
    draft(viewer, eid, "executive_briefer")
    saved = ad.get_rows(conn, eid)["executive_briefer"]
    assert saved["doc_state"] == "failed" and "executive briefer template" in saved["note"]
