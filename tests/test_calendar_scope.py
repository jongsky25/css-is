"""Office calendar scope (increment A2): who may see which items, and that a
requested scope can only NARROW what a viewer may see. Throwaway DB, no HTTP."""
from __future__ import annotations
from datetime import date

import pytest

import office_calendar as oc
import storage as st

DAY = "2026-10-06"
WIN = ("2026-10-01", "2026-10-31")


@pytest.fixture()
def world(tmp_path):
    """Bureau T > divisions D1, D2 > sections S1, S2 (in D1), S3 (in D2), plus an
    Office of the Director, and one account per interesting viewer."""
    conn = st.connect(str(tmp_path / "scope.db"))
    st.init_db(conn)
    unit = {}
    for path, level in (("T", "bureau"), ("T/D1", "division"), ("T/D2", "division"),
                        ("T/D1/S1", "section"), ("T/D1/S2", "section"),
                        ("T/D2/S3", "section"), ("T/OD", "office")):
        unit[path] = conn.execute(
            "INSERT INTO org_unit(name, short_name, level, path) VALUES (?,?,?,?)",
            (path, path.rsplit("/", 1)[-1], level, path)).lastrowid

    def account(label, path=None, designation=None):
        rp = conn.execute(
            "INSERT INTO resource_person(name, is_internal, org_unit_id, designation) "
            "VALUES (?,1,?,?)", (f"P {label}", unit.get(path), designation)).lastrowid if path else None
        uid = st.create_admin_user(conn, f"{label}@test.local", "x", "y", "viewer", rp_id=rp)
        return {"id": uid, "username": f"{label}@test.local", "role": "viewer"}

    w = {"conn": conn, "unit": unit,
         "s1": account("s1", "T/D1/S1"), "s1b": account("s1b", "T/D1/S1"),
         "s2": account("s2", "T/D1/S2"), "s3": account("s3", "T/D2/S3"),
         "d1chief": account("d1chief", "T/D1", "Division Chief"),
         "director": account("director", "T/OD", "Director"),
         "unlinked": account("unlinked"), "grant": account("grant")}
    conn.execute("UPDATE admin_user SET bureau_access='all' WHERE id=?", (w["grant"]["id"],))
    conn.commit()
    return w


def add(w, title, *, owner=None, audience="unit", people=(), by=None, day=DAY, **kw):
    return st.cal_create(w["conn"], title, day, owner_org_id=w["unit"].get(owner),
                         audience=audience, people=[p["id"] for p in people],
                         by=by, **kw)


def titles(w, viewer, scope="blend", **kw):
    return [i["title"] for i in oc.items_between(w["conn"], viewer, *WIN, scope=scope, **kw)
            if i["layer"] == "entries"]


# ---------------------------------------------------------------- visibility ---

def test_bureau_audience_is_visible_to_everyone_including_unlinked(world):
    add(world, "Strat Planning", owner="T", audience="bureau")
    for who in ("s1", "s3", "d1chief", "director", "unlinked", "grant"):
        assert titles(world, world[who]) == ["Strat Planning"], who


def test_unit_audience_follows_the_directory(world):
    add(world, "S1 huddle", owner="T/D1/S1")
    assert titles(world, world["s1"], "bureau") == ["S1 huddle"]
    assert titles(world, world["s1b"], "bureau") == ["S1 huddle"]
    assert titles(world, world["s2"], "bureau") == []          # sibling section
    assert titles(world, world["s3"], "bureau") == []          # other division
    assert titles(world, world["d1chief"], "bureau") == ["S1 huddle"]   # chief sees below
    assert titles(world, world["director"], "bureau") == ["S1 huddle"]
    assert titles(world, world["grant"], "bureau") == ["S1 huddle"]     # explicit grant


def test_a_section_sees_entries_owned_by_its_parent_division(world):
    add(world, "D1 all-hands", owner="T/D1")
    assert titles(world, world["s1"], "bureau") == ["D1 all-hands"]
    assert titles(world, world["s3"], "bureau") == []


def test_unlinked_account_sees_only_bureau_and_its_own(world):
    add(world, "Bureau thing", owner="T", audience="bureau")
    add(world, "Unit thing", owner="T/D1/S1")
    add(world, "Ownerless", owner=None)
    mine = add(world, "Mine", owner="T/D1/S1", people=[world["unlinked"]])
    assert mine
    assert sorted(titles(world, world["unlinked"], "bureau")) == ["Bureau thing", "Mine"]


def test_ownerless_unit_entry_is_only_for_its_people_and_creator(world):
    add(world, "Ownerless", owner=None, people=[world["s2"]], by=world["s1"]["username"])
    assert titles(world, world["s2"]) == ["Ownerless"]
    assert titles(world, world["s1"]) == ["Ownerless"]          # the creator
    assert titles(world, world["s3"], "bureau") == []
    assert titles(world, world["director"], "bureau") == []


def test_people_audience_is_only_the_named_people_and_creator(world):
    add(world, "Private chat", owner="T/D1/S1", audience="people",
        people=[world["s1"]], by=world["s2"]["username"])
    assert titles(world, world["s1"], "bureau") == ["Private chat"]
    assert titles(world, world["s2"], "bureau") == ["Private chat"]   # creator
    for who in ("s1b", "d1chief", "director", "grant", "unlinked", "s3"):
        assert titles(world, world[who], "bureau") == [], who


def test_being_listed_overrides_every_other_rule(world):
    add(world, "Cross-unit", owner="T/D2/S3", people=[world["s1"]])
    assert titles(world, world["s1"], "bureau") == ["Cross-unit"]


def test_an_admin_role_buys_nothing(world):
    add(world, "S1 huddle", owner="T/D1/S1")
    admin = {**world["s3"], "role": "admin"}
    assert titles(world, admin, "bureau") == []


def test_cancelled_entries_are_not_listed(world):
    eid = add(world, "Gone", owner="T", audience="bureau")
    st.cal_cancel(world["conn"], eid)
    assert titles(world, world["s1"]) == []


# --------------------------------------------------------------------- scopes ---

def test_scope_only_narrows_never_widens(world):
    add(world, "Bureau thing", owner="T", audience="bureau")
    add(world, "S1 thing", owner="T/D1/S1")
    add(world, "S3 thing", owner="T/D2/S3")
    for scope in oc.SCOPES:
        got = set(titles(world, world["s1"], scope))
        assert "S3 thing" not in got, scope
        assert got <= {"Bureau thing", "S1 thing"}, scope


def test_scope_mine_vs_blend_vs_section(world):
    add(world, "Bureau thing", owner="T", audience="bureau")
    add(world, "S1 thing", owner="T/D1/S1")
    add(world, "My trip", owner="T/D1/S1", people=[world["s1"]], kind="travel")
    assert titles(world, world["s1"], "mine") == ["My trip"]
    assert sorted(titles(world, world["s1"], "blend")) == ["Bureau thing", "My trip"]
    assert sorted(titles(world, world["s1"], "section")) == [
        "Bureau thing", "My trip", "S1 thing"]
    assert sorted(titles(world, world["s1b"], "section")) == [
        "Bureau thing", "My trip", "S1 thing"]


def test_mine_ignores_the_person_who_only_ran_the_import(world):
    s1 = world["s1"]
    add(world, "Imported thing", owner="T", audience="bureau", by=s1["username"], source="import")
    add(world, "Typed by me", owner="T", audience="bureau", by=s1["username"])
    assert titles(world, s1, "mine") == ["Typed by me"]
    assert sorted(titles(world, s1, "blend")) == ["Imported thing", "Typed by me"]
    add(world, "Imported, I'm on it", owner="T", audience="bureau", by=s1["username"],
        source="import", people=[s1])
    assert "Imported, I'm on it" in titles(world, s1, "mine")


def test_division_scope_includes_sibling_sections_for_a_chief(world):
    add(world, "S1 thing", owner="T/D1/S1")
    add(world, "S2 thing", owner="T/D1/S2")
    add(world, "S3 thing", owner="T/D2/S3")
    assert sorted(titles(world, world["d1chief"], "division")) == ["S1 thing", "S2 thing"]
    assert sorted(titles(world, world["director"], "bureau")) == [
        "S1 thing", "S2 thing", "S3 thing"]
    # a section member's division scope can't reach a sibling's entries
    assert titles(world, world["s1"], "division") == ["S1 thing"]


def test_viewer_context_resolves_section_and_division(world):
    ctx = oc.viewer_context(world["conn"], world["s1"])
    assert (ctx["kind"], ctx["section_path"], ctx["division_path"]) == (
        "unit", "T/D1/S1", "T/D1")
    chief = oc.viewer_context(world["conn"], world["d1chief"])
    assert (chief["section_path"], chief["division_path"]) == ("T/D1", "T/D1")
    none = oc.viewer_context(world["conn"], world["unlinked"])
    assert (none["kind"], none["section_path"], none["division_path"]) == (
        "none", None, None)
    assert oc.viewer_context(world["conn"], world["director"])["kind"] == "bureau"


def test_bad_arguments_raise(world):
    with pytest.raises(ValueError):
        oc.items_between(world["conn"], world["s1"], *WIN, scope="galaxy")
    with pytest.raises(ValueError):
        oc.items_between(world["conn"], world["s1"], *WIN, layers=["nonsense"])
    with pytest.raises(ValueError):
        oc.items_between(world["conn"], world["s1"], "2026-10-31", "2026-10-01")


# ------------------------------------------------------------------ item shape ---

def test_item_shape_people_and_tone(world):
    eid = add(world, "TA Palawan", owner="T", audience="bureau", kind="travel",
              day="2026-10-05", end_date="2026-10-08", start_time="09:00",
              people=[world["s1"]], tags=["PK"], status="tentative")
    (item,) = [i for i in oc.items_between(world["conn"], world["s3"], *WIN)
               if i["layer"] == "entries"]
    assert item["key"] == f"entry:{eid}" and item["url"] == f"/calendar/entries/{eid}"
    assert (item["start"], item["end"], item["all_day"]) == ("2026-10-05", "2026-10-08", False)
    assert item["tone"] == "green" and item["owner_label"] == "T"        # bureau-level unit
    assert item["flags"] == ["tentative"] and item["tags"] == ["PK"]
    assert item["people"][0]["user_id"] == world["s1"]["id"]
    assert item["people"][0]["name"] == "P s1" and item["people"][0]["initials"] == "PS"
    assert item["editable"] is True and item["private"] is False


def test_unit_tone_comes_from_the_setting_when_mapped(world):
    import json
    add(world, "S1 thing", owner="T/D1/S1")
    sid = world["unit"]["T/D1/S1"]
    st.set_setting(world["conn"], oc._TONES_SETTING, json.dumps({str(sid): "yellow"}))
    (item,) = [i for i in oc.items_between(world["conn"], world["s1"], *WIN, scope="section")
               if i["layer"] == "entries"]
    assert item["tone"] == "yellow"


def test_holidays_show_for_everyone_in_every_scope_and_cannot_be_edited(world):
    st.set_holiday(world["conn"], date(2026, 10, 14), "Office Day Off", "special")
    for who in ("s1", "unlinked", "director"):
        for scope in oc.SCOPES:
            hol = [i for i in oc.items_between(world["conn"], world[who], *WIN, scope=scope)
                   if i["layer"] == "holidays"]
            assert [h["title"] for h in hol] == ["Office Day Off"], (who, scope)
    assert hol[0]["editable"] is False and hol[0]["kind"] == "holiday"
    assert hol[0]["start"] == hol[0]["end"] == "2026-10-14"


def test_items_are_merged_and_sorted_by_day_then_time(world):
    st.set_holiday(world["conn"], date(2026, 10, 6), "Holiday", "regular")
    add(world, "Late", owner="T", audience="bureau", start_time="14:00")
    add(world, "Early", owner="T", audience="bureau", start_time="09:00")
    add(world, "Allday", owner="T", audience="bureau")
    add(world, "Earlier day", owner="T", audience="bureau", day="2026-10-02")
    got = [i["title"] for i in oc.items_between(world["conn"], world["s1"], *WIN)]
    assert got == ["Earlier day", "Holiday", "Allday", "Early", "Late"]


def test_layers_filter_limits_providers(world):
    st.set_holiday(world["conn"], date(2026, 10, 6), "Holiday", "regular")
    add(world, "Thing", owner="T", audience="bureau")
    only = oc.items_between(world["conn"], world["s1"], *WIN, layers=["holidays"])
    assert {i["layer"] for i in only} == {"holidays"}


def test_dates_may_be_date_objects(world):
    add(world, "Thing", owner="T", audience="bureau")
    got = oc.items_between(world["conn"], world["s1"], date(2026, 10, 1), date(2026, 10, 31))
    assert [i["title"] for i in got if i["layer"] == "entries"] == ["Thing"]
