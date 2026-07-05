"""Spot Feedback #26 — live 'who's using it + what's lately' read on /ops.

storage.usage_pulse() derives, with NO schema change, from the audit log
(sign-ins) and the cheap timestamp columns:
  * People & sign-ins — active in the last 15 min (a soft proxy, not a live
    session store), distinct staff signed in today / this week, last sign-in,
    and the recent-sign-ins list;
  * 'Lately' freshness — feedback today / this week, activities + participants
    created in the last 7 days.
These lock the windowing, plus that /ops renders the new panels.
"""
from datetime import timedelta
import storage as st
import tzutil as tz


def _fresh(tmp_path):
    conn = st.connect(str(tmp_path / "pulse.db"))
    st.init_db(conn)
    conn.execute("PRAGMA foreign_keys = OFF")   # orphan rows are fine — usage_pulse only COUNTs
    return conn


def _login(conn, actor, ts):
    conn.execute("INSERT INTO audit_log(ts, actor, action, prev_hash, row_hash) "
                 "VALUES (?,?,'login','x','y')", (ts, actor))


def _act(conn, actor, action, ts):
    conn.execute("INSERT INTO audit_log(ts, actor, action, prev_hash, row_hash) "
                 "VALUES (?,?,?,'x','y')", (ts, actor, action))


def test_usage_pulse_windows(tmp_path):
    conn = _fresh(tmp_path)
    now = tz.now_local()
    def stamp(**kw):
        return (now - timedelta(**kw)).isoformat(timespec="seconds")

    # Sign-ins (chronological so id-order matches time-order).
    _login(conn, "carol", stamp(days=10))        # outside the week
    _act(conn, "erin", "edit_remark", stamp(minutes=30))  # stale: not active now
    _act(conn, "dave", "export", stamp(minutes=5))        # active now, but not a login
    _login(conn, "alice", stamp(minutes=3))
    _login(conn, "bob", stamp(minutes=2))
    _login(conn, "alice", stamp(minutes=1))      # alice again — distinct-count still 1
    conn.commit()

    p = st.usage_pulse(conn)
    assert p["active_now"] == 3                   # alice, bob, dave within 15 min (erin/carol out)
    assert p["signed_in_today"] == 2              # distinct login actors today: alice, bob
    assert p["signed_in_week"] == 2               # carol (10d) excluded
    assert p["last_login"]["who"] == "alice"      # newest login by id
    assert len(p["recent_logins"]) == 4           # 4 login rows (cap is 6)
    assert p["recent_logins"][0]["who"] == "alice"


def test_usage_pulse_lately(tmp_path):
    conn = _fresh(tmp_path)
    now = tz.now_local()
    def stamp(**kw):
        return (now - timedelta(**kw)).isoformat(timespec="seconds")

    for ts in (stamp(minutes=1), stamp(hours=2), stamp(days=3), stamp(days=10)):
        conn.execute("INSERT INTO response(form_instance_id, submitted_at) VALUES (1, ?)", (ts,))
    # 2 today, +1 within the week, 1 old → today=2, week=3.
    for i, ts in enumerate((stamp(days=2), stamp(days=20))):
        conn.execute("INSERT INTO event(event_token, title, event_date, created_at) "
                     "VALUES (?, 'A', '2026-06-01', ?)", (f"tok{i}", ts))
    for ts in (stamp(days=1), stamp(hours=4)):
        conn.execute("INSERT INTO attendee(event_id, consent_at, consent_text, created_at) "
                     "VALUES (1, ?, 'notice', ?)", (ts, ts))
    conn.commit()

    p = st.usage_pulse(conn)
    assert p["responses_today"] == 2
    assert p["responses_week"] == 3               # 10-day-old one excluded
    assert p["activities_week"] == 1              # 20-day-old one excluded
    assert p["participants_week"] == 2


def test_usage_pulse_empty(tmp_path):
    """A brand-new system returns clean zeros, not an error."""
    p = st.usage_pulse(_fresh(tmp_path))
    assert p["active_now"] == 0 and p["signed_in_week"] == 0
    assert p["last_login"] is None and p["recent_logins"] == []
    assert p["responses_week"] == 0


def test_ops_page_renders_new_panels(admin):
    body = admin.get("/ops").text
    assert "Who's using it" in body
    assert "Active now" in body
    assert "Lately" in body
    assert "Last sign-in:" in body
