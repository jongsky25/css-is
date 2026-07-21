"""
Tests for psgc.py — the PSGC crosswalk infrastructure (E4.1).

These use a bare in-memory SQLite connection (no HTTP / app fixtures): the
crosswalk is pure reference-data machinery, so it is tested against its own
schema directly. Codes are synthetic but obey real PSGC nesting (an ancestor's
significant digits prefix every descendant's code).
"""
from __future__ import annotations

import sqlite3

import pytest

import psgc
from psgc import PublicationRow as PR


# --- realistic, well-nested synthetic codes (10-digit) ---------------------
# Region 03 → Prov Bulacan → City Malolos → two barangays;
# plus Region 13 (NCR) → District → City → barangay, to exercise Dist tier.
R_CL   = "0300000000"   # Region III (Central Luzon)
P_BUL  = "0301400000"   # Bulacan          (sig 03014, under 03)
C_MAL  = "0301401000"   # Malolos City     (sig 0301401, under 03014)
B_MAL1 = "0301401001"   # a barangay of Malolos
B_MAL2 = "0301401002"   # another barangay of Malolos

R_NCR  = "1300000000"   # NCR
D_NCR4 = "1339000000"   # an NCR district  (sig 1339, under 13)
C_QC   = "1339020000"   # a city           (sig 133902, under 1339)
B_QC1  = "1339020001"   # a barangay of that city


def _conn():
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    psgc.ensure_schema(conn)
    return conn


def _base_rows():
    """A full, self-contained hierarchy for one vintage."""
    return [
        PR(R_CL,   "Region III (Central Luzon)", psgc.LEVEL_REGION),
        PR(P_BUL,  "Bulacan",                     psgc.LEVEL_PROVINCE),
        PR(C_MAL,  "City of Malolos",             psgc.LEVEL_CITY),
        PR(B_MAL1, "Bagna",                        psgc.LEVEL_BARANGAY),
        PR(B_MAL2, "Santo Niño",                   psgc.LEVEL_BARANGAY),
        PR(R_NCR,  "National Capital Region",     psgc.LEVEL_REGION),
        PR(D_NCR4, "Fourth District",             psgc.LEVEL_DISTRICT),
        PR(C_QC,   "Quezon City",                 psgc.LEVEL_CITY),
        PR(B_QC1,  "Bagong Silang",               psgc.LEVEL_BARANGAY),
    ]


# ---------------------------------------------------------------------------
# schema + code helpers
# ---------------------------------------------------------------------------
def test_ensure_schema_idempotent():
    conn = _conn()
    psgc.ensure_schema(conn)   # second call must not raise
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"dim_geo", "dim_psgc_crosswalk", "psgc_vintage"} <= tables


@pytest.mark.parametrize("raw,expect", [
    ("0301401000", "0301401000"),
    (301401000, "301401000"),
    ("1380700000.0", "1380700000"),
    ("13-8070-0000", "1380700000"),
    ("  ", None),
    (None, None),
])
def test_clean_code(raw, expect):
    assert psgc.clean_code(raw) == expect


def test_ancestor_prefix_nesting_boundary_free():
    # 10-digit chain
    assert psgc.is_ancestor_code(R_CL, P_BUL)
    assert psgc.is_ancestor_code(P_BUL, C_MAL)
    assert psgc.is_ancestor_code(C_MAL, B_MAL1)
    assert psgc.is_ancestor_code(R_CL, B_MAL1)          # transitive
    assert not psgc.is_ancestor_code(B_MAL1, C_MAL)     # not upward
    assert not psgc.is_ancestor_code(C_MAL, C_MAL)      # not self
    assert not psgc.is_ancestor_code(P_BUL, C_QC)       # different region
    # 9-digit legacy chain nests too, with no width knowledge:
    assert psgc.is_ancestor_code("030000000", "030140000")
    assert psgc.is_ancestor_code("030140000", "030140001")


@pytest.mark.parametrize("raw,expect", [
    ("Reg", psgc.LEVEL_REGION), ("Province", psgc.LEVEL_PROVINCE),
    ("Bgy", psgc.LEVEL_BARANGAY), ("Brgy.", psgc.LEVEL_BARANGAY),
    ("City", psgc.LEVEL_CITY), ("SubMun", psgc.LEVEL_SUBMUN),
    ("Dist", psgc.LEVEL_DISTRICT), ("nonsense", None), ("", None),
])
def test_normalize_level(raw, expect):
    assert psgc.normalize_level(raw) == expect


def test_normalize_name_folds_fillers():
    assert psgc.normalize_name("City of Malolos") == psgc.normalize_name("Malolos City")
    assert psgc.normalize_name("Bacoor (Capital)") == "bacoor"


# ---------------------------------------------------------------------------
# hierarchy building in a single load
# ---------------------------------------------------------------------------
def test_load_builds_parent_chain_and_ancestry():
    conn = _conn()
    stats = psgc.load_publication(conn, _base_rows(), "2024Q4", loaded_at="2024-01-01T00:00:00")
    assert stats["total"] == 9
    assert stats["new"] == 9          # first vintage → everything is new

    # barangay B_MAL1 should resolve, and its parent should be Malolos,
    # its province Bulacan, its region Central Luzon.
    sk_b = psgc.resolve_geo(conn, "2024Q4", B_MAL1)
    row = psgc.geo_row(conn, sk_b)
    assert row["level"] == psgc.LEVEL_BARANGAY

    sk_city = psgc.resolve_geo(conn, "2024Q4", C_MAL)
    sk_prov = psgc.resolve_geo(conn, "2024Q4", P_BUL)
    sk_reg  = psgc.resolve_geo(conn, "2024Q4", R_CL)
    assert row["parent_geo_sk"] == sk_city
    assert row["citymun_geo_sk"] == sk_city
    assert row["province_geo_sk"] == sk_prov
    assert row["region_geo_sk"] == sk_reg

    # NCR district sits at the province tier of its barangay's ancestry.
    sk_bqc = psgc.resolve_geo(conn, "2024Q4", B_QC1)
    rq = psgc.geo_row(conn, sk_bqc)
    assert rq["province_geo_sk"] == psgc.resolve_geo(conn, "2024Q4", D_NCR4)
    assert rq["region_geo_sk"] == psgc.resolve_geo(conn, "2024Q4", R_NCR)


def test_two_same_named_barangays_stay_distinct():
    """Rung-3 must not merge two same-named barangays under one city."""
    conn = _conn()
    rows = [
        PR(R_CL,  "Region III", psgc.LEVEL_REGION),
        PR(P_BUL, "Bulacan",    psgc.LEVEL_PROVINCE),
        PR(C_MAL, "Malolos",    psgc.LEVEL_CITY),
        PR(B_MAL1, "San Isidro", psgc.LEVEL_BARANGAY),
        PR(B_MAL2, "San Isidro", psgc.LEVEL_BARANGAY),   # same name, different code
    ]
    psgc.load_publication(conn, rows, "2024Q4", loaded_at="t")
    sk1 = psgc.resolve_geo(conn, "2024Q4", B_MAL1)
    sk2 = psgc.resolve_geo(conn, "2024Q4", B_MAL2)
    assert sk1 != sk2


# ---------------------------------------------------------------------------
# resolution ladder across vintages
# ---------------------------------------------------------------------------
def test_exact_code_stable_across_vintages():
    conn = _conn()
    psgc.load_publication(conn, _base_rows(), "2023Q4", loaded_at="t1")
    before = psgc.resolve_geo(conn, "2023Q4", C_MAL)

    stats = psgc.load_publication(conn, _base_rows(), "2024Q4", loaded_at="t2")
    # identical file → every place matched by exact code, nothing new.
    assert stats["new"] == 0
    assert stats["exact"] == 9
    after = psgc.resolve_geo(conn, "2024Q4", C_MAL)
    assert before == after                       # same canonical identity
    # both vintages independently resolvable
    assert psgc.resolve_geo(conn, "2023Q4", C_MAL) == before


def test_correspondence_code_bridges_renumber():
    conn = _conn()
    # v1: legacy code for Malolos.
    v1 = [
        PR(R_CL,  "Region III", psgc.LEVEL_REGION),
        PR(P_BUL, "Bulacan",    psgc.LEVEL_PROVINCE),
        PR("0301499000", "Malolos", psgc.LEVEL_CITY),     # OLD code
    ]
    psgc.load_publication(conn, v1, "2018Q4", loaded_at="t1")
    old_sk = psgc.resolve_geo(conn, "2018Q4", "0301499000")

    # v2: NEW code, carrying the old one as its correspondence code.
    v2 = [
        PR(R_CL,  "Region III", psgc.LEVEL_REGION),
        PR(P_BUL, "Bulacan",    psgc.LEVEL_PROVINCE),
        PR(C_MAL, "Malolos", psgc.LEVEL_CITY, correspondence_code="0301499000"),
    ]
    stats = psgc.load_publication(conn, v2, "2020Q1", loaded_at="t2")
    assert stats["correspondence"] == 1
    new_sk = psgc.resolve_geo(conn, "2020Q1", C_MAL)
    assert new_sk == old_sk                      # same place, bridged by corr code
    # canonical view now reflects the new code
    assert psgc.current_code(conn, new_sk) == C_MAL


def test_name_parent_bridges_pure_recode():
    conn = _conn()
    v1 = [
        PR(R_CL,  "Region III", psgc.LEVEL_REGION),
        PR(P_BUL, "Bulacan",    psgc.LEVEL_PROVINCE),
        PR(C_MAL, "Malolos",    psgc.LEVEL_CITY),
        PR(B_MAL1, "Santo Niño", psgc.LEVEL_BARANGAY),
    ]
    psgc.load_publication(conn, v1, "2023Q4", loaded_at="t1")
    old_sk = psgc.resolve_geo(conn, "2023Q4", B_MAL1)

    # v2: the barangay is recoded (no correspondence code), same name/parent.
    v2 = [
        PR(R_CL,  "Region III", psgc.LEVEL_REGION),
        PR(P_BUL, "Bulacan",    psgc.LEVEL_PROVINCE),
        PR(C_MAL, "Malolos",    psgc.LEVEL_CITY),
        PR("0301401007", "Sto. Nino", psgc.LEVEL_BARANGAY),   # new code, fuzzy name
    ]
    stats = psgc.load_publication(conn, v2, "2024Q4", loaded_at="t2")
    assert stats["name_parent"] == 1
    assert psgc.resolve_geo(conn, "2024Q4", "0301401007") == old_sk


def test_new_place_gets_fresh_sk():
    conn = _conn()
    psgc.load_publication(conn, _base_rows(), "2023Q4", loaded_at="t1")
    n_before = conn.execute("SELECT COUNT(*) FROM dim_geo").fetchone()[0]

    v2 = _base_rows() + [PR("0301401009", "New Barangay", psgc.LEVEL_BARANGAY)]
    stats = psgc.load_publication(conn, v2, "2024Q4", loaded_at="t2")
    assert stats["new"] == 1
    n_after = conn.execute("SELECT COUNT(*) FROM dim_geo").fetchone()[0]
    assert n_after == n_before + 1


# ---------------------------------------------------------------------------
# public API + housekeeping
# ---------------------------------------------------------------------------
def test_resolve_geo_unknown_and_wrong_vintage():
    conn = _conn()
    psgc.load_publication(conn, _base_rows(), "2024Q4", loaded_at="t")
    assert psgc.resolve_geo(conn, "2024Q4", "9999999999") is None   # unknown code
    assert psgc.resolve_geo(conn, "1999Q1", C_MAL) is None          # unloaded vintage
    assert psgc.resolve_geo(conn, "2024Q4", None) is None


def test_resolve_any_vintage_prefers_latest():
    conn = _conn()
    psgc.load_publication(conn, _base_rows(), "2023Q4", loaded_at="t1")
    psgc.load_publication(conn, _base_rows(), "2024Q4", loaded_at="t2")
    sk = psgc.resolve_geo_any_vintage(conn, C_MAL)
    assert sk == psgc.resolve_geo(conn, "2024Q4", C_MAL)


def test_reload_same_vintage_is_idempotent():
    conn = _conn()
    psgc.load_publication(conn, _base_rows(), "2024Q4", loaded_at="t1")
    geo1 = conn.execute("SELECT COUNT(*) FROM dim_geo").fetchone()[0]
    xw1 = conn.execute("SELECT COUNT(*) FROM dim_psgc_crosswalk").fetchone()[0]

    psgc.load_publication(conn, _base_rows(), "2024Q4", loaded_at="t2")   # reload
    geo2 = conn.execute("SELECT COUNT(*) FROM dim_geo").fetchone()[0]
    xw2 = conn.execute("SELECT COUNT(*) FROM dim_psgc_crosswalk").fetchone()[0]
    assert (geo1, xw1) == (geo2, xw2)     # no duplication
    # vintage registry updated in place, single row
    assert conn.execute("SELECT COUNT(*) FROM psgc_vintage").fetchone()[0] == 1


def test_place_absent_from_newest_vintage_goes_inactive():
    conn = _conn()
    psgc.load_publication(conn, _base_rows(), "2023Q4", loaded_at="t1")
    sk_gone = psgc.resolve_geo(conn, "2023Q4", B_MAL2)

    # newer vintage drops B_MAL2
    v2 = [r for r in _base_rows() if r.code != B_MAL2]
    psgc.load_publication(conn, v2, "2024Q4", loaded_at="t2")
    assert psgc.geo_row(conn, sk_gone)["active"] == 0
    # a place still present stays active
    assert psgc.geo_row(conn, psgc.resolve_geo(conn, "2024Q4", C_MAL))["active"] == 1
    # …but the 2023Q4 crosswalk row for the dropped place is still resolvable
    assert psgc.resolve_geo(conn, "2023Q4", B_MAL2) == sk_gone


def test_older_reload_does_not_deactivate_current_places():
    conn = _conn()
    psgc.load_publication(conn, _base_rows(), "2024Q4", loaded_at="t2")
    # now (re)load an OLDER vintage that lacks NCR entirely
    v_old = [r for r in _base_rows() if not r.code.startswith("13")]
    psgc.load_publication(conn, v_old, "2020Q1", loaded_at="t1")
    # NCR places, present only in the newer 2024Q4, must remain active
    assert psgc.geo_row(conn, psgc.resolve_geo(conn, "2024Q4", C_QC))["active"] == 1


# ---------------------------------------------------------------------------
# file parser (fuzzy header detection)
# ---------------------------------------------------------------------------
def test_read_publication_csv(tmp_path):
    pytest.importorskip("pandas")
    csv = tmp_path / "psgc.csv"
    csv.write_text(
        "10-digit PSGC Code,Name,Geographic Level,Correspondence Code\n"
        f"{R_CL},Region III,Reg,\n"
        f"{P_BUL},Bulacan,Prov,\n"
        f"{C_MAL},City of Malolos,City,0301499000\n"
    )
    rows = psgc.read_publication(str(csv))
    assert len(rows) == 3
    assert rows[0].code == R_CL and rows[0].level == psgc.LEVEL_REGION
    assert rows[2].correspondence_code == "0301499000"

    conn = _conn()
    stats = psgc.load_publication(conn, rows, "2024Q4", loaded_at="t")
    assert stats["total"] == 3
    assert psgc.resolve_geo(conn, "2024Q4", C_MAL) is not None


def test_read_publication_missing_code_column(tmp_path):
    pytest.importorskip("pandas")
    csv = tmp_path / "bad.csv"
    csv.write_text("Foo,Bar\n1,2\n")
    with pytest.raises(ValueError):
        psgc.read_publication(str(csv))
