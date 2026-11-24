"""Travel filing checklist data (docs/TRAVEL_FILING_PLAN.md, section 6).

One row per document the checklist can ask for. `rule(kind, answers)` returns "required",
"optional" or None (not applicable) for a filing kind (`ca`, `liquidation`, `reimbursement`)
and the answers that drive the checklist. Pure data and functions: no database.

Keys in `answers` that are not asked on the form but filled in by the platform:
`mc114_format` (copied from the filing), `rides_cenrr` / `rides_rer` (set when the
itinerary is prepared, from `travel_rules.ride_check`) and `meals_not_provided` (set then too:
1 when any per diem day has meals or lodging unticked as not provided, DM 2026-0521)."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Callable, Optional

CHECKLIST_REV = "FMS-BD-01 r6 2025-06"

CA, LIQ, REI = "ca", "liquidation", "reimbursement"
LR_ = (LIQ, REI)
KINDS = (CA, LIQ, REI)

# The questions asked at filing that drive the checklist: (key, label, kinds they apply to).
ANSWER_KEYS = (
    ("flew", "I travelled by plane", (CA, LIQ, REI)),
    ("plane_fare_differs", "The fare I paid differs from the lowest economy fare", (LIQ,)),
    ("boat_bus", "I travelled by boat or bus", (LIQ, REI)),
    ("terminal_fee", "I paid a terminal fee", (LIQ, REI)),
    ("taxi_receipt", "I travelled by taxi", (LIQ, REI)),
    ("ride_hailing", "I used ride-hailing (TNVS)", (LIQ, REI)),
    ("gov_vehicle", "I used a government vehicle", (LIQ, REI)),
    ("rfid", "I used an RFID toll account", (LIQ, REI)),
    ("lodging_claimed", "I claim lodging (travel within 50 km)", (LIQ, REI)),
    ("per_diem_claimed", "I claim per diem", (LIQ, REI)),
    ("extra_expenses", "I have other extra expenses (rebooking, cancellation, or baggage for a cash advance)", (CA, LIQ, REI)),
    ("baggage_outbound", "I paid for extra baggage on the outbound flight", (LIQ, REI)),
    ("baggage_return", "I paid for extra baggage on the return flight", (LIQ, REI)),
    ("jo_cos", "I am a Job Order or COS worker", (CA, LIQ, REI)),
    ("representative_signs", "The Department Personnel Order allows a representative or OIC to sign", (CA, LIQ, REI)),
    ("exceeds_daily_rate", "My expenses exceed the daily rate", (LIQ, REI)),
    ("with_reimbursement", "This liquidation comes with a reimbursement claim", (LIQ,)),
    ("refund", "I am refunding part of the advance", (LIQ,)),
    ("revised_itinerary", "My itinerary changed from the cash advance", (LIQ,)),
    ("official_gasoline", "I need official gasoline", (CA,)),
    ("urgent_travel", "This is urgent or unplanned travel that could not be filed a week ahead (expedited processing)", (CA,)),
    ("cert_of_appearance_available", "I have a Certificate of Appearance", (LIQ, REI)),
)

ROLES = (("participant", "Participant"), ("secretariat", "Secretariat"),
         ("resource_person", "Resource person"), ("technical_support", "Technical support"))

# Documents that are signed in ink at submission (the print list on the ready page).
WET_SIGN = frozenset({"appendix_a", "appendix_b", "mc114_justification", "jo_cert", "cert_appearance",
                      "ridehail_receipt", "cenrr", "rer", "travel_report",
                      "extra_expense_justification", "meals_lodging_cert"})


def truthy(v) -> bool:
    """A form answer as a boolean ("1", "on", "yes", True ...)."""
    if isinstance(v, str):
        return v.strip().lower() in ("1", "true", "yes", "y", "on")
    return bool(v)


@dataclass(frozen=True)
class ItemDef:
    code: str
    label: str
    handling: str                       # generate | upload | fmis | carry
    rule: Callable[[str, dict], Optional[str]]
    copies: int = 1
    note: str = ""

    @property
    def wet_sign(self) -> bool:
        return self.code in WET_SIGN


@dataclass(frozen=True)
class ItemSpec:
    """One applicable checklist row for a filing."""
    code: str
    label: str
    handling: str
    requirement: str                    # "required" | "optional"
    copies: int
    wet_sign: bool
    note: str


def _always(*kinds):
    return lambda kind, a: "required" if kind in kinds else None


def _when(key, *kinds, optional=False):
    """Required for `kinds` when answers[key] is true."""
    def rule(kind, a):
        if kind in kinds and truthy(a.get(key)):
            return "optional" if optional else "required"
        return None
    return rule


def _mc114(kind, a):
    return "optional" if a.get("mc114_format") == "separate" else None


def _meals_lodging_cert(kind, a):
    """DM 2026-0521: every day counts as meals and lodging provided unless the person unticks it, and only
    unticked days need the Certificate of Non-Provision. Before the itinerary is prepared the answer is
    not known, so a per diem claim still lists the certificate."""
    if kind in (LIQ, REI) and truthy(a.get("per_diem_claimed")) and truthy(a.get("meals_not_provided", 1)):
        return "required"
    return None


def _extra(kinds):
    """Extra expenses of any kind: the general answer, or extra baggage on either flight (DM 2026-0521 asks for the
    baggage per flight, liquidation and reimbursement only)."""
    def rule(kind, a):
        if kind not in kinds:
            return None
        baggage = kind in LR_ and (truthy(a.get("baggage_outbound")) or truthy(a.get("baggage_return")))
        return "required" if truthy(a.get("extra_expenses")) or baggage else None
    return rule


def _return_baggage(kind, a):
    """DM 2026-0521: extra baggage on the return flight is not allowed by default when the outbound had none."""
    if kind in LR_ and truthy(a.get("baggage_return")) and not truthy(a.get("baggage_outbound")):
        return "required"
    return None


def _cert_appearance(kind, a):
    if kind in (LIQ, REI) and truthy(a.get("cert_of_appearance_available", True)):
        return "required"
    return None


def _bto_report(kind, a):
    if kind in (LIQ, REI) and not truthy(a.get("cert_of_appearance_available", True)):
        return "required"
    return None


def _plane_fare_proof(kind, a):
    if kind in (CA, REI) and truthy(a.get("flew")):
        return "required"
    if kind == LIQ and truthy(a.get("plane_fare_differs")):
        return "required"
    return None


def _appendix_a(kind, a):
    # A liquidation's Appendix A is part of the one Appendix A and B form, with the cash advance and reimbursement lines.
    return "required" if kind in KINDS else None


def _ors_dv(kind, a):
    if kind in (CA, REI):
        return "required"
    if kind == LIQ and truthy(a.get("with_reimbursement")):
        return "required"
    return None


LR = (LIQ, REI)

CHECKLIST: tuple = (
    ItemDef("fms_routing_slip", "FMIS routing slip", "fmis", _always(*KINDS), 1, "1 print-out"),
    ItemDef("ors", "Obligation Request and Status (ORS)", "fmis", _ors_dv, 3),
    ItemDef("dv", "Disbursement Voucher (DV)", "fmis", _ors_dv, 4,
            "For a reimbursement, note on the DV: no cash advance for this travel."),
    ItemDef("accountant_cert", "Accountant's certification", "fmis", _always(CA), 1,
            "Accounting checks for an earlier cash advance that was never liquidated."),
    ItemDef("liquidation_report", "Liquidation Report", "fmis", _always(LIQ), 2,
            "Generated in FMIS. The figures to enter are worked out under Liquidation figures on the prepare page."),
    ItemDef("dpo", "Department Personnel Order (DPO)", "upload", _always(*KINDS), 1,
            "It must state the funding source."),
    ItemDef("dpo_representative", "DPO allowing a representative or OIC to sign", "upload",
            _when("representative_signs", *KINDS), 1,
            "The order that lets a representative or the officer-in-charge sign in the Head of Office's place. Highlight the signer."),
    ItemDef("jo_cert", "Certification for Job Order / COS", "generate", _when("jo_cos", *KINDS), 1),
    ItemDef("jo_clearance", "Signed Certification for Job Order / COS (the JO clearance)", "upload",
            _when("jo_cos", *KINDS), 1,
            "Same document as the certification above: sign it, scan it and upload it here (DM 2025-0202-A/-B)."),
    ItemDef("appendix_a", "Appendix A: Itinerary of Travel", "generate", _appendix_a, 2),
    ItemDef("prev_appendix_a", "Appendix A of the cash advance", "carry", _always(LIQ), 1,
            "Taken from the linked cash advance, or add it by hand."),
    ItemDef("prev_dv", "DV of the cash advance", "carry", _always(LIQ), 1,
            "Taken from the linked cash advance, or add it by hand."),
    ItemDef("appendix_b", "Appendix B: Certificate of Travel Completed", "generate", _always(*LR), 2,
            "Includes the MC 114 justification when you choose that format."),
    ItemDef("mc114_justification", "MC 114 justification (separate sheet)", "generate", _mc114, 1),
    ItemDef("cert_appearance", "Certificate of Appearance", "upload", _cert_appearance, 1,
            "Sign in ink when submitting."),
    ItemDef("bto_report", "Back-to-office report", "upload", _bto_report, 1,
            "With highlights, plan of action, recommendations and a dated picture."),
    ItemDef("meals_lodging_cert", "Certificate of Non-Provision of Meals and Accommodation", "generate",
            _meals_lodging_cert, 1,
            "Made from the days you unticked on the prepare page. Full per diem is not allowed for any day the host "
            "or regional unit provided meals or lodging; the head of office who signs is accountable and an "
            "inaccurate certificate is not honoured (DM 2026-0521)."),
    ItemDef("plane_ticket", "Plane ticket / e-ticket", "upload", _when("flew", *LR), 1,
            "Lowest regular economy fare. Premium economy, comfort and business class are not allowed unless the "
            "Office of the President approved them in advance (DM 2024-0369)."),
    ItemDef("plane_fare_proof", "Proof of lowest fare (screenshot or quotation)", "upload",
            _plane_fare_proof, 1,
            "Clear screenshots of the fare options taken just before booking, showing the timestamp, date and fares. "
            "Lowest regular economy includes Cebu Pacific GO BASIC / GO EASY and PAL Economy Supersaver, Saver, Value "
            "and Flex. For a PAL round trip, include both the outbound and return fares unless both are Supersaver "
            "(DM 2026-0521)."),
    ItemDef("boarding_pass", "Boarding pass", "upload", _when("flew", *LR), 1,
            "Thermal paper needs a photocopy."),
    ItemDef("extra_expense_invoice", "Invoice for extra expenses", "upload",
            _extra(LR), 1,
            "Baggage, rebooking, cancellation. Extra baggage on the return flight is not allowed when the outbound "
            "flight had none, and personal baggage is never paid (DM 2026-0521)."),
    ItemDef("extra_expense_justification", "Justification for extra expenses", "upload",
            _extra(KINDS), 1,
            "Extra baggage must be for official use: say what official items were carried. Template pending; may sit "
            "inside Appendix B."),
    ItemDef("return_baggage_justification", "Justification for extra baggage on the return flight only", "upload",
            _return_baggage, 1,
            "You had no extra baggage on the outbound flight, so extra baggage on the return is not allowed by default. "
            "Explain the official items carried back and why; baggage for personal reasons is not paid, and FMS may deny "
            "claims it finds excessive (DM 2026-0521)."),
    ItemDef("boat_bus_ticket", "Boat or bus ticket", "upload", _when("boat_bus", *LR), 1,
            "Regular air-conditioned bus only."),
    ItemDef("terminal_fee", "Terminal fee receipt", "upload", _when("terminal_fee", *LR), 1),
    ItemDef("taxi_receipt", "Taxi receipts", "upload", _when("taxi_receipt", *LR), 1),
    ItemDef("cenrr", "Certification of Expenses Not Requiring Receipts (CENRR)", "generate",
            _when("rides_cenrr", *LR), 1),
    ItemDef("rer", "Receipt for Expenses Incurred (RER), one per ride", "generate",
            _when("rides_rer", *LR), 1),
    ItemDef("ridehail_receipt", "Ride-hailing receipts", "upload", _when("ride_hailing", *LR), 1,
            "Official e-receipts from the app or email: one passenger, point to point, matching the itinerary's dates "
            "and route. Keep them: FMS may check them on your phone or email, and unverified receipts are not paid. "
            "Multi-stop or shared rides count only with all passengers' claims submitted together, the fare split per "
            "stop, and a justification (DM 2026-0521). Write 'certified duplicate copy of the original' in ink on every "
            "page."),
    ItemDef("gov_vehicle_docs", "Government vehicle documents", "upload",
            _when("gov_vehicle", *LR), 1, "Trip ticket, fuel, toll, summary."),
    ItemDef("rfid_docs", "RFID documents", "upload", _when("rfid", *LR), 1,
            "Statement of account, invoice, Head certification, summary."),
    ItemDef("lodging_bill", "Lodging bill", "upload", _when("lodging_claimed", *LR), 1),
    ItemDef("exceeds_rate_cert", "Certification that expenses exceed the daily rate", "upload",
            _when("exceeds_daily_rate", *LR), 1, "Head of Agency certification."),
    ItemDef("refund_or", "DOH official receipt for the refund", "upload", _when("refund", LIQ), 1),
    ItemDef("urgent_justification", "Written justification for urgent or unplanned travel", "upload",
            _when("urgent_travel", CA), 1,
            "Why the travel could not be anticipated in time. The DPO must already be approved. FMS decides whether "
            "the request takes its expedited processing window (DM 2026-0521)."),
    ItemDef("gasoline_estimate", "Gasoline estimate", "upload", _when("official_gasoline", CA), 1,
            "Cleared by AS-GSD."),
    ItemDef("travel_report", "Post Travel Report", "generate", _always(*LR), 1,
            "The approver depends on the claimant's level."),
)

BY_CODE = {d.code: d for d in CHECKLIST}


def spec_for(code: str) -> Optional[ItemDef]:
    return BY_CODE.get(code)
