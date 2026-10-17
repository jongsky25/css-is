"""What the AI read off a filing's uploads, kept so the prepare page can draft Appendix A and B from it.

A reading is the small structured answer from `travel_scan` (kind, amount, date, route, vendor, reference,
times) or, for the Certificate of Appearance, the dates it covers. The file itself is never kept here.
Readings belong to one upload row: removing or replacing that upload forgets its readings, and retention
removes them with the filing. Nothing here decides a claim: the prepare page shows each drafted entry with
where it came from, and the person confirms it.

The draft functions are pure; only save / forget / for_filing touch the database."""
from __future__ import annotations
from datetime import date

import tzutil as tz
import travel_checklist as tc

# Upload rows whose reading becomes an Appendix A entry (a ride with a fare), and the mode it is.
RIDE_MODE = {"plane_ticket": "plane", "boat_bus_ticket": "bus", "taxi_receipt": "taxi", "ridehail_receipt": "tnvs"}
SEA_WORDS = ("ferry", "boat", "ship", "shipping", "roro", "ro-ro", "fastcraft", "lines", "2go")
_COLS = ("id", "item_code", "doc", "kind", "amount", "currency", "day", "origin", "destination", "vendor",
         "reference", "dep_time", "arr_time", "date_from", "date_to")


def save(conn, filing_id, code, doc, reading) -> bool:
    """Keep one readable reading for an upload row. A pesos receipt needs an amount; a certificate needs its
    dates. The same reading twice (same row, amount, date, vendor, reference) is kept once. True when stored."""
    if not isinstance(reading, dict) or not reading.get("readable"):
        return False
    if doc == "appearance":
        a, b = reading.get("date_from") or "", reading.get("date_to") or ""
        if not a:
            return False
        row = (filing_id, code, "appearance", None, None, None, None, None, None, None, None, None, None, a, b or a)
        dup = conn.execute("SELECT 1 FROM travel_reading WHERE filing_id=? AND item_code=? AND doc='appearance' "
                           "AND date_from=? AND date_to=?", (filing_id, code, a, b or a)).fetchone()
    elif doc == "receipt":
        if reading.get("currency") != "PHP" or not (reading.get("amount") or 0) > 0:
            return False
        row = (filing_id, code, "receipt", reading.get("kind"), float(reading["amount"]), "PHP", reading.get("date") or None,
               reading.get("origin") or None, reading.get("destination") or None, reading.get("vendor") or None,
               reading.get("reference") or None, reading.get("depart_time") or None, reading.get("arrive_time") or None,
               None, None)
        dup = conn.execute("SELECT 1 FROM travel_reading WHERE filing_id=? AND item_code=? AND doc='receipt' AND amount=? "
                           "AND COALESCE(day,'')=? AND COALESCE(vendor,'')=? AND COALESCE(reference,'')=?",
                           (filing_id, code, float(reading["amount"]), reading.get("date") or "", reading.get("vendor") or "",
                            reading.get("reference") or "")).fetchone()
    else:
        return False
    if dup:
        return False
    conn.execute("INSERT INTO travel_reading(filing_id, item_code, doc, kind, amount, currency, day, origin, destination, "
                 "vendor, reference, dep_time, arr_time, date_from, date_to, created_at) "
                 "VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)", (*row, tz.now_iso()))
    conn.commit()
    return True


def forget(conn, filing_id, code=None):
    """Drop the readings of one upload row (its files were removed or replaced), or of the whole filing."""
    if code is None:
        conn.execute("DELETE FROM travel_reading WHERE filing_id=?", (filing_id,))
    else:
        conn.execute("DELETE FROM travel_reading WHERE filing_id=? AND item_code=?", (filing_id, code))
    conn.commit()


def for_filing(conn, filing_id) -> list:
    cur = conn.execute(f"SELECT {', '.join(_COLS)} FROM travel_reading WHERE filing_id=? ORDER BY id", (filing_id,))
    return [dict(zip(_COLS, r)) for r in cur.fetchall()]


# ------------------------------------------------------------------------------------------ Appendix A ---

def _mode_of(r) -> str:
    code = r["item_code"]
    mode = RIDE_MODE.get(code, "")
    if code == "boat_bus_ticket" and any(w in (r.get("vendor") or "").lower() for w in SEA_WORDS):
        mode = "boat"
    return mode


def _is_blank(row) -> bool:
    return row["mode"] == "none" and not row["allowance"] and not row["from"] and not row["to"]


def draft_rows(rows, readings) -> list:
    """The itinerary rows with a ride entered for every ticket or receipt that was read. Each drafted entry
    carries `rid` (the reading it came from) and `src` (a sentence saying where it came from) so the page can
    show it and not draw it twice. A reading goes on the blank row of its own date; a second ride on a date
    gets its own entry right after (with no per diem, since a day's is claimed once); a reading with no date, or
    a date outside the trip, goes at the end. A boarding pass is skipped when an e-ticket was read: they are the
    same flight."""
    out = [dict(r) for r in rows]
    have_ticket = any(x["item_code"] == "plane_ticket" and x["doc"] == "receipt" for x in readings)
    rides = [x for x in readings if x["doc"] == "receipt" and _mode_of(x) and not (x["item_code"] == "boarding_pass" and have_ticket)]
    rides += [x for x in readings if x["doc"] == "receipt" and x["item_code"] == "boarding_pass" and not have_ticket]
    rides.sort(key=lambda x: (x["day"] or "9999-99-99", x["dep_time"] or "99:99", x["id"]))
    for x in rides:
        mode = _mode_of(x) or ("plane" if x["item_code"] == "boarding_pass" else "")
        if not mode:
            continue
        label = tc.BY_CODE[x["item_code"]].label if x["item_code"] in tc.BY_CODE else "Upload"
        entry = {"from": x["origin"] or "", "to": x["destination"] or "", "dep": x["dep_time"] or "", "arr": x["arr_time"] or "",
                 "mode": mode, "receipt": "receipt" if mode in ("taxi", "tnvs") else "none", "allowance": x["amount"],
                 "rid": x["id"],
                 "src": f"Drafted from your upload: {label}" + (f" ({x['vendor']})" if x["vendor"] else "") + ". Check it."}
        same_day = [i for i, r in enumerate(out) if r["date"] and r["date"] == x["day"]]
        target = next((i for i in same_day if _is_blank(out[i])), None)
        if target is not None:
            out[target].update(entry)
        elif same_day:
            extra = {**out[same_day[0]], **entry, "per_diem": 0, "day_kind": "", "basis": "", "place": "", "km": 0,
                     "lodging_provided": False, "meals_provided": False, "route_type": ""}
            out.insert(same_day[-1] + 1, extra)
        else:
            base = dict(out[0]) if out else {}
            base.update({k: v for k, v in (("date", x["day"] or ""),) if v is not None})
            base.update(entry)
            base.update({"per_diem": 0, "day_kind": "", "basis": "", "place": "", "km": 0, "route_type": "",
                         "lodging_provided": False, "meals_provided": False})
            out.append(base)
    return out


# ------------------------------------------------------------------------------------------ Appendix B ---

def _span(a: str, b: str) -> str:
    def f(d):
        try:
            return date.fromisoformat(d).strftime("%B %d, %Y").replace(" 0", " ")
        except ValueError:
            return d
    return f(a) if a == b else f"{f(a)} to {f(b)}"


def completion_defaults(filing, readings) -> dict:
    """Suggested answers for the Certificate of Travel Completed from what was read: how the travel went (from the
    dates on the Certificate of Appearance against the activity's) and, for a liquidation with a refund, the refund
    receipt. Only keys with something to suggest are returned; the person can change every one."""
    out = {}
    cert = [x for x in readings if x["doc"] == "appearance"]
    if cert:
        a, b = min(x["date_from"] for x in cert), max(x["date_to"] for x in cert)
        s, e = filing["act_start"], filing["act_end"]
        if (a, b) == (s, e):
            out["strictness"] = "strict"
        else:
            kind = "cut" if (a >= s and b <= e) else "extended" if (a <= s and b >= e) else "other"
            out["strictness"] = kind
            out["explanation"] = (f"The Certificate of Appearance covers {_span(a, b)}, while the activity ran {_span(s, e)}.")
    refund = next((x for x in reversed(readings) if x["item_code"] == "refund_or" and x["doc"] == "receipt"), None)
    if refund and filing["kind"] == "liquidation":
        out["refund_amount"] = f"{refund['amount']:.2f}"
        if refund["reference"]:
            out["refund_or_no"] = refund["reference"]
        if refund["day"]:
            out["refund_or_date"] = refund["day"]
    return out
