"""Read the amount off an uploaded ticket, boarding pass or receipt (the AI step of the travel
prepare page). The file is looked at once and dropped: nothing here stores it. What comes back is
a suggestion the person confirms before it goes in an Appendix A row; a wrong or unreadable scan
costs them a few keystrokes, never a wrong filing.

Pure apart from `read()`, which makes the one Gemini call through ai_core."""
from __future__ import annotations
import re
from datetime import date
from decimal import Decimal, InvalidOperation

import ai_core

FEATURE = "travel_scan"
MAX_BYTES = 6 * 1024 * 1024
MIME_OK = ("image/jpeg", "image/png", "image/webp", "application/pdf")
KINDS = ("plane_ticket", "boarding_pass", "bus_boat_ticket", "taxi_receipt", "ridehail_receipt",
         "terminal_fee", "lodging_bill", "official_receipt", "other")
MAX_AMOUNT = Decimal("1000000")
# Checklist rows whose uploads are tickets or receipts: an upload to one of these is also read for its amount.
READ_CODES = frozenset({"plane_ticket", "boarding_pass", "boat_bus_ticket", "terminal_fee", "taxi_receipt",
                        "ridehail_receipt", "lodging_bill", "extra_expense_invoice", "refund_or"})

SYSTEM = (
    "You read Philippine travel documents for a government travel claim: airline e-tickets, "
    "boarding passes, bus or boat tickets, taxi and ride-hailing receipts (Grab, Move It, "
    "inDrive, Angkas), terminal fee receipts and hotel bills. Report only what is printed on "
    "the document. Never guess or calculate a figure that is not shown. If the document is not "
    "one of these or cannot be read, set readable to false."
)
PROMPT = (
    "Read this document. amount is the total the traveller paid for the trip or item, in pesos, "
    "as a plain number (no currency sign, no thousands separators). For an airline ticket use "
    "the total fare including taxes and fees. If the amount is in another currency, give it in "
    "that currency and name it in currency. date is the travel or receipt date as YYYY-MM-DD. "
    "origin and destination are the places travelled between (leave empty if none). "
    "vendor is the airline, operator or business. reference is the ticket, booking or receipt "
    "number. depart_time and arrive_time are the departure and arrival times as 24-hour HH:MM when the "
    "document prints them (leave empty if not shown). note is one short sentence on anything the person "
    "should double-check."
)
SCHEMA = {"type": "OBJECT", "properties": {
    "readable": {"type": "BOOLEAN"},
    "kind": {"type": "STRING", "enum": list(KINDS)},
    "amount": {"type": "NUMBER"},
    "currency": {"type": "STRING"},
    "date": {"type": "STRING"},
    "origin": {"type": "STRING"},
    "destination": {"type": "STRING"},
    "vendor": {"type": "STRING"},
    "reference": {"type": "STRING"},
    "depart_time": {"type": "STRING"},
    "arrive_time": {"type": "STRING"},
    "note": {"type": "STRING"},
}, "required": ["readable", "kind", "amount", "currency", "date", "origin", "destination",
                "vendor", "reference", "depart_time", "arrive_time", "note"]}

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME = re.compile(r"^([01]\d|2[0-3]):[0-5]\d$")


def sniff(raw: bytes) -> str:
    """The real type of an upload, from its first bytes (the browser's label is not trusted)."""
    if raw[:3] == b"\xff\xd8\xff":
        return "image/jpeg"
    if raw[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if raw[:4] == b"RIFF" and raw[8:12] == b"WEBP":
        return "image/webp"
    if raw[:5] == b"%PDF-":
        return "application/pdf"
    return ""


def _text(v, n) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:n]


def clean(parsed) -> dict:
    """The model's answer as the page may show it. Nothing raises; a bad figure becomes 0."""
    p = parsed if isinstance(parsed, dict) else {}
    try:
        amount = Decimal(str(p.get("amount") or 0)).quantize(Decimal("0.01"))
    except (InvalidOperation, ValueError):
        amount = Decimal(0)
    if not (Decimal(0) < amount <= MAX_AMOUNT):
        amount = Decimal(0)
    cur = _text(p.get("currency"), 5).upper() or "PHP"
    if cur in ("PESO", "PESOS", "PHP", "P", "₱"):
        cur = "PHP"
    day = _text(p.get("date"), 10)
    try:
        if _DATE.match(day):
            date.fromisoformat(day)
        else:
            day = ""
    except ValueError:
        day = ""
    kind = p.get("kind") if p.get("kind") in KINDS else "other"
    readable = bool(p.get("readable")) and amount > 0
    return {"readable": readable, "kind": kind, "amount": float(amount), "currency": cur, "date": day,
            "origin": _text(p.get("origin"), 80), "destination": _text(p.get("destination"), 80),
            "vendor": _text(p.get("vendor"), 80), "reference": _text(p.get("reference"), 40),
            "depart_time": _hhmm(p.get("depart_time")), "arrive_time": _hhmm(p.get("arrive_time")),
            "note": _text(p.get("note"), 200)}


def _hhmm(v) -> str:
    v = _text(v, 5)
    return v if _TIME.match(v) else ""


async def read(conn, user, ip, raw: bytes, mime: str) -> dict:
    """One Gemini call over the file. Returns clean(); raises ai_core.AIError when AI is off, over
    budget or failing, so the caller can tell the person to type the amount."""
    result, _iid = await ai_core.ask_async(
        conn, user, FEATURE, PROMPT, ip=ip, system=SYSTEM, response_schema=SCHEMA,
        temperature=0.0, max_output_tokens=512, timeout=25.0, images=[(mime, raw)])
    return clean(result.get("parsed"))


# ---- the DPO and the Certificate of Appearance (read on upload, checked against the filing) ----------------
# Only the fields below are asked for, no names. The answer is checked against what the filing says and the
# person is told what does not match; none of it is stored.

DOC_RECEIPT, DOC_DPO, DOC_APPEARANCE = "receipt", "dpo", "appearance"
DOC_FOR = {**{c: DOC_RECEIPT for c in READ_CODES}, "dpo": DOC_DPO, "cert_appearance": DOC_APPEARANCE}

DPO_SYSTEM = (
    "You read a Philippine Department Personnel Order (DPO) that authorises official travel. Report only what "
    "is printed on it. Never guess. Do not copy any person's name. If the file is not a DPO or cannot be read, "
    "set readable to false."
)
DPO_PROMPT = (
    "Read this order. dpo_no is the order number as printed. dpo_date is the date the order was issued, "
    "YYYY-MM-DD. travel_start and travel_end are the first and last dates of travel it authorises, YYYY-MM-DD "
    "(leave empty if not shown). funding_stated is true only if the order names a funding source for the trip "
    "(for example a fund, project or budget line), false if it does not. funding is that funding source in a "
    "few words (empty if none). note is one short sentence on anything the person should double-check."
)
DPO_SCHEMA = {"type": "OBJECT", "properties": {
    "readable": {"type": "BOOLEAN"}, "dpo_no": {"type": "STRING"}, "dpo_date": {"type": "STRING"},
    "travel_start": {"type": "STRING"}, "travel_end": {"type": "STRING"}, "funding_stated": {"type": "BOOLEAN"},
    "funding": {"type": "STRING"}, "note": {"type": "STRING"},
}, "required": ["readable", "dpo_no", "dpo_date", "travel_start", "travel_end", "funding_stated", "funding", "note"]}

APPEAR_SYSTEM = (
    "You read a Philippine government Certificate of Appearance for official travel. Report only what is "
    "printed on it. Never guess. Do not copy any person's name. If the file is not such a certificate or cannot "
    "be read, set readable to false."
)
APPEAR_PROMPT = (
    "Read this certificate. date_from and date_to are the first and last dates the certificate says the person "
    "appeared or attended, YYYY-MM-DD (use the same date twice for a single day; leave empty if not shown). "
    "note is one short sentence on anything the person should double-check."
)
APPEAR_SCHEMA = {"type": "OBJECT", "properties": {
    "readable": {"type": "BOOLEAN"}, "date_from": {"type": "STRING"}, "date_to": {"type": "STRING"},
    "note": {"type": "STRING"},
}, "required": ["readable", "date_from", "date_to", "note"]}


def _day(v) -> str:
    v = _text(v, 10)
    try:
        return v if _DATE.match(v) and date.fromisoformat(v) else ""
    except ValueError:
        return ""


def clean_dpo(parsed) -> dict:
    p = parsed if isinstance(parsed, dict) else {}
    no = _text(p.get("dpo_no"), 60)
    return {"readable": bool(p.get("readable")) and bool(no), "dpo_no": no, "dpo_date": _day(p.get("dpo_date")),
            "travel_start": _day(p.get("travel_start")), "travel_end": _day(p.get("travel_end")),
            "funding_stated": bool(p.get("funding_stated")) and bool(_text(p.get("funding"), 80)),
            "funding": _text(p.get("funding"), 80), "note": _text(p.get("note"), 200)}


def clean_appearance(parsed) -> dict:
    p = parsed if isinstance(parsed, dict) else {}
    a, b = _day(p.get("date_from")), _day(p.get("date_to"))
    if a and not b:
        b = a
    if b and not a:
        a = b
    if a and b and b < a:
        a, b = b, a
    return {"readable": bool(p.get("readable")) and bool(a), "date_from": a, "date_to": b, "note": _text(p.get("note"), 200)}


async def read_doc(doc, conn, user, ip, raw: bytes, mime: str) -> dict:
    """The cleaned reading for one kind of upload (DOC_RECEIPT, DOC_DPO or DOC_APPEARANCE). Raises ai_core.AIError."""
    if doc == DOC_RECEIPT:
        return await read(conn, user, ip, raw, mime)
    system, prompt, schema, clean_fn = ((DPO_SYSTEM, DPO_PROMPT, DPO_SCHEMA, clean_dpo) if doc == DOC_DPO
                                        else (APPEAR_SYSTEM, APPEAR_PROMPT, APPEAR_SCHEMA, clean_appearance))
    result, _iid = await ai_core.ask_async(
        conn, user, FEATURE, prompt, ip=ip, system=system, response_schema=schema,
        temperature=0.0, max_output_tokens=512, timeout=25.0, images=[(mime, raw)])
    return clean_fn(result.get("parsed"))


def _key(no: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (no or "").upper())


def _fmt(d: str) -> str:
    try:
        return date.fromisoformat(d).strftime("%b %d, %Y").replace(" 0", " ")
    except ValueError:
        return d


def check(doc, reading: dict, filing) -> tuple:
    """(messages, fill) for a reading of the DPO or the Certificate of Appearance, set against the filing.
    messages are plain sentences for the person; fill is a DPO number / date to offer for the filing's own
    fields when they are empty or differ. A receipt reading has nothing to check here."""
    msgs, fill = [], None
    if doc == DOC_DPO:
        if not reading["readable"]:
            return ["Could not read a DPO number on that file, so nothing was checked."], None
        if not reading["funding_stated"]:
            msgs.append("The DPO does not seem to state the funding source. It must; ask for a corrected DPO.")
        if reading["dpo_no"] and not filing["dpo_no"]:
            fill = {"dpo_no": reading["dpo_no"], "dpo_date": reading["dpo_date"] if not filing["dpo_date"] else ""}
        elif reading["dpo_no"] and _key(reading["dpo_no"]) != _key(filing["dpo_no"]):
            msgs.append(f"The DPO reads {reading['dpo_no']}, but this filing says {filing['dpo_no']}.")
            fill = {"dpo_no": reading["dpo_no"], "dpo_date": reading["dpo_date"]}
        if reading["dpo_date"] and filing["dpo_date"] and reading["dpo_date"] != filing["dpo_date"]:
            msgs.append(f"The DPO is dated {_fmt(reading['dpo_date'])}, but this filing says {_fmt(filing['dpo_date'])}.")
            fill = {**(fill or {"dpo_no": ""}), "dpo_date": reading["dpo_date"]}
        elif reading["dpo_date"] and not filing["dpo_date"] and not fill:
            fill = {"dpo_no": "", "dpo_date": reading["dpo_date"]}
        a, b = reading["travel_start"], reading["travel_end"]
        if a and b and (filing["act_start"] < a or filing["act_end"] > b):
            msgs.append(f"The DPO covers {_fmt(a)} to {_fmt(b)}, but this activity runs {_fmt(filing['act_start'])} "
                        f"to {_fmt(filing['act_end'])}.")
    elif doc == DOC_APPEARANCE:
        if not reading["readable"]:
            return ["Could not read the dates on that certificate, so nothing was checked."], None
        a, b = reading["date_from"], reading["date_to"]
        if filing["act_start"] < a or filing["act_end"] > b:
            msgs.append(f"The certificate covers {_fmt(a)} to {_fmt(b)}, but this activity runs "
                        f"{_fmt(filing['act_start'])} to {_fmt(filing['act_end'])}.")
    if fill and not (fill.get("dpo_no") or fill.get("dpo_date")):
        fill = None
    return msgs, fill
