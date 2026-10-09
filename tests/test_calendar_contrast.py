"""Calendar colours stay readable (docs/CALENDAR_UX_PLAN.md Phase 3): every text/background pair the
calendar draws must reach WCAG AA (4.5:1) in the light, dark and high-contrast themes. Reads the
real stylesheets, so changing a token that breaks a pair fails here."""
from __future__ import annotations
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parent.parent / "static" / "css"
APP, CAL = (ROOT / "app.css").read_text(), (ROOT / "calendar.css").read_text()
TONES = ["green", "yellow", "magenta", "orange", "cyan", "blue", "grey"]


def block(src, selector):
    m = re.search(re.escape(selector) + r"\s*\{([^}]*)\}", src, re.S)
    return dict(re.findall(r"(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{3,6})", m.group(1))) if m else {}


def tokens(theme):
    sel = ":root" if theme == "light" else f':root[data-theme="{theme}"]'
    out = {**block(APP, ":root"), **block(CAL, ":root")}
    if theme != "light":
        out.update(block(APP, sel)); out.update(block(CAL, sel))
    return out


def lum(h):
    h = h.lstrip("#"); h = h * 2 if len(h) == 3 else h
    f = lambda v: v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4
    r, g, b = (f(int(h[i:i + 2], 16) / 255) for i in (0, 2, 4))
    return .2126 * r + .7152 * g + .0722 * b


def ratio(a, b):
    hi, lo = sorted((lum(a), lum(b)), reverse=True)
    return (hi + .05) / (lo + .05)


PAIRS = [("--soft", "--surface-3"), ("--ink", "--surface-3"), ("--ink-soft", "--surface"), ("--amber", "--amber-bg"),
         ("--red", "--red-bg"), ("--on-accent", "--accent"), ("--accent", "--accent-bg"), ("--soft", "--surface"),
         ("--soft", "--surface-2")]
for t in TONES:
    PAIRS += [("--soft", f"--cal-{t}-bg"), ("--ink", f"--cal-{t}-bg"), (f"--cal-{t}", f"--cal-{t}-bg")]


@pytest.mark.parametrize("theme", ["light", "dark", "contrast"])
def test_every_calendar_text_pair_reaches_aa(theme):
    t = tokens(theme)
    low = [(fg, bg, round(ratio(t[fg], t[bg]), 2)) for fg, bg in PAIRS if fg in t and bg in t and ratio(t[fg], t[bg]) < 4.5]
    assert not low, f"{theme}: below 4.5:1 -> {low}"
    assert sum(1 for fg, bg in PAIRS if fg in t and bg in t) >= len(PAIRS) - 3      # the check really found the tokens
