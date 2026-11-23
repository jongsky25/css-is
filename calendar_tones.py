"""Unit colours for the office calendar: chosen by each section, first come, first served.

Owner decision (docs/ORG_RESTRUCTURE_ASSESSMENT.md, Phase 3): every section head picks
their section's calendar colour, as long as it looks clearly different from the others.
The palette is fixed so that is guaranteed: every pair of tones is at least
MIN_DISTANCE apart (CIE76 colour difference) in both the light and the dark theme,
which tests/test_calendar_tones.py checks. A colour belongs to one unit at a time; a
taken colour stays with whoever chose it first until they change or release it.

The same colour is how a unit is marked in the Word "Calendar of Activities": each
tone names the Word highlight (or a shading close to `ref`) that the importer reads
as that unit's (calendar_import). The registry is the `calendar_unit_tones` setting
({org_unit_id: tone}), which office_calendar already draws from.
"""
from __future__ import annotations

import json
import math

import storage as st

SETTING = "calendar_unit_tones"
MIN_DISTANCE = 20

# key -> label, Word highlight name (or None: shading only), reference fill, and the
# light/dark theme colours mirrored in static/css/calendar.css.
PALETTE = {
    "green":   {"label": "Green",   "highlight": "green",       "ref": "00ff00", "light": "#2d7b57", "dark": "#5fcf93"},
    "yellow":  {"label": "Yellow",  "highlight": "yellow",      "ref": "ffff00", "light": "#8a6d00", "dark": "#e6c84a"},
    "magenta": {"label": "Magenta", "highlight": "magenta",     "ref": "ff00ff", "light": "#a21caf", "dark": "#e58df0"},
    "orange":  {"label": "Orange",  "highlight": None,          "ref": "ff9900", "light": "#ae5008", "dark": "#f0a35e"},
    "cyan":    {"label": "Cyan",    "highlight": "cyan",        "ref": "00ffff", "light": "#0e7490", "dark": "#5fd0e6"},
    "blue":    {"label": "Blue",    "highlight": "blue",        "ref": "0000ff", "light": "#2b6cb0", "dark": "#8fbbea"},
    "red":     {"label": "Red",     "highlight": "red",         "ref": "ff0000", "light": "#c81e1e", "dark": "#ff6b6b"},
    "purple":  {"label": "Purple",  "highlight": "darkMagenta", "ref": "800080", "light": "#5b21b6", "dark": "#a78bfa"},
    "maroon":  {"label": "Maroon",  "highlight": "darkRed",     "ref": "800000", "light": "#6b2a1a", "dark": "#c08a6a"},
    "lime":    {"label": "Lime",    "highlight": None,          "ref": "99cc00", "light": "#4d7c0f", "dark": "#a3e635"},
    "pink":    {"label": "Pink",    "highlight": None,          "ref": "ff66aa", "light": "#b8336a", "dark": "#ff9ec7"},
}
TONES = tuple(PALETTE)
NO_TONE = "grey"


def lab(hex_color):
    """CIE L*a*b* (D65) of '#rrggbb' / 'rrggbb'."""
    h = hex_color.lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    lin = lambda c: ((c + 0.055) / 1.055) ** 2.4 if c > 0.04045 else c / 12.92   # noqa: E731
    r, g, b = lin(r), lin(g), lin(b)
    x = (r * 0.4124 + g * 0.3576 + b * 0.1805) / 0.95047
    y = r * 0.2126 + g * 0.7152 + b * 0.0722
    z = (r * 0.0193 + g * 0.1192 + b * 0.9505) / 1.08883
    f = lambda v: v ** (1 / 3) if v > 0.008856 else 7.787 * v + 16 / 116          # noqa: E731
    return 116 * f(y) - 16, 500 * (f(x) - f(y)), 200 * (f(y) - f(z))


def distance(a, b):
    return math.dist(lab(a), lab(b))


def nearest_tone(hex_fill, limit=60):
    """Palette tone whose reference fill is closest to a Word shading, or None when
    nothing is within `limit` (decoration, not an owner)."""
    best = min(TONES, key=lambda t: distance(hex_fill, PALETTE[t]["ref"]))
    return best if distance(hex_fill, PALETTE[best]["ref"]) <= limit else None


# ── the registry ────────────────────────────────────────────────────────────

def registry(conn):
    """{org_unit_id: tone} for every unit holding a palette colour."""
    try:
        raw = json.loads(st.get_setting(conn, SETTING) or "{}")
    except ValueError:
        raw = {}
    return {int(k): v for k, v in raw.items() if v in PALETTE and str(k).isdigit()}


def holders(conn):
    """{tone: org_unit_id} -- the inverse of registry (first holder wins on a legacy clash)."""
    out = {}
    for uid, tone in sorted(registry(conn).items()):
        out.setdefault(tone, uid)
    return out


def _save(conn, reg):
    st.set_setting(conn, SETTING, json.dumps({str(k): v for k, v in sorted(reg.items())}))


def may_choose(conn, user, unit_id):
    """Section heads (and the acting OIC) choose for their own section or unit; an
    administrator may set any unit's colour, the bureau's included."""
    if not user:
        return False
    if user.get("role") == "admin":
        return True
    row = conn.execute("SELECT level, path FROM org_unit WHERE id=? AND retired_at IS NULL",
                       (unit_id,)).fetchone()
    if not row or row[0] != "section":
        return False
    return user["id"] in st.org_unit_chiefs(conn, unit_id) or st._section_oic_account_id(conn, row[1]) == user["id"]


def choose(conn, user, unit_id, tone):
    """Give `unit_id` the colour `tone`, releasing the colour it had. Refused while
    another unit holds that colour -- first come, first served."""
    if tone not in PALETTE:
        raise ValueError("Choose one of the listed colours.")
    if not may_choose(conn, user, unit_id):
        raise PermissionError("Only the section head (or its acting OIC) can choose this colour.")
    reg = registry(conn)
    holder = next((uid for uid, t in reg.items() if t == tone and uid != unit_id), None)
    if holder is not None:
        name = conn.execute("SELECT name FROM org_unit WHERE id=?", (holder,)).fetchone()
        raise ValueError(f"{PALETTE[tone]['label']} is already {(name[0] if name else 'another unit')}'s colour. "
                         "Pick a free one.")
    reg[int(unit_id)] = tone
    _save(conn, reg)
    st.audit(conn, user.get("username"), "calendar_colour", target_type="org_unit", target_id=unit_id,
             summary=f"chose {PALETTE[tone]['label']} as the calendar colour")
    return tone


def release(conn, user, unit_id):
    if not may_choose(conn, user, unit_id):
        raise PermissionError("Only the section head (or its acting OIC) can change this colour.")
    reg = registry(conn)
    if reg.pop(int(unit_id), None) is not None:
        _save(conn, reg)
        st.audit(conn, user.get("username"), "calendar_colour", target_type="org_unit", target_id=unit_id,
                 summary="released its calendar colour")


def assign_batch(conn, mapping):
    """The importer's tone -> unit choice: each listed unit takes that tone, which is
    taken off any other unit and off the unit's previous tone."""
    reg = registry(conn)
    for tone, uid in mapping.items():
        if tone not in PALETTE:
            continue
        reg = {u: t for u, t in reg.items() if t != tone and u != uid}
        reg[int(uid)] = tone
    _save(conn, reg)


def board(conn):
    """Rows for the colours page: every current section/unit (and the bureau) with
    its colour, plus the palette with who holds each tone."""
    reg = registry(conn)
    units = [dict(zip(("id", "name", "short_name", "level", "path"), r)) for r in conn.execute(
        "SELECT id, name, short_name, level, path FROM org_unit "
        "WHERE retired_at IS NULL AND level IN ('bureau','section') ORDER BY path")]
    names = {u["id"]: u["name"] for u in units}
    palette = [{"key": t, **PALETTE[t], "holder": next((names.get(u) or "a retired unit"
                                                       for u, x in reg.items() if x == t), None)}
               for t in TONES]
    return [dict(u, tone=reg.get(u["id"])) for u in units], palette


def section_number_tones(conn):
    """{section number: tone} for current sections holding a colour, read from
    short names like 'S7' or names like 'Section 7 ...' (used to turn a 'Section 7'
    mention in a calendar line into that section's colour)."""
    import re
    reg = registry(conn)
    out = {}
    for uid, name, short in conn.execute(
            "SELECT id, name, COALESCE(short_name,'') FROM org_unit WHERE level='section' AND retired_at IS NULL"):
        m = re.fullmatch(r"S(\d{1,2})", short.strip(), re.I) or re.match(r"section\s*(\d{1,2})\b", name.strip(), re.I)
        if m and uid in reg:
            out.setdefault(int(m.group(1)), reg[uid])
    return out
