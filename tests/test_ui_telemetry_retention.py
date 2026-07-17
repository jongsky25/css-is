"""
Passive UX telemetry — retention purge (docs/UX_TELEMETRY_HANDOFF_PLAN.md step 6).

ui_event is behavioral data, not audit-of-record like attendee PII (see
retention.py's module docstring for why the two jobs are unrelated beyond
sharing a "purge past cutoff" shape) — no consent record kept, no audit_log
entry. Covers: the storage-level delete, the retention.py CLI-callable job
(explicit --days, the ui_telemetry_retention_days app_setting default, and
--dry-run), and that attendee retention is untouched by any of this.
"""
import retention
import storage as st


def _reset(conn):
    conn.execute("DELETE FROM ui_event")
    conn.commit()


def _seed(conn, *, old_ts, new_ts):
    st.create_ui_events(conn, [
        {"user_id": 1, "role": "viewer", "session_id": "s1", "event_type": "pageview",
         "route": "/old", "component": None, "element_selector": None,
         "element_text": None, "meta": None},
    ])
    conn.execute("UPDATE ui_event SET created_at=? WHERE route='/old'", (old_ts,))
    st.create_ui_events(conn, [
        {"user_id": 1, "role": "viewer", "session_id": "s1", "event_type": "pageview",
         "route": "/new", "component": None, "element_selector": None,
         "element_text": None, "meta": None},
    ])
    conn.execute("UPDATE ui_event SET created_at=? WHERE route='/new'", (new_ts,))
    conn.commit()


def test_storage_purge_stale_ui_events(db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _seed(conn, old_ts="2020-01-01T00:00:00", new_ts="2026-07-01T00:00:00")
        n = st.purge_stale_ui_events(conn, "2025-01-01T00:00:00")
        assert n == 1
        routes = {r["route"] for r in st.list_ui_events(conn)}
        assert routes == {"/new"}
    finally:
        _reset(conn); conn.close()


def test_retention_purge_stale_ui_events_explicit_days(db_path):
    import tzutil as tz
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        # "old" well past 30 days, "new" just now.
        _seed(conn, old_ts="2020-01-01T00:00:00", new_ts=tz.now_iso())
        n = retention.purge_stale_ui_events(db_path=db_path, days=30)
        assert n == 1
        assert {r["route"] for r in st.list_ui_events(conn)} == {"/new"}
    finally:
        _reset(conn); conn.close()


def test_retention_purge_stale_ui_events_uses_app_setting_default(db_path):
    import tzutil as tz
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        st.set_setting(conn, "ui_telemetry_retention_days", "7")
        _seed(conn, old_ts="2020-01-01T00:00:00", new_ts=tz.now_iso())
        n = retention.purge_stale_ui_events(db_path=db_path)   # no explicit days -> reads the setting
        assert n == 1
        assert {r["route"] for r in st.list_ui_events(conn)} == {"/new"}
    finally:
        st.set_setting(conn, "ui_telemetry_retention_days", None)
        _reset(conn); conn.close()


def test_retention_purge_stale_ui_events_dry_run_changes_nothing(db_path):
    import tzutil as tz
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        _seed(conn, old_ts="2020-01-01T00:00:00", new_ts=tz.now_iso())
        n = retention.purge_stale_ui_events(db_path=db_path, days=30, dry_run=True)
        assert n == 1
        assert len(st.list_ui_events(conn)) == 2   # nothing actually deleted
    finally:
        _reset(conn); conn.close()


def test_retention_ui_events_purge_does_not_touch_attendee_pii(db_path):
    """The two retention jobs are independent — running the ui_event purge must
    never touch attendee rows (and vice versa is already covered by
    test_event_e.py::test_retention_purge)."""
    import tzutil as tz
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        before = conn.execute("SELECT COUNT(*) FROM attendee").fetchone()[0]
        _seed(conn, old_ts="2020-01-01T00:00:00", new_ts=tz.now_iso())
        retention.purge_stale_ui_events(db_path=db_path, days=30)
        after = conn.execute("SELECT COUNT(*) FROM attendee").fetchone()[0]
        assert before == after
    finally:
        _reset(conn); conn.close()
