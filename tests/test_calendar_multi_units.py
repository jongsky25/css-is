"""An item can involve more than one section (Spot Feedback #129): the owning unit stays the
primary one, `extra_org_ids` adds the others. Throwaway DB, no HTTP."""
from __future__ import annotations

import pytest

import office_calendar as oc
import storage as st
from tests.test_calendar_scope import DAY, WIN, add, titles, world  # noqa: F401  (world is a fixture)


def test_extra_units_are_stored_listed_and_exclude_the_primary(world):
    u = world["unit"]
    eid = add(world, "Joint", owner="T/D1/S1",
              extra_org_ids=[u["T/D1/S2"], u["T/D1/S2"], u["T/D1/S1"]])
    e = st.cal_get(world["conn"], eid)
    assert e["owner_org_id"] == u["T/D1/S1"]
    assert e["extra_org_ids"] == [u["T/D1/S2"]]


def test_an_unknown_unit_is_refused(world):
    with pytest.raises(ValueError):
        add(world, "Bad", owner="T/D1/S1", extra_org_ids=[999999])


def test_every_involved_section_sees_it_and_others_do_not(world):
    u = world["unit"]
    add(world, "Joint", owner="T/D1/S1", extra_org_ids=[u["T/D2/S3"]])
    assert "Joint" in titles(world, world["s1"], scope="section")
    assert "Joint" in titles(world, world["s3"], scope="section")    # the extra section
    assert "Joint" not in titles(world, world["s2"], scope="section")  # an uninvolved section
    assert "Joint" not in titles(world, world["s2"], scope="bureau")   # ...and it cannot see it at all


def test_item_labels_every_unit_and_the_filter_matches_any(world):
    u = world["unit"]
    add(world, "Joint", owner="T/D1/S1", extra_org_ids=[u["T/D1/S2"]], audience="bureau")
    item = next(i for i in oc.items_between(world["conn"], world["director"], *WIN, scope="bureau")
                if i["title"] == "Joint")
    assert item["owner_label"] == "S1 + S2"
    assert item["owner_org_id"] == u["T/D1/S1"]
    assert item["owner_org_ids"] == [u["T/D1/S1"], u["T/D1/S2"]]
    for pick in ("T/D1/S1", "T/D1/S2"):
        assert oc.apply_filters([item], {"owner_org_ids": {u[pick]}}) == [item]
    assert oc.apply_filters([item], {"owner_org_ids": {u["T/D2/S3"]}}) == []


def test_update_replaces_the_list_and_records_a_change(world):
    u, conn = world["unit"], world["conn"]
    eid = add(world, "Joint", owner="T/D1/S1")
    st.cal_update(conn, eid, by="x", extra_org_ids=[u["T/D1/S2"], u["T/D2/S3"]])
    assert st.cal_get(conn, eid)["extra_org_ids"] == sorted([u["T/D1/S2"], u["T/D2/S3"]])
    assert "extra_orgs" in st.cal_revisions(conn, eid)[0]["diff"]
    seq = st.cal_get(conn, eid)["sequence"]
    st.cal_update(conn, eid, by="x", title="Renamed")        # leaving the list out keeps it
    assert st.cal_get(conn, eid)["extra_org_ids"] == sorted([u["T/D1/S2"], u["T/D2/S3"]])
    assert st.cal_get(conn, eid)["sequence"] == seq          # no new calendar version for a unit change
    st.cal_update(conn, eid, by="x", extra_org_ids=[])
    assert st.cal_get(conn, eid)["extra_org_ids"] == []


def test_making_an_extra_unit_the_owner_drops_it_from_the_list(world):
    u, conn = world["unit"], world["conn"]
    eid = add(world, "Joint", owner="T/D1/S1", extra_org_ids=[u["T/D1/S2"]])
    st.cal_update(conn, eid, by="x", owner_org_id=u["T/D1/S2"])
    e = st.cal_get(conn, eid)
    assert e["owner_org_id"] == u["T/D1/S2"] and e["extra_org_ids"] == []


def test_delete_removes_the_links(world):
    u, conn = world["unit"], world["conn"]
    eid = add(world, "Joint", owner="T/D1/S1", extra_org_ids=[u["T/D1/S2"]])
    st.cal_delete(conn, eid)
    assert conn.execute("SELECT COUNT(*) FROM calendar_entry_unit").fetchone()[0] == 0
