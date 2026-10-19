"""Calendar Phase 4 (docs/CALENDAR_UX_PLAN.md): search, a remembered view, quick add from a day and the
item sheet. The scripted parts (sheet, keys, swipe) are checked in a real browser; this file covers what
the server decides: the search, the cookie, and the markup those scripts rely on."""
from __future__ import annotations
import re
from datetime import date, timedelta

import pytest

import office_calendar as oc
import storage as st
import tzutil as tz
from conftest import in_the_directory


@pytest.fixture()
def conn(app_mod):
    c = st.connect(app_mod.DB); st.init_db(c)
    yield c
    for (i,) in c.execute("SELECT id FROM calendar_entry WHERE title LIKE 'CALP4 %'").fetchall():
        st.cal_delete(c, i)
    c.execute("DELETE FROM holiday WHERE name LIKE 'CALP4 %'")
    c.commit(); c.close()


def mk(conn, title, day=None, **kw):
    kw.setdefault("audience", "bureau")
    return st.cal_create(conn, f"CALP4 {title}", day or tz.today_local().isoformat(), **kw)


def pref_cookie(client):
    return client.cookies.get("cal_pref")


def save_pref(client, layout="month", scope="mine", next_url="/calendar"):
    return client.post("/calendar/preference", data={"layout": layout, "scope": scope, "next": next_url},
                       follow_redirects=False)


# ------------------------------------------------------------------- search ---

def item(title, **kw):
    return {"title": title, "layer": kw.pop("layer", "entries"), "kind": "meeting", "status": "confirmed",
            "tags": kw.pop("tags", []), "owner_org_id": None, "venue": kw.pop("venue", None),
            "owner_label": kw.pop("owner_label", None), "people": kw.pop("people", []), **kw}


def test_text_search_matches_title_place_unit_tags_and_people_case_insensitively():
    items = [item("Strategic Planning"), item("Other", venue="Room Palawan"), item("Third", owner_label="Section 4"),
             item("Fourth", tags=["BHW"]), item("Fifth", people=[{"name": "Riza Santos"}]), item("Nope")]
    f = lambda t: [i["title"] for i in oc.apply_filters(items, {"text": t})]
    assert f("strat") == ["Strategic Planning"] and f("PALAWAN") == ["Other"] and f("section 4") == ["Third"]
    assert f("bhw") == ["Fourth"] and f("riza") == ["Fifth"] and f("zzz") == []


def test_a_text_search_drops_holidays_that_do_not_match_but_the_menus_never_do():
    hol = item("New Year", layer="holidays")
    assert oc.apply_filters([hol], {"kinds": {"travel"}}) == [hol]                      # backdrop stays for the menus
    assert oc.apply_filters([hol], {"text": "planning"}) == []
    assert oc.apply_filters([hol], {"text": "new year"}) == [hol]


def test_the_agenda_search_reads_through_the_whole_year_and_lists_only_matching_days(viewer, conn):
    y = tz.today_local().year
    mk(conn, "Zebra review", f"{y}-02-03"); mk(conn, "Zebra follow-up", f"{y}-11-20"); mk(conn, "Elephant", f"{y}-05-05")
    html = viewer.get("/calendar?q=zebra").text
    assert "CALP4 Zebra review" in html and "CALP4 Zebra follow-up" in html and "CALP4 Elephant" not in html
    assert f"Search in {y} · 2 matches" in html
    assert "Nothing scheduled today" not in html                                         # no pinned empty "today" in a search
    nav = html.split('<nav class="cal-nav"')[1].split("</nav>")[0]
    assert f"← {y - 1}" in nav and f"{y + 1} →" in nav and f"day={y - 1}-01-01" in nav


def test_search_has_a_box_a_removable_chip_and_clears_with_the_filters(viewer, conn):
    mk(conn, "Zebra", (tz.today_local() + timedelta(days=1)).isoformat())
    plain = viewer.get("/calendar").text
    assert 'type="search" name="q"' in plain and 'maxlength="80"' in plain and "Search: " not in plain
    html = viewer.get("/calendar?q=zebra&kind=meeting").text
    assert 'value="zebra"' in html and "Search: zebra" in html and "Filters (1)" in html       # the box is not a menu filter
    chip = html.split("Search: zebra")[0].rsplit("<a", 1)[-1]
    assert "q=zebra" not in chip and "kind=meeting" in chip                              # removing it keeps the others
    clear = re.search(r'<a href="([^"]+)">Clear filters</a>', html).group(1)
    assert "q=" not in clear and "kind=" not in clear


def test_search_text_is_escaped_trimmed_and_capped(viewer):
    html = viewer.get("/calendar", params={"q": '<script>alert(1)</script>' + "x" * 200}).text
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html
    value = re.search(r'name="q" value="([^"]*)"', html).group(1)
    assert len(value) <= 80 + len("&lt;script&gt;alert(1)&lt;/script&gt;")             # entity-escaped, but capped at 80 characters


def test_a_search_in_the_month_layout_filters_the_grid_instead_of_changing_the_window(viewer, conn):
    mk(conn, "Zebra", "2026-10-06"); mk(conn, "Elephant", "2026-10-07")
    html = viewer.get("/calendar?view=month&month=2026-10&q=zebra").text
    assert "CALP4 Zebra" in html and "CALP4 Elephant" not in html and "October 2026" in html


# --------------------------------------------------------- the remembered view ---

def test_a_chosen_layout_and_scope_are_remembered_for_a_plain_visit(viewer, conn):
    mk(conn, "Thing", (tz.today_local() + timedelta(days=1)).isoformat())
    chosen = viewer.get("/calendar?view=month&scope=mine").text
    assert "Save as preferred view" in chosen
    assert save_pref(viewer).status_code == 303
    assert pref_cookie(viewer) == "month:mine"
    html = viewer.get("/calendar").text                                                   # a bare visit
    assert 'aria-current="true">Month' in html and '<option value="mine" selected>' in html
    again = viewer.get("/?view=calendar").text                                            # ...and the home tab shares it
    assert 'aria-current="true">Month' in again and '<option value="mine" selected>' in again
    assert "Preferred view saved" in again


def test_a_link_that_names_something_always_wins_and_a_bare_visit_saves_nothing(viewer):
    save_pref(viewer)
    html = viewer.get("/calendar?day=2026-10-12").text                                    # explicit date: agenda, not the remembered month
    assert 'aria-current="true">Agenda' in html and 'aria-current="true">Month' not in html
    assert pref_cookie(viewer) == "month:mine"                                           # browsing does not replace it
    viewer.cookies.delete("cal_pref")
    viewer.get("/calendar")                                                               # nothing chosen, nothing saved
    assert pref_cookie(viewer) is None


def test_everything_i_can_see_is_the_default_without_a_saved_preference(viewer):
    for url in ("/calendar", "/?view=calendar"):
        html = viewer.get(url).text
        assert '<option value="bureau" selected>Everything I can see</option>' in html
    assert pref_cookie(viewer) is None


@pytest.mark.parametrize("bad", ["month", "week:bogus value", "x:mine", "<b>:mine", "agenda:" + "a" * 40])
def test_a_forged_cookie_is_ignored(viewer, bad):
    viewer.cookies.set("cal_pref", bad)
    r = viewer.get("/calendar")
    assert r.status_code == 200 and 'aria-current="true">Agenda' in r.text


def test_a_remembered_scope_the_person_is_not_offered_falls_back_quietly(viewer):
    viewer.cookies.set("cal_pref", "agenda:section")                                      # an unlinked account has no "section"
    assert '<option value="bureau" selected>' in viewer.get("/calendar").text


def test_a_remembered_team_layout_still_works_for_someone_with_a_team(app_mod, viewer):
    with in_the_directory(app_mod, "viewer@test.local", path="CALP4/D1/S1"):
        save_pref(viewer, "week", "blend")
        assert pref_cookie(viewer) == "week:blend"
        assert 'aria-current="true">Week' in viewer.get("/?view=calendar").text


def test_the_cookie_is_httponly_lax_and_a_year_long(viewer):
    sc = save_pref(viewer, scope="blend").headers["set-cookie"]
    assert "cal_pref=month:blend" in sc and "HttpOnly" in sc and "SameSite=lax" in sc and "Max-Age=31536000" in sc


def test_preference_can_be_saved_from_home_and_survives_refresh(viewer):
    url = "/?view=calendar&layout=timeline"
    assert "Save as preferred view" in viewer.get(url).text
    r = save_pref(viewer, "timeline", "bureau", url)
    assert r.headers["location"] == url
    assert "Preferred view saved" in viewer.get(url).text
    assert 'aria-current="true">Timeline' in viewer.get("/calendar").text


def test_invalid_preferences_are_rejected_and_redirect_stays_local(viewer):
    assert save_pref(viewer, "bogus", "mine").status_code == 400
    assert pref_cookie(viewer) is None
    r = save_pref(viewer, next_url="//outside.example")
    assert r.headers["location"] == "/calendar"


# ------------------------------------------- markup the scripts rely on ---

def test_the_item_sheet_and_its_controls_are_on_every_calendar_view(viewer, conn):
    for url in ("/calendar", "/calendar?view=month", "/?view=calendar"):
        html = viewer.get(url).text
        assert html.count('<dialog id="cal-sheet"') == 1, url
        sheet = html.split('<dialog id="cal-sheet"')[1].split("</dialog>")[0]
        assert "data-sheet-body" in sheet and "data-sheet-close" in sheet and "data-sheet-open" in sheet and "Open full page" in sheet


def test_items_stay_ordinary_links_so_the_sheet_is_only_an_enhancement(viewer, conn):
    mk(conn, "Linked thing", (tz.today_local() + timedelta(days=1)).isoformat())
    html = viewer.get("/calendar").text
    assert re.search(r'<a class="cal-tt" href="/calendar/entries/\d+">CALP4 Linked thing</a>', html)


def test_each_agenda_day_has_a_hidden_until_script_add_button_for_that_date(viewer, conn):
    mk(conn, "Dated", (tz.today_local() + timedelta(days=1)).isoformat())
    html = viewer.get("/calendar").text
    btns = re.findall(r'<button type="button" class="cal-dayadd" data-quick data-date="(\d{4}-\d\d-\d\d)" hidden aria-label="Add something on ([^"]+)"', html)
    assert btns and all(d in html for d, _ in btns)
    assert tz.today_local().isoformat() in [d for d, _ in btns]                          # today is always there


def test_a_month_number_opens_quick_add_with_a_real_link_behind_it(viewer):
    html = viewer.get("/calendar?view=month&month=2026-10").text
    nums = re.findall(r'<a class="cal-num" href="(/calendar/new\?day=[\d-]+)"[^>]*data-quick data-date="([\d-]+)"', html)
    assert len(nums) >= 28 and all(h.endswith(d) for h, d in nums)


def test_the_keyboard_shortcuts_are_listed_on_the_page(viewer):
    html = viewer.get("/calendar").text
    assert 'class="cal-keys"' in html and "<kbd>T</kbd> today" in html and "<kbd>S</kbd> search" in html


def test_the_calendar_script_never_builds_html_from_a_string():
    js = (pathlib_root() / "static" / "js" / "calendar.js").read_text()
    for banned in ("innerHTML", "outerHTML", "insertAdjacentHTML", "document.write", "eval(", "new Function"):
        assert banned not in js, banned
    assert "DOMParser" in js and "importNode" in js                                      # the sheet moves parsed nodes in
    assert 'querySelectorAll("script, iframe, object, embed, link, style")' in js        # ...after removing anything executable


def pathlib_root():
    import pathlib
    return pathlib.Path(__file__).resolve().parent.parent


def test_more_options_keeps_what_was_typed_in_quick_add(viewer):
    html = viewer.get("/calendar/new?day=2026-10-14&title=Budget+talk&end_date=2026-10-15"
                      "&start_time=09:30&kind=training").text
    assert 'value="Budget talk"' in html and 'value="2026-10-15"' in html and 'value="09:30"' in html
    assert re.search(r'<option value="training"\s+selected', html)
