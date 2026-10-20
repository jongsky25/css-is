"""Date-handling enhancements.

Covers three changes:
* event_date may not be scheduled more than 2 years ahead (server-side guard,
  not just the picker's `max`);
* the entry-window picker is date-only — a bare date is widened to the whole day
  (opens 00:00 / closes 23:59) so "closes June 16" accepts answers through all of
  June 16, while an explicit datetime-local value is kept as typed;
* dates display with the month spelled out ("June 16, 2026") so dd/mm is never
  ambiguous.
"""
import tzutil as _test_tz
import re
from datetime import date, timedelta

import app
import storage as st


# ---- pure helpers -----------------------------------------------------------

def test_event_date_bounds_two_years_ahead():
    today = date(2026, 6, 16)
    lo, hi = app._event_date_bounds(today)
    assert hi == "2028-06-16"          # exactly +2 years
    assert lo == "2021-06-16"          # -5 years floor


def test_event_date_bounds_leap_day():
    # Feb 29 has no counterpart in +2y / -5y; must not raise.
    lo, hi = app._event_date_bounds(date(2024, 2, 29))
    assert hi == "2026-02-28"
    assert lo == "2019-02-28"


def test_norm_open_close_widen_bare_date():
    assert app._norm_open("2026-06-16") == "2026-06-16T00:00"
    assert app._norm_close("2026-06-16") == "2026-06-16T23:59"
    # an explicit time is kept as typed (advanced "add specific time")
    assert app._norm_open("2026-06-16T08:30") == "2026-06-16T08:30"
    assert app._norm_close("2026-06-16T17:00") == "2026-06-16T17:00"
    # blank -> None on either side
    assert app._norm_open("") is None
    assert app._norm_close("   ") is None


def test_same_day_window_stays_open_all_day():
    # opens & closes on the same date: the day must be fully inside the window,
    # so the close bound must sort AFTER any real moment that day.
    o, c = app._norm_open("2026-06-16"), app._norm_close("2026-06-16")
    assert c > o                                   # passes the close>open check
    ctx = {"open_at": o, "close_at": c}
    assert app._window_state(ctx, now="2026-06-16T00:00") == "open"
    assert app._window_state(ctx, now="2026-06-16T12:00") == "open"
    assert app._window_state(ctx, now="2026-06-16T23:59") == "open"
    assert app._window_state(ctx, now="2026-06-17T00:00") == "closed"
    assert app._window_state(ctx, now="2026-06-15T23:59") == "not_yet"


def test_humandate_spells_out_month():
    assert app._humandate("2026-06-16") == "June 16, 2026"
    assert app._humandate("2026-06-16T08:30") == "June 16, 2026"   # date part only
    assert app._humandate("") == ""
    assert app._humandate(None) == ""
    assert app._humandate("not-a-date") == "not-a-date"            # passthrough


def test_humandt_hides_day_boundary_times():
    # 00:00 / 23:59 carry no real time-of-day -> render date only
    assert app._humandt("2026-06-16T00:00") == "June 16, 2026"
    assert app._humandt("2026-06-16T23:59") == "June 16, 2026"
    # a real time is shown
    assert app._humandt("2026-06-16T08:30").startswith("June 16, 2026")
    assert "8:30" in app._humandt("2026-06-16T08:30")
    assert app._humandt("") == ""


# ---- timezone: window logic uses local (PH) wall-clock ----------------------

def test_window_state_defaults_to_local_now(monkeypatch):
    """A survey set to open at the local 'now' must read as open even when the
    server clock is UTC (8 h behind PH). Regression: events created to open
    'now' stayed 'not open yet' for 8 hours because _window_state compared a
    PH-typed open time against a UTC datetime.now()."""
    from datetime import datetime as _dt

    # Freeze local now to a fixed PH wall-clock moment.
    fixed = _dt(2026, 6, 16, 19, 38)
    monkeypatch.setattr(app, "_now_local", lambda: fixed)

    ctx = {"open_at": "2026-06-16T19:34", "close_at": None}     # opened 4 min ago
    assert app._window_state(ctx) == "open"

    ctx_future = {"open_at": "2026-06-16T19:40", "close_at": None}
    assert app._window_state(ctx_future) == "not_yet"


def test_now_local_is_ahead_of_utc(real_application_clock):
    """_now_local() is PH time (UTC+8 by default), i.e. ahead of UTC."""
    from datetime import datetime as _dt, timezone as _tz
    delta = app._now_local() - _dt.now(_tz.utc).replace(tzinfo=None)
    # ~8 hours, allow a little slack for the two now() reads.
    assert timedelta(hours=7, minutes=59) < delta < timedelta(hours=8, minutes=1)


# ---- create flow ------------------------------------------------------------

def _rp_id(db_path):
    conn = st.connect(db_path)
    rp = conn.execute(
        "SELECT id FROM resource_person WHERE is_internal=1 LIMIT 1").fetchone()
    conn.close()
    return str(rp[0])


def _base(db_path, **extra):
    data = {"event_type": "bureau", "activity_name": "Date Forum",
            "qr_mode": "combined", "rp_id": _rp_id(db_path), "topic": "Keynote"}
    data.update(extra)
    return data


def test_event_more_than_two_years_ahead_rejected(manager, db_path):
    far = (_test_tz.today_local() + timedelta(days=3 * 366)).isoformat()
    r = manager.post("/create", data=_base(db_path, event_date=far),
                     follow_redirects=True)
    assert r.status_code == 400
    assert "2 years" in r.text


def test_event_within_two_years_accepted(manager, db_path):
    ok = (_test_tz.today_local() + timedelta(days=30)).isoformat()
    r = manager.post("/create", data=_base(db_path, event_date=ok),
                     follow_redirects=True)
    assert r.status_code == 200, r.text
    assert re.search(r"/e/([0-9a-f]{12})", r.text)


def test_create_screen_exposes_date_max(manager):
    r = manager.get("/create")
    assert r.status_code == 200
    hi = app._event_date_bounds()[1]
    assert f'max="{hi}"' in r.text


def _make_event(manager, db_path, **extra):
    ev_date = (_test_tz.today_local() + timedelta(days=10)).isoformat()
    r = manager.post("/create", data=_base(db_path, event_date=ev_date, **extra),
                     follow_redirects=True)
    assert r.status_code == 200, r.text
    return re.search(r"/e/([0-9a-f]{12})", r.text).group(1)


def _event_window(db_path, token):
    conn = st.connect(db_path)
    rows = conn.execute(
        """SELECT DISTINCT fi.open_at, fi.close_at FROM form_instance fi
           JOIN event_form ef ON ef.form_instance_id = fi.id
           JOIN event e ON e.id = ef.event_id
           WHERE e.event_token = ?""", (token,)).fetchall()
    conn.close()
    return rows


def test_window_edit_saves_date_only(manager, db_path):
    """Editing the window from the manage page with bare dates stores whole-day
    bounds on every form (the function the user flagged)."""
    tok = _make_event(manager, db_path)
    opens = (_test_tz.today_local() + timedelta(days=2)).isoformat()
    closes = (_test_tz.today_local() + timedelta(days=5)).isoformat()
    r = manager.post(f"/activities/{tok}/window",
                     data={"open_at": opens, "close_at": closes},
                     follow_redirects=False)
    assert r.status_code == 303
    rows = _event_window(db_path, tok)
    assert rows and all(o == f"{opens}T00:00" and c == f"{closes}T23:59"
                        for o, c in rows)


def test_window_edit_can_clear_back_to_always_open(manager, db_path):
    tok = _make_event(manager, db_path)
    closes = (_test_tz.today_local() + timedelta(days=5)).isoformat()
    manager.post(f"/activities/{tok}/window",
                 data={"open_at": "", "close_at": closes}, follow_redirects=False)
    # now clear both -> always open
    manager.post(f"/activities/{tok}/window",
                 data={"open_at": "", "close_at": ""}, follow_redirects=False)
    rows = _event_window(db_path, tok)
    assert rows and all(o is None and c is None for o, c in rows)


def test_window_edit_rejects_close_before_open(manager, db_path):
    tok = _make_event(manager, db_path)
    opens = (_test_tz.today_local() + timedelta(days=5)).isoformat()
    closes = (_test_tz.today_local() + timedelta(days=2)).isoformat()       # before open
    r = manager.post(f"/activities/{tok}/window",
                     data={"open_at": opens, "close_at": closes},
                     follow_redirects=False)
    assert r.status_code == 303
    assert "badwindow" in r.headers["location"]


def _qr_token(db_path, event_token):
    conn = st.connect(db_path)
    row = conn.execute(
        """SELECT fi.qr_token FROM form_instance fi
           JOIN event_form ef ON ef.form_instance_id = fi.id
           JOIN event e ON e.id = ef.event_id
           WHERE e.event_token = ? LIMIT 1""", (event_token,)).fetchone()
    conn.close()
    return row[0]


def test_spot_feedback_button_on_not_yet_page_for_staff(manager, db_path):
    """A signed-in staff member viewing a public 'not open yet' survey sees the
    Spot Feedback button (it extends to public attendee pages)."""
    opens = (_test_tz.today_local() + timedelta(days=3)).isoformat()
    tok = _make_event(manager, db_path, open_at=opens)   # future open -> not_yet
    qr = _qr_token(db_path, tok)
    r = manager.get(f"/r/{qr}")
    assert r.status_code == 403                  # closed.html for not_yet
    assert "isn't open yet" in r.text
    assert 'id="sfBtn"' in r.text                # feedback button present


def test_date_only_window_widens_to_whole_day(manager, db_path):
    """Posting bare dates to /create stores 00:00 / 23:59 bounds on every form."""
    ev_date = (_test_tz.today_local() + timedelta(days=10)).isoformat()
    close_date = (_test_tz.today_local() + timedelta(days=20)).isoformat()
    r = manager.post("/create", data=_base(
        db_path, event_date=ev_date, close_at=close_date), follow_redirects=True)
    assert r.status_code == 200, r.text
    tok = re.search(r"/e/([0-9a-f]{12})", r.text).group(1)
    conn = st.connect(db_path)
    rows = conn.execute(
        """SELECT DISTINCT fi.close_at FROM form_instance fi
           JOIN event_form ef ON ef.form_instance_id = fi.id
           JOIN event e ON e.id = ef.event_id
           WHERE e.event_token = ?""", (tok,)).fetchall()
    conn.close()
    assert rows and all(r[0] == f"{close_date}T23:59" for r in rows)
