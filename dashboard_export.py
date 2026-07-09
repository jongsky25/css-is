"""
CSS-IS dashboard export
=======================

Turns any dashboard visual into a STANDALONE, fully-captioned artifact the user
can download — as an image (PNG / JPEG), a document (PDF), an editable data table
(Excel / CSV), or a slide (PPTX).

"Standalone" is the whole point: a downloaded chart must make sense on its own,
away from the screen. So every export carries the same caption standard:

    CSS-IS Visual Caption Standard
    ------------------------------
    Title    — what is measured            (e.g. "Walk-in Service Satisfaction — Pulse")
    Subtitle — Person · Place · Time        (whichever apply, in that order)
    Unit     — the measure + scale          (e.g. "Top-box %", "Mean rating, 1–7")
    Notes    — n, data flags, plain reading, method note (footnotes)
    Source   — system name · generation timestamp

The numbers themselves still come from the engine via dashboard_insights; this
module only frames and packages them. Charts are redrawn server-side (not screen
-scraped) so the output is clean and the caption is baked in.
"""

from __future__ import annotations
import io
import re
import math
import textwrap
from dataclasses import dataclass, field

import matplotlib
matplotlib.use("Agg")                       # headless: no display needed on the server
import matplotlib.pyplot as plt
from matplotlib.gridspec import GridSpec
from matplotlib.backends.backend_pdf import PdfPages

import pandas as pd
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill
from openpyxl.utils import get_column_letter
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

# House palette (matches the dashboard).
INK = "#1c2330"; SOFT = "#5a6473"; ACCENT = "#2b6cb0"; LINE = "#d6d9e0"
TONE = {"good": "#2f855a", "mid": "#b7791f", "bad": "#c53030", "neutral": "#2b6cb0"}
DIM_COLORS = ["#2b6cb0", "#2f855a", "#b7791f", "#805ad5", "#0987a0", "#c53030",
              "#d53f8c", "#718096"]

METHOD_NOTE = ("Scores are computed fresh from individual responses; the overall "
               "perception is dimension-weighted. Walk-in scores are the top-box "
               "(Agree + Strongly Agree) share.")

# Per-format wiring: matplotlib/office writer + MIME + extension.
FORMATS = {
    "png":  ("image/png", "png"),
    "jpeg": ("image/jpeg", "jpg"),
    "jpg":  ("image/jpeg", "jpg"),
    "pdf":  ("application/pdf", "pdf"),
    "csv":  ("text/csv; charset=utf-8", "csv"),
    "xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", "xlsx"),
    "pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation", "pptx"),
}


# =====================================================================
# The caption standard
# =====================================================================

@dataclass
class VisualMeta:
    title: str
    place: str = ""
    person: str = ""
    period: str = ""
    unit: str = ""
    notes: list = field(default_factory=list)
    source: str = "CSS-IS Client Satisfaction System"
    generated_at: str = ""
    n: int = None                               # sample size, shown on the title as (N = …)

    def subtitle(self):
        """Person · Place · Time (N = …) — the caption-standard subtitle. N is the
        sample size; it rides on the title line so every artifact's heading states
        who/where/when and how many responses it's built from."""
        base = " · ".join(b for b in (self.person, self.place, self.period) if b)
        if self.n is not None:
            tail = f"N = {self.n:,}"
            base = f"{base} · {tail}" if base else tail
        return base

    def footnotes(self):
        out = []
        if self.unit:
            out.append("Unit: " + self.unit)
        out.extend(n for n in self.notes if n)
        out.append(f"Source: {self.source} · Generated {self.generated_at}")
        return out

    def filename(self, ext):
        base = "_".join(b for b in (self.title, self.person, self.period) if b)
        base = re.sub(r"[^A-Za-z0-9]+", "_", base).strip("_") or "visual"
        return f"{base[:80]}.{ext}"


# =====================================================================
# Figure framing — title block + footnotes, identical for every chart
# =====================================================================

def _frame(fig, meta):
    """Add the standard title/subtitle/footnote block around the axes."""
    fig.patch.set_facecolor("white")
    fig.suptitle(meta.title, x=0.04, y=0.965, ha="left", fontsize=15.5,
                 fontweight="bold", color=INK)
    sub = meta.subtitle()
    if sub:
        fig.text(0.04, 0.915, sub, ha="left", fontsize=10.5, color=SOFT)
    foot = "\n".join("\n".join(textwrap.wrap(f, 120)) for f in meta.footnotes())
    fig.text(0.04, 0.015, foot, ha="left", va="bottom", fontsize=7.6, color="#7a8290")


def _new_fig(w=9.2, h=5.4):
    fig = plt.figure(figsize=(w, h), dpi=150)
    return fig


def _band_color(tone):
    return TONE.get(tone, ACCENT)


# ---- per-visual figure builders ----------------------------------------------

def _fig_pulse(payload, meta):
    """The whole-page vital signs: one panel per survey type, each showing that
    sign's headline + band and its recent-months micro-trend. Mirrors the three
    vital cards on the page (the per-card detail travels in the rich PDF/PPTX)."""
    tiles = payload.get("tiles") or []
    n = max(1, len(tiles))
    fig = _new_fig(3.7 * n + 0.5, 5.0)
    gs = GridSpec(1, n, left=0.07, right=0.96, top=0.72, bottom=0.27, wspace=0.34)
    for i, t in enumerate(tiles):
        ax = fig.add_subplot(gs[0, i])
        color = _band_color(t.get("tone"))
        ymax = t["ymax"]
        micro = t.get("micro") or []
        labels = [m["label"] for m in micro]
        vals = [m["value"] for m in micro]
        bars = ax.bar(range(len(vals)), [v if v is not None else 0 for v in vals],
                      color=color, width=0.62)
        ax.set_xticks(range(len(labels))); ax.set_xticklabels(labels, fontsize=8)
        ax.set_ylim(0, ymax * 1.16)
        ax.set_ylabel("Positive responses (%)" if ymax == 100 else "Mean rating (1–7)", fontsize=8.5)
        ax.set_xlabel("Recent months", fontsize=8.5)
        for b, v in zip(bars, vals):
            if v is not None:
                ax.text(b.get_x() + b.get_width() / 2, v + ymax * 0.02, _fmt(v, ymax),
                        ha="center", va="bottom", fontsize=8, fontweight="bold", color=INK)
        band = f"  ·  {t['band']}" if t.get("band") else ""
        ax.set_title(f"{t['title']}\n{t['headline']} {t['unit']}{band}", fontsize=10.5,
                     fontweight="bold", color=color, loc="left", pad=8)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    _frame(fig, meta)
    return fig


def _fig_person_single(payload, meta):
    """One-time engagement: a 'scores over time' line makes no sense for a single
    session, so lead with the headline score (+ band, respondents, how it compares
    to the bureau) and give the dimension breakdown the full width."""
    card = payload.get("card") or {}
    rp = card.get("rp") or {}
    cmp = payload.get("cmp") or {}
    ymax = payload["ymax"]
    fig = _new_fig(9.6, 5.4)
    # Headline scorecard (text only — no chart).
    score = rp.get("shown", "—")
    band = rp.get("band")
    n = rp.get("n", 0)
    fig.text(0.07, 0.79, f"{score}" + ("" if payload.get("scale") == "pct" else " / 7"),
             fontsize=27, fontweight="bold", color=INK)
    if band:
        fig.text(0.07, 0.725, band, fontsize=12, fontweight="bold", color=ACCENT)
    sub = f"{n:,} rating{'' if n == 1 else 's'} at this activity"
    if cmp.get("phrase"):
        sub += f"  ·  scoring {cmp['phrase']}"
    fig.text(0.07, 0.675, sub, fontsize=10, color=SOFT)
    # Full-width dimension breakdown.
    ax = fig.add_axes([0.30, 0.22, 0.66, 0.36])
    bd = payload.get("breakdown") or []
    bmax = payload.get("breakdown_ymax", ymax)
    names = [d["name"] for d in bd][::-1]; bvals = [d["value"] for d in bd][::-1]
    ax.barh(range(len(bvals)), bvals, color=ACCENT, height=0.62)
    ax.set_yticks(range(len(names))); ax.set_yticklabels(names, fontsize=9)
    ax.set_xlim(0, bmax * 1.12)
    ax.set_title(payload.get("breakdown_title", "Breakdown"), fontsize=10, color=SOFT, loc="left", pad=12)
    ax.set_xlabel(meta.unit, fontsize=9)
    for i, v in enumerate(bvals):
        ax.annotate(_fmt(v, bmax), (v, i), textcoords="offset points", xytext=(4, 0),
                    va="center", fontsize=8.5, fontweight="bold")
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    _frame(fig, meta)
    return fig


def _fig_person(payload, meta):
    """Left: the person's score over time. Right: their ranked breakdown.
    For a single activity there is no 'over time', so a dedicated scorecard layout."""
    if payload.get("single"):
        return _fig_person_single(payload, meta)
    fig = _new_fig(9.6, 5.6)
    gs = GridSpec(1, 2, width_ratios=[1.1, 1], left=0.10, right=0.97,
                  top=0.80, bottom=0.27, wspace=0.32)
    ymax = payload["ymax"]

    ax1 = fig.add_subplot(gs[0])
    trend = payload.get("trend") or []
    labels = [p["label"] for p in trend]; vals = [p["value"] for p in trend]
    # A period with activity but no ratable score carries value=None. Plot it as a
    # gap (NaN) rather than letting matplotlib choke on float(None) at draw time,
    # and skip its annotation. Mirrors the on-screen chart's NaN handling.
    plot_vals = [v if v is not None else float("nan") for v in vals]
    ax1.plot(range(len(plot_vals)), plot_vals, "-o", color=ACCENT, linewidth=2.5, markersize=6)
    _thin_xticks(ax1, trend, k=8)                       # ~8 labels on a long history
    ax1.tick_params(axis="x", rotation=20)
    shown = {int(t) for t in ax1.get_xticks()}          # annotate only the shown points
    ax1.set_ylim(0, (ymax or 1) * 1.1); ax1.set_title("Scores over time", fontsize=10, color=SOFT, loc="left", pad=16)
    ax1.set_xlabel("Period", fontsize=9); ax1.set_ylabel(meta.unit, fontsize=9)
    for i, v in enumerate(vals):
        if i in shown and v is not None:
            ax1.annotate(_fmt(v, ymax), (i, v), textcoords="offset points", xytext=(0, 8),
                         ha="center", fontsize=8.5, fontweight="bold")
    for s in ("top", "right"):
        ax1.spines[s].set_visible(False)

    ax2 = fig.add_subplot(gs[1])
    bd = payload.get("breakdown") or []
    bmax = payload.get("breakdown_ymax", ymax) or ymax or 1
    names = [d["name"] for d in bd][::-1]; bvals = [d["value"] for d in bd][::-1]
    bar_vals = [v if v is not None else 0 for v in bvals]   # a scoreless area = no bar
    ax2.barh(range(len(bar_vals)), bar_vals, color=ACCENT, height=0.62)
    ax2.set_yticks(range(len(names))); ax2.set_yticklabels(names, fontsize=8.5)
    ax2.set_xlim(0, bmax * 1.12); ax2.set_title(payload.get("breakdown_title", "Breakdown"),
                                                fontsize=10, color=SOFT, loc="left", pad=12)
    ax2.set_xlabel(meta.unit, fontsize=9)
    for i, v in enumerate(bvals):
        if v is not None:
            ax2.annotate(_fmt(v, bmax), (v, i), textcoords="offset points", xytext=(4, 0),
                         va="center", fontsize=8.5, fontweight="bold")
    for s in ("top", "right"):
        ax2.spines[s].set_visible(False)
    _frame(fig, meta)
    return fig


def _fig_event(payload, meta):
    """The activity's SERVQUAL scorecard at a glance: each dimension's mean (1–7)
    against what people expected, with the headline numbers (OSQ, Average, SERVQUAL)
    on top — matching the official report. Falls back to the ranked event dimensions
    when the full SERVQUAL report isn't available."""
    rep = payload.get("report")
    fig = _new_fig(9.6, 5.4)
    if rep and rep.get("dims"):
        ax = fig.add_axes([0.10, 0.30, 0.86, 0.45])
        dims = rep["dims"]
        labels = [d["label"] for d in dims]
        vals = [d.get("value") or 0 for d in dims]
        exp = rep.get("expectation")
        bars = ax.bar(range(len(vals)), vals, color=ACCENT, width=0.62)
        ax.set_ylim(0, 8.0)
        ax.set_xticks(range(len(labels)))
        ax.set_xticklabels(labels, fontsize=9, rotation=12, ha="right")
        ax.set_ylabel("Mean rating (1–7)", fontsize=9)
        ax.set_xlabel("SERVQUAL dimension", fontsize=9)
        if exp:
            ax.axhline(exp, color="#dd6b20", ls="--", lw=1.4, label=f"Expectation {exp:.2f}")
            ax.legend(loc="upper right", frameon=False, fontsize=8.5)
        for b, v in zip(bars, vals):
            ax.text(b.get_x() + b.get_width() / 2, v + 0.08, f"{v:.2f}", ha="center",
                    va="bottom", fontsize=8.5, color=INK)
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
        head = (f"Overall Service Quality {rep['osq_shown']}/4"
                + (f" ({rep['osq_grade']})" if rep.get("osq_grade") else "")
                + f"   ·   Average {rep['average_shown']}/7   ·   SERVQUAL {rep['servqual_shown']}"
                + (f" ({rep['servqual_verdict']})" if rep.get("servqual_verdict") else ""))
        fig.text(0.10, 0.84, head, ha="left", fontsize=10, color=SOFT)
    else:
        ax = fig.add_axes([0.34, 0.24, 0.62, 0.54])
        ranked = payload.get("ranked") or []
        names = [d["name"] for d in ranked][::-1]
        vals = [d["value"] for d in ranked][::-1]
        ax.barh(range(len(vals)), vals, color=ACCENT, height=0.62)
        ax.set_yticks(range(len(names))); ax.set_yticklabels(names, fontsize=9)
        ax.set_xlim(0, payload["ymax"] * 1.1)
        ax.set_title("Area by area (of 7)", fontsize=10, color=SOFT, loc="left", pad=12)
        ax.set_xlabel("Mean rating (1–7)", fontsize=9)
        for i, v in enumerate(vals):
            ax.annotate(f"{v:.1f}", (v, i), textcoords="offset points", xytext=(4, 0),
                        va="center", fontsize=8.5, fontweight="bold")
        for s in ("top", "right"):
            ax.spines[s].set_visible(False)
    _frame(fig, meta)
    return fig


def _fig_trends(payload, meta):
    """The whole Trends story in ONE standalone image, mirroring the redesigned page:
      • Overall headline with the SPC control band ('usual range'), the centre line,
        the 95% confidence ribbon and red dots on periods that 'stand out'.
      • 'The flip side — who rated low' (the unhappy-share line).
      • 'By area', with the movers highlighted (improved green, slipped amber) and the
        steady areas dimmed to grey.
    The y-axis auto-zooms and the x-labels thin out, as on screen."""
    seg = payload.get("segment")
    sent = payload.get("sentiment")
    nrows = 3 if (seg or sent) else 2
    fig = _new_fig(9.8, 9.0 if nrows == 2 else 11.6)
    gs = GridSpec(nrows, 2, figure=fig, left=0.09, right=0.97,
                  top=0.86 if nrows == 3 else 0.84, bottom=0.22 if nrows == 3 else 0.27,
                  hspace=0.6, wspace=0.26)
    series = payload.get("series") or []
    labels = [p["label"] for p in series]
    n = len(labels)
    xs = list(range(n))
    yv = [p["value"] for p in series]
    ymax = payload["ymax"]
    pct = payload.get("pct")
    ylo = payload.get("ylo", 0)
    yhi = payload.get("yhi") or ymax
    step = max(1, math.ceil(n / 10))
    shown = [i for i in range(n) if i % step == 0 or i == n - 1]

    # ---- headline: control band + confidence ribbon + signal dots ----------------
    axh = fig.add_subplot(gs[0, :])
    ctl = payload.get("control")
    conf = payload.get("conf")
    if conf and any(c is not None for c in conf):
        lo = [yv[i] - conf[i] if (yv[i] is not None and conf[i] is not None) else float("nan")
              for i in xs]
        hi = [yv[i] + conf[i] if (yv[i] is not None and conf[i] is not None) else float("nan")
              for i in xs]
        axh.fill_between(xs, lo, hi, color=ACCENT, alpha=0.14, linewidth=0,
                         label="Margin of error", zorder=1)
    if ctl:
        axh.axhspan(max(ylo, ctl["lcl"]), min(yhi, ctl["ucl"]), color="#1c2330",
                    alpha=0.05, zorder=0, label="Usual range")
        axh.axhline(ctl["cl"], color=SOFT, linestyle="--", linewidth=1, alpha=0.7, zorder=1)
    axh.plot(xs, yv, "-o", color=ACCENT, linewidth=2.6, markersize=5, label="Overall", zorder=5)
    sig = set((ctl or {}).get("signals") or [])
    sig_xy = [(i, yv[i]) for i in sorted(sig) if i < n and yv[i] is not None]
    if sig_xy:
        axh.plot([i for i, _ in sig_xy], [v for _, v in sig_xy], "o", color=TONE["bad"],
                 markersize=8, zorder=6, label="Stands out")
    for i in shown:
        if yv[i] is not None:
            axh.annotate(_fmt(yv[i], ymax), (i, yv[i]), textcoords="offset points",
                         xytext=(0, 9), ha="center", fontsize=8, fontweight="bold")
    axh.set_ylim(ylo, yhi + (yhi - ylo) * 0.10)
    if payload.get("gridvals"):
        axh.set_yticks(payload["gridvals"])
    axh.set_xticks(shown); axh.set_xticklabels([labels[i] for i in shown], fontsize=8.5)
    axh.set_ylabel(payload.get("ylabel", ""), fontsize=9)
    axh.set_xlabel(payload.get("xlabel", "Period"), fontsize=9)
    cr = payload.get("control_read")
    axh.set_title("Overall" + (f" — {cr['label']}" if cr else ""), fontsize=11.5,
                  fontweight="bold", loc="left")
    for s in ("top", "right"):
        axh.spines[s].set_visible(False)
    axh.legend(loc="lower left", fontsize=7.5, frameon=False, ncol=4)

    # ---- the flip side: who rated low (unhappy share, % only) --------------------
    axl = fig.add_subplot(gs[1, 0])
    un = payload.get("unhappy") or []
    uv = [p.get("value") for p in un]
    if pct and any(v is not None for v in uv):
        axl.plot(range(len(uv)), [v if v is not None else float("nan") for v in uv],
                 "-o", color="#dd6b20", linewidth=2, markersize=3.5)
        top = max([v for v in uv if v is not None] or [0])
        axl.set_ylim(0, max(2.0, top * 1.35))
        _thin_xticks(axl, un, k=6)
    else:
        axl.text(0.5, 0.5, "Not shown on the 1–7 average view", ha="center", va="center",
                 fontsize=8.5, color=SOFT, transform=axl.transAxes)
        axl.set_xticks([])
    axl.set_title("The flip side — who rated low", fontsize=10.5, fontweight="bold", loc="left")
    axl.set_ylabel("Share rating it low (%)", fontsize=8.5)
    axl.set_xlabel(payload.get("xlabel", "Period"), fontsize=8.5)
    for s in ("top", "right"):
        axl.spines[s].set_visible(False)

    # ---- by area: movers highlighted, steady dimmed ------------------------------
    axa = fig.add_subplot(gs[1, 1])
    dims = payload.get("dims") or []
    roles = payload.get("roles") or {}
    role_color = {"up": TONE["good"], "down": TONE["mid"]}
    if roles:
        for dm in dims:                                   # steady first, in grey
            if dm["name"] in roles:
                continue
            dv = [p["value"] for p in dm["points"]]
            axa.plot(range(len(dv)), dv, "-", color="#c2c8d2", linewidth=1.1,
                     alpha=0.85, zorder=2)
        for dm in dims:                                   # movers on top, coloured
            if dm["name"] not in roles:
                continue
            dv = [p["value"] for p in dm["points"]]
            axa.plot(range(len(dv)), dv, "-", color=role_color.get(roles[dm["name"]], ACCENT),
                     linewidth=2.6, zorder=4, label=dm["name"])
    else:                                                 # no clear movers → colour all
        for idx, dm in enumerate(dims):
            dv = [p["value"] for p in dm["points"]]
            axa.plot(range(len(dv)), dv, "-", color=DIM_COLORS[idx % len(DIM_COLORS)],
                     linewidth=1.6, alpha=0.85, label=dm["name"])
    axa.set_title("By area" + (" — movers highlighted" if roles else ""), fontsize=10.5,
                  fontweight="bold", loc="left")
    axa.set_ylabel(payload.get("ylabel", ""), fontsize=8.5)
    axa.set_xlabel(payload.get("xlabel", "Period"), fontsize=8.5)
    if labels:
        _thin_xticks(axa, series, k=6)
    for s in ("top", "right"):
        axa.spines[s].set_visible(False)
    if roles or (0 < len(dims) <= 6):
        axa.legend(loc="best", fontsize=7, frameon=False)

    # ---- Phase D: segment split (modality) ---------------------------------------
    if seg:
        axs = fig.add_subplot(gs[2, 0])
        # overall reference line behind the segment lines
        axs.plot(xs, yv, "-", color="#94a3b8", linewidth=2, alpha=0.6, label="Overall", zorder=2)
        for idx, dm in enumerate(seg.get("series_raw") or []):
            dv = [p["value"] for p in dm["points"]]
            axs.plot(range(len(dv)), dv, "-o", color=DIM_COLORS[idx % len(DIM_COLORS)],
                     linewidth=2.4, markersize=3, label=dm["name"], zorder=4)
        axs.set_title("By delivery format", fontsize=10.5, fontweight="bold", loc="left")
        axs.set_ylabel(payload.get("ylabel", ""), fontsize=8.5)
        axs.set_xlabel(payload.get("xlabel", "Period"), fontsize=8.5)
        if labels:
            _thin_xticks(axs, series, k=6)
        for s in ("top", "right"):
            axs.spines[s].set_visible(False)
        axs.legend(loc="best", fontsize=7, frameon=False)

    # ---- Phase D: verbatim-sentiment trend ---------------------------------------
    if sent:
        axn = fig.add_subplot(gs[2, 1] if seg else gs[2, :])
        sv = [p.get("value") for p in (sent.get("series") or [])]
        sn = sent.get("series") or []
        axn.plot(range(len(sv)), [v if v is not None else float("nan") for v in sv],
                 "-o", color=TONE["good"], linewidth=2, markersize=3.5)
        axn.set_ylim(0, 100)
        axn.set_title("What people wrote — tone over time", fontsize=10.5,
                      fontweight="bold", loc="left")
        axn.set_ylabel("Comments that read positive (%)", fontsize=8.5)
        axn.set_xlabel(payload.get("xlabel", "Period"), fontsize=8.5)
        if sn:
            _thin_xticks(axn, sn, k=6)
        for s in ("top", "right"):
            axn.spines[s].set_visible(False)

    _frame(fig, meta)
    return fig


def _thin_xticks(ax, series, k=8):
    """Show ~k evenly-spaced x-labels (always the last) for a period series."""
    n = len(series)
    if not n:
        return
    step = max(1, math.ceil(n / k))
    shown = [i for i in range(n) if i % step == 0 or i == n - 1]
    ax.set_xticks(shown)
    ax.set_xticklabels([series[i]["label"] for i in shown], fontsize=8)


def _fig_participation(payload, meta):
    """The Participation story in one figure: response VOLUME over time per survey
    type (top, full width), then event-coverage % and responses-per-event (bottom
    pair). Mirrors the on-screen redesign; axes are labelled per the figure standard."""
    fig = _new_fig(9.8, 6.4)
    gs = GridSpec(2, 2, figure=fig, left=0.09, right=0.97, top=0.80, bottom=0.30,
                  hspace=0.62, wspace=0.30)
    xlabel = payload.get("xlabel", "Period")

    axv = fig.add_subplot(gs[0, :])
    longest = []
    for idx, v in enumerate(payload.get("volumes") or []):
        s = v.get("series") or []
        if not s:
            continue
        if len(s) > len(longest):
            longest = s
        axv.plot(range(len(s)), [p["value"] for p in s], "-o", linewidth=2.2,
                 markersize=4, color=DIM_COLORS[idx % len(DIM_COLORS)], label=v["title"])
    axv.set_title("Responses over time", fontsize=10.5, fontweight="bold", loc="left")
    axv.set_ylabel("Responses", fontsize=9); axv.set_xlabel(xlabel, fontsize=9)
    _thin_xticks(axv, longest)
    axv.legend(fontsize=8, frameon=False, ncol=3, loc="upper left")
    for s in ("top", "right"):
        axv.spines[s].set_visible(False)

    axc = fig.add_subplot(gs[1, 0])
    cs = payload.get("cov_series") or []
    if cs:
        axc.plot(range(len(cs)), [p["value"] for p in cs], "-o", color="#2f855a",
                 linewidth=2.2, markersize=4)
    axc.set_title("Event coverage", fontsize=10.5, fontweight="bold", loc="left")
    axc.set_ylabel("Events with feedback (%)", fontsize=8.5); axc.set_xlabel(xlabel, fontsize=8.5)
    axc.set_ylim(0, 105); _thin_xticks(axc, cs, k=6)
    for s in ("top", "right"):
        axc.spines[s].set_visible(False)

    axe = fig.add_subplot(gs[1, 1])
    es = payload.get("eng_series") or []
    if es:
        axe.plot(range(len(es)), [p["value"] for p in es], "-o", color="#805ad5",
                 linewidth=2.2, markersize=4)
    axe.set_title("Responses per event", fontsize=10.5, fontweight="bold", loc="left")
    axe.set_ylabel("Responses / event", fontsize=8.5); axe.set_xlabel(xlabel, fontsize=8.5)
    _thin_xticks(axe, es, k=6)
    for s in ("top", "right"):
        axe.spines[s].set_visible(False)

    _frame(fig, meta)
    return fig


def _fig_teams_index(payload, meta):
    """Unit comparison: each section/division's activity score (mean 1–7), as a
    ranked horizontal bar — the snapshot of the Teams index roster."""
    rows = [r for r in (payload.get("rows") or []) if r["level"] != "bureau"]
    rows = sorted(rows, key=lambda r: r.get("value") or 0)[-16:]
    fig = _new_fig(9.6, max(5.0, 0.42 * len(rows) + 2.2))
    ax = fig.add_axes([0.30, 0.16, 0.66, 0.62])
    names = [r["short"] for r in rows]
    vals = [r.get("value") or 0 for r in rows]
    bars = ax.barh(range(len(names)), vals, color=ACCENT, height=0.66)
    ax.set_yticks(range(len(names))); ax.set_yticklabels(names, fontsize=8.5)
    ax.set_xlim(0, 7.4); ax.set_xlabel("Mean rating (1–7)", fontsize=9)
    for b, r in zip(bars, rows):
        ax.annotate(f"{r['score']}  ·  {r['events']} act · {r['respondents']:,}",
                    (r.get("value") or 0, b.get_y() + b.get_height() / 2),
                    textcoords="offset points", xytext=(5, 0), va="center", fontsize=7.8,
                    color=SOFT)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    _frame(fig, meta)
    return fig


def _fig_people(payload, meta):
    """The People roster leaderboard: top people by the fair-adjusted score (0–100),
    so walk-in (%) and speaker (/7) folk rank on one axis — the snapshot of the grid."""
    rows = sorted(payload.get("rows") or [], key=lambda r: r.get("adj", 0))[-15:]
    fig = _new_fig(9.6, max(5.0, 0.42 * len(rows) + 2.0))
    ax = fig.add_axes([0.32, 0.16, 0.64, 0.62])
    names = [r["name"] for r in rows]
    vals = [r.get("adj", 0) for r in rows]
    ax.barh(range(len(names)), vals, color=ACCENT, height=0.66)
    ax.set_yticks(range(len(names))); ax.set_yticklabels(names, fontsize=8)
    ax.set_xlim(0, 108); ax.set_xlabel("Fair-adjusted score (0–100)", fontsize=9)
    ax.set_title("Top rated (fair-adjusted)", fontsize=10, color=SOFT, loc="left", pad=10)
    for y, r in enumerate(rows):
        shown = (f"{r['rp']}/7" if r["rp"] else (r["arta"] or ""))
        ax.annotate(f"{shown} · {r['ratings']:,} ratings", (r.get("adj", 0), y),
                    textcoords="offset points", xytext=(5, 0), va="center", fontsize=7.6, color=SOFT)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    _frame(fig, meta)
    return fig


def _fig_verbatims(payload, meta):
    """What people talk about most — the top comment themes by mention count."""
    themes = (payload.get("themes") or [])[:12]
    fig = _new_fig(9.6, max(4.6, 0.42 * len(themes) + 2.2))
    ax = fig.add_axes([0.34, 0.18, 0.62, 0.58])
    names = [t["name"] for t in themes][::-1]
    vals = [t["count"] for t in themes][::-1]
    ax.barh(range(len(names)), vals, color=ACCENT, height=0.66)
    ax.set_yticks(range(len(names))); ax.set_yticklabels(names, fontsize=8.5)
    ax.set_xlim(0, max(vals) * 1.18 if vals else 1)   # headroom for the count labels
    ax.set_xlabel("Comments mentioning this theme", fontsize=9)
    ax.set_title("What people talk about most", fontsize=10, color=SOFT, loc="left", pad=10)
    for i, v in enumerate(vals):
        ax.annotate(f"{v:,}", (v, i), textcoords="offset points", xytext=(4, 0), va="center",
                    fontsize=8, color=SOFT)
    for s in ("top", "right"):
        ax.spines[s].set_visible(False)
    _frame(fig, meta)
    return fig


_FIGS = {"pulse": _fig_pulse, "person": _fig_person, "event": _fig_event,
         "trends": _fig_trends, "participation": _fig_participation,
         "team": _fig_person, "teams_index": _fig_teams_index, "people": _fig_people,
         "verbatims": _fig_verbatims}


def _fmt(v, ymax):
    if v is None:
        return "—"
    return f"{v:.0f}%" if ymax == 100 else f"{v:.1f}"


# =====================================================================
# Tables (the aggregate data behind the visual) — for CSV / XLSX / PPTX
# =====================================================================

def _tables(visual, payload):
    """Return [(caption, DataFrame)] — the numbers behind the chart."""
    out = []
    if visual == "pulse":
        for t in payload.get("tiles") or []:
            unit = "Positive (%)" if t["ymax"] == 100 else "Mean (1–7)"
            micro = t.get("micro") or []
            out.append((f"Recent months — {t['title']}", pd.DataFrame(
                [{"Period": m["label"], unit: _round(m["value"]), "Respondents (n)": m.get("n", 0)}
                 for m in micro])))
            ins = t.get("insights") or []
            if ins:
                out.append((f"Things to know — {t['title']}", pd.DataFrame(
                    [{"Aspect": i["label"], "What we found": i["text"]} for i in ins])))
        summary = payload.get("summary") or {}
        rows = ([{"Card": "What has been good", "Point": s} for s in (summary.get("good") or [])]
                + [{"Card": "Worth looking at", "Point": s} for s in (summary.get("watch") or [])])
        if summary.get("overall"):
            rows.append({"Card": "Overall pulse", "Point": summary["overall"]})
        if rows:
            out.append(("Summary", pd.DataFrame(rows)))
    elif visual == "person":
        if payload.get("single"):
            # One-time engagement: a timeline row is meaningless — summarise the session.
            rp = (payload.get("card") or {}).get("rp") or {}
            cmp = payload.get("cmp") or {}
            row = {"Score": _round(rp.get("value")), "Band": rp.get("band") or "",
                   "Respondents (n)": rp.get("n", 0)}
            if cmp.get("avg") is not None:
                row["Bureau average"] = _round(cmp["avg"])
                row["Difference"] = f"{cmp['diff']:+.1f}"
            out.append(("This session", pd.DataFrame([row])))
        else:
            trend = payload.get("trend") or []
            out.append(("Scores over time", pd.DataFrame(
                [{"Period": p["label"], "Score": _round(p["value"]), "Respondents (n)": p.get("n", 0)}
                 for p in trend])))
        bd = payload.get("breakdown") or []
        if bd:
            out.append((payload.get("breakdown_title", "Breakdown"), pd.DataFrame(
                [{"Area": d["name"], "Score": _round(d["value"]), "Responses (n)": d.get("n", "")}
                 for d in bd])))
        yoy = payload.get("yoy") or {}
        ybars = yoy.get("bars") or []
        if len(ybars) > 1:
            out.append(("Year on year", pd.DataFrame(
                [{"Year": b["label"], "Score": b.get("shown"), "Ratings (n)": b.get("n", 0)}
                 for b in ybars])))
        peers = payload.get("peers") or {}
        if peers:
            def _rk(side, axis):
                d = peers.get(side)
                return f"#{d[axis]['rank']} of {d['n']}" if d else "—"
            out.append(("Peer standing (rank)", pd.DataFrame([
                {"Axis": "Overall performance", "Section": _rk("section", "overall"),
                 "Bureau": _rk("bureau", "overall")},
                {"Axis": "Rating quality", "Section": _rk("section", "quality"),
                 "Bureau": _rk("bureau", "quality")},
                {"Axis": "Engagement (events)", "Section": _rk("section", "engagement"),
                 "Bureau": _rk("bureau", "engagement")},
            ])))
        coach = payload.get("coach") or {}
        crows = [{"Type": "What's going well", "Note": s} for s in (coach.get("praise") or [])]
        if coach.get("motivation"):
            crows.append({"Type": "Encouragement", "Note": coach["motivation"]})
        if crows:
            out.append(("Coaching notes", pd.DataFrame(crows)))
        ta = payload.get("ta") or {}
        if ta and ta.get("focus"):
            fo = ta["focus"]
            trows = [{"Area": fo["area"], "Kind": "Focus", "Note": fo.get("diagnosis", "")}]
            trows += [{"Area": fo["area"], "Kind": "Try this", "Note": a} for a in (fo.get("actions") or [])]
            if ta.get("secondary"):
                se = ta["secondary"]
                trows += [{"Area": se["area"], "Kind": "Also", "Note": a}
                          for a in (se.get("actions") or [])[:2]]
            if ta.get("keep"):
                trows.append({"Area": "Strength to keep", "Kind": "Keep", "Note": ta["keep"]})
            out.append(("Strengthen technical assistance", pd.DataFrame(trows)))
        # De-duplicated respondent comments — every distinct written comment with
        # how many people gave it, most-repeated first.
        c = payload.get("comments") or {}
        if c.get("items"):
            out.append(("Respondent comments", pd.DataFrame(
                [{"Comment": q["text"], "Count": q["count"]} for q in c["items"]])))
    elif visual == "event":
        rep = payload.get("report")
        if rep:
            out.append(("SERVQUAL — dimension by dimension", pd.DataFrame(
                [{"Dimension": d["label"], "Score (/7)": _round(d["value"]),
                  "SERVQUAL gap": d.get("gap_shown", "—"), "vs section": d.get("sec_delta_shown", ""),
                  "Interpretation": d.get("verdict") or ""} for d in rep["dims"]])))
            out.append(("SERVQUAL summary", pd.DataFrame([
                {"Metric": "Total (sum of dimension means)", "Value": rep["total_shown"]},
                {"Metric": "Average (mean of dimension means)", "Value": rep["average_shown"]},
                {"Metric": "Expectation", "Value": rep["expectation_shown"]},
                {"Metric": "SERVQUAL (Average − Expectation)", "Value": rep["servqual_shown"]},
                {"Metric": "Overall Service Quality (item C, 1–4)", "Value": rep["osq_shown"]},
            ])))
        else:
            out.append(("Area by area", pd.DataFrame(
                [{"Area": d["name"], "Score (of 7)": _round(d["value"])} for d in (payload.get("ranked") or [])])))
        demo = payload.get("demo") or {}
        drows = []
        if demo.get("mf_ratio"):
            drows.append({"Group": "Male : Female", "Value": demo["mf_ratio"]})
        if demo.get("affil_ratio"):
            drows.append({"Group": "DOH : Non-DOH", "Value": demo["affil_ratio"]})
        if drows:
            out.append(("Who responded", pd.DataFrame(drows)))
        # De-duplicated respondent comments — every distinct written comment with
        # how many people gave it, most-repeated first.
        c = payload.get("comments") or {}
        if c.get("items"):
            out.append(("Respondent comments", pd.DataFrame(
                [{"Comment": q["text"], "Count": q["count"]} for q in c["items"]])))
    elif visual == "trends":
        series = payload.get("series") or []
        rows = []
        for i, p in enumerate(series):
            row = {"Period": p["label"], "Overall": _round(p["value"]), "Respondents (n)": p["n"]}
            for dm in payload.get("dims") or []:
                row[dm["name"]] = _round(dm["points"][i]["value"]) if i < len(dm["points"]) else None
            rows.append(row)
        out.append(("Trend by period", pd.DataFrame(rows)))
        un = payload.get("unhappy") or []
        if any(p.get("value") is not None for p in un):
            out.append(("Who rated low (unhappy share)", pd.DataFrame(
                [{"Period": p["label"], "Rated it low (%)": _round(p["value"]),
                  "Respondents (n)": p.get("n", 0)} for p in un])))
        mv = payload.get("movers") or {}
        mrows = []
        if mv.get("improved"):
            mrows.append({"Area": mv["improved"]["name"], "Movement": "Most improved",
                          "From": mv["improved"]["from_s"], "To": mv["improved"]["to_s"]})
        if mv.get("watch"):
            mrows.append({"Area": mv["watch"]["name"], "Movement": "Slipped most",
                          "From": mv["watch"]["from_s"], "To": mv["watch"]["to_s"]})
        if mrows:
            out.append(("What's moving", pd.DataFrame(mrows)))
        seg = payload.get("segment")
        if seg and seg.get("series_raw"):
            srows = []
            for i, p in enumerate(series):
                row = {"Period": p["label"]}
                for dm in seg["series_raw"]:
                    pts = dm["points"]
                    row[dm["name"]] = _round(pts[i]["value"]) if i < len(pts) else None
                srows.append(row)
            out.append(("By delivery format", pd.DataFrame(srows)))
        sent = payload.get("sentiment")
        if sent and sent.get("series"):
            out.append(("Comment tone over time", pd.DataFrame(
                [{"Period": p["label"], "Read as positive (%)": _round(p["value"]),
                  "Comments (n)": p.get("n", 0)} for p in sent["series"]])))
    elif visual == "participation":
        for v in payload.get("volumes") or []:
            s = v.get("series") or []
            if s:
                out.append((f"Responses over time — {v['title']}", pd.DataFrame(
                    [{"Period": p["label"], "Responses": p["value"]} for p in s])))
        cs = payload.get("cov_series") or []
        if cs:
            out.append(("Event coverage over time", pd.DataFrame(
                [{"Period": p["label"], "Events with feedback (%)": _round(p["value"]),
                  "Events (n)": p.get("n", 0)} for p in cs])))
        es = payload.get("eng_series") or []
        if es:
            out.append(("Responses per event", pd.DataFrame(
                [{"Period": p["label"], "Responses per event": _round(p["value"])} for p in es])))
        bu = [u for u in (payload.get("by_unit") or []) if u.get("count")]
        if bu:
            out.append(("Where feedback comes from", pd.DataFrame(
                [{"Unit": u["label"], "Responses": u["count"],
                  "Per event": u.get("per_event_s", "—"),
                  "Movement": {"up": "▲ grew most", "down": "▼ fell most"}.get(u.get("role"), "")}
                 for u in bu])))
        blind = payload.get("blind") or []
        if blind:
            out.append(("Blind spots", pd.DataFrame([{"Gap": b["text"]} for b in blind])))
    elif visual == "team":
        trend = payload.get("trend") or []
        if trend:
            out.append(("Activity scores over time", pd.DataFrame(
                [{"Period": p["label"], "Score (/7)": _round(p["value"]), "Responses (n)": p.get("n", 0)}
                 for p in trend])))
        bd = payload.get("breakdown") or []
        if bd:
            out.append(("Event areas, strongest to weakest", pd.DataFrame(
                [{"Area": d["name"], "Score (/7)": _round(d["value"])} for d in bd])))
        ybars = (payload.get("yoy") or {}).get("bars") or []
        if len(ybars) > 1:
            out.append(("Year on year", pd.DataFrame(
                [{"Year": b["label"], "Score (/7)": b.get("shown"), "Ratings (n)": b.get("n", 0)}
                 for b in ybars])))
        grp = (payload.get("standing") or {}).get("group") or {}
        if grp:
            out.append(("Standing among siblings", pd.DataFrame([
                {"Axis": "Overall performance", "Rank": f"#{grp['overall']['rank']} of {grp['n']}"},
                {"Axis": "Rating quality", "Rank": f"#{grp['quality']['rank']} of {grp['n']}"},
                {"Axis": "Engagement (activities)", "Rank": f"#{grp['engagement']['rank']} of {grp['n']}"},
            ])))
        coach = payload.get("coach") or {}
        crows = [{"Type": "What's going well", "Note": s} for s in (coach.get("praise") or [])]
        if coach.get("motivation"):
            crows.append({"Type": "Encouragement", "Note": coach["motivation"]})
        if crows:
            out.append(("Coaching notes", pd.DataFrame(crows)))
        ta = payload.get("ta") or {}
        if ta.get("focus"):
            fo = ta["focus"]
            trows = [{"Area": fo["area"], "Kind": "Focus", "Note": fo.get("diagnosis", "")}]
            trows += [{"Area": fo["area"], "Kind": "Try this", "Note": a} for a in (fo.get("actions") or [])]
            if ta.get("keep"):
                trows.append({"Area": "Strength to keep", "Kind": "Keep", "Note": ta["keep"]})
            out.append(("Strengthen technical assistance", pd.DataFrame(trows)))
    elif visual == "teams_index":
        out.append(("Unit comparison", pd.DataFrame(
            [{"Unit": r["short"], "Level": r["level"].capitalize(), "Score (/7)": _round(r["value"]),
              "Band": r.get("band") or "", "Activities": r["events"], "Respondents": r["respondents"],
              "Badges": r["badges"]} for r in (payload.get("rows") or [])])))
    elif visual == "people":
        out.append(("People roster", pd.DataFrame(
            [{"Name": r["name"], "Affiliation": "Internal" if r["is_internal"] else "External",
              "Section": r["section"], "Walk-in": r["arta"] or "", "Speaker (/7)": r["rp"] or "",
              "Ratings": r["ratings"], "Confidence": r["confidence"], "Badges": r["badges"]}
             for r in (payload.get("rows") or [])])))
        pr = payload.get("profile") or {}
        if pr:
            srows = [{"Metric": "People", "Value": pr.get("people")},
                     {"Metric": "Total ratings", "Value": pr.get("ratings")}]
            if pr.get("avg") is not None:
                srows.append({"Metric": "Average speaker score",
                              "Value": f"{pr['avg']}/7 ({pr.get('band')})"})
            if pr.get("avg_topbox") is not None:
                srows.append({"Metric": "Average walk-in top-box", "Value": f"{pr['avg_topbox']}%"})
            srows.append({"Metric": "Badges earned", "Value": pr.get("badges")})
            out.append(("Scope profile", pd.DataFrame(srows)))
    elif visual == "verbatims":
        out.append(("Comments", pd.DataFrame(
            [{"Date": r.get("when", ""), "Form": r.get("form", ""), "Topic": r.get("topic", ""),
              "Type": r["type"], "Item": r.get("item", ""), "Comment": r["text"]}
             for r in (payload.get("rows") or [])])))
        themes = payload.get("themes") or []
        if themes:
            out.append(("Themes", pd.DataFrame(
                [{"Theme": t["name"], "Mentions": t["count"]} for t in themes])))
    return out or [("Data", pd.DataFrame())]


def _round(v):
    return None if v is None else round(v, 2)


# =====================================================================
# Packaging — bytes for each format
# =====================================================================

# Visuals that ship the full per-format treatment (report-ready narrative PDF +
# storytelling PPTX), built by dashboard_docs. PNG/JPEG stay the single combined
# figure; CSV/XLSX stay the data + Details sheet. Other visuals fall back to the
# figure-in-a-wrapper PDF/PPTX until they get the same uplift.
import dashboard_docs as dd
_RICH = {"trends": (dd.trends_pdf, dd.trends_pptx),
         "pulse": (dd.pulse_pdf, dd.pulse_pptx),
         "person": (dd.person_pdf, dd.person_pptx),
         "participation": (dd.participation_pdf, dd.participation_pptx),
         "event": (dd.event_pdf, dd.event_pptx),
         "team": (dd.team_pdf, dd.team_pptx),
         "teams_index": (dd.teams_index_pdf, dd.teams_index_pptx),
         "people": (dd.people_pdf, dd.people_pptx),
         "verbatims": (dd.verbatims_pdf, dd.verbatims_pptx)}


def export(visual, payload, meta, fmt):
    """Return (bytes, mime, ext) for one visual in one format."""
    fmt = (fmt or "png").lower()
    if fmt not in FORMATS:
        raise ValueError(f"Unsupported format: {fmt}")
    mime, ext = FORMATS[fmt]
    rich = _RICH.get(visual)
    if fmt in ("png", "jpeg", "jpg"):
        data = _fig_bytes(_FIGS[visual](payload, meta), "jpeg" if fmt == "jpg" else fmt)
    elif fmt == "pdf":
        data = rich[0](payload, meta) if rich else _fig_bytes(_FIGS[visual](payload, meta), "pdf")
    elif fmt == "csv":
        data = _csv_bytes(_tables(visual, payload), meta)
    elif fmt == "xlsx":
        data = _xlsx_bytes(_tables(visual, payload), meta)
    else:  # pptx
        if rich:
            data = rich[1](payload, meta)
        else:
            fig = _FIGS[visual](payload, meta)
            data = _pptx_bytes(_fig_bytes(fig, "png"), _tables(visual, payload), meta)
    return data, mime, ext


def _fig_bytes(fig, fmt):
    buf = io.BytesIO()
    fig.savefig(buf, format=fmt, facecolor="white")
    plt.close(fig)
    return buf.getvalue()


def _meta_lines(meta):
    lines = [("Title", meta.title)]
    if meta.person:
        lines.append(("Person", meta.person))
    if meta.place:
        lines.append(("Place", meta.place))
    if meta.period:
        lines.append(("Time", meta.period))
    if meta.n is not None:
        lines.append(("Respondents (N)", f"{meta.n:,}"))
    if meta.unit:
        lines.append(("Unit", meta.unit))
    for n in meta.notes:
        if n:
            lines.append(("Note", n))
    lines.append(("Source", meta.source))
    lines.append(("Generated", meta.generated_at))
    return lines


def _csv_bytes(tables, meta):
    sio = io.StringIO()
    for k, v in _meta_lines(meta):
        sio.write(f"# {k}: {v}\n")
    sio.write("\n")
    for cap, df in tables:
        sio.write(f"# {cap}\n")
        df.to_csv(sio, index=False)
        sio.write("\n")
    return sio.getvalue().encode("utf-8-sig")          # BOM so Excel opens it cleanly


def _xlsx_bytes(tables, meta):
    wb = Workbook()
    info = wb.active; info.title = "Details"
    info.column_dimensions["A"].width = 16
    info.column_dimensions["B"].width = 90
    for r, (k, v) in enumerate(_meta_lines(meta), start=1):
        a = info.cell(row=r, column=1, value=k); a.font = Font(bold=True)
        b = info.cell(row=r, column=2, value=str(v)); b.alignment = Alignment(wrap_text=True)
    head_fill = PatternFill("solid", fgColor="2B6CB0")
    for cap, df in tables:
        ws = wb.create_sheet(_safe_sheet(cap))
        ws.cell(row=1, column=1, value=cap).font = Font(bold=True, size=12)
        if df.empty:
            continue
        cols = list(df.columns)
        for c, name in enumerate(cols, start=1):
            cell = ws.cell(row=3, column=c, value=str(name))
            cell.font = Font(bold=True, color="FFFFFF"); cell.fill = head_fill
            ws.column_dimensions[get_column_letter(c)].width = max(12, min(40, len(str(name)) + 4))
        for r, (_, row) in enumerate(df.iterrows(), start=4):
            for c, name in enumerate(cols, start=1):
                ws.cell(row=r, column=c, value=_cell(row[name]))
    buf = io.BytesIO(); wb.save(buf); return buf.getvalue()


def _pptx_bytes(png_bytes, tables, meta):
    prs = Presentation()                                # 10 x 7.5 in
    blank = prs.slide_layouts[6]

    # Slide 1 — the chart (caption already baked into the image).
    s1 = prs.slides.add_slide(blank)
    pic = s1.shapes.add_picture(io.BytesIO(png_bytes), Inches(0.3), Inches(0.4), width=Inches(9.4))
    # footer source line
    _textbox(s1, f"Source: {meta.source} · Generated {meta.generated_at}",
             Inches(0.3), Inches(7.0), Inches(9.4), Inches(0.4), size=9, color="7A8290")

    # Slide 2 — the data + caption (editable).
    s2 = prs.slides.add_slide(blank)
    _textbox(s2, meta.title, Inches(0.4), Inches(0.3), Inches(9.2), Inches(0.6),
             size=22, bold=True, color="1C2330")
    if meta.subtitle():
        _textbox(s2, meta.subtitle(), Inches(0.4), Inches(0.95), Inches(9.2), Inches(0.4),
                 size=12, color="5A6473")
    cap, df = tables[0]
    top = Inches(1.5)
    if not df.empty:
        _add_table(s2, df, Inches(0.4), top, Inches(9.2))
    foot = "  ·  ".join(meta.footnotes())
    _textbox(s2, foot, Inches(0.4), Inches(6.9), Inches(9.2), Inches(0.5), size=8, color="7A8290")

    buf = io.BytesIO(); prs.save(buf); return buf.getvalue()


# ---- pptx + xlsx helpers ------------------------------------------------------

def _textbox(slide, text, left, top, width, height, size=12, bold=False, color="000000"):
    tb = slide.shapes.add_textbox(left, top, width, height)
    tf = tb.text_frame; tf.word_wrap = True
    p = tf.paragraphs[0]; run = p.add_run(); run.text = text
    run.font.size = Pt(size); run.font.bold = bold
    run.font.color.rgb = RGBColor.from_string(color)
    return tb


def _add_table(slide, df, left, top, width, max_rows=12):
    cols = list(df.columns)
    shown = df.head(max_rows)
    rows = len(shown) + 1
    tbl = slide.shapes.add_table(rows, len(cols), left, top, width, Inches(0.4 * rows)).table
    for c, name in enumerate(cols):
        cell = tbl.cell(0, c)
        cell.fill.solid(); cell.fill.fore_color.rgb = RGBColor.from_string("2B6CB0")
        cell.text_frame.clear()
        run = cell.text_frame.paragraphs[0].add_run()
        run.text = str(name); run.font.size = Pt(11); run.font.bold = True
        run.font.color.rgb = RGBColor.from_string("FFFFFF")
    for r, (_, row) in enumerate(shown.iterrows(), start=1):
        for c, name in enumerate(cols):
            cell = tbl.cell(r, c)
            cell.text_frame.clear()
            run = cell.text_frame.paragraphs[0].add_run()
            run.text = _cell(row[name], ""); run.font.size = Pt(10)
    return tbl


def _cell(v, blank_for_none="—"):
    if v is None or (isinstance(v, float) and v != v):     # None / NaN
        return blank_for_none
    if isinstance(v, float):
        return f"{v:.2f}".rstrip("0").rstrip(".")
    return str(v)


def _safe_sheet(name):
    s = re.sub(r"[\\/?*\[\]:]", " ", str(name)).strip()[:31]
    return s or "Data"
