"""
Official ARTA / CO-CSM report builder (`_arta_official_report`) + the period→date
window helper. Pure aggregation over BLHSD-format rows — same source as the Excel
extract, so on-screen report and download stay in lock-step.
"""
import app


def _row(**kw):
    base = {f"SQD{i}": "" for i in range(9)}
    base.update({"CC1": "", "CC2": "", "CC3": "", "SEX": "", "AGE": "0",
                 "REGION": "", "CLIENT_TYPE": "", "SERVICE": "", "ONSITE_ONLINE": "",
                 "SUGGESTIONS": "", "FEEDBACK_TYPE": ""})
    base.update(kw)
    return base


def test_period_date_range():
    assert app._period_date_range("all") == (None, None)
    assert app._period_date_range("") == (None, None)
    assert app._period_date_range("year:2026") == ("2026-01-01", "2026-12-31")
    assert app._period_date_range("quarter:2026-Q1") == ("2026-01-01", "2026-03-31")
    assert app._period_date_range("quarter:2026-Q4") == ("2026-10-01", "2026-12-31")
    assert app._period_date_range("semester:2026-H1") == ("2026-01-01", "2026-06-30")
    assert app._period_date_range("semester:2026-H2") == ("2026-07-01", "2026-12-31")


def test_empty_rows():
    rep = app._arta_official_report([])
    assert rep == {"has_data": False, "respondents": 0}


def test_na_is_excluded_from_topbox():
    # SQD1 value 0 == N/A in the row, must not count toward n or top-box.
    rows = [_row(SQD1=5), _row(SQD1=0), _row(SQD1=2)]
    rep = app._arta_official_report(rows)
    sqd1 = next(d for d in rep["sqd"] if d["item"] == "SQD1")
    assert sqd1["n"] == 2          # the two real answers
    assert sqd1["na"] == 1         # the 0
    assert sqd1["score"] == 50.0   # one of two is top-box


def test_overall_is_pooled_topbox_over_sqd1_8():
    # SQD0 excluded from the overall headline; SQD1-8 pooled.
    rows = [_row(**{f"SQD{i}": 5 for i in range(9)}),
            _row(**{f"SQD{i}": 3 for i in range(9)})]
    rep = app._arta_official_report(rows)
    # 8 top-box of 16 SQD1-8 answers = 50%
    assert rep["overall"] == 50.0
    assert rep["overall_band"] == "Poor"
    assert rep["respondents"] == 2


def test_cc_lists_all_options_even_at_zero():
    rows = [_row(CC1=app.CSM_CC1_OPTS[0])]
    rep = app._arta_official_report(rows)
    assert len(rep["cc1"]) == len(app.CSM_CC1_OPTS)
    assert rep["cc1"][0]["n"] == 1 and rep["cc1"][0]["pct"] == 100.0
    assert all(c["n"] == 0 for c in rep["cc1"][1:])


def test_cc_matches_canonical_option_despite_smart_apostrophe():
    # Real data stores a curly apostrophe; the option constant uses a straight one.
    stored = app.CSM_CC1_OPTS[0].replace("'", "’")
    rows = [_row(CC1=stored), _row(CC1=stored)]
    cc1 = app._arta_official_report(rows)["cc1"]
    assert len(cc1) == len(app.CSM_CC1_OPTS)        # no duplicate "extra" row
    assert cc1[0]["label"] == app.CSM_CC1_OPTS[0]   # canonical label kept
    assert cc1[0]["n"] == 2


def test_cc_summary_headline_and_base():
    # CC1 awareness: opts 0-2 are "aware", opt 3 is "not aware"; blank excluded.
    rows = [_row(CC1=app.CSM_CC1_OPTS[0]), _row(CC1=app.CSM_CC1_OPTS[2]),
            _row(CC1=app.CSM_CC1_OPTS[3]), _row(CC1="")]
    rep = app._arta_official_report(rows)
    cc1 = rep["cc"]["cc1"]
    assert cc1["base"] == 3            # blank excluded
    assert cc1["pos_n"] == 2           # the two "aware" options
    assert cc1["pct"] == round(2 / 3 * 100, 1)
    assert cc1["top"]["short"] == "Aware — saw it here"


def test_cc_visibility_excludes_not_applicable_from_base():
    # CC2 "Not applicable" must drop out of the positive base.
    rows = [_row(CC2=app.CSM_CC2_OPTS[0]),   # Easy to see (positive)
            _row(CC2=app.CSM_CC2_OPTS[2]),   # Difficult (counts in base, not positive)
            _row(CC2=app.CSM_CC2_OPTS[4])]   # Not applicable (excluded)
    cc2 = app._arta_official_report(rows)["cc"]["cc2"]
    assert cc2["base"] == 2
    assert cc2["pos_n"] == 1
    assert cc2["pct"] == 50.0


def test_demographics_and_age_bands():
    rows = [_row(SEX="Male", AGE="25"), _row(SEX="Female", AGE="0"),
            _row(SEX="Male", AGE="70")]
    rep = app._arta_official_report(rows)
    sex = {d["label"]: d["n"] for d in rep["demo"]["sex"]}
    assert sex == {"Male": 2, "Female": 1}
    age = {d["label"]: d["n"] for d in rep["demo"]["age"]}
    assert age == {"20–34": 1, "Did not specify": 1, "65 & above": 1}


def test_comments_split_by_feedback_type():
    rows = [_row(SUGGESTIONS="good", FEEDBACK_TYPE="Positive"),
            _row(SUGGESTIONS="slow", FEEDBACK_TYPE="Negative"),
            _row(SUGGESTIONS="ok", FEEDBACK_TYPE=""),
            _row(SUGGESTIONS="", FEEDBACK_TYPE="Positive")]  # blank text dropped
    c = app._arta_official_report(rows)["comments"]
    assert c["total"] == 3
    assert [x["text"] for x in c["positive"]] == ["good"]
    assert [x["text"] for x in c["negative"]] == ["slow"]
    assert [x["text"] for x in c["other"]] == ["ok"]
