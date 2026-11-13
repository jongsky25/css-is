"""Public advisory poster: the BLHSD "ADVISORY" image generated from an activity's link-tree details.

The layout follows the office's own advisory image (portrait, 1272 x 1800 design units, which is A4 within 0.1%):
white letterhead, a green ADVISORY band with a yellow number box, a cream body (headline, attention line, body
text, a deadlines-and-links table) and a green/yellow footer holding the QR code and the contact person.

This module is pure: it draws from a plain dict and touches no database, network or clock. Persistence, numbering
and permissions live in `activity_advisory.py` and its routes. Like `certificate.py` the result is built in memory.

Text supports `**bold**` runs. Text that cannot fit even at the smallest size raises `AdvisoryTooLong`, so the
editor can say so instead of publishing a clipped image."""
from __future__ import annotations

import io
import os
import re
from functools import lru_cache

from PIL import Image, ImageDraw, ImageFont

_ASSETS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "assets")
_DIR = os.path.join(_ASSETS, "advisory")

W, H = 1272, 1800                       # design units; the default render is 2x
GREEN, YELLOW, CREAM = (14, 54, 54), (242, 185, 58), (236, 232, 226)
INK, WHITE, PAPER_TEXT = (26, 26, 26), (255, 255, 255), (250, 246, 238)
GRID = (96, 96, 96)

BODY_TOP, BODY_BOTTOM = 397, 1503       # the cream area between the number band and the footer
CONTENT_L, CONTENT_R = 83, 1210
MAX_ROWS = 8
LIMITS = {"headline": 180, "attention": 420, "body": 1100, "label": 90, "value": 220, "link_text": 160,
          "contact_name": 90, "contact_phone": 60, "contact_email": 90}
MEASURE = 4                              # text is measured at 4x so wrapping does not depend on the output scale
FIT_STEPS = (1.0, 0.94, 0.88, 0.82, 0.76, 0.70)


class AdvisoryTooLong(ValueError):
    """The text does not fit the poster even at the smallest size."""


# ---------------------------------------------------------------------------------------------- fonts

_SANS = {"regular": "Poppins-Regular.ttf", "medium": "Poppins-Medium.ttf",
         "semibold": "Poppins-SemiBold.ttf", "bold": "Poppins-Bold.ttf"}


@lru_cache(maxsize=256)
def _font(kind: str, bold: bool, px: int):
    """`kind`: sans (Poppins), serif (Libre Caslon Text, body) or title (Fraunces). Sizes are in pixels."""
    px = max(4, int(px))
    if kind == "sans":
        return ImageFont.truetype(os.path.join(_DIR, _SANS["bold" if bold is True else bold or "regular"]), px)
    if kind == "serif":
        f = ImageFont.truetype(os.path.join(_DIR, "LibreCaslonText.ttf"), px)
        f.set_variation_by_axes([700 if bold else 400])
        return f
    f = ImageFont.truetype(os.path.join(_DIR, "Fraunces.ttf"), px)          # axes: optical size, weight, softness, wonk
    f.set_variation_by_axes([72, 700, 0, 0])
    return f


def _width(kind, bold, size, text):
    return _font(kind, bold, round(size * MEASURE)).getlength(text) / MEASURE


# ---------------------------------------------------------------------------------------- text layout

_BOLD = re.compile(r"\*\*(.+?)\*\*", re.S)
_URL = re.compile(r"^(https?://\S+|www\.\S+|[\w-]+(\.[\w-]+)+(/\S*)?)$", re.I)


def _tokens(text, prefix=None):
    """Paragraphs of units; a unit is the tokens (word, bold, underline) with no space between them, so punctuation
    typed right after a `**bold**` run stays attached to it."""
    out = []
    for i, para in enumerate((text or "").replace("\r", "").split("\n")):
        units = [list(u) for u in prefix] if (i == 0 and prefix) else []
        runs, pos = [], 0
        for m in _BOLD.finditer(para):
            runs += [(para[pos:m.start()], False), (m.group(1), True)]
            pos = m.end()
        runs.append((para[pos:], False))
        cur = []
        for chunk, bold in runs:
            for part in re.findall(r"\s+|\S+", chunk):
                if part.isspace():
                    if cur:
                        units.append(cur)
                        cur = []
                else:
                    cur.append((part, bold, False))
        if cur:
            units.append(cur)
        out.append(units)
    return out


def _uw(kind, size, unit):
    return sum(_width(kind, b, size, w) for w, b, _ in unit)


def _line_w(kind, size, units):
    return sum(_uw(kind, size, u) for u in units) + _width(kind, False, size, " ") * max(0, len(units) - 1)


def _wrap(paragraphs, kind, size, max_w):
    """Lines as (units, last-line-of-its-paragraph)."""
    lines = []
    space = _width(kind, False, size, " ")
    for units in paragraphs:
        cur, cur_w = [], 0.0
        for unit in units:
            while len(unit) == 1 and len(unit[0][0]) > 1 and _uw(kind, size, unit) > max_w:   # one unbroken word, too wide
                word, bold, under = unit[0]
                cut = len(word) - 1
                while cut > 1 and _width(kind, bold, size, word[:cut]) > max_w:
                    cut -= 1
                if cur:
                    lines.append((cur, False))
                    cur, cur_w = [], 0.0
                lines.append(([[(word[:cut], bold, under)]], False))
                unit = [(word[cut:], bold, under)]
            w = _uw(kind, size, unit)
            add = w + (space if cur else 0)
            if cur and cur_w + add > max_w:
                lines.append((cur, False))
                cur, cur_w = [unit], w
            else:
                cur.append(unit)
                cur_w += add
        lines.append((cur, True))
    return lines


class _Pen:
    """Draws in design units on an image rendered at `scale` pixels per unit (or measures when `draw` is None)."""

    def __init__(self, img, scale):
        self.img, self.s = img, scale
        self.d = ImageDraw.Draw(img) if img is not None else None

    def px(self, v):
        return round(v * self.s)

    def rect(self, x0, y0, x1, y1, fill):
        if self.d:
            self.d.rectangle([self.px(x0), self.px(y0), self.px(x1) - 1, self.px(y1) - 1], fill=fill)

    def line(self, x0, y0, x1, y1, fill, width=1.0):
        if self.d:
            self.d.line([self.px(x0), self.px(y0), self.px(x1), self.px(y1)], fill=fill, width=max(1, self.px(width)))

    def text(self, x, y, s, kind, bold, size, fill, anchor="ls"):
        if self.d:
            self.d.text((self.px(x), self.px(y)), s, font=_font(kind, bold, self.px(size)), fill=fill, anchor=anchor)

    def paste(self, path, x, y, w=None, h=None):
        if not self.d:
            return
        im = _asset(path)
        if w and not h:
            h = w * im.height / im.width
        if h and not w:
            w = h * im.width / im.height
        im = im.resize((self.px(w), self.px(h)), Image.LANCZOS)
        self.img.paste(im, (self.px(x), self.px(y)), im if im.mode == "RGBA" else None)


@lru_cache(maxsize=32)
def _asset(path):
    return Image.open(path).convert("RGBA")


def _draw_lines(pen, lines, x, y, width, kind, size, leading, fill, align="justify"):
    """Draw wrapped lines; `y` is the top of the first line. Returns the y after the last line."""
    space = _width(kind, False, size, " ")
    for units, last in lines:
        base = y + size * 0.82 + (leading - size) / 2
        total = sum(_uw(kind, size, u) for u in units)
        if align == "justify" and not last and len(units) > 1:
            gap, start = (width - total) / (len(units) - 1), x
        else:
            gap = space
            start = x + (width - (total + gap * (len(units) - 1))) / 2 if align == "center" else x
        cx = start
        for unit in units:
            for word, bold, under in unit:
                pen.text(cx, base, word, kind, bold, size, fill)
                w = _width(kind, bold, size, word)
                if under:
                    pen.line(cx, base + size * 0.12, cx + w, base + size * 0.12, fill, max(1.2, size / 24))
                cx += w
            cx += gap
        y += leading
    return y


def _fit_one_line(text, kind, bold, size, max_w, min_size):
    while size > min_size and _width(kind, bold, size, text) > max_w:
        size -= 0.5
    return size


# ------------------------------------------------------------------------------------- the poster

def icon_for(label: str, value: str = "") -> str:
    """Pick a table icon from the row wording: confirmation, chat group, materials, lodging, travel or a plain link."""
    text = f"{label} {value}".lower()
    for words, icon in ((("confirm", "register", "registration", "sign up", "rsvp"), "confirm"),
                        (("viber", "telegram", "messenger", "chat", "group"), "chat"),
                        (("material", "reference", "slides", "program", "recording", "resource", "folder"), "folder"),
                        (("accommodation", "venue", "hotel", "lodging"), "building"),
                        (("travel", "flight", "transport", "airfare"), "plane"),
                        (("deadline", "due", "schedule", "date"), "calendar")):
        if any(w in text for w in words):
            return icon
    return "link"


def _is_link(value: str) -> bool:
    return bool(_URL.match((value or "").strip()))


def _compose(pen, f, k):
    """Draw the whole poster at font scale `k`; returns the y where the table ends (for the fit test)."""
    # header (letterhead)
    pen.rect(0, 0, W, 224, WHITE)
    pen.paste(os.path.join(_ASSETS, "doh_seal.png"), 83, 54, 129, 129)
    pen.paste(os.path.join(_DIR, "bagong_pilipinas.png"), 222, 46, None, 150)
    pen.rect(375, 36, 383, 205, (0, 0, 0))
    pen.text(410, 122, "Department of Health", "sans", "semibold", 36.5, (0, 0, 0))
    pen.text(410, 160, "Bureau of Local Health Systems Development", "sans", "regular", 33, (0, 0, 0))
    # number band
    pen.rect(0, 224, 925, 397, GREEN)
    pen.rect(925, 224, W, 397, YELLOW)
    if pen.d:
        pen.paste(os.path.join(_DIR, "megaphone.png"), 45, 234, None, 152)
    size = _fit_one_line("ADVISORY", "sans", "bold", 100, 435, 10)
    f_ = _font("sans", "bold", round(size * MEASURE))
    top, bottom = f_.getbbox("ADVISORY", anchor="ls")[1:4:2]
    pen.text(255, 310.5 - (top + bottom) / MEASURE / 2, "ADVISORY", "sans", "bold", size, PAPER_TEXT)
    num = f"No. {f['number']}"
    nsize = _fit_one_line(num, "serif", False, 34, 300, 18)
    pen.text(1098 - _width("serif", False, nsize, num) / 2, 310.5 + nsize * 0.3, num, "serif", False, nsize, GREEN)
    # cream body
    pen.rect(0, BODY_TOP, W, BODY_BOTTOM, CREAM)
    width = CONTENT_R - CONTENT_L
    y = BODY_TOP + 38 * k
    tsize, tlead = 52 * k, 61 * k
    title = _wrap(_tokens(f["headline"]), "title", tsize, width - 20)
    y = _draw_lines(pen, title, CONTENT_L, y, width, "title", tsize, tlead, INK, "center") + 66 * k
    bsize, blead = 29 * k, 37 * k
    if f["attention"].strip():
        att = _wrap(_tokens(f["attention"], prefix=[[("ATTENTION:", False, True)]]), "serif", bsize, width)
        y = _draw_lines(pen, att, CONTENT_L, y, width, "serif", bsize, blead, INK) + 28 * k
    if f["body"].strip():
        body = _wrap(_tokens(f["body"]), "serif", bsize, width)
        y = _draw_lines(pen, body, CONTENT_L, y, width, "serif", bsize, blead, INK) + 37 * k
    rows = f["rows"]
    if rows:
        pen.text(CONTENT_L, y + bsize * 0.82 + (blead - bsize) / 2, "Important Deadlines & Links:",
                 "serif", False, bsize, INK)
        y += blead + 30 * k
        split = CONTENT_L + 650
        left_w, right_w = split - CONTENT_L - 28 - 46, CONTENT_R - split - 14
        top_y = y
        laid = []
        for label, value in rows:
            lab = _wrap(_tokens(label), "serif", bsize, left_w)
            link = _is_link(value)
            vsize = bsize
            if link and " " not in value.strip():
                vsize = _fit_one_line(value.strip(), "serif", False, bsize, right_w, bsize * 0.8)
            val = _wrap(_tokens(value), "serif", vsize, right_w)
            h = max(55 * k, max(len(lab), len(val)) * blead + 18 * k)
            laid.append((lab, val, vsize, link, h, label, value))
            y += h
        end_y = y
        if pen.d:
            ry = top_y
            for lab, val, vsize, link, h, label, value in laid:
                icon = os.path.join(_DIR, f"icon_{icon_for(label, value)}.png")
                text_w = max((_line_w("serif", bsize, ln) for ln, _ in lab), default=0)
                group_w = 36 + 10 + text_w
                gx = CONTENT_L + (650 - group_w) / 2
                pen.paste(icon, gx, ry + h / 2 - 18, 36, 36)
                ly = ry + (h - len(lab) * blead) / 2
                _draw_lines(pen, lab, gx + 46, ly, text_w, "serif", bsize, blead, INK, "center")
                vy = ry + (h - len(val) * blead) / 2
                _draw_lines(pen, [([[(w, b, link) for w, b, _ in u] for u in ln], last) for ln, last in val],
                            split + 7, vy, right_w, "serif", vsize, blead, INK, "center")
                ry += h
            pen.line(CONTENT_L, top_y, CONTENT_R, top_y, GRID, 1.3)
            pen.line(CONTENT_L, end_y, CONTENT_R, end_y, GRID, 1.3)
            ly_ = top_y
            for lab, val, vsize, link, h, *_ in laid:
                ly_ += h
                if ly_ < end_y - 1:
                    pen.line(CONTENT_L, ly_, CONTENT_R, ly_, GRID, 1.3)
            pen.line(CONTENT_L, top_y, CONTENT_L, end_y, GRID, 1.3)
            pen.line(split, top_y, split, end_y, GRID, 1.3)
            pen.line(CONTENT_R, top_y, CONTENT_R, end_y, GRID, 1.3)
        y = end_y
    # footer
    pen.rect(0, BODY_BOTTOM, 783, 1748, GREEN)
    pen.rect(783, BODY_BOTTOM, W, 1748, YELLOW)
    pen.rect(0, 1748, W, H, WHITE)
    if pen.d:
        pen.rect(25, 1530, 222, 1727, WHITE)
        qr = _qr_image(f["qr_url"])
        pen.img.paste(qr.resize((pen.px(177), pen.px(177)), Image.NEAREST), (pen.px(35), pen.px(1540)))
    pen.text(256, 1603 + 9, "Scan the QR code or access the link:", "sans", "regular", 25, PAPER_TEXT)
    link_text = f["link_text"] or f["qr_url"]
    ls = _fit_one_line(link_text, "sans", "semibold", 27, 505, 15)
    pen.text(256, 1636 + 9, link_text, "sans", "semibold", ls, PAPER_TEXT)
    pen.text(830, 1560 + 9, "For queries or concerns:", "sans", "regular", 29, (30, 30, 30))
    name_size = 31
    name = _wrap(_tokens(f["contact_name"]), "sans", name_size, 417)
    while len(name) > 3 and name_size > 22:
        name_size -= 1
        name = _wrap(_tokens(f["contact_name"]), "sans", name_size, 417)
    ny = 1587
    for units, _ in name[:3]:
        line = " ".join("".join(w for w, *_ in u) for u in units)
        pen.text(830, ny + name_size * 0.85, line, "sans", "semibold", name_size, (0, 0, 0))
        ny += name_size * 0.95
    py = max(1658, ny + 22)
    pen.text(830, py + 8, f["contact_phone"], "sans", "regular", 26, (0, 0, 0))
    pen.text(830, py + 40, f["contact_email"], "sans", "regular", 26, (0, 0, 0))
    return y


@lru_cache(maxsize=16)
def _qr_cached(url):
    import qrcode
    q = qrcode.QRCode(border=0, box_size=10, error_correction=qrcode.constants.ERROR_CORRECT_M)
    q.add_data(url)
    q.make(fit=True)
    return q.make_image(fill_color="black", back_color="white").convert("RGB")


def _qr_image(url):
    return _qr_cached(url or "https://example.invalid")


def normalise(fields: dict) -> dict:
    """The poster's fields as clean strings within their limits; blank rows are dropped, at most MAX_ROWS kept."""
    def s(key):
        return " ".join(str(fields.get(key) or "").split()) if key != "body" and key != "attention" else \
            "\n".join(" ".join(p.split()) for p in str(fields.get(key) or "").replace("\r", "").split("\n")).strip()
    out = {k: s(k)[:v] for k, v in LIMITS.items() if k not in ("label", "value")}
    out["number"] = s("number")[:30]
    out["qr_url"] = str(fields.get("qr_url") or "").strip()[:500]
    rows = []
    for row in fields.get("rows") or []:
        label, value = (" ".join(str(x or "").split()) for x in (list(row) + ["", ""])[:2])
        if label or value:
            rows.append((label[:LIMITS["label"]], value[:LIMITS["value"]]))
    out["rows"] = rows[:MAX_ROWS]
    return out


def render_png(fields: dict, scale: float = 2.0) -> bytes:
    """The advisory as a PNG (default 2544 x 3600). Raises AdvisoryTooLong when the text cannot fit."""
    f = normalise(fields)
    for k in FIT_STEPS:
        if _compose(_Pen(None, 1), f, k) <= BODY_BOTTOM - 28:
            break
    else:
        raise AdvisoryTooLong("The text is too long for one advisory. Shorten the headline, body or table rows.")
    img = Image.new("RGB", (round(W * scale), round(H * scale)), WHITE)
    _compose(_Pen(img, scale), f, k)
    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return buf.getvalue()


def render_pdf(fields: dict) -> bytes:
    """The same poster as a one-page A4 PDF (the image is within 0.1% of A4 proportions)."""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.utils import ImageReader
    from reportlab.pdfgen import canvas
    png = render_png(fields, 2.0)
    buf = io.BytesIO()
    c = canvas.Canvas(buf, pagesize=A4)
    c.setTitle(f"Advisory No. {normalise(fields)['number']}")
    c.drawImage(ImageReader(io.BytesIO(png)), 0, 0, A4[0], A4[1])
    c.showPage()
    c.save()
    return buf.getvalue()


def filename(number: str, ext: str) -> str:
    return f"BLHSD-Advisory-{re.sub(r'[^0-9A-Za-z-]+', '', number or 'draft') or 'draft'}.{ext}"
