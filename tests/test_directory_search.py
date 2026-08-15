"""
The directory's staff search box.

Two independent things had it reading as broken, and they need separate guards
because they fail in different places:

  1. It matched nothing when you typed the section you were looking for. The
     "Assigned to" cell rendered only the SHORT path ("HSMED/S4"), and nobody
     searches for a colleague by typing "S4" — they type "Section 4" or "Equity".
     The fix is server-side: the unit's full name goes into the row.

  2. It did nothing at all on a phone. The filter marks non-matching rows
     `.nomatch`, and `tr.nomatch { display:none }` was written in each page's own
     <style> — where, under 640px, it LOSES to app.css's
     `table.resp-table tr { display:block }` on specificity. The rows were
     correctly flagged and stayed on screen anyway.

The second one is a CSS-cascade bug with no Python surface, so the guard here is
structural: the rule must live in app.css at the specificity that wins, and the
pages must not quietly reintroduce the copy that loses.
"""
from __future__ import annotations

import os
import re

import pytest

import storage as st

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as fh:
        return fh.read()


@pytest.fixture
def searchable(app_mod):
    """One section with a long, human name and one person in it."""
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    _wipe(conn)
    unit = conn.execute(
        "INSERT INTO org_unit(name, short_name, level, path) VALUES (?,?,?,?)",
        ("Section 4 - Equity in Health and Special Concerns", "S4",
         "section", "SRCHTEST/HSMED/S4")).lastrowid
    conn.execute(
        "INSERT INTO resource_person(name, is_internal, org_unit_id, position)"
        " VALUES (?,1,?,?)", ("SRCH-Person", unit, "Health Program Officer II"))
    conn.commit()
    yield conn
    _wipe(conn)                    # the DB is session-scoped — leave it as found
    conn.commit()
    conn.close()


def _wipe(conn):
    conn.execute("DELETE FROM resource_person WHERE name LIKE 'SRCH-%'")
    conn.execute("DELETE FROM org_unit WHERE path LIKE 'SRCHTEST%'")


def test_the_staff_row_carries_the_section_name_people_actually_type(admin, searchable):
    """The filter matches on the row's text, so what the row says IS the index."""
    page = admin.get("/directory")
    assert page.status_code == 200
    row = re.search(r"SRCH-Person.{0,1200}", page.text, re.S).group(0)

    assert "HSMED/S4" in row                              # the short path, as before
    assert "Section 4 - Equity in Health and Special Concerns" in row


def test_the_hide_rule_outranks_the_responsive_table_rules():
    """`table.resp-table tr { display:block }` inside the <=640px media query is
    (0,1,2); a bare `tr.nomatch` is (0,1,1) and loses to it. The winning selector
    has to be present, or the search box is dead on every phone."""
    css = _read("static", "css", "app.css")
    assert "table.resp-table tr.nomatch" in css
    # ...and it must not be trapped inside a media query — it applies at every width
    assert "table.resp-table tr.nomatch" in _without_at_rules(css)


def _without_at_rules(css):
    """`css` with every @media/@supports block (braces and all) removed, so a
    selector found in what's left is unconditionally in force."""
    out, i = [], 0
    while i < len(css):
        at = css.find("@media", i)
        sup = css.find("@supports", i)
        nxt = min(x for x in (at, sup, len(css)) if x >= 0)
        out.append(css[i:nxt])
        if nxt == len(css):
            break
        depth, j = 0, css.index("{", nxt)
        for j in range(j, len(css)):
            if css[j] == "{":
                depth += 1
            elif css[j] == "}":
                depth -= 1
                if depth == 0:
                    break
        i = j + 1
    return "".join(out)


@pytest.mark.parametrize("template", ["directory.html", "users.html"])
def test_pages_do_not_reintroduce_the_losing_copy(template):
    """A page-local `tr.nomatch { display:none }` looks right and silently fails
    under 640px. app.css owns this rule now."""
    body = _read("templates", template)
    assert not re.search(r"^\s*tr\.nomatch\s*\{", body, re.M), (
        f"{template} redefines tr.nomatch locally — it loses to app.css's "
        "table.resp-table rules under 640px. Delete it and rely on app.css.")


def test_every_search_box_on_the_page_has_a_table_to_filter(admin, searchable):
    """filterTable() walks up to the enclosing .dcard and takes the table inside
    it, so a search box in a card with no table is a silently dead box."""
    page = admin.get("/directory").text
    cards = page.split('<div class="dcard"')
    for card in cards[1:]:
        if 'class="dsearch"' not in card:
            continue
        assert '<table' in card, "a search box sits in a card with no table"
