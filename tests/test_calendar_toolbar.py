"""The calendar toolbar (docs/CALENDAR_UX_PLAN.md Phase 1): two rows, one GET form, filters behind
one button. Behaviour that matters is the markup the no-JS fallback and the script both rely on."""
from __future__ import annotations
import re
from datetime import timedelta

import pytest

import storage as st
import tzutil as tz
from conftest import in_the_directory


@pytest.fixture()
def conn(app_mod):
    c = st.connect(app_mod.DB); st.init_db(c)
    yield c
    for (i,) in c.execute("SELECT id FROM calendar_entry WHERE title LIKE 'CALTO %'").fetchall():
        st.cal_delete(c, i)
    c.commit(); c.close()


def mk(conn, title, offset=0, **kw):
    kw.setdefault("audience", "bureau")
    return st.cal_create(conn, f"CALTO {title}", (tz.today_local() + timedelta(days=offset)).isoformat(), **kw)


def form_of(html):
    return html.split('<form id="cal-f"')[1].split("</form>")[0]


@pytest.mark.parametrize("url", ["/calendar", "/?view=calendar"])
def test_two_rows_and_scope_is_one_select_not_five_pills(viewer, url):
    html = viewer.get(url).text
    assert html.count('class="cal-bar"') == 1 and html.count('<form id="cal-f"') == 1
    assert html.count('class="cal-pills cal-views"') == 1 and 'aria-label="Whose calendar"' in html
    scope = html.split('name="scope" class="cal-auto"')[1].split("</select>")[0]
    assert scope.count("<option") >= 2
    # the scope is posted by the select alone, never twice
    assert len(re.findall(r'name="scope"', form_of(html))) == 1


def test_team_layouts_have_no_scope_select_and_post_the_fixed_scope(app_mod, viewer):
    with in_the_directory(app_mod, "viewer@test.local", path="CALTO/D1/S1"):         # Week and Timeline need a team
        for layout in ("week", "timeline"):
            html = viewer.get(f"/calendar?view={layout}").text
            assert f'aria-current="true">{layout.capitalize()}' in html, layout
            f = form_of(html)
            assert 'aria-label="Whose calendar"' not in f and f.count('type="hidden" name="scope"') == 1, layout


def test_the_form_posts_back_to_the_page_it_is_on(viewer):
    assert 'action="/calendar"' in form_of(viewer.get("/calendar").text)
    home = form_of(viewer.get("/?view=calendar").text)
    assert 'action="/"' in home and 'name="view" value="calendar"' in home


def test_the_move_links_say_where_they_go_and_today_is_marked(viewer):
    html = viewer.get("/calendar").text
    nav = html.split('<nav class="cal-nav"')[1].split("</nav>")[0]
    assert "← Earlier" in nav and "Later →" in nav and 'aria-current="date"' in nav
    nav2 = viewer.get("/calendar?day=2026-03-02").text.split('<nav class="cal-nav"')[1].split("</nav>")[0]
    assert 'aria-current="date"' not in nav2                              # not on today's window


def test_filters_sit_behind_one_button_with_a_count_and_removable_chips(viewer, conn):
    mk(conn, "Standup", 1)
    plain = viewer.get("/calendar").text
    assert "<summary class=\"cal-btn\">Filters</summary>" in plain and "cal-chips-x" not in plain
    assert "Clear filters" not in plain
    html = viewer.get("/calendar?kind=meeting&status=confirmed").text
    assert "Filters (2)" in html and "Clear filters" in html and "· filtered" in html
    chips = html.split('class="cal-chips-x"')[1].split("</span>\n")[0]
    assert "Type: " in chips and "Status: " in chips
    for href in re.findall(r'href="([^"]+)"', chips):                     # each chip removes just its own filter
        assert ("kind=meeting" in href) != ("status=confirmed" in href), href


def test_the_filter_panel_has_a_plain_apply_button_for_browsers_without_script(viewer):
    html = viewer.get("/calendar").text
    assert 'class="cal-btn cal-apply" type="submit"' in html and "<noscript>" in form_of(html)
    assert html.count('class="cal-auto"') >= 4                            # scope, type, status, tag apply on change


def test_the_rare_actions_are_in_the_more_menu_and_import_is_admin_only(viewer, admin):
    v = viewer.get("/calendar").text.split('class="cal-more"')[1].split("</details>")[0]
    assert "Birthdays" in v and "data-quick" in v and "Import from Word" not in v
    a = admin.get("/calendar").text.split('class="cal-more"')[1].split("</details>")[0]
    assert "Import from Word" in a and 'href="/calendar/import"' in a


def test_a_saved_message_shows_as_text_and_never_as_a_macro(viewer):
    for url in ("/calendar?ok=Added+to+the+calendar.", "/?view=calendar&ok=Added+to+the+calendar."):
        html = viewer.get(url).text
        assert "✓ Added to the calendar." in html and "&lt;Macro" not in html and "<Macro" not in html, url


def test_an_empty_calendar_says_so_once_with_clear_next_steps(viewer, conn):
    html = viewer.get("/calendar?day=2031-01-06").text
    assert 'class="empty-state"' not in html and html.count('class="cal-empty"') == 1
    assert html.count("Nothing else planned") == 1
    assert "+ Add something</a>" in html and "Look further ahead</a>" in html and "Clear filters" not in html
    assert "Clear filters</a>" in viewer.get("/calendar?day=2031-01-06&kind=meeting").text       # a filter may be the reason
