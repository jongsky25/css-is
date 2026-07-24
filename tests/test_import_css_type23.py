"""import_css_type23 — the CSS.xlsx (Type 2 + Type 3) loader.

Locks the behaviour that matters for the request:
  * Type-2 activity feedback imports in full, spelling-variant titles collapsing
    into one activity form_instance;
  * Type-3 feedback imports ONLY for internal-staff resource persons — external
    guests and unmatched names are skipped, never invented;
  * a re-run is idempotent (same counts, no duplication);
  * the rows land as real answers/atoms the engine can read.

Uses a synthetic workbook so the test carries no dependency on the delivered
spreadsheet.
"""
from __future__ import annotations
import openpyxl
import pytest

import storage as st
import import_css_type23 as imp


def _t2_row(ws, ts, sex, doh, activity, a, bs, c, comment=""):
    row = [None] * 22
    row[0], row[4], row[5], row[7] = ts, sex, doh, activity
    row[8] = a
    for i in range(9):
        row[9 + i] = bs[i]
    row[18] = c
    row[21] = comment
    ws.append(row)


def _t3_row(ws, ts, sex, doh, rp, a, bs, c, comment=""):
    row = [None] * 19
    row[0], row[3], row[4], row[6] = ts, sex, doh, rp
    row[7] = a
    for i in range(9):
        row[8 + i] = bs[i]
    row[17] = c
    row[18] = comment
    ws.append(row)


@pytest.fixture
def workbook(tmp_path):
    wb = openpyxl.Workbook()
    t2 = wb.active
    t2.title = "Type 2"
    t2.append(["Timestamp", "Email", "Last", "First", "sex", "doh", "ifno",
               "Activity Title", "A"] + [f"B{i}" for i in range(1, 10)]
              + ["C", "SQE", "cnt", "Comment"])
    good = [7, 7, 7, 7, 6, 6, 6, 6, 6]
    # three spelling variants of ONE activity + a genuinely distinct one
    _t2_row(t2, "5/28/2026 10:00:00", "Male (Lalaki)", "Yes (Oo)",
            "National Equity in Health Strategic Alignment Activity", 7, good, 4, "great")
    _t2_row(t2, "5/28/2026 10:05:00", "Female (Babae)", "No (Hindi)",
            "national equity in health strategic alignment activity", 6, good, 4)
    _t2_row(t2, "5/28/2026 10:06:00", "Female (Babae)", "Yes (Oo)",
            "National Equity in Health Strategic Alignment Activitu", 7, good, 3)
    _t2_row(t2, "5/28/2026 11:00:00", "Male (Lalaki)", "Yes (Oo)",
            "Pretest of draft brochure on LHS", 7, good, 4)

    t3 = wb.create_sheet("Type 3")
    t3.append(["Timestamp", "Email", "Full name", "sex", "doh", "ifno",
               "RP", "A"] + [f"B{i}" for i in range(1, 10)] + ["C", "Comment"])
    # internal person, two spelling variants -> one cluster, both imported
    _t3_row(t3, "5/26/2026 09:00:00", "Female (Babae)", "Yes (Oo)",
            "Maria Teresa Santiago", 7, good, 4, "well prepared")
    _t3_row(t3, "5/26/2026 09:05:00", "Male (Lalaki)", "Yes (Oo)",
            "Ms. Maria Teresa Santiago", 7, good, 4)
    # external guest -> skipped
    _t3_row(t3, "5/26/2026 09:10:00", "Female (Babae)", "No (Hindi)",
            "Vlanche April Dulfo", 7, good, 4)
    # nobody in the registry -> skipped
    _t3_row(t3, "5/26/2026 09:15:00", "Male (Lalaki)", "Yes (Oo)",
            "Jinky Espino", 7, good, 4)

    path = str(tmp_path / "CSS.xlsx")
    wb.save(path)
    return path


@pytest.fixture
def db(tmp_path):
    conn = st.connect(str(tmp_path / "t.db"))
    st.init_db(conn)
    st.get_or_create_blhsd(conn)
    st.add_rp(conn, "Maria Teresa Santiago", is_internal=True)
    st.add_rp(conn, "Vlanche April Dulfo", is_internal=False)
    return conn


def test_type3_imports_internal_only(workbook, db):
    counts, decisions = imp.apply_import(db, imp.load_type2(workbook),
                                         imp.load_type3(workbook))
    # internal Santiago (2 rows, 2 variants) imported into one form_instance
    assert counts["t3_fi"] == 1
    assert counts["t3_resp"] == 2
    assert decisions["Maria Teresa Santiago"]["action"] == "import"
    assert decisions["Vlanche April Dulfo"]["action"] == "skip-external"
    assert decisions["Jinky Espino"]["action"] == "skip-unmatched"
    # no Type-3 form_instance may point at an external / non-internal person
    bad = db.execute(
        "SELECT COUNT(*) FROM form_instance fi JOIN resource_person rp "
        "ON rp.id=fi.rp_id WHERE fi.qr_token LIKE ? AND COALESCE(rp.is_internal,0)=0",
        (imp.TAG_T3 + "%",)).fetchone()[0]
    assert bad == 0


def test_type2_imports_all_and_clusters_titles(workbook, db):
    counts, _ = imp.apply_import(db, imp.load_type2(workbook), imp.load_type3(workbook))
    assert counts["t2_resp"] == 4          # every activity response kept
    assert counts["t2_fi"] == 2            # 3 spelling variants -> 1, plus the LHS one


def test_sex_and_affil_recorded(workbook, db):
    imp.apply_import(db, imp.load_type2(workbook), imp.load_type3(workbook))
    sexes = dict(db.execute(
        "SELECT text, COUNT(*) FROM item_remark WHERE item_id='SEX' GROUP BY text"))
    affils = dict(db.execute(
        "SELECT text, COUNT(*) FROM item_remark WHERE item_id='AFFIL' GROUP BY text"))
    assert set(sexes) <= {"M", "F"} and sum(sexes.values()) == 6   # 4 T2 + 2 T3
    assert set(affils) <= {"DOH", "NON-DOH"}


def test_reimport_is_idempotent(workbook, db):
    t2, t3 = imp.load_type2(workbook), imp.load_type3(workbook)
    first, _ = imp.apply_import(db, t2, t3)
    second, _ = imp.apply_import(db, t2, t3)
    assert first == second
    total_fi = db.execute(
        "SELECT COUNT(*) FROM form_instance WHERE qr_token LIKE ? OR qr_token LIKE ?",
        (imp.TAG_T2 + "%", imp.TAG_T3 + "%")).fetchone()[0]
    assert total_fi == first["t2_fi"] + first["t3_fi"]


def test_answers_land_as_atoms(workbook, db):
    imp.apply_import(db, imp.load_type2(workbook), imp.load_type3(workbook))
    # C is on the 1-4 scale; B/A on 1-7 — a spot check that values persisted
    a_vals = [r[0] for r in db.execute(
        "SELECT value FROM answer WHERE item_id='A' AND is_na=0")]
    c_vals = [r[0] for r in db.execute(
        "SELECT value FROM answer WHERE item_id='C' AND is_na=0")]
    assert a_vals and max(a_vals) <= 7
    assert c_vals and max(c_vals) <= 4
