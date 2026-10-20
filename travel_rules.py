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
CA_MIN_LEAD_DAYS = 7         # a cash advance needs MORE than this many days before the activity starts
NO_RECEIPT_LIMIT = 1000      # an unreceipted fare above this always goes to the Admin Unit
RECEIPT_MODES = ("tnvs", "taxi")
RIDE_MODES = RECEIPT_MODES + ("public_noreceipt",)
FLAG_LABELS = {
    "over_ceiling": "Fare above the ceiling",
    "unlisted_route": "Route not on the approved list",
    "no_receipt_over_1000": "No receipt for a fare above 1,000",
    "participant_only": "Participant-only travel",
}

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

    Liquidation and reimbursement are due 5 working days after the last day of the activity,
    whether or not it had ended when the filing was opened. A cash advance has no deadline
    while the activity is current or ahead; once it has ended it is held to the same date."""
    end, opened = _d(act_end_iso), _d(opened_iso)
    due = rooms.add_working_days(conn, end, DUE_WORKING_DAYS).isoformat()
    if kind in ("liquidation", "reimbursement"):
        return due, "plotted"
    if end < opened:
        return due, "after_fact"
    return None, "none"


def ca_lead_error(act_start_iso, today_iso):
    """Why a cash advance cannot be filed for this activity today, or None when it can.
    Owner's rule: only more than a week before the activity starts (8 or more days ahead)."""
    days = (_d(act_start_iso) - _d(today_iso)).days
    if days > CA_MIN_LEAD_DAYS:
        return None
    return ("A cash advance can only be filed more than a week before the activity starts. "
            "Once it is closer or over, file a reimbursement instead.")


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
