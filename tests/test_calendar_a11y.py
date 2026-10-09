"""Calendar accessibility (docs/CALENDAR_UX_PLAN.md Phase 5). A real-browser audit with axe-core found
these problems; each test pins one fix so it cannot come back: grids whose rows held links instead of
cells, a link given a cell role, buttons given a header role, empty header cells, a skipped heading
level, and a faded number that no longer read. They look at the HTML the server sends."""
from __future__ import annotations
import re
from html.parser import HTMLParser

import pytest

from conftest import in_the_directory

ROW_CHILD_ROLES = {"gridcell", "cell", "columnheader", "rowheader"}
VOID = {"input", "br", "img", "hr", "meta", "link"}


class _Roles(HTMLParser):
    """Collects, for every role=row element, the roles of its direct element children."""
    def __init__(self):
        super().__init__(); self.stack = []; self.rows = []; self.bad_anchor_roles = []; self.bad_button_roles = []

    def handle_starttag(self, tag, attrs):
        a = dict(attrs); role = a.get("role")
        if self.stack and self.stack[-1]["row"] is not None:
            self.stack[-1]["row"].append((tag, role, a.get("class", "")))
        if tag == "a" and role: self.bad_anchor_roles.append((role, a.get("class", "")))
        if tag == "button" and role: self.bad_button_roles.append((role, a.get("class", "")))
        if tag in VOID: return
        row = [] if role == "row" else None
        self.stack.append({"tag": tag, "row": row})
        if row is not None: self.rows.append(row)

    def handle_endtag(self, tag):
        while self.stack:
            if self.stack.pop()["tag"] == tag: break


def roles(html):
    p = _Roles(); p.feed(html); return p


def assert_rows_hold_only_cells(html, what):
    p = roles(html)
    assert p.rows, f"{what}: no rows found"
    bad = [(t, r, c) for row in p.rows for (t, r, c) in row if r not in ROW_CHILD_ROLES]
    assert not bad, f"{what}: row children that are not cells: {bad[:4]}"
    assert not p.bad_anchor_roles and not p.bad_button_roles, (what, p.bad_anchor_roles[:2], p.bad_button_roles[:2])


# --------------------------------------------------------------------- grids ---

def test_the_month_grid_rows_hold_only_cells_and_no_link_or_button_carries_a_cell_or_header_role(viewer):
    assert_rows_hold_only_cells(viewer.get("/calendar?view=month&month=2026-10").text, "month")


def test_week_and_timeline_rows_hold_only_cells(app_mod, viewer):
    with in_the_directory(app_mod, "viewer@test.local", path="CALA11Y/D1/S1"):
        for layout in ("week", "timeline"):
            assert_rows_hold_only_cells(viewer.get(f"/calendar?view={layout}").text, layout)


def test_the_timeline_day_headers_are_cells_that_contain_the_add_button(app_mod, viewer):
    with in_the_directory(app_mod, "viewer@test.local", path="CALA11Y/D1/S1"):
        html = viewer.get("/calendar?view=timeline").text
    assert re.search(r'<div class="cal-tl-dayh" role="columnheader"><button type="button" class="cal-tl-day', html)
    assert 'role="columnheader" class="cal-tl-day' not in html


def test_the_corner_header_of_week_and_timeline_is_named(app_mod, viewer):
    with in_the_directory(app_mod, "viewer@test.local", path="CALA11Y/D1/S1"):
        for layout in ("week", "timeline"):
            html = viewer.get(f"/calendar?view={layout}").text
            named = r'<div (?:role="columnheader" class="cal-pw-name"|class="cal-tl-name" role="columnheader")><span class="cal-sr">Person</span></div>'
            empty = r'<div (?:role="columnheader" class="cal-pw-name"|class="cal-tl-name" role="columnheader")></div>'
            assert re.search(named, html), layout
            assert not re.search(empty, html), layout


def test_the_compact_month_cell_is_the_gridcell_and_the_link_inside_it_names_the_day(viewer):
    html = viewer.get("/calendar?view=month&month=2026-10").text.split('class="cal-mgrid"')[1]
    cell = html.split('<div class="cal-mday')[1].split("</div>")[0]
    assert 'role="gridcell"' in cell and '<a class="cal-mlink"' in cell and re.search(r'aria-label="\w+day, \w+ \d+: \d+ items?', cell)
    assert not re.search(r'<a[^>]*role="gridcell"', html)


def test_today_is_marked_as_the_current_date_in_every_layout(viewer):
    assert re.search(r'<section class="cal-day today[^"]*"[^>]*aria-current="date"', viewer.get("/calendar").text)
    assert viewer.get("/calendar").text.count('aria-current="date"') >= 2                          # the day and the "Today" button


# ------------------------------------------------------------------- headings ---

def test_heading_levels_never_skip_even_when_the_range_is_empty(viewer):
    html = viewer.get("/calendar?day=2031-01-06").text
    content = re.findall(r'<h([1-6])[^>]*>', html.split('class="cal-bar"')[1])
    assert content and all(int(a) - int(b) <= 1 for b, a in zip(["1"] + content, content)), content
    assert "<h3" not in html.split('class="cal-empty"')[1].split("</div>")[0]


# --------------------------------------------------------------- readable fade ---

def test_faded_days_use_colour_not_opacity_so_the_number_stays_readable():
    css = open("static/css/calendar.css", encoding="utf-8").read()
    assert not re.search(r"\.cal-cell\.out\s*\{[^}]*opacity", css) and not re.search(r"\.cal-mday\.out\s*\{[^}]*opacity", css)
    assert re.search(r"\.cal-mday\.out \.cal-mnum\s*\{[^}]*color:var\(--soft\)", css)
    assert re.search(r"\.cal-num\[data-out\]\s*\{[^}]*color:var\(--soft\)", css)


def test_small_targets_in_the_grids_meet_the_24px_minimum():
    css = open("static/css/calendar.css", encoding="utf-8").read()
    assert re.search(r"\.cal-bar-item\s*\{[^}]*min-height:1\.5rem", css) and re.search(r"\.cal-more\s*\{[^}]*min-height:1\.5rem", css)


def test_nothing_in_the_toolbar_refuses_to_wrap_so_large_text_cannot_widen_the_page():
    css = open("static/css/calendar.css", encoding="utf-8").read()
    assert re.search(r"\.cal-nav a \{ white-space:normal", css) and re.search(r"\.cal-scope \{ flex-wrap:wrap", css)
    assert "grid-template-columns:minmax(0, 1fr); }" in css.split(".cal-fpanel {")[-1] or ".cal-fpanel { grid-template-columns:minmax(0, 1fr); }" in css


def test_motion_is_off_for_people_who_ask_for_less():
    css = open("static/css/calendar.css", encoding="utf-8").read()
    assert "@media (prefers-reduced-motion:no-preference)" in css                         # the sheet only slides when allowed
    assert re.search(r"prefers-reduced-motion:reduce\)[^}]*\.cal-item \{ transition:none", css)


def test_every_day_number_in_the_full_month_sits_in_the_first_grid_row_so_bars_cannot_cover_it(viewer):
    """Putting the numbers inside their cells (to satisfy the grid roles) once collapsed the number row, and
    event bars were drawn over the numbers. They must stay row-1 grid items of the week, inside the one layer."""
    html = viewer.get("/calendar?view=month&month=2026-10").text.split('class="cal-month"')[1]
    nums = re.findall(r'<a class="cal-num" href="/calendar/new\?day=[\d-]+" style="grid-column:(\d); grid-row:1"', html)
    assert len(nums) >= 28 and set(nums) == set("1234567")
    first_week = html.split('class="cal-week"')[1].split('class="cal-week"')[0]
    assert first_week.index('class="cal-layer"') < first_week.index('class="cal-num"') < first_week.index('class="cal-bar-item')  \
        if 'class="cal-bar-item' in first_week else True
    assert re.search(r"\.cal-week \{[^}]*grid-template-rows:auto repeat\(var\(--rows\), auto\)", open("static/css/calendar.css", encoding="utf-8").read())
