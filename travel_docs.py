"""Travel filing document helpers: text formatters now, payload builders in a later increment."""
from __future__ import annotations
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

MONTHS = ("January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December")

_ONES = ("", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine", "Ten", "Eleven",
         "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen", "Seventeen", "Eighteen", "Nineteen")
_TENS = ("", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety")
_SCALES = ((10 ** 9, "Billion"), (10 ** 6, "Million"), (1000, "Thousand"))


def _d(v) -> date:
    return v if isinstance(v, date) else date.fromisoformat(str(v))


def date_range(start, end) -> str:
    """Zero-padded range as the official forms print it: 'September 01-04, 2026'."""
    s, e = _d(start), _d(end)
    if e < s:
        s, e = e, s
    if s == e:
        return f"{MONTHS[s.month - 1]} {s.day:02d}, {s.year}"
    if (s.year, s.month) == (e.year, e.month):
        return f"{MONTHS[s.month - 1]} {s.day:02d}-{e.day:02d}, {s.year}"
    if s.year == e.year:
        return f"{MONTHS[s.month - 1]} {s.day:02d} - {MONTHS[e.month - 1]} {e.day:02d}, {s.year}"
    return (f"{MONTHS[s.month - 1]} {s.day:02d}, {s.year} - "
            f"{MONTHS[e.month - 1]} {e.day:02d}, {e.year}")


def _below_thousand(n: int) -> str:
    words = []
    if n >= 100:
        words.append(_ONES[n // 100] + " Hundred")
        n %= 100
    if n >= 20:
        words.append(_TENS[n // 10])
        n %= 10
    if n:
        words.append(_ONES[n])
    return " ".join(w for w in words if w)


def _int_words(n: int) -> str:
    if n == 0:
        return "Zero"
    parts = []
    for size, name in _SCALES:
        if n >= size:
            parts.append(_below_thousand(n // size) + " " + name)
            n %= size
    if n:
        parts.append(_below_thousand(n))
    return " ".join(parts)


def peso_words(amount) -> str:
    """'Four Hundred Fifty Pesos', 'Five Hundred Fifty Pesos and 50/100'."""
    amt = Decimal(str(amount)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amt < 0:
        raise ValueError("An amount in words cannot be negative.")
    pesos, centavos = int(amt), int((amt - int(amt)) * 100)
    out = f"{_int_words(pesos)} {'Peso' if pesos == 1 else 'Pesos'}"
    return f"{out} and {centavos:02d}/100" if centavos else out


def money(amount) -> str:
    """'1,060' for a whole amount, '1,060.50' otherwise."""
    amt = Decimal(str(amount or 0)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return f"{amt:,.0f}" if amt == amt.to_integral_value() else f"{amt:,.2f}"


# ===================================================================== T5 ===
# Payload builders. Nothing here is saved: the prepare page posts the edited values, we build the
# relay payloads in memory and throw them away once the documents are made.

import re
from dataclasses import dataclass, field
from decimal import InvalidOperation

import travel_rules as tr

MODES = ("taxi", "tnvs", "public_noreceipt", "van_doh", "plane", "bus", "boat", "own", "govt", "none")
MODE_LABELS = {"taxi": "Taxi", "tnvs": "TNVS", "public_noreceipt": "Public transport", "van_doh": "DOH van",
               "plane": "Plane", "bus": "Bus", "boat": "Boat", "own": "Private vehicle",
               "govt": "Government vehicle", "none": ""}
MAX_ROWS, MAX_DAYS = 40, 62
DOC_TEMPLATES = {"appendix_a": "appendix_a", "appendix_b": "appendix_b", "mc114_justification": "mc114_justification",
                 "jo_cert": "jo_cert", "travel_report": "travel_report", "cenrr": "cenrr", "rer": "rer"}
DOC_TITLES = {"appendix_a": "Appendix A - Itinerary of Travel", "appendix_b": "Appendix B - Certificate of Travel Completed",
              "mc114_justification": "MC 114 justification", "jo_cert": "Certification for Job Order",
              "travel_report": "Post Travel Report", "cenrr": "CENRR", "rer": "RER"}
DM_CITATION = "DM No. 2025-0202, as amended by DM Nos. 2025-0202-A and 2025-0202-B"
REQUEST_PHRASE = {"ca": "cash advance", "liquidation": "liquidation", "reimbursement": "reimbursement"}
STRICTNESS = ("strict", "cut", "extended", "other")
SIGNATORY_KEYS = ("head_name", "head_title", "station", "certifier_name", "certifier_title", "approver_name",
                  "approver_title", "noted_by_name", "noted_by_title", "reviewed_by_name", "reviewed_by_title",
                  "approved_by_name", "approved_by_title", "prepared_by", "signatory_name", "signatory_title")
TEXT_KEYS = ("purpose", "explanation", "refund_amount", "refund_or_no", "refund_or_date", "overview",
             "key_points", "contributions", "support_needed", "recommendations", "conclusion", "activities",
             "obligations", "itinerary_no")


@dataclass
class DocPayload:
    item_code: str
    template_key: str
    title: str
    fields: dict = field(default_factory=dict)
    blocks: dict = field(default_factory=dict)       # name -> [paragraph, ...]
    rows: dict = field(default_factory=dict)         # name -> {"marker": "r_date", "data": [{...}, ...]}
    index: int = 1                                   # 1-based position among documents of the same item (RER)


def long_date(v) -> str:
    d = _d(v)
    return f"{MONTHS[d.month - 1]} {d.day}, {d.year}"


def _txt(v, n=600) -> str:
    return " ".join(str(v or "").split())[:n]


def _para(v, n=3000) -> list:
    """Free text to relay paragraphs: blank lines and over-long input are trimmed, never raised."""
    lines = [_txt(x, 800) for x in str(v or "").replace("\r", "").split("\n")]
    out = [x for x in lines if x]
    return out[:60] if sum(map(len, out)) <= n * 4 else out[:20]


def _amt(v) -> Decimal:
    try:
        d = Decimal(str(v if v not in (None, "") else 0).replace(",", ""))
    except (InvalidOperation, ValueError):
        return Decimal(0)
    return d if d > 0 and d < Decimal("10000000") else Decimal(0)


def _iso(v) -> str:
    try:
        return date.fromisoformat(str(v or "").strip()[:10]).isoformat()
    except ValueError:
        return ""


def trip_days(start, end) -> list:
    s, e = _d(start), _d(end)
    if e < s:
        s, e = e, s
    out, cur = [], s
    while cur <= e and len(out) < MAX_DAYS:
        out.append(cur)
        cur = date.fromordinal(cur.toordinal() + 1)
    return out


def dpo_ref(filing) -> str:
    no, dt = (filing.get("dpo_no") or "").strip(), filing.get("dpo_date")
    if no and dt:
        return f"DPO No. {no} dated {long_date(dt)}"
    return f"DPO No. {no}" if no else "the Department Personnel Order"


def fill_tokens(text, filing, profile) -> str:
    """The MC 114 library tokens."""
    rep = {"traveler_name": profile.get("person_name") or profile.get("username") or "",
           "activity_title": filing.get("act_title") or "",
           "dates": date_range(filing["act_start"], filing["act_end"]), "venue": filing.get("act_venue") or ""}
    return re.sub(r"\{\{(traveler_name|activity_title|dates|venue)\}\}", lambda m: rep[m.group(1)], text or "")


def _library_text(conn, filing) -> str:
    fmt = filing.get("mc114_format")
    if fmt not in ("separate", "appendix_b"):
        return ""
    r = conn.execute("SELECT body FROM travel_justification WHERE active=1 AND format=? ORDER BY id LIMIT 1", (fmt,)).fetchone()
    return r[0] if r else ""


def _division(profile) -> str:
    path = (profile.get("org_path") or "").strip("/ ")
    return path.split("/")[-1] if path else ""


def defaults(conn, filing, profile, settings) -> dict:
    """What the prepare page starts with. `settings` is {'head_name': ..., 'certifier_name': ...}."""
    name = profile.get("person_name") or profile.get("username") or ""
    desig = profile.get("designation") or ""
    sig = {k: "" for k in SIGNATORY_KEYS}
    sig.update(head_name=settings.get("head_name", ""), head_title=settings.get("head_title", ""),
               station=settings.get("station", ""), certifier_name=settings.get("certifier_name", ""),
               certifier_title=settings.get("certifier_title", ""), prepared_by=name,
               approver_name=settings.get("head_name", ""), approver_title=settings.get("head_title", ""),
               noted_by_name=settings.get("head_name", ""), noted_by_title=settings.get("head_title", ""),
               approved_by_name=settings.get("head_name", ""), approved_by_title=settings.get("head_title", ""),
               signatory_name=settings.get("head_name", ""), signatory_title=settings.get("head_title", ""))
    days = trip_days(filing["act_start"], filing["act_end"])
    rows = [{"date": d.isoformat(), "from": "", "to": "", "dep": "", "arr": "", "mode": "none", "route_type": "",
             "receipt": "none", "allowance": 0, "per_diem": 0} for d in days]
    dates = date_range(filing["act_start"], filing["act_end"])
    texts = {k: "" for k in TEXT_KEYS}
    texts.update(purpose=f"attend {filing['act_title']}", strictness="strict",
                 activities=f"{filing['act_title']} on {dates}" + (f" at {filing['act_venue']}" if filing.get("act_venue") else ""),
                 day_by_day=[f"{long_date(d)}: " for d in days])
    return {"rows": rows, "texts": texts, "signatories": sig,
            "mc114_text": fill_tokens(_library_text(conn, filing), filing, profile),
            "traveler": {"name": name, "designation": desig, "employee_no": profile.get("employee_no") or ""},
            "modes": [[m, MODE_LABELS[m] or "No travel"] for m in MODES]}


def normalize(posted) -> dict:
    """Clean what the prepare page posted. Unknown keys are dropped; nothing raises."""
    posted = posted if isinstance(posted, dict) else {}
    rows = []
    for r in (posted.get("rows") if isinstance(posted.get("rows"), list) else [])[:MAX_ROWS]:
        if not isinstance(r, dict):
            continue
        mode = r.get("mode") if r.get("mode") in MODES else "none"
        rows.append({"date": _iso(r.get("date")), "from": _txt(r.get("from"), 80), "to": _txt(r.get("to"), 80),
                     "dep": _txt(r.get("dep"), 12), "arr": _txt(r.get("arr"), 12), "mode": mode,
                     "route_type": _txt(r.get("route_type"), 40),
                     "receipt": "receipt" if r.get("receipt") == "receipt" else "none",
                     "allowance": _amt(r.get("allowance")), "per_diem": _amt(r.get("per_diem"))})
    t = posted.get("texts") if isinstance(posted.get("texts"), dict) else {}
    texts = {k: (_txt(t.get(k), 3000) if k in ("itinerary_no", "refund_amount", "refund_or_no", "refund_or_date")
                 else str(t.get(k) or "")[:6000]) for k in TEXT_KEYS}
    texts["strictness"] = t.get("strictness") if t.get("strictness") in STRICTNESS else "strict"
    dbd = t.get("day_by_day")
    texts["day_by_day"] = [_txt(x, 1500) for x in dbd][:MAX_DAYS] if isinstance(dbd, list) else []
    s = posted.get("signatories") if isinstance(posted.get("signatories"), dict) else {}
    return {"rows": rows, "texts": texts, "mc114_text": str(posted.get("mc114_text") or "")[:6000],
            "sig": {k: _txt(s.get(k), 120) for k in SIGNATORY_KEYS}}


def rides_of(rows, ceilings) -> list:
    """[(row, key, RideResult)] for every row that is a taxi / TNVS / public-transport ride with a fare."""
    out = []
    for key, row in zip(tr.row_keys(rows), rows):
        res = tr.ride_check(row["mode"], row["route_type"], row["allowance"], row["receipt"], ceilings, key)
        if res.kind:
            out.append((row, key, res))
    return out


def ride_answers(rows, ceilings) -> dict:
    kinds = {res.kind for _r, _k, res in rides_of(rows, ceilings)}
    return {"rides_cenrr": 1 if "cenrr" in kinds else 0, "rides_rer": 1 if "rer" in kinds else 0}


def _m(d) -> str:
    return money(d)


def _leg(row) -> str:
    return " to ".join(x for x in (row["from"], row["to"]) if x) or "local travel"


def _appendix_a(ctx) -> DocPayload:
    f, n, sig = ctx["filing"], ctx["name"], ctx["sig"]
    data, grand = [], Decimal(0)
    for r in ctx["rows"]:
        total = r["allowance"] + r["per_diem"]
        grand += total
        data.append({"r_date": long_date(r["date"]) if r["date"] else "", "r_place": _leg(r), "r_dep": r["dep"],
                     "r_arr": r["arr"], "r_mode": MODE_LABELS[r["mode"]], "r_allowance": _m(r["allowance"]) if r["allowance"] else "",
                     "r_perdiem": _m(r["per_diem"]) if r["per_diem"] else "", "r_total": _m(total) if total else ""})
    purpose = (f"To {ctx['texts']['purpose'].strip() or 'attend ' + f['act_title']} on "
               f"{date_range(f['act_start'], f['act_end'])}" + (f" at {f['act_venue']}" if f.get("act_venue") else "")
               + f" as per {dpo_ref(f)}")
    return DocPayload("appendix_a", "appendix_a", ctx["title"]("appendix_a"), {
        "traveler_name": n, "purpose": purpose, "itinerary_no": ctx["texts"]["itinerary_no"], "grand_total": _m(grand),
        "certifier_name": sig["certifier_name"], "certifier_title": sig["certifier_title"],
        "prepared_by": sig["prepared_by"] or n, "approver_name": sig["approver_name"], "approver_title": sig["approver_title"]},
        rows={"itinerary": {"marker": "r_date", "data": data}})


def _evidence(items) -> list:
    return [f"{i + 1}. {it['label']}" for i, it in enumerate(
        x for x in items if x["handling"] != "fmis" and x["state"] == "present" or (x["handling"] == "generate" and x.get("doc_url")))]


def _appendix_b(ctx) -> DocPayload:
    f, n, sig, t = ctx["filing"], ctx["name"], ctx["sig"], ctx["texts"]
    lines = _para(t["explanation"])
    if f.get("mc114_format") == "appendix_b" and ctx["mc114_text"].strip():
        lines += ["Justification (MC 114):"] + _para(ctx["mc114_text"])
    chk = lambda k: "☒" if t["strictness"] == k else "☐"                      # noqa: E731
    return DocPayload("appendix_b", "appendix_b", ctx["title"]("appendix_b"), {
        "date": long_date(ctx["today"]), "head_name": sig["head_name"], "head_title": sig["head_title"], "station": sig["station"],
        "itinerary_ref": f"Appendix A, {date_range(f['act_start'], f['act_end'])}",
        "chk_strict": chk("strict"), "chk_cut": chk("cut"), "chk_extended": chk("extended"), "chk_other": chk("other"),
        "refund_amount": t["refund_amount"], "refund_or_no": t["refund_or_no"], "refund_or_date": t["refund_or_date"],
        "traveler_name": n, "traveler_designation": ctx["designation"],
        "approver_name": sig["approver_name"], "approver_title": sig["approver_title"]},
        blocks={"explanation": lines, "evidence_list": _evidence(ctx["items"])})


def _mc114(ctx) -> DocPayload:
    f, sig = ctx["filing"], ctx["sig"]
    body = _para(fill_tokens(ctx["mc114_text"], f, ctx["profile"]))
    return DocPayload("mc114_justification", "mc114_justification", ctx["title"]("mc114_justification"), {
        "traveler_name": ctx["name"], "traveler_position": ctx["designation"], "unit": _division(ctx["profile"]),
        "dates": date_range(f["act_start"], f["act_end"]), "dpo_ref": dpo_ref(f),
        "approver_name": sig["approver_name"], "approver_title": sig["approver_title"]}, blocks={"body": body})


def _jo_cert(ctx) -> DocPayload:
    f, sig, t = ctx["filing"], ctx["sig"], ctx["texts"]
    return DocPayload("jo_cert", "jo_cert", ctx["title"]("jo_cert"), {
        "date": long_date(ctx["today"]), "traveler_name": ctx["name"], "request_phrase": REQUEST_PHRASE[f["kind"]],
        "dm_citation": DM_CITATION, "signatory_name": sig["signatory_name"], "signatory_title": sig["signatory_title"]},
        blocks={"activities": _para(t["activities"]), "obligations": _para(t["obligations"])})


def _travel_report(ctx) -> DocPayload:
    f, sig, t = ctx["filing"], ctx["sig"], ctx["texts"]
    days = [x for x in t["day_by_day"] if x.strip()] or [f"{long_date(d)}:" for d in trip_days(f["act_start"], f["act_end"])]
    block = lambda k: _para(t[k])                                                         # noqa: E731
    return DocPayload("travel_report", "travel_report", ctx["title"]("travel_report"), {
        "name_designation": f"{ctx['name']}, {ctx['designation']}" if ctx["designation"] else ctx["name"],
        "travel_dates": date_range(f["act_start"], f["act_end"]), "dpo_ref": dpo_ref(f),
        "submitted_by_name": sig["prepared_by"] or ctx["name"], "submitted_by_title": ctx["designation"],
        "reviewed_by_name": sig["reviewed_by_name"], "reviewed_by_title": sig["reviewed_by_title"],
        "approved_by_name": sig["approved_by_name"], "approved_by_title": sig["approved_by_title"]},
        blocks={"overview": block("overview"), "day_by_day": days, "key_points": block("key_points"),
                "contributions": block("contributions"), "support_needed": block("support_needed"),
                "recommendations": block("recommendations"), "conclusion": block("conclusion")})


def _cenrr(ctx) -> list:
    rides = [(r, k) for r, k, res in rides_of(ctx["rows"], ctx["ceilings"]) if res.kind == "cenrr"]
    if not rides:
        return []
    sig, total = ctx["sig"], Decimal(0)
    data = []
    for r, _k in rides:
        total += r["allowance"]
        data.append({"p_date": long_date(r["date"]) if r["date"] else "",
                     "p_text": f"Fare from {_leg(r)} by {MODE_LABELS[r['mode']].lower()}", "p_amount": _m(r["allowance"])})
    return [DocPayload("cenrr", "cenrr", ctx["title"]("cenrr"), {
        "employee_name": ctx["name"], "employee_no": ctx["profile"].get("employee_no") or "", "office": sig["station"],
        "division": _division(ctx["profile"]), "total": _m(total), "purpose": f"attend {ctx['filing']['act_title']}",
        "printed_name": ctx["name"], "designation": ctx["designation"],
        "noted_by_name": sig["noted_by_name"], "noted_by_title": sig["noted_by_title"]},
        rows={"items": {"marker": "p_date", "data": data}})]


def _rers(ctx) -> list:
    out = []
    for r, _k, res in rides_of(ctx["rows"], ctx["ceilings"]):
        if res.kind != "rer":
            continue
        out.append(DocPayload("rer", "rer", ctx["title"]("rer"), {
            "payee_name": ctx["name"], "payee_designation": ctx["designation"], "amount_words": peso_words(r["allowance"]),
            "amount_figures": _m(r["allowance"]), "ride_from": r["from"], "ride_to": r["to"],
            "ride_date": long_date(r["date"]) if r["date"] else "", "purpose": f"attend {ctx['filing']['act_title']}"},
            index=len(out) + 1))
    return out


_BUILDERS = {"appendix_a": lambda c: [_appendix_a(c)], "appendix_b": lambda c: [_appendix_b(c)],
             "mc114_justification": lambda c: [_mc114(c)], "jo_cert": lambda c: [_jo_cert(c)],
             "travel_report": lambda c: [_travel_report(c)], "cenrr": _cenrr, "rer": _rers}


def build_payloads(kind, filing, profile, settings, posted, codes, *, ceilings, items=(), today=None) -> list:
    """The relay payloads for the requested generate-items, in checklist order. `posted` is what the
    prepare page sent; `items` the filing's checklist rows (for the evidence list in Appendix B)."""
    p = normalize(posted)
    sig = {**{k: "" for k in SIGNATORY_KEYS}, **p["sig"]}
    for k in ("head_name", "head_title", "station", "certifier_name", "certifier_title"):
        sig[k] = sig[k] or settings.get(k, "")
    for k in ("approver", "noted_by", "approved_by", "signatory"):          # default to the head of office
        sig[k + "_name"] = sig[k + "_name"] or sig["head_name"]
        sig[k + "_title"] = sig[k + "_title"] or sig["head_title"]
    name = profile.get("person_name") or profile.get("username") or ""
    ctx = {"filing": filing, "profile": profile, "name": name, "designation": profile.get("designation") or "",
           "rows": p["rows"], "texts": p["texts"], "sig": sig, "mc114_text": p["mc114_text"], "ceilings": ceilings,
           "items": list(items), "today": today or date.today(),
           "title": lambda code: f"{DOC_TITLES[code]} - {filing['ref_code']}"}
    out = []
    for code in DOC_TEMPLATES:
        if code in codes:
            out.extend(_BUILDERS[code](ctx))
    return out
