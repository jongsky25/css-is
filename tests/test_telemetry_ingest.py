"""
Passive UX telemetry — storage round-trip + POST /telemetry ingest
(docs/UX_TELEMETRY_HANDOFF_PLAN.md).

Covers: storage round-trip, login-gated ingest (the auth middleware 401s an
anonymous beacon before the handler ever runs), unknown event types dropped,
oversized batches capped, and server-side re-sanitization of a client that sends
raw (unmasked) text — the defense-in-depth the doc calls out as the single most
important thing a naive port could get wrong.
"""
import storage as st


def _reset(conn):
    conn.execute("DELETE FROM ui_event")
    conn.commit()


# ---- storage round-trip ------------------------------------------------------

def test_storage_roundtrip(db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        st.create_ui_events(conn, [
            {"user_id": 1, "role": "viewer", "session_id": "s1", "event_type": "pageview",
             "route": "/dashboard", "component": None, "element_selector": None,
             "element_text": None, "meta": {"from": "/login"}},
            {"user_id": 1, "role": "viewer", "session_id": "s1", "event_type": "dead_click",
             "route": "/dashboard", "component": "stats", "element_selector": "div.card",
             "element_text": "Total", "meta": None},
        ])
        rows = st.list_ui_events(conn)
        assert len(rows) == 2
        assert rows[0]["event_type"] == "dead_click"      # newest first
        assert rows[0]["component"] == "stats"
        assert rows[1]["meta"] == {"from": "/login"}
    finally:
        _reset(conn); conn.close()


def test_create_ui_events_noop_on_empty_batch(db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        st.create_ui_events(conn, [])
        assert st.list_ui_events(conn) == []
    finally:
        conn.close()


# ---- POST /telemetry ----------------------------------------------------------

def test_telemetry_requires_login(client, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn); conn.close()
    r = client.post("/telemetry", json={"events": [
        {"event_type": "pageview", "route": "/dashboard", "session_id": "s1"},
    ]})
    assert r.status_code == 401
    conn = st.connect(db_path)
    assert st.list_ui_events(conn) == []
    conn.close()


def test_telemetry_accepts_batch_when_signed_in(viewer, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        r = viewer.post("/telemetry", json={"events": [
            {"event_type": "pageview", "route": "/dashboard", "session_id": "s1"},
            {"event_type": "dead_click", "route": "/dashboard", "session_id": "s1",
             "component": "stats", "element_selector": "div.card", "element_text": "Total"},
        ]})
        assert r.status_code == 204
        rows = st.list_ui_events(conn)
        assert len(rows) == 2
        assert all(r["role"] == "viewer" for r in rows)
    finally:
        _reset(conn); conn.close()


def test_telemetry_drops_unknown_event_types(viewer, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        r = viewer.post("/telemetry", json={"events": [
            {"event_type": "not_a_real_type", "route": "/dashboard", "session_id": "s1"},
        ]})
        assert r.status_code == 204
        assert st.list_ui_events(conn) == []
    finally:
        _reset(conn); conn.close()


def test_telemetry_caps_oversized_batch(viewer, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        events = [{"event_type": "pageview", "route": "/x", "session_id": "s1"}
                  for _ in range(200)]
        r = viewer.post("/telemetry", json={"events": events})
        assert r.status_code == 204
        assert len(st.list_ui_events(conn)) == 50   # ui_telemetry.MAX_BATCH
    finally:
        _reset(conn); conn.close()


def test_telemetry_resanitizes_raw_route_and_text_server_side(viewer, db_path):
    """The client is supposed to mask before sending, but the server must never
    trust that alone — a stale script or a hand-crafted POST should still land
    sanitized."""
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        r = viewer.post("/telemetry", json={"events": [
            {"event_type": "dead_click", "route": "/directory/person/482/edit",
             "session_id": "s1", "element_text": "Call 09171234567 about client 90210"},
        ]})
        assert r.status_code == 204
        row = st.list_ui_events(conn)[0]
        assert row["route"] == "/directory/person/{id}/edit"
        assert "###" in row["element_text"]
        assert "09171234567" not in row["element_text"]
        assert "90210" not in row["element_text"]
    finally:
        _reset(conn); conn.close()


def test_telemetry_form_abandon_keeps_field_count_only(viewer, db_path):
    """form_abandon's meta carries a touched-field COUNT (clamped int); any
    other meta keys a client might sneak in are dropped by the server-side
    meta cleaner."""
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        r = viewer.post("/telemetry", json={"events": [
            {"event_type": "form_abandon", "route": "/create", "session_id": "s1",
             "element_selector": "form#createForm",
             "meta": {"fields": 4, "values": "should never persist"}},
            {"event_type": "form_abandon", "route": "/create", "session_id": "s1",
             "meta": {"fields": 99999}},
        ]})
        assert r.status_code == 204
        rows = st.list_ui_events(conn)
        assert len(rows) == 2
        assert rows[1]["meta"] == {"fields": 4}       # newest first; oldest last
        assert rows[0]["meta"] == {"fields": 500}     # clamped
    finally:
        _reset(conn); conn.close()


def test_telemetry_ignores_malformed_body(viewer, db_path):
    conn = st.connect(db_path); st.init_db(conn); _reset(conn)
    try:
        r = viewer.post("/telemetry", content=b"not json",
                        headers={"Content-Type": "application/json"})
        assert r.status_code == 204
        assert st.list_ui_events(conn) == []
    finally:
        conn.close()
