"""
UX Insights (/admin/ux-insights) — the ranked digest view over passive UX
telemetry (docs/UX_TELEMETRY_HANDOFF_PLAN.md step 5).

Covers: admin-only RBAC (via the existing /admin-prefix cap, no new gating
code), empty-state rendering, a seeded friction hotspot actually showing up
ranked, and the retention-window settings form (valid save + validation reject).
"""
import storage as st
import tzutil as tz


def _reset(conn):
    conn.execute("DELETE FROM ui_event")
    conn.execute("DELETE FROM spot_feedback")
    conn.execute("DELETE FROM feedback_update")
    # Actually remove the row (not set_setting(..., None), which would leave a
    # row with a NULL value — get_setting then returns None instead of falling
    # back to its default, since it only falls back when no row exists at all).
    conn.execute("DELETE FROM app_setting WHERE key='ui_telemetry_retention_days'")
    conn.commit()


def test_ux_insights_admin_only(admin, viewer, manager, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    assert admin.get("/admin/ux-insights").status_code == 200
    assert viewer.get("/admin/ux-insights").status_code == 403
    assert manager.get("/admin/ux-insights").status_code == 403


def test_ux_insights_empty_state(admin, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    body = admin.get("/admin/ux-insights").text
    assert "UX Insights" in body
    assert "No repeated friction spotted" in body


def test_ux_insights_shows_ranked_hotspot(admin, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        st.create_ui_events(conn, [
            {"user_id": 1, "role": "viewer", "session_id": "s1", "event_type": "rage_click",
             "route": "/directory/person/{id}/edit", "component": "save-btn",
             "element_selector": None, "element_text": "Save", "meta": None},
            {"user_id": 2, "role": "viewer", "session_id": "s2", "event_type": "rage_click",
             "route": "/directory/person/{id}/edit", "component": "save-btn",
             "element_selector": None, "element_text": "Save", "meta": None},
        ])
    finally:
        conn.close()
    body = admin.get("/admin/ux-insights").text
    assert "/directory/person/{id}/edit" in body
    assert "save-btn" in body
    assert "rage-click" in body


def test_ux_insights_window_param_clamped(admin, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    r = admin.get("/admin/ux-insights?days=99999")
    assert r.status_code == 200   # clamped server-side, never errors


# ---- retention settings form --------------------------------------------------

def test_ux_insights_retention_save_valid(admin, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        r = admin.post("/admin/ux-insights/retention", data={"retention_days": "45"},
                       follow_redirects=False)
        assert r.status_code == 303
        assert st.get_setting(conn, "ui_telemetry_retention_days") == "45"
    finally:
        _reset(conn); conn.close()


def test_ux_insights_retention_rejects_out_of_range(admin, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        r = admin.post("/admin/ux-insights/retention", data={"retention_days": "1"},
                       follow_redirects=False)
        assert r.status_code == 303
        assert "err=" in r.headers["location"]
        assert st.get_setting(conn, "ui_telemetry_retention_days") is None
    finally:
        _reset(conn); conn.close()


def test_ux_insights_retention_requires_admin(viewer, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    r = viewer.post("/admin/ux-insights/retention", data={"retention_days": "45"})
    assert r.status_code == 403
