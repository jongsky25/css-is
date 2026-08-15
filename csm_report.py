"""
Official CO-CSM report (ARTA Type-1) in the government template layout.

Renders the data assembled by ``app._csm_official_report`` into an EXACT
structural replica of the bureau's official Client Satisfaction Measurement
Report (the ANNEX-D submission document):

  Cover (DOH seal) → I. Overview: → II. Scope: → III. Methodology: →
  IV. Data and Interpretation (A. Demographic Profile; B. Count of CC and SQD
  results incl. CC answer analysis, SQD0, the eight named Service-Quality
  Dimensions, C. Average score per service) → OVERALL REPORT ANALYSIS →
  V. Agency Action Plan → VI. Continuous Improvement → Prepared/Approved by.

Built to match the actual submitted .docx element-for-element (headings, casing,
numbered rows, blank separator rows, full column headers, the seal & formula
IMAGES the office uses, signature block). Fidelity rule (per the bureau): match
exactly — you may ADD but not OMIT. The only intentional departures: values are
data-driven & corrected (the submitted file's data bugs are not reproduced); the
Overview date is period-accurate rather than the stale literal; and a couple of
small italic clarity notes are ADDED after tables.

Sections V and VI print `rep["action_plan_text"]` / `rep["continuous_improvement_text"]`
when the caller supplies them (docs/AI_INTEGRATION_PLAN.md Phase 5's saved,
possibly AI-drafted, report_draft rows), falling back to the original "N/A" /
standing boilerplate otherwise — export itself never calls AI.

  * official_docx(rep, meta) -> bytes
  * official_pdf(rep, meta)  -> bytes
"""
import io
import os
import re

from docx import Document
from docx.shared import Pt, RGBColor, Inches
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.table import WD_TABLE_ALIGNMENT

import report_docs as _rd

# ---------------------------------------------------------------------
# Mandated boilerplate text (verbatim from the template)
# ---------------------------------------------------------------------

_OVERVIEW = [
    "The Department of Health (DOH) is the principal health agency in the Philippines. "
    "It is responsible for ensuring access to basic public health services to all "
    "Filipinos through the provision of quality health care and regulation of providers "
    "of health goods and services.",
    "As stated in the ARTA Memorandum Circular (M.C.) No. 2022-05, government agencies "
    "shall administer the CSM to all clients with completed transaction. Per 6.7.3 of "
    "ARTA M.C. No. 2019-002, the client satisfaction measurement detailing the scope and "
    "period covered by the measurement, the methodology used, the results of the "
    "measurement, and the interpretation of the data shall be reported to the Authority. "
    "In addition, as per instruction of the Performance Monitoring and Strategy "
    "Management Division, all CSM data of the BLHSD are encoded in "
    "https://tinyurl.com/CentralOfficeCSM.",
]

_SCOPE_INTRO = [
    "DOH-BLHSD implemented the CSM on June 2023.",
    "The survey was made available to every client that visited the main and regional "
    "offices, as well as those that contacted BLHSD through email.",
    "The survey used the standard harmonized CSM questionnaire. It asked clients "
    "demographic questions, three (3) Citizen’s Charter questions, one (1) question "
    "related to the client’s overall satisfaction, and eight (8) questions related to "
    "the following Service Quality Dimensions:",
]
_SQD_DIMENSIONS = ["Responsiveness", "Reliability", "Access and Facilities",
                   "Communication", "Costs", "Integrity", "Assurance", "Outcome"]
_SCOPE_SERVICES_LEAD = "The services BLHSD surveyed were the following:"
_SCOPE_NOTE = ("The minimum amount of survey responses for each service was calculated "
               "based on a 95% confidence interval and 5% margin of error.")

_METHOD_INTRO = [
    "For physical clients, surveys were handed out and collected by BLHSD personnel "
    "immediately at the end of the transaction. Surveys and survey boxes were also "
    "available near the office’s exit.",
    "For online clients, emails containing the CSM portal link were sent after the last "
    "correspondence.",
    "The 8 Service Quality Dimension (SQD) questions were scored using a 5-point Likert "
    "Scale.",
]
_LIKERT = [("5", "Strongly Agree"), ("4", "Agree"), ("3", "Neither Agree nor Disagree"),
           ("2", "Disagree"), ("1", "Strongly Disagree")]
_FORMULA_DESC = "The Overall score for the 8 SQDs were computed based on the following formula:"
_FORMULA_TEXT = ("Overall Score  =  (Number of 'Strongly Agree' answers + Number of 'Agree' "
                 "answers)  ÷  (Total Number of Respondents − Number of 'N/A' answers)")
_INTERP_DESC = "The interpretation of the results are as follows:"
_INTERP = [("Below 60.0%", "Poor"), ("60.0% - 79.9%", "Fair"),
           ("80.0% - 94.9%", "Satisfactory"), ("95.0% - 100%", "Outstanding")]

_REPRESENTATIVE = ("BLHSD believes the demographic results are representative of the "
                   "agency's client base.")
_CC_QUESTIONS = [
    ("cc1", "CC1. Which of the following describes your awareness of the CC?"),
    ("cc2", "CC2. If aware of CC, would you say that the CC of this office was…?"),
    ("cc3", "CC3. If aware of CC, how much did the CC help you in your transaction?"),
]
_PER_SERVICE_LEAD = "The data below shows the Overall rating of each surveyed service."

_IMPROVEMENT = ("The Bureau will continue to implement the use of Harmonized CSM "
                "pursuant to RA 11032 and DM No. 2023-0158. CSS Forms 2.0 and 3.0 will "
                "still be utilized by the bureau for the conduct of activities and the "
                "results will be presented for analysis and discussion during Quarterly "
                "Management Reviews.")

# Added clarity notes (kept minimal & subtle; nothing mandated removed).
_NOTE_NA = ("Note: 'N/A' means the question did not apply to the transaction (e.g. a "
            "service with no fees) or was left blank; N/A answers are excluded from the "
            "denominator and so do not lower the score.")
_NOTE_DASH = "Note: a 0.0% rating indicates no transactions were recorded for that service in this period."
_SQD_HEADERS = ["", "Strongly Agree", "Agree", "Neither Agree nor Disagree", "Disagree",
                "Strongly Disagree", "N/A", "Total Responses", "Overall"]


# ---------------------------------------------------------------------
# value formatters (match the template's per-table conventions)
# ---------------------------------------------------------------------

def _pctw(v):   # whole percent — Overview, Age, Sex
    return "—" if v is None else f"{round(v)}%"


def _pct2(v):   # two decimals — Region, Customer Type
    return "—" if v is None else f"{v:.2f}%"


def _ovr(v):    # headline Overall (SQD0 / dimensions) — whole %, else N/A
    return "N/A" if v is None else f"{round(v)}%"


def _rate(v):   # per-service Overall Rating — template shows 0.0% when no responses
    return "0.0%" if v is None else f"{v:.1f}%"


def _num(items):
    return [(i + 1, it) for i, it in enumerate(items)]


def _cover_period(info):
    """Cover period line in the file's casing: 'Quarter' etc. upper-cased but the
    ordinal kept lowercase, e.g. '1st QUARTER (CY 2026)'."""
    s = info.get("heading", "").upper()
    return re.sub(r"(\d)(ST|ND|RD|TH)", lambda m: m.group(1) + m.group(2).lower(), s)


def _scope_coverage_line(info):
    """Scope coverage sentence, verbatim to the file's wording for the period:
    'This report covers Calendar Year {year} (from {Mon YYYY} – {Mon YYYY})'."""
    year = info.get("year", "")
    phrase = (info.get("phrase") or "").replace(" to ", " – ")
    if not year:
        return "This report covers all responses on record."
    line = f"This report covers Calendar Year {year}"
    return line + (f" (from {phrase})" if phrase else "")


def _dim_row(d):
    """One Service-Quality-Dimension row. An all-N/A dimension (no-fee service)
    prints 'N/A' in the Strongly-Agree / Total / Overall cells, as the official
    template does; the N/A column keeps the real count (data-driven, corrected)."""
    di = d["dist"]
    if d["score"] is None:
        return [d["dimension"], "N/A", di["A"], di["Neither"], di["D"], di["SD"],
                d["na"], "N/A", "N/A"]
    return [d["dimension"], di["SA"], di["A"], di["Neither"], di["D"], di["SD"],
            d["na"], d["n"], _ovr(d["score"])]


# =====================================================================
# DOCX
# =====================================================================
_INK = RGBColor(0x1C, 0x23, 0x30)
_GREY = RGBColor(0x6B, 0x72, 0x80)


def _center(p):
    p.alignment = WD_ALIGN_PARAGRAPH.CENTER
    return p


def _run(p, text, *, bold=False, size=None, italic=False, color=None):
    r = p.add_run(text)
    r.bold = bold
    r.italic = italic
    if size:
        r.font.size = Pt(size)
    if color:
        r.font.color.rgb = color
    return r


def _note(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_after = Pt(8)
    _run(p, text, italic=True, size=8.5, color=_GREY)


def _heading(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(12)
    p.paragraph_format.space_after = Pt(4)
    _run(p, text, bold=True, size=13, color=_INK)


def _subheading(doc, text):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(3)
    _run(p, text, bold=True, size=11, color=_INK)


def _dtable(doc, headers, rows, *, bold_rows=frozenset(), numeric_from=1):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    hdr = t.rows[0].cells
    for i, h in enumerate(headers):
        hdr[i].text = ""
        r = hdr[i].paragraphs[0].add_run(str(h))
        r.bold = True
        r.font.size = Pt(9.5)
        if numeric_from is not None and i >= numeric_from:
            hdr[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _rd._repeat_header(t.rows[0])
    for ri, row in enumerate(rows):
        cells = t.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = ""
            r = cells[i].paragraphs[0].add_run("" if val is None else str(val))
            r.font.size = Pt(9.5)
            r.bold = ri in bold_rows
            if numeric_from is not None and i >= numeric_from:
                cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    return t


def _docx_cover(doc, meta):
    info = meta.get("period_info", {})
    doc.add_paragraph()
    seal = meta.get("seal_path")
    if seal and os.path.exists(seal):
        _center(doc.add_paragraph()).add_run().add_picture(seal, width=Inches(2.4))
    _center(doc.add_paragraph())
    _run(_center(doc.add_paragraph()), "DEPARTMENT OF HEALTH", bold=True, size=22, color=_INK)
    for _ in range(2):
        doc.add_paragraph()
    for text, sz in (("Client Satisfaction Measurement Report", 16),
                     ("Bureau of Local Health Systems Development", 14),
                     (_cover_period(info) if info.get("heading") else "", 14)):
        if text:
            _run(_center(doc.add_paragraph()), text, bold=True, size=sz, color=_INK)
    doc.add_page_break()


def _docx_overview(doc, rep, meta):
    info = meta.get("period_info", {})
    ov = rep["overview"]
    _heading(doc, "I. Overview:")
    for para in _OVERVIEW:
        doc.add_paragraph(para)
    doc.add_paragraph(
        f"As of {info.get('as_of', 'this period')}, BLHSD surveyed its clients and "
        f"obtained the following results:")
    _dtable(doc, ["", "Score"], [
        ["CC Awareness:", _pctw(ov["cc_aware"])],
        ["CC Visibility:", _pctw(ov["cc_visible"])],
        ["CC Helpfulness:", _pctw(ov["cc_helpful"])],
        ["Response Rate:", _pctw(ov["response_rate"])],
        ["Overall Score:", _pctw(ov["overall"])],
    ])


def _docx_scope(doc, rep, meta):
    info = meta.get("period_info", {})
    sc = rep["scope"]
    _heading(doc, "II. Scope:")
    doc.add_paragraph(_SCOPE_INTRO[0])
    doc.add_paragraph(_scope_coverage_line(info))
    doc.add_paragraph(_SCOPE_INTRO[1])
    doc.add_paragraph(_SCOPE_INTRO[2])
    for dim in _SQD_DIMENSIONS:
        p = doc.add_paragraph(dim, style="List Number")
        p.paragraph_format.space_after = Pt(1)
    doc.add_paragraph(_SCOPE_SERVICES_LEAD)

    rows, bold = [], set()
    for it in sc["external"]:
        rows.append([it["service"], it["responses"], it["transactions"]])
    rows.append(["External Service Total", sc["ext_total"], sc["ext_total"]]); bold.add(len(rows) - 1)
    rows.append(["Internal Services", "", ""]); bold.add(len(rows) - 1)
    for it in sc["internal"]:
        rows.append([it["service"], it["responses"], it["transactions"]])
    rows.append(["Internal Service Total", sc["int_total"], sc["int_total"]]); bold.add(len(rows) - 1)
    rows.append(["OVERALL TOTAL", sc["grand_total"], sc["grand_total"]]); bold.add(len(rows) - 1)
    _dtable(doc, ["External Services", "Responses", "Total Transactions"], rows,
            bold_rows=bold, numeric_from=1)
    doc.add_paragraph(_SCOPE_NOTE)


def _docx_methodology(doc, meta):
    _heading(doc, "III. Methodology:")
    for para in _METHOD_INTRO:
        doc.add_paragraph(para)
    _dtable(doc, ["Scale", "Rating"], [[s, r] for s, r in _LIKERT], numeric_from=None)
    doc.add_paragraph(_FORMULA_DESC)
    fp = meta.get("formula_path")
    if fp and os.path.exists(fp):
        doc.add_picture(fp, width=Inches(5.6))
        doc.paragraphs[-1].alignment = WD_ALIGN_PARAGRAPH.CENTER
    else:
        p = doc.add_paragraph()
        _run(p, _FORMULA_TEXT, bold=True, size=10)
    doc.add_paragraph(_INTERP_DESC)
    _dtable(doc, ["Percentage", "Rating"], [[p_, r] for p_, r in _INTERP], numeric_from=None)


def _docx_data(doc, rep, meta):
    demo = rep["demo"]
    _heading(doc, "IV. Data and Interpretation")
    _subheading(doc, "A. Demographic Profile")

    _subheading(doc, "D1. AGE AND D2. SEX ANALYSIS:")
    rows = [[f"{n}. {it['label']}", _pctw(it["ext"]), _pctw(it["int"]), _pctw(it["all"])]
            for n, it in _num(demo["age"])]
    rows.append(["", "", "", ""])  # blank separator (as in the template)
    rows += [[f"{n}. {it['label']}", _pctw(it["ext"]), _pctw(it["int"]), _pctw(it["all"])]
             for n, it in _num(demo["sex"])]
    _dtable(doc, ["D1. Age and D2. Sex", "External", "Internal", "Overall"], rows,
            numeric_from=1)

    _subheading(doc, "D3. REGION ANALYSIS:")
    _dtable(doc, ["D3. Region", "External", "Internal", "Overall"],
            [[f"{n}. {it['label']}", _pct2(it["ext"]), _pct2(it["int"]), _pct2(it["all"])]
             for n, it in _num(demo["region"])], numeric_from=1)

    _subheading(doc, "CUSTOMER TYPE ANALYSIS:")
    _dtable(doc, ["Customer Type", "External", "Internal", "Overall"],
            [[f"D4. {it['label']}", _pct2(it["ext"]), _pct2(it["int"]), _pct2(it["all"])]
             for it in demo["client_type"]], numeric_from=1)
    doc.add_paragraph(_REPRESENTATIVE)

    _subheading(doc, "B. Count of CC and SQD results")
    _subheading(doc, "CITIZEN'S CHARTER ANSWERS ANALYSIS")
    cc_rows, bold = [], set()
    for bi, (key, question) in enumerate(_CC_QUESTIONS):
        cc_rows.append([question, "", ""]); bold.add(len(cc_rows) - 1)
        for n, it in _num(rep["cc_display"][key]):
            cc_rows.append([f"{n}. {it['label']}", it["n"], f"{it['pct']:.2f}%"])
        if bi < len(_CC_QUESTIONS) - 1:
            cc_rows.append(["", "", ""])
    _dtable(doc, ["Citizen's Charter Answers", "Responses", "Percentage"], cc_rows,
            bold_rows=bold, numeric_from=1)

    s0 = rep.get("sqd0") or {}
    d0 = s0.get("dist", {"SA": 0, "A": 0, "Neither": 0, "D": 0, "SD": 0})
    _subheading(doc, "SQD0 ANALYSIS")
    _dtable(doc, _SQD_HEADERS,
            [["Overall Satisfaction", d0["SA"], d0["A"], d0["Neither"], d0["D"], d0["SD"],
              s0.get("na", 0), s0.get("n", 0), _ovr(s0.get("score"))]], numeric_from=1)

    _subheading(doc, "SERVICE QUALITY DIMENSIONS ANALYSIS")
    rows = [_dim_row(d) for d in rep["dimensions"]]
    rows.append(["Overall", rep.get("overall_sa", ""), rep.get("overall_a", ""), 0, 0, 0,
                 "", rep.get("overall_n", ""), _ovr(rep.get("overall"))])
    _dtable(doc, ["Service Quality Dimensions"] + _SQD_HEADERS[1:], rows,
            bold_rows={len(rows) - 1}, numeric_from=1)
    sa, a, tot = rep.get("overall_sa", 0), rep.get("overall_a", 0), rep.get("overall_n", 0)
    p = doc.add_paragraph()
    _run(p, f"Overall Score = ({sa} + {a}) / ({tot} − 0) × 100 = {_ovr(rep.get('overall'))}",
         bold=True, size=10)
    band = rep.get("overall_band")
    if band:
        doc.add_paragraph(
            f"The 8 Service Quality Dimensions garnered a {_ovr(rep.get('overall'))} overall "
            f"score. This translates to an {band} rating for the Bureau's service to its "
            f"clients for the {meta.get('period_info', {}).get('label', 'period').lower()} "
            f"of {meta.get('period_info', {}).get('cy', '')}.".replace("  ", " "))
    _note(doc, _NOTE_NA)

    _subheading(doc, "C. Average score per service")
    doc.add_paragraph("ANALYSIS:")
    doc.add_paragraph(_PER_SERVICE_LEAD)
    ps = rep["per_service"]
    rows, bold = [], set()
    for s in ps["external"]:
        rows.append([s["service"], _rate(s["score"])])
    rows.append(["External Service Total", _rate(ps.get("ext_total"))]); bold.add(len(rows) - 1)
    rows.append(["Internal Services", ""]); bold.add(len(rows) - 1)
    for s in ps["internal"]:
        rows.append([s["service"], _rate(s["score"])])
    rows.append(["Internal Service Total", _rate(ps.get("int_total"))]); bold.add(len(rows) - 1)
    rows.append(["OVERALL TOTAL", _rate(ps.get("overall_total"))]); bold.add(len(rows) - 1)
    _dtable(doc, ["External Services", "Overall Rating"], rows, bold_rows=bold, numeric_from=1)
    _note(doc, _NOTE_DASH)


def _docx_closing(doc, rep, meta):
    _heading(doc, "OVERALL REPORT ANALYSIS")
    _subheading(doc, "V. Results of the Agency Action Plan reported as of:")
    doc.add_paragraph(rep.get("action_plan_text") or "N/A")
    _subheading(doc, "VI. Continuous Agency Improvement Plan:")
    doc.add_paragraph(rep.get("continuous_improvement_text") or _IMPROVEMENT)
    if rep.get("low_n"):
        _note(doc, f"Note on sample size — this period reflects N = {rep['respondents']} "
                   f"completed responses; results should be read with this base in mind.")

    doc.add_paragraph()
    doc.add_paragraph()
    pb, ab = meta.get("prepared_by", {}), meta.get("approved_by", {})
    sd = meta.get("sign_date", "")
    t = doc.add_table(rows=1, cols=2)
    t.alignment = WD_TABLE_ALIGNMENT.CENTER
    for cell, who, role in ((t.rows[0].cells[0], pb, "Prepared by:"),
                            (t.rows[0].cells[1], ab, "Approved by:")):
        _run(cell.paragraphs[0], role, size=10)
        cell.add_paragraph()
        cell.add_paragraph()
        _run(_center(cell.add_paragraph()), who.get("name", ""), bold=True, size=10.5)
        _run(_center(cell.add_paragraph()), who.get("title", ""), size=10)
        _run(_center(cell.add_paragraph()), f"Date: {sd}", size=10)


def official_docx(rep, meta):
    doc = Document()
    normal = doc.styles["Normal"]
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.15
    normal.font.size = Pt(10.5)
    _docx_cover(doc, meta)
    if not rep.get("has_data"):
        doc.add_paragraph("No CSM (Type-1) responses were recorded for this period.")
        return _rd._save(doc)
    _docx_overview(doc, rep, meta)
    _docx_scope(doc, rep, meta)
    _docx_methodology(doc, meta)
    _docx_data(doc, rep, meta)
    _docx_closing(doc, rep, meta)
    fr = doc.add_paragraph()
    _run(fr, f"Generated {meta.get('generated', '')} · Source: {meta.get('source', 'Office Connect')}",
         italic=True, size=8, color=_GREY)
    return _rd._save(doc)


# =====================================================================
# PDF (reportlab) — same structure, print-ready
# =====================================================================
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.styles import ParagraphStyle
from reportlab.platypus import (Paragraph, Spacer, Table, TableStyle,
                                Image as RLImage, PageBreak, KeepTogether)
from reportlab.lib.utils import ImageReader
from xml.sax.saxutils import escape as _esc

_CW = _rd._CONTENT_W  # 16 cm


def _pstyles():
    st = _rd._pdf_styles()
    base = st["body"]
    st["covertitle"] = ParagraphStyle("ct", parent=base, fontName=_rd._PDF_FONT_B,
                                      fontSize=22, alignment=TA_CENTER, textColor=_rd._INK,
                                      leading=26, spaceAfter=6)
    st["coversub"] = ParagraphStyle("cs", parent=base, fontName=_rd._PDF_FONT_B,
                                    fontSize=14, alignment=TA_CENTER, textColor=_rd._INK,
                                    leading=20, spaceAfter=4)
    st["coverbig"] = ParagraphStyle("cb", parent=base, fontName=_rd._PDF_FONT_B,
                                    fontSize=16, alignment=TA_CENTER, textColor=_rd._INK,
                                    leading=22, spaceAfter=4)
    st["sig"] = ParagraphStyle("sg", parent=base, alignment=TA_CENTER, fontSize=10, leading=13)
    st["signame"] = ParagraphStyle("sn", parent=base, fontName=_rd._PDF_FONT_B,
                                   alignment=TA_CENTER, fontSize=10.5, leading=13)
    st["sub"] = ParagraphStyle("sub", parent=base, fontName=_rd._PDF_FONT_B, fontSize=11,
                               spaceBefore=8, spaceAfter=3, textColor=_rd._INK)
    st["li"] = ParagraphStyle("li", parent=base, leftIndent=14, spaceAfter=1)
    return st


def _h2(text, st):
    return Paragraph(_esc(text), st["h2"])


def _sub(text, st):
    return Paragraph(f"<b>{_esc(text)}</b>", st["sub"])


def _pdf_table(headers, rows, widths, st, *, bold_rows=frozenset(), numeric_from=1):
    def cell(val, i, *, header=False, bold=False):
        right = numeric_from is not None and i >= numeric_from
        key = ("cellh" if header else "cell") + ("r" if right else "")
        style = st[key]
        if bold and not header:
            style = ParagraphStyle("b", parent=style, fontName=_rd._PDF_FONT_B)
        return Paragraph(_esc("" if val is None else str(val)), style)

    data = [[cell(h, i, header=True) for i, h in enumerate(headers)]]
    for ri, r in enumerate(rows):
        data.append([cell(v, i, bold=ri in bold_rows) for i, v in enumerate(r)])
    t = Table(data, colWidths=widths, repeatRows=1)
    style = [
        ("BACKGROUND", (0, 0), (-1, 0), _rd._HEADBG),
        ("GRID", (0, 0), (-1, -1), 0.5, _rd._LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 3),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ("LEFTPADDING", (0, 0), (-1, -1), 4),
        ("RIGHTPADDING", (0, 0), (-1, -1), 4),
    ]
    for ri in bold_rows:
        style.append(("BACKGROUND", (0, ri + 1), (-1, ri + 1), _rd._BOXBG))
    t.setStyle(TableStyle(style))
    return t


def _note_p(text, st):
    return Paragraph(_esc(text), st["note"])


def _img_flowable(path, width):
    iw, ih = ImageReader(path).getSize()
    img = RLImage(path, width=width, height=width * ih / iw)
    img.hAlign = "CENTER"
    return img


def _pdf_cover(st, meta):
    info = meta.get("period_info", {})
    out = [Spacer(1, 1.6 * cm)]
    seal = meta.get("seal_path")
    if seal and os.path.exists(seal):
        out += [_img_flowable(seal, 5.6 * cm), Spacer(1, 0.6 * cm)]
    out += [Paragraph("DEPARTMENT OF HEALTH", st["covertitle"]), Spacer(1, 1.2 * cm),
            Paragraph("Client Satisfaction Measurement Report", st["coverbig"]),
            Paragraph("Bureau of Local Health Systems Development", st["coversub"])]
    if info.get("heading"):
        out.append(Paragraph(_esc(_cover_period(info)), st["coversub"]))
    out.append(PageBreak())
    return out


def _paras(texts, st):
    return [Paragraph(_esc(t), st["body"]) for t in texts]


def official_pdf(rep, meta):
    st = _pstyles()
    info = meta.get("period_info", {})
    f = _pdf_cover(st, meta)
    if not rep.get("has_data"):
        f.append(Paragraph("No CSM (Type-1) responses were recorded for this period.",
                           st["body"]))
        return _rd._pdf_doc(meta, f)

    # I. Overview
    ov = rep["overview"]
    f.append(_h2("I. Overview:", st))
    f += _paras(_OVERVIEW, st)
    f.append(Paragraph(_esc(f"As of {info.get('as_of','this period')}, BLHSD surveyed its "
                            "clients and obtained the following results:"), st["body"]))
    f.append(_pdf_table(["", "Score"], [
        ["CC Awareness:", _pctw(ov["cc_aware"])], ["CC Visibility:", _pctw(ov["cc_visible"])],
        ["CC Helpfulness:", _pctw(ov["cc_helpful"])], ["Response Rate:", _pctw(ov["response_rate"])],
        ["Overall Score:", _pctw(ov["overall"])],
    ], [10 * cm, 6 * cm], st))

    # II. Scope
    sc = rep["scope"]
    f.append(_h2("II. Scope:", st))
    f += _paras([_SCOPE_INTRO[0], _scope_coverage_line(info),
                 _SCOPE_INTRO[1], _SCOPE_INTRO[2]], st)
    for i, dim in enumerate(_SQD_DIMENSIONS, 1):
        f.append(Paragraph(f"{i}. {_esc(dim)}", st["li"]))
    f.append(Paragraph(_esc(_SCOPE_SERVICES_LEAD), st["body"]))
    rows, bold = [], set()
    for it in sc["external"]:
        rows.append([it["service"], it["responses"], it["transactions"]])
    rows.append(["External Service Total", sc["ext_total"], sc["ext_total"]]); bold.add(len(rows) - 1)
    rows.append(["Internal Services", "", ""]); bold.add(len(rows) - 1)
    for it in sc["internal"]:
        rows.append([it["service"], it["responses"], it["transactions"]])
    rows.append(["Internal Service Total", sc["int_total"], sc["int_total"]]); bold.add(len(rows) - 1)
    rows.append(["OVERALL TOTAL", sc["grand_total"], sc["grand_total"]]); bold.add(len(rows) - 1)
    f.append(_pdf_table(["External Services", "Responses", "Total Transactions"], rows,
                        [10 * cm, 3 * cm, 3 * cm], st, bold_rows=bold))
    f.append(Paragraph(_esc(_SCOPE_NOTE), st["body"]))

    # III. Methodology
    f.append(_h2("III. Methodology:", st))
    f += _paras(_METHOD_INTRO, st)
    f.append(_pdf_table(["Scale", "Rating"], [[s, r] for s, r in _LIKERT],
                        [3 * cm, 13 * cm], st, numeric_from=None))
    f.append(Spacer(1, 4))
    f.append(Paragraph(_esc(_FORMULA_DESC), st["body"]))
    fp = meta.get("formula_path")
    if fp and os.path.exists(fp):
        f.append(Spacer(1, 3))
        f.append(_img_flowable(fp, 13.5 * cm))
        f.append(Spacer(1, 5))
    else:
        f.append(Paragraph(f"<b>{_esc(_FORMULA_TEXT)}</b>", st["body"]))
    f.append(Paragraph(_esc(_INTERP_DESC), st["body"]))
    f.append(_pdf_table(["Percentage", "Rating"], [[p, r] for p, r in _INTERP],
                        [6 * cm, 10 * cm], st, numeric_from=None))

    # IV. Data and Interpretation
    demo = rep["demo"]
    f.append(_h2("IV. Data and Interpretation", st))
    f.append(_sub("A. Demographic Profile", st))
    f.append(_sub("D1. AGE AND D2. SEX ANALYSIS:", st))
    dw = [7 * cm, 3 * cm, 3 * cm, 3 * cm]
    rows = [[f"{n}. {it['label']}", _pctw(it["ext"]), _pctw(it["int"]), _pctw(it["all"])]
            for n, it in _num(demo["age"])]
    rows.append(["", "", "", ""])
    rows += [[f"{n}. {it['label']}", _pctw(it["ext"]), _pctw(it["int"]), _pctw(it["all"])]
             for n, it in _num(demo["sex"])]
    f.append(_pdf_table(["D1. Age and D2. Sex", "External", "Internal", "Overall"], rows, dw, st))
    f.append(_sub("D3. REGION ANALYSIS:", st))
    f.append(_pdf_table(["D3. Region", "External", "Internal", "Overall"],
             [[f"{n}. {it['label']}", _pct2(it["ext"]), _pct2(it["int"]), _pct2(it["all"])]
              for n, it in _num(demo["region"])], dw, st))
    f.append(_sub("CUSTOMER TYPE ANALYSIS:", st))
    f.append(_pdf_table(["Customer Type", "External", "Internal", "Overall"],
             [[f"D4. {it['label']}", _pct2(it["ext"]), _pct2(it["int"]), _pct2(it["all"])]
              for it in demo["client_type"]], dw, st))
    f.append(Paragraph(_esc(_REPRESENTATIVE), st["body"]))

    f.append(_sub("B. Count of CC and SQD results", st))
    f.append(_sub("CITIZEN'S CHARTER ANSWERS ANALYSIS", st))
    cc_rows, bold = [], set()
    for bi, (key, question) in enumerate(_CC_QUESTIONS):
        cc_rows.append([question, "", ""]); bold.add(len(cc_rows) - 1)
        for n, it in _num(rep["cc_display"][key]):
            cc_rows.append([f"{n}. {it['label']}", it["n"], f"{it['pct']:.2f}%"])
        if bi < len(_CC_QUESTIONS) - 1:
            cc_rows.append(["", "", ""])
    f.append(_pdf_table(["Citizen's Charter Answers", "Responses", "Percentage"], cc_rows,
                        [10 * cm, 3 * cm, 3 * cm], st, bold_rows=bold))

    s0 = rep.get("sqd0") or {}
    d0 = s0.get("dist", {"SA": 0, "A": 0, "Neither": 0, "D": 0, "SD": 0})
    sqd_w = [3.4 * cm] + [1.55 * cm] * 5 + [1.0 * cm, 1.65 * cm, 1.5 * cm]
    f.append(_sub("SQD0 ANALYSIS", st))
    f.append(_pdf_table(_SQD_HEADERS,
             [["Overall Satisfaction", d0["SA"], d0["A"], d0["Neither"], d0["D"], d0["SD"],
               s0.get("na", 0), s0.get("n", 0), _ovr(s0.get("score"))]], sqd_w, st))

    f.append(_sub("SERVICE QUALITY DIMENSIONS ANALYSIS", st))
    rows = [_dim_row(d) for d in rep["dimensions"]]
    rows.append(["Overall", rep.get("overall_sa", ""), rep.get("overall_a", ""), 0, 0, 0,
                 "", rep.get("overall_n", ""), _ovr(rep.get("overall"))])
    f.append(_pdf_table(["Service Quality Dimensions"] + _SQD_HEADERS[1:], rows, sqd_w, st,
                        bold_rows={len(rows) - 1}))
    sa, a, tot = rep.get("overall_sa", 0), rep.get("overall_a", 0), rep.get("overall_n", 0)
    f.append(Paragraph(f"<b>Overall Score = ({sa} + {a}) / ({tot} − 0) × 100 = "
                       f"{_esc(_ovr(rep.get('overall')))}</b>", st["body"]))
    band = rep.get("overall_band")
    if band:
        f.append(Paragraph(_esc(
            f"The 8 Service Quality Dimensions garnered a {_ovr(rep.get('overall'))} overall "
            f"score. This translates to an {band} rating for the Bureau's service to its "
            f"clients for the {info.get('label','period').lower()} of {info.get('cy','')}."
            .replace("  ", " ")), st["body"]))
    f.append(_note_p(_NOTE_NA, st))

    f.append(_sub("C. Average score per service", st))
    f.append(Paragraph("<b>ANALYSIS:</b>", st["body"]))
    f.append(Paragraph(_esc(_PER_SERVICE_LEAD), st["body"]))
    ps = rep["per_service"]
    rows, bold = [], set()
    for s in ps["external"]:
        rows.append([s["service"], _rate(s["score"])])
    rows.append(["External Service Total", _rate(ps.get("ext_total"))]); bold.add(len(rows) - 1)
    rows.append(["Internal Services", ""]); bold.add(len(rows) - 1)
    for s in ps["internal"]:
        rows.append([s["service"], _rate(s["score"])])
    rows.append(["Internal Service Total", _rate(ps.get("int_total"))]); bold.add(len(rows) - 1)
    rows.append(["OVERALL TOTAL", _rate(ps.get("overall_total"))]); bold.add(len(rows) - 1)
    f.append(_pdf_table(["External Services", "Overall Rating"], rows, [13 * cm, 3 * cm], st,
                        bold_rows=bold))
    f.append(_note_p(_NOTE_DASH, st))

    # OVERALL REPORT ANALYSIS / V / VI
    f.append(_h2("OVERALL REPORT ANALYSIS", st))
    f.append(_sub("V. Results of the Agency Action Plan reported as of:", st))
    f.append(Paragraph(_esc(rep.get("action_plan_text") or "N/A"), st["body"]))
    f.append(_sub("VI. Continuous Agency Improvement Plan:", st))
    f.append(Paragraph(_esc(rep.get("continuous_improvement_text") or _IMPROVEMENT), st["body"]))
    if rep.get("low_n"):
        f.append(_note_p(f"Note on sample size — this period reflects N = {rep['respondents']} "
                         "completed responses; results should be read with this base in mind.",
                         st))

    # Signatures
    pb, ab = meta.get("prepared_by", {}), meta.get("approved_by", {})
    sd = meta.get("sign_date", "")
    sig = Table([[
        [Paragraph("Prepared by:", st["sig"]), Spacer(1, 1.1 * cm),
         Paragraph(_esc(pb.get("name", "")), st["signame"]),
         Paragraph(_esc(pb.get("title", "")), st["sig"]),
         Paragraph(_esc(f"Date: {sd}"), st["sig"])],
        [Paragraph("Approved by:", st["sig"]), Spacer(1, 1.1 * cm),
         Paragraph(_esc(ab.get("name", "")), st["signame"]),
         Paragraph(_esc(ab.get("title", "")), st["sig"]),
         Paragraph(_esc(f"Date: {sd}"), st["sig"])],
    ]], colWidths=[8 * cm, 8 * cm])
    sig.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"),
                             ("TOPPADDING", (0, 0), (-1, -1), 18)]))
    f.append(KeepTogether([Spacer(1, 0.8 * cm), sig]))
    return _rd._pdf_doc(meta, f)
