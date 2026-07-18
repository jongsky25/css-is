"""
UX Insights (/admin/ux-insights) — the ranked digest view over passive UX
telemetry (docs/UX_TELEMETRY_HANDOFF_PLAN.md step 5), plus the downloadable
AI-analysis handoff export (/admin/ux-insights/handoff, ux_handoff.py).

Covers: admin-only RBAC (via the existing /admin-prefix cap, no new gating
code), empty-state rendering, a seeded friction hotspot actually showing up
ranked, the retention-window settings form (valid save + validation reject),
and the handoff export — RBAC, attachment headers, both formats, the audit
row, and the end-to-end sanitization leak test (raw digits POSTed through
/telemetry must never surface in the export).
"""
import json

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


# ---- the downloadable AI-analysis handoff -------------------------------------

def _seed_hotspot(conn):
    st.create_ui_events(conn, [
        {"user_id": 1, "role": "viewer", "session_id": "sess-raw-A", "event_type": "pageview",
         "route": "/monitor", "component": None, "element_selector": None,
         "element_text": None, "meta": None},
        {"user_id": 1, "role": "viewer", "session_id": "sess-raw-A", "event_type": "rage_click",
         "route": "/directory/person/{id}/edit", "component": "save-btn",
         "element_selector": None, "element_text": "Save", "meta": None},
        {"user_id": 2, "role": "viewer", "session_id": "sess-raw-B", "event_type": "rage_click",
         "route": "/directory/person/{id}/edit", "component": "save-btn",
         "element_selector": None, "element_text": "Save", "meta": None},
    ])


def test_handoff_requires_admin(admin, viewer, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    assert admin.get("/admin/ux-insights/handoff").status_code == 200
    assert viewer.get("/admin/ux-insights/handoff").status_code == 403


def test_handoff_markdown_attachment_with_seeded_data(admin, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _seed_hotspot(conn)
    finally:
        conn.close()
    r = admin.get("/admin/ux-insights/handoff?days=30")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    cd = r.headers["content-disposition"]
    assert cd.startswith('attachment; filename="UX_Handoff_30d_')
    assert cd.endswith('.md"')
    body = r.text
    assert "# CSS-IS UX Telemetry Handoff" in body
    assert "/directory/person/{id}/edit" in body      # the seeded hotspot
    assert "## 6. Feature usage & coverage" in body
    # session ids are pseudonymized, user ids dropped outright
    assert "sess-raw-A" not in body and "sess-raw-B" not in body
    assert '"session": "s1"' in body


def test_handoff_json_variant_parses(admin, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _seed_hotspot(conn)
    finally:
        conn.close()
    r = admin.get("/admin/ux-insights/handoff?days=30&fmt=json")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("application/json")
    assert r.headers["content-disposition"].endswith('.json"')
    payload = json.loads(r.text)
    assert payload["totals"]["events"] == 3
    assert payload["opportunities"][0]["route"] == "/directory/person/{id}/edit"
    # the route → handler map resolves against the real app routes
    assert payload["route_handlers"]["/monitor"] == "monitor_index"
    # feature usage covers nav destinations never visited in the window
    never = [d["route"] for d in payload["feature_usage"]["never_used"]]
    assert "/admin/backups" in never
    assert all("sess-raw" not in (e.get("session") or "")
               for e in payload["sample_events"])


def test_handoff_never_leaks_raw_input_end_to_end(admin, viewer, db_path):
    """Defense-in-depth, extended to the export path: a stale/hand-crafted
    client POSTs unmasked digits; the download must never contain them."""
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    r = viewer.post("/telemetry", json={"events": [
        {"event_type": "dead_click", "route": "/directory/person/482/edit",
         "session_id": "sess-raw-C",
         "element_text": "Call 09171234567 about client 90210"},
    ]})
    assert r.status_code == 204
    body = admin.get("/admin/ux-insights/handoff?days=7").text
    assert "09171234567" not in body
    assert "90210" not in body
    assert "/directory/person/482/edit" not in body
    assert "/directory/person/{id}/edit" in body
    assert "sess-raw-C" not in body


def test_handoff_days_clamped_and_bad_fmt_falls_back(admin, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    r = admin.get("/admin/ux-insights/handoff?days=99999&fmt=nonsense")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert 'filename="UX_Handoff_365d_' in r.headers["content-disposition"]


def test_handoff_writes_audit_row(admin, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    admin.get("/admin/ux-insights/handoff?days=30")
    conn = st.connect(db_path)
    try:
        row = conn.execute(
            "SELECT action, target_type, summary FROM audit_log "
            "ORDER BY id DESC LIMIT 1").fetchone()
    finally:
        conn.close()
    assert row[0] == "export"
    assert row[1] == "ui_event"
    assert "UX telemetry handoff" in row[2]
