"""Home "Your recent activities" strip — st.activities_by_creator.

The home lifecycle feeds (upcoming/ongoing/concluded) only surface bureau events
(an F2 review + an `event` record). An "outside event" (Form 3 only, no event) is
invisible there — which is exactly the confusion a manager reported. This strip
gives every manager a creator-scoped list of what they made, so nothing is hidden.
"""
from __future__ import annotations
import storage as st


def _fresh(tmp_path):
    conn = st.connect(str(tmp_path / "mine.db"))
    st.init_db(conn)
    return conn


def test_outside_event_is_visible_to_its_creator(tmp_path):
    conn = _fresh(tmp_path)
    # An outside event: Form 3 only, NO event record (the case the feeds skip).
    fid = st.create_form_instance(conn, 3, "F3", "2026-06-16", topic="Crisis Management",
                                  created_by="vc@doh.local")
    st.record_response(conn, fid, [("SQD1", 6)])

    mine = st.activities_by_creator(conn, "vc@doh.local")
    assert [a["topic"] for a in mine] == ["Crisis Management"]
    a = mine[0]
    assert a["responses"] == 1
    assert a["kind"] == "Speaker review"
    assert a["event_token"] is None
    assert a["link"] == f"/r/{a['qr_token']}"   # no event -> link to the public form


def test_only_your_own_activities(tmp_path):
    conn = _fresh(tmp_path)
    st.create_form_instance(conn, 3, "F3", "2026-06-16", topic="Mine", created_by="me@x")
    st.create_form_instance(conn, 3, "F3", "2026-06-16", topic="Theirs", created_by="you@x")
    assert [a["topic"] for a in st.activities_by_creator(conn, "me@x")] == ["Mine"]
    # Unattributed (pre-migration) rows belong to nobody.
    st.create_form_instance(conn, 3, "F3", "2026-06-16", topic="Orphan")
    assert st.activities_by_creator(conn, "") == []
    assert "Orphan" not in [a["topic"] for a in st.activities_by_creator(conn, "me@x")]


def test_bureau_event_collapses_to_one_row_via_monitor(tmp_path):
    conn = _fresh(tmp_path)
    # A bureau event = one F2 + one speaker F3, all created by the same manager.
    f2 = st.create_form_instance(conn, 2, "F2", "2026-06-16", topic="Forum",
                                 created_by="mgr@x")
    f3 = st.create_form_instance(conn, 3, "F3", "2026-06-16", topic="Talk",
                                 created_by="mgr@x")
    ev = st.create_event(conn, "Forum", "2026-06-16",
                         form_instance_ids=[f2, f3], created_by="mgr@x")

    mine = st.activities_by_creator(conn, "mgr@x")
    assert len(mine) == 1                      # collapsed, not one row per form
    assert mine[0]["survey_type"] == 2         # the F2 review represents the event
    assert mine[0]["link"] == f"/monitor/{ev['event_token']}"


def test_since_days_limits_strip_by_event_date(tmp_path):
    from datetime import timedelta
    import tzutil as tz
    conn = _fresh(tmp_path)
    recent_date = (tz.now_local() - timedelta(days=5)).strftime("%Y-%m-%d")
    old_date = (tz.now_local() - timedelta(days=400)).strftime("%Y-%m-%d")
    future_date = (tz.now_local() + timedelta(days=10)).strftime("%Y-%m-%d")
    st.create_form_instance(conn, 3, "F3", recent_date, topic="Recent", created_by="me@x")
    st.create_form_instance(conn, 3, "F3", old_date, topic="Backlog", created_by="me@x")
    st.create_form_instance(conn, 3, "F3", future_date, topic="Upcoming", created_by="me@x")

    # No bound -> all three; 30-day window -> drops the years-old backlog but keeps
    # the recent one AND the upcoming one (future event_date passes the cutoff).
    assert {a["topic"] for a in st.activities_by_creator(conn, "me@x", limit=50)} == {
        "Recent", "Backlog", "Upcoming"}
    win = {a["topic"] for a in st.activities_by_creator(conn, "me@x", limit=50, since_days=30)}
    assert win == {"Recent", "Upcoming"}


def test_home_renders_the_strip_for_its_creator(manager, app_mod):
    """End-to-end: an activity the manager created shows in the home strip HTML."""
    import storage as st
    from datetime import timedelta
    conn = st.connect(app_mod.DB)
    # Date it relative to "today" so it stays inside the strip's 7-day window
    # regardless of when the suite runs (a fixed date drifts out and the row vanishes).
    recent = (app_mod._today_local() - timedelta(days=1)).isoformat()
    fid = st.create_form_instance(conn, 3, "F3", recent,
                                  topic="Strip Probe Activity",
                                  created_by="manager@test.local")
    st.record_response(conn, fid, [("SQD1", 6)])
    conn.commit(); conn.close()
    r = manager.get("/css")
    assert r.status_code == 200
    assert "Your recent activities" in r.text
    assert "Strip Probe Activity" in r.text
