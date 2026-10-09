"""
Monthly wellness-break register — a per-person, print-ready PDF of the breaks
someone availed in a calendar month, laid out like the DOH monitoring register
form (Name / Office header + a Monday–Friday grid, one two-row block per week
with an "Approved By" band under each).

It is the downloadable copy an employee keeps of their own record. Each approval
is signed ON THE DAY it covers, inside that weekday's cell: the approving chief's
handwritten signature — the one they drew on their profile — over their name and
"Digitally approved and signed". A chief with no signature on file still gets the
name and that stamp, which is how the whole register used to read. Either way it
is issued as PDF only, never in an editable form.

Field data comes from storage.wellness_person_month(): the person's name and
office, and the month's availed (approved/completed) breaks, each carrying the
deciding approver's name and signature image so the register can show who signed
off each break.
"""
from __future__ import annotations

import calendar
import io
import re
from datetime import date, timedelta
from xml.sax.saxutils import escape

_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]

# What we print under the approver's signature — and instead of it, when they
# have none on file: the approval is a system record, so there was never a wet
# signature to reproduce.
_SIGNED = "Digitally approved and signed"


def _parse_date(s):
    """'YYYY-MM-DD' (or a date) -> a date, or None."""
    if isinstance(s, date):
        return s
    if not s:
        return None
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})", str(s).strip())
    if not m:
        return None
    try:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    except ValueError:
        return None


def month_title(year, month):
    return f"{_MONTHS[month - 1]} {year}"


def filename(data):
    """A safe download name: Wellness-Register-<lastword>-<YYYY-MM>.pdf."""
    name = (data.get("name") or "").strip()
    who = re.sub(r"[^A-Za-z0-9]+", "", name.split()[-1]) if name else ""
    who = who or "employee"
    return f"Wellness-Register-{who}-{data['year']:04d}-{data['month']:02d}.pdf"


def _month_weeks(year, month):
    """The Monday-anchored weeks that overlap the month, as
    (monday, clipped_start, clipped_end) — clipped to the month's first/last day
    so the row label reads like the paper form ('08/03-08/07', '08/31')."""
    first = date(year, month, 1)
    last = date(year, month, calendar.monthrange(year, month)[1])
    monday = first - timedelta(days=first.weekday())
    weeks = []
    while monday <= last:
        friday = monday + timedelta(days=4)
        start, end = max(monday, first), min(friday, last)
        if end >= first and start <= last:      # week touches the month
            weeks.append((monday, start, end))
        monday += timedelta(days=7)
    return weeks


def _range_label(start, end):
    if start == end:
        return f"{start.month:02d}/{start.day:02d}"
    return f"{start.month:02d}/{start.day:02d}-{end.month:02d}/{end.day:02d}"


def time_range(start_time, hours):
    """'16:00' + 1 -> '16:00 - 17:00'. Falls back to the bare start time when it
    isn't a valid 'HH:MM', and wraps past midnight rather than printing '24:00+'."""
    s = (start_time or "").strip()
    m = re.fullmatch(r"([01]?\d|2[0-3]):([0-5]\d)", s)
    if not m:
        return s
    try:
        hrs = float(hours or 1)
    except (TypeError, ValueError):
        hrs = 1
    start = int(m.group(1)) * 60 + int(m.group(2))
    end = (start + int(round(hrs * 60))) % (24 * 60)
    return f"{start // 60:02d}:{start % 60:02d} - {end // 60:02d}:{end % 60:02d}"


def _break_html(e):
    """One availed break, as the form's day cell reads it."""
    t = escape(time_range(e.get("start_time"), e.get("hours")))
    act = escape(e.get("activity_label") or "")
    hrs = e.get("hours") or 1
    done = e.get("status") == "completed"
    head = f"<b>{t}</b> " if t else ""
    return f"{head}{act} · {hrs}h{' ✓' if done else ''}"


def _sign_off_html(e):
    """The approval that stands under a break: who signed it, over the stamp that
    replaces a wet signature. Printed whether or not an image accompanies it, so a
    chief with no signature on file still reads exactly as the register always has."""
    who = escape((e.get("approver") or "").strip())
    parts = [f"<b>{who}</b>"] if who else []
    parts.append(f"<i>{escape(_SIGNED)}</i>")
    return "<br/>".join(parts)


def _signature_image(e, max_w, max_h):
    """The approver's signature as a right-sized flowable, or None when they have
    none on file (or the stored bytes won't open — a register download must not
    fail over a bad blob)."""
    raw = e.get("approver_signature")
    if not raw:
        return None
    from reportlab.lib.utils import ImageReader
    from reportlab.platypus import Image
    try:
        iw, ih = ImageReader(io.BytesIO(raw)).getSize()
        if not iw or not ih:
            return None
        scale = min(max_w / float(iw), max_h / float(ih))
        # A fresh BytesIO per Image: platypus reads the stream when the flowable
        # is built, so a shared one would come up empty on the second cell.
        # mask='auto' keeps the pad's transparent background transparent, so the
        # signature sits ON the cell rather than in a white box.
        img = Image(io.BytesIO(raw), width=iw * scale, height=ih * scale,
                    mask="auto", lazy=0)
        img.hAlign = "LEFT"
        return img
    except Exception:
        return None


def _cell_styles():
    """The two paragraph styles a day cell is written in. Built on demand so the
    module keeps its lazy reportlab import."""
    from reportlab.lib.styles import ParagraphStyle
    return (ParagraphStyle("cell", fontName="Helvetica", fontSize=7, leading=8.5),
            ParagraphStyle("apprv", fontName="Helvetica", fontSize=6.5, leading=8))


def build_day_cell(entries, max_w, max_h, cell=None, apprv=None):
    """One weekday's contents: each break availed that day, and under each the
    signature that approved IT — the day is where an approval is signed, not the
    week. Returns a flowable list (reportlab table cells take one), or '' for a
    blank day, which is what the form's empty boxes are."""
    from reportlab.platypus import Paragraph
    if cell is None or apprv is None:
        cell, apprv = _cell_styles()
    flows = []
    for e in entries:
        flows.append(Paragraph(_break_html(e), cell))
        img = _signature_image(e, max_w, max_h)
        if img is not None:
            flows.append(img)
        flows.append(Paragraph(_sign_off_html(e), apprv))
    return flows or ""


def _approver_html(entries):
    """The week band's left-hand label. The names, the stamp and the signature
    itself now sit in the weekday cell of the day they approve, so this keeps only
    the paper form's label — the band it labels is the two-row week."""
    return "Approved By:"


def render_month_pdf(data) -> bytes:
    """Render one person's monthly register to PDF bytes. `data` is a
    storage.wellness_person_month() dict."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import ParagraphStyle
    from reportlab.lib.enums import TA_CENTER
    from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                    TableStyle)

    year, month = data["year"], data["month"]
    name = (data.get("name") or "").strip() or "________________"
    office = (data.get("office") or "").strip() or "________________"

    # Bucket the month's entries by calendar date.
    by_date = {}
    for e in data.get("entries", []):
        d = _parse_date(e.get("date"))
        if d:
            by_date.setdefault(d, []).append(e)

    cell = ParagraphStyle("cell", fontName="Helvetica", fontSize=7, leading=8.5)
    day_hdr = ParagraphStyle("dayhdr", fontName="Helvetica-Bold", fontSize=8,
                             leading=9, alignment=TA_CENTER)
    weeklab = ParagraphStyle("weeklab", fontName="Helvetica-Bold", fontSize=8,
                             leading=9.5)
    apprv = ParagraphStyle("apprv", fontName="Helvetica", fontSize=6.5, leading=8)

    col0 = 82
    dayw = (A4[0] - 30 * mm - col0) / 5.0
    sig_w, sig_h = dayw - 12, 20          # the signature's room inside a day cell

    days = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
    table_data = [[Paragraph(f"<b><i>{_MONTHS[month - 1].upper()}</i></b>", day_hdr)]
                  + [Paragraph(d, day_hdr) for d in days]]

    # SPAN the five weekday cells across each week's date row + approver row, so a
    # weekday is one tall cell over its 'Approved By' line — exactly the form.
    spans, shades = [], []
    for monday, start, end in _month_weeks(year, month):
        r = len(table_data)                         # date-row index
        row_date = [Paragraph(_range_label(start, end), weeklab)]
        week_entries = []
        for i in range(5):
            d = monday + timedelta(days=i)
            ents = by_date.get(d, []) if start <= d <= end else []
            week_entries.extend(ents)
            if not (start <= d <= end):             # day outside the month
                shades.append((i + 1, r))
            row_date.append(build_day_cell(ents, sig_w, sig_h, cell, apprv))
        table_data.append(row_date)
        table_data.append([Paragraph(_approver_html(week_entries), apprv)]
                          + ["", "", "", "", ""])
        for c in range(1, 6):
            spans.append(("SPAN", (c, r), (c, r + 1)))

    table = Table(table_data, colWidths=[col0] + [dayw] * 5, repeatRows=1)
    style = [
        ("GRID", (0, 0), (-1, -1), 0.7, colors.black),
        ("BOX", (0, 0), (-1, -1), 1.1, colors.black),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("VALIGN", (0, 0), (-1, 0), "MIDDLE"),
        ("BACKGROUND", (0, 0), (-1, 0), colors.Color(.93, .93, .93)),
        ("LEFTPADDING", (0, 0), (-1, -1), 3),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    style.extend(spans)
    for c, r in shades:
        style.append(("BACKGROUND", (c, r), (c, r + 1), colors.Color(.96, .96, .96)))
    table.setStyle(TableStyle(style))

    hdr = ParagraphStyle("hdr", fontName="Helvetica", fontSize=10, leading=15)
    title = ParagraphStyle("title", fontName="Helvetica-Bold", fontSize=13,
                           leading=16, alignment=TA_CENTER)
    sub = ParagraphStyle("sub", fontName="Helvetica", fontSize=8.5, leading=12,
                         alignment=TA_CENTER, textColor=colors.Color(.35, .35, .35))

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4,
                            leftMargin=15 * mm, rightMargin=15 * mm,
                            topMargin=13 * mm, bottomMargin=13 * mm,
                            title=f"Wellness Register — {name} — {month_title(year, month)}")
    story = [
        Paragraph("Two-Hour Weekly Wellness Break — Monitoring Register", title),
        Paragraph(f"{month_title(year, month)} &nbsp;·&nbsp; DOH DM 2025-0135", sub),
        Spacer(1, 8),
        Paragraph(f"Name: <b>{escape(name)}</b> &nbsp;&nbsp;&nbsp; "
                  f"Office: <b>{escape(office)}</b>", hdr),
        Spacer(1, 6),
        table,
    ]
    doc.build(story)
    return buf.getvalue()
