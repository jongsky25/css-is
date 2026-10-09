"""The printable meal request form for a conference room reservation (docs/ROOM_RESERVATION_PLAN.md R9).

A pure renderer, like wellness_register.py: `render_pdf(form)` takes the dict `rooms_meals.get_form` returns and
gives the bytes of a one-page A4 PDF; nothing here touches the database. The fields are the ones the Administrative
Section orders from: title of the activity, number of pax, special request for meals, and for breakfast, AM snack,
lunch and PM snack a yes/no with the requested delivery time."""
from __future__ import annotations
import io
import re
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

_INK, _SOFT, _LINE, _BAND = colors.HexColor("#1b2230"), colors.HexColor("#5a6473"), colors.HexColor("#9aa7bb"), colors.HexColor("#eef1f6")
_STATUS = {"pending": "Not yet requested", "requested": "Requested", "delivered": "Delivered",
           "not_delivered": "Not delivered", "cancelled": "Cancelled"}


def _p(text, size=10, bold=False, color=_INK, align=0, leading=None):
    style = ParagraphStyle("x", fontName="Helvetica-Bold" if bold else "Helvetica", fontSize=size, textColor=color,
                           alignment=align, leading=leading or size * 1.3)
    return Paragraph(escape(str(text)).replace("\n", "<br/>"), style)


def clock(hhmm):
    """'13:30' -> '1:30 PM'."""
    m = re.match(r"^(\d{1,2}):(\d{2})$", hhmm or "")
    if not m:
        return hhmm or "—"
    h = int(m.group(1))
    return f"{(h % 12) or 12}:{m.group(2)} {'AM' if h < 12 else 'PM'}"


def filename(form):
    ref = (form["reservation"].get("ref_code") or "meal-form").lower()
    return f"meal-request-{ref}.pdf"


def render_pdf(form):
    res = form["reservation"]
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=18 * mm, rightMargin=18 * mm, topMargin=16 * mm, bottomMargin=16 * mm,
                            title=f"Meal request form {res.get('ref_code', '')}", author="Office Connect")
    out = [_p("BUREAU OF LOCAL HEALTH SYSTEMS DEVELOPMENT", 8, color=_SOFT, align=1),
           Spacer(1, 2 * mm), _p("MEAL REQUEST FORM", 18, bold=True, align=1), Spacer(1, 1 * mm),
           _p(f"Conference room · Reference {res.get('ref_code', '')} · form version {form['version']}", 9, color=_SOFT, align=1),
           Spacer(1, 6 * mm)]

    def field(label, value, big=False):
        return [_p(label, 9, bold=True, color=_SOFT), _p(value if value not in (None, "") else "—", 12 if big else 10.5, bold=big)]

    when = f"{form['when']}, {form['hours']}"
    who = form["requester_name"] + (f" ({form['requester_unit']})" if form["requester_unit"] else "")
    rows = [field("1. Title of the Activity", form["title"], big=True),
            field("2. Number of Pax", form["pax"]),
            field("3. Special Request for Meals", form["special_request"] or "None"),
            field("Date and time of the activity", when + " · Conference room"),
            field("Requested by", who)]
    t = Table(rows, colWidths=[62 * mm, 112 * mm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LINEBELOW", (0, 0), (-1, -1), 0.5, _LINE),
                           ("TOPPADDING", (0, 0), (-1, -1), 5), ("BOTTOMPADDING", (0, 0), (-1, -1), 5)]))
    out += [t, Spacer(1, 7 * mm), _p("4. Meals", 11, bold=True), Spacer(1, 2 * mm)]

    head = [_p(x, 9, bold=True, color=colors.white) for x in ("Meal", "Needed?", "Requested delivery time", "For the Administrative Section")]
    body = [head]
    for i in form["items"]:
        yes = i["wanted"]
        status = _STATUS.get(i["status"], i["status"]) if yes else "—"
        if yes and i.get("status_at"):
            status += f"\n{i['status_at'][:10]}"
        body.append([_p(i["label"], 11, bold=True), _p("YES" if yes else "NO", 11, bold=yes, color=_INK if yes else _SOFT),
                     _p(clock(i["deliver_at"]) if yes else "—", 11), _p(status, 9.5, color=_INK if yes else _SOFT)])
    mt = Table(body, colWidths=[40 * mm, 24 * mm, 48 * mm, 62 * mm], repeatRows=1)
    mt.setStyle(TableStyle([("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1040a0")), ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                            ("GRID", (0, 0), (-1, -1), 0.5, _LINE), ("TOPPADDING", (0, 0), (-1, -1), 6), ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                            ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _BAND])]))
    out += [mt, Spacer(1, 6 * mm)]
    if res["status"] != "approved":
        out += [_p("The room booking has not been approved yet, so this order should not be placed until it is.", 9.5, bold=True, color=colors.HexColor("#9e6217")),
                Spacer(1, 4 * mm)]
    sig = Table([[_p("Requested by (signature over printed name)", 8.5, color=_SOFT), "",
                  _p("Received / ordered by (Administrative Section)", 8.5, color=_SOFT)]],
                colWidths=[80 * mm, 14 * mm, 80 * mm], rowHeights=[16 * mm])
    sig.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "BOTTOM"), ("LINEABOVE", (0, 0), (0, 0), 0.6, _INK),
                             ("LINEABOVE", (2, 0), (2, 0), 0.6, _INK), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0)]))
    out += [Spacer(1, 8 * mm), sig, Spacer(1, 8 * mm),
            _p(f"Prepared by Office Connect from the reservation {res.get('ref_code', '')}. Last updated {form['updated_at'][:16].replace('T', ' ')}.", 8, color=_SOFT, align=1)]
    doc.build(out)
    return buf.getvalue()
