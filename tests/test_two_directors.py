"""Two Directors with split oversight (docs/ORG_RESTRUCTURE_ASSESSMENT.md).

Synthetic bureau shaped like the interim BLHSD structure:

    TB                     bureau
    TB/OD4                 office   -- Director IV (top)
    TB/OD4/D1              division -- chief
    TB/OD4/D1/S1           section  -- head + staff
    TB/OD3                 office   -- Director III
    TB/OD3/D4              division -- chief
    TB/OD3/D4/S7           section  -- head + staff
    TB/OD3/MSU             section  -- "Unit Head" + staff
    TB/ADMIN               section  -- "Admin Head" + staff (Administrative Unit)

Owner decisions under test: Director IV decides Director III's own requests;
final approval follows the Director overseeing the owning unit; bureau and AU
items go to Director IV; Director III's team defaults to her office subtree;
the AU lead decides for all AU staff.
"""
from __future__ import annotations

import pytest

import storage as st
import travel


@pytest.fixture()
def bureau(app_mod):
    conn = st.connect(app_mod.DB)
    st.init_db(conn)
    # Isolated copy of the reference DB: retire any seeded Director so only the
    # two synthetic Directors below hold that rank.
    for rp_id, desig, pos in conn.execute(
            "SELECT id, designation, position FROM resource_person "
            "WHERE is_internal=1 AND archived_at IS NULL").fetchall():
        if st._org_rank(desig, pos) == 3:
            conn.execute("UPDATE resource_person SET archived_at='2026-01-01' WHERE id=?", (rp_id,))

    def unit(name, level, path):
        return conn.execute("INSERT INTO org_unit(name, short_name, level, path) VALUES (?,?,?,?)",
                            (name, path.rsplit("/", 1)[-1], level, path)).lastrowid

    def person(name, org, desig=None, pos=None):
        return conn.execute(
            "INSERT INTO resource_person(name, is_internal, org_unit_id, designation, position) "
            "VALUES (?,1,?,?,?)", (name, org, desig, pos)).lastrowid

    def account(key, rp):
        return st.create_admin_user(conn, f"td-{key}@test.local", "x", "y", "section_manager", rp_id=rp)

    u = {}
    u["tb"] = unit("Test Bureau", "bureau", "TB")
    u["od4"] = unit("Office of the Director IV", "office", "TB/OD4")
    u["d1"] = unit("Division 1", "division", "TB/OD4/D1")
    u["s1"] = unit("Section 1", "section", "TB/OD4/D1/S1")
    u["od3"] = unit("Office of the Director III", "office", "TB/OD3")
    u["d4"] = unit("Division 4", "division", "TB/OD3/D4")
    u["s7"] = unit("Section 7", "section", "TB/OD3/D4/S7")
    u["msu"] = unit("Management Support Unit", "section", "TB/OD3/MSU")
    u["au"] = unit("Administrative Unit", "section", "TB/ADMIN")

    a = {}
    a["dir4"] = account("dir4", person("TD Director Four", u["od4"], None, "OIC-Director IV"))
    a["dir3"] = account("dir3", person("TD Director Three", u["od3"], "Director III", "Medical Officer V"))
    a["od4_staff"] = account("od4staff", person("TD Office Four Staff", u["od4"]))
    a["chief1"] = account("chief1", person("TD Chief One", u["d1"], "Division Chief"))
    a["head1"] = account("head1", person("TD Head One", u["s1"], "Section Head"))
    a["staff1"] = account("staff1", person("TD Staff One", u["s1"]))
    a["chief4"] = account("chief4", person("TD Chief Four", u["d4"], "Division Chief"))
    a["head7"] = account("head7", person("TD Head Seven", u["s7"], "Section Head"))
    a["staff7"] = account("staff7", person("TD Staff Seven", u["s7"]))
    a["msu_lead"] = account("msulead", person("TD MSU Lead", u["msu"], "Unit Head"))
    a["msu_staff"] = account("msustaff", person("TD MSU Staff", u["msu"]))
    a["au_lead"] = account("aulead", person("TD AU Lead", u["au"], "Admin Head"))
    a["au_staff"] = account("austaff", person("TD AU Staff", u["au"]))
    conn.commit()
    yield {"conn": conn, "u": u, "a": a}
    conn.close()


def approvers(b, key):
    return set(st.get_approvers_for(b["conn"], b["a"][key]))


def test_each_division_chief_goes_to_their_own_director(bureau):
    a = bureau["a"]
    assert approvers(bureau, "chief1") == {a["dir4"]}
    assert approvers(bureau, "chief4") == {a["dir3"]}


def test_staff_and_section_heads_keep_the_ordinary_chain(bureau):
    a = bureau["a"]
    assert approvers(bureau, "staff1") == {a["head1"]}
    assert approvers(bureau, "head1") == {a["chief1"]}
    assert approvers(bureau, "staff7") == {a["head7"]}
    assert approvers(bureau, "head7") == {a["chief4"]}


def test_msu_lead_goes_to_director_three_and_msu_staff_to_their_lead(bureau):
    a = bureau["a"]
    assert approvers(bureau, "msu_staff") == {a["msu_lead"]}
    assert approvers(bureau, "msu_lead") == {a["dir3"]}


def test_administrative_unit_lead_goes_to_director_four(bureau):
    a = bureau["a"]
    assert approvers(bureau, "au_staff") == {a["au_lead"]}
    assert approvers(bureau, "au_lead") == {a["dir4"]}


def test_director_office_staff_go_to_their_director(bureau):
    assert approvers(bureau, "od4_staff") == {bureau["a"]["dir4"]}


def test_director_three_files_to_director_four_who_alone_auto_approves(bureau):
    conn, a = bureau["conn"], bureau["a"]
    assert approvers(bureau, "dir3") == {a["dir4"]}
    assert approvers(bureau, "dir4") == set()
    assert st._is_director(conn, a["dir4"]) is True
    assert st._is_director(conn, a["dir3"]) is False
    ps = st.work_arrangement_open_periods()[0]
    assert st.get_work_arrangement(conn, st.create_work_arrangement(conn, a["dir3"], ps, "REG"))["status"] == "pending"
    assert st.get_work_arrangement(conn, st.create_work_arrangement(conn, a["dir4"], ps, "REG"))["status"] == "approved"


def test_approver_copy_names_the_right_director(bureau):
    conn, a = bureau["conn"], bureau["a"]
    assert st.approver_name_for(conn, a["chief4"]) == "TD Director Three"
    assert st.approver_name_for(conn, a["chief1"]) == "TD Director Four"
    assert st.approver_name_for(conn, a["dir3"]) == "TD Director Four"
    assert st.approver_name_for(conn, a["dir4"]) is None
    assert st.approver_title_for(conn, a["chief4"]) == "the Director"
    assert st.approver_title_for(conn, a["dir3"]) == "the Director"
    assert st.approver_title_for(conn, a["dir4"]) == "an administrator"


def test_division_oic_follows_the_director_over_that_division(bureau):
    conn, a, u = bureau["conn"], bureau["a"], bureau["u"]
    st.set_section_oic(conn, u["d4"], a["head7"])          # head7 covers Division 4
    assert approvers(bureau, "head7") == {a["dir3"]}


def test_office_oic_is_added_beside_the_director(bureau):
    conn, a, u = bureau["conn"], bureau["a"], bureau["u"]
    st.set_section_oic(conn, u["od3"], a["msu_lead"])      # MSU lead acting for Director III
    assert approvers(bureau, "chief4") == {a["dir3"], a["msu_lead"]}


def test_director_resolution_by_unit(bureau):
    conn, a, u = bureau["conn"], bureau["a"], bureau["u"]
    assert st.director_accounts_for_unit(conn, u["s7"]) == [a["dir3"]]
    assert st.director_accounts_for_unit(conn, u["msu"]) == [a["dir3"]]
    assert st.director_accounts_for_unit(conn, u["s1"]) == [a["dir4"]]
    assert st.director_accounts_for_unit(conn, u["au"]) == [a["dir4"]]
    assert st.director_accounts_for_unit(conn, u["tb"]) == [a["dir4"]]
    assert st.director_accounts_for_unit(conn, None) == [a["dir4"]]
    assert st.org_unit_chiefs(conn, u["od3"]) == [a["dir3"]]
    assert st.org_unit_chiefs(conn, u["tb"]) == [a["dir4"]]


def test_team_scope_director_three_sees_her_office_unless_granted(bureau):
    conn, a = bureau["conn"], bureau["a"]
    assert st.team_scope_for_user(conn, {"id": a["dir4"]}) == (None, "bureau")
    assert st.team_scope_for_user(conn, {"id": a["dir3"]}) == ("TB/OD3", "unit")
    assert st._path_in_scope("TB/OD3/D4/S7", "TB/OD3")
    assert not st._path_in_scope("TB/OD4/D1", "TB/OD3")
    st.set_bureau_access(conn, a["dir3"], "all")
    assert st.team_scope_for_user(conn, {"id": a["dir3"]}) == (None, "bureau")


def test_signatures_use_the_overseeing_director(bureau):
    conn, u = bureau["conn"], bureau["u"]
    assert st.director_seat_holder(conn)[0] == "TD Director Four"
    assert st.director_seat_holder(conn, "TB/OD3/D4/S7") == ("TD Director Three", "Director III")
    out = travel.directory_signers(conn, bureau["a"]["staff7"], {})
    assert out["head_name"] == "TD Director Three"
    assert out["certifier_name"] == "TD Chief Four"
    assert st.work_arrangement_signatories(conn)["approved_by"]["name"] == "TD Director Four"


def test_org_structure_lists_both_offices_top_first(bureau):
    org = st.org_structure(bureau["conn"])
    paths = [o["path"] for o in org["offices"] if o["path"].startswith("TB/")]
    assert paths == ["TB/OD4", "TB/OD3"]
    msu = next(s for s in org["admin_sections"] if s["path"] == "TB/OD3/MSU")
    assert msu["office_name"] == "Office of the Director III"


def test_document_director_authority_follows_the_owning_unit(bureau):
    import documents_permissions as p
    conn, a, u = bureau["conn"], bureau["a"], bureau["u"]
    dir3, dir4 = {"id": a["dir3"]}, {"id": a["dir4"]}
    assert p.director_for(conn, dir3, u["s7"]) and not p.director_for(conn, dir4, u["s7"])
    assert p.director_for(conn, dir4, u["s1"]) and not p.director_for(conn, dir3, u["s1"])
    assert p.director_for(conn, dir4, u["au"]) and not p.director_for(conn, dir3, u["au"])
    doc = {"review_class": "director", "unit_id": u["d4"]}
    assert p.review_authority(conn, dir3, doc) and not p.review_authority(conn, dir4, doc)


def test_advisory_director_stage_follows_the_owning_division(bureau):
    import advisory_review as ar
    conn, a, u = bureau["conn"], bureau["a"], bureau["u"]
    assert ar.effective_director(conn, u["d4"]) == a["dir3"]
    assert ar.effective_director(conn, u["d1"]) == a["dir4"]
    assert ar.effective_director(conn, u["au"]) == a["dir4"]
    st.set_section_oic(conn, u["od3"], a["chief4"])
    assert ar.effective_director(conn, u["d4"]) == a["chief4"]


def test_single_director_directory_behaves_as_before(bureau):
    conn, a, u = bureau["conn"], bureau["a"], bureau["u"]
    conn.execute("UPDATE resource_person SET archived_at='2026-01-01' WHERE name='TD Director Three'")
    conn.commit()
    assert approvers(bureau, "chief4") == {a["dir4"]}
    assert approvers(bureau, "msu_lead") == {a["dir4"]}
    assert st.director_accounts_for_unit(conn, u["s7"]) == [a["dir4"]]


def test_scoped_tree_keeps_each_office(bureau, app_mod):
    org = st.org_structure(bureau["conn"])
    scoped = app_mod._scoped_org_struct(org, "TB/OD3")
    assert [o["path"] for o in scoped["offices"]] == ["TB/OD3"]
    assert {d["path"] for d in scoped["divisions"]} == {"TB/OD3/D4"}
