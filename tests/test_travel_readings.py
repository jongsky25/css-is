"""Appendix A and B drafted from what was read off the uploads (Spot Feedback #122, #123, #125): readings are kept on the
server, turned into itinerary entries and Certificate of Travel Completed answers, the Director and the filer's division
head fill the signers, and the filing page says when everything is in."""
from __future__ import annotations
import json
import re
from datetime import timedelta

import pytest

import storage as st
import travel
import travel_docs
import travel_readings as trd
import tzutil as tz
from test_travel_relay import conn, env, fake, mk, on, row, up, ai_clean, jpost, post   # noqa: F401  (fixtures + helpers)
from test_travel_scan import GOOD, JPEG, ai_on

START, END = "2026-10-05", "2026-10-07"


def blank_rows():
    return [travel_docs.blank_row(d) for d in ("2026-10-05", "2026-10-06", "2026-10-07")]


def rd(i, code, **kw):
    base = {"id": i, "item_code": code, "doc": "receipt", "kind": code, "amount": 1000.0, "currency": "PHP", "day": "2026-10-05",
            "origin": "", "destination": "", "vendor": "", "reference": "", "dep_time": "", "arr_time": "",
            "date_from": None, "date_to": None}
    return {**base, **kw}


# ------------------------------------------------------------------ the draft itself (pure) ---

def test_a_ticket_fills_the_blank_row_of_its_own_date():
    rows = trd.draft_rows(blank_rows(), [rd(1, "plane_ticket", amount=4521.5, origin="Manila", destination="Cebu",
                                           vendor="Cebu Pacific", dep_time="06:10", arr_time="07:40")])
    first = rows[0]
    assert (first["mode"], first["allowance"], first["from"], first["to"], first["dep"], first["arr"]) == \
        ("plane", 4521.5, "Manila", "Cebu", "06:10", "07:40")
    assert first["rid"] == 1 and "e-ticket" in first["src"].lower() and "Cebu Pacific" in first["src"]
    assert len(rows) == 3 and rows[1]["mode"] == "none"


def test_a_second_ride_on_a_day_gets_its_own_entry_without_a_second_per_diem():
    base = blank_rows()
    base[0]["per_diem"], base[0]["day_kind"] = 500, "full"
    rows = trd.draft_rows(base, [rd(1, "plane_ticket", amount=4000.0), rd(2, "taxi_receipt", amount=350.0, origin="Airport", destination="Hotel")])
    assert len(rows) == 4 and [r["date"] for r in rows[:2]] == ["2026-10-05", "2026-10-05"]
    taxi = rows[1]
    assert (taxi["mode"], taxi["receipt"], taxi["allowance"], taxi["per_diem"], taxi["day_kind"]) == ("taxi", "receipt", 350.0, 0, "")
    assert rows[0]["per_diem"] == 500                                          # the day's per diem stays on the first entry


def test_ride_hailing_and_boat_modes_and_an_undated_reading_goes_last():
    rows = trd.draft_rows(blank_rows(), [rd(1, "ridehail_receipt", amount=300.0, day="2026-10-06"),
                                         rd(2, "boat_bus_ticket", amount=900.0, vendor="Montenegro Shipping", day=""),
                                         rd(3, "boat_bus_ticket", amount=200.0, vendor="Victory Liner", day="2026-10-07")])
    assert rows[1]["mode"] == "tnvs" and rows[1]["receipt"] == "receipt"
    assert rows[2]["mode"] == "bus"
    assert rows[-1]["mode"] == "boat" and rows[-1]["date"] == "" and rows[-1]["allowance"] == 900.0


def test_a_boarding_pass_is_the_same_flight_as_the_ticket_but_stands_in_when_there_is_none():
    both = trd.draft_rows(blank_rows(), [rd(1, "plane_ticket", amount=4000.0), rd(2, "boarding_pass", amount=4000.0)])
    assert sum(1 for r in both if r["mode"] == "plane") == 1
    alone = trd.draft_rows(blank_rows(), [rd(2, "boarding_pass", amount=4000.0)])
    assert alone[0]["mode"] == "plane" and alone[0]["allowance"] == 4000.0


def test_things_that_are_not_rides_are_not_drafted_as_rides():
    rows = trd.draft_rows(blank_rows(), [rd(1, "terminal_fee", amount=100.0), rd(2, "lodging_bill", amount=5000.0),
                                         rd(3, "refund_or", amount=800.0), rd(4, "cert_appearance", doc="appearance", amount=None)])
    assert all(r["mode"] == "none" and not r["allowance"] for r in rows)


def test_nothing_read_means_the_rows_are_untouched():
    assert trd.draft_rows(blank_rows(), []) == blank_rows()


FILING = {"act_start": START, "act_end": END, "kind": "liquidation"}


def cert(i, a, b):
    return rd(i, "cert_appearance", doc="appearance", date_from=a, date_to=b, amount=None, currency=None)


def test_the_certificate_dates_suggest_how_the_travel_went():
    assert trd.completion_defaults(FILING, [cert(1, START, END)]) == {"strictness": "strict"}
    short = trd.completion_defaults(FILING, [cert(1, START, "2026-10-06")])
    assert short["strictness"] == "cut" and "October 5, 2026 to October 6, 2026" in short["explanation"] and "October 5, 2026 to October 7, 2026" in short["explanation"]
    assert trd.completion_defaults(FILING, [cert(1, "2026-10-04", END)])["strictness"] == "extended"
    assert trd.completion_defaults(FILING, [cert(1, "2026-10-06", "2026-10-09")])["strictness"] == "other"
    assert trd.completion_defaults(FILING, [cert(1, START, "2026-10-05"), cert(2, "2026-10-06", END)]) == {"strictness": "strict"}
    assert trd.completion_defaults(FILING, []) == {}


def test_the_refund_receipt_fills_the_refund_answers_for_a_liquidation_only():
    refund = rd(1, "refund_or", amount=800.0, reference="OR-123", day="2026-10-09")
    assert trd.completion_defaults(FILING, [refund]) == {"refund_amount": "800.00", "refund_or_no": "OR-123", "refund_or_date": "2026-10-09"}
    assert trd.completion_defaults({**FILING, "kind": "reimbursement"}, [refund]) == {}


# ------------------------------------------------------------------ what is kept ---

def test_only_readable_peso_readings_are_kept_once(conn):
    ref = mk_filing(conn)
    fid = travel.get_by_ref(conn, ref)["id"]
    good = {**GOOD, "readable": True}
    assert trd.save(conn, fid, "plane_ticket", "receipt", good) is True
    assert trd.save(conn, fid, "plane_ticket", "receipt", good) is False                 # the same reading twice
    assert trd.save(conn, fid, "plane_ticket", "receipt", {**good, "currency": "USD"}) is False
    assert trd.save(conn, fid, "plane_ticket", "receipt", {**good, "readable": False}) is False
    assert trd.save(conn, fid, "plane_ticket", "receipt", {**good, "amount": 0}) is False
    assert trd.save(conn, fid, "cert_appearance", "appearance", {"readable": True, "date_from": START, "date_to": ""}) is True
    got = trd.for_filing(conn, fid)
    assert [(r["item_code"], r["amount"]) for r in got if r["doc"] == "receipt"] == [("plane_ticket", 4521.5)]
    assert [(r["date_from"], r["date_to"]) for r in got if r["doc"] == "appearance"] == [(START, START)]


def mk_filing(conn, answers='{"flew": 1, "taxi_receipt": 1}'):
    """A filing row straight in the database, so these tests need no browser session."""
    uid = conn.execute("SELECT id FROM admin_user WHERE username='tt-reader@test.local'").fetchone()
    uid = uid[0] if uid else st.create_admin_user(conn, "tt-reader@test.local", "x", "y", "viewer")
    n = conn.execute("SELECT COUNT(*) FROM travel_filing").fetchone()[0] + 900
    ref = f"TF-TEST-{n}"
    conn.execute("DELETE FROM travel_filing WHERE ref_code=?", (ref,))
    conn.execute("INSERT INTO travel_filing(ref_code, user_id, kind, source_kind, act_title, act_start, act_end, answers_json, "
                 "opened_at, updated_at) VALUES (?,?,?,?,?,?,?,?,?,?)",
                 (ref, uid, "liquidation", "blank", "READTEST", START, END, answers, tz.now_iso(), tz.now_iso()))
    conn.commit()
    return ref


@pytest.fixture(autouse=True)
def _clean_test_filings(conn):
    yield
    conn.execute("DELETE FROM travel_filing WHERE ref_code LIKE 'TF-TEST-%'")
    conn.execute("DELETE FROM admin_user WHERE username='tt-reader@test.local'")
    conn.commit()


def test_removing_the_files_of_a_row_forgets_what_was_read_from_them(conn):
    ref = mk_filing(conn)
    filing = travel.get_by_ref(conn, ref)
    trd.save(conn, filing["id"], "plane_ticket", "receipt", {**GOOD, "readable": True})
    trd.save(conn, filing["id"], "taxi_receipt", "receipt", {**GOOD, "readable": True, "amount": 200.0})
    travel.sync_items(conn, filing)
    travel.clear_upload(conn, filing, "plane_ticket")
    assert [r["item_code"] for r in trd.for_filing(conn, filing["id"])] == ["taxi_receipt"]
    travel.save_item(conn, filing, "taxi_receipt", drive_url="https://drive.google.com/drive/folders/abc")      # a pasted link replaces the files
    assert trd.for_filing(conn, filing["id"]) == []


def test_marking_a_row_not_applicable_and_the_retention_purge_forget_readings(conn):
    ref = mk_filing(conn)
    filing = travel.get_by_ref(conn, ref)
    travel.sync_items(conn, filing)
    trd.save(conn, filing["id"], "taxi_receipt", "receipt", {**GOOD, "readable": True})
    travel.save_item(conn, filing, "taxi_receipt", na=True)
    assert trd.for_filing(conn, filing["id"]) == []
    trd.save(conn, filing["id"], "taxi_receipt", "receipt", {**GOOD, "readable": True})
    conn.execute("UPDATE travel_filing SET status='submitted', submitted_at='2020-01-01T00:00:00' WHERE id=?", (filing["id"],))
    conn.commit()
    assert travel.purge_filings(conn, relay=_NoFiles()) >= 1
    assert trd.for_filing(conn, filing["id"]) == []


class _NoFiles:
    def trash_file(self, file_id):
        import gdocs_relay as gr
        return gr.RelayResult(True, data={})


# ------------------------------------------------------------------ the whole flow ---

def prep_data(client, ref):
    html = client.get(f"/travel/f/{ref}/prepare").text
    return json.loads(re.search(r'<script[^>]*id="prep-data"[^>]*>(.*?)</script>', html, re.S).group(1).replace("<\\/", "</"))


def test_an_uploaded_ticket_is_drafted_into_appendix_a_on_the_prepare_page(viewer, conn, fake, on, ai_clean, monkeypatch):
    ref = mk(viewer, flew="1")
    first_day = (tz.today_local() - timedelta(days=10)).isoformat()
    ai_on(conn, monkeypatch, {**GOOD, "date": first_day, "depart_time": "06:10", "arrive_time": "07:40"})
    assert up(viewer, ref, code="plane_ticket", body=JPEG).json()["ok"]
    data = prep_data(viewer, ref)
    plane = [r for r in data["rows"] if r["mode"] == "plane"]
    assert len(plane) == 1 and plane[0]["date"] == first_day and plane[0]["allowance"] == 4521.5
    assert (plane[0]["from"], plane[0]["to"], plane[0]["dep"], plane[0]["arr"]) == ("Manila", "Cebu", "06:10", "07:40")
    assert "Cebu Pacific" in plane[0]["src"]
    # the reading is kept apart from the checklist row, and the form posted back ignores the bookkeeping keys
    cols = " ".join(str(c) for c in conn.execute("SELECT * FROM travel_item").fetchall())
    assert "4521" not in cols and "Cebu" not in cols
    assert conn.execute("SELECT COUNT(*) FROM travel_reading WHERE amount=4521.5").fetchone()[0] == 1
    norm = travel_docs.normalize({"rows": data["rows"]})
    assert "rid" not in norm["rows"][0] and "src" not in norm["rows"][0]


def test_the_dpo_date_is_added_from_the_uploaded_dpo_when_the_filing_has_none(viewer, conn, fake, on, ai_clean, monkeypatch):
    ref = mk(viewer)
    assert travel.get_by_ref(conn, ref)["dpo_date"] is None
    dpo = {"readable": True, "dpo_no": "2026-100", "dpo_date": "2026-09-20", "travel_start": "2000-01-01", "travel_end": "2099-12-31",
           "funding_stated": True, "funding": "GAA MOOE", "note": ""}
    ai_on(conn, monkeypatch, dpo)
    j = up(viewer, ref, code="dpo").json()
    assert j["ok"] and j["fill"] is None and any("DPO date" in c and "added" in c for c in j["checks"])
    assert travel.get_by_ref(conn, ref)["dpo_date"] == "2026-09-20"
    # a different number is a conflict for the person to settle, so nothing is changed and the button is offered
    conn.execute("UPDATE travel_filing SET dpo_date=NULL WHERE ref_code=?", (ref,)); conn.commit()
    ai_on(conn, monkeypatch, {**dpo, "dpo_no": "2026-999"})
    j = up(viewer, ref, code="dpo", body=JPEG).json()
    assert j["fill"] and travel.get_by_ref(conn, ref)["dpo_date"] is None


def test_the_certificate_dates_and_refund_receipt_draft_appendix_b(viewer, conn, fake, on, ai_clean, monkeypatch):
    ref = mk(viewer, refund="1", cert_of_appearance_available="1")
    start = (tz.today_local() - timedelta(days=10)).isoformat()
    cert_to = (tz.today_local() - timedelta(days=9)).isoformat()
    ai_on(conn, monkeypatch, {"readable": True, "date_from": start, "date_to": cert_to, "note": ""})
    assert up(viewer, ref, code="cert_appearance").json()["ok"]
    ai_on(conn, monkeypatch, {**GOOD, "kind": "official_receipt", "amount": 800.0, "reference": "OR-77", "date": start})
    assert up(viewer, ref, code="refund_or", body=JPEG).json()["ok"]
    texts = prep_data(viewer, ref)["texts"]
    assert texts["strictness"] == "cut" and "Certificate of Appearance covers" in texts["explanation"]
    assert (texts["refund_amount"], texts["refund_or_no"], texts["refund_or_date"]) == ("800.00", "OR-77", start)


# ------------------------------------------------------------------ the people who sign ---

@pytest.fixture()
def office(conn):
    """!TT: a bureau with a Director, one division with a Division Chief, and a section in it with one staff member."""
    for t in ("resource_person",):
        conn.execute("DELETE FROM resource_person WHERE name LIKE '!TT %'")
    conn.execute("DELETE FROM org_unit WHERE path LIKE 'TTB%'")
    ids = {}
    for key, name, level, path in (("bureau", "TT Bureau", "bureau", "TTB"), ("division", "TT Division", "division", "TTB/Div"),
                                   ("section", "TT Section", "section", "TTB/Div/Sec"), ("division2", "TT Other Division", "division", "TTB/Div2")):
        ids[key] = conn.execute("INSERT INTO org_unit(name, short_name, level, path) VALUES (?,?,?,?)", (name, name, level, path)).lastrowid
    def person(name, desig, unit, position=None):
        return conn.execute("INSERT INTO resource_person(name, is_internal, org_unit_id, designation, position) VALUES (?,?,?,?,?)",
                            (name, 1, ids[unit], desig, position)).lastrowid
    # as the real directory records them: a chief's position is their plantilla title, their designation "Division Chief"
    out = {"director": person("!TT Director", "OIC-Director IV", "bureau"),
           "chief": person("!TT Division Chief", "Division Chief", "division", "Medical Officer V"),
           "chief2": person("!TT Other Chief", "Division Chief", "division2", "Medical Officer V"), "staff": person("!TT Staff", "Medical Officer III", "section")}
    for k in ("staff", "chief"):
        out[k + "_uid"] = st.create_admin_user(conn, f"tt-{k}@test.local", "x", "y", "viewer", rp_id=out[k])
    conn.commit()
    yield out
    conn.execute("DELETE FROM admin_user WHERE username LIKE 'tt-%@test.local'")
    conn.execute("DELETE FROM resource_person WHERE name LIKE '!TT %'")
    conn.execute("DELETE FROM org_unit WHERE path LIKE 'TTB%'")
    conn.commit()


BLANK_SIG = {"head_name": "", "head_title": "OIC-Director", "certifier_name": "", "certifier_title": "Medical Officer V", "station": "BLHSD"}


def test_the_director_and_the_filers_division_head_sign_when_the_settings_are_blank(conn, office):
    sig = travel.directory_signers(conn, office["staff_uid"], BLANK_SIG)
    assert (sig["head_name"], sig["head_title"]) == ("!TT Director", "OIC-Director IV")      # the setting's "OIC-Director" is not paired with another name
    assert (sig["certifier_name"], sig["certifier_title"]) == ("!TT Division Chief", "Medical Officer V")
    assert sig["station"] == "BLHSD"


def test_a_named_head_in_the_settings_wins_but_the_division_head_still_comes_from_the_directory(conn, office):
    sig = travel.directory_signers(conn, office["staff_uid"], {**BLANK_SIG, "head_name": "Dr. Acting", "head_title": "OIC-Director",
                                                              "certifier_name": "Dr. Set", "certifier_title": "Medical Officer V"})
    assert (sig["head_name"], sig["head_title"]) == ("Dr. Acting", "OIC-Director")
    assert sig["certifier_name"] == "!TT Division Chief"


def test_the_filer_is_never_their_own_certifying_officer(conn, office):
    sig = travel.directory_signers(conn, office["chief_uid"], {**BLANK_SIG, "certifier_name": "Dr. Set"})
    assert sig["certifier_name"] == "Dr. Set"                                                 # the division chief files: the setting is the fallback


def test_a_filer_outside_the_directory_gets_the_settings(conn):
    sig = travel.directory_signers(conn, 987654, {**BLANK_SIG, "certifier_name": "Dr. Set"})
    assert sig["certifier_name"] == "Dr. Set"


# ------------------------------------------------------------------ the prompt ---

def item(code, handling, requirement="required", state="missing", **kw):
    return {"code": code, "label": code, "handling": handling, "requirement": requirement, "state": state, **kw}


def test_the_prompt_waits_until_every_required_upload_is_in():
    items = [item("dpo", "upload", state="present", drive_url="u"), item("plane_ticket", "upload"), item("appendix_a", "generate"),
             item("appendix_b", "generate")]
    assert travel.forms_ready_to_draft(items) == []
    items[1].update(state="present", drive_url="u")
    assert travel.forms_ready_to_draft(items) == ["appendix_a", "appendix_b"]
    items[1].update(state="na", drive_url=None)
    assert travel.forms_ready_to_draft(items) == ["appendix_a", "appendix_b"]
    items[2].update(doc_url="https://docs.google.com/x")
    assert travel.forms_ready_to_draft(items) == ["appendix_b"]
    items[3].update(doc_url="https://docs.google.com/y")
    assert travel.forms_ready_to_draft(items) == []


def test_fmis_rows_and_optional_rows_do_not_hold_the_prompt_back():
    items = [item("ors", "fmis"), item("jo_clearance", "upload", requirement="optional"), item("appendix_a", "generate")]
    assert travel.forms_ready_to_draft(items) == ["appendix_a"]


def test_the_prepare_page_starts_with_the_director_and_the_filers_division_head(app_mod, conn, office, on):
    from test_wellness import _client_for_id
    staff = _client_for_id(app_mod, office["staff_uid"])
    ref = mk(staff)
    sig = prep_data(staff, ref)["signatories"]
    assert (sig["head_name"], sig["certifier_name"]) == ("!TT Director", "!TT Division Chief")
    assert sig["approver_name"] == "!TT Director" and sig["noted_by_name"] == "!TT Director"           # these follow the head of office
    assert sig["certifier_title"] == "Medical Officer V" and sig["head_title"] == "OIC-Director IV"
    conn.execute("DELETE FROM travel_filing WHERE user_id=?", (office["staff_uid"],)); conn.commit()


# ------------------------------------------------------------------ the cash advance's Appendix A ---

def _ca_and_liquidation(conn, office, appendix_link):
    from datetime import date
    user = {"id": office["staff_uid"], "username": "tt-staff@test.local"}
    today = tz.today_local()
    src = lambda a, b: {"source_kind": "blank", "title": "CARRYTEST", "start": (today + timedelta(days=a)).isoformat(),
                        "end": (today + timedelta(days=b)).isoformat(), "venue": ""}
    ca = travel.create_filing(conn, user, kind="ca", source=src(20, 22), answers={}, role="participant", dpo_no="2026-1", today=today)
    if appendix_link:
        travel.save_item(conn, ca, "appendix_a", drive_url=appendix_link)
    conn.execute("UPDATE travel_filing SET status='submitted', submitted_at=? WHERE id=?", (tz.now_iso(), ca["id"])); conn.commit()
    liq = travel.create_filing(conn, user, kind="liquidation", source=src(-10, -8), answers={}, role="participant", dpo_no="2026-1",
                               ca_filing_id=ca["id"], today=today)
    return ca, liq


def _prev(conn, liq):
    r = conn.execute("SELECT state, drive_url, drive_source, note FROM travel_item WHERE filing_id=? AND item_code='prev_appendix_a'",
                     (liq["id"],)).fetchone()
    return dict(zip(("state", "drive_url", "drive_source", "note"), r))


def test_a_liquidation_takes_the_appendix_a_already_made_for_its_cash_advance(conn, office):
    link = "https://docs.google.com/document/d/CAAPPENDIXA/edit"
    ca, liq = _ca_and_liquidation(conn, office, link)
    got = _prev(conn, liq)
    assert (got["state"], got["drive_url"], got["drive_source"]) == ("present", link, "carried")
    assert ca["ref_code"] in got["note"]
    conn.execute("DELETE FROM travel_filing WHERE act_title='CARRYTEST'"); conn.commit()


def test_a_removed_carried_row_is_not_filled_in_again_and_a_missing_appendix_leaves_the_row_alone(conn, office):
    ca, liq = _ca_and_liquidation(conn, office, "https://docs.google.com/document/d/CAAPPENDIXA/edit")
    travel.save_item(conn, liq, "prev_appendix_a", drive_url="")
    assert _prev(conn, liq)["state"] == "missing" and travel.carry_from_ca(conn, travel.get_filing(conn, liq["id"])) is False
    assert _prev(conn, liq)["state"] == "missing"
    conn.execute("DELETE FROM travel_filing WHERE act_title='CARRYTEST'"); conn.commit()
    ca2, liq2 = _ca_and_liquidation(conn, office, None)                      # the cash advance has no Appendix A yet
    assert _prev(conn, liq2)["state"] == "missing" and _prev(conn, liq2)["drive_url"] is None
    conn.execute("DELETE FROM travel_filing WHERE act_title='CARRYTEST'"); conn.commit()
