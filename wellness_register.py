"""
Monthly wellness-break register — a per-person, print-ready PDF of the breaks
someone availed in a calendar month, laid out like the DOH monitoring register
form (Name / Office header + a Monday–Friday grid, one two-row block per week
with an "Approved By" line under each).

It is the downloadable copy an employee keeps of their own record: because the
approval already happened inside the system, the signature area is filled with
"Digitally approved and signed" instead of a blank line to sign — the register
is issued as PDF only, never in an editable form.

Field data comes from storage.wellness_person_month(): the person's name and
office, and the month's availed (approved/completed) breaks, each carrying the
deciding approver's name so the register can name who signed off each week.
"""
from __future__ import annotations

import calendar
import io
import re
from datetime import date, timedelta
from xml.sax.saxutils import escape

_MONTHS = ["January", "February", "March", "April", "May", "June", "July",
           "August", "September", "October", "November", "December"]

# What we stamp where the paper form leaves a line to sign: the approval is a
# system record, so there is nothing to sign by hand.
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


def _day_cell_html(entries):
    """The availed break(s) on one day, or '' when the day is blank."""
    lines = []
    for e in entries:
        t = escape((e.get("start_time") or "").strip())
        act = escape(e.get("activity_label") or "")
        hrs = e.get("hours") or 1
        done = e.get("status") == "completed"
        head = f"<b>{t}</b> " if t else ""
        tail = f" · {hrs}h{' ✓' if done else ''}"
        lines.append(f"{head}{act}{tail}")
    return "<br/>".join(lines)


def _approver_html(entries):
    """The 'Approved By' block for a week: the deciding approver's name(s) over
    the digital-signature stamp. Blank weeks show only the label, like the form."""
    if not entries:
        return "Approved By:"
    names = []
    for e in entries:
        n = (e.get("approver") or "").strip()
        if n and n not in names:
            names.append(n)
    who = escape(" / ".join(names)) if names else ""
    parts = ["Approved By:"]
    if who:
        parts.append(f"<b>{who}</b>")
    parts.append(f"<i>{escape(_SIGNED)}</i>")
    return "<br/>".join(parts)


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
            row_date.append(Paragraph(_day_cell_html(ents), cell))
        table_data.append(row_date)
        table_data.append([Paragraph(_approver_html(week_entries), apprv)]
                          + ["", "", "", "", ""])
        for c in range(1, 6):
            spans.append(("SPAN", (c, r), (c, r + 1)))

    col0 = 82
    dayw = (A4[0] - 30 * mm - col0) / 5.0
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
        Spacer(1, 6),
        Paragraph("Each weekday cell shows the break availed that day (start time · "
                  "activity · hours; ✓ = completed). Approvals were recorded in the "
                  "CSS Information System; “Digitally approved and signed” stands in "
                  "for the approver’s wet signature.", sub),
    ]
    doc.build(story)
    return buf.getvalue()
