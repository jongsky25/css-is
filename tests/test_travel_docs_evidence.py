"""Spot feedback #173: the "Evidence of Travel attached hereto" list fills itself with the standing attachments."""
import travel_docs as td


def item(code, label, handling="upload", state="missing", doc_url=""):
    return {"code": code, "label": label, "handling": handling, "state": state, "doc_url": doc_url}


ITEMS = [item("dpo", "Department Personnel Order (DPO)", state="present"),
         item("appendix_b", "Appendix B", "generate", doc_url="u"),
         item("cert_appearance", "Certificate of Appearance"),
         item("travel_report", "Post Travel Report", "generate", doc_url="u"),
         item("plane_ticket", "Plane ticket / e-ticket", state="present"),
         item("taxi_receipt", "Taxi receipts"),
         item("ors", "Obligation Request and Status (ORS)", "fmis", state="present")]


def test_standing_attachments_come_first_and_are_numbered():
    out = td._evidence(ITEMS, {"dpo_no": "2026-0412", "dpo_date": "2026-10-05"})
    assert out[0] == "1. Department Personnel Order (DPO) No. 2026-0412 dated October 5, 2026"
    assert out[1:4] == ["2. Appendix A and B", "3. Certificate of Appearance", "4. Post Travel Report"]


def test_unknown_dpo_number_and_date_are_left_blank():
    assert td._evidence(ITEMS, {})[0] == "1. Department Personnel Order (DPO) No. ________ dated ________"


def test_other_attachments_follow_without_repeating_the_standing_ones():
    out = td._evidence(ITEMS, {}, "  Boarding pass \n\nReceipt of the venue\n")
    assert out[4:] == ["5. Plane ticket / e-ticket", "6. Boarding pass", "7. Receipt of the venue"]
    assert len(out) == len(set(out)) and not any("Obligation" in ln or "Taxi" in ln for ln in out)


def test_back_to_office_report_stands_in_when_there_is_no_certificate_of_appearance():
    items = [i for i in ITEMS if i["code"] != "cert_appearance"] + [item("bto_report", "Back-to-office report")]
    assert td._evidence(items, {})[2] == "3. Back-to-office report"
