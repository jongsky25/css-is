"""Feedback #53 — per-activity verbatims on the Resource-person (Type-3) report.

An invited/outside activity is Form-3-only, so it has no per-activity SERVQUAL page to
carry its comments. When the Type-3 report is narrowed to one activity it must show
THAT activity's verbatims inline, and its "See this activity's verbatims" drill-down
must stay scoped to it — before this, an invited activity's comments were reachable
nowhere per-activity.
"""
from datetime import timedelta

import storage as st


def _invited_with_comment(app_mod, topic, comment, org="Partner Org C53"):
    """Create an invited/outside Form-3 activity with one SCORED speaker (B-items feed
    DIM_MAP_FORM3, so it lands in the RP report's Activity options) plus an overall
    remark — the verbatim we expect to surface. Returns its build_events id (= the
    single form id), which is exactly the Type-3 Activity filter value."""
    conn = st.connect(app_mod.DB)
    ext_id = conn.execute(
        "INSERT INTO external_organizer(name) VALUES (?)", (org,)).lastrowid
    date = (app_mod._today_local() - timedelta(days=5)).isoformat()
    fid = st.create_form_instance(conn, 3, "F3", date, topic=topic,
                                  organizer_external_id=ext_id, venue="Hall C53",
                                  created_by="mgr@x")
    st.record_response(conn, fid, [("B1", 6), ("B6", 6)], remarks=comment)
    conn.commit(); conn.close()
    app_mod.invalidate_atoms()
    return fid


def test_type3_report_shows_activity_verbatims_inline(manager, app_mod):
    comment = "The facilitator was outstanding and very clear"
    fid = _invited_with_comment(app_mod, "Invited Verbatim ZZZ", comment)
    html = manager.get(f"/reports?type=3&activity={fid}").text
    assert "In people's own words" in html, "the per-activity comment digest must render inline"
    assert comment in html, "the activity's own verbatim must appear on the report"
    # The drill-down link is scoped to this activity, not the all-RP roll-up.
    # (apostrophe is HTML-escaped in the rendered link text, so match around it)
    assert "See this activity" in html
    assert f"/reports/verbatims" in html and f"activity={fid}" in html


def test_type3_verbatims_page_scoped_to_activity(manager, app_mod):
    mine = "Loved this invited session, thank you"
    other = "A different unrelated session comment"
    fid = _invited_with_comment(app_mod, "Scoped Verbatim AAA", mine, org="Org AAA")
    _invited_with_comment(app_mod, "Other Verbatim BBB", other, org="Org BBB")
    html = manager.get(f"/reports/verbatims?survey_type=3&activity={fid}").text
    assert mine in html, "the scoped verbatims page must show this activity's comment"
    assert other not in html, "another activity's comment must NOT leak into the scoped page"


def test_type3_unmatched_activity_is_empty_not_bureau_wide(manager, app_mod):
    """Feedback #51 guard: a specific activity id that isn't an RP option must yield an
    empty, labelled report — never a silent fall-back to the whole bureau."""
    _invited_with_comment(app_mod, "Real Activity", "Some real comment", org="Org REAL")
    html = manager.get("/reports?type=3&activity=99999999").text
    assert "No responses in this scope." in html
    assert "Some real comment" not in html
