"""Travel filing rules (docs/TRAVEL_FILING_PLAN.md, section 6). Pure functions: the only
database use is the holiday lookup behind the working-day counters."""
from __future__ import annotations
import hashlib
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal
from typing import Optional

import rooms
import travel_checklist as tc
import travel_rates as rates

DUE_WORKING_DAYS = 5         # working days after the last day of the activity to file
DUE_CALENDAR_DAYS = 7        # DM 2026-0521: local-travel liquidation within 7 days of return
CA_HAND_IN_WORKING_DAYS = 3  # DM 2026-0521: a cash advance reaches FMS at least 3 working days before departure
CA_MIN_LEAD_DAYS = 7         # a cash advance needs MORE than this many days before the activity starts
NO_RECEIPT_LIMIT = 1000      # an unreceipted fare above this always goes to the Admin Unit
RECEIPT_MODES = ("tnvs", "taxi")
RIDE_MODES = RECEIPT_MODES + ("public_noreceipt",)
FLAG_LABELS = {
    "over_ceiling": "Fare above the ceiling",
    "unlisted_route": "Route not on the approved list",
    "no_receipt_over_1000": "No receipt for a fare above 1,000",
    "participant_only": "Participant-only travel",
    # DM 2026-0521 pre-audit checks on what the AI read off uploads (reading_flags)
    "receipt_mismatch": "Receipt does not match the itinerary",
    "shared_ride": "Multi-stop or shared ride",
    "fare_class": "Fare class not allowed",
    "fare_proof": "Proof of lowest fare incomplete",
}

# DM 2026-0521: the regular economy fares named as lowest (Cebu Pacific and Philippine Airlines). A brand is only
# checked for these two airlines; for any other airline only the cabin is.
ECONOMY_BRANDS = {
    "cebu": ("GO BASIC", "GO EASY"),
    "philippine airlines": ("ECONOMY SUPERSAVER", "SUPERSAVER", "SUPER SAVER", "ECONOMY SAVER", "SAVER",
                            "ECONOMY VALUE", "VALUE", "ECONOMY FLEX", "FLEX"),
}
NOT_ECONOMY = ("premium_economy", "business", "first")
RECEIPT_TOLERANCE = 1           # pesos a receipt may differ from its itinerary fare (rounding)

PER_DIEM_LABEL = "Per diem above the policy rate"


def flag_label(kind, detail="") -> str:
    """The heading a flag shows. A per diem above its policy rate is stored under 'over_ceiling' (the
    table only allows the four kinds), so the text of the flag tells it from a fare."""
    if kind == "over_ceiling" and (detail or "").startswith("Per diem"):
        return PER_DIEM_LABEL
    return FLAG_LABELS.get(kind, kind)


def _d(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v))


# ------------------------------------------------------------- deadlines ---

def count_working_days(conn, start_iso, end_iso) -> int:
    """Working days after `start` up to and including `end` (start itself is not counted)."""
    day, end, n = _d(start_iso), _d(end_iso), 0
    while day < end:
        day += timedelta(days=1)
        if rooms.is_working_day(conn, day):
            n += 1
    return n


def deadline_for(conn, kind, act_end_iso, opened_iso):
    """(deadline ISO date or None, rule) where rule is 'after_fact', 'plotted' or 'none'.

    Liquidation and reimbursement are due on the date `due_after` gives for the last day of the activity,
    whether or not it had ended when the filing was opened. A cash advance has no deadline
    while the activity is current or ahead; once it has ended it is held to the same date."""
    end, opened = _d(act_end_iso), _d(opened_iso)
    due = due_after(conn, end).isoformat()
    if kind in ("liquidation", "reimbursement"):
        return due, "plotted"
    if end < opened:
        return due, "after_fact"
    return None, "none"


def due_after(conn, end) -> date:
    """The filing date for an activity that ended on `end`: the earlier of 5 working days and
    7 calendar days after it (owner decision on DM 2026-0521, 2026-11-24). A 7th day that is not
    a working day moves back to the working day before it, never past the last day itself."""
    end = _d(end)
    by_working = rooms.add_working_days(conn, end, DUE_WORKING_DAYS)
    by_calendar = end + timedelta(days=DUE_CALENDAR_DAYS)
    if by_working <= by_calendar:
        return by_working
    day = by_calendar
    while day > end + timedelta(days=1) and not rooms.is_working_day(conn, day):
        day -= timedelta(days=1)
    return day


def ca_hand_in_by(conn, act_start_iso) -> date:
    """The last day a cash advance request should reach FMS: 3 working days before departure
    (DM 2026-0521). Shown and reminded only; FMS, not the platform, refuses late requests."""
    day, left = _d(act_start_iso), CA_HAND_IN_WORKING_DAYS
    while left > 0:
        day -= timedelta(days=1)
        if rooms.is_working_day(conn, day):
            left -= 1
    return day


def ca_lead_error(act_start_iso, today_iso, urgent=False):
    """Why a cash advance cannot be filed for this activity today, or None when it can.
    Owner's rule: only more than a week before the activity starts (8 or more days ahead). DM 2026-0521 adds an
    expedited window for urgent or unplanned travel (owner decision 3, 2026-11-24): inside the week a cash advance
    is allowed when the person marks it urgent, as long as the activity has not started."""
    days = (_d(act_start_iso) - _d(today_iso)).days
    if days > CA_MIN_LEAD_DAYS:
        return None
    if days >= 1 and urgent:
        return None
    if days >= 1:
        return ("A cash advance can only be filed more than a week before the activity starts, unless the travel is "
                "urgent or unplanned: tick that question and upload a written justification. Otherwise file a "
                "reimbursement instead.")
    return ("A cash advance can only be filed before the activity starts. File a reimbursement instead.")


def ca_urgent_window(act_start_iso, today_iso) -> bool:
    """True inside the week before the activity starts: only an urgent cash advance can be filed now."""
    days = (_d(act_start_iso) - _d(today_iso)).days
    return 1 <= days <= CA_MIN_LEAD_DAYS


# ----------------------------------------------------------------- rides ---

@dataclass(frozen=True)
class FlagSpec:
    kind: str
    sig: str
    detail: str
    row_key: str = ""


@dataclass
class RideResult:
    kind: Optional[str]                 # 'receipt' | 'cenrr' | 'rer' | None (no fare)
    flags: list = field(default_factory=list)


def _dec(v) -> Decimal:
    try:
        return Decimal(str(v if v not in (None, "") else 0))
    except Exception:                                       # noqa: BLE001
        return Decimal(0)


def _num(d: Decimal) -> str:
    return f"{d:,.2f}".rstrip("0").rstrip(".") if d != d.to_integral_value() else f"{d:,.0f}"


def flag_sig(kind, row_key, fare, route_type) -> str:
    """Stable fingerprint: a verified flag stays verified only while nothing in it changes."""
    raw = f"{kind}|{row_key}|{_dec(fare):.2f}|{route_type or ''}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()


def known_routes(ceilings) -> set:
    """Approved route types: those that carry an RER ceiling."""
    return {rt for (mode, rt) in ceilings if mode == "rer"}


def ride_check(mode, route_type, fare, receipt, ceilings, row_key="", cap=None) -> RideResult:
    """Which document a taxi / ride-hailing / public-transport fare needs, and what to flag.

    `ceilings` maps (mode, route_type) to an amount: ('rer', route) per approved route,
    ('tnvs', '*'), ('taxi', '*'), ('cenrr', '*'). A receipted TNVS or taxi fare is checked
    against its flat ceiling; an unreceipted fare is a CENRR up to the CENRR ceiling and an
    RER beyond it, capped per route.

    `cap` is the policy limit for the rate the person chose (travel_rates.row_cap). When there is
    one it is the limit for this ride, on any document, and the route counts as approved: the
    policy itself names it."""
    fare = _dec(fare)
    if fare <= 0 or mode not in RIDE_MODES:
        return RideResult(None)
    route_type = (route_type or "").strip()
    flags = []

    def add(kind, detail):
        flags.append(FlagSpec(kind, flag_sig(kind, row_key, fare, route_type), detail, row_key))

    def over(limit):
        add("over_ceiling", f"Fare {_num(fare)} is {_num(fare - limit)} above the {_num(limit)} ceiling.")

    policy = cap is not None
    known = policy or route_type in known_routes(ceilings)
    if not known:
        add("unlisted_route", "The route is not on the approved list.")
    if policy and fare > _dec(cap):
        over(_dec(cap))
    receipted = mode in RECEIPT_MODES and receipt == "receipt"
    if receipted:
        flat = _dec(ceilings.get((mode, "*"), 0))
        if not policy and flat and fare > flat:
            over(flat)
        return RideResult("receipt", flags)
    cenrr_cap = _dec(ceilings.get(("cenrr", "*"), 300))
    if fare <= cenrr_cap:
        return RideResult("cenrr", flags)
    if not policy:
        route_cap = _dec(ceilings.get(("rer", route_type), 0)) if known else Decimal(0)
        if known and route_cap and fare > route_cap:
            over(route_cap)
    if fare > NO_RECEIPT_LIMIT:
        add("no_receipt_over_1000", f"No receipt for a fare of {_num(fare)}.")
    return RideResult("rer", flags)


def row_keys(rows) -> list:
    """A key per itinerary row that survives other rows being added or removed:
    date|from|to, with a counter for repeats of the same leg."""
    seen, out = {}, []
    for r in rows:
        base = f"{r.get('date', '')}|{r.get('from', '')}|{r.get('to', '')}"
        seen[base] = seen.get(base, 0) + 1
        out.append(f"{base}|{seen[base]}")
    return out


def flags_for(filing, itinerary_rows, answers, ceilings, opts=None, is_working=None) -> list:
    """Every flag the filing currently deserves: one per offending ride, one per day whose per diem
    is above what its day kind allows, plus participant-only. `opts` are the policy-rate options
    the prepare page posted (region, receives_sa, discounted); `is_working` tells working days."""
    flags = []
    keys = row_keys(itinerary_rows)
    calc = rates.rates_for_rows(itinerary_rows, opts, is_working)
    for key, row, rr in zip(keys, itinerary_rows, calc):
        res = ride_check(row.get("mode"), row.get("route_type"), row.get("allowance"),
                         row.get("receipt"), ceilings, key, cap=rr.cap.amount if rr.cap else None)
        flags.extend(res.flags)
        if rr.per_diem is not None and _dec(row.get("per_diem")) > rr.per_diem:
            flags.append(FlagSpec("over_ceiling", flag_sig("over_ceiling", key + "|per_diem", row.get("per_diem"), row.get("day_kind")),
                                  f"Per diem {_num(_dec(row.get('per_diem')))} is {_num(_dec(row.get('per_diem')) - rr.per_diem)} "
                                  f"above the {_num(rr.per_diem)} the policy allows for this day.", key))
    if (answers or {}).get("role") == "participant":
        flags.append(FlagSpec("participant_only",
                              flag_sig("participant_only", "role", 0, ""),
                              "Travelling as a participant only; needs the supervisor's confirmation."))
    return flags


# ------------------------------------------------------------- checklist ---

def build_checklist(kind, answers) -> list:
    """The applicable checklist rows for a filing, in checklist order."""
    answers = answers or {}
    out = []
    for d in tc.CHECKLIST:
        req = d.rule(kind, answers)
        if req:
            out.append(tc.ItemSpec(d.code, d.label, d.handling, req, d.copies, d.wet_sign, d.note))
    return out


def readiness(filing, items, flags) -> list:
    """Current blockers shared by guidance and the ready/submitted write guards."""
    return (["The documents are still being made. Check form progress before continuing."]
            if filing.get("gen_state") == "running" else []) + completeness(filing, items, flags)


def completeness(filing, items, flags) -> list:
    """What still stands between this filing and 'ready', as sentences. FMIS rows and optional
    rows never count. `items` are dicts with code, label, handling, requirement, state,
    drive_url, doc_url, note; `flags` are dicts with state and detail."""
    missing = []
    if filing.get("kind") == "liquidation" and not filing.get("ca_filing_id") \
            and filing.get("advance_amount") in (None, ""):
        missing.append("Say which cash advance this liquidates, or enter the amount you received.")
    for it in items:
        if it.get("requirement") != "required" or it.get("handling") == "fmis" or it.get("state") == "na":
            continue
        h = it.get("handling")
        if h == "generate":
            ok = bool(it.get("doc_url"))
            what = "Generate"
        elif h == "carry":
            ok = bool(it.get("drive_url") or it.get("note"))
            what = "Add"
        else:
            ok = bool(it.get("drive_url"))
            what = "Add a Drive link for"
        if not ok:
            missing.append(f"{what} {it.get('label')}.")
    for fl in flags:
        if fl.get("state") == "open":
            missing.append(f"Waiting for the Admin Unit to verify: {fl.get('detail') or 'a flagged item'}")
        elif fl.get("state") == "rejected":
            why = f" ({fl['note']})" if fl.get("note") else ""
            missing.append(f"The Admin Unit did not accept: {fl.get('detail') or 'a flagged item'}{why} "
                           "Change it on the prepare page, or talk to them.")
    return missing


# ------------------------------------------------- DM 2026-0521: checks on what was read off uploads ---

def _airline(vendor) -> str:
    v = (vendor or "").lower()
    if "cebu" in v:
        return "cebu"
    if "philippine airlines" in v or v.strip() in ("pal", "pr") or "pal express" in v:
        return "philippine airlines"
    return ""


def _brand(v) -> str:
    return " ".join((v or "").upper().replace("-", " ").split())


def _rflag(kind, reading, detail) -> FlagSpec:
    key = f"reading:{reading.get('id')}"
    return FlagSpec(kind, flag_sig(kind, key, reading.get("amount") or 0, detail[:40]), detail, key)


def reading_flags(readings, rows) -> list:
    """Flags for the DM 2026-0521 pre-audit points, from the readings kept for the filing's uploads
    (travel_readings.for_filing) and the itinerary rows posted at generate. Only what a reading actually shows is
    checked: a detail the AI did not read raises nothing. Each flag goes to the Admin Unit like the others."""
    out = []
    receipts = [r for r in readings if r.get("doc") == "receipt"]
    ride_rows = [r for r in rows if r.get("mode") in ("tnvs", "taxi")]
    for x in receipts:
        if x.get("item_code") not in ("ridehail_receipt", "taxi_receipt"):
            continue
        what = "ride-hailing" if x["item_code"] == "ridehail_receipt" else "taxi"
        # Inconsistent with the itinerary (dates, amounts)
        if rows and x.get("day"):
            same_day = [r for r in ride_rows if r.get("date") == x["day"]]
            if not same_day:
                out.append(_rflag("receipt_mismatch", x, f"A {what} receipt dated {x['day']} has no {what} ride on that "
                                                         "date in the itinerary."))
            elif x.get("amount") and not any(abs(_dec(r.get("allowance")) - _dec(x["amount"])) <= RECEIPT_TOLERANCE
                                             for r in same_day):
                out.append(_rflag("receipt_mismatch", x, f"A {what} receipt of {_num(_dec(x['amount']))} on {x['day']} "
                                                         "does not match the fare entered for that date."))
        # Multi-stop or multi-passenger
        stops, pax = x.get("stops") or 0, x.get("passengers") or 0
        if stops > 1 or pax > 1:
            parts = ([f"{stops} stops"] if stops > 1 else []) + ([f"{pax} passengers"] if pax > 1 else [])
            need = ("Accepted only with every passenger's claim submitted together, consistent with the itinerary, "
                    "the fare split per stop or passenger, and a justification that it costs less than separate rides.")
            if x.get("fare_split") == 0:
                need += " The receipt shows no fare split."
            out.append(_rflag("shared_ride", x, f"A {what} receipt shows {' and '.join(parts)}. {need}"))
    tickets = [r for r in receipts if r.get("item_code") in ("plane_ticket", "boarding_pass")]
    for x in tickets:
        cabin, brand, airline = x.get("cabin") or "", _brand(x.get("fare_brand")), _airline(x.get("vendor"))
        if cabin in NOT_ECONOMY:
            out.append(_rflag("fare_class", x, f"The ticket reads {cabin.replace('_', ' ')} class. Only regular "
                                               "economy is allowed unless the Office of the President approved it in advance."))
        elif brand and airline and brand not in ECONOMY_BRANDS[airline]:
            out.append(_rflag("fare_class", x, f"The fare type reads {x.get('fare_brand')}, which is not one of the "
                                               "lowest regular economy fares named for this airline."))
    shots = [r for r in receipts if r.get("item_code") == "plane_fare_proof"]
    for x in (t for t in tickets if t.get("item_code") == "plane_ticket"):
        booked = x.get("booked_at") or ""
        taken = [s.get("captured_at") for s in shots if s.get("captured_at")]
        if booked and taken and all(t > booked for t in taken):
            out.append(_rflag("fare_proof", x, f"Every fare screenshot was taken after the ticket was booked ({booked}). "
                                               "The screenshots must be captured just before booking."))
        if (_airline(x.get("vendor")) == "philippine airlines" and x.get("round_trip") == 1
                and "SUPERSAVER" not in _brand(x.get("fare_brand")).replace(" ", "") and len(shots) < 2):
            out.append(_rflag("fare_proof", x, "A Philippine Airlines round trip that is not Economy Supersaver needs "
                                               "screenshots of both the outbound and the return fares."))
    return out
