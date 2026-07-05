#!/usr/bin/env python3
"""WCAG 2.2 AA contrast audit for the CSS-IS design tokens.

Phase 1 / 1C of the UI improvement plan. Parses the colour tokens out of
static/css/app.css, resolves every accent x theme combination the way the CSS
cascade would, and reports any text pair below the AA threshold (4.5:1 for
normal text, 3:1 for large/UI). Also checks the bespoke dark badge colour pairs
that have no token backing.

Run:  python tools/contrast_check.py
Exit code is non-zero if any hard-fail pair is found, so it can gate a deploy.
"""
from __future__ import annotations

import os
import re
import sys

CSS_PATH = os.path.join(os.path.dirname(__file__), "..", "static", "css", "app.css")

# Accents that ship as presets; "blue" is the default and lives in the base :root.
ACCENTS = ["blue", "teal", "violet", "emerald", "rose", "amber"]
THEMES = ["light", "dark", "contrast"]

# --- colour maths (WCAG 2.x) ---------------------------------------------------

def _hex(c: str):
    c = c.strip().lstrip("#")
    if len(c) == 3:
        c = "".join(ch * 2 for ch in c)
    return int(c[0:2], 16), int(c[2:4], 16), int(c[4:6], 16)


def _lin(v: float) -> float:
    v /= 255.0
    return v / 12.92 if v <= 0.03928 else ((v + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    r, g, b = _hex(hex_color)
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast(fg: str, bg: str) -> float:
    l1, l2 = luminance(fg), luminance(bg)
    hi, lo = max(l1, l2), min(l1, l2)
    return (hi + 0.05) / (lo + 0.05)


# --- token parsing -------------------------------------------------------------

HEX_TOKEN = re.compile(r"(--[\w-]+)\s*:\s*(#[0-9a-fA-F]{3,8})\b")


def parse_blocks(css: str) -> dict[str, dict[str, str]]:
    """Return {selector: {token: hex}} for every :root{...} rule (hex tokens only)."""
    blocks: dict[str, dict[str, str]] = {}
    # match  <selector> { <body> }  where selector starts with :root
    for m in re.finditer(r"(:root[^\{]*?)\{([^}]*)\}", css):
        sel = m.group(1).strip()
        toks = {t: v for t, v in HEX_TOKEN.findall(m.group(2))}
        if toks:
            blocks.setdefault(sel, {}).update(toks)
    return blocks


def selector_for(theme: str, accent: str) -> str:
    parts = ""
    if theme != "light":
        parts += f'[data-theme="{theme}"]'
    if accent != "blue":
        parts += f'[data-accent="{accent}"]'
    return ":root" + parts


def resolve(blocks: dict[str, dict[str, str]], theme: str, accent: str) -> dict[str, str]:
    """Apply the cascade in increasing specificity / source order:
    base :root  ->  theme  ->  accent  ->  theme+accent."""
    out: dict[str, str] = {}
    order = [
        ":root",
        f':root[data-theme="{theme}"]' if theme != "light" else None,
        f':root[data-accent="{accent}"]' if accent != "blue" else None,
        selector_for(theme, accent) if (theme != "light" and accent != "blue") else None,
    ]
    for sel in order:
        if sel and sel in blocks:
            out.update(blocks[sel])
    return out


# --- pairs that actually render as text ---------------------------------------
# (fg_token, bg_token, label, threshold). 4.5 = normal text; 3.0 = large/UI.
TEXT_PAIRS = [
    ("--on-accent", "--accent",    "button label on accent",        4.5),
    ("--accent",    "--surface",   "link/accent text on card",      4.5),
    ("--accent",    "--bg",        "link on page background",       4.5),
    ("--accent",    "--accent-bg", "accent text on its own tint",   4.5),
    ("--accent",    "--blue-bg",   "badge.blue text",               4.5),
    ("--accent-ink","--surface",   "strong/hover accent on card",   4.5),
    ("--ink",       "--surface",   "body text on card",             4.5),
    ("--ink",       "--bg",        "body text on page bg",          4.5),
    ("--ink-soft",  "--surface",   "secondary text on card",        4.5),
    ("--soft",      "--surface",   "muted/lede on card",            4.5),
    ("--soft",      "--bg",        "muted/lede on page bg",         4.5),
    ("--green",     "--green-bg",  "success text on tint",          4.5),
    ("--amber",     "--amber-bg",  "warning text on tint",          4.5),
    ("--red",       "--red-bg",    "error text on tint",            4.5),
    ("--green",     "--surface",   "success text on card",          4.5),
    ("--amber",     "--surface",   "warning text on card",          4.5),
    ("--red",       "--surface",   "error text on card",            4.5),
]
# --grey is placeholder/disabled text -> AA-exempt, reported as info only.
INFO_PAIRS = [
    ("--grey", "--surface", "placeholder/disabled on card", 3.0),
]

# Bespoke dark badge colours (app.css section "dark badge"): no token backing.
# Badge text is bold .72rem ~ small -> 4.5:1. (literal fg, bg)
DARK_BADGES = [
    ("gold",   "#fbbf24", "#2e2000"),
    ("rose",   "#fb7185", "#3a0a1c"),
    ("violet", "#a78bfa", "#231045"),
    ("teal",   "#2dd4bf", "#0a2424"),
    ("indigo", "#818cf8", "#151840"),
    ("stone",  "#c6c3c1", "#2a2826"),
]


def main() -> int:
    with open(CSS_PATH, encoding="utf-8") as fh:
        css = fh.read()
    blocks = parse_blocks(css)

    fails: list[str] = []
    infos: list[str] = []

    for theme in THEMES:
        for accent in ACCENTS:
            tok = resolve(blocks, theme, accent)
            for fg, bg, label, thr in TEXT_PAIRS:
                if fg not in tok or bg not in tok:
                    continue
                ratio = contrast(tok[fg], tok[bg])
                if ratio < thr:
                    fails.append(
                        f"  {theme:<8} {accent:<8} {ratio:4.2f}:1  (need {thr})  "
                        f"{label}  [{tok[fg]} on {tok[bg]}]"
                    )
            for fg, bg, label, thr in INFO_PAIRS:
                if fg in tok and bg in tok:
                    ratio = contrast(tok[fg], tok[bg])
                    if ratio < thr:
                        infos.append(
                            f"  {theme:<8} {accent:<8} {ratio:4.2f}:1  {label}  "
                            f"[{tok[fg]} on {tok[bg]}]"
                        )

    badge_fails: list[str] = []
    for name, fg, bg in DARK_BADGES:
        ratio = contrast(fg, bg)
        line = f"  dark badge.{name:<7} {ratio:4.2f}:1  [{fg} on {bg}]"
        (badge_fails if ratio < 4.5 else infos).append(line if ratio < 4.5 else line + "  (ok)")

    print("=== CSS-IS WCAG AA contrast audit ===")
    print(f"checked {len(THEMES)*len(ACCENTS)} accent x theme combos + {len(DARK_BADGES)} dark badges\n")

    if fails:
        print(f"FAIL — {len(fails)} text pair(s) below AA (4.5:1):")
        print("\n".join(fails))
    else:
        print("PASS — all token text pairs meet AA (4.5:1).")
    if badge_fails:
        print(f"\nFAIL — {len(badge_fails)} bespoke dark badge(s) below AA:")
        print("\n".join(badge_fails))
    if infos:
        print("\ninfo (AA-exempt / passing detail):")
        print("\n".join(infos))

    return 1 if (fails or badge_fails) else 0


if __name__ == "__main__":
    sys.exit(main())
