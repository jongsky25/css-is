"""Regression: the per-activity SERVQUAL report must render even when a Form-2
dimension's expectation gap is None.

A partial / save-and-resume submission can answer the perception items (B*) without
the single expectation item (A). Then `gap = perception - expectation` is None for
every dimension, and `templates/activity.html` used to crash on `None > 0.005`
(TypeError), 500-ing the whole report at /reports/activities/<id>. The gap cell now
renders the neutral "—" instead.
"""
from datetime import timedelta

import storage as st


def test_activity_report_renders_with_none_expectation_gap(admin, app_mod):
    conn = st.connect(app_mod.DB)
    recent = (app_mod._today_local() - timedelta(days=3)).isoformat()
    fid = st.create_form_instance(conn, 2, "F2", recent, topic="None-Gap Activity QQ",
                                  created_by="me@x")
    # Perception items only across the event dimensions — NO expectation (A) item,
    # so every dimension's gap is None.
    st.record_response(conn, fid, [("B1", 6), ("B2", 6), ("B5", 6), ("B8", 6), ("B9", 6)])
    conn.commit(); conn.close()
    app_mod.invalidate_atoms()

    # build_events keys a single-form activity by that form id.
    r = admin.get(f"/reports/activities/{fid}")
    assert r.status_code == 200, "a None-gap dimension must not 500 the report"
    # It got past the dimension table (where the crash was) and shows the neutral gap.
    assert "Service quality, dimension by dimension" in r.text
    assert "—" in r.text
