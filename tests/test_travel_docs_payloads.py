"""Travel document payload builders (T5): what the relay is asked to fill in, per document."""
from __future__ import annotations
import json
import pathlib
import shutil
import subprocess
from datetime import date

import pytest

import storage as st
import travel
import travel_docs as td
import travel_rules as tr

GOLDEN = pathlib.Path(__file__).parent / "golden" / "travel"
CEIL = {("rer", "residence_airport"): 550.0, ("rer", "residence_venue"): 450.0, ("tnvs", "*"): 700.0,
        ("taxi", "*"): 700.0, ("cenrr", "*"): 300.0}
PROFILE = {"person_name": "Juan Dela Cruz", "username": "juan@doh.gov.ph", "designation": "Nurse II",
           "employee_no": "12345", "org_path": "BLHSD/PLANNING"}
SETTINGS = {"head_name": "Dr. Ana Reyes", "head_title": "OIC-Director", "station": "Manila",
            "certifier_name": "Dr. Lito Cruz", "certifier_title": "Medical Officer V"}


def filing(start="2026-09-01", end="2026-09-04", **kw):
    f = {"id": 1, "ref_code": "TF-2609-0001", "kind": "liquidation", "act_title": "Regional Planning Workshop",
         "act_start": start, "act_end": end, "act_venue": "Cebu City", "dpo_no": "2026-123", "dpo_date": "2026-08-20",
         "mc114_format": "none"}
    f.update(kw)
    return f


def row(d, **kw):
    r = {"date": d, "from": "Home", "to": "Airport", "dep": "06:00", "arr": "07:00", "mode": "none",
         "route_type": "", "receipt": "none", "allowance": 0, "per_diem": 0}
    r.update(kw)
    return r


def build(codes, rows, f=None, texts=None, sig=None, mc114="", items=(), kind="liquidation", **kw):
    posted = {"rows": rows, "texts": texts or {}, "signatories": sig or {}, "mc114_text": mc114}
    return td.build_payloads(kind, f or filing(kind=kind), PROFILE, SETTINGS, posted, codes, ceilings=CEIL,
                             items=items, today=date(2026, 9, 10), **kw)


def one(codes, rows, **kw):
    out = build(codes, rows, **kw)
    assert len(out) == 1
    return out[0]


def check_golden(name, payload):
    got = {"item_code": payload.item_code, "template_key": payload.template_key, "title": payload.title,
           "fields": payload.fields, "blocks": payload.blocks, "rows": payload.rows}
    path = GOLDEN / f"{name}.json"
    if not path.exists():
        pytest.fail(f"missing golden file {path}; contents would be:\n{json.dumps(got, indent=2, ensure_ascii=False)}")
    assert got == json.loads(path.read_text())


# ----------------------------------------------------------------- appendix A ---

def test_appendix_a_four_day_trip_grows_one_row_per_day():
    rows = [row(f"2026-09-0{d}", mode="taxi", receipt="receipt", route_type="residence_airport", allowance=250, per_diem=500)
            for d in (1, 2, 3, 4)]
    p = one(["appendix_a"], rows, texts={"purpose": "attend the Regional Planning Workshop"}, kind="ca")
    assert len(p.rows["itinerary"]["data"]) == 4 and p.rows["itinerary"]["marker"] == "r_date"
    assert p.fields["grand_total"] == "3,000"
    assert p.fields["purpose"] == ("To attend the Regional Planning Workshop on September 01-04, 2026 at Cebu City "
                                   "as per DPO No. 2026-123 dated August 20, 2026")
    check_golden("appendix_a_four_day", p)


def test_appendix_a_cross_month_trip_and_empty_rows():
    f = filing("2026-08-30", "2026-09-02", kind="ca")
    p = one(["appendix_a"], [], f=f, kind="ca")
    assert "August 30 - September 02, 2026" in p.fields["purpose"]
    assert p.rows["itinerary"]["data"] == [] and p.fields["grand_total"] == "0"       # the relay keeps one blank row


def test_row_count_is_capped_and_bad_values_never_raise():
    rows = [row("2026-09-01", allowance="abc", per_diem=-5, mode="rocket") for _ in range(100)]
    p = one(["appendix_a"], rows, kind="ca")
    assert len(p.rows["itinerary"]["data"]) == td.MAX_ROWS and p.fields["grand_total"] == "0"
    assert p.rows["itinerary"]["data"][0]["r_mode"] == ""
    assert td.normalize("not a dict")["rows"] == [] and td.normalize({"rows": "x", "texts": 5})["texts"]["strictness"] == "strict"


# ----------------------------------------------------------------- appendix B ---

def test_appendix_b_checks_one_box_lists_evidence_and_appends_the_justification():
    items = [{"code": "plane_ticket", "label": "Plane ticket", "handling": "upload", "state": "present"},
             {"code": "boarding_pass", "label": "Boarding pass", "handling": "upload", "state": "missing"},
             {"code": "fms_routing_slip", "label": "FMIS routing slip", "handling": "fmis", "state": "present"},
             {"code": "travel_report", "label": "Post Travel Report", "handling": "generate", "state": "missing",
              "doc_url": "https://docs.google.com/d/1"}]
    f = filing(mc114_format="appendix_b")
    p = one(["appendix_b"], [], f=f, items=items, texts={"strictness": "cut", "explanation": "Left a day early.\n\nSick."},
            mc114="Because of the schedule.\nIt was necessary.")
    assert p.item_code == "appendix_b" and p.also == ("appendix_a",) and p.template_key == "claim_liq"   # one document, both rows
    assert (p.fields["chk_strict"], p.fields["chk_cut"]) == ("☐", "☒")
    # spot feedback #173: the standing attachments first (the DPO number and date come from the filing), then the other uploads
    assert p.blocks["evidence_list"] == ["1. Department Personnel Order (DPO) No. 2026-123 dated August 20, 2026", "2. Appendix A and B",
                                         "3. Certificate of Appearance", "4. Post Travel Report", "5. Plane ticket"]
    assert p.blocks["explanation"] == ["Left a day early.", "Sick.", "Justification (MC 114):",
                                       "Because of the schedule.", "It was necessary."]
    assert p.fields["date"] == "September 10, 2026" and p.fields["head_name"] == "Dr. Ana Reyes"
    check_golden("claim_liq_cut_short", p)


def test_appendix_b_without_the_justification_format_leaves_it_out():
    p = one(["appendix_b"], [], mc114="ignored text")
    assert p.blocks["explanation"] == []


# ------------------------------------------------- Appendix A and B as one document ---

def test_a_liquidation_makes_appendix_a_and_b_as_one_document_credited_to_both_rows():
    rows = [row("2026-09-01", mode="taxi", receipt="receipt", route_type="residence_airport", allowance=250, per_diem=500)]
    out = build(["appendix_a", "appendix_b", "travel_report"], rows)
    assert [(p.item_code, p.template_key, p.also) for p in out] == [
        ("appendix_a", "claim_liq", ("appendix_b",)), ("travel_report", "travel_report", ())]
    p = out[0]
    assert p.rows["itinerary"]["data"][0]["r_total"] == "750" and p.fields["grand_total"] == "750"      # the itinerary part
    assert p.fields["chk_strict"] == "☒" and "evidence_list" in p.blocks and p.fields["prepared_title"] == "Nurse II"   # the certificate part
    assert p.title == "Appendix A and B - Itinerary and Certificate of Travel Completed - TF-2609-0001"


def test_a_reimbursement_has_its_own_template_and_no_cash_advance_lines():
    p = one(["appendix_a", "appendix_b"], [], kind="reimbursement")
    assert p.template_key == "claim_rei" and "ca_amount" not in p.fields and p.also == ("appendix_b",)


def test_a_cash_advance_keeps_appendix_a_alone():
    p = one(["appendix_a"], [], kind="ca")
    assert (p.template_key, p.also) == ("appendix_a", ()) and "chk_strict" not in p.fields


def test_the_liquidation_itinerary_splits_the_total_into_the_advance_and_the_reimbursement():
    rows = [row("2026-09-01", allowance=1000, per_diem=500), row("2026-09-02", allowance=200, per_diem=0)]
    f = filing(advance_amount=1000.0)
    p = one(["appendix_a"], rows, f=f)
    assert (p.fields["grand_total"], p.fields["ca_amount"], p.fields["reimb_amount"]) == ("1,700", "1,000", "700")
    under = one(["appendix_a"], rows, f=filing(advance_amount=2000.0))
    assert (under.fields["ca_amount"], under.fields["reimb_amount"]) == ("2,000", "–")              # nothing beyond the advance
    unknown = one(["appendix_a"], rows)
    assert (unknown.fields["ca_amount"], unknown.fields["reimb_amount"]) == ("", "")                 # left for the person


def _template_expects():
    """{template key: its expected placeholders} for the three claim forms, read from the Apps Script source."""
    import re
    src = pathlib.Path("apps_script/travel_templates.gs").read_text(encoding="utf-8")
    out = {}
    for key in ("appendix_a", "claim_liq", "claim_rei"):
        m = re.search(r"key: '%s',.*?expect: \[(.*?)\] \}" % key, src, re.S)
        assert m, key
        out[key] = set(re.findall(r"'([a-z0-9_]+)'", m.group(1)))
    return out, src


@pytest.mark.parametrize("kind, key, codes", [("ca", "appendix_a", ["appendix_a"]),
                                              ("liquidation", "claim_liq", ["appendix_a"]),
                                              ("reimbursement", "claim_rei", ["appendix_a"])])
def test_every_placeholder_a_claim_template_expects_is_one_the_app_fills(kind, key, codes):
    """A template and the payload must not drift apart: a placeholder the app never fills would be left blank on the form,
    and a value the app sends that no template has would be lost."""
    expects, src = _template_expects()
    rows = [row("2026-09-01", mode="taxi", receipt="receipt", route_type="residence_airport", allowance=250, per_diem=500)]
    p = one(codes, rows, kind=kind, f=filing(kind=kind, advance_amount=1000.0))
    assert p.template_key == key
    sent = set(p.fields) | set(p.blocks) | {k for spec in p.rows.values() for d in spec["data"] for k in d}
    assert expects[key] <= sent, sorted(expects[key] - sent)
    for name in expects[key]:                                                      # and the builder really writes it
        assert "{{%s}}" % name in src or "'%s'" % name in src, name


# ---------------------------------------------------------------- the others ---

def test_mc114_replaces_the_library_tokens():
    p = one(["mc114_justification"], [], mc114="{{traveler_name}} attended {{activity_title}} on {{dates}} in {{venue}}.")
    assert p.blocks["body"] == ["Juan Dela Cruz attended Regional Planning Workshop on September 01-04, 2026 in Cebu City."]
    assert p.fields["traveler_position"] == "Nurse II" and p.fields["unit"] == "PLANNING"


def test_jo_cert_uses_the_request_phrase_and_citation():
    p = one(["jo_cert"], [], texts={"activities": "Documented the sessions", "obligations": "Submit minutes"})
    assert p.fields["request_phrase"] == "liquidation" and "2025-0202-B" in p.fields["dm_citation"]
    assert p.blocks == {"activities": ["Documented the sessions"], "obligations": ["Submit minutes"]}


def test_travel_report_day_by_day_follows_the_posted_days_or_seeds_from_the_dates():
    p = one(["travel_report"], [], texts={"day_by_day": ["Sept 1: arrived", "Sept 2: sessions"], "overview": "Good trip"})
    assert p.blocks["day_by_day"] == ["Sept 1: arrived", "Sept 2: sessions"] and p.blocks["overview"] == ["Good trip"]
    seeded = one(["travel_report"], [])
    assert seeded.blocks["day_by_day"] == [f"September {d}, 2026:" for d in (1, 2, 3, 4)]
    assert seeded.fields["name_designation"] == "Juan Dela Cruz, Nurse II"


def test_one_cenrr_per_small_unreceipted_ride():
    rows = [row("2026-09-01", mode="public_noreceipt", route_type="residence_airport", allowance=250),
            row("2026-09-02", mode="public_noreceipt", route_type="residence_airport", allowance=300),
            row("2026-09-03", mode="public_noreceipt", route_type="residence_airport", allowance=450),   # RER
            row("2026-09-04", mode="tnvs", receipt="receipt", route_type="residence_airport", allowance=600)]
    docs = build(["cenrr"], rows)
    assert [d.index for d in docs] == [1, 2] and all(d.item_code == "cenrr" for d in docs)
    assert [d.rows["items"]["data"][0]["p_amount"] for d in docs] == ["250", "300"]
    assert [d.fields["total"] for d in docs] == ["250", "300"]
    assert docs[0].fields["employee_no"] == "12345" and docs[0].fields["office"] == "Manila"
    check_golden("cenrr", docs[0])


def test_one_rer_per_ride_with_amount_in_words():
    rows = [row("2026-09-01", mode="public_noreceipt", route_type="residence_airport", allowance=500),
            row("2026-09-04", mode="public_noreceipt", route_type="residence_venue", allowance=450.5, **{"from": "Hotel", "to": "Venue"})]
    docs = build(["rer"], rows)
    assert [d.index for d in docs] == [1, 2] and all(d.item_code == "rer" for d in docs)
    assert docs[0].fields["amount_words"] == "Five Hundred Pesos" and docs[0].fields["amount_figures"] == "500"
    assert docs[1].fields["amount_words"] == "Four Hundred Fifty Pesos and 50/100"
    check_golden("rer_first", docs[0])


def test_no_ride_documents_when_nothing_needs_them():
    rows = [row("2026-09-01", mode="plane", allowance=5000), row("2026-09-02", mode="tnvs", receipt="receipt", route_type="residence_airport", allowance=400)]
    assert build(["cenrr", "rer"], rows) == []
    assert td.ride_answers(rows, CEIL) == {"rides_cenrr": 0, "rides_rer": 0}


def test_ride_answers_tell_the_checklist_what_to_add():
    rows = [row("2026-09-01", mode="public_noreceipt", route_type="residence_airport", allowance=100),
            row("2026-09-02", mode="public_noreceipt", route_type="residence_airport", allowance=551)]
    assert td.ride_answers(rows, CEIL) == {"rides_cenrr": 1, "rides_rer": 1}


def test_codes_not_asked_for_are_not_built():
    assert [p.item_code for p in build(["travel_report", "appendix_a"], [])] == ["appendix_a", "travel_report"]
    assert build(["fms_routing_slip"], []) == []


# ------------------------------------------------------------------ defaults ---

def test_defaults_seed_one_row_and_one_day_per_trip_day(tmp_path):
    c = st.connect(str(tmp_path / "d.db")); st.init_db(c)
    f = filing("2026-12-30", "2027-01-02", mc114_format="separate")
    d = td.defaults(c, f, PROFILE, {"head_name": "Dr. Ana Reyes"})
    assert [r["date"] for r in d["rows"]] == ["2026-12-30", "2026-12-31", "2027-01-01", "2027-01-02"]
    assert d["texts"]["day_by_day"][0] == "December 30, 2026: " and d["signatories"]["head_name"] == "Dr. Ana Reyes"
    assert "Juan Dela Cruz" in d["mc114_text"] and "Regional Planning Workshop" in d["mc114_text"]
    assert d["signatories"]["traveler_title"] == "Nurse II"
    assert td.defaults(c, filing(mc114_format="none"), PROFILE, {})["mc114_text"] == ""
    json.dumps(d, default=str)


def test_defaults_draft_the_report_overview_and_describe_the_days(tmp_path):
    c = st.connect(str(tmp_path / "d.db")); st.init_db(c)
    f = filing("2026-12-30", "2027-01-02", act_venue="Cebu City", dpo_no="123", dpo_date="2026-12-01")
    d = td.defaults(c, f, PROFILE, {})
    assert d["texts"]["overview"] == ("This report covers my travel to attend Regional Planning Workshop on "
                                      f"{td.date_range('2026-12-30', '2027-01-02')} at Cebu City, as per DPO No. 123 dated December 1, 2026.")
    assert [x["iso"] for x in d["days"]] == ["2026-12-30", "2026-12-31", "2027-01-01", "2027-01-02"]
    assert d["days"][0]["label"] == "December 30, 2026"
    assert d["activity"] == {"title": "Regional Planning Workshop", "venue": "Cebu City",
                             "start": "2026-12-30", "end": "2027-01-02"}


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_page_writes_each_report_day_from_the_itinerary():
    rows = [{"date": "2026-10-12", "from": "Quezon City", "to": "Tagaytay", "dep": "06:00", "arr": "08:30", "mode": "tnvs"},
            {"date": "2026-10-14", "from": "Tagaytay", "to": "Quezon City", "dep": "17:00", "arr": "", "mode": "van_doh"},
            {"date": "2026-10-13", "from": "", "to": "", "dep": "", "arr": "", "mode": "none"}]
    act = {"title": "Planning Workshop", "venue": "Tagaytay", "start": "2026-10-12", "end": "2026-10-14"}
    days = ["2026-10-11", "2026-10-12", "2026-10-13", "2026-10-14"]
    script = ("global.window=undefined;const src=require('fs').readFileSync('static/js/travel_prepare.js','utf8');"
              "const g={};new Function('globalThis',src.replace(/\\}\\)\\(typeof window[^\\n]*$/, '})(globalThis);'))(g);"
              f"const rows={json.dumps(rows)},act={json.dumps(act)},m={json.dumps({'tnvs': 'TNVS', 'van_doh': 'DOH van'})};"
              f"console.log(JSON.stringify({json.dumps(days)}.map(d=>g.TravelPrepare.describeDay(rows,d,act,m))));")
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    assert json.loads(out.stdout) == [
        "",                                                                    # before the activity, nothing entered
        "travelled from Quezon City to Tagaytay by TNVS (left 6:00 AM, arrived 8:30 AM); took part in Planning Workshop at Tagaytay",
        "took part in Planning Workshop at Tagaytay",                           # a middle day: the activity alone
        "took part in Planning Workshop at Tagaytay; travelled from Tagaytay to Quezon City by DOH van (left 5:00 PM)"]


@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_page_totals_a_liquidation_against_the_cash_advance():
    rows = [{"mode": "plane", "allowance": 2300.5, "per_diem": 0, "src": "Read from your e-ticket"},
            {"mode": "tnvs", "allowance": 0.1, "per_diem": 1500},
            {"mode": "tnvs", "allowance": 0.2, "per_diem": 0, "src": "Read from a receipt"},
            {"mode": "none", "allowance": 0, "per_diem": 1500}]
    modes = {"plane": "Plane", "tnvs": "TNVS"}
    script = ("global.window=undefined;const src=require('fs').readFileSync('static/js/travel_prepare.js','utf8');"
              "const g={};new Function('globalThis',src.replace(/\\}\\)\\(typeof window[^\\n]*$/, '})(globalThis);'))(g);"
              f"const rows={json.dumps(rows)},m={json.dumps(modes)};"
              "console.log(JSON.stringify([5000,3000,null,'',0].map(a=>g.TravelPrepare.liquidationFigures(rows,a,m))));")
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    refund, over, none, blank, zero = json.loads(out.stdout)
    assert [(l["label"], l["cents"], l["count"], l["fromFiles"]) for l in refund["lines"]] == [
        ("Plane", 230050, 1, 1), ("TNVS", 30, 2, 1), ("Per diem", 300000, 2, 0)]     # 0.1 + 0.2 is exactly 30 centavos
    assert refund["totalCents"] == 530080 and refund["advanceCents"] == 500000 and refund["diffCents"] == -30080
    assert over["diffCents"] == 3000 * 100 - 530080                                    # spent more than the advance
    assert none["advanceCents"] is None and none["diffCents"] is None
    assert blank["advanceCents"] is None                                               # an empty amount is "not on the filing"
    assert zero["advanceCents"] == 0 and zero["diffCents"] == -530080


# --------------------------------------------------- page rules match the server ---

@pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")
def test_the_page_ride_rules_agree_with_the_python_rules():
    cases = [("tnvs", "residence_airport", 700, "receipt"), ("tnvs", "residence_airport", 701, "receipt"),
             ("taxi", "", 300, "receipt"), ("public_noreceipt", "residence_airport", 300, "none"),
             ("public_noreceipt", "residence_airport", 300.01, "none"), ("public_noreceipt", "residence_airport", 551, "none"),
             ("public_noreceipt", "residence_venue", 451, "none"), ("public_noreceipt", "residence_venue", 1000.01, "none"),
             ("public_noreceipt", "unknown", 100, "none"), ("plane", "", 5000, "none"), ("tnvs", "residence_venue", 0, "receipt")]
    flat = [[m, rt, a] for (m, rt), a in CEIL.items()]
    script = ("const {TravelPrepare:T}=require('./static/js/travel_prepare.js');" if False else "") + \
        "global.window=undefined;const src=require('fs').readFileSync('static/js/travel_prepare.js','utf8');" \
        "const g={};new Function('globalThis',src.replace(/\\}\\)\\(typeof window[^\\n]*$/, '})(globalThis);'))(g);" \
        f"const c=g.TravelPrepare.ceilings({json.dumps(flat)});" \
        f"console.log(JSON.stringify({json.dumps(cases)}.map(x=>{{const r=g.TravelPrepare.rideCheck(x[0],x[1],x[2],x[3],c);return [r.kind,r.flags.length]}})));"
    out = subprocess.run(["node", "-e", script], capture_output=True, text=True, timeout=30)
    assert out.returncode == 0, out.stderr
    got = json.loads(out.stdout)
    for case, (kind, nflags) in zip(cases, got):
        res = tr.ride_check(case[0], case[1], case[2], case[3], CEIL)
        assert (res.kind, len(res.flags)) == (kind, nflags), case


def test_designation_confirmed_on_the_prepare_page_is_used_on_every_form():
    rows = [row("2026-09-01", mode="public_noreceipt", route_type="residence_airport", allowance=250),
            row("2026-09-02", mode="public_noreceipt", route_type="residence_airport", allowance=450)]
    docs = build(["cenrr", "rer", "mc114_justification"], rows, sig={"traveler_title": "Senior Health Program Officer"})
    assert [d.fields.get("designation") or d.fields.get("payee_designation") or d.fields.get("traveler_position") for d in docs] \
        == ["Senior Health Program Officer"] * 3
    blank = build(["cenrr"], rows)                                       # nothing typed: the profile's designation
    assert blank[0].fields["designation"] == "Nurse II"


def test_clock_text_never_shows_military_time():
    import travel_docs as td
    assert [td.clock_text(v) for v in ("00:05", "06:00", "12:00", "13:30", "23:59", "", "8:15 AM", "noon")] == \
        ["12:05 AM", "6:00 AM", "12:00 PM", "1:30 PM", "11:59 PM", "", "8:15 AM", "noon"]
