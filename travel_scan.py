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
         "terminal_fee", "lodging_bill", "other")
MAX_AMOUNT = Decimal("1000000")
# Checklist rows whose uploads are tickets or receipts: an upload to one of these is also read for its amount.
READ_CODES = frozenset({"plane_ticket", "boarding_pass", "boat_bus_ticket", "terminal_fee", "taxi_receipt",
                        "ridehail_receipt", "lodging_bill", "extra_expense_invoice"})

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
    "number. note is one short sentence on anything the person should double-check."
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
    "note": {"type": "STRING"},
}, "required": ["readable", "kind", "amount", "currency", "date", "origin", "destination",
                "vendor", "reference", "note"]}

_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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
            "note": _text(p.get("note"), 200)}


async def read(conn, user, ip, raw: bytes, mime: str) -> dict:
    """One Gemini call over the file. Returns clean(); raises ai_core.AIError when AI is off, over
    budget or failing, so the caller can tell the person to type the amount."""
    result, _iid = await ai_core.ask_async(
        conn, user, FEATURE, PROMPT, ip=ip, system=SYSTEM, response_schema=SCHEMA,
        temperature=0.0, max_output_tokens=512, timeout=25.0, images=[(mime, raw)])
    return clean(result.get("parsed"))
