"""Multi-day activities — an optional start→end date range.

Covers:
  * the humandaterange display filter (collapsing month/year);
  * creating an activity with an end date round-trips it to the event AND every
    form, while a single-day create keeps end_date NULL;
  * an end on/before the start is treated as single-day (not an error), and a
    non-date end is rejected;
  * editing the dates from the manage page re-dates the event + its forms;
  * the reporting period always keys off the START date.
"""
import re
import app as A
import storage as st


def _internal_rp(db_path):
    conn = st.connect(db_path)
    rp = conn.execute("SELECT id FROM resource_person WHERE is_internal=1 LIMIT 1").fetchone()
    conn.close()
    return str(rp[0])


def _create(manager, db_path, *, start, end=None, title="Range Forum"):
    data = {"event_type": "bureau", "activity_name": title,
            "event_date": start, "venue": "Hall A", "qr_mode": "combined",
            "rp_id": _internal_rp(db_path), "topic": "Keynote"}
    if end is not None:
        data["end_date"] = end
    r = manager.post("/create", data=data, follow_redirects=True)
    return r


def _event_token(r):
    return re.search(r"/e/([0-9a-f]{12})", r.text).group(1)


def _event_and_forms(db_path, tok):
    conn = st.connect(db_path)
    ev = conn.execute("SELECT event_date, end_date FROM event WHERE event_token=?",
                      (tok,)).fetchone()
    forms = conn.execute("""SELECT fi.event_date, fi.end_date FROM event_form ef
                            JOIN event e ON e.id=ef.event_id
                            JOIN form_instance fi ON fi.id=ef.form_instance_id
                            WHERE e.event_token=?""", (tok,)).fetchall()
    conn.close()
    return ev, forms


# --- the display filter -----------------------------------------------------

def test_humandaterange_collapses_and_widens():
    f = A._humandaterange
    # No end (or end <= start) -> single date, exactly like humandate.
    assert f("2026-06-16", None) == "June 16, 2026"
    assert f("2026-06-16", "2026-06-16") == "June 16, 2026"
    assert f("2026-06-16", "2026-06-10") == "June 16, 2026"
    # Same month -> collapse the day span and share the year.
    assert f("2026-06-16", "2026-06-18") == "June 16–18, 2026"
    # Same year, different month.
    assert f("2026-06-28", "2026-07-02") == "June 28 – July 2, 2026"
    # Across years -> both dates spelled in full.
    assert f("2026-12-30", "2027-01-02") == "December 30, 2026 – January 2, 2027"


# --- creation ---------------------------------------------------------------

def test_create_single_day_leaves_end_null(manager, db_path):
    r = _create(manager, db_path, start="2026-06-11")
    tok = _event_token(r)
    ev, forms = _event_and_forms(db_path, tok)
    assert ev == ("2026-06-11", None)
    assert forms and all(fd == ("2026-06-11", None) for fd in forms)


def test_create_multi_day_round_trips_end(manager, db_path):
    r = _create(manager, db_path, start="2026-06-16", end="2026-06-18")
    tok = _event_token(r)
    ev, forms = _event_and_forms(db_path, tok)
    assert ev == ("2026-06-16", "2026-06-18")
    assert forms and all(fd == ("2026-06-16", "2026-06-18") for fd in forms)
    # The confirmation page shows the collapsed range.
    assert "June 16–18, 2026" in r.text


def test_create_end_before_start_is_single_day(manager, db_path):
    # An end on/before the start isn't an error — it's just a single-day activity.
    r = _create(manager, db_path, start="2026-06-16", end="2026-06-10")
    assert r.status_code == 200
    tok = _event_token(r)
    ev, _ = _event_and_forms(db_path, tok)
    assert ev == ("2026-06-16", None)


def test_create_non_date_end_is_rejected(manager, db_path):
    r = manager.post("/create", data={
        "event_type": "bureau", "activity_name": "Bad End",
        "event_date": "2026-06-16", "end_date": "not-a-date",
        "venue": "Hall A", "qr_mode": "combined",
        "rp_id": _internal_rp(db_path), "topic": "Keynote",
    }, follow_redirects=True)
    assert r.status_code == 400
    assert "end date" in r.text.lower()


# --- manage editing ---------------------------------------------------------

def test_manage_dates_edit_redates_event_and_forms(manager, db_path):
    tok = _event_token(_create(manager, db_path, start="2026-06-11"))
    r = manager.post(f"/activities/{tok}/dates",
                     data={"event_date": "2026-07-01", "end_date": "2026-07-03"},
                     follow_redirects=False)
    assert r.status_code == 303 and "dateok=1" in r.headers["location"]
    ev, forms = _event_and_forms(db_path, tok)
    assert ev == ("2026-07-01", "2026-07-03")
    assert forms and all(fd == ("2026-07-01", "2026-07-03") for fd in forms)


def test_manage_dates_clearing_end_returns_to_single_day(manager, db_path):
    tok = _event_token(_create(manager, db_path, start="2026-06-16", end="2026-06-18"))
    manager.post(f"/activities/{tok}/dates",
                 data={"event_date": "2026-06-16", "end_date": ""},
                 follow_redirects=False)
    ev, _ = _event_and_forms(db_path, tok)
    assert ev == ("2026-06-16", None)


def test_manage_dates_bad_start_rejected_no_change(manager, db_path):
    tok = _event_token(_create(manager, db_path, start="2026-06-11"))
    r = manager.post(f"/activities/{tok}/dates",
                     data={"event_date": "garbage", "end_date": ""},
                     follow_redirects=False)
    assert r.status_code == 303 and "err=baddates" in r.headers["location"]
    ev, _ = _event_and_forms(db_path, tok)
    assert ev == ("2026-06-11", None)


def test_reporting_period_keys_off_start_date(manager, db_path):
    # A Dec 30 → Jan 2 activity must bucket into the START's year/quarter.
    tok = _event_token(_create(manager, db_path, start="2026-12-30", end="2027-01-02"))
    ev, _ = _event_and_forms(db_path, tok)
    assert ev == ("2026-12-30", "2027-01-02")
    import css_is_engine as eng
    import pandas as pd
    atoms = pd.DataFrame({"event_date": [ev[0]]})
    tagged = eng.assign_periods(atoms)
    assert tagged["year"].iloc[0] == "2026"
    assert tagged["quarter"].iloc[0] == "2026-Q4"
