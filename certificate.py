"""
Certificate of Appearance — an optional, auto-generated artifact for a registered
participant who has COMPLETED an activity's feedback (CSS). Faithful to the
DOH–BLHSD template (certificate of appearance PPT.pptx): Republic of the
Philippines / Department of Health / BUREAU OF LOCAL HEALTH SYSTEMS DEVELOPMENT
masthead + DOH seal, a "CERTIFICATE OF APPEARANCE" title, a certify sentence
built from the activity record, an "Issued this …" line, and a signatory pulled
from the directory (name, title, and — if uploaded — a signature image).

Issued as PDF only — an official certificate is never handed out in an editable
form:
  * render_pdf   — a print-ready, locked PDF (reportlab), the official copy.

Field data comes from app: the event row (title/date/venue/modality/verb), the
attendee name, and a signatory dict from storage.get_signatory().
"""
from __future__ import annotations

import io
import os
import re
from datetime import date, datetime

_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
_LOGO = os.path.join(_ASSETS, "cert_doh_logo.png")

_MASTHEAD = ["Republic of the Philippines", "Department of Health",
             "BUREAU OF LOCAL HEALTH SYSTEMS DEVELOPMENT",
             "San Lazaro Compound, Sta. Cruz, Manila"]

# Verb -> the phrase that precedes the activity title in the certify sentence.
_VERB_PHRASE = {
    "attended": "attended the",
    "appeared at": "appeared at the",
    "conducted": "conducted the",
    "participated in": "participated in the",
}

_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]


def _ordinal(n: int) -> str:
    if 10 <= n % 100 <= 20:
        suf = "th"
    else:
        suf = {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suf}"


def _parse_date(s):
    """'YYYY-MM-DD' -> a date, or None."""
    if not s:
        return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", s.strip())
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def _long_date(d):
    return f"{_MONTHS[d.month - 1]} {d.day}, {d.year}" if d else ""


def _long_date_range(a, b):
    """A single 'June 16, 2026', or 'June 16–18, 2026' for a multi-day activity.
    Collapses a shared month/year; widens across months and years as needed."""
    if not a:
        return ""
    if not b or b <= a:
        return _long_date(a)
    if (a.year, a.month) == (b.year, b.month):
        return f"{_MONTHS[a.month - 1]} {a.day}–{b.day}, {a.year}"
    if a.year == b.year:
        return f"{_MONTHS[a.month - 1]} {a.day} – {_MONTHS[b.month - 1]} {b.day}, {a.year}"
    return f"{_long_date(a)} – {_long_date(b)}"


def _fields(event, attendee_name, signatory, issue_date=None):
    """Build every filled string the certificate needs. `event` is a storage
    event dict; `signatory` is a storage.get_signatory() dict (or None)."""
    issue_date = issue_date or date.today()
    name = (attendee_name or "").strip() or "________________"
    title = (event.get("title") or "the activity").strip()
    verb = _VERB_PHRASE.get(event.get("certificate_verb") or "attended",
                            "attended the")

    ev_date = _parse_date(event.get("event_date"))
    held_on = _long_date_range(ev_date, _parse_date(event.get("end_date")))
    venue = (event.get("venue") or "").strip()
    online = (event.get("modality") or "f2f") == "online"

    # Compose the place/date clause, gracefully dropping any blank part.
    clause = []
    if held_on:
        clause.append(f"held on {held_on}")
    if venue:
        clause.append(("via " if online else "at ") + venue)
    place_date = (", " + ", ".join(clause)) if clause else ""

    body = (f"This is to certify that {name} {verb} {title}{place_date}. "
            "This certification is issued upon the request of the above-named "
            "individual for whatever legal purpose it may serve.")

    issued = (f"Issued this {_ordinal(issue_date.day)} day of "
              f"{_MONTHS[issue_date.month - 1]}, {issue_date.year}.")

    sig = signatory or {}
    return {
        "masthead": _MASTHEAD,
        "title": "CERTIFICATE OF APPEARANCE",
        "name": name,
        "body": body,
        "issued": issued,
        "signatory": (sig.get("display_name") or "").strip(),
        "signatory_title": (sig.get("title") or "").strip(),
        "signature_bytes": sig.get("signature_bytes"),
        "signature_mime": sig.get("signature_mime"),
    }


def filename(event, attendee_name, ext):
    """A safe download filename: Certificate-<lastword-of-name>-<event>.<ext>."""
    who = re.sub(r"[^A-Za-z0-9]+", "", (attendee_name or "").split()[-1:][0] if attendee_name else "") or "participant"
    ev = re.sub(r"[^A-Za-z0-9]+", "-", (event.get("title") or "activity")).strip("-")[:40] or "activity"
    return f"Certificate-{who}-{ev}.{ext}"


# ---------------------------------------------------------------------
# PDF — the official, print-ready copy (reportlab)
# ---------------------------------------------------------------------

def render_pdf(event, attendee_name, signatory, issue_date=None) -> bytes:
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib.units import mm
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Paragraph, Frame
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_JUSTIFY, TA_CENTER
    from reportlab.lib import colors

    f = _fields(event, attendee_name, signatory, issue_date)
    buf = io.BytesIO()
    W, H = landscape(A4)
    c = canvas.Canvas(buf, pagesize=(W, H))

    # Decorative double border.
    c.setStrokeColor(colors.HexColor("#1f4e79"))
    c.setLineWidth(2.5)
    c.rect(12 * mm, 12 * mm, W - 24 * mm, H - 24 * mm)
    c.setLineWidth(0.8)
    c.rect(14 * mm, 14 * mm, W - 28 * mm, H - 28 * mm)

    cx = W / 2
    top = H - 24 * mm

    # DOH seal (centered above the masthead).
    if os.path.exists(_LOGO):
        try:
            seal = ImageReader(_LOGO)
            sw = 20 * mm
            c.drawImage(seal, cx - sw / 2, top - sw, sw, sw,
                        mask="auto", preserveAspectRatio=True)
        except Exception:
            pass

    y = top - 24 * mm
    c.setFillColor(colors.black)
    for i, line in enumerate(f["masthead"]):
        bold = line.startswith("BUREAU")
        c.setFont("Times-Bold" if bold else "Times-Roman", 11 if bold else 10)
        c.drawCentredString(cx, y, line)
        y -= 5 * mm

    # Title.
    y -= 8 * mm
    c.setFont("Times-Bold", 26)
    c.setFillColor(colors.HexColor("#1f4e79"))
    c.drawCentredString(cx, y, f["title"])
    c.setFillColor(colors.black)
    c.setLineWidth(0.8)
    c.setStrokeColor(colors.HexColor("#1f4e79"))
    c.line(cx - 70 * mm, y - 3 * mm, cx + 70 * mm, y - 3 * mm)

    # Body + issued, justified, in a Frame so it wraps cleanly.
    body_style = ParagraphStyle("body", fontName="Times-Roman", fontSize=14,
                                leading=22, alignment=TA_JUSTIFY)
    issued_style = ParagraphStyle("issued", fontName="Times-Roman", fontSize=13,
                                  leading=20, alignment=TA_JUSTIFY,
                                  spaceBefore=10, firstLineIndent=24)
    # Bold the participant's name within the body for emphasis.
    body_html = f["body"].replace(
        f["name"], f"<b>{_xml(f['name'])}</b>", 1) if f["name"] else f["body"]
    story = [Paragraph(_xml_keep(body_html), body_style),
             Paragraph(_xml(f["issued"]), issued_style)]
    frame_top = y - 12 * mm
    frame = Frame(30 * mm, 40 * mm, W - 60 * mm, frame_top - 40 * mm,
                  showBoundary=0, topPadding=0, bottomPadding=0,
                  leftPadding=0, rightPadding=0)
    frame.addFromList(story, c)

    # Signatory block (right-of-centre), with the signature image above the line.
    sig_cx = cx + 35 * mm
    line_y = 36 * mm
    if f["signature_bytes"]:
        try:
            img = ImageReader(io.BytesIO(f["signature_bytes"]))
            iw, ih = img.getSize()
            sh = 16 * mm
            sw = sh * (iw / ih) if ih else 40 * mm
            sw = min(sw, 60 * mm)
            c.drawImage(img, sig_cx - sw / 2, line_y + 1 * mm, sw, sh,
                        mask="auto", preserveAspectRatio=True)
        except Exception:
            pass
    c.setLineWidth(0.8)
    c.setStrokeColor(colors.black)
    c.line(sig_cx - 45 * mm, line_y, sig_cx + 45 * mm, line_y)
    if f["signatory"]:
        c.setFont("Times-Bold", 12)
        c.drawCentredString(sig_cx, line_y - 5.5 * mm, f["signatory"])
    if f["signatory_title"]:
        c.setFont("Times-Roman", 10.5)
        c.drawCentredString(sig_cx, line_y - 10.5 * mm, f["signatory_title"])

    c.showPage()
    c.save()
    return buf.getvalue()


def _xml(s):
    from xml.sax.saxutils import escape
    return escape(s or "")


def _xml_keep(s):
    """Escape everything except our own <b></b> tags."""
    return (_xml(s).replace("&lt;b&gt;", "<b>").replace("&lt;/b&gt;", "</b>"))
