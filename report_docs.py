"""
Official document generation for the /reports official reports, built from the
on-screen report data (app._arta_official_report / app._servqual_official) so the
downloads and the page can never disagree. Three deliberately distinct artifacts:

  * DOCX — the complete tabular reference document (every data table).
  * PDF  — a report-ready narrative: captioned figures + key tables + a warm
           plain-language description of each visual, laid out WPSAR-style
           (Summary -> Results -> Methods & notes; table titles above, figure
           captions below, sequential numbering).
  * PPTX — a visual deck: one figure per slide with a plain-language insight,
           no tables.

Figures (PDF + PPTX) share one matplotlib charting layer for a consistent look.
"""
import io
import os
from xml.sax.saxutils import escape as _xml_escape

from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn

_GREY = RGBColor(0x6B, 0x72, 0x80)


# ---------------------------------------------------------------------
# small formatting helpers
# ---------------------------------------------------------------------

def _p0(x):
    return f"{x:.0f}%" if x is not None else "—"


def _strip_period(s):
    return (s or "").rstrip(". ").strip()


def _comment_text(q):
    """A single deduplicated comment rendered for display: the verbatim, with a
    ×N repeat count appended only when more than one respondent gave it."""
    t = q["text"]
    return f"{t}  (×{q['count']})" if q.get("count", 1) > 1 else t


# =====================================================================
# DOCX — complete tabular reference document
# =====================================================================

def _save(doc):
    buf = io.BytesIO()
    doc.save(buf)
    return buf.getvalue()


def _docx_base(meta):
    doc = Document()
    normal = doc.styles["Normal"]
    normal.paragraph_format.space_after = Pt(6)
    normal.paragraph_format.line_spacing = 1.15
    doc.add_heading(meta["title"], level=0)
    if meta.get("scope"):
        r = doc.add_paragraph().add_run(meta["scope"])
        r.italic = True
    fr = doc.add_paragraph().add_run(
        f"Generated {meta.get('generated', '')} · Source: {meta.get('source', 'CSS-IS')}")
    fr.italic = True
    fr.font.size = Pt(9)
    fr.font.color.rgb = _GREY
    return doc


def _repeat_header(row):
    trPr = row._tr.get_or_add_trPr()
    th = OxmlElement("w:tblHeader")
    th.set(qn("w:val"), "true")
    trPr.append(th)


def _table_title(doc, n, subject, meta=None, N=None):
    """Publication-style table caption: 'Table N. <subject>, <place>, <time>
    (N = <n>)'. Place/time come from meta; N is the standalone denominator."""
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(11)
    p.paragraph_format.space_after = Pt(3)
    loc = ", ".join(x for x in ((meta or {}).get("place"), (meta or {}).get("period")) if x)
    text = f"Table {n}. {subject}"
    if loc:
        text += f", {loc}"
    if N is not None:
        text += f" (N = {N:,})"
    run = p.add_run(text)
    run.bold = True
    run.font.size = Pt(9.5)


def _table(doc, headers, rows, numeric_from=None):
    t = doc.add_table(rows=1, cols=len(headers))
    t.style = "Table Grid"
    hdr = t.rows[0]
    for i, h in enumerate(headers):
        cell = hdr.cells[i]
        cell.text = ""
        cell.paragraphs[0].add_run(str(h)).bold = True
        if numeric_from is not None and i >= numeric_from:
            cell.paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    _repeat_header(hdr)
    for row in rows:
        cells = t.add_row().cells
        for i, val in enumerate(row):
            cells[i].text = "" if val is None else str(val)
            if numeric_from is not None and i >= numeric_from:
                cells[i].paragraphs[0].alignment = WD_ALIGN_PARAGRAPH.RIGHT
    return t


def _kv_line(doc, label, value):
    p = doc.add_paragraph()
    p.add_run(f"{label}: ").bold = True
    p.add_run(str(value))
    return p


def arta_docx(rep, meta):
    doc = _docx_base(meta)
    if not rep.get("has_data"):
        doc.add_paragraph("No walk-in / ARTA responses in this period.")
        return _save(doc)
    n = 0
    band = f" ({rep['overall_band']})" if rep.get("overall_band") else ""
    overall = f"{rep['overall']:.1f}%{band}" if rep.get("overall") is not None else "—"
    _kv_line(doc, "Overall Service Quality", f"{overall}  ·  top-box of SQD1–SQD8")
    _kv_line(doc, "Respondents", f"{rep['respondents']:,}")
    if rep.get("onsite_online"):
        _kv_line(doc, "Mode", ", ".join(
            f"{o['label']} {o['n']:,} ({o['pct']}%)" for o in rep["onsite_online"]))

    doc.add_heading("Service Quality Dimensions (SQD)", level=1)
    n += 1
    _table_title(doc, n, "Item-level satisfaction among walk-in clients (SQD0–SQD8)",
                 meta, N=rep["respondents"])
    rows = []
    for d in rep["sqd"]:
        di = d["dist"]
        rows.append([d["item"], d["text"], di["SA"], di["A"], di["Neither"], di["D"],
                     di["SD"], d["na"],
                     f"{d['score']}%" if d["score"] is not None else "—", d["band"] or ""])
    _table(doc, ["Item", "Statement", "SA", "A", "Neither", "D", "SD", "N/A",
                 "Top-box", "Band"], rows, numeric_from=2)

    doc.add_heading("Citizen's Charter (CC)", level=1)
    cc = rep["cc"]
    doc.add_paragraph(
        f"Awareness of the Citizen's Charter was {_p0(cc['cc1']['pct'])}; of those it applied to, "
        f"{_p0(cc['cc2']['pct'])} found it easy to see and {_p0(cc['cc3']['pct'])} found it helpful.")
    for key, subject in (("cc1", "Awareness of the Citizen's Charter"),
                         ("cc2", "Visibility of the Citizen's Charter"),
                         ("cc3", "Helpfulness of the Citizen's Charter")):
        s = rep["cc"][key]
        n += 1
        _table_title(doc, n, subject, meta, N=s["base"])
        _table(doc, ["Answer", "Full text", "n", "%"],
               [[it.get("short", it["label"]), it["label"], it["n"], f"{it['pct']}%"]
                for it in rep[key]], numeric_from=2)

    doc.add_heading("Respondent profile", level=1)
    for title, key in (("sex", "sex"), ("age group", "age"), ("client type", "client_type"),
                       ("region of residence", "region"), ("service availed", "service")):
        items = rep["demo"].get(key) or []
        if not items:
            continue
        n += 1
        _table_title(doc, n, f"Respondents by {title}", meta,
                     N=sum(i["n"] for i in items))
        _table(doc, ["Category", "n", "%"],
               [[i["label"], i["n"], f"{i['pct']}%"] for i in items], numeric_from=1)

    c = rep.get("comments") or {}
    if c.get("positive") or c.get("negative") or c.get("other"):
        doc.add_heading(f"What clients said ({c.get('total', 0):,})", level=1)
        doc.add_paragraph(
            "Every written comment is listed below, grouped by type. Identical "
            "answers are shown once with a ×N repeat count.")
        for label, key in (("Appreciated", "positive"), ("To improve", "negative"),
                           ("Other comments", "other")):
            if c.get(key):
                doc.add_paragraph(label, style="Heading 3")
                for q in c[key]:
                    doc.add_paragraph(_comment_text(q), style="List Bullet")
                more = c.get(key + "_unique", len(c[key])) - len(c[key])
                if more > 0:
                    p = doc.add_paragraph(f"…and {more:,} more unique comments")
                    p.runs[0].italic = True
    return _save(doc)


def servqual_docx(sq, meta):
    doc = _docx_base(meta)
    if not sq.get("has_data"):
        doc.add_paragraph("No responses in this scope.")
        return _save(doc)
    g = sq.get("gap")
    gtxt = f"  ({g['label']} expectation, {g['shown']})" if g else ""
    _kv_line(doc, "Overall perception", f"{sq['overall']['shown']} / 7{gtxt}")
    _kv_line(doc, "Respondents", f"{sq['respondents']:,}")

    doc.add_heading("Service Quality Dimensions", level=1)
    _table_title(doc, 1, "Service-quality dimension scores and gap versus expectation",
                 meta, N=sq["respondents"])
    _table(doc, ["Dimension", "Items", "Mean", "vs Expectation", "Interpretation", "n"],
           [[d["dim"], d["members"], d["shown"], d.get("gap_shown", "—"),
             d.get("verdict") or "", d["n"]] for d in sq["dimensions"]], numeric_from=2)

    s = sq["summary"]
    servqual = s["servqual"] + (f" ({s['servqual_label']})" if s.get("servqual_label") else "")
    osq = s["osq"] + (f" ({s['osq_band']})" if s.get("osq_band") else "")
    doc.add_heading("Summary", level=1)
    _table_title(doc, 2, "SERVQUAL summary", meta, N=sq["respondents"])
    _table(doc, ["Metric", "Value"], [
        ["Total (sum of dimension means)", s["total"]],
        ["Average (mean of dimension means)", s["average"]],
        ["Expectation", s["expectation"]],
        ["SERVQUAL (Average − Expectation)", servqual],
        ["Overall Service Quality (item C)", osq],
    ])

    demo = sq.get("demo")
    if demo and demo.get("has"):
        doc.add_heading("Respondent profile", level=1)
        _table_title(doc, 3, "Respondent characteristics", meta, N=sq["respondents"])
        _table(doc, ["Category", "Ratio", "Captured"], [
            ["Male : Female", demo["sex_ratio"], demo["sex_total"]],
            ["DOH : Non-DOH", demo["aff_ratio"], demo["aff_total"]],
        ], numeric_from=2)

    c = sq.get("comments") or {}
    if c.get("items"):
        doc.add_heading(f"Respondent comments ({c.get('total', 0):,})", level=1)
        doc.add_paragraph(
            "Every written comment is listed below. Identical answers are shown "
            "once with a ×N repeat count.")
        for q in c["items"]:
            doc.add_paragraph(_comment_text(q), style="List Bullet")
        more = c.get("unique", len(c["items"])) - len(c["items"])
        if more > 0:
            p = doc.add_paragraph(f"…and {more:,} more unique comments")
            p.runs[0].italic = True
    return _save(doc)


def servqual_xlsx(sq, meta):
    """Raw-data Excel of the consolidated SERVQUAL (Type 2/3) report — the same
    dimension, summary and respondent-profile numbers the DOCX carries, one table
    per sheet, for offices that want to work with the figures in a spreadsheet.
    The XLSX = raw-data role in the per-format download standard."""
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill
    from openpyxl.utils import get_column_letter

    wb = Workbook()
    head_fill = PatternFill("solid", fgColor="2B6CB0")

    def _tab(ws, title, headers, rows):
        ws.cell(row=1, column=1, value=title).font = Font(bold=True, size=12)
        for c, name in enumerate(headers, start=1):
            cell = ws.cell(row=3, column=c, value=name)
            cell.font = Font(bold=True, color="FFFFFF"); cell.fill = head_fill
            ws.column_dimensions[get_column_letter(c)].width = max(12, min(48, len(str(name)) + 4))
        for r, row in enumerate(rows, start=4):
            for c, val in enumerate(row, start=1):
                ws.cell(row=r, column=c, value=val)

    info = wb.active; info.title = "Report"
    info.column_dimensions["A"].width = 16; info.column_dimensions["B"].width = 72
    lines = [("Report", meta.get("title", "")), ("Scope", meta.get("scope", "")),
             ("Place", meta.get("place", "")), ("Period", meta.get("period", "")),
             ("Generated", meta.get("generated", "")), ("Source", meta.get("source", ""))]
    if not sq.get("has_data"):
        lines.append(("Note", "No responses in this scope."))
    for r, (k, v) in enumerate(lines, start=1):
        info.cell(row=r, column=1, value=k).font = Font(bold=True)
        info.cell(row=r, column=2, value=str(v)).alignment = Alignment(wrap_text=True)
    if not sq.get("has_data"):
        buf = io.BytesIO(); wb.save(buf); return buf.getvalue()

    # Dimensions — Mean as a real number (d["value"]) so the sheet is computable;
    # the gap/verdict stay as the shown strings (they carry the +/- and label).
    _tab(wb.create_sheet("Dimensions"),
         "Service-quality dimension scores and gap versus expectation",
         ["Dimension", "Items", "Mean", "vs Expectation", "Interpretation", "n"],
         [[d["dim"], d["members"], d.get("value"), d.get("gap_shown", "—"),
           d.get("verdict") or "", d["n"]] for d in sq["dimensions"]])

    s = sq["summary"]
    servqual = s["servqual"] + (f" ({s['servqual_label']})" if s.get("servqual_label") else "")
    osq = s["osq"] + (f" ({s['osq_band']})" if s.get("osq_band") else "")
    _tab(wb.create_sheet("Summary"), "SERVQUAL summary", ["Metric", "Value"],
         [["Respondents", sq["respondents"]],
          ["Total (sum of dimension means)", s["total"]],
          ["Average (mean of dimension means)", s["average"]],
          ["Expectation", s["expectation"]],
          ["SERVQUAL (Average − Expectation)", servqual],
          ["Overall Service Quality (item C)", osq]])

    demo = sq.get("demo")
    if demo and demo.get("has"):
        _tab(wb.create_sheet("Respondent profile"), "Respondent characteristics",
             ["Category", "Ratio", "Captured"],
             [["Male : Female", demo["sex_ratio"], demo["sex_total"]],
              ["DOH : Non-DOH", demo["aff_ratio"], demo["aff_total"]]])

    # Individual submissions — one row per respondent, the disaggregated raw data
    # behind the consolidated numbers above (feedback #56). Each person's own
    # dimension means, their overall, expectation (A) and overall service
    # quality (C), plus when they answered, the activity, and any written comment.
    resp = sq.get("responses") or []
    if resp:
        dim_names = [d["dim"] for d in sq["dimensions"]]
        headers = (["#", "Submitted", "Activity"] + dim_names
                   + ["Overall", "Expectation (A)", "Overall SQ (C)", "Comment"])
        rows = []
        for i, r in enumerate(resp, start=1):
            dims = r.get("dims") or {}
            rows.append([i, r.get("when", ""), r.get("activity", "")]
                        + [dims.get(d) for d in dim_names]
                        + [r.get("overall"), r.get("expectation"), r.get("osq"),
                           r.get("comment", "")])
        _tab(wb.create_sheet("Responses"),
             "Individual submissions — each respondent's own scores (raw data)",
             headers, rows)

    # De-duplicated comment roll-up — every distinct written comment with how
    # many respondents gave it, most-repeated first. A compact companion to the
    # raw per-respondent Comment column above.
    c = sq.get("comments") or {}
    if c.get("items"):
        _tab(wb.create_sheet("Comments"),
             f"Respondent comments — de-duplicated ({c.get('total', 0)} total, "
             f"{c.get('unique', 0)} unique)",
             ["Comment", "Count"],
             [[q["text"], q["count"]] for q in c["items"]])

    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


# =====================================================================
# Charts (matplotlib) — shared by PDF + PPTX
# =====================================================================
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as _plt

_C = {
    "good": "#2F855A", "mid": "#B7791F", "bad": "#C53030",
    "bar": "#4C7FB8", "bar2": "#7FA8D0", "exp": "#E07A3F",
    "grid": "#E5E9EF", "ink": "#1C2330", "soft": "#5A6473",
}
_BAND_C = {"Outstanding": _C["good"], "Satisfactory": _C["good"],
           "Excellent": _C["good"], "Good": _C["good"],
           "Fair": _C["mid"], "Poor": _C["bad"]}
_plt.rcParams.update({"font.size": 9, "axes.titlesize": 11, "axes.titleweight": "bold",
                      "figure.facecolor": "white", "axes.edgecolor": "#C7CDD6"})


def _fig_png(fig, w, h):
    fig.set_size_inches(w, h)
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight", facecolor="white")
    _plt.close(fig)
    return buf.getvalue()


def _clean(ax, ygrid=True):
    for sp in ("top", "right"):
        ax.spines[sp].set_visible(False)
    ax.tick_params(length=0)
    ax.set_axisbelow(True)
    if ygrid:
        ax.yaxis.grid(True, color=_C["grid"], linewidth=0.8)


def _chart_sqd(rep):
    items = rep["sqd"]
    labels = [d["item"] for d in items]
    vals = [d["score"] or 0 for d in items]
    colors = [_BAND_C.get(d["band"], _C["bar"]) for d in items]
    fig, ax = _plt.subplots()
    bars = ax.bar(labels, vals, color=colors)
    ax.set_ylim(0, 108)
    ax.set_ylabel("Positive responses (%)")
    ax.set_xlabel("Service-quality item (SQD)")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 1.5, f"{v:.0f}", ha="center",
                va="bottom", fontsize=8, color=_C["ink"])
    _clean(ax)
    return _fig_png(fig, 8.4, 3.9)


def _chart_cc(rep):
    cc = rep["cc"]
    labels = ["Awareness\n(CC1)", "Visibility\n(CC2)", "Helpfulness\n(CC3)"]
    vals = [cc["cc1"]["pct"] or 0, cc["cc2"]["pct"] or 0, cc["cc3"]["pct"] or 0]
    fig, ax = _plt.subplots()
    bars = ax.bar(labels, vals, color=[_C["bar"], _C["bar"], _C["bar"]], width=0.55)
    ax.set_ylim(0, 108)
    ax.set_ylabel("Positive responses (%)")
    ax.set_xlabel("Citizen's Charter question")
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 1.5, f"{v:.0f}%", ha="center",
                va="bottom", fontsize=9, color=_C["ink"])
    _clean(ax)
    return _fig_png(fig, 7.2, 3.7)


def _chart_profile(rep):
    # Vertical stack — one full-width horizontal bar chart per characteristic, so
    # the labels and bars have room to breathe (the side-by-side layout crowded).
    cats = [("Sex", "sex"), ("Age group", "age"), ("Client type", "client_type")]
    present = [(t, k) for t, k in cats if rep["demo"].get(k)]
    if not present:
        present = [("Sex", "sex")]
    counts = [min(len(rep["demo"].get(k) or []), 6) for _, k in present]
    fig, axes = _plt.subplots(len(present), 1, squeeze=False,
                              gridspec_kw={"height_ratios": [max(c, 1) for c in counts]})
    axes = [a[0] for a in axes]
    for ax, (t, k) in zip(axes, present):
        items = (rep["demo"].get(k) or [])[:6][::-1]
        labels = [i["label"] for i in items]
        vals = [i["pct"] for i in items]
        ax.barh(labels, vals, color=_C["bar"], height=0.6)
        ax.set_title(t, fontsize=10, loc="left", pad=3, color=_C["ink"])
        ax.set_xlim(0, max(vals + [1]) * 1.22)
        for y, v in enumerate(vals):
            ax.text(v + 1.5, y, f"{v:.0f}%", va="center", fontsize=8.5, color=_C["soft"])
        for sp in ("top", "right", "bottom"):
            ax.spines[sp].set_visible(False)
        ax.tick_params(length=0)
        ax.set_xticks([])
        ax.tick_params(axis="y", labelsize=9)
    axes[-1].set_xlabel("Share of respondents (%)")   # bars are labelled inline
    fig.subplots_adjust(hspace=0.55)
    h = max(2.6, 0.5 * sum(counts) + 0.55 * len(present))
    return _fig_png(fig, 7.8, h)


def _chart_dims(sq):
    dims = sq["dimensions"]
    labels = [d["dim"] for d in dims]
    vals = [d.get("value") or 0 for d in dims]
    exp = sq["expectation"].get("value")
    fig, ax = _plt.subplots()
    bars = ax.bar(labels, vals, color=_C["bar"])
    ax.set_ylim(0, 8.0)          # headroom so value labels + legend never collide
    ax.set_ylabel("Mean rating (1–7)")
    ax.set_xlabel("SERVQUAL dimension")
    if exp:
        # Reference line labelled via the legend (clear of the bar value labels).
        ax.axhline(exp, color=_C["exp"], ls="--", lw=1.4, label=f"Expectation {exp:.2f}")
        ax.legend(loc="upper right", frameon=False, fontsize=8.5,
                  handlelength=1.6, borderaxespad=0.2)
    for b, v in zip(bars, vals):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.08, f"{v:.2f}", ha="center",
                va="bottom", fontsize=8.5, color=_C["ink"])
    _clean(ax)
    _plt.setp(ax.get_xticklabels(), rotation=12, ha="right")
    return _fig_png(fig, 8.4, 4.0)


def _chart_gap(sq):
    exp = sq["expectation"].get("value") or 0
    avg = sq["overall"].get("value") or 0
    fig, ax = _plt.subplots()
    bars = ax.bar(["What they\nexpected", "What they\nexperienced"], [exp, avg],
                  color=[_C["exp"], _C["bar"]], width=0.5)
    ax.set_ylim(0, 7.4)
    ax.set_ylabel("Mean rating (1–7)")
    ax.set_xlabel("Expectation vs. experience")
    for b, v in zip(bars, [exp, avg]):
        ax.text(b.get_x() + b.get_width() / 2, v + 0.07, f"{v:.2f}", ha="center",
                va="bottom", fontsize=10, color=_C["ink"])
    _clean(ax)
    return _fig_png(fig, 5.6, 3.9)


# Shared "how it's computed" text — one source for the PDF Methods box and the
# PPTX Methods slide (so they can't drift apart).
METHODS_ARTA = (
    "Figures are computed from the walk-in (CO-CSM) responses for the period shown. "
    "“Top-box” counts Agree and Strongly Agree answers. Bands: Outstanding ≥95%, "
    "Satisfactory 80–94.9%, Fair 60–79.9%, Poor <60%. Citizen's Charter percentages "
    "exclude “Not applicable” and blank answers. SQD = service-quality dimension.")
METHODS_SQ = (
    "Figures are computed from the Form-2/Form-3 SERVQUAL responses in scope. Ratings run "
    "1–7. SERVQUAL = average perception minus expectation; above zero means the experience "
    "exceeded expectations. OSQ (item C) is the overall-satisfaction question (1–4): "
    "Excellent ≥3.25, Good 2.5–3.24, Fair 1.75–2.49, Poor <1.75.")


# =====================================================================
# Narrative (warm plain-language) — descriptions of each visual
# =====================================================================

def _na_arta_summary(rep):
    n = rep["respondents"]
    bp = {"Outstanding": "an outstanding result", "Satisfactory": "a satisfactory result",
          "Fair": "a fair result", "Poor": "a result that needs attention"}.get(
        rep.get("overall_band"), "")
    s = (f"{n:,} people gave feedback on the walk-in service. Overall, "
         f"{_p0(rep.get('overall'))} of their answers across the eight service-quality "
         f"questions were positive")
    return s + (f" — {bp}." if bp else ".")


def _na_arta_sqd(rep):
    scored = [d for d in rep["sqd"] if d.get("score") is not None and d["item"] != "SQD0"]
    if not scored:
        return "Item-level ratings were not available for this period."
    hi = max(scored, key=lambda d: d["score"])
    lo = min(scored, key=lambda d: d["score"])
    s = (f"Satisfaction was high across every question. People were happiest with "
         f"“{_strip_period(hi['text'])}” ({hi['score']:.0f}%).")
    if lo["item"] != hi["item"] and lo["score"] < hi["score"]:
        s += f" The area with the most room to grow was “{_strip_period(lo['text'])}” ({lo['score']:.0f}%)."
    return s


def _na_arta_cc(rep):
    cc = rep["cc"]
    return (f"Awareness of the Citizen's Charter was {_p0(cc['cc1']['pct'])}. Of those it "
            f"applied to, {_p0(cc['cc2']['pct'])} found it easy to see and "
            f"{_p0(cc['cc3']['pct'])} found it helpful.")


def _na_arta_profile(rep):
    parts = []
    if rep["demo"].get("sex"):
        t = max(rep["demo"]["sex"], key=lambda i: i["n"])
        parts.append(f"most were {t['label'].lower()} ({t['pct']:.0f}%)")
    if rep["demo"].get("client_type"):
        t = max(rep["demo"]["client_type"], key=lambda i: i["n"])
        parts.append(f"{t['pct']:.0f}% were {t['label'].lower()} clients")
    if rep["demo"].get("age"):
        t = max(rep["demo"]["age"], key=lambda i: i["n"])
        parts.append(f"the largest age group was {t['label'].lower()}")
    return ("Among those who shared their details, " + "; ".join(parts) + ".") if parts else ""


def _na_sq_summary(sq):
    g = sq.get("gap")
    s = f"{sq['respondents']:,} participants rated their experience {sq['overall']['shown']} out of 7"
    if g and g.get("label"):
        s += f" — {g['label'].lower()} what they expected ({g['shown']})"
    return s + "."


def _na_sq_dims(sq):
    dims = [d for d in sq["dimensions"] if d.get("value") is not None]
    if not dims:
        return ""
    hi = max(dims, key=lambda d: d["value"])
    lo = min(dims, key=lambda d: d["value"])
    exceeded = sum(1 for d in dims if d.get("verdict") == "Exceeds")
    s = f"All {len(dims)} service-quality areas scored strongly, led by {hi['dim']} ({hi['shown']})."
    s += f" {exceeded} of {len(dims)} beat what participants expected."
    if lo["dim"] != hi["dim"]:
        s += f" {lo['dim']} ({lo['shown']}) had the most headroom."
    return s


def _na_sq_osq(sq):
    su = sq["summary"]
    return (f"Overall service quality came out at {su['osq']}"
            + (f", rated {su['osq_band']}." if su.get("osq_band") else "."))


# =====================================================================
# PDF (reportlab) — report-ready narrative with figures + captions
# =====================================================================
from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import cm
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, Image as RLImage, KeepTogether)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

_PDF_FONT, _PDF_FONT_B = "Helvetica", "Helvetica-Bold"
try:
    _ttf = os.path.join(os.path.dirname(matplotlib.__file__), "mpl-data", "fonts", "ttf")
    pdfmetrics.registerFont(TTFont("DejaVu", os.path.join(_ttf, "DejaVuSans.ttf")))
    pdfmetrics.registerFont(TTFont("DejaVu-B", os.path.join(_ttf, "DejaVuSans-Bold.ttf")))
    _PDF_FONT, _PDF_FONT_B = "DejaVu", "DejaVu-B"
except Exception:
    pass

_HEADBG = colors.HexColor("#EDF2F7")
_BOXBG = colors.HexColor("#F1F5F9")
_LINE = colors.HexColor("#D7DCE3")
_ALT = colors.HexColor("#F8FAFC")
_INK = colors.HexColor("#1C2330")
_SOFT = colors.HexColor("#5A6473")
_CONTENT_W = 16.0 * cm


def _pdf_styles():
    base = getSampleStyleSheet()["Normal"]

    def s(name, **kw):
        kw.setdefault("fontName", _PDF_FONT)
        return ParagraphStyle(name, parent=base, **kw)

    return {
        "title": s("t", fontName=_PDF_FONT_B, fontSize=18, textColor=_INK, leading=22, spaceAfter=2),
        "scope": s("sc", fontSize=10.5, textColor=_SOFT, leading=14, spaceAfter=1),
        "foot": s("ft", fontSize=8.5, textColor=_SOFT, leading=12, spaceAfter=12),
        # keepWithNext stops a section heading being stranded at the foot of a
        # page while its figure/table flows onto the next one.
        "h2": s("h2", fontName=_PDF_FONT_B, fontSize=13, textColor=_INK, leading=16,
                spaceBefore=15, spaceAfter=5, keepWithNext=1),
        "body": s("bd", fontSize=10, leading=15, spaceAfter=9),
        "caption": s("cap", fontSize=8.5, textColor=_SOFT, leading=12, spaceBefore=3, spaceAfter=12),
        "tcap": s("tc", fontName=_PDF_FONT_B, fontSize=9.5, textColor=_INK, leading=12,
                  spaceBefore=4, spaceAfter=3),
        "boxlabel": s("bl", fontName=_PDF_FONT_B, fontSize=10, textColor=_INK, spaceAfter=3),
        "boxbody": s("bb", fontSize=10, leading=15),
        "note": s("nt", fontSize=8.5, textColor=_SOFT, leading=12, spaceAfter=2),
        "cell": s("c", fontSize=8.5, leading=11),
        "cellr": s("cr", fontSize=8.5, leading=11, alignment=TA_RIGHT),
        "cellh": s("ch", fontName=_PDF_FONT_B, fontSize=8.5, leading=11),
        "cellhr": s("chr", fontName=_PDF_FONT_B, fontSize=8.5, leading=11, alignment=TA_RIGHT),
    }


def _pdf_grid(headers, rows, widths, st, numeric_from=None):
    def cell(val, i, header=False):
        right = numeric_from is not None and i >= numeric_from
        key = ("cellh" if header else "cell") + ("r" if right else "")
        return Paragraph(_xml_escape("" if val is None else str(val)), st[key])

    data = [[cell(h, i, True) for i, h in enumerate(headers)]]
    data += [[cell(v, i) for i, v in enumerate(r)] for r in rows]
    t = Table(data, colWidths=widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _HEADBG),
        ("GRID", (0, 0), (-1, -1), 0.5, _LINE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ALT]),
    ]))
    return t


def _cap_para(kind, num, subject, meta, N, style):
    """Publication caption: '<kind> N. <subject>, <place>, <time> (N = n)'."""
    loc = ", ".join(x for x in ((meta or {}).get("place"), (meta or {}).get("period")) if x)
    rest = subject + (f", {loc}" if loc else "") + (f" (N = {N:,})" if N is not None else "")
    return Paragraph(f"<b>{kind} {num}.</b> {_xml_escape(rest)}", style)


def _fig_block(heading, png, num, subject, st, meta=None, N=None, width=_CONTENT_W):
    """Heading + figure + caption as one unbreakable unit, so a section title is
    never left stranded on a page without its figure (keepWithNext alone is not
    reliable when the next flowable is a tall image)."""
    img = RLImage(io.BytesIO(png))
    img.drawWidth = width
    img.drawHeight = width * img.imageHeight / img.imageWidth
    return KeepTogether([
        Paragraph(_xml_escape(heading), st["h2"]),
        img,
        _cap_para("Figure", num, subject, meta, N, st["caption"]),
    ])


def _table_block(num, subject, grid, st, meta=None, N=None):
    return KeepTogether([_cap_para("Table", num, subject, meta, N, st["tcap"]), grid])


def _box(label, paragraphs, st, bg=_BOXBG):
    inner = [Paragraph(label, st["boxlabel"])] + paragraphs
    t = Table([[inner]], colWidths=[_CONTENT_W])
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), bg),
        ("BOX", (0, 0), (-1, -1), 0.5, _LINE),
        ("LEFTPADDING", (0, 0), (-1, -1), 9), ("RIGHTPADDING", (0, 0), (-1, -1), 9),
        ("TOPPADDING", (0, 0), (-1, -1), 7), ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


def _pdf_doc(meta, flow):
    buf = io.BytesIO()
    SimpleDocTemplate(buf, pagesize=A4, title=meta["title"],
                      topMargin=1.5 * cm, bottomMargin=1.5 * cm,
                      leftMargin=2.0 * cm, rightMargin=2.0 * cm).build(flow)
    return buf.getvalue()


def _pdf_head(st, meta):
    out = [Paragraph(_xml_escape(meta["title"]), st["title"])]
    if meta.get("scope"):
        out.append(Paragraph(_xml_escape(meta["scope"]), st["scope"]))
    out.append(Paragraph(
        f"Generated {_xml_escape(meta.get('generated', ''))} · Source: "
        f"{_xml_escape(meta.get('source', 'CSS-IS'))}", st["foot"]))
    return out


def arta_pdf(rep, meta):
    st = _pdf_styles()
    f = _pdf_head(st, meta)
    if not rep.get("has_data"):
        f.append(Paragraph("No walk-in / ARTA responses in this period.", st["body"]))
        return _pdf_doc(meta, f)

    f.append(_box("Summary", [Paragraph(_xml_escape(_na_arta_summary(rep)), st["boxbody"])], st))
    f.append(Spacer(1, 12))

    N = rep["respondents"]
    f.append(_fig_block("How satisfied people were", _chart_sqd(rep), 1,
                        "Client satisfaction by service-quality question (SQD0–SQD8)",
                        st, meta, N=N))
    f.append(Paragraph(_xml_escape(_na_arta_sqd(rep)), st["body"]))

    f.append(_fig_block("The Citizen's Charter", _chart_cc(rep), 2,
                        "Awareness, visibility and helpfulness of the Citizen's Charter",
                        st, meta, N=N))
    f.append(Paragraph(_xml_escape(_na_arta_cc(rep)), st["body"]))

    prof = _na_arta_profile(rep)
    if prof:
        f.append(_fig_block("Who responded", _chart_profile(rep), 3,
                            "Profile of respondents", st, meta, N=N))
        f.append(Paragraph(_xml_escape(prof), st["body"]))

    # Only show "What clients said" when there are actual quotes to display.
    c = rep.get("comments") or {}
    pos, neg, other = c.get("positive") or [], c.get("negative") or [], c.get("other") or []
    if pos or neg or other:
        block = [Paragraph("What clients said", st["h2"]),
                 Paragraph(_xml_escape(
                     f"{c.get('total', 0):,} people left a written comment; a few of the "
                     "most common are shown below (×N marks repeated answers). The full "
                     "de-duplicated list is in the DOCX reference."),
                     st["body"])]
        for label, quotes in (("Appreciated", pos), ("To improve", neg), ("Other comments", other)):
            if quotes:
                block.append(Paragraph(f"<b>{label}</b>", st["note"]))
                for q in quotes[:4]:
                    block.append(Paragraph("“" + _xml_escape(_comment_text(q)) + "”", st["body"]))
        f.append(KeepTogether(block[:3]))
        f.extend(block[3:])

    f.append(_box("Methods & notes", [Paragraph(_xml_escape(METHODS_ARTA),
        st["note"])], st, bg=colors.white))
    return _pdf_doc(meta, f)


def servqual_pdf(sq, meta):
    st = _pdf_styles()
    f = _pdf_head(st, meta)
    if not sq.get("has_data"):
        f.append(Paragraph("No responses in this scope.", st["body"]))
        return _pdf_doc(meta, f)

    f.append(_box("Summary", [Paragraph(_xml_escape(_na_sq_summary(sq) + " " + _na_sq_osq(sq)),
                                        st["boxbody"])], st))
    f.append(Spacer(1, 12))

    N = sq["respondents"]
    f.append(_fig_block("How the experience scored", _chart_dims(sq), 1,
                        "Service-quality dimension scores versus expectation", st, meta, N=N))
    f.append(Paragraph(_xml_escape(_na_sq_dims(sq)), st["body"]))

    f.append(_fig_block("Expectation versus experience", _chart_gap(sq), 2,
                        "Expectation versus experience", st, meta, N=N, width=9.0 * cm))
    s = sq["summary"]
    servqual = s["servqual"] + (f" ({s['servqual_label']})" if s.get("servqual_label") else "")
    osq = s["osq"] + (f" ({s['osq_band']})" if s.get("osq_band") else "")
    f.append(_table_block(1, "SERVQUAL summary", _pdf_grid(["Metric", "Value"], [
        ["Total (sum of dimension means)", s["total"]],
        ["Average (mean of dimension means)", s["average"]],
        ["Expectation", s["expectation"]],
        ["SERVQUAL (Average − Expectation)", servqual],
        ["Overall Service Quality (item C)", osq],
    ], [10.0 * cm, 6.0 * cm], st), st, meta, N=N))
    f.append(Spacer(1, 10))

    demo = sq.get("demo")
    if demo and demo.get("has"):
        f.append(Paragraph("Who responded", st["h2"]))
        f.append(Paragraph(_xml_escape(
            f"Of those who shared their details, the male-to-female split was "
            f"{demo['sex_ratio']} and the DOH to non-DOH split was {demo['aff_ratio']}."),
            st["body"]))

    f.append(_box("Methods & notes", [Paragraph(_xml_escape(METHODS_SQ), st["note"])],
        st, bg=colors.white))
    return _pdf_doc(meta, f)


# =====================================================================
# PPTX (python-pptx) — bold colour-block storytelling deck
# 16:9; each slide stands alone (footer carries scope + period); a narrative
# arc: title -> hero number -> per-beat insight slides -> quotes -> takeaways.
# =====================================================================
from pptx import Presentation
from pptx.util import Inches, Pt as _PPt
from pptx.dml.color import RGBColor as _PRGB
from pptx.enum.text import PP_ALIGN, MSO_ANCHOR
from pptx.enum.shapes import MSO_SHAPE
from PIL import Image as _PILImage

_DEEP, _ACCENT = "11365E", "2E86C1"
_GOODP, _MIDP, _SOFTP, _CARDBG = "2F855A", "B7791F", "5A6473", "F4F7FB"
_SW, _SH = 13.333, 7.5


def _ppt_new():
    prs = Presentation()
    prs.slide_width = Inches(_SW)
    prs.slide_height = Inches(_SH)
    return prs


def _slide(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])


def _bg(slide, hexc):
    f = slide.background.fill
    f.solid()
    f.fore_color.rgb = _PRGB.from_string(hexc)


def _rect(slide, l, t, w, h, hexc):
    sh = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(l), Inches(t), Inches(w), Inches(h))
    sh.fill.solid()
    sh.fill.fore_color.rgb = _PRGB.from_string(hexc)
    sh.line.fill.background()
    sh.shadow.inherit = False
    return sh


def _round(slide, l, t, w, h, hexc, line="E2E8F0"):
    sh = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, Inches(l), Inches(t), Inches(w), Inches(h))
    sh.fill.solid()
    sh.fill.fore_color.rgb = _PRGB.from_string(hexc)
    if line:
        sh.line.color.rgb = _PRGB.from_string(line)
        sh.line.width = _PPt(0.75)
    else:
        sh.line.fill.background()
    sh.shadow.inherit = False
    return sh


def _txt(slide, text, l, t, w, h, size=18, bold=False, color="1C2330",
         align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    tb = slide.shapes.add_textbox(Inches(l), Inches(t), Inches(w), Inches(h))
    tf = tb.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for i, ln in enumerate(str(text).split("\n")):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = align
        r = p.add_run()
        r.text = ln
        r.font.size = _PPt(size)
        r.font.bold = bold
        r.font.color.rgb = _PRGB.from_string(color)
    return tb


def _footer(slide, meta, page, dark=False):
    col = "8FA8C4" if dark else "9AA3AF"
    left = f"{meta.get('source', 'CSS-IS')}  -  {meta.get('scope', '')}"
    _txt(slide, left, 0.55, _SH - 0.48, 11.2, 0.4, size=9, color=col, anchor=MSO_ANCHOR.MIDDLE)
    _txt(slide, str(page), _SW - 1.1, _SH - 0.48, 0.6, 0.4, size=9, color=col,
         align=PP_ALIGN.RIGHT, anchor=MSO_ANCHOR.MIDDLE)


def _header(slide, headline):
    _rect(slide, 0, 0, _SW, 1.15, _ACCENT)
    _txt(slide, headline, 0.6, 0, _SW - 1.6, 1.15, size=24, bold=True, color="FFFFFF",
         anchor=MSO_ANCHOR.MIDDLE)


def _pic(slide, png, top, max_w=9.8, max_h=4.9):
    im = _PILImage.open(io.BytesIO(png))
    iw, ih = im.size
    ar = iw / ih
    w, h = max_w, max_w / ar
    if h > max_h:
        h, w = max_h, max_h * ar
    slide.shapes.add_picture(io.BytesIO(png), Inches((_SW - w) / 2), Inches(top),
                             width=Inches(w), height=Inches(h))


def _ppt_save(prs):
    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()


def _title_slide(prs, meta):
    s = _slide(prs)
    _bg(s, _DEEP)
    _rect(s, 0.8, 5.0, 3.2, 0.14, _ACCENT)
    _txt(s, meta["title"], 0.8, 2.0, 11.7, 2.4, size=40, bold=True, color="FFFFFF")
    if meta.get("scope"):
        _txt(s, meta["scope"], 0.8, 4.3, 11.7, 0.6, size=18, color="D6E4F0")
    _txt(s, f"Generated {meta.get('generated', '')} - {meta.get('source', 'CSS-IS')}",
         0.8, 6.7, 11.7, 0.4, size=11, color="8FA8C4")


def _hero(prs, meta, page, big, line):
    s = _slide(prs)
    _bg(s, _DEEP)
    _txt(s, big, 0.6, 1.6, 12.1, 2.4, size=104, bold=True, color="FFFFFF",
         align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
    _txt(s, line, 0.6, 4.25, 12.1, 1.5, size=24, color="D6E4F0", align=PP_ALIGN.CENTER)
    _footer(s, meta, page, dark=True)


def _chart_slide(prs, meta, page, headline, png, sub=None, cap=None):
    s = _slide(prs)
    _header(s, headline)
    top = 1.45
    if sub:
        _txt(s, sub, 0.6, 1.22, 12.1, 0.6, size=14, color="5A6473")
        top = 1.98
    _pic(s, png, top, max_h=(6.45 if cap else 6.7) - top)
    if cap:                                  # figure caption: subject · place, period (N)
        _txt(s, cap, 0.6, _SH - 0.86, 12.1, 0.35, size=10, color="8A93A0")
    _footer(s, meta, page)


def _methods_slide(prs, meta, page, body, basis):
    """A closing 'Methods & notes' slide — the same computation note the PDF carries."""
    s = _slide(prs)
    _header(s, "Methods & notes")
    _txt(s, basis, 0.6, 1.55, 12.1, 0.6, size=15, bold=True, color="334155")
    _txt(s, body, 0.6, 2.45, 12.1, 4.0, size=14, color="5A6473")
    _footer(s, meta, page)


def _quotes_slide(prs, meta, page, headline, items):
    s = _slide(prs)
    _header(s, headline)
    top, ch, gap, left, w = 1.5, 1.15, 0.22, 1.1, 11.1
    for text, color, label in items[:4]:
        _round(s, left, top, w, ch, _CARDBG)
        _rect(s, left, top, 0.13, ch, color)
        _txt(s, '"' + text + '"', left + 0.45, top + 0.1, w - 0.8, ch - 0.45, size=15,
             color="334155", anchor=MSO_ANCHOR.MIDDLE)
        _txt(s, label, left + 0.45, top + ch - 0.36, w - 0.8, 0.3, size=10, bold=True, color=color)
        top += ch + gap
    _footer(s, meta, page)


def _stats_slide(prs, meta, page, headline, stats):
    s = _slide(prs)
    _header(s, headline)
    n = len(stats)
    cw, gap = 4.2, 0.7
    left = (_SW - (n * cw + (n - 1) * gap)) / 2
    for label, value in stats:
        _round(s, left, 2.4, cw, 2.5, _CARDBG)
        _txt(s, value, left, 2.75, cw, 1.2, size=44, bold=True, color=_DEEP,
             align=PP_ALIGN.CENTER, anchor=MSO_ANCHOR.MIDDLE)
        _txt(s, label, left, 4.05, cw, 0.6, size=16, color="5A6473", align=PP_ALIGN.CENTER)
        left += cw + gap
    _footer(s, meta, page)


def _table_cell(cell, text, *, bold=False, size=11, color="1C2330",
                align=PP_ALIGN.LEFT, fill=None):
    cell.text = "" if text is None else str(text)
    cell.vertical_anchor = MSO_ANCHOR.MIDDLE
    cell.margin_left = Inches(0.08)
    cell.margin_right = Inches(0.08)
    cell.margin_top = Inches(0.03)
    cell.margin_bottom = Inches(0.03)
    if fill:
        cell.fill.solid()
        cell.fill.fore_color.rgb = _PRGB.from_string(fill)
    p = cell.text_frame.paragraphs[0]
    p.alignment = align
    r = p.runs[0] if p.runs else p.add_run()
    r.font.size = _PPt(size)
    r.font.bold = bold
    r.font.color.rgb = _PRGB.from_string(color)


def _table_slide(prs, meta, page, headline, headers, rows, sub=None, aligns=None,
                 col_widths=None):
    """A data-table slide (native pptx table, not a picture, so it stays
    selectable/editable) — header band, optional subhead, a striped table,
    footer. Used for rosters where the data itself is the content, not a chart."""
    s = _slide(prs)
    _header(s, headline)
    top = 1.45
    if sub:
        _txt(s, sub, 0.6, 1.2, 12.1, 0.45, size=13, color="5A6473")
        top = 1.82
    aligns = aligns or [PP_ALIGN.LEFT] * len(headers)
    left, width = 0.6, _SW - 1.2
    n_rows, n_cols = len(rows) + 1, len(headers)
    row_h = min(0.46, max(0.32, (_SH - 0.7 - top) / max(n_rows, 1)))
    shape = s.shapes.add_table(n_rows, n_cols, Inches(left), Inches(top),
                               Inches(width), Inches(row_h * n_rows))
    table = shape.table
    if col_widths:
        total = sum(col_widths)
        for i, w in enumerate(col_widths):
            table.columns[i].width = Inches(width * w / total)
    for c, h in enumerate(headers):
        _table_cell(table.cell(0, c), h, bold=True, size=12, color="FFFFFF",
                    align=aligns[c], fill=_ACCENT)
    for r, row in enumerate(rows, start=1):
        bg = "FFFFFF" if r % 2 else _CARDBG
        for c, val in enumerate(row):
            _table_cell(table.cell(r, c), val, size=11, align=aligns[c], fill=bg)
    _footer(s, meta, page)
    return s


def rp_roster_pptx(events, meta):
    """Per-activity resource-person roster deck — mirrors the paper 'Form 3.0
    (Resource Person)' sheet: one slide per activity, a table of every scored
    resource person with their Overall Service Quality (item C band) and
    SERVQUAL Score (dimension average minus expectation, with verdict).
    `events` is a list of build_events()-shaped dicts (each with a `speakers`
    list already carrying osq_shown/osq_band/gap_shown/verdict) — already
    filtered to the chosen org/period/activity scope by the caller."""
    prs = _ppt_new()
    _title_slide(prs, meta)
    slides = [(e, [sp for sp in e.get("speakers") or [] if sp.get("value") is not None])
              for e in events]
    slides = [(e, sp) for e, sp in slides if sp]
    if not slides:
        _txt(_slide(prs), "No resource-person activities in this scope.",
             0.8, 3, 11.7, 1, size=20)
        return _ppt_save(prs)

    pg = 1
    for e, speakers in slides:
        pg += 1
        sub = "  ·  ".join(x for x in (e.get("date_shown"), e.get("venue")) if x) or None
        rows = []
        for i, sp in enumerate(speakers, start=1):
            osq = sp["osq_shown"] + (f" ({sp['osq_band']})" if sp.get("osq_band") else "")
            sq = sp["gap_shown"] + (f" ({sp['verdict']})" if sp.get("verdict") else "")
            rows.append([i, sp["name"], osq, sq])
        _table_slide(prs, meta, pg, e.get("name") or "Activity",
                     ["#", "Staff Name", "Overall Service Quality", "SERVQUAL Score"], rows,
                     sub=sub, aligns=[PP_ALIGN.RIGHT, PP_ALIGN.LEFT, PP_ALIGN.CENTER, PP_ALIGN.CENTER],
                     col_widths=[0.6, 3.6, 2.8, 3.0])
    return _ppt_save(prs)


def _takeaways_slide(prs, meta, page, points, focus):
    s = _slide(prs)
    _bg(s, _DEEP)
    _txt(s, "Key takeaways", 0.8, 0.6, 11.7, 0.9, size=30, bold=True, color="FFFFFF")
    top = 1.95
    for p in points:
        _txt(s, "●", 0.85, top, 0.4, 0.5, size=13, color=_ACCENT, anchor=MSO_ANCHOR.MIDDLE)
        _txt(s, p, 1.4, top, 11.1, 0.95, size=18, color="EAF1F8")
        top += 1.0
    if focus:
        _rect(s, 0.85, top + 0.05, 11.6, 0.025, _ACCENT)
        _txt(s, "WHERE TO FOCUS NEXT", 0.85, top + 0.2, 11.6, 0.4, size=13, bold=True, color="6FB1E0")
        _txt(s, focus, 0.85, top + 0.62, 11.6, 1.1, size=18, color="FFFFFF")
    _footer(s, meta, page, dark=True)


def _takeaways_arta(rep):
    cc = rep["cc"]
    scored = [d for d in rep["sqd"] if d.get("score") is not None and d["item"] != "SQD0"]
    pts = [f"Overall satisfaction was {_p0(rep.get('overall'))}"
           + (f" - {rep['overall_band']}." if rep.get("overall_band") else ".")]
    if scored:
        hi = max(scored, key=lambda d: d["score"])
        pts.append(f'Highest-rated: "{_strip_period(hi["text"])}" ({hi["score"]:.0f}%).')
    pts.append(f"{_p0(cc['cc1']['pct'])} were aware of the Citizen's Charter and "
               f"{_p0(cc['cc3']['pct'])} found it helpful.")
    focus = None
    if scored:
        lo = min(scored, key=lambda d: d["score"])
        if lo["score"] < 100:
            focus = f'"{_strip_period(lo["text"])}" ({lo["score"]:.0f}%) - the area with the most room to grow.'
    return pts, focus


def _takeaways_sq(sq):
    dims = [d for d in sq["dimensions"] if d.get("value") is not None]
    g = sq.get("gap")
    pts = [f"Participants rated their experience {sq['overall']['shown']} / 7"
           + (f" - {g['label'].lower()} expectations." if g and g.get("label") else ".")]
    if dims:
        hi = max(dims, key=lambda d: d["value"])
        pts.append(f"Strongest area: {hi['dim']} ({hi['shown']}).")
    su = sq["summary"]
    pts.append(f"Overall service quality was {su['osq']}"
               + (f", rated {su['osq_band']}." if su.get("osq_band") else "."))
    focus = None
    if dims:
        lo = min(dims, key=lambda d: d["value"])
        focus = f"{lo['dim']} ({lo['shown']}) - the dimension with the most headroom."
    return pts, focus


def arta_pptx(rep, meta):
    prs = _ppt_new()
    _title_slide(prs, meta)
    if not rep.get("has_data"):
        _txt(_slide(prs), "No walk-in / ARTA responses in this period.", 0.8, 3, 11.7, 1, size=20)
        return _ppt_save(prs)

    loc = ", ".join(x for x in (meta.get("place"), meta.get("period")) if x)
    nresp = rep["respondents"]
    _fig = [0]

    def _cap(subject):
        _fig[0] += 1
        base = f"Figure {_fig[0]}. {subject}"
        if loc:
            base += f", {loc}"
        return base + f" (N = {nresp:,})"

    pg = 1
    band = rep.get("overall_band") or ""
    _hero(prs, meta, pg, _p0(rep.get("overall")),
          "Overall client satisfaction" + (f" - {band}" if band else "")
          + f"\n{rep['respondents']:,} clients gave feedback")
    pg += 1

    scored = [d for d in rep["sqd"] if d.get("score") is not None and d["item"] != "SQD0"]
    sqd_head = ("Outstanding across every question"
                if scored and all(d["band"] == "Outstanding" for d in scored)
                else "Strong satisfaction across the board")
    _chart_slide(prs, meta, pg, sqd_head, _chart_sqd(rep), sub=_na_arta_sqd(rep),
                 cap=_cap("Client satisfaction by service-quality question (SQD0–SQD8)"))
    pg += 1

    cc = rep["cc"]
    ccvals = [cc[k]["pct"] or 0 for k in ("cc1", "cc2", "cc3")]
    cc_head = ("Almost everyone knew, saw and valued the Charter" if min(ccvals) >= 90
               else "Citizen's Charter: awareness, visibility, helpfulness")
    _chart_slide(prs, meta, pg, cc_head, _chart_cc(rep),
                 sub=f"{_p0(cc['cc1']['pct'])} aware - {_p0(cc['cc2']['pct'])} found it easy to see - "
                     f"{_p0(cc['cc3']['pct'])} found it helpful",
                 cap=_cap("Awareness, visibility and helpfulness of the Citizen's Charter"))
    pg += 1

    prof = _na_arta_profile(rep)
    if prof:
        _chart_slide(prs, meta, pg, "Who we heard from", _chart_profile(rep), sub=prof,
                     cap=_cap("Profile of respondents"))
        pg += 1

    items = []
    for label, key, color in (("Appreciated", "positive", _GOODP), ("To improve", "negative", _MIDP),
                              ("Comment", "other", _SOFTP)):
        for q in (rep["comments"].get(key) or [])[:2]:
            items.append((_comment_text(q), color, label))
    if items:
        _quotes_slide(prs, meta, pg, "In their words", items)
        pg += 1

    _methods_slide(prs, meta, pg, METHODS_ARTA,
                   f"Based on {nresp:,} responses" + (f" · {loc}" if loc else ""))
    pg += 1

    pts, focus = _takeaways_arta(rep)
    _takeaways_slide(prs, meta, pg, pts, focus)
    return _ppt_save(prs)


def servqual_pptx(sq, meta):
    prs = _ppt_new()
    _title_slide(prs, meta)
    if not sq.get("has_data"):
        _txt(_slide(prs), "No responses in this scope.", 0.8, 3, 11.7, 1, size=20)
        return _ppt_save(prs)

    loc = ", ".join(x for x in (meta.get("place"), meta.get("period")) if x)
    nresp = sq["respondents"]
    _fig = [0]

    def _cap(subject):
        _fig[0] += 1
        base = f"Figure {_fig[0]}. {subject}"
        if loc:
            base += f", {loc}"
        return base + f" (N = {nresp:,})"

    pg = 1
    g = sq.get("gap")
    vtxt = f" - {g['label'].lower()} expectations" if g and g.get("label") else ""
    _hero(prs, meta, pg, f"{sq['overall']['shown']}/7",
          "Overall experience rating" + vtxt + f"\n{sq['respondents']:,} participants")
    pg += 1

    dims = [d for d in sq["dimensions"] if d.get("value") is not None]
    dims_head = ("Every area beat expectations"
                 if dims and all(d.get("verdict") == "Exceeds" for d in dims)
                 else "How each service area scored")
    _chart_slide(prs, meta, pg, dims_head, _chart_dims(sq), sub=_na_sq_dims(sq),
                 cap=_cap("Service-quality dimension scores versus expectation"))
    pg += 1

    gap_head = ("Experience beat expectations" if (g and g["label"] == "Exceeds")
                else "Expectation versus experience")
    _chart_slide(prs, meta, pg, gap_head, _chart_gap(sq), sub=_na_sq_osq(sq),
                 cap=_cap("Expectation versus experience"))
    pg += 1

    demo = sq.get("demo")
    if demo and demo.get("has"):
        _stats_slide(prs, meta, pg, "Who responded",
                     [("Male : Female", demo["sex_ratio"]), ("DOH : Non-DOH", demo["aff_ratio"])])
        pg += 1

    _methods_slide(prs, meta, pg, METHODS_SQ,
                   f"Based on {nresp:,} responses" + (f" · {loc}" if loc else ""))
    pg += 1

    pts, focus = _takeaways_sq(sq)
    _takeaways_slide(prs, meta, pg, pts, focus)
    return _ppt_save(prs)
