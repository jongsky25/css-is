"""Spot Feedback #27 — make the audit log readable + show its shape.

storage gains plain-language labels for every audit action code (with a graceful
fallback for unmapped/new codes) and an `audit_breakdown` that ranks the recent
action types + busiest people. The audit page renders the friendly labels and a
"What's been happening" panel. (Builds on v1.60's at-a-glance counts.)
"""
from datetime import timedelta
import storage as st
import tzutil as tz


def _fresh(tmp_path):
    conn = st.connect(str(tmp_path / "audit.db"))
    st.init_db(conn)
    conn.execute("PRAGMA foreign_keys = OFF")
    return conn


def _row(conn, actor, action, ts):
    conn.execute("INSERT INTO audit_log(ts, actor, action, prev_hash, row_hash) "
                 "VALUES (?,?,?,'x','y')", (ts, actor, action))


def test_audit_label_known_and_fallback():
    assert st.audit_label("login") == "Signed in"
    assert st.audit_label("spot_feedback_triage") == "Updated feedback status"
    # Unknown / future code → humanized, never blank.
    assert st.audit_label("event_brand_new_thing") == "Event brand new thing"
    assert st.audit_label("") == "—"


def test_audit_category():
    assert st.audit_category("login") == "Sign-in"
    assert st.audit_category("backup_run") == "Data & backups"
    assert st.audit_category("totally_unmapped") == "Other"


def test_audit_breakdown_ranks_types_and_actors(tmp_path):
    conn = _fresh(tmp_path)
    now = tz.now_local()
    def stamp(**kw):
        return (now - timedelta(**kw)).isoformat(timespec="seconds")

    for _ in range(4):
        _row(conn, "alice", "export", stamp(hours=1))     # 4 exports
    for _ in range(2):
        _row(conn, "bob", "login", stamp(hours=2))        # 2 logins
    _row(conn, "carol", "edit_remark", stamp(days=2))     # 1 comment edit
    _row(conn, "carol", "login", stamp(days=20))          # outside the 7-day window
    conn.commit()

    b = st.audit_breakdown(conn, days=7)
    assert b is not None
    # Types ranked by count, carrying friendly labels.
    kinds = [(t["label"], t["n"]) for t in b["by_type"]]
    assert kinds[0] == ("Exported data", 4)
    assert ("Signed in", 2) in kinds
    assert ("Edited a comment", 1) in kinds
    assert b["by_type"][0]["pct"] == 100             # top bar is full
    # Busiest people: alice (4) ahead of bob (2).
    assert b["by_actor"][0] == {"who": "alice", "n": 4}
    assert {"who": "bob", "n": 2} in b["by_actor"]


def test_audit_breakdown_empty(tmp_path):
    assert st.audit_breakdown(_fresh(tmp_path)) is None


def test_audit_page_shows_friendly_labels(admin):
    from tests.conftest import PW
    signed_in = admin.post("/login", data={"username": "admin@test.local", "password": PW},
                           follow_redirects=False)
    assert signed_in.status_code == 303
    body = admin.get("/admin/audit").text
    assert "Signed in" in body                        # friendly label rendered (admin just logged in)
    # The insights aggregator exposes the label key the template uses.
    import storage as st, app as A
    conn = st.connect(A.DB)
    try:
        ins = st.audit_insights(conn)
    finally:
        conn.close()
    assert ins is None or "label" in ins["last"]
