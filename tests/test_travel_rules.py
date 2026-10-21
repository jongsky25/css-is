"""Travel filing rules: deadlines, ride checks, flags, checklist, completeness, formatters."""
from __future__ import annotations
from datetime import date

import pytest

import storage as st
import travel
import travel_checklist as tc
import travel_docs as td
import travel_rules as tr


@pytest.fixture()
def conn(tmp_path):
    c = st.connect(str(tmp_path / "travel.db")); st.init_db(c)
    c.execute("DELETE FROM holiday"); c.commit()          # deterministic: no seeded holidays
    return c


CEIL = {("rer", "residence_airport"): 550, ("rer", "residence_venue"): 450,
        ("tnvs", "*"): 700, ("taxi", "*"): 700, ("cenrr", "*"): 300}


def kinds(res):
    return sorted(f.kind for f in res.flags)


# --------------------------------------------------------------- deadlines ---

def test_deadline_is_five_working_days_after_the_last_day(conn):
    # Fri 16 Oct 2026 + 5 working days = Fri 23 Oct
    assert tr.deadline_for(conn, "liquidation", "2026-10-16", "2026-10-01") == ("2026-10-23", "plotted")
    assert tr.deadline_for(conn, "reimbursement", "2026-10-12", "2026-10-01") == ("2026-10-19", "plotted")


def test_deadline_skips_a_holiday(conn):
    st.set_holiday(conn, "2026-10-19", "Test holiday", "regular")
    assert tr.deadline_for(conn, "liquidation", "2026-10-12", "2026-10-01") == ("2026-10-20", "plotted")


def test_deadline_counts_from_the_last_day_not_from_opening(conn):
    # activity ended Fri 16 Oct, filing opened Tue 20 Oct: still due Fri 23 Oct
    assert tr.deadline_for(conn, "liquidation", "2026-10-16", "2026-10-20") == ("2026-10-23", "plotted")
    assert tr.deadline_for(conn, "reimbursement", "2026-10-16", "2026-10-20") == ("2026-10-23", "plotted")


def test_cash_advance_on_an_ended_activity_is_held_to_the_same_date(conn):
    assert tr.deadline_for(conn, "ca", "2026-10-09", "2026-10-16") == ("2026-10-16", "after_fact")


def test_cash_advance_on_a_future_or_current_activity_has_no_deadline(conn):
    assert tr.deadline_for(conn, "ca", "2026-10-16", "2026-10-01") == (None, "none")
    assert tr.deadline_for(conn, "ca", "2026-10-16", "2026-10-16") == (None, "none")


def test_count_working_days_excludes_start_includes_end(conn):
    assert tr.count_working_days(conn, "2026-10-16", "2026-10-23") == 5
    assert tr.count_working_days(conn, "2026-10-16", "2026-10-16") == 0
    st.set_holiday(conn, "2026-10-20", "Test holiday", "regular")
    assert tr.count_working_days(conn, "2026-10-16", "2026-10-23") == 4


def test_cash_advance_needs_more_than_a_week_of_lead():
    assert tr.ca_lead_error("2026-10-22", "2026-10-14") is None          # 8 days ahead
    assert tr.ca_lead_error("2026-10-21", "2026-10-14")                  # exactly 7 days: too late
    assert tr.ca_lead_error("2026-10-14", "2026-10-14")
    assert tr.ca_lead_error("2026-10-01", "2026-10-14")                  # already over


# -------------------------------------------------------------------- rides ---

def test_receipted_tnvs_and_taxi_use_the_flat_ceiling():
    assert tr.ride_check("tnvs", "residence_airport", 700, "receipt", CEIL).flags == []
    r = tr.ride_check("tnvs", "residence_airport", 701, "receipt", CEIL)
    assert r.kind == "receipt" and kinds(r) == ["over_ceiling"] and "1 above" in r.flags[0].detail
    assert kinds(tr.ride_check("taxi", "residence_venue", 701, "receipt", CEIL)) == ["over_ceiling"]


@pytest.mark.parametrize("route,fare,over", [
    ("residence_airport", 550, False), ("residence_airport", 551, True),
    ("residence_venue", 450, False), ("residence_venue", 451, True)])
def test_unreceipted_rer_ceilings(route, fare, over):
    r = tr.ride_check("public_noreceipt", route, fare, "none", CEIL)
    assert r.kind == "rer"
    assert kinds(r) == (["over_ceiling"] if over else [])


def test_cenrr_boundary():
    assert tr.ride_check("public_noreceipt", "residence_venue", 300, "none", CEIL).kind == "cenrr"
    assert tr.ride_check("public_noreceipt", "residence_venue", 300.01, "none", CEIL).kind == "rer"


def test_unreceipted_over_a_thousand_is_flagged():
    r = tr.ride_check("public_noreceipt", "residence_airport", 1000.01, "none", CEIL)
    assert "no_receipt_over_1000" in kinds(r)
    assert "no_receipt_over_1000" not in kinds(
        tr.ride_check("public_noreceipt", "residence_airport", 1000, "none", CEIL))


@pytest.mark.parametrize("mode,receipt", [("tnvs", "receipt"), ("taxi", "receipt"), ("taxi", "none"),
                                          ("public_noreceipt", "none")])
@pytest.mark.parametrize("route", ["", "somewhere_else", None])
def test_unknown_route_always_flags(mode, receipt, route):
    assert "unlisted_route" in kinds(tr.ride_check(mode, route, 200, receipt, CEIL))


def test_no_fare_or_other_modes_need_nothing():
    assert tr.ride_check("tnvs", "residence_venue", 0, "receipt", CEIL).kind is None
    assert tr.ride_check("plane", "residence_venue", 5000, "receipt", CEIL).flags == []


def test_flag_sig_changes_only_when_the_ride_changes():
    a = tr.ride_check("tnvs", "residence_venue", 701, "receipt", CEIL, "k1").flags[0]
    b = tr.ride_check("tnvs", "residence_venue", 701, "receipt", CEIL, "k1").flags[0]
    c = tr.ride_check("tnvs", "residence_venue", 750, "receipt", CEIL, "k1").flags[0]
    assert a.sig == b.sig != c.sig


def test_flags_for_rows_and_participant_only():
    rows = [{"date": "2026-10-12", "from": "Home", "to": "NAIA", "mode": "taxi",
             "route_type": "residence_airport", "receipt": "receipt", "allowance": 800},
            {"date": "2026-10-12", "from": "Home", "to": "NAIA", "mode": "taxi",
             "route_type": "residence_airport", "receipt": "receipt", "allowance": 800},
            {"date": "2026-10-13", "mode": "plane", "allowance": 5000}]
    flags = tr.flags_for({}, rows, {"role": "participant"}, CEIL)
    assert sorted(f.kind for f in flags) == ["over_ceiling", "over_ceiling", "participant_only"]
    assert len({f.sig for f in flags}) == 3            # repeated legs get distinct keys
    assert [f.kind for f in tr.flags_for({}, [], {"role": "secretariat"}, CEIL)] == []


# ---------------------------------------------------------------- checklist ---

def codes(kind, **a):
    return {i.code: i.requirement for i in tr.build_checklist(kind, a)}


def test_cash_advance_base_checklist():
    c = codes("ca")
    assert set(c) == {"fms_routing_slip", "ors", "dv", "accountant_cert", "dpo", "appendix_a"}


def test_liquidation_base_checklist():
    c = codes("liquidation")
    assert set(c) == {"fms_routing_slip", "dpo", "prev_appendix_a", "prev_dv", "appendix_a", "appendix_b",
                      "liquidation_report", "cert_appearance", "travel_report"}


def test_reimbursement_base_checklist():
    c = codes("reimbursement")
    assert set(c) == {"fms_routing_slip", "ors", "dv", "dpo", "appendix_a", "appendix_b",
                      "cert_appearance", "travel_report"}


def test_answers_add_rows():
    c = codes("liquidation", flew=1, with_reimbursement="yes", jo_cos=True, refund="1",
              revised_itinerary="on", plane_fare_differs=1)
    for code in ("plane_ticket", "boarding_pass", "plane_fare_proof", "ors", "dv", "jo_cert",
                 "jo_clearance", "refund_or", "appendix_a"):
        assert code in c, code
    assert "refund_or" not in codes("reimbursement", refund=1)
    assert "plane_fare_proof" in codes("ca", flew=1) and "plane_ticket" not in codes("ca", flew=1)
    assert "plane_fare_proof" not in codes("liquidation", flew=1)
    assert "gasoline_estimate" in codes("ca", official_gasoline=1)


def test_mc114_separate_is_optional_and_others_are_not_listed():
    assert codes("ca", mc114_format="separate")["mc114_justification"] == "optional"
    assert "mc114_justification" not in codes("ca", mc114_format="appendix_b")
    assert "mc114_justification" not in codes("ca")


def test_certificate_of_appearance_or_back_to_office_report():
    assert "cert_appearance" in codes("liquidation") and "bto_report" not in codes("liquidation")
    c = codes("reimbursement", cert_of_appearance_available="0")
    assert "bto_report" in c and "cert_appearance" not in c


def test_ride_documents_follow_the_derived_answers():
    c = codes("liquidation", rides_cenrr=1, rides_rer=1)
    assert "cenrr" in c and "rer" in c
    assert "cenrr" not in codes("ca", rides_cenrr=1)


def test_every_row_has_known_handling_and_wet_sign_set_matches():
    assert {d.handling for d in tc.CHECKLIST} <= {"generate", "upload", "fmis", "carry"}
    assert tc.WET_SIGN <= set(tc.BY_CODE)
    assert tc.BY_CODE["appendix_a"].wet_sign and not tc.BY_CODE["dpo"].wet_sign
    assert tc.BY_CODE["ors"].copies == 3 and tc.BY_CODE["dv"].copies == 4


# ------------------------------------------------------------- completeness ---

def item(code, handling, requirement="required", **kw):
    return {"code": code, "label": code, "handling": handling, "requirement": requirement,
            "state": "missing", "drive_url": None, "doc_url": None, **kw}


def test_fmis_and_optional_rows_never_block():
    items = [item("ors", "fmis"), item("mc114_justification", "generate", "optional")]
    assert tr.completeness({"kind": "ca"}, items, []) == []


def test_missing_rows_are_listed_in_words():
    items = [item("dpo", "upload"), item("appendix_a", "generate"), item("prev_dv", "carry"),
             item("travel_report", "generate", doc_url="https://x"),
             item("cert_appearance", "upload", state="na")]
    out = tr.completeness({"kind": "reimbursement"}, items, [])
    assert len(out) == 3 and any("Drive link" in m for m in out) and any("Generate" in m for m in out)


def test_present_manual_carry_and_open_flags():
    items = [item("prev_dv", "carry", note="paid 2025")]
    assert tr.completeness({"kind": "reimbursement"}, items, []) == []
    out = tr.completeness({"kind": "reimbursement"}, items,
                          [{"state": "open", "detail": "Fare 701"}, {"state": "verified", "detail": "x"}])
    assert len(out) == 1 and "Fare 701" in out[0]


def test_liquidation_needs_a_cash_advance_or_an_amount():
    assert tr.completeness({"kind": "liquidation"}, [], [])
    assert tr.completeness({"kind": "liquidation", "ca_filing_id": 3}, [], []) == []
    assert tr.completeness({"kind": "liquidation", "advance_amount": 2500.0}, [], []) == []


# --------------------------------------------------------------- formatters ---

@pytest.mark.parametrize("amount,words", [
    (450, "Four Hundred Fifty Pesos"), (1060, "One Thousand Sixty Pesos"),
    (550.5, "Five Hundred Fifty Pesos and 50/100"), (0, "Zero Pesos"), (1, "One Peso"),
    (1.05, "One Peso and 05/100"), (21000, "Twenty One Thousand Pesos"),
    (1234567, "One Million Two Hundred Thirty Four Thousand Five Hundred Sixty Seven Pesos")])
def test_peso_words(amount, words):
    assert td.peso_words(amount) == words


def test_peso_words_rejects_negative():
    with pytest.raises(ValueError):
        td.peso_words(-1)


@pytest.mark.parametrize("start,end,text", [
    ("2026-09-01", "2026-09-04", "September 01-04, 2026"),
    ("2026-08-30", "2026-09-02", "August 30 - September 02, 2026"),
    ("2026-09-01", "2026-09-01", "September 01, 2026"),
    ("2026-12-30", "2027-01-02", "December 30, 2026 - January 02, 2027")])
def test_date_range(start, end, text):
    assert td.date_range(start, end) == text
    assert td.date_range(date.fromisoformat(start), date.fromisoformat(end)) == text


def test_money():
    assert td.money(1060) == "1,060" and td.money(1060.5) == "1,060.50" and td.money(None) == "0"


def test_the_representative_dpo_row_says_it_allows_a_representative_or_oic_to_sign():
    """Spot feedback #145: it is the DPO that allows them to sign, not a DPO a representative signed."""
    import travel_checklist as tc
    row = next(d for d in tc.CHECKLIST if d.code == "dpo_representative")
    assert row.label == "DPO allowing a representative or OIC to sign" and "officer-in-charge" in row.note
    question = next(label for key, label, _ in tc.ANSWER_KEYS if key == "representative_signs")
    assert "allows a representative or OIC to sign" in question
