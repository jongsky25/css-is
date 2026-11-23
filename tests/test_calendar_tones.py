"""Section calendar colours: chosen by section heads, first come, first served, and
always clearly different from each other (docs/ORG_RESTRUCTURE_ASSESSMENT.md)."""
from __future__ import annotations

import itertools
import pathlib
import re

import pytest

import calendar_tones as ct
import storage as st

ROOT = pathlib.Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("theme", ["light", "dark"])
def test_every_pair_of_colours_looks_clearly_different(theme):
    for a, b in itertools.combinations(ct.TONES, 2):
        d = ct.distance(ct.PALETTE[a][theme], ct.PALETTE[b][theme])
        assert d >= ct.MIN_DISTANCE, (theme, a, b, round(d))


def test_there_is_a_colour_for_the_bureau_and_all_ten_sections():
    assert len(ct.TONES) >= 11


def test_the_stylesheets_draw_every_colour_in_every_theme():
    css = (ROOT / "static/css/calendar.css").read_text()
    schedule = (ROOT / "static/css/calendar-schedule.css").read_text()
    themes = re.split(r":root\[data-theme=", css.split(".cal-bar")[0])
    assert len(themes) == 3                                   # light, dark, contrast
    for t in ct.TONES:
        for block in themes:
            assert f"--cal-{t}:" in block and f"--cal-{t}-bg:" in block, t
        assert ct.PALETTE[t]["light"].lower() in themes[0].lower(), t
        assert ct.PALETTE[t]["dark"].lower() in themes[1].lower(), t
        for sel in (".cal-item", ".cal-unit-key", ".cal-unit", ".cal-mdots i"):
            assert f'{sel}[data-tone="{t}"]' in css, (sel, t)
        assert f"[data-tone={t}]" in schedule, t


@pytest.fixture()
def sections(app_mod):
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    st.set_setting(conn, ct.SETTING, "{}")

    def unit(name, path):
        return conn.execute("INSERT INTO org_unit(name, short_name, level, path) VALUES (?,?,?,?)",
                            (name, path.rsplit("/", 1)[-1], "section", path)).lastrowid

    def head(key, org):
        rp = conn.execute("INSERT INTO resource_person(name, is_internal, org_unit_id, designation) "
                          "VALUES (?,1,?,'Section Head')", (f"CT {key}", org)).lastrowid
        uid = st.create_admin_user(conn, f"ct-{key}@test.local", "x", "y", "section_manager", rp_id=rp)
        return {"id": uid, "username": f"ct-{key}@test.local", "role": "section_manager"}

    s7, s8 = unit("Section 7 Local Health Planning", "CT/S7"), unit("Section 8 Local Health Financing", "CT/S8")
    out = {"conn": conn, "s7": s7, "s8": s8, "head7": head("h7", s7), "head8": head("h8", s8)}
    conn.commit()
    yield out
    conn.close()


def test_first_come_first_served(sections):
    conn = sections["conn"]
    assert ct.choose(conn, sections["head7"], sections["s7"], "pink") == "pink"
    with pytest.raises(ValueError, match="already Section 7"):
        ct.choose(conn, sections["head8"], sections["s8"], "pink")
    ct.choose(conn, sections["head8"], sections["s8"], "lime")
    assert ct.registry(conn)[sections["s7"]] == "pink" and ct.registry(conn)[sections["s8"]] == "lime"


def test_changing_and_releasing_frees_the_old_colour(sections):
    conn = sections["conn"]
    ct.choose(conn, sections["head7"], sections["s7"], "pink")
    ct.choose(conn, sections["head7"], sections["s7"], "red")
    ct.choose(conn, sections["head8"], sections["s8"], "pink")           # pink is free again
    ct.release(conn, sections["head8"], sections["s8"])
    assert sections["s8"] not in ct.registry(conn) and ct.holders(conn) == {"red": sections["s7"]}


def test_only_that_sections_head_or_an_admin_may_choose(sections):
    conn = sections["conn"]
    with pytest.raises(PermissionError):
        ct.choose(conn, sections["head8"], sections["s7"], "pink")
    with pytest.raises(ValueError):
        ct.choose(conn, sections["head7"], sections["s7"], "beige")
    admin = {"id": 0, "username": "admin@test.local", "role": "admin"}
    ct.choose(conn, admin, sections["s7"], "maroon")
    assert ct.registry(conn)[sections["s7"]] == "maroon"


def test_section_number_mentions_follow_the_chosen_colour(sections):
    conn = sections["conn"]
    ct.choose(conn, sections["head7"], sections["s7"], "pink")
    assert ct.section_number_tones(conn)[7] == "pink"


def test_the_colours_page_lists_every_colour_and_lets_an_admin_choose(admin, sections):
    page = admin.get("/calendar/colours")
    assert page.status_code == 200 and all(ct.PALETTE[t]["label"] in page.text for t in ct.TONES)
    r = admin.post("/calendar/colours", data={"unit_id": str(sections["s7"]), "tone": "lime"})
    assert r.status_code == 200 and "Lime is now your calendar colour" in r.text
    r = admin.post("/calendar/colours", data={"unit_id": str(sections["s8"]), "tone": "lime"})
    assert r.status_code == 409 and "already" in r.text


def test_a_viewer_cannot_choose_for_a_section(viewer, sections):
    r = viewer.post("/calendar/colours", data={"unit_id": str(sections["s7"]), "tone": "lime"})
    assert r.status_code == 403
