"""Per-activity SERVQUAL report builders (pure logic, no DB)."""
import pandas as pd
import dashboard_insights as di

_ITEMS = ["A", "B1", "B2", "B3", "B4", "B5", "B6", "B7", "B8", "B9", "C"]


def _answers(fi_id, rid, org_path, date, value, *, osq=4.0, exp=6.0):
    """One respondent's full Form-2 answer set as atom rows."""
    rows = []
    for it in _ITEMS:
        v = exp if it == "A" else (osq if it == "C" else value)
        rows.append({"form_instance_id": fi_id, "response_id": rid, "survey_type": 2,
                     "is_na": False, "org_path": org_path, "event_date": date,
                     "item_id": it, "value": float(v)})
    return rows


def _atoms(*record_groups):
    rows = []
    for g in record_groups:
        rows.extend(g)
    return pd.DataFrame(rows)


def test_activity_benchmark_section_year_cohort():
    # This activity (fi 100) vs two OTHER activities the same section ran the same
    # year (fi 101, 102). A different section (fi 200) and a different year (fi 103)
    # must NOT count toward the cohort.
    atoms = _atoms(
        _answers(100, 1, "BLHSD/HSDD/S1", "2026-03-01", 6.6),   # the activity itself
        _answers(101, 2, "BLHSD/HSDD/S1", "2026-05-01", 6.0),   # peer, same section+year
        _answers(102, 3, "BLHSD/HSDD/S1", "2026-08-01", 6.0),   # peer, same section+year
        _answers(200, 4, "BLHSD/HSDD/S2", "2026-04-01", 5.0),   # other section — excluded
        _answers(103, 5, "BLHSD/HSDD/S1", "2025-04-01", 5.0),   # other year — excluded
    )
    b = di.activity_benchmark(atoms, [100], "Section 1")
    assert b is not None
    assert b["label"] == "Section 1" and b["year"] == "2026"
    assert b["peers"] == 2                      # two distinct peer event dates
    assert b["respondents"] == 2                # two peer respondents (self excluded)
    # cohort means come only from the two same-section/same-year peers (both 6.0)
    assert abs(b["overall"]["mean"] - 6.0) < 1e-9
    assert all(abs(d["mean"] - 6.0) < 1e-9 for d in b["dims"].values())


def test_activity_benchmark_none_when_no_peers():
    # The only activity its section ran that year -> no cohort -> None.
    atoms = _atoms(_answers(100, 1, "BLHSD/HSDD/S1", "2026-03-01", 6.6))
    assert di.activity_benchmark(atoms, [100], "Section 1") is None


def test_activity_benchmark_empty_atoms():
    assert di.activity_benchmark(pd.DataFrame(), [100], "Section 1") is None


def test_servqual_verdict_thresholds():
    assert di._servqual_verdict(0.26) == "Exceeds Expectation"
    assert di._servqual_verdict(0.10) == "Exceeds Expectation"
    assert di._servqual_verdict(0.05) == "Meets Expectation"
    assert di._servqual_verdict(0.0) == "Meets Expectation"
    assert di._servqual_verdict(-0.05) == "Meets Expectation"
    assert di._servqual_verdict(-0.10) == "Below Expectation"
    assert di._servqual_verdict(None) is None


def test_demographics_captured_only():
    d = di.activity_demographics({"male": 14, "female": 17, "doh": 24, "nondoh": 7}, {})
    assert d["mf_ratio"] == "14:17"
    assert d["affil_ratio"] == "24:7"
    assert d["manual"] is False
    # percentages are proportional within each pair
    assert round(d["female_pct"]) == round(17 / 31 * 100)


def test_demographics_manual_overrides_captured_per_field():
    # A manual value present for a field wins; blank manual falls back to captured.
    d = di.activity_demographics(
        {"male": 14, "female": 17, "doh": 24, "nondoh": 7},
        {"male": 40, "female": "", "doh": None, "nondoh": 10})
    assert d["male"] == 40 and d["female"] == 17      # female fell back to captured
    assert d["doh"] == 24 and d["nondoh"] == 10        # doh fell back, nondoh overridden
    assert d["manual"] is True


def test_demographics_empty_returns_none():
    assert di.activity_demographics({}, {}) is None
    assert di.activity_demographics({"male": 0, "female": 0, "doh": 0, "nondoh": 0}, {}) is None
