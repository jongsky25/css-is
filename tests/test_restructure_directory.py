"""Phase 2 restructure tooling: move/retire units and the restructure script.

Synthetic OLD directory (2 divisions, sections, one Office of the Director, an
Administrative Section) is moved onto the committed interim-structure plan.
"""
from __future__ import annotations

import json
import os
import sqlite3

import pytest

import storage as st
from scripts import restructure_directory as rd


@pytest.fixture()
def old_bureau(tmp_path):
    db = str(tmp_path / "office.db")
    conn = st.connect(db)
    st.init_db(conn)
    for table in ("section_oic",):
        conn.execute(f"DELETE FROM {table}")
    conn.execute("UPDATE resource_person SET org_unit_id=NULL")
    conn.execute("DELETE FROM org_unit")

    def unit(name, level, path):
        return conn.execute("INSERT INTO org_unit(name, short_name, level, path) VALUES (?,?,?,?)",
                            (name, path.rsplit("/", 1)[-1], level, path)).lastrowid

    def person(name, org, desig=None, pos=None):
        return conn.execute("INSERT INTO resource_person(name, is_internal, org_unit_id, designation, position) "
                            "VALUES (?,1,?,?,?)", (name, org, desig, pos)).lastrowid

    u = {"bureau": unit("Test Bureau", "bureau", "BLHSD"),
         "od": unit("Office of the Director", "office", "BLHSD/OD"),
         "hsdd": unit("Health Systems Development Division", "division", "BLHSD/HSDD"),
         "s2": unit("Section 2 - Planning & Financing", "section", "BLHSD/HSDD/S2"),
         "admin": unit("Administrative Section", "section", "BLHSD/ADMIN")}
    p = {"dir": person("RS Director", u["od"], None, "OIC-Director IV"),
         "chief": person("RS Chief", u["hsdd"], "Division Chief"),
         "head": person("RS Head", u["s2"], "Section Head"),
         "staff": person("RS Staff", u["s2"]),
         "former": person("RS Former", u["s2"]),
         "admin_head": person("RS Admin Head", u["admin"], "Admin Head")}
    conn.execute("UPDATE resource_person SET archived_at='2026-01-01' WHERE id=?", (p["former"],))
    conn.commit()
    conn.close()
    with open(rd.DEFAULT_PLAN, encoding="utf-8") as f:
        plan = json.load(f)
    mapping = {"bureau_path": "BLHSD",
               "reuse": {"BLHSD/OD": "OD4", "BLHSD/ADMIN": "AU"},
               "retire": ["BLHSD/HSDD/S2", "BLHSD/HSDD"],
               "staff": [{"rp_id": p["chief"], "unit": "LHPFD"},
                         {"rp_id": p["head"], "unit": "S7"},
                         {"name": "RS Staff", "unit": "S8"}]}
    mpath = tmp_path / "mapping.json"
    mpath.write_text(json.dumps(mapping))
    return {"db": db, "u": u, "p": p, "plan": plan, "mapping": mapping, "mpath": str(mpath)}


def _path_of(conn, rp_id):
    return conn.execute("SELECT ou.path FROM resource_person rp JOIN org_unit ou ON ou.id=rp.org_unit_id "
                        "WHERE rp.id=?", (rp_id,)).fetchone()[0]


def test_dry_run_changes_nothing(old_bureau, capsys):
    before = sqlite3.connect(old_bureau["db"]).execute("SELECT * FROM org_unit ORDER BY id").fetchall()
    assert rd.main(["--db", old_bureau["db"], "--mapping", old_bureau["mpath"]]) == 0
    out = capsys.readouterr().out
    assert "MOVE   BLHSD/OD -> BLHSD/OD4" in out and "RETIRE BLHSD/HSDD" in out and "Dry run only" in out
    after = sqlite3.connect(old_bureau["db"]).execute("SELECT * FROM org_unit ORDER BY id").fetchall()
    assert before == after
    assert not [f for f in os.listdir(os.path.dirname(old_bureau["db"])) if "pre-restructure" in f]


def test_apply_builds_the_new_tree_keeps_ids_and_retires_old_units(old_bureau, capsys):
    assert rd.main(["--db", old_bureau["db"], "--mapping", old_bureau["mpath"], "--apply"]) == 0
    assert "Applied. Backup:" in capsys.readouterr().out
    assert [f for f in os.listdir(os.path.dirname(old_bureau["db"])) if "pre-restructure" in f]
    conn = st.connect(old_bureau["db"])
    u, p = old_bureau["u"], old_bureau["p"]
    # Reused units keep their ids; the Director and admin head followed them.
    assert conn.execute("SELECT path, name FROM org_unit WHERE id=?", (u["od"],)).fetchone() == (
        "BLHSD/OD4", "Office of the Director IV")
    assert conn.execute("SELECT path, name, level FROM org_unit WHERE id=?", (u["admin"],)).fetchone() == (
        "BLHSD/ADMIN", "Administrative Unit", "section")
    assert _path_of(conn, p["dir"]) == "BLHSD/OD4"
    assert _path_of(conn, p["admin_head"]) == "BLHSD/ADMIN"
    # Every plan unit exists at its path.
    for unit in old_bureau["plan"]["units"]:
        assert conn.execute("SELECT 1 FROM org_unit WHERE path=? AND retired_at IS NULL",
                            (unit["path"],)).fetchone(), unit["path"]
    assert _path_of(conn, p["chief"]) == "BLHSD/OD3/LHPFD"
    assert _path_of(conn, p["head"]) == "BLHSD/OD3/LHPFD/S7"
    assert _path_of(conn, p["staff"]) == "BLHSD/OD3/LHPFD/S8"
    # Old units are retired, not deleted; the archived staffer stays as history.
    for key in ("hsdd", "s2"):
        assert conn.execute("SELECT retired_at FROM org_unit WHERE id=?", (u[key],)).fetchone()[0]
    assert conn.execute("SELECT org_unit_id FROM resource_person WHERE id=?", (p["former"],)).fetchone()[0] == u["s2"]
    assert not st.unit_is_active(conn, u["s2"]) and st.unit_is_active(conn, u["admin"])
    # Re-running is a no-op.
    conn.close()
    assert rd.main(["--db", old_bureau["db"], "--mapping", old_bureau["mpath"]]) == 0
    assert "CREATE" not in capsys.readouterr().out


def test_retiring_a_unit_that_still_has_staff_stops_everything(old_bureau, tmp_path, capsys):
    mapping = dict(old_bureau["mapping"], staff=[])          # nobody moved out of S2
    mpath = tmp_path / "bad.json"
    mpath.write_text(json.dumps(mapping))
    before = sqlite3.connect(old_bureau["db"]).execute("SELECT * FROM org_unit ORDER BY id").fetchall()
    assert rd.main(["--db", old_bureau["db"], "--mapping", str(mpath), "--apply"]) == 2
    assert "Cannot retire BLHSD/HSDD/S2" in capsys.readouterr().err
    assert sqlite3.connect(old_bureau["db"]).execute("SELECT * FROM org_unit ORDER BY id").fetchall() == before


def test_move_rewrites_descendant_paths_and_refuses_cycles(old_bureau):
    conn = st.connect(old_bureau["db"])
    u = old_bureau["u"]
    assert st.move_org_unit(conn, u["hsdd"], u["od"], "D1") == "BLHSD/OD/D1"
    assert conn.execute("SELECT path FROM org_unit WHERE id=?", (u["s2"],)).fetchone()[0] == "BLHSD/OD/D1/S2"
    with pytest.raises(ValueError):
        st.move_org_unit(conn, u["od"], u["s2"])
    with pytest.raises(ValueError):
        st.move_org_unit(conn, u["admin"], u["od"], "D1")       # path taken


def test_delete_is_refused_while_anything_references_the_unit(old_bureau):
    conn = st.connect(old_bureau["db"])
    u, p = old_bureau["u"], old_bureau["p"]
    conn.execute("UPDATE resource_person SET org_unit_id=NULL WHERE id IN (?,?)", (p["head"], p["staff"]))
    conn.commit()
    ok, reason = st.org_unit_deletable(conn, u["s2"])           # archived staffer still points at it
    assert not ok and "has staff assigned" in reason
    assert st.org_unit_references(conn, u["s2"]) == {"resource_person": 1}


@pytest.mark.parametrize("directory, dpo", [
    ("Canares, Rustom", "Rustom Cañares"),
    ("Ramos, Raile Jay", "Ralie Jay Ramos"),
    ("Reneva, Krizza Camille", "Krizza Camille Reñeva"),
    ("Castro, Mary Anne Millscents", "Mary Anne Milliscent Castro"),
    ("Gajitos, Maria Lourdes B.", "Dr. Maria Lourdes Gajitos, MO V"),
    ("Maria Teresa C. Santiago", "Ma. Teresa Santiago"),
])
def test_names_match_across_order_accents_titles_and_small_typos(directory, dpo):
    assert rd._name_score(directory, dpo) >= 0.9


@pytest.mark.parametrize("a, b", [
    ("Santiago, Marifel", "Ma. Carmela Santiago"),
    ("Dela Cruz, June", "Chariza dela Cruz"),
    ("Hizon, Irene", "Henry Miguel Hizon"),
])
def test_different_people_sharing_a_surname_do_not_match(a, b):
    assert rd._name_score(a, b) == 0.0


def test_unknown_and_ambiguous_names_stop_the_run_and_are_all_listed(old_bureau, tmp_path, capsys):
    conn = st.connect(old_bureau["db"])
    conn.execute("INSERT INTO resource_person(name, is_internal, org_unit_id) VALUES ('Staff, RS', 1, NULL)")
    conn.commit(); conn.close()
    mapping = dict(old_bureau["mapping"], staff=old_bureau["mapping"]["staff"][:2] + [
        {"name": "RS Staff", "unit": "S8"}, {"name": "Nobody Here", "unit": "S8"}])
    mpath = tmp_path / "names.json"
    mpath.write_text(json.dumps(mapping))
    assert rd.main(["--db", old_bureau["db"], "--mapping", str(mpath)]) == 2
    err = capsys.readouterr().err
    assert "matches more than one record" in err and "No current staff record matches 'Nobody Here'" in err


def test_a_former_lead_placed_as_a_member_loses_the_lead_title(old_bureau, tmp_path):
    p = old_bureau["p"]
    mapping = dict(old_bureau["mapping"], staff=[{"rp_id": p["chief"], "unit": "LHPFD", "designation": "Division Chief"},
                                                 {"name": "RS Head", "unit": "S8"},          # head -> member
                                                 {"rp_id": p["staff"], "unit": "S7", "designation": "Section Head"}])
    mpath = tmp_path / "lead.json"
    mpath.write_text(json.dumps(mapping))
    assert rd.main(["--db", old_bureau["db"], "--mapping", str(mpath), "--apply"]) == 0
    conn = st.connect(old_bureau["db"])
    desig = dict(conn.execute("SELECT id, designation FROM resource_person WHERE id IN (?,?,?)",
                              (p["chief"], p["head"], p["staff"])).fetchall())
    assert desig == {p["chief"]: "Division Chief", p["head"]: None, p["staff"]: "Section Head"}


def test_create_missing_adds_records_only_when_asked(old_bureau, tmp_path, capsys):
    staff = old_bureau["mapping"]["staff"] + [{"name": "Brand New Person", "unit": "S9", "designation": "Section Head"}]
    for flag, code in ((False, 2), (True, 0)):
        mpath = tmp_path / f"new-{flag}.json"
        mpath.write_text(json.dumps(dict(old_bureau["mapping"], staff=staff, create_missing=flag)))
        assert rd.main(["--db", old_bureau["db"], "--mapping", str(mpath), "--apply"]) == code
    assert "NEW    #" in capsys.readouterr().out
    conn = st.connect(old_bureau["db"])
    row = conn.execute("SELECT rp.designation, ou.path FROM resource_person rp JOIN org_unit ou ON ou.id=rp.org_unit_id "
                       "WHERE rp.name='Brand New Person'").fetchone()
    assert row == ("Section Head", "BLHSD/OD3/LHSSD/S9")


def test_an_acting_oic_on_a_retiring_unit_is_cleared_and_logged(old_bureau, capsys):
    conn = st.connect(old_bureau["db"])
    acct = st.create_admin_user(conn, "rs-oic@test.local", "x", "y", "section_manager", rp_id=old_bureau["p"]["admin_head"])
    st.set_section_oic(conn, old_bureau["u"]["s2"], acct)
    conn.close()
    assert rd.main(["--db", old_bureau["db"], "--mapping", old_bureau["mpath"], "--apply"]) == 0
    assert "CLEAR  acting OIC of BLHSD/HSDD/S2" in capsys.readouterr().out
    conn = st.connect(old_bureau["db"])
    assert conn.execute("SELECT COUNT(*) FROM section_oic").fetchone()[0] == 0
