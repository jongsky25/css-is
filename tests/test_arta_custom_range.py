"""
Type 1 (ARTA walk-in) custom date range -- 'range:START..END' period token on the
report/exports/verbatims, and From/To filtering on the walk-in entries manager.
"""
import pytest
from fastapi import HTTPException

import storage as st


def _stamp_type1(app_mod, stamps):
    """Give the first len(stamps) Type-1 responses exact submitted_at values."""
    conn = st.connect(app_mod.DB)
    ids = [r[0] for r in conn.execute(
        "SELECT r.id FROM response r JOIN form_instance fi ON fi.id = r.form_instance_id "
        "WHERE fi.survey_type = 1 ORDER BY r.id LIMIT ?", (len(stamps),))]
    assert len(ids) == len(stamps), "fixture needs enough Type-1 responses"
    for rid, ts in zip(ids, stamps):
        conn.execute("UPDATE response SET submitted_at=?, archived_at=NULL WHERE id=?", (ts, rid))
    conn.commit()
    conn.close()
    return ids


def test_period_from_dates_validation(app_mod):
    f = app_mod._period_from_dates
    assert f("2026-10-22", "2026-10-28") == "range:2026-10-22..2026-10-28"
    assert f("2026-10-22", "") == "range:2026-10-22..2026-10-22"      # one date = that day
    assert f("", "2026-10-22") == "range:2026-10-22..2026-10-22"
    assert f("", "") == ""
    for bad in (("2026-10-28", "2026-10-22"), ("2026-02-30", "2026-03-01"),
                ("2026-1-5", "2026-10-22"), ("2025-01-01", "2026-12-31")):
        with pytest.raises(HTTPException) as exc:
            f(*bad)
        assert exc.value.status_code == 400
    assert f("2026-01-01", "2026-12-31")                               # 365 days is fine


def test_range_token_only_for_walkin(app_mod):
    assert app_mod._report_period("range:2026-10-22..2026-10-22", allow_range=True) \
        == "range:2026-10-22..2026-10-22"
    assert app_mod._period_date_range("range:2026-10-22..2026-10-28") == ("2026-10-22", "2026-10-28")
    assert app_mod._parse_period("range:2026-10-22..2026-10-28") == (None, None)
    with pytest.raises(HTTPException):
        app_mod._report_period("range:2026-10-22..2026-10-22")           # Types 2/3 refuse it
    with pytest.raises(HTTPException):
        app_mod._report_period("range:2026-10-28..2026-10-22", allow_range=True)


def test_single_day_includes_whole_day_and_excludes_neighbours(app_mod):
    ids = _stamp_type1(app_mod, ["2026-10-21 23:59:59", "2026-10-22 00:00:00",
                                 "2026-10-22T23:59:59.999", "2026-10-23 00:00:00"])
    conn = st.connect(app_mod.DB)
    try:
        rows, total = st.walkin_entries_page(conn, date_from="2026-10-22", date_to="2026-10-22")
        assert {r["id"] for r in rows} == {ids[1], ids[2]} and total == 2
        _, wide = st.walkin_entries_page(conn, date_from="2026-10-21", date_to="2026-10-23")
        assert wide == 4
        got = app_mod._csm_type1_response_ids(conn, "2026-10-22", "2026-10-22")
        assert set(got) == {ids[1], ids[2]}
    finally:
        conn.close()


def test_entries_page_filters_and_keeps_filter_across_toggles(admin, app_mod):
    _stamp_type1(app_mod, ["2026-10-22 10:00:00", "2026-10-22 11:00:00", "2026-09-01 09:00:00"])
    page = admin.get("/arta/entries?date_from=2026-10-22&date_to=2026-10-22")
    assert page.status_code == 200
    assert "2 entries from" in page.text
    assert "Today" in page.text and "Last 7 days" in page.text
    assert admin.get("/arta/entries?date_from=2026-10-28&date_to=2026-10-22").status_code == 400
    assert admin.get("/arta/entries?date_from=nonsense").status_code == 400


def test_report_and_exports_follow_the_range(admin, app_mod):
    _stamp_type1(app_mod, ["2026-10-22 10:00:00", "2026-10-22 11:00:00", "2026-09-01 09:00:00"])
    rep = admin.get("/reports?type=1&date_from=2026-10-22&date_to=2026-10-22")
    assert rep.status_code == 200
    assert "2026-10-22 (inclusive)" in rep.text or "2026-10-22 to 2026-10-22" in rep.text
    assert 'name="date_from"' in rep.text and 'value="2026-10-22"' in rep.text
    # the same token drives the downloads and the comment drill-down
    tok = "range:2026-10-22..2026-10-22"
    assert admin.get(f"/csm-blhsd/export?period={tok}").status_code == 200
    assert admin.get(f"/reports/verbatims?survey_type=1&period={tok}").status_code == 200
    assert admin.get(f"/reports/export?type=1&period={tok}&fmt=docx").status_code == 200


def test_range_rejected_for_activity_and_rp_reports(admin):
    tok = "range:2026-10-22..2026-10-22"
    for typ in (2, 3):
        r = admin.get(f"/reports?type={typ}&period={tok}")
        assert r.status_code == 400
        assert admin.get(f"/reports/export?type={typ}&period={tok}&fmt=docx").status_code == 400
    # a stray date range on a non-walk-in report is ignored, not applied
    assert admin.get("/reports?type=2&date_from=2026-10-22&date_to=2026-10-22").status_code == 200
